# Candidate0.3.5: uncompressed WindowServer workload and accurate kernel capture

## Evidence and current conclusion

Candidate0.3.4 failed in report failure-detail-20261019-131639. First seven submissions completed. Third readback/submission8 used dedicated staging (owned1, new stage13), successfully acquired the desktop mutex, returned from pre-submit, and vkQueueSubmit returned0. Fence wait timed out after5000ms. The kernel later reported hung rcs0 context/request8:20, GuC context0x1002 not started, GPUHANG12:1:00dfffff. Fresh command pools, fresh readback staging and serial submit/finish are therefore insufficient. TLS-staging reuse is not required to trigger this hang.

The sample now succeeds but targets restarted WindowServer405 after original backend failure; it shows CoreDisplay pipeline initialization waiting in dummy zero-fill. It must not be treated as the original hang's stack. The same applies to follow-on texture exceptions and shader/pipeline errors after backend shutdown. No timeout increase, fake completion, unsafe resource free or swallowed exception is introduced.

## Kernel audit and the diagnostic defect repaired

The local i915 source follows upstream's two capture paths. intel_engine_coredump_alloc calls engine_record_registers/execlists only when CORE_DUMP_FLAG_IS_GUC_CAPTURE is absent. GuC captures instead attach a parsed register-list node. guc_capture_find_ecode copies selected values for the error code, but many legacy fields remain zero placeholders. The previous NullMoth summary printed legacy engine->head/tail/start/acthd/bbaddr without the parsed GuC lists. Those zeros did not demonstrate an idle ring, physical address0 or absence of a fault.

Diagnostic kernel1.0.9 fixes that evidence gap. While capture_engine owns the request reference returned by intel_engine_get_hung_entity, it records fence context/sequence/flags/error, readiness/active/started/completed states, pending submit dependencies, hardware breadcrumb, GuC ID/scheduling snapshot, LRC address and ring/batch GPU virtual addresses. It does not traverse live request lists, allocate buffers, wait on a GPU operation or add MMIO reads. Existing request APIs retain their RCU protection for breadcrumb lifetime. The values are a sampled view, not one atomic snapshot of every field.

The already-owned parsed GuC node is logged through a bounded printer: at most3lists and64registers/list/engine; absent capture is explicitly reported. Legacy fields can still appear in historical summary lines, but are no longer the only available register evidence. The helper does not request a new hardware capture or alter GuC scheduling, reset policy, firmware or timeout handling. Logging runs on the error path and may perturb failure timing/volume.

Kernel link uses the existing438object build, replacing only i915_gpu_error.o and intel_guc_capture.o. The undefined-symbol set remains identical to1.0.8. Candidate UUID E770B985-14A4-3ADE-A1EE-63204C3A9996. The1.0.8 bundle and full application evidence remain preserved in their original package location;1.0.9 is separately packaged under WindowServerKernel until the guarded installer applies it.

## Controlled workaround: compression off only in this WindowServer

Mesa ANV documents noccs for isolating compression-handling hangs. Its local source parses INTEL_DEBUG once; the ISL surface-support path rejects CCS when DEBUG_NO_CCS is set. MTL's image path also describes auxiliary compression storage/translation. Those facts justify investigating image/compression state across the desktop's render-to-readback workload; they do not prove compression caused this hang or exclude GuC dispatch, image-layout recording or physical display memory ownership.

Plugin0.3.5 sets INTEL_DEBUG to include noccs before its Intel ICD dlopen, only for vendor8086/device7d45/processWindowServer. Existing flags are preserved with bounded input; an oversized/failed setting stops initialization instead of claiming the policy applied. No new sync/stall/async-queue flags are combined with it. Apps, other processes/devices and the installed Mesa binary remain unchanged. The trace records this requested policy before ICD loading; it is not an independent measurement of every internal image's compression state. This relies on the normal first-ICD-load ordering and the audited Mesa parser.

This may reduce performance or increase memory bandwidth if it avoids the hang. It is a workaround trial, not a proven root-cause repair. Fresh pools, dedicated readback, publication deferral, bounded host-lock/fence waits and uncertain-resource quarantine remain from0.3.4, so compression is the only new intentional GPU execution policy. Firmware70.53.0 remains unchanged; the supplied Linux report used the same version. Physical plane/GGTT registers and stolen-memory mappings are not rewritten: no concrete overlap has been demonstrated.

