// route.hpp - Routing functions
#pragma once

#include "chipdb_types.hpp"
#include "netlist.hpp"
#include <map>
#include <vector>
#include <set>

namespace apycula {

// Forward declaration
using TileBitmap = std::vector<std::vector<uint8_t>>;
using Tilemap = std::map<Coord, TileBitmap>;

// PIP information extracted from netlist
struct Pip {
    int64_t row;
    int64_t col;
    std::string src;
    std::string dest;
};

// Extract PIPs from netlist
std::vector<Pip> get_pips(const Netlist& netlist);

// Route all nets and set fuses in tile bitmaps
void route_nets(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device);

// Set clock fuses for GW5A series
void set_clock_fuses(
    const Device& db,
    Tilemap& tilemap,
    int64_t row,
    int64_t col,
    const std::string& src,
    const std::string& dest,
    const std::string& device);

} // namespace apycula
