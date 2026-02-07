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
void place_cells(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device,
    const std::vector<BelInfo>& extra_bels = {});

// Placement functions for specific BEL types
void place_lut(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_dff(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_alu(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_iob(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_pll(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_bsram(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_dsp(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_iologic(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_osc(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_bufs(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_ram16sdp(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_clkdiv(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_dcs(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device);
void place_dqce(const Device& db, const BelInfo& bel, Tilemap& tilemap);
void place_dhcen(const Device& db, const BelInfo& bel, Tilemap& tilemap);

// Set default IO fuses for all IOB pins (used and unused) and bank-level fuses
void set_iob_default_fuses(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device);

// Apply accumulated slice fuses (called at end of place_cells)
void set_slice_fuses(const Device& db, Tilemap& tilemap);

// Helper: set fuses in a tile bitmap from a set of coordinates
void set_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses);

// Helper: clear fuses in a tile bitmap from a set of coordinates
void clear_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses);

} // namespace apycula
