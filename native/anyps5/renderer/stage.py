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


# The PS5 AGC driver block lives at a fixed guest address inside Kyty's reserved system
# region; Nova maps it through Kyty's kernel memory (registered with the renderer) instead
# of a raw MAP_FIXED_NOREPLACE mmap, which collides with that reservation (EEXIST).
p = root / 'Execution/src/Driver/Lifecycle.cpp'
s = p.read_text()
old = """    mapped = mmap(reinterpret_cast<void*>(DriverMemoryAddress), DriverMemoryBytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (mapped == MAP_FAILED) throw std::system_error(errno, std::generic_category(), "map the AGC driver memory");"""
assert s.count(old) == 1, 'Lifecycle.cpp driver memory mmap moved'
s = '#include "host_services.hpp"\n' + s.replace(old, """    mapped = NovaAnyPS5::Services().driverMemory(DriverMemoryAddress, DriverMemoryBytes);
    if (mapped == nullptr) throw std::runtime_error("Nova could not map the AGC driver memory at its fixed guest address");""")
# driverMemory maps AND registers the block (Nova publishes every kernel mapping to the
# renderer's allocation registry), so upstream's own registration would overlap it.
old = """#ifndef _WIN32
    GuestWriteWatch::GuestWriteWatchRegister_nid_postfix(mapped, DriverMemoryBytes);
#endif
    GuestAllocations::Mutation mutation;
    mutation.Add(mapped, DriverMemoryBytes, true, true, true);"""
assert s.count(old) == 1, 'Lifecycle.cpp driver memory registration moved'
s = s.replace(old, '    // Registered by Nova when driverMemory mapped it.')
p.write_text(s)
# Android: with an IDENTITY preTransform on a rotated panel the compositor rotates the image and
# vkQueuePresentKHR reports VK_SUBOPTIMAL_KHR every frame. Upstream recreated the swapchain (after a
# full device wait) on every SUBOPTIMAL. Keep it; only OUT_OF_DATE (or a size change) recreates.
p = root / 'Execution/src/VulkanDevice.cpp'
s = p.read_text()
old = """    if (presented == VK_ERROR_OUT_OF_DATE_KHR || presented == VK_SUBOPTIMAL_KHR) state->extent = {0, 0};
    else check(presented, "vkQueuePresentKHR");"""
assert s.count(old) == 1, 'VulkanDevice.cpp present result handling moved'
s = s.replace(old, """    if (presented == VK_ERROR_OUT_OF_DATE_KHR) state->extent = {0, 0};
    else if (presented != VK_SUBOPTIMAL_KHR) check(presented, "vkQueuePresentKHR");""")
p.write_text(s)
# Fill the whole Android surface like Nova's Kyty presenter; NOVA_ANYPS5_ASPECT=fit keeps aspect.
p = root / 'Execution/src/AspectFit.cpp'
s = p.read_text()
old = """AspectFitRect ComputeContainRect_nid_postfix(std::uint32_t sourceWidth, std::uint32_t sourceHeight, std::uint32_t destinationWidth, std::uint32_t destinationHeight) {
"""
assert s.count(old) == 1, 'AspectFit.cpp ComputeContainRect moved'
s = '#include <cstdlib>\n#include <cstring>\n' + s.replace(old, old + """    static const bool keepAspect = [] { const char* mode = std::getenv("NOVA_ANYPS5_ASPECT"); return mode && std::strcmp(mode, "fit") == 0; }();
    if (!keepAspect) {
        require(sourceWidth != 0 && sourceHeight != 0 && destinationWidth != 0 && destinationHeight != 0, "extent must be non-zero");
        return AspectFitRect{0, 0, destinationWidth, destinationHeight};
    }
""")
p.write_text(s)
# Nova backs guest memory with a shared memfd. Asynchronous userfaultfd write protection covers
# shmem only with UFFD_FEATURE_WP_HUGETLBFS_SHMEM; request it when the kernel offers it and keep the
# upstream feature set otherwise (unchanged behaviour on kernels without it).
p = stage / 'core/libs/prx/libc/src/GuestWriteWatch.cpp'
p.parent.mkdir(parents=True, exist_ok=True)
s = (source / 'core/libs/prx/libc/src/GuestWriteWatch.cpp').read_text()
old = """        uffdio_api api{};
        api.api = UFFD_API;
        api.features = UFFD_FEATURE_WP_ASYNC | UFFD_FEATURE_WP_UNPOPULATED;
        if (ioctl(_uffd, UFFDIO_API, &api) != 0 || (api.features & UFFD_FEATURE_WP_ASYNC) == 0 || (api.features & UFFD_FEATURE_WP_UNPOPULATED) == 0) return unavailable("asynchronous userfaultfd write protection");"""
