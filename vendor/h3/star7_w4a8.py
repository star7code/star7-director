"""Star7's local SM75 grouped-codebook W4A8 adapter for H3."""
from __future__ import annotations

import logging
import os
from collections import Counter

import torch
from comfy_kitchen.tensor.int8_utils import _build_hadamard, _rotate_activation
try:
    from . import h3_preprocess, w4a8_native
except ImportError:
    import h3_preprocess
    import w4a8_native

LOG = logging.getLogger("Star7-H3-W4A8")
_KERNEL = None
_LOAD_ATTEMPTED = False
_COUNTS = Counter()
_REASONS = Counter()


def _enabled():
    return os.environ.get("STAR7_W4A8_BRIDGE", "1").strip().lower() in {"1", "true", "yes", "on"}


def _load_kernel():
    global _KERNEL, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _KERNEL
    _LOAD_ATTEMPTED = True
    try:
        module = w4a8_native.Kernel()
    except (OSError, RuntimeError, ValueError, AttributeError) as exc:
        LOG.warning("[Star7 H3 W4A8] Independent CUDA library unavailable; using upstream CK. Check DLL, manifest and driver: %s", exc)
        return None
    _KERNEL = module
    LOG.debug("[Star7 H3 W4A8] Independent SM75 CUDA library available")
    return _KERNEL


def _fallback(reason):
    _COUNTS["ck_fallbacks"] += 1
    _REASONS[reason] += 1
    if _REASONS[reason] == 1:
        LOG.debug("[Star7 H3 W4A8] CK fallback: %s", reason)
    return None


def runtime_stats():
    keys = ("native_plain_linear_hits", "native_swiglu_fc2_hits",
            "inline_codebook_hits", "staged_codebook_hits", "ck_fallbacks")
    return {**{key: _COUNTS[key] for key in keys}, "fallback_reasons": dict(_REASONS)}


def runtime_summary():
    native = _COUNTS["native_plain_linear_hits"] + _COUNTS["native_swiglu_fc2_hits"]
    reasons = ", ".join(f"{reason} ({count})" for reason, count in sorted(_REASONS.items()))
    return (f"native={native} ck-fallback={_COUNTS['ck_fallbacks']} (cumulative)"
            + (f" reasons=[{reasons}]" if reasons else ""))


def _supported(linear, x, weight, input_act):
    if not _enabled() or getattr(linear, "quant_format", None) != "asym_w4a8_int8":
        return False
    if not x.is_cuda or torch.cuda.get_device_capability(x.device) != (7, 5):
        return False
    if x.dtype is not torch.float16:
        _fallback("activation dtype is not FP16")
        return False
    if weight is None or not hasattr(weight, "_params") or not hasattr(weight, "_qdata"):
        _fallback("weight was dequantized or patched")
        return False
    params = weight._params
    layout = weight._layout_cls
    layout_name = layout if isinstance(layout, str) else layout.__name__
    k = x.shape[-1] // 2 if input_act == "swiglu" else x.shape[-1]
    if (layout_name != "AsymW4A8Int8Layout"
            or params.convrot_groupsize != 256
            or getattr(params, "correction", None) is not None
            or params.codebook is None or params.codebook.numel() != 16
            or params.scale.dtype is not torch.float8_e4m3fn
            or weight._qdata.shape[0] % 8 or weight._qdata.shape[1] * 2 != k
            or k % 256 or params.group_size not in (4, 8, 16)
            or tuple(params.scale.shape) != (weight._qdata.shape[0], k // params.group_size)):
        _fallback("unsupported codebook layout, correction, or group size")
        return False
    if _load_kernel() is None:
        _fallback("native extension unavailable")
        return False
    return True


def try_forward(linear, x, weight, bias, input_act=None):
    """Return None for unsupported contracts; propagate CUDA launch failures."""
    if not _supported(linear, x, weight, input_act):
        return None
    kernel = _KERNEL
    params = weight._params
    original_shape = x.shape
    x2d = x.reshape(-1, x.shape[-1]).contiguous()
    if input_act == "swiglu":
        # Preserve FP16 Exact's FP32 SwiGLU and the FP16 boundary before
        # ConvRot. The fused FHT quantizer has different rounding here.
        fused = h3_preprocess.swiglu_scaled(x2d)
        if fused is None:
            gate, up = x2d.chunk(2, dim=-1)
            x2d = (torch.nn.functional.silu(gate.float()) * up.float() / 256.0).half()
        else:
            x2d = fused
    elif input_act is not None:
        return _fallback("unsupported fused activation")
    hadamard = _build_hadamard(256, device=x.device, dtype=x.dtype)
    rotated = _rotate_activation(x2d, hadamard, 256)
    qactivation, activation_scale = kernel.turing_fp16_int8_quantize(rotated)
    result = kernel.turing_fp16_codebook_w4a8_linear(
        qactivation, weight._qdata, activation_scale,
        params.scale.view(torch.uint8), params.s_channel, params.codebook,
        bias, params.group_size, 0,
    )
    _COUNTS["native_swiglu_fc2_hits" if input_act == "swiglu" else "native_plain_linear_hits"] += 1
    inline = x2d.shape[0] > 8192 and params.group_size == 16
    _COUNTS["inline_codebook_hits" if inline else "staged_codebook_hits"] += 1
    if input_act == "swiglu":
        result = result.to(torch.float32).mul_(256.0)
    return result.reshape(*original_shape[:-1], weight._qdata.shape[0])
