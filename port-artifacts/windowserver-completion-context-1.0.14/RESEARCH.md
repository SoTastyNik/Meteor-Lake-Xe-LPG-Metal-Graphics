# NMXGPU 1.0.14: deferred completion context ownership

Status: locally validated candidate; target kernel panic and physical accelerated desktop NOT yet verified fixed.

## Recovered target failure

Report Desktop/reports/failure-detail-20261019-181804 includes Kernel-2026-10-19-181731.panic. The backtrace confirms NMXGPU1.0.13 UUID121AACAE-4C53-3357-9356-38C79222A842, framebuffer0.2.4 and panel claim0.2.3, uptime8.036765554 seconds. It is not the older WindowServer-watchdog panic. Stack: nmx_mtx_lock -> guc_retire_inflight_request_prio -> signal_irq_work -> linux_irq_work_fn -> taskqueue_run_locked.

The lock guard actually tests mtx_lk==NULL. The error text 'used before mtx_init' does not prove that initialization was omitted. intel_context_init already initializes ce->guc_state.lock. A stale, wrongly selected or overwritten context can produce the same guard failure.

## Research and source findings

- Published upstream patch, September16,2026, 'drm/i915/gt: Fix ce use-after-free in signal_irq_work()': https://lists.openwall.net/linux-kernel/2026/09/16/2418 . It describes reading the signaler iterator after a final context put, particularly immediately freed virtual/parallel contexts. This is a submitted patch, not a claim of acceptance or a demonstrated match to the Dell panic.
- Original Linux completion implementation: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/intel_breadcrumbs.c
- Context lifetime/retirement: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/i915_request.c and https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/intel_context.c
- GuC callback: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c

The port's breadcrumb queue takes a request reference. Timeline retirement nevertheless calls intel_context_exit/unpin, and deferred GuC priority retirement accesses rq->context (or its parallel parent). The context signaler-list reference ends when the signaler is removed; it is not an explicit ownership guarantee for every request remaining on the separate deferred signal list. RCU surrounding a worker cannot recover a context freed before that worker starts. In this port the work runs on a taskqueue, and objects are dynamically allocated/freed by its UMA shim.

A deterministic local fixture with the actual old enqueue/worker/GuC functions reproduces a heap-use-after-free if context ownership disappears before the deferred callback runs. This establishes a vulnerable ordering in the model; the panic report does not by itself prove that exact target ordering or exclude another memory-corruption source.

## Correction

Every breadcrumb-owned request reference now also holds its context and, for parallel requests, a separate parent context reference under NMXKPI. Their lifetime runs through deferred GuC priority retirement, fence notification or cancellation. Pointers needed for cleanup are saved before releasing a possibly final request reference. Parent and child are released after request cleanup, with balanced independent ownership.

The already-completed enqueue path acquires ownership BEFORE publishing the fence's SIGNALED bit, since timeline retirement can act immediately on that bit. A duplicate signal attempt releases its temporary references. Incomplete insertion, cancellation, bulk context removal and transfer to deferred work pair their get/put operations consistently.

The signaler iterator snapshots the next context before releasing the current one, adapting the upstream patch to available FreeBSD RCU list primitives. The request iterator similarly snapshots its next entry before a losing signal path can drop its last request reference. A separate sanitizer case reproduced that request-iterator use-after-free during local development and passed after this correction.

The existing mutex panic guard remains. No lazy lock initialization, ignored lock, callback skip, arbitrary delay, timeout increase or reset workaround was added. No new structure fields or cross-object ABI changes. The firmware-DSM exclusion from1.0.13 remains, so its panel/ring hypothesis is still a separate unverified change. A target pass is required before crediting either fix with desktop success.

## Validation

Actual functions compiled with ASan/UBSan: breadcrumb enqueue, worker, cancel and bulk removal, plus the actual GuC retire callback and the new ownership helpers. Old negative control fails with heap-use-after-free at context access. Corrected functions pass90,000 simulated lifetimes: delayed worker; ownership disappearing exactly at SIGNALED publication; parent/child lifetime; incomplete-to-complete; cancellation before/after completion; bulk removal; competing already-signaled retirement; duplicate signaling. No live request/context objects remain. Kernel APIs, GPU completion and RCU are modeled; this does not execute real GPU scheduling.

Release x86_64 kernel links438objects with the same undefined-symbol set as frozen1.0.8. Final UUID9B0192B5-D9CC-3FE1-9781-9276B170A4BE. Installer/helper rollback fixtures and package verification run before publication. Original1.0.8 and saved22-case/26,000-frame evidence remain; those passes do not validate this kernel. No full hardware suite rerun.

## One target trial

On Dell fallback:

    sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh

After exit0 and one desktop boot armed, restart USB once without ResetNVRAM. No automatic reboot. If black/frozen/panic, power off and boot USB again for fallback; collect before reinstalling:

    sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh

The collector now saves recent kernel panic originals and nested Retired reports before the bounded unified-log search. If a desktop appears, collect on that trial boot; a visible fallback desktop is not an acceleration pass.
