
def fliplr(bmp):
    """
    Flips the entries in each row in the left/right direction.
    Returns a new matrix.
    """
    return [row[::-1] for row in bmp]

def flipud(bmp):
    """
    Reverse the order of elements in each column (up/down).
    Returns a refence.
    """
    return bmp[::-1]

def transpose(bmp):
    """
    Transposes a bitmap (swaps rows and cols)
    Returns a reference
    """
    return [[bmp[j][i] for j in range(len(bmp))] for i in range(len(bmp[0]))]

def vstack(bmp_0, bmp_1):
    """
    Stack matrices in sequence vertically (row wise).
    Returns a reference.
    """
    return [*bmp_0, *bmp_1]

def hstack(bmp_0, bmp_1):
    """
    Stack matrices in sequence horizontally (column wise).
    Returns a new matrix.
    """
    return [bmp[0] + bmp[1] for bmp in zip(bmp_0, bmp_1)]

def shape(bmp):
    """
    Return the shape of a matrix.
    """
    return [len(bmp), len(bmp[0])]

def fill(rows, cols, val):
    """
    Returns a new matrix of given shape, filled with val.
    """
    return [[val] * cols for i in range(rows)]

def ones(rows, cols):
    """
    Returns a new matrix of given shape, filled with ones.
    """
    return fill(rows, cols, 1)

def zeros(rows, cols):
    """
    Returns a new matrix of given shape, filled with zeros.
    """
    return fill(rows, cols, 0)

def packbits(bmp, axis = None):
    """
    Packs the elements of a bitmap into bytes.
    [1, 1, 0, 0, 0] -> [24]  # [5'b11000]
    Returns a list of bytes.
    """
    byte_list = []
    byte = 0
    bit_cnt = 0
    if not axis:
        for bmp_r in bmp:
            for col in range(shape(bmp)[1]):
                byte = (byte << 1) + bmp_r[col]
                bit_cnt += 1
                if bit_cnt == 8:
                    byte_list.append(byte)
                    bit_cnt = 0
                    byte = 0
    else:
        for bmp_r in bmp:
            byte_list.append([])
            byte_list_r = byte_list[-1]
            for col in range(shape(bmp)[1]):
                byte = (byte << 1) + bmp_r[col]
                bit_cnt += 1
                if bit_cnt == 8:
                    byte_list_r.append(byte)
                    bit_cnt = 0
                    byte = 0
    return byte_list

def xor(bmp_0, bmp_1):
    """
    Bitwise XOR
    Returns a new matrix
    """
    return [[ vals[0] ^ vals[1]for vals in zip(row[0], row[1])] for row in zip(bmp_0, bmp_1)]

def histogram(lst, bins):
    """
    Compute the histogram of a list.
    Returns a list of counters.
    """
    l_bins = len(bins) - 1
    r_lst = [0] * l_bins
    from itertools import chain
    for val in chain.from_iterable(lst):
        for i in range(l_bins):
            if val in range(bins[i], bins[i + 1]) or (i == l_bins - 1 and val == bins[-1]):
                r_lst[i] += 1
    return r_lst

def byte_histogram(lst):
    """
    Compute the histogram of a list of bytes.
    Returns a list of 256 counters.
    """
    r_lst = [0] * 256
    from itertools import chain
    for val in chain.from_iterable(lst):
        r_lst[val] += 1
    return r_lst

def any(bmp):
    """
    Test whether any matrix element evaluates to True.
    """
    for row in bmp:
        for val in row:
            if val:
                return True
    return False

def nonzero(bmp):
    """
    Return the indices of the elements that are non-zero.
    """
    res = ([], [])
    for ri, row in enumerate(bmp):
        for ci, val in enumerate(row):
            if val:
                res[0].append(ri)
                res[1].append(ci)
    return res
