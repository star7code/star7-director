"""Disk checkpoints use safetensors + an explicit tree, never pickle."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
try:
    from .core import identifier, STAGES, validate
except ImportError:
    from core import identifier, STAGES, validate

import threading
MIGRATION_LOCK=threading.RLock()
TABLES=('stages','outputs','base_aliases','retired_base_versions','films','output_versions')

class Storage:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self._migrate_legacy()
        self._migrate_files()
    @staticmethod
    def schema(db):
        db.execute("CREATE TABLE IF NOT EXISTS stages (project TEXT, shot TEXT, stage TEXT, version TEXT, fingerprint TEXT, artifact TEXT, PRIMARY KEY(project,shot,stage,version))")
        db.execute("CREATE TABLE IF NOT EXISTS outputs (project TEXT,shot TEXT,fingerprint TEXT,path TEXT,frame_count INTEGER,created INTEGER DEFAULT (unixepoch()),PRIMARY KEY(project,shot,fingerprint))")
        columns={r[1] for r in db.execute('PRAGMA table_info(outputs)')}
        for name in ('post_json','base_version','parameter_fingerprint'):
            if name not in columns:db.execute('ALTER TABLE outputs ADD COLUMN '+name+' TEXT')
        db.execute('CREATE TABLE IF NOT EXISTS base_aliases (project TEXT,shot TEXT,version TEXT,fingerprint TEXT,PRIMARY KEY(project,shot,version,fingerprint))')
        db.execute('CREATE TABLE IF NOT EXISTS retired_base_versions (project TEXT,shot TEXT,version TEXT,PRIMARY KEY(project,shot))')
        db.execute('CREATE TABLE IF NOT EXISTS films (project TEXT,filename TEXT,path TEXT,PRIMARY KEY(project,filename))')
        db.execute('CREATE TABLE IF NOT EXISTS output_versions (project TEXT,shot TEXT,version INTEGER,PRIMARY KEY(project,shot))')
    def projects(self):
        return sorted(p.parent.name for p in (self.root/'projects').glob('*/index.sqlite3'))
    def _migrate_legacy(self):
        import threading
        with MIGRATION_LOCK:
            old=self.root/'index.sqlite3'
            if not old.exists():return
            src=sqlite3.connect(old)
            try:
                tables=[r[0] for r in src.execute('SELECT name FROM sqlite_master WHERE type="table"') if r[0] in TABLES]
                ids=set()
                for table in tables:ids.update(r[0] for r in src.execute('SELECT DISTINCT project FROM '+table))
                for pid in ids:
                    path=self.root/'projects'/identifier(pid)/'index.sqlite3';path.parent.mkdir(parents=True,exist_ok=True);dest=sqlite3.connect(path)
                    try:
                        with dest:
                            self.schema(dest)
                            for table in tables:
                                columns=[r[1] for r in src.execute('PRAGMA table_info('+table+')')]
                                for row in src.execute('SELECT * FROM '+table+' WHERE project=? ORDER BY rowid',(pid,)):
                                    dest.execute('INSERT OR IGNORE INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',row)
                    finally:dest.close()
            finally:src.close()
            backup=self.root/'logs'/'legacy-index-before-migration.sqlite3';backup.parent.mkdir(parents=True,exist_ok=True)
            import shutil
            if not backup.exists():shutil.copy2(old,backup)
            old.unlink()
    def _migrate_files(self):
        import shutil,hashlib
        with MIGRATION_LOCK:
            for path in self.root.glob('*.json'):
                try:
                    plan=json.loads(path.read_text(encoding='utf8'))
                    if not isinstance(plan,dict) or plan.get('schema_version')!='1.0' or 'shots' not in plan:continue
                    pid=identifier(plan['id']);dest=self.root/'projects'/pid/'state.json';dest.parent.mkdir(parents=True,exist_ok=True)
                    if not dest.exists():shutil.copy2(path,dest)
                    path.unlink()
                except (ValueError,KeyError,OSError):continue
            for path in (self.root/'batches').glob('*.json'):
                try:
                    pid=identifier(json.loads(path.read_text(encoding='utf8'))['project_id']);dest=self.root/'projects'/pid/'batches'/path.name;dest.parent.mkdir(parents=True,exist_ok=True)
                    if not dest.exists():shutil.copy2(path,dest)
                    path.unlink()
                except (ValueError,KeyError,OSError):continue
            for project in (self.root/'projects').iterdir() if (self.root/'projects').exists() else []:
                if not project.is_dir():continue
                manifest=self.root/'previews'/(hashlib.sha256(project.name.encode()).hexdigest()+'-index.json')
                if not manifest.exists():continue
                try:
                    value=json.loads(manifest.read_text(encoding='utf8'));name=value['file']
                    if Path(name).name!=name or not name.endswith('.mp4'):continue
                    dest=project/'previews';dest.mkdir(exist_ok=True);source=manifest.parent/name
                    if source.exists() and not (dest/name).exists():shutil.copy2(source,dest/name)
                    shutil.copy2(manifest,dest/'index.json');source.unlink(missing_ok=True);manifest.unlink()
                except (ValueError,KeyError,OSError):continue
            for name in ('batches','previews'):
                try:(self.root/name).rmdir()
                except OSError:pass
    @contextmanager
    def db(self,project=None,create=True):
        if project is None:
            ids=self.projects()
            if len(ids)!=1:raise ValueError('Database access requires an explicit project ID')
            project=ids[0]
        path=self.root/'projects'/identifier(project)/'index.sqlite3'
        if create:path.parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(path if create or path.is_file() else ':memory:',timeout=30)
        try:
            with connection:
                self.schema(connection)
                yield connection
        finally:connection.close()
    def save_project(self,plan):
        validate(plan)
        path=self.root/'projects'/identifier(plan['id'])/'state.json';path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)
    def load_project(self,pid):
        path=self.root/'projects'/identifier(pid)/'state.json'
        if not path.exists():path=self.root/(identifier(pid)+'.json')
        return validate(json.loads(path.read_text(encoding='utf8')))
    def save_latent(self,project,shot,stage,fingerprint,latent):
        import torch
        from safetensors.torch import save_file
        from comfy.nested_tensor import NestedTensor
        if stage not in STAGES: raise ValueError('Invalid stage')
        folder=self.root/'projects'/identifier(project)/'cache'/identifier(shot)/stage
        folder.mkdir(parents=True,exist_ok=True)
        tensors={}
        def pack(value):
            if isinstance(value,NestedTensor): return {'type':'nested','items':[pack(v) for v in value.unbind()]}
            if isinstance(value,torch.Tensor):
                name='tensor_'+str(len(tensors))
                tensors[name]=value.detach().to('cpu').contiguous().clone()
                return {'type':'tensor','name':name}
            if isinstance(value,dict):
                if not all(isinstance(k,str) for k in value): raise TypeError('Cache dictionary keys must be text')
                return {'type':'dict','items':{k:pack(v) for k,v in value.items()}}
            if isinstance(value,(tuple,list)): return {'type':'tuple' if isinstance(value,tuple) else 'list','items':[pack(v) for v in value]}
            if value is None or isinstance(value,(str,int,float,bool)): return {'type':'scalar','value':value}
            raise TypeError('Unsupported cache object: '+type(value).__name__)
        tree=pack(latent)
        version=uuid.uuid4().hex
        path=folder/(version+'.safetensors')
        temp=path.with_suffix('.tmp')
        try:
            save_file(tensors,str(temp),metadata={'director_tree':json.dumps(tree,allow_nan=False),'fingerprint':fingerprint})
            os.replace(temp,path)
            with self.db(project) as db:
                db.execute('INSERT INTO stages VALUES (?,?,?,?,?,?)',(project,shot,stage,version,fingerprint,str(path.relative_to(self.root))))
                if stage=='base':db.execute('DELETE FROM retired_base_versions WHERE project=? AND shot=?',(project,shot))
        finally: temp.unlink(missing_ok=True)
        return version
    def load_latent(self,project,shot,stage,version,fingerprint=None):
        from safetensors import safe_open
        from comfy.nested_tensor import NestedTensor
        with self.db(project,create=False) as db:
            row=db.execute('SELECT fingerprint,artifact FROM stages WHERE project=? AND shot=? AND stage=? AND version=?',(identifier(project),identifier(shot),stage,identifier(version))).fetchone()
        if row is None: raise ValueError('Checkpoint not found')
        if fingerprint is not None and row[0]!=fingerprint: raise ValueError('Checkpoint belongs to an older shot revision')
        path=(self.root/row[1]).resolve()
        if not path.is_relative_to(self.root.resolve()): raise ValueError('Invalid checkpoint path')
        with safe_open(str(path),framework='pt',device='cpu') as f:
            def unpack(node):
                kind=node['type']
                if kind=='tensor': return f.get_tensor(node['name'])
                if kind=='scalar': return node['value']
                if kind=='dict': return {k:unpack(v) for k,v in node['items'].items()}
                values=[unpack(v) for v in node['items']]
                if kind=='nested': return NestedTensor(values)
                if kind=='tuple': return tuple(values)
                if kind=='list': return values
                raise ValueError('Unknown cache tree type')
            return unpack(json.loads(f.metadata()['director_tree']))
    def stages(self,project):
        with self.db(project,create=False) as db:
            rows=db.execute('SELECT shot,stage,version,fingerprint,artifact FROM stages WHERE project=? ORDER BY rowid',(identifier(project),)).fetchall()
        return [dict(zip(('shot','stage','version','fingerprint','artifact'),r)) for r in rows]
    def cache_was_cleared(self,project,shot):
        with self.db(project,create=False) as db:return db.execute('SELECT 1 FROM retired_base_versions WHERE project=? AND shot=?',(identifier(project),identifier(shot))).fetchone() is not None

    def alias_base(self,project,shot,version,fingerprint):
        with self.db(project) as db:db.execute('INSERT OR IGNORE INTO base_aliases VALUES (?,?,?,?)',(project,shot,version,fingerprint))
    def base_alias_matches(self,project,shot,version,fingerprint):
        with self.db(project,create=False) as db:return db.execute('SELECT 1 FROM base_aliases WHERE project=? AND shot=? AND version=? AND fingerprint=?',(project,shot,version,fingerprint)).fetchone() is not None
    def output_history(self,project,shot,limit=4):
        with self.db(project,create=False) as db:rows=db.execute('SELECT fingerprint,path,frame_count,post_json,base_version,parameter_fingerprint FROM outputs WHERE project=? AND shot=? ORDER BY created DESC,rowid DESC LIMIT ?',(project,shot,limit)).fetchall()
        return [{'fingerprint':r[0],'path':r[1],'frame_count':r[2],'post':json.loads(r[3]) if r[3] else None,'base_version':r[4],'parameter_fingerprint':r[5]} for r in rows]
    def record_output(self,project,shot,fingerprint,path,frame_count,post=None,base_version=None,parameter_fingerprint=None):
        identifier(project);identifier(shot)
        with self.db(project) as db:db.execute('INSERT OR REPLACE INTO outputs(project,shot,fingerprint,path,frame_count,post_json,base_version,parameter_fingerprint) VALUES (?,?,?,?,?,?,?,?)',(project,shot,fingerprint,path,frame_count,json.dumps(post) if post is not None else None,base_version,parameter_fingerprint))
    def latest_output(self,project,shot):
        with self.db(project,create=False) as db:row=db.execute('SELECT fingerprint,path,frame_count,post_json,base_version,parameter_fingerprint FROM outputs WHERE project=? AND shot=? ORDER BY created DESC,rowid DESC LIMIT 1',(identifier(project),identifier(shot))).fetchone()
        if not row:return None
        return {'fingerprint':row[0],'path':row[1],'frame_count':row[2],'post':json.loads(row[3]) if row[3] else None,'base_version':row[4],'parameter_fingerprint':row[5]}
    def record_film(self,project,path):
        identifier(project);path=Path(path)
        with self.db(project) as db:db.execute('INSERT OR REPLACE INTO films VALUES (?,?,?)',(project,path.name,str(path)))
    def film_path(self,project,filename):
        with self.db(project,create=False) as db:row=db.execute('SELECT path FROM films WHERE project=? AND filename=?',(identifier(project),filename)).fetchone()
        return row[0] if row else None
