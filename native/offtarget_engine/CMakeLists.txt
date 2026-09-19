cmake_minimum_required(VERSION 3.20)

project(offtarget_engine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(
    OFFTARGET_RUNTIME_OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_SOURCE_DIR}/../bin"
    CACHE PATH
    "Directory for offtarget-engine binaries"
)
set(
    CMAKE_RUNTIME_OUTPUT_DIRECTORY
    "${OFFTARGET_RUNTIME_OUTPUT_DIRECTORY}"
)
set(
    CMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG
    "${OFFTARGET_RUNTIME_OUTPUT_DIRECTORY}"
)
set(
    CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE
    "${OFFTARGET_RUNTIME_OUTPUT_DIRECTORY}"
)
set(
    CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO
    "${OFFTARGET_RUNTIME_OUTPUT_DIRECTORY}"
)
set(
    CMAKE_RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL
    "${OFFTARGET_RUNTIME_OUTPUT_DIRECTORY}"
)

add_library(
    offtarget_core
    STATIC
    src/alignment.cpp
    src/build_index.cpp
    src/fasta.cpp
    src/genome_index.cpp
    src/json_writer.cpp
    src/pam.cpp
    src/seed_plan.cpp
    src/search.cpp
)
target_include_directories(
    offtarget_core
    PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
if(WIN32)
    target_link_libraries(offtarget_core PUBLIC Psapi)
endif()

if(MSVC)
    target_compile_options(offtarget_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(
        offtarget_core
        PRIVATE
        -Wall
        -Wextra
        -Wpedantic
    )
endif()

add_executable(offtarget-engine src/main.cpp)
target_link_libraries(offtarget-engine PRIVATE offtarget_core)

option(OFFTARGET_BUILD_TESTS "Build native unit tests" ON)
if(OFFTARGET_BUILD_TESTS)
    enable_testing()
    add_executable(offtarget-engine-tests tests/unit_tests.cpp)
    target_link_libraries(offtarget-engine-tests PRIVATE offtarget_core)
    add_test(NAME offtarget-engine-tests COMMAND offtarget-engine-tests)
endif()
