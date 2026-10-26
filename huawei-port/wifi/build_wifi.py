"""Build AirportItlwm (Sequoia) for the MateBook 14 Intel Wi-Fi 6 AX201 on Meteor Lake CNVi (8086:7E40, RF "hr").

Base: laobamac/itlwm d695c971 + the Dell port's MTL/API83 changes, rolled back to the Dell-tested 0.1.0 state
(reverse of the 0.1.2 candidate's AWDL diffs). The Dell build only selected API83 firmware for the AX211 ("gf")
RF; this adds the same selection for "hr" on MA B-step (Linux: iwlwifi-ma-b0-hr-b0) and lets hr use the
API83 command paths, which depend on the firmware API rather than the RF. PNVM stays gf-only, as in Linux.

Usage (repository root, macOS with Xcode):  python3 huawei-port/wifi/build_wifi.py <out dir>
"""
import base64
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve()
SRC = OUT / 'itlwm'
BASE = 'd695c971420cc8af0daa286dcd3297e8236c0a63'
SDK = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'  # acidanthera/MacKernelSDK, pinned by laobamac's own CI
DELL = R / 'port-artifacts/awdl-radio-0.1.2-20261021/iGPU-Port/Peripherals/Continuity/Candidate-0.1.2/Source'
FW_URL = 'https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware.git/+/refs/tags/20251011/intel/iwlwifi/'
FIRMWARE = {
    'iwlwifi-ma-b0-gf-a0-83.ucode': '9386a8294457f527c6e0fa1eac440c50cbee801707fdb480a10889770c0d297b',
    'iwlwifi-ma-b0-gf-a0.pnvm': 'b21d3257a2a434ca4660353a7144c436eafaf8e60d0542e3159eaffee4de5629',
    'iwlwifi-ma-b0-hr-b0-83.ucode': '03b67d28b4916634c544e057abdc46b15b636a85064df993ca431fd92fe4a835',
}
GF = '"iwlwifi-ma-b0-gf-a0-83.ucode"'
HR = '"iwlwifi-ma-b0-hr-b0-83.ucode"'


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def replace(text, old, new, count):
    assert text.count(old) == count, (old[:80], text.count(old))
    return text.replace(old, new)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if SRC.exists():
        shutil.rmtree(SRC)
    sh('git', 'clone', '--quiet', 'https://github.com/laobamac/itlwm.git', str(SRC))
    sh('git', 'checkout', '--quiet', BASE, cwd=SRC)
    sh('git', 'clone', '--quiet', 'https://github.com/acidanthera/MacKernelSDK.git', str(SRC / 'MacKernelSDK'))
    sh('git', 'checkout', '--quiet', SDK, cwd=SRC / 'MacKernelSDK')
    for f in (DELL / 'Modified').rglob('*'):
        if f.is_file():
            dst = SRC / f.relative_to(DELL / 'Modified')
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
    # 0.1.2 candidate -> Dell-tested 0.1.0 (drops the unvalidated AWDL radio bridge from the RX/TX paths)
    for patch in ['0.1.1-to-0.1.2.patch', '0.1.0-to-0.1.1.patch']:
        sh('git', 'apply', '-R', '--whitespace=nowarn', str(DELL / patch), cwd=SRC)

    for name, digest in FIRMWARE.items():
        data = base64.b64decode(urllib.request.urlopen(FW_URL + name + '?format=TEXT').read())
        assert hashlib.sha256(data).hexdigest() == digest, name
        (SRC / 'itlwm/firmware' / name).write_bytes(data)
    (SRC / 'include/FwBinary.cpp').unlink(missing_ok=True)  # regenerated from itlwm/firmware by the build phase

    p = SRC / 'itlwm/hal_iwx/ItlIwx.cpp'
    s = p.read_text()
    # firmware selection: AX201 (hr) on MA B-step gets the official b0/API83 image
    s = replace(s, '''        if (latitude_parent) latitude_parent->setProperty("LatitudeWiFiFirmwareSelection", "ma-b0-api83-trial");
    } else if (device == 0x7e40 && latitude_parent) {''', '''        if (latitude_parent) latitude_parent->setProperty("LatitudeWiFiFirmwareSelection", "ma-b0-api83-trial");
    } else if (device == 0x7e40 && CSR_HW_REV_TYPE(sc->sc_hw_rev) == IWL_CFG_MAC_TYPE_MA &&
        IWX_CSR_HW_REV_STEP(sc->sc_hw_rev) == IWX_SILICON_B_STEP &&
        sc->sc_cfg == &iwl_cfg_ma_a0_hr_b0) {
        sc->sc_fwname = ''' + HR + ''';
        if (latitude_parent) latitude_parent->setProperty("LatitudeWiFiFirmwareSelection", "ma-b0-hr-api83-huawei");
    } else if (device == 0x7e40 && latitude_parent) {''', 1)
    # API83 command paths (MLD link, internal AUX, MAC_CONFIG v2) apply to either API83 image
    s = replace(s, f'        strcmp(sc->sc_fwname, {GF}) == 0 &&',
                f'        (strcmp(sc->sc_fwname, {GF}) == 0 || strcmp(sc->sc_fwname, {HR}) == 0) &&', 3)
    p.write_text(s)
    assert s.count(HR) == 4 and s.count(f'if (strcmp(sc->sc_fwname, {GF}) == 0)') == 1  # PNVM override stays gf-only

    # WCLDBG: the Sequoia recovery scans but never joins (no node_join_bss, no AUTH); macOS applies a private MAC,
    # the firmware restarts, and the join is lost somewhere between WCL and net80211. Log each step once per event.
    p = SRC / 'AirportItlwm/WCL/WCL.cpp'
    s = p.read_text()
    s = replace(s, '''    // Applying a private MAC restarts firmware asynchronously.''', '''    IOLog("itlwm: WCLDBG join request auth=%d running=%d joinPending=%d scanPending=%d macReconfig=%d ssidLen=%u upper=0x%x lower=0x%x\\n",
          int(auth), (ic->ic_if.if_flags & IFF_RUNNING) != 0, joinPending, scanPending, ic->ic_wcl_mac_reconfig,
          unsigned(join.ssidLength), unsigned(join.upperAuth), unsigned(join.lowerAuth));
    // Applying a private MAC restarts firmware asynchronously.''', 1)
    s = replace(s, '''        return !supported ? kIOReturnUnsupported : kIOReturnBusy;''', '''        IOLog("itlwm: WCLDBG join refused: %s\\n", !supported ? "unsupported auth" : "busy/not running");
        return !supported ? kIOReturnUnsupported : kIOReturnBusy;''', 1)
    s = replace(s, '''void AirportItlwmSkywalkInterface::resumeWCLJoin()
{
''', '''void AirportItlwmSkywalkInterface::resumeWCLJoin()
{
    IOLog("itlwm: WCLDBG resume join deferred=%d stopping=%d\\n", joinDeferred, wclStopping);
''', 1)
    s = replace(s, '''void AirportItlwmSkywalkInterface::finishWCLJoin(uint16_t status, uint16_t reason, IOReturn driverStatus)
{
''', '''void AirportItlwmSkywalkInterface::finishWCLJoin(uint16_t status, uint16_t reason, IOReturn driverStatus)
{
    IOLog("itlwm: WCLDBG finish join pending=%d status=%u reason=%u driver=0x%x\\n", joinPending, status, reason, driverStatus);
''', 1)
    s = replace(s, '''            bool ready = code == IEEE80211_EVT_DRIVER_READY;
''', '''            bool ready = code == IEEE80211_EVT_DRIVER_READY;
            IOLog("itlwm: WCLDBG driver %s macReconfig=%d deferred=%d\\n", ready ? "READY" : "STOPPED",
                  ic->ic_wcl_mac_reconfig, joinDeferred);
''', 1)
    p.write_text(s)
    p = SRC / 'itl80211/openbsd/net80211/ieee80211_node.c'
    s = p.read_text()
    s = replace(s, '''    /* We don't care about unrelated networks during background scans. */''', '''    if (ic->ic_des_esslen != 0 && ni->ni_esslen == ic->ic_des_esslen &&
        memcmp(ni->ni_essid, ic->ic_des_essid, ic->ic_des_esslen) == 0)
        XYLog("WCLDBG match fail=0x%x chan=%d protos=0x%x/0x%x akms=0x%x/0x%x ciphers=0x%x/0x%x group=%d mgmt=%d caps=0x%x psk=%d\\n",
              fail, ieee80211_chan2ieee(ic, ni->ni_chan), ni->ni_rsnprotos, ic->ic_rsnprotos, ni->ni_rsnakms,
              ic->ic_rsnakms, ni->ni_rsnciphers, ic->ic_rsnciphers, ni->ni_rsngroupcipher, ni->ni_rsngroupmgmtcipher,
              ni->ni_rsncaps, (ic->ic_flags & IEEE80211_F_PSK) != 0);

    /* We don't care about unrelated networks during background scans. */''', 1)
    p.write_text(s)

    build = OUT / 'build'
    with (OUT / 'xcodebuild.log').open('w') as log:
        r = subprocess.run(['xcodebuild', '-project', 'itlwm.xcodeproj', '-scheme', 'AirportItlwm-Sequoia',
                            '-configuration', 'Release', '-jobs', '3', 'ARCHS=x86_64', 'ONLY_ACTIVE_ARCH=NO',
                            'GIT_COMMIT=_' + BASE[:7] + '-huawei-hr',
                            'SYMROOT=' + str(build / 'products'), 'OBJROOT=' + str(build / 'obj'),
                            'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'build'],
                           cwd=SRC, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode:
        print((OUT / 'xcodebuild.log').read_text()[-12000:])
        raise SystemExit('xcodebuild failed')
    kext = next((build / 'products').rglob('AirportItlwm.kext'))
    dst = OUT / 'AirportItlwm.kext'
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(kext, dst)
    binary = (dst / 'Contents/MacOS/AirportItlwm').read_bytes()
    assert HR.strip('"').encode() in binary, 'hr firmware name not linked'
    sh('codesign', '--force', '--sign', '-', str(dst))
    print('built', dst)


if __name__ == '__main__':
    main()
