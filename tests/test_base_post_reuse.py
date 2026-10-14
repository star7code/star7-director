import unittest,tempfile,sys,types,importlib,copy
from pathlib import Path
from unittest.mock import patch
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('post_reuse_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
rt=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def test_batch_matching_does_not_downgrade_and_still_detects_base_edits(self):
  p={'schema_version':'1.0','id':'policy','assets':[],'shots':[{'id':'a','prompt':'garden','duration':1,'post':{'hd':True,'face':True}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   record={'post':copy.deepcopy(p['shots'][0]['post']),'fingerprint':rt.run_fingerprint(p,'a')};p['shots'][0]['post']={'hd':False,'face':False}
   self.assertFalse(rt.output_matches(p,'a',{},record));effective=rt.batch_plan(p,'a',record);self.assertTrue(rt.output_matches(effective,'a',{},record));self.assertEqual(p['shots'][0]['post'],{'hd':False,'face':False})
   p['shots'][0]['duration']=2;self.assertFalse(rt.output_matches(rt.batch_plan(p,'a',record),'a',{},record));self.assertEqual(rt.batch_plan(p,'a',record)['shots'][0]['post'],{'hd':True,'face':True})
 def test_parent_hd_does_not_invalidate_child_base_but_base_regeneration_does(self):
  p={'schema_version':'1.0','id':'reuse','assets':[],'shots':[{'id':'a','prompt':'garden','duration':1,'post':{'hd':False,'face':False}},{'id':'b','prompt':'continue','duration':1,'continuity':{'mode':'motion_redraw','source_shot':'a'},'post':{'hd':False,'face':False}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   store=rt.Storage(tmp);a=store.save_latent('reuse','a','base',rt.run_fingerprint(p,'a',stage='base'),{'samples':torch.zeros(1)});first=Path(tmp)/'a.mp4';first.write_bytes(b'base');store.record_output('reuse','a','fp',str(first),24,post={'hd':False},base_version=a)
   before=rt.run_fingerprint(p,'b',stage='base');b=store.save_latent('reuse','b','base',before,{'samples':torch.zeros(1)})
   p['shots'][0]['post']['hd']=True;p['shots'][1]['post']['hd']=True;hd=Path(tmp)/'a-hd.mp4';hd.write_bytes(b'high resolution');store.record_output('reuse','a','hd_fp',str(hd),24,post={'hd':True},base_version=a)
   self.assertEqual(before,rt.run_fingerprint(p,'b',stage='base'));self.assertEqual(rt.Star7DirectorBaseCache().find(p,'b',{})[0]['version'],b)
   p['shots'][0]['prompt']='new scene';self.assertIsNone(rt.Star7DirectorBaseCache().find(p,'b',{})[0]);p['shots'][0]['prompt']='garden'
   new_a=store.save_latent('reuse','a','base',rt.run_fingerprint(p,'a',stage='base'),{'samples':torch.ones(1)});changed=Path(tmp)/'a-new.mp4';changed.write_bytes(b'new first pass');store.record_output('reuse','a','new_fp',str(changed),24,post={'hd':False},base_version=new_a)
   self.assertNotEqual(before,rt.run_fingerprint(p,'b',stage='base'));self.assertIsNone(rt.Star7DirectorBaseCache().find(p,'b',{})[0])
 def test_legacy_cache_migration_checks_historical_source_generation(self):
  p={'schema_version':'1.0','id':'old','assets':[],'shots':[{'id':'a','prompt':'garden','duration':1},{'id':'b','prompt':'continue','duration':1,'continuity':{'mode':'tail_reference','source_shot':'a'}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   store=rt.Storage(tmp);a=store.save_latent('old','a','base','old_a',{'samples':torch.zeros(1)});first=Path(tmp)/'first.mp4';first.write_bytes(b'old video');store.record_output('old','a','first_fp',str(first),24,base_version=a)
   old_fp=rt.run_fingerprint(p,'b',stage='base',legacy_base_dependencies=True);b=store.save_latent('old','b','base',old_fp,{'samples':torch.zeros(1)})
   hd=Path(tmp)/'hd.mp4';hd.write_bytes(b'upgraded');store.record_output('old','a','hd_fp',str(hd),24,base_version=a)
   self.assertEqual(rt.Star7DirectorBaseCache().find(p,'b',{})[0]['version'],b)
 def test_name_only_edit_keeps_first_pass_cache_for_post_upgrade(self):
  p={'schema_version':'1.0','id':'rename_cache','assets':[{'id':'actor','name':'小洛','kind':'character','description':'student','media':[]}],'shots':[{'id':'a','prompt':'@{actor} speaks','duration':1,'post':{'hd':False,'face':False}}],'runtime':{'scope':'one'}}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   cache=rt.Star7DirectorBaseCache();_,version=cache.save_or_restore(p,'a',{'samples':torch.zeros(1)},{})
   p['assets'][0].update(name='另一个素材名',aliases=['小洛']);p['shots'][0]['post']['face']=True;p['runtime']['scope']='process'
   row,_=cache.find(p,'a',{});self.assertEqual(row['version'],version);self.assertEqual(cache.check_lazy_status(p,'a'),[])
   p['shots'][0]['prompt']='different performance';self.assertIsNone(cache.find(p,'a',{})[0])
if __name__=='__main__':unittest.main()
