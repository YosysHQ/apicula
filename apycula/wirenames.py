""" *********************************************************************************
     Names and encoding of wires on chips prior to the introduction of the 5A series
    *********************************************************************************
"""
wirenames_pre5a = { 0: "A0", 1: "B0", 2: "C0", 3: "D0", 4: "A1", 5: "B1", 6: "C1", 7: "D1", 8: "A2", 9: "B2", 10: "C2", 11: "D2", 12: "A3", 13: "B3", 14: "C3",
15: "D3", 16: "A4", 17: "B4", 18: "C4", 19: "D4", 20: "A5", 21: "B5", 22: "C5", 23: "D5", 24: "A6", 25: "B6", 26: "C6", 27: "D6", 28: "A7", 29: "B7",
30: "C7", 31: "D7", 32: "F0", 33: "F1", 34: "F2", 35: "F3", 36: "F4", 37: "F5", 38: "F6", 39: "F7", 40: "Q0", 41: "Q1", 42: "Q2", 43: "Q3", 44: "Q4",
45: "Q5", 46: "Q6", 47: "Q7", 48: "OF0", 49: "OF1", 50: "OF2", 51: "OF3", 52: "OF4", 53: "OF5", 54: "OF6", 55: "OF7", 56: "X01", 57: "X02", 58: "X03",
59: "X04", 60: "X05", 61: "X06", 62: "X07", 63: "X08", 64: "N100", 65: "SN10", 66: "SN20", 67: "N130", 68: "S100", 69: "S130", 70: "E100", 71: "EW10",
72: "EW20", 73: "E130", 74: "W100", 75: "W130", 76: "N200", 77: "N210", 78: "N220", 79: "N230", 80: "N240", 81: "N250", 82: "N260", 83: "N270", 84: "S200",
85: "S210", 86: "S220", 87: "S230", 88: "S240", 89: "S250", 90: "S260", 91: "S270", 92: "E200", 93: "E210", 94: "E220", 95: "E230", 96: "E240", 97: "E250",
98: "E260", 99: "E270", 100: "W200", 101: "W210", 102: "W220", 103: "W230", 104: "W240", 105: "W250", 106: "W260", 107: "W270", 108: "N800", 109: "N810",
110: "N820", 111: "N830", 112: "S800", 113: "S810", 114: "S820", 115: "S830", 116: "E800", 117: "E810", 118: "E820", 119: "E830", 120: "W800", 121: "W810",
122: "W820", 123: "W830", 124: "CLK0", 125: "CLK1", 126: "CLK2", 127: "LSR0", 128: "LSR1", 129: "LSR2", 130: "CE0", 131: "CE1", 132: "CE2", 133: "SEL0",
134: "SEL1", 135: "SEL2", 136: "SEL3", 137: "SEL4", 138: "SEL5", 139: "SEL6", 140: "SEL7", 141: "N101", 142: "N131", 143: "S101", 144: "S131", 145: "E101", 146: "E131",
147: "W101", 148: "W131", 149: "N201", 150: "N211", 151: "N221", 152: "N231", 153: "N241", 154: "N251", 155: "N261", 156: "N271", 157: "S201", 158: "S211",
159: "S221", 160: "S231", 161: "S241", 162: "S251", 163: "S261", 164: "S271", 165: "E201", 166: "E211", 167: "E221", 168: "E231", 169: "E241", 170: "E251",
171: "E261", 172: "E271", 173: "W201", 174: "W211", 175: "W221", 176: "W231", 177: "W241", 178: "W251", 179: "W261", 180: "W271", 181: "N202", 182: "N212",
183: "N222", 184: "N232", 185: "N242", 186: "N252", 187: "N262", 188: "N272", 189: "S202", 190: "S212", 191: "S222", 192: "S232", 193: "S242", 194: "S252",
195: "S262", 196: "S272", 197: "E202", 198: "E212", 199: "E222", 200: "E232", 201: "E242", 202: "E252", 203: "E262", 204: "E272", 205: "W202", 206: "W212",
207: "W222", 208: "W232", 209: "W242", 210: "W252", 211: "W262", 212: "W272", 213: "N804", 214: "N814", 215: "N824", 216: "N834", 217: "S804", 218: "S814",
219: "S824", 220: "S834", 221: "E804", 222: "E814", 223: "E824", 224: "E834", 225: "W804", 226: "W814", 227: "W824", 228: "W834", 229: "N808", 230: "N818",
231: "N828", 232: "N838", 233: "S808", 234: "S818", 235: "S828", 236: "S838", 237: "E808", 238: "E818", 239: "E828", 240: "E838", 241: "W808", 242: "W818",
243: "W828", 244: "W838", 245: "E110", 246: "W110", 247: "E120", 248: "W120", 249: "S110", 250: "N110", 251: "S120", 252: "N120", 253: "E111", 254: "W111",
255: "E121", 256: "W121", 257: "S111", 258: "N111", 259: "S121", 260: "N121", 261: "LB01", 262: "LB11", 263: "LB21", 264: "LB31", 265: "LB41", 266: "LB51",
267: "LB61", 268: "LB71", 269: "GB00", 270: "GB10", 271: "GB20", 272: "GB30", 273: "GB40", 274: "GB50", 275: "GB60", 276: "GB70", 277: "VCC", 278: "VSS",
279: "LT00", 280: "LT10", 281: "LT20", 282: "LT30", 283: "LT02", 284: "LT13", 285: "LT01", 286: "LT04", 287: "LBO0", 288: "LBO1", 289: "SS00", 290: "SS40",
291: "GT00", 292: "GT10", 293: "GBO0", 294: "GBO1", 295: "DI0", 296: "DI1", 297: "DI2", 298: "DI3", 299: "DI4", 300: "DI5", 301: "DI6", 302: "DI7",
             303: "CIN0", 304: "CIN1", 305: "CIN2", 306: "CIN3", 307: "CIN4", 308: "CIN5", 309: "COUT0", 310: "COUT1", 311: "COUT2", 312: "COUT3", 313: "COUT4", 314: "COUT5", 315: "SPCLK_0", 316: "SPCLK_1"}

