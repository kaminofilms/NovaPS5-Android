#pragma once
#include <array>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

namespace NovaLunaTrace {
enum class Kind : unsigned { Batch, Read, Event, Submit, Execute, Complete, Count };
inline bool Enabled() {
    static const bool enabled = [] {
        const char* override = std::getenv("NOVA_LUNA_TRACE");
        if (override != nullptr) return std::strcmp(override, "1") == 0;
        const char* title = std::getenv("NOVA_CACHE_TITLE_ID");
        return title != nullptr && std::strcmp(title, "PPSA36257") == 0;
    }();
    return enabled;
}
inline std::array<std::atomic<unsigned>, static_cast<unsigned>(Kind::Count)> counts {};
inline void Print(Kind kind, const char* format, ...) {
    if (!Enabled()) return;
    const unsigned n = counts[static_cast<unsigned>(kind)].fetch_add(1, std::memory_order_relaxed);
    if (n > 128) return;
    char body[768];
    if (n == 128) {
        std::snprintf(body, sizeof(body), "trace limit reached; later records suppressed");
    } else {
        va_list args;
        va_start(args, format);
        std::vsnprintf(body, sizeof(body), format, args);
        va_end(args);
    }
    std::fprintf(stderr, "NOVA_LUNA_TRACE: t%d kind=%u seq=%u %s\n",
                 static_cast<int>(gettid()), static_cast<unsigned>(kind), n, body);
}
}
