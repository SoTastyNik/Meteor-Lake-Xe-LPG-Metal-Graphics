## Candidate 0.3.0 fresh-pool enforced prepared

The master plugin now creates fresh command pools everywhere and destroys completed pools immediately after fence/witness completion. Pool cache/pop/push paths are removed; queue initialization no longer leaks an unused pool, and dummy initialization uses the common tracked allocator. Unsubmitted allocations clean up promptly. Uncertain GPU completion is quarantined and blocks the hardware gate.

Local compilation, sanitizer lifetime/completion checks, release constructor policy checks and mocked full 22-case/arming guards pass. USB signatures and hashes are verified. These are local checks; 0.3.0 has not yet passed the Dell hardware checklist or accelerated WindowServer/panel test.

Next on Dell: install-readback.sh; after exit=0 reboot USB once; then test-and-arm-desktop.sh. The script runs all 22 cases (1000 iterations each worker) and arms one desktop boot only after the current-run gate passes. No automatic reboot. Keep using the one-shot fallback after a failed panel boot.


Validation logs and frozen source files are stored in /Users/ved/Documents/iGPU Port/port-artifacts/desktop-0.3.0. Target hardware validation remains pending. No firmware, kernel, SIP or framebuffer changes in 0.3.0.
