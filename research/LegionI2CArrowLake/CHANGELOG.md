# Changelog

## 1.1.0 (2026-10-16)

- Controller class changed to `VoodooI2CPCILakeController`, which brings the function out of D3hot through PMCSR before using it. 1.0.0 read `0xffffffff` from every register and the touchpad stayed dead.

## 1.0.0 (2026-10-15)

- First version: VoodooI2C personality for `8086:7F4C` to `7F4F` with the Ice Lake / `bxt_i2c_info` timing values.
