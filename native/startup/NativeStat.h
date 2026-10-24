// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <sys/stat.h>
#include <cerrno>

namespace NovaStartup {
// One metadata request. In particular, stat(directory) must not enumerate children.
// Call only on resolved host paths; archive paths keep the archive implementation.
template<class GuestStat>
int ReadNativeStat(const char* path, GuestStat& output) {
    struct stat host{};
    if (::stat(path, &host) != 0) return errno;
    GuestStat result{};
    result.st_mode = host.st_mode;
    result.st_size = host.st_size;
    result.st_nlink = host.st_nlink;
    result.st_blksize = host.st_blksize;
    result.st_blocks = host.st_blocks;
    result.st_atim.tv_sec = host.st_atim.tv_sec;
    result.st_atim.tv_nsec = host.st_atim.tv_nsec;
    result.st_mtim.tv_sec = host.st_mtim.tv_sec;
    result.st_mtim.tv_nsec = host.st_mtim.tv_nsec;
    result.st_ctim.tv_sec = host.st_ctim.tv_sec;
    result.st_ctim.tv_nsec = host.st_ctim.tv_nsec;
    result.st_birthtim = result.st_ctim;
    output = result;
    return 0;
}
}
