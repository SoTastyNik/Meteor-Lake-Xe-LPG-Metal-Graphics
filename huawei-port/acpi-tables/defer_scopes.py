"""Make the MateBook 14 ACPI tables loadable by macOS's ACPICA (20160930).

That ACPICA aborts a whole table when a Scope() targets a node that does not exist yet (the firmware's DSDT
scopes into devices that later SSDTs create, e.g. \\_SB.PC00.UA00), so macOS ends up without the DSDT and
its GNVS fields (STAS, OSYS, ...). This loop loads the tables in acpiexec 20160930, finds the Scope named in
"[path] Namespace lookup failure ... [TABLE] table load failed", replaces that Scope block with NoOp (0xA3)
bytes of the same length, and re-emits the identical block in SSDT-LATE-SCOPES, which OpenCore adds after
every firmware table. It repeats until every table loads.

The targets (UA00, HDAS, I2C1, SPI0, ...) are created by the DSDT itself inside module-level If blocks such as
If (PCHS != 0x04) { Scope (_SB.PC00) { Device (I2C0) ... } }. macOS's ACPICA groups all module-level code and
runs it only after every table has loaded (AcpiGbl_GroupModuleLevelCode), so a top-level Scope in a late SSDT
fails as well ("AE_NOT_FOUND (SSDT:LATESCP ) while loading table" in the macOS log). Each re-emitted block is
therefore wrapped in If (CondRefOf (<absolute target>)), which ACPICA defers the same way and runs after the DSDT's.

Outputs in <out>: SSDT-LATE-SCOPES.aml, defer-patches.json (OpenCore ACPI patches: original block ->
NoOps, pinned by table signature/OEM table id/length), final-load.log.
Usage: python3 defer_scopes.py <acpiexec 20160930> <out dir>
"""
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACPIEXEC, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
NOOP = 0xA3
NAMECHARS = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
LOOKUP_FAIL = re.compile(r'\[([A-Z0-9_.]+)\] Namespace lookup failure, AE_NOT_FOUND \(\d+/dswload-\d+\)')
LOAD_FAIL = re.compile(r'\[(\w{4})\] table load failed')
LOADED = re.compile(r'Table \[(\w{4}): ([^\]]*)\] \(id')


def checksum(t):
    t[9] = 0
    t[9] = (-sum(t)) & 0xff


def pkglen(b, i):
    lead = b[i]
    n = lead >> 6
    if n == 0:
        return lead & 0x3f, 1
    v = lead & 0x0f
    for k in range(n):
        v |= b[i + 1 + k] << (4 + 8 * k)
    return v, n + 1


def namepath(b, i):
    """(segments, absolute, encoded length) of the NameString at i, or None."""
    j, absolute = i, False
    if b[j] == 0x5c:
        absolute, j = True, j + 1
    while b[j] == 0x5e:
        j += 1
    if b[j] == 0x2e:
        n, j = 2, j + 1
    elif b[j] == 0x2f:
        n, j = b[j + 1], j + 2
    elif b[j] == 0x00:
        return [], absolute, j + 1 - i
    else:
        n = 1
    segs = []
    for _ in range(n):
        s = bytes(b[j:j + 4])
        if len(s) < 4 or any(c not in NAMECHARS for c in s) or s[:1].isdigit():
            return None
        segs.append(s.decode())
        j += 4
    return segs, absolute, j - i


def find_scopes(t, target):
    """ScopeOp blocks whose NamePath is exactly target (absolute, or root-relative multi-segment)."""
    hits = []
    for i in range(36, len(t) - 6):
        if t[i] != 0x10:
            continue
        ln, lb = pkglen(t, i + 1)
        if ln < 5 or i + 1 + ln > len(t):
            continue
        np = namepath(t, i + 1 + lb)
        if not np:
            continue
        segs, absolute, nlen = np
        if segs == target and (absolute or len(segs) > 1) and lb + nlen <= ln:
            hits.append((i, 1 + ln))
    return hits


order = ['DSDT.aml'] + [p.name for p in sorted((HERE / 'native').glob('SSDT-*.aml'),
                                                key=lambda p: int(p.stem.split('-')[1]))]
tables = {n: bytearray((HERE / 'native' / n).read_bytes()) for n in order}
original = {n: bytes(t) for n, t in tables.items()}
ours = sorted((HERE / 'ours').glob('SSDT-*.aml'))
late_blocks, patches = [], []


