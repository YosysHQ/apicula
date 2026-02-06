// bitstream.hpp - Bitstream generation and output
#pragma once

#include <string>
#include <vector>
#include <map>
#include <cstdint>

#include "chipdb_types.hpp"
#include "netlist.hpp"

namespace apycula {

// Tile bitmap: 2D array of bits (row x col)
using TileBitmap = std::vector<std::vector<uint8_t>>;

// Tilemap: (row, col) -> tile bitmap
using Tilemap = std::map<Coord, TileBitmap>;

// Complete bitstream data
struct Bitstream {
    std::vector<std::vector<uint8_t>> frames;
    std::vector<std::vector<uint8_t>> header;
    std::vector<std::vector<uint8_t>> footer;
    bool compressed = false;
    std::map<int, TileBitmap> extra_slots;
};

// Create empty tilemap from device
Tilemap create_tilemap(const Device& db);

// Convert tilemap to fuse bitmap
std::vector<std::vector<uint8_t>> tilemap_to_bitmap(const Device& db, const Tilemap& tilemap);

// Generate bitstream from device database and netlist
Bitstream generate_bitstream(Device& db, const Netlist& netlist, const std::string& device, bool compress);

// Write bitstream to file (.fs format)
void write_bitstream(const std::string& path, const Bitstream& bs);

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
std::vector<std::vector<uint8_t>> zeros(size_t rows, size_t cols);
std::vector<std::vector<uint8_t>> ones(size_t rows, size_t cols);
std::vector<std::vector<uint8_t>> hstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b);
std::vector<std::vector<uint8_t>> vstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b);

} // namespace apycula
