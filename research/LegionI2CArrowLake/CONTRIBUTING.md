# Contributing

Reports from other Arrow Lake laptops are the useful thing: the laptop model, which I2C function your touchpad is on (`ioreg -r -n I2C1 -l | grep device-id`, likewise I2C0 to I2C3), the touchpad's ACPI name and `_CID`, and the `ioreg -r -c VoodooI2CPCILakeController -l -w0` output. If you get the interrupt working without polling (VoodooGPIO data for the Arrow Lake GPIO controllers), that belongs upstream in VoodooGPIO, but please say so here too.

Pull requests: small, with the machine you tested on. AI-assisted PRs are fine as long as you can explain the change, which is the same bar I hold my own code to.
