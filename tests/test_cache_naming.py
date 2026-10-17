import importlib,sys,types,tempfile,time,os,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));pkg=types.ModuleType('management_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
cache=importlib.import_module(pkg.__name__+'.cache_management');naming=importlib.import_module(pkg.__name__+'.naming')
class Tests(unittest.TestCase):
 def test_selected_projects_only_and_validation_before_delete(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as temp:
   root=Path(temp);store=cache.Storage(root);files={}
   for pid in ('current','other','keep'):
    p=root/pid/'shot'/'base'/'v.safetensors';p.parent.mkdir(parents=True);p.write_bytes(b'cache');files[pid]=p
    with store.db(pid) as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',(pid,'shot','base','v','fp',str(p.relative_to(root))))
    video=root/(pid+'.mp4');video.write_bytes(b'video');store.record_output(pid,'shot','fp',str(video),24)
   with self.assertRaises(ValueError):cache.clear(root,'current','selected_checkpoints',project_ids=['other','not_real'])
   self.assertTrue(all(p.exists() for p in files.values()))
   result=cache.clear(root,'current','selected_checkpoints',project_ids=['other']);self.assertEqual(result['freed_bytes'],5);self.assertFalse(files['other'].exists());self.assertTrue(files['current'].exists());self.assertTrue(files['keep'].exists())
   with self.assertRaisesRegex(ValueError,'当前项目'):cache.clear(root,'current','selected_checkpoints',project_ids=['current'])
   cache.clear(root,'keep','selected_checkpoints',project_ids=['current']);self.assertFalse(files['current'].exists());self.assertTrue(files['keep'].exists())
   for pid in files:self.assertEqual((root/(pid+'.mp4')).read_bytes(),b'video');self.assertIsNotNone(store.latest_output(pid,'shot'))
 def test_other_projects_and_current_project_are_separate(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as temp:
   root=Path(temp);store=cache.Storage(root);files={}
   for pid in ('current','old'):
    folder=root/pid/'shot'/'base';folder.mkdir(parents=True);p=folder/'v.safetensors';p.write_bytes(b'cache');files[pid]=p
    video=root/(pid+'.mp4');video.write_bytes(b'video');store.record_output(pid,'shot','fp',str(video),24)
    with store.db(pid) as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',(pid,'shot','base','v','fp',str(p.relative_to(root))))
   result=cache.clear(root,'current','other_checkpoints');self.assertEqual(result['freed_bytes'],5);self.assertTrue(files['current'].is_file());self.assertFalse(files['old'].exists());self.assertEqual(result['checkpoint_bytes'],5);self.assertEqual(result['other_checkpoint_bytes'],0)
   with self.assertRaisesRegex(ValueError,'当前项目'):cache.clear(root,'current','checkpoints')
   cache.clear(root,'old','selected_checkpoints',project_ids=['current']);self.assertFalse(files['current'].exists());self.assertTrue(store.cache_was_cleared('current','shot'));self.assertTrue(store.cache_was_cleared('old','shot'))
   for pid in ('current','old'):self.assertEqual((root/(pid+'.mp4')).read_bytes(),b'video');self.assertIsNotNone(store.latest_output(pid,'shot'))
   import torch
   store.save_latent('current','shot','base','new_fp',{'samples':torch.ones(1)})
   self.assertFalse(store.cache_was_cleared('current','shot'));self.assertTrue(store.cache_was_cleared('old','shot'))
 def test_numbering_reuses_current_gaps(self):
  lib={'assets':[{'kind':'character','name':'小红'},{'kind':'character','name':'小李'}]};self.assertEqual(naming.next_name(lib,'character')[0],'人物3');lib['assets']=[{'kind':'character','name':'人物1'},{'kind':'character','name':'小红'},{'kind':'character','name':'人物2'}];self.assertEqual(naming.next_name(lib,'character')[0],'人物4');lib['assets'].pop(0);self.assertEqual(naming.next_name(lib,'character')[0],'人物1');lib['assets']=[];self.assertEqual(naming.next_name(lib,'character')[0],'人物1')
 def test_renamed_slot_is_reserved_until_asset_deleted(self):
  lib={'assets':[{'id':'classroom','kind':'scene','name':'场景1'}]};naming.initialize(lib);lib['assets'][0]['name']='教室'
  self.assertEqual(naming.next_name(lib,'scene'),('场景2',2));lib['assets'].append({'id':'hall','kind':'scene','name':'场景2','sequence':2})
  self.assertEqual(naming.next_name(lib,'scene'),('场景3',3));lib['assets'].pop(0)
  self.assertEqual(naming.next_name(lib,'scene'),('场景1',1));lib['assets'].clear();self.assertEqual(naming.next_name(lib,'scene'),('场景1',1))
 def test_legacy_duplicate_slots_repaired_without_renaming(self):
  lib={'assets':[{'id':'room','kind':'scene','name':'教室','sequence':1},{'id':'hall','kind':'scene','name':'场景1','sequence':1},{'id':'yard','kind':'scene','name':'场景2','sequence':2}]}
  naming.initialize(lib);self.assertEqual([a['sequence'] for a in lib['assets']],[1,3,2]);self.assertEqual([a['name'] for a in lib['assets']],['教室','场景1','场景2']);self.assertEqual(naming.next_name(lib,'scene'),('场景4',4))
 def test_cache_cleanup_keeps_media_outputs_and_fresh_temp(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as temp:
   root=Path(temp);store=cache.Storage(root);folder=root/'project'/'shot'/'base';folder.mkdir(parents=True);latent=folder/'version.safetensors';latent.write_bytes(b'latent-cache')
   media=root/'media';media.mkdir();original=media/'original.png';original.write_bytes(b'original')
   final=root/'film.mp4';final.write_bytes(b'film')
   packages=root/'packages';packages.mkdir();stale=packages/'old.upload';stale.write_bytes(b'old');os.utime(stale,(time.time()-90000,)*2);fresh=packages/'new.upload';fresh.write_bytes(b'new')
   with store.db('project') as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',('project','shot','base','version','fingerprint',str(latent.relative_to(root))))
   before=cache.stats(root,'project');self.assertEqual(before['temporary_bytes'],3);self.assertEqual(before['checkpoint_bytes'],12);self.assertEqual(before['material_bytes'],8)
   cache.clear(root,'project','temporary');self.assertFalse(stale.exists());self.assertTrue(fresh.exists());self.assertTrue(latent.exists())
   with self.assertRaisesRegex(ValueError,'当前项目'):cache.clear(root,'project','checkpoints')
   cache.clear(root,'different','selected_checkpoints',project_ids=['project']);self.assertFalse(latent.exists());self.assertTrue(original.exists());self.assertTrue(final.exists());self.assertEqual(store.stages('project'),[])
 def test_invalid_cache_path_rejected(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as temp:
   root=Path(temp);store=cache.Storage(root);media=root/'media';media.mkdir();file=media/'file.safetensors';file.write_bytes(b'keep')
   with store.db('project') as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',('project','shot','base','version','fp','media/file.safetensors'))
   with self.assertRaises(ValueError):cache.clear(root,'different','selected_checkpoints',project_ids=['project'])
   self.assertTrue(file.exists())
 def test_package_groups_clear_only_selected_temporary_files(self):
  index=importlib.import_module(pkg.__name__+'.package_index')
  with tempfile.TemporaryDirectory(dir=ROOT) as temp:
   root=Path(temp);folder=root/'packages';folder.mkdir();media=root/'media';media.mkdir();original=media/'actor.png';original.write_bytes(b'original')
   first=folder/'first.upload';second=folder/'second.upload';first.write_bytes(b'first');second.write_bytes(b'second')
   for file in (first,second):os.utime(file,(time.time()-90000,)*2)
   one=index.begin(root,'人物包.zip',first);two=index.begin(root,'场景包.zip',second);index.update(root,one,state='failed',sources=['star7-director/actor.png']);index.update(root,two,state='failed')
   groups=cache.stats(root,'project')['packages'];self.assertEqual([g['name'] for g in groups],['人物包.zip','场景包.zip']);self.assertEqual(groups[0]['temporary_bytes'],5)
   cache.clear(root,'project','package',one);self.assertFalse(first.exists());self.assertTrue(second.exists());self.assertTrue(original.exists());self.assertEqual(cache.stats(root,'project')['packages'][1]['temporary_bytes'],6)
if __name__=='__main__':unittest.main()
