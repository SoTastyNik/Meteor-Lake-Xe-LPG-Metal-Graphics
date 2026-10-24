/* Local diagnostic: copy a referenced active request's pinned CPU ring into a
 * fixed boot-lifetime buffer. No live MMIO, allocation, waits or retained
 * pointers. Print only on hang, not while submitting under the scheduler lock.
 * These CPU snapshots are not simultaneous GPU/CPU state or batch contents.
 */
#ifndef NMX_REQUEST_CAPTURE_H
#define NMX_REQUEST_CAPTURE_H
#ifdef NMXKPI
struct nmx_request_ring_snapshot {
    unsigned ready;
    u64 context, seqno;
    u32 guc, head, infix, postfix, tail, wa_tail, size, span, count, start;
    u32 words[132];
};
static int nmx_snapshot_request_ring(struct i915_request *rq,
                                    struct nmx_request_ring_snapshot *out)
{
    struct intel_ring *ring;
    u32 i, mask;
    const u32 *words;
    if (!rq || INTEL_DEVID(rq->i915) != 0x7d55 ||
        rq->engine->class != RENDER_CLASS || rq->fence.seqno > 32 ||
        !i915_request_is_active(rq))
        return 0;
    ring = rq->ring;
    if (!ring || !ring->vaddr || atomic_read(&ring->pin_count) <= 0 ||
        ring->size < 64 || ring->size > 64*1024*1024 ||
        (ring->size & (ring->size-1)) ||
        rq->head >= ring->size || rq->wa_tail >= ring->size ||
        ((rq->head | rq->wa_tail) & 3))
        return 0;
    memset(out,0,sizeof(*out));
    mask = ring->size-1;
    out->context=rq->fence.context; out->seqno=rq->fence.seqno;
    out->guc=rq->context->guc_id.id;
    out->head=rq->head; out->infix=rq->infix; out->postfix=rq->postfix;
    out->tail=rq->tail; out->wa_tail=rq->wa_tail; out->size=ring->size;
    out->span=((rq->wa_tail-rq->head)&mask)/4;
    out->count=(out->span>128?128:out->span)+4;
    if(out->count>ring->size/4)out->count=ring->size/4;
    out->start=(rq->head-16)&mask;
    words=(const u32 *)ring->vaddr;
    for(i=0;i<out->count;i++)
        out->words[i]=READ_ONCE(words[((out->start+i*4)&mask)/4]);
    return 1;
}
static void nmx_print_request_ring(const struct nmx_request_ring_snapshot *s,
                                  const char *phase)
{
    u32 i;
    pr_err("NMX-i915-ring: phase=%s context=%llu seqno=%llu guc=%u head=%x infix=%x postfix=%x tail=%x wa-tail=%x size=%x span-dw=%u captured-dw=%u truncated=%u\n",
        phase,(unsigned long long)s->context,(unsigned long long)s->seqno,
        s->guc,s->head,s->infix,s->postfix,s->tail,s->wa_tail,
        s->size,s->span,s->count,s->span>128);
    for(i=0;i<s->count;i++)
        pr_err("NMX-i915-ring-word: phase=%s context=%llu seqno=%llu offset=%x value=%08x\n",
            phase,(unsigned long long)s->context,(unsigned long long)s->seqno,
            (s->start+i*4)&(s->size-1),s->words[i]);
}
void nmx_capture_request_ring(struct i915_request *rq);
void nmx_dump_saved_request_ring(struct i915_request *rq);
#ifdef NMX_REQUEST_CAPTURE_IMPLEMENTATION
static atomic_t nmx_ring_snapshot_count=ATOMIC_INIT(0);
static struct nmx_request_ring_snapshot nmx_ring_snapshots[96];
void nmx_capture_request_ring(struct i915_request *rq)
{
    struct nmx_request_ring_snapshot snapshot;
    int slot;
    if(atomic_read(&nmx_ring_snapshot_count)>=96 ||
       !nmx_snapshot_request_ring(rq,&snapshot))return;
    slot=atomic_inc_return(&nmx_ring_snapshot_count)-1;
    if(slot<0 || slot>=96)return;
    nmx_ring_snapshots[slot]=snapshot;
    smp_store_release(&nmx_ring_snapshots[slot].ready,1);
}
void nmx_dump_saved_request_ring(struct i915_request *rq)
{
    unsigned i,found=0;
    if(!rq)return;
    for(i=0;i<96;i++) {
        const struct nmx_request_ring_snapshot *s=&nmx_ring_snapshots[i];
        /* Slots are published once and never reused: readers need no lock. */
        if(!smp_load_acquire(&s->ready))continue;
        if(s->context==rq->fence.context && s->seqno<=rq->fence.seqno &&
           rq->fence.seqno-s->seqno<=4) {
            nmx_print_request_ring(s,"before-tail");found++;
        }
    }
    if(!found)pr_err("NMX-i915-ring: no saved request within bounded boot capture\n");
}
#endif
static void nmx_log_request_ring(struct i915_request *rq, const char *phase)
{
    struct nmx_request_ring_snapshot snapshot;
    if(nmx_snapshot_request_ring(rq,&snapshot))nmx_print_request_ring(&snapshot,phase);
}
#endif
#endif
