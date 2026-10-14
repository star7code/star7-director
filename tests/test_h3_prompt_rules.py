import unittest,sys,types,importlib,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));pkg=types.ModuleType('h3_rules_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core');story=importlib.import_module(pkg.__name__+'.storyboard')
def plan(prompt):return {'schema_version':'1.0','id':'p','assets':[{'id':'actor','kind':'character','name':'小可','media':[{'type':'image','source':'a.png'}]},{'id':'deer','kind':'character','name':'小鹿','media':[{'type':'image','source':'b.png'}]}],'shots':[{'id':'s','duration':5,'prompt':prompt}]}
class Tests(unittest.TestCase):
 def test_custom_prompt_toggle_retains_text_but_ignores_disabled_references(self):
  import json
  p=plan('A classroom.');plain=core.compile_shot(p,'s')['fingerprint']
  p['prompt_options']={'custom_prompt_enabled':True,'custom_prompt':'Soft light.'}
  enabled=core.compile_shot(p,'s');self.assertIn('Soft light.',enabled['prompt'])
  p['prompt_options']['custom_prompt_enabled']=False
  saved=json.loads(json.dumps(p));self.assertEqual(saved['prompt_options']['custom_prompt'],'Soft light.');self.assertFalse(saved['prompt_options']['custom_prompt_enabled']);self.assertEqual(core.compile_shot(saved,'s')['fingerprint'],plain)
  p['prompt_options']['custom_prompt']='Use @{missing}.';self.assertEqual(core.compile_shot(p,'s')['fingerprint'],plain)
  p['prompt_options'].update(custom_prompt_enabled=True,custom_prompt='Soft light.');self.assertEqual(core.compile_shot(p,'s')['fingerprint'],enabled['fingerprint'])
 def test_custom_prompt_refs_fingerprint_revert_and_readable_changes(self):
  p=plan('A classroom.');before=copy.deepcopy(p);old=core.compile_shot(p,'s')['fingerprint']
  parameter=importlib.import_module(pkg.__name__+'.parameter_state');baseline=parameter.snapshot(p,'s')
  p['prompt_options']={'custom_prompt':'Soft light.\nUse @{小可}.'}
  result=core.compile_shot(p,'s');self.assertIn('Soft light.',result['prompt']);self.assertNotIn('@{小可}',result['prompt']);self.assertNotEqual(result['fingerprint'],old);self.assertEqual(p['shots'],before['shots'])
  changes=parameter.visible_changes(baseline,parameter.snapshot(p,'s'));self.assertTrue(any(c['field']=='shot.prompt_options.custom_prompt' for c in changes));self.assertFalse(any(c['field']=='shot.prompt' for c in changes))
  p['prompt_options']['custom_prompt']='';self.assertEqual(core.compile_shot(p,'s')['fingerprint'],old);self.assertEqual(parameter.visible_changes(baseline,parameter.snapshot(p,'s')),[])
 def test_global_no_subtitles_all_shots_and_legacy_precedence(self):
  p=plan('garden');p['assets']=[];p['shots'].append({'id':'s2','duration':3,'prompt':'continue','continuity':{'mode':'motion_guide','source_shot':'s'}});before=copy.deepcopy(p)
  p['prompt_options']={'no_subtitles':True};self.assertTrue(all(s['prompt'].endswith('Screen: no subtitles, no on-screen text, no watermark.') for s in core.compile_plan(p)));self.assertEqual(p['shots'],before['shots'])
  legacy=copy.deepcopy(before);legacy['shots'][0]['prompt_options']={'no_subtitles':True};self.assertEqual(core.compile_shot(legacy,'s')['fingerprint'],core.compile_shot(p,'s')['fingerprint'])
  legacy['prompt_options']={'no_subtitles':False};self.assertNotIn('Screen:',core.compile_shot(legacy,'s')['prompt']);self.assertEqual(core.compile_shot(legacy,'s')['fingerprint'],core.compile_shot(before,'s')['fingerprint'])
  p['prompt_options']={'no_subtitles':'true'}
  with self.assertRaises(ValueError):core.compile_plan(p)
 def test_names_and_dialogue_literals(self):
  text='subject_definitions: <Subject 1> is @{小可}.\nsummary: [reference generation] a classroom shot.\nretention_analysis: <Subject 1>: fully_preserved - keep clothing.\ndetailed_description: [Shot 1] <Subject 1> (S1) says <d>[Chinese] 请发邮件到a@example.com，名字是@小鹿。</d>\noverall_soundscape: quiet room.\nnon_diegetic_music: N/A'
  p=plan(text);compiled=core.compile_shot(p,'s');self.assertIn('<Picture 1>',compiled['prompt']);self.assertIn('a@example.com，名字是@小鹿',compiled['prompt']);self.assertEqual(len(compiled['media']['image']),1)
  import json
  result=story.recognize(p,json.dumps({'shots':[{'duration':5,'prompt':text}]},ensure_ascii=False),'replace');self.assertTrue(result['valid'],result);self.assertIn('@{actor}',result['rows'][0]['prompt']);self.assertIn('@小鹿',result['rows'][0]['model_prompt']);self.assertFalse(any('缺少H3标准字段' in w for w in result['warnings']))
 def test_no_subtitle_injection_is_runtime_only(self):
  p=plan('@{小可} walks.');before=copy.deepcopy(p);self.assertNotIn('Screen:',core.compile_shot(p,'s')['prompt']);p['shots'][0]['prompt_options']={'no_subtitles':True};out=core.compile_shot(p,'s')['prompt'];self.assertTrue(out.endswith('Screen: no subtitles, no on-screen text, no watermark.'));self.assertEqual(p['shots'][0]['prompt'],before['shots'][0]['prompt']);self.assertNotEqual(core.compile_shot(p,'s')['fingerprint'],core.compile_shot(before,'s')['fingerprint'])
  p['shots'][0]['prompt']+='\nScreen: no subtitles, no on-screen text, no watermark.';self.assertEqual(core.compile_shot(p,'s')['prompt'].count('Screen: no subtitles'),1)
 def test_speech_markup_and_legacy_warning(self):
  import json
  p=plan('garden');bad=story.recognize(p,json.dumps({'shots':[{'duration':5,'prompt':'says <d>[Chinese] hello'}]}),'replace');self.assertFalse(bad['valid']);self.assertIn('闭合',bad['errors'][0]['message']);plain=story.recognize(p,'{"shots":[{"duration":5,"prompt":"garden"}]}','replace');self.assertTrue(plain['valid']);self.assertTrue(any('H3标准字段' in w for w in plain['warnings']))
if __name__=='__main__':unittest.main()
