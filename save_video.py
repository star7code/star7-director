"""Director-owned MP4 encoding with PyAV; no video-node plugin required."""
import shutil,uuid
from fractions import Fraction
from pathlib import Path
from .runtime import data_root
from .output_paths import reserve_generated

class Star7DirectorSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',),'frame_rate':('FLOAT',{'default':24}),
                'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'})},
                'optional':{'audio':('AUDIO',),'crf':('INT',{'default':19,'min':0,'max':51}),
                'format':(['video/h264-mp4'],),'pix_fmt':(['yuv420p'],),
                'loop_count':('INT',{'default':0}),'filename_prefix':('STRING',{'default':''}),
                'pingpong':('BOOLEAN',{'default':False}),'save_output':('BOOLEAN',{'default':True}),
                'save_metadata':('BOOLEAN',{'default':False})}}
    RETURN_TYPES=('STAR7_DIRECTOR_VIDEO',)
    OUTPUT_NODE=True
    FUNCTION='save'
    CATEGORY='Star7/导演台'
    def save(self,director_plan,shot_id,**kwargs):
        import folder_paths
        from .core import identifier
        identifier(director_plan['id']);identifier(shot_id)
        temp_root=Path(folder_paths.get_temp_directory()).resolve();relative='star7-director-staging/'+uuid.uuid4().hex;private=(temp_root/relative).resolve()
        if not private.is_relative_to(temp_root):raise ValueError('临时视频路径无效')
        private.mkdir(parents=True,exist_ok=False);target=None
        try:
            if kwargs.get('format','video/h264-mp4')!='video/h264-mp4':raise ValueError('导演台内置编码使用 H.264 MP4')
            if kwargs.get('pingpong') or kwargs.get('loop_count',0):raise ValueError('镜头导出不支持循环或往返播放')
            source=private/'clip.mp4'
            from .export_settings import settings
            encode_mp4(source,kwargs['images'],kwargs.get('audio'),kwargs.get('frame_rate',24),kwargs.get('crf',19),encoder=settings(director_plan)['encoder'])
            root=Path(folder_paths.get_output_directory()).resolve();target=reserve_generated(root,data_root(),director_plan['id'],shot_id)
            shutil.copyfile(source,target);relative_path=target.relative_to(root)
            preview={'filename':target.name,'subfolder':relative_path.parent.as_posix(),'type':'output','format':'video/h264-mp4','frame_rate':kwargs.get('frame_rate',24)}
            return {'ui':{'gifs':[preview]},'result':((True,[str(target)]),)}
        except Exception:
            if target:target.unlink(missing_ok=True)
            raise
        finally:
            # Only this freshly-created UUID staging directory is removed.
            if private.is_relative_to(temp_root) and private.parent.name=='star7-director-staging':shutil.rmtree(private)

def encode_mp4(path,images,audio=None,frame_rate=24,crf=19,encoder='cpu',preset='medium'):
    from .encoding_backend import choose_encoder,HardwareEncoderUnavailable,LOG
    shape=getattr(images,'shape',None)
    if not shape or len(shape)!=4 or shape[0]<1 or shape[3] not in (3,4):raise ValueError('视频编码需要非空的 NHWC RGB 图像')
    selected=choose_encoder('h264-mp4',encoder,quality=crf,width=shape[2],height=shape[1])
    try:return _encode_mp4(path,images,audio,frame_rate,crf,selected,preset)
    except HardwareEncoderUnavailable:
        if encoder!='auto':raise
        LOG.warning('Star7 video encode | hardware initialization failed; retrying with CPU H.264')
        Path(path).unlink(missing_ok=True)
        return _encode_mp4(path,images,audio,frame_rate,crf,'libx264',preset)


