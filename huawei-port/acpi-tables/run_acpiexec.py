"""Load the MateBook 14 ACPI tables the way macOS sees them, in a given acpiexec.

macOS (AppleACPIPlatform) embeds ACPICA 20160930. The DSDT gets OpenCore's _OSI -> XOSI patch;
our SSDTs are added after the firmware ones. MSDM (Windows key) is deliberately not in this folder.
Usage: python3 run_acpiexec.py <acpiexec> <log> [--no-ours]
"""
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
acpiexec, log = sys.argv[1], Path(sys.argv[2])
work = log.parent / (log.stem + '-tables')
work.mkdir(parents=True, exist_ok=True)
d = bytearray((here / 'native/DSDT.aml').read_bytes())
n = d.count(b'_OSI')
d = d.replace(b'_OSI', b'XOSI')
d[9] = 0
d[9] = (-sum(d)) & 0xff
(work / 'DSDT.aml').write_bytes(d)
tables = [work / 'DSDT.aml'] + sorted((here / 'native').glob('SSDT-*.aml'), key=lambda p: int(p.stem.split('-')[1]))
if '--no-ours' not in sys.argv:
    tables += sorted((here / 'ours').glob('SSDT-*.aml'))
# load, then run the module-level code / _INI pass and evaluate the objects macOS stumbled on
cmds = ['namespace \\STAS', 'namespace \\OSYS', 'evaluate \\_SB.UBTC._CRS', 'evaluate \\_SB.PC00.LPCB.RTC._STA',
        'evaluate \\_SB.GPI0._HID', 'evaluate \\_SB.PC00.TPD0._STA', 'quit']
r = subprocess.run([acpiexec, '-di'] + [str(t) for t in tables], input='\n'.join(cmds) + '\n',
                   capture_output=True, text=True, errors='replace')
log.write_text(f'_OSI->XOSI replaced {n}\n' + r.stdout + r.stderr)
print(f'{log}: {len(r.stdout.splitlines())} lines, rc={r.returncode}')
