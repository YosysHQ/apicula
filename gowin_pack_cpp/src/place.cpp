// place.cpp - BEL placement implementation
// Based on apycula/gowin_pack.py place_* functions
#include "place.hpp"
#include "bitstream.hpp"
#include "chipdb.hpp"
#include "fuses.hpp"
#include "attrids.hpp"
#include "utils.hpp"
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

// GND/VCC net bit indices (populated from netlist $PACKER_GND/$PACKER_VCC)
static std::set<int> gnd_net_bits;
static std::set<int> vcc_net_bits;

// ADC IO location tracking (like Python's adc_iolocs global)
static std::map<Coord, std::string> adc_iolocs;  // (row, col) -> bus string

static bool is_const_net(int bit) {
    return gnd_net_bits.count(bit) || vcc_net_bits.count(bit);
}

// Get attribute with default
static std::string get_attr(const std::map<std::string, std::string>& attrs,
                            const std::string& key,
                            const std::string& default_val = "") {
    auto it = attrs.find(key);
    if (it != attrs.end()) return it->second;
    return default_val;
}

// Check if row/col are within the grid bounds
static bool in_bounds(int64_t row, int64_t col, const Device& db) {
    return row >= 0 && row < static_cast<int64_t>(db.rows()) &&
           col >= 0 && col < static_cast<int64_t>(db.cols());
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
    std::regex bel_re(R"(X(\d+)Y(\d+)/(?:GSR|LUT|DFF|IOB|MUX|ALU|ODDR|OSC[ZFHWOA]?|BUF[GS]|RAM16SDP4|RAM16SDP2|RAM16SDP1|PLL|IOLOGIC|CLKDIV2|CLKDIV|BSRAM|ALU|MULTALU18X18|MULTALU36X18|MULTADDALU18X18|MULT36X36|MULT18X18|MULT9X9|PADD18|PADD9|BANDGAP|DQCE|DCS|USERFLASH|EMCU|DHCEN|MIPI_OBUF|MIPI_IBUF|DLLDLY|PINCFG|PLLA|ADC)(\w*))");

    for (const auto& cellname : netlist.cell_order) {
        auto cell_it = netlist.cells.find(cellname);
        if (cell_it == netlist.cells.end()) continue;
        const auto& cell = cell_it->second;
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
    const std::vector<BelInfo>& extra_bels,
    BsramInitMap* bsram_init_map,
    std::vector<Gw5aBsramInfo>* gw5a_bsrams,
    std::map<int, TileBitmap>* extra_slots,
    const PackArgs* args) {

    // Clear slice attributes and ADC IO locations for fresh run
    slice_attrvals.clear();
    adc_iolocs.clear();

    // Populate GND/VCC net bit sets from netlist (matching Python _gnd_net/_vcc_net)
    gnd_net_bits.clear();
    vcc_net_bits.clear();
    {
        auto gnd_it = netlist.nets.find("$PACKER_GND");
        if (gnd_it != netlist.nets.end()) {
            for (int b : gnd_it->second.bits) gnd_net_bits.insert(b);
        }
        auto vcc_it = netlist.nets.find("$PACKER_VCC");
        if (vcc_it != netlist.nets.end()) {
            for (int b : vcc_it->second.bits) vcc_net_bits.insert(b);
        }
    }

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
            // Check for DIFF cells (Python line 3298: if 'DIFF' in parms)
            auto diff_it = bel.parameters.find("DIFF");
            if (diff_it != bel.parameters.end()) {
                // N-pin: skip entirely (Python line 3300-3301)
                if (diff_it->second == "N") continue;
                // P-pin: get DIFF_TYPE mode (Python line 3307)
                auto dt_it = bel.parameters.find("DIFF_TYPE");
                if (dt_it != bel.parameters.end()) {
                    // TLVDS_IBUF_ADC: ADC analog input - skip IOB processing
                    // (Python line 3312-3315)
                    if (dt_it->second == "TLVDS_IBUF_ADC") {
                        int64_t io_col = bel.col - 1;
                        int64_t io_row = bel.row - 1;
                        adc_iolocs[{io_row, io_col}] = "2";
                        continue;
                    }
                }
            }
            place_iob(db, bel, tilemap, device);
        } else if (bel.type == "rPLL" || bel.type == "PLLVR" || bel.type == "PLLA" || bel.type == "RPLLA") {
            place_pll(db, bel, tilemap, device, extra_slots);
        } else if (bel.type == "DP" || bel.type == "SDP" || bel.type == "SP" || bel.type == "ROM") {
            if (is_gw5_family(device) && gw5a_bsrams) {
                // GW5A/GW5AST: collect BSRAM positions for deferred processing
                // Python: bisect.insort(gw5a_bsrams, (col - 1, row - 1, typ, parms, attrs))
                // where col/row are 1-indexed from cell placement
                Gw5aBsramInfo info;
                info.col = bel.col - 1;  // 0-indexed
                info.row = bel.row - 1;  // 0-indexed
                info.typ = bel.type;
                info.params = bel.parameters;
                info.attrs = bel.attributes;
                // Insert sorted (like Python's bisect.insort) - sorts by (col, row)
                auto it = std::lower_bound(gw5a_bsrams->begin(), gw5a_bsrams->end(), info);
                gw5a_bsrams->insert(it, info);
            } else if (bsram_init_map) {
                store_bsram_init_val(db, bel.row - 1, bel.col - 1, bel.type,
                                     bel.parameters, bel.attributes, device,
                                     *bsram_init_map);
            }
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
            place_iologic(db, bel, tilemap, device, netlist);
        } else if (bel.type == "OSC" || bel.type == "OSCZ" || bel.type == "OSCF" ||
                   bel.type == "OSCH" || bel.type == "OSCW" || bel.type == "OSCO" ||
                   bel.type == "OSCA") {
            place_osc(db, bel, tilemap, device);
        } else if (bel.type == "BUFS") {
            place_bufs(db, bel, tilemap);
        } else if (bel.type.find("RAM16SDP") != std::string::npos || bel.type == "RAMW") {
            place_ram16sdp(db, bel, tilemap);
        } else if (bel.type.find("CLKDIV") != std::string::npos) {
            place_clkdiv(db, bel, tilemap, device);
        } else if (bel.type == "DCS") {
            place_dcs(db, bel, tilemap, device);
        } else if (bel.type == "DQCE") {
            place_dqce(db, bel, tilemap);
        } else if (bel.type == "DHCEN") {
            place_dhcen(db, bel, tilemap);
        } else if (bel.type == "ADC") {
            place_adc(db, bel, tilemap, extra_slots);
        } else if (bel.type == "DLLDLY") {
            place_dlldly(db, bel, tilemap);
        } else if (bel.type == "PINCFG") {
            // Validate that --*_as_gpio flags match PINCFG cell parameters
            // (Python gowin_pack.py lines 3212-3216)
            if (args) {
                bool has_i2c = bel.parameters.count("I2C") > 0;
                bool has_sspi = bel.parameters.count("SSPI") > 0;
                if (args->i2c_as_gpio != has_i2c) {
                    std::cerr << "Warning: i2c_as_gpio has conflicting settings in nextpnr and gowin_pack." << std::endl;
                }
                if (args->sspi_as_gpio != has_sspi) {
                    std::cerr << "Warning: sspi_as_gpio has conflicting settings in nextpnr and gowin_pack." << std::endl;
                }
            }
        } else if (bel.type == "GSR" ||
                   bel.type == "BANDGAP" ||
                   bel.type.find("FLASH") != std::string::npos ||
                   bel.type.find("EMCU") != std::string::npos ||
                   bel.type.find("MUX2_") != std::string::npos ||
                   bel.type == "MIPI_OBUF" ||
                   bel.type.find("BUFG") != std::string::npos) {
            // No-op types - skip
            continue;
        } else if (bel.type == "MIPI_IBUF") {
            // MIPI_IBUF itself is a no-op, but we need to set AUX fuses on col+1
            // (Python: extra_mipi_bels + MIPI_IBUF_AUX handling, lines 3225-3232)
            int64_t aux_row = bel.row - 1;
            int64_t aux_col = bel.col;  // col+1 in 0-based (bel.col is already 1-based col, so col = bel.col - 1 + 1 = bel.col)
            if (in_bounds(aux_row, aux_col, db)) {
                const auto& aux_tiledata = db.get_tile(aux_row, aux_col);
                // Set MIPI AUX fuses for both A and B pins
                static const std::map<std::string, std::vector<std::pair<std::string, std::string>>> mipi_aux_attrs = {
                    {"A", {{"IO_TYPE", "LVDS25"}, {"LPRX_A2", "ENABLE"}, {"ODMUX", "TRIMUX"},
                           {"OPENDRAIN", "OFF"}, {"DIFFRESISTOR", "OFF"}, {"BANK_VCCIO", "2.5"}}},
                    {"B", {{"IO_TYPE", "LVDS25"}, {"BANK_VCCIO", "2.5"}}}
                };
                for (const auto& [iob_idx_aux, attr_pairs] : mipi_aux_attrs) {
                    std::set<int64_t> iob_attrs_set;
                    for (const auto& [k, val] : attr_pairs) {
                        auto attr_it = attrids::iob_attrids.find(k);
                        if (attr_it == attrids::iob_attrids.end()) continue;
                        auto val_it = attrids::iob_attrvals.find(val);
                        if (val_it == attrids::iob_attrvals.end()) continue;
                        add_attr_val(db, "IOB", iob_attrs_set, attr_it->second, val_it->second);
                    }
                    std::set<Coord> fuses = get_longval_fuses(db, aux_tiledata.ttyp, iob_attrs_set, "IOB" + iob_idx_aux);
                    set_fuses_in_tile(tilemap[{aux_row, aux_col}], fuses);
                }
            }
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

    if (!in_bounds(row, col, db)) return;

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

    if (!in_bounds(row, col, db)) return;

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

    if (!in_bounds(row, col, db)) return;

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

// Default IO standard by mode (Python _default_iostd)
static const std::map<std::string, std::string> default_iostd = {
    {"IBUF", "LVCMOS18"}, {"OBUF", "LVCMOS18"}, {"TBUF", "LVCMOS18"}, {"IOBUF", "LVCMOS18"},
    {"TLVDS_IBUF", "LVDS25"}, {"TLVDS_OBUF", "LVDS25"}, {"TLVDS_TBUF", "LVDS25"}, {"TLVDS_IOBUF", "LVDS25"},
    {"ELVDS_IBUF", "LVCMOS33D"}, {"ELVDS_OBUF", "LVCMOS33D"}, {"ELVDS_TBUF", "LVCMOS33D"}, {"ELVDS_IOBUF", "LVCMOS33D"},
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
    // IOB fuses are now set entirely by set_iob_default_fuses, which runs
    // after bank determination. This ensures correct BANK_VCCIO is used
    // (from the bank, not the individual IOB's IO_TYPE).
    // See set_iob_default_fuses Step 2b for used IOB processing.
    (void)db; (void)bel; (void)tilemap; (void)device;
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
    // Also collect full bel info for each used IOB for processing in Step 2b
    struct UsedIOBInfo {
        int64_t row, col;
        std::string iob_idx;
        std::string mode;
        std::map<std::string, std::string> user_attrs;  // parsed from &attrs
        std::map<std::string, std::string> params;       // NET_OEN, etc.
        bool hclk = false;       // connected to HCLK_GCLK
        bool hclk_pair = false;  // paired IOB for HCLK routing
    };

    // GW5A-25A HCLK IO pairs: (row, col) -> (pair_row, pair_col) (0-indexed)
    static const std::map<std::pair<int64_t,int64_t>, std::pair<int64_t,int64_t>> hclk_io_pairs = {
        {{36, 11}, {36, 30}}, {{36, 25}, {36, 32}},
        {{36, 53}, {36, 28}}, {{36, 74}, {36, 90}},
    };
    struct BankInfo {
        std::string iostd;
        std::set<std::string> used_bels;
        // Accumulated bank-level attributes from IOBs (matches Python in_bank_attrs)
        std::map<std::string, std::string> in_bank_attrs;
        // Used IOB info for Step 2b processing
        std::vector<UsedIOBInfo> used_iobs;
    };
    std::map<int64_t, BankInfo> banks;

    auto bels = get_bels(netlist);

    // Track the leaked 'mode' variable from the first pass (Python scoping bug).
    // In Python, the first pass loop sets 'mode' for DFF and IOB cells, and
    // the last value leaks into the second IO pass where it's used for DRIVE
    // override at Python lines 3666-3668.
    std::string first_pass_leaked_mode;
    for (const auto& bel : bels) {
        if (bel.type.size() >= 3 && bel.type.substr(0, 3) == "DFF") {
            // Python: mode = typ.strip('E')
            std::string stripped = bel.type;
            while (!stripped.empty() && stripped.back() == 'E') stripped.pop_back();
            first_pass_leaked_mode = stripped;
        } else if (bel.type == "IBUF" || bel.type == "OBUF" ||
                   bel.type == "IOBUF" || bel.type == "TBUF") {
            // MIPI_IBUF B-pin: skipped before mode is set (Python line 3296-3297)
            if (bel.parameters.count("MIPI_IBUF") && bel.num == "B") continue;
            auto diff_it = bel.parameters.find("DIFF");
            if (diff_it != bel.parameters.end()) {
                // N-pin: skipped before mode is set (Python line 3300-3301)
                if (diff_it->second == "N") continue;
                auto dt_it = bel.parameters.find("DIFF_TYPE");
                if (dt_it != bel.parameters.end()) {
                    first_pass_leaked_mode = dt_it->second;
                }
            } else {
                // Non-DIFF IOB: mode from ENABLE/INPUT/OUTPUT flags
                // bel.type already gives the resolved mode
                first_pass_leaked_mode = bel.type;
            }
        }
        // Other types (LUT, ALU, etc.) don't change mode in Python
    }

    for (const auto& bel : bels) {
        if (bel.type != "IBUF" && bel.type != "OBUF" &&
            bel.type != "TBUF" && bel.type != "IOBUF")
            continue;

        int64_t row = bel.row - 1;
        int64_t col = bel.col - 1;
        std::string iob_idx = bel.num;
        if (iob_idx.empty()) iob_idx = "A";

        // Skip B pin for MIPI_IBUF (Python line 3296-3297)
        if (bel.parameters.count("MIPI_IBUF") && iob_idx == "B") {
            continue;
        }

        // Check for DIFF pair handling (Python lines 3298-3315)
        auto diff_it = bel.parameters.find("DIFF");
        std::string diff_type;
        if (diff_it != bel.parameters.end()) {
            // Skip negative pin for LVDS
            if (diff_it->second == "N") {
                continue;
            }
            auto dt_it = bel.parameters.find("DIFF_TYPE");
            if (dt_it != bel.parameters.end()) {
                diff_type = dt_it->second;
            }
            // TLVDS_IBUF_ADC: ADC analog input - skip IOB processing entirely
            // Python line 3312-3315: check_adc_io then continue
            if (diff_type == "TLVDS_IBUF_ADC") {
                continue;
            }
        }

        std::string pin_name = rc_to_pin_name(db, row, col, iob_idx);
        if (pin_name.empty()) continue;

        auto bank_it = db.pin_bank.find(pin_name);
        if (bank_it == db.pin_bank.end()) continue;
        int64_t bank = bank_it->second;

        auto& bi = banks[bank];
        bi.used_bels.insert(pin_name);
        // For DIFF pairs (P pin), also mark the B pin as used
        if (!diff_type.empty()) {
            std::string b_pin = rc_to_pin_name(db, row, col, "B");
            if (!b_pin.empty()) {
                bi.used_bels.insert(b_pin);
            }
        }

        // Parse user attributes from &attr=val format
        std::string iostd = "LVCMOS18";
        std::map<std::string, std::string> user_attrs;
        for (const auto& [flag, val] : bel.attributes) {
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
                    user_attrs[attr_name] = attr_val;
                }
            }
        }
        // Also check direct parameters
        for (const auto& [k, v] : bel.parameters) {
            std::string rk = refine_io_attr_name(k);
            if (rk == "IO_TYPE") {
                iostd = get_iostd_alias(v);
                user_attrs["IO_TYPE"] = iostd;
            } else if (rk == "SLEWRATE" || rk == "PULLMODE" || rk == "DRIVE" ||
                       rk == "OPENDRAIN" || rk == "HYSTERESIS" || rk == "CLAMP" ||
                       rk == "DIFFRESISTOR" || rk == "SINGLERESISTOR" || rk == "VREF" ||
                       rk == "DDR_DYNTERM" || rk == "PULL_STRENGTH") {
                user_attrs[rk] = v;
            }
        }

        // Store full IOB info for Step 2b
        UsedIOBInfo iob_info;
        iob_info.row = row;
        iob_info.col = col;
        iob_info.iob_idx = iob_idx;
        // For DIFF pairs, use DIFF_TYPE as mode (Python line 3307)
        iob_info.mode = diff_type.empty() ? bel.type : diff_type;
        // Update iostd to mode-specific default if no explicit IO_TYPE was set
        // (Python line 3348: iostd = _default_iostd[mode])
        // For GW5A, defaults are LVCMOS33 (Python line 4258)
        if (user_attrs.find("IO_TYPE") == user_attrs.end()) {
            if (is_gw5) {
                // GW5A overrides all basic modes to LVCMOS33
                static const std::set<std::string> basic_modes = {
                    "IBUF", "OBUF", "TBUF", "IOBUF"
                };
                if (basic_modes.count(iob_info.mode)) {
                    iostd = "LVCMOS33";
                } else {
                    auto def_it = default_iostd.find(iob_info.mode);
                    if (def_it != default_iostd.end()) {
                        iostd = def_it->second;
                    }
                }
            } else {
                auto def_it = default_iostd.find(iob_info.mode);
                if (def_it != default_iostd.end()) {
                    iostd = def_it->second;
                }
            }
        }
        // Always set IO_TYPE in user_attrs (Python line 3360: io_desc.attrs['IO_TYPE'] = iostd)
        user_attrs["IO_TYPE"] = iostd;
        // MIPI_OBUF DIFF handling (Python lines 3361-3362)
        if (bel.parameters.count("DIFF") && bel.parameters.count("MIPI_OBUF")) {
            user_attrs["MIPI"] = "ENABLE";
        }
        // I3C handling (Python lines 3363-3364)
        if (bel.parameters.count("I3C_IOBUF")) {
            user_attrs["I3C_IOBUF"] = "ENABLE";
        }
        iob_info.user_attrs = user_attrs;
        // Store NET_* parameters for OEN handling
        for (const auto& [k, v] : bel.parameters) {
            if (k.substr(0, 4) == "NET_") {
                iob_info.params[k] = v;
            }
        }

        // GW5A-25A HCLK clock input detection (Python lines 3365-3381)
        if (device == "GW5A-25A" && bel.cell) {
            // Check if IOB's O port connects to a net with HCLK_GCLK in routing
            auto o_it = bel.cell->port_connections.find("O");
            if (o_it != bel.cell->port_connections.end()) {
                bool hclk_connected = false;
                for (const auto& [net_name, net] : netlist.nets) {
                    auto routing_it = net.attributes.find("ROUTING");
                    if (routing_it == net.attributes.end()) continue;
                    const std::string* routing_str = std::get_if<std::string>(&routing_it->second);
                    if (!routing_str || routing_str->find("HCLK_GCLK") == std::string::npos) continue;
                    // Check if any O bit is in this net
                    for (int obit : o_it->second) {
                        for (int nbit : net.bits) {
                            if (obit == nbit) {
                                hclk_connected = true;
                                break;
                            }
                        }
                        if (hclk_connected) break;
                    }
                    if (hclk_connected) break;
                }
                if (hclk_connected) {
                    auto pair_it = hclk_io_pairs.find({row, col});
                    if (pair_it != hclk_io_pairs.end()) {
                        // Create paired IOB entry
                        UsedIOBInfo pair_info;
                        pair_info.row = pair_it->second.first;
                        pair_info.col = pair_it->second.second;
                        pair_info.iob_idx = "A";
                        pair_info.mode = iob_info.mode;
                        pair_info.user_attrs = {{"IO_TYPE", iostd}};
                        pair_info.params = iob_info.params;
                        pair_info.hclk_pair = true;
                        bi.used_iobs.push_back(std::move(pair_info));
                    }
                    iob_info.hclk = true;
                }
            }
        }

        // Output IOBs determine bank IO standard and contribute bank attrs
        // NOTE: Must be done BEFORE std::move(iob_info) below
        // Python lines 3568: mode must be in {OBUF, IOBUF, TLVDS_OBUF, TLVDS_IOBUF,
        //   TLVDS_TBUF, ELVDS_OBUF, ELVDS_IOBUF} (note: ELVDS_TBUF is NOT in the list)
        {
            static const std::set<std::string> output_modes = {
                "OBUF", "IOBUF", "TLVDS_OBUF", "TLVDS_IOBUF",
                "TLVDS_TBUF", "ELVDS_OBUF", "ELVDS_IOBUF"
            };
            if (output_modes.count(iob_info.mode)) {
                // ELVDS_OBUF/ELVDS_IOBUF force BANK_VCCIO to 1.2
                if (iob_info.mode == "ELVDS_OBUF" || iob_info.mode == "ELVDS_IOBUF") {
                    bi.in_bank_attrs["BANK_VCCIO"] = "1.2";
                }
                if (bi.iostd.empty()) {
                    std::string io_type_for_bank = iostd;
                    if (!io_type_for_bank.empty() && io_type_for_bank.find("LVDS") != 0) {
                        bi.iostd = io_type_for_bank;
                    }
                }
                // NOTE: Python does NOT accumulate user_attrs into in_bank_attrs during
                // the first pass. Bank attrs are accumulated in the second pass (Step 2b).
            }
        }

        bi.used_iobs.push_back(std::move(iob_info));
    }

    // For banks with IOBs but no output IOBs setting IO standard, use default
    for (auto& [bank, bi] : banks) {
        if (bi.iostd.empty()) {
            bi.iostd = is_gw5 ? "LVCMOS33" : "LVCMOS12";
        }
        // Set BANK_VCCIO default if not already set (matching Python line 3591-3592)
        if (bi.in_bank_attrs.find("BANK_VCCIO") == bi.in_bank_attrs.end()) {
            auto vcc_it = vcc_ios.find(bi.iostd);
            if (vcc_it != vcc_ios.end()) {
                bi.in_bank_attrs["BANK_VCCIO"] = vcc_it->second;
            }
        }
        // NOTE: IO_TYPE is NOT set here - it gets accumulated in Step 2b (second pass)
    }


    // Step 2b: Set fuses for USED IOBs with full attributes + bank VCCIO
    // NOTE: This must run BEFORE bank fuse generation (Step 2c below) because
    // Python accumulates in_bank_attrs during IOB processing, then generates
    // bank fuses afterward.
    // Matches Python gowin_pack.py lines 3596-3730 (second IOB pass)
    for (auto& [bank, bi] : banks) {
        for (const auto& iob : bi.used_iobs) {
            const std::string& mode = iob.mode;
            bool is_tlvds = mode.substr(0, 6) == "TLVDS_";
            bool is_elvds = mode.substr(0, 6) == "ELVDS_";
            bool is_lvds = is_tlvds || is_elvds;

            // Determine base mode for init_io_attrs lookup (Python lines 3601-3604)
            std::string mode_for_attrs = mode;
            std::map<std::string, std::string> lvds_attrs;
            if (is_lvds) {
                mode_for_attrs = mode.substr(6);  // strip TLVDS_/ELVDS_ prefix
                lvds_attrs = {{"HYSTERESIS", "NA"}, {"PULLMODE", "NONE"}, {"OPENDRAIN", "OFF"}};
            }

            // Build IOB attributes from init_io_attrs for the base mode
            auto init_it = init_io_attrs.find(mode_for_attrs);
            if (init_it == init_io_attrs.end()) continue;
            std::map<std::string, std::string> in_iob_attrs = init_it->second;
            // GW5A: add PULL_STRENGTH=MEDIUM (Python line 4254-4257)
            if (is_gw5) {
                in_iob_attrs["PULL_STRENGTH"] = "MEDIUM";
            }
            // Apply LVDS overrides
            for (const auto& [lk, lv] : lvds_attrs) {
                in_iob_attrs[lk] = lv;
            }

            // Handle OEN connections (Python lines 3611-3621)
            static const std::set<std::string> non_ibuf_modes = {
                "OBUF", "IOBUF", "TBUF",
                "TLVDS_OBUF", "TLVDS_IOBUF", "TLVDS_TBUF",
                "ELVDS_OBUF", "ELVDS_IOBUF", "ELVDS_TBUF"
            };
            if (non_ibuf_modes.count(mode)) {
                auto oen_it = iob.params.find("NET_OEN");
                if (oen_it != iob.params.end() && !oen_it->second.empty()) {
                    const std::string& oen_val = oen_it->second;
                    if (oen_val == "GND") {
                        in_iob_attrs["TRIMUX_PADDT"] = "SIG";
                    } else if (oen_val == "VCC") {
                        in_iob_attrs["ODMUX_1"] = "0";
                    } else if (oen_val != "NET") {
                        in_iob_attrs["TRIMUX_PADDT"] = "SIG";
                        in_iob_attrs["TO"] = "SIG";
                    }
                } else {
                    in_iob_attrs["ODMUX_1"] = "1";
                }
            }

            // Apply user attributes (Python lines 3624-3627)
            for (const auto& [k, val] : iob.user_attrs) {
                in_iob_attrs[k] = val;
            }

            // Set BANK_VCCIO from bank (Python line 3627)
            auto bank_vccio_it = bi.in_bank_attrs.find("BANK_VCCIO");
            if (bank_vccio_it != bi.in_bank_attrs.end()) {
                in_iob_attrs["BANK_VCCIO"] = bank_vccio_it->second;
            }

            // TLVDS output buffer overrides (Python lines 3631-3633)
            if (mode == "TLVDS_OBUF" || mode == "TLVDS_TBUF" || mode == "TLVDS_IOBUF") {
                in_iob_attrs["LVDS_OUT"] = "ON";
                in_iob_attrs["ODMUX_1"] = "UNKNOWN";
                in_iob_attrs["ODMUX"] = "TRIMUX";
                in_iob_attrs["SLEWRATE"] = "FAST";
                in_iob_attrs["PERSISTENT"] = "OFF";
                in_iob_attrs["DRIVE"] = "0";
                in_iob_attrs["DIFFRESISTOR"] = "OFF";
            }
            // ELVDS output buffer overrides (Python lines 3634-3637)
            else if (mode == "ELVDS_OBUF" || mode == "ELVDS_TBUF" || mode == "ELVDS_IOBUF") {
                in_iob_attrs["ODMUX_1"] = "UNKNOWN";
                in_iob_attrs["ODMUX"] = "TRIMUX";
                in_iob_attrs["PERSISTENT"] = "OFF";
                in_iob_attrs["DIFFRESISTOR"] = "OFF";
                in_iob_attrs["IO_TYPE"] = get_iostd_alias(in_iob_attrs["IO_TYPE"]);
            }
            // TLVDS/ELVDS input buffer overrides (Python lines 3638-3640)
            if (mode == "TLVDS_IBUF" || mode == "ELVDS_IBUF") {
                in_iob_attrs["ODMUX_1"] = "UNKNOWN";
                in_iob_attrs.erase("BANK_VCCIO");
            }

            // MIPI IOB handling (Python lines 3641-3647)
            if (in_iob_attrs.count("IO_TYPE") && in_iob_attrs["IO_TYPE"] == "MIPI") {
                in_iob_attrs["LPRX_A1"] = "ENABLE";
                in_iob_attrs.erase("SLEWRATE");
                in_iob_attrs.erase("BANK_VCCIO");
                in_iob_attrs["PULLMODE"] = "NONE";
                in_iob_attrs["LVDS_ON"] = "ENABLE";
                in_iob_attrs["IOBUF_MIPI_LP"] = "ENABLE";
            }
            // I3C IOB handling (Python lines 3648-3655)
            if (in_iob_attrs.count("I3C_IOBUF")) {
                in_iob_attrs.erase("I3C_IOBUF");
                in_iob_attrs["PULLMODE"] = "NONE";
                in_iob_attrs["OPENDRAIN"] = "OFF";
                in_iob_attrs["OD"] = "ENABLE";
                in_iob_attrs["DIFFRESISTOR"] = "NA";
                in_iob_attrs["SINGLERESISTOR"] = "NA";
                in_iob_attrs["DRIVE"] = "16";
            }

            // Device-specific special cases (Python lines 3658-3663)
            if (device == "GW1N-1") {
                if (iob.row == 5 && mode_for_attrs == "OBUF") {
                    in_iob_attrs["TO"] = "UNKNOWN";
                }
            }
            // Python lines 3666-3668: leaked 'mode' variable DRIVE override
            // In Python, the 'mode' variable from the first pass leaks into the
            // second IO pass. If mode[1:] starts with 'LVDS', all IOBs with
            // non-zero DRIVE get DRIVE='UNKNOWN'.
            if (device != "GW1N-4" && device != "GW1NS-4") {
                if (first_pass_leaked_mode.size() > 1 &&
                    first_pass_leaked_mode.substr(1, 4) == "LVDS" &&
                    in_iob_attrs.count("DRIVE") && in_iob_attrs["DRIVE"] != "0") {
                    in_iob_attrs["DRIVE"] = "UNKNOWN";
                }
            }
            // Build B-pin attributes for LVDS pairs (Python lines 3664-3685)
            std::map<std::string, std::string> in_iob_b_attrs;
            // MIPI: change IO_TYPE to LVDS25 and set B-pin attrs (Python lines 3665-3671)
            if (in_iob_attrs.count("IO_TYPE") && in_iob_attrs["IO_TYPE"] == "MIPI") {
                in_iob_attrs["IO_TYPE"] = "LVDS25";
                in_iob_b_attrs["IO_TYPE"] = "LVDS25";
                in_iob_b_attrs["PULLMODE"] = "NONE";
                in_iob_b_attrs["OPENDRAIN"] = "OFF";
                in_iob_b_attrs["IOBUF_MIPI_LP"] = "ENABLE";
                in_iob_b_attrs["PERSISTENT"] = "OFF";
            }
            if (mode == "TLVDS_OBUF" || mode == "TLVDS_TBUF" || mode == "TLVDS_IOBUF") {
                in_iob_b_attrs = in_iob_attrs;
            } else if (mode == "TLVDS_IBUF" || mode == "ELVDS_IBUF") {
                in_iob_b_attrs = in_iob_attrs;
                if (mode == "ELVDS_IBUF") {
                    in_iob_attrs["PULLMODE"] = "UP";
                    in_iob_b_attrs["PULLMODE"] = "NONE";
                }
                in_iob_b_attrs["IO_TYPE"] = in_iob_attrs.count("IO_TYPE") ? in_iob_attrs["IO_TYPE"] : "UNKNOWN";
                in_iob_b_attrs["DIFFRESISTOR"] = in_iob_attrs.count("DIFFRESISTOR") ? in_iob_attrs["DIFFRESISTOR"] : "OFF";
            } else if (mode == "ELVDS_OBUF" || mode == "ELVDS_TBUF" || mode == "ELVDS_IOBUF") {
                if (mode == "ELVDS_IOBUF") {
                    in_iob_attrs["PULLMODE"] = "UP";
                }
                in_iob_b_attrs = in_iob_attrs;
            }

            // Look up and set fuses for both A and B pins
            if (!in_bounds(iob.row, iob.col, db))
                continue;
            const auto& tiledata = db.get_tile(iob.row, iob.col);

            // Process both (idx, in_iob_attrs) and possibly ('B', in_iob_b_attrs)
            // Python line 3687: for iob_idx, atr in [(idx, in_iob_attrs), ('B', in_iob_b_attrs)]:
            std::vector<std::pair<std::string, std::map<std::string, std::string>*>> iob_pairs;
            iob_pairs.push_back({iob.iob_idx, &in_iob_attrs});
            if (!in_iob_b_attrs.empty()) {
                iob_pairs.push_back({"B", &in_iob_b_attrs});
            }

            for (auto& [cur_idx, atr_ptr] : iob_pairs) {
                auto& atr = *atr_ptr;

                std::set<int64_t> iob_attrs_set;
                for (const auto& [k, val] : atr) {
                    auto attr_it = iob_attrids.find(k);
                    if (attr_it == iob_attrids.end()) continue;
                    auto val_it = iob_attrvals.find(val);
                    if (val_it == iob_attrvals.end()) continue;
                    add_attr_val(db, "IOB", iob_attrs_set, attr_it->second, val_it->second);
                    // Update in_bank_attrs (Python lines 3694-3699)
                    if (k == "LVDS_OUT" && val != "ENABLE" && val != "ON") {
                        if (!is_gw5) continue;
                    }
                    if (k == "IO_TYPE" && bi.in_bank_attrs.count("IO_TYPE") &&
                        bi.in_bank_attrs["IO_TYPE"].find("LVDS") == 0) {
                        continue;
                    }
                    bi.in_bank_attrs[k] = val;
                }

                int64_t fuse_row = iob.row;
                int64_t fuse_col = iob.col;
                int64_t fuse_ttyp = tiledata.ttyp;

                if (is_gw5) {
                    std::string iob_bel_name = "IOB" + cur_idx;
                    auto iob_bel_it = tiledata.bels.find(iob_bel_name);
                    if (iob_bel_it != tiledata.bels.end() && iob_bel_it->second.fuse_cell_offset) {
                        fuse_row += iob_bel_it->second.fuse_cell_offset->first;
                        fuse_col += iob_bel_it->second.fuse_cell_offset->second;
                        fuse_ttyp = db.get_ttyp(fuse_row, fuse_col);
                    }
                    if (mode_for_attrs == "OBUF" || mode_for_attrs == "IOBUF") {
                        add_attr_val(db, "IOB", iob_attrs_set,
                                     iob_attrids.at("IOB_UNKNOWN51"), iob_attrvals.at("TRIMUX"));
                    } else if (mode_for_attrs == "IBUF") {
                        // HCLK clock input fuses (Python lines 3708-3711)
                        if (iob.hclk) {
                            add_attr_val(db, "IOB", iob_attrs_set,
                                         iob_attrids.at("IOB_UNKNOWN67"), iob_attrvals.at("UNKNOWN263"));
                        } else if (iob.hclk_pair) {
                            add_attr_val(db, "IOB", iob_attrs_set,
                                         iob_attrids.at("IOB_UNKNOWN67"), iob_attrvals.at("UNKNOWN266"));
                        }
                    }
                }

std::set<Coord> fuses = get_longval_fuses(db, fuse_ttyp, iob_attrs_set,
                                                           "IOB" + cur_idx);
                auto& tile = tilemap[{fuse_row, fuse_col}];
                set_fuses_in_tile(tile, fuses);
            } // end for iob_pairs
        }
    }

    // Step 2c: Set bank-level fuses for used banks
    // This runs AFTER Step 2b so that in_bank_attrs has all accumulated IOB attrs
    // Python filters in_bank_attrs to this whitelist for bank fuse generation
    static const std::set<std::string> bank_attr_whitelist = {
        "BANK_VCCIO", "IO_TYPE", "LVDS_OUT", "DRIVE", "OPENDRAIN", "PULL_STRENGTH"
    };
    auto bt = db.bank_tiles();
    for (const auto& [bank, bi] : banks) {
        auto bt_it = bt.find(bank);
        if (bt_it == bt.end()) continue;
        auto [brow, bcol] = bt_it->second;
        const auto& tiledata = db.get_tile(brow, bcol);

        std::set<int64_t> bank_attrs;
        for (const auto& [k, val] : bi.in_bank_attrs) {
            if (bank_attr_whitelist.find(k) == bank_attr_whitelist.end()) continue;
            auto attr_it = iob_attrids.find(k);
            auto val_it = iob_attrvals.find(val);
            if (attr_it != iob_attrids.end() && val_it != iob_attrvals.end()) {
                add_attr_val(db, "IOB", bank_attrs, attr_it->second, val_it->second);
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

    // Step 3: Set per-pin default fuses for all IOB pins
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

        // Note: in the Python packer, _banks[bank].bels is never populated
        // (the .bels.add() line is commented out), so the unused IOB loop
        // processes ALL pins including used ones, writing default attrs on top.
        // We match this behavior by NOT skipping used pins.
        auto bi_it = banks.find(bank);

        // Determine IO standard for this bank
        std::string io_std;
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

        if (!in_bounds(row, col, db)) continue;

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

        // GW5A-specific: OPENDRAIN, DRIVE, DRIVE_LEVEL, and pullup/iomode
        if (is_gw5) {
            auto add_iob_attr = [&](const std::string& attr_name, const std::string& val_name) {
                auto a_it = iob_attrids.find(attr_name);
                auto v_it = iob_attrvals.find(val_name);
                if (a_it != iob_attrids.end() && v_it != iob_attrvals.end()) {
                    add_attr_val(db, "IOB", iob_attrs, a_it->second, v_it->second);
                }
            };

            add_iob_attr("OPENDRAIN", "OFF");
            std::string drive = (io_std == "LVCMOS10") ? "4" : "8";
            add_iob_attr("DRIVE", drive);
            add_iob_attr("DRIVE_LEVEL", drive);

            // get_pullup_io equivalent: determine PULLMODE and PADDI/TO/ODMUX_1
            // based on pin configuration
            static const std::set<std::string> no_pullup_cfgs = {
                "D08", "D09", "D10", "D11", "D12", "D13", "D14", "D15",
                "D16", "D17", "D18", "D19", "D20", "D21", "D22", "D23",
                "D24", "D25", "D26", "D27", "D28", "D29", "D30", "D31",
                "INITDLY0", "INITDLY1"
            };

            if (cfg.count("TDO") || cfg.count("DOUT")) {
                add_iob_attr("TO", "INV");
                add_iob_attr("ODMUX_1", "1");
                add_iob_attr("PULLMODE", "UP");
            } else if (cfg.count("RDWR") || cfg.count("RDWR_B") || cfg.count("PUDC_B")) {
                add_iob_attr("PADDI", "PADDI");
                add_iob_attr("PULLMODE", "DOWN");
            } else {
                bool has_no_pullup = false;
                for (const auto& cf : cfg) {
                    if (no_pullup_cfgs.count(cf)) {
                        has_no_pullup = true;
                        break;
                    }
                }
                if (has_no_pullup) {
                    add_iob_attr("PADDI", "PADDI");
                    add_iob_attr("PULLMODE", "NONE");
                } else {
                    add_iob_attr("PADDI", "PADDI");
                    add_iob_attr("PULLMODE", "UP");
                }
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
void place_pll(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device,
               std::map<int, TileBitmap>* extra_slots) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

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
            // Determine index: Python uses 1-based col (bel.col)
            // col != 28 in Python means bel.col != 28
            int idx = (bel.col != 28) ? 1 : 0;
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

    // For PLLA, rename params (prefix with A_) and merge defaults
    // Python: new_attrs = plla_attr_rename(attrs)
    //         pll_inattrs = add_pll_default_attrs(new_attrs, _default_plla_inattrs)
    if (pll_type == "PLLA") {
        std::map<std::string, std::string> plla_params;
        // Rename: prefix non-FCLKIN params with 'A_'
        for (const auto& [k, v] : params) {
            std::string uk = to_upper(k);
            if (uk != "FCLKIN") {
                plla_params["A_" + uk] = v;
            } else {
                plla_params[uk] = v;
            }
        }
        // Merge _default_plla_inattrs (only add if not already present)
        static const std::vector<std::pair<std::string, std::string>> default_plla_inattrs = {
            {"FCLKIN", "100.00"},
            {"A_IDIV_SEL", "1"},
            {"A_FBDIV_SEL", "1"},
            {"A_ODIV0_SEL", "8"},
            {"A_ODIV1_SEL", "8"},
            {"A_ODIV2_SEL", "8"},
            {"A_ODIV3_SEL", "8"},
            {"A_ODIV4_SEL", "8"},
            {"A_ODIV5_SEL", "8"},
            {"A_ODIV6_SEL", "8"},
            {"A_MDIV_SEL", "8"},
            {"A_MDIV_FRAC_SEL", "0"},
            {"A_ODIV0_FRAC_SEL", "0"},
            {"A_CLKOUT0_EN", "TRUE"},
            {"A_CLKOUT1_EN", "TRUE"},
            {"A_CLKOUT2_EN", "TRUE"},
            {"A_CLKOUT3_EN", "TRUE"},
            {"A_CLKOUT4_EN", "TRUE"},
            {"A_CLKOUT5_EN", "TRUE"},
            {"A_CLKOUT6_EN", "TRUE"},
            {"A_CLKFB_SEL", "INTERNAL"},
            {"A_CLKOUT0_DT_DIR", "1"},
            {"A_CLKOUT1_DT_DIR", "1"},
            {"A_CLKOUT2_DT_DIR", "1"},
            {"A_CLKOUT3_DT_DIR", "1"},
            {"A_CLKOUT0_DT_STEP", "0"},
            {"A_CLKOUT1_DT_STEP", "0"},
            {"A_CLKOUT2_DT_STEP", "0"},
            {"A_CLKOUT3_DT_STEP", "0"},
            {"A_CLK0_IN_SEL", "0"},
            {"A_CLK0_OUT_SEL", "0"},
            {"A_CLK1_IN_SEL", "0"},
            {"A_CLK1_OUT_SEL", "0"},
            {"A_CLK2_IN_SEL", "0"},
            {"A_CLK2_OUT_SEL", "0"},
            {"A_CLK3_IN_SEL", "0"},
            {"A_CLK3_OUT_SEL", "0"},
            {"A_CLK4_IN_SEL", "0"},
            {"A_CLK4_OUT_SEL", "0"},
            {"A_CLK5_IN_SEL", "0"},
            {"A_CLK5_OUT_SEL", "0"},
            {"A_CLK6_IN_SEL", "0"},
            {"A_CLK6_OUT_SEL", "0"},
            {"A_DYN_DPA_EN", "FALSE"},
            {"A_CLKOUT0_PE_COARSE", "0"},
            {"A_CLKOUT0_PE_FINE", "0"},
            {"A_CLKOUT1_PE_COARSE", "0"},
            {"A_CLKOUT1_PE_FINE", "0"},
            {"A_CLKOUT2_PE_COARSE", "0"},
            {"A_CLKOUT2_PE_FINE", "0"},
            {"A_CLKOUT3_PE_COARSE", "0"},
            {"A_CLKOUT3_PE_FINE", "0"},
            {"A_CLKOUT4_PE_COARSE", "0"},
            {"A_CLKOUT4_PE_FINE", "0"},
            {"A_CLKOUT5_PE_COARSE", "0"},
            {"A_CLKOUT5_PE_FINE", "0"},
            {"A_CLKOUT6_PE_COARSE", "0"},
            {"A_CLKOUT6_PE_FINE", "0"},
            {"A_DYN_PE0_SEL", "FALSE"},
            {"A_DYN_PE1_SEL", "FALSE"},
            {"A_DYN_PE2_SEL", "FALSE"},
            {"A_DYN_PE3_SEL", "FALSE"},
            {"A_DYN_PE4_SEL", "FALSE"},
            {"A_DYN_PE5_SEL", "FALSE"},
            {"A_DYN_PE6_SEL", "FALSE"},
            {"A_DE0_EN", "FALSE"},
            {"A_DE1_EN", "FALSE"},
            {"A_DE2_EN", "FALSE"},
            {"A_DE3_EN", "FALSE"},
            {"A_DE4_EN", "FALSE"},
            {"A_DE5_EN", "FALSE"},
            {"A_DE6_EN", "FALSE"},
            {"A_RESET_I_EN", "FALSE"},
            {"A_RESET_O_EN", "FALSE"},
            {"A_DYN_ICP_SEL", "FALSE"},
            {"A_ICP_SEL", "0"},
            {"A_DYN_LPF_SEL", "FALSE"},
            {"A_LPF_RES", "0"},
            {"A_LPF_CAP", "0"},
            {"A_SSC_EN", "0"},
        };
        for (const auto& [k, v] : default_plla_inattrs) {
            if (plla_params.find(k) == plla_params.end()) {
                plla_params[k] = v;
            }
        }
        params = std::move(plla_params);
    }

    for (const auto& [attr, val] : params) {
        std::string ua = to_upper(attr);
        std::string uv = to_upper(val);

        // Generic handler: if this attr is already a default string attr, override it.
        // Python: "if attr in pll_attrs: pll_attrs[attr] = val"
        if (pll_str_attrs.count(ua)) {
            pll_str_attrs[ua] = uv;
        }

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
        // Note: Python's attrs_upper() uppercases values BEFORE this loop runs,
        // but then compares against lowercase "true". Since "TRUE" != "true",
        // these bypass/dynamic checks effectively NEVER trigger in Python.
        // We match Python's (buggy) behavior by comparing the uppercased value
        // against lowercase "true", which always fails.
        if (ua == "DYN_IDIV_SEL") {
            if (uv == "true") pll_str_attrs["IDIVSEL"] = "DYN";
            continue;
        }
        if (ua == "DYN_FBDIV_SEL") {
            if (uv == "true") pll_str_attrs["FDIVSEL"] = "DYN";
            continue;
        }
        if (ua == "DYN_ODIV_SEL") {
            if (uv == "true") pll_str_attrs["ODIVSEL"] = "DYN";
            continue;
        }
        if (ua == "CLKOUT_BYPASS") {
            if (uv == "true") pll_str_attrs["BYPCK"] = "BYPASS";
            continue;
        }
        if (ua == "CLKOUTP_BYPASS") {
            if (uv == "true") pll_str_attrs["BYPCKPS"] = "BYPASS";
            continue;
        }
        if (ua == "CLKOUTD_BYPASS") {
            if (uv == "true") pll_str_attrs["BYPCKDIV"] = "BYPASS";
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
            // Python bug: attrs_upper() converts 'true' to 'TRUE', then
            // compares val == 'true' (lowercase), so the true branch is
            // never reached.  Match that behaviour here.
            if (false && uv == "TRUE") {
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

    // Apply defaults for parameters that may not be in the cell params
    // Python: add_pll_default_attrs merges _default_pll_inattrs before the loop
    if (pll_type == "RPLL" || pll_type == "PLLVR") {
        // DYN_SDIV_SEL default: 2  (binary "...010")
        if (pll_int_attrs.find("SDIV") == pll_int_attrs.end()) {
            pll_int_attrs["SDIV"] = 2;
        }
        // DYN_DA_EN default: FALSE -> compute DUTY from PSDA_SEL + DUTYDA_SEL
        if (pll_int_attrs.find("DUTY") == pll_int_attrs.end()) {
            pll_str_attrs["OSDLY"] = "DISABLE";
            pll_str_attrs["OPDLY"] = "DISABLE";
            int64_t phase_val = parse_binary(get_param(params, "PSDA_SEL", "0000"));
            pll_int_attrs["PHASE"] = phase_val;
            int64_t duty_val = parse_binary(get_param(params, "DUTYDA_SEL", "1000"));
            if ((phase_val + duty_val) < 16) {
                duty_val = phase_val + duty_val;
            } else {
                duty_val = phase_val + duty_val - 16;
            }
            pll_int_attrs["DUTY"] = duty_val;
        }
    }

    // Calculate pump parameters
    // Python: pump calc is device-based, not PLL-type-based (GW5A-25A has PLLA)
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
    } else if (pll_type != "PLLA") {
        double fref = fclkin / idiv;
        double fvco = (odiv * fbdiv * fclkin) / idiv;
        auto [fclkin_idx, icp, r_idx] = calc_pll_pump(fref, fvco, device);
        pll_int_attrs["ICPSEL"] = icp;
        pll_str_attrs["LPR"] = "R" + std::to_string(r_idx);
        pll_int_attrs["FLDCOUNT"] = fclkin_idx;
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

    // For PLLA (GW5A), write PLL fuses to extra slot bitmap (Python lines 3471-3474)
    if (pll_type == "PLLA" && extra_slots) {
        std::set<Coord> fuses = get_shortval_fuses(db, 1024, fin_attrs, "PLL");
        // Get slot_idx from extra_func[row, col]['pll']['slot_idx']
        auto ef_it = db.extra_func.find({row, col});
        if (ef_it != db.extra_func.end()) {
            auto pll_it = ef_it->second.find("pll");
            if (pll_it != ef_it->second.end()) {
                using msgpack::adaptor::get_map_value;
                int64_t slot_idx = get_map_value<int64_t>(pll_it->second, "slot_idx");

                // Create or get 8x35 slot bitmap (Python: bitmatrix.zeros(8, 35))
                auto& slot_bitmap = (*extra_slots)[static_cast<int>(slot_idx)];
                if (slot_bitmap.empty()) {
                    slot_bitmap = create_tile_bitmap(8, 35);
                }
                for (const auto& [r, c] : fuses) {
                    if (r >= 0 && r < 8 && c >= 0 && c < 35) {
                        slot_bitmap[r][c] = 1;
                    }
                }
            }
        }
    } else {
        // Non-PLLA: write PLL fuses to main tilemap
        std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, "PLL");
        auto& tile = tilemap[{row, col}];
        set_fuses_in_tile(tile, fuses);
    }

    // PLLVR: also write PLL fuses to cfg tile (only for GW1NS-4 / 4C)
    if (pll_type == "PLLVR") {
        int64_t cfg_type = 51;
        int64_t cfg_col = 37;
        std::set<Coord> cfg_fuses = get_shortval_fuses(db, cfg_type, fin_attrs, "PLL");
        if (!cfg_fuses.empty()) {
            set_fuses_in_tile(tilemap[{0, cfg_col}], cfg_fuses);
        }
    }

    // rPLL occupies adjacent tiles (RPLLB). For GW1N-1/GW1NZ-1/GW1N-4: 1 extra tile at col+1.
    // For GW1N-9/GW1N-9C/GW2A-18/GW2A-18C: 3 extra tiles.
    int num_extra = 0;
    int dir = 1;
    if (pll_type == "RPLL") {
        if (device == "GW1N-9C" || device == "GW1N-9" ||
            device == "GW2A-18" || device == "GW2A-18C") {
            num_extra = 3;
            if (col > 28) dir = -1;
        } else if (device == "GW1N-1" || device == "GW1NZ-1" || device == "GW1N-4") {
            num_extra = 1;
        }
    }
    for (int off = 1; off <= num_extra; ++off) {
        int64_t ecol = col + dir * off;
        if (ecol >= 0 && ecol < static_cast<int64_t>(db.cols())) {
            int64_t ettyp = db.get_ttyp(row, ecol);
            std::set<Coord> efuses = get_shortval_fuses(db, ettyp, fin_attrs, "PLL");
            if (!efuses.empty()) {
                set_fuses_in_tile(tilemap[{row, ecol}], efuses);
            }
        }
    }
}

// ============================================================================
// BSRAM constants
// ============================================================================

static const std::map<int64_t, std::string> bsram_bit_widths = {
    {1, "1"}, {2, "2"}, {4, "4"}, {8, "9"}, {9, "9"}, {16, "16"}, {18, "16"}, {32, "X36"}, {36, "X36"},
};

// ============================================================================
// store_bsram_init_val - Store BSRAM init data into global init map
// Based on apycula/gowin_pack.py store_bsram_init_val()
// ============================================================================
void store_bsram_init_val(const Device& db, int64_t row, int64_t col,
                          const std::string& typ,
                          const std::map<std::string, std::string>& params,
                          const std::map<std::string, std::string>& attrs,
                          const std::string& device,
                          BsramInitMap& bsram_init_map,
                          int map_offset) {
    // Skip BSRAM_AUX and cells without INIT_RAM_00
    if (typ == "BSRAM_AUX" || params.find("INIT_RAM_00") == params.end()) {
        return;
    }

    // Get subtype
    std::string subtype;
    auto st_it = attrs.find("BSRAM_SUBTYPE");
    if (st_it != attrs.end()) {
        subtype = to_upper(st_it->second);
        // Trim whitespace
        size_t start = subtype.find_first_not_of(" \t\n\r");
        size_t end = subtype.find_last_not_of(" \t\n\r");
        subtype = (start == std::string::npos) ? "" : subtype.substr(start, end - start + 1);
    }

    bool is_gw5 = is_gw5_family(device);

    // Initialize global map if empty
    if (bsram_init_map.empty()) {
        size_t init_height = is_gw5 ? 72 : 256;
        bsram_init_map = zeros(init_height * db.simplio_rows.size(),
                               static_cast<size_t>(db.width()));
    }

    // Create local map
    auto loc_map = is_gw5 ? zeros(256, 72) : zeros(256, 3 * 60);

    // Determine data width per init row
    int width;
    if (subtype.empty()) {
        width = 256;
    } else if (subtype == "X9") {
        width = 288;
    } else {
        std::cerr << "Warning: BSRAM init for subtype '" << subtype
                  << "' is not supported" << std::endl;
        return;
    }

    // Get reverse logicinfo for BSRAM_INIT
    const auto& rev_li = db.rev_logicinfo("BSRAM_INIT");

    // Process INIT_RAM_00 through INIT_RAM_3F
    int addr = -1;
    for (int init_row = 0; init_row < 0x40; ++init_row) {
        char row_name_buf[32];
        snprintf(row_name_buf, sizeof(row_name_buf), "INIT_RAM_%02X", init_row);
        std::string row_name(row_name_buf);

        auto it = params.find(row_name);
        if (it == params.end()) {
            addr += 0x100;
            continue;
        }

        const std::string& init_data = it->second;

        // Process bits - inline replication of Python get_bits generator
        int bit_no = 0;
        int ptr = -1;
        while (ptr >= -width) {
            bool is_parity = (bit_no == 8 || bit_no == 17);
            char bit_char;
            bool inc_addr;
            int current_bit_no = bit_no;

            if (is_parity) {
                if (width == 288) {
                    int actual_idx = static_cast<int>(init_data.size()) + ptr;
                    bit_char = (actual_idx >= 0) ? init_data[actual_idx] : '0';
                    ptr--;
                } else {
                    bit_char = '0';
                }
                inc_addr = false;
            } else {
                int actual_idx = static_cast<int>(init_data.size()) + ptr;
                bit_char = (actual_idx >= 0) ? init_data[actual_idx] : '0';
                ptr--;
                inc_addr = true;
            }

            bit_no = (bit_no + 1) % 18;

            // Apply addr increment
            if (inc_addr) {
                addr++;
            }

            if (bit_char == '0') {
                continue;
            }

            int logic_line = current_bit_no * 4 + (addr >> 12);
            auto li_it = rev_li.find(logic_line);
            if (li_it == rev_li.end()) continue;
            int bit = static_cast<int>(li_it->second.first) - 1;

            // Quad address remapping
            int quad;
            switch (addr & 0x30) {
                case 0x30: quad = 0xc0; break;
                case 0x20: quad = 0x40; break;
                case 0x10: quad = 0x80; break;
                default:   quad = 0x00; break;
            }
            int map_row = quad + ((addr >> 6) & 0x3f);
            if (map_row >= 0 && map_row < static_cast<int>(loc_map.size()) &&
                bit >= 0 && bit < static_cast<int>(loc_map[0].size())) {
                loc_map[map_row][bit] = 1;
            }
        }
    }

    // Place local map into global bsram_init_map
    int height = is_gw5 ? 72 : 256;
    if (is_gw5) {
        loc_map = transpose(loc_map);
    }

    int y = 0;
    for (int64_t brow : db.simplio_rows) {
        if (row == brow) break;
        y += height;
    }

    int x = 0;
    if (is_gw5) {
        x = 256 * map_offset;
    } else {
        for (int64_t jdx = 0; jdx < col; ++jdx) {
            x += static_cast<int>(db.get_tile(0, jdx).width);
        }
    }

    loc_map = flipud(loc_map);
    for (const auto& lrow : loc_map) {
        int x0 = x;
        for (uint8_t val : lrow) {
            if (val && y >= 0 && y < static_cast<int>(bsram_init_map.size()) &&
                x0 >= 0 && x0 < static_cast<int>(bsram_init_map[0].size())) {
                bsram_init_map[y][x0] = val;
            }
            x0++;
        }
        y++;
    }
}

// ============================================================================
// place_bsram - Place a BSRAM BEL
// Uses shortval table "BSRAM_{typ}"
// ============================================================================
void place_bsram(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

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
                // Note: In Python, byte_enable dispatch for BIT_WIDTH_0 with val=16/18
                // is dead code (nested inside else for 32/36). Only SDP with 32/36 is live.
                if (val == 32 || val == 36) {
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
                // Note: In Python, byte_enable dispatch for BIT_WIDTH_1 is all
                // dead code (nested inside else for 32/36). No byte_enable set here.
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

    // Set fuses in adjacent BSRAM AUX tiles (col+1 and col+2)
    for (int off = 1; off <= 2; ++off) {
        int64_t aux_col = col + off;
        if (aux_col < static_cast<int64_t>(db.cols())) {
            int64_t aux_ttyp = db.get_ttyp(row, aux_col);
            std::set<Coord> aux_fuses = get_shortval_fuses(db, aux_ttyp, fin_attrs, table_name);
            if (!aux_fuses.empty()) {
                set_fuses_in_tile(tilemap[{row, aux_col}], aux_fuses);
            }
        }
    }
}

// ============================================================================
// place_dsp - Place a DSP BEL
// Uses shortval table "DSP{mac}"
// ============================================================================
void place_dsp(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

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

    // Parse mac from num (format: "XY" where X=mac, Y=idx)
    int mac = 0;
    if (num.size() >= 2) {
        mac = num[0] - '0';
    } else if (num.size() == 1) {
        mac = num[0] - '0';
    }

    auto params = bel.parameters;
    auto attrs = bel.attributes;

    if (typ != "MULT36X36") {
        // Normal DSP: single set of attributes, single table
        std::set<int64_t> fin_attrs = set_dsp_attrs(db, typ, params, num, attrs);
        std::string table_name = "DSP" + std::to_string(mac);

        // Set fuses in main tile and AUX tiles (col to col+8)
        for (int off = 0; off <= 8; ++off) {
            int64_t c = col + off;
            if (c >= static_cast<int64_t>(db.cols())) break;
            int64_t ttyp = db.get_ttyp(row, c);
            auto ttyp_sv = db.shortval.find(ttyp);
            if (ttyp_sv != db.shortval.end() && ttyp_sv->second.find(table_name) != ttyp_sv->second.end()) {
                std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, table_name);
                set_fuses_in_tile(tilemap[{row, c}], fuses);
            }
        }
    } else {
        // MULT36X36: two macros, two sets of attributes
        auto fin_attrs_vec = set_dsp_mult36x36_attrs(db, typ, params, attrs);

        // Set fuses in main tile and AUX tiles (col to col+8)
        for (int off = 0; off <= 8; ++off) {
            int64_t c = col + off;
            if (c >= static_cast<int64_t>(db.cols())) break;
            int64_t ttyp = db.get_ttyp(row, c);
            auto ttyp_sv = db.shortval.find(ttyp);
            if (ttyp_sv == db.shortval.end()) continue;
            for (int m = 0; m < 2; ++m) {
                std::string table_name = "DSP" + std::to_string(m);
                if (ttyp_sv->second.find(table_name) != ttyp_sv->second.end()) {
                    std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs_vec[m], table_name);
                    set_fuses_in_tile(tilemap[{row, c}], fuses);
                }
            }
        }
    }
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
        // Python: int(attrs['TXCLK_POL']) == 0
        // Value may be "0" or a binary string like "00000000000000000000000000000000"
        if (parse_binary(txclk_it->second) == 0) {
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
void place_iologic(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device, const Netlist& netlist) {
    using namespace attrids;
    (void)device;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

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
    if (bel.type == "IOLOGIC_DUMMY") {
        auto main_cell_it = bel.attributes.find("MAIN_CELL");
        if (main_cell_it != bel.attributes.end()) {
            auto cell_it = netlist.cells.find(main_cell_it->second);
            if (cell_it != netlist.cells.end()) {
                auto fclk_it = cell_it->second.attributes.find("IOLOGIC_FCLK");
                if (fclk_it != cell_it->second.attributes.end()) {
                    if (auto* s = std::get_if<std::string>(&fclk_it->second)) {
                        iologic_fclk = *s;
                    }
                }
            }
        }
    }

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

    if (!in_bounds(row, col, db)) return;

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

    if (!in_bounds(row, col, db)) return;

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
void place_clkdiv(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    // Extract hclk_idx and section_idx from bel.num
    // Pattern: _HCLK{0,1}_SECT{0,1}
    std::regex hclk_re(R"(^_HCLK([01])_SECT([01])$)");
    std::smatch m;
    if (!std::regex_match(bel.num, m, hclk_re)) {
        std::cerr << "Unknown HCLK Bel/HCLK Section: " << bel.type << bel.num << std::endl;
        return;
    }
    std::string hclk_idx = m[1].str();
    std::string section_idx = m[2].str();

    // Get DIV_MODE from parameters (default "2")
    std::string div_mode = "2";
    auto dm_it = bel.parameters.find("DIV_MODE");
    if (dm_it != bel.parameters.end()) {
        div_mode = dm_it->second;
    }

    // Build transformed HCLK attributes matching Python's set_hclk_attrs
    std::map<std::string, std::string> attrs;

    if (bel.type.find("CLKDIV2") != std::string::npos) {
        // CLKDIV2: BK{section_idx}MUX{hclk_idx}_OUTSEL = DIV2
        attrs["BK" + section_idx + "MUX" + hclk_idx + "_OUTSEL"] = "DIV2";
    } else {
        // CLKDIV: HCLKDIV{hclk_idx}_DIV = DIV_MODE
        attrs["HCLKDIV" + hclk_idx + "_DIV"] = div_mode;
        if (section_idx == "1") {
            attrs["HCLKDCS" + hclk_idx + "_SEL"] = "HCLKBK" + section_idx + hclk_idx;
        }
    }

    // Convert to fuse attribute set
    std::set<int64_t> hclk_attrs;
    for (const auto& [attr, val] : attrs) {
        auto attr_it = hclk_attrids.find(attr);
        if (attr_it == hclk_attrids.end()) continue;
        auto val_it = hclk_attrvals.find(val);
        if (val_it == hclk_attrvals.end()) continue;
        add_attr_val(db, "HCLK", hclk_attrs, attr_it->second, val_it->second);
    }

    std::set<Coord> fuses = get_shortval_fuses(db, ttyp, hclk_attrs, "HCLK");

    auto& tile = tilemap[{row, col}];
    set_fuses_in_tile(tile, fuses);

    // GW1NS-4: CLKDIV has auxiliary tiles that also need HCLK fuses
    // Python generates CLKDIV_AUX bels at offset columns
    if (device == "GW1NS-4" && bel.type.find("_AUX") == std::string::npos) {
        // bel.col is 1-based
        int64_t aux_col = -1;
        if (bel.col == 18) {  // 1-based col
            aux_col = (bel.col + 3) - 1;  // 0-based
        } else if (bel.col == 17) {
            aux_col = (bel.col + 1) - 1;  // 0-based
        }
        if (aux_col >= 0 && aux_col < static_cast<int64_t>(db.cols())) {
            int64_t aux_ttyp = db.get_ttyp(row, aux_col);
            std::set<Coord> aux_fuses = get_shortval_fuses(db, aux_ttyp, hclk_attrs, "HCLK");
            if (!aux_fuses.empty()) {
                set_fuses_in_tile(tilemap[{row, aux_col}], aux_fuses);
            }
        }
    }
}

// ============================================================================
// place_dcs - Place a DCS BEL (Dynamic Clock Select)
// ============================================================================
void place_dcs(const Device& db, const BelInfo& bel, Tilemap& tilemap, const std::string& device) {
    using namespace attrids;

    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    if (!in_bounds(row, col, db)) return;

    // Check if DCS_MODE attribute is set
    auto dcs_mode_it = bel.attributes.find("DCS_MODE");
    if (dcs_mode_it == bel.attributes.end()) {
        return;
    }

    const auto& tiledata = db.get_tile(row, col);
    int64_t ttyp = tiledata.ttyp;

    // Spine-to-quadrant mapping: spine -> (quadrant_key, table_idx)
    static const std::map<std::string, std::pair<std::string, std::string>> spine2quadrant = {
        {"SPINE6",  {"1", "DCS6"}},
        {"SPINE7",  {"1", "DCS7"}},
        {"SPINE14", {"2", "DCS6"}},
        {"SPINE15", {"2", "DCS7"}},
        {"SPINE22", {"3", "DCS6"}},
        {"SPINE23", {"3", "DCS7"}},
        {"SPINE30", {"4", "DCS6"}},
        {"SPINE31", {"4", "DCS7"}},
    };

    // Get spine from extra_func[row, col]['dcs'][num]['clkout']
    auto ef_it = db.extra_func.find({row, col});
    if (ef_it == db.extra_func.end()) return;

    auto dcs_it = ef_it->second.find("dcs");
    if (dcs_it == ef_it->second.end()) return;

    int64_t dcs_idx = 0;
    try { dcs_idx = std::stoll(bel.num); } catch (...) { return; }

    // dcs is a dict with integer keys (DCS indices), not a list
    const auto& dcs_obj = dcs_it->second;
    if (dcs_obj.type != msgpack::type::MAP) return;

    // Find the entry with key == dcs_idx
    const msgpack::object* entry_ptr = nullptr;
    for (uint32_t i = 0; i < dcs_obj.via.map.size; ++i) {
        const auto& kv = dcs_obj.via.map.ptr[i];
        int64_t key = 0;
        if (kv.key.type == msgpack::type::POSITIVE_INTEGER) {
            key = static_cast<int64_t>(kv.key.via.u64);
        } else if (kv.key.type == msgpack::type::NEGATIVE_INTEGER) {
            key = kv.key.via.i64;
        } else {
            continue;
        }
        if (key == dcs_idx) {
            entry_ptr = &kv.val;
            break;
        }
    }
    if (!entry_ptr || entry_ptr->type != msgpack::type::MAP) return;

    using msgpack::adaptor::get_map_value;
    std::string spine = get_map_value<std::string>(*entry_ptr, "clkout");

    auto sq_it = spine2quadrant.find(spine);
    if (sq_it == spine2quadrant.end()) return;

    const auto& [q, idx] = sq_it->second;

    // Build DCS attributes: map quadrant key to DCS_MODE value
    std::string dcs_mode = dcs_mode_it->second;
    // Convert to uppercase
    for (auto& c : dcs_mode) c = std::toupper(c);

    auto val_it = dcs_attrvals.find(dcs_mode);
    if (val_it == dcs_attrvals.end()) return;

    auto attr_it = dcs_attrids.find(q);
    if (attr_it == dcs_attrids.end()) return;

    std::set<int64_t> dcs_attrs_set;
    add_attr_val(db, "DCS", dcs_attrs_set, attr_it->second, val_it->second);

    if (device == "GW5A-25A") {
        // GW5A: scan all tiles for matching longfuses table
        std::string dcs_name = "DCS" + std::to_string(dcs_idx + 6);
        for (int64_t r = 0; r < static_cast<int64_t>(db.rows()); ++r) {
            for (int64_t c = 0; c < static_cast<int64_t>(db.cols()); ++c) {
                int64_t t = db.get_ttyp(r, c);
                auto ttyp_it = db.longfuses.find(t);
                if (ttyp_it == db.longfuses.end()) continue;
                if (ttyp_it->second.find(dcs_name) == ttyp_it->second.end()) continue;
                auto& tile = tilemap[{r, c}];
                std::set<Coord> fuses = get_long_fuses(db, t, dcs_attrs_set, idx);
                set_fuses_in_tile(tile, fuses);
            }
        }
    } else {
        std::set<Coord> fuses = get_long_fuses(db, ttyp, dcs_attrs_set, idx);
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

    if (!in_bounds(pip_row, pip_col, db)) return;

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
    using namespace attrids;

    // Check if DHCEN_USED attribute is set
    if (bel.attributes.find("DHCEN_USED") == bel.attributes.end()) {
        return;
    }

    // DHCEN is a control wire - it doesn't have its own fuse, but HCLK
    // tiles along one edge need fuses set to enable the clock enable.
    // Look up the pip info from extra_func.
    int64_t ef_row = bel.row - 1;
    int64_t ef_col = bel.col - 1;

    auto ef_it = db.extra_func.find({ef_row, ef_col});
    if (ef_it == db.extra_func.end()) return;

    auto dhcen_it = ef_it->second.find("dhcen");
    if (dhcen_it == ef_it->second.end()) return;

    // Parse bel.num to get the DHCEN index
    int dhcen_idx = 0;
    try { dhcen_idx = std::stoi(bel.num); } catch (...) { return; }

    // dhcen is a list; get element at dhcen_idx
    const auto& dhcen_obj = dhcen_it->second;
    if (dhcen_obj.type != msgpack::type::ARRAY) return;
    if (static_cast<int>(dhcen_obj.via.array.size) <= dhcen_idx) return;

    const auto& entry = dhcen_obj.via.array.ptr[dhcen_idx];
    if (entry.type != msgpack::type::MAP) return;

    // Get pip: [location, wire, src, side]
    using msgpack::adaptor::get_map_value;
    auto pip = get_map_value<std::vector<std::string>>(entry, "pip");
    if (pip.size() < 4) return;

    std::string wire = pip[1];
    std::string side = pip[3];

    // Map wire name to HCLK attribute
    static const std::map<std::string, std::pair<std::string, std::string>> wire2attr_val = {
        {"HCLK_IN0",       {"HSB0MUX0_HSTOP", "HCLKCIBSTOP0"}},
        {"HCLK_IN1",       {"HSB1MUX0_HSTOP", "HCLKCIBSTOP2"}},
        {"HCLK_IN2",       {"HSB0MUX1_HSTOP", "HCLKCIBSTOP1"}},
        {"HCLK_IN3",       {"HSB1MUX1_HSTOP", "HCLKCIBSTOP3"}},
        {"HCLK_BANK_OUT0", {"BRGMUX0_BRGSTOP", "BRGCIBSTOP0"}},
        {"HCLK_BANK_OUT1", {"BRGMUX1_BRGSTOP", "BRGCIBSTOP1"}},
    };

    auto w2a_it = wire2attr_val.find(wire);
    if (w2a_it == wire2attr_val.end()) return;

    const auto& [attr_name, attr_val_name] = w2a_it->second;
    auto attr_id_it = hclk_attrids.find(attr_name);
    if (attr_id_it == hclk_attrids.end()) return;
    auto val_id_it = hclk_attrvals.find(attr_val_name);
    if (val_id_it == hclk_attrvals.end()) return;

    std::set<int64_t> fin_attrs;
    add_attr_val(db, "HCLK", fin_attrs, attr_id_it->second, val_id_it->second);

    // Set fuses along the edge specified by side
    if (side == "T" || side == "B") {
        int64_t row = (side == "T") ? 0 : static_cast<int64_t>(db.rows()) - 1;
        for (int64_t col = 0; col < static_cast<int64_t>(db.cols()); ++col) {
            int64_t ttyp = db.get_ttyp(row, col);
            std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, "HCLK");
            if (!fuses.empty()) {
                set_fuses_in_tile(tilemap[{row, col}], fuses);
            }
        }
    } else {
        int64_t col = (side == "L") ? 0 : static_cast<int64_t>(db.cols()) - 1;
        for (int64_t row = 0; row < static_cast<int64_t>(db.rows()); ++row) {
            int64_t ttyp = db.get_ttyp(row, col);
            std::set<Coord> fuses = get_shortval_fuses(db, ttyp, fin_attrs, "HCLK");
            if (!fuses.empty()) {
                set_fuses_in_tile(tilemap[{row, col}], fuses);
            }
        }
    }
}

// ============================================================================
// place_dlldly - Place a DLLDLY (Delay Line DLL) BEL
// Mirrors Python set_dlldly_attrs() (gowin_pack.py lines 2717-2744)
// and dispatch (line 3493-3500)
// ============================================================================
void place_dlldly(const Device& db, const BelInfo& bel, Tilemap& tilemap) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;
    if (!in_bounds(row, col, db)) return;

    auto params = bel.parameters;
    // Uppercase param values (like Python attrs_upper)
    for (auto& [k, v] : params) v = to_upper(v);

    std::string dll_insel = get_param(params, "DLL_INSEL", "1");
    std::string dly_sign = get_param(params, "DLY_SIGN", "0");
    std::string dly_adj = get_param(params, "DLY_ADJ",
        "00000000000000000000000000000000");

    if (dll_insel != "1") {
        std::cerr << "Error: DLL_INSEL parameter values other than 1 are not supported" << std::endl;
        return;
    }

    // Build DLLDLY attribute map
    std::map<std::string, std::string> dlldly_attrs;
    dlldly_attrs["ENABLED"] = "ENABLE";
    dlldly_attrs["MODE"] = "NORMAL";

    if (dly_sign == "1") {
        dlldly_attrs["SIGN"] = "NEG";
    }

    // Expand DLY_ADJ: iterate reversed string, set ADJ{i}="1" for each set bit
    for (int i = 0; i < static_cast<int>(dly_adj.size()); ++i) {
        int char_idx = static_cast<int>(dly_adj.size()) - 1 - i;
        if (char_idx >= 0 && dly_adj[char_idx] == '1') {
            dlldly_attrs["ADJ" + std::to_string(i)] = "1";
        }
    }

    // Convert to fuse attribute set
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, val] : dlldly_attrs) {
        auto attr_it = attrids::dlldly_attrids.find(attr);
        if (attr_it == attrids::dlldly_attrids.end()) continue;
        auto val_it = attrids::dlldly_attrvals.find(val);
        if (val_it == attrids::dlldly_attrvals.end()) continue;
        add_attr_val(db, "DLLDLY", fin_attrs, attr_it->second, val_it->second);
    }

    // Get dlldly_fusebels from extra_func[row, col]
    auto ef_it = db.extra_func.find({row, col});
    if (ef_it == db.extra_func.end()) return;

    auto fb_it = ef_it->second.find("dlldly_fusebels");
    if (fb_it == ef_it->second.end()) return;

    const msgpack::object& fusebels_obj = fb_it->second;
    if (fusebels_obj.type != msgpack::type::ARRAY) return;

    // Iterate fusebel locations and set fuses in each tile
    for (uint32_t i = 0; i < fusebels_obj.via.array.size; ++i) {
        const auto& pair = fusebels_obj.via.array.ptr[i];
        if (pair.type != msgpack::type::ARRAY || pair.via.array.size < 2) continue;

        int64_t dlldly_row = 0, dlldly_col = 0;
        if (pair.via.array.ptr[0].type == msgpack::type::POSITIVE_INTEGER)
            dlldly_row = static_cast<int64_t>(pair.via.array.ptr[0].via.u64);
        else if (pair.via.array.ptr[0].type == msgpack::type::NEGATIVE_INTEGER)
            dlldly_row = pair.via.array.ptr[0].via.i64;
        if (pair.via.array.ptr[1].type == msgpack::type::POSITIVE_INTEGER)
            dlldly_col = static_cast<int64_t>(pair.via.array.ptr[1].via.u64);
        else if (pair.via.array.ptr[1].type == msgpack::type::NEGATIVE_INTEGER)
            dlldly_col = pair.via.array.ptr[1].via.i64;

        if (!in_bounds(dlldly_row, dlldly_col, db)) continue;

        int64_t ttyp = db.get_ttyp(dlldly_row, dlldly_col);
        std::string table_name = "DLLDEL" + bel.num;
        std::set<Coord> fuses = get_long_fuses(db, ttyp, fin_attrs, table_name);
        set_fuses_in_tile(tilemap[{dlldly_row, dlldly_col}], fuses);
    }
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

        if (!in_bounds(grid_row, grid_col, db)) continue;

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

// ============================================================================
// set_adc_attrs - Parse ADC parameters and build attribute set
// Mirrors Python set_adc_attrs (gowin_pack.py lines 615-727)
// ============================================================================
static std::set<int64_t> set_adc_attrs(const Device& db,
                                        const std::map<std::string, std::string>& parms) {
    // Default ADC attributes (Python _default_adc_attrs)
    static const std::map<std::string, std::string> default_adc_attrs = {
        {"CLK_SEL", "0"}, {"DIV_CTL", "0"}, {"PHASE_SEL", "0"}, {"UNK0", "101"},
        {"ADC_EN_SEL", "0"}, {"IBIAS_CTL", "1000"}, {"UNK1", "1"}, {"UNK2", "10000"},
        {"CHOP_EN", "1"}, {"GAIN", "100"}, {"CAP_CTL", "0"}, {"BUF_EN", "0"},
        {"CSR_VSEN_CTRL", "0"}, {"CSR_ADC_MODE", "1"}, {"CSR_SAMPLE_CNT_SEL", "0"},
        {"CSR_RATE_CHANGE_CTRL", "0"}, {"CSR_FSCAL", "1011011010"}, // bin(730)
        {"CSR_OFFSET", "10010011100"},  // bin(1180)
    };

    // Merge defaults with user params (user params take precedence)
    std::map<std::string, std::string> adc_inattrs;
    for (const auto& [k, v] : default_adc_attrs) {
        adc_inattrs[k] = v;
    }
    // User params always override defaults
    for (const auto& [k, v] : parms) {
        std::string key = to_upper(k);
        adc_inattrs[key] = v;
    }

    // Parse attributes into (name, value) pairs where value is either int or string enum
    // We'll use a map of attr -> variant<int64_t, string>
    struct AttrVal {
        bool is_string = false;
        int64_t ival = 0;
        std::string sval;
    };
    std::map<std::string, AttrVal> adc_attrs;

    for (const auto& [attr, vl] : adc_inattrs) {
        int64_t val = parse_binary(vl);

        // Skip BUF_BK* attrs
        if (attr.substr(0, 6) == "BUF_BK") continue;

        // Default: store as int
        AttrVal av;
        av.ival = val;

        if (attr == "CLK_SEL") {
            if (val == 1) { av.is_string = true; av.sval = "CLK_CLK"; }
        } else if (attr == "DIV_CTL") {
            if (val) av.ival = (1LL << val);
        } else if (attr == "PHASE_SEL") {
            if (val) { av.is_string = true; av.sval = "PHASE_180"; }
        } else if (attr == "ADC_EN_SEL") {
            if (val == 1) { av.is_string = true; av.sval = "ADC"; }
        } else if (attr == "UNK0") {
            if (val == 0) { av.is_string = true; av.sval = "DISABLE"; }
        } else if (attr == "UNK1") {
            if (val == 1) { av.is_string = true; av.sval = "OFF"; }
        } else if (attr == "UNK2") {
            if (val == 0) { av.is_string = true; av.sval = "DISABLE"; }
        } else if (attr == "IBIAS_CTL") {
            if (val == 0) { av.is_string = true; av.sval = "DISABLE"; }
        } else if (attr == "CHOP_EN") {
            if (val == 1) { av.is_string = true; av.sval = "ON"; }
            else { av.is_string = true; av.sval = "UNKNOWN"; }
        } else if (attr == "GAIN") {
            if (val == 0) { av.is_string = true; av.sval = "DISABLE"; }
        } else if (attr == "CAP_CTL") {
            // keep as int
        } else if (attr == "BUF_EN") {
            // Expand into BUF_i_EN entries
            for (int i = 0; i < 12; i++) {
                if (val & (1LL << i)) {
                    AttrVal buf_av;
                    buf_av.is_string = true;
                    buf_av.sval = "ON";
                    adc_attrs["BUF_" + std::to_string(i) + "_EN"] = buf_av;
                }
            }
            continue;  // don't add BUF_EN itself
        } else if (attr == "CSR_ADC_MODE") {
            if (val == 1) { av.is_string = true; av.sval = "1"; }
            else { av.is_string = true; av.sval = "UNKNOWN"; }
        } else if (attr == "CSR_VSEN_CTRL") {
            if (val == 4) { av.is_string = true; av.sval = "UNK1"; }
            else if (val == 7) { av.is_string = true; av.sval = "UNK0"; }
        } else if (attr == "CSR_SAMPLE_CNT_SEL") {
            if (val > 4) av.ival = 2048;
            else av.ival = (1LL << val) * 64;
        } else if (attr == "CSR_RATE_CHANGE_CTRL") {
            if (val > 4) av.ival = 80;
            else av.ival = (1LL << val) * 4;
        } else if (attr == "CSR_FSCAL") {
            if (val >= 452 && val <= 840) {
                AttrVal fscal1;
                fscal1.ival = val;
                adc_attrs["CSR_FSCAL1"] = fscal1;
            }
            AttrVal fscal0;
            fscal0.ival = val;
            adc_attrs["CSR_FSCAL0"] = fscal0;
            continue;  // don't add CSR_FSCAL itself
        } else if (attr == "CSR_OFFSET") {
            if (val == 0) { av.is_string = true; av.sval = "DISABLE"; }
            else {
                if (val & (1LL << 11)) val -= (1LL << 12);
                av.ival = val;
            }
        }

        adc_attrs[attr] = av;
    }

    // Convert to logicinfo codes
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, av] : adc_attrs) {
        auto aid_it = attrids::adc_attrids.find(attr);
        if (aid_it == attrids::adc_attrids.end()) {
            continue;
        }

        int64_t val_code;
        if (av.is_string) {
            auto vid_it = attrids::adc_attrvals.find(av.sval);
            if (vid_it == attrids::adc_attrvals.end()) {
                continue;
            }
            val_code = vid_it->second;
        } else {
            val_code = av.ival;
        }
        add_attr_val(db, "ADC", fin_attrs, aid_it->second, val_code);
    }

    return fin_attrs;
}

// ============================================================================
// place_adc - Place an ADC BEL
// Mirrors Python place_cells ADC handling (gowin_pack.py lines 3439-3458)
// ============================================================================
void place_adc(const Device& db, const BelInfo& bel, Tilemap& tilemap,
               std::map<int, TileBitmap>* extra_slots) {
    int64_t row = bel.row - 1;
    int64_t col = bel.col - 1;

    // Extract ADC IO locations from attributes
    for (const auto& [attr, val] : bel.attributes) {
        if (attr.substr(0, 7) == "ADC_IO_") {
            // Parse "bus/XcolYrow" format
            std::regex io_re(R"((\d+)/X(\d+)Y(\d+))");
            std::smatch m;
            if (std::regex_match(val, m, io_re)) {
                std::string bus = m[1].str();
                int64_t io_col = std::stoll(m[2].str()) + 1;  // 1-indexed
                int64_t io_row = std::stoll(m[3].str()) + 1;  // 1-indexed
                // Store in adc_iolocs using 0-indexed coords (like Python)
                adc_iolocs[{io_row - 1, io_col - 1}] = bus;
            }
        }
    }

    // Get tile at ADC location
    const auto& tiledata = db.get_tile(row, col);
    auto& tile = tilemap[{row, col}];

    // Parse ADC attributes
    auto adc_attrs = set_adc_attrs(db, bel.parameters);

    // Main grid shortval fuses
    auto sv_it = db.shortval.find(tiledata.ttyp);
    if (sv_it != db.shortval.end() && sv_it->second.count("ADC")) {
        auto bits = get_shortval_fuses(db, tiledata.ttyp, adc_attrs, "ADC");
        set_fuses_in_tile(tile, bits);
    }

    // Slot shortval fuses (ttyp=1026, 8x6 bitmap)
    if (extra_slots) {
        // Get slot_idx from extra_func[row, col]['adc']['slot_idx']
        auto ef_it = db.extra_func.find({row, col});
        if (ef_it != db.extra_func.end()) {
            auto adc_it = ef_it->second.find("adc");
            if (adc_it != ef_it->second.end()) {
                using msgpack::adaptor::get_map_value;
                int64_t slot_idx = get_map_value<int64_t>(adc_it->second, "slot_idx");

                // Create or get 8x6 slot bitmap
                auto& slot_bitmap = (*extra_slots)[static_cast<int>(slot_idx)];
                if (slot_bitmap.empty()) {
                    slot_bitmap = create_tile_bitmap(8, 6);
                }

                auto slot_bits = get_shortval_fuses(db, 1026, adc_attrs, "ADC");
                for (const auto& [sr, sc] : slot_bits) {
                    if (sr >= 0 && sr < 8 && sc >= 0 && sc < 6) {
                        slot_bitmap[sr][sc] = 1;
                    }
                }
            }
        }
    }
}

// ============================================================================
// set_adc_iobuf_fuses - Set IOB fuses for ADC IO pins
// Mirrors Python set_adc_iobuf_fuses (gowin_pack.py lines 4105-4170)
// ============================================================================
void set_adc_iobuf_fuses(const Device& db, Tilemap& tilemap) {
    for (const auto& [ioloc, bus] : adc_iolocs) {
        int64_t row = ioloc.first;
        int64_t col = ioloc.second;
        const auto& tiledata = db.get_tile(row, col);

        // IOBA attributes
        {
            std::set<int64_t> io_attrs;
            // For bus not in "01" (i.e., bus >= "2"), add dynamic ADC attrs
            if (bus != "0" && bus != "1") {
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_ADC_DYN_IN"),
                             attrids::iob_attrvals.at("ENABLE"));
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN70"),
                             attrids::iob_attrvals.at("UNKNOWN"));
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN71"),
                             attrids::iob_attrvals.at("UNKNOWN"));
            }
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IO_TYPE"),
                         attrids::iob_attrvals.at("GW5_ADC_IN"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_ADC_IN"),
                         attrids::iob_attrvals.at("ENABLE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PULLMODE"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("HYSTERESIS"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("CLAMP"),
                         attrids::iob_attrvals.at("OFF"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("OPENDRAIN"),
                         attrids::iob_attrvals.at("OFF"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("DDR_DYNTERM"),
                         attrids::iob_attrvals.at("NA"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IO_BANK"),
                         attrids::iob_attrvals.at("NA"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PADDI"),
                         attrids::iob_attrvals.at("PADDI"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PULL_STRENGTH"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_VCCX_64"),
                         attrids::iob_attrvals.at("3.3"));

            auto bits = get_longval_fuses(db, tiledata.ttyp, io_attrs, "IOBA");
            set_fuses_in_tile(tilemap[{row, col}], bits);
        }

        // IOBB attributes
        {
            // Determine fuse location (may have offset for IOBB)
            int64_t fuse_row = row;
            int64_t fuse_col = col;
            auto iobb_it = tiledata.bels.find("IOBB");
            if (iobb_it != tiledata.bels.end() && iobb_it->second.fuse_cell_offset) {
                fuse_row += iobb_it->second.fuse_cell_offset->first;
                fuse_col += iobb_it->second.fuse_cell_offset->second;
            }
            const auto& fuse_tiledata = db.get_tile(fuse_row, fuse_col);

            std::set<int64_t> io_attrs;
            if (bus == "0" || bus == "1") {
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN60"),
                             attrids::iob_attrvals.at("ON"));
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN61"),
                             attrids::iob_attrvals.at("ON"));
            } else {
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_ADC_DYN_IN"),
                             attrids::iob_attrvals.at("ENABLE"));
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN70"),
                             attrids::iob_attrvals.at("UNKNOWN"));
                add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_UNKNOWN71"),
                             attrids::iob_attrvals.at("UNKNOWN"));
            }
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IO_TYPE"),
                         attrids::iob_attrvals.at("GW5_ADC_IN"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_ADC_IN"),
                         attrids::iob_attrvals.at("ENABLE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PULLMODE"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("HYSTERESIS"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("CLAMP"),
                         attrids::iob_attrvals.at("OFF"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("OPENDRAIN"),
                         attrids::iob_attrvals.at("OFF"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("DDR_DYNTERM"),
                         attrids::iob_attrvals.at("NA"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IO_BANK"),
                         attrids::iob_attrvals.at("NA"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PADDI"),
                         attrids::iob_attrvals.at("PADDI"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("PULL_STRENGTH"),
                         attrids::iob_attrvals.at("NONE"));
            add_attr_val(db, "IOB", io_attrs, attrids::iob_attrids.at("IOB_GW5_VCCX_64"),
                         attrids::iob_attrvals.at("3.3"));

            auto bits = get_longval_fuses(db, fuse_tiledata.ttyp, io_attrs, "IOBB");
            set_fuses_in_tile(tilemap[{fuse_row, fuse_col}], bits);
        }
    }
}

} // namespace apycula
