# NMXGPU 1.0.13: keep firmware-owned stolen memory out of i915

Hardware desktop status: NOT VERIFIED. No guaranteed fix has been found online. This is a targeted ownership correction supported by source inspection, not proof that the previous hung ring occupied the live panel buffer.

## Evidence and proposed mechanism

The 18:00:32 Dell report for kernel 1.0.12/framebuffer 0.2.4 still records command-ring words changing to 0xff000000. Readback submission 8 completed; render/event submission 9 timed out. GuC IPEHR contains the same value. This identifies corrupted command data but not its writer.

The source audit found a missing ownership boundary:

1. The local Intel display-device probe explicitly skips display discovery for 8086:7d45 to preserve the firmware panel. LatitudeMTLFB continues CPU scanout copies into DSM at host physical 0x60800000, length 8,294,400 bytes. The scanout PTEs begin at stolen offset 0x800000 (MTL DSM starts eight MiB after GSM).
2. i915 still creates the MTL stolen-local memory region. Its allocator normally excludes reserved firmware regions at the top and the initial allocation bias, not every active framebuffer automatically.
3. Linux's initial-plane handoff reserves the existing framebuffer with i915_gem_object_create_region_at(... I915_BO_PREALLOC). The skipped display path never performs that handoff here.
4. create_ring_vma tries local memory, then stolen memory on aperture-equipped non-LLC devices, then internal system memory. The MTL device definition has has_llc=0. Thus the port permits a command ring to be allocated from the same DSM pool that the panel still uses. Other kernel objects can use that pool too.

This explains a possible pixel-write source specific to physical desktop activity. Existing logs do not contain the damaged ring's backing allocation, so the overlap is not established for that particular ring. GPU virtual address 0xa9d000 cannot be treated as its physical address. The early generic stolen-base=0 message is also not proof of physical allocation at zero: MTL uses its separate BAR/offset setup.

## Change

In intel_memory_regions_hw_probe, under NMXKPI and device ID 7d45 only, skip creating both stolen-local and stolen-system regions. Leave ordinary system memory available and leave firmware display/GGTT reservations intact. The standard ring allocation function then falls back to internal system memory when no stolen region exists. No DSM allocation, release, or framebuffer reservation is partially initialized by this skip.

A ring-pin log records stolen=0/1, size, and GGTT virtual address so the next failure collection can verify the actual ring path. This log does not claim a physical address or identify a writer. No new firmware, timeout, reset, queue, Metal plugin, or display timing changes.

## Research checked

- Linux v6.14 stolen allocation and MTL region setup: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gem/i915_gem_stolen.c
- Linux v6.14 ring backing selection: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gt/intel_ring.c
- Linux v6.14 initial plane framebuffer reservation: https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/display/intel_plane_initial.c
- VM reference: https://github.com/ericek111/vibe-nullmoth-xe3-qemu . Its cache flush changes already exist in this tree. Its successful Xe3 SR-IOV/virtio display is not validation of the Dell's i915/physical-panel path.
- Upstream NVIDIA releases: https://github.com/nullmoth/nvidia-macos-driver/releases . NVIDIA presentation fixes do not establish a cure for this ring corruption.
- Upstream split commit a7f16b03 says Intel/AMD moved to a separate repository. A corresponding public repository was not found in the owner's public repository listing; no newer Intel fix was retrieved from it.
- Historical Intel discussion of pixel-looking overwritten commands: https://lkml.iu.edu/1701.1/03475.html . This supports investigating CPU/GPU writes and mapping correctness; it is different hardware and is not a matching fix.

## Validation and target workflow

Local sanitizer regression compiles the actual region-probe and ring-allocation functions. With NMXKPI enabled, 7d45 retains system memory, creates no stolen region, and allocates its ring internally. The unprotected/non-port path reproduces stolen ring allocation; other PCI IDs retain their previous behavior. Allocation-error cleanup is checked. Release x86_64 kernel links all 438 objects with exactly the baseline undefined-symbol set. Installer/KC rollback fixtures and request-capture bounds tests are checked separately before publication.

The saved 22-case/26,000-frame app evidence and original 1.0.8 kernel remain frozen. Those passes do not validate this changed kernel. No full hardware suite rerun is requested.

On the Dell fallback desktop, run:

    sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh

After WINDOWSERVER INSTALL exit=0 and one desktop boot armed, restart through the USB once without ResetNVRAM. If black/frozen, power off and boot USB again for fallback. Collect before reinstalling:

    sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh

Collect on the trial boot if it reaches a usable desktop. A visible desktop alone is insufficient to confirm WindowServer acceleration. The package does not reboot automatically or run the full GPU suite.
