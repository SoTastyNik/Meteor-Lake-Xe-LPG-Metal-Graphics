from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;p=r/'NullMoth/plugin';b=r/'backups/desktop-0.3.4-before';b.mkdir(parents=True,exist_ok=True)
for f in [p/'nvmtl_vk.c',p/'NVMTLDevice.m',p/'nvmtl_desktop_policy.h',r/'latitude-desktop/Library/NullMoth/load-panel-framebuffer.sh',r/'latitude-desktop/install-windowserver.sh']:
 if not (b/f.name).exists():shutil.copy2(f,b/f.name)
f=p/'nvmtl_desktop_policy.h';s=f.read_text()+'''
/* Dedicated readback allocation: avoid TLS retention and suballocation/park reuse
   only for the physical Meteor Lake WindowServer candidate. */
static inline int nvmtl_windowserver_fresh_readback(uint16_t vendor,uint16_t device,const char *process)
{
    return nvmtl_windowserver_serial_policy(vendor,device,process);
}
''';f.write_text(s)
f=p/'NVMTLDevice.m';s=f.read_text();a=s.index('#include "nvmtl_desktop_journal.h"');e=s.index('\nvoid nvlog(',a)
s=s[:a]+'''/* WindowServer cannot write the pre-created log file under its sandbox.
   Use its existing system-log channel; the root loader streams and flushes it. */
void nvmtl_desktop_trace(const char *phase,const char *detail,int result)
{
    if(strcmp(getprogname(),"WindowServer"))return;
    static _Atomic unsigned records;
    unsigned record=atomic_fetch_add(&records,1);
    if(record>=256)return;
    uint64_t tid=0;pthread_threadid_np(NULL,&tid);
    syslog(LOG_ERR,"NullMoth: desktop-trace: #%u ns=%llu tid=%llu phase=%.64s result=%d detail=%.480s",
        record+1,(unsigned long long)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW),
        (unsigned long long)tid,phase?phase:"?",result,detail?detail:"");
}
'''+s[e:]
# Do not recursively duplicate every existing failure/submit log through the trace budget.
s=s.replace('nvmtl_desktop_trace("plugin-log",t,0); ','')
# First-submit already has its own finite ID budget. Per-site throttling hid submission9+.
s=s.replace('const int dropped = nvlog_dropped(fmt, &rep);','const int dropped = nvlog_dropped(fmt, &rep);\n    const int startup = !strcmp(getprogname(),"WindowServer") && !strncmp(fmt,"first-submit:",13);')
s=s.replace('if (dropped && !diagnostic) return;','if (dropped && !diagnostic && !startup) return;').replace('    if (dropped) return;','    if (dropped && !startup) return;');f.write_text(s)
f=p/'nvmtl_vk.c';s=f.read_text();old='''    nvmtl_desktop_trace("vk-once-enter","",0);
    pthread_once(&g_vk_once, nvmtl_vk_initialize_once);
    nvmtl_desktop_trace("vk-once-exit","",g_state);''';new='''    static _Atomic unsigned init_calls;
    const int trace=atomic_fetch_add(&init_calls,1)<4;
    if(trace)nvmtl_desktop_trace("vk-once-enter","",0);
    pthread_once(&g_vk_once, nvmtl_vk_initialize_once);
    if(trace)nvmtl_desktop_trace("vk-once-exit","",g_state);''';assert old in s;s=s.replace(old,new)
old='    const int owned = getenv("NVMTL_READBACK_STAGE_FRESH") != NULL;';new='''    const int desktop_fresh=nvmtl_windowserver_fresh_readback(g_vendor,g_pci_device,getprogname());
    const int owned = desktop_fresh || getenv("NVMTL_READBACK_STAGE_FRESH") != NULL;''';assert old in s;s=s.replace(old,new)
# Log exact disposal and free proven pre-submit failures; keep uncertain work.
s=s.replace('''    if (rc) {
        nvlog("readback FAILED phase=submit-or-completion''','''    if (rc) {
        if(owned && rc==-1 && g_state==1)nvmtl_vk_buffer_destroy(&stage);
        nvlog("readback FAILED phase=submit-or-completion''',1)
s=s.replace('(stage && !strcmp(stage,"1")?16u:0u);','((stage && !strcmp(stage,"1")) || nvmtl_windowserver_fresh_readback(g_vendor,g_pci_device,getprogname())?16u:0u);')
s=s.replace('schedule-after-surface-publication; fresh command pools remain enforced','schedule-after-surface-publication; dedicated fresh readback staging; fresh command pools remain enforced')
f.write_text(s)
f=p/'NVMTLObjects.m';s=f.read_text();shutil.copy2(f,b/f.name);f.write_text(s.replace('candidate0.3.3','candidate0.3.4'))
f=r/'latitude-desktop/install-windowserver.sh';s=f.read_text().replace('candidate0.3.3','candidate0.3.4');f.write_text(s)
f=r/'latitude-desktop/Library/NullMoth/load-panel-framebuffer.sh';s=f.read_text().replace('candidate0.3.3','candidate0.3.4');old='''  stage sample-begin WindowServer
  bounded 10 /usr/bin/sample WindowServer 3 10 -file "$SAMPLE" > "$SAMPLEERR" 2>&1; result=$?''';new='''  # Resolve a positive PID; sample(name) returned process0/exit0 without a file.
  pid=$(/usr/bin/pgrep -x WindowServer | /usr/bin/head -n 1)
  case "$pid" in ''|*[!0-9]*) result=2; echo 'No valid WindowServer PID for sample' > "$SAMPLEERR" ;;
    *)
      if [ "$pid" -le 1 ]; then result=2; echo 'Refusing sample PID0/1' > "$SAMPLEERR"
      else
        stage sample-begin "$pid"
        bounded 10 /usr/bin/sample "$pid" 3 10 -file "$SAMPLE" > "$SAMPLEERR" 2>&1; result=$?
        if [ "$result" = 0 ] && { [ ! -s "$SAMPLE" ] || /usr/bin/grep -Eq 'pid_for_task.*failed|Sampling process 0' "$SAMPLEERR"; }; then
          result=2; echo 'Sample reported success without a usable target stack' >> "$SAMPLEERR"
        fi
      fi ;;
  esac''';assert old in s;s=s.replace(old,new);f.write_text(s)
print('Applied scoped dedicated fresh staging, known pre-submit cleanup, sandbox-compatible startup syslog, complete finite submit trace and honest sampler status')
