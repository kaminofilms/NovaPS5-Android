cmake_minimum_required(VERSION 3.22)
project(nova_dashboard LANGUAGES CXX)
find_package(SQLite3 REQUIRED)
find_package(nlohmann_json 3.11 REQUIRED)
find_package(Threads REQUIRED)
set(DASHBOARD_ROOT ${CMAKE_CURRENT_LIST_DIR}/../..)
add_library(nova_dashboard STATIC
    ${DASHBOARD_ROOT}/src/core/vfs/SystemDumpMount.cpp
    ${DASHBOARD_ROOT}/src/core/kernel/RnpsIoctlHle.cpp
    ${DASHBOARD_ROOT}/src/core/hle/HleShellCoreIpc.cpp
    ${DASHBOARD_ROOT}/src/core/db/AppDbSynchronizer.cpp)
target_compile_features(nova_dashboard PUBLIC cxx_std_20)
target_include_directories(nova_dashboard PUBLIC ${DASHBOARD_ROOT}/src)
target_link_libraries(nova_dashboard PUBLIC SQLite::SQLite3 nlohmann_json::nlohmann_json Threads::Threads)
set_target_properties(nova_dashboard PROPERTIES POSITION_INDEPENDENT_CODE ON)
include(CTest)
if(BUILD_TESTING AND NOT ANDROID)
    add_executable(dashboard_subsystem_tests ${DASHBOARD_ROOT}/tests/dashboard_subsystem.cpp)
    target_link_libraries(dashboard_subsystem_tests PRIVATE nova_dashboard)
    add_test(NAME dashboard_subsystem COMMAND dashboard_subsystem_tests)
endif()
