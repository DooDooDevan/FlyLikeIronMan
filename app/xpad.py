import ctypes
import math
import time
BUTTONS = dict(UP=0x0001, DOWN=0x0002, LEFT=0x0004, RIGHT=0x0008, START=0x0010, BACK=0x0020,
               LS=0x0040, RS=0x0080, LB=0x0100, RB=0x0200, A=0x1000, B=0x2000, X=0x4000, Y=0x8000)
STICK_DEAD_L = 0.24
STICK_DEAD_R = 0.27
TRIGGER_DEAD = 0.12
RESCAN = 1.0
class _GP(ctypes.Structure):
    _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]
class _State(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint), ("gp", _GP)]
class _Vib(ctypes.Structure):
    _fields_ = [("left", ctypes.c_ushort), ("right", ctypes.c_ushort)]
_xi = None
for _name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _xi = getattr(ctypes.windll, _name)
        break
    except OSError:
        continue
if _xi is not None:
    _xi.XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(_State)]
    _xi.XInputGetState.restype = ctypes.c_uint
    _xi.XInputSetState.argtypes = [ctypes.c_uint, ctypes.POINTER(_Vib)]
    _xi.XInputSetState.restype = ctypes.c_uint
class _Keystroke(ctypes.Structure):
    _fields_ = [("vk", ctypes.c_ushort), ("unicode", ctypes.c_wchar), ("flags", ctypes.c_ushort),
                ("user", ctypes.c_ubyte), ("hid", ctypes.c_ubyte)]
_get_keystroke = getattr(_xi, "XInputGetKeystroke", None) if _xi is not None else None
if _get_keystroke is not None:
    _get_keystroke.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(_Keystroke)]
    _get_keystroke.restype = ctypes.c_uint
_PAD_VK = {0x5800: "A", 0x5801: "B", 0x5802: "X", 0x5803: "Y", 0x5804: "RB", 0x5805: "LB",
           0x5810: "UP", 0x5811: "DOWN", 0x5812: "LEFT", 0x5813: "RIGHT", 0x5814: "START", 0x5815: "BACK",
           0x5816: "LS", 0x5817: "RS"}
def _stick(x, y, dead):
    x, y = x / 32767.0, y / 32767.0
    m = math.hypot(x, y)
    if m <= dead:
        return 0.0, 0.0
    k = min(1.0, (m - dead) / (1.0 - dead)) / m
    return max(-1.0, min(1.0, x * k)), max(-1.0, min(1.0, y * k))
def _trig(v):
    v = v / 255.0
    return 0.0 if v <= TRIGGER_DEAD else min(1.0, (v - TRIGGER_DEAD) / (1.0 - TRIGGER_DEAD))
def read_slot(i):
    if _xi is None:
        return None
    s = _State()
    return s if _xi.XInputGetState(i, ctypes.byref(s)) == 0 else None
def slots():
    out = {}
    for i in range(4):
        s = read_slot(i)
        if s is not None:
            g = s.gp
            out[i] = (g.buttons, g.lt, g.rt, g.lx, g.ly, g.rx, g.ry)
    return out
