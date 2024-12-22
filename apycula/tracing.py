import re
from typing import Final, TypeAlias
from collections import defaultdict, deque
from apycula.fuse_h4x import *
from apycula.wirenames import wirenames

from apycula.gowin_unpack import parse_tile_

Loc: TypeAlias = tuple[int, int]

# trace a signal to all it's sinks (or source)

def get_exact_wires(fse, ttyp, tile, negatives=False):
    # if not (fse.get(tile), None):
    #     return list
    tile_exact = parse_tile_exact(fse, ttyp, tile, negatives=negatives)
    wire_table:dict = tile_exact.get('wire', None)
    if wire_table:
        wire_table = wire_table.get(2, None)
        wire_table = [(wirenames[abs(wire[0])], wirenames[wire[1]]) for wire in wire_table]
        return wire_table
    return list()


def parse_intertile_wire(wire):
    # {direction}{length}{number}{segment}
    intertile_regex = r'([NSEW])(\d)(\d)(\d)'
    if m := re.match(intertile_regex, wire):
        return m.groups()
    else:
        return None

def is_intertile_node(wire):
    if not wire:
        return False
    if (wire[:2] in ("SN", "EW")):
        return True
    intertile_regex = r'([NSEW])(\d)(\d)(\d)'
    return bool(re.match(intertile_regex, wire))

def uturn(db, row: int, col: int, wire: str):
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
            x = -1 - col
            direction = uturnlut[direction]
        if row > db.rows - 1:
            row = 2 * db.rows - 1 - row
            direction = uturnlut[direction]
        if col > db.cols - 1:
            col = 2 * db.cols - 1 - col
            direction = uturnlut[direction]
        wire = f'{direction}{num}{segment}'
    return (row, col), wire

def source_intertile_wire(db, loc, node):
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
    direction, length, number, segment = parse_intertile_wire(node)
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    if not is_intertile_node(node):
        return None
    reverse_dir = uturnlut[node[0]]
    reverse_wire = reverse_dir + node[1:]
    vecs = { 'N': (-1,0), 'S': (1,0), 'W': (0,-1), 'E': (0,1) }[reverse_dir]
    
    trow = loc[0] + vecs[0] * int(segment)
    tcol = loc[1] + vecs[1] * int(segment)

    source_tile, rev_wire = uturn(db, trow, tcol, f'{reverse_dir}{length}{number}{segment}')
    true_wire = f'{uturnlut[rev_wire[0]]}{length}{number}0'
    if true_wire in inter_aliases:
        return source_tile, inter_aliases[true_wire]
    return source_tile, true_wire

def next_intertile_wires(db, loc, node):
    if not is_intertile_node(node):
        return []
    if node[-1] != '0':
        return []
    inter_wires = []
    if node[:2]=="SN":
        inter_wires = [uturn(db, loc[0]+disp, loc[1], f'{dir}1{node[2]}1')
                        for (disp, dir) in [(-1,"N"), (1, "S")]]
    elif node[:2]=="EW":
        inter_wires = [uturn(db, loc[0], loc[1]+disp, f'{dir}1{node[2]}1')
                        for (disp, dir) in [(1,"E"), (-1, "W")]]
    elif (this_wire:=parse_intertile_wire(node)):
        direction, length, number, segment = this_wire
        vecs = { 'N': (-1,0), 'S': (1,0), 'W': (0,-1), 'E': (0,1) }[direction]
        next_hops = {1: [1], 2:[1,2], 8:[4,8]}[int(length)]
        inter_wires = [uturn(db, loc[0]+vecs[0]*hop, loc[1]+vecs[1]*hop, f'{direction}{length}{number}{hop}') 
                    for hop in next_hops]
    return inter_wires


