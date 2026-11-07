import ctypes
import ctypes.wintypes as wt
import math
import mmap
import struct
import sys
import time
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
HUD_NAME, HUD_SIZE = "IronManFlightHUD", 128
HUD_FMT = "<dIddddIdddddId"
F_SONIC_LOW = 256
BOOT_HOLD = 3.2
BOOT_STOPS = ((0.00, (232, 46, 46)), (0.16, (232, 46, 46)), (0.40, (255, 134, 28)), (0.64, (255, 212, 46)),
              (0.88, (66, 214, 92)))
BOOT_BLUE = (70, 152, 255)
BOOT_TO_BLUE = 0.35
BOOT_BLINK = (1.0, 3)
MAP_NAME, MAP_MAX = "IronManFlightMap", 96
MAP_ENABLED = True
MAP_W, MAP_H = 400, 270
MAP_R = 5.0
AMBER = (255, 150, 45)
F_CRUISE = 128
CRUISE_TOP = 200000.0
WARPFX_NAME = "IronManFlightWarpFX"
F_FLYING, F_BURNING, F_LOCKED, F_SONIC, F_RIGHT, F_BRAKE, F_SHIPARMS = 1, 2, 4, 8, 16, 32, 64
W, H = 430, 150
POS = (0.028, 0.60)
FPS = 30
FADE = 0.35
WHITE = (236, 242, 245)
ORANGE = (255, 150, 40)
RED = (255, 70, 60)
DIM = (236, 242, 245, 70)
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
F_SONIC_GATED = 1024
F_SONIC_REFUSED = 2048
PLATE = (14, 18, 24)
HINT_IN = (0.35, 0.45)
HINT_HOLD = 0.8
HUD_STYLES = ("gauge", "off")
DEFAULT_CONFIG = dict(style="gauge", space_map=True, shock_waves=True, cruise_top=CRUISE_TOP, panel_key="F7")
u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32")
k32 = ctypes.WinDLL("kernel32")
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
u32.GetDC.restype = wt.HDC
u32.GetDC.argtypes = [wt.HWND]
u32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u32.GetForegroundWindow.restype = wt.HWND
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
u32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.c_void_p, ctypes.c_void_p, wt.HDC, ctypes.c_void_p,
                                    wt.DWORD, ctypes.c_void_p, wt.DWORD]
g32.CreateCompatibleDC.restype = wt.HDC
g32.CreateCompatibleDC.argtypes = [wt.HDC]
g32.CreateDIBSection.restype = wt.HBITMAP
g32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
g32.SelectObject.restype = wt.HGDIOBJ
g32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g32.DeleteObject.argtypes = [wt.HGDIOBJ]
g32.DeleteDC.argtypes = [wt.HDC]
k32.OpenProcess.restype = wt.HANDLE
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.GetModuleHandleW.restype = wt.HMODULE
u32.CreateWindowExW.restype = wt.HWND
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]
class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]
def font(size, style="SemiLight Condensed"):
    try:
        f = ImageFont.truetype(FONT, size)
        try:
            f.set_variation_by_name(style)
        except Exception:
            pass
        return f
    except OSError:
        return ImageFont.load_default()
def read_config(path=None):
    cfg = dict(DEFAULT_CONFIG)
    try:
        import settings
        S = settings.load(path, quiet=True)
    except Exception:
        return cfg
    try:
        cfg["style"] = "off" if S.hud["hud"] in (False, "off", "no") else "gauge"
        cfg["space_map"] = bool(S.hud["space_map"])
        cfg["shock_waves"] = bool(S.hud["shock_waves"])
    except Exception:
        pass
    try:
        top = float(S.cruise["top_speed_kms"]) * 1000.0
        if math.isfinite(top) and top >= 1000.0:
            cfg["cruise_top"] = top
    except Exception:
        pass
    try:
        vk = S.keys["panel"]
        cfg["panel_key"] = settings.key_name(vk) if vk else ""
    except Exception:
        pass
    return cfg
def ini_mtime():
    try:
        import settings
        return settings.INI.stat().st_mtime_ns
    except Exception:
        return None
def apply_config(cfg):
    global CRUISE_TOP, MAP_ENABLED
    CRUISE_TOP = float(cfg.get("cruise_top", DEFAULT_CONFIG["cruise_top"]))
    MAP_ENABLED = bool(cfg.get("space_map", True))
def idle_state():
    return dict(flags=0, fuel=1.0, charge=1.0, sonic=0.0, stage=0, prog=0.0, since=0.0, speed=0.0, dist=-1.0,
                build=-1.0, throttle=0.0, cruise=0.0, shock_n=0, shock_k=1.0)
def unpack_hud(buf, offset=0):
    (t, flags, fuel, charge, sonic, spd, stage, prog, since, build, thr, lvl, shn,
     shk) = struct.unpack_from(HUD_FMT, buf, offset)
    return t, dict(flags=flags, fuel=fuel, charge=charge, sonic=sonic, stage=stage, prog=prog, since=since,
                   speed=spd, dist=-1.0, build=build, throttle=thr, cruise=lvl, shock_n=shn, shock_k=shk)
def _toward(a, want, dt, secs):
    return a + max(-dt / secs, min(dt / secs, want - a))
class Overlay:
    def __init__(self):
        self.proc = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self.proc, hInstance=hinst, lpszClassName="IronManHUD")
        u32.RegisterClassW(ctypes.byref(wc))
        ex = 0x80000 | 0x20 | 0x8 | 0x80 | 0x8000000
        u32.CreateWindowExW.restype = wt.HWND
        self.hwnd = u32.CreateWindowExW(ex, "IronManHUD", "Iron Man HUD", 0x80000000, 0, 0, W, H,
                                        None, None, hinst, None)
        self.shown = False
        self.size = (W, H)
    def pump(self):
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
    def show(self, img, x, y):
        w, h = img.size
        a_ = np.asarray(img, dtype=np.uint16)
        px = np.empty((h, w, 4), np.uint8)
        al = a_[..., 3]
        px[..., 0] = a_[..., 2] * al // 255
        px[..., 1] = a_[..., 1] * al // 255
        px[..., 2] = a_[..., 0] * al // 255
        px[..., 3] = al
        px = px.tobytes()
        sdc = u32.GetDC(None)
        mdc = g32.CreateCompatibleDC(sdc)
        bi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                              biBitCount=32)
        bits = ctypes.c_void_p()
        g32.CreateDIBSection.restype = wt.HBITMAP
        bmp = g32.CreateDIBSection(mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, px, len(px))
        old = g32.SelectObject(mdc, bmp)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        pt, sz, src = wt.POINT(x, y), wt.SIZE(w, h), wt.POINT(0, 0)
        u32.UpdateLayeredWindow(self.hwnd, sdc, ctypes.byref(pt), ctypes.byref(sz), mdc, ctypes.byref(src), 0,
                                ctypes.byref(blend), 2)
        g32.SelectObject(mdc, old)
        g32.DeleteObject(bmp)
        g32.DeleteDC(mdc)
        u32.ReleaseDC(None, sdc)
        if not self.shown:
            u32.ShowWindow(self.hwnd, 4)
            self.shown = True
    def hide(self):
        if self.shown:
            u32.ShowWindow(self.hwnd, 0)
            self.shown = False
SHOCK_TIME = 1.0
SHOCK_CENTRE = (0.5, 0.56)
SHOCK_SIDE = 0.09
SHOCK_REACH = 1.35
SHOCK_SQUASH = 0.78
SHOCK_EDGE = (150, 205, 255)
SHOCK_K_MAX = 3.0
SHOCK_PAIR = 0.2
SHOCK_WAVES = 3
SHOCK_TRAIL = ((1.5, 0.09, 0.86, 0.70, 0.80),
               (2.2, 0.18, 0.74, 0.55, 0.65))
def shock_time(k):
    if k <= 1.0:
        return SHOCK_TIME * (0.45 + 0.55 * k)
    return SHOCK_TIME * (1.0 + 0.45 * (k - 1.0))
def shock_size(k):
    try:
        k = float(k)
    except (TypeError, ValueError):
        return 1.0
    return min(SHOCK_K_MAX, max(0.1, k)) if math.isfinite(k) else 1.0
def shock_look(k):
    if k <= 1.0:
        g = 0.3 + 0.7 * k
        return shock_time(k), SHOCK_REACH * g, 136 * g, 0.10 * g, int(30 * k), 0.55 + 0.45 * k
    e = k - 1.0
    return (shock_time(k), SHOCK_REACH * (1.0 + 0.25 * e), 136 * (1.0 + 0.7 * e), 0.10 * (1.0 + 0.9 * e),
            int(min(60.0, 30 * (1.0 + 0.5 * e))), 1.0 + 0.45 * e)
def shock_flash(t, k):
    if k <= 1.0:
        return int(110 * k * math.sin(math.pi * t / 0.14)) if 0.0 <= t < 0.14 and k > 0.3 else 0
    e = k - 1.0
    dur = 0.14 + 0.02 * e
    pop = min(200.0, 110.0 + 50.0 * e) * math.sin(math.pi * t / dur) if 0.0 <= t < dur else 0.0
    gk = min(1.0, max(0.0, (k - 2.0) / 0.6))
    glow = 70.0 * gk * (1.0 - t / 0.6) ** 2 if 0.0 <= t < 0.6 else 0.0
    return int(max(pop, glow))
