from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port'); p=r/'NullMoth/plugin'
(p/'nvmtl_readback.h').write_text('''#pragma once
#include <stdint.h>
#include <stddef.h>
/* The caller owns the image until completion. No persistent layout change is made. */
typedef struct { uint32_t cols, rows; size_t packed_row, bytes; VkBufferImageCopy copy; VkImageMemoryBarrier before, after; } nvmtl_read_plan;
static inline int nvmtl_read_plan_make(const nvk_image *i, size_t pitch,
    uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t level, uint32_t layer,
    VkImageAspectFlags aspect, VkImageAspectFlags barrier_aspect, size_t bpp, nvmtl_read_plan *p)
{
    if (!i || !i->img || !w || !h || !bpp || !i->w || !i->h || level >= 32 ||
        level >= (i->mips ? i->mips : 1) || i->samples > 1 ||
        !(i->usage & VK_IMAGE_USAGE_TRANSFER_SRC_BIT) ||
        i->layout == VK_IMAGE_LAYOUT_UNDEFINED || i->layout == VK_IMAGE_LAYOUT_PREINITIALIZED ||
        !aspect || (aspect & (aspect-1)) || (aspect & barrier_aspect) != aspect) return -1;
    uint32_t lw=i->w>>level, lh=i->h>>level;
    if (!lw) lw=1; if (!lh) lh=1;
    uint32_t nl=i->layers ? i->layers : 1;
    if (i->mtl_type==7) { nl >>= level; if (!nl) nl=1; }
    if (layer>=nl || x>=lw || y>=lh || w>lw-x || h>lh-y || x>INT32_MAX || y>INT32_MAX || layer>INT32_MAX) return -1;
    uint32_t bw=i->bw ? i->bw : 1, bh=i->bh ? i->bh : 1;
    if (x%bw || y%bh || (w%bw && w!=lw-x) || (h%bh && h!=lh-y)) return -1;
    p->cols=w/bw+(w%bw!=0); p->rows=h/bh+(h%bh!=0);
    if (p->cols>SIZE_MAX/bpp) return -1;
    p->packed_row=p->cols*bpp;
    if (pitch<p->packed_row || p->rows>SIZE_MAX/p->packed_row ||
        (p->rows>1 && pitch>(SIZE_MAX-p->packed_row)/(p->rows-1))) return -1;
    p->bytes=p->packed_row*p->rows;
    p->copy=(VkBufferImageCopy){0,0,0,{aspect,level,i->mtl_type==7 ? 0:layer,1},
        {(int32_t)x,(int32_t)y,i->mtl_type==7 ? (int32_t)layer:0},{w,h,1}};
    VkImageSubresourceRange range={barrier_aspect,level,1,i->mtl_type==7 ? 0:layer,1};
    p->before=(VkImageMemoryBarrier){VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,NULL,
        VK_ACCESS_MEMORY_READ_BIT|VK_ACCESS_MEMORY_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT,
        (VkImageLayout)i->layout,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
        VK_QUEUE_FAMILY_IGNORED,VK_QUEUE_FAMILY_IGNORED,(VkImage)i->img,range};
    p->after=p->before; p->after.srcAccessMask=VK_ACCESS_TRANSFER_READ_BIT;
    p->after.dstAccessMask=VK_ACCESS_MEMORY_READ_BIT|VK_ACCESS_MEMORY_WRITE_BIT;
    p->after.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL; p->after.newLayout=(VkImageLayout)i->layout;
    return 0;
}
static inline VkBufferMemoryBarrier nvmtl_read_host_barrier(const nvk_buffer *b, size_t bytes)
{
    return (VkBufferMemoryBarrier){VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,NULL,
        VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_HOST_READ_BIT,
        VK_QUEUE_FAMILY_IGNORED,VK_QUEUE_FAMILY_IGNORED,(VkBuffer)b->buf,0,bytes};
}
''')
f=p/'nvmtl_vk.c';s=f.read_text();s=s.replace('#include "nvmtl_vk.h"','#include "nvmtl_vk.h"\n#include "nvmtl_readback.h"',1)
a=s.index('int nvmtl_vk_image_read(nvk_queue *q,');b=s.index('\nstatic void img_to(',a)
s=s[:a]+'''static int nvmtl_vk_readback(nvk_queue *q, nvk_image *img, void *dst, size_t row_bytes,
    uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t level, uint32_t layer)
{
    nvmtl_read_plan plan;
    const size_t bpp = g_copy_bpp_override ? g_copy_bpp_override : (img && img->bpp ? img->bpp : 4);
    if (!q || !dst || nvmtl_read_plan_make(img, row_bytes, x,y,w,h,level,layer,
        nvmtl_copy_aspect(img), nvmtl_barrier_aspect(img), bpp, &plan)) {
        nvlog("readback REFUSED invalid image/copy parameters"); return -1;
    }
    nvmtl_vk_image_upload_barrier(img);
    const int owned = getenv("NVMTL_READBACK_STAGE_FRESH") != NULL;
    nvk_buffer stage = {0};
    if (owned ? nvmtl_vk_buffer_create(plan.bytes, 1, &stage) : nvmtl_vk_stage(q, plan.bytes, &stage)) return -1;
    /* All staging allocation paths require HOST_VISIBLE|HOST_COHERENT. Refuse
       an unknown or incompatible memory type rather than reading stale bytes. */
    const uint32_t mt = stage.memtype1 ? stage.memtype1-1 : UINT32_MAX;
    if (!stage.map || mt >= g_memp.memoryTypeCount ||
        (g_memp.memoryTypes[mt].propertyFlags & (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) !=
        (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) {
        nvlog("readback REFUSED noncoherent or unknown staging memory type %u", mt);
        if (owned) nvmtl_vk_buffer_destroy(&stage); return -1;
    }
    nvk_cmdbuf c;
    if (nvmtl_vk_cmd_begin(q, &c)) { if (owned) nvmtl_vk_buffer_destroy(&stage); return -1; }
    static _Atomic uint64_t sequence;
    const uint64_t id = atomic_fetch_add(&sequence,1)+1;
    uint64_t tid=0; pthread_threadid_np(NULL,&tid);
    const int trace = id<=32 || getenv("NVMTL_READBACK_TRACE") != NULL;
    if (trace) nvlog("first-submit readback #%llu thread=%llu img=%p stage=%p memory=%p offset=%zu type=%u coherent=1 layout=%u mip=%u layer=%u rect=%u,%u,%u,%u pitch=%zu bytes=%zu owned=%d cb=%p",
        (unsigned long long)id,(unsigned long long)tid,img->img,stage.buf,stage.mem,stage.poff,mt,img->layout,level,layer,x,y,w,h,row_bytes,plan.bytes,owned,c.cb);
    pvkCmdPipelineBarrier(c.cb,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,
        0,0,NULL,0,NULL,1,&plan.before);
    pvkCmdCopyImageToBuffer(c.cb,(VkImage)img->img,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,(VkBuffer)stage.buf,1,&plan.copy);
    VkBufferMemoryBarrier host=nvmtl_read_host_barrier(&stage,plan.bytes);
    pvkCmdPipelineBarrier(c.cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,
        0,0,NULL,1,&host,0,NULL);
    /* Restore only the copied subresource, leaving the shared layout tracker
       untouched and avoiding a readback-created divergence across mip levels. */
    pvkCmdPipelineBarrier(c.cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
        0,0,NULL,0,NULL,1,&plan.after);
    int rc=nvmtl_vk_submit_wait_at(&c,"image readback");
    if (trace || rc) nvlog("first-submit readback #%llu completion=%d stage=%p disposition=%s",
        (unsigned long long)id,rc,stage.buf,rc ? "retained-no-cpu-read" : owned ? "release-after-copy" : "tls-retained");
    /* On an uncertain submission, retain its allocation. Backend shutdown
       prevents further copies; freeing potentially pending memory is unsafe. */
    if (rc) return -1;
    for (uint32_t row=0;row<plan.rows;row++) memcpy((uint8_t *)dst+(size_t)row*row_bytes,
        (const uint8_t *)stage.map+(size_t)row*plan.packed_row,plan.packed_row);
    if (owned) nvmtl_vk_buffer_destroy(&stage);
    return 0;
}
int nvmtl_vk_image_read(nvk_queue *q, nvk_image *img, void *dst, size_t row_bytes)
{
    return nvmtl_vk_readback(q,img,dst,row_bytes,0,0,img ? img->w:0,img ? img->h:0,0,0);
}
''' + s[b:]
a=s.index('int nvmtl_vk_image_read_region_level_layer(nvk_queue *q,');b=s.index('\nint nvmtl_vk_copy_image(',a)
s=s[:a]+'''int nvmtl_vk_image_read_region_level_layer(nvk_queue *q, nvk_image *img, void *dst, size_t row_bytes,
                                     uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t level, uint32_t layer)
{
    return nvmtl_vk_readback(q,img,dst,row_bytes,x,y,w,h,level,layer);
}
''' +s[b:];f.write_text(s)
