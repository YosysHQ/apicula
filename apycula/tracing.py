import itertools
import re
import string
from typing import Iterable, TypeAlias
from collections import defaultdict, deque
from apycula.chipdb import Device
from apycula.gowin_unpack import parse_tile_, tbrl2rc
import random
# from apycula.tiled_fuzzer import rc2tbrl

#Node Type
Node: TypeAlias = tuple[int, int, str]


def rc2tbrl(db, row, col, num):
    edge = 'T'
    idx = col
    if row == db.rows:
        edge = 'B'
    elif col == 1:
        edge = 'L'
        idx = row
    elif col == db.cols:
        edge = 'R'
        idx = row
    return f"IO{edge}{idx}{num}"

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

# Mostly copied from gowin_arch_gen in nextpnr :). Logic for handling cases
# Where a wire would appear to go out of bounds
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
    """
    Returns the source of an intertile wire or 'None' if the wire supplied is invalid or no source is found
    Args:
        db (Device):
        loc (tuple (x:int, y:int)): coordinates of the tile the node of interest is from
        node: An intertile wire 
    Returns:
        source_node (Node): The source Node of an intertile wire
    """

    row, col, wire = node
    loc = (row, col)
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
    
    """
    Returns the intertile wires that have `node` as their source
    Args:
        db (Device):
        node (Node): A node with an intertile wire

    Returns:
        inter_wires(list[Node]): list of nodes that have `node` as their source
    """

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



def get_input_path_dict(tile_dict:dict[Node, Node], db:Device, source:Node|str, through_bel=('lut', 'ff')):
    """
    Returns dictionary of connections that emanate from a `node`.
    Args:
        tile_dict (dict): Dictionary of tiles (output of tile_bitmap) .
        db (Device): Device object representing the FPGA or chip.
        source(Node|str): Node to start trace from. The TBRL format may be used to specify IO Nodes 
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



def get_output_path_dict(tile_dict:dict, db:Device, source:Node|str, through_bel=('lut', 'ff')) -> dict:
    """
    Returns dictionary of connections that lead to a `node`.
    Args:
        tile_dict (dict): Dictionary of tiles (output of tile_bitmap) .
        db (Device): Device object representing the FPGA or chip.
        source (Node|str): Node to start trace from. A bit of a misnomer since we are tracing from destination to source nodes
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

def get_path_dict(tile_dict:dict, db:Device, source:Node|str, through_bel=('lut', 'ff')) -> dict:
    """
    Returns dictionary of connections that lead to a `node` or emanate from it
    Args:
        tile_dict (dict): Dictionary of tiles (output of tile_bitmap) .
        db (Device): Device object representing the FPGA or chip.
        source (Node|str): Node to start trace from. A bit of a misnomer since we are tracing from destination to source nodes
        through_bel (tuple, optional): BEL types to trace through. Defaults to ('lut', 'ff'), the only ones implemented for now.

    Returns:
        path_dict: A dictionary of dest<-src connections where the keys are destinations.
              In cases where there are multiple conceptual inputs to the same destination (like tracing from the output to input of a bel), 
              the input wires are separated by a "#". dest and src are always strings
    """
    input_path_dict = get_input_path_dict(tile_dict, db, source, through_bel)
    output_path_dict = get_output_path_dict(tile_dict, db, source, through_bel)
    path_dict = {**input_path_dict, **output_path_dict}
    return path_dict


def io_node_to_tbrl(db, node:Node):
    row, col, wire = node
    for bel_type, bel in db.grid[row][col].bels.items():
        if bel_type.startswith("IOB") and wire in bel.portmap.values():
            tbrl_name = rc2tbrl(db, row, col, bel_type[-1])
            return tbrl_name

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

# Connected by default in tiles (src -> list[destinations]). No longer in tiledata from V1.9.9
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