def path_trace(path_dict:dict, path_aliases,  ignore_intertile=True):
    children = set(path_dict.keys())
    parents = set(path_dict.values())
    terminals = children.difference(parents)
    print(terminals)

    trace_dict = defaultdict(list)

    for terminal in terminals:
        if ignore_intertile and is_intertile_node(terminal[-1]):
            continue 
        path = [terminal]
        node = terminal
        # Just greedy, depth first, guaranteed to exist
        while (this_parent:=path_dict[node]) != node:
            # print(this_parent)
            # print(path)
            path.append(this_parent)
            node = this_parent
        # yield terminal, path[::-1]
        trace_dict[terminal] = path[::-1]
    return trace_dict


def input_trace(bm, db, fse, source, through_lut=False, through_ff=False, negatives=False):
    LUT_IN_REGEX = r'[A-D][0-7]'
    bm:Final = bm
    path_aliases = {} #Maintain a record of when wires reconverge

    parent = {source: source} #this is what we'll return
    next_tile = deque([source[0]]) #next tile to parse
    tile_wires = defaultdict(list)
    tile_wires[source[0]].append(source[1]) #wires in this tile we are interested in
    seen = set()
    while next_tile:
        this_tile = next_tile.pop()
        # print(this_tile)
        # print(this_tile, parent)
        srow, scol = this_tile
        sttyp = db.grid[srow][scol].ttyp
        if (srow, scol) not in bm:
            continue
        # all_tile_wires = get_exact_wires(fse, sttyp, bm[(srow, scol, sttyp)], negatives=negatives)
        _, all_tile_wires, _ = parse_tile_(db, srow, scol, bm[(srow,scol)])
        wire_dict = defaultdict(list)
        # for src_wire, dest_wire in all_tile_wires: 
        #     wire_dict[src_wire].append(dest_wire)
        for dest_wire, src_wire in all_tile_wires.items(): 
            wire_dict[src_wire].append(dest_wire)
        wire_deque = deque(tile_wires[this_tile]) #copy wires of interest
        tile_wires[this_tile].clear() # reset the list of wires we are interested in
        while wire_deque:
            curr_wire = wire_deque.pop()
            full_wire_id = (this_tile, curr_wire)
            if through_lut and (re.match(LUT_IN_REGEX, curr_wire)):
                # print (f"Flip Flop found at location {(srow, scol, curr_wire)}")
                # A LUT can have multiple inputs, A Flip-flop can induce feedback
                lut_output = f'F{dest_wire[-1]}'
                ff_output = f'Q{dest_wire[-1]}'
                if (this_tile, lut_output) in parent:
                    path_aliases[(this_tile, curr_wire)] = parent[(this_tile, lut_output)]
                if lut_output in wire_dict and (this_tile, lut_output) not in parent:
                    wire_dict[curr_wire].append(lut_output)
                if through_ff and ff_output in wire_dict and (this_tile, ff_output) not in parent: 
                    #Assume this is always how this plays out. There's no indication otherwise
                    # parent[ff_output] = (this_tile, lut_output)
                    wire_dict[lut_output].append(ff_output)  

            for loc, inter_wire in next_intertile_wires(db,this_tile,curr_wire):
                # print(loc, inter_wire)
                _ttyp = db.grid[loc[0]][loc[1]].ttyp
                if loc in bm: 
                    if ((loc, inter_wire)) not in seen:
                        seen.add((loc, inter_wire))
                        next_tile.append(loc)
                        tile_wires[loc].append(inter_wire)
                        parent[(loc,inter_wire)] = full_wire_id
            for dest_wire in wire_dict[curr_wire]:
                if (wire_id:=(this_tile, dest_wire)) not in parent:   
                    wire_deque.append(dest_wire)
                    parent[wire_id] = (this_tile, curr_wire)
    return parent, path_aliases


