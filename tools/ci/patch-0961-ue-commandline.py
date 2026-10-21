#!/usr/bin/env python3
"""0.9.61: virtual empty ue4commandline.txt / uecommandline.txt in /app0 (Unreal Engine titles).

Luna Abyss (PPSA36257) and Super Meat Boy 3D (PPSA31162) print
  "File root is /devlog/app/"  then  "GEngineLoop.PreInit Failed!"  and call exit(0).
Unreal decides its file root from the presence of ue4commandline.txt in the root of /app0
("The existence of a ue4commandline.txt file in the root of /app0 is used to decide to use /app0
as the file root"; a blank file works), and without it falls back to /devlog/app/ and exits; the
AnyPS5 tester of Little Nightmares Enhanced reports the identical failure and fix (AnyPS5
discussion #6275). UE5 names the file uecommandline.txt.

When a game asks for either file in the root of /app0 and its dump has none, the path resolves
to an empty file Nova keeps in its work directory. The game folder is never changed. A dump that
has the file keeps using its own.
"""
from pathlib import Path
import sys

fs = Path(sys.argv[1]) / 'src/kernel/fileSystem.cpp'
s = fs.read_text()
old = '''		const auto native_rel_path = Common::PathFromUtf8(rel_path);
		if (Common::IsArchivePath(p.dir)) {
			return p.dir / native_rel_path;
		}
'''
if s.count(old) != 1:
    raise SystemExit('NOVA_0961_UE_CMDLINE: anchor changed')
s = s.replace(old, '''		const auto native_rel_path = Common::PathFromUtf8(rel_path);
		// Nova 0.9.61: Unreal picks /app0 as its file root only if this file exists there.
		if (p.point.starts_with("/app0") && rel_path.find('/') == std::string::npos) {
			std::string lower = rel_path;
			for (char& c: lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
			if (lower == "ue4commandline.txt" || lower == "uecommandline.txt") {
				const auto own = Common::IsArchivePath(p.dir) ? p.dir / native_rel_path
				                                              : ResolvePathIgnoringCase(p.dir / native_rel_path);
				std::error_code ec;
				if (!Common::IsArchivePath(p.dir) && std::filesystem::exists(own, ec)) {
					return own;
				}
				const char* work = std::getenv("NOVA_WORKDIR");
				if (work == nullptr) work = std::getenv("TMPDIR");
				if (work != nullptr && !Common::IsArchivePath(p.dir)) {
					const auto virtual_file = std::filesystem::path(work) / ("nova_" + lower);
					if (!std::filesystem::exists(virtual_file, ec)) {
						if (FILE* f = std::fopen(virtual_file.c_str(), "wb")) std::fclose(f);
					}
					static bool logged = false;
					if (!logged) {
						logged = true;
						std::fprintf(stderr, "NOVA_UE: /app0/%s is not in this dump; using an empty one (Unreal file root /app0)\\n",
						             rel_path.c_str());
					}
					return virtual_file;
				}
			}
		}
		if (Common::IsArchivePath(p.dir)) {
			return p.dir / native_rel_path;
		}
''')
for inc in ['#include <cctype>', '#include <cstdio>', '#include <cstdlib>', '#include <filesystem>']:
    if inc not in s:
        s = s.replace('#include', inc + '\n#include', 1)
fs.write_text(s)
print('NOVA_0961_UE_CMDLINE: empty /app0/ue4commandline.txt (uecommandline.txt) when the dump has none')
