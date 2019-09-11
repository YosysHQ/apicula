import json
import sys
import numpy as np
from bslib import read_bitstream

arr = read_bitstream(sys.argv[1])
diff = read_bitstream(sys.argv[2])
arr ^= diff
arr = np.unpackbits(arr, axis=1)

indices = np.transpose(np.nonzero(arr)).astype(int)
print(json.dumps(indices.tolist()))
