"""Director runtime and adapters to its bundled H3 implementations."""
import hashlib
import json
from pathlib import Path
from .core import compile_shot,compile_plan,preflight,identifier,dependency_source,has_motion_successor
from .storage import Storage
from .run_logging import event


def data_root(): return Path(__file__).resolve().parent/'data'

def postprocess_source(plan,source_shot):
    import folder_paths
    record=Storage(data_root()).latest_output(plan['id'],source_shot)
    if not record:raise ValueError('前段成品不可用：'+source_shot)
    path=Path(record['path']).resolve()
    if not path.is_relative_to(Path(folder_paths.get_output_directory()).resolve()) or not path.is_file():raise ValueError('前段成品文件不可用：'+source_shot)
    return {'path':path,'record':record,'id':source_shot}

def registry(name):
    from .backend import implementation
    internal=implementation(name)
    if internal is not None:return internal
    import nodes as comfy_nodes
    cls=comfy_nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:raise ValueError('请安装或启用节点：'+name)
    return cls

def unpack(result):
    if hasattr(result,'args'):return result.args
    if hasattr(result,'result'):return result.result
    if isinstance(result,dict):return result['result']
    return result

def resolve_media(source):
    import folder_paths
    if source.startswith('star7-project/'):
        base=(data_root()/'projects').resolve();path=(base/source[len('star7-project/'):]).resolve()
        if not path.is_relative_to(base):raise ValueError('无效项目素材路径')
    elif source.startswith('star7-director/'):
        base=(data_root()/'media').resolve();path=(base/source[len('star7-director/'):]).resolve()
        if not path.is_relative_to(base):raise ValueError('无效素材路径')
    else:path=Path(folder_paths.get_annotated_filepath(source))
    if not path.is_file():raise ValueError('参考素材不存在：'+source)
    return path

def media_revision(plan,shot_id=None):
    result={}
    for shot in ([compile_shot(plan,shot_id)] if shot_id else compile_plan(plan)):
        for items in [*shot['media'].values(),shot.get('keyframe_media',[])]:
            for item in items:
                if item.get('from_previous'):continue
                source=item['source']
                if source not in result:
                    p=resolve_media(source)
                    st=p.stat();result[plan.get('media_aliases',{}).get(source,source)]=(st.st_size,st.st_mtime_ns)
    return result

def generation_identity(plan):
    """Card names/aliases are labels for stable identities, not new references."""
    import copy,re
    from .references import MENTION,mention_name
    result=copy.deepcopy(plan);lookup={}
    for card in result['assets']:
        for name in [card['id'],card['name'],*card.get('aliases',[])]:lookup[name]=card['id']
    def text(value):
        # Only explicit @ references resolve names. Prose/dialogue stays literal.
        return MENTION.sub(lambda match:'@{'+lookup[mention_name(match)]+'}' if mention_name(match) in lookup else match[0],str(value or ''))
    if result.get('prompt_options',{}).get('custom_prompt'):
        result['prompt_options']['custom_prompt']=text(result['prompt_options']['custom_prompt'])
    for shot in result['shots']:
        shot.pop('name',None);shot['prompt']=text(shot['prompt'])
        if 'references' in shot:shot['references']=[lookup.get(ref,ref) for ref in shot['references']]
    for card in result['assets']:
        if 'description' in card:card['description']=text(card['description'])
        card['name']=card['id']
        for key in ('aliases','sequence'):card.pop(key,None)
    return result

