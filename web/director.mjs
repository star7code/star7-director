import {renderCache} from './cache-view.mjs?v=20261017-lifecycle3';
import {chooseDirectory,saveResponse,saveNative} from './export-save.mjs?v=20261015-modelonly';
import {mountExportResults} from './export-results.mjs?v=20261015-modelonly';
import {mountQueueView} from './queue-view.mjs?v=20261017-lifecycle3';
import {mountProjectManager} from './project-manager.mjs?v=20261015-modelonly';
import {mountPlaylistPreview} from './playlist-preview.mjs?v=20261013-monotone-post1';
import {changeContinuity} from './continuity-state.mjs?v=20261013-monotone-post1';
import {nextMaterialName,retireNameAlias,initializeMaterialSlots} from './asset-naming.mjs?v=20261013-monotone-post1';
import {mountShotPreview} from './shot-preview.mjs?v=20261014-fresh-base1';
import {mountLayout} from './layout.mjs?v=20261013-monotone-post1';
import {materialOutline} from './material-outline.mjs?v=20261014-import-guide1';
import {mountPrompt} from './prompt-editor.mjs?v=20261013-monotone-post1';
let projectManager=null,initialized=false;document.getElementById('app').inert=true;const projectReplies=new Map();let projectRequestId=0;
let shotMenuId=null,renameShotId=null;
let layoutUI=null;
let processUnavailableReason='';let promptUI=null,processReady=false,exportReady=false,processCheck=0,processTimer=null;
const $=id=>document.getElementById(id);
const kinds={character:'人物',scene:'场景',prop:'物品',voice:'音色',video:'视频',effect:'特效'};
const icons={character:'♙',scene:'⌂',prop:'◇',voice:'♫',video:'▷',effect:'✦'};
let plan={schema_version:'1.0',id:'project_'+Date.now(),title:'新建影片',settings:{width:960,height:544,fps:24},assets:[],shots:[{id:'shot_001',name:'shot_001',duration:5,seed:666,seed_control:'increment',prompt:'',continuity:{mode:'independent'},post:{hd:false,face:false}}]};
let importing=false,draggedShot=null,undoShotEdit=null,undoAssetEdit=null,pendingVoice=null,assetUploading=false,draggedAsset=null;
let previewUI=null,storyboardCandidate=null,storyboardToken=0,storyboardChecking=false;
let shotStates=new Map(),generatingShot=null,generatingPhase=null,runSubmitting=false,planRevision=0,noticeEpoch=0,processNoticeEpoch=0;
let queuedShots=new Set(),currentStale=false,statusShotKey=null,lastNotice={text:'先编排分镜，再检查资源。',error:false};
let batchSelecting=false,batchSelection=new Set();
let selected=0,category='character',editingAsset=null,busy=false,uploadedMedia=null,pipelineFields=[];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
function mediaURL(source){if(source.startsWith('star7-project/'))return '/star7/director/project-media/'+source.slice('star7-project/'.length).split('/').map(encodeURIComponent).join('/');if(source.startsWith('star7-director/'))return '/star7/director/media/'+encodeURIComponent(source.slice('star7-director/'.length));const cut=source.lastIndexOf('/');return '/view?'+new URLSearchParams({filename:source.slice(cut+1),subfolder:cut<0?'':source.slice(0,cut),type:'input'})}
function notice(text,error=false,kind='action'){noticeEpoch++;lastNotice={text,error,kind};$('global-notice').textContent=text;$('global-notice').style.color=error?'#f29e91':'#a99cec';paintParameterNotice();if(document.body.dataset.mode==='library'){$('library-status').hidden=false;$('library-status').textContent=text;$('library-status').style.color=error?'#f29e91':'#a99cec'}}
function draft(){if(!initialized)return;projectManager?.changed();planRevision++;notice('',false,'edit');invalidateStoryboard();plan.modified_at=new Date().toISOString();plan.title=$('title').value;if(plan.shots[selected])plan.runtime={active_shot_id:plan.shots[selected].id};parent.postMessage({type:'star7-director-plan',plan},location.origin);refreshProcessAvailability()}
function clearShotDrag(){draggedShot=null;for(const el of $('shots').querySelectorAll('.shot'))el.classList.remove('dragging','drop-before','drop-after')}
function rememberShotEdit(){undoShotEdit={shots:structuredClone(plan.shots),selectedId:plan.shots[selected]?.id}}
function clearShotUndo(){undoShotEdit=null;$('undo-shot').hidden=true}
function repairContinuity(){
 const earlier=new Set();let adjusted=0;
 for(let i=0;i<plan.shots.length;i++){
  const shot=plan.shots[i],continuity=shot.continuity||{mode:'independent'};
  if(!i&&shot.keyframes?.first?.from_previous){delete shot.keyframes.first;adjusted++;}
  if(continuity.mode!=='independent'&&!earlier.has(continuity.source_shot)){
   shot.continuity=i?{...continuity,source_shot:plan.shots[i-1].id,...(continuity.mode==='selected_frame'?{frame:0}:{})}:{mode:'independent'};adjusted++;
  }
  earlier.add(shot.id);
 }
 return adjusted;
}
function moveShot(id,targetId,after=false){
 if(importing||id===targetId)return;
 const from=plan.shots.findIndex(s=>s.id===id);if(from<0)return;
 const currentId=plan.shots[selected]?.id;const order=[...plan.shots];const [shot]=order.splice(from,1);
 const target=targetId===null?order.length:order.findIndex(s=>s.id===targetId);if(target<0)return;
 order.splice(target+(targetId!==null&&after?1:0),0,shot);
 if(order.every((s,i)=>s.id===plan.shots[i].id))return;
 rememberShotEdit();plan.shots=order;selected=Math.max(0,plan.shots.findIndex(s=>s.id===currentId));const adjusted=repairContinuity();draft();render();notice('已调整镜头顺序。'+(adjusted?` 已调整 ${adjusted} 处连续性引用，可撤销。`:''));
}
function drawShots(){
 const list=$('shots'),scrollTop=list.scrollTop,focusedId=document.activeElement?.closest('.shot')?.dataset.shotId;
 const existing=new Map(Array.from(list.querySelectorAll('.shot'),b=>[b.dataset.shotId,b]));
 const milliseconds=plan.shots.reduce((sum,s)=>sum+Math.round(Math.max(0,Number(s.duration??5)||0)*1000),0),minutes=Math.floor(milliseconds/60000),seconds=(milliseconds%60000)/1000;
 $('shot-total-duration').textContent='总时长：'+minutes+'分'+seconds+'秒';

 $('batch-select').hidden=batchSelecting;$('batch-confirm').hidden=!batchSelecting;$('batch-cancel').hidden=!batchSelecting;$('batch-confirm').disabled=runSubmitting||!batchSelection.size;$('batch-confirm').textContent='确定生成（'+batchSelection.size+'）';$('batch-select').disabled=importing||runSubmitting;
 const buttons=plan.shots.map((s,i)=>{
  const b=existing.get(s.id)||node('button');b.className='shot'+(selected===i?' active':'');b.dataset.shotId=s.id;b.draggable=false;const generating=generatingShot===s.id,stale=!!shotStates.get(s.id)?.stale;b.classList.toggle('generating',generating);b.classList.toggle('stale',stale&&!generating);b.title=(generating?'正在生成；':stale?'参数已修改：'+([...new Set(visibleChanges(shotStates.get(s.id),s).map(c=>c.label))].join('、')||'基准信息不足，请校验计划')+'；':'')+'选择镜头；抓住右侧六点调整顺序';
  const handle=node('span','⠿','drag-handle');handle.draggable=!importing;handle.title='拖动此抓手调整镜头顺序';handle.setAttribute('aria-label','调整镜头顺序');
  b.replaceChildren(handle,node('span',String(i+1).padStart(2,'0'),'num'),node('b',s.name||s.id),node('small',`${s.duration} 秒 · ${s.input_mode==='keyframes'?(s.keyframes?.first&&s.keyframes?.last?'首尾帧':s.keyframes?.first?'首帧':s.keyframes?.last?'尾帧':'智能首尾帧'):s.continuity?.mode==='independent'?'独立镜头':s.continuity?.mode==='tail_reference'?'尾帧参考':s.continuity?.mode==='selected_frame'?'选定画面参考':'延续镜头'}`));
  if(batchSelecting){const label=node('label',undefined,'shot-select');const check=node('input');check.type='checkbox';check.checked=batchSelection.has(s.id);check.setAttribute('aria-label','选择生成 '+(s.name||s.id));label.title='选择此镜头生成';label.append(check);label.onclick=e=>e.stopPropagation();check.onchange=()=>{if(check.checked)batchSelection.add(s.id);else batchSelection.delete(s.id);drawShots()};b.append(label)}
  b.onclick=()=>{if(importing)return;selected=plan.shots.findIndex(shot=>shot.id===s.id);render()};
  b.oncontextmenu=e=>{e.preventDefault();e.stopPropagation();openShotMenu(s.id,e.clientX,e.clientY)};
  handle.ondragstart=e=>{e.stopPropagation();if(importing){e.preventDefault();return}draggedShot=s.id;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-star7-director-shot',JSON.stringify({project:plan.id,id:s.id}));b.classList.add('dragging')};
  b.ondragover=e=>{if(!draggedShot||importing)return;e.preventDefault();e.stopPropagation();const after=e.clientY>b.getBoundingClientRect().top+b.getBoundingClientRect().height/2;for(const el of $('shots').querySelectorAll('.shot'))el.classList.remove('drop-before','drop-after');b.classList.add(after?'drop-after':'drop-before');e.dataTransfer.dropEffect='move'};
  b.ondrop=e=>{if(!draggedShot||importing)return;e.preventDefault();e.stopPropagation();const id=draggedShot,after=e.clientY>b.getBoundingClientRect().top+b.getBoundingClientRect().height/2;clearShotDrag();moveShot(id,s.id,after)};
  handle.ondragend=clearShotDrag;handle.onclick=e=>e.stopPropagation();
  b.onkeydown=e=>{if(e.key==='F2'){e.preventDefault();openShotRename(s.id);return}if(e.key==='ContextMenu'||e.shiftKey&&e.key==='F10'){e.preventDefault();const rect=b.getBoundingClientRect();openShotMenu(s.id,rect.left+20,rect.bottom);return}if(!e.altKey||!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const index=plan.shots.findIndex(shot=>shot.id===s.id),next=index+(e.key==='ArrowUp'?-1:1);if(next>=0&&next<plan.shots.length)moveShot(s.id,plan.shots[next].id,e.key==='ArrowDown')};
  return b;
 });
 // Selection/status updates keep the focused card and browser scroll anchor intact.
 if(list.children.length!==buttons.length||buttons.some((b,i)=>list.children[i]!==b)){
  list.replaceChildren(...buttons);
  if(focusedId)buttons.find(b=>b.dataset.shotId===focusedId)?.focus({preventScroll:true});
  list.scrollTop=scrollTop;
 }
 if(!plan.shots.length)$('shots').append(node('small','点击「＋ 镜头」开始编排。','empty-shots'));
}
$('shots').ondragover=e=>{if(draggedShot&&!importing){e.preventDefault();e.dataTransfer.dropEffect='move'}};
$('shots').ondrop=e=>{if(!draggedShot||importing)return;e.preventDefault();const id=draggedShot;clearShotDrag();moveShot(id,null)};
function render(){$('clear-vram-between-shots').checked=!!plan.execution_options?.clear_vram_between_shots;for(const id of ['project-library-import','project-library-export'])$(id).disabled=busy||importing;renderInputMode();migratePromptOptions();$('global-no-music').checked=!!plan.prompt_options.no_background_music;$('global-no-subtitles').checked=plan.prompt_options.no_subtitles;$('global-custom-prompt-enabled').checked=plan.prompt_options.custom_prompt_enabled??!!plan.prompt_options.custom_prompt?.trim();if(document.activeElement!==$('global-custom-prompt'))$('global-custom-prompt').value=plan.prompt_options.custom_prompt||'';$('import-storyboard').disabled=importing;renderContinuitySettings();layoutUI?.apply();document.body.dataset.busy=String(busy);closeShotMenu();ensureAssetSequences();
 renderCanvas();$('preset').value=plan.generation_preset||'standard';$('title').value=plan.title||'新建影片';
 refreshProcessAvailability();
 $('library-name').value=plan.library_name||'素材库';$('undo-asset').hidden=!undoAssetEdit;$('undo-asset').disabled=busy||importing;$('asset-count').textContent=plan.assets.length;$('shot-count').textContent=plan.shots.length;
 $('categories').replaceChildren(...Object.entries(kinds).map(([k,v])=>{const b=node('button',v,k===category?'active':'');b.onclick=()=>{category=k;render()};return b}));
 const query=$('search').value.toLowerCase();
 $('assets').replaceChildren(...plan.assets.filter(a=>(category==='all'||a.kind===category)&&a.name.toLowerCase().includes(query)).map(a=>{const b=node('button',undefined,'card');const art=node('div',icons[a.kind]||'◇','art');const image=a.media?.find(m=>m.type==='image');if(image){const im=document.createElement('img');im.src=mediaURL(image.thumbnail_source||image.source);im.loading='lazy';im.decoding='async';im.alt=a.name;im.draggable=false;im.ondragstart=e=>e.preventDefault();im.onerror=()=>{im.remove();art.textContent='图片缺失';b.classList.add('media-missing');b.title=a.name+'：素材文件缺失，点击素材卡重新上传即可补回';const note=b.querySelector('small');if(note)note.textContent='文件缺失 · 点击补回'};art.replaceChildren(im)};b.append(art,node('b',a.name),node('small',a.voice_id?'已绑定音色':kinds[a.kind]));b.title=a.name;b.onclick=()=>editAsset(a);const wrapper=node('div',undefined,'asset-item');wrapper.dataset.assetId=a.id;const remove=node('button','×','asset-remove');remove.title='删除 '+a.name;remove.setAttribute('aria-label','删除素材 '+a.name);remove.disabled=busy||importing;remove.onpointerdown=e=>e.stopPropagation();remove.onclick=e=>{e.preventDefault();e.stopPropagation();removeAsset(a.id)};wrapper.draggable=!busy&&!importing;wrapper.ondragstart=e=>{if(e.target.closest('.asset-remove')||busy||importing){e.preventDefault();return}draggedAsset=a.id;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-star7-director-asset',a.id);wrapper.classList.add('asset-dragging')};
wrapper.ondragover=e=>{if(!draggedAsset||busy||importing)return;e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='move';for(const el of $('assets').children)el.classList.remove('asset-drop');wrapper.classList.add('asset-drop')};
wrapper.ondrop=e=>{if(!draggedAsset)return;e.preventDefault();e.stopPropagation();const source=draggedAsset;clearAssetDrag();moveAsset(source,a.id)};wrapper.ondragend=clearAssetDrag;
wrapper.append(b,remove);return wrapper}));
 drawShots();previewUI?.show();
 const s=plan.shots[selected];$('face-count-override').checked=s?.post?.face_count!==undefined;$('face-count-override').disabled=!s;$('shot-face-count').value=String(s?.post?.face_count||plan.generation?.['395']?.face_count||pipelineFields.find(f=>f.internal&&String(f.nodeId)==='395'&&f.name==='face_count')?.value||1);$('shot-face-count').disabled=!s||!$('face-count-override').checked;for(const id of ['name','shot-title','duration','seed','seed-control','prompt','continuity','hd','face'])$(id).disabled=!s;
 $('apply-continuity').disabled=!s;
 $('run-one').disabled=!s||importing||runSubmitting;$('process-one').disabled=busy||!s;
 for(const id of ['run-all','combine','export-segments'])$(id).disabled=runSubmitting||!plan.shots.length;
 $('delete-shot').disabled=!canDeleteShot(s?.id);$('apply-all').disabled=!s;$('add-shot').disabled=importing;$('add-shot-after').disabled=importing||!s;$('undo-shot').hidden=!undoShotEdit;$('undo-shot').disabled=importing||!!undoShotEdit&&!canKeepQueuedShots(undoShotEdit.shots);$('process-one').disabled=true;
 if(!s){$('shot-id').textContent='';$('shot-title').value='';for(const id of ['name','duration','seed','prompt'])$(id).value='';$('hd').checked=false;$('face').checked=false;$('frame-field').hidden=true;promptUI?.refresh();$('mentions').hidden=true;$('result-video').pause();$('result-video').removeAttribute('src');$('result-video').hidden=true;$('preview-empty').hidden=false;return}
 parent.postMessage({type:'star7-director-select',shotId:s.id},location.origin);$('shot-id').textContent=s.id;$('shot-title').value=s.name||'';$('name').value=s.name||'';$('duration').value=s.duration;$('seed').value=s.seed||0;$('seed-control').value=s.seed_control||'fixed';renderNextSeed(s);$('prompt').value=s.prompt;promptUI?.refresh();
 $('continuity').value=s.continuity?.mode||'independent';$('frame-field').hidden=s.continuity?.mode!=='selected_frame';$('frame-index').value=s.continuity?.frame||0;$('hd').checked=!!s.post?.hd;$('face').checked=!!s.post?.face;
}
// Editing a checkbox must not rewrite optional fields or another control's value.
const postDrafts=new WeakMap();
function setPostField(shot,key,value){
 let draft=postDrafts.get(shot);
 if(!draft||draft.object!==shot.post){draft={object:shot.post,hadPost:Object.hasOwn(shot,'post'),original:structuredClone(shot.post||{})};postDrafts.set(shot,draft)}
 const original=draft.original;
 shot.post={...shot.post,[key]:value};
 if(value===false&&!Object.hasOwn(original,key))delete shot.post[key];
 if(!Object.keys(shot.post).length&&!draft.hadPost)delete shot.post;
 draft.object=shot.post;
}
function update(event){
 clearShotUndo();const s=plan.shots[selected];if(!s)return;const field=event.target.id;
 if(field==='name')s.name=$('name').value;
 if(field==='duration')s.duration=Number($('duration').value);
 if(field==='seed'||field==='seed-control'){
  const seed=Number($('seed').value),seedMode=$('seed-control').value;
  delete s.next_seed;
  if(field==='seed')s.seed=seed;else s.seed_control=seedMode;
  renderNextSeed(s);
 }
 if(field==='prompt')s.prompt=$('prompt').value;
 if(field==='hd'||field==='face')setPostField(s,field,$(field).checked);
 if(field==='face-count-override'||field==='shot-face-count'){
  if($('face-count-override').checked)s.post={...s.post,face_count:Number($('shot-face-count').value)};
  else{if(s.post)delete s.post.face_count;$('shot-face-count').value=String(plan.generation?.['395']?.face_count||pipelineFields.find(f=>f.internal&&String(f.nodeId)==='395'&&f.name==='face_count')?.value||1)}
  $('shot-face-count').disabled=!$('face-count-override').checked;
 }
 if(field==='continuity'||field==='frame-index'){
  const requestedMode=$('continuity').value,mode=selected?requestedMode:'independent';
  if(!selected&&requestedMode!=='independent')notice('首个镜头保持独立，可将当前模式应用到后续镜头。');
  const previousMode=s.continuity?.mode;
  s.continuity=changeContinuity(plan,s,mode,plan.shots[selected-1]?.id,Number($('frame-index').value));
  if(previousMode!==mode)promptUI?.refresh(true);
  if(mode==='selected_frame')$('frame-index').value=s.continuity.frame;
  $('frame-field').hidden=requestedMode!=='selected_frame';
 }
 $('shot-title').value=s.name||'';drawShots();draft();refreshProcessAvailability();
}
for(const id of ['name','duration','seed','seed-control','prompt','continuity','frame-index','hd','face','face-count-override','shot-face-count'])$(id).addEventListener('input',update);
function canvasPresetSize(resolution,ratio,orientation){const [a,b]=ratio.split(':').map(Number),short=Number(resolution),long=short*a/b,scale=Math.min(1,3840/Math.max(long,short)),align=n=>Math.max(32,Math.round(n/32)*32),w=align(long*scale),h=align(short*scale);return orientation==='portrait'?[h,w]:[w,h]}
function renderCanvas(){
 const width=plan.settings?.width||960,height=plan.settings?.height||544,profile=plan.canvas_profile||{resolution:'custom',ratio:'16:9',orientation:width>=height?'landscape':'portrait'};
 for(const option of $('resolution').options){const [w,h]=option.value==='custom'?[width,height]:canvasPresetSize(option.value,profile.ratio,profile.orientation);const label=option.value==='custom'?'自定义':option.value==='2160'?'4K（2160p）':option.value+'p';option.textContent=label+' · 约'+(w*h/1e6).toFixed(2)+' MP';option.title=w+' × '+h;}
 $('resolution').value=profile.resolution;$('aspect').value=profile.ratio;$('orientation').value=profile.orientation;$('width').value=width;$('height').value=height;
 $('canvas-resolution').textContent=profile.resolution==='custom'?'自定义':profile.resolution==='2160'?'4K':profile.resolution+'p';$('canvas-ratio').textContent=profile.resolution==='custom'?width+':'+height:profile.ratio;$('canvas-orientation').textContent=width===height?'方形':width>height?'横屏':'竖屏';$('canvas-width').textContent=width;$('canvas-height').textContent=height;refreshHDResolution();
}
function applyCanvasPreset(){
 const resolution=$('resolution').value,ratio=$('aspect').value,orientation=$('orientation').value;
 plan.canvas_profile={resolution,ratio,orientation};
 if(resolution!=='custom'){const [width,height]=canvasPresetSize(resolution,ratio,orientation);plan.settings={...plan.settings,width,height};}
 updateHDTarget();draft();renderCanvas();refreshProcessAvailability();
}
for(const id of ['resolution','aspect','orientation'])$(id).onchange=applyCanvasPreset;
for(const id of ['width','height'])$(id).onchange=()=>{if(!$(id).reportValidity()){renderCanvas();return}plan.settings={...plan.settings,[id]:Number($(id).value)};plan.canvas_profile={resolution:'custom',ratio:$('aspect').value,orientation:plan.settings.width>=plan.settings.height?'landscape':'portrait'};updateHDTarget();draft();renderCanvas();refreshProcessAvailability()};
for(const tab of document.querySelectorAll('[data-settings-tab]'))tab.onclick=()=>{for(const button of document.querySelectorAll('[data-settings-tab]'))button.setAttribute('aria-selected',String(button===tab));for(const page of document.querySelectorAll('[data-settings-page]'))page.hidden=page.dataset.settingsPage!==tab.dataset.settingsTab;$('pipeline-fields').scrollTop=0};
$('library-name').oninput=()=>{plan.library_name=$('library-name').value;draft()};$('title').oninput=draft;$('search').oninput=render;
function addShot(after=false){
 if(importing)return;rememberShotEdit();
 const used=plan.shots.map(s=>Number(s.id.match(/^shot_(\d+)/)?.[1]||0));const n=Math.max(plan.shot_sequence||0,...used,plan.shots.length)+1;plan.shot_sequence=n;
 let id='shot_'+String(n).padStart(3,'0');while(plan.shots.some(s=>s.id===id))id+='x';
 const index=after&&plan.shots[selected]?selected+1:plan.shots.length;plan.shots.splice(index,0,{id,name:id,duration:5,seed:666,seed_control:'increment',prompt:'',continuity:{mode:'independent'},post:{hd:false,face:false}});selected=index;draft();render();
};
$('add-shot').onclick=()=>addShot();$('add-shot-after').onclick=()=>addShot(true);
function closeShotMenu(){$('shot-menu').hidden=true;shotMenuId=null}
function openShotMenu(id,x,y){if(importing)return;selected=plan.shots.findIndex(s=>s.id===id);if(selected<0)return;render();shotMenuId=id;const menu=$('shot-menu');menu.hidden=false;const rect=menu.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(x,innerWidth-rect.width-8))+'px';menu.style.top=Math.max(8,Math.min(y,innerHeight-rect.height-8))+'px';$('shot-menu-delete').disabled=!canDeleteShot(id);$('shot-menu-rename').focus()}
function renameShot(id,value){if(importing)return;const shot=plan.shots.find(s=>s.id===id);if(!shot)return;clearShotUndo();shot.name=value;if(plan.shots[selected]?.id===id){if($('name').value!==value)$('name').value=value;if($('shot-title').value!==value)$('shot-title').value=value}drawShots();draft()}
function openShotRename(id){closeShotMenu();if(importing)return;const shot=plan.shots.find(s=>s.id===id);if(!shot)return;renameShotId=id;$('shot-rename-name').value=shot.name||'';$('shot-rename-dialog').showModal();$('shot-rename-name').focus();$('shot-rename-name').select()}
$('shot-title').oninput=()=>renameShot(plan.shots[selected]?.id,$('shot-title').value);
$('shot-menu-rename').onclick=()=>openShotRename(shotMenuId);
$('shot-menu-add-after').onclick=()=>{const id=shotMenuId;closeShotMenu();const index=plan.shots.findIndex(s=>s.id===id);if(index<0||importing)return;selected=index;addShot(true)};
$('shot-menu-delete').onclick=()=>{const id=shotMenuId;closeShotMenu();if(!canDeleteShot(id))return;selected=plan.shots.findIndex(s=>s.id===id);if(selected>=0){render();$('delete-shot').click()}};
$('shot-rename-close').onclick=()=>$('shot-rename-dialog').close();
$('shot-rename-dialog').querySelector('form').onsubmit=e=>{e.preventDefault();if(!$('shot-rename-name').reportValidity())return;renameShot(renameShotId,$('shot-rename-name').value.trim());$('shot-rename-dialog').close()};
document.addEventListener('pointerdown',e=>{if(!$('shot-menu').contains(e.target))closeShotMenu()});document.addEventListener('scroll',closeShotMenu,true);window.addEventListener('resize',closeShotMenu);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeShotMenu()});
$('delete-shot').onclick=()=>{
 if(!canDeleteShot(plan.shots[selected]?.id))return;
 rememberShotEdit();const removed=plan.shots[selected];plan.shot_sequence=Math.max(plan.shot_sequence||0,...plan.shots.map(s=>Number(s.id.match(/^shot_(\d+)/)?.[1]||0)));
 plan.shots.splice(selected,1);selected=Math.min(selected,Math.max(0,plan.shots.length-1));const adjusted=repairContinuity();
 if(plan.runtime){if(plan.shots[selected])plan.runtime.active_shot_id=plan.shots[selected].id;else delete plan.runtime.active_shot_id}
 $('result-video').pause();$('result-video').removeAttribute('src');$('result-video').hidden=true;$('preview-empty').hidden=false;
 draft();render();notice('已删除 '+(removed.name||removed.id)+'。'+(adjusted?` 已调整 ${adjusted} 处连续性引用。`:'')+'可点击撤销。');
};
$('undo-shot').onclick=()=>{
 if(importing||!undoShotEdit||!canKeepQueuedShots(undoShotEdit.shots))return;plan.shots=undoShotEdit.shots;selected=Math.max(0,plan.shots.findIndex(s=>s.id===undoShotEdit.selectedId));clearShotUndo();draft();render();notice('已撤销镜头调整。');
};
function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
$('export').onclick=()=>download(plan,plan.id+'.json');
$('catalog').onclick=()=>{const url=URL.createObjectURL(new Blob([materialOutline(plan)],{type:'text/plain;charset=utf-8'})),a=node('a');a.href=url;a.download=(plan.library_name||'素材库').replace(/[<>:"/\\|?*]/g,'_')+'_素材大纲.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};

async function importDocument(file){
 try{
  const incoming=JSON.parse(await file.text());let candidate;
  if(document.body.dataset.mode==='library'&&Array.isArray(incoming.assets)&&!Array.isArray(incoming.shots))candidate={...plan,assets:[...plan.assets,...incoming.assets]};
  else{
   if(incoming.schema_version!=='1.0'||!Array.isArray(incoming.shots))throw Error('需要 schema_version 1.0 和 shots');
   if(incoming.assets!==undefined){if(typeof incoming.id!=='string'||!Array.isArray(incoming.assets))throw Error('项目导入需要 id 和 assets');candidate=incoming}else candidate={...plan,shots:incoming.shots};
  }
  if(document.body.dataset.mode!=='library')for(const shot of candidate.shots||[])delete shot.next_seed;
  const response=await fetch('/star7/director/preflight',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(candidate)});const checked=await response.json();if(!response.ok)throw Error(checked.error||'分镜数据无效');
  clearAssetUndo();clearShotUndo();plan=candidate;selected=0;draft();render();notice(checked.missing.length?`已导入；有 ${checked.missing.length} 个素材需要重新上传。`:'已导入并通过资源检查。',!!checked.missing.length);
 }catch(e){notice('导入失败，原项目保持不变：'+e.message,true)}
}
$('import').onclick=()=>{if(!busy&&!importing)$('file').click()};$('file').onchange=async()=>{const file=$('file').files[0];if(file&&!busy&&!importing){importing=true;try{await importDocument(file)}finally{importing=false}}$('file').value=''};
$('validate').onclick=()=>{draft();notice('正在校验素材、衔接帧与生成配置…');parent.postMessage({type:'star7-director-validate',plan:structuredClone(plan),revision:planRevision},location.origin)};
function clearAssetDrag(){draggedAsset=null;for(const el of $('assets').children)el.classList.remove('asset-dragging','asset-drop')}
function moveAsset(id,target){
 if(busy||importing||id===target)return;const from=plan.assets.findIndex(a=>a.id===id),to=target===null?plan.assets.length-1:plan.assets.findIndex(a=>a.id===target);if(from<0||to<0)return;
 clearAssetUndo();const [asset]=plan.assets.splice(from,1);plan.assets.splice(to,0,asset);draft();render();notice('已调整素材顺序。');
}
$('assets').ondragover=e=>{if(draggedAsset&&!busy&&!importing){e.preventDefault();e.dataTransfer.dropEffect='move'}};
$('assets').ondrop=e=>{if(!draggedAsset)return;e.preventDefault();const source=draggedAsset;clearAssetDrag();moveAsset(source,null)};
function clearAssetUndo(){undoAssetEdit=null;$('undo-asset').hidden=true}
function removeAsset(id){
 if(busy||importing||assetUploading)return;const asset=plan.assets.find(a=>a.id===id);if(!asset)return;
 undoAssetEdit=structuredClone(plan.assets);plan.assets=plan.assets.filter(a=>a.id!==id);let unbound=0;
 for(const card of plan.assets)if(card.voice_id===id){delete card.voice_id;unbound++}
 if(editingAsset===id)$('asset-dialog').close();draft();render();notice('已删除 '+asset.name+'，原文件保留。'+(unbound?` 已解除 ${unbound} 个人物的音色绑定。`:'')+'镜头中的引用需替换，或撤销删除。');
}
$('undo-asset').onclick=()=>{if(busy||importing||!undoAssetEdit)return;plan.assets=undoAssetEdit;clearAssetUndo();draft();render();notice('已恢复素材与音色绑定。')};
function drawVoiceOptions(selectedVoice=''){
 const voices=[...plan.assets.filter(a=>a.kind==='voice'),...(pendingVoice?[pendingVoice]:[])];
 $('voice').replaceChildren(node('option','不绑定'),...voices.map(a=>{const option=node('option',a.name);option.value=a.id;return option}));$('voice').firstChild.value='';$('voice').value=selectedVoice;drawVoicePreview();
}
function drawVoicePreview(){const card=plan.assets.find(a=>a.id===$('voice').value)||(pendingVoice?.id===$('voice').value?pendingVoice:null);const media=card?.media?.find(m=>m.type==='audio');const player=$('voice-preview');player.pause();player.hidden=!media;if(media)player.src=mediaURL(media.source);else player.removeAttribute('src')}
function drawAssetEditor(){
 const kind=$('asset-kind').value,type=$('asset-media').value,source=$('asset-source').value;
 $('asset-description-toggle').hidden=!['character','scene','prop'].includes(kind)||type!=='image';$('voice-binding').hidden=kind!=='character';$('asset-clip').hidden=!source||!['audio','video'].includes(type);
 $('asset-upload-button').textContent=kind==='voice'?'上传音色':source?'更换素材':'上传素材';
 $('asset-upload').accept=kind==='voice'?'.wav,.mp3,.flac,.ogg,.m4a,.txt':kind==='effect'?'audio/*,video/*,.txt':kind==='video'?'video/*,.txt':'image/*,.txt';
 const preview=$('asset-preview');preview.replaceChildren();
 if(source&&type!=='none'){const media=document.createElement(type==='image'?'img':type==='audio'?'audio':'video');media.src=mediaURL(source);if(type!=='image')media.controls=true;else media.alt=$('asset-name').value||'素材预览';preview.append(media)}else preview.append(node('span',kind==='effect'?'可以只填写描述，也可以上传参考素材':'上传图片、视频或音频作为参考素材'));
}
function editAsset(asset=null){
 if(busy||importing||assetUploading)return;uploadedMedia=asset?.text_file?structuredClone(asset.text_file):asset?.media?.[0]?structuredClone(asset.media[0]):null;pendingVoice=null;$('asset-upload').value='';$('voice-upload').value='';$('upload-status').textContent='';editingAsset=asset?.id||null;
 $('asset-kind').replaceChildren(...Object.entries(kinds).filter(([k])=>k!=='all').map(([k,v])=>{const option=node('option',v);option.value=k;return option}));
 $('asset-kind').value=asset?.kind||(category!=='all'?category:'character');$('asset-name').value=asset?.name||nextAssetName($('asset-kind').value);$('asset-description').value=asset?.description||'';$('asset-inject-description').checked=asset?.inject_description===true;
 const defaultType=$('asset-kind').value==='voice'?'audio':$('asset-kind').value==='video'?'video':$('asset-kind').value==='effect'?'none':'image';
 $('asset-media').value=asset?(asset.media?.[0]?.type||'none'):defaultType;$('asset-source').value=asset?.media?.[0]?.source||'';$('asset-start').value=asset?.media?.[0]?.start_seconds||0;$('asset-length').value=asset?.media?.[0]?.duration_seconds||6;
 $('asset-delete').hidden=!asset;drawVoiceOptions(asset?.voice_id||'');drawAssetEditor();$('asset-dialog').showModal();
}
$('asset-upload-button').onclick=()=>{if(!assetUploading)$('asset-upload').click()};$('voice-upload-button').onclick=()=>{if(!assetUploading)$('voice-upload').click()};$('voice').onchange=drawVoicePreview;
$('asset-delete').onclick=()=>removeAsset(editingAsset);
$('add-asset').onclick=()=>editAsset();function saveAsset(textOnly=false){const name=$('asset-name').value.trim();if(!name){$('asset-name').reportValidity();return}if(plan.assets.some(a=>a.id!==editingAsset&&(a.name===name||a.id===name))){ $('upload-status').textContent='素材名称已存在，请换一个名称。';return}const kind=$('asset-kind').value,type=textOnly?'none':$('asset-media').value,source=textOnly?'':$('asset-source').value.trim();if(!textOnly&&(!source||type==='none')){$('upload-status').textContent='请上传对应素材文件；仅保存描述请点击「保存纯文本素材」。';return}if(type==='none'&&!$('asset-description').value.trim()){$('upload-status').textContent='请填写文字素材内容。';return}if(type!=='none'&&!source){$('upload-status').textContent='请先上传素材。';return}if(type!=='none'&&!allowedMedia(kind,type)){$('upload-status').textContent='素材文件与分类不匹配，请上传对应文件或保存为纯文本素材。';return}if(kind==='voice'&&type!=='audio'&&type!=='none'){$('upload-status').textContent='请上传音频作为音色素材。';return}if(type==='audio'||type==='video'){const start=Number($('asset-start').value),length=Number($('asset-length').value);if(!Number.isFinite(start)||start<0||start>86400||!Number.isFinite(length)||length<.1||length>30){$('upload-status').textContent='请填写有效的片段起点与时长（0.1–30 秒）。';return}}const previous=plan.assets.find(a=>a.id===editingAsset);const card={...previous,id:editingAsset||kind+'_'+crypto.randomUUID().slice(0,8),kind,name,description:$('asset-description').value,inject_description:$('asset-inject-description').checked,media:type==='none'?[]:[uploadedMedia&&uploadedMedia.source===source?uploadedMedia:previous?.media?.find(m=>m.source===source&&m.type===type)||{type,source},...(previous?.media?.slice(1)||[])]};if(!previous?.text_file||card.description!==previous.description||card.kind!==previous.kind||type!=='none')delete card.text_file;if(previous?.name&&previous.name!==name)card.aliases=[...new Set([...(card.aliases||[]),previous.name])];if(card.media[0]&&card.media[0].type!=='image'){card.media[0].start_seconds=Number($('asset-start').value);card.media[0].duration_seconds=Number($('asset-length').value)}delete card.voice_id;if(kind==='character'&&$('voice').value)card.voice_id=$('voice').value;clearAssetUndo();if(pendingVoice&&card.voice_id===pendingVoice.id)appendAsset(pendingVoice);retireNameAlias(plan,card.name,card.id);const index=plan.assets.findIndex(a=>a.id===card.id);if(index<0)appendAsset(card);else{if(previous.kind!==card.kind){delete card.sequence;const slots=new Set(plan.assets.filter(a=>a.kind===card.kind&&a.id!==card.id).map(a=>a.sequence));let n=1;while(slots.has(n))n++;card.sequence=n}plan.assets[index]=card;}$('asset-dialog').close();draft();render()};
$('asset-submit').onclick=e=>{e.preventDefault();saveAsset()};$('asset-text-submit').onclick=()=>saveAsset(true);
window.addEventListener('message',e=>{
 if(e.origin!==location.origin||e.source!==parent)return;
 if(e.data?.type==='star7-director-open'){const previous=plan;try{const candidate=JSON.parse(e.data.json);if(!candidate||typeof candidate.id!=='string'||!Array.isArray(candidate.assets)||!Array.isArray(candidate.shots))throw Error('项目数据格式无效，已保留原内容');batchSelecting=false;batchSelection.clear();planRevision++;shotStates.clear();generatingShot=null;generatingPhase=null;notice('',false,'open');invalidateStoryboard();document.body.dataset.mode=e.data.mode||'legacy';plan=candidate;selected=Math.max(0,plan.shots.findIndex(s=>s.id===e.data.selectedShot));pipelineFields=e.data.fields||[];drawPipeline();previewUI?.reset();render();initialized=true;$('app').inert=false;if(document.body.dataset.mode!=='library')projectManager?.opened()}catch(error){plan=previous;notice('界面初始化失败：'+error.message,true)}}
 if(e.data?.type==='star7-director-fields'){pipelineFields=e.data.fields||[];if(!$('pipeline-fields').contains(document.activeElement))drawPipeline()}
 if(e.data?.type==='star7-director-library'){invalidateStoryboard();plan.assets=e.data.assets;plan.reference_size=e.data.reference_size;render();promptUI?.refresh();projectManager?.changed();}
 if(e.data?.type==='star7-director-run-snapshot'&&e.data.projectId===plan.id){queuedShots=new Set(e.data.shotIds||[]);}
 if(e.data?.type==='star7-director-progress'){if(e.data.revision!==undefined&&e.data.revision!==planRevision)return;busy=!!e.data.busy;if(!busy)queuedShots.clear();if(busy&&$('storyboard-mode').value==='replace'){$('storyboard-mode').value='append';invalidateStoryboard()}$('storyboard-mode').querySelector('[value="replace"]').disabled=busy;notice(e.data.message,!!e.data.error);$('stop-run').hidden=!busy;for(const id of ['package-import','package-export','export','undo-asset','add-asset','import'])$(id).disabled=busy;render()}
 if(e.data?.type==='star7-director-result'){previewUI?.result(e.data);if(e.data.projectId===plan.id){tailFrameRevision++;renderInputMode()}refreshProcessAvailability()}
 if(e.data?.type==='star7-director-phase')previewUI?.phase(e.data);
 if(e.data?.type==='star7-director-run-accepted'){runSubmitting=false;if(e.data.queued)queuedShots.add(e.data.shotId);render()}
 if(e.data?.type==='star7-director-shot-states'&&e.data.projectId===plan.id&&e.data.revision===planRevision){applyShotStates(e.data.states);}
 if(e.data?.type==='star7-director-batch-state'){const r=e.data;generatingShot=r.status==='running'&&r.phase!=='done'?r.active_shot_id:null;generatingPhase=generatingShot?r.phase:null;drawShots();renderChangeDetails();const busyState=['queued','running'].includes(r.status),changed=busy!==busyState;busy=busyState;if(changed)render();$('stop-run').hidden=!busyState;$('cancel-stop').hidden=!busyState||!r.stop_after;$('stop-policy').hidden=!busyState||!r.stop_after;$('stop-policy').textContent=r.stop_after?'将在 '+r.stop_after+' 完成后停止':'';}
 if(e.data?.type==='star7-director-preview-start')previewUI?.start(e.data);
 if(e.data?.type==='star7-director-live-preview')previewUI?.preview(e.data);
 if(e.data?.type==='star7-director-preview-end')previewUI?.finish(e.data);
});
function drawPreviewSettings(){const target=$('preview-fields');target.replaceChildren();const names={preview_enabled:'启用实时预览',preview_model:'预览模型',preview_fps:'预览帧率',preview_resolution:'预览长边',preview_quality:'WebP 质量',first_step_only:'仅第一步预览'};for(const name of Object.keys(names)){const field=pipelineFields.find(f=>f.nodeId==='preview'&&f.name===name);if(!field)continue;const value=plan.preview?.[name]??field.value,label=node('label',undefined,'pipeline-field'),input=document.createElement(field.choices?'select':'input');input.dataset.preview=name;if(field.choices)input.replaceChildren(...field.choices.filter(v=>v!=='像素插值（Lanczos）').map(v=>{const o=node('option',String(v));o.value=v;return o}));else input.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text';if(input.type==='checkbox'){input.checked=value;label.classList.add('toggle-field')}else input.value=value;if(input.type==='number'){input.min=field.min;input.max=field.max;input.step=field.step||1}input.onchange=()=>{if(!input.reportValidity())return;plan.preview={...plan.preview,[name]:input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value};draft()};label.append(node('span',names[name]),input);target.append(label)}}
function hdTargetArea(resolution){const width=plan.settings?.width||960,height=plan.settings?.height||544,ratio=plan.canvas_profile?.resolution!=='custom'&&plan.canvas_profile?.ratio?plan.canvas_profile.ratio:Math.max(width,height)+':'+Math.min(width,height);const [w,h]=canvasPresetSize(resolution,ratio,width>=height?'landscape':'portrait');return w*h/1e6}
function updateHDTarget(){if(plan.hd_resolution&&plan.hd_resolution!=='custom')plan.generation={...plan.generation,'376':{...plan.generation?.['376'],preset:'自定义',target_megapixels:hdTargetArea(plan.hd_resolution)}}}
function refreshHDResolution(){const select=$('hd-resolution');if(!select)return;const field=pipelineFields.find(f=>f.nodeId==='376'&&f.name==='target_megapixels'),area=Number(plan.generation?.['376']?.target_megapixels??field?.value??2),source=(plan.settings?.width||960)*(plan.settings?.height||544)/1e6;
 for(const option of select.options){if(option.value==='custom'){option.textContent='自定义 · 约'+area.toFixed(2)+' MP';option.disabled=false;continue}const target=hdTargetArea(option.value);option.textContent=(option.value==='2160'?'4K（2160p）':option.value+'p')+' · 约'+target.toFixed(2)+' MP';const reason=target<(field?.min??.2)?'低于二采节点支持的最小目标':target<source-.0001?'低于当前生成尺寸，二采不缩小画面':Math.sqrt(target/source)>4?'超过二采模型支持的4倍放大范围':'';option.disabled=!!reason;option.title=reason}
 select.value=plan.hd_resolution||'custom';$('hd-custom-target').hidden=select.value!=='custom';const customInput=$('hd-custom-target').querySelector('input');if(document.activeElement!==customInput)customInput.value=area;
}
function drawHDResolution(field){const row=node('label',undefined,'pipeline-field'),select=node('select');select.id='hd-resolution';for(const original of $('resolution').options){const option=node('option');option.value=original.value;select.append(option)}row.append(node('span','目标分辨率'),select);$('hd-fields').append(row);
 const custom=node('label',undefined,'pipeline-field'),input=node('input');custom.id='hd-custom-target';input.type='number';input.dataset.parameter='target_megapixels';input.min=field.min??.2;input.max=field.max??36;input.step='any';input.value=plan.generation?.['376']?.target_megapixels??field.value;custom.append(node('span','自定义目标（MP）'),input);$('hd-fields').append(custom,node('small','保持原画面比例；二采不缩小画面。选择分辨率后使用自定义预设。'));
 select.onchange=()=>{plan.hd_resolution=select.value;if(select.value!=='custom'){updateHDTarget();input.value=plan.generation['376'].target_megapixels;const preset=$('hd-fields').querySelector('[data-parameter="preset"]');if(preset)preset.value='自定义'}draft();refreshHDResolution();refreshProcessAvailability()};input.onchange=()=>{if(!input.reportValidity())return;plan.hd_resolution='custom';plan.generation={...plan.generation,'376':{...plan.generation?.['376'],preset:'自定义',target_megapixels:Number(input.value)}};const preset=$('hd-fields').querySelector('[data-parameter="preset"]');if(preset)preset.value='自定义';draft();refreshHDResolution();refreshProcessAvailability()};refreshHDResolution();
}
const exportDefaults={format:'h264-mp4',frame_rate:0,quality_mode:'crf',crf:19,bitrate_mbps:8,pix_fmt:'yuv420p',preset:'medium',include_audio:true,audio_bitrate_kbps:192,save_metadata:false};
function drawExportSettings(){
 const values={...exportDefaults,...plan.export_settings},labels={format:'视频格式',frame_rate:'导出帧率（0 = 保持源帧率）',quality_mode:'视频质量控制',crf:'CRF（越低质量越高）',bitrate_mbps:'视频目标码率 / Mbps',pix_fmt:'像素格式',preset:'编码速度',include_audio:'保留音频',audio_bitrate_kbps:'音频码率 / kbps',save_metadata:'写入镜头参数元数据'},choices={format:[['h264-mp4','H.264 · MP4（默认）'],['h265-mp4','H.265 · MP4'],['vp9-webm','VP9 · WebM']],quality_mode:[['crf','恒定质量 CRF'],['bitrate','目标码率']],pix_fmt:[['yuv420p','YUV420P（默认，兼容性好）'],['yuv444p','YUV444P']],preset:[['fast','快速'],['medium','中等（默认）'],['slow','慢速']]},limits={frame_rate:[0,120,.001],crf:[0,51,1],bitrate_mbps:[.1,200,.1],audio_bitrate_kbps:[32,320,1]};
 $('export-fields').replaceChildren();
 for(const [key,value] of Object.entries(values)){if(!(key in exportDefaults))continue;const label=node('label',undefined,'pipeline-field'),input=document.createElement(choices[key]?'select':'input');input.dataset.exportSetting=key;
  if(choices[key])input.replaceChildren(...choices[key].map(([v,text])=>{const o=node('option',text);o.value=v;return o}));else input.type=typeof value==='boolean'?'checkbox':'number';
  if(input.type==='checkbox'){input.checked=value;label.classList.add('toggle-field')}else input.value=value;
  if(limits[key]){[input.min,input.max,input.step]=limits[key]}
  input.disabled=key==='crf'&&values.quality_mode!=='crf'||key==='bitrate_mbps'&&values.quality_mode!=='bitrate'||key==='audio_bitrate_kbps'&&!values.include_audio;
  input.onchange=()=>{if(!input.reportValidity())return;plan.export_settings={...values,[key]:input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value};draft();drawExportSettings()};label.append(node('span',labels[key]),input);$('export-fields').append(label);
 }
}
$('export-reset').onclick=()=>{delete plan.export_settings;draft();drawExportSettings()};
function drawPipeline(){
 const hdCfg=plan.generation?.['376'];if(hdCfg){delete hdCfg.upscale_method;if(hdCfg.upscale_model==='像素插值（Lanczos）')hdCfg.upscale_model=pipelineFields.find(f=>f.nodeId==='376'&&f.name==='upscale_model')?.value||'minimax_h3_latent_upscaler_3d_fp16.safetensors'}
 for(const group of ['sampling','hd','face'])$(group+'-fields').replaceChildren();drawPreviewSettings();drawExportSettings();
 const names={sampler_name:'采样器',scheduler:'调度方式',steps:'采样步数',denoise:'去噪强度',upscale_model:'放大模型',second_pass_lora:'二采 LoRA',second_pass_lora_strength:'二采 LoRA 强度',second_pass_attention:'二采注意力',preset:'预设',target_megapixels:'目标像素（MP）',refine_steps:'精修步数',refine_strength:'精修强度',enable_tiling:'启用分格',tile_count:'分格数量',tile_overlap:'分格重叠',face_detector:'人脸检测模型',face_lora:'修脸 LoRA',face_lora_strength:'修脸 LoRA 强度',face_attention:'修脸注意力',face_count:'修复人数',target_face:'目标人脸',custom_strength:'修脸强度',custom_canvas:'修脸尺寸',custom_crop_context:'裁剪上下文',custom_blend:'融合强度',custom_feather:'边缘羽化',preserve_repair_detail:'保留修复细节'};
 const groups={'126':'sampling','308':'sampling','376':'hd','395':'face'};
 for(const field of pipelineFields.filter(f=>f.internal&&groups[f.nodeId]&&f.name!=='upscale_method')){
  if(field.nodeId==='376'&&field.name==='target_megapixels'){drawHDResolution(field);continue}
  const label=node('label',undefined,'pipeline-field'),input=document.createElement(field.choices?'select':'input');
  const value=plan.generation?.[field.nodeId]?.[field.name]??field.value;
  if(field.choices)input.replaceChildren(...field.choices.filter(v=>v!=='像素插值（Lanczos）').map(v=>{const option=node('option',String(v));option.value=v;return option}));else input.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text';
  if(input.type==='checkbox')input.checked=value;else input.value=value;
  if(input.type==='number'){input.step=field.step??'any';if(field.min!==undefined)input.min=field.min;if(field.max!==undefined)input.max=field.max;}
  input.dataset.parameter=field.name;
  input.onchange=()=>{if(!input.reportValidity())return;const value=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;plan.generation={...plan.generation,[field.nodeId]:{...plan.generation?.[field.nodeId],[field.name]:value}};if(field.nodeId==='376'&&field.name==='preset'&&value!=='自定义'){delete plan.hd_resolution;refreshHDResolution()}if(groups[field.nodeId]==='sampling'){plan.generation_preset='custom';$('preset').value='custom'}draft();refreshProcessAvailability();if(field.nodeId==='376'&&field.name==='upscale_model')drawPipeline()};
  if(input.type==='checkbox')label.classList.add('toggle-field');label.append(node('span',names[field.name]||field.name),input);$(groups[field.nodeId]+'-fields').append(label);
 }
 for(const group of ['sampling','hd','face'])if(!$(group+'-fields').children.length)$(group+'-fields').append(node('small','连接导演台节点后加载可用参数。'));

}
function renderNextSeed(shot){$('next-seed-note').textContent=shot?.next_seed!==undefined&&shot?.seed_control!=='fixed'?'下次重新生成：'+shot.next_seed:''}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent||e.data?.type!=='star7-director-seed-state')return;const shot=plan.shots.find(s=>s.id===e.data.shotId);if(!shot)return;shot.seed=e.data.seed;shot.next_seed=e.data.nextSeed;if(plan.shots[selected]?.id===shot.id){$('seed').value=shot.seed;renderNextSeed(shot)}if(e.data.modifiedAt)plan.modified_at=e.data.modifiedAt;projectManager?.changed();refreshProcessAvailability();});
function refreshProcessAvailability(){
 clearTimeout(processTimer);const requestId=++processCheck,shot=plan.shots[selected];processReady=false;exportReady=false;const key=shot?plan.id+'/'+shot.id:null;if(key!==statusShotKey){statusShotKey=key;processUnavailableReason='';setStale(false)}$('export-shot').disabled=true;$('process-one').disabled=true;$('process-one').title='需要先生成当前镜头，且缓存与当前参数匹配';
 if(!shot||parent===window||document.body.dataset.mode==='library')return;
 processNoticeEpoch=noticeEpoch;processTimer=setTimeout(()=>parent.postMessage({type:'star7-director-check-process',plan:structuredClone(plan),shotId:shot.id,requestId},location.origin),250);
}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent||e.data?.type!=='star7-director-process-ready'||e.data.requestId!==processCheck)return;processUnavailableReason=e.data.reason||'';processReady=!!e.data.ready;exportReady=!!e.data.exportReady;if(e.data.states)applyShotStates(e.data.states);if(e.data.stale!==undefined)setStale(!!e.data.stale,processNoticeEpoch===noticeEpoch,!!e.data.preservesPost);$('export-shot').disabled=!exportReady;$('process-one').disabled=runSubmitting||(!busy&&!processReady&&!processUnavailableReason.includes('缓存已清除'));$('process-one').title=e.data.reason||'使用当前镜头的基础缓存进行二采／修脸'});
function run(scope,shotIds=[]){if(runSubmitting)return;if(scope==='process'&&!busy&&!processReady){notice(processUnavailableReason||'没有匹配的基础生成缓存，请先生成当前镜头。',true);return}if(importing){notice('请等待素材导入完成。',true);return}if(parent===window){notice('请从 ComfyUI 的导演台节点打开面板后生成。',true);return}draft();const requestPlan=structuredClone(plan),shotId=plan.shots[selected]?.id;if(!busy)queuedShots=new Set((scope==='all'?plan.shots:plan.shots.filter(s=>scope==='selected'?shotIds.includes(s.id):s.id===shotId)).map(s=>s.id));runSubmitting=true;busy=true;$('stop-run').hidden=false;render();parent.postMessage({type:'star7-director-run',plan:requestPlan,scope,shotId,shotIds},location.origin)}
$('run-one').onclick=()=>run('one');$('process-one').onclick=()=>{if(!busy&&!processReady&&processUnavailableReason.includes('缓存已清除')){notice(processUnavailableReason,true);return}if(!$('hd').checked&&!$('face').checked){notice('请先勾选当前镜头需要的二采或修脸。',true);return}run('process')};$('run-all').onclick=()=>run('all');$('stop-run').onclick=()=>parent.postMessage({type:'star7-director-stop',shotId:plan.shots[selected]?.id},location.origin);$('cancel-stop').onclick=()=>parent.postMessage({type:'star7-director-stop',cancel:true},location.origin);
function detectedMedia(file){
 const extension=file.name.split('.').pop().toLowerCase();
 if(['png','jpg','jpeg','webp','bmp'].includes(extension))return 'image';
 if(['wav','mp3','flac','ogg','m4a'].includes(extension))return 'audio';
 if(['mp4','mov','webm','mkv'].includes(extension))return 'video';
 return null;
}
function knownMaterials(excludeId=null){return plan.assets.filter(a=>a.id!==excludeId).flatMap(a=>[...(a.media||[]),...(a.text_file?[a.text_file]:[])].map(m=>({...m,asset_name:a.name}))) }
const normalizeFileName=name=>String(name||'').normalize('NFC').toLocaleLowerCase();
async function uploadFile(file,type){
 if(file.size>512*1024**2)throw Error('素材超过 512 MiB 上限');
 const exclude=$('asset-dialog').open?editingAsset:null,known=knownMaterials(exclude);
 const base=file.name.replace(/\.[^.]+$/,'');
 const sameName=known.find(m=>normalizeFileName(m.original_name||m.source?.split('/').pop())===normalizeFileName(file.name))||plan.assets.find(a=>a.id!==exclude&&normalizeFileName(a.name)===normalizeFileName(base));
 if(sameName)throw Error('已有该素材：'+(sameName.asset_name||sameName.name||file.name));
 if(file.size<=16*1024**2&&crypto.subtle){const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(v=>v.toString(16).padStart(2,'0')).join('');const duplicate=known.find(m=>m.content_hash===hash);if(duplicate)throw Error('已有该素材：'+duplicate.asset_name)}
 const data=new FormData();data.append('kind',type);data.append('known_media',JSON.stringify(known));data.append('file',file);
 const response=await fetch('/star7/director/upload',{method:'POST',body:data});const value=await response.json();if(!response.ok)throw Error(value.error||'上传失败');return value;
}
async function uploadToCard(file){
 if(/\.txt$/i.test(file.name)){try{const text=await readText(file);if(!$('asset-dialog').open)return;uploadedMedia=null;$('asset-description').value=text;$('asset-media').value='none';$('asset-source').value='';drawAssetEditor();$('upload-status').textContent='已读取描述，请点击「保存纯文本素材」。'}catch(e){$('upload-status').textContent=e.message}return}let type=detectedMedia(file);if(!type){$('upload-status').textContent='不支持的素材格式';return}

 if($('asset-kind').value==='voice'&&type!=='audio'){$('upload-status').textContent='音色素材请上传音频。';return}
 if(!allowedMedia($('asset-kind').value,type)){$('upload-status').textContent='文件格式与所选分类不匹配';return}$('asset-media').value=type;assetUploading=true;for(const id of ['asset-submit','asset-text-submit','asset-kind','asset-upload-button','voice-upload-button'])$(id).disabled=true;$('upload-status').textContent='上传中…';
 try{uploadedMedia=await uploadFile(file,type);$('asset-source').value=uploadedMedia.source;if(!$('asset-name').value)$('asset-name').value=nextAssetName($('asset-kind').value);$('upload-status').textContent='已上传：'+uploadedMedia.original_name;drawAssetEditor()}catch(e){$('upload-status').textContent='上传失败：'+e.message}finally{assetUploading=false;for(const id of ['asset-submit','asset-text-submit','asset-kind','asset-upload-button','voice-upload-button'])$(id).disabled=false}
}
$('asset-upload').onchange=async()=>{const file=$('asset-upload').files[0];if(file)await uploadToCard(file)};

