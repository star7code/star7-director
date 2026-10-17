"""Shared cache leases and snapshots of the Desktop-owned native queue."""
import copy,json,sys,threading,uuid
from contextlib import contextmanager

LOCK=threading.RLock()
LEASES={}

@contextmanager
def lease(plan):
    token=uuid.uuid4().hex
    with LOCK:LEASES[token]=copy.deepcopy(plan)
    try:yield
    finally:
        with LOCK:LEASES.pop(token,None)

def native_jobs():
    server=sys.modules.get('server')
    instance=getattr(getattr(server,'PromptServer',None),'instance',None)
    queue=getattr(instance,'prompt_queue',None)
    if queue is None:return []
    running,pending=queue.get_current_queue();result=[]
    for status,entries in (('running',running),('queued',pending)):
        for item in entries:
            for owner,spec in item[2].items():
                if spec.get('class_type')!='Star7DirectorDesk':continue
                try:
                    plan=json.loads(spec['inputs']['project_json'])
                    exporting=plan.get('star7_action')=='export'
                    if exporting:plan=json.loads(plan['export_json'])['plan']
                    if not isinstance(plan.get('id'),str):continue
                except (ValueError,TypeError,KeyError):continue
                result.append({'prompt_id':item[1],'owner_id':str(owner),'status':status,'plan':plan,'client_id':item[3].get('client_id'),'exporting':exporting})
    return result

def live_plans():
    with LOCK:
        batch=sys.modules.get(__package__+'.batch_runner')
        plans=[r['plan'] for r in getattr(batch,'RUNS',{}).values() if r['status'] in ('queued','running')]
        return plans+list(LEASES.values())+[j['plan'] for j in native_jobs()]

def protected_projects(current):
    return {current,*[p['id'] for p in live_plans()]}
