"""Preserve compatible video; normalize mismatched audio for film assembly."""
import uuid
from pathlib import Path
from .core import identifier
from .runtime import data_root,output_matches
from .storage import Storage

def profile(path):
    import av
    with av.open(str(path)) as f:
        video=f.streams.video[0] if f.streams.video else None
        if video is None:raise ValueError('镜头文件没有视频流')
        audio=f.streams.audio[0] if f.streams.audio else None
        return (video.codec_context.name,video.width,video.height,str(video.average_rate),video.codec_context.format.name,audio.codec_context.name if audio else None,audio.codec_context.sample_rate if audio else None,len(audio.codec_context.layout.channels) if audio else None)

def video_duration(path):
    import av
    with av.open(str(path)) as container:
        video=container.streams.video[0]
        if video.duration is not None:return float(video.duration*video.time_base)
        if video.frames and video.average_rate:return float(video.frames/video.average_rate)
        raise ValueError('无法读取镜头视频时长，已保留原视频')

def normalize_audio(paths,profiles,directory,plan):
    from .export_settings import run,settings
    options=settings(plan);normalized=[]
    for index,(path,description) in enumerate(zip(paths,profiles)):
        duration=video_duration(path);target=directory/('audio-'+str(index)+'.mov')
        inputs=['-i',str(path)];args=['-map','0:v:0','-c:v','copy']
        if options['include_audio'] and any(p[5] is not None for p in profiles):
            if description[5] is None:
                inputs+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo'];args+=['-map','1:a:0']
            else:args+=['-map','0:a:0']
            # Intermediate PCM avoids an AAC delay/padding block per segment.
            args+=['-c:a','pcm_f32le','-ar','48000','-ac','2','-af','aresample=48000:async=1:first_pts=0,apad']
        else:args+=['-an']
        args+=['-t',str(duration),'-movflags','+faststart']
        run(inputs,target,plan,codec_args=args);normalized.append(target)
    return normalized

def select_clips(plan,output_root):
    store=Storage(data_root());clips=[];missing=[];unavailable=[]
    project=identifier(plan['id']);shots=plan.get('shots',[])
    if not isinstance(shots,list):raise ValueError('镜头列表无效')
    ids=[identifier(s['id']) for s in shots]
    if len(ids)!=len(set(ids)):raise ValueError('镜头ID重复')
    for shot in shots:
        record=store.latest_output(plan['id'],shot['id'])
        if record is None:missing.append(shot['id']);continue
        path=Path(record['path']).resolve()
        if not path.is_relative_to(Path(output_root).resolve()):raise ValueError('镜头文件路径无效：'+shot['id'])
        if not path.is_file():unavailable.append(shot['id']);continue
        clips.append({'id':shot['id'],'name':shot.get('name') or shot['id'],'path':path,'frames':record['frame_count']})
    return {'clips':clips,'missing_shots':missing,'unavailable_shots':unavailable,'total':len(shots)}

def assembly_message(selection,stale=(),preview=False):
    message=('当前预览' if preview else '已合并导出')+' '+str(len(selection['clips']))+'/'+str(selection['total'])+' 个镜头的最近生成视频。'
    if selection['missing_shots']:message+=' 有 '+str(len(selection['missing_shots']))+' 个镜头尚未生成，本次只包含已生成内容。'
    if selection['unavailable_shots']:message+=' '+str(len(selection['unavailable_shots']))+' 个镜头的文件不可用，已跳过。'
    if stale:message+=' '+str(len(stale))+' 个镜头参数已修改但未更新生成，本次使用最近生成的视频。'
    if selection.get('audio_normalized'):message+=' 不同音频规格已统一为 48 kHz 双声道，缺少音轨的片段已补静音。'
    return message

def combine(plan,pipeline,output_root,selection=None):
    from .export_settings import extension,needs_encoding,run,settings,arguments
    suffix=extension(plan)
    store=Storage(data_root());selection=selection or select_clips(plan,output_root);paths=[c['path'] for c in selection['clips']]
    if not paths:raise ValueError('没有可合并镜头')
    profiles=[profile(p) for p in paths];first=profiles[0]
    durations=[video_duration(p) for p in paths]
    if any(p[:5]!=first[:5] for p in profiles[1:]):raise ValueError('镜头视频分辨率、帧率或编码不一致，请先统一画面设置；原有镜头已保留')
    audio_mismatch=any(p[5:]!=first[5:] for p in profiles[1:])
    from .output_paths import reserve_export_directory
    directory=reserve_export_directory(output_root,plan.get('title') or plan['id'],'合并导出')
    token=uuid.uuid4().hex[:12];listing=data_root()/('concat_'+token+'.txt');target=directory/('final-film-'+token+'.'+suffix);temp=target.with_name(target.stem+'.tmp.'+suffix);completed=False;parts=None
    try:
        if audio_mismatch:
            parts=directory/'.audio-normalization';parts.mkdir();paths=normalize_audio(paths,profiles,parts,plan)
        listing.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n"+'duration '+str(duration)+'\n' for p,duration in zip(paths,durations)),encoding='utf-8')
        audio_args=None
        if audio_mismatch:
            config=settings(plan)
            audio_args=arguments(plan) if needs_encoding(plan) else ['-map','0:v:0','-c:v','copy','-map','0:a:0?','-c:a','aac','-ar','48000','-ac','2','-b:a',str(int(config['audio_bitrate_kbps']*1000)),'-movflags','+faststart']
            if config['include_audio']:audio_args+=['-af','aresample=48000:async=1:first_pts=0,atrim=duration='+str(sum(durations))]
            audio_args+=['-t',str(sum(durations))]
        run(['-f','concat','-safe','0','-i',str(listing)],temp,plan,copy=not needs_encoding(plan),codec_args=audio_args)
        temp.replace(target)
        completed=True;store.record_film(plan['id'],target);selection['audio_normalized']=audio_mismatch
        return target
    finally:
        listing.unlink(missing_ok=True);temp.unlink(missing_ok=True)
        if parts is not None:
            # Only this call's freshly-created export subdirectory is cleaned.
            import shutil
            if parts.exists() and parts.resolve().is_relative_to(directory.resolve()) and parts.name=='.audio-normalization':shutil.rmtree(parts)
        if not completed:target.unlink(missing_ok=True);directory.rmdir()

def outdated_shots(plan,pipeline):
    store=Storage(data_root());result=[]
    for shot in plan['shots']:
        record=store.latest_output(plan['id'],shot['id'])
        if not record:continue
        try:matches=output_matches(plan,shot['id'],pipeline,record)
        except (ValueError,TypeError,KeyError,OSError):matches=False
        if not matches:result.append(shot['id'])
    return result
