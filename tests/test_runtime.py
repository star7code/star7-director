import asyncio,importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];COMFY=ROOT.parents[1]
sys.path[:0]=[str(COMFY),str(ROOT)]
package=types.ModuleType('director_runtime_test');package.__path__=[str(ROOT)];sys.modules[package.__name__]=package
runtime=importlib.import_module(package.__name__+'.runtime')
from comfy.nested_tensor import NestedTensor
import torch
from PIL import Image
class Tests(unittest.TestCase):
 def test_film_merge_real_files_preserves_sources(self):
  import subprocess,imageio_ffmpeg
  movie=importlib.import_module(package.__name__+'.combine')
  plan={'schema_version':'1.0','id':'film_test','assets':[],'shots':[{'id':'s1','prompt':'garden','duration':1},{'id':'s2','prompt':'garden','duration':1}]}
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(runtime,'data_root',return_value=Path(tmp)),patch.object(movie,'data_root',return_value=Path(tmp)):
   store=runtime.Storage(tmp);output=Path(tmp)/'output';output.mkdir()
   for shot in plan['shots']:
    path=output/(shot['id']+'.mp4')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=blue:s=32x32:r=24:d=0.3','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    store.record_output(plan['id'],shot['id'],runtime.run_fingerprint(plan,shot['id']),str(path),8)
   merged=movie.combine(plan,{},output)
   self.assertTrue(merged.is_file());self.assertTrue((output/'s1.mp4').is_file());self.assertTrue((output/'s2.mp4').is_file())
   self.assertEqual(movie.profile(merged)[:3],('h264',32,32))
   self.assertRegex(merged.parent.name,r'^film_test-合并导出-\d{8}-\d{6}-\d{6}(?:-\d+)?$');self.assertRegex(merged.name,r'^final-film-[0-9a-f]{12}\.mp4$');self.assertEqual(store.film_path(plan['id'],merged.name),str(merged))
   plan['shots'][0]['duration']=2
   self.assertEqual(movie.outdated_shots(plan,{}),['s1']);self.assertTrue(movie.combine(plan,{},output).is_file())
   plan['shots'][0]['duration']=1;self.assertEqual(movie.outdated_shots(plan,{}),[])
   plan['shots'][0]['prompt']='@{missing}';self.assertTrue(movie.combine(plan,{},output).is_file())
   plan['shots'].append({'id':'s3','duration':1,'prompt':'garden'})
   self.assertTrue(movie.combine(plan,{},output).is_file());selection=movie.select_clips(plan,output);self.assertEqual(selection['missing_shots'],['s3']);self.assertEqual(len(selection['clips']),2)
 def test_audio_reference_is_bounded_and_thumbnail_keeps_original(self):
  import wave,array,hashlib
  assets=importlib.import_module(package.__name__+'.assets')
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   folder=Path(tmp);wav=folder/'声音.wav'
   with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(array.array('h',[1000]*16000).tobytes())
   with patch.object(runtime,'resolve_media',return_value=wav):audio=runtime.load_audio(str(wav),start=.5,duration=.25)
   self.assertEqual(audio['waveform'].shape,(1,2,12000));self.assertEqual(audio['sample_rate'],48000)
   image=folder/'人物.png';Image.new('RGB',(800,600),(20,30,40)).save(image)
   digest=hashlib.sha256(image.read_bytes()).hexdigest();result=assets.finish_upload(image,'人物.png','image',digest)
   self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),digest)
   self.assertTrue(result['thumbnail_source'].endswith('.thumb.webp'))
   with Image.open(image.with_name(image.stem+'.thumb.webp')) as thumb:self.assertEqual(thumb.size,(240,180))
 def test_project_media_namespace_and_bounded_video(self):
  import subprocess,imageio_ffmpeg
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(runtime,'data_root',return_value=Path(tmp)):
   media=Path(tmp)/'media';media.mkdir();image=media/'actor.png';Image.new('RGB',(32,24),(10,20,30)).save(image)
   self.assertEqual(runtime.load_image('star7-director/actor.png').shape,(1,24,32,3))
   with self.assertRaises(ValueError):runtime.resolve_media('star7-director/../../outside.png')
   video=media/'test.mp4'
   subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=blue:s=64x32:r=24:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   frames=runtime.load_video('star7-director/test.mp4',.25,.25)
   self.assertEqual(frames.shape,(6,32,64,3))
 def test_v3_result_and_phase_aligned_guides(self):
  self.assertEqual(runtime.unpack(types.SimpleNamespace(args=(1,2))),(1,2))
  video=torch.arange(17.).reshape(1,1,17,1,1).expand(1,24,17,2,2)
  guides=runtime.previous_guides({'samples':NestedTensor((video,torch.zeros(1,32,2,100)))})
  self.assertEqual([g['resolved_frame_index'] for g in guides],[0,1,5,9,13,17,18])
  self.assertEqual(guides[-1]['latent'][0,0,0,0,0],16)
 def test_real_unicode_image_and_overwrite_revision(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   path=Path(tmp)/'参考 图像.png';Image.new('RGB',(32,32),(255,0,0)).save(path)
   with patch.object(runtime,'resolve_media',return_value=path):
    image=runtime.load_image(str(path));self.assertEqual(tuple(image.shape),(1,32,32,3));self.assertEqual(float(image[0,0,0,0]),1)
 def test_lazy_cache_skips_sampler_and_force_recomputes(self):
  plan={'schema_version':'1.0','id':'cache_test','assets':[],'shots':[{'id':'s1','duration':2,'prompt':'garden','seed':7,'continuity':{'mode':'independent'},'post':{'hd':False,'face':False}}]}
  latent={'samples':NestedTensor((torch.zeros(1,24,17,2,2),torch.zeros(1,32,2,93)))}
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(runtime,'data_root',return_value=Path(tmp)):
   cache=runtime.Star7DirectorBaseCache()
   self.assertEqual(cache.check_lazy_status(plan,'s1'),['latent'])
   _,version=cache.save_or_restore(plan,'s1',latent=latent)
   self.assertEqual(cache.check_lazy_status(plan,'s1'),[])
   plan['shots'][0]['post']['hd']=True
   self.assertEqual(cache.check_lazy_status(plan,'s1'),[])
   loaded,second=cache.save_or_restore(plan,'s1')
   self.assertEqual(version,second)
   plan['runtime']={'scope':'one'}
   self.assertEqual(cache.check_lazy_status(plan,'s1'),['latent'])
   plan['runtime']={'scope':'process'};plan['shots'][0]['seed']=99
   with self.assertRaises(ValueError):cache.check_lazy_status(plan,'s1')
 def test_conditioning_adapter_and_trim(self):
  plan={'schema_version':'1.0','id':'test','assets':[],'settings':{'width':640,'height':384,'fps':24},'shots':[{'id':'s1','duration':2,'prompt':'quiet garden','seed':7,'continuity':{'mode':'independent'}}]}
  seen={}
  class Conditioner:
   @classmethod
   def execute(cls,model,clip,v,a,prompt,w,h,length,**kwargs):
    seen.update(prompt=prompt,length=length,kwargs=kwargs)
    return types.SimpleNamespace(args=(model,[[torch.zeros(1),{}]],{'samples':NestedTensor((torch.zeros(1,24,17,24,40),torch.zeros(1,32,2,93)))},None,{},''))
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(runtime,'data_root',return_value=Path(tmp)),patch.object(runtime,'registry',return_value=Conditioner):
   out=runtime.Star7DirectorConditioning().prepare(plan,'s1',object(),object(),object(),object())
   self.assertEqual(seen['length'],56);self.assertEqual(out[4],7);self.assertEqual(out[8],'s1')
   plan['shots'].append({'id':'s2','duration':2,'prompt':'continue garden','seed':8,'continuity':{'mode':'previous_latent','source_shot':'s1'}})
   images=torch.zeros(73,2,2,3);audio={'waveform':torch.zeros(1,2,97334),'sample_rate':32000}
   frames,sound,count=runtime.Star7DirectorTrim().trim(images,audio,plan,'s2')
   self.assertEqual(count,48);self.assertEqual(len(frames),48);self.assertEqual(sound['waveform'].shape[-1],64000)
 def test_reference_tokens_reach_h3_with_matching_material_order(self):
  assets=[{'id':'girl','kind':'character','name':'小红','voice_id':'voice','media':[{'type':'image','source':'girl.png'}]},{'id':'scene','kind':'scene','name':'庭院','media':[{'type':'image','source':'scene.png'}]},{'id':'video','kind':'video','name':'视频1','media':[{'type':'video','source':'clip.mp4'}]},{'id':'voice','kind':'voice','name':'音色1','media':[{'type':'audio','source':'voice.wav'}]},{'id':'effect','kind':'effect','name':'特效1','description':'镜头渐暗','media':[]}]
  plan={'schema_version':'1.0','id':'test','assets':assets,'shots':[{'id':'s1','duration':2,'prompt':'在@{scene}中，用@{girl}替换@{video}的人物，@{effect}。再次出现@{girl}。','continuity':{'mode':'independent'}}]}
  seen={}
  class Conditioner:
   @classmethod
   def execute(cls,model,clip,v,a,prompt,w,h,length,**kwargs):
    seen.update(prompt=prompt,kwargs=kwargs);return types.SimpleNamespace(args=(model,[],{'samples':None},None,{},''))
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(runtime,'data_root',return_value=Path(tmp)),patch.object(runtime,'registry',return_value=Conditioner),patch.object(runtime,'preflight',return_value=[]),patch.object(runtime,'load_image',side_effect=lambda source,*args:source),patch.object(runtime,'load_video',side_effect=lambda source,*args:source),patch.object(runtime,'load_audio',side_effect=lambda source,*args:source):
   out=runtime.Star7DirectorConditioning().prepare(plan,'s1',object(),object(),object(),object());self.assertEqual(seen['prompt'],'在<Picture 1>中，用<Picture 2>替换<Video 1>的人物，镜头渐暗。再次出现<Picture 2>。\n小红音色：<Audio 1>');self.assertEqual(seen['kwargs']['ref_images'],{'ref_image_0':'scene.png','ref_image_1':'girl.png'});self.assertEqual(seen['kwargs']['ref_audio_0'],'voice.wav');self.assertEqual(seen['kwargs']['ref_video_0'],'clip.mp4');self.assertEqual(out[3]['identity_reference'],'girl.png');self.assertNotIn('reference-chip',seen['prompt'])
   plan['assets'].reverse();plan['assets'][next(i for i,a in enumerate(plan['assets']) if a['id']=='girl')]['name']='小李';runtime.Star7DirectorConditioning().prepare(plan,'s1',object(),object(),object(),object());self.assertIn('用<Picture 2>替换<Video 1>',seen['prompt']);self.assertIn('小李音色：<Audio 1>',seen['prompt'])
if __name__=='__main__':unittest.main()
