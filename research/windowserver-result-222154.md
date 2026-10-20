**Follow-up correction:** the full failed-boot log contains GuC crash/exception at22:19:41.790/.791 and non-recoverable wedged-on-init at22:19:41.795, preceding all Vulkan queries. The topology failure is downstream of an already failed GPU initialization. See windowserver-scanout-reservation-1.0.15.md.

# Target result 22:21:54: IOKit queries visible; Vulkan still rejects device

Latest report failure-detail-20261019-222154, installer221725, retained trial around22:19–22:20. Both saved locally in port-artifacts/windowserver-iokit-transport-220839.

Installed transport SHA2e0eb9f1cf0105aa22d24fc7368c78f30cda645ef9110c7dfeeed7baf3ca2c5f exactly matches candidate. Its startup messages are present in the failed WindowServer processes, establishing execution as well as installed identity. Fallback loaded modules still show NMXGPU1.0.14 and guarded HID1.0.1. No new kernel panic retained: .contents.panic references OLD183921 report.

Three new WindowServer crashes:22:19:43.2027,22:19:49.5332,22:20:01.1479. All SIGABRT via __assert_rtn in CoreDisplay_CreateDisplayForCGXDisplayDevice+3349. Vulkan again returns success with physical-device count0. No new render/readback success is demonstrated.

Each WindowServer startup now records: three GET_PCIINFO (0x40106415), two VERSION (0xc0406400), two GETPARAM (0xc0106446), three I915_QUERY (0xc0106479). All return kr0/errno0 at the outer transport/ioctl level. This verifies successful calls through the new IOKit library rather than just IOServiceOpen. It does not prove query payload validity: I915_QUERY reports per-item errors through negative query_item.length while returning ioctl success. Query item IDs/lengths were not captured by this candidate.

Source sequence in Mesa intel_device_info_i915_get_info_from_fd is timestamp GETPARAM, revision GETPARAM, query_topology. On MTL, query_topology performs length/data topology queries then geometry-subslices queries. Exactly three QUERY calls followed immediately by enumeration count0 is consistent with failure on the geometry size query (negative item.length), but not conclusive without payload results. No HWCONFIG/memory-region/aperture/context-parameter queries are seen afterward. Next useful evidence is the query ID, flags and returned item.length; successful top-level return must not be mistaken for valid device information. No GPU submission was reached in this visible initialization sequence.

Separately, CoreDisplay requests display mode0/depth0 and logs IOFBGetDisplayModeInformation failure, then failed framebuffer connection and failed Metal-device creation. The custom framebuffer currently advertises mode1. The request alone does not prove that accepting mode0 would fix the CoreDisplay crash; it may be an initialization/default-mode path. Keep this contract under investigation alongside enumeration.

No driver binaries, EFI, NVRAM or installer were changed in this log review. Prior GPU rendering baseline remains valid historical evidence; no full suite rerun. New candidate confirms more detailed transport-level evidence, not successful accelerated WindowServer composition.
