/*
 * NullMoth NVIDIA driver for macOS
 * Copyright (c) 2026 NullMoth Systems.
 * SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
 */

@interface NVMTLQueueReservation : NSObject { @public __weak NVMTLCommandBuffer *buffer; } @end
@implementation NVMTLQueueReservation @end
@interface NVMTLSubmissionPart : NSObject {
@public
    nvk_cmdbuf commands;
    NSSet *resources, *surfaces;
    NSSet *hybridOut;   // hybrid surfaces whose copy to their own pages this part records
    NSSet *tile4Mark;   // v49: surfaces this part made zero copy; completion marks them "NMXTile4" before publishing
    NSArray *scratch;
    id waitEvent, signalEvent;
    uint64_t value;
    unsigned encoders;
    NSArray *signals;
    nvmtl_inflight *inflight;
    int aheadFailed;
    BOOL waitFolded;
    BOOL aheadEmpty;
    BOOL submitting;      // split submit: the submit queue is in this part's execbuffer, the class lock released
    BOOL aheadDeclined;   // the ahead pass will never submit it (host pointers, no recording): the worker does
}
@end
static _Atomic unsigned gsub_inflight;
static void nvmtl_ws_timing_census(NVMTLCommandBuffer *cb, double deviceStart, double deviceEnd);
static _Atomic unsigned long long gsub_ahead, gsub_peak;
static _Atomic unsigned long long gAheadWork;   // parts the ahead pass submitted, folded or retired
static BOOL nvmtl_split_submit_on(void);
static void nvmtl_kick_submit(void);
static NSMutableArray *nvmtl_quarantined_parts;
static int nvmtl_gsub_finish(NVMTLSubmissionPart *part) {
    nvmtl_inflight *const f = part->inflight;
    part->inflight = NULL;
    const int r = nvmtl_vk_submit_finish(f);
    atomic_fetch_sub(&gsub_inflight, 1);
    if (r == 0) nvmtl_vk_inflight_free(f);
    return r;
}
@interface NVMTLPendingSurfaceWrite : NSObject {
@public __weak NVMTLCommandBuffer *buffer; __weak NVMTLTexture *texture; uint32_t seed;
}
@end
@implementation NVMTLPendingSurfaceWrite @end
// Queue keys and command-buffer references are weak. An abandoned recording is
// never registered; completion removes committed entries without retaining VRAM.
static NSMapTable *nvmtl_surface_writers;
// v40: a tagged-pointer number, not a formatted string (17 of WindowServer's main-thread samples per 1.8 s in v39)
static NSNumber *nvmtl_surface_writer_key(NVMTLTexture *t) {
    return @(((unsigned long long)IOSurfaceGetID(t->_surf) << 16) | (unsigned long long)(t->_plane & 0xFFFF));
}
static BOOL nvmtl_surface_pending_write(NVMTLCommandBuffer *cb, NVMTLTexture *t) {
    if (!cb || !t || !t->_surf) return NO;
    @synchronized ([NVMTLCommandBuffer class]) {
        NSNumber *key = nvmtl_surface_writer_key(t);
        for (id queue in nvmtl_surface_writers.keyEnumerator) {
            NSDictionary *writes = [nvmtl_surface_writers objectForKey:queue];
            NVMTLPendingSurfaceWrite *write = writes[key];
            NVMTLCommandBuffer *writer = write ? write->buffer : nil;
            NVMTLTexture *backing = write ? write->texture : nil;
            const BOOL sameBacking = backing && (backing == t || (backing->_vramOn && t->_vramOn));
            if (writer && writer != cb && sameBacking && write->seed == IOSurfaceGetSeed(t->_surf)) return YES;
        }
        return NO;
    }
}
static void nvmtl_surface_register_writes(NVMTLCommandBuffer *cb) {
    // The same lock as pending_write and finish_writes, taken here too: the map is shared with the completion thread, and
    // its one caller holding this (recursive) lock today must not be what keeps WindowServer's heap intact.
    @synchronized ([NVMTLCommandBuffer class]) {
        if (!nvmtl_surface_writers) nvmtl_surface_writers = [NSMapTable weakToStrongObjectsMapTable];
        NSMutableDictionary *writes = [nvmtl_surface_writers objectForKey:cb->_queue];
        for (NVMTLSubmissionPart *part in cb->_parts) for (NVMTLTexture *t in part->surfaces) {
            if (!t->_surf) continue;
            if (!writes) { writes = [NSMutableDictionary new]; [nvmtl_surface_writers setObject:writes forKey:cb->_queue]; }
            NVMTLPendingSurfaceWrite *write = [NVMTLPendingSurfaceWrite new];
            write->buffer = cb; write->texture = t; write->seed = IOSurfaceGetSeed(t->_surf);
            writes[nvmtl_surface_writer_key(t)] = write;
        }
    }
}
static void nvmtl_surface_finish_writes(NVMTLCommandBuffer *cb) {
    @synchronized ([NVMTLCommandBuffer class]) {
        NSMutableDictionary *writes = [nvmtl_surface_writers objectForKey:cb->_queue];
        for (id key in [writes.allKeys copy]) {
            NVMTLPendingSurfaceWrite *write = writes[key];
            if (!write->buffer || write->buffer == cb) [writes removeObjectForKey:key];
        }
        if (!writes.count) [nvmtl_surface_writers removeObjectForKey:cb->_queue];
    }
}

@implementation NVMTLSubmissionPart
- (void)dealloc {
    if (inflight) {
        nvlog("commit: G-SUB BUG - a part submitted ahead reached dealloc unfinished; finishing it now");
        if (nvmtl_gsub_finish(self) != 0) {
            (void)CFBridgingRetain(resources); (void)CFBridgingRetain(surfaces); (void)CFBridgingRetain(scratch);
            memset(&commands, 0, sizeof commands);
            return;
        }
    }
    if (commands.cb) nvmtl_vk_cmd_abandon(&commands);
}
@end

static NSMutableArray<NVMTLCommandBuffer *> *nvmtl_pending_buffers;
static BOOL nvmtl_pumping;
static void nvmtl_pump_buffers(void);
static BOOL nvmtl_async_commit_on(void) {
    static int on = -1;
    if (on < 0) { const char *e = getenv("NVMTL_ASYNC_COMMIT"); on = !(e && e[0] == '0');
        nvlog("commit: %s (NVMTL_ASYNC_COMMIT=%s)", on ? "ASYNC (default) - execution worker, submit ahead, queue capacity enforced" : "synchronous (NVMTL_ASYNC_COMMIT=0)", e ? e : "unset"); }
    return on;
}
static _Atomic unsigned long long gSkipEmpty;
static int nvmtl_skip_empty_on(void) {
    static int on = -1;
    if (on < 0) { const char *e = getenv("NVMTL_SKIP_EMPTY"); on = !(e && e[0] == '0');
        nvlog("commit: empty submission parts %s (NVMTL_SKIP_EMPTY=%s)", on ? "are NOT submitted" : "are submitted as before b78", e ? e : "unset"); }
    return on;
}

