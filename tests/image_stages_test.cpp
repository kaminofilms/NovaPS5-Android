#include "ImageStages.h"
#include <cassert>
#include <iostream>
int main(){
 using NovaRender::ImageStages;
 assert(ImageStages(VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT)==VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT);
 assert(ImageStages(VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_READ_BIT)==(VK_PIPELINE_STAGE_2_EARLY_FRAGMENT_TESTS_BIT|VK_PIPELINE_STAGE_2_LATE_FRAGMENT_TESTS_BIT));
 assert(ImageStages(VK_ACCESS_2_TRANSFER_READ_BIT)==VK_PIPELINE_STAGE_2_ALL_TRANSFER_BIT);
 assert(ImageStages(VK_ACCESS_2_SHADER_SAMPLED_READ_BIT)==(VK_PIPELINE_STAGE_2_ALL_GRAPHICS_BIT|VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT));
 assert(ImageStages(VK_ACCESS_2_INPUT_ATTACHMENT_READ_BIT)==VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT);
 assert(ImageStages(VK_ACCESS_2_HOST_WRITE_BIT)==VK_PIPELINE_STAGE_2_HOST_BIT);
 assert(ImageStages(0)==VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT);
 assert(ImageStages(VK_ACCESS_2_MEMORY_WRITE_BIT)==VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT);
 assert(ImageStages(VkAccessFlags2{1}<<63)==VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT);
 const VkAccessFlags2 bits[]={VK_ACCESS_2_TRANSFER_READ_BIT,VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT,VK_ACCESS_2_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT,VK_ACCESS_2_HOST_READ_BIT,VK_ACCESS_2_INPUT_ATTACHMENT_READ_BIT};
 for(unsigned mask=1;mask<64;mask++){
  VkAccessFlags2 access=0;VkPipelineStageFlags2 expected=0;
  for(unsigned bit=0;bit<6;bit++)if(mask&(1u<<bit)){access|=bits[bit];expected|=ImageStages(bits[bit]);}
  assert(ImageStages(access)==expected);
 }
 std::cout<<"PASS fixed-function, shader, host, mixed and unknown image accesses\n";
}
