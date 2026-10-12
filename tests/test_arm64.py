#!/usr/bin/env python3
"""Independently execute emitted ARM64 blocks using Unicorn, against x86-64."""
import pathlib,struct,subprocess,tempfile
from unicorn import Uc,UC_ARCH_ARM64,UC_ARCH_X86,UC_MODE_64,UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_LR
from unicorn.x86_const import UC_X86_REG_RAX,UC_X86_REG_RSP
root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 binary=pathlib.Path(d)/'native-tests'
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O2','-I'+str(root/'native'),str(root/'tests/native_tests.cpp'),str(root/'native/cpu_block.cpp'),str(root/'native/probe.cpp'),'-o',str(binary)],check=True)
 result=subprocess.run([str(binary)],capture_output=True,text=True,check=True)
 print(result.stderr.strip())
 lines=result.stdout.splitlines()
 for line in lines:
  expected,guest,emitted=line.split();expected=int(expected,16);x86=bytes.fromhex(guest)
  words=[int(emitted[i:i+8],16) for i in range(0,len(emitted),8)];arm=struct.pack('<'+'I'*len(words),*words)
  a=Uc(UC_ARCH_ARM64,UC_MODE_ARM);a.mem_map(0x10000,0x10000);a.mem_write(0x10000,arm);a.reg_write(UC_ARM64_REG_LR,0x18000);a.emu_start(0x10000,0x18000,count=1024);assert a.reg_read(UC_ARM64_REG_X0)==expected
  x=Uc(UC_ARCH_X86,UC_MODE_64);x.mem_map(0x10000,0x10000);x.mem_write(0x10000,x86);x.reg_write(UC_X86_REG_RSP,0x1f000);x.mem_write(0x1f000,struct.pack('<Q',0x18000));x.emu_start(0x10000,0x10000+len(x86)-1,count=1024);assert x.reg_read(UC_X86_REG_RAX)==expected
 print(f'PASS: {len(lines)} ARM64 integer blocks agree with independent x86-64 arithmetic; RET is the test boundary')
