import argparse
import ctypes
import ctypes.wintypes as wt
import json
import mmap
import os
import queue
import struct
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
APP = Path(__file__).resolve().parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
LOG = Path(os.environ.get("SUIT_CONTROL_LOG") or APP / "panel_log.txt")
TITLE = "Fly Like Iron Man - Suit Control"
AUTHOR = "DooDooDevan"
def log(msg):
    try:
        if LOG.exists() and LOG.stat().st_size > 512 * 1024:
            os.replace(LOG, LOG.with_name("panel_log.old.txt"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + str(msg).rstrip() + "\n")
    except OSError:
        pass
def _excepthook(tp, val, tb):
    log("".join(traceback.format_exception(tp, val, tb)))
try:
    import tkinter as tk
except Exception as _e:
    log(f"tkinter won't import: {_e!r}")
    if "--warm" not in sys.argv and "--preview" not in sys.argv:
        ctypes.windll.user32.MessageBoxW(
            None, "Suit Control needs Python's tkinter: the folders tcl\\ and Lib\\tkinter plus _tkinter.pyd, "
                  "tcl86t.dll and tk86t.dll next to python.exe. This Python doesn't have them.\n\n"
                  f"({_e})", TITLE, 0x10)
    raise SystemExit(1)
import control
import panel_proc
import panel_widgets as pw
import settings
try:
    import hud
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    hud = None
    log("the live gauge is off: " + traceback.format_exc(limit=2))
try:
    import panel_pages
    PAGES_ERR = ""
except Exception:
    panel_pages = None
    PAGES_ERR = traceback.format_exc(limit=6)
    log("panel_pages didn't load:\n" + PAGES_ERR)
PAGES = ("HOME", "FLIGHT", "POWERS", "SOUND", "VISUALS", "CONTROLS", "ABOUT")
RAIL_ACCENT = {"HOME": None, "FLIGHT": "throttle", "POWERS": ["burner", "sonic", "cruise"], "SOUND": None,
               "VISUALS": "amber", "CONTROLS": None, "ABOUT": None}
SETTINGS_PAGES = ("FLIGHT", "POWERS", "SOUND", "VISUALS", "CONTROLS")
MS_PER_LEVEL = 10.0 / 18.0 / 0.20
SAVE_DEBOUNCE_MS = 300
ACK_WAIT, ACK_WAIT_FOCUS = 3.0, 25.0
HIDDEN_EXIT_S = 15.0
TICK_MS = 50
GAUGE_MS = 166
GAUGE_IDLE_S = 2.0
GAUGE_AWAY_S = 1.0
GAP = 12
NAV_KEYS = (0x08, 0x09, 0x0D, 0x1B, 0x25, 0x26, 0x27, 0x28, 0x2E)
STAGE_TEXT = {1: "LOCATING YOUR SUIT", 2: "SYNCING", 3: "SUIT ONLINE"}
INTRO = {"HOME": "The suit at a glance: its state, the systems check and quick fixes.",
         "ABOUT": "Who made it, the licence in plain words, and tools for when something goes wrong."}
def page_intro(body, name):
    pw.label(body, INTRO[name], "help", bg=pw.BG, wrap=pw.px(760)).pack(anchor="w", pady=(0, pw.px(8)))
def typed_default(sec, key):
    d = settings.DEFAULTS[sec][key]
    if isinstance(d, str) and d.lower() in settings.TRUE + settings.FALSE and not (
            sec == "keys" and key in settings.KEY_SETTINGS):
        return d.lower() in settings.TRUE
    return d
def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return str(a).lower() == str(b).lower()
def speed_text(level):
    ms = float(level) * MS_PER_LEVEL
    return f"{ms:,.0f} m/s // {ms * 3.6:,.0f} km/h"
def clock(secs):
    secs = max(0, int(round(secs)))
    return f"{secs // 60}:{secs % 60:02d}"
def key_words(k):
    return k[1].replace("_", " ")
def scrub(text):
    home = os.path.expanduser("~")
    user = os.environ.get("USERNAME", "")
    for h in {home, home.replace("\\", "/")}:
        if h and len(h) > 3:
            text = text.replace(h, "%USERPROFILE%")
    if user and len(user) > 2:
        import re
        text = re.sub(re.escape(user), "<user>", text, flags=re.I)
    return text
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_MONPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
_u32.GetForegroundWindow.restype = wt.HWND
_u32.MonitorFromWindow.restype = wt.HMONITOR
_u32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
_u32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.c_void_p]
_u32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.c_void_p, _MONPROC, wt.LPARAM]
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD),
                ("szDevice", ctypes.c_wchar * 32)]
def _mon_info(hmon):
    mi = _MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(mi)
    if not hmon or not _u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    r, w = mi.rcMonitor, mi.rcWork
    return dict(name=mi.szDevice, rect=(r.left, r.top, r.right, r.bottom), work=(w.left, w.top, w.right, w.bottom),
                primary=bool(mi.dwFlags & 1))
def monitors():
    out = []
    def cb(h, dc, r, lp):
        i = _mon_info(h)
        if i:
            out.append(i)
        return 1
    try:
        _u32.EnumDisplayMonitors(None, None, _MONPROC(cb), 0)
    except Exception:
        pass
    return out
def monitor_of(hwnd):
    try:
        return _mon_info(_u32.MonitorFromWindow(hwnd, 2)) if hwnd else None
    except Exception:
        return None
def _colorref(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)
def dark_frame(hwnd):
    try:
        dwm = ctypes.WinDLL("dwmapi")
        for attr, val in ((20, 1), (35, _colorref(pw.BG)), (34, _colorref("#000000")), (36, _colorref(pw.TEXT))):
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(wt.HWND(hwnd), wt.DWORD(attr), ctypes.byref(v), wt.DWORD(4))
    except Exception:
        pass