@implementation NVMTLCommandBuffer (EventSubmission)
- (void)nvmtlReserveQueue {
    if (_reservation) return;
    NVMTLQueueReservation *r = [NVMTLQueueReservation new]; r->buffer = self;
    _reservation = r;
    if (!_queue->_reservations) _queue->_reservations = [NSMutableArray new];
    [_queue->_reservations addObject:r];
}
- (void)nvmtlReleaseReservation {
    if (_reservation) [_queue->_reservations removeObjectIdenticalTo:_reservation];
    _reservation = nil;
}
/*
 * v49: a hybrid surface the panel has now shown becomes zero copy. Its tiled private image is copied into a Tile4 image
 * over the surface's own pages, which it draws into from then on; the private image lives until this command buffer
 * completes (a texture holding it rides in its resources) and then goes to the image park. Not while a view of the
 * surface exists: a view holds an image view of the private image. The frame showing the switch may show once with
 * the plane still linear; the next flip, after completion marked the surface, is Tile4.
 */
static BOOL nvmtl_surface_promote(NVMTLCommandBuffer *cb, NVMTLTexture *s)
{
    if (s->_parent || !s->_surf || __atomic_load_n(&s->_nviews, __ATOMIC_ACQUIRE) ||
        !nvmtl_scanout_has((uint32_t)IOSurfaceGetID(s->_surf))) return NO;
    const size_t row = IOSurfaceGetBytesPerRow(s->_surf);
    const uint32_t w = s->_i.w, h = s->_i.h;
    nvk_image t4;
    if (row % 128 || row * (((size_t)h + 31) & ~(size_t)31) > s->_hostBuf.size ||
        (nvmtl_vk_image_create_buffer_alias_mod(w, h, s->_i.fmt, s->_i.bpp, 0, s->_i.storage ? 1 : 0, 1, &s->_hostBuf, 0, row, NVMTL_DRM_MOD_4_TILED, &t4)
         && nvmtl_vk_image_create_buffer_alias_mod(w, h, s->_i.fmt, s->_i.bpp, 0, 0, 1, &s->_hostBuf, 0, row, NVMTL_DRM_MOD_4_TILED, &t4))) {
        s->_zcCandidate = NO;
        syslog(LOG_ERR, "NullMoth: zero-copy surface %u %ux%u row %zu: no Tile4 image over its pages - stays hybrid",
               (unsigned)IOSurfaceGetID(s->_surf), w, h, row);
        return NO;
    }
    if (nvmtl_vk_cmd_copy_image(&cb->_c, &s->_i, 0, 0, &t4, 0, 0, w, h)) { nvmtl_vk_image_destroy(&t4); return NO; }   // the next frame tries again
    NVMTLTexture *old = [NVMTLTexture new];
    old->_i = s->_i;
    if (!cb->_resources) cb->_resources = [NVMTLResSet new];
    [(NVMTLResSet *)cb->_resources addObject:old];
    s->_i = t4; s->_tile4 = YES; s->_zcCandidate = NO; s->_stex = t4.storage != 0;
    static unsigned said; if (said++ < 32)
        syslog(LOG_ERR, "NullMoth: zero-copy surface %u %ux%u: on the panel now - its frame copied into Tile4 in its own pages, drawn there from now on",
               (unsigned)IOSurfaceGetID(s->_surf), w, h);
    return YES;
}
static void nvmtl_surface_mark_tile4(NVMTLTexture *t)
{
    CFTypeRef was = IOSurfaceCopyValue(t->_surf, CFSTR("NMXTile4"));
    if (was) { CFRelease(was); return; }
    int64_t pitch = (int64_t)IOSurfaceGetBytesPerRow(t->_surf);
    CFNumberRef v = CFNumberCreate(NULL, kCFNumberSInt64Type, &pitch);
    IOSurfaceSetValue(t->_surf, CFSTR("NMXTile4"), v); CFRelease(v);
    t->_tile4Owner = YES;
}
- (void)nvmtlSealPartWithSignal:(id)event value:(uint64_t)value restart:(BOOL)restart {
    if (!_parts) _parts = [NSMutableArray new];
    nvmtl_g79_flush(self);
    // Hybrid surfaces (NVMTLDevice.m nvmtl_surface_hybrid) were drawn in their tiled image: the part copies it to the
    // surface's own pages before it completes. One full copy per command buffer that wrote the surface.
    NSMutableSet *hybridOut = nil, *tile4Mark = nil;
    for (NVMTLTexture *s in _surfDirty) {
        if (!s->_hybrid) continue;
        if (s->_tile4) {   // v41 zero copy: drawn in place; completion only marks it published
            if (!hybridOut) hybridOut = [NSMutableSet new];
            [hybridOut addObject:s];
            continue;
        }
        if (s->_zcCandidate && _c.cb && !_c.in_rp && nvmtl_surface_promote(self, s)) {
            if (!hybridOut) hybridOut = [NSMutableSet new];
            [hybridOut addObject:s];
            if (!tile4Mark) tile4Mark = [NSMutableSet new];
            [tile4Mark addObject:s];
            continue;
        }
        if (!_c.cb || _c.in_rp || nvmtl_vk_cmd_copy_image(&_c, &s->_i, 0, 0, &s->_hostAlias, 0, 0, s->_i.w, s->_i.h)) {
            static unsigned said; if (said++ < 8)
                syslog(LOG_ERR, "NullMoth: hybrid surface %u: copy out not recorded (%s) - copied after completion",
                       (unsigned)IOSurfaceGetID(s->_surf), !_c.cb ? "no recording" : _c.in_rp ? "render pass open" : "copy refused");
            continue;
        }
        if (!hybridOut) hybridOut = [NSMutableSet new];
        [hybridOut addObject:s];
        const unsigned long long n = ++g_hybrid_out;
        if (n <= 4 || n % 4096 == 0)
            syslog(LOG_ERR, "NullMoth: hybrid surfaces: %llu GPU copies out, %llu copies in, %llu synchronous out, %llu surfaces made",
                   n, (unsigned long long)g_hybrid_in, (unsigned long long)g_hybrid_sync, (unsigned long long)g_surf_hybrid);
    }
    NVMTLSubmissionPart *part = [NVMTLSubmissionPart new];
    part->hybridOut = hybridOut;
    part->tile4Mark = tile4Mark;
    part->commands = _c;
    memset(&_c, 0, sizeof(_c));
    part->resources = [(NVMTLResSet *)_resources nvmtlTakeAll]; part->surfaces = [_surfDirty copy];
    // Another process may read an IOSurface once its writer is scheduled, and nothing orders its queue after ours.
    // v56 (upstream PR #438, mickys c77ee56): a surface written through a private image reaches its pages only when
    // -nvmtlSurfaceOut copies it after the GPU wait, while WindowServer hands ScreenCaptureKit clients their frame (and
    // CoreImage reads a rendered CVPixelBuffer) once the command buffer is scheduled, as Apple's IOSurfaceLock waits for
    // the GPU. With nvmtl-ws-early-schedule a capture client read the two-plane 420v surface before the copy-out: a share
    // that the other side never sees, a Photo Booth photo with no chroma (green). Such a command buffer now reports
    // "scheduled" once its writes are published. NVMTL_SCHEDULE_AFTER_SURFACE_WRITES=3 (default) does it for two-plane
    // surfaces only (capture and video frames, nothing else pays), =2 for every private one, =1 for every write, =0 never.
    static int after = -1; if (after < 0) {
        const char *e = getenv("NVMTL_SCHEDULE_AFTER_SURFACE_WRITES"); after = e && *e ? e[0] - '0' : 3;
        if (access("/Library/GPUBundles/nvmtl-no-surface-order", F_OK) == 0) after = 0;
        if (nvmtl_vk_windowserver_serial()) syslog(LOG_ERR, "NullMoth: surface writes before scheduled: mode %d%s", after,
                                                   after == 3 ? " (two-plane surfaces)" : after ? "" : " (off)"); }
    NVMTLTexture *drawable = _present ? (_present->_parent ?: _present) : nil;
    for (NVMTLTexture *s in part->surfaces) {
        if (nvmtl_vk_windowserver_serial() && !nvmtl_ws_early_schedule()) { _scheduleAfterPublish = YES; continue; }
        if (s == drawable || !after) continue;
        NVMTLTexture *r = s->_parent ? s->_parent : s;
        if (after == 1 || (r->_surf && (after == 3 ? IOSurfaceGetPlaneCount(r->_surf) > 1 : !r->_vramOn))) _scheduleAfterPublish = YES;
    }
    part->scratch = [_scratch copy]; part->signalEvent = event; part->value = value;
    part->encoders = _nEnc - _nEncSealed; _nEncSealed = _nEnc;
    if (_g79Sig.count) { part->signals = [_g79Sig copy]; [_g79Sig removeAllObjects]; }
    [_parts addObject:part];
    [_surfDirty removeAllObjects]; [_scratch removeAllObjects];
    // The repeated-setBytes cache points at ring chunks without owning them; the part now owns those chunks and frees
    // them when it completes, which can happen while this command buffer is still being encoded. A cache entry that
    // outlived its chunk was bound and retained again by the next identical setBytes, and the compute encoder's binding
    // table later released a freed object (mediaanalysisd under MPS convolution, endEncoding / .cxx_destruct).
    memset(_g79BRing, 0, sizeof _g79BRing); memset(_g79BLen, 0, sizeof _g79BLen);
    // Recording goes on after this seal, and the encoders' binding tables still name these resources by raw Vulkan
    // handle: a later dispatch snapshots them again without rebinding. The command buffer keeps holding them until it
    // completes, as Metal's do. WAS: only the part held them, so a texture the app had released died when that part
    // completed and the next dispatch wrote its destroyed image view (NVK abort in get_sampled_image_view_desc under
    // nvk_UpdateDescriptorSets: mediaanalysisd, Safari, wallpapers).
    if (restart) for (id o in (NVMTLResSet *)part->resources) [(NVMTLResSet *)_resources addObject:o];
    if (restart && nvmtl_vk_cmd_begin(&_queue->_q, &_c)) {
        _cbError = [NSError errorWithDomain:MTLCommandBufferErrorDomain code:MTLCommandBufferErrorOutOfMemory
            userInfo:@{NSLocalizedDescriptionKey:@"Could not allocate recording after event boundary"}];
    }
}
- (void)nvmtlRecordWait:(id)event value:(uint64_t)value {
    if (!event || _committed) return;
    if (nvmtl_g79_on(NVMTL_G79_EV)) {
        BOOL self_ = NO;
        for (NSArray *p in _g79Promised) if (p[0] == event && [p[1] unsignedLongLongValue] >= value) { self_ = YES; break; }
        BOOL held = !self_ && [event respondsToSelector:@selector(signaledValue)]
            && ((uint64_t(*)(id,SEL))objc_msgSend)(event, @selector(signaledValue)) >= value;
        if (self_ || held) {
            if (_g79C2C && nvmtl_g79_on(NVMTL_G79_WFOLD)) { _g79Owed = YES; nvmtl_g79_count(G79C_WAITFOLD); }
            else if (_c.cb) { nvmtl_vk_cmd_barrier(&_c); _g79Owed = NO; _g79C2C = NO; }
            nvmtl_g79_count(self_ ? G79C_WAITSELF : G79C_WAITHELD);
            return;
        }
        nvmtl_g79_count(G79C_WAITSPLIT);
    }
    [self nvmtlSealPartWithSignal:nil value:0 restart:YES];
    NVMTLSubmissionPart *part = [NVMTLSubmissionPart new];
    part->waitEvent = event; part->value = value; [_parts addObject:part];
}
- (void)nvmtlRecordSignal:(id)event value:(uint64_t)value {
    if (!event || _committed) return;
    if (nvmtl_g79_on(NVMTL_G79_EV)) {
        if (!_g79Sig) _g79Sig = [NSMutableArray new];
        if (!_g79Promised) _g79Promised = [NSMutableArray new];
        [_g79Sig addObject:@[event, @(value)]]; [_g79Promised addObject:@[event, @(value)]];
        nvmtl_g79_count(G79C_SIGRIDE);
        return;
    }
    [self nvmtlSealPartWithSignal:event value:value restart:YES];
}
- (void)nvmtlDispatchHandlers:(NSArray *)handlers scheduled:(BOOL)scheduled {
    if (!handlers.count) return;
    dispatch_queue_t order;
    dispatch_queue_t target;
    // the class, not the queue: apps may hold @synchronized(queue) while they wait for this command buffer
    @synchronized ([NVMTLCommandQueue class]) {
        if (!_queue->_callbackOrderQueue)
            _queue->_callbackOrderQueue = dispatch_queue_create("com.nvmtl.command-callbacks", DISPATCH_QUEUE_SERIAL);
        order = _queue->_callbackOrderQueue;
        target = _queue->_completionQueue ?: dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0);
    }
    for (NSUInteger i = 0; i < handlers.count; ++i) {
        dispatch_group_enter(_callbackGroup);
        if (scheduled) dispatch_group_enter(_scheduledGroup);
    }
    dispatch_async(order, ^{
        dispatch_sync(target, ^{
            for (MTLCommandBufferHandler handler in handlers) {
                const uint64_t callbackStart=self->_traceCommitNS ? clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) : 0;
                handler(self);
                if (callbackStart) {
                    const uint64_t elapsed=clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)-callbackStart;
                    static _Atomic unsigned callbackReports;
                    if (elapsed>=50000000ULL && atomic_fetch_add(&callbackReports,1)<16)
                        nvlog("first-submit: slow-callback0.3.12: cb=%p scheduled=%d elapsed_ms=%.3f",(__bridge void *)self,scheduled,elapsed*1e-6);
                }
                if (scheduled) dispatch_group_leave(self->_scheduledGroup);
                dispatch_group_leave(self->_callbackGroup);
            }
        });
    });
}
- (void)nvmtlMarkScheduled {
    if (_scheduleAfterPublish) return;
    [_completionCondition lock];
    if (!_wasScheduled) {
        _wasScheduled = YES; _cbstatus = MTLCommandBufferStatusScheduled;
        if (_traceCommitNS) _scheduledNS = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
        NSArray *handlers = [_scheduledHandlers copy]; [_scheduledHandlers removeAllObjects];
        [self nvmtlDispatchHandlers:handlers scheduled:YES];
        [_completionCondition broadcast];
    }
    [_completionCondition unlock];
}
- (void)nvmtlCollectDeviceTiming:(nvk_cmdbuf *)commands {
    if (!commands->timing.valid) { _gpuTimingInvalid = YES; return; }
    if (!_gpuTimingSeen) { _gpuTiming = commands->timing; _gpuTimingSeen = YES; }
    else {
        _gpuTiming.end_tick = commands->timing.end_tick;
        _gpuTiming.host_after_ns = commands->timing.host_after_ns;
    }
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
    if (nvmtl_vk_windowserver_serial()) { nvmtl_ws_timing_census(self, error ? 0 : deviceStart, error ? 0 : deviceEnd); nvmtl_vk_ipark_trim(); }
    nvmtl_surface_finish_writes(self);
    [_completionCondition lock];
    _gpuStart = deviceStart; _gpuEnd = deviceEnd;
    _legacyKernelEnd = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
    _cbError = error; _cbstatus = error ? MTLCommandBufferStatusError : MTLCommandBufferStatusCompleted;
    _executionDone = YES;
    [_completionCondition unlock];
    if (nvmtl_split_submit_on()) { @synchronized ([NVMTLCommandBuffer class]) { [_parts removeAllObjects]; } }
    else [_parts removeAllObjects];
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
- (void)nvmtlFinishCallbacks {
    [_completionCondition lock];
    NSArray *handlers = [_handlers copy]; [_handlers removeAllObjects];
    [self nvmtlDispatchHandlers:handlers scheduled:NO];
    _completionReady = YES;
    [_completionCondition broadcast]; [_completionCondition unlock];
}
static unsigned nvmtl_gsub_cap(void) {
    static int cap = -1;
    if (cap < 0) { const char *e = getenv("NVMTL_GSUB_INFLIGHT"); int v = e ? atoi(e) : 16;
        cap = v < 1 ? 1 : v > 32 ? 32 : v;
        nvlog("commit: G-SUB submit-ahead %s, at most %d parts in flight (NVMTL_GSUB_INFLIGHT=%s)",
              nvmtl_async_commit_on() && nvmtl_g79_on(NVMTL_G79_SUB) ? "ON" : "off", cap, e ? e : "unset"); }
    return (unsigned)cap;
}
static BOOL nvmtl_gsub_ahead_on(void) { return nvmtl_async_commit_on() && nvmtl_g79_on(NVMTL_G79_SUB) && nvmtl_gsub_cap(); }
static NSMapTable *nvmtl_evfold_submitted;
static _Atomic unsigned long long gEvFold, gEvFoldEmpty;
static BOOL nvmtl_evfold_on(void) {
    static int on = -1;
    if (on < 0) { const char *e = getenv("NVMTL_EVFOLD"); on = !(e && e[0] == '0');
        nvlog("commit: sub1 EVFOLD %s - an event wait whose signal is already in the channel %s (NVMTL_EVFOLD=%s)",
              on ? "ON" : "off", on ? "is ordered by the channel, no CPU hold" : "is held until the CPU reads the signal", e ? e : "unset"); }
    return on;
}
static uint64_t nvmtl_evfold_promised(id event) {
    return event ? [[nvmtl_evfold_submitted objectForKey:event] unsignedLongLongValue] : 0;
}
static void nvmtl_evfold_promise(id event, uint64_t value) {
    if (!event || !nvmtl_evfold_on()) return;
    if (!nvmtl_evfold_submitted) nvmtl_evfold_submitted = [NSMapTable weakToStrongObjectsMapTable];
    if (value > nvmtl_evfold_promised(event)) [nvmtl_evfold_submitted setObject:@(value) forKey:event];
}
static void nvmtl_evfold_promise_part(NVMTLSubmissionPart *part) {
    if (part->signalEvent) nvmtl_evfold_promise(part->signalEvent, part->value);
    for (NSArray *s in part->signals) nvmtl_evfold_promise(s[0], [s[1] unsignedLongLongValue]);
}
static void nvmtl_evfold_census(_Atomic unsigned long long *c, const char *what) {
    const unsigned long long k = atomic_fetch_add(c, 1) + 1;
    if (!(k & (k - 1))) nvlog("commit: sub1 EVFOLD %llu %s", k, what);
}
static void nvmtl_gsub_census(void) {
    const unsigned long long k = atomic_load(&gsub_ahead);
    if (k & (k - 1)) return;
    uint64_t s[9]; nvmtl_vk_gsub_nvk_stats(s, 9);
    nvlog("commit: G-SUB %llu parts submitted ahead, peak %llu in flight | NVK %s submits %llu acquires %llu cpuwaits %llu slotwaits %llu fifowaits %llu deferred %llu reaped %llu waits %llu",
          k, (unsigned long long)atomic_load(&gsub_peak), s[0] == ~0ull ? "G-SUB ABSENT" : s[0] ? "async" : "SYNC (NVRM_ASYNC=0)",
          (unsigned long long)s[1], (unsigned long long)s[2], (unsigned long long)s[3], (unsigned long long)s[4],
          (unsigned long long)s[5], (unsigned long long)s[6], (unsigned long long)s[7], (unsigned long long)s[8]);
}
// A texture over a copy-backed buffer must refresh the same bytes as a direct
// buffer binding. Keep direct managed-buffer writeback and copy each backing once.
static NSArray<NVMTLBuffer *> *nvmtl_submission_copies(NSSet *resources, BOOL writtenOnly) {
    NSMutableArray<NVMTLBuffer *> *copies = nil;
    for (id resource in resources) {
        NVMTLBuffer *buffer = nil;
        if ([resource isKindOfClass:[NVMTLBuffer class]]) buffer = resource;
        else if ([resource isKindOfClass:[NVMTLTexture class]]) {
            NVMTLTexture *texture = resource;
            if (writtenOnly && texture->_usage != MTLTextureUsageUnknown &&
                !(texture->_usage & (MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget))) continue;
            buffer = texture->_backBuf ?: (texture->_parent ? texture->_parent->_backBuf : nil);
        }
        if (!buffer || (!buffer->_hostPtr && !buffer->_shadow.map)) continue;
        if (!copies) copies = [NSMutableArray new];
        if (![copies containsObject:buffer]) [copies addObject:buffer];
    }
    return copies;
}
- (BOOL)nvmtlSubmitAhead {
    if (nvmtl_vk_windowserver_serial() && !nvmtl_ws_pipeline()) return NO;
    if (_executionDone || _cbError || !_committed || _workerOwns) return NO;
    if (_nextSubmit < _nextPart) _nextSubmit = _nextPart;
    while (_nextSubmit < _parts.count) {
        if (atomic_load(&gsub_inflight) >= nvmtl_gsub_cap()) return NO;
        NVMTLSubmissionPart *part = _parts[_nextSubmit];
        if (![part isKindOfClass:[NVMTLSubmissionPart class]]) return NO;
        if (part->waitEvent) {
            if (!nvmtl_evfold_on() || nvmtl_evfold_promised(part->waitEvent) < part->value) return NO;
            part->waitFolded = YES; _nextSubmit++; atomic_fetch_add(&gAheadWork, 1); nvmtl_evfold_census(&gEvFold, "event waits ordered by the channel (no CPU hold)");
            continue;
        }
        if (!part->commands.cb) return NO;
        if (!part->encoders && !part->resources.count && !part->surfaces.count && !part->scratch.count && nvmtl_skip_empty_on()) {
            if (!nvmtl_evfold_on() || _nextSubmit + 1 >= _parts.count) return NO;
            [self nvmtlMarkScheduled];
        if (!_legacyKernelStart) _legacyKernelStart = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
            nvmtl_vk_cmd_abandon(&part->commands);
            part->aheadEmpty = YES; _nextSubmit++; atomic_fetch_add(&gAheadWork, 1);
            nvmtl_evfold_promise_part(part);
            nvmtl_evfold_census(&gEvFoldEmpty, "empty split parts retired by the ahead pass");
            continue;
        }
        {
            static int hold = -1;
            if (hold < 0) { const char *e = getenv("NVMTL_GSUB_HOSTPTR_LIFT"); hold = (e && *e && *e != '0') ? 0 : 1; }
            if (hold) {
                for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, NO))
                    if (buffer->_hostPtr) { part->aheadDeclined = YES; return NO; }
            }
        }
        nvmtl_inflight *f = nvmtl_vk_inflight_new();
        if (!f) { part->aheadDeclined = YES; return NO; }
        for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, NO)) nvmtl_buffer_sync_in(buffer);
        [self nvmtlMarkScheduled];
        if (!_legacyKernelStart) _legacyKernelStart = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1e9;
        // An execbuffer takes 3-6 ms. Held across it, this lock stopped WindowServer's main thread for 18% of a drag, in
        // commit and in encoder creation. Only the pump's serial queue submits, so order does not depend on the lock; the
        // ahead pass (its only caller, at depth one) walks copies of what a commit can change meanwhile.
        const BOOL unlock = nvmtl_vk_windowserver_serial() && nvmtl_ws_submit_unlocked();
        id lockObject = [NVMTLCommandBuffer class];
        part->submitting = YES;
        if (unlock) objc_sync_exit(lockObject);
        const int r = nvmtl_vk_submit_begin(&part->commands, f);
        if (unlock) objc_sync_enter(lockObject);
        part->submitting = NO;
        _nextSubmit++; atomic_fetch_add(&gAheadWork, 1);
        if (r) {
            nvmtl_vk_inflight_free(f);
            part->aheadFailed = r;
            return NO;
        }
        part->inflight = f;
        nvmtl_evfold_promise_part(part);
        const unsigned long long n = atomic_fetch_add(&gsub_inflight, 1) + 1;
        if (n > atomic_load(&gsub_peak)) atomic_store(&gsub_peak, n);
        atomic_fetch_add(&gsub_ahead, 1);
        nvmtl_gsub_census();
    }
    return YES;
}
/* What WindowServer hands the pump: command buffers per present, and the parts (each its own execbuffer) they split
   into at event waits and signals. Logged every 2048 command buffers. */
