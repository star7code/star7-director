"""W4A8 C ABI bridge: public tensor addresses, CUDA stream and Python-owned memory."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys

import torch


class Args(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('activation','weight','activation_scale',
        'group_scale','channel_scale','codebook','bias','workspace','output','stream')]
    _fields_ += [(name, ctypes.c_int32) for name in ('rows','channels','width','group_size','workspace_rows','device')]


class Kernel:
    def __init__(self):
        root = Path(__file__).parent / 'bin'
        manifest = json.loads((root / 'w4a8_manifest.json').read_text(encoding='utf-8-sig'))
        platform = 'windows_x64' if sys.platform == 'win32' else 'linux_x86_64'
        if platform not in manifest:
            raise RuntimeError(f'No bundled W4A8 CUDA library for {platform}')
        entry = manifest[platform]
        path = root / entry['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError('W4A8 library checksum mismatch; update DLL and manifest together')
        lib = ctypes.CDLL(str(path))
        lib.star7_w4a8_abi_version.argtypes = []
        lib.star7_w4a8_abi_version.restype = ctypes.c_int
        lib.star7_w4a8_args_size.argtypes = []
        lib.star7_w4a8_args_size.restype = ctypes.c_int
        if lib.star7_w4a8_abi_version() != 1 or lib.star7_w4a8_args_size() != ctypes.sizeof(Args):
            raise RuntimeError('W4A8 C ABI mismatch')
        lib.star7_w4a8_last_error.argtypes = []
        lib.star7_w4a8_last_error.restype = ctypes.c_char_p
        lib.star7_w4a8_quantize.argtypes = [ctypes.c_uint64] * 3 + [ctypes.c_int] * 3 + [ctypes.c_uint64]
        lib.star7_w4a8_quantize.restype = ctypes.c_int
        lib.star7_w4a8_linear.argtypes = [ctypes.POINTER(Args)]
        lib.star7_w4a8_linear.restype = ctypes.c_int
        self.lib = lib

    def _check(self, result):
        if result:
            raise RuntimeError('[Star7 H3 W4A8] CUDA operation failed: ' +
                               self.lib.star7_w4a8_last_error().decode('utf-8','replace'))

    def turing_fp16_int8_quantize(self, value):
        if not value.is_cuda or value.dtype != torch.float16 or value.ndim != 2 or min(value.shape) <= 0:
            raise ValueError('W4A8 quantization expects a nonempty CUDA FP16 matrix')
        value = value.contiguous()
        rows,width = value.shape
        output = torch.empty_like(value,dtype=torch.int8)
        scales = torch.empty(rows,1,device=value.device,dtype=torch.float32)
        with torch.cuda.device(value.device):
            self._check(self.lib.star7_w4a8_quantize(value.data_ptr(),output.data_ptr(),scales.data_ptr(),
                rows,width,value.device.index,torch.cuda.current_stream(value.device).cuda_stream))
        return output,scales

    def turing_fp16_codebook_w4a8_linear(self, activation, weight, activation_scale,
                                        group_scale, channel_scale, codebook, bias, group_size, chunk_rows=0):
        activation,weight,group_scale = (t.contiguous() for t in (activation,weight,group_scale))
        activation_scale,channel_scale,codebook = (t.reshape(-1).to(torch.float32).contiguous()
                                                   for t in (activation_scale,channel_scale,codebook))
        if bias is not None:
            bias = bias.reshape(-1).to(torch.float32).contiguous()
        if activation.ndim != 2 or weight.ndim != 2 or group_scale.ndim != 2:
            raise ValueError('W4A8 activation, weight and group scales must be matrices')
        m,k = activation.shape
        n = weight.shape[0]
        if (min(m,n,k) <= 0 or max(m,n,k) > 2147483647 or k % 16 or n % 8 or
            weight.shape[1] * 2 != k or group_size < 4 or k % group_size or
            (16 % group_size and group_size % 16) or
            group_scale.shape != (n,k // group_size) or activation_scale.numel() != m or
            channel_scale.numel() != n or codebook.numel() != 16 or
            (bias is not None and bias.numel() != n)):
            raise ValueError('Unsupported W4A8 shape, scales or group size')
        tensors = (activation,weight,activation_scale,group_scale,channel_scale,codebook)
        dtypes = (torch.int8,torch.int8,torch.float32,torch.uint8,torch.float32,torch.float32)
        if any(not t.is_cuda or t.device != activation.device or t.dtype != dtype
               for t,dtype in zip(tensors,dtypes)) or (bias is not None and bias.device != activation.device):
            raise ValueError('W4A8 tensor device or dtype mismatch')
        inline = group_size == 16 and m > 8192 and chunk_rows <= 0
        if chunk_rows < -1 or (chunk_rows == -1 and not inline) or (chunk_rows > 0 and chunk_rows % 8):
            raise ValueError('Invalid W4A8 staged/inline workspace selection')
        rows = 0 if inline else min(n,chunk_rows or 4096)
        workspace = None if inline else torch.empty(rows,k,device=activation.device,dtype=torch.int8)
        output = torch.empty(m,n,device=activation.device,dtype=torch.float16)
        with torch.cuda.device(activation.device):
            args = Args(*(t.data_ptr() for t in tensors),bias.data_ptr() if bias is not None else 0,
                        workspace.data_ptr() if workspace is not None else 0,output.data_ptr(),
                        torch.cuda.current_stream(activation.device).cuda_stream,
                        m,n,k,group_size,rows,activation.device.index)
            self._check(self.lib.star7_w4a8_linear(ctypes.byref(args)))
        return output
