import sys
with open(sys.argv[1], 'rb') as f:
    d = f.read()

pos = 0;

def rint(w):
    global pos
    val = int.from_bytes(d[pos:pos+w], 'little', signed=True)
    pos+=w
    return val

def readFse():
    print("check", rint(4))
    while True:
        fuselen = rint(4)
        if fuselen == 0x9a1d85: break
        print("tile type", fuselen)
        readOneFile(fuselen)

def BfdArray(size1):
    size2 = rint(4)
    print("Bfd", size2)
    for i in range(size1):
        print([rint(4) for j in range(size2)])

def fuseArray(fuselength, size):
    print("fuse")
    for i in range(size):
        print([rint(2) for j in range(fuselength)])

def logicInfo(size):
    print("LogicInfo")
    for i in range(size):
        print([rint(2) for j in range(3)])

def wire(size):
    print("Wire")
    for i in range(size):
        print([rint(2) for j in range(8)])

def wireSearch(size):
    print("WireSearch")
    for i in range(size):
        print([rint(2) for j in range(3)])

def SInfoValue(size):
    print("SInfoValue")
    for i in range(size):
        print([rint(2) for j in range(8)])

def aloneNode(size):
    print("AloneNode")
    for i in range(size):
        print([rint(2) for j in range(15)])

def LFuseValue(size):
    print("LFuseValue")
    for i in range(size):
        print([rint(2) for j in range(17)])

def LInfoValue(size):
    print("LInfoValue")
    for i in range(size):
        print([rint(2) for j in range(22)])

def const(size):
    print("Const")
    print([rint(2) for j in range(size)])

def readOneFile(fuselength):
    print("tile height", rint(4))
    print("tile width", rint(4))
    tables = rint(4)
    print("File with {} tables".format(tables))
    for i in range(tables):
        typ = rint(4)
        size = rint(4)
        print("Table type", typ, "of size", size)
        if typ == 61:
            BfdArray(size)
        elif typ == 1:
            fuseArray(fuselength, size)
        elif typ in {7, 8, 9, 10, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x27, 0x31, 0x34, 0x37, 0x39, 0x3b, 0x3e, 0x3f, 0x41, 0x43, 0x46, 0x48, 0x4a, 0x4c}:
            logicInfo(size)
        elif typ in {2, 0x26, 0x30}:
            wire(size)
        elif typ == 3:
            wireSearch(size)
        elif typ in {5, 0x11, 0x14, 0x15, 0x16, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x32, 0x33, 0x38, 0x3c, 0x40, 0x42, 0x44, 0x47, 0x49, 0x4b, 0x4d}:
            SInfoValue(size)
        elif typ in {6, 0x45}:
            aloneNode(size)
        elif typ in {0x12, 0x13, 0x35, 0x36, 0x3a}:
            LFuseValue(size)
        elif typ in {0x17, 0x18, 0x25, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f}:
            LInfoValue(size)
        elif typ == 4:
            const(size)
        else:
            raise ValueError("Unknown type at {}".format(hex(pos)))


if __name__ == "__main__":
    readFse()

