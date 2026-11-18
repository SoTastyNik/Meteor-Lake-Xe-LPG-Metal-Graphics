/*
 * v75_2: the layer's own xnu spin locks, noted per CPU while held (nmx_kernel.c). A lck_spin raises the CPU's
 * preemption level; a thread that goes back to user space with it raised panics at its next page fault ("vm_fault()
 * KERN_FAILURE from user fault", WallpaperVideoExtension 2026-11-18). The DRM entry points check the level on the way
 * out (nmx_preempt_check) and name the locks still noted on that CPU.
 */
#ifndef NMX_SPIN_H
#define NMX_SPIN_H
#include <kern/locks.h>

void nmx_spin_lock_at(lck_spin_t *lk, const char *file, int line);
void nmx_spin_unlock_at(lck_spin_t *lk, const char *file, int line);
#define nmx_spin_lock(lk) nmx_spin_lock_at((lk), __FILE__, __LINE__)
#define nmx_spin_unlock(lk) nmx_spin_unlock_at((lk), __FILE__, __LINE__)

#endif
