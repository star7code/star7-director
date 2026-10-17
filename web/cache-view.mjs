const element=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el};
export function renderCache(root,value,{library=false,project,busy=false,formatBytes,onClear}){
 const get=id=>root.querySelector('#'+id),packs=value.packages||[];
 const filter=get('cache-stage');filter.disabled=busy||!value.cache_stage_filter;if(!value.cache_stage_filter)filter.value='all';
 const amount=item=>filter.value==='all'?(Number(item.bytes)||0):(Number(item.stage_bytes?.[filter.value])||0);
 get('cache-checkpoints').hidden=library;
 get('cache-project-footer').hidden=library;
 get('cache-package-count').textContent=packs.length+' 个素材包';
 get('cache-clear-temp').disabled=busy||!packs.some(p=>!p.in_use);
 const packages=get('cache-packages');packages.replaceChildren();
 if(!packs.length)packages.append(element('p','暂无导入素材包。','cache-empty'));
 for(const pack of packs){
  const row=element('div',undefined,'package-cache-row'),info=element('div',undefined,'cache-item-info');
  info.append(element('b',pack.name),element('small',formatBytes(pack.material_bytes)+(pack.in_use?' · 使用中':' · 未使用')));
  const button=element('button','删除此包');button.type='button';button.disabled=busy||pack.in_use;
  button.onclick=()=>onClear('package',pack.id);row.append(info,button);packages.append(row);
 }
 const projects=value.projects||[],current=projects.find(p=>p.current)||{id:project.id,name:project.title||project.id,bytes:value.checkpoint_bytes||0,current:true};
 const rows=[current,...projects.filter(p=>!p.current)],list=get('cache-projects');list.replaceChildren();
 const amounts=new Map(rows.map(p=>[p.id,amount(p)]));
 const choices=()=>[...list.querySelectorAll('[data-cache-project]')];
 const all=get('cache-select-all');
 const updateSelection=()=>{
  const available=choices().filter(c=>!c.disabled),selected=choices().filter(c=>c.checked);
  all.checked=!!available.length&&available.every(c=>c.checked);all.indeterminate=selected.length>0&&!all.checked;
  all.disabled=busy||!available.length;
  get('cache-selected-summary').textContent=selected.length?'已选 '+selected.length+' 个项目 · '+formatBytes(selected.reduce((n,c)=>n+amounts.get(c.dataset.cacheProject),0)):'选择需要清理的项目';
  get('cache-clear-selected').disabled=busy||!selected.length;
 };
 for(const item of rows){
  const row=element('div',undefined,'checkpoint-project-row'),label=element('label',undefined,'cache-project-selector');
  const choice=element('input');choice.type='checkbox';choice.dataset.cacheProject=item.id;
  choice.setAttribute('aria-label','选择 '+item.name+' 的辅助缓存');choice.disabled=busy||item.current||item.protected||!amount(item);choice.onchange=updateSelection;
  const info=element('span',undefined,'cache-item-info'),heading=element('span',undefined,'cache-project-heading');
  heading.append(element('b',item.name));if(item.current)heading.append(element('span','当前项目','cache-current-badge'));
  else if(item.protected)heading.append(element('span','生成／排队中','cache-current-badge'));
  info.append(heading,element('small',item.id));
  if(item.stage_bytes){const names={base:'一采',hd:'二采',face:'修脸',final:'运动衔接'};info.append(element('small',Object.entries(item.stage_bytes).filter(([,bytes])=>bytes>0).map(([stage,bytes])=>(names[stage]||stage)+' '+formatBytes(bytes)).join(' · ')))}
  label.append(choice,info);
  row.append(label,element('strong',formatBytes(amount(item)),'cache-item-size'));list.append(row);
 }
 all.onchange=()=>{for(const choice of choices())if(!choice.disabled)choice.checked=all.checked;updateSelection()};
 get('cache-checkpoint-total').textContent='合计 '+formatBytes(rows.reduce((n,p)=>n+amount(p),0));
 get('cache-clear-latent').hidden=true;
 get('cache-clear-other').disabled=busy||!rows.some(p=>!p.current&&!p.protected&&amount(p));
 filter.onchange=()=>renderCache(root,value,{library,project,busy,formatBytes,onClear});
 updateSelection();
}
