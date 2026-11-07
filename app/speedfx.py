import ctypes
import ctypes.wintypes as wt
import math
import re
import struct
import threading
import time
from pathlib import Path
G = 0x5042040
CAM = G + 0x1250
BACK_MIN, BACK_MAX = CAM + 0x20, CAM + 0x1C
FOV = G + 0x5090
SHIPPED = {BACK_MIN: 4.0, BACK_MAX: 7.2, FOV: 70.0}
GFX_FOV_BLOCK = 0xAC
GFX_BLUR = 0xC8
try:
    import flim_paths
    SETTINGS = flim_paths.graphics_settings_file() or Path("TKGRAPHICSSETTINGS.MXML")
except Exception:
    SETTINGS = Path(r"C:\Program Files (x86)\Steam\steamapps\common\No Man's Sky\Binaries\SETTINGS\TKGRAPHICSSETTINGS.MXML")
DIVE = (1.30, 8.0, 0.35)
BURNER = (1.40, 10.0, 0.40)
SONIC = (2.10, 24.0, 0.85)
WARP = (2.20, 38.0, 1.00)
EASE_IN, EASE_OUT = 0.6, 0.9
SONIC_EASE_IN = 0.18
_SHIPPED_FX = dict(DIVE=DIVE, BURNER=BURNER, SONIC=SONIC, WARP=WARP)
strength = 1.0
STRENGTH_MAX = 2.0
CAP_DIST = 3.2
CAP_FOV = 60.0
START_OK_DIST = (0.25, 12.6)
START_OK_FOV = (-31.0, CAP_FOV + 5.0)
class SpeedFX:
    def __init__(self):
        self.pm = self.base = None
        self.ok = False
        self.blur_addr, self.blur_orig = None, None
        self.cur = [1.0, 0.0, 0.0]
        self.vel = [0.0, 0.0, 0.0]
        self.punches = []
        self.punch_on = True
        self.effects_on = True
        self.fov_out = 0.0
        self.written = None
    def start(self, pm, base):
        self.pm, self.base = pm, base
        try:
            vals = {a: pm.read_float(base + a) for a in SHIPPED}
        except Exception:
            return False
        def ours(a, v):
            if a == FOV:
                return SHIPPED[FOV] + START_OK_FOV[0] <= v <= SHIPPED[FOV] + START_OK_FOV[1]
            lo, hi = START_OK_DIST[0] * (1 - 1e-5), START_OK_DIST[1] * (1 + 1e-5)
            return lo * SHIPPED[a] <= v <= hi * SHIPPED[a]
        self.ok = all(ours(a, vals[a]) for a in SHIPPED)
        if self.ok:
            try:
                for a, v in SHIPPED.items():
                    pm.write_float(base + a, v)
            except Exception:
                pass
            self.cur, self.vel = [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            self.fov_out = 0.0
            self.written = None
            threading.Thread(target=self._find_blur, daemon=True).start()
        return self.ok
    def _settings(self):
        try:
            buf, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(wt.HANDLE(self.pm.process_handle), 0, buf,
                                                                  ctypes.byref(n)):
                p = Path(buf.value).parent / "SETTINGS" / "TKGRAPHICSSETTINGS.MXML"
                if p.exists():
                    return p
        except Exception:
            pass
        return SETTINGS
    def _find_blur(self):
        try:
            txt = self._settings().read_text(errors="replace")
            get = lambda n: float(re.search(rf'name="{n}" value="([-\d.]+)"', txt).group(1))
            pat = struct.pack("<4f", get("FoVInShip"), get("FoVInShipFP"), get("FoVOnFoot"), get("FoVOnFootFP"))
            self.blur_orig = get("MotionBlurStrength")
        except Exception:
            return
        ours = None
        top = max(self.blur_orig, max(fx[2] for fx in _SHIPPED_FX.values()))
        hits = None
        try:
            import lookup
            g_ = lookup.gfx_settings(self.pm)
            if g_ and self.pm.read_bytes(g_ + GFX_FOV_BLOCK, 16) == pat:
                hits = [g_ + GFX_FOV_BLOCK]
        except Exception:
            hits = None
        for hit in (hits if hits is not None else _scan(self.pm.process_handle, pat)):
            a = hit - GFX_FOV_BLOCK + GFX_BLUR
            if not (self.base <= a < self.base + 0x10000000):
                try:
                    v = self.pm.read_float(a)
                    if abs(v - self.blur_orig) < 1e-4:
                        self.blur_addr = a
                        return
                    if ours is None and self.blur_orig < v <= top + 1e-4:
                        ours = a
                except Exception:
                    pass
        if ours is not None:
            try:
                self.pm.write_float(ours, self.blur_orig)
                self.blur_addr = ours
            except Exception:
                pass
    def punch(self, fov_deg, back_m, decay_s):
        if self.ok and self.punch_on and self.effects_on:
            now = time.perf_counter()
            self.punches = [p for p in self.punches if now - p[0] < p[3] * 7.0 / 6.0][-3:]
            self.punches.append((now, fov_deg, back_m, max(0.05, decay_s)))
    def _punch_now(self):
        fov = back = 0.0
        now = time.perf_counter()
        for t0, f, b, d in self.punches:
            tr, x = d / 6.0, now - t0
            if 0.0 <= x < tr:
                e = 0.5 - 0.5 * math.cos(math.pi * x / tr)
            elif tr <= x < tr + d:
                e = 0.5 + 0.5 * math.cos(math.pi * (x - tr) / d)
            else:
                continue
            fov, back = fov + f * e, back + b * e
        return fov, back
    @staticmethod
    def _damp(cur, vel, i, tgt, tau, dt):
        w = 2.15 / tau
        e, x = cur[i] - tgt, w * dt
        ex = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
        tmp = (vel[i] + w * e) * dt
        vel[i] = (vel[i] - w * tmp) * ex
        cur[i] = tgt + (e + tmp) * ex
    def update(self, dt, dive, burner, sonic=0.0, warp=0.0):
        if not self.ok:
            return
        dt = max(0.0, min(0.25, dt))
        try:
            k = float(strength)
            k = max(0.0, min(STRENGTH_MAX, k)) if math.isfinite(k) else 1.0
        except (TypeError, ValueError):
            k = 1.0
        tgt = [1.0, 0.0, 0.0]
        if self.effects_on:
            for amt, fx in ((dive, DIVE), (burner, BURNER), (sonic, SONIC), (warp, WARP)):
                tgt = [max(tgt[0], 1.0 + (fx[0] - 1.0) * amt * k), max(tgt[1], fx[1] * amt * k),
                       max(tgt[2], fx[2] * amt)]
        tgt[0] = min(tgt[0], CAP_DIST)
        ease_in = SONIC_EASE_IN if sonic > 0.5 and self.effects_on else EASE_IN
        for i in range(3):
            self._damp(self.cur, self.vel, i, tgt[i], ease_in if tgt[i] > self.cur[i] else EASE_OUT, dt)
        pf, pb = self._punch_now() if self.effects_on else (0.0, 0.0)
        dist = min(CAP_DIST, max(0.25, self.cur[0]))
        fov = max(-30.0, min(CAP_FOV, self.cur[1] + pf))
        q = (round(dist, 3), round(fov, 2), round(self.cur[2], 3), round(pb, 3))
        self.fov_out = q[1]
        if q != self.written:
            self.written = q
            self._write(*q)
    def set_effects(self, on):
        self.effects_on = bool(on)
        if not self.effects_on:
            self.punches = []
    def _write(self, dist, fov, blur, back=0.0):
        pm, b = self.pm, self.base
        try:
            pm.write_float(b + BACK_MIN, SHIPPED[BACK_MIN] * dist + back)
            pm.write_float(b + BACK_MAX, SHIPPED[BACK_MAX] * dist + back)
            pm.write_float(b + FOV, SHIPPED[FOV] + fov)
            if self.blur_addr is not None:
                pm.write_float(self.blur_addr, max(self.blur_orig, blur))
        except Exception:
            pass
    def restore(self):
        if self.ok:
            self.cur = [1.0, 0.0, 0.0]
            self.vel = [0.0, 0.0, 0.0]
            self.punches = []
            self.fov_out = 0.0
            self._write(1.0, 0.0, self.blur_orig or 0.0)
            self.written = None
class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
_k32 = ctypes.WinDLL("kernel32")
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
_k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
SCAN_CHUNK, SCAN_PACE = 4 << 20, 0.002
def _scan(handle, pat):
    k32, MBI = _k32, _MBI
    addr, mbi = 0, MBI()
    while addr < 0x7FFFFFFFFFFF and k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                                       ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and size < (1 << 31):
            off = 0
            while off < size:
                n = min(SCAN_CHUNK, size - off)
                m = min(n + 64, size - off)
                buf = ctypes.create_string_buffer(m)
                got = ctypes.c_size_t()
                if k32.ReadProcessMemory(handle, ctypes.c_void_p(base + off), buf, m, ctypes.byref(got)) and got.value:
                    d = buf.raw[:got.value]
                    i = d.find(pat)
                    while 0 <= i < n:
                        if i % 4 == 0:
                            yield base + off + i
                        i = d.find(pat, i + 1)
                off += n
                time.sleep(SCAN_PACE)
        addr = base + size
_fx = SpeedFX()
start, update, restore = _fx.start, _fx.update, _fx.restore
punch = _fx.punch
def set_effects(on):
    _fx.set_effects(on)
def set_blur(on):
    global DIVE, BURNER, SONIC, WARP
    fx = {n: (t if on else t[:2] + (0.0,)) for n, t in _SHIPPED_FX.items()}
    DIVE, BURNER, SONIC, WARP = fx["DIVE"], fx["BURNER"], fx["SONIC"], fx["WARP"]
def set_strength(k):
    global strength
    try:
        k = float(k)
    except (TypeError, ValueError):
        return
    if math.isfinite(k):
        strength = max(0.0, min(STRENGTH_MAX, k))
def extra_fov():
    return _fx.fov_out
