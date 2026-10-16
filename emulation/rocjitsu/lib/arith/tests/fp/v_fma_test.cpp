// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// FMA arithmetic and storage contracts for both wave sizes and element types.

#include "common/cpu.h"
#include "common/registers.h"
#include "fp/fma_test.h"
#include "rj_arith/rj_arith.h"

// Check FP16 arithmetic for Wave32.
TEST(FpFmaF16W32Gfx12, Arithmetic) {
  rocjitsu::arith::test::check_fma16<32>(rj_arith_v_fma_f16_w32_gfx12);
}

// Check FP16 arithmetic for Wave64.
TEST(FpFmaF16W64Gfx12, Arithmetic) {
  rocjitsu::arith::test::check_fma16<64>(rj_arith_v_fma_f16_w64_gfx12);
}

// Check FP32 arithmetic for Wave32.
TEST(FpFmaF32W32Gfx12, Arithmetic) {
  rocjitsu::arith::test::check_fma32<32>(rj_arith_v_fma_f32_w32_gfx12);
}

// Check FP32 arithmetic for Wave64.
TEST(FpFmaF32W64Gfx12, Arithmetic) {
  rocjitsu::arith::test::check_fma32<64>(rj_arith_v_fma_f32_w64_gfx12);
}

// Guard the finite/infinite boundary against double rounding, on every CPU path.
TEST(FpFmaF16W32Gfx12, OverflowBoundary) {
  using namespace rocjitsu::arith::test;
  struct Case {
    uint16_t a, b, c, expected, saturated;
  };
  const Case cases[] = {
      {0x4300, 0x7492, 0x9400, 0x7bff, 0x7bff}, {0xc300, 0x7492, 0x1400, 0xfbff, 0xfbff},
      {0x7bff, 0x4000, 0, 0x7c00, 0x7bff},      {0xfbff, 0x4000, 0, 0xfc00, 0xfbff},
      {0x7c00, 0x3c00, 0, 0x7c00, 0x7c00},      {0xfc00, 0x3c00, 0, 0xfc00, 0xfc00},
  };
  for (uint64_t cpu : supported_cpu_levels()) {
    for (uint64_t semantics :
         {RJ_ARITH_SEMANTICS_LOOSE, RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL_ALLOW_LOOSE}) {
      for (uint64_t fp_flags : {uint64_t{0}, RJ_ARITH_FP16_OVFL}) {
        for (const auto &sample : cases) {
          SCOPED_TRACE(testing::Message() << "cpu=" << cpu << " semantics=" << semantics
                                          << " fp_flags=" << fp_flags << " a=" << sample.a);
          Registers<4, 32> r;
          r.v[0][0] = sample.a;
          r.v[1][0] = sample.b;
          r.v[2][0] = sample.c;
          ASSERT_EQ(rj_arith_v_fma_f16_w32_gfx12(cpu | semantics | fp_flags, 1, 0, r.v + 3, r.v,
                                                 r.v + 1, r.v + 2, nullptr),
                    RJ_ARITH_SUCCESS);
          EXPECT_EQ(uint16_t(r.v[3][0]), fp_flags ? sample.saturated : sample.expected);
        }
      }
    }
  }
}

// Reject controls not implemented by this slice, before accessing operands.
TEST(FpFmaF16W32Gfx12, UnsupportedGuestControls) {
  for (uint64_t flag : {RJ_ARITH_FP_FLUSH_INPUT_DENORMALS, RJ_ARITH_FP_FLUSH_OUTPUT_DENORMALS,
                        RJ_ARITH_FP_IEEE_MODE}) {
    EXPECT_EQ(rj_arith_v_fma_f16_w32_gfx12(flag, 1, 0, nullptr, nullptr, nullptr, nullptr, nullptr),
              RJ_ARITH_ERROR_INVALID_FLAGS);
    EXPECT_EQ(
        rj_arith_v_wmma_f32_16x16x16_f16_w32_gfx12(flag, 0, nullptr, nullptr, nullptr, nullptr),
        RJ_ARITH_ERROR_INVALID_FLAGS);
  }
}

