"""Two-node director with a private execution plan, not extra canvas nodes."""
import copy,json,time,logging
from pathlib import Path
from .core import validate,compile_plan
from .run_logging import DirectorExecutionError,STAGES,event

TEMPLATE=Path(__file__).with_name('pipeline.json')

def template():return json.loads(TEMPLATE.read_text(encoding='utf-8'))

class Star7DirectorPlan:
    """Private plan value; deliberately absent from NODE_CLASS_MAPPINGS."""
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'project_json':('STRING',)}}
    FUNCTION='build'
    def build(self,project_json):return (validate(json.loads(project_json)),)

class _Step:
    def __init__(self,plan,key,class_type,inputs):self.plan=plan;self.key=key;self.spec={'class_type':class_type,'inputs':inputs}
    def out(self,index):return [self.key,index]
    def set_input(self,name,value):self.spec['inputs'][name]=value

class _ExecutionPlan:
    def __init__(self,prefix):self.prefix=prefix;self.steps={}
    def node(self,class_type,id,**inputs):
        step=_Step(self,self.prefix+id,class_type,inputs);self.steps[id]=step;return step
    def lookup_node(self,key):return self.steps[key]
    def finalize(self):return {step.key:step.spec for step in self.steps.values()}

def merge_library(plan,library):
    result=copy.deepcopy(plan)
    if library is not None:
        result['assets']=copy.deepcopy(list(library))
        if hasattr(library,'reference_size'):result['reference_size']=copy.deepcopy(library.reference_size)
    cfg=result.get('generation',{}).get('376',{})
    cfg.pop('upscale_method',None)
    if cfg.get('upscale_model')=='像素插值（Lanczos）':
        cfg['upscale_model']='minimax_h3_latent_upscaler_3d_fp16.safetensors'
    validate(result)
    return result

def preview_spec(plan):
    from .runtime import registry
    cls=registry('MiniMaxH3LivePreviewStar7');schema=cls.INPUT_TYPES()
    defs={**schema.get('required',{}),**schema.get('optional',{})}
    values={name:(definition[1].get('default') if len(definition)>1 and 'default' in definition[1] else definition[0][0] if isinstance(definition[0],list) else None) for name,definition in defs.items() if name!='model'}
    overrides=plan.get('preview',{})
    if not isinstance(overrides,dict):raise ValueError('实时预览设置无效')
    for name,value in overrides.items():
        if name not in values:raise ValueError('无效实时预览参数：'+name)
        typ=defs[name][0];options=defs[name][1] if len(defs[name])>1 else {}
        if isinstance(typ,list) and value not in typ or typ=='BOOLEAN' and not isinstance(value,bool) or typ=='INT' and (isinstance(value,bool) or not isinstance(value,int) or value<options.get('min',value) or value>options.get('max',value)):raise ValueError('实时预览参数超出范围：'+name)
        values[name]=value
    return {'class_type':'MiniMaxH3LivePreviewStar7','inputs':{'model':['363',0],**values}}

