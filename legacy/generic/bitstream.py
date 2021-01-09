from write_fasm import *
import re
from apycula import codegen

# Need to tell FASM generator how to write parameters
# (celltype, parameter) -> ParameterConfig
param_map = {
	("GENERIC_SLICE", "K"): ParameterConfig(write=False),
	("GENERIC_SLICE", "INIT"): ParameterConfig(write=True, numeric=True, width=2**4),
	("GENERIC_SLICE", "FF_USED"): ParameterConfig(write=True, numeric=True, width=1),

	("GENERIC_IOB", "INPUT_USED"): ParameterConfig(write=True, numeric=True, width=1),
	("GENERIC_IOB", "OUTPUT_USED"): ParameterConfig(write=True, numeric=True, width=1),
	("GENERIC_IOB", "ENABLE_USED"): ParameterConfig(write=True, numeric=True, width=1),
}

#gen_7_ PLACE_IOT8[B] //IBUF
#gen_4_ PLACE_R13C6[0][A]
def write_posp(f):
    belre = re.compile(r"R(\d+)C(\d+)_(SLICE|IOB)(\w)")
    namere = re.compile(r"\W+")
    for name, cell in ctx.cells:
        row, col, typ, idx = belre.match(cell.bel).groups()
        row = int(row)
        col = int(col)
        name = namere.sub('_', name)
        if typ == 'SLICE':
            idx = int(idx)
            cls = idx//2
            side = ['A', 'B'][idx%2]
            lutname = name + "_LUT"
            f.write(f"{lutname} PLACE_R{row}C{col}[{cls}][{side}]\n")

            lut = codegen.Primitive("LUT4", lutname)
            #lut.params["INIT"] = f"16'b{val:016b}"
            lut.portmap['F'] = f"R{row}C{col}_F{idx}"
            lut.portmap['I0'] = f"R{row}C{col}_A{idx}"
            lut.portmap['I1'] = f"R{row}C{col}_B{idx}"
            lut.portmap['I2'] = f"R{row}C{col}_C{idx}"
            lut.portmap['I3'] = f"R{row}C{col}_D{idx}"
            mod.wires.update(lut.portmap.values())
            mod.primitives[lutname] = lut

            if int(cell.params['FF_USED'], 2):
                dffname = name + "_DFF"
                f.write(f"{dffname} PLACE_R{row}C{col}[{cls}][{side}]\n")

                lut = codegen.Primitive("DFF", dffname)
                lut.portmap['D'] = f"R{row}C{col}_F{idx}"
                lut.portmap['Q'] = f"R{row}C{col}_Q{idx}"
                lut.portmap['CLK'] = f"R{row}C{col}_CLK{idx}"
                mod.wires.update(lut.portmap.values())
                mod.primitives[dffname] = lut
        elif typ == 'IOB':
            if row == 1:
                edge = 'T'
                num = col
            elif col == 1:
                edge = 'L'
                num = row
            elif col == 47: #TODO parameterize
                edge = 'R'
                num = row
            else:
                edge = 'B'
                num = col
            f.write(f"{name} PLACE_IO{edge}{num}[{idx}]\n")

            iob = codegen.Primitive("IOBUF", name)
            iob.portmap['I'] = f"R{row}C{col}_I{idx}"
            iob.portmap['O'] = f"R{row}C{col}_O{idx}"
            iob.portmap['IO'] = f"R{row}C{col}_IO{idx}"
            iob.portmap['OEN'] = f"R{row}C{col}_OEN{idx}"
            mod.wires.update(iob.portmap.values())
            mod.inouts.add(f"R{row}C{col}_IO{idx}")
            mod.primitives[name] = iob


with open("blinky.fasm", "w") as f:
	write_fasm(ctx, param_map, f)

mod = codegen.Module()
with open("blinky.posp", "w") as f:
    write_posp(f)

with open("blinky.vm", "w") as f:
    mod.write(f)

#code.interact(local=locals())
