/*
 * MtlDiag.efi - read-only OpenCore UEFI driver for the HUAWEI MateBook 14 (Core Ultra 5 125H).
 *
 * Under macOS no fixed-vector interrupt reaches a CPU: device interrupts (mouse, PS/2 keyboard, NVMe completion,
 * USB hot-plug) are lost, and with two CPUs IOPCIConfigurator hangs in mp_rendezvous_no_intrs (the IPI to the
 * second CPU is never answered). INIT/SIPI still start the APs. This driver changes nothing; it records the
 * interrupt-related CPU and VT-d state the firmware leaves behind and writes it to \MtlDiag.txt on every FAT volume
 * that carries \EFI\OC\OpenCore.efi (the OpenCore USB), so it can be read from Windows.
 */
typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef u64 UINTN;
typedef UINTN EFI_STATUS;
typedef void *EFI_HANDLE;
typedef u16 CHAR16;
typedef struct { u32 a; u16 b, c; u8 d[8]; } EFI_GUID;
typedef struct { u64 Signature; u32 Revision, HeaderSize, CRC32, Reserved; } EFI_TABLE_HEADER;
typedef struct {
    EFI_TABLE_HEADER Hdr;
    CHAR16 *FirmwareVendor;
    u32 FirmwareRevision;
    EFI_HANDLE ConsoleInHandle; void *ConIn;
    EFI_HANDLE ConsoleOutHandle; void *ConOut;
    EFI_HANDLE StandardErrorHandle; void *StdErr;
    void *RuntimeServices;
    struct { EFI_TABLE_HEADER Hdr; void *fn[44]; } *BootServices;
} EFI_SYSTEM_TABLE;
typedef struct FILE FILE;
struct FILE {
    u64 Revision;
    void *Open, *Close, *Delete, *Read, *Write;
};
typedef struct { u64 Revision; void *OpenVolume; } SIMPLE_FS;

/* EFI_BOOT_SERVICES function slots after the header */
enum { BS_HANDLE_PROTOCOL = 16, BS_LOCATE_HANDLE = 19 };
#define BY_PROTOCOL 2

#define MSR_APIC_BASE 0x1b
#define MSR_ARCH_CAPABILITIES 0x10a
#define MSR_XAPIC_DISABLE_STATUS 0xbd
#define MSR_X2APIC_ID 0x802
#define MSR_X2APIC_TPR 0x808
#define MSR_X2APIC_PPR 0x80a
#define MSR_X2APIC_LDR 0x80d
#define MSR_X2APIC_SVR 0x80f
#define MSR_X2APIC_LVT_TIMER 0x832
#define XAPIC_MMIO 0xfee00000ull

static EFI_GUID SimpleFsGuid = {0x964e5b22, 0x6459, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};

static u64 rdmsr(u32 msr) { u32 lo, hi; __asm__ volatile("rdmsr" : "=a"(lo), "=d"(hi) : "c"(msr)); return ((u64)hi << 32) | lo; }
static void cpuid(u32 leaf, u32 sub, u32 r[4]) { __asm__ volatile("cpuid" : "=a"(r[0]), "=b"(r[1]), "=c"(r[2]), "=d"(r[3]) : "a"(leaf), "c"(sub)); }
static u32 rd32(u64 a) { return *(volatile u32 *)a; }

static char report[1536];
static UINTN rlen;
static void put(const char *s) { while (*s && rlen < sizeof report - 1) report[rlen++] = *s++; }
static void hex(u64 v, int digits)
{
    put("0x");
    for (int i = digits - 1; i >= 0; i--) { char c[2] = {"0123456789abcdef"[(v >> (4 * i)) & 15], 0}; put(c); }
}
static void line(const char *k, u64 v, int digits) { put(k); put("="); hex(v, digits); put("\r\n"); }

