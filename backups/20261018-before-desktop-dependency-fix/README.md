# Latitude 5350 desktop composition candidate 0.1.0

The separate Acceleration package remains the passing application compute/render baseline (NMXGPU 1.0.6). This candidate adds a physical-panel framebuffer and NMXAGDC display bridge for WindowServer. It is not yet validated on the Dell.

Run on the Dell while Sequoia boots normally:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/install-runtime.sh
```

Only after installation succeeds, reboot through the same USB. The installer first validates all four kexts against the target kernel collections. It installs NMXAGDC alongside the existing render runtime, injects LatitudeMTLFB through the USB OpenCore config for early framebuffer matching, backs up EFI/config and runtime/AuxKC under /Library/NullMoth/latitude5350-backups, then arms both single-boot opt-ins. It does not reboot or terminate WindowServer.

After login:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/collect-runtime.sh
```

The collector reruns the Vulkan and Metal output proofs, records the framebuffer and AGDC state, checks each display's associated Metal device, and moves a small diagnostic window for six seconds while collecting presentation counter changes. It records WindowServer logs and mapped libraries. A working Metal app or visible diagnostic window alone does not prove desktop GPU composition; the report must establish the display association and active accelerated presentation path.

If the desktop hangs or is black, power-cycle and boot through the same USB again. The framebuffer and GPU opt-ins are consumed during probe, so the following boot should skip both experimental paths. Then collect logs, or restore the previous runtime and USB EFI:

```bash
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/Desktop/rollback-runtime.sh
```

The USB must remain connected for EFI restoration. If rollback cannot be run after a failed boot, the original USB config is also retained on the build Mac under backups/20261018-before-desktop.

The framebuffer is based on the reference project's NMXVGAFB IOFramebuffer and uses its existing NMXAccel two-phase display registration, AGDC bridge and frame-copy path. It keeps NMXIntelVGAFB as its IOKit class because CoreDisplay classifies Intel framebuffers by class name. Its bundle identifier is com.nullmoth.LatitudeMTLFB and its only personality matches PCI 8086:7D45 / subsystem 1028:0CB6. No VF blocker personality is installed.

The physical adaptation reads Intel plane, stride, surface, transcoder timing and frame-counter registers. It requires the active linear 32-bit XRGB surface to match GOP address, size and pitch, validates the aperture bounds and timing, measures refresh, and uses those timings instead of the QEMU 120 Hz assumption. It declines if another active framebuffer already exists. Virtio initialization is disabled in this build. The firmware scanout stays fixed: GPU composition is copied into it by the existing display pipe; direct GPU page flipping, modesetting and zero-copy physical scanout are not implemented.

Sources: https://github.com/ericek111/vibe-nullmoth-xe3-qemu and https://github.com/nullmoth/nvidia-macos-driver . Local source/build paths and hashes are recorded in BUILD-MANIFEST.json and port-artifacts on the build Mac.