wirenames_pre5a.update({n: f"UNK{n}" for n in range(506, 569)})

wirenames_pre5a.update({n: f"LWSPINETL{n - 1001}" for n in range(1001, 1009)})
wirenames_pre5a.update({n: f"LWSPINETR{n - 1009}" for n in range(1009, 1017)})
wirenames_pre5a.update({n: f"LWSPINEBL{n - 1017}" for n in range(1017, 1025)})
wirenames_pre5a.update({n: f"LWSPINEBR{n - 1025}" for n in range(1025, 1033)})
wirenames_pre5a.update({n: f"LWSPINEB1L{n - 1033}" for n in range(1033, 1041)})
wirenames_pre5a.update({n: f"LWSPINEB1R{n - 1041}" for n in range(1041, 1049)})

wirenames_pre5a.update({n: f"UNK{n}" for n in range(1049, 1241)})

wirenames_pre5a.update({n: f"5A{n}" for n in range(545, 553)}) # GW5A-25A need these
wirenames_pre5a.update({n: f"5A{n}" for n in range(556, 564)}) # GW5A-25A need these

wirenumbers_pre5a = {v: k for k, v in wirenames_pre5a.items()}

clknames_pre5a = {}
clknames_pre5a.update({n: f"SPINE{n}" for n in range(32)})
clknames_pre5a.update({n: f"LWT{n - 32}" for n in range(32, 40)})
clknames_pre5a.update({n: f"LWB{n - 40}" for n in range(40, 48)})
# Apparently the names of the 8 primary clock wires comprise the quadrant
# number and the number of the actual clock wire: P34 stands for primary clock
# #4, 3rd quadrant. The quadrants are numbered counterclockwise:
# 2        1
#   center
# 3        4
# in addition, chips with two quadrants have quadrant numbers 3 and 4, not 1
# and 2 as you might expect.
# Wires 6 and 7 are the outputs of the dynamic 4-input MUX, the assumed
# numbers of these inputs are listed below:
clknames_pre5a.update({
     48: 'P16A', 49: 'P16B', 50: 'P16C', 51: 'P16D',
     52: 'P17A', 53: 'P17B', 54: 'P17C', 55: 'P17D',
     56: 'P26A', 57: 'P26B', 58: 'P26C', 59: 'P26D',
     60: 'P27A', 61: 'P27B', 62: 'P27C', 63: 'P27D',
     64: 'P36A', 65: 'P36B', 66: 'P36C', 67: 'P36D',
     68: 'P37A', 69: 'P37B', 70: 'P37C', 71: 'P37D',
     72: 'P46A', 73: 'P46B', 74: 'P46C', 75: 'P46D',
     76: 'P47A', 77: 'P47B', 78: 'P47C', 79: 'P47D'
})
clknames_pre5a[80] = 'VSS'
# each PLL has 4 delay-critical outputs (clkout, clkoutp, clkoutd, clkoutd3),
# their numbers are listed here, the names indicate the possible location of
# the PLL (Top Left etc):
clknames_pre5a.update({
    81: 'TLPLL0CLK0', 82: 'TLPLL0CLK1', 83: 'TLPLL0CLK2', 84: 'TLPLL0CLK3',
    85: 'TLPLL1CLK0', 86: 'TLPLL1CLK1', 87: 'TLPLL1CLK2', 88: 'TLPLL1CLK3',
    89: 'BLPLL0CLK0', 90: 'BLPLL0CLK1', 91: 'BLPLL0CLK2', 92: 'BLPLL0CLK3',
    93: 'TRPLL0CLK0', 94: 'TRPLL0CLK1', 95: 'TRPLL0CLK2', 96: 'TRPLL0CLK3',
    97: 'TRPLL1CLK0', 98: 'TRPLL1CLK1', 99: 'TRPLL1CLK2', 100: 'TRPLL1CLK3',
    101: 'BRPLL0CLK0', 102: 'BRPLL0CLK1', 103: 'BRPLL0CLK2', 104: 'BRPLL0CLK3',
})
clknames_pre5a.update({n: f"UNK{n}" for n in range(105, 121)})
# These are CLKDIV output nodes
# clknames_pre5a.update({
#     106: 'THCLK0_CLKDIV_CLKOUT', 108:'THCLK1_CLKDIV_CLKOUT',
#     118: 'RHCLK0_CLKDIV_CLKOUT', 120:'RHCLK1_CLKDIV_CLKOUT',
#     110: 'BHCLK0_CLKDIV_CLKOUT', 112:'BHCLK1_CLKDIV_CLKOUT',
#     114: 'LHCLK0_CLKDIV_CLKOUT', 116:'LHCLK1_CLKDIV_CLKOUT',
# })
clknames_pre5a.update({
    106: 'THCLK0CLKDIV', 108:'THCLK1CLKDIV',
    118: 'RHCLK0CLKDIV', 120:'RHCLK1CLKDIV',
    110: 'BHCLK0CLKDIV', 112:'BHCLK1CLKDIV',
    114: 'LHCLK0CLKDIV', 116:'LHCLK1CLKDIV',
})

