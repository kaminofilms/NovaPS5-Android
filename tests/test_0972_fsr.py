#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile
repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 out=Path(td)/'fsr'
 subprocess.run(['c++','-std=c++20','-O1','-DVULKAN_HPP_DISPATCH_LOADER_DYNAMIC=1','-DVULKAN_HPP_NO_EXCEPTIONS','-I'+str(repo/'native/upscale'),str(repo/'tests/test_0972_fsr_vulkan.cpp'),'-lvulkan','-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
