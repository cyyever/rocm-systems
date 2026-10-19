# QEMU VFIO-user compute

This guide describes the QEMU/VFIO-user path that rocJITsu supports today.
The single-GPU guest qualification recipe uses `configs/gfx1250_mi455x.json`.
The launcher can also expose multiple local gfx1250 GPUs from a matching
configuration, including `configs/gfx1250_mi455x_kmd_4gpu.json`. QEMU owns the
guest, while rocJITsu supplies the emulated PCI devices and GPU models.

The repository provides the VFIO-user server and
`scripts/run-vfio-guest.py`. It does not build or distribute a guest kernel,
initramfs, AMDGPU package, ROCm runtime, or rocBLAS payload. Those inputs must
come from one mutually compatible public release or nightly. Record their
versions and SHA-256 digests when publishing a result.
The [pod guest payload recipe](../tests/guest/README.md) pins the external
QEMU, libvfio-user, driver, kernel, and ROCm inputs used by the same-host
peer/RCCL gates. It also distinguishes the zero-patch final driver module
from earlier diagnostic patch runs.
The [four-node VFIO pod controller](../scripts/run-rccl-pod-vfio.py) uses
`configs/gfx1250_mi455x_kmd_4node_2gpu_if.json` to launch the mixed local
peer and inter-node NET workload described by that recipe.

## Standard peer BAR transport

The pinned QEMU sends a standard, descriptorless `VFIO_USER_DMA_MAP` when a
requester maps another GPU's PCI BAR. The VFIO host decodes that IOVA against
the live 64-bit BAR registers of the other functions in the same server-local
node. It accepts only one unambiguous, fully covered BAR0 mapping backed by a
sealed, stable-size memfd. The map is bound to both live transport sessions;
exact UNMAP, BAR reprogramming, reset, and disconnect revoke it. A stale peer
IOVA is denied rather than reinterpreted as ordinary guest RAM. GPU peer
effects cross the modeled local fabric. Ordinary guest RAM uses its usual
descriptor-backed VFIO-user DMA map and never routes through the GPU fabric.

The active libvfio-user source carries only a generic fix for the upper
address register of a sub-4-GiB 64-bit BAR. A former nonstandard peer
transport is removed from the active source and launch path. Runs that
depended on it are historical controls, not evidence for the current
stock-transport gate. The peer endpoint does not advertise AtomicOp
completion; peer BAR atomics are rejected. The selected
stock driver emits UC peer PTEs, so cacheable peer coherence is a later gate.

## GPU VM hardware path

The guest uses the selected AMDGPU and AMDKFD driver with the ordinary GFXHUB,
MMHUB, NBIF/HDP, and KFD VM register and packet paths. BAR4 contains only the
MSI-X table and pending bits (8 KiB). The GFXHUB VMID-0 invalidation request
publishes the configured GART translator before its ACK bit is exposed. Both
hub models answer their versioned invalidation registers, and the NBIF 7.11
remap accepts the driver's HDP flush write. A PCI page-table walk retains a
lease on the transport session it captured, so reset or detach cannot redirect
that walk to a later session.

Nonzero-VMID GFX12 translations rewalk their page tables on each query. The
current functional model therefore has no retained UTC/TLB entries for a hub
invalidation to discard before its ACK. Any future translation cache must be
a separate Simdojo hardware component reached by the versioned hub request;
its selected VMID state must retire before the hub exposes completion.

The PCI function is a Simdojo component. Versioned IP block adapters own the
register claims and control handshakes for the blocks the discovery table
publishes; the SoC's GPU VM, queues, memory, and fabric models own data
effects. Additional IOMMU, memory-controller, MMHUB, or translation-cache
behavior must attach at those hardware boundaries and use the driver's
existing registers or packets. A register write alone cannot establish
cacheable visibility or retirement.

Those behaviors support functional GPU memory translation. They do not prove
that CPU-written PTEs have a cacheable publication order or that a peer PTE
has a cacheable memory type. The observed stock-driver peer PTE was UC, so
peer cache fills remain disabled. A nonzero-VMID peer PTE with any other memory
type is rejected before its PCI backing effect. Translated vector reads whose
full line maps to local VRAM can use the existing Simdojo V$ and L2 cache
components. Their tags retain the exact address-space handle, selected
physical line, raw PTE memory type, permissions, and local visibility epoch.
Local VRAM writes, HDP flushes, and fabric maintenance retire those clean
local tags. Translated scalar reads and vector stores still use direct VM
access, and cacheable peer fills remain unqualified. GFX12 translations retain
the exact PTE memory-type encoding alongside the broad cache policy, so a
deferred rewalk also rejects an NC-to-RW PTE change. VMID-0 GART transfers are
unaffected because MES and SDMA do not issue CU cache fills. A coherent peer
cache result still requires versioned hub/TLB invalidation and exact VM/PTE
and grant identity through fills, maintenance, effects, and retirement. Those
states must be driven by the stock driver's registers and packets.
Results from retired experiments do not qualify the current stock-driver
cache path.

### Same-host stock-driver control

On 2026-10-14, a fresh guest image built from the pinned DKMS package with
driver bug-fix patches `0001` through `0008`
bound two gfx1250 GPUs. With the corrected XIO3130 LinkCap and explicit root
AtomicOp completion for mapped guest RAM, a GPU1 kernel read and wrote GPU0
VRAM. The guest checked `observed=0x13579bdf` and
`final_owner=0x1357c047`; the server counted one committed read and write
from GPU1 to GPU0. The guest exited zero without a kernel UBSAN or WARNING. A
three-second wait after workload exit let the asynchronous KFD process
release finish before the test guest's forced poweroff; it also removed the
shutdown BO-free warning seen with immediate poweroff. The driver module was
unchanged between those runs.

With root and switch AtomicOp properties left off, the same driver bound both
PCI functions, but KFD rejected PCIe atomics and HIP reported no ROCm-capable
device. The working run enabled root completion and switch routing for the
VFIO backend's guest-RAM atomic operations. The peer endpoint's AtomicOp
completer bits stayed clear, and peer BAR atomics are rejected. This checks
ordinary peer reads and writes on one host; it does not qualify peer atomics,
cacheable coherence, or the four-guest same-host RCCL exit gate below. The
exact local images, commands, hashes, and log paths are in
`docs/stock-driver-hardware-path-20261014.md`.

## Host prerequisites

- Linux on x86-64.
- CMake 3.28 or newer for a VFIO-enabled build.
- Linux UAPI headers containing the VFIO migration and DMA logging interfaces
  used by libvfio-user (Linux 6.1 or newer is a practical baseline).
- Ninja and a supported C++20 compiler.
- Python 3.10 or newer for the launcher.
- QEMU with the `vfio-user-pci` device.
- Internet access during the first CMake configure, unless the fetched
  libvfio-user and json-c dependencies are already available locally.
- Optional access to `/dev/kvm`. The launcher falls back to TCG.

Check the QEMU capabilities before building a guest:

```bash
qemu-system-x86_64 -accel help
qemu-system-x86_64 -device help | rg vfio-user-pci
```

## Build the VFIO-user server

Run these commands from the rocjitsu source directory:

