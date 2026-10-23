#include "AppDbSynchronizer.h"
#include "../vfs/SystemDumpMount.h"
#include <nlohmann/json.hpp>
#include <sqlite3.h>
#include <algorithm>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>

namespace Nova::Dashboard {
namespace {
using Db = std::unique_ptr<sqlite3, decltype(&sqlite3_close)>;
using Stmt = std::unique_ptr<sqlite3_stmt, decltype(&sqlite3_finalize)>;
std::string quote(const std::string& s) {
    if (s.empty() || !std::all_of(s.begin(), s.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '_'; })) throw std::invalid_argument("Invalid SQL identifier");
    return "\"" + s + "\"";
}
Db openDb(const std::filesystem::path& path, int flags) {
    sqlite3* raw = nullptr;
    int rc = sqlite3_open_v2(path.string().c_str(), &raw, flags, nullptr);
    Db db(raw, sqlite3_close);
    if (rc != SQLITE_OK) throw std::runtime_error("Cannot open SQLite database");
    sqlite3_busy_timeout(db.get(), 2000);
    return db;
}
void sql(sqlite3* db, const std::string& query) {
    if (sqlite3_exec(db, query.c_str(), nullptr, nullptr, nullptr) != SQLITE_OK)
        throw std::runtime_error(sqlite3_errmsg(db));
}
Stmt prepare(sqlite3* db, const std::string& query) {
    sqlite3_stmt* raw = nullptr;
    int rc = sqlite3_prepare_v2(db, query.c_str(), -1, &raw, nullptr);
    Stmt statement(raw, sqlite3_finalize);
    if (rc != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db));
    return statement;
}
std::string text(sqlite3_stmt* s, int col) {
    const auto* t = sqlite3_column_text(s, col);
    return t ? reinterpret_cast<const char*>(t) : "";
}
void bind(sqlite3_stmt* s, int index, const std::string& value) {
    if (sqlite3_bind_text(s, index, value.c_str(), static_cast<int>(value.size()), SQLITE_TRANSIENT) != SQLITE_OK)
        throw std::runtime_error("SQLite bind failed");
}
bool inside(const std::filesystem::path& root, const std::filesystem::path& p) {
    auto part = p.begin();
    for (const auto& r : root) { if (part == p.end() || *part++ != r) return false; }
    return true;
}
}
AppScan AppDbSynchronizer::scan(const std::filesystem::path& games, const std::string& language) {
    AppScan result;
    try {
        const auto root = std::filesystem::canonical(games);
        for (const auto& entry : std::filesystem::directory_iterator(root)) {
            if (!entry.is_directory()) continue;
            try {
                const auto dir = std::filesystem::canonical(entry.path());
                if (!inside(root, dir)) throw std::runtime_error("Game directory escapes root");
                auto checked = [&](const std::filesystem::path& relative) {
                    const auto path = std::filesystem::weakly_canonical(dir / relative);
                    if (!inside(dir, path)) throw std::runtime_error("Metadata/asset escapes game directory");
                    return path;
                };
                const auto param = checked("sce_sys/param.json");
                if (!std::filesystem::exists(param)) continue;
                if (std::filesystem::file_size(param) > 1024 * 1024) throw std::runtime_error("Oversized param.json");
                std::ifstream input(param);
                auto j = nlohmann::json::parse(input, [](int depth, auto, auto&) {
                    if (depth > 64) throw std::runtime_error("param.json nesting limit exceeded");
                    return true;
                });
                InstalledApp app;
                app.titleId = j.at("titleId").get<std::string>();
                if (!SystemDumpMount::validTitleId(app.titleId)) throw std::runtime_error("Invalid titleId");
                app.directory = dir;
                app.contentVersion = j.value("contentVersion", "");
                app.title = app.titleId;
                if (j.contains("localizedParameters")) {
                    const auto& loc = j.at("localizedParameters");
                    std::string selected = loc.contains(language) ? language : loc.value("defaultLanguage", "en-US");
                    if (loc.contains(selected) && loc.at(selected).is_object())
                        app.title = loc.at(selected).value("titleName", app.titleId);
                }
                if (app.title.size() > 4096 || app.contentVersion.size() > 128 ||
                    app.title.find('\0') != std::string::npos || app.contentVersion.find('\0') != std::string::npos)
                    throw std::runtime_error("Invalid metadata string");
                for (const auto& a : result.apps) if (a.titleId == app.titleId) throw std::runtime_error("Duplicate titleId");
                auto asset = [&](const char* name) {
                    auto path = checked(std::filesystem::path("sce_sys") / name);
                    return std::filesystem::is_regular_file(path) ? path : std::filesystem::path{};
                };
                app.icon = asset("icon0.png"); app.background = asset("pic1.png");
                if (app.background.empty()) app.background = asset("pic0.png");
                app.sound = asset("snd0.at9");
                result.apps.push_back(std::move(app));
            } catch (const std::exception& e) { result.errors.push_back(entry.path().string() + ": " + e.what()); }
        }
        std::sort(result.apps.begin(), result.apps.end(), [](const auto& a, const auto& b) { return a.titleId < b.titleId; });
    } catch (const std::exception& e) { result.errors.push_back(e.what()); }
    return result;
}
void AppDbSynchronizer::synchronize(const std::filesystem::path& database,
                                  const std::filesystem::path& backup,
                                  const AppDbLayout& layout, const std::vector<InstalledApp>& apps) {
    const auto table = quote(layout.table), id = quote(layout.titleIdColumn),
               title = quote(layout.titleColumn), version = quote(layout.versionColumn);
    if (std::set<std::string>{id, title, version}.size() != 3) throw std::invalid_argument("Duplicate schema columns");
    if (!std::filesystem::is_regular_file(database) || std::filesystem::exists(backup) ||
        std::filesystem::weakly_canonical(database) == std::filesystem::weakly_canonical(backup))
        throw std::invalid_argument("Existing database and new backup path required");
    std::set<std::string> ids;
    for (const auto& app : apps)
        if (!SystemDumpMount::validTitleId(app.titleId) || !ids.insert(app.titleId).second)
            throw std::invalid_argument("Invalid or duplicate catalog title");
    auto db = openDb(database, SQLITE_OPEN_READWRITE);
    // Reject views and missing tables. Do not invent or overwrite a Sony schema.
    auto type = prepare(db.get(), "SELECT type FROM sqlite_master WHERE name=?");
    bind(type.get(), 1, layout.table);
    if (sqlite3_step(type.get()) != SQLITE_ROW || text(type.get(), 0) != "table")
        throw std::runtime_error("Profile table not found");
    type.reset();
    auto columns = prepare(db.get(), "PRAGMA table_info(" + table + ")");
    std::set<std::string> found;
    int step = 0;
    while ((step = sqlite3_step(columns.get())) == SQLITE_ROW) {
        auto name = text(columns.get(), 1); found.insert(name);
        bool mapped = name == layout.titleIdColumn || name == layout.titleColumn || name == layout.versionColumn;
        if (!mapped && sqlite3_column_int(columns.get(), 3) && sqlite3_column_type(columns.get(), 4) == SQLITE_NULL)
            throw std::runtime_error("Unmapped required schema column: " + name);
    }
    if (step != SQLITE_DONE) throw std::runtime_error("Cannot read database schema");
    columns.reset();
    for (const auto& name : {layout.titleIdColumn, layout.titleColumn, layout.versionColumn})
        if (!found.contains(name)) throw std::runtime_error("Profile column not found: " + name);
    // Live firmware databases must not be used here; the adapter must quiesce their users.
    auto copy = openDb(backup, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_EXCLUSIVE);
    auto* b = sqlite3_backup_init(copy.get(), "main", db.get(), "main");
    if (!b) throw std::runtime_error("Cannot initialize database backup");
    int rc = sqlite3_backup_step(b, -1); int finish = sqlite3_backup_finish(b);
    if (rc != SQLITE_DONE || finish != SQLITE_OK) throw std::runtime_error("Database backup failed");
    copy.reset();
    sql(db.get(), "PRAGMA foreign_keys=ON");
    sql(db.get(), "BEGIN IMMEDIATE");
    try {
        auto update = prepare(db.get(), "UPDATE " + table + " SET " + title + "=?," + version + "=? WHERE " + id + "=?");
        auto insert = prepare(db.get(), "INSERT INTO " + table + "(" + id + "," + title + "," + version + ") VALUES(?,?,?)");
        for (const auto& app : apps) {
            sqlite3_reset(update.get()); sqlite3_clear_bindings(update.get());
            bind(update.get(), 1, app.title); bind(update.get(), 2, app.contentVersion); bind(update.get(), 3, app.titleId);
            if (sqlite3_step(update.get()) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(db.get()));
            if (sqlite3_changes(db.get()) > 1) throw std::runtime_error("Ambiguous duplicate title rows");
            if (sqlite3_changes(db.get()) == 0) {
                sqlite3_reset(insert.get()); sqlite3_clear_bindings(insert.get());
                bind(insert.get(), 1, app.titleId); bind(insert.get(), 2, app.title); bind(insert.get(), 3, app.contentVersion);
                if (sqlite3_step(insert.get()) != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(db.get()));
            }
        }
        update.reset(); insert.reset();
        sql(db.get(), "COMMIT");
    } catch (...) { sqlite3_exec(db.get(), "ROLLBACK", nullptr, nullptr, nullptr); throw; }
}
} // namespace Nova::Dashboard
