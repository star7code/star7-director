"""Lossless, output-version-bound motion handoffs; no compressed video reads."""
import copy
import math
from .run_logging import event

KEY='star7_motion_handoff'
EXPORT='star7_export_timeline'

def check_request(plan,shot_id,prompt,*,processing=False,store=None):
    """Fail before sampling/upscaling if a legacy handoff must be rebuilt."""
    from .core import compile_shot
    from .runtime import Storage,data_root,Star7DirectorBaseCache,current_shot
    from .continuity import options
    from .vendor.aimixer.h3_motion_context import pixel_frames_for_latent_t
    shot=compile_shot(plan,shot_id)
    if shot['continuity']['mode'] not in ('motion_guide','previous_latent'):return
    post=next(s for s in plan['shots'] if s['id']==shot_id).get('post',{})
    store=store if store is not None else Storage(data_root());sid=shot['continuity']['source_shot'];record=store.latest_output(plan['id'],sid)
    if not record:raise ValueError('前段 '+sid+' 没有可用成品，请先生成前段')
    def info(stage,version):
        try:
            if not version:raise ValueError('Missing version')
            return store.latent_info(plan['id'],sid,stage,version)
        except (ValueError,OSError,KeyError) as error:
            raise ValueError('前段 '+sid+' 缺少'+('二采无损衔接缓存，请先对前段执行“仅二采／修脸当前”' if stage=='final' else '一采潜空间缓存，请先重新生成前段')+'；本次尚未开始采样或二采，不会改用压缩视频参考') from error
    base=info('base',record.get('base_version'))
    final=None
    if post.get('hd'):
        final=info('final',record.get('handoff_version'))
    elif record.get('handoff_version'):
        final=info('final',record['handoff_version'])
    timeline=(final or base).get(EXPORT,{})
    head=int(timeline.get('trim_frames',current_shot(plan,sid)[2]))
    window(pixel_frames_for_latent_t(base['samples'][0]['shape'][2]),head,record['frame_count'],options(plan,shot)['context_frames'])
    if processing and post.get('hd'):
        row,_=Star7DirectorBaseCache().find_for_process(plan,shot_id,prompt)
        if not row:raise ValueError('当前镜头缺少一采缓存，请先“仅重新生成当前”')
        cached=store.latent_info(plan['id'],shot_id,'base',row['version']);guide=cached.get(KEY)
        if not guide:raise ValueError('当前镜头仍是旧运动引导缓存，请先“仅重新生成当前”建立无损衔接数据；本次尚未开始二采')
        if guide['source_base_version']!=record.get('base_version'):raise ValueError('前段一采版本已改变，请重新生成当前镜头后再二采')
        if guide.get('source_final_version') and guide['source_final_version']!=record.get('handoff_version'):raise ValueError('前段二采版本已改变，请重新生成当前镜头后再二采')


