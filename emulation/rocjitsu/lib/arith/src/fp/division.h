// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Shared FP format traits, bitwise scaling, and division rounding/modifier rules.
// Internal helpers shared by instruction implementations; not part of the public C API.

// Format and rounding helpers adapted from rocjitsu shared/division.h.

#pragma once

#include "rj_arith/rj_arith.h"

#include <stdint.h>
#include <type_traits>

namespace rocjitsu::arith {

template <int Width> struct DivisionFormat {
  using Bits = std::conditional_t<Width == 64, uint64_t, uint32_t>;
  static constexpr int fraction = Width == 16 ? 10 : Width == 32 ? 23 : 52;
  static constexpr int bias = Width == 16 ? 15 : Width == 32 ? 127 : 1023;
  static constexpr Bits sign = Bits(1) << (Width - 1);
  static constexpr Bits infinity = Bits(2 * bias + 1) << fraction;
  static constexpr Bits quiet = Bits(1) << (fraction - 1);
};

// Apply OMOD/CLAMP to IEEE bits. Active OMOD flushes input subnormals to +0
// and output subnormals to signed zero. Finite overflow uses the supplied code.
template <int Width>
inline typename DivisionFormat<Width>::Bits
division_output(typename DivisionFormat<Width>::Bits result, uint32_t mode,
                typename DivisionFormat<Width>::Bits overflow = DivisionFormat<Width>::infinity) {
  using F = DivisionFormat<Width>;
  using T = typename F::Bits;
  unsigned omod = (mode >> 6) & 3;
  if (omod) {
    T magnitude = result & (F::sign - 1), out_sign = result & F::sign;
    int exponent = int((result & F::infinity) >> F::fraction);
    if (!exponent) {
      result = 0;
    } else if (magnitude < F::infinity) {
      exponent += omod == 3 ? -1 : int(omod);
      if (exponent <= 0) {
        result = out_sign;
      } else if (exponent >= 2 * F::bias + 1) {
        result = out_sign | overflow;
      } else {
        result = (result & ~F::infinity) | (T(exponent) << F::fraction);
      }
    }
  }
  if (mode & RJ_ARITH_ALU_CLAMP) {
    if ((result & F::sign) || (result > F::infinity)) {
      result = 0;
    } else if (result > (T(F::bias) << F::fraction)) {
      result = T(F::bias) << F::fraction;
    }
  }
  return result;
}

} // namespace rocjitsu::arith
