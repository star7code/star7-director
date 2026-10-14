"""SM75 preprocessing; leaves other architectures and attention overrides unchanged."""
import ctypes
import dataclasses
import hashlib
import json
import logging
from pathlib import Path

import torch

_LIBRARY = None
_CHECKED = False
_COMPACT_CHECKED = {}
_LOG = logging.getLogger('Star7-H3-Preprocess')


def available(device):
    global _LIBRARY, _CHECKED
    if device.type != 'cuda' or torch.cuda.get_device_capability(device) != (7, 5):
        return False
    if not _CHECKED:
        _CHECKED = True
        try:
            root = Path(__file__).parent / 'bin'
            manifest = json.loads((root / 'h3_preprocess_manifest.json').read_text(encoding='utf-8-sig'))
            path = root / manifest['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
                raise RuntimeError('H3 preprocessing library checksum mismatch')
            lib = ctypes.CDLL(str(path))
            lib.star7_h3_preprocess_abi.restype = ctypes.c_int
            if lib.star7_h3_preprocess_abi() != 1:
                raise RuntimeError('H3 preprocessing ABI mismatch')
            lib.star7_h3_quant_q.argtypes = [ctypes.c_void_p] * 3 + [ctypes.c_int] * 2 + [ctypes.c_int64] * 3 + [ctypes.c_uint64]
            lib.star7_h3_quant_q.restype = ctypes.c_int
            lib.star7_h3_swiglu_fp16.argtypes = [ctypes.c_void_p] * 2 + [ctypes.c_int] * 2 + [ctypes.c_uint64]
            lib.star7_h3_swiglu_fp16.restype = ctypes.c_int
            lib.star7_h3_k_anchor.argtypes = [ctypes.c_void_p] * 2 + [ctypes.c_int, ctypes.c_uint64]
            lib.star7_h3_k_anchor.restype = ctypes.c_int
            lib.star7_h3_quant_k.argtypes = [ctypes.c_void_p] * 4 + [ctypes.c_int] * 2 + [ctypes.c_uint64]
            lib.star7_h3_quant_k.restype = ctypes.c_int
            _LIBRARY = lib
        except (OSError, RuntimeError, AttributeError, ValueError) as error:
            _LOG.warning('[Star7 H3 Preprocess] Native library unavailable: %s', error)
    return _LIBRARY is not None


def memory_pressure(x, heads):
    if x.device.type != 'cuda':
        return False
    fixed_bytes = x.shape[0] * heads * 128 * x.element_size() * 3
    if fixed_bytes < 128 * 2**20:
        return False
    free, _ = torch.cuda.mem_get_info(x.device)
    cached = torch.cuda.memory_reserved(x.device) - torch.cuda.memory_allocated(x.device)
    return fixed_bytes > (free + cached) // 3


def compact_available(device):
    if not available(device):
        return False
    index = device.index if device.index is not None else torch.cuda.current_device()
    if index not in _COMPACT_CHECKED:
        import comfy_kitchen
        _COMPACT_CHECKED[index] = False
        try:
            with torch.cuda.device(device):
                probe = (torch.arange(1025 * 128, device=device, dtype=torch.float32) % 31 - 15).half().reshape(1, 1, 1025, 128)
                reference = comfy_kitchen.prequantize_int8_attention(probe, probe, probe)
                compact = CompactQK(probe.shape, device)
                positions = torch.arange(9, device=device) * 1024 // 8
                compact.prepare_key(probe.index_select(2, positions))
                for start in range(0, 1025, 256):
                    compact.write(start, probe[:, :, start:start + 256])
                    compact.write_key(start, probe[:, :, start:start + 256])
                if not all(torch.equal(a, b) for a, b in ((compact.data, reference.q),
                    (compact.scale, reference.q_scale), (compact.key, reference.k),
                    (compact.key_scale, reference.k_scale))):
                    raise RuntimeError('Installed Kitchen quantization differs from the compact kernel')
                _COMPACT_CHECKED[index] = True
        except (AttributeError, RuntimeError) as error:
            _LOG.warning('[Star7 H3 Preprocess] Compact Q/K disabled; preserving normal CK: %s', error)
    return _COMPACT_CHECKED[index]


def swiglu_scaled(x):
    if x.dtype != torch.float16 or not available(x.device):
        return None
    x = x.contiguous()
    output = x.new_empty(x.shape[0], x.shape[1] // 2)
    error = _LIBRARY.star7_h3_swiglu_fp16(x.data_ptr(), output.data_ptr(), x.shape[0],
                                        output.shape[1], torch.cuda.current_stream(x.device).cuda_stream)
    if error:
        raise RuntimeError(f'Star7 fused SwiGLU CUDA error {error}')
    return output


class CompactQK:
    def __init__(self, shape, device):
        self.data = torch.empty(shape, dtype=torch.int8, device=device)
        self.scale = torch.empty(shape[0], shape[1], ((shape[2] + 127) // 128) * 32,
                                 dtype=torch.float32, device=device)
        self.key = None

    def prepare_key(self, samples):
        samples = samples.contiguous()
        heads = samples.shape[1]
        indices = torch.empty(heads, device=samples.device, dtype=torch.int32)
        error = _LIBRARY.star7_h3_k_anchor(samples.data_ptr(), indices.data_ptr(), heads,
                                          torch.cuda.current_stream(samples.device).cuda_stream)
        if error:
            raise RuntimeError(f'Star7 K anchor CUDA error {error}')
        head_ids = torch.arange(heads, device=samples.device)
        self.anchor = samples[0, head_ids, indices.clamp_min(0).long()].clone()
        self.anchor.masked_fill_((indices < 0)[:, None], 0)
        self.key = torch.empty_like(self.data)
        self.key_scale = torch.empty(1, heads, ((self.data.shape[2] + 127) // 128) * 4,
                                     device=samples.device, dtype=torch.float32)

    def write_key(self, start, key):
        key = key.contiguous()
        length = key.shape[2]
        packed = torch.empty_like(key, dtype=torch.int8)
        scales = torch.empty(1, key.shape[1], ((length + 127) // 128) * 4,
                             device=key.device, dtype=torch.float32)
        error = _LIBRARY.star7_h3_quant_k(key.data_ptr(), self.anchor.data_ptr(), packed.data_ptr(),
                                         scales.data_ptr(), key.shape[1], length,
                                         torch.cuda.current_stream(key.device).cuda_stream)
        if error:
            raise RuntimeError(f'Star7 compact K CUDA error {error}')
        self.key[:, :, start:start + length].copy_(packed)
        offset = start // 128 * 4
        self.key_scale[:, :, offset:offset + scales.shape[-1]].copy_(scales)

    def write(self, start, query):
        query = query.contiguous()
        length = query.shape[2]
        packed = torch.empty_like(query, dtype=torch.int8)
        scale = torch.empty(1, query.shape[1], ((length + 127) // 128) * 32,
                            device=query.device, dtype=torch.float32)
        error = _LIBRARY.star7_h3_quant_q(query.data_ptr(), packed.data_ptr(), scale.data_ptr(),
                                         query.shape[1], length, *query.stride()[:3],
                                         torch.cuda.current_stream(query.device).cuda_stream)
        if error:
            raise RuntimeError(f'Star7 compact Q CUDA error {error}')
        self.data[:, :, start:start + length].copy_(packed)
        offset = start // 128 * 32
        self.scale[:, :, offset:offset + scale.shape[-1]].copy_(scale)

    def prequantize_value(self, key, value):
        import comfy_kitchen
        # Q/K use the complete sequence's anchor and aligned scale blocks;
        # Kitchen owns global V quantization and the final attention kernel.
        dummy_q = value[:, :, :1].contiguous()
        if self.key is not None:
            # Kitchen's read-only K input requires positive vector-aligned
            # strides. Overlapping zero rows supply launch metadata without
            # allocating another full floating-point key tensor.
            storage = torch.zeros((value.shape[2] - 1) * 4 + value.shape[1] * 128,
                                  device=value.device, dtype=value.dtype)
            key = storage.as_strided(value.shape, (0, 128, 4, 1))
        packed = comfy_kitchen.prequantize_int8_attention(dummy_q, key, value)
        packed = dataclasses.replace(packed, q=self.data, q_scale=self.scale)
        if self.key is not None:
            packed = dataclasses.replace(packed, k=self.key, k_scale=self.key_scale)
        return packed
