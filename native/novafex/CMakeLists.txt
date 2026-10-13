# Nova PS5 FEXCore bridge. Built inside the FEX source tree (Source/Tools/NovaFex) so it uses
# FEX's own targets and generated headers; see .github/workflows/novafex.yml.
add_library(novafex STATIC novafex.cpp novafex_arm64.S)
target_include_directories(novafex PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_include_directories(novafex PRIVATE ${CMAKE_BINARY_DIR}/generated)
target_link_libraries(novafex PUBLIC FEXCore Common JemallocDummy ${PTHREAD_LIB})

add_executable(novafex_test test/novafex_test.cpp)
target_link_libraries(novafex_test PRIVATE novafex)
