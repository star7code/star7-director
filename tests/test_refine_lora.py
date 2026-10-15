import sys,types,importlib,unittest,copy
from pathlib import Path
from unittest.mock import patch
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('refine_lora_tests');pkg.__path__=[str(ROOT/'vendor'/'h3')];sys.modules[pkg.__name__]=pkg
options=importlib.import_module(pkg.__name__+'.refine_model_options')
hd=importlib.import_module(pkg.__name__+'.h3_latent_upscale_star7')
class Tests(unittest.TestCase):
 def test_no_lora_clone_and_choices(self):
  from comfy.model_patcher import ModelPatcher
  model=ModelPatcher(torch.nn.Linear(2,2),torch.device('cpu'),torch.device('cpu'))
  model.add_patches({'weight':('diff',(torch.ones(2,2),))},1.0)
  model.object_patches['model_sampling']='sampling-config';model.model_options['keep']='attention-config'
  original=dict(model.patches);result,label=options.apply_selected_lora(None,model,options.NO_LORA,0)
  self.assertEqual(result.patches,{});self.assertEqual(model.patches,original);self.assertNotEqual(result.patches_uuid,model.patches_uuid)
  self.assertEqual(result.object_patches,model.object_patches);self.assertEqual(result.model_options,model.model_options)
  with patch.object(options.folder_paths,'get_filename_list',return_value=['turbo.safetensors']):self.assertEqual(options.lora_choices()[:2],[options.INHERIT_FIRST_PASS,options.NO_LORA])
  self.assertEqual(hd._sampling_profile(model,{},None,6,options.NO_LORA)[0],'base')
 def test_strength_zero_really_skips_sampler_and_lora_and_reports_zero(self):
  from comfy.nested_tensor import NestedTensor
  audio=torch.zeros(1,32,2,10);video=torch.zeros(1,24,7,4,4);latent={'samples':NestedTensor((video,audio))}
  output={'samples':NestedTensor((torch.zeros(1,24,7,8,8),audio))}
  with patch.object(hd,'_sampling_profile',return_value=('turbo','Turbo')),patch.object(hd,'_upscale_video',return_value=(output,output['samples'].tensors[0],audio,64,64,128,128,True)),patch.object(hd,'_sample_hd_refinement',side_effect=AssertionError('must not sample')),patch.object(hd,'apply_selected_lora',side_effect=AssertionError('must not load lora')),patch.object(hd,'_send_sigma_status'):
   result,report=hd.MiniMaxH3OneClickHDStar7().upscale(latent,{'model':object(),'positive':[]},preset='自定义',refine_steps=2,refine_strength=0)
   self.assertIs(result,output);self.assertIn('refine=0 step(s)',report);self.assertIn('refine=0.00s',report);self.assertTrue(torch.equal(result['samples'].tensors[1],audio))
if __name__=='__main__':unittest.main()