# ratio of wires that are connected by default. I was getting multiple routes between the same
# source and destination at some point and the routes with more non-default wires seemed more
# plausible.
def assess_path(path:list[Node]):
    """
    Calculate the ratio of wires connected by default in a given path.

    Args:
        path (list[Node]): A list of nodes representing a route.

    Returns:
        float: The ratio of default-connected wires to total wires in the path.
    """
    qual = 0 

    if len(path) < 2:
        return qual
    
    for i in range(len(path)-1):
        (srow, scol, snode), (drow, dcol, dnode) =  path[i], path[i+1]
        if srow==drow and scol==dcol and dnode in default_pips.get(snode, {}):
            qual += 1
    
    return (len(path) - qual)/len(path)

def enumerate_paths(path_dict:dict, sources:set[Node|str], dests:set[Node|str])->Iterable[Node]:
    """
    Generate all paths between given sources and destinations. Enumerating might be a better option
    than getting the list in one go for large designs.

    Args:
        path_dict (dict[dst, src]): A dictionary mapping destination nodes to their sources.
        sources (set[Node | str]): A set of starting nodes.
        dests (set[Node | str]): A set of destination nodes.

    Returns:
        Iterable[Node]: An iterator yielding paths as sequences of nodes from src to destination.
    """

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


# Accumulate paths from `enumerate_paths` and optionally rank them
def get_paths(path_dict:dict, sources:set[Node|str], dests:set[Node|str], sort:bool=False):
    """
    Accumulate paths between sources and destinations (generated by `enumerate_paths`), with optional ranking.

    Args:
        path_dict (dict[dst, src]): A dictionary mapping destination nodes to their sources.
        sources (set[Node | str]): A set of starting nodes.
        dests (set[Node | str]): A set of destination nodes.
        sort (bool): Whether to sort the paths based on a ranking criteria (default is False).

    Returns:
        list: A list of paths between the sources and destinations, optionally sorted.
    """
    paths = []
    for path in enumerate_paths(path_dict, sources, dests):
        paths.append(path)
    
    if sort:
        paths.sort(key = lambda x: (x[0], x[-1], assess_path(x)))

    return paths

