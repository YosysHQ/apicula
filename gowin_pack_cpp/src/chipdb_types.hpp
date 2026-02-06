// chipdb_types.hpp - Types for Gowin chipdb
// Based on apycula/chipdb.py dataclasses
#pragma once

#include <msgpack.hpp>
#include <string>
#include <vector>
#include <array>
#include <map>
#include <set>
#include <optional>
#include <cstdint>
#include <tuple>

namespace apycula {

// Type alias for coordinate tuples (row, col)
using Coord = std::pair<int64_t, int64_t>;

// Represents a Basic Element with modes and portmap
struct Bel {
    std::map<int64_t, std::set<Coord>> flags;  // int keys
    bool simplified_iob = false;
    bool is_diff = false;
    bool is_true_lvds = false;
    bool is_diff_p = false;
    std::map<std::string, std::set<Coord>> modes;  // string keys
    std::map<std::string, msgpack::object> portmap;  // values can be string, list, or nested list
    std::optional<Coord> fuse_cell_offset;
};

// Represents all configurable features for a tile type
struct Tile {
    int64_t width = 0;
    int64_t height = 0;
    int64_t ttyp = 0;
    std::map<std::string, std::map<std::string, std::set<Coord>>> pips;
    std::map<std::string, std::vector<std::pair<std::set<std::string>, std::set<Coord>>>> alonenode;
    std::map<std::string, std::map<std::string, std::set<Coord>>> clock_pips;
    std::map<std::string, std::vector<std::pair<std::set<std::string>, std::set<Coord>>>> alonenode_6;
    std::map<std::string, Bel> bels;
};

// Device database - tile-deduplicated structure
struct Device {
    // grid stores tile type IDs (ttyp), use get_tile(row, col) for Tile
    std::vector<std::vector<int64_t>> grid;
    // tiles: ttyp -> Tile
    std::map<int64_t, Tile> tiles;

    // Timing data: speed_grade -> category -> timing_name -> [values]
    // Using msgpack::object to defer parsing (complex nested structure)
    msgpack::object timing;
    std::map<std::string, std::string> wire_delay;

    // Package info
    std::map<std::string, std::tuple<std::string, std::string, std::string>> packages;
    std::map<std::string, std::map<std::string, std::map<std::string, std::pair<std::string, std::vector<std::string>>>>> pinout;
    std::map<std::string, std::map<std::string, std::vector<std::tuple<std::string, int64_t, int64_t, std::string, std::string>>>> sip_cst;
    std::map<std::string, int64_t> pin_bank;

    // Bitstream header/footer templates
    std::vector<std::vector<uint8_t>> cmd_hdr;
    std::vector<std::vector<uint8_t>> cmd_ftr;
    std::vector<std::vector<int64_t>> template_data;

    // Logic info tables
    std::map<std::string, std::map<Coord, int64_t>> logicinfo;
    std::map<std::string, std::map<int64_t, Coord>> rev_li;

    // Fuse tables
    std::map<int64_t, std::map<std::string, std::map<std::tuple<int64_t>, std::set<Coord>>>> longfuses;
    std::map<int64_t, std::map<std::string, std::map<Coord, std::set<Coord>>>> shortval;
    std::map<int64_t, std::map<std::string, std::map<std::array<int64_t, 16>, std::set<Coord>>>> longval;
    std::map<int64_t, std::vector<Coord>> const_fuses;

    // Himbaechel nodes
    std::map<std::string, std::pair<std::string, std::set<std::tuple<int64_t, int64_t, std::string>>>> nodes;

    // Bottom IO config
    std::tuple<std::string, std::string, std::vector<std::pair<std::string, std::string>>> bottom_io;
    std::set<int64_t> simplio_rows;
    std::map<std::string, std::tuple<int64_t, int64_t, std::string, std::string>> pad_pll;
    std::map<std::string, std::set<int64_t>> tile_types;
    std::vector<std::string> diff_io_types;
    std::map<Coord, std::map<std::string, std::map<std::string, std::set<Coord>>>> hclk_pips;
    std::map<Coord, std::map<std::string, msgpack::object>> extra_func;
    std::vector<std::string> chip_flags;
    std::map<std::array<int64_t, 3>, std::map<std::string, msgpack::object>> segments;
    std::string dcs_prefix = "CLK";
    std::map<std::string, std::set<std::string>> io_cfg;
    std::map<Coord, std::string> corner_tiles_io;
    std::map<std::string, std::map<std::string, std::vector<std::tuple<int64_t, int64_t, std::string, int64_t>>>> spine_select_wires;
    int64_t last_top_row = 0;

    // Get tile at (row, col) via tile deduplication
    const Tile& get_tile(int64_t row, int64_t col) const {
        return tiles.at(grid.at(row).at(col));
    }

    Tile& get_tile(int64_t row, int64_t col) {
        return tiles.at(grid.at(row).at(col));
    }

