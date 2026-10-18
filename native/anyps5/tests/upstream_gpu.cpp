#include "runtime_fixture.hpp"
#include <iostream>
#include <stdexcept>
int UpstreamTestMain();
int main() {
    try { NovaAnyTest::Configure(); return UpstreamTestMain(); }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
