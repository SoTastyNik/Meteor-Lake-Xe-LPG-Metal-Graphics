# Handoff brief — WindowServer desktop hang on Meteor Lake Xe-LPG under macOS

Prepared 2026-10-19. This is a request for root-cause hypotheses and patch-level guidance. Please read the
constraints in §10 before proposing anything: several "obvious" fixes are known dead ends.

---

## 1. What we are trying to fix

An out-of-tree macOS graphics stack runs on a real Intel Meteor Lake Xe-LPG iGPU. Application-level Metal
and Vulkan work and are verified. **WindowServer desktop composition does not.** The failure is a GPU
execution/progress failure in the surface **readback** path while WindowServer is also driving the GPU.
It is not a missing registration, not a shader-compile error, and not a host-lock problem.

Goal: restore GPU progress so WindowServer can composite the desktop.

---

## 2. Target hardware and software

| | |
|---|---|
| Machine | Dell Latitude 5350 |
| CPU | Intel Core Ultra 5 135U (CPUID `A06A4`) |
| iGPU | Meteor Lake-P Xe-LPG, PCI `8086:7D45`, subsystem `1028:0CB6`, rev 08, stepping `B0` |
| Cache/coherency | `has_llc=no`, `has_snoop=yes`, `has_flat_ccs=no` |
| OS | macOS 15.8.1 (24H32), x86_64 |
| Firmware | GuC **70.53.0**, DMC **2.23**, HuC **8.5.4**, GSC **102.1.15.1926** |
| Panel | 1920×1080, fixed firmware scanout |

The same laptop's Linux `i915` report identifies the same device, stepping, and GuC 70.53.0 on both GTs.

---

## 3. Stack

```
Metal app / WindowServer
  → NVMTLDriver.bundle        Metal driver plugin (user-space, NSBundle), NVMTLDevice/NVMTLAccelerator
  → libnvmtl_translate.dylib  Apple AIR → SPIR-V translator (metal2vulkan-derived)
  → ANV (Mesa 26.3.0-devel)   Intel Vulkan backend, patched for i915-on-xnu
  → libdrm / xf86drm.c        rebuilt as a pure IOKit render-node model
  → NMXAccel.kext             DRM user-client transport / accelerator
  → NMXGPU.kext               i915 + DRM/TTM + LinuxKPI compiled on xnu (438 source objects)
  → Xe-LPG hardware           GuC-submission engine, GGTT, DMC/HuC/GSC firmware
```

Kernel driver is **i915** (not `xe`), compiled against a LinuxKPI shim on xnu. GuC submission is enabled.

Display path is custom: `LatitudeMTLFB` + `NMXAGDC`, sustaining the **firmware framebuffer**; GPU
composition is copied into it by the existing display pipe. No page flipping, no modesetting. Plane/GGTT
registers are not rewritten.

---

## 4. Verified good (the control)

A 22-case hardware gate, 1,000 iterations each = **26,000 frames, 80,020 command pools created /
80,020 destroyed**, zero live/pending/quarantined. 11 cases via IOKit and 11 via direct DRM device-file
access, including a dedicated-fresh-staging case and RGBA/BGRA IOSurface backing-pixel verification.
Report `readback-20261019-114424`. This means **application** upload → render → readback → exact-pixel
comparison passes repeatedly, including full-HD readbacks, on the same hardware. The bug is specific to
the WindowServer workload, not to readback in general.

---

## 5. Exact failure sequence

### 5a. 0.2.5 / 0.3.3 boot (report `failure-detail-20261019-130037`, boot UUID `43CADE8D-…`)

```
panel claim active; framebuffer load returned 0; plugin SHA matched installed binary
submission #1  surface upload                       → complete
submission #2  render / event                       → complete
submission #3  readback                             → complete   (image readback works)
submission #4  render / event                       → complete
submission #5  readback on image2 / staging12
               submitted 12:58:50.085
               → VK_TIMEOUT (2) at 12:58:55.086, 5000 ms WindowServer fence budget
concurrent surface upload #6                        → stalls / times out ~80 ms later
plugin: backend disabled; CPU destination untouched; uncertain resources retained
kernel: rcs0 hung context, request 8:24 [0x1002] not yet started
kernel: GPU HANG 12:1:00dfffff  at 12:59:03.867
WindowServer PID163 terminates 12:59:04 (CoreAnimation pipeline PBGRAXb_Xh / "Vulkan is not up")
restarts 12:59:10/21: dummy zero-fill timeouts, CoreDisplay texture creation failures
```

An earlier boot showed the same shape at readback #5 with the IOSurface external-host import refused
(`VkResult -1000072003` = `VK_ERROR_INVALID_EXTERNAL_HANDLE`), falling back to private images.

### 5b. 0.3.4 boot (report `failure-detail-20261019-131639`)

