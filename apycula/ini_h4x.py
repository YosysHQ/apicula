import re, csv, os, sys
from enum import Enum
from pathlib import Path
import argparse

"""
Known IO Features
    name -> string representation
    count -> -1 if this feature has only a single option, the size (in bytes) of the encoding of number of options otherwise
    size -> number of bytes used to encode an option
    list -> True if this feature has multiple configuration options, false otherwise
"""
class IOF(Enum):
    TYPE = {"name":"Type", "count":-1, "size":4, "list":False}
    DRIVE = {"name": "Drive", "count": 2, "size":4, "list":True}
    DIFF_DRIVE = {"name": "Differential Drive", "count": 2, "size":4, "list":True}
    OPEN_DRAIN = {"name": "Open Drain", "count": 2, "size":4, "list":True}
    SLEW_RATE = {"name": "Slew Rate", "count": 2, "size":4, "list":True}
    CLAMP = {"name": "Clamp", "count": 2, "size":4, "list":True}
    VREF = {"name": "Voltage Reference", "count": 2, "size":4, "list":True}
    HYSTERISIS = {"name": "Hysterisis", "count": 2, "size":4, "list":True}
    PULL_MODE = {"name": "Pull Mode", "count": 2, "size":4, "list":True}
    SINGLE_RES = {"name": "Single Resistor", "count": 2, "size":4, "list":True}
    DIFF_RES = {"name": "Differential Resistor", "count": 2, "size":4, "list":True}
    VCC_IO = {"name": "VCC IO", "count": 2, "size":4, "list":True}
    I3C_MODE = {"name": "I3C Mode", "count": 2, "size":4, "list":True}
    MIPI_INPUT = {"name": "MIPI Input", "count": 2, "size":4, "list":True}
    MIPI_OUTPUT = {"name": "MIPI Output", "count": 2, "size":4, "list":True}
    PULL_STRENGTH = {"name": "PULL STRENGTH", "count": 2, "size":4, "list":True}
    BANK = {"name": "Bank", "count": 2, "size":4, "list":True}
    MODE = {"name": "Mode", "count": -1, "size":4, "list":False}


