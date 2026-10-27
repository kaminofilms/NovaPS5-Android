#include "kyty_bridge.hpp"
#include "memory_mutation.hpp"
#include "android_window.hpp"
#include "renderer/host_services.hpp"
#include "renderer/memory_registry.hpp"
#include "renderer/selected_vulkan_loader.hpp"
#include "renderer/video_platform.hpp"
#include "prx/libc/include/GuestAllocations.hpp"
#include "prx/libc/include/Shutdown.hpp"
#include "prx/libkernel/Equeue/Equeue.hpp"
#include "common/novaFex.h"
#include "common/emulatorConfig.h"
#include "graphics/presentation/window/hostInput.h"
#include "kernel/memory.h"
#include "kernel/eventQueue.h"
#include "kernel/pthread.h"
#include "libs/controller.h"
#include "libs/libs.h"
#include "loader/systemContent.h"
#include <SDL3/SDL.h>
#include <SDL3/SDL_vulkan.h>
#include <android/native_window.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <string_view>
#include <chrono>
#include <atomic>
#include <bit>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <sys/mman.h>
namespace Libs::Graphics::Gen5Driver {
// Defined in Kyty agc.cpp by apply_kyty.py: PS5 driver DMEM through Kyty kernel memory.
void* NovaAnyPS5DriverMemory(uint64_t address, size_t size);
}
#include <thread>
#include <unistd.h>
#include <vector>
extern PFN_vkGetInstanceProcAddr NovaAndroidVulkanLoader(PFN_vkGetInstanceProcAddr);
extern void NovaAndroidNoteFrame();
namespace Libs::LibKernel::Memory {
bool NovaAnyQuery(std::uint64_t, VirtualQueryInfo*);
std::vector<VirtualQueryInfo> NovaAnySnapshot();
bool NovaAnySharedBacking(std::uint64_t, std::size_t, int*, std::uint64_t*);
}
namespace NovaAnyPS5 {
namespace {
namespace Memory = Libs::LibKernel::Memory;
namespace Queue = Libs::LibKernel::EventQueue;
namespace Controller = Libs::Controller;
SDL_Window* appWindow = nullptr;
std::atomic<bool> running{true};
std::atomic<bool> stopped{false};
std::atomic<bool> background{false};
std::mutex windowMutex;
std::vector<std::shared_ptr<AndroidWindow>> windowOwners;
ANativeWindow* lastWindow = nullptr;
PFN_vkGetInstanceProcAddr instanceProc = nullptr;
void* rendererHandle = nullptr;
bool Guest(std::uint64_t address) { return address >= (std::uint64_t{1} << 39) && address < (std::uint64_t{1} << 47); }
void* Translate(std::uint64_t address, std::size_t bytes, std::size_t* available) {
    *available = bytes;
    if (Guest(address) && NovaFex::GuestVAEnabled()) {
        *available = static_cast<std::size_t>(std::min<std::uint64_t>(bytes, (std::uint64_t{1} << 30) - (address & ((std::uint64_t{1} << 30) - 1))));
        const auto host = NovaFex::TranslateGuestVA(address);
        return host != address ? reinterpret_cast<void*>(host) : nullptr;
    }
    return reinterpret_cast<void*>(address);
}
void Copy(void* destination, const void* source, std::size_t bytes) {
    auto to = reinterpret_cast<std::uint64_t>(destination);
    auto from = reinterpret_cast<std::uint64_t>(source);
    std::array<std::byte, 16384> scratch{};
    while (bytes) {
        std::size_t fromBytes = 0, toBytes = 0;
        void* toHost = Translate(to, bytes, &toBytes);
        auto* fromHost = Translate(from, bytes, &fromBytes);
        const auto count = std::min({toBytes, fromBytes, scratch.size()});
        if (!toHost || !fromHost || !count) throw std::runtime_error("AnyPS5 bulk copy reached an unmapped guest VA");
        if (Memory::TryReadBacking(from, scratch.data(), count)) {
            if (!Memory::TryWriteBacking(to, scratch.data(), count)) NovaGuest::Copy(toHost, scratch.data(), count);
        } else if (Memory::TryWriteBacking(to, fromHost, count)) {
        } else {
            NovaGuest::Copy(toHost, fromHost, count);
        }
        to += count;
        from += count;
        bytes -= count;
    }
}
int Compare(const void* left, const void* right, std::size_t bytes) {
    constexpr std::size_t Block = 4096;
    std::array<std::byte, Block> a{}, b{};
    auto x = reinterpret_cast<std::uint64_t>(left), y = reinterpret_cast<std::uint64_t>(right);
    while (bytes) {
        const auto count = std::min(bytes, Block);
        Copy(a.data(), reinterpret_cast<const void*>(x), count);
        Copy(b.data(), reinterpret_cast<const void*>(y), count);
        if (const int compared = std::memcmp(a.data(), b.data(), count)) return compared;
        x += count;
        y += count;
        bytes -= count;
    }
    return 0;
}
void NoteUnmapped(std::uint64_t address, const char* where) {
    static std::atomic<int> reported{0};
    if (reported.fetch_add(1, std::memory_order_relaxed) < 16)
        std::fprintf(stderr, "NOVA_ANYPS5: 0x%016llx is beyond the last %s mapping; reported as unmapped\n", static_cast<unsigned long long>(address), where);
}
bool Query(std::uint64_t address, MemoryRun* run) {
    // Android heap pointers carry a top-byte tag (TBI/MTE, e.g. 0xb4...). Mappings are untagged:
    // look up the untagged address and report the run with the caller's tag restored.
    if (const std::uint64_t tag = address & 0xff00000000000000ull) {
        if (!Query(address & ~0xff00000000000000ull, run)) return false;
        run->begin |= tag;
        run->end |= tag;
        return true;
    }
    Memory::VirtualQueryInfo info{};
    if (Memory::NovaAnyQuery(address, &info)) {
        if (info.start > address) *run = {address, info.start, false, false};
        else *run = {info.start, info.end, info.is_committed && (info.protection & 0x37) != 0, info.is_committed && (info.protection & 0x22) != 0};
        return true;
    }
    // No Kyty range at or after a guest address: the rest of the guest space is unmapped.
    // Upstream walks holes as inaccessible runs, so answer that instead of failing the query.
    if (Guest(address)) { NoteUnmapped(address, "guest"); *run = {address, std::uint64_t{1} << 47, false, false}; return true; }
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps, line)) {
        unsigned long long begin = 0, end = 0;
        char access[5]{};
        if (std::sscanf(line.c_str(), "%llx-%llx %4s", &begin, &end, access) != 3) continue;
        if (end <= address) continue;
        if (begin > address) *run = {address, begin, false, false};
        else *run = {begin, end, access[0] == 'r', access[1] == 'w'};
        return true;
    }
    if (address < (std::uint64_t{1} << 39)) { NoteUnmapped(address, "host"); *run = {address, std::uint64_t{1} << 39, false, false}; return true; }
    NoteUnmapped(address, "queryable");
    return false;
}
struct EventState { ::KernelEqueueEvent event; };
static_assert(sizeof(::KernelEvent) == sizeof(Queue::KernelEvent));
void FromNative(EventState& state, const Queue::KernelEqueueEvent& native) {
    state.event.triggered = native.triggered;
    state.event.deadlineNs = native.deadline_ns;
    state.event.intervalNs = native.interval_ns;
    state.event.event = std::bit_cast<::KernelEvent>(native.event);
    state.event.pendingEvents.clear();
    for (const auto& event : native.pending_events) state.event.pendingEvents.push_back(std::bit_cast<::KernelEvent>(event));
}
void ToNative(Queue::KernelEqueueEvent& native, const EventState& state) {
    native.triggered = state.event.triggered;
    native.deadline_ns = state.event.deadlineNs;
    native.interval_ns = state.event.intervalNs;
    native.event = std::bit_cast<Queue::KernelEvent>(state.event.event);
    native.pending_events.clear();
    for (const auto& event : state.event.pendingEvents) native.pending_events.push_back(std::bit_cast<Queue::KernelEvent>(event));
}
int AddEvent(std::int64_t queue, const ::KernelEqueueEvent& event) {
    if (!event.enabled || event.filter.pollFunc) throw std::runtime_error("AnyPS5 queue event requires unsupported host polling or disabled registration");
    auto state = std::make_shared<EventState>(EventState{event});
    Queue::KernelEqueueEvent native{};
    ToNative(native, *state);
    native.filter.owner = state;
    native.filter.data = state.get();
    native.filter.trigger_func = [](Queue::KernelEqueueEvent* target, void* data) {
        auto& state = *static_cast<EventState*>(target->filter.data);
        FromNative(state, *target);
        if (state.event.filter.triggerFunc) state.event.filter.triggerFunc(&state.event, data);
        ToNative(*target, state);
    };
    native.filter.reset_func = [](Queue::KernelEqueueEvent* target) {
        auto& state = *static_cast<EventState*>(target->filter.data);
        FromNative(state, *target);
        if (state.event.filter.resetFunc) state.event.filter.resetFunc(&state.event);
        ToNative(*target, state);
    };
    native.filter.delete_event_func = [](Queue::KernelEqueue queue, Queue::KernelEqueueEvent* target) {
        auto& state = *static_cast<EventState*>(target->filter.data);
        FromNative(state, *target);
        if (state.event.filter.deleteEventFunc) state.event.filter.deleteEventFunc(queue, &state.event);
    };
    return Queue::KernelAddEvent(queue, native);
}
void* Map(void* address, std::size_t bytes, int protection, int flags, int file, std::int64_t offset) noexcept {
    if ((flags & ~(0x1 | 0x2 | 0x10 | 0x1000)) || (protection & ~7)) { errno = EINVAL; return MAP_FAILED; }
    int hostFlags = (flags & 1) ? MAP_SHARED : MAP_PRIVATE;
    if (flags & 0x10) hostFlags |= MAP_FIXED_NOREPLACE;
    if (flags & 0x1000) hostFlags |= MAP_ANONYMOUS;
    void* mapped = mmap(address, bytes, protection, hostFlags, file, offset);
    if (mapped != MAP_FAILED) {
        try {
            GuestAllocations::Mutation mutation;
            mutation.Add(mapped, bytes, (protection & 3) != 0, (protection & 2) != 0, true);
        } catch (...) { munmap(mapped, bytes); errno = ENOMEM; return MAP_FAILED; }
    }
    return mapped;
}
AgcDriver::PresentationWindow Window() {
    while (running.load(std::memory_order_acquire)) {
        auto* native = static_cast<ANativeWindow*>(SDL_GetPointerProperty(SDL_GetWindowProperties(appWindow), SDL_PROP_WINDOW_ANDROID_WINDOW_POINTER, nullptr));
        if (!background.load(std::memory_order_acquire) && native) {
            std::lock_guard lock(windowMutex);
            if (native != lastWindow) {
                windowOwners.push_back(std::make_shared<AndroidWindow>(native, instanceProc));
                lastWindow = native;
            }
            return windowOwners.back()->Descriptor();
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    throw ProcessShutdown{};
}
int RefreshRate() {
    const auto display = SDL_GetDisplayForWindow(appWindow);
    const auto* mode = SDL_GetCurrentDisplayMode(display);
    if (!mode || mode->refresh_rate <= 0) throw std::runtime_error(std::string("Cannot query Android display refresh: ") + SDL_GetError());
    return static_cast<int>(std::lround(mode->refresh_rate));
}
void Presented() {
    NovaFex::NoteFrame();
    NovaFex::NoteGameFrame();
    NovaAndroidNoteFrame();
}
std::uint32_t Attribute3() {
    std::int32_t value = 0;
    Loader::SystemContentParamSfoGetInt("ATTRIBUTE3", &value);
    return static_cast<std::uint32_t>(value);
}
void AddExports(Loader::SymbolDatabase* symbols, const char* prefix) {
    struct Export { const char* name; const char* nid; const char* library; };
    static constexpr Export exports[] = {
#include "anyps5_exports.inc"
    };
    std::size_t count = 0;
    for (const auto& entry : exports) {
        if (!std::string_view(entry.library).starts_with(prefix)) continue;
        void* function = dlsym(rendererHandle, entry.name);
        if (!function) throw std::runtime_error(std::string("Missing AnyPS5 export: ") + entry.name);
        Loader::SymbolResolve resolve{entry.nid, entry.library, 1, entry.library, 1, 1, Loader::SymbolType::Func};
        const auto gate = Libs::NovaExportAddress(reinterpret_cast<std::uint64_t>(function), Loader::SymbolType::Func);
        symbols->Add(resolve, gate, entry.name);
        Libs::NovaNameHost(reinterpret_cast<std::uint64_t>(function), entry.name);
        ++count;
    }
    std::fprintf(stderr, "NOVA_ANYPS5: installed %zu %s native exports through NovaFEX\n", count, prefix);
}
}
bool Enabled() {
    const char* backend = std::getenv("NOVA_GPU_BACKEND");
    // Keep the established Kyty runtime until AnyPS5 guest-memory integration is device-verified.
    // Experimental AnyPS5 is selected only by an explicit request.
    return backend && std::strcmp(backend, "anyps5") == 0;
}
std::vector<Mapping> MappingSnapshotNow() {
    std::vector<Mapping> result;
    for (const auto& item : Memory::NovaAnySnapshot())
        result.push_back({item.start, item.end - item.start, (item.protection & 0x37) != 0, (item.protection & 0x22) != 0, (item.protection & 0x30) != 0});
    return result;
}
void Initialize() {
    setenv("APS5_TRACE_UNREADABLE", "1", 0);
    if (!std::getenv("ANYPS5_SHADER_CACHE_DIR")) {
        if (const char* work = std::getenv("NOVA_WORKDIR")) {
            const auto cache = (std::filesystem::path(work) / "cache" / "anyps5").string();
            setenv("ANYPS5_SHADER_CACHE_DIR", cache.c_str(), 0);
        }
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD)) throw std::runtime_error(SDL_GetError());
    appWindow = SDL_CreateWindow("NovaPS5 - AnyPS5", Config::GetScreenWidth(), Config::GetScreenHeight(), SDL_WINDOW_VULKAN | SDL_WINDOW_RESIZABLE);
    if (!appWindow) throw std::runtime_error(SDL_GetError());
    Libs::Graphics::HostInputInit(appWindow);
    if (!SDL_Vulkan_LoadLibrary(nullptr)) throw std::runtime_error(SDL_GetError());
    instanceProc = NovaAndroidVulkanLoader(reinterpret_cast<PFN_vkGetInstanceProcAddr>(SDL_Vulkan_GetVkGetInstanceProcAddr()));
    if (!instanceProc) throw std::runtime_error("Nova selected Vulkan driver has no instance entry point");
    rendererHandle = dlopen("libnova_anyps5_renderer.so", RTLD_NOW | RTLD_LOCAL);
    if (!rendererHandle) throw std::runtime_error(dlerror());
    ConfigureSelectedVulkan(instanceProc, std::shared_ptr<void>(rendererHandle, [](void*) {}));
    ConfigureHostServices({Copy, Compare, Translate, Query,
        [](std::int64_t queue) -> std::shared_ptr<void> { return Queue::KernelPinEqueue(queue); },
        AddEvent, Queue::KernelDeleteEvent, Queue::KernelTriggerEvent, Map,
        Memory::NovaAnySharedBacking,
        [](std::uintptr_t address, const void* data, std::size_t bytes) { return Memory::TryWriteBacking(address, data, bytes); },
        [](std::uint64_t address, std::size_t bytes) { return Libs::Graphics::Gen5Driver::NovaAnyPS5DriverMemory(address, bytes); }});
    ConfigureVideoPlatform({Window, RefreshRate, Presented,
        [](int) { running.store(false, std::memory_order_release); }, Attribute3,
        Libs::LibKernel::KernelGetProcessTime, Libs::LibKernel::KernelGetProcessTimeCounter});
    ConfigureMemoryRegistry(MappingSnapshotNow);
    { MemoryChange initial; }
    std::fprintf(stderr, "NOVA_ANYPS5: native ARM64 renderer, AGC API and VideoOut selected; guest execution=NovaFEX\n");
}
void RegisterGraphicsExports(Loader::SymbolDatabase* symbols) { AddExports(symbols, "Graphics5"); }
void RegisterVideoExports(Loader::SymbolDatabase* symbols) { AddExports(symbols, "VideoOut"); }
void Shutdown() {
    if (stopped.exchange(true)) return;
    running.store(false, std::memory_order_release);
    ShutdownRuntime();
    DisableMemoryRegistry();
    Libs::Graphics::HostInputShutdown();
    windowOwners.clear();
    SDL_DestroyWindow(appWindow);
    appWindow = nullptr;
}
}
namespace NovaAnyPS5 {
void RunWindow() {
    using namespace Libs;
    const auto button = [](int value) -> std::uint32_t {
        using namespace Controller;
        switch (value) {
            case SDL_GAMEPAD_BUTTON_SOUTH: return PAD_BUTTON_CROSS;
            case SDL_GAMEPAD_BUTTON_EAST: return PAD_BUTTON_CIRCLE;
            case SDL_GAMEPAD_BUTTON_WEST: return PAD_BUTTON_SQUARE;
            case SDL_GAMEPAD_BUTTON_NORTH: return PAD_BUTTON_TRIANGLE;
            case SDL_GAMEPAD_BUTTON_START: return PAD_BUTTON_OPTIONS;
            case SDL_GAMEPAD_BUTTON_LEFT_STICK: return PAD_BUTTON_L3;
            case SDL_GAMEPAD_BUTTON_RIGHT_STICK: return PAD_BUTTON_R3;
            case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return PAD_BUTTON_L1;
            case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return PAD_BUTTON_R1;
            case SDL_GAMEPAD_BUTTON_DPAD_UP: return PAD_BUTTON_UP;
            case SDL_GAMEPAD_BUTTON_DPAD_RIGHT: return PAD_BUTTON_RIGHT;
            case SDL_GAMEPAD_BUTTON_DPAD_DOWN: return PAD_BUTTON_DOWN;
            case SDL_GAMEPAD_BUTTON_DPAD_LEFT: return PAD_BUTTON_LEFT;
            case SDL_GAMEPAD_BUTTON_TOUCHPAD:
            case SDL_GAMEPAD_BUTTON_BACK: return PAD_BUTTON_TOUCH_PAD;
            default: return 0;
        }
    };
    while (running.load(std::memory_order_acquire)) {
        SDL_Event event{};
        if (!Graphics::HostInputWaitEvent(&event, 33)) continue;
        switch (event.type) {
            case SDL_EVENT_QUIT:
            case SDL_EVENT_TERMINATING: running.store(false, std::memory_order_release); break;
            case SDL_EVENT_WILL_ENTER_BACKGROUND:
            case SDL_EVENT_DID_ENTER_BACKGROUND: background.store(true, std::memory_order_release); break;
            case SDL_EVENT_WILL_ENTER_FOREGROUND:
            case SDL_EVENT_DID_ENTER_FOREGROUND: background.store(false, std::memory_order_release); break;
            case SDL_EVENT_KEY_DOWN:
            case SDL_EVENT_KEY_UP: Graphics::HostInputKey(event.key.key, event.key.down); break;
            case SDL_EVENT_MOUSE_BUTTON_DOWN:
            case SDL_EVENT_MOUSE_BUTTON_UP: Graphics::HostInputMouseButton(event.button.button, event.button.down); break;
            case SDL_EVENT_GAMEPAD_ADDED:
                if (auto* pad = SDL_OpenGamepad(event.gdevice.which)) Controller::Connect(SDL_GetJoystickID(SDL_GetGamepadJoystick(pad)));
                break;
            case SDL_EVENT_GAMEPAD_REMOVED:
                Controller::Disconnect(event.gdevice.which);
                if (auto* pad = SDL_GetGamepadFromID(event.gdevice.which)) SDL_CloseGamepad(pad);
                break;
            case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
            case SDL_EVENT_GAMEPAD_BUTTON_UP:
                if (const auto mapped = button(event.gbutton.button)) Controller::SetButton(event.gbutton.which, mapped, event.gbutton.down);
                break;
            case SDL_EVENT_GAMEPAD_AXIS_MOTION: {
                if (event.gaxis.axis > SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) break;
                const bool trigger = event.gaxis.axis >= SDL_GAMEPAD_AXIS_LEFT_TRIGGER;
                const int value = Controller::controller_get_axis(trigger ? 0 : SDL_JOYSTICK_AXIS_MIN, SDL_JOYSTICK_AXIS_MAX, event.gaxis.value);
                Controller::SetAxis(event.gaxis.which, static_cast<Controller::Axis>(event.gaxis.axis), value);
                break;
            }
            case SDL_EVENT_GAMEPAD_TOUCHPAD_DOWN:
            case SDL_EVENT_GAMEPAD_TOUCHPAD_MOTION:
            case SDL_EVENT_GAMEPAD_TOUCHPAD_UP:
                if (!event.gtouchpad.touchpad) Controller::SetTouchPad(event.gtouchpad.which, event.gtouchpad.finger, event.type != SDL_EVENT_GAMEPAD_TOUCHPAD_UP, event.gtouchpad.x, event.gtouchpad.y);
                break;
            case SDL_EVENT_GAMEPAD_SENSOR_UPDATE:
                if (event.gsensor.sensor == SDL_SENSOR_ACCEL || event.gsensor.sensor == SDL_SENSOR_GYRO)
                    Controller::SetSensor(event.gsensor.which, event.gsensor.sensor == SDL_SENSOR_ACCEL ? Controller::Sensor::Accel : Controller::Sensor::Gyro, event.gsensor.data, event.gsensor.sensor_timestamp / 1000);
                break;
            default: break;
        }
    }
    Shutdown();
}
}
