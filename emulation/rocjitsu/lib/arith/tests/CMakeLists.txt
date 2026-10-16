# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT

# Define instruction-family test binaries and discover their individual GoogleTest cases.
# Shared test utilities, standalone header checks, and cpuinfo are wired here.

include(GoogleTest)

# One explicit source, executable and arithmetic test per instruction.
foreach(
    instruction
    IN
    ITEMS
        v_swmmac_bf16_16x16x32_bf16_w32
        v_swmmac_bf16_16x16x32_bf16_w64
        v_swmmac_f16_16x16x32_f16_w32
        v_swmmac_f16_16x16x32_f16_w64
        v_swmmac_f32_16x16x32_bf16_w32
        v_swmmac_f32_16x16x32_bf16_w64
        v_swmmac_f32_16x16x32_bf8_bf8_w32
        v_swmmac_f32_16x16x32_bf8_bf8_w64
        v_swmmac_f32_16x16x32_bf8_fp8_w32
        v_swmmac_f32_16x16x32_bf8_fp8_w64
        v_swmmac_f32_16x16x32_f16_w32
        v_swmmac_f32_16x16x32_f16_w64
        v_swmmac_f32_16x16x32_fp8_bf8_w32
        v_swmmac_f32_16x16x32_fp8_bf8_w64
        v_swmmac_f32_16x16x32_fp8_fp8_w32
        v_swmmac_f32_16x16x32_fp8_fp8_w64
        v_swmmac_i32_16x16x32_iu4_w32
        v_swmmac_i32_16x16x32_iu4_w64
        v_swmmac_i32_16x16x32_iu8_w32
        v_swmmac_i32_16x16x32_iu8_w64
        v_swmmac_i32_16x16x64_iu4_w32
        v_swmmac_i32_16x16x64_iu4_w64
        v_wmma_bf16_16x16x16_bf16_w32
        v_wmma_bf16_16x16x16_bf16_w32_gfx12
        v_wmma_bf16_16x16x16_bf16_w64
        v_wmma_bf16_16x16x16_bf16_w64_gfx12
        v_wmma_f16_16x16x16_f16_w32
        v_wmma_f16_16x16x16_f16_w32_gfx12
        v_wmma_f16_16x16x16_f16_w64
        v_wmma_f16_16x16x16_f16_w64_gfx12
        v_wmma_f32_16x16x16_bf16_w32
        v_wmma_f32_16x16x16_bf16_w32_gfx12
        v_wmma_f32_16x16x16_bf16_w64
        v_wmma_f32_16x16x16_bf16_w64_gfx12
        v_wmma_f32_16x16x16_bf8_bf8_w32
        v_wmma_f32_16x16x16_bf8_bf8_w64
        v_wmma_f32_16x16x16_bf8_fp8_w32
        v_wmma_f32_16x16x16_bf8_fp8_w64
        v_wmma_f32_16x16x16_f16_w32
        v_wmma_f32_16x16x16_f16_w32_gfx12
        v_wmma_f32_16x16x16_f16_w64
        v_wmma_f32_16x16x16_f16_w64_gfx12
        v_wmma_f32_16x16x16_fp8_bf8_w32
        v_wmma_f32_16x16x16_fp8_bf8_w64
        v_wmma_f32_16x16x16_fp8_fp8_w32
        v_wmma_f32_16x16x16_fp8_fp8_w64
        v_wmma_i32_16x16x16_iu4_w32
        v_wmma_i32_16x16x16_iu4_w32_gfx12
        v_wmma_i32_16x16x16_iu4_w64
        v_wmma_i32_16x16x16_iu4_w64_gfx12
        v_wmma_i32_16x16x16_iu8_w32
        v_wmma_i32_16x16x16_iu8_w32_gfx12
        v_wmma_i32_16x16x16_iu8_w64
        v_wmma_i32_16x16x16_iu8_w64_gfx12
        v_wmma_i32_16x16x32_iu4_w32
        v_wmma_i32_16x16x32_iu4_w64
)
    string(REGEX REPLACE "^v_" "" test_name "${instruction}")
    set(target "rj_arith_${test_name}_test")
    add_executable(${target} wmma/${instruction}_test.cpp)
    target_link_libraries(${target} PRIVATE rj_arith GTest::gtest_main)
    target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    rj_configure_target(${target} WARNINGS)
    rj_add_gtest_tests(${target} TEST_PREFIX "rj_arith.")
    if(RJ_INSTALL_TESTS)
        file(APPEND "${RJ_INSTALL_CTEST_FILE}" "include(\"${target}.cmake\")\n")
    endif()