"""
Structure of Known .ini files
    align_start -> number of bytes used to encode the start alignment
    features -> *ordered* list of configurable IO features
    input -> number of input IO configuration points (each configuration point has options for all features)
    output -> number of output IO configuration points
    bidirectional -> number of bidirectional IO configuration points
    i3c_bank -> True if the device has an i3c_bank, False otherwise
    align_end -> number of bytes used to encode the end alignment
"""
schemas = [
    {
        "devices": ['GW1N-1', 'GW1NR-1'],
        "align_start": 2, 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.PULL_MODE, IOF.SINGLE_RES, IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3b,
        "output": 0x25,
        "bidirectional": 0x25,
        "i3c_bank": False,
        "align_end": 2
    },

     {
        "devices": ['GW1N-4', 'GW1NR-4', 'GW1NRF-4', 'GW1N-4D', 'GW1NR-4D'],
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.PULL_MODE, IOF.SINGLE_RES, IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3b,
        "output": 0x29,
        "bidirectional": 0x29,
        "i3c_bank": False,
        "align_end": 2
    },

    {
        "devices": ['GW1N-2', 'GW1NZ-2', 'GW1NR-2', 'GW1NZR-2', 'GW1N-1P5', 'GW1N-2B', 'GW1NR-2B', 'GW1N-1P5B', 'GW1N-2C', 'GW1NR-2C', 'GW1N-1P5C', 'GW1NZ-2B', 'GW1NZ-2C'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT, IOF.MIPI_OUTPUT, IOF.PULL_MODE, IOF.SINGLE_RES,
                    IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3c,
        "output": 0x2a,
        "bidirectional": 0x26,
        "i3c_bank": True,
        "align_end": 2
    },
    
    {
        "devices": ['GW1N-6', 'GW1N-9', 'GW1NR-9', 'GW1N-9C', 'GW1NR-9C', 'GW1NS-2', 'GW1NSR-2'],
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT, IOF.MIPI_OUTPUT, IOF.PULL_MODE, IOF.SINGLE_RES,
                    IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3c,
        "output": 0x2a,
        "bidirectional": 0x26,
        "i3c_bank": True,
        "align_end": 2
    },

    {
        "devices": ['GW1NZ-1', 'GW1NZ-1C'],
        "features": [IOF.TYPE, IOF.DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.HYSTERISIS, IOF.PULL_MODE, 
                     IOF.VCC_IO, IOF.MODE],
        "input": 0x18,
        "output": 0x0c,
        "bidirectional": 7,
        "i3c_bank": False,
        "align_end": 2
    },

    {
        "devices": ['GW1N-1S'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.MIPI_INPUT, IOF.PULL_MODE, IOF.SINGLE_RES, IOF.DIFF_RES, IOF.VCC_IO],
        "input": 0x38,
        "output": 0x25,
        "bidirectional": 0x25,
        "i3c_bank": False,
        "align_end": 2

    },

     {
        "devices": ['GW1NS-4', 'GW1NSR-4'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT, IOF.MIPI_OUTPUT, IOF.PULL_MODE, IOF.SINGLE_RES, 
                     IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3c,
        "output": 0x2a,
        "bidirectional": 0x26,
        "i3c_bank": True,
        "align_end": 2
    }, 

    {
        "devices": ['GW2A-18', 'GW2A-55', 'GW2AR-18', 'GW2A-55C', 'GW2A-18C', 'GW2AR-18C', 'GW2ANR-18C', 'GW2AN-55C'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.PULL_MODE, IOF.SINGLE_RES, IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x3b, 
        "output": 0x29,
        "bidirectional": 0x29,
        "i3c_bank": False,
        "align_end": 2
    },

    {
        "devices": ['GW5AT-138'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT, IOF.MIPI_OUTPUT, IOF.PULL_MODE, IOF.SINGLE_RES, 
                     IOF.DIFF_RES, IOF.VCC_IO, IOF.MODE],
        "input": 0x39,
        "output": 0x2e,
        "bidirectional": 0x2c,
        "i3c_bank": True,
        "align_end": 2
    },

    {
        "devices": ['GW2AN-18X', 'GW2AN-9X'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT, IOF.PULL_MODE, IOF.SINGLE_RES, IOF.DIFF_RES, 
                     IOF.VCC_IO, IOF.MODE],
        "input": 0x3c,
        "output": 0x29,
        "bidirectional": 0x25,
        "i3c_bank": True,
        "align_end": 2
    },

    {
        "devices": ['GW5AT-138B', 'GW5AST-138B', 'GW5A-138B', 'GW5AS-138B'], 
        "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT,  IOF.MIPI_OUTPUT, IOF.PULL_STRENGTH, IOF.PULL_MODE, 
                     IOF.SINGLE_RES, IOF.DIFF_RES, IOF.BANK,  IOF.VCC_IO, IOF.MODE],
        "input": 0x3b,
        "output": 0x2e,
        "bidirectional": 0x2c,
        "i3c_bank": True,
        "align_end": 2
    },

    {
        "devices": ['GW5AT-60'], 
         "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT,  IOF.MIPI_OUTPUT, IOF.PULL_STRENGTH, IOF.PULL_MODE, 
                     IOF.SINGLE_RES, IOF.DIFF_RES, IOF.BANK,  IOF.VCC_IO, IOF.MODE],
        "input": 0x52,
        "output": 0x37,
        "bidirectional": 0x36,
        "i3c_bank": True,
        "align_end": 2
    },

    {
        "devices": ['GW5A-25A', 'GW5AR-25A'], 
         "features": [IOF.TYPE, IOF.DRIVE, IOF.DIFF_DRIVE, IOF.OPEN_DRAIN, IOF.SLEW_RATE, IOF.CLAMP, IOF.VREF, 
                     IOF.HYSTERISIS, IOF.I3C_MODE, IOF.MIPI_INPUT,  IOF.MIPI_OUTPUT, IOF.PULL_STRENGTH, IOF.PULL_MODE, 
                     IOF.SINGLE_RES, IOF.DIFF_RES, IOF.BANK,  IOF.VCC_IO, IOF.MODE],
        "input": 0x52,
        "output": 0x37,
        "bidirectional": 0x36,
        "i3c_bank": True,
        "align_end": 2
    }
]

"""
Known mapping of PIO binary-file options to strings
"""
PIO_STR_MAPPINGS = {0: 'UNKNOWN', 1: 'MIPI', 2: 'BLVDS25E', 3: 'BLVDS25', 4: 'BLVDS_E', 5: 'HSTL', 6: 'HSTL_D', 7: 'HSTL15_I', 8: 'HSTL15D_I', 
                   9: 'HSTL18_I', 10: 'HSTL18_II', 11: 'HSTL18D_I', 12: 'HSTL18D_II', 13: 'SSTL', 14: 'SSTL_D', 15: 'SSTL15', 16: 'SSTL15D', 
                   17: 'SSTL18_I', 18: 'SSTL18_II', 19: 'SSTL18D_I', 20: 'SSTL18D_II', 21: 'SSTL25_I', 22: 'SSTL25_II', 23: 'SSTL25D_I', 
                   24: 'SSTL25D_II', 25: 'SSTL33_I', 26: 'SSTL33_II', 27: 'SSTL33D_I', 28: 'SSTL33D_II', 29: 'LVCMOS12', 30: 'LVCMOS15', 
                   31: 'LVCMOS18', 32: 'LVCMOS25', 33: 'LVCMOS33', 34: 'LVCMOS_D', 35: 'LVCMOS12D', 36: 'LVCMOS15D', 37: 'LVCMOS18D', 
                   38: 'LVCMOS25D', 39: 'LVCMOS33D', 40: 'LVDS', 41: 'LVDS_E', 42: 'LVDS25', 43: 'LVDS25E', 44: 'LVPECL33', 45: 'LVPECL33E', 
                   46: 'LVTTL33', 47: 'MLVDS25', 48: 'MLVDS_E', 49: 'MLVDS25E', 50: 'RSDS25E', 51: 'PCI33', 52: 'RSDS', 53: 'RSDS25', 
                   54: 'RSDS_E', 55: 'MINILVDS', 56: 'PPLVDS', 57: 'VREF1_DRIVER', 58: 'VREF2_DRIVER', 59: 'LVCMOS33OD25', 60: 'LVCMOS33OD18', 
                   61: 'LVCMOS33OD15', 62: 'LVCMOS25OD18', 63: 'LVCMOS25OD15', 64: 'LVCMOS18OD15', 65: 'LVCMOS15OD12', 66: 'LVCMOS25UD33', 
                   67: 'LVCMOS18UD25', 68: 'LVCMOS18UD33', 69: 'LVCMOS15UD18', 70: 'LVCMOS15UD25', 71: 'LVCMOS15UD33', 72: 'LVCMOS12UD15', 
                   73: 'LVCMOS12UD18', 74: 'LVCMOS12UD25', 75: 'LVCMOS12UD33', 76: 'VREF1_LOAD', 77: 'VREF2_LOAD', 78: 'ENABLE', 79: 'TRIMUX', 
                   80: 'PADDI', 81: 'PGBUF', 82: '0', 83: '1', 84: 'SIG', 85: 'INV', 86: 'TO', 87: '1.2', 88: '1.25', 89: '1.5', 90: '1.8', 
                   91: '2.0', 92: '2.5', 93: '3.3', 94: '3.5', 95: '2', 96: '4', 97: '6', 98: '8', 99: '12', 100: '16', 101: '20', 102: '24', 
                   103: '80', 104: '100', 105: '120', 106: 'NA', 107: 'ON', 108: 'OFF', 109: 'PCI', 110: 'HIGH', 111: 'H2L', 112: 'L2H', 
                   113: 'DOWN', 114: 'KEEPER', 115: 'NONE', 116: 'UP', 117: 'FAST', 118: 'SLOW', 119: 'I45', 120: 'I50', 121: 'I55', 122: 'TSREG', 
                   123: 'TMDDR', 124: 'OD1', 125: 'OD2', 126: 'OD3', 127: 'UD1', 128: 'UD3', 129: 'INTERNAL', 130: 'SINGLE', 131: 'DIFF', 
                   132: 'IN12', 133: 'UD2', 134: 'LVPECL_E', 135: '68', 136: '3', 137: '5', 138: '7', 139: '9', 140: '10', 141: '11', 142: '4.5', 
                   143: 'MIPI_IBUF', 144: '1.35', 145: '5.5', 146: '6.5', 147: '10.5', 148: '13.5', 149: '14', 150: 'TMDS33', 151: 'LPDDR', 
                   152: 'HSUL12', 153: 'HSUL12D', 154: 'HSTL12_I', 155: 'HSTL15_II', 156: 'HSTL15D_II', 157: 'SSTL12', 158: 'SSTL135', 
                   159: 'SSTL135D', 160: 'LVCMOS10', 161: 'LVCMOS33OD12', 162: 'LVCMOS25OD12', 163: 'LVCMOS18OD12', 164: 'HSTL12D_I', 
                   165: 'LVCMOS10D', 166: 'LVCMOS10UD12', 167: 'LVCMOS10UD15', 168: 'LVCMOS10UD18', 169: 'LVCMOS10UD25', 170: 'LVCMOS10UD33', 
                   171: 'LVCMOS15OD10', 172: 'LVCMOS18OD10', 173: '40', 174: '50', 175: '60', 176: '75', 177: '0.333VCCIO', 178: '0.417VCCIO', 
                   179: '0.583VCCIO', 180: '0.6V', 181: '0.675V', 182: '0.75V', 183: '0.9V', 184: '1.25V', 185: '1.5V', 186: 'MEDIUM', 187: 'WEAK', 
                   188: 'STRONG', 189: 'VCCX', 190: '1.0', 191: '1.375', 192: '134', 193: '139', 194: '145', 195: '150', 196: '72', 197: '74', 
                   198: '77', 199: '85', 200: '86', 201: '89', 202: '91', 203: '106', 204: '108', 205: '112', 206: '115', 207: '128', 208: '132', 
                   209: '172', 210: '180', 211: '82', 212: '84', 213: '99', 214: '101', 215: '123', 216: '164', 217: '96', 218: '157', 219: '79', 
                   220: '93', 221: '124', 222: '70', 223: '88', 224: '92', 225: '94', 226: '98', 227: '78', 228: '76', 229: '118', 235: '102', 
                   236: 'LPDDRD', 238: 'LVCMOS25OD10', 239: 'LVCMOS33OD10', 240: 'LVCMOS12OD10', 241: 'SSTL2D_I', 242: 'SSTL2D_II', 243: 'SSTL3D_I', 
                   244: 'SSTL3D_II', 245: 'SSTL12D_I', 246: 'SSTL15D_I', 247: 'SSTL135D_I', 248: 'SSTL2_I', 249: 'SSTL2_II', 250: 'SSTL3_I', 
                   251: 'SSTL3_II', 252: 'SSTL12_I', 253: 'SSTL15_I', 254: 'SSTL135_I', 255: 'ADC_IN', 256: '25', 257: '90', 258: '122', 259: '130', 
                   260: '0.5VCCIO', 261: '0.643VCCIO', 262: '0.357VCCIO', 298: 'LOW', 299: 'UHIGH'}

class IniParser:
    def __init__ (self, device:str, schema:dict=None, ini_file:str|Path=None, pio_str_mappings:Path|dict[int: str]=PIO_STR_MAPPINGS):
        self.device = device

        if schema is None:
            schema_options = [x for x in schemas if device.upper() in x["devices"]]
            if schema_options:
                self.schema = schema_options[0]
            else:
                self.schema = None
        else:
            self.schema = schema

        if not self.schema:
            raise Exception(f"No schema supplied/found for device {self.device}")
        
        self.ini_file = ini_file
        self.input = {}
        self.output = {}
        self.bidirectional = {}
        self.i3c_bank = []
        self.__pointer = 0
        self.byte_array = []

        if isinstance(pio_str_mappings, str) or isinstance(pio_str_mappings, Path):

            self.pio_str_mappings = {}
            self.str_pio_mappings = {}
            with open (pio_str_mappings, "r") as f:
                reader = csv.reader(f)
                for line in reader:
                    id, string, id_hex = line
                    id = int(id)
                    self.pio_str_mappings[id] = string
                    self.str_pio_mappings[string] = id

        elif isinstance(pio_str_mappings, dict):
            self.pio_str_mappings = pio_str_mappings
            self.str_pio_mappings = {v: k for k, v in self.pio_str_mappings.items()}
    
    def parse(self, ini_file=None):
        self.__pointer=0

        if ini_file is None or not ini_file:
            gowinhome = os.getenv("GOWINHOME")
            if not gowinhome:
                raise Exception("GOWINHOME not set")
            ini_file = f"{gowinhome}/IDE/share/device/{self.device}/{self.device}.ini"
    
        with open(ini_file, 'rb') as f:
            self.byte_array = f.read() #The ini files are pretty small so this is fine
            features = self.schema["features"]
            input_lines = self.schema["input"]
            output_lines = self.schema["output"]
            bidirectional_lines = self.schema["bidirectional"]
            i3c_bank = self.schema["i3c_bank"]

            start_align = self.__read_val(word_size=2, byteorder="little")
            assert start_align==1, "Start alignment incorrect, parsing failed"
            
            for idx in range(input_lines):
                self.input[idx] = {}
                curr_input = self.input[idx]
                
                for feature in features:
                    curr_input[feature] = self.__read_feature(feature)
            
            for idx in range(output_lines):
                self.output[idx] = {}
                curr_output = self.output[idx]
                
                for feature in features: 
                    curr_output[feature] = self.__read_feature(feature)
            
            for idx in range(bidirectional_lines):
                self.bidirectional[idx] = {}
                curr_bidir = self.bidirectional[idx]

                for feature in features:
                    curr_bidir[feature] = self.__read_feature(feature)

            if i3c_bank:
                count = self.__read_val(2, byteorder="little")
                self.i3c_bank = self.__read_val_array(word_size=2, num_words=count, byteorder="little")
            
            end_align = self.__read_val(word_size=2, byteorder="little")
            assert end_align==1, "End Alignment incorrect, parsing failed"
                

    def pioStringToBin (self, string_val:str) -> int:
        return self.str_pio_mappings.get(string_val, 0)

    def pioBinToString (self, binary_val:int) -> str:
        return self.pio_str_mappings.get(binary_val, "UNKNOWN")

    def csv_repr(self, options):
        if isinstance(options, int):
            return self.pioBinToString(options)
        else:
            return "/".join(self.pioBinToString(option) for option in options)

    def export_csv(self, csv_file:str, section:str=None, force=False):
        section = section.lower() 
        if (section == "input"):
            data = self.input
        elif section == "output":
            data = self.output
        elif section == "bidirectional":
            data = self.bidirectional
        else:
            raise Exception(f"Unknown INI section {section} requested for export")

        try:
            csv_file = Path(csv_file)
        except:
            raise Exception("Invalid epxort path")
        if csv_file.exists() and not force:
            raise FileExistsError (f"file {csv_file} already exists, call with `force=True` to overwrite")
        else:
            with open(csv_file, "w") as f:
                writer = csv.writer(f)
                features = [feature.value for feature in self.schema["features"]]
                row_data = [""]
                row_data.extend(feature["name"] for feature in features)
                writer.writerow(row_data)
                
                for idx in range(self.schema[section]):
                    data_dict = data.get(idx, {})
                    row_data = [idx+1]
                    row_data.extend([self.csv_repr(data_dict.get(feature, "")) for feature in self.schema["features"]])
                    writer.writerow(row_data)
    
    def __read_val(self, word_size=2, byteorder='little'):
        pointer_loc, value = IniParser.read_val(byte_array = self.byte_array, 
                                                pointer_start=self.__pointer, 
                                                word_size=word_size,
                                                byteorder = byteorder)
        self.__pointer = pointer_loc
        return value
    
    def __read_val_array(self, word_size=2, num_words=1, byteorder='little'):
        pointer_loc, option_list = IniParser.read_val_array(self.byte_array, self.__pointer, word_size=word_size, num_words=num_words, byteorder=byteorder)
        self.__pointer = pointer_loc
        return option_list
    

    def __read_feature(self, feature:IOF):
        feature = feature.value
        count_size = feature["count"]
        feature_size = feature["size"]

        if count_size >= 0:
            count = self.__read_val(count_size, byteorder="little")
            feature_options = self.__read_val_array(feature_size, count, byteorder="little")
            return feature_options
        else:
            feature_val = self.__read_val(feature_size, byteorder="little")
            return feature_val
    

    @staticmethod
    def read_val(byte_array: bytes, pointer_start:int=0, word_size:int=1, byteorder='little') -> tuple[int, int]:
        pointer_end_pos = pointer_start + word_size
        read_bytes = byte_array[pointer_start: pointer_end_pos]
        val = int.from_bytes(read_bytes, byteorder)
        # unique_vals.add(val)
        return pointer_end_pos, val

    @staticmethod
    def read_val_array(byte_array:bytes, pointer_start:int=0, word_size:int=1, num_words:int=1, byteorder='little') -> tuple[int, list[int]]:
        val_list = [0] * num_words
        pointer_loc = pointer_start
        for idx in range(num_words):
            pointer_loc, val_list[idx] = IniParser.read_val(byte_array, pointer_loc, word_size, byteorder)
        return pointer_loc, val_list




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="ini_h4x",
        description="This programme parses a .ini file and exports it as a csv file"
    )

    parser.add_argument('device', help="Device Name")
    parser.add_argument("-n", "--inifile", required=False, help="Manually set .ini file. ini_h4x will attempt to find the file using the device name otherwise")
    parser.add_argument('-s', '--section', default="all", choices=["input", "output", "bidirectional", "all"], required=False, help="Section of ini file to parse, default is 'all' ")
    parser.add_argument('-e', '--export_file', required=False, help="Name to use for output file")
    parser.add_argument("-f", '--force', required=False, help="set to overwrite conflicting existing files", action="store_true")


    args = parser.parse_args()
    device=args.device
    inifile = Path(args.inifile) if args.inifile else None
    section = args.section

    iniParser = IniParser(device=args.device.upper(), ini_file=inifile)
    iniParser.parse()

    sections = []
    if section == "all":
        sections = ["input", "output", "bidirectional"]
    else:
        sections = [section]
    
    for curr_section in sections: 
        if not args.export_file:
            export_file = f"{device}.{curr_section}.csv"
            export_file = Path(export_file)
        else:
            export_file = args.export_file
            export_file = export_file[:-4] if export_file[-3:].lower()==".csv" else export_file

            if args.section == "all":
                export_file = f"{export_file}.{curr_section}.csv"
            else: 
                export_file = Path(f"{export_file}.csv")

        try:
            iniParser.export_csv(section=curr_section, csv_file=export_file, force=args.force)
        except FileExistsError:
            print("Export FAILED because export file already exists. Call with '-f' to overwrite existing file")