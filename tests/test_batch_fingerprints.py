import copy,importlib,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('batch_fingerprint_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
rt=importlib.import_module(pkg.__name__+'.runtime');cache=importlib.import_module(pkg.__name__+'.cache_management')
class Tests(unittest.TestCase):
 def plan(self):return {'schema_version':'1.0','id':'batch','assets':[],'shots':[{'id':'s1','duration':1,'prompt':'garden','seed':666},{'id':'s2','duration':1,'prompt':'continue','continuity':{'mode':'motion_guide','source_shot':'s1'}}]}
 def test_comfy_float_coercion_preserves_fingerprint_without_mutation(self):
  class Scalar:
   @classmethod
   def INPUT_TYPES(cls):return {'required':{'strength_model':('FLOAT',),'steps':('INT',)}}
  import nodes
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.dict(nodes.NODE_CLASS_MAPPINGS,{'BatchScalar':Scalar}):
   p={'1':{'class_type':'BatchScalar','inputs':{'strength_model':1,'steps':4}}};queued=copy.deepcopy(p);queued['1']['inputs']['strength_model']=1.0
   self.assertEqual(rt.run_fingerprint(self.plan(),'s1',p),rt.run_fingerprint(self.plan(),'s1',queued));self.assertIs(type(p['1']['inputs']['strength_model']),int)
   queued['1']['inputs']['strength_model']=.8;self.assertNotEqual(rt.run_fingerprint(self.plan(),'s1',p),rt.run_fingerprint(self.plan(),'s1',queued))
 def test_optional_empty_name_compatibility_does_not_hide_real_changes(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   p=self.plan();p['shots'][0]['post']={'hd':True,'face':False};record={'fingerprint':rt.run_fingerprint(p,'s1')}
   p['shots'][0]['name']='';self.assertTrue(rt.output_matches(p,'s1',{},record))
   p['shots'][0]['post']['hd']=False;self.assertFalse(rt.output_matches(p,'s1',{},record))
   p['shots'][0]['post']['hd']=True;self.assertTrue(rt.output_matches(p,'s1',{},record))
   p['shots'][0]['duration']=3;self.assertFalse(rt.output_matches(p,'s1',{},record))
   p['shots'][0]['duration']=1;self.assertTrue(rt.output_matches(p,'s1',{},record))
 def test_one_bypasses_existing_base_cache(self):
  p=self.plan();p['runtime']={'scope':'one'};cache=rt.Star7DirectorBaseCache()
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(cache,'find',return_value=({'version':'old','fingerprint':'base'},'base')),patch.object(rt.Storage,'save_latent',return_value='new') as saved,patch.object(rt.Storage,'load_latent') as restored:
   self.assertEqual(cache.check_lazy_status(p,'s1'),['latent'])
   latent={'samples':'new first pass'};self.assertEqual(cache.save_or_restore(p,'s1',latent),(latent,'new'));saved.assert_called_once();restored.assert_not_called()
 def test_cache_cleanup_keeps_completed_clips_and_old_dependency_compatibility(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   root=Path(tmp);store=rt.Storage(root);plan=self.plan();movie=root/'s1.mp4';movie.write_bytes(b'finished-video');s2=root/'s2.mp4';s2.write_bytes(b'finished-video-2')
   folder=root/'batch'/'s1'/'base';folder.mkdir(parents=True);latent=folder/'v.safetensors';latent.write_bytes(b'latent')
   with store.db('batch') as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',('batch','s1','base','v','fp',str(latent.relative_to(root))))
   store.record_output('batch','s1',rt.run_fingerprint(plan,'s1'),str(movie),24)
   old=rt.run_fingerprint(plan,'s2',legacy_dependencies=True);store.record_output('batch','s2',old,str(s2),24)
   stable=rt.run_fingerprint(plan,'s2');record=store.latest_output('batch','s2');self.assertTrue(rt.output_matches(plan,'s2',{},record))
   cache.clear(root,'batch','checkpoints');self.assertFalse(latent.exists());self.assertEqual(store.stages('batch'),[]);self.assertEqual(movie.read_bytes(),b'finished-video');self.assertEqual(s2.read_bytes(),b'finished-video-2')
   self.assertEqual(stable,rt.run_fingerprint(plan,'s2'));self.assertTrue(rt.output_matches(plan,'s2',{},record))
   plan['shots'][0]['prompt']='different garden';self.assertFalse(rt.output_matches(plan,'s2',{},record))
 def test_own_parameters_ignore_upstream_changes_but_detect_local_edits(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   p=self.plan();record={'fingerprint':rt.run_fingerprint(p,'s2'),'parameter_fingerprint':rt.run_fingerprint(p,'s2',parameter_only=True)}
   p['shots'][0]['prompt']='new garden';p['shots'][0]['seed']=999
   self.assertTrue(rt.parameter_matches(p,'s2',{},record))
   self.assertFalse(rt.output_matches(p,'s2',{},record))
   p['shots'][1]['duration']=2;self.assertFalse(rt.parameter_matches(p,'s2',{},record))
   p['shots'][1]['duration']=1;self.assertTrue(rt.parameter_matches(p,'s2',{},record))
 def test_old_result_recovers_own_settings_from_generation_task(self):
  import json
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   root=Path(tmp);p=self.plan();store=rt.Storage(root);store.record_output(p['id'],'s2',rt.run_fingerprint(p,'s2'),'old.mp4',24)
   folder=root/'projects'/p['id']/'batches';folder.mkdir(parents=True,exist_ok=True)
   (folder/'saved.json').write_text(json.dumps({'plan':p,'prepared':{'output':{}},'results':{'s2':{'path':'old.mp4','prompt_id':'submitted'}}}))
   p['shots'][0]['prompt']='new upstream'
   self.assertTrue(rt.parameter_matches(p,'s2',{},store.latest_output(p['id'],'s2')))
   p['shots'][1]['prompt']='local edit';self.assertFalse(rt.parameter_matches(p,'s2',{},store.latest_output(p['id'],'s2')))
 def test_card_rename_roundtrip_is_not_a_generation_edit(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   p=self.plan();p['assets']=[{'id':'person','kind':'character','name':'小可','description':'a student','aliases':['人物1'],'sequence':1,'media':[]}];p['shots'][0]['prompt']='@{person} 小可说话';p['shots'][0]['name']='镜头一'
   initial=rt.run_fingerprint(p,'s1',parameter_only=True);record={'fingerprint':'unused','parameter_fingerprint':'v3:'+initial}
   p['assets'][0].update(name='小可O',aliases=['人物1','小可'])
   self.assertTrue(rt.parameter_matches(p,'s1',{},record))
   p['assets'][0].update(name='小可',aliases=['人物1','小可','小可O']);p['shots'][0]['prompt']='@{person} 小可说话';p['shots'][0]['name']='新镜头名称'
   self.assertTrue(rt.parameter_matches(p,'s1',{},record))
   p['shots'][0]['prompt']='@{person} 小可O说话';self.assertFalse(rt.parameter_matches(p,'s1',{},record));p['shots'][0]['prompt']='@{person} 小可说话'
   p['assets'][0]['description']='a different identity';self.assertFalse(rt.parameter_matches(p,'s1',{},record))
if __name__=='__main__':unittest.main()
