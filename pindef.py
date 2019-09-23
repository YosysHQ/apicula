import pandas as pd
from os.path import expanduser
from glob import glob

docdir = expanduser("~/Documents/gowinsemi/")
files = glob(docdir+"*Pinout.xlsx")

def get_pins(series, package, special_pins=False):
    fname = None
    for f in files:
        if series in f:
            fname = f
            break
    assert fname, "No file found for {}".format(series)

    df = pd.read_excel(fname, sheet_name="Pin List", header=1)
    df = df.dropna(subset=[package])
    df = df[df['Function']=="I/O"]
    if not special_pins:
        df = df[df["Configuration Function"].isna()]
    df = df[["BANK", package]].astype("int32")
    return df.groupby("BANK")[package].apply(list).to_dict()