# These are the external clock pins, two on each side
clknames_pre5a.update({
    121: 'PCLKT0', 122: 'PCLKT1', 123: 'PCLKB0', 124: 'PCLKB1',
    125: 'PCLKL0', 126: 'PCLKL1', 127: 'PCLKR0', 128: 'PCLKR1',
})
clknames_pre5a.update({
    129: 'TRBDCLK0', 130: 'TRBDCLK1', 131: 'TRBDCLK2', 132: 'TRBDCLK3',
    133: 'TLBDCLK1', 134: 'TLBDCLK2', 135: 'TLBDCLK3', 136: 'TLBDCLK0',
    137: 'BRBDCLK2', 138: 'BRBDCLK3', 139: 'BRBDCLK0', 140: 'BRBDCLK1',
    141: 'BLBDCLK3', 142: 'BLBDCLK0', 143: 'BLBDCLK1', 144: 'BLBDCLK2',
    145: 'TRMDCLK0', 146: 'TLMDCLK0', 147: 'BRMDCLK0', 148: 'BLMDCLK0',
    149: 'BLMDCLK1', 150: 'BRMDCLK1', 151: 'TLMDCLK1', 152: 'TRMDCLK1',
})

#clknames_pre5a[153] = 'VCC'

clknames_pre5a.update({n: f"UNK{n}" for n in range(153, 170)})

# HCLK?
clknames_pre5a.update({
    170: 'TBDHCLK0', 171: 'TBDHCLK1', 172: 'TBDHCLK2', 173: 'TBDHCLK3', 174: 'BBDHCLK0',
    175: 'BBDHCLK1', 176: 'BBDHCLK2', 177: 'BBDHCLK3', 178: 'LBDHCLK0', 179: 'LBDHCLK1',
    180: 'LBDHCLK2', 181: 'LBDHCLK3', 182: 'RBDHCLK0', 183: 'RBDHCLK1', 184: 'RBDHCLK2',
    185: 'RBDHCLK3'
})
# These wires are a mystery, they are a copy of P10-P15 etc, there is no reason
# to have another number for the output, but it is these numbers that are
# listed in tables 38, although the internal routes are routed to the
# originals.
# In general they are needed and the letter A is added to make the names
# different.
clknames_pre5a.update({
     186: 'P10A', 187: 'P11A', 188: 'P12A', 189: 'P13A', 190: 'P14A', 191: 'P15A',
     192: 'P20A', 193: 'P21A', 194: 'P22A', 195: 'P23A', 196: 'P24A', 197: 'P25A',
     198: 'P30A', 199: 'P31A', 200: 'P32A', 201: 'P33A', 202: 'P34A', 203: 'P35A',
     204: 'P40A', 205: 'P41A', 206: 'P42A', 207: 'P43A', 208: 'P44A', 209: 'P45A',
})


clknames_pre5a.update({n: f"UNK{n}" for n in range(210, 277)})
clknames_pre5a[277] = 'VCC'
clknames_pre5a.update({n: f"UNK{n}" for n in range(278, 281)})

