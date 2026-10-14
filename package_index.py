"""Import provenance for package-specific temporary cache reporting."""
import json,os,uuid,threading,time
from pathlib import Path
_lock=threading.RLock()
def read(root):
    path=Path(root)/'package-index.json'
    if not path.exists():return []
    return json.loads(path.read_text(encoding='utf-8'))
def update(root,pack_id,**fields):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with _lock:
        records=read(root);record=next((r for r in records if r['id']==pack_id),None)
        if record is None:record={'id':pack_id,'created':time.time(),'temporary':[],'sources':[]};records.append(record)
        record.update(fields);path=root/'package-index.json';temp=root/(uuid.uuid4().hex+'.index.tmp')
        try:temp.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
        finally:temp.unlink(missing_ok=True)
def begin(root,name,archive):
    pack_id=uuid.uuid4().hex;update(root,pack_id,name=Path(str(name).replace('\\','/')).name,temporary=[str(Path(archive).relative_to(root))],state='importing');return pack_id

def import_folder(media,root,pack_id):
    import re
    record=next((r for r in read(root) if r['id']==pack_id),{})
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(record.get('name','素材包')).stem).strip(' .')[:70] or '素材包'
    folder=Path(media)/'imports'/(name+'_'+pack_id)
    folder.mkdir(parents=True,exist_ok=False)
    return folder
