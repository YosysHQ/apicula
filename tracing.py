import re
from typing import TypeAlias
from collections import defaultdict, deque
from apycula.fuse_h4x import *
from apycula.chipdb import Device
from apycula.gowin_unpack import parse_tile_, tbrl2rc

Node: TypeAlias = tuple[int, int, str]

# trace a signal to all it's sinks (or source)

def parse_intertile_wire(wire:str):
    # {direction}{length}{number}{segment}
    intertile_regex = r'([NSEW])(\d)(\d)(\d)'
    if m := re.match(intertile_regex, wire):
        return m.groups()
    else:
        return None

def is_intertile_node(wire:str):
    if not wire:
        return False
    if (wire[:2] in ("SN", "EW")):
        return True
    intertile_regex = r'([NSEW])(\d)(\d)(\d)'
    return bool(re.match(intertile_regex, wire))

def uturn(db:Device, node:Node):
    row, col, wire = node
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    m = re.match(r"([NESW])([128]\d)(\d)", wire)
    if m:
        direction, num, segment = m.groups()
        # wires wrap around the edges
        # assumes 0-based indexes
        if row < 0:
            row = -1 - row
            direction = uturnlut[direction]
        if col < 0:
            col = -1 - col
            direction = uturnlut[direction]
        if row > db.rows - 1:
            row = 2 * db.rows - 1 - row
            direction = uturnlut[direction]
        if col > db.cols - 1:
            col = 2 * db.cols - 1 - col
            direction = uturnlut[direction]
        wire = f'{direction}{num}{segment}'
    return row, col, wire

def source_intertile_wire(db:Device, node:Node):
    row, col, wire = node
    loc = (row, col)
    """
    Returns the source of an intertile wire or 'None' if the wire supplied is invalid or no source is found
    Args:
        db (Device):
        loc (tuple (x:int, y:int)): coordinates of the tile the node of interest is from
        node: An intertile wire 
    Returns:
        tuple
    """
    inter_aliases = {
        'E110': 'EW10',
        'W110': 'EW10',
        'E120': 'EW20',
        'W120': 'EW20',
        'S110': 'SN10',
        'N110': 'SN10',
        'S120': 'SN20',
        'N120': 'SN20'
    }
    direction, length, number, segment = parse_intertile_wire(wire)
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    if not is_intertile_node(wire):
        return None
    reverse_dir = uturnlut[wire[0]]
    vecs = { 'N': (-1,0), 'S': (1,0), 'W': (0,-1), 'E': (0,1) }[reverse_dir]
    
    trow = row + vecs[0] * int(segment)
    tcol = col + vecs[1] * int(segment)

    srow, scol, rev_wire = uturn(db, (trow, tcol, f'{reverse_dir}{length}{number}{segment}'))
    true_wire = f'{uturnlut[rev_wire[0]]}{length}{number}0'
    if true_wire in inter_aliases:
        return srow, scol, inter_aliases[true_wire]
    return srow, scol, true_wire

_tbrlre = re.compile(r"IO([TBRL])(\d+)(\w)")
def __normalize_pin(db, pin):
    if isinstance(pin, str) and _tbrlre.match(pin):
        row,col,pin_idx = tbrl2rc(db, pin)
        wire = db.grid[row][col].bels["IOB"+pin_idx].portmap["I"]
        return row,col,wire
    else:
        return pin


def next_intertile_wires(db:Device, node:Node):
    row, col, wire = node
    if not is_intertile_node(wire):
        return []
    if wire[-1] != '0':
        return []
    inter_wires = []
    if wire[:2]=="SN":
        inter_wires = [uturn(db, (row+disp, col, f'{dir}1{wire[2]}1'))
                        for (disp, dir) in [(-1,"N"), (1, "S")]]
        
    elif wire[:2]=="EW":
        inter_wires = [uturn(db, (row, col+disp, f'{dir}1{wire[2]}1'))
                        for (disp, dir) in [(1,"E"), (-1, "W")]]
        
    elif (this_wire:=parse_intertile_wire(wire)):
        direction, length, number, segment = this_wire
        disp_r, disp_c = { 'N': (-1,0), 'S': (1,0), 'W': (0,-1), 'E': (0,1) }[direction]
        next_hops = {1: [1], 2:[1,2], 8:[4,8]}[int(length)]
        inter_wires = [uturn(db, (row+disp_r*hop, col+disp_c*hop, f'{direction}{length}{number}{hop}')) 
                    for hop in next_hops]
    return inter_wires

