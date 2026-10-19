from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'drm-kmod/drivers/gpu/drm/i915/gt/uc/intel_guc_capture.c').read_text();a=s.index('void intel_guc_capture_log_engine_node(');b=s.index('\n#endif',a)
pre='''#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#define GUC_CAPTURE_LIST_TYPE_MAX 3
struct guc_mmio_reg{unsigned offset,value,flags;};
struct info{unsigned num_regs;struct guc_mmio_reg *regs;};
struct __guc_capture_parsed_output{unsigned guc_id,lrca,eng_class,eng_inst,is_partial;struct info reginfo[3];};
struct intel_engine_coredump{struct __guc_capture_parsed_output *guc_capture_node;};
static unsigned lines,registers,unavailable;static void pr_err(const char *fmt,...){lines++;if(strstr(fmt,"guc-reg:"))registers++;if(strstr(fmt,"unavailable"))unavailable++;}
'''
post='''int main(void){struct intel_engine_coredump ee={0};intel_guc_capture_log_engine_node(&ee);assert(unavailable==1&&registers==0);struct guc_mmio_reg regs[64]={0};struct __guc_capture_parsed_output node={0};ee.guc_capture_node=&node;for(unsigned i=0;i<3;i++){node.reginfo[i].regs=regs;node.reginfo[i].num_regs=500;}intel_guc_capture_log_engine_node(&ee);assert(registers==192);registers=0;node.reginfo[0].num_regs=0;node.reginfo[1].regs=0;node.reginfo[2].num_regs=1;intel_guc_capture_log_engine_node(&ee);assert(registers==1);puts("PASS actual parsed GuC capture under ASan/UBSan: missing node, bounded192register limit, empty/null lists; no MMIO/waits/allocations");}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(pre+s[a:b]+post);subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
