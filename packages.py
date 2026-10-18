"""Portable projects contain explicit source media only; never caches or models."""
import copy,hashlib,json,os,shutil,tempfile,uuid,zipfile
from pathlib import Path,PurePosixPath
from .core import validate,compile_plan,identifier
from .assets import MEDIA,verify_upload,finish_upload,EXTENSIONS

def asset_sources(asset):return [*asset.get('media',[]),*([asset['text_file']] if asset.get('text_file') else [])]

LIMIT=2*1024**3

def project_assets(plan):
    result=list(plan['assets'])
    for shot in plan['shots']:
        images=[m for m in [*shot.get('keyframes',{}).values(),*shot.get('keyframe_points',[])] if m.get('source') and not m.get('from_previous')]
        for image in images:image.setdefault('type','image')
        if images:result.append({'media':images,'shot_id':shot['id']})
    return result

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()

def workflow_plan(workflow,plan,original_id=None):
    result=copy.deepcopy(workflow)
    owners=[];libraries=set()
    for n in result.get('nodes',[]):
        if n.get('type') in ('Star7DirectorDesk','Star7DirectorPlan'):
            try:belongs=json.loads(n.get('widgets_values',['{}'])[0]).get('id')==(original_id or plan['id'])
            except (ValueError,TypeError,IndexError):belongs=False
            if belongs:owners.append(n)
    for owner in owners:
        for inp in owner.get('inputs',[]):
            if inp.get('name')=='asset_library' and inp.get('link') is not None:
                link=next((l for l in result.get('links',[]) if l[0]==inp['link']),None)
                if link:libraries.add(link[1])
    for n in result.get('nodes',[]):
        if n in owners:
            n['widgets_values']=[json.dumps(plan,ensure_ascii=False)]
            n.pop('widgets_values_named',None)
        elif n.get('type')=='Star7DirectorLibrary' and n.get('id') in libraries:
            try:library=json.loads(n.get('widgets_values',['{}'])[0])
            except (ValueError,TypeError,IndexError):library={}
            n['widgets_values']=[json.dumps({**library,'assets':plan['assets'],**({'reference_size':plan['reference_size']} if 'reference_size' in plan else {})},ensure_ascii=False)]
    return result