static _Atomic unsigned long long gWsCb, gWsParts, gWsSubmits, gWsWaits, gWsSignals, gWsPresents;
static _Atomic unsigned long long gWsCensusT0;
void nvmtl_ws_note_present(void) { atomic_fetch_add(&gWsPresents, 1); }
static void nvmtl_ws_submission_census(NVMTLCommandBuffer *cb) {
    unsigned long long submits = 0, waits = 0, signals = 0;
    for (NVMTLSubmissionPart *p in cb->_parts) {
        if (![p isKindOfClass:[NVMTLSubmissionPart class]]) continue;
        if (p->commands.cb) submits++;
        if (p->waitEvent) waits++;
        if (p->signalEvent) signals++;
        signals += p->signals.count;
    }
    atomic_fetch_add(&gWsParts, cb->_parts.count); atomic_fetch_add(&gWsSubmits, submits);
    atomic_fetch_add(&gWsWaits, waits); atomic_fetch_add(&gWsSignals, signals);
    const unsigned long long n = atomic_fetch_add(&gWsCb, 1) + 1;
    const unsigned long long now = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
    unsigned long long t0 = atomic_load(&gWsCensusT0);
    if (!t0) { atomic_store(&gWsCensusT0, now); return; }
    if (n % 2048) return;
    const unsigned long long cbs = 2048, parts = atomic_exchange(&gWsParts, 0), subs = atomic_exchange(&gWsSubmits, 0);
    const unsigned long long w = atomic_exchange(&gWsWaits, 0), s = atomic_exchange(&gWsSignals, 0);
    const unsigned long long presents = atomic_exchange(&gWsPresents, 0);
    atomic_store(&gWsCensusT0, now);
    const double sec = (now - t0) * 1e-9;
    syslog(LOG_ERR, "NullMoth: submission census: %llu command buffers in %.1f s (%.0f/s), %llu presents (%.0f/s, %.2f buffers each); "
          "per buffer %.2f parts, %.2f execbuffers, %.2f event waits, %.2f signals",
          cbs, sec, cbs / sec, presents, presents / sec, presents ? (double)cbs / presents : 0.0,
          (double)parts / cbs, (double)subs / cbs, (double)w / cbs, (double)s / cbs);
}
/* WindowServer's command buffers over the whole session (the slow-part trace stops after 32): time on the GPU, and
   from commit to completion, as histograms. Logged every 512. */
