# Driver-queried GPU identity and shared memory in System Information

## Diagnosis

The successful 1.0.15 desktop checkpoint is retained. The former Metal-only 0.3.6 correction did not publish the PCI registry properties used by System Information; that gap is addressed by this candidate.

Apple IOGraphics sets IOFBMemorySize from the actual framebuffer range length. On this panel that is the rowBytes*height scanout image, not the GPU's shared system-memory heap. It must remain physically accurate. Our old panel start also wrote an arbitrary 1GiB IOFBMemorySize property; that write is now excluded on the Latitude path. No physical aperture, timing, scanout allocation, GPU kernel, accelerator or transport logic is altered.

Inspection of both slices of this host's SPDisplaysReporter binary shows a separate PCI device property path: numeric VRAM,totalMB is read ahead of VRAM,totalsize (the latter uses a 32-bit byte value and truncates heaps above 4GiB). model supplies the GPU label. Intel vendor-id selects shared-memory presentation. These host binary findings are local evidence, not a claim to have executed Sequoia's reporter on the Dell.

## Implementation

LatitudeMTLFB 0.2.5 accepts only a narrowly scoped LatitudeGPUIdentity report through setProperties. It checks administrator privilege using the calling task, exact Intel 8086:7d45 device/claim and validated panel state, typed fields, version, bounded printable name, nonzero shared heap no larger than queried physical RAM, and safe MiB range. It then publishes the queried model as NUL-terminated Data and VRAM,totalMB as a Number on the actual PCI provider, mirroring onto our framebuffer/accelerator. Exact bytes and provenance remain in NMXSharedMemoryBytes/NMXGPUIdentity. Other setProperties requests follow the inherited implementation. It never enlarges getVRAMRange, getApertureRange or IOFBMemorySize to the shared heap size.

The new root boot helper latitude-gpu-identity waits up to 14 seconds for the matching framebuffer and nmxgpu-claimed before opening our installed ANV driver directly. It queries physical-device properties and memory properties, requires a unique integrated 8086:7d45 GPU, validates counts/indices/heap bounds and uses the largest actual DEVICE_LOCAL heap. For this integrated GPU that heap is shared system RAM. Name and capacity are queried each active desktop boot; neither a marketing name nor 1536/2048MB is hardcoded. Device-ID and ANV memory-limit overrides are cleared for this reporting query. No logical Vulkan device, queue, shader, allocation or rendering test is created.

The heap capacity is the driver's usable allocation limit, not instantaneous free RAM, a recommendation, or reserved dedicated VRAM. Mesa ANV's default integrated heap policy restricts the kernel-reported system-memory region: half up to 4GiB, three quarters above that. Thus a 16GiB region could expose a 12GiB heap; the actual query controls the label. This is not an assertion of the Dell's next returned value. The standard property uses whole MiB; exact bytes remain visible for auditing.

After publication the helper reads back the PCI model and VRAM,totalMB and reports VERIFIED only if both match. load-panel-framebuffer.sh runs it under a 20-second watchdog after successful framebuffer load; reporting failure does not change the framebuffer load result. It preserves current/previous LatitudeGPUIdentity.log. The collector copies those logs and records a bounded system_profiler SPDisplaysDataType JSON snapshot. On fallback without a panel claim, the helper does not run. The installer backs up/replaces/restores this helper together with the loader/plugin, preserves the previous 0.2.4 framebuffer, validates the new framebuffer UUID/version in the final AuxKC and retains the unchanged GPU1.0.15 kernel.

## Validation and next boot

x86_64 framebuffer and helper compile/link and signatures pass. Actual kernel reporting method and reporter code run under ASan/UBSan with mocked IOKit/driver endpoints: varying driver names and >4GiB capacities are preserved; invalid privilege/device/claim/field/name/count/index/size cases fail; failed publication/readback is rejected. Installer/KC/rollback and loader failure-isolation fixtures pass. These are local checks; target System Information output remains unverified until the next Dell trial. No 22-case GPU suite rerun.

On the Dell USB fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0, restart through this USB once without ResetNVRAM. On a usable trial desktop run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If the trial fails, power off and boot USB fallback, then collect before reinstalling. Reporting success means matched PCI property readback plus a System Information snapshot showing the queried name/shared capacity. Existing actual scanout size in IOFBMemorySize is expected and must not be mistaken for a failed shared-heap publication. No automatic reboot, target install or NVRAM changes were performed on the build host. The saved working 1.0.15 EFI/archive remains unchanged.

## Primary references

- [Apple IOGraphics framebuffer source](https://github.com/apple-oss-distributions/IOGraphics/blob/main/IOGraphicsFamily/IOFramebuffer.cpp): IOFBMemorySize follows physical mapping length.
- [Apple XNU IOKit user-client source](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/Kernel/IOUserClient.cpp): calling-task privilege validation.
- [Vulkan physical-device properties](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceProperties.html): deviceName and PCI identity fields.
- [Vulkan physical-device memory properties](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceMemoryProperties.html): heaps and device-local memory flags.
- [Mesa ANV physical-device source](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/intel/vulkan/anv_physical_device.c): integrated system heap restrictions. The local compiled-source tree was inspected read-only.

Source snapshots, exact validation hashes and host reporter disassembly are in port-artifacts/registry-report. Reporting correction does not by itself cure remaining composition timeouts or establish a performance improvement.
