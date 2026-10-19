#pragma once
#include <stdint.h>
#include <stddef.h>
struct LatitudeScanout {
 uint64_t gop,gsm,dsm,dsmBytes,bar,barBytes,surface,bytes,ggttBytes;
};
enum LatitudeMapResult { LatitudeMapOK,LatitudeMapBounds,LatitudeMapFlags,LatitudeMapDiscontiguous,LatitudeMapGOP };
static inline LatitudeMapResult latitudeTranslate(const LatitudeScanout &m,const volatile uint64_t *pt,size_t count,uint64_t *cpu) {
 const uint64_t page=4096,eightM=8ull<<20,mask=0x00003ffffffff000ull;
 if(!m.bytes||m.bytes>(128ull<<20)||(m.gop&4095)||(m.surface&4095)||!m.gsm||m.gsm>UINT64_MAX-eightM||m.dsm!=m.gsm+eightM||!m.dsmBytes||m.ggttBytes>eightM)return LatitudeMapBounds;
 uint64_t pages=(m.bytes+page-1)/page,first=m.surface/page;
 if(first>m.ggttBytes/8||pages>m.ggttBytes/8-first||count<pages)return LatitudeMapBounds;
 uint64_t initial=pt[0]&mask;
 if(initial<eightM||m.bytes>m.dsmBytes||initial-eightM>m.dsmBytes-m.bytes)return LatitudeMapBounds;
 for(uint64_t i=0;i<pages;i++) {
  uint64_t pte=pt[i];if((pte&3)!=3)return LatitudeMapFlags;
  if((pte&mask)!=initial+i*page)return LatitudeMapDiscontiguous;
 }
 if(m.dsm>UINT64_MAX-(initial-eightM))return LatitudeMapBounds;
 uint64_t direct=m.dsm+(initial-eightM);
 bool viaBar=initial<=m.barBytes&&m.bytes<=m.barBytes-initial&&m.bar<=UINT64_MAX-initial&&m.gop==m.bar+initial;
 if(m.gop!=direct&&!viaBar)return LatitudeMapGOP;
 *cpu=direct;return LatitudeMapOK;
}