drawPipeline();
render();

$('asset-kind').onchange=()=>{if(!$('asset-source').value){const kind=$('asset-kind').value;$('asset-media').value=kind==='voice'?'audio':kind==='video'?'video':kind==='effect'?'none':'image'}drawAssetEditor()};
$('voice-upload').onchange=async()=>{
 const file=$('voice-upload').files[0];if(!file||assetUploading)return;
 if(detectedMedia(file)!=='audio'){$('upload-status').textContent='音色请上传音频文件，不支持视频。';return}
 assetUploading=true;for(const id of ['asset-submit','asset-text-submit','asset-kind','asset-upload-button','voice-upload-button'])$(id).disabled=true;$('upload-status').textContent='音色上传中…';
 try{
  const media=await uploadFile(file,'audio');media.start_seconds=0;media.duration_seconds=6;
  if(!$('asset-dialog').open)return;
  pendingVoice={id:'voice_'+crypto.randomUUID().slice(0,8),kind:'voice',name:nextAssetName('voice'),description:'',media:[media]};
  drawVoiceOptions(pendingVoice.id);$('upload-status').textContent='已上传音色：'+media.original_name+'；保存素材后绑定。';
 }catch(e){$('upload-status').textContent='音色上传失败：'+e.message}finally{assetUploading=false;for(const id of ['asset-submit','asset-text-submit','asset-kind','asset-upload-button','voice-upload-button'])$(id).disabled=false;$('voice-upload').value=''}
};
$('global-settings').onclick=()=>{$('global-dialog').showModal();$('project-current-name').value=plan.title||'';projectManager?.refresh();parent.postMessage({type:'star7-director-refresh-fields'},location.origin)};
$('global-close').onclick=()=>$('global-dialog').close();

