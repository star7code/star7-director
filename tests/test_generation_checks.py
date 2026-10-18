import copy,importlib,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('generation_checks_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
g=importlib.import_module(pkg.__name__+'.generation_checks');core=importlib.import_module(pkg.__name__+'.core')
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_inactive_refs_warn_but_validation_stays_successful(self):
  import execution
  p={'schema_version':'1.0','id':'warning_test','assets':[{'id':'actor','name':'小可','kind':'character','media':[{'type':'image','source':'not_used.png'}]},{'id':'voice','name':'音色1','kind':'voice','description':'Gentle voice.','media':[]}],'shots':[{'id':'a','duration':1,'input_mode':'keyframes','prompt':'@{actor} @{voice} @{首帧} @{尾帧参考} <d>@{参考帧}</d>','continuity':{'mode':'independent'}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(g,'data_root',return_value=Path(tmp)),patch.object(g,'preflight',return_value=[]),patch.object(execution,'validate_prompt',AsyncMock(return_value=(True,None,[],{}))):
   result=await g.validate_generation(p,{'output':{}})
   self.assertTrue(result['valid']);self.assertIn('仍可生成',result['message']);self.assertEqual(result['warnings'][0]['references'],['首帧','尾帧参考'])
   self.assertNotIn('音色1',result['warnings'][0]['references']);self.assertNotIn('参考帧',result['warnings'][0]['references'])
 async def test_future_predecessor_and_frame_bounds_are_checked_before_queue(self):
  import execution
  p={'schema_version':'1.0','id':'validation','assets':[],'shots':[{'id':'a','duration':1,'prompt':'garden'},{'id':'b','duration':1,'prompt':'Start from @{参考帧}.','continuity':{'mode':'selected_frame','source_shot':'a','frame':23}}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(g,'data_root',return_value=Path(tmp)),patch.object(g,'preflight',return_value=[]),patch.object(execution,'validate_prompt',AsyncMock(return_value=(True,None,[],{}))):
   result=await g.validate_generation(p,{'output':{}});self.assertTrue(result['valid'])
   compiled=core.compile_shot(p,'b');self.assertIn('Start from <Picture 1>',compiled['prompt']);self.assertIn('ordinary image reference',compiled['prompt']);self.assertEqual(compiled['continuity_reference']['frame'],23)
   p['shots'][1]['continuity']['frame']=24
   with self.assertRaisesRegex(ValueError,'超出'):await g.validate_generation(p,{'output':{}})
   p['shots'][1]['continuity']={'mode':'motion_redraw','source_shot':'a','context_frames':39}
   with self.assertRaisesRegex(ValueError,'长度不足'):await g.validate_generation(p,{'output':{}})
   p['shots'][1]['continuity']={'mode':'independent'};p['shots'][1]['prompt']='new scene'
   self.assertTrue((await g.validate_generation(p,{'output':{}},'one','b'))['valid'])
 def test_markers_follow_the_chosen_mode(self):
  p={'schema_version':'1.0','id':'markers','assets':[],'shots':[{'id':'a','duration':2,'prompt':'garden'},{'id':'b','duration':2,'prompt':'@{尾帧} @{参考帧}','continuity':{'mode':'selected_frame','source_shot':'a','frame':3}}]}
  result=core.compile_shot(p,'b');self.assertIn('@{尾帧} <Picture 1>',result['prompt']);self.assertNotIn('@{参考帧}',result['prompt'])
  p['shots'][1]['continuity']={'mode':'tail_reference','source_shot':'a'};result=core.compile_shot(p,'b');self.assertIn('<Picture 1> @{参考帧}',result['prompt'])
 def test_selected_frame_reaches_both_first_frame_and_numbered_reference(self):
  import torch
  rt=importlib.import_module(pkg.__name__+'.runtime');continuity=importlib.import_module(pkg.__name__+'.continuity')
  p={'schema_version':'1.0','id':'selected_delivery','assets':[],'shots':[{'id':'a','duration':2,'prompt':'garden'},{'id':'b','duration':1,'prompt':'Continue @{参考帧}.','continuity':{'mode':'selected_frame','source_shot':'a','frame':6}}]}
  captured={};pixels=torch.zeros(1,64,96,3)
  class Material:
   @staticmethod
   def execute(model,clip,video_vae,audio_vae,prompt,*args,**kwargs):
    captured.update(prompt=prompt,**kwargs);return model,[],{'samples':torch.zeros(1)},None,{},None
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(continuity,'source',return_value={'record':{'frame_count':48}}),patch.object(rt.Star7DirectorConditioning,'selected_frame',return_value=pixels),patch.object(rt,'registry',return_value=Material):
   rt.Star7DirectorConditioning().prepare(p,'b',object(),None,None,None)
  self.assertNotIn('first_frame',captured);self.assertIs(captured['ref_images']['ref_image_0'],pixels)
  self.assertIn('Continue <Picture 1>',captured['prompt']);self.assertIn('ordinary image reference',captured['prompt'])
if __name__=='__main__':unittest.main()
