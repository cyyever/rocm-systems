// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// IWYU pragma: private, include "rj_arith/rj_arith.h"

#ifndef RJ_ARITH_WMMA_H_
#define RJ_ARITH_WMMA_H_

#include "rj_arith_common.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Matrix source signs, accumulator modifiers, and half selection.
constexpr uint32_t RJ_ARITH_WMMA_NEG_LO_A = 1U << 0;
constexpr uint32_t RJ_ARITH_WMMA_NEG_LO_B = 1U << 1;
constexpr uint32_t RJ_ARITH_WMMA_NEG_C = 1U << 2;
constexpr uint32_t RJ_ARITH_WMMA_NEG_HI_A = 1U << 3;
constexpr uint32_t RJ_ARITH_WMMA_NEG_HI_B = 1U << 4;
constexpr uint32_t RJ_ARITH_WMMA_ABS_C = 1U << 5;
constexpr uint32_t RJ_ARITH_SWMMAC_INDEX_KEY_1 = 1U << 7;
constexpr uint32_t RJ_ARITH_SWMMAC_INDEX_KEY_2 = 1U << 8;
constexpr uint32_t RJ_ARITH_WMMA_HIGH_C_D = 1U << 8;
constexpr uint32_t RJ_ARITH_WMMA_SIGNED_A = 1U << 0;
constexpr uint32_t RJ_ARITH_WMMA_SIGNED_B = 1U << 1;
constexpr uint32_t RJ_ARITH_WMMA_CLAMP = 1U << 6;

// Dense matrix multiply-accumulate; operands contain one complete wave.
// Results are staged before writes, permitting whole-VGPR aliases.
int rj_arith_v_wmma_f32_16x16x16_f16_w32(uint64_t flags, uint64_t instruction_flags,
                                         uint32_t *const *d, const uint32_t *const *a,
                                         const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_f16_w64(uint64_t flags, uint64_t instruction_flags,
                                         uint32_t *const *d, const uint32_t *const *a,
                                         const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_bf16_w32(uint64_t flags, uint64_t instruction_flags,
                                          uint32_t *const *d, const uint32_t *const *a,
                                          const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_bf16_w64(uint64_t flags, uint64_t instruction_flags,
                                          uint32_t *const *d, const uint32_t *const *a,
                                          const uint32_t *const *b, const uint32_t *const *c);

// This instruction has no FP-status output: mode 3 accepts the same numeric contract as mode 2.
int rj_arith_v_wmma_f32_16x16x16_f16_w32_gfx12(uint64_t flags, uint64_t instruction_flags,
                                               uint32_t *const *d, const uint32_t *const *a,
                                               const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_bf16_w32_gfx12(uint64_t flags, uint64_t instruction_flags,
                                                uint32_t *const *d, const uint32_t *const *a,
                                                const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_f16_w64_gfx12(uint64_t flags, uint64_t instruction_flags,
                                               uint32_t *const *d, const uint32_t *const *a,
                                               const uint32_t *const *b, const uint32_t *const *c);

int rj_arith_v_wmma_f32_16x16x16_bf16_w64_gfx12(uint64_t flags, uint64_t instruction_flags,
                                                uint32_t *const *d, const uint32_t *const *a,
                                                const uint32_t *const *b, const uint32_t *const *c);

#ifdef __cplusplus
} // extern "C"
#endif

#endif
