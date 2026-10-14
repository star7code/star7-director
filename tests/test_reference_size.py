import importlib,sys,types,tempfile,unittest,copy,hashlib,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('reference_size_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
sizes=importlib.import_module(pkg.__name__+'.reference_size');runtime=importlib.import_module(pkg.__name__+'.runtime');desk=importlib.import_module(pkg.__name__+'.desk');core=importlib.import_module(pkg.__name__+'.core')
class Tests(unittest.TestCase):
 def test_geometry(self):
  for mode in ('long_edge','megapixels'):
   for kind,cap in [('image',1600),('video',800)]:
    for w,h in [(4000,3000),(1920,1080),(1080,1920),(641,385),(320,192),(24,4000)]:
     out=sizes.target_size(w,h,kind,{'mode':mode});self.assertLessEqual(out[0],w);self.assertLessEqual(out[1],h)
     if min(out)>=32:self.assertEqual(out[0]%32,0);self.assertEqual(out[1]%32,0)
     if mode=='long_edge':self.assertLessEqual(max(out),cap)
     else:self.assertLessEqual(out[0]*out[1],(1.5 if kind=='image' else .5)*1e6)
  self.assertEqual(sizes.target_size(320,192,'image'),(320,192))
 def test_real_loads_and_library(self):
  from PIL import Image
  import imageio_ffmpeg
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as td:
   root=Path(td);image=root/'image.png';Image.new('RGB',(2000,1200),'red').save(image);before=hashlib.sha256(image.read_bytes()).digest()
   with patch.object(runtime,'resolve_media',return_value=image):
    tensor=runtime.load_image('image.png');self.assertEqual(tuple(tensor.shape[1:3]),(960,1600))
    tensor=runtime.load_image('image.png',{'mode':'megapixels'});self.assertLessEqual(tensor.shape[1]*tensor.shape[2],1_500_000);self.assertEqual(tensor.shape[1]%32,0)
   self.assertEqual(before,hashlib.sha256(image.read_bytes()).digest())
   video=root/'video.mp4';subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=blue:s=320x192:r=24:d=0.2','-c:v','libx264',str(video)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   with patch.object(runtime,'resolve_media',return_value=video):frames=runtime.load_video('video.mp4',reference_size={'video_long_edge':160});self.assertEqual(tuple(frames.shape[1:3]),(96,160))
   plan={'schema_version':'1.0','id':'p','assets':[],'shots':[]};library=sizes.AssetLibrary([],{'mode':'megapixels','image_mp':2.2});merged=desk.merge_library(plan,copy.deepcopy(library));self.assertEqual(merged['reference_size']['image_mp'],2.2)
 def test_video_framerate_normalization(self):
  import imageio_ffmpeg
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as td:
   for rate in (12,30):
    path=Path(td)/('fps'+str(rate)+'.mp4');subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i',f'color=c=blue:s=64x64:r={rate}:d=1','-c:v','libx264',str(path)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    with patch.object(runtime,'resolve_media',return_value=path):frames=runtime.load_video('clip.mp4')
    self.assertEqual(len(frames),24)
 def test_cache_and_validation(self):
  plan={'schema_version':'1.0','id':'p','assets':[{'id':'a','kind':'character','name':'人物1','media':[{'type':'image','source':'image.png'}]}],'shots':[{'id':'s','prompt':'@a','duration':2}]}
  original=core.compile_shot(plan,'s')['fingerprint'];plan['reference_size']={'video_long_edge':640};self.assertEqual(core.compile_shot(plan,'s')['fingerprint'],original);plan['reference_size']={'image_long_edge':800};self.assertNotEqual(core.compile_shot(plan,'s')['fingerprint'],original)
  for bad in ({'mode':'oops'},{'image_mp':float('nan')},{'video_long_edge':0},{'image_mp':True}):
   plan['reference_size']=bad
   with self.assertRaises(ValueError):core.validate(plan)
if __name__=='__main__':unittest.main()
