"""Build NMXGPU.kext from source for the HUAWEI MateBook 14 (8086:7D55).

The upstream link (desktop-sources/link-kernel-1.0.15.py) consumes 438 objects in five
groups. The checked-in .o files are used only as the list of object names; every object
is deleted and recompiled from its source with the group's own compiler script.

Usage (repository root, macOS x86_64 with Xcode):  python3 huawei-port/build_kernel.py <out dir>
"""
import concurrent.futures
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
X = R / 'NullMoth/gpu-port/xkpi'
OUT = Path(sys.argv[1]).resolve()
LOGS = OUT / 'logs'
GROUPS = ['obj', 'obj-i915', 'lkobj', 'srcobj', 'xnuobj']
SCRIPT = {'obj': 'cc.sh', 'obj-i915': 'cc-i915.sh', 'lkobj': 'cclk.sh', 'srcobj': 'ccsrc.sh', 'xnuobj': 'ccxx.sh'}
# Source search order per group: the port's forks (override/) win over the upstream file of the same name,
# exactly as rt.sh and all-i915.sh select them. selftests/ and build-inputs/ copies are never sources.
SEARCH = {
    'obj': [X / 'override', R / 'drm-kmod', R / 'freebsd-src'],
    'obj-i915': [X / 'override/i915', R / 'drm-kmod/drivers/gpu/drm/i915'],
    'lkobj': [X / 'override/src', R / 'freebsd-src/sys/compat/linuxkpi/common/src', R / 'freebsd-src/sys/contrib/ck/src'],
    'srcobj': [X / 'bsdcompat/src'],
    'xnuobj': [X / 'xnu'],
}
EXPECTED = 438


def repoint_scripts():
    """The compiler scripts carry the author's absolute paths; point them at this checkout."""
    for name in ['cc.sh', 'cc-i915.sh', 'cclk.sh', 'ccsrc.sh']:
        p = X / name
        s = p.read_text()
        for old in ['X=/Users/ved/igpu-build/xkpi', 'X=/Volumes/MiniData/build/gpu-src/xkpi']:
            s = s.replace(old, f'X="{X}"')
        for old in ['K=/Users/ved/igpu-build/kpi', 'K=/Volumes/MiniData/build/gpu-src/kpi']:
            s = s.replace(old, f'K="{R}"')
        assert f'X="{X}"' in s and f'K="{R}"' in s, name
        # Intel-only build: drops the fb bridge's amdgpu_sg_display reference (unresolvable without amdgpu)
        if '-DNMX_I915_ONLY=1' not in s:
            s = s.replace('-DNMXKPI=1', '-DNMXKPI=1 -DNMX_I915_ONLY=1', 1)
        assert '-DNMX_I915_ONLY=1' in s, name
        p.write_text(s)
    # fbroot/ holds symlinks into the author's FreeBSD tree
    for rel in ['compat', 'contrib/ck', 'contrib/dev']:
        link = X / 'fbroot' / rel
        if link.is_symlink() or link.exists():
            link.unlink()
        link.parent.mkdir(parents=True, exist_ok=True)
        target = R / 'freebsd-src/sys' / rel
        assert target.is_dir(), target
        link.symlink_to(target, target_is_directory=True)


def restore_kpi_snapshot():
    """The root freebsd-src/drm-kmod carry later LinuxKPI edits (linux_uuid_t rename with an inline uuid_copy that
    collides with Kernel.framework's, static lkpi_pci_drivers, ...) that the 1.0.15 overrides predate: the checked-in
    lkobj/linux_pci.o still references the global pci_drivers. build-inputs/nmxnpu-source/upstream/kpi keeps the
    matching snapshot of every file the kernel build uses; put back the files that differ."""
    snap = R / 'build-inputs/nmxnpu-source/upstream/kpi'
    restored = []
    for sub in ['freebsd-src', 'drm-kmod']:
        for src in (snap / sub).rglob('*'):
            if not src.is_file():
                continue
            dst = R / sub / src.relative_to(snap / sub)
            if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                restored.append(str(dst.relative_to(R)))
    (OUT / 'kpi-snapshot-restored.txt').write_text('\n'.join(restored) + '\n')
    print(f'restored {len(restored)} LinuxKPI/drm-kmod files from the 1.0.15 snapshot')


def source_for(group, name):
    ext = '.cpp' if group == 'xnuobj' else '.c'
    for base in SEARCH[group]:
        hits = [p for p in base.rglob(name + ext)
                if 'selftests' not in p.parts and 'build-inputs' not in p.parts and 'logs' not in p.parts]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit(f'ambiguous source for {group}/{name}: {hits}')
    raise SystemExit(f'no source for {group}/{name}')


