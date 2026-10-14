"""Explainable shot edits, deliberately separate from execution/cache hashes."""
import json,copy
from pathlib import Path
from .core import _compile_shot,dependency_source

PREFIX='v4:'

def snapshot(plan,sid):
    from .runtime import generation_identity
    value=_compile_shot(generation_identity(plan),sid,parameter_payload=True)
    post=value['shot'].get('post',{})
    value={k:value[k] for k in ('shot','assets','first_from_previous') if k in value}
    value['generation']={'395':{'face_count':plan.get('generation',{}).get('395',{}).get('face_count',1)}} if post.get('face') else {}
    # Saved v4 snapshots remain readable through the explicit projection below.
    # File stat revisions belong exclusively to execution/cache fingerprints.
    return json.loads(json.dumps(value,ensure_ascii=False))

def source_revision(plan,sid):
    from .runtime import Storage,data_root
    source=dependency_source(plan,sid)
    if not source:return None
    row=Storage(data_root()).latest_output(plan['id'],source)
    return source_record(source,row)

def source_record(source,row):
    if not source:return None
    if not row:return {'id':source}
    # HD and face processing replace the exported file, but reuse the base
    # generation. Dependants only care whether that underlying shot changed.
    if row.get('base_version'):return {'id':source,'base_version':row['base_version']}
    return {'id':source,'fingerprint':row.get('fingerprint'),'path':row.get('path')}

def normalized_source(plan,source):
    """Resolve v4/legacy output pins to a base version when history allows."""
    if not source or not source.get('id'):return source
    if source.get('base_version'):return {'id':source['id'],'base_version':source['base_version']}
    if not (source.get('fingerprint') or source.get('path')):return {'id':source['id']}
    from .runtime import Storage,data_root
    store=Storage(data_root())
    constraints=['project=?','shot=?'];values=[plan['id'],source['id']]
    for field in ('fingerprint','path'):
        if source.get(field):constraints.append(field+'=?');values.append(source[field])
    with store.db(plan['id'],create=False) as db:
        row=db.execute('SELECT base_version FROM outputs WHERE '+' AND '.join(constraints)+' LIMIT 1',values).fetchone()
    if row and row[0]:return {'id':source['id'],'base_version':row[0]}
    return source

def source_changed(plan,sid,saved):
    before=normalized_source(plan,saved)
    after=source_revision(plan,sid)
    if not before or not after or before.get('id')!=after.get('id'):return False
    if 'base_version' in before and 'base_version' in after:return before['base_version']!=after['base_version']
    if 'base_version' in before or 'base_version' in after:return False
    if before.get('fingerprint') and after.get('fingerprint'):return before['fingerprint']!=after['fingerprint'] or before.get('path')!=after.get('path')
    return False

def uses_previous_tail(plan,sid):
    shot=next(s for s in plan['shots'] if s['id']==sid)
    return shot.get('input_mode')=='keyframes' and bool(shot.get('keyframes',{}).get('first',{}).get('from_previous'))

def encode(plan,sid,previous=None):
    source=source_revision(plan,sid)
    if previous and plan.get('runtime',{}).get('scope')=='process':
        old=baseline(plan,sid,previous)
        if old is not None:source=old.get('source')
    return PREFIX+json.dumps({'inputs':snapshot(plan,sid),'source':source},ensure_ascii=False,sort_keys=True)

def baseline(plan,sid,record):
    from .runtime import data_root
    saved=record.get('parameter_fingerprint','') or ''
    if saved.startswith(PREFIX):return json.loads(saved[len(PREFIX):])
    for path in sorted((data_root()/'projects'/plan['id']/'batches').glob('*.json'),reverse=True):
        try:
            task=json.loads(path.read_text(encoding='utf-8'));result=task.get('results',{}).get(sid,{})
            if result.get('path')!=record.get('path') or not result.get('prompt_id'):continue
            old=copy.deepcopy(task['plan'])
            if isinstance(result.get('post'),dict):next(s for s in old['shots'] if s['id']==sid)['post']=result['post']
            source=dependency_source(old,sid);pin=task.get('reference_pins',{}).get(source)
            ref=source_record(source,pin) if pin else None
            return {'inputs':snapshot(old,sid),'source':ref}
        except (OSError,ValueError,TypeError,KeyError):continue
    return None

CONTINUITY_NAMES={'independent':'独立镜头','motion_guide':'运动引导','motion_redraw':'运动引导＋重绘',
    'tail_reference':'尾帧画面参考','selected_frame':'选定画面参考','previous_latent':'运动引导'}

