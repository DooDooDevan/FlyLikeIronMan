import ctypes
import math
import struct
DATA_PTR = 0x6F6B208
MGR_OFF = 0x92CD50
MGR_VTABLE = 0x4B18400
CAM_MAT = 0x130
PLAYER_OFF = 0x72CDE0
PLAYER_VTABLE = 0x4B192D8
def _parse(raw):
    f = struct.unpack("<16f", raw)
    r, u, b, p = f[0:3], f[4:7], f[8:11], f[12:15]
    if not all(math.isfinite(x) for x in r + u + b + p):
        return None
    dot = lambda a, c: a[0] * c[0] + a[1] * c[1] + a[2] * c[2]
    if abs(dot(b, b) - 1) > 0.01 or abs(dot(r, r) - 1) > 0.01 or abs(dot(r, b)) > 0.01 or abs(dot(u, b)) > 0.01:
        return None
    return (-b[0], -b[1], -b[2]), p
def view_dir(pm, base):
    try:
        data = struct.unpack("<Q", pm.read_bytes(base + DATA_PTR, 8))[0]
        mgr = data + MGR_OFF
        if struct.unpack("<Q", pm.read_bytes(mgr, 8))[0] != base + MGR_VTABLE:
            return None
        return _parse(pm.read_bytes(mgr + CAM_MAT, 64))
    except Exception:
        return None
def cam_axes(pm, base):
    try:
        data = struct.unpack("<Q", pm.read_bytes(base + DATA_PTR, 8))[0]
        mgr = data + MGR_OFF
        if struct.unpack("<Q", pm.read_bytes(mgr, 8))[0] != base + MGR_VTABLE:
            return None
        raw = pm.read_bytes(mgr + CAM_MAT, 64)
        if _parse(raw) is None:
            return None
        f = struct.unpack("<16f", raw)
        return f[0:3], f[4:7], (-f[8], -f[9], -f[10])
    except Exception:
        return None
def player_up(pm, base):
    try:
        data = struct.unpack("<Q", pm.read_bytes(base + DATA_PTR, 8))[0]
        pl = data + PLAYER_OFF
        if struct.unpack("<Q", pm.read_bytes(pl, 8))[0] != base + PLAYER_VTABLE:
            return None
        u = struct.unpack("<3f", pm.read_bytes(pl + 0x320, 12))
        n = math.sqrt(sum(x * x for x in u))
        return tuple(x / n for x in u) if 0.9 < n < 1.1 else None
    except Exception:
        return None
def view_dir_inproc(base):
    try:
        data = ctypes.c_uint64.from_address(base + DATA_PTR).value
        if not data:
            return None
        mgr = data + MGR_OFF
        if ctypes.c_uint64.from_address(mgr).value != base + MGR_VTABLE:
            return None
        return _parse(ctypes.string_at(mgr + CAM_MAT, 64))
    except Exception:
        return None
if __name__ == "__main__":
    import time
    import pymem
    import pymem.process
    pm = pymem.Pymem("NMS.exe")
    base = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
    for _ in range(10):
        r, up = view_dir(pm, base), player_up(pm, base)
        if r and up:
            look, pos = r
            pitch = math.degrees(math.asin(max(-1, min(1, sum(a * b for a, b in zip(look, up))))))
            print(f"look {look[0]:+.3f} {look[1]:+.3f} {look[2]:+.3f}  pitch {pitch:+6.1f}  pos {pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f}")
        else:
            print("not available", r, up)
        time.sleep(0.3)
