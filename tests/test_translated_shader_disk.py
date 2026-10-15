from pathlib import Path
import re,subprocess,sys,tempfile
p=Path('work') if len(sys.argv)==1 else Path(tempfile.mkdtemp(prefix='nova-cache-test-'))
if len(sys.argv)>1:
    source=Path(sys.argv[1])/'src'
    ir=(source/'graphics/shader/recompiler/ir/ShaderIR.h').read_text()
    spec=(source/'graphics/shader/recompiler/ir/passes/ResourceMaterialization.h').read_text()
    (p/'novaShaderDisk.h').write_text((source/'graphics/host_gpu/renderer/pipeline/novaShaderDisk.h').read_text())
else:
    ir=(p/'ShaderIR.h').read_text(); spec=(p/'ResourceMaterialization.h').read_text()
def block(name,kind='struct',source=ir):
    start=source.index(kind+' '+name+' {'); end=source.index('\n};',start)+3
    return source[start:end]
prefix='''#include <array>
#include <vector>
#include <string>
#include <cstdint>
#include <cstddef>
#include <cassert>
namespace Prospero { enum class BufferFormat { kInvalid }; enum class TextureNumericClass { Unsupported }; }
namespace Decoder { enum class ImageDimension {Unknown}; }
namespace Libs::Graphics {
enum class ShaderType {Unknown,Vertex,Pixel,Compute};
enum class ImageResourceClass {None};
constexpr uint32_t DstSel(uint32_t x,uint32_t y,uint32_t z,uint32_t w){return x|(y<<3)|(z<<6)|(w<<9);}
constexpr uint32_t ShaderImageIdentitySwizzle=0xfac;
namespace ShaderRecompiler::IR {
struct PushData { static constexpr uint32_t NoStart=UINT32_MAX; };
'''
for name in ['StageInputKind','StageOutputKind','ImageMipMode','DescriptorBindingKind']:
    start=ir.index('enum class '+name);end=ir.index('};',start)+2
    prefix+=ir[start:end]+'\n'
prefix+='inline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;\n'
# Enum values above refer to these constants, so put them before enums.
prefix=prefix.replace('namespace ShaderRecompiler::IR {','namespace ShaderRecompiler::IR {\ninline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;').replace('\ninline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;\n#','\n#')
prefix=prefix[:prefix.rfind('inline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;')]+prefix[prefix.rfind('inline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;')+len('inline constexpr uint32_t FirstImageBinding=1, ImageBindingCount=48;'):]
for name in ['BufferResource','ImageResource','SamplerResource','SampledResourcePair','StageInput','StageOutput','Bindings','ShaderInfo','CompiledShaderInfo']:
    prefix+=block(name)+'\n'
prefix+=block('ResourceSpecialization',source=spec)+'\n}}\n'
(p/'xxhash.h').write_text('''#pragma once
#include <cstdint>
#include <cstddef>
extern "C" uint64_t XXH3_64bits(const void* data,size_t size);
''')
main='''
#include "novaShaderDisk.h"
using namespace Libs::Graphics;
int main(){
namespace D=NovaShaderDisk;
D::Entry original; original.info.stage=ShaderType::Vertex;
original.info.info.buffers.resize(2); original.info.info.buffers[0].indirect_resources={1,2,3};
original.info.info.images.resize(1); original.info.info.samplers.resize(1);
original.info.info.inputs.resize(1);original.info.info.inputs[0].debug_name="position";
original.info.info.outputs.resize(1);original.info.info.outputs[0].debug_name="output";
original.info.bindings.descriptor_counts[0]=19; original.info.bindings.push_data_start_dword=4;
original.spirv={0x07230203,0x10000,0,6,0,42};
auto dir=std::filesystem::temp_directory_path()/"nova-shader-roundtrip";std::filesystem::remove_all(dir);
std::vector<uint8_t> key={1,3,5,7};D::Store(dir,key,original);
D::Entry loaded;assert(D::Load(dir,key,loaded));
assert(loaded.info.info==original.info.info);assert(loaded.info.bindings==original.info.bindings);assert(loaded.spirv==original.spirv);
auto path=D::File(dir,key);std::ifstream in(path,std::ios::binary);std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)),{});in.close();
for(size_t n=0;n<data.size();++n){std::ofstream f(path,std::ios::binary|std::ios::trunc);f.write((char*)data.data(),n);f.close();assert(!D::Load(dir,key,loaded));}
for(size_t i=0;i<data.size();++i){auto bad=data;bad[i]^=0x80;std::ofstream f(path,std::ios::binary|std::ios::trunc);f.write((char*)bad.data(),bad.size());f.close();assert(!D::Load(dir,key,loaded));}
std::filesystem::remove_all(dir);std::puts("Shader metadata roundtrip, every truncation, and every single-byte corruption: PASS");
}
'''
(p/'disk-test.cpp').write_text(prefix+main)
subprocess.run(['c++','-std=c++20','-O1','-fsanitize=undefined','-I'+str(p),str(p/'disk-test.cpp'),'-l:libxxhash.so.0','-o',str(p/'disk-test')],check=True)
subprocess.run([str(p/'disk-test')],check=True)
