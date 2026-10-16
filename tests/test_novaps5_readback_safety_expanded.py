#!/usr/bin/env python3
"""Offline source-contract checks for Kyty 0.9.36; not a GPU integration test."""
from pathlib import Path
import unittest
import sys
import os
import subprocess
import tempfile
ROOT=Path(sys.argv.pop(1))/'src/graphics/host_gpu/renderer'
BUF=(ROOT/'cache/bufferCache.cpp').read_text()
CTX=(ROOT/'renderContext.cpp').read_text()
STREAM=(ROOT/'cache/streamBuffer.cpp').read_text()
SCHED=(ROOT/'commandScheduler.cpp').read_text()

def intersects(addr, copies, buffer_address):
    # Vulkan BufferCopy srcOffset is relative to the buffer's guest base.
    return any(buffer_address+c.src <= addr < buffer_address+c.src+c.size for c in copies)

class Copy:
    def __init__(self, src, size): self.src,self.size=src,size

class SafetyContracts(unittest.TestCase):
    def test_zero_copy_does_not_wait(self):
        method=BUF.split('bool BufferCache::DownloadBufferMemory(',1)[1].split('BufferCache::BufferCache(',1)[0]
        self.assertLess(method.index('if (copies.empty())'), method.index('m_scheduler.Wait(tick)'))
    def test_sync_publish_follows_wait(self):
        method=BUF.split('if constexpr (async) {',1)[1].split('return true;',1)[0]
        self.assertLess(method.index('m_scheduler.Wait(tick)'),method.index('m_scheduler.WaitPriorityOperations(tick)'))
        self.assertLess(method.index('m_scheduler.WaitPriorityOperations(tick)'),method.index('publish();'))
    def test_async_callback_owns_temporary_buffer(self):
        self.assertIn('owner = std::move(temporary)',BUF)
        self.assertIn('m_scheduler.DeferPriorityOperation(std::move(publish), telemetry)',BUF)
    def test_fault_width_not_assumed(self):
        self.assertIn('constexpr uint64_t fault_size = 1;',CTX)
        self.assertIn('PageFaultAccess::Write',CTX)
    def test_range_telemetry_uses_source_offsets_not_staging_offsets(self):
        base=0x10000
        copies=[Copy(0x100,16),Copy(0x300,4)]
        self.assertTrue(intersects(base+0x108,copies,base))
        self.assertFalse(intersects(base+0x200,copies,base))
        self.assertFalse(intersects(base+0x110,copies,base))
        self.assertTrue(intersects(base+0x303,copies,base))
    def test_overlap_not_claimed_as_safe_write(self):
        base=0x10000
        dirty=[Copy(0x100,16)]
        self.assertFalse(intersects(base+0x200,dirty,base))
        # Address-only disjointness cannot prove instruction-wide disjointness.
        self.assertTrue(intersects(base+0x100,dirty,base))

    def test_shared_allocator_waits_for_gpu_and_publication_before_reuse(self):
        method=STREAM.split('bool StreamBuffer::WaitPendingOperations(',1)[1]
        self.assertIn('Scheduler().Wait(watch.tick)',method)
        self.assertIn('Usage() == MemoryUsage::Download',method)
        self.assertIn('Scheduler().WaitPriorityOperations(watch.tick)',method)
        self.assertLess(method.index('Scheduler().WaitPriorityOperations(watch.tick)'),method.index('wait_bound = watch.upper_bound'))
    def test_shared_allocator_commits_current_tick_watch(self):
        method=STREAM.split('void StreamBuffer::Commit()',1)[1].split('uint64_t StreamBuffer::Copy(',1)[0]
        self.assertIn('Scheduler().CurrentTick()',method)
        self.assertIn('watch.upper_bound = m_offset',method)
        self.assertIn('watch.tick        = tick',method)
    def test_deferred_publication_waits_for_gpu_tick(self):
        method=SCHED.split('void CommandScheduler::PriorityOperationsThread(',1)[1].split('void CommandScheduler::DrainPriorityOperations(',1)[0]
        self.assertLess(method.index('m_master.Wait(operation.tick)'),method.index('RunOperation(std::move(operation.callback))'))
    def test_priority_wait_checks_queued_and_active_callbacks(self):
        method=SCHED.split('void CommandScheduler::WaitPriorityOperations(',1)[1].split('void CommandScheduler::RunOperation(',1)[0]
        self.assertIn('m_priority_active_tick <= tick',method)
        self.assertIn('m_priority_operations.front().tick <= tick',method)
    def test_sync_readback_waits_for_earlier_priority_publications(self):
        method=BUF.split('if constexpr (async) {',1)[1].split('return true;',1)[0]
        self.assertLess(method.index('m_scheduler.WaitPriorityOperations(tick)'),method.index('publish();'))

    def test_explicit_context_reaches_gpu_callback(self):
        self.assertIn('[this, vaddr, size, context] { ReadMemory(vaddr, size, true, context); }', BUF)
        self.assertIn('[this, vaddr, size, is_write, context]', BUF)
        self.assertIn('DownloadBufferMemory<false>(buffer, vaddr, size, context)', BUF)
        kernel=(ROOT.parents[2]/'kernel/memory.cpp').read_text()
        self.assertIn('Graphics::BufferCache::ReadbackCaller::Other', kernel)
        header=(ROOT/'cache/bufferCache.h').read_text()
        self.assertNotIn('bool is_write = false', header)

    def test_page_promotion_uses_actual_callback(self):
        self.assertIn('classification.Tracker(vaddr, size, address, bytes)',BUF)
        self.assertNotIn('size > copied_bytes',BUF)
        self.assertLess(BUF.index('if (copies.empty())'),BUF.index('classification.Copy('))

    def test_no_new_waits_or_gpu_commands(self):
        baseline=Path(__file__).with_name('readback_wait_contract.txt').read_text().splitlines()
        # Exact counts are anchored to the recovered source with all existing renderer patches.
        for row in baseline:
            path, token, expected = row.split('|')
            self.assertEqual((ROOT/path).read_text().count(token),int(expected),row)

    def test_priority_metadata_is_owned_by_operation(self):
        self.assertIn('CurrentTick(), telemetry', SCHED)
        self.assertIn('timer(operation.telemetry, NovaRender::ReadbackField::DeferredWaitNs)',SCHED)
        self.assertIn('telemetry, copies = std::move(copies)',BUF)

    def test_cost_window_integration(self):
        costs=(ROOT/'novaRenderCosts.h').read_text()
        self.assertIn('std::chrono::seconds(5)',costs)
        self.assertLess(costs.index('DumpReadbackCounters()'),costs.index('entries = {};',costs.index('DumpReadbackCounters()')))
        telemetry=(ROOT/'novaReadbackTelemetry.h').read_text()
        for name in ('priority_wait_ms','publish_ms','wait_ms','deferred_gpu_wait_ms','page_promotion_candidates'):
            self.assertIn(name,telemetry)

    def test_gc_retains_cpu_protection_until_publication(self):
        method=BUF[BUF.index('const auto completion_tick = m_scheduler.CurrentTick();'):]
        self.assertLess(method.index('WaitPriorityOperations(completion_tick)'),method.index('UnmarkRegionAsGpuModified'))
        self.assertLess(method.index('UnmarkRegionAsGpuModified'),method.index('UntrackMemory'))

    def test_release_mem_host_store_follows_publication(self):
        gpu=(ROOT.parents[1]/'guest_gpu/graphicsRun.cpp').read_text()
        method=gpu.split('auto complete_write =',1)[1].split('auto write32',1)[0]
        self.assertLess(method.index('WaitPriorityOperations'),method.index('GuestMemory::Copy'))
        self.assertLess(method.index('GuestMemory::Copy'),method.rindex('TriggerInterrupt'))
        self.assertIn('WriteEopLabel(',method)
        self.assertIn('DeferPriorityOperation(',method)

    def test_production_telemetry_sanitizer(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'telemetry'
            flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('SANITIZE')=='1' else []
            subprocess.run(['g++','-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror',*flags,
                '-I'+str(ROOT),str(Path(__file__).with_name('novaps5_readback_telemetry_sanitizer.cpp')),'-o',str(out)],check=True)
            for title in ('PPSA04703','PPSA15552',''):
                subprocess.run([str(out)],env=dict(os.environ,NOVA_CACHE_TITLE_ID=title),check=True)

if __name__=='__main__': unittest.main(verbosity=2)
