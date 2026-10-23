#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace Nova::Dashboard {
enum class ServiceResult { Ok, InvalidArgument, NotFound, NoEvent, QueueFull, Unsupported, Busy, LaunchFailed };
struct ShellMessage { std::string from, to; uint32_t type; std::vector<std::byte> payload; };
struct ShellUser { int32_t id = 1; std::string name = "NovaUser"; };
// Host-side service model. Not a declaration of Sony's undocumented wire ABI/NIDs.
class HleShellCoreIpc {
public:
    // Adapter owns guest suspension, game load and rollback. True means handoff committed.
    using LaunchHook = std::function<bool(const std::string&)>;
    explicit HleShellCoreIpc(ShellUser user = {}, LaunchHook launch = {});
    ShellUser initialUser() const;
    void registerApplication(std::string id);
    void registerInteger(std::string key, int64_t value);
    std::optional<int64_t> registryInteger(const std::string& key) const;
    ServiceResult send(ShellMessage);
    ServiceResult receive(const std::string& destination, ShellMessage& out);
    ServiceResult launchApplication(const std::string& titleId);
    std::optional<std::string> runningApplication() const;
    void gameExited();
private:
    mutable std::mutex mutex_;
    ShellUser user_;
    LaunchHook launch_;
    std::set<std::string> apps_;
    std::map<std::string, int64_t> integers_;
    std::map<std::string, std::deque<ShellMessage>> queues_;
    std::optional<std::string> running_;
    bool launching_ = false;
    size_t queuedBytes_ = 0;
    size_t queuedMessages_ = 0;
};
} // namespace Nova::Dashboard