$('asset-close').onclick=()=>$('asset-dialog').close();
$('asset-dialog').onclose=()=>{if($('asset-dialog').open)return;for(const media of $('asset-dialog').querySelectorAll('audio,video'))media.pause();pendingVoice=null;uploadedMedia=null;editingAsset=null};

let currentExportPending=false;
$('export-shot').onclick=async()=>{if(currentExportPending||!exportReady||!plan.shots[selected])return;currentExportPending=true;const current=structuredClone(plan),shot=current.shots[selected];try{const directory=await chooseDirectory();if(directory.native){notice('请选择视频保存目录…');notice(await saveNative({scope:'one',project_id:current.id,shot_id:shot.id,export_settings:current.export_settings||{},title:current.title,shot}));return}notice('正在将当前镜头保存到所选目录…');const response=await fetch('/star7/director/download-current/'+encodeURIComponent(current.id)+'/'+encodeURIComponent(shot.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({export_settings:current.export_settings||{},title:current.title,shot})});const disposition=response.headers.get('Content-Disposition')||'',encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i);const filename=encoded?decodeURIComponent(encoded[1]):shot.id+'.mp4';await saveResponse(directory,filename,response);notice('当前镜头已下载到：'+directory.name+'。原视频保留，未在导出目录新增副本。')}catch(error){notice(error.name==='AbortError'?'已取消选择目录':error.message,error.name!=='AbortError')}finally{currentExportPending=false}};
$('export-segments').onclick=()=>{if(parent===window){notice('请从 ComfyUI 导演台中导出。',true);return}parent.postMessage({type:'star7-director-export-segments',plan:structuredClone(plan)},location.origin)};
$('combine').onclick=()=>{if(parent===window){notice('请从 ComfyUI 导演台中合并。',true);return}parent.postMessage({type:'star7-director-combine',plan:JSON.parse(JSON.stringify(plan))},location.origin)};

