from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;p=r/'NullMoth/plugin';back=r/'backups/desktop-0.3.3-before'
def edit(name,old,new,count=1):
 f=p/name
 if not (back/name).exists():shutil.copy2(f,back/name)
 s=f.read_text();assert old in s,(name,old[:80]);f.write_text(s.replace(old,new,count))
edit('nvmtl_vk.h','int nvmtl_vk_windowserver_serial(void);','int nvmtl_vk_windowserver_serial(void);\nvoid nvmtl_desktop_trace(const char *phase,const char *detail,int result);')
edit('NVMTLDevice.m','void nvlog(const char *fmt, ...) {','''#include "nvmtl_desktop_journal.h"
void nvmtl_desktop_trace(const char *phase,const char *detail,int result)
{
    if(strcmp(getprogname(),"WindowServer"))return;
    static _Atomic unsigned records;
    if(atomic_fetch_add(&records,1)>=256)return;
    int error=nvmtl_journal_append(NVMTL_DESKTOP_JOURNAL_PATH,phase,detail,result);
    static _Atomic int reported;
    if(error&&!atomic_exchange(&reported,1))
        syslog(LOG_ERR,"NullMoth: desktop journal unavailable errno=%d",error);
}
void nvlog(const char *fmt, ...) {''')
edit('NVMTLDevice.m','if (nvmtl_log_failure(t)) syslog(LOG_ERR, "NullMoth: %s", t);','if (nvmtl_log_failure(t)) { nvmtl_desktop_trace("plugin-log",t,0); syslog(LOG_ERR, "NullMoth: %s", t); }')
edit('NVMTLObjects.m','static void nvmtl_conf_knobs(void)\n{','static void nvmtl_conf_knobs(void)\n{\n    nvmtl_desktop_trace("plugin-constructor","candidate0.3.3",0);')
edit('nvmtl_vk.c','static void nvmtl_vk_initialize_once(void) { (void)nvmtl_vk_initialize(); }','static void nvmtl_vk_initialize_once(void) { nvmtl_desktop_trace("vk-init-begin","",0); int r=nvmtl_vk_initialize(); nvmtl_desktop_trace("vk-init-end","",r); }')
edit('nvmtl_vk.c','    pthread_once(&g_vk_once, nvmtl_vk_initialize_once);','    nvmtl_desktop_trace("vk-once-enter","",0);\n    pthread_once(&g_vk_once, nvmtl_vk_initialize_once);\n    nvmtl_desktop_trace("vk-once-exit","",g_state);')
edit('nvmtl_vk.c','static pthread_mutex_t nvmtl_desktop_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;','#include "nvmtl_desktop_wait.h"\nstatic pthread_mutex_t nvmtl_desktop_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;')
edit('nvmtl_vk.c','    if(serial)pthread_mutex_lock(&nvmtl_desktop_submit_mutex);','''    if(serial){
        nvmtl_desktop_trace("desktop-lock-wait",who,0);
        int error=nvmtl_desktop_mutex_enter(&nvmtl_desktop_submit_mutex,nvmtl_gpu_wait_budget_ms());
        if(error){
            nvmtl_desktop_trace("desktop-lock-failed",who,error);
            g_state=-1;
            if(c){nvmtl_pool_state(c,NVK_POOL_QUARANTINED);nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);}
            nvlog("vk: desktop submission lock failed %d; backend disabled, resources quarantined",error);
            return -2;
        }
        nvmtl_desktop_trace("desktop-lock-acquired",who,0);
    }''')
edit('nvmtl_vk.c','    if(serial)pthread_mutex_unlock(&nvmtl_desktop_submit_mutex);','    if(serial){pthread_mutex_unlock(&nvmtl_desktop_submit_mutex);nvmtl_desktop_trace("desktop-lock-released",who,result);}')
edit('nvmtl_vk.c','nvmtl_pre_submit_hook(); g_perf_kind = k0;','nvmtl_desktop_trace("presubmit-begin","",0); nvmtl_pre_submit_hook(); nvmtl_desktop_trace("presubmit-end","",0); g_perf_kind = k0;',2)
edit('nvmtl_vk.c','    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;','    nvmtl_desktop_trace("queue-submit-begin",who,0);\n    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;\n    nvmtl_desktop_trace("queue-submit-end",who,result);')
edit('nvmtl_vk.c','    VkResult wr; long waited_ms = 0;','    VkResult wr; long waited_ms = 0;\n    nvmtl_desktop_trace("fence-wait-begin","",0);')
edit('nvmtl_vk.c','    if (nvmtl_submit_trace(f->diagnostic_id) || (wr != VK_SUCCESS && g_vendor == 0x8086))','    nvmtl_desktop_trace("fence-wait-end","",wr);\n    if (nvmtl_submit_trace(f->diagnostic_id) || (wr != VK_SUCCESS && g_vendor == 0x8086))')
print('Applied bounded WindowServer gate and early persistent stage journal')
