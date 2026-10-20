from pathlib import Path
import subprocess,tempfile,os
r=Path(__file__).resolve().parent.parent
old=(r/'research/voodooi2chid-source/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp').read_text();new=(r/'research/voodooi2c-core/VoodooI2C Satellites/VoodooI2CHID/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp').read_text()
def function(s):
 a=s.index('void VoodooI2CTouchscreenHIDEventDriver::forwardReport(');b=s.index('{',a);j=b+1;depth=1
 while depth:depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]
pre=r'''
#include <cstdint>
#include <cassert>
#include <cstdio>
using AbsoluteTime=uint64_t;
struct OSObject{virtual ~OSObject()=default;};
struct OSNumber:OSObject{uint8_t n;explicit OSNumber(uint8_t v):n(v){}virtual uint8_t unsigned8BitValue(){return n;}};
#define OSDynamicCast(t,v) dynamic_cast<t*>(v)
static const char*kIOFBTransformKey="IOFBTransform";
struct IOFramebuffer{OSObject*property=nullptr;void retain(){}OSObject*getProperty(const char*){return property;}};
struct VoodooI2CMultitouchEvent{unsigned contact_count;};
struct Timer{unsigned calls=0;void cancelTimeout(){calls++;}};
struct Interface{unsigned properties=0,reports=0;uint8_t rotation=0;void setProperty(const char*,uint8_t r,unsigned){properties++;rotation=r;}void handleInterruptReport(VoodooI2CMultitouchEvent,uint64_t){reports++;}};
static IOFramebuffer *next_fb;
static void absolutetime_to_nanoseconds(uint64_t a,uint64_t*b){*b=a;}
struct VoodooI2CTouchscreenHIDEventDriver{
 IOFramebuffer*active_framebuffer=nullptr;uint8_t current_rotation=2;Interface*multitouch_interface;Timer*timer_source,*drag_timer_source;bool is_scrolling=false;uint64_t last_multitouch_interaction_time=0;unsigned scrolls=0,scheduled=0,resets=0;
 IOFramebuffer*getFramebuffer(){return next_fb;}
 void resetTouch(){resets++;}void scrollPosition(uint64_t,VoodooI2CMultitouchEvent){scrolls++;}void scheduleScrollEnd(){scheduled++;}
 bool checkStylus(uint64_t,VoodooI2CMultitouchEvent){return false;}bool checkFingerTouch(uint64_t,VoodooI2CMultitouchEvent){return false;}
 void forwardReport(VoodooI2CMultitouchEvent,uint64_t);
};
'''
post=r'''
int main(int argc,char**){
 OSObject wrong;OSNumber zero(0),rotated(0x30);IOFramebuffer fb;
 for(unsigned i=0;i<(argc>1?1u:10000u);i++)for(unsigned type=0;type<5;type++)for(unsigned contacts=0;contacts<4;contacts++){
  Interface interface;Timer timer,drag;VoodooI2CTouchscreenHIDEventDriver d;d.multitouch_interface=&interface;d.timer_source=&timer;d.drag_timer_source=&drag;
  fb.property=type==0?nullptr:type==1?&wrong:type==2?&zero:&rotated;next_fb=type==4?nullptr:&fb;
  d.forwardReport({contacts},42);
  assert(d.current_rotation==(type==2?0:type==3?3:2));
  assert(interface.properties==(type==2||type==3?1u:0u));
  assert(interface.reports==(contacts?1u:0u));
  assert(d.scheduled==(contacts==2?1u:0u));
 }
 puts("PASS actual forwardReport ASan/UBSan:200000 cases missing/wrong-type/zero/rotated/no framebuffer; zero/single/multiple contacts; rotation and report delivery preserved");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 for name,s in [('old',old),('new',new)]:
  f=p/(name+'.cpp');f.write_text(pre+function(s)+post);exe=p/name
  subprocess.run(['xcrun','clang++','-std=c++17','-fsanitize=address,undefined','-O1','-g',str(f),'-o',str(exe)],check=True)
  env=os.environ.copy();env['UBSAN_OPTIONS']='halt_on_error=1'
  x=subprocess.run([str(exe),*(['old'] if name=='old' else [])],env=env,capture_output=True,text=True)
  if name=='old':
   assert x.returncode!=0 and ('null pointer' in x.stderr or 'AddressSanitizer' in x.stderr),x.stdout+x.stderr
   (r/'desktop-build/hid-nullguard/old-null-transform-sanitizer.txt').write_text(x.stderr);print('PASS negative control: original forwardReport crashes on absent transform property')
  else:assert x.returncode==0,x.stdout+x.stderr;print(x.stdout.strip())
