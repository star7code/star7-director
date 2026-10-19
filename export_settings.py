"""Validated export-only encoding; generated clips and caches stay unchanged."""
import json,math,os,shutil,subprocess,uuid
from pathlib import Path

DEFAULTS={'format':'h264-mp4','encoder':'auto','frame_rate':0,'quality_mode':'crf','crf':19,'bitrate_mbps':8,'pix_fmt':'yuv420p','preset':'medium','include_audio':True,'audio_bitrate_kbps':192,'save_metadata':False}
FORMATS={'h264-mp4':('mp4','libx264','video/h264-mp4'),'h265-mp4':('mp4','libx265','video/h265-mp4'),'vp9-webm':('webm','libvpx-vp9','video/webm')}

def settings(plan):
    raw=plan.get('export_settings',{})
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('导出设置无效')
    result={**DEFAULTS,**raw}
    for field,choices in {'format':FORMATS,'encoder':('auto','gpu','cpu'),'quality_mode':('crf','bitrate'),'pix_fmt':('yuv420p','yuv444p'),'preset':('fast','medium','slow')}.items():
        if result[field] not in choices:raise ValueError('不支持的导出设置：'+field)
    for field,low,high in (('frame_rate',0,120),('crf',0,51),('bitrate_mbps',.1,200),('audio_bitrate_kbps',32,320)):
        value=result[field]
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('导出参数超出范围：'+field)
    for field in ('include_audio','save_metadata'):
        if not isinstance(result[field],bool):raise ValueError('导出开关无效：'+field)
    for field in ('crf','audio_bitrate_kbps'):
        if result[field]!=int(result[field]):raise ValueError('导出参数必须为整数：'+field)
    return result

def extension(plan):return FORMATS[settings(plan)['format']][0]
def mime(plan):return FORMATS[settings(plan)['format']][2]
def needs_encoding(plan):return settings(plan)!=DEFAULTS

def arguments(plan,force_cpu=False):
    from .encoding_backend import choose_encoder,nvenc_options
    s=settings(plan);codec=choose_encoder(s['format'],'cpu' if force_cpu else s['encoder'],s['pix_fmt'],'ffmpeg',s['crf'] if s['quality_mode']=='crf' else 19)
    args=['-map','0:v:0','-c:v',codec,'-pix_fmt',s['pix_fmt']]
    if s['frame_rate']:args+=['-vf','fps='+str(s['frame_rate'])]
    if codec.endswith('_nvenc'):
        options=nvenc_options(s['crf'],s['preset'],int(s['bitrate_mbps']*1000000) if s['quality_mode']=='bitrate' else None)
        for name,value in options.items():args+=['-b:v' if name=='b' else '-'+name,value]
    elif codec=='libvpx-vp9':args+=['-deadline','good','-cpu-used',{'fast':'4','medium':'2','slow':'0'}[s['preset']]]
    else:args+=['-preset',s['preset']]
    if not codec.endswith('_nvenc') and s['quality_mode']=='crf':
        args+=['-crf',str(int(s['crf']))]
        if codec=='libvpx-vp9':args+=['-b:v','0']
    elif not codec.endswith('_nvenc'):args+=['-b:v',str(int(s['bitrate_mbps']*1000000))]
    if s['include_audio']:args+=['-map','0:a:0?','-c:a','libopus' if codec=='libvpx-vp9' else 'aac','-b:a',str(int(s['audio_bitrate_kbps']*1000))]
    else:args+=['-an']
    args+=['-map_metadata','-1']
    if s['save_metadata']:args+=['-metadata','comment='+json.dumps({'project':plan.get('title',plan['id']),'shots':[{k:v for k,v in shot.items() if k in ('id','name','seed','duration','prompt')} for shot in plan.get('shots',[])],'export_settings':s},ensure_ascii=False)]
    if extension(plan)=='mp4':args+=['-movflags','+faststart']
    if codec in ('libx265','hevc_nvenc'):args+=['-tag:v','hvc1']
    return args

def run(input_args,target,plan,copy=False,codec_args=None):
    import imageio_ffmpeg,comfy.model_management
    from .encoding_backend import LOG
    target=Path(target);log=target.with_suffix(target.suffix+'.encode.log')
    options=list(codec_args) if codec_args is not None else ['-c','copy','-movflags','+faststart'] if copy else arguments(plan)
    hardware=any(value in ('h264_nvenc','hevc_nvenc') for value in options)
    fallback=None
    if hardware and settings(plan)['encoder']=='auto':
        baseline=arguments(plan)
        if codec_args is None:fallback=arguments(plan,force_cpu=True)
        elif options[:len(baseline)]==baseline:fallback=arguments(plan,force_cpu=True)+options[len(baseline):]
    try:
        for attempt in range(2):
            with log.open('wb') as errors:
                command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-v','error','-nostdin','-y',*input_args,*options]
                # Preserve the bundled Windows x265 tiny-frame safety fix.
                if os.name=='nt' and '-c:v' in command and command[command.index('-c:v')+1]=='libx265' and '-i' in input_args:
                    source=Path(input_args[input_args.index('-i')+1])
                    if source.is_file():
                        import av
                        try:
                            with av.open(str(source)) as container:
                                stream=container.streams.video[0]
                                if min(stream.width,stream.height)<64:command+=['-x265-params','asm=0']
                        except (av.FFmpegError,IndexError):pass
                codec=options[options.index('-c:v')+1] if '-c:v' in options else 'copy'
                LOG.info('Star7 video export | codec=%s attempt=%d',codec,attempt+1)
                with subprocess.Popen([*command,str(target)],stdout=subprocess.DEVNULL,stderr=errors,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                    try:
                        while True:
                            comfy.model_management.throw_exception_if_processing_interrupted()
                            try:code=process.wait(timeout=.2);break
                            except subprocess.TimeoutExpired:pass
                    except BaseException:process.terminate();process.wait();raise
            if not code:return
            detail=log.read_text(encoding='utf-8',errors='replace')[-1500:]
            initialization_failure='nvenc' in detail.lower() and any(word in detail.lower() for word in ('cannot','failed','unsupported','not supported','no capable','opening encoder','requires'))
            if attempt==0 and fallback is not None and initialization_failure:
                LOG.warning('Star7 video export | hardware initialization failed; retrying with CPU')
                options=fallback;continue
            raise ValueError('导出编码失败（退出码 '+str(code)+'）：'+detail)
    finally:log.unlink(missing_ok=True)

def export_clip(source,target,plan):
    if not needs_encoding(plan):shutil.copyfile(source,target)
    else:
        target=Path(target);temporary=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.tmp'+target.suffix)
        try:run(['-i',str(source)],temporary,plan);temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
