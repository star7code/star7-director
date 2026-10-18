"""Server-owned sequential ComfyUI jobs. Browser polling is display-only."""
import asyncio,copy,json,secrets,time,uuid
from pathlib import Path
from .core import validate,preflight,identifier,dependency_source
from .runtime import data_root,Star7DirectorBaseCache,output_matches,batch_plan,parameter_matches
from .storage import Storage
from .generation_checks import validate_generation

from .execution_state import LOCK
RUNS={};TASKS={};MAX_SEED=2**53-1

def stop_prompt(pid):
    """Cancel only this native prompt; never set an unscoped interrupt flag."""
    from server import PromptServer
    queue=PromptServer.instance.prompt_queue
    if queue.delete_queue_item(lambda item:item[1]==pid):return True
    interrupt=getattr(queue,'interrupt_if_running',None)
    if callable(interrupt):return interrupt(pid)
    raise ValueError('当前 ComfyUI 不支持安全的指定任务中断，请使用原生队列停止')

async def wait_owned(run,pid,sid):
    if sid in run.get('cancelled',{}):stop_prompt(pid)
    try:await wait_job(pid)
    except Exception:
        if sid not in run.get('cancelled',{}):raise
    if sid in run.get('cancelled',{}):
        update(run,position=run['position']+1,active_shot_id=None,phase=None,message='已停止 '+sid+'；已有视频和缓存保留，继续其他可执行任务。')
        return False
    return True
def active():
    with LOCK:return any(r['status'] in ('queued','running') for r in RUNS.values())

def native_queue_items(project):
    from .execution_state import native_jobs
    known={(r.get('prompt_id'),r.get('owner_id')) for r in RUNS.values()}
    items=[]
    for job in native_jobs():
        if job['plan']['id']!=project or (job['prompt_id'],job['owner_id']) in known or job.get('exporting'):continue
        plan=job['plan'];sid=plan.get('runtime',{}).get('active_shot_id') or (plan.get('shots') or [{}])[0].get('id')
        found=next(((i+1,s) for i,s in enumerate(plan.get('shots',[])) if s['id']==sid),None)
        if not found:continue
        number,shot=found;rid='native:'+job['prompt_id']+':'+job['owner_id'];post=shot.get('post',{})
        items.append({'key':rid+':'+sid,'run_id':rid,'shot_id':sid,'name':shot.get('name') or sid,'number':number,'stages':['base']+(['hd'] if post.get('hd') else [])+(['face'] if post.get('face') else []),'status':job['status'],'active_stage':None,'origin':'native'})
    return items

def cancel_native(run_id,shot_id,confirm=False,expected=None):
    from .execution_state import native_jobs
    with LOCK:
        entry=next((j for j in native_jobs() if run_id=='native:'+j['prompt_id']+':'+j['owner_id']),None)
        if entry is None:raise ValueError('原生任务已结束或队列已变化，请刷新队列')
        managed=next((r for r in RUNS.values() if r.get('prompt_id')==entry['prompt_id'] and r['owner_id']==entry['owner_id'] and r['status']=='running'),None)
        if managed:
            if confirm:raise ValueError('任务已进入导演台执行阶段，请重新点击停止并核对队列')
            return cancel_item(managed['id'],shot_id)
        current=entry['plan'].get('runtime',{}).get('active_shot_id') or (entry['plan'].get('shots') or [{}])[0].get('id')
        if current!=shot_id:raise ValueError('队列已变化，请重新核对镜头')
        affected=[{'run_id':run_id,'shot_id':shot_id,'name':shot_id,'reason':'用户停止原生运行'}]
        if confirm:
            if expected is not None and expected!=[run_id+':'+shot_id]:raise ValueError('队列已变化，请重新核对')
            stop_prompt(entry['prompt_id'])
        return {'affected':affected,'confirmed':confirm,'stopping':entry['status']=='running'}
def folder(project=None):
    p=data_root()/'projects'/identifier(project)/'batches' if project else data_root()/'batches'
    if project:p.mkdir(parents=True,exist_ok=True)
    return p
def persist(run):
    p=folder(run['project_id'])/(run['id']+'.json');tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(run,ensure_ascii=False),encoding='utf-8');tmp.replace(p)