$('apply-continuity').onclick=()=>{if(importing||!plan.shots.length)return;const mode=$('continuity').value,frame=Number($('frame-index').value);if(mode==='selected_frame'&&(!Number.isInteger(frame)||frame<0)){$('frame-index').reportValidity();notice('参考帧序号必须是非负整数。',true);return}clearShotUndo();plan.shots.forEach((shot,i)=>{shot.continuity=changeContinuity(plan,shot,!i?'independent':mode,plan.shots[i-1]?.id,frame,true)});draft();render();notice(mode==='independent'?'已将全部镜头设为独立镜头。':'已应用到全部镜头，首个镜头保持独立，后续镜头依次延续前一镜头。')};
$('apply-all').onclick=()=>{if(importing)return;clearShotUndo();for(const shot of plan.shots)shot.post={...shot.post,hd:$('hd').checked,face:$('face').checked};draft();refreshProcessAvailability();notice('已将二采与修脸设置应用到全部镜头。')};
$('preset').onchange=()=>{const preset=$('preset').value;plan.generation_preset=preset;if(preset!=='custom'){plan.generation={...plan.generation,'126':{scheduler:'simple',steps:preset==='detail'?8:4,denoise:1},'308':{sampler_name:'euler'}};for(const f of pipelineFields)if(f.internal&&plan.generation?.[f.nodeId]?.[f.name]!==undefined)f.value=plan.generation[f.nodeId][f.name];drawPipeline()}draft();refreshProcessAvailability()};

