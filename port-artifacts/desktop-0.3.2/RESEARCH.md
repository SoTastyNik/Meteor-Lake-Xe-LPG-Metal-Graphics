# WindowServer candidate 0.3.2 — serial completion and surface scheduling

## Verified evidence

The preserved 0.3.1 hardware baseline is readback-20261019-114424: 22 cases, 26,000 frames, IOKit and direct access, exact pixels/padding and IOSurface backing checked, 80,020 command pools created/destroyed, no recorded hang/TLB timeout. It remains the verified application baseline; the user explicitly asked not to repeat the suite.

The failed physical desktop boot is captured in failure-detail-20261019-121101, including both current WindowServer .ips reports. Initial surface upload #1, render #2, readback #3 and render/event segment #4 completed. Second readback #5 was submitted at12:00:45.626. At the same time, the display pipe mapped the IOSurface and copied a blank frame to the panel. A second surface upload #6 was submitted at12:00:45.705 while #5 was still incomplete. Both fence waits hit the existing5-second budget. CoreDisplay then threw std::runtime_error from DisplaySurface::GetMTLTexture after the backend had shut down. The restarted WindowServer also failed; kernel later reported GPUHANG12:1:00dfffff.

Those observations establish failure ordering, not an exact GPU hang cause. External host-pointer imports were refused and fell back to copies; the fallback's first upload/readback succeeded, so import refusal alone is not established as the trigger. No physical overlap between scanout memory and command buffers has been demonstrated; this candidate does not rewrite GGTT, stolen-memory mappings, plane registers or firmware.

## Source and API research

Vulkan queue submission order is not a substitute for every resource dependency or host completion. Apple requires GPU-to-CPU synchronization of managed resources before consuming their CPU copy. The driver implements that through IOSurface copy-out after its Vulkan fence. Its submit-ahead worker previously allowed more than one WindowServer submission to be live while another thread issued synchronous surface copies. Scheduled notifications were ordinarily emitted before the corresponding IOSurface CPU publication, allowing the display consumer to observe the previous/blank backing.

Mesa's ANV debugging guidance recommends serialized submissions to investigate inter-command-buffer synchronization. Rather than enabling its debug sync path, which can block inside the ICD, this candidate uses the plugin's existing bounded wait and a recursive lock around its normal submit-begin/finish pair. The application path is unchanged. No INTEL_DEBUG flags or cache/compression settings are added.

Primary references:
- [Vulkan synchronization and submission order](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)
- [Apple managed-resource synchronization](https://developer.apple.com/documentation/metal/synchronizing-a-managed-resource-in-macos)
- [Mesa ANV debugging guidance](https://docs.mesa3d.org/drivers/anv.html#debugging-tips)

## Implemented change

Only WindowServer on vendor8086/device7d45 gets the new policy. The normal synchronous render/upload/readback wrapper holds a process-wide recursive mutex from submission begin through fence completion/retirement. WindowServer's submit-ahead method is disabled, keeping its event worker but preventing unfinished ahead submissions from escaping that bounded wrapper. One-time dummy-image initialization retains its separate descriptor-safe path; it has no new blocking lock order. Applications keep submit-ahead and normal concurrency.

For WindowServer command buffers that write IOSurfaces, the scheduled notification is deferred until their surface parts have completed and copied out. The execution finish routine now drains outstanding parts before releasing deferred scheduling, and error completion does not advertise successful publication. This fixes that early notification contract. It is not proof that every private display-transaction route honors scheduling or that the GPU hang is cured.

Fresh pools, their fence/witness checks and quarantine on uncertain completion remain intact. The5-second WindowServer budget is unchanged. The CoreDisplay exception is not hidden with fake textures or successful status after GPU failure.

## Validation and next hardware step

The x86_64 release plugin compiles and is ad-hoc signed. Local ASan/UBSan fixtures extract the actual submit wrapper and event methods:3,000 serialized submissions across3threads, application concurrency, recursion/error unlocking, two-part surface publication order, failed-copy/GPU completion and remaining-work drain. Pool lifetime/completion/readback tests pass; actual native release-constructor policy checks and80failed-command-buffer regression pass. These are local tests, not successful WindowServer operation on the Dell.

Only the Metal plugin changes in runtime. NMXGPU1.0.8, NMXAccel0.2.4, framebuffer/claim, libdrm and firmware remain byte-identical to the verified baseline. New install-windowserver.sh verifies saved baseline evidence, loaded kernel/accelerator UUIDs, installed kernel/accelerator/libdrm bytes and package signatures/hashes. It backs up/replaces only the plugin, verifies it and arms one GPU+panel boot. Partial failure restores the old plugin and clears both opt-ins. It runs no GPU tests, no full suite and no automatic reboot.

The failure collector now selects the latest desktop attempt window and includes full recent WindowServer crash reports. Next: run install-windowserver.sh on the fallback Dell desktop, then reboot through USB once. If unsuccessful, power off and boot USB again for fallback and collect-desktop-failure.sh. Candidate0.3.2 target desktop correctness and stability remain pending.
