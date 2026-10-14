import {mountFramePosition} from './frame-position.mjs';
export function clipDescription(clip,width=clip?.width,height=clip?.height){
 const post=clip?.post;
 const stage=!post?'已生成画面':post.hd&&post.face?'二采＋人脸修复画面':post.hd?'二采画面':post.face?'人脸修复画面':'一采画面';
 if(!(width>0&&height>0))return '当前为'+stage;
 const short=Math.min(width,height),preset=[240,360,480,540,720,900,1080,1200,1440,1800,2160].find(n=>Math.abs(short-n)<=16);
 const resolution=preset===2160?'4K（2160p）':preset?preset+'p':'自定义';
 return '当前为'+stage+'：'+resolution+' · '+width+'×'+height+' · '+(width*height/1e6).toFixed(2)+' MP';
}
export function mountShotPreview({video,image,empty,status,framePosition,infoLabel,phaseLabel,getPlan,getShot,request}){
 const clips=new Map(),live=new Map();let shown=null,requestId=0,pending=null;
 const key=(p,s)=>p+'\0'+s;
 const frameUI=framePosition?mountFramePosition({video,label:framePosition,getInfo:()=>({...clips.get(shown),fps:clips.get(shown)?.fps||getPlan().settings?.fps||24})}):null;
 function describe(){
  const clip=clips.get(shown),frame=live.get(shown);
  if(infoLabel){infoLabel.hidden=!!frame||video.hidden||!clip;infoLabel.textContent=infoLabel.hidden?'':clipDescription(clip,clip.width||video.videoWidth,clip.height||video.videoHeight)}
  if(phaseLabel){
   phaseLabel.hidden=!frame;
   if(!frame){phaseLabel.textContent='';return}
   const action=frame.phase==='hd'?'二采生成中':frame.phase==='face'?'人脸修复生成中':frame.phase==='decode'?'正在保存成品':'一采生成中';
   const picture=!video.hidden&&clip?clipDescription(clip,clip.width||video.videoWidth,clip.height||video.videoHeight):!image.hidden?'当前为一采实时预览画面':'当前暂无预览画面';
   phaseLabel.textContent=action+' · '+picture;
  }
 }
 video.addEventListener('loadedmetadata',describe);
 function display(){const plan=getPlan(),shot=getShot(),k=shot?key(plan.id,shot.id):null,frame=k&&live.get(k),clip=k&&clips.get(k),processing=['hd','face','decode'].includes(frame?.phase),useVideo=clip&&(!frame||processing&&!frame.awaitingBase);
  if(!useVideo)video.pause();video.hidden=true;image.hidden=true;status.hidden=true;empty.hidden=true;

  if(useVideo){image.removeAttribute('src');if(video.getAttribute('src')!==clip.url){video.pause();video.src=clip.url}video.hidden=false}
  else if(frame?.image){video.removeAttribute('src');if(image.src!==frame.image)image.src=frame.image;image.hidden=false;status.textContent=frame.message||'';status.hidden=!frame.message}
  else{video.removeAttribute('src');image.removeAttribute('src');empty.hidden=false;if(frame?.message){status.textContent=frame.message;status.hidden=false}}
  describe();frameUI?.refresh();
 }
 function show(){const p=getPlan(),s=getShot(),k=s?key(p.id,s.id):null;if(k===shown)return;shown=k;display();if(s){pending={projectId:p.id,shotId:s.id,requestId:++requestId};request({...pending})}}
 function result(data){if(!data.projectId||!data.shotId)return;if(data.requestId!==undefined&&(!pending||data.requestId!==pending.requestId))return;const k=key(data.projectId,data.shotId),frame=live.get(k);
  // A previous version arriving late must not release a pending first pass.
  if(data.requestId===undefined&&frame?.awaitingBase&&(!data.nonce||data.nonce!==frame.nonce&&data.nonce!==frame.baseNonce))return;
  if(data.url){clips.set(k,{url:data.url,frames:data.frames,fps:data.fps,post:data.post,width:data.width,height:data.height});if(data.requestId===undefined){if(frame)frame.awaitingBase=false;if(!data.keep_live)live.delete(k);if(pending?.projectId===data.projectId&&pending.shotId===data.shotId)pending=null}}else if(!frame)clips.delete(k);if(k===shown)display()}
 function start(data){const k=key(data.projectId,data.shotId),old=live.get(k),phase=data.phase||'base';live.set(k,{message:getPlan().preview?.preview_enabled===false?'实时预览已关闭，等待一采视频…':'等待实时预览…',runId:null,phase,nonce:data.nonce,baseNonce:phase==='base'?data.nonce:old?.baseNonce,awaitingBase:phase==='base'||!!old?.awaitingBase});if(k===shown)display()}
 function phase(data){const k=key(data.projectId,data.shotId),old=live.get(k)||{};live.set(k,{...old,phase:data.phase,nonce:data.nonce});if(k===shown)display()}
 function preview(data){const k=key(data.projectId,data.shotId),previous=live.get(k);if(['hd','face','decode'].includes(previous?.phase))return;if(data.status==='start'||data.status==='downloading'){live.set(k,{...previous,runId:data.run_id,message:data.status==='downloading'?'正在准备预览模型，采样继续运行…':'等待实时预览…'})}else{if(previous?.runId&&previous.runId!==data.run_id)return;live.set(k,{...previous,runId:data.run_id,image:data.image?'data:image/webp;base64,'+data.image:previous?.image,message:data.status==='error'?(data.message||'实时预览已跳过'):data.image?`实时预览 · 第 ${data.step}/${data.total} 步 · ${data.width}×${data.height}`:previous?.message})}if(k===shown)display()}
 function finish(data){const k=key(data.projectId,data.shotId),frame=live.get(k);if(frame?.awaitingBase&&['completed','stopped'].includes(data.status)){frame.phase='decode';frame.message='新一采已生成，正在读取成品…'}else live.delete(k);if(k===shown)display()}
 function reset(){clips.clear();live.clear();shown=null;pending=null;show()}
 return {show,result,start,phase,preview,finish,reset};
}
