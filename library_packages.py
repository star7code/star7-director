"""Standalone material archives; stage and validate before publishing sources."""
import copy,json,shutil,uuid,zipfile,unicodedata,re
from pathlib import Path,PurePosixPath
from .assets import MEDIA,EXTENSIONS,finish_upload,verify_upload
from .packages import LIMIT,digest
from .core import validate,KINDS

from .naming import initialize,next_name,retire_alias

def sources(asset):return [*asset.get('media',[]),*([asset['text_file']] if asset.get('text_file') else [])]

AUDIO={'.wav','.mp3','.flac','.ogg','.m4a'}
def normalized(value):return unicodedata.normalize('NFC',str(value)).casefold()
def check(library):
    if not isinstance(library,dict) or not isinstance(library.get('name','素材库'),str):raise ValueError('素材库索引无效')
    validate({'schema_version':'1.0','id':'library','assets':library.get('assets'),'shots':[]})
    from .reference_size import normalize
    normalize(library.get('reference_size'))
    counters=library.get('sequences',{})
    if not isinstance(counters,dict) or any(k not in KINDS or not isinstance(v,int) or isinstance(v,bool) or v<0 or v>1000000000 for k,v in counters.items()):raise ValueError('素材编号索引无效')
    names=set()
    for a in library['assets']:
        name=normalized(a['name'])
        if name in names:raise ValueError('素材名称重复：'+a['name'])
        names.add(name)
        for m in sources(a):
            if not isinstance(m,dict) or m.get('type') not in EXTENSIONS or not isinstance(m.get('source'),str):raise ValueError('素材来源索引无效')
            suffix=PurePosixPath(m['source']).suffix.lower()
            if a['kind']=='voice' and m['type']!='text' and (m['type']!='audio' or suffix not in AUDIO):raise ValueError('音色只支持音频文件：'+a['name'])
    return library

def export_library(library):
    from .runtime import resolve_media
    library=initialize(copy.deepcopy(check(library)));entries={};total=0;used_paths=set()
    directory=Path(__file__).parent/'data'/'packages';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(uuid.uuid4().hex+'.zip')
    try:
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED) as z:
            for a in library['assets']:
                if not a.get('media'):
                    content=str(a.get('description','')).encode('utf-8');source=a.get('text_file',{}).get('source') or 'text:'+a['id'];base=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',a['name']).strip(' .') or a['id'];name='media/'+base+'.txt';n=2
                    while name.casefold() in used_paths:name='media/'+base+'_'+str(n)+'.txt';n+=1
                    used_paths.add(name.casefold());z.writestr(name,content)
                    import hashlib
                    entries[source]={'path':name,'size':len(content),'sha256':hashlib.sha256(content).hexdigest()};a['text_file']={**a.get('text_file',{}),'type':'text','source':source,'original_name':a.get('text_file',{}).get('original_name') or a.get('original_name') or a['name']+'.txt'}
                    continue
                for m in sources(a):
                    source=m['source']
                    if source in entries:continue
                    file=resolve_media(source);verify_upload(file,m['type']);total+=file.stat().st_size
                    if total>LIMIT:raise ValueError('素材库超过 2 GiB')
                    base=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',a['name']).strip(' .') or a['id'];name='media/'+base+file.suffix.lower();n=2
                    while name.casefold() in used_paths:name='media/'+base+'_'+str(n)+file.suffix.lower();n+=1
                    used_paths.add(name.casefold())
                    entries[source]={'path':name,'size':file.stat().st_size,'sha256':digest(file)};z.write(file,name)
            z.writestr('index.json',json.dumps({'format':'star7-director-library','version':1,'name':library.get('name') or '素材库','sequences':library['sequences'],'reference_size':library.get('reference_size'),'assets':library['assets'],'media':entries},ensure_ascii=False,indent=2))
        return path
    except Exception:path.unlink(missing_ok=True);raise