def run_fingerprint(plan,shot_id,prompt=None,stage='final',legacy_inactive=False,legacy_dependencies=False,legacy_base_dependencies=False,dependency_records=None,parameter_only=False):
    if parameter_only:plan=generation_identity(plan)
    if stage=='base':
        import copy
        plan=copy.deepcopy(plan)
        for item in plan['shots']:item.pop('post',None)
    generation=plan.get('generation',{})
    original_post=next(s for s in plan['shots'] if s['id']==shot_id).get('post',{})
    if stage!='base' and not legacy_inactive:generation={k:v for k,v in generation.items() if not (k=='376' and not original_post.get('hd') or k=='395' and not original_post.get('face'))}
    if stage=='base':generation={k:v for k,v in generation.items() if k not in ('376','395','150','377')}
    from .core import _compile_shot
    shot=_compile_shot(plan,shot_id) if parameter_only else compile_shot(plan,shot_id)
    # Capture external model, LoRA, sampler, HD and face parameters. Exclude
    # project JSON, volatile checkpoint versions and unrelated output widgets.
    import copy
    pipeline={k:{'class_type':v.get('class_type'),'inputs':copy.deepcopy(v.get('inputs',{}))} for k,v in (prompt or {}).items() if not v.get('class_type','').startswith('Star7Director') and v.get('class_type') not in ('VHS_VideoCombine','MiniMaxH3ChunkedDecodeStar7','MiniMaxH3LivePreviewStar7') and (stage!='base' or v.get('class_type') not in ('MiniMaxH3OneClickHDStar7','MiniMaxH3FaceRefineLatentStar7'))}
    # ComfyUI coerces FLOAT inputs (e.g. LoRA 1 -> 1.0) during queue
    # validation. Status/preflight must hash the same values as execution.
    # Match its schema conversion, preserving fingerprints of existing results.
    import nodes as comfy_nodes
    for spec in pipeline.values():
        cls=comfy_nodes.NODE_CLASS_MAPPINGS.get(spec['class_type'])
        if cls is None:continue
        schema=cls.INPUT_TYPES();definitions={**schema.get('required',{}),**schema.get('optional',{})}
        for key,value in list(spec['inputs'].items()):
            if definitions.get(key,('UNKNOWN',))[0]=='FLOAT' and type(value) in (int,float):spec['inputs'][key]=float(value)
    if any(v.get('class_type')=='Star7DirectorDesk' for v in (prompt or {}).values()):
        from .desk import template
        post=next(s for s in plan['shots'] if s['id']==shot_id).get('post',{})
        for nid,spec in template().items():
            if nid in ('150','377') or nid=='376' and (stage=='base' or not post.get('hd')) or nid=='395' and (stage=='base' or not post.get('face')):continue
            if spec['class_type'].startswith('Star7Director'):continue
            effective={k:plan.get('generation',{}).get(nid,{}).get(k,value) for k,value in spec['inputs'].items() if not isinstance(value,list)}
            if nid=='395' and 'face_count' in post:effective['face_count']=post['face_count']
            pipeline['director:'+nid]={'class_type':spec['class_type'],'inputs':effective}
    import folder_paths
    files={}
    roles={'unet_name':('diffusion_models','unet'),'clip_name':('text_encoders','clip'),'vae_name':('vae',),'lora_name':('loras',),'second_pass_lora':('loras',),'face_lora':('loras',),'upscale_model':('latent_upscale_models','upscale_models')}
    for nid,node in pipeline.items():
        for field,folders in roles.items():
            value=node['inputs'].get(field)
            if not isinstance(value,str):continue
            for folder in folders:
                try:path=folder_paths.get_full_path(folder,value)
                except KeyError:continue
                if path and Path(path).is_file():
                    stat=Path(path).stat();files[nid+':'+field]=(stat.st_size,stat.st_mtime_ns);break
    dependencies={}
    source=shot['continuity'].get('source_shot') if not parameter_only and shot['continuity']['mode']!='independent' else None
    store=Storage(data_root())
    while source:
        rows=[row for row in store.stages(plan['id']) if row['shot']==source and row['stage']=='base']
        record=(dependency_records or {}).get(source) or store.latest_output(plan['id'],source)
        revision=None
        if record and Path(record['path']).is_file():
            stat=Path(record['path']).stat();revision=(record['fingerprint'],record['path'],stat.st_size,stat.st_mtime_ns)
        # Once a final video exists, latent cleanup must not invalidate its
        # dependent clips. The final file revision is the source of truth.
        base=rows[-1]['version'] if rows else None
        if legacy_dependencies and base is None:
            with store.db(plan['id']) as db:
                retired=db.execute('SELECT version FROM retired_base_versions WHERE project=? AND shot=?',(plan['id'],source)).fetchone()
                base=retired[0] if retired else None
        if stage=='base' and not legacy_base_dependencies:
            if not base:
                with store.db(plan['id']) as db:
                    retired=db.execute('SELECT version FROM retired_base_versions WHERE project=? AND shot=?',(plan['id'],source)).fetchone();base=retired[0] if retired else None
            dependencies[source]={'base_generation':record.get('base_version') if record and record.get('base_version') else base}
        else:dependencies[source]={'base':base if legacy_dependencies or not revision else None,'output':revision}
        upstream=compile_shot(plan,source)['continuity']
        source=upstream.get('source_shot') if upstream['mode']!='independent' else None
    payload={'generation':generation,'shot':shot['fingerprint'],'media':media_revision(plan,shot_id),'pipeline':pipeline,'dependencies':dependencies,'model_files':files}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def output_matches(plan,shot_id,prompt,record):
    if not record:return False
    variants=[plan]
    # Previous UI edits added empty names even when only HD was toggled.
    # An absent/empty display name has no effect on generation. Match the exact
    # old fingerprint with only that accidental metadata addition removed.
    if any(s.get('name')=='' for s in plan['shots']):
        import copy
        clean=copy.deepcopy(plan)
        for s in clean['shots']:
            if s.get('name')=='':s.pop('name')
        variants.append(clean)
    return any(record['fingerprint']==run_fingerprint(value,shot_id,prompt,legacy_inactive=inactive,legacy_dependencies=dependencies) for value in variants for inactive,dependencies in ((False,False),(False,True),(True,False),(True,True)))

