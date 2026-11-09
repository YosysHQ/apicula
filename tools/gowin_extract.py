#!/usr/bin/env python3
"""Extract vendor enums and .fse table types from a Gowin IDE's libgowin.so.

Static analysis only: the vendor library is disassembled with objdump and never
executed. It relies on libgowin.so being unstripped and built at -O0. The output
is meant to be committed, so running this is only needed for a new IDE version.

    gowin_extract.py extract LIBGOWIN_SO OUTDIR
    gowin_extract.py check-attrids OUTDIR [ATTRIDS_PY]

OUTDIR receives enums.json ({enum: {value: vendor_name}}), and the .fse table types
and per-device layouts are written to apycula/fse_formats.py. check-attrids reports where
apycula/attrids.py disagrees with the extracted names. Its exit status is 1 if a
numeric ID is missing from the vendor enum or a name differs beyond punctuation.
"""
import json
import os
import re
import struct
import subprocess
import sys
from collections import defaultdict

NAME_FN = re.compile(r'^(enumToStr(?:_part1)?\(NETLIST::(\w+)\)|getPioValueStr\(NETLIST::(\w+)\)'
                     r'|getInstSubTypeName\(NETLIST::(\w+),)')
FORMATS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'apycula', 'fse_formats.py')
READ_TABLE = 'fseFileData::readOneTable('
FORMAT_FNS = {'devToFsePath(DEV_TYPE, globalMem*)': 'devToFsePath',
              'fseFuseTable::readFseData(_IO_FILE*, DEV_TYPE)': 'fuse',
              'fseWireTable::readFseData(_IO_FILE*)': 'wire'}
HEADER = re.compile(r'^([0-9a-f]+) <(.*)>:$')
INSN = re.compile(r'^\s*([0-9a-f]+):\t(.*)$')
RIP = re.compile(r'lea\s+[-0x0-9a-f]+\(%rip\),%(\w+)\s+# ([0-9a-f]+)')
CTOR = re.compile(r'<(fse\w+)::\1\(')

# apycula/attrids.py table prefix -> vendor enum prefix
ATTRID_TABLES = {'pll': 'PLL', 'iob': 'PIO', 'iologic': 'IOL', 'cls': 'CLS', 'bsram': 'BSRAM',
                 'dsp': 'DSP', 'dll': 'DLL', 'hclk': 'HCLK', 'cfg': 'CFG', 'dlldly': 'DEL'}


class Image:
    """Read-only view of the ELF sections, addressed by virtual address."""

    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = f.read()
        shoff = struct.unpack_from('<Q', self.data, 0x28)[0]
        count = struct.unpack_from('<H', self.data, 0x3c)[0]
        self.sections = []
        for i in range(count):
            _, _, _, addr, off, size = struct.unpack_from('<IIQQQQ', self.data, shoff + i * 64)
            if addr:
                self.sections.append((addr, off, size))

    def offset(self, va):
        for addr, off, size in self.sections:
            if addr <= va < addr + size:
                return off + va - addr
        raise KeyError(hex(va))

    def i32(self, va):
        return struct.unpack_from('<i', self.data, self.offset(va))[0]

    def cstr(self, va):
        start = self.offset(va)
        return self.data[start:self.data.index(b'\0', start)].decode('latin1')


def relevant_functions(lib):
    """Yield (name, [(addr, text)]) for the functions this tool decodes."""
    proc = subprocess.Popen(['objdump', '-d', '-C', '--no-show-raw-insn', '-j', '.text', lib],
                            stdout=subprocess.PIPE, text=True, errors='replace', bufsize=1 << 20)
    name, body, keep = None, [], False
    for line in proc.stdout:
        header = HEADER.match(line)
        if header:
            if keep:
                yield name, body
            name, body = header[2], []
            keep = bool(NAME_FN.match(name)) or name.startswith(READ_TABLE) or name in FORMAT_FNS
        elif keep:
            insn = INSN.match(line)
            if insn:
                body.append((int(insn[1], 16), insn[2].strip()))
    if keep:
        yield name, body
    if proc.wait():
        raise RuntimeError(f'objdump failed with status {proc.returncode}')


