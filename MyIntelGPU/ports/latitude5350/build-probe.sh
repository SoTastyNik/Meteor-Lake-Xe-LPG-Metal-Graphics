#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
SDK="${KERNEL_SDK_DIR:-../../../MacKernelSDK}"
OUT=build/LatitudeMTLProbe.kext/Contents
mkdir -p "$OUT/MacOS"
xcrun clang++ -std=c++14 -arch x86_64 -mkernel -nostdlib -fno-builtin \
  -fno-exceptions -fno-rtti -fno-stack-protector -DKERNEL -D__STRICT_BSD__ \
  -I"$SDK/Headers" -Os -Wall -Wextra -Wno-unused-parameter \
  -c LatitudeMTLProbe.cpp -o build/LatitudeMTLProbe.o
xcrun clang++ -arch x86_64 -nostdlib -Wl,-kext \
  build/LatitudeMTLProbe.o "$SDK/Library/x86_64/libkmod.a" \
  -o "$OUT/MacOS/LatitudeMTLProbe"
cp Info.plist "$OUT/Info.plist"
plutil -lint "$OUT/Info.plist"
file "$OUT/MacOS/LatitudeMTLProbe"
