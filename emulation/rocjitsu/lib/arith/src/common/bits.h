// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Width-aware integer extension, bit counting, and bit reversal.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include <stdint.h>

namespace rocjitsu::arith {

// Leading or trailing zero count; a zero word returns UINT32_MAX.
template <bool Trailing, typename T> uint32_t bit_count_zero(T a) {
  if (!a) {
    return UINT32_MAX;
  }
#if defined(__GNUC__) || defined(__clang__)
  if constexpr (Trailing) {
    if constexpr (sizeof(T) == 8) {
      return __builtin_ctzll(a);
    } else {
      return __builtin_ctz(a);
    }
  } else {
    if constexpr (sizeof(T) == 8) {
      return __builtin_clzll(a);
    } else {
      return __builtin_clz(a);
    }
  }
#else
  uint32_t n = 0;
  if constexpr (Trailing) {
    while (!(a & 1)) {
      ++n;
      a >>= 1;
    }
  } else {
    const T sign = T(1) << (sizeof(T) * 8 - 1);
    while (!(a & sign)) {
      ++n;
      a <<= 1;
    }
  }
  return n;
#endif
}

} // namespace rocjitsu::arith
