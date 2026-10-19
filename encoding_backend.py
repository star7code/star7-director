"""Video compression backend selection, independent of H3 model acceleration."""
import logging
import subprocess
from fractions import Fraction
from functools import lru_cache

LOG=logging.getLogger('Star7DirectorEncode')
CPU={'h264-mp4':'libx264','h265-mp4':'libx265','vp9-webm':'libvpx-vp9'}
GPU={'h264-mp4':'h264_nvenc','h265-mp4':'hevc_nvenc'}


def nvenc_options(quality=19,preset='medium',bitrate=None):
    options={'preset':{'fast':'p4','medium':'p6','slow':'p7'}[preset],'tune':'hq','rc':'vbr'}
    if bitrate is None:options.update(cq=str(int(quality)),b='0')
    else:options['b']=str(int(bitrate))
    return options


@lru_cache(maxsize=32)
def hardware_available(codec,pix_fmt,engine):
    """Probe real encoder initialization; a compiled codec list is insufficient."""
    try:
        if engine=='pyav':
            import av,numpy as np
            context=av.CodecContext.create(codec,'w');context.width=256;context.height=256
            context.pix_fmt=pix_fmt;context.time_base=Fraction(1,24);context.framerate=Fraction(24)
            context.bit_rate=0;context.options=nvenc_options(preset='fast')
            context.open()
            frame=av.VideoFrame.from_ndarray(np.zeros((256,256,3),dtype=np.uint8),format='rgb24')
            frame=frame.reformat(format=pix_fmt);frame.pts=0;frame.time_base=Fraction(1,24)
            list(context.encode(frame));list(context.encode(None))
        else:
            import imageio_ffmpeg
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-v','error','-nostdin','-f','lavfi','-i','color=c=black:s=256x256:r=24:d=0.05',
                     '-an','-c:v',codec,'-pix_fmt',pix_fmt,'-preset','p4','-tune','hq','-rc','vbr','-cq','19','-b:v','0','-f','null','-']
            result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-600:])
        return True
    except Exception as error:
        LOG.info('Star7 video encode | hardware unavailable | codec=%s engine=%s reason=%s',codec,engine,str(error).strip()[-600:])
        return False


def choose_encoder(fmt,mode='auto',pix_fmt='yuv420p',engine='pyav',quality=19,width=None,height=None):
    if mode not in ('auto','gpu','cpu'):raise ValueError('无效视频编码方式')
    if mode=='cpu':return CPU[fmt]
    # Preserve true CRF 0 semantics; NVENC CQ 0 means automatic, not lossless.
    supported=fmt in GPU and int(quality)!=0
    if mode=='auto' and width is not None and height is not None and min(width,height)<256:supported=False
    if supported and hardware_available(GPU[fmt],pix_fmt,engine):return GPU[fmt]
    if mode=='gpu':raise ValueError('当前视频格式、质量或设备无法使用 NVIDIA GPU 硬件编码；请选择自动或 CPU 编码')
    return CPU[fmt]


class HardwareEncoderUnavailable(RuntimeError):pass
