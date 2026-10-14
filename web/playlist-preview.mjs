export function mountPlaylistPreview({video,title,position,previous,next}){
 let clips=[],index=0,token=0;
 const clock=n=>{n=Math.max(0,Math.floor(n||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0')};
 const start=i=>clips.slice(0,i).reduce((n,c)=>n+c.duration,0);
 function paint(){const time=video.currentTime||0;index=0;while(index+1<clips.length&&time>=start(index+1)-.02)index++;const clip=clips[index];title.textContent=clip?'第 '+(index+1)+'/'+clips.length+' 段 · '+clip.name:'';previous.disabled=index<=0;next.disabled=index>=clips.length-1;position.textContent=clips.length?clock(time)+' / '+clock(start(clips.length)):''}
 function seek(i){if(i<0||i>=clips.length)return;video.currentTime=start(i);paint();video.play().catch(()=>{})}
 video.addEventListener('timeupdate',paint);video.addEventListener('seeked',paint);video.addEventListener('ended',paint);
 previous.onclick=()=>seek(index-1);next.onclick=()=>seek(index+1);
 return {async load(items,url){clips=items;index=0;const version=++token;video.src=url;paint();try{await video.play()}catch{if(version===token)title.textContent+=' · 点击视频播放'}},reset(){token++;clips=[];index=0;video.pause();video.removeAttribute('src');video.load();paint()}};
}