static const double kWsGpuMs[] = { 2, 4, 8, 16, 33 }, kWsLatMs[] = { 8, 16, 33, 66, 133 };
static unsigned long long gWsGpu[6], gWsLat[6], gWsTimed, gWsUntimed, gWsWindowT0;
static double gWsGpuSum, gWsLatSum, gWsGpuMax, gWsLatMax, gWsSchedSum, gWsSchedMax;
/* v40 frame path: commit to done split at scheduled, vkQueueSubmit's start and return, the GPU's first and last timestamp
   and the worker seeing the fence: sched, pre-submit, execbuffer, GPU queue, GPU, signal, after */
enum { WSP_SCHED, WSP_PRE, WSP_EXEC, WSP_QUEUE, WSP_GPU, WSP_SIGNAL, WSP_AFTER, WSP_N };
static double gWsPathSum[WSP_N], gWsPathMax[WSP_N];
static unsigned long long gWsPathN;
static void nvmtl_ws_timing_census(NVMTLCommandBuffer *cb, double deviceStart, double deviceEnd) {
    if (!cb->_traceCommitNS) return;
    const double gpuSeconds = deviceEnd > deviceStart ? deviceEnd - deviceStart : 0;
    const double lat = (clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) - cb->_traceCommitNS) * 1e-6, gpu = gpuSeconds * 1e3;
    static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    pthread_mutex_lock(&lock);
    do {
        const uint64_t nowNS = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
        if (!gWsWindowT0) gWsWindowT0 = nowNS;
        if (cb->_scheduledNS > cb->_traceCommitNS) {
            const double sched = (cb->_scheduledNS - cb->_traceCommitNS) * 1e-6;
            gWsSchedSum += sched; if (sched > gWsSchedMax) gWsSchedMax = sched;
        }
        const nvmtl_gpu_interval *ti = &cb->_gpuTiming;
        if (deviceStart > 0 && cb->_scheduledNS > cb->_traceCommitNS && ti->host_locked_ns && ti->host_submitted_ns && ti->host_after_ns) {
            // the GPU interval and the submit stamps are CLOCK_UPTIME_RAW, the commit and schedule stamps CLOCK_MONOTONIC_RAW
            const double off = (double)nowNS - (double)clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
            const double commit = cb->_traceCommitNS - off, sched = cb->_scheduledNS - off, now = nowNS - off;
            const double t[WSP_N + 1] = { commit, sched, (double)ti->host_locked_ns, (double)ti->host_submitted_ns,
                                          deviceStart * 1e9, deviceEnd * 1e9, (double)ti->host_after_ns, now };
            for (int k = 0; k < WSP_N; k++) {
                const double ms = (t[k + 1] - t[k]) * 1e-6;
                gWsPathSum[k] += ms; if (ms > gWsPathMax[k]) gWsPathMax[k] = ms;
            }
            gWsPathN++;
        }
        unsigned k = 0; while (k < 5 && lat >= kWsLatMs[k]) k++;
        gWsLat[k]++; gWsLatSum += lat; if (lat > gWsLatMax) gWsLatMax = lat;
        if (gpu > 0 && gpu < 10000) {
            k = 0; while (k < 5 && gpu >= kWsGpuMs[k]) k++;
            gWsGpu[k]++; gWsGpuSum += gpu; if (gpu > gWsGpuMax) gWsGpuMax = gpu; gWsTimed++;
        } else gWsUntimed++;
        if ((gWsTimed + gWsUntimed) % 512) break;
        syslog(LOG_ERR, "NullMoth: frame timing: GPU ms <2 %llu, 2-4 %llu, 4-8 %llu, 8-16 %llu, 16-33 %llu, 33+ %llu "
               "(avg %.2f max %.1f, %llu untimed) | commit to done ms <8 %llu, 8-16 %llu, 16-33 %llu, 33-66 %llu, "
               "66-133 %llu, 133+ %llu (avg %.1f max %.1f) | commit to scheduled ms avg %.2f max %.1f | %.1f s%s",
               gWsGpu[0], gWsGpu[1], gWsGpu[2], gWsGpu[3], gWsGpu[4], gWsGpu[5], gWsTimed ? gWsGpuSum / gWsTimed : 0.0,
               gWsGpuMax, gWsUntimed, gWsLat[0], gWsLat[1], gWsLat[2], gWsLat[3], gWsLat[4], gWsLat[5],
               gWsLatSum / 512, gWsLatMax, gWsSchedSum / 512, gWsSchedMax, (nowNS - gWsWindowT0) * 1e-9,
               nvmtl_split_submit_on() ? ", split submit" : "");
        if (gWsPathN) {
            const double n = (double)gWsPathN;
            syslog(LOG_ERR, "NullMoth: frame timing path ms avg/max over %llu: sched %.2f/%.1f, pre-submit %.2f/%.1f, execbuffer %.2f/%.1f, "
                   "GPU queue %.2f/%.1f, GPU %.2f/%.1f, signal %.2f/%.1f, after %.2f/%.1f", gWsPathN,
                   gWsPathSum[WSP_SCHED] / n, gWsPathMax[WSP_SCHED], gWsPathSum[WSP_PRE] / n, gWsPathMax[WSP_PRE],
                   gWsPathSum[WSP_EXEC] / n, gWsPathMax[WSP_EXEC], gWsPathSum[WSP_QUEUE] / n, gWsPathMax[WSP_QUEUE],
                   gWsPathSum[WSP_GPU] / n, gWsPathMax[WSP_GPU], gWsPathSum[WSP_SIGNAL] / n, gWsPathMax[WSP_SIGNAL],
                   gWsPathSum[WSP_AFTER] / n, gWsPathMax[WSP_AFTER]);
        }
        memset(gWsPathSum, 0, sizeof gWsPathSum); memset(gWsPathMax, 0, sizeof gWsPathMax); gWsPathN = 0;
        memset(gWsGpu, 0, sizeof gWsGpu); memset(gWsLat, 0, sizeof gWsLat);
        gWsTimed = gWsUntimed = 0; gWsGpuSum = gWsLatSum = gWsGpuMax = gWsLatMax = gWsSchedSum = gWsSchedMax = 0;
        gWsWindowT0 = nowNS;
    } while (0);
    pthread_mutex_unlock(&lock);
}
static void nvmtl_gsub_ahead_pass1(void);
static void nvmtl_gsub_ahead_pass(void) {
    for (int round = 0; round < 64; round++) {
        const unsigned long long before = atomic_load(&gEvFold);
        nvmtl_gsub_ahead_pass1();
        if (atomic_load(&gEvFold) == before) break;
    }
}
static void nvmtl_gsub_ahead_pass1(void) {
    NSMutableSet *queues = [NSMutableSet new];
    for (NVMTLCommandBuffer *cb in [nvmtl_pending_buffers copy]) {
        id q = cb->_queue;
        if (!q || [queues containsObject:q]) continue;
        [queues addObject:q];
        for (NVMTLQueueReservation *r in [cb->_queue->_reservations copy]) {
            NVMTLCommandBuffer *b = r->buffer;
            if (!b) continue;
            if (![b nvmtlSubmitAhead]) break;
        }
    }
}
- (BOOL)nvmtlAdvancePart {
    if (_executionDone) return NO;
    if (_cbError) { [self nvmtlFinishExecution:_cbError]; return YES; }
    if (_nextPart >= _parts.count) { [self nvmtlFinishExecution:nil]; return YES; }
    NVMTLSubmissionPart *part = _parts[_nextPart];
    if (nvmtl_split_submit_on()) {
        // The submit queue owns execbuffers: a part it is submitting, or has yet to reach, is not submitted here as well
        // (it pumps the worker when it has). Parts it never takes (host pointers, empty ones) make the worker submit the
        // rest of this command buffer itself, as before.
        @synchronized ([NVMTLCommandBuffer class]) {
            if (part->submitting) return NO;
            if (!part->inflight && !part->aheadFailed && part->commands.cb && !_workerOwns) {
                const BOOL empty = !part->encoders && !part->resources.count && !part->surfaces.count && !part->scratch.count && nvmtl_skip_empty_on();
                if (!empty && !part->aheadDeclined) { nvmtl_kick_submit(); return NO; }
                _workerOwns = YES;
            }
        }
    }
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
        const uint64_t phaseBegin=_traceCommitNS ? clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) : 0;
        int result;
        uint64_t phaseImported=phaseBegin;
        if (part->inflight) result = nvmtl_gsub_finish(part);
        else if (part->aheadFailed) result = part->aheadFailed;
        else {
            for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, NO)) nvmtl_buffer_sync_in(buffer);
            if(phaseBegin)phaseImported=clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
            result = nvmtl_vk_submit_wait(&part->commands);
        }
        if (result == -2) {
            if (!nvmtl_quarantined_parts) nvmtl_quarantined_parts = [NSMutableArray new];
            [nvmtl_quarantined_parts addObject:part];
        }
        if (result == 0) [self nvmtlCollectDeviceTiming:&part->commands];
        const uint64_t phaseWait=phaseBegin ? clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) : 0;
        uint64_t phaseSurfaces=phaseWait;
        BOOL published = result == 0;
        if (published) {
            for (NVMTLTexture *texture in part->surfaces) {
                if ([part->tile4Mark containsObject:texture]) nvmtl_surface_mark_tile4(texture);
                if ([part->hybridOut containsObject:texture]) [texture nvmtlHybridCopied];
                else if (![texture nvmtlSurfaceOut]) { published = NO; continue; }
                nvmtl_mark_published(self, texture->_parent ? texture->_parent : texture);
            }
            if(phaseBegin)phaseSurfaces=clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
            for (NVMTLBuffer *buffer in nvmtl_submission_copies(part->resources, YES)) nvmtl_buffer_sync_out(buffer);
        }
        if (phaseBegin) {
            const uint64_t now=clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
            static _Atomic unsigned slowReports;
            if (now-_traceCommitNS>=50000000ULL && atomic_fetch_add(&slowReports,1)<32)
                nvlog("first-submit: slow-part0.3.19: cb=%p part=%lu/%lu elapsed_before_part_ms=%.3f gpu_wait_ms=%.3f publish_ms=%.3f surfaces=%lu result=%d published=%d import_ms=%.3f surface_out_ms=%.3f buffer_out_ms=%.3f",
                    (__bridge void *)self,(unsigned long)_nextPart,(unsigned long)_parts.count,
                    (phaseBegin-_traceCommitNS)*1e-6,(phaseWait-phaseBegin)*1e-6,(now-phaseWait)*1e-6,
                    (unsigned long)part->surfaces.count,result,published,
                    (phaseImported-phaseBegin)*1e-6,(phaseSurfaces-phaseWait)*1e-6,(now-phaseSurfaces)*1e-6);
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
    if (nvmtl_split_submit_on()) { @synchronized ([NVMTLCommandBuffer class]) { _parts[_nextPart++] = [NSNull null]; } }
    else _parts[_nextPart++] = [NSNull null];
    if (_nextPart == _parts.count) [self nvmtlFinishExecution:nil];
    return YES;
}
- (void)nvmtlSubmitWithEvents {
    @synchronized ([NVMTLCommandBuffer class]) {
        if (_committed) return;
        [self nvmtlReserveQueue];
        _committed = YES;
        if (!__atomic_load_n(&_rep, __ATOMIC_ACQUIRE)) __atomic_store_n(&_rep, nvmtl_ep_enter(), __ATOMIC_RELEASE);
        [_completionCondition lock]; _cbstatus = MTLCommandBufferStatusCommitted; [_completionCondition unlock];
        [self nvmtlSealPartWithSignal:nil value:0 restart:NO];
        if (nvmtl_vk_windowserver_serial()) nvmtl_ws_submission_census(self);
        nvmtl_surface_register_writes(self);
        if (!nvmtl_pending_buffers) nvmtl_pending_buffers = [NSMutableArray new];
        [nvmtl_pending_buffers addObject:self];
        nvmtl_pump_buffers();
    }
}
@end

