"""Evaluate the MateBook 14 peripherals' ACPI methods the way macOS sees them.

macos-view/ holds the tables in macOS load order: the firmware DSDT and SSDTs with OpenCore's ACPI > Patch entries
already applied (scope deferral, _OSI -> XOSI), then our SSDTs in ACPI > Add order (see ORDER.txt). Under macOS the
battery reads zeros (BAT0._STA lacks the present bit), the lid fails in HWEC.ECRD with AE_AML_OPERAND_TYPE
("found [Mutex]"), and the touchpad device TPDX that SSDT-TPAD-TSCR adds under I2C0 never appears.
Usage: python3 eval_macos.py <acpiexec 20160930> <log>
"""
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent / 'macos-view'
acpiexec, log = sys.argv[1], Path(sys.argv[2])
tables = [str(here / name) for name in (here / 'ORDER.txt').read_text().split()]
EC = '\\_SB.PC00.LPCB.HWEC'
cmds = [
    'namespace \\_SB.PC00.I2C0', 'namespace \\_SB.PC00.I2C1',
    'evaluate \\_SB.PC00.I2C0.TPDX._STA', 'evaluate \\_SB.PC00.I2C0.TPDX._CRS',
    'evaluate \\_SB.PC00.I2C1.TPLX._STA', 'evaluate \\_SB.PC00.I2C1.TPLX._CRS',
    f'evaluate {EC}._REG 3 1',
    f'evaluate {EC}.BAT0._STA', f'evaluate {EC}.BAT0._BIX', f'evaluate {EC}.BAT0._BST',
    f'evaluate {EC}.LID._LID', f'evaluate {EC}.ALSD._STA',
    'quit',
]
r = subprocess.run([acpiexec, '-di'] + tables, input='\n'.join(cmds) + '\n',
                   capture_output=True, text=True, errors='replace')
log.write_text(r.stdout + r.stderr)
print(f'{log}: {len(r.stdout.splitlines())} lines, rc={r.returncode}')
