#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import "../NullMoth/plugin/NVMTLFailedEncoder.m"
#include <assert.h>
static unsigned gpuCalls;
@interface TestEncoder : NSObject
- (void)setScissorRect:(MTLScissorRect)rect;
- (void)setViewport:(MTLViewport)viewport;
- (void)setVertexBytes:(const void *)bytes length:(NSUInteger)length atIndex:(NSUInteger)index;
- (NSUInteger)dispatchType;
- (MTLSize)tileSize;
@end
@implementation TestEncoder
- (void)setScissorRect:(MTLScissorRect)rect { gpuCalls++; }
- (void)setViewport:(MTLViewport)viewport { gpuCalls++; }
- (void)setVertexBytes:(const void *)bytes length:(NSUInteger)length atIndex:(NSUInteger)index { gpuCalls++; }
- (NSUInteger)dispatchType { gpuCalls++; return 42; }
- (MTLSize)tileSize { gpuCalls++; return MTLSizeMake(1,2,3); }
@end
int main(void) { @autoreleasepool {
    NSObject *device = [NSObject new];
    id e = [NVMTLFailedEncoder encoderForDevice:device encodingClass:[TestEncoder class]];
    assert(e != nil && [e device] == device);
    assert([e respondsToSelector:@selector(setScissorRect:)]);
    for (unsigned i=0;i<40000;i++) {
        [e setScissorRect:(MTLScissorRect){0,0,1920,1080}];
        [e setViewport:(MTLViewport){0,0,1920,1080,0,1}];
    }
    char bytes[16]={0}; [e setVertexBytes:bytes length:sizeof bytes atIndex:0];
    [e setLabel:@"failed"]; assert([[e label] isEqual:@"failed"]);
    assert([e dispatchType] == 0);
    MTLSize size=[e tileSize]; assert(!size.width && !size.height && !size.depth);
    [e endEncoding];
    assert(gpuCalls == 0);
} }
