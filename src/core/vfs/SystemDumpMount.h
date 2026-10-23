#pragma once
#include <filesystem>
#include <string>
#include <vector>

namespace Nova::Dashboard {
namespace fs = std::filesystem;
enum class Access { Read, Write };
struct Mount { std::string guest; fs::path host; bool readOnly; };
struct DumpProfile {
    std::string shellExecutable; // Explicit firmware-specific guest path; no guessed executable ID.
    std::vector<std::string> libraries;
    std::vector<std::string> bundles;
};
struct Validation { std::vector<std::string> errors; bool ready() const { return errors.empty(); } };
class SystemDumpMount {
public:
    SystemDumpMount(const fs::path& dump, const fs::path& games);
    void mountGame(const std::string& titleId);
    fs::path resolve(const std::string& guest, Access access = Access::Read) const;
    const std::vector<Mount>& mounts() const { return mounts_; }
    Validation validate(const DumpProfile&) const;
    static bool validTitleId(const std::string&);
    static bool isElf64X86(const fs::path&);
private:
    std::vector<Mount> mounts_;
    fs::path games_;
};
} // namespace Nova::Dashboard