def export_package(plan,workflow,input_root):
    from .runtime import resolve_media,data_root
    plan=copy.deepcopy(plan);plan.pop('runtime',None);plan.pop('media_aliases',None)
    compile_plan(plan)
    if not isinstance(workflow,dict) or not isinstance(workflow.get('nodes'),list):raise ValueError('缺少完整工作流')
    directory=Path(__file__).parent/'data'/'packages';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(uuid.uuid4().hex+'.zip')
    entries={};total=0
    try:
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for asset in project_assets(plan):
                for media in asset_sources(asset):
                    source=media['source']
                    if source not in entries:
                        file=resolve_media(source).resolve()
                        if not (file.is_relative_to(Path(input_root).resolve()) or file.is_relative_to(MEDIA.resolve()) or file.is_relative_to((data_root()/'projects'/plan['id']/'media').resolve())):raise ValueError('素材不在项目素材目录或 ComfyUI input 中：'+source)
                        verify_upload(file,media['type'])
                        total+=file.stat().st_size
                        if total>LIMIT:raise ValueError('项目包素材超过 2 GiB 上限')
                        category='keyframes/'+identifier(asset['shot_id']) if asset.get('shot_id') else 'assets/'+asset['kind']
                        name='media/'+category+'/'+uuid.uuid4().hex+file.suffix.lower()
                        entries[source]={'path':name,'sha256':digest(file),'size':file.stat().st_size}
                        z.write(file,name)
            manifest={'format':'star7-director-project','version':1,'plan':plan,'media':entries}
            z.writestr('project.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            z.writestr('workflow.json',json.dumps(workflow_plan(workflow,plan),ensure_ascii=False,indent=2))
        return path
    except Exception:path.unlink(missing_ok=True);raise

def import_package(archive,pack_id=None):
    created=[]
    pack_root=Path(archive).parent.parent if pack_id else Path(__file__).parent/'data'
    staging=pack_root/'packages'/('stage_'+uuid.uuid4().hex)
    staging.mkdir(parents=True)
    if pack_id:
        from .package_index import update
        update(pack_root,pack_id,temporary=[str(Path(archive).relative_to(pack_root)),str(staging.relative_to(pack_root))])
    try:
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>LIMIT:raise ValueError('项目包超过大小或文件数量上限')
            names=set()
            for info in infos:
                p=PurePosixPath(info.filename)
                if info.filename in names or p.is_absolute() or '..' in p.parts or '\\' in info.filename or ':' in info.filename:raise ValueError('项目包包含非法路径或重复文件')
                names.add(info.filename)
            for name in ('project.json','workflow.json'):
                if z.getinfo(name).file_size>4*1024**2:raise ValueError('项目配置过大')
            manifest=json.loads(z.read('project.json'));workflow=json.loads(z.read('workflow.json'))
            if manifest.get('format')!='star7-director-project' or manifest.get('version')!=1:raise ValueError('不支持的项目包')
            plan=manifest['plan'];validate(plan);original_id=plan['id']
            for shot in plan['shots']:shot.pop('next_seed',None)
            entries=manifest['media'];mapped={};validated={}
            if not isinstance(entries,dict):raise ValueError('无效素材索引')
            for asset in project_assets(plan):
                for media in asset_sources(asset):
                    source=media['source'];entry=entries[source];name=entry['path']
                    if not name.startswith('media/') or name not in names:raise ValueError('素材包缺少文件')
                    suffix=PurePosixPath(name).suffix.lower()
                    if suffix not in EXTENSIONS[media['type']]:raise ValueError('素材格式不匹配')
                    if name not in validated:
                        target=staging/(uuid.uuid4().hex+suffix)
                        with z.open(name) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024**2)
                        if target.stat().st_size!=entry['size'] or digest(target)!=entry['sha256']:raise ValueError('素材校验失败')
                        validated[name]=target
                    verify_upload(validated[name],media['type'])
            MEDIA.mkdir(parents=True,exist_ok=True)
            destination=MEDIA
            if pack_id:
                from .package_index import import_folder
                destination=import_folder(MEDIA,pack_root,pack_id)
            for asset in project_assets(plan):
                for media in asset_sources(asset):
                    source=media['source'];entry=entries[source]
                    if source not in mapped:
                        src=validated[entry['path']];parent=destination.joinpath(*PurePosixPath(entry['path']).parts[1:-1]);parent.mkdir(parents=True,exist_ok=True);dest=parent/(uuid.uuid4().hex+src.suffix)
                        shutil.copyfile(src,dest);created.append(dest)
                        meta=finish_upload(dest,media.get('original_name',src.name),media['type'],entry['sha256'],MEDIA)
                        if meta.get('thumbnail_source'):created.append(MEDIA/meta['thumbnail_source'].removeprefix('star7-director/'))
                        mapped[source]=meta
                    kind=media['type'];media.pop('thumbnail_source',None);media.update(mapped[source]);media['type']=kind
            plan['id']='project_'+uuid.uuid4().hex[:12];plan.pop('runtime',None);plan.pop('media_aliases',None)
            from datetime import datetime,timezone
            plan['modified_at']=datetime.now(timezone.utc).isoformat()
            compile_plan(plan)
            if pack_id:
                snapshot=destination/'index.json';snapshot.write_text(json.dumps({'assets':plan['assets']},ensure_ascii=False,indent=2),encoding='utf-8');created.append(snapshot)
                update(pack_root,pack_id,sources=['star7-director/'+p.relative_to(MEDIA).as_posix() for p in created],state='ready')
            return {'plan':plan,'workflow':workflow_plan(workflow,plan,original_id)}
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise
    finally:
        resolved=staging.resolve()
        if resolved.is_relative_to((pack_root/'packages').resolve()):shutil.rmtree(resolved)
