from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'latitude-desktop/test-readback.sh';s=f.read_text().replace('0.2.6','0.2.7');s=s.replace('NVMTLDriver.bundle/Contents/MacOS/*','NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver',1)
s=s.replace('''for route in direct iokit; do''','''for route in iokit direct; do
  echo "Checking $route device discovery before Metal enumeration..."
  "${USERCMD[@]}" env NMX_DRM_TEST_TRANSPORT="$route" "$HERE/tools/latitude-drm-route-test" > "$OUT/$route-discovery.txt" 2>&1
  probe=$?;cat "$OUT/$route-discovery.txt"
  if [ "$probe" != 0 ]; then echo "$route-discovery exit=$probe" >> "$OUT/results.txt"; result=1; break; fi''',1)
s=s.replace('''  echo "$name exit=$result" | tee''','''  case "$name" in *-iosurface|*-bgra-surface)
    grep -q '^PASS IOSurface backing:' "$log" || result=1 ;;
  esac
  echo "$name exit=$result" | tee''',1)
s=s.replace('''done
# Bounded historical''','''  run_case "$route-bgra-surface" "$route" 1 retained --size 1920x1080 --padding 64 --iosurface --bgra || { result=1; break; }
done
# Bounded historical''',1)
s=s.replace('eventMessage CONTAINS[c] "first-submit"\'','eventMessage CONTAINS[c] "first-submit" OR subsystem == "org.nullmoth.libdrm"\'',1)
s=s.replace('( sleep 30; kill -TERM "$child" 2>/dev/null )','( sleep 30; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null )',1)
s=s.replace('''echo "Saved report: $OUT"''','''if [ "$result" = 0 ]; then
  shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib > "$OUT/passing-binaries.txt"
  if [ "$COUNT" -ge 1000 ]; then echo "0.2.7 iterations=$COUNT all-22-cases-pass" > "$OUT/desktop-gate.txt"; fi
fi
echo "Saved report: $OUT"''',1)
f.write_text(s)
f=r/'latitude-desktop/install-runtime.sh';s=f.read_text().replace('0.2.6','0.2.7');f.write_text(s)
