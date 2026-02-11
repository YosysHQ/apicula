// route.cpp - Routing implementation
#include "route.hpp"
#include "place.hpp"
#include "fuses.hpp"
#include "attrids.hpp"
#include "wirenames.hpp"
#include <regex>
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace apycula {

// Map LUT input letter to pass-through INIT value
static const std::map<char, std::string> passthrough_init = {
    {'A', "1010101010101010"},
    {'B', "1100110011001100"},
    {'C', "1111000011110000"},
    {'D', "1111111100000000"},
};

std::vector<Pip> get_pips(const Netlist& netlist, std::vector<BelInfo>& pip_bels) {
    std::vector<Pip> pips;
    std::regex pip_re(R"(X(\d+)Y(\d+)/([\w_]+)/([\w_]+))");

    for (const auto& [name, net] : netlist.nets) {
        auto routing_it = net.attributes.find("ROUTING");
        if (routing_it == net.attributes.end()) continue;

        // Get routing string
        std::string routing;
        if (auto* s = std::get_if<std::string>(&routing_it->second)) {
            routing = *s;
        } else {
            continue;
        }

        // Parse PIPs from routing string
        // Format: wire;pip;wire;pip;wire;pip;...
        // PIPs are at indices 1, 4, 7, ... (every 3rd element starting from index 1)
        size_t pos = 0;
        int count = 0;
        while (pos < routing.size()) {
            size_t next = routing.find(';', pos);
            if (next == std::string::npos) next = routing.size();
            std::string segment = routing.substr(pos, next - pos);
            pos = next + 1;

            // Every 3rd segment starting from index 1 is a pip
            if (count % 3 == 1 && !segment.empty()) {
                std::smatch match;
                if (std::regex_match(segment, match, pip_re)) {
                    // Regex groups: X(col_val) Y(row_val) / wire1 / wire2
                    // Following Python: col = X_val + 1, row = Y_val + 1
                    // dest = wire1 (group 3), src = wire2 (group 4)
                    int64_t x_val = std::stoll(match[1].str());
                    int64_t y_val = std::stoll(match[2].str());
                    std::string dest = match[3].str();
                    std::string src = match[4].str();

                    // XD - input of the DFF: needs special handling
                    // Note: in get_pips, match[3] is called "src" in Python
                    // (which becomes "dest" in route_nets consumer). We use
                    // C++ naming that matches route_nets: dest=match[3], src=match[4].
                    // Python checks its "src" (=our dest) for XD prefix.
                    if (dest.size() >= 2 && dest[0] == 'X' && dest[1] == 'D') {
                        if (src.size() >= 1 && src[0] == 'F') {
                            // XD -> F: skip entirely
                            count++;
                            continue;
                        }
                        // Pass-through LUT: src (Python's "dest") is like "A5", "B3"
                        // src[0] is the LUT input letter, src[1] is the slice number
                        char lut_input = src[0];
                        std::string slice_num(1, src[1]);
                        auto init_it = passthrough_init.find(lut_input);
                        if (init_it != passthrough_init.end()) {
                            BelInfo bel;
                            bel.type = "LUT4";
                            bel.col = x_val + 1;
                            bel.row = y_val + 1;
                            bel.num = slice_num;
                            bel.parameters["INIT"] = init_it->second;
                            bel.name = "$PACKER_PASS_LUT_" + std::to_string(pip_bels.size());
                            bel.cell = nullptr;
                            pip_bels.push_back(std::move(bel));
                        }
                        count++;
                        continue;
                    }

                    Pip pip;
                    pip.col = x_val + 1;
                    pip.row = y_val + 1;
                    pip.dest = dest;
                    pip.src = src;
                    pips.push_back(pip);
                } else if (segment.find("DUMMY") == std::string::npos) {
                    std::cerr << "Invalid pip: " << segment << std::endl;
                }
            }
            count++;
        }
    }
    return pips;
}

void isolate_segments(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap) {

    std::regex wire_re(R"(X(\d+)Y(\d+)/([\w]+))");

    for (const auto& [name, net] : netlist.nets) {
        auto seg_it = net.attributes.find("SEG_WIRES_TO_ISOLATE");
        if (seg_it == net.attributes.end()) continue;

        std::string wires_str;
        if (auto* s = std::get_if<std::string>(&seg_it->second)) {
            wires_str = *s;
        } else {
            continue;
        }

        // Parse semicolon-separated wire list: "X{col}Y{row}/{wire};..."
        size_t pos = 0;
        while (pos < wires_str.size()) {
            size_t next = wires_str.find(';', pos);
            if (next == std::string::npos) next = wires_str.size();
            std::string wire_ex = wires_str.substr(pos, next - pos);
            pos = next + 1;

            if (wire_ex.empty()) continue;

            std::smatch res;
            if (!std::regex_match(wire_ex, res, wire_re)) {
                throw std::runtime_error("Invalid isolated wire:" + wire_ex);
            }

            // X -> col, Y -> row (0-indexed coordinates)
            int64_t col = std::stoll(res[1].str());
            int64_t row = std::stoll(res[2].str());
            std::string wire = res[3].str();

            const auto& tiledata = db.get_tile(row, col);
            auto& tile = tilemap[{row, col}];

            auto alone_it = tiledata.alonenode_6.find(wire);
            if (alone_it == tiledata.alonenode_6.end()) {
                throw std::runtime_error(
                    "Wire " + wire + " is not in alonenode fuse table");
            }
            if (alone_it->second.size() != 1) {
                throw std::runtime_error(
                    "Incorrect alonenode fuse table for " + wire);
            }

            // Get fuse bits from the single entry's second element (the fuse set)
            const auto& bits = alone_it->second[0].second;
            for (const auto& [brow, bcol] : bits) {
                if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                    bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                    tile[brow][bcol] = 1;
                }
            }
        }
    }
}

