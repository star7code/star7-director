import importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('standalone_director_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
desk=importlib.import_module(pkg.__name__+'.desk');runtime=importlib.import_module(pkg.__name__+'.runtime')
saver=importlib.import_module(pkg.__name__+'.save_video')

class Tests(unittest.TestCase):
 def test_retired_pixel_option_migrates_without_changing_quality_settings(self):
  plan={'schema_version':'1.0','id':'retired_pixel','assets':[],'shots':[],'generation':{'376':{'upscale_model':'像素插值（Lanczos）','upscale_method':'像素插值（Lanczos）','refine_steps':3,'refine_strength':.2,'enable_tiling':True}}}
  result=desk.merge_library(plan,None);cfg=result['generation']['376'];self.assertEqual(cfg['upscale_model'],'minimax_h3_latent_upscaler_3d_fp16.safetensors');self.assertNotIn('upscale_method',cfg);self.assertEqual((cfg['refine_steps'],cfg['refine_strength'],cfg['enable_tiling']),(3,.2,True));self.assertEqual(plan['generation']['376']['upscale_model'],'像素插值（Lanczos）')
  from unittest.mock import patch
  hd=importlib.import_module(pkg.__name__+'.vendor.h3.h3_latent_upscale_star7')
  with patch.object(hd,'_model_directory'),patch.object(hd.folder_paths,'get_filename_list',return_value=['local.safetensors']):
   self.assertNotIn('像素插值（Lanczos）',hd._model_choices());self.assertNotIn('upscale_method',hd.MiniMaxH3OneClickHDStar7.INPUT_TYPES()['required'])
 def test_segment_and_merged_export_folders_preserve_sources(self):
  import folder_paths,numpy as np,av
  exporter=importlib.import_module(pkg.__name__+'.export_node');movie=importlib.import_module(pkg.__name__+'.combine')
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);output=root/'output';output.mkdir();data=root/'data';plan={'schema_version':'1.0','id':'export_test','title':'演示/项目','assets':[],'shots':[{'id':'s1','duration':1,'prompt':'garden'},{'id':'s2','duration':1,'prompt':'garden'},{'id':'s3','duration':1,'prompt':'garden'}]}
   sources=[]
   with patch.object(runtime,'data_root',return_value=data),patch.object(exporter,'data_root',return_value=data),patch.object(movie,'data_root',return_value=data),patch.object(folder_paths,'get_output_directory',return_value=str(output)),patch.dict(sys.modules,{'server':types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(asset_manager=None)))}):
    store=runtime.Storage(data)
    for shot in plan['shots'][:2]:
     path=output/(shot['id']+'.mp4');saver.encode_mp4(path,np.zeros((4,32,32,3),dtype=np.float32),None,24,19);sources.append(path)
     store.record_output(plan['id'],shot['id'],runtime.run_fingerprint(plan,shot['id']),str(path),4)
    before=[p.read_bytes() for p in sources]
    result=exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':'segments'}));info=result['ui']['star7_export'][0];folder=Path(result['result'][0]);entries=result['ui']['gifs']
    self.assertRegex(folder.name,r'^演示_项目-分段导出-\d{8}-\d{6}-\d{6}(?:-\d+)?$');self.assertEqual(len(entries),2);self.assertEqual(info['missing_shots'],['s3']);self.assertEqual(info['included_shots'],['s1','s2'])
    self.assertEqual([p.read_bytes() for p in sorted(folder.glob('*.mp4'))],before)
    for entry in entries:
     target=output/entry['subfolder']/entry['filename'];self.assertTrue(target.is_file());self.assertEqual(store.film_path(plan['id'],entry['filename']),str(target))
    again=exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':'segments'}));self.assertNotEqual(again['result'][0],str(folder))
    merged=exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':'all'}));target=Path(merged['result'][0]);self.assertIn('演示_项目-合并导出-',target.parent.name)
    with av.open(str(target)) as container:self.assertEqual(len(list(container.decode(video=0))),8)
    single=exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':'one','shot_id':'s1'}));self.assertRegex(Path(single['result'][0]).parent.name,r'^\d{4}-\d{2}-\d{2}$')
    self.assertEqual([p.read_bytes() for p in sources],before)
    plan['export_settings']={'format':'vp9-webm','frame_rate':30,'preset':'fast'}
    for scope in ('one','segments','all'):
     encoded=exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':scope,'shot_id':'s1'}))
     for entry in encoded['ui']['gifs']:
      target=output/entry['subfolder']/entry['filename'];self.assertEqual(target.suffix,'.webm');self.assertEqual(entry['format'],'video/webm')
      with av.open(str(target)) as container:self.assertEqual(container.streams.video[0].codec_context.name,'vp9');self.assertEqual(float(container.streams.video[0].average_rate),30)
     self.assertEqual([p.read_bytes() for p in sources],before)
 def test_failed_segment_copy_cleans_only_new_export(self):
  import folder_paths
  exporter=importlib.import_module(pkg.__name__+'.export_node');movie=importlib.import_module(pkg.__name__+'.combine')
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);output=root/'output';output.mkdir();data=root/'data';source=output/'original.mp4';source.write_bytes(b'original');plan={'id':'copy_failure','title':'copy','shots':[{'id':'s1'}]}
   with patch.object(exporter,'data_root',return_value=data),patch.object(movie,'data_root',return_value=data),patch.object(folder_paths,'get_output_directory',return_value=str(output)):
    runtime.Storage(data).record_output(plan['id'],'s1','fingerprint',str(source),1)
    with patch.object(exporter.shutil,'copyfile',side_effect=OSError('copy failed')):
     with self.assertRaisesRegex(OSError,'copy failed'):exporter.Star7DirectorVideoExport().save(json.dumps({'plan':plan,'scope':'segments'}))
    self.assertEqual(source.read_bytes(),b'original');self.assertFalse(list(output.glob('Star7-Director/*/*')))
 def test_exactly_two_public_nodes(self):
  node_module=importlib.import_module(pkg.__name__+'.nodes')
  self.assertEqual(set(node_module.NODE_CLASS_MAPPINGS),{'Star7DirectorDesk','Star7DirectorLibrary'})
  schema=desk.Star7DirectorDesk.INPUT_TYPES()
  self.assertNotIn('rawLink',schema['optional']['model'][1] if len(schema['optional']['model'])>1 else {})
 def test_h3_classes_resolve_privately_without_external_plugin(self):
  import nodes as comfy_nodes
  external={k:v for k,v in comfy_nodes.NODE_CLASS_MAPPINGS.items() if not k.startswith(('MiniMaxH3','Star7Director','VHS_'))}
  with patch.object(comfy_nodes,'NODE_CLASS_MAPPINGS',external):
   for name in ('MiniMaxH3MaterialPromptStar7','MiniMaxH3OneClickHDStar7','MiniMaxH3FaceRefineLatentStar7','MiniMaxH3ChunkedDecodeStar7','MiniMaxH3LivePreviewStar7'):
    cls=runtime.registry(name)
    self.assertIn('.vendor.h3.',cls.__module__);self.assertTrue(cls.INPUT_TYPES())
   self.assertTrue(saver.Star7DirectorSaveVideo.INPUT_TYPES())
 def test_native_encoder_keeps_video_and_audio(self):
  import av,numpy as np
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   target=Path(tmp)/'native.mp4';frames=np.zeros((12,64,96,3),dtype=np.float32);frames[:,:,:,0]=1
   wave=np.zeros((1,2,24000),dtype=np.float32);wave[:,0]=.1
   saver.encode_mp4(target,frames,{'waveform':wave,'sample_rate':48000},24,19)
   with av.open(str(target)) as container:
    self.assertEqual(len(container.streams.video),1);self.assertEqual(len(container.streams.audio),1)
    stream=container.streams.video[0];self.assertEqual((stream.width,stream.height),(96,64))
    decoded=list(container.decode(video=0));self.assertEqual(len(decoded),12)
    self.assertGreater(decoded[0].to_ndarray(format='rgb24')[32,32,0],240)
   with av.open(str(target)) as container:self.assertGreater(sum(f.samples for f in container.decode(audio=0)),23000)
 def test_save_video_uses_no_foreign_encoder_and_removes_temporary_files(self):
  import folder_paths,numpy as np
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);temp=root/'temp';output=root/'output';temp.mkdir();output.mkdir()
   with patch.object(folder_paths,'get_temp_directory',return_value=str(temp)),patch.object(folder_paths,'get_output_directory',return_value=str(output)),patch.object(saver,'data_root',return_value=root/'data'):
    result=saver.Star7DirectorSaveVideo().save({'id':'standalone'},'s1',images=np.zeros((2,32,32,3),dtype=np.float32))
    self.assertTrue(Path(result['result'][0][1][0]).is_file());self.assertFalse(list(temp.rglob('clip.mp4')))
 def test_export_runs_on_workstation_without_model_inputs(self):
  exporter=importlib.import_module(pkg.__name__+'.export_node');expected={'result':('saved',),'ui':{}}
  with patch.object(exporter.Star7DirectorVideoExport,'save',return_value=expected) as save:
   result=desk.Star7DirectorDesk().generate(json.dumps({'star7_action':'export','export_json':'payload'}))
  self.assertEqual(result,expected);save.assert_called_once_with('payload')
 def test_private_executor_keeps_lazy_cache_and_reports_step_errors(self):
  class Cache:
   FUNCTION='save_or_restore'
   @classmethod
   def INPUT_TYPES(cls):return {'hidden':{'prompt':'PROMPT'}}
   def check_lazy_status(self,*args,**kwargs):return []
   def save_or_restore(self,**kwargs):return ('cached','v1')
  class Bad:
   FUNCTION='run'
   @classmethod
   def INPUT_TYPES(cls):return {}
   def run(self):raise AssertionError('sampler must not run')
  graph={'cache':{'class_type':'Star7DirectorBaseCache','inputs':{'latent':['sampler',0]}},'sampler':{'class_type':'Bad','inputs':{}}}
  with patch.object(runtime,'registry',side_effect=lambda name:Cache if name=='Star7DirectorBaseCache' else Bad):
   result=desk.execute_internal(graph,['cache',0],{'id':'p'},'s')
  self.assertEqual(result['result'],('cached',));self.assertNotIn('expand',result)
 def test_workstation_executes_all_stages_privately(self):
  calls=[];specs=desk.template()
  class Preview:
   @classmethod
   def INPUT_TYPES(cls):return {'required':{'model':('MODEL',)},'optional':{'preview_enabled':('BOOLEAN',{'default':False})}}
  def fake(name):
   if name=='Star7DirectorPlan':return desk.Star7DirectorPlan
   if name=='MiniMaxH3LivePreviewStar7':return Preview
   keys={k for spec in specs.values() if spec['class_type']==name for k in spec['inputs']}
   if name=='Star7DirectorStage':keys={'latent','director_plan','shot_id','phase'}
   def run(self,**inputs):
    calls.append((name,inputs))
    if name=='Star7DirectorConditioning':return (inputs['model'],'positive','latent',{},666,True,True,'unused','s1')
    if name=='Star7DirectorStage':return (inputs['latent'],)
    if name=='Star7DirectorSaveVideo':return {'result':((True,['movie.mp4']),),'ui':{'gifs':[{'filename':'movie.mp4'}]}}
    if name=='Star7DirectorComplete':return ('completed',)
    if name=='Star7DirectorTrim':return ('images','audio',24)
    if name=='MiniMaxH3ChunkedDecodeStar7':return ('images','audio')
    if name=='Star7DirectorBaseCache':return (inputs['latent'],'version')
    return ('value',)
   return type(name,(),{'FUNCTION':'run','INPUT_TYPES':classmethod(lambda cls:{'required':{k:('ANY',{}) for k in keys}}),
                       'check_lazy_status':lambda *args,**kwargs:['latent'],'run':run})
  plan={'schema_version':'1.0','id':'private_execution','assets':[],'shots':[{'id':'s1','duration':1,'seed':666,'prompt':'garden','post':{'hd':True,'face':True}}]}
  with patch.object(runtime,'registry',side_effect=fake):
   result=desk.Star7DirectorDesk().generate(json.dumps(plan),model=object(),clip=object(),video_vae=object(),audio_vae=object())
  self.assertEqual(result['result'],('completed',));self.assertNotIn('expand',result)
  names=[name for name,_ in calls]
  self.assertLess(names.index('SamplerCustomAdvanced'),names.index('MiniMaxH3OneClickHDStar7'))
  self.assertLess(names.index('MiniMaxH3OneClickHDStar7'),names.index('MiniMaxH3FaceRefineLatentStar7'))
  self.assertEqual(result['ui']['gifs'][0]['filename'],'movie.mp4')
if __name__=='__main__':unittest.main()
