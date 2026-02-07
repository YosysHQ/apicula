// fuses.cpp - Fuse lookup implementation
#include "fuses.hpp"
#include <cmath>

namespace apycula {

// Helper function to check if a table key matches the attrs set
// Matches Python get_table_fuses logic
static bool key_matches(const Coord& key, const std::set<int64_t>& attrs) {
    // Check first element of key
    int64_t attrval1 = key.first;
    if (attrval1 == 0) {
        // No feature needed in first slot
        // Check second element
        int64_t attrval2 = key.second;
        if (attrval2 == 0) return true;
        if (attrval2 > 0) return attrs.count(attrval2) > 0;
        if (attrval2 < 0) return attrs.count(std::abs(attrval2)) == 0;
        return true;
    }
    if (attrval1 > 0) {
        // This feature must be present
        if (attrs.count(attrval1) == 0) return false;
    } else {
        // attrval1 < 0: This feature is set by default and can only be unset
        if (attrs.count(std::abs(attrval1)) > 0) return false;
    }

    // Check second element
    int64_t attrval2 = key.second;
    if (attrval2 == 0) return true;
    if (attrval2 > 0) return attrs.count(attrval2) > 0;
    if (attrval2 < 0) return attrs.count(std::abs(attrval2)) == 0;

    return true;
}

// Helper for 16-element keys (longval)
static bool key_matches(const std::array<int64_t, 16>& key, const std::set<int64_t>& attrs) {
    for (size_t i = 0; i < 16; ++i) {
        int64_t attrval = key[i];
        if (attrval == 0) break;  // No more features
        if (attrval > 0) {
            // This feature must be present
            if (attrs.count(attrval) == 0) return false;
        } else {
            // attrval < 0: This feature is set by default and can only be unset
            if (attrs.count(std::abs(attrval)) > 0) return false;
        }
    }
    return true;
}

std::set<Coord> get_shortval_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table) {

    std::set<Coord> result;
    auto ttyp_it = db.shortval.find(ttyp);
    if (ttyp_it == db.shortval.end()) return result;

    auto table_it = ttyp_it->second.find(table);
    if (table_it == ttyp_it->second.end()) return result;

    // Iterate through all entries and check if key matches attrs
    for (const auto& [key, fuses] : table_it->second) {
        if (key_matches(key, attrs)) {
            result.insert(fuses.begin(), fuses.end());
        }
    }
    return result;
}

std::set<Coord> get_longval_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table) {

    std::set<Coord> result;
    auto ttyp_it = db.longval.find(ttyp);
    if (ttyp_it == db.longval.end()) return result;

    auto table_it = ttyp_it->second.find(table);
    if (table_it == ttyp_it->second.end()) return result;

    // Iterate through all entries and check if key matches attrs
    for (const auto& [key, fuses] : table_it->second) {
        if (key_matches(key, attrs)) {
            result.insert(fuses.begin(), fuses.end());
        }
    }
    return result;
}

std::set<Coord> get_long_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table) {

    std::set<Coord> result;
    auto ttyp_it = db.longfuses.find(ttyp);
    if (ttyp_it == db.longfuses.end()) return result;

    auto table_it = ttyp_it->second.find(table);
    if (table_it == ttyp_it->second.end()) return result;

    // longfuses uses tuple<int64_t> keys (single element)
    for (const auto& [key, fuses] : table_it->second) {
        int64_t attrval = std::get<0>(key);
        bool matches = false;
        if (attrval == 0) {
            matches = true;
        } else if (attrval > 0) {
            matches = (attrs.count(attrval) > 0);
        } else {
            matches = (attrs.count(std::abs(attrval)) == 0);
        }
        if (matches) {
            result.insert(fuses.begin(), fuses.end());
        }
    }
    return result;
}

int64_t add_attr_val(
    const Device& db,
    const std::string& logic_table,
    std::set<int64_t>& attrs,
    int64_t attr_id,
    int64_t val_id) {

    // Look up the code in logicinfo table
    auto table_it = db.logicinfo.find(logic_table);
    if (table_it == db.logicinfo.end()) return 0;

    // Key is (attr_id, val_id)
    Coord key{attr_id, val_id};
    auto code_it = table_it->second.find(key);
    if (code_it != table_it->second.end()) {
        int64_t code = code_it->second;
        if (code != 0) {
            attrs.insert(code);
        }
        return code;
    }
    return 0;
}

std::set<Coord> get_bank_fuses(
    const Device& db,
    int64_t ttyp,
    const std::set<int64_t>& attrs,
    const std::string& table,
    int64_t bank_num) {

    std::set<Coord> result;
    auto ttyp_it = db.longval.find(ttyp);
    if (ttyp_it == db.longval.end()) return result;

    auto table_it = ttyp_it->second.find(table);
    if (table_it == ttyp_it->second.end()) return result;

    // Filter keys by bank number (first element) and check remaining elements
    for (const auto& [key, fuses] : table_it->second) {
        if (key[0] != bank_num) continue;

        // Check remaining elements (skip first which is bank num)
        bool matches = true;
        for (size_t i = 1; i < 16; ++i) {
            int64_t attrval = key[i];
            if (attrval == 0) break;
            if (attrval > 0) {
                if (attrs.count(attrval) == 0) {
                    matches = false;
                    break;
                }
            } else {
                if (attrs.count(std::abs(attrval)) > 0) {
                    matches = false;
                    break;
                }
            }
        }
        if (matches) {
            result.insert(fuses.begin(), fuses.end());
        }
    }
    return result;
}

} // namespace apycula
