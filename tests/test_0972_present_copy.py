#!/usr/bin/env python3
"""Execute production prepared-frame copies/resizing, including sRGB bit preservation."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1];core=Path(sys.argv[1]).resolve()
source=(core/'src/graphics/presentation/window/swapchain.cpp').read_text()
methods=source[source.index('void Presenter::Frame::Transit('):source.index('void Presenter::Frame::Clear(')]
base=(repo/'tests/test_0972_fsr_vulkan.cpp').read_text()
base=base[:base.index(' NovaUpscale::State state;')]
base=base.replace('VK_API_VERSION_1_1','VK_API_VERSION_1_3')
base=base.replace('vk::Device d;Ok(p.createDevice', 'vk::PhysicalDeviceVulkan13Features f13{};f13.synchronization2=VK_TRUE;di.pNext=&f13;\n vk::Device d;Ok(p.createDevice')
harness=r'''
#include <optional>
struct VulkanImage {vk::Image image{};vk::DeviceMemory memory{};vk::Extent3D extent{};vk::Format format{};unsigned layers=1;
 struct State{vk::PipelineStageFlags2 pl_stage{};vk::AccessFlags2 access_mask{};vk::ImageLayout layout=vk::ImageLayout::eUndefined;}state;
 std::vector<int> subresource_states;
};
struct GraphicContext{vk::Device device;vk::PhysicalDevice physical;vk::PhysicalDeviceMemoryProperties memory;
 auto GetFormatProperties(vk::Format f){return physical.getFormatProperties(f);}
 bool CreateImage(const vk::ImageCreateInfo& ci,VulkanImage& image){
  if(device.createImage(&ci,nullptr,&image.image)!=vk::Result::eSuccess)return false;
  auto r=device.getImageMemoryRequirements(image.image);vk::MemoryAllocateInfo ai{r.size,Type(memory,r.memoryTypeBits,vk::MemoryPropertyFlagBits::eDeviceLocal)};
  Ok(device.allocateMemory(&ai,nullptr,&image.memory));Ok(device.bindImageMemory(image.image,image.memory,0));
  image.extent=ci.extent;image.format=ci.format;image.layers=ci.arrayLayers;return true;
 }
 void DeleteImage(VulkanImage& i){if(i.image)device.destroyImage(i.image);if(i.memory)device.freeMemory(i.memory);i={};}
};
struct CommandBuffer{vk::CommandBuffer command;GraphicContext& graphics;void EndRendering(){}auto Handle(){return command;}auto& GetGraphics(){return graphics;}};
struct Image{VulkanImage backing;void Transit(vk::ImageLayout,vk::AccessFlags2,std::optional<int>,vk::CommandBuffer);};
struct Presenter{struct Frame{VulkanImage image,resample;void Transit(vk::CommandBuffer,vk::ImageLayout,vk::AccessFlags2);void CopyFrom(CommandBuffer&,Image&);};};
#define EXIT_IF(x) assert(!(x))
#define EXIT(...) std::abort()
'''+methods+r'''
void Image::Transit(vk::ImageLayout l,vk::AccessFlags2 a,std::optional<int>,vk::CommandBuffer c){Presenter::Frame f;f.image=backing;f.Transit(c,l,a);backing.state=f.image.state;}
'''
base=base.replace('int main(){',harness+'\nint main(){')
test=r'''
 GraphicContext g{d,p,memory};CommandBuffer buffer{cmd,g};
 for(bool srgb:{false,true})for(unsigned height:{1080u,720u,540u,360u}){
  const unsigned width=height*16/9;Image source;Presenter::Frame frame;
  vk::ImageCreateInfo ci{};ci.imageType=vk::ImageType::e2D;ci.format=srgb?vk::Format::eR8G8B8A8Srgb:vk::Format::eR8G8B8A8Unorm;ci.extent=vk::Extent3D{1920,1080,1};ci.mipLevels=ci.arrayLayers=1;ci.samples=vk::SampleCountFlagBits::e1;ci.tiling=vk::ImageTiling::eOptimal;ci.usage=vk::ImageUsageFlagBits::eTransferSrc|vk::ImageUsageFlagBits::eTransferDst;
  assert(g.CreateImage(ci,source.backing));ci.format=vk::Format::eR8G8B8A8Unorm;ci.extent=vk::Extent3D{width,height,1};assert(g.CreateImage(ci,frame.image));
  auto upload=Allocate(d,memory,1920*1080*4,vk::BufferUsageFlagBits::eTransferSrc),read=Allocate(d,memory,width*height*4+64,vk::BufferUsageFlagBits::eTransferDst);
  for(unsigned reuse=0;reuse<3;reuse++){
   auto* in=static_cast<uint8_t*>(upload.mapped);for(unsigned i=0;i<1920*1080;i++){in[i*4]=128;in[i*4+1]=64;in[i*4+2]=reuse?33:192;in[i*4+3]=255;}std::memset(read.mapped,0x6c,read.bytes);
   Ok(cmd.reset());Ok(cmd.begin(vk::CommandBufferBeginInfo{vk::CommandBufferUsageFlagBits::eOneTimeSubmit}));source.Transit(vk::ImageLayout::eTransferDstOptimal,vk::AccessFlagBits2::eTransferWrite,{},cmd);
   vk::BufferImageCopy copy{};copy.imageSubresource={vk::ImageAspectFlagBits::eColor,0,0,1};copy.imageExtent=source.backing.extent;cmd.copyBufferToImage(upload.buffer,source.backing.image,vk::ImageLayout::eTransferDstOptimal,1,&copy);
   frame.CopyFrom(buffer,source);frame.Transit(cmd,vk::ImageLayout::eTransferSrcOptimal,vk::AccessFlagBits2::eTransferRead);copy.imageExtent=frame.image.extent;cmd.copyImageToBuffer(frame.image.image,vk::ImageLayout::eTransferSrcOptimal,read.buffer,1,&copy);
   vk::MemoryBarrier host{};host.srcAccessMask=vk::AccessFlagBits::eTransferWrite;host.dstAccessMask=vk::AccessFlagBits::eHostRead;cmd.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,vk::PipelineStageFlagBits::eHost,{},1,&host,0,nullptr,0,nullptr);
   Ok(cmd.end());vk::SubmitInfo submit{};submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;Ok(queue.submit(1,&submit,nullptr));Ok(queue.waitIdle());
   const auto* out=static_cast<const uint8_t*>(read.mapped);for(unsigned i=0;i<width*height;i++){assert(std::abs(int(out[i*4])-128)<=1);assert(std::abs(int(out[i*4+1])-64)<=1);assert(std::abs(int(out[i*4+2])-(reuse?33:192))<=1);assert(out[i*4+3]==255);}for(size_t i=width*height*4;i<read.bytes;i++)assert(out[i]==0x6c);
  }
  Free(d,upload);Free(d,read);g.DeleteImage(source.backing);g.DeleteImage(frame.image);g.DeleteImage(frame.resample);
 }
 Ok(d.waitIdle());d.destroyCommandPool(pool);d.destroy();instance.destroyDebugUtilsMessengerEXT(messenger);instance.destroy();assert(errors==0);
 std::cout<<"PASS production presentation copy: native/720/540/360, sRGB/UNORM preserved, repeated copies, bounds, zero Vulkan synchronization errors\n";
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.cpp').write_text(base+test)
 subprocess.run(['c++','-std=c++20','-O1','-DVULKAN_HPP_DISPATCH_LOADER_DYNAMIC=1','-DVULKAN_HPP_NO_EXCEPTIONS','-I'+str(repo/'native/upscale'),str(p/'test.cpp'),'-lvulkan','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
