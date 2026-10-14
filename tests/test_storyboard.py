import unittest,copy,types,sys,importlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));p=types.ModuleType('storyboard_tests');p.__path__=[str(ROOT)];sys.modules[p.__name__]=p
module=importlib.import_module(p.__name__+'.storyboard');core=importlib.import_module(p.__name__+'.core')
def plan():return {'schema_version':'1.0','id':'p','settings':{'width':640,'height':384},'assets':[{'id':'actor','name':'小红','kind':'character','voice_id':'voice','media':[{'type':'image','source':'actor.png'}]},{'id':'voice','name':'音色1','kind':'voice','description':'a warm voice','media':[]},{'id':'effect','name':'光线','kind':'effect','description':'sunlight illuminates @{actor}','media':[]}],'shots':[{'id':'shot_013','name':'old','duration':2,'prompt':'garden'}],'shot_sequence':13}
class Tests(unittest.TestCase):
 def test_optional_endpoint_modes(self):
  import json
  for code,fields,slots in [('S',{'first_frame':'@{小红}'},{'first'}),('E',{'last_frame':'actor'},{'last'}),('SE',{'first_frame':'小红','last_frame':'@{actor}'},{'first','last'})]:
   result=module.recognize(plan(),json.dumps({'shots':[{'duration':8,'mode':code,'prompt':'@{首帧} to @{尾帧}',**fields}]}),'replace')
   self.assertTrue(result['valid'],result['errors']);shot=result['candidate']['shots'][0];self.assertEqual(shot['input_mode'],'keyframes');self.assertEqual(set(shot['keyframes']),slots);self.assertEqual(shot['continuity'],{'mode':'independent'});self.assertEqual(result['rows'][0]['media_counts']['image'],len(slots))
   compiled=core._compile_shot(result['candidate'],shot['id']);self.assertEqual(set(compiled['keyframes']),slots)
  for fields in [{'mode':'S'},{'mode':'SE','first_frame':'actor'},{'mode':'E','last_frame':'音色1'},{'mode':'I','first_frame':'actor'},{'mode':'S','first_frame':'actor','last_frame':'actor'}]:
   result=module.recognize(plan(),json.dumps({'shots':[{'duration':8,'prompt':'garden',**fields}]}),'replace');self.assertFalse(result['valid'],fields)
 def test_internal_shots_stay_in_one_generation_clip(self):
  import json
  prompt='subject_definitions: <Subject 1> is @{小红}.\nsummary: [reference generation] Two camera views of one performance.\nretention_analysis: <Subject 1>: fully_preserved - identity only.\ndetailed_description: [Shot 1] <Subject 1> (S1) says: <d>[Chinese] 我们开始吧。</d> [Shot 2] At 00:05.000, a closer view shows the same character reacting.\noverall_soundscape: Room tone.\nnon_diegetic_music: N/A'
  result=module.recognize(plan(),json.dumps({'shots':[{'duration':10,'mode':'I','prompt':prompt}]}),'replace');self.assertTrue(result['valid'],result['errors']);self.assertEqual(result['count'],1);self.assertEqual(len(result['candidate']['shots']),1);self.assertEqual(result['total_duration'],10);self.assertIn('[Shot 2] At 00:05.000',result['rows'][0]['model_prompt']);self.assertIn('<Picture 1>',result['rows'][0]['model_prompt']);self.assertIn('<d>[Chinese] 我们开始吧。</d>',result['rows'][0]['model_prompt'])
 def test_import_mode_codes(self):
  p=plan();text='{"shots":[{"duration":3,"mode":"I","prompt":"garden"},{"duration":3,"mode":"R","prompt":"continue garden"}]}'
  result=module.recognize(p,text,'replace');self.assertTrue(result['valid'],result);a,b=result['candidate']['shots'];self.assertEqual(a['continuity'],{'mode':'independent'});self.assertEqual(b['continuity'],{'mode':'motion_redraw','source_shot':a['id']})
  result=module.recognize(p,'{"shots":[{"duration":3,"mode":"R","prompt":"continue"}]}','replace');self.assertFalse(result['valid']);self.assertIn('第一个镜头',result['errors'][0]['message'])
  result=module.recognize(p,'{"shots":[{"duration":3,"mode":"R","prompt":"continue"}]}','append');self.assertTrue(result['valid']);self.assertEqual(result['candidate']['shots'][-1]['continuity']['source_shot'],p['shots'][-1]['id'])
  result=module.recognize(p,'{"shots":[{"duration":3,"mode":"X","prompt":"continue"}]}');self.assertFalse(result['valid'])
 def test_fence_alias_text_binding_and_no_mutation(self):
  import json
  p=plan();before=copy.deepcopy(p);text='```json\n'+json.dumps({'shots':[{'duration':3.5,'prompt':'@{光线} @小红.'},{'时长':'2.5秒','提示词':'@{actor} smiles.'}]},ensure_ascii=False)+'\n```'
  result=module.recognize(p,text);self.assertTrue(result['valid'],result);self.assertEqual(p,before);self.assertEqual(result['candidate']['shots'][1]['id'],'shot_014');self.assertEqual(result['candidate']['shots'][1]['seed'],666);self.assertEqual(result['candidate']['shots'][1]['seed_control'],'increment');self.assertEqual(result['total_duration'],6);self.assertTrue(result['warnings']);self.assertEqual(result['rows'][0]['media_counts']['image'],1);self.assertIn('<Picture 1>',result['rows'][0]['model_prompt']);self.assertIn('a warm voice',result['rows'][0]['model_prompt']);self.assertNotIn('@',result['rows'][0]['model_prompt']);self.assertIn('@{actor}',result['rows'][0]['prompt'])
 def test_replace_fresh_ids_and_optional_name(self):
  result=module.recognize(plan(),'[{"duration":5,"prompt":"garden","name":"opening"}]','replace');self.assertTrue(result['valid']);self.assertEqual(len(result['candidate']['shots']),1);self.assertEqual(result['candidate']['shots'][0]['id'],'shot_014');self.assertEqual(result['candidate']['shots'][0]['name'],'opening')
 def test_errors_all_or_nothing(self):
  import json
  for bad in [{'duration':True,'prompt':'garden'},{'duration':61,'prompt':'garden'},{'duration':0,'prompt':'garden'},{'duration':3,'prompt':'@{unknown}'},{'duration':3,'prompt':'@{}'},{'duration':3,'prompt':'<span>garden</span>'},{'duration':3,'prompt':'<Picture1>'},{'duration':3,'prompt':'garden','seed':666},{'duration':3,'seconds':4,'prompt':'garden'}]:
   result=module.recognize(plan(),json.dumps({'shots':[{'duration':1,'prompt':'garden'},bad]}));self.assertFalse(result['valid'],bad);self.assertIsNone(result['candidate']);self.assertEqual(result['errors'][0]['index'],2)
 def test_bad_json_duplicate_and_multiple(self):
  for text in ['{"shots":[{"duration":5,"prompt":"garden"}]','{"shots":[{"duration":5,"duration":6,"prompt":"garden"}]}','{"shots":NaN}','```json\n{"shots":[]}\n```\n```json\n{"shots":[]}\n```']:
   with self.assertRaises(ValueError):module.recognize(plan(),text)
 def test_cycle_and_media_limit(self):
  import json
  p=plan();p['assets'][2]['description']='@{effect}'
  result=module.recognize(p,'{"shots":[{"duration":3,"prompt":"@{effect}"}]}');self.assertFalse(result['valid']);self.assertIn('循环',result['errors'][0]['message'])
  p=plan();p['assets'].extend({'id':'a'+str(i),'name':'picture'+str(i),'kind':'prop','media':[{'type':'image','source':str(i)+'.png'}]} for i in range(10));result=module.recognize(p,json.dumps({'shots':[{'duration':3,'prompt':' '.join('@{a'+str(i)+'}' for i in range(10))}]}));self.assertFalse(result['valid']);self.assertIn('exceed',result['errors'][0]['message'])
 def test_large_batch(self):
  import json
  p=plan();start=time.monotonic();result=module.recognize(p,json.dumps({'shots':[{'duration':1.25,'prompt':'@{actor} walks.'} for _ in range(500)]}));self.assertTrue(result['valid'],result['errors']);self.assertEqual(result['count'],500);self.assertEqual(result['total_duration'],625);self.assertEqual(len({s['id'] for s in result['candidate']['shots']}),501);self.assertLess(time.monotonic()-start,5)
if __name__=='__main__':unittest.main()
