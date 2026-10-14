import unittest,importlib,types,sys,copy
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('native_continuity_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
rt=importlib.import_module(pkg.__name__+'.runtime');core=importlib.import_module(pkg.__name__+'.core');motion=importlib.import_module(pkg.__name__+'.vendor.aimixer.h3_motion_context');redraw=importlib.import_module(pkg.__name__+'.vendor.aimixer.h3_latent_continue')
from comfy.nested_tensor import NestedTensor
class Tests(unittest.TestCase):
 def av(self,t=27):return {'samples':NestedTensor((torch.zeros(1,24,t,4,4),torch.zeros(1,32,2,150)))}
 def test_context_windows(self):
  for n,steps in [(5,2),(22,7),(39,12),(56,17)]:
   blocks,offsets,covered,end,gap=motion._video_tail_blocks(self.av(),n);self.assertEqual(len(blocks),steps);self.assertEqual(covered,n);self.assertEqual(offsets[0],0);self.assertEqual(gap,0)
 def test_native_guide_preserves_refs_and_no_global_patch(self):
  from comfy.ldm.minimax.model import PackedLayout
  from comfy.model_base import MiniMaxH3
  layout=PackedLayout.__init__;payload=MiniMaxH3.extra_conds
  cond=[[torch.zeros(1),{'minimax_refs':[{'kind':'image','latent':torch.ones(1,24,1,4,4)}]}]]
  out,head,gap=motion.apply_motion_context(cond,self.av(),vae=None,context_length=22,context_latent=self.av(),continue_audio=False)
  self.assertEqual(head,22);self.assertEqual(gap,0);self.assertEqual(len(out[0][1]['minimax_keyframes']),7);self.assertEqual([k[motion.CTX_FRAME_KEY] for k in out[0][1]['minimax_keyframes']],[0,1,5,9,13,17,18]);self.assertEqual(len(out[0][1]['minimax_refs']),1);self.assertIs(layout,PackedLayout.__init__);self.assertIs(payload,MiniMaxH3.extra_conds)
 def test_redraw_masks(self):
  previous=self.av();previous['samples'].tensors[0].fill_(.5)
  out,head,gap=redraw.apply_latent_continue(self.av(),prev_av=previous,prev_tail=None,vae=None,context_length=22,pin_audio=False,seam_min_mask=.65)
  self.assertEqual(head,22);self.assertEqual(gap,0);video,audio=out['samples'].unbind();mask,_=out['noise_mask'].unbind();self.assertTrue(torch.all(video[:,:,:7]==.5));self.assertAlmostEqual(float(mask.min()),.65,places=6);self.assertGreaterEqual(float(mask.min()),.64);self.assertLess(float(mask.min()),1);self.assertTrue(torch.all(mask[:,:,7:]==1))
 def test_modes_validation_and_duration(self):
  for mode in ('previous_latent','motion_guide','motion_redraw'):
   plan={'schema_version':'1.0','id':'test','assets':[],'shots':[{'id':'a','duration':3,'prompt':'garden'},{'id':'b','duration':1.5,'prompt':'garden','continuity':{'mode':mode,'source_shot':'a'}}],'continuity_settings':{'context_frames':39,'audio':True,'redraw':.65}}
   core.validate(plan);shot,frames,head=rt.current_shot(plan,'b');self.assertEqual(head,39);self.assertGreaterEqual(frames,75)
   plan['continuity_settings']['context_frames']=10
   with self.assertRaises(ValueError):core.validate(plan)
if __name__=='__main__':unittest.main()
