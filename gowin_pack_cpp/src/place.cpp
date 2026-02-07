// place.cpp - BEL placement implementation
// Based on apycula/gowin_pack.py place_* functions
#include "place.hpp"
#include "fuses.hpp"
#include "attrids.hpp"
#include <regex>
#include <iostream>
#include <cmath>
#include <algorithm>
#include <sstream>

namespace apycula {

// ============================================================================
// Helper functions
// ============================================================================

void set_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses) {
    for (const auto& [brow, bcol] : fuses) {
        if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
            bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
            tile[brow][bcol] = 1;
        }
    }
}

void clear_fuses_in_tile(TileBitmap& tile, const std::set<Coord>& fuses) {
    for (const auto& [brow, bcol] : fuses) {
        if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
            bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
            tile[brow][bcol] = 0;
        }
    }
}

// Convert string to uppercase
static std::string to_upper(const std::string& s) {
    std::string result = s;
    for (auto& c : result) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return result;
}

// Parse a binary string to int (handles leading 0b or raw binary digits)
static int64_t parse_binary(const std::string& s) {
    std::string trimmed = s;
    // Trim whitespace
    while (!trimmed.empty() && std::isspace(static_cast<unsigned char>(trimmed.back()))) {
        trimmed.pop_back();
    }
    while (!trimmed.empty() && std::isspace(static_cast<unsigned char>(trimmed.front()))) {
        trimmed.erase(trimmed.begin());
    }
    if (trimmed.empty()) return 0;
    // Handle 0b prefix
    if (trimmed.size() >= 2 && trimmed[0] == '0' && (trimmed[1] == 'b' || trimmed[1] == 'B')) {
        trimmed = trimmed.substr(2);
    }
    try {
        return std::stoll(trimmed, nullptr, 2);
    } catch (...) {
        // Try decimal
        try {
            return std::stoll(trimmed, nullptr, 10);
        } catch (...) {
            return 0;
        }
    }
}

// Check if a net bit index is a constant net (0 or 1 means VCC/GND in nextpnr)
static bool is_const_net(int bit) {
    return bit == 0 || bit == 1;
}

// Get parameter with default
static std::string get_param(const std::map<std::string, std::string>& params,
                             const std::string& key,
                             const std::string& default_val = "") {
    auto it = params.find(key);
    if (it != params.end()) return it->second;
    return default_val;
}

// Get attribute with default
static std::string get_attr(const std::map<std::string, std::string>& attrs,
                            const std::string& key,
                            const std::string& default_val = "") {
    auto it = attrs.find(key);
    if (it != attrs.end()) return it->second;
    return default_val;
}

// ============================================================================
// Store slice attributes to be applied at the end
// Key: (row, col, slice_idx), Value: map of attr->val
// ============================================================================
static std::map<std::tuple<int64_t, int64_t, int64_t>, std::map<std::string, std::string>> slice_attrvals;

// ============================================================================
// get_bels - Extract BELs from netlist
// ============================================================================
std::vector<BelInfo> get_bels(const Netlist& netlist) {
    std::vector<BelInfo> bels;
    std::regex bel_re(R"(X(\d+)Y(\d+)/(?:GSR|LUT|DFF|IOB|MUX|ALU|ODDR|OSC[ZFHWOA]?|BUF[GS]|RAM16SDP4|RAM16SDP2|RAM16SDP1|PLL[A]?|IOLOGIC|CLKDIV2?|BSRAM|DSP|MULT\w+|PADD\d+|BANDGAP|DQCE|DCS|USERFLASH|EMCU|DHCEN|MIPI_[IO]BUF|DLLDLY|PINCFG|ADC)(\w*))");

    for (const auto& [cellname, cell] : netlist.cells) {
        // Skip dummy cells and cells without BEL attribute
        if (cell.type.size() >= 6 && cell.type.substr(0, 6) == "DUMMY_") continue;
        if (cell.type == "OSER16" || cell.type == "IDES16") continue;

        auto bel_attr = cell.attributes.find("NEXTPNR_BEL");
        if (bel_attr == cell.attributes.end()) continue;

        std::string bel_str;
        if (auto* s = std::get_if<std::string>(&bel_attr->second)) {
            bel_str = *s;
        } else {
            continue;
        }

        if (bel_str == "VCC" || bel_str == "GND") continue;
        if (bel_str.size() >= 4 && (bel_str.substr(bel_str.size()-4) == "/GND" ||
                                     bel_str.substr(bel_str.size()-4) == "/VCC")) continue;

        std::smatch match;
        if (!std::regex_match(bel_str, match, bel_re)) {
            std::cerr << "Unknown bel: " << bel_str << std::endl;
            continue;
        }

        BelInfo bel;
        bel.col = std::stoll(match[1].str()) + 1;
        bel.row = std::stoll(match[2].str()) + 1;
        bel.type = cell.type;
        bel.num = match[3].str();
        bel.name = cellname;
        bel.cell = &cell;  // Store pointer to original cell

        // Copy parameters and attributes
        for (const auto& [k, v] : cell.parameters) {
            if (auto* s = std::get_if<std::string>(&v)) {
                bel.parameters[k] = *s;
            } else if (auto* i = std::get_if<int64_t>(&v)) {
                bel.parameters[k] = std::to_string(*i);
            }
        }
        for (const auto& [k, v] : cell.attributes) {
            if (auto* s = std::get_if<std::string>(&v)) {
                bel.attributes[k] = *s;
            } else if (auto* i = std::get_if<int64_t>(&v)) {
                bel.attributes[k] = std::to_string(*i);
            }
        }

        bels.push_back(std::move(bel));
    }
    return bels;
}

// ============================================================================
// place_cells - Main entry point for placement
// ============================================================================
void place_cells(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device,
    const std::vector<BelInfo>& extra_bels) {

    // Clear slice attributes for fresh run
    slice_attrvals.clear();

    auto bels = get_bels(netlist);
    // Append pass-through LUTs from routing
    bels.insert(bels.end(), extra_bels.begin(), extra_bels.end());

    for (const auto& bel : bels) {
        if (bel.type == "LUT4" || bel.type == "LUT1" || bel.type == "LUT2" || bel.type == "LUT3") {
            place_lut(db, bel, tilemap);
        } else if (bel.type.size() >= 3 && bel.type.substr(0, 3) == "DFF") {
            place_dff(db, bel, tilemap);
        } else if (bel.type == "ALU") {
            place_alu(db, bel, tilemap);
        } else if (bel.type == "IBUF" || bel.type == "OBUF" || bel.type == "IOBUF" || bel.type == "TBUF") {
            place_iob(db, bel, tilemap, device);
        } else if (bel.type == "rPLL" || bel.type == "PLLVR" || bel.type == "PLLA" || bel.type == "RPLLA") {
            place_pll(db, bel, tilemap, device);
        } else if (bel.type == "DP" || bel.type == "SDP" || bel.type == "SP" || bel.type == "ROM") {
            place_bsram(db, bel, tilemap, device);
        } else if (bel.type.find("MULT") != std::string::npos ||
                   bel.type.find("ALU54") != std::string::npos ||
                   bel.type.find("PADD") != std::string::npos) {
            place_dsp(db, bel, tilemap, device);
        } else if (bel.type == "IOLOGIC" || bel.type == "ODDR" || bel.type == "IDDR" ||
                   bel.type == "ODDRC" || bel.type == "IDDRC" ||
                   bel.type.find("OSER") != std::string::npos ||
                   bel.type.find("IDES") != std::string::npos ||
                   bel.type.find("OVIDEO") != std::string::npos ||
                   bel.type.find("IVIDEO") != std::string::npos ||
                   bel.type == "IOLOGIC_DUMMY" ||
                   bel.type == "IOLOGICI_EMPTY" ||
                   bel.type == "IOLOGICO_EMPTY") {
            place_iologic(db, bel, tilemap, device);
        } else if (bel.type == "OSC" || bel.type == "OSCZ" || bel.type == "OSCF" ||
                   bel.type == "OSCH" || bel.type == "OSCW" || bel.type == "OSCO" ||
                   bel.type == "OSCA") {
            place_osc(db, bel, tilemap, device);
        } else if (bel.type == "BUFS") {
            place_bufs(db, bel, tilemap);
        } else if (bel.type.find("RAM16SDP") != std::string::npos || bel.type == "RAMW") {
            place_ram16sdp(db, bel, tilemap);
        } else if (bel.type.find("CLKDIV") != std::string::npos) {
            place_clkdiv(db, bel, tilemap);
        } else if (bel.type == "DCS") {
            place_dcs(db, bel, tilemap, device);
        } else if (bel.type == "DQCE") {
            place_dqce(db, bel, tilemap);
        } else if (bel.type == "DHCEN") {
            place_dhcen(db, bel, tilemap);
        } else if (bel.type == "GSR" ||
                   bel.type == "BANDGAP" ||
                   bel.type == "PINCFG" ||
                   bel.type.find("FLASH") != std::string::npos ||
                   bel.type.find("EMCU") != std::string::npos ||
                   bel.type.find("MUX2_") != std::string::npos ||
                   bel.type == "MIPI_OBUF" ||
                   bel.type == "MIPI_IBUF" ||
                   bel.type.find("BUFG") != std::string::npos) {
            // No-op types - skip
            continue;
        } else {
            std::cerr << "Warning: unhandled BEL type '" << bel.type << "' for " << bel.name << std::endl;
        }
    }

    // Apply slice fuses at the end
    set_slice_fuses(db, tilemap);
}

// ============================================================================
// place_lut - Place a LUT BEL
// ============================================================================
void place_lut(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    auto& tile = tilemap[{row, col}];
    const auto& tiledata = db.get_tile(row, col);

    // Get LUT INIT value
    auto init_it = bel.parameters.find("INIT");
    if (init_it == bel.parameters.end()) return;

    std::string init = init_it->second;

    // Normalize to 16 bits
    if (init.size() > 16) {
        init = init.substr(init.size() - 16);
    } else if (init.size() < 16) {
        // Repeat to fill 16 bits
        std::string padded;
        while (padded.size() < 16) {
            padded += init;
        }
        init = padded.substr(0, 16);
    }

    // Find LUT bel in tiledata
    std::string lut_name = "LUT" + bel.num;
    auto bel_it = tiledata.bels.find(lut_name);
    if (bel_it == tiledata.bels.end()) {
        return;
    }

    const auto& lut_bel = bel_it->second;

    // For each '0' bit in INIT (read from LSB to MSB), set the corresponding fuses
    // Python: for bitnum, lutbit in enumerate(init[::-1]): if lutbit == '0': ...
    for (size_t bitnum = 0; bitnum < 16 && bitnum < init.size(); ++bitnum) {
        char lutbit = init[init.size() - 1 - bitnum];  // Reverse order
        if (lutbit == '0') {
            // Look up fuses for this bit position in bel.flags
            auto flags_it = lut_bel.flags.find(static_cast<int64_t>(bitnum));
            if (flags_it != lut_bel.flags.end()) {
                for (const auto& [brow, bcol] : flags_it->second) {
                    if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                        bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                        tile[brow][bcol] = 1;
                    }
                }
            }
        }
    }

    // Mark slice as used (for later slice fuse processing)
    int slice_idx = 0;
    if (!bel.num.empty()) {
        slice_idx = (bel.num[0] - '0') / 2;
    }
    slice_attrvals[{bel.row, bel.col, slice_idx}];  // Create entry if not exists
}