assert s.count(old) == 1, 'GuestWriteWatch.cpp UFFDIO_API block moved'
s = s.replace(old, """        uffdio_api api{};
        api.api = UFFD_API;
        api.features = UFFD_FEATURE_WP_ASYNC | UFFD_FEATURE_WP_UNPOPULATED | UFFD_FEATURE_WP_HUGETLBFS_SHMEM;
        if (ioctl(_uffd, UFFDIO_API, &api) != 0) {
            // The API handshake is one-shot per descriptor: reopen without the shmem feature.
            close(_uffd);
            _uffd = static_cast<int>(syscall(SYS_userfaultfd, O_CLOEXEC | O_NONBLOCK | UFFD_USER_MODE_ONLY));
            if (_uffd < 0) _uffd = static_cast<int>(syscall(SYS_userfaultfd, O_CLOEXEC | O_NONBLOCK));
            if (_uffd < 0) return unavailable("userfaultfd");
            api = {};
            api.api = UFFD_API;
            api.features = UFFD_FEATURE_WP_ASYNC | UFFD_FEATURE_WP_UNPOPULATED;
            if (ioctl(_uffd, UFFDIO_API, &api) != 0) return unavailable("asynchronous userfaultfd write protection");
        }
        if ((api.features & UFFD_FEATURE_WP_ASYNC) == 0 || (api.features & UFFD_FEATURE_WP_UNPOPULATED) == 0) return unavailable("asynchronous userfaultfd write protection");
        std::fprintf(stderr, "[memory] write watch: userfaultfd asynchronous write protection active (shmem %s)\\n", (api.features & UFFD_FEATURE_WP_HUGETLBFS_SHMEM) ? "yes" : "no");""")
p.write_text(s)
# Upstream screenshots are a desktop hotkey feature that writes PNGs through SDL paths.
# Nova never requests them; keep the request/take state and refuse the PNG write explicitly.
p = root / 'Execution/src/Screenshot.cpp'
assert p.is_file(), 'upstream Screenshot.cpp moved'
p.write_text(r"""#include "prx/libSceAgcDriver/Execution/include/Screenshot.hpp"
#include <atomic>
#include <stdexcept>
namespace { std::atomic<bool> requested{false}; }
void AgcDriver::Screenshot::Request() { requested.store(true); }
bool AgcDriver::Screenshot::Take() { return requested.exchange(false); }
std::filesystem::path AgcDriver::Screenshot::Write(std::string_view, std::uint32_t, std::uint32_t, std::span<const std::byte>) {
    throw std::runtime_error("Screenshot: PNG capture is not available in Nova Android");
}
""")
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
copy_start = s.index('[[gnu::no_sanitize("address")]] void CopyGuestBytes(')
copy_end = s.index('\n#else', copy_start)
s = s[:copy_start] + 'void CopyGuestBytes(void* destination, const void* source, std::size_t bytes) {\n    NovaAnyPS5::CopyMemory(destination, source, bytes);\n}' + s[copy_end:]


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
# Fused shader code is addressed by 48-bit GPU program registers: allocate it untagged on Android.
p = api / 'Misc/src/ShaderFusion.cpp'
s = p.read_text()
for old, new in [('    std::vector<std::uint8_t> storage;\n', '    std::vector<std::uint8_t, NovaAnyPS5::UntaggedAllocator<std::uint8_t>> storage;\n'),
                 ('FusedProgram program{std::vector<std::uint8_t>(layout.totalBytes + FusedCodeAlignment - 1), nullptr};', 'FusedProgram program{std::vector<std::uint8_t, NovaAnyPS5::UntaggedAllocator<std::uint8_t>>(layout.totalBytes + FusedCodeAlignment - 1), nullptr};')]:
    assert s.count(old) == 1, 'ShaderFusion.cpp: ' + old[:40]
    s = s.replace(old, new)
p.write_text('#include "untagged_allocator.hpp"\n' + s)
video_relative = pathlib.Path('core/libs/prx/libSceVideoOut')
shutil.copytree(source / video_relative, stage / video_relative, dirs_exist_ok=True)
video = stage / video_relative
(video / 'include/DisplayWindow.hpp').write_text('#pragma once\n#include "native_display.hpp"\n')
def edit(text, old, new, count=1):
    found = text.count(old)
    if found != count:
        raise SystemExit(f'NOVA_ANYPS5_STAGE: expected {count} of {old[:70]!r}, found {found}')
    return text.replace(old, new)
