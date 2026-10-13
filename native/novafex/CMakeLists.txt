# Nova PS5 FEXCore bridge. Built inside the FEX source tree (Source/Tools/NovaFex) so it uses
# FEX's own targets and generated headers; see .github/workflows/novafex.yml.
# libnovafex.so links FEXCore and its dependencies statically and exports only novafex.h.
add_library(novafex SHARED novafex.cpp novafex_arm64.S)
target_include_directories(novafex PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_include_directories(novafex PRIVATE ${CMAKE_BINARY_DIR}/generated)
target_link_libraries(novafex PRIVATE FEXCore Common JemallocDummy ${PTHREAD_LIB})
set_target_properties(novafex PROPERTIES CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
target_link_options(novafex PRIVATE -Wl,--exclude-libs,ALL -Wl,--no-undefined -Wl,-z,now)
target_compile_options(novafex PRIVATE -fno-omit-frame-pointer)

if(CMAKE_SYSTEM_NAME STREQUAL "Android")
	# Android (bionic): 16 KB-page compatible, libc++ kept private, Android log for diagnostics.
	target_link_options(novafex PRIVATE -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 -static-libstdc++)
	target_link_libraries(novafex PRIVATE log dl)

	# Static bionic test binary: runs on any Linux arm64 kernel without Android's linker.
	add_executable(novafex_test_static test/novafex_test.cpp novafex.cpp novafex_arm64.S)
	target_include_directories(novafex_test_static PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_BINARY_DIR}/generated)
	target_link_libraries(novafex_test_static PRIVATE FEXCore Common JemallocDummy)
	target_compile_definitions(novafex_test_static PRIVATE NOVAFEX_STATIC_TEST=1)
	target_link_options(novafex_test_static PRIVATE -static -static-libstdc++)
else()
	add_executable(novafex_test test/novafex_test.cpp)
	target_link_libraries(novafex_test PRIVATE novafex ${PTHREAD_LIB} dl)
	target_link_options(novafex_test PRIVATE -rdynamic)
	set_target_properties(novafex_test PROPERTIES BUILD_RPATH "$ORIGIN")
endif()
