"""Reuse VHS encoding privately; expose only the correctly named final file."""
import copy,shutil,uuid
from pathlib import Path
from .runtime import registry,data_root
from .output_paths import reserve_generated

class Star7DirectorSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):
        schema=copy.deepcopy(registry('VHS_VideoCombine').INPUT_TYPES())
        schema['required'].update(director_plan=('STAR7_DIRECTOR_PLAN',),shot_id=('STRING',{'default':'shot_001'}))
        return schema
    RETURN_TYPES=('VHS_FILENAMES',)
    OUTPUT_NODE=True
    FUNCTION='save'
    CATEGORY='Star7/导演台'
    def save(self,director_plan,shot_id,**kwargs):
        import folder_paths
        from .core import identifier
        identifier(director_plan['id']);identifier(shot_id)
        temp_root=Path(folder_paths.get_temp_directory()).resolve();relative='star7-director-staging/'+uuid.uuid4().hex;private=(temp_root/relative).resolve()
        if not private.is_relative_to(temp_root):raise ValueError('临时视频路径无效')
        private.mkdir(parents=True,exist_ok=False);target=None
        try:
            kwargs=dict(kwargs);kwargs.update(save_output=False,filename_prefix=relative+'/clip')
            adapter=registry('VHS_VideoCombine')();result=getattr(adapter,adapter.FUNCTION)(**kwargs)
            files=result['result'][0][1];sources=[Path(p).resolve() for p in files]
            if any(not p.is_relative_to(private) for p in sources):raise ValueError('视频编码器返回了不属于当前任务的文件')
            source=next((p for p in reversed(sources) if p.suffix.lower()=='.mp4' and p.is_file()),None)
            if source is None:raise ValueError('导演台需要MP4输出，请选择video/h264-mp4格式')
            root=Path(folder_paths.get_output_directory()).resolve();target=reserve_generated(root,data_root(),director_plan['id'],shot_id)
            shutil.copyfile(source,target);relative_path=target.relative_to(root)
            preview={'filename':target.name,'subfolder':relative_path.parent.as_posix(),'type':'output','format':kwargs.get('format','video/h264-mp4'),'frame_rate':kwargs.get('frame_rate',24)}
            return {'ui':{'gifs':[preview]},'result':((True,[str(target)]),)}
        except Exception:
            if target:target.unlink(missing_ok=True)
            raise
        finally:
            # Only this freshly-created UUID staging directory is removed.
            if private.is_relative_to(temp_root) and private.parent.name=='star7-director-staging':shutil.rmtree(private)
