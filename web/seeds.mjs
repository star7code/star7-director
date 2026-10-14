export const MAX_SEED=Number.MAX_SAFE_INTEGER;
export function nextSeed(seed,mode,random=()=>{const words=new Uint32Array(2);crypto.getRandomValues(words);return (words[0]&0x1fffff)*4294967296+words[1]}){
 if(mode==='increment')return seed===MAX_SEED?0:seed+1;
 if(mode==='decrement')return seed===0?MAX_SEED:seed-1;
 if(mode==='randomize')return random();
 return seed;
}
export function prepareRegeneration(shot){if((shot.seed_control||'fixed')!=='fixed'&&Number.isSafeInteger(shot.next_seed))shot.seed=shot.next_seed;delete shot.next_seed;}
export function afterGeneration(shot){shot.next_seed=nextSeed(shot.seed||0,shot.seed_control||'fixed');}
