import copy,importlib,sys,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('description_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core');state=importlib.import_module(pkg.__name__+'.parameter_state')
def plan():
 return {'schema_version':'1.0','id':'description_test','assets':[{'id':'actor','kind':'character','name':'小可','description':'wearing a white apron','voice_id':'voice','media':[{'type':'image','source':'actor.png'}]},{'id':'voice','kind':'voice','name':'音色','media':[{'type':'audio','source':'voice.wav','start_seconds':1,'duration_seconds':3}]}],'shots':[{'id':'s','prompt':'@{小可} walks.','duration':5,'seed':666}]}
class Tests(unittest.TestCase):
 def test_off_on_and_preservation(self):
  p=plan();before=copy.deepcopy(p);old=core.compile_shot(p,'s');self.assertNotIn('white apron',old['prompt']);p['assets'][0]['inject_description']=False;self.assertEqual(old,core.compile_shot(p,'s'))
  p['assets'][0]['inject_description']=True;out=core.compile_shot(p,'s');self.assertIn('<Picture 1> <Audio 1> wearing a white apron walks.',out['prompt']);self.assertEqual(len(out['media']['image']),1);self.assertEqual(len(out['media']['audio']),1);self.assertNotIn('小可音色：',out['prompt']);self.assertEqual(p['shots'],before['shots'])
  self.assertEqual(out['media']['audio'][0]['start_seconds'],1);self.assertEqual(out['media']['audio'][0]['duration_seconds'],3)
  self.assertEqual(core.agent_catalog(p)['assets'][0]['description'],'wearing a white apron');self.assertTrue(core.agent_catalog(p)['assets'][0]['inject_description'])
 def test_plain_text_always_expands_and_nested_description(self):
  p=plan();p['assets'].append({'id':'style','kind':'effect','name':'风格','description':'soft daylight','media':[]});p['assets'][0]['description']='white apron, @{style}';p['assets'][0]['inject_description']=True
  self.assertIn('<Picture 1> <Audio 1> white apron, soft daylight',core.compile_shot(p,'s')['prompt'])
  p['assets'][0]['media']=[];p['assets'][0]['inject_description']=False;out=core.compile_shot(p,'s');self.assertIn('white apron, soft daylight <Audio 1> walks.',out['prompt']);self.assertEqual(out['media']['image'],[]);self.assertEqual(len(out['media']['audio']),1)
 def test_cycles_only_rejected_when_description_is_consumed(self):
  p=plan();p['assets'][0]['description']='@{actor}';core.compile_shot(p,'s');p['assets'][0]['inject_description']=True
  with self.assertRaisesRegex(ValueError,'循环'):core.compile_shot(p,'s')
 def test_only_effective_description_counts_as_parameter_change(self):
  p=plan();old=state.snapshot(p,'s');p['assets'][0]['description']='wearing a red apron';self.assertEqual(state.visible_changes(old,state.snapshot(p,'s')),[])
  p['assets'][0]['inject_description']=True;changes=state.visible_changes(old,state.snapshot(p,'s'));self.assertEqual([c['field'] for c in changes],['assets.actor.description'])
 def test_keyframes_do_not_inject_invalid_picture_description(self):
  p=plan();p['assets'][0]['inject_description']=True;p['shots'][0].update(input_mode='keyframes',keyframes={'first':{'source':'first.png'}})
  out=core.compile_shot(p,'s');self.assertNotIn('white apron',out['prompt']);self.assertEqual(out['media']['image'],[]);self.assertEqual(len(out['media']['audio']),1)
 def test_standard_subject_voice_binding(self):
  p=plan();p['assets'][0]['inject_description']=True;p['shots'][0]['prompt']='subject_definitions:\n<Subject 1> is Xiao Ke using @{actor}.\nsummary:\nTalk.'
  out=core.compile_shot(p,'s');self.assertIn('<Picture 1> <Audio 1> wearing a white apron',out['prompt']);self.assertNotIn('voice timbre for',out['prompt'])
if __name__=='__main__':unittest.main()
