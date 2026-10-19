from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;p=r/'NullMoth/plugin';back=r/'backups/desktop-0.3.2-before';back.mkdir(parents=True,exist_ok=True)
for name in ['nvmtl_vk.c','nvmtl_vk.h','NVMTLEventSync.m','nvmtl_desktop_policy.h']:
 if not (back/name).exists():shutil.copy2(p/name,back/name)
f=p/'nvmtl_desktop_policy.h';s=f.read_text();s+='''\nstatic inline int nvmtl_windowserver_serial_policy(uint16_t vendor, uint16_t device, const char *process)
{
    return vendor == 0x8086 && device == 0x7d45 && process && !strcmp(process,"WindowServer");
}
''';f.write_text(s)
f=p/'nvmtl_vk.h';s=f.read_text();needle='uint32_t nvmtl_vk_diagnostic_policy(void);';assert needle in s;s=s.replace(needle,needle+'\nint nvmtl_vk_windowserver_serial(void);');f.write_text(s)
f=p/'nvmtl_vk.c';s=f.read_text();needle='static pthread_mutex_t nvmtl_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;';assert needle in s;s=s.replace(needle,needle+'''
static pthread_mutex_t nvmtl_desktop_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;
int nvmtl_vk_windowserver_serial(void)
{
    return nvmtl_windowserver_serial_policy(g_vendor,g_pci_device,getprogname());
}
''');old='''    nvmtl_inflight f;
    const int r = nvmtl_vk_submit_begin_at(c, &f, who);
    return r ? r : nvmtl_vk_submit_finish(&f);''';new='''    const int serial=nvmtl_vk_windowserver_serial();
    if(serial)pthread_mutex_lock(&nvmtl_desktop_submit_mutex);
    nvmtl_inflight f;
    const int r = nvmtl_vk_submit_begin_at(c, &f, who);
    const int result=r ? r : nvmtl_vk_submit_finish(&f);
    if(serial)pthread_mutex_unlock(&nvmtl_desktop_submit_mutex);
    return result;''';assert old in s;s=s.replace(old,new);needle='''    g_state = 1;''';# Put policy diagnostic at begin once vendor/device are selected, without changing init state ordering.
needle2='''    if (!getenv("NVRM_FLUSH_TIMEOUT_MS")) {''';assert needle2 in s;s=s.replace(needle2,'''    if(nvmtl_windowserver_serial_policy(vendor,g_pci_device,getprogname()))
        nvlog("desktop-policy: WindowServer 8086:7d45 serial completion, submit-ahead disabled, schedule-after-surface-publication; fresh command pools remain enforced");
'''+needle2,1);f.write_text(s)
f=p/'NVMTLEventSync.m';s=f.read_text();needle='''- (BOOL)nvmtlSubmitAhead {
    if (_executionDone''';assert needle in s;s=s.replace(needle,'''- (BOOL)nvmtlSubmitAhead {
    if (nvmtl_vk_windowserver_serial()) return NO;
    if (_executionDone''');old='''    for (NVMTLTexture *s in part->surfaces) if (after && s != drawable) _scheduleAfterPublish = YES;''';new='''    for (NVMTLTexture *s in part->surfaces)
        if (nvmtl_vk_windowserver_serial() || (after && s != drawable)) _scheduleAfterPublish = YES;''';assert old in s;s=s.replace(old,new)
# Move the scheduling notification after draining outstanding parts too.
old='''    if (_scheduleAfterPublish) { _scheduleAfterPublish = NO; [self nvmtlMarkScheduled]; }
    for (NSUInteger i = _nextPart;''';assert old in s;s=s.replace(old,'''    for (NSUInteger i = _nextPart;''');needle='''    if (!error) {
        for (dispatch_block_t action in _presentations) action();''';assert needle in s;s=s.replace(needle,'''    if (_scheduleAfterPublish) { _scheduleAfterPublish = NO; [self nvmtlMarkScheduled]; }
    if (!error) {
        for (dispatch_block_t action in _presentations) action();''');f.write_text(s)
print('Applied WindowServer-only serial completion and surface-publication scheduling policy; application and kernel paths preserved.')
