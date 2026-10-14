import importlib,sys,types,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));pkg=types.ModuleType('daily_output_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
paths=importlib.import_module(pkg.__name__+'.output_paths');Storage=importlib.import_module(pkg.__name__+'.storage').Storage
class Tests(unittest.TestCase):
 def test_shanghai_date_timestamp_and_safe_title(self):
  self.assertEqual(paths.output_prefix('shot001',datetime(2026,10,9,23,5,6,tzinfo=timezone.utc)),'Star7-Director/2026-10-10/S7D-20261010-070506-shot001')
  self.assertNotIn('../',paths.output_prefix('../test\\name:?',datetime(2026,10,10,tzinfo=timezone.utc)))
 def test_same_second_collision_and_project_film_isolation(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(paths,'output_prefix',return_value='Star7-Director/2026-10-10/S7D-20261010-180001-final-film'):
   a=paths.reserve_film(tmp);b=paths.reserve_film(tmp);self.assertNotEqual(a,b);self.assertEqual(b.name,'S7D-20261010-180001-final-film-2.mp4')
   store=Storage(Path(tmp)/'data');store.record_film('one',a);store.record_film('two',b);self.assertEqual(store.film_path('one',a.name),str(a));self.assertIsNone(store.film_path('two',a.name))
 def test_generated_versions_persist_across_timestamps(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   files=[paths.reserve_generated(Path(tmp)/'out',Path(tmp)/'data','project','shot_012') for _ in range(3)]
   self.assertTrue(files[0].name.endswith('-shot012.mp4'));self.assertTrue(files[1].name.endswith('-shot012-2.mp4'));self.assertTrue(files[2].name.endswith('-shot012-3.mp4'));self.assertTrue(all(p.is_file() for p in files))
 def test_two_projects_with_shot001_never_overwrite_each_other(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp,patch.object(paths,'output_prefix',side_effect=lambda title:'Star7-Director/fixed/S7D-same-'+title):
   root=Path(tmp);a=paths.reserve_generated(root/'out',root/'data','one','shot_001');b=paths.reserve_generated(root/'out',root/'data','two','shot_001')
   self.assertNotEqual(a,b);a.write_bytes(b'one');b.write_bytes(b'two');store=Storage(root/'data')
   store.record_output('one','shot_001','same-fingerprint',str(a),24);store.record_output('two','shot_001','same-fingerprint',str(b),24)
   self.assertEqual(store.latest_output('one','shot_001')['path'],str(a));self.assertEqual(store.latest_output('two','shot_001')['path'],str(b));self.assertEqual(a.read_bytes(),b'one')
