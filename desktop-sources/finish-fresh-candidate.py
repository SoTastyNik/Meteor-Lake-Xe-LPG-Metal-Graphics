from pathlib import Path
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop'
f=r/'desktop-sources/test-pool-lifetime.py';s=f.read_text().replace("a=s.index('static pthread_mutex_t nvmtl_submit_mutex')","a=s.index('/* created, destroyed, live, peak, quarantined, pending, completed, abandoned */')");f.write_text(s)
f=p/'tools/latitude-readback-test.m';s=f.read_text().replace('!strcmp(expectedPolicy,"retained")?13u:!strcmp(expectedPolicy,"fresh-pools")?15u:!strcmp(expectedPolicy,"fresh-staging")?29u:0u','!strcmp(expectedPolicy,"enforced")?47u:!strcmp(expectedPolicy,"enforced-fresh-staging")?63u:0u');needle=' if(atomic_load(&failed))return 1;\n if(surface)';repl=''' if(!native){
  SEL stats=NSSelectorFromString(@"nvmtlCommandPoolStats");
  NSArray *v=[gpu respondsToSelector:stats]?((id(*)(id,SEL))objc_msgSend)(gpu,stats):nil;
  if(v.count!=8){error("command pool statistics unavailable",0,0);}
  else {
   unsigned long long n[8];for(unsigned i=0;i<8;i++)n[i]=[v[i] unsignedLongLongValue];
   printf("POOL created=%llu destroyed=%llu live=%llu peak=%llu quarantined=%llu pending=%llu completed=%llu abandoned=%llu\\n",n[0],n[1],n[2],n[3],n[4],n[5],n[6],n[7]);
   if(!n[0]||!n[3]||n[0]!=n[1]||n[2]||n[4]||n[5]||n[0]!=n[6]+n[7])error("command pool cleanup imbalance",0,0);
   else puts("PASS command-pool cleanup: all created pools destroyed; zero live, pending or quarantined pools");
  }
 }
 if(atomic_load(&failed))return 1;
 if(surface)''';assert needle in s;s=s.replace(needle,repl);f.write_text(s)
f=p/'test-readback.sh';s=f.read_text().replace('0.2.9','0.3.0');s=s.replace('  local expected_policy=retained\n  [ "$pools" != 0 ] || expected_policy=fresh-pools\n  [ "$stages" = retained ] || expected_policy=fresh-staging','  local expected_policy=enforced\n  [ "$stages" = retained ] || expected_policy=enforced-fresh-staging');s=s.replace('command-pools=%s','legacy-case-selector=%s command-pools=fresh-enforced');s=s.replace("    grep -q '^PASS exact readback:'", "    grep -q '^PASS command-pool cleanup:' \"$log\" || result=1\n    grep -q '^PASS exact readback:'");s=s.replace('wait "$child"; kill "$watcher"','wait "$child"; capture_result=$?; kill "$watcher"');s=s.replace("printf 'READBACK SUITE exit=",'''if grep -Ei 'GPU HANG|Resetting (chip|rcs|engine)|GT[0-9 ]* reset' "$OUT/kernel-live.txt" "$OUT/gpu-history.txt" > "$OUT/hang-check.txt"; then
  echo 'FAIL GPU hang/reset recorded during suite'; result=1
fi
if [ "$capture_result" != 0 ]; then echo 'FAIL bounded historical capture incomplete'; result=1; fi
printf 'READBACK SUITE exit=''');s=s.replace("  echo 'Diagnostic candidate only: desktop activation remains disabled.' ",'''  if [ "$PROFILE" = full ] && [ "$COUNT" -ge 1000 ] && [ "$(grep -c ' exit=0$' "$OUT/results.txt")" = 22 ]; then
    { printf 'candidate=0.3.0 cases=22 iterations=%s boot=%s\\n' "$COUNT" "$BOOT_UUID"; cat "$OUT/passing-binaries.txt"; } > "$OUT/desktop-gate.txt"
    if [ -n "${READBACK_GATE_FILE:-}" ]; then cp "$OUT/desktop-gate.txt" "$READBACK_GATE_FILE" || exit 2; fi
    echo 'PASS full 22-case hardware gate, including effective policy and pool cleanup.'
  fi''');f.write_text(s)
(p/'test-and-arm-desktop.sh').write_text('''#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(uname -m)" = x86_64 ] && [ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Intel Dell.'; exit 2; }
GATE=$(mktemp -t latitude-fresh-gate)
EXPECTED=$(mktemp -t latitude-fresh-expected)
armed=0
cleanup() {
  rm -f "$GATE" "$EXPECTED"
  if [ "$armed" = 1 ]; then nvram -d nullmoth-panel-once 2>/dev/null || true; nvram -d nullmoth-gpu-once 2>/dev/null || true; fi
}
trap cleanup EXIT
READBACK_GATE_FILE="$GATE" /bin/bash "$HERE/test-readback.sh" 1000 full
{ printf 'candidate=0.3.0 cases=22 iterations=1000 boot=%s\\n' "$(sysctl -n kern.bootsessionuuid)"; shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib; } > "$EXPECTED"
cmp -s "$GATE" "$EXPECTED" || { echo 'FAIL missing/stale hardware gate or changed installed binaries; desktop not armed.'; exit 2; }
for relative in NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver nvmtl/libdrm.2.dylib; do
  cmp -s "$HERE/Library/GPUBundles/$relative" "/Library/GPUBundles/$relative" || { echo 'FAIL candidate binary changed during testing'; exit 2; }
done
armed=1
nvram nullmoth-gpu-once=1
nvram nullmoth-panel-once=1
armed=0
echo 'Full 22-case gate passed. One desktop boot armed. Reboot through this USB when ready.'
echo 'If the display fails, power off and boot this USB again for the firmware-display fallback.'
''')
f=p/'install-runtime.sh';s=f.read_text().replace('0.2.9','0.3.0').replace('desktop activation is disabled during comparison.','desktop activation requires the full test-and-arm-desktop.sh gate.').replace('iGPU-Port/diagnose-readback.sh fresh-pools','iGPU-Port/test-and-arm-desktop.sh');f.write_text(s)
f=r/'desktop-sources/test-release-probe-controls.py';s=f.read_text().replace('expected!=4','expected!=38').replace('0.2.9','0.3.0').replace("{},13","{},47").replace("'1'},15","'1'},47").replace("'1'},29","'1'},63").replace("'1'},4)","'1'},38)");s=s.replace("for executable,changes,expected in [", "for executable,changes,expected in [('latitude-readback-test',{'NVMTL_COMMAND_POOL_FRESH':'0'},47),");f.write_text(s)
