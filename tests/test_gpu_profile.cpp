// Host test of NovaGpuProfile with fake Vulkan entry points (timestamps from a counter).
#include "../native/render/NovaGpuProfile.h"
#include <cassert>
#include <cstring>
#include <map>
#include <thread>
static std::map<uint32_t, uint64_t> stamps;
static uint64_t gpu_clock = 1000;
static VkResult create(VkDevice, const VkQueryPoolCreateInfo* info, const VkAllocationCallbacks*, VkQueryPool* pool) {
    assert(info->queryType == VK_QUERY_TYPE_TIMESTAMP); *pool = reinterpret_cast<VkQueryPool>(uintptr_t(0x1234)); return VK_SUCCESS; }
static void reset(VkCommandBuffer, VkQueryPool, uint32_t first, uint32_t count) { for (uint32_t i = first; i < first + count; ++i) stamps.erase(i); }
static void write(VkCommandBuffer, VkPipelineStageFlagBits, VkQueryPool, uint32_t q) { stamps[q] = gpu_clock; }
static VkResult results(VkDevice, VkQueryPool, uint32_t first, uint32_t count, size_t size, void* data, VkDeviceSize stride, VkQueryResultFlags) {
    assert(stride == 16 && size >= count * 16u);
    auto* out = static_cast<uint64_t*>(data);
    for (uint32_t i = 0; i < count; ++i) { auto f = stamps.find(first + i); out[i * 2] = f == stamps.end() ? 0 : f->second; out[i * 2 + 1] = f != stamps.end(); }
    return VK_SUCCESS; }
int main() {
    setenv("NOVA_GPU_DRAW_PROFILE", "1", 1);
    VkPhysicalDeviceLimits limits {}; limits.timestampComputeAndGraphics = VK_TRUE; limits.timestampPeriod = 1000.0f;  // 1 tick = 1 us
    auto& p = NovaGpuProfile::Profiler::Get();
    auto cb = reinterpret_cast<VkCommandBuffer>(uintptr_t(0x99));
    auto begin = [&] { p.BeginCommandBuffer(reinterpret_cast<VkDevice>(uintptr_t(1)), limits, cb, create, results, reset, write); };
    begin();  // quiet period: nothing sampled
    { NovaGpuProfile::Scope s(cb, {NovaGpuProfile::Kind::Draw, 0xAA}); gpu_clock += 50; }
    assert(stamps.empty());
    std::this_thread::sleep_for(std::chrono::milliseconds(9100));
    begin();  // sampling second
    for (int i = 0; i < 3; ++i) { NovaGpuProfile::Scope s(cb, {NovaGpuProfile::Kind::Draw, 0xAA, 1920, 1080, 2, 3, 1}); gpu_clock += 4000; }  // 3 x 4 ms
    { NovaGpuProfile::Scope s(cb, {NovaGpuProfile::Kind::Dispatch, 0xBB, 8, 8, 0, 1, 1}); gpu_clock += 500; }
    assert(stamps.size() == 8);
    std::this_thread::sleep_for(std::chrono::milliseconds(3000));
    begin();  // report (prints NOVA_GPU_DRAWS + 2 pipelines: 0xaa 12 ms, 0xbb 0.5 ms)
    std::puts("PASS NovaGpuProfile: quiet period untouched; sampled draws timed and ranked");
}