// ============================================================================
// place_dff - Place a DFF BEL
// ============================================================================
void place_dff(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    (void)tilemap;  // DFF doesn't set fuses directly, uses slice fuses

    int dff_num = 0;
    if (!bel.num.empty()) {
        dff_num = bel.num[0] - '0';
    }
    int slice_idx = dff_num / 2;
    int reg_idx = dff_num % 2;

    // Get DFF mode from type (DFFE -> DFF, DFFR -> DFF with reset, etc.)
    std::string mode = bel.type;
    // Strip trailing 'E' for enable variants
    if (mode.size() > 3 && mode.back() == 'E') {
        mode = mode.substr(0, mode.size() - 1);
    }

    // Set slice attributes
    auto& dff_attrs = slice_attrvals[{bel.row, bel.col, slice_idx}];
    dff_attrs["REGMODE"] = "FF";
    dff_attrs["CEMUX_1"] = "UNKNOWN";
    dff_attrs["CEMUX_CE"] = "SIG";

    // REG0_REGSET and REG1_REGSET select set/reset or preset/clear
    if (mode == "DFFR" || mode == "DFFC" || mode == "DFFNR" || mode == "DFFNC" ||
        mode == "DFF" || mode == "DFFN") {
        dff_attrs["REG" + std::to_string(reg_idx) + "_REGSET"] = "RESET";
    } else {
        dff_attrs["REG" + std::to_string(reg_idx) + "_REGSET"] = "SET";
    }

    // Are set/reset/clear/preset port needed?
    if (mode != "DFF" && mode != "DFFN") {
        dff_attrs["LSRONMUX"] = "LSRMUX";
    }

    // Invert clock?
    if (mode == "DFFN" || mode == "DFFNR" || mode == "DFFNC" ||
        mode == "DFFNP" || mode == "DFFNS") {
        dff_attrs["CLKMUX_CLK"] = "INV";
    } else {
        dff_attrs["CLKMUX_CLK"] = "SIG";
    }

    // Async option?
    if (mode == "DFFNC" || mode == "DFFNP" || mode == "DFFC" || mode == "DFFP") {
        dff_attrs["SRMODE"] = "ASYNC";
    }
}

// ============================================================================
// place_alu - Place an ALU BEL
// ============================================================================
void place_alu(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    auto& tile = tilemap[{row, col}];
    const auto& tiledata = db.get_tile(row, col);

    int alu_num = 0;
    if (!bel.num.empty()) {
        alu_num = bel.num[0] - '0';
    }
    int slice_idx = alu_num / 2;

    // Clear LUT bits first
    std::string lut_name = "LUT" + bel.num;
    auto lut_it = tiledata.bels.find(lut_name);
    if (lut_it != tiledata.bels.end()) {
        for (const auto& [bitnum, fuses] : lut_it->second.flags) {
            for (const auto& [brow, bcol] : fuses) {
                if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                    bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                    tile[brow][bcol] = 0;
                }
            }
        }
    }

    // Get ALU mode fuses
    std::set<Coord> bits;
    std::string alu_name = "ALU" + bel.num;
    auto alu_it = tiledata.bels.find(alu_name);

    // Check for RAW_ALU_LUT first (optimized by nextpnr)
    auto raw_lut_it = bel.parameters.find("RAW_ALU_LUT");
    if (raw_lut_it != bel.parameters.end() && lut_it != tiledata.bels.end()) {
        std::string alu_init = raw_lut_it->second;
        if (alu_init.size() > 16) {
            alu_init = alu_init.substr(alu_init.size() - 16);
        } else if (alu_init.size() < 16) {
            std::string padded;
            while (padded.size() < 16) {
                padded += alu_init;
            }
            alu_init = padded.substr(0, 16);
        }

        for (size_t bitnum = 0; bitnum < 16 && bitnum < alu_init.size(); ++bitnum) {
            char bit = alu_init[alu_init.size() - 1 - bitnum];
            if (bit == '0') {
                auto flags_it = lut_it->second.flags.find(static_cast<int64_t>(bitnum));
                if (flags_it != lut_it->second.flags.end()) {
                    bits.insert(flags_it->second.begin(), flags_it->second.end());
                }
            }
        }
    } else if (alu_it != tiledata.bels.end()) {
        // Use ALU_MODE
        auto mode_it = bel.parameters.find("ALU_MODE");
        if (mode_it != bel.parameters.end()) {
            std::string mode = mode_it->second;
            // Try to find mode in alu_bel.modes
            auto modes_it = alu_it->second.modes.find(mode);
            if (modes_it != alu_it->second.modes.end()) {
                bits = modes_it->second;
            } else {
                // Try converting from binary
                try {
                    int mode_val = std::stoi(mode, nullptr, 2);
                    modes_it = alu_it->second.modes.find(std::to_string(mode_val));
                    if (modes_it != alu_it->second.modes.end()) {
                        bits = modes_it->second;
                    }
                } catch (...) {}
            }
        }
    }

    // Set the ALU fuses
    for (const auto& [brow, bcol] : bits) {
        if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
            bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
            tile[brow][bcol] = 1;
        }
    }

    // Enable ALU in slice
    auto& alu_attrs = slice_attrvals[{bel.row, bel.col, slice_idx}];
    alu_attrs["MODE"] = "ALU";
    alu_attrs["MODE_5A_" + std::to_string(alu_num % 2)] = "ALU";

    // CIN handling
    auto cin_it = bel.parameters.find("CIN_NETTYPE");
    if (cin_it != bel.parameters.end()) {
        if (cin_it->second == "VCC") {
            alu_attrs["ALU_CIN_MUX"] = "ALU_5A_CIN_VCC";
        } else if (cin_it->second == "GND") {
            alu_attrs["ALU_CIN_MUX"] = "ALU_5A_CIN_GND";
        } else {
            alu_attrs["ALU_CIN_MUX"] = "ALU_5A_CIN_COUT";
        }
    } else if (alu_attrs.find("ALU_CIN_MUX") == alu_attrs.end()) {
        alu_attrs["ALU_CIN_MUX"] = "ALU_5A_CIN_COUT";
    }
}

// ============================================================================
// IOB constants and helpers
// ============================================================================

// Default IO standard by mode
static const std::map<std::string, std::string> default_iostd = {
    {"IBUF", "LVCMOS18"}, {"OBUF", "LVCMOS18"}, {"TBUF", "LVCMOS18"}, {"IOBUF", "LVCMOS18"},
};

// VCC by IO standard
static const std::map<std::string, std::string> vcc_ios = {
    {"LVCMOS10", "1.0"}, {"LVCMOS12", "1.2"}, {"LVCMOS15", "1.5"}, {"LVCMOS18", "1.8"},
    {"LVCMOS25", "2.5"}, {"LVCMOS33", "3.3"}, {"LVDS25", "2.5"}, {"LVCMOS33D", "3.3"},
    {"LVCMOS_D", "3.3"}, {"MIPI", "1.2"},
    {"SSTL15", "1.5"}, {"SSTL18_I", "1.8"}, {"SSTL18_II", "1.8"},
    {"SSTL25_I", "2.5"}, {"SSTL25_II", "2.5"}, {"SSTL33_I", "3.3"}, {"SSTL33_II", "3.3"},
    {"SSTL15D", "1.5"}, {"SSTL18D_I", "1.8"}, {"SSTL18D_II", "1.8"},
    {"SSTL25D_I", "2.5"}, {"SSTL25D_II", "2.5"}, {"SSTL33D_I", "3.3"}, {"SSTL33D_II", "3.3"},
};

// Initial IO attributes per mode
static const std::map<std::string, std::map<std::string, std::string>> init_io_attrs = {
    {"IBUF", {
        {"PADDI", "PADDI"}, {"HYSTERESIS", "NONE"}, {"PULLMODE", "UP"}, {"SLEWRATE", "SLOW"},
        {"DRIVE", "0"}, {"CLAMP", "OFF"}, {"OPENDRAIN", "OFF"}, {"DIFFRESISTOR", "OFF"},
        {"VREF", "OFF"}, {"LVDS_OUT", "OFF"},
    }},
    {"OBUF", {
        {"ODMUX_1", "1"}, {"PULLMODE", "UP"}, {"SLEWRATE", "FAST"},
        {"DRIVE", "8"}, {"HYSTERESIS", "NONE"}, {"CLAMP", "OFF"},
        {"SINGLERESISTOR", "OFF"}, {"BANK_VCCIO", "1.8"}, {"LVDS_OUT", "OFF"},
        {"DDR_DYNTERM", "NA"}, {"TO", "INV"}, {"OPENDRAIN", "OFF"},
    }},
    {"TBUF", {
        {"ODMUX_1", "UNKNOWN"}, {"PULLMODE", "UP"}, {"SLEWRATE", "FAST"},
        {"DRIVE", "8"}, {"HYSTERESIS", "NONE"}, {"CLAMP", "OFF"},
        {"SINGLERESISTOR", "OFF"}, {"BANK_VCCIO", "1.8"}, {"LVDS_OUT", "OFF"},
        {"DDR_DYNTERM", "NA"}, {"TO", "INV"}, {"PERSISTENT", "OFF"},
        {"ODMUX", "TRIMUX"}, {"OPENDRAIN", "OFF"},
    }},
    {"IOBUF", {
        {"ODMUX_1", "UNKNOWN"}, {"PULLMODE", "UP"}, {"SLEWRATE", "FAST"},
        {"DRIVE", "8"}, {"HYSTERESIS", "NONE"}, {"CLAMP", "OFF"}, {"DIFFRESISTOR", "OFF"},
        {"SINGLERESISTOR", "OFF"}, {"BANK_VCCIO", "1.8"}, {"LVDS_OUT", "OFF"},
        {"DDR_DYNTERM", "NA"}, {"TO", "INV"}, {"PERSISTENT", "OFF"},
        {"ODMUX", "TRIMUX"}, {"PADDI", "PADDI"}, {"OPENDRAIN", "OFF"},
    }},
};

// Refine IO attribute names (nextpnr uses different names than the db)
static const std::map<std::string, std::string> refine_attrs_map = {
    {"SLEW_RATE", "SLEWRATE"}, {"PULL_MODE", "PULLMODE"}, {"OPEN_DRAIN", "OPENDRAIN"},
};

static std::string refine_io_attr_name(const std::string& attr) {
    auto it = refine_attrs_map.find(attr);
    if (it != refine_attrs_map.end()) return it->second;
    return attr;
}

// Get IO standard alias
static std::string get_iostd_alias(const std::string& iostd) {
    // Map specific IO standards to their aliases used in the fuse tables
    static const std::map<std::string, std::string> aliases = {
        {"BLVDS25E", "BLVDS_E"}, {"LVTTL33", "LVCMOS33"},
        {"LVCMOS12D", "LVCMOS_D"}, {"LVCMOS15D", "LVCMOS_D"},
        {"LVCMOS18D", "LVCMOS_D"}, {"LVCMOS25D", "LVCMOS_D"}, {"LVCMOS33D", "LVCMOS_D"},
        {"HSTL15", "HSTL"}, {"HSTL18_I", "HSTL"}, {"HSTL18_II", "HSTL"},
        {"SSTL15", "SSTL"}, {"SSTL18_I", "SSTL"}, {"SSTL18_II", "SSTL"},
        {"SSTL25_I", "SSTL"}, {"SSTL25_II", "SSTL"}, {"SSTL33_I", "SSTL"}, {"SSTL33_II", "SSTL"},
        {"MLVDS25E", "MLVDS_E"},
        {"SSTL15D", "SSTL_D"}, {"SSTL18D_I", "SSTL_D"}, {"SSTL18D_II", "SSTL_D"},
        {"SSTL25D_I", "SSTL_D"}, {"SSTL25D_II", "SSTL_D"}, {"SSTL33D_I", "SSTL_D"}, {"SSTL33D_II", "SSTL_D"},
        {"HSTL15D", "HSTL_D"}, {"HSTL18D_I", "HSTL_D"}, {"HSTL18D_II", "HSTL_D"},
        {"RSDS", "RSDS25"}, {"RSDS25E", "RSDS_E"},
    };
    auto it = aliases.find(iostd);
    if (it != aliases.end()) return it->second;
    return iostd;
}

