import importlib,sys,tempfile,types,unittest,subprocess,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('merge_audio_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
movie=importlib.import_module(pkg.__name__+'.combine');runtime=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def test_new_encoder_preserves_model_audio_rate(self):
  import av,numpy as np
  saver=importlib.import_module(pkg.__name__+'.save_video')
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   for rate in (32000,48000):
    target=Path(tmp)/(str(rate)+'.mp4');saver.encode_mp4(target,np.zeros((24,32,64,3),dtype=np.float32),{'waveform':np.zeros((1,2,rate),dtype=np.float32),'sample_rate':rate},24,19)
    with av.open(str(target)) as container:self.assertEqual(container.streams.audio[0].codec_context.sample_rate,rate)
 def test_mixed_audio_rates_channels_and_missing_audio_preserve_video(self):
  import av,imageio_ffmpeg,numpy as np
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);output=root/'output';output.mkdir();plan={'id':'audio_merge','assets':[],'shots':[]};original=[];decoded=[]
   with patch.object(movie,'data_root',return_value=root/'data'):
    store=runtime.Storage(root/'data')
    for i,(color,rate,channels) in enumerate((('red',32000,1),('blue',48000,2),('green',None,None))):
     path=output/(str(i)+'.mp4');args=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c='+color+':s=64x32:r=24:d=1']
     if rate:args+=['-f','lavfi','-i','sine=frequency=440:sample_rate='+str(rate)+':duration=1','-c:a','aac','-ar',str(rate),'-ac',str(channels)]
     args+=['-c:v','libx264','-pix_fmt','yuv420p',str(path)];subprocess.run(args,check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
     plan['shots'].append({'id':'s'+str(i),'duration':1,'prompt':'garden'});store.record_output(plan['id'],'s'+str(i),'fp',str(path),24);original.append((path,hashlib.sha256(path.read_bytes()).hexdigest()))
     with av.open(str(path)) as container:decoded.extend(f.to_ndarray(format='rgb24') for f in container.decode(video=0))
    selection=movie.select_clips(plan,output);merged=movie.combine(plan,{},output,selection)
    with av.open(str(merged)) as container:
     actual=[f.to_ndarray(format='rgb24') for f in container.decode(video=0)];self.assertEqual(len(actual),72)
     for a,b in zip(actual,decoded):self.assertTrue(np.array_equal(a,b))
    with av.open(str(merged)) as container:
     sound=container.streams.audio[0];self.assertEqual(sound.codec_context.sample_rate,48000);self.assertEqual(len(sound.codec_context.layout.channels),2)
     frames=list(container.decode(audio=0));self.assertAlmostEqual(sum(f.samples for f in frames)/48000,3,delta=.06)
     # The segment without audio must be silence, not repeated prior dialogue.
     tail=[f.to_ndarray() for f in frames if float(f.time or 0)>2.1];self.assertTrue(tail);self.assertLess(max(float(np.abs(a).max()) for a in tail),.0001)
    for path,digest in original:self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
    self.assertTrue(selection['audio_normalized']);self.assertIn('48 kHz',movie.assembly_message(selection));self.assertFalse(list(merged.parent.glob('.audio-normalization')))
 def test_normalization_failure_keeps_sources_and_removes_owned_temporary_files(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);output=root/'output';output.mkdir();source=output/'source.mp4';source.write_bytes(b'original');plan={'id':'failed_audio'};selection={'clips':[{'path':source},{'path':source}], 'total':2}
   with patch.object(movie,'data_root',return_value=root/'data'),patch.object(movie,'profile',side_effect=[('h264',64,32,'24','yuv420p','aac',32000,2),('h264',64,32,'24','yuv420p','aac',48000,2)]),patch.object(movie,'video_duration',return_value=1),patch.object(movie,'normalize_audio',side_effect=ValueError('encoding failed')):
    with self.assertRaisesRegex(ValueError,'encoding failed'):movie.combine(plan,{},output,selection)
   self.assertEqual(source.read_bytes(),b'original');self.assertFalse(list(output.glob('Star7-Director/*/*')))
if __name__=='__main__':unittest.main()
