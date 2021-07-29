import re
import os

from collections import deque, Counter, namedtuple

# read vendor .posp log
_cst_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_R(\d+)C(\d+)\[([0-3])\]\[([A-Z])\]")
_place_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_IO([TBLR])(\d+)\[([A-Z])\]")
def read_posp(fname):
    with open(fname, 'r') as f:
        for line in f:
            cst = _cst_parser.match(line)
            place = _place_parser.match(line)
            if cst:
                name, row, col, cls, lut = cst.groups()
                yield "cst", name, int(row), int(col), int(cls), lut
            elif place:
                name, side, num, pin = place.groups()
                yield "place", name, side, int(num), pin
            elif line.strip() and not line.startswith('//'):
                raise Exception(line)

# Read the packer vendor log to identify problem with primitives/attributes
# One line of error log with contains primitive name like inst1_IOB_IBUF
LogLine = namedtuple('LogLine', [
    'line_type',    # line type: Info, Warning, Error
    'code',         # error/message code like (CT1108)
    'prim_name',    # name of primitive
    'text'          # full text of the line
    ])

_err_parser = re.compile("(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
def read_err_log(fname):
    errs = list()
    with open(fname, 'r') as f:
        for line in f:
            res = _err_parser.match(line)
            if res:
                line_type, code, prim_name = res.groups()
                text = res.group(0)
                ll = LogLine(line_type, code, prim_name, text)
                errs.append(ll)
    return errs

# check if the primitive caused the warning/error
def primitive_caused_err(name, err_code, log):
    flt = filter(lambda el: el.prim_name == name and el.code == err_code, log)
    return next(flt, None) != None

