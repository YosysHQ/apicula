"""Parser implementation for the Gowin EDA .dat file, which contains the
tile layout of the FPGA"""
import io
import functools
import struct
import enum
from typing import NamedTuple, List, Any, Dict, Tuple

# The entire file is one big structure. These offsets are hence magic.
FILE_TILE_TYPE_OFFSET = 0x1670
FILE_TILE_ENABLED_OFFSET = 0x1EB30
FILE_GRID_INFO_OFFSET = 0x26060

# Maximum grid size supported in the file
GRID_COLS = 200
GRID_ROWS = 150


class GridInfo(NamedTuple):
    """basic metadata about the grid"""
    rows: int
    columns: int
    center_x: int
    center_y: int


class TileType(enum.Enum):
    EMPTY = 0
    IOBUF = 1
    LVDS = 2  # GW2A* only
    ROUTING = 3  # probably?
    CFU = 4  # Configuratble Function Unit
    CFU_RAM = 5  # CFU ram mode option
    BRAM = 6  # Block RAM
    DSP = 7  # Multiply/Accumulate
    PLL = 8  # Phase Locked Loop
    DLL = 9  # Delay Locked Loop


TILE_TYPE_CHARS = {
    TileType.EMPTY: " ",
    TileType.IOBUF: "I",
    TileType.LVDS: "L",
    TileType.ROUTING: "R",
    TileType.CFU: "C",
    TileType.CFU_RAM: "M",
    TileType.BRAM: "B",
    TileType.DSP: "D",
    TileType.PLL: "P",
    TileType.DLL: "Q",
}

TileGrid = List[List[Tuple[TileType, bool]]]


def tile_to_text_tile(tile: Tuple[TileType, bool]) -> str:
    """convert a tile into the character format required by the fuzzer json file"""
    type_char = TILE_TYPE_CHARS[tile[0]]
    return type_char if tile[1] else type_char.lower()


class DatFileReader:
    """reads the .dat file"""

    # TODO: file magic detection/early fail
    def __init__(self, f: memoryview) -> None:
        self._f = f

    @classmethod
    def from_file(cls, f: io.BufferedReader) -> "DatFileReader":
        """read a dat file from an open file"""
        return cls(memoryview(f.read()))

    def read_grid_info(self) -> GridInfo:
        grid_h, grid_w, cc_y, cc_x = struct.unpack_from(
            "<HHHH", self._f, offset=FILE_GRID_INFO_OFFSET
        )
        return GridInfo(grid_h, grid_w, cc_x, cc_y)

    def read_grid(self) -> TileGrid:
        """read the grid, which describes the tile layout"""
        grid_info = self.read_grid_info()
        # the grid area has a constant size of 200x150 tiles
        rows = []
        for y in range(GRID_ROWS):
            row = []
            for x in range(GRID_COLS):
                idx = y * 200 + x
                type_offset = FILE_TILE_TYPE_OFFSET + 4 * idx
                tile_type_id = struct.unpack_from("<I", self._f, offset=type_offset)[0]
                tile_type = TileType(tile_type_id)
                en_offset = FILE_TILE_ENABLED_OFFSET + idx
                tile_enabled = struct.unpack_from("?", self._f, offset=en_offset)[0]

                if x >= grid_info.columns:
                    if not tile_type == TileType.EMPTY:
                        raise ValueError(
                            f"expected empty tile outside of column range, found {tile_type}"
                        )
                    continue
                row.append((tile_type, tile_enabled))

            if y >= grid_info.rows:
                if not tile_type == TileType.EMPTY:
                    raise ValueError(
                        f"expected empty tile outside of row range, found {tile_type}"
                    )
                continue
            rows.append(row)

        return rows

    def print_grid(self) -> None:
        """print out grid in nice human-redable form"""
        grid_info = self.read_grid_info()
        # hack to print vertical counting header, zip(*it) translates a table
        for num in zip(*(str(i).rjust(3) for i in range(grid_info.columns))):
            print("   ", "".join(num))
        print()
        grid = [[tile_to_text_tile(t) for t in row] for row in self.read_grid()]
        for idx, row in enumerate(grid):
            print(f"{idx:3}", "".join(row))

    def to_json_dict(self) -> Dict[str, Any]:
        """return the dat as a dict suitable for dumping into .json for other tools"""
        res: Dict[str, Any] = {}
        grid_info = self.read_grid_info()
        res["rows"] = grid_info.rows
        res["cols"] = grid_info.columns
        res["center"] = (grid_info.center_x, grid_info.center_y)

        res["grid"] = [[tile_to_text_tile(t) for t in row] for row in self.read_grid()]
        return res
