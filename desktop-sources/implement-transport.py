from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port'); f=r/'libdrm/xf86drm.c';s=f.read_text()
a=s.index('drm_public int drmNmxIoctl(int fd, unsigned long request, void *arg)');b=s.index('\n/* the node the IOKit',a)
s=s[:a]+'''/* Test-only, process-scoped route selection. Handles stay on one DRM file. */
static unsigned long long nmx_direct_calls, nmx_iokit_calls;
static int nmx_test_route(void)
{
    const char *s = getenv("NMX_DRM_TEST_TRANSPORT");
    if (!s) return 0;
    if (!strcmp(s,"direct")) return 1;
    if (!strcmp(s,"iokit")) return 2;
    return -1;
}
__attribute__((destructor)) static void nmx_test_report(void)
{
    if (getenv("NMX_DRM_TEST_TRANSPORT"))
        fprintf(stderr,"NMX transport counters: requested=%s direct=%llu iokit=%llu\\n",
            getenv("NMX_DRM_TEST_TRANSPORT"),
            __atomic_load_n(&nmx_direct_calls,__ATOMIC_RELAXED),
            __atomic_load_n(&nmx_iokit_calls,__ATOMIC_RELAXED));
}
drm_public int drmNmxIoctl(int fd, unsigned long request, void *arg)
{
    const int route = nmx_test_route();
    if (route < 0) { errno=EINVAL; return -1; }
    io_connect_t conn = nmx_uc_get(fd, 0);
    if (route == 1 && conn) { errno=EXDEV; return -1; }
    if (route == 2 && !conn) { errno=EXDEV; return -1; }
    if (!conn) {
        __atomic_fetch_add(&nmx_direct_calls,1,__ATOMIC_RELAXED);
        int ret = ioctl(fd, request, arg);
        if (route == 1 || ret == 0 || errno != EPERM) return ret;
        conn = nmx_uc_get(fd, 1);
        if (!conn) { errno = EPERM; return -1; }
    }
    __atomic_fetch_add(&nmx_iokit_calls,1,__ATOMIC_RELAXED);
    return nmx_uc_call(conn, request, arg);
}
''' +s[b:]
old='''    int fd = open(path, flags);

    if (fd >= 0 || (errno != EPERM && errno != EACCES))'''
new='''    const int route = nmx_test_route();
    if (route < 0) { errno=EINVAL; return -1; }
    if (!strcmp(path, NMX_UC_NODE) && route == 2)
        return nmx_token_open(flags & O_CLOEXEC);
    int fd = open(path, flags);
    if (route == 1) return fd;

    if (fd >= 0 || (errno != EPERM && errno != EACCES))'''
assert old in s;s=s.replace(old,new,1);f.write_text(s)
f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text();s=s.replace('if (host_visible && size <= NVMTL_POOL_MAX && pool_buffer_create(size, out) == 0)', 'if (host_visible && host_visible != 3 && size <= NVMTL_POOL_MAX && pool_buffer_create(size, out) == 0)',1);s=s.replace('if (bpark_take(size, host_visible, out) == 0)', 'if (host_visible != 3 && bpark_take(size, host_visible, out) == 0)',1);s=s.replace('owned ? nvmtl_vk_buffer_create(plan.bytes, 1, &stage)', 'owned ? nvmtl_vk_buffer_create(plan.bytes, 3, &stage)',1);f.write_text(s)
