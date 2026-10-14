import ast,importlib,sys,types,unittest,tempfile,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('director_preview_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
desk=importlib.import_module(pkg.__name__+'.desk');runtime=importlib.import_module(pkg.__name__+'.runtime')
tree=ast.parse((ROOT.parent/'minimax-h3-chunk-star7/h3_live_preview.py').read_text(encoding='utf-8'))
node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MiniMaxH3LivePreviewStar7');env={'TAEH3_FILENAME':'taeh3.safetensors','_preview_model_choices':lambda:['taeh3.safetensors','other.safetensors']};exec(compile(ast.Module(body=[node],type_ignores=[]),'h3_live_preview.py','exec'),env);Preview=env['MiniMaxH3LivePreviewStar7']
class Tests(unittest.TestCase):
 def registry(self,name):
  if name=='MiniMaxH3LivePreviewStar7':return Preview
  if name=='Star7DirectorLivePreview':return importlib.import_module(pkg.__name__+'.stage').Star7DirectorLivePreview
  if name=='Star7DirectorStage':
   return type('StageSchema',(),{'INPUT_TYPES':classmethod(lambda cls:{'required':{k:('ANY',{}) for k in ('latent','director_plan','shot_id','phase')}})})
  keys={k for spec in desk.template().values() if spec['class_type']==name for k in spec['inputs']}
  return type('Schema',(),{'INPUT_TYPES':classmethod(lambda cls:{'required':{k:('ANY',{}) for k in keys}})})
 def test_graph_and_limits(self):
  plan={'schema_version':'1.0','id':'test','assets':[],'shots':[{'id':'s1','prompt':'garden','duration':2,'seed':7}]}
  ports={k:['external_'+k,0] for k in ('model','clip','video_vae','audio_vae')}
  with patch.object(runtime,'registry',side_effect=self.registry):
   plan['preview']={'preview_fps':8,'preview_resolution':'768','preview_quality':90,'first_step_only':True}
   graph,_=desk.internal_graph(plan,'s1',ports,'10.director.nonce.')
   preview=graph['10.director.nonce.605'];self.assertEqual(preview['class_type'],'Star7DirectorLivePreview');self.assertEqual(preview['inputs']['director_plan'],['10.director.nonce.600',0]);self.assertEqual(preview['inputs']['model'],ports['model']);self.assertEqual(graph['10.director.nonce.601']['inputs']['model'],['10.director.nonce.605',0])
   plan['preview']['preview_enabled']=False;graph,_=desk.internal_graph(plan,'s1',ports,'10.director.next.');self.assertNotIn('10.director.next.605',graph);self.assertEqual(graph['10.director.next.601']['inputs']['model'],ports['model'])
   for invalid in ({'preview_fps':25},{'preview_quality':0},{'preview_enabled':1},{'preview_resolution':'999'},{'preview_model':'unknown'}):
    plan['preview']=invalid
    with self.assertRaises(ValueError):desk.internal_graph(plan,'s1',ports,'test.')
 def test_preview_does_not_invalidate_cache(self):
  p={'schema_version':'1.0','id':'test','assets':[],'shots':[{'id':'s1','prompt':'garden','seed':7,'duration':2}]};prompt={'1':{'class_type':'Star7DirectorDesk','inputs':{}},'2':{'class_type':'MiniMaxH3LivePreviewStar7','inputs':{'preview_fps':5}}}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as td,patch.object(runtime,'data_root',return_value=Path(td)):
   final=runtime.run_fingerprint(p,'s1',prompt);base=runtime.run_fingerprint(p,'s1',prompt,'base');p['preview']={'preview_fps':24,'preview_enabled':False};prompt['2']['inputs']['preview_fps']=24
   self.assertEqual(final,runtime.run_fingerprint(p,'s1',prompt));self.assertEqual(base,runtime.run_fingerprint(p,'s1',prompt,'base'))
 def test_preview_adapter_binds_each_current_job_id(self):
  stage=importlib.import_module(pkg.__name__+'.stage');calls=[]
  class FakePreview:
   FUNCTION='patch'
   INPUT_TYPES=Preview.INPUT_TYPES
   def patch(self,**kwargs):calls.append(kwargs);return (kwargs['model'],)
  plan={'preview':{'preview_fps':8}}
  with patch.object(runtime,'registry',return_value=FakePreview):
   stage.Star7DirectorLivePreview().patch('model',plan,'10.director.first.605')
   stage.Star7DirectorLivePreview().patch('model',plan,'10.director.second.605')
  self.assertEqual([v['unique_id'] for v in calls],['10.director.first.605','10.director.second.605']);self.assertEqual(calls[1]['preview_fps'],8)
if __name__=='__main__':unittest.main()
