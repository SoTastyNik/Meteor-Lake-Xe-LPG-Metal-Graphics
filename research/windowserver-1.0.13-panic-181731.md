# Kernel 1.0.13 boot panic: `mutex … used before mtx_init` in GuC request retirement

**Target result: observed panic; cause unattributed. 1.0.13 is parked, not promoted.**

Collected 18:18:04 from the trial boot of kernel 1.0.13 + framebuffer 0.2.4. Full bundle:
`port-artifacts/windowserver-firmware-stolen-1.0.13/failure-detail-20261019-181804/`.

## What was installed and what booted

| Item | Value |
|---|---|
| Installer | `windowserver-install-20261019-181300`, `WINDOWSERVER INSTALL exit=0`, one desktop boot armed |
| Backup | `/Library/NullMoth/latitude5350-backups/windowserver-20261019-181304` |
| Kernel | `NMXGPU` 1.0.13, UUID `121AACAE-4C53-3357-9356-38C79222A842`, SHA-256 `d57981cbbcc45320399d348f9f7493664078dde66a3cdf4a08bc49aacf40cca4` |
| Framebuffer | `LatitudeMTLFB` 0.2.4 (retained, unchanged) |
| Panic report | `Kernel-panics/DiagnosticReports/Kernel-2026-10-19-181731.panic` |
| Uptime at panic | `8,036,765,554 ns` (≈ 8.04 s) |
| Kernel version | `xnu-11417.140.69.712.69~1/RELEASE_X86_64`, `24H32` |

The panic report names `com.nullmoth.NMXGPU(1.0.13)[121AACAE-4C53-3357-9356-38C79222A842]` in the
backtrace, so the new image did load and run; this is not a stale-binary trial.

## The panic, verbatim

```
panic(cpu 0 caller 0xffffff7fb3a737a6): NullMoth xkpi: mutex 0xffffff95128a9088 (?) used before mtx_init
Panicked task 0xffffff90457aa980: 245 threads: pid 0: kernel_task
0xffffffd6c8abfe40 : 0xffffff7fb3a737a6 com.nullmoth.NMXGPU : _nmx_mtx_lock.cold.1 + 0x26
0xffffffd6c8abfe50 : 0xffffff7fb3a3b996 com.nullmoth.NMXGPU : _nmx_mtx_lock + 0x66
0xffffffd6c8abfe80 : 0xffffff7fb3987a31 com.nullmoth.NMXGPU : _guc_retire_inflight_request_prio + 0x31
0xffffffd6c8abfeb0 : 0xffffff7fb38c7a64 com.nullmoth.NMXGPU : _signal_irq_work + 0x154
0xffffffd6c8abff20 : 0xffffff7fb3a2e3b6 com.nullmoth.NMXGPU : _linux_irq_work_fn + 0x16
0xffffffd6c8abff40 : 0xffffff7fb3a4415b com.nullmoth.NMXGPU : _taskqueue_run_locked + 0x4b
0xffffffd6c8abff70 : 0xffffff7fb3a44338 com.nullmoth.NMXGPU : _taskqueue_thread_loop + 0x38
```

Boot arguments: `-v debug=0x100 keepsyms=1 itlwm_he=1 itlwm_mtl_internal_aux=1 amfi_get_out_of_my_way=0x1
amfi=0x80 ipc_control_port_options=0`.

## Why the lock is the fault, from source

1. `signal_irq_work()` (`drm-kmod/drivers/gpu/drm/i915/gt/intel_breadcrumbs.c:170`) signals completed
   requests and calls the scheduler's retire hook at lines 254–255:
   `rq->engine->sched_engine->retire_inflight_request_prio(rq)`.
2. That hook is `guc_retire_inflight_request_prio()`
   (`drm-kmod/.../gt/uc/intel_guc_submission.c:4361`), which does
   `spin_lock(&ce->guc_state.lock)` at line 4364.
3. `ce` is `request_to_scheduling_context(rq)` → `intel_context_to_parent(rq->context)` (line 384).
4. `ce->guc_state.lock` is initialised only in `intel_context_init()`
   (`drm-kmod/.../gt/intel_context.c:415`, `spin_lock_init(&ce->guc_state.lock)`).