// Raw encodings from rocjitsu's gfx12 FP16 FMA model: rounding and NaN precedence.
TEST(FpFmaF16W32Gfx12, ExactEncodings) {
  using namespace rocjitsu::arith::test;
  const struct {
    uint16_t a, b, c, expected;
    uint64_t flags;
  } cases[] = {
      {0x4782, 0xda00, 0x03e1, 0xe5a1, 0},
      {0, 0x7c00, 0x7e01, 0xfe00, 0},
      {0x7c03, 0x7e01, 0, 0x7e03, 0},
      {0x7bff, 0x7bff, 0, 0x7c00, 0},
      {0x7bff, 0x7bff, 0, 0x7bff, RJ_ARITH_FP16_OVFL},
      {0x3c00, 0x3c00, 0xbc00, 0, 0},
      {1, 0x3c00, 0, 1, 0},
  };
  for (uint64_t cpu : supported_cpu_levels()) {
    for (uint64_t semantics : {RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL_ALLOW_LOOSE,
                               RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL_NO_FP_STATUS,
                               RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL}) {
      for (const auto &sample : cases) {
        SCOPED_TRACE(testing::Message()
                     << "cpu=" << cpu << " semantics=" << semantics << " a=" << sample.a);
        Registers<4, 32> r;
        r.v[0][0] = sample.a;
        r.v[1][0] = sample.b;
        r.v[2][0] = sample.c;
        uint32_t status = 0;
        ASSERT_EQ(rj_arith_v_fma_f16_w32_gfx12(cpu | semantics | sample.flags, 1, 0, r.v + 3, r.v,
                                               r.v + 1, r.v + 2, &status),
                  RJ_ARITH_SUCCESS);
        EXPECT_EQ(uint16_t(r.v[3][0]), sample.expected);
      }
    }
  }
}

// gfx1201 WAVE_EXCP_FLAG_USER observations under MODE=0xf0 (RNE, preserve denormals).
// These literal cases distinguish tininess, NaN suppression, and finite saturation.
TEST(FpFmaF16W32Gfx12, StatusBoundariesAndExec) {
  using namespace rocjitsu::arith::test;
  const struct {
    uint16_t a, b, c, expected;
    uint32_t causes;
    uint64_t flags;
  } cases[] = {
      {1, 0xb400, 0x0400, 0x0400, RJ_ARITH_EXCEPTION_INPUT_DENORM | RJ_ARITH_EXCEPTION_INEXACT, 0},
      {0x0400, 0x3bff, 0, 0x0400, RJ_ARITH_EXCEPTION_UNDERFLOW | RJ_ARITH_EXCEPTION_INEXACT, 0},
      {1, 0x3c00, 0, 1, RJ_ARITH_EXCEPTION_INPUT_DENORM, 0},
      {1, 0x3c00, 0x7e00, 0x7e00, 0, 0},
      {1, 0x7c00, 0, 0x7c00, RJ_ARITH_EXCEPTION_INPUT_DENORM, 0},
      {0x7c01, 0x3c00, 0, 0x7e01, RJ_ARITH_EXCEPTION_INVALID, 0},
      {0x7e02, 0x7c01, 0, 0x7e02, RJ_ARITH_EXCEPTION_INVALID, 0},
      {0x7c00, 0x3c00, 0xfc00, 0xfe00, RJ_ARITH_EXCEPTION_INVALID, 0},
      {0x7bff, 0x4000, 0, 0x7bff, RJ_ARITH_EXCEPTION_OVERFLOW | RJ_ARITH_EXCEPTION_INEXACT,
       RJ_ARITH_FP16_OVFL},
  };
  constexpr uint32_t preserved = 0x80000000U | RJ_ARITH_EXCEPTION_FLOAT_DIV0;
  for (uint64_t cpu : supported_cpu_levels()) {
    for (const auto &sample : cases) {
      SCOPED_TRACE(testing::Message() << "cpu=" << cpu << " a=" << sample.a << " b=" << sample.b);
      Registers<4, 32> r;
      r.v[0][31] = sample.a;
      r.v[1][31] = sample.b;
      r.v[2][31] = sample.c;
      uint32_t status = preserved;
      ASSERT_EQ(
          rj_arith_v_fma_f16_w32_gfx12(cpu | RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL | sample.flags,
                                       0x80000000U, 0, r.v + 3, r.v, r.v + 1, r.v + 2, &status),
          RJ_ARITH_SUCCESS);
      EXPECT_EQ(uint16_t(r.v[3][31]), sample.expected);
      EXPECT_EQ(status, preserved | sample.causes);
    }
    // Each exceptional lane contributes independently, and masked lanes contribute nothing.
    for (uint32_t exec_mask : {0U, 1U, 0x80000000U, 0x80000001U}) {
      Registers<4, 32> r;
      r.v[0][0] = 0;
      r.v[1][0] = 0x7c00;
      r.v[2][0] = 0;
      r.v[0][31] = 0x7bff;
      r.v[1][31] = 0x4000;
      r.v[2][31] = 0;
      uint32_t status = preserved;
      ASSERT_EQ(rj_arith_v_fma_f16_w32_gfx12(cpu | RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL,
                                             exec_mask, 0, r.v + 3, r.v, r.v + 1, r.v + 2, &status),
                RJ_ARITH_SUCCESS);
      uint32_t expected = preserved;
      if (exec_mask & 1) {
        expected |= RJ_ARITH_EXCEPTION_INVALID;
      }
      if (exec_mask & 0x80000000U) {
        expected |= RJ_ARITH_EXCEPTION_OVERFLOW | RJ_ARITH_EXCEPTION_INEXACT;
      }
      EXPECT_EQ(status, expected);
    }
  }
}