BRAKE_SHOCK_TIME = 0.45
BRAKE_REACH = 0.32
BRAKE_GAP = 0.07
BRAKE_PALMS = (0.035, 0.50)
def shock_colours():
    lut = np.zeros(256, np.uint32)
    for a in range(256):
        f = a / 255.0
        r, g, b = (int(e + (255 - e) * f ** 0.7) for e in SHOCK_EDGE)
        lut[a] = (b * a // 255) | ((g * a // 255) << 8) | ((r * a // 255) << 16) | (a << 24)
    return lut
def shock_lut(base, floor=0, alpha=1.0):
    idx = np.maximum(np.arange(256), min(255, max(0, int(floor))))
    if alpha < 0.999:
        idx = (idx * int(max(0.0, alpha) * 256)) >> 8
    return base[idx]
def shock_fill(view, a, lut, idx=None, rows=64):
    h, w = a.shape
    if idx is None or idx.shape[1] != w:
        idx = np.empty((max(1, min(rows, h)), w), np.intp)
    n = idx.shape[0]
    for y in range(0, h, n):
        m = min(n, h - y)
        idx[:m] = a[y:y + m]
        view[y:y + m] = lut[idx[:m]]
    return idx
def _shock_wave(d, cx, cy, t, gh, dur, reach, thick, core, wake_a, amp=1.0, part="all", ghost=0.25, floor=0):
    u = min(1.0, t / dur)
    k = gh / 1440.0
    ease = 1.0 - (1.0 - u) ** 3
    r0 = (0.03 + (reach - 0.03) * ease) * gh
    wake = int(wake_a * (1.0 - u) ** 2)
    if wake and part in ("all", "wake"):
        d.ellipse([cx - r0, cy - r0 * SHOCK_SQUASH, cx + r0, cy + r0 * SHOCK_SQUASH], fill=wake)
    tb = 0.22 * dur / SHOCK_TIME
    if t < tb and core > 0.0 and part in ("all", "burst"):
        c = int(255 * amp * (1.0 - t / tb) ** 1.5)
        for i in range(8):
            rr = (0.2 + t / tb) * core * gh * (1.0 - i / 8.0) + 1
            d.ellipse([cx - rr, cy - rr * SHOCK_SQUASH, cx + rr, cy + rr * SHOCK_SQUASH],
                      fill=min(255, int(c * ((i + 1) / 8.0) ** 2)))
    if part in ("all", "fronts"):
        for rf, af in ((1.0, 1.0), (0.7, ghost)):
            if af <= 0.0:
                continue
            r = r0 * rf
            th = thick * (0.12 + u) * k
            peak = 255 * af * amp * (1.0 - u) ** 1.2
            for i in range(10):
                w_ = max(1, int(th * (1.0 - i / 10.0)))
                a_ = min(255, max(floor, int(peak * ((i + 1) / 10.0) ** 2.2)))
                rr = r + w_ / 2
                d.ellipse([cx - rr, cy - rr * SHOCK_SQUASH, cx + rr, cy + rr * SHOCK_SQUASH], outline=a_, width=w_)
    return wake
def shock_paint(gw, gh, waves, side=-1.0, tb=None):
    im = Image.new("L", (gw, gh), 0)
    d = ImageDraw.Draw(im)
    cx = gw * (SHOCK_CENTRE[0] - side * SHOCK_SIDE)
    cy = gh * SHOCK_CENTRE[1]
    run = []
    for t, k in waves or ():
        if t is None:
            continue
        k = shock_size(k)
        look = shock_look(k)
        if 0.0 <= t < look[0]:
            run.append((t, k, look))
    wakes = [_shock_wave(d, cx, cy, t, gh, *look, part="wake") for t, k, look in run]
    floor = 0
    for (t, k, look), wake in zip(run, wakes):
        dur, reach, thick, core, wake_a, amp = look
        if k <= 1.0:
            _shock_wave(d, cx, cy, t, gh, *look, part="burst")
            _shock_wave(d, cx, cy, t, gh, *look, part="fronts")
        else:
            for k_from, lag, rx, tx, ax in reversed(SHOCK_TRAIL):
                s_ = min(1.0, max(0.0, (k - k_from) / 0.4 + 0.5))
                if s_ > 0.0 and 0.0 <= t - lag < dur - lag:
                    _shock_wave(d, cx, cy, t - lag, gh, dur - lag, reach * rx, thick * tx, 0.0, 0, amp * ax * s_,
                                part="fronts", ghost=0.0, floor=wake)
            _shock_wave(d, cx, cy, t, gh, *look, part="fronts", floor=wake)
            tb_ = 0.22 * dur / SHOCK_TIME
            if t < tb_:
                R = (0.2 + t / tb_) * core * gh + 2
                box = (max(0, int(cx - R)), max(0, int(cy - R * SHOCK_SQUASH)), min(gw, int(cx + R) + 1),
                       min(gh, int(cy + R * SHOCK_SQUASH) + 1))
                if box[2] > box[0] and box[3] > box[1]:
                    patch = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
                    _shock_wave(ImageDraw.Draw(patch), cx - box[0], cy - box[1], t, gh, *look, part="burst")
                    im.paste(ImageChops.lighter(im.crop(box), patch), box[:2])
        floor = max(floor, shock_flash(t, k))
    if tb is not None:
        for i, dx in enumerate((-BRAKE_PALMS[0], BRAKE_PALMS[0])):
            tt = tb - i * BRAKE_GAP
            if 0.0 <= tt < BRAKE_SHOCK_TIME:
                _shock_wave(d, cx + dx * gw, gh * BRAKE_PALMS[1], tt, gh, BRAKE_SHOCK_TIME, BRAKE_REACH, 60, 0.05, 20)
        if 0.0 <= tb < 0.08:
            floor = max(floor, int(45 * math.sin(math.pi * tb / 0.08)))
    return im, floor
class Shock:
    _wave = staticmethod(_shock_wave)
    def __init__(self, hinst):
        ex = 0x80000 | 0x20 | 0x8 | 0x80 | 0x8000000
        self.hwnd = u32.CreateWindowExW(ex, "IronManHUD", "Iron Man Shock", 0x80000000, 0, 0, 1, 1,
                                        None, None, hinst, None)
        self.size, self.mdc, self.view, self.shown = None, None, None, False
        self.lut = shock_colours()
        self.idx = None
    def _alloc(self, w, h):
        sdc = u32.GetDC(None)
        self.mdc = g32.CreateCompatibleDC(sdc)
        u32.ReleaseDC(None, sdc)
        bi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                              biBitCount=32)
        bits = ctypes.c_void_p()
        bmp = g32.CreateDIBSection(self.mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        g32.SelectObject(self.mdc, bmp)
        self.view = np.ctypeslib.as_array((ctypes.c_uint32 * (w * h)).from_address(bits.value)).reshape(h, w)
        self.size = (w, h)
    def frame(self, t, rect, side=-1.0, tb=None, k=1.0, alpha=1.0, waves=None):
        gx, gy, gw, gh = rect
        if self.size != (gw, gh):
            self._alloc(gw, gh)
        if waves is None:
            waves = [] if t is None else [(t, k)]
        im, floor = shock_paint(gw, gh, waves, side, tb)
        self.idx = shock_fill(self.view, np.asarray(im), shock_lut(self.lut, floor, alpha), self.idx)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        pt, sz, src = wt.POINT(gx, gy), wt.SIZE(gw, gh), wt.POINT(0, 0)
        sdc = u32.GetDC(None)
        u32.UpdateLayeredWindow(self.hwnd, sdc, ctypes.byref(pt), ctypes.byref(sz), self.mdc, ctypes.byref(src), 0,
                                ctypes.byref(blend), 2)
        u32.ReleaseDC(None, sdc)
        if not self.shown:
            u32.ShowWindow(self.hwnd, 4)
            self.shown = True
    def hide(self):
        if self.shown:
            u32.ShowWindow(self.hwnd, 0)
            self.shown = False
def game_rect():
    fg = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(64)
    u32.GetWindowTextW(fg, buf, 64)
    if buf.value != "No Man's Sky":
        return None
    rc = wt.RECT()
    u32.GetClientRect(fg, ctypes.byref(rc))
    pt = wt.POINT(0, 0)
    u32.ClientToScreen(fg, ctypes.byref(pt))
    return pt.x, pt.y, rc.right, rc.bottom
def spaced(d, xy, text, f, fill, gap):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + gap
    return x
def _mix(a, b, k):
    k = min(1.0, max(0.0, k))
    return tuple(int(round(255.0 * (((x / 255.0) ** 2.2) * (1.0 - k) + ((y / 255.0) ** 2.2) * k) ** (1.0 / 2.2)))
                 for x, y in zip(a, b))
def boot_colour(prog, online_t=None):
    p = min(1.0, max(0.0, prog))
    c = BOOT_STOPS[-1][1]
    for (p0, c0), (p1, c1) in zip(BOOT_STOPS, BOOT_STOPS[1:]):
        if p <= p1:
            k = (p - p0) / (p1 - p0)
            c = _mix(c0, c1, k * k * (3.0 - 2.0 * k))
            break
    if online_t is not None:
        k = min(1.0, max(0.0, online_t / BOOT_TO_BLUE))
        c = _mix(c, BOOT_BLUE, k * k * (3.0 - 2.0 * k))
    return c
def boot_gain(online_t):
    if online_t is None:
        return 1.0
    tb = online_t - BOOT_TO_BLUE
    if not 0.0 <= tb < BOOT_BLINK[0]:
        return 1.0
    return 0.3 + 0.7 * (0.5 + 0.5 * math.cos(2.0 * math.pi * BOOT_BLINK[1] * tb / BOOT_BLINK[0]))
class MapCard:
    SS = 2
    MERGE = 0.55
    POI_MAX = 5
    GLIDE = 0.22
    RANK = {4: 0, 5: 1, 3: 2, 2: 3, 7: 4, 6: 5, 1: 6}
    def __init__(self, scale, mark=1.0, plain=False):
        self.s = scale
        self.mark, self.plain = mark, plain
        self.f_lab = font(max(6, int(12 * scale)), "SemiLight Condensed")
        self.marks = []
        self.t = None
        self.static = None
    def proj(self, x, y, z, cx, cy, k):
        return cx + x * k, cy + z * k * 0.38 - y * k * 0.82
    def _clean(self, rows):
        rows = [r for r in rows if r[0] in self.RANK]
        big = sorted((r for r in rows if r[0] != 1), key=lambda r: self.RANK[r[0]])
        poi = sorted((r for r in rows if r[0] == 1), key=lambda r: r[1] * r[1] + r[2] * r[2] + r[3] * r[3])
        out = []
        for kind, x, y, z in big + poi:
            for m in out:
                if (m[1] - x) ** 2 + (m[2] - y) ** 2 + (m[3] - z) ** 2 < self.MERGE ** 2:
                    n = m[4] + 1
                    m[1], m[2], m[3], m[4] = (m[1] * m[4] + x) / n, (m[2] * m[4] + y) / n, (m[3] * m[4] + z) / n, n
                    break
            else:
                if kind == 1 and sum(1 for m in out if m[0] == 1) >= self.POI_MAX:
                    continue
                out.append([3 if kind == 7 else kind, x, y, z, 1])
        return out
    def _glide(self, targets, now):
        dt = 0.0 if self.t is None else max(0.0, min(0.5, now - self.t))
        self.t = now
        f = 1.0 - math.exp(-dt / self.GLIDE)
        old, new = self.marks, []
        for kind, x, y, z, _ in targets:
            best, bd = None, 1.5 ** 2
            for m in old:
                if m[0] == kind:
                    d_ = (m[1] - x) ** 2 + (m[2] - y) ** 2 + (m[3] - z) ** 2
                    if d_ < bd:
                        best, bd = m, d_
            if best is None:
                new.append([kind, x, y, z, 0.0])
            else:
                old.remove(best)
                new.append([kind, best[1] + (x - best[1]) * f, best[2] + (y - best[2]) * f,
                            best[3] + (z - best[3]) * f, min(1.0, best[4] + dt / 0.3)])
        self.marks = new
        return new
    def _static(self, w, h, W2, H2, P, cx, cy, k, col, lw, thin):
        yy, xx = np.mgrid[0:h, 0:w]
        rr = np.sqrt(((xx - w * 0.5) / (w * 0.5)) ** 2 + ((yy - h * 0.55) / (h * 0.5)) ** 2)
        back = np.zeros((h, w, 4), np.uint8)
        back[..., 0], back[..., 1], back[..., 2] = 14, 10, 6
        back[..., 3] = (np.clip((1.0 - rr) / 0.5, 0.0, 1.0) ** 1.4 * (0 if self.plain else 150)).astype(np.uint8)
        img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        A = 255
        dome = [P(MAP_R * math.cos(math.radians(t)), MAP_R * math.sin(math.radians(t)), 0.0) for t in range(0, 181, 3)]
        d.polygon(dome + [P(MAP_R, 0, 0)], fill=col + (int(A * 0.03),))
        for i, a_ in ((1, 0.20), (2, 0.24), (3, 0.42)):
            r = MAP_R * i / 3
            d.ellipse([cx - r * k, cy - r * k * 0.38, cx + r * k, cy + r * k * 0.38],
                      outline=col + (int(A * a_),), width=lw if i == 3 else thin)
        d.line(dome, fill=col + (int(A * 0.70),), width=lw)
        img = img.reduce(self.SS)
        return Image.fromarray(back, "RGBA"), img
    @staticmethod
    def _faded(im, alpha):
        if alpha >= 0.999:
            return im
        a = np.asarray(im).copy()
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        return Image.fromarray(a, "RGBA")
    def draw(self, alpha, rows, now):
        s, S = self.s, self.SS
        w, h = int(MAP_W * s), int(MAP_H * s)
        W2, H2 = w * S, h * S
        A = int(255 * alpha)
        cx, cy, k = W2 * 0.5, H2 * 0.66, (W2 * 0.42) / MAP_R
        P = lambda x, y, z: self.proj(x, y, z, cx, cy, k)
        col, hi = AMBER, (255, 222, 170)
        ms = s * self.mark
        lw = max(1, int(1.3 * ms * S))
        thin = max(1, int(0.8 * ms * S))
        if self.static is None:
            self.static = self._static(w, h, W2, H2, P, cx, cy, k, col, lw, thin)
        img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        sweep = (now * 0.35) % 1.0
        for j in range(6):
            t = (sweep - j * 0.012) * 2 * math.pi
            d.line([P(0, 0, 0), P(MAP_R * math.sin(t), 0, -MAP_R * math.cos(t))],
                   fill=col + (int(A * 0.22 * (1 - j / 6)),), width=thin)
        marks = self._glide(self._clean(rows), now)
        for kind, x, y, z, fade in sorted(marks, key=lambda m: m[3]):
            a1 = A * fade
            y = max(-MAP_R * (0.18 if kind == 1 else 0.45), min(MAP_R * 0.95, y))
            rr_ = math.sqrt(x * x + z * z)
            if rr_ > MAP_R:
                x, z = x * MAP_R / rr_, z * MAP_R / rr_
            if kind == 1 and y < 0:
                y *= max(0.0, 1.0 - rr_ / MAP_R) / 0.4 if rr_ > MAP_R * 0.6 else 1.0
            gx, gy = P(x, 0, z)
            tx, ty = P(x, y, z)
            if kind == 1:
                r_ = 2.2 * ms * S
                d.ellipse([tx - r_, ty - r_, tx + r_, ty + r_], fill=hi + (int(a1 * 0.75),))
                continue
            d.line([(gx, gy), (tx, ty)], fill=col + (int(a1 * 0.40),), width=thin)
            r0 = 1.6 * ms * S
            d.ellipse([gx - r0, gy - r0 * 0.5, gx + r0, gy + r0 * 0.5], fill=col + (int(a1 * 0.45),))
            if kind == 2:
                r_ = 5.5 * ms * S
                d.ellipse([tx - r_, ty - r_, tx + r_, ty + r_], outline=hi + (int(a1),), width=lw)
            elif kind in (3, 4, 5):
                r_ = (6.0 if kind != 3 else 4.8) * ms * S
                pts = [(tx, ty - r_), (tx + r_, ty), (tx, ty + r_), (tx - r_, ty)]
                if kind == 4:
                    d.polygon(pts, fill=hi + (int(a1 * 0.9),))
                else:
                    d.polygon(pts, outline=hi + (int(a1),), width=lw)
            else:
                r_ = 3.6 * ms * S
                c2 = (255, 80, 60) if kind == 6 else (170, 230, 255)
                d.polygon([(tx, ty - r_), (tx + r_ * 0.8, ty + r_ * 0.7), (tx - r_ * 0.8, ty + r_ * 0.7)], fill=c2 + (int(a1),))
        r_ = 4.5 * ms * S
        d.polygon([(cx, cy - r_ * 1.35), (cx + r_, cy + r_ * 0.6), (cx, cy + r_ * 0.15), (cx - r_, cy + r_ * 0.6)],
                  fill=WHITE + (A,))
        img = Image.alpha_composite(self._faded(self.static[1], alpha), img.reduce(S))
        glow = img.filter(ImageFilter.GaussianBlur(3.0 * s))
        img = Image.alpha_composite(Image.alpha_composite(self._faded(self.static[0], alpha), glow), img)
        if self.plain:
            return img
        dl = ImageDraw.Draw(img)
        tw = dl.textlength("S P A C E   M A P", font=self.f_lab)
        dl.text((int(w * 0.5 - tw * 0.5), int(14 * s)), "S P A C E   M A P", font=self.f_lab, fill=col + (int(A * 0.6),))
        return img
class SphereMap(MapCard):
    TILT = math.radians(22.0)
    def __init__(self, r_px, mark=1.0):
        MapCard.__init__(self, r_px / 65.0, mark=mark, plain=True)
        self.r_px = r_px
    def _proj(self, x, y, z, c, k):
        ca, sa = math.cos(self.TILT), math.sin(self.TILT)
        return c + x * k, c + (z * sa - y * ca) * k
    def _depth(self, y, z):
        return z * math.cos(self.TILT) + y * math.sin(self.TILT)
    def _ring(self, d, c, k, y0, rr, col, w, steps=72):
        pts = [self._proj(rr * math.cos(2 * math.pi * i / steps), y0, rr * math.sin(2 * math.pi * i / steps), c, k)
               for i in range(steps + 1)]
        d.line(pts, fill=col, width=w)
    def _sphere_static(self, W2, c, k, col, lw, thin):
        img = Image.new("RGBA", (W2, W2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        R = MAP_R * k
        d.ellipse([c - R, c - R, c + R, c + R], fill=col + (10,))
        for i, a_ in ((1, 0.18), (2, 0.22), (3, 0.45)):
            self._ring(d, c, k, 0.0, MAP_R * i / 3, col + (int(255 * a_),), lw if i == 3 else thin)
        for lat in (45.0, -45.0):
            self._ring(d, c, k, MAP_R * math.sin(math.radians(lat)), MAP_R * math.cos(math.radians(lat)),
                       col + (int(255 * 0.16),), thin)
        pts = [self._proj(0.0, MAP_R * math.cos(2 * math.pi * i / 72), MAP_R * math.sin(2 * math.pi * i / 72), c, k)
               for i in range(73)]
        d.line(pts, fill=col + (int(255 * 0.14),), width=thin)
        d.ellipse([c - R, c - R, c + R, c + R], outline=col + (int(255 * 0.75),), width=lw)
        return img.reduce(self.SS)
    def draw(self, alpha, rows, now):
        S = self.SS
        w = int(2 * self.r_px)
        W2 = w * S
        A = int(255 * alpha)
        c = W2 * 0.5
        k = (W2 * 0.5 - 2.0 * S) / MAP_R
        P = lambda x, y, z: self._proj(x, y, z, c, k)
        col, hi = AMBER, (255, 222, 170)
        ms = self.s * self.mark
        lw = max(1, int(1.3 * ms * S))
        thin = max(1, int(0.8 * ms * S))
        if self.static is None or self.static[0] != w:
            self.static = (w, self._sphere_static(W2, c, k, col, lw, thin))
        img = Image.new("RGBA", (W2, W2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        sweep = (now * 0.35) % 1.0
        for j in range(6):
            t = (sweep - j * 0.012) * 2 * math.pi
            d.line([P(0, 0, 0), P(MAP_R * math.sin(t), 0, -MAP_R * math.cos(t))],
                   fill=col + (int(A * 0.22 * (1 - j / 6)),), width=thin)
        marks = self._glide(self._clean(rows), now)
        for kind, x, y, z, fade in sorted(marks, key=lambda m: self._depth(m[2], m[3])):
            a1 = A * fade
            r3 = math.sqrt(x * x + y * y + z * z)
            if r3 > MAP_R * 0.97:
                f_ = MAP_R * 0.97 / r3
                x, y, z = x * f_, y * f_, z * f_
            gx, gy = P(x, 0, z)
            tx, ty = P(x, y, z)
            if kind == 1:
                r_ = 2.2 * ms * S
                d.ellipse([tx - r_, ty - r_, tx + r_, ty + r_], fill=hi + (int(a1 * 0.75),))
                continue
            d.line([(gx, gy), (tx, ty)], fill=col + (int(a1 * 0.40),), width=thin)
            r0 = 1.6 * ms * S
            d.ellipse([gx - r0, gy - r0 * 0.5, gx + r0, gy + r0 * 0.5], fill=col + (int(a1 * 0.45),))
            if kind == 2:
                r_ = 5.5 * ms * S
                d.ellipse([tx - r_, ty - r_, tx + r_, ty + r_], outline=hi + (int(a1),), width=lw)
            elif kind in (3, 4, 5):
                r_ = (6.0 if kind != 3 else 4.8) * ms * S
                pts = [(tx, ty - r_), (tx + r_, ty), (tx, ty + r_), (tx - r_, ty)]
                if kind == 4:
                    d.polygon(pts, fill=hi + (int(a1 * 0.9),))
                else:
                    d.polygon(pts, outline=hi + (int(a1),), width=lw)
            else:
                r_ = 3.6 * ms * S
                c2 = (255, 80, 60) if kind == 6 else (170, 230, 255)
                d.polygon([(tx, ty - r_), (tx + r_ * 0.8, ty + r_ * 0.7), (tx - r_ * 0.8, ty + r_ * 0.7)],
                          fill=c2 + (int(a1),))
        r_ = 4.5 * ms * S
        d.polygon([(c, c - r_ * 1.35), (c + r_, c + r_ * 0.6), (c, c + r_ * 0.15), (c - r_, c + r_ * 0.6)],
                  fill=WHITE + (A,))
        img = Image.alpha_composite(self._faded(self.static[1], alpha), img.reduce(S))
        glow = img.filter(ImageFilter.GaussianBlur(2.0 * self.s))
        return Image.alpha_composite(glow, img)
COMPASS_A, COMPASS_B, COMPASS_CY = 368.0, 82.2, -2.0
ARC_GAP = 42.0
ARC_SPAN = 84.0
GAUGE_W = (13.0, 9.0, 9.0, 7.0)
GAUGE_LINE = 2.0
GAUGE_MAP_R = 75.0
GAUGE_MAP_GAP = 6.0
GAUGE_BOOM_SECTIONS = 3
GAUGE_FIRST_Q = 0.25
GAUGE_EMPTY = (27, 30, 46)
GAUGE_DISC = (10, 14, 22)
GAUGE_COLS = {
    "throttle": ((34, 206, 52), (200, 255, 34)),
    "burner": ((40, 100, 232), (92, 156, 255)),
    "sonic": ((250, 190, 26), (226, 124, 6)),
    "cruise": ((132, 82, 246), (214, 168, 255)),
    "reverse": ((196, 26, 30), (255, 96, 72)),
    "first": ((10, 156, 132), (84, 232, 206)),
    "refused": ((255, 44, 34), (255, 116, 92)),
    "refused_hi": ((255, 236, 228), (255, 255, 255)),
}
GAUGE_CRUISE_TIERS = 3
GAUGE_GATED = (0.45, 0.30)
GAUGE_REFUSED_HZ = 5.0
SPEED_EASE = 0.15
SPEED_LAG = (1.5, 0.06)
SPEED_HZ = 15.0
HOVER_IN, HOVER_OUT = 0.8, 1.5
WARPFX_FRESH = 0.5
SPEED_PX = (32.0, 19.0, 22.0)
SPEED_GAP = 8.0
SPEED_WORD_COLS = {"HOVER MODE": (190, 250, 232), "REVERSE MODE": (255, 150, 132)}
def speed_text(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = 0.0
    return f"{int(round(v)) if math.isfinite(v) and v > 0.0 else 0:,} U/S"
def merge_warpfx(st, buf, now):
    if not st.get("flags", 0) & F_CRUISE:
        return st
    try:
        t, _s, spd, _x, _y, dist = struct.unpack_from("<6d", buf, 0)
    except Exception:
        return st
    if t > 0.0 and now - t < WARPFX_FRESH and math.isfinite(spd) and spd >= 0.0:
        st["speed"] = spd
    if now - t < 1.0:
        st["dist"] = dist
    return st
class SpeedReadout:
    def __init__(self):
        self.v = None
        self.t = None
        self.hover = False
        self.mode = None
        self.text = ""
        self.t_text = -99.0
    @staticmethod
    def _num(x, default=0.0):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return default
        return x if math.isfinite(x) else default
    def step(self, st, now):
        spd = max(0.0, self._num(st.get("speed", 0.0)))
        dt = 0.0 if self.t is None else min(0.5, max(0.0, now - self.t))
        self.t = now
        if self.v is None:
            self.v = spd
        else:
            self.v += (spd - self.v) * (1.0 - math.exp(-dt / SPEED_EASE))
            lag = max(SPEED_LAG[0], SPEED_LAG[1] * spd)
            self.v = min(spd + lag, max(spd - lag, self.v))
        thr = self._num(st.get("throttle", 0.0))
        reverse = thr <= -0.5
        if reverse or abs(thr) > 1e-6:
            self.hover = False
        else:
            self.hover = self.v <= HOVER_OUT if self.hover else self.v < HOVER_IN
        mode = "reverse" if reverse else "hover" if self.hover else "speed"
        text = "REVERSE MODE" if reverse else "HOVER MODE" if self.hover else speed_text(self.v)
        if text != self.text and (mode != self.mode or now - self.t_text >= 1.0 / SPEED_HZ - 1e-6):
            self.text, self.t_text = text, now
        self.mode = mode
        return self.text
class Gauge:
    SS = 2
    speed = False
    def __init__(self, scale, aspect=16.0 / 9.0):
        self.s = scale
        self.A = COMPASS_A * aspect / (16.0 / 9.0)
        k = scale * self.SS
        self.k = k
        L = self.L = GAUGE_LINE * k
        gw, bw, ow, cw = (w * k for w in GAUGE_W)
        d0 = ARC_GAP * k
        self.g = (d0, d0 + gw)
        self.b = (self.g[1] + L, self.g[1] + L + bw)
        self.o = (self.b[1], self.b[1] + ow)
        self.c = (self.o[1] + L, self.o[1] + L + cw)
        self.outer = self.c[1] + L
        self.t0, self.t1 = math.radians(90.0 + ARC_SPAN), math.radians(90.0 - ARC_SPAN)
        ends = [self._xy(t, d / k) for t in (self.t0, self.t1) for d in (self.g[0] - L, self.outer + L)]
        bottom_band = COMPASS_CY + COMPASS_B + self.outer / k
        self.sp_base = bottom_band + SPEED_GAP + SPEED_PX[0] * 0.78
        self.map_cy = self.sp_base + SPEED_PX[0] * 0.32 + GAUGE_MAP_GAP + GAUGE_MAP_R
        self.HALF = max(max(abs(x) for x, _ in ends), GAUGE_MAP_R) + 6.0
        self.Y0 = min(y for _, y in ends) - 6.0
        Y1 = self.map_cy + GAUGE_MAP_R + 6.0
        self.W2 = int(2 * self.HALF * k) // self.SS * self.SS
        self.H2 = int((Y1 - self.Y0) * k) // self.SS * self.SS
        self.size = (self.W2 // self.SS, self.H2 // self.SS)
        dref = (self.g[0] + self.c[1]) / 2 / k
        ts = np.linspace(self.t0, self.t1, 1201)
        pts = np.array([self._xy(t, dref) for t in ts])
        self.ts = ts
        self.cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]) * k
        self.len = float(self.cum[-1])
        self.dtdu = ((ts[1] - ts[0]) / (self.cum[1] - self.cum[0]), (ts[-1] - ts[-2]) / (self.cum[-1] - self.cum[-2]))
        self.r_map = (GAUGE_MAP_R - GAUGE_LINE) * scale
        self.static = None
        self.mapc, self.map_img, self.map_t = None, None, -9.0
        self.speedo = SpeedReadout()
        self.sp_at = (self.HALF * scale, (self.sp_base - self.Y0) * scale)
        self.sp_fonts, self.sp_img = None, None
        self.refused_t = None
    def _xy(self, t, d):
        c, s_ = math.cos(t), math.sin(t)
        nx, ny = COMPASS_B * c, self.A * s_
        n = math.hypot(nx, ny) or 1.0
        return self.A * c + d * nx / n, COMPASS_CY + COMPASS_B * s_ + d * ny / n
    def _pt(self, t, d):
        x, y = self._xy(t, d / self.k)
        return (x + self.HALF) * self.k, (y - self.Y0) * self.k
    def _t(self, u):
        if u <= 0.0:
            return self.t0 + u * self.dtdu[0]
        if u >= self.len:
            return self.t1 + (u - self.len) * self.dtdu[1]
        return float(np.interp(u, self.cum, self.ts))
    def _poly(self, a, b, u0, u1):
        if u1 <= u0:
            return None
        t0, t1 = self._t(u0), self._t(u1)
        n = max(1, int(math.ceil(abs(t1 - t0) / math.radians(1.0))))
        us = [u0 + (u1 - u0) * i / n for i in range(n + 1)]
        tt = [self._t(u) for u in us]
        return [self._pt(t, a) for t in tt] + [self._pt(t, b) for t in reversed(tt)]
    def _band(self, d, a, b, u0, u1, fill):
        p = self._poly(a, b, u0, u1)
        if p:
            d.polygon(p, fill=fill)
    def _grad(self, d, a, b, u0, u1, cols, alpha, inward=False, gain=1.0):
        if u1 <= u0:
            return
        n = max(3, int((b - a) / (2.0 * self.k)))
        e, m = cols
        for i in range(n):
            t = (i + 0.5) / n
            f = t if inward else 1.0 - abs(2.0 * t - 1.0)
            c = tuple(min(255, int((e[j] + (m[j] - e[j]) * f) * gain)) for j in range(3))
            self._band(d, a + (b - a) * i / n, a + (b - a) * (i + 1) / n + 0.6, u0, u1, c + (alpha,))
    def _make_static(self):
        L, n = self.L, self.len
        back = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(back)
        blk = (0, 0, 0, 255)
        self._band(d, self.g[0] - L, self.outer, -L, n + L, blk)
        emp = GAUGE_EMPTY + (255,)
        self._band(d, *self.g, 0.0, n, emp)
        self._band(d, self.b[0], self.o[1], 0.0, n, emp)
        self._band(d, *self.c, 0.0, n, emp)
        cx, cy = self.HALF * self.k, (self.map_cy - self.Y0) * self.k
        r = GAUGE_MAP_R * self.k
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=blk)
        r -= L
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GAUGE_DISC + (190,))
        front = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
        f = ImageDraw.Draw(front)
        u = n * GAUGE_FIRST_Q
        self._band(f, self.g[0] - L * 0.5, self.g[1] + L * 0.5, u - L * 0.5, u + L * 0.5, blk)
        for j in range(1, GAUGE_BOOM_SECTIONS):
            u = n * j / GAUGE_BOOM_SECTIONS
            self._band(f, self.o[0] - L * 0.5, self.o[1] + L * 0.5, u - L * 0.5, u + L * 0.5, blk)
        self._band(f, self.o[0] - L * 0.25, self.o[0] + L * 0.25, 0.0, n, blk)
        for j in range(1, GAUGE_CRUISE_TIERS):
            u = n * j / GAUGE_CRUISE_TIERS
            self._band(f, self.c[0] - L * 0.5, self.c[1] + L * 0.5, u - L * 0.5, u + L * 0.5, blk)
        self.static = (back.reduce(self.SS), front.reduce(self.SS))
    def place(self, gx, gy, gh, sc, gw=None):
        gw = gw if gw is not None else gh * 16.0 / 9.0
        return gx + int(round(gw / 2.0 - self.HALF * sc)), gy + int(round(self.Y0 * sc))
    def _map(self, alpha, rows, now):
        if self.mapc is None:
            self.mapc = SphereMap(self.r_map - 1.0, mark=1.25)
        if self.map_img is None or now - self.map_t >= 1.0 / 15:
            self.map_t = now
            self.map_img = self.mapc.draw(1.0, rows, now)
        im = self.map_img
        w, h = im.size
        cxf, cyf = self.HALF * self.s, (self.map_cy - self.Y0) * self.s
        layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
        layer.paste(im, (int(round(cxf - w * 0.5)), int(round(cyf - h * 0.5))))
        mask = Image.new("L", self.size, 0)
        r = self.r_map - 1
        ImageDraw.Draw(mask).ellipse([cxf - r, cyf - r, cxf + r, cyf + r], fill=255)
        a = np.asarray(layer).copy()
        a[..., 3] = (a[..., 3].astype(np.uint16) * np.asarray(mask) // 255).astype(np.uint8)
        return Image.fromarray(a, "RGBA")
    def _focus_masks(self, focus):
        if not hasattr(self, "_fmasks"):
            self._fmasks = {}
        if focus in self._fmasks:
            return self._fmasks[focus]
        n, L = self.len, self.L
        stack = self._poly(self.g[0] - L, self.outer, -L, n + L)
        on, dim, edge = (Image.new("L", (self.W2, self.H2), 0) for _ in range(3))
        do, dd, de = ImageDraw.Draw(on), ImageDraw.Draw(dim), ImageDraw.Draw(edge)
        span = {"throttle": self.g, "burner": self.b, "sonic": self.o, "cruise": self.c,
                "all": (self.g[0], self.c[1])}.get(focus)
        lw = max(2, int(round(2.5 * self.k)))
        if focus == "map":
            cx, cy, r = self.HALF * self.k, (self.map_cy - self.Y0) * self.k, GAUGE_MAP_R * self.k
            for m_ in (do, de):
                m_.ellipse([cx - r - lw, cy - r - lw, cx + r + lw, cy + r + lw], outline=255, width=2 * lw)
            dd.polygon(stack, fill=255)
        elif span is not None:
            part = self._poly(span[0] - L * 0.5, span[1] + L * 0.5, -L * 0.5, n + L * 0.5)
            do.polygon(part, fill=255)
            de.line(part + [part[0]], fill=255, width=lw, joint="curve")
            if focus != "all":
                dd.polygon(stack, fill=255)
                dd.polygon(part, fill=0)
        on, dim, edge = on.reduce(self.SS), dim.reduce(self.SS), edge.reduce(self.SS)
        halo = on.filter(ImageFilter.GaussianBlur(max(2.0, 7.0 * self.s)))
        self._fmasks[focus] = (on, dim, halo, edge)
        return self._fmasks[focus]
    def _focus(self, img, focus, pulse):
        on, dim, halo, edge = self._focus_masks(focus)
        if dim.getbbox():
            shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
            shade.putalpha(dim.point(lambda v: v * 150 // 255))
            img = Image.alpha_composite(img, shade)
        lvl = 0.2 + 0.8 * min(1.0, max(0.0, pulse))
        glow = Image.new("RGBA", img.size, (255, 255, 255, 0))
        glow.putalpha(halo.point(lambda v: int(v * 0.95 * lvl)))
        img = Image.alpha_composite(glow, img)
        lift = Image.new("RGBA", img.size, (255, 255, 255, 0))
        lift.putalpha(ImageChops.lighter(on.point(lambda v: int(v * 0.28 * lvl)),
                                         edge.point(lambda v: int(v * (0.35 + 0.65 * lvl)))))
        return Image.alpha_composite(img, lift)
    def draw(self, alpha, st, now, rows=(), focus=None, pulse=0.0):
        if self.static is None:
            self._make_static()
        n = self.len
        fills = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(fills)
        flags = st["flags"]
        thr = SpeedReadout._num(st.get("throttle", 0.0))
        thr = max(-1.0, min(1.0, thr))
        if thr < 0.0:
            self._grad(d, *self.g, 0.0, n, GAUGE_COLS["reverse"], 255, gain=0.92 + 0.08 * math.sin(now * 10.0))
        else:
            q = GAUGE_FIRST_Q
            self._grad(d, *self.g, 0.0, n * min(thr, q), GAUGE_COLS["first"], 255)
            self._grad(d, *self.g, n * q, n * thr, GAUGE_COLS["throttle"], 255)
        locked, burning = flags & F_LOCKED, flags & F_BURNING
        gain = (0.55 + 0.35 * math.sin(now * 6.0)) if locked else (1.12 if burning else 1.0)
        self._grad(d, *self.b, 0.0, n * min(1.0, max(0.0, st["fuel"])), GAUGE_COLS["burner"], 255, gain=gain)
        meter, build, sonic = min(1.0, max(0.0, st["charge"])), SpeedReadout._num(st.get("build", -1.0), -1.0), st["sonic"]
        cols = GAUGE_COLS["sonic"]
        if flags & F_SONIC_GATED:
            gain, keep = GAUGE_GATED
            cols = tuple(tuple(int(sum(c) / 3 + (x - sum(c) / 3) * keep) for x in c) for c in cols)
        elif flags & F_SONIC_LOW:
            gain = 0.6
        elif meter >= 1.0 and build < 0:
            gain = 0.9 + 0.12 * math.sin(now * 3.0)
        else:
            gain = 1.0 + 0.25 * min(1.0, sonic)
        lit, hot = meter, None
        if build >= 0.0:
            N = GAUGE_BOOM_SECTIONS
            tot = min(1.0, meter + build)
            k_ = min(max(1, math.ceil(build * N - 1e-6)), int(tot * N + 1e-6))
            if k_ >= 1:
                lit, hot = max(0.0, tot - k_ / N), (max(0.0, tot - k_ / N), tot)
            else:
                lit = tot
        self._grad(d, *self.o, 0.0, n * lit, cols, 255, inward=True, gain=gain)
        if hot:
            g_ = 0.97 + 0.08 * math.sin(now * 18.0)
            self._grad(d, *self.o, n * hot[0], n * hot[1], ((255, 214, 96), (255, 252, 236)), 255, inward=True, gain=g_)
        if flags & F_SONIC_REFUSED:
            if self.refused_t is None or now < self.refused_t:
                self.refused_t = now
            w = 0.5 + 0.5 * math.cos(2.0 * math.pi * GAUGE_REFUSED_HZ * (now - self.refused_t))
            lo, hi = GAUGE_COLS["refused"], GAUGE_COLS["refused_hi"]
            fl = tuple(tuple(int(a + (b - a) * w * w) for a, b in zip(lo[j], hi[j])) for j in (0, 1))
            self._grad(d, *self.o, 0.0, n, fl, 255, inward=True)
        else:
            self.refused_t = None
        lvl = min(1.0, max(0.0, st.get("cruise", 0.0)))
        gain = (1.0 + 0.18 * math.sin(now * 14.0)) if flags & F_CRUISE else 1.0
        self._grad(d, *self.c, 0.0, n * lvl, GAUGE_COLS["cruise"], 255, gain=gain)
        img = Image.alpha_composite(self.static[0], fills.reduce(self.SS))
        img = Image.alpha_composite(img, self.static[1])
        if rows is not None:
            img = Image.alpha_composite(img, self._map(alpha, rows, now))
        if self.speed:
            lay = self._speed_layer(self.speedo.step(st, now))
            if lay is not None:
                img.alpha_composite(lay[0], (max(0, lay[1]), max(0, lay[2])))
        if focus:
            img = self._focus(img, focus, pulse)
        if alpha < 0.999:
            a = np.asarray(img).copy()
            a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
            img = Image.fromarray(a, "RGBA")
        return img
    def _speed_layer(self, text):
        if not text:
            return None
        if self.sp_img is not None and self.sp_img[0] == text:
            return self.sp_img[1]
        s = self.s
        if self.sp_fonts is None:
            self.sp_fonts = tuple(font(max(6, int(round(px * s))), style) for px, style in
                                  zip(SPEED_PX, ("SemiBold Condensed", "SemiLight Condensed", "SemiBold Condensed")))
        fn, fu, fw = self.sp_fonts
        if text.endswith(" U/S"):
            runs, sep = [(text[:-4], fn, WHITE, 0.0, 255), ("U/S", fu, WHITE, 1.5 * s, 210)], 6.0 * s
        else:
            runs, sep = [(text, fw, SPEED_WORD_COLS.get(text, WHITE), 2.5 * s, 255)], 0.0
        m = ImageDraw.Draw(Image.new("L", (1, 1)))
        widths = [sum(m.textlength(ch, font=f_) for ch in t_) + gap * (len(t_) - 1) for t_, f_, _c, gap, _a in runs]
        tw = sum(widths) + sep * (len(runs) - 1)
        asc = max(r[1].getmetrics()[0] for r in runs)
        desc = max(r[1].getmetrics()[1] for r in runs)
        pad = int(math.ceil(6 * s)) + 2
        w, h = int(math.ceil(tw)) + 2 * pad, asc + desc + 2 * pad
        base = pad + asc
        mask = Image.new("L", (w, h), 0)
        txt = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dm, dt_ = ImageDraw.Draw(mask), ImageDraw.Draw(txt)
        sw = max(1, int(round(1.5 * s)))
        x = float(pad)
        for t_, f_, col, gap, a in runs:
            for ch in t_:
                dm.text((x, base), ch, font=f_, fill=255, anchor="ls", stroke_width=sw, stroke_fill=255)
                dt_.text((x, base), ch, font=f_, fill=col + (a,), anchor="ls")
                x += m.textlength(ch, font=f_) + gap
            x += sep - gap
        halo = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(1.0, 2.0 * s))), np.uint16)
        back = np.zeros((h, w, 4), np.uint8)
        back[..., 3] = np.minimum(255, halo * 150 // 255 + np.asarray(mask, np.uint16) * 60 // 255)
        out = Image.alpha_composite(Image.fromarray(back, "RGBA"), txt)
        ax, ay = self.sp_at
        res = (out, int(round(ax - pad - tw / 2.0)), int(round(ay - base)))
        self.sp_img = (text, res)
        return res
def _runs(text, f_text, f_key, col, gap=0.0):
    out, i = [], 0
    while i < len(text):
        j = text.find("[", i)
        k = text.find("]", j) if j >= 0 else -1
        if j < 0 or k < 0:
            out.append(("text", text[i:], f_text, col, gap))
            break
        if j > i:
            out.append(("text", text[i:j], f_text, col, gap))
        out.append(("key", text[j + 1:k], f_key, col, 0.0))
        i = k + 1
    return out
def caption(lines, scale, halo=150):
    s = scale
    m = ImageDraw.Draw(Image.new("L", (1, 1)))
    pad_k, gap_l, mar_k = 6.0 * s, 7.0 * s, 3.0 * s
    def run_w(r):
        kind, t, f_, _c, gap = r
        if kind == "key":
            return m.textlength(t, font=f_) + 2 * pad_k + 2 * mar_k
        return sum(m.textlength(ch, font=f_) for ch in t) + gap * max(0, len(t) - 1)
    sizes = []
    for runs in lines:
        asc = max((r[2].getmetrics()[0] for r in runs), default=0)
        desc = max((r[2].getmetrics()[1] for r in runs), default=0)
        sizes.append((sum(run_w(r) for r in runs), asc, desc))
    pad = int(math.ceil(8 * s)) + 2
    w = int(math.ceil(max((x[0] for x in sizes), default=1))) + 2 * pad
    h = int(math.ceil(sum(a + d for _w, a, d in sizes) + gap_l * max(0, len(lines) - 1))) + 2 * pad
    mask, txt = Image.new("L", (w, h), 0), Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dm, dt_ = ImageDraw.Draw(mask), ImageDraw.Draw(txt)
    sw, words, y = max(1, int(round(1.5 * s))), [], float(pad)
    for runs, (lw, asc, desc) in zip(lines, sizes):
        x, base = (w - lw) / 2.0, y + asc
        for kind, t, f_, col, gap in runs:
            if kind == "key":
                x += mar_k
                kw = m.textlength(t, font=f_) + 2 * pad_k
                kb = f_.getbbox(t)
                ka = (col[3] if len(col) > 3 else 255) / 255.0
                top, bot = base - asc * 0.86, base + desc * 0.55
                dm.rectangle([x - 2, top - 2, x + kw + 2, bot + 2], fill=int(255 * ka))
                dt_.rectangle([x, top, x + kw, bot], fill=WHITE + (int(36 * ka),), outline=WHITE + (int(225 * ka),),
                              width=max(1, int(round(1.5 * s))))
                dt_.text((x + pad_k, (top + bot) / 2.0 - (kb[1] + kb[3]) / 2.0), t, font=f_,
                         fill=WHITE + (int(255 * ka),))
                x += kw + mar_k
            else:
                for ch in t:
                    dm.text((x, base), ch, font=f_, fill=255, anchor="ls", stroke_width=sw, stroke_fill=255)
                    dt_.text((x, base), ch, font=f_, fill=tuple(col[:3]) + ((col[3] if len(col) > 3 else 255),),
                             anchor="ls")
                    x += m.textlength(ch, font=f_) + gap
            words.append(t)
        y += asc + desc + gap_l
    soft = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(1.0, 3.0 * s))), np.uint16)
    back = np.zeros((h, w, 4), np.uint8)
    back[..., 3] = np.minimum(255, soft * halo // 255 + np.asarray(mask, np.uint16) * 50 // 255)
    return Image.alpha_composite(Image.fromarray(back, "RGBA"), txt), words
class BootArc(Gauge):
    def __init__(self, scale, aspect=16.0 / 9.0, hint=""):
        super().__init__(scale, aspect)
        self.hint = hint
        self.texts = []
        self.boot_static = None
        self.cap = (None, None)
        s = scale
        self.f_head = font(max(6, int(round(20 * s))), "SemiBold Condensed")
        self.f_sub = font(max(6, int(round(15 * s))), "Light Condensed")
        self.f_key = font(max(6, int(round(13 * s))), "SemiBold Condensed")
    def _make_boot_static(self):
        L, n = self.L, self.len
        img = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        self._band(d, self.g[0] - L, self.outer, -L, n + L, (0, 0, 0, 255))
        self._band(d, self.g[0], self.c[1], 0.0, n, GAUGE_EMPTY + (255,))
        self.boot_static = img.reduce(self.SS)
    def _caption(self, stage, prog, since, now):
        online = stage == 3
        title = "SUIT ONLINE" if online else "SUIT STARTUP"
        head = [("text", title, self.f_head, WHITE + (255,), 2.5 * self.s)]
        if not online:
            head.append(("text", f"   {int(round(prog * 100)):d}%", self.f_head, WHITE + (180,), 0.0))
        if online:
            msg, a = "FLIGHT SYSTEMS READY   //   DOUBLE-TAP SPACE TO FLY", 220
        elif stage == 2:
            msg, a = "SYNCING TO YOU   //   TAKE A FEW STEPS", int(150 + 90 * (0.5 + 0.5 * math.sin(now * 3.0)))
        else:
            msg, a = "LOCATING YOUR SUIT" + "." * (int(now * 3) % 4), 190
        lines = [head, [("text", msg, self.f_sub, WHITE + (a,), 1.2 * self.s)]]
        ha = 0.0
        if online and self.hint:
            ha = min(1.0, max(0.0, (since - HINT_IN[0]) / HINT_IN[1]))
            if ha > 0.0:
                lines.append(_runs(f"[{self.hint.upper()}]  SUIT CONTROL", self.f_sub, self.f_key,
                                   WHITE + (int(235 * ha),), 1.2 * self.s))
        key = (tuple(tuple(r[:2]) + (r[3],) for ln in lines for r in ln),)
        if self.cap[0] != key:
            self.cap = (key, caption(lines, self.s))
        return self.cap[1]
    def draw(self, alpha, stage, prog, since, now):
        if self.boot_static is None:
            self._make_boot_static()
        online = stage == 3
        ot = max(0.0, since) if online else None
        p = 1.0 if online else min(1.0, max(0.0, prog))
        col, gain = boot_colour(p, ot), boot_gain(ot)
        n = self.len
        a0, a1 = self.g[0], self.c[1]
        fills = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(fills)
        edge, mid = tuple(int(x * 0.74) for x in col), _mix(col, (255, 255, 255), 0.2)
        u1 = n * p
        self._grad(d, a0, a1, 0.0, u1, (edge, mid), 255, gain=gain)
        if not online and u1 > 0.0:
            shine = Image.new("RGBA", (self.W2, self.H2), (0, 0, 0, 0))
            ds = ImageDraw.Draw(shine)
            sweep = ((now * 0.75) % 1.5 - 0.25) * u1
            for i in range(8):
                half = n * 0.045 * (1.0 - i / 8.0)
                lo, hi = max(0.0, sweep - half), min(u1, sweep + half)
                if hi > lo:
                    ds.polygon(self._poly(a0, a1, lo, hi), fill=(255, 255, 255, 14))
            tip = min(u1, n * 0.012 + 2.0 * self.k)
            ds.polygon(self._poly(a0, a1, u1 - tip, u1), fill=(255, 255, 255, int(150 + 60 * math.sin(now * 9.0))))
            fills = Image.alpha_composite(fills, shine)
        bar = fills.reduce(self.SS)
        halo = bar.getchannel("A").filter(ImageFilter.GaussianBlur(max(2.0, 7.0 * self.s)))
        glow = Image.new("RGBA", bar.size, col + (0,))
        glow.putalpha(halo.point(lambda v: int(v * 0.6 * min(1.0, gain))))
        img = Image.alpha_composite(glow, self.boot_static)
        img = Image.alpha_composite(img, bar)
        cap, words = self._caption(stage, prog, since, now)
        ax, ay = self.sp_at
        img.alpha_composite(cap, (max(0, int(round(ax - cap.width / 2.0))),
                                  max(0, int(round(ay - SPEED_PX[0] * 0.8 * self.s)))))
        self.texts = words
        if alpha < 0.999:
            a = np.asarray(img).copy()
            a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
            img = Image.fromarray(a, "RGBA")
        return img
TUT_FLAG = "tutorial.flag"
TUT_DELAY = 0.8
TUT_FADE = 0.35
TUT_PULSE_HZ = 1.4
TUT_GAP = 10.0
TUT_STEPS = (
    ("all", 5.0, "YOUR SUIT'S GAUGES", ("These bars around your compass are the suit's systems.",
                                         "Here is what each one does.")),
    ("throttle", 6.5, "THROTTLE", ("[{forward}] opens it, [{back}] closes it. It stays where you leave it.",
                                   "Double-tap [{back}] to brake hard.")),
    ("burner", 6.0, "AFTERBURNER", ("{afterburner_line}", "It recharges by itself.")),
    ("sonic", 6.5, "SONIC BOOM", ("Press [CAPS LOCK] for a blast once the throttle is past its first quarter.",
                                  "Each blast uses one section.")),
    ("cruise", 6.5, "INTERPLANETARY CRUISE", ("In space, hold [CAPS LOCK] to climb through three speed tiers.",
                                             "[{back}] brings it back down.")),
    ("map", 5.5, "SPEED AND SPACE MAP", ("Your speed, and the planets, stations and ships around you.",)),
    ("key", 7.0, "SUIT CONTROL", ("Press [{panel}] any time for settings, sounds and keys.",
                                  "Double-tap [SPACE] to fly.")),
)
TUT_PAD = {"throttle": "Controller: the left stick.", "burner": "Controller: flick the left stick up twice.",
           "sonic": "Controller: click the right stick.",
           "cruise": "Controller: hold the right stick click; the left stick back lowers it.",
           "key": "Controller: double-tap A to fly."}
TUT_COLS = {"throttle": GAUGE_COLS["throttle"][1], "burner": GAUGE_COLS["burner"][1], "sonic": GAUGE_COLS["sonic"][0],
            "cruise": GAUGE_COLS["cruise"][1]}
def _tut_flag():
    from pathlib import Path
    return Path(__file__).resolve().parent / TUT_FLAG
def tutorial_seen():
    try:
        return _tut_flag().exists()
    except Exception:
        return True
def tutorial_mark_seen():
    try:
        _tut_flag().write_text("seen\n", encoding="utf-8")
    except Exception:
        pass
def tutorial_keys(path=None):
    out = dict(forward="W", back="S", afterburner="SHIFT", panel="F7", afterburner_mode="toggle")
    try:
        import settings
        S = settings.load(path, quiet=True)
        for k in ("forward", "back", "afterburner", "panel"):
            vk = S.keys.get(k)
            if vk:
                out[k] = settings.key_name(vk).upper()
        out["afterburner_mode"] = str(S.flight.get("afterburner_mode", "toggle"))
    except Exception:
        pass
    return out
def pad_connected():
    try:
        import xpad
        return bool(xpad.slots())
    except Exception:
        return False
class Tutorial:
    def __init__(self, t0, keys=None, pad=False):
        self.t0, self.pad = t0, pad
        self.keys = dict(forward="W", back="S", afterburner="SHIFT", panel="F7", afterburner_mode="toggle")
        self.keys.update(keys or {})
        self.ends, t = [], 0.0
        for step in TUT_STEPS:
            t += step[1]
            self.ends.append(t)
        self.total = t
    def at(self, now):
        t = now - self.t0
        if not 0.0 <= t < self.total:
            return None
        i = next(j for j, e in enumerate(self.ends) if t < e)
        ti = t - (self.ends[i - 1] if i else 0.0)
        return i, ti, max(0.0, min(1.0, ti / TUT_FADE, (TUT_STEPS[i][1] - ti) / TUT_FADE))
    def done(self, now):
        return now - self.t0 >= self.total
    def lines(self, i):
        band, _secs, title, lines = TUT_STEPS[i]
        k = dict(self.keys)
        k["afterburner_line"] = ("Hold [{afterburner}] for a burst of speed." if k["afterburner_mode"] == "hold" else
                                 "Press [{afterburner}] to fire the afterburner, and again to stop.").format(**k)
        out = [ln.format(**k) for ln in lines]
        if self.pad and band in TUT_PAD:
            out.append(TUT_PAD[band])
        return title, out
    @staticmethod
    def pulse(ti):
        return 0.5 + 0.5 * math.cos(2.0 * math.pi * TUT_PULSE_HZ * ti)
    @staticmethod
    def demo(st, i, ti):
        band, d = TUT_STEPS[i][0], dict(st)
        if band == "all":
            d.update(throttle=0.6, fuel=1.0, charge=1.0, cruise=2.0 / 3.0)
        elif band == "throttle":
            d["throttle"] = 0.5 - 0.5 * math.cos(2.0 * math.pi * ti / 3.2)
        elif band == "burner":
            d["fuel"] = 0.3 + 0.7 * (0.5 + 0.5 * math.cos(2.0 * math.pi * ti / 3.0))
        elif band == "sonic":
            d["charge"] = (int(ti / 0.8) % 4) / 3.0
            d["flags"] = d.get("flags", 0) & ~(F_SONIC_GATED | F_SONIC_LOW | F_SONIC_REFUSED)
        elif band == "cruise":
            d["cruise"] = (int(ti / 1.1) % 4) / 3.0
        return d
class TutorialCard:
    def __init__(self, scale):
        s = self.s = scale
        self.f_title = font(max(6, int(round(22 * s))), "SemiBold Condensed")
        self.f_text = font(max(6, int(round(17 * s))), "SemiLight Condensed")
        self.f_pad = font(max(6, int(round(15 * s))), "Light Condensed")
        self.f_key = font(max(6, int(round(14 * s))), "SemiBold Condensed")
        self.cache = (None, None)
        self.texts = []
    def draw(self, title, lines, colour, i, n, alpha):
        key = (title, tuple(lines), colour, i, n)
        if self.cache[0] != key:
            s = self.s
            rows = [[("text", title, self.f_title, tuple(colour) + (255,), 2.5 * s)]]
            for ln in lines:
                pad_line = ln.startswith("Controller:")
                rows.append(_runs(ln, self.f_pad if pad_line else self.f_text, self.f_key,
                                  WHITE + ((175,) if pad_line else (240,))))
            body, words = caption(rows, s, halo=0)
            pad_x, pad_y, dots_h = int(22 * s), int(14 * s), int(18 * s)
            w, h = body.width + 2 * pad_x, body.height + 2 * pad_y + dots_h
            plate = np.zeros((h, w, 4), np.uint8)
            plate[..., :3] = PLATE
            fade_x = np.clip(np.minimum(np.arange(w), w - 1 - np.arange(w)) / max(1.0, 36.0 * s), 0.0, 1.0)
            plate[..., 3] = (fade_x * 178).astype(np.uint8)[None, :]
            img = Image.fromarray(plate, "RGBA")
            d = ImageDraw.Draw(img)
            lw = max(1, int(round(2.5 * s)))
            d.rectangle([int(w * 0.12), 0, int(w * 0.88), lw], fill=tuple(colour) + (235,))
            img.alpha_composite(body, (pad_x, pad_y))
            r, gap = 3.2 * s, 13.0 * s
            x0, y = w / 2.0 - gap * (n - 1) / 2.0, h - pad_y * 0.5 - dots_h * 0.5
            for j in range(n):
                cx = x0 + j * gap
                fill = tuple(colour) + (255,) if j == i else WHITE + (70,)
                d.ellipse([cx - r, y - r, cx + r, y + r], fill=fill)
            self.cache, self.texts = (key, img), words
        img = self.cache[1]
        if alpha < 0.999:
            a = np.asarray(img).copy()
            a[..., 3] = (a[..., 3] * max(0.0, alpha)).astype(np.uint8)
            img = Image.fromarray(a, "RGBA")
        return img
class Director:
    def __init__(self, cfg=None):
        self.cfg = dict(DEFAULT_CONFIG, **(cfg or {}))
        self.alpha = 0.0
        self.fx_a = 1.0
        self.boot_a, self.boot_p = 0.0, 0.0
        self.shock_t, self.shock_k, self.sonic_was, self.shock_seen = -99.0, 1.0, False, None
        self.waves = []
        self.ask_t = -99.0
        self.edge_wave = None
        self.brake_t, self.brake_was = -99.0, False
        self.tutorial = False
    def boot_done(self, st, fresh):
        hold = BOOT_HOLD + (HINT_HOLD if self.cfg.get("panel_key") else 0.0)
        return fresh and st["stage"] == 3 and st["since"] > hold + TUT_DELAY
    def _start(self, now, k):
        w = [now, k]
        run = [x for x in self.waves if 0.0 <= now - x[0] < shock_time(x[1])]
        self.waves = run[max(0, len(run) - (SHOCK_WAVES - 1)):] + [w]
        self.shock_t, self.shock_k = now, k
        return w
    def step(self, st, fresh, now, dt):
        flags = st["flags"] if fresh else 0
        want = 1.0 if (flags & F_FLYING or self.tutorial) and self.cfg["style"] != "off" else 0.0
        self.alpha = _toward(self.alpha, want, dt, FADE)
        waves = self.cfg["shock_waves"]
        shn = st.get("shock_n")
        asked = fresh and shn is not None and self.shock_seen is not None and shn != self.shock_seen
        if fresh and shn is not None:
            self.shock_seen = shn
        if asked and waves:
            k = shock_size(st.get("shock_k", 1.0))
            w = self.edge_wave
            if w is not None and 0.0 <= now - w[0] <= SHOCK_PAIR and any(x is w for x in self.waves):
                w[1] = k
                if w is self.waves[-1]:
                    self.shock_k = k
            else:
                self._start(now, k)
            self.edge_wave, self.ask_t = None, now
        sonic_now = bool(flags & F_SONIC)
        if (sonic_now and not self.sonic_was and waves and not flags & F_CRUISE
                and not 0.0 <= now - self.ask_t <= SHOCK_PAIR):
            self.edge_wave = self._start(now, min(1.0, max(0.1, SpeedReadout._num(st.get("sonic", 1.0), 1.0))))
        self.sonic_was = sonic_now
        brake_now = bool(flags & F_BRAKE)
        if brake_now and not self.brake_was and waves:
            self.brake_t = now
        self.brake_was = brake_now
        hold = BOOT_HOLD + (HINT_HOLD if self.cfg.get("panel_key") else 0.0)
        bwant = 1.0 if (fresh and st["stage"] in (1, 2, 3) and not flags & F_FLYING
                        and not (st["stage"] == 3 and st["since"] > hold)) else 0.0
        self.boot_a = _toward(self.boot_a, bwant, dt, FADE)
        if st["prog"] < self.boot_p - 0.2:
            self.boot_p = st["prog"]
        else:
            self.boot_p += (st["prog"] - self.boot_p) * (1 - math.exp(-dt / 0.15))
    def waves_at(self, now):
        return [(now - t0, k) for t0, k in self.waves if 0.0 <= now - t0 < shock_time(k)]
    def shocks(self, now):
        run = self.waves_at(now)
        ts = min(t for t, _k in run) if run else None
        tb = now - self.brake_t if now - self.brake_t < BRAKE_SHOCK_TIME + BRAKE_GAP else None
        return ts, tb
DEMO_BLASTS = ((11.0, 0.85), (11.6, 1.3), (12.2, 1.9), (29.5, 1.0), (33.0, 1.7), (36.0, 2.6))
def _demo_state(now):
    ph_ = now % 60
    n0 = len(DEMO_BLASTS) * int(now // 60)
    st = dict(idle_state(), flags=0, fuel=abs(math.sin(now / 4)), shock_n=n0)
    if ph_ < 11.0:
        st.update(stage=1 if ph_ < 4 else 2 if ph_ < 7 else 3,
                  prog=min(0.8, ph_ / 5) if ph_ < 4 else 0.8 + 0.1 * (ph_ - 4) / 3 if ph_ < 7 else 1.0,
                  since=max(0.0, ph_ - 7))
    else:
        fl = ph_ - 11.0
        st.update(stage=3, prog=1.0, since=fl + 4.0)
        flags = F_FLYING | (F_LOCKED if 18 < fl < 24 else 0)
        jit = 0.25 * (math.sin(now * 13.0) + math.sin(now * 7.3))
        if fl < 4.0:
            thr, spd = 0.0, abs(jit)
        elif fl < 10.0:
            thr = 0.25 * min(1.0, (fl - 4.0) / 3.0) if fl < 8.0 else 0.25 + 0.35 * (fl - 8.0) / 2.0
            spd = 300.0 * thr ** 1.2 + jit
        elif fl < 18.0:
            thr = 0.6
            spd = 300.0 * 0.6 ** 1.2 + sum(k_ * 60.0 * math.exp(-max(0.0, fl - t_) / 3.0)
                                           for t_, k_ in DEMO_BLASTS[:3] if fl >= t_)
        elif fl < 22.0:
            thr, spd = 0.0, max(0.0, 300.0 * 0.6 ** 1.2 * (1.0 - (fl - 18.0) / 3.0)) + abs(jit) * 0.5
        elif fl < 25.0:
            thr, spd = -1.0, 14.0 + jit
        elif fl < 27.0 or fl >= 45.0:
            thr, spd = 0.0, abs(jit)
        else:
            flags |= F_CRUISE | F_SONIC
            c_ = fl - 27.0
            thr = 1.0
            st["cruise"] = min(1.0, c_ / 9.0)
            spd = 1000.0 + 200532.0 * min(1.0, (c_ / 12.0) ** 2)
        if fl < 10.0 or 18.0 <= fl < 27.0:
            flags |= F_SONIC_GATED if (thr <= 0.25) else 0
        n_ = sum(1 for t_, _k in DEMO_BLASTS if fl >= t_)
        used = min(3, sum(1 for t_, _k in DEMO_BLASTS[:3] if fl >= t_))
        meter = 1.0 - used / 3.0 + (max(0.0, fl - 17.0) / 16.0 if fl > 17.0 else 0.0)
        if 2.0 <= fl < 2.5 or 16.0 <= fl < 16.5:
            flags |= F_SONIC_REFUSED
        last = max((t_ for t_, _k in DEMO_BLASTS[:3] if fl >= t_), default=None)
        sonic = max(0.0, 1.0 - (fl - last) / 2.0) if last is not None and fl < 18.0 else 0.0
        if sonic > 0.0:
            flags |= F_SONIC
        st.update(flags=flags | (F_SONIC_LOW if meter < 1.0 / 3.0 and not flags & F_CRUISE else 0),
                  throttle=thr, speed=max(0.0, spd), charge=min(1.0, meter), sonic=sonic,
                  shock_n=n0 + n_, shock_k=DEMO_BLASTS[n_ - 1][1] if n_ else 1.0)
    return st
def _dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            u32.SetProcessDPIAware()
        except Exception:
            pass
def main():
    _dpi_aware()
    parent = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    demo = len(sys.argv) > 2 and sys.argv[2] == "demo"
    cfg = read_config()
    apply_config(cfg)
    cfg_mt, cfg_check = ini_mtime(), time.perf_counter()
    shm = mmap.mmap(-1, HUD_SIZE, HUD_NAME)
    wfx = mmap.mmap(-1, 64, WARPFX_NAME)
    ov = Overlay()
    ov_boot = Overlay()
    ov_tut = Overlay()
    try:
        map_shm = mmap.mmap(-1, 16 + 16 * MAP_MAX, MAP_NAME)
    except Exception:
        map_shm = None
    boot, boot_h = None, 0
    tut, tut_card, tut_seen = None, None, tutorial_seen()
    shock = Shock(k32.GetModuleHandleW(None))
    panel, panel_h = None, 0
    logic = Director(cfg)
    last = time.perf_counter()
    PROCESS_QUERY_LIMITED = 0x1000
    ph = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, parent) if parent else None
    while True:
        now = time.perf_counter()
        dt, last = min(0.1, now - last), now
        if ph:
            code = wt.DWORD()
            if not k32.GetExitCodeProcess(ph, ctypes.byref(code)) or code.value != 259:
                break
        if now - cfg_check > 1.0:
            cfg_check = now
            mt = ini_mtime()
            if mt != cfg_mt:
                cfg_mt, cfg = mt, read_config()
                apply_config(cfg)
                logic.cfg = dict(DEFAULT_CONFIG, **cfg)
                panel = boot = tut_card = None
        if demo:
            st = _demo_state(now)
            fresh = True
        else:
            t, st = unpack_hud(shm)
            merge_warpfx(st, wfx, now)
            fresh = now - t < 1.0
        if tut is None and not tut_seen and not demo and logic.cfg["style"] != "off" and logic.boot_done(st, fresh):
            tut = Tutorial(now, tutorial_keys(), pad=pad_connected())
        if tut is not None and tut.done(now):
            tutorial_mark_seen()
            tut, tut_seen = None, True
        logic.tutorial = tut is not None
        logic.step(st, fresh, now, dt)
        alpha = logic.alpha
        rect = game_rect()
        ov.pump()
        rows = []
        if MAP_ENABLED and map_shm is not None and alpha > 0.01 and rect is not None:
            try:
                mt, mn = struct.unpack_from("<dI", map_shm, 0)
                if now - mt < 1.0:
                    rows = [struct.unpack_from("<I3f", map_shm, 16 + 16 * i) for i in range(min(mn, MAP_MAX))]
            except Exception:
                rows = []
        if rect is None or logic.boot_a <= 0.01:
            ov_boot.hide()
        else:
            gx, gy, gw, gh = rect
            sc_g = max(0.3, gh / 1440.0)
            if boot is None or boot_h != (gw, gh):
                boot, boot_h = BootArc(sc_g, gw / max(1, gh), logic.cfg.get("panel_key", "")), (gw, gh)
            ov_boot.show(boot.draw(logic.boot_a, st["stage"], logic.boot_p, st["since"], now),
                         *boot.place(gx, gy, gh, sc_g, gw))
        ts, tb = logic.shocks(now)
        shocking = rect is not None and (ts is not None or tb is not None) and logic.fx_a > 0.01
        if shocking:
            shock.frame(ts, rect, 1.0 if st["flags"] & F_RIGHT else -1.0, tb, logic.shock_k, logic.fx_a,
                        logic.waves_at(now))
        else:
            shock.hide()
        ta = tut.at(now) if tut is not None else None
        if rect is None or alpha <= 0.01:
            ov.hide()
            ov_tut.hide()
        elif not shocking or int(now * 60) % 2 == 0:
            gx, gy, gw, gh = rect
            sc_g = max(0.3, gh / 1440.0)
            if not isinstance(panel, Gauge) or panel_h != (gw, gh):
                panel, panel_h = Gauge(sc_g, aspect=gw / max(1, gh)), (gw, gh)
                panel.speed = True
                tut_card = None
            if ta is not None:
                i_, ti_, fade_ = ta
                band_ = TUT_STEPS[i_][0]
                st_ = st if st["flags"] & F_FLYING else Tutorial.demo(st, i_, ti_)
                im_ = panel.draw(alpha, st_, now, rows if MAP_ENABLED else None,
                                 focus=None if band_ == "key" else band_, pulse=Tutorial.pulse(ti_))
            else:
                im_ = panel.draw(alpha, st, now, rows if MAP_ENABLED else None)
            px_, py_ = panel.place(gx, gy, gh, sc_g, gw)
            ov.show(im_, px_, py_)
            if ta is not None:
                if tut_card is None:
                    tut_card = TutorialCard(sc_g)
                title_, lines_ = tut.lines(i_)
                card_ = tut_card.draw(title_, lines_, TUT_COLS.get(band_, WHITE), i_, len(TUT_STEPS),
                                      fade_ * alpha)
                ov_tut.show(card_, gx + int(round(gw / 2.0 - card_.width / 2.0)),
                            py_ + im_.height + int(round(TUT_GAP * sc_g)))
            else:
                ov_tut.hide()
        time.sleep(max(0.0, (1.0 / 60 if shocking else 1.0 / FPS) - (time.perf_counter() - now)))
if __name__ == "__main__":
    main()