def queue_items(run):
    """Describe submitted work, never the editor's subsequently changed values."""
    tasks=[run,*sorted((r for r in RUNS.values() if r['project_id']==run['project_id'] and r['status']=='queued' and r['id']!=run['id']),key=lambda r:r['created_at'])]
    items=[]
    for task in tasks:
        if task['status'] not in ('queued','running'):continue
        shots={s['id']:(i+1,s) for i,s in enumerate(task['plan']['shots'])}
        remaining=task['shot_ids'][task['position']:]
        if task.get('stop_after') in remaining:remaining=remaining[:remaining.index(task['stop_after'])+1]
        for sid in remaining:
            stopping=sid in task.get('cancelled',{}) and task.get('active_shot_id')==sid and task['status']=='running'
            if sid in task.get('retain_ids',[]) or sid in task.get('cancelled',{}) and not stopping:continue
            number,shot=shots[sid];post=shot.get('post',{})
            process=task['scope']=='process' or task['scope']=='all' and sid in task.get('base_pins',{}) and (post.get('hd') or post.get('face'))
            stages=task.get('queue_stages',{}).get(sid) or ([] if process else ['base'])+(['hd'] if post.get('hd') else [])+(['face'] if post.get('face') else [])
            active=task['status']=='running' and task.get('active_shot_id')==sid and task.get('phase')!='done'
            items.append({'key':task['id']+':'+sid,'run_id':task['id'],'shot_id':sid,'name':shot.get('name') or sid,'number':number,'stages':stages,'status':'stopping' if stopping else 'running' if active else 'queued','active_stage':task.get('phase') if active else None})
    return items+native_queue_items(run['project_id'])

def public(run):
    value=copy.deepcopy({k:v for k,v in run.items() if k not in ('plan','requested_plan','prepared','owner_id','bridge_id','client_id','base_pins','reference_pins')})
    value['pending_runs']=[{'id':r['id'],'shot_ids':r['shot_ids'],'scope':r['scope']} for r in sorted(RUNS.values(),key=lambda r:r['created_at']) if r['project_id']==run['project_id'] and r['status']=='queued' and r['id']!=run['id']]
    value['queue_items']=queue_items(run)
    if run.get('nonce') and run.get('active_shot_id') and run['status']=='running':
        value['preview_node_id']=str(run['owner_id'])+'.director.'+run['nonce']+'.605'
    return value
def state(run_id):
    with LOCK:
        r=RUNS.get(run_id)
        if r:return public(r)
    name=identifier(run_id)+'.json';p=next(iter((data_root()/'projects').glob('*/batches/'+name)),folder()/name)
    if not p.is_file():raise ValueError('任务记录不存在')
    r=json.loads(p.read_text(encoding='utf-8'))
    if r['status'] in ('queued','running'):
        phase=r.get('phase');shot=r.get('active_shot_id');r.update(status='interrupted',interrupted_at=time.time(),last_phase=phase,last_shot_id=shot,message='上次服务进程中断，任务停在 '+str(shot or '排队')+' / '+str(phase or '等待')+'；成品与缓存保留，继续生成全部可补齐未完成镜头。');r['revision']+=1;persist(r)
    return public(r)
def latest(project):
    identifier(project)
    with LOCK:items=[r for r in RUNS.values() if r['project_id']==project]
    if items:
        running=[r for r in items if r['status']=='running'];queued=[r for r in items if r['status']=='queued']
        return public(min(running or queued,key=lambda r:r['created_at']) if running or queued else max(items,key=lambda r:r['created_at']))
    items=[]
    for p in [*folder(project).glob('*.json'),*folder().glob('*.json')]:
        try:
            r=json.loads(p.read_text(encoding='utf-8'))
            if r['project_id']==project:items.append(r)
        except (OSError,ValueError,KeyError):continue
    return state(max(items,key=lambda r:r['created_at'])['id']) if items else None
def update(run,**values):
    with LOCK:run.update(values);run['revision']+=1;persist(run)
