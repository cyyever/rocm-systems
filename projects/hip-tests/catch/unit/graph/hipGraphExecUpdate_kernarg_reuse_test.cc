/*
 * Copyright (c) Advanced Micro Devices, Inc., or its affiliates.
 *
 * SPDX-License-Identifier: MIT
 */

/**
 * @addtogroup hipGraphExecUpdate hipGraphExecUpdate
 * @{
 * @ingroup GraphTest
 * Regression tests for kernel-argument slot reuse across executable graph
 * updates (https://github.com/ROCm/rocm-systems/issues/10713).
 */

#include <hip_test_common.hh>

namespace {
// Spins for `spin` cycles before storing, so a launch is still reading its
// kernel arguments while the host updates the executable graph.
__global__ void StoreAfterSpin(int* out, int index, int value, long long spin) {
  const long long start = clock64();
  while (clock64() - start < spin) {
  }
  out[index] = value;
}

__global__ void NoArgs() {}

struct SingleKernelGraph {
  int* out;
  int index = 0;
  int value = 0;
  long long spin = 0;
  void* args[4] = {&out, &index, &value, &spin};
  hipKernelNodeParams params{};
  hipGraph_t graph{};
  hipGraphNode_t node{};
  hipGraphExec_t exec{};

  explicit SingleKernelGraph(int* d_out) : out(d_out) {
    params.func = reinterpret_cast<void*>(StoreAfterSpin);
    params.gridDim = dim3(1);
    params.blockDim = dim3(1);
    params.kernelParams = args;
    HIP_CHECK(hipGraphCreate(&graph, 0));
    HIP_CHECK(hipGraphAddKernelNode(&node, graph, nullptr, 0, &params));
    HIP_CHECK(hipGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
  }
  ~SingleKernelGraph() {
    static_cast<void>(hipGraphExecDestroy(exec));
    static_cast<void>(hipGraphDestroy(graph));
  }
  void Update(int new_index, int new_value, long long new_spin) {
    index = new_index;
    value = new_value;
    spin = new_spin;
    HIP_CHECK(hipGraphExecKernelNodeSetParams(exec, node, &params));
  }
};

size_t FreeDeviceMemory() {
  size_t free_bytes = 0, total_bytes = 0;
  HIP_CHECK(hipMemGetInfo(&free_bytes, &total_bytes));
  return free_bytes;
}
}  // namespace

/**
 * Test Description
 * ------------------------
 *  - Updates and launches one executable graph many times, synchronizing after
 *    each launch. Every update re-captures the kernel packet; without slot
 *    reuse each capture takes fresh kernel-argument space, so device memory
 *    shrinks steadily until it is exhausted. Free memory must stay flat after
 *    warm-up and every launch must observe its own update.
 * Test source
 * ------------------------
 *  - unit/graph/hipGraphExecUpdate_kernarg_reuse_test.cc
 * Test requirements
 * ------------------------
 *  - HIP_VERSION >= 6.0
 */
HIP_TEST_CASE(Unit_hipGraphExecUpdate_KernargReuse_MemoryStable) {
  int* d_out{nullptr};
  HIP_CHECK(hipMalloc(&d_out, sizeof(int)));
  {
    SingleKernelGraph g(d_out);
    constexpr int kWarmup = 1000;
    constexpr int kIters = 50000;
    size_t free_after_warmup = 0;
    for (int i = 0; i < kIters; ++i) {
      g.Update(0, i, 0);
      HIP_CHECK(hipGraphLaunch(g.exec, nullptr));
      int seen = -1;
      HIP_CHECK(hipMemcpy(&seen, d_out, sizeof(int), hipMemcpyDeviceToHost));
      REQUIRE(seen == i);
      if (i == kWarmup) free_after_warmup = FreeDeviceMemory();
    }
    // Without reuse the loop consumes about 400 MiB on gfx1201.
    const size_t free_at_end = FreeDeviceMemory();
    REQUIRE(free_at_end + (size_t{1} << 20) >= free_after_warmup);
  }
  HIP_CHECK(hipFree(d_out));
}

/**
 * Test Description
 * ------------------------
 *  - Keeps several launches of one executable graph in flight and updates it
 *    between them. A replaced kernel-argument slot may only be reused once no
 *    launch that can still read it is running, so each launch must store the
 *    value it was launched with.
 * Test source
 * ------------------------
 *  - unit/graph/hipGraphExecUpdate_kernarg_reuse_test.cc
 * Test requirements
 * ------------------------
 *  - HIP_VERSION >= 6.0
 */
HIP_TEST_CASE(Unit_hipGraphExecUpdate_KernargReuse_InflightLaunchesKeepArgs) {
  constexpr int kDepth = 4;  // launches kept in flight before synchronizing
  constexpr int kRounds = 500;
  constexpr long long kSpin = 200000;
  int* d_out{nullptr};
  HIP_CHECK(hipMalloc(&d_out, kDepth * sizeof(int)));
  {
    SingleKernelGraph g(d_out);
    for (int round = 0; round < kRounds; ++round) {
      HIP_CHECK(hipMemset(d_out, 0xff, kDepth * sizeof(int)));
      for (int d = 0; d < kDepth; ++d) {
        g.Update(d, round * kDepth + d + 1, kSpin);
        HIP_CHECK(hipGraphLaunch(g.exec, nullptr));
      }
      int seen[kDepth];
      HIP_CHECK(hipMemcpy(seen, d_out, sizeof(seen), hipMemcpyDeviceToHost));
      for (int d = 0; d < kDepth; ++d) {
        INFO("round " << round << " launch " << d);
        REQUIRE(seen[d] == round * kDepth + d + 1);
      }
    }
  }
  HIP_CHECK(hipFree(d_out));
}

/**
 * Test Description
 * ------------------------
 *  - Keeps a sliding window of launches in flight, so the exec never becomes
 *    idle. Replaced slots must still be reused once the launches that could
 *    read them finish, and every launch must store its own value.
 * Test source
 * ------------------------
 *  - unit/graph/hipGraphExecUpdate_kernarg_reuse_test.cc
 * Test requirements
 * ------------------------
 *  - HIP_VERSION >= 6.0
 */
HIP_TEST_CASE(Unit_hipGraphExecUpdate_KernargReuse_SlidingWindow) {
  constexpr int kWindow = 2;  // launches kept in flight; the exec never drains
  constexpr int kWarmup = 200;
  constexpr int kRounds = 5000;
  constexpr long long kSpin = 2000000;  // keeps the other launch running at every update
  int* d_out{nullptr};
  HIP_CHECK(hipMalloc(&d_out, kWindow * sizeof(int)));
  // Non-blocking: the null-stream readbacks must not drain it.
  hipStream_t stream{};
  HIP_CHECK(hipStreamCreateWithFlags(&stream, hipStreamNonBlocking));
  hipEvent_t done[kWindow];
  for (auto& event : done) {
    HIP_CHECK(hipEventCreateWithFlags(&event, hipEventDisableTiming));
  }
  {
    SingleKernelGraph g(d_out);
    size_t free_after_warmup = 0;
    for (int round = 0; round < kRounds; ++round) {
      const int slot = round % kWindow;
      if (round >= kWindow) {
        HIP_CHECK(hipEventSynchronize(done[slot]));
        int seen = -1;
        HIP_CHECK(hipMemcpy(&seen, d_out + slot, sizeof(seen), hipMemcpyDeviceToHost));
        INFO("round " << round - kWindow);
        REQUIRE(seen == round - kWindow + 1);
      }
      if (round == kWarmup) free_after_warmup = FreeDeviceMemory();
      g.Update(slot, round + 1, kSpin);
      HIP_CHECK(hipGraphLaunch(g.exec, stream));
      HIP_CHECK(hipEventRecord(done[slot], stream));
    }
    HIP_CHECK(hipStreamSynchronize(stream));
    REQUIRE(FreeDeviceMemory() + (size_t{1} << 20) >= free_after_warmup);
  }
  for (auto& event : done) {
    HIP_CHECK(hipEventDestroy(event));
  }
  HIP_CHECK(hipStreamDestroy(stream));
  HIP_CHECK(hipFree(d_out));
}

/**
 * Test Description
 * ------------------------
 *  - A kernel without a kernel-argument segment is captured with no argument
 *    buffer. Graph instantiation must treat that as success, not as a failed
 *    kernel-argument allocation.
 * Test source
 * ------------------------
 *  - unit/graph/hipGraphExecUpdate_kernarg_reuse_test.cc
 * Test requirements
 * ------------------------
 *  - HIP_VERSION >= 6.0
 */
HIP_TEST_CASE(Unit_hipGraphInstantiate_KernelWithoutKernargs) {
  hipStream_t stream{};
  HIP_CHECK(hipStreamCreate(&stream));
  hipGraph_t graph{};
  HIP_CHECK(hipStreamBeginCapture(stream, hipStreamCaptureModeGlobal));
  for (int i = 0; i < 4; ++i) {
    NoArgs<<<1, 1, 0, stream>>>();
  }
  HIP_CHECK(hipStreamEndCapture(stream, &graph));
  hipGraphExec_t exec{};
  HIP_CHECK(hipGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
  HIP_CHECK(hipGraphLaunch(exec, stream));
  HIP_CHECK(hipStreamSynchronize(stream));
  HIP_CHECK(hipGraphExecDestroy(exec));
  HIP_CHECK(hipGraphDestroy(graph));
  HIP_CHECK(hipStreamDestroy(stream));
}

/**
 * End doxygen group GraphTest.
 * @}
 */
