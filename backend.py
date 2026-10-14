"""Private implementation registry; never registers extra ComfyUI nodes."""
import importlib

H3_IMPLEMENTATIONS={
    'MiniMaxH3MaterialPromptStar7':'h3_face_refine_star7',
    'MiniMaxH3OneClickHDStar7':'h3_latent_upscale_star7',
    'MiniMaxH3FaceRefineLatentStar7':'h3_face_refine_star7',
    'MiniMaxH3ChunkedDecodeStar7':'h3_stream_decode_star7',
    'MiniMaxH3LivePreviewStar7':'h3_live_preview',
}
PRIVATE_IMPLEMENTATIONS={
    'Star7DirectorPlan':'desk',
    'Star7DirectorConditioning':'runtime','Star7DirectorTrim':'runtime',
    'Star7DirectorComplete':'runtime','Star7DirectorBaseCache':'runtime',
    'Star7DirectorSamplingModel':'runtime','Star7DirectorSaveVideo':'save_video',
    'Star7DirectorStage':'stage','Star7DirectorLivePreview':'stage',
}
def implementation(name):
    if name in H3_IMPLEMENTATIONS:
        try:module=importlib.import_module('.vendor.h3.'+H3_IMPLEMENTATIONS[name],__package__)
        except ModuleNotFoundError as error:
            raise ValueError('导演台内置 H3 实现缺少 Python 模块 '+str(error.name)+'；请用 ComfyUI 的 Python 安装本项目 requirements.txt') from error
        return getattr(module,name)
    if name in PRIVATE_IMPLEMENTATIONS:
        return getattr(importlib.import_module('.'+PRIVATE_IMPLEMENTATIONS[name],__package__),name)
    return None
