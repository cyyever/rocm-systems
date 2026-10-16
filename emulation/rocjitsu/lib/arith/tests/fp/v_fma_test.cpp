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

// Raw encodings from rocjitsu shared/fp_mode.h's default-mode FP32 FMA rules.
// The finite witness distinguishes fused arithmetic from a rounded multiply plus add.
template <int Lanes, typename Call> static void check_fma32_encodings(Call call) {
  using namespace rocjitsu::arith::test;
  const struct {
    uint32_t a, b, c, expected;
  } cases[] = {
      {0x3f800001, 0x3f7ffffe, 0xbf800000, 0xa8800000}, // Fused cancellation.
      {0, 0x7f800000, 0x7fc12345, 0xffc00000},          // Invalid product beats C NaN.
      {0x7f800003, 0x7fc00005, 0, 0x7fc00003},          // First NaN, quieted.
      {0x80000000, 0x3f800000, 0x80000000, 0x80000000}, // Matching negative zeros.
      {3, 0x3f000000, 0, 2},                            // Subnormal halfway rounds to even.
  };
  for (uint64_t cpu : supported_cpu_levels()) {
    for (uint64_t semantics : {RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL_ALLOW_LOOSE,
                               RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL_NO_FP_STATUS}) {
      for (const auto &sample : cases) {
        SCOPED_TRACE(testing::Message() << cpu << '/' << semantics << '/' << sample.a);
        Registers<4, Lanes> r;
        r.v[0][0] = sample.a;
        r.v[1][0] = sample.b;
        r.v[2][0] = sample.c;
        ASSERT_EQ(call(cpu | semantics, 1, 0, r.v + 3, r.v, r.v + 1, r.v + 2, nullptr),
                  RJ_ARITH_SUCCESS);
        EXPECT_EQ(r.v[3][0], sample.expected);
      }
    }
  }
}

// Check exact FP32 encodings for both wave widths against the same model cases.
TEST(FpFmaF32W32Gfx12, ExactEncodings) { check_fma32_encodings<32>(rj_arith_v_fma_f32_w32_gfx12); }
TEST(FpFmaF32W64Gfx12, ExactEncodings) { check_fma32_encodings<64>(rj_arith_v_fma_f32_w64_gfx12); }

