import copy,importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('execution_safety_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
b=importlib.import_module(pkg.__name__+'.batch_runner')
state=importlib.import_module(pkg.__name__+'.execution_state')
cache=importlib.import_module(pkg.__name__+'.cache_management')
native=importlib.import_module(pkg.__name__+'.native_execution')
h=importlib.import_module(pkg.__name__+'.handoff')
rt=importlib.import_module(pkg.__name__+'.runtime')

def plan(pid='film'):
 return {'schema_version':'1.0','id':pid,'assets':[],'shots':[{'id':'a','prompt':'garden','duration':11,'seed':666,'seed_control':'increment','next_seed':667,'post':{'hd':True}},{'id':'b','prompt':'continue','duration':12,'continuity':{'mode':'motion_guide','source_shot':'a'},'post':{'hd':True}}]}

class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.root=Path(self.temp.name);b.RUNS.clear();b.TASKS.clear()
  self.patches=[patch.object(b,'data_root',return_value=self.root),patch.object(rt,'data_root',return_value=self.root)]
  for p in self.patches:p.start()
 def tearDown(self):
  b.RUNS.clear()
  for p in self.patches:p.stop()
  self.temp.cleanup()
 def cache_files(self,pid):
  store=cache.Storage(self.root);files={}
  for stage in ('base','hd','face','final'):
   file=self.root/'projects'/pid/'cache'/'a'/stage/'v.safetensors';file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(stage.encode());files[stage]=file
   with store.db(pid) as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',(pid,'a',stage,'v','fp',str(file.relative_to(self.root))))
  video=self.root/(pid+'.mp4');video.write_bytes(b'video');store.record_output(pid,'a','fp',str(video),264,base_version='v',handoff_version='v')
  return files
 def test_current_and_live_projects_reject_mixed_delete_atomically(self):
  files={pid:self.cache_files(pid) for pid in ('current','live','old')}
  b.RUNS['running']={'status':'running','plan':plan('live')}
  with self.assertRaisesRegex(ValueError,'当前项目'):cache.clear(self.root,'current','selected_checkpoints',project_ids=['old','current'])
  with self.assertRaisesRegex(ValueError,'生成'):cache.clear(self.root,'current','selected_checkpoints',project_ids=['old','live'])
  self.assertTrue(all(f.exists() for group in files.values() for f in group.values()))
  cache.clear(self.root,'current','other_checkpoints')
  self.assertTrue(all(f.exists() for f in files['live'].values()));self.assertTrue(all(f.exists() for f in files['current'].values()));self.assertFalse(any(f.exists() for f in files['old'].values()))
 def test_all_four_cache_stages_are_independently_removable(self):
  for stage in ('base','hd','face','final'):
   pid='project_'+stage;files=self.cache_files(pid)
   before=cache.stats(self.root,'other');row=next(r for r in before['projects'] if r['id']==pid)
   self.assertEqual(row['stage_bytes'][stage],len(stage))
   cache.clear(self.root,'other','selected_checkpoints',project_ids=[pid],stages=[stage])
   self.assertFalse(files[stage].exists());self.assertTrue(all(f.exists() for k,f in files.items() if k!=stage));self.assertEqual((self.root/(pid+'.mp4')).read_bytes(),b'video')
   self.assertIsNotNone(cache.Storage(self.root).latest_output(pid,'a'))
 def test_native_queue_and_export_jobs_protect_project(self):
  p=plan('native');queue=Mock();queue.get_current_queue.return_value=([],[(0,'pid',{'611':{'class_type':'Star7DirectorDesk','inputs':{'project_json':json.dumps(p)}}},{'client_id':'client'},[],{})])
  with patch.dict(sys.modules,{'server':types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=queue)))}):
   self.assertEqual(state.protected_projects('other'),{'other','native'})
   self.assertEqual(state.native_jobs()[0]['client_id'],'client')
   self.cache_files('native')
   with self.assertRaisesRegex(ValueError,'排队'):cache.clear(self.root,'other','selected_checkpoints',project_ids=['native'])
   items=b.native_queue_items('native');self.assertEqual(len(items),1);self.assertEqual(items[0]['origin'],'native')
   with patch.object(b,'stop_prompt',return_value=True) as stop:
    preview=b.cancel_native(items[0]['run_id'],'a');self.assertFalse(preview['stopping'])
    b.cancel_native(items[0]['run_id'],'a',True,[items[0]['key']]);stop.assert_called_once_with('pid')
 def test_targeted_stop_cannot_interrupt_unrelated_job(self):
  queue=Mock();queue.delete_queue_item.return_value=False;queue.interrupt_if_running.return_value=False
  with patch.dict(sys.modules,{'server':types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=queue)))}):
   self.assertFalse(b.stop_prompt('our-id'));queue.interrupt_if_running.assert_called_once_with('our-id')
   predicate=queue.delete_queue_item.call_args.args[0];self.assertFalse(predicate((0,'other-id')));self.assertTrue(predicate((0,'our-id')))
 def test_native_run_ignores_stale_scope_and_syncs_seed_and_output(self):
  p=plan();p['runtime']={'scope':'process','batch_id':'expired','request_nonce':'old','active_shot_id':'a'}
  store=b.Storage(self.root);video=self.root/'a.mp4';video.write_bytes(b'old');store.record_output('film','a','fp',str(video),264)
  job={'status':'running','owner_id':'611','prompt_id':'native-pid','plan':p,'client_id':'client'}
  with patch.object(native,'native_jobs',return_value=[job]),patch.object(native,'notify') as notify:
   with native.execution(p,{},'611') as actual:
    self.assertEqual(actual['runtime']['scope'],'one');self.assertNotEqual(actual['runtime']['request_nonce'],'old');self.assertEqual(actual['shots'][0]['seed'],667)
    rid=actual['runtime']['batch_id'];self.assertEqual(b.state(rid)['queue_items'][0]['status'],'running')
    store.record_output('film','a','new-fp',str(video),264)
   r=b.state(rid);self.assertEqual(r['status'],'completed');self.assertEqual(r['seed_updates']['a']['nextSeed'],668);self.assertEqual(r['results']['a']['prompt_id'],'native-pid');self.assertEqual(notify.call_count,2)
  self.assertEqual(p['runtime']['scope'],'process');self.assertEqual(p['shots'][0]['seed'],666)
 def test_native_failure_unlocks_project_and_preserves_previous_output(self):
  p=plan();video=self.root/'keep.mp4';video.write_bytes(b'keep');b.Storage(self.root).record_output('film','a','fp',str(video),264)
  with patch.object(native,'native_jobs',return_value=[{'status':'running','owner_id':'611','prompt_id':'pid','plan':p}]),patch.object(native,'notify'):
   with self.assertRaisesRegex(ValueError,'missing cache'):
    with native.execution(p,{},'611') as actual:
     rid=actual['runtime']['batch_id'];raise ValueError('missing cache')
  self.assertEqual(b.state(rid)['status'],'failed');self.assertEqual(state.protected_projects('other'),{'other'});self.assertEqual(video.read_bytes(),b'keep')
 def test_native_stop_is_terminal_and_preserves_output(self):
  from comfy.model_management import InterruptProcessingException
  p=plan()
  with patch.object(native,'native_jobs',return_value=[{'status':'running','owner_id':'611','prompt_id':'pid','plan':p}]),patch.object(native,'notify'),patch.object(b,'stop_prompt',return_value=True):
   with self.assertRaises(InterruptProcessingException):
    with native.execution(p,{},'611') as actual:
     rid=actual['runtime']['batch_id'];b.cancel_item(rid,'a',True);raise InterruptProcessingException()
  self.assertEqual(b.state(rid)['status'],'stopped');self.assertFalse(b.active())
 def test_validation_lease_protects_cache_until_failure_is_released(self):
  self.cache_files('checking')
  with state.lease(plan('checking')):
   with self.assertRaisesRegex(ValueError,'排队'):cache.clear(self.root,'other','selected_checkpoints',project_ids=['checking'])
  cache.clear(self.root,'other','selected_checkpoints',project_ids=['checking'])
  self.assertEqual(cache.Storage(self.root).stages('checking'),[])
 def test_importing_archive_is_protected_even_if_old(self):
  import os,time
  index=importlib.import_module(pkg.__name__+'.package_index');folder=self.root/'packages';folder.mkdir();archive=folder/'current.upload';archive.write_bytes(b'import in progress');os.utime(archive,(time.time()-90000,)*2)
  pack=index.begin(self.root,'material.zip',archive)
  with self.assertRaisesRegex(ValueError,'不能删除'):cache.clear(self.root,'other','package',pack)
  cache.clear(self.root,'other','temporary');self.assertTrue(archive.exists())
  index.update(self.root,pack,state='failed');cache.clear(self.root,'other','package',pack);self.assertFalse(archive.exists())
 def test_live_batch_scope_is_preserved_only_for_matching_request(self):
  p=plan();p['runtime']={'batch_id':'valid','request_nonce':'nonce','scope':'process','active_shot_id':'a'}
  b.RUNS['valid']={'status':'running','project_id':'film','active_shot_id':'a','nonce':'nonce','owner_id':'611'}
  with native.execution(p,{},'611') as actual:self.assertEqual(actual['runtime']['scope'],'process')
  with native.execution(p,{},'different-owner') as actual:self.assertEqual(actual['runtime']['scope'],'one')
 def test_missing_final_cache_fails_before_any_upscale(self):
  import torch
  from comfy.nested_tensor import NestedTensor
  p=plan();store=rt.Storage(self.root)
  v=store.save_latent('film','a','base','fp',{'samples':NestedTensor((torch.zeros(1,24,82,2,2),torch.zeros(1,32,2,600)))})
  store.record_output('film','a','fp','fixture.mp4',264,post={'hd':True},base_version=v)
  with self.assertRaisesRegex(ValueError,'尚未开始采样或二采'):h.check_request(p,'b',{})
  self.assertEqual(len(store.stages('film')),1)
 def test_valid_cache_provenance_passes_without_loading_tensor_payloads(self):
  import torch
  from comfy.nested_tensor import NestedTensor
  p=plan();store=rt.Storage(self.root)
  latent={'samples':NestedTensor((torch.zeros(1,24,82,2,2),torch.zeros(1,32,2,600)))}
  v=store.save_latent('film','a','base','fp',latent);final=store.save_latent('film','a','final','fp',latent)
  store.record_output('film','a','fp','fixture.mp4',264,post={'hd':True},base_version=v,handoff_version=final)
  with patch.object(rt.Storage,'load_latent',side_effect=AssertionError('Preflight must only read metadata')):h.check_request(p,'b',{})
  p['runtime']={'scope':'process'}
  current=store.save_latent('film','b','base','fp',latent)
  with patch.object(rt.Star7DirectorBaseCache,'find_for_process',return_value=({'version':current},'fp')):
   with self.assertRaisesRegex(ValueError,'旧运动引导缓存'):h.check_request(p,'b',{},processing=True)

if __name__=='__main__':unittest.main()
