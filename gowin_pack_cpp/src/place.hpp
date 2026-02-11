// place.hpp - BEL placement functions
#pragma once

#include "chipdb_types.hpp"
#include "netlist.hpp"
#include <map>
#include <vector>
#include <set>
#include <string>

namespace apycula {

// Forward declarations
using TileBitmap = std::vector<std::vector<uint8_t>>;
using Tilemap = std::map<Coord, TileBitmap>;
using BsramInitMap = std::vector<std::vector<uint8_t>>;

// GW5A BSRAM position info (collected during placement, processed after)
struct Gw5aBsramInfo {
    int64_t col;
    int64_t row;
    std::string typ;
    std::map<std::string, std::string> params;
    std::map<std::string, std::string> attrs;

    bool operator<(const Gw5aBsramInfo& o) const {
        if (col != o.col) return col < o.col;
        return row < o.row;
    }
};

// BEL information extracted from netlist
struct BelInfo {
    std::string type;
    int64_t row;
    int64_t col;
    std::string num;
    std::map<std::string, std::string> parameters;
    std::map<std::string, std::string> attributes;
    std::string name;
    const Cell* cell = nullptr;  // Pointer to original cell for connection info
};

// Extract BELs from netlist
std::vector<BelInfo> get_bels(const Netlist& netlist);

// Place all cells and set fuses in tile bitmaps.
// extra_bels are additional BelInfos (e.g. pass-through LUTs from routing).
// bsram_init_map: if non-null, BSRAM init data is accumulated here.
// gw5a_bsrams: if non-null, GW5A BSRAM positions are collected here instead
//              of calling store_bsram_init_val immediately.
void place_cells(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device,
    const std::vector<BelInfo>& extra_bels = {},
    BsramInitMap* bsram_init_map = nullptr,
    std::vector<Gw5aBsramInfo>* gw5a_bsrams = nullptr,
    std::map<int, TileBitmap>* extra_slots = nullptr);

// Placement functions for specific BEL types
void place_lut(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_dff(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_alu(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_iob(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_pll(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device,
               std::map<int, TileBitmap>* extra_slots = nullptr);
void place_bsram(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_dsp(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_iologic(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device, const Netlist& netlist);
void place_osc(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_bufs(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_ram16sdp(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_clkdiv(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_dcs(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_dqce(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_dhcen(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_adc(const Device& db, const BelInfo& bel, Tilemap& tilemap,
               std::map<int, TileBitmap>* extra_slots);

// Set default IO fuses for all IOB pins (used and unused) and bank-level fuses
void set_iob_default_fuses(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device);

// Set ADC IOB fuses for ADC IO pins
void set_adc_iobuf_fuses(const Device& db, Tilemap& tilemap);

// Apply accumulated slice fuses (called at end of place_cells)
void set_slice_fuses(const Device& db, Tilemap& tilemap);

// Store BSRAM init data for a single BSRAM cell into the global init map.
// map_offset: for GW5A-25A, the column-block offset (incremented per unique col)
void store_bsram_init_val(const Device& db, int64_t row, int64_t col,
                          const std::string& typ,
                          const std::map<std::string, std::string>& params,
                          const std::map<std::string, std::string>& attrs,
                          const std::string& device,
                          BsramInitMap& bsram_init_map,
                          int map_offset = 0);

// Helper: set fuses in a tile bitmap from a set of coordinates
void set_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses);

// Helper: clear fuses in a tile bitmap from a set of coordinates
void clear_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses);

// DSP type-specific attribute handlers (bels/dsp.cpp)
std::set<int64_t> set_dsp_attrs(const Device& db, const std::string& typ,
    std::map<std::string, std::string>& params, const std::string& num,
    std::map<std::string, std::string>& attrs);

std::vector<std::set<int64_t>> set_dsp_mult36x36_attrs(const Device& db, const std::string& typ,
    std::map<std::string, std::string>& params, std::map<std::string, std::string>& attrs);

} // namespace apycula
