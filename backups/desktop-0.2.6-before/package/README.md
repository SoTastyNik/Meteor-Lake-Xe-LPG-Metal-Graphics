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
