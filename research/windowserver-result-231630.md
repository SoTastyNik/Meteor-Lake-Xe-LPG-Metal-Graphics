# Dell result: registry reporting confirmed; smoothness remains unresolved

Collected failure-detail-20261019-231630 on the active desktop boot beginning 23:14:31 BST, 19 October 2026, Sequoia 15.8.1 build24H32. Exact loaded components match GPU1.0.15, framebuffer0.2.5, accelerator0.2.4, plugin0.3.6 and guarded HID1.0.1.

## Confirmed reporting fix

System Information JSON shows GPU name **Intel(R) Graphics (MTL)** and **12288 MB shared memory**. The root reporter independently queried 12884901888 bytes from the ANV device-local shared heap and 17179869184 bytes physical RAM, and verified PCI model/VRAM,totalMB readback. The registry agrees. This establishes the new reporting path on the target, with no fixed-name or 2GiB injection. It is shared allocation capacity, not dedicated VRAM or current free RAM. Actual physical scanout IOFBMemorySize remains 8294400 bytes by design.

## Choppy animation evidence

The live capture spans approximately 23:14:39–23:16:31. WindowServer stays PID163. Three CPU snapshots show 163.4%, 205.5% and 127.8% (macOS CPU percentages can exceed 100% across cores). There are 42 CoreAnimation synchronization/fence timeout lines. These are distinct from the bounded GPU submission trace: all24 logged initial fence completions return0; all32 logged initial readback completions return0. Those are trace caps, not the total number of frames and not an FPS benchmark. No GPU HANG, device-lost or wedged-on-init failure is present in this capture.

The 23:14:48 early sample includes render-pipeline creation, ANV shader preprocessing and SPIR-V/NIR compilation in the composition path. This is evidence of early compilation cost, not proof that compilation explains continuing steady-state choppiness. Host-pointer imports remain unavailable; surfaces use the existing private-image/copy path. Eight bounded buffer texture format-view refusals also appear. The exact contribution of compilation, copies, event synchronization and present pacing has not yet been isolated. A specific trackpad input fault is not established by this report.

Collected42 WindowServer diagnostic files and6 panic files are historical. Their timestamps do not indicate a new crash or panic in this 23:14 boot; the latest panic referenced by .contents.panic is18:39:21, and the retained22:40 CPU-resource diagnostic belongs to the preceding desktop. Do not treat the collector's 48-hour copy count as current failures.

## Next focus

Preserve this usable, correctly named/shared-memory-reporting candidate. Remaining work is composition latency and synchronization: distinguish first-use pipeline compilation from steady-state presentation cost, trace the CoreAnimation event/fence path and software cursor/frame-copy pacing, and measure frame timing before changing scheduling or adding speculative synchronization workarounds. No full22-case/26000-frame suite rerun is needed. This log review did not change executable payloads, EFI, boot markers or run GPU tests.
