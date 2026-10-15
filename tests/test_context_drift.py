import copy,importlib,sys,types,unittest
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('drift_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
drift=importlib.import_module(pkg.__name__+'.context_drift')
core=importlib.import_module(pkg.__name__+'.core')
state=importlib.import_module(pkg.__name__+'.parameter_state')
motion=importlib.import_module(pkg.__name__+'.vendor.aimixer.h3_motion_context')
from comfy.nested_tensor import NestedTensor
class Tests(unittest.TestCase):
 def test_process_reuses_exact_displayed_base_without_claiming_drift_applied(self):
  import tempfile,json
  from unittest.mock import patch
  rt=importlib.import_module(pkg.__name__+'.runtime')
  p={'schema_version':'1.0','id':'p','assets':[],'shots':[{'id':'a','prompt':'garden','duration':3},{'id':'b','prompt':'garden','duration':3,'continuity':{'mode':'motion_guide','source_shot':'a'},'post':{'hd':False}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   store=rt.Storage(tmp);fingerprint=rt.run_fingerprint(p,'b',stage='base');version=store.save_latent('p','b','base',fingerprint,{'samples':torch.zeros(1)})
   path=Path(tmp)/'b.mp4';path.write_bytes(b'video');store.record_output('p','b','fp',str(path),72,base_version=version,parameter_fingerprint=state.encode(p,'b'))
   p['continuity_settings']={'drift_control':True,'drift_strength':.3};p['shots'][1]['post']['hd']=True
   self.assertIsNone(rt.Star7DirectorBaseCache().find(p,'b',{})[0]);row,_=rt.Star7DirectorBaseCache().find_for_process(p,'b',{});self.assertEqual(row['version'],version)
   old=store.latest_output('p','b');p['runtime']={'scope':'process'}
   saved=json.loads(state.encode(p,'b',old)[len(state.PREFIX):]);self.assertNotIn('drift_control',saved['inputs'])
   p['shots'][1]['prompt']='different scene';self.assertIsNone(rt.Star7DirectorBaseCache().find_for_process(p,'b',{})[0])
 def test_finished_postprocess_accepts_drift_choice_but_keeps_real_base(self):
  import tempfile,json
  from unittest.mock import patch
  rt=importlib.import_module(pkg.__name__+'.runtime')
  p={'schema_version':'1.0','id':'p','assets':[],'continuity_settings':{'drift_control':True,'drift_strength':.3},'shots':[{'id':'a','prompt':'garden','duration':3},{'id':'b','prompt':'garden','duration':3,'continuity':{'mode':'motion_guide','source_shot':'a'},'post':{'hd':False}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   store=rt.Storage(tmp);fp=rt.run_fingerprint(p,'b',stage='base');version=store.save_latent('p','b','base',fp,{'samples':torch.zeros(1)})
   path=Path(tmp)/'b.mp4';path.write_bytes(b'video');store.record_output('p','b','base-out',str(path),72,base_version=version,parameter_fingerprint=state.encode(p,'b'))
   old=store.latest_output('p','b');p['continuity_settings']['drift_control']=False;p['shots'][1]['post']['hd']=True;p['runtime']={'scope':'process'}
   record={'parameter_fingerprint':state.encode(p,'b',old),'base_version':version,'post':{'hd':True}}
   saved=json.loads(record['parameter_fingerprint'][len(state.PREFIX):]);self.assertIsNone(saved['accepted_drift_control']);self.assertEqual(saved['inputs']['drift_control']['strength'],.3)
   self.assertEqual(state.details(p,'b',record)['changes'],[]);self.assertTrue(rt.parameter_matches(p,'b',{},record))
   store.record_output('p','b','hd-out',str(path),72,base_version=version,parameter_fingerprint=record['parameter_fingerprint'],post={'hd':True})
   row,_=rt.Star7DirectorBaseCache().find_for_process(p,'b',{});self.assertEqual(row['version'],version)
   p['continuity_settings']['drift_control']=True;p['continuity_settings']['drift_strength']=.2;self.assertFalse(rt.parameter_matches(p,'b',{},record));self.assertEqual(state.details(p,'b',record)['changes'][0]['field'],'shot.continuity.drift_control')
   p['continuity_settings']['drift_control']=False;p['shots'][1]['seed']=999;self.assertFalse(rt.parameter_matches(p,'b',{},record))
 def test_old_postprocess_recovers_accepted_choice_from_its_exact_task(self):
  import tempfile,json
  from unittest.mock import patch
  rt=importlib.import_module(pkg.__name__+'.runtime')
  p={'schema_version':'1.0','id':'p','assets':[],'continuity_settings':{'drift_control':True},'shots':[{'id':'a','prompt':'garden','duration':3},{'id':'b','prompt':'garden','duration':3,'continuity':{'mode':'motion_guide','source_shot':'a'},'post':{'hd':True}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   record={'parameter_fingerprint':state.encode(p,'b'),'path':'exact.mp4','post':{'hd':True}};p['continuity_settings']['drift_control']=False
   folder=Path(tmp)/'projects'/'p'/'batches';folder.mkdir(parents=True);(folder/'task.json').write_text(json.dumps({'scope':'process','plan':p,'results':{'b':{'path':'different.mp4','prompt_id':'job'}}}))
   self.assertFalse(rt.parameter_matches(p,'b',{},record))
   (folder/'task.json').write_text(json.dumps({'scope':'process','plan':p,'results':{'b':{'path':'exact.mp4','prompt_id':'job'}}}))
   self.assertTrue(rt.parameter_matches(p,'b',{},record));self.assertEqual(state.details(p,'b',record)['changes'],[])
 def test_taper_repeatability_rng_and_original_preserved(self):
  blocks=[torch.arange(384.).reshape(1,24,1,4,4)/100 for _ in range(7)];before=[b.clone() for b in blocks];rng=torch.random.get_rng_state()
  result=drift.taper_guides(blocks,.3,666);again=drift.taper_guides(blocks,.3,666)
  self.assertTrue(all(torch.equal(a,b) for a,b in zip(result,again)));self.assertTrue(torch.equal(rng,torch.random.get_rng_state()))
  self.assertTrue(all(torch.equal(a,b) for a,b in zip(before,blocks)));self.assertTrue(torch.equal(result[-1],blocks[-1]));self.assertFalse(torch.equal(result[0],blocks[0]))
  self.assertTrue(all(torch.isfinite(b).all() for b in result));self.assertIs(drift.taper_guides(blocks,0,666),blocks)
 def test_guide_integration_preserves_audio_refs_and_timing(self):
  previous={'samples':NestedTensor((torch.arange(24*27*16.).reshape(1,24,27,4,4)/100,torch.ones(1,32,2,150)))}
  latent={'samples':NestedTensor((torch.zeros(1,24,27,4,4),torch.zeros(1,32,2,150)))}
  cond=[[torch.zeros(1),{'minimax_refs':[{'kind':'image','latent':torch.ones(1,24,1,4,4)}]}]]
  baseline,head,gap=motion.apply_motion_context(cond,latent,vae=None,context_length=22,context_latent=previous,continue_audio=True)
  result,newhead,newgap=motion.apply_motion_context(cond,latent,vae=None,context_length=22,context_latent=previous,continue_audio=True,context_transform=lambda b:drift.taper_guides(b,.3,666))
  self.assertEqual((head,gap),(newhead,newgap));self.assertEqual(len(baseline[0][1]['minimax_keyframes']),len(result[0][1]['minimax_keyframes']))
  a=baseline[0][1]['minimax_keyframes'];b=result[0][1]['minimax_keyframes'];self.assertTrue(torch.equal(a[-1]['latent'],b[-1]['latent']));self.assertFalse(torch.equal(a[0]['latent'],b[0]['latent']))
  for x,y in zip(baseline[0][1]['minimax_refs'],result[0][1]['minimax_refs']):
   if 'audio_latent' in x:self.assertTrue(torch.equal(x['audio_latent'],y['audio_latent']))
  self.assertTrue(torch.equal(previous['samples'].tensors[1],torch.ones(1,32,2,150)))
 def test_fingerprint_only_for_enabled_motion_guide_and_explicit_detail(self):
  p={'schema_version':'1.0','id':'p','assets':[],'shots':[{'id':'a','prompt':'garden','duration':3},{'id':'b','prompt':'garden','duration':3,'continuity':{'mode':'motion_guide','source_shot':'a'}}]}
  original=core.compile_shot(p,'b')['fingerprint'];baseline=state.snapshot(p,'b')
  p['continuity_settings']={'drift_control':False,'drift_strength':.4};self.assertEqual(core.compile_shot(p,'b')['fingerprint'],original)
  p['continuity_settings']['drift_control']=True;self.assertNotEqual(core.compile_shot(p,'b')['fingerprint'],original)
  changes=state.visible_changes(baseline,state.snapshot(p,'b'));self.assertEqual([c['field'] for c in changes],['shot.continuity.drift_control'])
  p['continuity_settings']['drift_control']=False;self.assertEqual(state.visible_changes(baseline,state.snapshot(p,'b')),[])
  p['shots'][1]['continuity']['mode']='motion_redraw';a=core.compile_shot(p,'b')['fingerprint'];p['continuity_settings']['drift_control']=True;self.assertEqual(core.compile_shot(p,'b')['fingerprint'],a)
if __name__=='__main__':unittest.main()
