"""Explicit cache cleanup; original material files and final outputs are never deleted."""
import time,shutil
from pathlib import Path
from .storage import Storage
from .core import identifier,STAGES

def size(path):
    path=Path(path)
    if not path.exists() or path.is_symlink():return 0
    if path.is_file():return path.stat().st_size
    root=path.resolve()
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root))

def stale_packages(root):
    folder=Path(root)/'packages';cutoff=time.time()-86400
    if not folder.is_dir():return []
    return [p for p in folder.iterdir() if not p.is_symlink() and p.resolve().is_relative_to(folder.resolve()) and p.stat().st_mtime<cutoff and (p.suffix in ('.upload','.zip') or p.name.startswith(('stage_','library_stage_')))]

def referenced_sources(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('source','thumbnail_source') and isinstance(item,str):yield item
            else:yield from referenced_sources(item)
    elif isinstance(value,list):
        for item in value:yield from referenced_sources(item)

def protected_sources(root,active_sources=()):
    import json
    if not isinstance(active_sources,(list,tuple)) or any(not isinstance(s,str) for s in active_sources):raise ValueError('素材引用列表无效')
    protected=set(active_sources)
    for path in [*Path(root).glob('*.json'),*Path(root).glob('projects/*/project.json'),*Path(root).glob('projects/*/state.json')]:
        if path.name=='package-index.json':continue
        try:protected.update(referenced_sources(json.loads(path.read_text(encoding='utf-8'))))
        except (ValueError,OSError):raise ValueError('项目引用记录无法读取，已停止删除')
    return protected

def package_groups(root,active_sources=()):
    from .package_index import read
    result=[];root=Path(root).resolve();cutoff=time.time()-86400;protected=protected_sources(root,active_sources)
    for record in read(root):
        if record.get('state')=='deleted':continue
        temporary=[];materials=[]
        for relative in record.get('temporary',[]):
            path=(root/relative).resolve()
            if path.is_relative_to(root/'packages') and path.exists() and not path.is_symlink() and path.stat().st_mtime<cutoff:temporary.append(path)
        for source in record.get('sources',[]):
            if not source.startswith('star7-director/'):raise ValueError('素材包路径无效')
            path=(root/'media'/source.removeprefix('star7-director/')).resolve()
            if not path.is_relative_to(root/'media'):raise ValueError('素材包路径无效')
            if path.exists():materials.append(path)
        in_use=record.get('state')=='importing' or bool(set(record.get('sources',[]))&protected)
        result.append({'id':record['id'],'name':record.get('name','未命名压缩包'),'state':record.get('state'),'temporary_bytes':sum(size(p) for p in temporary),'material_bytes':sum(size(p) for p in materials),'in_use':in_use,'paths':temporary,'materials':materials})
    return result

def stats(root,project,active_sources=()):
    root=Path(root);project=identifier(project);store=Storage(root);checkpoints=0
    for row in store.stages(project):
        path=(root/row['artifact']).resolve()
        if (path.is_relative_to((root/project).resolve()) or path.is_relative_to((root/'projects'/project/'cache').resolve())) and path.suffix=='.safetensors':checkpoints+=size(path)
    projects=[]
    pids=store.projects()
    for pid in pids:
        identifier(pid);amount=0
        for row in store.stages(pid):
            path=(root/row['artifact']).resolve()
            if (path.is_relative_to(root.resolve()/pid) or path.is_relative_to((root/'projects'/pid/'cache').resolve())) and path.suffix=='.safetensors':amount+=size(path)
        if not amount:continue
        title=pid
        try:
            import json
            value=store.load_project(pid);title=value.get('title') or pid
        except (OSError,ValueError):pass
        projects.append({'id':pid,'name':title,'bytes':amount,'current':pid==project})
    return {'temporary_bytes':sum(size(p) for p in stale_packages(root)),'checkpoint_bytes':checkpoints,'other_checkpoint_bytes':sum(p['bytes'] for p in projects if not p['current']),'projects':projects,'material_bytes':size(root/'media'),'packages':[{k:v for k,v in p.items() if k not in ('paths','materials')} for p in package_groups(root,active_sources)]}

def clear(root,project,kind,pack_id=None,active_sources=()):
    root=Path(root).resolve();project=identifier(project);freed=0
    if kind in ('package','packages'):
        groups=package_groups(root,active_sources)
        if kind=='package':
            groups=[g for g in groups if g['id']==pack_id]
            if not groups:raise ValueError('素材包记录不存在')
            if groups[0]['state']=='ready' and groups[0]['in_use']:raise ValueError('素材包正在被素材库、工作流或已保存项目使用，不能删除')
        else:groups=[g for g in groups if g['state']=='ready' and not g['in_use']]
        from .package_index import update
        for group in groups:
            targets=[*group['paths'],*(group['materials'] if group['state']=='ready' else [])]
            for path in targets:
                freed+=size(path)
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink(missing_ok=True)
            if group['state']=='ready':
                # Each import owns a separate directory; remove it only when empty.
                for path in group['materials']:
                    parent=path.parent
                    if parent.is_relative_to(root/'media'/'imports'):
                        try:parent.rmdir()
                        except OSError:pass
                update(root,group['id'],state='deleted')
    elif kind=='temporary':
        for path in stale_packages(root):
            freed+=size(path)
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink(missing_ok=True)
    elif kind in ('checkpoints','other_checkpoints'):
        store=Storage(root)
        pids=[project] if kind=='checkpoints' else [pid for pid in store.projects() if pid!=project]
        for project_id in pids:
            with store.db(project_id) as db:
                rows=db.execute('SELECT project,shot,stage,version,artifact FROM stages WHERE project=? ORDER BY rowid',(project_id,)).fetchall()
                targets=[]
                for pid,sid,stage,version,artifact in rows:
                    identifier(pid);identifier(sid)
                    path=(root/artifact).resolve()
                    owned=path.is_relative_to(root/pid) or path.is_relative_to(root/'projects'/pid/'cache')
                    if stage not in STAGES or not owned or path.suffix!='.safetensors':raise ValueError('缓存路径无效，已停止清理')
                    targets.append((pid,sid,stage,version,path))
                for pid,sid,stage,version,path in targets:
                    freed+=size(path);path.unlink(missing_ok=True)
                    if stage=='base':
                        # Tiny revision metadata supports old video fingerprints;
                        # no latent tensor or reusable checkpoint is retained.
                        db.execute('INSERT OR REPLACE INTO retired_base_versions VALUES (?,?,?)',(pid,sid,version))
                    db.execute('DELETE FROM stages WHERE project=? AND shot=? AND stage=? AND version=?',(pid,sid,stage,version))
                    db.execute('DELETE FROM base_aliases WHERE project=? AND shot=? AND version=?',(pid,sid,version))
    else:raise ValueError('不支持的缓存清理类型')
    return {'freed_bytes':freed,**stats(root,project,active_sources)}
