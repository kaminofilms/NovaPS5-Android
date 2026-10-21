#!/usr/bin/env python3
"""0.9.54: fixes from the owner's 0.9.53 logs (Ever Forward, Dead Cells, Luna,
Hollow Knight, Wonder Boy). See docs/ANDROID-0.9.54.md.

1. Idle submit (Dead Cells freeze): when every PM4 queue is suspended, submit
   the recorded command buffer once so deferred EOP interrupts / operations
   reach the real GPU timeline. Without it a queue waiting on a CPU-written
   flag deadlocks against a CPU thread waiting for that IRQ. Bloodborne-Android
   relies on the same rule (the GPU thread submits when it runs out of work).
2. Periodic submit (Wonder Boy device loss, CPU/GPU overlap): submit every
   NOVA_SUBMIT_DRAWS (default 1024) draws/dispatches, as the inFAMOUS shadPS4
   fork does (ISS_SUBMIT_DRAWS), instead of one huge command buffer.
3. Readback "off" (Ever Forward 2.0-2.5 s/5 s in CPU write faults): shadPS4's
   default GpuReadbacksMode::Disabled. A CPU write to a GPU-written page drops
   the GPU ownership without downloading. "relaxed"/"precise" stay selectable.
4. Audio (Hollow Knight crackle): 80 ms output queue target instead of 40 ms
   (NOVA_AUDIO_LATENCY_MS). The Android low-latency stream mode, which SDL notes
   sounds flat on some devices, is disabled from the launcher.
5. Internal resolution for every title: NOVA_RASTER_SCALE_PCT (25-99) scales
   any 16:9 colour/depth pass of 540p or more through the existing raster scaler.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
src = root / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0954: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# ---- shared switches ----
sync = src / 'graphics/host_gpu/novaSync.h'
edit(sync, '''inline bool PreciseReadbacks() {''', '''// "off" (default, shadPS4 GpuReadbacksMode::Disabled): CPU writes to GPU-written
// pages discard GPU ownership without a download. "relaxed": CPU writes download
// first. "precise": reads are protected too. Accurate labels force precise.
inline bool ReadbackOff() {
    static const bool off = [] {
        const char* value = std::getenv("NOVA_READBACK_MODE");
        if (!FastLabels()) return false;
        return !value || std::string_view(value) == "off";
    }();
    return off;
}
inline uint32_t SubmitEveryDraws() {
    static const uint32_t every = [] {
        const char* value = std::getenv("NOVA_SUBMIT_DRAWS");
        const long n = value ? std::strtol(value, nullptr, 10) : 1024;
        return n <= 0 ? 0u : uint32_t(n < 64 ? 64 : (n > 65536 ? 65536 : n));
    }();
    return every;
}
inline bool PreciseReadbacks() {''')

# ---- 1 + 2: idle submit and periodic submit ----
gr = src / 'graphics/guest_gpu/graphicsRun.cpp'
edit(gr, '''	g_gpu_thread = true;
	g_gpu_state  = gpu;

	for (;;) {
		Submission                   submission;''', '''	g_gpu_thread = true;
	g_gpu_state  = gpu;
	// Nova 0.9.54: submit recorded work once per idle period so deferred IRQs
	// and operations reach the GPU timeline while every queue waits.
	bool nova_idle_flushed = false;
	bool nova_flush_idle   = false;

	for (;;) {
		if (nova_flush_idle) {
			nova_flush_idle = false;
			gpu->m_gfx_cp->BufferInit();
			gpu->m_gfx_cp->BufferFlush();
		}
		Submission                   submission;''')
edit(gr, '''				if (selected_queue < 0) {
					gpu->m_processing = false;
					{
						NovaRender::Scope wait_cost(NovaRender::Cost::QueuePollWait);
					gpu->m_work_available.WaitFor(&gpu->m_queue_mutex, 100);
					}''', '''				if (selected_queue < 0) {
					gpu->m_processing = false;
					if (!nova_idle_flushed) {
						nova_idle_flushed = true;
						nova_flush_idle   = true;
					} else {
						NovaRender::Scope wait_cost(NovaRender::Cost::QueuePollWait);
					gpu->m_work_available.WaitFor(&gpu->m_queue_mutex, 100);
					}''')
edit(gr, '''			gpu->m_gfx_cp->BufferInit();
			command();
''', '''			gpu->m_gfx_cp->BufferInit();
			command();
			nova_idle_flushed = false;
''')
edit(gr, '''		const bool complete = gpu->Process(submission);
''', '''		const bool complete = gpu->Process(submission);
		if (complete) nova_idle_flushed = false;
''')
edit(gr, 'void CommandProcessor::DrawIndex(DrawIndexArgs args) {', '''// Nova 0.9.54: bounded command buffers keep the GPU busy while recording
// continues and avoid multi-second submissions (inFAMOUS shadPS4 fork).
template <typename Scheduler>
static void NovaPeriodicSubmit(Scheduler& scheduler) {
	static thread_local uint32_t work = 0;
	const auto every = NovaSync::SubmitEveryDraws();
	if (every != 0 && ++work >= every) {
		work = 0;
		scheduler.Flush();
	}
}

void CommandProcessor::DrawIndex(DrawIndexArgs args) {''')
edit(gr, '''	m_renderer.GetRenderExecutor().DrawIndex(m_submit_id, CurrentBuffer(), args);
}''', '''	m_renderer.GetRenderExecutor().DrawIndex(m_submit_id, CurrentBuffer(), args);
	NovaPeriodicSubmit(GetScheduler());
}''')
edit(gr, '''	m_renderer.GetRenderExecutor().DrawAuto(m_submit_id, CurrentBuffer(), args);
}''', '''	m_renderer.GetRenderExecutor().DrawAuto(m_submit_id, CurrentBuffer(), args);
	NovaPeriodicSubmit(GetScheduler());
}''')
edit(gr, '''	m_renderer.GetRenderExecutor().DispatchIndirect(m_submit_id, CurrentBuffer(), args_addr, mode,
	                                                IsAsyncComputeQueue());
}''', '''	m_renderer.GetRenderExecutor().DispatchIndirect(m_submit_id, CurrentBuffer(), args_addr, mode,
	                                                IsAsyncComputeQueue());
	NovaPeriodicSubmit(GetScheduler());
}''')

# ---- 3: readback off ----
bc = src / 'graphics/host_gpu/renderer/cache/bufferCache.cpp'
edit(bc, '''		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		if (DownloadBufferMemory<false>(buffer, vaddr, size, context)) {''', '''		if (is_write && NovaSync::ReadbackOff()) {
			// shadPS4 default (readbacks disabled): the CPU write wins. Drop GPU
			// ownership of the faulting range without a GPU download or wait.
			m_memory_tracker.ForEachDownloadRange<false>(vaddr, size, [&](uint64_t address, uint64_t bytes) noexcept {
				m_eop_labels.Invalidate(address, bytes);
				m_gpu_modified_ranges.Subtract(address, bytes);
			});
			m_memory_tracker.UnmarkRegionAsGpuModified(vaddr, size);
			m_memory_tracker.MarkRegionAsCpuModified(vaddr, size);
			return;
		}
		auto& buffer = m_slot_buffers[FindBuffer(vaddr, size)];

		if (DownloadBufferMemory<false>(buffer, vaddr, size, context)) {''')
bcs = changes[bc]
if 'graphics/host_gpu/novaSync.h' not in bcs:
    i = bcs.index('#include')
    changes[bc] = bcs[:i] + '#include "graphics/host_gpu/novaSync.h"\n' + bcs[i:]

# ---- 4: audio latency ----
au = src / 'libs/audio.cpp'
edit(au, 'constexpr uint64_t AUDIO_OUT_TARGET_LATENCY_US = 40000;', '''// Nova 0.9.54: 80 ms default absorbs 30-60 FPS frame-time swings (was 40 ms).
static uint64_t NovaAudioLatencyUs() {
	const char* value = std::getenv("NOVA_AUDIO_LATENCY_MS");
	const long ms = value ? std::strtol(value, nullptr, 10) : 80;
	return uint64_t(ms < 20 ? 20 : (ms > 250 ? 250 : ms)) * 1000u;
}
static const uint64_t AUDIO_OUT_TARGET_LATENCY_US = NovaAudioLatencyUs();''')

# Android low-latency AAudio mode sounds flat/muffled on some devices (SDL note
# in SDL_aaudio.c). Default off; NOVA_AUDIO_LOW_LATENCY=1 restores it.
edit(au, '	if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {', '''	{
		const char* nova_low_latency = std::getenv("NOVA_AUDIO_LOW_LATENCY");
		SDL_SetHint(SDL_HINT_ANDROID_LOW_LATENCY_AUDIO,
		            (nova_low_latency && nova_low_latency[0] == '1') ? "1" : "0");
	}
	if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {''', count=2)

# ---- 5: internal resolution for every title ----
rs = src / 'common/novaRasterScale.h'
s = rs.read_text()
a = s.index('inline uint32_t Height(){'); b = s.index('inline void Note(')
s = s[:a] + '''// Nova 0.9.54: every title. NOVA_RASTER_SCALE_PCT in [25, 99] scales eligible
// 16:9 colour/depth passes of 540p or more; anything else stays native.
inline uint32_t ScalePct(){
 static const auto value=[]()->uint32_t{
  const auto* request=std::getenv("NOVA_RASTER_SCALE_PCT");
  const long pct=request?std::strtol(request,nullptr,10):100;
  return (pct<25||pct>=100)?100u:uint32_t(pct);
 }();return value;
}
inline bool Enabled(){return ScalePct()<100;}
inline std::pair<uint32_t,uint32_t> Extent(uint32_t w,uint32_t h){
 if(!Enabled()||h<540||uint64_t(w)*9!=uint64_t(h)*16)return {};
 const uint32_t rw=(w*ScalePct()/100)&~1u, rh=(h*ScalePct()/100)&~1u;
 if(rw==0||rh==0||rh>=h)return {};
 return {rw,rh};
}
''' + s[b:]
old_note = '''  std::fprintf(stderr,"NOVA_RESOLUTION_RASTER: native=%ux%u raster=%ux%u scaled_draws=%llu native_fallback_draws=%llu; native-sized compute/readback preserved\\n",
    w,h,Height()*16/9,Height(),(unsigned long long)scaled,(unsigned long long)native);'''
if s.count(old_note) != 1:
    raise SystemExit('NOVA_0954: raster note anchor changed')
s = s.replace(old_note, '''  std::fprintf(stderr,"NOVA_RESOLUTION_RASTER: native=%ux%u raster=%ux%u (%u%%) scaled_draws=%llu native_fallback_draws=%llu; native-sized compute/readback preserved\\n",
    w,h,Extent(w,h).first,Extent(w,h).second,ScalePct(),(unsigned long long)scaled,(unsigned long long)native);''')
if '#include <cstdlib>' not in s:
    s = '#include <cstdlib>\n' + s
changes[rs] = s

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0954: idle submit, periodic submit, readback off, 80 ms audio queue, per-title internal resolution')
