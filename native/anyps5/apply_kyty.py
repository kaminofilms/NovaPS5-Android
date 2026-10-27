import pathlib
import re
import sys

core = pathlib.Path(sys.argv[1]).resolve()
adapter = pathlib.Path(__file__).resolve().parent
any_source = pathlib.Path(sys.argv[2]).resolve()
renderer_build = pathlib.Path(sys.argv[3]).resolve()

def original(relative):
    path = core / relative
    backup = path.with_name(path.name + '.nova-anyps5-original')
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    return path, backup.read_text()

def change(relative, anchor, replacement):
    path, text = original(relative)
    if text.count(anchor) != 1:
        raise RuntimeError(f'{relative}: expected one integration anchor, got {text.count(anchor)}')
    path.write_text('#include "kyty_bridge.hpp"\n' + text.replace(anchor, replacement))

p, s = original('src/libs/agc.cpp')
s = s.replace('void Initialize() {', 'void Initialize() {\n    if (NovaAnyPS5::Enabled()) { NovaAnyPS5::Initialize(); return; }', 1)
s = s.replace('void Shutdown() {', 'void Shutdown() {\n    if (NovaAnyPS5::Enabled()) { NovaAnyPS5::Shutdown(); return; }', 1)
# AnyPS5's AGC driver owns the PS5 driver DMEM block at 0x0fe0000000. That address lies in
# Kyty's reserved guest system region, so it must be allocated and mapped through Kyty's
# kernel memory (as Gen5Driver::Initialize does), which also publishes it to the renderer.
anchor = 'static void ReleaseDmem() {'
assert s.count(anchor) == 1, 'agc.cpp ReleaseDmem anchor'
s = s.replace(anchor, r'''void* NovaAnyPS5DriverMemory(uint64_t requested_address, size_t requested_size) {
	std::scoped_lock lock {g_driver_dmem.mutex};
	if (requested_address != DriverDmemBase || requested_size != DriverDmemSize) {
		return nullptr;
	}
	if (g_driver_dmem.physical_offset >= 0) {
		return nullptr; // One owner per process: never hand the block out twice.
	}
	int64_t physical_offset = -1;
	if (LibKernel::Memory::KernelAllocateDirectMemory(0, LibKernel::Memory::KernelGetDirectMemorySize(),
	        DriverDmemSize, DriverDmemSize, 12, &physical_offset) != OK) {
		return nullptr;
	}
	void* address = reinterpret_cast<void*>(DriverDmemBase);
	if (LibKernel::Memory::KernelMapNamedDirectMemory(&address, DriverDmemSize, 0x33, 0, physical_offset,
	        DriverDmemSize, "SceAgcDriver") != OK || reinterpret_cast<uint64_t>(address) != DriverDmemBase) {
		EXIT_IF(LibKernel::Memory::KernelCheckedReleaseDirectMemory(physical_offset, DriverDmemSize) != OK);
		return nullptr;
	}
	std::memset(address, 0, DriverDmemSize);
	g_driver_dmem.physical_offset = physical_offset;
	return address;
}

''' + anchor, 1)
p.write_text('#include "kyty_bridge.hpp"\n' + s)
change('src/graphics/presentation/window/window.cpp', 'void WindowRun() {', 'void WindowRun() {\n    if (NovaAnyPS5::Enabled()) { NovaAnyPS5::RunWindow(); return; }')
change('src/libs/libAgcDriver.cpp', 'LIB_DEFINE(InitAgcDriver_1) {\n\tLibGen5::InitAgcDriver_1(s);', 'LIB_DEFINE(InitAgcDriver_1) {\n    if (NovaAnyPS5::Enabled()) { NovaAnyPS5::RegisterGraphicsExports(s); return; }\n\tLibGen5::InitAgcDriver_1(s);')
change('src/libs/libVideoOut.cpp', 'LIB_DEFINE(InitVideoOut_1) {', 'LIB_DEFINE(InitVideoOut_1) {\n    if (NovaAnyPS5::Enabled()) { NovaAnyPS5::RegisterVideoExports(s); return; }')
p = core / 'src/libs/libVideoOut.cpp'
s = p.read_text().replace('LIB_DEFINE(InitVideoOutVrrStatus_1) {', 'LIB_DEFINE(InitVideoOutVrrStatus_1) {\n    if (NovaAnyPS5::Enabled()) return;')
p.write_text(s)
p, s = original('src/kernel/memory.cpp')
s = '#include "memory_mutation.hpp"\n' + s
query_names = {'RegisterCallbacks', 'KernelAvailableDirectMemorySize', 'KernelGetPageTableStats', 'KernelDirectMemoryQuery', 'KernelQueryMemoryProtectionNovaT', 'KernelVirtualQueryNovaT', 'KernelIsStackNovaT', 'KernelAvailableFlexibleMemorySize', 'KernelMemoryPoolGetBlockStats'}
needle = 'std::lock_guard<std::recursive_mutex> memory_operation_lock(g_memory_operation_mutex);'
positions = list(re.finditer(re.escape(needle), s))
for match in reversed(positions):
    signatures = re.findall(r'^([^\n;{}]+\([^;{}]*\))\s*\{', s[:match.start()], re.M)
    signature = signatures[-1]
    name = re.search(r'(\w+)\s*\(', signature).group(1)
    if name not in query_names:
        s = s[:match.start()] + 'NovaAnyPS5::MemoryChange anyps5_memory_change;\n\t' + s[match.start():]
