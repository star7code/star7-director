import copy,importlib,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
pkg=types.ModuleType('hd_tile_decode_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
hd=importlib.import_module(pkg.__name__+'.vendor.h3.h3_latent_upscale_star7')
decoder=importlib.import_module(pkg.__name__+'.vendor.h3.h3_stream_decode_star7')
rt=importlib.import_module(pkg.__name__+'.runtime')
handoff=importlib.import_module(pkg.__name__+'.handoff')
import comfy.utils,comfy.conds

class TileModel:
 def __init__(self,video,audio,mask,fail_at=None):
  self.packed,self.latent_shapes=comfy.utils.pack_latents([video,audio]);self.latent_image=self.packed.clone();self.noise=torch.zeros_like(self.packed)
  self.video_mask=comfy.conds.CONDRegular(mask);self.audio_mask=comfy.conds.CONDRegular(torch.zeros(1,1,2,5));self.calls=0;self.fail_at=fail_at
  condition={'model_conds':{'denoise_mask':self.video_mask,'audio_denoise_mask':self.audio_mask}}
  # Shared COND wrappers must be cropped once, even if multiple groups use them.
  self.conds={'positive':[condition,condition]}
 def __call__(self,x,sigma,**kwargs):
  self.calls+=1;video,audio=comfy.utils.unpack_latents(x,self.latent_shapes)
  mask_video,mask_audio=comfy.utils.unpack_latents(kwargs['denoise_mask'],self.latent_shapes)
  assert mask_video.shape==video.shape
  assert self.video_mask.cond[:,:,0].count_nonzero()==0
  assert self.audio_mask.cond.count_nonzero()==0
  if self.calls==self.fail_at:raise RuntimeError('synthetic model failure')
  # This is the exact multiply that failed in native H3 with width 42 vs 134.
  return comfy.utils.pack_latents([video*self.video_mask.cond,audio*self.audio_mask.cond])[0]

class Tests(unittest.TestCase):
 def setup_tile(self,fail_at=None):
  video=torch.ones(1,24,2,76,134);audio=torch.ones(1,2,2,5);mask=torch.ones_like(video);mask[:,:,0]=0
  model=TileModel(video,audio,mask[:,:1],fail_at)
  grid,tiles=hd._spatial_tile_plan(video,4,128);proxy=hd._SpatialTileModel(model,model.latent_shapes,grid,tiles)
  full_mask=comfy.utils.pack_latents([mask,torch.zeros_like(audio)])[0]
  return model,proxy,full_mask
 def test_full_width_134_mask_is_cropped_for_all_four_tiles(self):
  model,proxy,mask=self.setup_tile();original=model.video_mask.cond;shape=model.latent_shapes;latent=model.latent_image;noise=model.noise
  out=proxy(model.packed,torch.ones(1),denoise_mask=mask,model_options={'transformer_options':{}})
  video,audio=comfy.utils.unpack_latents(out,shape)
  self.assertTrue(torch.equal(video,original.expand_as(video)));self.assertTrue((audio==0).all());self.assertEqual(model.calls,4)
  self.assertIs(model.video_mask.cond,original);self.assertIs(model.latent_shapes,shape);self.assertIs(model.latent_image,latent);self.assertIs(model.noise,noise)
 def test_original_uncropped_path_reproduces_reported_42_vs_134_error(self):
  model,proxy,mask=self.setup_tile()
  with patch.object(hd,'_tile_video_mask',side_effect=lambda value,*args:value):
   with self.assertRaisesRegex(RuntimeError,r'42.*134'):proxy(model.packed,torch.ones(1),denoise_mask=mask)
 def test_masks_and_model_state_are_restored_when_a_tile_fails(self):
  model,proxy,mask=self.setup_tile(fail_at=2);original=model.video_mask.cond;shape=model.latent_shapes;latent=model.latent_image;options={}
  with self.assertRaisesRegex(RuntimeError,'synthetic'):proxy(model.packed,torch.ones(1),denoise_mask=mask,model_options={'transformer_options':options})
  self.assertIs(model.video_mask.cond,original);self.assertIs(model.latent_shapes,shape);self.assertIs(model.latent_image,latent);self.assertNotIn('star7_spatial_tile_id',options)
 def test_broadcast_masks_preserve_singleton_axes(self):
  mask=torch.ones(1,1,2,1,134);out=hd._tile_video_mask(mask,(1,24,2,76,134),(10,40,34,84));self.assertEqual(tuple(out.shape),(1,1,2,1,50))
  with self.assertRaisesRegex(RuntimeError,'full canvas'):hd._tile_video_mask(torch.ones(1,1,2,76,133),(1,24,2,76,134),(0,76,0,42))
 def test_source_frame_budget_keeps_decoder_guard_without_extra_chunk(self):
  plan={'schema_version':'1.0','id':'budget','assets':[],'shots':[{'id':'a','duration':11,'prompt':'garden'},{'id':'b','duration':12,'prompt':'continue','continuity':{'mode':'motion_guide','source_shot':'a'}}]}
  self.assertEqual(rt.current_shot(plan,'a')[1],277);self.assertEqual(rt.current_shot(plan,'b')[1],328)
  for context in (5,22,39,56):
   plan['continuity_settings']={'context_frames':context}
   plan['shots'].append({'id':'c','duration':1,'prompt':'continue','continuity':{'mode':'motion_guide','source_shot':'b'}})
   for count in range(max(24,context),721):
    plan['shots'][0]['duration']=count/24;total=rt.current_shot(plan,'a')[1]
    layout=handoff.window(total,0,count,context);self.assertEqual(layout['guide_end']-layout['guide_frames']+layout['trim_frames'],count)
    plan['shots'][1]['duration']=count/24;total=rt.current_shot(plan,'b')[1]
    for head in range(max(context,22),max(context,22)+17):
     layout=handoff.window(total,head,count,context);self.assertEqual(layout['guide_end']-layout['guide_frames']+layout['trim_frames'],head+count)
   plan['shots'].pop()
 def test_cpu_validation_rejects_nonfinite_strided_frames(self):
  for dtype in (torch.float16,torch.float32,torch.float64,torch.bfloat16):
   data=torch.ones(3,3,8,10,dtype=dtype).movedim(1,-1);self.assertTrue(decoder._frames_are_finite(data,2))
   for bad in (float('nan'),float('inf'),float('-inf')):
    data[-1,-1,-1,-1]=bad;self.assertFalse(decoder._frames_are_finite(data,2))
   data[-1,-1,-1,-1]=1

if __name__=='__main__':unittest.main()
