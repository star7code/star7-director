"""Read-only native H3 checks. Never patch shared model classes."""
CTX_FRAME_KEY='star7_context_index'
CTX_AUDIO_END_KEY='star7_context_audio_end'
def ensure_layout_patch():
    import inspect
    from comfy.ldm.minimax.model import PackedLayout
    if any(getattr(PackedLayout.__init__,key,False) for key in ('_h3_motion_context_layout_patch','_h3_director_continuity_layout_patch')):raise RuntimeError('检测到其他运动衔接插件的全局H3补丁。Star7不叠加补丁，请重启ComfyUI恢复原生路径后使用运动模式')
    source=inspect.getsource(PackedLayout.__init__)
    if 'resolved_frame_index' not in source:raise RuntimeError('当前 ComfyUI H3 不支持内部关键帧位置，请更新 ComfyUI 后使用运动引导')
    return True
def ensure_payload_patch():
    import inspect
    from comfy.model_base import MiniMaxH3
    if any(getattr(MiniMaxH3.extra_conds,key,False) for key in ('_h3_motion_context_payload_patch','_h3_director_continuity_payload_patch')):raise RuntimeError('检测到其他插件的全局H3条件补丁，请重启ComfyUI后使用Star7运动模式')
    source=inspect.getsource(MiniMaxH3.extra_conds)
    if 'minimax_keyframes' not in source or 'minimax_refs' not in source or 'payload.get("cond_video_latents", []) +' not in source:raise RuntimeError('当前 ComfyUI H3 不支持素材与关键帧同时载入，请更新 ComfyUI')
    return True
