import copy,importlib,sys,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('voice_fallback_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core')
def plan():
 return {'schema_version':'1.0','id':'voice_test','assets':[{'id':'a','kind':'character','name':'小可','voice_id':'v','media':[{'type':'image','source':'a.png'}]},{'id':'v','kind':'voice','name':'小可音色','aliases':['声音'],'media':[{'type':'audio','source':'v.wav'}]}],'shots':[{'id':'s','duration':5,'prompt':'@{小可} speaks.'}]}
class Tests(unittest.TestCase):
 def test_missing_voice_is_inline_without_inferred_speaker(self):
  p=plan();before=copy.deepcopy(p);out=core.compile_shot(p,'s');self.assertEqual(out['prompt'],'<Picture 1> <Audio 1> speaks.');self.assertEqual(p,before);self.assertEqual(len(out['media']['audio']),1)
 def test_explicit_voice_anywhere_prevents_fallback_and_keeps_authored_format(self):
  for name in ('v','小可音色','声音'):
   p=plan();p['shots'][0]['prompt']='subject_definitions:\n<Subject 2> is @{a}.\n@{'+name+'} supplies the voice of <Subject 2> (S1).\nsummary:\nTalk.\nretention_analysis:\n@{'+name+'}: reference - retain timbre.\ndetailed_description:\n<Subject 2> (S1) says: <d>[Chinese] 你好。</d>'
   out=core.compile_shot(p,'s');self.assertNotIn('<Picture 1> <Audio',out['prompt']);self.assertIn('<Audio 1> supplies the voice of <Subject 2> (S1).',out['prompt']);self.assertEqual(out['prompt'].count('<Audio 1>'),2);self.assertEqual(len(out['media']['audio']),1)
 def test_explicit_nested_text_and_custom_prompt(self):
  p=plan();p['assets'].append({'id':'style','kind':'effect','name':'声音说明','description':'Use @{v} for voice timbre.','media':[]});p['shots'][0]['prompt']+=' @{style}'
  self.assertNotIn('<Picture 1> <Audio',core.compile_shot(p,'s')['prompt'])
  p=plan();p['prompt_options']={'custom_prompt':'Voice: @{v}','custom_prompt_enabled':True};self.assertNotIn('<Picture 1> <Audio',core.compile_shot(p,'s')['prompt'])
 def test_distinct_people_and_shared_audio(self):
  p=plan();p['assets'].extend([{'id':'b','kind':'character','name':'小洛','voice_id':'w','media':[{'type':'image','source':'b.png'}]},{'id':'w','kind':'voice','name':'小洛音色','media':[{'type':'audio','source':'w.wav'}]}]);p['shots'][0]['prompt']='@{a} and @{b}; @{v} belongs to the first speaker.'
  out=core.compile_shot(p,'s');self.assertIn('<Picture 1> and <Picture 2> <Audio 2>',out['prompt']);self.assertEqual(len(out['media']['audio']),2)
  p['assets'][2]['voice_id']='v';out=core.compile_shot(p,'s');self.assertNotIn('<Picture 2> <Audio',out['prompt']);self.assertEqual(len(out['media']['audio']),1)
 def test_catalog_carries_bound_voice(self):
  p=plan();self.assertEqual(core.agent_catalog(p)['assets'][0]['voice_id'],'v')
if __name__=='__main__':unittest.main()
