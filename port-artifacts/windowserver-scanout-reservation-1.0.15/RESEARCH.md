# GPU startup correction candidate 1.0.15

The latest full boot log reveals an earlier failure than the previously reported Vulkan enumeration problem. On the 22:19 trial, GuC loads firmware70.53.0 and enables submission, then reports a crash dump and exception at22:19:41.790–.791. i915 reports **Non-recoverable wedged on init** at22:19:41.795. WindowServer's zero-device queries begin later at22:19:43. The kernel's loaded/registered status and successful IOKit calls therefore did not mean the GPU initialized successfully. The prior report overemphasized downstream enumeration; this corrects that assessment.

The same firmware70.53.0 initialized successfully in the supplied Linux report. A speculative firmware replacement or accepting invalid topology is not justified. The working VM uses a different GPU/driver/display path and is not a direct GuC firmware reference for this Dell.

## Change

The previous1.0.13/14 workaround removed stolen regions entirely to protect the firmware panel. That forced internal rings and context objects into system memory. The latest capture confirms stolen=0 rings and an initialization failure. This does not prove that the memory policy alone caused the GuC exception, but it makes that unverified broad workaround a priority to replace.

1.0.15 restores i915's stolen-region setup while protecting the actual firmware framebuffer from allocations. A small IOKit bridge reads IOPlatformExpert's console address, pitch and dimensions. It validates 32-bit pixels, reasonable dimensions, page alignment, minimum pitch and multiplication bounds. The stolen initializer reads the hardware DSM base, verifies that the complete console image fits within usable DSM, rounds its ending offset up to at least64KiB, and starts the existing drm_mm allocator after that prefix. This conservatively excludes both the image and any preceding DSM bytes. It does not invent a topology, memory size or mode ID.

For the saved Dell values, DSM/GOP both start at0x60800000, pitch7680 × height1080 =0x7e9000 bytes. The excluded prefix is0x7f0000 bytes. Previously stolen allocation could start near offset0x1000; an allocation there overlaps the retained image. The new allocator begins after0x7f0000 while retaining the remaining stolen region for internal objects. This proves allocation exclusion in the local model, not that a specific earlier failed ring overlapped this image on hardware.

Invalid/missing console data or a console outside usable DSM refuses this stolen allocator rather than risking overlap. The normal policy for other PCI devices is unchanged. NMXGPU1.0.14 completion-context protection, existing GGTT firmware reservation, and ring diagnostics remain. Two early engine-initialization error paths now log their phase and errno. The collector extracts GuC crash/exception, wedged-on-init, reservation and engine-initialization messages into gpu-initialization-summary.txt so they are reviewed before downstream WindowServer failures.

## Validation and limits

- Actual original stolen initializer, when enabled, reproduces an allocator range overlapping the retained GOP image.
- Actual corrected initializer and bound helper pass ASan/UBSan, including524,288 offset/size cases, rounding, integer overflow, invalid DSM/console, other-device preservation and refusal paths.
- Actual console bridge passes ASan/UBSan with valid geometry and missing/error console, invalid output, alignment, depth, pitch, dimension and overflow cases.
- Four changed kernel sources compile;438-object x86_64 link succeeds. The only added undefined import is IOService::getPlatform, already used by the target framebuffer. The new bridge resolves inside the kernel binary. The candidate is ad-hoc signed and versions/UUID recorded in validation JSON.
- Completion-context sanitizer fixtures remain passing. Integrated desktop installer and kernel helper exercise exact predecessor1.0.14/current1.0.15 identities, cache rebuild, permanent bundle paths, version/UUID validation, transport rollback, kernel/framebuffer/cache rollback and failed arming cleanup. Saved26,000-frame evidence remains unchanged; no full hardware suite is rerun.

Hardware GuC startup and accelerated WindowServer success remain unverified. The initial system-memory-ring failure is not explained conclusively by an allocation-policy correlation. If the new candidate still fails, the initialization summary and phase errors are needed before another change. Prior ring corruption, compositor correctness and physical display output are not declared solved. Framebuffer mode0 warning is left for evaluation after a healthy render engine is established.

## Sources

Primary code reviewed: [Linux6.14 GT initialization](https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/intel_gt.c), [stolen allocator](https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gem/i915_gem_stolen.c), [initial-plane ownership](https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/display/intel_plane_initial.c), local Sequoia IOFramebuffer/IOPlatformExpert headers, and [VM patches](https://github.com/ericek111/vibe-nullmoth-xe3-qemu). Local retained target boot log22:19:41 and Linux dmesg are authoritative for the observed GuC events/firmware on this laptop. No upstream messages or contributions were made.

## Dell procedure

Run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh in the Dell USB fallback desktop. After exit0, restart through the USB once without ResetNVRAM. No22-case suite is needed. If the trial fails, power off, boot USB fallback and run collect-desktop-failure.sh before reinstalling. Do not interpret a successful installer or loaded kernel as successful GPU initialization; first check that the reservation is logged and that GuC did not crash/wedge.
