import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import compile_plan,compile_shot,agent_catalog,preflight,validate,import_shots
from storage import Storage

def project():
    return {'schema_version':'1.0','id':'test_project','settings':{'width':960,'height':544,'fps':24},
     'assets':[{'id':'actor','kind':'character','name':'角色甲','voice_id':'voice','media':[{'type':'image','source':'actor.png'}]},
               {'id':'voice','kind':'voice','name':'声音甲','media':[{'type':'audio','source':'voice.wav'}]},
               *[{'id':'prop_'+str(i),'kind':'prop','name':'物品'+str(i),'media':[{'type':'image','source':str(i)+'.png'}]} for i in range(20)]],
     'shots':[{'id':'s1','prompt':'@角色甲 走进房间','duration':5,'seed':7,'continuity':{'mode':'independent'}},
              {'id':'s2','prompt':'@actor 回头','duration':5,'seed':8,'continuity':{'mode':'previous_latent','source_shot':'s1'}}]}

class Tests(unittest.TestCase):
    def test_mentions_allow_sentence_punctuation(self):
        p=project();p['shots'][0]['prompt']='Use @actor. Keep the character consistent.'
        self.assertIn('<Picture 1>.',compile_shot(p,'s1')['prompt'])
    def test_only_selected_and_voice_binding(self):
        item=compile_shot(project(),'s1')
        self.assertEqual(len(item['media']['image']),1)
        self.assertEqual(len(item['media']['audio']),1)
        self.assertIn('<Picture 1>',item['prompt']);self.assertIn('<Audio 1>',item['prompt'])
    def test_limit_unknown_and_forward_dependency(self):
        p=project();p['shots'][0]['prompt']=' '.join('@prop_'+str(i) for i in range(10))
        with self.assertRaises(ValueError):compile_plan(p)
        p=project();p['shots'][0]['prompt']='@missing'
        with self.assertRaises(ValueError):compile_plan(p)
        p=project();p['shots'][0]['continuity']={'mode':'previous_latent','source_shot':'s2'}
        with self.assertRaises(ValueError):validate(p)
    def test_dependency_invalidates_and_unused_asset_does_not(self):
        p=project();first=compile_plan(p)
        p['assets'][-1]['description']='Unused card edit'
        self.assertEqual(first,compile_plan(p))
        p['shots'][0]['seed']=99
        second=compile_plan(p)
        self.assertNotEqual(first[0]['fingerprint'],second[0]['fingerprint'])
        self.assertNotEqual(first[1]['fingerprint'],second[1]['fingerprint'])
    def test_ai_import_keeps_asset_library(self):
        p=project()
        result=import_shots(p,{'schema_version':'1.0','shots':[p['shots'][0]]})
        self.assertEqual(result['assets'],p['assets'])
        self.assertEqual(len(result['shots']),1)
        self.assertEqual(len(p['shots']),2)
    def test_agent_catalog_has_no_paths(self):
        data=json.dumps(agent_catalog(project()))
        self.assertNotIn('actor.png',data);self.assertNotIn('voice.wav',data)
    def test_corrupt_media_is_detected_before_sampling(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            p=project();(Path(temp)/'actor.png').write_text('broken',encoding='utf-8')
            errors=preflight(p,temp)
            self.assertTrue(any(e['source']=='actor.png' and '媒体不可读取' in e['reason'] for e in errors))
    def test_preflight_all_shots_before_run(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            self.assertEqual({e['shot'] for e in preflight(project(),temp)},{'s1','s2'})
    def test_cache_roundtrip_audio_mask_and_repair(self):
        import torch
        from comfy.nested_tensor import NestedTensor
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            storage=Storage(temp)
            latent={'samples':NestedTensor((torch.randn(1,24,2,4,4),torch.randn(1,32,20))),
                    'noise_mask':NestedTensor((torch.ones(1,1,2,4,4),torch.zeros(1,1,20))),
                    'star7_face_latent_overlays':({'crop':torch.randn(1,24,2,2,2),'box':(1,2,3,4)},)}
            version=storage.save_latent('test_project','s1','face','fingerprint',latent)
            actual=storage.load_latent('test_project','s1','face',version,'fingerprint')
            for a,b in zip(actual['samples'].unbind(),latent['samples'].unbind()):torch.testing.assert_close(a,b,rtol=0,atol=0)
            self.assertIsInstance(actual['star7_face_latent_overlays'],tuple)
            torch.testing.assert_close(actual['star7_face_latent_overlays'][0]['crop'],latent['star7_face_latent_overlays'][0]['crop'])
            with self.assertRaises(ValueError):storage.load_latent('test_project','s1','face',version,'different')
            with self.assertRaises(TypeError):storage.save_latent('test_project','s1','face','fingerprint',{'model':object()})
            self.assertEqual(len(storage.stages('test_project')),1)
if __name__=='__main__':unittest.main()
