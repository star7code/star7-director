import importlib,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('export_settings_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
codec=importlib.import_module(pkg.__name__+'.export_settings');saver=importlib.import_module(pkg.__name__+'.save_video')
class Tests(unittest.TestCase):
 def test_defaults_validation_and_export_changes_do_not_dirty_shots(self):
  self.assertFalse(codec.needs_encoding({'id':'p'}))
  for value in ({'frame_rate':float('nan')},{'frame_rate':-1},{'format':'../mp4'},{'include_audio':1},{'crf':19.5},{'bitrate_mbps':0}):
   with self.assertRaises(ValueError):codec.settings({'export_settings':value})
  parameter=importlib.import_module(pkg.__name__+'.parameter_state');plan={'id':'p','assets':[],'shots':[{'id':'s','duration':1,'seed':666,'prompt':'garden'}]}
  before=parameter.snapshot(plan,'s');plan['export_settings']={'frame_rate':30};self.assertEqual(parameter.visible_changes(before,parameter.snapshot(plan,'s')),[])
 def test_real_export_formats_fps_audio_and_original_bytes(self):
  import av,numpy as np
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);source=root/'source.mp4';saver.encode_mp4(source,np.zeros((24,32,48,3),dtype=np.float32),{'waveform':np.zeros((1,2,48000),dtype=np.float32),'sample_rate':48000},24,19);original=source.read_bytes()
   copied=root/'copied.mp4';codec.export_clip(source,copied,{'id':'p'});self.assertEqual(copied.read_bytes(),original)
   for fmt,expected in (('h264-mp4','h264'),('h265-mp4','hevc'),('vp9-webm','vp9')):
    plan={'id':'p','shots':[],'export_settings':{'format':fmt,'frame_rate':30,'preset':'fast','quality_mode':'bitrate','bitrate_mbps':1,'save_metadata':True}}
    target=root/(fmt+'.'+codec.extension(plan));codec.export_clip(source,target,plan)
    with av.open(str(target)) as container:
     self.assertEqual(container.streams.video[0].codec_context.name,expected);self.assertEqual(len(container.streams.audio),1)
     frames=list(container.decode(video=0));self.assertEqual(len(frames),30);self.assertAlmostEqual(float(frames[-1].time),29/30,places=2)
    self.assertEqual(source.read_bytes(),original)
   silent=root/'silent.mp4';codec.export_clip(source,silent,{'id':'p','export_settings':{'include_audio':False,'frame_rate':30}})
   with av.open(str(silent)) as container:self.assertEqual(len(container.streams.audio),0)
   self.assertFalse(list(root.glob('*.encode.log')));self.assertFalse(list(root.glob('*.tmp.*')))
if __name__=='__main__':unittest.main()
