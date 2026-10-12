#!/usr/bin/env python3
"""Dependency-free Android build, requiring official SDK/NDK and Java 17 or ECJ."""
import argparse,hashlib,os,pathlib,shutil,struct,subprocess,zipfile
p=argparse.ArgumentParser();p.add_argument('--sdk',required=True);p.add_argument('--ndk',required=True);p.add_argument('--output',required=True);p.add_argument('--ecj');p.add_argument('--abi',choices=['arm64-v8a','x86_64'],default='arm64-v8a');p.add_argument('--keystore',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent;android=root/'android';sdk=pathlib.Path(a.sdk).resolve();ndk=pathlib.Path(a.ndk).resolve();out=pathlib.Path(a.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
bt=sdk/'build-tools/36.0.0'
if not bt.exists():bt=sdk/'android-16'
platform=sdk/'platforms/android-36/android.jar'
if not platform.is_file():platform=sdk/'android-36/android.jar'
build=root/'build'/a.abi;shutil.rmtree(build,ignore_errors=True)
for name in ['classes','dex','lib/'+a.abi]:(build/name).mkdir(parents=True,exist_ok=True)
def run(*args):subprocess.run([str(x) for x in args],check=True)
llvm=ndk/'toolchains/llvm/prebuilt/linux-x86_64';glslc=ndk/'shader-tools/linux-x86_64/glslc'
shader=[]
for stage in ['vert','frag']:
 f=build/f'triangle.{stage}.spv';run(glslc,'--target-env=vulkan1.0',root/f'native/triangle.{stage}','-o',f);raw=f.read_bytes();words=struct.unpack('<'+'I'*(len(raw)//4),raw)
 shader.append('inline constexpr uint32_t triangle_'+stage+'[]={\n'+','.join('0x%08x'%x for x in words)+'\n};\n')
(build/'shader_bytes.h').write_text('#pragma once\n#include <cstdint>\n'+''.join(shader))
run(llvm/'bin/clang++','--target='+({'arm64-v8a':'aarch64','x86_64':'x86_64'}[a.abi])+'-linux-android28','--sysroot='+str(llvm/'sysroot'),'-std=c++17','-O2','-g0','-fPIC','-shared','-static-libstdc++','-fvisibility=hidden','-Wl,-z,max-page-size=16384','-Wl,-z,common-page-size=16384','-Wl,--no-undefined','-Wl,-soname,libnovaps5.so','-I'+str(build),'-I'+str(root/'native'),root/'native/cpu_block.cpp',root/'native/probe.cpp',root/'native/renderer.cpp',root/'native/jni.cpp','-lvulkan','-landroid','-llog','-o',build/'lib'/a.abi/'libnovaps5.so')
run(llvm/'bin/llvm-strip','--strip-unneeded',build/'lib'/a.abi/'libnovaps5.so')
run(bt/'aapt2','compile','--dir',android/'res','-o',build/'resources.zip')
run(bt/'aapt2','link','-o',build/'unsigned.apk','-I',platform,'--manifest',android/'AndroidManifest.xml',build/'resources.zip','-A',android/'assets','--min-sdk-version','28','--target-sdk-version','36')
sources=sorted(android.glob('src/**/*.java'))
if shutil.which('javac'):run('javac','-source','8','-target','8','-classpath',platform,'-d',build/'classes',*sources)
elif a.ecj:run('java','-jar',a.ecj,'-source','8','-target','8','-bootclasspath',str(platform)+os.pathsep+str(bt/'core-lambda-stubs.jar'),'-nowarn','-d',build/'classes',*sources)
else:raise SystemExit('Install javac or specify --ecj')
with zipfile.ZipFile(build/'classes.jar','w') as archive:
 for f in sorted((build/'classes').rglob('*.class')):archive.write(f,str(f.relative_to(build/'classes')))
run(bt/'d8','--lib',platform,'--min-api','28','--output',build/'dex',build/'classes.jar')
with zipfile.ZipFile(build/'unsigned.apk','a',compression=zipfile.ZIP_DEFLATED) as archive:
 archive.write(build/'dex/classes.dex','classes.dex');archive.write(build/'lib'/a.abi/'libnovaps5.so','lib/'+a.abi+'/libnovaps5.so')
run(bt/'zipalign','-P','16','-f','4',build/'unsigned.apk',build/'aligned.apk')
key=pathlib.Path(a.keystore).resolve();key.parent.mkdir(parents=True,exist_ok=True)
if not key.is_file():run('keytool','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','novaps5dev','-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=NovaPs5 Development, O=Kamino Films, C=US')
run(bt/'apksigner','sign','--ks',key,'--ks-key-alias','novaps5dev','--ks-pass','pass:android','--key-pass','pass:android','--out',out,build/'aligned.apk')
run(bt/'apksigner','verify','--verbose','--print-certs',out);run(bt/'zipalign','-c','-P','16','4',out);run(bt/'aapt','dump','badging',out)
print('APK',out);print('SHA256',hashlib.sha256(out.read_bytes()).hexdigest())
