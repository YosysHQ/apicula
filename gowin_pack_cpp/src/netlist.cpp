// netlist.cpp - Nextpnr JSON netlist parsing implementation
#include "netlist.hpp"

#include <fstream>
#include <stdexcept>
#include <nlohmann/json.hpp>

namespace apycula {

Netlist parse_netlist(const std::string& path) {
    std::ifstream file(path);
    if (!file) {
        throw std::runtime_error("Could not open netlist file: " + path);
    }

    nlohmann::ordered_json j;
    file >> j;

    Netlist netlist;
    netlist.top = j.value("top", "top");

    // Parse settings
    if (j.contains("modules") && j["modules"].contains(netlist.top)) {
        const auto& module = j["modules"][netlist.top];

        if (module.contains("settings")) {
            for (const auto& [key, val] : module["settings"].items()) {
                if (val.is_string()) {
                    netlist.settings[key] = val.get<std::string>();
                }
            }
        }

        // Parse cells
        if (module.contains("cells")) {
            for (const auto& [name, cell_json] : module["cells"].items()) {
                Cell cell;
                cell.name = name;
                cell.type = cell_json.value("type", "");

                if (cell_json.contains("parameters")) {
                    for (const auto& [pname, pval] : cell_json["parameters"].items()) {
                        if (pval.is_string()) {
                            cell.parameters[pname] = pval.get<std::string>();
                        } else if (pval.is_number_integer()) {
                            cell.parameters[pname] = pval.get<int64_t>();
                        } else if (pval.is_boolean()) {
                            cell.parameters[pname] = pval.get<bool>();
                        }
                    }
                }

                if (cell_json.contains("attributes")) {
                    for (const auto& [aname, aval] : cell_json["attributes"].items()) {
                        if (aval.is_string()) {
                            cell.attributes[aname] = aval.get<std::string>();
                        } else if (aval.is_number_integer()) {
                            cell.attributes[aname] = aval.get<int64_t>();
                        }
                    }
                }

                if (cell_json.contains("connections")) {
                    for (const auto& [port, bits] : cell_json["connections"].items()) {
                        if (bits.is_array()) {
                            std::vector<int> bit_vec;
                            for (const auto& bit : bits) {
                                if (bit.is_number_integer()) {
                                    bit_vec.push_back(bit.get<int>());
                                } else if (bit.is_string()) {
                                    // "x" means unconnected
                                    bit_vec.push_back(-1);
                                }
                            }
                            cell.port_connections[port] = std::move(bit_vec);
                        }
                    }
                }

                netlist.cells[name] = std::move(cell);
                netlist.cell_order.push_back(name);
            }
        }

        // Parse nets
        if (module.contains("netnames")) {
            for (const auto& [name, net_json] : module["netnames"].items()) {
                Net net;
                net.name = name;

                if (net_json.contains("bits")) {
                    for (const auto& bit : net_json["bits"]) {
                        if (bit.is_number_integer()) {
                            net.bits.push_back(bit.get<int>());
                        }
                    }
                }

                if (net_json.contains("attributes")) {
                    for (const auto& [aname, aval] : net_json["attributes"].items()) {
                        if (aval.is_string()) {
                            net.attributes[aname] = aval.get<std::string>();
                        } else if (aval.is_number_integer()) {
                            net.attributes[aname] = aval.get<int64_t>();
                        }
                    }
                }

                netlist.nets[name] = std::move(net);
            }
        }
    }

    return netlist;
}

} // namespace apycula
