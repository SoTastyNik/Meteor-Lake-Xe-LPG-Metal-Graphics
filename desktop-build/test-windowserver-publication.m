#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/message.h>
#include <mach/mach.h>
#include <assert.h>
#include <stdatomic.h>
#include "nvmtl_vk.h"
static int gpu_result,copies,scheduled,drained,serial=1;
@class NVMTLCommandBuffer;
@interface NVMTLTexture:NSObject{@public NVMTLTexture *_parent;BOOL refuse;}- (BOOL)nvmtlSurfaceOut;@end
@implementation NVMTLTexture
- (BOOL)nvmtlSurfaceOut{if(refuse)return NO;copies++;return YES;}
@end
@interface NVMTLSubmissionPart:NSObject{@public nvk_cmdbuf commands;NSSet *resources,*surfaces;NSArray *scratch,*signals;id waitEvent,signalEvent;uint64_t value;unsigned encoders;nvmtl_inflight *inflight;int aheadFailed;BOOL waitFolded;}@end
@implementation NVMTLSubmissionPart @end
typedef NSMutableSet NVMTLResSet;
@interface NVMTLBuffer:NSObject @end
@implementation NVMTLBuffer @end
@interface NVMTLCommandBuffer:NSObject{@public BOOL _executionDone,_scheduleAfterPublish,_wasScheduled,_gpuTimingInvalid,_gpuTimingSeen;NSUInteger _nextPart;NSMutableArray *_parts,*_presentations,*_scratch,*_stTwins,*_scheduledHandlers;id _present,_e78Ring,_resources;NSMutableSet *_surfOverwrites;NSUInteger _e78RingOff;void *_g79BRing[8];NSCondition *_completionCondition;NSError *_cbError;MTLCommandBufferStatus _cbstatus;nvmtl_gpu_interval _gpuTiming;double _legacyKernelStart,_legacyKernelEnd,_gpuStart,_gpuEnd;}
- (void)nvmtlDispatchHandlers:(NSArray *)h scheduled:(BOOL)b;
- (void)nvmtlCollectDeviceTiming:(nvk_cmdbuf *)c;
- (void)nvmtlReleaseCapacity;
- (void)nvmtlMarkScheduled;
- (void)nvmtlFinishExecution:(NSError *)e;
- (BOOL)nvmtlAdvancePart;
@end
static NSMutableArray *nvmtl_quarantined_parts;static _Atomic unsigned long long gSkipEmpty;
static int nvmtl_gsub_finish(NVMTLSubmissionPart *p){drained++;p->inflight=NULL;return 0;}
static void nvmtl_surface_finish_writes(NVMTLCommandBuffer *b){}
static void nvmtl_res2_cb_done(NVMTLCommandBuffer *b){}
static BOOL nvmtl_skip_empty_on(void){return NO;}
static NSSet *nvmtl_submission_copies(NSSet *a,BOOL b){return [NSSet set];}
static void nvmtl_buffer_sync_in(NVMTLBuffer *b){}static void nvmtl_buffer_sync_out(NVMTLBuffer *b){}
int nvmtl_vk_submit_wait_at(nvk_cmdbuf *c,const char *who){c->cb=NULL;return gpu_result;}
int nvmtl_vk_cmd_abandon(nvk_cmdbuf *c){return 0;}
int nvmtl_vk_interval_seconds(const nvmtl_gpu_interval *c,double *a,double *b){return -1;}
static void nvmtl_mark_published(NVMTLCommandBuffer *b,NVMTLTexture *t){}
static void nvlog(const char *fmt,...){}
@implementation NVMTLCommandBuffer
- (void)nvmtlDispatchHandlers:(NSArray *)h scheduled:(BOOL)b{if(b)scheduled++;}
- (void)nvmtlCollectDeviceTiming:(nvk_cmdbuf *)c{}
- (void)nvmtlReleaseCapacity{}
- (void)nvmtlMarkScheduled {
    if (_scheduleAfterPublish) return;
    [_completionCondition lock];
    if (!_wasScheduled) {
        _wasScheduled = YES; _cbstatus = MTLCommandBufferStatusScheduled;
        NSArray *handlers = [_scheduledHandlers copy]; [_scheduledHandlers removeAllObjects];
        [self nvmtlDispatchHandlers:handlers scheduled:YES];
        [_completionCondition broadcast];
    }
    [_completionCondition unlock];
}
- (void)nvmtlFinishExecution:(NSError *)error {
    for (NSUInteger i = _nextPart; i < _parts.count; i++) {
        NVMTLSubmissionPart *p = _parts[i];
        if (![p isKindOfClass:[NVMTLSubmissionPart class]] || !p->inflight) continue;
        int result = nvmtl_gsub_finish(p);
        if (!result) [self nvmtlCollectDeviceTiming:&p->commands];
        else _gpuTimingInvalid = YES;
        if (result == -2) {
            if (!nvmtl_quarantined_parts) nvmtl_quarantined_parts = [NSMutableArray new];
            [nvmtl_quarantined_parts addObject:p];
        }
    }
    if (_scheduleAfterPublish) { _scheduleAfterPublish = NO; if (!error) [self nvmtlMarkScheduled]; }
    if (!error) {
        for (dispatch_block_t action in _presentations) action();
    }
    [_presentations removeAllObjects]; _present = nil;
    double deviceStart = 0, deviceEnd = 0;
    if (!error && _gpuTimingSeen && !_gpuTimingInvalid)
        (void)nvmtl_vk_interval_seconds(&_gpuTiming, &deviceStart, &deviceEnd);
    nvmtl_surface_finish_writes(self);
    [_completionCondition lock];
    _gpuStart = deviceStart; _gpuEnd = deviceEnd;
    _legacyKernelEnd = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
    _cbError = error; _cbstatus = error ? MTLCommandBufferStatusError : MTLCommandBufferStatusCompleted;
    _executionDone = YES;
    [_completionCondition unlock];
    [_parts removeAllObjects];
    // A finished command buffer lets go of everything only its GPU work needed: the setBytes ring and the scratch
    // buffers it filled, and any resources still listed on it. Apple's command buffers do the same. An app's
    // autorelease pool can keep thousands of finished command buffers alive during a long loop (Geekbench 7 does),
    // and holding these until the command buffer itself died filled VRAM until allocations were refused.
    [_scratch removeAllObjects]; _e78Ring = nil; _e78RingOff = 0; memset(_g79BRing, 0, sizeof _g79BRing);
    [(NVMTLResSet *)_resources removeAllObjects]; [_stTwins removeAllObjects];
    // Applications may retain completed command buffers. Pending overwrite
    // bookkeeping must not keep their IOSurfaces and VRAM alive indefinitely.
    [_surfOverwrites removeAllObjects]; _surfOverwrites = nil;
    if (!error) nvmtl_res2_cb_done(self);
    [self nvmtlReleaseCapacity];
}
- (BOOL)nvmtlAdvancePart {
    if (_executionDone) return NO;
    if (_cbError) { [self nvmtlFinishExecution:_cbError]; return YES; }
    if (_nextPart >= _parts.count) { [self nvmtlFinishExecution:nil]; return YES; }
    NVMTLSubmissionPart *part = _parts[_nextPart];
    const BOOL ahead = part->inflight || part->aheadFailed;
    if (part->waitEvent && !ahead && !part->waitFolded) {
        if (![part->waitEvent respondsToSelector:@selector(signaledValue)]) {
            [self nvmtlFinishExecution:[NSError errorWithDomain:MTLCommandBufferErrorDomain code:MTLCommandBufferErrorInternal
                userInfo:@{NSLocalizedDescriptionKey:@"Cannot wait on an event from another backend"}]];
            return YES;
        }
        uint64_t have = ((uint64_t(*)(id,SEL))objc_msgSend)(part->waitEvent,@selector(signaledValue));
        if (have < part->value) return NO;
    }
    if (!ahead && part->commands.cb && !part->encoders && !part->resources.count && !part->surfaces.count && !part->scratch.count && nvmtl_skip_empty_on()) {
        [self nvmtlMarkScheduled];
        if (!_legacyKernelStart) _legacyKernelStart = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
        nvmtl_vk_cmd_abandon(&part->commands);
        const unsigned long long k = atomic_fetch_add(&gSkipEmpty, 1);
        if (!k || ((k + 1) & 0xFFF) == 0) nvlog("commit: %llu empty submission parts NOT submitted (no encoder, no resources) - each WAS a full submit + wait", k + 1);
    }
    if (part->commands.cb || ahead) {
        [self nvmtlMarkScheduled];
        if (!_legacyKernelStart) _legacyKernelStart = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
        int result;
        if (part->inflight) result = nvmtl_gsub_finish(part);
        else if (part->aheadFailed) result = part->aheadFailed;
        else {
            for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, NO)) nvmtl_buffer_sync_in(buffer);
            result = nvmtl_vk_submit_wait(&part->commands);
        }
        if (result == -2) {
            if (!nvmtl_quarantined_parts) nvmtl_quarantined_parts = [NSMutableArray new];
            [nvmtl_quarantined_parts addObject:part];
        }
        if (result == 0) [self nvmtlCollectDeviceTiming:&part->commands];
        BOOL published = result == 0;
        if (published) {
            for (NVMTLTexture *texture in part->surfaces) {
                if (![texture nvmtlSurfaceOut]) published = NO;
                else nvmtl_mark_published(self, texture->_parent ? texture->_parent : texture);
            }
            for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, YES)) nvmtl_buffer_sync_out(buffer);
        }
        if (!published) {
            [self nvmtlFinishExecution:[NSError errorWithDomain:MTLCommandBufferErrorDomain code:MTLCommandBufferErrorInternal
                userInfo:@{NSLocalizedDescriptionKey:result ? @"GPU event segment submission failed" : @"Could not publish event segment writes"}]];
            return YES;
        }
    }
    if (part->signalEvent) {
        if (![part->signalEvent respondsToSelector:@selector(setSignaledValue:)]) {
            [self nvmtlFinishExecution:[NSError errorWithDomain:MTLCommandBufferErrorDomain code:MTLCommandBufferErrorInternal
                userInfo:@{NSLocalizedDescriptionKey:@"Cannot signal an event from another backend"}]];
            return YES;
        }
        ((void(*)(id,SEL,uint64_t))objc_msgSend)(part->signalEvent,@selector(setSignaledValue:),part->value);
    }
    for (NSArray *s in part->signals) {
        id event = s[0];
        if (![event respondsToSelector:@selector(setSignaledValue:)]) {
            [self nvmtlFinishExecution:[NSError errorWithDomain:MTLCommandBufferErrorDomain code:MTLCommandBufferErrorInternal
                userInfo:@{NSLocalizedDescriptionKey:@"Cannot signal an event from another backend"}]];
            return YES;
        }
        ((void(*)(id,SEL,uint64_t))objc_msgSend)(event, @selector(setSignaledValue:), [s[1] unsignedLongLongValue]);
    }
    _parts[_nextPart++] = [NSNull null];
    if (_nextPart == _parts.count) [self nvmtlFinishExecution:nil];
    return YES;
}
@end
static NVMTLCommandBuffer *buffer(BOOL fail){NVMTLCommandBuffer *b=[NVMTLCommandBuffer new];b->_completionCondition=[NSCondition new];b->_parts=[NSMutableArray new];b->_presentations=[NSMutableArray new];b->_scheduledHandlers=[NSMutableArray arrayWithObject:@1];b->_scheduleAfterPublish=YES;
 for(int i=0;i<2;i++){NVMTLSubmissionPart *p=[NVMTLSubmissionPart new];p->commands.cb=(void *)1;p->encoders=1;NVMTLTexture *t=[NVMTLTexture new];t->refuse=fail&&i==1;p->surfaces=[NSSet setWithObject:t];[b->_parts addObject:p];}
 return b;}
int main(void){@autoreleasepool{
 for(int mode=0;mode<3;mode++){copies=scheduled=drained=0;gpu_result=0;NVMTLCommandBuffer *b=buffer(mode==1);[b nvmtlMarkScheduled];assert(!scheduled&&!b->_wasScheduled);assert([b nvmtlAdvancePart]);assert(copies==1&&!scheduled&&!b->_executionDone);if(mode==2)gpu_result=-2;assert([b nvmtlAdvancePart]);assert(b->_executionDone);
 if(!mode){assert(copies==2&&scheduled==1&&b->_cbstatus==MTLCommandBufferStatusCompleted);}
 else{assert(scheduled==0&&b->_cbstatus==MTLCommandBufferStatusError&&b->_cbError);}}
 copies=scheduled=drained=0;gpu_result=0;NVMTLCommandBuffer *b=buffer(NO);NVMTLSubmissionPart *p=b->_parts[0];p->inflight=(nvmtl_inflight *)1;[b nvmtlFinishExecution:nil];assert(drained==1&&scheduled==1);
 puts("PASS actual event scheduling/advance/finish methods: no scheduled callback before all surface parts copy out; GPU/copy failures do not advertise publication; outstanding work drained before scheduling");
}}
