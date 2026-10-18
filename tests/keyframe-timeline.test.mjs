import assert from 'node:assert/strict';
import {timelineErrors,timelineLayout,changeTimelineDuration,keyframeTime,currentFrameAssets} from '../web/keyframe-timeline.mjs';
assert.equal(keyframeTime(4.166666666666667),4.2);
assert.equal(keyframeTime(7.1499999999999995),7.2);
assert.equal(keyframeTime(.1+.2),.3);
const shot={input_mode:'keyframes',duration:15,keyframes:{last:{source:'tail.png'}},keyframe_points:[{id:'middle',time_seconds:12,source:'middle.png'}]};
changeTimelineDuration(shot,10);
assert.equal(shot.keyframe_points.length,1);
assert.equal(shot.keyframe_points[0].time_seconds,12);
assert.equal(shot.keyframes.last.source,'tail.png');
assert.equal(timelineErrors(shot).length,1);
assert.equal(timelineLayout(shot).extent,12);
assert.equal(timelineLayout(shot).items.find(p=>p.id==='last').time,10);
assert.equal(currentFrameAssets(shot).find(p=>p.name==='尾帧').item.source,'tail.png');
shot.keyframe_points[0].time_seconds=8;
assert.deepEqual(timelineErrors(shot),[]);
assert.equal(timelineLayout(shot).extent,10);
shot.keyframe_points.push({id:'another',time_seconds:8.001,source:'another.png'});
assert.match(timelineErrors(shot)[0],/同一帧/);
const items=timelineLayout(shot).items.filter(p=>!p.endpoint);
assert.notEqual(items[0].lane,items[1].lane);
shot.input_mode='reference';assert.deepEqual(timelineErrors(shot),[]);
console.log('PASS: duration shrink keeps the tail endpoint, ordinary overflow recovers, close frames use separate lanes, frame collisions block generation.');

const endpointShot={input_mode:'keyframes',duration:12,keyframes:{first:{from_previous:true},last:{source:'end',thumbnail_source:'thumb'}},keyframe_points:[{id:'late',source:'late',time_seconds:11}]};
const endpoints=endpointShot.keyframes,ordinary=JSON.stringify(endpointShot.keyframe_points);
for(const duration of [10,12,8,10]){changeTimelineDuration(endpointShot,duration);assert.strictEqual(endpointShot.keyframes,endpoints);assert.equal(JSON.stringify(endpointShot.keyframe_points),ordinary);assert.equal(timelineLayout(endpointShot).items.find(p=>p.id==='last').time,duration);}
const noTail={input_mode:'keyframes',duration:12,keyframe_points:[]};changeTimelineDuration(noTail,10);assert.equal(noTail.keyframes,undefined);assert.deepEqual(noTail.keyframe_points,[]);
console.log('PASS: repeated shorten/extend preserves endpoint metadata, previous-shot first frame and all ordinary timestamps; absent tail stays absent.');

const stable={input_mode:'keyframes',duration:8,keyframes:{first:{source:'first.png'},last:{source:'last.png'}},keyframe_points:[
 {id:'a',time_seconds:1,source:'a.png'},{id:'b',time_seconds:3,source:'b.png'},{id:'c',time_seconds:4,source:'c.png'}]};
const rows=layout=>Object.fromEntries(layout.items.map(item=>[item.id,item.lane]));
const noOverlap=layout=>{for(const a of layout.items)for(const b of layout.items)if(a!==b&&a.lane===b.lane)assert(Math.abs(a.x-b.x)>=116-1e-8);};
let layout=timelineLayout(stable),initial=rows(layout);
for(const time of [2,2.1,2.2,2.1,2,1,2]){
 // 2 seconds crosses the old greedy packing threshold; 2.2 genuinely
 // collides with c, so only the moved a may need another row.
 stable.keyframe_points[0].time_seconds=time;
 const next=timelineLayout(stable,64,layout.items);noOverlap(next);
 for(const id of ['first','b','c','last'])assert.equal(rows(next)[id],rows(layout)[id],id+' jumped after another card moved');
 if(time===2&&layout.items.find(i=>i.id==='a').lane===initial.a)assert.deepEqual(rows(next),initial);
 layout=next;
}
// Crossing another keyframe changes chronological order, never its reference ID
// or the untouched cards' rows. Same-frame validation still runs independently.
stable.keyframe_points[0].time_seconds=3.1;
let next=timelineLayout(stable,64,layout.items);noOverlap(next);
assert.deepEqual(next.items.map(i=>i.id),['first','b','a','c','last']);
for(const id of ['first','b','c','last'])assert.equal(rows(next)[id],rows(layout)[id]);
stable.keyframe_points[0].time_seconds=3;assert(timelineErrors(stable).some(e=>e.includes('同一帧')));
next=timelineLayout(stable,20,next.items);noOverlap(next);
stable.keyframe_points=stable.keyframe_points.filter(p=>p.id!=='a');
next=timelineLayout(stable,20,next.items);noOverlap(next);
assert.deepEqual([...new Set(next.items.map(i=>i.lane))].sort((a,b)=>a-b),Array.from({length:next.lanes},(_,i)=>i));
assert(!JSON.stringify(stable).includes('lane'));
console.log('PASS: threshold jitter, actual collisions, chronological crossing, resize and deletion preserve stable display rows without changing shot data.');

