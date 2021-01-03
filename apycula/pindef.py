import pandas as pd
from os.path import expanduser
from glob import glob

docdir = expanduser("~/Documents/gowinsemi/")
files = glob(docdir+"*Pinout.xlsx")

VeryTrue = 2

def get_package(series, package, special_pins, header):
    fname = None
    for f in files:
        if "%s Pinout" % series in f:
            fname = f
            break
    assert fname, "No file found for {}".format(series)

    df = pd.read_excel(fname, sheet_name="Pin List", header=header, engine='openpyxl')
    df = df.dropna(subset=[package])
    df = df[df['Function']=="I/O"]
    if special_pins != VeryTrue:
        df = df[df["Configuration Function"] != "RECONFIG_N"] # can't be output
        df = df[~df["Configuration Function"].str.startswith("JTAGSEL_N", na=False)] # dedicated pin
    if not special_pins:
        df = df[df["Configuration Function"].isna()]
    return df

def all_packages(series, start, header):
    df = get_package(series, "Pin Name", True, header)
    return list(df.columns[start:])

def get_pins(series, package, special_pins=False, header=0):
    df = get_package(series, package, special_pins, header)
    df = df[["BANK", package]].astype("int32")
    return df.groupby("BANK")[package].apply(list).to_dict()

def get_locs(series, package, special_pins=False, header=0):
    df = get_package(series, package, special_pins, header)
    return {p.split('/')[0] for p in df["Pin Name"]}

def get_pin_locs(series, package, special_pins=False, header=0):
    def tryint(n):
        try:
            return int(n)
        except:
            return n

    df = get_package(series, package, special_pins, header)
    return {tryint(num): p.split('/')[0] for _, num, p in df[[package, "Pin Name"]].itertuples()}

def get_clock_locs(series, package, header=0):
    df = get_package(series, package, True, header)
    df = df[df["Configuration Function"].str.startswith("GCLK", na=False)]
    return {tuple(p.split('/')) for p in df["Pin Name"]}
    

