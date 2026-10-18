import pathlib
import shutil
import sys

source = pathlib.Path(sys.argv[1]).resolve()
stage = pathlib.Path(sys.argv[2]).resolve()
relative = pathlib.Path('core/libs/prx/libSceAgcDriver')
shutil.copytree(source / relative, stage / relative, dirs_exist_ok=True)
root = stage / relative
p = root / 'Execution/src/GuestMemory.cpp'
s = p.read_text()
s = s.replace('#include <emmintrin.h>', '#if defined(__x86_64__) || defined(_M_X64)\n#include <emmintrin.h>\n#endif')
start = '        for (; at + 16 <= size; at += 16) {'
end = '        _mm_sfence();'
assert s.count(start) == 1 and s.count(end) == 1
s = s.replace(start, '#if defined(__x86_64__) || defined(_M_X64)\n' + start)
s = s.replace(end, end + '\n#endif')
p.write_text(s)
p = root / 'Execution/src/Driver/Synchronization/WaitMemory.cpp'
s = p.read_text().replace('#include <immintrin.h>', '#if defined(__x86_64__) || defined(_M_X64)\n#include <immintrin.h>\n#endif')
s = s.replace('            _mm_pause();', '#if defined(__aarch64__)\n            __asm__ volatile("yield");\n#elif defined(__x86_64__) || defined(_M_X64)\n            _mm_pause();\n#endif')
p.write_text(s)
p = root / 'Execution/src/VulkanDevice.cpp'
s = p.read_text().replace('#include <SDL_loadso.h>\n#include <SDL_error.h>', '#include "selected_vulkan_loader.hpp"')
s = s.replace('SDL_LoadObject(', 'NovaAnyPS5::LoadSelectedVulkan(').replace('SDL_LoadFunction(', 'NovaAnyPS5::SelectedVulkanSymbol(').replace('SDL_UnloadObject(', 'NovaAnyPS5::ReleaseSelectedVulkan(').replace('SDL_GetError()', 'NovaAnyPS5::SelectedVulkanError()')
p.write_text(s)

p = stage / 'core/libs/prx/libc/include/CpuTopology.hpp'
p.parent.mkdir(parents=True, exist_ok=True)
s = (source / 'core/libs/prx/libc/include/CpuTopology.hpp').read_text()
s = s.replace('    return pthread_setaffinity_np(pthread_self(), sizeof(set), &set) == 0 ? mask : 0;', '#if defined(__ANDROID__)\n    return sched_setaffinity(0, sizeof(set), &set) == 0 ? mask : 0;\n#else\n    return pthread_setaffinity_np(pthread_self(), sizeof(set), &set) == 0 ? mask : 0;\n#endif')
p.write_text(s)


p = root / 'Graphics/src/GuestBufferMemory.cpp'
s = p.read_text()
s = '#include "platform_memory.hpp"\n' + s.replace('memfd_create(', 'NovaAnyPS5::CreateMemoryFile(')
p.write_text(s)


p = root / 'Execution/src/GuestMemory.cpp'
s = p.read_text()
s = '#include "host_services.hpp"\n' + s
signature = 'bool describePages(std::uintptr_t address, std::size_t bytes, Emit&& emit) {'
start = s.index(signature)
body = start + len(signature)
level = 1
end = body
while level:
    level += (s[end] == '{') - (s[end] == '}')
    end += 1
replacement = r"""
    const auto end = address + bytes;
    while (address < end) {
        NovaAnyPS5::MemoryRun run{};
        if (!NovaAnyPS5::Services().query(address, &run) || run.begin > address || run.end <= address) return false;
        const auto next = std::min<std::uint64_t>(end, run.end);
        if (!emit(PageRun{address, next, run.readable, run.writable})) return true;
        address = next;
    }
    return true;
}"""
s = s[:body] + replacement + s[end:]
s = s.replace('std::memcpy(', 'NovaAnyPS5::CopyMemory(').replace('std::memcmp(', 'NovaAnyPS5::CompareMemory(')

changed_start = s.index('        std::size_t at = 0;', s.index('void WriteChanged('))
changed_end = s.index('        return firstChanged < lastChanged ?', changed_start)
s = s[:changed_start] + r"""        std::size_t at = 0;
        while (at < size) {
            while (at < size && current[at] == original[at]) ++at;
            const auto first = at;
            while (at < size && current[at] != original[at]) ++at;
            if (first == at) continue;
            NovaAnyPS5::CopyMemory(destination + first, current.data() + first, at - first);
            firstChanged = std::min(firstChanged, first);
            lastChanged = at;
        }
        std::atomic_thread_fence(std::memory_order_release);
""" + s[changed_end:]