    // Get ttyp at (row, col)
    int64_t get_ttyp(int64_t row, int64_t col) const {
        return grid.at(row).at(col);
    }

    size_t rows() const { return grid.size(); }
    size_t cols() const { return grid.empty() ? 0 : grid[0].size(); }

    int64_t height() const {
        int64_t h = 0;
        for (size_t row = 0; row < rows(); ++row) {
            h += get_tile(row, 0).height;
        }
        return h;
    }

    int64_t width() const {
        int64_t w = 0;
        for (size_t col = 0; col < cols(); ++col) {
            w += get_tile(0, col).width;
        }
        return w;
    }

    // Get bank tiles mapping
    std::map<int64_t, Coord> bank_tiles() const {
        std::map<int64_t, Coord> res;
        for (size_t row = 0; row < rows(); ++row) {
            for (size_t col = 0; col < cols(); ++col) {
                const auto& tile = get_tile(row, col);
                for (const auto& [bel_name, bel] : tile.bels) {
                    if (bel_name.substr(0, 4) == "BANK") {
                        int64_t bank = std::stoll(bel_name.substr(4));
                        res[bank] = {static_cast<int64_t>(row), static_cast<int64_t>(col)};
                    }
                }
            }
        }
        return res;
    }

    // Reverse logicinfo lookup
    const std::map<int64_t, Coord>& rev_logicinfo(const std::string& name) {
        if (rev_li.find(name) == rev_li.end()) {
            auto& table = rev_li[name];
            for (const auto& [attrval, code] : logicinfo.at(name)) {
                table[code] = attrval;
            }
        }
        return rev_li.at(name);
    }
};

} // namespace apycula

