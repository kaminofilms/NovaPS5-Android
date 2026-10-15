#!/usr/bin/env python3
"""Compile the production archive template and exercise large shader vectors."""
from pathlib import Path
import subprocess
import tempfile

header = (Path(__file__).resolve().parents[1] / 'tools/ci/novaShaderDisk.h').read_text()
# Instantiate the production generic serializer without renderer dependencies.
start = header.index('template<class T> struct IsVector')
end = header.index('struct Entry')
archive = header[start:end]
archive = archive[:archive.index('        } else if constexpr (std::is_same_v<T,IR::BufferResource>)')] + '''
        } else { static_assert(sizeof(T)==0, "Unsupported test type"); }
    }
};
'''
program = '''
#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <type_traits>
#include <vector>
#include <cassert>
constexpr size_t Limit = 16u * 1024u * 1024u;
''' + archive + '''
int main() {
    std::vector<uint32_t> input(306511, 0x07230203u);
    Archive writer; writer.Fields(input); assert(writer.ok);
    Archive reader; reader.reading=true; reader.bytes=writer.bytes;
    std::vector<uint32_t> output; reader.Fields(output);
    assert(reader.ok && reader.cursor==reader.bytes.size() && output==input);
    reader=Archive{}; reader.reading=true; reader.bytes=writer.bytes;
    reader.bytes.pop_back(); reader.Fields(output); assert(!reader.ok);
    std::vector<uint32_t> too_large(Limit/4+1);
    Archive bounded; bounded.Fields(too_large); assert(!bounded.ok);
    Archive hostile; hostile.reading=true; hostile.bytes={255,255,255,255};
    hostile.Fields(output); assert(!hostile.ok);
}
'''
with tempfile.TemporaryDirectory() as d:
    source = Path(d)/'archive.cpp'; binary=Path(d)/'archive'
    source.write_text(program)
    subprocess.run(['g++','-std=c++20','-O2',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('NOVA_SHADER_ARCHIVE: large roundtrip, truncation, oversize and hostile length PASS')
