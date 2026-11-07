import ctypes
import struct
import fastwrite
LIFT = 2000.0
FIELDS = {0x18: 8.0, 0x1C: 15.0, 0x20: 8.0}
OLD_FIELDS = {0x50: 20.0}
CHECKS = {0x00: 1025.0, 0x40: -20.0, 0x48: 0.3}
class WaterSpeed:
    def __init__(self):
        self.pm = None
        self.addr = None
        self.orig = {}
        self.lifted = False
        self.failed = False
    def _find(self):
        pm = self.pm
        mod = pm.process_base
        base, size = mod.lpBaseOfDll, mod.SizeOfImage
        pat = struct.pack("<2f", 1025.0, 15.0)
        step = 16 << 20
        for off in range(0, size, step):
            try:
                d = pm.read_bytes(base + off, min(step + 8, size - off))
            except Exception:
                continue
            i = d.find(pat)
            while i >= 0:
                a = base + off + i
                if i % 4 == 0 and self._ok(a):
                    return a
                i = d.find(pat, i + 1)
        return None
    def _ok(self, a):
        try:
            for o, v in CHECKS.items():
                if abs(struct.unpack("<f", self.pm.read_bytes(a + o, 4))[0] - v) > 1e-3:
                    return False
            for o in FIELDS:
                x = struct.unpack("<f", self.pm.read_bytes(a + o, 4))[0]
                if not (0.0 < x <= LIFT):
                    return False
            return True
        except Exception:
            return False
    def start(self, pm):
        self.pm = pm
        try:
            self.addr = self._find()
        except Exception:
            self.addr = None
        if self.addr is None:
            self.failed = True
            return False
        for o, dflt in FIELDS.items():
            x = struct.unpack("<f", pm.read_bytes(self.addr + o, 4))[0]
            self.orig[o] = dflt if x >= LIFT else x
        if any(struct.unpack("<f", pm.read_bytes(self.addr + o, 4))[0] >= LIFT for o in FIELDS):
            self._put(False)
        for o, dflt in OLD_FIELDS.items():
            try:
                if struct.unpack("<f", pm.read_bytes(self.addr + o, 4))[0] >= LIFT:
                    fastwrite.write(pm.process_handle, self.addr + o, struct.pack("<f", dflt))
            except Exception:
                pass
        return True
    def _put(self, lift):
        if self.addr is None or not self._ok(self.addr):
            return False
        for o in FIELDS:
            v = LIFT if lift else self.orig.get(o, FIELDS[o])
            fastwrite.write(self.pm.process_handle, self.addr + o, struct.pack("<f", v))
        self.lifted = lift
        return True
    def update(self, flying):
        if self.addr is None or bool(flying) == self.lifted:
            return
        self._put(bool(flying))
    def ok(self):
        return self.addr is not None
    def restore(self):
        if self.addr is not None and self.lifted:
            self._put(False)
