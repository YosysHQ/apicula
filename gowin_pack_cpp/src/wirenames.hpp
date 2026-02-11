// wirenames.hpp - Clock wire name-to-number mappings for GW5A devices
// Ported from apycula/wirenames.py
#pragma once

#include <string>
#include <unordered_map>

namespace apycula {

// Get the clock wire number for a given name.
// Returns -1 if not a known clock wire.
inline int get_clk_number(const std::string& name, const std::string& device);

// Check if a pip is a clock pip that needs GW5A set_clock_fuses handling.
inline bool is_clock_pip(const std::string& src, const std::string& dest,
                         const std::string& device);

// Build clknumbers map for GW5A-25A (reverse of clknames_5a25a in Python)
inline const std::unordered_map<std::string, int>& clknumbers_5a25a() {
    static std::unordered_map<std::string, int> m;
    static bool built = false;
    if (built) return m;

    // SPINE0-31 -> 0-31
    for (int n = 0; n < 32; n++)
        m["SPINE" + std::to_string(n)] = n;
    // LWT0-7 -> 32-39
    for (int n = 0; n < 8; n++)
        m["LWT" + std::to_string(n)] = 32 + n;
    // LWB0-7 -> 40-47
    for (int n = 0; n < 8; n++)
        m["LWB" + std::to_string(n)] = 40 + n;
    // P{q}{w}{l} -> 48-79
    {
        const char suffixes[] = {'A', 'B', 'C', 'D'};
        int num = 48;
        for (int q = 1; q <= 4; q++) {
            for (int w = 6; w <= 7; w++) {
                for (char l : suffixes) {
                    m[std::string("P") + char('0'+q) + char('0'+w) + l] = num++;
                }
            }
        }
    }
    m["VSS"] = 80;
    // PLL{x}CLKOUT{y} -> 81-128 (order: 4,3,2,8,6,5)
    {
        const int pll_order[] = {4, 3, 2, 8, 6, 5};
        int num = 81;
        for (int pll : pll_order) {
            for (int y = 0; y < 8; y++) {
                m["PLL" + std::to_string(pll) + "CLKOUT" + std::to_string(y)] = num++;
            }
        }
    }
    // *BDCLK and *MDCLK -> 129-152
    for (int n = 0; n < 4; n++) m["TRBDCLK" + std::to_string(n)] = 129 + n;
    for (int n = 0; n < 4; n++) m["TLBDCLK" + std::to_string(n)] = 133 + n;
    for (int n = 0; n < 4; n++) m["BRBDCLK" + std::to_string(n)] = 137 + n;
    for (int n = 0; n < 4; n++) m["BLBDCLK" + std::to_string(n)] = 141 + n;
    for (int n = 0; n < 2; n++) m["TRMDCLK" + std::to_string(n)] = 145 + n;
    for (int n = 0; n < 2; n++) m["TLMDCLK" + std::to_string(n)] = 147 + n;
    for (int n = 0; n < 2; n++) m["BRMDCLK" + std::to_string(n)] = 149 + n;
    for (int n = 0; n < 2; n++) m["BLMDCLK" + std::to_string(n)] = 151 + n;
    // UNK153-168 (169 overwritten by TBDHCLK0)
    for (int n = 153; n <= 168; n++) m["UNK" + std::to_string(n)] = n;
    // *BDHCLK -> 169-184
    for (int n = 0; n < 4; n++) m["TBDHCLK" + std::to_string(n)] = 169 + n;
    for (int n = 0; n < 4; n++) m["RBDHCLK" + std::to_string(n)] = 173 + n;
    for (int n = 0; n < 4; n++) m["BBDHCLK" + std::to_string(n)] = 177 + n;
    for (int n = 0; n < 4; n++) m["LBDHCLK" + std::to_string(n)] = 181 + n;
    // UNK185-276
    for (int n = 185; n <= 276; n++) m["UNK" + std::to_string(n)] = n;
    m["VCC"] = 277;
    for (int n = 278; n <= 280; n++) m["UNK" + std::to_string(n)] = n;
    m["GT00"] = 291;
    m["GT10"] = 292;
    // UNK309-334
    for (int n = 309; n <= 334; n++) m["UNK" + std::to_string(n)] = n;
    // MPLL{x}* -> 501-566 (order: 4,3,2,8,6,5; 11 entries each)
    {
        const int pll_order[] = {4, 3, 2, 8, 6, 5};
        int num = 501;
        for (int pll : pll_order) {
            std::string pfx = "MPLL" + std::to_string(pll);
            for (int y = 0; y < 7; y++)
                m[pfx + "CLKOUT" + std::to_string(y)] = num++;
            m[pfx + "CLKFBOUT"] = num++;
            m[pfx + "CLKIN2"] = num++;
            m[pfx + "CLKIN6"] = num++;
            m[pfx + "CLKIN7"] = num++;
        }
    }
    // UNK567-569
    for (int n = 567; n <= 569; n++) m["UNK" + std::to_string(n)] = n;
    // HCLKMUX0 (1000) - HCLKMUX1 overwritten by LWSPINETL0
    m["HCLKMUX0"] = 1000;
    // LWSPINE* -> 1001-1048
    for (int n = 0; n < 8; n++) m["LWSPINETL" + std::to_string(n)] = 1001 + n;
    for (int n = 0; n < 8; n++) m["LWSPINETR" + std::to_string(n)] = 1009 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEBL" + std::to_string(n)] = 1017 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEBR" + std::to_string(n)] = 1025 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEB1L" + std::to_string(n)] = 1033 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEB1R" + std::to_string(n)] = 1041 + n;
    // UNK1049-1224
    for (int n = 1049; n <= 1224; n++) m["UNK" + std::to_string(n)] = n;
    // UNK ranges shared with GW5AST-138C
    for (int n = 1273; n <= 1288; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1353; n <= 1368; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1433; n <= 1448; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1513; n <= 1528; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1593; n <= 1608; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1673; n <= 1688; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1753; n <= 1768; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1833; n <= 1848; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1913; n <= 1928; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1993; n <= 2008; n++) m["UNK" + std::to_string(n)] = n;

    built = true;
    return m;
}

