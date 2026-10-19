"""Validated export-only encoding; generated clips and caches stay unchanged."""
import json,math,os,shutil,subprocess,uuid
from pathlib import Path

DEFAULTS={'format':'h264-mp4','frame_rate':0,'quality_mode':'crf','crf':19,'bitrate_mbps':8,'pix_fmt':'yuv420p','preset':'medium','include_audio':True,'audio_bitrate_kbps':192,'save_metadata':False}
FORMATS={'h264-mp4':('mp4','libx264','video/h264-mp4'),'h265-mp4':('mp4','libx265','video/h265-mp4'),'vp9-webm':('webm','libvpx-vp9','video/webm')}

def settings(plan):
    raw=plan.get('export_settings',{})
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('导出设置无效')
    result={**DEFAULTS,**raw}
    for field,choices in {'format':FORMATS,'quality_mode':('crf','bitrate'),'pix_fmt':('yuv420p','yuv444p'),'preset':('fast','medium','slow')}.items():
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

def arguments(plan):
    s=settings(plan);codec=FORMATS[s['format']][1];args=['-map','0:v:0','-c:v',codec,'-pix_fmt',s['pix_fmt']]
    if s['frame_rate']:args+=['-vf','fps='+str(s['frame_rate'])]
    if codec=='libvpx-vp9':args+=['-deadline','good','-cpu-used',{'fast':'4','medium':'2','slow':'0'}[s['preset']]]
    else:args+=['-preset',s['preset']]
    if s['quality_mode']=='crf':
        args+=['-crf',str(int(s['crf']))]
        if codec=='libvpx-vp9':args+=['-b:v','0']
    else:args+=['-b:v',str(int(s['bitrate_mbps']*1000000))]
    if s['include_audio']:args+=['-map','0:a:0?','-c:a','libopus' if codec=='libvpx-vp9' else 'aac','-b:a',str(int(s['audio_bitrate_kbps']*1000))]
    else:args+=['-an']
    args+=['-map_metadata','-1']
    if s['save_metadata']:args+=['-metadata','comment='+json.dumps({'project':plan.get('title',plan['id']),'shots':[{k:v for k,v in shot.items() if k in ('id','name','seed','duration','prompt')} for shot in plan.get('shots',[])],'export_settings':s},ensure_ascii=False)]
    if extension(plan)=='mp4':args+=['-movflags','+faststart']
    if codec=='libx265':args+=['-tag:v','hvc1']
    return args

def run(input_args,target,plan,copy=False,codec_args=None):
    import imageio_ffmpeg,comfy.model_management
    target=Path(target);log=target.with_suffix(target.suffix+'.encode.log')
    try:
        with log.open('wb') as errors:
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-v','error','-nostdin',*input_args]
            command+=codec_args if codec_args is not None else ['-c','copy','-movflags','+faststart'] if copy else arguments(plan)
            # The bundled Windows x265 can corrupt the heap with SIMD on a canvas
            # smaller than 64px. Disable its assembly path only for these tiny
            # HEVC file inputs; keep dimensions, quality and normal exports intact.
            if os.name=='nt' and '-c:v' in command and command[command.index('-c:v')+1]=='libx265' and '-i' in input_args:
                source=Path(input_args[input_args.index('-i')+1])
                if source.is_file():
                    import av
                    try:
                        with av.open(str(source)) as container:
                            stream=container.streams.video[0]
                            if min(stream.width,stream.height)<64:command+=['-x265-params','asm=0']
                    except (av.FFmpegError,IndexError):pass  # Let FFmpeg report invalid inputs.
            with subprocess.Popen([*command,str(target)],stdout=subprocess.DEVNULL,stderr=errors,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                try:
                    while True:
                        comfy.model_management.throw_exception_if_processing_interrupted()
                        try:code=process.wait(timeout=.2);break
                        except subprocess.TimeoutExpired:pass
                except BaseException:process.terminate();process.wait();raise
        if code:raise ValueError('导出编码失败（退出码 '+str(code)+'）：'+log.read_text(encoding='utf-8',errors='replace')[-1500:])
    finally:log.unlink(missing_ok=True)

def export_clip(source,target,plan):
    if not needs_encoding(plan):shutil.copyfile(source,target)
    else:
        target=Path(target);temporary=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.tmp'+target.suffix)
        try:run(['-i',str(source)],temporary,plan);temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
