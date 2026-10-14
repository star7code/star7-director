// Keep per-mode drafts outside generation parameters, so switching back is exact.
export function changeContinuity(plan,shot,mode,sourceDefault,frame=0,forceSource=false){
 const previous=shot.continuity||{mode:'independent'},drafts={...plan.ui_layout?.continuity_modes},modes={...(Object.hasOwn(drafts,shot.id)?drafts[shot.id]:{})};
 modes[previous.mode]=structuredClone(previous);
 let value=previous.mode===mode?structuredClone(previous):Object.hasOwn(modes,mode)?structuredClone(modes[mode]):mode==='independent'?{mode}:{mode,source_shot:previous.source_shot||sourceDefault};
 value.mode=mode;
 if(mode!=='independent'){
  const earlier=plan.shots.slice(0,plan.shots.findIndex(s=>s.id===shot.id));
  if(forceSource||!earlier.some(s=>s.id===value.source_shot))value.source_shot=sourceDefault;
  if(mode==='selected_frame'&&(forceSource||previous.mode===mode||value.frame===undefined))value.frame=frame;
 }
 modes[mode]=structuredClone(value);drafts[shot.id]=modes;plan.ui_layout={...plan.ui_layout,continuity_modes:drafts};return value;
}
