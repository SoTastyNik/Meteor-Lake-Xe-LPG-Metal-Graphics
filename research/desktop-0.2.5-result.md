# Desktop 0.2.5 target result — GPU stall remains

Report Desktop/reports/20261018-194932; experimental boot 19:46:56 on 18 October 2026. Installer and framebuffer load succeeded. The recovery boot at 19:48:57 skipped the reservation, preserving active-boot diagnostics. Current fallback Vulkan failure is not a new measurement of the active experimental boot.

Confirmed:
- recent-desktop-history.txt:1681–1714: existing pipe 0 identity verified, active=1, phase 2 complete.
- Line 1830: the exact-device WindowServer INTEL_DEBUG=stall policy was enabled. Therefore this is an actual negative result for that mitigation, not a missed configuration.
- Lines 2305–2329: first four plugin submissions return VK_SUCCESS from queue and fence operations. They comprise an upload, submit-ahead part, readback and another command-buffer part. Fence completion establishes executed/completed work, not correct final desktop pixels.
- Lines 2334–2372: first recorded stalled submission is #5, nvmtl_vk_image_read. Submission #6, a surface upload on the main thread, also times out. Both queue calls initially return success; fence waits return VK_TIMEOUT after 5000 ms.
- Lines 2378 onward: terminal-error command buffers are returned, with retries spaced roughly 16 ms instead of the previous tens-of-thousands of recursive calls in milliseconds.
- Crash report WindowServer-2026-10-18-194721.000.ips covers pid 163 at 19:47:11.6822: EXC_CRASH/SIGABRT, namespace COREANIMATION, details `spec=PBGRAXb_Xh`, `pipeline: Vulkan is not up in this process`. Its 56 recorded frames do not show the previous stack-guard exhaustion. Thus the old recursion failure is absent, but WindowServer still aborts through pipeline failure after backend shutdown. The application is not recovered by terminal-error buffers.
- Subsequent WindowServers pids 371, 396, 402 and 431 also abort in SkyLight MetalShader::CopyPipelineState after their first uploads time out. Repeated process restarts do not revive the already-stalled GPU.
- Line 3069: i915 reports rcs0 request 8:14 not yet started, followed by GPU HANG at 19:47:18.749.

First-error summary (lines 3071–3078): reset_count=0, suspended=0, awake=1; EIR/PGTBL_ER/fault_data=0. GuC CT0 head=0 tail=509 and CT1 head=174 tail=0. Hung engine captured IPEHR=ff000000, INSTDONE=ffdfffff, request head/post/tail=870/940/9d0. Ring start/head/tail and context pid are zero in this captured record. Those zero/unavailable fields cannot establish the absence of a memory fault or identify a scheduling defect. The summary is incomplete compared with a full GuC context and command-stream capture.

Four presentation transactions were logged, but each sampled 64 zero pixels. Correct accelerated desktop output remains unconfirmed. The barrier mitigation did not fix the GPU stall; failure handling changed the crash mode but did not keep WindowServer alive.

Next investigation should focus on the first blocked image readback and the request/context/dependency state it submits, including resource lifetime/reuse and the sandboxed transport. Do not assume all-zero captured registers prove a specific hardware cause, and do not extend timeouts as a substitute for resolving the stall. No driver, firmware or EFI changes were made during this log review. Do not repeat the same candidate installation as another experiment.
