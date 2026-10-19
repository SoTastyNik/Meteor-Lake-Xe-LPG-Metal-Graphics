# NMXGPU1.0.11 mapping-lifetime fix candidate

## Latest evidence

Report failure-detail-20261019-171652, failed boot17:14, loaded kernel1.0.10 (also confirmed in fallback showloaded), unchanged plugin0.3.5. Same submission8/third readback timeout, followed by WindowServer crash and GPU hang.

New saved ring data distinguishes this from a purely unexplained transport stall. Before context8/request18, offsets0xc98/0xc9c/0xca0/0xca4 contain0xfedca540/0/0x02800000/0 (hold-switchout address, data and the tail workaround). Before request20, the same four offsets all contain0xff000000. Parsed GuC capture reports RING_HEAD/ACTHD0xca4 and IPEHR0xff000000. The unexpected overwrite is already present before request20 is scheduled and before its fence timeout. That value is compatible with opaque-black pixels; it does not by itself prove who wrote it. Standard i915 debug request poisoning uses0xdb/0xdf bytes and the retired payload range excludes these trailing words. CPU ring contents at the later hang are all zero, but that capture follows process teardown, so those zeros are not treated as the initiating cause.

## Verified port incompatibility and implemented correction

The port's nmx_linux_cdev.c eagerly resolves mmap pages and creates static IOKit mappings. linux_page.c lkpi_unmap_mapping_range is deliberately empty, relying on mapping-lifetime pins to prevent stale mappings when backing storage moves or is reclaimed. nmx_drm_os.c supplies that hook for TTM. The compiled i915 mmap implementation did not register such a hook for vm_ops_cpu. Its fault handler temporarily pins pages while collecting PFNs then drops that pin. The GEM reference held until vm_close retains the object, not its backing pages. __i915_gem_object_put_pages can release unpinned backing and invokes mapping revocation that this shim cannot implement. A stale user mapping can therefore refer to memory reused by another allocation.

NMXGPU1.0.11 registers nmx_i915_user_mapping_pin for the CPU/WB/WC/UC i915 mmap path. It obtains a page pin through the existing ww-aware pin_pages_unlocked routine. The port already performs a second fault population after pinning, then publishes the user mapping. Cleanup removes the IOKit mapping, drops its page pin, and only then calls vm_close. Pin and map errors use the existing cleanup path. Multiple simultaneous mappings hold independent pins. These pins last for live mappings; they are not permanent allocations. They can increase resident memory while mappings remain live, rather than allowing unsafe reclaim.

A page pin alone does not keep a GGTT aperture translation fixed. The NMXKPI path now explicitly rejects legacy GTT mmap with EOPNOTSUPP instead of permitting an unrevokeable aperture alias. This can affect legacy clients requesting GTT mappings. The target ANV system-memory path selects WC/WB, verified from local Mesa i915/anv_kmd_backend.c; its CPU mapping path is the one being fixed. Custom mmap_ops paths are not changed. This is a correction to the port, not an upstream Linux driver bug. It is consistent with the ring corruption, but the capture does not establish that reclamation caused this particular overwrite; hardware validation is still required.

## Validation

- Actual hook, i915 put_pages function and port umap_free cleanup extracted into ASan/UBSan regression: old unpinned mapping allows backing release; new pin returns EBUSY until unmap. Multiple maps, pin failure, mapping failure and20,000balanced lifetimes pass. Cleanup ordering is asserted.
- Regenerated the existing macOS fork of i915_gem_mman.c using fork_i915_gem_mman.py and compiled that generated source. Direct upstream file contains a FreeBSD legacy mmap ioctl and is not the build input; the first attempted direct build failed on those existing FreeBSD-only APIs, then the correct fork compiled successfully.
-438-object x86_64 link passes; undefined external import set equals1.0.8. Kernel UUID B972B890-9276-3E0D-B260-190037118D3E. Signed binary SHA256496e108b4d94390ac6a7030aba655ff5c0c5c61d827d7d92c65b04315b27943a.
- Installer accepts exact loaded1.0.10 predecessor and1.0.11 candidate identities; structured prelink validation, build-before-install, safe rollback and one-shot arming fixtures pass. Previous1.0.10 payload and original1.0.8 application baseline retained. Plugin, accelerator, framebuffer, firmware, fresh command pools, staging, compression policy and wait budget unchanged.1.0.10 request-ring diagnostics retained.
- No GPU hardware suite rerun. This fixes a demonstrated mapping-lifetime omission; full acceleration and target hang resolution are unverified.

## Target action

On fallback Dell: sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh

Only after exit0, reboot through USB once without ResetNVRAM. If it fails, poweroff/USBfallback then collect-desktop-failure.sh before reinstalling. No automatic reboot or full22-case suite.

## Primary sources checked

- Local compiled port: override/src/nmx_linux_cdev.c (populate/pin/map/unmap), override/src/linux_page.c (revocation shim), override/src/nmx_drm_os.c (TTM lifetime hook), generated override/i915/i915_gem_mman.c, drm-kmod gem/i915_gem_pages.c.
- https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gem/i915_gem_mman.c
- https://github.com/torvalds/linux/blob/v6.14/drivers/gpu/drm/i915/gem/i915_gem_pages.c
- https://github.com/apple-oss-distributions/xnu/blob/main/iokit/Kernel/IOMemoryDescriptor.cpp
- https://developer.apple.com/documentation/kernel/iobuffermemorydescriptor/1574833-initwithphysicalmask

Upstream search also considered GuC CTB credits, power state and workarounds. This capture does not prove a credit deadlock, and no firmware swap, broad cache flush or hardware-workaround removal was applied. Apple's physical mapping code handles multiple ranges, so the old single-descriptor user-map shape alone was not accepted as proof of the overwrite.
