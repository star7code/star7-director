import importlib,sys,types,unittest,tempfile,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('memory_cleanup_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
b=importlib.import_module(pkg.__name__+'.batch_runner');rt=importlib.import_module(pkg.__name__+'.runtime')
class Tests(unittest.TestCase):
 def test_flags_only_for_owned_batch_between_clips(self):
  import server
  flags=[];instance=types.SimpleNamespace(prompt_queue=types.SimpleNamespace(set_flag=lambda k,v:flags.append((k,v))))
  p={'schema_version':'1.0','id':'memory_test','assets':[],'shots':[{'id':'a','duration':1,'prompt':'garden'},{'id':'c','duration':1,'prompt':'garden'}],'execution_options':{'clear_vram_between_shots':True},'runtime':{'batch_id':'cleanup_test','request_nonce':'n'}}
  run={'status':'running','scope':'all','project_id':p['id'],'active_shot_id':'a','nonce':'n','position':0,'shot_ids':['a','c'],'stop_after':None};b.RUNS['cleanup_test']=run
  try:
   with patch.object(server.PromptServer,'instance',instance,create=True):
    self.assertTrue(b.release_after_clip(p,'a'));self.assertEqual(flags,[('unload_models',True),('free_memory',True)])
    flags.clear();run['position']=1;self.assertFalse(b.release_after_clip(p,'a'))
    run['position']=0;run['stop_after']='a';self.assertFalse(b.release_after_clip(p,'a'));run['stop_after']=None
    run['scope']='one';self.assertFalse(b.release_after_clip(p,'a'));run['scope']='all'
    p['runtime']['request_nonce']='other';self.assertFalse(b.release_after_clip(p,'a'));self.assertEqual(flags,[])
  finally:b.RUNS.pop('cleanup_test',None)
 def test_toggle_does_not_change_generated_video_fingerprint(self):
  p={'schema_version':'1.0','id':'memory_fingerprint','assets':[],'shots':[{'id':'a','duration':1,'prompt':'garden'}]}
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)):
   before=rt.run_fingerprint(p,'a');p['execution_options']={'clear_vram_between_shots':True};self.assertEqual(before,rt.run_fingerprint(p,'a'));p['execution_options']['clear_vram_between_shots']=False;self.assertEqual(before,rt.run_fingerprint(p,'a'))
if __name__=='__main__':unittest.main()
