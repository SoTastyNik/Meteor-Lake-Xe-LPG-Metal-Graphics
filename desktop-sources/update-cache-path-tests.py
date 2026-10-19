from pathlib import Path
r=Path(__file__).resolve().parent.parent
body='''
if [ "$1" = create ]; then
  output=''; paths=''
  while [ "$#" -gt 0 ]; do
    case "$1" in -A) shift; output=$1;; -p) shift; paths="$paths $1";; esac
    shift
  done
  case "$output" in *next-aux.kc) [ "$MODE" != preflight-fail ] && [ "$MODE" != kc-preflight ] || exit 6;; *installed-aux.kc) [ "$MODE" != final-build-fail ] || exit 7;; esac
  printf 'new-cache\\n%s\\n%s\\n' "$MOCK_UUID" "$paths" > "$output"
  exit 0
fi
if [ "$1" = inspect ]; then
  case "$*" in *show-kext-uuids*) if [ "$MODE" = bad-uuid ]; then echo wrong; else echo "$MOCK_UUID"; fi;;
    *) if [ "$MODE" = bad-path ]; then echo "$WORK/NMXGPU.kext"; else echo "$MOCK_KERNEL_DEST"; fi;; esac
  exit 0
fi
if [ "$MODE" = kernel ]; then echo 'com.nullmoth.NMXGPU (1.0.7) wrong-uuid'
elif [ "$MODE" != cache-repair ]; then echo 'com.nullmoth.NMXGPU (1.0.8) verified-NMXGPU-uuid'; fi
echo 'com.nullmoth.NMXAccel (0.2.4) verified-NMXAccel-uuid'
echo com.dhinakg.AMFIPass
'''
p=r/'desktop-sources/test-windowserver-installer.py';s=p.read_text().replace("'kc-commit']","'kc-commit','cache-repair','bad-path','bad-uuid','final-build-fail']",1)
needle='  for name,body in scripts.items():';assert needle in s;s=s.replace(needle,'  scripts[\'kmutil\']='+repr(body)+'\n'+needle)
s=s.replace("f.write_text('old-plugin' if root==lib else 'new-plugin')","f.write_text('old-plugin' if root==lib else 'new-plugin')")
s=s.replace("  (pkg/'WindowServerKernel/NMXGPU-UUID.txt')", "  if mode=='cache-repair':(lib/'Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU').write_text('diagnostic-kernel')\n  (pkg/'WindowServerKernel/NMXGPU-UUID.txt')",1)
s=s.replace("MOCK_ONCE=str(p/'once')", "MOCK_ONCE=str(p/'once'),MOCK_UUID='diagnostic-uuid',MOCK_KERNEL_DEST=str(lib/'Extensions/NMXGPU.kext')")
s=s.replace("if mode=='success':assert c.returncode==0 and plugin=='new-plugin' and calls[:2]==['nullmoth-gpu-once=1','nullmoth-panel-once=1']", "if mode in ['success','cache-repair']:assert c.returncode==0 and plugin=='new-plugin' and (['nullmoth-gpu-once=1','nullmoth-panel-once=1']==calls[2:4] if mode=='cache-repair' else calls[:2]==['nullmoth-gpu-once=1','nullmoth-panel-once=1'])")
s=s.replace("['partial','verify','journal','kc-commit']","['partial','verify','journal','kc-commit','bad-path','bad-uuid','final-build-fail']")
s=s.replace("'diagnostic-kernel' if mode=='success' else", "'diagnostic-kernel' if mode in ['success','cache-repair'] else")
s=s.replace("assert (lib/'KernelCollections/AuxiliaryKernelExtensions.kc').read_text().strip()==('new-cache' if mode=='success' else 'old-cache'),mode+c.stdout+c.stderr", "cache=(lib/'KernelCollections/AuxiliaryKernelExtensions.kc').read_text()\n  if mode in ['success','cache-repair']:assert str(lib/'Extensions/NMXGPU.kext') in cache and '.latitude-windowserver.' not in cache and (pkg/'reports').is_dir(),cache\n  else:assert cache=='old-cache',mode+c.stdout+c.stderr")
s=s.replace("expected='new'  if mode=='success'", "expected='new'  if mode in ['success','cache-repair']")
s=s.replace("if mode!='success':assert 'old helper'", "if mode not in ['success','cache-repair']:assert 'old helper'")
p.write_text(s)
p=r/'desktop-sources/test-windowserver-kernel.py';s=p.read_text().replace("'missing-backup']","'missing-backup','bad-path','bad-uuid','final-build-fail']",1)
s=s.replace("  for name,body in mocks.items():", "  mocks['kmutil']="+repr(body)+"\n  (pkg/'WindowServerKernel/NMXGPU-UUID.txt').write_text('diag-uuid')\n  for name,body in mocks.items():")
s=s.replace("MODE=mode,CALLS", "MODE=mode,MOCK_UUID='diag-uuid',MOCK_KERNEL_DEST=str(lib/'Extensions/NMXGPU.kext'),CALLS")
s=s.replace("cache=='new-cache'", "cache.startswith('new-cache')")
s=s.replace("if mode=='success':assert cache.startswith('new-cache')", "if mode in ['success','already-new']:assert cache.startswith('new-cache') and str(lib/'Extensions/NMXGPU.kext') in cache and str(work/'NMXGPU.kext') not in cache")
s=s.replace(".read_text()=='old'\n  if mode=='already-new':assert not (root/'calls').exists()", ".read_text()==('new' if mode=='already-new' else 'old')")
p.write_text(s)