// Build clknumbers map for GW5AST-138C
inline const std::unordered_map<std::string, int>& clknumbers_5ast138c() {
    static std::unordered_map<std::string, int> m;
    static bool built = false;
    if (built) return m;

    // SPINE0-31 -> 0-31
    for (int n = 0; n < 32; n++)
        m["SPINE" + std::to_string(n)] = n;
    for (int n = 0; n < 8; n++)
        m["LWT" + std::to_string(n)] = 32 + n;
    for (int n = 0; n < 8; n++)
        m["LWB" + std::to_string(n)] = 40 + n;
    // P{q}{w}{l} -> 48-79 (same as 25A)
    {
        const char suffixes[] = {'A', 'B', 'C', 'D'};
        int num = 48;
        for (int q = 1; q <= 4; q++) {
            for (int w = 6; w <= 7; w++) {
                for (char l : suffixes) {
                    m[std::string("P") + char('0'+q) + char('0'+w) + l] = num++;
                }
            }
        }
    }
    m["VSS"] = 80;
    // 138C PLLs: TLPLL0CLK0-3, TLPLL1CLK0-3, BLPLL0/1, BRPLL1/0 -> 81-104
    for (int n = 0; n < 4; n++) m["TLPLL0CLK" + std::to_string(n)] = 81 + n;
    for (int n = 0; n < 4; n++) m["TLPLL1CLK" + std::to_string(n)] = 85 + n;
    for (int n = 0; n < 4; n++) m["BLPLL0CLK" + std::to_string(n)] = 89 + n;
    for (int n = 0; n < 4; n++) m["BLPLL1CLK" + std::to_string(n)] = 93 + n;
    for (int n = 0; n < 4; n++) m["BRPLL1CLK" + std::to_string(n)] = 97 + n;
    for (int n = 0; n < 4; n++) m["BRPLL0CLK" + std::to_string(n)] = 101 + n;
    // UNK105-130
    for (int n = 105; n <= 130; n++) m["UNK" + std::to_string(n)] = n;
    // PCLK pins
    m["PCLKT0"] = 131; m["PCLKT1"] = 132;
    m["PCLKB0"] = 133; m["PCLKB1"] = 134;
    m["PCLKL0"] = 135; m["PCLKL1"] = 136;
    m["PCLKR0"] = 137; m["PCLKR1"] = 138;
    // BDCLK/MDCLK (138C order differs from 25A)
    m["TRBDCLK0"] = 139; m["TRBDCLK1"] = 140;
    m["TRBDCLK2"] = 141; m["TRBDCLK3"] = 142;
    m["TLBDCLK1"] = 143; m["TLBDCLK2"] = 144;
    m["TLBDCLK3"] = 145; m["TLBDCLK0"] = 146;
    m["BRBDCLK2"] = 147; m["BRBDCLK3"] = 148;
    m["BRBDCLK0"] = 149; m["BRBDCLK1"] = 150;
    m["BLBDCLK1"] = 151; m["BLBDCLK2"] = 152;
    m["BLBDCLK3"] = 153; m["BLBDCLK0"] = 154;
    m["TRMDCLK0"] = 155; m["TLMDCLK0"] = 156;
    m["BRMDCLK0"] = 157; m["BLMDCLK0"] = 158;
    m["BLMDCLK1"] = 159; m["BRMDCLK1"] = 160;
    m["TLMDCLK1"] = 161; m["TRMDCLK1"] = 162;
    // UNK163-236
    for (int n = 163; n <= 236; n++) m["UNK" + std::to_string(n)] = n;
    // CBRIDGEOUT
    for (int n = 0; n < 8; n++)
        m["CBRIDGEOUT_TOP" + std::to_string(n)] = 237 + n;
    for (int n = 0; n < 8; n++)
        m["CBRIDGEOUT_BOTTOM" + std::to_string(n)] = 245 + n;
    // UNK253-308 (277 overwritten by VCC, 291/292 by GT00/GT10)
    for (int n = 253; n <= 276; n++) m["UNK" + std::to_string(n)] = n;
    m["VCC"] = 277;
    for (int n = 278; n <= 290; n++) m["UNK" + std::to_string(n)] = n;
    m["GT00"] = 291;
    m["GT10"] = 292;
    for (int n = 293; n <= 308; n++) m["UNK" + std::to_string(n)] = n;
    // UNK309-569
    for (int n = 309; n <= 569; n++) m["UNK" + std::to_string(n)] = n;
    // HCLKMUX0, LWSPINE* (same structure as 25A)
    m["HCLKMUX0"] = 1000;
    for (int n = 0; n < 8; n++) m["LWSPINETL" + std::to_string(n)] = 1001 + n;
    for (int n = 0; n < 8; n++) m["LWSPINETR" + std::to_string(n)] = 1009 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEBL" + std::to_string(n)] = 1017 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEBR" + std::to_string(n)] = 1025 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEB1L" + std::to_string(n)] = 1033 + n;
    for (int n = 0; n < 8; n++) m["LWSPINEB1R" + std::to_string(n)] = 1041 + n;
    for (int n = 1049; n <= 1224; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1273; n <= 1288; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1353; n <= 1368; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1433; n <= 1448; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1513; n <= 1528; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1593; n <= 1608; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1673; n <= 1688; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1753; n <= 1768; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1833; n <= 1848; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1913; n <= 1928; n++) m["UNK" + std::to_string(n)] = n;
    for (int n = 1993; n <= 2008; n++) m["UNK" + std::to_string(n)] = n;

    built = true;
    return m;
}

