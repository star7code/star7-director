// Layout heights belong to the project, never to an individual shot or render settings.
export function mountLayout({preview,prompt,handle,getPlan,onChange,isBusy}){
 let drag=null;
 const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
 function setHeight(element,height){element.style.height=height+'px'}
 function save(key,element,min,max){const plan=getPlan(),height=clamp(Math.round(element.getBoundingClientRect().height),min,max);plan.ui_layout={...plan.ui_layout,[key]:height};onChange()}
 function apply(){prompt.style.removeProperty('height');if(drag)return;const layout=getPlan().ui_layout||{};setHeight(preview,clamp(Number(layout.preview_height)||160,120,900));}
 function finish(){if(drag){save('preview_height',preview,120,900);drag=null}}
 handle.addEventListener('pointerdown',e=>{if(e.button!==0||isBusy())return;e.preventDefault();e.stopPropagation();drag={y:e.clientY,height:preview.getBoundingClientRect().height};handle.setPointerCapture(e.pointerId)});
 handle.addEventListener('pointermove',e=>{if(drag)setHeight(preview,clamp(drag.height+e.clientY-drag.y,120,900))});
 handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
 handle.addEventListener('keydown',e=>{if(isBusy()||!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();setHeight(preview,clamp(preview.getBoundingClientRect().height+(e.key==='ArrowDown'?20:-20),120,900));save('preview_height',preview,120,900)});
 // Only the video preview retains its resize gesture. Old prompt heights are ignored.
 document.addEventListener('pointerup',finish);document.addEventListener('mouseup',finish);window.addEventListener('blur',finish);
 apply();return {apply};
}
