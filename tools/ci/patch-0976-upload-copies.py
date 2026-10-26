#!/usr/bin/env python3
from pathlib import Path
import shutil,sys
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1])
p=root/'src/graphics/host_gpu/renderer/cache/bufferCache.cpp';s=p.read_text()
a=s.index('bool BufferCache::SynchronizeBuffer(');b=s.index('vk::Buffer BufferCache::UploadCopies(',a)
body=s[a:b]
for old,new in [
 ('copies.emplace_back(total_size, buffer.Offset(cursor), dirty_begin - cursor);','NovaRender::AppendUploadCopy(copies, total_size, buffer.Offset(cursor), dirty_begin - cursor);'),
 ('copies.emplace_back(total_size, buffer.Offset(cursor), end - cursor);','NovaRender::AppendUploadCopy(copies, total_size, buffer.Offset(cursor), end - cursor);')]:
 if body.count(old)!=1:raise SystemExit('0976: copy anchor changed; no files modified')
 body=body.replace(old,new)
s='#include "common/novaRender/UploadCopies.h"\n'+s[:a]+body+s[b:]
d=root/'src/common/novaRender';d.mkdir(parents=True,exist_ok=True)
shutil.copyfile(repo/'native/render/UploadCopies.h',d/'UploadCopies.h');p.write_text(s)
print('0976: adjacent upload copies merged; GPU-dirty gaps, bytes, barriers and ordering preserved')
