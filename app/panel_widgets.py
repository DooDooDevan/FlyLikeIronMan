import ctypes
import ctypes.wintypes as wt
import math
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
try:
    import hud as _hud
    _WHITE, _ORANGE, _RED, _AMBER = _hud.WHITE, _hud.ORANGE, _hud.RED, _hud.AMBER
    _COLS, _EMPTY, _DISC, _LINE_PX = dict(_hud.GAUGE_COLS), _hud.GAUGE_EMPTY, _hud.GAUGE_DISC, _hud.GAUGE_LINE
except Exception:
    _WHITE, _ORANGE, _RED, _AMBER = (236, 242, 245), (255, 150, 40), (255, 70, 60), (255, 150, 45)
    _COLS = {"throttle": ((34, 206, 52), (200, 255, 34)), "burner": ((40, 100, 232), (92, 156, 255)),
             "sonic": ((250, 190, 26), (226, 124, 6)), "cruise": ((132, 82, 246), (214, 168, 255)),
             "reverse": ((196, 26, 30), (255, 96, 72))}
    _EMPTY, _DISC, _LINE_PX = (27, 30, 46), (10, 14, 22), 3.5
def _hex(c):
    if isinstance(c, str):
        return c
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in c[:3])
def _rgb(c):
    if isinstance(c, str):
        h = c.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])
def mix(a, b, t):
    a, b = _rgb(a), _rgb(b)
    return _hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))
def _gain(c, k):
    return _hex(tuple(v * k for v in _rgb(c)))
BG = _hex(_DISC)
CARD = "#0E1218"
TRACK = _hex(_EMPTY)
HOVER = "#161B28"
SELECTED = "#141A26"
LINE = "#000000"
TEXT = _hex(_WHITE)
TEXT_DIM = "#93989D"
TEXT_OFF = "#4B5055"
RULE = "#5C6065"
STRIP = mix(CARD, TEXT, 0.85)
RED = _hex(_RED)
ORANGE = _hex(_ORANGE)
AMBER = _hex(_AMBER)
INFO = "#96CDFF"
GREEN = _hex(_COLS["throttle"][0])
ON_FILL = BG
ACCENTS = {k: (_hex(v[0]), _hex(v[1])) for k, v in _COLS.items()}
ACCENTS.update(danger=ACCENTS["reverse"], amber=(AMBER, "#FFDEAA"),
               white=("#AEB6BC", TEXT), hot=("#FFD660", "#FFFCEC"), info=("#5A96E6", INFO))
KIND_COLOUR = {"info": INFO, "ok": ACCENTS["throttle"][1], "warn": ORANGE, "error": RED}
HAIR = " "
REDUCE_MOTION = False
FRAME_MS = 16
TAU = 0.15
SCALE = 1.0
_FONTS = {}
_FONT_SPEC = {
    "title": ("SemiBold", 26), "head": ("SemiBold", 22), "card": ("SemiBold", 17), "value": ("SemiBold", 16),
    "label": ("SemiLight", 16), "help": ("Light", 14), "badge": ("SemiBold", 12), "num": ("SemiBold", 30),
    "mono": (None, 13),
}
_SEGOE = {"SemiBold": ("Segoe UI Semibold", "normal"), "SemiLight": ("Segoe UI Semilight", "normal"),
          "Light": ("Segoe UI Light", "normal")}
MIN_FONT_PX = 12
def scale_for(height, user=1.0):
    return max(0.85, min(1.6, float(height) / 1440.0)) * float(user)
def px(v):
    return int(round(v * SCALE))
def _lw(v):
    return max(1, px(v))
def spaced(text):
    return HAIR.join(str(text).upper())
KEY_LABELS = {"MOUSE3": "MOUSE 3", "MOUSE4": "MOUSE 4", "MOUSE5": "MOUSE 5", "PGUP": "PG UP", "PGDN": "PG DN",
              "CAPSLOCK": "CAPS", "SCROLLLOCK": "SCR LK", "BACKSPACE": "BKSP", "DELETE": "DEL", "INSERT": "INS",
              "NONE": "—", "": "—"}
def key_label(name):
    n = str(name or "").strip().upper()
    if n.startswith("NUMPAD"):
        return "NUM " + n[6:]
    return KEY_LABELS.get(n, n)
def font(name):
    if not _FONTS:
        _make_fonts(_ROOT[0] or tk._get_default_root("use panel_widgets fonts"))
    return _FONTS[name]
_ROOT = [None]
def _make_fonts(root):
    fams = set(tkfont.families(root))
    _FONTS.clear()
    for name, (inst, size) in _FONT_SPEC.items():
        n = -max(MIN_FONT_PX, px(size))
        if inst is None:
            spec = dict(family="Consolas" if "Consolas" in fams else "Courier New", size=n)
        elif f"Bahnschrift {inst} Condensed" in fams:
            spec = dict(family=f"Bahnschrift {inst} Condensed", size=n)
        else:
            fam, wgt = _SEGOE[inst]
            spec = dict(family=fam if fam in fams else "Segoe UI", size=n, weight=wgt)
        _FONTS[name] = tkfont.Font(root=root, **spec)
def _caps_y(f, y):
    return y + int(round(f.metrics("descent") * 0.38))
def _fit(f, text, w):
    if w <= 0 or f.measure(text) <= w:
        return text
    while text and f.measure(text + "…") > w:
        text = text[:-1]
    return text.rstrip(HAIR + " ") + "…"
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32")
g32 = ctypes.WinDLL("gdi32")
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
u32.SetWindowsHookExW.restype = wt.HANDLE
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
u32.CallNextHookEx.restype = LRESULT
u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
u32.UnhookWindowsHookEx.argtypes = [wt.HANDLE]
u32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.c_void_p, MONITORENUMPROC, wt.LPARAM]
u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
u32.GetDC.restype = wt.HDC
u32.GetDC.argtypes = [wt.HWND]
u32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u32.GetForegroundWindow.restype = wt.HWND
u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
u32.GetAsyncKeyState.restype = ctypes.c_short
g32.CreateCompatibleDC.restype = wt.HDC
g32.CreateCompatibleDC.argtypes = [wt.HDC]
g32.CreateDIBSection.restype = wt.HBITMAP
g32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE,
                                 wt.DWORD]
g32.SelectObject.restype = wt.HGDIOBJ
g32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g32.DeleteObject.argtypes = [wt.HGDIOBJ]
g32.DeleteDC.argtypes = [wt.HDC]
WH_CBT, HCBT_ACTIVATE, HCBT_SETFOCUS = 5, 5, 9
GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x08000000, 0x80, 0x40000
def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            u32.SetProcessDPIAware()
        except Exception:
            pass
def monitors():
    out = []
    def cb(h, dc, r, lp):
        out.append((r.contents.left, r.contents.top, r.contents.right, r.contents.bottom))
        return 1
    u32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out
def rightmost_monitor():
    m = monitors()
    return max(m, key=lambda r: r[0]) if m else (0, 0, u32.GetSystemMetrics(0), u32.GetSystemMetrics(1))
def monitor_height(x=None, y=None):
    if x is not None and y is not None:
        for r in monitors():
            if r[0] <= x < r[2] and r[1] <= y < r[3]:
                return r[3] - r[1]
    return u32.GetSystemMetrics(1)
class NoActivate:
    def __init__(self, block=True):
        self.block = block
        self.refused = 0
        self._proc = HOOKPROC(self._cb)
        self.hook = u32.SetWindowsHookExW(WH_CBT, self._proc, None, k32.GetCurrentThreadId())
    def _cb(self, code, wp, lp):
        if self.block and code in (HCBT_ACTIVATE, HCBT_SETFOCUS):
            self.refused += 1
            return 1
        return u32.CallNextHookEx(None, code, wp, lp)
    def remove(self):
        if self.hook:
            u32.UnhookWindowsHookEx(self.hook)
            self.hook = None
_GUARD = []
def no_activate_guard(block=True):
    if not _GUARD:
        _GUARD.append(NoActivate(block))
        tk_activation_lock()
    _GUARD[0].block = block
    return _GUARD[0]
_LOCK = []
def tk_activation_lock():
    if _LOCK:
        return _LOCK[0]
    import struct
    _LOCK.append(0)
    try:
        __import__("_tkinter")
        kx = ctypes.WinDLL("kernel32", use_last_error=True)
        kx.GetModuleHandleW.restype = ctypes.c_void_p
        kx.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        kx.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(wt.DWORD)]
        kx.VirtualProtect.restype = wt.BOOL
        base = None
        for name in ("tk86t.dll", "tk86.dll", "tk87.dll", "tcl9tk87.dll"):
            base = kx.GetModuleHandleW(name)
            if base:
                break
        if not base:
            return 0
        rd = lambda a, f: struct.unpack(f, ctypes.string_at(a, struct.calcsize(f)))
        nt = base + rd(base + 0x3C, "<I")[0]
        wide = rd(nt + 24, "<H")[0] == 0x20B
        ptr, pfmt = (8, "<Q") if wide else (4, "<I")
        imp_rva = rd(nt + 24 + (112 if wide else 96) + 8, "<I")[0]
        if not imp_rva:
            return 0
        def blocked():
            g = _GUARD[0] if _GUARD else None
            return bool(g and g.hook and g.block)
        H = ctypes.c_void_p
        protos = {"SetActiveWindow": ctypes.WINFUNCTYPE(H, H), "SetForegroundWindow": ctypes.WINFUNCTYPE(wt.BOOL, H),
                  "BringWindowToTop": ctypes.WINFUNCTYPE(wt.BOOL, H),
                  "ShowWindow": ctypes.WINFUNCTYPE(wt.BOOL, H, ctypes.c_int),
                  "SetWindowPos": ctypes.WINFUNCTYPE(wt.BOOL, H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                     ctypes.c_int, wt.UINT)}
        quiet = {1: 4, 5: 8, 9: 4, 10: 4}
        def wrap(name, orig):
            if name in ("SetActiveWindow", "SetForegroundWindow", "BringWindowToTop"):
                return lambda h: 0 if blocked() else orig(h)
            if name == "ShowWindow":
                return lambda h, cmd: orig(h, quiet.get(cmd, cmd) if blocked() else cmd)
            return lambda h, after, x, y, cx, cy, fl: orig(h, after, x, y, cx, cy, (fl | 0x10) if blocked() else fl)
        def put(slot, value):
            old = wt.DWORD()
            if not kx.VirtualProtect(slot, ptr, 0x04, ctypes.byref(old)):
                return False
            ctypes.memmove(slot, struct.pack(pfmt, value), ptr)
            kx.VirtualProtect(slot, ptr, old.value, ctypes.byref(old))
            return True
        keep, undo, d = [], [], base + imp_rva
        while True:
            oft, _ts, _fwd, name_rva, ft = rd(d, "<IIIII")
            if not name_rva:
                break
            if oft and ctypes.string_at(base + name_rva).decode("ascii", "replace").lower() == "user32.dll":
                i = 0
                while True:
                    ent = rd(base + oft + ptr * i, pfmt)[0]
                    if not ent:
                        break
                    if not ent >> (ptr * 8 - 1):
                        fn = ctypes.string_at(base + ent + 2).decode("ascii", "replace")
                        if fn in protos:
                            slot = base + ft + ptr * i
                            was = rd(slot, pfmt)[0]
                            orig = protos[fn](was)
                            cb = protos[fn](wrap(fn, orig))
                            keep.append((cb, orig))
                            if put(slot, ctypes.cast(cb, ctypes.c_void_p).value):
                                undo.append((slot, was))
                    i += 1
            d += 20
        def unlock():
            while undo:
                put(*undo.pop())
        import atexit
        atexit.register(unlock)
        _LOCK[:] = [len(undo), keep, unlock]
        return len(undo)
    except Exception as e:
        print(f"panel_widgets: tk_activation_lock: {e}", file=sys.stderr)
        return _LOCK[0]
def tk_activation_unlock():
    if len(_LOCK) > 2:
        _LOCK[2]()
def _key_down(vk):
    return bool(u32.GetAsyncKeyState(vk) & 0x8000)
class _Animator:
    FINISH_HIDDEN = ("ease", "slide", "scroll", "flash")
    def __init__(self):
        self.jobs = {}
        self.after_id = None
        self.paused = False
        self.root = None
    def add(self, widget, name, fn):
        self.root = widget._root()
        self.jobs[(widget, name)] = fn
        self._kick(FRAME_MS)
    def remove(self, widget, name=None):
        for k in [k for k in self.jobs if k[0] is widget and (name is None or k[1] == name)]:
            del self.jobs[k]
    def active(self, widget, name):
        return (widget, name) in self.jobs
    def _kick(self, ms):
        if self.after_id is None and not self.paused and self.jobs and self.root is not None:
            try:
                self.after_id = self.root.after(ms, self._tick)
            except tk.TclError:
                self.after_id = None
    def _tick(self):
        self.after_id = None
        now = time.perf_counter()
        ran = False
        for key, fn in list(self.jobs.items()):
            w = key[0]
            try:
                if not w.winfo_exists():
                    self.jobs.pop(key, None)
                    continue
                if not w.winfo_viewable():
                    if key[1] in self.FINISH_HIDDEN and not fn(now + 60.0):
                        self.jobs.pop(key, None)
                    continue
                ran = True
                if not fn(now):
                    self.jobs.pop(key, None)
            except tk.TclError:
                self.jobs.pop(key, None)
            except Exception:
                self.jobs.pop(key, None)
                try:
                    self.root.report_callback_exception(*sys.exc_info())
                except Exception:
                    pass
        self._kick(FRAME_MS if ran else 250)
