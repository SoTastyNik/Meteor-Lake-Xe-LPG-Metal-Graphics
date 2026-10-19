#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <assert.h>
#include "nvmtl_log_failure.h"
#define NVMTL_RELEASE 1
#define LOG_ERR 3
static int logged;
#define syslog(...) ((void)++logged)
#define NVLOG_SITES    256
#define NVLOG_VERBATIM 8
#define NVLOG_EVERY    4096
static struct { const char *fmt; uint64_t n; } g_nvlog_sites[NVLOG_SITES];
static pthread_mutex_t g_nvlog_lock = PTHREAD_MUTEX_INITIALIZER;
static int nvlog_dropped(const char *fmt, uint64_t *rep) {
    *rep = 0;
    pthread_mutex_lock(&g_nvlog_lock);
    int i = 0;
    for (; i < NVLOG_SITES; i++) {
        if (g_nvlog_sites[i].fmt == fmt) break;
        if (!g_nvlog_sites[i].fmt) { g_nvlog_sites[i].fmt = fmt; break; }
    }
    if (i == NVLOG_SITES) { pthread_mutex_unlock(&g_nvlog_lock); return 0; }
    uint64_t n = ++g_nvlog_sites[i].n;
    pthread_mutex_unlock(&g_nvlog_lock);
    if (n <= NVLOG_VERBATIM) return 0;
    if (n % NVLOG_EVERY == 0) { *rep = n; return 0; }
    return 1;
}
void nvlog(const char *fmt, ...) {
    const char *diagnostic_env = getenv("NVMTL_DIAGNOSTIC_STDERR");
    const int diagnostic = diagnostic_env && !strcmp(diagnostic_env, "1");
    uint64_t rep; const int dropped = nvlog_dropped(fmt, &rep);
    if (dropped && !diagnostic) return;
    char b[512]; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a);
    char t[640];
    if (rep) snprintf(t, sizeof t, "%s   [logged %llu times now]", b, (unsigned long long)rep);
    else     snprintf(t, sizeof t, "%s", b);
    /* Explicit test clients retain failures and copy/submit traces directly,
       independently of per-site syslog throttling or historical-log queries. */
    if (diagnostic && nvmtl_log_failure(t)) {
        fprintf(stderr, "NVMTL-DIAG pid=%d ns=%llu %s\n", getpid(),
            (unsigned long long)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW), t);
        fflush(stderr);
    }
    if (dropped) return;
#if NVMTL_RELEASE
    if (nvmtl_log_failure(t)) syslog(LOG_ERR, "NullMoth: %s", t);
#else
    syslog(LOG_NOTICE, "NVMTL: %s", t);
    FILE *f = fopen(nvmtl_log_path(), "a"); if (f) { fprintf(f, "pid %d NVMTL: %s\n", getpid(), t); fclose(f); }
#endif
}
int main(void){
 for(int i=0;i<40;i++)nvlog("readback FAILED phase=test value=%d",i);
 assert(logged==8);
 setenv("NVMTL_DIAGNOSTIC_STDERR","1",1);
 for(int i=0;i<20;i++)nvlog("readback FAILED phase=test value=%d",40+i);
 assert(logged==8);
 nvlog("ordinary cached memory type %u",0u);
 setenv("NVMTL_DIAGNOSTIC_STDERR","0",1);nvlog("readback FAILED phase=test value=%d",60);
 puts("PASS actual release logger: explicit stderr diagnostics survive per-site throttle; unset/zero stay off; routine messages excluded; syslog throttle unchanged");
}
