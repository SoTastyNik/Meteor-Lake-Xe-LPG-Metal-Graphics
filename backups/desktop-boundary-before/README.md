# Installer validation corrected

The16:44 installer safely rolled back after an empty kmutil UUID listing. Its saved prelink record actually contains the correct1.0.9 UUID and permanent path. The updated installer checks the structured record directly with a signed helper. Local parser and installer rollback checks pass. Driver binaries are unchanged; accelerated WindowServer remains unverified.

On the Dell fallback desktop, run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh`. Reboot through USB only after exit0, without ResetNVRAM. The full GPU suite is not rerun.

---

# Installer cache-path repair ready

The13:36 boot did not load NMXGPU: its AuxKC referenced a deleted temporary bundle. WindowServer waited for GPU publication. It did not test the compression workaround. The installer now rebuilds the final cache from the permanent installed bundle and verifies path/UUID before arming. It supports the exact installed1.0.9-but-not-loaded repair state.

On fallback Dell: run install-windowserver.sh again. Afterexit0, reboot USB once without ResetNVRAM; then collect-desktop-failure.sh. No full hardware-suite run. Driver binaries remain0.3.5/kernel1.0.9; their desktop behavior is still unverified.

[Evidence and installer correction](../windowserver-0.3.5-cache-repair-133725.md).

---

# Candidate0.3.5 — compression isolation plus request/GuC capture

Fresh readback staging did not prevent the0.3.4 GPU hang. This candidate disables image compression only in8086:7d45 WindowServer and installs diagnostic NMXGPU1.0.9. Its capture now includes owned request state and parsed GuC registers; legacy zero register placeholders alone were insufficient. This is an unverified workaround candidate, not a proven hang cure.

The installer verifies the saved22case/26,000frame application evidence. It does not rerun the suite. The original1.0.8 kernel remains frozen in the package;1.0.9 adds error diagnostics, without a scheduling, firmware, reset-policy or timeout change. Accelerator, framebuffer, firmware and transport remain unchanged. Compression off may affect bandwidth/performance.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

This version also builds the next auxiliary kernel collection and backs up the previous GPU kernel/cache before committing. Wait for exit=0 and ONE desktop boot armed, then restart directly through USB once without ResetNVRAM. Kernel1.0.9 takes effect on restart. No automatic reboot or GPU tests.

If black/frozen/artifacting: power off, boot USB again for fallback, collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If visible, collect on that boot. A visible fallback desktop is not an acceleration pass. Bring back the USB after this single attempt.

[Research, source audit, validation and remaining limits](../windowserver-0.3.5-research.md).

---

Historical instructions below are superseded by this workflow.

# Candidate0.3.4 — dedicated WindowServer readback staging

The0.3.3 active desktop boot still hung: fourth readback timeout, kernel GPU hang, then WindowServer crashes. This candidate gives each8086:7d45 WindowServer readback its own dedicated staging allocation, freed after completion and CPU copy, with quarantine on uncertain completion. It also frees known unsubmitted staging failures and fixes denied diagnostic writes, truncated startup logging and false-success stack samples. This is a controlled mitigation candidate, not a confirmed GPU-hang cure.

Kernel, firmware, accelerator, framebuffer, transport and the verified22case/26,000frame application baseline remain unchanged. No full-suite rerun is required.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0 and ONE desktop boot armed, restart directly through USB once. Do not reset NVRAM; that clears the one-shot markers. This installer has backups/rollback and does not reboot or run GPU tests.

If black/frozen/artifacting: power off, boot USB again for fallback, and collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If the desktop is visible, run the same collector on that boot. A visible fallback desktop is not acceleration evidence. Bring the USB back after this single targeted attempt.

[Detailed source research, evidence, changes, validation and unresolved risks](../windowserver-0.3.4-research.md).

---

Historical instructions below are superseded by this workflow.

# Candidate0.3.3 — WindowServer startup diagnostic and bounded submission lock

The latest black-screen boot did not preserve enough evidence to locate the failure. This candidate bounds the desktop submission-lock wait, quarantines resources on failure, and adds a pre-created, synced startup journal plus early loader stages and an attempted WindowServer stack sample. This is a targeted diagnostic/lock fix; working accelerated desktop output is not yet established.

The verified22-case/26,000-frame application baseline is retained. GPU kernel, accelerator, framebuffer/claim, firmware and transport remain unchanged. No hardware suite needs repeating.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0 and ONE desktop boot armed, reboot through this USB once. The installer backs up/replaces the plugin and two capture tools, prepares the journal and arms one GPU+panel attempt. It runs no GPU tests and does not reboot automatically.

If black/frozen/artifacting, power off and boot USB again for fallback. Then collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

The same read-only collector can capture a working desktop after a few minutes. It includes the new startup journal/sample plus recent full WindowServer crash reports. Bring the USB back for inspection.

Synced logging is best effort; disk waits and sandbox/sample permissions can still prevent capture. [Evidence, research and limits](../windowserver-0.3.3-research.md).

---

Historical instructions below are superseded by this workflow.

# Candidate 0.3.2 — WindowServer-only update

The verified0.3.1 baseline remains22cases/26,000frames passed with80,020command pools reclaimed. No full-suite rerun is required. The failed desktop boot exposed a second readback stalling alongside another surface upload, then a CoreDisplay texture exception after backend failure.

This plugin serializes WindowServer's normal submissions through completion, disables its submit-ahead path, and defers surface-writing scheduling notifications until copy-out finishes. The5-second timeout and quarantine behavior remain intact. Other applications retain normal concurrency. GPU kernel, accelerator, framebuffer, firmware and libdrm remain unchanged. Local build, sanitizer/order/error/installer tests pass; hardware desktop success is still pending.

On the Dell's fallback desktop, run only:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

It verifies the saved hardware baseline and loaded kernel/accelerator, replaces only the Metal plugin with backup/rollback, and arms one desktop boot. It does not run GPU tests or reboot. After exit=0 and ONE desktop boot armed, reboot through this USB once. Check the laptop panel and window movement.

If black/artifacting/frozen: power off, boot through this USB again for fallback, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

That saves the latest desktop attempt's boot logs and recent full WindowServer crash reports. If the desktop works, use the same read-only collector after a few minutes; avoid the old collect-desktop.sh, which also runs GPU probes. Bring back the USB after the targeted attempt.

[Evidence, primary references and implementation limits](../windowserver-0.3.2-research.md).

---

Historical instructions below are superseded by this desktop-only workflow.

# Candidate 0.3.1 — GuC wake-race fix

The latest0.3.0 target test passed4,000frames with balanced fresh command-pool destruction, then recorded a GuC TLB-invalidation timeout before the fifth process. That process subsequently lost an upload fence at frame428. Fresh pools remain enforced, but are insufficient to establish GPU stability.

Kernel1.0.8 fixes a reproduced LinuxKPI missed-wakeup race: a GuC reply arriving before the sleeper registers now leaves a task wake state that schedule_timeout observes under the same lock. Local sanitizer tests reproduce the old false timeout and pass100,000scenarios with the fix, including real timeout behavior. Hardware causation and stability remain unproven. NVMTLDriver remains0.3.0 because its binary is unchanged.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through this USB once, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

The full22case suite checks loaded NMXGPU1.0.8 and its exact build UUID before workloads. Any recorded kernel TLB timeout/hang/reset blocks the gate. Same-invocation proof binds the kernel, Metal plugin and libdrm hashes before one-shot GPU+panel arming. It never reboots automatically. Surface/WindowServer stability remains a separate test after the gate passes.

If the suite fails, collect-readback-failure.sh before reinstalling; logs save automatically as well. After failed desktop output, power off and boot USB again for fallback, then collect-desktop-failure.sh. [Detailed evidence and primary references](../fresh-pool-guc-research.md).

---

Historical candidate notes below are superseded by the steps above.

# Candidate 0.3.0 — fresh-pool enforced

Command-pool recycling is removed for every queue and helper path. Every submission gets a newly created pool; successful completion destroys it and all its command buffers before returning. Unsubmitted pools are destroyed on abandonment/failure. Timeout, device-loss or missing-witness resources remain quarantined, stop the backend and fail the gate, because completion is uncertain. Address-page caching and completion witnesses remain enabled.

The verified fresh-pool comparison passed 4,000 frames; the retained control lost the render fence at submission #305, padded frame101. This supports the permanent workaround. It does not prove the cause, long-term stability, or accelerated WindowServer output. Candidate 0.3.0 has compiled and passed local lifetime/failure/gate tests; its target checklist is still pending.

On the Dell, install:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through this USB once. Then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

This runs all 22 cases at 1,000 iterations per worker: raw/render small, full-HD, padded, repeated forced-fresh pools, fresh staging, fresh textures, independent queues, serial shared-texture handoff, RGBA IOSurface and BGRA IOSurface, through both IOKit and direct access. Every case checks actual loaded policy, exact pixels/padding and transport; surface cases also check published backing bytes. Pool counters must balance with zero live/pending/quarantined pools. Resident-memory progress is retained in the logs for soak analysis; other allocator caches are outside this pool-balance guarantee.

Only a passing same-invocation suite with the same boot UUID and binary hashes arms GPU+panel for one desktop boot. The script does not reboot. After its explicit success message, reboot through this USB when ready. A suite failure leaves desktop unarmed. Bring back the saved report. For another suite, prepare-readback-boot.sh and reboot USB first. If a desktop boot artifacts/hangs, power off and boot this USB again for firmware-display fallback; do not repeatedly reinstall.

The historical `fresh-pools` diagnostic is now a focused test of the permanent policy; the retained-pool profile is removed. Policy bits are 0x2f for normal tests and 0x3f with fresh staging; all other release processes also enforce fresh pools. Numeric Vulkan handle values may be reused by the Vulkan allocator after object destruction; no old pool object or command buffer is recycled by this driver.

Pool destruction follows the Vulkan requirement that command buffers are no longer pending: [vkDestroyCommandPool](https://docs.vulkan.org/refpages/latest/refpages/source/vkDestroyCommandPool.html), [vkWaitForFences](https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitForFences.html).

---

Historical candidate notes below describe older packages and are superseded by the steps above.

# Candidate 0.2.9 — repair and verify effective test controls

The 0.2.8 run confirms another GPU hang at frame 169, but its command-pool comparison was invalid. Release startup deliberately removes NVMTL_* environment settings, which removed both the fresh-pool switch and diagnostic logging. Requested settings in a policy file did not prove the driver used them. No pool-reuse conclusion should be drawn from that run.

This candidate preserves six exact =1 test controls only in the explicitly enabled latitude-readback-test process. Other processes and unrelated settings keep the original release scrub. The actual native release plugin constructor was tested, not just a mock of the runner: retained/fresh-pool/fresh-staging policy bits survived, while unrelated controls and controls in another process were removed.

The test now queries effective settings inside the loaded Metal driver AFTER release initialization. It prints POLICY effective=... expected=... and requires an exact match before submitting the workload. Fresh-pool runs require 0xf; retained warmups require 0xd; fresh-staging requires 0x1d. Missing/wrong policy stops the test. The runner also requires the effective-policy PASS marker. Desktop activation remains disabled.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools
```