class Pad:
    def __init__(self):
        self.connected = {}
        self.next_scan = 0.0
        self.mask = self.prev = 0
        self.lx = self.ly = self.rx = self.ry = self.lt = self.rt = 0.0
        self.rumble_until = 0.0
        self.mock = None
        self.mock_events = None
        self.npress, self.nrel = {}, {}
        self._ev, self.credit = ({}, {}), ({}, {})
        self.changes = []
    @property
    def any(self):
        return bool(self.connected) or self.mock is not None
    def poll(self, now=None):
        now = time.perf_counter() if now is None else now
        self.prev = self.mask
        mask, best_l, best_r, lt, rt = 0, (0.0, 0.0), (0.0, 0.0), 0.0, 0.0
        npress, nrel = {}, {}
        events = []
        if _get_keystroke is not None:
            ks = _Keystroke()
            for _ in range(64):
                if _get_keystroke(0xFF, 0, ctypes.byref(ks)) != 0:
                    break
                name = _PAD_VK.get(ks.vk)
                if name and not ks.flags & 4:
                    events.append((name, bool(ks.flags & 1)))
        if self.mock_events is not None:
            events += self.mock_events() or []
        for name, is_down in events:
            d = npress if is_down else nrel
            d[name] = d.get(name, 0) + 1
        self._ev = (npress, nrel)
        scan = now >= self.next_scan
        if scan:
            self.next_scan = now + RESCAN
        for i in range(4):
            if not scan and i not in self.connected:
                continue
            s = read_slot(i)
            if s is None:
                if self.connected.pop(i, None):
                    self.changes.append((now, "disconnected", i))
                continue
            if i not in self.connected:
                self.connected[i] = True
                self.changes.append((now, "connected", i))
            g = s.gp
            mask |= g.buttons
            l, r = _stick(g.lx, g.ly, STICK_DEAD_L), _stick(g.rx, g.ry, STICK_DEAD_R)
            if math.hypot(*l) > math.hypot(*best_l):
                best_l = l
            if math.hypot(*r) > math.hypot(*best_r):
                best_r = r
            lt, rt = max(lt, _trig(g.lt)), max(rt, _trig(g.rt))
        if self.mock is not None:
            m = self.mock()
            if m is not None:
                mm, mlx, mly, mrx, mry, mlt, mrt = m
                mask |= mm
                if math.hypot(mlx, mly) > math.hypot(*best_l):
                    best_l = (mlx, mly)
                if math.hypot(mrx, mry) > math.hypot(*best_r):
                    best_r = (mrx, mry)
                lt, rt = max(lt, mlt), max(rt, mrt)
        self.mask = mask
        (self.lx, self.ly), (self.rx, self.ry), self.lt, self.rt = best_l, best_r, lt, rt
        cnt = ({}, {})
        for k, evs in enumerate(self._ev):
            for name, b in BUTTONS.items():
                edge = bool(mask & b and not self.prev & b) if k == 0 else bool(self.prev & b and not mask & b)
                ev = evs.get(name, 0)
                cr = self.credit[k].get(name)
                if ev and cr is not None and now - cr < 0.5:
                    ev -= 1
                    del self.credit[k][name]
                if edge and not ev and not evs.get(name, 0):
                    ev = 1
                    self.credit[k][name] = now
                if ev:
                    cnt[k][name] = ev
        self.npress, self.nrel = cnt
        if self.rumble_until and now >= self.rumble_until:
            self.rumble_until = 0.0
            self._vib(0, 0)
        return self
    def down(self, name):
        return bool(self.mask & BUTTONS[name])
    def pressed(self, name):
        return self.npress.get(name, 0) > 0
    def released(self, name):
        return self.nrel.get(name, 0) > 0
    def presses(self, name):
        return self.npress.get(name, 0)
    def _vib(self, lo, hi):
        if _xi is None:
            return
        v = _Vib(int(max(0.0, min(1.0, lo)) * 65535), int(max(0.0, min(1.0, hi)) * 65535))
        for i in list(self.connected):
            _xi.XInputSetState(i, ctypes.byref(v))
    def rumble(self, lo, hi, secs):
        self._vib(lo, hi)
        self.rumble_until = time.perf_counter() + secs
    def stop(self):
        self.rumble_until = 0.0
        self._vib(0, 0)
PAD_NAMES = set(BUTTONS) | {"LT", "RT"}
PAD_DEFAULTS = dict(
    enabled="yes",
    fly_toggle="A",
    climb="B",
    descend="X",
    roll_left="LB",
    roll_right="RB",
    afterburner="none",
    faster="RIGHT",
    slower="LEFT",
    sonic_boom="RS",
    hard_brake="none",
    quit="LS+RS",
    stick_deadzone=str(STICK_DEAD_L),
    trigger_deadzone=str(TRIGGER_DEAD),
    move_threshold="0.5",
    stick_curve="1.0",
    double_tap_window="0.35",
    quit_hold="0.5",
    rumble="yes",
    rumble_strength="0.6",
)
PULSE = 0.06
FLIGHT_ONLY = ("climb", "descend", "roll_left", "roll_right", "afterburner", "faster", "slower",
               "sonic_boom", "hard_brake", "quit")
RETIRED_PAD = ("shoulder_swap", "barrel_left", "barrel_right")
FLICK_WINDOW = 0.4
TRIGGER_BITS = dict(LT=0x10000, RT=0x20000)
STALL_GAP = 0.1
def _parse_combo(text):
    t = (text or "").strip().upper()
    if t in ("", "NONE", "OFF"):
        return ()
    parts = tuple(p.strip() for p in t.split("+") if p.strip())
    return parts if all(p in PAD_NAMES for p in parts) else None
