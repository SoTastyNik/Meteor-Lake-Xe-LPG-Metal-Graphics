# fork_xe.py <xe-src>: the few places where Intel's 6.14 xe needs a macOS form. Everything else is Intel's file
# unchanged. Every anchor is exact with an asserted count, each file is rewritten atomically, and the script runs
# on a fresh copy of the pristine tree each build (all-xe.sh rsyncs xe-src first).
import os, sys
root = sys.argv[1]

def edit(name, pairs):
    p = os.path.join(root, name)
    t = open(p).read()
    for old, new, n in pairs:
        assert t.count(old) == n, (name, old[:70], t.count(old))
        t = t.replace(old, new)
    open(p + ".tmp", "w").write(t)
    os.replace(p + ".tmp", p)

def cut(name, start, end, replacement=""):
    p = os.path.join(root, name)
    t = open(p).read()
    assert t.count(start) == 1 and t.count(end) == 1, (name, start[:50])
    i, j = t.index(start), t.index(end)
    assert i < j
    t = t[:i] + replacement + t[j:]
    open(p + ".tmp", "w").write(t)
    os.replace(p + ".tmp", p)

# Resizable BAR: under macOS the PCI windows belong to IOPCIFamily and are fixed by the firmware/boot loader
# (OpenCore's ResizeAppleGpuBars) before the kernel starts, so the port uses the BAR as it finds it.
cut("xe_vram.c", "static void\n_resize_bar(struct xe_device *xe, int resno, resource_size_t size)\n",
    "static bool resource_is_valid(struct pci_dev *pdev, int bar)\n")
edit("xe_vram.c", [("\tresize_vram_bar(xe);\n", "\t/* the BAR stays the size the firmware gave it (see fork_xe.py) */\n", 1)])

# drm-kmod's drm_file keeps the opener's pid as a pid_t (no struct pid), and its TTM takes no address_space
# (amdgpu passes NULL on FreeBSD for the same reason).
edit("xe_device.c", [
    ("get_pid_task(rcu_access_pointer(file->pid), PIDTYPE_PID)", "get_pid_task(file->pid, PIDTYPE_PID)", 1),
    ("\t\t\t      xe->drm.anon_inode->i_mapping,\n", "\t\t\t      NULL,\n", 1),
])

# user fences and VM snapshots written/read by a worker thread in the owning process's memory: the port's form of
# kthread_use_mm + copy_*_user (nmx_mm_copy.c)
edit("xe_sync.c", [
    ("\t\tkthread_use_mm(ufence->mm);\n\t\tif (copy_to_user(ufence->addr, &ufence->value, sizeof(ufence->value)))\n",
     "\t\tif (nmx_mm_copy_to_user(ufence->mm, ufence->addr, &ufence->value, sizeof(ufence->value)))\n", 1),
    ("\t\tkthread_unuse_mm(ufence->mm);\n", "", 1),
])
edit("xe_vm.c", [
    ("\t\t\tkthread_use_mm(snap->snap[i].mm);\n\t\t\tif (!copy_from_user(snap->snap[i].data, userptr, snap->snap[i].len))\n",
     "\t\t\tif (!nmx_mm_copy_from_user(snap->snap[i].mm, snap->snap[i].data, userptr, snap->snap[i].len))\n", 1),
    ("\t\t\tkthread_unuse_mm(snap->snap[i].mm);\n", "", 1),
])

# LinuxKPI's ktime_get_*_ns return s64; xe's clock table holds u64 (*)(void). Same values, matching types.
edit("xe_query.c", [("\t\treturn &ktime_get_", "\t\treturn &nmx_ktime_get_", 5)])

# runtime-PM state is not tracked per device on macOS; this helper only silences a debug warning on Linux
edit("xe_pm.c", [
    ("\treturn dev->power.runtime_status == RPM_SUSPENDING ||\n\t\tdev->power.runtime_status == RPM_RESUMING ||\n"
     "\t\tpm_suspend_target_state != PM_SUSPEND_ON;\n",
     "\t(void)dev;\n\treturn false;\n", 1),
])