def parameter_matches(plan,shot_id,prompt,record):
    """Own generation settings only; changing an upstream result is not an edit."""
    if not record:return False
    from .parameter_state import baseline,snapshot,visible_changes,source_changed,uses_previous_tail,comparison_inputs
    saved_inputs=baseline(plan,shot_id,record)
    if saved_inputs is not None:
        return not visible_changes(comparison_inputs(saved_inputs),snapshot(plan,shot_id)) and not (
            uses_previous_tail(plan,shot_id) and source_changed(plan,shot_id,saved_inputs.get('source')))
    expected='v3:'+run_fingerprint(plan,shot_id,prompt,parameter_only=True)
    saved=record.get('parameter_fingerprint')
    if saved and (saved.startswith('v3:') or saved==expected[3:]):
        if saved==expected or saved==expected[3:]:
            from .parameter_state import encode
            record['parameter_fingerprint']=encode(plan,shot_id)
            if record.get('path'):
                store=Storage(data_root())
                with store.db(plan['id']) as db:
                    db.execute('UPDATE outputs SET parameter_fingerprint=? WHERE project=? AND shot=? AND fingerprint=?',
                               (record['parameter_fingerprint'],plan['id'],shot_id,record['fingerprint']))
        # An opaque legacy hash cannot identify a user edit. Retain the result
        # until a readable baseline is available; execution caches stay strict.
        return True
    # No readable historical plan means no evidence of a particular edit.
    # Never fall back to the execution/cache hash to paint an orange warning.
    return True


def batch_plan(plan,shot_id,record):
    """Batch updates add postprocessing; only explicit regeneration can remove it."""
    import copy
    actual=record.get('post') if record else None
    if not isinstance(actual,dict):return plan
    shot=next(s for s in plan['shots'] if s['id']==shot_id);requested=shot.get('post',{})
    post=dict(requested)
    for key in ('hd','face'):
        if actual.get(key):post[key]=True
    if actual.get('face') and not requested.get('face'):
        if 'face_count' in actual:post['face_count']=actual['face_count']
        else:post.pop('face_count',None)
    if post==requested:return plan
    result=copy.deepcopy(plan);next(s for s in result['shots'] if s['id']==shot_id)['post']=post
    return result

def load_image(source,reference_size=None):
    import numpy as np
    import torch
    from PIL import Image,ImageOps
    with Image.open(resolve_media(source)) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        from .reference_size import target_size
        size=target_size(*im.size,'image',reference_size)
        if im.size!=size:im=ImageOps.fit(im,size,method=Image.Resampling.LANCZOS,centering=(0.5,0.5))
        return torch.from_numpy(np.array(im).astype(np.float32)/255.0)[None]

