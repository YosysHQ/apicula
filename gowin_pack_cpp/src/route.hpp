// route.hpp - Routing functions
#pragma once

#include "chipdb_types.hpp"
#include "netlist.hpp"
#include <map>
#include <vector>
#include <set>

namespace apycula {

// Forward declarations
using TileBitmap = std::vector<std::vector<uint8_t>>;
using Tilemap = std::map<Coord, TileBitmap>;
struct BelInfo;  // defined in place.hpp

// PIP information extracted from netlist
struct Pip {
    int64_t row;
    int64_t col;
    std::string src;
    std::string dest;
};

// Extract PIPs from netlist.
// Also populates pip_bels with pass-through LUT BelInfos for XD wires.
std::vector<Pip> get_pips(const Netlist& netlist, std::vector<BelInfo>& pip_bels);

// Route all nets and set fuses in tile bitmaps.
// Returns pass-through LUT BelInfos that must be fed into placement.
std::vector<BelInfo> route_nets(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device);

// Isolate segments that need disconnection via alonenode_6 fuses.
// Parses the "SEG_WIRES_TO_ISOLATE" net attribute and sets the
// corresponding isolation fuse bits.
void isolate_segments(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap);

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
