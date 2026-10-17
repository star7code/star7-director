"""Observe native Run jobs through the same Director state and seed protocol."""
import copy,time,uuid
from contextlib import contextmanager
from .execution_state import LOCK,native_jobs

def notify(run):
    from .batch_runner import public
    try:
        from server import PromptServer
        with LOCK:payload={'owner_id':run['owner_id'],'run':public(run)}
        PromptServer.instance.send_sync('star7_director_run',payload,run.get('client_id'))
    except (AttributeError,RuntimeError):pass

@contextmanager
def execution(plan,prompt,owner):
    from . import batch_runner as b
    plan=copy.deepcopy(plan);runtime=plan.get('runtime',{});sid=runtime.get('active_shot_id') or (plan['shots'][0]['id'] if plan['shots'] else None)
    with LOCK:
        batch=b.RUNS.get(runtime.get('batch_id'))
        managed=bool(batch and batch['status']=='running' and batch['project_id']==plan['id'] and batch.get('active_shot_id')==sid and batch.get('nonce')==runtime.get('request_nonce') and str(batch['owner_id'])==str(owner))
    if managed:
        yield plan
        return
    # Serialized runtime is editor state, never authority to repeat a previous
    # process-only/batch request. Native Run always generates the selected shot.
    nonce=uuid.uuid4().hex;plan['runtime']={'scope':'one','active_shot_id':sid,'request_nonce':nonce}
    job=next((j for j in native_jobs() if j['status']=='running' and j['owner_id']==str(owner) and j['plan']['id']==plan['id']),None)
    if job is None:
        yield plan
        return
    store=b.Storage(b.data_root());shot=next((s for s in plan['shots'] if s['id']==sid),None)
    if shot is None:raise ValueError('请选择有效镜头后再运行')
    reservations={};previous=shot.get('seed',0)
    if store.latest_output(plan['id'],sid) and shot.get('seed_control','fixed')!='fixed' and type(shot.get('next_seed')) is int:shot['seed']=shot['next_seed']
    shot.pop('next_seed',None)
    if shot.get('seed',0)!=previous:reservations[sid]={'shotId':sid,'previousSeed':previous,'seed':shot['seed']}
    rid=uuid.uuid4().hex
    plan['runtime'].update(batch_id=rid,client_id=job.get('client_id'))
    run={'id':rid,'project_id':plan['id'],'created_at':time.time(),'revision':0,'status':'running','scope':'one','origin':'native','shot_ids':[sid],'position':0,'completed':0,'retained':0,'active_shot_id':sid,'nonce':nonce,'phase':'base','action':'one','prompt_id':job['prompt_id'],'stop_after':None,'message':'原生运行：生成当前选中镜头 '+sid,'results':{},'seed_updates':{},'seed_reservations':reservations,'plan':plan,'prepared':{'output':prompt or {}},'owner_id':str(owner),'client_id':job.get('client_id'),'base_pins':{},'retain_ids':[]}
    from .core import dependency_source
    source=dependency_source(plan,sid)
    if source and (record:=store.latest_output(plan['id'],source)):run['reference_pins']={source:record}
    with LOCK:b.RUNS[rid]=run;b.update(run)
    notify(run)
    try:
        yield plan
    except BaseException as error:
        from comfy.model_management import InterruptProcessingException
        stopped=isinstance(error,InterruptProcessingException) or sid in run.get('cancelled',{})
        b.update(run,status='stopped' if stopped else 'failed',active_shot_id=None,phase=None,message='已停止当前镜头；已有视频和缓存保留。' if stopped else str(error),error=None if stopped else str(error))
        raise
    else:
        record=store.latest_output(plan['id'],sid)
        if record:run['results'][sid]={'path':record['path'],'post':record.get('post'),'frames':record['frame_count'],'prompt_id':job['prompt_id'],'nonce':nonce}
        run['seed_updates'][sid]={'shotId':sid,'seed':shot.get('seed',0),'nextSeed':b.next_seed(shot),'seedControl':shot.get('seed_control','fixed')}
        b.update(run,status='completed',position=1,completed=1,active_shot_id=None,phase='done',message='当前镜头已完成：'+sid)
    finally:notify(run)
