// place.cpp - BEL placement implementation
// Based on apycula/gowin_pack.py place_* functions
#include "place.hpp"
#include "fuses.hpp"
#include "attrids.hpp"
#include <regex>
#include <iostream>

namespace apycula {

// Store slice attributes to be applied at the end
// Key: (row, col, slice_idx), Value: map of attr->val
static std::map<std::tuple<int64_t, int64_t, int64_t>, std::map<std::string, std::string>> slice_attrvals;

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

void place_cells(
    const Device& db,
    const Netlist& netlist,
    Tilemap& tilemap,
    const std::string& device) {

    // Clear slice attributes for fresh run
    slice_attrvals.clear();

    auto bels = get_bels(netlist);

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
                   bel.type.find("OSER") != std::string::npos ||
                   bel.type.find("IDES") != std::string::npos) {
            place_iologic(db, bel, tilemap, device);
        } else if (bel.type.size() >= 3 && bel.type.substr(0, 3) == "OSC") {
            place_osc(db, bel, tilemap, device);
        }
    }

    // Apply slice fuses at the end
    set_slice_fuses(db, tilemap);
}

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

void place_iob(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // IOB placement is complex - for now, basic implementation
    // Full implementation would need bank handling, IO standards, etc.
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // IOB fuses are in longval table - requires more complex handling
    // For now, this is a placeholder
}

void place_pll(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // PLL placement is complex and device-specific
    // For now, this is a placeholder
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // PLL fuses would be looked up from shortval table with PLL attributes
}

void place_bsram(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // BSRAM placement
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // BSRAM fuses would be looked up from shortval table
}

void place_dsp(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // DSP placement
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // DSP fuses would be looked up from shortval table
}

void place_iologic(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // IOLOGIC placement
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // IOLOGIC fuses would be looked up from shortval table
}

void place_osc(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    // Oscillator placement
    (void)tilemap;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (row < 0 || row >= static_cast<int64_t>(db.rows()) ||
        col < 0 || col >= static_cast<int64_t>(db.cols())) {
        return;
    }

    // OSC fuses would be looked up from shortval table
}

// Apply accumulated slice fuses
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
