import importlib,sys,types,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('encoding_backend_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
backend=importlib.import_module(pkg.__name__+'.encoding_backend')
export=importlib.import_module(pkg.__name__+'.export_settings')
saver=importlib.import_module(pkg.__name__+'.save_video')

class Tests(unittest.TestCase):
 def test_selection_and_unsupported_settings(self):
  with patch.object(backend,'hardware_available',return_value=True) as probe:
   self.assertEqual(backend.choose_encoder('h264-mp4'),'h264_nvenc')
   self.assertEqual(backend.choose_encoder('h265-mp4'),'hevc_nvenc')
   probe.reset_mock()
   for fmt,options,expected in [('h264-mp4',{'mode':'cpu'},'libx264'),('h264-mp4',{'quality':0},'libx264'),('vp9-webm',{},'libvpx-vp9'),('h264-mp4',{'width':48,'height':32},'libx264')]:
    self.assertEqual(backend.choose_encoder(fmt,**options),expected)
   probe.assert_not_called()
   with self.assertRaises(ValueError):backend.choose_encoder('vp9-webm','gpu')
  with patch.object(backend,'hardware_available',return_value=False):
   self.assertEqual(backend.choose_encoder('h264-mp4'),'libx264')
   with self.assertRaises(ValueError):backend.choose_encoder('h264-mp4','gpu')

 def test_nvenc_quality_bitrate_and_cpu_arguments(self):
  plan={'id':'p','export_settings':{'encoder':'auto','frame_rate':30,'save_metadata':True}}
  with patch.object(backend,'hardware_available',return_value=True):
   args=export.arguments(plan)
   self.assertIn('h264_nvenc',args);self.assertNotIn('-crf',args)
   self.assertEqual(args[args.index('-cq')+1],'19')
   self.assertIn('fps=30',args);self.assertIn('aac',args);self.assertIn('-metadata',args)
   cpu=export.arguments(plan,force_cpu=True)
   self.assertIn('libx264',cpu);self.assertIn('-crf',cpu);self.assertNotIn('-cq',cpu)
   plan['export_settings'].update(quality_mode='bitrate',bitrate_mbps=12)
   args=export.arguments(plan)
   self.assertNotIn('-cq',args);self.assertEqual(args[args.index('-b:v')+1],'12000000')

 def test_only_automatic_initialization_failure_retries(self):
  images=types.SimpleNamespace(shape=(24,256,256,3))
  with patch.object(backend,'choose_encoder',return_value='h264_nvenc'),patch.object(saver,'_encode_mp4',side_effect=[backend.HardwareEncoderUnavailable('init'),None]) as encode:
   saver.encode_mp4(ROOT/'tests/nonexistent-retry.mp4',images,encoder='auto')
   self.assertEqual(encode.call_count,2);self.assertEqual(encode.call_args.args[-2],'libx264')
  for mode,error in [('gpu',backend.HardwareEncoderUnavailable('init')),('auto',ValueError('invalid pixels'))]:
   with patch.object(backend,'choose_encoder',return_value='h264_nvenc'),patch.object(saver,'_encode_mp4',side_effect=error) as encode:
    with self.assertRaises(type(error)):saver.encode_mp4('unused.mp4',images,encoder=mode)
    self.assertEqual(encode.call_count,1)

 def test_old_projects_default_auto_without_forced_transcode(self):
  self.assertEqual(export.settings({'id':'p'})['encoder'],'auto')
  self.assertFalse(export.needs_encoding({'id':'p'}))
  with self.assertRaises(ValueError):export.settings({'export_settings':{'encoder':'bad'}})

 def test_export_retry_keeps_merge_options_and_does_not_mask_other_errors(self):
  import comfy.model_management,imageio_ffmpeg
  plan={'id':'p'};commands=[]
  class Process:
   def __init__(self,command,stderr,**kwargs):
    commands.append(command)
    self.code=1 if len(commands)==1 else 0
    if self.code:stderr.write(b'[h264_nvenc] Cannot load NVENC encoder')
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def wait(self,timeout=None):return self.code
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(backend,'hardware_available',return_value=True),patch.object(export.subprocess,'Popen',Process),patch.object(imageio_ffmpeg,'get_ffmpeg_exe',return_value='ffmpeg'),patch.object(comfy.model_management,'throw_exception_if_processing_interrupted'):
   extra=['-af','apad','-t','2.5'];target=Path(tmp)/'merged.mp4'
   export.run(['-i','unused.mp4'],target,plan,codec_args=export.arguments(plan)+extra)
   self.assertEqual(len(commands),2);self.assertIn('libx264',commands[1]);self.assertEqual(commands[1][-5:-1],extra)
   self.assertFalse(list(Path(tmp).glob('*.encode.log')))

 def test_export_output_errors_are_not_retried(self):
  import comfy.model_management,imageio_ffmpeg
  commands=[]
  class Process:
   def __init__(self,command,stderr,**kwargs):commands.append(command);stderr.write(b'No space left on device')
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def wait(self,timeout=None):return 1
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(backend,'hardware_available',return_value=True),patch.object(export.subprocess,'Popen',Process),patch.object(imageio_ffmpeg,'get_ffmpeg_exe',return_value='ffmpeg'),patch.object(comfy.model_management,'throw_exception_if_processing_interrupted'):
   with self.assertRaisesRegex(ValueError,'No space'):export.run(['-i','unused.mp4'],Path(tmp)/'out.mp4',{'id':'p'})
   self.assertEqual(len(commands),1)

if __name__=='__main__':unittest.main()
