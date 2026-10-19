# 0.3.1 — GuC wait compatibility fix after verified 0.3.0 hang

## Target evidence

Report readback-20261018-235331 loaded NVMTLDriver0.3.0 and verified actual policy0x2f, including permanent fresh pools. GPU registration worked after the explicit GPU-only boot. First four cases passed 1000 frames each: small raw, small render, full-HD render, padded full-HD. Each ended created=destroyed, zero live/pending/quarantined, peak1. Thus fresh allocation and prompt successful-completion cleanup were exercised on target.

At23:54:50.264, after the padded process finished and before the next process connected, kernel logged GuC TLB invalidation response timeout for seqno1. The fifth case subsequently hung on upload submission#1285 at zero-based frame428. Its preceding readback#428 completed, and that frame's render had not begun. QueueSubmit returned0; fence returned-4 after10798ms. Kernel reported rcs0 request12:2574 not yet started and GPU HANG12:1:00b79797. Pool counters1286created/1285destroyed/1quarantined show the uncertain pool was retained as designed. No desktop gate/activation occurred.

Fresh pools are insufficient as a complete hardware-stability fix. The earlier passing comparison was too short to establish long-term stability or isolate a root cause. The TLB error before the failing process makes kernel teardown/invalidation synchronization an investigation priority; it does not prove causation.

## Research and reproduced defect

The i915 invalidation path waits on WQ_FLAG_WOKEN using must_wait_woken, then schedule_timeout. Linux's woken callback both marks the flag and invokes the task wake machinery. The FreeBSD LinuxKPI callback in this port marked WOKEN and signaled the sleep channel, but did not persist TASK_WAKING. Its schedule_timeout checks TASK_WAKING under that channel lock before registering sleep. A reply between the outer flag check and registration could therefore signal an empty channel, then the waiter sleeps to expiry despite the flag being set.

The new override/src/linux_schedule.c retains the existing lock, WOKEN flag and signal; for matching task states it also sets TASK_WAKING under the same lock, following the port's existing wake_up_task protocol. This closes the reproduced pre-enrollment wake gap while leaving the timeout duration, actual GPU acknowledgement requirement and quarantine behavior intact. The common scheduler fix is used by all matching woken-callback users; the LinuxKPI impact is broader than one i915 call site. True missing hardware replies can still time out.

The actual old/patched woken callbacks, actual schedule_timeout, and actual i915 must_wait_woken are extracted into a deterministic scheduler fixture. The old version reproduces false expiry in the pre-enrollment race. Patched version preserves positive remaining time. 100000 total scenarios cover old/new paths, wake before flag check, pre-enrollment wake, registered wake, spurious wake then real response, and genuine timeout; ASan/UBSan pass. This verifies a software race fix, not a Dell hang cure. Kernel1.0.8 compiles, links438existing objects and introduces no new undefined symbols versus1.0.7.

Primary source references:
- [Linux i915 invalidation waiter](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c)
- [Linux wait/woken callback](https://github.com/torvalds/linux/blob/master/kernel/sched/wait.c)
- [FreeBSD LinuxKPI scheduler and woken callback](https://github.com/freebsd/freebsd-src/blob/main/sys/compat/linuxkpi/common/src/linux_schedule.c)

## Candidate and gate

Candidate0.3.1 carries NMXGPU1.0.8, unchanged NVMTLDriver0.3.0 fresh-pool implementation and unchanged firmware/framebuffer/security settings. Runtime expects kernel1.0.8 and the exact built Mach-O UUID, compares installed kernel/plugin/libdrm with the USB, and includes all three hashes in the same-invocation gate. The suite now rejects kernel TLB invalidation timeouts as well as hangs/resets. Its parser requires timestamped kernel records, excluding filter headers and log-command metadata that mention GPU HANG. Such metadata caused a false-positive match in the old parser, though the latest report contains a real hang as well. The full22case hardware gate remains required; no auto-reboot.

Next target steps: install-readback.sh, reboot USB once, test-and-arm-desktop.sh. Candidate0.3.1 hardware and accelerated WindowServer/panel results remain pending. Do not infer stable physical display from local build or sanitizer results.
