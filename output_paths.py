"""Daily output folders; project identity remains in the database index."""
import re
from datetime import datetime,timezone,timedelta

def output_prefix(title,now=None):
    moment=(now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=8)))
    title=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(title)).strip(' .')[:60] or 'video'
    return 'Star7-Director/'+moment.strftime('%Y-%m-%d')+'/S7D-'+moment.strftime('%Y%m%d-%H%M%S')+'-'+title

def reserve_film(output_root,title='final-film'):
    from pathlib import Path
    prefix=Path(output_root)/output_prefix(title);prefix.parent.mkdir(parents=True,exist_ok=True)
    n=0
    while True:
        path=prefix.with_name(prefix.name+(('-'+str(n+1)) if n else '')+'.mp4')
        try:
            with path.open('xb'):pass
            return path
        except FileExistsError:n+=1

def shot_code(shot_id):
    from .core import identifier
    identifier(shot_id);match=re.fullmatch(r'shot_(\d+)',shot_id)
    return 'shot'+str(int(match[1])).zfill(3) if match else 'shot'+shot_id.replace('_','')

def reserve_generated(output_root,data_root,project,shot_id):
    from .storage import Storage
    from .core import identifier
    from pathlib import Path
    identifier(project);identifier(shot_id);store=Storage(data_root)
    with store.db(project) as db:
        db.execute('CREATE TABLE IF NOT EXISTS output_versions (project TEXT,shot TEXT,version INTEGER,PRIMARY KEY(project,shot))')
    with store.db(project) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT version FROM output_versions WHERE project=? AND shot=?',(project,shot_id)).fetchone();version=(row[0] if row else 0)+1
        while True:
            title=shot_code(shot_id)+(('-'+str(version)) if version>1 else '')
            path=Path(output_root)/(output_prefix(title)+'.mp4');path.parent.mkdir(parents=True,exist_ok=True)
            try:
                with path.open('xb'):pass
                break
            except FileExistsError:version+=1
        db.execute('INSERT OR REPLACE INTO output_versions VALUES (?,?,?)',(project,shot_id,version))
    return path
