## Candidate 0.3.2 prepared — WindowServer-only trial

The22case/26,000frame application baseline is retained. Latest physical desktop failed: second readback and another surface upload timed out, then CoreDisplay threw while creating a texture after backend shutdown. Candidate0.3.2 serializes normal WindowServer submissions, disables submit-ahead and defers IOSurface-writer scheduling until successful copy-out. Scoped to8086:7d45 WindowServer; applications keep normal concurrency. No kernel, framebuffer, firmware or security changes. Local compile/sanitizer/order/error/installer regressions pass; target desktop success pending.

Next on fallback Dell: install-windowserver.sh, then after exit0 reboot through USB once. Installer changes only the Metal plugin and arms one desktop boot using the saved hardware baseline; no GPU suite rerun or auto-reboot. After failure, poweroff/USBfallback then collect-desktop-failure.sh; full crash reports and latest attempt window included.

