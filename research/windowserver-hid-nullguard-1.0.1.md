# HID boot panic guard, 19 October 2026

Full physical WindowServer acceleration remains unresolved. This candidate addresses an independently identified boot panic; it is not evidence of successful GPU composition.

## Evidence and correction

The latest retained panic in failure-detail-20261019-183951 has CR2=0 and faults in VoodooI2CTouchscreenHIDEventDriver::forwardReport+0x4f at uptime 9.116 seconds. The original USB driver UUID 92D5DDB4-D6CC-3D21-892D-DD1BDFF81676 matches the panic. Disassembly at the fault dereferences the null result of OSNumber's dynamic cast. The corresponding source reads IOFBTransform without checking whether the property exists or is numeric. Four earlier retained panics have the same function/offset signature. NMXGPU being loaded does not establish that it caused this fault.

The source guard updates rotation only when the cast succeeds. Otherwise it preserves the previous rotation and continues delivering input. Touchscreen and trackpad personalities remain enabled. This corrects the reproduced null dereference; unrelated corruption, further input problems, and the earlier GPU submission failures are not ruled out.

## Build and validation

- VoodooI2C v2.9.1: e3ac3ed207170c39db88d6a67a76cc9fd3a1895a.
- Its pinned VoodooI2CHID: a478fd605043989269584a73e23a15cc78994f5b.
- Its pinned VoodooGPIO headers: 733dc8063f5ef07288a7bc648fff5348df6d8f65.
- All 13 HID C++ files rebuilt for x86_64 with MacKernelSDK, minimum macOS 10.12, kernel/kext flags, no RTTI/exceptions, and libkmod. Ad-hoc signed. Version 1.0.1 distinguishes this local build.
- Original forwardReport reproduced the null dereference under ASan/UBSan. Patched actual function passed 200,000 modeled cases: absent/wrong-type/zero/rotated transform, no framebuffer, and zero/single/multiple contacts. Input report delivery and valid rotations were checked.
- Final disassembly has a null branch before the virtual method call. All original public symbols are preserved. Header compatibility adds imports for IOHIDEventService::newUserClient and dispatchBiometricEvent (available since the 10.12 target); this is not a binary-identical rebuild. Loading and input behavior on Sequoia still require target validation.
- Loader and collector fixtures pass. Capture now starts before the panel query, with separate current/previous early logs flushed every two seconds while the loader runs. An extremely early panic can still predate userspace capture.

The new HID bundle is injected by the existing USB OpenCore entry. Only that USB bundle is replaced, with the original backed up and a restore script provided. OpenCore configuration and other input drivers are unchanged. The installed desktop loader must be refreshed by install-windowserver.sh. NMXGPU1.0.14, framebuffer0.2.4, Metal plugin0.3.5 and frozen 26,000-frame evidence remain unchanged. No full hardware suite rerun.

## Why the working VM does not establish a Dell fix

The linked project uses Panther Lake Xe3 8086:b080, the xe driver, an SR-IOV virtual function, and Linux-hosted virtio scanout. It reports WindowServer GPU composition. The Dell uses Meteor Lake 8086:7d45, i915 and a physical eDP panel. The VF has no display engine, aperture BAR or stolen memory. Shared mapping, power, RCU and IOKit fixes have been compared with this port, but VF-specific display/submission changes are not a complete physical-panel implementation.

Sources: [VM setup and patches](https://github.com/ericek111/vibe-nullmoth-xe3-qemu), [pinned HID source](https://github.com/VoodooI2C/VoodooI2CHID/blob/a478fd605043989269584a73e23a15cc78994f5b/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp), [VoodooI2C v2.9.1](https://github.com/VoodooI2C/VoodooI2C/tree/v2.9.1).

## Target procedure

Boot the Dell through this USB into the fallback desktop. Run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh. Only after exit=0, restart through the USB once, without resetting NVRAM. No 22-case suite is required. If it fails, power off, boot the USB fallback, and run sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh before reinstalling. The collector records early logs, crash reports and the USB HID identity. A passing installer is not proof of accelerated graphics.