ANIM = _Animator()
def pause_animations(flag):
    ANIM.paused = bool(flag)
    if not flag:
        ANIM._kick(FRAME_MS)
def _ease(cur, target, dt, tau=TAU):
    if REDUCE_MOTION or dt <= 0:
        return target
    return target + (cur - target) * math.exp(-dt / tau)
def _pulse(now, speed=6.0):
    return 1.0 if REDUCE_MOTION else 0.55 + 0.45 * math.sin(now * speed)
_PRESS_T = [0.0]
def init(root, scale=None, user=1.0):
    global SCALE
    SCALE = float(scale) if scale else scale_for(monitor_height(), user)
    _ROOT[0] = root
    _make_fonts(root)
    ANIM.root = root
    root.bind_all("<MouseWheel>", _wheel, add="+")
    root.bind_all("<ButtonPress>", lambda e: _PRESS_T.__setitem__(0, time.perf_counter()), add="+")
    root.bind_all("<FocusIn>", _focus_scroll, add="+")
    return SCALE
def _bg_of(parent, colour=None):
    try:
        c = colour or parent.cget("bg")
        if isinstance(c, str) and len(c) == 7 and c.startswith("#"):
            return c.upper()
        r, g, b = parent.winfo_rgb(c)
        return "#%02X%02X%02X" % (r >> 8, g >> 8, b >> 8)
    except (tk.TclError, AttributeError):
        return BG
class Tooltip:
    DELAY = 450
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self._after = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")
    def _text(self):
        t = self.text() if callable(self.text) else self.text
        return str(t or "")
    def _enter(self, e=None):
        self._cancel()
        if self._text():
            self._after = self.widget.after(self.DELAY, self.show)
    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
    @staticmethod
    def _canvas(top):
        c = getattr(top, "_pw_tip", None)
        if c is None or not c.winfo_exists():
            c = tk.Canvas(top, bg=LINE, highlightthickness=0, bd=0, takefocus=0)
            top._pw_tip = c
        return c
    def show(self, force=False):
        self._after = None
        text = self._text()
        w = self.widget
        if not text or not w.winfo_exists() or not (force or w.winfo_viewable()):
            return
        top = w.winfo_toplevel()
        c = self._canvas(top)
        c.delete("all")
        f = font("help")
        L, pad, strip = _lw(2), px(10), _lw(3)
        wrap = px(360)
        t = c.create_text(L + strip + pad, L + pad, text=text, font=f, fill=TEXT, anchor="nw", width=wrap)
        x0, y0, x1, y1 = c.bbox(t)
        cw, ch = x1 + pad + L, y1 + pad + L
        c.create_rectangle(L, L, cw - L, ch - L, fill=CARD, outline="", width=0)
        c.create_rectangle(L, L, L + strip, ch - L, fill=STRIP, outline="", width=0)
        c.tag_raise(t)
        c.configure(width=cw, height=ch)
        tw, th = top.winfo_width(), top.winfo_height()
        wx, wy = w.winfo_rootx() - top.winfo_rootx(), w.winfo_rooty() - top.winfo_rooty()
        x = min(max(px(4), wx), max(px(4), tw - cw - px(4)))
        y = wy + w.winfo_height() + px(6)
        if y + ch > th - px(4):
            y = max(px(4), wy - ch - px(6))
        c.place(x=x, y=y)
        tk.Misc.tkraise(c)
    def hide(self, e=None):
        self._cancel()
        try:
            top = self.widget.winfo_toplevel()
            c = getattr(top, "_pw_tip", None)
            if c is not None and c.winfo_exists():
                c.place_forget()
        except (tk.TclError, KeyError):
            pass