def output_trace(bm, db, fse, source, through_lut=False, through_ff=False):
    #parse_tile_exact enforces that every wire can have only one input, which
    #should make this much faster.
    #We should only ever have to branch at the inputs to a LUT!
    #We also need to be able to trace the source of intertile wires.
    #I reason that to do that we can just call next_intertile_wire

    #This function has to be recursive

    #parent of source is destination
    TAG = "##TAG##"
    parent = {((-1, -1), TAG): source}
    source_loc, source_node = source
    trow, tcol = source_loc
    curr_ttyp = db.grid[trow][tcol].ttyp

    source_tiles = deque([source[0]])
    tile_wires = defaultdict(deque)
    tile_wires[(trow,tcol)].append(source_node)
    LUT_OUT_REGEX = r'F([0-3])'
    FF_OUT_REGEX = r'Q([0-3])'
    
    seen_dests = defaultdict(int)
    seen = set()

    while source_tiles:
        this_tile = source_tiles.pop()
        # print(this_tile)
        # print(this_tile)
        if not tile_wires[this_tile]:
            continue
        wire_deque = deque(tile_wires[this_tile])
        tile_wires[this_tile].clear()
        srow, scol = this_tile
        sttyp = db.grid[srow][scol].ttyp
        if (srow, scol) not in bm:
            print('loc', srow, scol, sttyp)
            continue

        # all_tile_wires = get_exact_wires(fse, sttyp, bm[(srow, scol, sttyp)], negatives=negatives)
        _, all_tile_wires, _ = parse_tile_(db, srow, scol, bm[(srow,scol)])
        # all_tile_wires = get_exact_wires(fse, sttyp, bm[(srow,scol,sttyp)])
        # print(this_tile, "\n", all_tile_wires)
        # print(all_tile_wires)
        wire_dict = {}
        for dest_wire, src_wire in all_tile_wires.items():
            if (alias_id:=seen_dests[(this_tile, dest_wire)]):
                alias_dest_wire = dest_wire + "#" + str(alias_id)
            else:
                alias_dest_wire = dest_wire
            seen_dests[(this_tile, dest_wire)] += 1
            wire_dict[alias_dest_wire]= src_wire
            if dest_wire in wire_deque:
                wire_deque.append(alias_dest_wire)
        # print(wire_dict)
        

        while wire_deque:
            curr_wire = wire_deque.pop()
            # print (this_tile,curr_wire)
            aliased_wire = curr_wire.split("#")[0]
            # print(curr_wire, aliased_wire)
            if (srow, scol) == (26,26):
                # print(sorted(list(wire_dict.keys())))
                pass
                # print(curr_wire)
            # print(srow, scol, curr_wire)
            # print(curr_wire)
            # while (next_wire:=wire_dict.get(curr_wire)) or is_intertile_node(next_wire):
            next_wire = wire_dict.get(curr_wire)
            if (next_wire):   
                wire_deque.append(next_wire)
                parent[(this_tile, curr_wire)] = (this_tile, next_wire)
                # print(curr_wire)
            elif through_lut and (re.match(LUT_OUT_REGEX, curr_wire)):
                # print("here")
                LUT_INS =  ('A','B','C','D')
                # print("heree")
                # for lut_in in LUT_INS:
                #     wire_deque.appendleft(lut_in + curr_wire[-1]
                wire_deque.extend([F'{i}{curr_wire[-1]}' for i in ('A','B','C','D')])

            elif through_ff and (re.match(FF_OUT_REGEX, curr_wire)):
                print(f"FF found at {(srow, scol, curr_wire)}")
                wire_deque.append(f'F{curr_wire[-1]}')
            elif (is_intertile_node(aliased_wire)):
                _sloc, _snode = source_intertile_wire(db, (srow, scol), aliased_wire)
                if (_sloc) != (srow, scol):
                    # print(srow, scol, curr_wire, _sloc, _snode)
                    parent[(this_tile, curr_wire)   ] = (_sloc, _snode)
                # print(_sloc, _snode)
                    if ((_sloc, _snode)) not in seen:
                        source_tiles.append(_sloc)
                        tile_wires[_sloc].append(_snode)
                        seen.add((_sloc, _snode))
            # curr_wire = next_wire

                
    return parent

    #     all_tile_wires = get_exact_wires(fse, sttyp, bm[(srow, scol, sttyp)])
    # wire_dict = defaultdict(list)
    # for src_wire, dest_wire in all_tile_wires: 
    #     wire_dict[src_wire].append(dest_wire)