```bash
cmake -S . -B build-vfio -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DROCJITSU_ENABLE_VFIO=ON
cmake --build build-vfio --target rocjitsu_bin rj_ip_discovery
```

The VFIO dependency gate runs during configuration and rejects CMake older than
3.28 while leaving the ordinary build's 3.22 minimum unchanged.

The resulting server is:

```text
build-vfio/tools/rocjitsu/rocjitsu
```

The build also produces the profile-specific IP-discovery generator at:

```text
build-vfio/tools/rj-ip-discovery/rj-ip-discovery
```

## Prepare compatible guest artifacts

The kernel, AMDGPU module, firmware, ROCm user-mode stack, and rocBLAS payload
must be mutually compatible. A current ROCm nightly is suitable when it has
gfx1250 support and its AMDGPU driver contains commit `4e07da515d1c`
(`drm/amdgpu: enumerate UMSCH HW IP`) or an equivalent backport. That fix
allows discovery of this compute-only device without a VCN instance.

The gfx1250 profile intentionally omits display and media IP such as JPEG,
VCN, and UVD. It retains the management-processor discovery records required
by the driver; those records do not imply a complete firmware-managed hardware
model. This does not mean that the Linux driver never opens firmware files.
With direct firmware loading, current AMDGPU code still parses firmware for
the enabled compute, MES, SDMA, and IMU paths. Package the firmware files that
match the exact AMDGPU module in the initramfs. The authoritative inventory
for a built module is:

```bash
modinfo -F firmware /path/to/amdgpu.ko | sort -u
```

For the current gfx1250 path, requests can include
`amdgpu/gc_12_1_0_imu.bin`, `amdgpu/gc_12_1_0_mec.bin`,
`amdgpu/gc_12_1_0_rlc_1.bin`, a matching gfx1250 MES image, and
`amdgpu/sdma_7_1_0.bin`. Use files from the same public driver/firmware
release. Do not add JPEG or VCN firmware, because those IP blocks are absent.

The launch command below selects file-based IP discovery with
`amdgpu.discovery=2`. Its `amdgpu/ip_discovery.bin` is not a vendor firmware
blob and must not be copied from an unrelated package. Generate it from the
same rocJITsu gfx1250 profile used by the emulated device:

```bash
mkdir -p /path/to/staging-root/lib/firmware/amdgpu
build-vfio/tools/rj-ip-discovery/rj-ip-discovery \
  gfx1250 \
  /path/to/staging-root/lib/firmware/amdgpu/ip_discovery.bin
```

Regenerate the table whenever the rocJITsu device profile changes, then pack
that staging tree into the initramfs.

The initramfs must contain:

- an executable `/init`;
- `/dev`, `/proc`, and `/sys` mount points;
- the guest kernel's AMDGPU module and all of its module dependencies;
- every firmware file requested by the selected gfx1250 driver path;
- the dynamic loader and transitive libraries needed by the workload;
- a gfx1250-capable ROCr/HIP runtime, rocBLAS, its gfx1250 Tensile metadata and
  code object, and a GEMM validation executable;
- a shutdown command such as BusyBox `poweroff`.

The init process must:

1. Mount devtmpfs, procfs, and sysfs.
2. Load the AMDGPU module and its dependencies.
3. Fail if AMDGPU did not bind the `0x1002:0x75c1` PCI function.
4. Fail if `/dev/kfd` is absent.
5. Run the GEMM validator and propagate its result.
6. Print stable success or failure markers.
7. Power the guest off. QEMU runs with `-no-reboot`, so poweroff is the
   normal successful exit path.

Use a fresh staging directory and an ordinary initramfs builder, or pack a
reviewed staging tree directly:

```bash
(
  cd /path/to/staging-root
  find . -print0 | cpio --null --create --format=newc
) | gzip -9 > /path/to/gfx1250-compute-initramfs.gz
```

Do not copy an arbitrary host `/opt/rocm` tree. Copy the selected package
payloads and all transitive ELF dependencies, preserve symlinks, and verify
that the rocBLAS library data contains a gfx1250 code object. A missing loader,
library, Tensile data file, or firmware file normally appears as a probe or
workload failure rather than as a host-launch failure.

### AMDGPU 7.1.3 driver bug-fix candidates

The current same-host pod image uses the pinned package with **zero local
AMDGPU/AMDKFD patches**. Patches `0001` through `0008` below repair
independent VM and KFD error paths; they are retained as upstream bug-fix
candidates and are not part of the pod image. `0011` is optional local
diagnostic logging. None is a simulator protocol. The following build recipe
documents the earlier fault-injection controls, not a prerequisite for
multi-GPU RCCL.

`patches/amdgpu/7.1.3.31500000-2390945.24.04/0001-link-pt-after-clear.patch`
applies to `amdgpu-dkms` package version
`1:7.1.3.31500000-2390945.24.04` (SHA-256
`edf6b629f2cb2d6091aac531c0787aee2387bdc0748a91f21ea38c6c10970ffb`).
In `amdgpu_vm_pt_alloc`, it asserts the root reservation and links a new child
page table to the VM only after `amdgpu_vm_pt_clear` succeeds. A failed clear
then reaches the existing cleanup path with the entry still unlinked. Its
scope is this allocation path; PTE/PDE update error recovery is separate.

Start from a fresh package extraction for each build because the package's
`pre-build.sh` rewrites source files. With matching guest kernel headers
installed, run these commands from the rocjitsu checkout root and apply the
patch before `make` runs that script:

```bash
pkg=/path/to/amdgpu-dkms_7.1.3.31500000-2390945.24.04_all.deb
sha256sum "$pkg"
work=$(mktemp -d)
dpkg-deb -x "$pkg" "$work"
src="$work/usr/src/amdgpu-7.1.3-2390945.24.04"
patch_dir=patches/amdgpu/7.1.3.31500000-2390945.24.04
pt_patch="$patch_dir/0001-link-pt-after-clear.patch"
dep_patch="$patch_dir/0002-abort-sdma-pt-clear-dependency.patch"
retry_patch="$patch_dir/0003-retry-failed-compute-tlb-flush.patch"
cpu_seq_patch="$patch_dir/0004-publish-cpu-tlb-seq-after-hdp.patch"
cpu_pde_patch="$patch_dir/0005-finalize-failed-cpu-pde-prefix.patch"
sdma_pde_patch="$patch_dir/0006-abort-failed-sdma-pde-job.patch"
kfd_unmap_patch="$patch_dir/0007-preserve-kfd-unmap-retry.patch"
kfd_tlb_patch="$patch_dir/0008-propagate-kfd-tlb-retry.patch"
patch --directory="$src" --strip=1 --dry-run < "$pt_patch"
patch --directory="$src" --strip=1 < "$pt_patch"
patch --directory="$src" --strip=1 --dry-run < "$dep_patch"
patch --directory="$src" --strip=1 < "$dep_patch"
patch --directory="$src" --strip=1 --dry-run < "$retry_patch"
patch --directory="$src" --strip=1 < "$retry_patch"
patch --directory="$src" --strip=1 --dry-run < "$cpu_seq_patch"
patch --directory="$src" --strip=1 < "$cpu_seq_patch"
patch --directory="$src" --strip=1 --dry-run < "$cpu_pde_patch"
patch --directory="$src" --strip=1 < "$cpu_pde_patch"
patch --directory="$src" --strip=1 --dry-run < "$sdma_pde_patch"
patch --directory="$src" --strip=1 < "$sdma_pde_patch"
patch --directory="$src" --strip=1 --dry-run < "$kfd_unmap_patch"
patch --directory="$src" --strip=1 < "$kfd_unmap_patch"
patch --directory="$src" --strip=1 --dry-run < "$kfd_tlb_patch"
patch --directory="$src" --strip=1 < "$kfd_tlb_patch"
(cd "$src" && make KERNELVER=6.17.0-23-generic)
modinfo -F version "$src/amd/amdgpu/amdgpu.ko"
modinfo -F vermagic "$src/amd/amdgpu/amdgpu.ko"
```

