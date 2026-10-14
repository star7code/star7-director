"""Temporary per-run SM80+ summaries and bounded projection probes."""
import collections
import importlib.metadata
import logging

import torch

_LOG = logging.getLogger('MiniMaxH3ActivationChunkStar7')


class RunDiagnostics:
    def __init__(self, configured):
        self.configured = configured
        self.run_number = 0
        self._reset()

    def _reset(self):
        self.calls = collections.Counter()
        self.steps = collections.Counter()
        self.seconds = collections.Counter()
        self.qkv = set()
        self.device = None
        self.finite_outputs = 0
        self.allocated = 0
        self.implementations = set()
        self.projection_checks = []
        self.rope_checks = []
        self.projection_probed = False
        self.projection_formats = set()

    def projection_capture(self, projector, x, input_quantized=False, fixed_input_scale=False):
        format_key = (str(getattr(projector, 'layout_type', None)), input_quantized)
        if format_key in self.projection_formats or len(self.projection_formats) >= 2:
            return None
        self.projection_formats.add(format_key)
        # ComfyUI's registered FP8 aliases default to scale=1, unlike CK's base.
        dynamic_scale = input_quantized and getattr(projector, 'input_scale', None) is None and not fixed_input_scale
        if dynamic_scale:
            self.projection_checks.append({'status': 'skipped-dynamic-input-scale'})
        samples = {}
        first_seen = False
        done = False

        def capture(start, end, q, k, v):
            nonlocal first_seen, done
            if done:
                return
            if start != 0 and end != x.shape[0]:
                return
            if start == 0 and first_seen:
                return
            if start == 0:
                first_seen = True
            if end == x.shape[0]:
                self.projection_probed = True
                done = True
            length = end - start
            if length <= 32:
                rows = list(range(length))
            else:
                middle = length // 2 - 8
                rows = list(range(8)) + list(range(middle, middle + 16)) + list(range(length - 8, length))
            try:
                indices = torch.tensor(rows, device=x.device)
                samples.update(start=start, end=end, indices=indices,
                               q=q.index_select(0, indices), k=k.index_select(0, indices))
                if dynamic_scale:
                    return
                actual = torch.cat([part.index_select(0, indices).flatten(1) for part in (q, k, v)], dim=-1).float()
                expected = projector(x.index_select(0, indices + start)).float()
                difference = actual - expected
                metrics = torch.stack((difference.norm() / expected.norm().clamp_min(1e-8),
                    difference.abs().amax(), torch.nn.functional.cosine_similarity(
                        actual.flatten(), expected.flatten(), dim=0, eps=1e-8))).detach()
                self.projection_checks.append({'format': format_key[0], 'rows': (start, end), 'sample_count': len(rows), 'metrics': metrics})
            except RuntimeError as error:
                status = 'probe-oom' if 'out of memory' in str(error).lower() else 'probe-error'
                self.projection_checks.append({'rows': (start, end), 'status': status, 'error_class': type(error).__name__})
                error.__traceback__ = None
                self.projection_probed = True
                done = True
                samples.clear()
        def norm_reference(start, end, q, k, freqs, q_scale, k_scale, epsilon, rot_dim):
            if samples.get('start') != start or samples.get('end') != end:
                return
            indices = samples['indices']
            rotation = freqs.index_select(1, indices)[0, :, 0].float()
            metrics = []
            for name, actual, scale in (('q', q, q_scale), ('k', k, k_scale)):
                expected = torch.nn.functional.rms_norm(samples[name].float(),
                    (actual.shape[-1],), scale.float(), epsilon)
                half = rot_dim // 2
                first, second = expected[..., :half], expected[..., half:rot_dim]
                rotated_first = first * rotation[:, None, :, 0, 0] + second * rotation[:, None, :, 0, 1]
                rotated_second = first * rotation[:, None, :, 1, 0] + second * rotation[:, None, :, 1, 1]
                expected = torch.cat((rotated_first, rotated_second, expected[..., rot_dim:]), dim=-1).to(actual.dtype).float()
                actual = actual.index_select(0, indices).float()
                metrics.append(torch.stack(((actual - expected).norm() / expected.norm().clamp_min(1e-8),
                    (actual - expected).abs().amax())).detach())
            self.rope_checks.append({'format': format_key[0], 'rows': (start, end), 'Q/K_relative_l2_max_abs': torch.stack(metrics)})
            samples.clear()
        def check_norm(start, end, *args):
            try:
                norm_reference(start, end, *args)
            except RuntimeError as error:
                self.rope_checks.append({'format': format_key[0], 'rows': (start, end),
                                        'status': 'probe-error', 'error_class': type(error).__name__})
                error.__traceback__ = None
            finally:
                samples.clear()
        capture.check_norm = check_norm
        return capture

    def observe(self, route, tensors, chunk, weight_format):
        self.calls[route] += 1
        self.device = tensors[0].device
        if len(self.qkv) < 8:
            self.qkv.add((route, tuple(tensors[0].shape), str(tensors[0].dtype),
                          tuple(tuple(t.stride()) for t in tensors), chunk, weight_format))
        self.allocated = max(self.allocated, torch.cuda.memory_allocated(self.device))

    def step(self, route, seconds, device=None):
        self.steps[route] += 1
        self.seconds[route] += seconds
        if device is not None:
            self.device = device

    def producer(self, device, shape, dtype, chunk, weight_format):
        self.calls['Sol-official-producer'] += 1
        self.device = device
        if len(self.qkv) < 8:
            self.qkv.add(('Sol-official-producer', shape, str(dtype), (), chunk, weight_format))
        self.allocated = max(self.allocated, torch.cuda.memory_allocated(device))

    def finish(self):
        if not self.calls and not self.steps:
            self._reset()
            return
        self.run_number += 1
        device = self.device
        capability = torch.cuda.get_device_capability(device)
        try:
            triton_version = importlib.metadata.version('triton-windows')
        except importlib.metadata.PackageNotFoundError:
            try:
                triton_version = importlib.metadata.version('triton')
            except importlib.metadata.PackageNotFoundError:
                triton_version = 'unavailable'
        _LOG.info('[Star7 H3 SM80+] run=%d | revision=projection-v2 | gpu=%s SM%d%d | torch=%s cuda=%s triton=%s | configured=%s implementations=%s | attention_calls=%s | timed_model_calls=%s model_seconds=%s | finite_outputs=%d | observed_allocated=%.2fGiB',
                  self.run_number, torch.cuda.get_device_name(device), *capability,
                  torch.__version__, torch.version.cuda, triton_version, self.configured, sorted(self.implementations),
                  dict(self.calls), dict(self.steps), {k: round(v, 3) for k, v in self.seconds.items()},
                  self.finite_outputs, self.allocated / 2**30)
        projection_checks = []
        for check in self.projection_checks:
            item = dict(check)
            metrics = item.pop('metrics', None)
            if metrics is not None:
                values = metrics.cpu().tolist()
                item.update(relative_l2=round(values[0], 6), max_abs=round(values[1], 6), cosine=round(values[2], 6))
            projection_checks.append(item)
        rope_checks = []
        for check in self.rope_checks:
            item = dict(check)
            values = item.pop('Q/K_relative_l2_max_abs', None)
            if values is not None:
                item['Q_K_relative_l2_max_abs'] = values.cpu().tolist()
            rope_checks.append(item)
        _LOG.info('[Star7 H3 SM80+] run=%d | QKV=(route, shape, dtype, Q/K/V strides, chunk, weight_format) %s | projection_row_checks=%s | norm_rope_row_checks=%s',
                  self.run_number, sorted(self.qkv), projection_checks, rope_checks)
        self._reset()
