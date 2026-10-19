from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text();needle='static VkCommandPool nvmtl_keep_pool_pop(void)\n{';s=s.replace(needle,'''static int nvmtl_command_pool_fresh(void)
{
    const char *e=getenv("NVMTL_COMMAND_POOL_FRESH");
    return e && !strcmp(e,"1");
}
static VkCommandPool nvmtl_keep_pool_pop(void)
{''',1)
s=s.replace('if (!nvmtl_keep_on()) return p;', 'if (!nvmtl_keep_on() || nvmtl_command_pool_fresh()) return p;',1)
s=s.replace('if (!nvmtl_keep_on()) return 0;\n    pthread_mutex_lock(&g_keep_lock); if (g_keep_npool', 'if (!nvmtl_keep_on() || nvmtl_command_pool_fresh()) return 0;\n    pthread_mutex_lock(&g_keep_lock); if (g_keep_npool',1);f.write_text(s)
f=r/'latitude-desktop/test-readback.sh';s=f.read_text();s=s.replace('NVMTL_POOL_REUSE="$pools"', 'NVMTL_POOL_REUSE=1',1)
s=s.replace('''  [ "$stages" = retained ] || envargs+=(NVMTL_READBACK_STAGE_FRESH=1)''','''  [ "$stages" = retained ] || envargs+=(NVMTL_READBACK_STAGE_FRESH=1)
  [ "$pools" != 0 ] || envargs+=(NVMTL_COMMAND_POOL_FRESH=1)
  printf 'route=%s command-pools=%s readback-staging=%s witness=enabled address-page-cache=enabled\\n' "$route" "$pools" "$stages" > "$OUT/$name-policy.txt"''',1)
s=s.replace('-u NVMTL_READBACK_STAGE_FRESH -u NVMTL_NO_POOL_REUSE', '-u NVMTL_COMMAND_POOL_FRESH -u NVMTL_READBACK_STAGE_FRESH -u NVMTL_NO_POOL_REUSE',1)
needle='''log stream --style compact''';s=s.replace(needle,'''# Never compare two profiles in one GPU boot, especially after a reset.
BOOT_UUID=$(sysctl -n kern.bootsessionuuid) || exit 2
[ -n "$BOOT_UUID" ] || exit 2
printf '%s\\n' "$BOOT_UUID" > "$OUT/boot-session.txt"
if [ "$PROFILE" != full ]; then
  LAST_BOOT="$HERE/reports/comparison-last-boot.txt"
  if [ -f "$LAST_BOOT" ] && [ "$(cat "$LAST_BOOT")" = "$BOOT_UUID" ]; then
    echo 'A comparison already ran this boot. Prepare and reboot USB before another profile.'; exit 2
  fi
  if nvram nullmoth-gpu-once >/dev/null 2>&1; then
    echo 'GPU opt-in is pending. Reboot through USB before running the comparison.'; exit 2
  fi
  printf '%s\\n' "$BOOT_UUID" > "$LAST_BOOT"
fi
log stream --style compact''',1)
s=s.replace('''if [ "$COUNT" -ge 1000 ] && [ "$PROFILE" = full ]; then echo "0.2.8 iterations=$COUNT all-22-cases-pass" > "$OUT/desktop-gate.txt"; fi''', '''echo 'Diagnostic candidate only: desktop activation remains disabled.' ''',1);f.write_text(s)
f=r/'latitude-desktop/install-runtime.sh';s=f.read_text().replace('''case "$MODE" in --readback-only|--desktop) ;; *) echo 'Usage: install-runtime.sh [--readback-only|--desktop]' >&2; exit 2 ;; esac''','''case "$MODE" in --readback-only) ;; *) echo 'Candidate 0.2.8 supports --readback-only; desktop activation is disabled during comparison.' >&2; exit 2 ;; esac''',1);s=s.replace('echo \'sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh\'','echo \'sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools\'',1);f.write_text(s)
f=r/'latitude-desktop/test-and-arm-desktop.sh';s=f.read_text();backup=r/'backups/desktop-0.2.8-before/test-and-arm-desktop.sh';backup.write_text(s);f.write_text('''#!/bin/bash
set -euo pipefail
echo 'Candidate 0.2.8 is a diagnostic comparison. Desktop activation is disabled.' >&2
echo 'Use sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools' >&2
exit 2
''')
(r/'latitude-desktop/diagnose-readback.sh').write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROFILE=${1:-fresh-pools}
case "$PROFILE" in retained|fresh-pools|fresh-staging) ;; *) echo 'Use retained, fresh-pools or fresh-staging.' >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Dell.' >&2; exit 2; }
echo "Diagnostic comparison: $PROFILE. Same three warmup tests, then 1000 padded frames."
/bin/bash "$HERE/test-readback.sh" 1000 "$PROFILE"
result=$?
echo "COMPARISON profile=$PROFILE exit=$result"
echo 'Desktop remains disabled. Bring back the USB report before choosing the next profile.'
exit "$result"
''')
(r/'latitude-desktop/prepare-readback-boot.sh').write_text('''#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] && [ "$(uname -m)" = x86_64 ] || { echo 'Run with sudo on the Intel Dell.' >&2; exit 2; }
nvram -d nullmoth-panel-once 2>/dev/null || true
if nvram nullmoth-panel-once >/dev/null 2>&1; then echo 'Panel opt-in could not be removed.' >&2; exit 1; fi
nvram nullmoth-gpu-once=1
echo 'Prepared ONE GPU-only boot. Reboot through USB before the next comparison.'
echo 'This script has not rebooted the laptop or enabled the custom panel.'
''')