// Guard ordinary midpoints and the finite/infinite boundary against double rounding.
TEST(FpFmaF16W32Gfx12, RoundingBoundaries) {
  using namespace rocjitsu::arith::test;
  struct Case {
    uint16_t a, b, c, expected, saturated;
  };
  const Case cases[] = {
      {0x32f9, 0xb0b7, 0x3780, 0x36fd, 0x36fd}, {0x4300, 0x7492, 0x9400, 0x7bff, 0x7bff},
      {0xc300, 0x7492, 0x1400, 0xfbff, 0xfbff}, {0x7bff, 0x4000, 0, 0x7c00, 0x7bff},
      {0xfbff, 0x4000, 0, 0xfc00, 0xfbff},      {0x7c00, 0x3c00, 0, 0x7c00, 0x7c00},
      {0xfc00, 0x3c00, 0, 0xfc00, 0xfc00},
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
  for (uint64_t flag :
       {RJ_ARITH_FP_FLUSH_INPUT_DENORMALS, RJ_ARITH_FP_FLUSH_OUTPUT_DENORMALS,
        RJ_ARITH_FP_IEEE_MODE, RJ_ARITH_FP_DX10_CLAMP_OFF, RJ_ARITH_FP_ROUND_UP,
        RJ_ARITH_FP_ROUND_DOWN, RJ_ARITH_FP_ROUND_ZERO, RJ_ARITH_FP_FLUSH_INPUT_DENORMALS_F16,
        RJ_ARITH_FP_PRESERVE_INPUT_DENORMALS_F16}) {
    EXPECT_EQ(rj_arith_v_fma_f16_w32_gfx12(flag, 1, 0, nullptr, nullptr, nullptr, nullptr, nullptr),
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
      {0x7e01, 0x7c03, 0, 0x7e01, 0},      // Earlier qNaN beats later sNaN.
      {0x3c00, 0x7e05, 0x7d07, 0x7e05, 0}, // B NaN beats C sNaN.
      {0x7c00, 0x3c00, 0xfc00, 0xfe00, 0}, // Opposite infinities.
      {0x8000, 0x3c00, 0x8000, 0x8000, 0}, // Matching negative zeros.
      {0x8001, 0x3800, 0, 0x8000, 0},      // Negative halfway underflow.
      {0x0001, 0x3800, 0, 0x0000, 0},      // Tie rounds to even zero.
      {0x0003, 0x3800, 0, 0x0002, 0},      // Tie rounds up to even subnormal.

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
template <int Lanes, typename Call> static void check_fma16_status(Call call) {
  using namespace rocjitsu::arith::test;
  using Mask = std::conditional_t<Lanes == 32, uint32_t, uint64_t>;
  constexpr Mask high_lane = Mask(1) << (Lanes - 1);
  const struct {
    uint16_t a, b, c, expected;
    uint32_t causes;
    uint64_t flags;
  } cases[] = {
      {0x3c00, 0x3c00, 0, 0x3c00, 0, 0},
      {0x3c01, 0x3c01, 0, 0x3c02, RJ_ARITH_EXCEPTION_INEXACT, 0},
      {1, 0x3800, 0, 0,
       RJ_ARITH_EXCEPTION_INPUT_DENORM | RJ_ARITH_EXCEPTION_UNDERFLOW | RJ_ARITH_EXCEPTION_INEXACT,
       0},
      // gfx1201 VOP3 lane 31, EXEC=0x80000000, MODE=0x010000f0.
      {0x3c00, 0x3c00, 0x7c01, 0x7e01, RJ_ARITH_EXCEPTION_INVALID, 0},
      {0x3c00, 0x7c00, 0xfc00, 0xfe00, RJ_ARITH_EXCEPTION_INVALID, 0},
      {0, 0x7c00, 1, 0xfe00, RJ_ARITH_EXCEPTION_INVALID, 0},

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
      Registers<4, Lanes> r;
      r.v[0][Lanes - 1] = sample.a;
      r.v[1][Lanes - 1] = sample.b;
      r.v[2][Lanes - 1] = sample.c;
      uint32_t status = preserved;
      ASSERT_EQ(call(cpu | RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL | sample.flags, high_lane, 0,
                     r.v + 3, r.v, r.v + 1, r.v + 2, &status),
                RJ_ARITH_SUCCESS);
      EXPECT_EQ(uint16_t(r.v[3][Lanes - 1]), sample.expected);
      EXPECT_EQ(status, preserved | sample.causes);
    }
    // Each exceptional lane contributes independently, and masked lanes contribute nothing.
    for (Mask exec_mask : {Mask(0), Mask(1), high_lane, high_lane | Mask(1)}) {
      SCOPED_TRACE(testing::Message() << "cpu=" << cpu << " exec_mask=" << exec_mask);
      Registers<4, Lanes> r;
      r.v[0][0] = 0;
      r.v[1][0] = 0x7c00;
      r.v[2][0] = 0;
      r.v[0][Lanes - 1] = 0x7bff;
      r.v[1][Lanes - 1] = 0x4000;
      r.v[2][Lanes - 1] = 0;
      uint32_t status = preserved;
      ASSERT_EQ(call(cpu | RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL, exec_mask, 0, r.v + 3, r.v,
                     r.v + 1, r.v + 2, &status),
                RJ_ARITH_SUCCESS);
      uint32_t expected = preserved;
      if (exec_mask & 1) {
        expected |= RJ_ARITH_EXCEPTION_INVALID;
      }
      if (exec_mask & high_lane) {
        expected |= RJ_ARITH_EXCEPTION_OVERFLOW | RJ_ARITH_EXCEPTION_INEXACT;
      }
      EXPECT_EQ(status, expected);
    }
  }
}

// The architectural causes accumulate identically across both EXEC widths.
TEST(FpFmaF16W32Gfx12, StatusBoundariesAndExec) {
  check_fma16_status<32>(rj_arith_v_fma_f16_w32_gfx12);
}
TEST(FpFmaF16W64Gfx12, StatusBoundariesAndExec) {
  check_fma16_status<64>(rj_arith_v_fma_f16_w64_gfx12);
}