$('package-export').onclick=()=>{if(!busy)parent.postMessage({type:'star7-director-package-export',plan:JSON.parse(JSON.stringify(plan))},location.origin)};
$('package-import').onclick=()=>{if(!busy)$('package-file').click()};
async function importPackage(file){
 try{notice('正在导入项目包…');const response=await fetch('/star7/director/package/import',{method:'POST',headers:{'Content-Type':'application/zip','X-Star7-Package-Name':encodeURIComponent(file.name)},body:file});const result=await response.json();if(!response.ok)throw Error(result.error);parent.postMessage({type:'star7-director-package-import',workflow:result.workflow},location.origin)}catch(e){notice('导入失败：'+e.message,true)}
}
$('package-file').onchange=async()=>{const file=$('package-file').files[0];if(file&&!busy&&!importing){importing=true;try{await importPackage(file)}finally{importing=false}}$('package-file').value=''};

function uniqueAssetName(base){
 const used=new Set(plan.assets.flatMap(a=>[a.id,a.name,...(a.aliases||[])]));let name=base||'素材',n=2;
 while(used.has(name))name=(base||'素材')+' '+n++;return name;
}
async function importMediaFiles(files){
 const targetCategory=category;let added=0;const failed=[];
 for(const file of files){
  const detected=detectedMedia(file);if(!detected){if(/\.txt$/i.test(file.name)){try{await importText(file,targetCategory);added++}catch(e){failed.push(file.name+'：'+e.message)}continue}failed.push(file.name+'：不支持的格式');continue}
  const kind=targetCategory!=='all'?targetCategory:detected==='audio'?'voice':detected==='video'?'video':'character';
  const type=detected;
  if(!allowedMedia(kind,type)){failed.push(file.name+'：文件格式与所选分类不匹配');continue}
  notice(`正在导入 ${file.name}…`);
  try{
   const media=await uploadFile(file,type);if(type!=='image'){media.start_seconds=0;media.duration_seconds=6}
   clearAssetUndo();appendAsset({id:kind+'_'+crypto.randomUUID().slice(0,8),kind,name:nextAssetName(kind),description:'',media:[media]});added++;draft();render();
  }catch(e){failed.push(file.name+'：'+e.message)}
 }
 notice(`已添加 ${added} 个素材。`+(failed.length?' 未导入：'+failed.join('；'):''),!!failed.length);
}
const isFileDrag=e=>!e.target.closest?.('[data-keyframe-slot],#storyboard-dialog')&&!draggedAsset&&!Array.from(e.dataTransfer?.types||[]).includes('application/x-star7-director-asset')&&Array.from(e.dataTransfer?.types||[]).includes('Files');let dragDepth=0;
const clearDrop=()=>{dragDepth=0;document.body.classList.remove('drop-active')};
document.addEventListener('dragenter',e=>{if(!isFileDrag(e))return;e.preventDefault();e.stopPropagation();dragDepth++;if(!busy&&!importing)document.body.classList.add('drop-active')},true);
document.addEventListener('dragover',e=>{if(!isFileDrag(e))return;e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect=busy||importing?'none':'copy'},true);
document.addEventListener('dragleave',e=>{if(!isFileDrag(e))return;if(--dragDepth<=0)clearDrop()},true);
document.addEventListener('drop',async e=>{
 if(!isFileDrag(e))return;e.preventDefault();e.stopPropagation();clearDrop();
 if(busy||importing){notice('当前操作完成后再导入。',true);return}
 const files=Array.from(e.dataTransfer.files);if(!files.length)return;
 const config=files.filter(f=>/\.(zip|json)$/i.test(f.name));
 if(config.length&&(files.length!==1)){notice('项目包或 JSON 请单独拖入，素材文件可以批量拖入。',true);return}
 importing=true;$('add-asset').disabled=true;
 try{
  if(config.length){if(/\.zip$/i.test(config[0].name))await (document.body.dataset.mode==='library'?importLibrary(config[0]):importPackage(config[0]));else await importDocument(config[0])}
  else if($('asset-dialog').open){if(files.length!==1)notice('编辑素材卡时请一次拖入一个文件。',true);else await uploadToCard(files[0])}
  else await importMediaFiles(files);
 }finally{importing=false;$('add-asset').disabled=busy;render();clearDrop()}
},true);
window.addEventListener('blur',clearDrop);

