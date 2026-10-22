# DOT2 and WMMA hardware fixtures

These raw results were captured on Radeon Pro W7900 (`gfx1100`) and Radeon AI
Pro R9700 (`gfx1201`) using TheRock `10.2.0a20260916`. The decoded regression
tests consume the captured bits directly and require no GPU.

| Header | Contents |
| --- | --- |
| `rdna_f16_samples.h` | Selected RDNA3 FP16 high-half WMMA output words. |
| `rdna_sparse_float_samples.h` | Selected RDNA4 sparse FP16 matrix output words. |
| `rdna_f8_samples.h` | Selected RDNA4 FP8/BF8 WMMA output words. |
| `rdna_integer_samples.h` | Selected RDNA integer WMMA/SWMMAC output words. |
| `gfx1100_cases.h` | GFX11 FP32-output DOT2 cases and a WMMA matrix. |
| `gfx1201_dot4_cases.h` | 256 native FP8/BF8 DOT4 outputs from 64 raw A/B/C triples. |
| `gfx1201_cases.h` | GFX12 FP32-output DOT2 cases and WMMA matrices. |
| `packed_operand_cases.h` | 440 packed WMMA instruction/operand captures for modifiers, selectors and inline constants. |
| `packed_wmma_cases.h` | Seven F16/BF16 matrix inputs with packed outputs for both architectures and wave sizes. |

DOT2 records store packed A/B words, FP32 C and the expected FP32 result.
WMMA inputs use row-major matrices. Packed matrix expectations are indexed by
`[gfx12][wave64][bf16][fixture][element]`, with row-major elements. Operand
fixtures store raw instruction words, uniform A/B/C words and the two
architecture-specific expected destination words. Their initial D value is
`0x56781234`, allowing the tests to check preservation of the unused half.

Coverage includes signed zeros, NaN payloads and precedence, infinities,
alignment and rounding boundaries, subnormals, cancellation, both packed
half selections, wave32/wave64 and overlapping input/output registers. Separate
regressions retain intermediate F16 overflow-mode and cancellation witnesses.
Comparisons include every output bit, including NaNs and preserved halves.

The GFX11 fixtures also test RDNA3.5 dispatch, without claiming a physical
RDNA3.5 measurement. The captures qualify dense F16/BF16 DOT2/WMMA arithmetic
on these two cards; they do not establish behavior for other matrix formats.

## RDNA matrix regressions

The `rdna_*_test.cpp` tests retain a few raw results captured on W7900
(`gfx1100`) and R9700 (`gfx1201`). They run without a GPU. The arithmetic models
are inferred from these observations, not specifications of hardware internals.

Integer cases distinguish intermediate saturation, sparse index selection, and
operand overlap. Inputs use the original capture seed and xorshift sequence.

FP8/BF8 cases distinguish native-format arithmetic and NaN precedence.

Sparse floating-point cases exercise index keys, source signs, and packed outputs.

FP16/BF16 dense cases exercise packed destination halves and accumulator handling.

Tests sample destination words and check that other registers remain unchanged.
This deliberately small corpus is regression coverage, not exhaustive validation.

RDNA4 floating DOT2 and all four FP8/BF8 DOT4 combinations were also checked
with DPP8 reversal and DPP16 row shifts on R9700 (`gfx1201`) using TheRock
`10.1.0a20260812`. Lane-dependent signs and integer accumulators distinguish
source permutation from destination masking. The decoded regressions cover
both wave sizes, inactive destinations, row/bank masks and overlapping sources.
The four-term FP8/BF8 model uses the same group alignment as the eight-term
matrix model, with a single group of four products.

The DOT4 arithmetic fixture uses xorshift32 seed `0x713fa225` and retains all
256 hardware outputs. It checks input format selection, NaN precedence and
rounding, including independence from the host floating-point rounding mode.
