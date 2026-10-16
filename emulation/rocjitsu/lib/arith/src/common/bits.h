// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Leading and trailing zero counts for unsigned integer words.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include <bit>
#include <stdint.h>

namespace rocjitsu::arith {

// Leading or trailing zero count; a zero word returns UINT32_MAX.
template <bool Trailing, typename T> uint32_t bit_count_zero(T a) {
  if (!a) {
    return UINT32_MAX;
  }
  return Trailing ? std::countr_zero(a) : std::countl_zero(a);
}

} // namespace rocjitsu::arith
