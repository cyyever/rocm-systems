// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Declarations connecting dense FP16/BF16 WMMA dispatch to the bit-exact
// AVX2/AVX-512 kernels for both wave sizes and gfx11/gfx12 layouts, with FP32 results.

#pragma once

#include <stdint.h>

namespace rocjitsu::arith {

// Compute empirical bit-exact FP16/BF16 A*B+C for the selected gfx layout
// and wave size. Requires validated mode; D may alias inputs.
template <bool Bf16, int Lanes, bool Rdna3>
void wmma_exact_x86_64_v3(uint32_t mode, uint32_t *const *d, const uint32_t *const *a,
                          const uint32_t *const *b, const uint32_t *const *c);

// Compute empirical bit-exact FP16/BF16 A*B+C for the selected gfx layout
// and wave size. Requires validated mode; D may alias inputs.
template <bool Bf16, int Lanes, bool Rdna3>
void wmma_exact_x86_64_v4(uint32_t mode, uint32_t *const *d, const uint32_t *const *a,
                          const uint32_t *const *b, const uint32_t *const *c);

} // namespace rocjitsu::arith
