import {createResultDelivery} from './result-delivery.mjs?v=20261014-fresh-base1';
import {createPreviewRecovery} from './preview-recovery.mjs?v=20261014-queue-changes1';
import {createBatchClient} from './batch-client.mjs?v=20261014-lifecycle2';
import {app} from '../../scripts/app.js';
import {api} from '../../scripts/api.js';
import {messageData} from './message-data.mjs?v=20261014-queue-changes1';
const PARAMETERS=new Set(['MiniMaxH3ChunkEnhancedLoaderStar7','CLIPLoader','VAELoader','LoraLoaderModelOnly','MiniMaxH3SigmaShift','MiniMaxH3ActivationChunkStar7','Star7VedaSparseAttention','KSamplerSelect','BasicScheduler','MiniMaxH3OneClickHDStar7','MiniMaxH3FaceRefineLatentStar7']);
// A closed tab is not a reusable workflow handle. Give each project read its
// own snapshot; never retain frontend workflow objects across tab deletion.
async function loadProjectWorkflow(item){const snapshot=structuredClone(item.workflow);snapshot.id=crypto.randomUUID();await app.loadGraphData(snapshot,true,false,'Star7-'+item.plan.id+'.json');}
async function jsonRequest(url,body){const response=await api.fetchApi(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.error||'请求失败');return value}
function fields(graph){return graph._nodes.filter(n=>PARAMETERS.has(n.comfyClass)).flatMap(n=>(n.widgets||[]).filter(w=>['combo','number','toggle'].includes(w.type)&&!n.inputs?.some(i=>i.widget?.name===w.name&&i.link!=null)).map(w=>({nodeId:n.id,classType:n.comfyClass,name:w.name,label:(n.title||n.comfyClass)+' · '+w.name,value:w.value,choices:Array.isArray(w.options?.values)?w.options.values:null})));}
async function waitPrompt(id){
 const deadline=Date.now()+24*60*60*1000;
 while(Date.now()<deadline){
  const response=await api.fetchApi('/history/'+encodeURIComponent(id));if(!response.ok)throw Error('无法读取任务结果，请检查连接后继续生成。');
  const history=await response.json();const record=history[id];
  if(record){if(record.status?.status_str==='error'){const message=record.status.messages?.find(m=>m[0]==='execution_error')?.[1];throw Error(message?.exception_message||'镜头执行失败，请查看 ComfyUI 日志')}if(record.status?.completed)return record}
  await new Promise(resolve=>setTimeout(resolve,2000));
 }
 throw Error('任务等待超时，请检查 ComfyUI 状态。');
}