def mark(plan,shot,phase,node_id=None):
    rid=plan.get('runtime',{}).get('batch_id')
    with LOCK:
        r=RUNS.get(rid)
        if r and r['active_shot_id']==shot:update(r,phase=phase)
    try:
        from server import PromptServer
        PromptServer.instance.send_sync('star7_director_stage',{'projectId':plan['id'],'shotId':shot,'nonce':plan.get('runtime',{}).get('request_nonce'),'phase':phase,'node_id':str(node_id),'batch_id':rid},plan.get('runtime',{}).get('client_id'))
    except (AttributeError,RuntimeError):pass
def approved_pin(plan,shot):
    rid=plan.get('runtime',{}).get('batch_id')
    with LOCK:
        r=RUNS.get(rid)
        if r and r['status']=='running' and r['active_shot_id']==shot and r['project_id']==plan['id'] and r.get('action')=='process':return copy.deepcopy(r['base_pins'].get(shot))
    return None

def approved_reference(plan,shot,source):
    """Only a live single-shot batch may use its selected finished artifact.

    This does not declare the old output up to date or relax base-cache checks.
    """
    runtime=plan.get('runtime',{})
    with LOCK:
        r=RUNS.get(runtime.get('batch_id'))
        if r and r['status']=='running' and r['scope'] in ('one','all','selected') and r['project_id']==plan['id'] and r['active_shot_id']==shot and r['nonce']==runtime.get('request_nonce'):
            return copy.deepcopy(r.get('reference_pins',{}).get(source))
    return None

def release_after_clip(plan,shot):
    """Let the native worker clear memory after execution, before its next job."""
    if plan.get('runtime',{}).get('intermediate_pass') or not plan.get('execution_options',{}).get('clear_vram_between_shots',False):return False
    runtime=plan.get('runtime',{})
    with LOCK:
        r=RUNS.get(runtime.get('batch_id'))
        if not r or r['status']!='running' or r['scope'] not in ('all','selected') or r['project_id']!=plan['id'] or r['active_shot_id']!=shot or r['nonce']!=runtime.get('request_nonce'):return False
        if r['position']>=len(r['shot_ids'])-1 or r['stop_after']==shot:return False
    from server import PromptServer
    queue=PromptServer.instance.prompt_queue
    queue.set_flag('unload_models',True)
    queue.set_flag('free_memory',True)
    return True
def control(run_id,target=None):
    with LOCK:
        r=RUNS.get(run_id)
        if not r or r['status'] not in ('queued','running'):raise ValueError('任务已结束')
        remaining=r['shot_ids'][r['position']:]
        if target is not None and target not in remaining:raise ValueError('请选择本次任务尚未完成的镜头，或正在生成的镜头')
        update(r,stop_after=target)
        return public(r)

def cancel_item(run_id,shot_id,confirm=False,expected=None):
    with LOCK:
        target=RUNS.get(run_id)
        if not target or target['status'] not in ('queued','running'):raise ValueError('任务已结束')
        if shot_id in target.get('retain_ids',[]) or shot_id not in target['shot_ids'][target['position']:]:raise ValueError('此镜头任务已结束')
        if shot_id in target.get('cancelled',{}):raise ValueError('此任务已取消')
        tasks=sorted((r for r in RUNS.values() if r['project_id']==target['project_id'] and r['status'] in ('queued','running')),key=lambda r:r['created_at'])
        store=Storage(data_root());available=set();blocked_ids=set();affected=[]
        for task in tasks:
            for shot in task['plan']['shots']:
                record=store.latest_output(task['project_id'],shot['id'])
                if record and Path(record['path']).is_file():available.add(shot['id'])
        for task in tasks:
            for sid in task['shot_ids'][task['position']:]:
                if sid in task.get('cancelled',{}) or sid in task.get('retain_ids',[]):continue
                chosen=task is target and sid==shot_id;source=dependency_source(task['plan'],sid)
                blocked=source in blocked_ids and source not in available
                if chosen or blocked:
                    affected.append({'run_id':task['id'],'shot_id':sid,'name':next(s.get('name') or sid for s in task['plan']['shots'] if s['id']==sid),'reason':'用户取消' if chosen else '前置镜头没有可用视频：'+source})
                    if sid not in available:blocked_ids.add(sid)
                else:available.add(sid)
        if confirm:
            keys=[i['run_id']+':'+i['shot_id'] for i in affected]
            if expected is not None and expected!=keys:raise ValueError('队列已变化，请重新点击取消，核对最新影响范围')
            for item in affected:
                task=RUNS[item['run_id']];task.setdefault('cancelled',{})[item['shot_id']]=item['reason']
                if task.get('stop_after')==item['shot_id']:task['stop_after']=None
                update(task)
            if target.get('active_shot_id')==shot_id and target['status']=='running' and target.get('prompt_id'):
                stop_prompt(target['prompt_id'])
            if tasks:update(tasks[0])
        return {'affected':affected,'confirmed':confirm,'stopping':target.get('active_shot_id')==shot_id and target['status']=='running','message':'停止／取消后保留已有视频；缺少前置视频的依赖任务一并取消，其他任务继续。'}
