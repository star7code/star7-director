"""Prefer RAM for RGB buffers; use file backing only under memory pressure."""
import contextvars
import logging
import math
import shutil
import uuid
import weakref
from contextlib import contextmanager
from pathlib import Path

_ACTIVE=contextvars.ContextVar('star7_director_frame_storage',default=False)
MAPPED_THRESHOLD=512*1024**2
_LOG=logging.getLogger('Star7DirectorFrames')


@contextmanager
def frame_storage_scope():
    token=_ACTIVE.set(True)
    try:yield
    finally:_ACTIVE.reset(token)


def storage_active():return _ACTIVE.get()


def _memory_snapshot():
    try:
        import psutil
        memory=psutil.virtual_memory()
        return int(memory.available),int(memory.total)
    except (ImportError,OSError,AttributeError):
        return None


def _prefer_mapping(size):
    if size<MAPPED_THRESHOLD:return False
    snapshot=_memory_snapshot()
    # Without a trustworthy estimate, try RAM. A real CPU allocation failure
    # can still fall back below; an unknown reading must not force disk I/O.
    if snapshot is None:return False
    available,total=snapshot
    reserve=max(2*1024**3,min(total//10,8*1024**3))
    workspace=min(size//4,2*1024**3)
    return available<size+reserve+workspace


def _release(mapping,path):
    try:mapping.close()
    finally:
        try:path.unlink(missing_ok=True)
        except OSError:_LOG.warning('Star7 frame buffer | temporary file could not be removed | %s',path)


def allocate_frames(shape,dtype=None,device='cpu'):
    import numpy as np
    import torch
    dtype=dtype or torch.float32
    size=math.prod(shape)*torch.empty((),dtype=dtype).element_size()
    if not storage_active() or torch.device(device).type!='cpu' or dtype!=torch.float32:
        return torch.empty(shape,dtype=dtype,device=device)
    if not _prefer_mapping(size):
        try:
            result=torch.empty(shape,dtype=dtype,device=device)
            if size>=MAPPED_THRESHOLD:
                _LOG.info('Star7 frame buffer | in-memory float32 | %.0f MiB | sufficient RAM budget',size/1024**2)
            return result
        except (MemoryError,RuntimeError) as error:
            cpu_oom=(isinstance(error,(MemoryError,torch.OutOfMemoryError))
                     or 'DefaultCPUAllocator' in str(error) and any(word in str(error).lower() for word in ('allocate','memory')))
            if not cpu_oom:raise
        # Leave the failed allocation's traceback before allocating its fallback.
        _LOG.warning('Star7 frame buffer | CPU allocation failed; falling back to temporary file backing')
    import folder_paths
    root=Path(folder_paths.get_temp_directory()).resolve()/'star7-director-frames'
    root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<size+512*1024**2:
        raise RuntimeError(f'Not enough free temporary disk space for video frames ({size/1024**3:.2f} GiB): {root}')
    path=root/(uuid.uuid4().hex+'.frames')
    array=None
    try:
        with path.open('xb') as file:file.truncate(size)
        array=np.memmap(path,dtype=np.float32,mode='r+',shape=tuple(shape))
        # torch keeps this NumPy owner alive through its storage, including views.
        # Close/unlink only when the last tensor using the mapped pixels is gone.
        weakref.finalize(array,_release,array._mmap,path)
        result=torch.from_numpy(array)
    except BaseException:
        if array is not None:array._mmap.close()
        path.unlink(missing_ok=True)
        raise
    _LOG.info('Star7 frame buffer | file-backed float32 | %.0f MiB | low RAM budget or allocation failure | shape=%s',size/1024**2,tuple(shape))
    return result


def decode_native_frames(vae,latent):
    """Use H3's existing native chunk writer with a reclaimable RGB destination."""
    import torch
    native=getattr(vae,'first_stage_model',None)
    compatible=(storage_active() and type(native).__name__=='MiniMaxH3VideoVAE'
                and getattr(native,'comfy_has_chunked_io',False)
                and callable(getattr(vae,'prepare_decode',None))
                and torch.device(vae.output_device).type=='cpu'
                and vae.vae_output_dtype()==torch.float32)
    if not compatible:return vae.decode(latent)
    import comfy.model_management as mm
    import comfy.model_prefetch
    shape=native.decode_output_shape(latent.shape)
    if math.prod(shape)*4<MAPPED_THRESHOLD:return vae.decode(latent)
    b,c,t,h,w=shape
    # NHWC backing improves CPU validation and encoding locality, while the
    # native decoder still writes exactly the same NCTHW float32 pixel values.
    output=allocate_frames((b,t,h,w,c))
    buffer=output.permute(0,4,1,2,3)
    vae.throw_exception_if_invalid()
    recover=False
    try:
        with mm.cuda_device_context(vae.device):
            with comfy.model_prefetch.pause_malloc_graph():vae.prepare_decode(latent.shape)
            for index in range(b):
                mm.throw_exception_if_processing_interrupted()
                samples=latent[index:index+1].to(device=vae.device,dtype=vae.vae_dtype)
                native.decode(samples,output_buffer=buffer[index:index+1])
                vae.process_output(buffer[index:index+1])
    except mm.OOM_EXCEPTION:
        # Preserve the core VAE's supported OOM/tiling recovery path.
        # Leave the exception scope first so its traceback releases GPU chunks.
        recover=True
    if recover:
        del buffer,output
        _LOG.warning('Star7 frame buffer | native decode OOM; using VAE-managed recovery')
        return vae.decode(latent)
    return output.reshape(b*t,h,w,c)


class SelectedFrames:
    """An ordered frame view; endpoint timing must not copy an entire RGB clip."""
    def __init__(self,images,indices):
        self.images=images;self.indices=tuple(int(i) for i in indices)
        self.shape=(len(self.indices),*images.shape[1:]);self.ndim=4
        self.device=images.device;self.dtype=images.dtype
    def __len__(self):return len(self.indices)
    def __getitem__(self,index):
        if isinstance(index,slice):return SelectedFrames(self.images,self.indices[index])
        return self.images[self.indices[index]]
