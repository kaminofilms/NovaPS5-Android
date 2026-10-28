#!/usr/bin/env python3
"""Task 5 (CRI audio CPU): stop CRI's Audio Output thread spinning on AudioOut2ContextGetQueueLevel.

Device logs (Wonder Boy, 0.9.103/0.9.104) show the CRI Audio Output thread at 80-100% of a core
while AudioOut itself costs ~1.5 ms per 5 s (NOVA_AUDIO_COST), ~6-7 million host calls per second,
and the freeze-report stack of that thread inside AudioOut2ContextGetQueueLevel. CRI polls the
queue level until a queue slot frees. A slot frees only when a grain drains on Kyty's sample clock
(audioout2_update_context_locked), so a repeated "full" answer cannot change before that time.

When the same thread asks again and the queue is still full, wait (outside the state lock) until
the next grain is due, then re-read the real state and return it. The first full answer is
returned immediately, and the answer is always the actual queue state after the wait: nothing is
faked. Kyty's own blocking ContextPush already waits on the same grain clock.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/libs/libAudio2.cpp'
s = p.read_text()
a = s.index('int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(')
b = s.index('int KYTY_SYSV_ABI AudioOut2PortCreate(', a)
old = s[a:b]
expected = '''int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(AudioOut2ContextHandle ctx, uint32_t* queue_level,
                                                uint32_t* available_queues) {
	if (queue_level != nullptr) {
		*queue_level = 0;
	}
	if (available_queues != nullptr) {
		*available_queues = 4;
	}

	g_audioout2_state_mutex.Lock();
	if (auto* state = audioout2_find_context_locked(ctx); state != nullptr) {
		audioout2_update_context_locked(state);
		if (queue_level != nullptr) {
			*queue_level = state->queued;
		}
		if (available_queues != nullptr) {
			*available_queues =
			    (state->queued < state->queue_depth ? state->queue_depth - state->queued : 0);
		}
	}
	g_audioout2_state_mutex.Unlock();

	return OK;
}
'''
if old.strip() != expected.strip():
    raise SystemExit('0990: AudioOut2ContextGetQueueLevel changed; no source written')
new = '''// Nova 0990: repeated full-queue polls wait for the next grain (see tools/ci/patch-0990).
struct NovaQueuePollStats {
	std::atomic<uint64_t> calls {0}, full {0}, waits {0}, waited_micros {0};
	std::atomic<uint64_t> next_report {0};
};
static NovaQueuePollStats g_nova_queue_poll;

static void nova_queue_poll_report(uint64_t now) {
	auto due = g_nova_queue_poll.next_report.load(std::memory_order_relaxed);
	if (now < due || !g_nova_queue_poll.next_report.compare_exchange_strong(due, now + 5000000, std::memory_order_relaxed)) {
		return;
	}
	if (due == 0) {
		return;
	}
	std::fprintf(stderr, "NOVA_AUDIO_POLL: 5s queue-level calls=%llu full=%llu waits=%llu waited_ms=%llu\\n",
	             static_cast<unsigned long long>(g_nova_queue_poll.calls.exchange(0)),
	             static_cast<unsigned long long>(g_nova_queue_poll.full.exchange(0)),
	             static_cast<unsigned long long>(g_nova_queue_poll.waits.exchange(0)),
	             static_cast<unsigned long long>(g_nova_queue_poll.waited_micros.exchange(0) / 1000));
}

int KYTY_SYSV_ABI AudioOut2ContextGetQueueLevel(AudioOut2ContextHandle ctx, uint32_t* queue_level,
                                                uint32_t* available_queues) {
	// Consecutive full answers seen by this thread (any context; reset by a non-full answer).
	thread_local uint32_t full_answers = 0;
	g_nova_queue_poll.calls.fetch_add(1, std::memory_order_relaxed);
	nova_queue_poll_report(LibKernel::KernelGetProcessTime());
	for (int round = 0;; round++) {
		if (queue_level != nullptr) {
			*queue_level = 0;
		}
		if (available_queues != nullptr) {
			*available_queues = 4;
		}

		bool     full        = false;
		uint64_t wait_micros = 0;
		uint64_t now         = 0;
		g_audioout2_state_mutex.Lock();
		if (auto* state = audioout2_find_context_locked(ctx); state != nullptr) {
			audioout2_update_context_locked(state);
			if (queue_level != nullptr) {
				*queue_level = state->queued;
			}
			if (available_queues != nullptr) {
				*available_queues =
				    (state->queued < state->queue_depth ? state->queue_depth - state->queued : 0);
			}
			full = state->queue_depth != 0 && state->queued >= state->queue_depth;
			if (full) {
				// The next slot frees when the oldest queued grain is due on the sample clock.
				const auto grain = static_cast<uint64_t>(audioout2_grain_micros(state->num_grains));
				now = LibKernel::KernelGetProcessTime();
				const auto elapsed = now > state->last_update ? now - state->last_update : 0;
				wait_micros = elapsed < grain ? grain - elapsed : 0;
				wait_micros = std::clamp<uint64_t>(wait_micros, 100, grain);
			}
		}
		g_audioout2_state_mutex.Unlock();

		if (!full) {
			full_answers = 0;
			break;
		}
		g_nova_queue_poll.full.fetch_add(1, std::memory_order_relaxed);
		if (++full_answers < 2 || round > 0) {
			break;
		}
		g_nova_queue_poll.waits.fetch_add(1, std::memory_order_relaxed);
		g_nova_queue_poll.waited_micros.fetch_add(wait_micros, std::memory_order_relaxed);
		Common::Thread::SleepMicro(static_cast<uint32_t>(wait_micros));
	}

	return OK;
}

'''
s = s[:a] + new + s[b:]
for header in ('#include <atomic>', '#include <cstdio>', '#include <algorithm>'):
    if header not in s:
        s = header + '\n' + s
p.write_text(s)
print('0990: repeated full AudioOut2 queue-level polls wait for the next grain; NOVA_AUDIO_POLL reports them')
