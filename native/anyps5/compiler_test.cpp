#include "shader_bridge.hpp"
#include <array>
#include <cstdio>
#include <stdexcept>
#include <spirv/unified1/spirv.hpp>
int main(int argc, char** argv) {
    using namespace ShaderRecompiler;
    try {
        constexpr std::array<std::uint32_t, 1> code{0xbf810000u};
        RecompileRequest request{};
        request.shader = {ShaderStage::Compute, 0x10000u, code, 0, {}};
        request.context.waveSize = 32;
        request.context.compute = ShaderComputeStageInfo{{32, 1, 1}, 0, {true, false, false}, false, 1};
        request.target.vulkanVersion = 0x00403000u;
        request.target.spirvVersion = 0x00010300u;
        request.target.subgroupSize = 32;
        request.target.maxWorkgroupSize = {1024, 1024, 64};
        request.target.maxWorkgroupInvocations = 1024;
        request.target.maxWorkgroupSharedMemoryBytes = 32768;
        request.layout = {0, 0, 0, 128};
        request.useCache = false;
        const auto result = NovaAnyPS5::Compile(request);
        const auto words = result.spirv.Words();
        if (words.size() < 5 || words[0] != spv::MagicNumber)
            throw std::runtime_error("AnyPS5 did not produce SPIR-V");
        if (argc == 2) {
            auto* file = std::fopen(argv[1], "wb");
            if (!file) throw std::runtime_error("Cannot open SPIR-V output");
            const auto written = std::fwrite(words.data(), sizeof(std::uint32_t), words.size(), file);
            const auto closed = std::fclose(file);
            if (written != words.size() || closed) throw std::runtime_error("Cannot write SPIR-V output");
        }
        std::printf("Real AnyPS5 compute compilation passed: %zu SPIR-V words\n", words.size());
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
