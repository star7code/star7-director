"""Explainable shot edits, deliberately separate from execution/cache hashes."""
import json,copy
from pathlib import Path
from .core import _compile_shot,dependency_source

PREFIX='v4:'

def snapshot(plan,sid):
    from .runtime import generation_identity,media_revision
    value=_compile_shot(generation_identity(plan),sid,parameter_payload=True)
    post=value['shot'].get('post',{})
    value['generation']={k:v for k,v in plan.get('generation',{}).items()
        if k not in ('150','377') and not (k=='376' and not post.get('hd') or k=='395' and not post.get('face'))}
    value['media_revision']=media_revision(plan,sid)
    # JSON roundtrip makes persisted lists and current stat tuples identical.
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

LABELS={'shot':'镜头','prompt':'提示词','seed':'种子','duration':'时长','input_mode':'输入模式',
    'post':'后处理','hd':'高清二采','face':'人脸修复','face_count':'修脸人数','continuity':'连续性',
    'mode':'模式','source_shot':'参考镜头','frame':'参考帧','keyframes':'首尾帧','first':'首帧','last':'尾帧',
    'assets':'引用素材','references':'素材引用','media_revision':'素材文件版本','settings':'画面规格',
    'width':'宽度','height':'高度','fps':'帧率','generation':'导演台生成设置','376':'二采参数','395':'修脸参数',
    'av_handoff':'镜头衔接','reference_size':'参考素材尺寸','prompt_options':'提示词选项',
    'media':'素材媒体','source':'文件','description':'素材描述','kind':'素材类型','text_file':'文本文件',
    'steps':'采样步数','denoise':'去噪强度','scheduler':'调度方式','sampler_name':'采样器','126':'采样参数','308':'采样器',
    'no_subtitles':'强调无字幕','no_background_music':'强调无背景音乐',
    'first_from_previous':'使用上段尾帧','tail_reference':'参考画面','audio':'延续音频','redraw':'重绘幅度','context_frames':'上下文帧数'}

def differences(old,new,path=()):
    if old==new:return []
    if path==('assets',) and isinstance(old,list) and isinstance(new,list):
        return differences({v['id']:v for v in old},{v['id']:v for v in new},path)
    if isinstance(old,dict) and isinstance(new,dict):
        return [row for key in sorted(old.keys()|new.keys()) for row in differences(old.get(key),new.get(key),(*path,key))]
    label=' / '.join(LABELS.get(str(k),str(k)) for k in path)
    def display(v):
        if v is None:return '未设置'
        if isinstance(v,bool):return '开启' if v else '关闭'
        text=str(v) if not isinstance(v,(list,dict)) else json.dumps(v,ensure_ascii=False)
        return text if len(text)<=100 else text[:97]+'…'
    return [{'field':'.'.join(path),'label':label,'before':display(old),'after':display(new)}]

CONTINUITY_NAMES={'independent':'独立镜头','motion_guide':'运动引导','motion_redraw':'运动引导＋重绘',
    'tail_reference':'尾帧画面参考','selected_frame':'选定画面参考','previous_latent':'运动引导'}

def visible_changes(old,new):
    """Group mode selection and its generated reference/handoff fields as one edit."""
    rows=differences(old,new)
    old_post=old.get('shot',{}).get('post') or {}
    new_post=new.get('shot',{}).get('post') or {}
    # Inactive post settings are absent from the saved generation snapshot.
    # Enabling a pass exposes its configured settings at the same time; that
    # is one user action, not a second independent parameter edit.
    for flag,node in (('hd','376'),('face','395')):
        if not old_post.get(flag) and new_post.get(flag):
            rows=[row for row in rows if not row['field'].startswith('generation.'+node)]
    before=old.get('shot',{}).get('continuity') or {'mode':'independent'}
    after=new.get('shot',{}).get('continuity') or {'mode':'independent'}
    if before!=after:
        def describe(value):
            mode=value.get('mode','independent');name=CONTINUITY_NAMES.get(mode,mode)
            if mode!='independent':
                source=value.get('source_shot')
                if source:name+='（参考 '+source+(' 的第 '+str(value.get('frame',0))+' 帧' if mode=='selected_frame' else ' 的画面')+'）'
            return name
        # These compiled fields are consequences of the same choice, not
        # separate edits a user can independently make in this panel.
        hidden_prefixes=('shot.continuity','av_handoff','tail_reference','first_from_previous')
        rows=[r for r in rows if not r['field'].startswith(hidden_prefixes)]
        if old.get('reference_size') is None and new.get('reference_size') is not None:
            rows=[r for r in rows if r['field']!='reference_size']
        rows.insert(0,{'field':'shot.continuity','label':'连续性','before':describe(before),'after':describe(after)})
    return rows

def details(plan,sid,record):
    if not record:return {'changes':[],'reference_changed':False}
    old=baseline(plan,sid,record)
    if old is None:return {'changes':[],'reference_changed':False,'baseline_unknown':True}
    changed=source_changed(plan,sid,old.get('source'))
    changes=visible_changes(old['inputs'],snapshot(plan,sid))
    if changed and uses_previous_tail(plan,sid):
        changes.append({'field':'shot.keyframes.first.from_previous.source_version','label':'首帧 / 上段视频尾帧',
                        'before':'原参考画面','after':'上段镜头已重新生成，当前镜头尚未更新'})
    return {'changes':changes,'reference_changed':changed and not uses_previous_tail(plan,sid)}
