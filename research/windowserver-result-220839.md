# Latest target result: 22:07 trial / 22:08:39 collection

Report: Desktop/reports/failure-detail-20261019-220839. Installer: windowserver-install-20261019-220542. Both copied locally into port-artifacts/hid-nullguard-1.0.1.

The collection's loaded modules confirm VoodooI2CHID1.0.1 UUID D7FE79DC-8031-304F-8FBC-E413C10B56F7 and NMXGPU1.0.14 UUID9B0192B5-D9CC-3FE1-9781-9276B170A4BE. USB HID binary hash matches the guarded build. No new kernel panic is retained: .contents.panic references the OLD183921 HID panic with the OLD1.0 UUID. Do not count it as a new recurrence. Absence of a panic file is not proof that no uncaptured panic occurred.

Trial boot UUID8376BFD9-8CD0-4134-9ECD-EC05F6371D30 starts22:07:07. Three new WindowServer reports capture failures at22:07:14.987,21.3596 and31.4419. All are SIGABRT/assertion failures in CoreDisplay_CreateDisplayForCGXDisplayDevice+3349, through UpdateCGXDisplayDevice/AddCGXDisplayDeviceToDeviceList/CGXDisplayDriverInitialize. This is now a captured userspace display initialization crash loop, not the earlier HID kernel panic signature.

Retained live capture shows repeated IOFBGetDisplayModeInformation failure, then failed framebuffer connection, then plugin0.3.5 load and IOKit DRM connections through NMXAccel. Vulkan enumeration returns SUCCESS with count0 (uid0/euid88), followed by Metal-device creation failure. The open connection messages prove only transport establishment, not functioning DRM ioctls or successful Vulkan physical-device initialization. Do not prematurely label the cause permissions, ring corruption or firmware submission.

Registry snapshot shows NMXIntelVGAFB and NMXAccel registered/matched/active, NMXVGAFBOpen=Yes, NMXDisplay=armed and live scanout1920x1080 pitch7680 at0x60800000. These registration/open flags do not establish successful CoreDisplay initialization. No new GPU render/readback timeout or valid completion sequence appears in this capture. Earlier ring corruption and GuC retirement candidates remain unvalidated, rather than proven resolved.

Next focus: determine why Vulkan physical-device initialization rejects the device in WindowServer, and independently inspect framebuffer mode-information/connection contract against CoreDisplay. Existing 22-case26,000-frame baseline remains unchanged; do not rerun it merely to reconfirm this crash. No binaries, EFI, OpenCore or NVRAM modified during this log review. Full physical accelerated desktop unresolved.
