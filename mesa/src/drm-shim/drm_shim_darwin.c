/*
 * Copyright © 2018 Broadcom
 * SPDX-License-Identifier: MIT
 */

/**
 * @file
 *
 * macOS front end for drm-shim.
 *
 * On Linux, drm-shim is preloaded and overrides libc by symbol name, and fakes
 * the sysfs files libdrm reads.  macOS has no sysfs: libdrm finds a DRM node by
 * its device number among the entries of /dev/dri and asks the kernel for the
 * PCI identity with DRM_IOCTL_GET_PCIINFO (as on OpenBSD).  This file fakes
 * exactly that surface, and routes ioctl/mmap on the fake node into the shared
 * core in device.c.
 *
 * Load it with DYLD_INSERT_LIBRARIES.  The libc entry points are replaced with
 * dyld interposing (__DATA,__interpose), which applies to every image except
 * this one, so calls made from inside the shim reach the real libc directly.
 */

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "drm-uapi/drm.h"
#include "drm_shim.h"
#include "util/u_debug.h"

/* Darwin assigns character majors at run time; this one is only ever seen
 * through the shim's own stat answers, never by the kernel.
 */
#define SHIM_DARWIN_MAJOR 250

/* Same layout and request number as libdrm's OpenBSD/Darwin definition. */
struct drm_pciinfo {
   uint16_t domain;
   uint8_t bus;
   uint8_t dev;
   uint8_t func;
   uint16_t vendor_id;
   uint16_t device_id;
   uint16_t subvendor_id;
   uint16_t subdevice_id;
   uint8_t revision_id;
};
#define DRM_IOCTL_GET_PCIINFO DRM_IOR(0x15, struct drm_pciinfo)

static const char render_node_path[] = "/dev/dri/renderD128";
static const char render_node_dirent_name[] = "renderD128";
const int render_node_minor = 128;
bool drm_shim_driver_prefers_new_render_node = true;
bool drm_shim_debug;

static struct drm_pciinfo shim_pciinfo;

static pthread_mutex_t shim_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t shim_once = PTHREAD_ONCE_INIT;
static bool inited;

/* opendir("/dev/dri") handles that still owe the caller our fake entry.  A
 * handful at most are open at once; the bound is checked, never assumed.
 */
#define MAX_DRI_DIRS 16
static DIR *dri_dirs[MAX_DRI_DIRS];

/* When /dev/dri does not exist (no DRM kernel driver yet), opendir returns
 * this pointer, which no real opendir can return.
 */
static int fake_dir_storage;
#define FAKE_DEV_DRI ((DIR *)&fake_dir_storage)

static void
init_shim_once(void)
{
   drm_shim_debug = debug_get_bool_option("DRM_SHIM_DEBUG", false);
   if (drm_shim_debug)
      fprintf(stderr, "Initializing DRM shim on %s\n", render_node_path);
   drm_shim_device_init();
   inited = true;
}

static void
init_shim(void)
{
   pthread_once(&shim_once, init_shim_once);
}

bool
drm_shim_inited(void)
{
   return inited;
}

/* The Linux files these describe do not exist on macOS; nothing reads them. */
void
drm_shim_override_file(const char *contents, const char *path_format, ...)
{
}

void
drm_shim_override_link(const char *contents, const char *path_format, ...)
{
}

void
drm_shim_pci_device_setup(uint16_t vendor_id, uint16_t device_id,
                          const char *pci_slot, const char *driver_name)
{
   unsigned domain = 0, bus = 0, dev = 0, func = 0;

   if (sscanf(pci_slot, "%x:%x:%x.%x", &domain, &bus, &dev, &func) != 4) {
      fprintf(stderr, "drm-shim: bad PCI slot '%s'\n", pci_slot);
      abort();
   }

   shim_device.bus_type = DRM_BUS_PCI;
   shim_device.driver_name = driver_name;
   shim_pciinfo = (struct drm_pciinfo) {
      .domain = domain, .bus = bus, .dev = dev, .func = func,
      .vendor_id = vendor_id, .device_id = device_id,
      .subvendor_id = 0x1234, .subdevice_id = 0x1234, .revision_id = 0,
   };
}

void
drm_shim_platform_device_setup(const char *driver_name, const char *fullname,
                               const char *compatible)
{
   /* libdrm has no Darwin platform-bus parser; only PCI devices are faked. */
   fprintf(stderr, "drm-shim: platform devices are not supported on macOS\n");
   abort();
}

static bool
is_render_node(const char *path)
{
   return path && strcmp(path, render_node_path) == 0;
}

static void
fill_node_stat(struct stat *st)
{
   memset(st, 0, sizeof(*st));
   st->st_rdev = makedev(SHIM_DARWIN_MAJOR, render_node_minor);
   st->st_mode = S_IFCHR | 0666;
}

static int
shim_open(const char *path, int flags, ...)
{
   mode_t mode = 0;
   if (flags & O_CREAT) {
      va_list ap;
      va_start(ap, flags);
      mode = (mode_t)va_arg(ap, int);
      va_end(ap);
   }

   if (!is_render_node(path))
      return open(path, flags, mode);

   init_shim();
   int fd = open("/dev/null", O_RDWR | (flags & O_CLOEXEC));
   if (fd >= 0)
      drm_shim_fd_register(fd, NULL);
   return fd;
}

static int
shim_close(int fd)
{
   if (inited)
      drm_shim_fd_unregister(fd);
   return close(fd);
}

