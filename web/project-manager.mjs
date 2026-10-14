export function mountProjectManager({getPlan,isBusy,onTitle,request,root}){
 const $=id=>document.getElementById(id);let revision=0,saved=0,timer=null,inflight=null,session=0,openedId=null,transition=null;
 const status=text=>$('project-save-status').textContent=text;
 async function refresh(){try{const data=await request('list');$('local-project-count').textContent=data.projects.length;$('local-project-list').replaceChildren(...data.projects.map(item=>{
  const row=document.createElement('div');row.className='local-project-row';const info=document.createElement('div'),name=document.createElement('b'),date=document.createElement('small');name.textContent=item.title+(item.id===getPlan().id?' · 当前项目':'');date.textContent=new Date(item.modified_at).toLocaleString()+' · '+item.shots+' 个镜头';info.append(name,date);row.append(info);
  for(const [label,action] of [['读取','read'],['重命名','rename'],['创建副本','clone'],['导出项目包','export'],['删除','delete']]){const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=['read','export'].includes(action)&&isBusy()||action==='delete'&&item.id===getPlan().id;button.onclick=async()=>{try{
   if(action==='export'){if(isBusy()){status('生成或排队完成后再导出项目包。');return}button.disabled=true;if(item.id===getPlan().id)await flush(true);status('正在导出项目包…');const result=await request('export',{id:item.id});status(result.message);return}
   if(action==='read'){await change(()=>request('read',{id:item.id}));return}
   if(action==='rename'){const title=await textName(item.title);if(title===null)return;if(item.id===getPlan().id){onTitle(title);changed();await flush(true)}else await request('rename',{id:item.id,title});}
   if(action==='clone'){const source=await request('read',{id:item.id});await request('clone',{plan:source.plan,workflow:source.workflow});}
   if(action==='delete'){if(!await confirmDelete(item.title))return;await request('delete',{id:item.id});}
   await refresh();
  }catch(e){status(e.message)}finally{if(action==='export')button.disabled=isBusy()}};row.append(button)}return row}));}catch(e){status(e.message)}}
 function opened(){session++;openedId=getPlan().id;revision=1;saved=0;clearTimeout(timer);inflight=null;$('project-current-name').value=getPlan().title||'';status('正在自动保存…');flush(false).catch(()=>{});}
 function changed(){if(document.body.dataset.mode==='library')return;revision++;status('有改动，正在自动保存…');clearTimeout(timer);timer=setTimeout(()=>flush(false).catch(()=>{}),500)}
 async function flush(manual=false){if(document.body.dataset.mode==='library')return;clearTimeout(timer);if(inflight){await inflight;if(manual||saved<revision)return flush(manual);return}const localSession=session,version=revision;
  const job=(async()=>{try{await request('save',{plan:structuredClone(getPlan()),manual});if(session===localSession){saved=version;status(manual?'已手动保存':'已自动保存');await refresh()}}catch(e){if(session===localSession)status('保存失败：'+e.message);throw e}})();inflight=job;
  try{await job}finally{if(inflight===job)inflight=null}if(session===localSession&&saved<revision)return flush(manual);
 }
 async function change(create){if(isBusy()){status('生成或排队完成后再切换项目。');return}try{
  if(saved<revision||inflight){const answer=await saveChoice();if(answer==='cancel')return;if(answer==='save')await flush(true);else{clearTimeout(timer);session++}}
  const item=await create();await request('activate',{item});
 }catch(e){status(e.message)}}
 function saveChoice(){return new Promise(resolve=>{const dialog=$('project-unsaved-dialog');dialog.showModal();transition=resolve})}
 for(const [id,value] of [['project-switch-save','save'],['project-switch-discard','discard'],['project-switch-cancel','cancel']])$(id).onclick=()=>{const resolve=transition;transition=null;$('project-unsaved-dialog').close();resolve?.(value)};
 $('project-unsaved-dialog').onclose=()=>{const resolve=transition;transition=null;resolve?.('cancel')};
 async function textName(value){return new Promise(resolve=>{const dialog=$('project-name-dialog'),input=$('project-name-value');input.value=value;dialog.showModal();input.focus();const finish=v=>{dialog.onclose=null;dialog.close();resolve(v)};$('project-name-ok').onclick=()=>{const name=input.value.trim();if(name&&name.length<=120)finish(name)};$('project-name-cancel').onclick=()=>finish(null);dialog.onclose=()=>finish(null)})}
 async function confirmDelete(name){return new Promise(resolve=>{const dialog=$('project-delete-dialog');$('project-delete-name').textContent=name;dialog.showModal();const finish=v=>{dialog.onclose=null;dialog.close();resolve(v)};$('project-delete-ok').onclick=()=>finish(true);$('project-delete-cancel').onclick=()=>finish(false);dialog.onclose=()=>finish(false)})}
 $('project-current-name').onchange=()=>{const value=$('project-current-name').value.trim();if(!value)return;onTitle(value);changed()};
 $('project-save').onclick=()=>flush(true).catch(()=>{});
 $('project-save-as').onclick=()=>change(()=>request('clone',{plan:structuredClone(getPlan())}));
 $('project-new').onclick=()=>change(()=>request('new',{plan:structuredClone(getPlan())}));
 $('project-package-import').onclick=()=>{if(isBusy()){status('生成或排队完成后再导入项目包。');return}$('package-import').click()};
 $('project-refresh').onclick=refresh;
 return {opened,changed,refresh};
}
