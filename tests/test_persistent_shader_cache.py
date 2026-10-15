#!/usr/bin/env python3
"""Guard the real compiled NovaPS5 0.9.26 Vulkan-cache and guest-metadata changes.

Android game process is forcibly killed on "Exit game"; caching only in the
PipelineCache destructor never writes a warmup cache. Snapshot writes must
retain the live Vulkan handle and use per-game/version/driver validation.
"""
from pathlib import Path
import re
import sys

repo = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1])
src = (root / "src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp").read_text()
hdr = (root / "src/graphics/host_gpu/renderer/pipeline/pipelineCache.h").read_text()
vert = (root / "src/graphics/shader/shaderVertexMetadata.cpp").read_text()
java = (repo / "nova-android/src/com/kaminofilms/novaps5/GameActivity.java").read_text()

def once(s, pattern, name):
    matches = re.findall(re.escape(pattern), s)
    assert len(matches) == 1, f"{name}: expected exactly one, got {len(matches)}"

once(src, 'return fmt::format("NovaPC26:{}:', "render-version driver signature")
for tok in ('properties.pipelineCacheUUID', 'properties.vendorID', 'properties.deviceID',
            'properties.driverVersion', 'KYTY_GIT_REVISION'):
    assert tok in src, f"missing driver cache validation: {tok}"
# Nova's pinned base patch already removes the upstream dirty-build gate.
assert 'if (git_hash.ends_with("-dirty"))' not in src, "dirty source still blocks cache"
assert 'm_driver_cache_path     = std::filesystem::path("_PipelineCache") / (title_id + ".bin");' in src
assert 'std::getenv("NOVA_CACHE_TITLE_ID")' in src, "missing title fallback"
assert 'Os.setenv("NOVA_CACHE_TITLE_ID", cacheTitleId, true);' in java
assert 'cacheTitleId.matches("[A-Za-z0-9_-]{3,48}")' in java
assert 'void Save(bool preserve_cache = false);' in hdr
once(src, "void PipelineCache::Save(bool preserve_cache) {", "snapshot method")
once(src, "if (!preserve_cache) {\n\t\tm_graphics.device.destroyPipelineCache(", "normal shutdown still closes cache")
assert "Common::File::RenameFile(temp_path, m_driver_cache_path)" in src, "atomic cache write lost"
assert "XXH3_64bits(payload.data(), payload.size())" in src, "cache integrity lost"
assert 'if (nova_count == 1u || nova_count == 16u || (nova_count > 16u && nova_count % 64u == 0u))' in src
assert src.count("Save(true);") == 2, "missing graphics or compute pipeline snapshot"
for name in ["m_graphics_pipelines.emplace", "m_compute_pipelines.emplace"]:
    i = src.index(name)
    j = src.index("return *iter->second;", i)
    assert "Save(true);" in src[i:j], f"new {name} path fails to save warmup"
assert "std::memcpy(&user_data, GuestMemory::Ptr(data.user_data, sizeof(user_data))" in vert
assert "GuestMemory::Ptr(user_data.direct_resource_offset, direct_size)" in vert
assert "#include \"common/guestMemory.h\"" in vert
assert "#if defined(KYTY_NOVA_FEX)" in vert
print("PASS 0.9.26 Vulkan per-title signed cache, live snapshot, shader metadata guest alias invariants")