```
first 7 submissions complete
submission #8 = third readback, using DEDICATED fresh staging (owned=1, new stage13)
  acquired desktop mutex, pre-submit returned, vkQueueSubmit returned VK_SUCCESS (0)
  → fence wait timed out after 5000 ms
kernel: hung rcs0 context, request 8:20, GuC context 0x1002 not started, GPU HANG 12:1:00dfffff
```

So **fresh command pools + dedicated fresh staging + serialized submit/finish are all insufficient**, and
TLS-staging reuse is **not required** to trigger the hang.

### 5c. 0.3.5 (current, unverified)

Only intentional change: `INTEL_DEBUG` gains `noccs` for vendor `8086` / device `7d45` / process
`WindowServer` (compression isolation), plus a **diagnostics-only** kernel 1.0.9. Result not yet
established from logs.

### 5d. New data point, unverified

An armed 0.3.5 boot now shows a **cursor instead of a black screen**. No logs collected yet, so we cannot
yet tell whether NMXGPU attached, whether the GPU hang/timeout is still present, or whether this is only
the cursor plane advancing over an otherwise stuck primary surface. Treat as unresolved.

---

## 6. Readback implementation (the failure site)

`port-artifacts/desktop-0.3.5/nvmtl_vk.c`, `nvmtl_vk_readback` (~line 5890) and
`nvmtl_vk_image_read` (line 5973). Per readback:

1. `nvmtl_read_plan_make(...)` computes copy region/row stride/mip/layer and barrier ranges.
2. `nvmtl_vk_image_upload_barrier(img)` (waits for prior accesses on the tracked old layout).
3. Staging allocation:
   - WindowServer/`7d45` fresh mode or `NVMTL_READBACK_STAGE_FRESH=1` → dedicated `nvmtl_vk_buffer_create(bytes, 3, …)` (owned, freed after CPU copy).
   - otherwise → `nvmtl_vk_stage(q, …)` TLS-retained pool buffer.
   - Required memory: `HOST_VISIBLE | HOST_COHERENT`, else refuse.
4. Recorded on one command buffer:
   - pipeline barrier `ALL_COMMANDS → TRANSFER` (`plan.before`),
   - `vkCmdCopyImageToBuffer` → staging, layout `TRANSFER_SRC_OPTIMAL`,
   - buffer `TRANSFER → HOST` memory barrier,
   - restore **only the copied subresource** `TRANSFER → ALL_COMMANDS` (`plan.after`) — the shared image
     layout tracker is deliberately not updated here.
5. `nvmtl_vk_submit_wait_at(&c, "image readback")` submits and waits.
6. On failure: retain the staging allocation (quarantine) unless it is a known pre-submit error `rc == -1`
   while the backend is healthy; CPU destination left untouched.

Fence timing: `pvkWaitForFences(..., 250 ms)` polling loop; WindowServer budget is **5000 ms**; on timeout
the backend is disabled and in-flight resources are not retired (`nvmtl_vk_submit_wait_at`, ~line 5437).
Uploads use a separate image `up_token` handle finished by fence wait (~lines 6025–6062).

---

## 7. Kernel diagnostics already added (kernel 1.0.9)

While `capture_engine` owns the request reference from `intel_engine_get_hung_entity`, it records:
fence context/sequence/flags/error; readiness/active/started/completed states; pending submit dependencies;
hardware breadcrumb; GuC ID + scheduling snapshot; LRC address; ring/batch GPU virtual addresses. It also
prints the already-owned **parsed GuC node** bounded to 3 lists × 64 registers per list/engine, and
explicitly reports absent capture.

It does **not** traverse live request lists, allocate, wait on the GPU, add MMIO reads, request a new
capture, or alter GuC scheduling/reset/timeouts. The 438-object link and undefined-symbol set are
unchanged vs 1.0.8.

Caveat: legacy `engine->head/tail/start/acthd` fields can still appear and are zero placeholders under GuC
capture — they do not mean "idle ring".

---

## 8. Memory model facts (do not re-derive from scratch)

- MTL distinguishes **DSM** (device physical addresses), **GSM-relative PTE offsets**, and **GGTT** virtual
  addresses. A plane's GGTT address indexes a page table.
- Prior work: DSM starts 8 MiB above GSMBASE; MTL GGTT PTEs for local memory use GSM-relative offsets.
- `Wa_22018444074`: BAR access to stolen memory can hang MTL, so direct GSM/DSM access is used when
  firmware reports permission (permission read at `0x138914`).
- No allocation overlap has been demonstrated in the available captures. The GT scratch path explicitly
  avoids its stolen fallback. GGTT/plane registers have **not** been modified.

---

## 9. What has been ruled out (do not re-propose)

