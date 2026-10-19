# WindowServer request-boundary investigation — NMXGPU1.0.10

Status: diagnostic candidate only. No demonstrated fix for the GPU hang or fully accelerated desktop. The candidate does not change compression policy, scheduling, timeouts, firmware, command pool allocation or reset behavior. It preserves the passing application baseline and does not run the22-case suite.

## Evidence and research

The16:53 boot loaded1.0.9 and NVMTLDriver0.3.5, applied noccs before ICD loading, completed submissions1–7, then stalled at submission8/readback3. Fence timeout16:53:35.460 preceded the original WindowServer163 CoreDisplay abort at16:53:35.842. Kernel hang capture16:53:43.292–43.369 found request context8/seq20 with started0/completed0, ring head0xca4, request head0xca8, request tail0xe08, HWSP0x12. The pointer is four bytes before the request start. This does not establish which instruction caused the stall. started0 is the software breadcrumb test; it is not independent proof that no user instruction executed. CLOSED in sched_state0x150 may reflect the crash before capture.

Audited local ring mappings/cache barriers, GuC scheduling, request completion and image readback. No reproduced defect in those paths has been established by this audit. In particular pmap_change_attr being a shim no-op alone does not prove the ring mapping is cached incorrectly: this port's vmap creates an IOKit mapping with the requested cache mode. Do not apply a broad flush workaround on that observation alone.

Compared GuC submission semantics against Linux v6.14 primary source: memory LRC tail updates and H2G scheduling enable/context-submit messages are distinct. The source includes reference/disable coordination and idle context teardown; a post-crash CLOSED bit alone is insufficient to diagnose that race. Local gen8_emit_wa_tail adds MI_ARB_CHECK and MI_NOOP for the idle/lite-restore workaround. Do not remove those hardware workarounds without identifying the captured words and request boundaries.

Primary sources:
- https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c
- https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/gen8_engine_cs.c
- https://docs.kernel.org/gpu/i915.html

## What this candidate adds

Before the LRC tail is published, copy up to128 request dwords plus4 preceding dwords into96 fixed, write-once boot-lifetime slots. Scope: device8086:7d45, render engine, active referenced request, seqno<=32, valid pinned CPU ring mapping. No persistent pointer, allocation, sleep, new MMIO or hot-path logging. Bounds and wrap handling reject invalid mappings/offsets and explicitly mark truncation. Slot publication uses release/acquire ordering; slots are never reused. Storage is fixed at roughly60KiB and released with the module; it cannot grow with a sustained OS loop.

On hang, print saved snapshots for the hung timeline's request and up to4 preceding sequence numbers, plus the ring's current CPU-mapped contents and existing parsed GuC register state. This distinguishes what was written before scheduling from what remains after the failure. It does not capture actual GPU-read contents or full user batches, so it may still not distinguish stale cache data from hardware/context faults. Missing early snapshots are explicitly reported when the fixed capture budget is exhausted. Diagnostics can change timing slightly, although submission logging is avoided.

The new kernel links438objects, has the same undefined imports as1.0.8, and contains only two newly rebuilt translation units over1.0.9. ASan/UBSan tests use the real snapshot code to check observed0xca4boundary, wraparound, truncation, invalid/unmapped/unpinned/inactive rings, device/sequence scope, saved-slot publication and budget. Installer/parser/rollback tests pass including upgrading exact loaded1.0.9 or1.0.10 and repairing either exact installed diagnostic kernel when not loaded. Both old1.0.9 and baseline1.0.8 payloads remain in the package for identity checks; installed rollback uses actual backups.

## Target action

Fallback Dell: sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh

Afterexit0, reboot USB once without ResetNVRAM. This is a diagnostic attempt; the black screen may recur. If it fails, poweroff/USBfallback then run collect-desktop-failure.sh before reinstalling. No full hardware suite, no automatic reboot. Do not interpret successful installation or a visible cursor as accelerated desktop success.
