#pragma once

#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>

namespace NovaRender {

// One executing snapshot and one pending snapshot. A newer complete snapshot
// supersedes the pending one; driver/Vulkan access stays on the rendering thread.
class LatestTask final {
public:
    LatestTask() : worker([this] { Run(); }) {}
    LatestTask(const LatestTask&) = delete;
    LatestTask& operator=(const LatestTask&) = delete;
    ~LatestTask() {
        Drain();
        {
            std::lock_guard lock(mutex);
            stopping = true;
        }
        changed.notify_all();
        worker.join();
    }
    void Post(std::function<void()> task) {
        {
            std::lock_guard lock(mutex);
            pending = std::move(task);
        }
        changed.notify_all();
    }
    void Drain() {
        std::unique_lock lock(mutex);
        changed.wait(lock, [this] { return !pending && !active; });
    }
private:
    void Run() {
        std::unique_lock lock(mutex);
        for (;;) {
            changed.wait(lock, [this] { return stopping || bool(pending); });
            if (stopping) return;
            auto task = std::move(pending);
            pending = {};
            active = true;
            lock.unlock();
            task();
            lock.lock();
            active = false;
            changed.notify_all();
        }
    }
    std::mutex mutex;
    std::condition_variable changed;
    std::function<void()> pending;
    bool active = false;
    bool stopping = false;
    std::thread worker;
};
} // namespace NovaRender
