#!/usr/bin/env python3
"""Compile real candidate translation units and link ADPF APIs; never package an APK.

This deliberately does not claim a full core link, CMake build or device run.
The corresponding-source tree must already contain its real dependency headers.
"""
import argparse,json,os,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('core',type=Path);p.add_argument('--out',required=True,type=Path)
p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
p.add_argument('--ndk',type=Path,default=os.environ.get('ANDROID_NDK'))
p.add_argument('--api',type=int,default=33)
a=p.parse_args()
if a.ndk is None:p.error('--ndk or ANDROID_NDK is required')
root=a.core.resolve();out=a.out.resolve();repo=a.repo.resolve();out.mkdir(parents=True,exist_ok=True)
compiler=a.ndk.resolve()/f'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android{a.api}-clang++'
if not compiler.is_file():p.error('Android compiler not found: '+str(compiler))
config='''#define KYTY_VERSION "candidate-object-check"
#define KYTY_BUILD_REPOSITORY "kaminofilms/NovaPS5-Android"
#define KYTY_RELEASE_TAG "not-a-release"
#define KYTY_ENDIAN KYTY_ENDIAN_LITTLE
#define KYTY_PLATFORM KYTY_PLATFORM_LINUX
#define KYTY_COMPILER KYTY_COMPILER_CLANG
#define KYTY_LINKER KYTY_LINKER_LLD
#define KYTY_BUILD KYTY_BUILD_RELEASE
'''
incs=[root/'src',out,repo/'native/novafex']
incs += [p for p in (root/'3rdparty').glob('*/include') if p.is_dir() and p.parent.name!='winpthread']
incs += [root/'3rdparty'/p for p in ['tracy/public','xxHash','imgui','stb','magic_enum/include/magic_enum','ffmpeg-core/include']]
files=['src/libs/libAudio2.cpp','src/graphics/host_gpu/renderer/context.cpp','src/graphics/host_gpu/renderer/renderDraw.cpp','src/graphics/host_gpu/renderer/pipeline/descriptors.cpp','src/kernel/pthread.cpp','src/graphics/host_gpu/renderer/commandScheduler.cpp','src/graphics/presentation/videoOut.cpp','src/graphics/guest_gpu/graphicsRun.cpp','src/libs/audio.cpp','src/graphics/host_gpu/renderer/cache/bufferCache.cpp','src/graphics/host_gpu/renderer/image/image.cpp','src/kernel/semaphore.cpp']
results=[]
with tempfile.TemporaryDirectory(prefix='nova-native-config-') as tmp:
 config_dir=Path(tmp);(config_dir/'cmake_config.h').write_text(config)
 incs=[config_dir,*incs]
 for f in files:
  start=time.monotonic();stem=Path(f).stem;log=out/(stem+'.log');obj=out/(stem+'.o')
  cmd=[str(compiler),'-std=c++20','-O2','-fPIC','-include',str(root/'src/common/novaBionic.h'),'-c','-DKYTY_ANDROID=1','-DKYTY_NOVA_FEX=1','-DFMT_HEADER_ONLY','-DTRACY_ENABLE','-DTRACY_CALLSTACK=0']+['-I'+str(p) for p in incs]+[str(root/f),'-o',str(obj)]
  with log.open('w') as sink:r=subprocess.run(cmd,stdout=sink,stderr=sink)
  results.append({'file':f,'exit':r.returncode,'seconds':round(time.monotonic()-start,2)})
  print(results[-1],flush=True)
  if r.returncode:
   lines=log.read_text().splitlines();print('\n'.join(x for x in lines if 'error:' in x)[:2400],flush=True)
  (out/'results.json').write_text(json.dumps(results,indent=2))
 probe=out/'power_link_probe.cpp'
 probe.write_text('''#include "common/novaPower/FrameHints.h"
#include "common/novaPower/WorkerAffinity.h"
extern "C" void NovaCandidatePowerLinkProbe(){
 NovaPower::ApplyWorkerAffinity("Job.Worker 0");NovaPower::RegisterMainGuest();
 NovaPower::Current().Begin();NovaPower::Current().End();
}
''')
 cmd=[str(compiler),'-std=c++20','-O2','-fPIC','-shared','-Wl,--no-undefined','-I'+str(root/'src'),str(probe),'-landroid','-o',str(out/'libcandidate_power_link_probe.so')]
 with (out/'power_link.log').open('w') as sink:r=subprocess.run(cmd,stdout=sink,stderr=sink)
 results.append({'file':'power API link probe','exit':r.returncode})
 (out/'results.json').write_text(json.dumps(results,indent=2))
 print(results[-1],flush=True)
(out/'compiler-version.txt').write_text(subprocess.check_output([str(compiler),'--version'],text=True))
if any(r['exit'] for r in results):raise SystemExit(1)
print('PASS 12 ARM64 Android object compilations and power API link probe; no full core link, APK or device validation')
