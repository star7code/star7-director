import importlib,sys,types,tempfile,json,zipfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('library_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
lib=importlib.import_module(pkg.__name__+'.library_packages');runtime=importlib.import_module(pkg.__name__+'.runtime');assets=importlib.import_module(pkg.__name__+'.assets')
from PIL import Image
class Tests(unittest.TestCase):
 def test_roundtrip_and_duplicate(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);image=root/'girl.png';Image.new('RGB',(32,32),(10,40,80)).save(image)
   library={'name':'测试素材库','reference_size':{'mode':'megapixels','image_mp':1.5,'video_mp':0.5},'assets':[{'id':'girl','kind':'character','name':'女生','aliases':['主角'],'description':'外观','media':[{'type':'image','source':'girl.png','original_name':'girl.png'}]},{'id':'fx','kind':'effect','name':'闪光','description':'镜头出现白色闪光','media':[]}]}
   with patch.object(runtime,'resolve_media',return_value=image),patch.object(lib,'MEDIA',root/'media'):
    archive=lib.export_library(library)
    try:
     with zipfile.ZipFile(archive) as z:self.assertEqual(len(z.namelist()),3);self.assertIn('index.json',z.namelist());self.assertIn('media/女生.png',z.namelist());self.assertIn('media/闪光.txt',z.namelist())
     result=lib.import_library(archive,{'name':'素材库','assets':[]});self.assertEqual(result['reference_size'],library['reference_size']);self.assertEqual(result['name'],library['name']);self.assertEqual(len(result['assets']),2);self.assertEqual(result['assets'][0]['aliases'],['主角']);self.assertEqual(result['assets'][1]['description'],'镜头出现白色闪光')
     before=set((root/'media').iterdir());again=lib.import_library(archive,result);self.assertEqual(len(again['assets']),2);self.assertEqual(before,set((root/'media').iterdir()))
    finally:archive.unlink()
 def test_plain_zip_text_and_rejection(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);archive=root/'plain.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('effect.txt','镜头渐暗');z.writestr('junk.exe',b'junk')
   with patch.object(lib,'MEDIA',root/'media'):
    result=lib.import_library(archive,{'name':'特效库','assets':[]},'effect');self.assertEqual(result['assets'][0]['description'],'镜头渐暗');self.assertIn('junk.exe',result['message'])
    voice=lib.import_library(archive,{'name':'音色库','assets':[]},'voice');self.assertEqual(voice['assets'][0]['kind'],'voice');self.assertEqual(voice['assets'][0]['media'],[])
   with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.png',b'bad')
   with self.assertRaises(ValueError):lib.import_library(archive,{'name':'素材库','assets':[]})
 def test_voice_only_and_binding(self):
  import wave
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);image=root/'person.png';Image.new('RGB',(32,32)).save(image);audio=root/'voice.wav'
   with wave.open(str(audio),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0'*3200)
   library={'name':'人物音色','assets':[{'id':'p','kind':'character','name':'人物','voice_id':'v','media':[{'type':'image','source':'person.png'}]},{'id':'v','kind':'voice','name':'声音','media':[{'type':'audio','source':'voice.wav'}]}]}
   with patch.object(runtime,'resolve_media',side_effect=lambda source:root/source),patch.object(lib,'MEDIA',root/'media'):
    archive=lib.export_library(library)
    try:
     result=lib.import_library(archive,{'name':'素材库','assets':[]});self.assertEqual(result['assets'][0]['voice_id'],result['assets'][1]['id'])
    finally:archive.unlink()
   with self.assertRaises(ValueError):assets.upload_target('voice.mp4','audio')
 def test_corrupt_index_no_files_published(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   root=Path(tmp);archive=root/'bad.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('index.json','{"format":"unknown"}')
   with patch.object(lib,'MEDIA',root/'media'):
    with self.assertRaises(ValueError):lib.import_library(archive,{'name':'素材库','assets':[]})
    self.assertFalse((root/'media').exists())
if __name__=='__main__':unittest.main()
