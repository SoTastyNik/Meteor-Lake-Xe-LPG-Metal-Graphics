# Installer validation repair — 2026-10-19 16:44:46 report

The installer exited2 before arming. It restored the previous GPU bundle, auxiliary collection, plugin and capture tools and cleared both one-shot markers. This attempt did not test accelerated WindowServer.

The saved kernel-final-path.txt contains three XML plists with NUL padding. The auxiliary collection's exact com.nullmoth.NMXGPU record contains version1.0.9, OSBundleUUID E770B985-14A4-3ADE-A1EE-63204C3A9996, executable Contents/MacOS/NMXGPU, nonzero executable size and permanent bundle path /Library/Extensions/NMXGPU.kext. The collection was not missing this driver. However, kmutil inspect with --show-kext-uuids and -b produced collection headings and no extension rows. The installer incorrectly treated this empty output as a UUID mismatch.

The installer now validates the structured prelink record through an ad-hoc signed universal Foundation helper. It requires exactly one matching bundle identifier across the dumped collections and checks its own binary UUID data, version, executable, size and permanent path. It rejects malformed XML, missing/duplicate records and UUIDs attached to other drivers. It does not remove identity checks or accept the empty UUID listing. Codesign verification and package hashes cover the new helper before installation changes.

Local verification: compiled arm64+x86_64 with warnings as errors; saved target output accepted; wrong UUID/path/version, missing/duplicate record, foreign UUID, empty executable and malformed XML rejected. Actual installer and kernel-update helper with mocked OS operations pass their success, guarded repair, failure and rollback cases with structured prelink records. Earlier mocks supplied an unrealistically successful UUID listing and missed this bug; regression now exercises the actual data format.

GPU/plugin binaries unchanged. No hardware suite rerun. Successful installer completion and the next real desktop trial remain required. This repairs the installer, not a demonstrated WindowServer GPU-hang cure.
