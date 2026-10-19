#include "latitude_scanout.h"
#include <assert.h>
#include <stdio.h>
int main(){
 LatitudeScanout m={0x90800000,0x90000000,0x90800000,128ull<<20,0x4000000000,256ull<<20,0xff800000,8192,8ull<<20};
 uint64_t pt[]={0x800003,0x801003},cpu=0;
 assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapOK&&cpu==m.gop);
 m.gop=m.bar+0x800000;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapOK&&cpu==0x90800000);
 m.gop++;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapBounds);m.gop--;
 pt[1]=0x802003;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapDiscontiguous);pt[1]=0x801001;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapFlags);pt[1]=0x801003;
 m.gop+=4096;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapGOP);m.gop-=4096;
 m.ggttBytes=4ull<<20;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapBounds);m.ggttBytes=8ull<<20;
 assert(latitudeTranslate(m,pt,1,&cpu)==LatitudeMapBounds);
 m.surface=0xfffff000;assert(latitudeTranslate(m,pt,2,&cpu)==LatitudeMapBounds);
 puts("PASS scanout translation fixtures: direct/BAR GOP aliases, page continuity, flags, bounds and mismatch rejection");
}