# no SR-IOV under macOS (pci_driver has no sriov_configure in LinuxKPI); the PF path is never entered
edit("xe_pci.c", [("\t.sriov_configure = xe_pci_sriov_configure,\n", "", 1)])
# every PCI bridge under macOS is driven by IOPCIFamily, so the "unbound bridge" case cannot arise
edit("xe_pm.c", [("\tif (!bridge->driver) {\n\t\tdrm_warn(&xe->drm, \"unbounded parent pci bridge, device won't support any PM support.\\n\");\n"
                  "\t\tdevice_set_pm_not_required(&pdev->dev);\n\t}\n",
                  "\t/* the bridge is IOPCIFamily's: always bound */\n", 1)])
# Panther Lake firmware: 6.14 xe probes PTL (when forced) but names no GuC/HuC blob for it; later Intel trees add
# xe/ptl_guc_70.bin and xe/ptl_huc.bin, which linux-firmware ships. The same minimum GuC version as LNL/BMG is used.
# PTL's GSC (release 105) is not added: 6.14's GSC code knows release 102/104 only, so HuC stays unauthenticated there.
edit("xe_uc_fw.c", [
    ("\tfw_def(BATTLEMAGE,\tmajor_ver(xe,\tguc,\tbmg,\t70, 29, 2))\t\\\n",
     "\tfw_def(PANTHERLAKE,\tmajor_ver(xe,\tguc,\tptl,\t70, 29, 2))\t\\\n\tfw_def(BATTLEMAGE,\tmajor_ver(xe,\tguc,\tbmg,\t70, 29, 2))\t\\\n", 1),
    ("\tfw_def(BATTLEMAGE,\tno_ver(xe,\thuc,\t\tbmg))\t\t\\\n",
     "\tfw_def(PANTHERLAKE,\tno_ver(xe,\thuc,\t\tptl))\t\t\\\n\tfw_def(BATTLEMAGE,\tno_ver(xe,\thuc,\t\tbmg))\t\t\\\n", 1),
])
# acpi_target_system_state() is declared by Linux's linux/acpi.h, which xe_display.c gets indirectly on Linux only
edit("display/xe_display.c", [('#include "intel_acpi.h"\n', '#include "intel_acpi.h"\n#include <linux/acpi.h>\n', 1)])
# SR-IOV VF (a Panther Lake VF passed to a macOS VM): 6.14 carries the VF driver but enables it on no platform. With
# has_sriov set, xe_sriov_probe_early() reads VF_CAP_REG and runs in VF mode on a VF, where update_device_info()
# already turns off display, GSC, GuC PC and pcode. On the physical function nothing changes (the PF path needs
# sriov_configure, removed above, and stays off: pf readiness fails without VFs to provision).
edit("xe_pci.c", [("\tPLATFORM(PANTHERLAKE),\n\t.has_display = true,\n\t.require_force_probe = true,\n",
                   "\tPLATFORM(PANTHERLAKE),\n\t.has_display = true,\n\t.has_sriov = true,\n\t.require_force_probe = true,\n", 1)])
# LinuxKPI puts a PCI driver on the "vgapci" bus class (where NMXGPU offers display devices, nmx_port_attach) only
# when it is named "drmn" - drm-kmod renames i915's and amdgpu's driver for that. xe kept "xe", registered on plain
# "pci" and was never offered the GPU: every xe device ended in "vgapci0: no driver attached".
edit("xe_pci.c", [("static struct pci_driver xe_pci_driver = {\n\t.name = DRIVER_NAME,\n",
                   "static struct pci_driver xe_pci_driver = {\n\t.name = \"drmn\",\t/* LinuxKPI: a DRM driver, on vgapci */\n", 1)])
