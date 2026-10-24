"""Retarget the Dell Latitude 5350 identity guards to the HUAWEI MateBook 14 (FLMH-XX).

Dell:   GPU 8086:7D45 (MTL-U, "Intel Graphics"),     subsystem 1028:0CB6
Huawei: GPU 8086:7D55 (MTL-H, "Intel Arc Graphics"), subsystem 19E5:3E71, revision 08

Every replacement is listed with the exact number of occurrences expected in the
upstream file, so a changed upstream fails loudly instead of being half-patched.
Run from the repository root:  python3 huawei-port/apply_identity.py [--check]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (file, old, new, expected count)
EDITS = [
    # NMXGPU kext personality and its start-time PCI guard
    ('NullMoth/gpu-port/xkpi/kext/Info.plist', '0x7D458086', '0x7D558086', 1),
    ('NullMoth/gpu-port/xkpi/xnu/nmx_kext.cpp',
     'pci->configRead16(kIOPCIConfigDeviceID) == 0x7D45;', 'pci->configRead16(kIOPCIConfigDeviceID) == 0x7D55;', 1),
    ('NullMoth/gpu-port/xkpi/xnu/nmx_kext.cpp',
     '// This local laptop build is restricted to the real Meteor Lake-U PCI ID.',
     '// This local laptop build is restricted to the HUAWEI MateBook 14 Meteor Lake-H PCI ID.', 1),

    # i915 (drm-kmod) bring-up gates added by the port
    ('drm-kmod/drivers/gpu/drm/i915/display/intel_display_device.c',
     'pdev->vendor == 0x8086 && pdev->device == 0x7d45', 'pdev->vendor == 0x8086 && pdev->device == 0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/i915_driver.c',
     'pdev->vendor == 0x8086 && pdev->device == 0x7d45', 'pdev->vendor == 0x8086 && pdev->device == 0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/gem/i915_gem_stolen.c',
     'INTEL_DEVID(i915) == 0x7d45', 'INTEL_DEVID(i915) == 0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/gt/intel_ring.c',
     'INTEL_DEVID(vma->vm->i915) == 0x7d45', 'INTEL_DEVID(vma->vm->i915) == 0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/gt/nmx_request_capture.h',
     'INTEL_DEVID(rq->i915) != 0x7d45', 'INTEL_DEVID(rq->i915) != 0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/i915_gpu_error.c',
     'INTEL_DEVID(engine->i915)==0x7d45', 'INTEL_DEVID(engine->i915)==0x7d55', 1),
    ('drm-kmod/drivers/gpu/drm/i915/i915_gpu_error.c',
     'INTEL_DEVID(error->i915) != 0x7d45', 'INTEL_DEVID(error->i915) != 0x7d55', 1),

    # Mesa ANV: 4 GiB shared heap cap on Darwin
    ('mesa/src/intel/vulkan/anv_latitude_heap.h', 'pci_id == 0x7d45', 'pci_id == 0x7d55', 1),

    # Metal plugin policies
    ('NullMoth/plugin/nvmtl_desktop_policy.h', 'device == 0x7d45', 'device == 0x7d55', 2),
    ('NullMoth/plugin/nvmtl_memory_identity.h', 'device == 0x7d45', 'device == 0x7d55', 2),
    ('NullMoth/plugin/nvmtl_vk.c', 'first-submit: 8086:7d45', 'first-submit: 8086:7d55', 1),

    # Framebuffer (LatitudeMTLFB) and the EFI panel claim: device + subsystem
    ('NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',
     'matchedPCI->configRead16(kIOPCIConfigDeviceID) != 0x7d45 ||', 'matchedPCI->configRead16(kIOPCIConfigDeviceID) != 0x7d55 ||', 1),
    ('NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',
     'matchedPCI->configRead16(kIOPCIConfigSubSystemVendorID) != 0x1028 ||',
     'matchedPCI->configRead16(kIOPCIConfigSubSystemVendorID) != 0x19e5 ||', 1),
    ('NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',
     'matchedPCI->configRead16(kIOPCIConfigSubSystemID) != 0x0cb6) return nullptr;',
     'matchedPCI->configRead16(kIOPCIConfigSubSystemID) != 0x3e71) return nullptr;', 1),
    ('desktop-sources/LatitudePanelClaim.cpp',
     'if(vendor!=0x8086||device!=0x7d45||sv!=0x1028||sd!=0x0cb6)',
     'if(vendor!=0x8086||device!=0x7d55||sv!=0x19e5||sd!=0x3e71)', 1),
    ('desktop-sources/build.py', "IOPCIMatch='0x7d458086'", "IOPCIMatch='0x7d558086'", 1),

    # GPU identity reporter (About This Mac / System Information)
    ('desktop-sources/latitude_gpu_identity.h', 'device != 0x7d45', 'device != 0x7d55', 1),
    ('desktop-sources/latitude_gpu_identity_kernel.inc',
     'device->unsigned64BitValue()!=0x7d45', 'device->unsigned64BitValue()!=0x7d55', 1),
    ('desktop-sources/latitude_gpu_identity_kernel.inc',
     'latitudeGPUIdentityValid(1,0x8086,0x7d45,', 'latitudeGPUIdentityValid(1,0x8086,0x7d55,', 1),
    ('desktop-sources/latitude_gpu_identity_kernel.inc',
     'pci->configRead16(2)!=0x7d45', 'pci->configRead16(2)!=0x7d55', 1),
    ('desktop-sources/latitude-gpu-identity.m',
     'sameID(pci,CFSTR("device-id"),0x7d45)', 'sameID(pci,CFSTR("device-id"),0x7d55)', 1),
    ('desktop-sources/latitude-gpu-identity.m',
     'sameID(parent,CFSTR("device-id"),0x7d45)', 'sameID(parent,CFSTR("device-id"),0x7d55)', 1),
    ('desktop-sources/latitude-gpu-identity.m',
     'candidate.deviceID==0x7d45', 'candidate.deviceID==0x7d55', 1),

    # Hardware Vulkan smoke test shipped with the runtime
    ('latitude-runtime/tools/latitude-vulkan-test.c', 'p.deviceID==0x7d45', 'p.deviceID==0x7d55', 1),
    ('latitude-runtime/tools/latitude-vulkan-test.c', 'Meteor Lake 8086:7d45 GPU', 'Meteor Lake 8086:7d55 GPU', 1),
    ('latitude-runtime/tools/latitude-vulkan-test.c', 'real 8086:7d45,', 'real 8086:7d55,', 1),
]


def main(check_only):
    bad = []
    for rel, old, new, count in EDITS:
        p = ROOT / rel
        text = p.read_text(encoding='utf-8')
        n_old, n_new = text.count(old), text.count(new)
        if n_old == 0 and n_new >= count:
            continue  # already applied
        if n_old != count:
            bad.append(f'{rel}: expected {count} x {old!r}, found {n_old}')
            continue
        if not check_only:
            p.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    if bad:
        sys.exit('identity patch mismatch:\n  ' + '\n  '.join(bad))
    print('identity:', 'checked' if check_only else 'applied', len(EDITS), 'edits')


if __name__ == '__main__':
    main('--check' in sys.argv[1:])
