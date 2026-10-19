#!/usr/bin/env python3
from pathlib import Path
import subprocess,sys
root=Path(sys.argv[1]);patch=Path(__file__).resolve().parents[2]/'patches/kyty-raster-resolution.patch'
subprocess.run(['git','apply','--check',str(patch)],cwd=root,check=True)
subprocess.run(['git','apply',str(patch)],cwd=root,check=True)
print('Nova raster scale: eligible 1080p color+depth proxies, native-space fragment coordinates, native-sized compute/readback')