5. In this port `spin_lock()` resolves to the FreeBSD mutex shim, and `nmx_mtx_lock()`
   (`NullMoth/gpu-port/xkpi/bsdcompat/src/nmx_lock.c:70`) calls `mtx_check()`, which panics when
   `m->mtx_lk == NULL`. The panic message prints the lock's `lo_name`, and here it is `?` — i.e. the name
   pointer is also NULL.

A zeroed `lo_name` and a NULL `mtx_lk` mean the `struct mtx` was never passed through `mtx_init()`. So the
object reached through `ce` is a zeroed (or recycled-and-zeroed) `intel_context`, not a contended or
destroyed lock in the ordinary sense.

**What this does not establish:** which context it was, whether `ce` was a parent of a parallel submission,
why its memory was zeroed, and whether the pointer was stale. The report contains no register dump, no
context/engine identity, and no allocation history for `0xffffff95128a9088`.

## Did the 1.0.13 change cause it?

1.0.13 makes two changes (`port-artifacts/windowserver-firmware-stolen-1.0.13/source/`):

* `intel_memory_region.c`: under `NMXKPI`, for device `0x7d45`, `continue` past
  `INTEL_MEMORY_STOLEN_LOCAL` and `INTEL_MEMORY_STOLEN_SYSTEM` so no stolen region is created;
* `gt/intel_ring.c`: a `drm_info` line recording `stolen=` / `size=` / `ggtt=` at ring pin.

**Not shown to have executed.** The retained unified log contains no `i915` line at all and neither
`stolen region withheld` nor `Latitude MTL ring pinned`. `drm_info` output is therefore not represented in
this capture, and the log cannot confirm that the region-skip branch ran — only the backtrace proves the
1.0.13 image did.

**No demonstrated mechanism.** Withholding a memory region changes where GEM objects and rings allocate; it
does not initialise or deinitialise an `intel_context`. Nothing in the two diffs touches context allocation,
`intel_context_init()`, GuC context registration, or request retirement. A causal path from "no stolen
region" to "a zeroed `ce->guc_state.lock`" is not shown by source inspection.

**Nothing excludes it either.** If a later initialisation step depends on the region probe having produced
a region (ordering, error unwinding, or a partially completed `intel_gt_init`), the skip could leave a
context allocated but not initialised. That is a hypothesis, not a finding, and this capture cannot
discriminate it.

**It is a new signature.** None of the retained kernel panic reports (17–19 October) contains
`used before mtx_init`; the others are WindowServer watchdog timeouts and kernel page faults. The panic is
new to this boot rather than a known recurring event.

## Consequence

* 1.0.13 must not be re-armed or described as a fix, a regression, or an improvement. It is **parked**.
* The last booted payload whose behaviour is characterised remains **1.0.12 + framebuffer 0.2.4**
  (`research/windowserver-1.0.12-failure-180032.md`): the ring overwrite still occurred and the readback
  still timed out.
* The next desktop trial should be preceded by a decision on 1.0.13: revert the region skip, or attribute
  the panic. Re-arming the same payload unchanged would only reproduce an 8-second panic.

## What would discriminate

1. **Reproduce or refute:** boot 1.0.12 again under the same collector. If the panic recurs without the
   region skip, 1.0.13 is not required for it; if it does not, the skip becomes the prime suspect without
   being proven.
2. **Make the region decision observable:** log it through the path the collector actually captures
   (`IOLog` / the `VFBLOG` route), not `drm_info`.
3. **Identify the context in the panic:** record `ce`, `rq->context`, the child/parent flag, `guc_id` and
   the engine in the panic path, and log every `intel_context_init()` with the same identifiers so the
   zeroed object can be matched to a missing initialisation.
4. **Unchanged:** the ring guard and the physical-page ownership map remain the way to name the writer of
   `0xff000000`; this panic does not answer that question.

Local payload and tests were not modified while writing this note. No reboot or reinstall is requested.