// ============================================================================
// place_iob - Place an IOB BEL
// Uses longval tables for fuse lookup
// ============================================================================
void place_iob(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);

    // Determine IOB mode from cell type
    std::string mode = bel.type;  // IBUF, OBUF, TBUF, IOBUF

    // Determine IOB index (A or B) from bel num
    std::string iob_idx = bel.num;
    if (iob_idx.empty()) iob_idx = "A";

    // Check that this IOB exists in the tile
    std::string iob_bel_name = "IOB" + iob_idx;
    if (tiledata.bels.find(iob_bel_name) == tiledata.bels.end()) {
        std::cerr << "Warning: IOB " << iob_bel_name << " not found in tile at ("
                  << row << "," << col << ")" << std::endl;
        return;
    }

    // Build IOB attributes starting from defaults for this mode
    auto init_it = init_io_attrs.find(mode);
    if (init_it == init_io_attrs.end()) {
        std::cerr << "Warning: Unknown IOB mode " << mode << std::endl;
        return;
    }
    std::map<std::string, std::string> in_iob_attrs = init_it->second;

    // Determine IO standard
    std::string iostd;
    auto iostd_default_it = default_iostd.find(mode);
    if (iostd_default_it != default_iostd.end()) {
        iostd = iostd_default_it->second;
    } else {
        iostd = "LVCMOS18";
    }

    // For GW5A-25A, default IO standard is LVCMOS33
    if (device == "GW5A-25A" || device == "GW5AST-138C") {
        iostd = "LVCMOS33";
    }

    in_iob_attrs["IO_TYPE"] = iostd;

    // Apply user attributes from the cell
    // Mode attribute separator is '&' in nextpnr himbaechel
    for (const auto& [flag, val] : bel.attributes) {
        // Attributes from nextpnr come as "&IO_TYPE=LVCMOS33" etc.
        if (!flag.empty() && flag[0] == '&') {
            size_t eq_pos = flag.find('=');
            if (eq_pos != std::string::npos) {
                std::string attr_name = flag.substr(1, eq_pos - 1);
                std::string attr_val = flag.substr(eq_pos + 1);
                attr_name = refine_io_attr_name(attr_name);
                if (attr_name == "IO_TYPE") {
                    iostd = get_iostd_alias(attr_val);
                    attr_val = iostd;
                }
                in_iob_attrs[attr_name] = attr_val;
            }
        }
    }

    // Also check for direct attributes (from himbaechel)
    for (const auto& [k, v] : bel.parameters) {
        std::string rk = refine_io_attr_name(k);
        if (rk == "IO_TYPE") {
            iostd = get_iostd_alias(v);
            in_iob_attrs["IO_TYPE"] = iostd;
        } else if (rk == "SLEWRATE" || rk == "PULLMODE" || rk == "DRIVE" ||
                   rk == "OPENDRAIN" || rk == "HYSTERESIS" || rk == "CLAMP" ||
                   rk == "DIFFRESISTOR" || rk == "SINGLERESISTOR" || rk == "VREF" ||
                   rk == "DDR_DYNTERM") {
            in_iob_attrs[rk] = v;
        }
    }

    // Handle OEN (output enable) connections for TBUF/IOBUF
    if (mode != "IBUF") {
        // Check for TRIMUX_PADDT attribute from nextpnr
        auto trimux_it = bel.parameters.find("TRIMUX_PADDT");
        if (trimux_it != bel.parameters.end()) {
            in_iob_attrs["TRIMUX_PADDT"] = trimux_it->second;
        }
        auto to_it = bel.parameters.find("TO");
        if (to_it != bel.parameters.end()) {
            in_iob_attrs["TO"] = to_it->second;
        }
    }

    // Set BANK_VCCIO based on IO standard
    auto vcc_it = vcc_ios.find(iostd);
    if (vcc_it != vcc_ios.end()) {
        in_iob_attrs["BANK_VCCIO"] = vcc_it->second;
    }

    // Build the fuse attribute set
    std::set<int64_t> iob_attrs_set;
    for (const auto& [k, val] : in_iob_attrs) {
        auto attr_it = iob_attrids.find(k);
        if (attr_it == iob_attrids.end()) {
            // Skip unknown attributes silently
            continue;
        }
        auto val_it = iob_attrvals.find(val);
        if (val_it == iob_attrvals.end()) {
            // Skip unknown values silently
            continue;
        }
        add_attr_val(db, "IOB", iob_attrs_set, attr_it->second, val_it->second);
    }

    // Handle fuse_cell_offset for GW5A devices
    int64_t fuse_row = row;
    int64_t fuse_col = col;
    int64_t fuse_ttyp = tiledata.ttyp;

    if (device == "GW5A-25A" || device == "GW5AST-138C") {
        auto iob_bel_it = tiledata.bels.find(iob_bel_name);
        if (iob_bel_it != tiledata.bels.end() && iob_bel_it->second.fuse_cell_offset) {
            fuse_row += iob_bel_it->second.fuse_cell_offset->first;
            fuse_col += iob_bel_it->second.fuse_cell_offset->second;
            fuse_ttyp = db.get_ttyp(fuse_row, fuse_col);
        }
        // GW5A special: add TRIMUX attribute for output modes
        if (mode == "OBUF" || mode == "IOBUF") {
            add_attr_val(db, "IOB", iob_attrs_set, iob_attrids.at("IOB_UNKNOWN51"), iob_attrvals.at("TRIMUX"));
        }
    }

    // Look up fuses from longval table
    std::set<Coord> fuses = get_longval_fuses(db, fuse_ttyp, iob_attrs_set, "IOB" + iob_idx);

    // Set fuses in tile
    auto& tile = tilemap[{fuse_row, fuse_col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// set_iob_default_fuses - Set default IO fuses for all IOB pins
// Matches Python gowin_pack.py lines 3758-3849 (unused IOB loop)
// and lines 3732-3749 (bank-level fuses)
// ============================================================================

// Helper: convert 0-indexed (row, col) + idx to pin name like "IOT2A"
static std::string rc_to_pin_name(const Device& db, int64_t row, int64_t col, const std::string& idx) {
    std::string side;
    auto corner_it = db.corner_tiles_io.find({row, col});
    if (corner_it != db.corner_tiles_io.end()) {
        side = corner_it->second;
    } else if (row == 0) {
        side = "T";
    } else if (row == static_cast<int64_t>(db.rows()) - 1) {
        side = "B";
    } else if (col == 0) {
        side = "L";
    } else if (col == static_cast<int64_t>(db.cols()) - 1) {
        side = "R";
    } else {
        return "";
    }

    int64_t num;
    if (side == "T" || side == "B") {
        num = col + 1;
    } else {
        num = row + 1;
    }
    return "IO" + side + std::to_string(num) + idx;
}

void set_iob_default_fuses(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device)
{
    using namespace attrids;

    bool is_gw5 = (device == "GW5A-25A" || device == "GW5AST-138C");

    // Step 1: Determine used banks and their IO standards from placed IOBs
    struct BankInfo {
        std::string iostd;
        std::set<std::string> used_bels;
    };
    std::map<int64_t, BankInfo> banks;

    auto bels = get_bels(netlist);
    for (const auto& bel : bels) {
        if (bel.type != "IBUF" && bel.type != "OBUF" &&
            bel.type != "TBUF" && bel.type != "IOBUF")
            continue;

        int64_t row = bel.row - 1;
        int64_t col = bel.col - 1;
        std::string pin_name = rc_to_pin_name(db, row, col, bel.num);
        if (pin_name.empty()) continue;

        auto bank_it = db.pin_bank.find(pin_name);
        if (bank_it == db.pin_bank.end()) continue;
        int64_t bank = bank_it->second;

        auto& bi = banks[bank];
        bi.used_bels.insert(pin_name);

        // Determine IO standard from attributes
        std::string iostd = "LVCMOS18";
        for (const auto& [flag, val] : bel.attributes) {
            if (!flag.empty() && flag[0] == '&') {
                size_t eq_pos = flag.find('=');
                if (eq_pos != std::string::npos) {
                    std::string attr_name = flag.substr(1, eq_pos - 1);
                    if (attr_name == "IO_TYPE") {
                        iostd = get_iostd_alias(flag.substr(eq_pos + 1));
                    }
                }
            }
        }
        for (const auto& [k, v] : bel.parameters) {
            if (k == "IO_TYPE") {
                iostd = get_iostd_alias(v);
            }
        }

        // Output IOBs determine bank IO standard
        if (bel.type == "OBUF" || bel.type == "IOBUF" || bel.type == "TBUF") {
            if (bi.iostd.empty()) {
                bi.iostd = iostd;
            }
        }
    }

    // For banks with IOBs but no output IOBs setting IO standard, use default
    for (auto& [bank, bi] : banks) {
        if (bi.iostd.empty()) {
            bi.iostd = is_gw5 ? "LVCMOS33" : "LVCMOS12";
        }
    }


    // Step 2: Set bank-level fuses for used banks
    auto bt = db.bank_tiles();
    for (const auto& [bank, bi] : banks) {
        auto bt_it = bt.find(bank);
        if (bt_it == bt.end()) continue;
        auto [brow, bcol] = bt_it->second;
        const auto& tiledata = db.get_tile(brow, bcol);

        std::set<int64_t> bank_attrs;
        auto vcc_it = vcc_ios.find(bi.iostd);
        if (vcc_it != vcc_ios.end()) {
            add_attr_val(db, "IOB", bank_attrs,
                         iob_attrids.at("BANK_VCCIO"),
                         iob_attrvals.at(vcc_it->second));
        }
        auto iostd_val_it = iob_attrvals.find(bi.iostd);
        if (iostd_val_it != iob_attrvals.end()) {
            auto io_type_id_it = iob_attrids.find("IO_TYPE");
            if (io_type_id_it != iob_attrids.end()) {
                add_attr_val(db, "IOB", bank_attrs,
                             io_type_id_it->second, iostd_val_it->second);
            }
        }

        auto bits = get_bank_fuses(db, tiledata.ttyp, bank_attrs, "BANK", bank);
        // get_bank_io_fuses: try IOBA, fallback to IOBB
        auto io_bits = get_longval_fuses(db, tiledata.ttyp, bank_attrs, "IOBA");
        if (io_bits.empty()) {
            io_bits = get_longval_fuses(db, tiledata.ttyp, bank_attrs, "IOBB");
        }
        bits.insert(io_bits.begin(), io_bits.end());

        auto& btile = tilemap[{brow, bcol}];
        set_fuses_in_tile(btile, bits);
    }

    // Step 3: Set per-pin default fuses for ALL IOB pins
    for (const auto& [bel_name, cfg] : db.io_cfg) {
        auto pbank_it = db.pin_bank.find(bel_name);
        if (pbank_it == db.pin_bank.end()) {
            if (!cfg.empty()) {
                std::cerr << "Warning: Pin " << bel_name
                          << " has config but no bank" << std::endl;
            }
            continue;
        }
        int64_t bank = pbank_it->second;

        // Determine IO standard for this bank
        std::string io_std;
        auto bi_it = banks.find(bank);
        if (bi_it != banks.end()) {
            io_std = bi_it->second.iostd;
        } else {
            // Unused bank - default IO standard
            io_std = is_gw5 ? "LVCMOS33" : "LVCMOS18";
            banks[bank].iostd = io_std;

            // Set bank-level fuses for this unused bank
            auto bt_it = bt.find(bank);
            if (bt_it != bt.end()) {
                auto [brow, bcol] = bt_it->second;
                const auto& tiledata = db.get_tile(brow, bcol);

                std::set<int64_t> bank_attrs;
                auto vcc_it = vcc_ios.find(io_std);
                if (vcc_it != vcc_ios.end()) {
                    add_attr_val(db, "IOB", bank_attrs,
                                 iob_attrids.at("BANK_VCCIO"),
                                 iob_attrvals.at(vcc_it->second));
                }

                auto bits = get_bank_fuses(db, tiledata.ttyp, bank_attrs, "BANK", bank);
                auto io_bits = get_longval_fuses(db, tiledata.ttyp, bank_attrs, "IOBA");
                if (io_bits.empty()) {
                    io_bits = get_longval_fuses(db, tiledata.ttyp, bank_attrs, "IOBB");
                }
                bits.insert(io_bits.begin(), io_bits.end());

                auto& btile = tilemap[{brow, bcol}];
                set_fuses_in_tile(btile, bits);
            }
        }

        // Parse pin name: IO{side}{num}{idx}
        if (bel_name.size() < 4) continue;
        char side = bel_name[2];
        std::string num_str = bel_name.substr(3, bel_name.size() - 4);
        std::string iob_idx(1, bel_name.back());

        int num;
        try {
            num = std::stoi(num_str);
        } catch (...) {
            continue;
        }

        int64_t row, col;
        if (side == 'T') {
            row = 0;
            col = num - 1;
        } else if (side == 'B') {
            row = static_cast<int64_t>(db.rows()) - 1;
            col = num - 1;
        } else if (side == 'L') {
            row = num - 1;
            col = 0;
        } else if (side == 'R') {
            row = num - 1;
            col = static_cast<int64_t>(db.cols()) - 1;
        } else {
            continue;
        }

        if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
            col < 0 || col >= static_cast<int64_t>(db.cols()))
            continue;

        const auto& tiledata = db.get_tile(row, col);
        if (tiledata.bels.find("IOB" + iob_idx) == tiledata.bels.end())
            continue;

        // Build attrs: IO_TYPE + BANK_VCCIO
        std::set<int64_t> iob_attrs;
        auto io_type_attr_it = iob_attrids.find("IO_TYPE");
        auto io_type_val_it = iob_attrvals.find(io_std);
        if (io_type_attr_it != iob_attrids.end() && io_type_val_it != iob_attrvals.end()) {
            add_attr_val(db, "IOB", iob_attrs,
                         io_type_attr_it->second, io_type_val_it->second);
        }
        auto vcc_it = vcc_ios.find(io_std);
        if (vcc_it != vcc_ios.end()) {
            auto vccio_attr_it = iob_attrids.find("BANK_VCCIO");
            auto vccio_val_it = iob_attrvals.find(vcc_it->second);
            if (vccio_attr_it != iob_attrids.end() && vccio_val_it != iob_attrvals.end()) {
                add_attr_val(db, "IOB", iob_attrs,
                             vccio_attr_it->second, vccio_val_it->second);
            }
        }

        // GW5A devices may need fuse_cell_offset
        if (!is_gw5) {
            auto bits = get_longval_fuses(db, tiledata.ttyp, iob_attrs, "IOB" + iob_idx);
            auto& tile = tilemap[{row, col}];
            set_fuses_in_tile(tile, bits);
        } else {
            int64_t fuse_row = row, fuse_col = col;
            int64_t fuse_ttyp = tiledata.ttyp;
            auto iob_bel_it = tiledata.bels.find("IOB" + iob_idx);
            if (iob_bel_it != tiledata.bels.end() && iob_bel_it->second.fuse_cell_offset) {
                fuse_row += iob_bel_it->second.fuse_cell_offset->first;
                fuse_col += iob_bel_it->second.fuse_cell_offset->second;
                fuse_ttyp = db.get_ttyp(fuse_row, fuse_col);
            }
            // GW5A special cases
            if (row == 2 && col == 91 && iob_idx == "B") {
                iob_idx = "A";
            } else if (row == 3 && col == 91) {
                continue;
            }
            auto bits = get_longval_fuses(db, fuse_ttyp, iob_attrs, "IOB" + iob_idx);
            auto& tile = tilemap[{fuse_row, fuse_col}];
            set_fuses_in_tile(tile, bits);
        }
    }
}

// ============================================================================
// PLL constants and helpers
// ============================================================================

// Permitted frequency ranges: {max_pfd, max_clkout, min_clkout, max_vco, min_vco}
static const std::map<std::string, std::array<double, 5>> permitted_freqs = {
    {"GW1N-1",   {400, 450, 3.125, 900, 400}},
    {"GW1NZ-1",  {400, 400, 3.125, 800, 400}},
    {"GW1N-4",   {400, 500, 3.125, 1000, 400}},
    {"GW1NS-4",  {400, 600, 4.6875, 1200, 400}},
    {"GW1N-9",   {400, 500, 3.125, 1000, 400}},
    {"GW1N-9C",  {400, 600, 3.125, 1200, 400}},
    {"GW1NS-2",  {400, 500, 3.125, 1200, 400}},
    {"GW2A-18",  {500, 625, 3.90625, 1250, 500}},
    {"GW2A-18C", {500, 625, 3.90625, 1250, 500}},
    {"GW5A-25A", {800, 1600, 6.25, 1600, 800}},
};

// Frequency-resistor table
static const std::vector<std::vector<std::pair<double, double>>> freq_R = {
    {{2.6, 65100.0}, {3.87, 43800.0}, {7.53, 22250.0}, {14.35, 11800.0}, {28.51, 5940.0}, {57.01, 2970.0}, {114.41, 1480}, {206.34, 820.0}},
    {{2.4, 69410.0}, {3.53, 47150.0}, {6.82, 24430.0}, {12.93, 12880.0}, {25.7, 6480.0}, {51.4, 3240.0}, {102.81, 1620}, {187.13, 890.0}},
    {{3.24, 72300}, {4.79, 48900}, {9.22, 25400}, {17.09, 13700}, {34.08, 6870}, {68.05, 3440}, {136.1, 1720}, {270.95, 864}},
};

// Calculate PLL pump parameters
static std::tuple<int64_t, int64_t, int64_t> calc_pll_pump(double fref, double fvco, const std::string& device) {
    int64_t fclkin_idx = static_cast<int64_t>((fref - 1) / 30);
    if ((fclkin_idx == 13 && fref <= 395) || (fclkin_idx == 14 && fref <= 430) ||
        (fclkin_idx == 15 && fref <= 465) || fclkin_idx == 16) {
        fclkin_idx = fclkin_idx - 1;
    }

    const std::vector<std::pair<double, double>>* freq_Ri;
    if (device == "GW2A-18" || device == "GW2A-18C") {
        freq_Ri = &freq_R[1];
    } else if (device == "GW5A-25A") {
        freq_Ri = &freq_R[2];
    } else {
        freq_Ri = &freq_R[0];
    }

    // Build r_vals: (R1, r_idx) for entries where fr[0] < fref
    std::vector<std::pair<double, int64_t>> r_vals;
    for (int idx = static_cast<int>(freq_Ri->size()) - 1; idx >= 0; --idx) {
        if ((*freq_Ri)[idx].first < fref) {
            r_vals.push_back({(*freq_Ri)[idx].second, static_cast<int64_t>(freq_Ri->size()) - 1 - idx});
        }
    }

    double K1;
    double C1;
    if (device == "GW2A-18" || device == "GW2A-18C") {
        double K0 = (-28.938 + std::sqrt(837.407844 - (385.07 - fvco) * 0.9892)) / 0.4846;
        K1 = 0.1942 * K0 * K0 - 13.173 * K0 + 518.86;
        C1 = 6.69244e-11;
    } else if (device == "GW5A-25A") {
        K1 = 120;
        if (fvco >= 1400.0) K1 = 240;
        C1 = 4.725e-11;
    } else {
        double K0 = (497.5 - std::sqrt(247506.25 - (2675.4 - fvco) * 78.46)) / 39.23;
        K1 = 4.8714 * K0 * K0 + 6.5257 * K0 + 142.67;
        C1 = 6.69244e-11;
    }
    double Kvco = 1000000.0 * K1;
    double Ndiv = fvco / fref;

    int64_t icp = 50; // default
    int64_t r_idx = 4; // default
    for (const auto& [R1, ri] : r_vals) {
        double Ic = (1.8769 / (R1 * R1 * Kvco * C1)) * 4.0 * Ndiv;
        if (Ic <= 0.00028) {
            icp = static_cast<int64_t>(Ic * 100000.0 + 0.5) * 10;
            r_idx = ri;
            break;
        }
    }

    return {(fclkin_idx + 1) * 16, icp, r_idx};
}

// ============================================================================
// place_pll - Place a PLL BEL
// Uses shortval table "PLL"
// ============================================================================
void place_pll(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    std::string pll_type = bel.type;
    // Normalize type
    if (pll_type == "rPLL" || pll_type == "RPLLA") {
        pll_type = "RPLL";
    }

    // Build internal PLL attributes
    std::map<std::string, std::string> pll_str_attrs;
    std::map<std::string, int64_t> pll_int_attrs;

    // Start with defaults for rPLL/PLLVR
    if (pll_type == "RPLL" || pll_type == "PLLVR") {
        pll_str_attrs["INSEL"] = "CLKIN1";
        pll_str_attrs["FBSEL"] = "CLKFB3";
        pll_str_attrs["PLOCK"] = "ENABLE";
        pll_str_attrs["FLOCK"] = "ENABLE";
        pll_str_attrs["FLTOP"] = "ENABLE";
        pll_int_attrs["GMCMODE"] = 15;
        pll_str_attrs["CLKOUTDIV3"] = "ENABLE";
        pll_str_attrs["CLKOUTDIV"] = "ENABLE";
        pll_str_attrs["CLKOUTPS"] = "ENABLE";
        pll_str_attrs["PDN"] = "ENABLE";
        pll_int_attrs["PASEL"] = 0;
        pll_str_attrs["IRSTEN"] = "DISABLE";
        pll_str_attrs["SRSTEN"] = "DISABLE";
        pll_str_attrs["PWDEN"] = "ENABLE";
        pll_str_attrs["RSTEN"] = "ENABLE";
        pll_int_attrs["FLDCOUNT"] = 16;
        pll_int_attrs["GMCGAIN"] = 0;
        pll_str_attrs["LPR"] = "R4";
        pll_int_attrs["ICPSEL"] = 50;

        if (pll_type == "PLLVR") {
            // Determine index: col != 28 -> idx=1, else idx=0
            int idx = (col != 28) ? 1 : 0;
            std::string vcc_attr = (idx == 0) ? "PLLVCC0" : "PLLVCC1";
            pll_str_attrs[vcc_attr] = "ENABLE";
        }
    } else if (pll_type == "PLLA") {
        // PLLA defaults
        pll_str_attrs["A_RESET_EN"] = "TRUE";
        pll_str_attrs["PWDEN"] = "ENABLE";
        pll_str_attrs["PDN"] = "ENABLE";
        pll_str_attrs["PLOCK"] = "ENABLE";
        pll_str_attrs["FLOCK"] = "ENABLE";
        pll_str_attrs["FLTOP"] = "ENABLE";
        pll_int_attrs["A_GMC_SEL"] = 15;
        pll_str_attrs["A_CLKIN_SEL"] = "CLKIN0";
        pll_int_attrs["FLDCOUNT"] = 32;
        pll_str_attrs["A_VR_EN"] = "DISABLE";
        pll_str_attrs["A_DYN_DPA_EN"] = "FALSE";
        pll_str_attrs["A_RESET_I_EN"] = "FALSE";
        pll_str_attrs["A_RESET_O_EN"] = "FALSE";
        pll_str_attrs["A_DYN_ICP_SEL"] = "FALSE";
        pll_str_attrs["A_DYN_LPF_SEL"] = "FALSE";
        pll_str_attrs["A_SSC_EN"] = "FALSE";
        pll_int_attrs["A_CLKFBOUT_PE_COARSE"] = 0;
        pll_int_attrs["A_CLKFBOUT_PE_FINE"] = 0;
    }

    // Parse parameters from cell
    double fclkin = 100.0;
    int64_t idiv = 1;
    int64_t fbdiv = 1;
    int64_t odiv = 8;

    // Get parameters from bel
    auto params = bel.parameters;

    for (const auto& [attr, val] : params) {
        std::string ua = to_upper(attr);
        std::string uv = to_upper(val);

        if (ua == "FCLKIN") {
            try { fclkin = std::stod(val); } catch (...) {}
            continue;
        }
        if (ua == "IDIV_SEL") {
            idiv = 1 + parse_binary(val);
            pll_int_attrs["IDIV"] = idiv;
            continue;
        }
        if (ua == "A_IDIV_SEL") {
            idiv = parse_binary(val);
            pll_int_attrs["A_IDIV_SEL"] = idiv;
            continue;
        }
        if (ua == "FBDIV_SEL") {
            fbdiv = 1 + parse_binary(val);
            pll_int_attrs["FDIV"] = fbdiv;
            continue;
        }
        if (ua == "A_FBDIV_SEL") {
            fbdiv = parse_binary(val);
            pll_int_attrs["A_FBDIV_SEL"] = fbdiv;
            continue;
        }
        if (ua == "ODIV_SEL") {
            odiv = parse_binary(val);
            pll_int_attrs["ODIV"] = odiv;
            continue;
        }
        if (ua == "DYN_SDIV_SEL") {
            pll_int_attrs["SDIV"] = parse_binary(val);
            continue;
        }
        if (ua == "DYN_IDIV_SEL") {
            if (uv == "TRUE") pll_str_attrs["IDIVSEL"] = "DYN";
            continue;
        }
        if (ua == "DYN_FBDIV_SEL") {
            if (uv == "TRUE") pll_str_attrs["FDIVSEL"] = "DYN";
            continue;
        }
        if (ua == "DYN_ODIV_SEL") {
            if (uv == "TRUE") pll_str_attrs["ODIVSEL"] = "DYN";
            continue;
        }
        if (ua == "CLKOUT_BYPASS") {
            if (uv == "TRUE") pll_str_attrs["BYPCK"] = "BYPASS";
            continue;
        }
        if (ua == "CLKOUTP_BYPASS") {
            if (uv == "TRUE") pll_str_attrs["BYPCKPS"] = "BYPASS";
            continue;
        }
        if (ua == "CLKOUTD_BYPASS") {
            if (uv == "TRUE") pll_str_attrs["BYPCKDIV"] = "BYPASS";
            continue;
        }
        if (ua == "CLKOUTD_SRC") {
            if (uv == "CLKOUTP") pll_str_attrs["CLKOUTDIVSEL"] = "CLKOUTPS";
            continue;
        }
        if (ua == "CLKOUTD3_SRC") {
            if (uv == "CLKOUTP") pll_str_attrs["CLKOUTDIV3SEL"] = "CLKOUTPS";
            continue;
        }
        if (ua == "CLKFB_SEL" || ua == "A_CLKFB_SEL") {
            if (uv == "INTERNAL") {
                if (ua == "CLKFB_SEL") {
                    // default FBSEL = CLKFB3 already set
                } else {
                    pll_str_attrs["A_CLKFB_SEL"] = "CLKFB2";
                }
            }
            continue;
        }
        if (ua == "DYN_DA_EN") {
            if (uv == "TRUE") {
                pll_str_attrs["DPSEL"] = "DYN";
                pll_int_attrs["DUTY"] = 0;
                pll_int_attrs["PHASE"] = 0;
                pll_str_attrs["PASEL"] = "DISABLE";
                int64_t tmp_val = parse_binary(get_param(params, "CLKOUT_DLY_STEP", "0")) * 50;
                pll_int_attrs["OPDLY"] = tmp_val;
                tmp_val = parse_binary(get_param(params, "CLKOUTP_DLY_STEP", "0")) * 50;
                pll_int_attrs["OSDLY"] = tmp_val;
            } else {
                pll_str_attrs["OSDLY"] = "DISABLE";
                pll_str_attrs["OPDLY"] = "DISABLE";
                std::string psda_str = get_param(params, "PSDA_SEL", "0000");
                int64_t phase_val = parse_binary(psda_str);
                pll_int_attrs["PHASE"] = phase_val;
                std::string duty_str = get_param(params, "DUTYDA_SEL", "1000");
                int64_t duty_val = parse_binary(duty_str);
                if ((phase_val + duty_val) < 16) {
                    duty_val = phase_val + duty_val;
                } else {
                    duty_val = phase_val + duty_val - 16;
                }
                pll_int_attrs["DUTY"] = duty_val;
            }
            continue;
        }

        // Handle A_ODIV*_SEL, A_MDIV_SEL, A_MDIV_FRAC_SEL, etc.
        if (ua.find("A_ODIV") != std::string::npos && ua.find("_SEL") != std::string::npos) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
        if (ua == "A_MDIV_SEL") {
            pll_int_attrs["A_MDIV_SEL"] = parse_binary(val);
            continue;
        }
        if (ua == "A_MDIV_FRAC_SEL") {
            pll_int_attrs["A_MDIV_FRAC_SEL"] = parse_binary(val);
            continue;
        }
        if (ua.find("A_CLKOUT") != std::string::npos && ua.find("_EN") != std::string::npos) {
            pll_str_attrs[ua] = val;
            continue;
        }
        if (ua.find("A_DYN_PE") != std::string::npos && ua.find("SEL") != std::string::npos) {
            pll_str_attrs[ua] = val;
            continue;
        }
        if (ua.find("A_DE") != std::string::npos && ua.find("_EN") != std::string::npos) {
            pll_str_attrs[ua] = val;
            continue;
        }
        if (ua.find("A_CLKOUT") != std::string::npos && ua.find("DT_DIR") != std::string::npos) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
        if (ua.find("A_CLKOUT") != std::string::npos && ua.find("DT_STEP") != std::string::npos) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
        if (ua.find("A_CLKOUT") != std::string::npos && ua.find("PE_COARSE") != std::string::npos) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
        if (ua.find("A_CLKOUT") != std::string::npos && ua.find("PE_FINE") != std::string::npos) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
        if (ua.find("A_CLK") != std::string::npos && (ua.find("IN_SEL") != std::string::npos || ua.find("OUT_SEL") != std::string::npos)) {
            pll_int_attrs[ua] = parse_binary(val);
            continue;
        }
    }

    // Calculate pump parameters for non-PLLA types
    if (pll_type != "PLLA") {
        if (device == "GW5A-25A") {
            double Fpfd = fclkin / idiv;
            double Fclkfb = Fpfd * fbdiv;
            double Fvco = Fclkfb * pll_int_attrs["A_MDIV_SEL"];
            auto [fclkin_idx, icp, r_idx] = calc_pll_pump(Fpfd, Fvco, device);
            pll_int_attrs["KVCO"] = fclkin_idx / 16;
            if (Fvco >= 1400.0) {
                fclkin_idx += 1;
            }
            pll_int_attrs["A_ICP_SEL"] = icp;
            pll_str_attrs["A_LPF_RES_SEL"] = "R" + std::to_string(r_idx);
            pll_int_attrs["FLDCOUNT"] = fclkin_idx;
        } else {
            double fref = fclkin / idiv;
            double fvco = (odiv * fbdiv * fclkin) / idiv;
            auto [fclkin_idx, icp, r_idx] = calc_pll_pump(fref, fvco, device);
            pll_int_attrs["ICPSEL"] = icp;
            pll_str_attrs["LPR"] = "R" + std::to_string(r_idx);
            pll_int_attrs["FLDCOUNT"] = fclkin_idx;
        }
    }

    // Build final attribute set
    // Pre-seed with all 16 default rows with value 0
    std::set<int64_t> fin_attrs;
    for (int i = 0; i < 16; ++i) {
        add_attr_val(db, "PLL", fin_attrs, i, 0);
    }

    // Add string attributes
    for (const auto& [attr, val] : pll_str_attrs) {
        auto attr_it = pll_attrids.find(attr);
        if (attr_it == pll_attrids.end()) continue;
        auto val_it = pll_attrvals.find(val);
        if (val_it == pll_attrvals.end()) continue;
        add_attr_val(db, "PLL", fin_attrs, attr_it->second, val_it->second);
    }

    // Add integer attributes
    for (const auto& [attr, val] : pll_int_attrs) {
        auto attr_it = pll_attrids.find(attr);
        if (attr_it == pll_attrids.end()) continue;
        add_attr_val(db, "PLL", fin_attrs, attr_it->second, val);
    }

    // Get fuses
    std::set<Coord> fuses;
    auto ttyp_sv = db.shortval.find(ttyp);
    if (ttyp_sv != db.shortval.end() && ttyp_sv->second.find("PLL") != ttyp_sv->second.end()) {
        fuses = get_shortval_fuses(db, ttyp, fin_attrs, "PLL");
    }

    // Set fuses
    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// BSRAM constants
// ============================================================================

static const std::map<int64_t, std::string> bsram_bit_widths = {
    {1, "1"}, {2, "2"}, {4, "4"}, {8, "9"}, {9, "9"}, {16, "16"}, {18, "16"}, {32, "X36"}, {36, "X36"},
};

// ============================================================================
// place_bsram - Place a BSRAM BEL
// Uses shortval table "BSRAM_{typ}"
// ============================================================================
void place_bsram(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    std::string typ = bel.type;  // DP, SDP, SP, ROM
    std::map<std::string, std::string> bsram_attrs;
    bsram_attrs["MODE"] = "ENABLE";
    bsram_attrs["GSR"] = "DISABLE";

    auto params = bel.parameters;

    // ROM special handling
    if (typ == "ROM") {
        bsram_attrs["CEMUX_CEA"] = "INV";
        bsram_attrs[typ + "A_BEHB"] = "DISABLE";
        bsram_attrs[typ + "A_BELB"] = "DISABLE";
        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
        bsram_attrs[typ + "B_BELB"] = "DISABLE";
    }

    for (const auto& [parm, raw_val] : params) {
        std::string uparm = to_upper(parm);

        if (uparm == "BIT_WIDTH") {
            int64_t val = parse_binary(raw_val);
            auto bw_it = bsram_bit_widths.find(val);
            if (bw_it != bsram_bit_widths.end()) {
                if (typ != "ROM") {
                    // Handle byte enable for SP
                    if (val == 16 || val == 18) {
                        // Check if byte enable signals are constant
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0_it = bel.cell->port_connections.find("AD0");
                            auto ad1_it = bel.cell->port_connections.find("AD1");
                            if (ad0_it != bel.cell->port_connections.end() && !ad0_it->second.empty() &&
                                ad1_it != bel.cell->port_connections.end() && !ad1_it->second.empty()) {
                                constant_be = is_const_net(ad0_it->second[0]) && is_const_net(ad1_it->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "A_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "A_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "A_BELB"] = "DISABLE";
                        }
                        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "B_BELB"] = "DISABLE";
                    } else if (val == 32 || val == 36) {
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0 = bel.cell->port_connections.find("AD0");
                            auto ad1 = bel.cell->port_connections.find("AD1");
                            auto ad2 = bel.cell->port_connections.find("AD2");
                            auto ad3 = bel.cell->port_connections.find("AD3");
                            if (ad0 != bel.cell->port_connections.end() && !ad0->second.empty() &&
                                ad1 != bel.cell->port_connections.end() && !ad1->second.empty() &&
                                ad2 != bel.cell->port_connections.end() && !ad2->second.empty() &&
                                ad3 != bel.cell->port_connections.end() && !ad3->second.empty()) {
                                constant_be = is_const_net(ad0->second[0]) && is_const_net(ad1->second[0]) &&
                                              is_const_net(ad2->second[0]) && is_const_net(ad3->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "A_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "A_BELB"] = "ENABLE";
                            bsram_attrs[typ + "B_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "B_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "A_BELB"] = "DISABLE";
                            bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "B_BELB"] = "DISABLE";
                        }
                    } else {
                        // 1, 2, 4, 8, 9
                        bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "A_BELB"] = "DISABLE";
                        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "B_BELB"] = "DISABLE";
                    }
                }
                if (val != 32 && val != 36) {
                    bsram_attrs[typ + "A_DATA_WIDTH"] = bw_it->second;
                    bsram_attrs[typ + "B_DATA_WIDTH"] = bw_it->second;
                } else if (typ != "SP") {
                    bsram_attrs["DBLWA"] = bw_it->second;
                    bsram_attrs["DBLWB"] = bw_it->second;
                }
            }
        } else if (uparm == "BIT_WIDTH_0") {
            int64_t val = parse_binary(raw_val);
            auto bw_it = bsram_bit_widths.find(val);
            if (bw_it != bsram_bit_widths.end()) {
                if (val != 32 && val != 36) {
                    bsram_attrs[typ + "A_DATA_WIDTH"] = bw_it->second;
                } else {
                    bsram_attrs["DBLWA"] = bw_it->second;
                }
                // Byte enable for port A
                if (val == 16 || val == 18) {
                    if (typ == "SDP") {
                        // SDP uses ADA0, ADA1
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0 = bel.cell->port_connections.find("ADA0");
                            auto ad1 = bel.cell->port_connections.find("ADA1");
                            if (ad0 != bel.cell->port_connections.end() && !ad0->second.empty() &&
                                ad1 != bel.cell->port_connections.end() && !ad1->second.empty()) {
                                constant_be = is_const_net(ad0->second[0]) && is_const_net(ad1->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "A_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "A_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "A_BELB"] = "DISABLE";
                        }
                        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "B_BELB"] = "DISABLE";
                    } else if (typ == "DP") {
                        // DP port A uses ADA0, ADA1
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0 = bel.cell->port_connections.find("ADA0");
                            auto ad1 = bel.cell->port_connections.find("ADA1");
                            if (ad0 != bel.cell->port_connections.end() && !ad0->second.empty() &&
                                ad1 != bel.cell->port_connections.end() && !ad1->second.empty()) {
                                constant_be = is_const_net(ad0->second[0]) && is_const_net(ad1->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "A_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "A_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "A_BELB"] = "DISABLE";
                        }
                    }
                } else if (val == 32 || val == 36) {
                    if (typ == "SDP") {
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0 = bel.cell->port_connections.find("ADA0");
                            auto ad1 = bel.cell->port_connections.find("ADA1");
                            auto ad2 = bel.cell->port_connections.find("ADA2");
                            auto ad3 = bel.cell->port_connections.find("ADA3");
                            if (ad0 != bel.cell->port_connections.end() && !ad0->second.empty() &&
                                ad1 != bel.cell->port_connections.end() && !ad1->second.empty() &&
                                ad2 != bel.cell->port_connections.end() && !ad2->second.empty() &&
                                ad3 != bel.cell->port_connections.end() && !ad3->second.empty()) {
                                constant_be = is_const_net(ad0->second[0]) && is_const_net(ad1->second[0]) &&
                                              is_const_net(ad2->second[0]) && is_const_net(ad3->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "A_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "A_BELB"] = "ENABLE";
                            bsram_attrs[typ + "B_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "B_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "A_BELB"] = "DISABLE";
                            bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "B_BELB"] = "DISABLE";
                        }
                    }
                } else {
                    // 1, 2, 4, 8, 9
                    if (typ == "SDP") {
                        bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "A_BELB"] = "DISABLE";
                        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "B_BELB"] = "DISABLE";
                    } else if (typ == "DP") {
                        bsram_attrs[typ + "A_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "A_BELB"] = "DISABLE";
                    }
                }
            }
        } else if (uparm == "BIT_WIDTH_1") {
            int64_t val = parse_binary(raw_val);
            auto bw_it = bsram_bit_widths.find(val);
            if (bw_it != bsram_bit_widths.end()) {
                if (val != 32 && val != 36) {
                    bsram_attrs[typ + "B_DATA_WIDTH"] = bw_it->second;
                } else {
                    bsram_attrs["DBLWB"] = bw_it->second;
                }
                // Byte enable for port B (DP only)
                if (typ == "DP") {
                    if (val == 16 || val == 18) {
                        bool constant_be = true;
                        if (bel.cell) {
                            auto ad0 = bel.cell->port_connections.find("ADB0");
                            auto ad1 = bel.cell->port_connections.find("ADB1");
                            if (ad0 != bel.cell->port_connections.end() && !ad0->second.empty() &&
                                ad1 != bel.cell->port_connections.end() && !ad1->second.empty()) {
                                constant_be = is_const_net(ad0->second[0]) && is_const_net(ad1->second[0]);
                            }
                        }
                        if (constant_be) {
                            bsram_attrs[typ + "B_BEHB"] = "ENABLE";
                            bsram_attrs[typ + "B_BELB"] = "ENABLE";
                        } else {
                            bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                            bsram_attrs[typ + "B_BELB"] = "DISABLE";
                        }
                    } else {
                        bsram_attrs[typ + "B_BEHB"] = "DISABLE";
                        bsram_attrs[typ + "B_BELB"] = "DISABLE";
                    }
                }
            }
        } else if (uparm == "BLK_SEL") {
            for (int i = 0; i < 3; ++i) {
                int idx = static_cast<int>(raw_val.size()) - 1 - i;
                if (idx >= 0 && raw_val[idx] == '0') {
                    bsram_attrs["CSA_" + std::to_string(i)] = "SET";
                    bsram_attrs["CSB_" + std::to_string(i)] = "SET";
                }
            }
        } else if (uparm == "BLK_SEL_0") {
            for (int i = 0; i < 3; ++i) {
                int idx = static_cast<int>(raw_val.size()) - 1 - i;
                if (idx >= 0 && raw_val[idx] == '0') {
                    bsram_attrs["CSA_" + std::to_string(i)] = "SET";
                }
            }
        } else if (uparm == "BLK_SEL_1") {
            for (int i = 0; i < 3; ++i) {
                int idx = static_cast<int>(raw_val.size()) - 1 - i;
                if (idx >= 0 && raw_val[idx] == '0') {
                    bsram_attrs["CSB_" + std::to_string(i)] = "SET";
                }
            }
        } else if (uparm == "READ_MODE0") {
            if (parse_binary(raw_val) == 1) {
                bsram_attrs[typ + "A_REGMODE"] = "OUTREG";
            }
        } else if (uparm == "READ_MODE1") {
            if (parse_binary(raw_val) == 1) {
                bsram_attrs[typ + "B_REGMODE"] = "OUTREG";
            }
        } else if (uparm == "READ_MODE") {
            if (parse_binary(raw_val) == 1) {
                bsram_attrs[typ + "A_REGMODE"] = "OUTREG";
                bsram_attrs[typ + "B_REGMODE"] = "OUTREG";
            }
        } else if (uparm == "RESET_MODE") {
            if (to_upper(raw_val) == "ASYNC") {
                bsram_attrs["OUTREG_ASYNC"] = "RESET";
            }
        } else if (uparm == "WRITE_MODE0") {
            int64_t wm = parse_binary(raw_val);
            if (wm == 1) bsram_attrs[typ + "A_MODE"] = "WT";
            else if (wm == 2) bsram_attrs[typ + "A_MODE"] = "RBW";
        } else if (uparm == "WRITE_MODE1") {
            int64_t wm = parse_binary(raw_val);
            if (wm == 1) bsram_attrs[typ + "B_MODE"] = "WT";
            else if (wm == 2) bsram_attrs[typ + "B_MODE"] = "RBW";
        } else if (uparm == "WRITE_MODE") {
            int64_t wm = parse_binary(raw_val);
            if (wm == 1) {
                bsram_attrs[typ + "A_MODE"] = "WT";
                bsram_attrs[typ + "B_MODE"] = "WT";
            } else if (wm == 2) {
                bsram_attrs[typ + "A_MODE"] = "RBW";
                bsram_attrs[typ + "B_MODE"] = "RBW";
            }
        }
    }

    // Build final attribute set
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, val] : bsram_attrs) {
        auto attr_it = bsram_attrids.find(attr);
        if (attr_it == bsram_attrids.end()) continue;
        auto val_it = bsram_attrvals.find(val);
        if (val_it == bsram_attrvals.end()) continue;
        add_attr_val(db, "BSRAM", fin_attrs, attr_it->second, val_it->second);
    }

    // Get fuses from shortval table "BSRAM_{typ}"
    std::string table_name = "BSRAM_" + typ;
    std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, table_name);

    // Set fuses
    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// place_dsp - Place a DSP BEL
