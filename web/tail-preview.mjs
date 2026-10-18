// Video-version checks are lightweight; only a changed version reloads pixels.
export function createTailPreview({getTarget,fetchRevision,onChange}){
 const versions=new Map(),pending=new Map();
 const key=t=>JSON.stringify([t.projectId,t.shotId]);
 function url(target){return target?'/star7/director/tail-image/'+encodeURIComponent(target.projectId)+'/'+encodeURIComponent(target.shotId)+'?full=1&v='+encodeURIComponent(versions.get(key(target))??'initial'):null}
 async function check(){
  const target=getTarget();if(!target)return;
  const id=key(target);if(pending.has(id))return pending.get(id);
  const work=(async()=>{try{
   const revision=await fetchRevision(target),value=revision??'missing';
   if(versions.get(id)!==value){versions.set(id,value);const active=getTarget();if(active&&key(active)===id)onChange()}
  }catch{/* Keep the last usable preview during transient connection errors. */}})();
  pending.set(id,work);try{await work}finally{if(pending.get(id)===work)pending.delete(id)}
 }
 return {url,check};
}