static void nvmtl_pump_buffers_sync(void) {
    @synchronized ([NVMTLCommandBuffer class]) {
        if (nvmtl_pumping) return;
        nvmtl_pumping = YES;
        BOOL progress;
        do {
            progress = NO;
            for (NVMTLCommandBuffer *cb in [nvmtl_pending_buffers copy]) {
                NSMutableArray *reservations = cb->_queue->_reservations;
                while (reservations.count && !((NVMTLQueueReservation *)reservations.firstObject)->buffer)
                    [reservations removeObjectAtIndex:0];
                if (reservations.firstObject != cb->_reservation) continue;
                if ([cb nvmtlAdvancePart]) progress = YES;
                if (cb->_executionDone) {
                    [cb nvmtlReleaseReservation];
                    [nvmtl_pending_buffers removeObjectIdenticalTo:cb];
                    [cb nvmtlFinishCallbacks];
                }
            }
        } while (progress);
        nvmtl_pumping = NO;
    }
}

static uint64_t nvmtl_pump_generation;
/*
 * v38 split submit (/Library/GPUBundles/nvmtl-ws-split-submit, WindowServer with the pipeline). One worker ran the
 * ahead pass (the execbuffers) and then blocked in the oldest command buffer's fence wait: a frame committed meanwhile
 * was not submitted until the previous one had finished on the GPU, and WindowServer's main thread waited for it in
 * waitUntilScheduled. In a Launchpad animation that kept ~30 frames/s with 9 ms of GPU work each, the GPU busy 20-40%
 * (v37 frame timing: 24 ms commit to done). Here every commit kicks a pass on its own serial queue, the only thread
 * that submits ahead; the worker waits for completions and leaves unsubmitted parts to it.
 */
