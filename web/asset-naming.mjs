export function initializeMaterialSlots(assets,kind,label){
 const cards=assets.filter(a=>a.kind===kind),used=new Set(),pending=[];
 for(const a of cards){const match=a.name.match(new RegExp('^'+label+'(\\d+)$'));const n=Number.isSafeInteger(a.sequence)&&a.sequence>0?a.sequence:Number(match?.[1])||0;if(n&&!used.has(n)){a.sequence=n;used.add(n)}else pending.push(a)}
 let n=1;for(const a of pending){while(used.has(n))n++;a.sequence=n;used.add(n++)}return used;
}
export function nextMaterialName(assets,label,kind){const slots=kind?initializeMaterialSlots(assets,kind,label):new Set(assets.map(a=>a.sequence).filter(n=>Number.isSafeInteger(n)&&n>0)),used=new Set(assets.flatMap(a=>[a.name,a.id]));let n=1;while(slots.has(n)||used.has(label+n))n++;return label+n}
export function retireNameAlias(plan,name,excludeId=null){for(const asset of plan.assets){if(asset.id===excludeId||!(asset.aliases||[]).includes(name))continue;const replace=text=>String(text||'').replace(/@(?:\{([^}]+)\}|([\w\u4e00-\u9fff-]+))/g,(token,braced,plain)=>(braced||plain)===name?'@{'+asset.id+'}':token);for(const shot of plan.shots||[])shot.prompt=replace(shot.prompt);for(const card of plan.assets)if(card.description)card.description=replace(card.description);asset.aliases=asset.aliases.filter(a=>a!==name)}}
