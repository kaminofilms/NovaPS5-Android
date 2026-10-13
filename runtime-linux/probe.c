#define _GNU_SOURCE
#define VK_NO_PROTOTYPES
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <sys/mman.h>
#include <dlfcn.h>
#include <vulkan/vulkan.h>

/* Nova x86-64 guest probe. Runs under FEX on Android and ARM64 CI.
 *   nova-probe            basic x86-64 execution
 *   nova-probe --vulkan   instance, devices, and every feature/extension KytyPS5 df5b9b9
 *                         requires (src/graphics/presentation/window/vulkanWindow.cpp)
 *   nova-probe --memory   highest reachable guest virtual address and Kyty arena window
 */

static int vulkan_probe(void) {
  void *library = dlopen("libvulkan.so.1", RTLD_NOW);
  if (!library) { fprintf(stderr, "NOVA_ERROR: Vulkan guest loader: %s\n", dlerror()); return 71; }
  Dl_info info;
  void *anchor = dlsym(library, "vkGetInstanceProcAddr");
  if (anchor && dladdr(anchor, &info)) printf("NOVA_VULKAN: guest libvulkan.so.1 resolved to %s\n", info.dli_fname);
  PFN_vkGetInstanceProcAddr gipa = (PFN_vkGetInstanceProcAddr)anchor;
  if (!gipa) { fputs("NOVA_ERROR: vkGetInstanceProcAddr missing\n", stderr); return 72; }
#define G(name) PFN_##name name = (PFN_##name)gipa(instance, #name)
  VkInstance instance = VK_NULL_HANDLE;
  G(vkCreateInstance);
  G(vkEnumerateInstanceVersion);
  uint32_t loader_version = VK_API_VERSION_1_0;
  if (vkEnumerateInstanceVersion) vkEnumerateInstanceVersion(&loader_version);
  printf("NOVA_VULKAN: loader instance version %u.%u.%u\n", VK_VERSION_MAJOR(loader_version), VK_VERSION_MINOR(loader_version), VK_VERSION_PATCH(loader_version));
  VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO, 0, "Nova FEX preflight", 1, "Nova", 1, VK_API_VERSION_1_3};
  VkInstanceCreateInfo create = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, 0, 0, &app, 0, 0, 0, 0};
  VkResult result = vkCreateInstance(&create, 0, &instance);
  if (result) { fprintf(stderr, "NOVA_ERROR: vkCreateInstance=%d%s\n", result, result == VK_ERROR_INCOMPATIBLE_DRIVER ? " (no usable ICD reached by the guest loader)" : ""); return 73; }
  G(vkEnumeratePhysicalDevices); G(vkDestroyInstance); G(vkGetPhysicalDeviceProperties);
  G(vkGetPhysicalDeviceFeatures2); G(vkEnumerateDeviceExtensionProperties); G(vkGetPhysicalDeviceProperties2);
  uint32_t count = 0;
  result = vkEnumeratePhysicalDevices(instance, &count, 0);
  printf("NOVA_VULKAN: vkEnumeratePhysicalDevices=%d devices=%u\n", result, count);
  if (result || !count) { vkDestroyInstance(instance, 0); return 74; }
  VkPhysicalDevice devices[16];
  if (count > 16) count = 16;
  vkEnumeratePhysicalDevices(instance, &count, devices);
  int any_suitable = 0;
  for (uint32_t d = 0; d < count; d++) {
    VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(devices[d], &p);
    printf("NOVA_VULKAN: device %u: %s api=%u.%u.%u driver=0x%x vendor=0x%x\n", d, p.deviceName,
           VK_VERSION_MAJOR(p.apiVersion), VK_VERSION_MINOR(p.apiVersion), VK_VERSION_PATCH(p.apiVersion), p.driverVersion, p.vendorID);
    if (vkGetPhysicalDeviceProperties2 && p.apiVersion >= VK_API_VERSION_1_2) {
      VkPhysicalDeviceDriverProperties drv = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
      VkPhysicalDeviceProperties2 p2 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &drv};
      vkGetPhysicalDeviceProperties2(devices[d], &p2);
      printf("NOVA_VULKAN: device %u driver id=%d name=\"%s\" info=\"%s\"\n", d, drv.driverID, drv.driverName, drv.driverInfo);
    }
    VkPhysicalDeviceFragmentShaderBarycentricFeaturesKHR bary = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FRAGMENT_SHADER_BARYCENTRIC_FEATURES_KHR};
    VkPhysicalDeviceImageViewMinLodFeaturesEXT minlod = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_VIEW_MIN_LOD_FEATURES_EXT, &bary};
    VkPhysicalDeviceColorWriteEnableFeaturesEXT cwe = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COLOR_WRITE_ENABLE_FEATURES_EXT, &minlod};
    VkPhysicalDeviceDepthClipEnableFeaturesEXT dce = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DEPTH_CLIP_ENABLE_FEATURES_EXT, &cwe};
    VkPhysicalDeviceDepthClipControlFeaturesEXT dcc = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DEPTH_CLIP_CONTROL_FEATURES_EXT, &dce};
    VkPhysicalDeviceVulkan11Features f11 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &dcc};
    VkPhysicalDeviceVulkan12Features f12 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &f11};
    VkPhysicalDeviceVulkan13Features f13 = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES, &f12};
    VkPhysicalDeviceFeatures2 f = {VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &f13};
    int api13 = p.apiVersion >= VK_API_VERSION_1_3;
    if (api13) vkGetPhysicalDeviceFeatures2(devices[d], &f);
    const VkPhysicalDeviceFeatures *b = &f.features;
    struct { const char *name; VkBool32 ok; } req[] = {
      {"apiVersion>=1.3", api13},
      {"colorWriteEnable", cwe.colorWriteEnable}, {"imageViewMinLod", minlod.minLod},
      {"depthClipControl", dcc.depthClipControl}, {"depthClipEnable", dce.depthClipEnable},
      {"depthClamp", b->depthClamp}, {"fragmentShaderBarycentric", bary.fragmentShaderBarycentric},
      {"samplerMirrorClampToEdge", f12.samplerMirrorClampToEdge}, {"storageBuffer16BitAccess", f11.storageBuffer16BitAccess},
      {"storageBuffer8BitAccess", f12.storageBuffer8BitAccess}, {"timelineSemaphore", f12.timelineSemaphore},
      {"shaderOutputLayer", f12.shaderOutputLayer}, {"shaderOutputViewportIndex", f12.shaderOutputViewportIndex},
      {"bufferDeviceAddress", f12.bufferDeviceAddress}, {"shaderBufferInt64Atomics", f12.shaderBufferInt64Atomics},
      {"shaderSampledImageArrayNonUniformIndexing", f12.shaderSampledImageArrayNonUniformIndexing},
      {"robustImageAccess", f13.robustImageAccess}, {"dynamicRendering", f13.dynamicRendering},
      {"synchronization2", f13.synchronization2}, {"sampleRateShading", b->sampleRateShading},
      {"depthBiasClamp", b->depthBiasClamp}, {"shaderClipDistance", b->shaderClipDistance},
      {"shaderCullDistance", b->shaderCullDistance}, {"largePoints", b->largePoints},
      {"multiViewport", b->multiViewport}, {"fillModeNonSolid", b->fillModeNonSolid},
      {"fragmentStoresAndAtomics", b->fragmentStoresAndAtomics}, {"samplerAnisotropy", b->samplerAnisotropy},
      {"robustBufferAccess", b->robustBufferAccess}, {"depthBounds", b->depthBounds},
      {"shaderStorageImageWriteWithoutFormat", b->shaderStorageImageWriteWithoutFormat},
      {"shaderImageGatherExtended", b->shaderImageGatherExtended}, {"independentBlend", b->independentBlend},
      {"tessellationShader", b->tessellationShader},
    };
    uint32_t ext_count = 0;
    vkEnumerateDeviceExtensionProperties(devices[d], 0, &ext_count, 0);
    VkExtensionProperties *exts = calloc(ext_count ? ext_count : 1, sizeof *exts);
    vkEnumerateDeviceExtensionProperties(devices[d], 0, &ext_count, exts);
    const char *need_ext[] = {"VK_KHR_swapchain", "VK_EXT_depth_clip_control", "VK_EXT_image_view_min_lod",
      "VK_KHR_push_descriptor", "VK_KHR_maintenance1", "VK_EXT_depth_clip_enable", "VK_EXT_color_write_enable",
      "VK_KHR_fragment_shader_barycentric"};
    int missing = 0;
    for (size_t i = 0; i < sizeof req / sizeof *req; i++)
      if (!req[i].ok) { printf("NOVA_KYTY_REQ: device %u FEATURE MISSING %s\n", d, req[i].name); missing++; }
    for (size_t i = 0; i < sizeof need_ext / sizeof *need_ext; i++) {
      int found = 0;
      for (uint32_t e = 0; e < ext_count; e++) found |= !strcmp(exts[e].extensionName, need_ext[i]);
      if (!found) { printf("NOVA_KYTY_REQ: device %u EXTENSION MISSING %s\n", d, need_ext[i]); missing++; }
    }
    free(exts);
    printf("NOVA_KYTY_REQ: device %u %s (%d missing of %zu checks)\n", d, missing ? "FAIL" : "PASS", missing,
           sizeof req / sizeof *req + sizeof need_ext / sizeof *need_ext);
    any_suitable |= !missing;
  }
  vkDestroyInstance(instance, 0);
  printf("NOVA_VULKAN: instance and device enumeration PASS; Kyty device requirements %s; frame presentation UNVERIFIED\n",
         any_suitable ? "PASS" : "FAIL");
  return any_suitable ? 0 : 75;
}

