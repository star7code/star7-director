"""Canvas director: expand the existing registered pipeline, no duplicate sampler."""
import copy,json
from pathlib import Path
from .core import validate,compile_plan

TEMPLATE=Path(__file__).with_name('pipeline.json')

def template():return json.loads(TEMPLATE.read_text(encoding='utf-8'))

def merge_library(plan,library):
    result=copy.deepcopy(plan)
    if library is not None:
        result['assets']=copy.deepcopy(list(library))
        if hasattr(library,'reference_size'):result['reference_size']=copy.deepcopy(library.reference_size)
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
    from comfy_execution.graph_utils import GraphBuilder,is_link
    from .runtime import registry
    plan=merge_library(plan,None)
    if shot_id not in {s['id'] for s in plan['shots']}:raise ValueError('请选择一个已有镜头')
    graph=GraphBuilder(prefix=prefix)
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
        if spec['class_type'] in ('VHS_VideoCombine','Star7DirectorSaveVideo'):
            fmt=definitions.get('format',('',{}))[1].get('formats',{}).get(spec['inputs']['format'],[])
            definitions.update({item[0]:item[1:] for item in fmt})
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

class Star7DirectorDesk:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'model':('MODEL',{'rawLink':True}),'clip':('CLIP',{'rawLink':True}),'video_vae':('VAE',{'rawLink':True}),'audio_vae':('VAE',{'rawLink':True}),'project_json':('STRING',{'multiline':True,'default':'{"schema_version":"1.0","id":"project","assets":[],"shots":[]}'})},'optional':{'asset_library':('STAR7_DIRECTOR_ASSET_LIBRARY',)},'hidden':{'unique_id':'UNIQUE_ID','prompt':'PROMPT'}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('运行报告',)
    OUTPUT_NODE=True
    FUNCTION='generate'
    CATEGORY='Star7/导演台'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def generate(self,model,clip,video_vae,audio_vae,project_json,asset_library=None,unique_id=None,prompt=None):
        plan=merge_library(json.loads(project_json),asset_library)
        compile_plan(plan)
        shot_id=plan.get('runtime',{}).get('active_shot_id') or (plan['shots'][0]['id'] if plan['shots'] else None)
        from .continuity import check_dependency
        if plan.get('runtime',{}).get('scope')!='process':check_dependency(plan,shot_id,prompt)
        if plan.get('runtime',{}).get('scope')=='process':
            from .runtime import Star7DirectorBaseCache
            if Star7DirectorBaseCache().find(plan,shot_id,prompt)[0] is None:raise ValueError('没有与当前参数匹配的基础缓存，请先生成当前镜头')
        graph,result=internal_graph(plan,shot_id,dict(model=model,clip=clip,video_vae=video_vae,audio_vae=audio_vae),str(unique_id)+'.director.'+str(plan.get('runtime',{}).get('request_nonce','manual'))+'.')
        return {'result':(result,),'expand':graph}

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
