import importlib,sys,types,tempfile,json,zipfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)];pkg=types.ModuleType('text_package_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core');lib=importlib.import_module(pkg.__name__+'.library_packages');cache=importlib.import_module(pkg.__name__+'.cache_management');index=importlib.import_module(pkg.__name__+'.package_index');assets=importlib.import_module(pkg.__name__+'.assets');runtime=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def test_nested_text_and_voice(self):
  plan={'schema_version':'1.0','id':'p','assets':[{'id':'person','kind':'character','name':'人物1','description':'红衣，使用@音色2','media':[]},{'id':'voice','kind':'voice','name':'音色2','description':'低沉平稳','media':[]}],'shots':[{'id':'s','prompt':'@人物1走来','duration':2,'seed':7}]}
  # Plain names require separation; stable IDs work without whitespace.
  plan['shots'][0]['prompt']='@{person}走来';result=core.compile_shot(plan,'s');self.assertEqual(result['prompt'],'红衣，使用低沉平稳走来');self.assertEqual(result['media']['audio'],[])
  plan['assets'][0]['voice_id']='voice';self.assertIn('人物1音色：低沉平稳',core.compile_shot(plan,'s')['prompt']);plan['assets'][1]['description']='@{person}'
  with self.assertRaisesRegex(ValueError,'循环'):core.compile_shot(plan,'s')
 def test_package_snapshot_delete_and_protection(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);folder=root/'packages';folder.mkdir();archive=folder/'one.upload'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('voice.txt','清亮的少女音色')
   pid=index.begin(root,'第一包.zip',archive)
   with patch.object(lib,'MEDIA',root/'media'):
    result=lib.import_library(archive,{'name':'素材库','assets':[]},'voice',pid)
   source=result['assets'][0]['text_file']['source'];file=root/'media'/source.removeprefix('star7-director/');self.assertTrue(file.exists());self.assertIn('第一包_',str(file));snapshot=file.parent/'index.json';before=snapshot.read_bytes()
   (root/'media'/'new.txt').write_text('新素材',encoding='utf-8');result['assets'].append({'id':'new','kind':'voice','name':'音色2','description':'新素材','media':[]});self.assertEqual(snapshot.read_bytes(),before)
   self.assertTrue(cache.stats(root,'p',[source])['packages'][0]['in_use'])
   with self.assertRaisesRegex(ValueError,'不能删除'):cache.clear(root,'p','package',pid,[source])
   store=cache.Storage(root);store.save_project({'schema_version':'1.0','id':'saved','assets':result['assets'],'shots':[]})
   with self.assertRaises(ValueError):cache.clear(root,'p','package',pid)
   (root/'projects'/'saved'/'state.json').unlink();other=folder/'two.upload'
   with zipfile.ZipFile(other,'w') as z:z.writestr('scene.txt','花园')
   second=index.begin(root,'第二包.zip',other)
   with patch.object(lib,'MEDIA',root/'media'):result2=lib.import_library(other,{'name':'素材库','assets':[]},'scene',second)
   secondfile=root/'media'/result2['assets'][0]['text_file']['source'].removeprefix('star7-director/');self.assertNotEqual(file.parent,secondfile.parent)
   cleared=cache.clear(root,'p','packages',active_sources=[result2['assets'][0]['text_file']['source']]);self.assertGreater(cleared['freed_bytes'],0);self.assertFalse(file.exists());self.assertTrue(secondfile.exists());self.assertTrue((root/'media'/'new.txt').exists())
 def test_all_text_categories_roundtrip(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);library={'name':'文本库','assets':[{'id':kind,'kind':kind,'name':kind,'description':'文字-'+kind,'media':[]} for kind in core.KINDS]}
   archive=lib.export_library(library)
   try:
    with patch.object(lib,'MEDIA',root/'media'):result=lib.import_library(archive,{'name':'素材库','assets':[]})
    self.assertEqual(len(result['assets']),6);self.assertTrue(all(not a['media'] and a['description'].startswith('文字-') for a in result['assets']))
   finally:archive.unlink()
if __name__=='__main__':unittest.main()
