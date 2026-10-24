"""Build HuaweiI2CMeteorLake.kext (VoodooI2C 2.9.1 controller personality for 8086:7E78 / 7E79).

Mirrors touchpad-sources/build.py of the Dell port: same compiler flags, VoodooI2C headers from
research/voodooi2c-core, libkmod from MacKernelSDK, LPSS timing values of the Meteor Lake controller.
Usage (repository root, macOS):  python3 huawei-port/i2c/build_i2c.py <out dir>
"""
import plistlib
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve()
NAME = 'HuaweiI2CMeteorLake'
BUNDLE = 'com.huawei-mtl.' + NAME
kext = OUT / f'{NAME}.kext'
(kext / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
flags = ['-arch', 'x86_64', '-mmacosx-version-min=10.12', '-mkernel', '-fapple-kext', '-nostdinc',
         '-I' + str(R / 'MacKernelSDK/Headers'),
         '-I' + str(R / 'research/voodooi2c-core/VoodooI2C/VoodooI2C/VoodooI2CController'),
         '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-D_FORTIFY_SOURCE=0', '-std=c++11', '-fno-rtti',
         '-fno-exceptions', '-fno-builtin', '-fno-common', '-O2', '-Wno-deprecated-declarations',
         '-Wno-inconsistent-missing-override', '-Wno-nullability-completeness']
obj = OUT / f'{NAME}.o'
subprocess.run(['xcrun', 'clang++', *flags, '-c', str(Path(__file__).parent / f'{NAME}.cpp'), '-o', str(obj)], check=True)
subprocess.run(['xcrun', 'clang++', '-arch', 'x86_64', '-mmacosx-version-min=10.12', '-fapple-kext', '-nostdlib',
                '-Xlinker', '-kext', str(obj), str(R / 'MacKernelSDK/Library/x86_64/libkmod.a'),
                '-o', str(kext / 'Contents/MacOS' / NAME)], check=True)
timing = {'I2CClkRate': 133000000, 'I2CSdaHoldTimeNs': 42, 'I2CSdaFallingTimeNs': 171, 'I2CSclFallingTimeNs': 208}
personality = lambda dev: {'CFBundleIdentifier': BUNDLE, 'IOClass': 'HuaweiI2CMeteorLakeController',
                           'IOProviderClass': 'IOPCIDevice', 'IOPCIMatch': f'0x{dev}8086',
                           'IOPCISecondaryMatch': '0x3e7119e5', 'IOProbeScore': 10001, **timing}
info = {'CFBundleIdentifier': BUNDLE, 'CFBundleName': NAME, 'CFBundleExecutable': NAME,
        'CFBundleVersion': '1.0.0', 'CFBundleShortVersionString': '1.0.0', 'CFBundlePackageType': 'KEXT',
        'CFBundleInfoDictionaryVersion': '6.0', 'OSBundleRequired': 'Root',
        'OSBundleLibraries': {'com.alexandred.VoodooI2C': '2.9.1', 'com.apple.kpi.iokit': '8.0.0',
                              'com.apple.kpi.libkern': '8.0.0', 'com.apple.kpi.mach': '8.0.0',
                              'com.apple.iokit.IOPCIFamily': '1.0.0'},
        'IOKitPersonalities': {'HuaweiMTL-I2C0-Touchpad': personality('7e78'),
                               'HuaweiMTL-I2C1-Touchscreen': personality('7e79')}}
(kext / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
subprocess.run(['codesign', '--force', '--sign', '-', str(kext)], check=True)
subprocess.run(['codesign', '--verify', '--strict', str(kext)], check=True)
print('built', kext)
