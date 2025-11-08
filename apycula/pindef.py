from os.path import expanduser
from glob import glob
import json
import os
import csv

VeryTrue = 2

# caches
# .CSV index of vendor files {(device, package) : file_name}
_pindef_index = {}
# (device, package) : pins
_pindef_files = {}

def get_package(device, package, special_pins):
    global _pindef_files
    if (device, package) not in _pindef_files:
        gowinhome = os.getenv("GOWINHOME")
        if not gowinhome:
            raise Exception("GOWINHOME not set")
        with open(_pindef_index[(device, package)]) as f:
            pins = json.load(f)
        _pindef_files[(device, package)] = [d for d in pins['PIN_DATA'] if d['TYPE'] == 'I/O']

    if special_pins != VeryTrue:
        pins = [pin for pin in _pindef_files[(device, package)]
                if 'CFG' not in pin.keys() or (
                    pin['CFG'] != 'RECONFIG_N' and not pin['CFG'].startswith('JTAGSEL_N'))]
    else:
        pins = _pindef_files[(device, package)]
    if not special_pins:
        return [pin for pin in pins if 'CFG' not in pin.keys()]
    return pins

# {partnumber : (pkg, device, speed)}
def all_packages(device):
    gowinhome = os.getenv("GOWINHOME")
    if not gowinhome:
        raise Exception("GOWINHOME not set")
    # {package: speed} vendor file
    speeds = {}
    with open(f"{gowinhome}/IDE/data/device/device_info.csv", mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file, fieldnames =
            ["unused_id", "partnumber", "series", "device", "unused_0", "unused_1", "package", "voltage", "speed"])
        for row in csv_reader:
            if row['device'] != device:
               continue
            speeds.update({row['partnumber']: row['speed']})
    global _pindef_index
    # _pindef_index = {}
    res = {}
    with open(f"{gowinhome}/IDE/data/device/device_package.csv", mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file, fieldnames =
            ["unused_id", "partnumber", "series", "device", "package", "filename"])
        for row in csv_reader:
            if row['device'] != device:
               continue
            res[row['partnumber']] = (row['package'], device, speeds[row['partnumber']])
            _pindef_index[(row['device'], row['package'])] = \
                    f"{gowinhome}/IDE/data/device/{row['filename']}"
    return res

def get_pins(device, package, special_pins=False):
    df = get_package(device, package, special_pins)
    res = {}
    for pin in df:
        res.setdefault(str(pin['BANK']), []).append(str(pin['INDEX']))
    return res

def get_bank_pins(device, package):
    df = get_package(device, package, VeryTrue)
    res = {}
    for pin in df:
        res[pin['NAME']] = str(pin['BANK'])
    return res

def get_locs(device, package, special_pins=False):
    df = get_package(device, package, special_pins)
    res = set()
    for pin in df:
        res.update({pin['NAME']})
    return res

def get_pin_locs(device, package, special_pins=False):
    df = get_package(device, package, special_pins)
    res = {}
    for pin in df:
        cfgs = []
        if 'CFG' in pin.keys():
            cfgs = pin['CFG'].split('/')
        res[str(pin['INDEX'])] = (pin['NAME'], cfgs)
    return res

def get_clock_locs(device, package):
    df = get_package(device, package, True)
    return [(pin['NAME'], *pin['CFG'].split('/')) for pin in df
            if 'CFG' in pin.keys() and pin['CFG'].startswith("GCLK")]

def get_pll_pads_locs(device, package):
    df = get_package(device, package, True)
    return [(pin['NAME'], *pin['CFG'].split('/')) for pin in df
            if 'CFG' in pin.keys() and 'PLL' in pin['CFG']]

# { name : (is_diff, is_true_lvds, is_positive, adc_bus)}
def get_diff_adc_cap_info(device, package, special_pins=False):
    df = get_package(device, package, special_pins)
    res = {}
    # If one pin of the pair is forbidden for the diff IO,
    # we can determine this only after we read the data of all pairs
    positive = {}
    negative = {}
    for pin in df:
        is_positive = False
        is_diff = 'DIFF' in pin.keys()
        adc_bus = None
        if 'ADC_INPUT' in pin.keys() and pin['ADC_INPUT']:
            adc_bus = pin['ADC_INPUT']

        if not is_diff:
            res[str(pin['NAME'])] = (is_diff, is_true_lvds, is_positive, adc_bus)
            continue
        is_true_lvds = 'TRUELVDS' in pin.keys()

        if pin['DIFF'] == 'P':
            is_positive = True
            positive[str(pin['NAME'])] = (is_diff, is_true_lvds, is_positive, adc_bus, str(pin['PAIR']))
        else:
            is_positive = False
            negative[str(pin['NAME'])] = (is_diff, is_true_lvds, is_positive, adc_bus)
    # check the pairs
    for pos_name, pos_flags in positive.items():
        neg_name = pos_flags[-1]
        if neg_name in negative.keys():
            res.update({pos_name : pos_flags[0:-1]})
            res.update({neg_name : negative[neg_name]})
    return res

