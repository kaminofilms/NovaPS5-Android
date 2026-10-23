#pragma once
#include <filesystem>
#include <string>
#include <vector>

namespace Nova::Dashboard {
struct InstalledApp {
    std::string titleId, title, contentVersion;
    std::filesystem::path directory, icon, background, sound;
};
struct AppScan { std::vector<InstalledApp> apps; std::vector<std::string> errors; };
struct AppDbLayout {
    // Caller supplies a schema verified against its specific dump. No automatic Sony schema guesses.
    std::string table, titleIdColumn, titleColumn, versionColumn;
};
class AppDbSynchronizer {
public:
    static AppScan scan(const std::filesystem::path& games, const std::string& language = "en-US");
    // Updates existing rows/inserts missing rows only. Never creates tables or deletes titles.
    // A separate, newly created SQLite backup is required before modification.
    static void synchronize(const std::filesystem::path& database,
                            const std::filesystem::path& backup,
                            const AppDbLayout&, const std::vector<InstalledApp>&);
};
} // namespace Nova::Dashboard
