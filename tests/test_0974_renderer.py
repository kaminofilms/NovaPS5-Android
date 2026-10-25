#!/usr/bin/env python3
"""Host regression checks and compile the actual patched Image::Transit body."""
from pathlib import Path
import os,subprocess,sys,tempfile
repo=Path(__file__).resolve().parents[1];root=Path(sys.argv[1]).resolve()
compiler=os.environ.get('CXX','c++')
includes=['-I',str(root/'3rdparty/Vulkan-Headers/include'),'-I',str(repo/'native/render')]
with tempfile.TemporaryDirectory() as td:
 t=Path(td)
 exe=t/'stages'
 subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',*includes,str(repo/'tests/image_stages_test.cpp'),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
 source=(root/'src/graphics/host_gpu/renderer/image/image.cpp').read_text()
 start=source.index('void Image::Transit(');end=source.index('\nvoid Image::Upload(',start)
 body=source[start:end]
 assert 'NovaRender::ImageStages' in body
 assert 'GetBarriers(destination_layout, destination_access, destination_stage, range)' in body
 assert body.index('if (barriers.empty())')<body.index('m_scheduler.EndRendering()')
 fixture='''#include <vulkan/vulkan.hpp>
#include "ImageStages.h"
#include <optional>
#include <vector>
struct ImageSubresourceRange {};
struct Scheduler {void EndRendering();};
struct Image {
 Scheduler m_scheduler;
 std::vector<vk::ImageMemoryBarrier2> GetBarriers(vk::ImageLayout,vk::AccessFlags2,vk::PipelineStageFlags2,std::optional<ImageSubresourceRange>);
 void Transit(vk::ImageLayout,vk::AccessFlags2,std::optional<ImageSubresourceRange>,vk::CommandBuffer);
};
'''+body
 (t/'transit.cpp').write_text(fixture)
 subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-Werror',*includes,'-c',str(t/'transit.cpp'),'-o',str(t/'transit.o')],check=True)
print('PASS actual Image::Transit body compiles with pinned Vulkan-Hpp headers; hazards preserved')
