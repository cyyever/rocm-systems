// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Integer FMA accumulation with FP64 round-to-odd intermediates and FP32 narrowing.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include "common/bits.h"

#include <stdint.h>

namespace rocjitsu::arith {

// Shift right, retaining a sticky low bit for all discarded nonzero bits.
inline uint64_t fma_shift_jam(uint64_t value, int shift) {
  if (!shift) {
    return value;
  }
  if (shift >= 64) {
    return value != 0;
  }
  return (value >> shift) | ((value << (64 - shift)) != 0);
}

// Return a finite FP32 fused product-plus-addend as FP64 bits, rounded to odd.
// Integer arithmetic makes the result independent of host FP controls. The
// extra precision preserves rounding decisions when narrowing to FP32 or FP16.
inline uint64_t fma_finite_round_odd(uint32_t a, uint32_t b, uint32_t c) {
  // Extract an integer significand and its binary scale, retaining subnormals.
  auto decode = [](uint32_t bits, int &exponent) {
    exponent = int((bits >> 23) & 255);
    uint64_t significand = bits & 0x7fffff;
    if (exponent) {
      significand |= 0x800000;
    } else {
      exponent = 1;
    }
    exponent -= 150;
    return significand;
  };
  int ea, eb, ec;
  uint64_t ma = decode(a, ea), mb = decode(b, eb), mc = decode(c, ec);
  uint64_t product = ma * mb;
  int ep = ea + eb;
  bool negative = ((a ^ b) >> 31) != 0, c_negative = (c >> 31) != 0;

  // Normalize both terms to bit 61, leaving room for a carry and retaining
  // every product bit. Cancellation is exact when the terms are close.
  auto normalize = [](uint64_t &value, int &exponent) {
    if (value) {
      // Inputs are below 2^62; the sum's carry is removed before normalization.
      const int shift = int(bit_count_zero<false>(value)) - 2;
      value <<= shift;
      exponent -= shift;
    }
  };
  normalize(product, ep);
  normalize(mc, ec);
  int exponent = !product ? ec : !mc ? ep : ep > ec ? ep : ec;
  if (product) {
    product = fma_shift_jam(product, exponent - ep);
  }
  if (mc) {
    mc = fma_shift_jam(mc, exponent - ec);
  }
  uint64_t sum;
  if (negative == c_negative) {
    sum = product + mc;
  } else if (product > mc) {
    sum = product - mc;
  } else {
    sum = mc - product;
    negative = mc > product ? c_negative : false;
  }
  if (!sum) {
    return uint64_t(negative) << 63;
  }
  if (sum & (1ULL << 62)) {
    sum = fma_shift_jam(sum, 1);
    ++exponent;
  }
  normalize(sum, exponent);
  uint64_t significand = fma_shift_jam(sum, 9);
  return (uint64_t(negative) << 63) | (uint64_t(exponent + 61 + 1023) << 52) |
         (significand & 0xfffffffffffffULL);
}

// Round a finite round-to-odd FP64 intermediate to nearest-even FP32, preserving
// subnormals. A carried significand can promote a subnormal to the smallest normal.
inline uint32_t fma_narrow_f32(uint64_t bits) {
  uint32_t sign = uint32_t(bits >> 32) & 0x80000000;
  uint64_t magnitude = bits & 0x7fffffffffffffffULL;
  if (!magnitude) {
    return sign;
  }
  const uint32_t overflow = sign | 0x7f800000;
  int exponent = int(magnitude >> 52) - 1023;
  if (exponent > 127) {
    return overflow;
  }

  if (exponent < -150) {
    return sign;
  }
  int shift = 29 + (exponent < -126 ? -126 - exponent : 0);
  uint64_t significand = (magnitude & 0xfffffffffffffULL) | (1ULL << 52);
  uint32_t rounded = uint32_t(significand >> shift);
  uint64_t unit = 1ULL << shift, remainder = significand & (unit - 1);
  rounded += remainder > unit / 2 || (remainder == unit / 2 && (rounded & 1));
  if (exponent < -126) {
    return sign | rounded;
  }
  if (rounded == (1U << 24)) {
    rounded >>= 1;
    ++exponent;
  }
  if (exponent > 127) {
    return overflow;
  }
  if (exponent < -126) {
    return sign;
  }
  return sign | (uint32_t(exponent + 127) << 23) | (rounded & 0x7fffff);
}

} // namespace rocjitsu::arith