For an opt-in KFD import/MAP diagnostic build, run the following after
applying `0008` and before the `make` command above. Leave it out of normal
guest builds:

```bash
kfd_trace_patch="$patch_dir/0011-trace-kfd-import-map.patch"
patch --directory="$src" --strip=1 --dry-run < "$kfd_trace_patch"
patch --directory="$src" --strip=1 < "$kfd_trace_patch"
```

Copy the new `amdgpu.ko` into a copy of the prepared guest root. Recompute the
module hash, image lock, and build attestation with that guest image's
packaging workflow, then repack the initramfs. The `cpio` command above only
repacks the files; it does not refresh those records. The production-only
build with `0001` passed against `6.17.0-23-generic`. A VFIO guest run with
that module reported `/dev/kfd` present and reference-checked FP32 128-by-128
SGEMM with zero failures and zero maximum absolute error, then powered off
normally. The existing `vm_update_mode=3` startup WARNs remain in the guest
log. Cacheable peer access requires separate fabric traffic and
synchronization qualification.

`0002-abort-sdma-pt-clear-dependency.patch` addresses a separate pre-submit
error in the SDMA child page-table clear path. If adding a PD/PT move fence to
the new SDMA job fails, the bundled scheduler has already consumed that fence
reference. The SDMA path ends the reservation iterator without releasing the
fence again. The page-table clear caller frees its unsubmitted job, clears the
job pointer and remaining dword count, and returns the original error. It does
not cover errors after submission or other SDMA update ranges.

A scratch guest pair used the same 260-allocation HIP probe and injected
`-ENOMEM` while adding a child-clear move-fence dependency. With `0001` only,
the guest reached the injection and timed out without a job cleanup or retry
result. With both patches, it recorded one job cleanup, returned
`hipErrorOutOfMemory` to the allocation, retried in the same process, verified
GPU memset/copy data, and powered off without a new WARN or oops after the
injection. A separate production-only build with both patches, no fault hook,
and the same guest kernel passed `/dev/kfd` detection and reference-checked
FP32 128-by-128 SGEMM with zero failures and zero maximum absolute error. It
powered off normally; the existing startup WARNs remain. These runs qualify
the injected pre-submit dependency error path, not other SDMA failures.

`0003-retry-failed-compute-tlb-flush.patch` records a compute VM TLB sequence
only after every requested PASID flush reports success. A reported error leaves
the same sequence eligible for a later retry. A compare-and-swap maximum keeps
an older concurrent call from lowering a newer recorded sequence. This
repairs the error bookkeeping at this call site. The KFD wrapper still drops
flush errors, and the reset and direct fallback paths can report success
without a checked invalidate. The patch does not qualify cacheable peer access.

Matched scratch guests used the same one-shot reported `-ETIME` at the compute
PASID flush with a single-XCC mask. At sequence 3, the two-patch control
recorded that sequence before the injected error, so a second call made no
low-level flush attempt. With `0003`, the failed call left the recorded
sequence at 2; the second call attempted the flush and then recorded sequence
3. Both guests passed the reference-checked SGEMM workload. The scratch probe
is excluded from the production patch and module.

A fresh production-only module with all three patches built against
`6.17.0-23-generic`. Its locked guest image detected `/dev/kfd` and passed
reference-checked FP32 128-by-128 SGEMM with zero failures and zero maximum
absolute error, then powered off normally. The two existing startup WARNs
remain. This validates the reported-error retry and normal compute paths;
it does not establish checked guest translation visibility or RCCL P2P.
The hashes and guest logs are recorded in
`tmp/p3v-compute-tlb-retry/BUILD-RECORD.md`.

`0004-publish-cpu-tlb-seq-after-hdp.patch` orders the CPU update's TLB
sequence publication after the normal HDP flush, while still holding the
reset-domain read lock. If a reset owns that lock, the existing skip path
continues to advance the sequence after the memory barrier. The sequence
marks an invalidation need, not checked PTE/PDE visibility: the HDP operation
has no checked completion result here, and the reset path still returns
success without a checked invalidate. This patch does not qualify cacheable
peer access. Build and guest evidence is recorded in
`tmp/p3v-cpu-seq-order/BUILD-RECORD.md`.

Matched scratch guests paused immediately before the normal HDP call. The
three-patch control had already advanced the sequence from 100 to 101 at
that point; with `0004`, it remained 100 until after HDP, then became 101.
A synthetic reset-lock trylock failure advanced it from 101 to 102 in both
guests. Both scratch guests and a fresh probe-free, four-patch guest passed
reference-checked FP32 128-by-128 SGEMM with zero failures and zero maximum
absolute error, then powered off. The two existing startup WARNs remain. The
synthetic branch probe is not an actual GPU reset.

`0005-finalize-failed-cpu-pde-prefix.patch` handles a later error in the CPU
PDE update loop after an earlier PDE store succeeded. It commits the written
prefix through the CPU HDP path, advances the VM's invalidation-needed TLB
sequence, preserves the original error, and keeps moved PDEs for retry. It
does not change the SDMA update path or make the sequence a checked BAR4
visibility receipt.

A scratch control changed one real compute VM PDE, then injected `-ETIME`
before a repeated update attempt on that entry. Its error path made no HDP
call and left the TLB sequence at zero. With `0005`, the same error path made
one HDP call and advanced the sequence to one. Both retained the moved entry,
retried in the same process, passed reference-checked SGEMM with zero failures
and zero maximum absolute error, and powered off. A fresh probe-free five-patch
guest passed the same checked SGEMM. The two existing startup WARNs remain.
The probe repeats one PDE rather than using two distinct moved PDEs; exact
build and log hashes are in `tmp/p3v-cpu-pde-error-finalize/BUILD-RECORD.md`.

`0006-abort-failed-sdma-pde-job.patch` frees an unsubmitted SDMA PDE update
job when a later update in the moved-PDE loop fails. The optional backend
abort callback only discards a pending job; prepare failure and submission
clear the caller's job pointer, so the error path cannot free a submitted
job. The moved PDE entries remain on their list for retry. This does not
finalize a submitted SDMA prefix or repair range-update errors.

Matched scratch guests temporarily selected the SDMA builder for one real
compute PDE update while the guest otherwise used CPU VM updates. They
encoded six pending dwords, then injected `-ENOMEM` before repeating an
update on that PDE. Neither submitted an SDMA job. The five-patch control
returned with a pending job; the six-patch guest recorded one abort and no
pending job. Both retained the moved entry, retried through the normal CPU
backend, passed reference-checked FP32 128-by-128 SGEMM with zero failures
and zero maximum absolute error, and powered off. A probe-free six-patch
CPU-mode guest passed the same checked SGEMM. All three retained the two
existing startup WARNs.

