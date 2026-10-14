import importlib,sys,types,tempfile,unittest,copy,json,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('smart_frames_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core');rt=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def plan(self):
  return {'schema_version':'1.0','id':'smart_test','assets':[{'id':'actor','name':'小可','kind':'character','media':[{'type':'image','source':'actor.png'}],'voice_id':'voice'},{'id':'voice','name':'音色1','kind':'voice','media':[{'type':'audio','source':'voice.wav'}]}],'shots':[{'id':'a','duration':2,'seed':666,'input_mode':'keyframes','keyframes':{'first':{'source':'first.png'}},'continuity':{'mode':'independent'},'prompt':'subject_definitions:\n<Subject 1> is 小可, using @{actor}.\nsummary:\nSpeak from @{首帧} toward @{尾帧}. Ignore @{尾帧参考}.\nretention_analysis:\nKeep identity.\ndetailed_description:\nSpeak Mandarin: <d>你好</d>.\noverall_soundscape:\nRoom tone.\nnon_diegetic_music:\nPiano.'}]}
 def test_mode_priority_audio_binding_and_missing_frame_are_nonblocking(self):
  p=self.plan();p['prompt_options']={'no_subtitles':True,'no_background_music':True};c=core.compile_shot(p,'a')
  self.assertEqual(c['media']['image'],[]);self.assertEqual(len(c['media']['audio']),1)
  self.assertIn('voice timbre for <Subject 1>',c['prompt']);self.assertIn('<Audio 1>',c['prompt']);self.assertIn('@{actor}',c['prompt'])
  self.assertIn('the supplied first frame',c['prompt']);self.assertIn('@{尾帧}',c['prompt']);self.assertIn('@{尾帧参考}',c['prompt']);self.assertNotIn('<Picture',c['prompt'])
  self.assertTrue(c['prompt'].endswith('non_diegetic_music:\nN/A'));self.assertIn('Screen: no subtitles',c['prompt']);self.assertNotIn('Piano',c['prompt'])
  p['shots'][0]['keyframes']['last']={'source':'last.png'};c=core.compile_shot(p,'a');self.assertIn('the supplied last frame',c['prompt']);self.assertIn('@{尾帧参考}',c['prompt'])
  p['shots'][0]['input_mode']='reference';c=core.compile_shot(p,'a');self.assertEqual(len(c['media']['image']),1);self.assertEqual(c['keyframe_media'],[]);self.assertIn('@{首帧}',c['prompt'])
 def test_native_endpoints_are_sent_with_audio_but_without_visual_refs(self):
  import torch
  p=self.plan();p['shots'][0]['keyframes']['last']={'source':'last.png'};captured={};pixels=torch.zeros(1,64,96,3)
  class Material:
   @staticmethod
   def execute(model,clip,v,a,prompt,*args,**kwargs):captured.update(prompt=prompt,**kwargs);return model,[],{},None,{},None
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(rt,'preflight',return_value=[]),patch.object(rt,'load_image',return_value=pixels),patch.object(rt,'load_audio',return_value={'waveform':torch.zeros(1,2,2400),'sample_rate':48000}),patch.object(rt,'registry',return_value=Material):
   rt.Star7DirectorConditioning().prepare(p,'a',object(),None,None,None)
  self.assertIs(captured['first_frame'],pixels);self.assertIs(captured['last_frame'],pixels);self.assertEqual(captured['ref_images'],{});self.assertIn('ref_audio_0',captured)
 def test_project_package_includes_endpoints_without_library_cards(self):
  packages=importlib.import_module(pkg.__name__+'.packages')
  p={'schema_version':'1.0','id':'package_frames','assets':[],'shots':[{'id':'a','duration':1,'prompt':'@{首帧}','input_mode':'keyframes','keyframes':{'first':{'source':'first.png'}}}]}
  self.assertEqual(len(packages.project_assets(p)),1);self.assertEqual(p['assets'],[])
  self.assertIs(packages.project_assets(p)[0]['media'][0],p['shots'][0]['keyframes']['first'])
 def test_rounded_native_length_keeps_endpoints_and_audio_pitch(self):
  import torch,math
  timing=importlib.import_module(pkg.__name__+'.endpoint_timing')
  rate=8000;wave=torch.sin(torch.arange(round(39/24*rate))*2*math.pi*200/rate).reshape(1,1,-1);images=torch.arange(39).reshape(39,1,1,1)
  result,audio=timing.fit_endpoints(images,{'sample_rate':rate,'waveform':wave},24)
  self.assertEqual(int(result[0]),0);self.assertEqual(int(result[-1]),38);self.assertEqual(audio['waveform'].shape[-1],rate)
  samples=audio['waveform'][0,0,:7000];crossings=((samples[:-1]<0)&(samples[1:]>=0)).sum().item();self.assertAlmostEqual(crossings/(7000/rate),200,delta=5)
 def test_deferred_previous_tail_is_not_a_missing_upload(self):
  p={'schema_version':'1.0','id':'deferred','assets':[],'shots':[{'id':'a','duration':1,'prompt':'scene'},{'id':'b','duration':1,'prompt':'@{首帧}','input_mode':'keyframes','keyframes':{'first':{'from_previous':True}}}]}
  core.validate(p);compiled=core.compile_shot(p,'b');self.assertEqual(compiled['keyframe_media'],[]);self.assertEqual(core.dependency_source(p,'b'),'a');self.assertIn('the supplied first frame',compiled['prompt'])
  packages=importlib.import_module(pkg.__name__+'.packages');self.assertEqual(packages.project_assets(p),[])
  p['shots'][1]['keyframes']['first']={'source':'uploaded.png'};self.assertIsNone(core.dependency_source(p,'b'))
 def test_deferred_frame_is_loaded_at_execution_not_during_editing(self):
  import torch
  p=self.plan();p['shots'].insert(0,{'id':'previous','duration':2,'prompt':'scene'});p['shots'][1]['keyframes']={'first':{'from_previous':True}};captured={};pixels=torch.zeros(1,64,96,3)
  tail=importlib.import_module(pkg.__name__+'.tail_reference')
  class Material:
   @staticmethod
   def execute(model,clip,v,a,prompt,*args,**kwargs):captured.update(kwargs);return model,[],{},None,{},None
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(rt,'preflight',return_value=[]),patch.object(rt,'postprocess_source',return_value={'path':'latest-video'}) as source,patch.object(tail,'load',return_value=pixels),patch.object(rt,'load_audio',return_value={'waveform':torch.zeros(1,2,2400),'sample_rate':48000}),patch.object(rt,'registry',return_value=Material):
   rt.Star7DirectorConditioning().prepare(p,'a',object(),None,None,None)
  source.assert_called_once_with(p,'previous');self.assertIs(captured['first_frame'],pixels)
 def test_reordering_changes_the_dynamic_first_frame_dependency(self):
  p={'schema_version':'1.0','id':'reorder','assets':[],'shots':[{'id':'a','prompt':'a','duration':1},{'id':'b','prompt':'b','duration':1},{'id':'c','prompt':'@{首帧}','duration':1,'input_mode':'keyframes','keyframes':{'first':{'from_previous':True}}}]}
  before=core.compile_shot(p,'c')['fingerprint'];p['shots'][:2]=list(reversed(p['shots'][:2]));self.assertNotEqual(before,core.compile_shot(p,'c')['fingerprint'])
if __name__=='__main__':unittest.main()
