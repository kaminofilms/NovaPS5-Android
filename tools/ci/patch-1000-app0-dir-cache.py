#!/usr/bin/env python3
"""Game-folder lookups without a directory scan per missing file; precise indirect-image errors.

Hellblade (PPSA27581) from an SD card: Unreal probes hundreds of optional .ini files that are not
in the dump, and every miss cost 50-90 ms in MountPoints::ResolvePath. ResolvePathIgnoringCase
re-lists the parent directory on each miss to look for a case variant, and SD-card listings are
slow, so boot crawled at ~25 lookups a second with the CPU idle. /app0 is the game's read-only
package, so its directory listings cannot change while it runs: each directory is listed once
(names keyed exactly and by ASCII lower case) and later lookups are answered from that listing.
Paths with "." or ".." components, unlistable directories and other mounts use the original
uncached resolver. A path absent from a cached listing is answered ENOENT by stat/open without
the native lookup (still ~55 ms per miss on the SD card in 0.9.114); guest unlink/rename/mkdir/rmdir
or a writing open under /app0 marks the listings stale. NOVA_APP0_DIR_CACHE=0 disables the cache.

Wolverine (PPSA03671) stops at "indirect image table ... has incompatible candidates". The message
now names the property that differs (numeric class, dimension, mip count, conversion format or
swizzle) and both values, so the right translation can be added; behaviour is unchanged.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'src'
fs = root / 'kernel/fileSystem.cpp'
rm = root / 'graphics/shader/recompiler/ir/passes/ResourceMaterialization.cpp'
text = {fs: fs.read_text(), rm: rm.read_text()}

def once(path, old, new):
    if text[path].count(old) != 1:
        raise SystemExit(f'1000: {path.name} anchor changed ({text[path].count(old)}): {old[:60]!r}; no source written')
    text[path] = text[path].replace(old, new, 1)

once(fs, '''#if KYTY_PLATFORM != KYTY_PLATFORM_WINDOWS
// Resolve guest paths case-insensitively on case-sensitive hosts.''', '''// Nova 1000: set by ResolvePath when an /app0 path is known (from a cached listing) not to exist,
// so stat/open answer ENOENT without a slow native lookup on the SD card. Guest writes under /app0
// mark the listings stale.
static thread_local bool g_nova_app0_missing = false;
static std::atomic<bool> g_nova_dir_cache_dirty {false};
static void NovaApp0Changed(const char* path) {
	if (path != nullptr && std::string_view(path).starts_with("/app0")) g_nova_dir_cache_dirty = true;
}
// Marks /app0 listings stale when a mutating call returns (after the change happened).
struct NovaApp0WriteGuard {
	std::string path;
	bool        active = true;
	~NovaApp0WriteGuard() {
		if (active) NovaApp0Changed(path.c_str());
	}
};
#if KYTY_PLATFORM != KYTY_PLATFORM_WINDOWS
// Resolve guest paths case-insensitively on case-sensitive hosts.''')
once(fs, '''#else
static bool HasWindowsForbiddenFilenameCharacter(''', '''// Nova 1000: /app0 is a read-only game package, so each directory is listed once.
struct NovaDirListing {
	bool                                         valid = false;
	std::unordered_map<std::string, std::string> by_lower;  // ASCII-lowercased name -> real name
	std::unordered_set<std::string>              exact;
};
static std::string NovaLowerAscii(std::string value) {
	for (char& c: value) {
		if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
	}
	return value;
}
static std::unordered_map<std::string, NovaDirListing> g_nova_dir_cache;  // guarded by MountPoints::m_mutex
static const NovaDirListing& NovaListDirectory(const std::filesystem::path& directory) {
	if (const auto found = g_nova_dir_cache.find(directory.native()); found != g_nova_dir_cache.end()) {
		return found->second;
	}
	if (g_nova_dir_cache.size() >= 16384) g_nova_dir_cache.clear();
	NovaDirListing listing;
	std::error_code ec;
	std::filesystem::directory_iterator entry(directory, ec), end;
	listing.valid = !ec;
	for (; !ec && entry != end; entry.increment(ec)) {
		auto name = entry->path().filename().string();
		listing.by_lower.emplace(NovaLowerAscii(name), name);
		listing.exact.insert(std::move(name));
	}
	if (ec) listing = {};  // a partial listing must not answer "missing"
	return g_nova_dir_cache.emplace(directory.native(), std::move(listing)).first->second;
}
static std::filesystem::path ResolvePathIgnoringCase(const std::filesystem::path& path);
static std::filesystem::path NovaResolveReadOnly(const std::filesystem::path& base, const std::filesystem::path& relative) {
	static const bool enabled = [] {
		const char* value = std::getenv("NOVA_APP0_DIR_CACHE");
		return !(value && value[0] == '0');
	}();
	if (!enabled) return ResolvePathIgnoringCase(base / relative);
	if (g_nova_dir_cache_dirty.exchange(false)) g_nova_dir_cache.clear();
	for (const auto& component: relative) {
		if (component == "." || component == "..") return ResolvePathIgnoringCase(base / relative);
	}
	std::filesystem::path resolved = base;
	bool matched = true;
	for (const auto& component: relative) {
		if (component.empty()) continue;
		if (!matched) {
			resolved /= component;
			continue;
		}
		const auto& listing = NovaListDirectory(resolved);
		if (!listing.valid) return ResolvePathIgnoringCase(base / relative);
		const auto name = component.string();
		if (listing.exact.contains(name)) {
			resolved /= component;
		} else if (const auto found = listing.by_lower.find(NovaLowerAscii(name)); found != listing.by_lower.end()) {
			resolved /= found->second;
		} else {
			resolved /= component;  // keep the unmatched tail for the caller's ENOENT
			matched = false;
		}
	}
	g_nova_app0_missing = !matched;
	return resolved;
}
#else
static bool HasWindowsForbiddenFilenameCharacter(''')
once(fs, '''		return ResolvePathIgnoringCase(p.dir / native_rel_path);
#endif
	}''', '''		if (p.point.starts_with("/app0")) return NovaResolveReadOnly(p.dir, native_rel_path);
		return ResolvePathIgnoringCase(p.dir / native_rel_path);
#endif
	}''')
once(fs, '''std::filesystem::path MountPoints::ResolvePath(const std::string& mounted_name) {
	Common::LockGuard lock(m_mutex);
''', '''std::filesystem::path MountPoints::ResolvePath(const std::string& mounted_name) {
	Common::LockGuard lock(m_mutex);
	g_nova_app0_missing = false;
''')
once(fs, '''    if (real_file_name.empty()) return KERNEL_ERROR_ENOENT;
    if (!Common::IsArchivePath(real_file_name)) {
        FileStat result{};''', '''    if (real_file_name.empty()) return KERNEL_ERROR_ENOENT;
    if (g_nova_app0_missing) return KERNEL_ERROR_ENOENT;  // Nova 1000: absent from the read-only listing
    if (!Common::IsArchivePath(real_file_name)) {
        FileStat result{};''')
once(fs, '''	file->real_name = g_mount_points->ResolvePath(file->name);
	if (file->real_name.empty()) {
		g_files->DeleteDescriptor(descriptor);
		return KERNEL_ERROR_ENOENT;
	}
''', '''	NovaApp0WriteGuard nova_app0_write {file->name, creat || trunc || rw_mode != Common::File::Mode::Read};
	file->real_name = g_mount_points->ResolvePath(file->name);
	if (file->real_name.empty() || (g_nova_app0_missing && !creat)) {
		g_files->DeleteDescriptor(descriptor);
		return KERNEL_ERROR_ENOENT;
	}
''')
for name, args in (('KernelUnlink', 'const char* path'), ('KernelMkdir', 'const char* path, uint16_t mode'), ('KernelRmdir', 'const char* path')):
    once(fs, f'int KYTY_SYSV_ABI {name}({args}) {{\n', f'int KYTY_SYSV_ABI {name}({args}) {{\n\tNovaApp0WriteGuard nova_app0_write {{path ? path : ""}};\n')
once(fs, 'int KYTY_SYSV_ABI KernelRename(const char* from, const char* to) {\n',
     'int KYTY_SYSV_ABI KernelRename(const char* from, const char* to) {\n\tNovaApp0WriteGuard nova_app0_from {from ? from : ""}, nova_app0_to {to ? to : ""};\n')
for header in ('#include <unordered_map>', '#include <unordered_set>', '#include <string_view>'):
    if header not in text[fs]:
        text[fs] = text[fs].replace('#include <filesystem>\n', '#include <filesystem>\n' + header + '\n', 1)

once(rm, '''			if (image.numeric_class != image_class.numeric_class ||
			    (!same_coordinates && !(is_2d(image.dimension) && is_2d(image_class.dimension))) ||
			    image.mip_count != image_class.mip_count ||
			    image.conversion_format != image_class.conversion_format ||
			    image.shader_swizzle != image_class.shader_swizzle) {
				return SpecializationFail(
				    fmt::format("indirect image table at pc 0x{:08x} has incompatible candidates",
				                program.info.images[root_index].first_use_pc));
			}''', '''			const char* nova_field = nullptr;
			uint32_t    nova_have = 0, nova_want = 0;
			if (image.numeric_class != image_class.numeric_class) {
				nova_field = "numeric_class"; nova_have = static_cast<uint32_t>(image.numeric_class); nova_want = static_cast<uint32_t>(image_class.numeric_class);
			} else if (!same_coordinates && !(is_2d(image.dimension) && is_2d(image_class.dimension))) {
				nova_field = "dimension"; nova_have = static_cast<uint32_t>(image.dimension) * 2u + (image.cube ? 1u : 0u);
				nova_want = static_cast<uint32_t>(image_class.dimension) * 2u + (image_class.cube ? 1u : 0u);
			} else if (image.mip_count != image_class.mip_count) {
				nova_field = "mip_count"; nova_have = image.mip_count; nova_want = image_class.mip_count;
			} else if (image.conversion_format != image_class.conversion_format) {
				nova_field = "conversion_format"; nova_have = static_cast<uint32_t>(image.conversion_format); nova_want = static_cast<uint32_t>(image_class.conversion_format);
			} else if (image.shader_swizzle != image_class.shader_swizzle) {
				nova_field = "shader_swizzle"; nova_have = image.shader_swizzle; nova_want = image_class.shader_swizzle;
			}
			if (nova_field != nullptr) {
				return SpecializationFail(
				    fmt::format("indirect image table at pc 0x{:08x} has incompatible candidates "
				                "(candidate {} {}={} vs first typed candidate {} {}={}, {} candidates)",
				                program.info.images[root_index].first_use_pc, candidate, nova_field, nova_have,
				                exemplar, nova_field, nova_want, resource_count));
			}''')

for path, s in text.items():
    path.write_text(s)
print('1000: /app0 directory listings cached for case-insensitive lookups; indirect-image mismatch named')