def next_seed(shot):
    value=shot.get('seed',0);mode=shot.get('seed_control','fixed')
    return (value+1)%(MAX_SEED+1) if mode=='increment' else (value-1)%(MAX_SEED+1) if mode=='decrement' else secrets.randbelow(MAX_SEED+1) if mode=='randomize' else value
def prompt_for(run,shot,action,first_pass=False):
    p=copy.deepcopy(run['prepared']['output']);plan=copy.deepcopy(run['plan']);nonce=uuid.uuid4().hex
    plan['runtime']={'scope':action,'active_shot_id':shot,'request_nonce':nonce,'batch_id':run['id'],'client_id':run['client_id']}
    if first_pass:
        next(s for s in plan['shots'] if s['id']==shot)['post']={'hd':False,'face':False}
        plan['runtime']['intermediate_pass']=True
    if run['scope'] in ('one','all','selected'):
        current=next(s for s in plan['shots'] if s['id']==shot)
        continuity=current.get('continuity',{})
        sid=continuity.get('source_shot') if current.get('input_mode','reference')=='reference' and continuity.get('mode','independent')!='independent' else None
        record=Storage(data_root()).latest_output(plan['id'],sid) if sid else None
        if record:
            run.setdefault('reference_pins',{})[sid]=copy.deepcopy(record)
            if not output_matches(plan,sid,p,record):
                run.setdefault('warnings',[]).append('参考 '+sid+' 最近已生成的视频；该镜头当前参数尚未更新到成品。')
    p[run['owner_id']]['inputs']['project_json']=json.dumps(plan,ensure_ascii=False)
    if p[run['owner_id']]['class_type']=='Star7DirectorDesk':
        link=p[run['owner_id']]['inputs'].get('asset_library');source=p.get(str(link[0])) if isinstance(link,list) else None
        if source and source['class_type']=='Star7DirectorLibrary':source['inputs']['library_json']=json.dumps({'assets':plan['assets'],'reference_size':plan.get('reference_size')},ensure_ascii=False)
    else:
        for spec in p.values():
            if spec['class_type'].startswith('Star7Director') and isinstance(spec.get('inputs',{}).get('shot_id'),str):spec['inputs']['shot_id']=shot
        if run.get('bridge_id'):p[run['bridge_id']]['inputs']['shot_id']=shot
    return p,nonce
async def enqueue(prompt,workflow,client_id,owner_id):
    from server import PromptServer
    import execution
    server=PromptServer.instance;pid=str(uuid.uuid4());server.node_replace_manager.apply_replacements(prompt)
    targets=[owner_id] if prompt[owner_id]['class_type']=='Star7DirectorDesk' else None
    valid=await execution.validate_prompt(pid,prompt,targets)
    if not valid[0]:raise ValueError('生成流程校验失败：'+str(valid[1]))
    number=server.number;server.number+=1
    extra={'client_id':client_id,'create_time':int(time.time()*1000),'extra_pnginfo':{'workflow':workflow}}
    server.prompt_queue.put((number,pid,prompt,extra,valid[2],{}));return pid
async def wait_job(pid):
    from server import PromptServer
    queue=PromptServer.instance.prompt_queue
    lost=0
    while True:
        history=queue.get_history(pid)
        if pid in history:
            h=history[pid]
            if h['status']['status_str']!='success':
                msg=next((m[1].get('exception_message') for m in h['status']['messages'] if m[0]=='execution_error'),None)
                raise ValueError(msg or '生成任务失败或被中断；已完成视频保留')
            return h
        running,pending=queue.get_current_queue()
        lost=0 if any(item[1]==pid for item in [*running,*pending]) else lost+1
        if lost>=4:raise ValueError('任务已从ComfyUI队列移除；已完成视频保留，可继续生成未完成镜头')
        await asyncio.sleep(.5)
