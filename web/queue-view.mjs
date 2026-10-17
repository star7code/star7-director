// Queue order and stages come from submitted server tasks, not current controls.
export function mountQueueView({getProjectId}){
 const $=id=>document.getElementById(id),dialog=$('queue-dialog'),list=$('queue-list'),summary=$('queue-summary');
 const labels={base:'一采',hd:'二采',face:'人脸修复'};
 let items=[],project=null,pendingCancel=null;
 async function cancelRequest(item,confirm=false){
  const runId=item.run_id||item.key.split(':')[0];
  const response=await fetch('/star7/director/batch/'+encodeURIComponent(runId)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shot_id:item.shot_id,confirm,expected:confirm?item.expected:undefined})});
  const data=await response.json();if(!response.ok)throw Error(data.error||'取消失败');return data;
 }
 async function askCancel(item){
  try{const data=await cancelRequest(item);pendingCancel={...item,expected:data.affected.map(i=>i.run_id+':'+i.shot_id)};$('queue-cancel-summary').textContent=data.affected.length>1?'这些依赖任务没有可用的前段视频，也将一并取消；后面的独立任务继续。':'取消这个排队任务；已有视频和其他可执行任务保留。';
   if(data.stopping)$('queue-cancel-summary').textContent='停止当前正在执行的镜头；已完成的视频与缓存保留，其他可执行任务继续。';
   $('queue-cancel-affected').replaceChildren(...data.affected.map(item=>{const row=document.createElement('li');row.textContent=item.name+' · '+item.reason;return row}));$('queue-cancel-dialog').showModal();
  }catch(error){summary.textContent=error.message}
 }
 $('queue-cancel-back').onclick=()=>{$('queue-cancel-dialog').close();pendingCancel=null};
 $('queue-cancel-confirm').onclick=async()=>{if(!pendingCancel)return;const button=$('queue-cancel-confirm');button.disabled=true;try{const data=await cancelRequest(pendingCancel,true);const removed=new Set(data.affected.map(i=>i.run_id+':'+i.shot_id));items=items.flatMap(i=>!removed.has(i.key)?[i]:data.stopping&&i.key===pendingCancel.key?[{...i,status:'stopping'}]:[]);draw();$('queue-cancel-dialog').close();pendingCancel=null;parent.postMessage({type:'star7-director-queue-request',projectId:project},location.origin)}catch(error){$('queue-cancel-summary').textContent=error.message}finally{button.disabled=false}};
 function draw(){
  list.replaceChildren();
  summary.textContent=items.length?`共 ${items.length} 个镜头任务 · 按下列顺序执行`:'当前没有正在生成或等待中的镜头。';
  for(const [index,item] of items.entries()){
   const row=document.createElement('li');row.className='queue-row'+(item.status==='running'?' running':'');
   const order=document.createElement('span');order.className='queue-order';order.textContent=String(index+1).padStart(2,'0');
   const detail=document.createElement('div');detail.className='queue-detail';
   const title=document.createElement('b');title.textContent=`镜头 ${String(item.number).padStart(2,'0')} · ${item.name}`;
   const stages=document.createElement('div');stages.className='queue-stages';
   for(const stage of item.stages){const chip=document.createElement('span');chip.className='queue-stage';chip.textContent=labels[stage]||stage;if(item.status==='running'&&item.active_stage===stage){chip.classList.add('active');chip.textContent+=' · 进行中'}stages.append(chip)}
   detail.append(title,stages);const state=document.createElement('small');state.className='queue-state';state.textContent=item.status==='running'?'正在执行':item.status==='stopping'?'正在停止':'等待中';row.append(order,detail,state);
   {const cancel=document.createElement('button');cancel.type='button';cancel.className='queue-cancel-item';cancel.textContent=item.status==='running'?'停止':item.status==='stopping'?'停止中':'取消';cancel.disabled=item.status==='stopping';cancel.title=item.status==='running'?'立即停止当前镜头任务':'取消尚未开始的镜头任务';cancel.onclick=()=>askCancel(item);row.append(cancel)}list.append(row);
  }
 }
 $('view-queue').onclick=()=>{if(project!==getProjectId()){items=[];project=getProjectId()}draw();dialog.showModal();summary.textContent='正在核对后台队列…';parent.postMessage({type:'star7-director-queue-request',projectId:project},location.origin)};
 $('queue-close').onclick=()=>dialog.close();
 window.addEventListener('message',e=>{
  if(e.origin!==location.origin||e.source!==parent)return;
  const data=e.data;
  if(data?.type==='star7-director-open'){items=[];project=null;if(dialog.open)draw();return}
  if(!['star7-director-batch-state','star7-director-queue'].includes(data?.type)||data.transition_only)return;
  if((data.project_id||data.projectId)!==getProjectId())return;
  project=getProjectId();
  if(data.error){summary.textContent='无法读取后台队列：'+data.error;return}
  if(data.type==='star7-director-batch-state'&&['running','queued'].includes(data.status)&&!Array.isArray(data.queue_items)){
   items=[];list.replaceChildren();summary.textContent='任务正在运行。队列详情需在任务结束后，通过 Comfy Desktop 重启服务以加载新版。';return;
  }
  items=data.queue_items||[];draw();
 });
}