def visualize_grid(plot:dict[str, list[Node]], rows, cols, show=False, save_name='', checkbox=False):
    """
    Visualize a grid with marked tiles and annotations. The source tile for a path is marked with '^',
    while its destination tile is marked with '$'

    Parameters:
        plot (dict): A dictionary where keys represent group labels and values are lists of `Node` objects.
                     Each group of nodes will be marked with a distinct ASCII character. 
                     Note: Avoid using `[all]` as a key in the plot dictionary.
        rows (int, optional): The number of rows in the grid. If not provided, it will be inferred from the data.
        cols (int, optional): The number of columns in the grid. If not provided, it will be inferred from the data.
        show (bool, optional): If `True`, the plot will be displayed. Defaults to `False`.
        save_name (str, optional): The filename to save the plot. If not provided, the plot will not be saved.
        checkbox (bool, optional): If `True`, adds interactive checkboxes to toggle the visibility of plot groups.
    Returns:
        None
    """
    try:
        import matplotlib
        import matplotlib.pyplot as plt
    except:
        raise ModuleNotFoundError ("Kindly install `matplotlib` to call this function")
    
    if checkbox:
        # matplotlib.use('Qt5Agg')
        from matplotlib.widgets import CheckButtons

    grid = [[0] * cols for _ in range(rows+1)]
    fig, ax = plt.subplots(figsize=(16,14))

    cmap = plt.get_cmap('tab10', 1)
    plt.imshow(grid, cmap=cmap, origin='upper', extent=[0, cols, 0, rows])
    plt.tick_params(labeltop=True, labelright=True, labelsize=10)
    plt.grid(which='both', color='black', linestyle='-', linewidth=1)
    
    x_ticks = list(range(0, cols+1))
    plt.xticks(x_ticks, rotation=90, fontsize=8, fontweight='light', fontfamily='monospace')

    yticks = list(range(rows, -1, -1 ))
    ylabels = [str(x) for x in yticks[::-1]]
    plt.yticks(yticks, ylabels, fontsize=8, fontweight='light', fontfamily='monospace')

    # ax = plt.gca()
    ax.set_aspect(0.8, adjustable='box')
    # ax.set_adjustable()

    plt.subplots_adjust(left=0.1, right=0.6, wspace=0.05)
    plot_chars = []
    plot_chars.extend(list(string.ascii_uppercase))
    # colors = ["white", "yellow", "red", "black", "gold", "cyan", "orange"]
    colors = ["white", "black", "red", "gold"]
    legend_opts = list(itertools.product(plot_chars, colors))
    random.Random(12).shuffle(legend_opts)

    if isinstance(plot, list):
        plot = {0: plot}


    plot = {str(k):v for k, v in plot.items()} #Cast to Strings for consistency

    legend_dict = {}
    l_idx = 0
    for k, path in plot.items():
        legend = legend_opts[l_idx%len(legend_opts)]
        legend_dict[str(k)] = [*legend, f"({legend[0]}) {path[0]} -> {path[-1]} //{k}"] #plot_character, plot_color, plot_label
        l_idx += 1
 
    legend_entries = [
        plt.Line2D([0], [0], color=color, markerfacecolor=color, marker='o', linestyle='', 
                   markeredgecolor='black', markersize=10, label=path_label)
        for k, (plot_char, color, path_label) in legend_dict.items()
    ]
    
    text_dict = defaultdict(list)
    for k, path in plot.items():
        base_plot_char, color, label = legend_dict[str(k)]

        locs = [(node[0], node[1]) for node in path]
        start_loc, end_loc = locs[0], locs[-1]

        for loc in locs:
            plot_char = base_plot_char
            if len(path) == 1:
                plot_char = plot_char + "!" #Single tile marker
            elif loc == start_loc:
                plot_char = plot_char + "^" #Start tile marker
            elif loc == end_loc:
                plot_char = plot_char + "$" #Final tile marker
            
            i, j = loc
            this_text = ax.text(j + 0.5, rows - i - 0.5, plot_char, ha='center', va='center', color=color, 
                                fontweight='bold', fontsize=8, visible=True)
            text_dict[k].append((loc, this_text)) # We store the texts so we can easily toggle visibility later on

    ALL_TAG = "[ALL]"
    _showing = set(plot.keys())
    showing = set(_showing) #We'll use this to manage state

    def check_callback(to_toggle=''):
        # print('click registered', "to_toggle", to_toggle)
        check.eventson = False
        if to_toggle is None:
            return
 
        if to_toggle != ALL_TAG:
            _, key = to_toggle.split("//")
            text_objs = text_dict[key]
            visibility = key in showing
            for loc, text in text_objs:
                text.set_visible(not visibility)
            if visibility:
                showing.remove(key)
            else:
                showing.add(key)

        else:
            key = ALL_TAG
            visibility = len(showing) == len(_showing)
            for text_list in text_dict.values():
                for text_loc, text_obj in text_list:
                    text_obj.set_visible(not visibility) #Toggle visibiility of characters
            
            if visibility:
                check.clear() #Clear all checkboxes
                showing.clear()
            else:
                for i in range(len(_showing)):
                    check.set_active(i, True) #Activate all checkboxes
                showing.update(_showing)
        
        # Keep the state of the 'ALL' checkbox consistent
        if len(showing) < len(_showing):
            check.set_active(0, False)
        elif len(showing) == len(_showing):
            check.set_active(0, True)

        check.eventson = True
        plt.draw()

    # Labels for checkboxes
    check_labels = [ALL_TAG]
    check_labels.extend([v[2] for k, v in legend_dict.items()])

    if show and checkbox:
        rax = plt.axes([0.6, 0.1, 0.4, 0.8])  # Position [left, bottom, width, height]
        rax.autoscale()
        rax.set_frame_on(False)
        check = CheckButtons(rax, check_labels, [True] * len(check_labels))
        check.on_clicked(check_callback)
    elif not (show or checkbox): 
        plt.legend(
            handles=legend_entries,
            loc='center left',  # Legend location
            bbox_to_anchor=(1.05, 0.5),  # Position outside the grid
            fontsize=10
        )

    if save_name:
        plt.savefig(save_name+".jpeg", dpi=300, bbox_inches='tight')

    if show:
        plt.axes(ax)
        plt.show()