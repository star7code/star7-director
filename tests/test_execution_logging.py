"""CPU-only checks for origin errors, interruptions and private executor events."""
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('director_execution_logging_tests');pkg.__path__=[str(ROOT)]
sys.modules[pkg.__name__]=pkg
desk=importlib.import_module(pkg.__name__+'.desk')
runtime=importlib.import_module(pkg.__name__+'.runtime')
logs=importlib.import_module(pkg.__name__+'.run_logging')


class Interrupted(Exception):pass


def node(function, lazy=False):
    return type('FakeNode',(),{
        'FUNCTION':'run','run':staticmethod(function),
        'INPUT_TYPES':classmethod(lambda cls:{}),
        'check_lazy_status':lambda *args,**kwargs:[] if lazy else ['latent'],
    })


class Tests(unittest.TestCase):
    def setUp(self):
        comfy=types.ModuleType('comfy');mm=types.ModuleType('comfy.model_management')
        mm.InterruptProcessingException=Interrupted
        mm.throw_exception_if_processing_interrupted=lambda:None
        comfy.model_management=mm
        graph=types.ModuleType('comfy_execution.graph_utils')
        graph.is_link=lambda value:isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and isinstance(value[1],int)
        modules={'comfy':comfy,'comfy.model_management':mm,'comfy_execution':types.ModuleType('comfy_execution'),'comfy_execution.graph_utils':graph}
        self.modules=patch.dict(sys.modules,modules);self.modules.start();self.addCleanup(self.modules.stop)

    def execute(self,graph,result):
        return desk.execute_internal(graph,result,{'id':'project_a'},'shot_001')

    def test_origin_is_wrapped_and_logged_once_across_dependents(self):
        original=RuntimeError('CUDA INT8 convrot dequantization failed: invalid argument')
        def fail(**kwargs):raise original
        def unreachable(**kwargs):self.fail('dependent step must not execute')
        graph={'x.127':{'class_type':'Sampler','inputs':{}},
               'x.377':{'class_type':'Decode','inputs':{'latent':['x.127',0]}},
               'x.150':{'class_type':'Encode','inputs':{'images':['x.377',0]}}}
        with patch.object(runtime,'registry',side_effect=lambda name:node(fail if name=='Sampler' else unreachable)):
            with self.assertLogs(logs.LOG,level='INFO') as output:
                with self.assertRaises(logs.DirectorExecutionError) as raised:self.execute(graph,['x.150',0])
        self.assertIs(raised.exception.__cause__,original)
        message=str(raised.exception)
        self.assertEqual(message.count('failed (node='),1)
        self.assertIn('base_sampling',message);self.assertNotIn('video_encode',message)
        self.assertEqual(sum('step_failed' in line for line in output.output),1)
        self.assertIn('project_a',output.output[-1]);self.assertIn('shot_001',output.output[-1])

    def test_interrupt_stays_interrupt_and_is_not_failure(self):
        def stop(**kwargs):raise Interrupted('cancelled')
        graph={'x.127':{'class_type':'Sampler','inputs':{}}}
        with patch.object(runtime,'registry',return_value=node(stop)):
            with self.assertLogs(logs.LOG,level='INFO') as output:
                with self.assertRaises(Interrupted):self.execute(graph,['x.127',0])
        self.assertTrue(any('step_interrupted' in line for line in output.output))
        self.assertFalse(any('step_failed' in line for line in output.output))

    def test_lazy_cache_never_runs_sampler_and_preserves_ui(self):
        def cached(**kwargs):return {'result':('cached',),'ui':{'gifs':[{'filename':'clip.mp4'}]}}
        def fail(**kwargs):self.fail('cache hit must skip sampler')
        graph={'x.602':{'class_type':'Star7DirectorBaseCache','inputs':{'latent':['x.127',0]}},
               'x.127':{'class_type':'Sampler','inputs':{}}}
        with patch.object(runtime,'registry',side_effect=lambda name:node(cached,True) if name=='Star7DirectorBaseCache' else node(fail)):
            with self.assertLogs(logs.LOG,level='INFO') as output:result=self.execute(graph,['x.602',0])
        self.assertEqual(result['result'],('cached',))
        self.assertEqual(result['ui']['gifs'][0]['filename'],'clip.mp4')
        self.assertTrue(any('step_complete' in line and 'seconds=' in line for line in output.output))
        self.assertFalse(any('base_sampling' in line for line in output.output))

    def test_error_message_cannot_inject_event_lines(self):
        with self.assertLogs(logs.LOG,level='INFO') as output:logs.event('example',error='first\nsecond')
        self.assertNotIn('\n',output.output[0]);self.assertIn('first\\nsecond',output.output[0])


if __name__=='__main__':unittest.main()