clknames_pre5a.update({291: "GT00", 292: "GT10"})

clknames_pre5a.update({n: f"UNK{n}" for n in range(501, 570)})

# HCLK->clock network
# Each HCLK can connect to other HCLKs through two MUXes in the clock system.
# Here we assign numbers to these MUXes and their inputs - two per HCLK
clknames_pre5a.update({
    1000: 'HCLKMUX0', 1001: 'HCLKMUX1',
    1002: 'HCLK0_BANK_OUT0', 1003: 'HCLK0_BANK_OUT1',
    1004: 'HCLK1_BANK_OUT0', 1005: 'HCLK1_BANK_OUT1',
    1006: 'HCLK2_BANK_OUT0', 1007: 'HCLK2_BANK_OUT1',
    1008: 'HCLK3_BANK_OUT0', 1009: 'HCLK3_BANK_OUT1',
})

clknames_pre5a.update({n: f"LWSPINETL{n - 1001}" for n in range(1001, 1009)})
clknames_pre5a.update({n: f"LWSPINETR{n - 1009}" for n in range(1009, 1017)})
clknames_pre5a.update({n: f"LWSPINEBL{n - 1017}" for n in range(1017, 1025)})
clknames_pre5a.update({n: f"LWSPINEBR{n - 1025}" for n in range(1025, 1033)})
clknames_pre5a.update({n: f"LWSPINEB1L{n - 1033}" for n in range(1033, 1041)})
clknames_pre5a.update({n: f"LWSPINEB1R{n - 1041}" for n in range(1041, 1049)})

clknames_pre5a.update({n: f"UNK{n}" for n in range(1049, 1225)})

clknumbers_pre5a = {v: k for k, v in clknames_pre5a.items()}

# hclk
hclknames_pre5a = clknames_pre5a.copy()
hclknames_pre5a.update({n: f"HCLK_UNK{n}" for n in range(26)})
# inputs
hclknames_pre5a.update({
    2: 'HCLK_IN0', 3: 'HCLK_IN1', 4: 'HCLK_IN2', 5: 'HCLK_IN3', 8: 'HCLK_BANK_IN0', 9: 'HCLK_BANK_IN1'
})

# HCLK section inputs
hclknames_pre5a.update({
    6: 'HCLK_BANK_OUT0', 7: 'HCLK_BANK_OUT1', 10: 'HCLK0_SECT0_IN', 11: 'HCLK0_SECT1_IN', 12: 'HCLK1_SECT0_IN', 13: 'HCLK1_SECT1_IN'
})

# Bypass connections from HCLK_IN to HCLK_OUT
hclknames_pre5a.update({
    16: 'HCLK_9IN0', 17: 'HCLK_9IN1', 18: 'HCLK_9IN2', 19: 'HCLK_9IN3'
})

# CLKDIV2 CLKOUT spurs on the GW1N-9C
hclknames_pre5a.update({
    20: 'HCLK_9_CLKDIV2_SECT0_OUT', 22:'HCLK_9_CLKDIV2_SECT2_OUT'
})

hclknames_pre5a[277] = 'VCC'
hclknames_pre5a[278] = 'VSS'


hclknumbers_pre5a = {v: k for k, v in hclknames_pre5a.items()}