def load_pad_settings(path=None, log=print):
    import configparser
    import os
    cfg = dict(PAD_DEFAULTS)
    if path is None:
        try:
            from settings import INI as path
        except Exception:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini")
    try:
        cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        cp.read(path, encoding="utf-8")
        if cp.has_section("pad"):
            for k, v in cp.items("pad"):
                if k not in PAD_DEFAULTS:
                    if k not in RETIRED_PAD:
                        log(f"settings.ini [pad]: '{k}' isn't a setting I know, ignoring it")
                    continue
                cfg[k] = v.strip()
    except Exception as e:
        log(f"settings.ini [pad]: couldn't read it ({e}), using the defaults")
    out = {}
    for k, d in PAD_DEFAULTS.items():
        v = cfg[k]
        if k in ("enabled", "rumble"):
            b = v.lower() in ("yes", "true", "on", "1")
            if v.lower() not in ("yes", "true", "on", "1", "no", "false", "off", "0"):
                log(f"settings.ini [pad]: '{k} = {v}' should be yes or no, using {d}")
                b = d == "yes"
            out[k] = b
        elif k in ("stick_deadzone", "trigger_deadzone", "move_threshold", "stick_curve", "double_tap_window",
                   "quit_hold", "rumble_strength"):
            lim = {"stick_curve": (0.5, 4.0), "double_tap_window": (0.15, 1.0), "quit_hold": (0.0, 5.0)}.get(k, (0.0, 0.95))
            try:
                f = float(v)
                if not lim[0] <= f <= lim[1]:
                    raise ValueError
            except ValueError:
                log(f"settings.ini [pad]: '{k} = {v}' isn't a number between {lim[0]} and {lim[1]}, using {d}")
                f = float(d)
            out[k] = f
        else:
            c = _parse_combo(v)
            if c is None or (k != "quit" and len(c) > 1):
                log(f"settings.ini [pad]: '{k} = {v}' isn't a pad button I know "
                    f"(A B X Y LB RB LT RT LS RS BACK START UP DOWN LEFT RIGHT, or none), using {d}")
                c = _parse_combo(d)
            out[k] = c
    return out