def input_trace(tile_dict:dict[Node, Node], db:Device, source:Node|str, through_bel=('lut', 'ff')):
    """
    Args:
        tile_dict (dict): Dictionary of tiles (output of tile_bitmap) .
        db (Device): Device object representing the FPGA or chip.
        source (str): Node to start trace from. 
        through_bel (tuple, optional): BEL types to trace through. Defaults to ('lut', 'ff'), the only ones implemented for now.

    Returns:
        dict: A dictionary of dest<-src connections where the keys are destinations.
              In cases where there are multiple conceptual inputs to the same destination (like tracing from the output to input of a bel), 
              the input wires are separated by a "#". dest and src are always strings
    """

    LUT_IN_REGEX = r'[A-D][0-7]'
    FF_IN_REGEX = r'F[0-7]'

    source = __normalize_pin(db, source)

    path_dict = {}
    row, col, snode = source
    sloc = (row,col)
    next_tile = deque([sloc]) #next tile to parse
    tile_wires = defaultdict(list)
    tile_wires[sloc].append(snode) #wires in this tile we are interested in
    seen = set()
    
    
    while next_tile:
        tile_loc = next_tile.pop()
        srow, scol = tile_loc
        tile_bels = db.grid[srow][scol].bels

        if tile_loc not in tile_dict or not tile_wires[tile_loc]:
            continue

        _, all_tile_wires, _ = parse_tile_(db, srow, scol, tile_dict[(srow,scol)])
        wire_dict = defaultdict(list)
        for dest_wire, src_wire in all_tile_wires.items(): 
            wire_dict[src_wire].append(dest_wire)
        
        # Trace the input of an IOB to its output
        for iob in ("IOBA", "IOBB"):
            if iob in tile_bels:
                portmap = tile_bels[iob].portmap
                input_node, output_node = portmap["I"], portmap["O"]
                wire_dict[input_node].append(output_node)

        wire_deque = deque(tile_wires[tile_loc]) #copy wires of interest
        tile_wires[tile_loc].clear() # reset the list of wires we are interested in       

        while wire_deque:
            curr_wire = wire_deque.pop()
            full_node_id = (*tile_loc, curr_wire)

            # General Commment: It's possible to have loops e.g LUT -> FF -> LUT
            if full_node_id in seen:
                continue
            seen.add(full_node_id)

            #Trace through LUTs by adding the lut_output to the deque of wires we'll trace through
            if 'lut' in through_bel and re.match(LUT_IN_REGEX, curr_wire) and f"LUT{curr_wire[-1]}" in tile_bels:
                lut_output = f'F{curr_wire[-1]}'
                lut_output_id = (*tile_loc, lut_output)
                prior_input_id =  path_dict.get(lut_output_id)
                if prior_input_id:
                    lut_input_id = (*tile_loc, prior_input_id[2] + "#" + curr_wire)
                else:
                    lut_input_id = (*tile_loc, curr_wire)
                    wire_deque.append(lut_output)
                path_dict[lut_output_id] = lut_input_id

            #Trace through LUTs by adding the lut_output to the deque of wires we'll trace through
            if 'ff' in through_bel and re.match(FF_IN_REGEX, curr_wire) and f"DFF{curr_wire[-1]}" in tile_bels:
                ff_output = f'Q{dest_wire[-1]}'
                path_dict[(*tile_loc, ff_output)] = full_node_id
                wire_deque.append(ff_output)
            
            #Trace through intertile wires. No support for other aliases yet
            for itrow, itcol, inter_wire in next_intertile_wires(db,full_node_id):
                loc = (itrow, itcol)
                next_tile.append(loc)
                tile_wires[loc].append(inter_wire)
                path_dict[(*loc,inter_wire)] = full_node_id

            # Regular search stuff 
            for dest_wire in wire_dict[curr_wire]:
                wire_id = (*tile_loc, dest_wire)
                wire_deque.appendleft(dest_wire)
                path_dict[wire_id] = full_node_id
                
    return path_dict