| Hypothesis | How excluded |
|---|---|
| Kext not injecting | Injection `- Success`; `NMXGPU` UUID matches candidate on target |
| Missing GPU opt-in | Opted-in boot evidence shows panel claim + framebuffer load success |
| Universal readback defect | Readback #3 completes on the same boot |
| `INTEL_DEBUG=stall` | Enabled on a failing boot (0.2.5); did not cure it — recorded **negative** |
| Timeout too short | Hang is a progress failure; extending the fence cannot restore execution |
| Firmware version mismatch | Loads GuC 70.53.0, matching the Linux report on both GTs |
| Host-lock contention | 0.3.2's unbounded mutex was bounded; hang persisted |
| Pool reuse | Fresh pools enforced; hang persisted |
| Readback staging reuse | Dedicated fresh staging; hang persisted (0.3.4, submission #8) |
| Xe2/Xe3 workarounds | Different generation; `has_flat_ccs=no` here; explicitly not applicable |
| External-host import refusal as sole cause | First fallback upload **and** readback both completed |

---

## 10. Hard constraints on any proposed fix

1. **No guessed register values, quirk values, or ACPI scopes.** If it is not measured or citable, say so.
2. **No timeout increases, fake completion, manufactured textures, swallowed exceptions, or unsafe frees.**
   These mask the sequence instead of restoring GPU execution.
3. **One variable per experiment**, with a before-state and a rollback. No automatic reboot.
4. **Evidence-first:** every claim needs a log line, a capture field, or a citation (kernel source, Mesa
   source, Vulkan spec, Intel workaround database).
5. **Do not re-run the 22-case application matrix**, and do not treat a passing application matrix as
   desktop evidence.
6. **Meteor Lake ≠ Panther Lake.** Do not import Xe2/Xe3 SR-IOV/VF or flat-CCS workarounds.
7. **No blind firmware swap**, no GGTT/plane rewrite without demonstrated overlap/fault evidence.
8. Preserve the passing application baseline and third-party licences.

---

## 11. What we want from you

For each item: a ranked hypothesis, the evidence for/against it in §5, a **minimal discriminating
experiment**, and exact code/register locations with sources. Distinguish "GuC never scheduled/dispatched
the context" from "context dispatched but hardware stopped".

Specific questions:

1. In i915 GuC submission, what condition leaves a context permanently **"not started"** (`0x1002`) while
   earlier contexts on the same engine completed, and the engine later reports a hung rcs0 context? Which
   fields distinguish blocked-on-dependency vs never-dispatched vs hardware hang?
2. Could the **external-host import refusal + private-image fallback** produce two aliases for one surface
   with divergent layout tracking, so a later readback waits on a layout transition that never occurs?
   How would we detect that from the plugin + kernel logs?
3. Does ANV insert any dependency (semaphore, batch, layout transition, aux/CCS metadata) for
   `storageModeManaged` / Metal-mapped IOSurfaces that the plugin's own recorded barriers do not model? Is
   `noccs` the right isolation for that, and what would prove or disprove it?
4. On MTL (`has_llc=no`, `has_snoop=yes`, `has_flat_ccs=no`), are there known i915/GuC workarounds for
   concurrent readback + display composition that this port may be missing (GT workarounds, `Wa_*`, CDCLK,
   forcewake, RC6/DC state interactions)?
5. Can the display-pipe / AGDC frame-copy path and the render/compute queue (different GuC contexts)
   deadlock or starve each other on MTL?
6. Any known GuC **70.53.0** defects relevant to context dispatch/descheduling on MTL?
7. Given the port can only add bounded, non-intrusive capture, what is the best next real signal to
   collect: GuC CTB/G2H tail/head, context descriptor state, schedule state, or engine CSB/breadcrumb?
8. Is there a genuinely better architecture for this surface path than the current copy-to-staging
   readback (e.g. mapping the IOSurface allocation directly, or using a different layout/queue-family
   strategy) that avoids the observed stall?

Deliverable we can act on: patch-level guidance for **i915-on-LinuxKPI** (FreeBSD `drm-kmod` base
`c16de0f9fa84f70b9551f69fde837a7f3a73c0e9`) and/or **Mesa ANV 26.3.0-devel**, plus the exact log line or
capture field that would confirm or falsify each hypothesis.

---

## 12. Evidence artifacts available on request

- `research/verified-windowserver-20261019-1200.md` — the 12:00 failure, submission by submission.
- `research/windowserver-0.3.5-research.md` — 0.3.4 failure, kernel capture audit, `noccs` rationale.
- `research/windowserver-0.3.4-research.md` — source-audit table across pools/staging/publication/memory.
- `research/verified-0.3.1-full-gate-20261019.md` — the 22-case / 26,000-frame control.
- `research/verified-0.3.1-guc-wake-fix.md` — reproduced LinuxKPI lost-wake race and its fix.
- `ROADMAP.md`, `README.md` — full candidate history 0.2.4 → 0.3.5 and current status.
- Raw report directories under `Desktop/reports/` on the target (WindowServer `.ips` crashes, `log show`
  windows, plugin `first-submit:` traces, kernel request/GuC capture).
