# Desktop candidate 0.2.4

- Accelerator compiled and linked for x86_64 Sequoia; KMOD and CFBundleVersion 0.2.4.
- Release Metal plugin compiled and linked for x86_64 with Foundation, Metal, IOSurface and IOKit; CFBundleVersion 0.2.4.
- Registration identity fixture and release-timeout logger regression fixture passed AddressSanitizer and UndefinedBehaviorSanitizer.
- Installer, collector, rollback and boot loader pass Bash syntax checks.
- Packaged kext/plugin signatures and all 71 USB package SHA-256 entries verified.
- Target kmutil preflight and boot/presentation tests remain pending; this ARM build Mac cannot validate the target private graphics-family ABI or reproduce the Dell GPU hang.
- Previous binaries and source inputs retained in backups/desktop-0.2.4-before.
- No changes to active USB EFI/config.plist, panel registers, firmware, i915 binary or the app-only Acceleration package during this revision.

The installer retains target preflight, backups/rollback and one-boot GPU/panel opt-ins. A failed boot is recovered by booting through USB again without reinstalling. The live log persists for collection from that fallback boot.
