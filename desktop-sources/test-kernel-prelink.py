from pathlib import Path
import plistlib,re,subprocess,tempfile,copy,uuid
r=Path(__file__).resolve().parent.parent
binary=r/'latitude-desktop/validate-kernel-prelink'
fixture=r/'desktop-sources/fixtures/kernel-prelink-164446.txt'
raw=fixture.read_bytes(); plists=[plistlib.loads(x) for x in re.findall(rb'<\?xml.*?</plist>',raw,re.S)]
expected='E770B985-14A4-3ADE-A1EE-63204C3A9996'; path='/Library/Extensions/NMXGPU.kext'
def check(data,ok):
 with tempfile.NamedTemporaryFile() as f:
  f.write(data);f.flush();c=subprocess.run([str(binary),f.name,expected,path,"1.0.9"],capture_output=True)
  assert (c.returncode==0)==ok,c.stdout+c.stderr
check(raw,True)
for mode in ['wrong-uuid','wrong-path','missing','duplicate','wrong-version','empty-executable','foreign-uuid','malformed']:
 x=copy.deepcopy(plists); records=x[-1]['_PrelinkInfoDictionary']; target=next(z for z in records if z.get('CFBundleIdentifier')=='com.nullmoth.NMXGPU')
 if mode=='wrong-uuid':target['OSBundleUUID']=bytes(16)
 if mode=='wrong-path':target['_PrelinkBundlePath']='/Library/GPUBundles/.temporary/NMXGPU.kext'
 if mode=='missing':records.remove(target)
 if mode=='duplicate':records.append(copy.deepcopy(target))
 if mode=='wrong-version':target['CFBundleVersion']='1.0.8'
 if mode=='empty-executable':target['_PrelinkExecutableSize']=0
 if mode=='foreign-uuid':
  records.append(dict(target,CFBundleIdentifier='other.driver'));target['OSBundleUUID']=bytes(16)
 data=b'header\n'+b'\0\n'.join(plistlib.dumps(z) for z in x)
 if mode=='malformed':data+=b'<?xml broken'
 check(data,False)
# Real saved framebuffer record exercises the generic extension validator.
args=[str(binary),str(fixture),'8F005BB5-A9E1-3A5F-882A-398E3D1E1E92','/Library/Extensions/LatitudeMTLFB.kext','0.2.3','com.nullmoth.LatitudeMTLFB','LatitudeMTLFB']
assert subprocess.run(args,capture_output=True).returncode==0
args[2]=expected
assert subprocess.run(args,capture_output=True).returncode!=0
print('PASS saved target prelink record, multiple collections/NUL padding; reject wrong UUID/path/version, missing/duplicate GPU, foreign UUID, empty executable, malformed XML')
