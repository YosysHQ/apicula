from __future__ import annotations
import sys
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Primitive:
    name: str
    num: int
    num_ins: int
    obj: list[int]
    ins: list[list[int]]


@dataclass
class Grid:
    num_rows: int
    num_cols: int
    center_x: int
    center_y: int
    rows: list[list[str]]


class Datfile:
    def __init__(self, path: Path):
        self.data = path.read_bytes()
        self._cur = 0x026060
        self.grid = self.read_grid()
        self.primitives = self.read_primitives()
        self.portmap = self.read_portmap()
        self.compat_dict = self.read_portmap()
        self.compat_dict.update(self.read_io())
        self.compat_dict.update(self.read_something())
        self.cmux_ins: dict[int, list[int]] = self.read_io()['CmuxIns']

    def read_u8(self):
        v = self.data[self._cur]
        self._cur += 1
        return v

    def read_i16(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 2], "little", signed=True)
        self._cur += 2
        return v

    def read_u16(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 2], "little")
        self._cur += 2
        return v

    def read_u8_at(self, pos):
        return self.data[pos]

    def read_u32_at(self, pos):
        return int.from_bytes(self.data[pos : pos + 4], "little")

    def read_i32(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 4], "little", signed=True)
        self._cur += 4
        return v

    def read_u32(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 4], "little")
        self._cur += 4
        return v

    def read_u64(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 8], "little")
        self._cur += 8
        return v

    def read_arr8(self, num: int) -> list[int]:
        arr = [self.read_u8() for _ in range(num)]
        return arr

    def read_arr16(self, num: int) -> list[int]:
        arr = [self.read_i16() for _ in range(num)]
        return arr

    def read_arr32(self, num: int) -> list[int]:
        arr = [self.read_i32() for _ in range(num)]
        return arr

    def read_arr8_with_padding(self, num: int, of_which_meaningful: int) -> list[int]:
        arr = self.read_arr8(num)
        for i in range(of_which_meaningful, num):
            assert arr[i] == 0
        return arr[:of_which_meaningful]

    def read_arr16_with_padding(self, num: int, of_which_meaningful: int) -> list[int]:
        arr = self.read_arr16(num)
        for i in range(of_which_meaningful, num):
            assert arr[i] == -1
        return arr[:of_which_meaningful]

    def read_arr32_with_padding(self, num: int, of_which_meaningful: int) -> list[int]:
        arr = self.read_arr32(num)
        for i in range(of_which_meaningful, num):
            assert arr[i] == 0
        return arr[:of_which_meaningful]

    def read_primitive(self, name: str) -> Primitive:
        num = self.read_u8()
        num_ins = self.read_u8()
        ins = []
        for _ in range(num):
            ins.append(self.read_arr16(num_ins))
        obj = self.read_arr16(num)
        return Primitive(name, num, num_ins, obj, ins)

    def read_primitives(self) -> list[Primitive]:
        self._cur = 0xC8
        ret = []
        primitives = [
            "Lut",
            "X0",
            "X1",
            "X2",
            "X8",
            "Clk",
            "Lsrs",
            "Ce",
            "Sel",
            "X11",
        ]
        for p in primitives:
            ret.append(self.read_primitive(p))

        assert self._cur == 0x166E, f"Expected to be at 0x166e but am at 0x{self._cur:x}"
        return ret

    def read_grid(self) -> Grid:
        self._cur = 0x026060
        grid_h = self.read_u16()
        grid_w = self.read_u16()
        cc_y = self.read_u16()
        cc_x = self.read_u16()
        rows = []
        grid_mapping = {
            (0, 0): " ",  # empty
            (1, 1): "I",  # I/O
            (2, 1): "L",  # LVDS (GW2A* only)
            (3, 1): "R",  # routing?
            (4, 0): "c",  # CFU, disabled
            (4, 1): "C",  # CFU
            (5, 1): "M",  # CFU with RAM option
            (6, 0): "b",  # blockram padding
            (6, 1): "B",  # blockram
            (7, 0): "d",  # dsp padding
            (7, 1): "D",  # dsp
            (8, 0): "p",  # pll padding
            (8, 1): "P",  # pll
            (9, 1): "Q",  # dll
        }
        for y in range(grid_h):
            row = []
            for x in range(grid_w):
                idx = y * 200 + x
                a = self.read_u32_at(5744 + 4 * idx)
                b = self.read_u8_at(125744 + idx)
                c = grid_mapping[a, b]

                if x == cc_x and y == cc_y:
                    assert c == "b"

                row.append(c)
            rows.append(row)
        return Grid(grid_h, grid_w, cc_x, cc_y, rows)

    def read_mult(self, num) -> list[tuple[int, int, int, int]]:
        ret = []
        for _ in range(num):
            a = self.read_i16()
            b = self.read_i16()
            c = self.read_i16()
            d = self.read_i16()
            ret.append((a, b, c, d))
        return ret

    def read_outs(self, num) -> list[tuple[int, int]]:
        ret = []
        for _ in range(num):
            a = self.read_i16()
            b = self.read_i16()
            c = self.read_i16()
            ret.append((a, b, c))
        return ret

    def read_clkins(self, num) -> list[tuple[int, int]]:
        ret = []
        for _ in range(num):
            a = self.read_i16()
            b = self.read_i16()
            ret.append((a, b))
        return ret

    def read_portmap(self) -> dict:
        self._cur = 0x55D2C
        # These are ordered by position in the file
        ret = {
            "IobufAIn": self.read_u16(),
            "IobufAOut": self.read_u16(),
            "IobufAOE": self.read_u16(),
            "IObufAIO": self.read_u16(),
            "IobufBIn": self.read_u16(),
            "IobufBOut": self.read_u16(),
            "IobufBOE": self.read_u16(),
            "IObufBIO": self.read_u16(),
            "IobufIns": self.read_arr16(10),
            "IobufOuts": self.read_arr16(10),
            "IobufOes": self.read_arr16(10),
            "IologicAIn": self.read_arr16(0x31),
            "IologicAOut": self.read_arr16(0x16),
            "IologicBIn": self.read_arr16(0x31),
            "IologicBOut": self.read_arr16(0x16),
            "BsramIn": self.read_arr16(0x84),
            "BsramOut": self.read_arr16(0x48),
            "BsramInDlt": self.read_arr16(0x84),
            "BsramOutDlt": self.read_arr16(0x48),
            "SsramIO": self.read_arr16(0x1C),
            "PllIn": self.read_arr16(0x24),
            "PllOut": self.read_arr16(0x5),
            "PllInDlt": self.read_arr16(0x24),
            "PllOutDlt": self.read_arr16(0x5),
            "PllClkin": self.read_clkins(6),
            "SpecPll0Ins": self.read_arr16(108),
            "SpecPll0Outs": self.read_arr16(15),
            "SpecPll0Clkin": self.read_arr16(18),
            "SpecPll1Ins": self.read_arr16(108),
            "SpecPll1Outs": self.read_arr16(15),
            "SpecPll1Clkin": self.read_arr16(18),
            "DllIn": self.read_arr16(4),
            "DllOut": self.read_arr16(9),
            "SpecDll0Ins": self.read_arr16(12),
            "SpecDll0Outs": self.read_arr16(27),
            "SpecDll1Ins": self.read_arr16(12),
            "SpecDll1Outs": self.read_arr16(27),
            "MultIn": self.read_mult(0x4F),
            "MultOut": self.read_mult(0x48),
            "MultInDlt": self.read_mult(0x4F),
            "MultOutDlt": self.read_mult(0x48),
            "PaddIn": self.read_mult(0x4C),
            "PaddOut": self.read_mult(0x36),
            "PaddInDlt": self.read_mult(0x4C),
            "PaddOutDlt": self.read_mult(0x36),
            "AluIn": self.read_clkins(0xA9),
            "AluOut": self.read_clkins(0x6D),
            "AluInDlt": self.read_clkins(0xA9),
            "AluOutDlt": self.read_clkins(0x6D),
            "MdicIn": self.read_clkins(0x36),
            "MdicInDlt": self.read_clkins(0x36),
            "CtrlIn": self.read_mult(0xE),
            "CtrlInDlt": self.read_mult(0xE),
        }
        assert self._cur == 0x58272
        return ret

    def read_io(self):
        self._cur = 363662
        ret = {}
        ret["CiuConnection"] = {}
        for i in range(320):
            ret["CiuConnection"][i] = self.read_arr16(60)
        ret["CiuFanoutNum"] = self.read_arr16(320)

        ret["CiuBdConnection"] = {}
        for i in range(320):
            ret["CiuBdConnection"][i] = self.read_arr16(60)

        ret["CiuBdFanoutNum"] = self.read_arr16(320)

        ret["CiuCornerConnection"] = {}
        for i in range(320):
            ret["CiuCornerConnection"][i] = self.read_arr16(60)
        ret["CiuCornerFanoutNum"] = self.read_arr16(320)

        ret["CmuxInNodes"] = {}
        for i in range(106):
            ret["CmuxInNodes"][i] = self.read_arr16(73)

        ret["CmuxIns"] = {}
        for i in range(106):
            ret["CmuxIns"][i] = self.read_arr16(3)

        ret["DqsRLoc"] = self.read_arr16(0x16)
        ret["DqsCLoc"] = self.read_arr16(0x16)
        ret["JtagIns"] = self.read_arr16(5)
        ret["JtagOuts"] = self.read_arr16(11)
        ret["ClksrcIns"] = self.read_arr16(0x26)
        ret["ClksrcOuts"] = self.read_arr16(16)
        ret["UfbIns"] = self.read_outs(0x5A)
        ret["UfbOuts"] = self.read_outs(0x20)
        self._cur += 4
        ret["McuIns"] = self.read_outs(0x109)
        ret["McuOuts"] = self.read_outs(0x174)
        ret["EMcuIns"] = self.read_outs(0x10E)
        ret["EMcuOuts"] = self.read_outs(0x13F)
        ret["AdcIns"] = self.read_outs(0xF)
        ret["AdcOuts"] = self.read_outs(13)
        ret["Usb2PhyIns"] = self.read_outs(0x46)
        ret["Usb2PhyOuts"] = self.read_outs(0x2A)
        ret["Eflash128kIns"] = self.read_outs(0x39)
        ret["Eflash128kOuts"] = self.read_outs(0x21)
        ret["SpmiIns"] = self.read_outs(0x17)
        ret["SpmiOuts"] = self.read_outs(0x2F)
        ret["I3cIns"] = self.read_outs(0x26)
        ret["I3cOuts"] = self.read_outs(0x28)
        assert self._cur == 0x7BE5A, hex(self._cur)
        return ret

    def read_something(self):
        self._cur = 0x026068
        ret = {
            "Dqs": {},
            "Cfg": {},
            "SpecCfg": {},
            "Bank": {},
            "X16": {},
            "TrueLvds": {},
            "Type": {},
        }

        assert self._cur == 0x026068, hex(self._cur)
        ret["Dqs"]["TA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        assert self._cur == 0x261F8, hex(self._cur)
        ret["Dqs"]["BA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        assert self._cur == 0x26388, hex(self._cur)
        ret["Dqs"]["LA"] = self.read_arr16_with_padding(150, self.grid.num_rows)
        ret["Dqs"]["RA"] = self.read_arr16_with_padding(150, self.grid.num_rows)
        ret["Dqs"]["TB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Dqs"]["BB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Dqs"]["LB"] = self.read_arr16_with_padding(150, self.grid.num_rows)
        ret["Dqs"]["RB"] = self.read_arr16_with_padding(150, self.grid.num_rows)

        assert self._cur == 0x26b58, hex(self._cur)
        ret["Cfg"]["TA"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Cfg"]["BA"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Cfg"]["LA"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Cfg"]["RA"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Cfg"]["TB"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Cfg"]["BB"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Cfg"]["LB"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Cfg"]["RB"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["SpecCfg"]["IOL"] = self.read_arr32_with_padding(10, 10)
        ret["SpecCfg"]["IOR"] = self.read_arr32_with_padding(10, 10)
        assert self._cur == 0x28188, hex(self._cur)

        ret["Bank"]["TA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Bank"]["BA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Bank"]["LA"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["Bank"]["RA"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["Bank"]["TB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Bank"]["BB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["Bank"]["LB"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["Bank"]["RB"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["Bank"]["SpecIOL"] = self.read_arr16_with_padding(10, 10)
        ret["Bank"]["SpecIOR"] = self.read_arr16_with_padding(10, 10)

        ret["X16"]["TA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["X16"]["BA"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["X16"]["LA"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["X16"]["RA"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["X16"]["TB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["X16"]["BB"] = self.read_arr16_with_padding(200, self.grid.num_cols)
        ret["X16"]["LB"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["X16"]["RB"] = self.read_arr16_with_padding(150, self.grid.num_cols)
        ret["X16"]["SpecIOL"] = self.read_arr16_with_padding(10, 10)
        ret["X16"]["SpecIOR"] = self.read_arr16_with_padding(10, 10)
        assert self._cur == 0x297B8, hex(self._cur)

        ret["TrueLvds"]["TopA"] = self.read_arr8_with_padding(200, self.grid.num_cols)
        ret["TrueLvds"]["BottomA"] = self.read_arr8_with_padding(200, self.grid.num_cols)
        ret["TrueLvds"]["LeftA"] = self.read_arr8_with_padding(150, self.grid.num_rows)
        ret["TrueLvds"]["RightA"] = self.read_arr8_with_padding(150, self.grid.num_rows)
        ret["TrueLvds"]["TopB"] = self.read_arr8_with_padding(200, self.grid.num_cols)
        ret["TrueLvds"]["BottomB"] = self.read_arr8_with_padding(200, self.grid.num_cols)
        ret["TrueLvds"]["LeftB"] = self.read_arr8_with_padding(150, self.grid.num_rows)
        ret["TrueLvds"]["RightB"] = self.read_arr8_with_padding(150, self.grid.num_rows)
        ret["TrueLvds"]["SpecIOL"] = self.read_arr8_with_padding(10, 10)
        ret["TrueLvds"]["SpecIOR"] = self.read_arr8_with_padding(10, 10)

        ret["Type"]["TopA"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Type"]["BottomA"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Type"]["LeftA"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Type"]["RightA"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Type"]["TopB"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Type"]["BottomB"] = self.read_arr32_with_padding(200, self.grid.num_cols)
        ret["Type"]["LeftB"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        ret["Type"]["RightB"] = self.read_arr32_with_padding(150, self.grid.num_rows)
        return ret


if __name__ == "__main__":
    gowinhome = os.getenv("GOWINHOME")
    if not gowinhome:
        raise Exception("GOWINHOME not set")
    device = sys.argv[1]
    p = Path(f"{gowinhome}/IDE/share/device/{device}/{device}.dat")
    df = Datfile(p)
