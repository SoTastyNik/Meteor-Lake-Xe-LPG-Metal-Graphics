# WindowServer investigation and candidate0.3.4

## Conclusion and boundary

The latest physical desktop failure is a GPU execution/progress failure. It is not explained by a missing GPU opt-in, and the later CoreAnimation/CoreDisplay exceptions are not evidence that a shader compiler error was the initial cause. A complete desktop fix has not been demonstrated. No software-only review can guarantee every future WindowServer error, and this candidate requires one real Dell desktop boot.

Candidate0.3.4 makes one controlled GPU-workload change: each8086:7d45 WindowServer readback uses a dedicated fresh allocation rather than TLS-retained staging. It also corrects three observed diagnostic defects. This removes a reuse variable at the failure site; the logs do not prove staging reuse caused the hang. Kernel/firmware/display changes without a demonstrated fault would obscure the next result.

## Evidence correlated across both operating systems

Report failure-detail-20261019-130037 contains an actual opted-in boot, UUID43CADE8D-A3E3-46D8-88F6-3CBD2AE93D0C. Panel claim activated, framebuffer load returned0, and candidate0.3.3 plugin SHA matched the installed binary. The first eight logged submissions completed, including three fullHD readbacks. Readback4 on image2/staging12 began12:58:50.085. At12:58:55.086 it returned VK_TIMEOUT after5000ms. Backend shutdown retained uncertain resources and left CPU output untouched.

The kernel subsequently reported an rcs0 hung context with request8:24 [0x1002] not yet started, then GPUHANG12:1:00dfffff at12:59:03.867. The capture reports GTawake1, resets0 and zero EIR/PGTBL/fault snapshots; those values do not prove a healthy engine or identify the failing address. A not-started request may be blocked behind earlier work; it is not proof that its image copy instruction is itself defective.

WindowServer PID163 terminated at12:59:04 with CoreAnimation pipelinePBGRAXb_Xh / Vulkan not up. Restarted processes timed out in dummy zero-fill, then CoreDisplay texture creation failed and crashes followed12:59:10/21. Changing shader compilation to report success, manufacturing textures after failure or extending waits would mask this sequence rather than restore GPU execution.

The provided Linux report Dell-0TCMF9_Ultra-5-135U_Intel-Graphics_20261012-1904_698f identifies1920x1080 panel operation and GuC70.53.0 on both GTs. The macOS failed boot also loads mtl_guc_70.bin70.53.0 with GuC submission enabled. That is not proof of identical kernel behavior, but provides no evidence that merely replacing the firmware version is the needed fix.

The application baseline remains22cases/26,000frames and80,020pools reclaimed, with both IOKit and direct routes and a fresh-staging case on each. This supports reusing its dedicated-allocation mechanism for the next desktop trial; it does not validate sustained physical composition. Earlier application passes are retained and are not rerun.

## Source audit and hypotheses

| Area | Finding | Decision |
| --- | --- | --- |
| Command pools | Actual normal/prologue/counter/dummy pools use the fresh tracked allocator; retirement checks fence/witness; uncertain work stays quarantined. | Preserve. |
| Host serialization |0.3.3 wrapper bounds recursive lock entry, then submits and waits. Latest report shows GPU fence timeout and hang, not a recorded host-lock timeout. | Preserve; do not call serialization a complete cure. |
| Readback staging | Thread-local buffer retained across copies; fourth readback reuses stage12. Dedicated mode3 allocation already bypasses pool suballocation and parked-buffer reuse. | Force dedicated mode only for this WindowServer/device. |
| Cleanup | Existing readback retained allocation for every submit error, including known pre-submit errors. | Free owned staging only for rc=-1 while backend is healthy; retain on uncertain rc=-2/backend shutdown. Normal completion frees after CPU copy. |
| Surface publication | Surface copy-out occurs after rendering; failed copy-out does not advertise successful publication. Scheduled deferral is retained. | Preserve. It does not establish all private display consumers honor that ordering. |
| Image dependencies | Readback emits image dependency, image-to-buffer copy, transfer-to-host barrier and restored subresource layout before completion/CPU consumption. Shared image layout tracking across independently recorded work remains an audit risk. | Preserve current barrier semantics in this controlled trial; do not assume submission serialization alone solves arbitrary recording races. |
| Physical display memory | CPU panel copies coincide with early desktop work. MTL distinguishes DSM physical addresses, GSM-relative PTE offsets and GGTT virtual addresses. No allocation overlap is demonstrated in the available capture. MTL GT scratch code explicitly avoids its stolen fallback. | Do not rewrite GGTT/plane registers or reserve guessed memory ranges. If fresh staging still hangs, require address/allocation and request-progress evidence for this branch. |
| GuC/LinuxKPI | Existing wake-race repair and26k pass are retained; GuC context dispatch remains a possible failure layer. | Do not import Xe3 VF-only workarounds as MTL fixes or change firmware blindly. |
| Process/thread lifetime | Port already holds Mach-task references and includes its LinuxKPI adaptations. Restart crashes occur after the GPU is lost. | Keep primary failure and restart fallout separate. No claim of exhaustive lifetime correctness. |

