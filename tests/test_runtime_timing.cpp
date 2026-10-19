#include "native/novafex/runtime_timing.hpp"
#include <cassert>
#include <chrono>
#include <thread>
using namespace NovaFex::Timing;
int main() {
    if (!Enabled()) {
        { Scope guest(Domain::GuestRuntime); Scope host(Domain::HostCall); }
        assert(Read().guest_wall == 0 && Read().host_wall == 0);
        return 0;
    }
    // Nested host -> guest callbacks must be exclusive, with no double count.
    State s;
    assert(s.Enter(Domain::GuestRuntime, {100, 20, true}) == Domain::Idle);
    assert(s.Enter(Domain::HostCall, {200, 60, true}) == Domain::GuestRuntime);
    s.Enter(Domain::GuestRuntime, {400, 80, true});
    s.Enter(Domain::HostCall, {450, 100, true});
    s.Enter(Domain::GuestRuntime, {500, 110, true});
    s.Enter(Domain::Idle, {600, 170, true});
    auto result = Read();
    assert(result.guest_wall == 250 && result.guest_cpu == 120);
    assert(result.host_wall == 250 && result.host_cpu == 30);
    assert(OffCpu(250, 120) == 130 && OffCpu(2, 3) == 0);
    s.Enter(Domain::GuestRuntime, {0, 0, false});
    s.Enter(Domain::Idle, {700, 200, true});
    assert(Read().invalid == 1);
    // Thread-local domains must not leak between workers.
    const auto before = Read();
    std::thread worker([] {
        Scope host(Domain::HostCall);
        std::this_thread::sleep_for(std::chrono::milliseconds(30));
        { Scope guest(Domain::GuestRuntime); }
    });
    worker.join();
    const auto after = Read();
    const auto wall = after.host_wall - before.host_wall;
    const auto cpu = after.host_cpu - before.host_cpu;
    assert(wall >= 20000000 && cpu < wall);
    assert(state.domain == Domain::Idle);
    assert(Now().valid);
}
