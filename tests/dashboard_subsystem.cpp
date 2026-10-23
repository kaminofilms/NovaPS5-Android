#include "core/vfs/SystemDumpMount.h"
#include "core/kernel/RnpsIoctlHle.h"
#include "core/hle/HleShellCoreIpc.h"
#include "core/db/AppDbSynchronizer.h"
#include <sqlite3.h>
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>

using namespace Nova::Dashboard;
static void require(bool yes) { if (!yes) throw std::runtime_error("Test requirement failed"); }
template<class F> static void rejects(F f) {
    bool threw = false; try { f(); } catch (const std::exception&) { threw = true; } require(threw);
}
static void write(const fs::path& p, const std::string& data) {
    fs::create_directories(p.parent_path()); std::ofstream(p, std::ios::binary) << data;
}
static void exec(sqlite3* db, const char* q) {
    if (sqlite3_exec(db, q, nullptr, nullptr, nullptr) != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db));
}
int main() {
    const auto root = fs::temp_directory_path() / ("nova-dashboard-" + std::to_string(std::random_device{}()));
    if (!fs::create_directory(root)) throw std::runtime_error("Test directory collision");
    struct Cleanup { fs::path path; ~Cleanup() { std::error_code ec; fs::remove_all(path, ec); } } cleanup{root};
    auto dump = root / "dump", games = root / "games";
    fs::create_directories(dump / "system"); fs::create_directories(games / "PPSA00001");
    SystemDumpMount mounts(dump, games); mounts.mountGame("PPSA00001");
    require(mounts.resolve("/system/a") == dump / "system/a");
    rejects([&] { mounts.resolve("/system/a", Access::Write); });
    rejects([&] { mounts.resolve("/system/../user/a"); });
    rejects([&] { mounts.resolve("/system_extra/a"); });
    rejects([&] { mounts.mountGame("../../bad"); });
    fs::create_directory_symlink(root, dump / "system/escape");
    rejects([&] { mounts.resolve("/system/escape/a"); });
    require(mounts.resolve("/data/new", Access::Write) == dump / "data/new");
    require(!mounts.validate({}).ready());
    std::string elf(64, '\0'); elf[0] = '\x7f'; elf[1] = 'E'; elf[2] = 'L'; elf[3] = 'F';
    elf[4] = 2; elf[5] = 1; elf[6] = 1; elf[18] = 62; elf[52] = 64;
    write(dump / "system/shell.elf", elf);
    write(dump / "system_ex/rnps/apps/NPXS40002/application.ps.bundle", "function main() {}\n");
    require(mounts.validate({"/system/shell.elf", {}, {"/system_ex/rnps/apps/NPXS40002/application.ps.bundle"}}).ready());
    write(dump / "system/bad.elf", "RNPSHEDR"); require(!SystemDumpMount::isElf64X86(dump / "system/bad.elf"));

    std::array<std::byte, 1024> memory{};
    GuestMemory bridge{
        [&](uint64_t address, std::span<std::byte> out) {
            if (address > memory.size() || out.size() > memory.size() - address) return false;
            std::memcpy(out.data(), memory.data() + address, out.size()); return true;
        },
        [&](uint64_t address, std::span<const std::byte> in) {
            if (address > memory.size() || in.size() > memory.size() - address) return false;
            std::memcpy(memory.data() + address, in.data(), in.size()); return true;
        }
    };
    auto setArgs = [&](RnpsRequest a) { std::memcpy(memory.data() + 16, &a, sizeof(a)); };
    auto getArgs = [&] { RnpsRequest a; std::memcpy(&a, memory.data() + 16, sizeof(a)); return a; };
    RnpsIoctlHle rnps([](BundleKind kind, std::span<const std::byte> bytes) {
        return kind == BundleKind::JavaScriptCandidate && bytes.size() == 8 &&
               std::memcmp(bytes.data(), "var a=1;", 8) == 0;
    });
    std::memcpy(memory.data() + 128, "RNPSHEDR", 8); setArgs({128, 8, 123});
    require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::Unsupported);
    require(getArgs().error == 123); // Never claim encrypted input was decrypted.
    std::memcpy(memory.data() + 128, "var a=1;", 8);
    require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::Completed);
    require(getArgs().error == 0);
    require(rnps.handle(false, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::WrongDevice);
    require(rnps.handle(true, 99, 16, bridge) == IoctlResult::UnknownRequest);
    setArgs({128, -1, 123}); require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::BadSize);
    setArgs({UINT64_MAX - 1, 8, 123}); require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::BadAddress);
    setArgs({16, 8, 123}); require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::BadAddress);
    setArgs({1000, 64, 123}); require(rnps.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::BadAddress);
    setArgs({128, 8, 123});
    RnpsIoctlHle noVerifier({});
    require(noVerifier.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::Unsupported);
    RnpsIoctlHle badVerifier([](auto, auto) { return false; });
    require(badVerifier.handle(true, VerifyDecryptRnpsBundle, 16, bridge) == IoctlResult::InvalidBundle);

    bool allowLaunch = false; HleShellCoreIpc* servicePtr = nullptr;
    HleShellCoreIpc service({}, [&](const std::string&) {
        require(servicePtr->initialUser().id == 1); // Callback runs outside service mutex.
        return allowLaunch;
    }); servicePtr = &service;
    service.registerApplication("NPXS40002"); service.registerApplication("PPSA00001");
    service.registerInteger("profile.language", 1);
    require(service.registryInteger("profile.language") == 1);
    require(!service.registryInteger("unverified.guest.key"));
    require(service.launchApplication("PPSA00001") == ServiceResult::LaunchFailed);
    require(!service.runningApplication());
    allowLaunch = true; require(service.launchApplication("PPSA00001") == ServiceResult::Ok);
    require(service.launchApplication("PPSA00001") == ServiceResult::Busy);
    service.gameExited(); require(!service.runningApplication());
    ShellMessage out;
    require(service.receive("NPXS40002", out) == ServiceResult::NoEvent);
    require(service.send({"PPSA00001", "NPXS40002", 7, {std::byte{1}}}) == ServiceResult::Ok);
    require(service.receive("NPXS40002", out) == ServiceResult::Ok && out.type == 7 && out.payload.size() == 1);
    for (int i = 0; i < 1024; ++i) require(service.send({"PPSA00001", "NPXS40002", 0, {}}) == ServiceResult::Ok);
    require(service.send({"PPSA00001", "NPXS40002", 0, {}}) == ServiceResult::QueueFull);

    write(games / "PPSA00001/sce_sys/param.json", R"({"titleId":"PPSA00001","contentVersion":"01.000.000","localizedParameters":{"defaultLanguage":"en-US","en-US":{"titleName":"Nova's fixture"}}})");
    write(games / "bad/sce_sys/param.json", "{");
    auto scan = AppDbSynchronizer::scan(games);
    require(scan.apps.size() == 1 && scan.errors.size() == 1 && scan.apps[0].title == "Nova's fixture");
    require(scan.apps[0].sound.empty()); // Optional assets must not hide an installed game.
    const auto database = root / "app.db";
    sqlite3* db = nullptr; require(sqlite3_open(database.string().c_str(), &db) == SQLITE_OK);
    exec(db, "CREATE TABLE apps(title_id TEXT PRIMARY KEY,title TEXT,version TEXT CHECK(version != 'bad')); CREATE TABLE untouched(value TEXT); INSERT INTO untouched VALUES('preserve');");
    sqlite3_close(db);
    const AppDbLayout layout{"apps", "title_id", "title", "version"};
    rejects([&] { AppDbSynchronizer::synchronize(database, root / "no-backup.db", {"missing", "id", "name", "ver"}, scan.apps); });
    require(!fs::exists(root / "no-backup.db"));
    AppDbSynchronizer::synchronize(database, root / "backup.db", layout, scan.apps);
    require(fs::is_regular_file(root / "backup.db"));
    auto failed = scan.apps; failed[0].title = "must rollback";
    auto second = failed[0]; second.titleId = "PPSA00002"; second.contentVersion = "bad"; failed.push_back(second);
    rejects([&] { AppDbSynchronizer::synchronize(database, root / "backup2.db", layout, failed); });
    require(sqlite3_open(database.string().c_str(), &db) == SQLITE_OK);
    sqlite3_stmt* s = nullptr;
    require(sqlite3_prepare_v2(db, "SELECT title FROM apps WHERE title_id='PPSA00001'", -1, &s, nullptr) == SQLITE_OK);
    require(sqlite3_step(s) == SQLITE_ROW && std::string(reinterpret_cast<const char*>(sqlite3_column_text(s, 0))) == "Nova's fixture");
    sqlite3_finalize(s);
    require(sqlite3_prepare_v2(db, "SELECT count(*) FROM apps", -1, &s, nullptr) == SQLITE_OK);
    require(sqlite3_step(s) == SQLITE_ROW && sqlite3_column_int(s, 0) == 1);
    sqlite3_finalize(s); sqlite3_close(db);
    std::cout << "Dashboard subsystem tests passed (synthetic fixtures; no Sony dashboard boot).\n";
}
