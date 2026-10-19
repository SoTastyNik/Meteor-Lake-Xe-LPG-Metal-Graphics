from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parent.parent
mman=(r/'NullMoth/gpu-port/xkpi/override/i915/i915_gem_mman.c').read_text()
pages=(r/'drm-kmod/drivers/gpu/drm/i915/gem/i915_gem_pages.c').read_text()
cdev=(r/'NullMoth/gpu-port/xkpi/override/src/nmx_linux_cdev.c').read_text()
def function(s,needle):
 a=s.index(needle);a=s.rfind('\n',0,a)+1;b=s.index('{',a);j=b+1;depth=1
 while depth:
  depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]+'\n'
hook=function(mman,'static int nmx_i915_user_mapping_pin(')
put=function(pages,'int __i915_gem_object_put_pages(')
cleanup=function(cdev,'static void umap_free(')
assert 'nmx_vma_set_pin(vma, nmx_i915_user_mapping_pin, obj)' in mman
assert 'vma->vm_ops == &vm_ops_cpu' in mman
mapping=mman[mman.index('static int\ni915_gem_object_mmap('):mman.index('int i915_gem_mmap(struct file')]
assert mapping.index('I915_MMAP_TYPE_GTT')<mapping.index('vma_set_file(vma, anon)')
assert 'return -EOPNOTSUPP;' in mapping
assert cdev.index('u->pinned = 1;')<cdev.index('err = nmx_xnu_map_user(')
pre=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#define M_NMXCDEV 0
struct sg_table{int x;};struct drm_i915_gem_object;
struct ops{void (*put_pages)(struct drm_i915_gem_object*,struct sg_table*);};
struct drm_i915_gem_object{int pins,fail;struct sg_table *pages;struct ops *ops;};
struct vm_area_struct;struct vmops{void (*close)(struct vm_area_struct*);};
struct vm_area_struct{struct vmops *vm_ops;void *vm_file,*vm_mm;};
struct nmx_umap{struct vm_area_struct vma;void *xmap;int pinned,vm_opened;int (*pin)(void*,bool);void *pin_arg;struct{int lock;}obj;void *pages;};
static char events[8];static unsigned event_n,freed;static struct sg_table page;
static int i915_gem_object_pin_pages_unlocked(struct drm_i915_gem_object *o){if(o->fail)return -ENOMEM;o->pins++;return 0;}
static void i915_gem_object_unpin_pages(struct drm_i915_gem_object *o){assert(o->pins>0);o->pins--;events[event_n++]='P';}
static bool i915_gem_object_has_pinned_pages(struct drm_i915_gem_object *o){return o->pins!=0;}
static void assert_object_held_shared(void *p){(void)p;}
static void i915_gem_object_release_mmap_offset(void *p){(void)p;}
static struct sg_table *__i915_gem_object_unset_pages(struct drm_i915_gem_object *o){struct sg_table *p=o->pages;o->pages=0;return p;}
#define IS_ERR_OR_NULL(p) (!(p))
static void drop(struct drm_i915_gem_object *o,struct sg_table *p){assert(p==&page);(void)o;freed++;}
static void nmx_xnu_unmap_user(void *p){assert(p);events[event_n++]='M';}
static void closed(struct vm_area_struct *p){(void)p;events[event_n++]='C';}
static void fput(void *p){(void)p;}static void mmput(void *p){(void)p;}static void mtx_destroy(void *p){(void)p;}
#define free(p,t) free(p)
'''
post=r'''
static void dispose(struct drm_i915_gem_object *o,bool mapped,bool pinned){
 struct nmx_umap *u=calloc(1,sizeof(*u));static struct vmops ops={closed};
 u->vma.vm_ops=&ops;u->vm_opened=1;u->pin=nmx_i915_user_mapping_pin;u->pin_arg=o;u->pinned=pinned;u->xmap=mapped?(void*)1:0;
 event_n=0;memset(events,0,sizeof events);umap_free(u);
 assert(!strcmp(events,mapped?"MPC":pinned?"PC":"C"));
}
int main(void){
 struct ops ops={drop};struct drm_i915_gem_object o={.pages=&page,.ops=&ops};
 /* Old static mapping: an object ref alone permits page release/reuse. */
 assert(__i915_gem_object_put_pages(&o)==0&&freed==1&&o.pages==0);
 /* New mapping pin: real put_pages guard blocks reclamation until unmap. */
 for(unsigned i=0;i<20000;i++){
  o.pages=&page;freed=0;assert(nmx_i915_user_mapping_pin(&o,true)==0&&o.pins==1);
  assert(__i915_gem_object_put_pages(&o)==-EBUSY&&o.pages==&page&&!freed);
  dispose(&o,true,true);assert(!o.pins);assert(__i915_gem_object_put_pages(&o)==0&&freed==1);
 }
 o.pages=&page;assert(!nmx_i915_user_mapping_pin(&o,true));assert(!nmx_i915_user_mapping_pin(&o,true));assert(o.pins==2);
 dispose(&o,true,true);assert(o.pins==1&&__i915_gem_object_put_pages(&o)==-EBUSY);dispose(&o,true,true);assert(o.pins==0);
 o.fail=1;assert(nmx_i915_user_mapping_pin(&o,true)==-ENOMEM&&!o.pins);dispose(&o,false,false);
 o.fail=0;assert(!nmx_i915_user_mapping_pin(&o,true));dispose(&o,false,true);assert(!o.pins);
 puts("PASS actual mapping hook + i915 page-release guard + port unmap cleanup under ASan/UBSan: old unpinned mapping permits release; pin blocks release, multiple maps retain pins, unmap precedes unpin/close, pin/map failure cleanup,20000 balanced lifetimes");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(pre+hook+put+cleanup+post);subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
