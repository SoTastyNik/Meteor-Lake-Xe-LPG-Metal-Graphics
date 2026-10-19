# Latitude 5350 desktop failure: source and log investigation

Investigated 18 October 2026. Target: Dell Latitude 5350, Meteor Lake 8086:7d45 / 1028:0cb6, macOS Sequoia 15.8.1 (24H32). Experimental desktop candidate 0.2.3. Report: `/Volumes/SEQOUIA/iGPU-Port/Desktop/reports/20261018-184026`.

## Findings grounded in the target log

The failed boot is 18:38:13; the fallback boot is 18:39:55. These must not be treated as one test. `panel-boot-loader.txt` records successful framebuffer start/match at 18:38:20 and a deliberate skip on the fallback boot. The Vulkan failure collected after 18:40 does not retest the failed boot's active GPU.

`driver-after-tests.txt` retains the earlier boot:

| Local time | Evidence | Interpretation |
|---|---|---|
| 18:38:19.081 | NMXAccel starts | Accelerator attachment progressed |
| 18:38:19.325 | Display phase 1; AGDC result 0 | Display preparation callback succeeded; not proof of composition |
| 18:38:19.332 | newDisplayPipe | A display pipe object was created |
| 18:38:20.459 | initFramebufferResource, head 0, live scanout 0x60800000, 1920x1080, pitch 7680, 8294400 bytes | Framebuffer resource construction reached the physical panel buffer; correct pixels and safe GPU access remain unproven |
| 18:38:20.459 | found_framebuffer, count 1 -> 1 | An existing pipe may already be registered; count did not increase |
| 18:38:20.459 | phase 2 reports no display pipe | Local bookkeeping did not mark head 0 as piped; this message alone does not prove no pipe object exists |
| 18:38:36.667 | rcs0 request 8:16 not yet started | Render queue stopped making expected progress |
| 18:38:36.744 | GPU HANG: ecode 12:1:00dfffff | Actual GPU hang, separate from the registration diagnostic |
| 18:38:44.091 | Fence expiration timeout | Work remained incomplete |

No passing accelerated-desktop result is present. The coloured-window program returning zero only means that its drawing/movement sequence completed on the fallback desktop.

## 1. Registration has a concrete bookkeeping defect

Local source: `NullMoth/kexts/NVRM/accel/nvrm-accel.cpp`, `registerPendingLocked`, approximately lines 398-453; `registerFramebufferLocked`, approximately lines 466-484; `nmxArmPhase2Locked`, approximately lines 2503-2518.

The registration code calls the display family's `found_framebuffer`, marks `fFBRegistered` immediately, then requires framebuffer count to increase by exactly one. If count stays unchanged, it stops without inspecting the already-existing pipe. Phase 2 tests `gNvHeadsPiped`, sees zero and exits before its explicit power-on notifications. Subsequent registration attempts skip that head because `fFBRegistered` is already set.

The log's earlier `newDisplayPipe` and `initFramebufferResource` calls make the already-adopted case a strong explanation for this bookkeeping failure. They do not establish that all pipe state is valid.

A correction should look for a pipe whose framebuffer pointer is exactly the intended framebuffer, before adding and after any family callback. Mark the registered/piped bits only after validating that identity. Bound any walk; reject duplicate identities and implausible counts. Do not force the count upward or declare success merely because it is one. Reuse the existing ABI checks rather than introduce guessed offsets. Current code uses reconstructed private Sequoia-family offsets; those are an independent compatibility constraint.

Even a successful phase-2 callback should be logged as registration/power completion, not as proof that WindowServer actually composites with this GPU.

## 2. The hang code is not a root-cause diagnosis

Upstream Linux 6.14 `i915_gpu_error.c` builds the last ecode field from IPEHR XOR INSTDONE. The middle field represents hung engine classes. It is a coarse fingerprint, not a lookup table of hardware faults. Thus a matching number from an unrelated Linux report would not justify applying its workaround.