/* Kyty's Linux allocator places automatic mappings in [640 GiB, 1008 GiB) and falls back to
 * kernel-chosen addresses. Android ARM64 kernels commonly use 39-bit user VA (512 GiB),
 * which puts that whole window out of reach. Report the real ceiling. */
static int memory_probe(void) {
  int top_bit = 0;
  for (int bit = 48; bit >= 36; bit--) {
    void *want = (void *)(1ULL << (bit - 1)); /* mappable => at least `bit` VA bits */
    void *p = mmap(want, 0x10000, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
    if (p == want) { munmap(p, 0x10000); top_bit = bit; break; }
    if (p != MAP_FAILED) munmap(p, 0x10000);
  }
  printf("NOVA_MEMORY: guest user VA is %d-bit (%s)\n", top_bit,
         top_bit >= 40 ? "Kyty arena window [0xA000000000,0xFC00000000) reachable" :
         "Kyty arena window unreachable; Kyty falls back to kernel-chosen addresses");
  const uintptr_t base = 0x200000000ULL; const size_t size = 0x400000000ULL; /* Kyty PS5 default map base, 16 GiB */
  errno = 0;
  void *p = mmap((void *)base, size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
  int e = errno;
  printf("NOVA_MEMORY: guest map base 0x%lx size 0x%lx %s errno=%d (%s)\n", (unsigned long)base, (unsigned long)size,
         p == (void *)base ? "PASS" : "FAIL", e, p == (void *)base ? "ok" : strerror(e));
  if (p != MAP_FAILED) munmap(p, size);
  return p == (void *)base ? 0 : 76;
}

int main(int argc, char **argv) {
  printf("NOVA_PROBE: x86-64 Linux process; page_size=%ld pid=%d\n", sysconf(_SC_PAGESIZE), getpid());
  if (argc > 1 && !strcmp(argv[1], "--vulkan")) return vulkan_probe();
  if (argc > 1 && !strcmp(argv[1], "--memory")) return memory_probe();
  return 0;
}
