// Recovery is display-only. It never submits, resumes or changes a GPU job.
export function createPreviewRecovery({getActive,fetchLatest,onPreview,interval=1000}){
 let timer=null,disposed=false,busy=false,lastNode=null,lastSignature=null,lastPush=0,epoch=0;
 const nodeOf=r=>r?.previewNodeId;
 async function recover(){
  if(disposed||busy)return;
  const active=getActive(),id=nodeOf(active);
  if(!id||active.phase!=='base')return;
  if(lastNode===id&&Date.now()-lastPush<1500)return;
  busy=true;const version=epoch;
  try{
   const payload=await fetchLatest(id),current=getActive();
   if(disposed||version!==epoch||!payload||nodeOf(current)!==id||current?.nonce!==active.nonce||current.phase!=='base'||String(payload.node_id)!==id)return;
   const signature=JSON.stringify([payload.run_id,payload.step,payload.status,payload.image]);
   if(lastNode!==id||signature!==lastSignature){lastNode=id;lastSignature=signature;onPreview(payload,current)}
  }catch{/* A temporary disconnect leaves the last frame visible. */}
  finally{busy=false}
 }
 timer=setInterval(recover,interval);
 return {recover,reset(){epoch++;lastNode=null;lastSignature=null;lastPush=0},pushed(id){lastNode=id;lastPush=Date.now()},dispose(){disposed=true;clearInterval(timer)}};
}