endforeach()

# Group related operations, element types, wave widths and architectures; retain one test per entry point.
foreach(
    mnemonic
    IN
    ITEMS
        v_add_sub
        v_round_f64
        v_div_fixup
        v_div_fmas
        v_div_scale
        v_fma_dx9_zero
        v_fma
        v_fma_mix
        v_fmaak
        v_fmac
        v_fmamk
        v_exponent
        v_min_max_med3
        v_min_max_med3_num
        v_min_max
        v_min_max_num
        v_minimum_maximum3
        v_minimum_maximum
        v_minimummaximum_maximumminimum
        v_minmax_maxmin
        v_minmax_maxmin_num
        v_mul_dx9_zero_f32
        v_mul
        v_pk_add_mul_f16
        v_pk_fma_f16
        v_pk_fmac_f16
        v_pk_selection_f16
        v_rcp_rsq_sqrt_f64
)
    string(REGEX REPLACE "^v_" "" test_name "${mnemonic}")
    set(target "rj_arith_${test_name}_test")
    add_executable(${target} fp/${mnemonic}_test.cpp)
    target_link_libraries(${target} PRIVATE rj_arith GTest::gtest_main)
    target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    rj_configure_target(${target} WARNINGS)
    rj_add_gtest_tests(${target} TEST_PREFIX "rj_arith.")
    if(RJ_INSTALL_TESTS)
        file(APPEND "${RJ_INSTALL_CTEST_FILE}" "include(\"${target}.cmake\")\n")
    endif()
endforeach()

# Related comparison predicates share a binary; every entry point has its own test.
foreach(
    family
    IN
    ITEMS
        constant
        integer_equality
        integer_ordering
        class
        float_equality
        float_ordered
        float_unordered
)
    set(target "rj_arith_compare_${family}_test")
    add_executable(${target} compare/${family}_test.cpp)
    target_link_libraries(${target} PRIVATE rj_arith GTest::gtest_main)
    target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    rj_configure_target(${target} WARNINGS)
    rj_add_gtest_tests(${target} TEST_PREFIX "rj_arith.")
    if(RJ_INSTALL_TESTS)
        file(APPEND "${RJ_INSTALL_CTEST_FILE}" "include(\"${target}.cmake\")\n")
    endif()
endforeach()

# Dot-product formats retain family-specific arithmetic and status expectations.
foreach(family IN ITEMS integer fp8 half dot2)
    set(target "rj_arith_dot_${family}_test")
    add_executable(${target} dot/${family}_test.cpp)
    target_link_libraries(${target} PRIVATE rj_arith GTest::gtest_main)
    target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    rj_configure_target(${target} WARNINGS)
    rj_add_gtest_tests(${target} TEST_PREFIX "rj_arith.")
    if(RJ_INSTALL_TESTS)
        file(APPEND "${RJ_INSTALL_CTEST_FILE}" "include(\"${target}.cmake\")\n")
    endif()
endforeach()

# Math families share unary layouts, with independent loose and exact references.
foreach(
    family
    IN
    ITEMS round root_reciprocal log_exp decompose trig rcp_iflag preop
)
    set(target "rj_arith_math_${family}_test")
    add_executable(${target} math/${family}_test.cpp)
    target_link_libraries(${target} PRIVATE rj_arith GTest::gtest_main)
    target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    rj_configure_target(${target} WARNINGS)
    rj_add_gtest_tests(${target} TEST_PREFIX "rj_arith.")
    if(RJ_INSTALL_TESTS)
        file(APPEND "${RJ_INSTALL_CTEST_FILE}" "include(\"${target}.cmake\")\n")
    endif()
endforeach()

# Infrastructure has no all-entry-point registry; contracts live in family helpers.
add_executable(rj_arith_cpu_test common/cpu_test.cpp)
target_link_libraries(rj_arith_cpu_test PRIVATE rj_arith GTest::gtest_main)
target_include_directories(
    rj_arith_cpu_test
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${rj_arith_source_dir}/src
)
rj_configure_target(rj_arith_cpu_test WARNINGS)
rj_add_gtest_tests(rj_arith_cpu_test TEST_PREFIX "rj_arith.")
if(RJ_INSTALL_TESTS)
    file(
        APPEND "${RJ_INSTALL_CTEST_FILE}"
        "include(\"rj_arith_cpu_test.cmake\")\n"
    )
endif()
add_subdirectory(headers)

# Standalone utilities.
add_subdirectory(cpuinfo)