static int
shim_access(const char *path, int mode)
{
   if (is_render_node(path))
      return 0;
   return access(path, mode);
}

static int
shim_stat(const char *path, struct stat *st)
{
   if (is_render_node(path)) {
      fill_node_stat(st);
      return 0;
   }
   return stat(path, st);
}

static int
shim_lstat(const char *path, struct stat *st)
{
   if (is_render_node(path)) {
      fill_node_stat(st);
      return 0;
   }
   return lstat(path, st);
}

static int
shim_fstat(int fd, struct stat *st)
{
   if (inited && drm_shim_fd_lookup(fd)) {
      fill_node_stat(st);
      return 0;
   }
   return fstat(fd, st);
}

static DIR *
shim_opendir(const char *name)
{
   DIR *dir = opendir(name);
   if (strcmp(name, "/dev/dri") != 0)
      return dir;

   if (!dir)
      dir = FAKE_DEV_DRI;

   pthread_mutex_lock(&shim_lock);
   int i;
   for (i = 0; i < MAX_DRI_DIRS && dri_dirs[i]; i++)
      ;
   if (i == MAX_DRI_DIRS) {
      pthread_mutex_unlock(&shim_lock);
      fprintf(stderr, "drm-shim: more than %d open /dev/dri handles\n", MAX_DRI_DIRS);
      abort();
   }
   dri_dirs[i] = dir;
   pthread_mutex_unlock(&shim_lock);
   return dir;
}

/* Our render node is listed first, then the real entries, if any. */
static struct dirent *
shim_readdir(DIR *dir)
{
   static struct dirent render_node_dirent;
   bool ours = false;

   pthread_mutex_lock(&shim_lock);
   for (int i = 0; i < MAX_DRI_DIRS; i++) {
      if (dri_dirs[i] == dir) {
         dri_dirs[i] = NULL;
         ours = true;
         break;
      }
   }
   pthread_mutex_unlock(&shim_lock);

   if (ours) {
      memset(&render_node_dirent, 0, sizeof(render_node_dirent));
      strcpy(render_node_dirent.d_name, render_node_dirent_name);
      render_node_dirent.d_namlen = strlen(render_node_dirent_name);
      render_node_dirent.d_type = DT_CHR;
      return &render_node_dirent;
   }

   if (dir == FAKE_DEV_DRI)
      return NULL;
   return readdir(dir);
}

static int
shim_closedir(DIR *dir)
{
   pthread_mutex_lock(&shim_lock);
   for (int i = 0; i < MAX_DRI_DIRS; i++) {
      if (dri_dirs[i] == dir)
         dri_dirs[i] = NULL;
   }
   pthread_mutex_unlock(&shim_lock);

   if (dir == FAKE_DEV_DRI)
      return 0;
   return closedir(dir);
}

static int
shim_ioctl(int fd, unsigned long request, ...)
{
   va_list ap;
   va_start(ap, request);
   void *arg = va_arg(ap, void *);
   va_end(ap);

   if (!inited || !drm_shim_fd_lookup(fd))
      return ioctl(fd, request, arg);

   if (request == DRM_IOCTL_GET_PCIINFO) {
      memcpy(arg, &shim_pciinfo, sizeof(shim_pciinfo));
      return 0;
   }
   return drm_shim_ioctl(fd, request, arg);
}

static int
shim_fcntl(int fd, int cmd, ...)
{
   va_list ap;
   va_start(ap, cmd);
   void *arg = va_arg(ap, void *);
   va_end(ap);

   int ret = fcntl(fd, cmd, arg);

   if (ret >= 0 && inited && (cmd == F_DUPFD || cmd == F_DUPFD_CLOEXEC)) {
      struct shim_fd *shim_fd = drm_shim_fd_lookup(fd);
      if (shim_fd)
         drm_shim_fd_register(ret, shim_fd);
   }
   return ret;
}

static int
shim_dup(int fd)
{
   int ret = dup(fd);
   if (ret >= 0 && inited) {
      struct shim_fd *shim_fd = drm_shim_fd_lookup(fd);
      if (shim_fd)
         drm_shim_fd_register(ret, shim_fd);
   }
   return ret;
}

static void *
shim_mmap(void *addr, size_t length, int prot, int flags, int fd, off_t offset)
{
   if (inited && fd >= 0) {
      struct shim_fd *shim_fd = drm_shim_fd_lookup(fd);
      if (shim_fd)
         return drm_shim_mmap(shim_fd, length, prot, flags, fd, offset);
   }
   return mmap(addr, length, prot, flags, fd, offset);
}

#define INTERPOSE(replacement, replacee)                                       \
   __attribute__((used)) static const struct {                                 \
      const void *r;                                                           \
      const void *o;                                                           \
   } interpose_##replacee __attribute__((section("__DATA,__interpose"))) = {   \
      (const void *)(unsigned long)&replacement,                               \
      (const void *)(unsigned long)&replacee}

INTERPOSE(shim_open, open);
INTERPOSE(shim_close, close);
INTERPOSE(shim_access, access);
INTERPOSE(shim_stat, stat);
INTERPOSE(shim_lstat, lstat);
INTERPOSE(shim_fstat, fstat);
INTERPOSE(shim_opendir, opendir);
INTERPOSE(shim_readdir, readdir);
INTERPOSE(shim_closedir, closedir);
INTERPOSE(shim_ioctl, ioctl);
INTERPOSE(shim_fcntl, fcntl);
INTERPOSE(shim_dup, dup);
INTERPOSE(shim_mmap, mmap);
