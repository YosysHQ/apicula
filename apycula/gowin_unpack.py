import sys
import os
import re
import random
import numpy as np
from itertools import chain, count
import pickle
import argparse
import importlib.resources
from apycula import codegen
from apycula import chipdb
from apycula.bslib import read_bitstream
from apycula.wirenames import wirenames

# bank iostandards
# XXX default io standard may be board-dependent!
_banks = {0: "LVCMOS33", 1: "LVCMOS18", 2: "LVCMOS18", 3: "LVCMOS18"}

# noiostd --- this is the case when the function is called
# with iostd by default, e.g. from the clock fuzzer
# With normal gowun_unpack io standard is determined first and it is known.
def parse_tile_(db, row, col, tile, default=True, noalias=False, noiostd = True):
    print((row, col))
    tiledata = db.grid[row][col]
    bels = {}
    for name, bel in tiledata.bels.items():
        if name[0:3] == "IOB":
            if noiostd:
                iostd = ''
            else:
                iostd = _banks[chipdb.loc2bank(db, row, col)]
            # modebits
            modebits = set()
            for _, mode_rec in bel.iob_flags[iostd].items():
                modebits |= mode_rec.decode_bits
            # Here we don't use a mask common to all modes (it didn't work),
            # instead we try the longest bit sequence first.
            for mode, mode_rec in sorted(bel.iob_flags[iostd].items(),
                    key = lambda m: len(m[1].decode_bits), reverse = True):
                print(mode, mode_rec.decode_bits)
                mode_bits = {(row, col)
                             for row, col in mode_rec.decode_bits
                             if tile[row][col] == 1}
                print("read", mode_bits)
                if mode_rec.decode_bits == mode_bits:
                    bels.setdefault(name, set()).add(mode)
                    # mode found
                    break

            for flag, flag_parm in bel.iob_flags[iostd][mode].flags.items():
                flag_bits = {(row, col)
                              for row, col in flag_parm.mask
                              if tile[row][col] == 1}
                for opt, bits in flag_parm.options.items():
                    if bits == flag_bits:
                        bels.setdefault(name, set()).add(f"{flag}={opt}")
        else:
            mode_bits = {(row, col)
                         for row, col in bel.mode_bits
                         if tile[row][col] == 1}
            print(name, bel.mode_bits)
            print("read", mode_bits)
            for mode, bits in bel.modes.items():
                print(mode, bits)
                if bits == mode_bits and (default or bits):
                    bels.setdefault(name, set()).add(mode)
                    if name == "BANK":
                        # set iostd for bank
                        flag_bits = {(row, col)
                                      for row, col in bel.bank_mask
                                      if tile[row][col] == 1}
                        for iostd, bits in bel.bank_flags.items():
                            if bits == flag_bits:
                                _banks[chipdb.loc2bank(db, row, col)] = iostd
                                break
                        # mode found
                        break
        # simple flags
        for flag, bits in bel.flags.items():
            used_bits = {tile[row][col] for row, col in bits}
            if all(used_bits):
                bels.setdefault(name, set()).add(flag)

    pips = {}
    for dest, srcs in tiledata.pips.items():
        pip_bits = set().union(*srcs.values())
        used_bits = {(row, col)
                     for row, col in pip_bits
                     if tile[row][col] == 1}
        for src, bits in srcs.items():
            # optionally ignore the defautl set() state
            if bits == used_bits and (default or bits):
                pips[dest] = src

    clock_pips = {}
    for dest, srcs in tiledata.clock_pips.items():
        pip_bits = set().union(*srcs.values())
        used_bits = {(row, col)
                     for row, col in pip_bits
                     if tile[row][col] == 1}
        for src, bits in srcs.items():
            # only report connection aliased to by a spine
            if bits == used_bits and (noalias or (row, col, src) in db.aliases):
                clock_pips[dest] = src

    return bels, pips, clock_pips


dffmap = {
    "DFF": None,
    "DFFN": None,
    "DFFS": "SET",
    "DFFR": "RESET",
    "DFFP": "PRESET",
    "DFFC": "CLEAR",
    "DFFNS": "SET",
    "DFFNR": "RESET",
    "DFFNP": "PRESET",
    "DFFNC": "CLEAR",
}
iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OE"], "inouts": ["IO"]},
}

# OE -> OEN
def portname(n):
    if n == "OE":
        return "OEN"
    return n

