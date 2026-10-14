import unittest,tempfile,sqlite3,json,importlib,types,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];pkg=types.ModuleType('storage_migration_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
mod=importlib.import_module(pkg.__name__+'.storage')
class Tests(unittest.TestCase):
 def test_read_only_unknown_project_does_not_create_phantom_folder(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);store=mod.Storage(root);self.assertIsNone(store.latest_output('default_unsaved','s'));self.assertEqual(store.stages('default_unsaved'),[]);self.assertFalse((root/'projects/default_unsaved').exists())
 def test_legacy_migration_and_separate_projects(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);db=sqlite3.connect(root/'index.sqlite3');mod.Storage.schema(db)
   with db:
    for pid in ('first','second'):db.execute('INSERT INTO outputs(project,shot,fingerprint,path,frame_count) VALUES (?,?,?,?,?)',(pid,'shot','fp',pid+'.mp4',24))
   db.close();plan={'schema_version':'1.0','id':'first','assets':[],'shots':[]};(root/'first.json').write_text(json.dumps(plan));(root/'batches').mkdir();(root/'batches/run.json').write_text(json.dumps({'project_id':'first'}))
   store=mod.Storage(root);self.assertFalse((root/'index.sqlite3').exists());self.assertFalse((root/'first.json').exists());self.assertTrue((root/'projects/first/state.json').exists());self.assertTrue((root/'projects/first/batches/run.json').exists());self.assertFalse((root/'batches').exists())
   self.assertEqual(store.latest_output('first','shot')['path'],'first.mp4');self.assertEqual(store.latest_output('second','shot')['path'],'second.mp4')
   with store.db('first') as db:self.assertEqual(db.execute('SELECT DISTINCT project FROM outputs').fetchall(),[('first',)])
   with store.db('second') as db:self.assertEqual(db.execute('SELECT DISTINCT project FROM outputs').fetchall(),[('second',)])
   again=mod.Storage(root);self.assertEqual(again.latest_output('first','shot')['frame_count'],24);self.assertFalse((root/'index.sqlite3').exists())
if __name__=='__main__':unittest.main()
