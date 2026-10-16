# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT

# Build and register the standalone CPU-feature diagnostic.

add_executable(rj_arith_cpuinfo cpuinfo.cpp)
target_link_libraries(rj_arith_cpuinfo PRIVATE rj_arith)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
        rj_arith_cpuinfo
        PRIVATE -Wall -Wextra -Werror -pedantic
    )
endif()
if(RJ_INSTALL_TESTS)
    rj_install_test_target(rj_arith_cpuinfo)
endif()
rj_add_test(
    NAME "rj_arith.cpuinfo"
    COMMAND rj_arith_cpuinfo
    INSTALL_COMMAND bin/rj_arith_cpuinfo
)