// Uses shortval table "DSP{mac}"
// ============================================================================
void place_dsp(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    std::string typ = bel.type;
    std::string num = bel.num;

    // For compound types, the num format from nextpnr is different
    // MULTADDALU18X18, MULTALU36X18, MULTALU18X18, ALU54D use num[-1]+num[-1]
    if (typ == "MULTADDALU18X18" || typ == "MULTALU36X18" || typ == "MULTALU18X18" || typ == "ALU54D") {
        if (!num.empty()) {
            char last = num.back();
            num = std::string(1, last) + std::string(1, last);
        }
    }

    // Parse mac and idx from num (format: "XY" where X=mac, Y=idx)
    int mac = 0;
    int idx = 0;
    if (num.size() >= 2) {
        mac = num[0] - '0';
        idx = num[1] - '0';
    } else if (num.size() == 1) {
        mac = num[0] - '0';
    }
    int even_odd = idx & 1;
    int pair_idx = idx / 2;

    std::map<std::string, std::string> dsp_str_attrs;
    std::map<std::string, int64_t> dsp_int_attrs;

    // M9MODE_EN for PADD9 and MULT9X9
    if (typ == "PADD9" || typ == "MULT9X9") {
        dsp_str_attrs["M9MODE_EN"] = "ENABLE";
    }

    // For a generic DSP implementation, we process the cell's parameters
    // and convert them to DSP attribute IDs
    auto params = bel.parameters;

    // Process common DSP parameters
    for (const auto& [parm, val] : params) {
        std::string uparm = to_upper(parm);
        // Many DSP params map directly to DSP attrids
        if (dsp_attrids.find(uparm) != dsp_attrids.end()) {
            // Check if value is a string attr or integer
            auto sval_it = dsp_attrvals.find(to_upper(val));
            if (sval_it != dsp_attrvals.end()) {
                dsp_str_attrs[uparm] = to_upper(val);
            } else {
                // Try parsing as integer
                try {
                    int64_t ival = parse_binary(val);
                    dsp_int_attrs[uparm] = ival;
                } catch (...) {}
            }
        }
    }

    // Also process attributes
    for (const auto& [attr, val] : bel.attributes) {
        std::string ua = to_upper(attr);
        if (dsp_attrids.find(ua) != dsp_attrids.end()) {
            auto sval_it = dsp_attrvals.find(to_upper(val));
            if (sval_it != dsp_attrvals.end()) {
                dsp_str_attrs[ua] = to_upper(val);
            }
        }
    }

    (void)even_odd;
    (void)pair_idx;

    // Build final attribute set
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, val] : dsp_str_attrs) {
        auto attr_it = dsp_attrids.find(attr);
        if (attr_it == dsp_attrids.end()) continue;
        auto val_it = dsp_attrvals.find(val);
        if (val_it == dsp_attrvals.end()) continue;
        add_attr_val(db, "DSP", fin_attrs, attr_it->second, val_it->second);
    }
    for (const auto& [attr, val] : dsp_int_attrs) {
        auto attr_it = dsp_attrids.find(attr);
        if (attr_it == dsp_attrids.end()) continue;
        add_attr_val(db, "DSP", fin_attrs, attr_it->second, val);
    }

    // Get fuses - table name is "DSP{mac}" where mac is the second-to-last char of num
    std::string table_name = "DSP" + std::to_string(mac);
    auto ttyp_sv = db.shortval.find(ttyp);
    std::set<Coord> fuses;
    if (ttyp_sv != db.shortval.end() && ttyp_sv->second.find(table_name) != ttyp_sv->second.end()) {
        fuses = get_shortval_fuses(db, ttyp, fin_attrs, table_name);
    }

    // Set fuses
    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// IOLOGIC constants and helpers
