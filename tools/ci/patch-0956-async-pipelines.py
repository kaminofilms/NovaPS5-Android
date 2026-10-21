#!/usr/bin/env python3
"""0.9.56: background graphics pipeline compilation (Eden/yuzu "asynchronous
shaders", also shipped by other Kyty-based Android builds).

New graphics pipelines used to be compiled on the GPU thread: every new shader
combination froze the game (NOVA_PIPELINE_TIME up to ~120 ms in owner logs).

Now a draw that needs a pipeline that is not built yet queues it on one worker
thread and waits at most NOVA_ASYNC_WAIT_US (default 2000 us, so pipelines found
in the driver/disk cache are still used immediately). If it is not ready, the
draw is skipped for that frame; the next draw with the same state uses it once
the worker finishes.

Never skipped (always compiled synchronously, as before):
  * draws whose shaders write buffers/images/addresses (side effects),
  * rect-list and tessellation draws (they build helper shaders per draw),
  * every draw when NOVA_ASYNC_PIPELINES=0.

Thread safety: the job owns copies of every input (pipeline key, vertex/pixel
input info and the compiled-shader metadata, whose storage can move when the
shader cache grows). One mutex serializes CreatePipelineInternal, which shares
the pipeline-library maps. The pipeline table itself stays on the GPU thread.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]); src = root / 'src'
changes = {}


def edit(path, old, new, count=1):
    s = changes.get(path, path.read_text())
    if s.count(old) != count:
        raise SystemExit(f'NOVA_0956_ASYNC: anchor changed {path}: {old[:90]!r} ({s.count(old)})')
    changes[path] = s.replace(old, new)


# ---- switches ----
sync = src / 'graphics/host_gpu/novaSync.h'
edit(sync, 'inline uint32_t SubmitEveryDraws() {', '''// Nova 0.9.56: background graphics pipeline compilation (default on).
inline bool AsyncPipelines() {
    static const bool on = [] {
        const char* value = std::getenv("NOVA_ASYNC_PIPELINES");
        return !(value && value[0] == '0');
    }();
    return on;
}
// How long a draw waits for a queued pipeline before it is skipped (microseconds).
inline uint32_t AsyncWaitUs() {
    static const uint32_t us = [] {
        const char* value = std::getenv("NOVA_ASYNC_WAIT_US");
        const long n = value ? std::strtol(value, nullptr, 10) : 2000;
        return uint32_t(n < 0 ? 0 : (n > 50000 ? 50000 : n));
    }();
    return us;
}
inline uint32_t SubmitEveryDraws() {''')

# ---- header ----
hdr = src / 'graphics/host_gpu/renderer/pipeline/pipelineCache.h'
edit(hdr, '#include <memory>\n', '#include <memory>\n#include <mutex>\n')
edit(hdr, '''	Pipeline& GetGraphicsPipeline(std::span<const RenderColorInfo>       colors,
	                              const RenderDepthInfo&                 depth,
	                              std::span<const ShaderVertexInputInfo> vertex_info,
	                              CommandBuffer& command, const ShaderPixelInputInfo* ps_input_info,
	                              vk::PrimitiveTopology topology, bool primitive_restart_enable,
	                              const GraphicsPrograms& programs);''',
     '''	// Nova 0.9.56: returns nullptr only when allow_async is set and the pipeline
	// is still compiling in the background (the caller skips that draw).
	Pipeline* GetGraphicsPipeline(std::span<const RenderColorInfo>       colors,
	                              const RenderDepthInfo&                 depth,
	                              std::span<const ShaderVertexInputInfo> vertex_info,
	                              CommandBuffer& command, const ShaderPixelInputInfo* ps_input_info,
	                              vk::PrimitiveTopology topology, bool primitive_restart_enable,
	                              const GraphicsPrograms& programs, bool allow_async = false);''')
edit(hdr, '''	void InitializeDriverCache();
};''', '''	void InitializeDriverCache();

	// Nova 0.9.56 background compilation (see pipelineCache.cpp).
	struct NovaAsyncJob;
	struct NovaAsyncWorker;
	std::mutex m_nova_compile_mutex;
	std::unordered_map<GraphicsPipelineKey, std::shared_ptr<NovaAsyncJob>, GraphicsPipelineKeyHash>
	    m_nova_pending;
	std::unique_ptr<NovaAsyncWorker> m_nova_worker;
	Pipeline* NovaInsertGraphics(GraphicsPipelineKey key, std::unique_ptr<Pipeline> cached);
	void      NovaAsyncStats(bool queued, bool skipped, bool waited_ok);
};''')

# ---- implementation ----
cpp = src / 'graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
s = cpp.read_text()
for inc in ('#include <condition_variable>', '#include <deque>', '#include <thread>', '#include <chrono>',
            '#include <cstdio>', '#include "graphics/host_gpu/novaSync.h"'):
    if inc not in s:
        s = s.replace('#include <algorithm>\n', '#include <algorithm>\n' + inc + '\n', 1)
changes[cpp] = s

edit(cpp, '''PipelineCache::PipelineCache(GraphicContext& graphics)''', '''// ---- Nova 0.9.56: background graphics pipeline compilation ----
struct PipelineCache::NovaAsyncJob {
	GraphicsPipelineKey                                   key;
	std::array<ShaderVertexInputInfo, 3>                  vertex_info {};
	uint32_t                                              vertex_count = 1;
	ShaderPixelInputInfo                                  pixel_info {};
	bool                                                  ps_active = false;
	GraphicsPrograms                                      programs;
	// Owned copies: Permutation storage in the shader cache may move.
	std::array<ShaderRecompiler::IR::CompiledShaderInfo, 4> compiled {};
	ShaderRecompiler::IR::ResourceSnapshot                  resources {};
	Pipeline                                                pipeline;
	std::atomic<bool>                                       done {false};
	std::chrono::steady_clock::time_point                   queued;
	uint32_t                                                compile_ms = 0;
};

struct PipelineCache::NovaAsyncWorker {
	explicit NovaAsyncWorker(std::function<void(NovaAsyncJob&)> compile_fn)
	    : compile(std::move(compile_fn)), thread([this] { Run(); }) {}
	~NovaAsyncWorker() {
		{
			std::lock_guard lock(mutex);
			stopping = true;
		}
		work.notify_all();
		thread.join();
	}
	void Post(std::shared_ptr<NovaAsyncJob> job) {
		{
			std::lock_guard lock(mutex);
			queue.push_back(std::move(job));
		}
		work.notify_all();
	}
	bool WaitFor(const NovaAsyncJob& job, std::chrono::microseconds timeout) {
		if (job.done.load(std::memory_order_acquire)) return true;
		std::unique_lock lock(mutex);
		return finished.wait_for(lock, timeout, [&] { return job.done.load(std::memory_order_acquire); });
	}
	void Wait(const NovaAsyncJob& job) {
		std::unique_lock lock(mutex);
		finished.wait(lock, [&] { return job.done.load(std::memory_order_acquire); });
	}
	size_t Pending() {
		std::lock_guard lock(mutex);
		return queue.size();
	}

private:
	void Run() {
		std::unique_lock lock(mutex);
		for (;;) {
			work.wait(lock, [this] { return stopping || !queue.empty(); });
			if (queue.empty()) return; // stopping with nothing left
			auto job = std::move(queue.front());
			queue.pop_front();
			lock.unlock();
			compile(*job);
			lock.lock();
			job->done.store(true, std::memory_order_release);
			finished.notify_all();
		}
	}
	std::function<void(NovaAsyncJob&)>        compile;
	std::mutex                                mutex;
	std::condition_variable                   work;
	std::condition_variable                   finished;
	std::deque<std::shared_ptr<NovaAsyncJob>> queue;
	bool                                      stopping = false;
	std::thread                               thread;
};

void PipelineCache::NovaAsyncStats(bool queued, bool skipped, bool waited_ok) {
	static uint64_t q = 0, sk = 0, ok = 0;
	static auto     begin = std::chrono::steady_clock::now();
	q += queued ? 1 : 0;
	sk += skipped ? 1 : 0;
	ok += waited_ok ? 1 : 0;
	const auto now = std::chrono::steady_clock::now();
	if (now - begin >= std::chrono::seconds(5)) {
		std::fprintf(stderr,
		             "NOVA_ASYNC_PIPELINES: queued=%llu ready_in_time=%llu skipped_draws=%llu pending=%zu\\n",
		             (unsigned long long)q, (unsigned long long)ok, (unsigned long long)sk,
		             m_nova_worker ? m_nova_worker->Pending() : size_t {0});
		q = sk = ok = 0;
		begin = now;
	}
}

PipelineCache::Pipeline* PipelineCache::NovaInsertGraphics(GraphicsPipelineKey key,
                                                           std::unique_ptr<Pipeline> cached) {
	EXIT_NOT_IMPLEMENTED(cached->pipeline == nullptr);
	EXIT_NOT_IMPLEMENTED(cached->pipeline_layout == nullptr);

	auto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));
	EXIT_IF(!inserted);
	m_last_graphics_key=iter->first; m_last_graphics_pipeline=iter->second.get();

	// Native Android kills the game process on Exit Game. Save an early
	// warmup snapshot, then every 64 new pipelines. Retain the Vulkan handle:
	// driver objects already in flight and synchronization are untouched.
#if defined(KYTY_NOVA_FEX)
	const size_t nova_count = m_graphics_pipelines.size() + m_compute_pipelines.size();
	if (nova_count == 1u || nova_count == 16u || (nova_count > 16u && nova_count % 64u == 0u)) {
		Save(true);
	}
#endif
	return iter->second.get();
}

PipelineCache::PipelineCache(GraphicContext& graphics)''')

edit(cpp, '''	InitializeDriverCache();
}

PipelineCache::~PipelineCache() {
	Save();''', '''	InitializeDriverCache();
	if (NovaSync::AsyncPipelines()) {
		m_nova_worker = std::make_unique<NovaAsyncWorker>([this](NovaAsyncJob& job) {
			const auto start = std::chrono::steady_clock::now();
			{
				std::lock_guard lock(m_nova_compile_mutex);
				CreatePipelineInternal(m_graphics, job.pipeline, job.key.rendering, job.key.vertex_input,
				                       std::span {job.vertex_info.data(), job.vertex_count},
				                       job.ps_active ? &job.pixel_info : nullptr, job.programs,
				                       job.key.static_params, m_driver_cache, m_libraries);
			}
			job.compile_ms = uint32_t(std::chrono::duration_cast<std::chrono::milliseconds>(
			    std::chrono::steady_clock::now() - start).count());
		});
		std::fprintf(stderr, "NOVA_ASYNC_PIPELINES: on (wait %u us before a draw is skipped)\\n",
		             NovaSync::AsyncWaitUs());
	} else {
		std::fprintf(stderr, "NOVA_ASYNC_PIPELINES: off\\n");
	}
}

PipelineCache::~PipelineCache() {
	// Finish queued background compiles before any Vulkan object is destroyed.
	m_nova_worker.reset();
	for (auto& [key, job] : m_nova_pending) {
		(void)key;
		if (job->pipeline.pipeline) m_graphics.device.destroyPipeline(job->pipeline.pipeline, nullptr);
		if (job->pipeline.pipeline_layout) m_graphics.device.destroyPipelineLayout(job->pipeline.pipeline_layout, nullptr);
		if (job->pipeline.descriptor_set_layout) m_graphics.device.destroyDescriptorSetLayout(job->pipeline.descriptor_set_layout, nullptr);
	}
	m_nova_pending.clear();
	Save();''')

# Signature and the miss path of GetGraphicsPipeline.
edit(cpp, '''PipelineCache::Pipeline& PipelineCache::GetGraphicsPipeline(
    std::span<const RenderColorInfo> colors, const RenderDepthInfo& depth,
    std::span<const ShaderVertexInputInfo> vertex_info, CommandBuffer& command,
    const ShaderPixelInputInfo* ps_input_info, vk::PrimitiveTopology topology,
    bool primitive_restart_enable, const GraphicsPrograms& programs) {''',
     '''PipelineCache::Pipeline* PipelineCache::GetGraphicsPipeline(
    std::span<const RenderColorInfo> colors, const RenderDepthInfo& depth,
    std::span<const ShaderVertexInputInfo> vertex_info, CommandBuffer& command,
    const ShaderPixelInputInfo* ps_input_info, vk::PrimitiveTopology topology,
    bool primitive_restart_enable, const GraphicsPrograms& programs, bool allow_async) {''')
edit(cpp, '''	if (m_last_graphics_pipeline != nullptr && key == m_last_graphics_key) return *m_last_graphics_pipeline;
	if (auto iter = m_graphics_pipelines.find(key); iter != m_graphics_pipelines.end()) {
		m_last_graphics_key=key; m_last_graphics_pipeline=iter->second.get();
		return *iter->second;
	}
''', '''	if (m_last_graphics_pipeline != nullptr && key == m_last_graphics_key) return m_last_graphics_pipeline;
	if (auto iter = m_graphics_pipelines.find(key); iter != m_graphics_pipelines.end()) {
		m_last_graphics_key=key; m_last_graphics_pipeline=iter->second.get();
		return iter->second.get();
	}

	// Nova 0.9.56: a pipeline already queued in the background.
	if (auto pending = m_nova_pending.find(key); pending != m_nova_pending.end()) {
		auto job = pending->second;
		if (!job->done.load(std::memory_order_acquire)) {
			if (allow_async) {
				NovaAsyncStats(false, true, false);
				return nullptr;
			}
			m_nova_worker->Wait(*job);
		}
		m_nova_pending.erase(pending);
		if (job->compile_ms >= 100) {
			std::fprintf(stderr, "NOVA_PIPELINE_TIME: kind=graphics ms=%u background=1\\n", job->compile_ms);
		}
		return NovaInsertGraphics(std::move(key), std::make_unique<Pipeline>(job->pipeline));
	}
	const bool nova_async = allow_async && m_nova_worker && !rect_list && vertex_info.size() == 1 &&
	                        programs.VertexStageCount() == 1;
	if (nova_async) {
		auto job          = std::make_shared<NovaAsyncJob>();
		job->key          = key;
		job->vertex_count = 1;
		job->vertex_info[0] = vertex_info[0];
		job->compiled[0]  = *vertex_info[0].stage.program;
		job->vertex_info[0].stage.program   = &job->compiled[0];
		job->vertex_info[0].stage.resources = &job->resources;
		job->ps_active = ps_active;
		if (ps_active) {
			job->pixel_info              = *ps_input_info;
			job->compiled[3]             = *ps_input_info->stage.program;
			job->pixel_info.stage.program   = &job->compiled[3];
			job->pixel_info.stage.resources = &job->resources;
		}
		job->programs = programs;
		job->queued   = std::chrono::steady_clock::now();
		m_nova_pending.emplace(key, job);
		m_nova_worker->Post(job);
		const bool ready = m_nova_worker->WaitFor(*job, std::chrono::microseconds(NovaSync::AsyncWaitUs()));
		NovaAsyncStats(true, !ready, ready);
		if (!ready) return nullptr;
		m_nova_pending.erase(key);
		return NovaInsertGraphics(std::move(key), std::make_unique<Pipeline>(job->pipeline));
	}
''')
edit(cpp, '''	auto cached = std::make_unique<Pipeline>();
	LogPipelineTrace("CreatePipelineInternal begin", vs_id, ps_id);
	CreatePipelineInternal(m_graphics, *cached, rendering, key.vertex_input, vertex_info,
	                       ps_input_info, programs, static_params, m_driver_cache, m_libraries);
	LogPipelineTrace("CreatePipelineInternal done", vs_id, ps_id);

	EXIT_NOT_IMPLEMENTED(cached->pipeline == nullptr);
	EXIT_NOT_IMPLEMENTED(cached->pipeline_layout == nullptr);

	auto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));
	EXIT_IF(!inserted);
	m_last_graphics_key=iter->first; m_last_graphics_pipeline=iter->second.get();

	// Native Android kills the game process on Exit Game. Save an early
	// warmup snapshot, then every 64 new pipelines. Retain the Vulkan handle:
	// driver objects already in flight and synchronization are untouched.
#if defined(KYTY_NOVA_FEX)
	const size_t nova_count = m_graphics_pipelines.size() + m_compute_pipelines.size();
	if (nova_count == 1u || nova_count == 16u || (nova_count > 16u && nova_count % 64u == 0u)) {
		Save(true);
	}
#endif
	return *iter->second;
}''', '''	auto cached = std::make_unique<Pipeline>();
	LogPipelineTrace("CreatePipelineInternal begin", vs_id, ps_id);
	{
		std::lock_guard nova_lock(m_nova_compile_mutex);
		CreatePipelineInternal(m_graphics, *cached, rendering, key.vertex_input, vertex_info,
		                       ps_input_info, programs, static_params, m_driver_cache, m_libraries);
	}
	LogPipelineTrace("CreatePipelineInternal done", vs_id, ps_id);
	return NovaInsertGraphics(std::move(key), std::move(cached));
}''')

# ---- caller: skip side-effect-free draws whose pipeline is still compiling ----
rd = src / 'graphics/host_gpu/renderer/renderDraw.cpp'
edit(rd, '''	auto& pipeline = m_context.GetPipelineCache().GetGraphicsPipeline(
	    std::span {state.color_info, state.color_count}, state.depth_info, vertex_stages, buffer,
	    state.ps_active ? &state.ps_input_info : nullptr, topology, primitive_restart_enable,
	    state.programs);''', '''	// Nova 0.9.56: only draws without shader side effects may be skipped while
	// their pipeline compiles in the background.
	bool nova_allow_async = NovaSync::AsyncPipelines();
	for (const auto* stage: stages) {
		if (stage->runtime->program->has_address_writes || HasShaderBufferWrites(*stage->runtime))
			nova_allow_async = false;
		for (const auto& resource: stage->runtime->program->info.images)
			if (resource.written) nova_allow_async = false;
	}
	auto* nova_pipeline = m_context.GetPipelineCache().GetGraphicsPipeline(
	    std::span {state.color_info, state.color_count}, state.depth_info, vertex_stages, buffer,
	    state.ps_active ? &state.ps_input_info : nullptr, topology, primitive_restart_enable,
	    state.programs, nova_allow_async);
	if (nova_pipeline == nullptr) {
		LogDrawPhase(draw.Name(), "SkippedPipelineCompiling");
		return;
	}
	auto& pipeline = *nova_pipeline;''')
rs = changes[rd]
if 'graphics/host_gpu/novaSync.h' not in rs:
    i = rs.index('#include')
    changes[rd] = rs[:i] + '#include "graphics/host_gpu/novaSync.h"\n' + rs[i:]

for path, text in changes.items():
    path.write_text(text)
print('NOVA_0956_ASYNC: background graphics pipeline compilation; side-effect-free draws skip while compiling')
