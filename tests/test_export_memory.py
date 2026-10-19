"""Bound final RGB storage and endpoint reordering without changing pixel values."""
import gc,importlib,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('export_memory_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
memory=importlib.import_module(pkg.__name__+'.vendor.h3.frame_memory')
timing=importlib.import_module(pkg.__name__+'.endpoint_timing')
saver=importlib.import_module(pkg.__name__+'.save_video')


class Tests(unittest.TestCase):
 def test_storage_policy_reserves_ram_but_keeps_large_buffers_in_memory_when_it_fits(self):
  gib=1024**3
  with patch.object(memory,'_memory_snapshot',return_value=(40*gib,64*gib)):
   self.assertFalse(memory._prefer_mapping(7*gib))
  with patch.object(memory,'_memory_snapshot',return_value=(8*gib,32*gib)):
   self.assertTrue(memory._prefer_mapping(7*gib))
  with patch.object(memory,'_memory_snapshot',return_value=None):
   self.assertFalse(memory._prefer_mapping(7*gib))

 def test_sufficient_ram_never_touches_temp_directory(self):
  import folder_paths
  with patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_memory_snapshot',return_value=(40*1024**3,64*1024**3)),patch.object(folder_paths,'get_temp_directory',side_effect=AssertionError('unnecessary disk access')):
   with memory.frame_storage_scope():pixels=memory.allocate_frames((2,8,8,3))
   pixels.fill_(.25);self.assertTrue(torch.equal(pixels,torch.full_like(pixels,.25)))

 def test_low_ram_uses_temporary_backing(self):
  import folder_paths
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_memory_snapshot',return_value=(0,32*1024**3)):
   with memory.frame_storage_scope():pixels=memory.allocate_frames((2,8,8,3))
   pixels.fill_(.5);self.assertEqual(len(list(Path(tmp).rglob('*.frames'))),1)
   del pixels;gc.collect();self.assertFalse(list(Path(tmp).rglob('*.frames')))

 def test_real_cpu_allocation_failure_falls_back_but_other_errors_propagate(self):
  import folder_paths
  original=torch.empty;shape=(2,8,8,3)
  def fail(shape_value,*args,**kwargs):
   if tuple(shape_value)==shape:raise MemoryError('synthetic CPU allocation failure')
   return original(shape_value,*args,**kwargs)
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'_prefer_mapping',return_value=False):
   with memory.frame_storage_scope(),patch.object(torch,'empty',side_effect=fail):pixels=memory.allocate_frames(shape)
   pixels.fill_(.75);self.assertEqual(len(list(Path(tmp).rglob('*.frames'))),1)
   del pixels;gc.collect();self.assertFalse(list(Path(tmp).rglob('*.frames')))
  def invalid(shape_value,*args,**kwargs):
   if tuple(shape_value)==shape:raise RuntimeError('invalid synthetic shape')
   return original(shape_value,*args,**kwargs)
  with memory.frame_storage_scope(),patch.object(memory,'_prefer_mapping',return_value=False),patch.object(torch,'empty',side_effect=invalid):
   with self.assertRaisesRegex(RuntimeError,'invalid synthetic shape'):memory.allocate_frames(shape)

 def test_mapped_float_pixels_and_cleanup_follow_last_tensor_view(self):
  import folder_paths
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_prefer_mapping',return_value=True):
   with memory.frame_storage_scope():
    pixels=memory.allocate_frames((4,8,8,3));pixels.fill_(.123456789);view=pixels[2]
    files=list(Path(tmp).rglob('*.frames'));self.assertEqual(len(files),1)
    expected=torch.full_like(view,.123456789);self.assertTrue(torch.equal(view,expected))
    del pixels;gc.collect();self.assertTrue(files[0].exists())
    del view;gc.collect();self.assertFalse(files[0].exists())
  self.assertFalse(memory.storage_active())

 def test_native_chunk_writer_uses_same_float_pixels_and_loader(self):
  import folder_paths
  expected=torch.linspace(0,1,1*3*7*8*8).reshape(1,3,7,8,8)
  calls=[]
  class MiniMaxH3VideoVAE:
   comfy_has_chunked_io=True
   def decode_output_shape(self,shape):return expected.shape
   def decode(self,samples,output_buffer=None):
    calls.append(('native',samples.dtype))
    for start in range(0,7,2):output_buffer[:,:,start:start+2].copy_(expected[:,:,start:start+2])
    return output_buffer
  vae=types.SimpleNamespace(first_stage_model=MiniMaxH3VideoVAE(),output_device=torch.device('cpu'),device=torch.device('cpu'),vae_dtype=torch.float32,
   vae_output_dtype=lambda:torch.float32,throw_exception_if_invalid=lambda:None,
   prepare_decode=lambda shape:calls.append(('prepare',tuple(shape))),process_output=lambda p:p,
   decode=lambda latent:expected.movedim(1,-1))
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_prefer_mapping',return_value=True):
   with memory.frame_storage_scope():
    result=memory.decode_native_frames(vae,torch.zeros(1,24,2,1,1))
    self.assertTrue(result.is_contiguous());self.assertEqual(result.shape,(7,8,8,3))
    self.assertTrue(torch.equal(result,expected.movedim(1,-1).reshape(7,8,8,3)))
    self.assertEqual([c[0] for c in calls],['prepare','native'])
    del result;gc.collect();self.assertFalse(list(Path(tmp).rglob('*.frames')))

 def test_non_native_vae_preserves_its_decode_path(self):
  sentinel=object();vae=types.SimpleNamespace(decode=lambda value:sentinel)
  with memory.frame_storage_scope():self.assertIs(memory.decode_native_frames(vae,None),sentinel)

 def test_native_oom_releases_failed_chunk_before_core_recovery(self):
  import weakref,folder_paths
  import comfy.model_management as mm
  held=[];expected=torch.zeros(1,4,8,8,3)
  class MiniMaxH3VideoVAE:
   comfy_has_chunked_io=True
   def decode_output_shape(self,shape):return (1,3,4,8,8)
   def decode(self,*args,**kwargs):
    chunk=torch.ones(4);held.append(weakref.ref(chunk));raise mm.OOM_EXCEPTION('synthetic OOM')
  def recover(latent):
   self.assertIsNone(held[0]());return expected
  vae=types.SimpleNamespace(first_stage_model=MiniMaxH3VideoVAE(),output_device=torch.device('cpu'),device=torch.device('cpu'),vae_dtype=torch.float32,
   vae_output_dtype=lambda:torch.float32,throw_exception_if_invalid=lambda:None,prepare_decode=lambda shape:None,process_output=lambda p:p,decode=recover)
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_prefer_mapping',return_value=True):
   with memory.frame_storage_scope():self.assertIs(memory.decode_native_frames(vae,torch.zeros(1,24,2,1,1)),expected)
   gc.collect();self.assertFalse(list(Path(tmp).rglob('*.frames')))

 def test_real_native_temporal_schedule_writes_identical_mapped_pixels(self):
  from comfy.ldm.minimax.vae import MiniMaxH3VideoVAE
  import folder_paths
  native=MiniMaxH3VideoVAE(encoder=False,decoder=False)
  native.decoder=types.SimpleNamespace(out_channels=3)
  def pixels(z,frames=slice(None)):
   values=z[:,:3].repeat_interleave(4,dim=2).repeat_interleave(16,dim=3).repeat_interleave(16,dim=4)
   return values[:,:,frames]
  native._adaptive_decode=pixels
  vae=types.SimpleNamespace(first_stage_model=native,output_device=torch.device('cpu'),device=torch.device('cpu'),vae_dtype=torch.float32,
   vae_output_dtype=lambda:torch.float32,throw_exception_if_invalid=lambda:None,prepare_decode=lambda shape:None,
   process_output=lambda p:p,decode=lambda latent:native.decode(latent).movedim(1,-1))
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(folder_paths,'get_temp_directory',return_value=tmp),patch.object(memory,'MAPPED_THRESHOLD',1),patch.object(memory,'_prefer_mapping',return_value=True):
   for tokens in (1,2,7,12,17):
    latent=torch.linspace(-.2,.3,24*tokens).reshape(1,24,tokens,1,1)
    dense=vae.decode(latent).reshape(-1,16,16,3)
    with memory.frame_storage_scope():mapped=memory.decode_native_frames(vae,latent)
    self.assertTrue(torch.equal(mapped,dense),f'native temporal overlap/padding differs at {tokens} tokens')
    del mapped;gc.collect()
   self.assertFalse(list(Path(tmp).rglob('*.frames')))

 def test_face_composite_buffer_matches_original_and_preserves_source(self):
  face=importlib.import_module(pkg.__name__+'.vendor.h3.vendor.h3facerefine.core')
  import comfy.model_management as mm
  base=torch.linspace(.1,.8,4*32*32*3).reshape(4,32,32,3)
  crops=base[:,8:24,8:24].clone().flip(2)
  transform={'boxes':[(8,8,16,16)]*4,'source':list(range(4)),'weights':[1.,.5,0.,1.],
   'canvas':(16,16),'src_size':(32,32),'face_rect':[(2,2,12,12)]*4}
  before=base.clone();args=(base,crops,transform,'face_only',0,2,.7,.8)
  with patch.object(mm,'get_torch_device',return_value=torch.device('cpu')):
   dense=face.H3FaceStitch().run(*args)[0]
   destination=torch.empty_like(base)
   mapped=face.H3FaceStitch().run(*args,output_buffer=destination)[0]
  self.assertIs(mapped,destination);self.assertTrue(torch.equal(mapped,dense));self.assertTrue(torch.equal(base,before))

 def test_endpoint_selection_is_lazy_and_encodes_identical_video(self):
  import av
  frames=torch.linspace(0,1,43*32*32*3).reshape(43,32,32,3)
  audio={'sample_rate':24000,'waveform':torch.zeros(1,1,43000)}
  with memory.frame_storage_scope():selected,sound=timing.fit_endpoints(frames,audio,24)
  indices=torch.linspace(0,42,24).round().long();expected=frames[indices]
  self.assertIsInstance(selected,memory.SelectedFrames);self.assertIs(selected.images,frames)
  self.assertEqual(len(selected),24);self.assertTrue(torch.equal(selected[0],frames[0]));self.assertTrue(torch.equal(selected[-1],frames[-1]))
  self.assertTrue(all(torch.equal(selected[i],expected[i]) for i in range(24)))
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   a,b=Path(tmp)/'lazy.mp4',Path(tmp)/'dense.mp4'
   saver.encode_mp4(a,selected,sound);saver.encode_mp4(b,expected,sound)
   with av.open(str(a)) as f:actual=[x.to_ndarray(format='rgb24') for x in f.decode(video=0)]
   with av.open(str(b)) as f:dense=[x.to_ndarray(format='rgb24') for x in f.decode(video=0)]
   import numpy as np
   self.assertEqual(len(actual),len(dense));self.assertTrue(all(np.array_equal(x,y) for x,y in zip(actual,dense)))

 def test_scope_recovers_on_exception(self):
  with self.assertRaisesRegex(RuntimeError,'cancelled'):
   with memory.frame_storage_scope():
    self.assertTrue(memory.storage_active());raise RuntimeError('cancelled')
  self.assertFalse(memory.storage_active())

 def test_executor_drops_intermediates_without_waiting_for_cyclic_gc(self):
  import weakref
  desk=importlib.import_module(pkg.__name__+'.desk');runtime=importlib.import_module(pkg.__name__+'.runtime')
  references=[]
  class Producer:
   FUNCTION='run'
   @classmethod
   def INPUT_TYPES(cls):return {'required':{}}
   def run(self):
    value=torch.ones(2,8,8,3);references.append(weakref.ref(value));return (value,)
  class Consumer:
   FUNCTION='run'
   @classmethod
   def INPUT_TYPES(cls):return {'required':{'images':('ANY',)}}
   def run(self,images):return ('done',)
  graph={'a':{'class_type':'Producer','inputs':{}},'b':{'class_type':'Consumer','inputs':{'images':['a',0]}}}
  was_enabled=gc.isenabled();gc.disable()
  try:
   with patch.object(runtime,'registry',side_effect=lambda name:Producer if name=='Producer' else Consumer):
    result=desk.execute_internal(graph,['b',0],{'id':'test'},'s')
   self.assertEqual(result['result'],('done',));self.assertIsNone(references[0]())
  finally:
   if was_enabled:gc.enable()


if __name__=='__main__':unittest.main()
