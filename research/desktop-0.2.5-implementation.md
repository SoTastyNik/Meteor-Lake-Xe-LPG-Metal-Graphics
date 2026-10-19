# Desktop 0.2.5: implementation and validation

Target failure: 19:12 boot in Desktop/reports/20261018-191454. Registration and phase 2 passed. GPU fences timed out; backend shutdown led to nil command buffers, recursive SkyLight RenderEncoder/SetScissor calls and stack-guard failure in WindowServer.

Implemented fix: return a command buffer carrying an encoding error when Vulkan command recording cannot begin. Its encoders forward typed calls without invoking GPU methods. It completes through the existing error/callback path, reports MTLCommandBufferStatusError, never presents its drawable and releases queue capacity. No successful rendering or scheduling is fabricated. The compiler-only fault-injection switch is absent from the shipped build flags.

Experimental mitigation: WindowServer on 8086:7D45 selects Mesa INTEL_DEBUG=stall before loading/initializing Mesa, only if INTEL_DEBUG is unset. The pinned Mesa source recognizes this option and sets always_flush_cache. This adds cache flushes/stalls between draw operations, as Mesa documents. Other apps and PCI IDs are excluded. This is a synchronization experiment, not an established root-cause fix. It may reduce performance.

Diagnostics: first 24 Intel submission begin/queue/fence events retained; kernel 1.0.7 prints a bounded summary of already-captured first-error GT/engine/GuC registers for 7D45. No new MMIO reads or allocations in that summary, and no full error/VMA serialization. Existing live-log capture and fallback collection retained. Five-second WindowServer timeout unchanged; no modesetting, firmware, EFI or security change.

Validation:
- 438-object x86_64 kernel links; no new undefined symbols versus 1.0.6.
- x86_64 release plugin builds, and both copied bundle signatures verify.
- Native build of the real plugin with compile-time recording failure: 80 command buffers across normal/unretained/descriptor APIs complete with error and one completion callback each; no scheduled callback, no presentation and no capacity exhaustion; commitAndWaitUntilSubmitted returns false.
- Terminal encoder: 40,000 scissor/viewport pairs plus pointer/scalar/struct argument/return cases pass ASan/UBSan without GPU method calls.
- Scoped policy, registration identity and release-log regression fixtures pass ASan/UBSan.
- Installer/collector/rollback/boot-helper Bash syntax and all 71 copied USB checksums pass.
- Target kernel-collection preflight and Dell desktop/pixel/stability tests are pending. Apple Silicon local tests cannot establish physical Intel GPU correctness or target WindowServer behavior.

References:
- https://docs.mesa3d.org/drivers/anv.html#debugging-tips
- https://developer.apple.com/documentation/metal/mtlcommandbuffer/error
- Local pinned Mesa: src/intel/dev/intel_debug.c and src/intel/vulkan/anv_physical_device.c.

Run on Dell: sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh . After desktop install exit=0, reboot through USB once. If usable, wait two minutes then collect-desktop.sh. If black/artifacting, power off, boot USB again without reinstalling, then collect from fallback. GPU composition and hang resolution remain unverified.