static BOOL nvmtl_split_submit_on(void) {
    static int on = -1;
    if (on < 0) on = nvmtl_vk_windowserver_serial() && nvmtl_gsub_ahead_on() && nvmtl_ws_split_submit();
    return on;
}
static void nvmtl_pump_worker(void);
static _Atomic int gSubmitKicked;
static _Atomic unsigned long long gSplitPasses, gSplitIdle;
static void nvmtl_kick_submit(void) {
    static dispatch_once_t once; static dispatch_queue_t q;
    dispatch_once(&once, ^{
        q = dispatch_queue_create("nvmtl.submit", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0));
        syslog(LOG_ERR, "NullMoth: split submit ON - execbuffers on their own queue, the execution worker only waits for completions");
    });
    if (atomic_exchange(&gSubmitKicked, 1)) return;   // a queued pass sees this commit too
    dispatch_async(q, ^{ @autoreleasepool {
        atomic_store(&gSubmitKicked, 0);
        const unsigned long long before = atomic_load(&gAheadWork);
        @synchronized ([NVMTLCommandBuffer class]) { nvmtl_gsub_ahead_pass(); }
        const BOOL work = atomic_load(&gAheadWork) != before;
        const unsigned long long n = atomic_fetch_add(&gSplitPasses, 1) + 1;
        if (!work) atomic_fetch_add(&gSplitIdle, 1);
        if (!(n & (n - 1)) && n >= 64)
            syslog(LOG_ERR, "NullMoth: split submit: %llu passes, %llu with nothing to submit, %llu parts submitted ahead, peak %llu in flight",
                   n, (unsigned long long)atomic_load(&gSplitIdle), (unsigned long long)atomic_load(&gsub_ahead),
                   (unsigned long long)atomic_load(&gsub_peak));
        if (work) nvmtl_pump_worker();   // the worker waits for what was submitted
    } });
}
static void nvmtl_pump_buffers(void) {
    if (nvmtl_split_submit_on()) nvmtl_kick_submit();
    nvmtl_pump_worker();
}
static void nvmtl_pump_worker(void) {
    static dispatch_once_t once; static dispatch_queue_t worker;
    const BOOL async = nvmtl_async_commit_on();
    if (async) dispatch_once(&once, ^{ worker = dispatch_queue_create("nvmtl.execution", DISPATCH_QUEUE_SERIAL); });
    if (!async) { nvmtl_vk_clock_refresh(); nvmtl_pump_buffers_sync(); return; }
    @synchronized ([NVMTLCommandBuffer class]) {
        if (!nvmtl_pending_buffers.count) return;
        ++nvmtl_pump_generation;
        if (nvmtl_pumping) return;
        nvmtl_pumping = YES;
        dispatch_async(worker, ^{
            for (;;) { @autoreleasepool {
                nvmtl_vk_clock_refresh();
                NSArray *batch; uint64_t generation;
                const BOOL split = nvmtl_split_submit_on();
                if (split) nvmtl_kick_submit();   // completions free in-flight capacity; the submit queue owns the ahead pass
                @synchronized ([NVMTLCommandBuffer class]) {
                    if (!split && nvmtl_gsub_ahead_on()) nvmtl_gsub_ahead_pass();
                    batch = [nvmtl_pending_buffers copy]; generation = nvmtl_pump_generation;
                }
                BOOL progress = NO;
                for (NVMTLCommandBuffer *cb in batch) {
                    BOOL eligible;
                    @synchronized ([NVMTLCommandBuffer class]) {
                        NSMutableArray *reservations = cb->_queue->_reservations;
                        while (reservations.count && !((NVMTLQueueReservation *)reservations.firstObject)->buffer)
                            [reservations removeObjectAtIndex:0];
                        eligible = reservations.firstObject == cb->_reservation;
                    }
                    if (!eligible) continue;
                    if ([cb nvmtlAdvancePart]) progress = YES;
                    @synchronized ([NVMTLCommandBuffer class]) {
                        if (cb->_executionDone) {
                            [cb nvmtlReleaseReservation];
                            [nvmtl_pending_buffers removeObjectIdenticalTo:cb];
                            [cb nvmtlFinishCallbacks];
                        }
                    }
                }
                @synchronized ([NVMTLCommandBuffer class]) {
                    if (!progress && generation == nvmtl_pump_generation) {
                        nvmtl_pumping = NO; return;
                    }
                }
            } }
        });
    }
}

