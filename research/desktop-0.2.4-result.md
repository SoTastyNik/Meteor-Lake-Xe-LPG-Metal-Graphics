# Desktop 0.2.4 target result: failed rendering; registration correction confirmed

Report: Desktop/reports/20261018-191454. Retained failed boot: 19:12 on 18 October 2026. The later collector ran on the fallback boot, so its failed Vulkan/i915 tests do not measure the active experimental boot.

Confirmed changes:
- recent-desktop-history.txt:1738: head 0 resolves to verified pipe 0, already adopted by family.
- Lines 1766–1771: accelerator enabled, pipe active=1, wsaaDefer=0; phase-2 identity verification and power notifications complete.
- Saved active-boot registry reports NMXDisplay=armed. This is driver initialization state, not an independent proof of GPU composition.
- Lines 2369–2374: one 1920x1080 presentation transaction copies an IOSurface into the panel. Its 64 diagnostic samples are all zero. This establishes that the transaction/copy path was entered; it does not establish correct rendered pixels.

Remaining failure:
- LatitudeDesktopLive.log:7055/7122/7418: host allocation imports return -1000072003 (VK_ERROR_INVALID_EXTERNAL_HANDLE); private-image/copy fallback is attempted. This does not by itself establish the cause of the later hang.
- Lines 13374/13473: fence waits return 2 (VK_TIMEOUT) after 5000 ms. The plugin disables its backend. This formerly filtered message is now retained.
- Lines 13474 onward: upload, buffer creation and command-buffer creation then fail. These later failures are consistent with the already-disabled backend and must not automatically be diagnosed as independent out-of-memory failures.
- WindowServer-2026-10-18-191306.ips describes pid 163 at captureTime 19:12:58.7296. EXC_BAD_ACCESS / KERN_PROTECTION_FAILURE is inside the main thread's STACK GUARD. The 512 recorded frames contain 255 RenderEncoder and 254 SetScissor calls. The top frames are NVMTLDriver nvlog and NVMTLCommandQueue commandBuffer. This is strong evidence of stack exhaustion through recursive SkyLight rendering after command-buffer failure, rather than proof of a standalone nvlog memory bug. The ultimate GPU-stall cause remains unknown.
- LatitudeDesktopLive.log:27361: kernel reports GPU HANG 12:1:00dfffff at 19:13:06.637. Detection comes after the plugin timeout; it does not establish when the GPU first stopped progressing.

Next implementation should investigate the first uncompleted GPU submission and its error state, and handle backend loss without triggering the observed command-buffer/render recursion. Increasing the five-second timeout alone would not demonstrate a fix. Keep the registration correction; no evidence supports undoing it. Do not repeat the same 0.2.4 install as a new test. No additional driver or EFI changes were made while examining this report.