def load_audio(source,start=0.0,duration=6.0):
    import subprocess,imageio_ffmpeg,numpy as np,torch
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(start),'-i',str(resolve_media(source)),'-t',str(duration),'-vn','-ar','48000','-ac','2','-f','f32le','pipe:1']
    result=subprocess.run(command,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode or not result.stdout:raise ValueError('音频参考片段无法读取：'+source)
    data=np.frombuffer(result.stdout,dtype=np.float32).copy().reshape(-1,2)
    return {'waveform':torch.from_numpy(data.T.copy())[None],'sample_rate':48000}

def load_video(source,start=0.0,duration=6.0,reference_size=None):
    import av,numpy as np,torch
    from PIL import Image
    from .reference_size import target_size
    frames=[];next_time=float(start);previous=None;size=None
    with av.open(str(resolve_media(source))) as container:
        stream=container.streams.video[0];rate=float(stream.average_rate or 24);interval=1/max(rate,1);end=float(start)+float(duration);origin=float((stream.start_time or 0)*stream.time_base)
        if start>0:container.seek(int((start+origin)*av.time_base),backward=True)
        if stream.duration is not None:end=min(end,float(stream.duration*stream.time_base))
        last_time=None
        def tensor(frame):
            nonlocal size
            image=frame.to_image().convert('RGB')
            if size is None:size=target_size(*image.size,'video',reference_size)
            if image.size!=size:image=image.resize(size,Image.Resampling.LANCZOS)
            return torch.from_numpy(np.asarray(image).copy()).float()/255
        previous_tensor=None;reached_end=False
        for index,frame in enumerate(container.decode(stream)):
            timestamp=float(frame.time)-origin if frame.time is not None else start+index*interval
            last_time=timestamp
            if timestamp<start:previous=frame;previous_tensor=None;continue
            while next_time<min(timestamp,end)-1e-6 and len(frames)<720:
                if previous is None:previous=frame
                if previous_tensor is None:previous_tensor=tensor(previous)
                frames.append(previous_tensor);next_time+=1/24
            if timestamp>=end or len(frames)>=720:reached_end=True;break
            previous=frame;previous_tensor=None
            if next_time<=timestamp+1e-6:
                previous_tensor=tensor(frame);frames.append(previous_tensor);next_time+=1/24
        if not reached_end and last_time is not None:end=min(end,last_time+interval)
        while previous is not None and next_time<end-1e-6 and len(frames)<720:
            if previous_tensor is None:previous_tensor=tensor(previous)
            frames.append(previous_tensor);next_time+=1/24
    if not frames:raise ValueError('视频参考片段没有可读取画面')
    return torch.stack(frames)

def current_shot(plan,shot_id):
    shot=compile_shot(plan,shot_id)
    requested=max(5,round(shot['duration']*24))
    from .continuity import MODES,options
    head=options(plan,shot)['context_frames'] if shot['continuity']['mode'] in MODES else 0
    frames=requested+head
    if shot['continuity']['mode'] in ('motion_guide','previous_latent'):
        # The exact prefix phase is known when the previous cache is read.
        # Budget its maximum visible head; do not append a blanket extra chunk.
        frames=requested+max(22,head)+16
    if has_motion_successor(plan,shot_id):
        frames=max(frames,22+17*(frames//17))
    frames+=(5-frames)%17
    return shot,frames,head

def latest_latent(project,shot_id,stage='base',expected=None):
    storage=Storage(data_root())
    rows=[r for r in storage.stages(project) if r['shot']==shot_id and r['stage']==stage]
    if not rows:
        if storage.cache_was_cleared(project,shot_id):raise ValueError('缓存已清除，请重新生成当前镜头以建立缓存，再执行二采／人脸修复：'+shot_id)
        raise ValueError('前一镜头没有可用缓存，请先生成：'+shot_id)
    row=rows[-1]
    if expected is not None and row['fingerprint']!=expected:raise ValueError('前段缓存与当前参数不一致，请先重新生成：'+shot_id)
    return storage.load_latent(project,shot_id,stage,row['version']),row

def previous_guides(latent):
    from comfy.ldm.minimax.model import FRAME_PER_TOKEN
    video=latent['samples'].unbind()[0]
    if video.shape[2]<7:raise ValueError('上一镜头不足 22 帧，不能进行 latent 延续')
    tail=video[:,:,-7:]
    guides=[];position=0
    for i in range(7):
        guides.append({'resolved_frame_index':position,'latent':tail[:,:,i:i+1].clone()})
        position+=FRAME_PER_TOKEN[i%5]
    return guides

class Star7DirectorConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'}),'model':('MODEL',),'clip':('CLIP',),'video_vae':('VAE',),'audio_vae':('VAE',)},'optional':{'prompt_override':('STRING',{'forceInput':True}),'first_frame':('IMAGE',),'last_frame':('IMAGE',)},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('MODEL','CONDITIONING','LATENT','STAR7_H3_REFINE_CONTEXT','INT','BOOLEAN','BOOLEAN','STRING','STRING')
    RETURN_NAMES=('模型','正面条件','音视频潜空间','采样上下文','种子','高清二采','人脸修复','输出前缀','当前镜头')
    FUNCTION='prepare'
    CATEGORY='Star7/导演台'
    @classmethod
    def IS_CHANGED(cls,director_plan,shot_id,**kwargs):return run_fingerprint(director_plan,shot_id,kwargs.get('prompt'))+str(director_plan.get('runtime',{}).get('request_nonce',''))
    def prepare(self,director_plan,shot_id,model,clip,video_vae,audio_vae,prompt=None,prompt_override=None,first_frame=None,last_frame=None):
        import folder_paths
        errors=preflight(director_plan,folder_paths.get_input_directory())
        if errors:raise ValueError('生成前资源检查失败：'+errors[0]['shot']+' / '+errors[0]['source'])
        shot,frames,head=current_shot(director_plan,shot_id)
        from .continuity import check_dependency
        processing=director_plan.get('runtime',{}).get('scope')=='process' and Star7DirectorBaseCache().find(director_plan,shot_id,prompt)[0] is not None
        if processing:
            row,_=Star7DirectorBaseCache().find(director_plan,shot_id,prompt)
            shape=Storage(data_root()).latent_video_shape(director_plan['id'],shot_id,'base',row['version'])
            from .vendor.aimixer.h3_motion_context import pixel_frames_for_latent_t
            frames=pixel_frames_for_latent_t(shape[2])
        from .keyframe_timeline import require_valid,guide_frame
        require_valid(next(s for s in director_plan['shots'] if s['id']==shot_id))
        if not processing:check_dependency(director_plan,shot_id,prompt)
        settings=director_plan.get('settings',{})
        kwargs={}
        previous_pixels=None
        def previous_image():
            nonlocal previous_pixels
            if previous_pixels is None:
                from .core import dependency_source
                from .tail_reference import load
                source=dependency_source(director_plan,shot_id)
                if not source:raise ValueError('此镜头没有上段视频可作为首帧')
                previous_pixels=load(postprocess_source(director_plan,source),director_plan.get('reference_size'))
            return previous_pixels
        kwargs['ref_images']={'ref_image_'+str(i):previous_image() if item.get('from_previous') else load_image(item['source'],director_plan.get('reference_size')) for i,item in enumerate(shot['media']['image'])}
        for i,item in enumerate(shot['media']['audio']):kwargs['ref_audio_'+str(i)]=load_audio(item['source'],float(item.get('start_seconds',0)),float(item.get('duration_seconds',6)))
        # Video soundtracks are intentionally excluded from public audio slots;
        # only explicitly referenced voice/audio cards define <Audio N> labels.
        for i,item in enumerate(shot['media']['video']):
            frames_in=load_video(item['source'],float(item.get('start_seconds',0)),float(item.get('duration_seconds',6)),director_plan.get('reference_size'))
            kwargs['ref_video_'+str(i)]=frames_in
        mode=shot['continuity']['mode']
        motion_keyframes=next(s for s in director_plan['shots'] if s['id']==shot_id).get('input_mode')=='keyframes' and (mode=='motion_guide' or has_motion_successor(director_plan,shot_id))
        endpoint_images={}
        for endpoint,item in shot.get('keyframes',{}).items():
            image=previous_image() if item.get('from_previous') else load_image(item['source'],director_plan.get('reference_size'))
            if motion_keyframes:endpoint_images[endpoint]=image
            else:kwargs[endpoint+'_frame']=image
        if first_frame is not None and mode!='independent':raise ValueError('外接首帧与连续性参考不能同时使用，请选择独立镜头')
        if first_frame is not None:kwargs['first_frame']=first_frame
        if last_frame is not None:kwargs['last_frame']=last_frame
        if mode=='selected_frame':
            from .continuity import source
            info=source(director_plan,shot_id,prompt) if not processing else postprocess_source(director_plan,shot['continuity']['source_shot'])
            selected=self.selected_frame(director_plan['id'],shot['continuity']['source_shot'],shot['continuity']['frame'],info=info)
            from .reference_size import target_size
            import torch.nn.functional as F
            h,w=selected.shape[1:3];size=target_size(w,h,'image',director_plan.get('reference_size'))
            ref=selected if size==(w,h) else F.interpolate(selected.permute(0,3,1,2),size=(size[1],size[0]),mode='bilinear',align_corners=False).permute(0,2,3,1)
            kwargs['ref_images']['ref_image_'+str(shot['continuity_reference']['index'])]=ref
            if prompt_override is not None:
                from .tail_reference import augment_prompt
                prompt_override=augment_prompt(prompt_override,shot['continuity_reference']['label'],frame=shot['continuity']['frame'])
        if mode=='tail_reference':
            from .continuity import source
            from .tail_reference import load
            ref=shot['continuity_reference']
            info=source(director_plan,shot_id,prompt) if not processing else postprocess_source(director_plan,shot['continuity']['source_shot'])
            kwargs['ref_images']['ref_image_'+str(ref['index'])]=load(info,director_plan.get('reference_size'))
            if prompt_override is not None:
                from .tail_reference import augment_prompt
                prompt_override=augment_prompt(prompt_override,ref['label'])
        cls=registry('MiniMaxH3MaterialPromptStar7')
        values=unpack(cls.execute(model,clip,video_vae,audio_vae,prompt_override if prompt_override is not None else shot['prompt'],settings.get('width',960),settings.get('height',544),frames,audio_mode='模型原生生成 / Native',reference_quality='保留高分辨率参考 / Max（显存较高）',**kwargs))
        model,positive,latent,_audio,context,_report=values
        # Face identity must follow a character card, never whichever scene or
        # prop happened to occupy <Picture 1> in the user's prompt.
        context=dict(context)
        from .continuity import MODES,apply
        if mode in MODES and not processing:positive,latent,head=apply(director_plan,shot,positive,latent,video_vae,audio_vae,prompt)
        elif motion_keyframes and processing:
            from .handoff import EXPORT
            saved=Storage(data_root()).latent_info(director_plan['id'],shot_id,'base',row['version'])
            head=int(saved.get(EXPORT,{}).get('trim_frames',head))
        if motion_keyframes:
            from .handoff import EXPORT
            latent={**latent,EXPORT:{**latent.get(EXPORT,{}),'trim_frames':head,'keyframe_timeline':1}}
        context['keyframe_points']=[]
        if shot.get('keyframe_points') or endpoint_images:
            from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide,temporal_shape
            native_frames=temporal_shape(frames)[0]
            for point in shot['keyframe_points']:
                image=load_image(point['source'],director_plan.get('reference_size'))
                index=head+guide_frame(point['time_seconds'],shot['duration'],max(1,round(shot['duration']*24))) if motion_keyframes else guide_frame(point['time_seconds'],shot['duration'],native_frames)
                positive=unpack(MiniMaxH3AddGuide.execute(positive,latent,index,vae=video_vae,image=image))[0]
                context['keyframe_points'].append({'frame_idx':index,'image':image})
            for endpoint,image in endpoint_images.items():
                index=head if endpoint=='first' else head+max(1,round(shot['duration']*24))-1
                positive=unpack(MiniMaxH3AddGuide.execute(positive,latent,index,vae=video_vae,image=image))[0]
                context['keyframe_points'].append({'frame_idx':index,'image':image})
        context['identity_reference']=None
        for card in director_plan['assets']:
            if card['kind']=='character' and card['id'] in shot['labels']:
                character_sources={m['source'] for m in card.get('media',[]) if m['type']=='image'}
                index=next((i for i,m in enumerate(shot['media']['image']) if m['source'] in character_sources),None)
                if index is not None:context['identity_reference']=kwargs['ref_images']['ref_image_'+str(index)];break
        if shot.get('keyframe_points') or shot.get('keyframes'):
            context['positive']=[[tensor,{k:v for k,v in meta.items() if k!='minimax_keyframes'}] for tensor,meta in positive]
        else:context['positive']=positive
        from .handoff import prepare_refinement,restore_prefix
        context['star7_motion_refinement']=lambda output,conditioning:prepare_refinement(output,conditioning,director_plan,shot_id,prompt)
        context['star7_motion_restore']=restore_prefix
        Storage(data_root()).save_project(director_plan)
        identifier(shot_id)
        original=next(s for s in director_plan['shots'] if s['id']==shot_id)
        from .output_paths import output_prefix
        prefix=output_prefix(original.get('name') or shot_id)
        return model,positive,latent,context,shot['seed'],bool(original.get('post',{}).get('hd')),bool(original.get('post',{}).get('face')),prefix,shot_id
    @staticmethod
    def selected_frame(project,source_shot,index,info=None):
        import io,subprocess
        import numpy as np,torch
        from PIL import Image
        store=Storage(data_root())
        record=info['record'] if info else store.latest_output(project,source_shot)
        if record is None:raise ValueError('选帧延续需要上一镜头已保存的视频')
        if index>=record['frame_count']:raise ValueError('选定帧超出上一镜头长度')
        import imageio_ffmpeg
        result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(index/24),'-i',record['path'],'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not result.stdout:raise ValueError('无法读取选定画面')
        with Image.open(io.BytesIO(result.stdout)) as im:return torch.from_numpy(np.array(im.convert('RGB')).astype(np.float32)/255)[None]

class Star7DirectorTrim:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'images':('IMAGE',),'audio':('AUDIO',),'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'})},'optional':{'handoff_latent':('LATENT',)}}
    RETURN_TYPES=('IMAGE','AUDIO','INT')
    RETURN_NAMES=('交付画面','交付音频','交付帧数')
    FUNCTION='trim'
    CATEGORY='Star7/导演台'
    def trim(self,images,audio,director_plan,shot_id,handoff_latent=None):
        _,_,head=current_shot(director_plan,shot_id)
        from .handoff import EXPORT
        if handoff_latent is not None:head=int(handoff_latent.get(EXPORT,{}).get('trim_frames',head))
        if len(images)<=head:raise ValueError('生成视频短于连续性参考头')
        shot=compile_shot(director_plan,shot_id);requested=max(1,round(shot['duration']*24))
        motion_timeline=shot['continuity']['mode']=='motion_guide' or has_motion_successor(director_plan,shot_id)
        if not motion_timeline and (shot.get('keyframes',{}).get('last') or shot.get('keyframe_points')) and len(images)>requested:
            from .endpoint_timing import fit_endpoints
            if head:
                images=images[head:];audio=dict(audio);audio['waveform']=audio['waveform'][...,round(head/24*audio['sample_rate']):]
            result,output=fit_endpoints(images,audio,requested)
            return result,output,len(result)
        result=images[head:head+requested]
        output=dict(audio)
        start=round(head/24*audio['sample_rate'])
        end=start+round(len(result)/24*audio['sample_rate'])
        output['waveform']=audio['waveform'][...,start:end]
        return result,output,len(result)

