# Recovered 0.2.7 failure evidence

Source: Desktop/reports/readback-failure-20261018-204706/failure-window.txt. Narrow historical capture completed (exit=0). The log tool reported a wall-clock-adjustment warning, so timestamps should be corroborated with boot/uptime when doing fine-grained ordering.

At 20:37:14.957 the kernel reports GPU HANG ecode 12:1:00b79797. Engine 0 is marked hung. The bounded capture has IPEHR ff686868 and INSTDONE ffdfffff; ring/batch fields are zero/incomplete, so they do not identify the faulting command. At the same timestamp the padded readback test (pid 867) reports fence wait result -4 (VK_ERROR_DEVICE_LOST) after 13,072 ms, with a 60,000 ms budget. It disables its Vulkan backend and reports texture getBytes readback FAILED. The kernel then reports context reset due to GPU hang.

Therefore the 0xA5 mismatch follows a real GPU hang/device loss during the readback wait, not merely a successful copy with a wrong first pixel. It is not a 60-second application watchdog expiry. This does not prove the readback copy caused the hang: preceding queued work, resource lifetime, command reuse and the kernel/transport path remain possible causes.

All of this occurred in an isolated test with no panel claim; the current NVRAM capture has neither panel nor GPU one-shot present. The accelerated desktop was not armed by this failed suite. The coloured line cannot be tied to a specific cause from these logs.

Next controlled target work: retain exact warmup and failing full-HD/padded workload; capture stderr and kernel live; compare retained resources with only fresh command pools, then only fresh staging, on clean GPU boots after any hang. Do not combine switches or run the next variant on an already hung GPU. Local diagnostic 0.2.8 exists but USB runtime remains 0.2.7; no verified GPU execution fix yet.
