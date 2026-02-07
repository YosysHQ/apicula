// fuses.hpp - Fuse lookup functions
#pragma once

#include "chipdb_types.hpp"
#include <set>

namespace apycula {

// Get fuses from shortval table matching an attribute set
// attrs is a set of logicinfo codes (integers)
// Returns set of fuse coordinates
std::set<Coord> get_shortval_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table);

// Get fuses from longval table matching an attribute set
std::set<Coord> get_longval_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table);

// Get fuses from longfuses table for a single feature
std::set<Coord> get_long_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table);

// Add attribute value to attrs set by looking up in logicinfo table
// Returns the code that was added (or 0 if not found)
int64_t add_attr_val(
    const Device& db,
    const std::string& logic_table,
    std::set<int64_t>& attrs,
    int64_t attr_id,
    int64_t val_id);

// Get bank fuses from longval table
std::set<Coord> get_bank_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table,
    int64_t bank_num);

} // namespace apycula
