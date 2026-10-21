#!/usr/bin/env python3
"""0.9.57: execute the production bodies of the deferred write-fault path.

1. Upload exclusion (SynchronizeBuffer range callback, real RangeSet): bytes in
   the exact GPU dirty set are never uploaded; everything else is, in order.
2. Merge (NovaPumpDeferredWriteFaults, real RangeSet and EopLabels, fake guest
   memory): untouched bytes get the GPU value, CPU-changed bytes are kept and the
   page is marked CPU-modified, re-dirtied pages are dropped with R still dirty,
   jobs whose copy has not completed stay pending, already-downloaded ranges are
   left alone, unreadable memory is skipped.
3. Structure: the deferral runs before the synchronous download, only for fault
   writes in Relaxed mode, with a 64-byte guard band and no overlapping image;
   the completion callback touches only the job; every shortcut treats exact
   dirty bytes as GPU-modified; switch defaults.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

src = Path(sys.argv[1]) / 'src'
SAN = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []
bc = (src / 'graphics/host_gpu/renderer/cache/bufferCache.cpp').read_text()
hdr = (src / 'graphics/host_gpu/renderer/cache/bufferCache.h').read_text()


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


inc = ['-I' + str(src), '-I' + str(src.parent / '3rdparty/fmt/include')]

def build(tmp, name, code):
    # rangeSet.h only needs the EXIT macros; avoid the generated cmake_config.h.
    (Path(tmp) / 'common').mkdir(exist_ok=True)
    (Path(tmp) / 'common/assert.h').write_text('#pragma once\n#include <cstdlib>\n'
        '#define EXIT(...) std::abort()\n#define EXIT_IF(x) do { if (x) std::abort(); } while (0)\n'
        '#define EXIT_NOT_IMPLEMENTED(x) EXIT_IF(x)\n')
    p = Path(tmp) / (name + '.cpp'); p.write_text(code); out = Path(tmp) / name
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    *SAN, '-I' + tmp, *inc, str(p), '-o', str(out)], check=True)
    return out

def run(binary, *args, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith('NOVA_')}
    e.update(env)
    subprocess.run([str(binary), *args], env=e, check=True, timeout=30)


# ---- 3. structure ----
rm = between(bc, 'void BufferCache::ReadMemory(', '\nbool BufferCache::NovaDeferWriteFault(')
assert rm.index('if (is_write && NovaDeferWriteFault(vaddr, context)) {') < rm.index('DownloadBufferMemory<false>')
assert rm.index('NovaSync::ReadbackOff()') < rm.index('NovaDeferWriteFault')
defer = between(bc, 'bool BufferCache::NovaDeferWriteFault(', '\nvoid BufferCache::NovaPumpDeferredWriteFaults()')
for needle in ['!NovaSync::DeferredWriteFaults() || !context.is_fault_origin || NovaSync::PreciseReadbacks()',
               'NovaSync::ReadbackOff()', 'fault_vaddr - 64', 'fault_vaddr + 64',
               'm_gpu_modified_ranges.Intersects(guard_begin, guard_end - guard_begin)) return false;',
               'm_texture_cache.FindImageFromRange(page, TRACKER_PAGE_SIZE)) return false;',
               'if (m_nova_dwf.size() >= 256) return false;']:
    assert needle in defer, needle
assert defer.index('TryReadBacking') < defer.index('m_memory_tracker.UnmarkRegionAsGpuModified'), 'snapshot before release'
assert 'm_gpu_modified_ranges.Subtract' not in defer, 'R must stay dirty until the merge'
completion = between(defer, 'm_scheduler.DeferPriorityOperation([this, job, mapped, offset, total] {', '});')
assert 'm_gpu_modified_ranges' not in completion and 'm_memory_tracker' not in completion and 'Backing' not in completion
ob = between(bc, 'std::pair<Buffer*, uint64_t> BufferCache::ObtainBuffer(', '\nstd::pair<Buffer*, uint64_t> BufferCache::ObtainBufferForImage(')
assert '!m_gpu_modified_ranges.Intersects(vaddr, size) &&' in ob
assert 'return m_memory_tracker.IsRegionGpuModified(vaddr, size) || m_gpu_modified_ranges.Intersects(vaddr, size);' in bc
gc = between(bc, 'void BufferCache::RunGarbageCollector() {', '\nvoid BufferCache::ProcessFaultBuffer()')
assert 'm_gpu_modified_ranges.Intersects(buffer.CpuAddress(), buffer.Size());' in gc.split('if (dirty && !aggressive)')[0]

upload = between(bc, '	    [&](uint64_t address, uint64_t bytes) noexcept {\n		    // Nova 0.9.57: bytes still in the exact GPU dirty set',
                 '	    [&]() noexcept { source = UploadCopies(buffer, copies, total_size); });')
pump = between(bc, 'void BufferCache::NovaPumpDeferredWriteFaults() {', '\nBufferId BufferCache::FindBuffer(')
job = between(hdr, '	struct NovaDwfJob {', '	std::vector<std::shared_ptr<NovaDwfJob>> m_nova_dwf;')

with tempfile.TemporaryDirectory() as tmp:
    # ---- 1. upload exclusion ----
    up = build(tmp, 'upload', r'''
#include "graphics/host_gpu/rangeSet.h"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace Libs::Graphics;
struct Copy { uint64_t src, dst, size; };
struct CopyVec : std::vector<Copy> { void emplace_back(uint64_t s, uint64_t d, uint64_t n) { push_back({s, d, n}); } };
struct Buf { uint64_t base; uint64_t Offset(uint64_t a) const { return a - base; } };
int main() {
  RangeSet m_gpu_modified_ranges; Buf buffer{0x10000};
  CopyVec copies; uint64_t total_size = 0;
  auto cb =
''' + upload.replace('	    [&](uint64_t address, uint64_t bytes) noexcept {', '[&](uint64_t address, uint64_t bytes) noexcept {', 1).rstrip().rstrip(',') + r''';
  // no dirty bytes: one copy
  cb(0x11000, 0x1000); assert(copies.size()==1 && copies[0].dst==0x1000 && copies[0].size==0x1000 && total_size==0x1000);
  copies.clear(); total_size = 0;
  // two dirty islands inside the page: three uploads around them
  m_gpu_modified_ranges.Add(0x11100, 0x40); m_gpu_modified_ranges.Add(0x11800, 0x100);
  cb(0x11000, 0x1000);
  assert(copies.size()==3);
  assert(copies[0].dst==0x1000 && copies[0].size==0x100);
  assert(copies[1].dst==0x1140 && copies[1].size==0x800-0x140);
  assert(copies[2].dst==0x1900 && copies[2].size==0x700);
  assert(total_size==0x1000-0x140);
  assert(copies[1].src==0x100 && copies[2].src==0x100+0x6c0);
  copies.clear(); total_size = 0;
  // dirty covers the whole request: nothing uploaded
  m_gpu_modified_ranges.Add(0x12000, 0x1000); cb(0x12000, 0x1000); assert(copies.empty() && total_size==0);
  // dirty at the edges
  m_gpu_modified_ranges.Add(0x13000, 0x10); m_gpu_modified_ranges.Add(0x13ff0, 0x10); cb(0x13000, 0x1000);
  assert(copies.size()==1 && copies[0].dst==0x3010 && copies[0].size==0xfe0);
  std::puts("NOVA_0957_DWF_UPLOAD: PASS");
}''')
    run(up)

    # ---- 2. merge ----
    mg = build(tmp, 'merge', r'''
#include "graphics/host_gpu/rangeSet.h"
#include "graphics/host_gpu/renderer/novaEopLabels.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <vector>
using namespace Libs::Graphics;
constexpr uint64_t TRACKER_PAGE_SIZE = 4096;
std::map<uint64_t, uint8_t> g_mem; bool g_unreadable = false;
namespace Libs::LibKernel::Memory {
bool TryReadBacking(uint64_t a, void* d, uint64_t n) { if (g_unreadable) return false; auto* p=(uint8_t*)d; for(uint64_t i=0;i<n;i++) p[i]=g_mem[a+i]; return true; }
bool TryWriteBacking(uint64_t a, const void* d, uint64_t n) { auto* p=(const uint8_t*)d; for(uint64_t i=0;i<n;i++) g_mem[a+i]=p[i]; return true; }
}
struct Tracker { std::map<uint64_t,bool> gpu, cpu;
  bool IsRegionGpuModified(uint64_t a, uint64_t) { return gpu[a & ~4095ull]; }
  void MarkRegionAsCpuModified(uint64_t a, uint64_t) { cpu[a & ~4095ull] = true; } };
struct Cache {
''' + job + r'''
  std::vector<std::shared_ptr<NovaDwfJob>> m_nova_dwf;
  uint64_t m_nova_dwf_deferred = 0, m_nova_dwf_merged = 0, m_nova_dwf_conflicts = 0, m_nova_dwf_dropped = 0;
  Tracker m_memory_tracker; RangeSet m_gpu_modified_ranges; NovaRender::EopLabels m_eop_labels;
  void NovaPumpDeferredWriteFaults();
};
''' + pump.replace('void BufferCache::NovaPumpDeferredWriteFaults()', 'void Cache::NovaPumpDeferredWriteFaults()', 1) + r'''
std::shared_ptr<Cache::NovaDwfJob> Job(Cache& c, uint64_t page, std::vector<std::pair<uint64_t,uint64_t>> r, uint8_t old_v, uint8_t gpu_v, bool ready) {
  auto j = std::make_shared<Cache::NovaDwfJob>(); j->page = page; j->ranges = r;
  for (auto [b,e] : r) { c.m_gpu_modified_ranges.Add(b, e-b); for (uint64_t a=b;a<e;a++){ g_mem[a]=old_v; j->snapshot.push_back(old_v); j->gpu.push_back(gpu_v);} }
  j->ready = ready; c.m_nova_dwf.push_back(j); return j;
}
int main() {
  Cache c;
  // A: clean merge, two ranges
  Job(c, 0x20000, {{0x20100,0x20140},{0x20800,0x20808}}, 0x11, 0xAA, true);
  uint32_t v = 7; c.m_eop_labels.Record(0x20800, &v, 4, 1);
  g_mem[0x20010] = 0x55; // CPU byte outside R
  // B: CPU overwrote one byte of R after the fault
  Job(c, 0x30000, {{0x30000,0x30010}}, 0x22, 0xBB, true); g_mem[0x30004] = 0x99;
  // C: GPU re-dirtied the page
  Job(c, 0x40000, {{0x40000,0x40010}}, 0x33, 0xCC, true); c.m_memory_tracker.gpu[0x40000] = true;
  // D: copy not completed yet
  auto d = Job(c, 0x50000, {{0x50000,0x50010}}, 0x44, 0xDD, false);
  // E: range already downloaded synchronously (no longer dirty) -> untouched
  Job(c, 0x60000, {{0x60000,0x60010}}, 0x66, 0xEE, true); c.m_gpu_modified_ranges.Subtract(0x60000, 0x10); g_mem[0x60001]=0x67;
  c.NovaPumpDeferredWriteFaults();
  for (uint64_t a=0x20100;a<0x20140;a++) assert(g_mem[a]==0xAA);
  for (uint64_t a=0x20800;a<0x20808;a++) assert(g_mem[a]==0xAA);
  assert(g_mem[0x20010]==0x55);
  assert(!c.m_gpu_modified_ranges.Intersects(0x20000, 4096) && !c.m_eop_labels.Find(0x20800,4));
  assert(!c.m_memory_tracker.cpu[0x20000]);
  assert(g_mem[0x30004]==0x99 && g_mem[0x30003]==0xBB && g_mem[0x30005]==0xBB && c.m_memory_tracker.cpu[0x30000]);
  assert(!c.m_gpu_modified_ranges.Intersects(0x30000, 16));
  assert(g_mem[0x40000]==0x33 && c.m_gpu_modified_ranges.Intersects(0x40000,16));
  assert(g_mem[0x50000]==0x44 && c.m_gpu_modified_ranges.Intersects(0x50000,16));
  assert(g_mem[0x60000]==0x66 && g_mem[0x60001]==0x67 && !c.m_memory_tracker.cpu[0x60000]);
  assert(c.m_nova_dwf.size()==1 && c.m_nova_dwf[0]==d);
  assert(c.m_nova_dwf_merged==3 && c.m_nova_dwf_conflicts==1 && c.m_nova_dwf_dropped==1);
  d->ready = true; c.NovaPumpDeferredWriteFaults();
  assert(g_mem[0x50000]==0xDD && c.m_nova_dwf.empty() && !c.m_gpu_modified_ranges.Intersects(0x50000,16));
  // F: unreadable guest memory: nothing written, range released
  Job(c, 0x70000, {{0x70000,0x70004}}, 0x01, 0x02, true); g_unreadable = true; c.NovaPumpDeferredWriteFaults(); g_unreadable = false;
  assert(g_mem[0x70000]==0x01 && !c.m_gpu_modified_ranges.Intersects(0x70000,4) && c.m_nova_dwf.empty());
  c.NovaPumpDeferredWriteFaults(); // empty: no-op
  std::puts("NOVA_0957_DWF_MERGE: PASS");
}''')
    run(mg)

    # ---- switch ----
    sw = build(tmp, 'switch', r'''
#include "graphics/host_gpu/novaSync.h"
#include <cassert>
#include <cstdio>
#include <cstring>
int main(int, char** argv) { assert(NovaSync::DeferredWriteFaults() == (std::strcmp(argv[1], "on") == 0)); std::puts("NOVA_0957_DWF_SWITCH: PASS"); }''')
    run(sw, 'on', NOVA_CACHE_TITLE_ID='PPSA04703')
    run(sw, 'off', NOVA_CACHE_TITLE_ID='PPSA04703', NOVA_DEFERRED_WRITE_FAULTS='0')
    run(sw, 'off', NOVA_CACHE_TITLE_ID='PPSA15552')
    run(sw, 'off')
    run(sw, 'on', NOVA_CACHE_TITLE_ID='PPSA27841', NOVA_DEFERRED_WRITE_FAULTS='1')
print('NOVA_0957_DWF_REGRESSION: PASS')