def output_trace(tile_dict:dict, db:Device, source:Node|str, through_bel=('lut', 'ff')) -> dict:
    """
    Args:
        tile_dict (dict): Dictionary of tiles (output of tile_bitmap) .
        db (Device): Device object representing the FPGA or chip.
        source (str): Node to start trace from. A bit of a misnomer since we are tracing from destination to source nodes
        through_bel (tuple, optional): BEL types to trace through. Defaults to ('lut', 'ff'), the only ones implemented for now.

    Returns:
        path_dict: A dictionary of dest<-src connections where the keys are destinations.
              In cases where there are multiple conceptual inputs to the same destination (like tracing from the output to input of a bel), 
              the input wires are separated by a "#". dest and src are always strings
    """

    source = __normalize_pin(db, source)
    #parent of source is destination
    path_dict = {source: source}
    srow, scol, source_node = source
    sloc = (srow, scol)
    source_tiles = deque([sloc])
    tile_wires = defaultdict(list)
    tile_wires[sloc].append(source_node)

    LUT_OUT_REGEX = r'F([0-7])'
    FF_OUT_REGEX = r'Q([0-7])'
    
    seen = set()

    while source_tiles:
        tile_loc = source_tiles.pop()
        if tile_loc not in tile_dict or not tile_wires[tile_loc]:
            continue

        wire_deque = deque(tile_wires[tile_loc])
        tile_wires[tile_loc].clear()
        _, wire_dict, _ = parse_tile_(db, *tile_loc, tile_dict[tile_loc], default=True)

        # Trace the output of an IOB to its input
        tile_bels = db.grid[tile_loc[0]][tile_loc[1]].bels
        for iob in ("IOBA", "IOBB"):
            if iob in tile_bels:
                portmap = tile_bels[iob].portmap
                input_node, output_node = portmap["I"], portmap["O"]
                wire_dict[output_node] = input_node

        while wire_deque:
            curr_wire = wire_deque.pop()
            full_curr_id = (*tile_loc, curr_wire)
            if full_curr_id in seen: 
                continue
            seen.add(full_curr_id)
            next_wire = wire_dict.get(curr_wire)
        
            if next_wire:   
                wire_deque.append(next_wire)
                path_dict[full_curr_id] = (*tile_loc, next_wire)

            # Trace LUTs and FFs to their possible inputs.
            if 'lut' in through_bel and re.match(LUT_OUT_REGEX, curr_wire) and f"LUT{curr_wire[-1]}" in tile_bels:
                lut_sources = [F'{id}{curr_wire[-1]}' for id in ('A','B','C','D')]
                lut_sources = [x for x in lut_sources if x in wire_dict]
                if lut_sources:
                    #Assumption that there is never a '#' in a wirename, which holds so far.
                    path_dict[full_curr_id] = (*tile_loc, "#".join(lut_sources))
                    wire_deque.extend(lut_sources)

            if 'ff' in through_bel and re.match(FF_OUT_REGEX, curr_wire) and f"DFF{curr_wire[-1]}" in tile_bels:
                if (ff_source := f'F{curr_wire[-1]}') in wire_dict:
                    wire_deque.append(ff_source)
                    path_dict[full_curr_id] = (*tile_loc, ff_source)

            #Trace an intertile wire to its source in a potentially different tile
            if is_intertile_node(curr_wire):
                it_row, it_col, it_wire = source_intertile_wire(db, full_curr_id)
                it_node = (it_row, it_col, it_wire)
                path_dict[full_curr_id] = it_node
                if (it_node) not in seen:
                    source_tiles.append((it_row,it_col))
                    tile_wires[(it_row, it_col)].append(it_wire)
         
    return path_dict


def get_io_nodes(db:Device):
    rows, cols = db.rows, db.cols
    nodes = []


    for row in range(rows):
        for col in (0, cols-1):
            bels = db.grid[row][col].bels
            for bel_type, bel in bels.items():
                if bel_type.startswith("IOB"):
                    bel_input = bel.portmap["I"]
                    nodes.append ((row, col, bel_input))
    
    for col in range(cols):
        for row in (0, rows-1):
            bels = db.grid[row][col].bels
            for bel_type, bel in bels.items():
                if bel_type.startswith("IOB"):
                    bel_input = bel.portmap["I"]
                    nodes.append ((row, col, bel_input))
    
    return nodes

