#pragma once
#include <filesystem>
#include <fstream>
#include <cstring>
#include <type_traits>
#include <vector>
#include <string>
#include <cstdio>
#include <xxhash.h>
namespace Libs::Graphics::NovaShaderDisk {
namespace IR = ShaderRecompiler::IR;
inline constexpr size_t Limit = 16u * 1024u * 1024u;
template<class T> struct IsVector : std::false_type {};
template<class T, class A> struct IsVector<std::vector<T,A>> : std::true_type {};
template<class T> struct IsArray : std::false_type {};
template<class T, size_t N> struct IsArray<std::array<T,N>> : std::true_type {};
struct Archive {
    std::vector<uint8_t> bytes;
    size_t cursor = 0;
    bool reading = false, ok = true;
    template<class... T> void Fields(T&... values) { (Value(values), ...); }
    template<class T> void Value(T& v) {
        if (!ok) return;
        if constexpr (std::is_arithmetic_v<T> || std::is_enum_v<T>) {
            if constexpr (std::is_same_v<T,bool>) {
                uint8_t b = v ? 1 : 0; Value(b);
                if (b > 1) ok = false; else v = b != 0;
            } else if (reading) {
                if (cursor > bytes.size() || sizeof(T) > bytes.size()-cursor) { ok=false; return; }
                std::memcpy(&v, bytes.data()+cursor, sizeof(T)); cursor += sizeof(T);
            } else {
                if (bytes.size() > Limit-sizeof(T)) { ok=false; return; }
                const auto* p=reinterpret_cast<const uint8_t*>(&v); bytes.insert(bytes.end(),p,p+sizeof(T));
            }
        } else if constexpr (IsVector<T>::value || std::is_same_v<T,std::string>) {
            uint32_t n=static_cast<uint32_t>(v.size()); Value(n);
            if (!ok || n > Limit || (reading && n > bytes.size()-cursor)) {ok=false; return;}
            if (reading) v.resize(n);
            for (auto& x:v) Value(x);
        } else if constexpr (IsArray<T>::value) {
            for(auto& x:v) Value(x);
        } else if constexpr (std::is_same_v<T,IR::BufferResource>) { Fields(v.source,v.descriptor_index,v.first_use_pc,v.max_byte_extent,v.packed_stride,v.descriptor_format,v.descriptor_swizzle,v.image_alias,v.read,v.written,v.atomic,v.formatted,v.scalar,v.indirect_root,v.indirect_mapping_offset,v.indirect_search_iterations,v.indirect_resources);
        } else if constexpr (std::is_same_v<T,IR::ImageResource>) { Fields(v.source,v.descriptor_index,v.first_use_pc,v.resource_class,v.numeric_class,v.dimension,v.mip_mode,v.mip_count,v.conversion_format,v.shader_swizzle,v.read,v.written,v.atomic,v.atomic64,v.depth_compare,v.cube,v.r128,v.indirect_root,v.indirect_mapping_offset,v.indirect_search_iterations,v.indirect_resources);
        } else if constexpr (std::is_same_v<T,IR::SamplerResource>) { Fields(v.source,v.first_use_pc,v.snapshot_index,v.indirect_resources,v.force_point_filtering,v.depth_compare,v.integer_border,v.gather_lod);
        } else if constexpr (std::is_same_v<T,IR::SampledResourcePair>) { Fields(v.image,v.sampler,v.first_use_pc);
        } else if constexpr (std::is_same_v<T,IR::StageInput>) { Fields(v.kind,v.location,v.component_count,v.debug_name,v.per_vertex);
        } else if constexpr (std::is_same_v<T,IR::StageOutput>) { Fields(v.kind,v.index,v.location,v.debug_name);
        } else if constexpr (std::is_same_v<T,IR::Bindings>) { Fields(v.descriptor_counts,v.descriptor_mask,v.push_data_start_dword,v.dispatch_thread_dword,v.memory_offset_dword);
        } else if constexpr (std::is_same_v<T,IR::ShaderInfo>) { Fields(v.buffers,v.images,v.samplers,v.sampled_pairs,v.inputs,v.outputs,v.user_data_registers,v.live_buffers,v.vertex_fetch_components,v.vertex_offset_sgpr,v.instance_offset_sgpr,v.has_bitwise_xor,v.uses_dma,v.uses_swizzle,v.uses_lds,v.uses_gds,v.uses_flattened_srt,v.uses_dispatch_threads,v.bvh,v.subgroup_ballot,v.subgroup_barrier,v.subgroup_shuffle,v.subgroup_local_invocation_id,v.compute_derivatives,v.image_gather_extended,v.function_lds,v.function_scratch,v.pixel_valid_mask,v.buffer_int64_atomics,v.buffer_u8,v.buffer_u16,v.shared_int64_atomics,v.coherent_buffers,v.float64);
        } else if constexpr (std::is_same_v<T,IR::CompiledShaderInfo>) { Fields(v.stage,v.shader_hash,v.wave_size,v.user_data_base,v.user_data_count,v.scratch_dwords,v.param_export_mask,v.has_address_writes,v.info,v.bindings);
        } else if constexpr (std::is_same_v<T,IR::ResourceSpecialization::Buffer>) { Fields(v.packed_stride,v.descriptor_format,v.descriptor_swizzle,v.zero_stride_oob,v.indirect_root,v.indirect_mapping_offset,v.indirect_search_iterations);
        } else if constexpr (std::is_same_v<T,IR::ResourceSpecialization::Image>) { Fields(v.numeric_class,v.dimension,v.mip_count,v.conversion_format,v.shader_swizzle,v.indirect_root,v.indirect_mapping_offset,v.indirect_search_iterations,v.cube,v.fmask);
        } else if constexpr (std::is_same_v<T,IR::ResourceSpecialization>) { Fields(v.buffers,v.images);
        } else { static_assert(sizeof(T)==0, "Unserialized shader field type"); }
    }
};
struct Entry { IR::CompiledShaderInfo info; std::vector<uint32_t> spirv; };
inline std::filesystem::path Directory(const std::string& signature, const std::string& title) {
    if (title.empty()) return {};
    char id[32]; std::snprintf(id,sizeof(id),"%016llx",(unsigned long long)XXH3_64bits(signature.data(),signature.size()));
    return std::filesystem::path("_ShaderCache29") / title / id;
}
inline std::filesystem::path File(const std::filesystem::path& dir, const std::vector<uint8_t>& key) {
    char id[32]; std::snprintf(id,sizeof(id),"%016llx.bin",(unsigned long long)XXH3_64bits(key.data(),key.size())); return dir/id;
}
inline bool Load(const std::filesystem::path& dir, const std::vector<uint8_t>& key, Entry& result) {
    if(dir.empty() || key.empty()) return false;
    std::ifstream file(File(dir,key),std::ios::binary|std::ios::ate);
    if(!file) return false;
    auto size=file.tellg(); if(size < 16 || size > static_cast<std::streamoff>(Limit)) return false;
    Archive a; a.reading=true; a.bytes.resize(static_cast<size_t>(size)); file.seekg(0);
    if(!file.read(reinterpret_cast<char*>(a.bytes.data()),size)) return false;
    uint64_t checksum=0; std::memcpy(&checksum,a.bytes.data(),8);
    if(checksum!=XXH3_64bits(a.bytes.data()+8,a.bytes.size()-8)) return false;
    a.cursor=8; uint32_t version=0; std::vector<uint8_t> stored;
    a.Fields(version,stored); if(!a.ok || version!=1 || stored!=key) return false;
    a.Fields(result.info,result.spirv);
    return a.ok && a.cursor==a.bytes.size() && result.spirv.size()>=5 && result.spirv[0]==0x07230203u;
}
inline void Store(const std::filesystem::path& dir, const std::vector<uint8_t>& key, Entry& entry) {
    if(dir.empty() || key.empty()) return;
    Archive a; uint64_t checksum=0; uint32_t version=1; auto k=key;
    a.Fields(checksum,version,k,entry.info,entry.spirv); if(!a.ok) return;
    checksum=XXH3_64bits(a.bytes.data()+8,a.bytes.size()-8); std::memcpy(a.bytes.data(),&checksum,8);
    std::error_code ec; std::filesystem::create_directories(dir,ec); if(ec) return;
    // Bound persistent cache growth. Refuse new entries once the title budget is reached.
    static uint32_t stores=0; static bool full=false;
    if((stores++%64u)==0) {
        uintmax_t total=0; for(auto it=std::filesystem::directory_iterator(dir,ec); !ec && it!=std::filesystem::directory_iterator(); it.increment(ec)) {
            total+=it->file_size(ec); if(ec) break;
        }
        full=total>256u*1024u*1024u;
    }
    if(full) return;
    auto path=File(dir,key); auto temp=path; temp += ".tmp";
    {std::ofstream f(temp,std::ios::binary|std::ios::trunc); if(!f.write(reinterpret_cast<const char*>(a.bytes.data()),a.bytes.size())) return; f.flush(); if(!f) return;}
    std::filesystem::rename(temp,path,ec);
}
}
