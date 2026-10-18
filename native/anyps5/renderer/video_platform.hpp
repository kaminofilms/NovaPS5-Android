#pragma once
#include "prx/libSceAgcDriver/Execution/include/Presentation.hpp"
#include <cstdint>
namespace NovaAnyPS5 {
struct VideoPlatform {
    AgcDriver::PresentationWindow (*window)();
    int (*refreshRate)();
    void (*framePresented)();
    void (*requestExit)(int);
    std::uint32_t (*appAttribute3)();
    std::uint64_t (*processTime)();
    std::uint64_t (*processTimeCounter)();
};
void ConfigureVideoPlatform(const VideoPlatform& platform);
const VideoPlatform& Video();
}
