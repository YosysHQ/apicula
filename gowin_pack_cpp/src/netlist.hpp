// netlist.hpp - Nextpnr JSON netlist parsing
#pragma once

#include <string>
#include <vector>
#include <map>
#include <variant>

namespace apycula {

// Parameter value can be string, int, or bool
using ParamValue = std::variant<std::string, int64_t, bool>;
using ParamMap = std::map<std::string, ParamValue>;

// A cell in the netlist
struct Cell {
    std::string name;
    std::string type;
    ParamMap parameters;
    ParamMap attributes;
    std::map<std::string, std::vector<int>> port_connections;  // port -> bit indices
};

// A net in the netlist
struct Net {
    std::string name;
    std::vector<int> bits;
    ParamMap attributes;
};

// The complete netlist
struct Netlist {
    std::string top;
    std::map<std::string, Cell> cells;
    std::map<std::string, Net> nets;
    std::map<std::string, std::string> settings;
};

// Parse a Nextpnr JSON file
Netlist parse_netlist(const std::string& path);

} // namespace apycula