std::vector<BelInfo> route_nets(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device) {

    std::vector<BelInfo> pip_bels;
    auto pips = get_pips(netlist, pip_bels);

    bool is_gw5a = (device == "GW5A-25A" || device == "GW5AST-138C");

    // Track used spines for dedup (shared across all pips)
    std::set<std::pair<char, std::string>> used_spines;

    for (const auto& pip : pips) {
        // PIPs use 1-indexed coordinates; convert to 0-indexed for tile access
        int64_t row = pip.row - 1;
        int64_t col = pip.col - 1;

        if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
            col < 0 || col >= static_cast<int64_t>(db.cols())) {
            continue;
        }

        // GW5A clock pips use full-scan set_clock_fuses
        if (is_gw5a && is_clock_pip(pip.src, pip.dest, device)) {
            set_clock_fuses(db, tilemap, pip.row, pip.col, pip.src, pip.dest,
                            device, used_spines);
            continue;
        }

        const auto& tiledata = db.get_tile(row, col);
        auto& tile = tilemap[{row, col}];

        // Look up PIP fuses
        std::set<Coord> bits;
        bool found = false;

        // Check clock_pips first (skip for GW5A-25A which uses set_clock_fuses above)
        if (device != "GW5A-25A") {
            auto clock_it = tiledata.clock_pips.find(pip.dest);
            if (clock_it != tiledata.clock_pips.end()) {
                auto src_it = clock_it->second.find(pip.src);
                if (src_it != clock_it->second.end()) {
                    bits = src_it->second;
                    found = true;
                }
            }
        }

        // Check HCLK pips (uses 0-indexed coordinates)
        if (!found) {
            Coord hclk_coord = {row, col};
            auto hclk_it = db.hclk_pips.find(hclk_coord);
            if (hclk_it != db.hclk_pips.end()) {
                auto dest_it = hclk_it->second.find(pip.dest);
                if (dest_it != hclk_it->second.end()) {
                    auto src_it = dest_it->second.find(pip.src);
                    if (src_it != dest_it->second.end()) {
                        bits = src_it->second;
                        found = true;
                        // HCLK interbank fuses
                        if (pip.dest == "HCLK_BANK_OUT0" || pip.dest == "HCLK_BANK_OUT1") {
                            char mux_idx = pip.dest.back(); // '0' or '1'
                            std::string attr_name = std::string("BRGMUX") + mux_idx + "_BRGOUT";
                            auto attr_it = attrids::hclk_attrids.find(attr_name);
                            auto val_it = attrids::hclk_attrvals.find("ENABLE");
                            if (attr_it != attrids::hclk_attrids.end() &&
                                val_it != attrids::hclk_attrvals.end()) {
                                std::set<int64_t> fin_attrs;
                                add_attr_val(db, "HCLK", fin_attrs, attr_it->second, val_it->second);
                                int64_t ttyp = db.get_ttyp(row, col);
                                auto hclk_fuses = get_shortval_fuses(db, ttyp, fin_attrs, "HCLK");
                                bits.insert(hclk_fuses.begin(), hclk_fuses.end());
                            }
                        }
                    }
                }
            }
        }

        // Check regular pips
        if (!found) {
            auto pip_it = tiledata.pips.find(pip.dest);
            if (pip_it != tiledata.pips.end()) {
                auto src_it = pip_it->second.find(pip.src);
                if (src_it != pip_it->second.end()) {
                    bits = src_it->second;
                    found = true;
                }
            }

            // Check alonenode for isolation fuses (only for regular pips)
            if (found) {
                auto alone_it = tiledata.alonenode.find(pip.dest);
                if (alone_it != tiledata.alonenode.end()) {
                    for (const auto& [srcs, fuses] : alone_it->second) {
                        if (srcs.find(pip.src) == srcs.end()) {
                            // Source not in allowed set, add isolation fuses
                            bits.insert(fuses.begin(), fuses.end());
                        }
                    }
                }
            }
        }

        if (!found) {
            std::cerr << pip.src << " " << pip.dest
                      << " not found in tile " << pip.row << " " << pip.col
                      << std::endl;
            continue;
        }

        // Set the fuse bits
        for (const auto& [brow, bcol] : bits) {
            if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                tile[brow][bcol] = 1;
            }
        }
    }

    // Isolate segments after PIP routing
    isolate_segments(db, netlist, tilemap);

    return pip_bels;
}