s = s.replace('            destination[at] = current[at];', '            NovaAnyPS5::CopyMemory(destination + at, current.data() + at, 1);')
s = s.replace('        std::atomic_ref(*pointer).store(value, std::memory_order_release);', '        auto* host = static_cast<std::uint64_t*>(NovaAnyPS5::ContiguousMemory(reinterpret_cast<std::uintptr_t>(pointer), sizeof(*pointer)));\n        if (!host) throw std::runtime_error("AnyPS5 GPU label is not contiguous in host memory");\n        std::atomic_ref(*host).store(value, std::memory_order_release);')
p.write_text(s)
p = root / 'Graphics/src/GuestBufferMemory.cpp'
s = p.read_text()
s = '#include "host_services.hpp"\n' + s
needle = '    void* const host = entry.alias != nullptr ? entry.alias : reinterpret_cast<void*>(entry.base);'
assert s.count(needle) == 1
s = s.replace(needle, '    void* const host = entry.alias != nullptr ? entry.alias : NovaAnyPS5::ContiguousMemory(entry.base, static_cast<std::size_t>(entry.bytes));\n    if (!host) { failure = VK_ERROR_INVALID_EXTERNAL_HANDLE; return "guest host-import range is not contiguous"; }')
p.write_text(s)

cmake = (root / 'CMakeLists.txt').read_text().split('add_library(libSceAgcDriver SHARED EXCLUDE_FROM_ALL')[0]
cmake += '''
add_library(nova_anyps5_agc STATIC ${agcDriverSources})
add_dependencies(nova_anyps5_agc agc_trace_revision)
target_include_directories(nova_anyps5_agc PUBLIC
    "${NOVA_ANYPS5_STAGED_ROOT}/core/libs"
    "${ANYPS5_SOURCE_DIR}/core/libs"
    "${agcTextureDetileGeneratedRoot}"
    "${NOVA_ANYPS5_RENDERER_ADAPTER_DIR}")
target_link_libraries(nova_anyps5_agc PUBLIC nova_anyps5_compiler)
target_compile_features(nova_anyps5_agc PUBLIC cxx_std_20)
set_target_properties(nova_anyps5_agc PROPERTIES POSITION_INDEPENDENT_CODE ON)
'''
post = (root / 'PostCompile.cmake').read_text().split('target_sources(agc_driver_bda_device_tests')[0]
post = post.replace('libSceAgcDriver agc_driver_visual_test', 'nova_anyps5_agc')
cmake += post
(root / 'CMakeLists.txt').write_text(cmake)

api_relative = pathlib.Path('core/libs/prx/libSceAgc')
shutil.copytree(source / api_relative, stage / api_relative, dirs_exist_ok=True)
api = stage / api_relative
api_cmake = (api / 'CMakeLists.txt').read_text().split('\n)\n')[0] + '\n)\n'
api_cmake = api_cmake.replace('add_library(libSceAgc SHARED EXCLUDE_FROM_ALL', 'add_library(nova_anyps5_agc_api STATIC')
api_cmake += r"""
target_include_directories(nova_anyps5_agc_api PUBLIC "${NOVA_ANYPS5_STAGED_ROOT}/core/libs" "${ANYPS5_SOURCE_DIR}/core/libs")
target_link_libraries(nova_anyps5_agc_api PUBLIC nova_anyps5_agc)
target_compile_definitions(nova_anyps5_agc_api PRIVATE APS5_AGC_CREATE_LOG=0 APS5_ENABLE_TIMING_LOG=0 APS5_ENABLE_TRACY=0)
set_target_properties(nova_anyps5_agc_api PROPERTIES POSITION_INDEPENDENT_CODE ON)
"""
(api / 'CMakeLists.txt').write_text(api_cmake)
video_relative = pathlib.Path('core/libs/prx/libSceVideoOut')
shutil.copytree(source / video_relative, stage / video_relative, dirs_exist_ok=True)
video = stage / video_relative
(video / 'include/DisplayWindow.hpp').write_text('#pragma once\n#include "native_display.hpp"\n')
p = video / 'include/VideoOutDriver.hpp'
s = p.read_text().replace('    HostHdrProbe hdrProbe;', '    void* attachedWindow = nullptr;').replace('#include "SDL.h"', '').replace('#include "prx/libSceVideoOut/include/HostHdrProbe.hpp"', '').replace('    HostHdrProbe hdrProbe;', '')
p.write_text(s)
p = video / 'src/VideoOutDriver.cpp'
s = p.read_text()
for include in ['SDL.h', 'SDL_vulkan.h', 'prx/libSceVideoOut/include/PadInput.hpp', 'prx/libSceVideoOut/include/MouseInput.hpp', 'prx/libSceVideoOut/include/KeyboardInput.hpp', 'prx/libSceVideoOut/include/ImeTextInput.hpp', 'prx/libScePad/include/PadState.hpp']:
    s = s.replace('#include "' + include + '"', '')
