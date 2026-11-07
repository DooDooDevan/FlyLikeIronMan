import time
AIRBORNE = 0x504330C
WATER = (0x5044C8C, 0x5044FBC, 0x50452EC)
FIELDS = (0x1C - 0x7C, 0x110 - 0x7C)
EVERY = 0.02
SHIPPED = ((AIRBORNE, 0.8), (WATER[0], 0.55), (WATER[1], 0.55), (WATER[2], 0.55))
class WaterCam:
    def __init__(self, pm, base):
        self.pm, self.base, self.saved, self.next = pm, base, None, 0.0
        try:
            if base is None or not all(abs(abs(pm.read_float(base + r)) - v) < 1e-3 for r, v in SHIPPED):
                self.base = None
        except Exception:
            self.base = None
    def ok(self):
        return self.base is not None
    def _span(self, rva):
        return self.base + rva + FIELDS[0], FIELDS[1] - FIELDS[0]
    def update(self, flying):
        if self.base is None:
            return
        if not flying:
            self.restore()
            return
        now = time.perf_counter()
        if now < self.next:
            return
        self.next = now + EVERY
        try:
            if self.saved is None:
                self.saved = [self.pm.read_bytes(*self._span(r)) for r in WATER]
            a, n = self._span(AIRBORNE)
            src = self.pm.read_bytes(a, n)
            for r in WATER:
                self.pm.write_bytes(self._span(r)[0], src, n)
        except Exception:
            pass
    def restore(self):
        if self.saved is None:
            return
        try:
            side = self.pm.read_float(self.base + AIRBORNE)
            for r, b in zip(WATER, self.saved):
                self.pm.write_bytes(self._span(r)[0], b, len(b))
                v = self.pm.read_float(self.base + r)
                if (v > 0) != (side > 0):
                    self.pm.write_float(self.base + r, -v)
        except Exception:
            pass
        self.saved = None