window.addEventListener("blur",clearAssetDrag);

function allowedMedia(kind,type){return kind==='voice'?type==='audio':kind==='video'?type==='video':kind==='effect'?['audio','video'].includes(type):type==='image'}
async function readText(file){if(file.size>1024*1024)throw Error('文字素材超过 1 MiB');const bytes=new Uint8Array(await file.arrayBuffer());let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{throw Error('文字素材请使用 UTF-8 编码 TXT')}if(!text.trim()||text.includes('\0'))throw Error('文字素材为空或格式无效');return text}
async function importText(file,kind=category){const name=file.name.replace(/\.txt$/i,'');if(plan.assets.some(a=>normalizeFileName(a.original_name||a.name)===normalizeFileName(file.name)))throw Error('已有该素材：'+name);const description=await readText(file);clearAssetUndo();appendAsset({id:kind+'_'+crypto.randomUUID().slice(0,8),kind,name:nextAssetName(kind),original_name:file.name,description,media:[]});draft();render()}
$('library-import').onclick=()=>{if(!busy&&!importing)$('library-file').click()};
$('library-file').onchange=async()=>{const file=$('library-file').files[0];if(file&&!busy&&!importing){importing=true;try{await importLibrary(file)}finally{importing=false;render()}}$('library-file').value=''};
async function importLibrary(file){try{notice('正在校验并导入素材库…');const data=new FormData();data.append('library',JSON.stringify({name:plan.library_name||'素材库',sequences:plan.asset_sequences,reference_size:plan.reference_size,assets:plan.assets}));data.append('file',file);const response=await fetch('/star7/director/library/import?category='+encodeURIComponent(category),{method:'POST',body:data});const result=await response.json();if(!response.ok)throw Error(result.error);for(const card of result.assets)retireNameAlias(plan,card.name,card.id);plan.assets=result.assets;plan.library_name=result.name;plan.asset_sequences=result.sequences;plan.reference_size=result.reference_size||plan.reference_size;clearAssetUndo();draft();render();notice(result.message)}catch(e){notice('素材库导入失败：'+e.message,true)}}
$('library-export').onclick=async()=>{if(busy||importing)return;try{const response=await fetch('/star7/director/library/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:plan.library_name||'素材库',sequences:plan.asset_sequences,reference_size:plan.reference_size,assets:plan.assets})});if(!response.ok)throw Error((await response.json()).error);const url=URL.createObjectURL(await response.blob()),a=node('a');a.href=url;const stamp=new Date().toISOString().replace(/[-:]/g,'').replace('T','_').slice(0,15);a.download=(plan.library_name||'素材库').replace(/[<>:"/\\|?*]/g,'_')+'_'+stamp+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('素材库已导出。')}catch(e){notice('导出失败：'+e.message,true)}};

function ensureAssetSequences(){plan.asset_sequences={};for(const kind of Object.keys(kinds)){const used=initializeMaterialSlots(plan.assets,kind,kinds[kind]);plan.asset_sequences[kind]=Math.max(0,...used)}}
function nextAssetName(kind){return nextMaterialName(plan.assets,kinds[kind],kind)}
function appendAsset(card){ensureAssetSequences();const slots=new Set(plan.assets.filter(a=>a.kind===card.kind).map(a=>a.sequence));let n=1;while(slots.has(n))n++;card.sequence=n;retireNameAlias(plan,card.name,card.id);plan.assets.push(card)}

const formatBytes=value=>{const n=Number(value)||0;if(n<1024)return n+' B';if(n<1024**2)return (n/1024).toFixed(1)+' KiB';if(n<1024**3)return (n/1024**2).toFixed(1)+' MiB';return (n/1024**3).toFixed(2)+' GiB'};
function assetSources(value){if(!value||typeof value!=='object')return [];if(Array.isArray(value))return value.flatMap(assetSources);return Object.entries(value).flatMap(([key,item])=>['source','thumbnail_source'].includes(key)&&typeof item==='string'?[item]:assetSources(item))}
let workflowSources=[],cacheClearing=false;const cacheContextRequests=new Map();
function refreshCacheSources(){if(parent===window){workflowSources=[];return Promise.resolve()}return new Promise((resolve,reject)=>{const requestId=crypto.randomUUID(),timer=setTimeout(()=>{cacheContextRequests.delete(requestId);reject(Error('无法确认工作流素材引用，请刷新页面后再清理。'))},5000);cacheContextRequests.set(requestId,{resolve:()=>{clearTimeout(timer);resolve()}});parent.postMessage({type:'star7-director-cache-context',requestId},location.origin)})}
function cacheSources(){return [...new Set([...workflowSources,...assetSources(plan.assets)])]}
function drawCache(value){renderCache($('cache-dialog'),value,{library:document.body.dataset.mode==='library',project:plan,busy:cacheClearing,formatBytes,onClear:clearCache})}

async function loadCache(){try{const response=await fetch('/star7/director/cache/'+encodeURIComponent(plan.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({active_sources:cacheSources()})});const value=await response.json();if(!response.ok)throw Error(value.error);drawCache(value);$('cache-notice').textContent=''}catch(e){$('cache-notice').textContent=e.message}}
async function openCache(){$('cache-dialog').showModal();$('cache-notice').textContent='正在统计…';try{await refreshCacheSources();await loadCache()}catch(e){$('cache-notice').textContent=e.message}}
window.addEventListener('message',e=>{if(e.origin===location.origin&&e.source===parent&&e.data?.type==='star7-director-cache-context'){workflowSources=e.data.sources||[];const request=cacheContextRequests.get(e.data.requestId);if(request){cacheContextRequests.delete(e.data.requestId);request.resolve()}}});
$('cache-settings').onclick=openCache;$('global-cache-settings').onclick=openCache;$('cache-close').onclick=()=>$('cache-dialog').close();
async function clearCache(kind,package_id=null,project_ids=null){if(cacheClearing)return;cacheClearing=true;for(const button of $('cache-dialog').querySelectorAll('.cache-actions button,.package-cache-row button,#cache-select-all,#cache-stage,[data-cache-project]'))button.disabled=true;try{await refreshCacheSources();const response=await fetch('/star7/director/cache/'+encodeURIComponent(plan.id)+'/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,package_id,project_ids,stages:$('cache-stage').value==='all'?null:[$('cache-stage').value],active_sources:cacheSources()})});const value=await response.json();if(!response.ok)throw Error(value.error);cacheClearing=false;drawCache(value);refreshProcessAvailability();$('cache-notice').textContent='已释放 '+formatBytes(value.freed_bytes)+(kind==='selected_checkpoints'?'。选中项目辅助缓存已清除，视频和素材保留。':kind==='checkpoints'?'。当前项目缓存已清除，重新生成镜头后可重新建立二采／修脸缓存；视频和素材保留。':kind==='other_checkpoints'?'。其他项目辅助缓存已清除，当前项目、全部视频和素材保留。':'')}catch(e){cacheClearing=false;await loadCache();$('cache-notice').textContent=e.message}finally{cacheClearing=false}}
$('cache-clear-selected').onclick=()=>{const ids=[...$('cache-sizes').querySelectorAll('[data-cache-project]:checked')].map(el=>el.dataset.cacheProject);if(ids.length)clearCache('selected_checkpoints',null,ids)};
$('cache-clear-other').onclick=()=>clearCache('other_checkpoints');$('cache-clear-temp').onclick=()=>clearCache('packages');$('cache-clear-latent').onclick=()=>clearCache('checkpoints');

function promptAssets(){
 const shot=plan.shots[selected],smart=shot?.input_mode==='keyframes';
 const assets=plan.assets.map(a=>({...a,disabled:smart&&a.media?.some(m=>['image','video'].includes(m.type))}));
 const virtual=(id,name,referenceToken,disabled)=>({id,name,referenceToken,kind:'continuity',virtual:true,disabled});
 if(smart)return [...assets,virtual('__star7_first_frame__','首帧','@{首帧}',!shot.keyframes?.first),virtual('__star7_last_frame__','尾帧','@{尾帧}',!shot.keyframes?.last)];
 return [...assets,...(shot?.continuity?.mode==='selected_frame'?[virtual('__star7_selected_frame__','参考帧','@{参考帧}',!selected)]:[virtual('__star7_tail_frame__','尾帧参考','@{尾帧参考}',!selected||shot?.continuity?.mode!=='tail_reference')])];
}
promptUI=mountPrompt({source:$('prompt'),editor:$('prompt-editor'),menu:$('mentions'),getAssets:promptAssets,mediaURL,onEditAsset:editAsset});

layoutUI=mountLayout({preview:$('shot-preview'),prompt:$('prompt-editor'),handle:$('preview-resize'),getPlan:()=>plan,onChange:draft,isBusy:()=>false});
previewUI=mountShotPreview({video:$('result-video'),image:$('live-preview'),empty:$('preview-empty'),status:$('live-status'),framePosition:$('frame-position'),infoLabel:$('preview-info'),phaseLabel:$('generation-phase'),getPlan:()=>plan,getShot:()=>plan.shots[selected],request:data=>{if(parent!==window)parent.postMessage({type:'star7-director-get-result',...data},location.origin)}});previewUI.show();

let referenceMode='long_edge';
const referenceDefaults={mode:'long_edge',image_long_edge:1600,video_long_edge:800,image_mp:1.5,video_mp:0.5};
function referenceModeView(mode){referenceMode=mode;$('reference-edge-fields').hidden=mode!=='long_edge';$('reference-mp-fields').hidden=mode!=='megapixels';$('reference-mode-edge').classList.toggle('primary',mode==='long_edge');$('reference-mode-mp').classList.toggle('primary',mode==='megapixels')}
$('reference-settings').onclick=()=>{const value={...referenceDefaults,...plan.reference_size};$('reference-image-edge').value=value.image_long_edge;$('reference-video-edge').value=value.video_long_edge;$('reference-image-mp').value=value.image_mp;$('reference-video-mp').value=value.video_mp;referenceModeView(value.mode);$('reference-error').textContent='';$('reference-dialog').showModal()};
$('reference-mode-edge').onclick=()=>referenceModeView('long_edge');$('reference-mode-mp').onclick=()=>referenceModeView('megapixels');$('reference-close').onclick=()=>$('reference-dialog').close();
$('reference-save').onclick=()=>{const ids=referenceMode==='long_edge'?['reference-image-edge','reference-video-edge']:['reference-image-mp','reference-video-mp'];if(ids.some(id=>!$(id).reportValidity()))return;const value={mode:referenceMode,image_long_edge:Number($('reference-image-edge').value),video_long_edge:Number($('reference-video-edge').value),image_mp:Number($('reference-image-mp').value),video_mp:Number($('reference-video-mp').value)};plan.reference_size=value;draft();$('reference-dialog').close();notice('参考素材尺寸已应用，下次生成时生效。')};

function renderContinuitySettings(){const cfg=plan.continuity_settings||{};$('context-frames').value=String(cfg.context_frames??22);$('context-audio').checked=cfg.audio??true;$('context-redraw').value=cfg.redraw??.65;$('context-drift').checked=cfg.drift_control??false;$('context-drift-strength').value=cfg.drift_strength??.3}
for(const id of ['context-frames','context-audio','context-redraw','context-drift','context-drift-strength'])$(id).onchange=()=>{if(!$(id).reportValidity())return;plan.continuity_settings={...plan.continuity_settings,drift_control:$('context-drift').checked,drift_strength:Number($('context-drift-strength').value),context_frames:Number($('context-frames').value),audio:$('context-audio').checked,redraw:Number($('context-redraw').value)};draft();refreshProcessAvailability()};

function invalidateStoryboard(){const hadPreview=storyboardCandidate!==null||storyboardChecking;storyboardCandidate=null;storyboardToken++;$('storyboard-apply').disabled=true;if(hadPreview||$('storyboard-dialog').open){$('storyboard-summary').textContent='内容或项目已修改，请重新识别。';$('storyboard-preview').replaceChildren()}}
$('import-storyboard').onclick=()=>{if(importing)return;if(busy)$('storyboard-mode').value='append';$('storyboard-dialog').showModal();$('storyboard-text').focus()};$('storyboard-close').onclick=()=>$('storyboard-dialog').close();
$('storyboard-text').oninput=invalidateStoryboard;$('storyboard-mode').onchange=invalidateStoryboard;
let storyboardFileToken=0;
async function readStoryboardFile(file){const token=++storyboardFileToken;if(!file)return;try{if(file.size>1024*1024)throw Error('分镜文件超过 1 MiB');if(!/\.(json|txt|md)$/i.test(file.name))throw Error('请选择 JSON、TXT 或 Markdown 分镜文件；项目 ZIP 请在项目设置中导入');const text=await file.text();if(token!==storyboardFileToken)return;$('storyboard-text').value=text;invalidateStoryboard();$('storyboard-summary').textContent='已读取 '+file.name+'，请点击“识别并检查”。';$('storyboard-summary').classList.remove('error');}catch(e){$('storyboard-summary').textContent=e.message;$('storyboard-summary').classList.add('error')}}
$('storyboard-upload').onclick=()=>$('storyboard-file').click();$('storyboard-file').onchange=()=>{readStoryboardFile($('storyboard-file').files[0]);$('storyboard-file').value=''};
$('storyboard-dialog').addEventListener('dragover',e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();$('storyboard-text').classList.add('file-hover')}});
$('storyboard-dialog').addEventListener('dragleave',()=>$('storyboard-text').classList.remove('file-hover'));
$('storyboard-dialog').addEventListener('drop',e=>{if(!e.dataTransfer.files.length)return;e.preventDefault();e.stopPropagation();$('storyboard-text').classList.remove('file-hover');if(e.dataTransfer.files.length!==1){$('storyboard-summary').textContent='请一次拖入一个分镜文件';return}readStoryboardFile(e.dataTransfer.files[0])});
$('storyboard-example').onclick=()=>{
 $('storyboard-example-code').textContent=JSON.stringify({shots:[{duration:10,mode:'I',prompt:'独立建立新场景，描述人物、环境、构图与完整动作。素材使用 @{素材名称}。'},{duration:10,mode:'R',prompt:'接续前段的动作与运动方向，描述这一段的新进展。'},{duration:8,mode:'F',prompt:'以 @{尾帧参考} 保持人物和环境状态，明确描述这一段的新机位、背景方向与动作。'}]},null,2);
 $('storyboard-frame-example-code').textContent=JSON.stringify({shots:[{duration:8,mode:'S',first_frame:'@{起始图片}',prompt:'从 @{首帧} 开始，镜头缓慢推进。'},{duration:8,mode:'E',last_frame:'@{结束图片}',prompt:'描述动作过程，最终到达 @{尾帧} 的画面。'},{duration:10,mode:'SE',first_frame:'@{起始图片}',last_frame:'@{结束图片}',prompt:'从 @{首帧} 平滑发展到 @{尾帧}，描述中间的动作。'}]},null,2);
 $('storyboard-example-dialog').showModal();
};$('storyboard-example-close').onclick=()=>$('storyboard-example-dialog').close();

$('storyboard-recognize').onclick=async()=>{if(storyboardChecking||importing)return;invalidateStoryboard();const token=storyboardToken;storyboardChecking=true;$('storyboard-recognize').disabled=true;$('storyboard-summary').textContent='正在识别并检查引用…';try{const response=await fetch('/star7/director/storyboard/recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan,text:$('storyboard-text').value,mode:$('storyboard-mode').value})});const result=await response.json();if(token!==storyboardToken)return;if(!response.ok)throw Error(result.error||'识别失败');const summary=`识别 ${result.count} 个镜头 · 总时长 ${Number(result.total_duration.toFixed(3))} 秒 · ${result.mode==='replace'?'替换现有 '+plan.shots.length+' 个镜头':'追加到现有镜头'}`;$('storyboard-summary').textContent=summary+(result.errors.length?' · '+result.errors.length+' 处问题，请修正后再导入':' · 检查通过')+(result.warnings.length?'\n'+result.warnings.join('；'):'');$('storyboard-summary').classList.toggle('error',!result.valid);$('storyboard-preview').replaceChildren();for(const row of result.rows){const card=node('article',undefined,'recognized-shot'+(row.valid?'':' error'));card.append(node('b',row.name+' · '+(row.duration??'?')+' 秒 · '+(row.input_mode==='keyframes'?(row.keyframes.first&&row.keyframes.last?'SE 首尾帧':row.keyframes.first?'S 首帧':'E 尾帧'):row.continuity?.mode==='tail_reference'?'F 尾帧画面参考':row.continuity?.mode==='motion_redraw'?'运动引导＋重绘':row.continuity?.mode==='motion_guide'||row.continuity?.mode==='previous_latent'?'R 运动引导':'I 独立镜头')));if(row.valid){card.append(node('p',row.prompt));if(row.references.length)card.append(node('small','引用：'+row.references.map(a=>a.name).join('、')));const details=node('details');details.append(node('summary','查看生成用提示词'),node('pre',row.model_prompt));card.append(details)}else card.append(node('p','镜头 '+row.index+'：'+row.error));$('storyboard-preview').append(card)}for(const error of result.errors.filter(e=>e.index===null))$('storyboard-preview').append(node('p',error.message,'error'));storyboardCandidate=result.valid?result.candidate:null;$('storyboard-apply').disabled=!storyboardCandidate;$('storyboard-apply').textContent=result.valid?'确认导入 '+result.count+' 个镜头':'确认导入'}catch(error){if(token===storyboardToken){$('storyboard-summary').textContent=error.message;$('storyboard-summary').classList.add('error')}}finally{storyboardChecking=false;$('storyboard-recognize').disabled=false}};
$('storyboard-apply').onclick=()=>{if(!storyboardCandidate||importing)return;if(busy&&$('storyboard-mode').value!=='append'){notice('生成期间只能追加镜头，不能替换本次任务中的镜头。',true);return}const next=storyboardCandidate,oldCount=plan.shots.length,append=$('storyboard-mode').value==='append';rememberShotEdit();if(append){plan.shots.push(...next.shots.slice(oldCount));plan.shot_sequence=Math.max(plan.shot_sequence||0,next.shot_sequence||0)}else plan=next;selected=append?oldCount:0;$('storyboard-dialog').close();draft();render();notice('镜头已导入，可点击「撤销」恢复之前的列表。')};

$('compiled-prompt-close').onclick=()=>$('compiled-prompt-dialog').close();
$('inspect-prompt').onclick=async()=>{
 draft();const snapshot=structuredClone(plan),shot=snapshot.shots[selected];if(!shot)return;
 $('compiled-prompt-text').textContent='';$('compiled-mapping').replaceChildren();$('compiled-prompt-error').textContent='正在编译…';$('compiled-prompt-dialog').showModal();
 try{const response=await fetch('/star7/director/preflight',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot)}),result=await response.json();if(!response.ok)throw Error(result.error||'提示词编译失败');const compiled=result.shots.find(s=>s.id===shot.id);$('compiled-prompt-text').textContent=compiled.prompt;
 for(const [id,label] of Object.entries(compiled.labels)){$('compiled-mapping').append(node('p',(snapshot.assets.find(a=>a.id===id)?.name||id)+' → '+label));}
 if(compiled.continuity_reference)$('compiled-mapping').append(node('p','前段 '+compiled.continuity_reference.source_shot+(compiled.continuity_reference.role==='previous_selected_frame'?' 的第 '+compiled.continuity_reference.frame+' 帧 → ':' 的成品最后一帧 → ')+compiled.continuity_reference.label+(compiled.continuity_reference.role==='previous_selected_frame'?'（指定首帧，同时用作图片参考）':'（生成时读取；普通图片参考，不锁首帧）')));
 const missing=result.missing.filter(m=>m.shot===shot.id);$('compiled-prompt-error').textContent=missing.length?'素材不可用：'+missing.map(m=>m.reason).join('；'):'';
 }catch(error){$('compiled-prompt-error').textContent=error.message;}
};

function migratePromptOptions(){if(!Object.hasOwn(plan.prompt_options||{},'no_subtitles'))plan.prompt_options={...plan.prompt_options,no_subtitles:plan.shots.some(s=>s.prompt_options?.no_subtitles===true)};for(const shot of plan.shots)if(shot.prompt_options){delete shot.prompt_options.no_subtitles;if(!Object.keys(shot.prompt_options).length)delete shot.prompt_options}}
$('global-custom-prompt-enabled').onchange=()=>{plan.prompt_options={...plan.prompt_options,custom_prompt_enabled:$('global-custom-prompt-enabled').checked};draft();refreshProcessAvailability()};
$('global-custom-prompt').oninput=()=>{plan.prompt_options={...plan.prompt_options,custom_prompt_enabled:$('global-custom-prompt-enabled').checked,custom_prompt:$('global-custom-prompt').value};draft()};
$('global-custom-prompt').onchange=()=>refreshProcessAvailability();
$('global-no-subtitles').onchange=()=>{plan.prompt_options={...plan.prompt_options,no_subtitles:$('global-no-subtitles').checked};draft();refreshProcessAvailability()};

function canDeleteShot(id){return !!id&&!importing&&!runSubmitting&&!queuedShots.has(id)}
function canKeepQueuedShots(shots){return [...queuedShots].every(id=>shots.some(s=>s.id===id))}
function visibleChanges(state,shot){
 const allowed=new Set(['shot.duration','shot.seed','shot.prompt','shot.input_mode','shot.continuity','shot.continuity.mode','shot.continuity.source_shot','shot.continuity.frame','shot.continuity.drift_control','shot.keyframes.first','shot.keyframes.last','shot.keyframes.first.from_previous.source_version','shot.references','shot.post.hd','shot.post.face','shot.post.face_count','shot.prompt_options.no_subtitles','shot.prompt_options.no_background_music','shot.prompt_options.custom_prompt']);
 let changes=(state?.changes||[]).filter(c=>allowed.has(c.field)||/^assets\.[^.]+\.(media|voice_id|description)$/.test(c.field||''));
 const modes={reference:'参考模式',keyframes:'智能首尾帧模式','未设置':'参考模式'};
 changes=changes.map(c=>c.field==='shot.input_mode'?{...c,label:'输入模式',before:modes[c.before]||c.before,after:modes[c.after]||c.after}:c);
 for(const [flag,nodeId] of [['hd','376'],['face','395']]){
  if(changes.some(c=>c.field==='shot.post.'+flag&&c.after==='开启'))changes=changes.filter(c=>!c.field?.startsWith('generation.'+nodeId));
 }
 const related=changes.filter(c=>['shot.continuity.mode','shot.continuity.source_shot','shot.continuity.frame'].includes(c.field));
 if(!related.length)return changes;
 const part=name=>related.find(c=>c.field==='shot.continuity.'+name);
 const names={independent:'独立镜头',motion_guide:'运动引导',motion_redraw:'运动引导＋重绘',tail_reference:'尾帧画面参考',selected_frame:'选定画面参考',previous_latent:'运动引导'};
 const mode=part('mode'),source=part('source_shot'),frame=part('frame');
 const toMode=mode?.after||shot?.continuity?.mode||'independent',fromMode=mode?.before||toMode;
 const describe=(value,ref,index)=>{let text=names[value]||value;if(value!=='independent'&&ref&&ref!=='未设置')text+='（参考 '+ref+(value==='selected_frame'?' 的第 '+(index||0)+' 帧':' 的画面')+'）';return text};
 const previous=describe(fromMode,source?.before||shot?.continuity?.source_shot,frame?.before),current=describe(toMode,source?.after||shot?.continuity?.source_shot,frame?.after??shot?.continuity?.frame);
 return [{field:'shot.continuity',label:'连续性',before:previous,after:current},...changes.filter(c=>(!c.field?.startsWith('shot.continuity.')||c.field==='shot.continuity.drift_control')&&!['av_handoff','tail_reference','first_from_previous'].some(prefix=>c.field?.startsWith(prefix))&&!(c.field==='reference_size'&&c.before==='未设置'))];
}
function paintParameterNotice(){$('notice').textContent=lastNotice.text;$('notice').style.color=lastNotice.error?'#f29e91':'#94a4bb'}
function setStale(value,announce=true,preservesPost=false){const changed=currentStale!==value;currentStale=value;if(!announce){if(!value&&lastNotice.kind==='parameter')notice('',false,'parameter');return;}if(value&&(changed||lastNotice.kind==='edit'||lastNotice.kind==='parameter'))notice(preservesPost?'后处理选项已修改；继续生成全部会保留已有二采／修脸成品，不会降级。需要降级请使用仅重新生成当前。':'镜头待更新：'+([...new Set(visibleChanges(shotStates.get(plan.shots[selected]?.id),plan.shots[selected]).map(c=>c.label))].join('、')||'请查看参数改动明细')+'。当前显示上次生成的画面。',!preservesPost,'parameter');else if(!value&&lastNotice.kind==='parameter')notice('',false,'parameter')}
function pendingUpstream(shot){if(!shot||generatingPhase!=='base'||!generatingShot||!shotStates.get(shot.id)?.has_output)return false;const index=plan.shots.indexOf(shot);if(shot.input_mode==='keyframes')return !!shot.keyframes?.first?.from_previous&&index>0&&plan.shots[index-1].id===generatingShot;return shot.continuity?.mode!=='independent'&&shot.continuity?.source_shot===generatingShot}
function renderChangeDetails(){const shot=plan.shots[selected],state=shotStates.get(shot?.id)||{},pending=pendingUpstream(shot),smart=pending&&shot.input_mode==='keyframes';const list=$('parameter-changes');list.replaceChildren();for(const change of visibleChanges(state,shot)){const text=change.label+'：'+change.before+' → '+change.after,item=node('li');if(change.field==='shot.continuity.drift_control'){const button=node('button',text,'parameter-setting-link');button.type='button';button.onclick=()=>{if(!$('global-dialog').open)$('global-dialog').showModal();document.querySelector('[data-settings-tab="continuity"]').click();$('context-drift').focus()};item.append(button)}else item.textContent=text;list.append(item)}if(smart&&!state.changes?.some(change=>change.field==='shot.keyframes.first.from_previous.source_version'))list.append(node('li','首帧 / 上段视频尾帧：前镜头正在重新生成，当前镜头将需要更新'));$('parameter-details').hidden=!list.children.length;$('parameter-summary').textContent='参数改动明细（'+list.children.length+'）'+(state.preserves_post?' · 批量生成保留已有后处理':'');const note=$('reference-change-note');note.hidden=!(state.reference_changed||pending&&!smart);note.textContent=pending&&!smart?'前一参考镜头正在重新生成，当前镜头尚未更新':'前一参考镜头已重新生成，当前镜头尚未更新';}
function applyShotStates(states){for(const [id,state] of Object.entries(states||{}))shotStates.set(id,state);drawShots();renderChangeDetails();}


mountExportResults();

let tailFrameRevision=0;
function renderInputMode(){
 renderChangeDetails();
 const shot=plan.shots[selected],smart=shot?.input_mode==='keyframes';$('input-mode').value=smart?'keyframes':'reference';$('input-mode').disabled=!shot;
 document.querySelector('.continuity-row').hidden=smart;$('keyframe-fields').hidden=!smart;
 $('use-previous-tail').disabled=!shot||selected===0;
 for(const key of ['first','last']){
  const zone=document.querySelector('[data-keyframe-slot="'+key+'"]'),item=shot?.keyframes?.[key],image=zone.querySelector('img'),label=zone.querySelector('span');
  zone.classList.toggle('from-previous',!!item?.from_previous);label.textContent=item?.from_previous?'上段视频尾帧':'点击或拖入图片';
  if(item?.from_previous){
   const previous=plan.shots[selected-1];image.hidden=true;
   if(previous){const url='/star7/director/tail-image/'+encodeURIComponent(plan.id)+'/'+encodeURIComponent(previous.id)+'?v='+tailFrameRevision;
    image.onload=()=>{if(plan.shots[selected]===shot&&shot.keyframes?.[key]===item)image.hidden=false};image.onerror=()=>{if(plan.shots[selected]===shot&&shot.keyframes?.[key]===item)image.hidden=true};
    if(image.getAttribute('src')!==url)image.src=url;else image.hidden=!image.complete||!image.naturalWidth;
   }else image.removeAttribute('src');
  }else{image.onload=null;image.onerror=()=>{image.hidden=true};image.hidden=!item;if(item)image.src=mediaURL(item.thumbnail_source||item.source);else image.removeAttribute('src')}
  document.querySelector('[data-keyframe-clear="'+key+'"]').disabled=!item;
 }
}
$('input-mode').onchange=()=>{const shot=plan.shots[selected];if(!shot)return;shot.input_mode=$('input-mode').value;draft();drawShots();renderInputMode();promptUI.refresh(true);refreshProcessAvailability()};
const endpointVersions=new WeakMap();
function endpointVersion(shot,key){const values=endpointVersions.get(shot)||{};values[key]=(values[key]||0)+1;endpointVersions.set(shot,values);return values[key]}
for(const zone of document.querySelectorAll('[data-keyframe-slot]')){
 const key=zone.dataset.keyframeSlot,input=zone.querySelector('input');
 zone.onclick=e=>{if(e.target===input)return;const shot=plan.shots[selected],image=zone.querySelector('img');if(shot?.keyframes?.[key]?.from_previous&&!image.hidden){$('keyframe-view-image').src=image.src;$('keyframe-view-dialog').showModal()}else input.click()};zone.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();input.click()}};
 async function upload(file){const shot=plan.shots[selected];if(!shot||!file)return;const version=endpointVersion(shot,key);if(detectedMedia(file)!=='image'){notice('首尾帧只支持图片。',true);return}try{zone.setAttribute('aria-busy','true');const data=new FormData();data.append('kind','image');data.append('known_media','[]');data.append('file',file);const response=await fetch('/star7/director/upload',{method:'POST',body:data});const item=await response.json();if(!response.ok)throw Error(item.error||'上传失败');if(plan.shots.includes(shot)&&endpointVersions.get(shot)?.[key]===version){shot.keyframes={...shot.keyframes,[key]:item};draft();drawShots();renderInputMode();promptUI.refresh(true);refreshProcessAvailability()}}catch(error){notice(error.message,true)}finally{if(endpointVersions.get(shot)?.[key]===version){zone.removeAttribute('aria-busy');input.value=''}}}
 input.onchange=()=>upload(input.files[0]);zone.ondragover=e=>{e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='copy'};zone.ondrop=e=>{e.preventDefault();e.stopPropagation();if(e.dataTransfer.files.length!==1){notice('请一次上传一张图片。',true);return}upload(e.dataTransfer.files[0])};
 document.querySelector('[data-keyframe-clear="'+key+'"]').onclick=()=>{const shot=plan.shots[selected];if(!shot)return;endpointVersion(shot,key);zone.removeAttribute('aria-busy');delete shot.keyframes?.[key];draft();drawShots();renderInputMode();promptUI.refresh(true);refreshProcessAvailability()};
}
$('global-no-music').onchange=()=>{plan.prompt_options={...plan.prompt_options,no_background_music:$('global-no-music').checked};draft();refreshProcessAvailability()};

for(const [button,target] of [['project-library-import','library-import'],['project-library-export','library-export'],['project-material-outline','catalog']])$(button).onclick=()=>$(target).click();
$('clear-vram-between-shots').onchange=()=>{plan.execution_options={...plan.execution_options,clear_vram_between_shots:$('clear-vram-between-shots').checked};draft()};

let playlistRequest=0;
const playlistPreview=mountPlaylistPreview({video:$('all-preview-video'),title:$('all-preview-title'),position:$('all-preview-position'),previous:$('all-preview-previous'),next:$('all-preview-next')});
$('preview-all').onclick=async()=>{
 const requestId=++playlistRequest,job=crypto.randomUUID().replaceAll('-','');playlistPreview.reset();notice('正在准备连续预览…');$('all-preview-summary').textContent='源视频和顺序不变时复用预览；更新成功后清理旧版。';$('all-preview-preparation').hidden=false;$('all-preview-progress').value=0;$('all-preview-progress-label').textContent='正在检查已生成的视频…';$('all-preview-dialog').showModal();
 let polling=false;const poll=setInterval(async()=>{if(polling||requestId!==playlistRequest)return;polling=true;try{const response=await fetch('/star7/director/preview-progress/'+job);if(!response.ok)return;const data=await response.json();if(requestId!==playlistRequest)return;$('all-preview-progress').value=data.percent;$('all-preview-progress-label').textContent=data.message+' '+data.percent+'%'}catch{}finally{polling=false}},500);
 try{const response=await fetch('/star7/director/preview-playlist?progress='+job,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(plan)}),data=await response.json();if(!response.ok)throw Error(data.error||'无法读取预览');if(requestId!==playlistRequest||!$('all-preview-dialog').open)return;$('all-preview-progress').value=100;$('all-preview-preparation').hidden=true;$('all-preview-summary').textContent=data.message;notice(data.message);playlistPreview.load(data.clips,data.url)}catch(error){if(requestId===playlistRequest){$('all-preview-preparation').hidden=true;$('all-preview-summary').textContent=error.message;notice(error.message,true)}}finally{clearInterval(poll)}
};
$('all-preview-close').onclick=()=>$('all-preview-dialog').close();$('all-preview-dialog').onclose=()=>{playlistRequest++;playlistPreview.reset()};

function projectRequest(action,body={}){return new Promise((resolve,reject)=>{const requestId=++projectRequestId;projectReplies.set(requestId,{resolve,reject});parent.postMessage({type:'star7-director-local-project',action,body,item:body.item,requestId},location.origin)})}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent)return;const data=e.data;
 if(data?.type==='star7-director-project-graph-dirty'){planRevision++;notice('',false,'edit');projectManager?.changed();refreshProcessAvailability();}
 if(data?.type==='star7-director-project-reply'){const pending=projectReplies.get(data.requestId);if(!pending)return;projectReplies.delete(data.requestId);if(data.error)pending.reject(Error(data.error));else pending.resolve(data.result)}
 if(data?.type==='star7-director-project-media'&&data.projectId===plan.id){const visit=v=>{if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(['source','thumbnail_source'].includes(k)&&data.map[x])v[k]=data.map[x];else visit(x)}};visit(plan.assets);for(const shot of plan.shots)visit(shot.keyframes);plan.media_aliases={...plan.media_aliases,...data.aliases};render();}
});
projectManager=mountProjectManager({getPlan:()=>plan,isBusy:()=>busy,onTitle:value=>{plan.title=value;$('title').value=value;draft()},request:projectRequest});

$('batch-select').onclick=()=>{if(importing||runSubmitting)return;batchSelecting=true;batchSelection.clear();drawShots()};
$('batch-cancel').onclick=()=>{batchSelecting=false;batchSelection.clear();drawShots()};
$('batch-confirm').onclick=()=>{if(!batchSelection.size||runSubmitting)return;const ids=plan.shots.filter(s=>batchSelection.has(s.id)).map(s=>s.id);batchSelecting=false;batchSelection.clear();run('selected',ids)};

mountQueueView({getProjectId:()=>plan.id});

$('use-previous-tail').onclick=()=>{const shot=plan.shots[selected];if(!shot||!selected)return;endpointVersion(shot,'first');shot.keyframes={...shot.keyframes,first:{from_previous:true}};tailFrameRevision++;draft();drawShots();renderInputMode();promptUI.refresh(true)};
$('keyframe-view-close').onclick=()=>$('keyframe-view-dialog').close();
