import json
from aiohttp import web
from server import PromptServer
from .core import compile_plan,preflight,agent_catalog
from .nodes import DATA
from .storage import Storage
import folder_paths

@PromptServer.instance.routes.get('/star7/director/local-projects')
async def list_local_projects(request):
    from .project_store import listing
    return web.json_response({'projects':listing()})

@PromptServer.instance.routes.post('/star7/director/local-projects/{action}')
async def local_project_action(request):
    import asyncio
    from . import project_store as projects
    try:
        body=await request.json();action=request.match_info['action']
        if action=='save':result=await asyncio.to_thread(projects.save,body['plan'],body.get('workflow',{}),body.get('manual',False))
        elif action=='clone':result=await asyncio.to_thread(projects.clone,body['plan'],body.get('workflow',{}),body.get('title'))
        elif action=='new':result=await asyncio.to_thread(projects.create,body['plan'],body.get('workflow',{}))
        elif action=='read':result=await asyncio.to_thread(projects.read,body['id'])
        elif action=='rename':result=await asyncio.to_thread(projects.rename,body['id'],body['title'])
        elif action=='delete':result=await asyncio.to_thread(projects.delete,body['id'])
        else:raise ValueError('未知项目操作')
        return web.json_response(result)
    except (ValueError,KeyError,TypeError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.get('/star7/director/project-media/{pid}/media/{filename}')
async def project_media(request):
    from .core import identifier
    from .project_store import folder
    try:
        pid=identifier(request.match_info['pid']);name=request.match_info['filename']
        if __import__('pathlib').Path(name).name!=name:raise ValueError('无效素材名')
        root=(folder(pid)/'media').resolve();path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():return web.json_response({'error':'素材不存在'},status=404)
        return web.FileResponse(path)
    except ValueError as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.get('/star7/director/projects/{pid}')
async def read_project(request):
    try: return web.json_response(Storage(DATA).load_project(request.match_info['pid']))
    except FileNotFoundError: return web.json_response({'error':'Project not found'},status=404)
    except ValueError as e: return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.put('/star7/director/projects/{pid}')
async def save_project(request):
    try:
        if request.content_length is None or request.content_length>2**20: raise ValueError('Project payload too large')
        plan=await request.json()
        if plan.get('id')!=request.match_info['pid']: raise ValueError('Project ID mismatch')
        compile_plan(plan)
        Storage(DATA).save_project(plan)
        return web.json_response({'saved':True})
    except (ValueError,TypeError,KeyError) as e: return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/preflight')
async def check_project(request):
    try:
        plan=await request.json()
        return web.json_response({'shots':compile_plan(plan),'missing':preflight(plan,folder_paths.get_input_directory()),'agent_catalog':agent_catalog(plan)})
    except (ValueError,TypeError,KeyError) as e: return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/validate-generation')
async def check_generation(request):
    try:
        from .generation_checks import validate_generation
        body=await request.json()
        return web.json_response(await validate_generation(body['plan'],body['prepared']))
    except (ValueError,TypeError,KeyError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/upload')
async def upload_media(request):
    import hashlib
    from .assets import upload_target,finish_upload
    path=None
    try:
        reader=await request.multipart()
        kind_part=await reader.next()
        if kind_part is None or kind_part.name!='kind':raise ValueError('Missing media kind')
        kind=await kind_part.text()
        part=await reader.next();known=[]
        if part is not None and part.name=='known_media':
            import json
            raw=await part.read()
            if len(raw)>512*1024:raise ValueError('素材索引过大')
            known=json.loads(raw)
            if not isinstance(known,list) or len(known)>10000:raise ValueError('无效素材索引')
            part=await reader.next()
        if part is None or part.name!='file' or not part.filename:raise ValueError('Missing upload file')
        path,original=upload_target(part.filename,kind)
        import unicodedata
        for item in known:
            if isinstance(item,dict) and isinstance(item.get('original_name'),str) and unicodedata.normalize('NFC',item['original_name']).casefold()==unicodedata.normalize('NFC',original).casefold():raise ValueError('已有该素材：'+str(item.get('asset_name') or original))
        total=0;digest=hashlib.sha256()
        with path.open('xb') as out:
            while True:
                chunk=await part.read_chunk(65536)
                if not chunk:break
                total+=len(chunk)
                if total>512*2**20:raise ValueError('素材超过 512 MiB 上限')
                digest.update(chunk);out.write(chunk)
        incoming_hash=digest.hexdigest()
        from .assets import MEDIA
        from .packages import digest as file_digest
        for item in known:
            if not isinstance(item,dict) or item.get('content_hash')!=incoming_hash:continue
            source=item.get('source','')
            if not isinstance(source,str) or not source.startswith('star7-director/'):continue
            existing=(MEDIA/source[len('star7-director/'):]).resolve()
            if existing.is_relative_to(MEDIA.resolve()) and existing.is_file() and file_digest(existing)==incoming_hash:raise ValueError('已有该素材：'+str(item.get('asset_name') or item.get('original_name') or existing.name))
        result=finish_upload(path,original,kind,incoming_hash)
        return web.json_response(result)
    except Exception as e:
        if path is not None:path.unlink(missing_ok=True)
        return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/status')
async def project_status(request):
    from .runtime import output_matches,Star7DirectorBaseCache,batch_plan,parameter_matches
    try:
        body=await request.json();plan=body['plan'];pipeline=body.get('prompt',{})
        result={}
        store=Storage(DATA)
        from pathlib import Path
        from .core import identifier
        identifier(plan['id'])
        for shot in plan['shots']:
            identifier(shot['id'])
            record=store.latest_output(plan['id'],shot['id'])
            has_output=bool(record and Path(record['path']).resolve().is_relative_to(Path(folder_paths.get_output_directory()).resolve()) and Path(record['path']).is_file())
            problem='';changes={};valid=has_output;batch_valid=has_output;base=None
            try:
                from .parameter_state import details
                changes=details(plan,shot['id'],record) if has_output else {}
                valid=bool(has_output and parameter_matches(plan,shot['id'],pipeline,record))
                batch_valid=valid or bool(has_output and parameter_matches(batch_plan(plan,shot['id'],record),shot['id'],pipeline,record))
            except (ValueError,TypeError,KeyError,OSError) as error:problem=str(error)
            try:
                base,_=Star7DirectorBaseCache().find(plan,shot['id'],pipeline)
            except (ValueError,TypeError,KeyError,OSError) as error:problem=problem or str(error)
            reason='缓存已清除，请重新生成当前镜头以建立缓存，再执行二采／人脸修复' if not base and store.cache_was_cleared(plan['id'],shot['id']) else '没有与当前参数匹配的基础缓存，请先生成当前镜头'
            result[shot['id']]={'complete':valid,'batch_complete':batch_valid,'stale':has_output and not batch_valid,'parameters_changed':has_output and not valid,'preserves_post':has_output and batch_valid and not valid,'frames':record['frame_count'] if record else None,'has_output':has_output,'base_available':base is not None,'base_reason':problem or ('' if base else reason)}
            result[shot['id']].update(changes)
            if problem:result[shot['id']]['resource_problem']=problem
        return web.json_response(result)
    except (ValueError,TypeError,KeyError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.get('/star7/director/result/{pid}/{sid}')
async def shot_result(request):
    import pathlib,urllib.parse
    from .core import identifier
    try:
        store=Storage(DATA);pid=identifier(request.match_info['pid']);sid=identifier(request.match_info['sid'])
        record=store.latest_output(pid,sid)
        if request.query.get('run_id'):
            from .batch_runner import state
            task=state(identifier(request.query['run_id']))
            if task['project_id']!=pid:raise ValueError('任务与项目不匹配')
            result=task.get('results',{}).get(sid);filename=request.query.get('filename')
            if result and (not filename or pathlib.Path(result['path']).name==filename):
                record={'path':result['path'],'frame_count':result['frames'],'post':result.get('post')}
            else:
                record=next((r for r in store.output_history(pid,sid,128) if pathlib.Path(r['path']).name==filename),None)
            if record is None:raise ValueError('任务成品版本已被较新版本替换')
        if record is None:return web.json_response({'error':'尚未生成'},status=404)
        path=pathlib.Path(record['path']).resolve();base=pathlib.Path(folder_paths.get_output_directory()).resolve()
        if not path.is_relative_to(base) or not path.is_file():raise ValueError('输出文件不可用')
        relative=path.relative_to(base)
        from .video_info import finished_info
        info=finished_info(record,store,pid,sid)
        return web.json_response({'url':'/view?'+urllib.parse.urlencode({'filename':relative.name,'subfolder':str(relative.parent).replace('\\','/'),'type':'output'}),'filename':path.name,'frames':record['frame_count'],**info,'download_url':'/star7/director/download-shot/'+urllib.parse.quote(pid)+'/'+urllib.parse.quote(sid)})
    except (ValueError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/validate-pipeline')
async def validate_pipeline(request):
    import execution,uuid
    try:
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('Invalid pipeline')
        from .desk import internal_graph,merge_library
        import json
        expanded=dict(body)
        for nid,spec in body.items():
            if spec.get('class_type')!='Star7DirectorDesk':continue
            values=spec['inputs'];plan=json.loads(values['project_json'])
            library_link=values.get('asset_library')
            if isinstance(library_link,list):
                lib=body.get(library_link[0],{})
                if lib.get('class_type')=='Star7DirectorLibrary':
                    from .reference_size import AssetLibrary
                    data=json.loads(lib['inputs']['library_json']);plan=merge_library(plan,AssetLibrary(data.get('assets',[]),data.get('reference_size')))
            shot=plan.get('runtime',{}).get('active_shot_id') or (plan['shots'][0]['id'] if plan['shots'] else None)
            from .continuity import check_dependency
            check_dependency(plan,shot,body)
            ports={key:values[key] for key in ('model','clip','video_vae','audio_vae')}
            graph,result=internal_graph(plan,shot,ports,nid+'.director.')
            expanded.pop(nid);expanded.update(graph)
            for target in expanded.values():
                for key,value in target['inputs'].items():
                    if value==[nid,0]:target['inputs'][key]=result
        result=await execution.validate_prompt(str(uuid.uuid4()),expanded,None)
        return web.json_response({'valid':result[0],'errors':result[3]})
    except (ValueError,TypeError,KeyError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/combine')
async def combine_project(request):
    import asyncio,urllib.parse,pathlib
    from .combine import combine,outdated_shots,select_clips,assembly_message
    try:
        body=await request.json()
        plan=body['plan'];pipeline=body.get('prompt',{});selection=select_clips(plan,folder_paths.get_output_directory());included={c['id'] for c in selection['clips']};stale=[s for s in outdated_shots(plan,pipeline) if s in included]
        path=await asyncio.to_thread(combine,plan,pipeline,folder_paths.get_output_directory(),selection)
        relative=path.relative_to(pathlib.Path(folder_paths.get_output_directory()))
        return web.json_response({'url':'/view?'+urllib.parse.urlencode({'filename':relative.name,'subfolder':str(relative.parent).replace('\\','/'),'type':'output'}),'filename':path.name,'outdated_shots':stale,'missing_shots':selection['missing_shots'],'message':assembly_message(selection,stale),'download_url':'/star7/director/download-film/'+urllib.parse.quote(plan['id'])+'/'+urllib.parse.quote(path.name)})
    except (ValueError,OSError,KeyError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/preview-playlist')
async def preview_playlist(request):
    import urllib.parse,pathlib,av,asyncio,re
    from .combine import select_clips,assembly_message
    from .preview_film import build,update,progress
    job=request.query.get('progress','')
    if job and not re.fullmatch('[a-f0-9]{32}',job):return web.json_response({'error':'无效预览请求编号'},status=400)
    update(job,0,'正在检查已生成的视频…')
    try:
        plan=await request.json();root=pathlib.Path(folder_paths.get_output_directory()).resolve();selection=select_clips(plan,root);clips=[]
        if not selection['clips']:raise ValueError('当前没有可预览的已生成视频')
        for clip in selection['clips']:
            relative=clip['path'].relative_to(root)
            with av.open(str(clip['path'])) as f:
                stream=f.streams.video[0];duration=float(stream.duration*stream.time_base) if stream.duration is not None else clip['frames']/float(stream.average_rate or 24)
            clips.append({'id':clip['id'],'name':clip['name'],'duration':duration,'url':'/view?'+urllib.parse.urlencode({'filename':relative.name,'subfolder':relative.parent.as_posix(),'type':'output'})})
        path=await asyncio.to_thread(build,[{**source,'duration':clip['duration']} for source,clip in zip(selection['clips'],clips)],plan['id'],lambda percent,message:update(job,percent,message))
        update(job,100,progress(job)['message'],'complete')
        return web.json_response({'clips':clips,'url':'/star7/director/continuous-preview/'+path.stem,'missing_shots':selection['missing_shots'],'unavailable_shots':selection['unavailable_shots'],'message':assembly_message(selection,preview=True),'total_duration':sum(c['duration'] for c in clips)})
    except (ValueError,OSError,KeyError,IndexError) as e:
        update(job,0,str(e),'failed');return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.get('/star7/director/preview-progress/{job}')
async def preview_progress(request):
    import re
    from .preview_film import progress
    job=request.match_info['job']
    if not re.fullmatch('[a-f0-9]{32}',job):raise web.HTTPNotFound()
    return web.json_response(progress(job))


@PromptServer.instance.routes.get('/star7/director/generation-fields')
async def generation_fields(request):
    from .desk import template,preview_spec
    from .runtime import registry
    result=[]
    for nid,spec in {**template(),'preview':preview_spec({})}.items():
        if nid not in ('308','126','376','395','preview'):continue
        cls=registry(spec['class_type']);schema=cls.INPUT_TYPES();defs={**schema.get('required',{}),**schema.get('optional',{})}
        for name,value in spec['inputs'].items():
            definition=defs.get(name)
            if definition is None or isinstance(value,list):continue
            typ=definition[0];options=definition[1] if len(definition)>1 else {}
            choices=typ if isinstance(typ,list) else options.get('options') if typ=='COMBO' else None
            result.append({'nodeId':nid,'classType':spec['class_type'],'name':name,'label':name,'value':value,'choices':choices,'internal':True,**{key:options[key] for key in ('min','max','step') if key in options}})
    return web.json_response(result)

@PromptServer.instance.routes.get('/star7/director/continuous-preview/{key}')
async def continuous_preview(request):
    import re
    from .runtime import data_root
    key=request.match_info['key']
    if not re.fullmatch('[a-f0-9]{64}',key):raise web.HTTPNotFound()
    path=next(iter((data_root()/'projects').glob('*/previews/'+key+'.mp4')),data_root()/'previews'/(key+'.mp4'))
    if not path.is_file():raise web.HTTPNotFound()
    return web.FileResponse(path)

@PromptServer.instance.routes.post('/star7/director/package/export')
async def export_project_package(request):
    import asyncio
    from .packages import export_package
    path=None
    try:
        body=await request.json()
        path=await asyncio.to_thread(export_package,body['plan'],body['workflow'],folder_paths.get_input_directory())
        response=web.StreamResponse(headers={'Content-Type':'application/zip','Content-Disposition':'attachment; filename="Star7-Director-project.zip"','Content-Length':str(path.stat().st_size)})
        await response.prepare(request)
        with path.open('rb') as file:
            while True:
                chunk=await asyncio.to_thread(file.read,1024**2)
                if not chunk:break
                await response.write(chunk)
        await response.write_eof();return response
    except (ValueError,KeyError,OSError) as e:
        if path is not None:raise
        return web.json_response({'error':str(e)},status=400)
    finally:
        if path is not None:path.unlink(missing_ok=True)

@PromptServer.instance.routes.post('/star7/director/package/import')
async def import_project_package(request):
    import asyncio,uuid
    from .packages import import_package,LIMIT
    path=DATA/'packages'/(uuid.uuid4().hex+'.upload');path.parent.mkdir(parents=True,exist_ok=True)
    from .package_index import begin,update
    from urllib.parse import unquote
    pack_id=begin(DATA,unquote(request.headers.get('X-Star7-Package-Name','项目包.zip')),path)
    try:
        total=0
        with path.open('xb') as out:
            async for chunk in request.content.iter_chunked(1024**2):
                total+=len(chunk)
                if total>LIMIT:raise ValueError('项目包超过 2 GiB 上限')
                out.write(chunk)
        result=await asyncio.to_thread(import_package,path,pack_id)
        Storage(DATA).save_project(result['plan'])
        return web.json_response(result)
    except Exception as e:
        update(DATA,pack_id,state='failed');return web.json_response({'error':str(e)},status=400)
    finally:path.unlink(missing_ok=True)


@PromptServer.instance.routes.get('/star7/director/media/{filename:.+}')
async def project_media(request):
    from pathlib import Path
    from .assets import MEDIA
    name=request.match_info['filename'];path=(MEDIA/name).resolve()
    if not path.is_relative_to(MEDIA.resolve()) or not path.is_file():return web.Response(status=404)
    return web.FileResponse(path)

@PromptServer.instance.routes.post('/star7/director/library/export')
async def export_material_library(request):
    import asyncio
    from .library_packages import export_library
    path=None
    try:
        path=await asyncio.to_thread(export_library,await request.json())
        response=web.StreamResponse(headers={'Content-Type':'application/zip','Content-Disposition':'attachment; filename="Star7-library.zip"','Content-Length':str(path.stat().st_size)})
        await response.prepare(request)
        with path.open('rb') as file:
            while True:
                chunk=await asyncio.to_thread(file.read,1024**2)
                if not chunk:break
                await response.write(chunk)
        await response.write_eof();return response
    except Exception as e:
        if path is not None:raise
        return web.json_response({'error':str(e)},status=400)
    finally:
        if path is not None:path.unlink(missing_ok=True)

@PromptServer.instance.routes.post('/star7/director/library/import')
async def import_material_library(request):
    import asyncio,uuid
    from .library_packages import import_library
    from .packages import LIMIT
    path=DATA/'packages'/(uuid.uuid4().hex+'.upload');path.parent.mkdir(parents=True,exist_ok=True);pack_id=None
    try:
        reader=await request.multipart();part=await reader.next()
        if part is None or part.name!='library':raise ValueError('缺少当前素材库索引')
        raw=bytearray()
        while True:
            chunk=await part.read_chunk()
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>4*1024**2:raise ValueError('素材库索引过大')
        current=json.loads(raw);part=await reader.next()
        if part is None or part.name!='file':raise ValueError('缺少 ZIP 文件')
        from .package_index import begin
        pack_id=begin(DATA,part.filename or '素材库.zip',path)
        total=0
        with path.open('xb') as file:
            while True:
                chunk=await part.read_chunk()
                if not chunk:break
                total+=len(chunk)
                if total>LIMIT:raise ValueError('压缩包超过 2 GiB')
                file.write(chunk)
        result=await asyncio.to_thread(import_library,path,current,request.query.get('category','character'),pack_id)
        return web.json_response(result)
    except Exception as e:
        if pack_id:
            from .package_index import update
            update(DATA,pack_id,state='failed')
        return web.json_response({'error':str(e)},status=400)
    finally:path.unlink(missing_ok=True)

@PromptServer.instance.routes.post('/star7/director/cache/{project}')
@PromptServer.instance.routes.get('/star7/director/cache/{project}')
async def cache_status(request):
    import asyncio
    from .cache_management import stats
    try:
        body=await request.json() if request.method=='POST' else {}
        return web.json_response(await asyncio.to_thread(stats,DATA,request.match_info['project'],body.get('active_sources',[])))
    except Exception as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/cache/{project}/clear')
async def clear_cache(request):
    import asyncio
    from .cache_management import clear
    try:
        queue=PromptServer.instance.prompt_queue
        running,pending=queue.get_current_queue()
        from .batch_runner import active
        if running or pending or active():raise ValueError('任务运行中，请完成后再清理缓存')
        body=await request.json()
        return web.json_response(await asyncio.to_thread(clear,DATA,request.match_info['project'],body.get('kind'),body.get('package_id'),body.get('active_sources',[]),body.get('project_ids')))
    except Exception as e:return web.json_response({'error':str(e)},status=400)

def video_download(path,name):
    import re,urllib.parse,pathlib
    path=pathlib.Path(path).resolve();root=pathlib.Path(folder_paths.get_output_directory()).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('视频文件不可用')
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(name)).strip(' .')[:150] or 'video.mp4'
    name=pathlib.Path(name).stem+path.suffix
    return web.FileResponse(path,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+urllib.parse.quote(name),'Cache-Control':'no-store'})

@PromptServer.instance.routes.get('/star7/director/download-shot/{pid}/{sid}')
async def download_shot(request):
    from .core import identifier
    try:
        pid=identifier(request.match_info['pid']);sid=identifier(request.match_info['sid']);record=Storage(DATA).latest_output(pid,sid)
        if record is None:raise ValueError('当前镜头尚未生成')
        return video_download(record['path'],request.query.get('name',__import__('pathlib').Path(record['path']).name))
    except (ValueError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.get('/star7/director/download-film/{pid}/{filename}')
async def download_film(request):
    import pathlib,re
    from .core import identifier
    try:
        pid=identifier(request.match_info['pid']);name=request.match_info['filename']
        path=Storage(DATA).film_path(pid,name)
        if path is None:
            if not re.fullmatch(r'film_[0-9a-f]{12}\.mp4',name):raise ValueError('全片记录不存在')
            path=pathlib.Path(folder_paths.get_output_directory())/'Star7-Director'/pid/name
        return video_download(path,request.query.get('name',pathlib.Path(path).name))
    except (ValueError,OSError) as e:return web.json_response({'error':str(e)},status=400)

@PromptServer.instance.routes.post('/star7/director/storyboard/recognize')
async def recognize_storyboard(request):
    from .storyboard import recognize
    try:
        if request.content_length is None or request.content_length>8*2**20:raise ValueError('请求过大')
        body=await request.json()
        from .core import identifier
        pid=identifier(body['plan'].get('id'));store=Storage(DATA)
        with store.db(pid) as db:reserved=[row[0] for row in db.execute('SELECT shot FROM stages WHERE project=? UNION SELECT shot FROM outputs WHERE project=?',(pid,pid))]
        return web.json_response(recognize(body['plan'],body.get('text'),body.get('mode','append'),reserved))
    except (ValueError,KeyError,TypeError) as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.post('/star7/director/batch/start')
async def start_batch(request):
    from .batch_runner import start
    try:return web.json_response(await start(await request.json()))
    except Exception as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.get('/star7/director/batch/{run_id}')
async def batch_status(request):
    from .batch_runner import state
    try:return web.json_response(state(request.match_info['run_id']))
    except Exception as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.get('/star7/director/batch/project/{project}')
async def project_batch(request):
    from .batch_runner import latest
    try:return web.json_response({'run':latest(request.match_info['project'])})
    except Exception as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.post('/star7/director/batch/{run_id}/control')
async def batch_control(request):
    from .batch_runner import control
    try:
        body=await request.json();return web.json_response(control(request.match_info['run_id'],body.get('stop_after')))
    except Exception as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.post('/star7/director/batch/{run_id}/cancel')
async def batch_cancel(request):
    from .batch_runner import cancel_item
    try:
        body=await request.json();return web.json_response(cancel_item(request.match_info['run_id'],body['shot_id'],body.get('confirm') is True,body.get('expected')))
    except Exception as error:return web.json_response({'error':str(error)},status=400)

@PromptServer.instance.routes.get('/star7/director/tail-image/{pid}/{sid}')
async def tail_image(request):
    try:
        from .runtime import postprocess_source
        from .continuity import export_tail
        from .core import identifier
        import asyncio,io
        from PIL import Image
        pid=identifier(request.match_info['pid']);sid=identifier(request.match_info['sid'])
        def decode():
            pixels,_=export_tail(postprocess_source({'id':pid},sid),1,False)
            picture=Image.fromarray((pixels[0].cpu().numpy()*255).round().clip(0,255).astype('uint8'));picture.thumbnail((600,600))
            data=io.BytesIO();picture.save(data,format='PNG');return data.getvalue()
        return web.Response(body=await asyncio.to_thread(decode),content_type='image/png',headers={'Cache-Control':'no-store'})
    except Exception as error:return web.json_response({'error':str(error)},status=404)
