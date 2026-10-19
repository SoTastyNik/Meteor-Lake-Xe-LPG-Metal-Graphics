from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;p=r/'NullMoth/plugin';b=r/'backups/desktop-0.3.5-before';b.mkdir(parents=True,exist_ok=True)
for f in [p/'nvmtl_vk.c',p/'NVMTLObjects.m',p/'nvmtl_desktop_policy.h',r/'latitude-desktop/install-windowserver.sh',r/'latitude-desktop/Library/NullMoth/load-panel-framebuffer.sh']:
 shutil.copy2(f,b/f.name)
f=p/'nvmtl_desktop_policy.h';s=f.read_text()+'''
/* Set before the Intel ICD is loaded: its debug parser is process-once. */
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
static inline int nvmtl_windowserver_disable_ccs(uint16_t vendor,uint16_t device,const char *process)
{
    if(!nvmtl_windowserver_serial_policy(vendor,device,process))return 0;
    const char *previous=getenv("INTEL_DEBUG");
    char flags[4096];
    int n=snprintf(flags,sizeof flags,"%s%snoccs",previous?previous:"",previous&&*previous?",":"");
    if(n<0||(size_t)n>=sizeof flags)return -E2BIG;
    if(setenv("INTEL_DEBUG",flags,1))return -errno;
    return 1;
}
''';f.write_text(s)
f=p/'nvmtl_vk.c';s=f.read_text();needle='''    const uint16_t vendor = nvmtl_vk_vendor();''';s=s.replace(needle,needle+'''
    const int compression_policy=nvmtl_windowserver_disable_ccs(vendor,g_pci_device,getprogname());
    if(compression_policy<0){nvlog("first-submit: FAILED compression policy errno=%d",-compression_policy);return -1;}
    if(compression_policy)nvmtl_desktop_trace("compression-policy","INTEL_DEBUG includes noccs before ICD loading",0);
''',1);s=s.replace('candidate0.3.4: serial completion','candidate0.3.5: noccs; serial completion');f.write_text(s)
for f in [p/'NVMTLObjects.m',r/'latitude-desktop/install-windowserver.sh',r/'latitude-desktop/Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/latitude-desktop-journal.c']:
 s=f.read_text().replace('candidate0.3.4','candidate0.3.5');f.write_text(s)
p=r/'desktop-sources/build-windowserver-0.3.4.py';s=p.read_text().replace('0.3.4','0.3.5');(r/'desktop-sources/build-windowserver-0.3.5.py').write_text(s)
print('Scoped noccs policy set before ICD load; app/other-device environment unaffected')
