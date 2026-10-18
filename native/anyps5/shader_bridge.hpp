#pragma once
#include "Recompiler.hpp"
#if defined(__GNUC__)
#define NOVA_ANYPS5_API __attribute__((visibility("default")))
#else
#define NOVA_ANYPS5_API
#endif
namespace NovaAnyPS5 {
NOVA_ANYPS5_API ShaderRecompiler::RecompileResult Compile(const ShaderRecompiler::RecompileRequest& request);
}