anchor = '\tbool QuerySpan(uint64_t start, uint64_t size, std::vector<Range>* out) {'
assert s.count(anchor) == 1
s = s.replace(anchor, '\tstd::vector<Range> NovaAnySnapshot() { Common::LockGuard lock(m_mutex); return m_ranges; }\n\n' + anchor)
anchor = 'void SetFlexibleMemorySize(uint64_t size) {'
helpers = r'''
bool NovaAnyQuery(uint64_t address, VirtualQueryInfo* output) {
    std::lock_guard<std::recursive_mutex> lock(g_memory_operation_mutex);
    VirtualRanges::Range range{};
    if (!g_virtual_ranges || !g_virtual_ranges->Query(address, 1, &range)) return false;
    *output = {};
    output->start = range.start;
    output->end = range.start + range.size;
    output->offset = range.offset;
    output->protection = range.protection;
    output->is_committed = IsCommittedRangeType(range.type);
    output->is_direct = range.type == VirtualRangeType::Direct;
    return true;
}
std::vector<VirtualQueryInfo> NovaAnySnapshot() {
    std::lock_guard<std::recursive_mutex> lock(g_memory_operation_mutex);
    std::vector<VirtualQueryInfo> result;
    for (const auto& range : g_virtual_ranges->NovaAnySnapshot()) {
        if (!IsCommittedRangeType(range.type)) continue;
        VirtualQueryInfo info{};
        info.start = range.start;
        info.end = range.start + range.size;
        info.protection = range.protection;
        info.is_committed = 1;
        result.push_back(info);
    }
    return result;
}
bool NovaAnySharedBacking(uint64_t address, size_t bytes, int* file, uint64_t* offset) {
    std::lock_guard<std::recursive_mutex> lock(g_memory_operation_mutex);
    return g_guest_address_space->NovaAnySharedBacking(address, bytes, file, offset);
}
'''
assert s.count(anchor) == 1
s = s.replace(anchor, helpers + '\n' + anchor)
p.write_text(s)
p, s = original('src/kernel/memoryAddressSpace.inc')
# Guest VA slots exist only in [2^39, 2^47). Android tagged heap pointers (0xb4...) are host
# addresses: without this bound each such call tried (and failed) to allocate a 1 GiB slot window.
anchor = '\tif (vaddr < (uint64_t {1} << 39) || !NovaFex::GuestVAEnabled()) {'
assert s.count(anchor) == 1, 'memoryAddressSpace.inc NovaHostVA anchor'
s = s.replace(anchor, '\tif (vaddr < (uint64_t {1} << 39) || vaddr >= (uint64_t {1} << 47) || !NovaFex::GuestVAEnabled()) {')
# Wait for GPU leases only on the range whose host mapping/protection changes.
for unit in ['bool ProtectUnit(uint64_t vaddr, uint64_t size, VirtualMemory::Mode mode) {',
             'bool UnmapBackingUnit(uint64_t vaddr, uint64_t size) {',
             'bool ReleaseFreeUnit(uint64_t vaddr, uint64_t size) {',
             'bool ReleaseCommittedUnit(uint64_t vaddr, uint64_t size) {']:
    assert s.count('\t' + unit + '\n\t\tNOVA_HOST_VA(vaddr, size);') == 1, unit
    s = s.replace('\t' + unit + '\n\t\tNOVA_HOST_VA(vaddr, size);', '\t' + unit + '\n\t\tNovaAnyPS5::PrepareRangeChange(vaddr, size);\n\t\tNOVA_HOST_VA(vaddr, size);')
