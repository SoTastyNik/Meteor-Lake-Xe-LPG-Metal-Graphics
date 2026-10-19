# WindowServer candidate 0.3.3: bounded host lock and retained startup evidence

## What the latest evidence establishes

The full application baseline remains candidate0.3.1, NMXGPU1.0.8 and NMXAccel0.2.4:22 cases,26,000 frames,80,020 pools reclaimed. This is evidence of those application workloads, not successful WindowServer composition.

Candidate0.3.2 installed successfully at12:30:32. Its next boot began12:32:04 and black-screened; fallback began12:33:19/20. Report failure-detail-20261019-123632 contains only the12:32:11 live-log header, an empty registry file and no new WindowServer crash report. Its .previous captures belong to the earlier12:00 attempt. Unified history does not retain the failed boot's plugin/queue/fence events. We cannot infer whether the new submission policy ran, whether it deadlocked, or whether the GPU hung again.

Source audit found an independent correctness gap: the new recursive desktop mutex used unbounded pthread_mutex_lock before the existing GPU wait budget started. No lock inversion was established. Candidate0.3.3 bounds acquisition using trylock plus a monotonic deadline, preserving recursion and the process/device scope. A failure disables the backend and quarantines the entering command's pools; it neither unlocks another thread's mutex nor submits/frees uncertain work. The GPU-fence timeout remains separate. This is not a complete wall-clock bound on initialization, ICD calls, disk I/O or kernel waits.

## Evidence capture and limits

The installer pre-creates /Library/Logs/LatitudeDesktopAttempt.trace, owned by _windowserver with mode0600, before arming the boot. The plugin opens this existing regular file without following symlinks and appends boot UUID, monotonic/epoch timestamps, process/thread IDs and stage/result records. Stages cover constructor entry, Vulkan once/init, desktop lock acquisition, pre-submit hook, queue submission and fence wait. Only WindowServer writes plugin stages, capped at256 calls. The file stops accepting writes at256KiB. No environment knob enables this path for other processes.

Each record requests F_FULLFSYNC with fsync fallback. This improves the chance of surviving forced power-off; it is not a guarantee, and the sync itself can block or perturb timing. WindowServer's sandbox may refuse the file even with correct ownership; the first journal error is sent to syslog. The root loader writes independent stages into the same boot-tagged journal before its first claim query, periodically flushes live logs and attempts a bounded3-second WindowServer sample after8seconds. Sample errors are retained. No sandbox, task-port or SIP restrictions are bypassed.

Claim queries, registry snapshots, sample invocation and framebuffer-load invocation have watchdogs. A kernel-uninterruptible task may outlive a signal, so these are best-effort process deadlines. Fallback boots leave the failed attempt's live/registry/sample files intact. The journal itself is prepared/rotated only by an explicit install, and records distinguish any subsequent fallback boot by UUID. The collector includes the journal, previous journal, stack sample/errors, existing live/registry logs and recent full WindowServer crash reports. It runs no GPU probes.

## Research basis

[Vulkan queue submission](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueueSubmit.html) requires host synchronization and does not equate submission order with completion. Existing fence/witness-based retirement and quarantine remain necessary; a host-lock deadline cannot justify freeing in-flight GPU objects.

[Apple fsync documentation](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html) distinguishes host buffer flushing from the stronger drive-flush request F_FULLFSYNC. [Apple's disk-write guidance](https://developer.apple.com/documentation/xcode/reducing-disk-writes) motivates restricting these expensive writes to startup diagnostics rather than indefinite per-frame logging. [Unified logging](https://developer.apple.com/documentation/os/logging/) does not replace a deliberately retained startup trace in this failure mode.

The earlier managed-resource/publication policy remains from0.3.2; see [Apple managed-resource synchronization](https://developer.apple.com/documentation/metal/synchronizing-a-managed-resource-in-macos). No new claim is made that deferred Metal scheduling alone fixes every private CoreDisplay transaction.

## Scope and validation

Runtime changes are the Metal plugin, boot loader script and a signed x86_64 journal helper. Kernel/accelerator UUIDs and bytes, framebuffer/claim, libdrm, firmware, fresh command pools, completion witness checks, quarantine and application submission concurrency are preserved. The installer backs up all three changed components, verifies them and prepares logging before arming one GPU+panel boot. Failed preparation or partial arming restores all previous components and clears both markers. No automatic reboot or full hardware-suite run.

Local validation: x86_64 release build/signing; native release diagnostic-control checks and80failed-command-buffer regressions; actual submit wrapper under ASan/UBSan with3,000 serialized submissions, normal app concurrency, recursive managed upload and forced lock contention; pool lifetime30,000objects across3threads and four completion/witness failure modes; actual event publication and readback methods; actual journal helper safety/rotation/flush/cap; mocked-OS loader stage/capture/fallback/error behavior; actual installer rollback including journal failure; collector retention of new artifacts even when history search fails. The test fixture needed a non-static trace stub after the public declaration was added; production compilation did not fail on this issue.

Next hardware action is one targeted install-windowserver.sh and USB boot. Hardware desktop correctness and stability are pending. Existing application tests do not need repeating for this attempt.
