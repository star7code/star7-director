"""Reference resize limits, applied during loading without modifying source files."""
import math
DEFAULTS={'mode':'long_edge','image_long_edge':1600,'video_long_edge':800,'image_mp':1.5,'video_mp':0.5}
def normalize(value=None):
    if value is not None and not isinstance(value,dict):raise ValueError('参考素材尺寸设置必须是对象')
    result={**DEFAULTS,**(value or {})}
    if result['mode'] not in ('long_edge','megapixels'):raise ValueError('参考素材尺寸模式无效')
    for name in ('image_long_edge','video_long_edge'):
        if type(result[name]) is not int or not 32<=result[name]<=8192:raise ValueError('参考最长边必须是 32–8192 的整数')
    for name in ('image_mp','video_mp'):
        v=result[name]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0.1<=v<=64:raise ValueError('参考百万像素必须为 0.1–64')
    return {k:result[k] for k in DEFAULTS}
def target_size(width,height,kind,config=None):
    cfg=normalize(config)
    if cfg['mode']=='long_edge':
        limit=max(32,cfg[kind+'_long_edge']//32*32);scale=min(1,limit/max(width,height));area=math.inf
    else:
        area=cfg[kind+'_mp']*1_000_000;scale=min(1,math.sqrt(area/(width*height)));limit=math.inf
    raw=(width*scale,height*scale)
    if min(raw)<32:return max(1,int(raw[0])),max(1,int(raw[1]))
    w=min(width//32*32,max(32,round(raw[0]/32)*32));h=min(height//32*32,max(32,round(raw[1]/32)*32))
    if w>=h:w=min(w,limit)
    else:h=min(h,limit)
    while w*h>area and (w>32 or h>32):
        options=[(w-32,h)] if w>32 else []
        if h>32:options.append((w,h-32))
        w,h=min(options,key=lambda size:abs(math.log((size[0]/size[1])/(width/height))))
    return int(w),int(h)
class AssetLibrary(list):
    def __init__(self,assets,reference_size=None):super().__init__(assets);self.reference_size=normalize(reference_size)