// ============================================================================

// Default IOLOGIC attributes per type
static const std::map<std::string, std::map<std::string, std::string>> iologic_default_attrs = {
    {"DUMMY", {}},
    {"IOLOGIC", {}},
    {"IOLOGIC_DUMMY", {}},
    {"IOLOGICI_EMPTY", {{"GSREN", "FALSE"}, {"LSREN", "true"}}},
    {"IOLOGICO_EMPTY", {{"GSREN", "FALSE"}, {"LSREN", "true"}}},
    {"ODDR", {{"TXCLK_POL", "0"}}},
    {"ODDRC", {{"TXCLK_POL", "0"}}},
    {"OSER4", {{"GSREN", "FALSE"}, {"LSREN", "true"}, {"TXCLK_POL", "0"}, {"HWL", "false"}}},
    {"OSER8", {{"GSREN", "false"}, {"LSREN", "true"}, {"TXCLK_POL", "0"}, {"HWL", "false"}}},
    {"OSER10", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"OSER16", {{"GSREN", "false"}, {"LSREN", "true"}, {"CLKOMUX", "ENABLE"}}},
    {"OVIDEO", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"IDES4", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"IDES8", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"IDES10", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"IVIDEO", {{"GSREN", "false"}, {"LSREN", "true"}}},
    {"IDDR", {{"CLKIMUX", "ENABLE"}, {"LSRIMUX_0", "0"}, {"LSROMUX_0", "0"}}},
    {"IDDRC", {{"CLKIMUX", "ENABLE"}, {"LSRIMUX_0", "1"}, {"LSROMUX_0", "0"}}},
    {"IDES16", {{"GSREN", "false"}, {"LSREN", "true"}, {"CLKIMUX", "ENABLE"}}},
};

