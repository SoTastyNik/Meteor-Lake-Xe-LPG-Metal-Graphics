from pathlib import Path
p=Path(__file__).resolve().parent.parent/'latitude-desktop/install-windowserver.sh';s=p.read_text()
s=s.replace('DEST=/Library/GPUBundles/NVMTLDriver.bundle','''codesign --verify --strict "$HERE/Library/NullMoth/latitude-desktop-journal"
/bin/bash -n "$HERE/Library/NullMoth/load-panel-framebuffer.sh"
DEST=/Library/GPUBundles/NVMTLDriver.bundle
HELPER=/Library/NullMoth/latitude-desktop-journal
LOADER=/Library/NullMoth/load-panel-framebuffer.sh''')
s=s.replace('changed=0','''# Capture every file before changing any runtime component.
for file in "$HELPER" "$LOADER"; do
  if [ -e "$file" ]; then cp -p "$file" "$BACKUP/$(basename "$file")"; else touch "$BACKUP/$(basename "$file").absent"; fi
done
changed=0''')
s=s.replace("    if [ -d \"$WORK/previous.bundle\" ]; then",'''    for file in "$HELPER" "$LOADER"; do
      name=$(basename "$file")
      if [ -f "$BACKUP/$name.absent" ]; then rm -f "$file"; else cp -p "$BACKUP/$name" "$file"; fi
    done
    if [ -d "$WORK/previous.bundle" ]; then''')
s=s.replace("previous plugin restored", "previous plugin and capture tools restored")
s=s.replace('shasum -a 256 "$DEST/Contents/MacOS/NVMTLDriver"', '''for file in "$HELPER" "$LOADER"; do
  cp "$HERE/Library/NullMoth/$(basename "$file")" "$file.new"
  chown root:wheel "$file.new"
  chmod 755 "$file.new"
  mv -f "$file.new" "$file"
  cmp -s "$HERE/Library/NullMoth/$(basename "$file")" "$file"
done
codesign --verify --strict "$HELPER"
"$HELPER" prepare
"$HELPER" stage installer-ready candidate0.3.3 0
shasum -a 256 "$HELPER" "$LOADER" > "$REPORT/installed-capture-tools.txt"
shasum -a 256 "$DEST/Contents/MacOS/NVMTLDriver"''')
s=s.replace('candidate0.3.2','candidate0.3.3');p.write_text(s)