// Get clknumbers map for a device
inline const std::unordered_map<std::string, int>& get_clknumbers(const std::string& device) {
    if (device == "GW5AST-138C") return clknumbers_5ast138c();
    return clknumbers_5a25a(); // default for GW5A-25A
}

// Get clock number for a wire name (-1 if not a clock wire)
inline int get_clk_number(const std::string& name, const std::string& device) {
    const auto& nums = get_clknumbers(device);
    auto it = nums.find(name);
    return (it != nums.end()) ? it->second : -1;
}

// Check if a pip should use GW5A clock routing (set_clock_fuses)
// Matches Python is_clock_pip() in gowin_pack.py
inline bool is_clock_pip(const std::string& src, const std::string& dest,
                         const std::string& device) {
    // Check for _BOT/_TOP suffix at position 8
    if (src.size() > 12 && (src.substr(8, 4) == "_BOT" || src.substr(8, 4) == "_TOP")) {
        return true;
    }

    const auto& nums = get_clknumbers(device);
    auto src_it = nums.find(src);
    if (src_it == nums.end()) return false;
    auto dest_it = nums.find(dest);
    if (dest_it == nums.end()) return false;

    int src_num = src_it->second;

    if (device == "GW5A-25A") {
        // UNK212 = 212, MPLL4CLKOUT0 = 501, UNK569 = 569
        return src_num < 212 || (src_num >= 501 && src_num <= 569);
    }
    if (device == "GW5AST-138C") {
        // UNK269 = 269, UNK309 = 309
        return src_num < 269 || src_num >= 309;
    }
    return false;
}

} // namespace apycula
