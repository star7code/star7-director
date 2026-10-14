import importlib,json,sys,tempfile,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('package_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
packs=importlib.import_module(pkg.__name__+'.packages');runtime=importlib.import_module(pkg.__name__+'.runtime')
from PIL import Image
class Tests(unittest.TestCase):
 def fixture(self,folder):
  image=folder/'人物.png';Image.new('RGB',(32,32),(10,20,30)).save(image)
  plan={'schema_version':'1.0','id':'test_project','assets':[{'id':'actor','kind':'character','name':'人物','media':[{'type':'image','source':'actor.png'}]}],'shots':[{'id':'s1','prompt':'@actor walks','duration':2}]}
  workflow={'nodes':[{'id':2,'type':'Star7DirectorDesk','inputs':[{'name':'asset_library','link':1}],'widgets_values':[json.dumps(plan)]},{'id':1,'type':'Star7DirectorLibrary','widgets_values':['{}']}],'links':[[1,1,0,2,0,'STAR7_DIRECTOR_ASSET_LIBRARY']]}
  return image,plan,workflow
 def test_roundtrip_excludes_cache_and_preserves_original(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   folder=Path(tmp);image,plan,workflow=self.fixture(folder);original=image.read_bytes()
   plan['prompt_options']={'custom_prompt':'Soft lighting.','custom_prompt_enabled':False}
   with patch.object(runtime,'resolve_media',return_value=image),patch.object(packs,'MEDIA',folder/'imported'):
    archive=packs.export_package(plan,workflow,folder)
    try:
     with zipfile.ZipFile(archive) as z:self.assertEqual(len(z.namelist()),3);self.assertFalse(any('cache' in n or '.safetensors' in n for n in z.namelist()))
     result=packs.import_package(archive)
     self.assertNotEqual(result['plan']['id'],plan['id']);self.assertEqual(result['plan']['assets'][0]['id'],'actor')
     self.assertEqual(result['plan']['prompt_options'],plan['prompt_options'])
     self.assertEqual(json.loads(result['workflow']['nodes'][0]['widgets_values'][0])['prompt_options'],plan['prompt_options'])
     imported=list((folder/'imported').glob('*.png'))[0];self.assertEqual(imported.read_bytes(),original)
     self.assertEqual(image.read_bytes(),original)
     self.assertEqual(json.loads(result['workflow']['nodes'][1]['widgets_values'][0])['assets'],result['plan']['assets'])
    finally:archive.unlink(missing_ok=True)
 def test_endpoints_roundtrip_without_adding_asset_cards(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   folder=Path(tmp);image,plan,workflow=self.fixture(folder);plan['assets']=[];plan['shots'][0].update(input_mode='keyframes',prompt='Use @{首帧}.',keyframes={'first':{'source':'frame.png'},'last':{'source':'frame.png'}})
   with patch.object(runtime,'resolve_media',return_value=image),patch.object(packs,'MEDIA',folder/'imported'):
    archive=packs.export_package(plan,workflow,folder)
    try:
     imported=packs.import_package(archive)['plan'];self.assertEqual(imported['assets'],[])
     frames=imported['shots'][0]['keyframes'];self.assertEqual(frames['first']['source'],frames['last']['source']);self.assertTrue(frames['first']['source'].startswith('star7-director/'))
     self.assertTrue((folder/'imported'/frames['first']['source'].removeprefix('star7-director/')).is_file());self.assertEqual(imported['shots'][0]['input_mode'],'keyframes')
    finally:archive.unlink(missing_ok=True)
 def test_traversal_is_rejected(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   archive=Path(tmp)/'bad.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.txt','bad')
   with self.assertRaises(ValueError):packs.import_package(archive)
 def test_tampered_media_rejected_before_publishing(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   folder=Path(tmp);image,plan,workflow=self.fixture(folder)
   with patch.object(runtime,'resolve_media',return_value=image),patch.object(packs,'MEDIA',folder/'imported'):
    archive=packs.export_package(plan,workflow,folder);bad=folder/'bad.zip'
    try:
     with zipfile.ZipFile(archive) as z,zipfile.ZipFile(bad,'w') as out:
      for name in z.namelist():
       content=z.read(name)
       if name=='project.json':
        manifest=json.loads(content);manifest['media']['actor.png']['sha256']='0'*64;content=json.dumps(manifest)
       out.writestr(name,content)
     with self.assertRaises(ValueError):packs.import_package(bad)
     self.assertFalse((folder/'imported').exists())
    finally:archive.unlink(missing_ok=True)
if __name__=='__main__':unittest.main()