// Custom msgpack adaptors for map-based deserialization
namespace msgpack {
MSGPACK_API_VERSION_NAMESPACE(MSGPACK_DEFAULT_API_NS) {
namespace adaptor {

// Helper to get value from msgpack map by string key
template<typename T>
T get_map_value(const msgpack::object& o, const char* key, const T& default_val = T{}) {
    if (o.type != msgpack::type::MAP) return default_val;
    for (size_t i = 0; i < o.via.map.size; ++i) {
        auto& kv = o.via.map.ptr[i];
        if (kv.key.type == msgpack::type::STR) {
            std::string k(kv.key.via.str.ptr, kv.key.via.str.size);
            if (k == key) {
                // Handle nil values by returning default
                if (kv.val.type == msgpack::type::NIL) {
                    return default_val;
                }
                return kv.val.as<T>();
            }
        }
    }
    return default_val;
}

template<typename T>
bool has_map_key(const msgpack::object& o, const char* key) {
    if (o.type != msgpack::type::MAP) return false;
    for (size_t i = 0; i < o.via.map.size; ++i) {
        auto& kv = o.via.map.ptr[i];
        if (kv.key.type == msgpack::type::STR) {
            std::string k(kv.key.via.str.ptr, kv.key.via.str.size);
            if (k == key) return true;
        }
    }
    return false;
}

// Deserialize Bel from msgpack map
template<>
struct convert<apycula::Bel> {
    msgpack::object const& operator()(msgpack::object const& o, apycula::Bel& v) const {
        if (o.type != msgpack::type::MAP) throw msgpack::type_error();
        v.flags = get_map_value<std::map<int64_t, std::set<apycula::Coord>>>(o, "flags");
        v.simplified_iob = get_map_value<bool>(o, "simplified_iob", false);
        v.is_diff = get_map_value<bool>(o, "is_diff", false);
        v.is_true_lvds = get_map_value<bool>(o, "is_true_lvds", false);
        v.is_diff_p = get_map_value<bool>(o, "is_diff_p", false);
        v.modes = get_map_value<std::map<std::string, std::set<apycula::Coord>>>(o, "modes");
        v.portmap = get_map_value<std::map<std::string, msgpack::object>>(o, "portmap");
        v.fuse_cell_offset = get_map_value<std::optional<apycula::Coord>>(o, "fuse_cell_offset");
        return o;
    }
};

// Deserialize Tile from msgpack map
template<>
struct convert<apycula::Tile> {
    msgpack::object const& operator()(msgpack::object const& o, apycula::Tile& v) const {
        if (o.type != msgpack::type::MAP) throw msgpack::type_error();
        v.width = get_map_value<int64_t>(o, "width", 0);
        v.height = get_map_value<int64_t>(o, "height", 0);
        v.ttyp = get_map_value<int64_t>(o, "ttyp", 0);
        v.pips = get_map_value<std::map<std::string, std::map<std::string, std::set<apycula::Coord>>>>(o, "pips");
        v.alonenode = get_map_value<std::map<std::string, std::vector<std::pair<std::set<std::string>, std::set<apycula::Coord>>>>>(o, "alonenode");
        v.clock_pips = get_map_value<std::map<std::string, std::map<std::string, std::set<apycula::Coord>>>>(o, "clock_pips");
        v.alonenode_6 = get_map_value<std::map<std::string, std::vector<std::pair<std::set<std::string>, std::set<apycula::Coord>>>>>(o, "alonenode_6");
        v.bels = get_map_value<std::map<std::string, apycula::Bel>>(o, "bels");
        return o;
    }
};

// Deserialize Device from msgpack map
template<>
struct convert<apycula::Device> {
    msgpack::object const& operator()(msgpack::object const& o, apycula::Device& v) const {
        if (o.type != msgpack::type::MAP) throw msgpack::type_error();
        v.grid = get_map_value<std::vector<std::vector<int64_t>>>(o, "grid");
        v.tiles = get_map_value<std::map<int64_t, apycula::Tile>>(o, "tiles");
        v.timing = get_map_value<msgpack::object>(o, "timing");
        v.wire_delay = get_map_value<std::map<std::string, std::string>>(o, "wire_delay");
        v.packages = get_map_value<std::map<std::string, std::tuple<std::string, std::string, std::string>>>(o, "packages");
        v.pinout = get_map_value<std::map<std::string, std::map<std::string, std::map<std::string, std::pair<std::string, std::vector<std::string>>>>>>(o, "pinout");
        v.sip_cst = get_map_value<std::map<std::string, std::map<std::string, std::vector<std::tuple<std::string, int64_t, int64_t, std::string, std::string>>>>>(o, "sip_cst");
        v.pin_bank = get_map_value<std::map<std::string, int64_t>>(o, "pin_bank");
        v.cmd_hdr = get_map_value<std::vector<std::vector<uint8_t>>>(o, "cmd_hdr");
        v.cmd_ftr = get_map_value<std::vector<std::vector<uint8_t>>>(o, "cmd_ftr");
        v.template_data = get_map_value<std::vector<std::vector<int64_t>>>(o, "template");
        v.logicinfo = get_map_value<std::map<std::string, std::map<apycula::Coord, int64_t>>>(o, "logicinfo");
        v.rev_li = get_map_value<std::map<std::string, std::map<int64_t, apycula::Coord>>>(o, "rev_li");
        v.longfuses = get_map_value<std::map<int64_t, std::map<std::string, std::map<std::tuple<int64_t>, std::set<apycula::Coord>>>>>(o, "longfuses");
        v.shortval = get_map_value<std::map<int64_t, std::map<std::string, std::map<apycula::Coord, std::set<apycula::Coord>>>>>(o, "shortval");
        v.longval = get_map_value<std::map<int64_t, std::map<std::string, std::map<std::array<int64_t, 16>, std::set<apycula::Coord>>>>>(o, "longval");
        v.const_fuses = get_map_value<std::map<int64_t, std::vector<apycula::Coord>>>(o, "const");
        v.nodes = get_map_value<std::map<std::string, std::pair<std::string, std::set<std::tuple<int64_t, int64_t, std::string>>>>>(o, "nodes");
        v.bottom_io = get_map_value<std::tuple<std::string, std::string, std::vector<std::pair<std::string, std::string>>>>(o, "bottom_io");
        v.simplio_rows = get_map_value<std::set<int64_t>>(o, "simplio_rows");
        v.pad_pll = get_map_value<std::map<std::string, std::tuple<int64_t, int64_t, std::string, std::string>>>(o, "pad_pll");
        v.tile_types = get_map_value<std::map<std::string, std::set<int64_t>>>(o, "tile_types");
        v.diff_io_types = get_map_value<std::vector<std::string>>(o, "diff_io_types");
        v.hclk_pips = get_map_value<std::map<apycula::Coord, std::map<std::string, std::map<std::string, std::set<apycula::Coord>>>>>(o, "hclk_pips");
        v.extra_func = get_map_value<std::map<apycula::Coord, std::map<std::string, msgpack::object>>>(o, "extra_func");
        v.chip_flags = get_map_value<std::vector<std::string>>(o, "chip_flags");
        v.segments = get_map_value<std::map<std::array<int64_t, 3>, std::map<std::string, msgpack::object>>>(o, "segments");
        v.dcs_prefix = get_map_value<std::string>(o, "dcs_prefix", "CLK");
        v.io_cfg = get_map_value<std::map<std::string, std::set<std::string>>>(o, "io_cfg");
        v.corner_tiles_io = get_map_value<std::map<apycula::Coord, std::string>>(o, "corner_tiles_io");
        v.spine_select_wires = get_map_value<std::map<std::string, std::map<std::string, std::vector<std::tuple<int64_t, int64_t, std::string, int64_t>>>>>(o, "spine_select_wires");
        v.last_top_row = get_map_value<int64_t>(o, "last_top_row", 0);
        return o;
    }
};

} // namespace adaptor
} // MSGPACK_API_VERSION_NAMESPACE
} // namespace msgpack
