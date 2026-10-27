"""Build the user-space and auxiliary kext components for the HUAWEI MateBook 14 (8086:7D55).

Upstream build scripts are run unchanged where they exist (desktop-sources/build.py,
build-framebuffer-0.2.12.py, build-windowserver-0.3.19.py, NullMoth/build/nmxaccel_build.sh);
only the helpers that were built ad hoc on the original machine get explicit commands here.

Usage (repository root, macOS x86_64):  python3 huawei-port/build_desktop.py <out dir>
"""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve()
LOGS = OUT / 'logs'
VERSIONS = {'LatitudeMTLFB': '0.2.12', 'LatitudePanelClaim': '0.2.3', 'NMXAccel': '0.2.9', 'NVMTLDriver': '0.3.19'}
X86 = ['-arch', 'x86_64', '-mmacosx-version-min=15.0']


def run(name, cmd, cwd=R, env=None):
    log = LOGS / f'{name}.log'
    with log.open('w') as f:
        p = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    if p.returncode:
        print(log.read_text()[-8000:])
        raise SystemExit(f'{name} failed ({p.returncode})')


def sign(path):
    subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(path)], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(path)], check=True)


def uuid_of(binary):
    return subprocess.check_output(['xcrun', 'dwarfdump', '--uuid', str(binary)], text=True).split()[1]


def set_version(kext, version):
    p = kext / 'Contents/Info.plist'
    info = plistlib.loads(p.read_bytes())
    info['CFBundleVersion'] = info['CFBundleShortVersionString'] = version
    p.write_bytes(plistlib.dumps(info))


