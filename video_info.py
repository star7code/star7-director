"""Preview metadata comes from the finished file, never current UI settings."""
from pathlib import Path

def finished_info(record,store=None,project=None,shot=None):
    import av
    path=Path(record['path'])
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        info={'width':stream.codec_context.width,'height':stream.codec_context.height,'fps':float(stream.average_rate or 24),'post':record.get('post')}
    # Legacy records did not store processing flags. A larger finished canvas
    # than its preceding native H3 base cache establishes HD, but not face repair.
    # Read only the safetensors header; do not load latent tensors or guess from
    # current project settings, which the user may already have changed.
    if info['post'] is None and store and project and shot:
        rows=[r for r in store.stages(project) if r['shot']==shot and r['stage']=='base']
        for row in reversed(rows):
            artifact=(store.root/row['artifact']).resolve()
            if not artifact.is_relative_to(store.root.resolve()) or not artifact.is_file() or artifact.stat().st_mtime_ns>path.stat().st_mtime_ns:continue
            try:
                import json
                from safetensors import safe_open
                with safe_open(str(artifact),framework='pt',device='cpu') as f:
                    tree=json.loads(f.metadata()['director_tree'])['items']['samples']
                    video=tree['items'][0] if tree['type']=='nested' else tree
                    shape=f.get_slice(video['name']).get_shape()
                if len(shape)==5 and shape[1]==24:
                    h,w=shape[-2]*16,shape[-1]*16
                    if info['width']>=w and info['height']>=h and (info['width']>w or info['height']>h):
                        info['post']={'hd':True,'face':None};info['legacy_stage']=True
                break
            except (KeyError,ValueError,OSError,TypeError):continue
    return info
