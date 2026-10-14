import importlib,sys,types,tempfile,unittest,json,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('project_store_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
store=importlib.import_module(pkg.__name__+'.project_store');rt=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def test_save_clone_cache_fingerprint_and_delete_preserve_video(self):
  import torch
  from PIL import Image
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(store,'data_root',return_value=Path(tmp)),patch.object(rt,'data_root',return_value=Path(tmp)):
   root=Path(tmp);(root/'media').mkdir();im=root/'media/actor.png';Image.new('RGB',(64,32)).save(im)
   p={'schema_version':'1.0','id':'source','title':'Original','assets':[{'id':'actor','name':'小可','kind':'character','media':[{'type':'image','source':'star7-director/actor.png'}]}],'shots':[{'id':'a','name':'a','duration':1,'seed':666,'next_seed':667,'seed_control':'increment','prompt':'@{actor}','continuity':{'mode':'independent'}}]}
   workflow={'nodes':[{'id':1,'type':'Star7DirectorDesk','widgets_values':[json.dumps(p)]}],'links':[]}
   db=rt.Storage(root);basefp=rt.run_fingerprint(p,'a',stage='base');version=db.save_latent(p['id'],'a','base',basefp,{'samples':torch.zeros(1)});video=root/'kept.mp4';video.write_bytes(b'finished-video');fp=rt.run_fingerprint(p,'a');db.record_output(p['id'],'a',fp,str(video),24,post={'hd':False},base_version=version)
   saved=store.save(p,workflow,True);managed=saved['plan'];self.assertTrue(managed['assets'][0]['media'][0]['source'].startswith('star7-project/source/media/'))
   self.assertEqual(fp,rt.run_fingerprint(managed,'a'));self.assertEqual(basefp,rt.run_fingerprint(managed,'a',stage='base'));self.assertTrue(db.stages('source')[0]['artifact'].startswith('projects'))
   duplicate=store.clone(managed,saved['workflow']);copyplan=duplicate['plan'];self.assertNotEqual(copyplan['id'],'source');self.assertTrue(copyplan['title'].startswith('NP-'));self.assertEqual(copyplan['shots'][0]['seed'],666);self.assertEqual(copyplan['shots'][0]['next_seed'],667)
   self.assertEqual(fp,rt.run_fingerprint(copyplan,'a'));self.assertTrue(rt.output_matches(copyplan,'a',{},db.latest_output(copyplan['id'],'a')));self.assertEqual(rt.Star7DirectorBaseCache().find(copyplan,'a',{})[0]['version'],version)
   self.assertEqual(db.latest_output(copyplan['id'],'a')['path'],str(video));self.assertFalse(list(store.folder(copyplan['id']).rglob('*.mp4')))
   changed=store.rename(copyplan['id'],'Renamed');self.assertEqual(changed['plan']['title'],'Renamed');self.assertEqual(len(store.listing()),2)
   caches=importlib.import_module(pkg.__name__+'.cache_management');caches.clear(root,copyplan['id'],'checkpoints');self.assertEqual(db.stages(copyplan['id']),[]);self.assertTrue(db.stages('source'));self.assertEqual(video.read_bytes(),b'finished-video')
   store.delete(copyplan['id']);self.assertEqual(len(store.listing()),1);self.assertEqual(video.read_bytes(),b'finished-video');self.assertTrue(db.latest_output('source','a'));self.assertTrue(rt.Star7DirectorBaseCache().find(managed,'a',{})[0]);self.assertTrue(list((root/'project-trash').iterdir()))
 def test_new_project_is_empty_and_has_unique_id(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(store,'data_root',return_value=Path(tmp)):
   p={'schema_version':'1.0','id':'old','title':'Old','shot_sequence':88,'assets':[],'shots':[{'id':'a','duration':2,'prompt':'story'}]}
   new=store.create(p,{'nodes':[{'type':'Star7DirectorDesk','widgets_values':[json.dumps(p)]}]})
   self.assertEqual(new['plan']['assets'],[]);self.assertEqual(new['plan']['shots'],[]);self.assertEqual(new['plan']['shot_sequence'],0);self.assertEqual(p['shot_sequence'],88);self.assertNotEqual(new['plan']['id'],'old');self.assertEqual(json.loads(new['workflow']['nodes'][0]['widgets_values'][0])['id'],new['plan']['id'])
 def test_failed_copy_rolls_back_new_project_only(self):
  import torch
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(store,'data_root',return_value=Path(tmp)),patch.object(rt,'data_root',return_value=Path(tmp)):
   root=Path(tmp);p={'schema_version':'1.0','id':'original','title':'Original','assets':[],'shots':[{'id':'a','duration':1,'prompt':'garden'}]};db=rt.Storage(root)
   db.save_latent('original','a','base','fingerprint',{'samples':torch.zeros(1)});store.save(p,{})
   with patch.object(store,'copy_atomic',side_effect=OSError('Disk full')):
    with self.assertRaises(OSError):store.clone(p,{})
   self.assertEqual([r['id'] for r in store.listing()],['original']);self.assertTrue(db.stages('original'));self.assertEqual(len(list((root/'projects').iterdir())),1)
 def test_legacy_library_media_container_is_not_listed_or_deleted(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(store,'data_root',return_value=Path(tmp)):
   root=Path(tmp)
   for pid in ('library_610','real_project'):
    store.atomic(root/'projects'/pid/'project.json',{'plan':{'id':pid,'title':pid,'shots':[]},'saved_at':'2026-10-14'})
   media=root/'projects'/'library_610'/'media'/'needed.png';media.parent.mkdir();media.write_bytes(b'preserve references')
   self.assertEqual([p['id'] for p in store.listing()],['real_project']);self.assertEqual(media.read_bytes(),b'preserve references')
if __name__=='__main__':unittest.main()
