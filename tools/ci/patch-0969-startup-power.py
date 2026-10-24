#!/usr/bin/env python3
"""Startup metadata fix and removal of persistent GPU max-clock forcing.

Does not bypass a guest fault or claim to fix Wolverine's untraced null object.
"""
from pathlib import Path
import shutil
import sys

repo = Path(__file__).resolve().parents[2]
root = Path(sys.argv[1])
changes = {}
def replace(p, old, new):
    s = changes.get(p, p.read_text())
    if s.count(old) != 1:
        raise SystemExit(f'0969 source anchor changed: {p}: {old[:80]!r}')
    changes[p] = s.replace(old, new, 1)

p = root/'src/kernel/fileSystem.cpp'
replace(p, '#include <cstdlib>', '''#include <cstdlib>
#include <chrono>
#if defined(KYTY_ANDROID)
#include "common/startup/NativeStat.h"
#endif''')
replace(p, '\tauto real_file_name = g_mount_points->ResolvePath(path);\n\n\tconst auto info = Common::File::GetInfo(real_file_name);', '''
#if defined(KYTY_ANDROID)
    const auto nova_stat_start = std::chrono::steady_clock::now();
    static std::atomic<uint64_t> nova_stat_calls{0};
    const auto nova_stat_call = ++nova_stat_calls;
    const bool nova_stat_sample = nova_stat_call <= 8 || (nova_stat_call & (nova_stat_call-1)) == 0;
    if (nova_stat_sample)
        std::fprintf(stderr, "NOVA_STAT: begin call=%llu guest=%s\\n",
                     static_cast<unsigned long long>(nova_stat_call), path);
#endif
    auto real_file_name = g_mount_points->ResolvePath(path);
#if defined(KYTY_ANDROID)
    if (real_file_name.empty()) return KERNEL_ERROR_ENOENT;
    if (!Common::IsArchivePath(real_file_name)) {
        FileStat result{};
        const int error = NovaStartup::ReadNativeStat(real_file_name.c_str(), result);
        const auto us = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now()-nova_stat_start).count();
        static std::atomic<uint64_t> nova_stat_slow{0};
        bool slow_sample = false;
        if (us >= 50000) {
            const auto n = ++nova_stat_slow;
            slow_sample = n <= 8 || (n & (n-1)) == 0;
        }
        if (nova_stat_sample || slow_sample)
            std::fprintf(stderr, "NOVA_STAT: end call=%llu us=%lld errno=%d guest=%s host=%s\\n",
                         static_cast<unsigned long long>(nova_stat_call),
                         static_cast<long long>(us), error, path, real_file_name.c_str());
        if (error == 0) { *sb = result; return OK; }
        // Linux errno numbers differ from the guest FreeBSD ABI.
        switch (error) {
            case ENOENT: return KERNEL_ERROR_ENOENT;
            case ENOTDIR: return KERNEL_ERROR_ENOTDIR;
            case EACCES: return KERNEL_ERROR_EACCES;
            case EPERM: return KERNEL_ERROR_EPERM;
            case ELOOP: return KERNEL_ERROR_ELOOP;
            case ENAMETOOLONG: return KERNEL_ERROR_ENAMETOOLONG;
            case EFAULT: return KERNEL_ERROR_EFAULT;
            case EINTR: return KERNEL_ERROR_EINTR;
            default: return KERNEL_ERROR_EIO;
        }
    }
#endif
    const auto info = Common::File::GetInfo(real_file_name);''')

# The old detached loop reasserted a device-wide power override forever. Always
# restore normal KGSL power control; let Android govern clocks and thermals.
p = root/'src/novaAndroid.cpp'
s = p.read_text()
start = s.index('void NovaStartGpuTurbo() {')
end = s.index('\n} // namespace', start)
old = s[start:end]
replace(p, old, '''void NovaStartGpuTurbo() {
    static const int result = [] {
        const int status = NovaSetGpuTurbo(false);
        std::fprintf(stderr, "NOVA_GPU_POWER: Android-managed clocks; cleared legacy turbo override (result=%d)\\n", status);
        return status;
    }();
    (void)result;
}''')
p = root/'src/graphics/presentation/videoOut.cpp'
s = p.read_text()
old = '\t\ttotal_wait -= static_cast<int64_t>(frame_begin - sleep_begin);'
assert s.count(old) == 1, '0969 vblank pacing anchor changed'
s = s.replace(old, '''        const bool nova_frame_late = total_wait <
            static_cast<int64_t>(frame_begin - sleep_begin);
        // A delayed frame/scheduler wake must not accumulate negative sleep
        // debt and emit a burst of synthetic vblanks to catch up afterwards.
        total_wait = std::max<int64_t>(0, total_wait -
            static_cast<int64_t>(frame_begin - sleep_begin));''')
old = '\t\tif (!presented && total_wait < 0) {'
assert s.count(old) == 1, '0969 idle presentation anchor changed'
s = s.replace(old, '\t\tif (!presented && nova_frame_late) {')
changes[p] = s
for p, s in changes.items():
    p.write_text(s)
shutil.copytree(repo/'native/startup', root/'src/common/startup', dirs_exist_ok=True)
print('NOVA_0969: native metadata, stat tracing, Android-managed GPU power, bounded vblank debt; no boot bypass')
