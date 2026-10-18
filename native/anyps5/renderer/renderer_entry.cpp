#include "host_services.hpp"
#include "prx/libSceAgcDriver/Execution/include/Driver.hpp"
extern "C" void NovaAnyPS5WaitIdle() {
    AgcDriverWaitIdle_nid_postfix();
}
