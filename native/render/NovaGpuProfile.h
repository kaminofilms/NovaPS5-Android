// Nova 0992: sampled per-draw / per-dispatch GPU timing (NOVA_GPU_DRAW_PROFILE=1).
//
// Wonder Boy gameplay costs ~42 ms of GPU time per frame on Adreno 840 regardless of Turnip's
// sysmem mode or the internal-resolution setting, so the cost is neither render-pass restarts
// nor plainly pixel-bound. This finds which GPU work it is: for one second out of every ten,
// each draw/dispatch recorded by the guest renderer is bracketed by two BOTTOM_OF_PIPE
// timestamps; results are read back with availability once the query chunk is reused (many
// command buffers later, never waiting on the GPU) and reported by pipeline:
//
//   NOVA_GPU_DRAWS: window_s=10.0 sampled=2100 unready=0 measured_ms=812.4 frames~=24
//   NOVA_GPU_DRAW: rank=1 kind=draw pipeline=0x... calls=48 gpu_ms=210.3 avg_us=4381 max_us=5120
//                  target=1920x1080x3 last_count=3x1
//
// Timing changes nothing the GPU does except adding timestamps (which drain the pipe between
// sampled draws, so sampled seconds run slower). Sysmem rendering (Turnip "sysmem") gives the
// most precise per-draw numbers; in GMEM mode in-pass timestamps include tile replay.
#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <vulkan/vulkan.h>

namespace NovaGpuProfile {

enum class Kind : uint8_t { Draw, Dispatch, DispatchIndirect, Tiler, Blit, Fault };

inline const char* KindName(Kind kind) {
	switch (kind) {
		case Kind::Draw: return "draw";
		case Kind::Dispatch: return "dispatch";
		case Kind::DispatchIndirect: return "dispatch_indirect";
		case Kind::Tiler: return "tiler";
		case Kind::Blit: return "blit";
		case Kind::Fault: return "fault";
	}
	return "?";
}

struct Meta {
	Kind     kind     = Kind::Draw;
	uint64_t pipeline = 0;
	uint32_t width = 0, height = 0, targets = 0;  // render size (draws) or groups x/y (dispatch)
	uint32_t count = 0, instances = 0;            // vertices/indices x instances, or groups z
};

inline bool Enabled() {
	static const bool enabled = [] {
		const char* value = std::getenv("NOVA_GPU_DRAW_PROFILE");
		return value != nullptr && value[0] == '1';
	}();
	return enabled;
}

class Profiler {
public:
	static Profiler& Get() {
		static Profiler profiler;
		return profiler;
	}

	// At command-buffer begin (outside any render pass): collect the chunk being reused and,
	// during a sampling second, reset it and attach it to this command buffer.
	void BeginCommandBuffer(VkDevice device, VkPhysicalDeviceLimits const& limits, VkCommandBuffer command,
	                        PFN_vkCreateQueryPool create, PFN_vkGetQueryPoolResults results, PFN_vkCmdResetQueryPool reset,
	                        PFN_vkCmdWriteTimestamp write) {
		if (!Enabled()) return;
		std::lock_guard lock(m_mutex);
		m_write = write;
		if (m_failed) return;
		if (m_pool == VK_NULL_HANDLE) {
			if (!limits.timestampComputeAndGraphics || limits.timestampPeriod <= 0.0f || create == nullptr) {
				m_failed = true;
				std::fprintf(stderr, "NOVA_GPU_DRAWS: unavailable (no graphics timestamps)\n");
				return;
			}
			VkQueryPoolCreateInfo info {};
			info.sType      = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO;
			info.queryType  = VK_QUERY_TYPE_TIMESTAMP;
			info.queryCount = kChunks * kQueriesPerChunk;
			if (create(device, &info, nullptr, &m_pool) != VK_SUCCESS) {
				m_pool   = VK_NULL_HANDLE;
				m_failed = true;
				std::fprintf(stderr, "NOVA_GPU_DRAWS: unavailable (query pool)\n");
				return;
			}
			m_device        = device;
			m_ns_per_tick   = limits.timestampPeriod;
			m_valid_mask    = ~uint64_t {0};
			m_window_start  = Clock::now();
		}
		m_active.erase(command);
		const auto now = Clock::now();
		const auto into_window = std::chrono::duration_cast<std::chrono::milliseconds>(now - m_window_start).count();
		const bool sampling = into_window >= kQuietMs && into_window < kQuietMs + kSampleMs;
		Report(now, results);
		if (!sampling) return;
		auto& chunk = m_chunks[m_next];
		Collect(chunk, m_next, results);
		chunk.used  = 0;
		chunk.metas.clear();
		reset(command, m_pool, m_next * kQueriesPerChunk, kQueriesPerChunk);
		m_active[command] = m_next;
		m_next            = (m_next + 1) % kChunks;
	}

	// Returns a slot (>= 0) when this draw is sampled; Before writes the opening timestamp.
	int Before(VkCommandBuffer command) {
		if (!Enabled()) return -1;
		std::lock_guard lock(m_mutex);
		const auto found = m_active.find(command);
		if (found == m_active.end() || m_write == nullptr) return -1;
		auto& chunk = m_chunks[found->second];
		if (chunk.used + 2 > kQueriesPerChunk) return -1;
		const uint32_t query = found->second * kQueriesPerChunk + chunk.used;
		m_write(command, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, m_pool, query);
		chunk.used += 2;
		chunk.metas.push_back({});
		return static_cast<int>(query);
	}

