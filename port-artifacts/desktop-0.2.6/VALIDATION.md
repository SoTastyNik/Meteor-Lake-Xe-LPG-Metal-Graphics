# Candidate 0.2.6 local validation

Copy-plan tests and the actual extracted readback/transport implementations passed ASan/UBSan. The readback test records producer dependency → copy → transfer/host dependency → subresource restoration → completion, then checks padded CPU output. Simulated timeout preserves output and retains memory; command-begin failure and noncoherent staging are rejected safely. Transport fixtures verify actual branch logic and fail-closed direct/IOKit routing. These tests mock Vulkan/IOKit calls and cannot validate GPU execution.

A native fault-injection build of the plugin passed 80 error command buffers with terminal encoders, completion callbacks and capacity release. The x86_64 release plugin contains no compile-time fault injection.

The native Apple M4 test harness passed 2,000 shared-texture handoff frames, 100 full-HD padded IOSurface frames, and independent raw/fresh-texture frames. These results validate the workload and exact-pixel checker on Apple hardware, not the Intel driver or Intel compiler.

x86_64 plugin, libdrm and isolated test executable built; signatures and USB package hashes verified separately. The installer and runner pass bash -n. Readback-only mode removes the panel one-shot and arms only the GPU one-shot.

Pending: Intel smoke test, 1,000-frame test matrix, driver allocation-growth analysis, synchronization-validation-layer proof, broader shared-image ownership, conditional kernel capture expansion and physical WindowServer acceptance. No desktop-success claim.
