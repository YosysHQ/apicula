# These constants are used to interact with the 'logicinfo', 'shortval' and maybe 'longval' tables
# * - it seems that these attributes must always be present (XXX)
iob_attrids = {
        'IO_TYPE':               0,
        'SLEWRATE':              1, # *
        'PULLMODE':              2, # *
        'DRIVE':                 3, # *
        'OPENDRAIN':             4, # *
        'HYSTERESIS':            5, # *
        'CLAMP':                 6, # *
        'DIFFRESISTOR':          7, # *
        'SINGLERESISTOR':        8, # *
        'VREF':                  9, # *
        'VCCIO':                 10,
        'DIFFDRIVE':             11,
        'I3C_MODE':              12,
        'MIPI_INPUT':            13,
        'MIPI_OUTPUT':           14,
        'DRIVE_LEVEL':           15,
        'LVDS_OUT':              16, # *
        'LVDS_VCCIO':            17,
        'DDR_DYNTERM':           18,
        'IO_BANK':               19, # *
        'PERSISTENT':            20, # *
        'TO':                    21,
        'ODMUX':                 22,
        'ODMUX_1':               23,
        'PADDI':                 24,
        'PG_MUX':                25,
        'DATA_MUX':              26,
        'TRI_MUX':               27,
        'TRIMUX_PADDT'           28,
        'IOBUF_PADDI'            29,
        'USED'                   30, # *
        'IOBUF_OVERDRIVE':       31,
        'IOBUF_UNDERDRIVE':      32,
        'IOBUF_LVDS25_VCCIO':    33,
        'IN12_MODE':             34,
        'OD':                    35,
        'LPRX_A1':               36,
        'LPRX_A2':               37,
        'MIPI':                  38,
        'LVDS_SEL':              39,
        'VLDS_ON':               40,
        'IOBUF_MIPI_LP':         41,
        'IOBUF_ODT_RESISTOR':    42,
        'IOBUF_CIB_CONTROL':     43,
        'IOBUF_INR_MODE':        44,
        'IOBUF_STDBY_LVDS_MODE': 45,
        'IOBUF_IODUTY':          46,
        'IOBUF_ODT_DYNTERM':     47,
        'MIPI_IBUF_DRIVE':       48,
        'MIPI_IBUF_DRIVE_LEVEL': 49
        }

iob_attrvals = {
            'UNKNOWN':          0, # possible a dummy value for line 0 in logicinfo?
            # standard
            'MIPI':             1,
            'BLVDS25E':         2,
            'BLVDS25':          3,
            'BLVDS_E':          4,
            'HSTL':             5,
            'HSTL_D':           6,
            'HSTL15_I':         7,
            'HSTL15D_I':        8,
            'HSTL18_I':         9,
            'HSTL18_II':        10,
            'HSTL18D_I':        11,
            'HSTL18D_II':       12,
            'SSTL':             13,
            'SSTL_D':           14,
            'SSTL15':           15,
            'SSTL15D':          16,
            'SSTL18_I':         17,
            'SSTL18_II':        18,
            'SSTL18D_I':        19,
            'SSTL18D_II':       20,
            'SSTL25_I':         21,
            'SSTL25_II':        22,
            'SSTL25D_I':        23,
            'SSTL25D_II':       24,
            'SSTL33_I':         25,
            'SSTL33_II':        26,
            'SSTL33D_I':        27,
            'SSTL33D_II':       28,
            'LVCMOS12':         29,
            'LVCMOS15':         30,
            'LVCMOS18':         31,
            'LVCMOS25':         32,
            'LVCMOS33':         33,
            'LVCMOS_D':         34,
            'LVCMOS12D':        35,
            'LVCMOS15D':        36,
            'LVCMOS18D':        37,
            'LVCMOS25D':        38,
            'LVCMOS33D':        39,
            'LVDS':             40,
            'LVDS_E':           41,
            'LVDS25':           42,
            'LVDS25E':          43,
            'LVPECL33':         44,
            'LVPECL33E':        45,
            'LVTTL33':          46,
            'MLVDS25':          47,
            'MLVDS_E':          48,
            'MLVDS25E':         49,
            'RSDS25E':          50,
            'PCI33':            51,
            'RSDS':             52,
            'RSDS25':           53,
            'RSDS_E':           54,
            'MINILVDS':         55,
            'PPLVDS':           56,
            #
            'VREF1_DRIVER':     57,
            'VREF2_DRIVER':     58,
            'LVCMOS33OD25':     59,
            'LVCMOS33OD18':     60,
            'LVCMOS33OD15':     61,
            'LVCMOS25OD18':     62,
            'LVCMOS25OD15':     63,
            'LVCMOS18OD15':     64,
            'LVCMOS15OD12':     65,
            'LVCMOS25UD33':     66,
            'LVCMOS18UD25':     67,
            'LVCMOS18UD33':     68,
            'LVCMOS15UD18':     69,
            'LVCMOS15UD25':     70,
            'LVCMOS15UD33':     71,
            'LVCMOS12UD15':     72,
            'LVCMOS12UD18':     73,
            'LVCMOS12UD25':     74,
            'LVCMOS12UD33':     75,
            'VREF1_LOAD':       76,
            'VREF2_LOAD':       77,
            #
            'ENABLE':           78,
            'TRIMUX':           79,
            'PADDI':            80,
            'PGBUF':            81,
            '0':                82,
            '1':                83,
            'SIG':              84,
            'INV':              85,
            'TO':               86,
            # voltage
            '1.2':              87,
            '1.25':             88,
            '1.5':              89,
            '1.8':              90,
            '2.0':              91,
            '2.5':              92,
            '3.3':              93,
            '3.5':              94,
            # mA
            '2':                95,
            '4':                96,
            '6':                97,
            '8':                98,
            '12':               99,
            '16':               100,
            '20':               101,
            '24':               102,
            # XXX ?
            '80':               103,
            '100':              104,
            '120':              105,
            #
            'NA':               106,
            'ON':               107,
            'OFF':              108,
            # XXX
            'PCI':              109,
            # histeresis
            'HIGH':             110,
            'H2L':              111,
            'L2H':              112,
            # pullmode
            'DOWN':             113,
            'KEEPER':           114,
            'NONE':             115,
            'UP':               116,
            # slew
            'FAST':             117,
            'SLOW':             118,
            #
            'I45':              119.
            'I50':              120,
            'I55':              121,
            'TSREG'             122,
            'TMDDR':            123,
            'OD1':              124,
            'OD2':              125,
            'OD3':              126,
            'UD1':              127,
            'UD3':              128,
            # resistor?
            'INTERNAL':         129,
            'SINGLE':           130,
            'DIFF':             131,
            #
            'IN12':             132,
            'UD2':              133,
            'LVPECL_E':         134,
            #
            '68':               135,
            '3':                136,
            '5':                137,
            '7':                138,
            '9':                139,
            '10':               140,
            '11':               141,
            '4.5':              142,
            'MIPI_IBUF':        143,
            '1.35':             144,
            '5.5':              145,
            '6.5':              146,
            '10.5':             147,
            '13.5':             148,
            '14':               149,
            # more standard
            'TMDS33':           150,
            'LPDDR':            151,
            'HSUL12':           152,
            'HSUL12D':          153,
            'HSTL12_I':         154,
            'HSTL15_II':        155,
            'HSTL15D_II':       156,
            'SSTL12':           157,
            'SSTL135':          158,
            'SSTL135D':         159,
            'LVCMOS10':         160,
            'LVCMOS33OD12':     161,
            'LVCMOS25OD12':     162,
            'LVCMOS18OD12':     163,
        }