def main():
    for d in ['Extensions', 'EFI-Kexts', 'GPUBundles', 'NullMoth', 'tools']:
        (OUT / d).mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    (R / 'desktop-build').mkdir(exist_ok=True)

    # Framebuffer + early panel claim: build.py links both, 0.2.12 relinks the framebuffer from current nmxvgafb.cpp
    run('kexts-0.2.3', [sys.executable, 'desktop-sources/build.py'])
    run('framebuffer-0.2.12', [sys.executable, 'desktop-sources/build-framebuffer-0.2.12.py'])
    fb = R / 'latitude-desktop/WindowServerFramebuffer/LatitudeMTLFB.kext'
    claim = R / 'latitude-desktop/EFI-Kexts/LatitudePanelClaim.kext'
    assert b'0x7d558086' in (claim / 'Contents/Info.plist').read_bytes(), 'LatitudePanelClaim is not retargeted'
    for kext, dest in [(fb, OUT / 'Extensions'), (claim, OUT / 'EFI-Kexts')]:
        shutil.copytree(kext, dest / kext.name, dirs_exist_ok=True)
    set_version(OUT / 'EFI-Kexts/LatitudePanelClaim.kext', VERSIONS['LatitudePanelClaim'])
    sign(OUT / 'EFI-Kexts/LatitudePanelClaim.kext')
    sign(OUT / 'Extensions/LatitudeMTLFB.kext')

    # Metal accelerator (generic Intel personality; the panel/front-copy paths gate on LatitudePanelValidated)
    env = dict(os.environ, OGKM=str(R / 'ogkm610'))
    run('nmxaccel', ['bash', 'NullMoth/build/nmxaccel_build.sh', str(R / 'NullMoth/kexts/NVRM'), str(OUT / 'accel-build')], env=env)
    shutil.copytree(OUT / 'accel-build/NMXAccel.kext', OUT / 'Extensions/NMXAccel.kext', dirs_exist_ok=True)
    set_version(OUT / 'Extensions/NMXAccel.kext', VERSIONS['NMXAccel'])
    sign(OUT / 'Extensions/NMXAccel.kext')

    # Metal plugin (only the shipping x86_64 variant is packaged)
    run('plugin-0.3.19', [sys.executable, 'desktop-sources/build-windowserver-0.3.19.py'])
    shutil.copy2(R / 'desktop-build/NVMTLDriver-0.3.19', OUT / 'GPUBundles/NVMTLDriver')

    # AIR -> SPIR-V translator
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET='15.0', CARGO_TARGET_DIR=str(OUT / 'cargo'))
    run('translator', ['cargo', 'build', '--release', '--locked', '--target', 'x86_64-apple-darwin',
                       '--manifest-path', 'NullMoth/translator/wrapper/Cargo.toml'], env=env)
    shutil.copy2(OUT / 'cargo/x86_64-apple-darwin/release/libnvmtl_translate.dylib', OUT / 'GPUBundles/libnvmtl_translate.dylib')

    # Boot-time helpers that only existed as binaries on the Dell's USB
    run('journal', ['xcrun', 'clang', *X86, '-O2', '-I', 'NullMoth/plugin', 'desktop-sources/latitude-desktop-journal.c',
                    '-o', str(OUT / 'NullMoth/latitude-desktop-journal')])
    run('gpu-identity', ['xcrun', 'clang', *X86, '-fobjc-arc', '-O2', '-I', 'Vulkan-Headers/include', '-I', 'desktop-sources',
                         'desktop-sources/latitude-gpu-identity.m', '-framework', 'Foundation', '-framework', 'IOKit',
                         '-o', str(OUT / 'NullMoth/latitude-gpu-identity')])
    run('validate-kernel-prelink', ['xcrun', 'clang', *X86, '-fobjc-arc', '-O2', 'desktop-sources/validate-kernel-prelink.m',
                                    '-framework', 'Foundation', '-o', str(OUT / 'tools/validate-kernel-prelink')])
    for f in ['NullMoth/latitude-desktop-journal', 'NullMoth/latitude-gpu-identity', 'tools/validate-kernel-prelink']:
        sign(OUT / f)

    # Small hardware tests from the upstream runtime, rebuilt for this machine's identity, plus the bare i915 probe
    libdrm = ['-I', 'build-tree/sysroot/include', '-I', 'build-tree/sysroot/include/libdrm', 'build-tree/sysroot/lib/libdrm.2.dylib']
    drm_tools = ['latitude-i915-info', 'latitude-gpu-probe']
    for name, src, extra in [('latitude-vulkan-test', 'latitude-runtime/tools/latitude-vulkan-test.c', ['-I', 'Vulkan-Headers/include']),
                             ('latitude-metal-test', 'latitude-runtime/tools/latitude-metal-test.m', ['-fobjc-arc', '-framework', 'Foundation', '-framework', 'Metal', '-framework', 'IOKit']),
                             ('latitude-i915-info', 'latitude-runtime/tools/latitude-i915-info.c', libdrm),
                             ('latitude-gpu-probe', 'huawei-port/tools/latitude-gpu-probe.c', libdrm)]:
        run(name, ['xcrun', 'clang', *X86, '-O2', *extra, src, '-o', str(OUT / 'tools' / name)])
        if name in drm_tools:
            # the sysroot's libdrm carries the build machine's install name; the package installs it to GPUBundles/nvmtl
            old = subprocess.check_output(['otool', '-D', str(R / 'build-tree/sysroot/lib/libdrm.2.dylib')], text=True).split('\n')[1].strip()
            subprocess.run(['install_name_tool', '-change', old, '/Library/GPUBundles/nvmtl/libdrm.2.dylib',
                            str(OUT / 'tools' / name)], check=True)
        sign(OUT / 'tools' / name)
    shutil.copy2(R / 'latitude-runtime/tools/check.spv', OUT / 'tools/check.spv')

    # VoodooI2C controller personality for the touchpad/touchscreen controllers (OpenCore-injected)
    run('i2c', [sys.executable, 'huawei-port/i2c/build_i2c.py', str(OUT / 'EFI-Kexts')])

    for kext in ['Extensions/LatitudeMTLFB.kext', 'Extensions/NMXAccel.kext', 'EFI-Kexts/LatitudePanelClaim.kext']:
        name = Path(kext).stem
        (OUT / f'{name}-UUID.txt').write_text(uuid_of(OUT / kext / 'Contents/MacOS' / name) + '\n')
        (OUT / f'{name}-VERSION.txt').write_text(VERSIONS[name] + '\n')
    print('desktop components built')


if __name__ == '__main__':
    main()