// Apply IOLOGIC attribute modifications (like Python's iologic_mod_attrs)
static void iologic_mod_attrs(std::map<std::string, std::string>& attrs) {
    // Convert all keys to uppercase
    std::map<std::string, std::string> upper_attrs;
    for (auto& [k, v] : attrs) {
        upper_attrs[to_upper(k)] = to_upper(v);
    }
    attrs = upper_attrs;

    // TXCLK_POL -> TSHX
    auto txclk_it = attrs.find("TXCLK_POL");
    if (txclk_it != attrs.end()) {
        if (txclk_it->second == "0") {
            attrs["TSHX"] = "SIG";
        } else {
            attrs["TSHX"] = "INV";
        }
        attrs.erase("TXCLK_POL");
    }

    // HWL -> UPDATE
    auto hwl_it = attrs.find("HWL");
    if (hwl_it != attrs.end()) {
        if (hwl_it->second == "TRUE") {
            attrs["UPDATE"] = "SAME";
        }
        attrs.erase("HWL");
    }

    // GSREN -> GSR
    auto gsren_it = attrs.find("GSREN");
    if (gsren_it != attrs.end()) {
        if (gsren_it->second == "TRUE") {
            attrs["GSR"] = "ENGSR";
        }
        attrs.erase("GSREN");
    }

    // Remove LSREN, Q0_INIT, Q1_INIT
    attrs.erase("LSREN");
    attrs.erase("Q0_INIT");
    attrs.erase("Q1_INIT");
}

