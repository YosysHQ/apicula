import sys
import json
import numpy as np
from bslib import read_bitstream
from PIL import Image

image = np.zeros([712, 2840], dtype="byte")
for fname in sys.argv[1:]:
    print(fname)
    with open(fname) as f:
        try:
            data = json.load(f)
        except json.decoder.JSONDecodeError:
            continue
        for x, y in data:
            image[x][y] += 1

print(np.nonzero(image > 1))
im = Image.frombytes(mode='1', size=image.shape[::-1], data=np.packbits(image))
#im.show()
im.save("bitmap.png","PNG")
