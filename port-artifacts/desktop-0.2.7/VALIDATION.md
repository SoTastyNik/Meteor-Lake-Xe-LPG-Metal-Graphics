## Candidate 0.2.7 prepared — target validation pending

0.2.6 passed all 10 direct cases on the Dell (1,200 frames, report 20261018-201754). Forced IOKit failed during enumeration before any ioctl. The new candidate fixes inconsistent forced-route enumeration and token node classification, adds automatic IOKit discovery fallback, and corrects prior-access synchronization during IOSurface reuploads. It also fixes the release filter prefix so image/staging traces are retained.

The revised suite tests IOKit first, probes metadata and nested-pointer ioctls, and checks actual RGBA/BGRA IOSurface backing pixels immediately after GPU completion. `test-and-arm-desktop.sh` runs 1,000 iterations across 22 cases and enables ONE desktop boot only if all cases pass. It does not reboot automatically. Use install-readback.sh, reboot USB once, then test-and-arm-desktop.sh. Details: Desktop/README.md.

Local ASan/UBSan routing/discovery/barrier/failure tests and native Apple M4 harness checks pass. They do not establish Intel IOKit correctness or WindowServer success. Both still need the target test. Shared-image recording concurrency and broader display features remain unverified.


See enumeration.txt, barriers.txt, recording.txt, transport.txt and arming.txt for local fixtures. Native RGBA/BGRA backing-pixel tests each checked 100 full-HD frames on Apple M4. The current plugin fault-injection regression passed 80 failed command buffers. Hardware results are pending.
