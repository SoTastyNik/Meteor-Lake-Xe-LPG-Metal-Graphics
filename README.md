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
![Candidate](https://img.shields.io/badge/Candidate-0.3.5-orange)

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
| GPU-composited WindowServer desktop | Submissions 1–4 complete; **readback #5 times out at 5000 ms**, upload #6 stalls, then GPU hang | **Failing — blocking** |
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
| Machine | Dell Latitude 5350 2-in-1|
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

### The failures we still cannot explain, and say so

* The **exact root cause** of the WindowServer hang is not established.
* `Readback #3` succeeds and `#5` fails on the same boot; the trace does **not** prove they share an
  image, so "reuse while pending" remains unproven.
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

<a name="versions"></a>
## 🕓 Version history (0.2.4 → 0.3.5)

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
evidence points at the surface/readback path under concurrent WindowServer load, and the next step is
deeper kernel request-progress capture rather than another guess. That is the honest frontier.