def ident(t):
    return bytes(t[0:4]).decode(), bytes(t[16:24]).decode('latin1').rstrip('\x00 ')


def encode_pkglen(n):
    """PkgLength for n bytes of content (the encoding's own bytes count towards the length)."""
    if n + 1 <= 0x3f:
        return bytes([n + 1])
    for extra in (1, 2, 3):
        total = n + 1 + extra
        if total < 1 << (4 + 8 * extra):
            return bytes([(extra << 6) | (total & 0x0f)]) + (total >> 4).to_bytes(extra, 'little')
    raise ValueError(n)


def deferred(block):
    """If (CondRefOf (<absolute scope target>)) { block }: module-level code, run after the DSDT's own If blocks."""
    segs, _, _ = namepath(block, 1 + pkglen(block, 1)[1])
    name = b''.join(x.encode() for x in segs)
    prefix = b'' if len(segs) == 1 else bytes.fromhex('2e') if len(segs) == 2 else bytes([0x2f, len(segs)])
    content = bytes.fromhex('5b12') + b'\\' + prefix + name + bytes(1) + block   # CondRefOf (\path, NullName)
    return bytes.fromhex('a0') + encode_pkglen(len(content)) + content          # IfOp


def late_table():
    body = b''.join(deferred(b) for b in late_blocks).replace(b'_OSI', b'XOSI')   # OpenCore's _OSI->XOSI patch targets the DSDT only
    t = bytearray(b'SSDT' + struct.pack('<I', 36 + len(body)) + bytes([2, 0]) + b'HUAWEI' + b'LATESCP ' +
                  struct.pack('<I', 1) + b'INTL' + struct.pack('<I', 0x20160930)) + body
    checksum(t)
    return t


def load():
    work = OUT / 'work'
    work.mkdir(exist_ok=True)
    files = []
    for name in order:
        t = bytearray(tables[name])
        if name == 'DSDT.aml':
            t = bytearray(bytes(t).replace(b'_OSI', b'XOSI'))
        checksum(t)
        (work / name).write_bytes(t)
        files.append(str(work / name))
    files += [str(p) for p in ours]
    if late_blocks:
        (work / 'SSDT-LATE-SCOPES.aml').write_bytes(late_table())
        files.append(str(work / 'SSDT-LATE-SCOPES.aml'))
    r = subprocess.run([ACPIEXEC, '-di'] + files, input='quit\n', capture_output=True, text=True, errors='replace')
    return r.stdout + r.stderr


def failing_table(log):
    """First firmware table, in load order, without a success line."""
    loaded = [(s, o.strip()) for s, o in LOADED.findall(log)]
    k = 0
    for name in order:
        if k < len(loaded) and loaded[k] == ident(tables[name]):
            k += 1
        else:
            return name
    return None


for it in range(80):
    log = load()
    fail = LOOKUP_FAIL.search(log)
    if not LOAD_FAIL.search(log) or not fail:
        break
    path = fail.group(1).split('.')
    name = failing_table(log)
    hits = find_scopes(tables[name], path) if name else []
    if not hits:
        print(log[-5000:])
        raise SystemExit(f'cannot locate Scope({".".join(path)}) in failing table {name}')
    for start, length in hits:
        late_blocks.append(bytes(tables[name][start:start + length]))
        tables[name][start:start + length] = bytes([NOOP]) * length
        patches.append({'table': name, 'path': '.'.join(path), 'offset': start, 'length': length})
    print(f'iteration {it}: deferred {len(hits)} Scope({".".join(path)}) block(s) from {name}')

(OUT / 'final-load.log').write_text(log)
if late_blocks:
    (OUT / 'SSDT-LATE-SCOPES.aml').write_bytes(late_table())
oc = []
for p in patches:
    t = original[p['table']]
    oc.append({'Comment': f"Defer {p['table']} Scope({p['path']}) for macOS ACPICA 20160930",
               'TableSignature': t[0:4].hex(), 'OemTableId': t[16:24].hex(), 'TableLength': len(t),
               'Find': t[p['offset']:p['offset'] + p['length']].hex(), 'Replace': 'a3' * p['length']})
(OUT / 'defer-patches.json').write_text(json.dumps(oc, indent=1))
print(f'{len(patches)} Scope blocks deferred; remaining table load failures: {len(LOAD_FAIL.findall(log))}')
for line in log.splitlines():
    if 'ACPI Error' in line or 'ACPI Exception' in line:
        print('  ', line)
