from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;d=r/'drm-kmod/drivers/gpu/drm/i915';b=r/'backups/kernel-1.0.9-before';b.mkdir(parents=True,exist_ok=True)
for rel in ['i915_gpu_error.c','gt/uc/intel_guc_capture.c','gt/uc/intel_guc_capture.h']:
 f=d/rel;dest=b/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
f=d/'i915_gpu_error.c';s=f.read_text();needle='''	intel_engine_get_hung_entity(engine, &ce, &rq);''';insert='''
#ifdef NMXKPI
    /* rq has a reference from get_hung_entity. Snapshot only existing state:
       no new MMIO, list walks, allocation or wait in the hang path. */
    if (rq && INTEL_DEVID(engine->i915)==0x7d45) {
        pr_err("NMX-i915-request: engine=%s context=%llu seqno=%u flags=%lx error=%d ready=%u active=%u started=%u completed=%u submit-pending=%d\\n",
            engine->name, (unsigned long long)rq->fence.context, rq->fence.seqno,
            READ_ONCE(rq->fence.flags), READ_ONCE(rq->fence.error),
            i915_request_is_ready(rq), i915_request_is_active(rq),
            i915_request_started(rq), i915_request_completed(rq),atomic_read(&rq->submit.pending));
        pr_err("NMX-i915-request: guc-id=%u sched=%08x lrca=%08x hwsp=%08x ring=%llx head=%x postfix=%x tail=%x batch=%llx bytes=%llx\\n",
            rq->context->guc_id.id,READ_ONCE(rq->context->guc_state.sched_state),rq->context->lrc.lrca,
            hwsp_seqno(rq),(unsigned long long)rq->ring->vma->node.start,
            rq->head,rq->postfix,rq->tail,
            (unsigned long long)(rq->batch_res?rq->batch_res->start:0),
            (unsigned long long)(rq->batch_res?rq->batch_res->vma_size:0));
    }
#endif
''';assert needle in s;s=s.replace(needle,needle+insert,1)
needle='''            pr_err("NMX-i915-first-error: ring start=''';s=s.replace(needle,'''            intel_guc_capture_log_engine_node(engine);
'''+needle,1);f.write_text(s)
f=d/'gt/uc/intel_guc_capture.h';s=f.read_text();needle='void intel_guc_capture_free_node';s=s.replace(needle,'#ifdef NMXKPI\nvoid intel_guc_capture_log_engine_node(const struct intel_engine_coredump *ee);\n#endif\n\n'+needle,1);f.write_text(s)
f=d/'gt/uc/intel_guc_capture.c';s=f.read_text();needle='''#endif //CONFIG_DRM_I915_CAPTURE_ERROR''';insert='''#ifdef NMXKPI
/* The GuC path deliberately does not fill legacy ee->head/tail/etc. Emit the
   already-parsed captured values, rather than treating zero placeholders as HW. */
void intel_guc_capture_log_engine_node(const struct intel_engine_coredump *ee)
{
    const struct __guc_capture_parsed_output *node=ee->guc_capture_node;
    unsigned i,j;
    if(!node){pr_err("NMX-i915-guc-capture: unavailable; legacy register fields may be placeholders\\n");return;}
    pr_err("NMX-i915-guc-capture: id=%u lrca=%08x class=%u instance=%u partial=%u\\n",
        node->guc_id,node->lrca,node->eng_class,node->eng_inst,node->is_partial);
    for(i=0;i<GUC_CAPTURE_LIST_TYPE_MAX && i<3;i++){
        unsigned count=node->reginfo[i].num_regs;
        const struct guc_mmio_reg *regs=node->reginfo[i].regs;
        pr_err("NMX-i915-guc-capture: list=%u count=%u limit=64\\n",i,count);
        if(!regs)continue;
        for(j=0;j<count && j<64;j++)
            pr_err("NMX-i915-guc-reg: list=%u offset=%08x value=%08x flags=%08x\\n",
                i,regs[j].offset,regs[j].value,regs[j].flags);
    }
}
#endif

''';assert s.count(needle)==1;s=s.replace(needle,insert+needle);f.write_text(s)
print('Added bounded referenced-request and parsed GuC capture diagnostics; no scheduler/MMIO/policy changes')
