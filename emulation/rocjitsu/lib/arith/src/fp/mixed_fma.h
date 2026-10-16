// Copyright (c) 2026 Advanced Micro Devices, Inc.
// SPDX-License-Identifier: MIT

// Mixed FP16/FP32 FMA with FP32 or selected-halfword output.
// Operation selectors and backend declarations shared by dispatch and SIMD code.

#pragma once

#include <stdint.h>

namespace rocjitsu::arith {

enum class MixedFma { Float, Low, High };

} // namespace rocjitsu::arith
