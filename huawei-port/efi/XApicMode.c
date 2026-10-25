/*
 * XApicMode.efi - OpenCore UEFI driver for the HUAWEI MateBook 14 (Core Ultra 5 125H).
 *
 * The firmware hands the CPUs to the OS in x2APIC mode (its MADT carries only x2APIC entries). XNU keeps whatever
 * mode the BSP is in (osfmk/i386/lapic_native.c lapic_init: is_x2apic = APIC_BASE.EXTD; no boot-arg can switch an
 * already-enabled x2APIC back), and its x2APIC path is only exercised under hypervisors. On this laptop Sequoia
 * panics bringing up the application processors (mp_rv_action / intel_startCPU) with any CPU subset.
 *
 * Real Macs boot in xAPIC mode, so this driver returns the BSP to xAPIC at ExitBootServices, after the firmware
 * is done with its own APIC use. XNU's lapic_configure then moves every AP to xAPIC as it starts it.
 * Nothing is changed when x2APIC is locked (IA32_XAPIC_DISABLE_STATUS.LEGACY_XAPIC_DISABLED): leaving x2APIC there
 * would #GP. The decision is written to \HuaweiApicMode.txt on the volume the driver was loaded from.
 */
typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef u64 UINTN;
typedef UINTN EFI_STATUS;
typedef void *EFI_HANDLE;
typedef void *EFI_EVENT;
typedef u16 CHAR16;
typedef struct { u32 a; u16 b, c; u8 d[8]; } EFI_GUID;
typedef struct { u64 Signature; u32 Revision, HeaderSize, CRC32, Reserved; } EFI_TABLE_HEADER;
typedef struct { void *Reset; EFI_STATUS (*OutputString)(void *, CHAR16 *); } TEXT_OUT;
typedef struct {
    EFI_TABLE_HEADER Hdr;
    CHAR16 *FirmwareVendor;
    u32 FirmwareRevision;
    EFI_HANDLE ConsoleInHandle; void *ConIn;
    EFI_HANDLE ConsoleOutHandle; TEXT_OUT *ConOut;
    EFI_HANDLE StandardErrorHandle; void *StdErr;
    void *RuntimeServices;
    struct { EFI_TABLE_HEADER Hdr; void *fn[40]; } *BootServices;
} EFI_SYSTEM_TABLE;
typedef struct { u32 Revision; EFI_HANDLE ParentHandle; EFI_SYSTEM_TABLE *SystemTable; EFI_HANDLE DeviceHandle; } LOADED_IMAGE;
typedef struct FILE FILE;
struct FILE {
    u64 Revision;
    EFI_STATUS (*Open)(FILE *, FILE **, CHAR16 *, u64, u64);
    EFI_STATUS (*Close)(FILE *);
    EFI_STATUS (*Delete)(FILE *);
    void *Read;
    EFI_STATUS (*Write)(FILE *, UINTN *, void *);
};
typedef struct { u64 Revision; EFI_STATUS (*OpenVolume)(void *, FILE **); } SIMPLE_FS;

/* EFI_BOOT_SERVICES function slots after the header */
enum { BS_CREATE_EVENT = 7, BS_HANDLE_PROTOCOL = 16 };
#define EVT_SIGNAL_EXIT_BOOT_SERVICES 0x00000201u
#define TPL_NOTIFY 16
#define MSR_APIC_BASE 0x1b
#define MSR_ARCH_CAPABILITIES 0x10a
#define MSR_XAPIC_DISABLE_STATUS 0xbd
#define APIC_BASE_EXTD (1ull << 10)
#define APIC_BASE_EN (1ull << 11)

