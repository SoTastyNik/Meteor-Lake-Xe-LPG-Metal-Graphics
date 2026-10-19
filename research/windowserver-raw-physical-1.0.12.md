# NMXGPU1.0.12 + LatitudeMTLFB0.2.4: raw physical allocation correction

Status: compiled/local regressions pass; target desktop outcome unverified. The1.0.11 trial still overwrote trailing ring words with0xff000000. This candidate corrects a different demonstrated allocator assumption; no claim that all acceleration failures are fixed.

## Source finding

Apple's Sequoia source xnu-11417.140.69, IOBufferMemoryDescriptor.cpp, lines234–241 and304–312: the allocation checks for a system mapper unless kIOMemoryMapperNone is requested. kIOMemoryHostPhysicallyContiguous requests host-page contiguity. kIOMemoryPhysicallyContiguous alone only requests host contiguity when no mapper is present (or MapperNone is also set). An IOMMU-contiguous DMA address range therefore need not be one raw CPU physical run. This behavior is also present in Apple's current main branch.

The port's framebuffer allocator requested only PhysicallyContiguous, obtained getPhysicalSegment(0,nullptr,MapperNone), ignored that raw segment's length and exported it as the base of the whole surface. NMXAccel's getApertureMemoryDescriptor reconstructs an IODeviceMemory physical range from base+length. With scattered host pages that range can include memory the allocation does not own. That supplies a concrete mechanism for pixel writes into adjacent kernel allocations. The snapshot's black-pixel-looking corruption supports investigating this mechanism, but neither the snapshot nor the source proves the target had a system mapper or identifies the ring's physical page ownership. This is a fix candidate, not a proven causal diagnosis.

The same flag assumption exists in the port's kernel contiguous allocator, whose callers require raw physical runs. Its ordinary scattered-page allocation path already records each physical page separately and remains unchanged.

## Corrections

- Framebuffer reserved and dynamic surface buffers request HostPhysicallyContiguous and MapperNone, and declare KernelUserShared because applications map them.
- Before exporting a surface physical base, require a nonzero raw physical address, a segment covering the requested bytes, sufficient descriptor length, a valid CPU pointer and no address overflow. Reject fragmented/invalid spans before clearing or exposing them. Return reserved slots, descriptor references and budget on rejection. Successful logs include the verified raw span.
- The kernel contiguous allocator requests HostPhysicallyContiguous and MapperNone and validates the actual raw span, requested address ceiling and alignment. Zero-size and invalid spans fail with handle unset and descriptors cleaned up. Noncontiguous allocations are unchanged.
- Installer stages/backups/commits/rolls back the GPU kernel and framebuffer together with the AuxKC. Preflight excludes both old installed bundles and includes both candidates. The final KC is rebuilt from permanent paths, and exact UUID/version/path/executable records are checked for both extensions before arming. Plugin, accelerator, scanout geometry, scheduling, firmware, timeouts and fresh command pools remain unchanged.1.0.11 mapping pins and1.0.10 ring diagnostics remain.
- Collector includes the installed framebuffer hash/plist as current-collection-boot evidence, not proof of a failed boot's loaded identity.

## Local verification

Actual Sequoia allocation-decision code plus actual old/new framebuffer allocation functions in an ASan/UBSan fixture reproduce the old error: mapper-enabled allocation has a short raw segment, but the old function exports the full surface size. New flags force host contiguity in that decision. Deliberately fragmented results are rejected even with corrected flags.2,000balanced allocation/free cycles, reserved-slot/budget recovery, zero/oversized requests, kernel mask failures and prepare failures pass. The fixture models a mapper; it does not measure the Dell's actual memory layout.

Framebuffer0.2.4 and kernel1.0.12 compile/link. Framebuffer undefined import set equals0.2.3;438-object GPU kernel undefined import set equals1.0.8. Signatures verify. Installer tests cover success, exact previous/current diagnostic kernels, repair, both collection-record validation failures, partial arm, preflight/build/mirroring failure and rollback of kernel+framebuffer+cache+plugin. Saved application proof remains unchanged; no full hardware suite rerun. Earlier memory-lifetime and bounded ring-capture regressions pass.

Potential cost: host-contiguous allocations can be more expensive or fail under fragmentation. The corrected path fails allocation rather than exporting unowned memory. Lifetime pins can keep live mappings resident. Legacy GTT mmap remains rejected as documented for1.0.11. These changes do not establish support for all WindowServer/Metal behavior.

## Hardware action

Fallback Dell:
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh

Only after exit0, reboot USB once without ResetNVRAM. No automatic reboot or22-case rerun. If the desktop fails, poweroff/USBfallback and run collect-desktop-failure.sh before reinstalling. Inspect the new verified-span logs, first failed submission and ring data before proposing another change.

## Primary sources

- https://github.com/apple-oss-distributions/xnu/blob/xnu-11417.140.69/iokit/Kernel/IOBufferMemoryDescriptor.cpp#L304
- https://github.com/apple-oss-distributions/xnu/blob/main/iokit/Kernel/IOBufferMemoryDescriptor.cpp
- https://developer.apple.com/documentation/kernel/iobuffermemorydescriptor/1574833-initwithphysicalmask
- Local NMXVGAFB/nmxvgafb.cpp nmxVramAlloc and NVRM/accel/nvrm-accel.cpp getApertureMemoryDescriptor.
- Local xkpi/xnu/nmx_vm.cpp nmx_xnu_mem_alloc.

The web search did not establish an upstream GuC/firmware patch matching this exact capture. No credit workaround, firmware swap, broad cache flush or timeout increase was applied.