// ============================================================================
// place_iologic - Place an IOLOGIC BEL
// Uses shortval table "IOLOGIC{num}"
// ============================================================================
void place_iologic(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    // Determine the IOLOGIC type from attributes
    std::string iologic_type = get_attr(bel.attributes, "IOLOGIC_TYPE", bel.type);
    std::string iologic_fclk = get_attr(bel.attributes, "IOLOGIC_FCLK", "UNKNOWN");

    // Strip trailing I/O from num
    std::string num = bel.num;
    if (!num.empty() && (num.back() == 'I' || num.back() == 'O')) {
        num = num.substr(0, num.size() - 1);
    }

    // Handle IOLOGIC_DUMMY: get FCLK from MAIN_CELL
    // (In C++ we just use the attribute if set)

    // Recode spines for non-simple types
    if (iologic_type != "IDDR" && iologic_type != "IDDRC" &&
        iologic_type != "ODDR" && iologic_type != "ODDRC" &&
        iologic_type != "IOLOGICI_EMPTY" && iologic_type != "IOLOGICO_EMPTY") {
        static const std::map<std::string, std::string> recode_spines = {
            {"UNKNOWN", "UNKNOWN"}, {"HCLK_OUT0", "SPINE10"},
            {"HCLK_OUT1", "SPINE11"}, {"HCLK_OUT2", "SPINE12"},
            {"HCLK_OUT3", "SPINE13"},
        };
        auto rc_it = recode_spines.find(iologic_fclk);
        if (rc_it != recode_spines.end()) {
            iologic_fclk = rc_it->second;
        }
    } else {
        iologic_fclk = "UNKNOWN";
    }

    // Start with default attrs for this type
    auto default_it = iologic_default_attrs.find(iologic_type);
    std::map<std::string, std::string> in_attrs;
    if (default_it != iologic_default_attrs.end()) {
        in_attrs = default_it->second;
    }

    // Merge cell parameters
    for (const auto& [k, v] : bel.parameters) {
        in_attrs[k] = v;
    }

    // Apply modifications
    iologic_mod_attrs(in_attrs);

    // Handle OUTMODE
    auto outmode_it = in_attrs.find("OUTMODE");
    if (outmode_it != in_attrs.end()) {
        if (iologic_type == "IOLOGICO_EMPTY") {
            in_attrs.erase("OUTMODE");
        } else {
            std::string outmode = outmode_it->second;
            if (outmode != "ODDRX1") {
                in_attrs["CLKODDRMUX_WRCLK"] = "ECLK0";
            }
            if (outmode != "ODDRX1" || iologic_type == "ODDRC") {
                in_attrs["LSROMUX_0"] = "1";
            } else {
                in_attrs["LSROMUX_0"] = "0";
            }
            in_attrs["CLKODDRMUX_ECLK"] = "UNKNOWN";
            if (iologic_fclk == "SPINE12" || iologic_fclk == "SPINE13") {
                in_attrs["CLKODDRMUX_ECLK"] = "ECLK1";
            } else if (iologic_fclk == "SPINE10" || iologic_fclk == "SPINE11") {
                in_attrs["CLKODDRMUX_ECLK"] = "ECLK0";
            }
            if (outmode == "ODDRX8" || outmode == "DDRENABLE16") {
                in_attrs["LSROMUX_0"] = "0";
            }
            if (outmode == "DDRENABLE16") {
                in_attrs["OUTMODE"] = "DDRENABLE";
                in_attrs["ISI"] = "ENABLE";
            }
            if (outmode == "DDRENABLE") {
                in_attrs["ISI"] = "ENABLE";
            }
            in_attrs["LSRIMUX_0"] = "0";
            in_attrs["CLKOMUX"] = "ENABLE";
        }
    }

    // Handle INMODE
    auto inmode_it = in_attrs.find("INMODE");
    if (inmode_it != in_attrs.end()) {
        if (iologic_type == "IOLOGICI_EMPTY") {
            in_attrs.erase("INMODE");
        } else if (iologic_type != "IDDR" && iologic_type != "IDDRC") {
            std::string inmode = inmode_it->second;
            in_attrs["CLKOMUX_1"] = "1";
            in_attrs["CLKODDRMUX_ECLK"] = "UNKNOWN";
            if (iologic_fclk == "SPINE12" || iologic_fclk == "SPINE13") {
                in_attrs["CLKIDDRMUX_ECLK"] = "ECLK1";
            } else if (iologic_fclk == "SPINE10" || iologic_fclk == "SPINE11") {
                in_attrs["CLKIDDRMUX_ECLK"] = "ECLK0";
            }
            in_attrs["LSRIMUX_0"] = "1";
            if (inmode == "IDDRX8" || inmode == "DDRENABLE16") {
                in_attrs["LSROMUX_0"] = "0";
            }
            if (inmode == "DDRENABLE16") {
                in_attrs["INMODE"] = "DDRENABLE";
                in_attrs["ISI"] = "ENABLE";
            }
            if (inmode == "DDRENABLE") {
                in_attrs["ISI"] = "ENABLE";
            }
            in_attrs["LSROMUX_0"] = "0";
            in_attrs["CLKIMUX"] = "ENABLE";
        }
    }

    // Handle IODELAY
    auto iodelay_it = bel.attributes.find("IODELAY");
    if (iodelay_it != bel.attributes.end()) {
        if (iodelay_it->second == "IN") {
            in_attrs["INDEL"] = "ENABLE";
        } else {
            in_attrs["OUTDEL"] = "ENABLE";
        }
        in_attrs["CLKOMUX"] = "ENABLE";
        in_attrs["IMARG"] = "ENABLE";
        in_attrs["INDEL_0"] = "ENABLE";
        in_attrs["INDEL_1"] = "ENABLE";

        auto sdly_it = in_attrs.find("C_STATIC_DLY");
        if (sdly_it != in_attrs.end()) {
            std::string dly = sdly_it->second;
            for (int i = 1; i <= 7 && i <= static_cast<int>(dly.size()); ++i) {
                if (dly[dly.size() - i] == '1') {
                    in_attrs["DELAY_DEL" + std::to_string(i - 1)] = "1";
                }
            }
            in_attrs.erase("C_STATIC_DLY");
        }
    }

    // Build final attribute set
    std::set<int64_t> fin_attrs;
    for (const auto& [k, val] : in_attrs) {
        auto attr_it = iologic_attrids.find(k);
        if (attr_it == iologic_attrids.end()) {
            // Skip unknown attributes
            continue;
        }
        auto val_it = iologic_attrvals.find(val);
        if (val_it == iologic_attrvals.end()) {
            continue;
        }
        add_attr_val(db, "IOLOGIC", fin_attrs, attr_it->second, val_it->second);
    }

    // Get fuses from shortval table "IOLOGIC{num}"
    std::string table_name = "IOLOGIC" + num;
    std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, table_name);

    // Set fuses
    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// place_osc - Place an Oscillator BEL