async def execute(run):
    from .run_diagnostics import monitor
    stop_diagnostics=lambda:None
    store=Storage(data_root())
    try:
        previous=TASKS.get(run.get('predecessor_id'))
        if previous:await asyncio.shield(previous)
        elif run.get('predecessor_id'):
            while RUNS.get(run['predecessor_id'],{}).get('status') in ('queued','running'):await asyncio.sleep(.25)
        # Reconcile a queued continue-all with work completed while it waited.
        # Compare the submitted seed, before reserving the next regeneration seed.
        if run.get('predecessor_id') and run['scope']=='all':
            requested=run.get('requested_plan',run['plan'])
            for sid in run['shot_ids']:
                record=store.latest_output(run['project_id'],sid)
                if record and Path(record['path']).is_file() and parameter_matches(batch_plan(requested,sid,record),sid,run['prepared']['output'],record):
                    if sid not in run['retain_ids']:run['retain_ids'].append(sid)
                    run.get('seed_reservations',{}).pop(sid,None)
        update(run,status='running')
        stop_diagnostics=monitor(run,data_root())
        for index,sid in enumerate(run['shot_ids']):
            reason=run.get('cancelled',{}).get(sid);source=dependency_source(run['plan'],sid)
            if not reason and source and sid not in run.get('retain_ids',[]):
                predecessor=store.latest_output(run['project_id'],source)
                if not predecessor or not Path(predecessor['path']).is_file():reason='前置镜头没有可用视频：'+source
                else:
                    current=next(s for s in run['plan']['shots'] if s['id']==sid);cfg=current.get('continuity',{})
                    mode=('motion_guide' if current.get('keyframe_motion') else 'independent') if current.get('input_mode')=='keyframes' else cfg.get('mode');count=predecessor['frame_count']
                    if mode=='selected_frame' and cfg.get('frame',0)>=count:reason='前段视频不包含所选参考帧：'+source
                    if mode in ('previous_latent','motion_guide','motion_redraw') and count<cfg.get('context_frames',run['plan'].get('continuity_settings',{}).get('context_frames',22)):reason='前段视频长度不足所需上下文：'+source
            if reason:
                if run.get('stop_after')==sid:run['stop_after']=None
                run.setdefault('skipped',{})[sid]=reason;update(run,position=index+1,active_shot_id=None,message='跳过 '+sid+'：'+reason+'；继续检查后续镜头。');continue
            shot=next(s for s in run['plan']['shots'] if s['id']==sid);record=store.latest_output(run['project_id'],sid)
            if run['scope'] in ('all','process') and record and Path(record['path']).is_file():
                run['plan']=batch_plan(run['plan'],sid,record);shot=next(s for s in run['plan']['shots'] if s['id']==sid)
            if run['scope']=='all' and record and Path(record['path']).is_file() and sid in run.get('retain_ids',[]):
                # A prior clip is not a result of this run until explicitly retained.
                run['results'][sid]={'path':record['path'],'post':record.get('post'),'frames':record['frame_count']}
                run['retained']+=1;update(run,position=index+1,message='保留已有成品：'+sid)
            else:
                row,_=(Star7DirectorBaseCache().find_for_process if run['scope']=='process' else Star7DirectorBaseCache().find)(run['plan'],sid,run['prepared']['output'])
                post=shot.get('post',{});action='process' if run['scope']=='process' or run['scope']=='all' and row and (post.get('hd') or post.get('face')) else 'one' if run['scope'] in ('one','selected') else 'all'
                from .handoff import check_request
                check_request(run['plan'],sid,run['prepared']['output'],processing=action=='process')
                sampled=action!='process'
                run.setdefault('queue_stages',{})[sid]=([] if not sampled else ['base'])+(['hd'] if post.get('hd') else [])+(['face'] if post.get('face') else [])
                if action=='one' and (post.get('hd') or post.get('face')):
                    # Finish a playable fresh first pass before postprocessing it.
                    first,base_nonce=prompt_for(run,sid,'one',first_pass=True)
                    update(run,position=index,active_shot_id=sid,nonce=base_nonce,action='one',phase='base',message='重新生成一采：'+(shot.get('name') or sid))
                    base_pid=await enqueue(first,run['prepared'].get('workflow',{}),run['client_id'],run['owner_id']);update(run,prompt_id=base_pid)
                    if not await wait_owned(run,base_pid,sid):continue
                    base_record=store.latest_output(run['project_id'],sid)
                    if not base_record:raise ValueError('一采生成完成，但没有找到一采视频；后处理未启动')
                    run['results'][sid]={'path':base_record['path'],'post':base_record.get('post'),'frames':base_record['frame_count'],'prompt_id':base_pid,'nonce':base_nonce}
                    run['intermediate_nonce']=base_nonce
                    shot['next_seed']=next_seed(shot);run['seed_updates'][sid]={'shotId':sid,'seed':shot.get('seed',0),'nextSeed':shot['next_seed'],'seedControl':shot.get('seed_control','fixed')}
                    update(run,phase='decode',message='一采视频已保存，准备二采／人脸修复：'+sid)
                    row,_=(Star7DirectorBaseCache().find_for_process if run['scope']=='process' else Star7DirectorBaseCache().find)(run['plan'],sid,run['prepared']['output'])
                    if not row:raise ValueError('新一采视频已保留，但新一采缓存不可用；后处理未启动')
                    action='process'
                if action=='process' and not row:
                    run.setdefault('skipped',{})[sid]='一采缓存不可用，请重新生成当前镜头'
                    update(run,position=index+1,active_shot_id=None,message='跳过 '+sid+'：一采缓存不可用；继续后续任务。')
                    continue
                if action=='process':run['base_pins'][sid]=row
                prompt,nonce=prompt_for(run,sid,action)
                phase='hd' if action=='process' and post.get('hd') else 'face' if action=='process' and post.get('face') else 'base'
                update(run,position=index,active_shot_id=sid,nonce=nonce,action=action,phase=phase,message='处理 '+(shot.get('name') or sid)+'。'+' '.join(run.get('warnings',[])))
                pid=await enqueue(prompt,run['prepared'].get('workflow',{}),run['client_id'],run['owner_id']);update(run,prompt_id=pid)
                if not await wait_owned(run,pid,sid):continue
                record=store.latest_output(run['project_id'],sid)
                if record:
                    # Old files without provenance get a reliable base label only
                    # when their full first-pass fingerprint is verified.
                    run['results'][sid]={'path':record['path'],'post':record.get('post'),'frames':record['frame_count'],'prompt_id':pid,'nonce':nonce}
                if sampled and sid not in run['seed_updates']:
                    shot['next_seed']=next_seed(shot);run['seed_updates'][sid]={'shotId':sid,'seed':shot.get('seed',0),'nextSeed':shot['next_seed'],'seedControl':shot.get('seed_control','fixed')}
                run['completed']+=1;update(run,position=index+1,phase='done')
            if run['stop_after']==sid:
                update(run,status='stopped',active_shot_id=None,message='已在 '+sid+' 完成后停止；成品已保留。');return
        update(run,status='completed',active_shot_id=None,message=f"已更新 {run['completed']} 个镜头，保留 {run['retained']} 个未变化镜头。"+(f" 跳过／取消 {len(run['skipped'])} 个任务。" if run.get('skipped') else '')+' '.join(run.get('warnings',[])))
    except Exception as error:update(run,status='failed',active_shot_id=None,message=str(error),error=str(error))
    finally:stop_diagnostics()