static EFI_GUID LoadedImageGuid = {0x5b1b31a1, 0x9562, 0x11d2, {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static EFI_GUID SimpleFsGuid = {0x964e5b22, 0x6459, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};

static u64 rdmsr(u32 msr) { u32 lo, hi; __asm__ volatile("rdmsr" : "=a"(lo), "=d"(hi) : "c"(msr)); return ((u64)hi << 32) | lo; }
static void wrmsr(u32 msr, u64 v) { __asm__ volatile("wrmsr" :: "c"(msr), "a"((u32)v), "d"((u32)(v >> 32)) : "memory"); }
static void cpuid(u32 leaf, u32 sub, u32 r[4]) { __asm__ volatile("cpuid" : "=a"(r[0]), "=b"(r[1]), "=c"(r[2]), "=d"(r[3]) : "a"(leaf), "c"(sub)); }

static int switch_allowed;   /* decided once at load: x2APIC active and not locked */
static int switched;

static void __attribute__((ms_abi)) on_exit_boot_services(EFI_EVENT e, void *ctx)
{
    (void)e; (void)ctx;
    if (!switch_allowed || switched) return;
    u64 base = rdmsr(MSR_APIC_BASE);
    if (!(base & APIC_BASE_EXTD)) return;
    /* x2APIC -> xAPIC requires passing through the disabled state (SDM 10.12.5) */
    wrmsr(MSR_APIC_BASE, base & ~(APIC_BASE_EN | APIC_BASE_EXTD));
    wrmsr(MSR_APIC_BASE, (base & ~APIC_BASE_EXTD) | APIC_BASE_EN);
    switched = 1;
}

/* tiny ASCII formatting into a fixed buffer */
static char report[512];
static UINTN rlen;
static void put(const char *s) { while (*s && rlen < sizeof report - 1) report[rlen++] = *s++; }
static void puthex(u64 v) { char b[19]; b[0] = '0'; b[1] = 'x'; for (int i = 0; i < 16; i++) b[2 + i] = "0123456789abcdef"[(v >> (60 - 4 * i)) & 15]; b[18] = 0; put(b); }

static void write_report(EFI_HANDLE image, EFI_SYSTEM_TABLE *st)
{
    typedef EFI_STATUS (*HandleProtocol_t)(EFI_HANDLE, EFI_GUID *, void **) __attribute__((ms_abi));
    HandleProtocol_t hp = (HandleProtocol_t)st->BootServices->fn[BS_HANDLE_PROTOCOL];
    LOADED_IMAGE *li = 0; SIMPLE_FS *fs = 0; FILE *root = 0, *f = 0;
    static CHAR16 name[] = u"\\HuaweiApicMode.txt";
    if (hp(image, &LoadedImageGuid, (void **)&li) || !li) return;
    if (hp(li->DeviceHandle, &SimpleFsGuid, (void **)&fs) || !fs) return;
    typedef EFI_STATUS (*OpenVolume_t)(void *, FILE **) __attribute__((ms_abi));
    if (((OpenVolume_t)fs->OpenVolume)(fs, &root) || !root) return;
    typedef EFI_STATUS (*Open_t)(FILE *, FILE **, CHAR16 *, u64, u64) __attribute__((ms_abi));
    typedef EFI_STATUS (*Close_t)(FILE *) __attribute__((ms_abi));
    typedef EFI_STATUS (*Write_t)(FILE *, UINTN *, void *) __attribute__((ms_abi));
    /* recreate the file so an older, longer report does not leave trailing text */
    if (!((Open_t)root->Open)(root, &f, name, 3, 0) && f) ((Close_t)f->Delete)(f);
    f = 0;
    if (!((Open_t)root->Open)(root, &f, name, 0x8000000000000003ull, 0) && f) {
        UINTN n = rlen;
        ((Write_t)f->Write)(f, &n, report);
        ((Close_t)f->Close)(f);
    }
    ((Close_t)root->Close)(root);
}

EFI_STATUS __attribute__((ms_abi)) efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *st)
{
    u32 r[4];
    u64 base = rdmsr(MSR_APIC_BASE), arch = 0, xdis = 0;
    int locked = 0;
    cpuid(7, 0, r);
    if (r[3] & (1u << 29)) {                     /* IA32_ARCH_CAPABILITIES enumerated */
        arch = rdmsr(MSR_ARCH_CAPABILITIES);
        if (arch & (1ull << 21)) {               /* XAPIC_DISABLE_STATUS MSR present */
            xdis = rdmsr(MSR_XAPIC_DISABLE_STATUS);
            locked = (int)(xdis & 1);            /* LEGACY_XAPIC_DISABLED */
        }
    }
    int x2apic = (base & APIC_BASE_EXTD) != 0;
    switch_allowed = x2apic && !locked;

    put("XApicMode 1.0\r\nAPIC_BASE="); puthex(base);
    put(x2apic ? " (x2APIC)" : " (xAPIC)");
    put("\r\nARCH_CAPABILITIES="); puthex(arch);
    put("\r\nXAPIC_DISABLE_STATUS="); puthex(xdis);
    put(locked ? " (x2APIC LOCKED)" : "");
    put("\r\nAction: ");
    put(switch_allowed ? "BSP x2APIC -> xAPIC at ExitBootServices\r\n"
                       : (x2apic ? "none: x2APIC is locked by the platform\r\n" : "none: already xAPIC\r\n"));
    write_report(image, st);

    if (switch_allowed) {
        typedef EFI_STATUS (*CreateEvent_t)(u32, UINTN, void *, void *, EFI_EVENT *) __attribute__((ms_abi));
        EFI_EVENT ev;
        ((CreateEvent_t)st->BootServices->fn[BS_CREATE_EVENT])(EVT_SIGNAL_EXIT_BOOT_SERVICES, TPL_NOTIFY,
                                                               (void *)on_exit_boot_services, 0, &ev);
    }
    return 0;
}
