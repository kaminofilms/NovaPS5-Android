#!/usr/bin/env python3
"""0.9.63: free the spinning core, skip read-to-read image barriers.

  1. Window event loop (0.9.62 NOVA_THREAD_CPU stack, every title): the SDL main thread used a
     whole core in HostInputWaitEvent -> SDL_WaitEventTimeout -> SDL_UpdateJoysticks ->
     SDL_GetTicks. On Android, SDL's wait loop keeps pumping joysticks instead of blocking. Now
     the loop polls events and sleeps up to 4 ms when none are pending (at most ~250 checks/s),
     which keeps input immediate and the core idle. NOVA_EVENT_POLL_MS (1-16) overrides.
  2. Image barriers (0.9.62 NOVA_PASS_BREAK, Ever Forward ~155 per frame from Image::Transit):
     a transition that keeps the layout and goes from one read-only access to another needs no
     barrier (no read-after-read hazard). Every reader's stage and access are merged into the
     tracked state, so a later write still waits for all of them. Writes, layout changes and
     the first use are unchanged.

NOVA_IMAGE_BARRIERS reports elided / emitted every 5 s.
"""
from pathlib import Path
import sys

src = Path(sys.argv[1]) / 'src/graphics'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0963: anchor changed {path.name}: {old[:80]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


hi = src / 'presentation/window/hostInput.cpp'
edit(hi, '''	timeout              = timeout < 0 ? max_wait_ms : std::min(timeout, max_wait_ms);
	const bool has_event = SDL_WaitEventTimeout(event, timeout);''', '''	timeout              = timeout < 0 ? max_wait_ms : std::min(timeout, max_wait_ms);
#if defined(__ANDROID__)
	// Nova 0.9.63: SDL's Android wait loop pumps joysticks continuously (a full core).
	// Poll, and sleep briefly when nothing is pending.
	static const int nova_poll_ms = [] {
		const char* v = std::getenv("NOVA_EVENT_POLL_MS");
		const int   ms = v != nullptr ? std::atoi(v) : 4;
		return ms < 1 ? 1 : (ms > 16 ? 16 : ms);
	}();
	bool has_event = SDL_PollEvent(event);
	if (!has_event && timeout != 0) {
		SDL_Delay(static_cast<Uint32>(std::min(timeout < 0 ? nova_poll_ms : timeout, nova_poll_ms)));
		has_event = SDL_PollEvent(event);
	}
#else
	const bool has_event = SDL_WaitEventTimeout(event, timeout);
#endif''')
s = changes[hi]
if '#include <cstdlib>' not in s:
    s = s.replace('#include', '#include <cstdlib>\n#include', 1)
changes[hi] = s

im = src / 'host_gpu/renderer/image/image.cpp'
edit(im, '''Image::Barriers Image::GetBarriers(vk::ImageLayout                      destination_layout,''', '''// Nova 0.9.63: read-to-read transitions in the same layout need no barrier.
namespace {
constexpr vk::AccessFlags2 kNovaWriteAccess =
    vk::AccessFlagBits2::eShaderWrite | vk::AccessFlagBits2::eShaderStorageWrite | vk::AccessFlagBits2::eTransferWrite |
    vk::AccessFlagBits2::eMemoryWrite | vk::AccessFlagBits2::eColorAttachmentWrite |
    vk::AccessFlagBits2::eDepthStencilAttachmentWrite | vk::AccessFlagBits2::eHostWrite;
bool NovaReadToRead(const VulkanImageState& from, vk::ImageLayout layout, vk::AccessFlags2 access) {
	static const bool enabled = [] {
		const char* v = std::getenv("NOVA_IMAGE_BARRIER_MERGE");
		return v == nullptr || v[0] != '0';
	}();
	return enabled && from.layout == layout && from.layout != vk::ImageLayout::eUndefined &&
	       from.access_mask != vk::AccessFlags2 {} && !(from.access_mask & kNovaWriteAccess) &&
	       access != vk::AccessFlags2 {} && !(access & kNovaWriteAccess);
}
void NovaCountImageBarrier(bool elided) {
	static std::atomic<uint64_t> skipped {0}, emitted {0};
	static std::atomic<int64_t>  start {0};
	(elided ? skipped : emitted).fetch_add(1, std::memory_order_relaxed);
	const int64_t now = std::chrono::duration_cast<std::chrono::seconds>(
	                        std::chrono::steady_clock::now().time_since_epoch()).count();
	int64_t first = start.load(std::memory_order_relaxed);
	if (first == 0) { start.store(now); return; }
	if (now - first >= 5 && start.compare_exchange_strong(first, now)) {
		std::fprintf(stderr, "NOVA_IMAGE_BARRIERS: read_to_read_elided=%llu emitted=%llu\\n",
		             (unsigned long long)skipped.exchange(0), (unsigned long long)emitted.exchange(0));
	}
}
} // namespace

Image::Barriers Image::GetBarriers(vk::ImageLayout                      destination_layout,''')
edit(im, '''		if (state.layout == destination_layout && state.access_mask == destination_access &&
		    !repeated_write) {
			return {};
		}
''', '''		if (state.layout == destination_layout && state.access_mask == destination_access &&
		    !repeated_write) {
			return {};
		}
		if (NovaReadToRead(state, destination_layout, destination_access)) {
			// Keep every reader in the state so a later write waits for all of them.
			state.pl_stage |= destination_stage;
			state.access_mask |= destination_access;
			NovaCountImageBarrier(true);
			return {};
		}
		NovaCountImageBarrier(false);
''')
s = changes[im]
for inc in ['#include <atomic>', '#include <chrono>', '#include <cstdio>', '#include <cstdlib>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
changes[im] = s

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0963: event loop polls with short sleeps; read-to-read image barriers skipped (NOVA_IMAGE_BARRIER_MERGE=0 restores)')