def window(total_frames,export_head,export_frames,context_frames):
    """A complete latent window may extend past the exact visible join.

    Previously unshown source frames become the next clip's opening. No old
    frames are replayed/discarded and the requested delivery duration is kept.
    """
    end=int(export_head)+int(export_frames)
    if export_frames<context_frames or end>total_frames:
        raise ValueError('Lossless motion handoff has insufficient source frames')
    # Native H3 decodes 17-frame chunks from seven latent tokens (22-frame
    # coverage). Pin that decoder chunk in full, including its lookahead.
    guide_end=22+17*(end//17)
    overshoot=guide_end-end
    minimum=max(22,int(context_frames))
    length=int(context_frames)+17*max(0,math.ceil((minimum+overshoot-int(context_frames))/17))
    if guide_end>total_frames or guide_end<length:
        raise ValueError('Lossless motion handoff cannot align the source timeline')
    return {'guide_frames':length,'guide_end':guide_end,'trim_frames':length-overshoot,
            'source_end':end,'overshoot':overshoot}


def load_source(plan,info,*,final=False):
    from .runtime import data_root
    from .storage import Storage
    record=info.get('record',{});sid=info['id']
    version=record.get('handoff_version' if final else 'base_version')
    if not version:
        action='仅二采／修脸当前' if final else '仅重新生成当前'
        raise ValueError(f'前段 {sid} 缺少无损衔接缓存，请对前段执行“{action}”；不会改用压缩视频参考')
    try:return Storage(data_root()).load_latent(plan['id'],sid,'final' if final else 'base',version)
    except (ValueError,OSError) as error:
        raise ValueError(f'前段 {sid} 的无损衔接缓存已清理或不可用，请重建前段缓存；不会改用压缩视频参考') from error


def apply_base(plan,shot,positive,latent,info,video_vae,audio_vae,options):
    from .vendor.aimixer.h3_motion_context import apply_motion_context,video_from_latent,pixel_frames_for_latent_t
    from .runtime import current_shot
    previous=load_source(plan,info);src=video_from_latent(previous);dst=video_from_latent(latent)
    if next(s for s in plan['shots'] if s['id']==shot['id']).get('post',{}).get('hd') and (info['record'].get('post') or {}).get('hd'):
        load_source(plan,info,final=True)
    if tuple(src.shape[1:2])+tuple(src.shape[3:])!=tuple(dst.shape[1:2])+tuple(dst.shape[3:]):
        raise ValueError('运动引导前后的一采分辨率不一致，无法无损衔接；请统一基础生成尺寸')
    timeline=previous.get(EXPORT,{})
    source_head=int(timeline.get('trim_frames',current_shot(plan,info['id'])[2]))
    if info['record'].get('handoff_version'):
        saved=load_source(plan,info,final=True).get(EXPORT)
        if saved:source_head=int(saved['trim_frames'])
    layout=window(pixel_frames_for_latent_t(src.shape[2]),source_head,info['record']['frame_count'],options['context_frames'])
    transform=None
    if options['drift_control']:
        from .context_drift import taper_guides
        transform=lambda blocks:taper_guides(blocks,options['drift_strength'],shot.get('seed',0))
    out,_,gap=apply_motion_context(positive,latent,vae=video_vae,
        context_length=layout['guide_frames'],exact_context_length=True,context_latent=previous,
        context_end_frame=layout['guide_end'],audio_vae=audio_vae,continue_audio=options['audio'],
        audio_context_length=layout['guide_frames'],context_transform=transform)
    if gap:raise ValueError('Lossless motion handoff unexpectedly moved the source join')
    result=dict(latent)
    result[KEY]={**layout,'source_shot':info['id'],'source_base_version':info['record']['base_version'],'source_final_version':info['record'].get('handoff_version')}
    result[EXPORT]={'trim_frames':layout['trim_frames']}
    event('motion_handoff_base',project=plan['id'],shot=shot['id'],source=info['id'],route='raw_latent',**layout)
    return out,result,layout['trim_frames']


def prepare_refinement(latent,positive,plan,shot_id,prompt):
    """Protect the previous HD latent prefix from both upscale drift and noise."""
    import torch
    from comfy.nested_tensor import NestedTensor
    from .continuity import source
    from .vendor.aimixer.h3_motion_context import _video_tail_blocks,CTX_FRAME_KEY
    guide=latent.get(KEY)
    if not guide:
        from .core import compile_shot
        if compile_shot(plan,shot_id)['continuity']['mode'] in ('motion_guide','previous_latent'):
            raise ValueError('当前一采仍是旧运动引导缓存，请“仅重新生成当前”建立无损衔接数据；不能把旧视频参考冒充潜空间衔接')
        return latent,positive
    info=source(plan,shot_id,prompt)
    if info['record'].get('base_version')!=guide['source_base_version']:
        raise ValueError('运动引导来源的一采版本已改变，请重新生成当前镜头；不能混用不同版本的衔接缓存')
    if guide.get('source_final_version') and guide['source_final_version']!=info['record'].get('handoff_version'):
        raise ValueError('运动引导来源的二采版本已改变，请重新生成当前镜头；不能混用不同版本的衔接缓存')
    previous=load_source(plan,info,final=True)
    parts=list(latent['samples'].unbind());source_video=previous['samples'].unbind()[0]
    if tuple(source_video.shape[1:2])+tuple(source_video.shape[3:])!=tuple(parts[0].shape[1:2])+tuple(parts[0].shape[3:]):
        raise ValueError('运动引导前后二采分辨率不一致，无法锁定无损参考头；请统一二采目标尺寸')
    blocks,offsets,_,_,gap=_video_tail_blocks(previous,guide['guide_frames'],end_frame=guide['guide_end'])
    if gap:raise ValueError('HD motion handoff has an invalid temporal phase')
    prefix=torch.cat(blocks,dim=2).to(device=parts[0].device,dtype=parts[0].dtype)
    video=parts[0].clone();video[:,:,:prefix.shape[2]]=prefix
    result=dict(latent);result['samples']=NestedTensor((video,parts[1]))
    old=result.get('noise_mask')
    mask=list(old.unbind())[0].clone() if old is not None else torch.ones_like(video)
    mask[:,:,:prefix.shape[2]]=0
    result['noise_mask']=NestedTensor((mask,torch.zeros_like(parts[1])))
    out=[]
    for embedding,metadata in positive:
        meta=dict(metadata)
        keep=[dict(k) for k in meta.get('minimax_keyframes',[]) if not (CTX_FRAME_KEY in k and 'latent' in k)]
        meta['minimax_keyframes']=keep+[{'resolved_frame_index':int(p),CTX_FRAME_KEY:int(p),'latent':b.to(video)} for p,b in zip(offsets,blocks)]
        out.append([embedding,meta])
    event('motion_handoff_hd',project=plan['id'],shot=shot_id,source=info['id'],route='raw_final_latent',pinned_tokens=prefix.shape[2])
    return result,out


def restore_prefix(sampled,protected):
    from comfy.nested_tensor import NestedTensor
    from .vendor.aimixer.h3_motion_context import steps_for_frames
    guide=protected.get(KEY)
    if not guide:return sampled
    n=steps_for_frames(guide['guide_frames']);members=list(sampled['samples'].unbind())
    video=members[0].clone();video[:,:,:n]=protected['samples'].unbind()[0][:,:,:n].to(video)
    result=dict(sampled);result['samples']=NestedTensor((video,members[1]))
    result[KEY]=copy.deepcopy(guide);result[EXPORT]=copy.deepcopy(protected[EXPORT])
    return result
