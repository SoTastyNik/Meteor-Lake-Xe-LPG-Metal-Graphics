#!/bin/bash
# build-guest.sh [all|xe|link] <out dir>: builds NMXGPU.kext in the macOS VM with Nullmoth's own scripts.
#   all  - everything (DRM core + amdgpu, i915, xe, the runtime), then links
#   xe   - xe only (after a fork_xe.py / override/xe change), then links
#   link - only the link step
# The scripts expect their Mac's layout (/Volumes/MiniData/build/gpu-src, /opt/homebrew/bin/python3); the guest
# bootstrap (vm/guest/bootstrap.sh) makes those paths exist.
set -uo pipefail
X=/Volumes/MiniData/build/gpu-src/xkpi
WHAT=${1:-all}; OUT=${2:-$HOME/build/out}
cd "$X" || exit 1
mkdir -p fbroot obj obj-i915 obj-xe lkobj srcobj xnuobj logs logs-i915 logs-xe lklogs srclogs xnulogs "$OUT"
# fbroot: a FreeBSD source-root view for includes like <compat/linuxkpi/...> and <contrib/dev/acpica/...>
# (not in Nullmoth's repo; its NMXNPU source archive carries the same layout)
mkdir -p fbroot fbroot/contrib
[ -e fbroot/compat ] || ln -s ../../kpi/freebsd-src/sys/compat fbroot/compat
[ -e fbroot/contrib/dev ] || ln -s ../../../kpi/freebsd-src/sys/contrib/dev fbroot/contrib/dev
[ -e fbroot/contrib/ck ] || ln -s ../../../kpi/freebsd-src/sys/contrib/ck fbroot/contrib/ck
# xe includes <uapi/drm/xe_drm.h>, but cc-xe.sh only has -I$V/include/uapi: make uapi/ resolve inside it
[ -e ../linux-6.14/include/uapi/uapi ] || ln -s . ../linux-6.14/include/uapi/uapi
[ -f amd.flags ] || /opt/homebrew/bin/python3 gen_flags.py ../kpi/drm-kmod amd.flags || exit 1
t0=$(date +%s)
# a step that stops before compiling (all-xe.sh exits 1 when fork_xe.py's anchors no longer match) leaves no .failed
# file behind, only stale objects: it counts as a failure too
stepfail=0
case "$WHAT" in
    all)  ./all.sh 25; ./all-i915.sh 25; ./all-xe.sh 25 || stepfail=1; ./rt.sh | tee rt.out ;;
    xe)   ./all-xe.sh 25 || stepfail=1 ;;
    rt)   ./rt.sh | tee rt.out ;;
    xert) ./all-xe.sh 25 || stepfail=1; ./rt.sh | tee rt.out ;;
    link) ;;
    *) echo "usage: $0 [all|xe|rt|xert|link] <out>"; exit 2 ;;
esac
# the runtime (rt.sh) reports its failures as "LK FAIL x" / "SRC FAIL x" lines, not .failed files
rtfail=0; case "$WHAT" in rt|xert|all) rtfail=$(grep -c -E '^(LK|SRC|XNU) FAIL' rt.out) ;; esac
fail=$(( stepfail + rtfail + $(ls logs/*.failed 2>/dev/null | wc -l) + $(ls logs-i915/*.failed 2>/dev/null | wc -l) + $(find logs-xe -name '*.failed' | wc -l) ))
echo "compile failures: $fail ($(( $(date +%s) - t0 )) s)"
# never link stale objects over a failed compile
if [ "$fail" != 0 ]; then
    for f in $(ls logs/*.failed logs-i915/*.failed 2>/dev/null; find logs-xe -name '*.failed'); do grep -m3 -A2 "error:" "${f%.failed}.log"; done
    grep -E '^(LK|SRC|XNU) FAIL' rt.out 2>/dev/null | while read -r _ _ b; do grep -h -m3 -A2 "error:" srclog_$b.txt lklogs/$b.log 2>/dev/null; done
    rm -rf "$OUT/NMXGPU.kext"; exit 1
fi
# rt.sh compiles every xnu/*.cpp, NMXNPU's kext stub included; it has its own kmod_info and belongs to the NPU kext
rm -f xnuobj/nmx_npu_kext.o
rm -rf "$OUT/NMXGPU.kext"
kext/build.sh "$OUT"