A full SDMA-mode guest timed out on both SDMA rings with the five-patch
parent and the six-patch image before reaching SGEMM. The temporary backend
override tests pre-submit cleanup; it does not qualify the full SDMA mode.
Job rollover and submitted-prefix behavior were source-reviewed but not
dynamically tested. Exact build, image, and guest log hashes are in
`tmp/p3v-sdma-pde-abort/BUILD-RECORD.md`. Checked translation and HDP
visibility and cacheable peer access remained open at this six-patch stage.

`0007-preserve-kfd-unmap-retry.patch` keeps a freed-mapping descriptor when
its range clear fails. The KFD attachment records an unmap in progress, so a
reported clear or returned-fence error reaches the ioctl caller and a retry
does not remove the software mapping twice. A pending attachment cannot be
freed; an already mapped handle cannot be mapped again before its unmap
retry. KFD PTE updates drain the VM's pending clears and wait for their fence
before writing a new mapping, including at a reused VA. Unmap completion
checks its update fence before clearing the pending state. A page-directory
update failure attempts to roll back the new mapping and retains unfinished
cleanup for retry. When a mapping rollback reports a clear failure, its DMA
attachment stays mapped. A later map retry releases that attachment after
the clear succeeds and before mapping it again.

The matched CPU-mode fault guests injected `-ENOMEM` before one real freed
mapping clear. The six-patch control reported unmap success, allowed a second
allocation to map at the same VA, and rejected a retry of the first unmap as
`EINVAL`. The seven-patch guest returned `ENOMEM`, rejected a map of the
still-pending first handle as `EBUSY`, mapped the second allocation at the
same VA after draining the old clear, and completed the first unmap retry.
Both guest probes and their reference-checked SGEMM controls passed. The
reviewed patch revision passed the same one-shot probe and a separate
probe-free guest image. The latter detected `/dev/kfd`, passed
reference-checked FP32 128-by-128 SGEMM with zero failures and zero maximum
absolute error, then powered off normally. The two existing startup WARNs
remain. Build inputs, image hashes, and logs are recorded in
`tmp/p3v-kfd-unmap-review/BUILD-RECORD.md`; the six-patch matched control is
recorded in `tmp/p3v-kfd-unmap-production/BUILD-RECORD.md`.

This is a KFD retry and PTE update ordering repair. The seven-patch ioctl
probe did not read the replacement PTE through a GPU kernel. The
mapping-rollback DMA lifetime paths were reviewed in source but not
fault-injected. Partial range failures, SDMA submitted-prefix errors, direct
GART and unlocked SVM writers, and checked translation visibility still
needed separate proofs at that stage. The KFD TLB wrapper also still dropped
flush errors, so this patch did not authorize cacheable peer access,
or coherent RCCL P2P.

`0008-propagate-kfd-tlb-retry.patch` returns compute TLB flush errors through
KFD map and unmap ioctls. A new map flushes the VM before writing PTEs that
could reuse a stale VA. After an unmap clears PTEs, its attachments remain
pending until every requested device has flushed its TLB and released DMA
mappings. This lets a caller retry from `n_success=0`, as the active ROCr
thunk does, even if cleanup failed after an earlier device succeeded. A
successful ioctl then clears the pending state; free and remap reject it
while cleanup remains pending.

In matched one-shot `-ETIME` guests, the seven-patch control reported unmap
success despite the injected flush error. The revised guest returned `ETIME`,
then completed a zero-count retry and free. A second probe supplied the same
GPU ID twice and failed the second DMA cleanup call: the previous candidate
rejected a zero-count retry as `EINVAL`, while the revised candidate retried
and freed the allocation. These probes and their reference-checked SGEMM
controls passed. A probe-free eight-patch guest detected `/dev/kfd`, passed
reference-checked FP32 128-by-128 SGEMM with zero failures and zero maximum
absolute error, and powered off. All retained the two existing startup WARNs.
Exact inputs, hashes, commands, and logs are in
`tmp/p3v-kfd-tlb-retry/BUILD-RECORD.md` and
`tmp/p3v-kfd-tlb-production/BUILD-RECORD.md`.

An eight-patch GPU-read probe now checks local compute translation after a
KFD GTT allocation is unmapped, freed, and replaced at the same VA. Its
kernel read the first allocation's `0x13579bdf` and the replacement's
`0x2468ace0`; reference-checked SGEMM passed. With a one-shot pre-update
`-ENOMEM` on the first unmap, the eight-patch guest returned `ENOMEM` with
`n_success=0`, mapped a second allocation at that VA, and read its
`0x2468ace0` value before and after retrying and freeing the first handle.
Both allocations then unmapped and freed, and SGEMM passed. A matched
six-patch control read the first value but incorrectly reported unmap success
after the injected error, so its probe stopped before the replacement read.
The three guests retained the two existing startup WARNs. Commands, hashes,
and logs are in `tmp/p3v-kfd-translation-read/BUILD-RECORD.md`.

The duplicate-ID probe checks ioctl retry bookkeeping on one GPU; it does
not prove distinct-device peer access. AQL attachment and process teardown
paths were reviewed in source but not fault-injected. Other KFD queue and SVM
flush call sites still discard errors. Partial range failures, submitted
SDMA errors, direct GART and unlocked SVM writers, and other translation
paths remain unqualified. Cacheable peer access and coherent RCCL P2P remain
unqualified.
The same-VA GPU reads do not establish distinct-device or four-GPU coherent
traffic.

A later four-GPU fixture probe mapped one GTT allocation to two distinct KFD
GPU IDs, then unmapped and freed it. With a one-shot `-ETIME` on the second
device's DMA cleanup, unmap returned `ETIME` with `n_success=2`; retrying from
`n_success=0` succeeded and free completed. The normal and fault guests both
passed a post-cleanup reference-checked SGEMM with zero failures. Exact
images, module hashes, commands, and logs are in
`tmp/p3v-four-gpu-eightpatch/BUILD-RECORD.md`. This checks two-device cleanup
bookkeeping, but the probe did not read its GTT allocation on either GPU.
The remaining coherence and error-path gates above still apply.

The current AMDGPU patch set contains driver bug fixes `0001` through
`0008` and the optional KFD import/MAP logging patch `0011`. Earlier
experimental guest modules are outside this patch set; their results do
not qualify stock-driver cacheable coherence.

A later [zero-patch pod ablation](unpatched-amdgpu-pod-ablation-20261015.md)
passed the two-GPU peer probe and the four-guest RCCL workload without any of
these local driver patches. The eight error-path fixes remain separate
upstream candidates; this normal-path result does not make them required for
the pod qualification image. That ablation still used a nonstandard host peer
transport and therefore did not pass the revised VFIO exit gate.

A wider source search found a real
`unlocked=true` caller in `amdkfd/kfd_svm.c`:
`svm_range_unmap_from_gpu` calls `amdgpu_vm_update_range` from SVM
invalidation. The selected CPU backend brackets its PTE stores, but
`svm_range_unmap_from_gpus` clears `mapped_to_gpu` before a successful clear,
drops `kfd_flush_tlb` errors, and several notifier callers discard unmap
errors. The kernel's interval-notifier contract requires GPU page-table use
to have stopped when that callback returns. This error path needs repair or
an enforceable exclusion of SVM-backed cacheable aliases before eligibility
can advance.

