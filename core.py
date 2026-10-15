"""Director plans contain references and metadata, never model objects."""
import hashlib
import json
import math
import re
from pathlib import Path

try:
    from .reference_size import normalize as reference_limits
except ImportError:
    from reference_size import normalize as reference_limits

ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
try:
    from .references import MENTION,TAIL_REFERENCE_ID,SELECTED_REFERENCE_ID,is_tail_reference,mention_name
except ImportError:
    from references import MENTION,TAIL_REFERENCE_ID,SELECTED_REFERENCE_ID,is_tail_reference,mention_name
KINDS = {"character", "prop", "scene", "effect", "voice", "video"}
LIMITS = {"image": 9, "audio": 3, "video": 3}
STAGES = {"base", "hd", "face", "final"}

def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("ID must contain 1–64 letters, digits, underscores or hyphens")
    return value

def dependency_source(plan,shot_id):
    index=next(i for i,s in enumerate(plan['shots']) if s['id']==shot_id);shot=plan['shots'][index]
    if shot.get('input_mode')=='keyframes':
        if shot.get('keyframes',{}).get('first',{}).get('from_previous'):
            return plan['shots'][index-1]['id'] if index else None
        return None
    continuity=shot.get('continuity',{})
    return continuity.get('source_shot') if continuity.get('mode','independent')!='independent' else None

def validate_continuity_settings(cfg):
    if not isinstance(cfg,dict):raise ValueError('连续性设置必须是对象')
    if 'context_frames' in cfg and (type(cfg['context_frames']) is not int or cfg['context_frames'] not in (5,22,39,56)):raise ValueError('上下文帧数只支持5、22、39、56')
    if 'audio' in cfg and type(cfg['audio']) is not bool:raise ValueError('音频延续开关必须是布尔值')
    if 'drift_control' in cfg and type(cfg['drift_control']) is not bool:raise ValueError('运动引导去漂移必须为开关值')
    strength=cfg.get('drift_strength',.3)
    if isinstance(strength,bool) or not isinstance(strength,(int,float)) or not math.isfinite(strength) or not 0<=strength<=.6:raise ValueError('去漂移强度必须为0–0.6')
    v=cfg.get('redraw',.65)
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not .4<=v<=.95:raise ValueError('重绘幅度必须为0.40–0.95')

def injects_image_description(asset, smart=False):
    return not smart and bool(asset.get('inject_description',False)) and bool(asset.get('description','').strip()) and asset.get('kind') in ('character','prop','scene') and any(m.get('type')=='image' for m in asset.get('media',[]))


