"""Assemble the HUAWEI MateBook 14 graphics package from the three CI build outputs.

Usage (repository root, macOS):
  python3 huawei-port/package.py <kernel out> <desktop out> <mesa out> <package dir>

Rebuilt here for 8086:7D55: NMXGPU, NMXAccel, LatitudeMTLFB, LatitudePanelClaim, NVMTLDriver,
libnvmtl_translate, ANV (libvulkan_intel) and libdrm, plus the boot helpers.
Hardware-independent upstream files are taken from latitude-runtime/ and verified against its
SHA256SUMS.txt: the Vulkan loader, air-opt, ICD manifest, i915 firmware, the plugin's
NVIDIA-video/SASS resources. air-runtime/libLLVM.dylib is not in git; it comes from the NullMoth
2.0.2 release the port is based on and must match the hash the runtime records.
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
KERNEL, DESKTOP, MESA, PKG = (Path(a).resolve() for a in sys.argv[1:5])
UP = R / 'latitude-runtime'
NULLMOTH = ('https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.0.2/nullmoth-nvidia-2.0.2.tar.gz')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def upstream_sums():
    sums = {}
    for line in (UP / 'SHA256SUMS.txt').read_text().splitlines():
        h, name = line.split(None, 1)
        sums[name.strip()] = h
    return sums


def copy_verified(rel, sums, dst):
    src = UP / rel
    assert sha(src) == sums[rel], f'upstream file changed: {rel}'
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        dst.symlink_to(os.readlink(src))
    else:
        shutil.copy2(src, dst)


def sign(p):
    subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(p)], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(p)], check=True)


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    lib = PKG / 'Library'
    sums = upstream_sums()

    # Kernel extensions (AuxKC) and the OpenCore-injected panel claim
    ext = lib / 'Extensions'
    ext.mkdir(parents=True)
    shutil.copytree(KERNEL / 'NMXGPU.kext', ext / 'NMXGPU.kext')
    for k in ['NMXAccel.kext', 'LatitudeMTLFB.kext']:
        shutil.copytree(DESKTOP / 'Extensions' / k, ext / k)
    for k in ['LatitudePanelClaim.kext', 'HuaweiI2CMeteorLake.kext']:
        shutil.copytree(DESKTOP / 'EFI-Kexts' / k, PKG / 'EFI-Kexts' / k)

    # Metal plugin bundle
    bundle = lib / 'GPUBundles/NVMTLDriver.bundle'
    macos = bundle / 'Contents/MacOS'
    macos.mkdir(parents=True)
    info = plistlib.loads((UP / 'Library/GPUBundles/NVMTLDriver.bundle/Contents/Info.plist').read_bytes())
    info['CFBundleVersion'] = info['CFBundleShortVersionString'] = '0.3.19'
    (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    shutil.copy2(DESKTOP / 'GPUBundles/NVMTLDriver', macos / 'NVMTLDriver')
    shutil.copy2(DESKTOP / 'GPUBundles/libnvmtl_translate.dylib', macos / 'libnvmtl_translate.dylib')
    subprocess.run(['install_name_tool', '-id', '@loader_path/libnvmtl_translate.dylib', str(macos / 'libnvmtl_translate.dylib')], check=True)
    for rel in sorted(sums):
        if rel.startswith('Library/GPUBundles/NVMTLDriver.bundle/') and not rel.endswith(
                ('/NVMTLDriver', '/libnvmtl_translate.dylib', '/Info.plist', '/air-runtime/libLLVM.dylib')):
            copy_verified(rel, sums, PKG / rel)
    llvm_rel = 'Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/air-runtime/libLLVM.dylib'
    archive = PKG.parent / 'nullmoth-nvidia-2.0.2.tar.gz'
    if not archive.exists():
        urllib.request.urlretrieve(NULLMOTH, archive)
    with tarfile.open(archive) as t:
        member = next(m for m in t.getmembers() if m.name.endswith('/' + llvm_rel) or m.name == llvm_rel)
        data = t.extractfile(member).read()
    assert hashlib.sha256(data).hexdigest() == sums[llvm_rel], 'libLLVM.dylib does not match the runtime hash'
    (PKG / llvm_rel).write_bytes(data)

    # Vulkan backend: rebuilt ANV + libdrm, upstream loader/air-opt/ICD
    nvmtl = lib / 'GPUBundles/nvmtl'
    for rel in sorted(sums):
        if rel.startswith('Library/GPUBundles/nvmtl/') and not rel.endswith(('/libvulkan_intel.dylib', '/libdrm.2.dylib')):
            copy_verified(rel, sums, PKG / rel)
    for name in ['libvulkan_intel.dylib', 'libdrm.2.dylib']:
        shutil.copy2(MESA / 'nvmtl' / name, nvmtl / name)
    copy_verified('Library/GPUBundles/nvmtl-allow.txt', sums, lib / 'GPUBundles/nvmtl-allow.txt')

    # Firmware (GuC 70.53.0 / HuC 8.5.4 / DMC 2.23 / GSC 102.1.15.1926: same Meteor Lake firmware Linux loads on this laptop)
    for rel in sorted(sums):
        if rel.startswith('Library/NullMoth/firmware/'):
            copy_verified(rel, sums, PKG / rel)

    # Boot helpers and the panel loader daemon
    nm = lib / 'NullMoth'
    for name in ['latitude-desktop-journal', 'latitude-gpu-identity']:
        shutil.copy2(DESKTOP / 'NullMoth' / name, nm / name)
    shutil.copy2(R / 'port-artifacts/desktop-0.3.5/load-panel-framebuffer.sh', nm / 'load-panel-framebuffer.sh')
    (lib / 'LaunchDaemons').mkdir()
    shutil.copy2(HERE / 'com.huawei-mtl.panel-load.plist', lib / 'LaunchDaemons/com.huawei-mtl.panel-load.plist')

    # Tools, installer, licences
    tools = PKG / 'tools'
    shutil.copytree(DESKTOP / 'tools', tools)
    for name in ['install.sh', 'uninstall.sh', 'collect.sh', 'README-RU.txt']:
        shutil.copy2(HERE / name, PKG / name)
    shutil.copytree(UP / 'licenses', PKG / 'licenses')
    for name in ['NMXGPU-UUID.txt']:
        shutil.copy2(KERNEL / name, PKG / name)
    for name in ['NMXAccel', 'LatitudeMTLFB', 'LatitudePanelClaim']:
        for suffix in ['UUID', 'VERSION']:
            shutil.copy2(DESKTOP / f'{name}-{suffix}.txt', PKG / f'{name}-{suffix}.txt')
    (PKG / 'NMXGPU-VERSION.txt').write_text(plistlib.loads((ext / 'NMXGPU.kext/Contents/Info.plist').read_bytes())['CFBundleVersion'] + '\n')

    # Every Mach-O is x86_64 and freshly ad-hoc signed; bundles are sealed last
    for p in sorted(PKG.rglob('*')):
        if p.is_file() and not p.is_symlink() and p.read_bytes()[:4] == bytes.fromhex('cffaedfe'):
            assert subprocess.check_output(['lipo', '-archs', str(p)], text=True).strip() == 'x86_64', p
            p.chmod(0o755)
            main_exe = (p.parent.name == 'MacOS' and p.parent.parent.parent.suffix == '.bundle'
                        and p.name == p.parent.parent.parent.stem)
            if '.kext/' not in str(p) and not main_exe:  # nested code first; the bundle seal covers its executable
                sign(p)
    for p in [bundle, *ext.iterdir(), *(PKG / 'EFI-Kexts').iterdir()]:
        sign(p)
    for p in [PKG / 'install.sh', PKG / 'uninstall.sh', PKG / 'collect.sh', nm / 'load-panel-framebuffer.sh']:
        p.chmod(0o755)
        subprocess.run(['/bin/bash', '-n', str(p)], check=True)
    subprocess.run(['plutil', '-lint', str(lib / 'LaunchDaemons/com.huawei-mtl.panel-load.plist')], check=True)

    manifest = {
        'target': {'model': 'HUAWEI FLMH-XX (MateBook 14, 2024)', 'cpu': 'Intel Core Ultra 5 125H',
                   'gpu': '8086:7D55 rev 08', 'subsystem': '19E5:3E71', 'panel': 'EDO142 2880x1920 OLED'},
        'base': 'VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics (Dell Latitude 5350, 8086:7D45)',
        'macos': 'Sequoia 15 (upstream evidence: 15.8.1 24H32)',
        'hardware_tested': False,
    }
    (PKG / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    (PKG / 'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(PKG).as_posix()}\n'
                                                for p in sorted(PKG.rglob('*'))
                                                if p.is_file() and p.name != 'SHA256SUMS.txt'))
    with tarfile.open(PKG.parent / f'{PKG.name}.tar.gz', 'w:gz') as t:
        t.add(PKG, arcname=PKG.name)
    print('package ready:', PKG)


if __name__ == '__main__':
    main()