def jump_tables(image, body):
    """Yield (case_value, target_addr) for every `cmp; ja; jump table` switch."""
    for n, (_, text) in enumerate(body[:-1]):
        cmp_ = re.match(r'cmp[lw]?\s+\$0x([0-9a-f]+),%eax', text)
        if not cmp_ or not body[n + 1][1].startswith('ja'):
            continue
        base = 0
        if n and (sub := re.match(r'sub\s+\$0x([0-9a-f]+),%eax', body[n - 1][1])):
            base = int(sub[1], 16)
        table = next((int(r[2], 16) for _, x in body[n + 1:n + 8] if (r := RIP.search(x))), None)
        if table is None:
            continue
        for k in range(int(cmp_[1], 16) + 1):
            yield k + base, (table + image.i32(table + 4 * k)) & 0xffffffff


def string_assigned_at(image, body, index):
    for _, text in body[index:index + 8]:
        rip = RIP.search(text)
        if rip and rip[1] == 'rsi':
            return image.cstr(int(rip[2], 16))
        if text.startswith(('jmp', 'ret')):
            return None
    return None


def decode_names(image, body):
    index = {addr: n for n, (addr, _) in enumerate(body)}
    names = {}
    for value, target in jump_tables(image, body):
        if target in index and (s := string_assigned_at(image, body, index[target])) is not None:
            names[value] = s
    # Small enums are compiled to compare chains rather than jump tables.
    for n, (_, text) in enumerate(body[:-1]):
        cmp_ = re.match(r'cmp[lw]?\s+\$0x([0-9a-f]+),(%eax|-0x[0-9a-f]+\(%rbp\))', text)
        je = re.match(r'je\s+([0-9a-f]+)', body[n + 1][1])
        if cmp_ and je and int(je[1], 16) in index:
            s = string_assigned_at(image, body, index[int(je[1], 16)])
            if s is not None:
                names.setdefault(int(cmp_[1], 16), s)
    return names


def decode_table_types(image, body):
    index = {addr: n for n, (addr, _) in enumerate(body)}
    classes = defaultdict(list)
    for value, target in jump_tables(image, body):
        cls = None
        for _, text in body[index[target]:index[target] + 25] if target in index else ():
            if ctor := CTOR.search(text):
                cls = ctor[1]
                break
            if text.startswith('jmp'):
                break
        classes[cls or 'unresolved'].append(value)
    return {cls: sorted(types) for cls, types in sorted(classes.items())}


def extract(lib, outdir):
    image = Image(lib)
    enums = {}
    table_types = None
    funcs = {}
    for name, body in relevant_functions(lib):
        if name.startswith(READ_TABLE):
            table_types = decode_table_types(image, body)
            funcs['table'] = body
            continue
        if name in FORMAT_FNS:
            funcs[FORMAT_FNS[name]] = body
            continue
        match = NAME_FN.match(name)
        enum = match[2] or match[3] or match[4]
        target = enums.setdefault('PIO_VALUE_ALT' if name.startswith('getPioValueStr') else enum, {})
        target.update({str(k): v for k, v in decode_names(image, body).items()})
    if table_types is None:
        raise RuntimeError('fseFileData::readOneTable not found')
    devices = decode_device_formats(image, funcs)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'enums.json'), 'w') as f:
        json.dump(enums, f, indent=1, sort_keys=True)
        f.write('\n')
    write_formats(table_types, devices)
    print(f'{len(enums)} enums, {sum(map(len, enums.values()))} names -> {outdir}')


def normalise(name):
    return str(name).upper().replace('_', '').replace('.', '')


def check_attrids(outdir, path):
    with open(os.path.join(outdir, 'enums.json')) as f:
        enums = json.load(f)
    namespace = {}
    with open(path) as f:
        exec(compile(f.read(), path, 'exec'), namespace)
    problems = 0
    for ours, vendor in ATTRID_TABLES.items():
        for suffix, kind in (('attrids', 'ATTR'), ('attrvals', 'VALUE')):
            table = namespace.get(f'{ours}_{suffix}')
            names = enums.get(f'{vendor}_{kind}')
            if table is None or names is None:
                print(f'skip {ours}_{suffix}: no matching table')
                continue
            for name, value in table.items():
                if not isinstance(value, int):
                    continue
                theirs = names.get(str(value))
                if theirs is None:
                    print(f'{ours}_{suffix}[{value}] {name}: not in vendor enum')
                    problems += 1
                elif normalise(theirs) != normalise(name) and 'UNKNOWN' not in theirs:
                    print(f'{ours}_{suffix}[{value}] {name}: vendor name {theirs}')
                    problems += 1
    print(f'{problems} differences')
    return 1 if problems else 0


