import struct
G = 0x5043150
CLOSE_DIST = G + 0x5060
CLOSE_X = G + 0x5064
SHIPPED = {CLOSE_DIST: 0.5, CLOSE_X: 0.5}
NEW_DIST = 4.0
class LookUpCam:
    def __init__(self):
        self.base, self.orig = None, {}
    def ok(self):
        return bool(self.orig)
    def apply(self, pm, base, side=1.0):
        try:
            vals = {rva: pm.read_float(base + rva) for rva in SHIPPED}
            if abs(vals[CLOSE_DIST] - SHIPPED[CLOSE_DIST]) > 1e-3 and abs(vals[CLOSE_DIST] - NEW_DIST) > 1e-3:
                return False
            if abs(abs(vals[CLOSE_X]) - SHIPPED[CLOSE_X]) > 1e-3:
                return False
            self.base = base
            self.orig = {rva: struct.pack("<f", v) for rva, v in SHIPPED.items()}
            pm.write_float(base + CLOSE_DIST, NEW_DIST)
            self.set_side(pm, side)
            return True
        except Exception:
            self.orig = {}
            return False
    def set_side(self, pm, side):
        if self.ok():
            pm.write_float(self.base + CLOSE_X, SHIPPED[CLOSE_X] * (1.0 if side >= 0 else -1.0))
    def restore(self, pm):
        if self.ok():
            for rva, raw in self.orig.items():
                try:
                    pm.write_bytes(self.base + rva, raw, 4)
                except Exception:
                    pass
            self.orig = {}
_cam = LookUpCam()
CENTER_START = G + 0x1250 + 0x3C
CENTER_SHIPPED = 0.4
PAN_FAR, PAN_NEAR = G + 0x1250 + 0x98, G + 0x1250 + 0x9C
PAN_FAR_SHIPPED = 10.0
_center = {}
def center_delay(pm, base, secs):
    try:
        v = pm.read_float(base + CENTER_START)
        if abs(v - CENTER_SHIPPED) > 1e-3 and not _center:
            if not 0.0 <= v <= 3600.0:
                return False
        _center["base"] = base
        pm.write_float(base + CENTER_START, float(secs))
        try:
            far, near = pm.read_float(base + PAN_FAR), pm.read_float(base + PAN_NEAR)
            if abs(near) < 1e-3 and (abs(far - PAN_FAR_SHIPPED) < 1e-3 or abs(far) < 1e-3):
                pm.write_float(base + PAN_FAR, near)
                _center["pan"] = True
        except Exception:
            pass
        return True
    except Exception:
        return False
def apply(pm, base, side=1.0):
    return _cam.apply(pm, base, side)
def set_side(pm, side):
    _cam.set_side(pm, side)
def restore(pm):
    _cam.restore(pm)
    if _center:
        try:
            pm.write_float(_center["base"] + CENTER_START, CENTER_SHIPPED)
            if _center.get("pan"):
                pm.write_float(_center["base"] + PAN_FAR, PAN_FAR_SHIPPED)
        except Exception:
            pass
        _center.clear()
if __name__ == "__main__":
    import time
    import pymem
    import pymem.process
    pm = pymem.Pymem("NMS.exe")
    base = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
    side = -1.0 if pm.read_float(base + 0x50463FC) < 0 else 1.0
    show = lambda t: print(t, [round(pm.read_float(base + r), 3) for r in (CLOSE_DIST, CLOSE_X)])
    show("before ")
    print("apply ->", apply(pm, base, side))
    show("applied")
    time.sleep(0.5)
    restore(pm)
    show("restored")
