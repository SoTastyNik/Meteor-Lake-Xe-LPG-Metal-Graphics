#include <mach/mach.h>

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include "nvmtl_vk.h"
#include "nvmtl_readback.h"
int main(void) {
 nvk_image i={.img=(void *)1,.w=1920,.h=1080,.mips=12,.layers=4,.samples=1,.bpp=4,.usage=VK_IMAGE_USAGE_TRANSFER_SRC_BIT,.layout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
 nvmtl_read_plan p; const uint32_t a=VK_IMAGE_ASPECT_COLOR_BIT;
 assert(!nvmtl_read_plan_make(&i,7744,0,0,1920,1080,0,0,a,a,4,&p));
 assert(p.bytes==1920u*1080*4 && p.packed_row==7680 && p.rows==1080);
 assert(p.before.srcAccessMask & VK_ACCESS_MEMORY_WRITE_BIT);
 assert(p.before.dstAccessMask==VK_ACCESS_TRANSFER_READ_BIT);
 assert(p.after.newLayout==i.layout && p.after.oldLayout==VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL);
 assert(!nvmtl_read_plan_make(&i,3840,0,0,960,540,1,3,a,a,4,&p));
 assert(p.before.subresourceRange.baseMipLevel==1 && p.before.subresourceRange.levelCount==1);
 assert(p.before.subresourceRange.baseArrayLayer==3 && p.before.subresourceRange.layerCount==1);
 assert(i.layout==VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
 nvk_buffer b={.buf=(void *)2}; VkBufferMemoryBarrier host=nvmtl_read_host_barrier(&b,4096);
 assert(host.srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT && host.dstAccessMask==VK_ACCESS_HOST_READ_BIT && host.offset==0 && host.size==4096);
 #define BAD(x,y,w,h,l,z,pitch) assert(nvmtl_read_plan_make(&i,pitch,x,y,w,h,l,z,a,a,4,&p))
 BAD(0,0,1,1,32,0,4); BAD(0,0,1,1,12,0,4); BAD(UINT32_MAX,0,2,1,0,0,8);
 BAD(0,0,1920,1080,0,0,7679); BAD(0,0,1920,1080,0,4,7680); BAD(0,0,0,1,0,0,4);
 BAD(0,0,1920,1080,0,0,SIZE_MAX);
 i.samples=4; BAD(0,0,1,1,0,0,4); i.samples=1;
 i.usage=0; BAD(0,0,1,1,0,0,4); i.usage=VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
 i.layout=VK_IMAGE_LAYOUT_UNDEFINED; BAD(0,0,1,1,0,0,4); i.layout=VK_IMAGE_LAYOUT_GENERAL;
 i.mtl_type=7;i.layers=8; BAD(0,0,1,1,2,2,4);
 assert(!nvmtl_read_plan_make(&i,4,0,0,1,1,2,1,a,a,4,&p));
 assert(p.copy.imageOffset.z==1 && p.copy.imageSubresource.baseArrayLayer==0);
 i.mtl_type=2;i.w=65;i.h=65;i.bw=4;i.bh=4;
 assert(!nvmtl_read_plan_make(&i,16,64,64,1,1,0,0,a,a,16,&p));
 assert(nvmtl_read_plan_make(&i,16,0,0,1,1,0,0,a,a,16,&p));
 assert(nvmtl_read_plan_make(&i,16,1,0,4,4,0,0,a,a,16,&p));
 puts("PASS: full/padded/subresource copy plans; overflow/mip/sample/usage/block bounds; producer and host dependencies; layout restoration");
}
