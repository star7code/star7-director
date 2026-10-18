"""Local project snapshots own media/cache, but only index generated videos."""
import copy,json,uuid,hashlib,shutil,threading
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .runtime import data_root,resolve_media
from .storage import Storage
from .core import validate,identifier
from .packages import workflow_plan

LOCK=threading.RLock()
def stamp():return datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
def folder(pid):return data_root()/'projects'/identifier(pid)
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    try:tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)
def copy_atomic(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:shutil.copy2(source,tmp);tmp.replace(target)
    finally:tmp.unlink(missing_ok=True)

def listing():
    with LOCK:return _listing()
def _listing():
    result=[]
    for path in (data_root()/'projects').glob('*/project.json'):
        try:
            item=json.loads(path.read_text(encoding='utf8'));p=item['plan']
            # Legacy library-panel autosaves are media containers, not projects.
            # Keep their files: real projects may still reference those images.
            import re
            if re.fullmatch(r'library_[0-9]+',p['id']) and not p['shots']:continue
            result.append({'id':p['id'],'title':p.get('title') or p['id'],'modified_at':item['saved_at'],'shots':len(p['shots'])})
        except (ValueError,OSError,KeyError):continue
    return sorted(result,key=lambda p:p['modified_at'],reverse=True)
def default_title():
    name='NP-'+stamp();existing={p['title'] for p in listing()};value=name;n=2
    while value in existing:value=name+'-'+str(n);n+=1
    return value

def read(pid):
    with LOCK:
        path=folder(pid)/'project.json'
        if not path.is_file():raise ValueError('项目不存在或已删除')
        return json.loads(path.read_text(encoding='utf8'))
def own_media(plan):
    mappings={};aliases=dict(plan.get('media_aliases',{}));base=folder(plan['id'])/'media';base.mkdir(parents=True,exist_ok=True)
    def visit(value,category):
        if isinstance(value,list):
            for v in value:visit(v,category)
        elif isinstance(value,dict):
            for key,item in list(value.items()):
                if key in ('source','thumbnail_source') and isinstance(item,str):
                    if item.startswith('star7-project/'+plan['id']+'/media/'):continue
                    if item not in mappings:
                        src=resolve_media(item);hasher=hashlib.sha256()
                        with src.open('rb') as stream:
                            for chunk in iter(lambda:stream.read(1024**2),b''):hasher.update(chunk)
                        digest=hasher.hexdigest();identity=aliases.get(item,item);name=category+'/'+hashlib.sha256(identity.encode()).hexdigest()[:12]+'-'+digest[:24]+src.suffix.lower();dest=base/name;dest.parent.mkdir(parents=True,exist_ok=True)
                        if not dest.exists():
                            copy_atomic(src,dest)
                        target='star7-project/'+plan['id']+'/media/'+name;mappings[item]=target;aliases[target]=aliases.get(item,item)
                    value[key]=mappings[item]
                else:visit(item,category)
    for asset in plan['assets']:visit(asset,'assets/'+asset['kind'])
    for shot in plan['shots']:
        visit(shot.get('keyframes',{}),'keyframes/'+shot['id'])
        visit(shot.get('keyframe_points',[]),'keyframes/'+shot['id'])
    if aliases:plan['media_aliases']=aliases
    return mappings
def migrate_cache(pid):
    store=Storage(data_root());target=folder(pid)/'cache';target.mkdir(parents=True,exist_ok=True)
    for row in store.stages(pid):
        source=(data_root()/row['artifact']).resolve()
        if source.is_relative_to(target.resolve()) or not source.is_file():continue
        dest=target/row['shot']/row['stage']/source.name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():copy_atomic(source,dest)
        with store.db(pid) as db:db.execute('UPDATE stages SET artifact=? WHERE project=? AND shot=? AND stage=? AND version=?',(str(dest.relative_to(data_root())),pid,row['shot'],row['stage'],row['version']))
        # Each indexed stage belongs to this project. Copies of other projects
        # use their own rows/artifacts, never the same mutable cache file.
        if source.is_relative_to((data_root()/pid).resolve()):
            try:source.unlink(missing_ok=True)
            except PermissionError:pass
def save(plan,workflow,manual=False):
    validate(plan)
    with LOCK:
        plan=copy.deepcopy(plan);plan.pop('runtime',None);pid=identifier(plan['id'])
        maps=own_media(plan);flow=workflow_plan(workflow,plan)
        saved=datetime.now(timezone.utc).isoformat();old_path=folder(pid)/'project.json'
        if old_path.is_file():
            old=json.loads(old_path.read_text(encoding='utf8'))
            if old['plan']==plan and old.get('workflow')==flow:saved=old['saved_at']
        item={'plan':plan,'workflow':flow,'saved_at':saved,'manual':manual}
        atomic(folder(pid)/'project.json',item);Storage(data_root()).save_project(plan);migrate_cache(pid)
        return {**item,'media_map':maps}
def clone(plan,workflow,title=None):
    validate(plan)
    with LOCK:
        source=plan['id'];original=copy.deepcopy(plan);plan=copy.deepcopy(plan)
        plan['id']='P-'+stamp()+'-'+uuid.uuid4().hex[:6];plan['title']=title or default_title();plan.pop('runtime',None)
        target=plan['id']
        try:
            result=save(plan,workflow_plan(workflow,plan,source),True);store=Storage(data_root())
            # Copy complete auxiliary stages, retaining versions and fingerprints.
            for row in store.stages(source):
                path=(data_root()/row['artifact']).resolve()
                if not path.is_relative_to(data_root().resolve()) or not path.is_file():continue
                dest=folder(target)/'cache'/row['shot']/row['stage']/path.name;dest.parent.mkdir(parents=True,exist_ok=True);copy_atomic(path,dest)
                with store.db(target) as db:db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',(target,row['shot'],row['stage'],row['version'],row['fingerprint'],str(dest.relative_to(data_root()))))
            with store.db(source) as source_db,store.db(target) as db:
                for table in ('outputs','base_aliases','retired_base_versions','films','output_versions'):
                    if not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():continue
                    columns=[r[1] for r in source_db.execute('PRAGMA table_info('+table+')')];rows=source_db.execute('SELECT * FROM '+table+' WHERE project=?',(source,)).fetchall()
                    for row in rows:
                        values=list(row);values[columns.index('project')]=target;db.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',values)
            return result
        except Exception:
            database=Storage(data_root())
            with database.db(target) as db:
                for table in ('stages','outputs','base_aliases','retired_base_versions','films','output_versions'):
                    if db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():db.execute('DELETE FROM '+table+' WHERE project=?',(target,))
            path=folder(target).resolve();base=(data_root()/'projects').resolve()
            if path.parent==base and path.name==target and path.exists():shutil.rmtree(path)
            (data_root()/(target+'.json')).unlink(missing_ok=True)
            raise

def create(plan,workflow):
    old=plan['id'];new=copy.deepcopy(plan);new['id']='P-'+stamp()+'-'+uuid.uuid4().hex[:6];new['title']=default_title();new['assets']=[];new['shots']=[];new['shot_sequence']=0;new.pop('runtime',None);new.pop('media_aliases',None);new.pop('asset_sequences',None)
    return save(new,workflow_plan(workflow,new,old),True)
def rename(pid,title):
    title=str(title).strip()
    if not title or len(title)>120:raise ValueError('项目名称需为1–120个字符')
    item=read(pid);item['plan']['title']=title;return save(item['plan'],item['workflow'],True)
def delete(pid):
    from .batch_runner import RUNS,LOCK as batch_lock
    with batch_lock:
        if any(r['project_id']==pid and r['status'] in ('queued','running') for r in RUNS.values()):raise ValueError('项目正在生成或排队，不能删除')
    with LOCK:
        read(pid);source=folder(pid);destination=data_root()/'project-trash'/(identifier(pid)+'-'+uuid.uuid4().hex[:6]);destination.parent.mkdir(parents=True,exist_ok=True)
        # Its own SQLite index moves with the folder; video files stay in output.
        source.replace(destination)
        (data_root()/(identifier(pid)+'.json')).unlink(missing_ok=True)
        return {'deleted':pid,'message':'项目已移入本地回收区；生成视频保留。'}
