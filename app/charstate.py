import struct
from classes import vtables_for
from objects import find
from rtti import pm
CLASS, OFFSET = "cGcPlayerCharacterComponent", 0x214
GROUND = {0, 2, 7}
AIR = 8
SPACE = 16
ATMO = 17
WATER = 12
SURFACE = 13
_VT = None
def _vtable():
    global _VT
    if _VT is None:
        try:
            import lookup
            _VT = lookup.vtable(pm, CLASS)
        except Exception:
            _VT = vtables_for(CLASS)[0]
    return _VT
def alive(addr):
    try:
        return struct.unpack("<Q", pm.read_bytes(addr - OFFSET, 8))[0] == _vtable()
    except Exception:
        return False
def candidates():
    try:
        import lookup
        c = lookup.component(pm)
        if c:
            return [c + OFFSET]
    except Exception:
        pass
    return [o + OFFSET for o in find(_vtable())]
def pick_airborne(addrs):
    airborne = [a for a in addrs if read(a) == AIR]
    return airborne[0] if len(airborne) == 1 else None
def in_space(addrs):
    return any_reads(addrs, SPACE)
def any_reads(addrs, value):
    return any(read(a) == value and alive(a) for a in addrs)
def any_dead(addrs):
    return any(not alive(a) for a in addrs)
def read(addr):
    try:
        return struct.unpack("<i", pm.read_bytes(addr, 4))[0]
    except Exception:
        return None
DATA_PTR, SPAWN_STATE = 0x6F6B208, 0xE70 + 0xD5070 + 0xD0
VEHICLE_MODES = {1: "ship", 6: "ship", 7: "exocraft"}
ON_FOOT_MODES = {0, 8, 9}
_mode_trusted = [None]
def player_mode():
    from rtti import BASE
    try:
        data = struct.unpack("<Q", pm.read_bytes(BASE + DATA_PTR, 8))[0]
        v = struct.unpack("<i", pm.read_bytes(data + SPAWN_STATE, 4))[0] if data else None
    except Exception:
        return None
    return v if v is not None and 0 <= v < 16 else None
def calibrate():
    if _mode_trusted[0] is None:
        _mode_trusted[0] = player_mode() in ON_FOOT_MODES
    return _mode_trusted[0]
def blocked(addrs=None, mine=None):
    if addrs and any(read(a) in (AIR, SPACE, ATMO, WATER, SURFACE) and alive(a) for a in addrs):
        return None
    if _mode_trusted[0] is not False and player_mode() in VEHICLE_MODES:
        return "vehicle"
    return None
def wait_blocked(addrs, secs, mine=None):
    import time
    end = time.perf_counter() + secs
    while True:
        b = blocked(addrs, mine)
        if b or time.perf_counter() >= end:
            return b
        time.sleep(0.1)
if __name__ == "__main__":
    for a in candidates():
        print(f"0x{a:X} = {read(a)}")
def in_water(addrs):
    return any_reads(addrs, WATER) or any_reads(addrs, SURFACE)