void set_clock_fuses(
    const Device& db,
    Tilemap& tilemap,
    int64_t row_,   // 1-indexed pip row
    int64_t col_,   // 1-indexed pip col
    const std::string& src,
    const std::string& dest,
    const std::string& device,
    std::set<std::pair<char, std::string>>& used_spines) {

    // SPINE->{GT00, GT10} must be set in the cell only
    if (dest == "GT00" || dest == "GT10") {
        const auto& tiledata = db.get_tile(row_ - 1, col_ - 1);
        auto clock_it = tiledata.clock_pips.find(dest);
        if (clock_it != tiledata.clock_pips.end()) {
            auto src_it = clock_it->second.find(src);
            if (src_it != clock_it->second.end()) {
                auto& tile = tilemap[{row_ - 1, col_ - 1}];
                for (const auto& [brow, bcol] : src_it->second) {
                    tile[brow][bcol] = 1;
                }
            }
        }
        return;
    }

    // Area-based filtering for GW5AST-138C
    // area: 'T' = top, 'B' = bottom, 'C' = clock bridge
    char area = 'T';
    int64_t allowed_row_start = 0;
    int64_t allowed_row_end = static_cast<int64_t>(db.rows());
    int64_t allowed_col_start = 0;
    int64_t allowed_col_end = static_cast<int64_t>(db.cols());

    // Clock bridge tile types and locations for GW5AST-138C
    static const std::set<int64_t> clock_bridge_ttypes = {80, 81, 82, 83, 84, 85};
    std::set<int64_t> clock_bridge_cols;
    int64_t clock_bridge_row = 54; // single bridge row

    if (device == "GW5AST-138C") {
        allowed_row_end = 55; // top half

        // Build clock bridge cols
        for (int64_t c = 0; c < static_cast<int64_t>(db.cols()); c++) {
            int64_t ttyp = db.get_ttyp(clock_bridge_row, c);
            if (clock_bridge_ttypes.count(ttyp)) {
                clock_bridge_cols.insert(c);
            }
        }

        if (row_ - 1 >= 55) {
            // Bottom half
            allowed_row_start = 55;
            allowed_row_end = static_cast<int64_t>(db.rows());
            area = 'B';
        } else {
            int64_t ttyp = db.get_ttyp(row_ - 1, col_ - 1);
            if (clock_bridge_ttypes.count(ttyp)) {
                // Clock bridge area
                allowed_row_start = clock_bridge_row;
                allowed_row_end = clock_bridge_row + 1;
                allowed_col_start = 0;
                allowed_col_end = static_cast<int64_t>(db.cols());
                // Only include bridge cols
                area = 'C';
            }
        }
    }

    std::string spine_enable_table;
    std::pair<char, std::string> spine_key = {area, dest};

    if (dest.substr(0, 5) == "SPINE" && used_spines.find(spine_key) == used_spines.end()) {
        used_spines.insert(spine_key);

        // Get spine number from name
        const auto& nums = get_clknumbers(device);
        auto it = nums.find(dest);
        if (it != nums.end()) {
            char buf[32];
            snprintf(buf, sizeof(buf), "5A_PCLK_ENABLE_%02d", it->second);
            spine_enable_table = buf;
        }

        // Scan all tiles in allowed area
        for (int64_t row = 0; row < static_cast<int64_t>(db.rows()); row++) {
            if (row < allowed_row_start || row >= allowed_row_end) continue;

            for (int64_t col = 0; col < static_cast<int64_t>(db.cols()); col++) {
                // Area filtering for 138C
                if (device == "GW5AST-138C") {
                    if (area == 'C') {
                        if (!clock_bridge_cols.count(col)) continue;
                    } else if (area == 'T') {
                        // Skip clock bridge tiles in top area
                        if (row == clock_bridge_row && clock_bridge_cols.count(col)) continue;
                    }
                }

                const auto& rc = db.get_tile(row, col);
                int64_t ttyp = db.get_ttyp(row, col);
                std::set<Coord> bits;

                // Check clock_pips for this tile
                auto clock_it = rc.clock_pips.find(dest);
                if (clock_it != rc.clock_pips.end()) {
                    auto src_it = clock_it->second.find(src);
                    if (src_it != clock_it->second.end()) {
                        bits = src_it->second;
                    }
                }

                // Check spine enable table in shortval
                if (!spine_enable_table.empty()) {
                    auto ttyp_it = db.shortval.find(ttyp);
                    if (ttyp_it != db.shortval.end()) {
                        auto table_it = ttyp_it->second.find(spine_enable_table);
                        if (table_it != ttyp_it->second.end()) {
                            Coord key{1, 0};
                            auto val_it = table_it->second.find(key);
                            if (val_it != table_it->second.end()) {
                                bits.insert(val_it->second.begin(), val_it->second.end());
                                std::cerr << "Enable spine " << dest << " <- " << src
                                          << " (" << row_ << ", " << col_ << ") by "
                                          << spine_enable_table << " at (" << row << ", " << col << ")" << std::endl;
                            }
                        }
                    }
                }

                if (!bits.empty()) {
                    auto& tile = tilemap[{row, col}];
                    for (const auto& [brow, bcol] : bits) {
                        if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                            bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                            tile[brow][bcol] = 1;
                        }
                    }
                }
            }
        }
    }
}

} // namespace apycula