async def start(body):
    from .execution_state import lease
    validate(body['plan'])
    with lease(body['plan']):return await _start(body)

async def _start(body):
    import folder_paths
    plan=copy.deepcopy(body['plan']);validate(plan);owner=str(body['owner_id']);prepared=copy.deepcopy(body['prepared']);scope=body.get('scope','all')
    if scope not in ('all','one','process','selected'):raise ValueError('不支持的生成范围')
    if owner not in prepared.get('output',{}) or prepared['output'][owner]['class_type']!='Star7DirectorDesk':raise ValueError('缺少导演台工作站节点')
    with LOCK:
        existing=[r for r in RUNS.values() if r['project_id']==plan['id'] and r['status'] in ('queued','running')]
    errors=preflight(plan,folder_paths.get_input_directory())
    if errors:raise ValueError('素材不可用：'+errors[0]['source'])
    requested=body.get('shot_ids',[])
    if scope=='selected' and (not isinstance(requested,list) or not requested or any(sid not in {s['id'] for s in plan['shots']} for sid in requested)):raise ValueError('请选择有效的镜头')
    shot_ids=[s['id'] for s in plan['shots'] if scope=='all' or scope=='selected' and s['id'] in requested or scope not in ('all','selected') and s['id']==body.get('shot_id')]
    if not shot_ids:raise ValueError('没有可生成镜头')
    if scope=='process' and not any(next(s for s in plan['shots'] if s['id']==shot_ids[0]).get('post',{}).get(k) for k in ('hd','face')):raise ValueError('请勾选二采或人脸修复')
    if scope in ('all','process'):
        store=Storage(data_root())
        for sid in shot_ids:
            record=store.latest_output(plan['id'],sid)
            if record and Path(record['path']).is_file():plan=batch_plan(plan,sid,record)
    if not existing:await validate_generation(plan,prepared,scope,shot_ids if scope=='selected' else body.get('shot_id'))
    pins={}
    for sid in shot_ids:
        row,_=(Star7DirectorBaseCache().find_for_process if scope=='process' else Star7DirectorBaseCache().find)(plan,sid,prepared['output'])
        if row:pins[sid]=row
        if scope=='process' and not row and not existing:raise ValueError('没有可用一采缓存，请重新生成当前镜头')
        if scope=='process' and not any(next(s for s in plan['shots'] if s['id']==sid).get('post',{}).get(k) for k in ('hd','face')):raise ValueError('请勾选二采或人脸修复')
    retain_ids=[]
    store=Storage(data_root())
    if scope=='all':
        retain_ids=[sid for sid in shot_ids if (record:=store.latest_output(plan['id'],sid)) and Path(record['path']).is_file() and parameter_matches(plan,sid,prepared['output'],record)]
    requested_plan=copy.deepcopy(plan)
    seed_reservations={}
    for sid in shot_ids:
        shot=next(s for s in plan['shots'] if s['id']==sid)
        if scope=='process' or sid in retain_ids:continue
        record=store.latest_output(plan['id'],sid)
        row=pins.get(sid);post=shot.get('post',{})
        if scope=='all' and row and (post.get('hd') or post.get('face')):continue
        previous=shot.get('seed',0)
        # A pending seed belongs to a completed local generation, never a fresh import.
        if record and Path(record['path']).is_file() and shot.get('seed_control','fixed')!='fixed' and isinstance(shot.get('next_seed'),int):
            shot['seed']=shot['next_seed']
        shot.pop('next_seed',None)
        if shot.get('seed',0)!=previous:
            seed_reservations[sid]={'shotId':sid,'previousSeed':previous,'seed':shot['seed']}
            pins.pop(sid,None)
    rid=uuid.uuid4().hex;r={'id':rid,'project_id':plan['id'],'created_at':time.time(),'revision':0,'status':'queued','scope':scope,'shot_ids':shot_ids,'position':0,'completed':0,'retained':0,'active_shot_id':None,'nonce':None,'phase':None,'action':None,'prompt_id':None,'stop_after':None,'message':'任务已交给服务端','results':{},'seed_updates':{},'plan':plan,'prepared':prepared,'owner_id':owner,'bridge_id':str(body['bridge_id']) if body.get('bridge_id') is not None else None,'client_id':body.get('client_id'),'base_pins':pins,'retain_ids':retain_ids,'seed_reservations':seed_reservations}
    r['requested_plan']=requested_plan
    with LOCK:
        existing=[v for v in RUNS.values() if v['project_id']==plan['id'] and v['status'] in ('queued','running')]
        if existing:
            predecessor=max(existing,key=lambda v:v['created_at']);r['predecessor_id']=predecessor['id'];r['message']='已排队：'+shot_ids[0]+'，等待已提交任务完成。'
            head=min(existing,key=lambda v:v['created_at']);update(head)
        RUNS[rid]=r;persist(r)
    TASKS[rid]=asyncio.create_task(execute(r));return public(r)
