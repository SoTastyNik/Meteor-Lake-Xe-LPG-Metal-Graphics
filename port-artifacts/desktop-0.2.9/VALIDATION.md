## Candidate 0.2.9 effective-policy repair prepared

The latest 0.2.8 test (readback-20261018-231611) hit GPU HANG 12:1:00b79797 at frame 169. It does not test fresh pools: release initialization stripped NVMTL_* settings, including the experimental flags and direct diagnostics. The policy file only recorded intent. No conclusion about pool reuse is justified.

The fix narrowly preserves explicit controls for the named test process and adds an in-driver effective-policy query. Each workload refuses to run unless the actual post-initialization policy matches the requested profile. Tests against the real native release plugin constructor passed for all three profiles, unrelated controls and another process. Desktop activation remains disabled; target validation remains pending.

Next: install-readback.sh, reboot USB, then diagnose-readback.sh fresh-pools. No GPU-hang cure is claimed.


Local fixture outputs are stored here. Mocked test runs do not exercise Intel hardware. The 0.2.9 release plugin is x86_64 and ad-hoc signed. USB hashes/signature and shell syntax are checked separately.