A four-GPU fixture diagnostic with the unsigned nine-patch module exercised
the normal unlocked SVM notifier path. GPU0 read `0x13579bdf` from a
CPU-backed SVM page; `munmap` entered the notifier with the range mapped and
its unlocked GPU clear returned zero. A new page at the same VA was mapped
through KFD SVM ACCESS and read as `0x2468ace0`; its `munmap` again entered
with a mapped range and a successful unlocked clear. Reference-checked SGEMM
passed and the guest powered off. The diagnostic module added only
probe-scoped notifier and clear logging; source, image, command, hashes, and
logs are in `tmp/p3v-svm-invalidate/BUILD-RECORD.md`. This checks normal
local SVM translation and invalidation. Error handling, peer visibility, and
cacheable eligibility remain open.

A matched one-shot fault image returned `-ENOMEM` before the first SVM GPU
clear. The notifier had entered with the range mapped, but `munmap` still
completed without that clear. The probe reused the same VA, read the
replacement value on GPU0, passed checked SGEMM, and powered off. That later
success does not repair the missing invalidation at the first notifier
return. The fault image, exact command, source diff, module and image hashes,
logs, and checker are in `tmp/p3v-svm-clear-fault/BUILD-RECORD.md`. The
normal-run launcher correctly rejected this fault image because it observed
only one real successful clear across two `munmap` calls. SVM error ownership
and the unchecked TLB flush remain open; cacheable eligibility stays zero.

## GEMM qualification contract

A useful qualification workload calls `rocblas_sgemm` and compares every
output element against a CPU reference. The reference qualification used an
FP32, column-major, non-transposed 128 x 128 x 128 multiply with alpha 1 and
beta 0. Its inputs were deterministic. A validator can expose this stable log
contract:

```text
guest: /dev/kfd present
sgemm-validator: api=rocblas_sgemm ... m=128 n=128 k=128 alpha=1 beta=0
sgemm-validator: max_absolute_error=... failures=0
sgemm-validator: PASS
guest: done
```

Do not qualify the device merely because the kernel probed or a kernel was
submitted. Require numerical validation, a zero-status QEMU exit, and orderly
rocJITsu shutdown. The packaged rocBLAS installation must select a supported
gfx1250 backend and find its matching library data without runtime environment
overrides.

## Launch the guest

Choose a short output path because Unix-domain socket paths are limited. The
output directory must not already exist.

```bash
QEMU=/path/to/qemu-system-x86_64
KERNEL=/path/to/vmlinuz
INITRAMFS=/path/to/gfx1250-compute-initramfs.gz
ROCJITSU=build-vfio/tools/rocjitsu/rocjitsu
OUTPUT=/tmp/rocjitsu-gemm-run

python3 scripts/run-vfio-guest.py \
  --qemu "${QEMU}" \
  --kernel "${KERNEL}" \
  --initramfs "${INITRAMFS}" \
  --rocjitsu "${ROCJITSU}" \
  --config configs/gfx1250_mi455x.json \
  --output "${OUTPUT}" \
  --accel auto \
  --memory 4G \
  --probe-timeout 10 \
  --startup-timeout 60 \
  --append 'console=ttyS0 rdinit=/init panic=-1 amdgpu.discovery=2 amdgpu.emu_mode=1 amdgpu.fw_load_type=0 amdgpu.vm_update_mode=3 amdgpu.gpu_recovery=0 amdgpu.vramlimit=1024 amdgpu.ip_block_mask=0x3f rocjitsu.workload=sgemm' \
  --expect-log 'guest: /dev/kfd present' \
  --expect-log 'sgemm-validator: PASS' \
  --reject-log 'sgemm-validator: FAIL' \
  --reject-log 'guest: FATAL:'
```

The 1 GiB VRAM limit leaves enough guest VRAM for ROCr to provision queue
scratch at the device's advertised occupancy. A smaller limit can be adequate
for scratch-free kernels but may make a private-segment dispatch wait
indefinitely for scratch allocation.

The repository does not provide the validator binary, so make the guest
validator emit the example markers above or replace the `--expect-log` and
`--reject-log` values with its stable public output.

`--accel auto` selects KVM when QEMU advertises it and `/dev/kvm` is
usable; otherwise it selects TCG. KVM and TCG both expose the same VFIO-user
device. TCG is slower but avoids a host KVM dependency.
`--smp` sets the guest virtual CPU count; its default is one. The four-rank
RCCL P2P guest below uses `--smp 4`.

Run the same command with `--dry-run` first. Dry-run validates all input paths
and executable permissions, confirms that QEMU provides `vfio-user-pci`, asks
the selected rocJITsu binary to confirm that it was built with VFIO-user
support, selects the accelerator, prints the exact server and QEMU argument
vectors, and does not create the output directory.

Each QEMU or rocJITsu capability probe is limited to `--probe-timeout`
seconds (10 by default). SIGTERM or SIGINT sent to the launcher while a probe
is running terminates and reaps that probe before the launcher exits.

The launcher waits at most `--startup-timeout` seconds (60 by default) for the
server to create and explicitly announce its listening socket. It then checks
the socket, creates shared memfd-backed guest RAM, and starts:

```text
rocjitsu --config configs/gfx1250_mi455x.json \
  --vfio-socket <output>/vfio-user.sock
```

and connects QEMU's `vfio-user-pci` device to that socket. Shared guest RAM
is required so the VFIO-user server can map DMA windows.

### Expose multiple local GPUs

Repeat `--socket` once for each local GPU, in GPU ordinal order. Every socket
must have a distinct, short path directly inside the new output directory.
The paths are the complete ordered local GPU list; specifying one `--socket`
does not append the default socket. The default remains
`<output>/vfio-user.sock` when no `--socket` is specified. rocJITsu validates
the socket count against the selected configuration or local node.

For the repository's four-GPU configuration, use the same prepared guest inputs
and kernel command line as above, with four explicit sockets:

The preset uses PCI ID `0x1002:0x75c1` for every GPU, matching the single-GPU
guest contract. The guest must discover four distinct BDFs and confirm that
AMDGPU binds each one before running per-GPU numerical checks.

```bash
OUTPUT=/tmp/rocjitsu-four-gpu-run

python3 scripts/run-vfio-guest.py \
  --qemu "${QEMU}" \
  --kernel "${KERNEL}" \
  --initramfs "${INITRAMFS}" \
  --rocjitsu "${ROCJITSU}" \
  --config configs/gfx1250_mi455x_kmd_4gpu.json \
  --output "${OUTPUT}" \
  --socket "${OUTPUT}/gpu0.sock" \
  --socket "${OUTPUT}/gpu1.sock" \
  --socket "${OUTPUT}/gpu2.sock" \
  --socket "${OUTPUT}/gpu3.sock" \
  --accel auto \
  --memory 4G \
  --append 'console=ttyS0 rdinit=/init panic=-1 amdgpu.discovery=2 amdgpu.emu_mode=1 amdgpu.fw_load_type=0 amdgpu.vm_update_mode=3 amdgpu.gpu_recovery=0 amdgpu.vramlimit=1024 amdgpu.ip_block_mask=0x3f rocjitsu.workload=sgemm'
```

