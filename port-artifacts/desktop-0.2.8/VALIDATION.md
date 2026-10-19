## Candidate 0.2.8 diagnostic comparison prepared

Recovered 0.2.7 evidence confirms GPU HANG 12:1:00b79797 and readback VK_ERROR_DEVICE_LOST after 13,072 ms, followed by a context reset. IOKit access passed; correct WindowServer remains unverified.

The USB now contains plugin 0.2.8 with direct per-test diagnostics and a command-pool-only fresh-allocation switch. The same three warmups precede a single retained/fresh-pool/fresh-staging comparison. Witnesses and address-page caching stay on in the fresh-command-pool case. The runner checks boot UUIDs and refuses another comparison in the same boot. Kernel events are captured live and historical lookup starts at the current run. Desktop activation is disabled in this candidate; no GPU-hang cure is claimed.

Next target step: install-readback.sh, reboot USB once, then `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools`. Return the first report before selecting the next clean-boot variant. Further variants require prepare-readback-boot.sh and a USB reboot. Full instructions: Desktop/README.md.


Local fixture outputs are stored here. Mocked test runs do not exercise Intel hardware. The 0.2.8 release plugin is x86_64 and ad-hoc signed. USB hashes/signature and shell syntax are checked separately.
