from pathlib import Path
p=Path('/Users/ved/Documents/iGPU Port/latitude-desktop/install-runtime.sh');s=p.read_text();s=s.replace("echo 'Latitude desktop candidate 0.2.5 — failure handling and conservative GPU barriers'",'''MODE=${1:---readback-only}
case "$MODE" in --readback-only|--desktop) ;; *) echo 'Usage: install-runtime.sh [--readback-only|--desktop]' >&2; exit 2 ;; esac
echo "Latitude candidate 0.2.6 — $MODE"''',1)
s=s.replace('nvram nullmoth-panel-once=1','''if [ "$MODE" = --desktop ]; then
  nvram nullmoth-panel-once=1
else
  # Probe sees no panel opt-in; retain firmware scanout for application tests.
  nvram -d nullmoth-panel-once 2>/dev/null || true
  if nvram nullmoth-panel-once >/dev/null 2>&1; then
    echo 'Panel one-shot is still present; isolated install refused.' >&2
    exit 1
  fi
fi''',1)
s=s.replace('echo "Installed the experimental desktop candidate. Backup: $BACKUP"','echo "Installed candidate 0.2.6 mode=$MODE. Backup: $BACKUP"',1)
s=s.replace("echo 'Reboot through the same USB, then run collect-runtime.sh from this package.'",'''if [ "$MODE" = --readback-only ]; then
  echo 'Reboot through the same USB once. Keep the firmware desktop, then run:'
  echo 'sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh'
else
  echo 'Reboot through the same USB, then run collect-runtime.sh from this package.'
fi''',1)
p.write_text(s)