The probe-free eight-patch guest enumerated and bound all four PCI functions
at `0000:00:04.0` through `0000:00:07.0`. A second image selected each GPU
by `HIP_VISIBLE_DEVICES`, checked that HIP reported the expected BDF, and
ran the reference-checked FP32 128-by-128 SGEMM on each one. All four runs
reported zero failures and zero maximum absolute error. The two preexisting
startup WARNs remained. Inputs, commands, hashes, and logs are in
`tmp/p3v-four-gpu-eightpatch/BUILD-RECORD.md`. These runs qualify four local
compute paths under the replicated preset; they do not check peer access.

To use the explicit four-GPU scale-up schematic instead of the legacy replicated
preset, replace the config argument above with
`--config configs/gfx1250_mi455x_4gpu_scaleup.json` and add `--node node0`.
Keep all four sockets and the same guest inputs. This graph projects local
fabric routes but does not advertise KFD peer links. Its 1 GiB BAR0 aperture
per GPU covers the guide's 1 GiB guest VRAM limit; this is a simulator guest
setting, not a physical BAR claim. The per-GPU GEMM check validates
local compute only; the larger BAR does not qualify guest P2P or RCCL.

Use `--node <id>` with a system manifest to select the local node served by
this process; rocJITsu checks the selection. The launcher starts one rocJITsu
server and waits for one readiness signal, then checks that every requested
socket exists before starting QEMU. For multiple GPUs, QEMU receives one
`vfio-user-pci` device per socket on `pcie.0` at slots `0x4`, `0x5`, and so
on, with IDs `rocjitsu-gpu-0`, `rocjitsu-gpu-1`, and so on. The single-GPU
QEMU device arguments remain unchanged.

The existing GEMM qualification contract covers one GPU. A multi-GPU launch
does not by itself establish guest PCI enumeration, peer DMA, RCCL operation,
or numerical correctness. Check the actual guest BDFs and validate the intended
multi-GPU workload before reporting such a result.

### Build QEMU with general PCIe fixes

The tested QEMU source is 10.1.0 commit
`f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3`. Apply the repository's
general PCIe fixes to a clean checkout, then build in a separate directory:

```bash
QEMU_SOURCE=/path/to/qemu-10.1-source
QEMU_BUILD=/path/to/qemu-10.1-build
scripts/apply-qemu-pcie-fixes.sh "$QEMU_SOURCE"
mkdir -p "$QEMU_BUILD"
(
  cd "$QEMU_BUILD"
  "$QEMU_SOURCE/configure" --target-list=x86_64-softmmu --enable-kvm \
    --disable-docs --disable-tools --disable-guest-agent --disable-werror
  ninja qemu-system-x86_64
)
```

The script fixes QEMU VFIO-user's class-code default so the guest retains the
device's compute class. `qemu-10.1-xio3130-link-capability.patch` fixes a
separate PCIe bridge defect: QEMU 10.1
otherwise publishes zero speed and width in each XIO3130 downstream port's
LinkCap, even though its LinkSta reports Gen1 x1. The selected AMDGPU driver
reads that parent LinkCap when it initializes PCIe bandwidth, and zero width
leaves KFD with an empty lane mask. The patch gives the port valid Gen1 x1
defaults through QEMU's ordinary link properties. It changes no guest driver
code or PCIe AtomicOp capability.
`qemu-10.1-pcie-atomic-capabilities.patch` adds root
port 32-bit and 64-bit completer properties and PCIe switch routing property
default to off. The VFIO DMA backend completes aligned 32-bit and 64-bit
atomics on mapped guest RAM; the launcher enables those PCIe bits only with
`--p2v-atomic-root`. The peer GPU endpoint continues to advertise no AtomicOp
completion, and the server rejects atomics aimed at a peer BAR grant.

These QEMU fixes do not change the VFIO-user protocol. Standard
descriptorless peer BAR DMA maps carry no owner trailer or socket ordinal;
the server resolves them through its live PCI BAR address decoder. For a two-
or four-GPU peer-admission diagnostic, pass
`--p2v-switch-topology`. It places every ordered GPU socket behind its own
downstream port of one X3130 switch. The option requires exactly two or four
sockets and does not change the default PCI layout. A four-GPU run also needs
BAR0 to cover each GPU's used VRAM; the default 256 MiB aperture with a 1 GiB
guest VRAM limit is insufficient for peer admission. The switch option alone
does not qualify peer mappings or coherent traffic.
Preserve the exact QEMU source commit, patch choice, binary hash, launcher
arguments, and server binary hash in the run record.

The selected gfx1250 AMDKFD driver requires PCIe atomics to guest RAM before
it exposes a ROCm device. For the two-GPU switch path, pass
`--p2v-atomic-root` only with a server that implements aligned guest-RAM
atomics. The launcher checks that patched QEMU exposes the root and switch
properties, then enables both root completion widths and routing on that
switch path. Without this option, the capabilities stay off and the current
guest reaches `hipGetDeviceCount` with no ROCm-capable device. This option
does not qualify peer BAR atomics, cacheable peer access, or coherent fabric.

Guest P2V qualification requires a requester kernel to read and write owner
VRAM and the owner to read back the expected value. For the prepared g7 HIP
probe, require one `p2v-hip: numerical` line with
`observed=0x13579bdf`, `final_owner=0x1357c047`, matching expected fields,
and `result=PASS`, plus zero-status guest exit and orderly server shutdown.
A successful KFD
peer map, requester PTE update, HIP launch, or synchronize alone is
insufficient. No guest P2V or AtomicOp result is qualified by the patch or
launcher option alone.

### Four-GPU fixture peer and RCCL results

With the probe-free eight-patch module, the four-GPU guest numerically checked
requester GPU1 reading and writing owner GPU0 VRAM. An expanded HIP probe
passed the same sentinel and final-owner checks on all 12 directed GPU
pairs; the server recorded one committed read and write on every matching
route. The guest used a nonstandard peer transport and a diagnostic switch that
advertises AtomicOp routing bits for peer-map admission. These probes did
not execute an AtomicOp.

The four-rank RCCL P2P guest then passed AllReduce, Broadcast, AllGather,
ReduceScatter, and SendRecv on all four ranks, with 20 passing reference
results and four distinct bus IDs. Its logs showed P2P/IPC data channels,
and the server recorded writes on eight directed fabric routes. Exact
images, binaries, commands, hashes, and logs are in
`tmp/p3v-four-gpu-eightpatch/BUILD-RECORD.md`. These results establish
functional peer reads and writes and numerical RCCL P2P under this
diagnostic setup. Cacheable coherence, AtomicOp completion, and the
remaining VM error paths remain unqualified. Peer cache fills stay disabled.

Older guest experiments used unsupported interfaces and are excluded from
this qualification. Their numerical results do not qualify cacheable
coherence or peer AtomicOp completion.

