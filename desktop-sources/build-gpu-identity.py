from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent
out=r/'latitude-desktop/Library/NullMoth/latitude-gpu-identity'
subprocess.run(['xcrun','clang','-arch','x86_64','-mmacosx-version-min=15.0','-fobjc-arc','-O2','-I',str(r/'Vulkan-Headers/include'),'-I',str(r/'desktop-sources'),str(r/'desktop-sources/latitude-gpu-identity.m'),'-framework','Foundation','-framework','IOKit','-o',str(out)],check=True)
subprocess.run(['codesign','--force','--sign','-','--timestamp=none',str(out)],check=True)
subprocess.run(['codesign','--verify','--strict',str(out)],check=True)
print('Built signed x86_64 GPU identity query/publisher; no target execution.')
