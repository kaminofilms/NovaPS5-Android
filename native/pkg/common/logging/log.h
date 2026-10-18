#pragma once
#include <cstdio>
// Installer-only logging adapter. No emulator/runtime subsystem dependency.
#define LOGF(...) do { std::fprintf(stderr, "NOVA_PKG: "); std::fprintf(stderr, __VA_ARGS__); std::fputc('\n', stderr); } while (false)