The same three warmups precede the padded full-HD case. This run will prove fresh command pools are actually selected while completion witnesses and address-page caching stay enabled. Direct stderr diagnostics and live kernel capture remain active. Bring the USB back after the result. No desktop boot is armed, and no GPU-hang fix is claimed yet.

A second comparison needs a clean GPU boot: prepare-readback-boot.sh, reboot USB, then diagnose-readback.sh fresh-staging or retained. Do not mix variants in the same boot. No kernel, firmware, panel or security changes in this candidate. The policy bug and the persistent GPU hang are separate findings.

---

## Historical candidate notes

# Candidate 0.2.8 — controlled GPU-hang comparison

The recovered 0.2.7 log confirms a GPU hang during the padded readback wait: `12:1:00b79797`, then Vulkan device loss (-4) after 13.1 seconds and a context reset. The untouched 0xA5 destination follows the failed readback; it is not evidence of a proven row-stride arithmetic defect. IOKit discovery and three 1,000-frame cases passed before this failure.

This diagnostic candidate adds direct error logs and isolated lifetime controls. It is not a confirmed fix for the GPU hang. WindowServer activation is disabled during this comparison; the installer accepts readback-only mode.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once, even if macOS shows no extension-update prompt. Then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools
```

The run keeps the original three 1,000-frame warmups, then repeats the failing padded full-HD case with fresh command pools. Completion-witness commands/checks and address-page caching stay enabled. The older NVMTL_POOL_REUSE=0 switch disabled those mechanisms too; this new comparison uses a narrower NVMTL_COMMAND_POOL_FRESH switch instead.

Each case prints progress every 50 frames, stops on the first failure and saves detailed stderr directly alongside live kernel events in Desktop/reports/readback-TIMESTAMP. Historical lookup is limited to the current run. Test clients retain exact late submit/fence/readback IDs and error phases without relying on syslog throttling. Sleeping watchdog children no longer hold the terminal logging pipe open.

Bring the USB report back after this first comparison. It does not arm the desktop or automatically prepare another test boot. To compare a different profile later, first prepare a clean GPU-only boot:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/prepare-readback-boot.sh
```

