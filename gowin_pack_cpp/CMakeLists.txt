cmake_minimum_required(VERSION 3.20)
project(gowin_pack VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Options
option(GOWIN_PACK_STATIC "Build static binary" OFF)

# Fetch dependencies
include(FetchContent)

# nlohmann/json for netlist parsing
FetchContent_Declare(
    json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
)

# CLI11 for argument parsing
FetchContent_Declare(
    cli11
    GIT_REPOSITORY https://github.com/CLIUtils/CLI11.git
    GIT_TAG v2.4.1
)

# msgpack-c for chipdb deserialization
FetchContent_Declare(
    msgpack
    GIT_REPOSITORY https://github.com/msgpack/msgpack-c.git
    GIT_TAG cpp-7.0.0
)

FetchContent_MakeAvailable(json cli11 msgpack)

# Find zlib for decompression
find_package(ZLIB REQUIRED)

# Main executable
add_executable(gowin_pack
    src/main.cpp
    src/chipdb.cpp
    src/netlist.cpp
    src/bitstream.cpp
    src/route.cpp
    src/place.cpp
    src/fuses.cpp
    src/bels/dsp.cpp
)

target_include_directories(gowin_pack PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${msgpack_SOURCE_DIR}/include
)

target_link_libraries(gowin_pack PRIVATE
    nlohmann_json::nlohmann_json
    CLI11::CLI11
    ZLIB::ZLIB
)

# Compiler warnings
target_compile_options(gowin_pack PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)

# Static linking for distribution
if(GOWIN_PACK_STATIC)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        target_link_options(gowin_pack PRIVATE -static -static-libgcc -static-libstdc++)
    elseif(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        target_link_options(gowin_pack PRIVATE -static)
    endif()
endif()

# Install target
install(TARGETS gowin_pack DESTINATION bin)

# Tests (optional)
option(BUILD_TESTS "Build tests" OFF)
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
