from pathlib import Path
import subprocess,tempfile,os
r=Path(__file__).resolve().parent.parent
new=(r/'drm-kmod/drivers/gpu/drm/i915/gt/intel_breadcrumbs.c').read_text();old=(r/'backups/completion-context-before-1.0.14/intel_breadcrumbs.c').read_text();guc=(r/'drm-kmod/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c').read_text()
def function(s,needle):
 a=s.index(needle);a=s.rfind('\n',0,a)+1;b=s.index('{',a);j=b+1;depth=1
 while depth:depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]+'\n'
pre=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define unlikely(x) (x)
#define GEM_BUG_ON(x) assert(!(x))
#define I915_FENCE_FLAG_SIGNAL 1
#define I915_FENCE_FLAG_ACTIVE 2
#define DMA_FENCE_FLAG_SIGNALED_BIT 0
#define GUC_PRIO_FINI 99
#define __maybe_unused __attribute__((unused))
typedef uint64_t ktime_t;
struct list_head{struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head*h){h->next=h->prev=h;}
static bool list_empty(const struct list_head*h){return h->next==h;}
static void list_add_rcu(struct list_head*n,struct list_head*p){n->next=p->next;n->prev=p;p->next->prev=n;p->next=n;}
static void list_del_rcu(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
static void list_replace(struct list_head*a,struct list_head*b){b->next=a->next;b->prev=a->prev;b->next->prev=b;b->prev->next=b;}
#define list_entry(p,t,m) container_of(p,t,m)
#define list_entry_rcu(p,t,m) list_entry(p,t,m)
#define list_for_each_entry_rcu(p,h,m) for(p=list_entry((h)->next,typeof(*p),m); &(p)->m!=(h);p=list_entry((p)->m.next,typeof(*p),m))
#define list_for_each_entry_safe(p,n,h,m) for(p=list_entry((h)->next,typeof(*p),m),n=list_entry((p)->m.next,typeof(*p),m);&(p)->m!=(h);p=n,n=list_entry((n)->m.next,typeof(*n),m))
#define list_for_each_prev(p,h) for(p=(h)->prev;p!=(h);p=p->prev)
struct llist_node{struct llist_node*next;};struct llist_head{struct llist_node*first;};
static bool llist_empty(struct llist_head*h){return !h->first;}
static bool llist_add(struct llist_node*n,struct llist_head*h){bool empty=!h->first;n->next=h->first;h->first=n;return empty;}
static struct llist_node *llist_del_all(struct llist_head*h){struct llist_node*n=h->first;h->first=0;return n;}
#define llist_entry(p,t,m) container_of(p,t,m)
#define llist_for_each_safe(p,n,h) for(p=h;p && ((n=p->next),1);p=n)
struct irq_work{int dummy;};
struct intel_context{int refs,signal_lock;struct{struct intel_context *parent;}parallel;struct{int lock;}guc_state;struct list_head signals,signal_link;void*timeline;};
struct i915_request;struct sched_engine{void(*retire_inflight_request_prio)(struct i915_request*);};
struct intel_breadcrumbs{struct irq_work irq_work;struct list_head signalers;struct llist_head signaled_requests;int irq_armed,signaler_active,active;};
struct engine{struct intel_breadcrumbs*breadcrumbs;struct sched_engine*sched_engine;};
struct fence{unsigned long flags;struct list_head cb_list;uint64_t seqno;};
struct i915_request{int refs,lock,guc_prio;bool complete;struct intel_context *context;struct engine*engine;struct fence fence;struct list_head signal_link;struct llist_node signal_node;};
static unsigned contexts,requests,callbacks,notifications;static struct intel_context *retire_at_signal;
static struct intel_context *intel_context_get(struct intel_context*c){assert(c->refs>0);c->refs++;return c;}
static void intel_context_put(struct intel_context*c){assert(c->refs>0);if(!--c->refs){contexts--;memset(c,0,sizeof(*c));free(c);}}
static struct i915_request *i915_request_get(struct i915_request*q){assert(q->refs>0);q->refs++;return q;}
static void i915_request_put(struct i915_request*q){assert(q->refs>0);if(!--q->refs){requests--;free(q);}}
static bool test_bit(unsigned b,unsigned long*p){return (*p>>b)&1;}
static bool test_and_clear_bit(unsigned b,unsigned long*p){bool v=test_bit(b,p);*p&=~(1ul<<b);return v;}
static void set_bit(unsigned b,unsigned long*p){*p|=1ul<<b;}
static bool __dma_fence_signal(struct fence*f){bool win=!test_bit(0,&f->flags);set_bit(0,&f->flags);if(retire_at_signal){struct intel_context*c=retire_at_signal;retire_at_signal=0;intel_context_put(c);}return win;}
static void spin_lock(int*l){assert(*l==1);}static void spin_unlock(int*l){assert(*l==1);}
#define spin_lock_irqsave(l,f) do{f=0;spin_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)f;spin_unlock(l);}while(0)
static void atomic_inc(int*p){++*p;}static void atomic_dec(int*p){--*p;}static int atomic_read(int*p){return *p;}
static void rcu_read_lock(void){}static void rcu_read_unlock(void){}static void cpu_relax(void){abort();}
static ktime_t ktime_get(void){return 1;}
static void intel_breadcrumbs_disarm_irq(struct intel_breadcrumbs*b){b->irq_armed=0;}static void intel_breadcrumbs_arm_irq(struct intel_breadcrumbs*b){b->irq_armed=1;}
static bool __i915_request_is_complete(struct i915_request*q){return q->complete;}
static void add_retire(struct intel_breadcrumbs*b,void*t){(void)b;(void)t;}
static bool intel_timeline_is_last(void*t,struct i915_request*q){(void)t;(void)q;return false;}
static bool remove_signaling_context(struct intel_breadcrumbs*b,struct intel_context*c){(void)b;if(!list_empty(&c->signals))return false;list_del_rcu(&c->signal_link);return true;}
static void add_signaling_context(struct intel_breadcrumbs*b,struct intel_context*c){list_add_rcu(&c->signal_link,&b->signalers);}
static bool check_signal_order(struct intel_context*c,struct i915_request*q){return c==q->context;}
static bool i915_seqno_passed(uint64_t a,uint64_t b){return a>=b;}
static void __dma_fence_signal__timestamp(struct fence*f,ktime_t t){(void)f;(void)t;}
static void __dma_fence_signal__notify(struct fence*f,struct list_head*h){(void)f;(void)h;notifications++;}
static bool irq_work_queue(struct irq_work*w){(void)w;return true;}
static struct intel_context *request_to_scheduling_context(struct i915_request*q){struct intel_context*c=q->context;return c->parallel.parent?c->parallel.parent:c;}
static void guc_prio_fini(struct i915_request*q,struct intel_context*c){assert(c->guc_state.lock==1);q->guc_prio=GUC_PRIO_FINI;callbacks++;}
'''
post=r'''
static struct intel_context *context_new(struct intel_context*parent){struct intel_context*c=calloc(1,sizeof(*c));c->refs=1;c->signal_lock=c->guc_state.lock=1;c->parallel.parent=parent;INIT_LIST_HEAD(&c->signals);INIT_LIST_HEAD(&c->signal_link);contexts++;return c;}
static struct i915_request *request_new(struct intel_context*c,struct engine*e,bool complete){struct i915_request*q=calloc(1,sizeof(*q));q->refs=1;q->lock=1;q->context=c;q->engine=e;q->complete=complete;INIT_LIST_HEAD(&q->fence.cb_list);q->fence.seqno=1;requests++;return q;}
int main(int argc,char**argv){
 (void)argv;struct intel_breadcrumbs b={0};INIT_LIST_HEAD(&b.signalers);struct sched_engine se={guc_retire_inflight_request_prio};struct engine e={&b,&se};
 for(unsigned i=0;i<(argc>1?1u:10000u);i++){
  /* Already complete, then timeline ownership vanishes before IRQ worker. */
  struct intel_context*c=context_new(0);struct i915_request*q=request_new(c,&e,true);insert_breadcrumb(q);intel_context_put(c);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* Drop owner synchronously at SIGNALED publication, before queue insertion. */
  c=context_new(0);q=request_new(c,&e,true);retire_at_signal=c;insert_breadcrumb(q);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* Parallel parent lifetime is independent of the child's reference. */
  struct intel_context*parent=context_new(0);c=context_new(parent);q=request_new(c,&e,true);insert_breadcrumb(q);intel_context_put(parent);intel_context_put(c);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* Incomplete insertion, completed asynchronously; context list owner drops. */
  c=context_new(0);q=request_new(c,&e,false);insert_breadcrumb(q);intel_context_put(c);q->complete=true;signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* Cancellation before completion balances the list's ownership. */
  c=context_new(0);q=request_new(c,&e,false);insert_breadcrumb(q);i915_request_cancel_breadcrumb(q);intel_context_put(c);i915_request_put(q);assert(!contexts&&!requests);
  /* Completed cancellation transfers ownership to deferred signal work. */
  c=context_new(0);q=request_new(c,&e,false);insert_breadcrumb(q);q->complete=true;i915_request_cancel_breadcrumb(q);intel_context_put(c);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* Bulk removal has the same ownership transfer. */
  c=context_new(0);q=request_new(c,&e,false);insert_breadcrumb(q);q->complete=true;intel_context_remove_breadcrumbs(c,&b);intel_context_put(c);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
  /* A competing signal/retirement removes the last external request ref. */
  c=context_new(0);q=request_new(c,&e,false);insert_breadcrumb(q);q->complete=true;set_bit(0,&q->fence.flags);i915_request_put(q);intel_context_put(c);signal_irq_work(&b.irq_work);assert(!contexts&&!requests);
  /* Duplicate signal attempts never add another live owner. */
  c=context_new(0);q=request_new(c,&e,true);insert_breadcrumb(q);irq_signal_request(q,&b);intel_context_put(c);signal_irq_work(&b.irq_work);i915_request_put(q);assert(!contexts&&!requests);
 }
 assert(callbacks==notifications);puts("PASS actual breadcrumb enqueue/worker/cancel/bulk-remove + GuC callback ASan/UBSan:90000 lifetimes, retirement at publication, delayed worker, child/parent, duplicate signal; zero retained objects");
}
'''
needles=['static void signal_irq_work(','static void irq_signal_request(','static void insert_breadcrumb(','void i915_request_cancel_breadcrumb(','void intel_context_remove_breadcrumbs(']
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 for tag,src in [('old',old),('new',new)]:
  helpers=''
  if tag=='new':helpers=''.join(function(src,x) for x in ['static void breadcrumb_request_get(','static void breadcrumb_request_put('])
  slist=function(src,'static struct llist_node *\nslist_add(')
  body=pre+function(guc,'static void guc_retire_inflight_request_prio(')+helpers+slist+''.join(function(src,x) for x in needles)+post
  f=p/(tag+'.c');f.write_text(body);exe=p/tag
  subprocess.run(['xcrun','clang','-DNMXKPI=1','-fsanitize=address,undefined','-g','-O1',str(f),'-o',str(exe)],check=True)
  result=subprocess.run([str(exe),*(['old'] if tag=='old' else [])],capture_output=True,text=True)
  if tag=='old':
   assert result.returncode!=0 and 'heap-use-after-free' in result.stderr,result.stdout+result.stderr
   (r/'desktop-build/completion-context-old-asan.txt').write_text(result.stderr)
   print('PASS negative control: actual old enqueue/worker dereferences freed context at GuC retirement callback')
  else:
   assert result.returncode==0,result.stdout+result.stderr
   print(result.stdout.strip())