Reboot through USB, then use `diagnose-readback.sh fresh-staging` (only readback staging is fresh) or `diagnose-readback.sh retained` (normal resources with the same diagnostics). Do not run variants back-to-back on the same GPU boot; the runner refuses that. A passing fresh-pool result by itself is not proof that pool reuse caused the original hang, especially if added diagnostics affect timing. A control/repeat comparison is needed.

No new kernel, firmware, panel-registration or security changes. GPU remains 1.0.7, accelerator 0.2.4, panel/claim 0.2.3 and libdrm remains the 0.2.7 IOKit correction. Correct accelerated WindowServer composition and a GPU-hang fix remain pending.

---

## Historical candidate notes

# Candidate 0.2.7 — IOKit discovery and desktop preparation

The Dell's 0.2.6 report passed all ten direct tests (1,200 frames). Forced IOKit failed before any ioctl: enumeration used temporary raw devfs opens, then the forced IOKit policy rejected them. This candidate routes forced discovery through IOKit metadata and recognizes tracked IOKit tokens as render nodes. It also falls back through IOKit when automatic discovery can read the directory but cannot query its nodes.

The IOSurface reupload path now waits for prior image accesses using the tracked old layout rather than treating every reupload as an initial discard. This is a synchronization correction for the WindowServer path, not proof its hang is cured. Readback identity traces now match the release-log filter. Kernel, panel registration, firmware and security settings are unchanged.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once. Then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