""" *********************************************************************************
     Names and encoding of wires of the 5A series chips
    *********************************************************************************
"""
wirenames_5a25a = { 0: "A0", 1: "B0", 2: "C0", 3: "D0", 4: "A1", 5: "B1", 6: "C1", 7: "D1", 8: "A2", 9: "B2", 10: "C2", 11: "D2", 12: "A3", 13: "B3", 14: "C3",
15: "D3", 16: "A4", 17: "B4", 18: "C4", 19: "D4", 20: "A5", 21: "B5", 22: "C5", 23: "D5", 24: "A6", 25: "B6", 26: "C6", 27: "D6", 28: "A7", 29: "B7",
30: "C7", 31: "D7", 32: "F0", 33: "F1", 34: "F2", 35: "F3", 36: "F4", 37: "F5", 38: "F6", 39: "F7", 40: "Q0", 41: "Q1", 42: "Q2", 43: "Q3", 44: "Q4",
45: "Q5", 46: "Q6", 47: "Q7", 48: "OF0", 49: "OF1", 50: "OF2", 51: "OF3", 52: "OF4", 53: "OF5", 54: "OF6", 55: "OF7", 56: "X01", 57: "X02", 58: "X03",
59: "X04", 60: "X05", 61: "X06", 62: "X07", 63: "X08", 64: "N100", 65: "SN10", 66: "SN20", 67: "N130", 68: "S100", 69: "S130", 70: "E100", 71: "EW10",
72: "EW20", 73: "E130", 74: "W100", 75: "W130", 76: "N200", 77: "N210", 78: "N220", 79: "N230", 80: "N240", 81: "N250", 82: "N260", 83: "N270", 84: "S200",
85: "S210", 86: "S220", 87: "S230", 88: "S240", 89: "S250", 90: "S260", 91: "S270", 92: "E200", 93: "E210", 94: "E220", 95: "E230", 96: "E240", 97: "E250",
98: "E260", 99: "E270", 100: "W200", 101: "W210", 102: "W220", 103: "W230", 104: "W240", 105: "W250", 106: "W260", 107: "W270", 108: "N800", 109: "N810",
110: "N820", 111: "N830", 112: "S800", 113: "S810", 114: "S820", 115: "S830", 116: "E800", 117: "E810", 118: "E820", 119: "E830", 120: "W800", 121: "W810",
122: "W820", 123: "W830", 124: "CLK0", 125: "CLK1", 126: "CLK2", 127: "LSR0", 128: "LSR1", 129: "LSR2", 130: "CE0", 131: "CE1", 132: "CE2", 133: "SEL0",
134: "SEL1", 135: "SEL2", 136: "SEL3", 137: "SEL4", 138: "SEL5", 139: "SEL6", 140: "SEL7", 141: "N101", 142: "N131", 143: "S101", 144: "S131", 145: "E101", 146: "E131",
147: "W101", 148: "W131", 149: "N201", 150: "N211", 151: "N221", 152: "N231", 153: "N241", 154: "N251", 155: "N261", 156: "N271", 157: "S201", 158: "S211",
159: "S221", 160: "S231", 161: "S241", 162: "S251", 163: "S261", 164: "S271", 165: "E201", 166: "E211", 167: "E221", 168: "E231", 169: "E241", 170: "E251",
171: "E261", 172: "E271", 173: "W201", 174: "W211", 175: "W221", 176: "W231", 177: "W241", 178: "W251", 179: "W261", 180: "W271", 181: "N202", 182: "N212",
183: "N222", 184: "N232", 185: "N242", 186: "N252", 187: "N262", 188: "N272", 189: "S202", 190: "S212", 191: "S222", 192: "S232", 193: "S242", 194: "S252",
195: "S262", 196: "S272", 197: "E202", 198: "E212", 199: "E222", 200: "E232", 201: "E242", 202: "E252", 203: "E262", 204: "E272", 205: "W202", 206: "W212",
207: "W222", 208: "W232", 209: "W242", 210: "W252", 211: "W262", 212: "W272", 213: "N804", 214: "N814", 215: "N824", 216: "N834", 217: "S804", 218: "S814",
219: "S824", 220: "S834", 221: "E804", 222: "E814", 223: "E824", 224: "E834", 225: "W804", 226: "W814", 227: "W824", 228: "W834", 229: "N808", 230: "N818",
231: "N828", 232: "N838", 233: "S808", 234: "S818", 235: "S828", 236: "S838", 237: "E808", 238: "E818", 239: "E828", 240: "E838", 241: "W808", 242: "W818",
243: "W828", 244: "W838", 245: "E110", 246: "W110", 247: "E120", 248: "W120", 249: "S110", 250: "N110", 251: "S120", 252: "N120", 253: "E111", 254: "W111",
255: "E121", 256: "W121", 257: "S111", 258: "N111", 259: "S121", 260: "N121", 261: "LB01", 262: "LB11", 263: "LB21", 264: "LB31", 265: "LB41", 266: "LB51",
267: "LB61", 268: "LB71", 269: "GB00", 270: "GB10", 271: "GB20", 272: "GB30", 273: "GB40", 274: "GB50", 275: "GB60", 276: "GB70", 277: "VCC", 278: "VSS",
279: "LT00", 280: "LT10", 281: "LT20", 282: "LT30", 283: "LT02", 284: "LT13", 285: "LT01", 286: "LT04", 287: "LBO0", 288: "LBO1", 289: "SS00", 290: "SS40",
291: "GT00", 292: "GT10", 293: "GBO0", 294: "GBO1", 295: "DI0", 296: "DI1", 297: "DI2", 298: "DI3", 299: "DI4", 300: "DI5", 301: "DI6", 302: "DI7",
             303: "CIN0", 304: "CIN1", 305: "CIN2", 306: "CIN3", 307: "CIN4", 308: "CIN5", 309: "COUT0", 310: "COUT1", 311: "COUT2", 312: "COUT3", 313: "COUT4", 314: "COUT5", 315: "SPCLK_0", 316: "SPCLK_1"}

wirenames_5a25a.update({n: f"UNK{n}" for n in range(506, 569)})

