"""Fast film assembly only when clip formats match; no hidden transcoding."""
import subprocess,uuid
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
        return (video.codec_context.name,video.width,video.height,str(video.average_rate),str(video.codec_context.format),audio.codec_context.name if audio else None,audio.codec_context.sample_rate if audio else None,len(audio.codec_context.layout.channels) if audio else None)

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
    return message

def combine(plan,pipeline,output_root,selection=None):
    from .export_settings import extension,needs_encoding,run
    suffix=extension(plan)
    store=Storage(data_root());selection=selection or select_clips(plan,output_root);paths=[c['path'] for c in selection['clips']]
    if not paths:raise ValueError('没有可合并镜头')
    first=profile(paths[0])
    if any(profile(p)!=first for p in paths[1:]):raise ValueError('镜头分辨率或编码不一致，请先统一输出设置；原有镜头已保留')
    from .output_paths import reserve_export_directory
    directory=reserve_export_directory(output_root,plan.get('title') or plan['id'],'合并导出')
    token=uuid.uuid4().hex[:12];listing=data_root()/('concat_'+token+'.txt');target=directory/('final-film-'+token+'.'+suffix);temp=target.with_name(target.stem+'.tmp.'+suffix);completed=False
    try:
        listing.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n" for p in paths),encoding='utf-8')
        run(['-f','concat','-safe','0','-i',str(listing)],temp,plan,copy=not needs_encoding(plan))
        temp.replace(target)
        completed=True;store.record_film(plan['id'],target)
        return target
    finally:
        listing.unlink(missing_ok=True);temp.unlink(missing_ok=True)
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