class _Widget(tk.Canvas):
    FOCUSABLE = True
    def __init__(self, parent, width, height, bg=None, tip=None, cursor="hand2"):
        bg = _bg_of(parent, bg)
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0,
                         takefocus=1 if self.FOCUSABLE else 0, cursor=cursor if self.FOCUSABLE else "")
        self.bg = bg
        self.L = _lw(3)
        self.R = _lw(2)
        self._hover = self._focus = self._ring = self._pressed = False
        self._disabled = False
        self._why = None
        self._tip_text = tip
        self.tooltip = Tooltip(self, self._tip)
        self._cbs = []
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Configure>", lambda e: self.redraw(), add="+")
    def _tip(self):
        if self._disabled and self._why:
            return self._why
        return self._tip_text() if callable(self._tip_text) else self._tip_text
    def set_tip(self, text):
        self._tip_text = text
    def set_disabled(self, flag, why=None):
        self._disabled = bool(flag)
        self._why = why
        self.configure(takefocus=0 if flag or not self.FOCUSABLE else 1,
                       cursor="" if flag or not self.FOCUSABLE else "hand2")
        if flag:
            self._pressed = False
        self.redraw()
    @property
    def disabled(self):
        return self._disabled
    def on_change(self, cb):
        self._cbs.append(cb)
        return self
    def _fire(self, value):
        for cb in list(self._cbs):
            cb(value)
    def _on_enter(self, e=None):
        self._hover = True
        self.redraw()
    def _on_leave(self, e=None):
        self._hover = False
        self.redraw()
    def _on_focus_in(self, e=None):
        self._focus = True
        self._ring = time.perf_counter() - _PRESS_T[0] > 0.3
        self.redraw()
    def _on_focus_out(self, e=None):
        self._focus = self._ring = False
        self.redraw()
    def _keyed(self):
        if self._focus and not self._ring:
            self._ring = True
    def _grab_focus(self):
        self.tooltip.hide()
        if self.FOCUSABLE and not self._disabled:
            try:
                self.focus_set()
            except tk.TclError:
                pass
    def _size(self):
        w, h = self.winfo_width(), self.winfo_height()
        return (w if w > 1 else int(self.cget("width")), h if h > 1 else int(self.cget("height")))
    def _inside(self, e):
        w, h = self._size()
        return 0 <= e.x < w and 0 <= e.y < h
    def redraw(self):
        try:
            self.delete("all")
            self._draw(*self._size())
        except tk.TclError:
            pass
    def _draw(self, w, h):
        pass
    def rect(self, x0, y0, x1, y1, fill, tags=()):
        return self.create_rectangle(x0, y0, x1, y1, fill=fill, outline="", width=0, tags=tags)
    def box(self, x0, y0, x1, y1, fill, line=None, L=None):
        L = self.L if L is None else L
        self.rect(x0 - L, y0 - L, x1 + L, y1 + L, line or LINE)
        if fill:
            self.rect(x0, y0, x1, y1, fill)
    def ring(self, x0, y0, x1, y1, L=None):
        if self._focus and self._ring and not self._disabled:
            L = self.L if L is None else L
            self.rect(x0 - L - self.R, y0 - L - self.R, x1 + L + self.R, y1 + L + self.R, TEXT)
    def grad(self, x0, y0, x1, y1, accent, k=1.0, inward=False):
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        e, m = _accent(accent)
        e, m = _rgb(e), _rgb(m)
        h = y1 - y0
        n = max(1, min(12, h // max(1, px(2))))
        for i in range(n):
            t = (i + 0.5) / n
            f = t if inward else 1.0 - abs(2.0 * t - 1.0)
            c = tuple(min(255, (e[j] + (m[j] - e[j]) * f) * k) for j in range(3))
            self.rect(x0, y0 + round(h * i / n), x1, y0 + round(h * (i + 1) / n), _hex(c))
    def _vgrad(self, x0, y0, x1, y1, accent, k=1.0):
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        e, m = (_rgb(c) for c in _accent(accent))
        wd = x1 - x0
        n = max(1, min(12, wd))
        for i in range(n):
            f = 1.0 - abs(2.0 * (i + 0.5) / n - 1.0)
            c = tuple(min(255, (e[j] + (m[j] - e[j]) * f) * k) for j in range(3))
            self.rect(x0 + round(wd * i / n), y0, x0 + round(wd * (i + 1) / n), y1, _hex(c))
    def text(self, x, y, s, f="label", fill=TEXT, anchor="w", caps=True, **kw):
        fo = font(f) if isinstance(f, str) else f
        return self.create_text(x, _caps_y(fo, y) if caps else y, text=s, font=fo, fill=fill, anchor=anchor, **kw)
    def custom_badge(self, x, y, anchor="w"):
        f = font("badge")
        s = spaced("custom")
        tw, cap = f.measure(s), int(f.metrics("ascent") * 0.72)
        pad = px(5)
        x0 = x if anchor == "w" else x - tw - 2 * pad
        L = _lw(2)
        y0, y1 = y - cap // 2 - L - px(3), y + (cap + 1) // 2 + L + px(3)
        self.rect(x0, y0, x0 + tw + 2 * pad, y1, AMBER)
        self.rect(x0 + L, y0 + L, x0 + tw + 2 * pad - L, y1 - L, self.bg)
        self.text(x0 + pad, (y0 + y1) // 2, s, f, AMBER)
        return x0 + tw + 2 * pad
def _accent(a):
    if a is None:
        return ACCENTS["white"]
    if isinstance(a, str):
        if a in ACCENTS:
            return ACCENTS[a]
        return (mix(a, LINE, 0.25), a)
    return a
def _eq(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-6
        except (TypeError, ValueError):
            return False
    return a == b
def _decimals(step):
    s = f"{step:.6f}".rstrip("0").rstrip(".")
    return len(s.split(".")[1]) if "." in s else 0
class Slider(_Widget):
    COMMIT_MS = 400
    def __init__(self, parent, lo, hi, value=None, step=1, default=None, fmt=None, accent="throttle", width=None,
                 readout=None, big_step=10, command=None, tip=None, bg=None):
        self.lo, self.hi, self.step = lo, hi, step
        self._ints = all(isinstance(v, int) and not isinstance(v, bool) for v in (lo, hi, step))
        self.default = default
        self.fmt = fmt
        self.accent = accent
        self.big = big_step
        self.ro = px(96) if readout is None else readout
        v = lo if value is None else value
        self._value = self._committed = v
        self._shown = self._clamp(v)
        self._t = time.perf_counter()
        self._drag = None
        self._key_after = None
        self._live = []
        super().__init__(parent, width or px(320), px(40), bg, tip)
        if command:
            self.on_change(command)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", lambda e: self.reset())
        for k, d in (("Left", -1), ("Right", 1), ("Down", -1), ("Up", 1)):
            self.bind(f"<KeyPress-{k}>", lambda e, d=d: self._key(d * (self.big if e.state & 1 else 1)))
        self.bind("<KeyPress-Prior>", lambda e: self._key(self.big))
        self.bind("<KeyPress-Next>", lambda e: self._key(-self.big))
        self.bind("<KeyPress-Home>", lambda e: self._key_to(self.lo))
        self.bind("<KeyPress-End>", lambda e: self._key_to(self.hi))
        self.bind("<FocusOut>", lambda e: self._commit_keys(), add="+")
    def _clamp(self, v):
        return max(self.lo, min(self.hi, v))
    def _snap(self, v):
        v = self._clamp(self.lo + round((v - self.lo) / self.step) * self.step)
        return int(round(v)) if self._ints else round(v, 6)
    @property
    def custom(self):
        try:
            return not (self.lo - 1e-9 <= self._value <= self.hi + 1e-9)
        except TypeError:
            return True
    def get(self):
        return self._value
    def set(self, value, animate=True):
        self._value = self._committed = value
        try:
            target = self._clamp(float(value))
        except (TypeError, ValueError):
            target = self.lo
        if not animate or REDUCE_MOTION:
            self._shown = target
            ANIM.remove(self, "ease")
        else:
            self._ease_to()
        self.redraw()
    def set_default(self, v):
        self.default = v
        self.redraw()
    def on_live(self, cb):
        self._live.append(cb)
        return self
    def reset(self):
        if self._disabled or self.default is None:
            return
        self._cancel_keys()
        self._value = self.default
        self._ease_to()
        self._fire_live()
        self._commit()
    def _commit(self):
        if not _eq(self._value, self._committed):
            self._committed = self._value
            self._fire(self._value)
        self.redraw()
    def _fire_live(self):
        for cb in list(self._live):
            cb(self._value)
    def _ease_to(self):
        self._t = time.perf_counter()
        ANIM.add(self, "ease", self._ease_step)
    def _ease_step(self, now):
        target = self._clamp(float(self._value)) if not self.custom else \
            (self.hi if self._value > self.hi else self.lo)
        self._shown = _ease(self._shown, target, now - self._t)
        self._t = now
        span = (self.hi - self.lo) or 1
        done = abs(self._shown - target) / span < 0.0015
        if done:
            self._shown = target
        self.redraw()
        return not done
    def _track(self, w):
        m = self.R + self.L + px(4)
        x0 = m
        x1 = w - (self.ro + px(14) if self.ro else 0) - m
        return x0, max(x0 + px(20), x1)
    def _x(self, v, w):
        x0, x1 = self._track(w)
        span = (self.hi - self.lo) or 1
        return x0 + (min(self.hi, max(self.lo, v)) - self.lo) / span * (x1 - x0)
    def _v(self, x, w):
        x0, x1 = self._track(w)
        return self.lo + (x - x0) / max(1, x1 - x0) * (self.hi - self.lo)
    def _text_of(self, v):
        if callable(self.fmt):
            return self.fmt(v)
        if isinstance(self.fmt, str):
            return self.fmt.format(v)
        if isinstance(v, float) and not self._ints:
            return f"{v:.{_decimals(self.step)}f}"
        return f"{v}"
    def _draw(self, w, h):
        cy = h // 2
        x0, x1 = self._track(w)
        ty0, ty1 = cy - px(6), cy + px(6)
        dis, cus = self._disabled, self.custom
        k = 1.12 if (self._hover or self._drag) and not dis else 1.0
        self.ring(x0, ty0, x1, ty1)
        self.box(x0, ty0, x1, ty1, TRACK)
        xv = int(round(self._x(self._shown, w)))
        if dis:
            self.rect(x0, ty0, xv, ty1, mix(TRACK, TEXT_OFF, 0.45))
        else:
            self.grad(x0, ty0, xv, ty1, self.accent, k)
        if self.default is not None and not cus:
            try:
                xd = int(round(self._x(float(self.default), w)))
                self.rect(xd - _lw(1), ty1 + self.L + px(2), xd + _lw(1), ty1 + self.L + px(7),
                          mix(self.bg, TEXT, 0.5 if not dis else 0.2))
            except (TypeError, ValueError):
                pass
        tw, th = px(4), px(12)
        col = TEXT_OFF if dis else (AMBER if cus else ("#FFFFFF" if self._drag is not None or self._hover else TEXT))
        self.box(xv - tw, cy - th, xv + tw, cy + th, col)
        self._readout(w, cy, x1)
    def _readout(self, w, cy, x1):
        if not self.ro:
            return
        rx = x1 + self.L + px(14)
        txt = self._text_of(self._value)
        f = font("value")
        dis, cus = self._disabled, self.custom
        col = TEXT_OFF if dis else (AMBER if cus else TEXT)
        if not cus:
            self.text(rx, cy, _fit(f, txt, w - rx), f, col)
            return
        bw = font("badge").measure(spaced("custom")) + px(10)
        if f.measure(txt) + px(8) + bw <= w - rx:
            self.text(rx, cy, txt, f, col)
            self.custom_badge(rx + f.measure(txt) + px(8), cy)
        else:
            self.text(rx, cy - px(9), _fit(f, txt, w - rx), f, col)
            self.custom_badge(rx, cy + px(10))
    def _press(self, e):
        if self._disabled:
            return
        self._grab_focus()
        self._cancel_keys()
        w = self._size()[0]
        if e.x > self._track(w)[1] + px(10):
            return
        xv = self._x(self._shown, w)
        grab = e.x - xv if abs(e.x - xv) <= px(4) + self.L + px(3) else 0.0
        self._drag = grab
        self._pressed = True
        self._move_to(e.x - grab, ease=grab == 0.0)
    def _motion(self, e):
        if self._drag is None or self._disabled:
            return
        self._move_to(e.x - self._drag, ease=False)
    def _release(self, e):
        if self._drag is None:
            return
        self._drag = None
        self._pressed = False
        self._commit()
    def _move_to(self, x, ease):
        v = self._snap(self._v(x, self._size()[0]))
        changed = not _eq(v, self._value)
        self._value = v
        if ease:
            self._ease_to()
        else:
            ANIM.remove(self, "ease")
            self._shown = self._clamp(float(v))
        if changed:
            self._fire_live()
        self.redraw()
    def _key(self, steps):
        if self._disabled:
            return "break"
        self._keyed()
        base = self._clamp(self._value) if not self.custom else (self.hi if self._value > self.hi else self.lo)
        self._key_to(base + steps * self.step)
        return "break"
    def _key_to(self, v):
        if self._disabled:
            return "break"
        self._keyed()
        v = self._snap(v)
        if not _eq(v, self._value):
            self._value = v
            self._ease_to()
            self._fire_live()
        self._cancel_keys()
        self._key_after = self.after(self.COMMIT_MS, self._commit_keys)
        self.redraw()
        return "break"
    def _cancel_keys(self):
        if self._key_after:
            try:
                self.after_cancel(self._key_after)
            except tk.TclError:
                pass
            self._key_after = None
    def _commit_keys(self):
        if self._key_after:
            self._cancel_keys()
            self._commit()
class DualSlider(Slider):
    def __init__(self, parent, lo, hi, value=None, step=1, default=None, fmt=None, accent="throttle", width=None,
                 readout=None, big_step=10, min_gap=None, command=None, tip=None, bg=None):
        self.gap = step if min_gap is None else min_gap
        self._which = 1
        a, b = value if value is not None else (lo, hi)
        super().__init__(parent, lo, hi, None, step, default, fmt, accent, width,
                         px(120) if readout is None else readout, big_step, command, tip, bg)
        self._value = self._committed = (a, b)
        self._shown = (self._clamp(a), self._clamp(b))
        self.bind("<KeyPress-space>", self._swap)
    @property
    def custom(self):
        try:
            return any(not (self.lo - 1e-9 <= v <= self.hi + 1e-9) for v in self._value)
        except TypeError:
            return True
    def set(self, value, animate=True):
        a, b = value
        self._value = self._committed = (a, b)
        if not animate or REDUCE_MOTION:
            self._shown = (self._clamp(a), self._clamp(b))
            ANIM.remove(self, "ease")
        else:
            self._ease_to()
        self.redraw()
    def _ease_step(self, now):
        dt = now - self._t
        self._t = now
        tg = tuple(self._clamp(float(v)) for v in self._value)
        self._shown = tuple(_ease(s, t, dt) for s, t in zip(self._shown, tg))
        span = (self.hi - self.lo) or 1
        done = all(abs(s - t) / span < 0.0015 for s, t in zip(self._shown, tg))
        if done:
            self._shown = tg
        self.redraw()
        return not done
    def _push(self, which, v):
        v = self._snap(v)
        a, b = (self._clamp(x) for x in self._value)
        if which == 0:
            a = min(v, self.hi - self.gap)
            b = max(b, a + self.gap)
        else:
            b = max(v, self.lo + self.gap)
            a = min(a, b - self.gap)
        return (self._snap(a), self._snap(b))
    def _text_of(self, v):
        one = super()._text_of
        return f"{one(v[0])}  –  {one(v[1])}"
    def _draw(self, w, h):
        cy = h // 2
        x0, x1 = self._track(w)
        ty0, ty1 = cy - px(6), cy + px(6)
        dis, cus = self._disabled, self.custom
        k = 1.12 if (self._hover or self._drag is not None) and not dis else 1.0
        self.ring(x0, ty0, x1, ty1)
        self.box(x0, ty0, x1, ty1, TRACK)
        xa, xb = (int(round(self._x(s, w))) for s in self._shown)
        if dis:
            self.rect(xa, ty0, xb, ty1, mix(TRACK, TEXT_OFF, 0.45))
        else:
            self.grad(xa, ty0, xb, ty1, self.accent, k)
        if self.default is not None and not cus:
            for d in self.default:
                xd = int(round(self._x(float(d), w)))
                self.rect(xd - _lw(1), ty1 + self.L + px(2), xd + _lw(1), ty1 + self.L + px(7),
                          mix(self.bg, TEXT, 0.5 if not dis else 0.2))
        tw, th = px(4), px(12)
        keys = self._focus and self._ring
        for i, xv in enumerate((xa, xb)):
            hot = i == self._which and (self._drag is not None or keys)
            col = TEXT_OFF if dis else (AMBER if cus else ("#FFFFFF" if hot or self._hover else
                                                           (TEXT_DIM if keys else TEXT)))
            self.box(xv - tw, cy - th, xv + tw, cy + th, col)
        self._readout(w, cy, x1)
    def _press(self, e):
        if self._disabled:
            return
        self._grab_focus()
        self._cancel_keys()
        w = self._size()[0]
        if e.x > self._track(w)[1] + px(10):
            return
        xa, xb = (self._x(s, w) for s in self._shown)
        self._which = 0 if abs(e.x - xa) < abs(e.x - xb) or (e.x < xa) else 1
        if abs(xa - xb) < 2 and e.x > xb:
            self._which = 1
        xv = (xa, xb)[self._which]
        grab = e.x - xv if abs(e.x - xv) <= px(4) + self.L + px(3) else 0.0
        self._drag = grab
        self._pressed = True
        self._move_to(e.x - grab, ease=grab == 0.0)
    def _move_to(self, x, ease):
        v = self._push(self._which, self._v(x, self._size()[0]))
        changed = v != self._value
        self._value = v
        if ease:
            self._ease_to()
        else:
            ANIM.remove(self, "ease")
            self._shown = tuple(self._clamp(float(x_)) for x_ in v)
        if changed:
            self._fire_live()
        self.redraw()
    def _key(self, steps):
        if self._disabled:
            return "break"
        cur = self._clamp(self._value[self._which])
        self._key_to(cur + steps * self.step)
        return "break"
    def _key_to(self, v):
        if self._disabled:
            return "break"
        self._keyed()
        nv = self._push(self._which, v)
        if nv != self._value:
            self._value = nv
            self._ease_to()
            self._fire_live()
        self._cancel_keys()
        self._key_after = self.after(self.COMMIT_MS, self._commit_keys)
        self.redraw()
        return "break"
    def _commit(self):
        if self._value != self._committed:
            self._committed = self._value
            self._fire(self._value)
        self.redraw()
    def reset(self):
        if self._disabled or self.default is None:
            return
        self._cancel_keys()
        self._value = tuple(self.default)
        self._ease_to()
        self._fire_live()
        self._commit()
    def _swap(self, e=None):
        if not self._disabled:
            self._keyed()
            self._commit_keys()
            self._which = 1 - self._which
            self.redraw()
        return "break"
class Toggle(_Widget):
    def __init__(self, parent, value=False, default=None, accent="throttle", text=("ON", "OFF"), command=None,
                 tip=None, bg=None):
        self._value = self._committed = bool(value)
        self._pos = 1.0 if value else 0.0
        self._t = time.perf_counter()
        self.default = default
        self.accent = accent
        self.labels = text
        tw = max(font("value").measure(spaced(t)) for t in text) + px(12) if text else 0
        self.bw, self.bh = px(56), px(26)
        m = _lw(3) + _lw(2)
        super().__init__(parent, self.bw + 2 * m + tw, self.bh + 2 * m, bg, tip)
        if command:
            self.on_change(command)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", lambda e: self.reset())
        self.bind("<KeyPress-space>", self._keypress)
        self.bind("<KeyPress-Return>", self._keypress)
    def get(self):
        return self._value
    def set(self, value, animate=True):
        self._value = self._committed = bool(value)
        self._go(animate)
    def set_default(self, v):
        self.default = v
    def _go(self, animate=True):
        if not animate or REDUCE_MOTION:
            self._pos = 1.0 if self._value else 0.0
            ANIM.remove(self, "ease")
            self.redraw()
        else:
            self._t = time.perf_counter()
            ANIM.add(self, "ease", self._step)
    def _step(self, now):
        target = 1.0 if self._value else 0.0
        self._pos = _ease(self._pos, target, now - self._t, 0.07)
        self._t = now
        done = abs(self._pos - target) < 0.01
        if done:
            self._pos = target
        self.redraw()
        return not done
    custom = False
    def _flip(self, v=None):
        self._value = (not self._value) if v is None else bool(v)
        self._go()
        if self._value != self._committed:
            self._committed = self._value
            self._fire(self._value)
    def reset(self):
        if not self._disabled and self.default is not None:
            self._flip(bool(self.default))
    def _press(self, e):
        if self._disabled:
            return
        self._grab_focus()
        self._pressed = True
        self.redraw()
    def _release(self, e):
        if self._disabled or not self._pressed:
            return
        self._pressed = False
        if self._inside(e):
            self._flip()
        else:
            self.redraw()
    def _keypress(self, e):
        if not self._disabled:
            self._keyed()
            self._flip()
        return "break"
    def _draw(self, w, h):
        m = self.L + self.R
        x0, y0 = m, (h - self.bh) // 2
        x1, y1 = x0 + self.bw, y0 + self.bh
        dis = self._disabled
        self.ring(x0, y0, x1, y1)
        self.rect(x0, y0, x1, y1, LINE)
        L = self.L
        ix0, iy0, ix1, iy1 = x0 + L, y0 + L, x1 - L, y1 - L
        self.rect(ix0, iy0, ix1, iy1, TRACK if not self._hover or dis else mix(TRACK, TEXT, 0.06))
        p = self._pos
        kw = (ix1 - ix0) * 0.42
        kx = ix0 + (ix1 - ix0 - kw) * p
        if p > 0.0:
            lit = int(round(kx))
            k = (1.12 if self._hover else 1.0) * (0.9 if self._pressed else 1.0)
            if dis:
                self.rect(ix0, iy0, lit, iy1, mix(TRACK, TEXT_OFF, 0.45))
            else:
                self.grad(ix0, iy0, lit, iy1, self.accent, k * (0.35 + 0.65 * p))
        kc = TEXT_OFF if dis else mix(TEXT_DIM, TEXT, p)
        if self._hover and not dis:
            kc = mix(kc, "#FFFFFF", 0.5)
        kx0 = int(round(kx))
        self.rect(kx0 - _lw(2), iy0, kx0 + int(kw) + _lw(2), iy1, LINE)
        self.rect(kx0, iy0 + _lw(1), kx0 + int(kw), iy1 - _lw(1), kc)
        if self.labels:
            t = spaced(self.labels[0] if self._value else self.labels[1])
            col = TEXT_OFF if dis else (TEXT if self._value else TEXT_DIM)
            self.text(x1 + L + px(12), (y0 + y1) // 2, t, "value", col)
def _options(opts):
    out = []
    for o in opts:
        if isinstance(o, (tuple, list)):
            out.append((o[0], str(o[1])))
        else:
            out.append((o, str(o)))
    return out
class Segmented(_Widget):
    def __init__(self, parent, options, value=None, default=None, accent="white", width=None, command=None,
                 tip=None, bg=None):
        self.options = _options(options)
        self.default = default
        self.accent = accent
        self._value = self._committed = self.options[0][0] if value is None else value
        self._hot = -1
        self._lit = 1.0
        self._t = 0.0
        f = font("value")
        cw = max(f.measure(spaced(lab)) for _, lab in self.options) + px(28)
        m = _lw(3) + _lw(2)
        self.bh = px(30)
        self.cells_w = width or cw * len(self.options) + _lw(3) * (len(self.options) - 1)
        super().__init__(parent, self.cells_w + 2 * m + self._tag_w(), self.bh + 2 * m, bg, tip)
        if command:
            self.on_change(command)
        self.bind("<Motion>", self._motion)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<Double-Button-1>", lambda e: self.reset())
        self.bind("<KeyPress-Left>", lambda e: self._key(-1))
        self.bind("<KeyPress-Right>", lambda e: self._key(1))
    def index_of(self, value=None):
        v = self._value if value is None else value
        for i, (ov, _) in enumerate(self.options):
            if _eq(ov, v):
                return i
        return -1
    @property
    def custom(self):
        return self.index_of() < 0
    def get(self):
        return self._value
    def set(self, value, animate=True):
        self._value = self._committed = value
        self._resize()
        self._glow(animate)
    def set_default(self, v):
        self.default = v
    def _tag_text(self):
        return spaced("custom") + "  " + str(self._value)
    def _tag_w(self):
        return font("value").measure(self._tag_text()) + px(36) if self.custom else 0
    def _resize(self):
        m = self.L + self.R
        w = self.cells_w + 2 * m + self._tag_w()
        if int(self.cget("width")) != w:
            self.configure(width=w)
    def _glow(self, animate=True):
        if animate and not REDUCE_MOTION:
            self._lit, self._t = 0.4, time.perf_counter()
            ANIM.add(self, "ease", self._step)
        else:
            self._lit = 1.0
            self.redraw()
    def _step(self, now):
        self._lit = _ease(self._lit, 1.0, now - self._t, 0.08)
        self._t = now
        done = self._lit > 0.99
        if done:
            self._lit = 1.0
        self.redraw()
        return not done
    def _choose(self, i):
        v = self.options[i][0]
        if not _eq(v, self._value):
            self._value = v
            self._resize()
            self._glow()
        if not _eq(self._value, self._committed):
            self._committed = self._value
            self._fire(self._value)
    def reset(self):
        if not self._disabled and self.default is not None and self.index_of(self.default) >= 0:
            self._choose(self.index_of(self.default))
    def _cells(self, w, h):
        m = self.L + self.R
        x0, y0, x1 = m, (h - self.bh) // 2, w - m - self._tag_w()
        n = len(self.options)
        L = self.L
        cw = (x1 - x0 - L * (n - 1)) / n
        return [(int(round(x0 + i * (cw + L))), int(round(x0 + i * (cw + L) + cw))) for i in range(n)], y0
    def _at(self, x):
        cells, _ = self._cells(*self._size())
        for i, (a, b) in enumerate(cells):
            if a - self.L // 2 <= x < b + self.L // 2 + 1:
                return i
        return -1
    def _motion(self, e):
        i = self._at(e.x) if not self._disabled else -1
        if i != self._hot:
            self._hot = i
            self.redraw()
    def _on_leave(self, e=None):
        self._hot = -1
        super()._on_leave(e)
    def _press(self, e):
        if self._disabled:
            return
        self._grab_focus()
        i = self._at(e.x)
        if i >= 0:
            self._choose(i)
    def _key(self, d):
        if self._disabled:
            return "break"
        self._keyed()
        i = self.index_of()
        i = (0 if d > 0 else len(self.options) - 1) if i < 0 else max(0, min(len(self.options) - 1, i + d))
        self._choose(i)
        return "break"
    def _draw(self, w, h):
        cells, y0 = self._cells(w, h)
        y1 = y0 + self.bh
        dis = self._disabled
        self.ring(cells[0][0], y0, cells[-1][1], y1)
        self.rect(cells[0][0] - self.L, y0 - self.L, cells[-1][1] + self.L, y1 + self.L, LINE)
        sel = self.index_of()
        f = font("value")
        if self.custom:
            a, b = cells[-1][1] + self.L + px(14), w - self.L - self.R
            c = TEXT_OFF if dis else AMBER
            self.rect(a, y0 - _lw(2), b, y1 + _lw(2), c)
            self.rect(a + _lw(2), y0, b - _lw(2), y1, mix(self.bg, c, 0.10))
            self.text((a + b) // 2, (y0 + y1) // 2, self._tag_text(), f, c, anchor="center")
        for i, (a, b) in enumerate(cells):
            lab = _fit(f, spaced(self.options[i][1]), b - a - px(8))
            if i == sel:
                if dis:
                    self.rect(a, y0, b, y1, mix(TRACK, TEXT_OFF, 0.5))
                    col = TRACK
                else:
                    self.grad(a, y0, b, y1, self.accent, (1.12 if self._hot == i else 1.0) * (0.55 + 0.45 * self._lit))
                    col = ON_FILL
            else:
                hot = self._hot == i and not dis
                self.rect(a, y0, b, y1, mix(TRACK, TEXT, 0.07) if hot else TRACK)
                col = TEXT_OFF if dis else (TEXT if hot else TEXT_DIM)
            self.text((a + b) // 2, (y0 + y1) // 2, lab, f, col, anchor="center")
class KeyCap(_Widget):
    CAPTURE_S = 10.0
    def __init__(self, parent, value="none", default=None, width=None, vk=None, command=None, tip=None, bg=None):
        self._value = self._committed = value
        self.default = default
        self._vk = vk
        self._own_vk = vk is not None
        self._state, self._note = None, None
        self._cap = None
        self._cap_t = 0.0
        self._poll_id = None
        self._dbl_t = 0.0
        self.bw, self.bh = width or px(116), px(34)
        m = _lw(3) + _lw(2)
        super().__init__(parent, self.bw + 2 * m, self.bh + 2 * m, bg, tip)
        if command:
            self.on_change(command)
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<KeyPress>", self._keypress)
        self.bind("<KeyRelease>", lambda e: "break" if self._cap else None)
        self.bind("<FocusOut>", lambda e: self.cancel(), add="+")
        self.bind("<Destroy>", lambda e: self._stop_poll(), add="+")
    def get(self):
        return self._value
    def set(self, value, animate=True):
        self._value = self._committed = value
        self.redraw()
    def set_default(self, v):
        self.default = v
    def set_state(self, state=None, note=None):
        self._state, self._note = state, note
        self.redraw()
    def _tip(self):
        if self._note and not self._disabled:
            base = super()._tip()
            return f"{self._note}\n{base}" if base else self._note
        return super()._tip()
    def reset(self):
        if not self._disabled and self.default is not None:
            self._commit(self.default)
    def _commit(self, v):
        self._value = v
        self.redraw()
        if str(v).upper() != str(self._committed).upper():
            self._committed = v
            self._fire(v)
    @property
    def custom(self):
        n = str(self._value or "").strip()
        if n.lower() in ("", "none", "off", "no", "-"):
            return False
        if not self._own_vk:
            try:
                import settings
                return settings.key_code(n) is None
            except Exception:
                return False
        return n.upper() not in self._table()
    @property
    def capturing(self):
        return self._cap is not None
    def _table(self):
        if self._vk is None:
            try:
                import settings
                self._vk = dict(settings.VK)
            except Exception:
                self._vk = {}
        return self._vk
    def start_capture(self):
        if self._disabled or self._cap:
            return
        self._grab_focus()
        self._cap, self._cap_t = "wait", time.perf_counter()
        ANIM.add(self, "pulse", lambda now: (self.redraw(), self._cap is not None)[1])
        self._poll()
    def cancel(self):
        if self._cap:
            self._cap = None
            self._stop_poll()
            self.redraw()
    def _stop_poll(self):
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
    def _poll(self):
        self._poll_id = None
        if not self._cap:
            return
        table = self._table()
        downs = [n for n, vk in table.items() if _key_down(vk)]
        esc, click = _key_down(0x1B), _key_down(0x01)
        if self._cap == "wait":
            if not downs and not esc and not click:
                self._cap = "armed"
        elif esc or click or time.perf_counter() - self._cap_t > self.CAPTURE_S:
            self.cancel()
            return
        elif downs:
            self._cap = None
            self.redraw()
            if "DELETE" in downs:
                self._commit("none")
                return
            plain = [n for n in downs if n not in _MODS and n not in _GENERIC]
            pick = plain[0] if plain else _MODS.get(downs[0], downs[0])
            self._commit(_MODS.get(pick, pick))
            return
        self._poll_id = self.after(16, self._poll)
    def _double(self, e=None):
        self._dbl_t = time.perf_counter()
        self.cancel()
        self.reset()
    def _click(self, e):
        if self._disabled or time.perf_counter() - self._dbl_t < 0.4:
            return
        if self._inside(e):
            self.start_capture()
    def _keypress(self, e):
        if self._cap:
            return "break"
        if self._disabled:
            return None
        if e.keysym in ("Return", "space"):
            self._keyed()
            self.start_capture()
            return "break"
        if e.keysym in ("Delete", "BackSpace"):
            self._keyed()
            self._commit("none")
            return "break"
        return None
    def _draw(self, w, h):
        m = self.L + self.R
        x0, y0 = m, (h - self.bh) // 2
        x1, y1 = x0 + self.bw, y0 + self.bh
        dis = self._disabled
        now = time.perf_counter()
        cap = self._cap is not None
        self.ring(x0, y0, x1, y1)
        line = LINE
        if cap:
            line = mix(LINE, ORANGE, _pulse(now))
        elif self._state == "block" and not dis:
            line = RED
        elif (self._state == "warn" or self.custom) and not dis:
            line = mix(LINE, AMBER, 0.75)
        self.rect(x0 - self.L, y0 - self.L, x1 + self.L, y1 + self.L, line)
        face = mix(HOVER, TEXT, 0.06) if self._hover and not dis else HOVER
        if cap:
            face = mix(HOVER, ORANGE, 0.14 * _pulse(now))
        self.rect(x0, y0, x1, y1, face)
        lip = _lw(3)
        self.rect(x0, y0, x1, y0 + _lw(2), mix(face, TEXT, 0.22 if not dis else 0.06))
        self.rect(x0, y1 - lip, x1, y1, mix(face, LINE, 0.55))
        if cap:
            t, col = spaced("press a key"), mix(ORANGE, "#FFFFFF", 0.25 * _pulse(now))
        else:
            name = str(self._value or "none")
            t = spaced(key_label(name))
            unset = name.strip().lower() in ("none", "", "off", "-")
            col = TEXT_OFF if dis else (RED if self._state == "block" else
                                        (AMBER if self.custom else (TEXT_DIM if unset else TEXT)))
        f = font("value")
        self.text((x0 + x1) // 2, (y0 + y1 - lip) // 2 + _lw(1), _fit(f, t, self.bw - px(10)), f, col,
                  anchor="center")
        if self._state == "warn" and not cap and not dis:
            c = px(9)
            self.create_polygon(x1 - c, y0, x1, y0, x1, y0 + c, fill=AMBER, outline="")
_MODS = {"LSHIFT": "SHIFT", "RSHIFT": "SHIFT", "LCTRL": "CTRL", "RCTRL": "CTRL", "LALT": "ALT", "RALT": "ALT"}
_GENERIC = ("SHIFT", "CTRL", "ALT")
class Button(_Widget):
    def __init__(self, parent, text, command=None, kind="normal", accent=None, width=None, height=None, tip=None,
                 bg=None):
        self.label = text
        self.kind = kind
        self.accent = accent or ("white" if kind == "primary" else None)
        self.command = command
        self._busy = False
        self._busy_t = 0.0
        f = font("card" if kind == "primary" else "value")
        self.bh = height or px(44 if kind == "primary" else 36)
        m = _lw(3) + _lw(2)
        bw = width or f.measure(spaced(text)) + px(44 if kind != "ghost" else 16)
        super().__init__(parent, bw + 2 * m, self.bh + 2 * m, bg, tip)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<KeyPress-Return>", self._keypress)
        self.bind("<KeyPress-space>", self._keypress)
    def set_text(self, text):
        self.label = text
        self.redraw()
    def set_busy(self, flag):
        self._busy = bool(flag)
        if flag:
            self._busy_t = time.perf_counter()
            ANIM.add(self, "busy", lambda now: (self.redraw(), self._busy)[1])
        self.redraw()
    def invoke(self):
        if not self._disabled and not self._busy and self.command:
            self.command()
    def _press(self, e):
        if self._disabled or self._busy:
            return
        self._grab_focus()
        self._pressed = True
        self.redraw()
    def _release(self, e):
        if not self._pressed:
            return
        self._pressed = False
        self.redraw()
        if self._inside(e):
            self.invoke()
    def _keypress(self, e):
        if not self._disabled:
            self._keyed()
            self.invoke()
        return "break"
    def _body(self, w, h):
        m = self.L + self.R
        return m, (h - self.bh) // 2 + self.L, w - m, (h + self.bh) // 2 - self.L
    def _draw(self, w, h):
        x0, y0, x1, y1 = self._body(w, h)
        dis, hov, prs = self._disabled, self._hover and not self._disabled, self._pressed
        kind = self.kind
        dy = _lw(1) if prs else 0
        if kind != "ghost":
            self.ring(x0, y0, x1, y1)
            edge = LINE
            if kind == "danger" and hov:
                edge = mix(LINE, RED, 0.7)
            self.rect(x0 - self.L, y0 - self.L, x1 + self.L, y1 + self.L, edge)
        else:
            if self._focus and self._ring:
                self.rect(x0, y1 - _lw(2), x1, y1, TEXT)
        f = font("card" if kind == "primary" else "value")
        k = (1.12 if hov else 1.0) * (0.9 if prs else 1.0)
        if kind == "primary":
            if dis:
                self.rect(x0, y0, x1, y1, mix(TRACK, TEXT_OFF, 0.4))
                col = TRACK
            else:
                self.grad(x0, y0, x1, y1, self.accent, k * (0.8 if self._busy else 1.0))
                col = ON_FILL
        elif kind == "ghost":
            col = TEXT_OFF if dis else (TEXT if hov else TEXT_DIM)
            if self.accent and not dis:
                col = _accent(self.accent)[1] if hov else mix(_accent(self.accent)[1], self.bg, 0.25)
        else:
            face = HOVER if not hov else mix(HOVER, TEXT, 0.07)
            if prs:
                face = _gain(face, 0.9)
            self.rect(x0, y0, x1, y1, face)
            if not dis:
                self.rect(x0, y0, x1, y0 + _lw(1), mix(face, TEXT, 0.12 if not hov else 0.22))
            if kind == "danger":
                col = TEXT_OFF if dis else (mix(RED, "#FFFFFF", 0.25) if hov else RED)
            else:
                col = TEXT_OFF if dis else TEXT
            if self.accent and not dis:
                self.grad(x0, y0, x0 + _lw(4), y1, self.accent, k)
        if self._busy:
            col = mix(col, self.bg if kind == "ghost" else (TRACK if kind == "primary" else HOVER), 0.35)
        self.text((x0 + x1) // 2, (y0 + y1) // 2 + dy, _fit(f, spaced(self.label), x1 - x0 - px(12)), f, col,
                  anchor="center")
        if self._busy and kind != "ghost":
            self._shimmer(x0, y1 - _lw(3), x1, y1)
    def _shimmer(self, x0, y0, x1, y1):
        now = time.perf_counter()
        u = ((now - self._busy_t) * 0.9) % 1.4 - 0.2
        n = 24
        base = _accent(self.accent)[0] if self.kind == "primary" else HOVER
        hi = "#FFFFFF" if self.kind == "primary" else _accent(self.accent or "info")[1]
        for i in range(n):
            t = (i + 0.5) / n
            a = math.exp(-((t - u) / 0.14) ** 2)
            self.rect(x0 + (x1 - x0) * i // n, y0, x0 + (x1 - x0) * (i + 1) // n, y1, mix(base, hi, min(1.0, a)))
class HoldButton(Button):
    def __init__(self, parent, text, command=None, hold=0.8, hold_text="HOLD TO CONFIRM", kind="danger",
                 accent=None, width=None, height=None, tip=None, bg=None):
        self.hold = float(hold)
        self.hold_text = hold_text
        self._prog = 0.0
        self._holding = False
        self._t = 0.0
        self._done_t = None
        self._rel_after = None
        f = font("value")
        width = width or max(f.measure(spaced(text)), f.measure(spaced(hold_text))) + px(44)
        super().__init__(parent, text, command, kind, accent, width, height, tip, bg)
        self.unbind("<KeyPress-Return>")
        self.unbind("<KeyPress-space>")
        for k in ("Return", "space"):
            self.bind(f"<KeyPress-{k}>", self._kdown)
            self.bind(f"<KeyRelease-{k}>", self._kup)
        self.bind("<Leave>", lambda e: self._let_go(), add="+")
        self.bind("<FocusOut>", lambda e: self._let_go(), add="+")
    @property
    def progress(self):
        return self._prog
    def _start(self):
        if self._disabled or self._busy or self._holding:
            return
        self._holding = True
        self._done_t = None
        self._t = time.perf_counter()
        ANIM.add(self, "hold", self._step)
        self.redraw()
    def _let_go(self):
        if self._holding:
            self._holding = False
            self._pressed = False
            self._t = time.perf_counter()
            ANIM.add(self, "hold", self._step)
    def _step(self, now):
        dt = min(0.1, now - self._t)
        self._t = now
        if self._done_t is not None:
            self.redraw()
            if now - self._done_t > 0.35:
                self._done_t = None
                self._prog = 0.0
                self.redraw()
                return False
            return True
        if self._holding:
            self._prog = min(1.0, self._prog + dt / max(0.05, self.hold))
            if self._prog >= 1.0:
                self._holding = False
                self._pressed = False
                self._done_t = now
                self.redraw()
                if self.command:
                    self.command()
                return True
        else:
            self._prog = max(0.0, self._prog - dt / 0.2)
        self.redraw()
        return self._holding or self._prog > 0.0
    def _press(self, e):
        if self._disabled or self._busy:
            return
        self._grab_focus()
        self._pressed = True
        self._start()
    def _release(self, e):
        self._pressed = False
        self._let_go()
        self.redraw()
    def _kdown(self, e):
        if self._rel_after:
            self.after_cancel(self._rel_after)
            self._rel_after = None
        if not self._disabled:
            self._keyed()
            self._start()
        return "break"
    def _kup(self, e):
        if self._rel_after:
            self.after_cancel(self._rel_after)
        self._rel_after = self.after(40, self._kup_now)
        return "break"
    def _kup_now(self):
        self._rel_after = None
        self._let_go()
    def invoke(self):
        pass
    def _hold_mark(self, x0, y0, x1, y1):
        f = font("value")
        lw = f.measure(_fit(f, spaced(self.label), x1 - x0 - px(12)))
        gw, gh, L = px(16), max(4, px(6)), _lw(2)
        gx1 = x1 - px(10)
        gx0 = gx1 - gw
        if gx0 - L - px(6) < (x0 + x1 + lw) // 2:
            return
        cy = (y0 + y1) // 2
        self.rect(gx0 - L, cy - gh // 2 - L, gx1 + L, cy - gh // 2 + gh + L, LINE)
        self.rect(gx0, cy - gh // 2, gx1, cy - gh // 2 + gh, TRACK)
        if not self._disabled:
            self.grad(gx0, cy - gh // 2, gx0 + gw * 2 // 5, cy - gh // 2 + gh, "reverse", 0.9)
    def _draw(self, w, h):
        label = self.label
        if self._holding or self._prog > 0.0 and self._done_t is None:
            self.label = self.hold_text
        super()._draw(w, h)
        self.label = label
        x0, y0, x1, y1 = self._body(w, h)
        if self.hold >= 0.3 and self._prog <= 0.0:
            self._hold_mark(x0, y0, x1, y1)
        if self._prog > 0.0 and not self._disabled:
            xf = x0 + int((x1 - x0) * self._prog)
            flash = 0.0
            if self._done_t is not None:
                flash = max(0.0, 1.0 - (time.perf_counter() - self._done_t) / 0.35)
            self.grad(x0, y0, xf, y1, "reverse", 1.0 + 0.25 * flash)
            f = font("value")
            t = spaced(self.hold_text if self._done_t is None else self.label)
            self.text((x0 + x1) // 2, (y0 + y1) // 2, _fit(f, t, x1 - x0 - px(12)), f, "#FFFFFF", anchor="center")
class RailItem(_Widget):
    def __init__(self, parent, text, command=None, accent=None, selected=False, width=None, tip=None, bg=None):
        self.label = text
        self.command = command
        self.accent = accent
        self.selected = selected
        self.badge = None
        super().__init__(parent, width or px(208), px(44), bg, tip)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<ButtonPress-1>", lambda e: self._grab_focus())
        self.bind("<KeyPress-Return>", self._keypress)
        self.bind("<KeyPress-space>", self._keypress)
        self.bind("<KeyPress-Up>", lambda e: self._move(-1))
        self.bind("<KeyPress-Down>", lambda e: self._move(1))
    def set_selected(self, flag):
        self.selected = bool(flag)
        self.redraw()
    def set_badge(self, colour=None):
        self.badge = colour
        self.redraw()
    def _release(self, e):
        if not self._disabled and self._inside(e) and self.command:
            self.command()
    def _keypress(self, e):
        if not self._disabled and self.command:
            self._keyed()
            self.command()
        return "break"
    def _move(self, d):
        items = [w for w in self.master.winfo_children() if isinstance(w, RailItem) and not w.disabled]
        if self in items:
            nxt = items[(items.index(self) + d) % len(items)]
            nxt._ring = True
            nxt.focus_set()
            nxt._ring = True
        return "break"
    def _draw(self, w, h):
        dis, hov, sel = self._disabled, self._hover and not self._disabled, self.selected
        if sel:
            self.rect(0, 0, w, h, SELECTED)
            self.rect(0, 0, _lw(3), h, STRIP)
        elif hov:
            self.rect(0, 0, w, h, HOVER)
        if self._focus and self._ring:
            L = _lw(2)
            self.rect(0, 0, w, L, TEXT)
            self.rect(0, h - L, w, h, TEXT)
            self.rect(w - L, 0, w, h, TEXT)
            self.rect(0, 0, L, h, TEXT)
        acc = self.accent
        accs = list(acc) if isinstance(acc, list) else [acc or "white"]
        L, bw, mh = _lw(2), px(5), px(20)
        mx0, my0 = px(24), (h - mh) // 2
        n = len(accs)
        mx1 = mx0 + n * bw + (n - 1) * L
        self.rect(mx0 - L, my0 - L, mx1 + L, my0 + mh + L, LINE)
        for i, a in enumerate(accs):
            xa = mx0 + i * (bw + L)
            if dis:
                self.rect(xa, my0, xa + bw, my0 + mh, TRACK)
            else:
                k = 1.0 if sel or hov else (0.5 if a == "white" else 0.7)
                self._vgrad(xa, my0, xa + bw, my0 + mh, a, k)
        col = TEXT_OFF if dis else (TEXT if sel or hov else TEXT_DIM)
        f = font("card")
        tx = mx0 + px(30)
        self.text(tx, h // 2, _fit(f, spaced(self.label), w - tx - px(30)), f, col)
        if self.badge:
            b = px(8)
            self.rect(w - px(18) - b, h // 2 - b // 2 - L, w - px(18) + L, h // 2 + b // 2 + L, LINE)
            self.rect(w - px(18) - b + L, h // 2 - b // 2, w - px(18), h // 2 + b // 2, _hex(self.badge))
class Chip(_Widget):
    def __init__(self, parent, text, command=None, accent="white", selected=False, small=False, colour=None,
                 width=None, tip=None, bg=None):
        self.FOCUSABLE = command is not None
        self.label, self.command, self.accent = text, command, accent
        self.selected, self.small, self.colour = selected, small, colour
        self._fade = 1.0
        self._flash_t = None
        f = font("badge" if small else "value")
        self.bh = px(20 if small else 28)
        m = _lw(2 if small else 3) + _lw(2)
        bw = width or f.measure(spaced(text)) + px(16 if small else 30)
        super().__init__(parent, bw + 2 * m, self.bh + 2 * m, bg, tip)
        self.L = _lw(2 if small else 3)
        if command:
            self.bind("<ButtonPress-1>", self._press)
            self.bind("<ButtonRelease-1>", self._release)
            self.bind("<KeyPress-Return>", self._keypress)
            self.bind("<KeyPress-space>", self._keypress)
    def set_text(self, text):
        self.label = text
        self.redraw()
    def set_selected(self, flag):
        self.selected = bool(flag)
        self.redraw()
    def flash(self, text=None, hold=1.2, fade=0.6):
        if text is not None:
            self.label = text
        self._fade, self._flash_t = 1.0, time.perf_counter()
        hold, fade = (0.8, 0.0) if REDUCE_MOTION else (hold, fade)
        def step(now):
            t = now - self._flash_t
            self._fade = 1.0 if t < hold else max(0.0, 1.0 - (t - hold) / fade) if fade else 0.0
            self.redraw()
            return self._fade > 0.0
        ANIM.add(self, "flash", step)
        self.redraw()
    def _press(self, e):
        if not self._disabled:
            self._grab_focus()
            self._pressed = True
            self.redraw()
    def _release(self, e):
        if not self._pressed:
            return
        self._pressed = False
        self.redraw()
        if self._inside(e) and not self._disabled:
            self.command()
    def _keypress(self, e):
        if not self._disabled:
            self._keyed()
            self.command()
        return "break"
    def _draw(self, w, h):
        if self._fade <= 0.0:
            return
        m = self.L + self.R
        x0, y0, x1, y1 = m, (h - self.bh) // 2, w - m, (h + self.bh) // 2
        dis, hov = self._disabled, self._hover and not self._disabled and self.command
        f = font("badge" if self.small else "value")
        t = _fit(f, spaced(self.label), x1 - x0 - px(8))
        a = self._fade
        if self.command is None:
            col = _hex(self.colour) if self.colour else TEXT_DIM
            self.rect(x0 - self.L, y0 - self.L, x1 + self.L, y1 + self.L, mix(self.bg, col, 0.85 * a))
            self.rect(x0, y0, x1, y1, mix(self.bg, col, 0.10 * a))
            self.text((x0 + x1) // 2, (y0 + y1) // 2, t, f, mix(self.bg, col, a), anchor="center")
            return
        self.ring(x0, y0, x1, y1)
        self.rect(x0 - self.L, y0 - self.L, x1 + self.L, y1 + self.L, LINE)
        if self.selected and not dis:
            self.grad(x0, y0, x1, y1, self.accent, (1.12 if hov else 1.0) * (0.9 if self._pressed else 1.0))
            col = ON_FILL
        else:
            self.rect(x0, y0, x1, y1, mix(TRACK, TEXT, 0.07) if hov else TRACK)
            col = TEXT_OFF if dis else (TEXT if hov else TEXT_DIM)
            if not dis:
                self.rect(x0, y1 - _lw(2), x1, y1, mix(TRACK, _accent(self.accent)[1], 0.55 if hov else 0.3))
        self.text((x0 + x1) // 2, (y0 + y1) // 2 + (_lw(1) if self._pressed else 0), t, f, col, anchor="center")
class BandMeter(_Widget):
    FOCUSABLE = False
    def __init__(self, parent, value=0.0, accent="throttle", width=None, height=None, sections=0, pulse=False,
                 hot=None, inward=None, tip=None, bg=None):
        self._value = float(value)
        self._shown = self._value
        self._t = 0.0
        self.accent, self.sections = accent, int(sections)
        self.hot, self.pulsing = hot, pulse
        self.inward = (accent == "sonic") if inward is None else inward
        self.bh = height or px(14)
        m = _lw(3) + 1
        super().__init__(parent, width or px(240), self.bh + 2 * m, bg, tip)
        if pulse:
            self.set_pulse(True)
    def get(self):
        return self._value
    def set(self, value, animate=True):
        self._value = max(0.0, min(1.0, float(value)))
        if not animate or REDUCE_MOTION:
            self._shown = self._value
            self.redraw()
        else:
            self._t = time.perf_counter()
            ANIM.add(self, "ease", self._step)
    def _step(self, now):
        self._shown = _ease(self._shown, self._value, now - self._t)
        self._t = now
        done = abs(self._shown - self._value) < 0.002
        if done:
            self._shown = self._value
        self.redraw()
        return not done
    def set_pulse(self, flag):
        self.pulsing = bool(flag)
        if flag and not REDUCE_MOTION:
            ANIM.add(self, "pulse", lambda now: (self.redraw(), self.pulsing)[1])
        else:
            ANIM.remove(self, "pulse")
            self.redraw()
    def set_hot(self, span):
        self.hot = span
        self.redraw()
    def _draw(self, w, h):
        L = self.L
        x0, y0, x1, y1 = L + 1, (h - self.bh) // 2, w - L - 1, (h + self.bh) // 2
        self.box(x0, y0, x1, y1, TRACK)
        k = _pulse(time.perf_counter()) if self.pulsing else 1.0
        xf = x0 + int(round((x1 - x0) * self._shown))
        if self._disabled:
            self.rect(x0, y0, xf, y1, mix(TRACK, TEXT_OFF, 0.45))
        else:
            self.grad(x0, y0, xf, y1, self.accent, k, self.inward)
            if self.hot:
                a, b = self.hot
                self.grad(x0 + int((x1 - x0) * a), y0, x0 + int((x1 - x0) * b), y1, "hot",
                          0.97 + 0.08 * math.sin(time.perf_counter() * 18.0), True)
        for j in range(1, self.sections):
            xd = x0 + int(round((x1 - x0) * j / self.sections))
            self.rect(xd - L // 2, y0, xd - L // 2 + L, y1, LINE)
LIGHT_COLOURS = {"ok": ACCENTS["throttle"], "warn": (ORANGE, "#FFC070"), "bad": ACCENTS["reverse"],
                 "busy": ACCENTS["info"], "off": (TEXT_OFF, TEXT_OFF)}
class Light(_Widget):
    FOCUSABLE = False
    def __init__(self, parent, label, state="off", fix="", width=None, command=None, tip=None, bg=None):
        self.label, self.state, self.fix = label, state, fix
        self.command = command
        self._link_hover = False
        super().__init__(parent, width or px(300), px(44), bg, tip, cursor="")
        if command:
            self.bind("<Motion>", self._motion)
            self.bind("<ButtonRelease-1>", self._click)
        self.set(state)
    def set(self, state=None, label=None, fix=None):
        if state is not None:
            self.state = state
        if label is not None:
            self.label = label
        if fix is not None:
            self.fix = fix
        if self.state == "busy" and not REDUCE_MOTION:
            ANIM.add(self, "pulse", lambda now: (self.redraw(), self.state == "busy")[1])
        self.redraw()
    def get(self):
        return self.state
    def _on_fix(self, e):
        f = font("help")
        x = px(30)
        return self.command and self.fix and x <= e.x <= x + f.measure(self.fix) and e.y > self._size()[1] * 0.55
    def _motion(self, e):
        on = bool(self._on_fix(e))
        if on != self._link_hover:
            self._link_hover = on
            self.configure(cursor="hand2" if on else "")
            self.redraw()
    def _on_leave(self, e=None):
        self._link_hover = False
        super()._on_leave(e)
    def _click(self, e):
        if self._on_fix(e):
            self.command()
    def _draw(self, w, h):
        e, m = LIGHT_COLOURS.get(self.state, LIGHT_COLOURS["off"])
        k = _pulse(time.perf_counter(), 5.0) if self.state == "busy" else 1.0
        s, L = px(12), _lw(2)
        two = bool(self.fix)
        cy = px(14) if two else h // 2
        lx, ly = px(4) + L * 2, cy - s // 2
        if self.state not in ("off",):
            g = _lw(3)
            self.rect(lx - L - g, ly - L - g, lx + s + L + g, ly + s + L + g, mix(self.bg, m, 0.16 * k))
        self.rect(lx - L, ly - L, lx + s + L, ly + s + L, LINE)
        if self.state == "off":
            self.rect(lx, ly, lx + s, ly + s, TRACK)
        else:
            self.grad(lx, ly, lx + s, ly + s, (e, m), 0.75 + 0.25 * k)
        f = font("value")
        tx = px(30)
        self.text(tx, cy, _fit(f, spaced(self.label), w - tx - px(4)), f, TEXT if self.state != "off" else TEXT_DIM)
        if two:
            fh = font("help")
            col = {"bad": RED, "warn": ORANGE}.get(self.state, TEXT_DIM)
            if self._link_hover:
                col = mix(col, "#FFFFFF", 0.35)
            t = _fit(fh, self.fix, w - tx - px(4))
            self.text(tx, px(33), t, fh, col, caps=False)
            if self.command:
                y = px(33) + fh.metrics("descent") + px(4)
                self.rect(tx, y, tx + fh.measure(t), y + _lw(1), mix(self.bg, col, 0.8 if self._link_hover else 0.4))
class Card(_Widget):
    FOCUSABLE = False
    def __init__(self, parent, title=None, accent=None, sections=0, badge=None, width=None, pad=16, bg=None,
                 tip=None):
        self.title, self.accent, self.sections, self.badge = title, accent, sections, badge
        self.pad = px(pad)
        self._head_w = None
        super().__init__(parent, width or px(480), px(80), bg, tip, cursor="")
        L, strip = self.L, _lw(3)
        self.bx = L + strip + self.pad
        self.by = L + self.pad + (px(38) if title else 0)
        self.body = tk.Frame(self, bg=CARD, highlightthickness=0, bd=0)
        self._win = self.create_window(self.bx, self.by, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._fit_body, add="+")
        self.bind("<Configure>", self._fit_width, add="+")
    def set_badge(self, text):
        self.badge = text
        self.redraw()
    def set_title(self, text):
        self.title = text
        self.redraw()
    def header(self, widget):
        self._head_w = widget
        self.redraw()
        return widget
    def _fit_body(self, e=None):
        h = self.by + self.body.winfo_reqheight() + self.pad + self.L
        w = self.bx + self.body.winfo_reqwidth() + self.pad + self.L
        if int(self.cget("height")) != h:
            self.configure(height=h)
        if int(self.cget("width")) < w:
            self.configure(width=w)
    def _fit_width(self, e=None):
        w = self.winfo_width()
        bw = max(1, w - self.bx - self.pad - self.L)
        self.itemconfigure(self._win, width=bw)
    def redraw(self):
        try:
            for i in self.find_all():
                if self.type(i) != "window":
                    self.delete(i)
            w, h = self._size()
            self._draw(w, h)
            if self._head_w is not None:
                self.delete("head")
                hh = self._head_w.winfo_reqheight()
                ry = self.L + self.pad + px(28)
                cy = max(self.L + (hh + 1) // 2, min(self.L + self.pad + px(14), ry - _lw(1) - (hh + 1) // 2))
                self.create_window(w - self.L - self.pad, cy, window=self._head_w, anchor="e", tags="head")
        except tk.TclError:
            pass
    def _draw(self, w, h):
        L, strip = self.L, _lw(3)
        self.rect(0, 0, w, h, LINE)
        self.rect(L, L, w - L, h - L, CARD)
        self.rect(L, L, L + strip, h - L, STRIP)
        if not self.title:
            return
        x, y = self.bx, L + self.pad + px(12)
        f = font("card")
        t = spaced(self.title)
        self.text(x, y, t, f, TEXT if not self._disabled else TEXT_OFF)
        x += f.measure(t) + px(16)
        if self.accent:
            bw, bh = px(92), px(8)
            self.box(x + L, y - bh // 2, x + L + bw, y + bh // 2, None)
            self.grad(x + L, y - bh // 2, x + L + bw, y + bh // 2, self.accent, 1.0, self.accent == "sonic")
            for j in range(1, int(self.sections)):
                xd = x + L + round(bw * j / self.sections)
                self.rect(xd - L // 2, y - bh // 2, xd - L // 2 + L, y + bh // 2, LINE)
        if self.badge and self._head_w is None:
            fb = font("badge")
            self.text(w - L - self.pad, y, spaced(self.badge), fb, TEXT_DIM, anchor="e")
        ry = L + self.pad + px(28)
        self.rect(self.bx, ry, w - L - self.pad, ry + _lw(1), mix(CARD, TEXT, 0.22))
class InlineStrip(_Widget):
    FOCUSABLE = False
    def __init__(self, parent, kind="info", width=None, bg=None):
        self.kind = kind
        self.msg = ""
        self.actions = []
        self.closable = True
        self._open = 0.0
        self._target = 0.0
        self._t = 0.0
        self._timer = None
        self._hot = -1
        self.full = px(42)
        super().__init__(parent, width or px(600), 1, bg, cursor="")
        self.configure(height=0)
        self.bind("<Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._click)
    @property
    def shown(self):
        return self._target > 0.0
    def show(self, text, kind=None, actions=(), timeout=None, close=True):
        self.msg, self.actions, self.closable = text, list(actions), close
        if kind:
            self.kind = kind
        self._slide(1.0)
        self._cancel_timer()
        if timeout:
            self._timer = self.after(int(timeout * 1000), self.hide)
        self.redraw()
    def hide(self):
        self._cancel_timer()
        self._slide(0.0)
    def _cancel_timer(self):
        if self._timer:
            try:
                self.after_cancel(self._timer)
            except tk.TclError:
                pass
            self._timer = None
    def _slide(self, target):
        self._target = target
        if REDUCE_MOTION:
            self._open = target
            self.configure(height=int(self.full * target))
            self.redraw()
            return
        self._t = time.perf_counter()
        ANIM.add(self, "slide", self._step)
        if target > 0 and self._open == 0.0:
            self._open = 0.05
            self.configure(height=max(1, int(self.full * self._open)))
    def _step(self, now):
        self._open = _ease(self._open, self._target, now - self._t, 0.05)
        self._t = now
        done = abs(self._open - self._target) < 0.02
        if done:
            self._open = self._target
        self.configure(height=int(round(self.full * self._open)))
        self.redraw()
        return not done
    def _spots(self, w):
        f = font("value")
        x = w - px(14)
        out = []
        if self.closable:
            out.append((x - px(16), x))
            x -= px(16) + px(18)
        for lab, _ in reversed(self.actions):
            tw = f.measure(spaced(lab))
            out.append((x - tw, x))
            x -= tw + px(22)
        return list(reversed(out))
    def _at(self, x):
        for i, (a, b) in enumerate(self._spots(self._size()[0])):
            if a - px(6) <= x <= b + px(6):
                return i
        return -1
    def _motion(self, e):
        i = self._at(e.x)
        if i != self._hot:
            self._hot = i
            self.configure(cursor="hand2" if i >= 0 else "")
            self.redraw()
    def _click(self, e):
        i = self._at(e.x)
        if i < 0:
            return
        if i < len(self.actions):
            self.actions[i][1]()
        else:
            self.hide()
    def _draw(self, w, h):
        if h < 2:
            return
        col = KIND_COLOUR.get(self.kind, INFO)
        full = self.full
        top = h - full
        L = self.L
        self.rect(0, top, w, h, LINE)
        self.rect(L, top + L, w - L, h - L, mix(CARD, col, 0.10))
        self.rect(L, top + L, L + _lw(4), h - L, col)
        cy = top + full // 2
        spots = self._spots(w)
        tx1 = (spots[0][0] - px(18)) if spots else w - px(14)
        f = font("label")
        self.text(L + _lw(4) + px(12), cy, _fit(f, self.msg, tx1 - px(24)), f, TEXT, caps=False)
        fv = font("value")
        for i, (a, b) in enumerate(spots):
            hot = i == self._hot
            if i < len(self.actions):
                c = mix(col, "#FFFFFF", 0.35) if hot else col
                self.text(a, cy, spaced(self.actions[i][0]), fv, c)
                self.rect(a, cy + px(10), b, cy + px(10) + _lw(1), mix(CARD, c, 0.8 if hot else 0.35))
            else:
                c = TEXT if hot else TEXT_DIM
                s = px(5)
                xm = (a + b) // 2
                self.create_line(xm - s, cy - s, xm + s + 1, cy + s + 1, fill=c, width=_lw(2))
                self.create_line(xm - s, cy + s, xm + s + 1, cy - s - 1, fill=c, width=_lw(2))
class Toast(InlineStrip):
    def __init__(self, container, width=None):
        super().__init__(container, "ok", width or px(440), bg=_bg_of(container))
        self.container = container
    def show(self, text, kind="ok", action=None, timeout=2.5):
        super().show(text, kind, [action] if action else [], timeout, close=False)
        self._place()
    def _place(self):
        self.place(in_=self.container, relx=1.0, rely=1.0, x=-px(18), y=-px(18), anchor="se")
        tk.Misc.tkraise(self)
    def _step(self, now):
        keep = super()._step(now)
        if not keep and self._target == 0.0:
            self.place_forget()
        return keep
    def hide(self):
        super().hide()
        if REDUCE_MOTION:
            self.place_forget()
class _ScrollBar(_Widget):
    FOCUSABLE = False
    def __init__(self, parent, page):
        self.page = page
        self._drag = None
        super().__init__(parent, px(10), 10, bg=_bg_of(parent), cursor="")
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
    def _thumb(self, h):
        a, b = self.page.canvas.yview()
        if b - a >= 0.999:
            return None
        m = px(4)
        return m + int((h - 2 * m) * a), m + int((h - 2 * m) * b)
    def _press(self, e):
        t = self._thumb(self.winfo_height())
        if not t:
            return
        if t[0] <= e.y <= t[1]:
            self._drag = (e.y, self.page.offset())
        else:
            self.page.scroll_by(self.page.canvas.winfo_height() * 0.9 * (1 if e.y > t[1] else -1))
    def _motion(self, e):
        if self._drag is None:
            return
        y0, off0 = self._drag
        total = self.page.total()
        self.page.scroll_to(off0 + (e.y - y0) * total / max(1, self.winfo_height() - px(8)), animate=False)
    def _draw(self, w, h):
        t = self._thumb(h)
        if not t:
            return
        x0, x1 = px(3), w - px(3)
        self.rect(x0, px(4), x1, h - px(4), mix(self.bg, TRACK, 0.7))
        hot = self._hover or self._drag is not None
        self.rect(x0, t[0], x1, t[1], mix(TRACK, TEXT, 0.45 if hot else 0.22))
class ScrollPage(tk.Frame):
    def __init__(self, parent, bg=BG, padx=24, pady=16):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        self.padx, self.pady = px(padx), px(pady)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=1, takefocus=0)
        self.bar = _ScrollBar(self, self)
        self.body = tk.Frame(self.canvas, bg=bg, highlightthickness=0, bd=0)
        self._win = self.canvas.create_window(self.padx, self.pady, window=self.body, anchor="nw")
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._target = 0.0
        self._t = 0.0
        self._lkey = None
        self.body.bind("<Configure>", self._layout, add="+")
        self.canvas.bind("<Configure>", self._layout, add="+")
        self.canvas.bind("<KeyPress-Prior>", lambda e: self.scroll_by(-self.canvas.winfo_height() * 0.9))
        self.canvas.bind("<KeyPress-Next>", lambda e: self.scroll_by(self.canvas.winfo_height() * 0.9))
    def total(self):
        return self.body.winfo_reqheight() + 2 * self.pady
    def view(self):
        return max(1, self.canvas.winfo_height())
    def offset(self):
        return self.canvas.yview()[0] * self.total()
    def _layout(self, e=None):
        key = (self.canvas.winfo_width(), self.canvas.winfo_height(), self.body.winfo_reqheight())
        if key == self._lkey:
            return
        self._lkey = key
        w = max(1, self.canvas.winfo_width() - 2 * self.padx)
        self.canvas.itemconfigure(self._win, width=w)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.total()))
        self.scroll_to(min(self._target, max(0, self.total() - self.view())), animate=False)
    def _moveto(self, y):
        self.canvas.yview_moveto(y / max(1, self.total()))
        self.canvas.coords(self._win, self.padx, self.pady)
        self.bar.redraw()
    def scroll_to(self, y, animate=True):
        y = max(0.0, min(float(y), max(0, self.total() - self.view())))
        self._target = y
        if not animate or REDUCE_MOTION:
            ANIM.remove(self.canvas, "scroll")
            self._moveto(y)
            return
        self._t = time.perf_counter()
        ANIM.add(self.canvas, "scroll", self._step)
    def scroll_by(self, dy):
        self.scroll_to(self._target + dy)
    def top(self):
        self.scroll_to(0, animate=False)
    def _step(self, now):
        cur = self.offset()
        nxt = _ease(cur, self._target, now - self._t, 0.07)
        self._t = now
        done = abs(nxt - self._target) < 0.75
        if done:
            nxt = self._target
        self._moveto(nxt)
        return not done
    def see(self, widget):
        try:
            y = widget.winfo_rooty() - self.body.winfo_rooty() + self.pady
            h = widget.winfo_height()
        except tk.TclError:
            return
        off, v, m = self._target, self.view(), px(24)
        if y - m < off:
            self.scroll_to(y - m)
        elif y + h + m > off + v:
            self.scroll_to(y + h + m - v)
def _page_of(w):
    while w is not None:
        if isinstance(w, ScrollPage):
            return w
        w = getattr(w, "master", None)
    return None
def _wheel(e):
    try:
        w = e.widget.winfo_containing(e.x_root, e.y_root)
    except (tk.TclError, AttributeError, KeyError):
        return
    page = _page_of(w)
    if page is not None and page.total() > page.view():
        page.scroll_by(-e.delta / 120.0 * px(96))
def _focus_scroll(e):
    w = e.widget
    if isinstance(w, str):
        return
    page = _page_of(getattr(w, "master", None))
    if page is not None and isinstance(w, _Widget) and w._ring:
        page.see(w)
def label(parent, text, style="label", colour=None, wrap=None, bg=None, **kw):
    col = colour or (TEXT_DIM if style == "help" else TEXT)
    return tk.Label(parent, text=text, font=font(style), fg=col, bg=bg or _bg_of(parent), bd=0, padx=0, pady=0,
                    anchor="w", justify="left", wraplength=wrap or 0, **kw)
def capture(root, out, x=None, y=None, settle=0.4, ready=None):
    from PIL import Image
    if not _GUARD or not _GUARD[0].hook or not _GUARD[0].block:
        raise RuntimeError("capture() needs no_activate_guard(True), installed before tk.Tk()")
    mon = rightmost_monitor()
    x = mon[0] + px(24) if x is None else x
    y = mon[1] + px(24) if y is None else y
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.update_idletasks()
    hwnd = int(root.wm_frame(), 16)
    ex = u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    u32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    u32.SetWindowPos(hwnd, None, x, y, w, h, 0x0010 | 0x0004 | 0x0020)
    u32.ShowWindow(hwnd, 4)
    root.deiconify()
    for _ in range(4):
        t_end = time.perf_counter() + settle
        while time.perf_counter() < t_end:
            root.update()
            time.sleep(0.01)
        nw, nh = root.winfo_reqwidth(), root.winfo_reqheight()
        if (nw, nh) == (w, h):
            break
        w, h = nw, nh
        root.geometry(f"{w}x{h}+{x}+{y}")
    if ready:
        ready()
        t_end = time.perf_counter() + 0.15
        while time.perf_counter() < t_end:
            root.update()
            time.sleep(0.01)
    root.update()
    if u32.GetForegroundWindow() == hwnd:
        u32.ShowWindow(hwnd, 0)
        raise OSError("the preview window took the foreground: install no_activate_guard() before tk.Tk()")
    rc = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rc))
    w, h = rc.right - rc.left, rc.bottom - rc.top
    sdc = u32.GetDC(None)
    mdc = g32.CreateCompatibleDC(sdc)
    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]
    bi = BIH(biSize=ctypes.sizeof(BIH), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
    bits = ctypes.c_void_p()
    bmp = g32.CreateDIBSection(mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    old = g32.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, 2)
    data = ctypes.string_at(bits, w * h * 4)
    g32.SelectObject(mdc, old)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(None, sdc)
    u32.ShowWindow(hwnd, 0)
    if not ok:
        raise OSError("PrintWindow failed")
    Image.frombuffer("RGB", (w, h), data, "raw", "BGRX", 0, 1).save(out)
    return w, h
def _gallery(root):
    outer = tk.Frame(root, bg=BG, highlightthickness=0, bd=0)
    outer.pack(fill="both", expand=True)
    head = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0, height=px(52))
    head.pack(fill="x")
    head.create_rectangle(0, 0, _lw(3), px(52), fill=STRIP, outline="")
    cx, cy, r = px(28), px(26), px(8)
    head.create_polygon(cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy, outline=TEXT, fill="", width=_lw(2))
    q = r * 0.45
    head.create_polygon(cx, cy - q, cx + q, cy, cx, cy + q, cx - q, cy, fill=TEXT, outline="")
    head.create_text(px(48), _caps_y(font("head"), cy), text=spaced("suit control") + "   " +
                     spaced("widget kit"), font=font("head"), fill=TEXT, anchor="w")
    head.create_text(px(380), _caps_y(font("help"), cy), anchor="w", fill=TEXT_DIM, font=font("help"),
                     text=f"panel_widgets.py  //  every widget, every state  //  scale {SCALE:.2f}")
    grid = tk.Frame(outer, bg=BG)
    grid.pack(fill="both", expand=True, padx=px(16), pady=(0, px(16)))
    cols = [tk.Frame(grid, bg=BG) for _ in range(4)]
    for i, c in enumerate(cols):
        c.grid(row=0, column=i, sticky="n", padx=px(6))
    def card(col, title, **kw):
        c = Card(cols[col], title, width=px(440 if col else 300), **kw)
        c.pack(fill="x", pady=px(6))
        return c.body
    def cap(parent, text, row, col=0):
        label(parent, text, "help").grid(row=row, column=col, sticky="w", pady=(px(4), 0))
    def put(w, row, col=1, **kw):
        w.grid(row=row, column=col, sticky="w", padx=(px(10), 0), pady=px(2), **kw)
        return w
    rail = tk.Frame(cols[0], bg=BG)
    rail.pack(fill="x", pady=px(6))
    items = [("home", None), ("flight", "throttle"), ("powers", ["burner", "sonic", "cruise"]), ("sound", None),
             ("visuals", "amber"), ("controls", None), ("about", None)]
    made = {}
    for name, acc in items:
        ri = RailItem(rail, name, accent=acc, selected=name == "flight", width=px(300))
        ri.pack(fill="x")
        made[name] = ri
    made["powers"]._hover = True
    made["sound"].set_badge(AMBER)
    made["controls"]._focus = made["controls"]._ring = True
    made["about"].set_disabled(True)
    b = card(0, "status lights")
    Light(b, "game running", "ok", "Build 184271 // supported", width=px(260)).pack(anchor="w")
    Light(b, "game link (mod)", "warn", "Paused: the game is in a menu", width=px(260)).pack(anchor="w")
    Light(b, "mods enabled", "bad", "Turn mods back on: click to fix", width=px(260), command=lambda: None).pack(
        anchor="w")
    Light(b, "suit", "busy", "Starting // take a few steps", width=px(260)).pack(anchor="w")
    Light(b, "controller", "off", width=px(260)).pack(anchor="w")
    b = card(0, "band meters")
    BandMeter(b, 0.62, "throttle", width=px(250)).pack(anchor="w", pady=px(2))
    BandMeter(b, 0.4, "burner", width=px(250), pulse=False).pack(anchor="w", pady=px(2))
    BandMeter(b, 0.67, "sonic", width=px(250), sections=3, hot=(0.33, 0.67)).pack(anchor="w", pady=px(2))
    BandMeter(b, 0.67, "cruise", width=px(250), sections=3).pack(anchor="w", pady=px(2))
    BandMeter(b, 1.0, "reverse", width=px(250)).pack(anchor="w", pady=px(2))
    b = card(1, "slider", accent="throttle")
    rows = [("normal", dict(accent="throttle")), ("hover", dict(accent="burner")),
            ("keyboard focus", dict(accent="sonic")), ("custom (500)", dict(accent="cruise")),
            ("disabled", dict(accent="throttle"))]
    for i, (t, kw) in enumerate(rows):
        cap(b, t, i)
        s = put(Slider(b, 20, 160, 80, 5, default=80, width=px(300), fmt="{} M/S", **kw), i)
        if t == "hover":
            s._hover = True
        if t.startswith("keyboard"):
            s._focus = s._ring = True
        if t.startswith("custom"):
            s.set(500, animate=False)
        if t == "disabled":
            s.set_disabled(True)
        s.redraw()
    cap(b, "decimals", len(rows))
    put(Slider(b, 0.5, 6.0, 2.5, 0.1, default=2.5, width=px(300), fmt="{:.1f} s", accent="white"), len(rows))
    b = card(1, "dual slider")
    cap(b, "range", 0)
    put(DualSlider(b, 1, 160, (5, 80), 1, default=(5, 80), width=px(300), fmt="{}"), 0)
    cap(b, "focus", 1)
    d = put(DualSlider(b, 1, 160, (40, 120), 1, default=(5, 80), width=px(300), accent="info"), 1)
    d._focus = d._ring = True
    d.redraw()
    cap(b, "custom", 2)
    put(DualSlider(b, 1, 160, (5, 300), 1, width=px(300)), 2)
    b = card(1, "toggle")
    for i, (t, v, acc) in enumerate([("on", True, "throttle"), ("off", False, "throttle"), ("hover", True, "info"),
                                     ("focus", False, "amber"), ("disabled on", True, "throttle"),
                                     ("disabled off", False, "throttle")]):
        cap(b, t, i // 2 * 2, (i % 2) * 2)
        g = Toggle(b, v, accent=acc)
        g.grid(row=i // 2 * 2 + 1, column=(i % 2) * 2, sticky="w", pady=px(2), padx=(0, px(30)))
        if t == "hover":
            g._hover = True
        if t == "focus":
            g._focus = g._ring = True
        if t.startswith("disabled"):
            g.set_disabled(True)
        g.redraw()
    b = card(2, "segmented")
    curve = [(1.0, "linear"), (1.6, "balanced"), (2.4, "fine")]
    for i, (t, kw) in enumerate([("normal", dict(value=1.6)), ("accent", dict(value="toggle", accent="burner")),
                                 ("focus + hover", dict(value=1.0)), ("custom (1.9)", dict(value=1.9)),
                                 ("disabled", dict(value=2.4))]):
        cap(b, t, i)
        opts = [("toggle", "toggle"), ("hold", "hold")] if "accent" in kw else curve
        sg = put(Segmented(b, opts, width=px(300) if opts is curve else None, **kw), i)
        if t.startswith("focus"):
            sg._focus = sg._ring = True
            sg._hot = 2
        if t == "disabled":
            sg.set_disabled(True)
        sg.redraw()
    b = card(2, "keycaps")
    keys = [("forward", "W", None), ("afterburner", "SHIFT", None), ("climb", "MOUSE5", None), ("unbound", "none", None),
            ("capturing", "R", "cap"), ("blocked", "SPACE", "block"), ("game key", "F", "warn"), ("focus", "HOME", "focus"),
            ("disabled", "END", "dis")]
    for i, (t, k_, st) in enumerate(keys):
        cap(b, t, i // 3 * 2, i % 3)
        kc = KeyCap(b, k_, width=px(116))
        kc.grid(row=i // 3 * 2 + 1, column=i % 3, sticky="w", pady=(0, px(4)), padx=(0, px(8)))
        if st == "cap":
            kc._cap = "armed"
        elif st in ("block", "warn"):
            kc.set_state(st, "Space is the suit's take-off key" if st == "block" else "The game uses F (visor)")
        elif st == "focus":
            kc._focus = kc._ring = True
        elif st == "dis":
            kc.set_disabled(True)
        kc.redraw()
    b = card(2, "chips and badges")
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w")
    for i, n in enumerate(("classic", "cinematic", "fast", "comfort")):
        c = Chip(row, n, command=lambda: None, selected=i == 0, accent="white")
        c.pack(side="left", padx=(0, px(6)))
        if i == 2:
            c._hover = True
            c.redraw()
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w", pady=(px(8), 0))
    Chip(row, "↻ after restart", small=True, colour=AMBER).pack(side="left", padx=(0, px(6)))
    Chip(row, "applied ✓", small=True, colour=ACCENTS["throttle"][1]).pack(side="left", padx=(0, px(6)))
    Chip(row, "experimental", small=True, colour=ACCENTS["cruise"][1]).pack(side="left", padx=(0, px(6)))
    Chip(row, "saved · applies when the suit starts", small=True).pack(side="left")
    b = card(3, "buttons")
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w")
    Button(row, "power up the suit", kind="primary", accent="throttle").pack(side="left", padx=(0, px(8)))
    Button(row, "relight jets", kind="primary", accent="info").pack(side="left")
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w", pady=(px(8), 0))
    Button(row, "back to game", kind="primary").pack(side="left", padx=(0, px(8)))
    bb = Button(row, "restart hud", kind="primary", accent="burner")
    bb.pack(side="left")
    bb.set_busy(True)
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w", pady=(px(8), 0))
    pb = Button(row, "find my character")
    pb.pack(side="left", padx=(0, px(8)))
    pb._pressed = True
    pb.redraw()
    h_ = Button(row, "repair all")
    h_.pack(side="left", padx=(0, px(8)))
    h_._hover = True
    h_.redraw()
    f_ = Button(row, "relight jets", accent="burner")
    f_.pack(side="left")
    f_._focus = f_._ring = True
    f_.redraw()
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w", pady=(px(8), 0))
    Button(row, "stop", kind="danger").pack(side="left", padx=(0, px(8)))
    dz = Button(row, "find my character")
    dz.pack(side="left", padx=(0, px(8)))
    dz.set_disabled(True, "Land first")
    Button(row, "open folder", kind="ghost").pack(side="left")
    Button(row, "undo", kind="ghost", accent="throttle").pack(side="left")
    b = card(3, "hold to confirm")
    row = tk.Frame(b, bg=CARD)
    row.pack(anchor="w")
    HoldButton(row, "power down", hold_text="hold to power down").pack(side="left", padx=(0, px(8)))
    hb = HoldButton(row, "force stop", hold_text="hold to force stop")
    hb.pack(side="left")
    hb._prog, hb._holding = 0.55, True
    hb.redraw()
    ANIM.remove(hb)
    b = card(3, "afterburner", accent="burner", badge="live")
    cap(b, "thrust", 0)
    put(Slider(b, 1.5, 4.0, 2.4, 0.1, default=2.4, accent="burner", width=px(260), fmt="×{:.1f}"), 0)
    cap(b, "mode", 1)
    put(Segmented(b, [("toggle", "toggle"), ("hold", "hold")], "toggle", accent="burner"), 1)
    b = card(3, "sonic boom", accent="sonic", sections=3, badge="live")
    label(b, "PRESS = 1 BLAST  //  3 PER METER, EACH BIGGER", "help").pack(anchor="w")
    b = card(3, "notices")
    s1 = InlineStrip(b, "error", width=px(400))
    s1.pack(fill="x", pady=(0, px(6)))
    s1.show("Couldn't save: the folder is read-only", actions=[("retry", lambda: None), ("open folder", lambda: None)])
    s2 = InlineStrip(b, "ok", width=px(400))
    s2.pack(fill="x", pady=(0, px(6)))
    s2.show("CINEMATIC applied", actions=[("undo", lambda: None)])
    s4 = InlineStrip(b, "warn", width=px(400))
    s4.pack(fill="x", pady=(0, px(6)))
    s4.show("1 change waits for a restart (motion blur)", actions=[("restart now", lambda: None)], close=False)
    s3 = InlineStrip(b, "info", width=px(400))
    s3.pack(fill="x")
    s3.show("F7 in the game brings this back")
    for s_ in (s1, s2, s3, s4):
        ANIM.remove(s_)
        s_._open = 1.0
        s_.configure(height=s_.full)
    b = card(2, "scroll page + tooltip")
    sp = ScrollPage(b, bg=CARD, padx=8, pady=6)
    sp.configure(height=px(150), width=px(380))
    sp.pack_propagate(False)
    sp.pack(fill="x")
    for i in range(9):
        label(sp.body, f"Row {i + 1}  //  a page longer than its window scrolls with the wheel",
              bg=CARD).pack(anchor="w", pady=px(3))
    tipper = Button(b, "hover me")
    tipper.pack(anchor="w", pady=(px(10), px(70)))
    tipper.set_tip("Re-finds your character after a load or a teleport. Land first: it needs you on foot.")
    return tipper, sp
def main(argv):
    global REDUCE_MOTION
    import argparse
    ap = argparse.ArgumentParser(description="Suit Control widget kit")
    ap.add_argument("--gallery", action="store_true", help="render every widget in every state to a PNG")
    ap.add_argument("--out", default="widgets_gallery.png")
    ap.add_argument("--scale", type=float, default=None, help="default: the rightmost monitor's")
    a = ap.parse_args(argv)
    if not a.gallery:
        ap.print_help()
        return 0
    dpi_aware()
    guard = no_activate_guard(True)
    REDUCE_MOTION = True
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=BG)
    mon = rightmost_monitor()
    init(root, scale=a.scale or scale_for(mon[3] - mon[1]))
    tipper, sp = _gallery(root)
    def ready():
        sp.scroll_to(px(40), animate=False)
        tipper.tooltip.show()
    try:
        w, h = capture(root, a.out, ready=ready)
    finally:
        root.destroy()
    guard.remove()
    print(f"{a.out}: {w}x{h} (activations refused: {guard.refused})")
    return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
