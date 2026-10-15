"""Disposable, seeded guide perturbation; never changes saved video or audio.

Inspired by the video-only temporal taper described by H3 Context Noise and
H3 Context Loop. Independent implementation; no external node dependency.
"""
def taper_guides(blocks,strength,seed):
    import torch
    if not blocks or strength==0:return blocks
    generator=torch.Generator(device='cpu').manual_seed(int(seed)&0xffffffffffffffff)
    count=len(blocks);ramp=min(3,count);result=[]
    for index,block in enumerate(blocks):
        # The guide nearest the new clip stays clean to preserve the join.
        amount=float(strength)*min(1.,(count-1-index)/max(1,ramp-1))
        if amount==0:result.append(block);continue
        value=block.float();mean=value.mean(dim=(-2,-1),keepdim=True)
        std=value.std(dim=(-2,-1),keepdim=True,unbiased=False)
        noise=torch.randn(block.shape,generator=generator,device='cpu',dtype=torch.float32).to(block.device)
        noise=noise*std+mean
        result.append((value*(1-amount)+noise*amount).to(block.dtype))
    return result