s = '#include "video_platform.hpp"\n' + s
start = s.index('std::vector<const char*> windowExtensions(')
end = s.index('void checkConfig(', start)
s = s[:start] + s[end:]
start = s.index('    SDL_SetHint(SDL_HINT_WINDOWS_DPI_AWARENESS,')
end = s.index('    try {\n        AgcDriverWaitIdle_nid_postfix();', start)
s = s[:start] + s[end:]
s = s.replace('        SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER);', '').replace('    SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER);', '')
start = s.index('void VideoOutDriver::updateDisplayRefreshRate() {')
end = s.index('\n}\n', start) + 3
s = s[:start] + '''void VideoOutDriver::updateDisplayRefreshRate() {
    const int rate = NovaAnyPS5::Video().refreshRate();
    require(rate > 0, "host display refresh rate is invalid");
    displayRefreshRate.store(rate);
}
''' + s[end:]
s = s.replace('    hdrProbe.Poll(window.Handle());', '').replace('        hdrProbe.Poll(window.Handle());', '').replace('        hdrProbe.Release();', '').replace('    hdrProbe.Release();', '')
s = s.replace('        const auto extensions = windowExtensions(window.Handle());\n        const AgcDriver::PresentationWindow target{window.Handle(), extensions, &createWindowSurface, &windowDrawableSize, req.width, req.height, req.timing};', '        auto target = NovaAnyPS5::Video().window();\n        target.width = req.width;\n        target.height = req.height;\n        target.timing = req.timing;\n        if (attachedWindow != target.context) {\n            if (attachedWindow) AgcDriverReleaseWindow_nid_postfix(attachedWindow);\n            AgcDriverAttachWindow_nid_postfix(target);\n            attachedWindow = target.context;\n        }')
s = s.replace('        window.UpdateTitle();', '')
s = s.replace('        const auto extensions = windowExtensions(window.Handle());\n        AgcDriverAttachWindow_nid_postfix({window.Handle(), extensions, &createWindowSurface, &windowDrawableSize, VIDEO_OUT_DEFAULT_WIDTH, VIDEO_OUT_DEFAULT_HEIGHT, nullptr});', '        const auto target = NovaAnyPS5::Video().window();\n        AgcDriverAttachWindow_nid_postfix(target);\n        attachedWindow = target.context;')
s = s.replace('        PadInput padInput;\n        MouseInput mouseInput;\n        KeyboardInput keyboardInput;\n        ImeTextInput imeTextInput;', '')
start = s.index('            SDL_Event event;')
end = s.index('            if (current) {', start)
s = s[:start] + '            updateDisplayRefreshRate();\n            pollHostHdr();\n' + s[end:]
start = s.index('                int windowWidth = 0;')
end = s.index('                const auto finished = ', start)
s = s[:start] + s[end:]
s = s.replace('    req.terminal = true;\n    req.cfg->vblankCond.notify_all();', '    req.terminal = true;\n    NovaAnyPS5::Video().framePresented();\n    req.cfg->vblankCond.notify_all();')
s = s.replace('sceKernelGetProcessTime()', 'NovaAnyPS5::Video().processTime()').replace('sceKernelGetProcessTimeCounter()', 'NovaAnyPS5::Video().processTimeCounter()')
assert 'SDL_' not in s
p.write_text(s)
video_cmake = '''add_library(nova_anyps5_video STATIC
    Unimplemented.cpp src/Event.cpp src/Buffer.cpp src/Output.cpp src/VideoOutDriver.cpp
    "${ANYPS5_SOURCE_DIR}/core/libs/prx/libkernel/Time/TimedWait.cpp")
target_include_directories(nova_anyps5_video PUBLIC "${NOVA_ANYPS5_STAGED_ROOT}/core/libs" "${ANYPS5_SOURCE_DIR}/core/libs" "${NOVA_ANYPS5_RENDERER_ADAPTER_DIR}")
target_link_libraries(nova_anyps5_video PUBLIC nova_anyps5_agc)
target_compile_definitions(nova_anyps5_video PRIVATE APS5_ENABLE_TIMING_LOG=0 APS5_ENABLE_TRACY=0)
set_target_properties(nova_anyps5_video PROPERTIES POSITION_INDEPENDENT_CODE ON)
'''
(video / 'CMakeLists.txt').write_text(video_cmake)
