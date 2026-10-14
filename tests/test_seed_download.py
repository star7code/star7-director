import ast, asyncio, tempfile, types, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from core import identifier,compile_shot
from test_core import project

class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_downloads(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
   root=Path(td).resolve();out=root/'output';out.mkdir();clip=out/'clip.mp4';clip.write_bytes(b'test video');outside=root/'private.mp4';outside.write_bytes(b'private')
   film=out/'Star7-Director'/'test'/'film_123456abcdef.mp4';film.parent.mkdir(parents=True);film.write_bytes(b'film')
   daily=out/'Star7-Director'/'2026-10-10'/'Star7-Director-20261010-180001-film.mp4';daily.parent.mkdir();daily.write_bytes(b'daily film')
   records={'s':{'path':str(clip)},'bad':{'path':str(outside)}}
   tree=ast.parse(Path('routes.py').read_text(encoding='utf-8'));keep=[]
   for n in tree.body:
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('video_download','download_shot','download_film'):
     n.decorator_list=[];n.body=[b for b in n.body if not isinstance(b,ast.ImportFrom)];keep.append(n)
   env={'web':web,'identifier':identifier,'DATA':root,'Storage':lambda _:types.SimpleNamespace(latest_output=lambda p,s:records.get(s),film_path=lambda p,n:str(daily) if p=='test' and n==daily.name else None),'folder_paths':types.SimpleNamespace(get_output_directory=lambda:str(out))}
   exec(compile(ast.Module(body=keep,type_ignores=[]),'routes.py','exec'),env)
   app=web.Application();app.router.add_get('/shot/{pid}/{sid}',env['download_shot']);app.router.add_get('/film/{pid}/{filename}',env['download_film'])
   async with TestClient(TestServer(app)) as client:
    r=await client.get('/shot/test/s?name=角色.mp4');self.assertEqual(r.status,200);self.assertEqual(await r.read(),b'test video');self.assertIn('attachment;',r.headers['Content-Disposition'])
    for url in ('/shot/test/missing','/shot/test/bad','/film/test/clip.mp4'):
     r=await client.get(url);self.assertEqual(r.status,400)
    r=await client.get('/film/test/film_123456abcdef.mp4');self.assertEqual(r.status,200);self.assertEqual(await r.read(),b'film')
    r=await client.get('/film/test/'+daily.name);self.assertEqual(r.status,200);self.assertEqual(await r.read(),b'daily film');self.assertIn(daily.name,r.headers['Content-Disposition'])
    r=await client.get('/film/other/'+daily.name);self.assertEqual(r.status,400)
 def test_seed_metadata(self):
  p=project();before=compile_shot(p,'s1')['fingerprint'];p['shots'][0].update(seed_control='increment',next_seed=8);self.assertEqual(compile_shot(p,'s1')['fingerprint'],before)
  p['shots'][0]['seed']=8;self.assertNotEqual(compile_shot(p,'s1')['fingerprint'],before)
  for value in ('invalid',None):
   p['shots'][0]['seed_control']=value
   with self.assertRaises(ValueError):compile_shot(p,'s1')
if __name__=='__main__':unittest.main()
