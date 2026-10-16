// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Scalar FP32 FMA under default guest controls, including exceptional values.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include "fp/fma_integer.h"

#include <stdint.h>

namespace rocjitsu::arith {

// rocjitsu shared/fp_mode.h FMA NaN ordering and nearest-even rounding,
// using the existing integer intermediate instead of host FP-control changes.
// Accept raw FP32 encodings, preserving subnormals. No FP status is produced.
inline uint32_t fma_value_f32(uint32_t a, uint32_t b, uint32_t c, bool rdna3) {
  uint32_t ma = a & 0x7fffffff, mb = b & 0x7fffffff, mc = c & 0x7fffffff;

  uint32_t result;
  if ((ma == 0 && mb == 0x7f800000) || (mb == 0 && ma == 0x7f800000)) {
    result = 0xffc00000;
  } else if (ma > 0x7f800000 || mb > 0x7f800000 || mc > 0x7f800000) {
    result = (ma > 0x7f800000 ? a : mb > 0x7f800000 ? b : c) | (!rdna3 ? 0x00400000 : 0);
  } else if (ma == 0x7f800000 || mb == 0x7f800000) {
    result = ((a ^ b) & 0x80000000) | 0x7f800000;
    if (mc == 0x7f800000 && ((result ^ c) & 0x80000000)) {
      result = 0xffc00000;
    }
  } else if (mc == 0x7f800000) {
    result = c;
  } else {
    uint64_t value = fma_finite_round_odd(a, b, c);

    // Nearest-even cancellation produces +0; matching signed-zero terms
    // preserve their sign.
    const bool matching_zeros = (ma == 0 || mb == 0) && mc == 0 && ((a ^ b ^ c) & 0x80000000) == 0;
    if (!(value & 0x7fffffffffffffffULL) && !matching_zeros) {
      value = 0;
    }
    result = fma_narrow_f32(value);
  }
  return result;
}

} // namespace rocjitsu::arith
