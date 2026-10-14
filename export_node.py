"""Output-only ComfyUI job; no model or sampler dependencies."""
import json,shutil
from pathlib import Path
from .core import identifier
from .storage import Storage
from .runtime import data_root

class Star7DirectorVideoExport:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'export_json':('STRING',{'multiline':True})}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('保存位置',)
    FUNCTION='save'
    OUTPUT_NODE=True
    CATEGORY='Star7/导演台'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def save(self,export_json):
        import folder_paths,av
        from .combine import combine,outdated_shots,select_clips,assembly_message
        from .output_paths import reserve_film
        body=json.loads(export_json);plan=body['plan'];pid=identifier(plan['id']);root=Path(folder_paths.get_output_directory()).resolve();store=Storage(data_root());scope=body['scope']
        if scope=='all':
            selection=select_clips(plan,root);included={c['id'] for c in selection['clips']}
            stale=[sid for sid in outdated_shots(plan,body.get('prompt',{})) if sid in included];path=combine(plan,body.get('prompt',{}),root,selection)
            message=assembly_message(selection,stale)
        elif scope=='one':
            sid=identifier(body['shot_id']);record=store.latest_output(pid,sid)
            if not record:raise ValueError('当前镜头尚未生成视频')
            source=Path(record['path']).resolve()
            if not source.is_relative_to(root) or not source.is_file():raise ValueError('当前镜头成品文件不可用')
            from .output_paths import shot_code
            path=reserve_film(root,shot_code(sid)+'-export')
            try:shutil.copyfile(source,path)
            except Exception:path.unlink(missing_ok=True);raise
            store.record_film(pid,path);stale=[];message='已导出当前镜头最近生成的视频。'
        else:raise ValueError('导出范围无效')
        relative=path.relative_to(root)
        with av.open(str(path)) as c:fps=float(c.streams.video[0].average_rate or 24)
        from server import PromptServer
        assets=bool(getattr(getattr(PromptServer.instance,'asset_manager',None),'enabled',False))
        info={'filename':relative.name,'subfolder':relative.parent.as_posix(),'type':'output','format':'video/h264-mp4','frame_rate':fps}
        result={'project_id':pid,'scope':scope,'filename':path.name,'message':message,'outdated_shots':stale,'assets_enabled':assets}
        if scope=='all':result.update(included_shots=[c['id'] for c in selection['clips']],missing_shots=selection['missing_shots'],unavailable_shots=selection['unavailable_shots'])
        return {'ui':{'gifs':[info],'star7_export':[result]},'result':(str(path),)}
