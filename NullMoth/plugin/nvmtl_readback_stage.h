#pragma once
#include <pthread.h>
#include <string.h>
#include "nvmtl_ws_tuning.h"

#define NVMTL_READBACK_SLOTS 4
/* 40 MB, as NVMTL_PUBLICATION_MAX: a 2880x1920 frame did not fit the retained slots and got a fresh 22 MB
   staging buffer every frame */
#define NVMTL_READBACK_KEEP_MAX (40u << 20)
typedef struct {
    pthread_mutex_t mutex;
    nvk_buffer buffer;
    int quarantined;
} nvmtl_readback_slot;
static nvmtl_readback_slot nvmtl_readback_slots[NVMTL_READBACK_SLOTS]={
    {PTHREAD_MUTEX_INITIALIZER,{0},0},{PTHREAD_MUTEX_INITIALIZER,{0},0},
    {PTHREAD_MUTEX_INITIALIZER,{0},0},{PTHREAD_MUTEX_INITIALIZER,{0},0}
};

/* A lease holds its slot mutex through GPU completion AND the CPU copy.
   Try-lock only: nested or concurrent readers fall back instead of waiting. */
static int nvmtl_readback_stage_acquire(size_t bytes,int retain,nvk_buffer *out,int *lease)
{
    *lease=-1;
    if(retain && bytes && bytes<=NVMTL_READBACK_KEEP_MAX){
        for(unsigned i=0;i<NVMTL_READBACK_SLOTS;i++){
            nvmtl_readback_slot *slot=&nvmtl_readback_slots[i];
            if(pthread_mutex_trylock(&slot->mutex))continue;
            if(slot->quarantined){pthread_mutex_unlock(&slot->mutex);continue;}
            if(slot->buffer.buf && slot->buffer.size<bytes)
                nvmtl_vk_buffer_destroy(&slot->buffer);
            if(slot->buffer.buf && slot->buffer.size<bytes){pthread_mutex_unlock(&slot->mutex);return -1;}
            /* leased slots get their cache lines flushed around every use, so they may live in cached memory */
            if(!slot->buffer.buf && nvmtl_vk_buffer_create(bytes,nvmtl_ws_cached_readback()?NVMTL_HOST_CACHED_READBACK:3,&slot->buffer)){
                pthread_mutex_unlock(&slot->mutex);return -1;
            }
            *out=slot->buffer;*lease=(int)i;return 0;
        }
    }
    return nvmtl_vk_buffer_create(bytes,3,out);
}

/* disposition: 0 uncertain submission, 1 completed/never submitted,
   2 known idle but invalid mapping/type. Never free uncertain GPU resources. */
static void nvmtl_readback_stage_release(nvk_buffer *stage,int lease,int disposition)
{
    if(lease<0){if(disposition)nvmtl_vk_buffer_destroy(stage);return;}
    nvmtl_readback_slot *slot=&nvmtl_readback_slots[lease];
    if(!disposition)slot->quarantined=1;
    else if(disposition==2)nvmtl_vk_buffer_destroy(&slot->buffer);
    memset(stage,0,sizeof *stage);
    pthread_mutex_unlock(&slot->mutex);
}
