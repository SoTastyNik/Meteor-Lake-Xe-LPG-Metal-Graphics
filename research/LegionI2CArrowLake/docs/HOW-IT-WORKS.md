# How LegionI2CArrowLake works

## The problem

VoodooI2C matches Intel LPSS I2C controllers by PCI ID, one personality per PCH generation, each carrying the bus clock and the SDA/SCL timing values for that silicon. 2.9.1 knows Sunrise Point, Cannon Lake, Comet Lake and Ice Lake. The Arrow Lake-HX / 800-series PCH functions `8086:7F4C`, `7F4D`, `7F4E` and `7F4F` are not in the list, so nothing attaches and a touchpad on those buses never appears.

## The timing values

Linux `drivers/mfd/intel-lpss-pci.c` assigns these four IDs `bxt_i2c_info`: clock 133 MHz, SDA hold 42 ns, SDA falling 171 ns, SCL falling 208 ns. VoodooI2C's Ice Lake personality (0x34E8, also `bxt_i2c_info` in Linux) carries exactly those numbers, so the personality here is the Ice Lake one with the `IOPCIMatch` changed to `0x7f4c8086&0xFFFCFFFF` (mask the two low bits of the device ID, so one entry covers all four functions).

## D3hot

Version 1.0.0 used `VoodooI2CPCIController` as the class and did not work: the controller enumerated, VoodooI2C attached, and every register read returned `0xffffffff`, including `COMP_TYPE`, which the driver checks first. That is what a PCI function in D3hot looks like: the firmware had left the unused I2C controller powered down, and nothing had brought it back. VoodooI2C's `VoodooI2CPCILakeController` subclass (used for its Ice Lake and newer personalities) writes the power management control register (PMCSR, in the capability at offset 0x80) to put the function in D0 before it maps the registers. Switching the class to that one is the whole of 1.1.0, and the touchpad has worked since.

## Interrupts

The touchpad's interrupt line is a GPIO pin. VoodooGPIO routes those for the PCH generations it has community data for; Arrow Lake's GPIO controllers (`INTC1082`, `INTC1084`) are not among them. With `-vi2c-force-polling` VoodooI2C polls the device instead, which is what runs here. Adding the Arrow Lake GPIO community tables to VoodooGPIO (from the Linux `pinctrl-meteorlake` / Arrow Lake pinctrl driver) is the proper fix and is not done.

## Checking

```
ioreg -r -c VoodooI2CPCILakeController -l -w0
```

shows the controller with the four timing properties and, below it, the device nub and `VoodooI2CHIDDevice`. If the controller is there but the register dump shows `0xffffffff`, the D0 transition did not happen; if nothing matches at all, check that `IOPCIMatch` covers your device ID (`ioreg -r -n I2C1 -l | grep device-id`).
