from pathlib import Path
import shutil,subprocess,hashlib,json
r=Path(__file__).resolve().parent.parent;u=Path('/Volumes/SEQOUIA/iGPU-Port');p=r/'latitude-desktop'
backup=u/'backups/collector-selection-before';backup.mkdir(parents=True,exist_ok=True)
for f in [u/'collect-desktop-failure.sh',u/'Desktop/collect-readback-failure.sh']:
 dst=backup/f.name
 if not dst.exists():shutil.copy2(f,dst)
f=p/'collect-readback-failure.sh';s=f.read_text().replace('[ -d "$candidate" ] && [ -f "$candidate/results.txt" ] && LATEST=$candidate','[ -d "$candidate" ] && LATEST=$candidate');s=s.replace('last_epoch=$(stat -f %m "$LATEST/results.txt") || exit 2\nstart_epoch=$((last_epoch-150));end_epoch=$((last_epoch+60))','''last_epoch=0
for artifact in "$LATEST"/*.txt; do
  [ -f "$artifact" ] || continue
  epoch=$(stat -f %m "$artifact") || exit 2
  [ "$epoch" -le "$last_epoch" ] || last_epoch=$epoch
done
[ "$last_epoch" -gt 0 ] || { echo 'Latest report has no timestamped evidence'; exit 2; }
start_epoch=$((last_epoch-150));end_epoch=$((last_epoch+60))
# Include driver registration during the report's boot, even if no case ran.
boot_epoch=$(sed -n 's/.*sec = \\([0-9]*\\),.*/\\1/p' "$LATEST/boot.txt" 2>/dev/null)
case "$boot_epoch" in ''|*[!0-9]*) ;; *) start_epoch=$((boot_epoch-5));; esac''');s=s.replace('cp "$LATEST/results.txt" "$LATEST/boot.txt" "$OUT/" 2>/dev/null || true','''for artifact in results.txt boot.txt capture-window.txt accelerator-before.txt loaded-kexts.txt plugin.plist binaries.txt; do
  [ ! -f "$LATEST/$artifact" ] || cp "$LATEST/$artifact" "$OUT/"
done
[ -f "$OUT/results.txt" ] || printf 'Suite stopped before recording case results; see source report and registration evidence.\\n' > "$OUT/results.txt"''');s=s.replace('CONTAINS[c] "GuC"))','CONTAINS[c] "GuC" OR eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "Latitude"))');f.write_text(s)
f=u/'collect-desktop-failure.sh';s=f.read_text();a=s.index('START=${1:');b=s.index('\nOUT=',a);s=s[:a]+'''if [ "$#" -ge 1 ]; then
  START=$1
else
  boot_epoch=''
  for report in "$HERE"/Desktop/reports/readback-[0-9]*; do
    [ ! -f "$report/boot.txt" ] || boot_epoch=$(sed -n 's/.*sec = \\([0-9]*\\),.*/\\1/p' "$report/boot.txt")
  done
  case "$boot_epoch" in ''|*[!0-9]*) boot_epoch=$(($(date +%s)-1200));; esac
  START=$(date -r "$((boot_epoch-5))" '+%Y-%m-%d %H:%M:%S')
fi
END=${2:-$(date '+%Y-%m-%d %H:%M:%S')}'''+s[b:];s=s.replace('watcher=$!','watcher=$!').replace(' ) &\nwatcher=', ' ) >/dev/null 2>&1 &\nwatcher=');s=s.replace(') &\nwatcher=',') >/dev/null 2>&1 &\nwatcher=');f.write_text(s);(r/'desktop-sources/collect-desktop-failure.sh').write_text(s)
for f in [p/'collect-readback-failure.sh',u/'collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
shutil.copy2(p/'collect-readback-failure.sh',u/'Desktop/collect-readback-failure.sh')
f=p/'SHA256SUMS.txt';s=f.read_text();lines=[]
for line in s.splitlines():
 digest,rel=line.split('  ',1)
 if rel=='collect-readback-failure.sh':digest=hashlib.sha256((p/rel).read_bytes()).hexdigest()
 lines.append(digest+'  '+rel)
f.write_text('\n'.join(lines)+'\n');shutil.copy2(f,u/'Desktop/SHA256SUMS.txt')
f=u/'SHA256SUMS.json';m=json.loads(f.read_text());m['collect-desktop-failure.sh']=hashlib.sha256((u/'collect-desktop-failure.sh').read_bytes()).hexdigest();f.write_text(json.dumps(m,indent=2)+'\n')
print('Updated collector report selection and time windows; no driver, EFI or boot marker changes.')
