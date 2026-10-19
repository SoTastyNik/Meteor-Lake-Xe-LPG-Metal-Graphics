from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text();backup=r/'backups/desktop-0.2.7-before/nvmtl_vk.c';backup.write_text(s)
s=s.replace('''    VkImageMemoryBarrier toDst = { VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, NULL, 0, VK_ACCESS_TRANSFER_WRITE_BIT,
        VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        VK_QUEUE_FAMILY_IGNORED, VK_QUEUE_FAMILY_IGNORED, (VkImage)img->img, range };
    pvkCmdPipelineBarrier(c->cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &toDst);''','''    VkImageMemoryBarrier toDst = nvmtl_surface_upload_before(img, range);
    pvkCmdPipelineBarrier(c->cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &toDst);''',1)
f.write_text(s)
f=r/'NullMoth/plugin/nvmtl_readback.h';s=f.read_text();s+='''
/* IOSurface reuploads can follow render or transfer accesses to this image. */
static inline VkImageMemoryBarrier nvmtl_surface_upload_before(const nvk_image *i, VkImageSubresourceRange range)
{
    return (VkImageMemoryBarrier){VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,NULL,
        i->layout==VK_IMAGE_LAYOUT_UNDEFINED ? 0 : VK_ACCESS_MEMORY_READ_BIT|VK_ACCESS_MEMORY_WRITE_BIT,
        VK_ACCESS_TRANSFER_WRITE_BIT,(VkImageLayout)i->layout,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        VK_QUEUE_FAMILY_IGNORED,VK_QUEUE_FAMILY_IGNORED,(VkImage)i->img,range};
}
''';f.write_text(s)
f=r/'desktop-sources/test-readback.c';s=f.read_text();needle=' puts("PASS:';idx=s.index(needle);s=s[:idx]+''' i.layout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
 VkImageSubresourceRange range={a,0,1,0,1};
 VkImageMemoryBarrier upload=nvmtl_surface_upload_before(&i,range);
 assert(upload.oldLayout==VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL && (upload.srcAccessMask&VK_ACCESS_MEMORY_WRITE_BIT) && upload.dstAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT);
 i.layout=VK_IMAGE_LAYOUT_UNDEFINED;upload=nvmtl_surface_upload_before(&i,range);assert(upload.srcAccessMask==0);
'''+s[idx:];f.write_text(s)
