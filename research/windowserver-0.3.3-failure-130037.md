# Candidate0.3.3: active desktop attempt failed on fourth readback

Evidence: failure-detail-20261019-130037. Failed boot UUID43CADE8D-A3E3-46D8-88F6-3CBD2AE93D0C began approximately12:58:39. Collector ran13:00:37 on fallback boot12:59:58 UUID1755918F-01FE-46C8-8FE1-D2982DD55840. Installed plugin SHA matches0.3.3:7f9afc41c04f990113fe646cf2d74dc4c283600bb31147df19fabe6418cfc1f9.

## Active path and failure order

-12:58:46 root journal: claim-active.12:58:47 framebuffer load exited0. This was an opted-in desktop attempt, unlike the previous NVRAM-reset fallback.
-12:58:49.782 through12:58:50.078: first eight logged submissions complete successfully. These include surface upload, rendering/event work and three readbacks. GPU completion is not proof of correct pixels/panel composition.
-12:58:50.085: fourth readback, image2/staging12, fullHD1920x1080/pitch7680.12:58:55.086 fence timeout(VK_TIMEOUT2) after5000ms; backend disables, retains uncertain resources, leaves CPU destination untouched. Later first-submit records are rate-limited by nvlog, so absence of a #9 queue line does not establish absence of a ninth submission.
-12:59:03.799 kernel reports hung rcs0 context, active request8:24 [0x1002] not yet started.12:59:03.867 GPUHANG12:1:00dfffff. First-error diagnostics report resets0, GTawake1, IOMMU0, EIR/PGTBL_ER/fault registers0, GuC CT0tail618/CT1head236. Zero register snapshots do not establish a healthy queue or exclude a memory bug.
-WindowServer PID163 crash12:59:04: COREANIMATION termination, pipeline specPBGRAXb_Xh, Vulkan is not up in this process. This is after backend timeout, not proof of a primary shader compile defect. Restarted processes fail dummy zero-fill with2second timeouts and CoreDisplay texture creation, then crash at12:59:10(PID444) and12:59:21(PID461).

## Capture limits

Root journal and live/registry capture survived. WindowServer direct journal was denied: errno1, matching Sandbox file-write-data denial for /Library/Logs/LatitudeDesktopAttempt.trace. No plugin-stage entries therefore does not mean plugin never loaded. Existing unified live records establish plugin GPU submissions. The stack sample did not produce a usable output; stderr says pid_for_task failed, process0, although sample returned0. Do not count sample-end/result0 as a successful stack capture.

## Interpretation

Serialization/bounded host lock did not cure the physical desktop GPU hang. This failure is a fence timeout followed by an explicit kernel GPU hang, not evidence of the host mutex deadline firing. Three readbacks completed before the fourth stalled; that does not establish stable acceleration. Earlier26,000-frame application baseline is retained; no full-suite rerun is indicated. Further source investigation should focus on GT/request/GuC progress and resource transitions in the physical desktop workload. Do not suppress downstream CoreAnimation errors, extend timeouts blindly, bypass sandbox restrictions, or declare a fixed desktop from successful early submissions. No new candidate, boot configuration or security change was made while examining this report.