def import_library(archive,current,category='character',pack_id=None):
    current=initialize(copy.deepcopy(check(current)))
    if category not in KINDS:raise ValueError('无效素材分类')
    pack_root=Path(archive).parent.parent if pack_id else Path(__file__).parent/'data'
    directory=pack_root/'packages';staging=directory/('library_stage_'+uuid.uuid4().hex);staging.mkdir(parents=True)
    if pack_id:
        from .package_index import update
        update(pack_root,pack_id,temporary=[str(Path(archive).relative_to(pack_root)),str(staging.relative_to(pack_root))])
    created=[];skipped=[];initially_empty=not current['assets']
    try:
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist();names=set()
            if len(infos)>10000 or sum(i.file_size for i in infos)>LIMIT:raise ValueError('压缩包超过 2 GiB 或文件数量上限')
            for i in infos:
                p=PurePosixPath(i.filename)
                if i.filename in names or p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('压缩包包含非法路径或重复文件')
                names.add(i.filename)
            def extract(name,suffix):
                file=staging/(uuid.uuid4().hex+suffix)
                with z.open(name) as src,file.open('xb') as dst:shutil.copyfileobj(src,dst,1024**2)
                return file
            pending=[];archive_name=None;structured=False
            if 'index.json' in names:
                if z.getinfo('index.json').file_size>4*1024**2:raise ValueError('素材索引过大')
                index=json.loads(z.read('index.json'));structured=True
                if index.get('format')!='star7-director-library' or index.get('version')!=1:raise ValueError('不是支持的素材库索引')
                initialize(check(index));archive_name=index.get('name');entries=index.get('media',{});files={}
                for a in index['assets']:
                    for m in sources(a):
                        entry=entries.get(m['source']);name=entry.get('path') if isinstance(entry,dict) else None
                        if not isinstance(name,str) or not name.startswith('media/') or name not in names:raise ValueError('素材索引缺少文件')
                        suffix=PurePosixPath(name).suffix.lower()
                        if suffix not in EXTENSIONS[m['type']]:raise ValueError('素材格式与索引不匹配')
                        if name not in files:
                            file=extract(name,suffix)
                            if file.stat().st_size!=entry.get('size') or digest(file)!=entry.get('sha256'):raise ValueError('素材文件校验失败')
                            files[name]=file
                        verify_upload(files[name],m['type'])
                    pending.append((copy.deepcopy(a),[(files[entries[m['source']]['path']],m) for m in sources(a)]))
            else:
                for info in infos:
                    if info.is_dir() or PurePosixPath(info.filename).name.startswith('.') or info.filename.startswith('__MACOSX/'):continue
                    suffix=PurePosixPath(info.filename).suffix.lower();typ='image' if suffix in EXTENSIONS['image'] else 'audio' if suffix in AUDIO else 'video' if suffix in EXTENSIONS['video'] else None
                    allowed=(typ=='audio' if category=='voice' else typ=='video' if category=='video' else typ in ('audio','video') or suffix=='.txt' if category=='effect' else typ=='image') or suffix=='.txt'
                    if not allowed:skipped.append(info.filename+'：格式与分类不匹配');continue
                    try:
                        file=extract(info.filename,suffix);description=''
                        if suffix=='.txt':
                            if file.stat().st_size>1024**2:raise ValueError('文字超过 1 MiB')
                            description=file.read_text(encoding='utf-8-sig')
                            if not description.strip() or '\0' in description:raise ValueError('文字为空或格式无效')
                        else:verify_upload(file,typ)
                        a={'original_name':PurePosixPath(info.filename).name,'id':category+'_'+uuid.uuid4().hex[:12],'name':PurePosixPath(info.filename).stem,'kind':category,'description':description,'media':[]}
                        pending.append((a,[(file,{'type':'text' if suffix=='.txt' else typ,'original_name':PurePosixPath(info.filename).name})]))
                    except Exception as e:skipped.append(info.filename+'：'+str(e))
                if not pending:raise ValueError('压缩包没有可导入的素材。'+('；'.join(skipped[:8])))
            # Deduplicate before moving files; bindings follow the same ID mapping.
            used={normalized(a['name']):a for a in current['assets']};hashes={m.get('content_hash'):a for a in current['assets'] for m in sources(a) if m.get('content_hash')}
            mappings={};accepted=[]
            for a,media in pending:
                duplicate=used.get(normalized(a['name'])) if structured else next((card for card in [*current['assets'],*(item[0] for item in accepted)] if normalized(card.get('original_name',''))==normalized(a.get('original_name')) or any(normalized(m.get('original_name',''))==normalized(a.get('original_name')) for m in card.get('media',[]))),None)
                file_hashes=[digest(file) for file,_ in media]
                if not duplicate:duplicate=next((hashes[h] for h in file_hashes if h in hashes),None)
                if duplicate:
                    if a.get('voice_id') is not None or a['kind']!=duplicate['kind']:
                        if a['kind']!=duplicate['kind']:raise ValueError('同名或同内容素材的分类冲突：'+a['name'])
                    mappings[a['id']]=duplicate['id'];skipped.append(a['name']+'：已有该素材');continue
                if not structured:a['name'],a['sequence']=next_name({'assets':[*current['assets'],*(card for card,_ in accepted)]},a['kind'])
                old=a['id'];existing_ids={card['id'] for card in current['assets']}|{card['id'] for card,_ in accepted};a['id']=old if old not in existing_ids else a['kind']+'_'+uuid.uuid4().hex[:12];mappings[old]=a['id'];retire_alias({'assets':[*current['assets'],*(card for card,_ in accepted)]},a['name'],a['id']);used[normalized(a['name'])]=a
                for h in file_hashes:hashes[h]=a
                accepted.append((a,media))
            if len(current['assets'])+len(accepted)>500:raise ValueError('素材库最多 500 个素材')
            MEDIA.mkdir(parents=True,exist_ok=True)
            destination=MEDIA
            if pack_id and accepted:
                from .package_index import import_folder
                destination=import_folder(MEDIA,pack_root,pack_id)
            for a,media in accepted:
                a['media']=[]
                for file,meta in media:
                    dest=destination/(uuid.uuid4().hex+file.suffix);shutil.copyfile(file,dest);created.append(dest)
                    stored=finish_upload(dest,meta.get('original_name',file.name),meta['type'],digest(file),MEDIA)
                    if stored.get('thumbnail_source'):created.append(MEDIA/stored['thumbnail_source'].removeprefix('star7-director/'))
                    if meta['type']=='text':a['text_file']={**meta,**stored}
                    else:a['media'].append({**meta,**stored})
                if a.get('voice_id'):a['voice_id']=mappings[a['voice_id']]
                current['assets'].append(a)
            if not current.get('name') or (initially_empty and archive_name):current['name']=archive_name or current.get('name') or '素材库'
            if structured:
                if initially_empty and index.get('reference_size') is not None:current['reference_size']=index['reference_size']
                for kind,value in index['sequences'].items():current['sequences'][kind]=max(current['sequences'].get(kind,0),value)
            initialize(check(current))
            if pack_id:
                if accepted:
                    snapshot=destination/'index.json';snapshot.write_text(json.dumps({'name':archive_name or current['name'],'assets':[a for a,_ in accepted]},ensure_ascii=False,indent=2),encoding='utf-8');created.append(snapshot)
                update(pack_root,pack_id,sources=['star7-director/'+p.relative_to(MEDIA).as_posix() for p in created],state='ready')
            current['message']=f'已导入 {len(accepted)} 个素材。'+(' 跳过：'+'；'.join(skipped[:12]) if skipped else '')
            return current
    except Exception:
        for file in created:file.unlink(missing_ok=True)
        raise
    finally:shutil.rmtree(staging)
