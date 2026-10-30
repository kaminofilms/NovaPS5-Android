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
#include <string>
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

// Nova 0999: what the slowest pipelines' translated shaders contain. Each SPIR-V module created
// while profiling is summarized (instruction mix, memory accesses by kind, loops); pipelines map
// to their modules, and the report prints a NOVA_GPU_SHADER line under each top pipeline. With
// NOVA_SHADER_EXPORT_DIR set, the top pipelines' SPIR-V is also written there once per shader.
struct ShaderSummary {
	std::string           stage;
	uint64_t              hash = 0;
	uint32_t              words = 0, instructions = 0, functions = 0, calls = 0, loops = 0, branches = 0;
	uint32_t              samples = 0, fetches = 0, gathers = 0, image_reads = 0, image_writes = 0;
	uint32_t              loads_bda = 0, loads_ssbo = 0, loads_ubo = 0, loads_push = 0, loads_local = 0, loads_other = 0;
	uint32_t              stores_bda = 0, stores_ssbo = 0, atomics = 0, discards = 0, ptr_converts = 0;
	std::vector<uint32_t> spirv;  // kept only while under the export budget
};

inline ShaderSummary SummarizeSpirv(const uint32_t* words, size_t count) {
	ShaderSummary s;
	s.words = static_cast<uint32_t>(count);
	if (count < 5 || words[0] != 0x07230203u) return s;
	std::unordered_map<uint32_t, uint32_t> pointer_class;  // pointer type id -> storage class
	std::unordered_map<uint32_t, uint32_t> value_type;     // pointer value id -> its type id
	auto storage = [&](uint32_t pointer) -> int64_t {
		const auto type = value_type.find(pointer);
		if (type == value_type.end()) return -1;
		const auto cls = pointer_class.find(type->second);
		return cls == pointer_class.end() ? -1 : int64_t(cls->second);
	};
	for (size_t i = 5; i < count;) {
		const uint32_t length = words[i] >> 16u, op = words[i] & 0xffffu;
		if (length == 0 || i + length > count) break;
		const uint32_t* w = words + i;
		++s.instructions;
		switch (op) {
			case 32: if (length >= 4) pointer_class[w[1]] = w[2]; break;                       // OpTypePointer
			case 39: if (length >= 4) pointer_class[w[1]] = w[2]; break;                       // OpTypeForwardPointer
			case 59: if (length >= 4) value_type[w[2]] = w[1]; break;                          // OpVariable
			case 65: case 66: case 67: case 70:                                                // OpAccessChain variants
				if (length >= 4) value_type[w[2]] = w[1];
				break;
			case 120: if (length >= 4) value_type[w[2]] = w[1]; ++s.ptr_converts; break;       // OpConvertUToPtr
			case 124: if (length >= 4) value_type[w[2]] = w[1]; break;                         // OpBitcast (may yield a pointer)
			case 54: ++s.functions; break;                                                     // OpFunction
			case 57: ++s.calls; break;                                                         // OpFunctionCall
			case 246: ++s.loops; break;                                                        // OpLoopMerge
			case 250: ++s.branches; break;                                                     // OpBranchConditional
			case 87: case 88: case 89: case 90: case 91: case 92: case 93: case 94: ++s.samples; break;
			case 95: ++s.fetches; break;
			case 96: case 97: ++s.gathers; break;
			case 98: ++s.image_reads; break;
			case 99: ++s.image_writes; break;
			case 252: case 5380: ++s.discards; break;                                          // OpKill / demote
			case 61:                                                                           // OpLoad
				if (length >= 4) {
					value_type[w[2]] = w[1];  // a loaded value may itself be a pointer
					switch (storage(w[3])) {
						case 5349: ++s.loads_bda; break;   // PhysicalStorageBuffer
						case 12: ++s.loads_ssbo; break;    // StorageBuffer
						case 2: ++s.loads_ubo; break;      // Uniform
						case 9: ++s.loads_push; break;     // PushConstant
						case 6: case 7: ++s.loads_local; break;
						default: ++s.loads_other; break;
					}
				}
				break;
			case 62:                                                                           // OpStore
				if (length >= 3) {
					const auto cls = storage(w[1]);
					if (cls == 5349) ++s.stores_bda; else if (cls == 12) ++s.stores_ssbo;
				}
				break;
			default:
				if (op >= 227 && op <= 242) ++s.atomics;                                        // OpAtomic*
				break;
		}
		i += length;
	}
	return s;
}