static uint64_t nvmtl_event_read(NSCondition *condition, uint64_t *storage) {
    [condition lock]; uint64_t value = *storage; [condition unlock]; return value;
}
static void nvmtl_event_signal(id event, NSCondition *condition, uint64_t *storage,
                              NSMutableArray *notifications, uint64_t value) {
    NSMutableArray *ready = [NSMutableArray new];
    [condition lock];
    if (value > *storage) *storage = value;
    value = *storage;
    for (NSArray *notification in notifications)
        if ([notification[1] unsignedLongLongValue] <= value) [ready addObject:notification];
    [notifications removeObjectsInArray:ready];
    [condition broadcast]; [condition unlock];
    for (NSArray *notification in ready) {
        MTLSharedEventListener *listener = notification[0];
        MTLSharedEventNotificationBlock block = notification[2];
        dispatch_async(listener.dispatchQueue, ^{ block(event, value); });
    }
    nvmtl_pump_buffers();
}
static void nvmtl_event_notify(id event, NSCondition *condition, uint64_t *storage,
                              NSMutableArray *notifications, MTLSharedEventListener *listener,
                              uint64_t wanted, MTLSharedEventNotificationBlock block) {
    if (!listener || !block) return;
    [condition lock]; uint64_t value = *storage;
    if (value < wanted) [notifications addObject:@[listener, @(wanted), [block copy]]];
    [condition unlock];
    if (value >= wanted) dispatch_async(listener.dispatchQueue, ^{ block(event, value); });
}
static BOOL nvmtl_event_wait(NSCondition *condition, uint64_t *storage, uint64_t wanted, uint64_t milliseconds) {
    NSDate *deadline = milliseconds == UINT64_MAX ? nil : [NSDate dateWithTimeIntervalSinceNow:(double)milliseconds / 1000.0];
    [condition lock];
    while (*storage < wanted) {
        if (!milliseconds) break;
        if (deadline) { if (![condition waitUntilDate:deadline]) break; }
        else [condition wait];
    }
    BOOL done = *storage >= wanted; [condition unlock]; return done;
}