def internal_graph(plan,shot_id,ports,prefix):
    from comfy_execution.graph_utils import is_link
    from .runtime import registry
    plan=merge_library(plan,None)
    if shot_id not in {s['id'] for s in plan['shots']}:raise ValueError('请选择一个已有镜头')
    graph=_ExecutionPlan(prefix=prefix)
    full_specs=template();specs=copy.deepcopy(full_specs)
    preview=preview_spec(plan)
    if preview['inputs']['preview_enabled']:
        specs['605']={'class_type':'Star7DirectorLivePreview','inputs':{'model':['363',0],'director_plan':['600',0]}};specs['601']['inputs']['model']=['605',0]
    shot=next(s for s in plan['shots'] if s['id']==shot_id)
    post=shot.get('post',{});aliases={}
    if not post.get('hd',False):specs.pop('376');aliases['376']=('602',0)
    if not post.get('face',False):specs.pop('395');aliases['395']=('376' if post.get('hd',False) else '602',0)
    def phase_node(key,phase,source):
        specs[key]={'class_type':'Star7DirectorStage','inputs':{'latent':source,'director_plan':['600',0],'shot_id':shot_id,'phase':phase}}
    phase_node('607','base',specs['127']['inputs']['latent_image']);specs['127']['inputs']['latent_image']=['607',0]
    for key,nid,phase,field in (('608','376','hd','sampled_av_latent'),('609','395','face','sampled_av_latent'),('610','377','decode','av_latent')):
        if nid in specs:
            source=specs[nid]['inputs'][field];phase_node(key,phase,source);specs[nid]['inputs'][field]=[key,0]
    overrides=plan.get('generation',{})
    if not isinstance(overrides,dict):raise ValueError('生成设置必须是对象')
    for key,values in overrides.items():
        if key not in full_specs or not isinstance(values,dict):raise ValueError('无效生成设置')
        for name,value in values.items():
            import math
            if not isinstance(value,(str,int,float,bool)) or isinstance(value,float) and not math.isfinite(value):raise ValueError('生成参数必须是有效标量：'+name)
            if name not in full_specs[key]['inputs'] or isinstance(full_specs[key]['inputs'][name],list):raise ValueError('不允许覆盖内部连接：'+name)
    for key,spec in specs.items():
        cls=registry(spec['class_type'])
        defs=cls.INPUT_TYPES();definitions={**defs.get('required',{}),**defs.get('optional',{})}
        for name in spec['inputs']:
            if name not in definitions:raise ValueError('节点接口需要适配：'+spec['class_type']+' / '+name)
        graph.node(spec['class_type'],id=key)
    planner=graph.node('Star7DirectorPlan',id='600',project_json=json.dumps(plan,ensure_ascii=False))
    externals={'363':ports['model'],'130':ports['clip'],'121':ports['video_vae'],'122':ports['audio_vae']}
    for key,spec in specs.items():
        target=graph.lookup_node(key)
        for name,value in spec['inputs'].items():
            if is_link(value):
                source,index=value
                while source in aliases:source,index=aliases[source]
                value=externals[source] if source in externals else graph.lookup_node(source).out(index)
            elif name=='shot_id':value=shot_id
            elif key in overrides and name in overrides[key]:value=overrides[key][name]
            if key=='395' and name=='face_count' and 'face_count' in post:value=post['face_count']
            target.set_input(name,value)
    return graph.finalize(),graph.lookup_node('604').out(0)

def validate_execution_plan(graph):
    from .runtime import registry
    from comfy_execution.graph_utils import is_link
    for key,spec in graph.items():
        definitions=registry(spec['class_type']).INPUT_TYPES()
        definitions={**definitions.get('required',{}),**definitions.get('optional',{})}
        for name,value in spec['inputs'].items():
            if is_link(value):continue
            definition=definitions[name];kind=definition[0];limits=definition[1] if len(definition)>1 else {}
            if isinstance(kind,list) and value not in kind:raise ValueError('内部设置不支持该选项：'+name+' = '+str(value))
            if kind in ('INT','FLOAT'):
                if isinstance(value,bool) or not isinstance(value,(int,float)) or kind=='INT' and not isinstance(value,int):raise ValueError('内部设置需要有效数字：'+name)
                if value<limits.get('min',value) or value>limits.get('max',value):raise ValueError('内部设置超出范围：'+name)
            if kind=='BOOLEAN' and not isinstance(value,bool):raise ValueError('内部设置需要布尔值：'+name)

def execute_internal(graph,result,plan,shot_id,prompt=None):
    from .runtime import registry,unpack
    from comfy_execution.graph_utils import is_link
    import comfy.model_management
    values={};ui={};active=set()
    def resolve(value):return run(value[0])[value[1]] if is_link(value) and value[0] in graph else value
    def run(key):
        if key in values:return values[key]
        if key in active:raise ValueError('Director execution plan contains a cycle')
        active.add(key);spec=graph[key];started=None
        stage=STAGES.get(key.rsplit('.',1)[-1],spec['class_type'])
        context={'project':plan.get('id'),'shot':shot_id,'stage':stage,'node':key}
        try:
            cls=registry(spec['class_type']);obj=cls()
            comfy.model_management.throw_exception_if_processing_interrupted()
            lazy=spec['class_type']=='Star7DirectorBaseCache' and not obj.check_lazy_status(plan,shot_id,prompt=prompt)
            inputs={name:resolve(value) for name,value in spec['inputs'].items() if not (lazy and name=='latent')}
            hidden=cls.INPUT_TYPES().get('hidden',{})
            for name,kind in hidden.items():
                if kind=='PROMPT':inputs[name]=prompt
                elif kind=='UNIQUE_ID':inputs[name]=key
            started=time.perf_counter()
            if stage in STAGES.values():event('step_start',**context)
            output=getattr(obj,cls.FUNCTION)(**inputs)
            if isinstance(output,dict):
                for name,items in output.get('ui',{}).items():ui.setdefault(name,[]).extend(items)
            values[key]=unpack(output)
            if stage in STAGES.values():event('step_complete',**context,seconds=round(time.perf_counter()-started,3))
            return values[key]
        except Exception as error:
            if isinstance(error,DirectorExecutionError):raise
            if isinstance(error,comfy.model_management.InterruptProcessingException):
                if started is not None:event('step_interrupted',**context,seconds=round(time.perf_counter()-started,3))
                raise
            event('step_failed',level=logging.ERROR,**context,error_type=type(error).__name__,error=str(error),
                  seconds=round(time.perf_counter()-started,3) if started is not None else None)
            raise DirectorExecutionError(stage,key,error) from error
        finally:active.remove(key)
    report=resolve(result)
    return {'result':(report,),'ui':ui}