# VF GMD_ID read (6.14 bug, fixed upstream by giving read_gmdid() a dummy GT with xe_gt_mmio_init()): 6.14 talks to
# the GuC through the root GT before that GT's MMIO is set up, so the first VF_SW_FLAG write went through a NULL base
# (panic in xe_mmio_write32 from xe_gt_sriov_vf_bootstrap). Map it first; since 6.14 reuses the real root GT, drop the
# media GSI offset afterwards so the main GT does not keep it after the GMDID_MEDIA read.
edit("xe_pci.c", [
    ("\t\txe_guc_comm_init_early(&gt->uc.guc);\n\n\t\t/* Don't bother with GMDID if failed to negotiate the GuC ABI */\n",
     "\t\txe_gt_mmio_init(gt);\n\t\txe_guc_comm_init_early(&gt->uc.guc);\n\n\t\t/* Don't bother with GMDID if failed to negotiate the GuC ABI */\n", 1),
    ("\t\tgt->info.id = 0;\n\t\tgt->info.type = XE_GT_TYPE_UNINITIALIZED;\n",
     "\t\tgt->info.id = 0;\n\t\tgt->info.type = XE_GT_TYPE_UNINITIALIZED;\n\t\tgt->mmio.adj_offset = 0;\n\t\tgt->mmio.adj_limit = 0;\n", 1),
])
# VF before interrupts: 6.14 runs the VF/PF handshake (VF2GUC relay over CT) in xe_gt_init_hwconfig(), before
# xe_irq_install(); upstream later moved it after IRQs. The GuC answers (G2H tail moves) but nothing processes the
# reply, so the wait timed out. While xe's IRQs are not enabled, poll: kick the G2H handling every 2 ms.
edit("xe_guc_ct.c", [("\tret = wait_event_timeout(ct->g2h_fence_wq, g2h_fence.done, HZ);\n",
    "\tif (!atomic_read(&ct_to_xe(ct)->irq.enabled)) {\n"
    "\t\tunsigned long nmx_end = jiffies + HZ;\n\n"
    "\t\tdo {\n\t\t\txe_guc_ct_irq_handler(ct);\n"
    "\t\t\tret = wait_event_timeout(ct->g2h_fence_wq, g2h_fence.done, msecs_to_jiffies(2));\n"
    "\t\t} while (!ret && time_before(jiffies, nmx_end));\n"
    "\t} else {\n\t\tret = wait_event_timeout(ct->g2h_fence_wq, g2h_fence.done, HZ);\n\t}\n", 1)])
# Runtime PM: macOS never suspends the device under the driver, but LinuxKPI's pm_runtime_get_if_active() and
# pm_runtime_get_if_in_use() are TODO stubs returning -EINVAL. xe's G2H worker and CT fast path bail out unless
# get_if_active succeeds, so every GuC reply was dropped. The device is always awake here: say so.
edit("xe_pm.c", [
    ("\treturn pm_runtime_get_if_active(xe->drm.dev) > 0;\n",
     "\t/* macOS port: no runtime PM, the device is always active (LinuxKPI's helper is a -EINVAL stub) */\n"
     "\tpm_runtime_get_noresume(xe->drm.dev);\n\treturn true;\n", 1),
    ("\treturn pm_runtime_get_if_in_use(xe->drm.dev) > 0;\n",
     "\t/* macOS port: no runtime PM (see xe_pm_runtime_get_if_active) */\n"
     "\tpm_runtime_get_noresume(xe->drm.dev);\n\treturn true;\n", 1),
])
# Shutdown on a VF (backport of upstream, as in Linux 7.2): the driver-initiated FLR and the GDRST full-GT reset are PF
# registers. A VF reads GU_CNTL_PROTECTED as 0 ("FLR allowed"), so 6.14's xe_device_shutdown wrote GU_CNTL, which a
# VF cannot, and waited out its 3 s completion timeout ("Driver-FLR-reinit wait completion failed! -60") inside
# NMXGPU's systemWillShutdown, on every restart ("Restart still waiting on NMXGPU"). A VF quiesces its GTs and asks the
# GuC to reset its own state (VF2GUC_VF_RESET) instead; the PF resets the function itself.
edit("xe_device.c", [("static bool xe_driver_flr_disabled(struct xe_device *xe)\n{\n"
                      "\treturn xe_mmio_read32(xe_root_tile_mmio(xe), GU_CNTL_PROTECTED) & DRIVERINT_FLR_DIS;\n}\n",
                      "static bool xe_driver_flr_disabled(struct xe_device *xe)\n{\n"
                      "\tif (IS_SRIOV_VF(xe))\n\t\treturn true;\n\n"
                      "\treturn xe_mmio_read32(xe_root_tile_mmio(xe), GU_CNTL_PROTECTED) & DRIVERINT_FLR_DIS;\n}\n", 1)])
