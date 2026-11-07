import struct
import sys
import pymem
import pymem.process
pm = pymem.Pymem("NMS.exe")
mod = pymem.process.module_from_name(pm.process_handle, "NMS.exe")
BASE, END = mod.lpBaseOfDll, mod.lpBaseOfDll + mod.SizeOfImage
def q(a):
    return struct.unpack("<Q", pm.read_bytes(a, 8))[0]
def d(a):
    return struct.unpack("<I", pm.read_bytes(a, 4))[0]
_names = {}
def class_name(vtable):
    if vtable in _names:
        return _names[vtable]
    name = None
    try:
        if BASE <= vtable < END and vtable % 8 == 0:
            col = q(vtable - 8)
            if BASE <= col < END and d(col) == 1:
                td = BASE + d(col + 12)
                raw = pm.read_bytes(td + 16, 128).split(b"\0")[0]
                if raw.startswith(b".?A"):
                    name = raw.decode("ascii", "replace")
    except Exception:
        pass
    _names[vtable] = name
    return name
def owners(addr, back=0x4000):
    found = []
    start = (addr - back) & ~7
    buf = pm.read_bytes(start, addr - start + 8)
    for off in range(0, len(buf) - 7, 8):
        v = struct.unpack_from("<Q", buf, off)[0]
        if BASE <= v < END:
            n = class_name(v)
            if n:
                found.append((start + off, v, n))
    return found
if __name__ == "__main__":
    print(f"NMS.exe at 0x{BASE:X}-0x{END:X}")
    for a in (int(x, 16) for x in sys.argv[1:]):
        print(f"\n== 0x{a:X}: nearest vtables before it ==")
        for at, vt, n in owners(a)[-12:]:
            print(f"  object at 0x{at:X} (+0x{a - at:X} to target)  vtable RVA 0x{vt - BASE:X}  {n}")
