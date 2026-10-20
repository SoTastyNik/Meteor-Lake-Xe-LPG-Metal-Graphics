/* Query ANV identity/heaps; publish through LatitudeMTLFB's root-only reporting endpoint.
 * No logical device, queue, shader, allocation or rendering work is created. */
#import <Foundation/Foundation.h>
#include <IOKit/IOKitLib.h>
#include <sys/sysctl.h>
#include <dlfcn.h>
#include <unistd.h>
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include "latitude_gpu_identity.h"
#ifndef LATITUDE_IDENTITY_ICD
#define LATITUDE_IDENTITY_ICD "/Library/GPUBundles/nvmtl/libvulkan_intel.dylib"
#endif

static int fail(const char *reason) { fprintf(stderr,"GPU identity: %s\n",reason); return 2; }
static BOOL sameID(io_registry_entry_t pci, CFStringRef key, uint32_t wanted) {
    CFTypeRef value=IORegistryEntryCreateCFProperty(pci,key,kCFAllocatorDefault,0);
    uint32_t actual=0; BOOL valid=value && CFGetTypeID(value)==CFDataGetTypeID() && CFDataGetLength(value)==4;
    if(valid) memcpy(&actual,CFDataGetBytePtr(value),4);
    if(value)CFRelease(value);
    return valid && actual==wanted;
}
/* Wait for the kernel claim before touching ANV: firmware attachment is asynchronous. */
static BOOL hardwareReady(void) {
    io_iterator_t iter=0;
    if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("NMXIntelVGAFB"),&iter)!=KERN_SUCCESS)return NO;
    io_service_t fb;unsigned matches=0;BOOL ready=NO;
    while((fb=IOIteratorNext(iter))) {
        io_registry_entry_t claim=0,pci=0;
        if(IORegistryEntryGetParentEntry(fb,kIOServicePlane,&claim)==KERN_SUCCESS &&
           IORegistryEntryGetParentEntry(claim,kIOServicePlane,&pci)==KERN_SUCCESS &&
           sameID(pci,CFSTR("vendor-id"),0x8086) && sameID(pci,CFSTR("device-id"),0x7d45)) {
            ++matches;
            CFTypeRef claimed=IORegistryEntryCreateCFProperty(pci,CFSTR("nmxgpu-claimed"),kCFAllocatorDefault,0);
            ready=claimed && CFGetTypeID(claimed)==CFBooleanGetTypeID() && CFBooleanGetValue(claimed);
            if(claimed)CFRelease(claimed);
        }
        if(pci)IOObjectRelease(pci);if(claim)IOObjectRelease(claim);IOObjectRelease(fb);
    }
    IOObjectRelease(iter);return matches==1 && ready;
}
static int publish(NSDictionary *report) {
    io_iterator_t iter=0;
    if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("NMXIntelVGAFB"),&iter)!=KERN_SUCCESS)
        return fail("framebuffer lookup failed");
    io_service_t fb=0,candidate;io_registry_entry_t pci=0;unsigned matches=0;
    while((candidate=IOIteratorNext(iter))) {
        io_registry_entry_t claim=0,parent=0;
        if(IORegistryEntryGetParentEntry(candidate,kIOServicePlane,&claim)==KERN_SUCCESS &&
           IORegistryEntryGetParentEntry(claim,kIOServicePlane,&parent)==KERN_SUCCESS &&
           sameID(parent,CFSTR("vendor-id"),0x8086) && sameID(parent,CFSTR("device-id"),0x7d45)) {
            ++matches;
            if(!fb) { fb=candidate; candidate=0; pci=parent; parent=0; }
        }
        if(parent)IOObjectRelease(parent);if(claim)IOObjectRelease(claim);if(candidate)IOObjectRelease(candidate);
    }
    IOObjectRelease(iter);
    if(matches!=1) {if(fb)IOObjectRelease(fb);if(pci)IOObjectRelease(pci);return fail("expected exactly one matching physical framebuffer");}
    kern_return_t result=IORegistryEntrySetCFProperties(fb,(__bridge CFTypeRef)@{@"LatitudeGPUIdentity":report});
    BOOL verified=NO;
    if(result==KERN_SUCCESS) {
        CFTypeRef model=IORegistryEntryCreateCFProperty(pci,CFSTR("model"),kCFAllocatorDefault,0);
        CFTypeRef mb=IORegistryEntryCreateCFProperty(pci,CFSTR("VRAM,totalMB"),kCFAllocatorDefault,0);
        NSData *expected=[report[@"name"] dataUsingEncoding:NSUTF8StringEncoding];
        NSMutableData *terminated=[expected mutableCopy];uint8_t zero=0;[terminated appendBytes:&zero length:1];
        verified=model && mb && CFGetTypeID(model)==CFDataGetTypeID() && CFGetTypeID(mb)==CFNumberGetTypeID() &&
                 [(__bridge NSData *)model isEqualToData:terminated] &&
                 [(__bridge NSNumber *)mb unsignedLongLongValue]==([report[@"sharedHeapBytes"] unsignedLongLongValue]>>20);
        if(model)CFRelease(model);if(mb)CFRelease(mb);
    }
    IOObjectRelease(pci);IOObjectRelease(fb);
    if(result!=KERN_SUCCESS) {fprintf(stderr,"GPU identity: driver publication failed 0x%x\n",result);return 3;}
    if(!verified)return fail("published PCI properties failed readback verification");
    puts("GPU identity: PCI model and shared VRAM,totalMB publication VERIFIED");return 0;
}
int main(int argc,char **argv) { @autoreleasepool {
    setvbuf(stdout,NULL,_IONBF,0);
    BOOL queryOnly=argc==2 && !strcmp(argv[1],"--query-only");
    if(argc>1 && !queryOnly)return fail("usage: latitude-gpu-identity [--query-only]");
    if(!queryOnly && geteuid()!=0)return fail("publication requires root");
    if(!queryOnly) {
#ifndef LATITUDE_IDENTITY_RETRIES
#define LATITUDE_IDENTITY_RETRIES 15
#endif
        BOOL ready=NO;
        for(unsigned i=0;i<LATITUDE_IDENTITY_RETRIES;i++) {
            if(hardwareReady()){ready=YES;break;}
            if(i+1<LATITUDE_IDENTITY_RETRIES)sleep(1);
        }
        if(!ready){fail("GPU/framebuffer not ready; no Vulkan query or registry change performed");return 75;}
    }
    /* Direct driver path, no loader selection or spoofed device override from a shell. */
    unsetenv("INTEL_DEVID_OVERRIDE");unsetenv("ANV_FORCE_FAMILY");unsetenv("ANV_SYS_MEM_LIMIT");
    uint64_t ram=0;size_t size=sizeof(ram);
    if(sysctlbyname("hw.memsize",&ram,&size,NULL,0) || size!=sizeof(ram) || !ram)return fail("physical RAM query failed");
    void *library=dlopen(LATITUDE_IDENTITY_ICD,RTLD_NOW|RTLD_LOCAL);
    if(!library)return fail(dlerror());
    PFN_vkGetInstanceProcAddr get=(PFN_vkGetInstanceProcAddr)dlsym(library,"vk_icdGetInstanceProcAddr");
    if(!get)get=(PFN_vkGetInstanceProcAddr)dlsym(library,"vkGetInstanceProcAddr");
    if(!get)return fail("driver entry point unavailable");
    PFN_vkCreateInstance create=(PFN_vkCreateInstance)get(VK_NULL_HANDLE,"vkCreateInstance");
    if(!create)return fail("vkCreateInstance unavailable");
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="LatitudeGPUIdentity",.apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo info={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
    VkInstance instance=VK_NULL_HANDLE;VkResult result=create(&info,NULL,&instance);
    if(result!=VK_SUCCESS) {fprintf(stderr,"GPU identity: vkCreateInstance=%d\n",result);return 2;}
    PFN_vkEnumeratePhysicalDevices enumerate=(PFN_vkEnumeratePhysicalDevices)get(instance,"vkEnumeratePhysicalDevices");
    PFN_vkGetPhysicalDeviceProperties properties=(PFN_vkGetPhysicalDeviceProperties)get(instance,"vkGetPhysicalDeviceProperties");
    PFN_vkGetPhysicalDeviceMemoryProperties memory=(PFN_vkGetPhysicalDeviceMemoryProperties)get(instance,"vkGetPhysicalDeviceMemoryProperties");
    PFN_vkDestroyInstance destroy=(PFN_vkDestroyInstance)get(instance,"vkDestroyInstance");
    int status=2;
    if(!enumerate || !properties || !memory || !destroy) {fail("required Vulkan queries unavailable");goto done;}
    {
        uint32_t count=0;VkPhysicalDevice devices[8];
        if(enumerate(instance,&count,NULL)!=VK_SUCCESS || !count || count>8){fail("invalid physical-device count");goto done;}
        if(enumerate(instance,&count,devices)!=VK_SUCCESS || !count || count>8){fail("physical-device enumeration failed");goto done;}
        VkPhysicalDevice selected=VK_NULL_HANDLE;VkPhysicalDeviceProperties identity={0};unsigned matches=0;
        for(uint32_t i=0;i<count;i++) {
            VkPhysicalDeviceProperties candidate={0};properties(devices[i],&candidate);
            if(candidate.vendorID==0x8086 && candidate.deviceID==0x7d45 && candidate.deviceType==VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU) {
                ++matches;selected=devices[i];identity=candidate;
            }
        }
        if(matches!=1){fail("expected exactly one matching integrated GPU");goto done;}
        VkPhysicalDeviceMemoryProperties heaps={0};memory(selected,&heaps);
        if(!heaps.memoryHeapCount || heaps.memoryHeapCount>VK_MAX_MEMORY_HEAPS ||
           !heaps.memoryTypeCount || heaps.memoryTypeCount>VK_MAX_MEMORY_TYPES){fail("invalid driver heap/type counts");goto done;}
        for(uint32_t i=0;i<heaps.memoryTypeCount;i++)
            if(heaps.memoryTypes[i].heapIndex>=heaps.memoryHeapCount){fail("invalid memory type heap index");goto done;}
        uint64_t capacity=0;
        for(uint32_t i=0;i<heaps.memoryHeapCount;i++) {
            if(!heaps.memoryHeaps[i].size || heaps.memoryHeaps[i].size>ram){fail("invalid shared heap size");goto done;}
            if((heaps.memoryHeaps[i].flags&VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) && heaps.memoryHeaps[i].size>capacity)capacity=heaps.memoryHeaps[i].size;
        }
        unsigned length=(unsigned)strnlen(identity.deviceName,sizeof(identity.deviceName));
        if(length>=sizeof(identity.deviceName) || !latitudeGPUIdentityValid(1,identity.vendorID,identity.deviceID,identity.deviceName,length,capacity,ram)) {
            fail("driver identity/capacity validation failed");goto done;
        }
        NSDictionary *report=@{@"version":@1,@"vendor":@(identity.vendorID),@"device":@(identity.deviceID),
          @"name":[NSString stringWithUTF8String:identity.deviceName],@"sharedHeapBytes":@(capacity),@"physicalRAMBytes":@(ram),
          @"source":@"ANV VkPhysicalDeviceProperties + VkPhysicalDeviceMemoryProperties",@"capacityMeaning":@"maximum shared device-local Vulkan heap; not free RAM or dedicated VRAM"};
        NSData *json=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:NULL];
        fwrite(json.bytes,1,json.length,stdout);putchar('\n');
        status=queryOnly?0:publish(report);
    }
done:
    if(destroy)destroy(instance,NULL);
    dlclose(library);
    return status;
} }
