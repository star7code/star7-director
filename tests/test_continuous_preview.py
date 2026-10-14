import importlib,sys,types,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('continuous_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
preview=importlib.import_module(pkg.__name__+'.preview_film');story=importlib.import_module(pkg.__name__+'.storyboard')
class Tests(unittest.TestCase):
 def test_actual_concat_and_mixed_resolution(self):
  import imageio_ffmpeg,av
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(preview,'data_root',return_value=Path(tmp)):
   root=Path(tmp);clips=[]
   for i,size in enumerate(('64x64','96x64')):
    path=root/(str(i)+'.mp4');subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c='+('red' if i==0 else 'blue')+':s='+size+':r=24:d=0.5','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True);clips.append({'path':path,'duration':.5})
   updates=[];target=preview.build(clips,'projectA',lambda n,m:updates.append(n));self.assertEqual(updates[-1],100);self.assertEqual(updates,sorted(updates))
   with av.open(str(target)) as f:
    frames=list(f.decode(video=0));self.assertEqual(len(frames),24);self.assertEqual(frames[0].width,64);self.assertEqual(frames[-1].width,64)
    self.assertGreater(frames[0].to_ndarray(format='rgb24')[32,32,0],200);self.assertGreater(frames[-1].to_ndarray(format='rgb24')[32,32,2],200)
   modified=target.stat().st_mtime_ns;self.assertEqual(preview.build(clips,'projectA'),target);self.assertEqual(target.stat().st_mtime_ns,modified);self.assertTrue(all(c['path'].exists() for c in clips))
   other=preview.build(clips,'projectB');self.assertTrue(other.is_file())
   newer=preview.build(clips[::-1],'projectA');self.assertNotEqual(newer,target);self.assertFalse(target.exists());self.assertTrue(other.exists());self.assertEqual(len(list((root/'projects').glob('*/previews/*.mp4'))),2)
   bad=root/'bad.mp4';bad.write_bytes(b'broken')
   with self.assertRaises(Exception):preview.build([{'path':bad,'duration':1}],'projectA')
   self.assertTrue(newer.exists());self.assertEqual(len(list((root/'projects').glob('*/previews/*.mp4'))),2);self.assertFalse(list((root/'projects').glob('*/previews/*.txt')))
 def test_exported_storyboard_keeps_parameters(self):
  import json
  plan={'schema_version':'1.0','id':'source','assets':[],'shots':[]}
  exported={**plan,'shots':[{'id':'old1','name':'first','duration':2,'prompt':'garden','seed':123,'next_seed':124,'seed_control':'increment','post':{'hd':True},'continuity':{'mode':'independent'}},{'id':'old2','name':'second','duration':3,'prompt':'trees','seed':456,'post':{},'continuity':{'mode':'selected_frame','source_shot':'old1','frame':12}}]}
  result=story.recognize(plan,json.dumps(exported));self.assertTrue(result['valid'],result['errors']);shots=result['candidate']['shots'];self.assertEqual(shots[0]['seed'],123);self.assertNotIn('next_seed',shots[0]);self.assertEqual(shots[0]['seed_control'],'increment');self.assertTrue(shots[0]['post']['hd']);self.assertEqual(shots[1]['continuity']['source_shot'],shots[0]['id']);self.assertEqual(shots[1]['continuity']['frame'],12)
if __name__=='__main__':unittest.main()
