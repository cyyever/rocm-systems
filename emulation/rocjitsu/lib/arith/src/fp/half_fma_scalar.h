// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Scalar RDNA3/gfx12 FP16 FMA with default guest controls and optional finite saturation.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include "rj_arith/rj_arith.h"

#include "common/float_formats.h"
#include "common/internal.h"
#include "fp/fma_integer.h"

#include <cmath>
#include <stdint.h>

namespace rocjitsu::arith {

// Round finite FP64 to nearest-even FP16, optionally saturating finite overflow.
inline uint16_t half_fma_narrow(double value, bool saturate) {
  // Adapted from rocjitsu mixed_fma_simd.h: round_finite_f16_simd.
  uint64_t bits = double_bits(value);
  int exponent = (bits >> 52) & 2047;
  uint16_t sign = uint16_t((bits >> 48) & 0x8000);
  if (exponent < 998) {
    return sign;
  }
  if (exponent > 1038) {
    return sign | (saturate ? 0x7bff : 0x7c00);
  }
  int shift = exponent < 1009 ? 1051 - exponent : 42;
  uint64_t significand = (bits & 0x000fffffffffffffULL) | (1ULL << 52);
  uint64_t rounded = significand >> shift;
  if (exponent >= 1009) {
    rounded += (exponent - 1009) << 10;
  }
  uint64_t remainder = significand & ((1ULL << shift) - 1);
  uint64_t halfway = 1ULL << (shift - 1);
  rounded += remainder > halfway || (remainder == halfway && (rounded & 1));
  if (rounded >= 0x7c00) {
    rounded = saturate ? 0x7bff : 0x7c00;
  }
  return sign | uint16_t(rounded);
}

// Adapted from rocjitsu shared/fp_mode.h: fma_f16 and finish_fma_f16.
// Default guest rounding and denormal policy; preserve architecture-specific NaN results.
// A null status pointer skips reporting; otherwise OR causes into existing bits.
// Reporting is supported for gfx12 only.
template <bool Rdna3 = false>
inline uint16_t half_fma_value(uint16_t a, uint16_t b, uint16_t c, bool saturate,
                               uint32_t *exceptions = nullptr) {
  uint16_t ma = a & 0x7fff, mb = b & 0x7fff, mc = c & 0x7fff;
  const bool a_nan = ma > 0x7c00, b_nan = mb > 0x7c00, c_nan = mc > 0x7c00;
  const bool nan = a_nan || b_nan || c_nan;
  const bool invalid_product = (ma == 0 && mb == 0x7c00) || (mb == 0 && ma == 0x7c00);

  // NaNs and invalid operations suppress
  // denormal-input reporting; infinities alone do not. Classification uses bits
  // and the integer FMA intermediate, never the host's exception flags.
  bool report = exceptions != nullptr;
  if (report) {
    // Every signaling NaN contributes, regardless of which operand supplies the payload.
    bool invalid =
        invalid_product || (a_nan && !(ma & 0x200)) || (b_nan && !(mb & 0x200)) ||
        (c_nan && !(mc & 0x200)) ||
        (!nan && (ma == 0x7c00 || mb == 0x7c00) && mc == 0x7c00 && ((a ^ b ^ c) & 0x8000));
    if (invalid) {
      *exceptions |= RJ_ARITH_EXCEPTION_INVALID;
    } else if (!nan && ((ma && ma < 0x400) || (mb && mb < 0x400) || (mc && mc < 0x400))) {
      *exceptions |= RJ_ARITH_EXCEPTION_INPUT_DENORM;
    }
  }
  uint16_t exceptional = 0;
  if (invalid_product) {
    exceptional = 0xfe00;
  } else if (nan) {
    exceptional = (a_nan ? a : b_nan ? b : c) | (!Rdna3 ? 0x0200 : 0);
  } else if (ma == 0x7c00 || mb == 0x7c00) {
    exceptional = ((a ^ b) & 0x8000) | 0x7c00;
    if (mc == 0x7c00 && ((exceptional ^ c) & 0x8000)) {
      exceptional = 0xfe00;
    }
  } else if (mc == 0x7c00) {
    exceptional = c;
  }
  if (exceptional) {
    return exceptional;
  }

  double value = as_double(fma_finite_round_odd(as_bits(f16_to_float(a)), as_bits(f16_to_float(b)),
                                                as_bits(f16_to_float(c))));

  if (value == 0) {
    // Nearest-even cancellation produces +0; a negative-zero product plus
    // negative-zero C preserves -0.
    const bool product_negative = (a ^ b) & 0x8000;
    const bool matching_zeros = mc == 0 && product_negative == bool(c & 0x8000);
    value = (matching_zeros && product_negative) ? -0.0 : 0.0;
  }
  uint16_t result = half_fma_narrow(value, false);
  if (report) {
    // FP16_OVFL changes the result, not overflow reporting. The round-to-odd
    // intermediate retains discarded information even across large exponent gaps.
    uint16_t magnitude = result & 0x7fff;
    if (magnitude == 0x7c00) {
      *exceptions |= RJ_ARITH_EXCEPTION_OVERFLOW | RJ_ARITH_EXCEPTION_INEXACT;
    } else if (value != double(f16_to_float(result))) {
      *exceptions |= RJ_ARITH_EXCEPTION_INEXACT;

      // Tininess is detected after significand rounding, before limiting the
      // exponent: the midpoint immediately below the smallest normal is not tiny.
      if (std::abs(value) < 0x1p-14 - 0x1p-26) {
        *exceptions |= RJ_ARITH_EXCEPTION_UNDERFLOW;
      }
    }
  }
  return saturate && (result & 0x7fff) == 0x7c00 ? (result & 0x8000) | 0x7bff : result;
}

} // namespace rocjitsu::arith