edit("xe_gt_sriov_vf.c", [("\terr = guc_action_vf_reset(guc);\n\tif (unlikely(err))\n"
                           "\t\txe_gt_sriov_err(gt, \"Failed to reset GuC state (%pe)\\n\", ERR_PTR(err));\n\treturn err;\n}\n",
                           "\terr = guc_action_vf_reset(guc);\n\tif (unlikely(err))\n"
                           "\t\txe_gt_sriov_err(gt, \"Failed to reset GuC state (%pe)\\n\", ERR_PTR(err));\n\treturn err;\n}\n\n"
                           "/* xe_gt_sriov_vf_reset - reset the GuC's state for this VF (needs GuC MMIO communication) */\n"
                           "int xe_gt_sriov_vf_reset(struct xe_gt *gt)\n{\n"
                           "\tif (!xe_device_uc_enabled(gt_to_xe(gt)))\n\t\treturn -ENODEV;\n\n"
                           "\treturn vf_reset_guc_state(gt);\n}\n", 1)])
edit("xe_gt_sriov_vf.h", [("int xe_gt_sriov_vf_bootstrap(struct xe_gt *gt);\n",
                           "int xe_gt_sriov_vf_bootstrap(struct xe_gt *gt);\nint xe_gt_sriov_vf_reset(struct xe_gt *gt);\n", 1)])
edit("xe_gt.c", [("#include \"xe_sriov.h\"\n", "#include \"xe_sriov.h\"\n#include \"xe_gt_sriov_vf.h\"\n", 1),
                 ("static int do_gt_reset(struct xe_gt *gt)\n{\n\tint err;\n\n",
                  "static int do_gt_reset(struct xe_gt *gt)\n{\n\tint err;\n\n"
                  "\tif (IS_SRIOV_VF(gt_to_xe(gt)))\n\t\treturn xe_gt_sriov_vf_reset(gt);\n\n", 1)])