static void collect(void)
{
    u32 r[4];
    u64 base = rdmsr(MSR_APIC_BASE), arch = 0, xdis = 0;
    put("MtlDiag 1.0 (firmware state when OpenCore loads its drivers)\r\n");
    line("IA32_APIC_BASE", base, 16);
    put((base & (1ull << 10)) ? "  mode: x2APIC\r\n" : ((base & (1ull << 11)) ? "  mode: xAPIC\r\n" : "  mode: APIC disabled\r\n"));
    put((base & (1ull << 8)) ? "  this CPU is the BSP\r\n" : "  this CPU is NOT the BSP\r\n");
    cpuid(7, 0, r);
    if (r[3] & (1u << 29)) {
        arch = rdmsr(MSR_ARCH_CAPABILITIES);
        line("IA32_ARCH_CAPABILITIES", arch, 16);
        if (arch & (1ull << 21)) {
            xdis = rdmsr(MSR_XAPIC_DISABLE_STATUS);
            line("IA32_XAPIC_DISABLE_STATUS", xdis, 16);
            put((xdis & 1) ? "  x2APIC LOCKED (legacy xAPIC disabled)\r\n" : "  x2APIC not locked\r\n");
        }
    }
    cpuid(1, 0, r);
    line("CPUID.1 EBX[31:24] initial APIC ID", r[1] >> 24, 2);
    line("CPUID.1 ECX (bit21 = x2APIC)", r[2], 8);
    cpuid(0xb, 0, r);
    line("CPUID.B EDX x2APIC ID", r[3], 8);
    cpuid(0x1f, 0, r);
    line("CPUID.1F.0 EAX/EBX", ((u64)r[0] << 32) | r[1], 16);
    if (base & (1ull << 10)) {
        line("x2APIC ID", rdmsr(MSR_X2APIC_ID), 8);
        line("x2APIC LDR", rdmsr(MSR_X2APIC_LDR), 8);
        line("x2APIC TPR", rdmsr(MSR_X2APIC_TPR), 8);
        line("x2APIC PPR", rdmsr(MSR_X2APIC_PPR), 8);
        line("x2APIC SVR (bit8 = enabled)", rdmsr(MSR_X2APIC_SVR), 8);
        line("x2APIC LVT timer", rdmsr(MSR_X2APIC_LVT_TIMER), 8);
    } else if (base & (1ull << 11)) {
        u64 mm = base & 0xfffff000ull;
        line("xAPIC ID", rd32(mm + 0x20), 8);
        line("xAPIC LDR", rd32(mm + 0xd0), 8);
        line("xAPIC DFR", rd32(mm + 0xe0), 8);
        line("xAPIC TPR", rd32(mm + 0x80), 8);
        line("xAPIC SVR (bit8 = enabled)", rd32(mm + 0xf0), 8);
    }
    static const u64 units[] = {0xfc800000ull, 0xfc801000ull};
    for (int i = 0; i < 2; i++) {
        u32 ver = rd32(units[i]);
        put("VT-d unit "); hex(units[i], 8); put(": ");
        if (ver == 0xffffffffu) { put("absent\r\n"); continue; }
        u64 ecap = ((u64)rd32(units[i] + 0x14) << 32) | rd32(units[i] + 0x10);
        u32 gsts = rd32(units[i] + 0x1c);
        put("ver="); hex(ver, 8); put(" ecap="); hex(ecap, 16); put(" gsts="); hex(gsts, 8);
        put((gsts >> 31) & 1 ? " TE" : ""); put((gsts >> 26) & 1 ? " QIE" : "");
        put((gsts >> 25) & 1 ? " IRE" : ""); put((gsts >> 23) & 1 ? " CFIS" : "");
        put((ecap >> 3) & 1 ? " [IR supported" : " [no IR"); put((ecap >> 4) & 1 ? ", EIM]" : "]");
        put("\r\n");
        if ((gsts >> 25) & 1) {
            u64 irta = ((u64)rd32(units[i] + 0xbc) << 32) | rd32(units[i] + 0xb8);
            put("  IRTA="); hex(irta, 16); put((irta >> 11) & 1 ? " (EIME x2APIC format)\r\n" : "\r\n");
        }
    }
}

typedef EFI_STATUS (*HandleProtocol_t)(EFI_HANDLE, EFI_GUID *, void **) __attribute__((ms_abi));
typedef EFI_STATUS (*LocateHandle_t)(u32, EFI_GUID *, void *, UINTN *, EFI_HANDLE *) __attribute__((ms_abi));
typedef EFI_STATUS (*OpenVolume_t)(void *, FILE **) __attribute__((ms_abi));
typedef EFI_STATUS (*Open_t)(FILE *, FILE **, CHAR16 *, u64, u64) __attribute__((ms_abi));
typedef EFI_STATUS (*Close_t)(FILE *) __attribute__((ms_abi));
typedef EFI_STATUS (*Write_t)(FILE *, UINTN *, void *) __attribute__((ms_abi));

static void write_everywhere(EFI_SYSTEM_TABLE *st)
{
    static EFI_HANDLE handles[64];
    static CHAR16 marker[] = u"\\EFI\\OC\\OpenCore.efi";
    static CHAR16 name[] = u"\\MtlDiag.txt";
    UINTN size = sizeof handles;
    HandleProtocol_t hp = (HandleProtocol_t)st->BootServices->fn[BS_HANDLE_PROTOCOL];
    if (((LocateHandle_t)st->BootServices->fn[BS_LOCATE_HANDLE])(BY_PROTOCOL, &SimpleFsGuid, 0, &size, handles))
        return;
    for (UINTN i = 0; i < size / sizeof(EFI_HANDLE); i++) {
        SIMPLE_FS *fs = 0; FILE *root = 0, *f = 0;
        if (hp(handles[i], &SimpleFsGuid, (void **)&fs) || !fs) continue;
        if (((OpenVolume_t)fs->OpenVolume)(fs, &root) || !root) continue;
        if (!((Open_t)root->Open)(root, &f, marker, 1, 0) && f) {
            ((Close_t)f->Close)(f);
            f = 0;
            /* recreate so an older, longer report leaves no trailing text */
            if (!((Open_t)root->Open)(root, &f, name, 3, 0) && f) ((Close_t)f->Delete)(f);
            f = 0;
            if (!((Open_t)root->Open)(root, &f, name, 0x8000000000000003ull, 0) && f) {
                UINTN n = rlen;
                ((Write_t)f->Write)(f, &n, report);
                ((Close_t)f->Close)(f);
            }
        }
        ((Close_t)root->Close)(root);
    }
}

EFI_STATUS __attribute__((ms_abi)) efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *st)
{
    (void)image;
    collect();
    write_everywhere(st);
    return 0;
}
