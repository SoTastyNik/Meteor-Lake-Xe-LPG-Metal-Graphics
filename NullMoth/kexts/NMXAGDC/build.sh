#!/bin/bash
# build.sh <out>: NMXAGDC.kext (regenerates nmx-agdc.cpp from NVRMAGDC first)
set -uo pipefail
D=$(cd "$(dirname "$0")" && pwd); OUT=$1; mkdir -p "$OUT/NMXAGDC.kext/Contents/MacOS"
python3 "$D/gen.py" || exit 1
SDK=$(xcrun --show-sdk-path); KHDR="$SDK/System/Library/Frameworks/Kernel.framework/Headers"
xcrun clang++ -arch x86_64 -fapple-kext -mkernel -nostdinc -I"$KHDR" -I"$D" -DKERNEL -DKERNEL_PRIVATE -DDRIVER_PRIVATE -DAPPLE -DNeXT \
  -std=c++17 -fno-rtti -fno-exceptions -fno-builtin -fno-common -Wall -Wno-unused-parameter -Wno-inconsistent-missing-override -Wno-unused-function -O2 \
  -c "$D/nmx-agdc.cpp" -o "$OUT/nmxagdc.o" 2>"$OUT/nmxagdc.err" || { grep error "$OUT/nmxagdc.err" | head; exit 1; }
xcrun clang++ -arch x86_64 -fapple-kext -nostdlib -Xlinker -kext -lkmodc++ -lkmod -lcc_kext "$OUT/nmxagdc.o" \
  -o "$OUT/NMXAGDC.kext/Contents/MacOS/NMXAGDC" || exit 1
cp "$D/Info.plist" "$OUT/NMXAGDC.kext/Contents/Info.plist"
echo "NMXAGDC $(stat -f %z "$OUT/NMXAGDC.kext/Contents/MacOS/NMXAGDC") B"
