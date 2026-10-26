#include "native/render/ReadOnlyDepth.h"
#include <cassert>
#include <array>
int main(){
 for(uint32_t api:{VK_API_VERSION_1_2,VK_API_VERSION_1_3,VK_API_VERSION_1_4})
 for(bool scaled:{false,true})for(VkImageAspectFlags writes:std::array<VkImageAspectFlags,4>{0u,VK_IMAGE_ASPECT_DEPTH_BIT,VK_IMAGE_ASPECT_STENCIL_BIT,VK_IMAGE_ASPECT_DEPTH_BIT|VK_IMAGE_ASPECT_STENCIL_BIT})
 for(bool depthClear:{false,true})for(bool stencilClear:{false,true}){
 const bool wanted=api>=VK_API_VERSION_1_3&&!scaled&&!writes&&!depthClear&&!stencilClear;
 assert(NovaRender::CanOmitDepthStore(api,scaled,writes,depthClear,stencilClear)==wanted);
 }
}
