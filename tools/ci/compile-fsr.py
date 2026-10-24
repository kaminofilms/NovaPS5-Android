#!/usr/bin/env python3
"""Compile the AMD FSR1 shaders used by the native presentation pass."""
from pathlib import Path
import subprocess,struct,tempfile,hashlib,urllib.request
repo=Path(__file__).resolve().parents[2];root=repo/'native/upscale'
commit=(root/'vendor/UPSTREAM_COMMIT').read_text().strip()
expected={'ffx_a.h':'f60e2722fcd13989523b9164d776ab382b3692791767f3bf8bb19967f763f3fb',
          'ffx_fsr1.h':'93c3922362ea7fc99cbcc698ca30c98de4f8c246d1fbb0b09e015ddef38ce3a5'}
for name,digest in expected.items():
 p=root/'vendor'/name
 if not p.exists():
  url='https://raw.githubusercontent.com/GPUOpen-Effects/FidelityFX-FSR/'+commit+'/ffx-fsr/'+name
  p.write_bytes(urllib.request.urlopen(url,timeout=60).read())
 if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise SystemExit('AMD FSR1 header checksum mismatch: '+name)
header=['// Generated from fsr_easu.comp/fsr_rcas.comp with AMD FSR1 MIT headers.','#pragma once','#include <cstdint>','namespace NovaUpscale {']
with tempfile.TemporaryDirectory() as td:
 for name in ['easu','rcas']:
  binary=Path(td)/(name+'.spv')
  subprocess.run(['glslangValidator','-V','--target-env','vulkan1.1','-I'+str(root),str(root/('fsr_'+name+'.comp')),'-o',str(binary)],check=True)
  subprocess.run(['spirv-val','--target-env','vulkan1.1',str(binary)],check=True)
  data=binary.read_bytes();words=struct.unpack('<'+'I'*(len(data)//4),data)
  header.append('inline constexpr uint32_t '+name+'Shader[]={'+','.join(hex(w) for w in words)+'};')
header.append('}')
(root/'fsr_shaders.h').write_text('\n'.join(header)+'\n')
print('PASS compiled EASU + RCAS and SPIR-V Vulkan 1.1 validation')
