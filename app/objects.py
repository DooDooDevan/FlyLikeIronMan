import struct
import sys
import numpy as np
from rtti import BASE, class_name, pm, q
from vscan import CHUNK, read, regions
def find(vtable, progress=None):
    return find_many([vtable], progress)[vtable]
def find_many(vtables, progress=None):
    from rtti import END
    vts = np.array(sorted(set(vtables)), dtype=np.uint64)
    hits = {int(v): [] for v in vts}
    jobs = [(BASE + off, min(CHUNK, END - BASE - off), True) for off in range(0, END - BASE, CHUNK)]
    for base, size in regions(pm.process_handle):
        jobs += [(base + off, min(CHUNK, size - off), False) for off in range(0, size, CHUNK)]
    total, done = float(sum(j[1] for j in jobs)) or 1.0, 0
    for addr, size, image in jobs:
        if image:
            try:
                buf = pm.read_bytes(addr, size)
            except Exception:
                buf = None
        else:
            buf = read(pm, addr, size)
        done += size
        if buf is not None:
            arr = np.frombuffer(buf, dtype=np.uint64, count=len(buf) // 8)
            for i in np.nonzero(arr == vts[0] if len(vts) == 1 else np.isin(arr, vts))[0]:
                hits[int(arr[i])].append(addr + int(i) * 8)
        if progress is not None:
            try:
                progress(done / total)
            except Exception:
                pass
    return hits
if __name__ == "__main__":
    if sys.argv[1] == "vtable":
        vt = q(int(sys.argv[2], 16))
        print(f"vtable RVA 0x{vt - BASE:X}  {class_name(vt)}")
    else:
        vt = BASE + int(sys.argv[2], 16)
        print(class_name(vt))
        for a in find(vt):
            print(f"0x{a:X}")
