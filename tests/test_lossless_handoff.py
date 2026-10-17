import copy,importlib,sys,types,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
pkg=types.ModuleType('lossless_handoff_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
h=importlib.import_module(pkg.__name__+'.handoff')
rt=importlib.import_module(pkg.__name__+'.runtime')
motion=importlib.import_module(pkg.__name__+'.vendor.aimixer.h3_motion_context')
continuity=importlib.import_module(pkg.__name__+'.continuity')
from comfy.nested_tensor import NestedTensor


class Tests(unittest.TestCase):
 def av(self,t=82,size=2):
  video=torch.arange(t,dtype=torch.float32).view(1,1,t,1,1).expand(1,24,t,size,size).clone()
  return {'samples':NestedTensor((video,torch.zeros(1,32,2,600)))}
 def plan(self):return {'schema_version':'1.0','id':'handoff','assets':[],'shots':[{'id':'a','duration':11,'prompt':'garden','post':{'hd':True}},{'id':'b','duration':12,'prompt':'continue','continuity':{'mode':'motion_guide','source_shot':'a'},'post':{'hd':True}}]}
 def test_exact_join_for_all_contexts_and_fractional_durations(self):
  for context in (5,22,39,56):
   for head in (0,22,26,39,71):
    for frames in range(context,1441):
     total=5+17*max(0,__import__('math').ceil((head+frames+17-5)/17))
     if total<context+51:continue
     layout=h.window(total,head,frames,context)
     self.assertEqual(layout['guide_end']-layout['guide_frames']+layout['trim_frames'],head+frames)
     self.assertGreaterEqual(layout['trim_frames'],max(context,22))
     self.assertLess(layout['trim_frames'],max(context,22)+17)
     self.assertGreaterEqual(layout['guide_end'],17*(layout['source_end']//17)+22)
     self.assertEqual(layout['guide_end']%17,5)
 def test_11_second_source_does_not_jump_to_unshown_end_or_replay(self):
  self.assertEqual(h.window(277,0,264,22),{'guide_frames':39,'guide_end':277,'trim_frames':26,'source_end':264,'overshoot':13})
 def test_base_guide_uses_exact_source_tokens_without_vae_roundtrip(self):
  previous=self.av();target=self.av(97);plan=self.plan();info={'id':'a','record':{'frame_count':264,'base_version':'base_a','handoff_version':'final_a','post':{'hd':True}}}
  previous[h.EXPORT]={'trim_frames':0}
  class VAE:
   def encode(self,*args):raise AssertionError('VAE re-encode forbidden')
  with patch.object(h,'load_source',return_value=previous):
   out,result,head=h.apply_base(plan,plan['shots'][1],[[torch.zeros(1),{}]],target,info,VAE(),None,{'context_frames':22,'audio':False,'drift_control':False})
  self.assertEqual(head,26);self.assertEqual(result[h.EXPORT]['trim_frames'],26)
  guides=out[0][1]['minimax_keyframes'];self.assertEqual(len(guides),12)
  self.assertTrue(torch.equal(torch.cat([g['latent'] for g in guides],2),previous['samples'].unbind()[0][:,:,70:82]))
  self.assertNotIn(h.KEY,target)
 def test_hd_pin_and_tiled_sampler_restoration_are_bit_exact(self):
  source=self.av(82,4);target=self.av(97,4);original=target['samples'].unbind()[0].clone()
  target[h.KEY]={**h.window(277,0,264,22),'source_shot':'a','source_base_version':'base_a'}
  target[h.EXPORT]={'trim_frames':26}
  positive=[[torch.zeros(1),{'minimax_refs':[{'kind':'image'}],'minimax_keyframes':[{'star7_context_index':0,'resolved_frame_index':0,'latent':torch.zeros(1,24,1,2,2)}]}]]
  with patch.object(continuity,'source',return_value={'id':'a','record':{'base_version':'base_a','handoff_version':'final_a'}}),patch.object(h,'load_source',return_value=source):
   protected,out=h.prepare_refinement(target,positive,self.plan(),'b',{})
  prefix=source['samples'].unbind()[0][:,:,70:82]
  self.assertTrue(torch.equal(protected['samples'].unbind()[0][:,:,:12],prefix))
  mask=protected['noise_mask'].unbind()[0];self.assertTrue((mask[:,:,:12]==0).all());self.assertTrue((mask[:,:,12:]==1).all())
  sampled=dict(protected);sampled['samples']=NestedTensor((protected['samples'].unbind()[0]+7,protected['samples'].unbind()[1]))
  restored=h.restore_prefix(sampled,protected)['samples'].unbind()[0]
  self.assertTrue(torch.equal(restored[:,:,:12],prefix));self.assertTrue(torch.equal(restored[:,:,12:],original[:,:,12:]+7))
  self.assertTrue(torch.equal(target['samples'].unbind()[0],original));self.assertEqual(len(out[0][1]['minimax_refs']),1)
  self.assertTrue(all(k['latent'].shape[-2:]==(4,4) for k in out[0][1]['minimax_keyframes']))
 def test_resolution_and_version_mismatch_are_not_silently_resized(self):
  target=self.av(97,4);target[h.KEY]={**h.window(277,0,264,22),'source_base_version':'old'}
  with patch.object(continuity,'source',return_value={'id':'a','record':{'base_version':'new'}}):
   with self.assertRaisesRegex(ValueError,'版本'):h.prepare_refinement(target,[],self.plan(),'b',{})
  target[h.KEY]['source_base_version']='new'
  with patch.object(continuity,'source',return_value={'id':'a','record':{'base_version':'new'}}),patch.object(h,'load_source',return_value=self.av(82,2)):
   with self.assertRaisesRegex(ValueError,'分辨率'):h.prepare_refinement(target,[],self.plan(),'b',{})
 def test_missing_handoff_cache_is_explicit_without_pixel_fallback(self):
  with self.assertRaisesRegex(ValueError,'不会改用压缩视频'):h.load_source(self.plan(),{'id':'a','record':{'base_version':'exists'}},final=True)
 def test_hd_same_size_shortcut_still_protects_motion_prefix(self):
  hd=importlib.import_module(pkg.__name__+'.vendor.h3.h3_latent_upscale_star7')
  latent=self.av(97,4);members=latent['samples'].unbind();calls=[]
  def prepare(value,positive):
   calls.append(value);result=dict(value);result[h.EXPORT]={'trim_frames':26};return result,positive
  context={'model':object(),'positive':[],'star7_motion_refinement':prepare}
  with patch.object(hd,'_upscale_video',return_value=(dict(latent),members[0],members[1],128,128,128,128,False)),patch.object(hd,'_sampling_profile',return_value=('base','base')),patch.object(hd,'_send_sigma_status'):
   result,_=hd.MiniMaxH3OneClickHDStar7().upscale(latent,context,preset='自定义')
   self.assertEqual(result[h.EXPORT]['trim_frames'],26);self.assertEqual(len(calls),1)
   calls.clear();hd.MiniMaxH3OneClickHDStar7().upscale(latent,context,enable_hd=False);self.assertEqual(calls,[])
 def test_actual_prefix_trim_keeps_exact_video_and_audio_duration(self):
  images=torch.arange(328).view(-1,1,1,1).expand(-1,2,2,3)
  audio={'waveform':torch.arange(328).view(1,1,-1),'sample_rate':24}
  result,sound,count=rt.Star7DirectorTrim().trim(images,audio,self.plan(),'b',{h.EXPORT:{'trim_frames':26}})
  self.assertEqual(count,288);self.assertEqual(int(result[0,0,0,0]),26);self.assertEqual(int(result[-1,0,0,0]),313)
  self.assertTrue(torch.equal(sound['waveform'],audio['waveform'][...,26:314]))
 def test_final_cache_roundtrip_and_output_binding(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
   store=rt.Storage(temp);sample=self.av(82,4);sample[h.EXPORT]={'trim_frames':0,'frame_count':264}
   v=store.save_latent('handoff','a','final','fp',sample)
   store.record_output('handoff','a','fp','fixture.mp4',264,handoff_version=v)
   record=store.latest_output('handoff','a');self.assertEqual(record['handoff_version'],v)
   loaded=store.load_latent('handoff','a','final',v)
   self.assertTrue(torch.equal(loaded['samples'].unbind()[0],sample['samples'].unbind()[0]))
   self.assertEqual(store.output_history('handoff','a')[0]['handoff_version'],v)

if __name__=='__main__':unittest.main()
