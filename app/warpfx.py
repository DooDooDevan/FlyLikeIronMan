import ctypes
import ctypes.wintypes as wt
import math
import mmap
import os
import random
import struct
import sys
import threading
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
WARPFX_NAME = "IronManFlightWarpFX"
BLUR_FPS, STREAK_FPS = 30, 60
WORK = 2
BLUR_DIV = 6
BLUR_TAPS = 7
BLUR_STEP = 0.024
BLUR_CLEAR = (0.20, 0.62)
BLUR_ALPHA = 0.92
BLUR_LIFT = 1.10
KEEP_OUT = ((0.0, 0.84, 0.26, 0.97),)
STREAKS = 240
STREAK_COL = (110, 170, 255)
GLOW = (0.42, 1.05, 120)
RINGS = 3
RING_EVERY = 0.9
CRUISE_TOP = 200000.0
EXCLUDE_FROM_CAPTURE = False
WDA_EXCLUDEFROMCAPTURE = 0x11
IDLE_POLL = 0.015
BOOM_AT, BOOM_FMT = 48, "<dd"
BOOM_K = (0.4, 3.0)
BOOM_STALE = 1.0
BOOM_LATE = 0.05
BOOM_ZOOM = 0.17
BOOM_TAPS = (4, 4, 4)
BOOM_FRINGE = 0.016
BOOM_SHAKE = 0.006
BOOM_FLASH = (70, 60, 235)
BOOM_SQUASH = 0.62
BOOM_GREEN = (0.08, 0.40, 150.0, 0.30)
BOOM_GREEN_COL = (60, 255, 110)
PACK_AT = 64
BLAST_AT = 104
BLAST_GLOW = (0.15, 0.45, 1.0, (0.30, 0.65, 1.0))
SCALE_AT = 96
LEVEL_AT = 88
CRUISE_GLOW = (70.0, 160.0, 1.4, 0.48, 0.5)
CRUISE_BLUE = (140, 210, 255)
VHS = (0.9, 26.0, 22.0, 34.0, 0.10)
VHS_TILES = 6
DEMO_BOOMS = ((2.5, 1.0), (5.0, 1.7), (7.5, 2.6), (11.6, 0.85), (12.4, 1.3), (13.3, 1.9))
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
u32.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
u32.FindWindowExW.restype = wt.HWND
u32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
g32.CreateCompatibleDC.restype = wt.HDC
g32.CreateCompatibleDC.argtypes = [wt.HDC]
g32.CreateDIBSection.restype = wt.HBITMAP
g32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
g32.SelectObject.restype = wt.HGDIOBJ
g32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g32.DeleteObject.argtypes = [wt.HGDIOBJ]
g32.DeleteDC.argtypes = [wt.HDC]
g32.StretchBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD]
g32.SetStretchBltMode.argtypes = [wt.HDC, ctypes.c_int]
k32.OpenProcess.restype = wt.HANDLE
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.GetModuleHandleW.restype = wt.HMODULE
u32.CreateWindowExW.restype = wt.HWND
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
SRCCOPY, COLORONCOLOR = 0x00CC0020, 3
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
_proc_ref = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))
_class_done = [False]
def _register():
    if not _class_done[0]:
        wc = WNDCLASSW(lpfnWndProc=_proc_ref, hInstance=k32.GetModuleHandleW(None), lpszClassName="IronManWarp")
        u32.RegisterClassW(ctypes.byref(wc))
        _class_done[0] = True
