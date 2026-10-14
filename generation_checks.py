"""Check the same plan that will be submitted, without sampling or queueing."""
import copy,json,uuid
from pathlib import Path
from .core import compile_plan,preflight
from .runtime import data_root,output_matches,parameter_matches
from .storage import Storage

def inactive_references(plan,compiled):
    """Report disabled references without turning them into validation errors."""
    from .references import MENTION,mention_name,TAIL_REFERENCE_ID,SELECTED_REFERENCE_ID
    by_id={a['id']:a for a in plan['assets']};warnings=[]
    for result in compiled:
        shot=next(s for s in plan['shots'] if s['id']==result['id']);smart=shot.get('input_mode','reference')=='keyframes';names=[]
        if smart:
            for aid in result['labels']:
                card=by_id[aid]
                if any(m['type'] in ('image','video') for m in card.get('media',[])):names.append(card['name'])
        for text in (shot['prompt'],result['prompt']):
            for match in MENTION.finditer(text):
                token=mention_name(match);name=None
                if token==TAIL_REFERENCE_ID:
                    if smart:
                        if match[1]!='尾帧':name='尾帧参考'
                        elif not shot.get('keyframes',{}).get('last'):name='尾帧'
                    elif shot.get('continuity',{}).get('mode')!='tail_reference':name='尾帧参考'
                elif token==SELECTED_REFERENCE_ID and (smart or shot.get('continuity',{}).get('mode')!='selected_frame'):name='参考帧'
                elif token=='__star7_first_frame__' and not (smart and shot.get('keyframes',{}).get('first')):name='首帧'
                elif token=='__star7_last_frame__' and not (smart and shot.get('keyframes',{}).get('last')):name='尾帧'
                if name:names.append(name)
        names=list(dict.fromkeys(names))
        if names:warnings.append({'shot_id':shot['id'],'references':names,'message':shot['id']+'：'+ '、'.join(names)+' 在当前模式下无效'})
    return warnings

async def validate_generation(plan,prepared,scope='all',shot_id=None):
    import folder_paths,execution
    compiled=compile_plan(plan);prompt=prepared['output'];store=Storage(data_root())
    errors=preflight(plan,folder_paths.get_input_directory())
    if errors:raise ValueError(errors[0]['shot']+'：素材不可用 '+errors[0]['source'])
    if not compiled:raise ValueError('没有可生成的镜头')
    frames={};selected=[s for s in compiled if scope=='all' or scope=='selected' and s['id'] in shot_id or scope not in ('all','selected') and s['id']==shot_id]
    root=Path(folder_paths.get_output_directory()).resolve()
    for shot in compiled:
        record=store.latest_output(plan['id'],shot['id'])
        usable=bool(record and Path(record['path']).resolve().is_relative_to(root) and Path(record['path']).is_file())
        will_generate=(scope=='all' and (not usable or not parameter_matches(plan,shot['id'],prompt,record)) or scope=='selected' and shot['id'] in shot_id)
        frames[shot['id']]=max(1,round(shot['duration']*24)) if will_generate else record['frame_count'] if usable else None
    from .continuity import MODES,options
    for shot in selected:
        cfg=shot['continuity'];mode=cfg['mode']
        from .core import dependency_source
        deferred=shot.get('keyframes',{}).get('first',{}).get('from_previous')
        if deferred and frames.get(dependency_source(plan,shot['id'])) is None:raise ValueError(shot['id']+'：上段没有视频，也没有计划在此前生成，无法取得首帧')
        if mode=='independent':continue
        count=frames.get(cfg.get('source_shot'))
        if count is None:raise ValueError(shot['id']+'：前段没有可用视频 '+cfg.get('source_shot',''))
        if mode=='selected_frame' and cfg['frame']>=count:raise ValueError(shot['id']+'：参考帧 '+str(cfg['frame'])+' 超出前段范围 0–'+str(count-1))
        if mode in MODES and count<options(plan,shot)['context_frames']:raise ValueError(shot['id']+'：前段长度不足所选上下文帧数，请降低上下文或增加前段秒数')
    # Validate each distinct post-processing branch before spending GPU time.
    # Future predecessors may not exist yet; their planned lengths were checked above.
    from .desk import internal_graph,validate_execution_plan
    desks=[(nid,v) for nid,v in prompt.items() if v['class_type']=='Star7DirectorDesk']
    branches=set()
    for shot in selected:
        original=next(s for s in plan['shots'] if s['id']==shot['id']);post=original.get('post',{})
        branch=(bool(post.get('hd')),bool(post.get('face')),post.get('face_count'))
        if branch in branches:continue
        branches.add(branch)
        for nid,spec in desks:
            missing=[k for k in ('model','clip','video_vae','audio_vae') if k not in spec['inputs']]
            if missing:raise ValueError('工作站缺少生成输入：'+', '.join(missing))
            ports={k:spec['inputs'][k] for k in ('model','clip','video_vae','audio_vae')}
            graph,result=internal_graph(plan,shot['id'],ports,nid+'.validation.')
            validate_execution_plan(graph)
        valid=await execution.validate_prompt(str(uuid.uuid4()),copy.deepcopy(prompt),None)
        if not valid[0]:raise ValueError(shot['id']+'：节点或模型配置不通过 '+json.dumps(valid[1],ensure_ascii=False))
    warnings=inactive_references(plan,selected)
    message=str(len(selected))+' 个镜头通过生成预检：衔接帧范围、节点与模型配置正常。'
    if warnings:
        message+=' 有引用在当前模式下无效，仍可生成。'+'；'.join(w['message'] for w in warnings[:3])
        if len(warnings)>3:message+='；另有 '+str(len(warnings)-3)+' 个镜头存在无效引用。'
    else:message=str(len(selected))+' 个镜头通过生成预检：素材引用、衔接帧范围、节点与模型配置正常。'
    return {'valid':True,'count':len(selected),'warnings':warnings,'message':message}
