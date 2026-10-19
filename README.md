# Meteor Lake Xe-LPG Hardware Acceleration for macOS

![License](https://img.shields.io/badge/License-per--component_(see_below)-lightgrey.svg)
![Platform](https://img.shields.io/badge/Platform-macOS_15_Sequoia-blue)
![Hardware](https://img.shields.io/badge/Hardware-Intel_Core_Ultra_5_135U-orange)
![Graphics](https://img.shields.io/badge/Graphics-Xe--LPG%20%2F%208086%3A7D45-red)
![API](https://img.shields.io/badge/API-Metal%20%2F%20Vulkan-purple)
![Language](https://img.shields.io/badge/Language-C%20%2F%20Obj--C%20%2F%20C%2B%2B-blueviolet)
![Status](https://img.shields.io/badge/Status-Metal%20%2B%20Vulkan%20working%20%7C%20WindowServer%20composition%20in%20progress-yellow)

A hardware-acceleration port that brings **Metal and Vulkan** to the **Intel Core Ultra (Meteor Lake-P)
Xe-LPG iGPU (`8086:7D45`)** on a **Dell Latitude 5350** running **macOS 15 Sequoia**, using the
[NullMoth](https://github.com/nullmoth/nvidia-macos-driver) NVIDIA-for-macOS driver tree as the driver
skeleton and retargeting its graphics stack from NVIDIA/GSP to Intel i915/GuC.

The port reuses NullMoth's *Metal driver plugin → shader translator → Mesa Vulkan backend → kernel
extensions* architecture, but replaces every NVIDIA-specific element: the GSP firmware path becomes the
Intel GuC/HuC/GSC firmware path, the NVK backend becomes Mesa's **ANV** Intel driver, and the NVIDIA
kernel extensions become an i915-derived `NMXGPU` plus a DRM-user-client `NMXAccel`.

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

---

## 📊 Status at a glance

| Milestone | Evidence | Status |
| :--- | :--- | :--- |
| Real GPU identification (`8086:7D45`, Dell `1028:0CB6`) | macOS probe and the laptop's own Linux report agree | **Confirmed** |
| `NMXGPU` i915 kernel extension loads and attaches to the real GPU | Report `readback-20261019-114424`, kernel UUID match | **Confirmed** |
| Memory-mapped I/O / GGTT / firmware bring-up (GuC 70.53.0) | Kernel capture `kernel-guc-capture-1.0.9.log`; firmware loaded on both GTs | **Confirmed (init only)** |
| **Metal and Vulkan application rendering/compute** | **65,536 correct Vulkan values, 4,096 correct Metal pixels**, 26,000 exact frames across 22 cases (11 IOKit + 11 direct) | **Working** |
| Command-pool lifetime | **80,020 pools created / 80,020 destroyed**, zero live/pending/quarantined across the gate | **Passing (scoped)** |
| Accelerator + display-pipe registration | 0.2.4 / 0.2.5 reports: pipe 0 verified, phase-2 power-on complete, pipe active | **Init confirmed** |
| GPU-composited WindowServer desktop | Submissions 1–4 complete; **readback #5 times out at 5000 ms**, upload #6 stalls, then GPU hang | **Failing — blocking** |
| Panel scanout with correct pixels | Framebuffer loads and describes 1920×1080, reaches fixed scanout; presentation samples remain zero | **Partial / unverified** |
| Sleep-wake, brightness, external displays, video decode, long soak | No passing evidence | **Unverified** |

Every row below is traceable to a dated report under `research/`. The point of the table is to keep the
**working** Metal/Vulkan stack clearly separated from the **unfinished** desktop composition.

---

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

## 🧱 Component inventory

| Component | Version / base | Source in tree | Licence |
|---|---|---|---|
| `NMXGPU.kext` | kernel 1.0.9 candidate | `latitude-desktop`, `drm-kmod`, `freebsd-src` | i915/Linux → GPL-2.0; NullMoth wrapper PolyForm NC |
| `NMXAccel.kext` | 0.1 | `accel-build/NMXAccel.kext` | NullMoth PolyForm NC |
| `LatitudeMTLFB.kext` | 0.1.0 (`LatitudeMTLPanel`) | `desktop-build/LatitudeMTLFB.kext` | project |
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

## 🐞 The current blocker, stated precisely

This is the most important section in the document. On the physical desktop path, the failure is an
**actual GPU execution/progress failure**, not a missing registration and not merely a shader-compile
error. The observed ordering on a real opted-in boot (`failure-detail-20261019-130037`, boot UUID
`43CADE8D-…`, and `failure-detail-20261019-121101`):

```
panel claim activates, framebuffer load = 0, plugin SHA matches installed binary
submission #1  surface upload        → complete
submission #2  render / event        → complete
submission #3  readback              → complete
submission #4  render / event        → complete
submission #5  readback (image2 / staging12) submitted 12:58:50.085
               → VK_TIMEOUT after 5000 ms WindowServer fence budget
submission #6  concurrent surface upload → stalls ~80 ms later
plugin: backend disabled, CPU destination left untouched, uncertain resources retained
kernel: rcs0 hung context, request 8:24 [0x1002] not yet started
kernel: GPU HANG 12:1:00dfffff  recorded 12:59:03.867
WindowServer PID163 terminates; restarts hit dummy zero-fill timeouts
CoreDisplay: DisplaySurface::GetMTLTexture → SurfaceColorFill → "Failed to create MTLTexture"
             (BGRA8Unorm 1920x1080, storageModeManaged) → SIGABRT
```

What is **established**:

* Submissions 1–4 really complete, including three full-HD readbacks — readback *can* work, so this is
  not "readback is universally broken".
* Readback #3 and readback #5 may reference **different images**; the trace does not prove they share
  one. Treating pointer/address equality as reuse-while-pending is not evidence.
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

---

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
├── backups/               # Per-candidate source/EFI snapshots (backups/desktop-0.3.5-before/ …)
├── build-inputs/          # Pre-flight compilation payloads
├── build-tree/            # Compiler intermediate object tree
├── desktop-build/         # Versioned NVMTLDriver 0.2.4 → 0.3.5 binaries + kexts + link logs
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
| `verified-0.3.1-full-gate-20261019.md` | The 22-case / 26,000-frame / 80,020-pool hardware gate record |
| `verified-windowserver-20261019-1200.md` | The desktop failure, submission by submission |
| `windowserver-0.3.5-research.md` | Current candidate: compression isolation + kernel capture |
| `windowserver-0.3.4-research.md` | Dedicated-staging candidate and the source audit table |
| `verified-0.3.1-guc-wake-fix.md` | The LinuxKPI lost-wake race, reproduced and fixed |
| `desktop-roadmap-evidence.json` | Machine-readable evidence |

---

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

## 🗺️ Roadmap

`ROADMAP.md` is authoritative and dated. The following is a summary of its structure, not a substitute.

**Current (0.3.5):** compression isolation for this WindowServer/device only, plus diagnostic NMXGPU
1.0.9 kernel capture that reports referenced request state and parsed GuC registers. The 1.0.9 kernel
changes **diagnostics only** — not scheduling, reset or timeouts.

**Promotion criteria (unchanged):**

* A desktop pass requires evidence that the candidate activated, the desktop stayed responsive, **real
  frames were presented**, and no GPU/fence errors occurred. A visible software-fallback desktop is
  **not** a pass.
* The full 22-case gate must be revalidated (not merely re-run for show) when a candidate changes the
  render path.
* No automatic reboot from any installer or test script.

**If 0.3.5 still fails**, the next branch is targeted kernel request/dependency/GuC-progress capture
correlated with the now-complete startup submissions, then physical memory ownership/layout
investigation — **not** another identical reboot, longer fence timeout, or repeat of the application
matrix.

**Deferred:** sustained physical composition, sleep/wake, brightness, external outputs, hardware video
decode, modesetting and error recovery. Every one of these is currently **unverified**, and no
future-proof claim is made for any of them.

---

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

**The top-level licence of this repository must be reconciled with the components above before any
distribution.** The per-component licences are preserved in-tree (`latitude-desktop/licenses/`,
`latitude-runtime/licenses/`, and each upstream tree's own `LICENSE`/`COPYING`). Do not relicense or
redistribute this tree until that reconciliation is complete, and note that the PolyForm Noncommercial
terms inherited from NullMoth restrict commercial use independently of Apache-2.0.

---

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

## 📈 Where this breaks with consensus

The common claim is that modular Intel Core Ultra parts are a dead end for modern macOS graphics. On
this machine that claim is already partly falsified:

* the GPU is **identified** and the i915-based kext **attaches** to it on real hardware;
* **GuC 70.53.0** firmware loads and submission is enabled;
* **Metal and Vulkan work.** Vulkan returns 65,536 correct values, Metal renders 4,096 correct pixels,
  and **26,000 application frames** pass exact-pixel validation over **both** transport routes;
* a real **LinuxKPI lost-wake race** was found, reproduced and fixed.

What is not yet falsified is the hard part: **GPU-composited WindowServer on the physical panel.** The
evidence points at the surface/readback path under concurrent WindowServer load, and the next step is
deeper kernel request-progress capture rather than another guess. That is the honest frontier.
