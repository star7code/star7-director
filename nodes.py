import json
from pathlib import Path
from .core import compile_shot, validate, agent_catalog
from .storage import Storage

DATA=Path(__file__).resolve().parent/'data'

def plan(text): return validate(json.loads(text))

class Star7DirectorPlan:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'project_json':('STRING',{'multiline':True,'default':'{"schema_version":"1.0","id":"project","assets":[],"shots":[]}'})},'optional':{'asset_library':('STAR7_DIRECTOR_ASSET_LIBRARY',)}}
    RETURN_TYPES=('STAR7_DIRECTOR_PLAN','STRING')
    RETURN_NAMES=('director_plan','agent_catalog')
    FUNCTION='build'
    CATEGORY='Star7/导演台'
    def build(self,project_json,asset_library=None):
        value=json.loads(project_json)
        value["assets"]=[*value.get("assets",[]),*(asset_library or [])]
        if hasattr(asset_library,"reference_size"):value["reference_size"]=asset_library.reference_size
        validate(value)
        return value,json.dumps(agent_catalog(value),ensure_ascii=False)

class Star7DirectorShot:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'})}}
    RETURN_TYPES=('STRING','FLOAT','INT','STRING','STRING')
    RETURN_NAMES=('prompt','seconds','seed','reference_manifest','continuity_manifest')
    FUNCTION='select'
    CATEGORY='Star7/导演台'
    def select(self,director_plan,shot_id):
        shot_id=director_plan.get('runtime',{}).get('active_shot_id',shot_id)
        shot=compile_shot(director_plan,shot_id)
        return shot['prompt'],shot['duration'],shot['seed'],json.dumps(shot['media'],ensure_ascii=False),json.dumps(shot['continuity'])

class Star7DirectorSaveLatent:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'latent':('LATENT',),'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'}),'stage':(['base','hd','face','final'],)},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('LATENT','STRING')
    RETURN_NAMES=('latent','checkpoint_version')
    FUNCTION='save'
    OUTPUT_NODE=True
    CATEGORY='Star7/导演台'
    def save(self,latent,director_plan,shot_id,stage,prompt=None):
        shot=compile_shot(director_plan,shot_id)
        from .runtime import run_fingerprint
        fingerprint=run_fingerprint(director_plan,shot_id,prompt,stage='base' if stage=='base' else 'final')
        version=Storage(DATA).save_latent(director_plan['id'],shot_id,stage,fingerprint,latent)
        return latent,version

class Star7DirectorLoadLatent:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',{'default':'shot_001'}),'stage':(['base','hd','face','final'],),'version':('STRING',{'default':''})},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('LATENT',)
    FUNCTION='load'
    CATEGORY='Star7/导演台'
    def load(self,director_plan,shot_id,stage,version,prompt=None):
        shot=compile_shot(director_plan,shot_id)
        from .runtime import run_fingerprint
        return (Storage(DATA).load_latent(director_plan['id'],shot_id,stage,version,run_fingerprint(director_plan,shot_id,prompt,stage='base' if stage=='base' else 'final')),)

class Star7DirectorAssetCard:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'card_json':('STRING',{'multiline':True,'default':'{"id":"character_01","kind":"character","name":"人物1","media":[]}'})}}
    RETURN_TYPES=('STAR7_DIRECTOR_ASSET',)
    FUNCTION='build'
    CATEGORY='Star7/导演台/素材'
    def build(self,card_json):
        card=json.loads(card_json)
        check=dict(card)
        check.pop('voice_id',None)
        validate({'schema_version':'1.0','id':'card_validation','assets':[check],'shots':[]})
        return (card,)

class Star7DirectorAssetLibrary:
    @classmethod
    def INPUT_TYPES(cls): return {'required':{'card':('STAR7_DIRECTOR_ASSET',)},'optional':{'library':('STAR7_DIRECTOR_ASSET_LIBRARY',)}}
    RETURN_TYPES=('STAR7_DIRECTOR_ASSET_LIBRARY',)
    FUNCTION='append'
    CATEGORY='Star7/导演台/素材'
    def append(self,card,library=None):
        result=list(library or [])
        if any(a['id']==card['id'] for a in result): raise ValueError('Duplicate material ID')
        return ([*result,card],)

NODE_CLASS_MAPPINGS={cls.__name__:cls for cls in (Star7DirectorPlan,Star7DirectorShot,Star7DirectorSaveLatent,Star7DirectorLoadLatent,Star7DirectorAssetCard,Star7DirectorAssetLibrary)}
NODE_DISPLAY_NAME_MAPPINGS=dict(zip(NODE_CLASS_MAPPINGS,('导演台 - Star7','镜头输入 - Star7','保存镜头缓存 - Star7','载入镜头缓存 - Star7','素材卡 - Star7','素材库汇集 - Star7')))

from .runtime import MAPPINGS,NAMES
NODE_CLASS_MAPPINGS.update(MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(NAMES)

from .desk import Star7DirectorDesk,Star7DirectorLibrary
NODE_CLASS_MAPPINGS.update(Star7DirectorDesk=Star7DirectorDesk,Star7DirectorLibrary=Star7DirectorLibrary)
NODE_DISPLAY_NAME_MAPPINGS.update(Star7DirectorDesk="导演台工作站 - Star7",Star7DirectorLibrary="项目素材库 - Star7")