Source: https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/i915_gpu_error.c (generate_ecode, error_msg, error-state capture).

The next useful evidence is the first retained GPU coredump: fault registers, ring head/tail, command stream, context identity, outstanding requests, GuC state and page-table information. A fence timeout does not establish whether submission, execution, interrupt delivery or memory access failed.

Our port has an error-state visibility gap: upstream exposes the captured state through sysfs/debugfs, while `NullMoth/gpu-port/xkpi/override/i915/nmx_i915_debugfs.c` deliberately supplies empty registration functions because macOS has no debugfs. The normal Linux `/sys/class/drm/card0/error` command is therefore not an available collection method here. A bounded read-only export of the retained first-error object, or a carefully bounded persistent-log dump on the first hang, needs to be designed and verified before another opaque black-screen test. Large synchronous dump work in reset context should be avoided.

## 3. The reference desktop's scanout mechanism is VM-specific

The Xe3 reference explicitly describes Panther Lake SR-IOV, macOS Tahoe, virtio-vga and QEMU blob scanout. It also describes a two-phase display handshake, firmware-framebuffer exclusion, sandbox transports and cache-coherency fixes. Those are useful architectural references, but not validation of Meteor Lake physical display ownership, stolen-memory mapping or Sequoia's private display ABI.

Source: https://github.com/ericek111/vibe-nullmoth-xe3-qemu#part-4-a-gpu-composited-desktop-in-a-vm and its Known issues / Scope sections.

The physical build disables virtio initialization. In the current framebuffer, `scanoutSurface` refuses when virtio is inactive; `nmxIopBlobFlip` only runs when `NMXVirtioScanout` exists. Therefore this build's intended physical presentation path is the existing frame-copy fallback into the fixed firmware scanout. It is not the reference's zero-copy page-flip path. GPU composition with a final CPU copy remains a valid intermediate objective, but it must be measured and described accurately.

## 4. Meteor Lake address spaces must stay distinct

Linux's stolen-memory setup distinguishes CPU DSM address, GPU-local offsets relative to GSMBASE, GGTT virtual addresses and the aperture alias. The candidate's translation checks are consistent with that distinction and reaching the live-scanout callback is useful progress. It does not establish a valid GEM import of those pages or correct lifetime/ownership.

Sources:
- https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/gem/i915_gem_stolen.c (MTL offset and direct DSM setup).
- https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/gt/intel_ggtt.c (direct GSM mapping).
- https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/i915_utils.c (direct stolen-access workaround).

Before enabling further access, audit that the firmware scanout's GGTT and stolen ranges remain reserved against i915 reuse with display discovery disabled. No overlap has been demonstrated in these logs. Do not change live plane registers or overwrite GGTT entries as a diagnostic shortcut.

## 5. Host-import and firmware-display risks need isolated tests

`NVMTLDevice.m` enables imported host-memory IOSurface images on Intel. `nvmtl_vk.c` imports host allocations through Vulkan; Mesa's i915 backend uses GEM_USERPTR. The local MMU-notifier shim explicitly never delivers mapping invalidations. Wiring retains physical pages, but does not by itself make later CPU remapping visible to GPU mappings. This is a limitation to audit for cached IOSurfaces; it is not evidence that a remap occurred during this failure.

Khronos requires the imported range to remain valid for the imported allocation's lifetime and requires synchronization between host and device access: https://docs.vulkan.org/refpages/latest/refpages/source/VkImportMemoryHostPointerInfoEXT.html . Ordinary host allocations and host-mapped foreign memory use distinct handle types. Do not assume every CPU-mappable scanout is a valid ordinary host import.

The source already has a diagnostic switch `/var/db/nvmtl-no-host-surface` to use private images and copies instead. It is a useful later controlled A/B test, after registration and collection are reliable; it does not disable every possible host-pointer import in the plugin.

