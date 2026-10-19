from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parent.parent
src=(r/'NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp').read_text();old=(r/'backups/raw-physical-before/nmxvgafb.cpp').read_text();vm=(r/'NullMoth/gpu-port/xkpi/xnu/nmx_vm.cpp').read_text();apple=(r/'desktop-build/Apple-IOBufferMemoryDescriptor-Sequoia.cpp').read_text()
def fn(s,n):
 a=s.index(n);a=s.rfind('\n',0,a)+1;b=s.index('{',a);j=b+1;d=1
 while d:d+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]+'\n'
a=apple.index('bool contig =');b=apple.index('mappedOrShared =',a);selection=apple[a:b]
options=src[src.index('static const IOOptionBits kNmxRawPhysicalOptions'):src.index('static void nmxVramReleaseBuffer')]
pre=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cassert>
using OSObject=void;using IOOptionBits=unsigned;using IOByteCount=uint64_t;using IOPhysicalAddress=uint64_t;using addr64_t=uint64_t;using mach_vm_address_t=uint64_t;using SInt64=int64_t;using IOReturn=int;
const unsigned kIODirectionInOut=3,kIOMemoryPhysicallyContiguous=0x10,kIOMemoryHostPhysicallyContiguous=0x80,kIOMemoryMapperNone=0x100,kIOMemoryKernelUserShared=0x10000;
const int kernel_task=0,kIOReturnSuccess=0,kIOReturnBadArgument=1,kIOReturnNoSpace=2,kIOReturnNoMemory=3;
const uint64_t PAGE_SIZE=4096;
static bool mapped=true,broken=false,prep_fail=false;static unsigned live=0,complete_n=0;static IOOptionBits last_options;
static bool apple_host_contiguous(IOOptionBits options){
'''
pre+=selection+'return contig; }\n'+r'''
struct IOBufferMemoryDescriptor {
 unsigned refs=1;uint64_t length,span,physical=0x100000;void *bytes;
 IOBufferMemoryDescriptor(uint64_t n,bool contig):length(n),span(contig&&!broken?n:4096),bytes(malloc(n)){assert(bytes);live++;}
 static IOBufferMemoryDescriptor *inTaskWithPhysicalMask(int,IOOptionBits options,uint64_t n,uint64_t){last_options=options;return new IOBufferMemoryDescriptor(n,apple_host_contiguous(options));}
 static IOBufferMemoryDescriptor *inTaskWithOptions(int,IOOptionBits options,uint64_t n,uint64_t){last_options=options;return new IOBufferMemoryDescriptor(n,false);}
 void retain(){refs++;}void release(){if(!--refs){free(bytes);live--;delete this;}}
 void *getBytesNoCopy(){return bytes;}uint64_t getLength(){return length;}
 uint64_t getPhysicalSegment(uint64_t,IOByteCount *s,IOOptionBits f){assert(f==kIOMemoryMapperNone);if(s)*s=span;return physical;}
 int prepare(){return prep_fail?1:0;}void complete(){complete_n++;}
};
static const unsigned kVramSlots=2;static IOBufferMemoryDescriptor *gVramSlot[2];static unsigned gVramSlotBusy,gVramLogs;static unsigned long long gVramSlotBytes;static SInt64 gVramUsed,gVramCookie;static const unsigned long long kVramBudget=536870912;static void *gVramLock=nullptr;
static SInt64 OSAddAtomic64(SInt64 n,SInt64 *p){SInt64 old=*p;*p+=n;return old;}static void IOLockLock(void*){}static void IOLockUnlock(void*){}
#define VFBLOG(...) ((void)0)
#define OSDynamicCast(t,p) static_cast<t*>(p)
#define bzero(p,n) memset(p,0,n)
struct NVRMVramRequest {uint64_t size,phys,actualSize,mappedTotal,allocationCookie;void *handle,*kva;};
'''
body=options+fn(src,'static void nmxVramReleaseBuffer(')+fn(src,'static IOReturn nmxVramAlloc(')+fn(src,'static IOReturn nmxVramFree(')+fn(old,'static IOReturn nmxVramAlloc(').replace('nmxVramAlloc(','old_nmxVramAlloc(',1)+fn(vm,'extern "C" void *nmx_xnu_mem_alloc(')
post=r'''
int main(){
 assert(!apple_host_contiguous(kIODirectionInOut|kIOMemoryPhysicallyContiguous));
 NVRMVramRequest r={};r.size=8192;assert(!old_nmxVramAlloc(&r));auto *unsafe=static_cast<IOBufferMemoryDescriptor*>(r.handle);assert(unsafe->span<r.actualSize);assert(!nmxVramFree(&r)&&!live&&!gVramUsed);
 for(int i=0;i<2000;i++){r={};r.size=8192;assert(!nmxVramAlloc(&r));auto *safe=static_cast<IOBufferMemoryDescriptor*>(r.handle);assert(safe->span>=r.actualSize);assert(last_options&kIOMemoryHostPhysicallyContiguous);assert(last_options&kIOMemoryMapperNone);assert(!nmxVramFree(&r)&&!live&&!gVramUsed);}
 broken=true;r={};r.size=8192;assert(nmxVramAlloc(&r)==kIOReturnNoMemory&&!r.handle&&!live&&!gVramUsed);broken=false;
 // An invalid reserved slot must be made available again after rejection.
 broken=true;gVramLock=(void*)1;gVramSlot[0]=new IOBufferMemoryDescriptor(8192,true);gVramSlotBytes=8192;gVramSlotBusy=2;r={};r.size=8192;assert(nmxVramAlloc(&r)==kIOReturnNoMemory&&gVramSlotBusy==2&&live==1&&!gVramUsed);gVramSlot[0]->release();gVramSlot[0]=nullptr;gVramLock=nullptr;gVramSlotBytes=0;broken=false;
 r={};r.size=~uint64_t(0);assert(nmxVramAlloc(&r)==kIOReturnBadArgument&&!live);r.size=0;assert(nmxVramAlloc(&r)==kIOReturnBadArgument);
 void *h=nullptr;void *p=nmx_xnu_mem_alloc(8192,1,0xffffffff,4096,&h);assert(p&&h);static_cast<IOBufferMemoryDescriptor*>(h)->release();assert(!live);
 broken=true;h=(void*)1;assert(!nmx_xnu_mem_alloc(8192,1,0xffffffff,4096,&h)&&!h&&!live);broken=false;
 h=(void*)1;assert(!nmx_xnu_mem_alloc(8192,1,0x100fff,4096,&h)&&!h&&!live);
 prep_fail=true;h=(void*)1;assert(!nmx_xnu_mem_alloc(8192,1,0xffffffff,4096,&h)&&!h&&!live);prep_fail=false;
 assert(!nmx_xnu_mem_alloc(0,1,0,4096,&h)&&!h&&!live);
 puts("PASS actual Sequoia allocation decision + old/new framebuffer allocator + kernel contiguous allocator under ASan/UBSan: old mapper-enabled export admits a short raw physical segment; corrected flags require host contiguity; short spans rejected, slots/budget recovered,2000 balanced lifetimes, mask/zero/prepare-failure cleanup");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(pre+body+post);subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-fsanitize=address,undefined','-g',str(p/'test.cpp'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
