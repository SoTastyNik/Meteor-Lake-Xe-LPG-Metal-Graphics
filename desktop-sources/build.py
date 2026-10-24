from pathlib import Path
import subprocess,plistlib,shutil
root=Path(__file__).resolve().parent.parent;src=root/'NullMoth/kexts/NMXVGAFB';out=root/'desktop-build';pkg=root/'latitude-desktop'
sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()
flags=['-arch','x86_64','-mmacosx-version-min=15.0','-fapple-kext','-mkernel','-nostdinc','-I'+sdk+'/System/Library/Frameworks/Kernel.framework/Headers','-DKERNEL','-DKERNEL_PRIVATE','-DDRIVER_PRIVATE','-DAPPLE','-DNeXT','-DLATITUDE_MTL_PANEL','-I'+str(root/'desktop-sources'),'-std=c++17','-fno-rtti','-fno-exceptions','-fno-builtin','-fno-common','-Wall','-Wno-unused-parameter','-Wno-inconsistent-missing-override','-O2']
for name,path in [('nmxvgafb',src/'nmxvgafb.cpp'),('nmx_virtio_gpu',src/'nmx_virtio_gpu.cpp'),('LatitudePanelClaim',root/'desktop-sources/LatitudePanelClaim.cpp')]:
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(['xcrun','clang++',*flags,'-c',str(path),'-o',str(out/(name+'.o'))],stdout=log,stderr=subprocess.STDOUT)
 if r.returncode:print((out/(name+'.log')).read_text()[-6000:]);raise SystemExit(r.returncode)
for name,subdir,objects in [('LatitudeMTLFB','Library/Extensions',['nmxvgafb','nmx_virtio_gpu']),('LatitudePanelClaim','EFI-Kexts',['LatitudePanelClaim'])]:
 kext=pkg/subdir/(name+'.kext');(kext/'Contents/MacOS').mkdir(parents=True,exist_ok=True)
 subprocess.run(['xcrun','clang++','-arch','x86_64','-mmacosx-version-min=15.0','-fapple-kext','-nostdlib','-Xlinker','-kext','-lkmodc++','-lkmod','-lcc_kext',*[str(out/(o+'.o')) for o in objects],'-o',str(kext/'Contents/MacOS'/name)],check=True)
 m={'CFBundleExecutable':name,'CFBundleIdentifier':'com.nullmoth.'+name,'CFBundleName':name,'CFBundlePackageType':'KEXT','CFBundleVersion':'0.2.3','CFBundleShortVersionString':'0.2.3','CFBundleInfoDictionaryVersion':'6.0','OSBundleLibraries':{'com.apple.kpi.iokit':'8.0','com.apple.kpi.libkern':'8.0','com.apple.kpi.mach':'8.0','com.apple.iokit.IOPCIFamily':'1.0.0'}}
 person={'CFBundleIdentifier':m['CFBundleIdentifier'],'IOClass':'NMXIntelVGAFB' if name=='LatitudeMTLFB' else name,'IOProviderClass':'LatitudePanelClaim' if name=='LatitudeMTLFB' else 'IOPCIDevice','IOMatchCategory':'IOFramebuffer','IOProbeScore':60000}
 if name=='LatitudePanelClaim':person.update(IOPCIMatch='0x7d558086');m['OSBundleRequired']='Root'
 else:m['OSBundleLibraries'].update({'com.apple.iokit.IOGraphicsFamily':'1.0.0','com.apple.kpi.bsd':'8.0'})
 m['IOKitPersonalities']={name:person};(kext/'Contents/Info.plist').write_bytes(plistlib.dumps(m))
 subprocess.run(['codesign','--force','--sign','-',str(kext)],check=True);subprocess.run(['codesign','--verify','--strict',str(kext)],check=True)
 print('Built',name)