def _encode_mp4(path,images,audio,frame_rate,crf,codec,preset):
    import av,numpy as np,logging,time
    started=time.perf_counter();conversion_seconds=0.0
    shape=getattr(images,'shape',None)
    if not shape or len(shape)!=4 or shape[0]<1 or shape[3] not in (3,4):raise ValueError('视频编码需要非空的 NHWC RGB 图像')
    count,height,width,_=shape
    if width%2 or height%2:raise ValueError('H.264 视频宽高必须是偶数')
    rate=Fraction(str(frame_rate))
    if not 0<rate<=120 or not 0<=int(crf)<=51:raise ValueError('视频编码帧率或 CRF 无效')
    def numpy(value):return value.detach().cpu().numpy() if hasattr(value,'detach') else np.asarray(value)
    log=logging.getLogger('Star7DirectorEncode')
    log.info('Star7 video encode | codec=%s | %dx%d frames=%d fps=%s | frame_source=%s',codec,width,height,count,rate,type(images).__name__)
    with av.open(str(path),'w',format='mp4',options={'movflags':'+faststart'}) as container:
        video=container.add_stream(codec,rate=rate)
        video.width=int(width);video.height=int(height);video.pix_fmt='yuv420p'
        if codec.endswith('_nvenc'):
            from .encoding_backend import nvenc_options
            video.bit_rate=0;video.options=nvenc_options(crf,preset)
        else:video.options={'crf':str(int(crf)),'preset':preset}
        sound=None;waveform=None
        if audio is not None:
            sample_rate=int(audio.get('sample_rate',0));waveform=audio.get('waveform')
            if sample_rate<=0 or waveform is None:raise ValueError('音频缺少波形或有效采样率')
            waveform=numpy(waveform)
            if waveform.ndim==3:
                if waveform.shape[0]!=1:raise ValueError('镜头音频只支持一个批次')
                waveform=waveform[0]
            if waveform.ndim!=2 or waveform.shape[0] not in (1,2):raise ValueError('镜头音频需要单声道或双声道波形')
            waveform=np.ascontiguousarray(waveform,dtype=np.float32)
            if not np.isfinite(waveform).all():raise ValueError('音频波形包含无效数值')
            if waveform.shape[1]:
                layout='mono' if waveform.shape[0]==1 else 'stereo'
                # Keep the model's native rate (H3 commonly supplies 32 kHz),
                # matching the previous encoder rather than forcing 48 kHz.
                encoding_rate=sample_rate if sample_rate in (8000,11025,12000,16000,22050,24000,32000,44100,48000,64000,88200,96000) else 48000
                sound=container.add_stream('aac',rate=encoding_rate);sound.layout=layout;sound.bit_rate=192000
                resampler=av.AudioResampler(format='fltp',layout=layout,rate=encoding_rate)
        try:container.start_encoding()
        except av.FFmpegError as error:
            if not codec.endswith('_nvenc'):raise
            from .encoding_backend import HardwareEncoderUnavailable
            raise HardwareEncoderUnavailable('GPU video encoder initialization failed: '+str(error)) from error
        for index in range(int(count)):
            import comfy.model_management
            comfy.model_management.throw_exception_if_processing_interrupted()
            conversion_started=time.perf_counter()
            pixel=numpy(images[index])[...,:3]
            if np.issubdtype(pixel.dtype,np.floating):
                if not np.isfinite(pixel).all():raise ValueError('视频画面包含无效数值')
                pixel=(np.clip(pixel,0,1)*255).round().astype(np.uint8)
            pixel=np.ascontiguousarray(pixel,dtype=np.uint8)
            conversion_seconds+=time.perf_counter()-conversion_started
            frame=av.VideoFrame.from_ndarray(pixel,format='rgb24');frame.pts=index;frame.time_base=1/rate
            for packet in video.encode(frame):container.mux(packet)
        for packet in video.encode():container.mux(packet)
        if sound is not None:
            for offset in range(0,waveform.shape[1],1024):
                frame=av.AudioFrame.from_ndarray(np.ascontiguousarray(waveform[:,offset:offset+1024]),format='fltp',layout=layout)
                frame.sample_rate=sample_rate;frame.pts=offset;frame.time_base=Fraction(1,sample_rate)
                for converted in resampler.resample(frame):
                    for packet in sound.encode(converted):container.mux(packet)
            for converted in resampler.resample(None):
                for packet in sound.encode(converted):container.mux(packet)
            for packet in sound.encode():container.mux(packet)
    log.info('Star7 video encode completed | total=%.2fs pixel_conversion=%.2fs',time.perf_counter()-started,conversion_seconds)
