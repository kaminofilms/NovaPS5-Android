"""Host test of patched AudioOut2ContextGetQueueLevel (patch-0990): the real function body against a
fake sample clock. Usage: test_0990_audio_queue_poll.py <patched kyty tree>"""
from pathlib import Path
import os, subprocess, sys, tempfile

s = (Path(sys.argv[1]) / 'src/libs/libAudio2.cpp').read_text()
a = s.index('// Nova 0990:')
b = s.index('int KYTY_SYSV_ABI AudioOut2PortCreate(', a)
fixture = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <mutex>
#define KYTY_SYSV_ABI
constexpr int OK = 0;
using AudioOut2ContextHandle = uint64_t;
struct Mutex { std::mutex value; void Lock() { value.lock(); } void Unlock() { value.unlock(); } } g_audioout2_state_mutex;
struct State { uint32_t num_grains = 256, queued = 0, queue_depth = 4; uint64_t last_update = 0; } state;
uint64_t clock_us = 1000000;
int sleeps = 0; uint64_t slept = 0;
uint32_t audioout2_grain_micros(uint32_t n) { return std::max<uint32_t>(n * 1000000u / 48000u, 1000u); }
State* audioout2_find_context_locked(uint64_t h) { return h == 1 ? &state : nullptr; }
// Same drain rule as Kyty: whole grains elapsed since last_update leave the queue.
void audioout2_update_context_locked(State* st) {
    if (st->last_update == 0 || st->queued == 0) { st->last_update = clock_us; return; }
    const uint64_t g = audioout2_grain_micros(st->num_grains);
    const uint64_t drained = std::min<uint64_t>(st->queued, (clock_us - st->last_update) / g);
    st->queued -= static_cast<uint32_t>(drained); st->last_update += drained * g;
    if (st->queued == 0) st->last_update = clock_us;
}
namespace LibKernel { uint64_t KernelGetProcessTime() { return clock_us; } }
namespace Common { struct Thread { static void SleepMicro(uint32_t n) {
    assert(g_audioout2_state_mutex.value.try_lock()); g_audioout2_state_mutex.value.unlock();  // never under the lock
    ++sleeps; slept += n; clock_us += n; } }; }
''' + s[a:b] + r'''
int main() {
    uint32_t level = 99, avail = 99;
    const uint64_t grain = audioout2_grain_micros(256);  // 5333 us
    // Not full: answers immediately with the real values.
    state.queued = 2; state.last_update = clock_us;
    assert(AudioOut2ContextGetQueueLevel(1, &level, &avail) == OK && level == 2 && avail == 2 && sleeps == 0);
    // Full: the first answer is immediate and truthful.
    state.queued = 4; state.last_update = clock_us; clock_us += 1000;
    assert(AudioOut2ContextGetQueueLevel(1, &level, &avail) == OK && level == 4 && avail == 0 && sleeps == 0);
    // Repeated full poll: waits until the oldest grain is due (grain - 1000 us), then reports the freed slot.
    assert(AudioOut2ContextGetQueueLevel(1, &level, &avail) == OK && sleeps == 1 && slept == grain - 1000);
    assert(level == 3 && avail == 1);
    // A non-full answer resets the streak: next full poll is immediate again.
    state.queued = 4; state.last_update = clock_us;
    assert(AudioOut2ContextGetQueueLevel(1, &level, &avail) == OK && avail == 0 && sleeps == 1);
    // Unknown context: original defaults, no wait.
    assert(AudioOut2ContextGetQueueLevel(7, &level, &avail) == OK && level == 0 && avail == 4 && sleeps == 1);
    // Null outputs are allowed.
    assert(AudioOut2ContextGetQueueLevel(1, nullptr, nullptr) == OK);
    std::puts("PASS 0990 queue-level: immediate truthful answers; repeated full poll waits one grain outside the lock");
}
'''
with tempfile.TemporaryDirectory() as d:
    d = Path(d); (d / 't.cpp').write_text(fixture)
    subprocess.run(['c++', '-std=c++20', '-pthread', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', str(d / 't.cpp'), '-o', str(d / 't')], check=True)
    subprocess.run([str(d / 't')], check=True, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
