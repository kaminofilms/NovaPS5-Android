#!/usr/bin/env python3
"""Verify the pinned Android compute-mesh driver, alone or inside the APK.

These are packaging checks, not proof of Vulkan feature advertisement on hardware.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

EXPECTED = '4893e09fef65271c434965cb8d5380a783115ca9c481cce8dfb81ae8f7395efc'


def verify(path):
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if 'AndroidManifest.xml' in archive.namelist():
            raw = archive.read('assets/drivers/turnip-a8xx.zip')
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('bundled driver checksum differs from the reviewed A8xx build')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        meta = json.loads(archive.read('meta.json'))
        if meta['name'] != 'Mesa Turnip v26.3.0-20261012-A8xx':
            raise ValueError('unexpected driver metadata')
        lib = archive.read(meta['libraryName'])
    if lib[:6] != b'\x7fELF\x02\x01' or lib[18:20] != b'\xb7\x00':
        raise ValueError('driver must be little-endian AArch64 ELF64')
    offset, = struct.unpack_from('<Q', lib, 32)
    entry_size, count = struct.unpack_from('<HH', lib, 54)
    loads = []
    for i in range(count):
        header = struct.unpack_from('<IIQQQQQQ', lib, offset + i * entry_size)
        if header[0] == 1:
            loads.append(header)
    if not loads or any(h[7] < 16384 or h[2] % 16384 != h[3] % 16384 for h in loads):
        raise ValueError('driver is not 16 KB page compatible')
    for token in (b'VK_EXT_mesh_shader', b'Uses mesh shaders', b'tu_mesh_vs',
                  b'load_mesh_ring_ir3', b'tu_mesh_setup'):
        if token not in lib:
            raise ValueError('compute mesh implementation missing: ' + repr(token))
    if b'GLIBC_' in lib:
        raise ValueError('Linux/glibc driver cannot load through Android adrenotools')
    print('NOVA_MESH_DRIVER: PASS checksum, metadata, Android AArch64, 16 KB alignment, compute mesh code')


if __name__ == '__main__':
    verify(sys.argv[1])