## Implemented diagnostic repairs

1. WindowServer's direct journal writes are denied by Sandbox file-write-data, errno1, even though the installer pre-creates the file with correct ownership. The plugin now sends bounded stage records through its existing syslog channel; the root loader already streams these events and flushes the retained live log. No sandbox/SIP change is required. Root loader/journal heartbeat capture remains separate.
2. nvlog's per-format eight-message throttle hid queue/fence records after submission8, despite the caller's finite first24 budget. WindowServer startup first-submit messages now bypass that per-format drop. Their caller-side budgets remain; ordinary application/failure throttling remains. Stage records have their own256-call limit and Vulkan-once tracing covers only the first four calls.
3. sample(WindowServer-name) returned0 while reporting pid_for_task failure/process0 and produced no stack file. The loader now resolves an explicit positive PID, refuses PID0/1, and records failure when output is missing or stderr reports the observed task failure. A denied sample is retained as an error, not a successful capture. No task-port restriction is bypassed.

Root logging remains best effort: fsync/F_FULLFSYNC can block, and power loss can still lose data. Syslog forwarding also relies on the OS being able to deliver events. The new bounded record volume avoids indefinite per-frame logging; it is not a guaranteed crash-proof recorder.

## Local validation and hardware acceptance

The actual readback implementation under ASan/UBSan checks barrier/copy/restore/wait order, exact padded copies, invalid/noncoherent inputs, failed recording, timeout keeping CPU output untouched, normal cleanup, known pre-submit cleanup, backend-lost retention, process/device scope and20,000balanced dedicated allocation/reclamation cycles. These are mocked Vulkan calls, not20,000hardware frames.

The actual release logger fixture verifies all24startup submissions survive the old eight-format throttle,256stage cap and unchanged application throttling. Loader fixtures cover active/fallback/load error plus sample exit0-without-file, task-failure/process0 output and PID0. Installer fixtures verify immutable-baseline guards and rollback of plugin/loader/helper on verification, journal preparation or partial arming failure. Native release policy and80failed-command-buffer checks remain applicable. Release x86_64 compilation/signature and final USB hashes are checked during packaging.

Next hardware action: install-windowserver.sh from the Dell fallback desktop, then afterexit0 reboot through USB once without ResetNVRAM. Do not repeat the full22-case suite. If black/frozen/artifacting, poweroff/USBfallback and collect-desktop-failure.sh before reinstalling. If visible, collect on that same boot before further changes. A pass requires evidence that the candidate activated, the desktop remains responsive, real frames are presented, and no GPU/fence errors occur. A visible fallback desktop is not a pass.

If this still fails, the next branch is targeted kernel request/dependency/GuC progress capture correlated with the now-complete startup submissions, then physical memory ownership/layout investigation. It is not another identical reboot, longer fence timeout or repeat of the application matrix. Longer session, application launching, sleep/wake, modesetting and error recovery remain unverified desktop behaviors; no future-proof claim is made.

## Primary research references

- [Vulkan synchronization and layout rules](https://docs.vulkan.org/spec/latest/chapters/synchronization.html): execution order alone is insufficient for all data hazards; layout/dependency scopes matter.
- [Vulkan memory retirement rules](https://docs.vulkan.org/refpages/latest/refpages/source/vkFreeMemory.html): pending commands must complete before referenced memory is freed. This underpins retained/quarantined failure paths.
- [Vulkan queue submission](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueueSubmit.html): queue order and host synchronization requirements are distinct from completion.
- [Mesa ANV hang debugging](https://docs.mesa3d.org/drivers/anv.html): sync/stall/compression/queue controls are diagnostic isolation tools, not proof of a root cause. No new INTEL_DEBUG flags are applied here.
- [Linux i915 architecture](https://docs.kernel.org/next/gpu/i915.html), [v6.14 GuC submission source](https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c), [v6.14 GT scratch source](https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/gt/intel_gt.c): distinguish dependency/dispatch/completion, inspect MTL-specific allocation behavior.
- [Apple managed-resource synchronization](https://developer.apple.com/documentation/metal/synchronizing-a-managed-resource-in-macos), [Apple file flushing](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html).
- [Original render-driver project](https://github.com/VedCloud2/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS) and [Xe3 VM reference](https://github.com/ericek111/vibe-nullmoth-xe3-qemu). The latter uses Panther Lake SR-IOV/xe, Tahoe and virtio/QEMU scanout; it is architectural reference material, not evidence of this MTL/i915/eDP path working.
