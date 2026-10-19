from pathlib import Path
f=Path('/Users/ved/Documents/iGPU Port/libdrm/xf86drm.c');s=f.read_text()
needle='static int drm_darwin_sandbox_devices(uint32_t flags, drmDevicePtr devices[], int max_devices);'
s=s.replace(needle,needle+'\nstatic int nmx_test_route(void);\nstatic int drm_darwin_token_type(int fd);',1)
needle='''drm_public int drmGetNodeTypeFromFd(int fd)
{
    struct stat sbuf;'''
s=s.replace(needle,'''drm_public int drmGetNodeTypeFromFd(int fd)
{
#ifdef __APPLE__
    if (drm_darwin_token_type(fd) == DRM_NODE_RENDER)
        return DRM_NODE_RENDER;
#endif
    struct stat sbuf;''',1)
needle='''    sysdir = opendir(DRM_DIR_NAME);
#ifdef __APPLE__
    if (!sysdir && (errno == EPERM || errno == EACCES))'''
replace='''#ifdef __APPLE__
    /* Select the same transport for discovery and rendering. A forced IOKit
     * process must not enumerate through temporary devfs descriptors. */
    const int route = nmx_test_route();
    if (route < 0) return -EINVAL;
    if (route == 2)
        return drm_darwin_sandbox_devices(flags, devices, max_devices);
#endif
    sysdir = opendir(DRM_DIR_NAME);
#ifdef __APPLE__
    if (!sysdir && route != 1 && (errno == EPERM || errno == EACCES))'''
assert needle in s;s=s.replace(needle,replace,1)
needle='''    closedir(sysdir);

    if (devices != NULL)
        return MIN2(device_count, max_devices);'''
replace='''    closedir(sysdir);
#ifdef __APPLE__
    /* Directory access can succeed while individual node queries are denied. */
    if (device_count == 0 && route == 0) {
        ret = drm_darwin_sandbox_devices(flags, devices, max_devices);
        if (ret > 0) return ret;
    }
#endif
    if (devices != NULL)
        return MIN2(device_count, max_devices);'''
assert needle in s;s=s.replace(needle,replace,1)
needle='static int drm_darwin_token_device(int fd, uint32_t flags, drmDevicePtr *device)\n{'
a=s.index(needle);b=s.index('\n/* the NullMoth DRM node ioctls',a)
s=s[:a]+'''static int drm_darwin_token_type(int fd)
{
    io_connect_t conn = nmx_uc_get(fd, 0);
    struct nmx_uc *u;
    bool token = false;
    if (!conn) return -1;
    pthread_mutex_lock(&nmx_ucs_lock);
    for (u = nmx_ucs; u != NULL; u = u->next)
        if (u->fd == fd && u->conn == conn) token = u->token;
    pthread_mutex_unlock(&nmx_ucs_lock);
    return token ? DRM_NODE_RENDER : -1;
}

static int drm_darwin_token_device(int fd, uint32_t flags, drmDevicePtr *device)
{
    (void)flags;
    if (drm_darwin_token_type(fd) != DRM_NODE_RENDER) return -ENOENT;
    io_connect_t conn = nmx_uc_get(fd, 0);
    return conn ? drm_darwin_uc_device(conn, device) : -ENOENT;
}
''' +s[b:]
# Emit diagnostic details for transport failure without depending on a syslog filter.
s=s.replace('''        errno = EIO;
        return -1;
    }
    if (err) {''','''        os_log_error(nmx_log(), "ioctl 0x%{public}lx transport failure: kr=0x%{public}x output-count=%{public}u", request, kr, nout);
        errno = EIO;
        return -1;
    }
    if (err) {''',1)
f.write_text(s)
