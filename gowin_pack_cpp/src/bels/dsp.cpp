// bels/dsp.cpp - DSP type-specific attribute handlers
// Ported from apycula/gowin_pack.py set_dsp_attrs and related functions
#include "../place.hpp"
#include "../fuses.hpp"
#include "../attrids.hpp"
#include "../utils.hpp"
#include <iostream>
#include <sstream>
#include <algorithm>
#include <cmath>

namespace apycula {

// ============================================================================
// Helpers
// ============================================================================

// Ensure params have default "0" for missing register parameters
static void set_dsp_regs_0(std::map<std::string, std::string>& params, const std::vector<std::string>& names) {
    for (const auto& n : names) {
        if (params.find(n) == params.end()) params[n] = "0";
    }
}

// CE/CLK/RESET value computation from binary attribute strings
static std::string get_ce_val(const std::map<std::string, std::string>& attrs) {
    auto it = attrs.find("CE");
    if (it != attrs.end() && parse_binary(it->second) != 0)
        return "CEIN" + std::to_string(parse_binary(it->second));
    return "UNKNOWN";
}

static std::string get_clk_val(const std::map<std::string, std::string>& attrs) {
    auto it = attrs.find("CLK");
    if (it != attrs.end() && parse_binary(it->second) != 0)
        return "CLKIN" + std::to_string(parse_binary(it->second));
    return "UNKNOWN";
}

static std::string get_reset_val(const std::map<std::string, std::string>& attrs) {
    auto it = attrs.find("RESET");
    if (it != attrs.end() && parse_binary(it->second) != 0)
        return "RSTIN" + std::to_string(parse_binary(it->second));
    return "UNKNOWN";
}

using DA = std::map<std::string, std::string>;

// _01LH = [(0, 'L'), (1, 'H')]
static const std::vector<std::pair<int,char>> _01LH = {{0,'L'},{1,'H'}};
// _ABLH = [('A','L'),('A','H'),('B','L'),('B','H')]
static const std::vector<std::pair<char,char>> _ABLH = {{'A','L'},{'A','H'},{'B','L'},{'B','H'}};

// ============================================================================
// set_multalu18x18_attrs
// ============================================================================
static void set_multalu18x18_attrs(const Device& /*db*/, const std::string& /*typ*/,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int /*mac*/)
{
    attrs_upper(attrs);
    std::string ce_val = get_ce_val(attrs);
    std::string clk_val = get_clk_val(attrs);
    std::string reset_val = get_reset_val(attrs);

    int mode = static_cast<int>(parse_binary(get_param(params, "MULTALU18X18_MODE", "0")));
    int mode_01 = (mode != 2) ? 1 : 0;
    std::string accload = attrs["NET_ACCLOAD"];

    da["RCISEL_3"] = "1";
    if (mode_01) da["RCISEL_1"] = "1";

    da["OR2CIB_EN0L_0"] = "ENABLE";
    da["OR2CIB_EN0H_1"] = "ENABLE";
    da["OR2CIB_EN1L_2"] = "ENABLE";
    da["OR2CIB_EN1H_3"] = "ENABLE";

    if (params.count("B_ADD_SUB") && parse_binary(params["B_ADD_SUB"]) == 1)
        da["OPCD_7"] = "1";

    da["ALU_EN"] = "ENABLE";
    da["OPCD_5"] = "1";
    da["OPCD_9"] = "1";
    for (int i : {5, 6}) {
        da["CINBY_" + std::to_string(i)] = "ENABLE";
        da["CINNS_" + std::to_string(i)] = "ENABLE";
        da["CPRBY_" + std::to_string(i)] = "ENABLE";
        da["CPRNS_" + std::to_string(i)] = "ENABLE";
    }

    if (attrs.count("USE_CASCADE_IN")) { da["CSGIN_EXT"] = "ENABLE"; da["CSIGN_PRE"] = "ENABLE"; }
    if (attrs.count("USE_CASCADE_OUT")) da["OR2CASCADE_EN"] = "ENABLE";

    if (mode_01) {
        da["OPCD_2"] = "1";
        if (accload == "VCC") {
            da["OR2CASCADE_EN"] = "ENABLE";
        } else if (accload == "GND") {
            da["OPCD_0"] = "1"; da["OPCD_1"] = "1";
        } else {
            da["OPCDDYN_0"] = "ENABLE"; da["OPCDDYN_1"] = "ENABLE";
            da["OR2CASCADE_EN"] = "ENABLE";
            da["OPCDDYN_INV_0"] = "ENABLE"; da["OPCDDYN_INV_1"] = "ENABLE";
        }
        if (mode == 0) {
            da["OPCD_4"] = "1";
            if (params.count("C_ADD_SUB") && parse_binary(params["C_ADD_SUB"]) == 1)
                da["OPCD_8"] = "1";
        }
    } else {
        da["OPCD_0"] = "1"; da["OPCD_3"] = "1";
    }

    set_dsp_regs_0(params, {"AREG","BREG","CREG","DREG","DSIGN_REG","ASIGN_REG","BSIGN_REG","PIPE_REG","OUT_REG"});

    for (const auto& [parm, val] : params) {
        if (parm == "AREG") {
            if (val == "0") {
                for (auto [i,h] : _01LH) {
                    da["IRBY_IREG" + std::to_string(mode_01) + "A" + h + "_" + std::to_string(4*mode_01+i)] = "ENABLE";
                    da["IRNS_IREG" + std::to_string(mode_01) + "A" + h + "_" + std::to_string(4*mode_01+i)] = "ENABLE";
                }
            } else {
                for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_REGMA"+std::to_string(mode_01)] = ce_val;
                    da[std::string("CLK")+h+"MUX_REGMA"+std::to_string(mode_01)] = clk_val;
                    da[std::string("RST")+h+"MUX_REGMA"+std::to_string(mode_01)] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'})
                        da[std::string("RSTGEN")+h+"MUX_REGMA"+std::to_string(mode_01)] = "SYNC";
            }
        }
        if (parm == "BREG") {
            if (val == "0") {
                for (auto [i,h] : _01LH) {
                    da["IRBY_IREG" + std::to_string(mode_01) + "B" + h + "_" + std::to_string(4*mode_01+2+i)] = "ENABLE";
                    da["IRNS_IREG" + std::to_string(mode_01) + "B" + h + "_" + std::to_string(4*mode_01+2+i)] = "ENABLE";
                }
            } else {
                for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_REGMB"+std::to_string(mode_01)] = ce_val;
                    da[std::string("CLK")+h+"MUX_REGMB"+std::to_string(mode_01)] = clk_val;
                    da[std::string("RST")+h+"MUX_REGMB"+std::to_string(mode_01)] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'})
                        da[std::string("RSTGEN")+h+"MUX_REGMB"+std::to_string(mode_01)] = "SYNC";
            }
        }
        if (parm == "CREG" && mode_01) {
            if (val == "0") {
                for (auto [i,h] : _01LH) da[std::string("CIR_BYP")+h+"_"+std::to_string(i)] = "1";
            } else {
                for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_CREG"] = ce_val;
                    da[std::string("CLK")+h+"MUX_CREG"] = clk_val;
                    da[std::string("RST")+h+"MUX_CREG"] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGC0"] = "SYNC";
            }
        }
        if (parm == "DREG" && !mode_01) {
            if (val == "0") {
                da["CIR_BYPH_1"] = "1";
                int ii = 4;
                for (auto [a,h] : _ABLH) {
                    da[std::string("IRBY_IREG1")+a+h+"_"+std::to_string(ii)] = "ENABLE";
                    da[std::string("IRNS_IREG1")+a+h+"_"+std::to_string(ii)] = "ENABLE";
                    ii++;
                }
            } else {
                da["CEHMUX_CREG"] = ce_val; da["CLKHMUX_CREG"] = clk_val; da["RSTHMUX_CREG"] = reset_val;
                for (auto [a,h] : _ABLH) {
                    da[std::string("CE")+h+"MUX_REGM"+a+"1"] = ce_val;
                    da[std::string("CLK")+h+"MUX_REGM"+a+"1"] = clk_val;
                    da[std::string("RST")+h+"MUX_REGM"+a+"1"] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") {
                    da["RSTGENHMUX_REGC0"] = "SYNC";
                    for (auto [a,h] : _ABLH)
                        da[std::string("RSTGEN")+h+"MUX_REGM"+a+"1"] = "SYNC";
                }
            }
        }
        if (parm == "ASIGN_REG") {
            if (val == "0") {
                da["CINNS_"+std::to_string(3*mode_01)] = "ENABLE";
                da["CINBY_"+std::to_string(3*mode_01)] = "ENABLE";
            } else {
                da["CEMUX_ASIGN"+std::to_string(mode_01)+"1"] = ce_val;
                da["CLKMUX_ASIGN"+std::to_string(mode_01)+"1"] = clk_val;
                da["RSTMUX_ASIGN"+std::to_string(mode_01)+"1"] = reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_ASIGN"+std::to_string(mode_01)+"1"] = "SYNC";
            }
        }
        if (parm == "BSIGN_REG") {
            if (val == "0") {
                da["CINNS_"+std::to_string(1+3*mode_01)] = "ENABLE";
                da["CINBY_"+std::to_string(1+3*mode_01)] = "ENABLE";
            } else {
                da["CEMUX_BSIGN"+std::to_string(mode_01)+"1"] = ce_val;
                da["CLKMUX_BSIGN"+std::to_string(mode_01)+"1"] = clk_val;
                da["RSTMUX_BSIGN"+std::to_string(mode_01)+"1"] = reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_BSIGN"+std::to_string(mode_01)+"1"] = "SYNC";
            }
        }
        if (parm == "DSIGN_REG" && !mode_01) {
            if (val == "0") {
                da["CINNS_4"] = "ENABLE"; da["CINBY_4"] = "ENABLE";
            } else {
                da["CEMUX_BSIGN11"] = ce_val; da["CLKMUX_BSIGN11"] = clk_val; da["RSTMUX_BSIGN11"] = reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_BSIGN11"] = "SYNC";
            }
            if (params.count("PIPE_REG")) {
                if (params["PIPE_REG"] == "0") {
                    da["CPRNS_4"] = "ENABLE"; da["CPRBY_4"] = "ENABLE";
                } else {
                    da["CLK_BSIGN12"] = clk_val; da["RST_BSIGN12"] = reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                        da["RSTGENMUX_BSIGN12"] = "SYNC";
                }
            }
        }
        if (parm == "PIPE_REG") {
            if (val == "0") {
                da["CPRNS_"+std::to_string(3*mode_01)] = "ENABLE";
                da["CPRBY_"+std::to_string(3*mode_01)] = "ENABLE";
                da["CPRNS_"+std::to_string(1+3*mode_01)] = "ENABLE";
                da["CPRBY_"+std::to_string(1+3*mode_01)] = "ENABLE";
                for (auto [i,h] : _01LH) {
                    da["PPREG"+std::to_string(mode_01)+"_NS"+h+"_"+std::to_string(2*mode_01+i)] = "ENABLE";
                    da["PPREG"+std::to_string(mode_01)+"_BYP"+h+"_"+std::to_string(2*mode_01+i)] = "ENABLE";
                }
            } else {
                for (char i : {'A','B'}) {
                    da[std::string("CEMUX_")+i+"SIGN"+std::to_string(1-mode_01)+"2"] = ce_val;
                    da[std::string("CLKMUX_")+i+"SIGN"+std::to_string(1-mode_01)+"2"] = clk_val;
                    da[std::string("RSTMUX_")+i+"SIGN"+std::to_string(1-mode_01)+"2"] = reset_val;
                }
                for (char i : {'L','H'}) {
                    da[std::string("CE")+i+"MUX_REGP"+std::to_string(1-mode_01)] = ce_val;
                    da[std::string("CLK")+i+"MUX_REGP"+std::to_string(1-mode_01)] = clk_val;
                    da[std::string("RST")+i+"MUX_REGP"+std::to_string(1-mode_01)] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") {
                    da["RSTGENMUX_ASIGN"+std::to_string(1-mode_01)+"2"] = "SYNC";
                    da["RSTGENMUX_BSIGN"+std::to_string(1-mode_01)+"2"] = "SYNC";
                    da["RSTGENLMUX_REGP"+std::to_string(1-mode_01)] = "SYNC";
                    da["RSTGENHMUX_REGP"+std::to_string(1-mode_01)] = "SYNC";
                }
            }
        }
        if (parm == "OUT_REG") {
            if (val == "0") {
                for (int i = 0; i < 2; i++) {
                    da["OREG"+std::to_string(i)+"_NSL_"+std::to_string(2*i)] = "ENABLE";
                    da["OREG"+std::to_string(i)+"_BYPL_"+std::to_string(2*i)] = "ENABLE";
                    da["OREG"+std::to_string(i)+"_NSH_"+std::to_string(2*i+1)] = "ENABLE";
                    da["OREG"+std::to_string(i)+"_BYPH_"+std::to_string(2*i+1)] = "ENABLE";
                }
            } else {
                for (int i = 0; i < 2; i++)
                    for (char h : {'L','H'}) {
                        da[std::string("CE")+h+"MUX_OREG"+std::to_string(i)] = ce_val;
                        da[std::string("CLK")+h+"MUX_OREG"+std::to_string(i)] = clk_val;
                        da[std::string("RST")+h+"MUX_OREG"+std::to_string(i)] = reset_val;
                    }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) {
                        da[std::string("RSTGEN")+h+"MUX_OREG0"] = "SYNC";
                        da[std::string("RSTGEN")+h+"MUX_OREG1"] = "SYNC";
                    }
            }
        }
        if (parm == "ACCLOAD_REG0") {
            if (val == "0") { da["CINNS_2"] = "ENABLE"; da["CINBY_2"] = "ENABLE"; }
            else {
                da["CEMUX_ALUSEL1"] = ce_val; da["CLKMUX_ALUSEL1"] = clk_val; da["RSTMUX_ALUSEL1"] = reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_ALUSEL1"] = "SYNC";
            }
        }
        if (parm == "ACCLOAD_REG1") {
            if (val == "0") { da["CPRNS_2"] = "ENABLE"; da["CPRBY_2"] = "ENABLE"; }
            else {
                da["CEMUX_ALUSEL2"] = ce_val; da["CLKMUX_ALUSEL2"] = clk_val; da["RSTMUX_ALUSEL2"] = reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_ALUSEL2"] = "SYNC";
            }
        }
    }
}

