#include "install.h"
#include "package/tablePfs.h"
#include "package/pkgParser.h"
#include "package/pfsParser.h"
#include "IO/Decompressor.hpp"
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <set>
#include <mutex>

namespace NovaPkg {
std::string Install(const std::string& input, const std::string& output) {
    namespace fs = std::filesystem;
    static std::once_flag codecs;
    std::call_once(codecs, [] {
        KytyPS5::IO::DecompressionProvider::Instance().RegisterDecompressor(
            0, std::make_unique<KytyPS5::IO::ZlibDecompressor>());
    });
    if (!fs::is_directory(output) || !fs::is_empty(output))
        throw std::runtime_error("Installation staging directory must be empty");
    const auto package = Libs::Firmware::PkgParser::Parse(input);
    if (!package.ok) throw std::runtime_error(package.error);
    if (package.is_encrypted) throw std::runtime_error("Encrypted PKG data is unsupported; use a decrypted package or extracted game folder");
    if (!package.extraction_error.empty()) throw std::runtime_error(package.extraction_error);
    const auto root = fs::path(output) / "pfs_files";
    if (package.is_finalized_image && package.pfs_image_offset != package.pfs_segment_offset) {
        ExtractTablePfs(input, package.pfs_segment_offset, package.pfs_segment_size,
                        package.pfs_image_offset, root.string());
    } else {
    const auto extracted = Libs::Firmware::PkgParser::ExtractAll(package, input, output);
    if (!extracted) throw std::runtime_error("Package filesystem extraction failed; no game was installed");
    const auto image = fs::path(output) / "body.pfs";
    const auto parsed = Libs::Firmware::PfsParser::Parse(image.string());
    if (!parsed.ok || parsed.is_encrypted) throw std::runtime_error("Installed filesystem validation failed");
    const auto canonical = fs::canonical(root);
    std::set<std::string> names;
    uint32_t expected = 0;
    for (const auto& file : parsed.files) {
        const fs::path relative(file.name);
        if (relative.empty() || relative.is_absolute() || !names.insert(file.name).second)
            throw std::runtime_error("Unsafe or duplicate package path");
        for (const auto& part : relative)
            if (part == "." || part == ".." || part.string().find('\\') != std::string::npos || part.string().find(':') != std::string::npos)
                throw std::runtime_error("Unsafe package path");
        if (file.is_directory) continue;
        ++expected;
        const auto path = root / relative;
        if (fs::is_symlink(path) || !fs::is_regular_file(path) || fs::file_size(path) != file.size)
            throw std::runtime_error("Incomplete installed file: " + file.name);
        auto resolved = fs::canonical(path).lexically_relative(canonical);
        if (resolved.empty() || *resolved.begin() == "..") throw std::runtime_error("Package path escapes staging");
    }
    if (expected != extracted) throw std::runtime_error("Incomplete package extraction");
        fs::remove(image);
    }
    std::ifstream boot(root / "eboot.bin", std::ios::binary);
    unsigned char h[20]{};
    boot.read(reinterpret_cast<char*>(h), sizeof(h));
    if (boot.gcount() != sizeof(h) || h[0] != 0x7f || h[1] != 'E' || h[2] != 'L' || h[3] != 'F' || h[4] != 2 || h[5] != 1 || h[18] != 62 || h[19] != 0)
        throw std::runtime_error("Package has no decrypted x86-64 ELF eboot.bin supported by Nova");
    return root.string();
}
}

