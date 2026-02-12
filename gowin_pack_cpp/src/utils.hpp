// utils.hpp - Shared utility functions for the C++ packer
#pragma once

#include <string>
#include <map>
#include <cctype>
#include <cstdint>

namespace apycula {

// Convert string to uppercase
inline std::string to_upper(const std::string& s) {
    std::string result = s;
    for (auto& c : result) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return result;
}

// Uppercase all values in an attribute map
inline void attrs_upper(std::map<std::string, std::string>& attrs) {
    for (auto& [k, v] : attrs) v = to_upper(v);
}

// Parse a binary string to int (handles leading 0b or raw binary digits)
inline int64_t parse_binary(const std::string& s) {
    std::string trimmed = s;
    while (!trimmed.empty() && std::isspace(static_cast<unsigned char>(trimmed.back()))) {
        trimmed.pop_back();
    }
    while (!trimmed.empty() && std::isspace(static_cast<unsigned char>(trimmed.front()))) {
        trimmed.erase(trimmed.begin());
    }
    if (trimmed.empty()) return 0;
    if (trimmed.size() >= 2 && trimmed[0] == '0' && (trimmed[1] == 'b' || trimmed[1] == 'B')) {
        trimmed = trimmed.substr(2);
    }
    try {
        return std::stoll(trimmed, nullptr, 2);
    } catch (...) {
        try {
            return std::stoll(trimmed, nullptr, 10);
        } catch (...) {
            return 0;
        }
    }
}

// Get a value from a string map with a default
inline std::string get_param(const std::map<std::string, std::string>& params,
                             const std::string& key,
                             const std::string& default_val = "") {
    auto it = params.find(key);
    if (it != params.end()) return it->second;
    return default_val;
}

} // namespace apycula
