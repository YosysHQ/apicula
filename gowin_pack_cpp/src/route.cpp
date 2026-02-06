// route.cpp - Routing implementation
#include "route.hpp"
#include <regex>
#include <iostream>

namespace apycula {

std::vector<Pip> get_pips(const Netlist& netlist) {
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
        // Format: wire1;pip1;wire2;pip2;...
        size_t pos = 0;
        int count = 0;
        while (pos < routing.size()) {
            size_t next = routing.find(';', pos);
            if (next == std::string::npos) next = routing.size();
            std::string segment = routing.substr(pos, next - pos);
            pos = next + 1;

            // Every 3rd segment (1-indexed) is a pip
            if (count % 3 == 1 && !segment.empty()) {
                std::smatch match;
                if (std::regex_match(segment, match, pip_re)) {
                    Pip pip;
                    pip.col = std::stoll(match[1].str()) + 1;
                    pip.row = std::stoll(match[2].str()) + 1;
                    pip.dest = match[3].str();
                    pip.src = match[4].str();
                    pips.push_back(pip);
                }
            }
            count++;
        }
    }
    return pips;
}

void route_nets(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device) {

    auto pips = get_pips(netlist);

    for (const auto& pip : pips) {
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

        // Check clock_pips first
        auto clock_it = tiledata.clock_pips.find(pip.dest);
        if (clock_it != tiledata.clock_pips.end()) {
            auto src_it = clock_it->second.find(pip.src);
            if (src_it != clock_it->second.end()) {
                bits = src_it->second;
            }
        }

        // Check regular pips
        if (bits.empty()) {
            auto pip_it = tiledata.pips.find(pip.dest);
            if (pip_it != tiledata.pips.end()) {
                auto src_it = pip_it->second.find(pip.src);
                if (src_it != pip_it->second.end()) {
                    bits = src_it->second;
                }
            }
        }

        // Check alonenode for isolation fuses
        auto alone_it = tiledata.alonenode.find(pip.dest);
        if (alone_it != tiledata.alonenode.end()) {
            for (const auto& [srcs, fuses] : alone_it->second) {
                if (srcs.find(pip.src) == srcs.end()) {
                    // Source not in allowed set, add isolation fuses
                    bits.insert(fuses.begin(), fuses.end());
                }
            }
        }

        // Set the fuse bits
        for (const auto& [brow, bcol] : bits) {
            if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                tile[brow][bcol] = 1;
            }
        }
    }
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
