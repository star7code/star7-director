import ast,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT.parent/'minimax-h3-chunk-star7/h3_live_preview.py').read_text(encoding='utf-8'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_remember_preview_payload')
class Tests(unittest.TestCase):
 def test_frame_survives_status_updates_but_not_a_new_sampling_run(self):
  env={'_LATEST_PREVIEW_LOCK':threading.Lock(),'_LATEST_PREVIEW_PAYLOADS':{}}
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'preview_recovery','exec'),env)
  remember=env['_remember_preview_payload'];cache=env['_LATEST_PREVIEW_PAYLOADS']
  remember({'node_id':'n','run_id':'first','image':'frame','step':2})
  remember({'node_id':'n','run_id':'first','status':'done'})
  self.assertEqual(cache['n']['image'],'frame');self.assertEqual(cache['n']['step'],2)
  remember({'node_id':'n','run_id':'second','status':'start'})
  self.assertNotIn('image',cache['n'])
  remember({'node_id':'n','run_id':'second','image':'new-frame'})
  self.assertEqual(cache['n']['image'],'new-frame')
if __name__=='__main__':unittest.main()