def cut(text, start_marker, end_marker, replacement=''):
    if text.count(start_marker) != 1:
        raise SystemExit(f'NOVA_ANYPS5_STAGE: expected one start {start_marker[:70]!r}')
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]
p = video / 'include/VideoOutDriver.hpp'
s = p.read_text()
s = edit(s, '    HostHdrProbe hdrProbe;', '    void* attachedWindow = nullptr;')
s = edit(s, '#include "SDL.h"', '')
s = edit(s, '#include "prx/libSceVideoOut/include/HostHdrProbe.hpp"', '')
p.write_text(s)
p = video / 'src/VideoOutDriver.cpp'
s = p.read_text()
for include in ['SDL.h', 'SDL_vulkan.h', 'prx/libSceVideoOut/include/PadInput.hpp', 'prx/libSceVideoOut/include/MouseInput.hpp', 'prx/libSceVideoOut/include/KeyboardInput.hpp', 'prx/libSceVideoOut/include/ImeTextInput.hpp', 'prx/libScePad/include/PadState.hpp']:
    s = edit(s, '#include "' + include + '"\n', '')
s = '#include "video_platform.hpp"\n' + s
# Nova owns the Android surface: SDL window/instance helpers are not built.
s = cut(s, 'std::vector<const char*> windowExtensions(', 'void checkConfig(')
s = cut(s, '    OnMainThread([] {\n        SDL_SetHint(SDL_HINT_WINDOWS_DPI_AWARENESS', '    try {\n        AgcDriverWaitIdle_nid_postfix();')
s = edit(s, '        OnMainThread([] { SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER); });\n', '')
s = edit(s, '    OnMainThread([] { SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER); });\n', '')
start = s.index('void VideoOutDriver::updateDisplayRefreshRate() {')
end = s.index('\n}\n', start) + 3
s = s[:start] + '''void VideoOutDriver::updateDisplayRefreshRate() {
    const int rate = NovaAnyPS5::Video().refreshRate();
    require(rate > 0, "host display refresh rate is invalid");
    displayRefreshRate.store(rate);
}
''' + s[end:]
s = edit(s, '        hdrProbe.Poll(window.Handle());\n', '')
s = edit(s, '    hdrProbe.Poll(window.Handle());\n', '')
s = edit(s, '        hdrProbe.Release();\n', '')
s = edit(s, '    hdrProbe.Release();\n', '')
s = edit(s, '        const auto extensions = windowExtensions(window.Handle());\n        const AgcDriver::PresentationWindow target{window.Handle(), extensions, &createWindowSurface, &windowDrawableSize, req.width, req.height, req.timing};',
         '        auto target = NovaAnyPS5::Video().window();\n        target.width = req.width;\n        target.height = req.height;\n        target.timing = req.timing;\n        if (attachedWindow != target.context) {\n            if (attachedWindow) AgcDriverReleaseWindow_nid_postfix(attachedWindow);\n            AgcDriverAttachWindow_nid_postfix(target);\n            attachedWindow = target.context;\n        }')
s = edit(s, '        const auto extensions = windowExtensions(window.Handle());\n        AgcDriverAttachWindow_nid_postfix({window.Handle(), extensions, &createWindowSurface, &windowDrawableSize, VIDEO_OUT_DEFAULT_WIDTH, VIDEO_OUT_DEFAULT_HEIGHT, nullptr});',
         '        const auto target = NovaAnyPS5::Video().window();\n        AgcDriverAttachWindow_nid_postfix(target);\n        attachedWindow = target.context;')
s = edit(s, '        OnMainThread([&] { window.UpdateTitle(); });\n', '')
# Input comes from Nova's Android controls, not SDL host devices.
s = edit(s, '    std::optional<PadInput> padInput;\n    std::optional<MouseInput> mouseInput;\n    std::optional<KeyboardInput> keyboardInput;\n    std::optional<ImeTextInput> imeTextInput;\n', '')
s = edit(s, '        OnMainThread([&] {\n            padInput.emplace();\n            mouseInput.emplace();\n            keyboardInput.emplace();\n            imeTextInput.emplace();\n        });\n', '')
s = cut(s, '            const bool quit = OnMainThread([&] {\n                SDL_Event event;', '            pollHostHdr();', '            updateDisplayRefreshRate();\n')
s = edit(s, '            OnMainThread([&] { mouseInput->UpdateCapture(!padInput->MouseModeEnabled()); });\n', '')
s = cut(s, '                int windowWidth = 0;', '                const auto finished = ')
s = edit(s, '    OnMainThread([&] {\n        padInput.reset();\n        mouseInput.reset();\n        keyboardInput.reset();\n        imeTextInput.reset();\n        window.Destroy();\n    });', '    window.Destroy();')
s = edit(s, '    req.terminal = true;\n    req.cfg->vblankCond.notify_all();', '    req.terminal = true;\n    NovaAnyPS5::Video().framePresented();\n    req.cfg->vblankCond.notify_all();')
if s.count('sceKernelGetProcessTime()') == 0:
    raise SystemExit('NOVA_ANYPS5_STAGE: process time calls moved')
