import ast,asyncio,importlib,io,json,sys,tempfile,types,zipfile
from pathlib import Path
from unittest.mock import patch
from aiohttp import web,FormData
from aiohttp.test_utils import TestClient,TestServer
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT.parents[1]),str(ROOT)]
pkg=types.ModuleType('route_tests');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
lib=importlib.import_module(pkg.__name__+'.library_packages')
async def main():
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  data=Path(tmp);tree=ast.parse((ROOT/'routes.py').read_text(encoding='utf-8'));functions=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name in ('import_material_library','export_material_library','cache_status','clear_cache','upload_media')]
  for f in functions:f.decorator_list=[]
  queue=types.SimpleNamespace(get_current_queue=lambda:([],[]));namespace={'__package__':pkg.__name__,'web':web,'json':json,'DATA':data,'PromptServer':types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=queue))}
  exec(compile(ast.Module(body=functions,type_ignores=[]),'routes.py','exec'),namespace)
  app=web.Application();app.router.add_post('/import',namespace['import_material_library']);app.router.add_post('/export',namespace['export_material_library']);app.router.add_get('/cache/{project}',namespace['cache_status']);app.router.add_post('/cache/{project}/clear',namespace['clear_cache']);app.router.add_post('/upload',namespace['upload_media'])
  assets=importlib.import_module(pkg.__name__+'.assets')
  with patch.object(lib,'MEDIA',data/'media'),patch.object(assets,'MEDIA',data/'media'):
   async with TestClient(TestServer(app)) as client:
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr('光效.txt','淡紫色发光粒子')
    form=FormData();form.add_field('library',json.dumps({'name':'特效库','assets':[]}));form.add_field('file',buf.getvalue(),filename='fx.zip',content_type='application/zip')
    response=await client.post('/import?category=effect',data=form);assert response.status==200,await response.text();result=await response.json();assert len(result['assets'])==1
    response=await client.post('/export',json=result);assert response.status==200,await response.text();blob=await response.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:assert json.loads(z.read('index.json'))['assets'][0]['description']=='淡紫色发光粒子'
    form=FormData();form.add_field('library',json.dumps(result));form.add_field('file',b'broken',filename='bad.zip',content_type='application/zip');response=await client.post('/import?category=effect',data=form);assert response.status==400
    assert not list((data/'packages').glob('*.upload'))
    form=FormData();form.add_field('kind','text');form.add_field('known_media','[]');form.add_field('file','文字参考'.encode(),filename='original.txt',content_type='text/plain');response=await client.post('/upload',data=form);assert response.status==200,await response.text();uploaded=await response.json();assert uploaded['original_name']=='original.txt';assert (data/'media'/uploaded['source'].split('/')[-1]).exists()
    response=await client.get('/cache/test_project');assert response.status==200;assert (await response.json())['material_bytes']>0
    queue.get_current_queue=lambda:([{'running':True}],[]);response=await client.post('/cache/test_project/clear',json={'kind':'checkpoints'});assert response.status==400
    queue.get_current_queue=lambda:([],[]);response=await client.post('/cache/test_project/clear',json={'kind':'temporary'});assert response.status==200
 print('PASS: real multipart import, streaming ZIP export, malformed ZIP rejection and temporary archive cleanup')
asyncio.run(main())
