// bitstream.cpp - Bitstream generation implementation
#include "bitstream.hpp"
#include "route.hpp"
#include "place.hpp"
#include "fuses.hpp"
#include "attrids.hpp"

#include <cmath>
#include <fstream>
#include <iostream>
#include <regex>
#include <stdexcept>
#include <algorithm>

namespace apycula {

// ---------------------------------------------------------------------------
// CRC-16-Arc lookup table (polynomial 0x8005, reflected)
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Bit matrix primitive operations
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Matrix transformations (mirrors Python apycula/bitmatrix.py)
// ---------------------------------------------------------------------------

// Flip left-right (reverse each row)
std::vector<std::vector<uint8_t>> fliplr(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<std::vector<uint8_t>> result = m;
    for (auto& row : result) {
        std::reverse(row.begin(), row.end());
    }
    return result;
}

// Flip up-down (reverse row order)
std::vector<std::vector<uint8_t>> flipud(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<std::vector<uint8_t>> result = m;
    std::reverse(result.begin(), result.end());
    return result;
}

// Transpose (swap rows and columns)
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

// Pack bits into bytes per row (equivalent to Python packbits with axis=1).
// Each row of the input 2D bit matrix is independently packed into bytes.
// Bits are packed MSB-first: bit 0 of the row goes into bit 7 of byte 0.
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

// Pack bits into bytes with flattening (equivalent to Python packbits with
// axis=None).  All rows are concatenated into a single stream of bits which
// is then packed into bytes.  This is the variant used by the Python
// header_footer() checksum calculation.
std::vector<uint8_t> packbits_flat(const std::vector<std::vector<uint8_t>>& m) {
    std::vector<uint8_t> result;
    uint8_t byte = 0;
    int bit_cnt = 0;
    for (const auto& row : m) {
        for (uint8_t bit : row) {
            byte = static_cast<uint8_t>((byte << 1) | (bit & 1));
            ++bit_cnt;
            if (bit_cnt == 8) {
                result.push_back(byte);
                byte = 0;
                bit_cnt = 0;
            }
        }
    }
    // Flush any remaining bits (pad with zeros on the right, same as numpy)
    if (bit_cnt > 0) {
        byte = static_cast<uint8_t>(byte << (8 - bit_cnt));
        result.push_back(byte);
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

// ---------------------------------------------------------------------------
// Tilemap creation and conversion
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Isolate segments
// ---------------------------------------------------------------------------
// Because of default connections, a segment may end up being enabled at both
// ends.  Nextpnr detects and lists the wires that need to be isolated via the
// SEG_WIRES_TO_ISOLATE net attribute.  Here we parse that information and
// disconnect using the alonenode_6 table.

void isolate_segments(const Netlist& netlist, const Device& db, Tilemap& tilemap) {
    // Pattern: X<col>Y<row>/<wire_name>
    static const std::regex wire_re(R"(X(\d+)Y(\d+)/([\w]+))");

    for (const auto& [net_name, net] : netlist.nets) {
        // Look for the SEG_WIRES_TO_ISOLATE attribute
        auto attr_it = net.attributes.find("SEG_WIRES_TO_ISOLATE");
        if (attr_it == net.attributes.end()) {
            continue;
        }

        // The attribute value is a semicolon-separated list of wire references
        std::string val;
        if (auto* s = std::get_if<std::string>(&attr_it->second)) {
            val = *s;
        } else {
            continue;
        }

        // Split on semicolons
        size_t pos = 0;
        while (pos < val.size()) {
            size_t next = val.find(';', pos);
            if (next == std::string::npos) next = val.size();
            std::string wire_ex = val.substr(pos, next - pos);
            pos = next + 1;

            if (wire_ex.empty()) continue;

            std::smatch match;
            if (!std::regex_match(wire_ex, match, wire_re)) {
                throw std::runtime_error("Invalid isolated wire: " + wire_ex);
            }

            int64_t col = std::stoll(match[1].str());
            int64_t row = std::stoll(match[2].str());
            std::string wire = match[3].str();

            const auto& tile = db.get_tile(row, col);
            auto an_it = tile.alonenode_6.find(wire);
            if (an_it == tile.alonenode_6.end()) {
                throw std::runtime_error(
                    "Wire " + wire + " is not in alonenode_6 fuse table");
            }
            if (an_it->second.size() != 1) {
                throw std::runtime_error(
                    "Incorrect alonenode_6 fuse table for " + wire);
            }

            const auto& bits = an_it->second[0].second;  // set<Coord>
            auto& btile = tilemap[{row, col}];
            for (const auto& [brow, bcol] : bits) {
                set_bit(btile, brow, bcol);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// GSR (Global Set/Reset) fuse setting
// ---------------------------------------------------------------------------
// In the Python implementation this uses attrids tables to look up the fuse
// coordinates for GSR and CFG shortval entries.  The full attrids lookup is
// device-specific and loaded from the chipdb.  This implementation sets the
// fuses via the shortval tables in the Device database, matching the Python
// gsr() function in gowin_pack.py.
//
// The Python flow:
//   1. Build a set of (attr_id, attr_val) pairs for GSR and CFG.
//   2. For each tile whose ttyp is in the relevant type set, look up fuses
//      from db.shortval[ttyp]['GSR'] and db.shortval[ttyp]['CFG'].
//   3. Set those fuse bits in the tilemap.
//
// Because the full attrids machinery is complex and device-version dependent,
// we provide a direct shortval-based implementation that covers the common
// case.  Callers with special attrids requirements can extend this function.

void set_gsr_fuses(const Device& db, Tilemap& tilemap, const PackArgs& args) {
    using namespace attrids;
    const std::string& device = args.device;

    // Build GSR attribute set: GSRMODE = ACTIVE_LOW
    std::set<int64_t> gsr_attrs;
    add_attr_val(db, "GSR", gsr_attrs,
                 gsr_attrids.at("GSRMODE"), gsr_attrvals.at("ACTIVE_LOW"));

    // Build CFG attribute set: GSR=USED, GOE=F0/F1, DONE=F0/F3, GWD=F0/F1
    std::set<int64_t> cfg_attrs;
    std::string cfg_function = "F0";
    std::string cfg_done_function = "F0";
    if (device == "GW5A-25A" || device == "GW5AST-138C") {
        cfg_function = "F1";
        cfg_done_function = "F3";
    }
    add_attr_val(db, "CFG", cfg_attrs,
                 cfg_attrids.at("GSR"), cfg_attrvals.at("USED"));
    add_attr_val(db, "CFG", cfg_attrs,
                 cfg_attrids.at("GOE"), cfg_attrvals.at(cfg_function));
    add_attr_val(db, "CFG", cfg_attrs,
                 cfg_attrids.at("GSR"), cfg_attrvals.at(cfg_function));
    add_attr_val(db, "CFG", cfg_attrs,
                 cfg_attrids.at("DONE"), cfg_attrvals.at(cfg_done_function));
    add_attr_val(db, "CFG", cfg_attrs,
                 cfg_attrids.at("GWD"), cfg_attrvals.at(cfg_function));

    // Determine which tile types contain the GSR and CFG shortval tables
    std::set<int64_t> gsr_type = {50, 83};
    std::set<int64_t> cfg_type = {50, 51};
    if (device == "GW2A-18" || device == "GW2A-18C") {
        gsr_type = {1, 83};
        cfg_type = {1, 51};
    } else if (device == "GW5A-25A") {
        gsr_type = {49, 83};
        cfg_type = {49, 51};
    } else if (device == "GW5AST-138C") {
        gsr_type = {220};
        cfg_type = {220};
    }

    for (size_t row = 0; row < db.rows(); ++row) {
        for (size_t col = 0; col < db.cols(); ++col) {
            int64_t ttyp = db.get_ttyp(row, col);
            bool is_gsr = gsr_type.count(ttyp) > 0;
            bool is_cfg = cfg_type.count(ttyp) > 0;
            if (!is_gsr && !is_cfg) continue;

            auto& btile = tilemap[{static_cast<int64_t>(row),
                                    static_cast<int64_t>(col)}];
            std::set<Coord> bits;
            if (is_gsr) {
                auto gsr_fuses = get_shortval_fuses(db, ttyp, gsr_attrs, "GSR");
                bits.insert(gsr_fuses.begin(), gsr_fuses.end());
            }
            if (is_cfg) {
                auto cfg_fuses = get_shortval_fuses(db, ttyp, cfg_attrs, "CFG");
                bits.insert(cfg_fuses.begin(), cfg_fuses.end());
            }
            for (const auto& [brow, bcol] : bits) {
                set_bit(btile, brow, bcol);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Dual-mode pin fuse setting
// ---------------------------------------------------------------------------
// Handles the various *_AS_GPIO flags from PackArgs.  The Python
// dualmode_pins() builds a set of attribute fuse coordinates from the CFG
// shortval table, clears the "YES" fuses, then sets only the ones that the
// user has requested.
//
// As with set_gsr_fuses(), the full implementation requires the attrids
// tables.  This function provides the structural framework; a complete port
// would resolve the symbolic flag names through attrids into shortval
// coordinates.

void set_dualmode_pin_fuses(const Device& db, Tilemap& tilemap, const PackArgs& args) {
    using namespace attrids;
    const std::string& device = args.device;

    // Build pin_flags map matching Python dualmode_pins()
    std::map<std::string, std::string> pin_flags;
    pin_flags["JTAG_AS_GPIO"]     = args.jtag_as_gpio      ? "YES" : "UNKNOWN";
    pin_flags["SSPI_AS_GPIO"]     = args.sspi_as_gpio      ? "YES" : "UNKNOWN";
    pin_flags["MSPI_AS_GPIO"]     = args.mspi_as_gpio      ? "YES" : "UNKNOWN";
    pin_flags["READY_AS_GPIO"]    = args.ready_as_gpio     ? "YES" : "UNKNOWN";
    pin_flags["DONE_AS_GPIO"]     = args.done_as_gpio      ? "YES" : "UNKNOWN";
    pin_flags["RECONFIG_AS_GPIO"] = args.reconfign_as_gpio ? "YES" : "UNKNOWN";
    pin_flags["I2C_AS_GPIO"]      = args.i2c_as_gpio       ? "YES" : "UNKNOWN";
    pin_flags["CPU_AS_GPIO_25"]   = "UNKNOWN";
    pin_flags["CPU_AS_GPIO_0"]    = "UNKNOWN";
    pin_flags["CPU_AS_GPIO_1"]    = "UNKNOWN";

    if (args.cpu_as_gpio) {
        if (device == "GW5A-25A") {
            pin_flags["CPU_AS_GPIO_25"] = "YES";
        } else if (device == "GW5AST-138C") {
            pin_flags["CPU_AS_GPIO_0"] = "YES";
            pin_flags["CPU_AS_GPIO_1"] = "YES";
        }
    }

    // Build set_attrs (actual values) and clr_attrs (all YES) via attrids
    std::set<int64_t> set_attrs;
    std::set<int64_t> clr_attrs;
    for (const auto& [k, val] : pin_flags) {
        auto attr_it = cfg_attrids.find(k);
        if (attr_it == cfg_attrids.end()) continue;
        add_attr_val(db, "CFG", set_attrs, attr_it->second, cfg_attrvals.at(val));
        add_attr_val(db, "CFG", clr_attrs, attr_it->second, cfg_attrvals.at("YES"));
    }

    // Determine which tile types contain the CFG shortval table
    std::set<int64_t> cfg_type = {50, 51};
    if (device == "GW2A-18" || device == "GW2A-18C") {
        cfg_type = {1, 51};
    } else if (device == "GW5A-25A") {
        cfg_type = {49, 51};
    } else if (device == "GW5AST-138C") {
        cfg_type = {220};
    }

    for (size_t row = 0; row < db.rows(); ++row) {
        for (size_t col = 0; col < db.cols(); ++col) {
            int64_t ttyp = db.get_ttyp(row, col);
            if (cfg_type.count(ttyp) == 0) continue;

            auto& btile = tilemap[{static_cast<int64_t>(row),
                                    static_cast<int64_t>(col)}];

            // First clear all "YES" fuses, then set the requested ones
            auto clr_fuses = get_shortval_fuses(db, ttyp, clr_attrs, "CFG");
            for (const auto& [brow, bcol] : clr_fuses) {
                clear_bit(btile, brow, bcol);
            }
            auto set_fuses = get_shortval_fuses(db, ttyp, set_attrs, "CFG");
            for (const auto& [brow, bcol] : set_fuses) {
                set_bit(btile, brow, bcol);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Checksum calculation
// ---------------------------------------------------------------------------
// Matches the Python header_footer() in gowin_pack.py:
//   bs = bitmatrix.fliplr(bs)
//   bs = bitmatrix.packbits(bs)            # axis=None -> flatten then pack
//   res = int(sum(bs[0::2]) * pow(2,8) + sum(bs[1::2]))
//   checksum = res & 0xffff
//
// The packed flat byte array is treated as a sequence of 16-bit big-endian
// words: even-indexed bytes are the high bytes, odd-indexed bytes are the low
// bytes.

static uint16_t compute_checksum(const std::vector<std::vector<uint8_t>>& main_map) {
    auto flipped = fliplr(main_map);
    auto packed = packbits_flat(flipped);

    uint64_t sum_even = 0;  // sum of bytes at even indices (high bytes)
    uint64_t sum_odd  = 0;  // sum of bytes at odd indices  (low bytes)
    for (size_t i = 0; i < packed.size(); ++i) {
        if (i % 2 == 0) {
            sum_even += packed[i];
        } else {
            sum_odd += packed[i];
        }
    }
    uint64_t res = sum_even * 256 + sum_odd;
    return static_cast<uint16_t>(res & 0xFFFF);
}

// ---------------------------------------------------------------------------
// Footer checksum encoding
// ---------------------------------------------------------------------------
// The Python sets the checksum in the footer like this:
//   db.cmd_ftr[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")
//
// This produces 8 bytes:
//   [0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, checksum_hi, checksum_lo]
//
// For GW5A-25A an extra 8-byte entry (0x68...) is inserted at index 1
// before the checksum entry.

static void set_footer_checksum(std::vector<std::vector<uint8_t>>& footer,
                                uint16_t checksum,
                                const std::string& device) {
    // Build the checksum command: 0x0A opcode in byte 0, checksum in bytes 6-7
    // (big-endian)
    std::vector<uint8_t> cksum_cmd = {
        0x0A, 0x00, 0x00, 0x00, 0x00, 0x00,
        static_cast<uint8_t>((checksum >> 8) & 0xFF),
        static_cast<uint8_t>(checksum & 0xFF)
    };

    // Replace footer[1] with the checksum command
    if (footer.size() > 1) {
        footer[1] = cksum_cmd;
    } else {
        // Ensure footer has at least 2 entries
        while (footer.size() < 2) {
            footer.push_back({});
        }
        footer[1] = cksum_cmd;
    }

    // For GW5A-25A, insert an extra command at index 1, pushing checksum
    // to index 2.
    if (device == "GW5A-25A") {
        std::vector<uint8_t> extra_cmd = {
            0x68, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        };
        footer.insert(footer.begin() + 1, extra_cmd);
    }
}

// ---------------------------------------------------------------------------
// Frame generation with per-frame CRC
// ---------------------------------------------------------------------------
// Matches the Python bslib.py write_bitstream():
//
//   1. Flip the bitmap left-right.
//   2. Pad each row to a multiple of 8 bits with leading 1-bits.
//   3. Pack per row (axis=1).
//   4. For each packed row (frame):
//      a. Accumulate frame data into a running CRC buffer.
//      b. Compute CRC-16/ARC over the buffer.
//      c. Append 2-byte CRC (little-endian: lo, hi) + 6 bytes 0xFF padding.
//      d. Reset the CRC buffer to 6 bytes of 0xFF (the padding).
//
// The first frame's CRC includes accumulated header bytes (after the 3-line
// preamble, excluding SPI address lines starting with 0xD2).

static std::vector<std::vector<uint8_t>> generate_frames(
    const std::vector<std::vector<uint8_t>>& main_map,
    const std::vector<std::vector<uint8_t>>& header,
    bool compress)
{
    // Step 1: flip left-right
    auto bitmap = fliplr(main_map);

    // Step 2: compute padding to make each row a multiple of 8 (or 64 if
    // compressing) bits wide.  Padding is prepended as 1-bits.
    size_t ncols = bitmap.empty() ? 0 : bitmap[0].size();
    size_t nrows = bitmap.size();
    size_t align = compress ? 64 : 8;
    size_t padded_width = static_cast<size_t>(
        std::ceil(static_cast<double>(ncols) / align) * align);
    size_t padlen = padded_width - ncols;

    if (padlen > 0) {
        auto pad = ones(nrows, padlen);
        bitmap = hstack(pad, bitmap);
    }

    // Step 3: pack per row
    auto packed = packbits(bitmap);

    // Step 4: build CRC buffer and generate frames
    // Accumulate header bytes (skip preamble and SPI address lines).
    std::vector<uint8_t> crcdat;
    {
        int preamble = 3;
        for (const auto& hdr_line : header) {
            if (preamble <= 0 && !hdr_line.empty() && hdr_line[0] != 0xD2) {
                crcdat.insert(crcdat.end(), hdr_line.begin(), hdr_line.end());
            }
            if (preamble > 0) --preamble;
        }
    }

    std::vector<std::vector<uint8_t>> frames;
    frames.reserve(packed.size());
    for (const auto& row_bytes : packed) {
        // Extend CRC buffer with frame data
        crcdat.insert(crcdat.end(), row_bytes.begin(), row_bytes.end());

        // Compute CRC-16/ARC over the accumulated buffer
        uint16_t crc = crc16_arc(crcdat);

        // Reset CRC buffer to 6 bytes of 0xFF (the padding that follows
        // this frame in the bitstream).
        crcdat.assign(6, 0xFF);

        // Build the frame: data + CRC(2 bytes, little-endian) + padding(6x 0xFF)
        std::vector<uint8_t> frame;
        frame.reserve(row_bytes.size() + 8);
        frame.insert(frame.end(), row_bytes.begin(), row_bytes.end());
        frame.push_back(static_cast<uint8_t>(crc & 0xFF));
        frame.push_back(static_cast<uint8_t>((crc >> 8) & 0xFF));
        for (int i = 0; i < 6; ++i) {
            frame.push_back(0xFF);
        }
        frames.push_back(std::move(frame));
    }
    return frames;
}

// ---------------------------------------------------------------------------
// Main bitstream generation entry point
// ---------------------------------------------------------------------------

Bitstream generate_bitstream(Device& db, const Netlist& netlist, const PackArgs& args) {
    Bitstream bs;
    bs.compressed = args.compress;
    bs.header = db.cmd_hdr;
    bs.footer = db.cmd_ftr;

    const std::string& device = args.device;

    // -----------------------------------------------------------------------
    // Step 1: Create tilemap
    // -----------------------------------------------------------------------
    auto tilemap = create_tilemap(db);

    // -----------------------------------------------------------------------
    // Step 2: Route nets
    // -----------------------------------------------------------------------
    route_nets(db, netlist, tilemap, device);

    // -----------------------------------------------------------------------
    // Step 3: Isolate segments
    // -----------------------------------------------------------------------
    isolate_segments(netlist, db, tilemap);

    // -----------------------------------------------------------------------
    // Step 4: Set GSR (Global Set/Reset) fuses
    // -----------------------------------------------------------------------
    set_gsr_fuses(db, tilemap, args);

    // -----------------------------------------------------------------------
    // Step 5: Place cells
    // -----------------------------------------------------------------------
    place_cells(db, netlist, tilemap, device);

    // -----------------------------------------------------------------------
    // Step 6: Set dual-mode pin fuses
    // -----------------------------------------------------------------------
    set_dualmode_pin_fuses(db, tilemap, args);

    // -----------------------------------------------------------------------
    // Step 7: Set constant fuses
    // -----------------------------------------------------------------------
    for (size_t row = 0; row < db.rows(); ++row) {
        for (size_t col = 0; col < db.cols(); ++col) {
            const auto& tile = db.get_tile(row, col);
            auto it = db.const_fuses.find(tile.ttyp);
            if (it != db.const_fuses.end()) {
                auto& tile_bm = tilemap[{static_cast<int64_t>(row),
                                          static_cast<int64_t>(col)}];
                for (const auto& [brow, bcol] : it->second) {
                    set_bit(tile_bm, brow, bcol);
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // Step 8: Convert tilemap to bitmap
    // -----------------------------------------------------------------------
    auto main_map = tilemap_to_bitmap(db, tilemap);

    // -----------------------------------------------------------------------
    // Step 9: Transpose if GW5A series
    // -----------------------------------------------------------------------
    bool is_gw5 = (device == "GW5A-25A" || device == "GW5AST-138C");
    if (is_gw5) {
        main_map = transpose(main_map);
    }

    // -----------------------------------------------------------------------
    // Step 10: Compute checksum and set in footer
    // -----------------------------------------------------------------------
    uint16_t checksum = compute_checksum(main_map);
    set_footer_checksum(bs.footer, checksum, device);

    // -----------------------------------------------------------------------
    // Step 11: Update frame count in header
    // -----------------------------------------------------------------------
    // The last header line contains the frame count in bytes [2:3] (big-endian).
    size_t nrows = main_map.size();
    if (!bs.header.empty() && bs.header.back().size() >= 4) {
        bs.header.back()[2] = static_cast<uint8_t>((nrows >> 8) & 0xFF);
        bs.header.back()[3] = static_cast<uint8_t>(nrows & 0xFF);
    }

    // -----------------------------------------------------------------------
    // Step 12: Generate frames with per-frame CRC
    // -----------------------------------------------------------------------
    bs.frames = generate_frames(main_map, bs.header, args.compress);

    return bs;
}

// ---------------------------------------------------------------------------
// Bitstream file output (.fs format)
// ---------------------------------------------------------------------------

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

    // Write frame data (each frame already contains data + CRC + padding)
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