s = s.replace('sceKernelGetProcessTime()', 'NovaAnyPS5::Video().processTime()').replace('sceKernelGetProcessTimeCounter()', 'NovaAnyPS5::Video().processTimeCounter()')
for banned in ['SDL', 'hdrProbe', 'padInput', 'mouseInput', 'keyboardInput', 'imeTextInput', 'windowExtensions', 'UpdateTitle']:
    if banned in s:
        raise SystemExit(f'NOVA_ANYPS5_STAGE: {banned} remains in staged VideoOutDriver.cpp')
p.write_text(s)
video_cmake = '''add_library(nova_anyps5_video STATIC
    Unimplemented.cpp src/Event.cpp src/Buffer.cpp src/Output.cpp src/VideoOutDriver.cpp)
target_include_directories(nova_anyps5_video PUBLIC "${NOVA_ANYPS5_STAGED_ROOT}/core/libs" "${ANYPS5_SOURCE_DIR}/core/libs" "${NOVA_ANYPS5_RENDERER_ADAPTER_DIR}")
target_link_libraries(nova_anyps5_video PUBLIC nova_anyps5_agc)
target_compile_definitions(nova_anyps5_video PRIVATE APS5_ENABLE_TIMING_LOG=0 APS5_ENABLE_TRACY=0)
set_target_properties(nova_anyps5_video PROPERTIES POSITION_INDEPENDENT_CODE ON)
'''
(video / 'CMakeLists.txt').write_text(video_cmake)
import re
for subtree in [root, api]:
    for p in subtree.rglob('*'):
        if not p.is_file() or p.suffix not in {'.cpp', '.hpp'} or 'tests' in p.parts:
            continue
        s = p.read_text()
        updated = re.sub(r'std::atomic_ref(<[^<>]+>)?\(', lambda m: 'NovaAnyPS5::Atomic' + (m.group(1) or '') + '(', s)
        if updated != s:
            p.write_text('#include "guest_access.hpp"\n' + updated)
p = root / 'Execution/src/Driver/Queues/Submission.cpp'
s = p.read_text()
start = s.index('bool Driver::copySegment(')
end = s.index('\nvoid Driver::readRegisterLists(', start)
segment = s[start:end]
needle = '    budget -= words;'
assert segment.count(needle) == 1
segment = segment.replace(needle, needle + '\n    const NovaAnyPS5::TranslatedRead<std::uint32_t> translated(guest, words);\n    const auto* guestHost = translated.Data();')
segment = segment.replace('guest[', 'guestHost[').replace('submission.commands.end(), guest + cursor, guest + words', 'submission.commands.end(), guestHost + cursor, guestHost + words').replace('submission.commands.end(), guest + cursor, guest + cursor + count', 'submission.commands.end(), guestHost + cursor, guestHost + cursor + count').replace('std::span(guest + cursor, count)', 'std::span(guestHost + cursor, count)')
s = s[:start] + segment + s[end:]
s = s.replace('    const auto descriptor = *packet;', '    Packet descriptor{};\n    GuestMemory::CopyGuestBytes(&descriptor, packet, sizeof(descriptor));')
p.write_text(s)
for p in root.rglob('*.cpp'):
    s = p.read_text()
    changed = False
    for value_type in ['std::uint32_t', 'std::uint64_t']:
        needle = '*reinterpret_cast<const volatile ' + value_type + '*>('
        while needle in s:
            start = s.index(needle)
            first = start + len(needle)
            end, level = first, 1
            while level:
                level += (s[end] == '(') - (s[end] == ')')
                end += 1
            s = s[:start] + 'NovaAnyPS5::ReadVolatile<' + value_type + '>(' + s[first:end-1] + ')' + s[end:]
            changed = True
    if changed:
        p.write_text('#include "guest_access.hpp"\n' + s)