class FlightPad:
    def __init__(self, settings=None, log=print):
        global STICK_DEAD_L, TRIGGER_DEAD
        self.cfg = settings if settings is not None else load_pad_settings(log=log)
        STICK_DEAD_L = self.cfg["stick_deadzone"]
        TRIGGER_DEAD = self.cfg["trigger_deadzone"]
        self.pad = Pad()
        self.keys = set()
        self.active = True
        self.climb_held = self.descend_held = False
        self.move = {"forward": False, "back": False, "left": False, "right": False}
        self.pulses = {}
        self.tap_last, self.tap_rel, self.tap_ev = -9.0, -9.0, None
        self.quit_since, self.combo_used = None, set()
        self.last_use = -1e9
        self.flying = True
        self.forward = False
        self.left_held = self.right_held = False
        self._fwd_prev, self._flick_t, self._ab_flick = False, -9.0, False
        self.inert = set()
        self.log = log
    @property
    def enabled(self):
        return self.cfg["enabled"]
    def _val(self, combo):
        if not combo:
            return 0.0
        v = 1.0
        for b in combo:
            v = min(v, self.pad.lt if b == "LT" else self.pad.rt if b == "RT" else float(self.pad.down(b)))
        return v
    def _edge(self, b, rising=True):
        if b in ("LT", "RT"):
            cur = (self.pad.lt if b == "LT" else self.pad.rt) > 0.5
            prev = getattr(self, "_trig_prev_" + b, False)
            setattr(self, "_trig_prev_" + b, cur)
            return cur and not prev if rising else prev and not cur
        return self.pad.pressed(b) if rising else self.pad.released(b)
    def update(self, now, keymap, active=True, flying=True):
        c = self.cfg
        self.active = active
        self.flying = flying
        prev_t, self.poll_t = getattr(self, "poll_t", now), now
        if not c["enabled"] or not active:
            if c["enabled"]:
                self.pad.poll(now)
                for t, what, slot in self.pad.changes:
                    self.log(f"controller {slot + 1} {what}")
                self.pad.changes.clear()
                self._edge("LT"), self._edge("RT")
                self.tap_ev, self.tap_last, self.quit_since = None, -9.0, None
                self.pulses.clear()
            self.keys = set()
            self.climb_held = self.descend_held = self.left_held = self.right_held = False
            self._ab_flick = self._fwd_prev = False
            for k in self.move:
                self.move[k] = False
            return self
        p = self.pad.poll(now)
        for t, what, slot in p.changes:
            self.log(f"controller {slot + 1} {what}")
        p.changes.clear()
        if p.mask or p.lx or p.ly or p.rx or p.ry or p.lt or p.rt:
            self.last_use = now
        th = c["move_threshold"]
        for name, v in (("right", p.lx), ("left", -p.lx)):
            self.move[name] = not (flying and self.forward) and v > (th * 0.7 if self.move[name] else th)
        side = self.move["right"] or self.move["left"]
        thf = th if side else th * 0.6
        for name, v in (("forward", p.ly), ("back", -p.ly)):
            self.move[name] = v > (thf * 0.7 if self.move[name] else thf)
        q = c["quit"]
        if flying and q and all(self._val((b,)) > 0.5 for b in q):
            self.quit_since = self.quit_since or now
            self.combo_used |= set(q)
        else:
            self.quit_since = None
        quitting = self.quit_since is not None and now - self.quit_since >= c["quit_hold"]
        qset = set(q)
        for action in ("afterburner", "faster", "slower", "hard_brake"):
            combo = c[action]
            if len(combo) != 1:
                continue
            b = combo[0]
            if b in qset:
                hit = self._edge(b, rising=False) and b not in self.combo_used
            else:
                hit = self._edge(b)
            if hit and flying and action not in self.inert:
                self.pulses[action] = now + PULSE
        for b in list(self.combo_used):
            if not self._val((b,)) > 0.5 and not any(self._val((x,)) > 0.5 for x in qset):
                self.combo_used.discard(b)
        ft = c["fly_toggle"]
        if len(ft) == 1:
            b = ft[0]
            n = self.pad.presses(b) if b in BUTTONS else int(self._edge(b))
            stall = now - prev_t > STALL_GAP
            for i in range(n):
                t_ = prev_t if stall and i == 0 else now
                if t_ - self.tap_last < c["double_tap_window"]:
                    self.tap_ev = (self.tap_rel, now)
                    self.tap_last = -9.0
                else:
                    self.tap_last = now
            if b in BUTTONS and self.pad.released(b):
                self.tap_rel = now
        up_ = self.move["forward"]
        if up_ and not self._fwd_prev:
            if now - self._flick_t < max(FLICK_WINDOW, c["double_tap_window"]):
                self._ab_flick, self._flick_t = True, -9.0
            else:
                self._flick_t = now
        if not up_:
            self._ab_flick = False
        self._fwd_prev = up_
        rl_, rr_ = flying and self._val(c["roll_left"]) > 0.5, flying and self._val(c["roll_right"]) > 0.5
        self.left_held, self.right_held = self.move["left"] or rl_, self.move["right"] or rr_
        keys = set()
        for name, held in dict(self.move, left=self.left_held, right=self.right_held).items():
            if held and keymap.get(name):
                keys.add(keymap[name])
        if flying and self._ab_flick and keymap.get("afterburner"):
            keys.add(keymap["afterburner"])
        self.climb_held = flying and self._val(c["climb"]) > 0.5
        self.descend_held = flying and self._val(c["descend"]) > 0.5
        sb_ = c["sonic_boom"]
        sonic_held = flying and self._val(sb_) > 0.5 and not (set(sb_) & qset and set(sb_) & self.combo_used)
        for action, held in (("climb", self.climb_held), ("descend", self.descend_held), ("sonic_boom", sonic_held)):
            if held and keymap.get(action):
                keys.add(keymap[action])
        for action, until in list(self.pulses.items()):
            if now < until:
                if keymap.get(action):
                    keys.add(keymap[action])
            else:
                del self.pulses[action]
        if quitting and keymap.get("quit"):
            keys.add(keymap["quit"])
        self.keys = keys
        return self
    def _curve(self, v):
        return math.copysign(abs(v) ** self.cfg["stick_curve"], v)
    def axes(self, fw, st, cl, kb_fw=None, kb_st=None, kb_cl=None):
        if not self.cfg["enabled"] or not self.active:
            return fw, st, cl
        p = self.pad
        if kb_fw is not None:
            fw = kb_fw
        elif p.ly:
            fw = self._curve(p.ly)
        rb_ = (self._val(self.cfg["roll_right"]) - self._val(self.cfg["roll_left"])) if self.flying else 0.0
        if kb_st is not None:
            st = kb_st
        elif rb_:
            st = rb_
        elif p.lx and not (self.flying and self.forward):
            st = self._curve(p.lx)
        if kb_cl is not None:
            cl = kb_cl
        else:
            up, dn = self._val(self.cfg["climb"]), self._val(self.cfg["descend"])
            if up or dn:
                cl = up - dn
        return fw, st, cl
    def card(self):
        c = self.cfg
        n = lambda k: "+".join(c[k]) or "-"
        state = "found" if slots() else "none plugged in yet (picked up when you plug one in)"
        brake = f"{n('hard_brake')} or double-flick the stick back" if c["hard_brake"] else "double-flick the stick back"
        ab_ = (f"{n('afterburner')} or double-flick the stick up" if c["afterburner"]
               else "double-flick the stick up")
        return (f"controller {state}: double-tap {n('fly_toggle')} fly, left stick move, right stick camera; "
                f"flying: {n('climb')}/{n('descend')} up/down, {n('roll_left')}/{n('roll_right')} roll "
                f"(a sidestep at a hover), {ab_} afterburner, {n('sonic_boom')} sonic boom / interplanetary, "
                f"{brake} hard brake, "
                + ("" if {"faster", "slower"} <= self.inert else f"{n('faster')}/{n('slower')} speed, ")
                + f"hold {n('quit')} quit (the game ignores those buttons while you fly; on foot they're the game's)")
    def used_mask(self):
        if not self.cfg["enabled"]:
            return 0
        m = 0
        for action in FLIGHT_ONLY:
            if action in self.inert:
                continue
            for b in self.cfg.get(action) or ():
                m |= BUTTONS.get(b, 0) | TRIGGER_BITS.get(b, 0)
        return m
    def take_tap(self):
        ev, self.tap_ev = self.tap_ev, None
        return ev
    def buzz(self, lo, hi, secs, now=None):
        now = time.perf_counter() if now is None else now
        if self.cfg["enabled"] and self.cfg["rumble"] and now - self.last_use < 60.0:
            k = self.cfg["rumble_strength"]
            self.pad.rumble(lo * k, hi * k, secs)
    def stop(self):
        try:
            self.pad.stop()
        except Exception:
            pass
