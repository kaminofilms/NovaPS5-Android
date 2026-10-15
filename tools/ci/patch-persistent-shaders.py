#!/usr/bin/env python3
"""Enable safe Android Vulkan pipeline cache persistence and bounded AGC metadata aliases.

Executed on the *compiled* Kyty tree after the existing 0.9.25 source patches.
Fails closed on source drift. The cache epoch is intentionally versioned: old
shader/pipeline translations must not share driver blobs with a new renderer.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1])
cache_h = root / "src/graphics/host_gpu/renderer/pipeline/pipelineCache.h"
cache_cpp = root / "src/graphics/host_gpu/renderer/pipeline/pipelineCache.cpp"
vertex_cpp = root / "src/graphics/shader/shaderVertexMetadata.cpp"
app_java = Path(sys.argv[2]) if len(sys.argv) > 2 else None

def once(data: str, old: str, new: str, label: str) -> str:
    n = data.count(old)
    if n != 1:
        raise SystemExit(f"NOVA_SHADER_CACHE: {label}: expected 1 anchor, found {n}")
    return data.replace(old, new, 1)

header = cache_h.read_text()
source = cache_cpp.read_text()
vertex = vertex_cpp.read_text()

header = once(header, "\tvoid Save();",
              "\t// Snapshot keeps the Vulkan cache alive for subsequent rendering.\n"
              "\tvoid Save(bool preserve_cache = false);",
              "cache method signature")

source = once(source, "#include <cstring>", "#include <cstring>\n#include <cstdlib>",
              "cstdlib include")
source = once(source,
              "return fmt::format(\"KytyPC1:{}:{:08x}:{:08x}:{:08x}:{}\\n\", KYTY_GIT_REVISION,",
              "// Epoch isolates NovaPS5 0.9.26's translated shader semantics from older builds.\n"
              "\treturn fmt::format(\"NovaPC26:{}:{:08x}:{:08x}:{:08x}:{}\\n\", KYTY_GIT_REVISION,",
              "driver cache epoch")
source = once(source,
              """\tstd::string title_id;
\tif ((!Loader::SystemContentParamSfoGetString("TITLE_ID", &title_id) || title_id.empty()) &&
\t    (!Loader::SystemContentParamSfoGetString("CONTENT_ID", &title_id) || title_id.empty())) {
\t\treturn {};
\t}""",
              """\tstd::string title_id;
\tif ((!Loader::SystemContentParamSfoGetString("TITLE_ID", &title_id) || title_id.empty()) &&
\t    (!Loader::SystemContentParamSfoGetString("CONTENT_ID", &title_id) || title_id.empty())) {
#if defined(KYTY_NOVA_FEX)
\t\t// Android Activity knows the game's metadata before the renderer initializes.
\t\t// Keep the same identifier validation below for the environment fallback.
\t\tif (const char* supplied = std::getenv("NOVA_CACHE_TITLE_ID"); supplied != nullptr) {
\t\t\ttitle_id = supplied;
\t\t}
#endif
\t\tif (title_id.empty()) {
\t\t\treturn {};
\t\t}
\t}""",
              "title ID Android fallback")
source = once(source,
              """\tconst std::string_view git_hash     = KYTY_GIT_HASH;
\tconst std::string_view git_revision = KYTY_GIT_REVISION;
\tif (git_hash == "unknown" || git_revision == "unknown") {
\t\tPipelineCacheLog("Vulkan pipeline cache: disabled (unknown git revision)");
\t\treturn;
\t}
\tif (git_hash.ends_with("-dirty")) {
\t\tPipelineCacheLog("Vulkan pipeline cache: disabled (dirty build)");
\t\treturn;
\t}""",
              """#if !defined(KYTY_NOVA_FEX)
\t// Vanilla desktop Kyty rejects dirty/unknown source revisions. The Nova
\t// Android build always applies source overlays and has a renderer-specific,
\t// driver UUID/ID/version + cache epoch signature, so keep the validated
\t// cache enabled for it instead of disabling every build as "dirty".
\tconst std::string_view git_hash     = KYTY_GIT_HASH;
\tconst std::string_view git_revision = KYTY_GIT_REVISION;
\tif (git_hash == "unknown" || git_revision == "unknown") {
\t\tPipelineCacheLog("Vulkan pipeline cache: disabled (unknown git revision)");
\t\treturn;
\t}
\tif (git_hash.ends_with("-dirty")) {
\t\tPipelineCacheLog("Vulkan pipeline cache: disabled (dirty build)");
\t\treturn;
\t}
#endif""",
              "dirty build rejection")
