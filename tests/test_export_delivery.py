import importlib,sys,types,tempfile,unittest,zipfile,ast,json
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('delivery_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
delivery=importlib.import_module(pkg.__name__+'.export_delivery')
class Tests(unittest.TestCase):
 def test_native_save_cancel_group_zip_and_single(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);out=root/'output';group=out/'项目-分段导出-now';group.mkdir(parents=True);data=root/'data';store=delivery.Storage(data);chosen=root/'chosen';chosen.mkdir()
   for name in ('01.mp4','02.mp4'):
    p=group/name;p.write_bytes(name.encode());store.record_film('p',p)
   store.record_output('p','s','fp',str(group/'01.mp4'),24)
   body={'project_id':'p','filename':'01.mp4'}
   with patch.object(delivery,'choose_native_directory',return_value=None):
    self.assertTrue(delivery.save_native(data,out,body)['cancelled']);self.assertEqual(list(chosen.iterdir()),[])
   with patch.object(delivery,'choose_native_directory',return_value=chosen):
    delivery.save_native(data,out,body);self.assertEqual(len(list((chosen/group.name).iterdir())),2)
    delivery.save_native(data,out,{**body,'zip':True})
    with zipfile.ZipFile(chosen/(group.name+'.zip')) as z:self.assertEqual(len(z.namelist()),2)
    delivery.save_native(data,out,{'scope':'one','project_id':'p','shot_id':'s'})
    delivery.save_native(data,out,{'scope':'one','project_id':'p','shot_id':'s'})
    self.assertEqual((chosen/'01.mp4').read_bytes(),b'01.mp4');self.assertEqual((chosen/'01-2.mp4').read_bytes(),b'01.mp4')
   self.assertEqual(len(list(group.iterdir())),2)
 def test_group_copy_zip_collision_and_path_boundary(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);output=root/'output';folder=output/'Star7-Director'/'2026-10-15'/'项目-分段导出-20261015';folder.mkdir(parents=True);store=delivery.Storage(root/'data');sources=[]
   for i in range(3):
    p=folder/(str(i)+'.mp4');p.write_bytes(('video'+str(i)).encode());store.record_film('p',p);sources.append(p)
   unrelated=folder/'private.mp4';unrelated.write_bytes(b'do not include')
   anchor,paths,grouped=delivery.export_files(root/'data',output,'p','0.mp4');self.assertEqual(paths,sources);self.assertTrue(grouped)
   downloads=root/'Downloads';target=delivery.copy_to_downloads(anchor,paths,grouped,downloads);self.assertEqual(target.name,folder.name);self.assertEqual(len(list(target.iterdir())),3)
   for p in paths:self.assertEqual((target/p.name).read_bytes(),p.read_bytes())
   second=delivery.copy_to_downloads(anchor,paths,grouped,downloads);self.assertNotEqual(second,target)
   archive=root/'export.zip';delivery.build_archive(archive,anchor,paths)
   with zipfile.ZipFile(archive) as z:self.assertEqual(z.namelist(),[folder.name+'/'+p.name for p in paths]);self.assertEqual(z.read(folder.name+'/1.mp4'),b'video1')
   with self.assertRaises(ValueError):delivery.export_files(root/'data',output,'p','../private.mp4')
   outside=root/'outside.mp4';outside.write_bytes(b'private');store.record_film('p',outside)
   with self.assertRaises(ValueError):delivery.export_files(root/'data',output,'p','outside.mp4')
   sources[-1].unlink()
   with self.assertRaisesRegex(ValueError,'移动或删除'):delivery.export_files(root/'data',output,'p','0.mp4')
 def test_failed_copy_keeps_sources_and_existing_downloads(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);source=root/'project-分段导出-now'/'video.mp4';source.parent.mkdir();source.write_bytes(b'source');downloads=root/'Downloads';downloads.mkdir();existing=downloads/source.parent.name;existing.mkdir();(existing/'keep.txt').write_text('keep')
   with patch.object(delivery.shutil,'copy2',side_effect=OSError('failed')):
    with self.assertRaises(OSError):delivery.copy_to_downloads(source,[source],True,downloads)
   self.assertEqual(source.read_bytes(),b'source');self.assertEqual(list(downloads.iterdir()),[existing]);self.assertTrue((existing/'keep.txt').exists())
class Routes(unittest.IsolatedAsyncioTestCase):
 async def test_native_save_requires_local_origin_and_returns_cancel(self):
  tree=ast.parse((ROOT/'routes.py').read_text(encoding='utf-8'));function=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='save_native_export');function.decorator_list=[]
  env={'__name__':pkg.__name__+'.native_route','__package__':pkg.__name__,'web':web,'DATA':ROOT/'tests','folder_paths':types.SimpleNamespace(get_output_directory=lambda:str(ROOT/'tests'))}
  exec(compile(ast.Module(body=[function],type_ignores=[]),'routes.py','exec'),env)
  app=web.Application();app.router.add_post('/native',env['save_native_export'])
  async with TestClient(TestServer(app)) as client:
   with patch.object(delivery,'save_native',return_value={'cancelled':True}) as save:
    for headers in ({},{'Origin':'https://other.example'}):
     response=await client.post('/native',json={},headers=headers);self.assertEqual(response.status,400)
    save.assert_not_called()
    response=await client.post('/native',json={},headers={'Origin':str(client.make_url('/')).rstrip('/')});self.assertEqual(response.status,200);self.assertTrue((await response.json())['cancelled']);save.assert_called_once()
 async def test_current_download_streams_without_creating_export_copy(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);out=root/'output';out.mkdir();source=out/'original.mp4';source.write_bytes(b'original-video');data=root/'data';store=delivery.Storage(data);store.record_output('p','s','fp',str(source),24)
   tree=ast.parse((ROOT/'routes.py').read_text(encoding='utf-8'));function=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='download_current');function.decorator_list=[]
   env={'__name__':pkg.__name__+'.current_route','__package__':pkg.__name__,'web':web,'DATA':data,'Storage':delivery.Storage,'folder_paths':types.SimpleNamespace(get_output_directory=lambda:str(out))}
   exec(compile(ast.Module(body=[function],type_ignores=[]),'routes.py','exec'),env)
   app=web.Application();app.router.add_post('/current/{pid}/{sid}',env['download_current'])
   async with TestClient(TestServer(app)) as client:
    response=await client.post('/current/p/s',json={'export_settings':{}});self.assertEqual(response.status,200);self.assertEqual(await response.read(),b'original-video');self.assertEqual(list(out.iterdir()),[source])
    import numpy as np,av,io
    saver=importlib.import_module(pkg.__name__+'.save_video');saver.encode_mp4(source,np.zeros((24,32,48,3),dtype=np.float32),None,24,19);before=source.read_bytes()
    response=await client.post('/current/p/s',json={'export_settings':{'format':'vp9-webm','frame_rate':30,'preset':'fast'}});self.assertEqual(response.status,200);raw=await response.read()
    with av.open(io.BytesIO(raw)) as container:self.assertEqual(container.streams.video[0].codec_context.name,'vp9');self.assertEqual(float(container.streams.video[0].average_rate),30)
    # HTTP EOF reaches the client just before the server's finally cleanup.
    import asyncio
    async with asyncio.timeout(2):
     while list((data/'packages').glob('*')):await asyncio.sleep(.01)
    self.assertEqual(source.read_bytes(),before);self.assertEqual(list(out.iterdir()),[source]);self.assertFalse(list((data/'packages').glob('*')))
    with store.db('p',create=False) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM films').fetchone()[0],0)
 async def test_zip_contains_whole_group_and_native_action_checks_origin(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   root=Path(tmp);out=root/'output';folder=out/'项目-分段导出-now';folder.mkdir(parents=True);data=root/'data';store=delivery.Storage(data)
   for name in ('01.mp4','02.mp4'):
    p=folder/name;p.write_bytes(name.encode());store.record_film('p',p)
   tree=ast.parse((ROOT/'routes.py').read_text(encoding='utf-8'));keep=[]
   for n in tree.body:
    if isinstance(n,ast.AsyncFunctionDef) and n.name in ('export_action','download_export_zip'):n.decorator_list=[];keep.append(n)
   env={'__name__':pkg.__name__+'.delivery_routes','__package__':pkg.__name__,'web':web,'DATA':data,'folder_paths':types.SimpleNamespace(get_output_directory=lambda:str(out))}
   exec(compile(ast.Module(body=keep,type_ignores=[]),'routes.py','exec'),env)
   app=web.Application();app.router.add_get('/zip/{pid}/{filename}',env['download_export_zip']);app.router.add_post('/action/{pid}/{filename}',env['export_action'])
   async with TestClient(TestServer(app)) as client:
    response=await client.get('/zip/p/01.mp4');self.assertEqual(response.status,200);raw=await response.read()
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertEqual(len(z.namelist()),2);self.assertIn(folder.name+'/02.mp4',z.namelist())
    self.assertFalse(list((data/'packages').glob('*.zip')))
    response=await client.post('/action/p/01.mp4',json={'action':'downloads'});self.assertEqual(response.status,400)
    with patch.object(delivery,'copy_to_downloads',return_value=root/'Downloads'/folder.name) as copy:
     response=await client.post('/action/p/01.mp4',json={'action':'downloads'},headers={'Origin':str(client.make_url('/')).rstrip('/')});self.assertEqual(response.status,200);result=await response.json();self.assertEqual(result['count'],2);self.assertEqual(len(copy.call_args.args[1]),2)
if __name__=='__main__':unittest.main()
