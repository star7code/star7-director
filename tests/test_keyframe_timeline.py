import copy, importlib, json, sys, types, unittest, tempfile
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('timeline_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core')
timeline=importlib.import_module(pkg.__name__+'.keyframe_timeline')
parameter=importlib.import_module(pkg.__name__+'.parameter_state')
story=importlib.import_module(pkg.__name__+'.storyboard')


def plan():
 return {'schema_version':'1.0','id':'timeline','assets':[
  {'id':'actor','kind':'character','name':'小可','media':[{'type':'image','source':'actor.png'}]},
  {'id':'pose','kind':'keyframe','name':'姿态','media':[{'type':'image','source':'pose.png'}]}],
  'shots':[{'id':'a','duration':15,'prompt':'Use @{actor}.','input_mode':'keyframes',
   'keyframes':{'first':{'source':'start.png'},'last':{'source':'end.png'}},
   'keyframe_points':[{'id':'middle','time_seconds':12,'source':'pose.png'}]}]}


class Tests(unittest.TestCase):
 def test_timeline_reference_survives_reorder_and_numbers_only_when_mentioned(self):
  p=plan();shot=p['shots'][0]
  shot['keyframe_points'].append({'id':'earlier','time_seconds':3,'source':'earlier.png'})
  marker=timeline.frame_reference_id('middle')
  shot['prompt']='Use @{actor} with @{'+marker+'}.'
  result=core.compile_shot(p,'a')
  self.assertEqual(result['prompt'],'Use <Picture 1> with <Picture 2>.')
  self.assertEqual(result['media']['image'][1]['source'],'pose.png')
  self.assertEqual([c['name'] for c in timeline.reference_cards(shot)],['首帧','关键帧1','关键帧2','尾帧'])
  shot['keyframe_points'][0]['time_seconds']=1
  self.assertEqual(timeline.reference_cards(shot)[1]['id'],marker)
  self.assertEqual(core.compile_shot(p,'a')['media']['image'][1]['source'],'pose.png')
  self.assertIn('@{'+marker+'}',shot['prompt'])

 def test_first_and_last_prompt_references_have_real_picture_slots(self):
  p=plan();p['shots'][0]['prompt']='@{首帧} then @{尾帧}.'
  result=core.compile_shot(p,'a')
  self.assertEqual(result['prompt'],'<Picture 1> then <Picture 2>.')
  self.assertEqual([m['source'] for m in result['media']['image']],['start.png','end.png'])

 def test_unreferenced_guides_do_not_consume_picture_slots(self):
  result=core.compile_shot(plan(),'a')
  self.assertEqual(len(result['media']['image']),1)
  self.assertEqual(len(result['keyframe_media']),3)

 def test_previous_tail_reference_is_deferred_without_missing_upload(self):
  p=plan();p['shots'].insert(0,{'id':'prev','duration':3,'prompt':'scene'})
  shot=p['shots'][1];shot['keyframes']['first']={'from_previous':True};shot['prompt']='@{首帧}'
  result=core.compile_shot(p,'a')
  self.assertEqual(result['prompt'],'<Picture 1>')
  self.assertTrue(result['media']['image'][0]['from_previous'])

 def test_shrink_keeps_draft_but_blocks_generation_until_repaired(self):
  p=plan();shot=p['shots'][0];core.validate(p);timeline.require_valid(shot)
  shot['duration']=10;core.validate(p);core.compile_plan(p)
  self.assertEqual(shot['keyframe_points'][0]['time_seconds'],12)
  restored=json.loads(json.dumps(p));self.assertEqual(restored['shots'][0]['keyframe_points'],shot['keyframe_points'])
  with self.assertRaisesRegex(ValueError,'超出'):timeline.require_valid(shot)
  shot['keyframe_points'][0]['time_seconds']=8;timeline.require_valid(shot)

 def test_reference_numbering_does_not_include_anchors(self):
  result=core.compile_shot(plan(),'a')
  self.assertEqual(result['media']['image'],[{'asset_id':'actor','type':'image','source':'actor.png'}])
  self.assertIn('<Picture 1>',result['prompt'])
  self.assertEqual({m['source'] for m in result['keyframe_media']},{'start.png','end.png','pose.png'})

 def test_duplicate_native_frame_is_rejected(self):
  p=plan();s=p['shots'][0];s['keyframe_points']=[{'id':'a','time_seconds':2,'source':'a.png'}, {'id':'b','time_seconds':2.001,'source':'b.png'}]
  with self.assertRaisesRegex(ValueError,'同一帧'):timeline.require_valid(s)
  s['keyframe_points'][0]['time_seconds']=0
  with self.assertRaisesRegex(ValueError,'同一帧'):timeline.require_valid(s)
  s['keyframe_points']=[{'id':'tail','time_seconds':15,'source':'tail.png'}]
  with self.assertRaisesRegex(ValueError,'同一帧'):timeline.require_valid(s)

 def test_times_and_sources_change_fingerprint_and_explainable_projection(self):
  p=plan();old=parameter.snapshot(p,'a');before=core.compile_shot(p,'a')['fingerprint']
  p['shots'][0]['keyframe_points'][0]['time_seconds']=8
  self.assertNotEqual(before,core.compile_shot(p,'a')['fingerprint'])
  changes=parameter.visible_changes(old,parameter.snapshot(p,'a'))
  self.assertTrue(any(c['field']=='shot.keyframe_points' for c in changes))
  old=parameter.snapshot(p,'a');p['assets'][0]['media'][0]['source']='new_actor.png'
  self.assertTrue(any(c['field']=='assets.actor.media' for c in parameter.visible_changes(old,parameter.snapshot(p,'a'))))

 def test_reference_mode_ignores_stored_timeline(self):
  p=plan();p['shots'][0]['input_mode']='reference';before=core.compile_shot(p,'a')['fingerprint']
  p['shots'][0]['keyframe_points'][0]['time_seconds']=900
  self.assertEqual(before,core.compile_shot(p,'a')['fingerprint'])
  self.assertEqual(core.compile_shot(p,'a')['keyframe_points'],[])

 def test_invalid_numeric_data_is_not_saved(self):
  for value in (True,-1,float('nan'),float('inf'),'2'):
   p=plan();p['shots'][0]['keyframe_points'][0]['time_seconds']=value
   with self.assertRaises(ValueError):core.validate(p)

 def test_missing_image_draft_is_editable_but_not_generated(self):
  p=plan();del p['shots'][0]['keyframe_points'][0]['source'];core.validate(p)
  with self.assertRaisesRegex(ValueError,'图片'):timeline.require_valid(p['shots'][0])

 def test_package_collects_keyframes_outside_library(self):
  packages=importlib.import_module(pkg.__name__+'.packages');p=plan()
  cards=packages.project_assets(p)
  self.assertTrue(any(m.get('source')=='pose.png' for a in cards[2:] for m in a['media']))
  self.assertEqual(len(p['assets']),2)

 def test_native_frame_mapping_preserves_relative_time_and_last(self):
  self.assertEqual(timeline.guide_frame(0,10,243),0)
  self.assertEqual(timeline.guide_frame(10,10,243),242)
  self.assertEqual(timeline.guide_frame(5,10,243),122)

 def test_k_import_resolves_library_images_and_keeps_references(self):
  p=plan();text=json.dumps({'shots':[{'duration':10,'mode':'K','first_frame':'姿态',
     'keyframes':[{'time_seconds':4,'image':'姿态'}], 'prompt':'Use @{小可}.'}]},ensure_ascii=False)
  result=story.recognize(p,text,'replace');self.assertTrue(result['valid'],result)
  s=result['candidate']['shots'][0];self.assertEqual(s['keyframe_points'][0]['source'],'pose.png')
  self.assertIn('<Picture 1>',core.compile_shot(result['candidate'],s['id'])['prompt'])
  bad=text.replace('"time_seconds": 4','"time_seconds": 14')
  self.assertFalse(story.recognize(p,bad,'replace')['valid'])

 def test_runtime_builds_all_guides_and_hd_reencodes_original_pixels(self):
  import torch
  import comfy.nested_tensor
  rt=importlib.import_module(pkg.__name__+'.runtime')
  backend=importlib.import_module(pkg.__name__+'.vendor.h3.h3_face_refine_star7')
  hd=importlib.import_module(pkg.__name__+'.vendor.h3.h3_latent_upscale_star7')
  class Clip:
   def tokenize(self,prompt,**kwargs):return prompt
   def encode_from_tokens_scheduled(self,tokens):return [[torch.zeros(1,2,8),{}]]
  class Vae:
   def encode(self,images):return torch.zeros(1,24,1,images.shape[1]//16,images.shape[2]//16)
  p=plan();p['shots'][0]['prompt']+=' @{'+timeline.frame_reference_id('middle')+'}';p['settings']={'width':96,'height':64,'fps':24};pixels=torch.zeros(1,64,96,3);vae=Vae()
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(rt,'preflight',return_value=[]),patch.object(rt,'load_image',return_value=pixels),patch.object(rt,'registry',return_value=backend.MiniMaxH3MaterialPromptStar7):
   result=rt.Star7DirectorConditioning().prepare(p,'a',object(),Clip(),vae,None)
  positive,latent,context=result[1:4]
  self.assertEqual(len(positive[0][1]['minimax_keyframes']),3)
  self.assertEqual(len(positive[0][1]['minimax_refs']),2)
  self.assertEqual(len(context['keyframe_points']),1)
  self.assertNotIn('minimax_keyframes',context['positive'][0][1])
  video,audio=latent['samples'].tensors
  enlarged={'samples':comfy.nested_tensor.NestedTensor((torch.zeros(1,24,video.shape[2],8,12),audio))}
  refined,_=hd._add_hd_endpoint_guides(context['positive'],enlarged,context)
  guides=refined[0][1]['minimax_keyframes']
  self.assertEqual(len(guides),3)
  self.assertTrue(all(tuple(g['latent'].shape[-2:])==(8,12) for g in guides))
  self.assertEqual(len(refined[0][1]['minimax_refs']),2)


class MotionTimelineTests(unittest.TestCase):
 def fixture(self):
  p=plan();p['shots'].insert(0,{'id':'prev','duration':3,'prompt':'scene'});p['shots'][1]['keyframe_motion']=True
  return p

 def test_motion_uses_previous_shot_and_effective_settings(self):
  p=self.fixture();p['continuity_settings']={'context_frames':39,'audio':False}
  result=core.compile_shot(p,'a');self.assertEqual(result['continuity'],{'mode':'motion_guide','source_shot':'prev'})
  self.assertEqual(core.dependency_source(p,'a'),'prev');self.assertTrue(core.has_motion_successor(p,'prev'))
  before=core._compile_shot(p,'a',parameter_payload=True);self.assertEqual(before['av_handoff']['context_frames'],39);self.assertFalse(before['av_handoff']['audio'])
  self.assertEqual(parameter.editable_inputs(before)['continuity']['mode'],'motion_guide')
  rt=importlib.import_module(pkg.__name__+'.runtime')
  self.assertGreaterEqual(rt.current_shot(p,'prev')[1],22+17*(72//17))
  p['shots'][1]['keyframe_motion']=False;after=core._compile_shot(p,'a',parameter_payload=True)
  self.assertTrue(any(c['field']=='shot.continuity' for c in parameter.visible_changes(before,after)))
  self.assertIsNone(core.dependency_source(p,'a'));self.assertEqual(core.compile_shot(p,'a')['continuity']['mode'],'independent')
  p['shots'][0].update(input_mode='keyframes',keyframe_motion=True)
  with self.assertRaises(ValueError):core.validate(p)

 def test_motion_occupies_first_slot_without_consuming_dormant_image(self):
  p=self.fixture();s=p['shots'][1];s['prompt']='@{首帧} @{尾帧}'
  result=core.compile_shot(p,'a');self.assertNotIn('first',result['keyframes']);self.assertFalse(any(m['source']=='start.png' for m in result['media']['image']+result['keyframe_media']))
  first=core.compile_shot(p,'a')['fingerprint'];s['keyframes']['first']={'source':'dormant.png'};self.assertEqual(core.compile_shot(p,'a')['fingerprint'],first)
  s['keyframe_motion']=False;self.assertEqual(core.compile_shot(p,'a')['keyframes']['first']['source'],'dormant.png')

 def test_motion_offsets_all_guides_and_hd_reuses_correct_indices(self):
  import torch
  import comfy.nested_tensor
  rt=importlib.import_module(pkg.__name__+'.runtime');continuity=importlib.import_module(pkg.__name__+'.continuity')
  backend=importlib.import_module(pkg.__name__+'.vendor.h3.h3_face_refine_star7');hd=importlib.import_module(pkg.__name__+'.vendor.h3.h3_latent_upscale_star7')
  class Clip:
   def tokenize(self,prompt,**kwargs):return prompt
   def encode_from_tokens_scheduled(self,tokens):return [[torch.zeros(1,2,8),{}]]
  class Vae:
   def encode(self,images):return torch.zeros(1,24,1,images.shape[1]//16,images.shape[2]//16)
  handoff=importlib.import_module(pkg.__name__+'.handoff');original_apply=continuity.apply;heads=[]
  def apply(_plan,_shot,positive,latent,*args):
   from comfy_extras.nodes_minimax_h3 import temporal_shape
   video,audio=latent['samples'].tensors;source_frames,source_t,_=temporal_shape(rt.current_shot(_plan,'prev')[1])
   previous={'samples':comfy.nested_tensor.NestedTensor((torch.zeros(1,24,source_t,*video.shape[-2:]),torch.zeros_like(audio)))}
   info={'id':'prev','record':{'frame_count':72,'base_version':'base_previous','post':{}}}
   with patch.object(handoff,'load_source',return_value=previous),patch.object(continuity,'source',return_value=info):result=original_apply(_plan,_shot,positive,latent,*args)
   heads.append(result[2]);return result
  p=self.fixture();p['settings']={'width':96,'height':64,'fps':24};p['continuity_settings']={'audio':False};pixels=torch.zeros(1,64,96,3)
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(rt,'preflight',return_value=[]),patch.object(rt,'load_image',return_value=pixels),patch.object(rt,'registry',return_value=backend.MiniMaxH3MaterialPromptStar7),patch.object(continuity,'check_dependency'),patch.object(continuity,'apply',side_effect=apply) as applied:
   result=rt.Star7DirectorConditioning().prepare(p,'a',object(),Clip(),Vae(),None)
  applied.assert_called_once();context=result[3];self.assertIsNone(context.get('first_frame'));self.assertIsNone(context.get('last_frame'))
  head=heads[0];self.assertGreaterEqual(head,22);self.assertEqual(result[2]['star7_export_timeline']['trim_frames'],head)
  indices=[x['frame_idx'] for x in context['keyframe_points']];self.assertEqual(indices,[head+288,head+359])
  self.assertGreater(len(result[1][0][1]['minimax_keyframes']),2)
  video,audio=result[2]['samples'].tensors
  refined,_=hd._add_hd_endpoint_guides(context['positive'],{'samples':comfy.nested_tensor.NestedTensor((torch.zeros(1,24,video.shape[2],8,12),audio))},context)
  self.assertEqual([g['resolved_frame_index'] for g in refined[0][1]['minimax_keyframes']],indices)

 def test_motion_trim_excludes_context_and_keeps_exact_timeline(self):
  import torch
  rt=importlib.import_module(pkg.__name__+'.runtime');p=self.fixture()
  images=torch.arange(430).reshape(430,1,1,1);audio={'sample_rate':24,'waveform':torch.arange(430).reshape(1,1,430)}
  result,sound,count=rt.Star7DirectorTrim().trim(images,audio,p,'a',{'star7_export_timeline':{'trim_frames':39}})
  self.assertEqual(count,360);self.assertEqual(int(result[0]),39);self.assertEqual(int(result[-1]),398);self.assertEqual(int(sound['waveform'][0,0,0]),39)

 def test_legacy_keyframe_source_is_rejected_before_sampling(self):
  handoff=importlib.import_module(pkg.__name__+'.handoff');p=self.fixture();p['shots'][0]['input_mode']='keyframes'
  base={'samples':[{'shape':(1,24,27,4,6)}]}
  store=types.SimpleNamespace(latest_output=lambda *args:{'frame_count':72,'base_version':'base'},latent_info=lambda *args:base)
  with self.assertRaisesRegex(ValueError,'旧关键帧时间轴'):handoff.check_request(p,'a',{},store=store)
  base['star7_export_timeline']={'trim_frames':0,'keyframe_timeline':1};handoff.check_request(p,'a',{},store=store)


class ImageFitTests(unittest.TestCase):
 def test_tail_revision_tracks_file_changes_without_decoding(self):
  tail=importlib.import_module(pkg.__name__+'.tail_reference')
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   path=Path(tmp)/'clip.mp4';path.write_bytes(b'first');info={'path':path}
   version=tail.output_revision(info);self.assertEqual(version,tail.output_revision(info))
   path.write_bytes(b'changed video');self.assertNotEqual(version,tail.output_revision(info))
   path.unlink()
   with self.assertRaises(OSError):tail.output_revision(info)

 def test_one_decimal_matches_native_guide_position(self):
  self.assertEqual(timeline.round_time(4.166666666666667),4.2)
  self.assertEqual(timeline.round_time(7.1499999999999995),7.2)
  self.assertEqual(timeline.guide_frame(4.166666666666667,10,243),timeline.guide_frame(4.2,10,243))
  self.assertEqual(timeline.guide_frame(0,10,243),0)
  self.assertEqual(timeline.guide_frame(10,10,243),242)

 def test_image_loading_and_previous_tail_crop_keep_center_geometry(self):
  import torch
  from PIL import Image
  rt=importlib.import_module(pkg.__name__+'.runtime')
  tail=importlib.import_module(pkg.__name__+'.tail_reference')
  continuity=importlib.import_module(pkg.__name__+'.continuity')
  sizes=importlib.import_module(pkg.__name__+'.reference_size')
  pixels=torch.zeros(1,64,192,3);pixels[:,:,80:112,0]=1
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   image=Path(tmp)/'source.png';Image.fromarray((pixels[0].numpy()*255).astype('uint8')).save(image)
   original=image.read_bytes()
   with patch.object(rt,'resolve_media',return_value=image),patch.object(sizes,'target_size',return_value=(64,64)):
    loaded=rt.load_image('source.png')
   self.assertEqual(int((loaded[0,32,:,0]>.5).sum()),32)
   self.assertEqual(original,image.read_bytes())
  with patch.object(continuity,'export_tail',return_value=(pixels,None)),patch.object(sizes,'target_size',return_value=(64,64)):
   loaded=tail.load({'path':'fixture'})
  self.assertEqual(int((loaded[0,32,:,0]>.5).sum()),32)

 def test_pure_endpoints_center_crop_without_stretch_and_keep_original_context(self):
  import torch
  import comfy_extras.nodes_minimax_h3 as native
  backend=importlib.import_module(pkg.__name__+'.vendor.h3.h3_face_refine_star7')
  pixels=torch.zeros(1,64,192,3)
  pixels[:,:,80:112,0]=1
  captured={}
  def execute(*args,**kwargs):
   captured.update(kwargs)
   return [[torch.zeros(1,2,8),{}]],{'samples':torch.zeros(1,24,1,4,4)}
  with patch.object(native.MiniMaxH3ImageToVideo,'execute',side_effect=execute):
   result=backend.MiniMaxH3MaterialPromptStar7.execute(object(),None,None,None,'A scene',64,64,5,first_frame=pixels,last_frame=pixels)
  first=captured['first_frame'];self.assertEqual(tuple(first.shape),(1,64,64,3))
  # The central 32px stripe retains its width; stretching would reduce it to ~11px.
  self.assertEqual(int((first[0,32,:,0]>.5).sum()),32)
  self.assertTrue(torch.equal(first,captured['last_frame']))
  self.assertIs(result[4]['first_frame'],pixels)

if __name__=='__main__':unittest.main()
