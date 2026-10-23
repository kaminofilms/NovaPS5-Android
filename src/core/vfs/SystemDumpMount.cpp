#include "SystemDumpMount.h"
#include "../kernel/RnpsIoctlHle.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <stdexcept>

namespace Nova::Dashboard {
static bool beneath(const fs::path& root, const fs::path& path) {
    auto p = path.begin();
    for (auto r = root.begin(); r != root.end(); ++r, ++p)
        if (p == path.end() || *p != *r) return false;
    return true;
}
SystemDumpMount::SystemDumpMount(const fs::path& dump, const fs::path& games)
    : games_(fs::weakly_canonical(games)) {
    const auto root = fs::weakly_canonical(dump);
    for (const auto& name : {"system", "system_ex", "data", "user", "system_data"}) {
        const auto host = fs::weakly_canonical(root / name);
        if (!beneath(root, host)) throw std::invalid_argument("Dump mount escapes root");
        mounts_.push_back({std::string("/") + name, host,
                           std::string(name) == "system" || std::string(name) == "system_ex"});
    }
}
bool SystemDumpMount::validTitleId(const std::string& id) {
    return id.size() == 9 && (id.starts_with("PPSA") || id.starts_with("NPXS")) &&
        std::all_of(id.begin() + 4, id.end(), [](char c) { return c >= '0' && c <= '9'; });
}
void SystemDumpMount::mountGame(const std::string& id) {
    if (!validTitleId(id)) throw std::invalid_argument("Invalid title ID");
    const auto host = fs::weakly_canonical(games_ / id);
    if (!beneath(games_, host) || !fs::is_directory(host)) throw std::invalid_argument("Invalid game directory");
    const std::string guest = "/mnt/sandbox/pfsmnt/" + id + "-app0";
    for (const auto& m : mounts_) if (m.guest == guest) return;
    mounts_.push_back({guest, host, true});
}
fs::path SystemDumpMount::resolve(const std::string& guest, Access access) const {
    if (guest.empty() || guest[0] != '/' || guest.find('\0') != std::string::npos ||
        guest.find('\\') != std::string::npos) throw std::invalid_argument("Invalid guest path");
    for (const auto& c : fs::path(guest)) if (c == "..") throw std::invalid_argument("Path traversal");
    const Mount* best = nullptr;
    for (const auto& m : mounts_)
        if ((guest == m.guest || guest.starts_with(m.guest + "/")) &&
            (!best || m.guest.size() > best->guest.size())) best = &m;
    if (!best) throw std::invalid_argument("Unmapped guest path");
    if (access == Access::Write && best->readOnly) throw std::invalid_argument("Read-only mount");
    const auto suffix = guest.size() == best->guest.size() ? "" : guest.substr(best->guest.size() + 1);
    const auto path = fs::weakly_canonical(best->host / suffix);
    if (!beneath(best->host, path)) throw std::invalid_argument("Symlink escapes mount");
    return path;
}
bool SystemDumpMount::isElf64X86(const fs::path& p) {
    std::array<unsigned char, 64> h{};
    std::ifstream f(p, std::ios::binary);
    if (!f.read(reinterpret_cast<char*>(h.data()), h.size())) return false;
    // Full ELF structural/loading validation remains the existing loader's responsibility.
    return h[0] == 0x7f && h[1] == 'E' && h[2] == 'L' && h[3] == 'F' &&
           h[4] == 2 && h[5] == 1 && h[6] == 1 && h[18] == 62 && h[19] == 0 &&
           h[52] == 64 && h[53] == 0;
}
Validation SystemDumpMount::validate(const DumpProfile& profile) const {
    Validation result;
    if (profile.shellExecutable.empty()) result.errors.push_back("No firmware shell profile selected");
    auto checkElf = [&](const std::string& p) {
        try { if (!isElf64X86(resolve(p))) result.errors.push_back("Missing/unsupported ELF: " + p); }
        catch (const std::exception& e) { result.errors.push_back(p + ": " + e.what()); }
    };
    if (!profile.shellExecutable.empty()) checkElf(profile.shellExecutable);
    for (const auto& p : profile.libraries) checkElf(p);
    if (profile.bundles.empty()) result.errors.push_back("No RNPS requirements in firmware profile");
    for (const auto& p : profile.bundles) {
        try {
            std::ifstream f(resolve(p), std::ios::binary);
            std::array<std::byte, 64> bytes{};
            f.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
            auto kind = classifyBundle(std::span(bytes).first(static_cast<size_t>(f.gcount())));
            if (kind == BundleKind::Unknown || kind == BundleKind::Encrypted)
                result.errors.push_back("Missing/encrypted/unrecognized RNPS bundle: " + p);
        } catch (const std::exception& e) { result.errors.push_back(p + ": " + e.what()); }
    }
    return result;
}
} // namespace Nova::Dashboard
