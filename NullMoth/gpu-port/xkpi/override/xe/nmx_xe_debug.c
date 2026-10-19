// SPDX-License-Identifier: MIT
/*
 * The xe half of debug.nmxgpu_dump (xnu/nmx_diag.cpp): prints what Linux would show in debugfs - GuC CT state, every
 * exec queue with its scheduler entity (queued jobs, the fence it waits on), the GuC's own queue print, each engine's
 * pending hardware fences and the memory-based interrupt page - to the kernel log, on demand.
 */
#include <linux/xarray.h>
#include <drm/drm_print.h>
#include <drm/gpu_scheduler.h>
#include <drm/spsc_queue.h>

#include "xe_device.h"
#include "xe_exec_queue_types.h"
#include "xe_gt.h"
#include "xe_guc_ct.h"
#include "xe_guc_exec_queue_types.h"
#include "xe_guc_submit.h"
#include "xe_hw_engine_types.h"
#include "xe_hw_fence_types.h"
#include "xe_lrc.h"
#include "nmx_xnu.h"

void nmx_xe_debug_register(struct xe_device *xe);

static struct xe_device *nmx_xe;

/* drm_info_printer goes through dev_printk's "%pV", which LinuxKPI's printk does not expand: format here instead */
static void dump_printfn(struct drm_printer *p, struct va_format *vaf)
{
	char buf[512];
	va_list ap;

	va_copy(ap, *vaf->va);
	vsnprintf(buf, sizeof(buf), vaf->fmt, ap);
	va_end(ap);
	printf("xe dump: %s", buf);
}

static void dump_puts(struct drm_printer *p, const char *str)
{
	printf("xe dump: %s", str);
}

static void dump_fence(struct drm_printer *p, const char *what, struct dma_fence *f)
{
	if (f == NULL) {
		drm_printf(p, "    %s: none\n", what);
		return;
	}
	drm_printf(p, "    %s: %s/%s seqno %llu flags 0x%lx signaled %d error %d\n", what,
		   f->ops->get_driver_name(f), f->ops->get_timeline_name(f), (unsigned long long)f->seqno,
		   f->flags, dma_fence_is_signaled(f), f->error);
}

static void dump_queue(struct drm_printer *p, struct xe_exec_queue *q)
{
	struct drm_gpu_scheduler *s = &q->guc->sched.base;
	struct drm_sched_entity *e = q->entity;
	struct drm_sched_job *j;
	int pending = 0;
	struct xe_lrc *lrc = q->lrc[0];

	list_for_each_entry(j, &s->pending_list, list)
		pending++;
	drm_printf(p, "  queue guc_id %u class %d flags 0x%lx state 0x%x | sched ready %d pause_submit %d credits %d/%u pending %d\n",
		   q->guc->id, q->class, (unsigned long)q->flags, atomic_read(&q->guc->state), s->ready, s->pause_submit,
		   atomic_read(&s->credit_count), s->credit_limit, pending);
	drm_printf(p, "    entity: queued %d stopped %d | lrc seqno %d start %d head %u tail %u\n",
		   spsc_queue_count(&e->job_queue), e->stopped, xe_lrc_seqno(lrc), xe_lrc_start_seqno(lrc),
		   xe_lrc_ring_head(lrc), lrc->ring.tail);
	dump_fence(p, "entity waits on", e->dependency);
	dump_fence(p, "last fence", q->last_fence);
}

static void nmx_xe_dump(void)
{
	struct xe_device *xe = nmx_xe;
	struct drm_printer p;
	struct xe_gt *gt;
	struct xe_tile *tile;
	u8 id;

	if (xe == NULL)
		return;
	p = (struct drm_printer){ .printfn = dump_printfn, .puts = dump_puts };
	for_each_tile(tile, xe, id) {
		if (tile->memirq.bo != NULL) {
			const u8 *src = tile->memirq.source.vaddr;
			char buf[256];
			int k = 0;

			for (int i = 0; i < 64 && k < 230; i++)
				if (src[i])
					k += snprintf(buf + k, sizeof(buf) - k, " %d=%02x", i, src[i]);
			buf[k] = 0;
			drm_printf(&p, "tile %u memirq source:%s\n", id, k ? buf : " all zero");
		}
	}
	for_each_gt(gt, xe, id) {
		struct xe_guc *guc = &gt->uc.guc;
		struct xe_hw_engine *hwe;
		enum xe_hw_engine_id hid;
		struct xe_exec_queue *q;
		unsigned long index;

		drm_printf(&p, "GT%u: irq enabled %d, submission stopped %d enabled %d\n", id,
			   atomic_read(&xe->irq.enabled), atomic_read(&guc->submission_state.stopped),
			   guc->submission_state.enabled);
		xe_guc_ct_print(&guc->ct, &p, false);
		mutex_lock(&guc->submission_state.lock);
		xa_for_each(&guc->submission_state.exec_queue_lookup, index, q)
			if (q->guc->id == index)
				dump_queue(&p, q);
		mutex_unlock(&guc->submission_state.lock);
		xe_guc_submit_print(guc, &p);
		for_each_hw_engine(hwe, gt, hid) {
			struct xe_hw_fence_irq *irq = hwe->fence_irq;
			struct list_head *l;
			int n = 0;

			if (irq == NULL)
				continue;
			spin_lock_irq(&irq->lock);
			list_for_each(l, &irq->pending)
				n++;
			spin_unlock_irq(&irq->lock);
			drm_printf(&p, "  engine %s: irq_offset %u, fence irq enabled %d, %d fences pending\n", hwe->name,
				   hwe->irq_offset, irq->enabled, n);
		}
	}
}

void nmx_xe_debug_register(struct xe_device *xe)
{
	nmx_xe = xe;
	nmx_xnu_set_dump_hook(nmx_xe_dump);
}
