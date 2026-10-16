// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Cross-family declarations connecting public dispatch to x86 SIMD kernels.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include <stdint.h>

namespace rocjitsu::arith {

#if defined(RJ_ARITH_HAVE_X86_64_V3)

// Evaluate wmma f32 for the caller-selected operation.
// Requires the named CPU features and validated instruction controls.
template <bool Bf16, int Lanes, bool Rdna3>
void wmma_f32_x86_64_v3(uint32_t modifiers, uint32_t *const *d, const uint32_t *const *a,
                        const uint32_t *const *b, const uint32_t *const *c);

// Evaluate fma for the caller-selected operation. Preserve destination lanes outside
// exec_mask.
// Requires the named CPU features and validated instruction controls.
void fma_x86_64_v3(uint64_t flags, uint32_t exec_mask, uint32_t modifiers, uint32_t *d,
                   const uint32_t *a, const uint32_t *b, const uint32_t *c);

#endif

} // namespace rocjitsu::arith
