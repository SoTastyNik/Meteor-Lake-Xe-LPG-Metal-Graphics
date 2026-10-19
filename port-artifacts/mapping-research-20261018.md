# i915 mapping investigation

Latest report: 20261018-143425. GuC initializes and the Intel MTL Vulkan physical device enumerates, but vkCreateDevice returns VK_ERROR_MEMORY_MAP_FAILED. No successful GPU workload is recorded.

Linux documentation requires the mmap-offset path for Gen12 and newer; the legacy GEM mmap ioctl is removed. Its flags distinguish WB, WC and fixed-placement caching; fixed is intended for devices with local memory. Source: https://www.kernel.org/doc/html/v6.16/gpu/driver-uapi.html (drm_i915_gem_mmap_offset).

The FreeBSD i915 source separates offset creation from the actual mmap/fault path. Offset creation may fail before any mapping is attempted. Source: https://github.com/freebsd/drm-kmod/blob/c16de0f9fa84f70b9551f69fde837a7f3a73c0e9/drivers/gpu/drm/i915/gem/i915_gem_mman.c

Local NullMoth uses fork_i915_gem_mman.py to compile override/i915/i915_gem_mman.c. Its offset request validates cache mode and object properties. nmx_linux_cdev.c then invokes the driver's mmap/fault handlers, collects physical pages and maps them through xnu. Its existing diagnostics omit early request rejection and missing mmap-operation cases. Absence of a kernel mapping error therefore does not locate the failure.

The reference Xe3/QEMU project uses Panther Lake virtual functions and the xe driver. Its desktop/Metal success is not evidence of physical Meteor Lake i915 support. Source: https://github.com/ericek111/vibe-nullmoth-xe3-qemu

Revision 1.0.4 added the existing anv_nmx_mmap bridge to i915, matching the patched Xe backend. It did not resolve the target failure. Revision 1.0.5 adds explicit error logging around both mapping stages and independent temporary GEM object CPU mapping tests for WB/WC at 4 KiB, 64 KiB and 2 MiB. CPU mapping/readback is distinct from GPU execution. No additional kernel or cache-policy changes are made before the failing stage and errno are known.

Next target evidence: i915-info.txt and vulkan.txt from 1.0.5, plus driver-after-tests.txt and dmesg-after-tests.txt. Successful offset requests followed by failed NMX maps implicate bridge/mmap/fault handling. Failed offset requests implicate i915 cache/object eligibility or offset allocation. Different WB/WC outcomes identify a cache-mode-dependent path without assuming it is safe to force another mode.
