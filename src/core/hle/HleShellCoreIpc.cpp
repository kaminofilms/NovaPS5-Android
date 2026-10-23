#include "HleShellCoreIpc.h"
#include "../vfs/SystemDumpMount.h"
#include <stdexcept>
#include <utility>

namespace Nova::Dashboard {
HleShellCoreIpc::HleShellCoreIpc(ShellUser user, LaunchHook launch)
    : user_(std::move(user)), launch_(std::move(launch)) {
    if (user_.id <= 0 || user_.name.empty()) throw std::invalid_argument("Invalid initial user");
}
ShellUser HleShellCoreIpc::initialUser() const { std::lock_guard lock(mutex_); return user_; }
void HleShellCoreIpc::registerApplication(std::string id) {
    if (!SystemDumpMount::validTitleId(id)) throw std::invalid_argument("Invalid title ID");
    std::lock_guard lock(mutex_);
    if (apps_.size() >= 4096 && !apps_.contains(id)) throw std::length_error("Application limit");
    apps_.insert(std::move(id));
}
void HleShellCoreIpc::registerInteger(std::string key, int64_t value) {
    if (key.empty() || key.size() > 256) throw std::invalid_argument("Invalid registry key");
    std::lock_guard lock(mutex_);
    if (integers_.size() >= 4096 && !integers_.contains(key)) throw std::length_error("Registry limit");
    integers_[std::move(key)] = value;
}
std::optional<int64_t> HleShellCoreIpc::registryInteger(const std::string& key) const {
    std::lock_guard lock(mutex_);
    auto i = integers_.find(key);
    return i == integers_.end() ? std::nullopt : std::optional(i->second);
}
ServiceResult HleShellCoreIpc::send(ShellMessage m) {
    if (m.payload.size() > 64 * 1024) return ServiceResult::InvalidArgument;
    std::lock_guard lock(mutex_);
    if (!apps_.contains(m.from) || !apps_.contains(m.to)) return ServiceResult::NotFound;
    if (queuedMessages_ >= 1024 || queuedBytes_ + m.payload.size() > 4 * 1024 * 1024)
        return ServiceResult::QueueFull;
    queuedBytes_ += m.payload.size(); ++queuedMessages_;
    queues_[m.to].push_back(std::move(m));
    return ServiceResult::Ok;
}
ServiceResult HleShellCoreIpc::receive(const std::string& destination, ShellMessage& out) {
    std::lock_guard lock(mutex_);
    if (!apps_.contains(destination)) return ServiceResult::NotFound;
    auto q = queues_.find(destination);
    if (q == queues_.end() || q->second.empty()) return ServiceResult::NoEvent;
    out = std::move(q->second.front()); q->second.pop_front();
    queuedBytes_ -= out.payload.size(); --queuedMessages_;
    return ServiceResult::Ok;
}
ServiceResult HleShellCoreIpc::launchApplication(const std::string& id) {
    {
        std::lock_guard lock(mutex_);
        if (!apps_.contains(id)) return ServiceResult::NotFound;
        if (launching_ || running_) return ServiceResult::Busy;
        if (!launch_) return ServiceResult::Unsupported;
        launching_ = true;
    }
    bool ok = false;
    try { ok = launch_(id); } catch (...) { ok = false; }
    {
        std::lock_guard lock(mutex_);
        launching_ = false;
        if (ok) running_ = id;
    }
    return ok ? ServiceResult::Ok : ServiceResult::LaunchFailed;
}
std::optional<std::string> HleShellCoreIpc::runningApplication() const {
    std::lock_guard lock(mutex_); return running_;
}
void HleShellCoreIpc::gameExited() {
    std::lock_guard lock(mutex_);
    if (launching_) throw std::logic_error("Launch handoff still in progress");
    running_.reset();
}
} // namespace Nova::Dashboard
