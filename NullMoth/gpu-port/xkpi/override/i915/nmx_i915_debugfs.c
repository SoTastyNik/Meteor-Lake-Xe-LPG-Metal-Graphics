/*
 * i915's GT debugfs registration: macOS has no debugfs, so there is nothing to register (CONFIG_DEBUG_FS is off).
 * The registration point is used instead to hook the GT into the driver state dump (xnu/nmx_diag.cpp,
 * NMX_DRM_IOCTL_DEBUG_DUMP): GT and GuC state, the GuC CT channel, submission and context state, and every engine's
 * intel_engine_dump (ring registers, HWSP seqnos, requests), which is what a submission that never completes needs.
 */
#include <drm/drm_print.h>

#include "i915_drv.h"
#include "i915_request.h"
#include "gt/intel_engine.h"
#include "gt/intel_gt.h"
#include "gt/intel_gt_debugfs.h"
#include "gt/intel_gt_pm.h"
#include "gt/intel_timeline.h"
#include "gt/uc/intel_guc.h"
#include "gt/uc/intel_guc_ct.h"
#include "gt/uc/intel_guc_submission.h"
#include "gt/uc/intel_uc_fw.h"
#include "nmx_xnu.h"

static struct intel_gt *nmx_gt;

/* drm_info_printer goes through dev_printk's "%pV", which LinuxKPI's printk does not expand: format here instead */
static void dump_printfn(struct drm_printer *p, struct va_format *vaf)
{
	char buf[512];
	va_list ap;

	va_copy(ap, *vaf->va);
	vsnprintf(buf, sizeof(buf), vaf->fmt, ap);
	va_end(ap);
	printf("i915 dump: %s", buf);
}

static void dump_puts(struct drm_printer *p, const char *str)
{
	printf("i915 dump: %s", str);
}

static void nmx_i915_dump(void)
{
	struct intel_gt *gt = nmx_gt;
	struct intel_guc *guc;
	struct intel_engine_cs *engine;
	enum intel_engine_id id;
	struct drm_printer p;

	if (gt == NULL)
		return;
	guc = gt_to_guc(gt);
	p = (struct drm_printer){ .printfn = dump_printfn, .puts = dump_puts };
	{
		/* user deadlines (syncobj waits) are on user space's CLOCK_MONOTONIC: show both kernel clocks */
		extern int64_t nmx_user_monotonic_ns(void);
		drm_printf(&p, "clocks: ktime %lld ns, user CLOCK_MONOTONIC as computed by the kernel %lld ns\n",
			   (long long)ktime_get_ns(), (long long)nmx_user_monotonic_ns());
	}
	drm_printf(&p, "GT%u: awake %d wedged %d, guc submission %d\n", gt->info.id,
		   intel_gt_pm_is_awake(gt), intel_gt_is_wedged(gt), intel_uc_uses_guc_submission(&gt->uc));
	intel_uc_fw_dump(&guc->fw, &p);
	intel_guc_load_status(guc, &p);
	intel_guc_ct_print_info(&guc->ct, &p);
	if (intel_uc_uses_guc_submission(&gt->uc)) {
		intel_guc_submission_print_info(guc, &p);
		intel_guc_submission_print_context_info(guc, &p);
	}
	/* every active timeline's requests, including ones still waiting on a dependency and not yet sent to the GuC */
	intel_gt_show_timelines(gt, &p, i915_request_show);
	for_each_engine(engine, gt, id)
		intel_engine_dump(engine, &p, "%s\n", engine->name);
}

void intel_gt_debugfs_register(struct intel_gt *gt)
{
	if (gt->info.id == 0) {
		nmx_gt = gt;
		nmx_xnu_set_dump_hook(nmx_i915_dump);
	}
}

void intel_gt_debugfs_register_files(struct dentry *root, const struct intel_gt_debugfs_file *files,
                                     unsigned long count, void *data)
{
}