_sides = "AB"
def tile2verilog(dbrow, dbcol, bels, pips, clock_pips, mod, cfg, cst, db):
    # db is 0-based, floorplanner is 1-based
    row = dbrow+1
    col = dbcol+1
    aliases = db.grid[dbrow][dbcol].aliases
    for dest, src in chain(pips.items(), aliases.items(), clock_pips.items()):
        srcg = chipdb.wire2global(row, col, db, src)
        destg = chipdb.wire2global(row, col, db, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

    belre = re.compile(r"(IOB|LUT|DFF|BANK|CFG)(\w*)")
    for bel, flags in bels.items():
        typ, idx = belre.match(bel).groups()

        if typ == "LUT":
            val = sum(1<<f for f in flags)
            name = f"R{row}C{col}_LUT4_{idx}"
            lut = codegen.Primitive("LUT4", name)
            lut.params["INIT"] = f"16'b{val:016b}"
            lut.portmap['F'] = f"R{row}C{col}_F{idx}"
            lut.portmap['I0'] = f"R{row}C{col}_A{idx}"
            lut.portmap['I1'] = f"R{row}C{col}_B{idx}"
            lut.portmap['I2'] = f"R{row}C{col}_C{idx}"
            lut.portmap['I3'] = f"R{row}C{col}_D{idx}"
            mod.wires.update(lut.portmap.values())
            mod.primitives[name] = lut
            cst.cells[name] = f"R{row}C{col}[{int(idx) // 2}][{_sides[int(idx) % 2]}]"
        elif typ == "DFF":
            kind, = flags # DFF only have one flag
            idx = int(idx)
            port = dffmap[kind]
            name = f"R{row}C{col}_{typ}E_{idx}"
            dff = codegen.Primitive(kind+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx//2}"
            dff.portmap['D'] = f"R{row}C{col}_F{idx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{idx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx//2}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx//2}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff
            cst.cells[name] = f"R{row}C{col}[{int(idx) // 2}][{_sides[int(idx) % 2]}]"
        elif typ == "IOB":
            try:
                kind, = flags.intersection(iobmap.keys())
            except ValueError:
                continue
            flags.remove(kind)
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            name = f"R{row}C{col}_{kind}_{idx}"
            wires = set(iobmap[kind]['wires'])
            ports = set(chain.from_iterable(iobmap[kind].values())) - wires

            iob = codegen.Primitive(kind, name)

            for port in wires:
                wname = portmap[port]
                iob.portmap[portname(port)] = f"R{row}C{col}_{wname}"

            for port in ports:
                iob.portmap[port] = f"R{row}C{col}_{port}{idx}"

            wnames = [f"R{row}C{col}_{portmap[w]}" for w in iobmap[kind]['wires']]
            mod.wires.update(wnames)
            for direction in ['inputs', 'outputs', 'inouts']:
                wnames = [f"R{row}C{col}_{w}{idx}" for w in iobmap[kind].get(direction, [])]
                getattr(mod, direction).update(wnames)
            mod.primitives[name] = iob
            # constraints
            pos = chipdb.loc2pin_name(db, dbrow, dbcol)
            bank = chipdb.loc2bank(db, dbrow, dbcol)
            cst.ports[name] = f"{pos}{idx}"
            iostd = _banks.get(bank)
            if iostd:
                cst.attrs.setdefault(name, {}).update({"IO_TYPE" : iostd})
            for flg in flags:
                name_val = flg.split('=')
                cst.attrs.setdefault(name, {}).update({name_val[0] : name_val[1]})

        elif typ == "CFG":
            for flag in flags:
                for name in cfg.settings.keys():
                    if name.startswith(flag):
                        cfg.settings[name] = 'true'

    # gnd = codegen.Primitive("GND", "mygnd")
    # gnd.portmap["G"] = "VSS"
    # mod.primitives["mygnd"] = gnd
    # vcc = codegen.Primitive("VCC", "myvcc")
    # vcc.portmap["V"] = "VCC"
    # mod.primitives["myvcc"] = vcc
    mod.assigns.append(("VCC", "1"))
    mod.assigns.append(("GND", "0"))

def default_device_config():
    return {
        "JTAG regular_io":          "false",
        "SSPI regular_io":          "false",
        "MSPI regular_io":          "false",
        "READY regular_io":         "false",
        "DONE regular_io":          "false",
        "RECONFIG_N regular_io":    "false",
        "MODE regular_io":          "false",
        "CRC_check": "true",
        "compress": "false",
        "encryption": "false",
        "security_bit_enable": "true",
        "bsram_init_fuse_print": "true",
        "download_speed": "250/100",
        "spi_flash_address": "0x00FFF000",
        "format": "txt",
        "background_programming": "false",
        "secure_mode": "false"}

def main():
    parser = argparse.ArgumentParser(description='Unpack Gowin bitstream')
    parser.add_argument('bitstream')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='unpack.v')
    parser.add_argument('-c', '--config', default='unpack.cfg')
    parser.add_argument('-s', '--cst', default='unpack.cst')

    args = parser.parse_args()

    with importlib.resources.open_binary("apycula", f"{args.device}.pickle") as f:
        db = pickle.load(f)

    bitmap = read_bitstream(args.bitstream)[0]
    bm = chipdb.tile_bitmap(db, bitmap)
    mod = codegen.Module()
    cfg = codegen.DeviceConfig(default_device_config())
    cst = codegen.Constraints()

    for (drow, dcol, dname), (srow, scol, sname) in db.aliases.items():
        src = f"R{srow+1}C{scol+1}_{sname}"
        dest = f"R{drow+1}C{dcol+1}_{dname}"
        mod.wires.update({src, dest})
        mod.assigns.append((dest, src))

    # banks first: need to know iostandards
    for pos in db.corners.keys():
        row, col = pos
        try:
            t = bm[(row, col)]
        except KeyError:
            continue
        bels, pips, clock_pips = parse_tile_(db, row, col, t)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cfg, cst, db)

    for idx, t in bm.items():
        row, col = idx
        # skip banks & dual pisn
        if (row, col) in db.corners:
            continue
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #if idx == (5, 0):
        #    from fuse_h4x import *
        #    fse = readFse(open("/home/pepijn/bin/gowin/IDE/share/device/GW1N-1/GW1N-1.fse", 'rb'))
        #    breakpoint()
        bels, pips, clock_pips = parse_tile_(db, row, col, t, noiostd = False)
        #print(bels)
        #print(pips)
        #print(clock_pips)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cfg, cst, db)

    with open(args.output, 'w') as f:
        mod.write(f)

    with open(args.config, 'w') as f:
        cfg.write(f)

    with open(args.cst, 'w') as f:
        cst.write(f)

if __name__ == "__main__":
    main()