class Shaders {
public:
	static Shaders& Get() { static Shaders shaders; return shaders; }

	void NoteModule(uint64_t module, const char* stage, uint64_t hash, const uint32_t* words, size_t count) {
		if (!Enabled() || module == 0) return;
		auto summary  = SummarizeSpirv(words, count);
		summary.stage = stage ? stage : "?";
		summary.hash  = hash;
		std::lock_guard lock(m_mutex);
		if (m_kept_bytes + count * 4 <= kKeepBytes) {
			summary.spirv.assign(words, words + count);
			m_kept_bytes += count * 4;
		}
		m_modules[module] = std::move(summary);
	}
	void NotePipeline(uint64_t pipeline, const uint64_t* modules, size_t count) {
		if (!Enabled() || pipeline == 0) return;
		std::lock_guard lock(m_mutex);
		m_pipelines[pipeline].assign(modules, modules + count);
	}
	// One line per module of the pipeline; exports SPIR-V once per shader for the top ranks.
	void Report(size_t rank, uint64_t pipeline, bool export_spirv) {
		std::lock_guard lock(m_mutex);
		const auto found = m_pipelines.find(pipeline);
		if (found == m_pipelines.end()) {
			if (pipeline != 0) std::fprintf(stderr, "NOVA_GPU_SHADER: rank=%zu pipeline=0x%llx modules=unknown\n", rank, (unsigned long long)pipeline);
			return;
		}
		for (const auto module: found->second) {
			const auto it = m_modules.find(module);
			if (it == m_modules.end()) continue;
			const auto& s = it->second;
			std::fprintf(stderr,
			             "NOVA_GPU_SHADER: rank=%zu pipeline=0x%llx stage=%s hash=%016llx words=%u instrs=%u funcs=%u calls=%u loops=%u branches=%u "
			             "samples=%u fetches=%u gathers=%u image_reads=%u image_writes=%u loads(bda=%u ssbo=%u ubo=%u push=%u local=%u other=%u) "
			             "stores(bda=%u ssbo=%u) atomics=%u discards=%u ptr_converts=%u\n",
			             rank, (unsigned long long)pipeline, s.stage.c_str(), (unsigned long long)s.hash, s.words, s.instructions, s.functions,
			             s.calls, s.loops, s.branches, s.samples, s.fetches, s.gathers, s.image_reads, s.image_writes, s.loads_bda, s.loads_ssbo,
			             s.loads_ubo, s.loads_push, s.loads_local, s.loads_other, s.stores_bda, s.stores_ssbo, s.atomics, s.discards, s.ptr_converts);
			if (export_spirv) Export(s);
		}
	}

private:
	static constexpr size_t kKeepBytes = size_t {48} << 20;

	void Export(const ShaderSummary& s) {
		static const char* dir = std::getenv("NOVA_SHADER_EXPORT_DIR");
		if (dir == nullptr || dir[0] == 0 || s.spirv.empty()) return;
		const std::string key = s.stage + std::to_string(s.hash) + "_" + std::to_string(s.words);
		if (!m_exported.emplace(key, true).second) return;
		const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
		char path[512];
		std::snprintf(path, sizeof(path), "%s/%s_%s_%016llx_%u.spv", dir, title ? title : "game", s.stage.c_str(),
		              (unsigned long long)s.hash, s.words);
		if (FILE* file = std::fopen(path, "wb")) {
			const bool ok = std::fwrite(s.spirv.data(), 4, s.spirv.size(), file) == s.spirv.size();
			std::fclose(file);
			std::fprintf(stderr, "NOVA_GPU_SHADER_EXPORT: %s %s\n", ok ? "wrote" : "short write", path);
		} else {
			std::fprintf(stderr, "NOVA_GPU_SHADER_EXPORT: cannot open %s\n", path);
		}
	}

	std::mutex                                           m_mutex;
	std::unordered_map<uint64_t, ShaderSummary>          m_modules;
	std::unordered_map<uint64_t, std::vector<uint64_t>>  m_pipelines;
	std::unordered_map<std::string, bool>                m_exported;
	size_t                                               m_kept_bytes = 0;
};

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
			if (rank < 6) Shaders::Get().Report(rank + 1, key.pipeline, rank < 4);
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