wirenames_5a25a.update({n: f"LWSPINETL{n - 1001}" for n in range(1001, 1009)})
wirenames_5a25a.update({n: f"LWSPINETR{n - 1009}" for n in range(1009, 1017)})
wirenames_5a25a.update({n: f"LWSPINEBL{n - 1017}" for n in range(1017, 1025)})
wirenames_5a25a.update({n: f"LWSPINEBR{n - 1025}" for n in range(1025, 1033)})
wirenames_5a25a.update({n: f"LWSPINEB1L{n - 1033}" for n in range(1033, 1041)})
wirenames_5a25a.update({n: f"LWSPINEB1R{n - 1041}" for n in range(1041, 1049)})

wirenames_5a25a.update({n: f"UNK{n}" for n in range(1049, 1241)})

wirenames_5a25a.update({n: f"5A{n}" for n in range(545, 553)}) # GW5A-25A need these
wirenames_5a25a.update({n: f"5A{n}" for n in range(556, 564)}) # GW5A-25A need these

wirenumbers_5a25a = {v: k for k, v in wirenames_5a25a.items()}

clknames_5a25a = {}
clknames_5a25a.update({n: f"SPINE{n}" for n in range(32)})
clknames_5a25a.update({n: f"LWT{n - 32}" for n in range(32, 40)})
clknames_5a25a.update({n: f"LWB{n - 40}" for n in range(40, 48)})
# Apparently the names of the 8 primary clock wires comprise the quadrant
# number and the number of the actual clock wire: P34 stands for primary clock
# #4, 3rd quadrant. The quadrants are numbered counterclockwise:
# 2        1
#   center
# 3        4
# in addition, chips with two quadrants have quadrant numbers 3 and 4, not 1
# and 2 as you might expect.
# Wires 6 and 7 are the outputs of the dynamic 4-input MUX, the assumed
# numbers of these inputs are listed below:
clknames_5a25a.update({
     48: 'P16A', 49: 'P16B', 50: 'P16C', 51: 'P16D',
     52: 'P17A', 53: 'P17B', 54: 'P17C', 55: 'P17D',
     56: 'P26A', 57: 'P26B', 58: 'P26C', 59: 'P26D',
     60: 'P27A', 61: 'P27B', 62: 'P27C', 63: 'P27D',
     64: 'P36A', 65: 'P36B', 66: 'P36C', 67: 'P36D',
     68: 'P37A', 69: 'P37B', 70: 'P37C', 71: 'P37D',
     72: 'P46A', 73: 'P46B', 74: 'P46C', 75: 'P46D',
     76: 'P47A', 77: 'P47B', 78: 'P47C', 79: 'P47D'
})
clknames_5a25a[80] = 'VSS'
# each PLL has 4 delay-critical outputs (clkout, clkoutp, clkoutd, clkoutd3),
# their numbers are listed here, the names indicate the possible location of
# the PLL (Top Left etc):
clknames_5a25a.update({
     81: 'PLL4CLKOUT0',  82: 'PLL4CLKOUT1',  83: 'PLL4CLKOUT2',  84: 'PLL4CLKOUT3',
     85: 'PLL4CLKOUT4',  86: 'PLL4CLKOUT5',  87: 'PLL4CLKOUT6',  88: 'PLL4CLKOUT7',
     89: 'PLL3CLKOUT0',  90: 'PLL3CLKOUT1',  91: 'PLL3CLKOUT2',  92: 'PLL3CLKOUT3',
     93: 'PLL3CLKOUT4',  94: 'PLL3CLKOUT5',  95: 'PLL3CLKOUT6',  96: 'PLL3CLKOUT7',
     97: 'PLL2CLKOUT0',  98: 'PLL2CLKOUT1',  99: 'PLL2CLKOUT2', 100: 'PLL2CLKOUT3',
    101: 'PLL2CLKOUT4', 102: 'PLL2CLKOUT5', 103: 'PLL2CLKOUT6', 104: 'PLL2CLKOUT7',
    105: 'PLL8CLKOUT0', 106: 'PLL8CLKOUT1', 107: 'PLL8CLKOUT2', 108: 'PLL8CLKOUT3',
    109: 'PLL8CLKOUT4', 110: 'PLL8CLKOUT5', 111: 'PLL8CLKOUT6', 112: 'PLL8CLKOUT7',
    113: 'PLL6CLKOUT0', 114: 'PLL6CLKOUT1', 115: 'PLL6CLKOUT2', 116: 'PLL6CLKOUT3',
    117: 'PLL6CLKOUT4', 118: 'PLL6CLKOUT5', 119: 'PLL6CLKOUT6', 120: 'PLL6CLKOUT7',
    121: 'PLL5CLKOUT0', 122: 'PLL5CLKOUT1', 123: 'PLL5CLKOUT2', 124: 'PLL5CLKOUT3',
    125: 'PLL5CLKOUT4', 126: 'PLL5CLKOUT5', 127: 'PLL5CLKOUT6', 128: 'PLL5CLKOUT7',
 })