	void After(VkCommandBuffer command, int slot, const Meta& meta) {
		if (slot < 0) return;
		std::lock_guard lock(m_mutex);
		const auto chunk_index = static_cast<uint32_t>(slot) / kQueriesPerChunk;
		auto&      chunk       = m_chunks[chunk_index];
		const auto local       = (static_cast<uint32_t>(slot) % kQueriesPerChunk) / 2;
		if (local < chunk.metas.size()) chunk.metas[local] = meta;
		m_write(command, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, m_pool, static_cast<uint32_t>(slot) + 1);
	}

private:
	using Clock = std::chrono::steady_clock;
	static constexpr uint32_t kChunks          = 128;
	static constexpr uint32_t kQueriesPerChunk = 1024;  // 512 sampled draws per command buffer
	static constexpr int64_t  kQuietMs         = 9000;  // then sample for kSampleMs
	static constexpr int64_t  kSampleMs        = 1000;

	struct Chunk {
		uint32_t          used = 0;
		std::vector<Meta> metas;
	};
	struct Key {
		uint64_t pipeline;
		Kind     kind;
		bool     operator==(const Key& other) const { return pipeline == other.pipeline && kind == other.kind; }
	};
	struct KeyHash {
		size_t operator()(const Key& key) const { return std::hash<uint64_t> {}(key.pipeline * 8 + uint64_t(key.kind)); }
	};
	struct Stat {
		uint64_t calls = 0, ticks = 0, max_ticks = 0;
		Meta     last {};
	};

	void Collect(Chunk& chunk, uint32_t index, PFN_vkGetQueryPoolResults results) {
		if (chunk.used == 0 || results == nullptr) return;
		std::vector<uint64_t> data(size_t(chunk.used) * 2);
		results(m_device, m_pool, index * kQueriesPerChunk, chunk.used, data.size() * sizeof(uint64_t), data.data(),
		        2 * sizeof(uint64_t), VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT);
		for (uint32_t i = 0; i + 1 < chunk.used; i += 2) {
			const auto& meta  = chunk.metas[i / 2];
			const auto  begin = data[size_t(i) * 2], begin_ok = data[size_t(i) * 2 + 1];
			const auto  end = data[size_t(i + 1) * 2], end_ok = data[size_t(i + 1) * 2 + 1];
			if (!begin_ok || !end_ok || end < begin) {
				++m_unready;
				continue;
			}
			auto& stat = m_stats[Key {meta.pipeline, meta.kind}];
			const auto ticks = (end - begin) & m_valid_mask;
			++stat.calls;
			stat.ticks += ticks;
			stat.max_ticks = std::max(stat.max_ticks, ticks);
			stat.last      = meta;
			++m_sampled;
			m_measured_ticks += ticks;
		}
		chunk.used = 0;
		chunk.metas.clear();
	}

	void Report(Clock::time_point now, PFN_vkGetQueryPoolResults results) {
		const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - m_window_start).count();
		if (elapsed < kQuietMs + kSampleMs + 2000) return;  // let the sampled chunks finish on the GPU
		for (uint32_t i = 0; i < kChunks; ++i) Collect(m_chunks[i], i, results);
		m_active.clear();
		std::vector<std::pair<Key, Stat>> sorted(m_stats.begin(), m_stats.end());
		std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.second.ticks > b.second.ticks; });
		const double ms = double(m_measured_ticks) * m_ns_per_tick / 1e6;
		std::fprintf(stderr, "NOVA_GPU_DRAWS: window_s=%.1f sampled=%llu unready=%llu measured_ms=%.1f pipelines=%zu\n", elapsed / 1000.0,
		             (unsigned long long)m_sampled, (unsigned long long)m_unready, ms, sorted.size());
		for (size_t rank = 0; rank < sorted.size() && rank < 15; ++rank) {
			const auto& [key, stat] = sorted[rank];
			std::fprintf(stderr,
			             "NOVA_GPU_DRAW: rank=%zu kind=%s pipeline=0x%llx calls=%llu gpu_ms=%.2f avg_us=%.0f max_us=%.0f size=%ux%ux%u last_count=%ux%u\n",
			             rank + 1, KindName(key.kind), (unsigned long long)key.pipeline, (unsigned long long)stat.calls,
			             double(stat.ticks) * m_ns_per_tick / 1e6, double(stat.ticks) * m_ns_per_tick / 1e3 / double(stat.calls),
			             double(stat.max_ticks) * m_ns_per_tick / 1e3, stat.last.width, stat.last.height, stat.last.targets,
			             stat.last.count, stat.last.instances);
		}
		m_stats.clear();
		m_sampled = m_unready = m_measured_ticks = 0;
		m_window_start = now;
	}

	std::mutex                                 m_mutex;
	VkDevice                                   m_device = VK_NULL_HANDLE;
	VkQueryPool                                m_pool   = VK_NULL_HANDLE;
	PFN_vkCmdWriteTimestamp                    m_write  = nullptr;
	bool                                       m_failed = false;
	double                                     m_ns_per_tick = 1.0;
	uint64_t                                   m_valid_mask  = ~uint64_t {0};
	std::array<Chunk, kChunks>                 m_chunks {};
	uint32_t                                   m_next = 0;
	std::unordered_map<VkCommandBuffer, uint32_t> m_active;
	std::unordered_map<Key, Stat, KeyHash>     m_stats;
	uint64_t                                   m_sampled = 0, m_unready = 0, m_measured_ticks = 0;
	Clock::time_point                          m_window_start = Clock::now();
};

// RAII bracket used at each draw/dispatch site.
class Scope {
public:
	Scope(VkCommandBuffer command, const Meta& meta) : m_command(command), m_meta(meta), m_slot(Profiler::Get().Before(command)) {}
	~Scope() { Profiler::Get().After(m_command, m_slot, m_meta); }
	Scope(const Scope&)            = delete;
	Scope& operator=(const Scope&) = delete;

private:
	VkCommandBuffer m_command;
	Meta            m_meta;
	int             m_slot;
};

} // namespace NovaGpuProfile
