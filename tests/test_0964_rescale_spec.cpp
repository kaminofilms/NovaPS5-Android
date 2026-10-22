#include "graphics/shader/recompiler/backend/spirv/SpirvBuilder.h"
#include "native/novarescale/policy.h"
#include <cassert>
#include <map>
#include <set>

int main() {
    using Libs::Graphics::ShaderRecompiler::Spirv::Builder;
    Builder builder;
    const auto u32 = builder.Type(spv::OpTypeInt,32u,0u);
    std::set<uint32_t> ids;
    for(uint32_t i=0;i<NovaRescale::StageWords;i++)
        assert(ids.insert(builder.NovaSpecializationU32(u32,0,NovaRescale::SpecBase+i)).second);
    const auto code=builder.Build();
    std::map<uint32_t,uint32_t> decorated;
    std::set<uint32_t> definitions;
    for(size_t i=5;i<code.size();) {
        const uint32_t size=code[i]>>16, op=code[i]&0xffff;
        assert(size && i+size<=code.size());
        if(op==spv::OpDecorate && code[i+2]==spv::DecorationSpecId)
            assert(decorated.emplace(code[i+1],code[i+3]).second);
        if(op==spv::OpSpecConstant) {
            assert(size==4 && code[i+3]==0);
            assert(definitions.insert(code[i+2]).second);
        }
        i+=size;
    }
    assert(decorated.size()==NovaRescale::StageWords && definitions==ids);
    std::set<uint32_t> spec_ids;
    for(auto [id,spec]:decorated) {
        assert(ids.count(id));
        assert(spec>=NovaRescale::SpecBase && spec<NovaRescale::SpecBase+NovaRescale::StageWords);
        assert(spec_ids.insert(spec).second);
    }
}
