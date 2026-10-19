#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IONVRAM.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <pexpert/pexpert.h>
#include <mach/kmod.h>
extern "C" kern_return_t _start(kmod_info_t *,void *) { return KERN_SUCCESS; }
extern "C" kern_return_t _stop(kmod_info_t *,void *) { return KERN_SUCCESS; }
extern "C" { KMOD_EXPLICIT_DECL(com.nullmoth.LatitudePanelClaim,"0.2.0",_start,_stop) }
static bool claimed = false;
class LatitudePanelClaim : public IOService {
 OSDeclareDefaultStructors(LatitudePanelClaim)
 IOWorkLoop *loop = nullptr;
 IOTimerEventSource *timer = nullptr;
 bool holding = false;
 void releaseHold() { if (holding) { holding=false;adjustBusy(-1); } }
 static void timeout(OSObject *owner,IOTimerEventSource *) {
  auto me=OSDynamicCast(LatitudePanelClaim,owner);if(!me)return;
  me->retain();bool hasFB=false;
  if(OSIterator *it=me->getClientIterator()) { while(OSObject *o=it->getNextObject()) {
   IOService *c=OSDynamicCast(IOService,o);if(c&&c->metaCast("IOFramebuffer")&&!c->isInactive())hasFB=true;
  }it->release(); }
  me->releaseHold();
  if(!hasFB) {
   IOLog("LatitudePanelClaim: no framebuffer after 45 seconds; releasing PCI category for firmware fallback\n");
   IOService *pci=me->getProvider();if(pci)pci->retain();
   me->terminate(kIOServiceRequired);
   if(pci){pci->registerService(kIOServiceAsynchronous);pci->release();}
  }
  me->release();
 }
public:
 IOService *probe(IOService *provider,SInt32 *score) override {
  auto pci=OSDynamicCast(IOPCIDevice,provider);
  if(!pci||claimed||pci->configRead16(kIOPCIConfigVendorID)!=0x8086||pci->configRead16(kIOPCIConfigDeviceID)!=0x7d45||pci->configRead16(kIOPCIConfigSubSystemVendorID)!=0x1028||pci->configRead16(kIOPCIConfigSubSystemID)!=0x0cb6)return nullptr;
  PE_Video v={};IOPlatformExpert *pe=getPlatform();
  if(!pe||pe->getConsoleInfo(&v)!=kIOReturnSuccess||!v.v_baseAddr||v.v_depth!=32||v.v_width<640||v.v_height<480||v.v_rowBytes<v.v_width*4)return nullptr;
  IODeviceMemory *ap=pci->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress2);
  uint64_t base=v.v_baseAddr&~0xfffull,bytes=(uint64_t)v.v_rowBytes*v.v_height;
  if(!ap||base<ap->getPhysicalAddress()||bytes>ap->getLength()||base-ap->getPhysicalAddress()>ap->getLength()-bytes)return nullptr;
  bool once=false;
  if(IORegistryEntry *e=IORegistryEntry::fromPath("/options",gIODTPlane)) {
   if(auto n=OSDynamicCast(IODTNVRAM,e)) {
    if(OSObject *o=n->copyProperty("nullmoth-panel-once")) {
     o->release();once=true;
     if(const OSSymbol *key=OSSymbol::withCString("nullmoth-panel-once")){n->removeProperty(key);key->release();}n->sync();
    }
   }e->release();
  }
  if(!once)return nullptr;
  claimed=true;setProperty("LatitudePanelOptedIn",kOSBooleanTrue);
  IOLog("LatitudePanelClaim: one-shot consumed; reserving firmware panel for Auxiliary KC framebuffer\n");
  return IOService::probe(provider,score);
 }
 bool start(IOService *provider) override {
  if(!IOService::start(provider))return false;
  loop=IOWorkLoop::workLoop();timer=IOTimerEventSource::timerEventSource(this,timeout);
  if(!loop||!timer||loop->addEventSource(timer)!=kIOReturnSuccess){OSSafeReleaseNULL(timer);OSSafeReleaseNULL(loop);return false;}
  holding=true;adjustBusy(1);timer->setTimeoutMS(45000);registerService();return true;
 }
 IOReturn callPlatformFunction(const OSSymbol *fn,bool wait,void *p1,void *p2,void *p3,void *p4) override {
  if(fn&&fn->isEqualTo("latitudePanelFramebufferReady")){if(timer)timer->cancelTimeout();setProperty("LatitudePanelFramebufferReady",kOSBooleanTrue);releaseHold();return kIOReturnSuccess;}
  return IOService::callPlatformFunction(fn,wait,p1,p2,p3,p4);
 }
 void stop(IOService *provider) override {
  if(timer){timer->cancelTimeout();if(loop)loop->removeEventSource(timer);}OSSafeReleaseNULL(timer);OSSafeReleaseNULL(loop);releaseHold();IOService::stop(provider);
 }
};
OSDefineMetaClassAndStructors(LatitudePanelClaim,IOService)