def manifest():
    items = []
    for g in GROUPS:
        for o in sorted((X / g).glob('*.o')):
            items.append((g, o.stem, source_for(g, o.stem)))
    assert len(items) == EXPECTED, len(items)
    return items


def compile_one(item):
    group, name, src = item
    log = LOGS / f'{group}--{name}.log'
    with log.open('w') as f:
        p = subprocess.run(['bash', str(X / SCRIPT[group]), str(src)], cwd=X, stdout=f, stderr=subprocess.STDOUT)
    ok = p.returncode == 0 and (X / group / f'{name}.o').is_file()
    return item, ok


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    repoint_scripts()
    restore_kpi_snapshot()
    items = manifest()
    (OUT / 'kernel-sources.txt').write_text(''.join(f'{g}/{n}.o <- {s.relative_to(R)}\n' for g, n, s in items))
    for g, n, _ in items:
        (X / g / f'{n}.o').unlink()
    # ccxx.sh refreshes shared boundary headers on every call; do it once before the parallel run
    (X / 'bsdcompat/include/nmxxnu').mkdir(exist_ok=True)
    for h in ['nmx_port.h', 'nmx_xnu.h']:
        (X / 'bsdcompat/include/nmxxnu' / h).write_bytes((X / 'bsdcompat/include' / h).read_bytes())
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(compile_one, items))
    failed = [f'{g}/{n}' for (g, n, _), ok in results if not ok]
    if failed:
        errors = {}
        for f in failed:
            g, n = f.split('/')
            for line in (LOGS / f'{g}--{n}.log').read_text(errors='replace').splitlines():
                if ': error:' in line:
                    errors.setdefault(re.sub(r'^.*/([^/]+:\d+):\d+: error: ', r'\1 ', line), []).append(f)
        for key, files in sorted(errors.items(), key=lambda kv: -len(kv[1]))[:60]:
            print(f'{len(files):4} {key}   [{files[0]}]')
        raise SystemExit(f'{len(failed)} of {len(items)} kernel objects failed')
    print(f'compiled {len(items)} kernel objects')

    objects = [str(X / g / f'{n}.o') for g, n, _ in items]
    kext = OUT / 'NMXGPU.kext/Contents'
    (kext / 'MacOS').mkdir(parents=True, exist_ok=True)
    with (OUT / 'link.log').open('w') as log:
        subprocess.run(['xcrun', 'clang', '-arch', 'x86_64', '-mmacosx-version-min=15.0', '-fapple-kext', '-nostdlib',
                        '-Xlinker', '-kext', *objects, '-lkmodc++', '-lkmod', '-lcc_kext', '-o', str(kext / 'MacOS/NMXGPU')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    info = plistlib.loads((X / 'kext/Info.plist').read_bytes())
    match = info['IOKitPersonalities']
    assert '0x7D558086' in plistlib.dumps(match).decode(), 'NMXGPU personality is not retargeted'
    info['CFBundleVersion'] = info['CFBundleShortVersionString'] = os.environ.get('NMXGPU_VERSION', '1.0.15')
    (kext / 'Info.plist').write_bytes(plistlib.dumps(info))
    # Imports must stay within what the upstream 1.0.15 link resolved against (checked against its 1.0.8 baseline)
    undefined = subprocess.check_output(['xcrun', 'nm', '-uj', str(kext / 'MacOS/NMXGPU')], text=True).split()
    (OUT / 'NMXGPU-imports.txt').write_text('\n'.join(undefined) + '\n')
    reference = R / 'latitude-desktop/WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU'
    upstream = set(subprocess.check_output(['xcrun', 'nm', '-uj', str(reference)], text=True).split())
    # HUAWEI additions, all com.apple.kpi.iokit: the idle-sleep assertion NMXGPU holds while it drives the GPU
    upstream |= {'__ZN9IOService15getPMRootDomainEv', '__ZN14IOPMrootDomain17createPMAssertionEyjP9IOServicePKc',
                 '__ZN14IOPMrootDomain18releasePMAssertionEy'}
    extra = sorted(set(undefined) - upstream)
    assert not extra, f'imports the upstream 1.0.15 kernel does not have: {extra}'
    subprocess.run(['codesign', '--force', '--sign', '-', str(OUT / 'NMXGPU.kext')], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(OUT / 'NMXGPU.kext')], check=True)
    uuid = subprocess.check_output(['xcrun', 'dwarfdump', '--uuid', str(kext / 'MacOS/NMXGPU')], text=True).split()[1]
    (OUT / 'NMXGPU-UUID.txt').write_text(uuid + '\n')
    print('NMXGPU', uuid, len(undefined), 'imports')


if __name__ == '__main__':
    main()
