"""Temporary continuous playback, independent of official exports."""
import hashlib,json,subprocess,threading,uuid,tempfile,time
from .runtime import data_root
from .combine import profile
from .core import identifier
LOCK=threading.Lock()
PROGRESS={};PROGRESS_LOCK=threading.Lock()
def update(job,percent,message,status='running'):
    if not job:return
    with PROGRESS_LOCK:
        for key in list(PROGRESS):
            if time.time()-PROGRESS[key]['updated']>3600:PROGRESS.pop(key,None)
        PROGRESS[job]={'percent':percent,'message':message,'status':status,'updated':time.time()}
def progress(job):
    with PROGRESS_LOCK:return dict(PROGRESS.get(job,{'percent':0,'message':'正在检查已生成的视频…','status':'running'}))

def clean(folder):
    referenced=set()
    for manifest in [*folder.glob('*-index.json'),*folder.glob('index.json')]:
        try:referenced.add(json.loads(manifest.read_text(encoding='utf8'))['file'])
        except (OSError,ValueError,KeyError):continue
    for path in folder.glob('*.mp4'):
        if len(path.stem)==64 and path.name not in referenced:
            try:path.unlink()
            except OSError:pass # A player may still hold the old file; retry next preparation.

def build(clips,project='legacy',notify=lambda percent,message:None):
    import imageio_ffmpeg,av
    folder=data_root()/'projects'/identifier(project)/'previews';folder.mkdir(parents=True,exist_ok=True)
    paths=[c['path'] for c in clips]
    def signature():return hashlib.sha256(json.dumps(['v2',project,[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths]]).encode()).hexdigest()
    key=signature();target=folder/(key+'.mp4');manifest=folder/'index.json'
    with LOCK:
        def publish():
            pending=manifest.with_suffix('.tmp');pending.write_text(json.dumps({'file':target.name}),encoding='utf8');pending.replace(manifest);clean(folder)
        if target.is_file():publish();notify(100,'视频未变化，已复用当前预览');return target
        notify(2,'正在准备新版预览…')
        token=uuid.uuid4().hex;listing=folder/(token+'.txt');temp=folder/(token+'.mp4');normalized=[]
        def run(args,duration,base,span,message):
            with tempfile.TemporaryFile() as errors:
                proc=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-y','-progress','pipe:1','-nostats',*args],stdout=subprocess.PIPE,stderr=errors,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in proc.stdout:
                    if line.startswith('out_time_us='):
                        try:notify(round(base+span*min(1,max(0,float(line.strip().split('=')[1])/1e6/max(duration,.01)))),message)
                        except ValueError:pass
                proc.wait();proc.stdout.close()
                if proc.returncode:
                    errors.seek(0);raise ValueError('连续预览准备失败，原镜头已保留：'+errors.read().decode('utf8',errors='replace')[-400:])
        try:
            first=profile(paths[0]);same=all(profile(p)==first for p in paths[1:]);inputs=paths
            if not same:
                w,h=first[1:3];fps=first[3] if first[3]!='None' else '24';inputs=[]
                for i,path in enumerate(paths):
                    out=folder/(token+'-'+str(i)+'.mp4');normalized.append(out)
                    with av.open(str(path)) as f:
                        has_audio=bool(f.streams.audio);duration=float(f.duration/av.time_base) if f.duration else clips[i]['duration']
                    args=['-i',str(path)]
                    if not has_audio:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
                    args+=['-map','0:v:0','-map','0:a:0' if has_audio else '1:a:0','-vf',f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1','-r',fps,'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-af','apad','-t',str(duration),str(out)]
                    run(args,duration,2+78*i/len(paths),78/len(paths),'正在统一预览格式 '+str(i+1)+'/'+str(len(paths)));inputs.append(out)
            listing.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n" for p in inputs),encoding='utf8')
            base=2 if same else 80
            run(['-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(temp)],sum(c['duration'] for c in clips),base,97-base,'正在拼接连续预览…')
            if signature()!=key:raise ValueError('准备期间镜头视频已更新，请再次点击预览；旧预览保留')
            temp.replace(target);publish();notify(100,'新版预览已就绪，旧版已清理')
            return target
        finally:
            for path in [listing,temp,*normalized]:path.unlink(missing_ok=True)