// Reproduce the user's 12-second screenshot, including its stale third row.
const times=[1.7,2.8,4.2,4.8,5.6,6.3,7,7.8,8.8,9.9];
const crowded={input_mode:'keyframes',duration:12,keyframes:{first:{source:'first'},last:{source:'last'}},keyframe_points:times.map((t,i)=>({id:'k'+(i+1),time_seconds:t,source:'image'+i}))};
const screenshotRows=[0,0,1,0,1,0,1,0,1,2,0,0];
const previous=[{id:'first',time:0},...times.map((time,i)=>({id:'k'+(i+1),time})),{id:'last',time:12}].map((item,i)=>({...item,lane:screenshotRows[i]}));
const content=JSON.stringify(crowded);let compact=timelineLayout(crowded,131,previous);
assert.equal(compact.lanes,2);assert.equal(rows(compact).k9,0);noOverlap(compact);
for(const item of previous)if(item.id!=='k9')assert.equal(rows(compact)[item.id],item.lane,'unrelated screenshot card moved');
assert.equal(JSON.stringify(crowded),content);
for(const time of [8.7,8.8,8.9,8.8]){crowded.keyframe_points[8].time_seconds=time;compact=timelineLayout(crowded,131,compact.items);assert.equal(rows(compact).k9,0);noOverlap(compact);}
crowded.keyframe_points[8].time_seconds=9.1;compact=timelineLayout(crowded,131,compact.items);assert.equal(rows(compact).k9,1);noOverlap(compact);
crowded.keyframe_points[8].time_seconds=9;compact=timelineLayout(crowded,131,compact.items);assert.equal(rows(compact).k9,1,'near-boundary card bounced up too early');
crowded.keyframe_points[8].time_seconds=8.9;compact=timelineLayout(crowded,131,compact.items);assert.equal(rows(compact).k9,0,'card did not return when the gap cleared');noOverlap(compact);
console.log('PASS: screenshot third row collapses to two with only keyframe9 moving, generation data unchanged; 8.7/8.8/8.9 stays stable and a real collision recovers with hysteresis.');
const deletedRow={duration:4,keyframes:{},keyframe_points:[{id:'remaining',time_seconds:2}]};
const restored=timelineLayout(deletedRow,64,[{id:'first',time:0,lane:0},{id:'remaining',time:2,lane:2},{id:'last',time:4,lane:0}]);
assert.equal(restored.lanes,1);assert.equal(rows(restored).remaining,0);noOverlap(restored);
console.log('PASS: deleting the only card in a middle row reclaims the hole without a sparse-row exception.');

// Both endpoints own the bottom layer even when old display state put them elsewhere.
const baselineShot={duration:4,keyframe_points:[{id:'near',time_seconds:.1,source:'near'}]};
const beforeBaseline=JSON.stringify(baselineShot);
for(const pixels of [64,20,2]){
 const result=timelineLayout(baselineShot,pixels,[{id:'first',time:0,lane:2},{id:'last',time:4,lane:1},{id:'near',time:.1,lane:0}]);
 const first=result.items.find(i=>i.id==='first'),last=result.items.find(i=>i.id==='last');
 assert.equal(first.lane,0);assert.equal(last.lane,0);assert(result.items.find(i=>i.id==='near').lane>0);
 assert(last.x-first.x>=56*(first.scale+last.scale)-1e-8);
 assert.equal(JSON.stringify(baselineShot),beforeBaseline);
}
console.log('PASS: endpoints always own the baseline; compressed endpoints fit; ordinary cards stack upward without changing generation data.');

const dense={duration:8,keyframe_points:[{id:'left',time_seconds:2},{id:'right',time_seconds:3.85}]};
const denseLayout=timelineLayout(dense);assert.equal(rows(denseLayout).left,0);assert.equal(rows(denseLayout).right,0);noOverlap(denseLayout);
console.log('PASS: cards 118.4px apart share a layer with a visible gap.');
