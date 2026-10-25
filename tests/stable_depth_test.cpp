#include "StableDepth.h"
#include <cassert>
#include <iostream>
int main(){
 using NovaRender::StableDepthLayout;
 constexpr auto ds=VK_IMAGE_ASPECT_DEPTH_BIT|VK_IMAGE_ASPECT_STENCIL_BIT;
 constexpr auto writable=VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
 constexpr VkImageLayout requested[]={writable,VK_IMAGE_LAYOUT_DEPTH_STENCIL_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_STENCIL_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_STENCIL_ATTACHMENT_OPTIMAL};
 for(auto r:requested){
  assert(StableDepthLayout(writable,r,ds,false,false,true)==writable);
  for(unsigned guards=1;guards<8;guards++)assert(StableDepthLayout(writable,r,ds,guards&1,guards&2,!(guards&4))==r);
 }
 assert(StableDepthLayout(VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_OPTIMAL,VK_IMAGE_ASPECT_DEPTH_BIT,false,false,true)==VK_IMAGE_LAYOUT_DEPTH_ATTACHMENT_OPTIMAL);
 assert(StableDepthLayout(VK_IMAGE_LAYOUT_STENCIL_ATTACHMENT_OPTIMAL,VK_IMAGE_LAYOUT_STENCIL_READ_ONLY_OPTIMAL,VK_IMAGE_ASPECT_STENCIL_BIT,false,false,true)==VK_IMAGE_LAYOUT_STENCIL_ATTACHMENT_OPTIMAL);
 for(auto r:requested){
  for(auto unsafe:{VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,VK_IMAGE_LAYOUT_GENERAL})assert(StableDepthLayout(unsafe,r,ds,false,false,true)==r);
  assert(StableDepthLayout(writable,r,VK_IMAGE_ASPECT_COLOR_BIT,false,false,true)==r);
 }
 // A depth-write draw followed by test-only draws need no layout oscillation.
 auto state=writable;unsigned original_changes=0,new_changes=0;auto original=writable;
 for(int i=0;i<1000;i++){
  auto r=requested[i%4];original_changes+=r!=original;original=r;
  auto next=StableDepthLayout(state,r,ds,false,false,true);new_changes+=next!=state;state=next;
 }
 assert(original_changes==999&&new_changes==0);
 // Sampling is a hard boundary; the helper must preserve that real transition.
 assert(StableDepthLayout(state,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,ds,true,false,true)==VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);
 std::cout<<"PASS depth/stencil layouts, sampled/bound/partial guards, 1000 alternating draws, sampling boundary\n";
}