def validate(plan):
    if not isinstance(plan, dict) or plan.get("schema_version") != "1.0":
        raise ValueError("Expected director schema_version 1.0")
    reference_limits(plan.get("reference_size"))
    identifier(plan.get("id"))
    assets, shots = plan.get("assets"), plan.get("shots")
    if not isinstance(assets, list) or not isinstance(shots, list) or len(assets)>500 or len(shots)>1000:
        raise ValueError("Invalid asset/shot list")
    validate_continuity_settings(plan.get('continuity_settings',{}))
    execution_options=plan.get('execution_options',{})
    if not isinstance(execution_options,dict) or ('clear_vram_between_shots' in execution_options and type(execution_options['clear_vram_between_shots']) is not bool):raise ValueError('段间清理显存必须为开关值')
    options=plan.get('prompt_options',{})
    if not isinstance(options,dict) or ('no_subtitles' in options and type(options['no_subtitles']) is not bool):raise ValueError('全局无字幕选项必须是布尔值')
    if not isinstance(options.get('custom_prompt',''),str) or len(options.get('custom_prompt',''))>12000:raise ValueError('自定义参数必须为文字，最多 12000 字符')
    if 'custom_prompt_enabled' in options and type(options['custom_prompt_enabled']) is not bool:raise ValueError('启用自定义参数必须为开关值')
    names, asset_ids, shot_ids = {}, set(), set()
    for asset in assets:
        if not isinstance(asset,dict): raise ValueError('素材卡必须是对象')
        if not isinstance(asset.get('aliases',[]),list) or not isinstance(asset.get('media',[]),list): raise ValueError('别名与媒体必须是列表')
        if not isinstance(asset.get('name'),str): raise ValueError('素材名称必须是文字')
        if not isinstance(asset.get('description',''),str):raise ValueError('素材描述必须是文字')
        if 'inject_description' in asset and type(asset['inject_description']) is not bool:raise ValueError('注入素材描述必须是开关值')
        aid = identifier(asset.get("id"))
        if aid in asset_ids: raise ValueError("Duplicate asset ID: " + aid)
        asset_ids.add(aid)
        if asset.get("kind") not in KINDS or not str(asset.get("name", "")).strip():
            raise ValueError("Invalid asset category/name")
        for name in [aid, asset["name"], *asset.get("aliases", [])]:
            if not isinstance(name, str) or not name.strip(): raise ValueError("Invalid alias")
            if name in names and names[name] != aid: raise ValueError("Ambiguous asset name: " + name)
            names[name] = aid
        for media in asset.get("media", []):
            if not isinstance(media,dict): raise ValueError('媒体引用必须是对象')
            if media.get("type") not in LIMITS or not isinstance(media.get("source"), str) or not media["source"]:
                raise ValueError("Invalid media reference")
            for key,default,minimum,maximum in (('start_seconds',0,0,86400),('duration_seconds',6,.1,30)):
                value=media.get(key,default)
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not minimum<=value<=maximum:raise ValueError('参考片段参数无效：'+key)
    for asset in assets:
        voice = asset.get("voice_id")
        if voice is not None and not isinstance(voice,str): raise ValueError("音色绑定必须是素材 ID")
        if voice and (voice not in asset_ids or not any(a["id"]==voice and a["kind"]=="voice" for a in assets)):
            raise ValueError("Character voice binding must reference a voice card")
    for shot in shots:
        if not isinstance(shot,dict): raise ValueError('镜头必须是对象')
        if not isinstance(shot.get('references',[]),list) or not all(isinstance(v,str) for v in shot.get('references',[])): raise ValueError('镜头引用必须是文字列表')
        if shot.get('input_mode','reference') not in ('reference','keyframes'):raise ValueError('无效镜头输入模式')
        endpoints=shot.get('keyframes',{})
        if not isinstance(endpoints,dict) or any(k not in ('first','last') or not isinstance(v,dict) or not (isinstance(v.get('source'),str) or k=='first' and v.get('from_previous') is True) for k,v in endpoints.items()):raise ValueError('首尾帧必须是图片素材或上段尾帧设置')
        if endpoints.get('first',{}).get('from_previous') and not shot_ids:raise ValueError('首个镜头没有上段视频，不能使用上段尾帧')
        if not isinstance(shot.get('post',{}),dict): raise ValueError('后处理设置必须是对象')
        if any(not isinstance(v,bool) for k,v in shot.get('post',{}).items() if k in ('hd','face')): raise ValueError('二采和修脸开关必须是 true 或 false')
        count=shot.get('post',{}).get('face_count')
        if count is not None and (type(count) is not int or not 1<=count<=4):raise ValueError('当前镜头修脸人数必须为 1–4 的整数')
        validate_continuity_settings(shot.get("continuity",{}))
        options=shot.get('prompt_options',{})
        if not isinstance(options,dict) or ('no_subtitles' in options and type(options['no_subtitles']) is not bool):raise ValueError('无字幕选项必须是布尔值')
        sid = identifier(shot.get("id"))
        if sid in shot_ids: raise ValueError("Duplicate shot ID: " + sid)
        shot_ids.add(sid)
        duration = shot.get("duration", 5)
        if not isinstance(duration, (int,float)) or isinstance(duration,bool) or not math.isfinite(duration) or not 0 < duration <= 60:
            raise ValueError("Shot duration must be between 0 and 60 seconds")
        if not isinstance(shot.get("prompt"), str): raise ValueError("Shot prompt must be text")
        if shot.get('seed_control','fixed') not in ('fixed','increment','decrement','randomize'):raise ValueError('生成后种子控制无效')
        if 'next_seed' in shot and (type(shot['next_seed']) is not int or not 0<=shot['next_seed']<=2**53-1):raise ValueError('下一次种子无效')
        continuity = shot.get("continuity", {"mode":"independent"})
        if not isinstance(continuity,dict): raise ValueError('连续性必须是对象')
        if continuity.get("mode") not in ("independent","previous_latent","motion_guide","motion_redraw","selected_frame","tail_reference"):
            raise ValueError("Invalid continuity mode")
        source = continuity.get("source_shot")
        if source is not None and not isinstance(source,str): raise ValueError("连续性 source_shot 必须是镜头 ID")
        if continuity["mode"] != "independent":
            if source not in shot_ids or source==sid: raise ValueError("Continuity must reference an earlier shot")
        if continuity["mode"] == "selected_frame" and (not isinstance(continuity.get("frame"), int) or continuity["frame"]<0):
            raise ValueError("Select a non-negative frame index")
        if not isinstance(shot.get("seed",0),int) or isinstance(shot.get("seed",0),bool) or not 0 <= shot.get("seed",0) <= 2**53-1: raise ValueError("Invalid seed")
    settings=plan.get("settings",{})
    if not isinstance(settings,dict): raise ValueError('画布设置必须是对象')
    if settings.get("fps",24) != 24: raise ValueError("Initial H3 profile requires 24 fps")
    for key, default in (("width",960),("height",544)):
        value=settings.get(key,default)
        if not isinstance(value,int) or not 32<=value<=8192 or value%32:
            raise ValueError("H3 canvas must use a 32-pixel grid")
    return plan