# Memory-based interrupts on a VF (backport of upstream, as in Linux 7.2 xe_memirq.c): Intel's programming note says
# to assume an engine's MI_USER_INTERRUPT and the GuC's GUC2HOST status bytes are always set. 6.14 handled them only
# when the byte read non-zero, so a report whose source byte arrived without its status byte lost a fence signal or
# a GuC reply (a stall until some later interrupt, or a G2H timeout). Both handlers are idempotent; the bytes are
# still cleared.
edit("xe_memirq.c", [
    ("\tif (memirq_received(memirq, status, ilog2(GT_RENDER_USER_INTERRUPT), hwe->name))\n"
     "\t\txe_hw_engine_handle_irq(hwe, GT_RENDER_USER_INTERRUPT);\n",
     "\t/* the programming note says to assume GT_MI_USER_INTERRUPT is always set (backport) */\n"
     "\tmemirq_received(memirq, status, ilog2(GT_RENDER_USER_INTERRUPT), hwe->name);\n"
     "\txe_hw_engine_handle_irq(hwe, GT_RENDER_USER_INTERRUPT);\n", 1),
    ("\tif (memirq_received(memirq, status, ilog2(GUC_INTR_GUC2HOST), name))\n"
     "\t\txe_guc_irq_handler(guc, GUC_INTR_GUC2HOST);\n",
     "\t/* the programming note says to assume GUC_INTR_GUC2HOST is always set (backport) */\n"
     "\tmemirq_received(memirq, status, ilog2(GUC_INTR_GUC2HOST), name);\n"
     "\txe_guc_irq_handler(guc, GUC_INTR_GUC2HOST);\n", 1),
])
# Xe3 render workarounds (backport of upstream, as in Linux 7.2 xe_wa.c lrc_was): 14026781792 (FF_MODE
# DIS_TE_PATCH_CTRL), 22021007897 for Xe3 (SBE_PUSH_CONSTANT_BEHIND_FIX_ENABLE) and 14024681466
# (FAST_CLEAR_VALIGN_FIX). They live in the context image, so a VF applies them itself.
edit("regs/xe_gt_regs.h", [
    ("#define   DIS_MESH_AUTOSTRIP\t\t\tREG_BIT(15)\n",
     "#define   DIS_MESH_AUTOSTRIP\t\t\tREG_BIT(15)\n#define   DIS_TE_PATCH_CTRL\t\t\tREG_BIT(4)\n", 1),
    ("#define COMMON_SLICE_CHICKEN4\t\t\tXE_REG(0x7300, XE_REG_OPTION_MASKED)\n",
     "#define COMMON_SLICE_CHICKEN4\t\t\tXE_REG(0x7300, XE_REG_OPTION_MASKED)\n"
     "#define XEHP_COMMON_SLICE_CHICKEN4\t\tXE_REG_MCR(0x7300, XE_REG_OPTION_MASKED)\n"
     "#define   SBE_PUSH_CONSTANT_BEHIND_FIX_ENABLE\tREG_BIT(12)\n", 1),
    ("#define   MSC_MSAA_REODER_BUF_BYPASS_DISABLE\tREG_BIT(14)\n",
     "#define   MSC_MSAA_REODER_BUF_BYPASS_DISABLE\tREG_BIT(14)\n#define   FAST_CLEAR_VALIGN_FIX\t\t\tREG_BIT(13)\n", 1),
])
edit("xe_wa.c", [("\t/* Xe3_LPG */\n\t{ XE_RTP_NAME(\"14021490052\"),",
    "\t/* Xe3_LPG */\n"
    "\t{ XE_RTP_NAME(\"14026781792\"),\n"
    "\t  XE_RTP_RULES(GRAPHICS_VERSION_RANGE(3000, 3510), ENGINE_CLASS(RENDER)),\n"
    "\t  XE_RTP_ACTIONS(SET(FF_MODE, DIS_TE_PATCH_CTRL))\n\t},\n"
    "\t{ XE_RTP_NAME(\"22021007897\"),\n"
    "\t  XE_RTP_RULES(GRAPHICS_VERSION_RANGE(3000, 3005), ENGINE_CLASS(RENDER)),\n"
    "\t  XE_RTP_ACTIONS(SET(XEHP_COMMON_SLICE_CHICKEN4, SBE_PUSH_CONSTANT_BEHIND_FIX_ENABLE))\n\t},\n"
    "\t{ XE_RTP_NAME(\"14024681466\"),\n"
    "\t  XE_RTP_RULES(GRAPHICS_VERSION_RANGE(3000, 3005), ENGINE_CLASS(RENDER)),\n"
    "\t  XE_RTP_ACTIONS(SET(XEHP_SLICE_COMMON_ECO_CHICKEN1, FAST_CLEAR_VALIGN_FIX))\n\t},\n"
    "\t{ XE_RTP_NAME(\"14021490052\"),", 1)])