def row_bytes_at(body, index):
    """Size argument of the first fread at or after an instruction index."""
    size = None
    for _, text in body[index:]:
        if mov := re.match(r'mov\s+\$0x([0-9a-f]+),%esi', text):
            size = int(mov[1], 16)
        if 'fread' in text:
            return size
    return None


def decode_device_formats(image, funcs):
    """Per-device .fse layout, keyed by the .fse file's base name."""
    def per_device(name):
        body = funcs[name]
        index = {addr: n for n, (addr, _) in enumerate(body)}
        return body, index, dict(jump_tables(image, body))

    paths, path_index, path_cases = per_device('devToFsePath')
    fuse, fuse_index, fuse_cases = per_device('fuse')
    wire, wire_index, wire_cases = per_device('wire')
    table, table_index, table_cases = per_device('table')

    signed = set()
    for _, text in table[table_index[table_cases[0x43]]:]:
        if CTOR.search(text):
            break
        if cmp_ := re.match(r'cmpl\s+\$0x([0-9a-f]+),-0x[0-9a-f]+\(%rbp\)', text):
            signed.add(int(cmp_[1], 16))

    devices = {}
    for code, target in sorted(path_cases.items()):
        name = None
        for _, text in paths[path_index[target]:path_index[target] + 40]:
            if rip := RIP.search(text):
                s = image.cstr(int(rip[2], 16))
                if s.endswith('.fse'):
                    name = os.path.basename(s)[:-4]
            if text.startswith('jmp'):
                break
        if name is None:
            continue
        devices[name] = {'dev_type': code,
                         'fuse_row': row_bytes_at(fuse, fuse_index[fuse_cases[code]]) // 2,
                         'wire_row': row_bytes_at(wire, wire_index[wire_cases[code]]) // 2,
                         'table_0x43': 'signedlogicinfo' if code in signed else 'logicinfo'}
    return devices


TABLE_KIND = {'fseBfdArrayTable': 'grid', 'fseFuseTable': 'fuse', 'fseWireTable': 'wire',
              'fseWireSearchTable': 'wiresearch', 'fseConstTable': 'const',
              'fseSInfoValueTable': 'shortval', 'fseAloneNodeTable': 'alonenode',
              'fseLogicInfoTable': 'logicinfo', 'fseSignedLogicInfoTable': 'signedlogicinfo',
              'fseLFuseValueTable': 'longfuse', 'fseLInfoValueTable': 'longval',
              'fseDrpFuseTable': 'drpfuse'}


def write_formats(types, devices):
    path = FORMATS_PATH
    kinds = {t: TABLE_KIND[c] for c, ts in types.items() if c in TABLE_KIND for t in ts}
    with open(path, 'w') as f:
        f.write('# Generated by tools/gowin_extract.py extract. Do not edit.\n\n')
        f.write('# .fse table type -> kind, from fseFileData::readOneTable\n')
        f.write('TABLE_KINDS = {\n')
        for t in sorted(kinds):
            f.write(f'    0x{t:02x}: {kinds[t]!r},\n')
        f.write('}\n\n# device -> (fuse row, wire row, kind of table 0x43)\n')
        f.write('DEVICE_FORMATS = {\n')
        for name, d in sorted(devices.items()):
            f.write(f"    {name!r}: ({d['fuse_row']}, {d['wire_row']}, {d['table_0x43']!r}),\n")
        f.write('}\n')
    print(f'{len(kinds)} table types, {len(devices)} devices -> {path}')


def main(argv):
    if len(argv) == 4 and argv[1] == 'extract':
        extract(argv[2], argv[3])
        return 0
    if len(argv) in (3, 4) and argv[1] == 'check-attrids':
        default = os.path.join(os.path.dirname(__file__), '..', 'apycula', 'attrids.py')
        return check_attrids(argv[2], argv[3] if len(argv) == 4 else default)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
