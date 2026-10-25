#!/usr/bin/env python3
"""Narrow upload memory dependencies; preserve stages, accesses and pass endings."""
from pathlib import Path
import shutil, sys
repo = Path(__file__).resolve().parents[2]
root = Path(sys.argv[1])
p = root / 'src/graphics/host_gpu/renderer/cache/bufferCache.cpp'
s = p.read_text()
start = s.index('bool BufferCache::SynchronizeBuffer(')
end = s.index('vk::Buffer BufferCache::UploadCopies(', start)
body = s[start:end]
old = '\t\tbefore.offset              = 0;\n\t\tbefore.size                = buffer.Size();'
if body.count(old) != 1:
    raise SystemExit('0974 upload: anchor changed; no files modified')
new = '''\t\tconst auto upload_range = NovaRender::UploadDestinationRange(copies, buffer.Size());
\t\tbefore.offset              = upload_range.offset;
\t\tbefore.size                = upload_range.size;'''
body = body.replace(old, new)
s = '#include "common/novaRender/UploadRange.h"\n' + s[:start] + body + s[end:]
(root / 'src/common/novaRender').mkdir(parents=True, exist_ok=True)
shutil.copyfile(repo / 'native/render/UploadRange.h', root / 'src/common/novaRender/UploadRange.h')
p.write_text(s)
print('NOVA_0974: buffer upload dependencies bounded to copied destination span')
