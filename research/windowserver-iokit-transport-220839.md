# WindowServer IOKit transport candidate, 19 October 2026

The 22:07 trial has three CoreDisplay assertion crashes. This is a failed desktop, with no successful GPU composition. Early capture shows explicit WindowServer sandbox denials for writable opens and ioctls on /dev/dri/renderD128. The Metal plugin loads but Vulkan enumeration returns success with zero devices. The earlier HID panic is not newly recorded; the collector loaded the guarded HID1.0.1.

## Source finding

The existing automatic fallback connects through IOKit during discovery. However, drmNmxOpen first retries a denied writable render-node open as read-only. That descriptor can then enter drmGetDevice2's devfs rediscovery path: its helper recognizes only synthetic tokens, even if this real descriptor already has an IOKit DRM file after an ioctl denial. Thus successful discovery/connection does not guarantee that subsequent identity/version queries use the same available transport.

The corrected library sends a denied writable open of the known renderD128 node directly to an IOKit token. It also obtains PCI identity from an already established IOKit connection for real descriptors that have switched transport. Unknown descriptors retain ordinary discovery; no new client is created by the identity helper. EPERM and EACCES are handled. Forced direct/IOKit tests retain their route isolation. No sandbox policy is weakened.

This is a reproduced transport gap consistent with the target access pattern. The retained logs do not expose ANV's exact rejection branch, so it is not yet proven to be the only cause of zero devices. Bounded startup diagnostics now record the first64 IOKit ioctl results and first64 kernel errno results per process, making the next rejection visible without relying on WindowServer stderr. Returned data and errno behavior are preserved.

## Validation

- Negative control using the actual old functions reproduces read-only fallback and refusal to use an existing real-fd IOKit connection for identity.
- Corrected actual functions pass ASan/UBSan fixtures for both permission errno values, tracked real fd and token identity, invalid flags/null output, untracked fd, forced direct/IOKit routes, unrelated nodes and non-permission open failure.
- Existing actual transport/enumeration regression fixtures pass.
- x86_64 libdrm compiles and links; all public exports and undefined imports match the frozen baseline. Ad-hoc signed with the existing installed library ID. The baseline library is preserved separately.
- Integrated installer tests verify baseline and already-updated transports, replacement, signature failure rollback, and rollback after plugin/journal/kernel/arming failures. Both opt-ins are cleared on failed preparation. No target reboot or hardware suite is run here.

The desktop installer stages WindowServerTransport/libdrm.2.dylib, accepts only the exact saved baseline or exact candidate as installed input, backs it up, installs it atomically, verifies bytes/signature, and restores it on later failure. Collector includes the installed transport hash. NMXGPU1.0.14, Metal plugin0.3.5, framebuffer0.2.4, USB HID1.0.1 and saved26,000-frame evidence are unchanged. The baseline test gate is historical evidence for the old library, not certification of this new candidate. No22-case rerun is requested.

## Framebuffer findings

CoreDisplay also reports get-mode-information and framebuffer-connection failures. The registry nevertheless shows an active/open NMXIntelVGAFB and armed NMXAccel. These are insufficient to establish that all CoreDisplay contracts succeed. The source advertises a single fixed physical-panel mode; blindly accepting arbitrary unknown mode IDs would hide errors rather than establish correct output. No speculative mode-ID patch is included. If GPU enumeration recovers but CoreDisplay still fails, the next evidence must identify the requested mode and exact failing framebuffer operation.

## Sources and target procedure

Compared the [VM project's libdrm patches](https://github.com/ericek111/vibe-nullmoth-xe3-qemu/tree/master/patches/libdrm) and local libdrm xf86drm.c against Mesa's anv_physical_device_try_create, intel_get_device_info_from_fd and intel_get_kmd_type. The VM's token fallback provides the basis; this corrects the remaining mixed real-fd path used on this target. Mesa was read, not modified. No upstream contributions or messages were made.

On the Dell fallback desktop run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh. After exit0 restart through USB once without ResetNVRAM. A system-extension update prompt is not required for this userspace library change. If it fails, power off, boot USB fallback and collect-desktop-failure.sh before reinstalling. Full physical WindowServer acceleration remains unresolved until the target demonstrates stable composition.
