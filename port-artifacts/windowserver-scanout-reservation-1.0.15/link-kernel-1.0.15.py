from pathlib import Path
import subprocess,json
r=Path(__file__).resolve().parent.parent;x=r/'NullMoth/gpu-port/xkpi';objects=[f for d in ['obj','obj-i915','lkobj','srcobj','xnuobj'] for f in sorted((x/d).glob('*.o'))];assert len(objects)==438
out=r/'desktop-build/NMXGPU-1.0.15'
with (r/'desktop-build/kernel-link-1.0.15.log').open('w') as log:subprocess.run(['xcrun','clang','-arch','x86_64','-mmacosx-version-min=15.0','-fapple-kext','-nostdlib','-Xlinker','-kext',*[str(f) for f in objects],'-lkmodc++','-lkmod','-lcc_kext','-o',str(out)],stderr=log,stdout=log,check=True)
def undefined(p):return set(subprocess.check_output(['xcrun','nm','-uj',str(p)],text=True).splitlines())
a=undefined(r/'desktop-build/NMXGPU-1.0.8');b=undefined(out);print('New imports:',sorted(b-a)); print('Removed imports:',sorted(a-b)); assert b-a <= {'__ZN9IOService11getPlatformEv'}, b-a
print('PASS 438-object x86_64 kernel link; undefined imports checked against 1.0.8')
print(subprocess.check_output(['xcrun','dwarfdump','--uuid',str(out)],text=True).strip())
