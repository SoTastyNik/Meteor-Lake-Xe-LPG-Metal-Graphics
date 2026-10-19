# Latitude 5350 GPU port — revised roadmap

Updated 18 October 2026 after desktop candidate 0.2.5, report `20261018-194932`. Target: Dell Latitude 5350, Core Ultra 5 135U, Intel 8086:7D45 / Dell 1028:0CB6, Sequoia 15.8.1 (24H32).

The next milestone is a repeatable, correct image readback under the actual Intel runtime. Another bootable desktop candidate is not evidence of progress by itself. The current blocker is GPU execution/lifetime/synchronization during the desktop workload; registration already works.




## Candidate 0.2.9 effective-policy repair prepared

The latest 0.2.8 test (readback-20261018-231611) hit GPU HANG 12:1:00b79797 at frame 169. It does not test fresh pools: release initialization stripped NVMTL_* settings, including the experimental flags and direct diagnostics. The policy file only recorded intent. No conclusion about pool reuse is justified.

The fix narrowly preserves explicit controls for the named test process and adds an in-driver effective-policy query. Each workload refuses to run unless the actual post-initialization policy matches the requested profile. Tests against the real native release plugin constructor passed for all three profiles, unrelated controls and another process. Desktop activation remains disabled; target validation remains pending.

Next: install-readback.sh, reboot USB, then diagnose-readback.sh fresh-pools. No GPU-hang cure is claimed.


## Candidate 0.2.8 diagnostic comparison prepared

Recovered 0.2.7 evidence confirms GPU HANG 12:1:00b79797 and readback VK_ERROR_DEVICE_LOST after 13,072 ms, followed by a context reset. IOKit access passed; correct WindowServer remains unverified.

The USB now contains plugin 0.2.8 with direct per-test diagnostics and a command-pool-only fresh-allocation switch. The same three warmups precede a single retained/fresh-pool/fresh-staging comparison. Witnesses and address-page caching stay on in the fresh-command-pool case. The runner checks boot UUIDs and refuses another comparison in the same boot. Kernel events are captured live and historical lookup starts at the current run. Desktop activation is disabled in this candidate; no GPU-hang cure is claimed.

Next target step: install-readback.sh, reboot USB once, then `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools`. Return the first report before selecting the next clean-boot variant. Further variants require prepare-readback-boot.sh and a USB reboot. Full instructions: Desktop/README.md.


## Candidate 0.2.7 prepared — target validation pending

0.2.6 passed all 10 direct cases on the Dell (1,200 frames, report 20261018-201754). Forced IOKit failed during enumeration before any ioctl. The new candidate fixes inconsistent forced-route enumeration and token node classification, adds automatic IOKit discovery fallback, and corrects prior-access synchronization during IOSurface reuploads. It also fixes the release filter prefix so image/staging traces are retained.

The revised suite tests IOKit first, probes metadata and nested-pointer ioctls, and checks actual RGBA/BGRA IOSurface backing pixels immediately after GPU completion. `test-and-arm-desktop.sh` runs 1,000 iterations across 22 cases and enables ONE desktop boot only if all cases pass. It does not reboot automatically. Use install-readback.sh, reboot USB once, then test-and-arm-desktop.sh. Details: Desktop/README.md.

Local ASan/UBSan routing/discovery/barrier/failure tests and native Apple M4 harness checks pass. They do not establish Intel IOKit correctness or WindowServer success. Both still need the target test. Shared-image recording concurrency and broader display features remain unverified.


## Candidate 0.2.6 prepared — Intel tests pending

The readback correctness patch and isolated test matrix are on the USB. Local ASan/UBSan recording/error tests pass. Native Apple M4 exact-pixel tests validate the harness only. Default installation is now readback-only; physical panel ownership is disabled for the next GPU application test. Automatic WindowServer `INTEL_DEBUG=stall` was removed after its failed target result.