def foreground_pid():
    try:
        pid = wt.DWORD()
        _u32.GetWindowThreadProcessId(_u32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0
def logo_image(size):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r = size / 2, size * 0.46
    d.polygon([(c, c - r), (c + r, c), (c, c + r), (c - r, c)], fill=(10, 14, 22, 255))
    w = max(2, size // 11)
    pts = [(c, c - r + w), (c + r - w, c), (c, c + r - w), (c - r + w, c)]
    d.line(pts + [pts[0]], fill=(236, 242, 245, 255), width=w)
    q = r * 0.42
    d.polygon([(c, c - q), (c + q, c), (c, c + q), (c - q, c)], fill=(236, 242, 245, 255))
    return im
class PanelState:
    def __init__(self, path, enabled=True):
        self.path, self.enabled = Path(path), enabled
        self.d = {}
        try:
            if enabled and self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                self.d = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            self.d = {}
    def get(self, k, default=None):
        return self.d.get(k, default)
    def set(self, **kw):
        self.d.update(kw)
    def save(self):
        if not self.enabled:
            return
        tmp = self.path.with_name(self.path.name + ".tmp")
        for _ in range(10):
            try:
                tmp.write_text(json.dumps(self.d, indent=1), encoding="utf-8")
                os.replace(tmp, self.path)
                return
            except OSError:
                time.sleep(0.03)
class Ctx:
    def __init__(self, app, ini):
        self.app = app
        self.root = app.root
        self.demo = app.demo
        self.client = app.client
        self.ini = Path(ini)
        self.session = self.ini.with_name("settings.panel-session.ini")
        self.S = settings.load(self.ini, quiet=True)
        self.mtime = self._stat()
        self.overlay = {}
        self.pending = {}
        self.failed = {}
        self.saving = False
        self._after = None
        self.results = queue.Queue()
        self.waits = []
        self._listeners = []
        self.session_started = False
    def _stat(self):
        try:
            return os.stat(self.ini).st_mtime
        except OSError:
            return 0.0
    def reload_cache(self):
        self.S = settings.load(self.ini, quiet=True)
    def get(self, sec, key):
        k = (str(sec).lower(), str(key).lower())
        if k in self.overlay:
            return self.overlay[k]
        sec, key = k
        if sec == "keys" and key in settings.KEY_SETTINGS:
            return settings.key_name(self.S.keys.get(key, 0))
        if sec == "pad":
            raw = self.S.raw("pad").get(key)
            if raw is not None and raw.strip():
                return raw.strip()
            try:
                import xpad
                return str(xpad.PAD_DEFAULTS.get(key, ""))
            except Exception:
                return ""
        if sec == "game":
            return self.S.raw("game").get(key, "")
        return getattr(self.S, sec)[key]
    def default(self, sec, key):
        if sec == "pad":
            try:
                import xpad
                return str(xpad.PAD_DEFAULTS.get(key, ""))
            except Exception:
                return ""
        return typed_default(sec, key)
    def rng(self, sec, key):
        return settings.RANGES.get((sec, key))
    def choices(self, sec, key):
        c = settings.CHOICES.get((sec, key))
        return list(c) if c else None
    def apply_class(self, sec, key):
        return control.apply_class(sec, key)
    def badge_for(self, sec, key):
        return "AFTER RESTART" if control.apply_class(sec, key) == "restart" else None
    def snapshot(self, keys):
        return {k: self.get(*k) for k in keys}
    def status(self):
        st = self.app.st
        return st if st and st.get("alive") else None
    def running(self):
        return bool(self.app.st and self.app.st.get("alive"))
    def suit(self):
        return self.app.suit[0]
    def speed_text(self, level):
        return speed_text(level)
    def after(self, ms, fn):
        return self.root.after(ms, fn)
    def toast(self, text, kind="ok", action=None):
        self.app.toast(text, kind, action)
    def strip(self, text, kind="error", actions=()):
        self.app.strip.show(text, kind, list(actions))
    def on_settings(self, cb):
        self._listeners.append(cb)
    def set(self, sec, key, value, **kw):
        self.set_many({(sec, key): value})
    def set_many(self, changes, **kw):
        if not changes:
            return
        for (sec, key), v in dict(changes).items():
            k = (str(sec).lower(), str(key).lower())
            self.pending[k] = v
            self.overlay[k] = v
        if not self.session_started:
            self.begin_session()
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
        self._after = self.root.after(SAVE_DEBOUNCE_MS, self.flush)
    def begin_session(self):
        self.session_started = True
        try:
            settings.begin_session(self.ini, self.session)
        except Exception:
            log("begin_session: " + traceback.format_exc(limit=2))
    def flush(self, sync=False):
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if not self.pending:
            return
        if self.saving and sync:
            end = time.perf_counter() + 3.0
            while self.saving and time.perf_counter() < end:
                try:
                    changes_, res_, err_ = self.results.get(timeout=0.05)
                except queue.Empty:
                    continue
                self.saving = False
                self._saved(changes_, res_, err_)
        if self.saving:
            self._after = self.root.after(80, self.flush)
            return
        changes = dict(self.pending)
        self.pending.clear()
        self.saving = True
        def work():
            try:
                self.results.put((changes, settings.save(changes, self.ini), None))
            except Exception as e:
                self.results.put((changes, None, e))
        if sync:
            work()
            self.drain()
        else:
            threading.Thread(target=work, daemon=True, name="suit-save").start()
    def drain(self):
        while True:
            try:
                changes, res, err = self.results.get_nowait()
            except queue.Empty:
                return
            self.saving = False
            self._saved(changes, res, err)
    def _saved(self, changes, res, err):
        keys = set(changes)
        if err is not None:
            msg = err.args[0] if isinstance(err, settings.SettingsError) and err.args else \
                f"{err.__class__.__name__}: {err}"
            log(f"save refused: {msg}  {changes}")
            self.failed.update(changes)
            for k in keys:
                if k not in self.pending:
                    self.overlay.pop(k, None)
            self.app.saved(keys, False, msg)
            self.app.reload_pages()
            self.strip(f"Not saved: {msg}", "error", [("RETRY", self.retry), ("OPEN FOLDER", self.app.open_folder)])
            return
        self.failed = {k: v for k, v in self.failed.items() if k not in keys}
        if not self.failed and self.app.strip.shown and self.app.strip.kind == "error":
            self.app.strip.hide()
        self.mtime = res[3] or self._stat()
        self.reload_cache()
        for k in keys:
            if k not in self.pending:
                self.overlay.pop(k, None)
        restart = {k for k in keys if control.apply_class(*k) == "restart"}
        self.app.settings_changed(keys)
        if not self.running():
            self.app.saved(keys, True, "saved")
            return
        def acked(a):
            if restart:
                self.app.restart_pending.update(restart)
                self.app.saved(keys, True, "after restart")
            else:
                self.app.saved(keys, True, "applied" if a and a[0] == "done" else "saved")
        self.send("reload", (self.mtime,), on_ack=acked)
    def retry(self):
        if self.failed:
            self.set_many(dict(self.failed))
    def external_change(self):
        m = self._stat()
        if m == self.mtime or self.saving or self.pending:
            return False
        self.mtime = m
        self.reload_cache()
        self.overlay.clear()
        self.app.reload_pages()
        self.app.settings_changed({(s, k) for s in ("keys", "panel") for k in settings.DEFAULTS[s]})
        if self.running():
            self.send("reload", (m,))
        self.toast("settings.ini changed outside Suit Control: reloaded", "info")
        return True
    def send(self, cmd, a=(), text="", on_ack=None, timeout=None):
        name = cmd if isinstance(cmd, str) else control.CMDS.get(int(cmd), ("?", False))[0]
        if not self.running():
            if on_ack:
                self.root.after_idle(lambda: on_ack(("refused", 0, "the suit is off")))
            return 0
        try:
            seq = self.client.send(name, a, text)
        except Exception as e:
            log(f"send {name}: {e!r}")
            if on_ack:
                self.root.after_idle(lambda: on_ack(("failed", 0, "couldn't reach the suit")))
            return 0
        focus = control.CMDS.get(control.CMD.get(name, 0), ("", False))[1]
        wait = timeout or (ACK_WAIT_FOCUS if focus else ACK_WAIT)
        self.waits.append([seq, time.perf_counter() + wait, on_ack, name])
        return seq
    def poll_acks(self, now):
        keep = []
        for w in self.waits:
            seq, deadline, cb, name = w
            try:
                a = self.client.ack(seq)
            except Exception:
                a = None
            if a and a[0] in control.FINAL:
                self._call(cb, a)
            elif now > deadline:
                self._call(cb, None)
            else:
                keep.append(w)
        self.waits = keep
    def drop_waits(self):
        for w in self.waits:
            self._call(w[2], None)
        self.waits = []
    @staticmethod
    def _call(cb, a):
        if cb:
            try:
                cb(a)
            except Exception:
                log("ack callback: " + traceback.format_exc(limit=3))
    def undo_session(self):
        self.flush(sync=True)
        try:
            ch = settings.session_changes(self.ini, self.session) if self.session_started else {}
        except Exception as e:
            ch = {}
            log(f"session_changes: {e!r}")
        if not ch:
            self.toast("Nothing to undo: your settings are as they were", "info")
            return
        self.set_many(ch)
        self.flush(sync=True)
        self.app.reload_pages()
        self.toast(f"Undone: {len(ch)} setting{'s' if len(ch) != 1 else ''} put back")
    def reset_all(self):
        ch = settings.reset_all_changes()
        before = self.snapshot(ch)
        self.set_many(ch)
        self.flush(sync=True)
        self.app.reload_pages()
        self.toast("Every setting is back to its default", "ok",
                   ("UNDO", lambda: (self.set_many(before), self.app.reload_pages())))
def card(parent, title=None, accent=None, **kw):
    c = pw.Card(parent, title, accent=accent, width=pw.px(200), **kw)
    return c
class Dots(pw._Widget):
    def __init__(self, parent, command, tip=None):
        self.command = command
        super().__init__(parent, pw.px(34), pw.px(30), tip=tip)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<KeyPress-Return>", self._key)
        self.bind("<KeyPress-space>", self._key)
    def _press(self, e):
        self._grab_focus()
        self._pressed = True
        self.redraw()
    def _release(self, e):
        if self._pressed:
            self._pressed = False
            self.redraw()
            if self._inside(e):
                self.command()
    def _key(self, e):
        self._keyed()
        self.command()
        return "break"
    def _draw(self, w, h):
        if self._hover or self._pressed:
            self.rect(0, 0, w, h, pw.HOVER)
        if self._focus and self._ring:
            self.rect(0, h - pw._lw(2), w, h, pw.TEXT)
        col = pw.TEXT if self._hover else pw.TEXT_DIM
        s, gap = pw.px(4), pw.px(4)
        x = (w - 3 * s - 2 * gap) // 2
        for i in range(3):
            self.rect(x + i * (s + gap), h // 2 - s // 2, x + i * (s + gap) + s, h // 2 - s // 2 + s, col)
class GaugeHero(tk.Canvas):
    def __init__(self, parent):
        self.g = None
        if hud is not None:
            try:
                self.g = hud.Gauge(0.55 * pw.SCALE)
            except Exception:
                log("gauge: " + traceback.format_exc(limit=2))
        w, h = self.g.size if self.g else (pw.px(443), pw.px(207))
        super().__init__(parent, width=w, height=h, bg=pw.CARD, highlightthickness=0, bd=0, takefocus=0)
        self.W, self.H = w, h
        self.photo = None
        self.item = None
        self.last = None
        self._base = None
        self._said = None
        self._fails = 0
        if self.g is not None:
            g_ = self.g
            cx, cy, r = g_.HALF * g_.s, (g_.map_cy - g_.Y0) * g_.s, hud.GAUGE_MAP_R * g_.s
            x, ys = int(cx + r + pw.px(16)), (int(cy - r * 0.42), int(cy + r * 0.12), int(cy + r * 0.58))
        else:
            x, ys = int(w * 0.36), (int(h * 0.30), int(h * 0.47), int(h * 0.62))
        self.t_num = self.create_text(x, ys[0], anchor="w", font=pw.font("num"), fill=pw.TEXT, text="")
        self.t_unit = self.create_text(x, ys[0], anchor="w", font=pw.font("value"), fill=pw.TEXT_DIM,
                                       text="")
        self.t_alt = self.create_text(x, ys[1], anchor="w", font=pw.font("help"), fill=pw.TEXT_DIM, text="")
        self.t_mode = self.create_text(x, ys[2], anchor="w", font=pw.font("badge"), fill=pw.TEXT_DIM,
                                       text="")
        if self.g is None:
            self.create_text(w // 2, h // 2, text="(the live gauge needs hud.py and Pillow)", fill=pw.TEXT_OFF,
                             font=pw.font("help"))
    def draw(self, fresh, st, now):
        if self.g is None:
            return
        key = None if fresh else ("idle",)
        if key is not None and key == self.last:
            return
        self.last = key
        try:
            img = self.g.draw(1.0 if fresh else 0.35, st if fresh else hud.idle_state(), now, () if fresh else None)
            if self._base is None or self._base.size != img.size:
                self._base = Image.new("RGBA", img.size, tuple(int(pw.CARD[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
            out = self._base.copy()
            out.alpha_composite(img)
            if self.photo is None or (self.photo.width(), self.photo.height()) != out.size:
                self.photo = ImageTk.PhotoImage(out, master=self)
                if self.item is None:
                    self.item = self.create_image(0, 0, anchor="nw", image=self.photo)
                    self.tag_lower(self.item)
                else:
                    self.itemconfigure(self.item, image=self.photo)
            else:
                self.photo.paste(out)
            self._fails = 0
        except tk.TclError:
            self._fails += 1
            if self._fails in (1, 50):
                log("gauge draw (will retry): " + traceback.format_exc(limit=2))
            self.last = None
            self.photo = None
            if self.item is not None:
                try:
                    self.delete(self.item)
                except tk.TclError:
                    pass
                self.item = None
        except Exception:
            log("gauge draw: " + traceback.format_exc(limit=3))
            self.g = None
    def readout(self, num, unit, alt, mode, live=True):
        said = (num, unit, alt, mode, live)
        if said == self._said:
            return
        self._said = said
        f = pw.font("num")
        self.itemconfigure(self.t_num, text=num, fill=pw.TEXT if live else pw.TEXT_OFF)
        x, y = self.coords(self.t_num)
        self.coords(self.t_unit, x + f.measure(num) + pw.px(8), y + pw.px(5))
        self.itemconfigure(self.t_unit, text=unit)
        self.itemconfigure(self.t_alt, text=alt)
        self.itemconfigure(self.t_mode, text=pw.spaced(mode) if mode else "",
                           fill=pw.TEXT if live else pw.TEXT_DIM)
def flight_mode(st):
    if not st or not st.get("alive"):
        return "SUIT OFFLINE"
    if not st.get("flying"):
        return "ON FOOT"
    if st.get("suspended"):
        return "HOLDING POSITION"
    for k, w in (("cruise", "INTERPLANETARY"), ("dive", "DIVE"), ("burning", "AFTERBURNER"),
                 ("ab_cooling", "COOLING"), ("reversing", "REVERSE"), ("water", "UNDERWATER"), ("space", "SPACE")):
        if st.get(k):
            return "FLYING // " + w
    return "HOVER" if abs(st.get("throttle", 0.0)) < 0.01 and st.get("speed", 0.0) < 2.0 else "FLYING"
class HomePage:
    def __init__(self, app, page):
        self.app, self.ctx, self.page = app, app.ctx, page
        px = pw.px
        b = page.body
        self.cache = {}
        page_intro(b, "HOME")
        self.warn = pw.InlineStrip(b, "warn")
        self.warn.pack(fill="x")
        self.rbar = pw.InlineStrip(b, "warn")
        self.rbar.pack(fill="x")
        hero = card(b, None)
        hero.pack(fill="x", pady=(0, px(GAP)))
        hb = hero.body
        self.head = pw.label(hb, "", "title")
        self.head.pack(anchor="w")
        self.sub = pw.label(hb, "", "label", colour=pw.TEXT_DIM, wrap=px(740))
        self.sub.pack(anchor="w", pady=(px(2), 0))
        self.bar_row = tk.Frame(hb, bg=pw.CARD)
        self.bar = pw.BandMeter(self.bar_row, 0.0, "info", width=px(443), height=px(12))
        self.bar.pack(side="left")
        self.bar_txt = pw.label(self.bar_row, "", "badge", colour=pw.INFO)
        self.bar_txt.pack(side="left", padx=(px(12), 0))
        row = tk.Frame(hb, bg=pw.CARD)
        row.pack(fill="x", pady=(px(14), 0))
        self.row = row
        self.gauge = GaugeHero(row)
        self.gauge.pack(side="left", anchor="n")
        col = tk.Frame(row, bg=pw.CARD)
        col.pack(side="right", anchor="n", padx=(px(16), 0))
        BW = px(262)
        self.pslot = tk.Frame(col, bg=pw.CARD)
        self.pslot.pack(anchor="e")
        self.primary = pw.Button(self.pslot, "BACK TO GAME", self._primary, kind="primary", width=BW)
        self.force = pw.HoldButton(self.pslot, "FORCE STOP", self.app.force_stop, hold=1.5,
                                   hold_text="HOLD TO FORCE STOP", width=BW,
                                   tip="Hold it 1.5 s: ends a stuck flight script. The camera puts itself back "
                                       "the next time the suit powers up.")
        self.primary.pack()
        self.primary_kind = "primary"
        self.b_power = pw.HoldButton(col, "POWER DOWN", lambda: self.app.run_job("power"), hold=0.8,
                                     hold_text="HOLD TO POWER DOWN", width=BW,
                                     tip="Hold it: turns the suit off cleanly, and camera, hands and HUD go back "
                                         "to the game's own. Holding End in the game does the same.")
        self.b_find = pw.Button(col, "FIND MY CHARACTER", self._find, width=BW,
                                tip="Goes back to the game and looks for your character again: use it after "
                                    "a load or a teleport, or if flying moves the wrong body.")
        for w in (self.b_power, self.b_find):
            w.pack(anchor="e", pady=(px(8), 0))
        sysc = card(b, "systems check")
        sysc.pack(fill="x")
        self.lights = {}
        for name, label in (("game", "game"), ("mod", "game link (mod)"), ("suit", "suit"),
                            ("mods", "mods enabled"), ("build", "game build"), ("pad", "controller")):
            lt = pw.Light(sysc.body, label, "off", "", width=px(320), command=lambda: None)
            lt.pack(fill="x", pady=(0, px(2)))
            self.lights[name] = lt
        rc = card(b, "repair")
        rc.pack(fill="x", pady=(px(GAP), 0))
        rc.header(pw.Button(rc, "REPAIR ALL", self._repair_all, kind="ghost", accent="info", height=px(26), bg=pw.CARD,
                            tip="All four below, one after the other."))
        g = tk.Frame(rc.body, bg=pw.CARD)
        g.pack(fill="x")
        self.repairs = {}
        for i, (cmd, label, help_) in enumerate((
                ("relight", "RELIGHT JETS", "Flames out mid-flight? Goes back to the game and lights them."),
                ("reset_fx", "REPAIR CAMERA", "Puts the camera's distance and view back to the game's own."),
                ("restart_hud", "RESTART HUD", "The gauge and map, started again."),
                ("restart_effects", "RESTART EFFECTS", "The warp and speed effects, started again."))):
            g.columnconfigure(i, weight=1, uniform="rep")
            cell = tk.Frame(g, bg=pw.CARD)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(6), 0 if i == 3 else px(6)))
            bt = pw.Button(cell, label, (lambda c=cmd: self._repair(c)), width=px(150))
            bt.pack(fill="x")
            pw.label(cell, help_, "help", wrap=px(170)).pack(anchor="w", pady=(px(4), 0))
            self.repairs[cmd] = bt
        self.reload()
    def _primary(self):
        k = self.cache.get("primary_action")
        if k == "game":
            self.app.run_job("game")
        elif k == "start":
            self.app.run_job("start")
        elif k == "back":
            self.app.back_to_game()
    def _restart(self):
        if self.app.st.get("flying"):
            self.ctx.toast("Land first: the suit restarts on the ground", "info")
        else:
            self.app.run_job("restart")
        self.refresh(self.ctx.status(), force=True)
    def _find(self):
        self.app.send_in_game("refind", "Looking for your character: stand still in the open")
    def _repair(self, cmd):
        if cmd == "relight":
            self.app.send_in_game("relight", "Relighting the jets")
            return
        bt = self.repairs[cmd]
        bt.set_busy(True)
        def done(a, bt=bt, label=bt.label.title().replace("Hud", "HUD")):
            bt.set_busy(False)
            if a and a[0] == "done":
                self.ctx.toast(f"{label}: done" + (f" ({a[2]})" if a[2] else ""))
            else:
                self.ctx.toast(f"{label}: " + (a[2] if a and a[2] else "the suit didn't answer"), "warn")
        self.ctx.send(cmd, on_ack=done)
    def _repair_all(self):
        for cmd in ("reset_fx", "restart_hud", "restart_effects"):
            self._repair(cmd)
        if self.app.st.get("flying"):
            self.app.send_in_game("relight", "Relighting the jets")
    def _fix(self, name):
        a = self.app
        if name == "game" and not a.probe.get("nms_pid"):
            a.run_job("game")
        elif name == "suit":
            if a.suit[0] == "offline" and a.probe.get("nms_pid"):
                a.run_job("start")
        elif name == "pad":
            a.select("CONTROLS")
    def state(self):
        a = self.app
        st, (suit, why) = a.st, a.suit
        p = a.probe
        if a.job is not None:
            return "job", a.job_title, pw.INFO, a.job_text or "…", None
        nms = bool(p.get("nms_pid"))
        if suit == "not_responding":
            return ("stuck", "NOT RESPONDING", pw.RED,
                    f"The flight script is stuck ({why}). Hold FORCE STOP to end it; POWER UP starts it again.",
                    "force")
        if not nms and suit != "online":
            last = ""
            if st.get("magic") and st.get("phase") == "exited" and st.get("exit_code") not in (0, 75):
                last = f" The suit stopped last time: {why}."
            return ("nogame", "NO MAN'S SKY ISN'T RUNNING", pw.TEXT,
                    "Start the game: the suit powers up by itself once you're in the world." + last, "game")
        if suit == "offline":
            odd = st.get("magic") and not (st.get("phase") == "exited" and st.get("exit_code") in (0, 75))
            last = f" It stopped last time: {why}." if odd else ""
            if a.mod_state == "live":
                return ("ready", "SUIT OFFLINE", pw.TEXT,
                        "You're in the world: power up the suit, then double-tap Space to fly." + last, "start")
            return ("load", "LOAD YOUR SAVE", pw.TEXT,
                    "The suit powers up once you're in the world. Already there? Power it up." + last, "start")
        if not nms:
            return "closing", "THE GAME CLOSED", pw.TEXT_DIM, "The suit is powering down with it.", None
        if st.get("phase") == "starting" or st.get("startup_stage") in (1, 2):
            return ("starting", "STARTING", pw.INFO,
                    "Finding your character. In the game: take a few steps.", "back")
        if st.get("phase") in ("quitting", "exited"):
            return ("quitting", "POWERING DOWN", pw.INFO,
                    "The suit is switching off: camera, hands and HUD go back to the game's own.", "back")
        if suit == "busy":
            return "busy", "BUSY", pw.INFO, why[:1].upper() + why[1:] if why else "Busy", "back"
        key = a.keys_text("panel")
        if st.get("flying"):
            if st.get("suspended"):
                return ("holding", "HOLDING POSITION", pw.ORANGE,
                        f"He hovers while Suit Control is in front. Back to the game: {key} or Esc.", "back")
            return "flying", "FLYING", pw.ACCENTS["throttle"][1], flight_mode(st).title(), "back"
        return ("online", "SUIT ONLINE", pw.TEXT,
                f"Flight systems ready // double-tap Space in the game to fly. {key} brings this back.", "back")
    def refresh(self, status=None, force=False):
        a = self.app
        c = self.cache
        key, head, colour, sub, act = self.state()
        if force or c.get("head") != (head, colour):
            c["head"] = (head, colour)
            self.head.configure(text=pw.spaced(head), fg=colour)
        if force or c.get("sub") != sub:
            c["sub"] = sub
            self.sub.configure(text=sub)
        st = a.st
        starting = key == "starting"
        if starting != c.get("bar_on"):
            c["bar_on"] = starting
            if starting:
                self.bar_row.pack(anchor="w", pady=(px_(8), 0), before=self.row)
            else:
                self.bar_row.pack_forget()
        if starting:
            stage = int(st.get("startup_stage", 0))
            prog = max(0.05, min(1.0, float(st.get("startup_progress", 0.0))))
            if c.get("bar") != (stage, round(prog, 2)):
                c["bar"] = (stage, round(prog, 2))
                self.bar.set(prog)
                self.bar_txt.configure(text=pw.spaced(STAGE_TEXT.get(stage, "POWERING UP")))
        c["primary_action"] = act
        want = "force" if act == "force" else "primary"
        if want != self.primary_kind:
            self.primary_kind = want
            (self.primary if want == "force" else self.force).pack_forget()
            (self.force if want == "force" else self.primary).pack()
        label = {"game": "START GAME", "start": "POWER UP THE SUIT", "back": "BACK TO GAME"}.get(act, "PLEASE WAIT")
        accent = "throttle" if act in ("game", "start") else "white"
        if force or c.get("primary") != (label, accent, a.job is not None):
            c["primary"] = (label, accent, a.job is not None)
            self.primary.accent = accent
            self.primary.set_text(label)
            self.primary.set_busy(a.job is not None)
            self.primary.set_disabled(act is None and a.job is None)
        alive = a.suit[0] in ("online", "busy")
        flying = bool(st.get("flying")) and alive
        busy = a.job is not None
        sec = (alive and not busy, flying, a.suit[0], busy, starting)
        if force or c.get("sec") != sec:
            c["sec"] = sec
            self.b_power.set_text("POWER DOWN: HE DROPS" if flying else "POWER DOWN")
            self.b_power.set_disabled(not alive or busy, "The suit is already off" if not alive else "Busy")
            self.b_find.set_disabled(not alive or flying or busy or starting,
                                     "Land first" if flying else "Power up the suit first" if not alive else
                                     "It's already looking: take a few steps in the game" if starting else "Busy")
            hold = 0.8 if self.ctx.get("panel", "confirm_quit") else 0.05
            self.b_power.hold = hold
            for cmd, bt in self.repairs.items():
                bt.set_disabled(not alive, "Power up the suit first")
            self.repairs["relight"].set_disabled(not flying, "Only while he flies" if alive
                                                 else "Power up the suit first")
        self._lights()
        self._strips()
        a.draw_gauge()
    def _lights(self):
        a = self.app
        p, st = a.probe, a.st
        nms = bool(p.get("nms_pid"))
        L = {}
        L["game"] = ("ok", "Running") if nms else ("off", "Not running // click to start it")
        ms = a.mod_state
        L["mod"] = {"live": ("ok", "Hand and foot jets connected"),
                    "paused": ("warn", "Paused: the game is in a menu or loading"),
                    "not_attached": ("warn", "Not attached yet: load your save (start the game through Steam)"),
                    "off": ("off", "Starts with the game")}.get(ms, ("off", ""))
        if ms == "paused" and p.get("fg_pid") == os.getpid():
            L["mod"] = ("ok", "Connected // in the background while this window is open")
        s, why = a.suit
        if s == "online" and (st.get("phase") == "starting" or st.get("startup_stage") in (1, 2)):
            s, why = "busy", "starting"
        elif s == "online" and st.get("phase") == "quitting":
            s, why = "busy", "powering down"
        L["suit"] = {"online": ("ok", "Running" + (f" // {st.get('version')}" if st.get("version") else "")),
                     "busy": ("busy", (why or "busy")[:1].upper() + (why or "busy")[1:]),
                     "not_responding": ("bad", "Not responding: hold FORCE STOP above"),
                     "offline": (("bad" if nms and a.mod_state == "live" else "off"),
                                 "Off // click to power it up" if nms else "Off")}[s]
        dis = p.get("mods_disabled") or st.get("mods_disabled")
        L["mods"] = (("bad", "The game switched mods off (after a crash?): restart it through Steam")
                     if dis else ("ok", "On") if p.get("mods_known") else ("off", "Unknown"))
        L["build"] = a.build_light()
        pads = p.get("pads") or []
        on = bool(self.ctx.get("pad", "enabled").lower() in settings.TRUE)
        L["pad"] = ((("ok", f"Connected (slot {pads[0] + 1})") if on else
                     ("warn", "Connected, but turned off: CONTROLS page")) if pads else
                    ("off", "None connected // plug one in any time"))
        act = {"game": not nms and a.job is None, "suit": s == "offline" and nms and a.job is None,
               "pad": bool(pads) and not on}
        for k, (state, fix) in L.items():
            if self.cache.get(("light", k)) != (state, fix, act.get(k)):
                self.cache[("light", k)] = (state, fix, act.get(k))
                lt = self.lights[k]
                lt.command = (lambda n=k: self._fix(n)) if act.get(k) else None
                lt._link_hover = False
                lt.configure(cursor="")
                lt.set(state=state, fix=fix)
    def _strips(self):
        a = self.app
        w = self.ctx.S.warnings
        if w and not self.cache.get("warned") == len(w):
            self.cache["warned"] = len(w)
            n = len(w)
            self.warn.show(f"settings.ini: {n} line{'s' if n != 1 else ''} ignored, defaults used. "
                           f"{w[0].replace('settings.ini: ', '')}", "warn",
                           [("OPEN FILE", lambda: a.open_path(self.ctx.ini))])
        elif not w and self.cache.get("warned"):
            self.cache["warned"] = 0
            self.warn.hide()
        on = a.suit[0] in ("online", "busy")
        rp = sorted(a.restart_pending) if on else []
        flag = on and bool(a.st.get("restart_pending"))
        if (rp, flag) != self.cache.get("rp"):
            self.cache["rp"] = (rp, flag)
            if rp:
                n = len(rp)
                self.rbar.show(f"{n} change{'s' if n != 1 else ''} wait{'' if n != 1 else 's'} for a restart: "
                               + ", ".join(key_words(k) for k in rp), "warn",
                               [("RESTART SUIT", self._restart)], close=False)
            elif flag:
                self.rbar.show("Some changes wait for a restart of the suit", "warn",
                               [("RESTART SUIT", self._restart)], close=False)
            else:
                self.rbar.hide()
    def reload(self):
        self.refresh(self.ctx.status(), force=True)
    def on_show(self):
        self.refresh(self.ctx.status(), force=True)
def px_(v):
    return pw.px(v)
class AboutPage:
    def __init__(self, app, page):
        self.app, self.ctx = app, app.ctx
        px = pw.px
        b = page.body
        self.cache = {}
        page_intro(b, "ABOUT")
        c = card(b, None)
        c.pack(fill="x")
        top = tk.Frame(c.body, bg=pw.CARD)
        top.pack(fill="x")
        if hud is not None:
            try:
                self._logo = ImageTk.PhotoImage(logo_image(px(52)))
                tk.Label(top, image=self._logo, bg=pw.CARD, bd=0).pack(side="left", padx=(0, px(14)))
            except Exception:
                pass
        t = tk.Frame(top, bg=pw.CARD)
        t.pack(side="left", anchor="w")
        pw.label(t, pw.spaced("fly like iron man"), "title").pack(anchor="w")
        pw.label(t, pw.spaced(f"by {AUTHOR}"), "value", colour=pw.TEXT_DIM).pack(anchor="w")
        self.ver = pw.label(c.body, "", "label")
        self.ver.pack(anchor="w", pady=(px(12), 0))
        self.build = pw.label(c.body, "", "label", colour=pw.TEXT_DIM)
        self.build.pack(anchor="w", pady=(px(2), 0))
        lic = card(b, "licence")
        lic.pack(fill="x", pady=(px(GAP), 0))
        for line in ("Free to use, for anyone.",
                     f"Credit required: show \"Fly Like Iron Man by {AUTHOR}\" wherever you share it, show it or "
                     "use any of it (mods, videos, modpacks).",
                     "No sale: never sold, in whole or in part, and never behind a paywall.",
                     "Changed versions keep this credit and these terms. The closest standard licence is "
                     "Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)."):
            r = tk.Frame(lic.body, bg=pw.CARD)
            r.pack(fill="x", pady=(0, px(4)))
            tk.Frame(r, bg=pw.TEXT_DIM, width=px(6), height=px(6)).pack(side="left", anchor="n", pady=(px(8), 0))
            pw.label(r, line, "label", wrap=px(720)).pack(side="left", padx=(px(10), 0), anchor="w")
        cr = card(b, "credits")
        cr.pack(fill="x", pady=(px(GAP), 0))
        pw.label(cr.body, "Built with NMS.py and pyMHF by monkeyman192 and contributors (MIT), Pymem, NumPy and "
                          "Pillow. Game files compiled with MBINCompiler (monkeyman192). Every sound was made for "
                          "this mod.", "label", wrap=px(740)).pack(anchor="w")
        pw.label(cr.body, "A fan mod: not made by or affiliated with Hello Games, Marvel or Disney. No Man's Sky "
                          "© Hello Games.", "help", wrap=px(740)).pack(anchor="w", pady=(px(6), 0))
        tc = card(b, "tools")
        tc.pack(fill="x", pady=(px(GAP), 0))
        g = tk.Frame(tc.body, bg=pw.CARD)
        g.pack(fill="x")
        items = (("OPEN README", lambda: app.open_path(app.readme()), "The guide: install, controls, uninstall."),
                 ("OPEN SETTINGS FOLDER", app.open_folder, "settings.ini and the logs."),
                 ("COPY DIAGNOSTICS", app.copy_diagnostics,
                  "What's running, the suit's state and its last 36 log lines, onto the clipboard (your user name "
                  "is left out). Paste it into a bug report."),
                 ("UNDO MY CHANGES", self.ctx.undo_session,
                  "Every setting back to how it was before Suit Control changed anything this time."))
        for i, (label, cmd, tip) in enumerate(items):
            g.columnconfigure(i % 2, weight=1, uniform="tools")
            bt = pw.Button(g, label, cmd, tip=tip)
            bt.grid(row=i // 2, column=i % 2, sticky="ew", pady=(0, px(8)), padx=(0, px(8) if i % 2 == 0 else 0))
        rr = tk.Frame(tc.body, bg=pw.CARD)
        rr.pack(fill="x", pady=(px(4), 0))
        pw.HoldButton(rr, "RESET ALL TO DEFAULTS", self.ctx.reset_all, hold=1.2, hold_text="HOLD TO RESET ALL",
                      tip="Every setting (keys and controller too) back to how the mod ships. Your game path stays. "
                          "Undo puts them back.").pack(side="left")
        pw.label(rr, "Keeps your game path and your own notes in settings.ini.", "help").pack(
            side="left", padx=(px(14), 0))
        lg = card(b, "recent log")
        lg.pack(fill="x", pady=(px(GAP), 0))
        lg.header(pw.Button(lg, "COPY LOG", self._copy_log, kind="ghost", height=px(26), bg=pw.CARD))
        self.log = pw.label(lg.body, "", "mono", colour=pw.TEXT_DIM, wrap=px(760))
        self.log.pack(anchor="w", fill="x")
        self.lines = []
        self.reload()
    def _copy_log(self):
        self.app.clip("\n".join(self.lines) or "(the suit has logged nothing yet)")
        self.ctx.toast("The recent log is on the clipboard")
    def reload(self):
        a = self.app
        self.ver.configure(text=f"Version {a.version()}  //  Suit Control: {a.keys_text('panel')} in the game "
                                "opens it")
        self.refresh(self.ctx.status(), force=True)
    def refresh(self, status=None, force=False):
        a = self.app
        text = a.build_light()[1]
        bt = "Game b" + text[1:] if text.startswith("Build") else text
        if force or self.cache.get("build") != bt:
            self.cache["build"] = bt
            self.build.configure(text=bt)
        now = time.perf_counter()
        if not force and now - self.cache.get("log_t", 0.0) < 1.0:
            return
        self.cache["log_t"] = now
        lines = a.log_lines()
        if force or lines != self.lines:
            self.lines = lines
            self.log.configure(text="\n".join(lines[-36:]) or "The suit hasn't logged anything yet.")
def _force_stop(client, progress=None):
    try:
        st = client.status()
        if not panel_proc.script_running():
            return panel_proc.Result(True, "the flight script isn't running: nothing to stop", 0)
        if control.suit_state(st)[0] != "not_responding":
            return panel_proc.Result(False, "the suit is answering again: nothing was stopped", 0)
    except Exception as e:
        return panel_proc.Result(False, f"couldn't check the suit ({e}): nothing was stopped", 0)
    return panel_proc.force_stop(client, progress)
class World:
    def __init__(self):
        self.q = queue.Queue()
        self.stop_ev = threading.Event()
        self.kick = threading.Event()
        self.mod = panel_proc.ModWatch()
        self._hud = None
        self._hud_err = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="suit-probe")
    def start(self):
        self.thread.start()
    def stop(self):
        self.stop_ev.set()
        self.kick.set()
    def _run(self):
        info, slow_t, build_t, pad_t = {}, -1e9, -1e9, -1e9
        while not self.stop_ev.is_set():
            try:
                p = panel_proc.probe()
                self.mod.update(bool(p["nms_pid"]))
                p["mod"], p["mod_age"] = self.mod.state()
                now = time.perf_counter()
                if now - slow_t > 5.0:
                    slow_t = now
                    try:
                        import modsguard
                        info["mods_disabled"], info["mods_known"] = bool(modsguard.disabled()), True
                    except Exception:
                        info["mods_known"] = False
                if now - build_t > 60.0:
                    build_t = now
                    try:
                        import flim_paths
                        info["build"] = flim_paths.steam_build_id()
                    except Exception:
                        info["build"] = None
                if now - pad_t > 2.0:
                    pad_t = now
                    try:
                        import xpad
                        info["pads"] = sorted(xpad.slots())
                    except Exception:
                        info["pads"] = []
                p.update(info)
                self.q.put(p)
            except Exception:
                log("probe: " + traceback.format_exc(limit=3))
            self.kick.wait(1.0)
            self.kick.clear()
    def latest(self):
        p = None
        while True:
            try:
                p = self.q.get_nowait()
            except queue.Empty:
                return p
    def status(self, client):
        return client.status()
    def hud(self, now):
        if hud is None or self._hud_err:
            return False, None
        try:
            if self._hud is None:
                self._hud = mmap.mmap(-1, hud.HUD_SIZE, tagname=hud.HUD_NAME)
            t, st = hud.unpack_hud(self._hud)
            return (t > 0 and now - t < 1.0), st
        except Exception:
            self._hud_err = True
            log("HUD block: " + traceback.format_exc(limit=2))
            return False, None
    def tick(self, now):
        pass
    def job(self, kind, client):
        fn = {"start": panel_proc.start_suit, "restart": panel_proc.restart_suit, "power": panel_proc.power_down,
              "force": _force_stop}.get(kind)
        if kind == "game":
            return panel_proc.Job(lambda progress=None: panel_proc.start_game(progress))
        return panel_proc.Job(fn, client)
class DemoWorld(World):
    SCENARIOS = ("online", "flying", "nogame", "offline", "starting", "stuck")
    def __init__(self, suffix, scenario="online"):
        super().__init__()
        self.server = control.Server(suffix=suffix, version="dev", beat=True)
        self.scenario = scenario
        self.t0 = time.perf_counter()
        for line in ("suit online: double-tap Space to fly", "flight on", "afterburner", "sonic boom: 3 blasts",
                     "hard brake", "super-hero landing", "flight off"):
            self.server.log(line)
    def start(self):
        pass
    def stop(self):
        try:
            self.server.stop_beat()
        except Exception:
            pass
    def set(self, scenario):
        self.scenario = scenario
        self.t0 = time.perf_counter()
    def latest(self):
        s = self.scenario
        return dict(t=time.perf_counter(), nms_pid=0 if s == "nogame" else 4242, nms_hwnd=0, game_fg=False,
                    fg_hwnd=0, fg_pid=0, script=s not in ("nogame", "offline"),
                    mod="off" if s == "nogame" else "live", mod_age=0.02, mods_disabled=False, mods_known=True,
                    build="26385139", pads=[0])
    def status(self, client):
        if self.scenario == "nogame":
            return control.parse_status(bytes(control.STS_SIZE))
        if self.scenario == "offline":
            raw = bytearray(control.STS_SIZE)
            struct.pack_into(control.STS_HDR_FMT, raw, 0, control.STS_MAGIC, control.PROTO, 3, 0x7FFFFFF0, 8, 1.0,
                             1.0, b"dev", 0)
            struct.pack_into(control.LINE_FMT, raw, control.STS_LINE_OFF, 1, 1.0, b"flight off: End held")
            return control.parse_status(bytes(raw))
        return client.status()
    def _flags(self, *names):
        f = 0
        for n in names:
            f |= control.FL[n]
        return f
    def hud(self, now):
        s = self.scenario
        if s in ("nogame", "offline", "stuck"):
            return False, None
        st = dict(hud.idle_state()) if hud else {}
        if s == "starting":
            st.update(stage=2, prog=0.62)
        elif s == "flying":
            st.update(flags=1, fuel=0.72, charge=0.75, throttle=0.0, speed=3.0)
        else:
            st.update(fuel=1.0, charge=1.0, throttle=0.0)
        return True, st
    def tick(self, now):
        s = self.scenario
        srv = self.server
        for c in srv.poll():
            nm, msg, state = c["name"], "done", control.DONE
            if nm == "reload":
                msg = "applied"
            elif nm == "quit":
                self.set("offline")
            elif nm == "ping":
                msg = "pong"
            srv.ack(c["seq"], state, 0, msg)
        if s in ("nogame", "offline"):
            return
        base = self._flags("armed", "mod_live", "character_ok", "hud_alive", "warpfx_alive", "panel_seen")
        tel = dict(flags=base, flags2=0, startup_stage=3, startup_progress=1.0, speed=0.0, throttle=0.0,
                   cruise_level=0.0, ab_fuel=1.0, sonic_meter=1.0, speed_level=0.0, min_speed=5.0, max_speed=80.0,
                   height=-1.0, loop_hz=60.0, mod_age=0.02, player_mode=0, settings_warnings=0, away_s=-1.0)
        phase = 1
        if s == "starting":
            phase = 0
            tel.update(startup_stage=2, startup_progress=0.62, flags=self._flags("mod_live", "hud_alive"))
        elif s == "flying":
            tel.update(flags=base | self._flags("flying", "suspended"), speed=3.0, ab_fuel=0.72,
                       sonic_meter=0.75, away_s=12.0 + (now - self.t0), height=42.0)
        elif s == "stuck":
            tel["loop_t"] = now - 41.0
        srv.publish(phase=phase, **tel)
        srv.line({"starting": "syncing: take a few steps", "stuck": "re-finding your character"}.get(
            s, "suit online"))
    def job(self, kind, client):
        return DemoJob(self, kind)
class DemoJob:
    STEPS = {"start": (("checking that you're in the world ...", 0.5), ("powering up the suit ...", 0.8)),
             "restart": (("waiting for the suit to power down ...", 0.8), ("powering up the suit ...", 0.8)),
             "power": (("waiting for the suit to power down ...", 0.8),),
             "force": (("stopping the flight script ...", 0.6),),
             "game": (("starting No Man's Sky through Steam ...", 0.8),)}
    AFTER = {"start": "starting", "restart": "starting", "power": "offline", "force": "offline", "game": "offline"}
    def __init__(self, world, kind):
        self.events, self.done, self.result = queue.Queue(), False, None
        self.world, self.kind = world, kind
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        for text, secs in self.STEPS.get(self.kind, ()):
            self.events.put(text)
            time.sleep(secs)
        self.world.set(self.AFTER.get(self.kind, "online"))
        self.result = panel_proc.Result(True, {"start": "the suit is starting", "restart": "the suit is starting",
                                               "power": "the suit is powered down", "force": "stopped",
                                               "game": "starting the game"}.get(self.kind, "done"), 0)
        self.done = True
class NullClient:
    suffix = ""
    def status(self):
        return control.parse_status(bytes(control.STS_SIZE))
    def __getattr__(self, name):
        def nothing(*a, **k):
            return 0 if name in ("send", "show_count", "show_request") else None
        return nothing
class App:
    JOB_TITLES = {"start": "POWERING UP", "restart": "RESTARTING", "power": "POWERING DOWN", "force": "STOPPING",
                  "game": "STARTING THE GAME"}
    def __init__(self, root, guard, args, lock=None):
        self.root, self.guard, self.args, self.lock = root, guard, args, lock
        self.demo = bool(args.demo or args.preview)
        self.preview = bool(args.preview)
        self.visible = False
        self.page = None
        self.st = {}
        self.suit = ("offline", "not started")
        self.probe = {}
        self.mod_state = "off"
        self.job = None
        self.job_kind = None
        self.job_title = ""
        self.job_text = ""
        self.restart_pending = set()
        self.session = None
        self.raise_seen = None
        self.show_seen = None
        self.hotkey_t = 0.0
        self.nms_gone_t = None
        self._n = 0
        self._gauge_after = None
        self._gauge_key, self._gauge_t = None, 0.0
        self._err_t = 0.0
        self.hotkey = None
        self.objs = {}
        self.scroll = {}
        self.rail = {}
        self.menu = None
        self.supported_build = ""
        self.supported_steam = set()
        self.front = False
        self.demo_dir = None
        try:
            import flim_paths
            self.supported_build = flim_paths.SUPPORTED_BUILD
            self.supported_steam = {str(b) for b in getattr(flim_paths, "SUPPORTED_STEAM_BUILDS", ())}
        except Exception:
            pass
        if self.demo:
            suffix = f"Demo{os.getpid()}"
            self.client = control.Client(suffix=suffix)
            self.world = DemoWorld(suffix, args.scenario or "online")
            d = self.demo_dir = Path(tempfile.mkdtemp(prefix="SuitControlDemo-"))
            ini = d / "settings.ini"
            try:
                src = settings.INI if settings.INI.exists() else settings.DEFAULT_INI
                ini.write_bytes(src.read_bytes())
            except OSError:
                pass
            self.state = PanelState(d / "panel.json", enabled=False)
        else:
            try:
                self.client = control.Client()
            except OSError as e:
                log(f"control blocks: {e!r}")
                self.client = NullClient()
            self.world = World()
            ini = settings.INI
            self.state = PanelState(settings.INI.with_name("panel.json"))
        self.ctx = Ctx(self, ini)
        self.show_seen = self.client.show_count() if not isinstance(self.client, NullClient) else 0
        self.build()
    def build(self):
        root, px = self.root, pw.px
        root.title(TITLE)
        root.configure(bg=pw.BG)
        root.report_callback_exception = self._tk_error
        W, H = px(1080), px(760)
        self.outer = tk.Frame(root, bg=pw.BG, width=W, height=H)
        self.outer.pack(fill="both", expand=True)
        self.outer.pack_propagate(False)
        self.head = tk.Canvas(self.outer, bg=pw.BG, height=px(44), highlightthickness=0, bd=0, takefocus=0)
        self.head.pack(fill="x")
        self.head.bind("<Configure>", lambda e: self.draw_header())
        self.menu_btn = Dots(self.head, self.toggle_menu, tip="Keep on top, the settings folder, diagnostics, "
                                                                "quit Suit Control")
        body = tk.Frame(self.outer, bg=pw.BG)
        body.pack(fill="both", expand=True)
        rail = tk.Frame(body, bg=pw.BG, width=px(208))
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Frame(body, bg=pw.mix(pw.BG, pw.TEXT, 0.08), width=pw._lw(1)).pack(side="left", fill="y")
        accents = dict(RAIL_ACCENT)
        if panel_pages is not None:
            accents.update(getattr(panel_pages, "RAIL_ACCENT", {}) or {})
        tk.Frame(rail, bg=pw.BG, height=px(10)).pack()
        for i, name in enumerate(PAGES):
            ri = pw.RailItem(rail, name, command=(lambda n=name: self.select(n)), accent=accents.get(name),
                             width=px(208), tip=f"Ctrl+{i + 1}")
            ri.pack(fill="x")
            self.rail[name] = ri
        foot = tk.Frame(rail, bg=pw.BG)
        foot.pack(side="bottom", fill="x", padx=px(16), pady=(0, px(16)))
        self.back_btn = pw.Button(foot, "BACK TO GAME", self.back_to_game, width=px(160))
        self.back_btn.pack(anchor="w")
        self.rail_hint = pw.label(foot, "", "help")
        self.rail_hint.pack(anchor="w", pady=(px(6), 0))
        self.content = tk.Frame(body, bg=pw.BG)
        self.content.pack(side="left", fill="both", expand=True)
        notices = tk.Frame(self.content, bg=pw.BG)
        notices.pack(fill="x", padx=(px(24), px(34)), pady=(px(8), 0))
        self.banner = pw.InlineStrip(notices, "warn")
        self.banner.pack(fill="x")
        self.strip = pw.InlineStrip(notices, "error")
        self.strip.pack(fill="x")
        self.note = pw.InlineStrip(notices, "info")
        self.note.pack(fill="x")
        self.note_closed = False
        self.stack = tk.Frame(self.content, bg=pw.BG)
        self.stack.pack(fill="both", expand=True)
        self._toast = pw.Toast(self.content)
        for name in PAGES:
            sp = pw.ScrollPage(self.stack)
            self.scroll[name] = sp
            try:
                if name == "HOME":
                    obj = HomePage(self, sp)
                elif name == "ABOUT":
                    obj = AboutPage(self, sp)
                elif panel_pages is not None and name in getattr(panel_pages, "PAGES", {}):
                    obj = panel_pages.PAGES[name](sp, self.ctx)
                else:
                    obj = self._missing_page(sp, name, PAGES_ERR or "this page isn't built yet")
            except Exception:
                tb = traceback.format_exc(limit=6)
                log(f"page {name} failed to build:\n{tb}")
                for w in sp.body.winfo_children():
                    w.destroy()
                obj = self._missing_page(sp, name, tb)
            self.objs[name] = obj
        self._rail_foot()
        root.bind("<Escape>", self._esc)
        for i, name in enumerate(PAGES):
            root.bind(f"<Control-Key-{i + 1}>", lambda e, n=name: self.select(n))
        root.bind_all("<ButtonPress-1>", self._click_anywhere, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close_x)
        last = self.state.get("page", "HOME")
        self.select(last if last in PAGES and not self.preview else "HOME", quiet=True)
    def _missing_page(self, sp, name, why):
        c = card(sp.body, f"{name.lower()} isn't available")
        c.pack(fill="x")
        pw.label(c.body, "This page didn't load. The other pages work; the details are in panel_log.txt.",
                 "label", wrap=pw.px(740)).pack(anchor="w")
        pw.label(c.body, scrub(why.strip().splitlines()[-1] if why.strip() else why), "help",
                 wrap=pw.px(740)).pack(anchor="w", pady=(pw.px(6), 0))
        class Missing:
            def refresh(self, status=None):
                pass
        return Missing()
    def draw_header(self):
        c, px = self.head, pw.px
        c.delete("all")
        w, h = max(c.winfo_width(), px(400)), px(44)
        c.create_rectangle(0, 0, pw._lw(3), h, fill=pw.STRIP, outline="")
        cx, cy, r = px(26), h // 2, px(9)
        c.create_polygon(cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy, outline=pw.TEXT, fill="", width=pw._lw(2))
        q = r * 0.45
        c.create_polygon(cx, cy - q, cx + q, cy, cx, cy + q, cx - q, cy, fill=pw.TEXT, outline="")
        fh = pw.font("head")
        t = pw.spaced("suit control")
        c.create_text(px(46), pw._caps_y(fh, cy), text=t, font=fh, fill=pw.TEXT, anchor="w")
        c.create_text(px(46) + fh.measure(t) + px(18), pw._caps_y(pw.font("help"), cy), anchor="w",
                      text=pw.spaced("fly like iron man") + "  //  " + pw.spaced(f"by {AUTHOR}"),
                      font=pw.font("badge"), fill=pw.TEXT_DIM)
        c.create_rectangle(0, h - pw._lw(1), w, h, fill=pw.mix(pw.BG, pw.TEXT, 0.12), outline="")
        c.create_window(w - px(12), cy, window=self.menu_btn, anchor="e")
        x = w - px(12) - int(self.menu_btn.cget("width")) - px(18)
        fb = pw.font("badge")
        for name, state in reversed(self.header_lights()):
            s = pw.spaced(name)
            tw = fb.measure(s)
            c.create_text(x, pw._caps_y(fb, cy), text=s, font=fb, anchor="e",
                          fill=pw.TEXT if state != "off" else pw.TEXT_DIM)
            x -= tw + px(8)
            sq = px(9)
            c.create_rectangle(x - sq - pw._lw(2), cy - sq // 2 - pw._lw(2), x + pw._lw(2), cy + sq // 2 + pw._lw(2),
                               fill=pw.LINE, outline="")
            e, m = pw.LIGHT_COLOURS.get(state, pw.LIGHT_COLOURS["off"])
            y0, n = cy - sq // 2, 3
            for i in range(n):
                f = 1.0 - abs(2.0 * (i + 0.5) / n - 1.0)
                c.create_rectangle(x - sq, y0 + sq * i // n, x, y0 + sq * (i + 1) // n, fill=pw.mix(e, m, f),
                                   outline="")
            x -= sq + px(20)
        self._hdr = tuple(self.header_lights())
    def build_light(self):
        sup, bid = self.supported_build, str(self.probe.get("build") or "")
        if not bid:
            return "off", f"Made for build {sup} // not a Steam install, can't tell"
        if bid == sup:
            return "ok", f"Build {sup} // supported"
        if bid in self.supported_steam:
            return "ok", f"Build {sup} (Steam {bid}) // supported"
        return "warn", f"Steam build {bid}: the mod is made for build {sup}; an update may be needed"
    def header_lights(self):
        nms = bool(self.probe.get("nms_pid"))
        s = self.suit[0]
        mod = {"live": "ok", "paused": "warn", "not_attached": "warn"}.get(self.mod_state, "off")
        suit = {"online": "ok", "busy": "busy", "not_responding": "bad"}.get(s, "off")
        if s == "online" and (self.st.get("phase") in ("starting", "quitting") or
                              self.st.get("startup_stage") in (1, 2)):
            suit = "busy"
        return [("game", "ok" if nms else "off"), ("mod", mod), ("suit", suit)]
    def select(self, name, quiet=False):
        if name not in PAGES or name == self.page:
            return
        old = self.page
        if old is not None:
            self.scroll[old].place_forget()
            self.rail[old].set_selected(False)
            self._call(old, "on_hide")
        self.page = name
        sp = self.scroll[name]
        sp.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.rail[name].set_selected(True)
        self._call(name, "on_show")
        self._refresh_page()
        self._notes()
        if not quiet:
            self.state.set(page=name)
        self.draw_gauge(force=True)
    def _call(self, name, method, *a):
        fn = getattr(self.objs.get(name), method, None)
        if fn is None:
            return None
        try:
            return fn(*a)
        except Exception:
            self._page_error(name, method)
            return None
    def _page_error(self, name, method):
        tb = traceback.format_exc(limit=5)
        now = time.perf_counter()
        if now - self._err_t > 5.0:
            self._err_t = now
            log(f"{name}.{method}:\n{tb}")
            self.strip.show(f"Something went wrong on {name} (written to panel_log.txt)", "error")
    def _refresh_page(self):
        if self.page:
            st = self.st if self.st.get("alive") else None
            self._call(self.page, "refresh", st)
    def reload_pages(self):
        for name in PAGES:
            self._call(name, "reload")
        for cb in list(self.ctx._listeners):
            try:
                cb()
            except Exception:
                log("on_settings listener: " + traceback.format_exc(limit=3))
    def saved(self, keys, ok, text):
        for name in PAGES:
            if hasattr(self.objs.get(name), "saved"):
                self._call(name, "saved", set(keys), ok, text)
    def settings_changed(self, keys):
        if ("keys", "panel") in keys or any(k[0] == "keys" for k in keys):
            self._hotkey_sync()
            self._rail_foot()
        if ("panel", "always_on_top") in keys:
            self._topmost()
    def _notes(self):
        want = self.page in SETTINGS_PAGES and not self.st.get("alive") and not self.note_closed
        if want and not self.note.shown:
            self.note.show("The suit is off: changes are saved and apply when it starts.", "info", close=False)
        elif not want and self.note.shown:
            self.note.hide()
    def toast(self, text, kind="ok", action=None):
        try:
            self._toast.show(text, kind, action, timeout=2.5 if not action else 5.0)
        except tk.TclError:
            pass
    def start(self):
        if isinstance(self.client, NullClient):
            self.strip.show("Suit Control can't reach the suit: start it the same way as the game (both normally, "
                            "or both as administrator).", "error", close=False)
        self.world.start()
        if not self.demo:
            self._hotkey_start()
        self._tick()
        if not (self.args.warm and not self.demo):
            self.root.after(10, lambda: self.show("launch"))
    def _tick(self):
        n = self._n = self._n + 1
        now = time.perf_counter()
        try:
            self._hotkey_poll(now)
            if not isinstance(self.client, NullClient) and n % 2 == 0:
                c = self.client.show_count()
                if c != self.show_seen:
                    self.show_seen = c
                    self.show("handoff")
            self._job_poll()
            self.ctx.drain()
            p = self.world.latest()
            if p is not None:
                self._probe(p, now)
            every = (2 if self.front or not self.probe.get("game_fg") else 5) if self.visible else 20
            if n % every == 0 or n == 1:
                self.world.tick(now)
                self.status_tick(now)
            if n % 5 == 0:
                self._beat()
            if n % 20 == 0:
                self.ctx.external_change()
                self._idle_exit(now)
        except Exception:
            log("tick: " + traceback.format_exc(limit=5))
        try:
            self.root.after(TICK_MS, self._tick)
        except tk.TclError:
            pass
    def _probe(self, p, now):
        self.probe = p
        self.mod_state = p.get("mod", "off")
        if p.get("nms_pid"):
            self.nms_gone_t = None
        elif self.nms_gone_t is None:
            self.nms_gone_t = now
        self._rail_foot()
    def _rail_foot(self):
        game = bool(self.probe.get("nms_pid"))
        want = (game, self.keys_text("panel"))
        if want == getattr(self, "_foot", None):
            return
        self._foot = want
        self.back_btn.set_text("BACK TO GAME" if game else "MINIMISE")
        self.back_btn.set_tip(f"Esc or {want[1]} does this too" if game else "Esc does this too")
        self.rail_hint.configure(text=f"{want[1]} or Esc" if game else "")
    def status_tick(self, now=None):
        now = time.perf_counter() if now is None else now
        try:
            st = self.world.status(self.client)
        except Exception:
            log("status: " + traceback.format_exc(limit=2))
            st = control.parse_status(bytes(control.STS_SIZE))
        self.st = st
        self.suit = control.suit_state(st, now)
        if self.suit[0] == "not_responding" and self.probe.get("script") is False:
            self.suit = ("offline", "stopped without saying why (killed or crashed)")
            st = self.st = dict(st, alive=False, responding=False)
        if st.get("magic") and st["session"] != self.session:
            if self.session is not None:
                self.ctx.drop_waits()
                self.restart_pending.clear()
                self.raise_seen = None
            self.session = st["session"]
        self.ctx.poll_acks(now)
        if st.get("alive"):
            rr = st.get("raise_req", 0)
            if self.raise_seen is None:
                self.raise_seen = rr
            elif rr != self.raise_seen:
                self.raise_seen = rr
                if now - self.hotkey_t > 1.0:
                    self.show("raise")
        if not self.visible:
            return
        self._refresh_page()
        self._banner()
        self._notes()
        if tuple(self.header_lights()) != getattr(self, "_hdr", None):
            self.draw_header()
    def _banner(self):
        st = self.st
        want = bool(st.get("alive") and st.get("flying") and st.get("suspended") and not st.get("space"))
        if want:
            left = 60.0 - max(0.0, st.get("away_s", 0.0))
            key = self.keys_text("panel")
            text = (f"SUIT HOLDING POSITION // BACK TO GAME: {key} OR ESC // " +
                    (f"STARTS COMING DOWN IN {clock(left)}" if left > 0 else "COMING DOWN SLOWLY"))
            if not self.banner.shown:
                self.banner.show(text, "warn", close=False)
            elif self.banner.msg != text:
                self.banner.msg = text
                self.banner.redraw()
        elif self.banner.shown:
            self.banner.hide()
    def _beat(self):
        try:
            hwnd = int(self.root.wm_frame(), 16) if not self.preview else 0
        except (tk.TclError, ValueError):
            hwnd = 0
        fg = self.front = self.visible and foreground_pid() == os.getpid()
        hk = bool(self.hotkey and self.hotkey.registered)
        try:
            self.client.beat(visible=self.visible, foreground=fg, hotkey=hk, hwnd=hwnd)
        except Exception:
            pass
    def _idle_exit(self, now):
        if self.demo or self.visible or self.nms_gone_t is None:
            return
        if now - self.nms_gone_t > HIDDEN_EXIT_S and self.job is None:
            log("the game is gone and the panel is hidden: quitting")
            self.quit()
    def draw_gauge(self, force=False):
        if not (self.visible and self.page == "HOME"):
            if self._gauge_after is not None:
                try:
                    self.root.after_cancel(self._gauge_after)
                except tk.TclError:
                    pass
                self._gauge_after = None
            return
        home = self.objs.get("HOME")
        if not isinstance(home, HomePage):
            return
        now = time.perf_counter()
        fresh, st = self.world.hud(now)
        live = bool(fresh and st is not None)
        key = (tuple(round(float(st.get(k, 0.0) or 0.0), 3) for k in
                     ("fuel", "charge", "sonic", "build", "throttle", "cruise")) + (int(st.get("flags", 0)),)
               if live else None)
        age = now - self._gauge_t
        away = bool(self.probe.get("game_fg")) and not self.front
        if away:
            due = age >= GAUGE_AWAY_S
        else:
            due = (key != self._gauge_key and age >= GAUGE_MS / 1000.0 - 0.01) or age >= GAUGE_IDLE_S
        if force or due or (not live and self._gauge_key is not None):
            home.gauge.draw(live, st, now)
            self._gauge_key, self._gauge_t = key, now
        self._readout(home.gauge, live)
        if self._gauge_after is None and not pw.REDUCE_MOTION:
            self._gauge_after = self.root.after(GAUGE_MS, self._gauge_loop)
    def _gauge_loop(self):
        self._gauge_after = None
        self.draw_gauge()
    def _readout(self, g, fresh):
        st = self.st
        if not st.get("alive") or self.suit[0] == "not_responding":
            g.readout("—", "M/S", "", "SUIT OFFLINE" if not st.get("alive") else "NOT RESPONDING", live=False)
            return
        spd = float(st.get("speed", 0.0))
        if st.get("cruise") and spd >= 1000:
            num, unit, alt = f"{spd / 1000:.0f}", "KM/S", f"{spd * 3.6:,.0f} km/h"
        else:
            num, unit = f"{spd:.0f}", "M/S"
            alt = f"{spd * 3.6:.0f} km/h" + (f"  //  {st['height']:.0f} m up" if st.get("height", -1) >= 0 else "")
        g.readout(num, unit, alt, flight_mode(st), live=fresh)
    def show(self, why="launch"):
        if self.preview:
            return
        self.guard.block = False
        pw.pause_animations(False)
        was = self.visible
        self.visible = True
        try:
            if not was:
                self._place()
            self.root.deiconify()
            self.root.lift()
            hwnd = int(self.root.wm_frame(), 16)
            if not was:
                dark_frame(hwnd)
            if panel_proc.raise_window(hwnd):
                self.root.focus_force()
                self._topmost()
            else:
                self.root.attributes("-topmost", True)
                self.root.after(4000, self._topmost)
        except tk.TclError:
            pass
        self.world.kick.set()
        self.status_tick()
        self.draw_header()
        self.draw_gauge(force=True)
        self._call(self.page, "on_show")
    def hide(self, to_game=True):
        if not self.visible:
            return
        if not self.demo and not self.probe.get("nms_pid"):
            try:
                self.root.iconify()
            except tk.TclError:
                pass
            return
        self._remember_place()
        self.visible = False
        self.close_menu()
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        self.guard.block = True
        pw.pause_animations(True)
        self._call(self.page, "on_hide")
        if to_game and not self.demo and self.probe.get("nms_pid"):
            threading.Thread(target=panel_proc.focus_game, daemon=True, name="suit-focus").start()
    def back_to_game(self):
        self.hide(to_game=True)
    def toggle(self):
        if self.visible and foreground_pid() == os.getpid():
            self.hide()
        else:
            self.show("hotkey")
    def _esc(self, e=None):
        w = self.root.focus_get()
        if isinstance(w, pw.KeyCap) and w.capturing:
            return
        if self.menu is not None:
            self.close_menu()
            return
        self.hide()
    def close_x(self):
        if self.demo or not self.probe.get("nms_pid"):
            self.quit()
            return
        if not self.state.get("x_note"):
            self.state.set(x_note=True)
            self.state.save()
            self.strip.show(f"Suit Control keeps running: {self.keys_text('panel')} in the game brings it back.",
                            "info")
            self.root.after(1800, self.hide)
            return
        self.hide()
    def quit(self):
        self._remember_place()
        try:
            self.ctx.flush(sync=True)
        except Exception:
            pass
        self.state.save()
        self.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
    def close(self):
        if self.hotkey:
            self.hotkey.stop()
        self.world.stop()
        if self.lock:
            self.lock.close()
            self.lock = None
        if self.demo_dir is not None:
            import shutil
            shutil.rmtree(self.demo_dir, ignore_errors=True)
            self.demo_dir = None
    def _topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.ctx.get("panel", "always_on_top")))
        except tk.TclError:
            pass
    def _place(self):
        W, H = pw.px(1080), pw.px(760)
        mons = monitors()
        s = self.state
        g = s.get("geom")
        if isinstance(g, list) and len(g) == 4:
            x, y, w, h = (int(v) for v in g)
            for m in mons:
                l, t, r, b = m["work"]
                if m["name"] == s.get("monitor") and l <= x + 80 < r and t <= y + 20 < b:
                    self.root.geometry(f"{max(w, pw.px(860))}x{max(h, pw.px(560))}+{x}+{y}")
                    return
        mon = monitor_of(self.probe.get("nms_hwnd") or panel_proc.nms_window()) or next(
            (m for m in mons if m["primary"]), None)
        if mon:
            l, t, r, b = mon["work"]
            x, y = l + max(0, (r - l - W) // 2), t + max(0, (b - t - H) // 2)
            self.root.geometry(f"{W}x{H}+{x}+{y}")
    def _remember_place(self):
        if self.preview or not self.visible:
            return
        try:
            if self.root.state() != "normal":
                return
            import re
            g = re.match(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)", self.root.wm_geometry())
            if not g:
                return
            w, h, x, y = (int(v.replace("+-", "-").replace("--", "-")) for v in g.groups())
            m = monitor_of(int(self.root.wm_frame(), 16))
            self.state.set(geom=[x, y, w, h], monitor=m["name"] if m else "")
            self.state.save()
        except (tk.TclError, ValueError, TypeError):
            pass
    def _hotkey_vks(self):
        S = self.ctx.S
        vk = S.keys.get("panel", 0)
        blocked = [S.keys[k] for k in settings.KEY_SETTINGS if k != "panel" and S.keys.get(k)] + list(NAV_KEYS)
        return vk, blocked
    def _hotkey_start(self):
        vk, blocked = self._hotkey_vks()
        try:
            self.hotkey = panel_proc.HotkeyThread(vk, blocked)
            self.hotkey.start()
        except Exception:
            log("hotkey: " + traceback.format_exc(limit=3))
            self.hotkey = None
        self._bind_key()
    def _hotkey_sync(self):
        if self.hotkey:
            vk, blocked = self._hotkey_vks()
            self.hotkey.set_vk(vk, blocked)
        self._bind_key()
    def _bind_key(self):
        old = getattr(self, "_bound", None)
        if old:
            try:
                self.root.unbind(old)
            except tk.TclError:
                pass
        name = self.keys_text("panel")
        self._bound = None
        if name.startswith("F") and name[1:].isdigit():
            self._bound = f"<KeyPress-{name}>"
            self.root.bind(self._bound, lambda e: (None if self.hotkey and self.hotkey.registered else self.hide()))
    def _hotkey_poll(self, now):
        if not self.hotkey:
            return
        while True:
            try:
                ev = self.hotkey.queue.get_nowait()
            except queue.Empty:
                return
            if ev == "toggle":
                self.hotkey_t = now
                self.toggle()
    def keys_text(self, action):
        k = self.ctx.get("keys", action)
        return pw.key_label(k) if k and k != "none" else "—"
    def run_job(self, kind):
        if self.job is not None:
            return
        if kind == "force" and not self.can_force_stop():
            self.toast("FORCE STOP is only for a suit that isn't responding: give it a moment", "info")
            return
        if kind in ("start", "restart"):
            self.ctx.flush(sync=True)
        try:
            self.job = self.world.job(kind, self.client)
        except Exception as e:
            log(f"job {kind}: {e!r}")
            self.strip.show(f"Couldn't {kind}: {e}", "error")
            return
        self.job_kind = kind
        self.job_title = self.JOB_TITLES.get(kind, kind.upper())
        self.job_text = "…"
        self._call("HOME", "refresh", None)
    def _job_poll(self):
        j = self.job
        if j is None:
            return
        changed = False
        while True:
            try:
                t = j.events.get_nowait()
            except queue.Empty:
                break
            self.job_text = t[:1].upper() + t[1:]
            changed = True
        if j.done:
            r = j.result or panel_proc.Result(False, "it stopped without a result", 0)
            kind = self.job_kind
            self.job, self.job_kind = None, None
            text = r.text[:1].upper() + r.text[1:] if r.text else ("Done" if r.ok else "That didn't work")
            if r.ok:
                self.toast(text, "ok")
                if kind in ("restart", "start"):
                    self.restart_pending.clear()
            else:
                if "FORCE STOP" in r.text:
                    text = text.split(":")[0] + (
                        ". It may still be finishing: if it stops responding, HOME offers FORCE STOP (hold it).")
                self.strip.show(text, "error")
            log(f"{kind}: {'ok' if r.ok else 'failed'}: {r.text}")
            self.world.kick.set()
            try:
                now = time.perf_counter()
                self.world.tick(now)
                self.status_tick(now)
            except Exception:
                log("job status: " + traceback.format_exc(limit=2))
            changed = True
        if changed and self.page == "HOME":
            self._call("HOME", "refresh", None)
    def can_force_stop(self):
        return self.suit[0] == "not_responding" and (self.demo or self.probe.get("script") is not False)
    def force_stop(self):
        self.run_job("force")
    def send_in_game(self, cmd, doing):
        if not self.ctx.running():
            self.strip.show("The suit is off: power it up first", "warn")
            return
        def acked(a, cmd=cmd):
            if a is None:
                self.toast(f"The suit didn't answer ({cmd})", "warn")
            elif a[0] != "done":
                self.toast(f"{doing}: {a[2] or a[0]}", "warn")
        self.ctx.send(cmd, on_ack=acked)
        self.toast(doing + " (back in the game)", "info")
        self.back_to_game()
    def toggle_menu(self):
        if self.menu is not None:
            self.close_menu()
            return
        px = pw.px
        m = tk.Frame(self.outer, bg=pw.LINE, highlightthickness=0, bd=0)
        inner = tk.Frame(m, bg=pw.CARD)
        inner.pack(padx=pw._lw(3), pady=pw._lw(3))
        tk.Frame(inner, bg=pw.STRIP, width=pw._lw(3)).pack(side="left", fill="y")
        col = tk.Frame(inner, bg=pw.CARD)
        col.pack(side="left", padx=px(8), pady=px(8))
        top = bool(self.ctx.get("panel", "always_on_top"))
        for label, fn in ((f"KEEP ON TOP: {'ON' if top else 'OFF'}", self._toggle_top),
                          ("OPEN SETTINGS FOLDER", self.open_folder),
                          ("COPY DIAGNOSTICS", self.copy_diagnostics),
                          ("QUIT SUIT CONTROL", self.quit)):
            pw.Button(col, label, (lambda f=fn: (self.close_menu(), f())), kind="ghost", width=px(220),
                      height=px(30)).pack(anchor="w")
        m.place(in_=self.outer, relx=1.0, x=-px(10), y=px(46), anchor="ne")
        tk.Misc.tkraise(m)
        self.menu = m
    def close_menu(self):
        if self.menu is not None:
            try:
                self.menu.destroy()
            except tk.TclError:
                pass
            self.menu = None
    def _click_anywhere(self, e):
        if self.menu is None:
            return
        w = e.widget
        while w is not None:
            if w is self.menu or w is self.menu_btn:
                return
            w = getattr(w, "master", None)
        self.close_menu()
    def _toggle_top(self):
        self.ctx.set("panel", "always_on_top", not bool(self.ctx.get("panel", "always_on_top")))
        self._topmost()
    def open_path(self, p):
        try:
            os.startfile(str(p))
        except OSError as e:
            self.strip.show(f"Couldn't open {Path(p).name}: {e.strerror or e}", "error")
    def open_folder(self):
        self.open_path(self.ctx.ini.parent)
    def readme(self):
        for p in (APP / "README.txt", APP.parent / "README.txt", APP / "README_controls_and_details.txt"):
            if p.exists():
                return p
        return APP / "README.txt"
    def version(self):
        for p in (APP / "VERSION.txt", APP.parent / "VERSION.txt"):
            try:
                v = p.read_text(encoding="utf-8").strip().splitlines()[0]
                if v:
                    return v
            except (OSError, IndexError):
                pass
        return "dev"
    def clip(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            pass
    def log_lines(self):
        try:
            got = self.client.log_lines(0) or []
        except Exception:
            got = []
        now, wall = time.perf_counter(), time.time()
        return [time.strftime("%H:%M:%S", time.localtime(wall - (now - t))) + "  " + txt for _, t, txt in got]
    def diagnostics(self):
        st, p = self.st, self.probe
        out = [f"Fly Like Iron Man - Suit Control diagnostics, {time.strftime('%Y-%m-%d %H:%M:%S')}",
               f"version: {self.version()}   python {sys.version.split()[0]}   windows {sys.getwindowsversion().build}"
               f"   scale {pw.SCALE:.2f}   demo {self.demo}",
               f"game: {'running, pid ' + str(p.get('nms_pid')) if p.get('nms_pid') else 'not running'}"
               f"   in front: {p.get('game_fg')}   build {p.get('build')} (made for {self.supported_build})"
               f"   mods disabled: {p.get('mods_disabled')}   mod link: {self.mod_state} ({p.get('mod_age', -1):.2f} s)",
               f"suit: {self.suit[0]} ({self.suit[1]})   phase {st.get('phase')}   pid {st.get('pid')}"
               f"   version {st.get('version')}   beat {st.get('age', 0):.2f} s   loop {st.get('loop_age', 0):.2f} s"
               f"   loop {st.get('loop_hz', 0):.0f} Hz   script mutex {p.get('script')}",
               "flags: " + " ".join(k for k in control.FL if st.get(k)) + "   flags2: " +
               " ".join(k for k in control.FL2 if st.get(k)),
               f"status line: {st.get('line', (0, 0, ''))[2]}",
               f"hotkey: {self.keys_text('panel')} registered {bool(self.hotkey and self.hotkey.registered)}"
               f" {getattr(self.hotkey, 'error', '')}",
               f"settings: {self.ctx.ini}   warnings: {len(self.ctx.S.warnings)}"]
        out += ["  " + w for w in self.ctx.S.warnings]
        out.append("restart pending: " + (", ".join(f"[{s}] {k}" for s, k in sorted(self.restart_pending)) or "no"))
        out.append("")
        out.append("recent log:")
        out += ["  " + ln for ln in self.log_lines()]
        try:
            tail = panel_proc.flight_out_tail(8)
        except Exception:
            tail = []
        if tail:
            out += ["", "flight_out.txt (last lines):"] + ["  " + ln for ln in tail]
        return scrub("\n".join(out))
    def copy_diagnostics(self):
        self.clip(self.diagnostics())
        self.toast("Diagnostics are on the clipboard (no user name in them)")
    def _tk_error(self, tp, val, tb):
        log("".join(traceback.format_exception(tp, val, tb)))
        now = time.perf_counter()
        if now - self._err_t > 5.0:
            self._err_t = now
            try:
                self.strip.show("Something went wrong in Suit Control (written to panel_log.txt)", "error")
            except tk.TclError:
                pass
    PREVIEWS = (("home", "HOME", "online"), ("home_flying", "HOME", "flying"), ("home_nogame", "HOME", "nogame"),
                ("home_offline", "HOME", "offline"), ("home_starting", "HOME", "starting"),
                ("home_stuck", "HOME", "stuck"),
                ("flight", "FLIGHT", "online"), ("powers", "POWERS", "online"), ("sound", "SOUND", "online"),
                ("visuals", "VISUALS", "online"), ("controls", "CONTROLS", "online"), ("about", "ABOUT", "online"),
                ("home_end", "HOME", "online"), ("about_end", "ABOUT", "online"))
    def run_previews(self, which, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        pw.REDUCE_MOTION = True
        self.root.overrideredirect(True)
        want = which.lower()
        jobs = [p for p in self.PREVIEWS if want == "all" or p[0] == want or p[1].lower() == want and
                p[0] == p[1].lower()]
        if not jobs:
            raise SystemExit(f"--preview: no page called {which!r} (all, " +
                             ", ".join(p[0] for p in self.PREVIEWS) + ")")
        self.visible = True
        made = []
        for name, page, scen in jobs:
            self.world.set(scen)
            now = time.perf_counter()
            self.world.tick(now)
            self._probe(self.world.latest(), now)
            self.status_tick(now)
            self.select(page, quiet=True)
            self.scroll[page].top()
            self.draw_header()
            self.status_tick()
            self.draw_gauge(force=True)
            png = out / f"panel_{name}.png"
            def ready(page=page, end=name.endswith("_end")):
                self.status_tick()
                self.draw_gauge(force=True)
                if end:
                    self.scroll[page].scroll_to(1e9, animate=False)
                else:
                    self.scroll[page].top()
            pw.capture(self.root, str(png), ready=ready)
            made.append(png)
        return made
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Suit Control: Fly Like Iron Man's settings and control window")
    ap.add_argument("--warm", action="store_true", help="start hidden (F7 in the game shows it)")
    ap.add_argument("--demo", action="store_true", help="a made-up suit; never touches the real one")
    ap.add_argument("--scenario", default=None, choices=DemoWorld.SCENARIOS, help="--demo: which state")
    ap.add_argument("--preview", default=None, metavar="PAGE", help="--demo: render PAGE (or all) to PNGs, exit")
    ap.add_argument("--out", default=None, help="--preview: the folder for the PNGs")
    ap.add_argument("--scale", type=float, default=None, help="UI scale (1.0 = 1440p)")
    return ap.parse_args(argv)
def pick_scale(args, state):
    if args.scale:
        return float(args.scale)
    if args.preview:
        return 1.0
    mons = monitors()
    name = state.get("monitor")
    mon = next((m for m in mons if m["name"] == name), None) or monitor_of(panel_proc.nms_window()) or next(
        (m for m in mons if m["primary"]), None)
    if not mon:
        return pw.scale_for(pw.monitor_height())
    return pw.scale_for(mon["rect"][3] - mon["rect"][1])
def activation_lock():
    for mod in (pw, panel_pages):
        fn = getattr(mod, "tk_activation_lock", None) if mod is not None else None
        if fn is not None:
            try:
                return bool(fn())
            except Exception:
                log("tk_activation_lock: " + traceback.format_exc(limit=2))
    return False
def main(argv=None):
    args = parse_args(argv)
    if args.preview:
        args.demo = True
    sys.excepthook = _excepthook
    threading.excepthook = lambda a: log("".join(traceback.format_exception(a.exc_type, a.exc_value,
                                                                            a.exc_traceback)))
    lock = None
    if not args.demo:
        lock = panel_proc.PanelLock()
        if lock.taken:
            if not args.warm:
                try:
                    panel_proc.handoff_to_resident(control.Client())
                except Exception:
                    log("hand-over: " + traceback.format_exc(limit=2))
            return 0
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DooDooDevan.FlyLikeIronMan.SuitControl")
    except Exception:
        pass
    pw.dpi_aware()
    guard = pw.no_activate_guard(True)
    if not activation_lock() and (args.warm or args.preview):
        log("no Tk activation lock (panel_pages / panel_widgets didn't load): a hidden start could take the "
            "game's focus, so this one doesn't start")
        if lock:
            lock.close()
        guard.remove()
        return 0
    root = tk.Tk()
    root.withdraw()
    state = PanelState(settings.INI.with_name("panel.json"), enabled=not args.demo)
    pw.init(root, scale=pick_scale(args, state))
    if hud is not None:
        try:
            root._icon = ImageTk.PhotoImage(logo_image(64))
            root.iconphoto(True, root._icon)
        except Exception:
            pass
    app = None
    try:
        app = App(root, guard, args, lock)
        if args.preview:
            out = args.out or str(APP / "shots" / "panel")
            made = app.run_previews(args.preview, out)
            print("\n".join(str(p) for p in made))
            return 0
        log(f"Suit Control started ({'warm' if args.warm else 'demo' if args.demo else 'launch'}), "
            f"scale {pw.SCALE:.2f}")
        app.start()
        root.mainloop()
        return 0
    finally:
        if app is not None:
            app.close()
        try:
            root.destroy()
        except tk.TclError:
            pass
        guard.remove()
if __name__ == "__main__":
    sys.exit(main())