The fallback report exposes two IONDRVFramebuffer objects, including `.Display_boot` created through the firmware-display route. The Xe3 reference reports that an extra pipe-less firmware display can prevent its IOPresentment path. We do not have the failed boot's complete framebuffer registry, so we cannot assert that both existed during that boot. Capture the full IOService display tree during the experimental attempt before deciding whether to suppress the extra display. Preserve fallback boot functionality.

## Next experiment, in order

1. Retrieve the missing WindowServer/NVMTL logs for 18:38:00–18:39:50 from the installed Dell's retained unified log. This can be done from the working fallback boot, with no reinstall or reboot.
2. Prepare a narrowly scoped registration correction and validate the existing-pipe case, fresh-registration case, refusal, mismatched framebuffer and retry behavior. Keep runtime and EFI recovery mechanisms intact.
3. Add a bounded way to persist the first GPU error state and active-boot framebuffer/accelerator registry before the test can fail. Do not rely on a five-minute tail collected after reboot.
4. Only then run a single controlled desktop attempt. If it hangs, analyze its first error state; isolate IOSurface host imports as a separate experiment rather than changing several variables together.

Success requires a usable panel, a Metal device associated with the online display, WindowServer loading the intended plugin, completing display transactions with advancing counters, correct pixels under movement, and no GPU hang during the observation period. Registration logs alone are insufficient.

No driver binaries, installed target files or EFI settings were changed during this research pass.

## Addendum: retained failed-boot detail collected at 18:53:55

New report: `/Volumes/SEQOUIA/iGPU-Port/Desktop/reports/failure-detail-20261018-185355/failed-boot.txt`. Search exit=0; 7,569 lines / 975,257 bytes. It covers the requested failed boot without requiring a new experimental attempt.

- Line 5312: the display-pipe user client was created successfully. Line 5333: CoreDisplay reports a framebuffer created. This reinforces that the driver's phase-2 "no pipe" message is not a reliable inventory of actual family objects.
- Lines 5352-5360: GPUWrangler lists an additional `IOService:/AppleACPIPlatformExpert/display/IONDRVFramebuffer`, without PCI, AGDC or accelerator association. Opening that firmware framebuffer fails with 0xe00002be. The previously hypothetical extra firmware display is now confirmed in the failed boot, although its contribution to the hang is still unproven.
- Lines 5996-5998: WindowServer pid 163 executes NVMTLDriver code. Vulkan refuses imported host allocations of 8,355,840 and 8,294,400 bytes. The plugin explicitly selects private-image/copy fallback for the first surface (0 successful host-surface imports, 1 refusal). A second surface also fails import at lines 6068-6069. Therefore these particular surfaces did not successfully enter the zero-copy host-image path. Disabling that path alone cannot be assumed to fix the failure because fallback was already attempted.
- Lines 6110-6129: at 18:38:28.425 the fallback upload fails; buffer creation and command-buffer begin then fail repeatedly. The diagnostic reaches at least 28,672 command-buffer failures within about 38 ms. These log messages do not include the underlying VkResult, so they cannot distinguish device loss, allocation failure or another cause.
- Lines 6130-6150: at 18:38:28.466 the kernel records a WindowServer corpse; a new WindowServer pid 351 starts at 18:38:28.519. This establishes a process exit/restart, but this report does not contain the exception type, crash backtrace or exit reason. Several accelerator resources remain locked during cleanup, according to the family diagnostics.
- Line 7461: the first explicit GPU HANG message is later, at 18:38:36.744. The GPU may have stopped progressing before detection; chronological message order does not prove the WindowServer exit caused the GPU hang.
- Lines 7548-7549: the replacement WindowServer also encounters readback/upload failures. Line 7552: another GPU HANG is reported.

Revised priorities: fix registration identity bookkeeping; obtain WindowServer's corresponding DiagnosticReports crash file and preserve the exact VkResult at import/upload/submit/wait failure; retain first-GPU-error details; then evaluate the extra firmware framebuffer with fallback recovery intact. The plugin being loaded proves WindowServer attempted to use this implementation, not that it produced correct accelerated desktop frames. No additional reinstall is needed to establish these findings.
