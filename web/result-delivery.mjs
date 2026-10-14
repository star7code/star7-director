// Retry transient reads; a newer result always supersedes an older response.
export function createResultDelivery({getProjectId,fetchResult,onResult,interval=1000}){
 const pending=new Map(),latest=new Map(),done=new Set();let disposed=false,epoch=0;
 const shotKey=r=>r.project_id+':'+r.sid;
 async function attempt(item){
  if(disposed||item.busy)return;const key=shotKey(item);
  if(getProjectId()!==item.project_id||latest.get(key)?.key!==item.key){pending.delete(item.key);return}
  item.busy=true;
  try{const data=await fetchResult(item.run,item.sid,item.result);
   if(disposed||item.epoch!==epoch)return;
   if(latest.get(key)?.key!==item.key||getProjectId()!==item.project_id){pending.delete(item.key);return}
   if(!data)return;
   if(!data.obsolete)onResult(data,item.run,item.sid,item.result);
   done.add(item.key);pending.delete(item.key);
  }catch{/* Keep pending until a successful read or a newer result. */}
  finally{item.busy=false}
 }
 function offer(run){if(run.project_id!==getProjectId())return;for(const [sid,result] of Object.entries(run.results||{})){
  // A clip without a prompt ID is an existing output copied into the task,
  // including on older servers. The shot selector loads it separately.
  if(!result.prompt_id)continue;
  const key=run.id+':'+sid+':'+result.path,item={key,sid,result,run,project_id:run.project_id,busy:false,epoch},old=latest.get(shotKey(item)),time=run.created_at||0;
  if(old&&(old.time>time||old.time===time&&old.revision>(run.revision||0)))continue;
  latest.set(shotKey(item),{key,time,revision:run.revision||0});if(done.has(key)||pending.has(key))continue;pending.set(key,item);attempt(item);
 }}
 const timer=setInterval(()=>{for(const item of pending.values())attempt(item)},interval);
 return {offer,reset(){epoch++;pending.clear();latest.clear();done.clear()},retry(){return Promise.all([...pending.values()].map(attempt))},dispose(){disposed=true;clearInterval(timer);pending.clear()}};
}
