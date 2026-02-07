// route.cpp - Routing implementation
#include "route.hpp"
#include "place.hpp"
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

    for (const auto& pip : pips) {
        // PIPs use 1-indexed coordinates; convert to 0-indexed for tile access
        int64_t row = pip.row - 1;
        int64_t col = pip.col - 1;

        if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
            col < 0 || col >= static_cast<int64_t>(db.cols())) {
            continue;
        }

        const auto& tiledata = db.get_tile(row, col);
        auto& tile = tilemap[{row, col}];

        // Look up PIP fuses
        std::set<Coord> bits;
        bool found = false;

        // Check clock_pips first (skip for GW5A-25A which uses set_clock_fuses)
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
                        // TODO: bits.update(do_hclk_banks(db, row, col, pip.src, pip.dest))
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
    int64_t row,
    int64_t col,
    const std::string& src,
    const std::string& dest,
    const std::string& device) {

    // Implementation for GW5A clock routing
    const auto& tiledata = db.get_tile(row, col);
    auto& tile = tilemap[{row, col}];

    auto clock_it = tiledata.clock_pips.find(dest);
    if (clock_it != tiledata.clock_pips.end()) {
        auto src_it = clock_it->second.find(src);
        if (src_it != clock_it->second.end()) {
            for (const auto& [brow, bcol] : src_it->second) {
                tile[brow][bcol] = 1;
            }
        }
    }
}

} // namespace apycula
