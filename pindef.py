import pandas as pd
from os.path import expanduser
from glob import glob

docdir = expanduser("~/Documents/gowinsemi/")
files = glob(docdir+"*Pinout.xlsx")

def get_package(series, package, special_pins, header):
    fname = None
    for f in files:
        if "%s Pinout" % series in f:
            fname = f
            break
    assert fname, "No file found for {}".format(series)

    df = pd.read_excel(fname, sheet_name="Pin List", header=header)
    df = df.dropna(subset=[package])
    df = df[df['Function']=="I/O"]
    df = df[df["Configuration Function"] != "RECONFIG_N"] # can't be output
    df = df[df["Configuration Function"] != "JTAGSEL_N"] # dedicated pin
    df = df[df["Configuration Function"] != "JTAGSEL_N/LPLL_T_in"] # whack-a-mole
    if not special_pins:
        df = df[df["Configuration Function"].isna()]
    return df

def get_pins(series, package, special_pins=False, header=0):
    df = get_package(series, package, special_pins, header)
    df = df[["BANK", package]].astype("int32")
    return df.groupby("BANK")[package].apply(list).to_dict()

def get_locs(series, package, special_pins=False, header=0):
    df = get_package(series, package, special_pins, header)
    return {p.split('/')[0] for p in df["Pin Name"]}

def get_clock_locs(series, package, header=0):
    df = get_package(series, package, True, header)
    df = df[df["Configuration Function"].str.startswith("GCLK", na=False)]
    return {tuple(p.split('/')) for p in df["Pin Name"]}
    

