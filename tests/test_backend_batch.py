import asyncio,unittest,tempfile,sys,types,importlib,copy,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('batch_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
b=importlib.import_module(pkg.__name__+'.batch_runner')
def plan():return {'schema_version':'1.0','id':'batch_test','assets':[],'shots':[{'id':sid,'prompt':'garden','duration':1,'seed':666,'seed_control':'increment','continuity':{'mode':'independent'},'post':{'hd':False,'face':False}} for sid in ('a','c','d')]}
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.root=Path(self.temp.name);self.queued=[];self.gates={};b.RUNS.clear();b.TASKS.clear();self.entered=asyncio.Event()
  class Cache:
   def find(inner,p,sid,prompt):
    file=self.root/(sid+'.safetensors');return ({'artifact':file.name,'version':sid,'fingerprint':'base'} if file.is_file() else None,'base')
   find_for_process=find
  async def enqueue(p,w,c,o):
   data=json.loads(p[o]['inputs']['project_json']);self.queued.append(data);pid='job'+str(len(self.queued));self.gates[pid]=asyncio.Event();self.entered.set();return pid
  async def wait(pid):
   await self.gates[pid].wait();p=self.queued[int(pid[3:])-1];sid=p['runtime']['active_shot_id'];shot=next(s for s in p['shots'] if s['id']==sid);path=self.root/(sid+'.mp4');path.write_bytes(b'video');(self.root/(sid+'.safetensors')).write_bytes(b'new-base');b.Storage(self.root).record_output(p['id'],sid,json.dumps(shot['post'],sort_keys=True),str(path),24,post=shot['post']);return {}
  def matches(p,sid,prompt,record):return record['fingerprint']==json.dumps(next(s for s in p['shots'] if s['id']==sid)['post'],sort_keys=True)
  self.patches=[patch.object(b,'validate_generation',return_value={'valid':True}),patch.object(b,'data_root',return_value=self.root),patch.object(b,'preflight',return_value=[]),patch.object(b,'Star7DirectorBaseCache',Cache),patch.object(b,'enqueue',side_effect=enqueue),patch.object(b,'wait_job',side_effect=wait),patch.object(b,'output_matches',side_effect=matches),patch.object(b,'parameter_matches',side_effect=matches)]
  for p in self.patches:p.start()
 async def asyncTearDown(self):
  for task in b.TASKS.values():
   if not task.done():task.cancel()
  await asyncio.sleep(0)
  for p in self.patches:p.stop()
  self.temp.cleanup()
 async def begin(self,p=None,scope='all'):
  p=p or plan();return await b.start({'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':scope,'shot_id':'a'})
 async def wait_count(self,n):
  for _ in range(100):
   if len(self.queued)>=n:return
   await asyncio.sleep(.005)
  self.fail('Server did not enqueue the next job')
 async def test_server_continues_without_any_observer_and_stop_can_be_changed(self):
  original=plan();r=await self.begin(original);await self.wait_count(1);original['shots'][1]['prompt']='edited later';b.control(r['id'],'c');b.control(r['id'],'d');b.control(r['id'],None);b.control(r['id'],'c')
  self.gates['job1'].set();await self.wait_count(2);self.assertEqual(self.queued[1]['shots'][1]['prompt'],'garden');self.gates['job2'].set();await b.TASKS[r['id']]
  self.assertEqual(b.state(r['id'])['status'],'stopped');self.assertEqual(len(self.queued),2)
  r2=await self.begin();await self.wait_count(3);self.gates['job3'].set();await b.TASKS[r2['id']];self.assertEqual(b.state(r2['id'])['retained'],2);self.assertEqual(b.state(r2['id'])['completed'],1)
 async def test_all_hd_reuses_base_and_does_not_advance_sampling_seed(self):
  p=plan();p['shots']=p['shots'][:2];store=b.Storage(self.root)
  for s in p['shots']:
   (self.root/(s['id']+'.safetensors')).write_bytes(b'base');video=self.root/(s['id']+'.mp4');video.write_bytes(b'video');store.record_output(p['id'],s['id'],json.dumps(s['post'],sort_keys=True),str(video),24,post=s['post']);s['post']['hd']=True
  r=await self.begin(p);await self.wait_count(1);self.assertEqual(self.queued[0]['runtime']['scope'],'process');self.gates['job1'].set();await self.wait_count(2);self.assertEqual(self.queued[1]['runtime']['scope'],'process');self.gates['job2'].set();await b.TASKS[r['id']]
  self.assertEqual(b.state(r['id'])['seed_updates'],{});self.assertEqual(b.state(r['id'])['completed'],2)
 async def test_restored_hd_is_skipped_but_one_forces_first_pass_with_selected_post(self):
  p=plan();p['shots']=p['shots'][:1];shot=p['shots'][0];shot['post']={'hd':True,'face':True};store=b.Storage(self.root)
  video=self.root/'a.mp4';video.write_bytes(b'finished');(self.root/'a.safetensors').write_bytes(b'base')
  store.record_output(p['id'],'a',json.dumps(shot['post'],sort_keys=True),str(video),24,post=shot['post'])
  shot['post']['hd']=False;shot['post']['hd']=True
  r=await self.begin(p);await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['retained'],1);self.assertEqual(len(self.queued),0)
  r=await self.begin(p,'one');await self.wait_count(1)
  submitted=self.queued[0];self.assertEqual(submitted['runtime']['scope'],'one');self.assertEqual(submitted['shots'][0]['post'],{'hd':False,'face':False})
  self.gates['job1'].set();await self.wait_count(2);self.assertEqual(self.queued[1]['runtime']['scope'],'process');self.assertEqual(self.queued[1]['shots'][0]['post'],{'hd':True,'face':True});self.assertEqual(b.state(r['id'])['results']['a']['post'],{'hd':False,'face':False});self.gates['job2'].set();await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['seed_updates']['a']['nextSeed'],667)
 async def test_one_consumes_next_seed_and_failed_job_stops_batch(self):
  p=plan();video=self.root/'used.mp4';video.write_bytes(b'used');b.Storage(self.root).record_output(p['id'],'a','used',str(video),24);p['shots'][0]['next_seed']=667;r=await self.begin(p,'one');await self.wait_count(1);self.assertNotIn('a',b.state(r['id'])['results']);self.assertEqual(self.queued[0]['shots'][0]['seed'],667);self.gates['job1'].set();await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['seed_updates']['a']['nextSeed'],668)
  with patch.object(b,'wait_job',side_effect=ValueError('sampler failed')):
   p['id']='failed';r=await self.begin(p);await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['status'],'failed');self.assertEqual(b.state(r['id'])['completed'],0)
 async def test_all_and_process_queue_and_reconcile_completed_work(self):
  p=plan();p['shots']=p['shots'][:1]
  first=await self.begin(p,'one');await self.wait_count(1)
  second=await self.begin(p,'all')
  upgraded=copy.deepcopy(p);upgraded['shots'][0]['post']['hd']=True
  third=await self.begin(upgraded,'process')
  self.assertEqual(second['predecessor_id'],first['id']);self.assertEqual(third['predecessor_id'],second['id'])
  self.gates['job1'].set();await self.wait_count(2)
  self.assertEqual(b.state(second['id'])['retained'],1)
  self.assertEqual(self.queued[1]['runtime']['scope'],'process')
  self.gates['job2'].set();await b.TASKS[third['id']]
  self.assertEqual(b.state(third['id'])['status'],'completed')
 async def test_selected_can_queue_behind_one(self):
  p=plan();first=await self.begin(p,'one');await self.wait_count(1)
  selected=await b.start({'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':'selected','shot_ids':['d','c']})
  self.assertEqual(selected['predecessor_id'],first['id']);self.assertEqual(selected['shot_ids'],['c','d'])
  self.gates['job1'].set();await self.wait_count(2);self.gates['job2'].set();await self.wait_count(3);self.gates['job3'].set();await b.TASKS[selected['id']]
 async def test_one_queues_behind_active_run_without_a_browser(self):
  p=plan();p['shots']=p['shots'][:1]
  first=await self.begin(p);await self.wait_count(1)
  second=await self.begin(p,'one');self.assertEqual(second['status'],'queued');self.assertEqual(second['predecessor_id'],first['id'])
  self.assertEqual(b.latest(p['id'])['id'],first['id']);self.assertEqual(b.latest(p['id'])['pending_runs'][0]['id'],second['id']);self.assertEqual(len(self.queued),1)
  p['shots'][0]['prompt']='edited after queuing'
  self.gates['job1'].set();await self.wait_count(2)
  self.assertEqual(self.queued[1]['shots'][0]['prompt'],'garden');self.assertEqual(self.queued[1]['shots'][0]['seed'],666);self.assertEqual(b.latest(p['id'])['id'],second['id'])
  self.gates['job2'].set();await b.TASKS[second['id']];self.assertEqual(b.state(second['id'])['status'],'completed')
 async def test_process_restart_persists_interrupted_stage(self):
  r=await self.begin();await self.wait_count(1);saved=b.RUNS[r['id']];saved.update(phase='hd',active_shot_id='a');b.persist(saved);b.TASKS[r['id']].cancel();await asyncio.sleep(0);b.RUNS.clear()
  state=b.state(r['id']);self.assertEqual(state['status'],'interrupted');self.assertEqual(state['last_phase'],'hd');self.assertEqual(state['last_shot_id'],'a');self.assertEqual(b.state(r['id'])['revision'],state['revision'])
 async def test_batch_does_not_remove_completed_post_but_one_can(self):
  for actual in [{'hd':True,'face':False},{'hd':False,'face':True},{'hd':True,'face':True}]:
   p=plan();p['shots']=p['shots'][:1];video=self.root/'kept.mp4';video.write_bytes(b'video');b.Storage(self.root).record_output(p['id'],'a',json.dumps(actual,sort_keys=True),str(video),24,post=actual)
   r=await self.begin(p);await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['retained'],1);self.assertEqual(len(self.queued),0)
  r=await self.begin(p,'one');await self.wait_count(1);self.assertEqual(self.queued[0]['shots'][0]['post'],{'hd':False,'face':False});self.gates['job1'].set();await b.TASKS[r['id']]
 async def test_face_upgrade_preserves_existing_hd_when_hd_unchecked(self):
  p=plan();p['shots']=p['shots'][:1];p['shots'][0]['post']={'hd':False,'face':True};video=self.root/'hd.mp4';video.write_bytes(b'hd');b.Storage(self.root).record_output(p['id'],'a',json.dumps({'hd':True,'face':False},sort_keys=True),str(video),24,post={'hd':True,'face':False});(self.root/'a.safetensors').write_bytes(b'base')
  r=await self.begin(p);await self.wait_count(1);self.assertEqual(self.queued[0]['runtime']['scope'],'process');self.assertEqual(self.queued[0]['shots'][0]['post'],{'hd':True,'face':True});self.assertEqual(p['shots'][0]['post'],{'hd':False,'face':True});self.gates['job1'].set();await b.TASKS[r['id']]
  r=await self.begin(p,'process');await self.wait_count(2);self.assertEqual(self.queued[1]['shots'][0]['post'],{'hd':True,'face':True});self.gates['job2'].set();await b.TASKS[r['id']]
 async def test_selected_regenerates_only_checked_shots_in_story_order(self):
  p=plan();r=await b.start({'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':'selected','shot_ids':['d','a']})
  self.assertEqual(r['shot_ids'],['a','d']);await self.wait_count(1)
  self.assertEqual(self.queued[0]['runtime']['active_shot_id'],'a');self.assertEqual(self.queued[0]['runtime']['scope'],'one')
  self.gates['job1'].set();await self.wait_count(2);self.assertEqual(self.queued[1]['runtime']['active_shot_id'],'d')
  self.gates['job2'].set();await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['completed'],2)
 async def test_all_retained_scope_is_frozen_before_jobs_run(self):
  p=plan();store=b.Storage(self.root)
  for sid in ('c','d'):
   video=self.root/(sid+'.mp4');video.write_bytes(b'old');store.record_output(p['id'],sid,json.dumps({'hd':False,'face':False},sort_keys=True),str(video),24)
  r=await self.begin(p);await self.wait_count(1)
  with patch.object(b,'output_matches',return_value=False),patch.object(b,'parameter_matches',return_value=False):
   self.gates['job1'].set();await b.TASKS[r['id']]
  self.assertEqual(len(self.queued),1);self.assertEqual(b.state(r['id'])['retained'],2)
 async def test_queue_view_keeps_submission_order_and_stage_properties(self):
  p=plan();p['shots'][0]['post']={'hd':True,'face':True}
  first=await self.begin(p,'one');await self.wait_count(1)
  second=await b.start({'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':'one','shot_id':'c'})
  third=await self.begin(p,'one')
  view=b.state(first['id'])['queue_items'];self.assertEqual([v['shot_id'] for v in view],['a','c','a'])
  self.assertEqual(view[0]['stages'],['base','hd','face']);self.assertEqual(view[1]['stages'],['base'])
  self.assertEqual(view[0]['status'],'running');self.assertEqual(view[1]['status'],'queued')
  b.update(b.RUNS[first['id']],phase='hd');self.assertEqual(b.state(first['id'])['queue_items'][0]['active_stage'],'hd')
 async def test_queue_view_excludes_retained_clips_and_shows_process_only(self):
  p=plan();p['shots']=p['shots'][:1];p['shots'][0]['post']={'hd':True,'face':True}
  (self.root/'a.safetensors').write_bytes(b'base')
  r=await self.begin(p,'process');await self.wait_count(1)
  self.assertEqual(b.state(r['id'])['queue_items'][0]['stages'],['hd','face'])
  self.gates['job1'].set();await b.TASKS[r['id']]
  r=await self.begin(p);await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['queue_items'],[])
 async def test_cancelled_post_keeps_new_first_pass_and_does_not_start_next_shot(self):
  p=plan();p['shots'][0]['post']={'hd':True,'face':False};r=await self.begin(p,'one');await self.wait_count(1)
  self.gates['job1'].set();await self.wait_count(2)
  self.assertEqual(b.state(r['id'])['results']['a']['post'],{'hd':False,'face':False})
  for task in b.TASKS.values():task.cancel()
  await asyncio.sleep(0)
  self.assertEqual(b.Storage(self.root).latest_output(p['id'],'a')['post'],{'hd':False,'face':False})
 async def test_cancel_chain_continues_at_independent_shot(self):
  p=plan();p['shots'][1]['continuity']={'mode':'motion_guide','source_shot':'a'};p['shots'][2]['continuity']={'mode':'motion_guide','source_shot':'c'}
  p['shots'].append({**copy.deepcopy(p['shots'][0]),'id':'e'})
  r=await self.begin(p);preview=b.cancel_item(r['id'],'a');self.assertEqual([i['shot_id'] for i in preview['affected']],['a','c','d'])
  b.cancel_item(r['id'],'a',True);await self.wait_count(1);self.assertEqual(self.queued[0]['runtime']['active_shot_id'],'e')
  self.gates['job1'].set();await b.TASKS[r['id']];self.assertEqual(len(self.queued),1);self.assertEqual(len(b.state(r['id'])['skipped']),3)
 async def test_cancelling_regeneration_with_existing_video_keeps_dependents(self):
  p=plan();p['shots'][2]['continuity']={'mode':'tail_reference','source_shot':'c'}
  video=self.root/'c.mp4';video.write_bytes(b'old video');b.Storage(self.root).record_output(p['id'],'c','old',str(video),24)
  first=await self.begin(p,'one');await self.wait_count(1)
  args={'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':'one'}
  second=await b.start({**args,'shot_id':'c'});third=await b.start({**args,'shot_id':'d'})
  preview=b.cancel_item(second['id'],'c');self.assertEqual([i['shot_id'] for i in preview['affected']],['c']);b.cancel_item(second['id'],'c',True)
  with self.assertRaises(ValueError):b.cancel_item(first['id'],'a',True)
  self.gates['job1'].set();await self.wait_count(2);self.assertEqual(self.queued[1]['runtime']['active_shot_id'],'d');self.gates['job2'].set();await b.TASKS[third['id']]
  self.assertEqual(len(self.queued),2)
 async def test_missing_dynamic_first_frame_skips_to_uploaded_independent_shot(self):
  p=plan();p['shots'][1].update(input_mode='keyframes',keyframes={'first':{'from_previous':True}})
  r=await self.begin(p);b.cancel_item(r['id'],'a',True);await self.wait_count(1);self.assertEqual(self.queued[0]['runtime']['active_shot_id'],'d')
  self.gates['job1'].set();await b.TASKS[r['id']];self.assertEqual(set(b.state(r['id'])['skipped']),{'a','c'})
 async def test_cancel_confirmation_cannot_expand_silently(self):
  p=plan();r=await self.begin(p)
  with self.assertRaisesRegex(ValueError,'队列已变化'):b.cancel_item(r['id'],'a',True,['unseen:task'])
  self.assertNotIn('cancelled',b.RUNS[r['id']]);preview=b.cancel_item(r['id'],'a');keys=[i['run_id']+':'+i['shot_id'] for i in preview['affected']];b.cancel_item(r['id'],'a',True,keys)
 async def test_first_generation_uses_set_seed_for_every_scope(self):
  for scope in ('one','all','selected'):
   p=plan();p['id']='first_'+scope;p['shots']=p['shots'][:1];p['shots'][0]['next_seed']=667
   r=await b.start({'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','scope':scope,'shot_id':'a','shot_ids':['a']})
   count=len(self.queued)+1;await self.wait_count(count);self.assertEqual(self.queued[-1]['shots'][0]['seed'],666)
   self.gates['job'+str(count)].set();await b.TASKS[r['id']];self.assertEqual(b.state(r['id'])['seed_updates']['a']['nextSeed'],667)
 async def test_explicit_reset_to_same_seed_wins_over_previous_generation(self):
  p=plan();p['shots']=p['shots'][:1];video=self.root/'used.mp4';video.write_bytes(b'used');b.Storage(self.root).record_output(p['id'],'a','used',str(video),24)
  p['shots'][0]['seed']=666;p['shots'][0].pop('next_seed',None)
  r=await self.begin(p,'one');await self.wait_count(1);self.assertEqual(self.queued[0]['shots'][0]['seed'],666);self.gates['job1'].set();await b.TASKS[r['id']]
 async def test_changed_all_and_one_use_same_pending_seed(self):
  for scope in ('one','all'):
   p=plan();p['id']='pending_'+scope;p['shots']=p['shots'][:1];p['shots'][0]['next_seed']=667
   video=self.root/(p['id']+'.mp4');video.write_bytes(b'used');b.Storage(self.root).record_output(p['id'],'a','older parameters',str(video),24)
   r=await self.begin(p,scope);count=len(self.queued)+1;await self.wait_count(count);self.assertEqual(self.queued[-1]['shots'][0]['seed'],667);self.gates['job'+str(count)].set();await b.TASKS[r['id']]
if __name__=='__main__':unittest.main()