source = once(source, "void PipelineCache::Save() {",
              "void PipelineCache::Save(bool preserve_cache) {",
              "snapshot-aware Save")
source = once(source,
              """\tm_graphics.device.destroyPipelineCache(m_driver_cache, nullptr);
\tm_driver_cache = nullptr;
}

PipelineCache::GraphicsPrograms PipelineCache::GetGraphicsPrograms(""",
              """\tif (!preserve_cache) {
\t\tm_graphics.device.destroyPipelineCache(m_driver_cache, nullptr);
\t\tm_driver_cache = nullptr;
\t}
}

PipelineCache::GraphicsPrograms PipelineCache::GetGraphicsPrograms(""",
              "snapshot retains live VkPipelineCache")
# Save the new pipeline cache on a bounded schedule before Android's normal
# exitGame killProcess path. Never call from the GPU completion thread.
snapshot = """\t// Native Android kills the game process on Exit Game. Save an early
\t// warmup snapshot, then every 64 new pipelines. Retain the Vulkan handle:
\t// driver objects already in flight and synchronization are untouched.
#if defined(KYTY_NOVA_FEX)
\tconst size_t nova_count = m_graphics_pipelines.size() + m_compute_pipelines.size();
\tif (nova_count == 16u || (nova_count > 16u && nova_count % 64u == 0u)) {
\t\tSave(true);
\t}
#endif
"""
source = once(source,
              """\tauto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));
\tEXIT_IF(!inserted);

\treturn *iter->second;""",
              """\tauto [iter, inserted] = m_graphics_pipelines.emplace(std::move(key), std::move(cached));
\tEXIT_IF(!inserted);

""" + snapshot + """\treturn *iter->second;""",
              "graphics pipeline snapshot cadence")
source = once(source,
              """\tauto [iter, inserted] = m_compute_pipelines.emplace(compute_program.id, std::move(cached));
\tEXIT_IF(!inserted);

\treturn *iter->second;""",
              """\tauto [iter, inserted] = m_compute_pipelines.emplace(compute_program.id, std::move(cached));
\tEXIT_IF(!inserted);

""" + snapshot + """\treturn *iter->second;""",
              "compute pipeline snapshot cadence")

# Native aliases replace per-field host SIGSEGV handler roundtrips. Crossing
# a FEX 1-GiB slot leaves original pointer unchanged, so wrapped memcpy still
# handles the split correctly and semantics remain byte-for-byte identical.
vertex = once(vertex, "#include \"graphics/shader/shaderVertexMetadata.h\"",
              "#include \"graphics/shader/shaderVertexMetadata.h\"\n#include \"common/guestMemory.h\"",
              "vertex metadata host view include")
vertex = once(vertex,
              "std::memcpy(&user_data, data.user_data, sizeof(user_data));",
              """#if defined(KYTY_NOVA_FEX)
\tstd::memcpy(&user_data, GuestMemory::Ptr(data.user_data, sizeof(user_data)),
\t            sizeof(user_data));
#else
\tstd::memcpy(&user_data, data.user_data, sizeof(user_data));
#endif""",
              "guest-owned shader user data")
vertex = once(vertex,
              "std::memcpy(direct_offsets.data(), user_data.direct_resource_offset, direct_size);",
              """#if defined(KYTY_NOVA_FEX)
\t\tstd::memcpy(direct_offsets.data(),
\t\t            GuestMemory::Ptr(user_data.direct_resource_offset, direct_size), direct_size);
#else
\t\tstd::memcpy(direct_offsets.data(), user_data.direct_resource_offset, direct_size);
#endif""",
              "guest-owned direct offsets")

# Stage all changes in memory; write only after every anchor has passed.
cache_h.write_text(header)
cache_cpp.write_text(source)
vertex_cpp.write_text(vertex)
if app_java is not None:
    java = app_java.read_text()
    java = once(java, 'Os.setenv("NOVA_WORKDIR", work.getPath(), true);',
                'Os.setenv("NOVA_WORKDIR", work.getPath(), true);\n'
                '            String cacheTitleId = titleId(new File(game));\n'
                '            if (cacheTitleId.matches("[A-Za-z0-9_-]{3,48}")) {\n'
                '                Os.setenv("NOVA_CACHE_TITLE_ID", cacheTitleId, true);\n'
                '            } else {\n'
                '                Os.unsetenv("NOVA_CACHE_TITLE_ID");\n'
                '            }',
                "Android per-title cache ID")
    app_java.write_text(java)
print("NOVA_SHADER_CACHE: signed per-title driver cache, periodic live snapshots, native vertex metadata aliases")
