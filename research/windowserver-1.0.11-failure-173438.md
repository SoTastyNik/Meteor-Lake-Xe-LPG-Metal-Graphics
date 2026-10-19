# NMXGPU1.0.11 target failure — report20261019-173438

Installer20261019-172954 returned0 and recorded the1.0.11 mapping-lifetime candidate. Collector at17:34:38 runs on fallback boot17:33:58. Installed SHA496e108b4d94390ac6a7030aba655ff5c0c5c61d827d7d92c65b04315b27943a matches1.0.11; fallback-loaded kernel version/UUID1.0.11/B972B890-9276-3E0D-B260-190037118D3E. These current-boot identity fields alone are not a direct UUID capture of the failed boot. Installation preceded the17:32trial and no intervening reinstall is shown. Plugin SHA unchanged0.3.5.

Failed boot17:32: NMXGPU load notification17:32:22.425. WindowServer163 submission8/readback3 fence timeout17:32:30.136 after5000ms. Original WindowServer163 abort17:32:30.9299, CoreAnimation termination: spec=PBGRAXb_Xh, pipeline: Vulkan is not up in this process. Later process restarts also fail. Kernel capture17:32:39.567–39.637 again finds context8/seq20 ready1 active1 started0 completed0 submit-pending=-1, HWSP0x12; GPU HANG12:1:00dfffff.

Saved pre-tail context8/seq18 ring words0xc98/0xc9c/0xca0/0xca4 are0xfedca540/0/0x02800000/0. Saved pre-tail seq20 has0xff000000 at all four offsets. GuC IPEHR again0xff000000. The contemporaneous seq20 request itself starts with expected PIPE_CONTROL words at0xca8. Later hang CPU snapshot is all zeros after userspace crashed; it is not treated as the first corruption event.

Conclusion: identical pre-submit ring overwrite persists in the trial associated with1.0.11. The lifetime-pin omission was a source-demonstrated port defect, but correcting it did not resolve this failure. Do not continue treating page reclamation from missing pins as the established writer/cause. No new GPU or desktop success is established. Preserve the fix as an independent correctness correction, subject to its documented resident-memory and unsupported legacy GTT-mmap limits.

Next discriminating investigation: identify the physical pages and map/allocation owners of the ring and the IOSurface/private-image/staging buffers before the first overwrite; locate the earliest submission boundary with changed words. Neither the pixel-looking constant nor a later crash stack identifies the writer. Avoid firmware/CCS/timeout changes or another full22-case suite on this evidence. No new payload or boot settings changed during this log review.

Full capture preserved locally under port-artifacts/windowserver-mapping-lifetime-1.0.11/failure-detail-20261019-173438.