Run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh` on the Dell. After exit=0, reboot USB once and run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh`. Reports go to `Desktop/reports/readback-TIMESTAMP`. The 100-iteration smoke test comes before the 1,000-iteration gate and another desktop attempt.

Implemented: validated full/region readback, transfer-write/host-read dependency, copied-subresource layout restoration, coherent-memory verification, timeout retention, image/stage identities, dedicated-staging option, deterministic raw/render/IOSurface tests, controlled two-thread cases, verified direct/IOKit route counters.

Pending: target results, broader render/compute/blit image-state concurrency, synchronization validation, conditional kernel-request/GEM correlation, desktop stability and later display features. Artifacting and full acceleration are not confirmed fixed.

## Evidence and corrected status

| Milestone | Current evidence | Status |
|---|---|---|
| Real GPU identification | macOS probe and Linux report agree on 7D45 | Confirmed |
| Application GPU output | Earlier Vulkan/Metal compute and 4096-pixel render checks passed, including report 20261018-145513 | Limited passing coverage; broad stability unverified |
| Physical framebuffer and scanout adoption | Custom framebuffer loads, describes 1920×1080, reaches fixed scanout | Initialization confirmed; correct desktop pixels unverified |
| Accelerator/display registration | 0.2.4 and 0.2.5 verify existing pipe 0, phase 2 complete, pipe active | Confirmed initialization |
| Desktop workload execution | First four 0.2.5 submissions complete; #5 readback and #6 upload time out | Blocking failure |
| WindowServer failure handling | Prior stack-overflow signature absent; terminal error buffers exercised; WindowServer still aborts on pipeline/backend failure | Partial improvement, not recovery |
| Correct accelerated desktop | Presentation samples remain zero; visible artifacts reported | Failed/unverified |
| Sleep, brightness, external outputs, video decode | No relevant passing evidence | Deferred |

The active 0.2.5 boot starts at 19:46:56; the collection is from the fallback boot at 19:48:57. A fallback Vulkan failure does not retest the active GPU. `desktop exit=0` only says the small window test ran; it is not proof of acceleration. `NMXDisplay=armed` is driver state, not a pixel-correctness result.

Machine-readable evidence: `research/desktop-roadmap-evidence.json` on the build Mac, copied to `iGPU-Port/desktop-roadmap-evidence.json` on USB. Plugin submission IDs and i915 request sequence numbers belong to different namespaces and must not be equated without correlation.

## What the research changes

### 1. Treat readback as the first observed failure, not yet the proven cause

In 0.2.5, upload #1, command-buffer work #2, readback #3 and command-buffer work #4 complete. Readback #5 is accepted by Vulkan but its fence never completes within five seconds. Main-thread upload #6 also stalls. The later render-engine hang confirms this is more than a presentation-only defect. We still lack the image/staging identity and the exact lower-level request dependency associated with #5.

Do not conclude that every readback is broken: #3 passed. Do not assume #3 and #5 reference the same image: the current trace does not establish that.

### 2. Audit resource synchronization before adding more global flags

`NullMoth/plugin/nvmtl_vk.c`, `nvmtl_vk_image_read`, transitions the image and copies to a mapped staging buffer, then waits and reads the CPU mapping. The function does not record an explicit transfer-write → host-read dependency. Khronos' readback examples include a host-read dependency, a completion wait and, where required, mapped-memory invalidation. This is a concrete correctness gap to address in a focused patch, but it does not explain a pre-read fence timeout by itself. [Khronos synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html#cpu-read-back-of-data-written-by-a-compute-shader)

The regional readback function uses a fragment-read source scope and the common `img_to` helper, which covers all mips/layers using one layout field. Audit render-target writes, transfer writes, compute writes and mixed subresources. A barrier's old layout must agree with the affected subresource. [Image-memory barrier requirements](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageMemoryBarrier.html)

