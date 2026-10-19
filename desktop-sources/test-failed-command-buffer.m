#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <assert.h>
#include <dlfcn.h>
#import <objc/message.h>
static unsigned presented;
@interface TestFailedDrawable : NSObject
- (void)present;
@end
@implementation TestFailedDrawable
- (void)present { presented++; }
@end
int main(int argc, char **argv) { @autoreleasepool {
    assert(argc == 2);
    void *bundle=dlopen(argv[1],RTLD_NOW | RTLD_LOCAL);
    if (!bundle) { fprintf(stderr,"%s\n",dlerror()); return 2; }
    Class queueClass=NSClassFromString(@"NVMTLCommandQueue"); assert(queueClass);
    id<MTLCommandQueue> queue=[queueClass new]; assert(queue);
    for (unsigned i=0;i<80;i++) { @autoreleasepool {
        id<MTLCommandBuffer> cb = i % 3 == 0 ? [queue commandBuffer] : i % 3 == 1 ? [queue commandBufferWithUnretainedReferences] : [queue commandBufferWithDescriptor:[MTLCommandBufferDescriptor new]]; assert(cb);
        assert(cb.status != MTLCommandBufferStatusCompleted);
        MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
        id<MTLRenderCommandEncoder> encoder=[cb renderCommandEncoderWithDescriptor:pass]; assert(encoder);
        [encoder setScissorRect:(MTLScissorRect){0,0,1920,1080}];
        [encoder setViewport:(MTLViewport){0,0,1920,1080,0,1}];
        [encoder endEncoding];
        id<MTLComputeCommandEncoder> compute=[cb computeCommandEncoderWithDispatchType:MTLDispatchTypeSerial];assert(compute);
        [compute setThreadgroupMemoryLength:16 atIndex:0]; [compute endEncoding];
        __block unsigned completions=0, scheduled=0;
        [cb addScheduledHandler:^(id<MTLCommandBuffer> b){ ++scheduled; }];
        [cb addCompletedHandler:^(id<MTLCommandBuffer> b){ assert(b.status==MTLCommandBufferStatusError); ++completions; }];
        [cb presentDrawable:(id<MTLDrawable>)[TestFailedDrawable new]];
        [cb commit]; [cb waitUntilScheduled]; [cb waitUntilCompleted];
        assert(!((BOOL(*)(id,SEL))objc_msgSend)(cb,NSSelectorFromString(@"commitAndWaitUntilSubmitted")));
        assert(presented==0);
        assert(cb.status==MTLCommandBufferStatusError && cb.error);
        assert(scheduled==0 && completions==1);
    } }
    puts("PASS: 80 failed command buffers, safe encoders, error completion, completion callbacks and capacity release");
} }