PAD_SHM_NAME, PAD_SHM_SIZE, PAD_SHM_FMT = "IronManFlightPad", 64, "<dIIiffffIII"
PAD_ACT = dict(jump=1, reload=2, swap_weapon=4)
PAD_VKS = (0x57, 0x41, 0x53, 0x44, 0x52, 0x46, 0x10, 0x11, 0x20)
class PadShare:
    def __init__(self):
        import mmap
        self.shm = mmap.mmap(-1, PAD_SHM_SIZE, tagname=PAD_SHM_NAME)
        self.roll_seq, self.roll_dir = 0, 0
    def write(self, fp=None, roll=0, force=0, suppress=0, act=0):
        import struct
        if roll:
            self.roll_seq, self.roll_dir = (self.roll_seq + 1) & 0xFFFFFFFF, roll
        bits = force
        if fp is not None and fp.enabled and fp.active:
            held = dict(fp.move, left=fp.left_held, right=fp.right_held, climb=fp.climb_held, descend=fp.descend_held)
            for i, action in enumerate(("forward", "left", "back", "right", "climb", "descend")):
                if held.get(action):
                    bits |= 1 << i
        p = fp.pad if fp is not None and fp.enabled else None
        try:
            used = fp.used_mask() if fp is not None else 0
        except Exception:
            used = 0
        try:
            self.shm[:struct.calcsize(PAD_SHM_FMT)] = struct.pack(
                PAD_SHM_FMT, time.perf_counter(), bits, self.roll_seq, self.roll_dir,
                p.lx if p else 0.0, p.ly if p else 0.0, p.lt if p else 0.0, p.rt if p else 0.0, suppress, used,
                act)
        except Exception:
            pass
if __name__ == "__main__":
    p = Pad()
    print("pads:", slots())
    t_end = time.perf_counter() + float(__import__("sys").argv[1] if len(__import__("sys").argv) > 1 else 5)
    while time.perf_counter() < t_end:
        p.poll()
        for c in p.changes:
            print(c)
        p.changes.clear()
        names = [n for n in BUTTONS if p.down(n)]
        print(f"\rL {p.lx:+.2f} {p.ly:+.2f}  R {p.rx:+.2f} {p.ry:+.2f}  LT {p.lt:.2f} RT {p.rt:.2f}  {names}     ",
              end="", flush=True)
        time.sleep(0.05)
    print()
