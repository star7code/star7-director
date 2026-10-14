# Shot handoff

- Independent: no previous shot dependency.
- Selected frame: use a specific zero-based frame from the previous exported video.
- Motion guide: use a time-aligned AV tail as native H3 conditioning.
- Motion guide + redraw: initialize the next AV latent from that tail and use model-local, schedule-aware masks to redraw the seam.

The default context is 22 frames, with 5/39/56 also available. Audio continuation is optional. Redraw ranges from 0.40 to 0.95, default 0.65. Settings are inherited globally; old previous_latent workflows remain supported as motion guide. The first shot stays independent when applying a mode to all shots.

Prefer the actual exported result as the handoff source, including HD/face processing. Re-encode its tail at the next canvas when needed. Only fall back to the base latent if there is no export and that cache exactly matches current base settings. A stale export is rejected. Dependency errors are checked before model loading. The repeated context head is discarded and output is cropped to the requested duration on the 24fps frame grid.

Implementation reuses Apache-2.0 AIMixer AV-tail and redraw helpers (see vendor/aimixer/NOTICE.md), adapting private context markers to native resolved_frame_index and audio keyframes. No global H3 classes are patched. Detected foreign global continuity patches are rejected with a restart instruction instead of stacking wrappers. Older ComfyUI versions without native interior keyframe/reference support must be updated.

Short-window tests cannot establish indefinite chain quality or every GPU/backend. Hard guide may accumulate visual changes; redraw trades stronger following for freer seam reconstruction. Face detection is independent and may produce false positives on non-person imagery; enable face repair only where wanted.
