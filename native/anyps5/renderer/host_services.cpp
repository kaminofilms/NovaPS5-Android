#include "host_services.hpp"
#include "prx/libc/include/GuestArena.hpp"
#include "prx/libc/include/Shutdown.hpp"
#include "prx/libkernel/Equeue/Equeue.hpp"
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <condition_variable>
#include <thread>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
namespace NovaAnyPS5 {
namespace {
std::atomic<const HostServices*> installed{nullptr};
std::mutex configureMutex;
HostServices configured{};
}
void ConfigureHostServices(const HostServices& services) {
    if (!services.copy || !services.compare || !services.translate || !services.query ||
        !services.pinQueue || !services.addEvent || !services.deleteEvent || !services.triggerEvent ||
        !services.map || !services.sharedBacking || !services.writeBacking || !services.driverMemory)
        throw std::invalid_argument("AnyPS5 host services are incomplete");
    std::lock_guard lock(configureMutex);
    if (installed.load(std::memory_order_acquire)) throw std::logic_error("AnyPS5 host services are already installed");
    configured = services;
    installed.store(&configured, std::memory_order_release);
}
const HostServices& Services() {
    const auto* services = installed.load(std::memory_order_acquire);
    if (!services) throw std::logic_error("AnyPS5 native host services have not been installed");
    return *services;
}
void CopyMemory(void* destination, const void* source, std::size_t bytes) {
    Services().copy(destination, source, bytes);
}
int CompareMemory(const void* left, const void* right, std::size_t bytes) {
    return Services().compare(left, right, bytes);
}
void* ContiguousMemory(std::uint64_t address, std::size_t bytes) {
    std::size_t available = 0;
    void* host = Services().translate(address, bytes, &available);
    return host && available >= bytes ? host : nullptr;
}
}
extern "C" KernelEqueueRef EqueuePin_nid_postfix(KernelEqueue queue) {
    auto owner = NovaAnyPS5::Services().pinQueue(queue);
    return owner ? KernelEqueueRef(owner, reinterpret_cast<KernelEqueuePrivate*>(owner.get())) : KernelEqueueRef{};
}
extern "C" int EqueueAddEvent_nid_postfix(KernelEqueue queue, const KernelEqueueEvent& event) {
    return NovaAnyPS5::Services().addEvent(queue, event);
}
extern "C" int EqueueDeleteEvent_nid_postfix(KernelEqueue queue, std::uintptr_t id, std::int16_t filter) {
    return NovaAnyPS5::Services().deleteEvent(queue, id, filter);
}
extern "C" int EqueueTriggerEvent_nid_postfix(KernelEqueue queue, std::uintptr_t id, std::int16_t filter, void* data) {
    return NovaAnyPS5::Services().triggerEvent(queue, id, filter, data);
}
extern "C" void* mmap_nid_postfix(void* address, std::size_t bytes, int protection, int flags, int file, std::int64_t offset) noexcept {
    try { return NovaAnyPS5::Services().map(address, bytes, protection, flags, file, offset); }
    catch (...) { std::terminate(); }
}
namespace { std::atomic<std::uint64_t> notImplementedCalls{0}; }
extern "C" std::uint64_t NotImplementedCalls_nid_no_patch() { return notImplementedCalls.load(std::memory_order_relaxed); }
extern "C" [[noreturn]] void NotImplemented_nid_no_patch(const char* function) {
    notImplementedCalls.fetch_add(1, std::memory_order_relaxed);
    throw std::runtime_error(std::string("AnyPS5 unimplemented export: ") + (function ? function : "unknown"));
}
namespace GuestArena {
extern "C" void GuestArenaRange_nid_postfix(std::uintptr_t* base, std::size_t* bytes) {
    NovaAnyPS5::Services();
    *base = 0;
    *bytes = 0;
}
// Nova, not the AnyPS5 arena, owns guest memory (GuestArenaRange reports no arena). The
// upstream arena invokes these hooks from its own host-read and protection paths, which do
// not exist here, so registration is recorded but never invoked: the same behaviour as the
// previous pin, which did not register them at all.
namespace { std::atomic<void (*)(std::uintptr_t, std::size_t)> accessObserver{nullptr}, hostReadHook{nullptr}; }
extern "C" void GuestArenaSetAccessObserver_nid_postfix(void (*callback)(std::uintptr_t, std::size_t)) {
    accessObserver.store(callback, std::memory_order_release);
}
extern "C" void GuestArenaSetHostReadHook_nid_no_patch(void (*hook)(std::uintptr_t, std::size_t)) {
    hostReadHook.store(hook, std::memory_order_release);
}
extern "C" bool GuestArenaSharedBacking_nid_postfix(std::uintptr_t address, std::size_t bytes, int* file, std::uint64_t* offset) {
    return NovaAnyPS5::Services().sharedBacking(address, bytes, file, offset);
}
extern "C" bool GuestArenaWriteSharedBacking_nid_no_patch(std::uintptr_t address, const void* source, std::size_t bytes) {
    return NovaAnyPS5::Services().writeBacking(address, source, bytes);
}
}
namespace {
std::stop_source shutdownSource;
std::mutex shutdownMutex;
std::vector<void (*)()> shutdownCallbacks;
std::atomic<void (*)()> endFlush{nullptr};
std::atomic<void (*)()> exitDrain{nullptr};
bool shutdownStarted = false;
bool shutdownFinished = false;
std::thread::id shutdownThread;
std::condition_variable shutdownChanged;
std::exception_ptr shutdownFailure;
}
extern "C" std::stop_token LibcShutdownToken_nid_postfix() { return shutdownSource.get_token(); }
extern "C" void LibcRequestShutdown_nid_postfix() { shutdownSource.request_stop(); }
extern "C" [[noreturn]] void LibcAwaitExit_nid_postfix() { throw ProcessShutdown{}; }
extern "C" void LibcRegisterShutdown_nid_postfix(void (*callback)()) {
    std::lock_guard lock(shutdownMutex);
    if (!callback || shutdownStarted) throw std::logic_error("Invalid AnyPS5 shutdown callback registration");
    shutdownCallbacks.push_back(callback);
}
// Upstream runs the drain on _Exit (the AGC driver saves its pipeline cache there).
// Nova runs it once at the start of runtime shutdown.
extern "C" void LibcSetExitDrain_nid_no_patch(void (*drain)()) {
    if (!drain) throw std::invalid_argument("Null AnyPS5 exit drain");
    void (*expected)() = nullptr;
    if (!exitDrain.compare_exchange_strong(expected, drain) && expected != drain)
        throw std::logic_error("AnyPS5 exit drain already installed");
}
extern "C" void LibcSetEndFlush_nid_no_patch(void (*flush)()) {
    if (!flush) throw std::invalid_argument("Null AnyPS5 flush callback");
    void (*expected)() = nullptr;
    if (!endFlush.compare_exchange_strong(expected, flush) && expected != flush)
        throw std::logic_error("AnyPS5 flush callback already installed");
}
namespace NovaAnyPS5 {
void ShutdownRuntime() {
    std::unique_lock lock(shutdownMutex);
    if (shutdownStarted) {
        if (!shutdownFinished && shutdownThread == std::this_thread::get_id()) throw std::logic_error("Recursive AnyPS5 runtime shutdown");
        shutdownChanged.wait(lock, [] { return shutdownFinished; });
        if (shutdownFailure) std::rethrow_exception(shutdownFailure);
        return;
    }
    shutdownStarted = true;
    shutdownThread = std::this_thread::get_id();
    auto callbacks = std::move(shutdownCallbacks);
    lock.unlock();
    LibcRequestShutdown_nid_postfix();
    std::exception_ptr failure;
    try { if (auto drain = exitDrain.exchange(nullptr)) drain(); }
    catch (...) { failure = std::current_exception(); }
    for (auto it = callbacks.rbegin(); it != callbacks.rend(); ++it) {
        try { (*it)(); } catch (...) { if (!failure) failure = std::current_exception(); }
    }
    try { if (auto flush = endFlush.load(std::memory_order_acquire)) flush(); }
    catch (...) { if (!failure) failure = std::current_exception(); }
    lock.lock();
    shutdownFailure = failure;
    shutdownFinished = true;
    lock.unlock();
    shutdownChanged.notify_all();
    if (failure) std::rethrow_exception(failure);
}
}
extern "C" void LibcRunShutdown_nid_postfix() { NovaAnyPS5::ShutdownRuntime(); }

// Title metadata for upstream diagnostics (performance trace/overlay labels). Nova's launcher
// exports the installed title ID; Nova has no param.json title or content version here.
#include "prx/libkernel/AppMetadata/include/AppMetadata.hpp"
namespace {
const char* novaTitleId() {
    const char* id = std::getenv("NOVA_CACHE_TITLE_ID");
    return id && *id && std::strlen(id) < sizeof(AppTitleId::value) ? id : nullptr;
}
}
extern "C" bool HasAppParamJson_nid_no_patch() { return novaTitleId() != nullptr; }
extern "C" AppTitleId GetAppTitleId_nid_postfix() {
    AppTitleId result{};
    if (const char* id = novaTitleId()) std::memcpy(result.value, id, std::strlen(id));
    return result;
}
extern "C" AppTitle GetAppTitle_nid_postfix() {
    AppTitle result{};
    if (const char* id = novaTitleId()) std::memcpy(result.value, id, std::strlen(id));
    return result;
}
extern "C" AppContentVersion GetAppContentVersion_nid_no_patch() { return AppContentVersion{}; }
