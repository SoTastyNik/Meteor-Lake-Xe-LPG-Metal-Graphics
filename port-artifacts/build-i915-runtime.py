#!/usr/bin/env python3
"""Build i915 + shared DRM + runtime for the Latitude, without unrelated AMD/Xe/NPU engines."""
from pathlib import Path
import concurrent.futures, json, subprocess, sys, time, os
ROOT=Path(__file__).resolve().parent.parent
X=Path('/Users/ved/igpu-build/xkpi'); K=Path('/Users/ved/igpu-build/kpi'); D=K/'drm-kmod'
LOG=ROOT/'port-artifacts/full-build-logs'; LOG.mkdir(exist_ok=True)
for d in ['obj','obj-i915','lkobj','srcobj','xnuobj']:(X/d).mkdir(exist_ok=True)
subprocess.run([sys.executable,str(X/'gen_flags.py'),str(D),str(X/'amd.flags')],check=True)
def sources(*mods):
 r=subprocess.run([sys.executable,str(X/'srclist.py'),str(D),str(X/'amd.flags'),*mods],capture_output=True,text=True,check=True)
 if r.stderr.strip():raise RuntimeError(r.stderr)
 return [Path(p) for p in r.stdout.splitlines() if p.strip()]
exclude={'drm_gem_ttm_helper.c','drm_writeback.c','drm_hdcp_helper.c','sync_file.c','dma-fence-unwrap.c','dma-buf.c','dma-buf-kmod.c','linux_fb.c','vt_drmfb.c','drm_os_freebsd.c'}
core=[p for p in sources('drm','ttm','dmabuf') if p.name not in exclude]
for name in ['drm_client.c','drm_client_modeset.c','drm_panel_orientation_quirks.c','drm_mipi_dsi.c']:core.append(D/'drivers/gpu/drm'/name)
intel=[p for p in sources('i915') if p.name not in {'intel_ggtt_gmch.c','i915_gem_mman.c'}]
subprocess.run([sys.executable,str(X/'fork_i915_gem_mman.py'),str(D),str(X/'override/i915/i915_gem_mman.c')],check=True)
intel+=sorted((X/'override/i915').glob('*.c'))
skip=set('linux_80211 linux_80211_macops linuxkpi_80211_pm linux_netdev linux_usb linux_i2c linux_i2cbb linux_cmdline linux_eventfd'.split())
linux=[]
for p in sorted((K/'freebsd-src/sys/compat/linuxkpi/common/src').glob('*.c')):
 if p.stem not in skip and not (X/'override/src'/p.name).exists():linux.append(p)
linux+=sorted((X/'override/src').glob('*.c'));linux.append(K/'freebsd-src/sys/contrib/ck/src/ck_epoch.c')
bsd=sorted((X/'bsdcompat/src').glob('*.c'))
xnu=[p for p in sorted((X/'xnu').glob('*.cpp')) if p.name!='nmx_npu_kext.cpp']
jobs=[]
for script,paths in [('cc.sh',core),('cc-i915.sh',intel),('cclk.sh',linux),('ccsrc.sh',bsd),('ccxx.sh',xnu)]:
 # A duplicate basename would overwrite an object and produce a broken kext.
 assert len({p.stem for p in paths})==len(paths),(script,'duplicate basename')
 jobs.extend((script,p) for p in paths)
def compile_one(job):
 script,p=job;log=LOG/(script+'-'+p.name+'.log')
 with log.open('w') as out:r=subprocess.run([str(X/script),str(p),*(['-DNMX_I915_ONLY'] if script=='cclk.sh' and p.name=='nmx_fb_bridge.c' else [])],stdout=out,stderr=subprocess.STDOUT,cwd=X)
 return {'script':script,'source':str(p),'returncode':r.returncode,'log':str(log)}
start=time.time();results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for n,result in enumerate(pool.map(compile_one,jobs),1):
  results.append(result)
  if result['returncode']:print('FAIL',result['source'],flush=True)
  elif n%50==0:print('Compiled',n,'/',len(jobs),flush=True)
failed=[r for r in results if r['returncode']]
report={'total':len(results),'failed':len(failed),'seconds':round(time.time()-start,1),'results':results}
(ROOT/'port-artifacts/full-build-results.json').write_text(json.dumps(report,indent=2)+'\n')
print('TOTAL',len(results),'FAILED',len(failed),'SECONDS',report['seconds'],flush=True)
for r in failed:
 errors=[s for s in Path(r['log']).read_text().splitlines() if 'error:' in s]
 print(Path(r['source']).name,':','\n'.join(errors[:4]))
sys.exit(bool(failed))
