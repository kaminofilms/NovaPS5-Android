#!/usr/bin/env python3
"""Compile and exercise the mesh subgroup selector from the patched renderer."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve() / 'src'
program = r'''
#include "graphics/host_gpu/renderer/pipeline/meshWorkgroup.h"
#include <cassert>
#include <set>
using Libs::Graphics::SelectMeshSubgroup;
int main() {
    // PPSA31162: three guest wave64s fit in three host wave32s.
    static_assert(SelectMeshSubgroup(64, 64, 192, 128, 128, true) == 32);
    static_assert(SelectMeshSubgroup(64, 64, 128, 128, 128, true) == 64);
    static_assert(SelectMeshSubgroup(64, 64, 256, 128, 128, true) == 32);
    // No unsupported feature/limit bypass, including the per-axis limit.
    static_assert(SelectMeshSubgroup(64, 64, 192, 128, 128, false) == 64);
    static_assert(SelectMeshSubgroup(64, 64, 192, 128, 64, true) == 64);
    static_assert(SelectMeshSubgroup(64, 64, 257, 128, 128, true) == 64);
    static_assert(SelectMeshSubgroup(64, 32, 192, 128, 128, true) == 64);
    static_assert(SelectMeshSubgroup(32, 64, 192, 128, 128, false) == 32);
    for (unsigned guest : {192u, 256u}) {
        auto width = SelectMeshSubgroup(64, 64, guest, 128, 128, true);
        unsigned host = (guest + 63u) / 64u * width;
        assert(host <= 128);
        std::set<unsigned> lanes;
        for (unsigned i = 0; i < host; ++i)
            for (unsigned half = 0; half < 2; ++half)
                assert(lanes.insert(i + (i & ~31u) + half * 32).second);
        assert(lanes.size() == guest);
        assert(*lanes.begin() == 0 && *lanes.rbegin() == guest - 1);
    }
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)
    (path / 'test.cpp').write_text(program)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I', str(source),
                    str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('NOVA_MESH_WORKGROUP: PASS selection, limits, and guest lane coverage')
