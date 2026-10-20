from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parent.parent
src=(r/'drm-kmod/drivers/gpu/drm/i915/intel_memory_region.c').read_text()
ring=(r/'drm-kmod/drivers/gpu/drm/i915/gt/intel_ring.c').read_text()
def function(s,needle):
 a=s.index(needle);b=s.index('{',a);j=b+1;depth=1
 while depth:depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]+'\n'
probe=function(src,'int intel_memory_regions_hw_probe(')
create=function(ring,'static struct i915_vma *create_ring_vma(')
pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
typedef uint16_t u16;typedef uint64_t u64;
#define INTEL_MEMORY_SYSTEM 0
#define INTEL_MEMORY_STOLEN_LOCAL 1
#define INTEL_MEMORY_STOLEN_SYSTEM 2
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define INTEL_DEVID(d) ((d)->device)
#define HAS_REGION(d,i) (((d)->mask>>(i))&1)
#define IS_DGFX(d) 0
#define ERR_PTR(e) ((void*)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_CAST(p) ((void*)(p))
#define drm_info(...) ((void)0)
#define drm_dbg(...) ((void)0)
#define drm_err(...) ((void)0)
#define I915_BO_ALLOC_VOLATILE 1
#define I915_BO_ALLOC_PM_VOLATILE 2
#define HAS_LLC(d) 0
struct resource{unsigned size;};
struct intel_memory_region{unsigned id;char *name;struct resource region,io;};
struct drm_i915_private{unsigned device,mask;int drm;struct{struct intel_memory_region *regions[3],*stolen_region;}mm;};
struct i915_address_space{struct drm_i915_private *i915;bool has_read_only;};
struct i915_ggtt{struct i915_address_space vm;};struct drm_i915_gem_object{bool stolen;};struct i915_vma{struct drm_i915_gem_object *obj;};
static const struct{u16 class,instance;}intel_region_map[]={{0,0},{1,0},{2,0}};
static struct intel_memory_region regions[3];static unsigned stolen_calls,internal_calls,cleanups;static int fail;
static struct intel_memory_region *setup(struct drm_i915_private *d,u16 t,u16 i){(void)d;(void)i;if(fail)return ERR_PTR(-ENOMEM);if(t)stolen_calls++;return &regions[t];}
#define i915_gem_shmem_setup setup
#define i915_gem_ttm_system_setup setup
#define i915_gem_stolen_lmem_setup setup
#define i915_gem_stolen_smem_setup setup
static void intel_memory_regions_driver_release(struct drm_i915_private *d){(void)d;cleanups++;}
static u64 resource_size(struct resource *r){return r->size;}
static struct drm_i915_gem_object object;static struct i915_vma vma;
static void *i915_gem_object_create_lmem(struct drm_i915_private*d,int s,int f){(void)d;(void)s;(void)f;return ERR_PTR(-ENODEV);}
static bool i915_ggtt_has_aperture(struct i915_ggtt *g){(void)g;return true;}
static void *i915_gem_object_create_stolen(struct drm_i915_private*d,int s){(void)s;if(!d->mm.stolen_region)return ERR_PTR(-ENODEV);object.stolen=true;return &object;}
static void *i915_gem_object_create_internal(struct drm_i915_private*d,int s){(void)d;(void)s;internal_calls++;object.stolen=false;return &object;}
static void i915_gem_object_set_readonly(void*p){(void)p;}
static void *i915_vma_instance(struct drm_i915_gem_object*o,void*v,void*f){(void)v;(void)f;vma.obj=o;return &vma;}
static void i915_gem_object_put(void*p){(void)p;}
'''
post=r'''
int main(void){
 struct drm_i915_private d={.device=0x7d45,.mask=7};
 struct i915_ggtt g={.vm={.i915=&d}};
 assert(!intel_memory_regions_hw_probe(&d));
#ifdef NMXKPI
 assert(d.mm.regions[0]&&!d.mm.regions[1]&&!d.mm.regions[2]&&!d.mm.stolen_region&&!stolen_calls);
 assert(create_ring_vma(&g,16384)==&vma&&!vma.obj->stolen&&internal_calls==1);
#else
 assert(d.mm.stolen_region&&stolen_calls==2);
 assert(create_ring_vma(&g,16384)==&vma&&vma.obj->stolen&&!internal_calls);
#endif
 struct drm_i915_private other={.device=0x9a60,.mask=7};
 assert(!intel_memory_regions_hw_probe(&other)&&other.mm.regions[1]&&other.mm.regions[2]&&other.mm.stolen_region);
 fail=1;assert(intel_memory_regions_hw_probe(&other)==-ENOMEM&&cleanups==1);
 puts("PASS actual region-probe and ring-allocation functions: protected 7d45 uses system ring; other-device/non-port paths preserved; error cleanup preserved");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(pre+probe+create+post)
 for defines in [[],['-DNMXKPI=1']]:
  subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g',*defines,str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
