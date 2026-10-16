// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Fused arithmetic across FP widths, aliases, and guest controls.
// Shared family test runner; instruction-specific cases supply operations and expectations.

#pragma once

#include "common/cpu.h"
#include "common/registers.h"
#include "common/semantics.h"
#include "fp/elementwise.h"
#include "fp/fma_reference.h"
#include "fp/reference.h"
#include "rj_arith/rj_arith.h"

#include <gtest/gtest.h>
#include <stdint.h>
#include <type_traits>

namespace rocjitsu::arith::test {

// Exercise FP32 FMA arithmetic, modifiers, EXEC, aliases and API errors.
// For these normal inputs, the inherited model agrees with std::fma;
// exceptional encodings are covered separately by literal witnesses.
template <int Lanes, typename Call> void check_fma(Call call, bool gfx12) {
  constexpr int Width = 32;
  using Mask = std::conditional_t<Lanes == 32, uint32_t, uint64_t>;
  using Registers = rocjitsu::arith::test::Registers<10, Lanes>;
  Registers input = make_fp_inputs<Width, Lanes>();

  rocjitsu::arith::test::expect_invalid_fp_requests([&](uint64_t flags, uint64_t mode) {
    Registers r = input;
    int aliasing_offset = 6;
    Mask exec_mask = ~Mask(0);
    uint32_t fp_status = 0x80000000U;

    int result =
        call(flags, exec_mask, mode, r.v + aliasing_offset, r.v, r.v + 2, r.v + 4, &fp_status);
    r.expect_preserved(input, 0, 0);
    EXPECT_EQ(fp_status, 0x80000000U);
    EXPECT_EQ(call(flags, exec_mask, mode, nullptr, nullptr, nullptr, nullptr, &fp_status), result);
    return result;
  });

  // FP32 exercises DPP8, OMOD and combined ABS/NEG in addition to the
  // basic modifiers common to both formats. gfx11 ignores OMOD under the
  // default guest FP mode; compute_fma_expected accounts for that difference.
  const uint64_t modes[] = {0,
                            RJ_ARITH_ALU_NEG_A,
                            RJ_ARITH_ALU_CLAMP,
                            RJ_ARITH_DPP8 | (0x53977ULL << RJ_ARITH_DPP8_SELECT_SHIFT),
                            RJ_ARITH_DPP8 | (0x53977ULL << RJ_ARITH_DPP8_SELECT_SHIFT) |
                                RJ_ARITH_DPP_FI | RJ_ARITH_ALU_NEG_A,
                            RJ_ARITH_ALU_OMOD_2,
                            RJ_ARITH_ALU_ABS_B | RJ_ARITH_ALU_NEG_A};
  const int aliasing_offsets[] = {6, 0, 2, 4};

  const auto cpu_levels = rocjitsu::arith::test::supported_cpu_levels();
  for (uint64_t cpu : cpu_levels) {
    for (uint64_t semantics : rocjitsu::arith::test::semantics_modes()) {
      for (uint64_t mode : modes) {
        for (Mask exec_mask :
             {Mask(0), ~Mask(0), Mask(0xaaaaaaaaaaaaaaaaULL), Mask(1) << (Lanes - 1)}) {
          for (int aliasing_offset : aliasing_offsets) {
            SCOPED_TRACE(::testing::Message() << cpu << '/' << semantics << '/' << mode << '/'
                                              << exec_mask << '/' << aliasing_offset);
            Registers r = input, expected_registers = input;
            uint64_t flags = cpu | semantics;
            uint32_t fp_status = 0x80000000U;

            int result = call(flags, exec_mask, mode, r.v + aliasing_offset, r.v, r.v + 2, r.v + 4,
                              &fp_status);
            if (semantics == RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL) {
              EXPECT_EQ(result, RJ_ARITH_ERROR_UNSUPPORTED_FP_STATUS);
              r.expect_preserved(input, 0, 0);
              EXPECT_EQ(fp_status, 0x80000000U);
              continue;
            }
            ASSERT_EQ(result, RJ_ARITH_SUCCESS);
            EXPECT_EQ(fp_status, 0x80000000U);
            compute_fma_expected<Width>(input, exec_mask, mode, aliasing_offset, expected_registers,
                                        gfx12);

            expect_fp_result<Width>(input, r, expected_registers, exec_mask, aliasing_offset, mode,
                                    semantics,
                                    /*atol=*/1e-5,
                                    /*rtol=*/1e-6);
          }
        }
      }
    }
  }
}

} // namespace rocjitsu::arith::test
