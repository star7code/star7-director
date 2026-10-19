"""CPU regression checks: refinement must not install a GPU-specific backend."""
import ast
import copy
import importlib
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parents[1]), str(ROOT)]
pkg = types.ModuleType('model_backend_boundary_tests')
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
hd = importlib.import_module(pkg.__name__ + '.vendor.h3.h3_latent_upscale_star7')
face = importlib.import_module(pkg.__name__ + '.vendor.h3.h3_face_refine_star7')
desk = importlib.import_module(pkg.__name__ + '.desk')
runtime = importlib.import_module(pkg.__name__ + '.runtime')
options = importlib.import_module(pkg.__name__ + '.vendor.h3.refine_model_options')


class Tests(unittest.TestCase):
    def model(self, chunked):
        from comfy.model_patcher import ModelPatcher
        model = ModelPatcher(torch.nn.Linear(2, 2), torch.device('cpu'), torch.device('cpu'))
        model.object_patches['model_sampling'] = types.SimpleNamespace(shift=6, audio_shift=6)
        if chunked:
            model.object_patches['diffusion_model.external_chunk'] = 'external chunk marker'
            model.model_options['transformer_options'] = {'external_backend': 'existing selection'}
            model.add_patches({'weight': ('diff', (torch.ones(2, 2),))}, 1.)
        return model

    def latent(self, size=4):
        from comfy.nested_tensor import NestedTensor
        return {'samples': NestedTensor((torch.zeros(1, 24, 7, size, size), torch.zeros(1, 32, 2, 10)))}

    def test_no_private_chunk_engines_remain_or_are_imported(self):
        retired = {'nodes', 'h3_preprocess', 'sla_backend', 'sm75_backend', 'sm80_diagnostics',
                   'sol_backend', 'sol_sm75_backend', 'star7_w4a8', 'vsa_sm75_backend', 'w4a8_native'}
        for name in retired:
            self.assertFalse((ROOT / 'vendor/h3' / (name + '.py')).exists())
            self.assertNotIn(pkg.__name__ + '.vendor.h3.' + name, sys.modules)
        for module in (hd, face):
            schema = (module.MiniMaxH3OneClickHDStar7 if module is hd else module.MiniMaxH3FaceRefineLatentStar7).INPUT_TYPES()
            field = 'second_pass_attention' if module is hd else 'face_attention'
            self.assertEqual(schema['required'][field][0], [options.INHERIT_FIRST_PASS])
            tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
            self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr == 'install_model_patch' for node in ast.walk(tree)))

    def test_legacy_settings_migrate_without_editing_source_or_other_parameters(self):
        plan = {'schema_version': '1.0', 'id': 'backend_migration', 'assets': [], 'shots': [],
                'generation': {'376': {'second_pass_attention': 'Sol', 'refine_steps': 3, 'enable_tiling': True},
                               '395': {'face_attention': 'SLA', 'face_count': 2}, '126': {'steps': 8}}}
        original = copy.deepcopy(plan)
        result = desk.merge_library(plan, None)
        self.assertEqual(result['generation']['376'], {**plan['generation']['376'], 'second_pass_attention': '继承一采'})
        self.assertEqual(result['generation']['395'], {**plan['generation']['395'], 'face_attention': '继承一采'})
        self.assertEqual(result['generation']['126'], plan['generation']['126'])
        self.assertEqual(plan, original)

    def test_hd_sampler_inherits_native_or_external_patches_even_with_legacy_override(self):
        import comfy_extras.nodes_custom_sampler as sampler
        for chunked in (False, True):
            for lora in (options.INHERIT_FIRST_PASS, options.NO_LORA):
                for fails in (False, True):
                    with self.subTest(chunked=chunked, lora=lora, fails=fails), ExitStack() as stack:
                        model = self.model(chunked)
                        before = copy.deepcopy(model.model_options)
                        before_objects = dict(model.object_patches)
                        latent, output = self.latent(), self.latent(8)
                        video, audio = output['samples'].unbind()
                        seen = []
                        def guider(connected, positive):
                            seen.append(connected)
                            self.assertEqual(connected.object_patches, before_objects)
                            self.assertEqual(connected.model_options, before)
                            return (connected,)
                        def sample(noise, connected, selected, sigmas, value):
                            self.assertIs(connected, seen[0])
                            if fails:
                                raise RuntimeError('synthetic sampler failure')
                            return value
                        stack.enter_context(patch.object(hd, '_sampling_profile', return_value=('base', 'base')))
                        stack.enter_context(patch.object(hd, '_upscale_video', return_value=(output, video, audio, 64, 64, 128, 128, True)))
                        stack.enter_context(patch.object(hd, '_send_sigma_status'))
                        stack.enter_context(patch.object(hd, '_sample_hd_refinement', side_effect=sample))
                        stack.enter_context(patch.object(sampler.BasicGuider, 'execute', side_effect=guider))
                        stack.enter_context(patch.object(sampler.KSamplerSelect, 'execute', return_value=(object(),)))
                        stack.enter_context(patch.object(sampler.RandomNoise, 'execute', return_value=(object(),)))
                        def run():
                            return hd.MiniMaxH3OneClickHDStar7().upscale(latent, {'model': model, 'positive': []},
                                preset='自定义', refine_steps=2, second_pass_lora=lora, second_pass_attention='Sol')
                        if fails:
                            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                                run()
                        else:
                            result, report = run()
                            self.assertIn('inherit connected model', report)
                            self.assertTrue(torch.equal(result['samples'].unbind()[1], audio))
                        # Empty transformer_options is harmless, but existing settings must be unchanged.
                        expected = copy.deepcopy(before)
                        expected.setdefault('transformer_options', {})
                        self.assertEqual(seen[0].model_options, expected)
                        self.assertEqual(model.object_patches, before_objects)
                        self.assertEqual(seen[0].patches, {} if lora == options.NO_LORA else model.patches)

    def test_face_sampling_keeps_external_model_patches_through_mask_clones(self):
        import comfy_extras.nodes_custom_sampler as sampler
        for chunked in (False, True):
            with self.subTest(chunked=chunked), ExitStack() as stack:
                model = self.model(chunked)
                latent = self.latent()
                images = torch.zeros(5, 64, 64, 3)
                transform = {'boxes': [[0, 0, 64, 64]] * 5, 'crop_factor': 2.6}
                tracked = (images, transform, None, 'track', 64, 64, 5)
                before = copy.deepcopy(model.model_options)
                seen = []
                def guider(connected, positive):
                    seen.append(connected)
                    self.assertEqual(connected.object_patches, model.object_patches)
                    self.assertEqual(connected.model_options, before)
                    self.assertEqual(connected.patches, model.patches)
                    return (connected,)
                stack.enter_context(patch.object(face, '_decode_video_frames', return_value=images))
                stack.enter_context(patch.object(face, '_ensure_face_detector', return_value='mock detector'))
                stack.enter_context(patch.object(face.H3FaceTrackCrop, 'run', return_value=tracked))
                stack.enter_context(patch.object(face.H3InjectVideoLatent, 'run', side_effect=lambda value, *args: (value,)))
                stack.enter_context(patch.object(face, '_compact_face_overlay', return_value={'test': 'overlay'}))
                stack.enter_context(patch.object(face, '_send_face_repair_resolution'))
                stack.enter_context(patch.object(sampler.BasicScheduler, 'execute', return_value=(torch.tensor([.2, 0.]),)))
                stack.enter_context(patch.object(sampler.BasicGuider, 'execute', side_effect=guider))
                stack.enter_context(patch.object(sampler.KSamplerSelect, 'execute', return_value=(object(),)))
                stack.enter_context(patch.object(sampler.RandomNoise, 'execute', return_value=(object(),)))
                stack.enter_context(patch.object(sampler.SamplerCustomAdvanced, 'execute', side_effect=lambda *args: (args[-1],)))
                result, report = face.MiniMaxH3FaceRefineLatentStar7().refine(latent,
                    {'model': model, 'positive': [], 'video_vae': object()}, face_attention='SLA', preserve_repair_detail=False)
                self.assertEqual(len(seen), 1)
                self.assertIn('inherit connected model', report)
                self.assertEqual(model.model_options, before)
                self.assertEqual(result[face._FACE_LATENT_OVERLAYS_KEY], ({'test': 'overlay'},))


if __name__ == '__main__':
    unittest.main()
