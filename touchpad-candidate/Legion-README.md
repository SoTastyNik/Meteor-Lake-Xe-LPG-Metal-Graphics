# LegionI2CArrowLake

> **Heads up:** a good portion of this code is AI generated. I do understand how it works,
> and I'm happy to explain any of it. If something looks wrong or you have a question,
> open an issue or ping me on Discord (`watchthelight`).

A codeless kext (one `Info.plist`, no binary) that lets VoodooI2C drive the I2C controllers of Intel's Arrow Lake-HX / 800-series PCH (`8086:7F4C` to `7F4F`), so an I2C touchpad on those laptops works in macOS. VoodooI2C 2.9.1 only matches Sunrise Point, Cannon Lake, Comet Lake and Ice Lake controller IDs; this adds a personality for the Arrow Lake ones with the right timing values and the controller class that wakes the device from D3hot.

Written for a Lenovo Legion 5 15IAX10, whose ELAN06FA touchpad (`PNP0C50`, ACPI `\_SB.PC02.I2C1.TPD0`) sits on I2C1 = `8086:7F4D`.

## Status

| What | Tested on | Result |
|---|---|---|
| Touchpad ELAN06FA on `8086:7F4D` | Legion 5 15IAX10, VoodooI2C 2.9.1 + VoodooI2CHID, macOS 15.8.1 and 26.7.1 (25G241), OpenCore 1.0.8 | pointer, tap, two-finger scroll working daily since 2026-10-16; interrupt polled (`-vi2c-force-polling`), see below |

## What it can't do

- It needs `-vi2c-force-polling`: VoodooGPIO has no community data for the Arrow Lake GPIO controllers (`INTC1082` / `INTC1084`), so the touchpad interrupt cannot be routed and VoodooI2C polls instead. That costs a little CPU and latency; it does not affect how the pad feels here.
- It only matches the controller. Your touchpad still needs the right VoodooI2C satellite (VoodooI2CHID for `PNP0C50` HID-over-I2C devices) and an ACPI `_STA` that says the device is present under Darwin.
- Tested on one laptop and one controller revision.

## Installation

1. Install VoodooI2C 2.9.1 (with its VoodooGPIO and VoodooI2CServices plugins) and VoodooI2CHID the usual way. If VoodooPS2 is also loaded, load only one copy of VoodooInput.
2. Copy `LegionI2CArrowLake.kext` to `EFI/OC/Kexts/` and add it to `config.plist`, `Kernel > Add`, after VoodooI2C and VoodooI2CHID:

   ```
   BundlePath      LegionI2CArrowLake.kext
   ExecutablePath  (empty)
   PlistPath       Contents/Info.plist
   MinKernel       (empty)
   MaxKernel       (empty)
   Enabled         true
   ```

3. Add `-vi2c-force-polling` to `boot-args`.
4. Reboot and check:

   ```
   ioreg -r -c VoodooI2CPCILakeController -l -w0 | grep -E 'IOPCIMatch|I2CClkRate|COMP'
   ioreg -r -c VoodooI2CHIDDevice | head
   ```

5. Rollback: set `Enabled` to false. It has no code, so the worst case is a touchpad that stays dead.

## Properties

| Key | Value | Where it comes from |
|---|---|---|
| `IOPCIMatch` | `0x7f4c8086&0xFFFCFFFF` | matches 7F4C, 7F4D, 7F4E, 7F4F |
| `IOClass` | `VoodooI2CPCILakeController` | the VoodooI2C controller class that forces the function to D0 through PMCSR before touching it |
| `I2CClkRate` | 133000000 | Linux `intel-lpss-pci.c`, `bxt_i2c_info` for these IDs |
| `I2CSdaHoldTimeNs` | 42 | same |
| `I2CSdaFallingTimeNs` | 171 | same |
| `I2CSclFallingTimeNs` | 208 | same |
| `IOProbeScore` | 9999 | above VoodooI2C's own personalities, which do not match anyway |

## How it works

VoodooI2C's controller personalities carry the clock and timing values per PCH generation and name a controller class. Linux gives the Arrow Lake-HX LPSS I2C functions the same `bxt_i2c_info` timing table as Ice Lake (0x34E8), so the Ice Lake values are copied. The first version used the plain `VoodooI2CPCIController` class and failed: the firmware leaves the controller in D3hot, every register read returned `0xffffffff` (`COMP_TYPE` included), and VoodooI2C gave up. The `VoodooI2CPCILakeController` class writes the PMCSR (capability 0x80) to bring the function to D0 first, which is what 1.1.0 changed. More in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

## Credits

- [VoodooI2C](https://github.com/VoodooI2C/VoodooI2C) (alexandred and contributors, GPL-2.0): the driver this plugs into.
- Linux `drivers/mfd/intel-lpss-pci.c`: the device IDs and timing table.

## Licence

The `Info.plist` is ISC (see `LICENSE`). VoodooI2C itself is GPL-2.0 and is not included here.
