MyIntelGPU — Native Intel Gen 12 iGPU Driver for Hackintosh
Standalone macOS IOKit kernel extension that drives Intel Gen 10–12 integrated GPUs
(Xe-LP, e.g. 8086:A7AC / Core 5 120U) — hardware Apple never shipped a driver for.

No Lilu. No WhateverGreen. No OpenCore injection.  
Pure native driver loaded directly from /Library/Extensions.

✦ Status (2026-10-02)
Layer	Status
PCI setup / MMIO (BAR0/BAR2)	✅
Display / IOFramebuffer	⚠️ BIOS/GOP + IONDRVSupport owns the panel. MyIntelFB probes, builds 1920×1080@60, then loses match within ~2 ms
RCS / BCS / VCS rings + execlists submission	✅
PPGTT identity mapping (GEM buffers)	✅
Media engines (VDBOX/VEBOX detect via 0x138010)	✅
H.264 hardware decode	⏳ Unverified — submission works, ESR=0, but harness shows FAIL-NODATA
ExecBatch / WaitBatch / RingStatus client API	✅ (v4.0.61)
Full Metal / VideoToolbox integration	⏳ Next


⚠️ Hardware Decode Status — Not Proven
Harness output:

Code
[READBACK] probe=20480 poison(0xA5)=2091 zero=0 other=18389
[READBACK] => FAIL-NODATA
[SRC-COHERENCE] aperture vs CPU: MATCH ✅
2091 bytes never written → decode target not producing pixels

ESR=0 → ring retired without error, but no pixel output

[SRC-COHERENCE] MATCH → memory path CPU-coherent

Re-run harness until poison=0 before claiming decode works.

⚙️ Build
bash
cd ~/Documents/GitHub/IntelReviveGPU-Gen-10-12-on-Hackintosh
make BUILD_NUMBER=94 KERNEL_SDK_DIR=~/MacKernelSDK clean
make BUILD_NUMBER=94 KERNEL_SDK_DIR=~/MacKernelSDK -j$(sysctl -n hw.ncpu)
Notes:

BUILD_NUMBER must be set manually → prevents drift from commit count

Never run make as root → fix ownership with chown if needed

🚀 Deploy (Library/Extensions only — never OpenCore)
bash
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/kext-backups/pre-$STAMP
sudo cp -R /Library/Extensions/MyIntelGPU.kext ~/kext-backups/pre-$STAMP/
sudo rm -rf /Library/Extensions/MyIntelGPU.kext
sudo cp -R MyIntelGPU.kext /Library/Extensions/
sudo chown -R root:wheel /Library/Extensions/MyIntelGPU.kext
sudo chmod -R 755 /Library/Extensions/MyIntelGPU.kext
sudo codesign -s - --force /Library/Extensions/MyIntelGPU.kext
sudo kmutil install --volume-root /
Check loaded kexts:

bash
kmutil showloaded | grep -i myintel
🔍 Post-reboot Verification
bash
log show --predicate 'sender == "MyIntelGPU"' --last 20m --style syslog
Expected healthy boot:

TIMING: start total < 1000 ms

SUBMIT[RCS], [BCS], [VCS] lines present

ESR/EIR/IPEIR = 0x00000000

EDID passthrough: injected

system_profiler SPDisplaysDataType → Online: Yes

🧪 Test Harness
bash
cd ~/Documents/src/VCSMediaHarness
clang++ -x objective-c++ -std=c++14 -O2 \
  -framework IOKit -framework CoreFoundation -framework Foundation \
  test_submit_vcs.m MyIntelVCSCommand.cpp -o /tmp/vcs_test_harness
/tmp/vcs_test_harness test_clip.h264 /tmp/vcs_test_out.nv12
📡 Client API (IOUserClient selectors)
Sel	Name	Purpose
0–11	legacy GEM/ring/readback	buffer mgmt, submit proof batches
12	ExecBatch	submit caller-authored command stream
13	WaitBatch	poll HWSP seqno fence
14	RingStatus	telemetry
20–24	accelerator step machine	IOAccelerator adoption path


🏗 Architecture
Code
Userspace (harness / VideoToolbox-bypass)
    │ IOConnectCall
    ▼
MyIntelVCSClient (IOUserClient) ── GEM buffers, PPGTT identity map
    ▼
MyIntelRing (execlists ELSP) ── BB_START → flush → USER_INTERRUPT
    ▼
VDBOX / VCS0 engine (MFX command stream, Gen12)
📖 Deployment Guide
See เส้นทางทำต่อ.md (repo root) and
Desktop/MyIntelGPU-DEPLOY-GUIDE.md for full build/deploy/rollback procedures.

Iron rules:

Deploy only to /Library/Extensions

Backup before deploy

Never reboot mid-deploy