def _compile_shot(plan, shot_id, parameter_payload=False):
    shot=next((s for s in plan["shots"] if s["id"]==shot_id),None)
    if shot is None: raise ValueError("Unknown shot")
    import copy
    shot=copy.deepcopy(shot)
    original_prompt=shot['prompt']
    prompt_options=plan.get('prompt_options',{})
    custom_prompt=prompt_options.get('custom_prompt','').strip() if prompt_options.get('custom_prompt_enabled',bool(prompt_options.get('custom_prompt','').strip())) else ''
    if custom_prompt:shot['prompt']=original_prompt.rstrip()+'\n\n'+custom_prompt
    smart=shot.get('input_mode','reference')=='keyframes'
    keyframes=shot.get('keyframes',{}) if smart else {}
    if smart:shot['continuity']={'mode':'independent'}
    by_id={a["id"]:a for a in plan["assets"]}
    names={n:a["id"] for a in plan["assets"] for n in [a["id"],a["name"],*a.get("aliases",[])]}
    requested=[]
    def select(name):
        if is_tail_reference(name,names):
            return TAIL_REFERENCE_ID
        if name in (SELECTED_REFERENCE_ID,'__star7_first_frame__','__star7_last_frame__'):return name
        aid=names.get(name)
        if aid is None: raise ValueError("Unknown material: @"+name)
        if aid not in requested: requested.append(aid)
        return aid
    visiting=set();expanded=set()
    def expand(name):
        aid=select(name)
        if aid in (TAIL_REFERENCE_ID,SELECTED_REFERENCE_ID,'__star7_first_frame__','__star7_last_frame__'):return aid
        if aid in visiting:raise ValueError('文字素材引用形成循环：'+by_id[aid]['name'])
        if aid in expanded:return aid
        visiting.add(aid)
        if not by_id[aid].get('media') or injects_image_description(by_id[aid],smart):
            for match in MENTION.finditer(by_id[aid].get('description','')):expand(mention_name(match))
        voice=by_id[aid].get('voice_id')
        if voice:expand(voice)
        visiting.remove(aid);expanded.add(aid);return aid
    for match in MENTION.finditer(shot['prompt']):expand(mention_name(match))
    for ref in shot.get('references',[]):expand(ref)
    media={kind:[] for kind in LIMITS}
    labels={}
    for aid in requested:
        labels[aid]=[]
        for item in by_id[aid].get("media",[]):
            kind=item["type"]
            if smart and kind in ('image','video'):continue
            existing=next((i for i,m in enumerate(media[kind]) if m["source"]==item["source"]),None)
            if existing is None:
                media[kind].append({"asset_id":aid,**item})
                existing=len(media[kind])-1
            labels[aid].append(f"<{dict(image='Picture',audio='Audio',video='Video')[kind]} {existing+1}>")
    for kind,limit in LIMITS.items():
        if len(media[kind])>limit: raise ValueError(f"{kind} references {len(media[kind])} exceed {limit}; split the shot")
    continuity_reference=None
    reference_mode=shot.get('continuity',{}).get('mode')
    if reference_mode in ('tail_reference','selected_frame'):
        if len(media['image'])>=LIMITS['image']:raise ValueError(('参考帧' if reference_mode=='selected_frame' else '尾帧画面参考')+'占用1张图片，本镜头其他图片最多8张')
        index=len(media['image']);label=f'<Picture {index+1}>'
        continuity_reference={'index':index,'label':label,'source_shot':shot['continuity']['source_shot'],'role':'previous_final_frame','token':'@{尾帧}'}
    if reference_mode=='selected_frame':continuity_reference.update(role='previous_selected_frame',frame=shot['continuity']['frame'],token='@{参考帧}')
    # Explicit references include nested text/opted-in descriptions, but not
    # the automatic voice_id dependency. This distinguishes authored bindings
    # from the missing-reference safety net.
    explicit=set()
    def mark_explicit(name):
        aid=names.get(name)
        if aid is None or aid in explicit:return
        explicit.add(aid)
        card=by_id[aid]
        if not card.get('media') or injects_image_description(card,smart):
            for match in MENTION.finditer(card.get('description','')):mark_explicit(mention_name(match))
    for match in MENTION.finditer(shot['prompt']):mark_explicit(mention_name(match))
    explicit_audio={label for aid in explicit for label in labels.get(aid,[]) if label.startswith('<Audio ')}
    fallback_audio={}
    for aid in requested:
        voice=by_id[aid].get('voice_id')
        if not voice:continue
        tags=[tag for tag in labels.get(voice,[]) if tag.startswith('<Audio ')]
        if tags and not all(tag in explicit_audio or tag in shot['prompt'] for tag in tags):
            fallback_audio[aid]=' '.join(tags)
    def text_for(aid):
        if aid==TAIL_REFERENCE_ID:
            if smart:return 'the supplied last frame' if keyframes.get('last') else '@{尾帧}'
            return continuity_reference['label'] if reference_mode=='tail_reference' else '@{尾帧参考}'
        if aid==SELECTED_REFERENCE_ID:return continuity_reference['label'] if reference_mode=='selected_frame' else '@{参考帧}'
        if aid=='__star7_first_frame__':return 'the supplied first frame' if smart and keyframes.get('first') else '@{首帧}'
        if aid=='__star7_last_frame__':return 'the supplied last frame' if smart and keyframes.get('last') else '@{尾帧}'
        label='@{'+aid+'}' if smart and any(m['type'] in ('image','video') for m in by_id[aid].get('media',[])) else ' '.join(labels[aid])
        if label:
            if aid in fallback_audio:label+=' '+fallback_audio[aid]
            description=by_id[aid].get('description','').strip()
            return label+' '+MENTION.sub(replace,description) if description and injects_image_description(by_id[aid],smart) else label
        text=MENTION.sub(replace,by_id[aid].get('description') or by_id[aid]['name'])
        return text+' '+fallback_audio[aid] if aid in fallback_audio else text
    def replace(match):
        aid=select(mention_name(match))
        if aid==TAIL_REFERENCE_ID and smart and match[1]!='尾帧':return match[0]
        if aid==TAIL_REFERENCE_ID and not (smart and keyframes.get('last') or not smart and reference_mode=='tail_reference'):return match[0]
        if aid==SELECTED_REFERENCE_ID and reference_mode!='selected_frame':return match[0]
        if aid=='__star7_first_frame__' and not (smart and keyframes.get('first')):return match[0]
        if aid=='__star7_last_frame__' and not (smart and keyframes.get('last')):return match[0]
        return text_for(aid)
    prompt=MENTION.sub(replace,shot['prompt'])
    # Text-only voice cards remain textual timbre guidance. Audio bindings
    # are authored explicitly or inserted inline above, never inferred S IDs.
    voices=[]
    for aid in requested:
        voice=by_id[aid].get('voice_id')
        if voice and voice not in explicit and not labels.get(voice):
            voices.append(by_id[aid]['name']+'音色：'+text_for(voice))
    if voices:prompt+='\n'+'；'.join(voices)
    if continuity_reference:
        from .tail_reference import augment_prompt
        prompt=augment_prompt(prompt,continuity_reference['label'],frame=continuity_reference.get('frame'))
    no_subtitles=plan.get('prompt_options',{}).get('no_subtitles',shot.get('prompt_options',{}).get('no_subtitles',False))
    if no_subtitles:
        cue='Screen: no subtitles, no on-screen text, no watermark.'
        prompt='\n'.join(line for line in prompt.splitlines() if line.strip().lower()!=cue.lower()).rstrip()+'\n'+cue
    if plan.get('prompt_options',{}).get('no_background_music',False):
        prompt=re.sub(r'(?mis)^\s*non_diegetic_music\s*:.*?(?=^\s*[a-z_]+\s*:|\Z)', '', prompt).rstrip()+'\nnon_diegetic_music:\nN/A'
    fingerprint_shot={k:v for k,v in shot.items() if k not in ('seed_control','next_seed')}
    fingerprint_shot['prompt']=original_prompt
    # Hash the effective flag, preserving old per-shot fingerprints while
    # global settings take precedence over legacy values.
    options=dict(shot.get('prompt_options',{}))
    if custom_prompt:options['custom_prompt']=custom_prompt
    else:options.pop('custom_prompt',None)
    if no_subtitles:options['no_subtitles']=True
    else:options.pop('no_subtitles',None)
    if options:fingerprint_shot['prompt_options']=options
    else:fingerprint_shot.pop('prompt_options',None)
    if not smart:
        fingerprint_shot.pop('keyframes',None)
        fingerprint_shot.pop('input_mode',None)
    if plan.get('prompt_options',{}).get('no_background_music',False):fingerprint_shot.setdefault('prompt_options',{})['no_background_music']=True
    payload={"shot":fingerprint_shot,"settings":plan.get("settings",{}),"assets":[by_id[a] for a in requested]}
    if fallback_audio:payload['voice_inline_recipe']=1
    # An absent/disabled switch has the same behavior as legacy assets.
    payload['assets']=[{k:v for k,v in card.items() if k!='inject_description' or injects_image_description(card,smart)} for card in payload['assets']]
    if smart and keyframes.get('first',{}).get('from_previous'):
        payload['first_from_previous']=dependency_source(plan,shot_id)
    aliases=plan.get('media_aliases',{})
    def canonical_media(value):
        if isinstance(value,list):return [canonical_media(v) for v in value]
        if isinstance(value,dict):return {k:aliases.get(v,v) if k in ('source','thumbnail_source') and isinstance(v,str) else canonical_media(v) for k,v in value.items()}
        return value
    if aliases:payload=canonical_media(payload)
    if not continuity_reference and any(is_tail_reference(mention_name(m)) for m in MENTION.finditer(prompt)):payload['tail_marker_passthrough']=1
    if continuity_reference:payload['tail_reference']={'version':3 if reference_mode=='selected_frame' else 2,**{k:v for k,v in continuity_reference.items() if k!='token'}}
    if media['image'] or media['video'] or continuity_reference or keyframes:
        sizes=reference_limits(plan.get('reference_size'));payload['reference_size']={'mode':sizes['mode'],**{k:v for k,v in sizes.items() if ((media['image'] or continuity_reference or keyframes) and k.startswith('image_') or media['video'] and k.startswith('video_')) and (k.endswith('_mp') if sizes['mode']=='megapixels' else k.endswith('_long_edge'))}}
    if shot.get('continuity',{}).get('mode','independent') in ('previous_latent','motion_guide','motion_redraw'):
        cfg={**plan.get('continuity_settings',{}),**shot['continuity']};payload['av_handoff']={'version':2,'context_frames':cfg.get('context_frames',22),'audio':cfg.get('audio',True),'redraw':cfg.get('redraw',.65) if cfg['mode']=='motion_redraw' else None}
        if cfg['mode']!='motion_redraw' and cfg.get('drift_control',False) and cfg.get('drift_strength',.3)>0:
            payload['av_handoff']['drift_control']={'recipe':1,'strength':cfg.get('drift_strength',.3)}
    if parameter_payload:return payload
    fingerprint=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return {"id":shot_id,"prompt":prompt,"duration":shot.get("duration",5),"seed":shot.get("seed",0),
            "keyframe_media":[{'type':'image',**m} for m in keyframes.values() if not m.get('from_previous')],"keyframes":keyframes,"continuity":shot.get("continuity",{"mode":"independent"}),"media":media,"labels":labels,"fingerprint":fingerprint,**({'continuity_reference':continuity_reference} if continuity_reference else {})}

