"""Host candidate regressions; NOT Android/GPU/FPS certification."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1]
core=Path(sys.argv[1]).resolve()
env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
cpp=['worker_policy.cpp','work0981-binding_cache_test.cpp','work0983-readonly_depth_test.cpp']
python=[('test_frame_hints.py',[]),('work0982-test_snapshot.py',[str(core)]),('test_context_push.py',[str(core)])]
with tempfile.TemporaryDirectory(prefix='nova-candidate-tests-') as tmp:
 for name in cpp:
  output=str(Path(tmp)/name.removesuffix('.cpp'))
  subprocess.run([os.environ.get('HOST_CXX','c++'),'-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-I'+str(repo),'-I'+str(core/'3rdparty/Vulkan-Headers/include'),str(repo/'tests'/name),'-o',output],check=True,env=env)
  subprocess.run([output],check=True,env=env)
  print('PASS',name,flush=True)
 for name,args in python:
  subprocess.run([sys.executable,str(repo/'tests'/name),*args],check=True,env=env)
  print('PASS',name,flush=True)
print('PASS 6 host suites; Android/GPU/device gates remain open')
