import re
import struct
import sys
import numpy as np
from objects import find
from rtti import BASE, END, pm, q
_image = None
def image():
    global _image
    if _image is None:
        parts = []
        for off in range(0, END - BASE, 1 << 24):
            try:
                parts.append(pm.read_bytes(BASE + off, min(1 << 24, END - BASE - off)))
            except Exception:
                parts.append(bytes(min(1 << 24, END - BASE - off)))
        _image = b"".join(parts)
    return _image
def vtables_for(name):
    img = image()
    out = []
    for m in re.finditer(re.escape(f".?AV{name}@@".encode()) + b"\0", img):
        td_rva = m.start() - 16
        for c in re.finditer(re.escape(struct.pack("<I", td_rva)), img):
            col = c.start() - 12
            if col < 0 or struct.unpack_from("<I", img, col)[0] != 1:
                continue
            for v in re.finditer(re.escape(struct.pack("<Q", BASE + col)), img):
                out.append(BASE + v.start() + 8)
    return out
def matches(buf, base, vec, tol=1e-4):
    f = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 4)
    with np.errstate(all="ignore"):
        hit = (np.abs(f[:-2] - vec[0]) < tol) & (np.abs(f[1:-1] - vec[1]) < tol) & (np.abs(f[2:] - vec[2]) < tol)
    return [base + int(i) * 4 for i in np.nonzero(hit)[0]]
def search(obj, vec, depth, size=0x2000, path=()):
    try:
        buf = pm.read_bytes(obj, size)
    except Exception:
        return
    for sign, label in ((1, ""), (-1, " (negated)")):
        for a in matches(buf, obj, vec * sign):
            yield path + (a - obj,), label
    if depth == 0:
        return
    for off in range(0, size, 8):
        p = struct.unpack_from("<Q", buf, off)[0]
        if 0x10000 < p < 0x7FF000000000 and not (BASE <= p < END):
            yield from search(p, vec, depth - 1, size, path + (off,))
if __name__ == "__main__":
    name = sys.argv[2]
    vts = vtables_for(name)
    print(f"{name}: vtables at RVA {[hex(v - BASE) for v in vts]}")
    if sys.argv[1] == "field":
        vec = np.frombuffer(pm.read_bytes(int(sys.argv[3], 16), 12), dtype=np.float32)
        depth = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        print(f"looking for {vec.round(4).tolist()}")
        for vt in vts[:1]:
            objs = find(vt)
            print(f"{len(objs)} objects: {[hex(o) for o in objs[:10]]}")
            for obj in objs:
                for path, label in search(obj, vec, depth):
                    print(f"  object 0x{obj:X}  path {' -> '.join(hex(p) for p in path)}{label}")