clknames_5a25a.update({
    129: 'TRBDCLK0', 130: 'TRBDCLK1', 131: 'TRBDCLK2', 132: 'TRBDCLK3',
    133: 'TLBDCLK0', 134: 'TLBDCLK1', 135: 'TLBDCLK2', 136: 'TLBDCLK3',
    137: 'BRBDCLK0', 138: 'BRBDCLK1', 139: 'BRBDCLK2', 140: 'BRBDCLK3',
    141: 'BLBDCLK0', 142: 'BLBDCLK1', 143: 'BLBDCLK2', 144: 'BLBDCLK3',
    145: 'TRMDCLK0', 146: 'TRMDCLK1', 147: 'TLMDCLK0', 148: 'TLMDCLK1',
    149: 'BRMDCLK0', 150: 'BRMDCLK1', 151: 'BLMDCLK0', 152: 'BLMDCLK1',
})
#clknames_5a25a[153] = 'VCC'

clknames_5a25a.update({n: f"UNK{n}" for n in range(153, 170)})

# HCLK
clknames_5a25a.update({
    169: 'TBDHCLK0', 170: 'TBDHCLK1', 171: 'TBDHCLK2', 172: 'TBDHCLK3',
    173: 'RBDHCLK0', 174: 'RBDHCLK1', 175: 'RBDHCLK2', 176: 'RBDHCLK3',
    177: 'BBDHCLK0', 178: 'BBDHCLK1', 179: 'BBDHCLK2', 180: 'BBDHCLK3',
    181: 'LBDHCLK0', 182: 'LBDHCLK1', 183: 'LBDHCLK2', 184: 'LBDHCLK3',
})


clknames_5a25a.update({n: f"UNK{n}" for n in range(185, 277)})
clknames_5a25a[277] = 'VCC'
clknames_5a25a.update({n: f"UNK{n}" for n in range(278, 281)})

clknames_5a25a.update({291: "GT00", 292: "GT10"})

clknames_5a25a.update({
    501: 'MPLL4CLKOUT0', 502: 'MPLL4CLKOUT1', 503: 'MPLL4CLKOUT2', 504: 'MPLL4CLKOUT3',
    505: 'MPLL4CLKOUT4', 506: 'MPLL4CLKOUT5', 507: 'MPLL4CLKOUT6', 508: 'MPLL4CLKFBOUT',
    509: 'MPLL4CLKIN2',  510: 'MPLL4CLKIN6',  511: 'MPLL4CLKIN7',
    512: 'MPLL3CLKOUT0', 513: 'MPLL3CLKOUT1', 514: 'MPLL3CLKOUT2', 515: 'MPLL3CLKOUT3',
    516: 'MPLL3CLKOUT4', 517: 'MPLL3CLKOUT5', 518: 'MPLL3CLKOUT6', 519: 'MPLL3CLKFBOUT',
    520: 'MPLL3CLKIN2',  521: 'MPLL3CLKIN6',  522: 'MPLL3CLKIN7',
    523: 'MPLL2CLKOUT0', 524: 'MPLL2CLKOUT1', 525: 'MPLL2CLKOUT2', 526: 'MPLL2CLKOUT3',
    527: 'MPLL2CLKOUT4', 528: 'MPLL2CLKOUT5', 529: 'MPLL2CLKOUT6', 530: 'MPLL2CLKFBOUT',
    531: 'MPLL2CLKIN2',  532: 'MPLL2CLKIN6',  533: 'MPLL2CLKIN7',
    534: 'MPLL8CLKOUT0', 535: 'MPLL8CLKOUT1', 536: 'MPLL8CLKOUT2', 537: 'MPLL8CLKOUT3',
    538: 'MPLL8CLKOUT4', 539: 'MPLL8CLKOUT5', 540: 'MPLL8CLKOUT6', 541: 'MPLL8CLKFBOUT',
    542: 'MPLL8CLKIN2',  543: 'MPLL8CLKIN6',  544: 'MPLL8CLKIN7',
    545: 'MPLL6CLKOUT0', 546: 'MPLL6CLKOUT1', 547: 'MPLL6CLKOUT2', 548: 'MPLL6CLKOUT3',
    549: 'MPLL6CLKOUT4', 550: 'MPLL6CLKOUT5', 551: 'MPLL6CLKOUT6', 552: 'MPLL6CLKFBOUT',
    553: 'MPLL6CLKIN2',  554: 'MPLL6CLKIN6',  555: 'MPLL6CLKIN7',
    556: 'MPLL5CLKOUT0', 557: 'MPLL5CLKOUT1', 558: 'MPLL5CLKOUT2', 559: 'MPLL5CLKOUT3',
    560: 'MPLL5CLKOUT4', 561: 'MPLL5CLKOUT5', 562: 'MPLL5CLKOUT6', 563: 'MPLL5CLKFBOUT',
    564: 'MPLL5CLKIN2',  565: 'MPLL5CLKIN6',  566: 'MPLL5CLKIN7',
})
clknames_5a25a.update({n: f"UNK{n}" for n in range(567, 570)})

