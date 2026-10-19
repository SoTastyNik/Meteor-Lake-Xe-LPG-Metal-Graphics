# Latitude 5350 port status — 18 October 2026, after desktop 0.2.5

The current plan is [ROADMAP.md](ROADMAP.md). It replaces the earlier status page's obsolete statement that the runtime is untested.

Application GPU output was demonstrated in earlier Dell reports: Vulkan compute, Metal compute and the small Metal pixel-output test passed. This is limited test coverage, not broad application compatibility or stability certification.

Physical-panel desktop acceleration is still failing. The latest experimental boot, preserved in Desktop/reports/20261018-194932, verifies framebuffer attachment, existing display-pipe identity, phase-2 power notifications and an active pipe. The first four traced GPU submissions complete; submission #5 (image readback) and the following upload time out. The render engine subsequently hangs. Presentation samples remain zero and the user sees artifacts.

The 0.2.5 command-buffer change removed the previous stack-overflow crash signature from this test, but WindowServer still aborts when the backend is unavailable and restarts repeatedly. INTEL_DEBUG=stall was enabled and did not cure the hang. Neither is a successful desktop result.

Current desktop package: NMXGPU 1.0.7, NMXAccel 0.2.4, LatitudeMTLFB/LatitudePanelClaim 0.2.3 and NVMTLDriver 0.2.5. The separate Acceleration package remains the earlier application-testing package. Reports collected on the fallback boot with the one-shot GPU inactive must not be confused with tests of the active experimental boot.

Next work: prepare an isolated full-size readback reproducer and resource-correlated trace; audit readback host visibility, layout/subresource ownership and resource reuse; compare direct versus verified IOKit transport. Investigate the first GPU error using that evidence. The roadmap defines promotion criteria before another physical-desktop candidate.

No reboot or reinstall is requested for this documentation update. Do not repeat the unchanged 0.2.5 installation as a new experiment. The existing one-boot opt-ins, target preflight, backups and rollback remain in place. If recovery is needed after an opted-in failed boot, boot through the USB again without reinstalling, then collect-desktop.sh from the fallback desktop.

Security/EFI history: the earlier USB setup used csr-active-config Data 430A0000, SecureBootModel Disabled, Lilu and AMFIPass. This roadmap update changes none of those settings. Their original backups remain under iGPU-Port/backups and on the build Mac.

Detailed evidence: [0.2.5 result](desktop-0.2.5-result.md), [0.2.5 implementation](desktop-0.2.5-implementation.md), and [parsed timeline/crashes](desktop-roadmap-evidence.json). Hardware video decode, sleep/wake, brightness, modesetting, external displays and complete desktop support remain unverified.
