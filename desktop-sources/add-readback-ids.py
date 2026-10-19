from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port/NullMoth/plugin')
f=r/'nvmtl_vk.h';s=f.read_text();s=s.replace('/* memory type + 1, 0 unknown */ } nvk_buffer;', '/* memory type + 1, 0 unknown */ uint64_t trace_id; } nvk_buffer;',1);s=s.replace('uint64_t up_token; } nvk_image;', 'uint64_t up_token, trace_id; } nvk_image;',1);f.write_text(s)
f=r/'nvmtl_vk.c';s=f.read_text();s=s.replace('} else *out = pending;','''} else {
        static _Atomic uint64_t allocation_sequence;
        pending.trace_id=atomic_fetch_add(&allocation_sequence,1)+1;
        *out = pending;
    }''',1)
s=s.replace('const uint64_t id = atomic_fetch_add(&sequence,1)+1;','''const uint64_t id = atomic_fetch_add(&sequence,1)+1;
    static _Atomic uint64_t image_sequence;
    uint64_t image_id=__atomic_load_n(&img->trace_id,__ATOMIC_RELAXED);
    if (!image_id) {
        uint64_t candidate=atomic_fetch_add(&image_sequence,1)+1, expected=0;
        __atomic_compare_exchange_n(&img->trace_id,&expected,candidate,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED);
        image_id=__atomic_load_n(&img->trace_id,__ATOMIC_RELAXED);
    }''',1)
s=s.replace('thread=%llu img=%p stage=%p memory=', 'thread=%llu image-id=%llu stage-id=%llu img=%p stage=%p memory=',1)
s=s.replace('(unsigned long long)id,(unsigned long long)tid,img->img,stage.buf,stage.mem,','(unsigned long long)id,(unsigned long long)tid,(unsigned long long)image_id,(unsigned long long)stage.trace_id,img->img,stage.buf,stage.mem,',1)
f.write_text(s)