// Uses shortval table "OSC"
// ============================================================================
void place_osc(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    auto& tile = tilemap[{row, col}];

    // Special handling for GW1NZ-1: turn on oscillator
    if (device == "GW1NZ-1") {
        int64_t en_row = static_cast<int64_t>(db.rows()) - 1;
        int64_t en_col = static_cast<int64_t>(db.cols()) - 1;
        auto& en_tile = tilemap[{en_row, en_col}];
        if (23 < static_cast<int64_t>(en_tile.size()) && 63 < static_cast<int64_t>(en_tile[23].size())) {
            en_tile[23][63] = 0;
        }
        if (22 < static_cast<int64_t>(en_tile.size()) && 63 < static_cast<int64_t>(en_tile[22].size())) {
            en_tile[22][63] = 1;
        }
    }

    // Clear powersave fuses first
    {
        std::set<int64_t> clear_attrs;
        add_attr_val(db, "OSC", clear_attrs, osc_attrids.at("POWER_SAVE"), osc_attrvals.at("ENABLE"));
        std::set<Coord> clear_fuses = get_shortval_fuses(db, ttyp, clear_attrs, "OSC");
        clear_fuses_in_tile(tile, clear_fuses);
    }

    // Build OSC attributes from parameters
    std::string typ = bel.type;
    auto params = bel.parameters;

    std::map<std::string, std::string> osc_str_attrs;
    std::map<std::string, int64_t> osc_int_attrs;

    for (const auto& [param, val] : params) {
        std::string uparam = to_upper(param);
        if (uparam == "FREQ_DIV") {
            int64_t fdiv = parse_binary(val);
            if (fdiv % 2 == 1) {
                if (fdiv == 3 && device == "GW5A-25A") {
                    fdiv = 0;
                } else {
                    std::cerr << "Warning: Divisor of " << typ << " must be even, got " << fdiv << std::endl;
                }
            }
            osc_int_attrs["MCLKCIB"] = fdiv;
            osc_str_attrs["MCLKCIB_EN"] = "ENABLE";
        } else if (uparam == "REGULATOR_EN") {
            int64_t reg = parse_binary(val);
            if (reg == 1) {
                osc_str_attrs["OSCREG"] = "ENABLE";
            }
        }
    }

    // Type-specific defaults
    if (typ != "OSCA") {
        osc_str_attrs["NORMAL"] = "ENABLE";
    }
    if (typ != "OSC" && typ != "OSCW") {
        osc_str_attrs["USERPOWER_SAVE"] = "ENABLE";
    }

    // Build final attribute set
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, val] : osc_str_attrs) {
        auto attr_it = osc_attrids.find(attr);
        if (attr_it == osc_attrids.end()) continue;
        auto val_it = osc_attrvals.find(val);
        if (val_it == osc_attrvals.end()) continue;
        add_attr_val(db, "OSC", fin_attrs, attr_it->second, val_it->second);
    }
    for (const auto& [attr, val] : osc_int_attrs) {
        auto attr_it = osc_attrids.find(attr);
        if (attr_it == osc_attrids.end()) continue;
        add_attr_val(db, "OSC", fin_attrs, attr_it->second, val);
    }

    // For GW5A-25A, set fuses in all OSC-related cells
    if (device == "GW5A-25A") {
        for (const auto& [row_col, func_desc] : db.extra_func) {
            // Check if this cell has 'osc' or 'osc_fuses_only' in extra_func
            bool has_osc = false;
            for (const auto& [func_key, func_val] : func_desc) {
                if (func_key == "osc" || func_key == "osc_fuses_only") {
                    has_osc = true;
                    break;
                }
            }
            if (has_osc) {
                int64_t osc_row = row_col.first;
                int64_t osc_col = row_col.second;
                auto& osc_tile = tilemap[{osc_row, osc_col}];
                int64_t osc_ttyp = db.get_ttyp(osc_row, osc_col);
                std::set<Coord> fuses = get_shortval_fuses(db, osc_ttyp, fin_attrs, "OSC");
                set_fuses_in_tile(osc_tile, fuses);
            }
        }
    } else {
        // Normal case: set fuses in the OSC tile
        std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, "OSC");
        set_fuses_in_tile(tile, fuses);
    }
}

// ============================================================================
// place_bufs - Place a BUFS BEL (clock buffer)
// BUFS fuses must be cleared (set to 0) to activate
// ============================================================================
void place_bufs(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    auto& tile = tilemap[{row, col}];

    // BUFS fuses must be reset to 0 to activate
    // The parameters contain 'L' and/or 'R' keys indicating which side to activate
    std::string bufs_name = "BUFS" + bel.num;
    auto bufs_it = tiledata.bels.find(bufs_name);
    if (bufs_it == tiledata.bels.end()) return;

    std::set<Coord> bits2zero;
    for (const auto& [key, val] : bel.parameters) {
        if (key == "L" || key == "R") {
            // Look up the fuses for this flag in the bel's flags map
            // The flags map uses string keys for BUFS
            auto mode_it = bufs_it->second.modes.find(key);
            if (mode_it != bufs_it->second.modes.end()) {
                bits2zero.insert(mode_it->second.begin(), mode_it->second.end());
            }
        }
    }

    clear_fuses_in_tile(tile, bits2zero);
}

// ============================================================================
// place_ram16sdp - Place a RAM16SDP BEL
// Sets all 4 slices to SSRAM mode
// ============================================================================
void place_ram16sdp(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    (void)db;
    (void)tilemap;

    // Set all 4 slices to SSRAM mode
    for (int idx = 0; idx < 4; ++idx) {
        auto& ram_attrs = slice_attrvals[{bel.row, bel.col, idx}];
        ram_attrs["MODE"] = "SSRAM";
    }

    // Slice 2 gets special WRE handling
    auto& ram_attrs2 = slice_attrvals[{bel.row, bel.col, 2}];
    ram_attrs2["LSRONMUX"] = "LSRMUX";
    ram_attrs2["LSR_MUX_LSR"] = "INV";
    ram_attrs2["CLKMUX_1"] = "UNKNOWN";
    ram_attrs2["CLKMUX_CLK"] = "SIG";
}

// ============================================================================
// place_clkdiv - Place a CLKDIV BEL
// Uses shortval table "HCLK"
// ============================================================================
void place_clkdiv(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    // Build HCLK attributes from parameters
    std::set<int64_t> hclk_attrs;

    for (const auto& [param, val] : bel.parameters) {
        auto attr_it = hclk_attrids.find(param);
        if (attr_it == hclk_attrids.end()) continue;
        auto val_it = hclk_attrvals.find(val);
        if (val_it == hclk_attrvals.end()) {
            // Try integer value
            try {
                int64_t ival = parse_binary(val);
                add_attr_val(db, "HCLK", hclk_attrs, attr_it->second, ival);
            } catch (...) {}
            continue;
        }
        add_attr_val(db, "HCLK", hclk_attrs, attr_it->second, val_it->second);
    }

    std::set<Coord> fuses = get_shortval_fuses(db, ttyp, hclk_attrs, "HCLK");

    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);
}

// ============================================================================
// place_dcs - Place a DCS BEL (Dynamic Clock Select)
// ============================================================================
void place_dcs(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // Check if DCS_MODE attribute is set
    if (bel.attributes.find("DCS_MODE") == bel.attributes.end()) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    // Build DCS attributes
    std::set<int64_t> dcs_attrs_set;
    for (const auto& [attr, val] : bel.attributes) {
        auto attr_it = dcs_attrids.find(attr);
        if (attr_it == dcs_attrids.end()) continue;
        auto val_it = dcs_attrvals.find(val);
        if (val_it == dcs_attrvals.end()) continue;
        add_attr_val(db, "DCS", dcs_attrs_set, attr_it->second, val_it->second);
    }

    // For non-GW5A, use longfuses table
    if (device != "GW5A-25A") {
        // The DCS table name depends on the spine quadrant
        // For simplicity, try with the number-based table
        std::string dcs_num = bel.num;
        std::string table_name = db.dcs_prefix + dcs_num;
        std::set<Coord> fuses = get_long_fuses(db, ttyp, dcs_attrs_set, table_name);
        auto& tile = tilemap[{row, col}];
        set_fuses_in_tile(tile, fuses);
    }
}

// ============================================================================
// place_dqce - Place a DQCE BEL
// DQCE is just a control wire (clock pip)
// ============================================================================
void place_dqce(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    // DQCE_PIP attribute specifies the pip to set
    auto pip_it = bel.attributes.find("DQCE_PIP");
    if (pip_it == bel.attributes.end()) return;

    std::string pip = pip_it->second;
    std::regex pipre(R"(X(\d+)Y(\d+)/([\w_]+)/([\w_]+))");
    std::smatch match;
    if (!std::regex_match(pip, match, pipre)) {
        std::cerr << "Warning: Bad DQCE pip " << pip << " at " << bel.name << std::endl;
        return;
    }

    int64_t pip_col = std::stoll(match[1].str());
    int64_t pip_row = std::stoll(match[2].str());
    std::string dest = match[3].str();
    std::string src = match[4].str();

    if (pip_row < 0 || pip_row >= static_cast<int64_t>(db.rows()) ||
        pip_col < 0 || pip_col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    const auto& pip_tiledata = db.get_tile(pip_row, pip_col);
    auto& pip_tile = tilemap[{pip_row, pip_col}];

    auto dest_it = pip_tiledata.clock_pips.find(dest);
    if (dest_it == pip_tiledata.clock_pips.end()) return;
    auto src_it = dest_it->second.find(src);
    if (src_it == dest_it->second.end()) return;

    set_fuses_in_tile(pip_tile, src_it->second);
}

// ============================================================================
// place_dhcen - Place a DHCEN BEL
// DHCEN controls HCLK fuses
// ============================================================================
void place_dhcen(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    (void)db;
    (void)tilemap;

    // Check if DHCEN_USED attribute is set
    if (bel.attributes.find("DHCEN_USED") == bel.attributes.end()) {
        return;
    }

    // DHCEN itself is just a control wire - the actual fuses are set
    // via HCLK configuration. The Python code looks up the corresponding
    // HCLK wire and sets its fuses. For now, this is handled as part of
    // the routing/HCLK configuration.
}

// ============================================================================
// set_slice_fuses - Apply accumulated slice fuses
// ============================================================================
void set_slice_fuses(const Device& db, Tilemap& tilemap) {
    using namespace attrids;

    for (const auto& [pos, attrvals] : slice_attrvals) {
        auto [row, col, slice_idx] = pos;
        int64_t grid_row = row - 1;
        int64_t grid_col = col - 1;

        if (grid_row < 0 || grid_row >= static_cast<int64_t>(db.rows()) ||
            grid_col < 0 || grid_col >= static_cast<int64_t>(db.cols())) {
            continue;
        }

        auto& tile = tilemap[{grid_row, grid_col}];
        int64_t ttyp = db.get_ttyp(grid_row, grid_col);

        // Build final attribute map with defaults
        std::map<std::string, std::string> final_attrs = attrvals;

        // Add default attributes if not set
        if (final_attrs.find("MODE") != final_attrs.end() && final_attrs["MODE"] == "SSRAM") {
            final_attrs["REG0_REGSET"] = "UNKNOWN";
            final_attrs["REG1_REGSET"] = "UNKNOWN";
        } else if (final_attrs.find("REGMODE") == final_attrs.end()) {
            final_attrs["LSRONMUX"] = "0";
            final_attrs["CLKMUX_1"] = "1";
        }
        if (final_attrs.find("REG0_REGSET") == final_attrs.end()) {
            final_attrs["REG0_REGSET"] = "RESET";
        }
        if (final_attrs.find("REG1_REGSET") == final_attrs.end()) {
            final_attrs["REG1_REGSET"] = "RESET";
        }
        if (slice_idx == 0 && final_attrs.find("ALU_CIN_MUX") == final_attrs.end()) {
            final_attrs["ALU_CIN_MUX"] = "ALU_5A_CIN_COUT";
        }

        // Build attribute value set for shortval lookup
        std::set<int64_t> av;

        for (const auto& [attr, val] : final_attrs) {
            // Look up attribute ID
            auto attr_it = cls_attrids.find(attr);
            if (attr_it == cls_attrids.end()) continue;

            // Look up value ID
            auto val_it = cls_attrvals.find(val);
            if (val_it == cls_attrvals.end()) continue;

            // Add to attribute set via logicinfo lookup
            add_attr_val(db, "SLICE", av, attr_it->second, val_it->second);
        }

        // Look up fuses from shortval table for CLS{slice_idx}
        std::string table_name = "CLS" + std::to_string(slice_idx);

        auto ttyp_it = db.shortval.find(ttyp);
        if (ttyp_it != db.shortval.end()) {
            auto table_it = ttyp_it->second.find(table_name);
            if (table_it != ttyp_it->second.end()) {
                // Get fuses matching our attribute set
                std::set<Coord> fuses = get_shortval_fuses(db, ttyp, av, table_name);
                for (const auto& [brow, bcol] : fuses) {
                    if (brow >= 0 && brow < static_cast<int64_t>(tile.size()) &&
                        bcol >= 0 && bcol < static_cast<int64_t>(tile[brow].size())) {
                        tile[brow][bcol] = 1;
                    }
                }
            }
        }
    }
}

} // namespace apycula
