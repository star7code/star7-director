import copy,importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('parameter_state_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
rt=importlib.import_module(pkg.__name__+'.runtime');ps=importlib.import_module(pkg.__name__+'.parameter_state')
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.patch=patch.object(rt,'data_root',return_value=self.root);self.patch.start()
  self.plan={'schema_version':'1.0','id':'test','assets':[],'shots':[{'id':'s1','duration':1,'seed':666,'prompt':'garden','post':{'hd':False,'face':False}},{'id':'s2','duration':1,'seed':666,'prompt':'continue','continuity':{'mode':'tail_reference','source_shot':'s1'}}]}
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def record(self,sid):return {'fingerprint':'full','parameter_fingerprint':ps.encode(self.plan,sid),'post':copy.deepcopy(next(s for s in self.plan['shots'] if s['id']==sid).get('post',{}))}
 def test_external_lora_does_not_mark_edits_but_own_changes_do_and_revert(self):
  record=self.record('s1');prompt={'lora':{'class_type':'LoraLoader','inputs':{'strength_model':.2}}}
  self.assertTrue(rt.parameter_matches(self.plan,'s1',prompt,record))
  self.plan['shots'][0]['seed']=777;changes=ps.details(self.plan,'s1',record)['changes'];self.assertEqual(changes[0]['label'],'镜头 / 种子');self.assertFalse(rt.parameter_matches(self.plan,'s1',prompt,record))
  self.plan['shots'][0]['seed']=666;self.assertEqual(ps.details(self.plan,'s1',record)['changes'],[]);self.assertTrue(rt.parameter_matches(self.plan,'s1',prompt,record))
 def test_upstream_result_changes_only_reference_notice(self):
  store=rt.Storage(self.root);movie=self.root/'one.mp4';movie.write_bytes(b'1');store.record_output('test','s1','old',str(movie),24)
  record=self.record('s2');store.record_output('test','s1','new',str(movie),24)
  self.plan['shots'][0]['seed']=888
  self.assertTrue(rt.parameter_matches(self.plan,'s2',{},record));self.assertEqual(ps.details(self.plan,'s2',record),{'changes':[],'reference_changed':True})
 def test_postprocessing_does_not_change_reference_but_new_base_does(self):
  store=rt.Storage(self.root);movie=self.root/'one.mp4';movie.write_bytes(b'1')
  store.record_output('test','s1','base',str(movie),24,post={'hd':False,'face':False},base_version='base-one')
  record=self.record('s2')
  store.record_output('test','s1','hd',str(movie),24,post={'hd':True},base_version='base-one')
  self.assertFalse(ps.details(self.plan,'s2',record)['reference_changed'])
  store.record_output('test','s1','face',str(movie),24,post={'hd':True,'face':True},base_version='base-one')
  self.assertFalse(ps.details(self.plan,'s2',record)['reference_changed'])
  store.record_output('test','s1','new-base',str(movie),24,base_version='base-two')
  self.assertTrue(ps.details(self.plan,'s2',record)['reference_changed'])
  self.assertTrue(rt.parameter_matches(self.plan,'s2',{},record))
 def test_previous_tail_rebuild_is_real_edit_but_postprocessing_is_not(self):
  shot=self.plan['shots'][1];shot['input_mode']='keyframes';shot['keyframes']={'first':{'from_previous':True}}
  store=rt.Storage(self.root);movie=self.root/'one.mp4';movie.write_bytes(b'1')
  store.record_output('test','s1','base',str(movie),24,base_version='base-one')
  record=self.record('s2')
  store.record_output('test','s1','hd',str(movie),24,post={'hd':True},base_version='base-one')
  self.assertTrue(rt.parameter_matches(self.plan,'s2',{},record))
  store.record_output('test','s1','new-base',str(movie),24,base_version='base-two')
  self.assertFalse(rt.parameter_matches(self.plan,'s2',{},record))
  self.assertFalse(rt.parameter_matches(rt.batch_plan(self.plan,'s2',record),'s2',{},record))
  details=ps.details(self.plan,'s2',record)
  self.assertFalse(details['reference_changed'])
  self.assertEqual(details['changes'][-1]['label'],'首帧 / 上段视频尾帧')
 def test_saved_v4_file_pin_resolves_to_base_generation(self):
  store=rt.Storage(self.root);old=self.root/'old.mp4';new=self.root/'new.mp4';old.write_bytes(b'old');new.write_bytes(b'new')
  store.record_output('test','s1','first',str(old),24,base_version='base-one')
  record=self.record('s2');saved=json.loads(record['parameter_fingerprint'][len(ps.PREFIX):])
  saved['source']={'id':'s1','fingerprint':'first','path':str(old)}
  record['parameter_fingerprint']=ps.PREFIX+json.dumps(saved)
  store.record_output('test','s1','hd',str(new),24,post={'hd':True},base_version='base-one')
  self.assertFalse(ps.details(self.plan,'s2',record)['reference_changed'])
  store.record_output('test','s1','regenerated',str(new),24,base_version='base-two')
  self.assertTrue(ps.details(self.plan,'s2',record)['reference_changed'])
 def test_legacy_task_reference_pin_shows_notice_without_batch_regeneration(self):
  store=rt.Storage(self.root);movie=self.root/'old.mp4';movie.write_bytes(b'old')
  store.record_output('test','s1','first',str(movie),24,base_version='base-one')
  batches=self.root/'projects'/'test'/'batches';batches.mkdir(parents=True)
  (batches/'task.json').write_text(json.dumps({'plan':self.plan,'results':{'s2':{'path':'child.mp4','prompt_id':'prompt'}},
    'reference_pins':{'s1':store.latest_output('test','s1')}}),encoding='utf8')
  record={'path':'child.mp4','parameter_fingerprint':'v3:old'}
  store.record_output('test','s1','new',str(movie),24,base_version='base-two')
  self.assertTrue(ps.details(self.plan,'s2',record)['reference_changed'])
  self.assertTrue(rt.parameter_matches(self.plan,'s2',{},record))
 def test_deselecting_hd_preserves_batch_and_face_is_an_upgrade(self):
  shot=self.plan['shots'][0];shot['post']['hd']=True;record=self.record('s1');shot['post']['hd']=False
  self.assertFalse(rt.parameter_matches(self.plan,'s1',{},record));self.assertTrue(rt.parameter_matches(rt.batch_plan(self.plan,'s1',record),'s1',{},record))
  shot['post']['face']=True;self.assertFalse(rt.parameter_matches(rt.batch_plan(self.plan,'s1',record),'s1',{},record))
 def test_enabling_post_pass_has_one_explanation_but_later_setting_edits_remain_visible(self):
  shot=self.plan['shots'][0]
  self.plan['generation']={'376':{'enable_tiling':True,'target_megapixels':2.6},'395':{'face_count':1}}
  record=self.record('s1')
  shot['post']['hd']=True
  rows=ps.details(self.plan,'s1',record)['changes']
  self.assertEqual([row['field'] for row in rows],['shot.post.hd'])
  self.assertFalse(rt.parameter_matches(self.plan,'s1',{},record))
  shot['post']['hd']=False;shot['post']['face']=True
  rows=ps.details(self.plan,'s1',record)['changes']
  self.assertEqual([row['field'] for row in rows],['shot.post.face'])
  shot['post']['face']=False
  self.assertEqual(ps.details(self.plan,'s1',record)['changes'],[])
  shot['post']['hd']=True
  generated=self.record('s1')
  self.plan['generation']['376']['target_megapixels']=3.0
  self.assertEqual(ps.details(self.plan,'s1',generated)['changes'][0]['field'],'generation.376.target_megapixels')
 def test_legacy_task_ignores_external_pipeline(self):
  directory=self.root/'projects'/'test'/'batches';directory.mkdir(parents=True)
  (directory/'saved.json').write_text(json.dumps({'plan':self.plan,'prepared':{'output':{'old_lora':{}}},'results':{'s1':{'path':'old.mp4','prompt_id':'p'}}}),encoding='utf-8')
  record={'path':'old.mp4','parameter_fingerprint':'v3:unknown'}
  self.assertTrue(rt.parameter_matches(self.plan,'s1',{'new_lora':{}},record))
 def test_continuity_mode_is_one_human_readable_change(self):
  shot=self.plan['shots'][1];shot['continuity']={'mode':'independent'};record=self.record('s2')
  shot['continuity']={'mode':'motion_guide','source_shot':'s1'}
  changes=ps.details(self.plan,'s2',record)['changes']
  self.assertEqual(len(changes),1);self.assertEqual(changes[0]['label'],'连续性')
  self.assertEqual(changes[0]['before'],'独立镜头')
  self.assertEqual(changes[0]['after'],'运动引导（参考 s1 的画面）')
  self.assertFalse(rt.parameter_matches(self.plan,'s2',{},record))
  shot['continuity']={'mode':'independent'}
  self.assertEqual(ps.details(self.plan,'s2',record)['changes'],[])
 def test_selected_frame_switch_is_one_change_but_independent_setting_remains_detailed(self):
  shot=self.plan['shots'][1];shot['continuity']={'mode':'independent'};record=self.record('s2')
  shot['continuity']={'mode':'selected_frame','source_shot':'s1','frame':7}
  changes=ps.details(self.plan,'s2',record)['changes']
  self.assertEqual(len(changes),1);self.assertIn('第 7 帧',changes[0]['after'])
if __name__=='__main__':unittest.main()
