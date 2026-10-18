#include "shader_bridge.hpp"
namespace NovaAnyPS5 {
ShaderRecompiler::RecompileResult Compile(const ShaderRecompiler::RecompileRequest& request) {
    return ShaderRecompiler::Recompile(request);
}
}