A separate size-controlled four-vCPU diagnostic passed all five RCCL cases
at 1,024 and 262,144 total FP32 elements, with three host-reference-checked
iterations per rank. The endpoint now reports successful backing bytes as
well as effect counts per directed route. Source-matched RCCL tuning logs
selected RING/LL for the four small collectives and RING/SIMPLE for the
large ones; SendRecv reported P2P setup completion on every rank. Each run
logged completed legacy IPC buffer imports on every rank, and no selected
P2P/IPC send connector used `/read` or `/CE`. The large isolated cases
recorded 59,782,752 aggregate committed backing-write bytes and 118,476
writes across the twelve directed routes; all peer read counters were zero.
The exact image, binaries, commands, per-case totals, route counters, and
log hashes are in `tmp/p4b/BUILD-RECORD.md` and
`tmp/p4b/matrix-summary.json`. These byte totals may include transport
metadata and do not identify payload backing ranges or match each IPC
import to a particular fabric effect. Guest KFD MAP identity, cacheable
visibility, checked GART publication, and a release-compatible firmware
tuple remain unqualified.

For a VFIO diagnostic with at least two functions, pass
`--fabric-effect-trace` to the launcher. The server reserves room for
200,000 committed directed effects before serving, then reports each effect's
request ID, requester/owner GPU IDs, operation, canonical backing ID and
offset, byte count, target-map ID, requester GPU VA, and IOVA at shutdown.
The opt-in trace records no failed or queued effect. It reports overflow and
exits with an error if any effect was dropped. Run
`python3 scripts/check-vfio-fabric-trace.py SERVER_LOG CASE_SUMMARY_JSON
GUEST_LOG CONFIG_JSON` for the four-rank RCCL fixture. The checker matches
every record with directed counts and byte totals, the host-reference case
summary, and exactly one completed RCCL IPC import range in the requester's
rank log. It resolves each rank's bus ID to a GPU ID using the four-GPU
configuration. The map ID belongs to the QEMU/VFIO target grant. A VA
match to an RCCL import range does not identify the guest KFD MAP handle,
the selected channel, or application payload bytes.

With the package-pinned guest patch `0011-trace-kfd-import-map.patch`, also
pass `amdgpu.p4v_ipc_map_trace=1` and add `--require-kfd-map` to the checker.
The guest logs successful KFD DMA-buf and IPC import ioctls and each imported
BO's completed GPU MAP after its sync and TLB flush. The checker joins the
requester's rank PID, the KFD handle and VA extent, the guest KFD GPU IDs,
and the RCCL import range to each fabric effect. In the selected legacy
RCCL fixture, the kernel import is the DMA-buf ioctl; the separate KFD IPC
import ioctl does not run. A completed MAP record does not prove its lifetime
at the later effect, the connector channel, or the application payload handoff.

### Connect guest NICs for a NET/Socket control

The launcher adds no NIC by default. To connect two independently launched
guests over QEMU's socket Ethernet backend, add one of these option pairs to
each otherwise complete launch command:

```text
node0: --net-socket-listen 127.0.0.1:17000 --net-mac 02:00:00:00:00:01
node1: --net-socket-connect 127.0.0.1:17000 --net-mac 02:00:00:00:00:02
```

Start the listening launcher first. Wait until its QEMU process binds the
host TCP port (for a local run, inspect the listening port with `ss -ltn`),
then start the connector while the listener remains running. A TCP connect
probe can consume QEMU's single peer connection. Use separate output
directories and VFIO sockets. Select `--node node0` and `--node node1` with
the two-node system manifest. On different hosts, bind the listener to an
address reachable by the
connector and open that TCP port. Each endpoint must be numeric IPv4 with a
port from 1 to 65535, and each NIC needs a distinct unicast MAC. The NIC uses
Q35 PCI slot `0x8`, leaving slots `0x4` through `0x7` for up to four GPU
functions.

The socket endpoint is a host transport address; it does not assign guest IP
addresses. The guest image must bring up its virtio NIC, configure distinct
addresses and a route, and check peer connectivity. RCCL also connects to its
own advertised guest IP during bootstrap, so bring up loopback and check a
local TCP connection. Give the two guests distinct hostnames or
`NCCL_HOSTID` values so RCCL identifies them as separate nodes.

After mounting `devtmpfs` on `/dev`, create and mount `/dev/shm` before
starting RCCL:

```sh
mkdir -p /dev/shm
mount -t tmpfs -o mode=1777,nodev,nosuid tmpfs /dev/shm
ip link set lo up
```

The selected RCCL library checks `/dev/shm` during communicator setup even
when `NCCL_SHM_DISABLE=1`; creating it in the staging root before the
`devtmpfs` mount is insufficient.

The `hip_rccl_gfx1250_test` rank binary supports a two-guest TCP bootstrap.
Build it with
`cmake --build build-vfio --target hip_rccl_gfx1250_test_target`, then
package it with matched `librccl`, its transitive ELF dependencies, and the
gfx1250 RCCL code object. Rank 0 uses `--rank=0 --world-size=2` and
`--bootstrap-listen=GUEST_IP:PORT`; rank 1 uses `--rank=1 --world-size=2` and
`--bootstrap-connect=RANK0_GUEST_IP:PORT`. Generate a fresh 128-bit
hexadecimal run ID for each pair, for example with
`python3 -c 'import secrets; print(secrets.token_hex(16))'`. Pass it to
both ranks as `--bootstrap-run-id=ID`. Use the same seed, test filter, and
`--bootstrap-timeout-ms`, and assert `--expected-devices=1` on each guest.
These bootstrap addresses are guest IPs, separate from QEMU's host socket
endpoints. Existing daemon tests still use `--shared-dir`.

Set `NCCL_NET=Socket`, `NCCL_SOCKET_IFNAME` to the guest NIC, and disable IB,
P2P, and SHM for the NET control. Require numerical GoogleTest success on
both ranks and `NET/Socket` channel evidence. The bootstrap timeout covers
only its handshake and case exchange; the paired guest controller must also
bound the complete run and clean up both guest processes on failure.

### Earlier same-host guest NET controls, terminal fault, and rank loss

A same-host run connected two independent VMMs with QEMU socket Ethernet over
`127.0.0.1` and assigned guest IPs `10.77.0.1` and `10.77.0.2`. With one GPU
visible per guest, both ranks passed AllReduce, Broadcast, AllGather,
ReduceScatter, and SendRecv over `NET/Socket`; the AllReduce host-reference
checks found zero mismatches. The run record is
`tmp/p5v0-rccl-image-v13/five-case/faultfix-result.json`.

