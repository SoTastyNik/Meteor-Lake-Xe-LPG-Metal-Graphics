/*
 * VtdOff.efi - OpenCore UEFI driver for the HUAWEI MateBook 14 (Core Ultra 5 125H).
 *
 * The firmware DMAR sets INTR_REMAP and DMA_CTRL_PLATFORM_OPT_IN, and the firmware runs the CPUs in x2APIC mode.
 * Under macOS (DMAR dropped, so XNU never touches VT-d) the devices behave as if their interrupts never arrive:
 * a USB mouse only works if it is present at boot and then crawls, hot-plug is never seen, the NVMe times out on its
 * first admin command (Identify) and the USB stick is reset at the same moment. That is what MSIs blocked by an
 * interrupt-remapping unit that the OS does not know about look like.
 *
 * Real Macs hand macOS VT-d with translation and remapping off, so at ExitBootServices this driver turns off DMA
 * translation (TE) and interrupt remapping (IRE) in both remapping units of this laptop's DMAR (DRHD 0xFC800000 and
 * 0xFC801000, VT-d spec 11.4.4 GCMD/GSTS). A unit whose version register reads as all ones is skipped. The register
 * state found at load time is published as the volatile variable
 * 4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:VtdOffReport, which `nvram -p` shows under macOS.
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
typedef struct { EFI_TABLE_HEADER Hdr; void *fn[14]; } EFI_RUNTIME_SERVICES;
typedef struct {
    EFI_TABLE_HEADER Hdr;
    CHAR16 *FirmwareVendor;
    u32 FirmwareRevision;
    EFI_HANDLE ConsoleInHandle; void *ConIn;
    EFI_HANDLE ConsoleOutHandle; void *ConOut;
    EFI_HANDLE StandardErrorHandle; void *StdErr;
    EFI_RUNTIME_SERVICES *RuntimeServices;
    struct { EFI_TABLE_HEADER Hdr; void *fn[40]; } *BootServices;
} EFI_SYSTEM_TABLE;

/* EFI_BOOT_SERVICES / EFI_RUNTIME_SERVICES function slots after the header */
enum { BS_CREATE_EVENT = 7, RT_SET_VARIABLE = 8 };
#define EVT_SIGNAL_EXIT_BOOT_SERVICES 0x00000201u
#define TPL_NOTIFY 16
#define VAR_BS_RT 0x6u   /* volatile, boot service + runtime access */

/* VT-d remapping unit registers (VT-d spec 11.4) */
#define VTD_VER 0x00
#define VTD_GCMD 0x18
#define VTD_GSTS 0x1c
#define GSTS_TES (1u << 31)
#define GSTS_IRES (1u << 25)
/* one-shot command bits that must not be written back from GSTS: SRTP, SFL, WBF, SIRTP */
#define GCMD_ONE_SHOT ((1u << 30) | (1u << 29) | (1u << 27) | (1u << 24))

static const u64 units[] = {0xfc800000ull, 0xfc801000ull};
#define NUNITS (sizeof units / sizeof units[0])

static EFI_GUID ReportGuid = {0x4d1fda02, 0x38c7, 0x4a6a, {0x9c, 0xc6, 0x4b, 0xcc, 0xa8, 0xb3, 0x01, 0x02}};

static u32 rd32(u64 base, u32 off) { return *(volatile u32 *)(base + off); }
static void wr32(u64 base, u32 off, u32 v) { *(volatile u32 *)(base + off) = v; }

/* clear one persistent GCMD bit and wait (bounded) for GSTS to follow */
static void vtd_clear(u64 base, u32 bit)
{
    u32 sts = rd32(base, VTD_GSTS);
    if (!(sts & bit)) return;
    wr32(base, VTD_GCMD, (sts & ~GCMD_ONE_SHOT) & ~bit);
    for (u32 i = 0; i < 10000000u && (rd32(base, VTD_GSTS) & bit); i++)
        __asm__ volatile("pause");
}

static int done;

static void __attribute__((ms_abi)) on_exit_boot_services(EFI_EVENT e, void *ctx)
{
    (void)e; (void)ctx;
    if (done) return;
    done = 1;
    for (UINTN i = 0; i < NUNITS; i++) {
        if (rd32(units[i], VTD_VER) == 0xffffffffu) continue;
        vtd_clear(units[i], GSTS_IRES);   /* interrupt remapping first, as Linux does on shutdown */
        vtd_clear(units[i], GSTS_TES);
    }
}

static char report[256];
static UINTN rlen;
static void put(const char *s) { while (*s && rlen < sizeof report - 1) report[rlen++] = *s++; }
static void puthex(u64 v, int digits)
{
    put("0x");
    for (int i = digits - 1; i >= 0; i--) { char c[2] = {"0123456789abcdef"[(v >> (4 * i)) & 15], 0}; put(c); }
}

EFI_STATUS __attribute__((ms_abi)) efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *st)
{
    (void)image;
    put("VtdOff 1.0");
    for (UINTN i = 0; i < NUNITS; i++) {
        u32 ver = rd32(units[i], VTD_VER), sts = ver == 0xffffffffu ? 0 : rd32(units[i], VTD_GSTS);
        put("; "); puthex(units[i], 8); put(" ver="); puthex(ver, 8); put(" gsts="); puthex(sts, 8);
        put(sts & GSTS_TES ? " TE" : ""); put(sts & GSTS_IRES ? " IRE" : "");
    }

    typedef EFI_STATUS (*SetVariable_t)(CHAR16 *, EFI_GUID *, u32, UINTN, void *) __attribute__((ms_abi));
    static CHAR16 name[] = u"VtdOffReport";
    ((SetVariable_t)st->RuntimeServices->fn[RT_SET_VARIABLE])(name, &ReportGuid, VAR_BS_RT, rlen, report);

    typedef EFI_STATUS (*CreateEvent_t)(u32, UINTN, void *, void *, EFI_EVENT *) __attribute__((ms_abi));
    EFI_EVENT ev;
    ((CreateEvent_t)st->BootServices->fn[BS_CREATE_EVENT])(EVT_SIGNAL_EXIT_BOOT_SERVICES, TPL_NOTIFY,
                                                           (void *)on_exit_boot_services, 0, &ev);
    return 0;
}
