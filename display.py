import sys
from bslib import read_bitstream
from PIL import Image

arr = read_bitstream(sys.argv[1])
if len(sys.argv) > 2:
    diff = read_bitstream(sys.argv[2])
    arr ^= diff

size = (arr.shape[1]*8, arr.shape[0])
print(size)
im = Image.frombytes(mode='1', size=size, data=arr)
#im.show()
im.save("bitmap.png","PNG")