def editable_inputs(value):
    """Explicit user choices only; compiler/cache metadata is never an edit."""
    shot=value.get('shot') or {};post=shot.get('post') or {}
    smart=shot.get('input_mode','reference')=='keyframes'
    mode=(shot.get('continuity') or {}).get('mode','independent')
    mode='motion_guide' if mode=='previous_latent' else mode
    continuity={'mode':mode if not smart else 'independent'}
    if not smart and mode!='independent':
        continuity['source_shot']=shot.get('continuity',{}).get('source_shot')
        if mode=='selected_frame':continuity['frame']=shot.get('continuity',{}).get('frame',0)
    frames={}
    if smart:
        for slot in ('first','last'):
            frame=(shot.get('keyframes') or {}).get(slot) or {}
            if frame.get('from_previous'):
                frames[slot]={'from_previous':True,'source_shot':value.get('first_from_previous')}
            elif frame.get('source'):frames[slot]={'source':frame['source']}
    assets={}
    def selected_media(item):
        result={k:item[k] for k in ('type','source') if k in item}
        if item.get('type') in ('audio','video'):
            result.update(start_seconds=item.get('start_seconds',0),duration_seconds=item.get('duration_seconds',6))
        return result
    for card in value.get('assets',[]):
        media=[selected_media(m)
               for m in card.get('media',[]) if not smart or m.get('type')=='audio']
        # Keyframe mode does not consume the prompt's image/video references.
        # A character image still matters when it is used for face repair.
        if smart and post.get('face') and card.get('kind')=='character':
            media=[selected_media(m) for m in card.get('media',[])]
        if media or not card.get('media'):
            assets[card['id']]={'media':media,'description':card.get('description',''),
                                'voice_id':card.get('voice_id') or None}
    return {'duration':shot.get('duration',5),'seed':shot.get('seed',0),'prompt':shot.get('prompt',''),
            'input_mode':'keyframes' if smart else 'reference','continuity':continuity,'keyframes':frames,
            'references':sorted(shot.get('references') or []),'assets':assets,
            'post':{'hd':bool(post.get('hd')),'face':bool(post.get('face')),
                    'face_count':post.get('face_count',value.get('generation',{}).get('395',{}).get('face_count',1)) if post.get('face') else None},
            'prompt_options':{k:bool(shot.get('prompt_options',{}).get(k)) for k in ('no_subtitles','no_background_music')}}

def visible_changes(old,new,names=None):
    """One readable row per editable choice, never a recursive payload dump."""
    before=editable_inputs(old);after=editable_inputs(new);rows=[];names=names or {}
    def add(field,label,a,b):
        rows.append({'field':field,'label':label,'before':str(a),'after':str(b)})
    for key,label in (('duration','镜头 / 时长'),('seed','镜头 / 种子')):
        if before[key]!=after[key]:
            suffix=' 秒' if key=='duration' else ''
            add('shot.'+key,label,str(before[key])+suffix,str(after[key])+suffix)
    if before['prompt']!=after['prompt']:
        add('shot.prompt','提示词','原提示词','提示词内容已修改')
    mode_changed=before['input_mode']!=after['input_mode']
    if mode_changed:
        labels={'reference':'参考模式','keyframes':'智能首尾帧模式'}
        add('shot.input_mode','输入模式',labels[before['input_mode']],labels[after['input_mode']])
    elif before['continuity']!=after['continuity']:
        def describe(value):
            mode=value['mode'];name=CONTINUITY_NAMES.get(mode,mode);source=value.get('source_shot')
            if source:name+='（参考 '+source+(' 的第 '+str(value.get('frame',0))+' 帧' if mode=='selected_frame' else ' 的画面')+'）'
            return name
        add('shot.continuity','连续性',describe(before['continuity']),describe(after['continuity']))
    for slot,label in (('first','首帧'),('last','尾帧')):
        a=before['keyframes'].get(slot);b=after['keyframes'].get(slot)
        if a==b or mode_changed and not (a or b):continue
        def describe(frame):
            return '未设置' if not frame else '使用上段视频尾帧' if frame.get('from_previous') else '已指定图片'
        add('shot.keyframes.'+slot,label,describe(a),'已更换图片' if a and b and a.get('source') and b.get('source') else describe(b))
    if not mode_changed:
        if before['references']!=after['references']:
            add('shot.references','素材引用','原引用列表','引用列表已修改')
        for aid in sorted(before['assets'].keys()|after['assets'].keys()):
            a=before['assets'].get(aid);b=after['assets'].get(aid)
            if a==b:continue
            label='引用素材 / '+names.get(aid,'素材')
            if a is None or b is None:
                add('assets.'+aid,label,'未引用' if a is None else '已引用','未引用' if b is None else '已引用')
            elif a['media']!=b['media']:
                add('assets.'+aid+'.media',label,'原素材文件或片段','素材文件或片段已更换')
            elif a['voice_id']!=b['voice_id']:
                add('assets.'+aid+'.voice_id','音色绑定 / '+names.get(aid,'素材'),'原绑定音色','绑定音色已修改')
            else:
                add('assets.'+aid+'.description','素材描述 / '+names.get(aid,'素材'),'原素材描述','素材描述已修改')
    for flag,label in (('hd','高清二采'),('face','人脸修复')):
        if before['post'][flag]!=after['post'][flag]:
            add('shot.post.'+flag,label,'开启' if before['post'][flag] else '关闭','开启' if after['post'][flag] else '关闭')
    if before['post']['face'] and after['post']['face'] and before['post']['face_count']!=after['post']['face_count']:
        add('shot.post.face_count','修脸人数',str(before['post']['face_count'])+' 人',str(after['post']['face_count'])+' 人')
    for key,label in (('no_subtitles','强调无字幕'),('no_background_music','强调无背景音乐')):
        if before['prompt_options'][key]!=after['prompt_options'][key]:
            add('shot.prompt_options.'+key,label,'开启' if before['prompt_options'][key] else '关闭','开启' if after['prompt_options'][key] else '关闭')
    return rows

def details(plan,sid,record):
    if not record:return {'changes':[],'reference_changed':False}
    old=baseline(plan,sid,record)
    if old is None:return {'changes':[],'reference_changed':False,'baseline_unknown':True}
    changed=source_changed(plan,sid,old.get('source'))
    changes=visible_changes(old['inputs'],snapshot(plan,sid),{a['id']:a['name'] for a in plan.get('assets',[])})
    if changed and uses_previous_tail(plan,sid):
        changes.append({'field':'shot.keyframes.first.from_previous.source_version','label':'首帧 / 上段视频尾帧',
                        'before':'原参考画面','after':'上段镜头已重新生成，当前镜头尚未更新'})
    return {'changes':changes,'reference_changed':changed and not uses_previous_tail(plan,sid)}
