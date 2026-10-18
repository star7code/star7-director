"""One decoded final frame as an ordinary numbered H3 appearance reference."""
import re
import threading
import uuid

_preview_lock=threading.Lock()

def preview_file(info,directory,full=True):
    """Decode once per saved video revision; share pixels across both UI modes."""
    import av
    from pathlib import Path
    revision=output_revision(info);directory=Path(directory)
    original=directory/(revision+'.png');thumbnail=directory/(revision+'-thumb.png')
    with _preview_lock:
        if not original.is_file():
            picture=None
            with av.open(str(info['path'])) as container:
                stream=container.streams.video[0];count=info.get('record',{}).get('frame_count',0)
                if count>1:container.seek(int((count-1)/24*av.time_base),backward=True)
                for frame in container.decode(stream):picture=frame.to_image().convert('RGB')
            if picture is None:raise ValueError('上段视频没有可读取画面')
            if output_revision(info)!=revision:raise ValueError('上段视频正在更新，请稍后重新查看')
            directory.mkdir(parents=True,exist_ok=True)
            temporary=original.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            try:picture.save(temporary,format='PNG');temporary.replace(original)
            finally:temporary.unlink(missing_ok=True)
        if not full and not thumbnail.is_file():
            from PIL import Image
            with Image.open(original) as image:
                image.thumbnail((600,600));temporary=thumbnail.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                try:image.save(temporary,format='PNG');temporary.replace(thumbnail)
                finally:temporary.unlink(missing_ok=True)
    return original if full else thumbnail,revision


def output_revision(info):
    """Identify the actual saved clip without decoding any video frames."""
    import hashlib
    from pathlib import Path
    path=Path(info['path']).resolve();stat=path.stat()
    return hashlib.sha256(f'{path}\0{stat.st_mtime_ns}\0{stat.st_ctime_ns}\0{stat.st_size}'.encode()).hexdigest()[:24]

def augment_prompt(prompt,label,frame=None):
    definition=(label+" is the preceding clip's final frame, used as visual evidence for character identity, clothing, lighting and spatial relationships. It is not a locked first frame or a fixed camera viewpoint. Preserve or change framing, visible background and action according to this shot's instructions. If a viewpoint change is requested, show the background appropriate to that viewpoint; do not represent a camera change merely by swapping the actors' physical positions. Actor movement follows the described action.")
    retention=label+': reference - reuse the stated appearance and spatial relationships; allow the requested camera, composition, action and visible background to change.'
    if frame is not None:
        definition=label+" is frame "+str(frame)+" from the preceding clip, used as an ordinary image reference for identity, lighting and spatial relationships. It is not a locked first frame. Follow the requested camera viewpoint and action."
        retention=label+': reference - reuse the selected visual evidence while allowing the described camera viewpoint and action to change.'
    if definition in prompt:return prompt
    if re.search(r'(?mi)^\s*subject_definitions\s*:',prompt):
        section=re.search(r'(?mi)^\s*summary\s*:',prompt)
        if section:prompt=prompt[:section.start()].rstrip()+'\n'+definition+'\n'+prompt[section.start():]
        else:prompt+='\n'+definition
        section=re.search(r'(?mi)^\s*detailed_description\s*:',prompt)
        if section and re.search(r'(?mi)^\s*retention_analysis\s*:',prompt):prompt=prompt[:section.start()].rstrip()+'\n'+retention+'\n'+prompt[section.start():]
        return prompt
    # Text-only shots now have one image reference; promote the three-field
    # format or plain prose to reference generation without duplicating sound.
    fields={}
    matches=list(re.finditer(r'(?mi)^\s*(integrated_multimodal_description|overall_soundscape|non_diegetic_music)\s*:',prompt))
    if matches:
        for i,m in enumerate(matches):fields[m[1]]=prompt[m.end():matches[i+1].start() if i+1<len(matches) else len(prompt)].strip()
    body=fields.get('integrated_multimodal_description',prompt if not matches else prompt[:matches[0].start()].strip())
    return ('subject_definitions: '+definition+'\nsummary: [reference generation] '+body+'\nretention_analysis: '+retention+'\ndetailed_description: '+body+'\noverall_soundscape: '+fields.get('overall_soundscape','Natural ambience appropriate to the described shot.')+'\nnon_diegetic_music: '+fields.get('non_diegetic_music','N/A'))

def load(info,config=None):
    if not info or 'path' not in info:raise ValueError('尾帧画面参考需要前一镜头已生成的成品视频；潜空间缓存不能代替成品尾帧')
    from .continuity import export_tail
    from .reference_size import target_size
    from comfy.utils import common_upscale
    pixels,_=export_tail(info,1,False)
    h,w=pixels.shape[1:3];size=target_size(w,h,'image',config)
    if size!=(w,h):pixels=common_upscale(pixels.permute(0,3,1,2),size[0],size[1],'bilinear','center').permute(0,2,3,1)
    return pixels
