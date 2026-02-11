// bitstream.hpp - Bitstream generation and output
#pragma once

#include <string>
#include <vector>
#include <map>
#include <cstdint>

#include "chipdb_types.hpp"
#include "netlist.hpp"
#include "place.hpp"

namespace apycula {

// Tile bitmap: 2D array of bits (row x col)
using TileBitmap = std::vector<std::vector<uint8_t>>;
using BsramInitMap = std::vector<std::vector<uint8_t>>;

// Tilemap: (row, col) -> tile bitmap
using Tilemap = std::map<Coord, TileBitmap>;

// Complete bitstream data
struct Bitstream {
    std::vector<std::vector<uint8_t>> frames;
    std::vector<std::vector<uint8_t>> header;
    std::vector<std::vector<uint8_t>> footer;
    bool compressed = false;
    std::map<int, TileBitmap> extra_slots;
    // GW5A BSRAM init data (written separately, not appended to main bitmap)
    BsramInitMap gw5a_bsram_init_map;
    std::vector<Gw5aBsramInfo> gw5a_bsrams;
};

// Pack arguments - configuration flags passed through the tool chain.
// Mirrors the argparse flags from the Python gowin_pack.py.
struct PackArgs {
    std::string device;
    bool compress = false;
    bool jtag_as_gpio = false;
    bool sspi_as_gpio = false;
    bool mspi_as_gpio = false;
    bool ready_as_gpio = false;
    bool done_as_gpio = false;
    bool reconfign_as_gpio = false;
    bool cpu_as_gpio = false;
    bool i2c_as_gpio = false;
};

// Create empty tilemap from device
Tilemap create_tilemap(const Device& db);

// Convert tilemap to fuse bitmap
std::vector<std::vector<uint8_t>> tilemap_to_bitmap(const Device& db, const Tilemap& tilemap);

// Generate bitstream from device database and netlist.
// The PackArgs struct carries device name, compression flag, and dual-mode
// pin GPIO flags so that GSR and dual-mode pin fuses can be set.
Bitstream generate_bitstream(Device& db, const Netlist& netlist, const PackArgs& args);

// Write bitstream to file (.fs format)
void write_bitstream(const std::string& path, const Bitstream& bs);

// Write bitstream with GW5A BSRAM init data (separate block-based format)
void write_bitstream_gw5a(const std::string& path, const Bitstream& bs,
                          const BsramInitMap& bsram_init_map,
                          const std::vector<Gw5aBsramInfo>& gw5a_bsrams);

// CRC-16-Arc calculation
uint16_t crc16_arc(const uint8_t* data, size_t len);
uint16_t crc16_arc(const std::vector<uint8_t>& data);

// Bit matrix operations
TileBitmap create_tile_bitmap(int64_t height, int64_t width);
void set_bit(TileBitmap& bm, int64_t row, int64_t col);
void clear_bit(TileBitmap& bm, int64_t row, int64_t col);
void flip_bit(TileBitmap& bm, int64_t row, int64_t col);

// Matrix transformations (like Python bitmatrix)
std::vector<std::vector<uint8_t>> fliplr(const std::vector<std::vector<uint8_t>>& m);
std::vector<std::vector<uint8_t>> flipud(const std::vector<std::vector<uint8_t>>& m);
std::vector<std::vector<uint8_t>> transpose(const std::vector<std::vector<uint8_t>>& m);
std::vector<std::vector<uint8_t>> packbits(const std::vector<std::vector<uint8_t>>& m);
std::vector<uint8_t> packbits_flat(const std::vector<std::vector<uint8_t>>& m);
std::vector<std::vector<uint8_t>> zeros(size_t rows, size_t cols);
std::vector<std::vector<uint8_t>> ones(size_t rows, size_t cols);
std::vector<std::vector<uint8_t>> hstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b);
std::vector<std::vector<uint8_t>> vstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b);

// Isolate segments that nextpnr has marked for isolation.
// Parses SEG_WIRES_TO_ISOLATE net attributes and sets the corresponding
// alonenode_6 fuses in the tilemap.
void isolate_segments(const Netlist& netlist, const Device& db, Tilemap& tilemap);

// Set Global Set/Reset (GSR) fuses in the tilemap.
// Configures the GSR mode and related CFG fuses for the target device.
void set_gsr_fuses(const Device& db, Tilemap& tilemap, const PackArgs& args);

// Set dual-mode pin fuses in the tilemap.
// Handles JTAG_AS_GPIO, SSPI_AS_GPIO, MSPI_AS_GPIO, etc. based on
// the flags in PackArgs.
void set_dualmode_pin_fuses(const Device& db, Tilemap& tilemap, const PackArgs& args);

} // namespace apycula
