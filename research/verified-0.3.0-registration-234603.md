# 0.3.0 attempt at 23:46:03: stopped at registration

Install at 23:42:31 succeeded (READBACK INSTALL exit=0). Target boot time 23:45:08. test-and-arm-desktop-20261018-234603.txt reports Metal plugin registration timed out after 75 seconds, DESKTOP PREPARATION exit=2. accelerator-before.txt is empty. NMXGPU1.0.7 and NMXAccel0.2.4 are listed as loaded kexts, but no NMXAccel service was found. Installed plugin version and hashes passed runner checks. No cases were started; no policy/pool cleanup results exist; no desktop gate or desktop arming occurred. Exact registration failure cause remains unknown.

Collector defects discovered: readback-failure-234733 selected older readback-232908 because it required results.txt; newest report has no results on early preflight exit. Its frame101 device loss belongs to the old retained control. failure-detail-234759 queried hard-coded 18:38:00–18:39:50, so its WindowServer hang is historical and unrelated to candidate0.3.0.

Fixed collector selection to newest report even without results, include report boot time and latest artifact time, preserve preflight metadata and include NMX/Latitude kernel probe messages. Removed fixed desktop-collector timestamps; defaults to latest report boot through collection time. Fixed watchdog output inheritance. Existing reports preserved; backups in backups/collector-selection-before. Actual read-only collector fixture now covers newest preflight-only report overriding an older report with results; test and all80 package hashes pass. No driver/EFI/boot marker changes.

Next: run collect-readback-failure.sh on Dell before reboot/reinstall, return USB for current-boot probe logs. No conclusion on 0.3.0 fresh-pool stability can be drawn from this attempt.
