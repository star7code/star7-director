"""Keep a supplied last frame when H3 rounds the native temporal length up."""
def fit_endpoints(images,audio,frames):
    import torch,subprocess,imageio_ffmpeg
    count=len(images)
    if count<=frames:return images,audio
    indices=torch.linspace(0,count-1,frames,device=images.device).round().long() if frames>1 else torch.tensor([count-1],device=images.device)
    output=dict(audio);rate=audio['sample_rate'];wave=audio['waveform'];target=round(frames/24*rate);source=round(count/24*rate)
    factor=count/frames;filters=[]
    while factor>2:filters.append('atempo=2');factor/=2
    filters.append('atempo='+str(factor));rows=[]
    for row in wave:
        pcm=row[...,:source].detach().float().cpu().T.contiguous().numpy().tobytes();channels=row.shape[0]
        command=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','f32le','-ar',str(rate),'-ac',str(channels),'-i','pipe:0','-af',','.join(filters),'-f','f32le','pipe:1']
        result=subprocess.run(command,input=pcm,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('首尾帧音视频时长对齐失败：'+result.stderr.decode(errors='replace'))
        import numpy as np
        samples=torch.from_numpy(np.frombuffer(result.stdout,dtype=np.float32).copy().reshape(-1,channels).T)
        if samples.shape[-1]<target:samples=torch.nn.functional.pad(samples,(0,target-samples.shape[-1]))
        rows.append(samples[...,:target])
    output['waveform']=torch.stack(rows).to(device=wave.device,dtype=wave.dtype)
    return images[indices],output
