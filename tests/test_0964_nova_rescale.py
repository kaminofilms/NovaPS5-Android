#!/usr/bin/env python3
"""Host regressions and structural checks against the actually patched Kyty tree."""
from pathlib import Path
import os, subprocess, sys, tempfile

root=Path(sys.argv[1]).resolve()
repo=Path(__file__).resolve().parents[1]
def source(p): return (root/'src'/p).read_text()
image=source('graphics/host_gpu/renderer/image/image.cpp')
draw=source('graphics/host_gpu/renderer/renderDraw.cpp')
assert 'create.extent.width = NovaRescale::Dimension' in image
assert 'graphics->DeleteImage(*previous)' in image and 'DeferOperation([graphics,previous' in image
assert 'swap_image(*previous,backing)' in image
assert 'NovaNative("readback")' in image and 'NovaNative("upload")' in image
assert 'attachment-refresh-mismatch' in draw
assert draw.index('NovaRescale::Pending() = {}') < draw.index('auto* nova_pipeline =')
assert 'data[0]=image.info.extent.width' in draw
assert 'data[2]=image.backing.extent.width' in draw
pc=source('graphics/host_gpu/renderer/pipeline/pipelineCache.cpp')
assert 'static_params.nova_rescale = NovaRescale::Pending()' in pc
assert '":rescale64"' in pc
sh=source('graphics/host_gpu/renderer/pipeline/shaders.cpp')
assert '!NovaRescale::Enabled() && !rect_list' in sh
assert 'pSpecializationInfo=&nova_specs[slot]' in sh
emitter=source('graphics/shader/recompiler/backend/spirv/spirvEmitterImage.cpp')
assert 'NovaSpecializationU32' in emitter and 'Select(s,TypeU32(s),active,guest,result[axis])' in emitter
assert 'NovaImageCoordinate(ctx,mem,AddressU32' in emitter
assert 'nova_backing_scaled' in source('graphics/host_gpu/renderer/context.cpp')
assert (root/'src/common/novaRescale.h').read_bytes()==(repo/'native/novarescale/policy.h').read_bytes()

flags=['-std=c++20','-Wall','-Wextra','-Werror']
if os.environ.get('SANITIZE')=='1': flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp)
    def run(name, sources, includes):
        binary=t/name
        subprocess.run(['g++',*flags,*includes,*map(str,sources),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
    run('policy',[repo/'tests/test_0964_rescale_policy.cpp'],['-I'+str(repo)])
    # Test the real SPIR-V builder, replacing only unrelated platform macros.
    (t/'common').mkdir()
    (t/'common/common.h').write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\n#define KYTY_CLASS_DEFAULT_COPY(x)\n')
    (t/'common/assert.h').write_text('#pragma once\n#include <cstdlib>\n#define EXIT_IF(x) do{if(x)std::abort();}while(0)\n')
    spirv=Path(os.environ.get('NOVA_SPIRV_INCLUDE',str(root/'3rdparty/SPIRV-Headers/include')))
    run('specialization',[repo/'tests/test_0964_rescale_spec.cpp',root/'src/graphics/shader/recompiler/backend/spirv/SpirvBuilder.cpp'],
        ['-I'+str(t),'-I'+str(repo),'-I'+str(root/'src'),'-I'+str(spirv)])
print('Nova rescale: extent/policy, distinct SPIR-V specialization identities, integration checks passed')
