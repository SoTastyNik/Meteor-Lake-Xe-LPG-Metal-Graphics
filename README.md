# Meteor Lake Xe-LPG Hardware Acceleration for macOS

![License](https://img.shields.io/badge/License-Custom_(Apache--2.0_original_work)-lightgrey.svg)
![Platform](https://img.shields.io/badge/Platform-macOS_15_Sequoia-blue)
![Arch](https://img.shields.io/badge/Arch-x86__64-informational)
![Bootloader](https://img.shields.io/badge/Bootloader-OpenCore_1.0.8-9cf)
![Hardware](https://img.shields.io/badge/Hardware-Intel_Core_Ultra_5_135U-orange)
![Graphics](https://img.shields.io/badge/Graphics-Xe--LPG%20%2F%208086%3A7D45-red)
![Firmware](https://img.shields.io/badge/Firmware-GuC_70.53.0-blue)<br>
![API](https://img.shields.io/badge/API-Metal%20%2F%20Vulkan-purple)
![Vulkan](https://img.shields.io/badge/Vulkan-ANV_%2F_Mesa_26.3.0-purple)
![Kernel](https://img.shields.io/badge/Kext-i915_on_LinuxKPI-red)
![Language](https://img.shields.io/badge/Language-C%20%2F%20Obj--C%20%2F%20C%2B%2B-blueviolet)<br>
![Status](https://img.shields.io/badge/Status-Metal%20%2B%20Vulkan%20working-brightgreen)
![Desktop](https://img.shields.io/badge/Desktop-WindowServer_in_progress-yellow)
![Verified](https://img.shields.io/badge/Verified-26%2C000_frames-brightgreen)
![Candidate](https://img.shields.io/badge/Candidate-0.3.5_%2B_k1.0.13_panic-red)

A hardware-acceleration port that brings **Metal and Vulkan** to the **Intel Core Ultra (Meteor Lake-P)
Xe-LPG iGPU (`8086:7D45`)** on a **Dell Latitude 5350** running **macOS 15 Sequoia**, using the
[NullMoth](https://github.com/nullmoth/nvidia-macos-driver) NVIDIA-for-macOS driver tree as the driver
skeleton and retargeting its graphics stack from NVIDIA/GSP to Intel i915/GuC.

The port reuses NullMoth's *Metal driver plugin → shader translator → Mesa Vulkan backend → kernel
extensions* architecture, but replaces every NVIDIA-specific element: the GSP firmware path becomes the
Intel GuC/HuC/GSC firmware path, the NVK backend becomes Mesa's **ANV** Intel driver, and the NVIDIA
kernel extensions become an i915-derived `NMXGPU` plus a DRM-user-client `NMXAccel`.

## 📑 Contents

- [What works today](#works)
- [Status at a glance](#status)
- [Security warning](#security)
- [Hardware and software target](#target)
- [Compatibility](#compatibility)
- [Architecture](#architecture)
- [Component inventory](#components)
- [Implementation detail](#implementation)
- [The current blocker](#blocker)
- [Failure signatures](#failures)
- [Struggles and breakthroughs](#history)
- [Validation methodology](#validation)
- [Reproduce the claims](#reproduce)
- [Diagnostics cheat-sheet](#diagnostics)
- [Workspace layout](#workspace)
- [Building and testing](#build)
- [Roadmap](#roadmap)
- [Version history](#versions)
- [Attribution and licensing](#licensing)
- [Design principles](#principles)
- [Design decisions](#adr)
- [Glossary](#glossary)
- [FAQ](#faq)
- [Where this breaks with consensus](#consensus)

<a name="works"></a>
## ✅ What works today

**Metal and Vulkan run on the Xe-LPG iGPU.** This is not aspirational — it is measured on the physical
Dell Latitude 5350, under macOS 15.8.1, with exact-pixel validation:

* **Vulkan (ANV)** enumerates the real device `8086:7d45`, submits a compute shader and returns
  **65,536 correct values**.
* **Metal** selects a device attached to `NMXAccel`, computes correct values and renders
  **4,096 correct pixels**.
* The full hardware gate passes **26,000 frames** across **22 cases** (11 IOKit + 11 direct routes),
  including padded-row full-HD and RGBA/BGRA IOSurface backing-pixel verification — report
  `readback-20261019-114424`. Earlier Metal/Vulkan compute and 4096-pixel render passes are recorded in
  report `20261018-145513`.
* Command-pool accounting across that gate: **80,020 created / 80,020 destroyed**, zero live, pending or
  quarantined.

So the hard parts of a graphics port — PCI attach, GuC firmware bring-up, GGTT/staging memory, AIR→SPIR-V
lowering, and Metal/Vulkan application rendering and compute on real silicon — **work today**.

The one thing still in progress is **WindowServer compositing the desktop on the physical panel**. That
is a distinct, narrower problem (a readback/surface path under concurrent WindowServer load), and it is
described in *The current blocker* below. A working Metal/Vulkan stack and a composited login screen are
two different milestones; this project has finished the first and is attacking the second.

The latest kernel work moved the question from *which submission stalls* to *what changed the ring*: the
1.0.10 build captured the corrupted words, and the 1.0.11 mapping-safety fix was built and booted — the
hardware reproduced the same overwrite, so the next step is naming the writer rather than guessing. A
second candidate (kernel 1.0.12 + framebuffer 0.2.4) corrected a raw-physical allocation assumption and
refused to export a buffer whose pages are not host-contiguous; it was booted on 19 October and the
overwrite **still occurred**. A third candidate (kernel 1.0.13) withholds the firmware's stolen-memory
region from i915; it **panicked ~8 seconds into boot**, before any desktop, on an uninitialised context
lock in the GuC completion path. None of these is a fix. That is documented in *The current blocker*.

---

<a name="status"></a>
## 📊 Status at a glance

| Milestone | Evidence | Status |
| :--- | :--- | :--- |
| Real GPU identification (`8086:7D45`, Dell `1028:0CB6`) | macOS probe and the laptop's own Linux report agree | **Confirmed** |
| `NMXGPU` i915 kernel extension loads and attaches to the real GPU | Report `readback-20261019-114424`, kernel UUID match | **Confirmed** |
| Memory-mapped I/O / GGTT / firmware bring-up (GuC 70.53.0) | Kernel capture `kernel-guc-capture-1.0.9.log`; firmware loaded on both GTs | **Confirmed (init only)** |
| **Metal and Vulkan application rendering/compute** | **65,536 correct Vulkan values, 4,096 correct Metal pixels**, 26,000 exact frames across 22 cases (11 IOKit + 11 direct) | **Working** |
| Command-pool lifetime | **80,020 pools created / 80,020 destroyed**, zero live/pending/quarantined across the gate | **Passing (scoped)** |
| Accelerator + display-pipe registration | 0.2.4 / 0.2.5 reports: pipe 0 verified, phase-2 power-on complete, pipe active | **Init confirmed** |
| GPU-composited WindowServer desktop | The cut-off moves with the candidate — 0.2.5/0.3.2 stall at readback **#5** (upload #6 ~80 ms later), 0.3.3 at its **fourth** readback, 0.3.4/0.3.5 at **submission #8**, 1.0.12 completes readback #8 then stalls on **submission #9**. The hang itself is invariant | **Failing — blocking** |
| Kernel command-ring integrity | 1.0.10 capture: the words below request 20's head (`0xc98–0xca4` — request 18's switch-out and WA tail) read `0xff000000`; GuC `IPEHR=0xff000000`, `RING_HEAD=ACTHD=0xca4`. **Identical on 1.0.11.** The 1.0.12 boot again saved `0xff000000` at request 22's `0xe00–0xe0c`, with `IPEHR=0xff000000`, `RING_HEAD=ACTHD=0xe0c`, `RING_TAIL=0xf70` | **Corrupted — writer unidentified** |
| Kernel boot integrity (1.0.13) | `panic: NullMoth xkpi: mutex … used before mtx_init` at 8.04 s uptime, backtrace `guc_retire_inflight_request_prio` ← `signal_irq_work` ← `irq_work`. The lock is a zeroed `intel_context.guc_state.lock`; no desktop was reached | **Panics before desktop — parked** |
| i915 CPU user-mapping page lifetime | Source audit: `lkpi_unmap_mapping_range` is a no-op and the i915 `vm_ops_cpu` path did not register the lifetime page pin the TTM path installs. Kernel 1.0.11 adds it | **Defect confirmed in source; does not fix the hang** |
| Raw-physical buffer export | `nmxVramAlloc` / `nmx_xnu_mem_alloc` requested only `kIOMemoryPhysicallyContiguous` and exported `getPhysicalSegment(0, …, MapperNone)` without checking the segment length. 1.0.12 + framebuffer 0.2.4 add `HostPhysicallyContiguous \| MapperNone` and a span check | **Booted 19 Oct 18:00; overwrite persisted; no span-refusal line in the retained log, so the guard's execution is unverified** |
| Panel scanout with correct pixels | Framebuffer loads and describes 1920×1080, reaches fixed scanout; presentation samples remain zero | **Partial / unverified** |
| Sleep-wake, brightness, external displays, video decode, long soak | No passing evidence | **Unverified** |

Every row above is traceable to a dated report under `research/`. The point of the table is to keep the
**working** Metal/Vulkan stack clearly separated from the **unfinished** desktop composition.

---

<a name="security"></a>
## ⚠️ Security warning

This project requires changes that weaken macOS platform security:

| Setting | Effect |
|---|---|
| `csr-active-config = 0x0A43` | Disables large parts of System Integrity Protection |
| `SecureBootModel = Disabled` | Disables Apple Secure Boot |
| AMFIPass + `amfi_get_out_of_my_way=0x1` | Bypasses AMFI code-signing enforcement |
| Custom kexts in the Auxiliary Kernel Collection | Unsigned, unnotarised kernel code runs at boot |

**Do not do this on a machine holding irreplaceable data or credentials.** A boot loop, a kext panic or a
damaged kernel collection can make the installation unbootable. Keep a known-good EFI on a separate USB
drive and a full backup off-device. This is an experimental hardware-porting project, not a supported
configuration.

---

<a name="target"></a>
## 🎯 Hardware and software target

| | |
|---|---|
| Machine | Dell Latitude 5350 |
| CPU | Intel Core Ultra 5 135U — 12C/14T (2 P Redwood Cove + 8 E Crestmont + 2 LP E), CPUID `A06A4` |
| iGPU | Meteor Lake-P Xe-LPG, PCI `8086:7D45`, subsystem `1028:0CB6`, rev 08 |
| OS | macOS 15 Sequoia 15.8.1 (24H32), x86_64 |
| Graphics stepping | `B0` |
| Cache/coherency | `has_llc=no`, `has_snoop=yes`, `has_flat_ccs=no` (from the laptop's Linux report) |
| Firmware | GuC **70.53.0**, DMC **2.23**, HuC **8.5.4**, GSC **102.1.15.1926** |

The GPU model is not guessed: the macOS PCI probe and the Linux `i915` report from the same physical
laptop identify the same device, the same stepping and the same firmware family. That agreement is what
makes the retargeting plan viable, and it is the reference point every kernel experiment is measured
against.

> **Note on neighbouring hardware.** The sibling `NullMoth-Xe` work targets **Panther Lake / Xe3
> (`8086:b080`)** as an SR-IOV virtual function on a QEMU host. Meteor Lake is **Xe-LPG**, a different
> generation with different memory and firmware behaviour (`has_flat_ccs=no` here, flat-CCS remedies
> there). Xe2/Xe3 flat-CCS and VF power/firmware workarounds must **not** be copied onto this device.

---

<a name="compatibility"></a>
## 🖥️ Compatibility

Only one configuration has evidence behind it. Everything else is honestly marked untested.

| Target | Status |
|---|---|
| Dell Latitude 5350, `8086:7D45`, macOS 15.8.1 (24H32), x86_64 | **Tested** — Metal + Vulkan pass; desktop composition in progress |
| Other Meteor Lake SKUs that expose `8086:7D45` | **Untested** — same device ID, likely the same path, no claim made |
| Meteor Lake SKUs with a different device ID | **Untested** — `IOPCIPrimaryMatch` must be changed; nothing else is verified |
| Alder Lake / Raptor Lake iGPUs | **Not targeted** — the i915 code may apply, but no evidence exists |
| Lunar Lake (Xe2) / Panther Lake (Xe3) | **Not supported** by this port — different generation and cache behaviour |
| macOS 15.0–15.7 | **Untested** — only 15.8.1 has hardware evidence |
| macOS 26 Tahoe | **Untested** |
| Apple Silicon | **Not applicable** |

Changing the device ID alone is not a port. Each new target needs its own firmware match, memory/cache
assumptions and a fresh 22-case gate before any claim is made. "Unknown" is not "works".

---

<a name="architecture"></a>
## 🧭 Architecture

```
Metal app
   │
   ▼
NVMTLDriver.bundle          ← out-of-tree Metal driver plugin (NSBundle-loaded user client)
   │  • NVMTLDevice / NVMTLAccelerator  (IOKit-facing provider subclasses)
   │  • NVMTLObjects.m                   (resource, texture, sampler, surface lifetime)
   │
   ▼
libnvmtl_translate.dylib    ← Apple AIR → SPIR-V shader translator
   │  (based on metal2vulkan; LGPL-3.0 / GPL-3.0)
   │
   ▼
ANV (Mesa Vulkan)           ← Intel Vulkan backend, built from Mesa 26.3.0-devel
   │  patched for the i915-on-xnu path
   │
   ▼
libdrm + xf86drm.c          ← userspace DRM abstraction, rebuilt as a pure IOKit render-node model
   │
   ▼
NMXAccel.kext               ← DRM user-client transport / accelerator (com.nullmoth.NMXAccel)
   │
   ▼
NMXGPU.kext                ← 438 i915 + DRM/TTM + LinuxKPI + compatibility + IOKit sources
   │  (com.nullmoth.NMXGPU, personality NMXGPUIntel)
   │
   ▼
Xe-LPG hardware  (GuC-managed engine, GGTT, DMC/HuC/GSC firmware)
```

Two paths are exercised and both matter:

* **Direct** — through the DRM device-file interface.
* **IOKit** — forced through the IOKit render-node transport.

The gate runs **11 cases on each route**. A call named `drmNmxIoctl` does not prove IOKit was used, so
each case logs and verifies the route it actually took rather than trusting the entry point.

---

<a name="components"></a>
## 🧱 Component inventory

| Component | Version / base | Source in tree | Licence |
|---|---|---|---|
| `NMXGPU.kext` | kernel **1.0.13** (parked — boot panic) on the 1.0.12/1.0.11 correction lineage | `latitude-desktop`, `drm-kmod`, `freebsd-src` | i915/Linux → GPL-2.0; NullMoth wrapper PolyForm NC |
| `NMXAccel.kext` | 0.1 | `accel-build/NMXAccel.kext` | NullMoth PolyForm NC |
| `LatitudeMTLFB.kext` | **0.2.4** candidate (raw host-physical allocation) | `desktop-build/LatitudeMTLFB.kext` | project |
| `NMXAGDC.kext` | 0.1 (`NMXAGDCLoader`) | `desktop-build/NMXAGDC.kext` | project |
| Metal plugin | `NVMTLDriver` 0.3.5 candidate | `NullMoth/plugin/` | PolyForm NC |
| Shader translator | AIR → SPIR-V | `NullMoth/translator/` | LGPL-3.0 / GPL-3.0 |
| Vulkan backend | ANV on Mesa **26.3.0-devel** | `mesa/` (patched via `port-artifacts/mesa-i915-darwin-mmap.patch`) | MIT |
| DRM userspace | libdrm 2.4.x | `libdrm/` | MIT |
| DRM kernel modules | linuxkpi port of Linux DRM | `drm-kmod/` | MIT / GPL-2.0 |
| LinuxKPI | FreeBSD compatibility layer on xnu | `freebsd-src/`, `latitude-desktop` | BSD-2-Clause |
| Firmware | GuC/DMC/HuC/GSC | `firmware/i915/` | see `firmware/LICENSE.i915` |
| Kernel build headers | MacKernelSDK | `MacKernelSDK/` | Apple |
| Security bypass | AMFIPass 1.4.1 | `AMFIPass/` | not included in this tree — verify upstream |
| Topology/inject kexts | Lilu, VirtualSMC, … | OpenCore `Kexts/` | mixed |

Exact revisions for every patched base are recorded in `latitude-runtime/BUILD-MANIFEST.json`, and
upstream package hashes are in `SHA256SUMS-upstream.txt`.

---

<a name="implementation"></a>
## 🔬 Implementation detail, layer by layer

### 1. Kernel bring-up: i915 on LinuxKPI

`NMXGPU` is not a from-scratch driver. It is the Linux `i915` driver compiled against a LinuxKPI
compatibility layer on xnu, restricted to `8086:7D45`. The laptop build compiles **438 i915, DRM/TTM,
LinuxKPI, compatibility and IOKit source files**; AMD and Xe drivers are deliberately **not** linked in,
and the AMD-only display-init reference is conditionally excluded. The result links with **no
unresolved driver-internal C symbols**.

The loader is a one-shot opt-in: an NVRAM variable is consumed before GPU initialisation, so a failed
attach cannot silently re-arm on every boot. `NMIntelFB`, `NMXAGDC` and `NMXVGAFB` exist in the tree as
display siblings, but the tested candidate uses the **i915 no-display discovery path** and skips the
DRM-to-`IOFramebuffer` bridge, leaving the panel on its firmware framebuffer while the render runtime is
validated independently. (`LatitudeMTLFB.kext` and `NMXAGDC.kext` are the Latitude-specific builds of
that display path; the panel-claim work is in `latitude-desktop/LatitudePanelClaim.cpp`.)

### 2. Firmware handshake and the GuC

Initialisation writes the GPU's MMIO register blocks during early kernel boot and loads firmware whose
versions match the laptop's own Linux report exactly — **GuC 70.53.0**, **DMC 2.23**, **HuC 8.5.4**,
**GSC 102.1.15.1926**. Kernel capture (`kernel-guc-capture-1.0.9.log`) shows GuC loaded on both GTs with
GuC submission enabled.

Two honest caveats:

* Firmware *load* and GuC *submission enable* are not proof of correct scheduling under load.
* A real GuC defect **has** been observed: at 23:54:50.264 a **GuC TLB-invalidation response timeout**
  for seqno 1 was logged before the next test process started. It is a real event; it is *not* proven to
  be the cause of the following hang.

**A reproduced software race was fixed on this path.** The i915 invalidation waiter sets `WQ_FLAG_WOKEN`
and sleeps; Linux's woken callback also persists `TASK_WAKING`. The FreeBSD LinuxKPI callback marked the
flag and signalled the channel but did **not** persist `TASK_WAKING`, so a reply arriving between the
outer flag check and sleep registration could signal an empty channel and the waiter would sleep to
expiry despite the flag being set. The override in `linux_schedule.c` sets `TASK_WAKING` under the same
sleep-channel lock, following the port's existing `wake_up_task` protocol. The old and patched callbacks
plus the real i915 `must_wait_woken` are extracted into a deterministic fixture: the old version
reproduces the false expiry, the patched one preserves positive remaining time, across **100,000
scenarios** under ASan/UBSan. This is a **verified software fix**; it is not a claim to have fixed the
Dell hang.

### 3. Memory: GGTT, staging and command-pool lifetime

Metal resources reach the GPU through three distinct address spaces, and conflating them is a known
trap:

* **DSM** — device physical addresses.
* **GSM / PTE** — graphics-memory-relative PTE offsets.
* **GGTT** — graphics translation table virtual addresses.

No allocation overlap has been demonstrated in the available capture, and the GT scratch path explicitly
avoids its stolen fallback. On that evidence, GGTT/plane registers are **not** rewritten and no guessed
memory ranges are reserved.

Command-pool lifetime is handled by a **fresh-allocation policy**: pools are created fresh and destroyed
immediately after fence/witness completion, the cache/pop/push reuse paths are removed, and uncertain
completions are **quarantined** rather than reused. The verified gate reports **80,020 created / 80,020
destroyed**, zero live, pending or quarantined, with `created = destroyed = completed + abandoned` for
every case, and peak concurrency of 2 in the independent-worker cases. This is a command-pool object
count for this matrix — **not** a guarantee about every driver memory cache or indefinite runtime.

An important correction to earlier project text: fresh pools alone are **not** a complete stability fix.
The 0.3.0 run that introduced them passed four 1000-frame cases and then hit the GuC TLB timeout and a
hang on the fifth process. Fresh allocation remained correct behaviour; it was never sufficient on its
own.

### 4. The translation stack: AIR → SPIR-V → ANV

Apple hands the plugin **Apple Intermediate Representation (AIR)**. The translator lowers AIR to
**SPIR-V**, which is what the Xe-LPG execution units actually consume, and **ANV** (the Intel Vulkan
driver in Mesa) compiles and submits it. ANV completed **1,045 build steps** for this target; CLC tools
were built separately for the Apple Silicon build host.

`xf86drm.c` in `libdrm` is reworked into a **unified IOKit render-node model**, and the Metal plugin
subclasses `NVMTLDevice` / `NVMTLAccelerator` so the GPU appears as a legitimate node in the I/O
Registry. The surface-publication and desktop-serialization logic that the current failure exercises
lives in `NullMoth/plugin/nvmtl_vk.c` (`nvmtl_vk_image_read` and the surface copy-out path) and
`NullMoth/plugin/NVMTLObjects.m`.

### 5. Security and injection

Under modern macOS security the plugin and kexts must be loaded and trusted explicitly:

* `csr-active-config = Data 430A0000` (`0x0A43`) — the driver's required custom SIP mask.
* `SecureBootModel = Disabled`.
* **AMFIPass 1.4.1** enabled *after* Lilu.
* `amfi_get_out_of_my_way=0x1`, `amfi=0x80`, `ipc_control_port_options=0` per the NullMoth setup.
* GPU-hiding `DeviceProperties` removed; `csr-active-config` and `boot-args` placed in `NVRAM → Delete`
  so prior values are replaced on the next boot.
* No persistent `nmxintel` boot argument — GPU activation is one-shot.

---

<a name="blocker"></a>
## 🐞 The current blocker, stated precisely

This is the most important section in the document. On the physical desktop path, the failure is an
**actual GPU execution/progress failure**, not a missing registration and not merely a shader-compile
error. **Nothing in this document has fixed it.** What changed between candidates is *where* the run
stops, which is why the numbers differ from section to section: each figure below belongs to one specific
boot, and the plugin's submission counter, the readback counter and i915's request sequence are three
different namespaces.

The 0.3.3 boot (`failure-detail-20261019-130037`, boot UUID `43CADE8D-…`, boot start 12:58:39):

```
panel claim activates, framebuffer load = 0, plugin SHA matches installed binary
12:58:49.782–12:58:50.078  eight submissions complete: surface upload, render/event work, three readbacks
12:58:50.085  fourth readback, image2 / staging12, 1920x1080 pitch 7680
              → VK_TIMEOUT at 12:58:55.086, after the 5000 ms WindowServer fence budget
plugin: backend disabled, CPU destination left untouched, uncertain resources retained
12:59:03.799  kernel: hung rcs0 context, active request 8:24 [0x1002] not yet started
12:59:03.867  kernel: GPU HANG 12:1:00dfffff
WindowServer PID163 terminates 12:59:04; restarts hit zero-fill timeouts
CoreDisplay: DisplaySurface::GetMTLTexture → SurfaceColorFill → "Failed to create MTLTexture"
             (BGRA8Unorm 1920x1080, storageModeManaged) → SIGABRT
```

Two earlier boots — 0.2.5 and 0.3.2 (`failure-detail-20261019-121101`, 12:00) — show the same shape at a
different cut-off: readback **#5** accepted by Vulkan, its fence never completing within 5000 ms, and the
concurrent upload **#6** stalling ~80 ms later. That "#5 / #6" ordering is the 0.2.5/0.3.2 signature, not
the 0.3.3 one; the fourth readback above is where 0.3.3 stops.

| Candidate (boot) | Last thing that completed | First thing that stalled |
|---|---|---|
| 0.2.5 | readback #3, render/event #4 | readback **#5**; upload #6 stalls ~80 ms later |
| 0.3.2 (`121101`, 12:00) | readback #3, render/event #4 | readback **#5** |
| 0.3.3 (`130037`, 12:58) | eight submissions incl. three readbacks | **fourth** readback (image2/staging12) |
| 0.3.4 / 0.3.5 | first seven submissions | **submission #8** = third readback, dedicated fresh staging |
| 1.0.10 (diagnostic) | reproduces the 0.3.4/0.3.5 cut-off | same submission #8 / readback #3 |
| 1.0.12 + fb 0.2.4 | readback #8 completed in 2 ms | **submission #9** (render/event) |

What is **established**:

* Readbacks really do complete before the failure — three of them on the 0.3.3 boot — so this is not
  "readback is universally broken".
* The readbacks that succeed and the one that stalls **may reference different images**; the trace does
  not prove they share one. Treating pointer/address equality as reuse-while-pending is not evidence.
* The first fallback upload also completes, so the IOSurface external-host import refusal
  (`VkResult -1000072003`) cannot by itself explain the second stall.
* A not-started request may simply be blocked behind earlier work; it is not proof that its own copy
  instruction is defective.
* The later CoreDisplay/CoreAnimation exceptions are **consequences**, not the initial cause. Reporting
  shader compilation success, manufacturing textures after failure, or extending the fence timeout
  would mask the sequence rather than restore GPU execution.

What is **not** established: an exact single root cause. Candidate 0.3.4 removes one variable — dedicated
fresh staging for this `8086:7d45` WindowServer instead of thread-local retained staging — and fixes
three diagnostic defects (sandboxed journal writes, a per-format log throttle hiding submissions past
#8, and a `sample` invocation that returned success while producing no stack). It does not claim to fix
the hang.

### What the kernel 1.0.10 ring capture actually recorded

Kernel 1.0.10 changes **diagnostics only**. Before the logical-ring tail is published it copies the
request's own ring words plus the **four words below the head** into write-once boot slots, and on hang
it re-reads the live pinned CPU ring. On the 17:14 boot it recorded this for render context 8 (ring GGTT
base `a9d000`, size `0x4000`):

| Request | head | infix | postfix | tail | WA tail | four words below the head, at submission |
|---|---|---|---|---|---|---|
| 16 | `9d8` | `a78` | `aa8` | `b38` | `b40` | `0x9c8–0x9d4`: `ff000000 ×4` (request 14's ending) |
| 18 | `b40` | `be0` | `c10` | `ca0` | `ca8` | `0xb30–0xb3c`: `fedca540 / 0 / 02800000 / 0` (request 16's ending) |
| 20 | `ca8` | `d48` | `d78` | `e08` | `e10` | `0xc98–0xca4`: `ff000000 ×4` (request 18's ending) |

The window is `[head − 16, wa_tail + 8)`, so it also contains the request's *own* ending. That is what makes
the comparison decisive:

* At request 18's submission, `0xc98–0xca4` hold `fedca540 / 0 / 02800000 / 0` — request 18's own
  switch-out `MI_STORE_DATA_IMM` and its `MI_ARB_CHECK` / `MI_NOOP` workaround tail.
* At request 20's submission, the four words below its head are those same `0xc98–0xca4` offsets — now
  `ff000000 ×4`.
* At request 16's submission, the four words below its head (`0x9c8–0x9d4`, request 14's ending) already
  read `ff000000`; at request 18's submission, request 16's ending (`0xb30–0xb3c`) was still intact. The
  overwrite is therefore not uniformly applied to every retired request.
* The **hang** snapshot, taken from the same pinned CPU mapping in the same millisecond, reads all zeros
  — that capture follows the userspace crash and is *not* treated as the first corruption event.

The GuC register capture independently shows the GPU fetching that word: `IPEHR=ff000000`,
`INSTDONE=ffdfffff`, `RING_HEAD=ACTHD=0xca4` (the word after request 18's `MI_ARB_CHECK`), while
`RING_TAIL=0xe08` (request 20 already published).

**What this establishes:** real ring content changed at a request boundary and the GPU fetched it, seen by
both the CPU mapping and the instruction-pointer register. It is not a fence-budget or scheduling artefact.
**What it does not establish:** which code wrote those words, or how far back the change reaches — the
window starts at `head − 16`, so it cannot bound the overwrite. `0xff000000` is *consistent with* opaque
black, but that proves nothing on its own; a search of the port, plugin and accelerator sources finds no
`0xff000000` constant (only unrelated PCI class masks), so it is not a marker this project writes
deliberately.

The same signature, byte for byte, was then recorded on a **second, independent build** (kernel 1.0.11,
17:32 boot): context 8 request 18's ending intact at capture, request 20's ending `ff000000`, `IPEHR`
`ff000000` again — and, later in the same boot, context 12's `0x9c8–0x9d4` (request 14's ending) and
`0xb30–0xb3c` (request 16's ending) also read `ff000000`. In other words the overwrite is reproducible,
is not a one-off scribble, and it *spreads* over the boot.

**Candidate writers, none yet proven.** (1) An external write aliasing the ring's physical pages — a stale
user mapping or a surface fill. (2) The ring emitter writing the wrong offset. (3) Cache/coherency
(weakened: the CPU snapshot and the GPU `IPEHR` agree, so both saw the same memory). (4) The
`RING_HEAD=ACTHD=0xca4` value itself being the anomaly, with head and tail both sitting mid-request. The
raw-physical export correction below gives candidate (1) its first concrete mechanism — a fill over a
flat range that may not match the allocation — while leaving it conditional on a system mapper. That
candidate was then booted (18:00) and the overwrite still occurred, with no span-refusal line in the log;
so the mechanism is **unproven and weakened**, and candidate (1) still has no demonstrated writer.

**The cheap decisive tests** are a **ring guard** (store the previous request's tail and WA-tail dwords at
each tail publication and diff them at hang, turning "the words changed" into "these bytes changed between
*these* two events") and a **physical-page ownership map** — the page numbers behind the ring, the
IOSurface/private-image/staging buffers, and the earliest submission boundary whose words differ. Neither
the pixel-looking constant nor a later crash stack names the writer.

### The 1.0.12 raw-physical allocator correction

The ring capture narrowed *where* the corruption lands. A second, independent audit asked a different
question: **which code can write a flat physical range at all?** The answer includes every buffer the port
exports to another agent as "one contiguous run of physical memory", because the exporter never checked
that the run was real.

Apple's `IOBufferMemoryDescriptor::initWithPhysicalMask` (xnu-11417.140.69) decides host contiguity like
this:

```c
mapped = (NULL != IOMapper::gSystem);          // only if kIOMemoryMapperNone is absent
contig = (0 != (options & kIOMemoryHostPhysicallyContiguous));
if (!contig && (0 != (options & kIOMemoryPhysicallyContiguous))) {
        contig |= (!mapped);
        contig |= (0 != (kIOMemoryMapperNone & options));
}
```

So `kIOMemoryPhysicallyContiguous` by itself requests **host**-page contiguity only when no system mapper
exists (or when `kIOMemoryMapperNone` is also set). With an IOMMU, the allocation can be contiguous in the
mapper's address space while the host pages are scattered.

The port's surface allocator, `nmxVramAlloc()`, requested `kIODirectionInOut |
kIOMemoryPhysicallyContiguous` and then exported the surface with
`getPhysicalSegment(0, nullptr, kIOMemoryMapperNone)` — taking the **first segment's base** and ignoring the
segment length it had just been handed. `NMXAccel` converts that base plus the surface size into an
`IODeviceMemory` physical range. If the pages were scattered, the exported range extends into physical
memory the allocation does not own, and any fill of "the surface" writes there. That is the first
candidate mechanism in this investigation that can produce **pixel-valued writes outside the buffer**
rather than an instruction-emitter bug.

Kernel **1.0.12** and framebuffer **0.2.4** correct the assumption:

* `nmxVramAlloc()` and `nmx_xnu_mem_alloc()` add `kIOMemoryHostPhysicallyContiguous | kIOMemoryMapperNone`.
* They reject the export unless the first segment covers the whole request (segment length, descriptor
  length, CPU pointer and address overflow); the kernel allocator also enforces the physical mask and
  requested alignment.
* A rejected allocation releases its slot and budget, and `nmxVramFree()` uses the same slot-release path,
  so the slot bitmap and retain count stay balanced.
* The installer stages, validates, backs up and rolls back the framebuffer together with the kernel and the
  AuxKC, so a failed desktop boot cannot leave a new framebuffer paired with an old kernel.

The host regression uses Apple's actual contiguity decision (copied from the Sequoia source, not
reimplemented) plus the real old and new allocator functions, under ASan/UBSan: the deliberately
fragmented allocator makes the old code export a 4 KiB segment for an 8 KiB request and the new code
reject it; 2,000 allocate/free cycles leave no live descriptor and no leaked budget.

**What this does not establish.** Two things weaken it as *the* cause on this laptop:

1. **The precondition is not evidenced.** The 17:32 boot log records `AppleVTD is not yet installed as
   gSystem`, with no later installation line, and the i915 first-error capture reports `iommu=0`. If
   `IOMapper::gSystem` is `NULL`, Apple's own `contig |= !mapped` makes even the *old* flag request
   host-contiguous pages. The candidate's research note concedes that the target's mapper state is not
   proven; it should stay a conditional, not a conclusion.
2. **The fix does not cover the two virtio scan-out buffers.** `fScanBuf` (`nmxvgafb.cpp:909`) and
   `fCursorBuf` (`nmxvgafb.cpp:1202`) still allocate with only `kIODirectionInOut |
   kIOMemoryPhysicallyContiguous` and still publish `getPhysicalSegment(0, nullptr, kIOMemoryMapperNone)`
   with no span check. On the Latitude build the virtio path is compiled out — `start()` sets the
   `-nmxvgafbnovirtio` flag unconditionally under `LATITUDE_MTL_PANEL` — so these two buffers are **never
   allocated on the Dell**. That makes them a correctness item for the QEMU/virtio configuration, not a
   candidate writer on this laptop.

Kernel 1.0.12 is UUID `000EF47E-E9CC-3CFB-A130-4AEBD40B46C5`, signed-binary SHA-256
`1ad3f4dc…`; framebuffer 0.2.4 is UUID `59DA4CD2-AF66-36A4-A364-A6A8E899666A`, SHA-256 `495ed4cc…`.

**It was booted, and it did not fix the hang** (`windowserver-1.0.12-failure-180032`, 18:00:32, installed
payload hashes matching the candidate):

* The desktop reached **submission #8 / readback #3** for image 2 with fresh owned staging 13; the readback
  completed after 2 ms and released its staging after the copy.
* **Submission #9** (render/event, `nvmtlAdvancePart`) queued at 17:58:47.585 and timed out at
  17:58:52.585 after 5000 ms.
* The ring capture still shows corruption: saved request 20 already has `0xff000000` at `0xc98–0xca4` (yet
  request 20 completed), and request 22 has `0xff000000` at `0xe00–0xe0c`, immediately before its normal
  start at `0xe10`. The hang snapshot holds `0xff000000` in all 94 captured words; GuC `IPEHR=0xff000000`,
  `RING_HEAD=ACTHD=0xe0c`, `RING_TAIL=0xf70`, `GPU HANG 12:1:00dfffff`.
* **No `refusing noncontiguous` line appears anywhere in the retained log.** The new guard therefore has no
  runtime evidence of having executed, and the capture cannot say whether the guarded branch was taken,
  skipped, or never reached. Raw contiguity is **not** a demonstrated explanation, and the fix is neither
  confirmed nor excluded by this trial.

### The 1.0.13 trial (18:17) — withheld stolen memory, boot panic

Kernel **1.0.13** (UUID `121AACAE-4C53-3357-9356-38C79222A842`, SHA-256 `d57981cb…`) is a different
hypothesis: that i915's MTL **stolen-memory region** overlaps the firmware panel buffer that
`LatitudeMTLFB` still scans out, because the port skips display discovery for `8086:7d45` and therefore
never performs Linux's initial-plane framebuffer handoff. The change makes `intel_memory_regions_hw_probe`
`continue` past `INTEL_MEMORY_STOLEN_LOCAL` and `INTEL_MEMORY_STOLEN_SYSTEM` for `0x7d45` under `NMXKPI`,
so rings and objects allocate from ordinary system memory; a second hunk logs `stolen=`/`size=`/`ggtt=`
at ring pin. The research note states plainly that the overlap for the damaged ring is **not**
established and that the GGTT virtual address `0xa9d000` cannot be read as a physical address.

The installer completed (18:13:00, exit 0), the kernel image loaded, and the boot **panicked after
8.04 seconds** — before any desktop, and before the ring capture could record anything:

```
panic(cpu 0): NullMoth xkpi: mutex 0xffffff95128a9088 (?) used before mtx_init
  _nmx_mtx_lock.cold.1 ← _nmx_mtx_lock ← _guc_retire_inflight_request_prio
  ← _signal_irq_work ← _linux_irq_work_fn ← _taskqueue_run_locked
kext in backtrace: com.nullmoth.NMXGPU(1.0.13)[121AACAE-…]
```

From source, the faulting lock is `ce->guc_state.lock` inside `guc_retire_inflight_request_prio()`
(`intel_guc_submission.c:4364`), where `ce = intel_context_to_parent(rq->context)`. That lock is
initialised only in `intel_context_init()` (`intel_context.c:415`). The port's `nmx_mtx_lock()` panics when
the embedded `mtx_lk` is `NULL`, and the printed lock name is `?` — so the object behind `ce` is a
**zeroed, never-initialised context** (or recycled and zeroed memory), not a contended lock.

**What is and is not attributed.** The backtrace proves the 1.0.13 image ran. It does **not** show that the
region-skip branch ran: the retained unified log contains no `i915` line and neither `stolen region
withheld` nor `ring pinned`, so the `drm_info` output is simply not in the capture. No mechanism from
"no stolen region" to "zeroed context mutex" is demonstrated by the two diffs, and nothing excludes one
either. None of the retained kernel panic reports (17–19 October) carries this signature, so it is new to
this boot. The stolen/DSM overlap hypothesis is therefore **untested**, not disproved. **The panic's cause
is unattributed; 1.0.13 is parked, not promoted.** The detailed record is
`research/windowserver-1.0.13-panic-181731.md`.

The last booted payload whose behaviour is characterised therefore remains **1.0.12 + framebuffer 0.2.4**:
ring corrupted, readback timed out. That is the state this document reports.

### What has been eliminated by controlled experiment

| Hypothesis | How it was excluded |
|---|---|
| Kext not injecting | Injection is `- Success`; `NMXGPU` UUID matches the candidate on target |
| Missing GPU opt-in | Opted-in boot evidence above shows the panel claim and framebuffer load succeeding |
| Universal readback defect | Readback #3 completes cleanly on the same boot |
| `INTEL_DEBUG=stall` would cure it | It was enabled on the failing 0.2.5 boot and did not cure the hang — a recorded **negative** result |
| Timeout budget too short | The hang is a progress failure; lengthening the fence would not restore execution |
| Firmware version mismatch | macOS loads `mtl_guc_70.bin` 70.53.0, matching the Linux report on both GTs |
| Xe2/Xe3 workarounds | Different generation and different cache behaviour; explicitly not applicable |
| Missing page pin on i915 CPU user mappings | Kernel 1.0.11 added the mapping-lifetime pin and the **identical** ring overwrite plus `IPEHR=ff000000` recurred on the 17:32 boot — reclamation stays as an independent correctness fix, not the cause |
| Hardware compression (`noccs`) | Compression-off was confirmed applied before ICD load and submission #8 / readback #3 still stalled |

---

<a name="failures"></a>
## 🧨 Failure signature reference

When this port fails, it fails with a small set of recognisable log lines. This table maps each one to
what it actually means and what to do next — so the next person does not have to rediscover the sequence.

| Log signature | Meaning | Next action |
|---|---|---|
| `Prelinked injection … - Success` is **absent**; `EFI_INVALID_PARAMETER` | The kext has no `_kmod_info`; OpenCore silently skipped it | Rebuild with `KMOD_EXPLICIT_DECL`; run the `check-kmod-info` guard |
| `EB.LD.OFS\|OPEN! Err(0xE) <usr\standalone\OS.dmg.root_hash>` → `EXITBS:START` | The boot image lacks the root-hash file — not an EFI fault | Use a full installer image, not a trimmed `BaseSystem.dmg` |
| `GPU HANG 12:1:00dfffff` / `12:1:00b79797` | The GPU stopped progressing; the address identifies the hang, not its cause | Capture request and GuC state; do not raise the fence timeout |
| `VK_TIMEOUT` after 5000 ms | A fence never completed | Find the first *uncompleted* submission, not the first timeout |
| `VkResult -1000072003` | `VK_ERROR_INVALID_EXTERNAL_HANDLE` — IOSurface import was refused | Check whether the private-image fallback also completes |
| `pipeline: Vulkan is not up in this process` | WindowServer aborted after the backend shut down | Treat as aftermath; look earlier in the log |
| `GPUWranglerWaitForPublish` | No GPU was ever published | Check `kextstat`, then the AuxKC bundle paths |
| `GuC TLB invalidation response timeout` | The waiter did not observe the response | Check the LinuxKPI woken path; see the lost-wake fix |
| `EXC_BAD_ACCESS` in the stack guard, hundreds of `RenderEncoder` frames | Recursive SkyLight rendering after command-buffer failure | Bound the error path; do not recurse |
| `Failed to create MTLTexture` (BGRA8Unorm 1920×1080, managed) | CoreDisplay allocation after GPU loss | Restore GPU execution; do not fabricate textures |
| `NMX-i915-ring-word … value=ff000000` / `IPEHR=ff000000` | Words below a request head changed to `0xff000000` and the GPU fetched them as an instruction | Run the ring-guard diff and the physical-page ownership map; do not assume a pixel write |
| `RING_HEAD`/`ACTHD` mid-request (`0xca4`) while `RING_TAIL` is already ahead (`0xe08`) | The GPU's read pointer stopped *inside* a request after the CPU had published the next one | Read the saved ring window, not just the register values |
| `NullMoth xkpi: mutex 0x… (?) used before mtx_init`, from `_nmx_mtx_lock` under `_signal_irq_work`/`_taskqueue_run_locked` | A `struct mtx` whose `mtx_lk` is `NULL` and whose name is `?` — an object that never passed through `mtx_init()` (kernel 1.0.13: `ce->guc_state.lock` in `guc_retire_inflight_request_prio`) | Park the build; identify the object and the missing initialisation. This is not contention and not a timeout |
| `refusing noncontiguous` **absent** from a log of a guarded build | The span guard left no runtime evidence that it executed | Do not treat the trial as a test of the guard; verify the branch's log path is captured first |

**Reading rules.** The first error in the log is usually the cause; later ones are usually consequences.
A timeout is a symptom of missing progress, not proof of a defective submission. A zeroed register dump
is not evidence of an idle GPU unless the capture path was verified to print it.

---

<a name="history"></a>
## 🧗 How we got here — the struggles and the breakthroughs

None of the above arrived in a straight line. Four separate things had to be fixed before a single
pixel could be validated, and three of them failed silently — which is why they cost the most time.
This section records the dead ends as carefully as the wins, because the dead ends are what constrain
the next experiment.

### Timeline of the hard parts

| Date | Struggle | What actually fixed it |
|---|---|---|
| 8 Oct | Kext would not inject into the prelinked kernel; OpenCore reported nothing useful | Supplying a real `_kmod_info` via `KMOD_EXPLICIT_DECL` |
| 8 Oct | macOS froze at `EXITBS:START` on every EFI change | The recovery image was missing `OS.dmg.root_hash`; not an EFI fault |
| 8 Oct | WhateverGreen assumed to be the Alder/Meteor Lake answer | It does not support either family; abandoned |
| 18 Oct | `MyIntelGPU` kext failed authentication on the target | Rebuilt as an i915-derived `NMXGPU` under a custom SIP mask |
| 18 Oct | First desktop attempts died after 4 submissions | Readback fence timeout identified as the first failure |
| 18 Oct | GuC TLB timeout, then hang on the fifth process | Lost-wake race in LinuxKPI reproduced and fixed (software only) |
| 18 Oct | Fresh pools did not stop the hang | Accepted as a lesson: fresh allocation was necessary, not sufficient |
| 19 Oct | A/B tests were measuring nothing | Release constructor was stripping every `NVMTL_*` variable |
| 19 Oct | WindowServer stack exhaustion after backend loss | Terminal-error buffers bounded the recursion |
| 19 Oct | A black-screen boot left no evidence at all | Bounded the desktop mutex and added a pre-created journal |
| 19 Oct | Journal writes silently denied | Moved stage records to the existing syslog channel |
| 19 Oct | Submissions past #8 invisible in logs | Per-format throttle bypassed for startup submissions |
| 19 Oct | Crash sampler "succeeded" with no stack | Fixed PID resolution; missing output now fails loudly |
| 19 Oct | Kernel capture showed zeros for ring state | GuC's parsed register lists were never being printed |
| 19 Oct | Driver installed but never loaded | AuxKC referenced a deleted temporary bundle; installer rebuilt from permanent paths |

---

### Phase 0 — "Why will this kext not inject?" (8 October)

The first blocker looked like a driver bug. It was a metadata bug.

OpenCore was silently discarding the kext. The chain was:

```
KextFindKmodAddress      → Kmod = 0
InternalPrelinkKext      → EFI_UNSUPPORTED          (Link.c:1629)
PrelinkedInjectKext      → EFI_INVALID_PARAMETER    (reported quietly)
```

The binary had **no `_kmod_info` symbol**, so OpenCore had nothing to link the kext against.

What we eliminated, and why it mattered:

* **Xcode 15.4's SDK contains no `kmod_info*` and no `CreateKModInfo*`.** CI diagnostics
  (`37789629143`, `37789952837`) confirmed this across the SDK.
* **MacKernelSDK does not define `_kmod_info` either.** Pinned and inspected at
  `3f750085caa17ec3a7880f11c11bf4f48cd6a164`; no archive exports it. It was therefore *not* vendored.
* **Eight different link-flag arrangements all failed.** The symbol was simply absent.
* **A dummy `_kmod_info` was rejected on principle.** Satisfying a guard with a fake structure would
  have produced a kext that linked and then misbehaved.

The breakthrough was reading `libkern/kmod/README` instead of guessing: the object emitted by XNU's
`CreateKModInfo.perl` must be compiled and placed **between `-lkmodc++` and `-lkmod`**. That became
`kmod_info.c` using `KMOD_EXPLICIT_DECL`, with a `check-kmod-info` build guard
(`OK (_kmod_info present)`) so the failure could never silently return.

Result, for the first time:

```
OC: Prelinked injection CoreUltraGraphics.kext (…) - Success
OCAK: Local relocs 313
```

**Lesson:** a build that produces a `.kext` is not a build that can be injected. The guard now fails
the build, not the boot.

### Phase 0b — "Why does macOS freeze at EXITBS:START?" (8 October)

With injection fixed, boot still stopped dead:

```
AAPL: #[EB.LD.OFS|OPEN!] Err(0xE) <"usr\standalone\OS.dmg.root_hash">
AAPL: #[EB.RH.LRH|P!] Err(0xE) <- EB.LD.LF
AAPL: #[EB.BST.FBS|!] Err(0xE) <- EB.RH.LRH
AAPL: #[EB|LOG:EXITBS:START]
```

`Err(0xE)` is `STATUS_NOT_FOUND`. Apple's `boot.efi` wanted a root-hash file that was **not inside the
recovery image at all** — confirmed by listing `BaseSystem.dmg` directly: zero matches for `root_hash`.

Three controlled experiments proved this was not our configuration:

* **ACPI** — bisected from 8 SSDTs to 2, both rename patches off, kext off. Byte-identical failure.
* **SIP** — set `csr-active-config = 0x7F000000`; the log confirms `EB.CSR.S 0x7F` and
  `EB|CSR:OUT 0x6F`. Identical failure.
* **Quirks** — verified against the MATs guidance (`OCABC: MAT support is 1`) and against a known-good
  Latitude 7400 EFI. Ours already matched.

The image was the problem, not the EFI. `DmgLoading = Any` would not help either: that setting *relaxes*
verification, and the file genuinely did not exist. No config change can conjure it.

**Lesson:** "invariant across every config change" is evidence about the *image*, not the config.
Chasing `SetupVirtualMap`, `DevirtualiseMmio` and `DmgLoading` was time spent on the wrong layer.

### Phase 1 — The pivot to NullMoth (18 October)

WhateverGreen was the obvious candidate and was ruled out from its own documentation: the last
documented Intel family is Ice Lake, and it supports neither Alder Lake nor Meteor Lake
([FAQ.IntelHD.en.md](https://github.com/acidanthera/WhateverGreen/blob/master/Manual/FAQ.IntelHD.en.md),
[README](https://github.com/acidanthera/WhateverGreen/blob/master/README.md)).

Rather than write a graphics driver from scratch, the project retargeted **NullMoth's NVIDIA driver**,
keeping its Metal plugin, shader translator and userspace architecture and replacing every NVIDIA
element with an Intel one. That decision is why the project reached real GPU submissions at all.

The first target attempt, `MyIntelGPU`, failed **authentication** on the laptop — a signature problem,
not a Meteor Lake problem. Rebuilding as an i915-derived kext under a custom SIP mask turned that into
an attach.

### Phase 2 — Assembling a stack that had never run (18 October)

This phase was mostly unglamorous construction, and every number here was hard-won:

* **438** i915, DRM/TTM, LinuxKPI, compatibility and IOKit sources compiled into `NMXGPU`, with AMD and
  Xe drivers deliberately excluded and **no unresolved driver-internal symbols**.
* **1,045** ANV build steps for the Intel Vulkan backend, plus CLC tools built separately for the Apple
  Silicon host.
* Firmware matched to the laptop's own Linux report rather than guessed: GuC **70.53.0**, DMC **2.23**,
  HuC **8.5.4**, GSC **102.1.15.1926**.
* A one-shot NVRAM opt-in so a failed attach cannot silently re-arm on every boot.

The PCI probe then succeeded on the real `8086:7D45`, and `NMXAccel` began declining startup unless
`NMXGPU` had actually claimed the device — a guard that later proved its worth.

### Phase 3 — First submissions, first hang (18 October, 19:12–19:49)

Registration worked. Composition did not.

**0.2.4** reached the panel and copied an IOSurface into it — but all 64 diagnostic samples were zero,
and host allocation imports returned `-1000072003` (`VK_ERROR_INVALID_EXTERNAL_HANDLE`), falling back to
private images. Fence waits then returned `VK_TIMEOUT` after 5000 ms. WindowServer died with
`EXC_BAD_ACCESS / KERN_PROTECTION_FAILURE` **inside the main thread's stack guard**, after 512 frames
containing 255 `RenderEncoder` and 254 `SetScissor` calls. That was **stack exhaustion through
recursive SkyLight rendering after command-buffer failure**, not a standalone logging bug. GPU HANG
`12:1:00dfffff` followed at 19:13:06.637.

**0.2.5** narrowed it. The first four submissions returned `VK_SUCCESS`; **submission #5**
(`nvmtl_vk_image_read`) and the concurrent upload **#6** both timed out. `INTEL_DEBUG=stall` was
confirmed *enabled* on the failing boot — so it is a recorded **negative result**, not a missed setting.
Terminal-error command buffers bounded the recursion (retries spaced ~16 ms instead of tens of
thousands of calls), but WindowServer still aborted with `pipeline: Vulkan is not up in this process`.

The kernel's captured `reset_count=0`, `EIR/PGTBL_ER/fault_data=0` and zeroed ring fields looked
reassuring. They were not evidence of anything: the capture was incomplete.

**Lesson:** "the first four submissions succeed" is not progress if the fifth is where it dies. The
first *uncompleted* submission is the measurement.

### Phase 4 — The GuC lost-wake race (18 October, 23:54)

**0.3.0** introduced fresh command pools. It passed four 1000-frame cases cleanly, then:

```
23:54:50.264  GuC TLB invalidation response timeout, seqno 1
              (after the padded process finished, before the next connected)
fifth case     hang on upload submission #1285, zero-based frame 428
              fence returned -4 after 10,798 ms
kernel         rcs0 request 12:2574 not yet started, GPU HANG 12:1:00b79797
pools          1286 created / 1285 destroyed / 1 quarantined
```

The hang was real, and fresh pools were **not** the fix. But the TLB timeout pointed at the waiter, and
that produced the most valuable software find of the project.

Linux's i915 invalidation waiter sets `WQ_FLAG_WOKEN` and sleeps. Linux's woken callback *also*
persists `TASK_WAKING`. The FreeBSD LinuxKPI callback in this port marked the flag and signalled the
channel but **did not persist `TASK_WAKING`**. `schedule_timeout` checks `TASK_WAKING` under that
channel lock before registering sleep — so a reply arriving between the outer flag check and
registration could signal an **empty channel**, leaving the waiter to sleep to expiry with the flag
already set.

The fix sets `TASK_WAKING` under the same lock, following the port's existing `wake_up_task` protocol.
The real old and patched callbacks, the real `schedule_timeout` and the real i915 `must_wait_woken` were
extracted into a deterministic fixture: the old version **reproduces the false expiry**, the patched one
preserves positive remaining time, across **100,000 scenarios** under ASan/UBSan.

It is a verified software fix. It is **not** a claim to have cured the Dell hang, and the report says so.

### Phase 5 — The gate that finally meant something (19 October)

Two more failures had to be fixed before a pass was trustworthy:

**The tests were measuring nothing (0.2.8).** `nvmtl_conf_knobs()`'s release constructor stripped
**every** `NVMTL_*` environment variable before backend initialisation. Fresh-pool, diagnostics,
readback-trace and staging settings were all inert. The shell's record of requested settings was not
evidence of *effective* settings, and every earlier release-environment A/B conclusion had to be
withdrawn. **0.2.9** preserved six exact controls only for the named test process and added an
in-driver **effective-policy query**; the workload now refuses to start on any mismatch.

**The collectors were selecting the wrong evidence (0.3.0).** One report required `results.txt`, so an
early preflight exit silently selected an older report whose frame-101 device loss belonged to a
different candidate. Another had hard-coded timestamps and attributed an unrelated historical hang.
Selection was rewritten to take the newest report even without results, record the boot time, and
preserve preflight metadata.

Only then did the gate mean what it claimed:

```
22 cases           11 IOKit + 11 direct
26,000 frames      1000 iterations per case
80,020 pools       created = destroyed = completed + abandoned
0                  live / pending / quarantined
```

That is the baseline that still stands, and it is why "Metal and Vulkan work" is a measured statement
rather than an inference.

### Phase 6 — WindowServer, one variable at a time (19 October, 12:00–13:37)

Every desktop candidate failed, and each failure narrowed the search:

| Candidate | Struggle | What it proved |
|---|---|---|
| 0.3.2 | Black screen, **no retained evidence** — only a live-log header and an empty registry | An unbounded `pthread_mutex_lock` preceded the GPU wait budget |
| 0.3.3 | 8 submissions, 3 readbacks, then readback #4 timed out; GPU HANG `12:1:00dfffff` | Bounded `trylock` + deadline; the hang is not host-lock contention |
| 0.3.4 | First 7 submissions, then **submission #8** (third readback) timed out with dedicated fresh staging | Staging reuse is **not required** to trigger the hang |
| 0.3.5 | Driver installed but never loaded | AuxKC referenced a deleted temporary bundle |

Three diagnostic defects had to be repaired before the failures could even be read:

* **Sandboxed journal writes were denied** (`errno 1`) even with correct ownership. Stage records moved
  to the existing syslog channel; no sandbox or SIP change was needed.
* **A per-format eight-message throttle hid submissions past #8**, despite the caller's finite budget.
  Startup submissions now bypass it.
* **`sample` returned 0 while reporting `pid_for_task` failure and process 0**, producing no stack. The
  loader now resolves an explicit positive PID, refuses 0/1, and records missing output as a failure.

And the kernel capture itself was lying by omission:

```
intel_engine_coredump_alloc  → legacy register capture only when GUC_CAPTURE is absent
GuC captures                 → attach a parsed register-list node instead
previous summary             → printed legacy engine->head/tail/start/acthd, all zeros
```

Those zeros did **not** prove an idle ring, physical address 0, or the absence of a fault. Kernel 1.0.9
records the owned request's fence context/sequence/flags/error, readiness and completion states,
pending dependencies, GuC ID and scheduling snapshot, LRC address, and ring/batch GPU virtual
addresses, plus a bounded parsed-GuC printer (3 lists, 64 registers per list/engine). It changes
**diagnostics only** — not scheduling, reset policy or timeouts.

The 13:36 boot added one more lesson, and it was self-inflicted: the installer built a preflight AuxKC
from a temporary source path, installed that collection, then deleted the source. The kernel manager
then reported a missing bundle at `.latitude-windowserver.xux6gR/NMXGPU.kext`, `NMXGPU` never loaded,
and WindowServer waited in `GPUWranglerWaitForPublish` for a GPU that was never published. Local mocked
cache tests had checked file contents and rollback but **not recorded source paths**. The installer now
builds the final AuxKC from the permanent installed path, inspects prelink metadata for that path,
refuses the temporary one, and verifies the candidate UUID.

**Lesson:** an installer that can produce a silent "driver installed but not loaded" state is worse than
one that fails loudly. Rollback tests must assert *where* files came from, not just that they exist.

### Phase 7 — A ring capture, a real source defect, and its falsification (19 October, 17:00–17:38)

Kernel 1.0.10 was a **diagnostic-only** build: it saves the bounded words around each active
render-ring request at submission and re-reads them at hang. The 17:14 boot with plugin 0.3.5 reproduced
the familiar stall — submission #8 / readback #3 — and the capture finally showed *content*, not just a
pointer: the words below request 20's head had become `0xff000000`, and the GuC `IPEHR` matched.

A source audit then found a **genuine defect**, independent of the hang. The port's mapping-revocation
shim, `lkpi_unmap_mapping_range()`, is deliberately empty, and it is safe only because mappings are
supposed to be pinned for their lifetime. `drm_gem_ttm_mmap()` installs that lifetime pin
(`nmx_ttm_pin`), but the i915 `vm_ops_cpu` path (`WB`/`WC`/`UC`) never did. On Linux, `put_pages`
revokes the user PTE before the backing is freed; the port cannot revoke, so an idle *mapped* object's
pages could be reclaimed and reused underneath a live user mapping.

Kernel 1.0.11 is the fix candidate: pin i915 CPU user mappings for the lifetime of the mapping and
release the pin after the IOKit mapping is gone; refuse the legacy `I915_MMAP_TYPE_GTT` alias the port
cannot revoke; and report `i915_gem_mmap_gtt_version() = 4` under NMXKPI. It links **438 objects** with
the same undefined-import set as 1.0.8, kernel UUID `B972B890-9276-3E0D-B260-190037118D3E`, signed-binary
SHA-256 `496e108b4d94390ac6a7030aba655ff5c0c5c61d827d7d92c65b04315b27943a`, and passes a 20,000-lifetime
ASan/UBSan fixture plus the installer/rollback fixtures.

Then the 17:32 boot with 1.0.11 failed **the same way**. Same submission, same fence timeout, same
`0xff000000` below request 20's head, same `IPEHR=ff000000`. The lifetime-pin omission is a real port bug
and stays in the tree as a correctness fix — but it is **not the writer** of this overwrite.

**Lesson:** a real defect is not the same thing as *the* cause. The pin is well-motivated and provable in
source; the capture proved it was not sufficient. Keep both facts.

### Phase 8 — From "which submission" to "which writer" (19 October, 17:39–17:47)

The 1.0.11 falsification left two threads: prove the overwrite's extent, and name the code that can write a
flat physical range. The second thread produced a source-demonstrated allocator defect rather than another
scheduler theory. Apple's `IOBufferMemoryDescriptor` grants host-page contiguity for
`kIOMemoryPhysicallyContiguous` only when there is no system mapper; the port's surface export assumed it
unconditionally and ignored the segment length returned by `getPhysicalSegment()`. Kernel 1.0.12 and
framebuffer 0.2.4 add `HostPhysicallyContiguous | MapperNone` and refuse a short span.

The honest part is the caveat: the same boot log says `AppleVTD is not yet installed as gSystem`, so on
*this* machine the old flag may already have produced contiguous pages. The correction is still right —
the export should never have trusted a base address without its length — but it is a **candidate**, not a
demonstrated fix. The scan-out and cursor exports (`fScanBuf`, `fCursorBuf`) still use the old pattern, so
the audit is not finished either.

**Lesson:** a mechanism that can explain the value is not the same as evidence that the mechanism ran.
Record the precondition you have not measured next to the fix you have.

### Phase 9 — Two candidates, two negative results, one boot panic (19 October, 17:55–18:18)

The 1.0.12 / framebuffer 0.2.4 pair was installed at 17:55 and booted at 17:58. Readback #8 completed in
2 ms; submission #9 timed out after 5000 ms; the ring still held `0xff000000` at request 22's
`0xe00–0xe0c`, with `IPEHR=0xff000000`. The guard added by the candidate left **no** `refusing
noncontiguous` line in the retained log, so the trial neither confirms nor refutes it. It is a negative
result for "raw contiguity was the cause", not a refutation of the source correction.

The next hypothesis was ownership rather than contiguity: i915 creates an MTL stolen-memory region, the
port skips display discovery for `8086:7d45`, and Linux's initial-plane handoff therefore never reserves
the firmware panel buffer in that region — so a ring could be allocated from memory the panel still scans
out. Kernel 1.0.13 withholds both stolen regions from i915 on this device ID and logs the ring's
`stolen=` state. The installer completed at 18:13; the boot **panicked at 18:17:31**, 8.04 s in, inside
`guc_retire_inflight_request_prio`, locking a zeroed `intel_context.guc_state.lock`. The desktop was never
reached.

The honest reading is narrow: the new failure mode is real and its stack is source-identifiable, but
nothing in the two diffs shows a path from "region withheld" to "context never initialised", and the
capture does not even show that the new log lines executed. **Lesson:** a candidate that fails earlier is
not a stronger explanation; it is a new question. Park it, record it, and do not re-arm it unchanged.

### The failures we still cannot explain, and say so

* The **exact root cause** of the WindowServer hang is not established.
* **Who writes `0xff000000` below a request head is unidentified.** The capture window starts at
  `head − 16`, so it cannot bound how far the change reaches, and `0xff000000` is not a constant this
  port, plugin or accelerator writes anywhere.
* The overwrite is **reproducible across three independent kernel builds** (1.0.10, 1.0.11, 1.0.12) and
  **spreads** over a single boot. That fits a systematic writer better than a random stray store, but
  "systematic" is a description, not a cause, and no writer has been named.
* `Readback #3` succeeds and `#5` fails on the same boot; the trace does **not** prove they share an
  image, so "reuse while pending" remains unproven.
* Whether the raw-physical export defect could have run on **this** machine is unresolved. The 17:32 log
  says `AppleVTD is not yet installed as gSystem`; a later installation is neither shown nor excluded, so
  the precondition for scattered host pages is not established either way. The 18:00 boot of the guarded
  build contains **no** span-refusal line, so it is not established that the guard executed at all.
* **Why kernel 1.0.13 panicked is unattributed.** The stack names a zeroed context lock, which means a
  context object reached `guc_retire_inflight_request_prio` without `intel_context_init()`. Whether the
  stolen-region skip caused that, exposed a latent ordering bug, or the object was stale memory is not
  determined, and the new `drm_info` lines are absent from the retained log.
* The not-started request `8:24 [0x1002]` may simply be blocked behind earlier work; it is not proof
  that its own copy instruction is defective.
* IOSurface import refusal (`-1000072003`) cannot alone explain the stall, because the fallback's first
  upload and readback both completed.
* Later CoreDisplay/CoreAnimation exceptions are **aftermath**, not cause. Faking pipeline success or
  manufacturing textures would hide the failure.

### What the struggles taught us

1. **Silent failures are the expensive ones.** Missing `_kmod_info`, a stripped environment, a filtered
   log line, a sampler that "succeeds" with no output, an AuxKC pointing at a deleted directory — every
   one of these produced a *plausible-looking* result that was wrong.
2. **Verify the measurement before trusting the conclusion.** Four separate times, the instrument was
   broken (stripped env, report selection, log throttle, kernel capture zeros).
3. **"Invariant across changes" is a clue about the layer.** When nothing you change matters, you are
   changing the wrong layer — the image, not the EFI.
4. **Fix one variable, and keep the negative result.** `INTEL_DEBUG=stall` did not work; that is now
   knowledge, not a retry candidate.
5. **A verified software fix is not a hardware fix.** The lost-wake race is real, reproduced and fixed.
   It still does not explain the desktop hang, and the documentation refuses to conflate them.
6. **A real defect can be the wrong defect.** The 1.0.11 mapping-lifetime omission is provable in source
   and worth fixing; the hardware reproduced the original ring overwrite anyway. Record the falsification
   instead of defending the fix.
7. **A mechanism is not a measurement.** The 1.0.12 raw-span defect can explain a pixel-valued write, but
   the boot log does not show that its precondition (a system mapper) was present, and the guarded build's
   own refusal message never appeared. State the conditional with the fix.
8. **A candidate that fails earlier has not explained more.** Kernel 1.0.13 removed a memory region and
   panicked eight seconds into boot. A new, earlier failure is a new question, not evidence for the
   hypothesis that motivated it — and a build whose log lines never show up cannot even prove the branch
   ran.

---

<a name="validation"></a>
## ✅ Validation methodology

The project uses a 22-case hardware gate that runs **before** any desktop boot is armed. What it does
and does not prove:

**Does prove (when it passes):**
* Deterministic upload → render → readback → exact-pixel comparison on real hardware.
* 1000 iterations per case, **26,000 frames total**, including padded-row full-HD and RGBA/BGRA
  IOSurface backing-pixel verification.
* Both direct and IOKit transports, with route markers checked rather than assumed.
* Pool accounting: `created = destroyed = completed + abandoned`, zero live/pending/quarantined.
* The suite **refuses to arm** a desktop boot unless the loaded kernel/plugin/libdrm hashes match the
  package, the boot UUID is current, and the parser sees **no timestamped** kernel GPU-hang,
  TLB-timeout/reset or fault events. (The parser excludes log-filter headers and command metadata, which
  previously produced a false-positive hang match.)

**Does not prove:**
* Sustained stability, correctness of arbitrary workloads, or that the hardware hang root cause is
  understood.
* Anything about WindowServer composition, which is the workload that fails.
* That a passing application matrix predicts desktop success — it demonstrably does not.

Local test-suite passes (ASan/UBSan, mocked Vulkan calls, installer rollback fixtures, release-policy
constructors, native Apple Silicon harness checks) validate **code paths only**. They are never
presented as hardware results. Mocked allocation/reclamation counts are labelled as mocked.

---

<a name="reproduce"></a>
## 🧪 Reproduce the claims

Every figure in this document comes from a dated run on the physical Dell, not from a private harness.
The scripts and the report format live in the tree, so the claims can be re-run and re-checked. All steps
assume the **Dell Latitude 5350** (`8086:7D45`) with the runtime installed on x86_64 macOS.

### 1. Confirm you are running the recorded configuration

```bash
cd latitude-runtime
shasum -a 256 -c SHA256SUMS.txt        # shipped binaries match the manifest
cat BUILD-MANIFEST.json                # base revisions for every patched upstream
sw_vers; sysctl -n machdep.cpu.brand_string
```

If the hashes do not verify, stop: you are not measuring the recorded configuration.

### 2. Reproduce the two smallest results (GPU work, no desktop)

```bash
./latitude-runtime/tools/latitude-vulkan-test ./latitude-runtime/tools/check.spv
./latitude-runtime/tools/latitude-metal-test
```

Expected output:

* Vulkan prints a device line for `8086:7d45` and
  `PASS Vulkan hardware execution: real 8086:7d45, 65536 verified values, seed=…`
* Metal prints `PASS render: 4096 pixels checked after shader execution`

These are the 65,536-value and 4,096-pixel claims, in isolation.

### 3. Reproduce the 22-case gate (26,000 frames)

```bash
sudo /bin/bash latitude-desktop/test-readback.sh 1000 full
```

This runs 11 IOKit + 11 direct cases at 1,000 iterations each and writes
`latitude-desktop/reports/readback-<timestamp>/`. It does **not** arm a desktop boot; the
`test-and-arm-desktop.sh` wrapper is what arms one after the gate passes.

Then check the report directory:

```bash
grep -c ' exit=0$' results.txt        # expect 22 passing cases
cat hang-check.txt                    # expect empty: no timestamped hang/TLB/reset/fault events
cat desktop-gate.txt                  # candidate, case/iteration counts, boot UUID, binary hashes
```

The recorded run behind the numbers above is `readback-20261019-114424` (on the USB installer this is
`Desktop/reports/readback-20261019-114424`), written up in
`research/verified-0.3.1-full-gate-20261019.md`: 22 cases, 26,000 frames, **80,020 pools created /
80,020 destroyed**, zero live, pending or quarantined.

### 4. What a reproduction does and does not mean

* A pass reproduces the **application matrix** for the installed candidate. It does not reproduce the
  WindowServer result, which fails.
* The gate checks that the loaded kernel, plugin and libdrm hashes match the package and that the boot UUID
  is current. A pass with different binaries is a different result, not a reproduction.
* Local unit tests (ASan/UBSan, mocked Vulkan, installer rollback fixtures) validate code paths only and
  are never hardware evidence.
* The kernel 1.0.10/1.0.11 ring words are diagnostic evidence, not a fix. A reproduction that still shows
  `ff000000` below a request head reproduces the corruption; it does not identify the writer.

---

<a name="diagnostics"></a>
## 🔎 Diagnostics cheat-sheet

The commands used to gather every report in `research/`. Run them **before** rebooting or reinstalling:
a failed boot's unified log is often gone after the next restart.

```bash
# Is the GPU visible to IOKit?
ioreg -l -p IOService | grep -i -E "7d45|NMXGPU"

# Did the kexts actually load (not just install)?
kextstat | grep -i -E "nmxgpu|nmxaccel"

# GPU and display state
system_profiler SPDisplaysDataType

# Our driver's messages, last 10 minutes
log show --last 10m --predicate 'eventMessage CONTAINS "NMXGPU"'
log show --last 10m --predicate 'eventMessage CONTAINS "CoreUltraGraphics"'

# Kernel GPU events
log show --last 10m --predicate 'eventMessage CONTAINS "GPU HANG" OR eventMessage CONTAINS "TLB"'

# Kernel 1.0.10+ command-ring words (the 0xff000000 overwrite), and the parsed request/GuC state
log show --last 10m --predicate 'eventMessage CONTAINS "NMX-i915-ring"'
log show --last 10m --predicate 'eventMessage CONTAINS "NMX-i915-request" OR eventMessage CONTAINS "NMX-i915-first-error"'

# Framebuffer 0.2.4+: an allocation refused because its host pages are not contiguous
log show --last 10m --predicate 'eventMessage CONTAINS "refusing noncontiguous"'

# Kernel 1.0.13: did the stolen-region skip and the ring-pin log actually run?
log show --last 10m --predicate 'eventMessage CONTAINS "stolen region withheld" OR eventMessage CONTAINS "Latitude MTL ring pinned"'

# Kernel panics, including the 1.0.13 boot panic (8 s uptime, "used before mtx_init")
ls -t /Library/Logs/DiagnosticReports/Kernel-*.panic | head -1
log show --last 10m --predicate 'eventMessage CONTAINS "used before mtx_init"'

# Newest WindowServer crash report
ls -t ~/Library/Logs/DiagnosticReports/WindowServer*.ips | head -1

# Full failure bundle, before any reinstall
# (pass the failed boot's start and end time)
./research/collect-desktop-failure.sh '2026-10-19 12:50:00' '2026-10-19 13:00:00'
```

The rule is **collect first, reboot second, reinstall last**. Installing a new candidate over a failed
boot destroys the evidence that candidate failed.

---

<a name="workspace"></a>
## 📂 Workspace layout

```text
iGPU Port/
├── AMFIPass/              # AMFI bypass kext (1.4.1) used by the OpenCore config
├── MacKernelSDK/          # Apple kernel-space headers for kext builds
├── MyIntelGPU/            # Earlier standalone diagnostic kext (probe only; failed auth on target)
├── NullMoth/              # Upstream NVIDIA-for-macOS tree: kexts/, plugin/, translator/, nvk/, nvk-macos.patch
├── NullMoth-Xe/           # Sibling Panther Lake / Xe3 SR-IOV VF work + patch series (separate target)
├── Vulkan-Headers/        # Khronos Vulkan headers
├── accel-build/           # NMXAccel.kext build output
├── backups/               # Per-candidate source/EFI snapshots (backups/desktop-0.3.5-before/, backups/kernel-1.0.11-before/ …)
├── build-inputs/          # Pre-flight compilation payloads
├── build-tree/            # Compiler intermediate object tree
├── desktop-build/         # Versioned NVMTLDriver 0.2.4 → 0.3.5 binaries + kernel 1.0.9 → 1.0.13 link logs and tests
├── desktop-sources/       # Patch scripts that generate each candidate (implement-*, fix-*, package-*)
├── drm-kmod/              # Linux DRM ported to FreeBSD via linuxkpi (i915/, drm/, ttm/, linuxkpi/)
├── firmware/i915/         # mtl_guc_70.bin, mtl_dmc.bin, mtl_huc_gsc.bin, mtl_gsc_1.bin (+LICENSE.i915)
├── freebsd-src/           # FreeBSD source subset / LinuxKPI compatibility headers
├── latitude-desktop/      # Latitude-specific desktop glue (LatitudePanelClaim.cpp, scanout, journal)
├── latitude-runtime/      # Packaged install/rollback runtime (Library/, BUILD-MANIFEST.json, SHA256SUMS)
├── libdrm/                # Userspace DRM abstraction (patched xf86drm.c)
├── mesa/                  # Mesa 26.3.0-devel incl. src/intel/vulkan (ANV)
├── ogkm610/               # NVIDIA open-kernel-modules 610 tree (translation reference)
├── port-artifacts/        # Per-candidate audit bundles (desktop-0.3.5/, patches, logs, validation)
├── research/              # Dated evidence records and candidate research notes
├── toolchain/             # Cross-compilation tooling
├── upstream-runtime/      # Runtime package staging
├── PORT-STATUS.md         # Short point-in-time status
├── ROADMAP.md             # Authoritative, dated roadmap and promotion criteria
└── SHA256SUMS-upstream.txt
```

`research/` is the evidence trail; read the newest files first:

| File | Contents |
|---|---|
| `windowserver-1.0.13-panic-181731.md` | 1.0.13 boot panic: verbatim stack, the zeroed context lock in source, and why the cause is unattributed |
| `windowserver-firmware-stolen-1.0.13.md` | The stolen/DSM ownership hypothesis and the region-skip candidate |
| `windowserver-1.0.12-failure-180032.md` | 1.0.12 / framebuffer 0.2.4 target trial: corruption and timeout persist; no span-refusal evidence |
| `windowserver-raw-physical-1.0.12.md` | 1.0.12 / framebuffer 0.2.4 raw-physical allocation audit and its stated caveats |
| `windowserver-1.0.11-failure-173438.md` | 1.0.11 hardware trial: identical ring overwrite; the page-pin fix is not the cause |
| `windowserver-mmap-lifetime-1.0.11.md` | The mapping-lifetime defect and the 1.0.11 fix candidate |
| `windowserver-boundary-diagnostic-1.0.10.md` | 1.0.10 diagnostic scope, bounds and capture design |
| `windowserver-0.3.5-failure-165941.md` | Frozen-cursor boot; submission #8 / readback #3 stall |
| `verified-0.3.1-full-gate-20261019.md` | The 22-case / 26,000-frame / 80,020-pool hardware gate record |
| `verified-windowserver-20261019-1200.md` | The desktop failure, submission by submission |
| `windowserver-0.3.5-research.md` | 0.3.5 candidate: compression isolation + kernel capture |
| `windowserver-0.3.4-research.md` | Dedicated-staging candidate and the source audit table |
| `verified-0.3.1-guc-wake-fix.md` | The LinuxKPI lost-wake race, reproduced and fixed |
| `desktop-roadmap-evidence.json` | Machine-readable evidence |

---

<a name="build"></a>
## 🛠️ Building and testing

1. **Build prerequisites** — Xcode command line tools, `meson`/`ninja` for Mesa and libdrm, the Apple
   `kext`/SDK path via `MacKernelSDK`, and the CLC tools (built separately for an Apple Silicon host).
2. **Compile the components** — i915/DRM via the drm-kmod Makefiles, ANV/libdrm via meson, the plugin and
   translator via the NullMoth build, the kexts via `MacKernelSDK`.
3. **Package** — `latitude-runtime/install-runtime.sh` validates hashes and both kexts against the
   target's kernel collections *before* touching live files; `BUILD-MANIFEST.json` pins every base.
4. **Gate** — run the 22-case suite on the target. A pass is required before any desktop boot is armed.
5. **Desktop trial** — one armed boot, then collect failure evidence with
   `collect-desktop-failure.sh` **before** reinstalling anything.
6. **Roll back** — `rollback-runtime.sh` restores the saved runtime and Auxiliary KC from
   `/Library/NullMoth/latitude5350-backups` and clears the one-shot opt-in.

Never bypass a failed kernel-collection validation. Bring the report back instead.

---

<a name="roadmap"></a>
## 🗺️ Roadmap

`ROADMAP.md` is authoritative and dated. The following is a summary of its structure, not a substitute.

**Current (plugin 0.3.5, kernel 1.0.13 parked, framebuffer 0.2.4):** compression isolation for this
WindowServer/device only; diagnostic kernels 1.0.9 → 1.0.10 (bounded command-ring words, parsed GuC
registers and request state); the 1.0.11 mapping-lifetime correction (lifetime page pin for i915 CPU user
mappings; legacy GTT mmap refused); the 1.0.12 / framebuffer 0.2.4 raw-physical correction
(`HostPhysicallyContiguous | MapperNone`, verified segment span, rollback of kernel + framebuffer + AuxKC
as one unit); and kernel 1.0.13, which withholds the MTL stolen-memory regions from i915 on `8086:7d45`.
Kernels 1.0.9 and 1.0.10 changed **diagnostics only**; 1.0.11 was shown **not** to resolve the ring
overwrite; **1.0.12 was booted and the overwrite persisted**; **1.0.13 panicked 8.04 s into boot** and is
parked until that panic is attributed or the change is reverted.

**Promotion criteria (unchanged):**

* A desktop pass requires evidence that the candidate activated, the desktop stayed responsive, **real
  frames were presented**, and no GPU/fence errors occurred. A visible software-fallback desktop is
  **not** a pass.
* The full 22-case gate must be revalidated (not merely re-run for show) when a candidate changes the
  render path.
* No automatic reboot from any installer or test script.

**The ring overwrite is now the target.** The next branch is a **ring guard** — diff the previous
request's tail and WA-tail dwords between tail publications — plus a **physical-page ownership map** of the
ring, the IOSurface/private-image/staging buffers, and the earliest submission boundary whose words
changed. The raw-physical correction gives that map a specific question to answer: were the exported
surfaces actually host-contiguous on this machine (`IOMapper::gSystem` present or not), and did the
guarded allocator ever refuse a span? The virtio scan-out and cursor buffers need the same check for the
QEMU configuration. **Not** another identical reboot, a longer fence timeout, a firmware swap, or a repeat
of the application matrix — and not another boot of 1.0.13 unchanged, which would only reproduce its
panic.

**Deferred:** sustained physical composition, sleep/wake, brightness, external outputs, hardware video
decode, modesetting and error recovery. Every one of these is currently **unverified**, and no
future-proof claim is made for any of them.

---

<a name="versions"></a>
## 🕓 Version history (plugin 0.2.4 → 0.3.5, kernel 1.0.8 → 1.0.13, framebuffer → 0.2.4)

Each candidate changed as few things as possible, and each failure narrowed the next step. The one-line
"what changed" and "what happened" is the honest spine of the project. All dates are October 2026.

| Version | What changed | What happened |
|---|---|---|
| 0.2.4 | First desktop path: panel claim, pipe 0 registration, IOSurface-to-panel copy | Registration confirmed; **all 64 diagnostic samples zero**, IOSurface import `-1000072003`, fence `VK_TIMEOUT` at 5000 ms, WindowServer stack exhaustion, `GPU HANG 12:1:00dfffff` |
| 0.2.5 | Bounded terminal-error buffers so backend loss cannot recurse | Submissions 1–4 complete; **readback #5 and upload #6 time out**; `INTEL_DEBUG=stall` confirmed enabled and ineffective (recorded negative) |
| 0.2.6 | Readback correctness patch and isolated per-case matrix | 10 direct cases pass (1,200 frames); forced IOKit fails during enumeration before any ioctl |
| 0.2.7 | Forced-route enumeration + token classification fix, discovery fallback, prior-access sync, release trace filter | Recovered evidence: `VK_ERROR_DEVICE_LOST` after 13,072 ms and `GPU HANG 12:1:00b79797` |
| 0.2.8 | Diagnostic comparison plus a command-pool-only fresh-allocation switch | **Invalid as a test** — the release constructor stripped every `NVMTL_*` variable; hang at frame 169 |
| 0.2.9 | Preserve explicit controls for the test process, in-driver effective-policy query, refuse on mismatch | Restores trustworthy A/B measurement; desktop activation still disabled |
| 0.3.0 | Fresh command pools everywhere, immediate destroy, quarantine on uncertain completion | 4,000 frames pass, then a **GuC TLB-invalidation timeout and a hang on the fifth process** (upload #1285, frame 428); 1286 created / 1285 destroyed / 1 quarantined |
| 0.3.1 | LinuxKPI lost-wake fix (`TASK_WAKING` under the sleep-channel lock) in kernel 1.0.8 | 100,000 ASan/UBSan scenarios reproduce-then-fix the race; **full 22-case / 26,000-frame / 80,020-pool gate passes** — the standing baseline |
| 0.3.2 | WindowServer-only serialization: no submit-ahead, defer IOSurface-writer scheduling | Black screen with **no retained evidence**; an unbounded `pthread_mutex_lock` ran before the GPU wait |
| 0.3.3 | Bounded `trylock` + deadline, pre-created startup journal, early loader capture, sampler fix | 8 submissions / 3 readbacks, then **readback #4 times out**; `GPU HANG 12:1:00dfffff` |
| 0.3.4 | Dedicated fresh staging scoped to this `8086:7d45` WindowServer; journal, log-throttle and sampler fixes | Submissions 1–7 pass, **submission #8** (third readback) times out — staging reuse is not required to trigger the hang |
| 0.3.5 | `noccs` compression isolation scoped to WindowServer/device; diagnostic kernel 1.0.9 (parsed GuC registers + request state) | AuxKC pointed at a deleted temporary bundle; the installer was rebuilt from permanent paths. **Desktop result still unverified** |
| 0.3.5 + kernel 1.0.10 | Diagnostic only: bounded command-ring capture in `intel_guc_submission` and `i915_gpu_error` — the words below each active render request's head, saved at submission and re-read at hang (fixed ~60 KiB, write-once slots, no hot-path logging) | 17:14 boot reproduced submission #8 / readback #3. The 17:16 capture shows request 18's switch-out and WA tail (`0xc98–0xca4`) reading `0xff000000` before request 20, with GuC `IPEHR=ff000000`, `RING_HEAD=ACTHD=0xca4`. **Diagnostic only, no fix** |
| kernel 1.0.11 (fix candidate) | Pin i915 CPU user mappings (`WB`/`WC`/`UC`) for the mapping lifetime and release the pin after the IOKit unmap; refuse the legacy `I915_MMAP_TYPE_GTT` alias; report `i915_gem_mmap_gtt_version() = 4` under NMXKPI | Local only: 438-object x86_64 link, undefined-import set equals 1.0.8, kernel UUID `B972B890-…`, signed-binary SHA-256 `496e108b…`, 20,000-lifetime ASan/UBSan fixture and installer/rollback fixtures pass. **17:32 hardware boot reproduced the identical ring overwrite and `IPEHR=ff000000`. Fix does not resolve the hang; retained as a correctness correction** |
| kernel 1.0.12 + framebuffer 0.2.4 (candidate) | Request `kIOMemoryHostPhysicallyContiguous \| kIOMemoryMapperNone` in `nmxVramAlloc()` and `nmx_xnu_mem_alloc()`; refuse to export a raw physical span unless the first segment covers the whole request (segment/descriptor length, CPU pointer and overflow; mask and alignment in the kernel allocator); release slot and budget on rejection; installer stages/validates/backs up/rolls back kernel + framebuffer + AuxKC together | Local: Sequoia-decision ASan/UBSan fixture (old code exports a 4 KiB segment for an 8 KiB request, new code rejects it; 2,000 balanced cycles), both kexts build and link, installer/rollback fixtures pass. Kernel UUID `000EF47E-…`, SHA-256 `1ad3f4dc…`; framebuffer UUID `59DA4CD2-…`, SHA-256 `495ed4cc…`. **Booted 19 Oct 17:58: readback #8 completed, submission #9 timed out at 5000 ms, `0xff000000` recurred at `0xe00–0xe0c` with `IPEHR=ff000000`; no span-refusal line in the log, so the guard's execution is unverified. Does not fix the hang** |
| kernel 1.0.13 (parked) | Withhold `INTEL_MEMORY_STOLEN_LOCAL` and `INTEL_MEMORY_STOLEN_SYSTEM` from i915 for `8086:7d45` under `NMXKPI`, so rings/objects allocate from system memory instead of the DSM pool the firmware panel occupies; log `stolen=`/`size=`/`ggtt=` at ring pin | Local: 438-object x86_64 link with the frozen 1.0.8 import set, region-probe/ring-allocation sanitizer fixtures, installer/KC rollback fixtures. Kernel UUID `121AACAE-4C53-3357-9356-38C79222A842`, SHA-256 `d57981cb…`. **Booted 19 Oct 18:17 and panicked after 8.04 s: `mutex … used before mtx_init` in `guc_retire_inflight_request_prio`, on a zeroed `intel_context.guc_state.lock`. No desktop. Cause unattributed; do not re-arm unchanged** |

---

<a name="licensing"></a>
## ⚖️ Attribution and licensing

This project is a **retargeting**, not original work. It stands on:

* [NullMoth / nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) — driver skeleton,
  plugin, translator and the `xkpi` LinuxKPI-on-xnu layer. **PolyForm Noncommercial 1.0.0**; the kexts,
  plugin and translator carry this licence, which is **noncommercial** and materially different from
  the Apache-2.0 badge this README previously displayed.
* The [NullMoth-Xe](https://github.com/nullmoth/nvidia-macos-driver) Panther Lake write-up — the
  upstream portability fixes reused for drm-kmod, libdrm, Mesa and the plugin.
* Intel `i915`, DRM and TTM from the Linux kernel — **GPL-2.0**; firmware under
  `firmware/LICENSE.i915`.
* FreeBSD `linuxkpi` and `freebsd-src` — **BSD-2-Clause**.
* [Mesa](https://gitlab.freedesktop.org/mesa/mesa) 26.3.0-devel incl. ANV — **MIT**.
* `libdrm` — **MIT**.
* Khronos `Vulkan-Headers` — Apache-2.0 / MIT (see `Vulkan-Headers/LICENSES`).
* The AIR→SPIR-V translator (based on `metal2vulkan`) — **LGPL-3.0** with **GPL-3.0** components; see
  `NullMoth/translator/LICENSE` and `COPYING`.
* `ogkm610` — NVIDIA open kernel modules, MIT except where noted.
* AMFIPass 1.4.1, Lilu and VirtualSMC — by their respective authors, under their own terms. No licence
  text ships inside `AMFIPass/AMFIPass.kext` in this tree; confirm it upstream before redistribution.

**Original work** (VedCloud code, scripts, patches, tests and documentation) is licensed under the
**[Meteor Lake Xe-LPG Metal Graphics License](LICENSE)**, whose grant is substantively equivalent to
Apache-2.0 and which is additionally available under Apache-2.0. **Third-party components are not
licensed by it** and remain under their own terms, enumerated in Schedule A of `LICENSE`.

Because the tree combines **GPL-2.0-only** code (e.g. `drm-kmod/drivers/gpu/drm/drm_gpuvm.c`,
`dma-buf/sync_file.c`) with **GPL-3.0** code (the translator) and with **PolyForm Noncommercial** code
(NullMoth), no single license covers the combined work: GPL-2.0-only and GPL-3.0 are mutually
incompatible, and PolyForm NC is incompatible with both the GPL and permissive relicensing. Those
incompatibilities are inherent to the upstreams and are not resolved by the project license. The
per-component licences are preserved in-tree (`latitude-desktop/licenses/`, `latitude-runtime/licenses/`,
and each upstream tree's own `LICENSE`/`COPYING`), and must remain in place.

---

<a name="principles"></a>
## 🧾 Design principles

These rules are enforced by convention across the tree, and they are why the evidence in `research/`
can be trusted:

1. **No guessed register values, quirk values or ACPI scope names.** If it is not measured or sourced,
   it is not written.
2. **No unsourced attributions.** Every external claim carries an exact URL, or the text says the
   source could not be found.
3. **Local build success ≠ hardware success.** Mocked tests are labelled as mocked; a passing compile
   is never reported as a passing device.
4. **One variable at a time**, with a saved before-state and a rollback path, and no automatic reboots.
5. **Negative results are recorded** and stay negative. `INTEL_DEBUG=stall`, longer timeouts and
   fabricated success are documented dead ends, not proposed fixes.
6. **Generation boundaries are respected.** Meteor Lake is not Panther Lake; Xe-LPG is not Xe3.
7. **The failure comes before its consequences.** GPU execution failure is reported as the failure;
   CoreDisplay crashes are reported as its aftermath.

---

<a name="adr"></a>
## 🧮 Design decisions

The choices that shaped the port, and the alternatives that were rejected. These are the reasons the
evidence in `research/` looks the way it does.

| # | Decision | Alternative rejected | Why |
|---|---|---|---|
| 1 | Retarget NullMoth's driver skeleton | Write a Metal driver from scratch; use WhateverGreen | The Metal plugin, AIR→SPIR-V translator and LinuxKPI-on-xnu base already existed; WhateverGreen documents Ice Lake as its newest Intel family and supports neither Alder nor Meteor Lake |
| 2 | Base the kernel driver on `i915` | The `xe` driver | The laptop's own Linux reference and the available xnu DRM/LinuxKPI port are i915-based; a second driver model would be a separate project |
| 3 | Vulkan backend = ANV | NVK; software fallback | Xe-LPG is Intel silicon, and ANV is the mature Intel Vulkan backend in Mesa |
| 4 | Keep the AIR→SPIR-V translator | Rewrite the Metal frontend | Metal hands the plugin AIR, so lowering to SPIR-V is the shortest path to ANV |
| 5 | One-shot NVRAM opt-in for GPU activation | Always-on kext | A failed attach must not silently re-arm on every boot |
| 6 | Fresh command pools, destroyed immediately | Cache / pop / push pool reuse | Reuse was a variable in the hang; removing it was necessary, though not sufficient |
| 7 | Quarantine uncertain completions | Reuse resources after a timeout | Reusing work whose fence was never observed risks corrupting later submissions |
| 8 | Bounded `trylock` + deadline on the desktop submission lock | Blocking `pthread_mutex_lock` | The 0.3.2 black screen showed an unbounded lock running before the GPU wait budget |
| 9 | Scope dedicated staging to this WindowServer/device | Change staging globally | Isolates one variable without perturbing the passing application matrix |
| 10 | Scope `noccs` compression isolation likewise | Disable compression everywhere | Tests compression as a variable while leaving application behaviour unchanged |
| 11 | Kernel 1.0.9 changes diagnostics only | Change scheduling, reset policy or timeouts | No evidence supports a scheduling fix; capture the missing request/GuC state first |
| 12 | Never reboot automatically; collect before reinstall | Auto-retry the boot | The failed boot's unified log is the evidence; rebooting or reinstalling destroys it |
| 13 | Treat application and desktop as separate milestones | Assume one pass means "working" | 26,000 passing application frames demonstrably do not predict WindowServer success |
| 14 | Pin i915 CPU user mappings for the mapping lifetime; refuse the legacy GTT mmap the port cannot revoke | Add a cache flush, raise the fence timeout, or restore FreeBSD's whole-object VM mmap | The port's revocation shim is a no-op, so a lifetime pin is the only way a static IOKit mapping is safe; a flush or a longer timeout would mask the sequence rather than restore GPU execution |
| 15 | Keep the 1.0.11 correction in the tree even though the hang persisted | Revert it when the ring overwrite recurred | It fixes a real, source-demonstrated mapping-safety defect; "not the cause of *this* hang" is not the same as "not a bug" |
| 16 | Require `HostPhysicallyContiguous \| MapperNone` and verify the returned segment spans the whole buffer before exporting a raw physical range | Trust `PhysicallyContiguous` and the base address alone | Apple's own code makes `PhysicallyContiguous` host-contiguous only when no system mapper exists; the exported `IODeviceMemory` range must not extend past memory the allocation owns, regardless of whether this target currently has a mapper |
| 17 | Ship kernel 1.0.12 + framebuffer 0.2.4 as a candidate, not a fix | Call the hang solved because the allocator assumption was wrong | The scattered-page precondition is not evidenced on this target (`AppleVTD is not yet installed as gSystem`), the virtio-build scan-out exports (`fScanBuf`/`fCursorBuf`) still take a raw span without a length check, and the later 18:00 boot confirmed the overwrite persisted with no span-refusal evidence |
| 18 | Park kernel 1.0.13 (stolen-region skip) after its boot panic; discriminate with a 1.0.12 boot first | Re-arm 1.0.13 unchanged, or declare the stolen-memory hypothesis disproved | The panic's cause is unattributed: the stack proves a zeroed `intel_context.guc_state.lock` reached `guc_retire_inflight_request_prio`, but no path from "region withheld" to that state is shown, and the new log lines are absent from the capture. Re-arming would reproduce the same 8-second panic; booting the last characterised payload under the same collector tests whether the panic needs the region skip at all |

---

<a name="glossary"></a>
## 📖 Glossary

| Term | Meaning |
|---|---|
| **AIR** | Apple Intermediate Representation — Metal's shader IR, the input to the translator |
| **ANV** | Mesa's Intel Vulkan driver |
| **AuxKC** | Auxiliary Kernel Collection — where third-party kexts are staged on modern macOS |
| **CCS / `noccs`** | Colour Compression; `noccs` disables it as an isolation experiment |
| **CLC** | Mesa's OpenCL C compiler, used here to build shader tooling for the host |
| **DSM / GSM / GGTT** | Device physical / graphics-memory-relative / graphics-translation-table address spaces |
| **GEM / TTM** | DRM graphics-execution memory management, and its translation-table manager |
| **GuC / HuC / DMC / GSC** | Intel GPU microcontroller and firmware: scheduling, media, display, security |
| **LRC** | Logical Ring Context — per-context GPU register state |
| **LinuxKPI** | FreeBSD's Linux kernel API shim, used here to compile i915 on xnu |
| **MATs** | Memory Attributes Tables — firmware memory-map support that selects booter quirks |
| **PSO** | Pipeline State Object |
| **SIP** | System Integrity Protection |
| **SPIR-V** | Vulkan's shader IR |
| **Xe-LPG** | The GPU generation in Meteor Lake, distinct from Xe2 (Lunar Lake) and Xe3 (Panther Lake) |

---

<a name="faq"></a>
## ❓ FAQ

**Does this actually work?**
For applications, yes: Metal and Vulkan run on the Xe-LPG iGPU and produce exact, verified output
(65,536 Vulkan values, 4,096 Metal pixels, 26,000 frames across 22 cases). Your entire desktop, no:
WindowServer composition still hangs. Those are two different milestones, and this project says so plainly.

**Can I install it on my laptop?**
Only if you have this exact configuration: Dell Latitude 5350, iGPU `8086:7D45`, macOS 15.8.1. A
different device ID needs `IOPCIPrimaryMatch` changes and a fresh evidence run; nothing else is claimed.
There is no generic installer.

**Can I use it as a daily driver, for games or video editing?**
No. Sustained stability, WindowServer composition, hardware video decode, sleep/wake, brightness and
external displays are all unverified. The only validated workload is the application gate.

**Is it safe to install?**
No. The setup disables large parts of SIP and AMFI and loads unsigned kexts. A boot loop or a damaged
kernel collection can make the machine unbootable. Keep a known-good EFI on a separate USB and a full
backup off-device.

**Why does the desktop fail if Metal works?**
WindowServer is a different workload: concurrent surface import and readback, long-lived contexts, colour
compression and panel scanout. The application gate does not exercise that path — and the project states
explicitly that a passing application matrix does not predict desktop success.

**Didn't you find the cause in the ring buffer?**
We found the *symptom* precisely: a four-word `0xff000000` block replaces the previous request's
switch-out and workaround tail, and the GPU fetches it (`IPEHR=0xff000000`, `RING_HEAD=ACTHD=0xca4`).
We have **not** identified the writer. Kernel 1.0.11 fixed a real mapping-lifetime defect and the hardware
reproduced the identical overwrite, so that defect is explicitly **not** claimed as the cause. Kernel 1.0.12
and framebuffer 0.2.4 corrected a second real defect — a raw physical span exported without checking that
the pages were host-contiguous — but that build was booted on 19 October and the overwrite recurred, with
no span-refusal line in the log to show the guard even ran. Kernel 1.0.13 then withheld i915's stolen-memory
region and **panicked 8 seconds into boot** on an uninitialised context lock, a failure whose cause is not
yet attributed. The next step is a ring guard plus physical-page ownership, not another guess — and not
another boot of 1.0.13 unchanged.

**Why not WhateverGreen?**
Its own documentation lists Ice Lake as the newest supported Intel family; it supports neither Alder Lake
nor Meteor Lake.

**Why `i915` and not the `xe` driver?**
Because the available xnu DRM/LinuxKPI port and the laptop's own Linux reference report are i915-based.
That is a project constraint, not a claim that `xe` could not work.

**Why NullMoth?**
It already provides the three hard pieces this port needs — the Metal driver plugin, the AIR→SPIR-V
translator and the LinuxKPI-on-xnu driver skeleton — so the work becomes retargeting rather than invention.

**Is the GPU really doing the work, or is it a software fallback?**
The probes read exact values and pixels back from device memory and verify the transport route, so the
application results are real GPU execution. A *visible desktop* is a different matter: presenting the
firmware framebuffer is not accelerated composition, and the project does not count it as success.

**Can I contribute? What do you need?**
The same hardware and reproducible evidence: the report directory, boot UUID, exact log lines and the gate
output. "It works for me" without logs is not usable, and neither is a local build pass presented as a
hardware result.

**Why is the license custom, and can I use this commercially?**
No — commercial use is not permitted for the combined tree, because the NullMoth components are PolyForm
Noncommercial 1.0.0. The custom license covers only VedCloud original work; the GPL, LGPL, MIT and BSD
components keep their own terms. See *Attribution and licensing*.

**Will this support Lunar Lake or Panther Lake?**
That is the separate `NullMoth-Xe` target. Xe2/Xe3 cache and firmware workarounds must not be applied to
Meteor Lake.

---

<a name="consensus"></a>
## 📈 Where this breaks with consensus

The common claim is that modular Intel Core Ultra parts are a dead end for modern macOS graphics. On
this machine that claim is already partly falsified:

* the GPU is **identified** and the i915-based kext **attaches** to it on real hardware;
* **GuC 70.53.0** firmware loads and submission is enabled;
* **Metal and Vulkan work.** Vulkan returns 65,536 correct values, Metal renders 4,096 correct pixels,
  and **26,000 application frames** pass exact-pixel validation over **both** transport routes;
* a real **LinuxKPI lost-wake race** was found, reproduced and fixed.

What is not yet falsified is the hard part: **GPU-composited WindowServer on the physical panel.** The
evidence now points at command-ring *content* at a request boundary: a four-word `0xff000000` block
replaces the previous request's switch-out and workaround tail, and the GPU fetches it. The writer is
unidentified; the next step is a ring guard and a physical-page ownership map rather than another guess.
A second source defect — a raw physical span exported without verifying host contiguity — has a corrected
candidate (1.0.12 + framebuffer 0.2.4) that was booted and did **not** stop the overwrite; the log does not
show its guard executing. A third candidate (1.0.13, stolen-memory withholding) panicked 8 seconds into
boot and is parked. That is the honest frontier.
