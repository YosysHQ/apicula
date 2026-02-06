// bitstream.cpp - Bitstream generation implementation
#include "bitstream.hpp"
#include "route.hpp"
#include "place.hpp"

#include <fstream>
#include <stdexcept>
#include <algorithm>

namespace apycula {

// CRC-16-Arc lookup table (polynomial 0x8005, reflected)
static const uint16_t crc_table[256] = {
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
    0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
    0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
    0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
    0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
    0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
    0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
    0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
    0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
    0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
    0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
    0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
    0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
    0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
    0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
    0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
    0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
    0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
    0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
    0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
    0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040
};

uint16_t crc16_arc(const uint8_t* data, size_t len) {
    uint16_t crc = 0;
    for (size_t i = 0; i < len; ++i) {
        crc = (crc >> 8) ^ crc_table[(crc ^ data[i]) & 0xFF];
    }
    return crc;
}

uint16_t crc16_arc(const std::vector<uint8_t>& data) {
    return crc16_arc(data.data(), data.size());
}

TileBitmap create_tile_bitmap(int64_t height, int64_t width) {
    return TileBitmap(height, std::vector<uint8_t>(width, 0));
}

void set_bit(TileBitmap& bm, int64_t row, int64_t col) {
    if (row >= 0 && row < static_cast<int64_t>(bm.size()) &&
        col >= 0 && col < static_cast<int64_t>(bm[row].size())) {
        bm[row][col] = 1;
    }
}

void clear_bit(TileBitmap& bm, int64_t row, int64_t col) {
    if (row >= 0 && row < static_cast<int64_t>(bm.size()) &&
        col >= 0 && col < static_cast<int64_t>(bm[row].size())) {
        bm[row][col] = 0;
    }
}

void flip_bit(TileBitmap& bm, int64_t row, int64_t col) {
    if (row >= 0 && row < static_cast<int64_t>(bm.size()) &&
        col >= 0 && col < static_cast<int64_t>(bm[row].size())) {
        bm[row][col] ^= 1;
    }
}

// Flip left-right
std::vector<std::vector<uint8_t>> fliplr(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<std::vector<uint8_t>> result = m;
    for (auto& row : result) {
        std::reverse(row.begin(), row.end());
    }
    return result;
}

// Flip up-down
std::vector<std::vector<uint8_t>> flipud(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<std::vector<uint8_t>> result = m;
    std::reverse(result.begin(), result.end());
    return result;
}

// Transpose
std::vector<std::vector<uint8_t>> transpose(const std::vector<std::vector<uint8_t>>& m) {
    if (m.empty() || m[0].empty()) return {};
    size_t rows = m.size();
    size_t cols = m[0].size();
    std::vector<std::vector<uint8_t>> result(cols, std::vector<uint8_t>(rows));
    for (size_t i = 0; i < rows; ++i) {
        for (size_t j = 0; j < cols; ++j) {
            result[j][i] = m[i][j];
        }
    }
    return result;
}

// Pack bits into bytes (each row)
std::vector<std::vector<uint8_t>> packbits(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<std::vector<uint8_t>> result;
    for (const auto& row : m) {
        std::vector<uint8_t> packed;
        for (size_t i = 0; i < row.size(); i += 8) {
            uint8_t byte = 0;
            for (size_t j = 0; j < 8 && i + j < row.size(); ++j) {
                byte |= (row[i + j] & 1) << (7 - j);
            }
            packed.push_back(byte);
        }
        result.push_back(std::move(packed));
    }
    return result;
}

std::vector<std::vector<uint8_t>> zeros(size_t rows, size_t cols) {
    return std::vector<std::vector<uint8_t>>(rows, std::vector<uint8_t>(cols, 0));
}

std::vector<std::vector<uint8_t>> ones(size_t rows, size_t cols) {
    return std::vector<std::vector<uint8_t>>(rows, std::vector<uint8_t>(cols, 1));
}

std::vector<std::vector<uint8_t>> hstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b) {
    if (a.size() != b.size()) {
        throw std::runtime_error("hstack: row count mismatch");
    }
    std::vector<std::vector<uint8_t>> result;
    for (size_t i = 0; i < a.size(); ++i) {
        std::vector<uint8_t> row = a[i];
        row.insert(row.end(), b[i].begin(), b[i].end());
        result.push_back(std::move(row));
    }
    return result;
}

std::vector<std::vector<uint8_t>> vstack(const std::vector<std::vector<uint8_t>>& a,
                                          const std::vector<std::vector<uint8_t>>& b) {
    std::vector<std::vector<uint8_t>> result = a;
    result.insert(result.end(), b.begin(), b.end());
    return result;
}

Tilemap create_tilemap(const Device& db) {
    Tilemap tilemap;
    for (size_t row = 0; row < db.rows(); ++row) {
        for (size_t col = 0; col < db.cols(); ++col) {
            const auto& tile = db.get_tile(row, col);
            tilemap[{static_cast<int64_t>(row), static_cast<int64_t>(col)}] =
                create_tile_bitmap(tile.height, tile.width);
        }
    }
    return tilemap;
}

