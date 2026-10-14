import unittest,importlib,sys,types,tempfile,copy,json,subprocess
from pathlib import Path
from unittest.mock import patch
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('tail_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
core=importlib.import_module(pkg.__name__+'.core');rt=importlib.import_module(pkg.__name__+'.runtime');tail=importlib.import_module(pkg.__name__+'.tail_reference');continuity=importlib.import_module(pkg.__name__+'.continuity');story=importlib.import_module(pkg.__name__+'.storyboard')
def plan():
 return {'schema_version':'1.0','id':'tail_test','settings':{'width':64,'height':32},'assets':[{'id':'actor','name':'白衣','kind':'character','media':[{'type':'image','source':'actor.png'}]},{'id':'room','name':'教室','kind':'scene','media':[{'type':'image','source':'room.png'}]}],'shots':[{'id':'a','duration':1,'seed':666,'prompt':'garden','continuity':{'mode':'independent'}},{'id':'b','duration':1,'seed':666,'prompt':'subject_definitions: <Subject 1> is @{白衣}. <Subject 2> is @{教室}.\nsummary: reverse shot\nretention_analysis: retain clothing\ndetailed_description: Chalkboard behind the white-clothed woman.\noverall_soundscape: room tone\nnon_diegetic_music: N/A','continuity':{'mode':'tail_reference','source_shot':'a'}}]}
class Tests(unittest.TestCase):
 def test_virtual_token_mode_priority_and_scope(self):
  p=plan();p['shots'][1]['prompt']='Use @{尾帧} for placement, @{白衣} for identity and @{教室} for architecture. Use @{尾帧} for the requested new viewpoint.'
  c=core.compile_shot(p,'b');self.assertEqual(c['continuity_reference']['label'],'<Picture 3>');self.assertNotIn('@',c['prompt']);self.assertEqual(len(c['media']['image']),2);self.assertIn('Use <Picture 3> for placement, <Picture 1> for identity and <Picture 2>',c['prompt'])
  for mode in ('motion_redraw','independent'):
   p['shots'][1]['continuity']={'mode':mode,**({'source_shot':'a'} if mode!='independent' else {})}
   c=core.compile_shot(p,'b');self.assertNotIn('continuity_reference',c);self.assertEqual(c['prompt'].count('@{尾帧}'),2);self.assertNotIn('<Picture 3>',c['prompt']);self.assertEqual(len(c['media']['image']),2);self.assertEqual(c['continuity']['mode'],mode)
  p=plan();p['shots'][1]['continuity']={'mode':'motion_redraw','source_shot':'a'};p['shots'][1]['prompt']='@{白衣} in @{教室}';c=core.compile_shot(p,'b');self.assertNotIn('continuity_reference',c);self.assertNotIn('<Picture 3>',c['prompt'])
  p['assets'].append({'id':'actual_tail','name':'尾帧','kind':'scene','media':[{'type':'image','source':'another.png'}]});p['shots'][1]['prompt']='@{actual_tail} is a real material';c=core.compile_shot(p,'b');self.assertIn('<Picture 1>',c['prompt']);self.assertNotIn('continuity_reference',c)
  p=plan();p['assets'].append({'id':'text_tail','name':'构图','kind':'effect','description':'Frame the subject using @{尾帧}.','media':[]});p['shots'][1]['prompt']='@{构图}';c=core.compile_shot(p,'b');self.assertIn('using <Picture 1>',c['prompt']);self.assertNotIn('@',c['prompt'])
  for spelling in ('@尾帧','@{伪帧}','@{tail_frame}'):
   p=plan();p['shots'][1]['prompt']=spelling
   with self.assertRaisesRegex(ValueError,'Unknown material'):core.compile_shot(p,'b')
 def test_import_virtual_reference_and_explicit_mode(self):
  p=plan();result=story.recognize(p,'{"shots":[{"duration":3,"mode":"F","prompt":"Use @{尾帧} for a new close-up."}]}');self.assertTrue(result['valid'],result['errors']);self.assertIn('@{尾帧}',result['candidate']['shots'][-1]['prompt']);self.assertIn('<Picture 1>',result['rows'][0]['model_prompt'])
  result=story.recognize(p,'{"shots":[{"duration":3,"mode":"R","prompt":"Ignore @{尾帧}."}]}');self.assertTrue(result['valid'],result['errors']);self.assertIn('@{尾帧}',result['rows'][0]['model_prompt']);self.assertEqual(result['rows'][0]['media_counts']['image'],0);self.assertEqual(result['candidate']['shots'][-1]['continuity']['mode'],'motion_redraw')
 def test_numbering_budget_fingerprint_and_format(self):
  p=plan();before=copy.deepcopy(p);c=core.compile_shot(p,'b');self.assertEqual(c['continuity_reference']['label'],'<Picture 3>');self.assertIn("<Picture 3> is the preceding clip's final frame",c['prompt']);self.assertNotIn('<Video',c['prompt']);self.assertEqual(len(c['media']['image']),2);self.assertEqual(p,before)
  self.assertEqual(rt.current_shot(p,'b')[2],0)
  five=plan();five['assets'][1]['media']=[{'type':'image','source':f'angle_{i}.png'} for i in range(4)]+[{'type':'image','source':'angle_0.png'}]
  compiled=core.compile_shot(five,'b');self.assertEqual(len(compiled['media']['image']),5);self.assertEqual(compiled['continuity_reference']['label'],'<Picture 6>')
  p['shots'][0]['prompt']='changed';self.assertNotEqual(c['fingerprint'],core.compile_shot(p,'b')['fingerprint'])
  p=plan();p['assets'][1]['media']=[{'type':'image','source':str(i)+'.png'} for i in range(8)]
  with self.assertRaisesRegex(ValueError,'最多8张'):core.compile_shot(p,'b')
  p=plan();p['shots'][1]['prompt']='A close-up of the same woman.';p['prompt_options']={'no_subtitles':True};c=core.compile_shot(p,'b');self.assertIn('subject_definitions:',c['prompt']);self.assertEqual(c['continuity_reference']['label'],'<Picture 1>');self.assertTrue(c['prompt'].endswith('Screen: no subtitles, no on-screen text, no watermark.'));self.assertEqual(tail.augment_prompt(c['prompt'],'<Picture 1>'),c['prompt'])
 def test_import_defaults_and_explicit_f(self):
  p=plan();p['shots']=[]
  result=story.recognize(p,json.dumps({'shots':[{'duration':1,'prompt':'garden'},{'duration':1,'prompt':'continue'},{'duration':1,'mode':'F','prompt':'reverse'}]}),'replace');self.assertTrue(result['valid'],result['errors']);self.assertEqual([s['continuity']['mode'] for s in result['candidate']['shots']],['independent','motion_redraw','tail_reference']);self.assertEqual(result['rows'][2]['media_counts']['image'],1);self.assertEqual(result['rows'][2]['continuity_reference']['label'],'<Picture 1>')
  result=story.recognize(p,'{"shots":[{"duration":1,"mode":"F","prompt":"reverse"}]}','replace');self.assertFalse(result['valid'])
 def test_reads_actual_final_frame_and_no_latent_fallback(self):
  import imageio_ffmpeg
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   path=Path(tmp)/'final.mkv'
   subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=red:s=64x32:r=24:d=0.5','-f','lavfi','-i','color=c=blue:s=64x32:r=24:d=0.5','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0','-c:v','ffv1',str(path)],check=True,capture_output=True)
   import folder_paths
   with patch.object(folder_paths,'get_output_directory',return_value=tmp):pixels=tail.load({'path':path,'record':{'frame_count':24}})
   self.assertEqual(tuple(pixels.shape),(1,32,64,3));self.assertGreater(float(pixels[0,:,:,2].mean()),.9);self.assertLess(float(pixels[0,:,:,0].mean()),.05)
  with self.assertRaisesRegex(ValueError,'成品'):tail.load({'latent':{}})
 def test_prepare_passes_numbered_image_and_role_to_real_adapter(self):
  p=plan();calls={};pixels=torch.ones(1,32,64,3)*.25
  class Adapter:
   @staticmethod
   def execute(*args,**kwargs):calls.update(args=args,kwargs=kwargs);return ('model',[[0,{}]],{},None,{},'report')
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(rt,'registry',return_value=Adapter),patch.object(rt,'preflight',return_value=[]),patch.object(rt,'load_image',return_value=torch.zeros_like(pixels)),patch.object(continuity,'check_dependency'),patch.object(continuity,'source',return_value={'path':'validated'}),patch.object(tail,'load',return_value=pixels):
   rt.Star7DirectorConditioning().prepare(p,'b',None,None,None,None)
  self.assertIs(calls['kwargs']['ref_images']['ref_image_2'],pixels);self.assertNotIn('first_frame',calls['kwargs']);self.assertNotIn('last_frame',calls['kwargs']);self.assertIn('<Picture 3>',calls['args'][4]);self.assertIn('not a locked first frame',calls['args'][4])
if __name__=='__main__':unittest.main()
