## Candidate0.3.1 prepared: NMXGPU1.0.8 GuC wait compatibility fix

The verified0.3.0 test passed4,000frames with zero live command pools. A GuC TLB-invalidation timeout preceded the fifth process, which later hung on upload#1285 at frame428. Fresh pools remain enabled but do not establish complete stability.

A deterministic test of actual scheduler/i915 wait code reproduced a pre-enrollment lost wake in the LinuxKPI woken callback. Kernel1.0.8 persists the task wake state under the sleep-channel lock.100,000sanitizer scenarios and438-object kernel link pass; no new undefined symbols. This fixes a verified software race; target hang causation and hardware validation remain pending.

Next: install-readback.sh; after exit=0 reboot USB once; test-and-arm-desktop.sh. Full22case gate now requires the loaded1.0.8UUID and rejects timestamped kernel TLB errors/hangs/resets. Log-filter/command metadata are excluded. Driver/plugin/firmware/display policies otherwise unchanged; no automatic reboot. Research: fresh-pool-guc-research.md.