def get_end_points(db:Device, path_dict:dict[Node,Node], src_criterion=None, dest_criterion=None):
    rows, cols = db.rows, db.cols

    io_nodes = get_io_nodes(db)

    def expand(node_list):
        return [(row, col,single_node) for row, col, node in node_list  for single_node in node.split("#")]

    all_dests = set(expand(path_dict.keys()))
    all_srcs = set(expand(path_dict.values()))

    # return all_srcs, all_dests
    # pure_srcs = all_srcs
    # pure_srcs = all_srcs.difference(all_dests) 

    _src_criterion = lambda node: (node[0] in (0, rows-1) or node[1] in (0, cols-1)) and node in io_nodes
    _dest_criterion = lambda node: (node[0] in (0, rows-1) or node[1] in (0, cols-1)) and node in io_nodes

    src_criterion = src_criterion or _src_criterion
    dest_criterion = dest_criterion or _dest_criterion

    all_srcs = [src for src in all_srcs if src_criterion(src)]
    all_dests = [dest for dest in all_dests if dest_criterion(dest)]

    return all_srcs, all_dests

default_pips = {
    "F0": ["D2", "D3", "D4", "D5", "D6", "D7"],
    "F1": ["B2", "B3", "B4", "B5", "B6", "B7"],
    "F2": ["D0", "D1"],
    "F3": ["B0", "B1"],
    "F4": ["C0", "C1", "C2", "C3", "C6", "C7"],
    "F5": ["A0", "A1", "A2", "A3", "A6", "A7"],
    "F6": ["C4", "C5"],
    "F7": ["A4", "A5"],
    "Q0": ["X01", "X05", "E100", "W100", "W130", "E130", "N100", "S100", "S130", "N130", "E200", "W200", "N200", "S200", "E800", "W800", "N800",  "S800"],
    "Q1": ["X02", "X06", "E210", "W210", "N210", "S210", "E810", "W810", "N810", "S810"],
    "Q2": ["E220", "W220", "N220", "S220"],
    "Q3": ["E230", "W230", "N230", "S230"],
    "Q4": ["E240", "W240", "N240", "S240", "E820", "W820", "N820", "S820"],
    "Q5": ["E250", "W250", "N250", "S250", "E830", "W830", "N830", "S830"],
    "Q6": ["X03", "X07", "E260", "W260", "N260", "S260"],
    "Q7": ["X04", "X08", "E270", "W270", "N270", "S270"]
}

def assess_path(path:list[Node]):
    qual = 0 

    if len(path) < 2:
        return qual
    
    for i in range(len(path)-1):
        (srow, scol, snode), (drow, dcol, dnode) =  path[i], path[i+1]
        if srow==drow and scol==dcol and dnode in default_pips.get(snode, {}):
            qual += 1
    
    return (len(path) - qual)/len(path)

def enumerate_paths(path_dict:dict, sources:set[Node|str], dests:set[Node|str]):

    sources = set(sources)
    dests = list(set(dests))
    dests.sort()

    def __path_finder (prior_path):
        curr_node = prior_path[-1]
        path = list(prior_path)
        while ((next_node:=path_dict.get(curr_node)) not in path) and next_node:
            curr_node = next_node

            row, col, wire = curr_node
            if curr_node in sources or wire in ['VSS', 'VCC']:
                path.append(curr_node)
                yield list(path[::-1])
            
            #Assumption that there is never a '#' in a wirename, which holds so far...
            elif "#" in wire:
                alts = wire.split("#")
                for alt in alts:
                    node = (row, col, alt)
                    alt_path = [*path, node]
                    if node in sources and node not in path:
                        yield list(alt_path[::-1])
                    yield from __path_finder(alt_path)

            else:
                path.append(curr_node)

    for dst in dests:
        # print ('dst', dst)
        # print('dst', dst)
        yield from __path_finder([dst])


def get_paths(path_dict:dict, sources:set[Node|str], dests:set[Node|str], sort:bool=False):
    paths = []
    for path in enumerate_paths(path_dict, sources, dests):
        paths.append(path)
    
    if sort:
        paths.sort(key = lambda x: (x[0], x[-1], assess_path(x)))

    return paths