map_unit = '\t                    GuestBackingStore::FailureReason* failure_reason) {\n\t\tNOVA_HOST_VA(vaddr, size);'
assert s.count(map_unit) == 1, 'MapBackingUnit'
s = s.replace(map_unit, '\t                    GuestBackingStore::FailureReason* failure_reason) {\n\t\tNovaAnyPS5::PrepareRangeChange(vaddr, size);\n\t\tNOVA_HOST_VA(vaddr, size);')
anchor = '\tbool ZeroRange(uint64_t backing_offset, uint64_t size) {'
method = r'''
    bool NovaAnySharedBacking(uint64_t address, size_t bytes, int* file, uint64_t* offset) {
#if KYTY_PLATFORM == KYTY_PLATFORM_LINUX
        if (!file || !offset || !bytes || UINT64_MAX - address < bytes) return false;
        std::shared_lock lock(m_mutex);
        auto found = m_maps.upper_bound(address);
        if (found == m_maps.begin()) return false;
        --found;
        const auto& range = found->second;
        if (address < range.vaddr || address >= range.vaddr + range.size || bytes > range.vaddr + range.size - address) return false;
        const int duplicate = fcntl(m_fd, F_DUPFD_CLOEXEC, 0);
        if (duplicate < 0) return false;
        *file = duplicate;
        *offset = range.backing_offset + address - range.vaddr;
        return true;
#else
        return false;
#endif
    }
'''
assert s.count(anchor) == 1
s = s.replace(anchor, method + '\n' + anchor)
anchor = '\tbool ZeroBacking(uint64_t backing_offset, uint64_t size) {'
method = r'''
    bool NovaAnySharedBacking(uint64_t address, size_t bytes, int* file, uint64_t* offset) {
#if defined(KYTY_NOVA_FEX)
        if (NovaGuest::Piece(address, bytes) != bytes) return false;
        address = reinterpret_cast<uint64_t>(NovaGuest::Host(address));
#endif
        return m_backing->NovaAnySharedBacking(address, bytes, file, offset);
    }
'''
assert s.count(anchor) == 1
s = s.replace(anchor, method + '\n' + anchor)
p.write_text(s)
p, s = original('CMakeLists.txt')
s += f'''
if(KYTY_ANDROID)
    target_sources(kyty_emulator PRIVATE "{adapter}/kyty_bridge.cpp")
    set_source_files_properties("{adapter}/kyty_bridge.cpp" PROPERTIES COMPILE_OPTIONS "-fexceptions;-frtti")
    target_include_directories(kyty_emulator BEFORE PRIVATE "{adapter}" "{any_source}/core/libs" "{any_source}/core/shader/recompiler" "{any_source}/core/shader/recompiler/RdnaDecoder/include")
    target_link_libraries(kyty_emulator "{renderer_build}/renderer/libnova_anyps5_renderer.so")
endif()
'''
p.write_text(s)
print('Staged native AnyPS5 graphics, VideoOut, NovaFEX exports and memory integration')
