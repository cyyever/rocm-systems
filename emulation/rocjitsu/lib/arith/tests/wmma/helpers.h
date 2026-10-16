// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Matrix operand layouts, sparse indices, and shared invalid-flag checks.

#pragma once

#include "common/contracts.h"
#include "common/cpu.h"
#include "common/registers.h"
#include "common/semantics.h"
#include "rj_arith/rj_arith.h"

#include <bit>
#include <gtest/gtest.h>
#include <initializer_list>
#include <random>
#include <stdint.h>
#include <vector>

namespace rocjitsu::arith::test {

// Check invalid flags with real storage (all preserved) and null operands
// (rejected before access). The last offset denotes C for WMMA or sparse
// indices for SWMMAC; SWMMAC's D is also its accumulator input.
template <typename Call, int RegistersCount, int Lanes>
void expect_matrix_invalid_flags(Call call, const Registers<RegistersCount, Lanes> &input, int d,
                                 int a, int b, int c_or_indices, uint64_t supported_modifiers) {
  expect_invalid_flags(
      [&](uint64_t flags, uint64_t modifiers) {
        auto r = input;
        int result = call(flags, modifiers, r.v + d, r.v + a, r.v + b, r.v + c_or_indices);
        r.expect_preserved(input, 0, 0);
        EXPECT_EQ(call(flags, modifiers, nullptr, nullptr, nullptr, nullptr),
                  RJ_ARITH_ERROR_INVALID_FLAGS);
        return result;
      },
      supported_modifiers);
}

// Isolate each factor-half sign and accumulator modifier with exactly representable
// arithmetic. These cases supplement the varied-input per-instruction goldens.
template <bool Bf16, int Lanes, bool Gfx11, typename Call> void expect_matrix_modifiers(Call call) {
  constexpr int factors = Gfx11 ? 8 : 128 / Lanes, outputs = 256 / Lanes;
  Registers<32, Lanes> input;
  for (int reg = 0; reg < factors * 2; ++reg) {
    for (int lane = 0; lane < Lanes; ++lane) {
      input.v[reg][lane] = Bf16 ? 0x3f803f80U : 0x3c003c00U;
    }
  }
  for (int reg = 16; reg < 16 + outputs; ++reg) {
    for (int lane = 0; lane < Lanes; ++lane) {
      input.v[reg][lane] = std::bit_cast<uint32_t>(-2.0f);
    }
  }
  const struct {
    uint64_t mode;
    float expected;
  } cases[] = {{0, 14},
               {RJ_ARITH_WMMA_NEG_LO_A, -2},
               {RJ_ARITH_WMMA_NEG_HI_A, -2},
               {RJ_ARITH_WMMA_NEG_LO_B, -2},
               {RJ_ARITH_WMMA_NEG_HI_B, -2},
               {RJ_ARITH_WMMA_NEG_LO_A | RJ_ARITH_WMMA_NEG_HI_A, -18},
               {RJ_ARITH_WMMA_NEG_C, 18},
               {RJ_ARITH_WMMA_ABS_C, 18},
               {RJ_ARITH_WMMA_ABS_C | RJ_ARITH_WMMA_NEG_C, 14}};
  for (uint64_t cpu : supported_cpu_levels()) {
    for (uint64_t semantics : semantics_modes()) {
      for (const auto &test : cases) {
        SCOPED_TRACE(testing::Message() << cpu << '/' << semantics << '/' << test.mode);
        auto r = input;
        ASSERT_EQ(call(cpu | semantics, test.mode, r.v + 24, r.v, r.v + factors, r.v + 16),
                  RJ_ARITH_SUCCESS);
        for (int reg = 24; reg < 24 + outputs; ++reg) {
          for (int lane = 0; lane < Lanes; ++lane) {
            EXPECT_EQ(r.v[reg][lane], std::bit_cast<uint32_t>(test.expected));
          }
        }
        r.expect_preserved(input, 24, outputs);
      }
    }
  }
}

// Check tied C/D aliases against a disjoint snapshot of the same effective inputs.
// Scratch registers [48, 48+outputs) must be disjoint from the operand ranges.
// Numerical correctness is checked separately by each instruction's fixture.
template <int RegistersCount, int Lanes, typename Call>
void expect_sparse_aliasing(Call call, const Registers<RegistersCount, Lanes> &input, int outputs,
                            int b, int index, std::initializer_list<int> offsets,
                            const std::vector<uint64_t> &cpu_levels) {
  static_assert(RegistersCount >= 56);
  for (uint64_t cpu : cpu_levels) {
    for (uint64_t semantics : {RJ_ARITH_SEMANTICS_LOOSE, RJ_ARITH_SEMANTICS_BIT_EXACT_EMPIRICAL}) {
      for (int aliasing_offset : offsets) {
        SCOPED_TRACE(::testing::Message() << cpu << '/' << semantics << '/' << aliasing_offset);
        auto r = input, reference = input;
        for (int reg = 0; reg < outputs; ++reg) {
          for (int lane = 0; lane < Lanes; ++lane) {
            reference.v[48 + reg][lane] = r.v[aliasing_offset + reg][lane];
          }
        }
        ASSERT_EQ(call(cpu | semantics, 0, reference.v + 48, reference.v, reference.v + b,
                       reference.v + index),
                  RJ_ARITH_SUCCESS);
        ASSERT_EQ(call(cpu | semantics, 0, r.v + aliasing_offset, r.v, r.v + b, r.v + index),
                  RJ_ARITH_SUCCESS);
        for (int reg = 0; reg < outputs; ++reg) {
          for (int lane = 0; lane < Lanes; ++lane) {
            EXPECT_EQ(r.v[aliasing_offset + reg][lane], reference.v[48 + reg][lane]);
          }
        }
        r.expect_preserved(input, aliasing_offset, outputs);
      }
    }
  }
}

// Clear unused metadata banks so reading the wrong selector cannot pass by
// observing the same pairs. Only the selected bank needs valid 2:4 pairs.
template <int Lanes, int Width = Lanes == 64 ? 8 : 16>
void isolate_sparse_selector(uint32_t *index, uint64_t mode) {
  static_assert(Width == 8 || Width == 16);
  constexpr int width = Width;
  int key = int((mode >> 7) & (32 / Width - 1));
  uint32_t mask = ((1U << width) - 1) << (width * key);
  for (int lane = 0; lane < Lanes; ++lane) {
    index[lane] &= mask;
  }
}

// Select two increasing K positions per group of four, using high engine bits.
// Draw order is row-major and part of the deterministic golden-input contract.
template <int K> void make_sparse_indices(std::minstd_rand &random, int (&selected)[16][K]) {
  static_assert(K % 2 == 0);
  const uint32_t pairs[] = {0x4, 0x8, 0xc, 0x9, 0xd, 0xe};
  for (int row = 0; row < 16; ++row) {
    for (int k = 0; k < K; k += 2) {
      uint32_t pair = pairs[(random() >> 16) % 6];
      selected[row][k] = 2 * k + (pair & 3);
      selected[row][k + 1] = 2 * k + (pair >> 2);
    }
  }
}

// Write an A/B element in the gfx11 dense WMMA layout. Coordinate is the
// A row or B column; each 16-lane group repeats the complete K vector.
template <int Bits, int Lanes>
void set_wmma_gfx11(uint32_t *const *v, int coordinate, int k, uint32_t bits) {
  static_assert(Bits == 4 || Bits == 8 || Bits == 16);
  static_assert(Lanes == 32 || Lanes == 64);
  for (int group = 0; group < Lanes / 16; ++group) {
    auto &word = v[k * Bits / 32][coordinate + 16 * group];
    int shift = k * Bits % 32;
    word = (word & ~(((1U << Bits) - 1) << shift)) | (bits << shift);
  }
}

// Write a gfx12 dense WMMA FP16/BF16 A/B element. K is partitioned
// between 16-lane groups, with adjacent halves packed in each word.
template <int Lanes>
void set_wmma_gfx12_half(uint32_t *const *v, int coordinate, int k, uint32_t bits) {
  static_assert(Lanes == 32 || Lanes == 64);
  constexpr int group_k = 16 / (Lanes / 16);
  auto &word = v[(k % group_k) / 2][coordinate + 16 * (k / group_k)];
  int shift = 16 * (k % 2);
  word = (word & ~(0xffffU << shift)) | (bits << shift);
}

// Write a gfx12 dense WMMA 4/8-bit A/B element. Wave64 distributes
// the Wave32 register words into the upper 32 lanes.
template <int Bits, int Lanes>
void set_wmma_gfx12_small(uint32_t *const *v, int coordinate, int k, uint32_t bits) {
  static_assert(Bits == 4 || Bits == 8);
  static_assert(Lanes == 32 || Lanes == 64);
  int bit = (k % 8 + 8 * (k / 16)) * Bits;
  int lane = coordinate + 16 * ((k / 8) % 2);
  auto &word = v[Lanes == 32 ? bit / 32 : 0][lane + (Lanes == 64 ? 32 * (bit / 32) : 0)];
  int shift = bit % 32;
  word = (word & ~(((1U << Bits) - 1) << shift)) | (bits << shift);
}

} // namespace rocjitsu::arith::test
