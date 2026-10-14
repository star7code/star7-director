"""Graph-local phase notifications; no sampler or server monkey-patches."""
class Star7DirectorLivePreview:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'model':('MODEL',),'director_plan':('STAR7_DIRECTOR_PLAN',)},'hidden':{'unique_id':'UNIQUE_ID'}}
    RETURN_TYPES=('MODEL',)
    FUNCTION='patch'
    CATEGORY='Star7/导演台'
    def patch(self,model,director_plan,unique_id=None):
        from .desk import preview_spec
        from .runtime import registry,unpack
        values=preview_spec(director_plan)['inputs'];values={k:v for k,v in values.items() if k!='model'}
        cls=registry('MiniMaxH3LivePreviewStar7')
        return unpack(getattr(cls(),cls.FUNCTION)(model=model,unique_id=unique_id,**values))

class Star7DirectorStage:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',),'director_plan':('STAR7_DIRECTOR_PLAN',),'shot_id':('STRING',),'phase':(['base','hd','face','decode'],)},'hidden':{'unique_id':'UNIQUE_ID'}}
    RETURN_TYPES=('LATENT',)
    FUNCTION='mark'
    CATEGORY='Star7/导演台'
    def mark(self,latent,director_plan,shot_id,phase,unique_id=None):
        from .batch_runner import mark
        mark(director_plan,shot_id,phase,unique_id);return (latent,)