class Star7DirectorComplete:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'filenames':('STAR7_DIRECTOR_VIDEO',),'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'}),'frame_count':('INT',)},'optional':{'handoff_latent':('LATENT',)},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('STRING',)
    FUNCTION='finish'
    OUTPUT_NODE=True
    CATEGORY='Star7/导演台'
    def finish(self,filenames,director_plan,shot_id,frame_count,prompt=None,handoff_latent=None):
        paths=filenames[1]
        path=next((p for p in reversed(paths) if str(p).lower().endswith(('.mp4','.webm','.mkv'))),None)
        if path is None or not Path(path).is_file():raise ValueError('没有找到本镜头输出视频')
        fingerprint=run_fingerprint(director_plan,shot_id,prompt)
        store=Storage(data_root());base,_=Star7DirectorBaseCache().find(director_plan,shot_id,prompt);original=next(s for s in director_plan['shots'] if s['id']==shot_id)
        from .parameter_state import encode
        previous=store.latest_output(director_plan['id'],shot_id)
        handoff_version=None
        if handoff_latent is not None:
            from .handoff import EXPORT,KEY
            snapshot={k:handoff_latent[k] for k in ('samples',KEY,'star7_face_latent_overlays') if k in handoff_latent}
            snapshot[EXPORT]={**handoff_latent.get(EXPORT,{}),'trim_frames':int(handoff_latent.get(EXPORT,{}).get('trim_frames',current_shot(director_plan,shot_id)[2])),'frame_count':int(frame_count),'base_version':base['version'] if base else None}
            handoff_version=store.save_latent(director_plan['id'],shot_id,'final',fingerprint,snapshot)
            event('handoff_cache_saved',project=director_plan['id'],shot=shot_id,version=handoff_version)
        store.record_output(director_plan['id'],shot_id,fingerprint,str(path),frame_count,post=original.get('post',{}),base_version=base['version'] if base else None,parameter_fingerprint=encode(director_plan,shot_id,previous),handoff_version=handoff_version)
        from .batch_runner import release_after_clip
        release_after_clip(director_plan,shot_id)
        return ('镜头已完成：'+shot_id,)

