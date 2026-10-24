"""Cross-build libdrm and Mesa's Intel Vulkan driver (ANV) for x86_64 macOS on an arm64 macOS host.

The project's CLC tools in build-tree/tools (mesa_clc, vtn_bindgen2, llvm-spirv) are arm64
binaries, so this runs on Apple Silicon, as the original build did (build-tree/x86_64-macos.ini).
The only Huawei change inside Mesa is anv_latitude_heap.h (pci_id 0x7d55), applied beforehand
by huawei-port/apply_identity.py.

Usage (repository root):  python3 huawei-port/build_mesa.py <out dir>
"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve()
WORK = OUT / 'work'
PREFIX = WORK / 'sysroot'
TOOLS = R / 'build-tree/tools'
LOGS = OUT / 'logs'


def run(name, cmd, env):
    log = LOGS / f'{name}.log'
    with log.open('w') as f:
        p = subprocess.run(cmd, cwd=R, env=env, stdout=f, stderr=subprocess.STDOUT)
    if p.returncode:
        print(log.read_text()[-12000:])
        raise SystemExit(f'{name} failed ({p.returncode})')


def main():
    assert subprocess.check_output(['uname', '-m'], text=True).strip() == 'arm64', 'run on an arm64 host'
    for d in (WORK, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    assert b'pci_id == 0x7d55' in (R / 'mesa/src/intel/vulkan/anv_latitude_heap.h').read_bytes(), 'identity patch missing'
    for p in (TOOLS / 'bin').iterdir():
        p.chmod(0o755)
    brew = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip())
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([str(Path(sys.executable).parent), str(TOOLS / 'bin'), str(brew / 'opt/bison/bin'),
                                   str(brew / 'opt/flex/bin'), env['PATH']])
    env['DYLD_FALLBACK_LIBRARY_PATH'] = str(TOOLS / 'lib')
    env['MACOSX_DEPLOYMENT_TARGET'] = '15.0'
    # record what the host tools need, for diagnosing a missing LLVM/clang runtime
    (LOGS / 'tool-deps.txt').write_text(subprocess.run(['otool', '-L', str(TOOLS / 'bin/mesa_clc'), str(TOOLS / 'bin/vtn_bindgen2')],
                                                       capture_output=True, text=True).stdout)

    # Apple ar cannot write the empty archives Mesa declares (libintel_decoder_gen.a); llvm-ar can
    assert (brew / 'opt/llvm@20/bin/llvm-ar').is_file()
    cross = WORK / 'x86_64-macos.ini'
    cross.write_text(f"""[binaries]
c = ['clang', '-arch', 'x86_64', '-mmacosx-version-min=15.0']
cpp = ['clang++', '-arch', 'x86_64', '-mmacosx-version-min=15.0']
objc = ['clang', '-arch', 'x86_64', '-mmacosx-version-min=15.0']
ar = '{brew / 'opt/llvm@20/bin/llvm-ar'}'
strip = 'strip'
pkg-config = '{shutil.which('pkg-config', path=env['PATH'])}'
[host_machine]
system = 'darwin'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
[properties]
pkg_config_libdir = '{PREFIX / 'lib/pkgconfig'}'
needs_exe_wrapper = true
""")

    run('libdrm-setup', ['meson', 'setup', str(WORK / 'libdrm'), 'libdrm', '--cross-file', str(cross), '--prefix', str(PREFIX),
                         '--buildtype=release', '-Dintel=disabled', '-Dradeon=disabled', '-Damdgpu=disabled',
                         '-Dnouveau=disabled', '-Dvmwgfx=disabled', '-Dtests=false', '-Dinstall-test-programs=false'], env)
    run('libdrm-build', ['ninja', '-C', str(WORK / 'libdrm'), 'install'], env)

    run('mesa-setup', ['meson', 'setup', str(WORK / 'mesa'), 'mesa', '--cross-file', str(cross), '--prefix', str(PREFIX),
                       '--buildtype=release', '-Dvulkan-drivers=intel', '-Dgallium-drivers=', '-Dplatforms=',
                       '-Dopengl=false', '-Dgles1=disabled', '-Dgles2=disabled', '-Degl=disabled', '-Dglx=disabled',
                       '-Dgbm=disabled', '-Dglvnd=disabled', '-Dllvm=disabled', '-Dmesa-clc=system',
                       '-Dmicrosoft-clc=disabled', '-Dintel-rt=disabled', '-Dvideo-codecs=', '-Dvulkan-layers=',
                       '-Dtools=', '-Dbuild-tests=false', '-Dxmlconfig=disabled', '-Dexpat=disabled', '-Dzstd=disabled',
                       '-Dvalgrind=disabled', '-Dlibunwind=disabled', '-Dlmsensors=disabled', '-Dspirv-tools=disabled'], env)
    run('mesa-build', ['ninja', '-C', str(WORK / 'mesa'), 'src/intel/vulkan/libvulkan_intel.dylib'], env)

    out = OUT / 'nvmtl'
    out.mkdir(exist_ok=True)
    for src in [WORK / 'mesa/src/intel/vulkan/libvulkan_intel.dylib', PREFIX / 'lib/libdrm.2.dylib']:
        dst = out / src.name
        shutil.copy2(src.resolve(), dst)
        assert subprocess.check_output(['lipo', '-archs', str(dst)], text=True).strip() == 'x86_64', dst
        # same install names as the upstream runtime: both live in /Library/GPUBundles/nvmtl
        subprocess.run(['install_name_tool', '-id', f'/Library/GPUBundles/nvmtl/{src.name}', str(dst)], check=True)
    deps = subprocess.check_output(['otool', '-L', str(out / 'libvulkan_intel.dylib')], text=True)
    for line in deps.splitlines()[1:]:
        dep = line.strip().split(' (')[0]
        if dep.endswith('libdrm.2.dylib') and dep != '/Library/GPUBundles/nvmtl/libdrm.2.dylib':
            subprocess.run(['install_name_tool', '-change', dep, '/Library/GPUBundles/nvmtl/libdrm.2.dylib',
                            str(out / 'libvulkan_intel.dylib')], check=True)
    (LOGS / 'anv-deps.txt').write_text(subprocess.check_output(['otool', '-L', str(out / 'libvulkan_intel.dylib')], text=True))
    for p in out.iterdir():
        subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(p)], check=True)
    (OUT / 'SHA256SUMS.txt').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  nvmtl/{p.name}\n'
                                                for p in sorted(out.iterdir())))
    print('ANV + libdrm built for x86_64')


if __name__ == '__main__':
    main()
