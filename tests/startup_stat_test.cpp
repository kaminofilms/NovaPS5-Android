#include "NativeStat.h"
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <unistd.h>
struct Timespec { int64_t tv_sec, tv_nsec; };
struct GuestStat {
    uint32_t st_dev, st_ino;
    uint16_t st_mode, st_nlink;
    uint32_t st_uid, st_gid, st_rdev;
    Timespec st_atim, st_mtim, st_ctim;
    int64_t st_size, st_blocks;
    uint32_t st_blksize, st_flags, st_gen;
    int32_t st_lspare;
    Timespec st_birthtim;
};
int main() {
    char pattern[]="/tmp/nova-stat-XXXXXX";
    const auto root=std::filesystem::path(mkdtemp(pattern));
    const auto file=root/"data";
    { std::ofstream f(file); f << "1234567"; }
    GuestStat g{};
    assert(NovaStartup::ReadNativeStat(file.c_str(),g)==0);
    assert(g.st_size==7 && S_ISREG(g.st_mode));
    struct stat native{};
    assert(::stat(file.c_str(),&native)==0);
    assert(g.st_mtim.tv_sec==native.st_mtim.tv_sec && g.st_mtim.tv_nsec==native.st_mtim.tv_nsec);
    assert(g.st_blocks==native.st_blocks);
    const auto saved=g.st_size;
    assert(NovaStartup::ReadNativeStat((root/"missing").c_str(),g)==ENOENT);
    assert(g.st_size==saved); // Failure never publishes partial metadata.
    assert(NovaStartup::ReadNativeStat((file/"child").c_str(),g)==ENOTDIR);
    std::filesystem::create_symlink(file,root/"link");
    assert(NovaStartup::ReadNativeStat((root/"link").c_str(),g)==0 && g.st_size==7);
    for(int i=0;i<1000;++i) std::ofstream(root/std::to_string(i));
    assert(NovaStartup::ReadNativeStat(root.c_str(),g)==0 && S_ISDIR(g.st_mode));
    assert(::stat(root.c_str(),&native)==0 && g.st_size==native.st_size);
    std::filesystem::remove_all(root);
}