## Installation and recovery

The same install-windowserver.sh accepts only the frozen baseline1.0.8 kernel or exact1.0.9 candidate UUID and matching installed bytes, plus verified accelerator/transport/package/evidence. It builds a complete next AuxKC against the laptop's system collections before mutating runtime files. It backs up the previous GPU kernel and AuxKC, stages plugin/capture tools, commits the new kernel/cache, mirrors via kcditto, then arms one GPU+panel boot. Partial failure restores plugin/tools/kernel/cache and clears opt-ins. A failed cache rollback retains work/backup paths and exits3 for attention. No automatic reboot, firmware/security/EFI change or full hardware-suite run.

The collector now records the kernel loaded on the collection boot and its installed binary hash with a bounded identity query. This is explicitly current/fallback identity, not proof of the earlier failed boot's identity. Correlate install reports, boot UUIDs and retained kernel events.

On the Dell fallback desktop: run install-windowserver.sh, wait for exit0/one boot armed, then restart directly through USB without ResetNVRAM. Kernel1.0.9 takes effect on that restart. If black/frozen, poweroff/USBfallback and collect-desktop-failure.sh before reinstalling. A visible desktop should be collected on that same boot. Do not rerun the22case suite or accept a visible fallback session as an accelerated pass.

## Validation and limitations

Both changed kernel units compile;438object link passes with no new undefined imports. The actual GuC printer runs under ASan/UBSan with absent/empty/null/oversized lists and a bounded192register limit. The actual compression helper tests exact process/vendor/device scope, preserving flags, unset/empty environment, oversized input rejection; source-order check verifies application before ICD load.

Actual installer plus actual kernel-update helper are exercised together with OS mocks: baseline/kernel guards, success, KC build failure before mutation, commit/mirroring failure, journal failure, signature verification failure, partial arming, restoring kernel/cache/plugin/capture tools. Separate helper tests cover a kernel already current. The collector's crash/retained-artifact behavior still passes after kernel identity capture was added. Native release control masks and80failed command buffers pass, and the actual readback regression exercises20,000balanced mocked allocation lifetimes and uncertain-resource retention. Release x86_64 builds/signatures/package hashes are checked. These are local validation, not a hardware desktop pass or a repetition of the application matrix.

A real physical desktop session remains necessary to establish whether noccs helps. If it hangs, the request/parsed-GuC capture should distinguish dependency blockage, dispatch/completion state and useful captured fault addresses. Those results, rather than another blind staging tweak, drive the next correction. Neither a complete hardware fix nor protection against every future WindowServer failure is claimed.

## Primary references

- [Mesa ANV debugging](https://docs.mesa3d.org/drivers/anv.html): compression-disabling isolation; no implication that a matching symptom has one universal fix.
- [Linux6.14 error capture](https://raw.githubusercontent.com/torvalds/linux/v6.14/drivers/gpu/drm/i915/i915_gpu_error.c): legacy-vs-GuC capture branches, owned request/context references.
- [Linux6.14 GuC capture](https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/uc/intel_guc_capture.c): parsed capture ownership and existing register printer.
- [i915 architecture](https://docs.kernel.org/next/gpu/i915.html): request dependencies, dispatch and completion are separate phases.
- [Vulkan synchronization](https://docs.vulkan.org/spec/latest/chapters/synchronization.html), [memory lifetime](https://docs.vulkan.org/refpages/latest/refpages/source/vkFreeMemory.html): retirement remains gated on completion, not a timeout.
- [FreeBSD report on7d45](https://github.com/freebsd/drm-kmod/issues/441): useful platform context, different OS/workload/GuC mode; not evidence of this macOS root cause.

Local Mesa source inspected (no edits): src/intel/dev/intel_debug.c, src/intel/isl/isl.c, src/intel/vulkan/anv_image.c and anv_device.c. Local kernel audit also covered GuC submit/CT, request capture, GGTT binder/direct DSM handling, scheduler wakeup, thread/process identity, RCU and DMA barriers. No additional reproduced scheduling defect was established in those paths during this review.
