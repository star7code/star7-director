import {chooseDirectory,saveExport} from './export-save.mjs?v=20261015-type2';
export function mountExportResults(){
 const $=id=>document.getElementById(id);let result=null,items=[],selected=0,pending=null;
 const send=data=>parent.postMessage(data,location.origin);
 function select(index){selected=index;const item=items[index];if(!item)return;$('export-result-video').pause();$('export-result-video').src=item.url;$('export-result-position').textContent=(result.scope==='segments'?`第 ${index+1} / ${items.length} 段 · `:'')+(item.name||item.filename);$('export-result-prev').disabled=index===0;$('export-result-next').disabled=index>=items.length-1;for(const [i,button] of [...$('export-result-list').children].entries())button.classList.toggle('active',i===index)}
 function busy(value){for(const id of ['export-result-open','export-result-download','export-result-zip'])$(id).disabled=value}
 async function save(zip){if(!result||pending)return;const current=result;pending=crypto.randomUUID();busy(true);try{const directory=await chooseDirectory();$('export-result-status').textContent=zip?'正在保存 ZIP…':'正在保存视频…';const message=await saveExport(directory,current,zip);if(result===current)$('export-result-status').textContent=message}catch(error){if(result===current)$('export-result-status').textContent=error.name==='AbortError'?'已取消选择目录':error.message}finally{pending=null;busy(false)}}
 function action(value){if(!result||pending)return;pending=crypto.randomUUID();busy(true);$('export-result-status').textContent=value==='downloads'?'正在保存全部视频到系统下载目录…':'正在打开导出文件夹…';send({type:'star7-director-export-action',requestId:pending,projectId:result.project_id,filename:items[selected].filename,action:value})}
 window.addEventListener('message',e=>{
  if(e.origin!==location.origin||e.source!==parent)return;
  if(e.data?.type==='star7-director-export-action-result'&&e.data.requestId===pending){pending=null;busy(false);$('export-result-status').textContent=e.data.error||e.data.message+(e.data.directory?'：'+e.data.directory:'');return}
  if(e.data?.type!=='star7-director-export-result')return;
  result=e.data;pending=null;busy(false);items=result.items?.length?result.items:[{filename:result.filename,url:result.url,name:result.filename,download_url:result.download_url}];
  $('export-result-title').textContent=result.scope==='segments'?'分段导出 · '+items.length+' 个视频':result.scope==='all'?'合并导出结果':'单镜头导出结果';
  $('export-result-message').textContent=result.message;$('export-result-location').textContent='已保存到 ComfyUI 输出目录：'+(result.subfolder||'');$('export-result-status').textContent='';
  $('export-result-list').replaceChildren(...items.map((item,index)=>{const button=document.createElement('button');button.type='button';button.className='export-item';const title=document.createElement('b'),file=document.createElement('small');title.textContent=String(index+1).padStart(2,'0')+' · '+(item.name||item.shot_id||'视频');file.textContent=item.filename;button.append(title,file);button.onclick=()=>select(index);return button}));
  $('export-result-list').hidden=result.scope!=='segments';$('export-result-navigation').hidden=result.scope!=='segments';$('export-result-zip').hidden=result.scope==='one';$('export-result-download').textContent='下载到指定目录';select(0);
  if(!$('export-result-dialog').open)$('export-result-dialog').showModal();
 });
 $('export-result-prev').onclick=()=>select(Math.max(0,selected-1));$('export-result-next').onclick=()=>select(Math.min(items.length-1,selected+1));
 $('export-result-close').onclick=()=>$('export-result-dialog').close();$('export-result-dialog').onclose=()=>$('export-result-video').pause();
 $('export-result-open').onclick=()=>action('open');
 $('export-result-download').onclick=()=>save(false);
 $('export-result-zip').onclick=()=>save(true);
 const resize=new ResizeObserver(()=>{if($('export-result-dialog').open&&result?.scope==='segments'){const height=Math.max(180,$('export-result-player').getBoundingClientRect().height)+'px';$('export-result-list').style.height=height;$('export-result-list').style.maxHeight=height}});resize.observe($('export-result-player'));
}