def compile_plan(plan):
    validate(plan)
    compiled=[]
    fingerprints={}
    for shot in plan['shots']:
        item=_compile_shot(plan,shot['id'])
        source=item['continuity'].get('source_shot')
        if item['continuity']['mode']!='independent':
            item['fingerprint']=hashlib.sha256((item['fingerprint']+fingerprints[source]).encode()).hexdigest()
        fingerprints[item['id']]=item['fingerprint']
        compiled.append(item)
    return compiled

def compile_shot(plan,shot_id):
    for item in compile_plan(plan):
        if item['id']==shot_id: return item
    raise ValueError('Unknown shot')

def preflight(plan, input_root):
    """Validate every selected asset before spending GPU time."""
    root=Path(input_root).resolve()
    errors=[]
    for shot in compile_plan(plan):
        for values in [*shot["media"].values(),shot.get("keyframe_media",[])]:
            for item in values:
                source=item['source']
                if source.startswith('star7-project/'):
                    media_root=(Path(__file__).resolve().parent/'data'/'projects').resolve();path=(media_root/source[len('star7-project/'):]).resolve()
                    if not path.is_relative_to(media_root):raise ValueError('Invalid project media path')
                elif source.startswith('star7-director/'):
                    media_root=(Path(__file__).resolve().parent/'data'/'media').resolve();path=(media_root/source[len('star7-director/'):]).resolve()
                    if not path.is_relative_to(media_root):raise ValueError('Invalid director media path')
                else:
                    path=Path(source)
                    if not path.is_absolute():path=root/path
                path=path.resolve()
                problem=None
                if not path.is_file(): problem='文件不存在'
                else:
                    try:
                        if item['type']=='image':
                            from PIL import Image
                            with Image.open(path) as image:image.verify()
                        else:
                            import av
                            with av.open(str(path)) as container:
                                streams=container.streams.audio if item['type']=='audio' else container.streams.video
                                if not streams:raise ValueError('缺少对应媒体流')
                                if container.duration is not None and float(item.get('start_seconds',0))>=container.duration/av.time_base:raise ValueError('参考片段起点超出素材长度')
                    except Exception as error:problem='媒体不可读取或片段无效：'+str(error)
                if problem:errors.append({'shot':shot['id'],'asset':item['asset_id'],'source':item['source'],'reason':problem})
    return errors

def agent_catalog(plan):
    validate(plan)
    return {"schema_version":"1.0","assets":[{k:a[k] for k in ("id","kind","name","aliases","description","voice_id","inject_description") if k in a} |
            {"media_types":sorted({m["type"] for m in a.get("media",[])})} for a in plan["assets"]],
            "instructions":"Reference stable IDs as @id. Output {schema_version: 1.0, shots: [{id, name, duration, seed, prompt, continuity, post}]}. Use only listed assets; do not recreate asset cards. Independent continuity: {mode: independent}; continuation: {mode: previous_latent, source_shot: earlier_id}. File paths are omitted."}

def import_shots(project,document):
    validate(project)
    if document.get('schema_version')!='1.0' or not isinstance(document.get('shots'),list):
        raise ValueError('Expected schema_version 1.0 and shots')
    import copy
    result=copy.deepcopy(project)
    result['shots']=copy.deepcopy(document['shots'])
    compile_plan(result)
    return result
