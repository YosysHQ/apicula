// chipdb.hpp - Chip database loading and access
#pragma once

#include <string>
#include <vector>
#include <fstream>
#include <stdexcept>

#include <msgpack.hpp>
#include "chipdb_types.hpp"
#include "chipdb_adaptors.hpp"

namespace apycula {

// Find the chipdb file for a given device
std::string find_chipdb(const std::string& device);

// Load a chipdb from a MessagePack file
Device load_chipdb(const std::string& path);

// Check if device is GW5 family
inline bool is_gw5_family(const std::string& device) {
    return device == "GW5A-25A" || device == "GW5AST-138C";
}

} // namespace apycula