class Star7DirectorDesk:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'project_json':('STRING',{'multiline':True,'default':'{"schema_version":"1.0","id":"project","assets":[],"shots":[]}'})},'optional':{'model':('MODEL',),'clip':('CLIP',),'video_vae':('VAE',),'audio_vae':('VAE',),'asset_library':('STAR7_DIRECTOR_ASSET_LIBRARY',)},'hidden':{'unique_id':'UNIQUE_ID','prompt':'PROMPT'}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('运行报告',)
    OUTPUT_NODE=True
    FUNCTION='generate'
    CATEGORY='Star7/导演台'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def generate(self,project_json,model=None,clip=None,video_vae=None,audio_vae=None,asset_library=None,unique_id=None,prompt=None):
        document=json.loads(project_json)
        if document.get('star7_action')=='export':
            from .export_node import Star7DirectorVideoExport
            return Star7DirectorVideoExport().save(document['export_json'])
        if any(value is None for value in (model,clip,video_vae,audio_vae)):raise ValueError('生成需要连接模型、文本编码器、视频 VAE 和音频 VAE；导出已有视频不需要这些输入')
        plan=merge_library(document,asset_library)
        from .native_execution import execution
        with execution(plan,prompt,unique_id) as request:
            return self.generate_plan(request,model,clip,video_vae,audio_vae,unique_id,prompt)

    def generate_plan(self,plan,model,clip,video_vae,audio_vae,unique_id,prompt):
        compile_plan(plan)
        shot_id=plan.get('runtime',{}).get('active_shot_id') or (plan['shots'][0]['id'] if plan['shots'] else None)
        if shot_id is None:raise ValueError('请先添加镜头')
        from .keyframe_timeline import require_valid
        require_valid(next(s for s in plan['shots'] if s['id']==shot_id))
        from .handoff import check_request
        check_request(plan,shot_id,prompt,processing=plan.get('runtime',{}).get('scope')=='process')
        from .continuity import check_dependency
        if plan.get('runtime',{}).get('scope')!='process':check_dependency(plan,shot_id,prompt)
        if plan.get('runtime',{}).get('scope')=='process':
            from .runtime import Star7DirectorBaseCache
            if Star7DirectorBaseCache().find(plan,shot_id,prompt)[0] is None:raise ValueError('没有与当前参数匹配的基础缓存，请先生成当前镜头')
        graph,result=internal_graph(plan,shot_id,dict(model=model,clip=clip,video_vae=video_vae,audio_vae=audio_vae),str(unique_id)+'.director.'+str(plan.get('runtime',{}).get('request_nonce','manual'))+'.')
        return execute_internal(graph,result,plan,shot_id,prompt)

class Star7DirectorLibrary:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'library_json':('STRING',{'multiline':True,'default':'{"assets":[]}'})}}
    RETURN_TYPES=('STAR7_DIRECTOR_ASSET_LIBRARY',)
    RETURN_NAMES=('素材库',)
    FUNCTION='build'
    CATEGORY='Star7/导演台/素材'
    def build(self,library_json):
        data=json.loads(library_json);assets=data.get('assets',[])
        from .reference_size import AssetLibrary
        assets=AssetLibrary(assets,data.get('reference_size'))
        validate({'schema_version':'1.0','id':'library','assets':assets,'shots':[]})
        return (assets,)