`img->layout` is updated while recording. Trace recording and submission order separately, especially between the main thread and execution worker. The IOSurface monitor already serializes SurfaceIn/SurfaceOut for wrappers sharing a surface/plane; the question is whether all GPU encoding that uses the same image participates in a sufficient ownership scheme. Adding a global lock around waits could create a new deadlock and is not a substitute for that audit.

### 3. Separate lifetime/reuse tests from synchronization tests

The trace reuses command-buffer addresses. That is not proof of reuse while pending. The source frees a completed command buffer before caching its pool; later allocations may receive the same address. Verify generation/ownership and completion, rather than treating pointer equality as a bug. Vulkan forbids freeing pending command buffers and requires host synchronization of their pool. [Command-buffer lifetime requirements](https://docs.vulkan.org/refpages/latest/refpages/source/vkFreeCommandBuffers.html)

Uploads and readbacks have distinct thread-local staging helpers. Thread-local allocation reduces direct sharing but does not prove safety for reentrancy, backing-allocation reuse, image destruction or timeout cleanup. Record these lifetimes explicitly.

### 4. Use the laptop's Linux evidence to constrain kernel experiments

USB evidence under `Dell-0TCMF9_Ultra-5-135U_Intel-Graphics_20261012-1904_698f` identifies graphics 12.70, stepping B0, `has_llc=no`, `has_snoop=yes`, `has_flat_ccs=no`. Its kernel log loads GuC 70.53.0, DMC 2.23, HuC 8.5.4 and GSC 102.1.15.1926, matching the selected firmware family/versions.

This makes cache-policy implementation worth auditing, but does not prove a coherency fault. It also means that Xe2/Xe3 flat-CCS remedies and Panther Lake VF power/firmware settings should not be copied onto this physical Meteor Lake device. Linux initialization is reference evidence, not a substitute for a matching rendering test.

The recorded zero fault/ring fields are incomplete capture data. They do not prove fault-free memory access. The current summary omits command-stream content and portions of GuC context capture. Upstream keeps additional state for GPU-hang analysis. [Linux i915 capture source](https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/i915_gpu_error.c)

### 5. Record negative experiments accurately

`INTEL_DEBUG=stall` was actually enabled on the failing 0.2.5 boot. It did not cure the hang. Keep it as a recorded negative result, not a proposed next fix. Mesa describes `stall`, `sync`, compression and queue controls as diagnostic experiments; none is a general guarantee of correctness. [Mesa ANV debugging guidance](https://docs.mesa3d.org/drivers/anv.html#debugging-tips)

WindowServer's original recursive stack exhaustion changed to a pipeline-creation abort after backend shutdown. Terminal-error command buffers do not restore the GPU or provide working desktop recovery. Further placeholder pipelines or fabricated success would conceal the original failure rather than repair it.

## Implementation sequence and promotion criteria

### A. Build an isolated readback reproducer — next priority

Use the actual NVMTL/ANV/i915 stack, with a firmware desktop and no custom panel ownership. Prepare the tool before requesting a target boot. Do not run the whole workload against a GPU already hung by WindowServer.

The tool should upload a deterministic frame pattern, render a deterministic modification, read back, and compare every expected pixel. Use 64×64 first, then 1920×1080 at pitch 7680, padded-row variants, and repeated frames with changing seeds. Exercise single-thread sequential operations before two controlled threads. Log a compact pass/failure summary and retain the first failure.

It must support one-variable cases: fresh versus reused command pools, fresh versus retained staging, and direct devfs versus forced IOKit transport. A call named `drmNmxIoctl` does not prove IOKit was used: it initially tries the device-file ioctl. Log and verify the actual route. A forced route needs explicit test support; it is not currently a ready-made switch.

Recommended pass criterion: exact output for 1,000 iterations per selected case, no hang/reset and no unexpected growth in retained GPU allocations. This is a project test threshold, not proof of general stability. Fail fast on a GPU timeout; do not keep submitting to the same stopped backend.

### B. Make a focused readback correctness patch

Add the transfer-write → host-read dependency and verify coherent versus noncoherent handling. Validate image aspect, sample count, usage, dimensions, row pitch and subresource bounds before issuing the copy. Use the actual producer's stage/access scope and affected mip/layer; do not broaden every transition indiscriminately.

Trace image and staging logical IDs plus generation, memory type/coherency, layout before/after recording, submission ID, thread and completion. Record retire/free/reuse events. Add a thread-safe ownership scheme only after establishing which paths share an image and how recording order relates to submission order.

Promotion criterion: the isolated suite passes and synchronization validation reports no relevant errors where a compatible validation layer is available. First verify that the layer loads and receives a deliberate test violation. A debug-utils messenger alone is not a Vulkan validation layer.

### C. Use controlled experiments to assign the remaining failure

| Isolated result | Next investigation | Evidence required |
|---|---|---|
| Single-thread, fresh resources still fail | ANV/i915 transfer command and mapping path | Exact copy parameters, GEM objects/addresses and first GPU error |
| Reuse alone causes failure | Pool/staging lifetime and generation | A resource reused/freed while pending, or a repeatable fresh/reused A/B result |
| Two threads alone cause failure | Image-state ordering and queue/host ownership | Same logical resource and a conflicting recording/submission sequence |
| IOKit alone causes failure | ioctl ABI, task/mm identity, copyin/copyout and mapping | Same workload, verified route difference, first differing ioctl/result |
| Raw transfers pass but render/readback fails | Render state, layout/decompression and shader workload | First failing render-to-readback transition, not a later cascading error |
| Isolated stack passes but WindowServer fails | IOSurface identity/lifetime and compositor-specific operations | Resource-correlated trace reproducing the isolated success versus compositor failure |

Do not change firmware, multiple debug flags and memory policy in the same comparison. Keep the confirmed registration correction and recovery mechanism while isolating one factor.

### D. Expand kernel capture if userspace evidence does not settle the cause

Correlate the failing submission to GEM handles, context/VM, batch address, i915 request sequence and its wait dependencies. Capture whether GuC queued, scheduled, started and completed that request, plus relevant capture-list validity. Interpret CT head/tail values in the proper send/receive ABI; raw unequal values are not sufficient to diagnose a broken queue.

Export the retained first error through a bounded read-only path from a safe worker context. Avoid full coredump serialization, large allocations, live register pokes or filesystem writes in reset-critical paths. Preserve the first error rather than overwriting it with later process-restart failures.

### E. Return to a single desktop boot only after readback is reproducible

Use the known panel mapping and registration code. Confirm the online display's accelerator association, WindowServer's actual plugin/transport, advancing successful transaction counts and frame numbers, and visible correct output. Zero samples and an `armed` property do not pass.

Investigate the extra firmware framebuffer separately if it still interferes with CoreDisplay. Preserve a working fallback; do not remove it as an unmeasured attempt to fix a readback GPU hang.

Initial desktop acceptance: correct login/window drawing and a changing known colour pattern; ten minutes of movement/resize without artifacting, timeout, reset or WindowServer restart. Repeat on three cold starts. These are proposed milestone thresholds, not a claim of complete compatibility.

### F. Broaden support after the desktop milestone

Then test ordinary Metal/OpenGL applications, memory pressure, repeated application exit, lock/unlock and multiple displays. Modesetting, brightness, hardware cursor, sleep/wake, video acceleration and power management remain separately scoped work. Each needs its own evidence; passing compute/render tests does not certify those features.

## Immediate deliverables and boundaries

1. Readback reproducer and resource-correlated trace.
2. Focused synchronization/subresource patch with local tests.
3. A documented isolated experiment matrix and retained first-failure bundle.
4. A desktop candidate only after the relevant isolated gate passes or yields a specific kernel defect requiring that test.

No new driver binary, firmware, security setting or active EFI configuration was changed during this roadmap/research revision. No reboot or reinstall is requested now. The deployed 0.2.5 candidate remains a failed desktop experiment. A successful end state cannot yet be promised, and the root cause remains open.