function linkedLibrary(owner){const input=owner.inputs?.find(i=>i.name==='asset_library');const link=input?.link!=null?owner.graph.links[input.link]:null;return link?owner.graph.getNodeById(link.origin_id):null}
function readLibrary(owner){const library=linkedLibrary(owner);const value=library?.widgets?.find(w=>w.name==='library_json')?.value;return value?JSON.parse(value).assets:null}
function readReferenceSize(owner){const library=linkedLibrary(owner),value=library?.widgets?.find(w=>w.name==='library_json')?.value;return value?(JSON.parse(value).reference_size||{mode:'long_edge',image_long_edge:1600,video_long_edge:800,image_mp:1.5,video_mp:0.5}):undefined}
function withLibrary(owner,plan){const assets=readLibrary(owner);return assets===null?plan:{...plan,assets,reference_size:readReferenceSize(owner)}}
function hideJSON(owner,name){const w=owner.widgets?.find(w=>w.name===name);if(w){w.hidden=true;w.type='hidden';w.computeSize=()=>[0,0];for(const el of [w.element,w.inputEl])if(el?.style)el.style.display='none'}return w}
function mount(owner,libraryMode=false,dialog=null){
 if(!owner.graph||owner.graph.getNodeById(owner.id)!==owner)return;
 if(owner._directorMount)return;
 const labels={model:'模型',clip:'文本编码器',video_vae:'视频 VAE',audio_vae:'音频 VAE',asset_library:'项目素材库'};for(const input of owner.inputs||[])if(labels[input.name])input.label=labels[input.name];
 const downloadVideo=(url,name)=>{const a=document.createElement('a');a.href=url+(url.includes('?')?'&':'?')+new URLSearchParams({name});a.download=name;a.click()};
 const graph=owner.graph,isDesk=owner.comfyClass==='Star7DirectorDesk';let disposed=false,reloadVersion=0,dom=null;
 const attached=()=>!disposed&&owner.graph===graph&&graph.getNodeById(owner.id)===owner;
 const frame=document.createElement('iframe');frame.src=new URL('./index.html?v=20261019-model-backend1&mode='+(libraryMode?'library':isDesk?'desk':'legacy'),import.meta.url).href;frame.style.cssText='display:block;width:100%;height:100%;border:0;min-width:0;border-radius:10px;background:#111317';
 const host=document.createElement('div');host.style.cssText='width:100%;height:100%;min-width:0;overflow:hidden;pointer-events:auto;';host.append(frame);
 const widget=hideJSON(owner,libraryMode?'library_json':'project_json');let running=false,stop=false,livePlan=null,activeRun=null,executingOwner=false,exporting=false,serverOwned=false,batchRunId=null;const revisions=new Map();const seenSeeds=new Map(),progressSignatures=new Map();let projectSaveChain=Promise.resolve();
 const send=(type,extra)=>{if(attached())frame.contentWindow?.postMessage(messageData({type,...extra}),location.origin)};
 const progress=(message,busy=false,error=false)=>send('star7-director-progress',{message,busy,error});
 const prepare=async()=>{const prepared=await app.graphToPrompt(graph);if(isDesk){const output=prepared.output,keep=new Set();const visit=id=>{id=String(id);if(keep.has(id)||!output[id])return;keep.add(id);for(const value of Object.values(output[id].inputs||{}))if(Array.isArray(value)&&value.length===2&&typeof value[0]==='string'&&typeof value[1]==='number')visit(value[0])};visit(owner.id);prepared.output=Object.fromEntries(Object.entries(output).filter(([id])=>keep.has(id)))}return prepared};
 const syncLibrary=plan=>{const library=linkedLibrary(owner);const field=library?.widgets?.find(w=>w.name==='library_json');if(field){field.value=JSON.stringify({...JSON.parse(field.value),assets:plan.assets,reference_size:plan.reference_size||JSON.parse(field.value).reference_size});library.setDirtyCanvas(true,true);library._directorReload?.()}};
 const previewRecovery=createPreviewRecovery({getActive:()=>activeRun,fetchLatest:async id=>{const response=await api.fetchApi('/star7/director/h3-preview/latest?node_id='+encodeURIComponent(id));return response.ok?response.json():null},onPreview:(data,run)=>send('star7-director-live-preview',{...data,projectId:run.projectId,shotId:run.shotId})});
 const resultDelivery=createResultDelivery({getProjectId:()=>(livePlan||JSON.parse(widget.value)).id,fetchResult:async(r,sid,result)=>{const filename=result.path.split(/[\\/]/).pop();const response=await api.fetchApi('/star7/director/result/'+encodeURIComponent(r.project_id)+'/'+encodeURIComponent(sid)+'?'+new URLSearchParams({run_id:r.id,filename}));if(response.status===400)return {obsolete:true};if(!response.ok)throw Error('结果读取失败');return response.json()},onResult:(info,r,sid,result)=>{if(activeRun?.shotId===sid&&result.nonce&&activeRun.nonce!==result.nonce&&result.nonce!==r.intermediate_nonce)return;send('star7-director-result',{...info,nonce:result.nonce,keep_live:activeRun?.shotId===sid&&activeRun.nonce!==result.nonce,projectId:r.project_id,shotId:sid})}});
 const applyBatchState=r=>{
  if(!attached()||!r)return;if(r.revision<=(revisions.get(r.id)??-1)){resultDelivery.offer(r);return;}revisions.set(r.id,r.revision);if(!r.transition_only)batchRunId=r.id;const value=livePlan||JSON.parse(widget.value);if(value.id!==r.project_id)return;
  const busy=r.transition_only?running:['queued','running'].includes(r.status);if(!r.transition_only){serverOwned=busy;running=busy;livePlan=value;
  send('star7-director-run-snapshot',{projectId:r.project_id,shotIds:busy?[...r.shot_ids.slice(r.position),...(r.pending_runs||[]).flatMap(p=>p.shot_ids)]:[]});
  send('star7-director-batch-state',{...r});
  if(r.active_shot_id&&r.phase!=='done'){
   const next={projectId:r.project_id,shotId:r.active_shot_id,nonce:r.nonce,phase:r.phase,previewNodeId:r.preview_node_id||String(owner.id)+'.director.'+r.nonce+'.605'};
   if(activeRun?.nonce!==next.nonce)send('star7-director-preview-start',next);
   activeRun=next;send('star7-director-phase',next);previewRecovery.recover();
  }else if(activeRun){send('star7-director-preview-end',{...activeRun,status:r.status});activeRun=null}
  }
  resultDelivery.offer(r);
  for(const item of Object.values(r.seed_reservations||{})){const key=r.id+':start:'+item.shotId;if(seenSeeds.has(key))continue;seenSeeds.set(key,JSON.stringify(item));const shot=value.shots.find(s=>s.id===item.shotId);if(shot?.seed===item.previousSeed){shot.seed=item.seed;delete shot.next_seed;send('star7-director-seed-state',{shotId:shot.id,seed:shot.seed})}}
  for(const item of Object.values(r.seed_updates||{})){const key=r.id+':'+item.shotId,signature=JSON.stringify(item);if(seenSeeds.get(key)===signature)continue;seenSeeds.set(key,signature);const current=value.shots.find(s=>s.id===item.shotId);if(current&&current.seed===item.seed&&(current.seed_control||'fixed')===item.seedControl){current.next_seed=item.nextSeed;send('star7-director-seed-state',item)}}
  widget.value=JSON.stringify(value);owner.setDirtyCanvas(true,true);
  const signature=JSON.stringify([r.message,busy]);if(!r.transition_only&&progressSignatures.get(r.id)!==signature){progressSignatures.set(r.id,signature);progress(r.message,busy,['failed','interrupted'].includes(r.status))}
  if(!busy&&!r.transition_only)livePlan=null;
 };
 const batch=createBatchClient({startRequest:body=>jsonRequest('/star7/director/batch/start',body),fetchState:async id=>{const r=await api.fetchApi('/star7/director/batch/'+id);if(!r.ok)throw Error('无法读取后台任务状态');return r.json()},fetchProject:async id=>(await (await api.fetchApi('/star7/director/batch/project/'+encodeURIComponent(id))).json()).run,controlRequest:(id,target)=>jsonRequest('/star7/director/batch/'+id+'/control',{stop_after:target}),onState:applyBatchState,onQueued:r=>{const item=r.seed_reservation;if(item){const value=livePlan||JSON.parse(widget.value),shot=value.shots.find(s=>s.id===item.shotId);if(shot?.seed===item.previousSeed){shot.seed=item.seed;delete shot.next_seed;widget.value=JSON.stringify(value);send('star7-director-seed-state',{shotId:shot.id,seed:shot.seed})}}progress(r.message,true)},onError:e=>progress('与 ComfyUI 服务失去连接，无法确认任务是否仍在运行。恢复连接后将重新检查进度。'+e.message,true,true)});
 const listener=async e=>{
  if(!attached()||app.graph!==graph||e.origin!==location.origin||e.source!==frame.contentWindow)return;
  const data=e.data;
  if(data?.type==='star7-director-queue-request'){
   const current=livePlan||JSON.parse(widget.value);if(data.projectId!==current.id)return;
   try{const response=await api.fetchApi('/star7/director/batch/project/'+encodeURIComponent(current.id));if(!response.ok)throw Error('服务返回 '+response.status);const result=await response.json();if(result.run&&['running','queued'].includes(result.run.status)&&!Array.isArray(result.run.queue_items))throw Error('任务仍在运行；队列详情需在任务结束后重启桌面版服务以加载新版。');send('star7-director-queue',{projectId:current.id,queue_items:result.run?.queue_items||result.native_queue_items||[]})}catch(error){send('star7-director-queue',{projectId:current.id,error:error.message})}return;
  }
  if(data?.type==='star7-director-local-project'){
   const graphSnapshot=['save','clone','new'].includes(data.action)?graph.serialize():null;
   const work=async()=>{if(!attached())return;try{
    if(['new','read','activate'].includes(data.action)&&running)throw Error('生成或排队完成后再切换项目。');
    if(data.action==='list'){const result=await (await api.fetchApi('/star7/director/local-projects')).json();send('star7-director-project-reply',{requestId:data.requestId,result});return}
    if(data.action==='export'){
     if(running)throw Error('生成或排队完成后再导出项目包。');
     const item=await jsonRequest('/star7/director/local-projects/read',{id:data.body.id});
     if(!item.workflow?.nodes?.length)throw Error('此项目缺少保存的工作流，请读取后保存一次再导出。');
     const response=await api.fetchApi('/star7/director/package/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:item.plan,workflow:item.workflow})});
     if(!response.ok)throw Error((await response.json()).error);
     if(!attached())return;
     const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=(item.plan.title||item.plan.id)+'.star7.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
     send('star7-director-project-reply',{requestId:data.requestId,result:{message:'项目包已导出，包含工作流、设置和素材。'}});return;
    }
    if(data.action==='activate'){
     send('star7-director-project-reply',{requestId:data.requestId,result:{ok:true}});
     if(data.item.workflow?.nodes?.length)await loadProjectWorkflow(data.item);
     else{widget.value=JSON.stringify(data.item.plan);syncLibrary(data.item.plan);livePlan=null;await reload()}
     return;
    }
    const value={...data.body};if(value.plan&&value.plan.id===JSON.parse(widget.value).id)value.plan=withLibrary(owner,value.plan);
    if(['save','clone','new'].includes(data.action)&&!value.workflow)value.workflow=graphSnapshot;
    const result=await jsonRequest('/star7/director/local-projects/'+data.action,value);
    if(!attached())return;
    if(data.action==='save'&&result.media_map&&Object.keys(result.media_map).length){
     const current=livePlan||JSON.parse(widget.value);
     const remap=v=>{if(Array.isArray(v))v.forEach(remap);else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(['source','thumbnail_source'].includes(k)&&result.media_map[x])v[k]=result.media_map[x];else remap(x)}};
     if(current.id===result.plan.id){remap(current);current.media_aliases={...current.media_aliases,...result.plan.media_aliases};widget.value=JSON.stringify(current);syncLibrary(current);send('star7-director-project-media',{projectId:current.id,map:result.media_map,aliases:current.media_aliases})}
    }
    send('star7-director-project-reply',{requestId:data.requestId,result});
   }catch(error){send('star7-director-project-reply',{requestId:data.requestId,error:error.message})}};
   projectSaveChain=projectSaveChain.then(work,work);return;
  }
  if(data?.type==='star7-director-plan'){
   if(running&&!libraryMode){livePlan=JSON.parse(JSON.stringify(data.plan));widget.value=JSON.stringify(livePlan);owner.setDirtyCanvas(true,true);return}
   if(libraryMode){widget.value=JSON.stringify({name:data.plan.library_name||'素材库',sequences:data.plan.asset_sequences,reference_size:data.plan.reference_size,assets:data.plan.assets});for(const n of graph._nodes)if(linkedLibrary(n)===owner)n._directorLibraryChanged?.()}
   else{widget.value=JSON.stringify(data.plan);syncLibrary(data.plan)}owner.setDirtyCanvas(true,true);return;
  }
  if(data?.type==='star7-director-get-result'){try{const r=await api.fetchApi('/star7/director/result/'+encodeURIComponent(data.projectId)+'/'+encodeURIComponent(data.shotId));send('star7-director-result',{projectId:data.projectId,shotId:data.shotId,requestId:data.requestId,...(r.ok?await r.json():{url:null})})}catch{send('star7-director-result',{projectId:data.projectId,shotId:data.shotId,requestId:data.requestId,url:null})}return}
  if(data?.type==='star7-director-validate'){try{const plan=withLibrary(owner,data.plan),prepared=await prepare();const states=await jsonRequest('/star7/director/status',{plan,prompt:prepared.output});send('star7-director-shot-states',{projectId:plan.id,revision:data.revision,states});const result=await jsonRequest('/star7/director/validate-generation',{plan,prepared});send('star7-director-progress',{message:result.message,busy:running,error:false,revision:data.revision})}catch(error){send('star7-director-progress',{message:'校验未通过：'+error.message,busy:running,error:true,revision:data.revision})}return}
  if(data?.type==='star7-director-check-process'){
   try{const plan=withLibrary(owner,data.plan),prepared=await prepare();const states=await jsonRequest('/star7/director/status',{plan,prompt:prepared.output});const state=states[data.shotId],shot=plan.shots.find(s=>s.id===data.shotId);send('star7-director-process-ready',{requestId:data.requestId,states,ready:!!(state?.process_available??state?.base_available)&&!!(shot?.post?.hd||shot?.post?.face),exportReady:!!state?.has_output,complete:!!state?.complete,stale:state?.parameters_changed??(!!state?.has_output&&!state?.complete),preservesPost:!!state?.preserves_post,reason:state?.process_reason||state?.base_reason})}catch(error){send('star7-director-process-ready',{requestId:data.requestId,ready:false,reason:error.message})}return;
  }
  if(data?.type==='star7-director-cache-context'){
   const sources=[];const scan=value=>{if(!value||typeof value!=='object')return;for(const [key,item] of Object.entries(value)){if(['source','thumbnail_source'].includes(key)&&typeof item==='string')sources.push(item);else scan(item)}};
   for(const n of graph._nodes)for(const w of n.widgets||[])if(['library_json','project_json'].includes(w.name)){try{scan(JSON.parse(w.value))}catch{}}
   send('star7-director-cache-context',{sources:[...new Set(sources)],requestId:data.requestId});return;
  }
  if(data?.type==='star7-director-refresh-fields'&&!libraryMode){try{const internals=isDesk?await (await api.fetchApi('/star7/director/generation-fields')).json():[];const value=JSON.parse(widget.value);for(const f of internals)if(value.generation?.[f.nodeId]?.[f.name]!==undefined)f.value=value.generation[f.nodeId][f.name];send('star7-director-fields',{fields:[...internals,...fields(graph)]})}catch(error){progress(error.message,running,true)}return}
  if(data?.type==='star7-director-stop'){try{await batch.stopAfter(data.cancel?null:data.shotId)}catch(error){progress(error.message,running,true)}return}
  if(data?.type==='star7-director-select'&&isDesk){const value=livePlan||JSON.parse(widget.value);if(value.shots.some(s=>s.id===data.shotId)){value.runtime={...value.runtime,active_shot_id:data.shotId};widget.value=JSON.stringify(value);owner.setDirtyCanvas(true,true)}return}
  if(data?.type==='star7-director-select'&&!running&&!isDesk&&!libraryMode){const bridge=graph._nodes.find(n=>n.comfyClass==='Star7DirectorConditioning');const selected=bridge?.widgets.find(w=>w.name==='shot_id');if(selected)selected.value=data.shotId;return}
  if(data?.type==='star7-director-parameter'){const n=graph._nodes.find(n=>String(n.id)===String(data.nodeId));if(n&&PARAMETERS.has(n.comfyClass)){const w=n.widgets?.find(w=>w.name===data.name);if(w){w.value=data.value;w.callback?.(w.value);n.setDirtyCanvas(true,true)}}return}
  if(data?.type==='star7-director-package-export'&&!running){try{
   const plan=withLibrary(owner,data.plan);const response=await api.fetchApi('/star7/director/package/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan,workflow:graph.serialize()})});
   if(!response.ok)throw Error((await response.json()).error);const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=(plan.title||plan.id)+'.star7.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);progress('项目包已导出，包含工作流、设置和素材。');
  }catch(error){progress(error.message,false,true)}return}
  if(data?.type==='star7-director-package-import'&&!running){try{if(!data.workflow?.nodes)throw Error('项目包缺少工作流');await app.loadGraphData(data.workflow)}catch(error){progress(error.message,false,true)}return}
  if(data?.type==='star7-director-download-export'){if(['/star7/director/download-film/','/star7/director/download-export-zip/'].some(prefix=>data.url?.startsWith(prefix)))downloadVideo(data.url,data.filename);return}
  if(data?.type==='star7-director-export-action'){
   try{const response=await jsonRequest('/star7/director/export-action/'+encodeURIComponent(data.projectId)+'/'+encodeURIComponent(data.filename),{action:data.action});send('star7-director-export-action-result',{...response,requestId:data.requestId})}catch(error){send('star7-director-export-action-result',{requestId:data.requestId,error:error.message})}return;
  }
 if(['star7-director-combine','star7-director-export-segments'].includes(data?.type)&&!exporting){exporting=true;progress('导出任务已提交，将在当前生成步骤之后保存已有视频…',running);try{
   if(app.graph!==graph)throw Error('请返回导演台工作流');const prepared=await prepare(),scope=data.type==='star7-director-combine'?'all':data.type==='star7-director-export-segments'?'segments':'one',payload=JSON.stringify({plan:withLibrary(owner,data.plan),prompt:prepared.output,scope,shot_id:data.shotId});
   const title=scope==='all'?'Star7 · 合并导出全片':scope==='segments'?'Star7 · 分段导出':'Star7 · 导出当前镜头',exportPlan=JSON.stringify({star7_action:'export',export_json:payload}),output={[String(owner.id)]:{class_type:'Star7DirectorDesk',inputs:{project_json:exportPlan},_meta:{title}}},workflow=structuredClone(prepared.workflow?.nodes?.length?prepared.workflow:graph.serialize());
   const queued=await api.queuePrompt(0,{output,workflow});if(!queued.prompt_id)throw Error('未收到导出任务编号');const history=await waitPrompt(queued.prompt_id),ui=history.outputs?.[String(owner.id)],result=ui?.star7_export?.[0],entry=ui?.gifs?.[0];if(!result||!entry)throw Error('导出任务未返回视频');
   const url='/view?'+new URLSearchParams({filename:entry.filename,subfolder:entry.subfolder,type:'output'}),download_url='/star7/director/download-film/'+encodeURIComponent(result.project_id)+'/'+encodeURIComponent(result.filename);
   const entries=ui.gifs||[entry],items=(result.items||entries.map(e=>({filename:e.filename,name:e.filename}))).map(item=>{const e=entries.find(e=>e.filename===item.filename)||entry;return {...item,url:'/view?'+new URLSearchParams({filename:item.filename,subfolder:e.subfolder,type:'output'}),download_url:'/star7/director/download-film/'+encodeURIComponent(result.project_id)+'/'+encodeURIComponent(item.filename)}});
   const directory_name=entry.subfolder.split('/').pop(),zip_url='/star7/director/download-export-zip/'+encodeURIComponent(result.project_id)+'/'+encodeURIComponent(result.filename);send('star7-director-export-result',{...result,items,directory_name,zip_url,url,download_url,asset_id:entry.id,job_id:queued.prompt_id});progress(result.message+(result.assets_enabled?' 已保存到 ComfyUI 资产。':' 已保存到 ComfyUI 任务输出。'),running);
  }catch(error){progress(error.message,running,true)}finally{exporting=false}return}
  if(data?.type!=='star7-director-run'||libraryMode)return;
  const wasRunning=running;running=true;serverOwned=true;if(!wasRunning)batchRunId=null;
  try{
   if(app.graph!==graph)throw Error('请回到导演台所在工作流。');
   const plan=withLibrary(owner,structuredClone(data.plan));
   livePlan=structuredClone(plan);widget.value=JSON.stringify(plan);owner.setDirtyCanvas(true,true);progress('正在把任务交给服务端…',true);
   const prepared=await prepare();let bridgeId=null;
   if(!isDesk){const bridges=graph._nodes.filter(n=>n.comfyClass==='Star7DirectorConditioning');if(bridges.length!==1)throw Error('工作流需要一个镜头条件桥');bridgeId=String(bridges[0].id)}
   const queued=await batch.start({plan,prepared,scope:data.scope,shot_id:data.shotId,shot_ids:data.shotIds,owner_id:String(owner.id),bridge_id:bridgeId,client_id:api.clientId});send('star7-director-run-accepted',{shotId:data.shotId,queued:!!queued.predecessor_id});
  }catch(error){running=wasRunning;serverOwned=wasRunning;if(!wasRunning)livePlan=null;send('star7-director-run-accepted',{error:true});progress(error.message,wasRunning,true)}

 };
 const execution=e=>{if(!attached())return;const d=e.detail||{},id=String(d.display_node??d.node??'');executingOwner=isDesk&&(id===String(owner.id)||id.startsWith(owner.id+'.director.'));if(executingOwner&&!activeRun&&!serverOwned){try{const p=JSON.parse(widget.value);activeRun={projectId:p.id,shotId:p.runtime?.active_shot_id||p.shots[0]?.id,nonce:p.runtime?.request_nonce||'manual'};send('star7-director-preview-start',activeRun)}catch{}}if(!d.node&&!running)activeRun=null};
 const phaseEvent=e=>{if(!attached())return;const d=e.detail||{};if(isDesk&&!String(d.node_id||'').startsWith(owner.id+'.director.'))return;if(serverOwned&&batchRunId&&d.batch_id!==batchRunId)return;if(serverOwned&&activeRun?.nonce&&d.nonce!==activeRun.nonce)return;if(d.projectId!==(livePlan||JSON.parse(widget.value)).id)return;const next={projectId:d.projectId,shotId:d.shotId,nonce:d.nonce,phase:d.phase,previewNodeId:String(owner.id)+'.director.'+d.nonce+'.605'};if(activeRun?.nonce!==next.nonce)send('star7-director-preview-start',next);activeRun=next;send('star7-director-phase',next)};
 const nativeRun=e=>{const d=e.detail;if(!attached()||String(d?.owner_id)!==String(owner.id)||d.run?.project_id!==(livePlan||JSON.parse(widget.value)).id)return;applyBatchState(d.run);batch.restore(d.run.project_id).catch(error=>progress(error.message,running,true))};
 const livePreview=e=>{const d=e.detail;if(!isDesk||!activeRun||String(d?.node_id)!==activeRun.previewNodeId)return;previewRecovery.pushed(activeRun.previewNodeId);send('star7-director-live-preview',{...d,projectId:activeRun.projectId,shotId:activeRun.shotId})};
 const suppressDefault=e=>{if(!isDesk||!executingOwner)return;if(e.type==='b_preview_with_metadata'){const id=String(e.detail?.displayNodeId??e.detail?.parentNodeId??e.detail?.nodeId??'');if(id!==String(owner.id)&&!id.startsWith(owner.id+'.director.'))return;}e.preventDefault();e.stopImmediatePropagation();owner.imgs=[];owner.setDirtyCanvas(true,true)};
 if(isDesk){api.addEventListener('star7_director_run',nativeRun);api.addEventListener('executing',execution);api.addEventListener('star7_director_stage',phaseEvent);api.addEventListener('star7_director_h3_live_preview',livePreview);api.addEventListener('b_preview',suppressDefault,true);api.addEventListener('b_preview_with_metadata',suppressDefault,true)}
 // Observe this workflow only; ignore view/selection and runtime state.
 let graphSignature=null;
 const graphWatch=libraryMode?null:setInterval(()=>{if(app.graph!==graph||!owner._directorInitialized)return;try{
  const snapshot=graph.serialize();const signature=JSON.stringify({links:snapshot.links,nodes:snapshot.nodes.map(n=>({id:n.id,type:n.type,mode:n.mode,widgets:['Star7DirectorDesk','Star7DirectorPlan'].includes(n.type)?null:n.widgets_values}))});
  if(graphSignature!==null&&graphSignature!==signature)send('star7-director-project-graph-dirty');graphSignature=signature;
 }catch{}},2000);
 const cleanup=()=>{if(disposed)return;disposed=true;reloadVersion++;clearInterval(graphWatch);previewRecovery.dispose();resultDelivery.dispose();batch.dispose();window.removeEventListener('message',listener);frame.onload=null;host.remove();const index=owner.widgets?.indexOf(dom);if(index>=0){dom.onRemove?.();owner.widgets.splice(index,1)}delete owner._directorMount;delete owner._directorReload;delete owner._directorLibraryChanged;if(isDesk){api.removeEventListener('star7_director_run',nativeRun);api.removeEventListener('executing',execution);api.removeEventListener('star7_director_stage',phaseEvent);api.removeEventListener('star7_director_h3_live_preview',livePreview);api.removeEventListener('b_preview',suppressDefault,true);api.removeEventListener('b_preview_with_metadata',suppressDefault,true)}};
 window.addEventListener('message',listener);
 const reload=async()=>{
  if(!attached())return;const version=++reloadVersion;
  if(running&&!serverOwned)return;
  try{
   let value=libraryMode?{schema_version:'1.0',id:'library_'+owner.id,library_name:JSON.parse(widget.value).name||'素材库',asset_sequences:JSON.parse(widget.value).sequences||{},assets:JSON.parse(widget.value).assets,reference_size:JSON.parse(widget.value).reference_size,shots:[]}:JSON.parse(widget.value);
   if(!value||typeof value.id!=='string'||!Array.isArray(value.assets)||!Array.isArray(value.shots))throw Error('当前节点未包含有效项目数据；原数据已保留，请读取已保存的项目工作流。');
   if(!libraryMode&&value.generation_preset==='detail'&&value.generation?.['126']?.steps===6)value.generation={...value.generation,'126':{...value.generation['126'],steps:8}};
   if(!libraryMode&&!owner._directorInitialized){
    for(const parameter of (isDesk?[]:value.pipeline_parameters||[])){const target=graph._nodes.find(n=>String(n.id)===String(parameter.nodeId)&&n.comfyClass===parameter.classType);const item=target?.widgets?.find(w=>w.name===parameter.name);if(item){item.value=parameter.value;item.callback?.(item.value);target.setDirtyCanvas(true,true)}}
    owner._directorInitialized=true;
   }
   if(!libraryMode){value=withLibrary(owner,value);widget.value=JSON.stringify(value)}
   const internals=isDesk?await (await api.fetchApi('/star7/director/generation-fields')).json():[];
   if(!attached()||version!==reloadVersion)return;
   for(const f of internals)if(value.generation?.[f.nodeId]?.[f.name]!==undefined)f.value=value.generation[f.nodeId][f.name];
   activeRun=null;previewRecovery.reset();resultDelivery.reset();
   send('star7-director-open',{json:JSON.stringify(value),fields:libraryMode?[]:[...internals,...fields(graph)],mode:libraryMode?'library':isDesk?'desk':'legacy',selectedShot:value.runtime?.active_shot_id});if(!libraryMode){revisions.clear();await batch.restore(value.id);}
  }catch(error){progress(error.message,false,true)}
 };
 owner._directorLibraryChanged=()=>{try{const assets=readLibrary(owner);if(assets!==null){const value=JSON.parse(widget.value);value.assets=assets;value.reference_size=readReferenceSize(owner);widget.value=JSON.stringify(value);send('star7-director-library',{assets,reference_size:value.reference_size});owner.setDirtyCanvas(true,true)}}catch(error){progress(error.message,false,true)}};
 owner._directorReload=reload;frame.onload=reload;
 owner._directorMount={dispose:cleanup};
 if(dialog){dialog.append(host);dialog.onclose=()=>{stop=true;cleanup();dialog.remove()};return}
 dom=owner.addDOMWidget('director_ui','director',host,{serialize:false,hideOnZoom:false,getValue:()=>'',setValue:()=>{},getMinHeight:()=>libraryMode?560:850});
 // A computeSize hook makes LiteGraph treat this DOM widget as fixed height.
 delete dom.computeSize;
 dom.computeLayoutSize=()=>({minHeight:libraryMode?560:850,maxHeight:undefined,minWidth:0});
 delete dom.options.getMaxHeight;delete dom.options.getHeight;
 owner.setSize([Math.max(owner.size[0],libraryMode?340:1120),Math.max(owner.size[1],libraryMode?660:990)]);
}
function mountCurrentGraph(){for(const n of app.graph?._nodes||[])if(['Star7DirectorDesk','Star7DirectorLibrary'].includes(n.comfyClass))mount(n,n.comfyClass==='Star7DirectorLibrary')}
app.registerExtension({name:'Star7.Director',beforeLoadGraph(){for(const n of app.graph?._nodes||[])n._directorMount?.dispose()},afterConfigureGraph:mountCurrentGraph,onGraphLoadError:mountCurrentGraph,async beforeRegisterNodeDef(nodeType,nodeData){
 if(!['Star7DirectorDesk','Star7DirectorLibrary'].includes(nodeData.name))return;
 if(nodeData.name==='Star7DirectorDesk')nodeType.prototype.onDrawBackground=function(){this.imgs=[];this.images=[];for(let i=(this.widgets?.length||0)-1;i>=0;i--)if(this.widgets[i].name==='$$canvas-image-preview'){this.widgets[i].onRemove?.();this.widgets.splice(i,1)}};
 const original=nodeType.prototype.onNodeCreated;
 nodeType.prototype.onNodeCreated=function(){original?.apply(this,arguments);hideJSON(this,nodeData.name==='Star7DirectorLibrary'?'library_json':'project_json');
  setTimeout(()=>mount(this,nodeData.name==='Star7DirectorLibrary'),0);
 };
 const added=nodeType.prototype.onAdded;nodeType.prototype.onAdded=function(){const r=added?.apply(this,arguments);setTimeout(()=>mount(this,nodeData.name==='Star7DirectorLibrary'),0);return r};
 const removed=nodeType.prototype.onRemoved;nodeType.prototype.onRemoved=function(){this._directorMount?.dispose();this._directorInitialized=false;return removed?.apply(this,arguments)};
 const configured=nodeType.prototype.onConfigure;nodeType.prototype.onConfigure=function(){const r=configured?.apply(this,arguments);if(nodeData.name!=='Star7DirectorPlan')this.setSize([Math.max(this.size[0],nodeData.name==='Star7DirectorLibrary'?340:1120),Math.max(this.size[1],nodeData.name==='Star7DirectorLibrary'?660:990)]);return r};
}});
