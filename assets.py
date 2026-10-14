"""Uploaded media lives on the director's data disk, not in source folders."""
import hashlib
import os
import uuid
from pathlib import Path

MEDIA=Path(__file__).resolve().parent/'data'/'media'
EXTENSIONS={'text':{'.txt'},'image':{'.png','.jpg','.jpeg','.webp','.bmp'},'audio':{'.wav','.mp3','.flac','.ogg','.m4a','.mp4','.mov','.webm','.mkv'},'video':{'.mp4','.mov','.webm','.mkv'}}

def upload_target(original,kind):
    if kind not in EXTENSIONS:raise ValueError('Unsupported media type')
    original=Path(original.replace('\\','/')).name
    suffix=Path(original).suffix.lower()
    if suffix not in EXTENSIONS[kind] or (kind=='audio' and suffix in EXTENSIONS['video']):raise ValueError('文件格式与素材类型不匹配')
    MEDIA.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex+suffix
    return MEDIA/token,original

def verify_upload(path,kind):
    if kind=='text':
        if path.stat().st_size>1024**2:raise ValueError('文字素材超过 1 MiB')
        text=path.read_text(encoding='utf-8-sig')
        if not text.strip() or '\0' in text:raise ValueError('文字素材为空或格式无效')
    elif kind=='image':
        from PIL import Image
        with Image.open(path) as im:im.verify()
    else:
        import av
        with av.open(str(path)) as container:
            streams=container.streams.audio if kind=='audio' else container.streams.video
            if not streams:raise ValueError('文件没有对应媒体流')

def finish_upload(path,original,kind,digest,media_root=None):
    verify_upload(path,kind)
    relative=path.relative_to(media_root or MEDIA).as_posix() if media_root is not None or path.is_relative_to(MEDIA) else path.name
    result={'source':'star7-director/'+relative,'type':kind,'original_name':original,'content_hash':digest,'size':path.stat().st_size}
    if kind=='image':
        from PIL import Image,ImageOps
        thumbnail=path.with_name(path.stem+'.thumb.webp')
        with Image.open(path) as image:
            image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((240,240));image.save(thumbnail,'WEBP',quality=82)
        result['thumbnail_source']='star7-director/'+str(Path(relative).with_name(thumbnail.name)).replace('\\','/')
    return result