def _dib(w, h):
    sdc = u32.GetDC(None)
    mdc = g32.CreateCompatibleDC(sdc)
    u32.ReleaseDC(None, sdc)
    bi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
    bits = ctypes.c_void_p()
    bmp = g32.CreateDIBSection(mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    g32.SelectObject(mdc, bmp)
    g32.SetStretchBltMode(mdc, COLORONCOLOR)
    return mdc, np.ctypeslib.as_array((ctypes.c_uint32 * (w * h)).from_address(bits.value)).reshape(h, w)
_game_hwnd = [None]
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
    _game_hwnd[0] = fg
    return (pt.x, pt.y, rc.right, rc.bottom) if rc.right > 64 and rc.bottom > 64 else None
def _yes(v, default=True):
    s = str(v).split(";")[0].split("#")[0].strip().lower()
    return True if s in ("yes", "true", "on", "1") else False if s in ("no", "false", "off", "0") else default
def read_config(path=None):
    cfg = dict(warp_effects=True, warp_blur=True, cruise_top=CRUISE_TOP)
    try:
        import settings
        S = settings.load(path, quiet=True)
    except Exception:
        return cfg
    for name in ("warp_effects", "warp_blur"):
        try:
            v = S.effects[name] if name in S.effects else S.raw("effects").get(name, True)
            cfg[name] = v if isinstance(v, bool) else _yes(v)
        except Exception:
            pass
    try:
        top = float(S.cruise["top_speed_kms"]) * 1000.0
        if math.isfinite(top) and top >= 1000.0:
            cfg["cruise_top"] = top
    except Exception:
        pass
    return cfg
def ini_mtime():
    try:
        import settings
        return settings.INI.stat().st_mtime_ns
    except Exception:
        return None
def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
def _zoom_box(cx, cy, w, h, z):
    return (cx - cx / z, cy - cy / z, cx + (w - cx) / z, cy + (h - cy) / z)
def boom_dur(k):
    return min(1.45, max(0.5, 0.35 + 0.37 * k))
def boom_env(t, k):
    d = boom_dur(k)
    if not 0.0 <= t < d:
        return 0.0
    hold = 0.035 + 0.02 * k
    if t <= hold:
        return 1.0
    u = (t - hold) / (d - hold)
    return (1.0 - u) ** 2
class BoomMix:
    def __init__(self):
        self.zoom = 0.0
        self.close = 0.0
        self.alpha = 0.0
        self.lift = 0.0
        self.fringe = 0.0
        self.shake = (0.0, 0.0)
        self.flash = 0.0
        self.veil = 0.0
        self.flare = 0.0
        self.flare_len = 0.0
        self.flare_k = 0.0
        self.burst = 0.0
        self.burst_spd = 0.0
        self.rings = []
        self.green = 0.0
def boom_mix(booms, now):
    m = None
    for t0, k in booms:
        t = max(0.0, now - t0)
        d = boom_dur(k)
        if t >= d:
            continue
        if m is None:
            m = BoomMix()
        e = boom_env(t, k)
        fd = min(d, 0.10 + 0.06 * k)
        fl = (1.0 - t / fd) ** 2 if t < fd else 0.0
        m.zoom = max(m.zoom, BOOM_ZOOM * k ** 1.1 * e)
        m.close = max(m.close, min(1.0, 0.35 * k) * e)
        m.alpha = max(m.alpha, min(0.96, 0.62 + 0.14 * k) * e)
        m.lift = max(m.lift, min(0.6, 0.25 * k) * fl)
        m.fringe = max(m.fringe, BOOM_FRINGE * k * e)
        m.flash = max(m.flash, min(BOOM_FLASH[2], BOOM_FLASH[0] + BOOM_FLASH[1] * k) * fl)
        m.veil = max(m.veil, max(0.0, k - 1.2) * 45.0 * fl)
        sd = min(d, 0.22 + 0.1 * k)
        if t < sd:
            amp = BOOM_SHAKE * k ** 1.2 * (1.0 - t / sd) ** 2
            ph = (t0 * 7.31) % (2.0 * math.pi)
            m.shake = (m.shake[0] + amp * math.cos(2.0 * math.pi * 11.0 * t + ph),
                       m.shake[1] + amp * 0.7 * math.sin(2.0 * math.pi * 15.0 * t + 1.7 * ph))
        fd2 = min(d, 0.18 + 0.1 * k)
        if t < fd2:
            f2 = min(1.0, 0.45 + 0.25 * k) * (1.0 - t / fd2) ** 1.5
            if f2 > m.flare:
                m.flare, m.flare_len, m.flare_k = f2, min(0.6, 0.25 + 0.12 * k) * (1.0 + 0.6 * t / fd2), k
        gi, go, ga, _gs = BOOM_GREEN
        if t < gi:
            u = t / gi
            g = u * u * (3.0 - 2.0 * u)
        elif t < gi + go:
            u = (t - gi) / go
            g = 1.0 - u * u * (3.0 - 2.0 * u)
        else:
            g = 0.0
        m.green = max(m.green, ga * min(1.3, k) * g)
        m.burst = max(m.burst, min(0.8, 0.25 * k) * e)
        m.burst_spd = max(m.burst_spd, (0.6 + 0.5 * k) * e)
        for j in range(1 if k < 1.4 else 2 if k < 2.2 else 3):
            tr, rd = t - 0.07 * j, 0.85 * d - 0.07 * j
            if 0.0 <= tr < rd:
                m.rings.append((tr / rd, k, (1.0, 0.5, 0.3)[j]))
    return m
class State:
    def __init__(self, demo, cfg=None, shm=None, name=WARPFX_NAME):
        self.demo = demo
        self.cfg = cfg or dict(warp_effects=True, warp_blur=True, cruise_top=CRUISE_TOP)
        self.t0 = time.perf_counter()
        self.shm = shm if shm is not None else bytearray(128) if demo else mmap.mmap(-1, 128, name)
        self.stop = False
        self.frames = [0, 0]
        self.streak_hwnd = None
        self.lock = threading.Lock()
        self.boom_seen = None
        self.boom_list = []
    def read(self, layer="streaks"):
        now = time.perf_counter()
        cfg = self.cfg
        if not cfg.get("warp_effects", True) or (layer == "blur" and not cfg.get("warp_blur", True)):
            return 0.0, 0.0, 0.5, 0.5
        if self.demo:
            t = (now - self.t0) % 14.0
            s = min(1.0, t / 2.5) if t < 10.0 else max(0.0, 1.0 - (t - 10.0) / 1.5)
            return s, min(1.0, t / 3.0) if t < 10.0 else s, 0.5, 0.5
        try:
            t, s, spd, vx, vy, _d = struct.unpack_from("<6d", self.shm, 0)
        except Exception:
            return 0.0, 0.0, 0.5, 0.5
        if now - t > 0.3 or not (0.0 < s <= 1.5):
            return 0.0, 0.0, 0.5, 0.5
        top = cfg.get("cruise_top", CRUISE_TOP)
        return min(1.0, s), min(1.0, max(0.0, spd / top)) ** 0.5, min(0.95, max(0.05, vx)), min(0.95, max(0.05, vy))
    def vp(self, now=None):
        if self.demo:
            return 0.5, 0.5
        now = time.perf_counter() if now is None else now
        try:
            t, _s, _spd, vx, vy = struct.unpack_from("<5d", self.shm, 0)
        except Exception:
            return 0.5, 0.5
        try:
            pt, px, py = struct.unpack_from("<3d", self.shm, PACK_AT)
            if 0.0 <= now - pt <= 0.3 and not _s > 0.01 and 0.0 < px < 1.0 and 0.0 < py < 1.0:
                return px, py
        except Exception:
            pass
        if not now - t <= 0.3:
            return 0.5, 0.5
        return min(0.95, max(0.05, vx)), min(0.95, max(0.05, vy))
    def blast_in(self, now=None):
        if self.demo:
            return None
        now = time.perf_counter() if now is None else now
        try:
            bt, bi = struct.unpack_from("<dd", self.shm, BLAST_AT)
        except Exception:
            return None
        age = now - bt
        if not (bt > 0.0 and 0.0 <= age < sum(BLAST_GLOW[:3]) and 1 <= int(bi) <= 3):
            return None
        return age, int(bi)
    def cruise_glow_in(self, now=None):
        if self.demo:
            return 0.0, None, None
        now = time.perf_counter() if now is None else now
        try:
            t = struct.unpack_from("<d", self.shm, 0)[0]
            lv = struct.unpack_from("<d", self.shm, LEVEL_AT)[0]
            pt, px, py = struct.unpack_from("<3d", self.shm, PACK_AT)
            sc = struct.unpack_from("<d", self.shm, SCALE_AT)[0]
        except Exception:
            return 0.0, None, None
        if not (now - t <= 0.3 and math.isfinite(lv)):
            return 0.0, None, None
        if not (0.0 <= now - pt <= 0.3 and 0.0 < px < 1.0 and 0.0 < py < 1.0):
            px = py = None
        self.scale = sc if math.isfinite(sc) and 0.0 < sc < 10.0 else None
        return min(1.0, max(0.0, lv)), px, py
    def _boom_in(self, bt, bk, now):
        if bt == self.boom_seen:
            return False
        self.boom_seen = bt
        if not (math.isfinite(bt) and math.isfinite(bk)) or bt <= 0.0 or bk <= 0.0:
            return False
        if not -0.5 < now - bt <= BOOM_STALE:
            return False
        self.boom_list = [b for b in self.boom_list if now - b[0] < boom_dur(b[1])][-3:] + [
            (max(bt, now - BOOM_LATE), min(BOOM_K[1], max(BOOM_K[0], bk)))]
        return True
    def _demo_boom(self, now):
        cyc, ph = divmod(now - self.t0, 14.0)
        last = None
        for at, k in DEMO_BOOMS:
            if at <= ph:
                last = (self.t0 + cyc * 14.0 + at, k)
        if last is not None:
            struct.pack_into(BOOM_FMT, self.shm, BOOM_AT, *last)
    def boom_poll(self, now=None):
        now = time.perf_counter() if now is None else now
        with self.lock:
            if self.demo:
                self._demo_boom(now)
            try:
                bt, bk = struct.unpack_from(BOOM_FMT, self.shm, BOOM_AT)
            except Exception:
                bt, bk = 0.0, 0.0
            self._boom_in(bt, bk, now)
            self.boom_list = [b for b in self.boom_list if now - b[0] < boom_dur(b[1])]
            return list(self.boom_list)
    def boom(self, layer="streaks", now=None):
        now = time.perf_counter() if now is None else now
        booms = self.boom_poll(now)
        cfg = self.cfg
        if not booms or not cfg.get("warp_effects", True) or (layer == "blur" and not cfg.get("warp_blur", True)):
            return None
        return boom_mix(booms, now)
    def wants(self, layer="streaks", now=None):
        now = time.perf_counter() if now is None else now
        s, spd, vx, vy = self.read(layer)
        mix = self.boom(layer, now)
        if s <= 0.01 and mix is None:
            return None
        if mix is not None:
            vx, vy = self.vp(now)
        return s, spd, vx, vy, mix
class Layer:
    def __init__(self, title, work=WORK):
        _register()
        self.work = work
        ex = 0x80000 | 0x20 | 0x8 | 0x80 | 0x8000000
        self.hwnd = u32.CreateWindowExW(ex, "IronManWarp", title, 0x80000000, 0, 0, 1, 1, None, None,
                                        k32.GetModuleHandleW(None), None)
        if EXCLUDE_FROM_CAPTURE:
            try:
                u32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE)
            except Exception:
                pass
        self.size = None
        self.shown = False
    def alloc(self, gw, gh):
        if self.size == (gw, gh):
            return
        self.size = (gw, gh)
        self.wdc, self.wview = _dib(gw, gh)
        self.sdc_, self.sview = _dib(gw // self.work, gh // self.work)
    def pump(self):
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
    def present(self, rect, below=None):
        gx, gy, gw, gh = rect
        sw, sh = gw // self.work, gh // self.work
        g32.StretchBlt(self.wdc, 0, 0, gw, gh, self.sdc_, 0, 0, sw, sh, SRCCOPY)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        pt, sz, src = wt.POINT(gx, gy), wt.SIZE(gw, gh), wt.POINT(0, 0)
        sdc = u32.GetDC(None)
        u32.UpdateLayeredWindow(self.hwnd, sdc, ctypes.byref(pt), ctypes.byref(sz), self.wdc, ctypes.byref(src), 0,
                                ctypes.byref(blend), 2)
        u32.ReleaseDC(None, sdc)
        if not self.shown:
            if below:
                u32.SetWindowPos(self.hwnd, below, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            u32.ShowWindow(self.hwnd, 4)
            self.shown = True
            _raise_hud()
    def hide(self):
        if self.shown:
            u32.ShowWindow(self.hwnd, 0)
            self.shown = False
def _raise_hud():
    h = None
    for _ in range(16):
        h = u32.FindWindowExW(None, h, "IronManHUD", None)
        if not h:
            break
        if u32.IsWindowVisible(h):
            u32.SetWindowPos(h, wt.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x4000)
def _keep_out(w, h):
    k = np.ones((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for x0, y0, x1, y1 in KEEP_OUT:
        dx = np.maximum(np.maximum(x0 * w - xx, xx - x1 * w), 0) / (0.04 * w)
        dy = np.maximum(np.maximum(y0 * h - yy, yy - y1 * h), 0) / (0.04 * h)
        k *= np.clip(np.hypot(dx, dy), 0.0, 1.0)
    return k
class Grabber(threading.Thread):
    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.want = None
        self.wake = threading.Event()
        self.bufs, self.size = None, None
        self.full = None
        self.latest = None
    def run(self):
        i = 0
        while not self.state.stop:
            want = self.want
            if want is None:
                self.wake.wait(0.02)
                self.wake.clear()
                continue
            (gx, gy, gw, gh), w2, h2 = want
            if self.size != (w2, h2) or self.full is None or self.full[2] != (gw, gh):
                self.bufs, self.size, self.latest = [_dib(w2, h2) for _ in range(3)], (w2, h2), None
                fdc, fview = _dib(gw, gh)
                self.full = (fdc, fview, (gw, gh))
            hw = _game_hwnd[0]
            if not hw or not u32.PrintWindow(hw, self.full[0], 3):
                time.sleep(0.02)
                continue
            g32.StretchBlt(self.bufs[i][0], 0, 0, w2, h2, self.full[0], 0, 0, gw, gh, SRCCOPY)
            self.latest = (i, time.perf_counter())
            i = (i + 1) % 3
    def frame(self, w2, h2, max_age=0.5):
        lt = self.latest
        if lt is None or self.size != (w2, h2) or time.perf_counter() - lt[1] > max_age:
            return None
        return self.bufs[lt[0]][1].view(np.uint8).reshape(h2, w2, 4)[..., :3].copy()
class BlurFX:
    def __init__(self):
        self.key = None
        self.r = self.keep = self.mask = self.maskf = None
    def render(self, frame, s, vx, vy, mix, sw, sh):
        h2, w2 = frame.shape[:2]
        small = Image.fromarray(frame)
        cx, cy = vx * w2, vy * h2
        key = (w2, h2, round(vx, 2), round(vy, 2))
        if key != self.key:
            yy, xx = np.mgrid[0:h2, 0:w2]
            self.r = (np.hypot((xx - vx * w2) / (w2 * 0.5), (yy - vy * h2) / (h2 * 0.5)) / math.sqrt(2.0)).astype(
                np.float32)
            self.keep = _keep_out(w2, h2)
            self.maskf = (_smooth(self.r, *BLUR_CLEAR) * self.keep).astype(np.float32)
            self.mask = (self.maskf * 256.0).astype(np.uint16)
            self.key = key
        box = None
        if mix is None:
            acc = frame.astype(np.uint16)
            for i in range(1, BLUR_TAPS):
                acc += np.asarray(small.resize((w2, h2), Image.BILINEAR,
                                               box=_zoom_box(cx, cy, w2, h2, 1.0 + BLUR_STEP * s * i)))
            a = ((self.mask.astype(np.uint32) * int(255 * BLUR_ALPHA * s)) >> 8).astype(np.uint16)
            bl = np.minimum((acc.astype(np.uint32) * int(1024 * BLUR_LIFT / BLUR_TAPS)) >> 10, 255).astype(np.uint16)
        else:
            q = (1.0 + BLUR_STEP * s * (BLUR_TAPS - 1) + mix.zoom) ** (1.0 / (math.prod(BOOM_TAPS) - 1))
            img, acc, step = small, frame.astype(np.uint16), 1
            for p, n in enumerate(BOOM_TAPS):
                if p:
                    acc >>= BOOM_TAPS[p - 1].bit_length() - 1
                    img = Image.fromarray(acc.astype(np.uint8))
                for i in range(1, n):
                    acc += np.asarray(img.resize((w2, h2), Image.BILINEAR,
                                                 box=_zoom_box(cx, cy, w2, h2, q ** (step * i))))
                step *= n
            bl = np.minimum(acc * np.float32((BLUR_LIFT + mix.lift) / BOOM_TAPS[-1]), 255.0).astype(np.uint8)
            if mix.fringe > 0.002:
                for ch, f in ((2, 1.0), (1, 0.5)):
                    im = Image.fromarray(np.ascontiguousarray(bl[..., ch]))
                    bl[..., ch] = np.asarray(im.resize((w2, h2), Image.BILINEAR,
                                                       box=_zoom_box(cx, cy, w2, h2, 1.0 + mix.fringe * f)))
            c = mix.close
            mb = _smooth(self.r, BLUR_CLEAR[0] * (1.0 - c), BLUR_CLEAR[1] * (1.0 - 0.65 * c)) * self.keep
            a = np.maximum(self.maskf * np.float32(BLUR_ALPHA * s * 255.0),
                           mb * np.float32(255.0 * mix.alpha)).astype(np.uint16)
            bl = bl.astype(np.uint16)
            sx, sy = mix.shake
            if abs(sx) > 1e-5 or abs(sy) > 1e-5:
                dx, dy = -sx * h2, -sy * h2
                mx = max(abs(dx), abs(dy) * w2 / h2) + 0.01
                my = mx * h2 / w2
                box = (mx + dx, my + dy, w2 - mx + dx, h2 - my + dy)
        out = np.empty((h2, w2, 4), np.uint8)
        out[..., :3] = (bl * a[..., None]) >> 8
        out[..., 3] = a
        up = Image.frombuffer("RGBa", (w2, h2), out, "raw", "RGBa", 0, 1).resize((sw, sh), Image.BILINEAR, box=box)
        return np.asarray(up).view(np.uint32).reshape(sh, sw)
def blur_loop(state):
    lay = Layer("Iron Man Warp Blur")
    grab = Grabber(state)
    grab.start()
    fx = BlurFX()
    nxt = 0.0
    shown_t = 0.0
    while not state.stop:
        try:
            lay.pump()
            now = time.perf_counter()
            w = state.wants("blur", now)
            rect = game_rect() if w is not None else None
            if rect is None:
                grab.want, grab.latest = None, None
                lay.hide()
                time.sleep(IDLE_POLL)
                continue
            s, spd, vx, vy, mix = w
            gx, gy, gw, gh = rect
            lay.alloc(gw, gh)
            sw, sh = gw // WORK, gh // WORK
            w2, h2 = gw // BLUR_DIV, gh // BLUR_DIV
            grab.want = (rect, w2, h2)
            grab.wake.set()
            frame = grab.frame(w2, h2)
            if frame is None:
                if lay.shown and now - shown_t > 0.3:
                    lay.hide()
                time.sleep(0.005)
                continue
            lay.sview[:] = fx.render(frame, s, vx, vy, mix, sw, sh)
            lay.present(rect, state.streak_hwnd)
            shown_t = now
            state.frames[0] += 1
            nxt = max(now, nxt) + 1.0 / BLUR_FPS
            time.sleep(max(0.0, nxt - time.perf_counter()))
        except Exception as e:
            print(f"warp blur frame failed: {e!r}", flush=True)
            lay.hide()
            time.sleep(0.1)
    lay.hide()
SPHERE = (2.4, 0.22, 0.90, 1.30, 0.35)
def sphere_mask(sw, sh, cx, cy, rad):
    xs = (np.arange(sw, dtype=np.float32) - cx) / np.float32(rad)
    ys = (np.arange(sh, dtype=np.float32) - cy) / np.float32(rad)
    r = np.sqrt(np.add.outer(ys * ys, xs * xs))
    e0, e1 = SPHERE[2], SPHERE[3]
    u = np.clip((r - e0) / (e1 - e0), 0.0, 1.0)
    return r, 1.0 - u * u * (3.0 - 2.0 * u)
def sphere_over(out, sw, sh, cx, cy, rad, alpha, rgb):
    r, fade = sphere_mask(sw, sh, cx, cy, rad)
    mid = SPHERE[1]
    rim = mid + (1.0 - mid) * np.minimum(r, 1.0) ** 2.5
    hx = (np.arange(sw, dtype=np.float32) - (cx - 0.38 * rad)) / np.float32(0.28 * rad)
    hy = (np.arange(sh, dtype=np.float32) - (cy - 0.42 * rad)) / np.float32(0.28 * rad)
    hl = np.outer(np.exp(-0.5 * hy * hy), np.exp(-0.5 * hx * hx)) * np.float32(SPHERE[4])
    ga = np.clip((rim + hl) * fade, 0.0, 1.0) * np.float32(alpha)
    px = out.view(np.uint8).reshape(sh, sw, 4).astype(np.float32)
    keep = 1.0 - ga / 255.0
    for ch, c in ((0, rgb[2]), (1, rgb[1]), (2, rgb[0])):
        px[..., ch] = px[..., ch] * keep + ga * np.float32(c / 255.0)
    px[..., 3] = px[..., 3] * keep + ga
    return np.clip(px, 0.0, 255.0).astype(np.uint8).view(np.uint32).reshape(sh, sw)
def glow_over(out, sw, sh, cx, cy, alpha, spread, rgb):
    sg = np.float32(spread)
    xs = (np.arange(sw, dtype=np.float32) - cx) / np.float32(sh * 0.5)
    ys = (np.arange(sh, dtype=np.float32) - cy) / np.float32(sh * 0.5)
    q = np.float32(-0.5 / (sg * sg))
    ga = np.outer(np.exp(ys * ys * q), np.exp(xs * xs * q)) * np.float32(alpha)
    px = out.view(np.uint8).reshape(sh, sw, 4).astype(np.float32)
    keep = 1.0 - ga / 255.0
    for ch, c in ((0, rgb[2]), (1, rgb[1]), (2, rgb[0])):
        px[..., ch] = px[..., ch] * keep + ga * np.float32(c / 255.0)
    px[..., 3] = px[..., 3] * keep + ga
    return np.clip(px, 0.0, 255.0).astype(np.uint8).view(np.uint32).reshape(sh, sw)
class Streaks:
    def __init__(self, seed=7):
        self.rnd = rnd = random.Random(seed)
        self.parts = [[rnd.uniform(0, 2 * math.pi), rnd.uniform(0.03, 1.2), rnd.uniform(0.6, 1.4),
                       rnd.uniform(0.35, 1.0)] for _ in range(STREAKS)]
        lut = np.zeros(256, np.uint32)
        for v in range(256):
            f = v / 255.0
            r_, g_, b_ = (int(e + (255 - e) * f ** 1.6) for e in STREAK_COL)
            lut[v] = (b_ * v // 255) | ((g_ * v // 255) << 8) | ((r_ * v // 255) << 16) | (v << 24)
        self.lut = lut
        self.glow_key, self.glow = None, None
        self.rings = []
        self.ring_t = 0.0
        self.cg = [0.0, 0.1, 0.0]
        self.cg_at = None
        self.vhs = 0.0
        self.vhs_key, self.vhs_grain, self.vhs_t, self.vhs_ov = None, None, 0.0, None
    def cruise_glow(self, dt, level, px, py, scale=None):
        a0, a1, s0, s1, ease_s = CRUISE_GLOW
        g = level * 3.0
        if self.cg[0] <= 0.0 and self.vhs <= 0.0:
            self.cg_lock = None
            if px is not None:
                tr = getattr(self, "cg_track", None)
                cur = (px, py, scale if scale else 0.0)
                kt = 1.0 - math.exp(-max(0.0, dt) / 0.3)
                self.cg_track = cur if tr is None else tuple(a + (c - a) * kt for a, c in zip(tr, cur))
        bl = getattr(self, "blast", None)
        if bl is not None and g < 1.0 - 1e-6 and (getattr(self, "cg_lock", None) or getattr(self, "cg_track", None)):
            if getattr(self, "cg_lock", None) is None:
                self.cg_lock = self.cg_track
            lx, ly, lsc = self.cg_lock
            age, bi = bl
            ti, th, to, sizes = BLAST_GLOW
            if age < ti:
                e = age / ti
                e = e * e * (3.0 - 2.0 * e)
            elif age < ti + th:
                e = 1.0
            else:
                e = max(0.0, 1.0 - (age - ti - th) / to)
                e = e * e * (3.0 - 2.0 * e)
            u = sizes[bi - 1]
            r0 = min(s1, s0 * lsc) if lsc else 0.6 * s1
            self.cg = [(a0 + (a1 - a0) * u) * e, r0 + (s1 - r0) * u, 1.0 if bi >= 3 else 0.0]
            self.cg_at = (lx, ly)
            self.vhs = e if bi >= 2 else 0.0
            self.vhs_t += max(0.0, dt)
            if e <= 0.0:
                self.cg[0], self.vhs = 0.0, 0.0
            return (self.cg[0] > 0.0 and self.cg_at is not None) or self.vhs > 0.0
        if g >= 1.0 - 1e-6 and (getattr(self, "cg_lock", None) or getattr(self, "cg_track", None)):
            if getattr(self, "cg_lock", None) is None:
                self.cg_lock = self.cg_track
            lx, ly, lsc = self.cg_lock
            u = min(1.0, (g - 1.0) / 2.0)
            r0 = min(s1, s0 * lsc) if lsc else 0.6 * s1
            tgt = (a0 + (a1 - a0) * u, r0 + (s1 - r0) * u, min(1.0, max(0.0, g - 2.0)))
            self.cg_at = (lx, ly)
        else:
            tgt = (0.0, self.cg[1], self.cg[2])
        k = 1.0 - math.exp(-max(0.0, dt) / ease_s)
        self.cg = [c + (t - c) * k for c, t in zip(self.cg, tgt)]
        if self.cg[0] < 0.5 and tgt[0] == 0.0:
            self.cg[0] = 0.0
        vt = 1.0 if g >= 2.0 - 1e-6 else 0.0
        self.vhs += (vt - self.vhs) * (1.0 - math.exp(-max(0.0, dt) / (VHS[0] / 3.0)))
        if vt == 0.0 and self.vhs < 0.01:
            self.vhs = 0.0
        self.vhs_t += max(0.0, dt)
        return (self.cg[0] > 0.0 and self.cg_at is not None) or self.vhs > 0.0
    def draw(self, sw, sh, now, dt, s, spd, vx, vy, mix=None):
        rnd, parts = self.rnd, self.parts
        cx, cy = vx * sw, vy * sh
        R = math.hypot(sw, sh) * 0.5
        key = (sw, sh, round(vx, 2), round(vy, 2))
        if key != self.glow_key and s > 0.0:
            yy, xx = np.mgrid[0:sh, 0:sw]
            r = np.hypot((xx - cx) / (sw * 0.5), (yy - cy) / (sh * 0.5)) / math.sqrt(2.0)
            self.glow, self.glow_key = (_smooth(r, GLOW[0], GLOW[1]) ** 1.4 * GLOW[2]).astype(np.float32), key
        st, sp = s, spd
        if mix is not None:
            cx, cy = cx + mix.shake[0] * sh, cy + mix.shake[1] * sh
            st, sp = max(s, mix.burst), spd + mix.burst_spd
        im = Image.new("L", (sw, sh), 0)
        d = ImageDraw.Draw(im)
        grow = (0.8 + 4.2 * sp) * dt
        ln = 0.05 + 0.55 * sp
        for p in parts:
            p[1] += p[1] * grow * p[2] + 0.02 * dt
            if p[1] > 1.25:
                p[0], p[1], p[2], p[3] = (rnd.uniform(0, 2 * math.pi), rnd.uniform(0.03, 0.3),
                                          rnd.uniform(0.6, 1.4), rnd.uniform(0.35, 1.0))
            r0 = p[1]
            r1 = r0 * (1.0 + ln * p[2])
            fade = min(1.0, max(0.0, (r0 - 0.06) / 0.3))
            al = int(255 * p[3] * fade * st)
            if al < 8:
                continue
            c_, s_ = math.cos(p[0]), math.sin(p[0])
            d.line([(cx + c_ * r0 * R, cy + s_ * r0 * R), (cx + c_ * r1 * R, cy + s_ * r1 * R)], fill=al,
                   width=1 if r0 < 0.45 else 2)
        if now >= self.ring_t:
            self.ring_t = now + RING_EVERY / max(0.3, 0.4 + spd)
            self.rings.append(now)
        self.rings = [t for t in self.rings if now - t < 1.6][-RINGS:]
        for t in self.rings:
            u = (now - t) / 1.6
            rr = (0.12 + 1.1 * u ** 1.6) * R
            al = int(34 * s * math.sin(math.pi * u))
            if al > 3:
                for j, f_ in enumerate((0.35, 0.7, 1.0)):
                    d.ellipse([cx - rr, cy - rr * 0.62, cx + rr, cy + rr * 0.62], outline=int(al * f_),
                              width=max(1, int((6 - 2 * j) * R / 1470)))
        if mix is None:
            a = np.asarray(im, np.float32)
            a = np.minimum(255.0, a + self.glow * s if s > 0.0 and self.glow is not None else a).astype(np.uint8)
            return self.lut[a]
        a = np.asarray(im, np.float32)
        np.maximum(a, self._boom_light(sw, sh, cx, cy, R, mix), out=a)
        if s > 0.0:
            a += self.glow * s
        if mix.flash > 0.5:
            xs = (np.arange(sw, dtype=np.float32) - cx) / np.float32(sw * 0.5)
            ys = (np.arange(sh, dtype=np.float32) - cy) / np.float32(sh * 0.5)
            for sig, wgt in ((0.10, 0.55), (0.45, 0.45)):
                q = np.float32(-0.5 / (sig * sig))
                a += np.outer(np.exp(ys * ys * q) * np.float32(mix.flash * wgt), np.exp(xs * xs * q))
        if mix.veil > 0.5:
            a += np.float32(mix.veil)
        np.minimum(a, 255.0, out=a)
        out = self.lut[a.astype(np.uint8)]
        if mix.green > 0.5:
            out = glow_over(out, sw, sh, cx, cy, mix.green, BOOM_GREEN[3], BOOM_GREEN_COL)
        return out
    def _cruise_over(self, out, sw, sh):
        if self.cg_at is None:
            return out
        cx, cy = self.cg_at[0] * sw, self.cg_at[1] * sh
        rad = max(4.0, self.cg[1] * sh * 0.5)
        if self.vhs > 0.0:
            out = self._vhs_over(out, sw, sh, cx, cy, rad)
        if not self.cg[0] > 0.0:
            return out
        b = self.cg[2]
        rgb = tuple(g_ + (c_ - g_) * b for g_, c_ in zip(BOOM_GREEN_COL, CRUISE_BLUE))
        return sphere_over(out, sw, sh, cx, cy, rad, self.cg[0], rgb)
    def _vhs_over(self, out, sw, sh, cx, cy, rad):
        v = self.vhs
        _e, ga_, sa_, wa_, sp_ = VHS
        t = self.vhs_t
        hw, hh = sw, sh
        if self.vhs_key != (hw, hh):
            rng = np.random.default_rng(11)
            self.vhs_grain = [rng.random((hh, hw), dtype=np.float32) for _ in range(VHS_TILES)]
            self.vhs_key, self.vhs_ov = (hw, hh), None
        step = int(t * 12.0)
        ck = (step, round(v, 2), sw, sh, int(cx), int(cy), int(rad))
        if getattr(self, "vhs_ck", None) != ck or self.vhs_ov is None:
            self.vhs_ck = ck
            n = self.vhs_grain[step % VHS_TILES]
            xs = np.arange(hw, dtype=np.float32) / np.float32(hw)
            ys = np.arange(hh, dtype=np.float32) / np.float32(hh)
            ph = 2.0 * math.pi * sp_ * t
            wa = np.float32(wa_ * v)
            grain = (n - 0.5) * np.float32(2.0 * ga_ * v)
            scan = np.zeros(hh, np.float32)
            scan[::2] = sa_ * v
            by = (t * 0.35) % 1.3 - 0.15
            band = np.clip(1.0 - np.abs(ys - by) / 0.025, 0.0, 1.0) * np.float32(18.0 * v)
            lift = np.maximum(grain, 0.0) + band[:, None]
            _r, m = sphere_mask(hw, hh, cx, cy, rad)
            lift = lift * m
            wa = wa * m
            a_add = np.clip(wa + lift + (np.maximum(-grain, 0.0) + scan[:, None]) * m, 0.0, 255.0)
            ov = np.empty((hh, hw, 4), np.float32)
            for ch, k in ((0, 2), (1, 1), (2, 0)):
                o = k * 2.0 * math.pi / 3.0
                cx_ = np.sin(2.0 * math.pi * 1.3 * xs + ph + o).astype(np.float32)
                cy_ = np.sin(2.0 * math.pi * 0.9 * ys - 0.7 * ph + o).astype(np.float32)
                ov[..., ch] = (0.5 + 0.25 * np.add.outer(cy_, cx_)) * wa + lift
            ov[..., 3] = a_add
            ov = np.clip(ov, 0.0, 255.0).astype(np.uint16)
            keep = (256.0 - a_add).astype(np.uint16)
            up = lambda x: x
            ovf, kf = up(ov), up(keep)
            if ovf.shape[:2] != (sh, sw):
                ovf = np.pad(ovf, ((0, sh - ovf.shape[0]), (0, sw - ovf.shape[1]), (0, 0)), mode="edge")
                kf = np.pad(kf, ((0, sh - kf.shape[0]), (0, sw - kf.shape[1])), mode="edge")
            self.vhs_ov, self.vhs_keep = ovf, kf[..., None]
        px = out.view(np.uint8).reshape(sh, sw, 4).astype(np.uint16)
        px = ((px * self.vhs_keep) >> 8) + self.vhs_ov
        return np.minimum(px, 255).astype(np.uint8).view(np.uint32).reshape(sh, sw)
    def _boom_light(self, sw, sh, cx, cy, R, mix):
        im = Image.new("L", (sw, sh), 0)
        d = ImageDraw.Draw(im)
        sc = R / 734.0
        for v, k, amp in sorted(mix.rings, key=lambda x: x[2]):
            rr = (0.03 + (0.85 + 0.3 * k) * (1.0 - (1.0 - v) ** 3)) * R
            peak = 255.0 * min(1.0, 0.45 + 0.17 * k) * amp * (1.0 - v) ** 1.3
            box = [cx - rr, cy - rr * BOOM_SQUASH, cx + rr, cy + rr * BOOM_SQUASH]
            for j, f in ((3, 0.12), (2, 0.25), (1, 0.45)):
                q = rr + j * 1.2 * sc
                a_ = int(peak * f)
                if a_ >= 2:
                    d.ellipse([cx - q, cy - q * BOOM_SQUASH, cx + q, cy + q * BOOM_SQUASH], outline=a_,
                              width=max(1, int(1.2 * sc + 0.5)))
            tail = (0.03 + 0.03 * k) * R * (0.12 + 0.88 * v)
            for i in range(10):
                f = (i + 1) / 10.0
                a_ = int(peak * f ** 2.2)
                if a_ >= 2:
                    d.ellipse(box, outline=a_, width=max(1, int(tail * (1.0 - f) + 1.6 * sc)))
        a = np.asarray(im)
        if mix.flare > 0.01:
            L = mix.flare_len * sw
            hh = (1.5 + 1.5 * mix.flare_k) * sc
            half = int(hh * 3.0) + 2
            y0 = int(cy) - half
            if -half * 2 < y0 < sh:
                strip = Image.new("L", (sw, 2 * half), 0)
                ds = ImageDraw.Draw(strip)
                yc = cy - y0
                for i in range(6):
                    f = (i + 1) / 6.0
                    lw, lh = L * (1.0 - 0.55 * f * f), hh * (3.0 - 2.6 * f)
                    ds.ellipse([cx - lw, yc - lh, cx + lw, yc + lh], fill=int(255 * mix.flare * f ** 1.8))
                sa = np.asarray(strip)
                ya, yb = max(0, y0), min(sh, y0 + 2 * half)
                if yb > ya:
                    a = a.copy()
                    np.maximum(a[ya:yb], sa[ya - y0:yb - y0], out=a[ya:yb])
        return a
def streak_loop(state):
    lay = Layer("Iron Man Warp Streaks")
    state.streak_hwnd = lay.hwnd
    fx = Streaks()
    last = time.perf_counter()
    while not state.stop:
        try:
            lay.pump()
            now = time.perf_counter()
            dt, last = min(0.1, now - last), now
            w = state.wants("streaks", now)
            rect = game_rect() if w is not None else None
            if rect is None:
                lay.hide()
                fx.rings = []
                time.sleep(IDLE_POLL)
                continue
            s, spd, vx, vy, mix = w
            gx, gy, gw, gh = rect
            lay.alloc(gw, gh)
            sw, sh = gw // WORK, gh // WORK
            lay.sview[:] = fx.draw(sw, sh, now, dt, s, spd, vx, vy, mix)
            lay.present(rect)
            state.frames[1] += 1
            time.sleep(max(0.0, 1.0 / STREAK_FPS - (time.perf_counter() - now)))
        except Exception as e:
            print(f"warp streaks frame failed: {e!r}", flush=True)
            lay.hide()
            time.sleep(0.1)
    lay.hide()
GLOW_WORK, GLOW_FPS = 4, 15
def glow_loop(state):
    lay = Layer("Iron Man Cruise Glow", GLOW_WORK)
    fx = Streaks()
    last = time.perf_counter()
    while not state.stop:
        try:
            lay.pump()
            now = time.perf_counter()
            dt, last = min(0.2, now - last), now
            fx.blast = state.blast_in(now)
            on = state.cfg.get("warp_effects", True) and fx.cruise_glow(dt, *state.cruise_glow_in(now),
                                                                          getattr(state, "scale", None))
            rect = game_rect() if on else None
            if rect is None:
                lay.hide()
                time.sleep(0.05)
                continue
            gx, gy, gw, gh = rect
            lay.alloc(gw, gh)
            sw, sh = gw // GLOW_WORK, gh // GLOW_WORK
            lay.sview[:] = fx._cruise_over(np.zeros((sh, sw), np.uint32), sw, sh)
            lay.present(rect)
            time.sleep(max(0.0, 1.0 / GLOW_FPS - (time.perf_counter() - now)))
        except Exception as e:
            print(f"cruise glow frame failed: {e!r}", flush=True)
            lay.hide()
            time.sleep(0.2)
    lay.hide()
def compose(base, views, size=None):
    if size is None:
        size = next((v.shape[1], v.shape[0]) for v in views if v is not None)
    w, h = size
    out = np.asarray(Image.fromarray(np.ascontiguousarray(base)).resize((w, h), Image.BILINEAR), np.float32)
    for lay in views:
        if lay is None:
            continue
        if lay.shape != (h, w):
            lay = np.asarray(Image.fromarray(lay.view(np.uint8).reshape(lay.shape[0], lay.shape[1], 4)).resize(
                (w, h), Image.NEAREST)).view(np.uint32).reshape(h, w)
        a = ((lay >> 24) & 255).astype(np.float32)[..., None] / 255.0
        add = np.stack([(lay >> 16) & 255, (lay >> 8) & 255, lay & 255], -1).astype(np.float32)
        out = out * (1.0 - a) + add
    return np.clip(out, 0, 255).astype(np.uint8)
def alive(pid):
    if pid <= 0:
        return True
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259
def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    demo = "demo" in sys.argv[2:]
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    state = State(demo, read_config())
    cfg_mt = ini_mtime()
    ths = [threading.Thread(target=f, args=(state,), daemon=True) for f in (blur_loop, streak_loop, glow_loop)]
    for th in ths:
        th.start()
        time.sleep(0.05)
    try:
        while alive(pid) and (not demo or time.perf_counter() - state.t0 < float(os.environ.get("WARPFX_DEMO_S", 30))):
            time.sleep(0.5)
            mt = ini_mtime()
            if mt != cfg_mt:
                cfg_mt, state.cfg = mt, read_config()
    finally:
        state.stop = True
        time.sleep(0.2)
        if demo:
            el = time.perf_counter() - state.t0
            print(f"demo {el:.1f} s: blur {state.frames[0] / el:.1f} fps, streaks {state.frames[1] / el:.1f} fps", flush=True)
if __name__ == "__main__":
    main()
