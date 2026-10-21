#!/usr/bin/env python3
"""0.9.56: execute the production bodies of the new paths.

1. Background pipeline worker (NovaAsyncWorker from pipelineCache.cpp): jobs run
   in order on one thread, WaitFor times out on slow jobs and succeeds on fast
   ones, Wait blocks until done, destruction drains the queue. Run also under
   ThreadSanitizer (or ASan/UBSan with SANITIZE=1).
2. Switches: NOVA_ASYNC_PIPELINES, NOVA_ASYNC_WAIT_US, readback default relaxed.
3. Structure of GetGraphicsPipeline / ExecutePreparedDraw: only side-effect-free
   draws may be skipped, the skip returns before render targets are acquired,
   every CreatePipelineInternal call is serialized, the worker joins first in
   the destructor.
4. Raster scale: cleared attachments skip the down-copy; counter is reported.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(sys.argv[1]); src = root / 'src'
SAN = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('SANITIZE') == '1' else []


def between(s, a, b):
    i = s.index(a); return s[i:s.index(b, i)]


def build(tmp, name, code, extra=()):
    p = Path(tmp) / (name + '.cpp'); p.write_text(code); out = Path(tmp) / name
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    *SAN, *extra, '-I' + str(src), str(p), '-o', str(out), '-pthread'], check=True)
    return out


def run(binary, *args, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith('NOVA_')}
    e.update(env)
    subprocess.run([str(binary), *args], env=e, check=True, timeout=60)


pc = (src / 'graphics/host_gpu/renderer/pipeline/pipelineCache.cpp').read_text()
rd = (src / 'graphics/host_gpu/renderer/renderDraw.cpp').read_text()
ctx = (src / 'graphics/host_gpu/renderer/context.cpp').read_text()
img = (src / 'graphics/host_gpu/renderer/image/image.cpp').read_text()

# ---- 3. structure ----
get = between(pc, 'PipelineCache::Pipeline* PipelineCache::GetGraphicsPipeline(', '\nPipelineCache::Pipeline&\nPipelineCache::GetComputePipeline(')
assert get.index('m_graphics_pipelines.find(key)') < get.index('m_nova_pending.find(key)') < get.index('const bool nova_async =')
assert 'allow_async && m_nova_worker && !rect_list && vertex_info.size() == 1' in get
assert get.count('return nullptr;') == 2, 'only the two async paths may return nullptr'
assert get.count('if (allow_async) {') == 1 and 'm_nova_worker->Wait(*job);' in get, 'non-skippable draws wait'
assert 'job->vertex_info[0].stage.program   = &job->compiled[0];' in get and 'job->pixel_info.stage.program   = &job->compiled[3];' in get
assert get.count('std::lock_guard nova_lock(m_nova_compile_mutex);') == 1
assert pc.count('CreatePipelineInternal(m_graphics, ') == 3  # sync graphics, worker graphics, compute
worker_fn = between(pc, 'm_nova_worker = std::make_unique<NovaAsyncWorker>(', '});')
assert 'std::lock_guard lock(m_nova_compile_mutex);' in worker_fn
dtor = between(pc, 'PipelineCache::~PipelineCache() {', '\nvoid PipelineCache::InitializeDriverCache()')
assert dtor.index('m_nova_worker.reset();') < dtor.index('Save();') < dtor.index('destroy(m_graphics_pipelines);')
draw = between(rd, 'void RenderExecutor::ExecutePreparedDraw(', '\nvoid RenderExecutor::DrawIndex(')
assert draw.index('bool nova_allow_async = NovaSync::AsyncPipelines();') < draw.index('GetGraphicsPipeline(')
gate = between(draw, 'bool nova_allow_async', 'auto* nova_pipeline')
assert 'has_address_writes' in gate and 'HasShaderBufferWrites' in gate and 'resource.written' in gate
skip = draw.index('if (nova_pipeline == nullptr) {')
assert skip < draw.index('AcquireRenderTargets(') < draw.index('BindPipeline(')

# ---- 4. raster ----
assert 'Handle(),!attachment.is_clear)' in ctx
assert 'Handle(),!(depth_stencil.depth_clear && !depth_stencil.has_stencil))' in ctx
begin = between(img, 'vk::ImageView Image::BeginRasterScale(', '\nvoid Image::EndRasterScale(')
assert begin.index('if(!load){') < begin.index('RasterBlit(')

with tempfile.TemporaryDirectory() as tmp:
    # ---- 1. worker ----
    worker = between(pc, 'struct PipelineCache::NovaAsyncWorker {', '\nvoid PipelineCache::NovaAsyncStats(')
    code = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
struct PipelineCache {
  struct NovaAsyncJob { std::atomic<bool> done{false}; int id=0; int sleep_ms=0; };
  struct NovaAsyncWorker;
};
''' + worker + r'''
using Job = PipelineCache::NovaAsyncJob;
int main() {
  std::vector<int> order; std::mutex m; std::atomic<int> running{0}; std::atomic<int> overlap{0};
  auto compile = [&](Job& j) {
    if (running.fetch_add(1) != 0) overlap.fetch_add(1);
    std::this_thread::sleep_for(std::chrono::milliseconds(j.sleep_ms));
    { std::lock_guard l(m); order.push_back(j.id); }
    running.fetch_sub(1);
  };
  std::vector<std::shared_ptr<Job>> jobs;
  {
    PipelineCache::NovaAsyncWorker w(compile);
    auto fast = std::make_shared<Job>(); fast->id = 0; fast->sleep_ms = 0;
    w.Post(fast);
    assert(w.WaitFor(*fast, std::chrono::milliseconds(2000)));
    auto slow = std::make_shared<Job>(); slow->id = 1; slow->sleep_ms = 150;
    w.Post(slow);
    assert(!w.WaitFor(*slow, std::chrono::microseconds(2000)));   // draw would be skipped
    w.Wait(*slow); assert(slow->done.load());                     // non-skippable draw waits
    for (int i = 2; i < 40; ++i) { auto j = std::make_shared<Job>(); j->id = i; j->sleep_ms = i % 3; jobs.push_back(j); w.Post(j); }
  } // destructor drains the queue and joins
  for (auto& j : jobs) assert(j->done.load());
  assert(order.size() == 40 && overlap.load() == 0);
  for (int i = 0; i < 40; ++i) assert(order[i] == i);
  // Destroying an idle worker returns.
  { PipelineCache::NovaAsyncWorker idle(compile); }
  std::puts("NOVA_0956_WORKER: PASS");
}
'''
    wb = build(tmp, 'worker', code)
    run(wb)
    if os.getenv('SANITIZE') != '1':
        tsan = build(tmp, 'worker_tsan', code, ['-fsanitize=thread'])
        e = dict(os.environ, TSAN_OPTIONS='halt_on_error=1')
        # Some CI kernels use high mmap ASLR entropy that TSan cannot map; retry without ASLR.
        r = subprocess.run([str(tsan)], env=e, capture_output=True, text=True, timeout=120)
        if r.returncode != 0 and 'unexpected memory mapping' in r.stderr:
            r = subprocess.run(['setarch', os.uname().machine, '-R', str(tsan)], env=e,
                               capture_output=True, text=True, timeout=120)
        if r.returncode != 0 and 'unexpected memory mapping' in r.stderr:
            print('NOVA_0956_WORKER_TSAN: skipped (kernel memory layout unsupported by TSan)')
        else:
            sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
            assert r.returncode == 0, 'ThreadSanitizer reported a problem'

    # ---- 2. switches ----
    sw = build(tmp, 'switches', r'''
#include "graphics/host_gpu/novaSync.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
int main(int, char** argv) {
  assert(NovaSync::AsyncPipelines() == (std::strcmp(argv[1], "on") == 0));
  assert(NovaSync::AsyncWaitUs() == std::strtoul(argv[2], nullptr, 10));
  const char* rb = argv[3];
  assert(NovaSync::ReadbackOff() == (std::strcmp(rb, "off") == 0));
  assert(NovaSync::PreciseReadbacks() == (std::strcmp(rb, "precise") == 0));
  std::puts("NOVA_0956_SWITCHES: PASS");
}''')
    run(sw, 'on', '2000', 'relaxed')
    run(sw, 'off', '2000', 'relaxed', NOVA_ASYNC_PIPELINES='0')
    run(sw, 'on', '0', 'relaxed', NOVA_ASYNC_WAIT_US='-5')
    run(sw, 'on', '50000', 'relaxed', NOVA_ASYNC_WAIT_US='900000')
    run(sw, 'on', '2000', 'relaxed', NOVA_READBACK_MODE='relaxed')
    run(sw, 'on', '2000', 'off', NOVA_READBACK_MODE='off')
    run(sw, 'on', '2000', 'precise', NOVA_READBACK_MODE='precise')
    run(sw, 'on', '2000', 'precise', NOVA_LABEL_MODE='accurate', NOVA_READBACK_MODE='off')

    # ---- 4. raster counter ----
    rs = build(tmp, 'raster', r'''
#include "common/novaRasterScale.h"
#include <cassert>
#include <cstdio>
int main() {
  for (int i = 0; i < 3; ++i) NovaRaster::NoteSkippedCopy();
  assert(NovaRaster::SkippedCopies().load() == 3);
  std::puts("NOVA_0956_RASTER: PASS");
}''')
    run(rs)
print('NOVA_0956_REGRESSION: PASS')
