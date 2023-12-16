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
        self._cur = 0x026060
        self.data = path.read_bytes()

    def read_u8(self):
        v = self.data[self._cur]
        self._cur += 1
        return v

    def read_u16(self):
        v = int.from_bytes(self.data[self._cur : self._cur + 2], "little")
        self._cur += 2
        return v

    def read_u8_at(self, pos):
        return self.data[pos]

    def read_u32_at(self, pos):
        return int.from_bytes(self.data[pos : pos + 4], "little")

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
        arr = [self.read_u16() for _ in range(num)]
        return arr

    def read_arr32(self, num: int) -> list[int]:
        arr = [self.read_u32() for _ in range(num)]
        return arr

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
        grid_h = df.read_u16()
        grid_w = df.read_u16()
        cc_y = df.read_u16()
        cc_x = df.read_u16()
        rows = []
        for y in range(grid_h):
            row = []
            for x in range(grid_w):
                idx = y * 200 + x
                a = self.read_u32_at(5744 + 4 * idx)
                b = self.read_u8_at(125744 + idx)
                c = {
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
                }[a, b]

                if x == cc_x and y == cc_y:
                    assert c == "b"

                row.append(c)
            rows.append(row)
        return Grid(grid_h, grid_w, cc_x, cc_y, rows)


gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")
device = sys.argv[1]
p = Path(f"{gowinhome}/IDE/share/device/{device}/{device}.dat")
df = Datfile(p)

print(df.read_grid())
print(df.read_primitives())
