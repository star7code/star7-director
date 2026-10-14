import copy,importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('selected_source_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
rt=importlib.import_module(pkg.__name__+'.runtime');b=importlib.import_module(pkg.__name__+'.batch_runner');c=importlib.import_module(pkg.__name__+'.continuity')
class Tests(unittest.TestCase):
 def test_independent_shot_needs_no_predecessor_video(self):
  p={'schema_version':'1.0','id':'independent','assets':[],'shots':[{'id':'a','duration':1,'prompt':'not generated'},{'id':'b','duration':1,'prompt':'different scene','continuity':{'mode':'independent'}}]}
  with patch.object(rt.Storage,'latest_output',side_effect=AssertionError('Must not read predecessor')):
   c.check_dependency(p,'b',{})
   self.assertIsNone(c.source(p,'b',{}))
 def test_single_shot_uses_selected_video_without_claiming_it_matches(self):
  import folder_paths
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(rt,'data_root',return_value=Path(tmp)),patch.object(b,'data_root',return_value=Path(tmp)),patch.object(folder_paths,'get_output_directory',return_value=tmp):
   p={'schema_version':'1.0','id':'test_selected','assets':[],'shots':[{'id':'a','duration':2,'prompt':'changed after generation','post':{'hd':False}},{'id':'c','duration':2,'prompt':'new angle','continuity':{'mode':'tail_reference','source_shot':'a'}}]}
   video=Path(tmp)/'a.mp4';video.write_bytes(b'finished');store=rt.Storage(tmp);store.record_output(p['id'],'a','old_settings',str(video),48,post={'hd':True});old=store.latest_output(p['id'],'a')
   run={'id':'selected','status':'running','scope':'one','project_id':p['id'],'plan':p,'prepared':{'output':{'10':{'class_type':'Star7DirectorDesk','inputs':{}}}},'owner_id':'10','client_id':'test','active_shot_id':'c','nonce':None}
   b.RUNS[run['id']]=run
   try:
    prompt,nonce=b.prompt_for(run,'c','one');run['nonce']=nonce;submitted=json.loads(prompt['10']['inputs']['project_json'])
    self.assertFalse(rt.output_matches(submitted,'a',prompt,old))
    self.assertTrue(run['warnings']);self.assertEqual(c.source(submitted,'c',prompt)['path'],video);c.check_dependency(submitted,'c',prompt)
    # A later result cannot silently change the artifact selected for this job.
    newer=Path(tmp)/'a-new.mp4';newer.write_bytes(b'newer');store.record_output(p['id'],'a','new_settings',str(newer),48)
    self.assertEqual(c.source(submitted,'c',prompt)['path'],video)
    wrong=copy.deepcopy(submitted);wrong['runtime']['request_nonce']='other'
    with self.assertRaisesRegex(ValueError,'不匹配'):c.source(wrong,'c',prompt)
    run['scope']='all'
    self.assertEqual(c.source(submitted,'c',prompt)['path'],video)
    run['scope']='one';video.unlink()
    with self.assertRaisesRegex(ValueError,'文件不可用'):c.source(submitted,'c',prompt)
   finally:b.RUNS.pop(run['id'],None)
if __name__=='__main__':unittest.main()
