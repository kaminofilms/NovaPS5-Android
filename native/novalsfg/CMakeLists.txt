# Nova PS5: libnovalsfg.so (Lossless Scaling frame generation, see novalsfg.h).
# LSFG_SOURCE: checkout of lsfg-vk-android (MIT) with its submodules, prepared by
# tools/ci/build-android-lsfg.sh.
cmake_minimum_required(VERSION 3.16)
project(novalsfg LANGUAGES C CXX)

if(NOT LSFG_SOURCE)
  message(FATAL_ERROR "LSFG_SOURCE is required")
endif()

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_C_VISIBILITY_PRESET hidden)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
add_compile_options(-Wno-deprecated-declarations -Wno-unused-template)

add_subdirectory(${LSFG_SOURCE}/thirdparty/dxbc dxbc EXCLUDE_FROM_ALL)
add_subdirectory(${LSFG_SOURCE}/thirdparty/pe-parse/pe-parser-library pe-parse EXCLUDE_FROM_ALL)
add_subdirectory(${LSFG_SOURCE}/thirdparty/volk volk EXCLUDE_FROM_ALL)
add_subdirectory(${LSFG_SOURCE}/framegen framegen EXCLUDE_FROM_ALL)

add_library(novalsfg SHARED novalsfg.cpp ${LSFG_SOURCE}/src/extract/trans.cpp)
set_target_properties(novalsfg PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(novalsfg PRIVATE ${LSFG_SOURCE}/include)
target_link_libraries(novalsfg PRIVATE lsfg-vk-framegen pe-parse dxbc volk)
if(ANDROID)
  target_link_libraries(novalsfg PRIVATE android log)
endif()
# Export only the nova_lsfg_* C API; keep volk, STL and helpers private.
target_link_options(novalsfg PRIVATE -Wl,--exclude-libs,ALL -Wl,--no-undefined
  "-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/novalsfg.map")
