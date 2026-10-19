# Verified 0.3.1 full hardware gate — 2026-10-19

Report: Desktop/reports/readback-20261019-114424. Window11:44:24–11:56:28, bootUUID1345EE7C-A520-434A-BA9F-A9CA1D7F25D7. Loaded NMXGPU1.0.8 UUID CA03CFB3-FE4C-30A5-8565-2A8A705601B7 matches candidate. All22case logs independently checked:11IOKit+11direct,26000exact frames including padding, threaded cases andRGBA/BGRA IOSurface backing verification. Actual loaded policy and transport markers match allcases.

Pool totals80020created/80020destroyed. Every case has zero live,pending,quarantined and created=destroyed=completed+abandoned. Peak concurrent pools2 in independent-worker cases; otherwise1. These are command-pool object counts, not a guarantee for all driver memory caches or indefinite OS-loop lifetime.

Suite exit0; desktop gate present and current. Installed plugin/libdrm/kernel hashes recorded in gate match USBpackage. Live+historical reports inspected: no captured kernel GPUhang,TLBtimeout/reset orfault events. hang-check.txt empty. Full hardware gate and desktop preparation exit0. Root arm log explicitly reports one desktop boot armed; noautomaticreboot. Physical WindowServer/panel test and longer soak remain pending. Passing26kframes supports candidate stability for this matrix; not definitive proof of hardware hang root cause or desktop correctness.

Next: return USBtoDell and bootthroughitonce. Inspect physical desktop. If artifacts/hang, poweroffandbootUSBagain forfallback; collect-desktop-failure.sh before reinstalling. Do not require rerunning hardware suite for this already-armed immediate desktop test unless boot opt-in was consumed by another boot.
