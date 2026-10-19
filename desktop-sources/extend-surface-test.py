from pathlib import Path
f=Path('/Users/ved/Documents/iGPU Port/latitude-desktop/tools/latitude-readback-test.m');s=f.read_text();s=s.replace('static BOOL raw=NO,surface=NO,fresh=NO,shared=NO,native=NO;', 'static BOOL raw=NO,surface=NO,fresh=NO,shared=NO,native=NO,bgra=NO;')
s=s.replace('texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:width', 'texture2DDescriptorWithPixelFormat:(output&&bgra ? MTLPixelFormatBGRA8Unorm:MTLPixelFormatRGBA8Unorm) width:width',1)
s=s.replace('(id)kIOSurfacePixelFormat:@(0x52474241)', '(id)kIOSurfacePixelFormat:@(bgra?0x42475241:0x52474241)',1)
s=s.replace('else if(!strcmp(argv[i],"--raw"))raw=YES;', 'else if(!strcmp(argv[i],"--raw"))raw=YES;else if(!strcmp(argv[i],"--bgra"))bgra=YES;',1)
s=s.replace('d.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;', 'd.colorAttachments[0].pixelFormat=bgra?MTLPixelFormatBGRA8Unorm:MTLPixelFormatRGBA8Unorm;',1)
s=s.replace('channel(x,y,seed,c)+(raw?0:delta)', 'channel(x,y,seed,(!raw&&bgra&&c<3)?2-c:c)+(raw?0:delta)',1)
needle='''  if(shared)pthread_mutex_unlock(&ownership);
  if((frame+1)%50==0'''
replacement='''  if(surface && !atomic_load(&failed)) {
   IOSurfaceRef backing=out.iosurface;
   if(!backing || IOSurfaceLock(backing,kIOSurfaceLockReadOnly,NULL)!=kIOReturnSuccess) error("IOSurface backing lock",worker,frame);
   else {
    const uint8_t *base=IOSurfaceGetBaseAddress(backing);size_t stride=IOSurfaceGetBytesPerRow(backing);
    if(!base||stride<(size_t)width*4) error("IOSurface backing geometry",worker,frame);
    else for(unsigned y=0;y<height&&!atomic_load(&failed);y++)for(unsigned x=0;x<width;x++)for(unsigned c=0;c<4;c++) {
     unsigned expected=c==3?255:(channel(x,y,seed,bgra?2-c:c)+delta)&255;
     unsigned got=base[(size_t)y*stride+x*4+c];
     if(got!=expected){char msg[240];snprintf(msg,sizeof msg,"IOSurface backing (%u,%u) c=%u got=%u expected=%u",x,y,c,got,expected);error(msg,worker,frame);break;}
    }
    IOSurfaceUnlock(backing,kIOSurfaceLockReadOnly,NULL);
   }
  }
  if(shared)pthread_mutex_unlock(&ownership);
  if((frame+1)%50==0'''
assert needle in s;s=s.replace(needle,replacement,1)
s=s.replace('if(atomic_load(&failed))return 1;','if(atomic_load(&failed))return 1;\n if(surface)puts("PASS IOSurface backing: all published CPU pixels checked after GPU completion");',1)
f.write_text(s)
