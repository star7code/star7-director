"""AV handoff on native H3 paths; no global monkey-patches."""
import copy
MODES=('previous_latent','motion_guide','motion_redraw')
CHOICES=(5,22,39,56)
def options(plan,shot):
    cfg={**plan.get('continuity_settings',{}),**shot.get('continuity',{})}
    return {'context_frames':cfg.get('context_frames',22),'audio':cfg.get('audio',True),'redraw':cfg.get('redraw',.65),'drift_control':cfg.get('drift_control',False),'drift_strength':cfg.get('drift_strength',.3)}
def source(plan,shot_id,prompt):
    from .runtime import data_root,run_fingerprint,latest_latent,output_matches
    from .storage import Storage
    from .core import compile_shot
    shot=compile_shot(plan,shot_id);sid=shot['continuity'].get('source_shot')
    if not sid:return None
    from .batch_runner import approved_reference
    selected=approved_reference(plan,shot_id,sid)
    store=Storage(data_root());record=selected or store.latest_output(plan['id'],sid)
    if record:
        from pathlib import Path
        import folder_paths
        path=Path(record['path']).resolve();root=Path(folder_paths.get_output_directory()).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('前一镜头的成品文件不可用：'+sid)
        if not selected and not output_matches(plan,sid,prompt,record):raise ValueError('前一镜头的成品与当前设置不匹配，请先生成：'+sid)
        return {'id':sid,'record':record,'path':path}
    # A valid base cache remains useful when export failed; never accept stale revisions.
    latent,_=latest_latent(plan['id'],sid,expected=run_fingerprint(plan,sid,prompt,stage='base'))
    return {'id':sid,'latent':latent}
def check_dependency(plan,shot_id,prompt):
    from .core import compile_shot
    shot=compile_shot(plan,shot_id)
    if shot['continuity']['mode']!='independent':
        info=source(plan,shot_id,prompt)
        if shot['continuity']['mode']=='tail_reference' and (not info or 'path' not in info):raise ValueError('尾帧画面参考需要前一镜头已生成的成品视频')
def export_tail(info,n,audio=True):
    import av,torch,numpy as np
    from pathlib import Path
    from collections import deque
    from .runtime import load_audio
    path=info['path'];frames=deque(maxlen=n)
    count=int(info['record']['frame_count']);start=max(0,(count-n)/24)
    with av.open(str(path)) as c:
        stream=c.streams.video[0];rate=float(stream.average_rate or 24)
        if abs(rate-24)>.05:raise ValueError('运动衔接目前需要24fps成品')
        if start:c.seek(int(start*av.time_base),backward=True)
        for frame in c.decode(stream):frames.append(torch.from_numpy(np.asarray(frame.to_image().convert('RGB')).copy()).float()/255)
        has_audio=bool(c.streams.audio)
    if len(frames)<n:raise ValueError('前一镜头不足 '+str(n)+' 帧，请降低上下文帧数或延长前一镜头')
    import folder_paths
    annotated=path.relative_to(Path(folder_paths.get_output_directory()).resolve()).as_posix()+' [output]'
    sound=load_audio(annotated,max(0,(count-max(24,n))/24),max(24,n)/24) if audio and has_audio else None
    return torch.stack(list(frames)),sound

def apply(plan,shot,positive,latent,video_vae,audio_vae,prompt):
    from .vendor.aimixer.h3_motion_context import apply_motion_context,CTX_AUDIO_END_KEY,CTX_FRAME_KEY,FPS,AUDIO_HZ
    from .vendor.aimixer.h3_latent_continue import apply_latent_continue
    info=source(plan,shot['id'],prompt);cfg=options(plan,shot)
    if shot['continuity']['mode'] in ('motion_guide','previous_latent'):
        from .handoff import apply_base
        out,result,head=apply_base(plan,shot,positive,latent,info,video_vae,audio_vae,cfg)
        native=[]
        for embedding,metadata in out:
            meta=dict(metadata);refs=[]
            keyframes=[{**kf,'resolved_frame_index':int(kf[CTX_FRAME_KEY])} if CTX_FRAME_KEY in kf else dict(kf) for kf in meta.get('minimax_keyframes',[])]
            for ref in meta.get('minimax_refs',[]):
                if CTX_AUDIO_END_KEY not in ref:refs.append(ref);continue
                ticks=int(ref.get('ref_audio_t',0));start=round(float(ref[CTX_AUDIO_END_KEY])-ticks/AUDIO_HZ*FPS)
                keyframes.append({'resolved_frame_index':start,'audio_latent':ref['audio_latent']})
            meta['minimax_refs']=refs;meta['minimax_keyframes']=keyframes;native.append([embedding,meta])
        return native,result,head
    prev=info.get('latent');pixels=sound=None
    if 'path' in info:pixels,sound=export_tail(info,cfg['context_frames'],cfg['audio'])
    mode=shot['continuity']['mode']
    if mode=='motion_redraw':
        out,head,gap=apply_latent_continue(latent,prev_av=prev,prev_tail=pixels,vae=video_vae,context_length=cfg['context_frames'],pin_audio=cfg['audio'],context_audio=sound,audio_vae=audio_vae,audio_context_length=cfg['context_frames'],seam_min_mask=cfg['redraw'])
        if gap:raise ValueError('基础缓存尾部需要相位裁剪，请先导出前一镜头后再衔接')
        return positive,out,head
    transform=None
    if cfg['drift_control']:
        from .context_drift import taper_guides
        transform=lambda blocks:taper_guides(blocks,cfg['drift_strength'],shot.get('seed',0))
    out,head,gap=apply_motion_context(positive,latent,vae=video_vae,context_length=cfg['context_frames'],context_latent=prev,context_frames=pixels,context_audio=sound,audio_vae=audio_vae,continue_audio=cfg['audio'],audio_context_length=cfg['context_frames'],keep_existing_keyframes=True,context_transform=transform)
    if gap:raise ValueError('基础缓存尾部需要相位裁剪，请先导出前一镜头后再衔接')
    # Native H3 can pin AV keyframes directly. Move context audio from refs into
    # a time-aligned keyframe so no global PackedLayout timeline patch is needed.
    native=[]
    for embedding,metadata in out:
        meta=dict(metadata);refs=[];keyframes=[{**kf,'resolved_frame_index':int(kf[CTX_FRAME_KEY])} if CTX_FRAME_KEY in kf else dict(kf) for kf in meta.get('minimax_keyframes',[])]
        for ref in meta.get('minimax_refs',[]):
            if CTX_AUDIO_END_KEY not in ref:refs.append(ref);continue
            ticks=int(ref.get('ref_audio_t',0));start=round(float(ref[CTX_AUDIO_END_KEY])-ticks/AUDIO_HZ*FPS)
            keyframes.append({'resolved_frame_index':start,'audio_latent':ref['audio_latent']})
        meta['minimax_refs']=refs;meta['minimax_keyframes']=keyframes;native.append([embedding,meta])
    return native,latent,head
