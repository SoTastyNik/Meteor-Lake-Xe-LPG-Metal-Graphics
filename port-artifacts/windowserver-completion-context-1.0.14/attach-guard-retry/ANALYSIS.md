# 18:30:02 collection: 1.0.14 loaded, attach parked by earlier panic marker

Latest target evidence: failure-detail-20261019-183002, collection on boot18:28:47. Loaded NMXGPU1.0.14 UUID9B0192B5-D9CC-3FE1-9781-9276B170A4BE and installed SHA80c3fe8bfa639a1f6cd52a29ab485695d4f18ae289f70e39bbc4b021fb0ab0f6 match candidate. Panel claim0.2.3 and framebuffer0.2.4 are loaded. Prior-boot18:27 refusal to hot-load over1.0.13 is not evidence the18:28boot ran old code.

Key failed-boot lines:
-18:28:54.573: one-shot nullmoth-gpu-once consumed.
-18:28:54.588:46SYSINITs ran.
-18:28:54.589: 'the last attach of8086:7d45 never returned ... this GPU stays with macOS'.
-18:29:40.532: NMXAccel says NMXGPU has not claimed8086:7d45.

Sample18:29:03.831: WindowServer163 main thread in CGXMappedDisplayStart -> GPUWranglerWaitForPublish -> IOConnectCallMethod. This is before a demonstrated Metal submission. No new panic report: the18:17:31mutex panic is retained historical1.0.13evidence. Absence of a new panic is not validation of1.0.14because attach was refused. No rendering/ring success can be inferred.

NMXGPU::attachNow checks persistent NVRAM 'nullmoth-gpu-attaching' before nmx_port_attach. A panic during attach leaves it present. The installer previously armed gpu/panel once but did not clear that failed-attach marker. This is the exact blocker recorded in the new log, unlike the unproven underlying ring-overlap/panic hypotheses.

Installer-only correction: after payload/KC commit and all existing checks, before one-shot arming, query and save the marker. If present, clear that exact variable for the user's explicit retry and verify absence. A deletion failure or remaining marker returns nonzero, so the existing trap rolls back and clears one-shot arms. The kernel guard stays enabled and will park again following another incomplete attach. It is not disabled or auto-cleared each boot. No kernel/plugin/framebuffer binary, EFI settings or firmware changed in this correction.

Local regression uses the actual shell helper with stateful NVRAM mocks: absent, present, deletion refused, deletion reports success but marker persists. Only absent/confirmed-cleared cases reach arming. Actual integrated installer and transactional kernel-helper fixtures pass. Source checks confirm helper is invoked after commit and before arming. No GPU suite rerun or live NVRAM edits on the build host.

## Requested repositories

WhateverXe: https://github.com/b00t0x/WhateverXe . README targets BigSur20G1443 and implemented Xe-LP backends for TigerLake9A40/9A49/9A78 and AlderLake-N46D0–46D4. The device table contains no7d45MeteorLakebackend. README lists internal panels as planned and Xe-LPG as not planned. Its OS helper recognizes newerOSfamilies, but recognizing an OS does not create a supported GPU backend. Its Apple-driver/root-patch architecture is different from this Linux i915/ANV path. Adding its boot args or spoofing a supported device does not establish MeteorLakecompatibility. No WhateverXe installation or AMFIPass replacement made.

Device selection: https://github.com/b00t0x/WhateverXe/blob/main/docs/device-selection.md
Device table: https://github.com/b00t0x/WhateverXe/blob/main/WhateverXe/kern_xelp_devices.hpp

VM reference: https://github.com/ericek111/vibe-nullmoth-xe3-qemu . It validates PantherLakeXe3SR-IOVVF with xe and virtio display, not MeteorLakei915and physicaleDP. It explicitly retains NMXGPU's attach boot guard. Relevant shared fixes already found in this tree: per-run physical kernel maps through IOMultiMemoryDescriptor; RCU unlock on original epoch record; non-WB clear/kunmap cache flush; initial power-on does not trigger resume without prior suspend; IOKit DRM user client. VF-only relay/MSI/FLR and virtio blob scanout should not be applied wholesale to this physical device. No claim of byte-for-byte equivalence of every patch or validation of all shared paths.

Next target: boot Dell USB fallback, run the updated install-windowserver.sh; after exit0 restart through USB once without ResetNVRAM. If black/panic, poweroff/USBfallback then collect-desktop-failure.sh before another install. Original1.0.8hardware evidence retained;1.0.14rendering and full desktop acceleration remain unverified.
