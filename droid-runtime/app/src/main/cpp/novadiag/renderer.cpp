#define VK_USE_PLATFORM_ANDROID_KHR
#include <vulkan/vulkan.h>
#include "renderer.h"
#include "diagnostic_pad.h"
#include "shader_bytes.h"
#include <android/log.h>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <memory>
#include <mutex>
#include <sstream>
#include <thread>
#include <vector>
#include <algorithm>
#include <stdexcept>
namespace Nova {
namespace {
std::mutex pad_mutex,status_mutex,lifecycle_mutex;
NovaDiagnosticPad pad{};
std::atomic<uint64_t> frames{0};
std::string status="Renderer stopped";
void Status(const std::string& s){std::lock_guard<std::mutex> l(status_mutex);status=s;__android_log_print(ANDROID_LOG_INFO,"NovaPs5","%s",s.c_str());}
std::string Version(uint32_t n){return std::to_string(VK_VERSION_MAJOR(n))+"."+std::to_string(VK_VERSION_MINOR(n))+"."+std::to_string(VK_VERSION_PATCH(n));}
void Check(VkResult result,const char* action){if(result!=VK_SUCCESS)throw std::runtime_error(std::string(action)+": VkResult "+std::to_string(result));}
uint32_t LoaderVersion(){uint32_t version=VK_API_VERSION_1_0;auto fn=reinterpret_cast<PFN_vkEnumerateInstanceVersion>(vkGetInstanceProcAddr(VK_NULL_HANDLE,"vkEnumerateInstanceVersion"));if(fn)fn(&version);return version;}
std::string Escape(const std::string& s){std::string v;for(char c:s){if(c=='"'||c=='\\')v+='\\';if(c=='\n')v+="\\n";else if(static_cast<unsigned char>(c)>=32)v+=c;}return v;}
std::string FailJson(const std::string& s){return "{\"available\":false,\"error\":\""+Escape(s)+"\"}";}
struct Renderer {
    std::atomic<bool> stop{false};std::thread worker;ANativeWindow* window;
    VkInstance instance=VK_NULL_HANDLE;VkSurfaceKHR surface=VK_NULL_HANDLE;VkPhysicalDevice gpu=VK_NULL_HANDLE;
    VkDevice device=VK_NULL_HANDLE;VkQueue queue=VK_NULL_HANDLE;uint32_t family=0;
    VkSwapchainKHR swapchain=VK_NULL_HANDLE;VkFormat format=VK_FORMAT_UNDEFINED;VkExtent2D extent{};
    VkRenderPass pass=VK_NULL_HANDLE;VkPipelineLayout layout=VK_NULL_HANDLE;VkPipeline pipeline=VK_NULL_HANDLE;
    VkCommandPool pool=VK_NULL_HANDLE;VkCommandBuffer command=VK_NULL_HANDLE;
    VkSemaphore acquired=VK_NULL_HANDLE,complete=VK_NULL_HANDLE;VkFence fence=VK_NULL_HANDLE;
    std::vector<VkImage> images;std::vector<VkImageView> views;std::vector<VkFramebuffer> buffers;
    explicit Renderer(ANativeWindow* w):window(w){}
    ~Renderer(){Stop();}
    void Stop(){stop=true;if(worker.joinable())worker.join();}
    VkShaderModule Shader(const uint32_t* code,size_t bytes){VkShaderModuleCreateInfo c{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};c.codeSize=bytes;c.pCode=code;VkShaderModule m;Check(vkCreateShaderModule(device,&c,nullptr,&m),"Create SPIR-V shader");return m;}
    void Init(){
        const char* ie[]={VK_KHR_SURFACE_EXTENSION_NAME,VK_KHR_ANDROID_SURFACE_EXTENSION_NAME};
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.pApplicationName="NovaPs5 Vulkan diagnostic";app.applicationVersion=VK_MAKE_VERSION(0,1,0);app.apiVersion=std::min(LoaderVersion(),VK_API_VERSION_1_3);
        VkInstanceCreateInfo ic{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ic.pApplicationInfo=&app;ic.enabledExtensionCount=2;ic.ppEnabledExtensionNames=ie;Check(vkCreateInstance(&ic,nullptr,&instance),"Create Vulkan instance");
        VkAndroidSurfaceCreateInfoKHR sc{VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR};sc.window=window;Check(vkCreateAndroidSurfaceKHR(instance,&sc,nullptr,&surface),"Create Android Vulkan surface");
        uint32_t count=0;Check(vkEnumeratePhysicalDevices(instance,&count,nullptr),"Enumerate Vulkan GPUs");if(!count)throw std::runtime_error("No Vulkan GPU available");std::vector<VkPhysicalDevice> devices(count);Check(vkEnumeratePhysicalDevices(instance,&count,devices.data()),"Read Vulkan GPUs");
        bool found=false;
        for(auto d:devices){uint32_t n=0;vkGetPhysicalDeviceQueueFamilyProperties(d,&n,nullptr);std::vector<VkQueueFamilyProperties> props(n);vkGetPhysicalDeviceQueueFamilyProperties(d,&n,props.data());
            for(uint32_t q=0;q<n;++q){VkBool32 present=false;Check(vkGetPhysicalDeviceSurfaceSupportKHR(d,q,surface,&present),"Surface queue support");if((props[q].queueFlags&VK_QUEUE_GRAPHICS_BIT)&&present){gpu=d;family=q;found=true;break;}}
            if(found)break;
        }
        if(!found)throw std::runtime_error("No graphics/present queue available");
        float priority=1;VkDeviceQueueCreateInfo qc{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qc.queueFamilyIndex=family;qc.queueCount=1;qc.pQueuePriorities=&priority;
        const char* de[]={VK_KHR_SWAPCHAIN_EXTENSION_NAME};VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};dc.queueCreateInfoCount=1;dc.pQueueCreateInfos=&qc;dc.enabledExtensionCount=1;dc.ppEnabledExtensionNames=de;Check(vkCreateDevice(gpu,&dc,nullptr,&device),"Create Vulkan device");vkGetDeviceQueue(device,family,0,&queue);
        VkSurfaceCapabilitiesKHR caps;Check(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(gpu,surface,&caps),"Surface capabilities");
        if(!(caps.supportedUsageFlags&VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))throw std::runtime_error("Surface has no color attachment support");
        uint32_t fn=0;Check(vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&fn,nullptr),"Surface formats");if(!fn)throw std::runtime_error("No surface formats");std::vector<VkSurfaceFormatKHR> formats(fn);Check(vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&fn,formats.data()),"Read formats");
        auto chosen=formats[0];for(auto f:formats)if(f.format==VK_FORMAT_R8G8B8A8_UNORM||f.format==VK_FORMAT_B8G8R8A8_UNORM){chosen=f;break;}
        if(chosen.format==VK_FORMAT_UNDEFINED)chosen.format=VK_FORMAT_B8G8R8A8_UNORM;
        format=chosen.format;extent=caps.currentExtent;
        if(extent.width==UINT32_MAX){extent.width=std::max(caps.minImageExtent.width,std::min(caps.maxImageExtent.width,static_cast<uint32_t>(std::max(1,ANativeWindow_getWidth(window)))));extent.height=std::max(caps.minImageExtent.height,std::min(caps.maxImageExtent.height,static_cast<uint32_t>(std::max(1,ANativeWindow_getHeight(window)))));}
        uint32_t image_count=std::max(2u,caps.minImageCount);if(caps.maxImageCount)image_count=std::min(image_count,caps.maxImageCount);
        VkCompositeAlphaFlagBitsKHR alpha=VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;for(auto a:{VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR,VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR})if(caps.supportedCompositeAlpha&a){alpha=a;break;}
        VkSwapchainCreateInfoKHR sw{VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR};sw.surface=surface;sw.minImageCount=image_count;sw.imageFormat=format;sw.imageColorSpace=chosen.colorSpace;sw.imageExtent=extent;sw.imageArrayLayers=1;sw.imageUsage=VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;sw.imageSharingMode=VK_SHARING_MODE_EXCLUSIVE;sw.preTransform=caps.currentTransform;sw.compositeAlpha=alpha;sw.presentMode=VK_PRESENT_MODE_FIFO_KHR;sw.clipped=VK_TRUE;Check(vkCreateSwapchainKHR(device,&sw,nullptr,&swapchain),"Create swapchain");
        Check(vkGetSwapchainImagesKHR(device,swapchain,&image_count,nullptr),"Swapchain images");images.resize(image_count);Check(vkGetSwapchainImagesKHR(device,swapchain,&image_count,images.data()),"Read images");
        VkAttachmentDescription at{};at.format=format;at.samples=VK_SAMPLE_COUNT_1_BIT;at.loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR;at.storeOp=VK_ATTACHMENT_STORE_OP_STORE;at.stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE;at.stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE;at.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED;at.finalLayout=VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        VkAttachmentReference ar{0,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};VkSubpassDescription sub{};sub.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS;sub.colorAttachmentCount=1;sub.pColorAttachments=&ar;
        VkSubpassDependency dependency{};dependency.srcSubpass=VK_SUBPASS_EXTERNAL;dependency.dstSubpass=0;dependency.srcStageMask=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;dependency.dstStageMask=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;dependency.dstAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
        VkRenderPassCreateInfo rp{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};rp.attachmentCount=1;rp.pAttachments=&at;rp.subpassCount=1;rp.pSubpasses=&sub;rp.dependencyCount=1;rp.pDependencies=&dependency;Check(vkCreateRenderPass(device,&rp,nullptr,&pass),"Create render pass");
        for(auto im:images){VkImageViewCreateInfo iv{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};iv.image=im;iv.viewType=VK_IMAGE_VIEW_TYPE_2D;iv.format=format;iv.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;iv.subresourceRange.levelCount=1;iv.subresourceRange.layerCount=1;VkImageView view;Check(vkCreateImageView(device,&iv,nullptr,&view),"Create image view");views.push_back(view);
            VkFramebufferCreateInfo fb{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};fb.renderPass=pass;fb.attachmentCount=1;fb.pAttachments=&view;fb.width=extent.width;fb.height=extent.height;fb.layers=1;VkFramebuffer buffer;Check(vkCreateFramebuffer(device,&fb,nullptr,&buffer),"Create framebuffer");buffers.push_back(buffer);}
        VkPipelineLayoutCreateInfo plc{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};Check(vkCreatePipelineLayout(device,&plc,nullptr,&layout),"Create pipeline layout");
        VkShaderModule vertex=Shader(triangle_vert,sizeof(triangle_vert)),fragment=VK_NULL_HANDLE;
        try{
            fragment=Shader(triangle_frag,sizeof(triangle_frag));
            VkPipelineShaderStageCreateInfo stages[2]{};for(auto& s:stages){s.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;s.pName="main";}stages[0].stage=VK_SHADER_STAGE_VERTEX_BIT;stages[0].module=vertex;stages[1].stage=VK_SHADER_STAGE_FRAGMENT_BIT;stages[1].module=fragment;
            VkPipelineVertexInputStateCreateInfo vi{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};VkPipelineInputAssemblyStateCreateInfo ia{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};ia.topology=VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
            VkPipelineViewportStateCreateInfo vs{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};vs.viewportCount=1;vs.scissorCount=1;
            VkPipelineRasterizationStateCreateInfo rs{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};rs.polygonMode=VK_POLYGON_MODE_FILL;rs.cullMode=VK_CULL_MODE_NONE;rs.frontFace=VK_FRONT_FACE_COUNTER_CLOCKWISE;rs.lineWidth=1;
            VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};ms.rasterizationSamples=VK_SAMPLE_COUNT_1_BIT;
            VkPipelineColorBlendAttachmentState ba{};ba.colorWriteMask=15;VkPipelineColorBlendStateCreateInfo bs{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};bs.attachmentCount=1;bs.pAttachments=&ba;
            VkDynamicState ds[]={VK_DYNAMIC_STATE_VIEWPORT,VK_DYNAMIC_STATE_SCISSOR};VkPipelineDynamicStateCreateInfo dys{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};dys.dynamicStateCount=2;dys.pDynamicStates=ds;
            VkGraphicsPipelineCreateInfo pi{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};pi.stageCount=2;pi.pStages=stages;pi.pVertexInputState=&vi;pi.pInputAssemblyState=&ia;pi.pViewportState=&vs;pi.pRasterizationState=&rs;pi.pMultisampleState=&ms;pi.pColorBlendState=&bs;pi.pDynamicState=&dys;pi.layout=layout;pi.renderPass=pass;
            Check(vkCreateGraphicsPipelines(device,VK_NULL_HANDLE,1,&pi,nullptr,&pipeline),"Create SPIR-V graphics pipeline");
        }catch(...){if(fragment)vkDestroyShaderModule(device,fragment,nullptr);vkDestroyShaderModule(device,vertex,nullptr);throw;}
        vkDestroyShaderModule(device,vertex,nullptr);vkDestroyShaderModule(device,fragment,nullptr);
        VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pc.queueFamilyIndex=family;pc.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;Check(vkCreateCommandPool(device,&pc,nullptr,&pool),"Create command pool");VkCommandBufferAllocateInfo cb{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};cb.commandPool=pool;cb.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;cb.commandBufferCount=1;Check(vkAllocateCommandBuffers(device,&cb,&command),"Create command buffer");
        VkSemaphoreCreateInfo se{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};Check(vkCreateSemaphore(device,&se,nullptr,&acquired),"Acquire semaphore");Check(vkCreateSemaphore(device,&se,nullptr,&complete),"Present semaphore");VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};fc.flags=VK_FENCE_CREATE_SIGNALED_BIT;Check(vkCreateFence(device,&fc,nullptr,&fence),"Create frame fence");
        Status("Vulkan pipeline ready. Triangle is a diagnostic scene, not a PS5 game.");
    }
    void Draw(){
        uint32_t index=0;auto result=vkAcquireNextImageKHR(device,swapchain,100000000,acquired,VK_NULL_HANDLE,&index);if(result==VK_TIMEOUT||result==VK_NOT_READY)return;if(result!=VK_SUBOPTIMAL_KHR)Check(result,"Acquire image");
        Check(vkWaitForFences(device,1,&fence,VK_TRUE,1000000000),"Wait for previous frame");Check(vkResetFences(device,1,&fence),"Reset frame fence");Check(vkResetCommandBuffer(command,0),"Reset command buffer");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};begin.flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;Check(vkBeginCommandBuffer(command,&begin),"Begin frame");
        NovaDiagnosticPad input;{std::lock_guard<std::mutex> l(pad_mutex);input=pad;}
        VkClearValue clear{};clear.color.float32[0]=.025f+input.analog_buttons_r2/255.f*.16f;clear.color.float32[1]=.035f+input.analog_buttons_l2/255.f*.12f;clear.color.float32[2]=.10f+input.left_stick_x/255.f*.06f;clear.color.float32[3]=1;
        VkRenderPassBeginInfo rb{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};rb.renderPass=pass;rb.framebuffer=buffers[index];rb.renderArea.extent=extent;rb.clearValueCount=1;rb.pClearValues=&clear;vkCmdBeginRenderPass(command,&rb,VK_SUBPASS_CONTENTS_INLINE);
        float ratio=static_cast<float>(extent.width)/std::max(1u,extent.height);float width=std::min(static_cast<float>(extent.width)*.45f,static_cast<float>(extent.height)*.80f);
        VkViewport vp{(extent.width-width)*.5f+(input.left_stick_x/255.f-.5f)*70,(extent.height-width/ratio)*.5f+(input.left_stick_y/255.f-.5f)*70,width,width/ratio,0,1};VkRect2D sc{{0,0},extent};vkCmdSetViewport(command,0,1,&vp);vkCmdSetScissor(command,0,1,&sc);vkCmdBindPipeline(command,VK_PIPELINE_BIND_POINT_GRAPHICS,pipeline);vkCmdDraw(command,3,1,0,0);vkCmdEndRenderPass(command);Check(vkEndCommandBuffer(command),"End frame");
        VkPipelineStageFlags wait=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};submit.waitSemaphoreCount=1;submit.pWaitSemaphores=&acquired;submit.pWaitDstStageMask=&wait;submit.commandBufferCount=1;submit.pCommandBuffers=&command;submit.signalSemaphoreCount=1;submit.pSignalSemaphores=&complete;Check(vkQueueSubmit(queue,1,&submit,fence),"Submit frame");VkPresentInfoKHR present{VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};present.waitSemaphoreCount=1;present.pWaitSemaphores=&complete;present.swapchainCount=1;present.pSwapchains=&swapchain;present.pImageIndices=&index;result=vkQueuePresentKHR(queue,&present);if(result!=VK_SUBOPTIMAL_KHR)Check(result,"Present frame");
        // Wait for presentation queue before reusing the one present semaphore.
        // This intentionally favors diagnostic correctness over emulator performance.
        Check(vkQueueWaitIdle(queue),"Complete diagnostic presentation");++frames;
    }
    void Cleanup(){
        if(device){vkDeviceWaitIdle(device);if(fence)vkDestroyFence(device,fence,nullptr);if(acquired)vkDestroySemaphore(device,acquired,nullptr);if(complete)vkDestroySemaphore(device,complete,nullptr);if(pool)vkDestroyCommandPool(device,pool,nullptr);if(pipeline)vkDestroyPipeline(device,pipeline,nullptr);if(layout)vkDestroyPipelineLayout(device,layout,nullptr);for(auto b:buffers)vkDestroyFramebuffer(device,b,nullptr);if(pass)vkDestroyRenderPass(device,pass,nullptr);for(auto v:views)vkDestroyImageView(device,v,nullptr);if(swapchain)vkDestroySwapchainKHR(device,swapchain,nullptr);vkDestroyDevice(device,nullptr);device=VK_NULL_HANDLE;}
        if(surface)vkDestroySurfaceKHR(instance,surface,nullptr);if(instance)vkDestroyInstance(instance,nullptr);if(window){ANativeWindow_release(window);window=nullptr;}
    }
    void Run(){try{Init();while(!stop)Draw();}catch(const std::exception& e){Status(std::string("Vulkan diagnostic failed: ")+e.what());}Cleanup();}
};
std::unique_ptr<Renderer> renderer;
}
std::string VulkanReport(){
    VkInstance instance=VK_NULL_HANDLE;
    try{
        uint32_t loader=LoaderVersion();VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.pApplicationName="NovaPs5 capabilities";app.apiVersion=std::min(loader,VK_API_VERSION_1_3);VkInstanceCreateInfo create{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};create.pApplicationInfo=&app;Check(vkCreateInstance(&create,nullptr,&instance),"Create capability instance");
        uint32_t n=0;Check(vkEnumeratePhysicalDevices(instance,&n,nullptr),"Enumerate GPUs");if(!n)throw std::runtime_error("No Vulkan GPUs found");std::vector<VkPhysicalDevice> g(n);Check(vkEnumeratePhysicalDevices(instance,&n,g.data()),"Read GPUs");
        VkPhysicalDeviceProperties properties;vkGetPhysicalDeviceProperties(g[0],&properties);VkPhysicalDeviceFeatures basic;vkGetPhysicalDeviceFeatures(g[0],&basic);
        uint32_t queried_api=std::min(app.apiVersion,properties.apiVersion);VkPhysicalDeviceVulkan11Properties p11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_PROPERTIES};VkPhysicalDeviceSubgroupProperties subgroup{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};VkPhysicalDeviceSubgroupSizeControlProperties size{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_PROPERTIES};VkPhysicalDeviceProperties2 p2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};if(queried_api>=VK_API_VERSION_1_2)p2.pNext=&p11;else if(queried_api>=VK_API_VERSION_1_1)p2.pNext=&subgroup;if(queried_api>=VK_API_VERSION_1_3)p11.pNext=&size;
        VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};VkPhysicalDeviceVulkan13Features f13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};VkPhysicalDeviceFeatures2 f2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};if(queried_api>=VK_API_VERSION_1_2)f2.pNext=&f12;if(queried_api>=VK_API_VERSION_1_3)f12.pNext=&f13;
        if(app.apiVersion>=VK_API_VERSION_1_1){vkGetPhysicalDeviceFeatures2(g[0],&f2);vkGetPhysicalDeviceProperties2(g[0],&p2);}
        uint32_t en=0;Check(vkEnumerateDeviceExtensionProperties(g[0],nullptr,&en,nullptr),"Read extension count");std::vector<VkExtensionProperties> extensions(en);Check(vkEnumerateDeviceExtensionProperties(g[0],nullptr,&en,extensions.data()),"Read extensions");auto has=[&](const char* name){for(auto e:extensions)if(!std::strcmp(e.extensionName,name))return true;return false;};
        std::ostringstream out;out<<"{\"available\":true,\"gpu\":\""<<Escape(properties.deviceName)<<"\",\"vulkan\":\""<<Version(properties.apiVersion)<<"\",\"loader\":\""<<Version(loader)<<"\",\"vendorId\":"<<properties.vendorID<<",\"deviceId\":"<<properties.deviceID<<",\"driverVersion\":"<<properties.driverVersion<<",\"api13\":"<<(properties.apiVersion>=VK_API_VERSION_1_3?"true":"false")<<",\"shaderInt64\":"<<(basic.shaderInt64?"true":"false")<<",\"dualSrcBlend\":"<<(basic.dualSrcBlend?"true":"false")<<",\"geometryShader\":"<<(basic.geometryShader?"true":"false")<<",\"tessellationShader\":"<<(basic.tessellationShader?"true":"false")<<",\"dynamicRendering\":"<<(f13.dynamicRendering?"true":"false")<<",\"synchronization2\":"<<(f13.synchronization2?"true":"false")<<",\"bufferDeviceAddress\":"<<(f12.bufferDeviceAddress?"true":"false")<<",\"descriptorIndexing\":"<<(f12.descriptorIndexing?"true":"false")<<",\"shaderFloat16\":"<<(f12.shaderFloat16?"true":"false")<<",\"subgroupSize\":"<<(queried_api>=VK_API_VERSION_1_2?p11.subgroupSize:subgroup.subgroupSize)<<",\"minSubgroup\":"<<size.minSubgroupSize<<",\"maxSubgroup\":"<<size.maxSubgroupSize<<",\"subgroupSizeControl\":"<<(f13.subgroupSizeControl?"true":"false")<<",\"fragmentBarycentric\":"<<(has(VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME)?"true":"false")<<",\"meshShader\":"<<(has(VK_EXT_MESH_SHADER_EXTENSION_NAME)?"true":"false")<<",\"extensionCount\":"<<en<<",\"ps5Execution\":false}";
        vkDestroyInstance(instance,nullptr);return out.str();
    }catch(const std::exception& e){if(instance)vkDestroyInstance(instance,nullptr);return FailJson(e.what());}
}
void StartRenderer(ANativeWindow* window){std::lock_guard<std::mutex> l(lifecycle_mutex);renderer.reset();frames=0;Status("Starting Vulkan diagnostic");if(!window){Status("No Android surface available");return;}renderer=std::make_unique<Renderer>(window);Renderer* r=renderer.get();r->worker=std::thread([r]{r->Run();});}
void StopRenderer(){std::lock_guard<std::mutex> l(lifecycle_mutex);renderer.reset();}
std::string RendererStatus(){std::lock_guard<std::mutex> l(status_mutex);return status+"\nFrames presented: "+std::to_string(frames.load());}
void ResetPad(){std::lock_guard<std::mutex> l(pad_mutex);pad={};pad.left_stick_x=pad.left_stick_y=pad.right_stick_x=pad.right_stick_y=128;pad.orientation_w=1;pad.connected=true;pad.connected_count=1;}
void SetPad(uint32_t buttons,float lx,float ly,float rx,float ry,float l2,float r2,int touches,float tx,float ty){
    auto axis=[](float v){if(!std::isfinite(v))v=0;return static_cast<uint8_t>(std::lround((std::clamp(v,-1.f,1.f)+1.f)*127.5f));};auto trigger=[](float v){if(!std::isfinite(v))v=0;return static_cast<uint8_t>(std::lround(std::clamp(v,0.f,1.f)*255.f));};
    std::lock_guard<std::mutex> l(pad_mutex);pad.buttons=buttons|(l2>0?0x100:0)|(r2>0?0x200:0);pad.left_stick_x=axis(lx);pad.left_stick_y=axis(ly);pad.right_stick_x=axis(rx);pad.right_stick_y=axis(ry);pad.analog_buttons_l2=trigger(l2);pad.analog_buttons_r2=trigger(r2);pad.orientation_w=1;pad.connected=true;pad.connected_count=1;pad.timestamp=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();pad.touch_data.touch_num=touches?1:0;
    if(!std::isfinite(tx))tx=0;if(!std::isfinite(ty))ty=0;pad.touch_data.touch[0].x=static_cast<uint16_t>(std::clamp(tx,0.f,1.f)*1919);pad.touch_data.touch[0].y=static_cast<uint16_t>(std::clamp(ty,0.f,1.f)*941);pad.touch_data.touch[0].id=0;
}
std::string PadStatus(){std::lock_guard<std::mutex> l(pad_mutex);std::ostringstream s;s<<"Diagnostic input: "<<sizeof(pad)<<" bytes • buttons 0x"<<std::hex<<pad.buttons<<std::dec<<"\nL "<<int(pad.left_stick_x)<<","<<int(pad.left_stick_y)<<"   R "<<int(pad.right_stick_x)<<","<<int(pad.right_stick_y)<<"   L2 "<<int(pad.analog_buttons_l2)<<"  R2 "<<int(pad.analog_buttons_r2)<<"\nTouch points: "<<int(pad.touch_data.touch_num);return s.str();}
}