class Star7DirectorBaseCache:
    def find_for_process(self,plan,sid,prompt):
        row,fingerprint=self.find(plan,sid,prompt)
        if row:return row,fingerprint
        from .parameter_state import baseline,snapshot,visible_changes
        record=Storage(data_root()).latest_output(plan['id'],sid)
        if not record or not record.get('base_version'):return None,None
        old=baseline(plan,sid,record)
        if old is None:return None,None
        changes=visible_changes(old['inputs'],snapshot(plan,sid))
        if any(c['field'] not in ('shot.continuity.drift_control','shot.post.hd','shot.post.face','shot.post.face_count') for c in changes):return None,None
        import copy
        source=copy.deepcopy(plan);drift=old['inputs'].get('drift_control') or {}
        source['continuity_settings']={**source.get('continuity_settings',{}),'drift_control':bool(drift),'drift_strength':drift.get('strength',.3)}
        row,fingerprint=self.find(source,sid,prompt)
        return (row,fingerprint) if row and row['version']==record['base_version'] else (None,None)
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',{'lazy':True}),'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'})},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('LATENT','STRING')
    RETURN_NAMES=('基础采样结果','checkpoint_version')
    FUNCTION='save_or_restore'
    OUTPUT_NODE=True
    CATEGORY='Star7/导演台'
    def find(self,director_plan,shot_id,prompt):
        if director_plan.get('runtime',{}).get('scope')=='process':
            from .batch_runner import approved_pin
            pin=approved_pin(director_plan,shot_id)
            if pin and (data_root()/pin['artifact']).is_file():return pin,pin['fingerprint']
        expected=run_fingerprint(director_plan,shot_id,prompt,stage='base')
        store=Storage(data_root());rows=[r for r in store.stages(director_plan['id']) if r['shot']==shot_id and r['stage']=='base' and (data_root()/r['artifact']).is_file()]
        for row in reversed(rows):
            if row['fingerprint']==expected or store.base_alias_matches(director_plan['id'],shot_id,row['version'],expected):return row,row['fingerprint']
        for old in (run_fingerprint(director_plan,shot_id,prompt,stage='base',legacy_base_dependencies=True),run_fingerprint(director_plan,shot_id,prompt,stage='base',legacy_base_dependencies=True,legacy_dependencies=True)):
            for row in reversed(rows):
                if row['fingerprint']==old:
                    store.alias_base(director_plan['id'],shot_id,row['version'],expected);return row,row['fingerprint']
        identity='semantic:'+run_fingerprint(director_plan,shot_id,prompt,stage='base',parameter_only=True)
        for row in reversed(rows):
            if store.base_alias_matches(director_plan['id'],shot_id,row['version'],identity):return row,row['fingerprint']
        # Recover provenance of older caches from the job which produced the video.
        record=store.latest_output(director_plan['id'],shot_id)
        candidate=next((r for r in rows if record and r['version']==record.get('base_version')),None)
        if candidate:
            for task_path in (data_root()/'projects'/director_plan['id']/'batches').glob('*.json'):
                try:
                    task=json.loads(task_path.read_text(encoding='utf-8'));result=task.get('results',{}).get(shot_id,{})
                    if not result.get('prompt_id') or result.get('path')!=record['path']:continue
                    old_identity='semantic:'+run_fingerprint(task['plan'],shot_id,task['prepared']['output'],stage='base',parameter_only=True)
                    if old_identity==identity:
                        store.alias_base(director_plan['id'],shot_id,candidate['version'],identity);return candidate,candidate['fingerprint']
                except (OSError,ValueError,KeyError,TypeError):continue
        # Old children encoded a predecessor's final file revision. A later HD
        # save changes that file but not its base generation. Match the exact
        # historical revision only when its base provenance is also the same.
        if rows:
            import itertools
            choices=[];source_id=compile_shot(director_plan,shot_id)['continuity'].get('source_shot')
            while source_id and len(choices)<6:
                caches=[r for r in store.stages(director_plan['id']) if r['shot']==source_id and r['stage']=='base' and (data_root()/r['artifact']).is_file()]
                latest=store.latest_output(director_plan['id'],source_id);wanted=(latest or {}).get('base_version') or (caches[-1]['version'] if caches else None);records=[]
                for record in store.output_history(director_plan['id'],source_id):
                    path=Path(record['path'])
                    if not path.is_file():continue
                    version=record.get('base_version')
                    if version is None:
                        before=[r for r in caches if (data_root()/r['artifact']).stat().st_mtime_ns<=path.stat().st_mtime_ns]
                        if before:version=max(before,key=lambda r:(data_root()/r['artifact']).stat().st_mtime_ns)['version']
                    if version and version==wanted:records.append((source_id,record))
                if not records:break
                choices.append(records);source_id=compile_shot(director_plan,source_id)['continuity'].get('source_shot')
            if choices and not source_id:
                for combination in itertools.islice(itertools.product(*choices),64):
                    overrides=dict(combination);old=run_fingerprint(director_plan,shot_id,prompt,stage='base',legacy_base_dependencies=True,dependency_records=overrides)
                    for row in reversed(rows):
                        if row['fingerprint']==old:store.alias_base(director_plan['id'],shot_id,row['version'],expected);return row,row['fingerprint']
        return None,expected
    def check_lazy_status(self,director_plan,shot_id,latent=None,prompt=None):
        row,_=self.find(director_plan,shot_id,prompt)
        scope=director_plan.get('runtime',{}).get('scope','all')
        if scope=='process' and row is None:
            if Storage(data_root()).cache_was_cleared(director_plan['id'],shot_id):raise ValueError('缓存已清除，请重新生成当前镜头以建立缓存，再执行二采／人脸修复')
            raise ValueError('没有参数匹配的基础缓存，请先生成当前镜头')
        if scope!='one' and row is not None:return []
        return ['latent'] if latent is None else []
    def save_or_restore(self,director_plan,shot_id,latent=None,prompt=None):
        store=Storage(data_root());row,fingerprint=self.find(director_plan,shot_id,prompt)
        if director_plan.get('runtime',{}).get('scope','all')!='one' and row is not None:
            latent=store.load_latent(director_plan['id'],shot_id,'base',row['version'],fingerprint)
            event('base_cache_restored',project=director_plan['id'],shot=shot_id,version=row['version'])
            return latent,row['version']
        if latent is None:raise ValueError('基础采样没有返回 latent')
        version=store.save_latent(director_plan['id'],shot_id,'base',fingerprint,latent)
        store.alias_base(director_plan['id'],shot_id,version,'semantic:'+run_fingerprint(director_plan,shot_id,prompt,stage='base',parameter_only=True))
        event('base_cache_saved',project=director_plan['id'],shot=shot_id,version=version)
        return latent,version

class Star7DirectorSamplingModel:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'model':('MODEL',),'latent':('LATENT',),'sigmas':('SIGMAS',)}}
    RETURN_TYPES=('MODEL',)
    FUNCTION='patch'
    CATEGORY='Star7/导演台'
    def patch(self,model,latent,sigmas):
        from .vendor.aimixer.h3_latent_continue import install_continue_prefix_remask
        return (install_continue_prefix_remask(model,dict(latent),sigmas),)

MAPPINGS={c.__name__:c for c in (Star7DirectorConditioning,Star7DirectorTrim,Star7DirectorComplete,Star7DirectorBaseCache,Star7DirectorSamplingModel)}
NAMES=dict(zip(MAPPINGS,('镜头条件桥 - Star7','裁剪衔接参考头 - Star7','镜头完成记录 - Star7','基础缓存与恢复 - Star7','运动衔接采样模型 - Star7')))
