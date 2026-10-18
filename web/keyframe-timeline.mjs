export const FRAME_DRAG='application/x-star7-director-frame';
export const keyframeTime=value=>Math.round(Number(value)*10+1e-9)/10;
const boundedTime=(value,duration)=>Math.max(0,Math.min(Math.floor(duration*10+1e-9)/10,keyframeTime(value)));
export const frameReferenceId=id=>'__star7_keyframe_'+id+'__';
export function currentFrameAssets(shot,previous){if(shot?.input_mode!=='keyframes')return [];const points=[...(shot.keyframe_points||[])].sort((a,b)=>a.time_seconds-b.time_seconds||a.id.localeCompare(b.id));return [{id:'__star7_first_frame__',name:'首帧',item:shot.keyframe_motion?undefined:shot.keyframes?.first},...points.map((item,i)=>({id:frameReferenceId(item.id),name:'关键帧'+(i+1),item})),{id:'__star7_last_frame__',name:'尾帧',item:shot.keyframes?.last}].map(a=>({...a,kind:'current_frame',virtual:true,currentFrame:true,shotId:shot.id,referenceToken:'@{'+a.id+'}',disabled:!a.item?.source&&!a.item?.from_previous,media:a.item?.source?[{type:'image',source:a.item.source,thumbnail_source:a.item.thumbnail_source}]:[],previewURL:a.item?.from_previous?previous:undefined}));}
export const ASSET_DRAG='application/x-star7-director-asset';
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
const TIMELINE_EDGE=64;
const CARD_SPACING=116,RETURN_SPACING=124;
export function changeTimelineDuration(shot,duration){
 // Endpoints follow the shot boundary; only ordinary points use absolute time.
 shot.duration=duration;
}
export function timelineErrors(shot){
 if(shot?.input_mode!=='keyframes')return [];
 const duration=Number(shot.duration)||0,frames=Math.max(1,Math.round(duration*24)),occupied=new Set(),errors=[];
 if(shot.keyframe_motion||shot.keyframes?.first)occupied.add(0);if(shot.keyframes?.last)occupied.add(frames-1);
 for(const p of shot.keyframe_points||[]){const t=keyframeTime(p.time_seconds),index=Math.min(frames-1,Math.round(t*24));
  if(!Number.isFinite(t)||t<0||t>duration)errors.push(`${t} 秒超出镜头时长 ${duration} 秒`);
  else if(!p.source)errors.push(`${t} 秒的关键帧尚未设置图片`);
  else if(occupied.has(index))errors.push(`${t} 秒与其他关键帧处于同一帧，请调整时间`);
  occupied.add(index);
 }return errors;
}
export function timelineLayout(shot,pixels=64,previous=[]){
 const duration=Math.max(.1,Number(shot.duration)||5),points=shot.keyframe_points||[],extent=Math.max(duration,...points.map(p=>Number(p.time_seconds)||0));
 const items=[{id:'first',time:0,endpoint:true,item:shot.keyframes?.first},...points.map(p=>({id:p.id,time:Number(p.time_seconds),item:p})),{id:'last',time:duration,endpoint:true,item:shot.keyframes?.last}].sort((a,b)=>a.time-b.time||(a.id==='first'?-1:b.id==='first'?1:a.id==='last'?1:b.id==='last'?-1:a.id.localeCompare(b.id)));
 const lanes=[],prior=new Map(previous.map(item=>[item.id,item]));
 for(const item of items){item.x=TIMELINE_EDGE+item.time*pixels;item.scale=item.endpoint?Math.min(1,duration*pixels/CARD_SPACING):1;}
 // Endpoints own the baseline. Preserve the other rows before placing moved
 // cards; layer numbers always count upward from the rail.
 const priority=item=>item.endpoint?-1:!prior.has(item.id)?2:prior.get(item.id).time===item.time?0:1;
 for(const item of [...items].sort((a,b)=>priority(a)-priority(b))){
  const fits=(row,gap=CARD_SPACING)=>!row?.some(x=>Math.abs(item.x-x)<gap);
  let lane=item.endpoint?0:prior.get(item.id)?.lane;
  if(priority(item)===1&&lane>0){const above=lanes.findIndex((row,index)=>index<lane&&fits(row,RETURN_SPACING));if(above>=0)lane=above;}
  if(!item.endpoint&&(lane===undefined||!fits(lanes[lane]))){lane=lanes.findIndex(row=>fits(row));if(lane<0)lane=lanes.length;}
  (lanes[lane]??=[]).push(item.x);item.lane=lane;
 }
 // Return a redundant highest layer toward the baseline without exchanging
 // other cards' layers. The extra 8px prevents boundary jitter.
 while(lanes.length>1){
  const bottom=lanes.length-1,lower=items.filter(item=>item.lane===bottom),upper=Array.from(lanes.slice(0,bottom),row=>[...(row||[])]),moves=[];
  for(const item of lower){
   const lane=upper.findIndex(row=>row.every(x=>Math.abs(item.x-x)>=RETURN_SPACING));
   if(lane<0)break;
   upper[lane].push(item.x);moves.push({item,lane});
  }
  if(moves.length!==lower.length)break;
  for(const {item,lane} of moves)item.lane=lane;
  for(let lane=0;lane<bottom;lane++)lanes[lane]=upper[lane];lanes.pop();
 }
 const rows=[...new Set(items.map(item=>item.lane))].sort((a,b)=>a-b);
 for(const item of items)item.lane=rows.indexOf(item.lane);
 return {duration,extent,items,lanes:rows.length,width:2*TIMELINE_EDGE+extent*pixels,height:80+rows.length*184};
}
export function readAssetDrag(event,assets,projectId){
 try{const raw=event.dataTransfer.getData(ASSET_DRAG);if(!raw)return null;let data;try{data=JSON.parse(raw)}catch{data={id:raw}};
  const card=assets.find(a=>a.id===data.id);
  if(card){const image=card.media?.find(m=>m.type==='image');return image?{...image}:null}
  // A library iframe has its own drag state. Only accept explicit image media,
  // same-origin events and the serialized card; the backend still validates paths.
  const image=data.media?.find(m=>m.type==='image');return image&&typeof image.source==='string'?{...image}:null;
 }catch{return null}
}
export function mountKeyframeTimeline({root,getShot,getPlan,isLocked,onChange,uploadFile,mediaURL,notice,previousURL,previewPrevious}){
 let renderId=0;const versions=new WeakMap(),images=new WeakMap(),layouts=new WeakMap();let dragging=false,lastWidth=0;
 function version(shot,id){const values=versions.get(shot)||{};values[id]=(values[id]||0)+1;versions.set(shot,values);return values[id]}
 function live(shot,id){return getPlan().shots.includes(shot)&&(id==='first'||id==='last'||shot.keyframe_points?.some(p=>p.id===id))}
 function changed(){onChange();render()}
 function assign(shot,id,media){if(id==='first')shot.keyframe_motion=false;if(id==='first'||id==='last')shot.keyframes={...shot.keyframes,[id]:media};else{const index=shot.keyframe_points?.findIndex(p=>p.id===id);if(index>=0){const point=shot.keyframe_points[index];shot.keyframe_points[index]={...media,id:point.id,time_seconds:point.time_seconds}}}changed()}
 async function upload(shot,id,file){if(!file||isLocked())return;const ticket=version(shot,id);try{const image=await uploadFile(file,'image');if(live(shot,id)&&versions.get(shot)?.[id]===ticket)assign(shot,id,image)}catch(error){notice(error.message,true)}}
 function add(shot,time){if(isLocked())return;shot.keyframe_points||=[];shot.keyframe_points.push({id:'kf_'+crypto.randomUUID().slice(0,12),time_seconds:boundedTime(time,shot.duration)});changed()}
 function render(){
  if(dragging)return;renderId++;const shot=getShot();root.replaceChildren();if(!shot||shot.input_mode!=='keyframes')return;
  for(const point of shot.keyframe_points||[])point.time_seconds=keyframeTime(point.time_seconds);
  const width=Math.max(2*TIMELINE_EDGE+1,root.clientWidth-2),extent=Math.max(.1,Number(shot.duration)||5,...(shot.keyframe_points||[]).map(p=>Number(p.time_seconds)||0)),scale=(width-2*TIMELINE_EDGE)/extent,layout=timelineLayout(shot,scale,layouts.get(shot));layouts.set(shot,layout.items);lastWidth=root.clientWidth;const frames=currentFrameAssets(shot,previousURL(shot)),frameNames=new Map(frames.map(a=>[a.id,a]));let shotImages=images.get(shot);if(!shotImages){shotImages=new Map();images.set(shot,shotImages)}
  const head=el('div','kf-heading'),title=el('b',null,'关键帧'),duration=el('span',null,`${layout.duration} 秒`);head.append(title,duration);
  const previous=el('button',null,'使用上段尾帧画面作为此段首帧');previous.type='button';previous.disabled=isLocked()||getPlan().shots.indexOf(shot)===0;
  const tailActive=!!shot.keyframes?.first?.from_previous&&!shot.keyframe_motion;previous.dataset.action='previous-tail';previous.setAttribute('aria-pressed',String(tailActive));previous.classList.toggle('active',tailActive);
  previous.onclick=()=>{version(shot,'first');assign(shot,'first',{from_previous:true})};head.append(previous);root.append(head);
  const motion=el('button',null,'使用上一段尾部视频作为运动引导');motion.type='button';motion.dataset.action='previous-motion';motion.disabled=previous.disabled;motion.setAttribute('aria-pressed',String(!!shot.keyframe_motion));motion.classList.toggle('active',!!shot.keyframe_motion);motion.title='使用上一段尾部视频占用首帧位置，复用运动引导设置；再次点击关闭并恢复原首帧';motion.onclick=()=>{version(shot,'first');shot.keyframe_motion=!shot.keyframe_motion;changed()};head.append(motion);
  const scroll=el('div','kf-scroll'),stage=el('div','kf-stage');stage.style.width=layout.width+'px';stage.style.height=layout.height+'px';scroll.append(stage);root.append(scroll);
  const rail=el('div','kf-rail');rail.style.left=TIMELINE_EDGE+'px';rail.style.width=layout.duration*scale+'px';stage.append(rail);
  if(layout.extent>layout.duration){const overflow=el('div','kf-overflow');overflow.style.left=TIMELINE_EDGE+layout.duration*scale+'px';overflow.style.width=(layout.extent-layout.duration)*scale+'px';overflow.title=`${layout.duration}～${layout.extent} 秒超出镜头时长`;stage.append(overflow)}
  const tickStep=Math.max(1,Math.ceil(layout.extent/15));
  const ticks=new Set([layout.duration,layout.extent]);for(let t=0;t<=layout.extent;t+=tickStep)ticks.add(t);
  for(const t of [...ticks].sort((a,b)=>a-b)){const tick=el('span','kf-tick',t+'s');tick.style.left=TIMELINE_EDGE+t*scale+'px';stage.append(tick)}
  for(const entry of layout.items){
   const motionFirst=entry.id==='first'&&shot.keyframe_motion;
   const card=el('article','kf-card');card.dataset.keyframeId=entry.id;card.dataset.layer=entry.lane;card.style.left=entry.x+'px';card.style.bottom=76+entry.lane*184+'px';card.style.transform=`translateX(-50%) scale(${entry.scale})`;card.style.transformOrigin='bottom center';
   card.classList.toggle('kf-invalid',entry.time>layout.duration);card.classList.toggle('kf-empty',!entry.item?.source&&!entry.item?.from_previous);
   const stem=el('div','kf-stem');stem.style.left=entry.x+'px';stem.style.height=38+entry.lane*184+'px';stem.style.bottom='38px';stage.append(stem);
   const refId=entry.id==='first'?'__star7_first_frame__':entry.id==='last'?'__star7_last_frame__':frameReferenceId(entry.id),frameAsset=frameNames.get(refId);const name=el('div','kf-card-title',entry.endpoint?frameAsset.name:'⠿ '+frameAsset.name);
   const remove=el('button','kf-remove','×');remove.type='button';remove.title=motionFirst?'关闭运动引导':entry.endpoint?'清除图片':'删除关键帧';remove.setAttribute('aria-label',remove.title);remove.disabled=isLocked();
   remove.onclick=e=>{e.stopPropagation();version(shot,entry.id);if(motionFirst)shot.keyframe_motion=false;else if(entry.endpoint)delete shot.keyframes?.[entry.id];else shot.keyframe_points=shot.keyframe_points.filter(p=>p.id!==entry.id);changed()};
   const zone=el('div','keyframe-zone kf-square');zone.dataset.keyframeSlot=entry.id;zone.tabIndex=0;zone.setAttribute('role','button');zone.setAttribute('aria-label',name.textContent+'图片');
   const input=el('input');input.type='file';input.accept='image/*';input.hidden=true;input.onchange=()=>upload(shot,entry.id,input.files[0]);
   const replace=el('button','kf-replace','替换');replace.type='button';replace.title='选择图片替换，保留关键帧及时间';replace.setAttribute('aria-label','替换'+frameAsset.name+'图片');replace.disabled=isLocked();replace.onclick=e=>{e.preventDefault();e.stopPropagation();input.value='';input.click()};
   const source=motionFirst||entry.item?.from_previous?previousURL(shot):entry.item?.source?mediaURL(entry.item.thumbnail_source||entry.item.source):null;
   const previousFirst=motionFirst||entry.item?.from_previous,previewLabel=motionFirst?'上段尾部引导':entry.item?.from_previous?'上段尾帧画面':'';
   if(previousFirst){card.classList.remove('kf-empty');zone.classList.add('kf-motion-placeholder');zone.setAttribute('aria-label','首帧位置：'+previewLabel);zone.title=previewLabel;zone.append(el('span','kf-motion-label',previewLabel));}
   if(source){let cache=shotImages.get(entry.id);if(!cache||cache.source!==source){cache={source,image:el('img')};cache.image.src=source;shotImages.set(entry.id,cache)}const image=cache.image;image.alt=frameAsset.name;image.draggable=!motionFirst;image.onerror=()=>{image.hidden=true;if(motionFirst)return;zone.append(el('span',null,entry.item?.from_previous?'上段尾帧待生成':'图片不可用'))};image.ondragstart=e=>{e.stopPropagation();if(motionFirst){e.preventDefault();return}e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData(FRAME_DRAG,JSON.stringify({project:getPlan().id,shot:shot.id,id:refId}));e.dataTransfer.setData('text/plain','@{'+refId+'}')};zone.append(image)}else{shotImages.delete(entry.id);if(!motionFirst)zone.append(el('span',null,'＋ 图片'))};
   const activate=()=>{if(source){const full=previousFirst?source:mediaURL(entry.item.source);previewPrevious(full,frameAsset.name,previewLabel)}else if(previousFirst)notice('上段尾帧尚未就绪，请先生成上一段。');else if(!isLocked())input.click()};
   zone.append(input,remove,replace);zone.onclick=e=>{if(e.target===input||e.target.closest('button'))return;activate()};zone.onkeydown=e=>{if(e.target===zone&&['Enter',' '].includes(e.key)){e.preventDefault();activate()}};
   zone.ondragover=e=>{e.preventDefault();e.stopPropagation();zone.classList.add('kf-drop');e.dataTransfer.dropEffect='copy'};zone.ondragleave=()=>zone.classList.remove('kf-drop');
   zone.ondrop=e=>{e.preventDefault();e.stopPropagation();zone.classList.remove('kf-drop');if(isLocked())return;const media=readAssetDrag(e,getPlan().assets,getPlan().id);if(media){version(shot,entry.id);assign(shot,entry.id,media)}else if(e.dataTransfer.files.length===1)upload(shot,entry.id,e.dataTransfer.files[0]);else notice('请拖入一张图片或素材库图片卡。',true)};
   const time=el('input','kf-time');time.type='number';time.min='0';time.step='0.1';time.value=keyframeTime(entry.time).toFixed(1);time.disabled=entry.endpoint||isLocked();time.setAttribute('aria-label',name.textContent+'时间／秒');time.title=entry.endpoint?'首尾帧随镜头时长固定':'时间／秒';
   time.onchange=()=>{const value=Number(time.value);if(!Number.isFinite(value)||value<0){notice('请输入大于等于 0 的秒数。',true);time.value=keyframeTime(entry.time).toFixed(1);return}entry.item.time_seconds=keyframeTime(value);changed()};
   const row=el('label','kf-time-row');row.append(time,el('span',null,'秒'));card.append(name,zone,row);
   for(const side of [-1,1]){if(entry.id==='first'&&side<0||entry.id==='last'&&side>0)continue;const plus=el('button','kf-add '+(side<0?'before':'after'),'＋');plus.type='button';plus.title=side<0?'在前面增加关键帧':'在后面增加关键帧';plus.setAttribute('aria-label',plus.title);plus.disabled=isLocked();plus.onclick=()=>{const index=layout.items.indexOf(entry),neighbor=layout.items[index+side]||layout.items[index-side],t=neighbor?(entry.time+neighbor.time)/2:entry.time;add(shot,t)};card.append(plus)}
   if(!entry.endpoint){name.tabIndex=0;name.setAttribute('role','slider');name.setAttribute('aria-valuemin','0');name.setAttribute('aria-valuemax',String(layout.duration));name.setAttribute('aria-valuenow',String(entry.time));
    name.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key)||isLocked())return;e.preventDefault();entry.item.time_seconds=boundedTime(entry.time+(e.key==='ArrowLeft'?-1:1)*(e.shiftKey?1:.1),layout.duration);changed()};
    name.onpointerdown=e=>{if(isLocked()||e.button!==0)return;e.preventDefault();const start=e.clientX,original=entry.time;let moved=false;dragging=true;name.setPointerCapture(e.pointerId);
     name.onpointermove=event=>{moved=true;const seconds=boundedTime(original+(event.clientX-start)/scale,layout.duration);entry.item.time_seconds=seconds;card.style.left=TIMELINE_EDGE+seconds*scale+'px';stem.style.left=card.style.left;time.value=seconds.toFixed(1);card.classList.remove('kf-invalid')};
     const end=()=>{name.onpointermove=null;name.onpointerup=null;name.onpointercancel=null;dragging=false;if(moved)changed();else render()};name.onpointerup=end;name.onpointercancel=end;
    };
   }stage.append(card);
  }
  const errors=timelineErrors(shot);if(errors.length){const status=el('div','kf-errors',errors.join('；'));status.setAttribute('role','alert');root.append(status)}
 }
 const observer=new ResizeObserver(()=>{if(root.clientWidth>0&&Math.abs(root.clientWidth-lastWidth)>1)render()});observer.observe(root);
 return {render};
}
