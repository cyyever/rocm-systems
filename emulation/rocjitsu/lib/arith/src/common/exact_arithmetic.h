// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Dispatch interfaces for exact x86 multiply and fused arithmetic.
// Internal helpers shared by instruction implementations; not part of the public C API.

#pragma once

#include <stdint.h>

namespace rocjitsu::arith {

#if defined(RJ_ARITH_HAVE_X86_64_V3)
// Nearest guest rounding; special/tiny results are repaired with the inherited model.
bool fma_exact_x86_64_v3(uint64_t flags, uint32_t exec_mask, uint32_t mode, uint32_t *d,
                         const uint32_t *a, const uint32_t *b, const uint32_t *c, bool rdna3);

// Evaluate half fma exact for the caller-selected operation. Preserve destination lanes
// outside exec_mask.
// Requires the named CPU features and validated instruction controls. Return false to request
// fallback.
bool half_fma_exact_x86_64_v3(uint64_t flags, uint32_t exec_mask, uint32_t mode, uint32_t *d,
                              const uint32_t *a, const uint32_t *b, const uint32_t *c,
                              uint32_t *state, bool rdna3 = false);

#endif

#if defined(RJ_ARITH_HAVE_X86_64_V4)

// All FP32 inputs and guest rounding modes; exceptional/tiny lanes use scalar repair.
bool fma_exact_x86_64_v4(uint64_t flags, uint32_t exec_mask, uint32_t mode, uint32_t *d,
                         const uint32_t *a, const uint32_t *b, const uint32_t *c,
                         bool rdna3 = false);

// All FP16 inputs and numeric policies. Unsupported reporting policies decline
// without changing outputs; nonfinite lanes use the inherited scalar model.
bool half_fma_exact_x86_64_v4(uint64_t flags, uint32_t exec_mask, uint32_t mode, uint32_t *d,
                              const uint32_t *a, const uint32_t *b, const uint32_t *c,
                              uint32_t *state, bool rdna3 = false);

#endif

} // namespace rocjitsu::arith
