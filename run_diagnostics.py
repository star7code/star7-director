"""Observe Star7 jobs without launching, supervising or changing ComfyUI."""
import os,json,time,threading,sys,faulthandler,atexit
LOCK=threading.Lock();FAULT_FILE=None

def install_fault_handler(root):
    global FAULT_FILE
    # Keep an already configured launcher fault handler untouched.
    with LOCK:
        if not faulthandler.is_enabled():
            try:
                folder=root/'logs';folder.mkdir(exist_ok=True);FAULT_FILE=(folder/'native-fault.log').open('a',encoding='utf8');faulthandler.enable(file=FAULT_FILE,all_threads=True)
            except (OSError,RuntimeError):pass
def monitor(run,root):
    path=root/'projects'/run['project_id']/'diagnostics'/'generation.jsonl'
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with LOCK:
            if path.exists() and path.stat().st_size>4*1024**2:path.replace(path.with_suffix('.previous.jsonl'))
    except OSError:return lambda:None
    stop=threading.Event()
    def write(event):
        try:
            row={'time':time.time(),'event':event,'pid':os.getpid(),'parent_pid':os.getppid(),'run_id':run['id'],'shot':run.get('active_shot_id'),'phase':run.get('phase'),'status':run.get('status')}
            import psutil
            process=psutil.Process();memory=process.memory_info();row.update(rss=memory.rss,private_bytes=getattr(memory,'private',None),process_started=process.create_time(),available_ram=psutil.virtual_memory().available)
            if event=='start':row['executable']=sys.executable;row['arguments']=sys.argv;row['shot_ids']=run['shot_ids']
            with LOCK:
                with path.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        except Exception:pass
    write('start')
    def observe():
        while not stop.wait(15):write('heartbeat')
    threading.Thread(target=observe,daemon=True,name='Star7-job-diagnostics').start()
    def exited():
        if not stop.is_set():write('process_exit')
    atexit.register(exited)
    def finish():
        stop.set();atexit.unregister(exited);write('end')
    return finish