Using the same guest image, an invalid AllReduce destination at GPU VA
`0x4000` left HIP and RCCL reporting success after five seconds with the
earlier server. With the VM-fault interrupt route, both guests received a KFD
device-memory-violation event and `hipPeekAtLastError` and `hipStreamQuery`
reported an illegal memory access within five seconds. Immediate
`hipStreamSynchronize` and RCCL async queries still returned success, so this
check establishes delayed guest-visible fault reporting, not synchronous
failure at the collective call. The baseline and updated run records are
`tmp/p5v0-terminal-fault/base-result.json` and
`tmp/p5v0-terminal-fault/tim-result.json`; their assertions and binary hashes
are in `tmp/p5v0-terminal-fault/gate-summary.json`. This earlier two-guest
control exercises only NET/Socket between one GPU in each guest. Its scope
excludes mixed local P2P/NET traffic. The later
[same-host pod gate](same-host-pod-rccl-gate.md#run-this-gate) qualifies normal
mixed transport on one host. Operation across two actual hosts remains
unqualified.

The four-vCPU rank-loss fixture uses that same pair of independent VMMs and
one GPU per guest. The opt-in rank deadline covers collective submission and
HIP stream synchronization. Its first AllReduce iteration checks the H2D
input, a GPU copy, the destination sentinel, and the result against the host
reference. The guest runs a separate shell monitor for the timeout marker, so
it can request poweroff if rank exit blocks in KFD teardown. The image is
`tmp/p5v0-loss/smp4-image/initramfs.gz` (SHA-256
`39da49790291e6c1732c03f359d5b30c0f881b80640a235d42265dd5b08d9451`).
With the Release VFIO server (SHA-256
`461209e501ab5788ab333293746cd539ef10430d4f0b3c6e3eea66dede6c14c7`),
both guests passed all five cases with `NET/Socket` per case, zero
input/copy/sentinel/result mismatches, normal poweroff, and no remaining VFIO
sockets. The record is `tmp/p5v0-loss/d49adc7af83d/result.json`.

The control server left the survivor stuck during rank exit: the guest logged
`RCCL_COLLECTIVE_TIMEOUT`, then KFD queue eviction waited for a MES
`REMOVE_QUEUE` fence and never powered off within the 180-second controller
deadline (`tmp/p5v0-loss/97f1d2339a89/result.json`). MES removal had used
graceful queue close, which can return busy for outstanding work and leave the
removal frame unacknowledged. Explicit MES removal now preempts unfinished
compute work only after committed cursor, completion, and scratch publication
state is clear. Pending publication leaves the queue live for retry; terminal
publication failure requires reset or force cancellation. The 89 affected
MES, registry, VM service, and PCI tests pass, including the two PCI cursor
publication checks that failed with unconditional force cancellation.
The PCI frontend boundary check also passes after compute-unit handler wiring
moved behind the SoC interface.

With the Release server above, the controller killed rank 0's QEMU after both
ranks entered AllReduce over `NET/Socket`. Rank 1 reported the 90-second
collective timeout, logged a guest failure, and powered off within the
180-second loss window. Both launchers exited without controller interruption,
and neither VFIO socket remained. The record is
`tmp/p5v0-loss/9ce847fbd188/result.json`. The deadline provides guest
workload fail-stop; native RCCL peer-error response remains unverified. These
runs used the original QEMU binary (SHA-256
`6490713c842d4b8ff713a02c280f0581353fd6a3c3a87ff1374d37f54127a099`).
The rank-loss fixture covers NET-only failure handling. Mixed-transport rank
loss remains unverified; the later four-node runs record normal same-host
mixed P2P/NET operation. MPI-enabled `rccl-tests`, release-matched firmware,
and two-host operation remain unqualified.

### Same-host exit gate: four guests on one host

The complete current gate, including the equivalent emulated KFD run, is in
[the same-host gate](same-host-pod-rccl-gate.md#run-this-gate). Four independent
guests each need two modeled GPUs and one RCCL rank per GPU in the same
communicator: the current controllers require exactly four nodes with two
GPUs each. Each guest must use local GPU fabric for P2P/IPC and its
NIC for cross-guest NET traffic. The selected A0 driver uses UC PCIe peer BAR
mappings; a configured hive ID or model link does not establish native xGMI.
Require per-rank numerical references for all five collectives at small and
large sizes with repeats, both channel types, directed committed fabric
effects, bounded completion, and clean teardown. The two-host and cacheable
peer-coherence qualifications follow this same-host gate.
The [2026-10-19 local result](same-host-pod-rccl-result-20261019.md)
records both modes with `--fabric-effect-trace` selecting directed evidence,
but its source capture does not qualify the current rebased tree.
The [2026-10-15 result](same-host-pod-rccl-result-20261015.md) passes this
gate in both modes with zero local AMDGPU/AMDKFD patches and standard
VFIO-user peer DMA maps. The earlier
[2026-10-14 result](same-host-pod-rccl-result-20261014.md) remains a
historical control; its VFIO run used a removed nonstandard peer
transport.

## Results and reruns

The launcher writes:

```text
<output>/guest.log
<output>/server.log
```

Success requires all requested log markers, no rejected marker, QEMU status
zero, and cooperative rocJITsu termination. The launcher sends SIGTERM to the
server after QEMU exits and waits up to five seconds for it to stop cleanly.
After that grace period it sends SIGKILL, reaps the server, and fails the run.
Any server exit while QEMU is still running fails the run, regardless of exit
status. An orderly guest disconnect does not terminate the server; it remains
alive until the launcher observes QEMU exit and requests shutdown.

Each run needs a new output directory. Preserve the logs together with:

- the rocJITsu Git commit;
- the QEMU version;
- the accelerator selected by dry-run;
- kernel, initramfs, AMDGPU package, firmware package, and ROCm package
  versions and SHA-256 digests;
- the exact kernel command line;
- the GEMM dimensions, input definition, reference calculation, and
  acceptance tolerance.

## Troubleshooting

### QEMU does not recognize `vfio-user-pci`

Use a QEMU build with VFIO-user PCI support. This is distinct from the
host-kernel VFIO passthrough devices.

### The server does not report readiness

Inspect `server.log`. Also keep the output path short and ensure that no
stale path already exists. The socket must be directly inside the output
directory. The launcher waits on a pipe inherited by rocJITsu, which reports
readiness after configuration parsing, topology construction, engine startup,
and the final socket bind. Process exit or a closed pipe reports startup
failure immediately; a live server that does not report readiness receives
SIGTERM after `--startup-timeout` seconds and is force-killed if it cannot
complete the bounded shutdown handshake.

### AMDGPU reports a missing firmware file

Copy the named file from the firmware package matching the guest AMDGPU module,
then rebuild the initramfs. Absence of JPEG/VCN hardware only removes media
firmware requirements; it does not remove compute, MES, SDMA, IMU, or
IP-discovery parser inputs.

### AMDGPU fails while discovering multimedia IP

Use a driver containing `4e07da515d1c` or its backport. Do not work around
this by adding a fake JPEG or VCN device to rocJITsu.

### `/dev/kfd` is absent

Check `guest.log` for the first AMDGPU probe failure. Verify the PCI ID,
module/kernel match, firmware inventory, kernel configuration, and the
compute-only IP-block mask before debugging ROCm user space.

### rocBLAS cannot find a kernel

Verify that the guest contains the gfx1250 Tensile metadata and code object
from the same rocBLAS package as `librocblas.so`. Do not substitute files
from another GPU target.

### The run stops making progress

The launcher does not impose a runtime deadline. It waits for QEMU to exit and
fails immediately if rocJITsu exits first. A normal guest disconnect leaves the
server alive until the launcher observes QEMU's exit and requests shutdown, so
this ordering needs no grace period. Use the partial `guest.log` and `server.log`
to distinguish slow progress from a deadlock. CI systems can enforce a job-level
budget without changing launcher behavior. If that budget sends SIGTERM or
SIGINT to the launcher, it terminates and reaps both children and removes the
owned VFIO sockets before exiting. SIGKILL cannot provide cooperative cleanup.