# HCLK->clock network
# Each HCLK can connect to other HCLKs through two MUXes in the clock system.
# Here we assign numbers to these MUXes and their inputs - two per HCLK
clknames_5a25a.update({
    1000: 'HCLKMUX0', 1001: 'HCLKMUX1',
    1002: 'HCLK0_BANK_OUT0', 1003: 'HCLK0_BANK_OUT1',
    1004: 'HCLK1_BANK_OUT0', 1005: 'HCLK1_BANK_OUT1',
    1006: 'HCLK2_BANK_OUT0', 1007: 'HCLK2_BANK_OUT1',
    1008: 'HCLK3_BANK_OUT0', 1009: 'HCLK3_BANK_OUT1',
})

clknames_5a25a.update({n: f"LWSPINETL{n - 1001}" for n in range(1001, 1009)})
clknames_5a25a.update({n: f"LWSPINETR{n - 1009}" for n in range(1009, 1017)})
clknames_5a25a.update({n: f"LWSPINEBL{n - 1017}" for n in range(1017, 1025)})
clknames_5a25a.update({n: f"LWSPINEBR{n - 1025}" for n in range(1025, 1033)})
clknames_5a25a.update({n: f"LWSPINEB1L{n - 1033}" for n in range(1033, 1041)})
clknames_5a25a.update({n: f"LWSPINEB1R{n - 1041}" for n in range(1041, 1049)})

clknames_5a25a.update({n: f"UNK{n}" for n in range(1049, 1225)})

clknumbers_5a25a = {v: k for k, v in clknames_5a25a.items()}

# hclk
hclknames_5a25a = clknames_5a25a.copy()

hclknames_5a25a[0] = 'VSS'
hclknames_5a25a[1] = 'VCC'
hclknames_5a25a[187] = 'VSS'
hclknames_5a25a[188] = 'VCC'
hclknames_5a25a[374] = 'VSS'
hclknames_5a25a[375] = 'VCC'
hclknames_5a25a[561] = 'VSS'
hclknames_5a25a[562] = 'VCC'

hclknames_5a25a.update({n: f"HCLK_UNK{n}" for n in range(2, 701)})

# HCLK->CLK
hclknames_5a25a.update({n: f"HCLK_TO_GCLK0{i}" for i, n in enumerate([25, 27, 28, 29])})
hclknames_5a25a.update({n: f"HCLK_TO_GCLK1{i}" for i, n in enumerate([212, 214, 215, 216])})
hclknames_5a25a.update({n: f"HCLK_TO_GCLK2{i}" for i, n in enumerate([399, 401, 402, 403])})
hclknames_5a25a.update({n: f"HCLK_TO_GCLK3{i}" for i, n in enumerate([586, 588, 589, 590])})

# GCLK pins
hclknames_5a25a.update({n: f"HCLK_GCLK0{i}" for i, n in enumerate(range(123, 131))})
hclknames_5a25a.update({n: f"HCLK_GCLK1{i}" for i, n in enumerate(range(310, 318))})
hclknames_5a25a.update({n: f"HCLK_GCLK2{i}" for i, n in enumerate(range(497, 505))})
hclknames_5a25a.update({n: f"HCLK_GCLK3{i}" for i, n in enumerate(range(684, 692))})

hclknumbers_5a25a = {v: k for k, v in hclknames_5a25a.items()}

# Switcher
wirenames   = None
wirenumbers = None
clknames    = None
clknumbers  = None
hclknames   = None
hclknumbers = None

def select_wires(device):
    global wirenames, clknames, hclknames, wirenumbers, clknumbers, hclknumbers
    if device in {'GW5A-25A'}:
        wirenames   = wirenames_5a25a
        wirenumbers = wirenumbers_5a25a
        clknames    = clknames_5a25a
        clknumbers  = clknumbers_5a25a
        hclknames   = hclknames_5a25a
        hclknumbers = hclknumbers_5a25a
    else:
        wirenames   = wirenames_pre5a
        wirenumbers = wirenumbers_pre5a
        clknames    = clknames_pre5a
        clknumbers  = clknumbers_pre5a
        hclknames   = hclknames_pre5a
        hclknumbers = hclknumbers_pre5a



