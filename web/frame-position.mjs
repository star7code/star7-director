export function mountFramePosition({video,label,getInfo}){
 let callback=null,generation=0,presentedTime=null;
 function update(){const info=getInfo()||{},duration=video.duration;if(video.hidden||video.readyState<1||!Number.isFinite(duration)||duration<=0){label.hidden=true;label.textContent='';return}
  const total=Number(info.frames)>0?Number(info.frames):Math.max(1,Math.round(duration*(Number(info.fps)||24)));
  const fps=Number(info.fps)||24;
  const time=presentedTime??video.currentTime,index=Math.min(total-1,Math.max(0,Math.floor(time*fps+1e-4)));
  label.textContent='当前帧序号：'+index;label.hidden=false;
 }
 function cancel(){generation++;if(callback!==null&&video.cancelVideoFrameCallback)video.cancelVideoFrameCallback(callback);callback=null}
 function schedule(){if(!video.requestVideoFrameCallback||video.hidden||callback!==null)return;const version=generation;callback=video.requestVideoFrameCallback((_,meta)=>{callback=null;if(version!==generation)return;presentedTime=meta.mediaTime;update();if(!video.paused&&!video.ended)schedule()})}
 function refresh(){cancel();presentedTime=null;update();if(!video.hidden)schedule()}
 video.addEventListener('loadedmetadata',refresh);video.addEventListener('play',()=>{update();schedule()});video.addEventListener('pause',update);video.addEventListener('timeupdate',()=>{if(!video.requestVideoFrameCallback||presentedTime===null)update()});
 video.addEventListener('seeking',()=>{cancel();presentedTime=null;update()});video.addEventListener('seeked',()=>{update();schedule()});video.addEventListener('ended',()=>{presentedTime=video.duration;update();cancel()});video.addEventListener('emptied',()=>{cancel();presentedTime=null;update()});
 return {refresh};
}
