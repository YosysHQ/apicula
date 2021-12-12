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
            ["unused_id", "partnumber", "series", "device", "package", "voltage", "speed"])
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
        res[str(pin['INDEX'])] = pin['NAME']
    return res

def get_clock_locs(device, package):
    df = get_package(device, package, True)
    return [(pin['NAME'], *pin['CFG'].split('/')) for pin in df
            if 'CFG' in pin.keys() and pin['CFG'].startswith("GCLK")]


