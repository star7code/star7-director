function safeName(name){return String(name||'video').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[ .]+$/,'')||'video'}
export async function chooseDirectory(){
 const host=parent===window?window:parent;
 // Electron exposes the browser API even when its picker cannot complete.
 // Local Windows saves use the native dialog consistently, on every click.
 if(['127.0.0.1','localhost','[::1]'].includes(location.hostname)&&/Win/i.test(host.navigator.platform))return {native:true};
 if(typeof host.showDirectoryPicker!=='function')return {native:true};
 try{return await host.showDirectoryPicker({id:'star7-export',mode:'readwrite',startIn:'downloads'})}
 catch(error){if(['NotSupportedError','SecurityError','InvalidStateError'].includes(error.name))return {native:true};throw error}
}
export async function saveNative(body){
 const response=await fetch('/star7/director/save-native',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),result=await response.json();
 if(!response.ok)throw Error(result.error||'保存失败');
 if(result.cancelled)throw new DOMException('已取消选择目录','AbortError');
 return result.message;
}
async function freshDirectory(parentHandle,name){
 name=safeName(name);let index=1;
 while(true){const candidate=name+(index===1?'':'-'+index);
  try{await parentHandle.getDirectoryHandle(candidate);index++}catch(e){if(e.name!=='NotFoundError')throw e;return {name:candidate,handle:await parentHandle.getDirectoryHandle(candidate,{create:true})}}
 }
}
async function freshFile(directory,name){
 name=safeName(name);const dot=name.lastIndexOf('.'),stem=dot>0?name.slice(0,dot):name,suffix=dot>0?name.slice(dot):'';let index=1;
 while(true){const candidate=stem+(index===1?'':'-'+index)+suffix;
  try{await directory.getFileHandle(candidate);index++}catch(e){if(e.name!=='NotFoundError')throw e;return {name:candidate,handle:await directory.getFileHandle(candidate,{create:true})}}
 }
}
export async function saveResponse(directory,name,response){
 if(!response.ok){let error;try{error=(await response.json()).error}catch{}throw Error(error||'下载失败：'+response.status)}
 const file=await freshFile(directory,name);let writable;
 try{writable=await file.handle.createWritable();if(response.body)await response.body.pipeTo(writable);else{await writable.write(await response.blob());await writable.close()}return file.name}
 catch(error){try{await writable?.abort()}catch{}await directory.removeEntry(file.name);throw error}
}
export async function saveExport(directory,result,zip=false){
 if(directory.native)return saveNative({project_id:result.project_id,filename:result.filename||result.items?.[0]?.filename,zip});
 if(zip){await saveResponse(directory,result.directory_name+'.zip',await fetch(result.zip_url));return 'ZIP 已保存到所选目录：'+directory.name}
 const files=result.items?.length?result.items:[{filename:result.filename,download_url:result.download_url}];let target=directory,created=null;
 if(result.scope!=='one'){created=await freshDirectory(directory,result.directory_name);target=created.handle}
 try{for(const file of files)await saveResponse(target,file.filename,await fetch(file.download_url))}
 catch(error){if(created)await directory.removeEntry(created.name,{recursive:true});throw error}
 return files.length+' 个视频已保存到：'+directory.name+(created?'/'+created.name:'');
}
