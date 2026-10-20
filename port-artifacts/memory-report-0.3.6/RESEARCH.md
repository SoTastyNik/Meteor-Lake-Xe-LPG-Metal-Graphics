# Query-based Metal memory reporting 0.3.6

The working 1.0.15 desktop checkpoint remains saved in checkpoints/usable-desktop-1.0.15-20261019-224818 and its dated USB archive. This candidate changes the Metal plugin and collector, preserving kernel, framebuffer, accelerator, transport and EFI configuration.

Per the user's correction, no fixed GPU model or 1536/2048MB property is injected. The unpublished config-2048MB.plist was removed. On the scoped integrated Intel GPU the Metal name comes directly from VkPhysicalDeviceProperties.deviceName (the existing backend previously reported Intel(R) Graphics (MTL)). Heap sizes come from VkPhysicalDeviceMemoryProperties. Unified-memory identity requires the actual integrated device type and matching PCI identity; dedicatedMemorySize is zero for that UMA device. This is shared system RAM, not dedicated VRAM.

The recommended working set uses the queried memory budget when available and never exceeds the queried device-local heap. If the backend lacks a usable budget extension, the existing conservative 70-percent heap estimate is explicitly identified as an estimate. A recommendation is not instantaneous free RAM or a physical reservation. The former fixed 1GiB floor and sparse full-heap shortcut are bypassed for this integrated device. Failed initialization reports unknown/zero, not invented 2GiB.

The existing plugin attempted host-pointer imports that the current compiled i915 userptr implementation cannot provide (compiled stub returns ENODEV). This candidate bypasses those failed attempts for 8086:7d45, using the already working private-image/copy fallback. It does not implement zero-copy or establish that CoreAnimation timeout/CPU issues are cured.

## The separate Display 7MB entry

Apple IOGraphics derives IOFBMemorySize from getVRAMRange length. This framebuffer intentionally exposes its actual rowBytes*height physical scanout range, approximately 7.9MiB. Enlarging that mapping to a pretend 2GiB would misrepresent the physical mapping. System Information also reads registry identity/memory properties separately from Metal. Therefore this plugin correction does not yet implement automatic registry publication for that display entry and cannot promise that label will change on the next boot. No cosmetic property injection substitutes for that remaining integration.

The collector now records a bounded SPDisplaysDataType JSON snapshot (20-second watchdog) to compare actual macOS labels and Metal support after the next boot. No 22-case suite rerun. Use install-windowserver.sh on the Dell fallback, wait for exit=0, then restart via USB once without resetting NVRAM. Collect on the usable trial boot, or on fallback after a failed trial, before reinstalling.

## Primary sources

- [Apple unified-memory API](https://developer.apple.com/documentation/metal/mtldevice/hasunifiedmemory)
- [Apple recommended working set](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize)
- [Vulkan memory heaps and budgets](https://docs.vulkan.org/spec/latest/chapters/memory.html)
- [Apple IOGraphics framebuffer source](https://github.com/apple-oss-distributions/IOGraphics/blob/main/IOGraphicsFamily/IOFramebuffer.cpp)

Local checks and exact payload hashes are in the adjacent validation JSON. Hardware behavior of 0.3.6 remains unverified. Successful WindowServer GPU work from the earlier 1.0.15 report remains established.