# G2H fence completion flag (backport of upstream, as in Linux 7.2 xe_guc_ct.c): the waiter reads g2h_fence.done
# with READ_ONCE and parse_g2h_response sets it with WRITE_ONCE. (Runs after the IRQ-less poll edit above, which
# split the wait into two.)
edit("xe_guc_ct.c", [
    ("ct->g2h_fence_wq, g2h_fence.done, ", "ct->g2h_fence_wq, READ_ONCE(g2h_fence.done), ", 2),
    ("\t\tif (g2h_fence.done) {\n", "\t\tif (READ_ONCE(g2h_fence.done)) {\n", 1),
    ("\tg2h_fence->done = true;\n\tsmp_mb();\n", "\tWRITE_ONCE(g2h_fence->done, true);\n\tsmp_mb();\n", 1),
])
# Runtime resume from reclaim on a VF (backport of upstream, as in Linux 7.2 xe_pm.c): only D3cold makes it unsafe.
# 6.14 also excluded SR-IOV, so on this VF every BO move that handles system CCS pages (Xe3 iGPU: most user BOs)
# took the noresume branch and hit drm_WARN_ON(handle_system_ccs), ~80 times a minute on the desktop.
edit("xe_pm.c", [("\treturn !xe->d3cold.capable && !xe->info.has_sriov;\n", "\treturn !xe->d3cold.capable;\n", 1)])
# --- NMX VF DIAGNOSTICS (temporary, for bring-up on the VF) ---
# count VF interrupts, and on a G2H timeout print both CT descriptors: tells "GuC never read the H2G" (DMA/GGTT) from
# "GuC answered but no interrupt arrived" (IRQ path)
edit("xe_irq.c", [("static irqreturn_t vf_mem_irq_handler(int irq, void *arg)\n{\n\tstruct xe_device *xe = arg;\n",
                   "unsigned int nmx_vf_irq_count;\nstatic irqreturn_t vf_mem_irq_handler(int irq, void *arg)\n{\n\tstruct xe_device *xe = arg;\n\n\tnmx_vf_irq_count++;\n", 1)])
edit("xe_guc_ct.c", [("\t\txe_gt_err(gt, \"Timed out wait for G2H, fence %u, action %04x, done %s\",\n\t\t\t  g2h_fence.seqno, action[0], str_yes_no(g2h_fence.done));\n",
    "\t\txe_gt_err(gt, \"Timed out wait for G2H, fence %u, action %04x, done %s\",\n\t\t\t  g2h_fence.seqno, action[0], str_yes_no(g2h_fence.done));\n"
    "\t\t{\n\t\t\textern unsigned int nmx_vf_irq_count;\n\t\t\tstruct xe_device *nxe = ct_to_xe(ct);\n"
    "\t\t\txe_gt_err(gt, \"NMX CT: h2g head %u tail %u status %#x | g2h head %u tail %u status %#x | info h2g tail %u g2h head %u | ggtt %#x | vf irqs %u enabled %d memirq %d\\n\",\n"
    "\t\t\t\t  desc_read(nxe, (&ct->ctbs.h2g), head), desc_read(nxe, (&ct->ctbs.h2g), tail), desc_read(nxe, (&ct->ctbs.h2g), status),\n"
    "\t\t\t\t  desc_read(nxe, (&ct->ctbs.g2h), head), desc_read(nxe, (&ct->ctbs.g2h), tail), desc_read(nxe, (&ct->ctbs.g2h), status),\n"
    "\t\t\t\t  ct->ctbs.h2g.info.tail, ct->ctbs.g2h.info.head, xe_bo_ggtt_addr(ct->bo), nmx_vf_irq_count,\n"
    "\t\t\t\t  atomic_read(&nxe->irq.enabled), xe_device_uses_memirq(nxe));\n\t\t}\n", 1)])
print("xe fork applied")

# debug.nmxgpu_dump (override/xe/nmx_xe_debug.c): the probed device prints its GuC, queue and fence state on demand
edit("xe_pci.c", [("\terr = xe_device_probe(xe);\n\tif (err)\n\t\treturn err;\n",
     "\terr = xe_device_probe(xe);\n\tif (err)\n\t\treturn err;\n\t{ void nmx_xe_debug_register(struct xe_device *); nmx_xe_debug_register(xe); }\n", 1)])

# TEMPORARY (2026-10-16): a VM_BIND that fails with EFAULT in WindowServer only - say which copy failed
edit("xe_vm.c", [("\t\t\terr = -EFAULT;\n\t\t\tgoto free_bind_ops;\n",
     "\t\t\terr = -EFAULT;\n\t\t\tprintf(\"xe vm_bind: copying %u bind ops from 0x%llx failed\\n\", args->num_binds, (unsigned long long)args->vector_of_binds);\n\t\t\tgoto free_bind_ops;\n", 1)])
