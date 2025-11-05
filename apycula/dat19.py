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
    inputs: list[int]
    input_src: list[list[int]]


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
        self._cur = 0x07b4a4
        partType = self.read_u16()

        self.grid = self.read_grid()
        self.primitives = self.read_primitives()
        self.compat_dict = {}
        self.portmap = self.read_portmap()
        self.compat_dict = self.read_portmap()

        if partType == 0:       # 1/2 Series
            self.compat_dict.update(self.read_something())
        elif partType == 1:
            print(f"PartType {partType} is not supported")

        elif partType == 2:  # 5 Series
            self.gw5aStuff = self.read_5Astuff()
            self.compat_dict.update(self.read_something5A())

        elif partType == 4:
            print(f"PartType {partType} is not supported")

        self.compat_dict.update(self.read_io())
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

    def read_arr16_at(self, num:int, base:int, offset:int):
        ret = []

        for n in range(num):
            self._cur = (n + base) * 2 + offset
            ret.append(self.read_i16())
        return ret

    def read_arr32_at(self, num:int, base:int, offset:int):
        ret = []

        for n in range(num):
            self._cur = (n + base) * 4 + offset
            ret.append(self.read_i32())
        return ret


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
        grid_h = self.read_u16() # chipRows_
        grid_w = self.read_u16() # chipCols_
        cc_y = self.read_u16() # hiq_
        cc_x = self.read_u16() # viq_
        # 26068
        rows = []
        grid_mapping = {
            (0, 0): " ",  # empty
            (1, 0): "1",  # unknown
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
            (10, 0): "2", # unknown
            (10, 1): "3", # unknown
            (11, 1): "4", # unknown
            (12, 1): "5"  # unknown
        }
        for y in range(grid_h):
            row = []
            for x in range(grid_w):
                idx = y * 200 + x
                a = self.read_u32_at(5744 + 4 * idx)
                b = self.read_u8_at(125744 + idx)
                c = grid_mapping[a, b]

                if (a,b) not in grid_mapping.keys():
                    print("no grid_mapping key for coords: ", a, b)
                #if x == cc_x and y == cc_y:
                #    assert c == "b"

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

    def read_scaledGrid16(self, numRows, numCols, rowScaling, colScaling, baseOffset):
        ret = []

        for row in range(numRows):
            rowArr = []
            for col in range(numCols):
                self._cur = (row * rowScaling) + (col * colScaling * 2) + baseOffset
                rowArr.append(self.read_u16())
            ret.append(rowArr)
        return ret

    def read_scaledGrid16i(self, numRows, numCols, rowScaling, colScaling, baseOffset):
        ret = []

        for row in range(numRows):
            rowArr = []
            for col in range(numCols):
                self._cur = (row * rowScaling) + (col * colScaling * 2) + baseOffset
                rowArr.append(self.read_i16())
            ret.append(rowArr)
        return ret

    def read_5Astuff(self) -> dict:
        RSTable5ATOffset = 0x7b4a8
        ret = { }

        #These are set (not read from file), but can't find reference
        #ret["UNKNOWN"] = 0x1d
        #ret["UNKNOWN"] = 0x1d
        #ret["UNKNOWN"] = 0x16
        #ret["UNKNOWN"] = 0x16
        #ret["UNKNOWN"] = 0xe

        self._cur = RSTable5ATOffset + 0x24be0
        ret["TopHiq"] = self.read_u16()
        ret["TopViq"] = self.read_u16()
        ret["BotHiq"] = self.read_u16()
        ret["BotViq"] = self.read_u16()

        ret["PllIn"]                = self.read_arr16_at(0xd8, 0, RSTable5ATOffset + 0x1b58)
        ret["PllOut"]               = self.read_arr16_at(0x20, 0, RSTable5ATOffset + 0x1d08)
        ret["PllInDlt"]             = self.read_arr16_at(0xd8, 0, RSTable5ATOffset + 0x1d48)
        ret["PllOutDlt"]            = self.read_arr16_at(0x20, 0, RSTable5ATOffset + 0x1ef8)

        ret["5ATIOLogicAIn"]        = self.read_arr16_at(0x3e, RSTable5ATOffset + 0x1880, 0)
        ret["5ATIOLogicBIn"]        = self.read_arr16_at(0x3e, RSTable5ATOffset + 0x18b8, 0xc)
        ret["5ATIOLogicAOut"]       = self.read_arr16_at(0x27, RSTable5ATOffset + 0x18f8, 8)
        ret["5ATIOLogicBOut"]       = self.read_arr16_at(0x27, RSTable5ATOffset + 0x1920, 6)
        ret["5ATIODelayAOut"]       = self.read_arr16_at(0x27, RSTable5ATOffset + 0x19c0, 0xc)
        ret["5ATIODelayBOut"]       = self.read_arr16_at(0x27, RSTable5ATOffset + 0x19e8, 10)
        ret["5ATIODelayAIn"]        = self.read_arr16_at(0x3e, RSTable5ATOffset + 0x1948, 0x4)
        ret["5ATIODelayBIn"]        = self.read_arr16_at(0x3e, RSTable5ATOffset + 0x1988, 0)

        # The following address offsets are also mentioned
        # All 5 are mentioned in FanIns, but only the 3rd and 4th are mentioned in FanOuts
        #ret["UNKNOWN"]             = self.read_scaledGrid16(0x20, 0x1d, 0x1d, RSTable5ATOffset + 0x3428, 0)
        #ret["UNKNOWN"]             = self.read_scaledGrid16(0xc, 0x16, 0x16, RSTable5ATOffset + 0x3b68, 0)
        #ret["UNKNOWN"]             = self.read_scaledGrid16(0xc, 0x16, 0x16, RSTable5ATOffset + 0x1e98, 8)
        #ret["UNKNOWN"]             = self.read_scaledGrid16(0x20, 0x16, 0x16, RSTable5ATOffset + 0x1fa0, 8)
        #ret["UNKNOWN"]             = self.read_scaledGrid16(0x8, 0xe, 0xe, RSTable5ATOffset + 0x2260, 8)

        ret["PllLTIns"]             = self.read_scaledGrid16(216, 3, 6, 1, RSTable5ATOffset + 0x1f38)
        ret["PllLTOuts"]            = self.read_scaledGrid16( 32, 3, 6, 1, RSTable5ATOffset + 0x2448)
        ret["PllLBIns"]             = self.read_scaledGrid16(216, 3, 6, 1, RSTable5ATOffset + 0x2508)
        ret["PllLBOuts"]            = self.read_scaledGrid16( 32, 3, 6, 1, RSTable5ATOffset + 0x2a18)
        ret["PllRTIns"]             = self.read_scaledGrid16(216, 3, 6, 1, RSTable5ATOffset + 0x2ad8)
        ret["PllRTOuts"]            = self.read_scaledGrid16( 32, 3, 6, 1, RSTable5ATOffset + 0x2fe8)
        ret["PllRBIns"]             = self.read_scaledGrid16(216, 3, 6, 1, RSTable5ATOffset + 0x30a8)
        ret["PllRBOuts"]            = self.read_scaledGrid16( 32, 3, 6, 1, RSTable5ATOffset + 0x35b8)

        """
        ret["MipiIns1"]             = self.read_scaledGrid16(0xc3, 3, 3, RSTable5ATOffset + 0x22d0, 0xe)
        ret["MipiIns2"]             = self.read_scaledGrid16(0xc3, 3, 3, RSTable5ATOffset + 0x2680, 0xe)
        ret["MipiOuts1"]            = self.read_scaledGrid16(0x76, 3, 3, RSTable5ATOffset + 0x2520, 0)
        ret["MipiOuts2"]            = self.read_scaledGrid16(0x76, 3, 3, RSTable5ATOffset + 0x28c8, 6)

        ret["MipiDPhyIns"]          = self.read_scaledGrid16(0xbb, 3, 3, RSTable5ATOffset + 0x91c0, 10)
        ret["MipiDPhyOuts"]         = self.read_scaledGrid16(0x6a, 3, 3, RSTable5ATOffset + 0x93f0, 0xc)

        ret["Gtrl12QuadDBIns1"]     = self.read_scaledGrid16(0x351, 3, 3, RSTable5ATOffset + 0x2a28, 10)
        ret["Gtrl12QuadDBIns2"]     = self.read_scaledGrid16(0x351, 3, 3, RSTable5ATOffset + 0x3420, 0)
        ret["Gtrl12QuadDBOuts1"]    = self.read_scaledGrid16(0x29c, 3, 3, RSTable5ATOffset + 0x6180, 0xc)
        ret["Gtrl12QuadDBOuts2"]    = self.read_scaledGrid16(0x29c, 3, 3, RSTable5ATOffset + 0x6958, 4)

        ret["Gtrl12PmacDBIns"]      = self.read_scaledGrid16(0xb68, 3, 3, RSTable5ATOffset + 0x3e10, 6)
        ret["Gtrl12PmacDBOuts"]     = self.read_scaledGrid16(0xb68, 3, 3, RSTable5ATOffset + 0x7128, 0xc)

        ret["Gtrl12UparDBIns"]      = self.read_scaledGrid16(0x69, 3, 3, RSTable5ATOffset + 0x6048, 6)
        ret["Gtrl12UparDBOuts"]     = self.read_scaledGrid16(0x69, 3, 3, RSTable5ATOffset + 0x8620, 10)
        """

        ret["Ae350SocIns"]          = self.read_scaledGrid16(0x1b1, 3, 3, RSTable5ATOffset + 0x86a0, 6)
        ret["Ae350SocOuts"]         = self.read_scaledGrid16(0x206, 3, 3, RSTable5ATOffset + 0x8bb0, 10)


        ret["CMuxTopInNodes"]       = self.read_scaledGrid16(0xbd, 0x54, 0x54, RSTable5ATOffset + 0x13fc4, 0)
        ret["CMuxBotInNodes"]       = self.read_scaledGrid16(0xbd, 0x54, 0x54, RSTable5ATOffset + 0x1bbcc, 0)
        ret["CMuxTopIns"]           = self.read_scaledGrid16i(0xbd, 3, 6, 1, RSTable5ATOffset + 0x24304)
        ret["CMuxBotIns"]           = self.read_scaledGrid16i(0xbd, 3, 6, 1, RSTable5ATOffset + 0x24772)

        ret["MipiIO1"]              = self.read_scaledGrid16(10, 0xf, 0xf, RSTable5ATOffset + 0x240e0, 0)
        ret["MipiIO2"]              = self.read_scaledGrid16(10, 0xf, 0xf, RSTable5ATOffset + 0x24176, 0)
        for n in range(5):
            ret["MipiIOName1_{n}"]  = self.read_scaledGrid16(10, 0xf, 0x4b, 5, RSTable5ATOffset + 0x2420c + n)
            ret["MipiIOName2_{n}"]  = self.read_scaledGrid16(10, 0xf, 0x4b, 5, RSTable5ATOffset + 0x244fa + n)
        ret["MipiBank1"]            = self.read_arr16_at(10, RSTable5ATOffset + 0x240e0, 0)
        ret["MipiBank2"]            = self.read_arr16_at(10, RSTable5ATOffset + 0x24176, 0)

        ret["QuadIO1"]              = self.read_scaledGrid16(15, 0xf, 0xf, RSTable5ATOffset + 0x2483c, 0)
        ret["QuafIO2"]              = self.read_scaledGrid16(15, 0xf, 0xf, RSTable5ATOffset + 0x24977, 0)
        for n in range(5):
            ret["QuadIOName1_{n}"]  = self.read_scaledGrid16(15, 0xf, 0x4b, 5, RSTable5ATOffset + 0x2483c + n)
            ret["QuafIOName2_{n}"]  = self.read_scaledGrid16(15, 0xf, 0xf, 5, RSTable5ATOffset + 0x24977 + n)
        ret["QuadBank1"]            = self.read_arr16_at(15, RSTable5ATOffset + 0x123f0, 8)
        ret["QuadBank2"]            = self.read_arr16_at(15, RSTable5ATOffset + 0x12408, 2)

        ret["AdcIO"]                = self.read_scaledGrid16(4, 0xf, 0xf, 1, RSTable5ATOffset + 0x25708)
        for n in range(5):
            ret["QuaAdcIOName_{n}"] = self.read_scaledGrid16(4, 0xf, 0x4b, 5, RSTable5ATOffset + 0x25744 + n)
        ret["AdcBank"]              = self.read_arr16_at(4, RSTable5ATOffset + 0x12b80, 0)

        ret["Mult12x12In"]          = self.read_arr16_at(0x18, RSTable5ATOffset + 0x9530, 8)
        ret["Mult12x12Out"]         = self.read_arr16_at(0x18, RSTable5ATOffset + 0x9560, 8)
        ret["Mult12x12InDlt"]       = self.read_arr16_at(0x18, RSTable5ATOffset + 0x9590, 8)
        ret["Mult12x12OutDlt"]      = self.read_arr16_at(0x18, RSTable5ATOffset + 0x95c0, 8)

        #The following are defined right next to Mult12x12 so are probably realted, but not referenced
        #ret["UNKNOWN"]              = self.read_arr16_at(0x18, RSTable5ATOffset + 0x12a6a, 0)
        #ret["UNKNOWN"]              = self.read_arr16_at(0x18, RSTable5ATOffset + 0x12b2a, 0)
        #ret["UNKNOWN"]              = self.read_arr16_at(0x18, RSTable5ATOffset + 0x12aca 0)
        #ret["UNKNOWN"]              = self.read_arr16_at(0x18, RSTable5ATOffset + 0x12b8a, 0)

        ret["MultAddAlu12x12In"]    = self.read_arr16_at(100, RSTable5ATOffset + 0x95f0, 8)
        ret["MultAddAlu12x12Out"]   = self.read_arr16_at(0x60, RSTable5ATOffset + 0x9658, 8)
        ret["MultAddAlu12x12InDlt"] = self.read_arr16_at(100, RSTable5ATOffset + 0x96b8, 8)
        ret["MultAddAlu12x12OutDlt"]= self.read_arr16_at(0x60, RSTable5ATOffset + 0x9718, 8)

        ret["Multalu27x18In"]       = self.read_arr16_at(0xca, RSTable5ATOffset + 0x9778, 8)
        ret["Multalu27x18InDlt"]    = self.read_arr16_at(0xca, RSTable5ATOffset + 0x99c0, 2)
        ret["Multalu27x18Out"]      = self.read_arr16_at(0x7b, RSTable5ATOffset + 0x9840, 0xc)
        ret["Multalu27x18OutDlt"]   = self.read_arr16_at(0x7b, RSTable5ATOffset + 0x9988, 6)
        ret["MultCtrlIn"]           = self.read_arr16_at(0x6, RSTable5ATOffset + 0x9a00, 0xc)
        ret["MultCtrlOut"]          = self.read_arr16_at(0x6, RSTable5ATOffset + 0x9a08, 8)

        ret["DqsRLoc"]              = self.read_arr16_at(0x2, RSTable5ATOffset + 0x12c38, 0)
        ret["DqsCLoc"]              = self.read_arr16_at(0x2, RSTable5ATOffset + 0x12c38, 4)

        ret["MDdrDllIns1"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12c38, 8)
        ret["MDdrDllIns2"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12cb0, 2)
        ret["MDdrDllIns3"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12d20, 0xc)
        ret["MDdrDllIns4"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12d98, 6)
        ret["MDdrDllIns5"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12e10, 0)
        ret["MDdrDllIns6"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12e30, 0xe)
        ret["MDdrDllIns7"]          = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12e58, 0xc)

        ret["S0DdrDllIns1"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12c60, 6)
        ret["S0DdrDllIns2"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12cd8, 0)
        ret["S0DdrDllIns3"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12d48, 10)
        ret["S0DdrDllIns4"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12dc0, 4)

        ret["S1DdrDllIns1"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12c88, 4)
        ret["S1DdrDllIns2"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12cf8, 0xe)
        ret["S1DdrDllIns3"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12d70, 8)
        ret["S1DdrDllIns4"]         = self.read_scaledGrid16(4, 3, 3, RSTable5ATOffset + 0x12de8, 2)

        ret["MDdrDllOuts1"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12c48, 0)
        ret["MDdrDllOuts2"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12cb8, 10)
        ret["MDdrDllOuts3"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12d30, 4)
        ret["MDdrDllOuts4"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12da0, 0xe)
        ret["MDdrDllOuts5"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12e18, 8)
        ret["MDdrDllOuts6"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12e40, 6)
        ret["MDdrDllOuts7"]         = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12e68, 4)

        ret["S0DdrDllOuts1"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12c68, 0xe)
        ret["S0DdrDllOuts2"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12ce0, 8)
        ret["S0DdrDllOuts3"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12d58, 2)
        ret["S0DdrDllOuts4"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12dc8, 0xc)

        ret["S1DdrDllOuts1"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12c90, 0xc)
        ret["S1DdrDllOuts2"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12d08, 6)
        ret["S1DdrDllOuts3"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12d80, 0)
        ret["S1DdrDllOuts4"]        = self.read_scaledGrid16(9, 3, 3, RSTable5ATOffset + 0x12df0, 10)

        ret["CmseraIns"]            = self.read_scaledGrid16(0x20, 3, 3, RSTable5ATOffset + 0x12e80, 10)
        ret["CmseraOuts"]           = self.read_scaledGrid16(0x60, 3, 3, RSTable5ATOffset + 0x12ee0, 10)

        ret["AdcLRCIns"]            = self.read_scaledGrid16(0x28, 3, 3, RSTable5ATOffset + 0x13000, 10)
        ret["AdcLRCOuts"]           = self.read_scaledGrid16(0x12, 3, 3, RSTable5ATOffset + 0x13078, 10)
        ret["AdcLRCCfgvsenctl1"]    = self.read_scaledGrid16(3, 3, 3, RSTable5ATOffset + 0x78000, 6)
        ret["AdcLRCCfgvsenctl2"]    = self.read_scaledGrid16(0x24, 3, 3, RSTable5ATOffset + 0x130b8, 8)
        ret["AdcULCOuts"]           = self.read_scaledGrid16(0x12, 3, 3, RSTable5ATOffset + 0x13128, 0)
        ret["AdcULCCfgvsenctl"]     = self.read_scaledGrid16(3, 3, 3, RSTable5ATOffset + 0x13158, 0xc)
        ret["Adc25kIns"]            = self.read_scaledGrid16i(25, 3, 6, 1, RSTable5ATOffset + 0x26dfe)
        ret["Adc25kOuts"]           = self.read_scaledGrid16i(28, 3, 6, 1, RSTable5ATOffset + 0x26e94)

        ret["CibFabricNode"]        = self.read_scaledGrid16(6, 3, 6, 1, RSTable5ATOffset + 0x27254)
        ret["SharedIOLogicIOBloc"]  = self.read_scaledGrid16(0x9c, 2, 2, RSTable5ATOffset + 0x13208, 0xe)

        ret["TopAMBGA121N"]         = self.read_arr16_at(200, RSTable5ATOffset + 0x2668e, 0)
        ret["TopBMBGA121N"]         = self.read_arr16_at(200, RSTable5ATOffset + 0x2694a, 0)
        ret["BottomAMBGA121N"]      = self.read_arr16_at(200, RSTable5ATOffset + 0x26756, 0)
        ret["BottomBMBGA121N"]      = self.read_arr16_at(200, RSTable5ATOffset + 0x26a12, 0)
        ret["TopAMBGA121NName"]     = self.read_scaledGrid16(200, 9, 9, RSTable5ATOffset + 0x26c06, 0)
        ret["BottomAMBGA121NName"]  = self.read_scaledGrid16(200, 9, 9, RSTable5ATOffset + 0x2730e, 0)
        ret["TopBMBGA121NName"]     = self.read_scaledGrid16(200, 9, 9, RSTable5ATOffset + 0x284a2, 0)
        ret["BottomBMBGA121NName"]  = self.read_scaledGrid16(200, 9, 9, RSTable5ATOffset + 0x28baa, 0)

        ret["LeftAMBGA121N"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x2681e, 0)
        ret["LeftBMBGA121N"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x26ada, 0)
        ret["RightAMBGA121N"]       = self.read_arr16_at(0x96, RSTable5ATOffset + 0x268b4, 0)
        ret["RightBMBGA121N"]       = self.read_arr16_at(0x96, RSTable5ATOffset + 0x26b70, 0)
        ret["LeftAMBGA121NName"]    = self.read_scaledGrid16(0x96, 9, 9, RSTable5ATOffset + 0x27a16, 0)
        ret["RightAMBGA121NName"]   = self.read_scaledGrid16(0x96, 9, 9, RSTable5ATOffset + 0x27f5c, 0)
        ret["LeftBMBGA121NName"]    =  self.read_scaledGrid16(0x96, 9, 9, RSTable5ATOffset + 0x292b2, 0)
        ret["RightBMBGA121NName"]   = self.read_scaledGrid16(0x96, 9, 9, RSTable5ATOffset + 0x297f8, 0)

        ret["SpineColumn"]          = self.read_arr16_at(8, RSTable5ATOffset + 0x14e98, 0xe)


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
            #"dsp12x12Ins": self.read_clkins(30),
            #"dsp12x12Outs": self.read_clkins(24),
            #"dsp12x12InDlt": self.read_clkins(30),
            #"dsp12x12OutDlt": self.read_clkins(24),
            #"dsp12x12SumIns": self.read_arr16(113),
            #"dsp12x12SumOuts": self.read_arr16(112),
            #"dsp12x12SumInDlt": self.read_arr16(113),
            #"dsp12x12SumOutDlt": self.read_arr16(112),
            #"dsp27x18Ins": self.read_arr16(163),
            #"dsp27x18Outs": self.read_arr16(139),
            #"dsp27x18InDlt": self.read_arr16(163),
            #"dsp27x18OutDlt": self.read_arr16(139),
            #"dspCtrlIns": self.read_clkins(6),
            #"dspCtrlInDlt": self.read_clkins(6),
        }
        assert self._cur == 0x58272 #0x58c8e
        return ret

    def read_io(self):
        self._cur = 0x58272
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
        ret["ClksrcIns"] = self.read_arr16(0x27)
        ret["ClksrcOuts"] = self.read_arr16(17)
        ret["UfbIns"] = self.read_outs(0x5A)
        ret["UfbOuts"] = self.read_outs(0x20)
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
        assert self._cur == 0x7b43e, hex(self._cur)
        return ret

    def read_something5A(self):
        RSTable5ATOffset = 0x7b4a8
        ret = {
            "Dqs": {},
            "Cfg": {},
        }
        ret["Dqs"]["TA"]        = self.read_arr16_at(200, RSTable5ATOffset + 0x9a10, 4)
        ret["Dqs"]["TB"]        = self.read_arr16_at(200, RSTable5ATOffset + 0x9cc8, 0xc)
        ret["Dqs"]["BA"]        = self.read_arr16_at(200, RSTable5ATOffset + 0x9ad8, 4)
        ret["Dqs"]["BB"]        = self.read_arr16_at(200, RSTable5ATOffset + 0x9d90, 0xc)
        ret["Dqs"]["LA"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x9ba0, 4)
        ret["Dqs"]["LB"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x9e58, 0xc)
        ret["Dqs"]["RA"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x9c38, 0)
        ret["Dqs"]["RA"]        = self.read_arr16_at(0x96, RSTable5ATOffset + 0x9ef0, 8)

        ret["Dqs"]["LeftIO"]    = self.read_arr16_at(0x16, RSTable5ATOffset + 0x9f88, 4)
        ret["Dqs"]["RightIO"]   = self.read_arr16_at(0x16, RSTable5ATOffset + 0x9fa0, 0)
        ret["Dqs"]["TopIO"]     = self.read_arr16_at(0x16, RSTable5ATOffset + 0x9fb0, 0xc)
        ret["Dqs"]["BottomIO"]  = self.read_arr16_at(0x16, RSTable5ATOffset + 0x9fc8, 8)

        ret["Cfg"]["TA"]        = self.read_arr32_at(200, RSTable5ATOffset, 0)
        ret["Cfg"]["BA"]        = self.read_arr32_at(200, RSTable5ATOffset + 200, 0)
        ret["Cfg"]["LA"]        = self.read_arr32_at(0x96, RSTable5ATOffset + 400, 0)
        ret["Cfg"]["RA"]        = self.read_arr32_at(0x96, RSTable5ATOffset + 224, 8)
        ret["Cfg"]["TB"]        = self.read_arr32_at(200, RSTable5ATOffset + 700, 0)
        ret["Cfg"]["BB"]        = self.read_arr32_at(200, RSTable5ATOffset + 900, 0)
        ret["Cfg"]["LB"]        = self.read_arr32_at(0x96, RSTable5ATOffset + 0x44c, 0)
        ret["Cfg"]["RB"]        = self.read_arr32_at(0x96, RSTable5ATOffset + 0x4e0, 8)

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
    dat = Datfile(p)

    grid = dat.read_grid()
    for rd in grid.rows:
        for rc in rd:
            print(rc, end='')
        print('')