std::vector<std::vector<uint8_t>> tilemap_to_bitmap(const Device& db, const Tilemap& tilemap) {
    // Calculate total dimensions
    int64_t total_height = db.height();
    int64_t total_width = db.width();

    auto bitmap = zeros(total_height, total_width);

    // Copy each tile to the right position
    int64_t y_offset = 0;
    for (size_t row = 0; row < db.rows(); ++row) {
        const auto& first_tile = db.get_tile(row, 0);
        int64_t x_offset = 0;
        for (size_t col = 0; col < db.cols(); ++col) {
            const auto& tile = db.get_tile(row, col);
            auto it = tilemap.find({static_cast<int64_t>(row), static_cast<int64_t>(col)});
            if (it != tilemap.end()) {
                const auto& tile_bm = it->second;
                for (size_t ty = 0; ty < tile_bm.size(); ++ty) {
                    for (size_t tx = 0; tx < tile_bm[ty].size(); ++tx) {
                        bitmap[y_offset + ty][x_offset + tx] = tile_bm[ty][tx];
                    }
                }
            }
            x_offset += tile.width;
        }
        y_offset += first_tile.height;
    }
    return bitmap;
}

Bitstream generate_bitstream(Device& db, const Netlist& netlist, const std::string& device, bool compress) {
    Bitstream bs;
    bs.compressed = compress;
    bs.header = db.cmd_hdr;
    bs.footer = db.cmd_ftr;

    // Create tilemap
    auto tilemap = create_tilemap(db);

    // Route nets
    route_nets(db, netlist, tilemap, device);

    // Place cells
    place_cells(db, netlist, tilemap, device);

    // Set constant fuses
    for (size_t row = 0; row < db.rows(); ++row) {
        for (size_t col = 0; col < db.cols(); ++col) {
            const auto& tile = db.get_tile(row, col);
            auto it = db.const_fuses.find(tile.ttyp);
            if (it != db.const_fuses.end()) {
                auto& tile_bm = tilemap[{static_cast<int64_t>(row), static_cast<int64_t>(col)}];
                for (const auto& [brow, bcol] : it->second) {
                    set_bit(tile_bm, brow, bcol);
                }
            }
        }
    }

    // Convert tilemap to bitmap
    auto main_map = tilemap_to_bitmap(db, tilemap);

    // For GW5A series, transpose
    bool is_gw5 = (device == "GW5A-25A" || device == "GW5AST-138C");
    if (is_gw5) {
        main_map = transpose(main_map);
    }

    // Generate frames with CRC
    auto bitmap = fliplr(main_map);
    auto packed = packbits(bitmap);

    for (const auto& row : packed) {
        std::vector<uint8_t> frame = row;
        // Add CRC placeholder
        uint16_t crc = crc16_arc(frame);
        frame.push_back(crc & 0xFF);
        frame.push_back((crc >> 8) & 0xFF);
        // Add padding (48 bits = 6 bytes of 0xFF)
        for (int i = 0; i < 6; ++i) {
            frame.push_back(0xFF);
        }
        bs.frames.push_back(std::move(frame));
    }

    // Update frame count in header
    size_t frame_count = bs.frames.size();
    if (!bs.header.empty() && bs.header.back().size() >= 4) {
        bs.header.back()[2] = (frame_count >> 8) & 0xFF;
        bs.header.back()[3] = frame_count & 0xFF;
    }

    // Calculate checksum
    auto flat_bs = fliplr(main_map);
    auto packed_bs = packbits(flat_bs);
    uint64_t sum = 0;
    for (const auto& row : packed_bs) {
        for (size_t i = 0; i + 1 < row.size(); i += 2) {
            sum += (row[i] << 8) + row[i + 1];
        }
    }
    uint16_t checksum = sum & 0xFFFF;

    // Set checksum in footer
    if (bs.footer.size() > 1 && bs.footer[1].size() >= 8) {
        bs.footer[1][6] = checksum & 0xFF;
        bs.footer[1][7] = (checksum >> 8) & 0xFF;
    }

    return bs;
}

void write_bitstream(const std::string& path, const Bitstream& bs) {
    std::ofstream file(path);
    if (!file) {
        throw std::runtime_error("Could not open output file: " + path);
    }

    // Helper to write a byte as 8 binary digits
    auto write_byte = [&file](uint8_t b) {
        for (int i = 7; i >= 0; --i) {
            file << ((b >> i) & 1);
        }
    };

    // Write header lines
    for (const auto& line : bs.header) {
        for (uint8_t b : line) {
            write_byte(b);
        }
        file << '\n';
    }

    // Write frame data
    for (const auto& frame : bs.frames) {
        for (uint8_t b : frame) {
            write_byte(b);
        }
        file << '\n';
    }

    // Write footer lines
    for (const auto& line : bs.footer) {
        for (uint8_t b : line) {
            write_byte(b);
        }
        file << '\n';
    }
}

} // namespace apycula