This checks IOKit first and runs 1,000 iterations in each of 22 cases. It validates actual transport counters, exact pixels, padded rows, concurrency/reuse variants and both RGBA/BGRA IOSurface backing bytes. Backing bytes are checked immediately after GPU completion, before getBytes. The low-level discovery probe has a 60-second watchdog; workload cases have a 600-second watchdog. Progress prints every 50 frames. Reports remain under Desktop/reports/readback-TIMESTAMP. The script enables the experimental GPU/panel desktop for ONE boot only after the entire suite passes; it does not reboot automatically. On failure it stops and does not enable a desktop boot.

After the all-cases-passed/desktop-enabled message, reboot through USB. If usable, exercise window movement/resizing and collect with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If black/artifacting, power off and boot USB again WITHOUT reinstalling, then collect from fallback. A passing isolated suite is not a desktop success claim.

For a short diagnostic run without arming: `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh`. Local tests pass; Intel IOKit access, IOSurface publication and physical WindowServer remain pending.

Primary references: [Khronos synchronization](https://docs.vulkan.org/guide/latest/synchronization_examples.html), [Apple IOUserClient interface](https://github.com/apple-oss-distributions/IOKitUser/blob/main/IOKitLib.h). Detailed source changes and local validation are preserved in port-artifacts/desktop-0.2.7 on the build Mac.

---

## Historical candidate notes

# Candidate 0.2.6 — isolated readback test

The last desktop test still hung the GPU. This candidate repairs two concrete readback synchronization gaps and adds a controlled reproducer. It is not a confirmed desktop fix.

The default installer now selects **readback-only**: GPU enabled for one boot, custom panel ownership disabled. Firmware scanout stays available for running the application test. Run on the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After exit=0, reboot through the USB once, then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh
```

The first run uses 100 iterations per worker/case. It checks exact pixels at 64x64 and 1920x1080, padded rows, pool/staging/texture reuse, two independent threads, serialized shared-texture handoff, and IOSurface output. Each case prints progress every 50 frames and has a 600-second watchdog. The suite stops on the first failure. Actual route counters must prove direct devfs versus IOKit; a process name alone is insufficient. Logs are saved under `Desktop/reports/readback-TIMESTAMP`. It does not automatically run another desktop boot.

After reviewing the smoke-test report, the longer gate is `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh 1000`. Passing either suite does not certify WindowServer. Do not run against a GPU already hung by a desktop attempt. If the GPU hangs, power off and boot USB again without reinstalling; the GPU opt-in is one-shot.

Readback now waits for relevant prior GPU writes, copies the requested mip/layer, makes transfer writes visible to the host, restores that subresource's prior layout, waits for completion and only then copies CPU bytes. Coherent staging is verified; invalid bounds/usage/samples and unknown/noncoherent staging are refused. `NVMTL_READBACK_STAGE_FRESH=1` selects dedicated allocations bypassing buffer pools/parking. Failure retains potentially pending memory. `NVMTL_READBACK_TRACE=1` records copy identity, resources, memory type, thread and completion. Broader shared-image recording concurrency remains unresolved pending measurements.

Reference: [Khronos CPU readback synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html) and [copy validity requirements](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyImageToBuffer.html). The prior automatic `INTEL_DEBUG=stall` experiment failed on target and is no longer selected automatically.

Local checks verify recording/error paths and the harness on Apple M4. Intel readback stability, synchronization-layer validation, full GPU error export and physical desktop acceptance remain pending. NMXGPU remains 1.0.7, NMXAccel 0.2.4, panel/claim 0.2.3; no new kernel, firmware or security changes in this candidate.

---

## Historical candidate notes (commands below describe earlier desktop experiments)

# Desktop candidate 0.2.5 — failure handling and GPU barrier experiment

Candidate 0.2.4 confirmed registration and phase-2 power-on, then a five-second fence timeout disabled the backend. WindowServer subsequently exhausted its stack retrying nil command buffers. The new plugin returns terminal-error command buffers with encoders that accept calls without issuing GPU commands. Commit reports an error; it does not report successful rendering. A native fault-injection build of the real plugin exercised 80 such buffers, error callbacks, waits and capacity release. A separate forwarding test exercised 40,000 scissor/viewport pairs under ASan/UBSan.

For WindowServer on 8086:7D45 only, this candidate selects Mesa INTEL_DEBUG=stall before initialization, unless explicitly configured already. This documented experimental mode adds cache flushes/barriers between drawing operations. It may reduce performance; it is not a confirmed cure for this GPU hang. Other applications keep the existing policy. Reference: https://docs.mesa3d.org/drivers/anv.html#debugging-tips . The five-second WindowServer fence timeout stays unchanged.

GPU 1.0.7 adds a bounded first-error register summary from state already captured by i915: no extra MMIO reads, no mode-setting changes and no full-coredump serialization. Release logs also retain the first 24 Intel submission begin/queue/fence events. These supplement the saved startup log and recovery collector. NMXAccel remains 0.2.4, panel/claim 0.2.3. No firmware, security or persistent boot-opt-in changes.

Install on the Dell with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh`. After exit=0, reboot through USB once. If usable, allow two minutes and collect with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If artifacting/black, power off and boot through USB again without reinstalling, then collect from the fallback desktop. Correct accelerated composition and GPU stability remain unverified.

# Desktop candidate 0.2.4 — pipe registration correction

The 18:38 failed boot created a pipe before manual registration; the old code rejected its unchanged count and skipped phase-2 power notifications. NMXAccel now finds a unique pipe by framebuffer identity before adding one, and only marks the head registered after validation. Refusals remain retryable. Null, duplicate and out-of-range pipe tables are rejected. Existing Sequoia private-family offsets remain a compatibility limitation.

The Metal plugin now preserves positive fence-timeout/backend-disable messages in release syslog and logs VkResult for imported allocation and command-buffer creation failures. This fixes missing diagnostic evidence; it is not a proven fix for the separate GPU hang.

On an opted-in boot the existing background loader captures 120 seconds of live WindowServer/driver logs and registry snapshots at roughly 2, 10 and 30 seconds. The following fallback boot preserves them. collect-desktop.sh copies those logs, recent WindowServer crash reports and a bounded 15-minute retained log. These are text/registry diagnostics, not a complete GPU coredump.

Local: accelerator and plugin compile for x86_64; signatures verify; identity lookup and timeout-log regression cases pass ASan/UBSan; scripts pass Bash syntax checks. Target kmutil validation and actual desktop operation remain pending. Framebuffer/claim stay at 0.2.3, GPU stays at 1.0.6, firmware and EFI recovery policy are unchanged. Extra firmware display suppression is deferred to a separate experiment.

On the Dell: run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh`. Only after desktop install exit=0, reboot through the USB once. If usable, run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If black/artifacting, power off and boot through USB again without reinstalling, then run that collector from the fallback desktop.

# Desktop candidate 0.2.3 — Meteor Lake scanout translation

Linux v6.14 i915 confirms the previous address assumption was wrong for Meteor Lake: a plane's GGTT address indexes a page table; local-memory PTEs use offsets relative to GSMBASE, and DSM starts 8 MiB above GSMBASE. The driver also documents Wa_22018444074: BAR access to stolen memory can hang MTL, so direct GSM/DSM access is used when firmware reports permission at 0x138914.

The candidate requires permission value 1, valid GSM/DSM geometry, a bounded GGTT table span, present and local-memory PTE flags, and contiguous backing pages for every page of the linear framebuffer. It accepts GOP only if its address equals the translated direct physical address or the corresponding in-range BAR alias. It then uses the verified direct DSM physical address. It rejects invalid flags, discontiguous memory, mismatched GOP or unavailable firmware access. No display or GGTT table writes are introduced. The existing pitch/format/dimension/timing checks remain. The scanout is validated only after the render driver marks initialization complete, within a five-second bound.

Local fixture tests passed under ASan/UBSan for correct direct/BAR aliases and error rejection. This does not establish hardware mapping correctness. Target values and desktop composition remain unverified. The previous report reached framebuffer probe/start and read an active 1920x1080 plane with pitch 7680 and GGTT address 0xff800000; application output tests still passed.

Run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh on the Dell. After exit=0, reboot through USB, then run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh. If it hangs, power-cycle and boot through USB again without reinstalling for the one-shot fallback.

Sources are recorded in BUILD-MANIFEST.json. Historical revision notes follow and are superseded where they differ.

# Desktop candidate 0.2.2 — explicit framebuffer loading

The start-only check in load-check-20261018-181334 exited 0 and loaded LatitudeMTLFB 0.2.1 into the Dell kernel with no approvals required. This establishes code loading only, not panel attachment or composition. The automatic provider/matching handoff remains unresolved.

This revision removes the early reservation's registry-busy hold. The actual framebuffer retains its readiness hold and existing physical validation. An installed root LaunchDaemon (com.ved.latitude-panel-load) checks for an opted-in active LatitudePanelClaim service at boot, then requests kmutil load --load-style start-and-match -b com.nullmoth.LatitudeMTLFB. Without a reservation it skips loading. Its output is saved at /Library/Logs/LatitudePanelLoad.log and copied into collector reports. The job and helper are backed up/restored by the desktop installer and rollback script. No live WindowServer restart is performed.

Run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh on the Dell. After exit=0, reboot through the USB, then run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh. This candidate is unverified. If the desktop hangs, power-cycle and boot through USB again without reinstalling; both opt-ins should have been consumed. Bring back the reports.

Historical notes below describe previous revisions and are superseded where they differ.

# Desktop candidate 0.2.1

The 15:43 report confirms OpenCore now injects LatitudePanelClaim successfully and the kernel loads it. Application Vulkan/Metal output tests still pass. No reservation service appeared, the panel one-shot remained unconsumed, and the display has no associated Metal device. Desktop composition remains unverified.

The early reservation no longer requires GOP information and BAR memory descriptors during probe. Those checks remain in the real framebuffer before scanout adoption. Probe still verifies the exact Dell PCI/subsystem identity and consumes the single-boot opt-in. Its registry diagnostics identify whether probe ran, why it declined, and whether reservation started. The personality matches 8086:7D45; subsystem validation remains in probe code rather than an additional personality filter.

Run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh. After success reboot through USB, then run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh. All safeguards and backup/rollback paths from 0.2.0 remain. This revision is unverified on the Dell.

Historical notes follow.

# Desktop candidate 0.2.0 — early reservation, Auxiliary KC framebuffer

Run /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh with sudo /bin/bash on the Dell. After success, reboot through the USB, then run collect-desktop.sh. This revision is unverified on the Dell.

The early driver LatitudePanelClaim inherits IOService and needs no IOGraphicsFamily vtable in Boot KC. It reserves the IOFramebuffer match category only for 8086:7D45 / subsystem 1028:0CB6, validates GOP lies in the aperture, consumes nullmoth-panel-once, then publishes as the provider for LatitudeMTLFB. The real framebuffer is installed in /Library/Extensions and linked into the Auxiliary KC, where target validation can resolve IOGraphicsFamily. It finds PCI through the claim provider, performs the existing physical plane/timing validation and joins NMXAccel. No standalone Apple graphics executable is copied or forced.

The claim holds the registry busy for up to 45 seconds. A successfully started framebuffer releases the parent hold and uses the existing NMXAccel readiness hold. If no framebuffer has attached at the deadline, the claim releases itself and requests firmware rematching; this fallback is unverified on hardware. The next boot skips the claim because the opt-in was consumed. Both boot gates must be rearmed by the installer for another experiment.

The installer disables the previous direct LatitudeMTLFB OpenCore entry, injects LatitudePanelClaim, validates all five kexts against the target collections and backs up runtime/AuxKC/USB EFI. rollback-runtime.sh restores all managed paths and both EFI bundles. The existing Acceleration package remains the passing application baseline.

0.1.1 failed because the target standalone IOGraphicsFamily executable was absent. Its log records successful automatic rollback. That approach is superseded by this split-loading design. The previous report showed application Vulkan/Metal output passing, but no display-associated Metal device and no accelerated desktop composition.

The historical implementation notes below describe prior candidates. Their direct framebuffer injection and Kernel Force instructions are superseded.

# Latitude 5350 desktop composition candidate 0.1.0

The separate Acceleration package remains the passing application compute/render baseline (NMXGPU 1.0.6). This candidate adds a physical-panel framebuffer and NMXAGDC display bridge for WindowServer. It is not yet validated on the Dell.

Run on the Dell while Sequoia boots normally:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/install-runtime.sh
```

Only after installation succeeds, reboot through the same USB. The installer first validates all four kexts against the target kernel collections. It installs NMXAGDC alongside the existing render runtime, injects LatitudeMTLFB through the USB OpenCore config for early framebuffer matching, backs up EFI/config and runtime/AuxKC under /Library/NullMoth/latitude5350-backups, then arms both single-boot opt-ins. It does not reboot or terminate WindowServer.

After login:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/collect-runtime.sh
```

The collector reruns the Vulkan and Metal output proofs, records the framebuffer and AGDC state, checks each display's associated Metal device, and moves a small diagnostic window for six seconds while collecting presentation counter changes. It records WindowServer logs and mapped libraries. A working Metal app or visible diagnostic window alone does not prove desktop GPU composition; the report must establish the display association and active accelerated presentation path.

If the desktop hangs or is black, power-cycle and boot through the same USB again. The framebuffer and GPU opt-ins are consumed during probe, so the following boot should skip both experimental paths. Then collect logs, or restore the previous runtime and USB EFI:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/rollback-runtime.sh
```

The USB must remain connected for EFI restoration. If rollback cannot be run after a failed boot, the original USB config is also retained on the build Mac under backups/20261018-before-desktop.

The framebuffer is based on the reference project's NMXVGAFB IOFramebuffer and uses its existing NMXAccel two-phase display registration, AGDC bridge and frame-copy path. It keeps NMXIntelVGAFB as its IOKit class because CoreDisplay classifies Intel framebuffers by class name. Its bundle identifier is com.nullmoth.LatitudeMTLFB and its only personality matches PCI 8086:7D45 / subsystem 1028:0CB6. No VF blocker personality is installed.

The physical adaptation reads Intel plane, stride, surface, transcoder timing and frame-counter registers. It requires the active linear 32-bit XRGB surface to match GOP address, size and pitch, validates the aperture bounds and timing, measures refresh, and uses those timings instead of the QEMU 120 Hz assumption. It declines if another active framebuffer already exists. Virtio initialization is disabled in this build. The firmware scanout stays fixed: GPU composition is copied into it by the existing display pipe; direct GPU page flipping, modesetting and zero-copy physical scanout are not implemented.

Sources: https://github.com/ericek111/vibe-nullmoth-xe3-qemu and https://github.com/nullmoth/nvidia-macos-driver . Local source/build paths and hashes are recorded in BUILD-MANIFEST.json and port-artifacts on the build Mac.

## 0.1.1 — boot dependency correction

Report 20261018-152728 preserves passing application tests but shows no desktop GPU association. OpenCore reports IOGraphicsFamily absent from Boot KC, then vtable patching failure and Invalid Parameter for LatitudeMTLFB. The panel one-shot remains unconsumed. The installer now requests the target system's IOGraphicsFamily via Kernel/Force, processed before Kernel/Add, and records its target Info.plist. No substitute Apple driver or vtable bypass is used. This boot change is unverified on target. Re-run install-desktop.sh, reboot through USB after success, then collect-desktop.sh. The collector now copies the newest OpenCore log into the report. Reference: https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/Configuration.tex (Kernel Force).
