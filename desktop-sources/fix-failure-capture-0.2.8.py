from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'NullMoth/plugin/NVMTLDevice.m';s=f.read_text();old='''    uint64_t rep; if (nvlog_dropped(fmt, &rep)) return;
    char b[512];''';new='''    const char *diagnostic_env = getenv("NVMTL_DIAGNOSTIC_STDERR");
    const int diagnostic = diagnostic_env && !strcmp(diagnostic_env, "1");
    uint64_t rep; const int dropped = nvlog_dropped(fmt, &rep);
    if (dropped && !diagnostic) return;
    char b[512];''';assert old in s;s=s.replace(old,new,1)
old='''#if NVMTL_RELEASE
    if (nvmtl_log_failure(t)) syslog(LOG_ERR, "NullMoth: %s", t);''';new='''    /* Explicit test clients retain failures and copy/submit traces directly,
       independently of per-site syslog throttling or historical-log queries. */
    if (diagnostic && nvmtl_log_failure(t)) {
        fprintf(stderr, "NVMTL-DIAG pid=%d ns=%llu %s\\n", getpid(),
            (unsigned long long)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW), t);
        fflush(stderr);
    }
    if (dropped) return;
#if NVMTL_RELEASE
    if (nvmtl_log_failure(t)) syslog(LOG_ERR, "NullMoth: %s", t);''';assert old in s;s=s.replace(old,new,1);f.write_text(s)
f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text();s=s.replace('if (g_state != 1 || !c || !c->cb) return -2;', 'if (g_state != 1 || !c || !c->cb) { nvlog("vk: submit FAILED phase=backend-or-command state=%d command=%p", g_state, c ? c->cb : NULL); return -2; }',1)
s=s.replace('if (result != VK_SUCCESS) { nvmtl_cmd_retire(c); return -1; }','if (result != VK_SUCCESS) { nvlog("vk: submit FAILED phase=vkEndCommandBuffer result=%d", result); nvmtl_cmd_retire(c); return -1; }',1)
s=s.replace('if (result != VK_SUCCESS) { nvmtl_cmd_retire(c); return -1; }','if (result != VK_SUCCESS) { nvlog("vk: submit FAILED phase=vkCreateFence result=%d", result); nvmtl_cmd_retire(c); return -1; }',1)
s=s.replace('if (nvmtl_vk_init()) return -1;\n    const uint64_t b0', 'if (nvmtl_vk_init()) { nvlog("vk: recording FAILED phase=backend-init state=%d",g_state); return -1; }\n    const uint64_t b0',1)
s=s.replace('if (owned ? nvmtl_vk_buffer_create(plan.bytes, 3, &stage) : nvmtl_vk_stage(q, plan.bytes, &stage)) return -1;', '''if (owned ? nvmtl_vk_buffer_create(plan.bytes, 3, &stage) : nvmtl_vk_stage(q, plan.bytes, &stage)) {
        nvlog("readback FAILED phase=staging-allocation image=%p bytes=%zu owned=%d",img->img,plan.bytes,owned); return -1;
    }''',1)
s=s.replace('if (nvmtl_vk_cmd_begin(q, &c)) { if (owned) nvmtl_vk_buffer_destroy(&stage); return -1; }','''if (nvmtl_vk_cmd_begin(q, &c)) {
        nvlog("readback FAILED phase=record-begin image=%p stage=%p bytes=%zu",img->img,stage.buf,plan.bytes);
        if (owned) nvmtl_vk_buffer_destroy(&stage); return -1;
    }''',1)
s=s.replace('''    if (rc) return -1;
    for (uint32_t row=0;row<plan.rows;row++)''','''    if (rc) {
        nvlog("readback FAILED phase=submit-or-completion result=%d image-id=%llu stage-id=%llu; CPU destination untouched",rc,(unsigned long long)image_id,(unsigned long long)stage.trace_id);
        return rc;
    }
    for (uint32_t row=0;row<plan.rows;row++)''',1);f.write_text(s)
f=r/'latitude-desktop/test-readback.sh';s=f.read_text().replace('0.2.7','0.2.8');s=s.replace('COUNT=${1:-100}', '''COUNT=${1:-100}
PROFILE=${2:-full}
case "$PROFILE" in full|retained|fresh-pools|fresh-staging) ;; *) echo 'Profile must be full, retained, fresh-pools or fresh-staging'; exit 2 ;; esac''',1)
s=s.replace('''mkdir -p "$OUT"''','''mkdir -p "$OUT"
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
printf 'start=%s profile=%s\\n' "$START_TIME" "$PROFILE" > "$OUT/capture-window.txt"
LIVE_CHILD=''
stop_live() {
  if [ -n "$LIVE_CHILD" ]; then kill -TERM "$LIVE_CHILD" 2>/dev/null || true; wait "$LIVE_CHILD" 2>/dev/null || true; LIVE_CHILD=''; fi
}
trap stop_live EXIT
''',1)
needle='''echo "Readback suite: $COUNT iterations per worker/case. Progress every 50 frames. Logs: $OUT"''';s=s.replace(needle,'''log stream --style compact --level debug --predicate 'process == "kernel" AND (eventMessage CONTAINS[c] "i915" OR eventMessage CONTAINS[c] "drmn" OR eventMessage CONTAINS[c] "GPU HANG" OR eventMessage CONTAINS[c] "GuC") OR subsystem == "org.nullmoth.libdrm"' > "$OUT/kernel-live.txt" 2>&1 &
LIVE_CHILD=$!
echo "Readback suite: $COUNT iterations per worker/case, profile=$PROFILE. Progress every 50 frames. Logs: $OUT"''',1)
s=s.replace('NVMTL_ENABLE=1 NMX_DRM_TEST_TRANSPORT=', 'NVMTL_ENABLE=1 NVMTL_DIAGNOSTIC_STDERR=1 NMX_DRM_TEST_TRANSPORT=',1)
s=s.replace('''result=0
for route in iokit direct; do''','''result=0
ROUTES=(iokit direct)
[ "$PROFILE" = full ] || ROUTES=(iokit)
for route in "${ROUTES[@]}"; do''',1)
needle='''  run_case "$route-padded" "$route" 1 retained --size 1920x1080 --padding 64 || { result=1; break; }''';repl='''  if [ "$PROFILE" != full ]; then
    pool_mode=1;stage_mode=retained
    [ "$PROFILE" != fresh-pools ] || pool_mode=0
    [ "$PROFILE" != fresh-staging ] || stage_mode=fresh
    run_case "$route-padded-$PROFILE" "$route" "$pool_mode" "$stage_mode" --size 1920x1080 --padding 64 || result=1
    break
  fi
'''+needle;assert needle in s;s=s.replace(needle,repl,1)
s=s.replace('''# Bounded historical capture, without issuing more GPU work after a failure.
log show --last 20m --style compact''','''# Capture only this run, starting at its recorded wall-clock timestamp.
# Primary failure evidence is already in each test's stderr and live stream.
stop_live
END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
printf 'end=%s\\n' "$END_TIME" >> "$OUT/capture-window.txt"
log show --start "$START_TIME" --end "$END_TIME" --style compact''',1)
s=s.replace('''if [ "$COUNT" -ge 1000 ]; then echo "0.2.8 iterations=$COUNT all-22-cases-pass"''','''if [ "$COUNT" -ge 1000 ] && [ "$PROFILE" = full ]; then echo "0.2.8 iterations=$COUNT all-22-cases-pass"''',1)
f.write_text(s)
f=r/'latitude-desktop/install-runtime.sh';f.write_text(f.read_text().replace('0.2.7','0.2.8'))
