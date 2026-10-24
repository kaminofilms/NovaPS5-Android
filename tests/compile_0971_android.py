#!/usr/bin/env python3
"""Compile changed production units only; does not link the core or build an APK.
Usage: compile_0971_android.py CORE_ROOT NDK HEADERS_DIR GENERATED_DIR
HEADERS_DIR supplies the upstream dependency headers; GENERATED_DIR supplies
cmake_config.h and the real compiled blit SPIR-V headers used by swapchain.cpp.
"""
from pathlib import Path
import concurrent.futures,subprocess,sys
repo=Path(__file__).resolve().parents[1]
root,ndk,headers,generated=map(lambda p:Path(p).resolve(),sys.argv[1:])
compiler=ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android33-clang++'
includes=[root/'src',generated,repo/'native/novafex']+[headers/p for p in ['fmt/include','spdlog/include','SDL3/include','Vulkan-Headers/include','Vulkan-Hpp','tracy/public','magic_enum/include/magic_enum','xxHash','imgui','SPIRV-Headers/include','OpenXR-SDK/include','ZArchive/include','VulkanMemoryAllocator/include']]
files=[root/'src'/p for p in ['novaAndroid.cpp','graphics/presentation/videoOut.cpp','graphics/presentation/window/swapchain.cpp','graphics/presentation/window/vulkanWindow.cpp','kernel/fileSystem.cpp','common/timing/ClockAudit.cpp']]+[repo/'native/novafex/clock_probe.cpp']
def compile_file(source):
 output=generated/(source.stem+'.o');log=generated/(source.stem+'.compile.txt')
 flags=['-std=c++20','-fPIC','-c','-DKYTY_ANDROID=1','-D_LIBCPP_ENABLE_EXPERIMENTAL=1','-D__STDC_FORMAT_MACROS','-DSPDLOG_FMT_EXTERNAL=1','-DSPDLOG_HEADER_ONLY=1','-DTRACY_ENABLE=1','-DTRACY_ON_DEMAND=1','-DTRACY_CALLSTACK=0','-Wno-deprecated-declarations','-Wno-unused-command-line-argument']
 result=subprocess.run([str(compiler),*flags,*[arg for p in includes for arg in ['-I',str(p)]],str(source),'-o',str(output)],capture_output=True,text=True)
 log.write_text(result.stdout+result.stderr)
 return source,result.returncode,log
failed=False
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for source,code,log in pool.map(compile_file,files):
  print(('FAIL' if code else 'PASS')+' Android ARM64 object: '+str(source.relative_to(root) if source.is_relative_to(root) else source))
  if code:failed=True;print(log.read_text()[-5000:])
raise SystemExit(1 if failed else 0)
