"""Run CPU regression modules separately; never submit a live ComfyUI job."""
import os, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parent
environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
failed = []
for path in sorted(root.glob('test_*.py')):
    if path.stem.endswith('_live'):
        continue
    command = ([sys.executable, str(path)] if path.stem == 'test_library_routes'
               else [sys.executable, '-m', 'unittest', 'discover', '-s', str(root), '-p', path.name])
    result = subprocess.run(
        command,
        cwd=root.parent, env=environment, capture_output=True, text=True, encoding='utf-8',
    )
    print(f'{path.name}: {"PASS" if result.returncode == 0 else "FAIL"}', flush=True)
    print(result.stdout + result.stderr, flush=True)
    if result.returncode:
        failed.append(path.name)
if failed:
    print('Failed modules: ' + ', '.join(failed))
sys.exit(bool(failed))