// ============================================================================
// set_multaddalu18x18_attrs
// ============================================================================
static void set_multaddalu18x18_attrs(const Device& /*db*/, const std::string& /*typ*/,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int /*mac*/)
{
    attrs_upper(attrs);
    std::string ce_val = get_ce_val(attrs), clk_val = get_clk_val(attrs), reset_val = get_reset_val(attrs);
    int mode = static_cast<int>(parse_binary(get_param(params, "MULTADDALU18X18_MODE", "0")));
    std::string accload = attrs["NET_ACCLOAD"];

    if (mode == 0) { da["RCISEL_3"] = "1"; da["RCISEL_1"] = "1"; }
    da["OR2CIB_EN0L_0"]="ENABLE"; da["OR2CIB_EN0H_1"]="ENABLE";
    da["OR2CIB_EN1L_2"]="ENABLE"; da["OR2CIB_EN1H_3"]="ENABLE";

    if (params.count("B_ADD_SUB") && parse_binary(params["B_ADD_SUB"]) == 1) da["OPCD_7"] = "1";
    if (attrs.count("USE_CASCADE_IN")) { da["CSGIN_EXT"]="ENABLE"; da["CSIGN_PRE"]="ENABLE"; }
    if (attrs.count("USE_CASCADE_OUT")) da["OR2CASCADE_EN"] = "ENABLE";

    da["ALU_EN"]="ENABLE"; da["OPCD_0"]="1"; da["OPCD_2"]="1"; da["OPCD_9"]="1";
    for (int i : {5,6}) {
        da["CINBY_"+std::to_string(i)]="ENABLE"; da["CINNS_"+std::to_string(i)]="ENABLE";
        da["CPRBY_"+std::to_string(i)]="ENABLE"; da["CPRNS_"+std::to_string(i)]="ENABLE";
    }

    if (mode == 0) { da["OPCD_4"]="1"; da["OPCD_5"]="1";
        if (params.count("C_ADD_SUB") && parse_binary(params["C_ADD_SUB"]) == 1) da["OPCD_8"]="1";
    } else if (mode == 2) { da["OPCD_5"]="1";
    } else {
        if (accload == "VCC") { da["OPCD_4"]="1"; da["OPCD_6"]="1"; da["OR2CASCADE_EN"]="ENABLE"; }
        else if (accload != "GND") { da["OPCDDYN_4"]="ENABLE"; da["OPCDDYN_6"]="ENABLE"; da["OR2CASCADE_EN"]="ENABLE"; }
    }

    // NET_ASEL/BSEL
    if (attrs["NET_ASEL0"] == "VCC") da["AIRMUX1_0"] = "ENABLE";
    else if (!attrs["NET_ASEL0"].empty() && attrs["NET_ASEL0"] != "GND") da["AIRMUX1_SEL_0"] = "ENABLE";
    if (attrs["NET_ASEL1"] == "VCC") da["AIRMUX1_1"] = "ENABLE";
    else if (!attrs["NET_ASEL1"].empty() && attrs["NET_ASEL1"] != "GND") da["AIRMUX1_SEL_1"] = "ENABLE";
    if (attrs["NET_BSEL0"] == "VCC") da["BIRMUX1_0"] = "ENABLE";
    else if (!attrs["NET_BSEL0"].empty() && attrs["NET_BSEL0"] != "GND") {
        da["BIRMUX0_0"]="ENABLE"; da["BIRMUX0_1"]="ENABLE"; da["BIRMUX1_0"]="ENABLE"; da["BIRMUX1_1"]="ENABLE";
    }
    if (attrs["NET_BSEL1"] == "VCC") da["BIRMUX1_2"] = "ENABLE";
    else if (!attrs["NET_BSEL1"].empty() && attrs["NET_BSEL1"] != "GND") { da["BIRMUX1_2"]="ENABLE"; da["BIRMUX1_3"]="ENABLE"; }

    da["MATCH_SHFEN"]="ENABLE";
    da["IRASHFEN_0"]="1"; da["IRASHFEN_1"]="1"; da["IRBSHFEN_0"]="1"; da["IRBSHFEN_1"]="1";

    set_dsp_regs_0(params, {"A0REG","A1REG","B0REG","B1REG","CREG","PIPE0_REG","PIPE1_REG","OUT_REG",
                            "ASIGN0_REG","ASIGN1_REG","ACCLOAD_REG0","ACCLOAD_REG1","BSIGN0_REG","BSIGN1_REG","SOA_REG"});

    for (const auto& [parm, val] : params) {
        if (parm == "A0REG" || parm == "A1REG") {
            int k = static_cast<int>(parse_binary(std::string(1, parm[1])));
            if (val == "0") {
                for (auto [i,h] : _01LH) {
                    da["IRBY_IREG"+std::to_string(k)+"A"+h+"_"+std::to_string(4*k+i)] = "ENABLE";
                    da["IRNS_IREG"+std::to_string(k)+"A"+h+"_"+std::to_string(4*k+i)] = "ENABLE";
                }
            } else {
                for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_REGMA"+std::to_string(k)] = ce_val;
                    da[std::string("CLK")+h+"MUX_REGMA"+std::to_string(k)] = clk_val;
                    da[std::string("RST")+h+"MUX_REGMA"+std::to_string(k)] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGMA"+std::to_string(k)] = "SYNC";
            }
        }
        if (parm == "B0REG" || parm == "B1REG") {
            int k = static_cast<int>(parse_binary(std::string(1, parm[1])));
            if (val == "0") {
                for (auto [i,h] : _01LH) {
                    da["IRBY_IREG"+std::to_string(k)+"B"+h+"_"+std::to_string(4*k+2+i)] = "ENABLE";
                    da["IRNS_IREG"+std::to_string(k)+"B"+h+"_"+std::to_string(4*k+2+i)] = "ENABLE";
                }
            } else {
                for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_REGMB"+std::to_string(k)] = ce_val;
                    da[std::string("CLK")+h+"MUX_REGMB"+std::to_string(k)] = clk_val;
                    da[std::string("RST")+h+"MUX_REGMB"+std::to_string(k)] = reset_val;
                }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGMB"+std::to_string(k)] = "SYNC";
            }
        }
        if (parm == "CREG" && mode == 0) {
            if (val == "0") { for (auto [i,h] : _01LH) da[std::string("CIR_BYP")+h+"_"+std::to_string(i)] = "1"; }
            else {
                for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_CREG"]=ce_val; da[std::string("CLK")+h+"MUX_CREG"]=clk_val; da[std::string("RST")+h+"MUX_CREG"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGC0"] = "SYNC";
            }
        }
        if (parm == "ASIGN0_REG" || parm == "ASIGN1_REG") {
            int k = static_cast<int>(parse_binary(std::string(1, parm[5])));
            if (val == "0") { da["CINNS_"+std::to_string(3*k)]="ENABLE"; da["CINBY_"+std::to_string(3*k)]="ENABLE"; }
            else {
                da["CEMUX_ASIGN"+std::to_string(k)+"1"]=ce_val; da["CLKMUX_ASIGN"+std::to_string(k)+"1"]=clk_val; da["RSTMUX_ASIGN"+std::to_string(k)+"1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_ASIGN"+std::to_string(k)+"1"] = "SYNC";
            }
        }
        if (parm == "BSIGN0_REG" || parm == "BSIGN1_REG") {
            int k = static_cast<int>(parse_binary(std::string(1, parm[5])));
            if (val == "0") { da["CINNS_"+std::to_string(1+3*k)]="ENABLE"; da["CINBY_"+std::to_string(1+3*k)]="ENABLE"; }
            else {
                da["CEMUX_BSIGN"+std::to_string(k)+"1"]=ce_val; da["CLKMUX_BSIGN"+std::to_string(k)+"1"]=clk_val; da["RSTMUX_BSIGN"+std::to_string(k)+"1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    da["RSTGENMUX_BSIGN"+std::to_string(k)+"1"] = "SYNC";
            }
        }
        if (parm == "PIPE0_REG" || parm == "PIPE1_REG") {
            int k = static_cast<int>(parse_binary(std::string(1, parm[4])));
            if (val == "0") {
                da["CPRNS_"+std::to_string(3*k)]="ENABLE"; da["CPRBY_"+std::to_string(3*k)]="ENABLE";
                da["CPRNS_"+std::to_string(1+3*k)]="ENABLE"; da["CPRBY_"+std::to_string(1+3*k)]="ENABLE";
                for (auto [i,h] : _01LH) {
                    da["PPREG"+std::to_string(k)+"_NS"+h+"_"+std::to_string(2*k+i)] = "ENABLE";
                    da["PPREG"+std::to_string(k)+"_BYP"+h+"_"+std::to_string(2*k+i)] = "ENABLE";
                }
            } else {
                for (char i : {'A','B'}) { da[std::string("CEMUX_")+i+"SIGN"+std::to_string(k)+"2"]=ce_val; da[std::string("CLKMUX_")+i+"SIGN"+std::to_string(k)+"2"]=clk_val; da[std::string("RSTMUX_")+i+"SIGN"+std::to_string(k)+"2"]=reset_val; }
                for (char i : {'L','H'}) { da[std::string("CE")+i+"MUX_REGP"+std::to_string(k)]=ce_val; da[std::string("CLK")+i+"MUX_REGP"+std::to_string(k)]=clk_val; da[std::string("RST")+i+"MUX_REGP"+std::to_string(k)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") {
                    da["RSTGENMUX_ASIGN"+std::to_string(k)+"2"]="SYNC"; da["RSTGENMUX_BSIGN"+std::to_string(k)+"2"]="SYNC";
                    da["RSTGENLMUX_REGP"+std::to_string(k)]="SYNC"; da["RSTGENHMUX_REGP"+std::to_string(k)]="SYNC";
                }
            }
        }
        if (parm == "SOA_REG") {
            if (val == "0") {
                da["IRBY_IRMATCHH_9"]="ENABLE"; da["IRNS_IRMATCHH_9"]="ENABLE";
                da["IRBY_IRMATCHL_8"]="ENABLE"; da["IRNS_IRMATCHL_8"]="ENABLE";
            } else {
                for (char h : {'L','H'}) { std::string p = (h=='L')?"CEL":"CEH"; da[std::string(1,(h=='L')?'C':'C')+std::string("E")+h+"MUX_REGSD"]=ce_val; da[std::string("CLK")+h+"MUX_REGSD"]=clk_val; da[std::string("RST")+h+"MUX_REGSD"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") { da["RSTGENHMUX_REGSD"]="SYNC"; da["RSTGENLMUX_REGSD"]="SYNC"; }
            }
        }
        if (parm == "OUT_REG") {
            if (val == "0") {
                for (int k = 0; k < 2; k++) {
                    da["OREG"+std::to_string(k)+"_NSL_"+std::to_string(2*k)]="ENABLE"; da["OREG"+std::to_string(k)+"_BYPL_"+std::to_string(2*k)]="ENABLE";
                    da["OREG"+std::to_string(k)+"_NSH_"+std::to_string(2*k+1)]="ENABLE"; da["OREG"+std::to_string(k)+"_BYPH_"+std::to_string(2*k+1)]="ENABLE";
                }
            } else {
                for (int k = 0; k < 2; k++) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_OREG"+std::to_string(k)]=ce_val; da[std::string("CLK")+h+"MUX_OREG"+std::to_string(k)]=clk_val; da[std::string("RST")+h+"MUX_OREG"+std::to_string(k)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC")
                    for (char h : {'L','H'}) { da[std::string("RSTGEN")+h+"MUX_OREG0"]="SYNC"; da[std::string("RSTGEN")+h+"MUX_OREG1"]="SYNC"; }
            }
        }
        if (parm == "ACCLOAD_REG0") {
            if (val == "0") { da["CINNS_2"]="ENABLE"; da["CINBY_2"]="ENABLE"; }
            else { da["CEMUX_ALUSEL1"]=ce_val; da["CLKMUX_ALUSEL1"]=clk_val; da["RSTMUX_ALUSEL1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") da["RSTGENMUX_ALUSEL1"]="SYNC"; }
        }
        if (parm == "ACCLOAD_REG1") {
            if (val == "0") { da["CPRNS_2"]="ENABLE"; da["CPRBY_2"]="ENABLE"; }
            else { da["CEMUX_ALUSEL2"]=ce_val; da["CLKMUX_ALUSEL2"]=clk_val; da["RSTMUX_ALUSEL2"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") da["RSTGENMUX_ALUSEL2"]="SYNC"; }
        }
    }
}

// ============================================================================
// set_multalu36x18_attrs
// ============================================================================
static void set_multalu36x18_attrs(const Device& /*db*/, const std::string& typ,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int mac)
{
    attrs_upper(attrs);
    std::string ce_val = get_ce_val(attrs), clk_val = get_clk_val(attrs), reset_val = get_reset_val(attrs);
    int mode = static_cast<int>(parse_binary(get_param(params, "MULTALU36X18_MODE", "0")));
    std::string accload = attrs["NET_ACCLOAD"];

    da["RCISEL_1"]="1"; da["RCISEL_3"]="1";
    da["OR2CIB_EN0L_0"]="ENABLE"; da["OR2CIB_EN0H_1"]="ENABLE";
    da["OR2CIB_EN1L_2"]="ENABLE"; da["OR2CIB_EN1H_3"]="ENABLE";
    da["ALU_EN"]="ENABLE";
    for (int i : {5,6}) { da["CINBY_"+std::to_string(i)]="ENABLE"; da["CINNS_"+std::to_string(i)]="ENABLE"; da["CPRBY_"+std::to_string(i)]="ENABLE"; da["CPRNS_"+std::to_string(i)]="ENABLE"; }

    if (attrs.count("USE_CASCADE_IN")) { da["CSGIN_EXT"]="ENABLE"; da["CSIGN_PRE"]="ENABLE"; }
    if (attrs.count("USE_CASCADE_OUT")) da["OR2CASCADE_EN"]="ENABLE";

    da["OPCD_0"]="1"; da["OPCD_9"]="1";
    if (mode == 0) { da["OPCD_4"]="1"; da["OPCD_5"]="1";
        if (params.count("C_ADD_SUB") && parse_binary(params["C_ADD_SUB"]) == 1) da["OPCD_8"]="1";
    } else if (mode == 2) { da["OPCD_5"]="1";
    } else {
        if (accload == "VCC") { da["OPCD_4"]="1"; da["OPCD_6"]="1"; da["OR2CASCADE_EN"]="ENABLE"; }
        else if (accload != "GND") { da["OPCDDYN_4"]="ENABLE"; da["OPCDDYN_6"]="ENABLE"; da["OR2CASCADE_EN"]="ENABLE"; }
    }

    set_dsp_regs_0(params, {"AREG","BREG","CREG","PIPE_REG","OUT_REG","ASIGN_REG","BSIGN_REG","ACCLOAD_REG0","ACCLOAD_REG1"});
    for (const auto& [parm, val] : params) {
        if (parm == "AREG") {
            if (val == "0") { for (int k = 0; k < 2; k++) for (auto [i,h] : _01LH) { da["IRBY_IREG"+std::to_string(k)+"A"+h+"_"+std::to_string(4*k+i)]="ENABLE"; da["IRNS_IREG"+std::to_string(k)+"A"+h+"_"+std::to_string(4*k+i)]="ENABLE"; } }
            else { for (int k = 0; k < 2; k++) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_REGMA"+std::to_string(k)]=ce_val; da[std::string("CLK")+h+"MUX_REGMA"+std::to_string(k)]=clk_val; da[std::string("RST")+h+"MUX_REGMA"+std::to_string(k)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (int k = 0; k < 2; k++) for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGMA"+std::to_string(k)]="SYNC"; }
        }
        if (parm == "BREG") {
            if (val == "0") { for (int k = 0; k < 2; k++) for (auto [i,h] : _01LH) { da["IRBY_IREG"+std::to_string(k)+"B"+h+"_"+std::to_string(4*k+2+i)]="ENABLE"; da["IRNS_IREG"+std::to_string(k)+"B"+h+"_"+std::to_string(4*k+2+i)]="ENABLE"; } }
            else { for (int k = 0; k < 2; k++) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_REGMB"+std::to_string(k)]=ce_val; da[std::string("CLK")+h+"MUX_REGMB"+std::to_string(k)]=clk_val; da[std::string("RST")+h+"MUX_REGMB"+std::to_string(k)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (int k = 0; k < 2; k++) for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGMB"+std::to_string(k)]="SYNC"; }
        }
        if (parm == "CREG") {
            if (val == "0") { for (auto [i,h] : _01LH) da[std::string("CIR_BYP")+h+"_"+std::to_string(i)]="1"; }
            else { for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_CREG"]=ce_val; da[std::string("CLK")+h+"MUX_CREG"]=clk_val; da[std::string("RST")+h+"MUX_CREG"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGC0"]="SYNC"; }
        }
        if (parm == "ASIGN_REG") {
            if (val == "0") { for (int k = 0; k < 2; k++) { da["CINNS_"+std::to_string(3*k)]="ENABLE"; da["CINBY_"+std::to_string(3*k)]="ENABLE"; } }
            else { for (int k = 0; k < 2; k++) { da["CEMUX_ASIGN"+std::to_string(k)+"1"]=ce_val; da["CLKMUX_ASIGN"+std::to_string(k)+"1"]=clk_val; da["RSTMUX_ASIGN"+std::to_string(k)+"1"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (int k = 0; k < 2; k++) da["RSTGENMUX_ASIGN"+std::to_string(k)+"1"]="SYNC"; }
        }
        if (parm == "BSIGN_REG") {
            if (val == "0") { for (int k = 0; k < 2; k++) { da["CINNS_"+std::to_string(1+3*k)]="ENABLE"; da["CINBY_"+std::to_string(1+3*k)]="ENABLE"; } }
            else { for (int k = 0; k < 2; k++) { da["CEMUX_BSIGN"+std::to_string(k)+"1"]=ce_val; da["CLKMUX_BSIGN"+std::to_string(k)+"1"]=clk_val; da["RSTMUX_BSIGN"+std::to_string(k)+"1"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (int k = 0; k < 2; k++) da["RSTGENMUX_BSIGN"+std::to_string(k)+"1"]="SYNC"; }
        }
        if (parm == "PIPE_REG") {
            if (val == "0") {
                for (int k = 0; k < 2; k++) { da["CPRNS_"+std::to_string(3*k)]="ENABLE"; da["CPRBY_"+std::to_string(3*k)]="ENABLE"; da["CPRNS_"+std::to_string(1+3*k)]="ENABLE"; da["CPRBY_"+std::to_string(1+3*k)]="ENABLE";
                    for (auto [i,h] : _01LH) { da["PPREG"+std::to_string(k)+"_NS"+h+"_"+std::to_string(2*k+i)]="ENABLE"; da["PPREG"+std::to_string(k)+"_BYP"+h+"_"+std::to_string(2*k+i)]="ENABLE"; } }
            } else {
                for (int k = 0; k < 2; k++) { for (char i : {'A','B'}) { da[std::string("CEMUX_")+i+"SIGN"+std::to_string(k)+"2"]=ce_val; da[std::string("CLKMUX_")+i+"SIGN"+std::to_string(k)+"2"]=clk_val; da[std::string("RSTMUX_")+i+"SIGN"+std::to_string(k)+"2"]=reset_val; }
                    for (char i : {'L','H'}) { da[std::string("CE")+i+"MUX_REGP"+std::to_string(k)]=ce_val; da[std::string("CLK")+i+"MUX_REGP"+std::to_string(k)]=clk_val; da[std::string("RST")+i+"MUX_REGP"+std::to_string(k)]=reset_val; } }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (int k = 0; k < 2; k++) { da["RSTGENMUX_ASIGN"+std::to_string(k)+"2"]="SYNC"; da["RSTGENMUX_BSIGN"+std::to_string(k)+"2"]="SYNC"; da["RSTGENLMUX_REGP"+std::to_string(k)]="SYNC"; da["RSTGENHMUX_REGP"+std::to_string(k)]="SYNC"; }
            }
        }
        if (parm == "OUT_REG") {
            if (mac == 0 && typ == "MULT36X36") {
                da["OREG0_NSH_1"]="ENABLE"; da["OREG0_BYPH_1"]="ENABLE";
                da["OREG1_NSL_2"]="ENABLE"; da["OREG1_BYPL_2"]="ENABLE";
                da["OREG1_NSH_3"]="ENABLE"; da["OREG1_BYPH_3"]="ENABLE";
                if (val == "0") { da["OREG0_NSL_0"]="ENABLE"; da["OREG0_BYPL_0"]="ENABLE"; }
                else { da["CELMUX_OREG0"]=ce_val; da["CLKLMUX_OREG0"]=clk_val; da["RSTLMUX_OREG0"]=reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") da["RSTGENLMUX_OREG0"]="SYNC"; }
            } else {
                if (val == "0") { for (int k = 0; k < 2; k++) { da["OREG"+std::to_string(k)+"_NSL_"+std::to_string(2*k)]="ENABLE"; da["OREG"+std::to_string(k)+"_BYPL_"+std::to_string(2*k)]="ENABLE"; da["OREG"+std::to_string(k)+"_NSH_"+std::to_string(2*k+1)]="ENABLE"; da["OREG"+std::to_string(k)+"_BYPH_"+std::to_string(2*k+1)]="ENABLE"; } }
                else { for (int k = 0; k < 2; k++) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_OREG"+std::to_string(k)]=ce_val; da[std::string("CLK")+h+"MUX_OREG"+std::to_string(k)]=clk_val; da[std::string("RST")+h+"MUX_OREG"+std::to_string(k)]=reset_val; }
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") for (char h : {'L','H'}) { da[std::string("RSTGEN")+h+"MUX_OREG0"]="SYNC"; da[std::string("RSTGEN")+h+"MUX_OREG1"]="SYNC"; } }
            }
        }
        if (parm == "ACCLOAD_REG0") {
            if (val == "0") { da["CINNS_2"]="ENABLE"; da["CINBY_2"]="ENABLE"; }
            else { da["CEMUX_ALUSEL1"]=ce_val; da["CLKMUX_ALUSEL1"]=clk_val; da["RSTMUX_ALUSEL1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") da["RSTGENMUX_ALUSEL1"]="SYNC"; }
        }
        if (parm == "ACCLOAD_REG1") {
            if (val == "0") { da["CPRNS_2"]="ENABLE"; da["CPRBY_2"]="ENABLE"; }
            else { da["CEMUX_ALUSEL2"]=ce_val; da["CLKMUX_ALUSEL2"]=clk_val; da["RSTMUX_ALUSEL2"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"] == "SYNC") da["RSTGENMUX_ALUSEL2"]="SYNC"; }
        }
    }
}

// ============================================================================
// set_alu54d_attrs
// ============================================================================
static void set_alu54d_attrs(const Device& /*db*/, const std::string& /*typ*/,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int /*mac*/)
{
    attrs_upper(attrs);
    da["ALU_EN"]="ENABLE";
    for (int i = 2; i < 7; i++) { da["CPRNS_"+std::to_string(i)]="ENABLE"; da["CPRBY_"+std::to_string(i)]="ENABLE";
        if (i > 4) { da["CINNS_"+std::to_string(i)]="ENABLE"; da["CINBY_"+std::to_string(i)]="ENABLE"; } }

    da["OPCD_3"]="1"; da["OPCD_9"]="1";
    if (params["B_ADD_SUB"] == "1") da["OPCD_7"]="1";

    if (attrs.count("USE_CASCADE_IN")) { da["CSGIN_EXT"]="ENABLE"; da["CSIGN_PRE"]="ENABLE"; }
    if (attrs.count("USE_CASCADE_OUT")) da["OR2CASCADE_EN"]="ENABLE";

    std::string ce_val = get_ce_val(attrs), clk_val = get_clk_val(attrs), reset_val = get_reset_val(attrs);

    set_dsp_regs_0(params, {"AREG","BREG","OUT_REG","ACCLOAD_REG"});
    for (const auto& [parm, val] : params) {
        if (parm == "ALUD_MODE") {
            int ival = static_cast<int>(parse_binary(val));
            if (ival == 2) { da["OPCD_1"]="1"; da["OPCD_5"]="1"; }
            else {
                if (ival == 0) { da["OPCD_6"]="1"; if (params["C_ADD_SUB"] == "1") da["OPCD_8"]="1"; }
                else da["OPCD_5"]="1";
                if (attrs["NET_ACCLOAD"] == "GND") { da["OPCD_0"]="1"; da["OPCD_1"]="1"; }
                else if (attrs["NET_ACCLOAD"] == "VCC") da["OR2CASCADE_EN"]="ENABLE";
                else { da["OR2CASCADE_EN"]="ENABLE"; da["OPCDDYN_0"]="ENABLE"; da["OPCDDYN_1"]="ENABLE"; da["OPCDDYN_INV_0"]="ENABLE"; da["OPCDDYN_INV_1"]="ENABLE"; }
            }
        }
        if (parm == "OUT_REG") {
            int ii = 0;
            if (val == "0") {
                for (int i = 0; i < 2; i++) for (char h : {'L','H'}) {
                    da["OREG"+std::to_string(i)+"_NS"+h+"_"+std::to_string(ii)]="ENABLE";
                    da["OREG"+std::to_string(i)+"_BYP"+h+"_"+std::to_string(ii)]="ENABLE";
                    da["OR2CIB_EN"+std::to_string(i)+h+"_"+std::to_string(ii)]="ENABLE";
                    ii++;
                }
            } else {
                for (int i = 0; i < 2; i++) for (char h : {'L','H'}) {
                    da[std::string("CE")+h+"MUX_OREG"+std::to_string(i)]=ce_val;
                    da[std::string("CLK")+h+"MUX_OREG"+std::to_string(i)]=clk_val;
                    da[std::string("RST")+h+"MUX_OREG"+std::to_string(i)]=reset_val;
                    da["OR2CIB_EN"+std::to_string(i)+h+"_"+std::to_string(ii)]="ENABLE";
                    ii++;
                }
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC")
                    for (char h : {'H','L'}) for (int i = 0; i < 2; i++) da[std::string("RSTGEN")+h+"MUX_OREG"+std::to_string(i)]="SYNC";
            }
        }
        if (parm == "AREG") {
            if (val == "0") {
                int ii = 0; da["CIR_BYPL_0"]="1";
                for (char a : {'A','B'}) for (char h : {'L','H'}) { da[std::string("IRBY_IREG0")+a+h+"_"+std::to_string(ii)]="ENABLE"; da[std::string("IRNS_IREG0")+a+h+"_"+std::to_string(ii)]="ENABLE"; ii++; }
            } else {
                da["CELMUX_CREG"]=ce_val; da["CLKLMUX_CREG"]=clk_val; da["RSTLMUX_CREG"]=reset_val;
                for (char a : {'A','B'}) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_REGM"+a+"0"]=ce_val; da[std::string("CLK")+h+"MUX_REGM"+a+"0"]=clk_val; da[std::string("RST")+h+"MUX_REGM"+a+"0"]=reset_val; }
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC") {
                    da["RSTGENLMUX_REGC0"]="SYNC";
                    for (char a : {'A','B'}) for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGM"+a+"0"]="SYNC";
                }
            }
        }
        if (parm == "BREG") {
            if (val == "0") {
                int ii = 4; da["CIR_BYPH_1"]="1";
                for (char a : {'A','B'}) for (char h : {'L','H'}) { da[std::string("IRBY_IREG1")+a+h+"_"+std::to_string(ii)]="ENABLE"; da[std::string("IRNS_IREG1")+a+h+"_"+std::to_string(ii)]="ENABLE"; ii++; }
            } else {
                da["CEHMUX_CREG"]=ce_val; da["CLKHMUX_CREG"]=clk_val; da["RSTHMUX_CREG"]=reset_val;
                for (char a : {'A','B'}) for (char h : {'L','H'}) { da[std::string("CE")+h+"MUX_REGM"+a+"1"]=ce_val; da[std::string("CLK")+h+"MUX_REGM"+a+"1"]=clk_val; da[std::string("RST")+h+"MUX_REGM"+a+"1"]=reset_val; }
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC") {
                    da["RSTGENLMUX_REGC0"]="SYNC";
                    for (char a : {'A','B'}) for (char h : {'L','H'}) da[std::string("RSTGEN")+h+"MUX_REGM"+a+"0"]="SYNC";
                }
            }
        }
        if (parm == "ASIGN_REG") {
            if (val == "0") { da["CINBY_3"]="ENABLE"; da["CINNS_3"]="ENABLE"; }
            else { da["CEMUX_ASIGN11"]=ce_val; da["CLKMUX_ASIGN11"]=clk_val; da["RSTMUX_ASIGN11"]=reset_val;
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC") da["RSTGENMUX_ASIGN11"]="SYNC"; }
        }
        if (parm == "BSIGN_REG") {
            if (val == "0") { da["CINBY_4"]="ENABLE"; da["CINNS_4"]="ENABLE"; }
            else { da["CEMUX_BSIGN11"]=ce_val; da["CLKMUX_BSIGN11"]=clk_val; da["RSTMUX_BSIGN11"]=reset_val;
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC") da["RSTGENMUX_BSIGN11"]="SYNC"; }
        }
        if (parm == "ACCLOAD_REG") {
            if (val == "0") { da["CINBY_2"]="ENABLE"; da["CINNS_2"]="ENABLE"; }
            else { da["CEMUX_ALUSEL1"]=ce_val; da["CLKMUX_ALUSEL1"]=clk_val; da["RSTMUX_ALUSEL1"]=reset_val;
                if (params.count("ALU_RESET_MODE") && params["ALU_RESET_MODE"] == "SYNC") da["RSTGENMUX_ALUSEL1"]="SYNC"; }
        }
    }
    da["RCISEL_1"]="1"; da["RCISEL_3"]="1";
}

// ============================================================================
// set_padd9_attrs
// ============================================================================
static void set_padd9_attrs(const Device& /*db*/, const std::string& /*typ*/,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int /*mac*/,
    int idx, int even_odd, int pair_idx)
{
    attrs_upper(attrs);
    da["CINBY_"+std::to_string(pair_idx+7)]="ENABLE"; da["CINNS_"+std::to_string(pair_idx+7)]="ENABLE";
    if (pair_idx) { da["CIR_BYPH_1"]="1"; da["RCISEL_3"]="1"; }
    else { da["CIR_BYPL_0"]="1"; da["RCISEL_1"]="1"; }

    if (pair_idx == 0 && attrs.count("LAST_IN_CHAIN")) da["PRAD_FBB1"]="ENABLE";
    da["PRAD_MUXA0EN_"+std::to_string(pair_idx)]="ENABLE";

    if (attrs["NET_ASEL"] == "VCC") da["PRAD_MUXA1_"+std::to_string(pair_idx*2)]="ENABLE";
    else if (!attrs["NET_ASEL"].empty() && attrs["NET_ASEL"] != "GND") { da["PRAD_MUXA1_"+std::to_string(pair_idx*2)]="ENABLE"; da["PRAD_MUXA1_"+std::to_string(pair_idx*2+1)]="ENABLE"; }

    std::string ce_val = get_ce_val(attrs), clk_val = get_clk_val(attrs), reset_val = get_reset_val(attrs);

    if (pair_idx) { da["MATCH"]="ENABLE"; da["MATCH_SHFEN"]="ENABLE"; }
    da["OR2CIB_EN"+std::to_string(pair_idx)+"L_"+std::to_string(pair_idx*2)]="ENABLE";

    set_dsp_regs_0(params, {"AREG","BREG"});
    for (const auto& [parm, val] : params) {
        if (parm == "AREG") {
            if (val == "0") {
                if (even_odd) { da["IRNS_PRAD"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE"; da["IRBY_PRAD"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE"; }
                else { da["IRNS_PRAD"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE"; da["IRBY_PRAD"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGA"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_REGA"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_REGA"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENHMUX_REGA"+std::to_string(pair_idx)]="SYNC"; }
                else { da["CELMUX_REGMA"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_REGMA"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_REGMA"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENLMUX_REGA"+std::to_string(pair_idx)]="SYNC"; }
            }
        }
        if (parm == "BREG") {
            if (val == "0") {
                if (even_odd) { da["IRNS_PRAD"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE"; da["IRBY_PRAD"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE"; }
                else { da["IRNS_PRAD"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE"; da["IRBY_PRAD"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGB"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_REGB"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_REGB"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENHMUX_REGB"+std::to_string(pair_idx)]="SYNC"; }
                else { da["CELMUX_REGMA"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_REGMA"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_REGMA"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENLMUX_REGB"+std::to_string(pair_idx)]="SYNC"; }
            }
        }
        if (parm == "SOREG" && pair_idx) {
            if (val == "0") {
                if (even_odd) { da["IRNS_IRMATCHH_9"]="ENABLE"; da["IRBY_IRMATCHH_9"]="ENABLE"; }
                else { da["IRNS_IRMATCHL_8"]="ENABLE"; da["IRBY_IRMATCHL_8"]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGSD"]=ce_val; da["CLKHMUX_REGSD"]=clk_val; da["RSTHMUX_REGSD"]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENHMUX_REGSD"]="SYNC"; }
                else { da["CELMUX_REGSD"]=ce_val; da["CLKLMUX_REGSD"]=clk_val; da["RSTLMUX_REGSD"]=reset_val;
                    if (params.count("PADD_RESET_MODE") && params["PADD_RESET_MODE"]=="SYNC") da["RSTGENLMUX_REGSD"]="SYNC"; }
            }
        }
        if (parm == "BSEL_MODE") {
            if (val == "0") da["PRAD_MUXB_"+std::to_string(pair_idx*2)]="ENABLE";
            else da["PRAD_MUXB_"+std::to_string(pair_idx*2+1)]="ENABLE";
        }
    }
    // mult: * C=1
    da["AIRMUX0_"+std::to_string(pair_idx)]="ENABLE";
    da["BIRMUX0_"+std::to_string(pair_idx*2)]="ENABLE";
    if (even_odd) {
        da["IRBY_IREG"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE";
        da["IRBY_IREG"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE";
        for (int x : {pair_idx*3, pair_idx*3+1}) { da["CINNS_"+std::to_string(x)]="ENABLE"; da["CINBY_"+std::to_string(x)]="ENABLE"; da["CPRNS_"+std::to_string(x)]="ENABLE"; da["CPRBY_"+std::to_string(x)]="ENABLE"; }
        da["PPREG"+std::to_string(pair_idx)+"_NSH_"+std::to_string(pair_idx*2+1)]="ENABLE"; da["PPREG"+std::to_string(pair_idx)+"_BYPH_"+std::to_string(pair_idx*2+1)]="ENABLE";
        da["OREG"+std::to_string(pair_idx)+"_NSH_"+std::to_string(pair_idx*2+1)]="ENABLE"; da["OREG"+std::to_string(pair_idx)+"_BYPH_"+std::to_string(pair_idx*2+1)]="ENABLE";
        da["OR2CIB_EN"+std::to_string(pair_idx)+"H_"+std::to_string(pair_idx*2+1)]="ENABLE";
    } else {
        da["IRBY_IREG"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE";
        da["IRBY_IREG"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE";
        for (int x : {pair_idx*3, pair_idx*3+1}) { da["CINNS_"+std::to_string(x)]="ENABLE"; da["CINBY_"+std::to_string(x)]="ENABLE"; da["CPRNS_"+std::to_string(x)]="ENABLE"; da["CPRBY_"+std::to_string(x)]="ENABLE"; }
        da["PPREG"+std::to_string(pair_idx)+"_NSL_"+std::to_string(pair_idx*2)]="ENABLE"; da["PPREG"+std::to_string(pair_idx)+"_BYPL_"+std::to_string(pair_idx*2)]="ENABLE";
        da["OREG"+std::to_string(pair_idx)+"_NSL_"+std::to_string(pair_idx*2)]="ENABLE"; da["OREG"+std::to_string(pair_idx)+"_BYPL_"+std::to_string(pair_idx*2)]="ENABLE";
        da["OR2CIB_EN"+std::to_string(pair_idx)+"L_"+std::to_string(pair_idx*2)]="ENABLE";
    }
}

// ============================================================================
// set_mult9x9_attrs
// ============================================================================
static void set_mult9x9_attrs(const Device& /*db*/, const std::string& /*typ*/,
    std::map<std::string, std::string>& params, const std::string& /*num*/,
    std::map<std::string, std::string>& attrs, DA& da, int /*mac*/,
    int idx, int even_odd, int pair_idx)
{
    attrs_upper(attrs);
    std::string ce_val = get_ce_val(attrs), clk_val = get_clk_val(attrs), reset_val = get_reset_val(attrs);

    da["IRASHFEN_"+std::to_string(pair_idx)]="1"; da["IRBSHFEN_"+std::to_string(pair_idx)]="1";
    if (pair_idx) da["MATCH_SHFEN"]="ENABLE";
    if (even_odd) da["OR2CIB_EN"+std::to_string(pair_idx)+"H_"+std::to_string(idx)]="ENABLE";
    else da["OR2CIB_EN"+std::to_string(pair_idx)+"L_"+std::to_string(idx)]="ENABLE";

    if (attrs["NET_ASEL"] == "VCC") da["AIRMUX1_"+std::to_string(pair_idx)]="ENABLE";
    else if (!attrs["NET_ASEL"].empty() && attrs["NET_ASEL"] != "GND") da["AIRMUX1_SEL_"+std::to_string(pair_idx)]="ENABLE";
    if (attrs["NET_BSEL"] == "VCC") da["BIRMUX1_"+std::to_string(pair_idx*2)]="ENABLE";
    else if (!attrs["NET_BSEL"].empty() && attrs["NET_BSEL"] != "GND") { da["BIRMUX0_"+std::to_string(pair_idx*2)]="ENABLE"; da["BIRMUX0_"+std::to_string(pair_idx*2+1)]="ENABLE"; da["BIRMUX1_"+std::to_string(pair_idx*2)]="ENABLE"; da["BIRMUX1_"+std::to_string(pair_idx*2+1)]="ENABLE"; }

    set_dsp_regs_0(params, {"AREG","BREG","OUT_REG","PIPE_REG","ASIGN_REG","BSIGN_REG","SOA_REG"});
    for (const auto& [parm, val] : params) {
        if (parm == "AREG") {
            if (val == "0") {
                if (even_odd) { da["IRBY_IREG"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"AH_"+std::to_string(pair_idx*4+1)]="ENABLE"; }
                else { da["IRBY_IREG"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"AL_"+std::to_string(pair_idx*4)]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGMA"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_REGMA"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_REGMA"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENHMUX_REGMA"+std::to_string(pair_idx)]="SYNC"; }
                else { da["CELMUX_REGMA"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_REGMA"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_REGMA"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENLMUX_REGMA"+std::to_string(pair_idx)]="SYNC"; }
            }
        }
        if (parm == "BREG") {
            if (val == "0") {
                if (even_odd) { da["IRBY_IREG"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"BH_"+std::to_string(pair_idx*4+3)]="ENABLE"; }
                else { da["IRBY_IREG"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE"; da["IRNS_IREG"+std::to_string(pair_idx)+"BL_"+std::to_string(pair_idx*4+2)]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGMB"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_REGMB"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_REGMB"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENHMUX_REGMB"+std::to_string(pair_idx)]="SYNC"; }
                else { da["CELMUX_REGMB"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_REGMB"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_REGMB"+std::to_string(pair_idx)]=reset_val;
                    if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENLMUX_REGMB"+std::to_string(pair_idx)]="SYNC"; }
            }
        }
        if (parm == "ASIGN_REG") {
            if (val == "0") { da["CINNS_"+std::to_string(pair_idx*3)]="ENABLE"; da["CINBY_"+std::to_string(pair_idx*3)]="ENABLE"; }
            else { da["CEMUX_ASIGN"+std::to_string(pair_idx)+"1"]=ce_val; da["CLKMUX_ASIGN"+std::to_string(pair_idx)+"1"]=clk_val; da["RSTMUX_ASIGN"+std::to_string(pair_idx)+"1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENMUX_ASIGN"+std::to_string(pair_idx)+"1"]="SYNC"; }
        }
        if (parm == "BSIGN_REG") {
            if (val == "0") { da["CINNS_"+std::to_string(pair_idx*3+1)]="ENABLE"; da["CINBY_"+std::to_string(pair_idx*3+1)]="ENABLE"; }
            else { da["CEMUX_BSIGN"+std::to_string(pair_idx)+"1"]=ce_val; da["CLKMUX_BSIGN"+std::to_string(pair_idx)+"1"]=clk_val; da["RSTMUX_BSIGN"+std::to_string(pair_idx)+"1"]=reset_val;
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") da["RSTGENMUX_BSIGN"+std::to_string(pair_idx)+"1"]="SYNC"; }
        }
        if (parm == "PIPE_REG") {
            if (val == "0") {
                da["CPRNS_"+std::to_string(pair_idx*3)]="ENABLE"; da["CPRBY_"+std::to_string(pair_idx*3)]="ENABLE";
                da["CPRNS_"+std::to_string(pair_idx*3+1)]="ENABLE"; da["CPRBY_"+std::to_string(pair_idx*3+1)]="ENABLE";
                if (even_odd) { da["PPREG"+std::to_string(pair_idx)+"_NSH_"+std::to_string(idx)]="ENABLE"; da["PPREG"+std::to_string(pair_idx)+"_BYPH_"+std::to_string(idx)]="ENABLE"; }
                else { da["PPREG"+std::to_string(pair_idx)+"_NSL_"+std::to_string(idx)]="ENABLE"; da["PPREG"+std::to_string(pair_idx)+"_BYPL_"+std::to_string(idx)]="ENABLE"; }
            } else {
                da["CEMUX_ASIGN"+std::to_string(pair_idx)+"2"]=ce_val; da["CLKMUX_ASIGN"+std::to_string(pair_idx)+"2"]=clk_val; da["RSTMUX_ASIGN"+std::to_string(pair_idx)+"2"]=reset_val;
                da["CEMUX_BSIGN"+std::to_string(pair_idx)+"2"]=ce_val; da["CLKMUX_BSIGN"+std::to_string(pair_idx)+"2"]=clk_val; da["RSTMUX_BSIGN"+std::to_string(pair_idx)+"2"]=reset_val;
                if (even_odd) { da["CEHMUX_REGP"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_REGP"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_REGP"+std::to_string(pair_idx)]=reset_val; }
                else { da["CELMUX_REGP"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_REGP"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_REGP"+std::to_string(pair_idx)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") {
                    da["RSTGENMUX_ASIGN"+std::to_string(pair_idx)+"2"]="SYNC"; da["RSTGENMUX_BSIGN"+std::to_string(pair_idx)+"2"]="SYNC";
                    if (even_odd) da["RSTGENHMUX_REGP"+std::to_string(pair_idx)]="SYNC"; else da["RSTGENLMUX_REGP"+std::to_string(pair_idx)]="SYNC";
                }
            }
        }
        if (parm == "OUT_REG") {
            if (val == "0") {
                if (even_odd) { da["OREG"+std::to_string(pair_idx)+"_BYPH_"+std::to_string(idx)]="ENABLE"; da["OREG"+std::to_string(pair_idx)+"_NSH_"+std::to_string(idx)]="ENABLE"; }
                else { da["OREG"+std::to_string(pair_idx)+"_BYPL_"+std::to_string(idx)]="ENABLE"; da["OREG"+std::to_string(pair_idx)+"_NSL_"+std::to_string(idx)]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_OREG"+std::to_string(pair_idx)]=ce_val; da["CLKHMUX_OREG"+std::to_string(pair_idx)]=clk_val; da["RSTHMUX_OREG"+std::to_string(pair_idx)]=reset_val; }
                else { da["CELMUX_OREG"+std::to_string(pair_idx)]=ce_val; da["CLKLMUX_OREG"+std::to_string(pair_idx)]=clk_val; da["RSTLMUX_OREG"+std::to_string(pair_idx)]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") {
                    if (even_odd) da["RSTGENHMUX_OREG"+std::to_string(pair_idx)]="SYNC"; else da["RSTGENLMUX_OREG"+std::to_string(pair_idx)]="SYNC";
                }
            }
        }
        if (parm == "SOA_REG" && pair_idx) {
            if (val == "0") {
                if (even_odd) { da["IRBY_IRMATCHH_9"]="ENABLE"; da["IRNS_IRMATCHH_9"]="ENABLE"; }
                else { da["IRBY_IRMATCHL_8"]="ENABLE"; da["IRNS_IRMATCHL_8"]="ENABLE"; }
            } else {
                if (even_odd) { da["CEHMUX_REGSD"]=ce_val; da["CLKHMUX_REGSD"]=clk_val; da["RSTHMUX_REGSD"]=reset_val; }
                else { da["CELMUX_REGSD"]=ce_val; da["CLKLMUX_REGSD"]=clk_val; da["RSTLMUX_REGSD"]=reset_val; }
                if (params.count("MULT_RESET_MODE") && params["MULT_RESET_MODE"]=="SYNC") {
                    if (even_odd) da["RSTGENHMUX_REGSD"]="SYNC"; else da["RSTGENLMUX_REGSD"]="SYNC";
                }
            }
        }
    }
}

// ============================================================================
// Convert dsp_attrs dict to fin_attrs set
// ============================================================================
static std::set<int64_t> dsp_attrs_to_fin(const Device& db, const DA& da) {
    using namespace attrids;
    std::set<int64_t> fin_attrs;
    for (const auto& [attr, val] : da) {
        auto attr_it = dsp_attrids.find(attr);
        if (attr_it == dsp_attrids.end()) continue;
        auto val_it = dsp_attrvals.find(val);
        if (val_it == dsp_attrvals.end()) continue;
        add_attr_val(db, "DSP", fin_attrs, attr_it->second, val_it->second);
    }
    return fin_attrs;
}

// ============================================================================
// set_dsp_attrs - main entry point
// ============================================================================
std::set<int64_t> set_dsp_attrs(const Device& db, const std::string& typ,
    std::map<std::string, std::string>& params, const std::string& num,
    std::map<std::string, std::string>& attrs)
{
    DA da;
    int mac = num[0] - '0';
    int idx = num[1] - '0';
    int even_odd = idx & 1;
    int pair_idx = idx / 2;

    if (typ == "PADD9" || typ == "MULT9X9") da["M9MODE_EN"] = "ENABLE";

    if (typ == "PADD9") {
        set_padd9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
    } else if (typ == "PADD18") {
        idx *= 2; even_odd = idx & 1; pair_idx = idx / 2;
        set_padd9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
        idx += 1; even_odd = idx & 1; pair_idx = idx / 2;
        set_padd9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
    } else if (typ == "MULT9X9") {
        set_mult9x9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
    } else if (typ == "MULT18X18") {
        idx *= 2; even_odd = idx & 1; pair_idx = idx / 2;
        set_mult9x9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
        idx += 1; even_odd = idx & 1; pair_idx = idx / 2;
        set_mult9x9_attrs(db, typ, params, num, attrs, da, mac, idx, even_odd, pair_idx);
    } else if (typ == "ALU54D") {
        set_alu54d_attrs(db, typ, params, num, attrs, da, mac);
    } else if (typ == "MULTALU18X18") {
        set_multalu18x18_attrs(db, typ, params, num, attrs, da, mac);
    } else if (typ == "MULTALU36X18") {
        set_multalu36x18_attrs(db, typ, params, num, attrs, da, mac);
    } else if (typ == "MULTADDALU18X18") {
        set_multaddalu18x18_attrs(db, typ, params, num, attrs, da, mac);
    }

    return dsp_attrs_to_fin(db, da);
}

// ============================================================================
// set_dsp_mult36x36_attrs - special case for MULT36X36 (two macros)
// ============================================================================
std::vector<std::set<int64_t>> set_dsp_mult36x36_attrs(const Device& db, const std::string& typ,
    std::map<std::string, std::string>& params, std::map<std::string, std::string>& attrs)
{
    attrs_upper(attrs);
    attrs["NET_ASEL"] = "GND";
    attrs["NET_BSEL"] = "GND";

    set_dsp_regs_0(params, {"AREG","BREG","ASIGN_REG","BSIGN_REG"});

    // macro 0
    DA da0;
    params["MULTALU36X18_MODE"] = "1"; // ACC/0 + A*B
    attrs["NET_ACCLOAD"] = "GND";
    params["OUT_REG"] = get_param(params, "OUT0_REG", "0");
    params["ACCLOAD_REG0"] = "0";
    params["ACCLOAD_REG1"] = "0";
    set_multalu36x18_attrs(db, typ, params, "00", attrs, da0, 0);
    da0["OR2CASCADE_EN"] = "ENABLE";
    da0["IRNS_IRMATCHH_9"]="ENABLE"; da0["IRNS_IRMATCHL_8"]="ENABLE";
    da0["IRBY_IRMATCHH_9"]="ENABLE"; da0["IRBY_IRMATCHL_8"]="ENABLE";
    da0["MATCH_SHFEN"] = "ENABLE";
    da0.erase("IRASHFEN_0");
    da0.erase("RCISEL_1");
    da0.erase("RCISEL_3");

    std::vector<std::set<int64_t>> ret;
    ret.push_back(dsp_attrs_to_fin(db, da0));

    // macro 1
    DA da1;
    params["MULTALU36X18_MODE"] = "10"; // A*B + CASI
    params["OUT_REG"] = get_param(params, "OUT1_REG", "0");
    set_multalu36x18_attrs(db, typ, params, "00", attrs, da1, 1);
    da1["CSGIN_EXT"]="ENABLE"; da1["CSIGN_PRE"]="ENABLE";
    da1["IRNS_IRMATCHH_9"]="ENABLE"; da1["IRNS_IRMATCHL_8"]="ENABLE";
    da1["IRBY_IRMATCHH_9"]="ENABLE"; da1["IRBY_IRMATCHL_8"]="ENABLE";
    da1["MATCH_SHFEN"]="ENABLE";
    da1.erase("IRASHFEN_0");
    da1.erase("RCISEL_1");
    da1.erase("RCISEL_3");
    da1.erase("OPCD_5");
    da1["OPCD_4"] = "1";

    ret.push_back(dsp_attrs_to_fin(db, da1));
    return ret;
}

} // namespace apycula
