import ctypes
import json
import math
import os
import sys
import time
from pathlib import Path
import numpy as np
import pymem
import fastwrite
import keys
import animswap
import arsenal
import lookupcam as lookcam
import speedfx
import audio
import settings as _settings
HERE = Path(__file__).parent
SET = _settings.load()
import control as _control
try:
    VERSION = (HERE / "VERSION.txt").read_text().strip()
except OSError:
    VERSION = "dev"
_SCRIPT_MUTEX = _control.Mutex("Local\\IronManFlightScript")
if _SCRIPT_MUTEX.taken:
    print("the flight script is already running (one at a time): this copy stops", flush=True)
    sys.exit(3)
class _NullServer:
    def __getattr__(self, name):
        return lambda *a, **k: ([] if name == "poll" else False if name == "panel" else None)
try:
    CTRL = _control.Server(version=VERSION)
except Exception as _e:
    print(f"Suit Control channel unavailable ({_e!r}): flying without it", flush=True)
    CTRL = getattr(_control, "NullServer", _NullServer)()
try:
    sys.stdout = _control.Tee(sys.stdout, CTRL)
except Exception:
    pass
CONFIG, LOG = HERE / "config.json", HERE / "flight_log.csv"
sys.setswitchinterval(0.0005)
cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
JETPACK_POSE = "--pose" in sys.argv
if JETPACK_POSE:
    sys.argv.remove("--pose")
CLASSIC = "--classic" in sys.argv
if CLASSIC:
    sys.argv.remove("--classic")
THRUST_FWD = 10.0
THRUST_UP = 19.5
DRAG_THRUST = 0.20
DRAG_THRUST_UP = 0.37
DRAG_COAST = 1.00
SPACE_BOOST = 1.0
VEL = int(sys.argv[1] if len(sys.argv) > 1 else cfg.get("vel", "2697E720090"), 16)
CAM = int(sys.argv[2] if len(sys.argv) > 2 else cfg.get("cam", "26D0D200170"), 16)
BODY = int(cfg["body"], 16) if "body" in cfg else None
CAM_SIGN = cfg.get("cam_sign", 1)
SAVED_UP = np.array(cfg["up"]) if "up" in cfg else None
MIN_SPEED, MAX_SPEED, START_SPEED = SET.flight["min_speed"], SET.flight["max_speed"], SET.flight["start_speed"]
SPEED = START_SPEED
if SET.flight["remember_speed"]:
    try:
        SPEED = min(max(float(cfg.get("speed", START_SPEED)), MIN_SPEED), MAX_SPEED)
    except (TypeError, ValueError):
        pass
SPEED = float(sys.argv[3]) if len(sys.argv) > 3 else SPEED
THROTTLE_MODE = True
THROTTLE_UP = 2.5
THROTTLE_DOWN = 1.5
THROTTLE_CURVE = 1.6
THROTTLE_DETENT = 0.5
THROTTLE_REVERSE_SPEED = 20.0
KICK_SPEED = START_SPEED if THROTTLE_MODE else None
HOVER_MOVE_SPEED = 10.0
HOVER_STRAFE_SPEED = 30.0
HOVER_STRAFE_MAX = 25.0
BOOST = 2.0
ACCEL_TIME = 0.45
BRAKE_TIME = 0.30
CAM_SMOOTH = 0.04
CAMERA_PITCH_STEERS = True
TURN_GRIP = 4.0
LEVEL_DEADZONE = math.radians(12)
LOOK_PITCH_FULL = math.radians(28)
YAW_RATE_MAX = math.radians(720)
PITCH_RATE_MAX = math.radians(270)
PITCH_LIMIT = math.radians(85)
CARVE_RATE_MAX = math.radians(240)
HEAD_HOLD = math.sin(math.radians(3))
SNAP_ANGLE = math.radians(60)
SNAP_CONFIRM = 0.05
FLIP_STRAFE = SET.flight["flip_strafe"]
AFTERBURNER = 2.4
DIVE_ENTER = math.radians(-58)
DIVE_EXIT = math.radians(-48)
DIVE_SPEED = 1.15
AB_FUEL_TIME = 10.0
AB_RECHARGE_TIME = 15.0
AB_RECHARGE_DELAY = 1.0
SONIC_KEY = "CAPS"
SONIC_KICK = 60.0
SONIC_KICK_CURVE = 0.6
SONIC_BOOST = 6.0
SONIC_HOLD = 2.5
SONIC_FADE = 2.5
SONIC_DRAG = 0.4
SONIC_CHARGE_TIME = 1.2
SONIC_SECTIONS = 3
SONIC_BLAST_KICK = (30.0, 50.0, 80.0)
SONIC_BLAST_K = (0.55, 0.8, 1.0)
SONIC_BLAST_SHOCK = (0.85, 1.3, 1.9)
SONIC_BLAST_PUNCH = ((5.0, 0.5, 0.5), (8.0, 0.8, 0.7), (12.0, 1.3, 1.0))
SONIC_BLAST_RUMBLE = ((0.6, 0.4, 0.25), (0.8, 0.6, 0.35), (1.0, 0.9, 0.55))
SONIC_BLAST_SOUNDS = (("sonic_blast_1", "sonic_boom_mid"), ("sonic_blast_2", "sonic_boom"),
                      ("sonic_blast_3", "sonic_boom"))
SONIC_REARM = 0.25
SONIC_REARM_HOOK = 0.04
SONIC_GATE = 0.25
SONIC_REFUSED_SHOW = 0.5
SONIC_REFILL_TIME = 16.0
SONIC_REFILL_DELAY = 0.8
SONIC_RELEASE = 0.05
SONIC_TAP = 1.0 / SONIC_SECTIONS
SONIC_BIG = 0.7
SONIC_MID = 0.3
SONIC_COOLDOWN = SONIC_REFILL_TIME
FIRST_Q = 0.25
PILOT_FLAME = 0.2
CRUISE_MAX = 200000.0
CRUISE_START = 2000.0
CRUISE_RAMP = 0.5
CRUISE_ACC = 1600.0
CRUISE_K = 1.0
CRUISE_MIN = 300.0
CRUISE_DOWN = 0.12
CRUISE_AHEAD = 0.05
CRUISE_MARGIN = (0.35, 20000.0)
CRUISE_FAR = (450000.0, 5.5)
CRUISE_FLOOR = 1500.0
CRUISE_TURN = 0.35
CRUISE_OUT = 1.0
CRUISE_OUT_SPEED = 300.0
CRUISE_OUT_ATMO = 0.3
CRUISE_COOLDOWN = 3.0
CRUISE_FILL = 3.0
CRUISE_SEG_FILL = (2.5, 2.0, 2.0)
IP_CHARGE_TIME = 2.5
IP_HUM_VOLUME = 0.55
IP_HUM_FADE_IN, IP_HUM_FADE_OUT = 2.5, 1.5
IP_CHARGE_CUT = 0.25
IP_CAPS_GRACE = 0.2
IP_AUDIO_LATENCY = 0.04
IP_BOOM_SHOCK = (1.0, 1.7, 2.6)
IP_BOOM_PUNCH = ((6.0, 0.6, 0.7), (10.0, 1.1, 0.9), (16.0, 1.8, 1.3))
IP_BOOM_RUMBLE = ((0.6, 0.4, 0.35), (0.85, 0.7, 0.5), (1.0, 1.0, 0.8))
IP_BOOM_SOUNDS = ((), ("ip_boom2", "sonic_boom"), ("ip_boom3", "sonic_boom"))
IP_HUM_PITCH = (1.0, 1.5, 2.52)
IP_HUM_LOUD_K = 0.3
IP_GROWL = False
IP_GROWL_VOLUME = 0.5
IP_GROWL_FADE_IN, IP_GROWL_FADE_OUT, IP_HUM_HANDOFF = 1.0, 1.2, 1.0
IP_HUM_DUCK = (0.4, 0.0, 0.5, 1.5)
CRUISE_DRAIN = 2.0
CRUISE_LOW = 1000.0
CRUISE_TIERS = ((1000.0, 6000.0), (15000.0, 50000.0), (100000.0, 200000.0))
CRUISE_DETENT = 0.4
DOCK_ON = False
DOCK_MOUTH = (300.0, 1100.0)
DOCK_RADIUS = 200.0
DOCK_IN_SPEED = 3.0
DOCK_TIMEOUT = 60.0
PULL_ON = True
PULL_MOUTH = (320.0, 1300.0)
PULL_RADIUS = 250.0
PULL_IN_SPEED = 3.0
PULL_MAX = 220.0
PULL_ACC = 140.0
PULL_CENTER = 2.0
PULL_CENTER_MAX = 60.0
PULL_WARP = 320.0
PULL_INSIDE = (0.0, -880.0, 1598.0)
PULL_INSIDE_OFF = (0.0, -1024.0, 0.0)
PULL_PATH = ((0.0, -890.0, 1200.0), (0.0, -900.0, 800.0), (0.0, -906.0, 470.0),
             (0.0, -912.0, 300.0), (0.0, -921.0, 190.0), (0.0, -927.0, 122.0))
PULL_WALL_Z = 390.7
PULL_HOP = 12.0
PULL_STALL = 1.5
PULL_INSIDE_BOX = ((-450.0, 450.0), (-1300.0, -500.0), (-700.0, 2300.0))
PULL_NEAR_TE = 2500.0
ANOMALY_UP = (0.0, 1.0, 0.0)
ST_CATCH = (60.0, 1100.0)
ST_RADIUS = 90.0
ST_TUBE = 40.0
ST_TUBE_FROM = 700.0
ST_HOP = 12.0
ST_OUT_END = 300.0
ST_IN_MAX = 160.0
FR_WALL = 4.2
FR_HOP = 12.0
FR_CATCH = 7.0
FR_DOOR_HALF = (18.0, 16.0)
FR_MIN_SPEED = 1.5
PULL_IN_MAX = 130.0
PULL_IN_SLOW = 0.9
PULL_TIMEOUT = 45.0
PULL_EXIT_ZONE = ((-70.0, 70.0), (-950.0, -840.0), (200.0, 1750.0))
PULL_EXIT_AXIS = ((0.0, -878.0), 1880.0)
PULL_EXIT_WARP = 1820.0
PULL_OUT_AT = 450.0
PULL_OUT_END = 1400.0
PULL_OUT_SPEED = 40.0
BRAKE_TAP = 0.3
BRAKE_TIME = 0.5
BRAKE_RATE = 1.6
BRAKE_COOLDOWN = 0.8
BRAKE_RELIGHT = 0.1
HANDS_IDLE_DELAY = 0.2
QUARTER_HANDS_HOLD = 0.45
BRAKE_DRAG = 1.6
BURNER_IDLE_DELAY = 1.0
BURNER_IDLE_SPEED = 6.0
HARD_LAND_SPEED = 10.0
DIVE_LANDS = SET.flight["dive_lands"]
CAM_CENTER_DELAY = SET.camera["recenter_delay"]
SPACE_DRAG_THRUST = 0.12
SPACE_DRAG_COAST = 0.06
SPACE_BRAKE_RATE = 3.0
ENTRY_PITCH_MAX = 50.0
SPACE_CAM_SETTLE = 4.0
SPACE_CAM_HOLD = 1.5
SET_HANDOFF_IN_SPACE = True
TAKEOFF_CHECK = (0.15, 0.5, 0.5)
WATER_RELIGHT = (0.3, 0.25)
WATER_OUT_HOLD = 2.5
WATER_OUT_HEIGHT = 2.0
WATER_STALE_QUIET = 120.0
WATER_MAX_SPEED = 19.0
SKIM = False
SKIM_DEPTH = 0.3
SKIM_GAIN, SKIM_MAX = 3.0, 6.0
SKIM_BAND = (-1.5, 1.5)
SKIM_LOOK = (-40.0, 25.0)
SKIM_FRESH = 60.0
SKIM_FAR = 60.0
SKIM_EMA = 0.35
SKIM_DIVE = 0.8
LAND_BLOCK_HOLD = 0.6
SPACE_ALIGN = False
SPACE_ALIGN_LOOK = 30.0
SPACE_ALIGN_RATE = math.radians(25)
SPACE_ALIGN_PITCH = 20.0
LEVEL_SLOW = False
LEVEL_RATE = math.radians(90)
FREEZE_KEEP_FACING = False
CROSS_HOLD_PLANET_ONLY = True
CROSS_PLANET_LIM = 70.0
CROSS_FREEZE = 2.0
ENTRY_CAM_HOLD = False
CROSS_ROWS_HOLD = True
CROSS_IN_GAME = True
CROSS_ROWS_MAX = 3.0
CROSS_UP_KEEP = 1.5
CROSS_PITCH_EASE = 60.0
CROSS_LEVEL_DONE = 1.0
CROSS_MIN_HOLD = 0.6
CROSS_LEAD = 0.025
SPACE_CAM_CENTER = 0x5042040 + 0x2CE0 + 0x3C
SPACE_CAM_CENTER_SHIPPED = 2.2
CAM_PLANET_LIMIT = 59.0
PLANET_HOLD = 0.5
ENTRY_PITCH = 45.0
ENTRY_CAM_FIX = False
CAM_ANGLES = (0x21D0, 0x21E0, 0x2A10, 0x2A20)
CAM_YAW_BEHIND = 0.0
HANDOFF_PAIRS = (0x2A10, 0x2A20)
CAM_SAVED = (0x2A20,)
CAM_PITCH_LIMIT = 0x2650
SPACE_ROLL_RATE = math.radians(110)
SPACE_ROLL_ACC = math.radians(450)
PLAYER_SKYDIVE = 0x198
PLAYER_CAM_LOOK = 0x220
PLAYER_ORIENT = 0x1E0
FLY_CENTER_DELAY = 3600.0
VK = dict(F8=0x77, END=0x23, HOME=0x24, W=0x57, A=0x41, S=0x53, D=0x44, SPACE=0x20, CTRL=0x11,
          SHIFT=0x10, PGUP=0x21, PGDN=0x22, R=0x52, F=0x46, CAPS=0x14)
CLIMB, DESCEND =("R", "F") if JETPACK_POSE else ("SPACE", "CTRL")
KEYMAP = {VK[n]: SET.vk(a) for n, a in (("W", "forward"), ("S", "back"), ("A", "left"), ("D", "right"),
                                        ("R", "climb"), ("F", "descend"), ("SHIFT", "afterburner"),
                                        ("F8", "fly_toggle"), ("PGUP", "faster"), ("PGDN", "slower"),
                                        ("END", "quit"))}
KEYMAP = {d: b for d, b in KEYMAP.items() if b != d}
VK["ARM"] = SET.vk("arm_toggle") or 0x07
VK["ARSENAL"] = SET.vk("arsenal_toggle") or 0x07
IRONMAN_NO_WEAPONS = {15: "Animus Beam", 0: "Repulsors", 1: "Twin Repulsors", 2: "Wrist Cannon",
                      16: "Rocket Pods", 4: "Charged Blast", 11: "Terrain Manipulator"}
WEAPON_SEL, WEAPON_WHEEL = 0xF74, 0x51A0
WHEEL_LIST, WHEEL_N, WHEEL_CAP = 0x51B4, 0x5208, 21
WHEEL_RESTORE = [None]
RELOAD_TRIES = 2
PAD_FORWARD_THROTTLE = 0.02
VK["BRAKE"] = 0x07
VK["PANEL"] = SET.vk("panel") or 0x07
_gaks = ctypes.windll.user32.GetAsyncKeyState
_gaks.restype = ctypes.c_short
key = lambda vk: _gaks(KEYMAP.get(vk, vk))
FG = [True]
kbdown = lambda name: FG[0] and bool(key(VK[name]) & 0x8000)
import xpad
PAD = xpad.FlightPad(log=lambda m: print(m, flush=True))
PAD_SHARE = xpad.PadShare()
if THROTTLE_MODE:
    PAD.inert = {"faster", "slower"}
down = lambda name: FG[0] and (bool(key(VK[name]) & 0x8000) or name in PAD.keys)
class PadRoute:
    TAPS = {"R": xpad.PAD_ACT["reload"], "G": xpad.PAD_ACT["swap_weapon"]}
    TAP_SECS = 0.08
    MIN_EDGE = 0.07
    GAP = 0.3
    RETRY = 0.4
    KB_UP = 0.12
    BUTTONS = (0x01, 0x02, 0x04, 0x05, 0x06)
    def __init__(self):
        self.src = "kb"
        self.space = False
        self.kb_space = False
        self.jump, self.jump_t = False, -9.0
        self.pend_down = self.pend_up = False
        self.until = {}
        self.hold_off = 0.0
        self.kbm_t = -1e9
        self.btn_was = False
        self.switches, self.switch_t = 0, -9.0
        self.retry_t, self.retry_n, self.kb_again = 0.0, 3, 0.0
    def route(self, name, up):
        if name == "SPACE":
            if up and self.space:
                self.pend_up = True
            elif not up and not self.space:
                self.pend_down = True
            self.space = not up
            if up:
                if self.kb_space:
                    keys.raw_send("SPACE", True)
                    self.kb_space = False
            elif self.src == "kb" and not self.kb_space and time.perf_counter() >= max(self.hold_off, self.kb_again):
                keys.raw_send("SPACE", False)
                self.kb_space = True
            return True
        b = self.TAPS.get(name)
        if b and self.src == "pad":
            if not up:
                self.until[b] = time.perf_counter() + self.TAP_SECS
            return True
        return False
    def update(self, now, pad_t, key_t):
        btn_ = any(_gaks(b_) & 0x8000 for b_ in self.BUTTONS)
        if btn_ and not self.btn_was:
            self.kbm_t = now
        self.btn_was = btn_
        if key_t > self.kbm_t:
            self.kbm_t = key_t
        want = "pad" if pad_t > self.kbm_t else "kb"
        if want != self.src:
            self.src, self.hold_off, self.switch_t = want, now + self.GAP, now
            self.switches += 1
            self.pend_down = self.pend_up = False
            self.retry_t, self.retry_n = now + self.GAP + self.RETRY, 0
            if self.kb_space:
                keys.raw_send("SPACE", True)
                self.kb_space = False
        if self.retry_n < 3 and now >= self.retry_t and self.space:
            b_ = jet_signals()[0]
            if b_ > 0.0 and now - b_ > 0.3:
                self.retry_n, self.retry_t = self.retry_n + 1, now + self.RETRY
                if self.src == "pad":
                    self.pend_up = self.pend_down = True
                elif self.kb_space:
                    keys.raw_send("SPACE", True)
                    self.kb_space, self.kb_again = False, now + self.KB_UP
            else:
                self.retry_n = 3
        if (self.src == "kb" and self.space and not self.kb_space and now >= self.hold_off
                and now >= self.kb_again):
            keys.raw_send("SPACE", False)
            self.kb_space = True
    def bits(self, now):
        if self.src == "pad" and now >= self.hold_off:
            if now - self.jump_t >= self.MIN_EDGE:
                if self.jump and (self.pend_up or not self.space):
                    self.jump, self.jump_t, self.pend_up = False, now, False
                elif not self.jump and (self.pend_down or self.space):
                    self.jump, self.jump_t, self.pend_down = True, now, False
        elif self.jump:
            self.jump, self.jump_t = False, now
        b = xpad.PAD_ACT["jump"] if self.jump else 0
        for bit, u in list(self.until.items()):
            if now < u:
                b |= bit
            else:
                del self.until[bit]
        return b
ROUTE = PadRoute()
keys.ROUTE[0] = ROUTE.route
def fire_held():
    return bool(_gaks(0x01) & 0x8000) or (PAD.enabled and PAD.active and PAD.pad.rt > 0.5)
pm = pymem.Pymem("NMS.exe")
def rd(addr):
    return np.frombuffer(pm.read_bytes(addr, 12), dtype=np.float32).astype(np.float64)
PHYS_LIMIT = 19968.0
def wr(v):
    sp_ = float(np.linalg.norm(v))
    if sp_ > PHYS_LIMIT:
        v = v * (PHYS_LIMIT / sp_)
    pm.write_bytes(VEL, v.astype(np.float32).tobytes(), 12)
try:
    import viewdir
except ImportError:
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "viewdir", HERE / "exeanalysis" / "camera" / "camfind2" / "viewdir.py")
        viewdir = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(viewdir)
    except Exception:
        viewdir = None
try:
    import pymem.process
    BASE = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
except Exception:
    BASE = None
import watercam
water_cam = watercam.WaterCam(pm, BASE)
import swimswap
swim_anims = swimswap.SwimSwaps()
import waterspeed
water_speed = waterspeed.WaterSpeed()
def cam_axes():
    r = viewdir.cam_axes(pm, BASE) if viewdir is not None and BASE is not None else None
    if r is None:
        return None, None, None
    f, u = clean_unit(np.array(r[2], dtype=np.float64)), clean_unit(np.array(r[1], dtype=np.float64))
    if f is None or u is None:
        return None, None, None
    rt = unit(np.cross(f, u))
    return f, rt, unit(np.cross(rt, f))
def view_dir():
    if viewdir is not None and BASE is not None:
        r = viewdir.view_dir(pm, BASE)
        look = clean_unit(r[0]) if r else None
        if look is not None:
            return look, True
    try:
        return clean_unit(rd(CAM) * CAM_SIGN), False
    except Exception:
        return None, False
def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else v
def ease(dt, secs):
    return 1.0 - math.exp(-dt / secs)
def clean_unit(v, lo=0.5, hi=2.0):
    if v is None:
        return None
    v = np.asarray(v, dtype=np.float64)
    if v.shape != (3,) or not np.isfinite(v).all():
        return None
    n = float(np.linalg.norm(v))
    return v / n if lo < n < hi else None
def flat(v, up):
    h = v - up * float(np.dot(v, up))
    n = float(np.linalg.norm(h))
    return h / n if n > 1e-9 else None
def any_flat(up):
    h = flat(np.array([1.0, 0.0, 0.0]), up)
    return h if h is not None else flat(np.array([0.0, 1.0, 0.0]), up)
def yaw_about(a, b, up):
    return math.atan2(float(np.dot(np.cross(a, b), up)), float(np.dot(a, b)))
def turn_about(a, ang, up):
    return a * math.cos(ang) + np.cross(up, a) * math.sin(ang)
def slerp_toward(a, b, max_ang):
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    ang = math.acos(c)
    if ang <= max_ang:
        return b.copy()
    perp = b - a * c
    n = float(np.linalg.norm(perp))
    if n < 1e-9:
        return a.copy()
    return a * math.cos(max_ang) + (perp / n) * math.sin(max_ang)
def learn_up():
    v0 = rd(VEL)
    if np.linalg.norm(v0) < 1.0:
        return None
    time.sleep(0.25)
    v1 = rd(VEL)
    fall = v1 - v0
    if np.linalg.norm(fall) < 0.5 or np.dot(v1, fall) <= 0 or np.linalg.norm(v1) <= np.linalg.norm(v0):
        return None
    return -unit(fall)
def hop_up():
    keys.hold(0.12, "SPACE")
    time.sleep(0.08)
    v1 = rd(VEL)
    time.sleep(0.15)
    fall = rd(VEL) - v1
    if np.linalg.norm(fall) < 0.5 or np.dot(-fall, v1) <= 0:
        return None
    return -unit(fall)
import mmap
import struct
_SHM = mmap.mmap(-1, 128, tagname="IronManFlightShared")
_SHM_FMT = "<Id3d3d3d3d"
SHM_LEGS = 112
_shm_seq = [0]
def _shm_vec(v, as_unit=False):
    z = (0.0, 0.0, 0.0)
    if v is None:
        return z
    v = clean_unit(v) if as_unit else np.asarray(v, dtype=np.float64)
    if v is None or v.shape != (3,) or not np.isfinite(v).all():
        return z
    return tuple(float(x) for x in v)
def share(flying, fwd=None, push=None, up=None, burner=False, vel=None, dive=False, space=False, cruise=False,
          water=False):
    _shm_seq[0] = (_shm_seq[0] + 1) & 0x01FFFFFF
    try:
        _SHM[:struct.calcsize(_SHM_FMT)] = struct.pack(
            _SHM_FMT, _shm_seq[0] | (0x80000000 if flying else 0) | (0x40000000 if flying and burner else 0)
            | (0x20000000 if vel is not None else 0) | (0x10000000 if flying and dive else 0)
            | (0x08000000 if flying and space else 0) | (0x04000000 if flying and cruise else 0)
            | (0x02000000 if flying and water else 0),
            time.perf_counter(),
            *_shm_vec(fwd, True), *_shm_vec(push), *_shm_vec(up, True), *_shm_vec(vel))
    except Exception:
        pass
_THR = mmap.mmap(-1, 64, tagname="IronManFlightThrottle")
THR_FMT = "<dffffI"
def throttle_share(flying, throttle, speed, flags):
    try:
        _THR[0:struct.calcsize(THR_FMT)] = struct.pack(THR_FMT, time.perf_counter(), float(throttle), float(speed),
                                                        FIRST_Q, PILOT_FLAME, (flags & 0x17F) | (128 if flying else 0))
    except Exception:
        pass
_NAV = mmap.mmap(-1, 128, tagname="IronManFlightNav2")
def nav():
    try:
        t_, h_, cx, cy, cz, r_ = struct.unpack("<6d", _NAV[0:48])
    except Exception:
        return None
    return (t_, h_, np.array([cx, cy, cz]), r_) if r_ > 0 and time.perf_counter() - t_ < 1.5 else None
_WARP = mmap.mmap(-1, 128, tagname="IronManFlightWarp")
_JET = mmap.mmap(-1, 32, tagname="IronManFlightJet")
_PLANETS = mmap.mmap(-1, 512, tagname="IronManFlightPlanets")
_WARPFX = mmap.mmap(-1, 128, tagname="IronManFlightWarpFX")
_PACK = mmap.mmap(-1, 32, tagname="IronManFlightPack")
BOOM_VFOV = 55.0
_warpfx_proc = [None]
def obstacles():
    try:
        t_, n_ = struct.unpack_from("<dI", _PLANETS, 0)
        if not 0 < n_ <= 12 or time.perf_counter() - t_ > 1.5:
            return None
        vals = struct.unpack_from("<" + "4d" * n_, _PLANETS, 16)
    except Exception:
        return None
    return t_, [(np.array(vals[4 * i:4 * i + 3]), vals[4 * i + 3]) for i in range(n_)]
def warpfx_share(strength, speed, vp=(0.5, 0.5), dist=-1.0):
    try:
        _WARPFX[0:48] = struct.pack("<6d", time.perf_counter(), strength, speed, vp[0], vp[1], dist)
        _JET[16:24] = struct.pack("<Q", VEL)
    except Exception:
        pass
def pack_screen(now):
    try:
        t_, x_, y_, z_ = struct.unpack_from("<4d", _PACK, 0)
        if not 0.0 <= time.perf_counter() - t_ < 0.3:
            return
        vd_ = viewdir.view_dir(pm, BASE)
        f_, r_, u_ = cam_axes()
        if vd_ is None or f_ is None:
            return
        d_ = np.array([x_, y_, z_]) - np.array(vd_[1])
        z = float(d_ @ f_)
        if z < 0.3:
            return
        tv_ = math.tan(math.radians(0.5 * (BOOM_VFOV + speedfx.extra_fov())))
        asp_ = 16.0 / 9.0
        sx_ = 0.5 + 0.5 * float(d_ @ r_) / z / (tv_ * asp_)
        sy_ = 0.5 - 0.5 * float(d_ @ u_) / z / tv_
        if 0.0 < sx_ < 1.0 and 0.0 < sy_ < 1.0:
            _WARPFX[64:88] = struct.pack("<3d", time.perf_counter(), sx_, sy_)
            _WARPFX[96:104] = struct.pack("<d", 1.0 / (z * tv_))
    except Exception:
        pass
def warpfx_blast(i):
    try:
        _WARPFX[104:120] = struct.pack("<dd", time.perf_counter(), float(i))
    except Exception:
        pass
def warpfx_boom(size):
    try:
        _WARPFX[48:64] = struct.pack("<dd", time.perf_counter(), float(size))
    except Exception:
        pass
def warpfx_start():
    _warpfx_proc[0] = None
    try:
        if not SET.effects.get("warp_effects", True):
            return
        import subprocess
        _warpfx_proc[0] = subprocess.Popen([sys.executable, "-u", str(HERE / "warpfx.py"), str(os.getpid())],
                                           cwd=HERE, creationflags=0x08000000)
        keys._OURS.add(_warpfx_proc[0].pid)
    except Exception as e:
        print(f"warp effects unavailable ({e})", flush=True)
UNIBEAM_TOOL = 5
UNIBEAM_SOUNDS = ("unibeam_start", "unibeam_hum", "unibeam_down")
UNIBEAM_VOLUME = 0.6
UNIBEAM_CUT = 0.08
_unibeam = dict(firing=False, t0=0.0, hum=False)
def unibeam_sound(now, live):
    u_ = _unibeam
    firing = False
    if live and arsenal.state.weapon:
        try:
            firing = (struct.unpack("<i", pm.read_bytes(arsenal.state.weapon + WEAPON_SEL, 4))[0] == UNIBEAM_TOOL
                      and fire_held())
        except Exception:
            firing = False
    if firing and not u_["firing"]:
        audio.track_stop("unibeam_down")
        audio.track_play("unibeam_start", 0.0, volume=UNIBEAM_VOLUME)
        audio.track_play("unibeam_hum", 0.0, loop=True, volume=UNIBEAM_VOLUME)
        u_.update(firing=True, t0=now, hum=True)
    elif not firing and u_["firing"]:
        audio.track_stop("unibeam_start", UNIBEAM_CUT)
        audio.track_stop("unibeam_hum", UNIBEAM_CUT)
        audio.track_play("unibeam_down", 0.0, volume=1.0)
        u_.update(firing=False, hum=False)
WRIST_TOOL = 3
WRIST_SOUNDS = ("wristlaser_charge", "wristlaser_hold", "wristlaser_shot", "wristlaser_extra",
                "wristlaser_wub")
WRIST_WUB_VOLUME = 0.85
WRIST_CHARGE_LEN = 3.50
WRIST_HOLD_IN = 0.02
WRIST_CUT = 0.05
_wrist = dict(held=False, t0=0.0, hold=False)
def wrist_sound(now, live):
    w_ = _wrist
    held = tool = False
    if live and arsenal.state.weapon:
        try:
            tool = struct.unpack("<i", pm.read_bytes(arsenal.state.weapon + WEAPON_SEL, 4))[0] == WRIST_TOOL
            held = tool and fire_held()
        except Exception:
            held = tool = False
    if held and not w_["held"]:
        audio.track_stop("wristlaser_hold")
        audio.track_play("wristlaser_charge", 0.0, volume=1.0)
        w_.update(held=True, t0=now, hold=False)
    elif held and not w_["hold"] and now - w_["t0"] >= WRIST_CHARGE_LEN - WRIST_HOLD_IN:
        audio.track_play("wristlaser_hold", 0.0, loop=True, volume=1.0, fade=WRIST_HOLD_IN)
        w_["hold"] = True
    elif not held and w_["held"]:
        audio.track_stop("wristlaser_charge", WRIST_CUT)
        audio.track_stop("wristlaser_hold", WRIST_CUT)
        if tool:
            audio.track_play("wristlaser_shot", 0.0, volume=1.0)
            audio.track_play("wristlaser_extra", 0.0, volume=1.0)
            audio.track_play("wristlaser_wub", 0.0, volume=WRIST_WUB_VOLUME)
        w_.update(held=False, hold=False)
def jet_signals():
    try:
        return struct.unpack("<2d", _JET[0:16])
    except Exception:
        return 0.0, 0.0
def in_anomaly(p_, te_=None):
    b_ = PULL_INSIDE_BOX
    if p_ is None or not (b_[0][0] < p_[0] < b_[0][1] and b_[1][0] < p_[1] < b_[1][1] and b_[2][0] < p_[2] < b_[2][1]):
        return False
    return te_ is None or float(np.linalg.norm(np.asarray(p_) - np.asarray(te_))) > PULL_NEAR_TE
def _centre(radial):
    c_ = -radial * PULL_CENTER
    n_ = float(np.linalg.norm(c_))
    return c_ * (PULL_CENTER_MAX / n_) if n_ > PULL_CENTER_MAX else c_
_ROLL = mmap.mmap(-1, 64, tagname="IronManFlightRoll")
def roll_share(rate, axis):
    now_ = time.perf_counter()
    a_ = (0.0, 0.0, 0.0) if axis is None else tuple(float(x) for x in axis)
    try:
        _ROLL[0:40] = struct.pack("<5d", now_, float(rate), *a_)
        ack_ = struct.unpack_from("<d", _ROLL, 40)[0]
    except Exception:
        return False
    return now_ - ack_ < 0.3
def warp_to(world, offset, vel, look):
    n_ = (struct.unpack_from("<I", _WARP, 0)[0] + 1) & 0xFFFFFFFF
    _WARP[8:104] = struct.pack("<12d", *world, *offset, *vel, *look)
    _WARP[0:4] = struct.pack("<I", n_)
    return n_
def warp_done(n_):
    return struct.unpack_from("<I", _WARP, 4)[0] == n_
_STATION = mmap.mmap(-1, 192, tagname="IronManFlightStation")
def station():
    try:
        v_ = struct.unpack("<19d", _STATION[0:152])
    except Exception:
        return None
    if time.perf_counter() - v_[0] > 1.5:
        return None
    return (np.array(v_[1:4]), np.array(v_[4:13]).reshape(3, 3), np.array(v_[13:16]), np.array(v_[16:19]))
_FREIGHTER = mmap.mmap(-1, 192, tagname="IronManFlightFreighter")
def cruise_cap(level):
    lv_ = max(0.0, min(1.0, level)) * len(CRUISE_TIERS)
    i_ = min(len(CRUISE_TIERS) - 1, int(lv_))
    lo_, hi_ = CRUISE_TIERS[i_]
    return lo_ * (hi_ / lo_) ** (lv_ - i_)
def cruise_fill_rate(level):
    n_ = len(CRUISE_TIERS)
    seg_ = min(n_ - 1, int(level * n_ + 1e-9))
    return 1.0 / n_ / CRUISE_SEG_FILL[seg_]
def cruise_mark(level):
    n_ = len(CRUISE_TIERS)
    return min(n_, int(level * n_ + 1e-9))
def cruise_tier(level):
    if level <= 0.0:
        return 0
    return min(len(CRUISE_TIERS), int(level * len(CRUISE_TIERS) + 1e-9) + 1)
def cruise_level_step(lvl, rate, dt, now, lock):
    if rate == 0:
        return lvl, lock
    d_ = 1 if rate > 0 else -1
    n_ = len(CRUISE_TIERS)
    if lock is not None and lock[1] == d_ and now < lock[0]:
        return lvl, lock
    l2 = max(0.0, min(1.0, lvl + rate * dt))
    for j_ in range(1, n_):
        b_ = j_ / n_
        if (lvl < b_ <= l2) or (lvl > b_ >= l2):
            return b_, (now + CRUISE_DETENT, d_)
    return l2, lock
def ip_auto_origin(now, level):
    return now + IP_AUDIO_LATENCY - max(0.0, level) * len(CRUISE_TIERS) * IP_CHARGE_TIME
def ip_hum_volume(rate):
    return IP_HUM_VOLUME * max(0.25, rate) ** IP_HUM_LOUD_K
def ip_hum_rate(level):
    x_ = max(0.0, min(1.0, level)) * len(CRUISE_TIERS) - 1.0
    if x_ <= 0.0:
        return IP_HUM_PITCH[0]
    lo_, hi_, u_ = (IP_HUM_PITCH[0], IP_HUM_PITCH[1], x_) if x_ <= 1.0 else (IP_HUM_PITCH[1], IP_HUM_PITCH[2], x_ - 1.0)
    return lo_ * (hi_ / lo_) ** min(1.0, u_)
def ip_auto_level(now, origin):
    return min(1.0, max(0.0, (now - origin) / IP_CHARGE_TIME)) / len(CRUISE_TIERS)
def throttle_speed(t):
    if t < 0:
        return THROTTLE_REVERSE_SPEED
    return MIN_SPEED + (MAX_SPEED - MIN_SPEED) * min(1.0, t) ** THROTTLE_CURVE
def throttle_step(t, fin, dt, now, lock):
    if fin > 0:
        return min(1.0, t + fin * dt / THROTTLE_UP), None, False
    if fin < 0:
        if t > 0.0:
            t2 = t + fin * dt / THROTTLE_DOWN
            if t2 <= 0.0:
                return 0.0, now + THROTTLE_DETENT, False
            return t2, lock, False
        if lock is not None and now < lock:
            return 0.0, lock, False
        return 0.0, lock, True
    return t, lock, False
def freighter():
    try:
        v_ = struct.unpack("<19d", _FREIGHTER[0:152])
    except Exception:
        return None
    if time.perf_counter() - v_[0] > 1.5 or v_[15] < 1:
        return None
    return (np.array(v_[1:4]), np.array(v_[4:13]).reshape(3, 3), v_[13], v_[14], list(v_[16:16 + int(min(3, v_[15]))]))
def freighter_hop(l_, vl_, dz_, dy_, xs_):
    door_ = min(xs_, key=lambda x_: abs(l_[0] - x_))
    if abs(l_[0] - door_) > FR_DOOR_HALF[0] or abs(l_[1] - dy_) > FR_DOOR_HALF[1]:
        return None
    wall_ = dz_ + FR_WALL
    if wall_ - FR_CATCH < l_[2] < wall_ + 0.5 and vl_[2] > FR_MIN_SPEED:
        return wall_ + FR_HOP
    if wall_ - 0.5 < l_[2] < wall_ + FR_CATCH and vl_[2] < -FR_MIN_SPEED:
        return wall_ - FR_HOP
    return None
def dock_tunnel():
    try:
        t_, *v_ = struct.unpack("<7d", _NAV[48:104])
    except Exception:
        return None
    return (np.array(v_[0:3]), np.array(v_[3:6])) if time.perf_counter() - t_ < 1.5 else None
_GAME = mmap.mmap(-1, 16, tagname="IronManFlightGame")
def game_component():
    try:
        return struct.unpack_from("<Q", _GAME, 8)[0]
    except Exception:
        return 0
class CrawlWatch:
    JUMP = (1.5, 3.5)
    NEED = 4
    def __init__(self):
        self.last, self.jumps, self.fixed_t, self.busy = 0.0, [], -1e9, False
    def step(self, now, fg, menu_up):
        try:
            t = struct.unpack_from("<d", _GAME, 0)[0]
        except Exception:
            return False
        if t <= 0.0 or t == self.last:
            return False
        gap, self.last = t - self.last, t
        if not fg or menu_up or not (self.JUMP[0] <= gap <= self.JUMP[1]):
            self.jumps = []
            return False
        self.jumps.append(gap)
        if len(self.jumps) >= self.NEED and now - self.fixed_t > 60.0 and not self.busy:
            self.jumps, self.fixed_t, self.busy = [], now, True
            import threading
            threading.Thread(target=self._wake, daemon=True, name="crawl-fix").start()
            return True
        return False
    def _wake(self):
        try:
            u_ = ctypes.windll.user32
            hw_ = keys.game_window()
            u_.ShowWindow(hw_, 6)
            time.sleep(1.5)
            u_.ShowWindow(hw_, 9)
            keys.focus()
        except BaseException:
            pass
        finally:
            self.busy = False
def game_stalled(now):
    try:
        t = struct.unpack_from("<d", _GAME, 0)[0]
    except Exception:
        return False
    return t > 0.0 and now - t > 0.3
_HUD = mmap.mmap(-1, 128, tagname="IronManFlightHUD")
_ARMS = mmap.mmap(-1, 64, tagname="IronManFlightArms2")
_ARMS_FMT = "<dQI6f"
_HUD_FMT = "<dIddddIdddddId"
_hud_proc = [None]
_HUD_BOOT = [0, 0.0, 0.0]
def hud(flying, burning=False, fuel=1.0, locked=False, charge=1.0, sonic=0.0, speed=0.0, right=False, brake=False,
        cruising=False, build=-1.0, throttle=0.0, cruise_level=0.0, shock_n=0, shock_size=1.0, gated=False,
        refused=False):
    try:
        _HUD[:struct.calcsize(_HUD_FMT)] = struct.pack(
            _HUD_FMT, time.perf_counter(), (1 if flying else 0) | (2 if burning else 0) | (4 if locked else 0)
            | (8 if sonic > 0 else 0) | (16 if right else 0) | (32 if brake else 0)
            | (64 if arsenal.state.on else 0) | (128 if cruising else 0)
            | (256 if charge < SONIC_TAP and build < 0 else 0)
            | (1024 if gated else 0) | (2048 if refused else 0), fuel, charge, sonic, speed,
            *_HUD_BOOT, build, throttle, cruise_level, shock_n & 0xFFFFFFFF, shock_size)
    except Exception:
        pass
def hud_start():
    _hud_proc[0] = None
    try:
        import subprocess
        _hud_proc[0] = subprocess.Popen([sys.executable, "-u", str(HERE / "hud.py"), str(os.getpid())],
                                        cwd=HERE, creationflags=0x08000000)
        keys._OURS.add(_hud_proc[0].pid)
    except Exception as e:
        print(f"HUD unavailable ({e})", flush=True)
def sfx(name):
    rumble = {"flight_on": (0.5, 0.2, 0.18), "flight_off": (0.3, 0.0, 0.12),
              "afterburner_on": (0.9, 0.6, 0.3)}.get(name)
    if rumble:
        PAD.buzz(*rumble)
    audio.play(name)
_SFX_HAVE = {}
def sfx_any(*names):
    for n_ in names:
        if n_ not in _SFX_HAVE:
            _SFX_HAVE[n_] = (HERE / "sounds" / f"{n_}.wav").exists()
        if _SFX_HAVE[n_]:
            sfx(n_)
            return n_
    return None
cue = audio.cue
def status(text, cue_name=None):
    print(text, flush=True)
    try:
        CTRL.line(text)
    except Exception:
        pass
    audio.title(text)
    if cue_name:
        cue(cue_name)
_KEY_ACTIONS = (("W", "forward"), ("S", "back"), ("A", "left"), ("D", "right"), ("R", "climb"), ("F", "descend"),
                ("SHIFT", "afterburner"), ("F8", "fly_toggle"), ("PGUP", "faster"), ("PGDN", "slower"),
                ("END", "quit"))
def rebuild_keymap(S):
    km_ = {VK[n]: S.vk(a) for n, a in _KEY_ACTIONS}
    KEYMAP.clear()
    KEYMAP.update({d: b for d, b in km_.items() if b and b != d})
    VK["ARM"] = S.vk("arm_toggle") or 0x07
    VK["ARSENAL"] = S.vk("arsenal_toggle") or 0x07
    VK["PANEL"] = S.vk("panel") or 0x07
    share_keymap()
def apply_fx_settings(S):
    try:
        cm_ = S.camera
        if hasattr(speedfx, "set_effects"):
            speedfx.set_effects(bool(cm_["speed_effects"]))
        if hasattr(speedfx, "set_blur"):
            speedfx.set_blur(bool(cm_["motion_blur"]))
        if hasattr(speedfx, "set_strength"):
            speedfx.set_strength(float(cm_.get("effects_strength", 1.0)))
        speedfx._fx.punch_on = bool(cm_["speed_effects"]) and bool(cm_.get("camera_kicks", True))
    except Exception as e_:
        print(f"speed effects settings: {e_!r}", flush=True)
def share_keymap():
    try:
        vks = [KEYMAP.get(VK[n], 0) for n in ("W", "A", "S", "D", "R", "F")]
        flags = 1
        _SHM[120:128] = bytes([v & 0xFF for v in vks] + [flags, int(round(SET.flight["double_tap_window"] * 100))])
    except Exception:
        pass
class ShoulderCam:
    CAMS = (
        (0x5042DBC, 0.4),
        (0x5042FDC, 0.55),
        (0x50430EC, 0.65),
        (0x50431FC, 0.65),
        (0x504330C, 0.8),
        (0x504341C, 0.6),
        (0x504352C, 0.7),
        (0x504363C, 0.8),
        (0x504374C, 0.2),
        (0x504385C, 0.8),
        (0x504396C, 1.0),
        (0x5043B8C, 0.8),
        (0x5043C9C, 0.6),
        (0x5043DAC, 0.65),
        (0x5043EBC, 0.4),
        (0x504440C, 0.6),
        (0x504451C, 0.8),
        (0x504462C, 0.6),
        (0x504473C, 0.4),
        (0x504484C, 0.2),
        (0x504495C, 1.5),
        (0x5044A6C, 1.0),
        (0x5044B7C, 0.4),
        (0x5044C8C, 0.55),
        (0x5044D9C, 0.8),
        (0x5044EAC, 0.7),
        (0x5044FBC, 0.55),
        (0x50450CC, 0.7),
        (0x50452EC, 0.55),
    )
    DATA_PTR = 0x6F6B208
    CAM_OBJ = 0x92ECC0
    CAM_VTABLE = 0x4B18B20
    RETARGET = 0x81C
    def __init__(self):
        self.addrs, self.side = [], 1.0
        try:
            import pymem.process
            self.base = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
            addrs = [self.base + rva for rva, _ in self.CAMS]
            vals = [pm.read_float(a) for a in addrs]
            if all(abs(abs(v) - abs(d)) < 1e-3 for v, (_, d) in zip(vals, self.CAMS)):
                self.addrs = addrs
                self.side = 1.0 if vals[-1] * self.CAMS[-1][1] > 0 else -1.0
        except Exception:
            pass
    def ok(self):
        return bool(self.addrs)
    def _nudge(self):
        try:
            data = pm.read_ulonglong(self.base + self.DATA_PTR)
            cam = data + self.CAM_OBJ
            if data and pm.read_ulonglong(cam) == self.base + self.CAM_VTABLE:
                b = pm.read_uchar(cam + self.RETARGET)
                pm.write_uchar(cam + self.RETARGET, b ^ 1)
        except Exception:
            pass
    def set(self, side):
        if self.addrs:
            self.side = side
            for a, (_, d) in zip(self.addrs, self.CAMS):
                pm.write_float(a, d * side)
            self._nudge()
    def swap(self, now=None):
        self.set(-self.side)
    def update(self, now):
        pass
BODY_STALE = [cfg.get("verified") is False]
def addresses_ok():
    if BODY_STALE[0]:
        return False
    if BODY is None:
        return False
    from locate import still_valid
    return still_valid(BODY, VEL)
def character_ok():
    for _ in range(4):
        if addresses_ok():
            return True
        time.sleep(0.25)
    return relocate()
DECK_MSG = ("on a Corvette deck: Iron Man mode stays off there (the deck moves you in the ship's own frame). "
            "Step off it and double-tap Space")
def ctl_busy(text=None):
    try:
        CTRL.publish(flags=int(CTRL.tel.get("flags", 0)) | _control.FL["busy"])
        if text:
            CTRL.line(text)
    except Exception:
        pass
def relocate():
    import locate
    ctl_busy("re-finding your character ...")
    print("re-finding your character...", flush=True)
    keys.release("SPACE")
    time.sleep(0.6)
    obj, vel, _ = locate.locate(log=lambda m: print(m, flush=True) if SET.debug["verbose"] else None)
    if vel is None:
        return False
    adopt(obj, vel)
    return True
def adopt(obj, vel):
    global VEL, BODY
    BODY, VEL = obj, vel
    BODY_STALE[0] = False
    try:
        c = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        c.update(body=f"{obj:X}", vel=f"{vel:X}", verified=True)
        CONFIG.write_text(json.dumps(c, indent=2))
    except (OSError, ValueError):
        pass
STUB_HOLD = math.sin(math.radians(25))
CAM_RATE_MAX = math.radians(1500)
def within(a, b, ang):
    return ang >= math.pi or float(np.dot(a, b)) > math.cos(ang)
class Steer:
    def __init__(self, up, pitch_steers=True):
        self.up = unit(np.asarray(up, dtype=np.float64))
        self.pitch_steers = pitch_steers
        self.head, self.head_known = None, False
        self.pitch = 0.0
        self.view, self.view_t = None, 0.0
        self.cand, self.cand_since, self.cand_t = None, 0.0, 0.0
        self.yaw_sign = 1.0
    def set_up(self, up):
        self.up = unit(np.asarray(up, dtype=np.float64))
        if self.head is not None:
            self.head = flat(self.head, self.up)
            if self.head is None:
                self.head, self.head_known = any_flat(self.up), False
    def _accept(self, view, now):
        view = clean_unit(view)
        if view is None:
            return self.view
        if self.view is None or within(view, self.view, SNAP_ANGLE + CAM_RATE_MAX * (now - self.view_t)):
            self.view, self.view_t, self.cand = view, now, None
        elif self.cand is None or not within(view, self.cand, SNAP_ANGLE / 3 + CAM_RATE_MAX * (now - self.cand_t)):
            self.cand, self.cand_since, self.cand_t = view, now, now
        else:
            self.cand, self.cand_t = view, now
            if now - self.cand_since >= SNAP_CONFIRM:
                self.view, self.view_t, self.cand = view, now, None
        return self.view
    def update(self, dt, view, now, true_view=True):
        up = self.up
        hold = HEAD_HOLD if true_view else STUB_HOLD
        view = self._accept(view, now)
        if view is not None:
            d = float(np.clip(np.dot(view, up), -1.0, 1.0))
            s = math.sqrt(max(0.0, 1.0 - d * d))
            h = flat(view, up)
            if h is not None and s > hold and not self.head_known:
                self.head, self.head_known = h, True
            elif h is not None and self.head_known:
                x = min(max((s - hold) / max(min(hold, 0.08), 1e-6), 0.0), 1.0)
                err = yaw_about(self.head, h, up)
                if abs(err) > math.pi - 0.05 and math.copysign(1.0, err) != self.yaw_sign:
                    err = self.yaw_sign * (2 * math.pi - abs(err))
                step = err * ease(dt, CAM_SMOOTH) * x * x * (3 - 2 * x)
                step = max(-YAW_RATE_MAX * dt, min(YAW_RATE_MAX * dt, step))
                if abs(step) > 1e-6:
                    self.yaw_sign = math.copysign(1.0, step)
                self.head = turn_about(self.head, step, up)
            pt = max(-PITCH_LIMIT, min(PITCH_LIMIT, math.atan2(d, s))) if true_view else 0.0
            gap = (pt - self.pitch) * ease(dt, CAM_SMOOTH)
            self.pitch += max(-PITCH_RATE_MAX * dt, min(PITCH_RATE_MAX * dt, gap))
        if self.head is None:
            if view is None:
                return None, None, None
            self.head = any_flat(up)
        head = flat(self.head, up)
        self.head = head if head is not None else any_flat(up)
        head = self.head
        p = dead_zone(self.pitch) if self.pitch_steers else 0.0
        fwd = head * math.cos(p) + up * math.sin(p)
        right = np.cross(head, up)
        cam_up = up * math.cos(p) - head * math.sin(p)
        return fwd, right, cam_up
def dead_zone(p):
    a = abs(p)
    if a <= LEVEL_DEADZONE:
        return 0.0
    if a < LOOK_PITCH_FULL:
        a = (a - LEVEL_DEADZONE) * LOOK_PITCH_FULL / (LOOK_PITCH_FULL - LEVEL_DEADZONE)
    return math.copysign(min(a, PITCH_LIMIT), p)
class SonicBlast:
    def __init__(self):
        self.meter = 1.0
        self.up_t = -9.0
        self.armed = True
        self.poured = -9.0
        self.fired = -9.0
        self.refused_t = -9.0
        self.chain = 0
        self.rearm = SONIC_REARM
        self.build = None
    def key(self, now, raw):
        if raw:
            fresh, self.armed, self.up_t = self.armed, False, None
            return fresh
        if self.up_t is None:
            self.up_t = now
        if now - self.up_t >= self.rearm:
            self.armed = True
        return False
    def sections(self):
        return int(self.meter * SONIC_SECTIONS + 1e-6)
    def fire(self, now):
        n_ = self.sections()
        if n_ < 1:
            return None
        self.chain = max(1, min(SONIC_SECTIONS, SONIC_SECTIONS + 1 - n_))
        self.meter = max(0.0, self.meter - 1.0 / SONIC_SECTIONS)
        if self.meter < 1e-6:
            self.meter = 0.0
        self.poured = self.fired = now
        return self.chain
    def refuse(self, now):
        self.refused_t = now
    def cancel(self):
        pass
    def refill(self, now, dt):
        if now - self.poured >= SONIC_REFILL_DELAY and self.meter < 1.0:
            self.meter = min(1.0, self.meter + dt / SONIC_REFILL_TIME)
def water_flag(raw, was, now, seen, pos, wpos, up):
    if raw:
        return True
    if not was or now - seen >= WATER_OUT_HOLD:
        return False
    if pos is None or wpos is None or up is None:
        return True
    try:
        return float(np.dot(np.asarray(pos) - np.asarray(wpos), np.asarray(up))) <= WATER_OUT_HEIGHT
    except Exception:
        return True
def surf_update(surf, surf_t, p, now, up):
    p = np.asarray(p, dtype=float)
    if surf is None or now - surf_t > SKIM_FRESH:
        return p.copy(), now
    d = p - surf
    h = float(np.dot(d, up))
    if float(np.linalg.norm(d - up * h)) > SKIM_FAR:
        return p.copy(), now
    return p - up * ((1.0 - SKIM_EMA) * h), now
def skim_vz(h, el):
    if not (SKIM_BAND[0] < h < SKIM_BAND[1]) or not (SKIM_LOOK[0] < el < SKIM_LOOK[1]):
        return None
    return max(-SKIM_MAX, min(SKIM_MAX, SKIM_GAIN * (-SKIM_DEPTH - h)))
class PhysicalKey:
    PHYS_STUCK = 0.5
    PHYS_DEAD = 2.0
    def __init__(self, vk):
        self.vk, self.async_up_t = vk, None
        try:
            import spacetap
            self.tap = spacetap.DoubleTap(window=0.0, vk=vk)
        except Exception:
            self.tap = None
    def seen(self):
        t = self.tap
        return t is not None and (t.physically_down or t.last_release > 0.0)
    def ok(self, now):
        t = self.tap
        if t is None or not getattr(t, "hooked", False):
            return False
        if now - getattr(t, "last_any", 0.0) > self.PHYS_DEAD:
            inj_ = getattr(t, "injected_down", ())
            if any(_gaks(vk_) & 0x8000 and vk_ not in inj_ for vk_ in (0x57, 0x41, 0x53, 0x44, 0x20)):
                return False
        return True
    def down(self, now):
        if self.tap is None or not self.tap.physically_down:
            self.async_up_t = None
            return False
        if _gaks(self.vk) & 0x8000:
            self.async_up_t = None
        elif self.async_up_t is None:
            self.async_up_t = now
        elif now - self.async_up_t > self.PHYS_STUCK:
            self.tap.physically_down, self.async_up_t = False, None
            return False
        return True
def fly_step(v, dt, fwd, right, cam_up, up, fw, st, cl, boost, drag_k=1.0, drags=None, side_level=None):
    if fwd is None:
        fwd, right, cam_up, fw, st = np.zeros(3), np.zeros(3), up, 0, 0
    if CLASSIC:
        want = unit(fwd * fw + right * st + up * cl) * SPEED * boost
        speeding_up = np.linalg.norm(want) > np.linalg.norm(v)
        nv = v + (want - v) * ease(dt, ACCEL_TIME if speeding_up else BRAKE_TIME)
    else:
        k_ = (SPEED / 18.0) * boost
        ks_ = (max(SPEED, side_level) / 18.0) * boost if side_level else k_
        kst_ = ((max(SPEED, HOVER_STRAFE_SPEED) / 18.0) * boost if side_level and fw == 0 else ks_)
        want = fwd * fw * THRUST_FWD * k_ + right * st * THRUST_FWD * kst_ + cam_up * cl * THRUST_UP * ks_
        planar, vert = math.hypot(fw, st), abs(cl)
        if drags is not None:
            drag = drags[0] if planar or vert else drags[1]
        elif planar or vert:
            drag = (DRAG_THRUST * planar + DRAG_THRUST_UP * vert) / (planar + vert)
        else:
            drag = DRAG_COAST
        nv = v * math.exp(-drag * drag_k * dt)
        ahead = float(np.dot(nv, fwd))
        if fw < 0 and ahead > 2.0 and drags is None:
            nv = nv + fwd * ahead * (math.exp(-(BRAKE_DRAG - drag) * dt) - 1.0)
        nv = nv + want * dt
        if side_level and fw == 0 and st:
            sv_ = float(np.dot(nv, right))
            if sv_ * st > HOVER_STRAFE_MAX:
                nv = nv - right * (sv_ - math.copysign(HOVER_STRAFE_MAX, sv_))
        spd = float(np.linalg.norm(nv))
        if fw > 0 and spd > 2.0:
            vd = nv / spd
            ang = math.acos(float(np.clip(np.dot(vd, fwd), -1.0, 1.0)))
            if ang < math.radians(100):
                vd = slerp_toward(vd, fwd, min(ang * ease(dt, 1.0 / TURN_GRIP), CARVE_RATE_MAX * dt))
                nv = vd * spd
    if not np.isfinite(nv).all():
        nv = v if np.isfinite(v).all() else np.zeros(3)
    return nv, want
_CRUISE_TIERS0 = CRUISE_TIERS
_CRUISE_FAR0 = CRUISE_FAR
_SOUND_GROUPS = {"suit_sounds": ("flight_on", "flight_off", "afterburner_on", "land_hard", "land_soft",
                                 "brake_boom", "suit_online", "power_down", "brake_wub"),
                 "boom_sounds": ("sonic_boom", "sonic_boom_mid", "sonic_burst", "sonic_blast_1", "sonic_blast_2",
                                 "sonic_blast_3", "boom_denied", "ip_boom1", "ip_boom2", "ip_boom3")}
IP_MODE = "mine"
_IP_MUTE = {"mine": (),
            "off": ("ip_stage1", "ip_charge", "ip_hum", "ip_boom1", "ip_boom2", "ip_boom3",
                    "ip_growl",
                    "ip_stage1_rev")}
SONIC_KICK_SCALE = 1.0
RESTART_ONLY = {("flight", "remember_speed"), ("debug", "flight_log"), ("camera", "speed_effects"),
                ("camera", "motion_blur")}
HUD_SETTINGS = {("hud", "hud"), ("hud", "space_map"), ("hud", "shock_waves"), ("cruise", "top_speed_kms")}
def apply_settings(S):
    global MIN_SPEED, MAX_SPEED, START_SPEED, KICK_SPEED, THROTTLE_UP, THROTTLE_DOWN, THROTTLE_CURVE, THROTTLE_DETENT
    global THROTTLE_REVERSE_SPEED, AFTERBURNER, AB_FUEL_TIME, AB_RECHARGE_TIME, DIVE_SPEED, BRAKE_TAP
    global SONIC_BOOST, SONIC_CHARGE_TIME, SONIC_REFILL_TIME, SONIC_KICK_SCALE, CRUISE_SEG_FILL, CRUISE_DRAIN
    global CRUISE_TIERS, CRUISE_MAX, IP_HUM_VOLUME, FLIP_STRAFE, DIVE_LANDS, CAM_CENTER_DELAY, CRUISE_FAR, PILOT_FLAME
    global HOVER_MOVE_SPEED
    f = S.flight
    MIN_SPEED, MAX_SPEED = f["min_speed"], f["max_speed"]
    START_SPEED = f["start_speed"]
    KICK_SPEED = START_SPEED if THROTTLE_MODE else None
    THROTTLE_UP, THROTTLE_DOWN = f["throttle_up_time"], f["throttle_down_time"]
    THROTTLE_CURVE, THROTTLE_DETENT, THROTTLE_REVERSE_SPEED = f["throttle_curve"], f["hover_detent"], f["reverse_speed"]
    AFTERBURNER, AB_FUEL_TIME, AB_RECHARGE_TIME = f["afterburner_power"], f["afterburner_time"], f["afterburner_recharge"]
    DIVE_SPEED, BRAKE_TAP = f["dive_boost"], f["hard_brake_window"]
    FLIP_STRAFE, DIVE_LANDS = f["flip_strafe"], f["dive_lands"]
    PILOT_FLAME = max(0.05, min(1.0, float(f.get("pilot_flame", PILOT_FLAME))))
    HOVER_MOVE_SPEED = max(1.0, min(60.0, float(f.get("hover_move_speed", HOVER_MOVE_SPEED))))
    b = S.boom
    SONIC_BOOST, SONIC_CHARGE_TIME, SONIC_REFILL_TIME, SONIC_KICK_SCALE = (b["boost"], b["charge_time"],
                                                                          b["refill_time"], b["kick_scale"])
    c = S.cruise
    k_ = c["top_speed_kms"] * 1000.0 / 200000.0
    CRUISE_TIERS = tuple((lo * k_, hi * k_) for lo, hi in _CRUISE_TIERS0)
    CRUISE_TIERS = ((max(_CRUISE_TIERS0[0][0], CRUISE_TIERS[0][0]), max(CRUISE_START * 1.5, CRUISE_TIERS[0][1])),
                    ) + CRUISE_TIERS[1:]
    CRUISE_MAX = c["top_speed_kms"] * 1000.0
    CRUISE_FAR = (_CRUISE_FAR0[0] * k_, _CRUISE_FAR0[1])
    CRUISE_SEG_FILL = (IP_CHARGE_TIME, c["tier_fill_time"], c["tier_fill_time"])
    CRUISE_DRAIN = c["drain_time"]
    CAM_CENTER_DELAY = S.camera["recenter_delay"]
    IP_HUM_VOLUME = S.sound["hum_volume"]
    try:
        audio._state["cues"] = bool(S.sound["cues"])
        audio.muted = {n for g, names in _SOUND_GROUPS.items() if not S.sound[g] for n in names}
    except Exception:
        pass
    global IP_MODE
    IP_MODE = "mine" if S.sound.get("interplanetary", True) else "off"
    try:
        audio.muted = set(audio.muted) | set(_IP_MUTE[IP_MODE])
    except Exception:
        pass
apply_settings(SET)
FOCUS_CMDS = {"fly", "refind", "relight"}
def _settings_diff(a, b):
    out = set()
    for sec in _settings.DEFAULTS:
        for k in _settings.DEFAULTS[sec]:
            if getattr(a, sec).get(k) != getattr(b, sec).get(k):
                out.add((sec, k))
    return out
def _start_panel():
    import subprocess
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    try:
        subprocess.Popen([str(w if w.exists() else exe), str(HERE / "control_panel.py")], cwd=HERE,
                         creationflags=0x00000008 | 0x00000200)
        return True
    except Exception as e:
        print(f"couldn't open Suit Control ({e})", flush=True)
        return False
def main():
    global SPEED, SET
    import charstate
    import jetfuel
    def own_slot():
        try:
            with open(HERE / "limbjets_log.txt", "rb") as f_:
                f_.seek(0, 2)
                f_.seek(max(0, f_.tell() - 262144))
                txt = f_.read().decode(errors="replace")
            i = txt.rfind("refresh on 0x")
            if i >= 0:
                a_ = int(txt[i + 11:].split(":")[0], 16) + charstate.OFFSET
                if charstate.alive(a_):
                    return a_
        except Exception:
            pass
        return None
    states = charstate.candidates()
    if own_slot():
        states = [own_slot()]
    def keep_states_fresh():
        import threading
        logf = HERE / "limbjets_log.txt"
        def rebuilds():
            try:
                size = logf.stat().st_size
                if size < pos_[0]:
                    pos_[0], count_[0] = 0, 0
                if size > pos_[0]:
                    with open(logf, "rb") as f_:
                        f_.seek(pos_[0])
                        count_[0] += f_.read().count(b"refresh on ")
                    pos_[0] = size
                return count_[0]
            except OSError:
                return count_[0]
        pos_, count_ = [0], [0]
        def run():
            seen = rebuilds()
            while True:
                time.sleep(2.0)
                n = rebuilds()
                if n == seen and not charstate.any_dead(list(states)):
                    continue
                seen = n
                time.sleep(1.0)
                try:
                    new = [own_slot()] if own_slot() else charstate.candidates()
                except Exception:
                    continue
                if new and set(new) != set(states):
                    states[:] = new
                    print(f"character rebuilt: {len(new)} state slots re-found", flush=True)
        threading.Thread(target=run, daemon=True).start()
    keep_states_fresh()
    tank = jetfuel.locate()
    tank_full = max(jetfuel.read(tank), 1.0) if tank else None
    player = tank - jetfuel.OFFSET if tank else None
    import refind
    refinder = refind.Refinder(player, addresses_ok)
    def view_pitch(up_ref):
        ax_ = viewdir.cam_axes(pm, BASE) if viewdir is not None and BASE is not None else None
        if ax_ is None or up_ref is None:
            return None
        return math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(np.array(ax_[2]), up_ref))))))
    XG = [None, 0.0]
    def game_up():
        if XG[0] is not None and time.perf_counter() < XG[1]:
            return XG[0]
        if player is None:
            return None
        try:
            u = rd(player + 0x320)
        except Exception:
            return None
        return unit(u) if 0.9 < np.linalg.norm(u) < 1.1 else None
    if SET.debug["verbose"]:
        print(f"jetpack tank {'0x%X, full = %.1f s' % (tank, tank_full) if tank else 'not found'}", flush=True)
    elif not tank:
        print("jetpack fuel couldn't be found: while flying, the jetpack may run dry after ~12 s "
              "(restart the launcher if it does)", flush=True)
    my_state, grounded_since, last_blocked = None, None, -1.0
    on, was = False, {}
    next_fill = 0.0
    up, steer, want = None, None, np.zeros(3)
    space, sp_axes = False, (None, None, None)
    roll_v = 0.0
    next_zone, settle_up, relight = 0.0, 0.0, False
    zone_t = (0.0, None)
    zone_dbg_t = 0.0
    space_since = 0.0
    space_cam_t = 0.0
    freeze_cmd = freeze_fh = freeze_look = freeze_face = None
    level_rows = None
    freeze, freeze_next = None, 0.0
    handoff_orig = None
    xrows = None
    xhold = None
    entry_pitch = -ENTRY_PITCH
    center_on = False
    planet_pitch, space_cam = 0.0, (0.0, 0.0)
    entry_aim, fix_cam, next_fix = None, (0.0, 0.0), 0.0
    cam_angles_until, cam_pitch_in = 0.0, None
    v = np.zeros(3)
    last = time.perf_counter()
    next_log, next_title = 0.0, 0.0
    log = None
    if SET.debug["flight_log"]:
        new_log = not LOG.exists()
        log = LOG.open("a", encoding="utf-8")
        if new_log:
            log.write("time,on,speed_setting,speed,want,climb,boost\n")
    audio.start(HERE / "sounds", volume=SET.sound["sound_volume"], cues=SET.sound["cues"])
    audio.track_open("ip_charge")
    audio.track_open("ip_hum")
    for n_ in UNIBEAM_SOUNDS + WRIST_SOUNDS:
        audio.track_open(n_)
    if IP_GROWL:
        audio.track_open("ip_growl")
    share_keymap()
    if not SET.camera["motion_blur"]:
        speedfx.DIVE, speedfx.BURNER = speedfx.DIVE[:2] + (0.0,), speedfx.BURNER[:2] + (0.0,)
    import collections
    import spacetap
    fall_hist = collections.deque(maxlen=1024)
    armed = True
    next_block = 0.0
    taps = spacetap.DoubleTap(window=SET.flight["double_tap_window"] + 0.05)
    history = collections.deque(maxlen=400)
    next_sample = 0.0
    last_up = None
    def up_between(t0, t1):
        pts = [(t, vv) for t, vv in history if t0 <= t <= t1]
        if len(pts) < 4 or pts[-1][0] - pts[0][0] < 0.06:
            return None
        ts = np.array([p[0] for p in pts])
        vs = np.array([p[1] for p in pts])
        acc = np.polyfit(ts - ts[0], vs, 1)[0]
        vel = vs.mean(axis=0)
        g = np.linalg.norm(acc)
        if 3.0 < g < 40.0 and np.dot(-acc, vel) > 0:
            return -unit(acc)
        if np.linalg.norm(vel) > 2.0:
            return unit(vel)
        return None
    beat = [0]
    def limb_flag(on_):
        beat[0] += 1
        text = f"1 {player:X} {CAM:X} {CAM_SIGN} {beat[0]}" if on_ and player else ("1" if on_ else f"0 {beat[0]}")
        tmp = HERE / "limbjets.flag.tmp"
        for _ in range(20):
            try:
                tmp.write_text(text)
                tmp.replace(HERE / "limbjets.flag")
                return
            except OSError:
                time.sleep(0.005)
    limb_flag(False)
    sys.setswitchinterval(0.0005)
    import gc
    gc.collect()
    gc.freeze()
    if viewdir is None or BASE is None or viewdir.view_dir(pm, BASE) is None:
        print("the game's camera can't be read right now: you'll fly level (aiming up/down won't climb or dive)"
              " until it can", flush=True)
    try:
        import modsguard
        if modsguard.disabled():
            print("WARNING: the game has all mods switched off (it does that after a crash) -- no hand / foot "
                  "jets or poses this session. Quit the game; starting it from Steam switches them back on "
                  "(modsguard.py), or set DisableAllMods to false in its GCMODSETTINGS.MXML", flush=True)
    except Exception:
        pass
    seeded = False
    try:
        c_ = json.loads(CONFIG.read_text())
        if c_.get("cands") and time.time() - float(c_.get("cands_t", 0)) < 1800:
            seeded = refinder.seed([(int(o, 16), int(va, 16)) for o, va in c_["cands"]])
    except (OSError, ValueError, TypeError):
        pass
    if not addresses_ok():
        try:
            import lookup
            b_, v_ = lookup.body(pm)
            if b_:
                adopt(b_, v_)
        except Exception:
            pass
    startup = refind.Startup(refinder, known=addresses_ok(), seeded=seeded)
    try:
        import lookup
        wvt_ = lookup.vtable(pm, "cGcPlayerWeapon")
        if lookup.weapon(pm):
            arsenal.state.weapon = lookup.weapon(pm)
        try:
            w_ = struct.unpack_from("<Q", _ARMS, 8)[0]
            if w_ and struct.unpack("<Q", pm.read_bytes(w_, 8))[0] == wvt_:
                arsenal.state.weapon = w_
        except Exception:
            pass
        arsenal.start(pm, wvt_)
    except Exception as e:
        print(f"ship arsenal unavailable ({e.__class__.__name__})", flush=True)
    ship_arms, arsenal_note, reload_tap, reload_tries, reload_sel = True, "", 0.0, 0, None
    print("suit starting up (the HUD shows it)" + ("" if addresses_ok() else
          ": take a few steps and it syncs to you -- no jump needed"), flush=True)
    audio.title("starting up")
    if PAD.enabled:
        print(PAD.card(), flush=True)
    def pressed(name):
        now_down = down(name)
        hit = now_down and not was.get(name, False)
        was[name] = now_down if FG[0] else bool(key(VK[name]) & 0x8000)
        return hit
    next_beat, next_check = 0.0, 0.0
    speed_key_t, speed_before = {}, SPEED
    pip_due = None
    burner = False
    burner_on_t = -9.0
    burn_was = False
    burning = False
    ab_fuel, ab_locked, ab_last = 1.0, False, -9.0
    sonic_t = -99.0
    sonic_k = 1.0
    boom = SonicBlast()
    caps_phys = PhysicalKey(VK[SONIC_KEY])
    def caps_key_down(now_):
        if not FG[0]:
            return False
        kb_ = caps_phys.down(now_) if caps_phys.ok(now_) else kbdown(SONIC_KEY)
        return bool(kb_) or SONIC_KEY in PAD.keys
    sonic_carry = False
    brake_t, brake_tap = -9.0, -9.0
    sonic = 0.0
    cruise = False
    cruise_lvl = 0.0
    throttle = 0.0
    thr_lock = None
    reversing = False
    shock_seq, shock_k = 0, 1.0
    brake_fx_t = -9.0
    lvl_lock = None
    fin_ = 0.0
    cruise_prev = False
    ip_charge = ip_hum = False
    ip_caps_t = -9.0
    ip_auto = None
    ip_raise_ok = False
    ip_duck_t = None
    ip_growl = False
    ip_hum_rate_now, ip_pitch_t = 1.0, -9.0
    cruise_spd, cruise_end, cruise_out = 0.0, -CRUISE_COOLDOWN, None
    cruise_fx = 0.0
    cruise_h = None
    cruise_t0 = -9.0
    dock = None
    force_toggle = False
    ctl_next = sts_next = 0.0
    pub_slow_t, mods_off_, pmode_ = 0.0, False, None
    ctl_pending, ctl_track_stop = [], []
    settings_gen, raise_req, panel_launch_t, sts_err = 0, 0, -9.0, False
    loop_n_, loop_t0_ = 0, time.perf_counter()
    dock_check = 0.0
    pull = None
    pull_out_check = 0.0
    st_check = 0.0
    fr_hop_until = 0.0
    hud_start()
    warpfx_start()
    dive = False
    water = False
    jet_relight = None
    cruise_seen = False
    stale_now, verify_t = False, 0.0
    water_stale_quiet = 0.0
    water_last = -9.0
    water_seen, water_pos = -9.0, None
    surf_pt, surf_t, raw_w_prev = None, -9.0, None
    skim_ok, skimming = True, False
    verify = None
    verify_miss = 0
    import waterhold
    depth_hold = waterhold.DepthHold()
    hold_pos = None
    jet_repress = None
    idle_since = None
    q_hands_until = 0.0
    g_skip_t = 0.0
    wheel_orig = None
    on_t = -9.0
    unfocused_since = None
    suspended = False
    stalled_was = False
    space_ok_t = 0.0
    end_since, end_told = None, False
    fuel_seen, fuel_dry, fuel_tries = False, 0, 0
    route_seen, route_said = "kb", -99.0
    resume_t = None
    menu_up = False
    fg_since = 0.0
    crawl = CrawlWatch()
    stalled = False
    shoulder = ShoulderCam()
    if shoulder.ok():
        if lookcam.apply(pm, shoulder.base, shoulder.side):
            print("look-up camera: kept back", flush=True)
        animswap.start(pm)
        speedfx._fx.punch_on = bool(SET.camera["speed_effects"])
        if not SET.camera["speed_effects"] and not hasattr(speedfx, "set_effects"):
            print("speed effects off (settings.ini)", flush=True)
        elif speedfx.start(pm, shoulder.base):
            apply_fx_settings(SET)
            print("speed effects ready (dive / afterburner: camera eases back, wider view, motion blur)"
                  if SET.camera["speed_effects"] else "speed effects off (settings)", flush=True)
        if lookcam.center_delay(pm, shoulder.base, CAM_CENTER_DELAY):
            print(f"camera holds your aim {CAM_CENTER_DELAY:g} s before re-centering", flush=True)
    else:
        print("camera settings not found for this game version: no look-up camera or speed effects", flush=True)
    swim_anims.start(pm)
    if not water_speed.start(pm):
        print("underwater speed limit not found: underwater stays at 19 m/s", flush=True)
    pad_keymap = dict(forward="W", back="S", left="A", right="D", climb=CLIMB, descend=DESCEND,
                      afterburner="SHIFT", faster="PGUP", slower="PGDN", quit="END",
                      sonic_boom=SONIC_KEY, hard_brake="BRAKE")
    game_check = 0.0
    while not _QUIT[0]:
        now = time.perf_counter()
        if now >= game_check:
            game_check = now + 1.0
            code_ = ctypes.c_ulong(0)
            if (ctypes.windll.kernel32.GetExitCodeProcess(ctypes.c_void_p(pm.process_handle), ctypes.byref(code_))
                    and code_.value != 259):
                keys.release_all()
                print("the game closed: flight script stopping", flush=True)
                return
        fg = keys.focused()
        if fg != FG[0]:
            FG[0] = fg
            taps.reset()
            if fg:
                fg_since = now
                space_ok_t = max(space_ok_t, now + 0.1)
                if suspended:
                    suspended = False
                    if on:
                        status("resumed (game focused again)")
        if down("END"):
            end_since = end_since or now
            if now - end_since >= 1.0:
                if on:
                    sfx("flight_off")
                try:
                    CTRL.publish(phase=2)
                except Exception:
                    pass
                break
        else:
            if end_since is not None:
                status("hold End for 1 s to quit the flight script")
            end_since = None
        if now >= ctl_next:
            ctl_next = now + 0.02
            ctl_pending.extend(CTRL.poll(now))
        ctl_quit = None
        for c_ in list(ctl_pending):
            if ((c_["name"] in FOCUS_CMDS or c_["flags"] & _control.F_WAIT_FOCUS)
                    and not (fg and now - fg_since >= 0.4 and not stalled and not menu_up)):
                if now - c_["issued"] > c_["ttl"]:
                    CTRL.ack(c_["seq"], _control.EXPIRED, 0, "the game never came to the front")
                    ctl_pending.remove(c_)
                elif not c_.get("waiting"):
                    c_["waiting"] = True
                    CTRL.ack(c_["seq"], 2, 0, "waiting for the game window")
                continue
            ctl_pending.remove(c_)
            nm_, a_ = c_["name"], c_["a"]
            res_ = (_control.DONE, 0, "")
            try:
                if nm_ == "ping":
                    res_ = (_control.DONE, 0, "pong")
                elif nm_ == "reload":
                    new_ = _settings.load(quiet=True)
                    if getattr(new_, "unreadable", False):
                        CTRL.ack(c_["seq"], _control.FAILED, 0, "settings.ini was busy: try again")
                        continue
                    diff_ = _settings_diff(SET, new_)
                    SET = new_
                    apply_settings(SET)
                    settings_gen += 1
                    try:
                        PAD.cfg = xpad.load_pad_settings()
                        xpad.STICK_DEAD_L, xpad.TRIGGER_DEAD = PAD.cfg["stick_deadzone"], PAD.cfg["trigger_deadzone"]
                    except Exception:
                        pass
                    rebuild_keymap(SET)
                    taps.window = SET.flight["double_tap_window"] + 0.05
                    apply_fx_settings(SET)
                    restart_only_ = set(RESTART_ONLY)
                    if hasattr(speedfx, "set_effects") and hasattr(speedfx, "set_blur"):
                        restart_only_ -= {("camera", "speed_effects"), ("camera", "motion_blur")}
                    if ("sound", "sound_volume") in diff_:
                        if hasattr(audio, "set_volume"):
                            audio.set_volume(SET.sound["sound_volume"])
                        else:
                            restart_only_.add(("sound", "sound_volume"))
                    later_ = sorted(f"{s_}.{k_}" for s_, k_ in diff_ & restart_only_)
                    if ("effects", "warp_effects") in diff_:
                        try:
                            if _warpfx_proc[0] is not None:
                                keys._OURS.discard(_warpfx_proc[0].pid)
                                _warpfx_proc[0].terminate()
                        except Exception:
                            pass
                        warpfx_start()
                    print(f"settings reloaded from Suit Control ({len(diff_)} changed)", flush=True)
                    res_ = (_control.DONE, len(later_), ("restart for: " + ", ".join(later_))[:47] if later_
                            else f"{len(diff_)} applied")
                elif nm_ == "fly":
                    want_ = a_[0]
                    if want_ < 0 or (want_ > 0) != bool(on):
                        force_toggle = True
                elif nm_ == "quit":
                    ctl_quit = 75 if a_[0] >= 1 else 0
                elif nm_ == "refind":
                    if on:
                        res_ = (_control.REFUSED, 0, "land first")
                    else:
                        refinder.forget()
                        res_ = (_control.DONE, 0, "found") if relocate() else (_control.FAILED, 0, "not found")
                elif nm_ == "reset_fx":
                    speedfx.restore()
                    lookcam.center_delay(pm, shoulder.base, FLY_CENTER_DELAY if on else CAM_CENTER_DELAY)
                elif nm_ == "play_sound":
                    if c_["text"] in ("ip_charge", "ip_hum"):
                        audio.track_play(c_["text"], 0.0, volume=1.0 if c_["text"] == "ip_charge" else IP_HUM_VOLUME)
                        ctl_track_stop.append((now + (a_[1] or 3.0), c_["text"]))
                    else:
                        audio.play(c_["text"])
                elif nm_ == "restart_hud":
                    try:
                        if _hud_proc[0] is not None:
                            keys._OURS.discard(_hud_proc[0].pid)
                            _hud_proc[0].terminate()
                    except Exception:
                        pass
                    hud_start()
                elif nm_ == "restart_effects":
                    try:
                        if _warpfx_proc[0] is not None:
                            keys._OURS.discard(_warpfx_proc[0].pid)
                            _warpfx_proc[0].terminate()
                    except Exception:
                        pass
                    warpfx_start()
                elif nm_ == "relight":
                    if on:
                        resume_t = now
                        res_ = (_control.DONE, 0, "jets relit")
                    else:
                        res_ = (_control.REFUSED, 0, "not flying")
                elif nm_ == "refill":
                    ab_fuel, ab_locked, boom.meter = 1.0, False, 1.0
                else:
                    res_ = (_control.REFUSED, 0, f"unknown command {c_['cmd']}")
            except Exception as e_:
                res_ = (_control.FAILED, 0, f"{e_.__class__.__name__}: {e_}"[:47])
            if res_ is not None:
                CTRL.ack(c_["seq"], *res_)
        for t_, n_ in list(ctl_track_stop):
            if now >= t_:
                audio.track_stop(n_, 0.5)
                ctl_track_stop.remove((t_, n_))
        if ctl_quit is not None:
            if on:
                sfx("flight_off")
            EXIT_CODE[0] = ctl_quit
            print("quit from Suit Control" + (" (restarting)" if ctl_quit == 75 else ""), flush=True)
            try:
                CTRL.publish(phase=2)
            except Exception:
                pass
            break
        if pressed("PANEL"):
            pid_, alive_, _ = CTRL.panel()
            try:
                hk_ = bool(struct.unpack_from(_control.CTL_BEAT_FMT, CTRL.ctl, _control.CTL_BEAT_OFF)[1] & 4)
            except Exception:
                hk_ = False
            if alive_ and hk_:
                pass
            elif alive_:
                raise_req += 1
            elif now - panel_launch_t > 3.0:
                panel_launch_t = now
                if _start_panel():
                    status("opening Suit Control")
        if now >= sts_next:
            sts_next = now + 0.1
            try:
                fl_ = ((_control.FL["flying"] if on else 0) | (_control.FL["suspended"] if suspended else 0)
                       | (_control.FL["space"] if space else 0) | (_control.FL["water"] if water else 0)
                       | (_control.FL["cruise"] if cruise else 0) | (_control.FL["dive"] if dive else 0)
                       | (_control.FL["burning"] if burning else 0) | (_control.FL["ab_cooling"] if ab_locked else 0)
                       | (_control.FL["reversing"] if reversing else 0) | (_control.FL["focused"] if fg else 0)
                       | (_control.FL["character_ok"] if addresses_ok() else 0)
                       | (_control.FL["right_shoulder"] if shoulder.ok() and shoulder.side > 0 else 0)
                       | (_control.FL["hud_alive"] if _hud_proc[0] is not None and _hud_proc[0].poll() is None else 0)
                       | (_control.FL["pull"] if pull is not None else 0)
                       | (_control.FL["ship_arms"] if ship_arms else 0)
                       | (_control.FL.get("menu_up", 0) if menu_up else 0))
                try:
                    import locate as locate_p
                    if locate_p.ON_DECK:
                        fl_ |= _control.FL.get("on_deck", 0)
                except Exception:
                    pass
                if now >= pub_slow_t:
                    pub_slow_t = now + 5.0
                    try:
                        import modsguard
                        mods_off_ = bool(modsguard.disabled())
                    except Exception:
                        mods_off_ = False
                    try:
                        pmode_ = charstate.player_mode()
                    except Exception:
                        pmode_ = None
                fl2_ = ((_control.FL2.get("mods_disabled", 0) if mods_off_ else 0)
                        | (_control.FL2.get("no_shoulder", 0) if not shoulder.ok() else 0)
                        | (_control.FL2.get("speedfx_refused", 0) if not getattr(speedfx._fx, "ok", True) else 0))
                gt_ = struct.unpack_from("<d", _GAME, 0)[0]
                if gt_ > 0.0 and now - gt_ < 0.5:
                    fl_ |= _control.FL["mod_live"]
                loop_hz_ = loop_n_ / max(1e-3, now - loop_t0_)
                loop_n_, loop_t0_ = 0, now
                CTRL.publish(flags=fl_, startup_stage=startup.state, startup_progress=startup.progress,
                             speed=float(np.linalg.norm(v)) if on else 0.0, throttle=-1.0 if reversing else throttle,
                             cruise_level=cruise_lvl, ab_fuel=ab_fuel, sonic_meter=boom.meter, speed_level=SPEED,
                             min_speed=MIN_SPEED, max_speed=MAX_SPEED, height=-1.0, loop_hz=loop_hz_,
                             mod_age=(now - gt_) if gt_ > 0.0 else -1.0, settings_gen=settings_gen,
                             raise_req=raise_req, flags2=fl2_, player_mode=255 if pmode_ is None else pmode_,
                             settings_warnings=len(getattr(SET, "warnings", []) or []),
                             away_s=(now - unfocused_since) if (on and suspended) else -1.0)
            except Exception as e_:
                if not sts_err:
                    sts_err = True
                    print(f"control status failed ({e_!r})", flush=True)
        loop_n_ += 1
        PAD.forward = bool(on and THROTTLE_MODE and throttle > PAD_FORWARD_THROTTLE)
        PAD.update(now, pad_keymap, fg, flying=on)
        ROUTE.update(now, PAD.last_use, taps.last_key)
        if ROUTE.src != route_seen:
            route_seen = ROUTE.src
            if now - route_said > 10.0:
                route_said = now
                print(f"controls: {'controller' if route_seen == 'pad' else 'keyboard / mouse'} "
                      "(the game's jetpack and weapon keys follow it)", flush=True)
        shoulder.update(now)
        if not on:
            throttle, cruise_lvl, reversing = 0.0, 0.0, False
            ip_auto, ip_raise_ok = None, False
            if ip_charge or ip_hum or ip_growl:
                audio.track_stop("ip_charge", IP_CHARGE_CUT)
                audio.track_stop("ip_hum", IP_HUM_FADE_OUT)
                audio.track_stop("ip_growl", IP_GROWL_FADE_OUT)
                ip_charge = ip_hum = ip_growl = False
        if not on or throttle != 0.0 or any(down(k_) for k_ in ("W", "A", "S", "D", CLIMB, DESCEND)):
            idle_since = None
        elif idle_since is None:
            idle_since = now
        if on:
            on_t = now
        try:
            legs_ = struct.unpack_from("<d", _SHM, SHM_LEGS)[0] if on or now - on_t < 1.0 else 0.0
        except Exception:
            legs_ = 0.0
        kw_, ks_, ka_, kd_ = down("W"), down("S"), down("A"), down("D")
        carried_ = on and THROTTLE_MODE and throttle > 0.0 and not reversing
        quarter_ = carried_ and not space and not water and throttle <= FIRST_Q and fin_ >= 0
        side_ = ka_ != kd_ and not kw_ and (not carried_ or quarter_)
        if quarter_:
            q_hands_until = now + QUARTER_HANDS_HOLD
        animswap.update((idle_since is not None and now - idle_since >= HANDS_IDLE_DELAY) or quarter_
                        or (on and now < q_hands_until),
                        legs_ if math.isfinite(legs_) else 0.0,
                        {"brake": 1.0 if on and ks_ and not (kw_ or ka_ or kd_) else 0.0,
                         "left": 1.0 if on and side_ and ka_ and not ks_ else 0.0,
                         "right": 1.0 if on and side_ and kd_ and not ks_ else 0.0,
                         "brake_left": 1.0 if on and side_ and ka_ and ks_ else 0.0,
                         "brake_right": 1.0 if on and side_ and kd_ and ks_ else 0.0})
        water_speed.update(on)
        swim_anims.update(on and water, (kw_ or carried_) and not quarter_, ks_ or (on and THROTTLE_MODE and reversing),
                          ka_ and side_, kd_ and side_)
        dt, last = min(now - last, 0.05), now
        if not (on and burning) and now - ab_last >= AB_RECHARGE_DELAY and ab_fuel < 1.0:
            ab_fuel = min(1.0, ab_fuel + dt / AB_RECHARGE_TIME)
            if ab_fuel >= 1.0 and ab_locked:
                ab_locked = False
                print("afterburner recharged", flush=True)
        sa = now - sonic_t
        hold_, fade_ = SONIC_HOLD * sonic_k, SONIC_FADE * max(sonic_k, 0.2)
        sonic = 1.0 if sa < hold_ else max(0.0, 1.0 - (sa - hold_) / fade_)
        sonic = sonic_k * sonic * sonic * (3 - 2 * sonic) if on else 0.0
        if not on or space or cruise:
            boom.cancel()
        boom.refill(now, dt)
        if startup.state == refind.SYNC and addresses_ok():
            startup.finish()
        if startup.result is not None and not startup.adopted:
            startup.adopted = True
            if not addresses_ok():
                adopt(*startup.result)
                print("found your character (from your own movement)", flush=True)
        if startup.state == refind.READY and not startup.chimed:
            startup.chimed = True
            sfx("suit_online")
            status("suit online: double-tap Space (or F8) to fly, W / S throttle (it stays where you leave it), "
                   "hold End to quit." if THROTTLE_MODE else
                   f"suit online (speed {SPEED:.0f}): double-tap Space (or F8) to fly, PgUp/PgDn speed, hold End to quit.")
            audio.title("ready")
        if arsenal.state.note != arsenal_note:
            arsenal_note = arsenal.state.note
            print(arsenal_note, flush=True)
        if pressed("ARSENAL"):
            ship_arms = not ship_arms
            status("weapons: " + ("your STARSHIP's (Photon Cannon, Positron, Infraknife, Cyclotron, Rockets, "
                                  "Phase Beam) while flying" if ship_arms else "your multi-tool as it is"),
                   "speed_up" if ship_arms else "speed_down")
        if (on and ship_arms) != arsenal.state.on and arsenal.state.ready:
            arsenal.set_ship(on and ship_arms)
        kl_ = arsenal.state.keep_loaded()
        if not kl_ or getattr(arsenal.state, "clip_sel", None) != reload_sel:
            reload_tries, reload_sel = 0, getattr(arsenal.state, "clip_sel", None)
        firing_ = fire_held()
        if kl_ and firing_ and reload_tries < RELOAD_TRIES and now - reload_tap > 2.0 and FG[0]:
            reload_tap, reload_tries = now, reload_tries + 1
            keys.press("R")
            time.sleep(0.04)
            keys.release("R")
        if arsenal.state.weapon:
            try:
                w_ = arsenal.state.weapon
                n_ = struct.unpack("<i", pm.read_bytes(w_ + WHEEL_N, 4))[0]
                if 0 < n_ <= WHEEL_CAP:
                    lst_ = list(struct.unpack(f"<{n_}i", pm.read_bytes(w_ + WHEEL_LIST, 4 * n_)))
                    if all(0 <= x < 32 for x in lst_):
                        if on:
                            keep_ = [x for x in lst_ if x not in IRONMAN_NO_WEAPONS]
                            if keep_ != lst_ and keep_:
                                wheel_orig = lst_
                                WHEEL_RESTORE[0] = (w_, lst_)
                                pm.write_bytes(w_ + WHEEL_LIST, struct.pack(f"<{n_}i", *(keep_ + [0] * (n_ - len(keep_)))),
                                               4 * n_)
                                pm.write_bytes(w_ + WHEEL_N, struct.pack("<i", len(keep_)), 4)
                        elif wheel_orig and set(lst_) <= set(wheel_orig):
                            o_ = wheel_orig
                            pm.write_bytes(w_ + WHEEL_LIST, struct.pack(f"<{len(o_)}i", *o_), 4 * len(o_))
                            pm.write_bytes(w_ + WHEEL_N, struct.pack("<i", len(o_)), 4)
                            wheel_orig = WHEEL_RESTORE[0] = None
            except Exception:
                pass
        unibeam_sound(now, on and FG[0])
        wrist_sound(now, on and FG[0])
        if on and FG[0] and arsenal.state.weapon and now - g_skip_t > 0.25:
            try:
                sel_ = struct.unpack("<i", pm.read_bytes(arsenal.state.weapon + WEAPON_SEL, 4))[0]
                whl_ = struct.unpack("<i", pm.read_bytes(arsenal.state.weapon + WEAPON_WHEEL, 4))[0]
                if sel_ in IRONMAN_NO_WEAPONS and whl_ != 2:
                    g_skip_t = now
                    keys.press("G")
                    time.sleep(0.03)
                    keys.release("G")
            except Exception:
                pass
        try:
            _ARMS[:struct.calcsize(_ARMS_FMT)] = struct.pack(_ARMS_FMT, time.perf_counter(), arsenal.state.weapon or 0,
                                                              1 if arsenal.state.on else 0, *(0.0,) * 6)
        except Exception:
            pass
        _HUD_BOOT[:] = [startup.state, startup.progress,
                        (now - startup.ready_t) if startup.ready_t is not None else 0.0]
        if not on:
            refinder.poll(now)
            share(False)
            dive = False
            burn_was = burning = False
            speedfx.update(dt, 0.0, 0.0)
            water_cam.update(False)
        hud(on, burning or sonic > 0 or cruise, ab_fuel, ab_locked, boom.meter,
            max(sonic, cruise_fx),
            float(np.linalg.norm(v)) if on else 0.0, shoulder.ok() and shoulder.side > 0,
            on and (now - brake_t < 0.3 or now - brake_fx_t < 0.3),
            cruise_fx > 0.0, -1.0 if boom.build is None else boom.build, -1.0 if reversing else throttle, cruise_lvl,
            shock_seq, shock_k,
            gated=on and THROTTLE_MODE and not (space or cruise) and (reversing or fin_ < 0 or throttle <= SONIC_GATE),
            refused=on and now - boom.refused_t < SONIC_REFUSED_SHOW)
        if on != center_on and shoulder.ok():
            center_on = on
            lookcam.center_delay(pm, shoulder.base, FLY_CENTER_DELAY if on else CAM_CENTER_DELAY)
            try:
                pm.write_float(shoulder.base + SPACE_CAM_CENTER, FLY_CENTER_DELAY if on else SPACE_CAM_CENTER_SHIPPED)
            except Exception:
                pass
        if now >= next_beat:
            next_beat = now + (0.3 if on else 1.0)
            limb_flag(on)
        if on and now >= next_check:
            next_check = now + 0.5
            lost = not addresses_ok()
            if lost:
                on, burner = False, False
                limb_flag(False)
                if JETPACK_POSE:
                    keys.release("SPACE")
                sfx("flight_off")
                if lost:
                    cue("error")
                print("flight OFF (the game rebuilt your character: double-tap Space again)", flush=True)
        for k_, other_, f_ in (("PGUP", "PGDN", 1.2), ("PGDN", "PGUP", 1 / 1.2)):
            if not pressed(k_) or THROTTLE_MODE:
                continue
            old_ = SPEED
            if down(other_) and now - speed_key_t.get(other_, -9.0) < 0.15:
                SPEED = START_SPEED
                pip_due = None
                status(f"speed {SPEED:.0f} (back to the start speed)", "speed_up" if SPEED > speed_before else "speed_down")
            else:
                speed_before = SPEED
                SPEED = min(max(SPEED * f_, MIN_SPEED), MAX_SPEED)
                if abs(SPEED - old_) < 1e-6:
                    status(f"speed {SPEED:.0f} (that's the {'top' if f_ > 1 else 'lowest'} speed: "
                           "max_speed / min_speed in settings.ini)", "speed_limit")
                else:
                    status(f"speed {SPEED:.0f}")
                    pip_due = (now + 0.15, "speed_up" if f_ > 1 else "speed_down")
            speed_key_t[k_] = now
        if pip_due and now >= pip_due[0]:
            cue(pip_due[1])
            pip_due = None
            if SET.flight["remember_speed"] and abs(SPEED - old_) > 1e-6:
                try:
                    c = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
                    c["speed"] = round(SPEED, 2)
                    CONFIG.write_text(json.dumps(c, indent=2))
                except (OSError, ValueError):
                    pass
        if now >= next_sample:
            next_sample = now + 0.01
            try:
                history.append((now, rd(VEL)))
            except Exception:
                pass
        if dock is not None:
            st_ = dock["state"]
            if st_ == "call" and not on:
                keys.press("X")
                dock.update(state="menu", t=now)
            elif st_ == "menu" and now - dock["t"] > 0.1 and not dock.get("up"):
                keys.release("X")
                dock["up"] = True
            elif st_ == "menu" and now - dock["t"] > 0.7:
                n_ = (struct.unpack_from("<I", _NAV, 112)[0] + 1) & 0xFFFFFFFF
                _NAV[112:116] = struct.pack("<I", n_)
                dock.update(state="ack", req=n_, t=now)
            elif st_ == "ack":
                done_, ok_ = struct.unpack("<Ii", _NAV[116:124])
                if done_ == dock["req"]:
                    if ok_:
                        dock.update(state="docking", t=now, last=None, still=0)
                    else:
                        keys.press("X"); time.sleep(0.08); keys.release("X")
                        status("couldn't call your starship to dock you", "error")
                        dock, force_toggle = None, True
                elif now - dock["t"] > 3.0:
                    status("the in-game half didn't answer: no docking", "error")
                    dock, force_toggle = None, True
            elif st_ == "docking" and now - dock["t"] > 1.0:
                if now >= dock.get("next", 0.0):
                    dock["next"] = now + 0.5
                    try:
                        p_ = rd(player + 0x360) if player else None
                    except Exception:
                        p_ = None
                    inside = charstate.player_mode() == 4 or in_anomaly(p_)
                    if inside and dock.get("in_t") is None:
                        dock["in_t"] = now
                    if inside and p_ is not None and dock["last"] is not None \
                            and float(np.linalg.norm(p_ - dock["last"])) < 0.08:
                        dock["still"] += 1
                    else:
                        dock["still"] = 0
                    dock["last"] = p_
                    if dock["still"] >= 6 and now - dock["in_t"] >= 6.0:
                        keys.press("E")
                        dock.update(state="exit", t=now, tries=dock.get("tries", 0) + 1)
                if dock["state"] == "docking" and now - dock["t"] > DOCK_TIMEOUT:
                    status("the docking didn't finish: you're in your starship", "error")
                    dock = None
            elif st_ == "exit" and now - dock["t"] > 1.4:
                keys.release("E")
                dock.update(state="out", t=now)
            elif st_ == "out":
                if charstate.player_mode() == 4 and now - dock["t"] > 1.5:
                    dock, force_toggle = None, True
                    print("inside the Space Anomaly: Iron Man mode back on", flush=True)
                elif now - dock["t"] > 4.0:
                    if dock["tries"] < 3:
                        keys.press("E")
                        dock.update(state="exit", t=now, tries=dock["tries"] + 1)
                    else:
                        status("inside the Space Anomaly, but still in your starship: hold E to get out", "error")
                        dock = None
        f8 = pressed("F8")
        tapped = taps.fired() and fg
        if dock is not None:
            f8 = tapped = False
        f8 = f8 or force_toggle
        force_toggle = False
        if not SET.keys["double_tap_space"]:
            tapped = False
        if VK["ARM"] != 0x07:
            if VK["ARM"] == 0x91:
                now_armed = bool(ctypes.windll.user32.GetKeyState(0x91) & 1)
            else:
                now_armed = (not armed) if pressed("ARM") else armed
            if now_armed != armed:
                armed = now_armed
                status("take-off " + ("ARMED: double-tap Space to fly" if armed else
                                      "disarmed: double-tap Space won't lift you off")
                       + (" (once you've landed)" if on and not armed else ""), "ready" if armed else "speed_down")
        pad_tap = PAD.take_tap()
        if pad_tap and not tapped and dock is None:
            taps.tap_gap, tapped = pad_tap, True
        if f8 or tapped:
            if not on and refinder.cands and not addresses_ok():
                m_ = refinder.match()
                if m_:
                    adopt(*m_)
                    print("found your character again", flush=True)
                refinder.forget()
            if on:
                on, burner = False, False
                limb_flag(False)
                if JETPACK_POSE:
                    keys.release("SPACE")
                sfx("flight_off")
                print("flight OFF", flush=True)
                pull = None
            elif not armed:
                status(f"take-off is disarmed: press {_settings.key_name(VK['ARM'])} to arm it", "error")
            elif charstate.blocked(states, my_state):
                status("can't fly from here: " + ("you're in a vehicle, get out first"
                                                 if charstate.blocked(states, my_state) == "vehicle"
                                                 else "you're in water, get out first"), "error")
            elif not addresses_ok() and charstate.wait_blocked(states, 3.0):
                status("can't fly from here: you're in a vehicle, get out first", "error")
            elif startup.state == refind.SCAN and not addresses_ok():
                status("the suit is still starting up: one moment (the bar on the HUD shows it)", "error")
            elif not character_ok():
                refinder.forget()
                import locate as locate_
                if locate_.ON_DECK:
                    status(DECK_MSG, "error")
                else:
                    status("couldn't find your character: land, let go of every key, stand still for a second, "
                           "then double-tap Space again (it jumps once to find you)", "error")
            elif charstate.in_space(states):
                f_, r_, u_ = cam_axes()
                up = u_ if u_ is not None else (game_up() if game_up() is not None else np.array([0.0, 0.0, 1.0]))
                space, sp_axes, space_since = True, (f_, r_, u_), time.perf_counter()
                try:
                    v = rd(VEL)
                except Exception:
                    v = np.zeros(3)
                if not np.isfinite(v).all():
                    v = np.zeros(3)
                on, grounded_since = True, None
                steer = Steer(up, pitch_steers=CAMERA_PITCH_STEERS)
                on_since = time.perf_counter()
                verify, hold_pos = None, None
                suspended, fuel_dry, fuel_tries, resume_t, fuel_seen = False, 0, 0, None, False
                limb_flag(True)
                time.sleep(0.03)
                if JETPACK_POSE:
                    keys.press("SPACE")
                sfx("flight_on")
                print("flight ON  (SPACE: 6-axis, you drift -- double-tap S to stop)", flush=True)
            else:
                space = False
                up = game_up()
                if up is None and tapped and taps.tap_gap:
                    r, p = taps.tap_gap
                    up = up_between(r + 0.03, p - 0.01)
                if up is None and not tapped:
                    up = learn_up()
                    if up is None:
                        up = hop_up()
                if up is None:
                    up = last_up if last_up is not None else (unit(SAVED_UP) if SAVED_UP is not None else None)
                if up is None:
                    status("couldn't feel gravity: jump first, let go of all keys, then press F8", "error")
                else:
                    last_up = up
                    on, v, grounded_since = True, up * 6.0, None
                    if charstate.in_water(states):
                        v = np.zeros(3)
                    steer = Steer(up, pitch_steers=CAMERA_PITCH_STEERS)
                    on_since = time.perf_counter()
                    suspended, fuel_dry, fuel_tries, resume_t = False, 0, 0, None
                    fuel_seen = False
                    verify, verify_t, verify_miss = [], on_since, 0
                    hold_pos = None
                    limb_flag(True)
                    time.sleep(0.03)
                    if JETPACK_POSE:
                        keys.press("SPACE")
                    comp_ = game_component()
                    if comp_ and charstate.read(comp_ + charstate.OFFSET) is not None:
                        my_state = comp_ + charstate.OFFSET
                    elif my_state is None or charstate.read(my_state) is None:
                        my_state = charstate.pick_airborne(states)
                    if my_state is None:
                        my_state = own_slot()
                    sfx("flight_on")
                    charstate.calibrate()
                    if SET.debug["verbose"]:
                        print(f"flight ON  (up = {up[0]:.2f} {up[1]:.2f} {up[2]:.2f}, "
                              f"auto-landing {'on' if my_state else 'off: state not found'}, "
                              f"player state {charstate.player_mode()})", flush=True)   
                    else:
                        print("flight ON" + ("" if my_state else "  (auto-landing off this time: land with F,"
                                             " then double-tap Space to stop)"), flush=True)
            last = time.perf_counter()
        stalled = game_stalled(now)
        if crawl.step(now, fg, menu_up):
            status("the game was stuck at a crawl after a window change: woke it (minimized and restored it)", "error")
        if stalled != stalled_was:
            stalled_was = stalled
            if not stalled:
                resume_t = now + 0.6
        if on:
            if not fg and not suspended:
                suspended, unfocused_since, burner = True, now, False
                if JETPACK_POSE:
                    keys.release("SPACE")
                status("paused (game not focused): hovering until you come back")
            if (JETPACK_POSE and fg and now >= space_ok_t and not taps.physically_down
                    and not bool(key(VK["SPACE"]) & 0x8000) and not jet_repress):
                keys.press("SPACE")
            burn_t, menu_t = jet_signals()
            if menu_t > 0.0 and now - menu_t < 0.25:
                menu_up = True
            elif menu_up and now - menu_t > 0.4:
                menu_up = False
                resume_t = now + 0.3
            if resume_t is not None and now >= resume_t and now - on_since > 1.0:
                resume_t = None
                if JETPACK_POSE and fg:
                    keys.release("SPACE")
                    space_ok_t = now + 0.12
                    print("back from a pause: pressing Space for the game's jetpack again", flush=True)
            if tank and now >= next_fill:
                next_fill = now + 0.25
                try:
                    if burn_t > 0.0:
                        draining = now - burn_t < 0.5
                    else:
                        draining = jetfuel.read(tank) < tank_full - 0.02
                    if draining:
                        fuel_seen, fuel_dry, fuel_tries = True, 0, 0
                    elif JETPACK_POSE and fg and not stalled and not space and not menu_up \
                            and (fuel_seen or fuel_tries < 2) \
                            and now - on_since > 1.0 \
                            and now - ROUTE.switch_t > 1.8 \
                            and now >= space_ok_t:
                        fuel_dry += 1
                        if fuel_dry >= (3 if fuel_tries < 4 else 12):
                            fuel_dry, fuel_tries = 0, fuel_tries + 1
                            keys.release("SPACE")
                            space_ok_t = now + 0.1
                            if fuel_tries <= 1:
                                print("the game's jetpack had stopped: pressing Space for it again", flush=True)
                    if jetfuel.read(tank) < tank_full - 1.0:
                        jetfuel.fill(tank, tank_full)
                except Exception:
                    tank = None
            actual = rd(VEL)
            if cruise_seen and not cruise and JETPACK_POSE and on:
                jet_relight = now + WATER_RELIGHT[0]
                print("re-lighting the jetpack after the cruise (its sound)", flush=True)
            cruise_seen = cruise
            if jet_relight and now >= jet_relight and JETPACK_POSE and fg:
                jet_relight, jet_repress = None, now + WATER_RELIGHT[1]
                keys.release("SPACE")
            if jet_repress and now >= jet_repress and fg:
                jet_repress = None
                if on and JETPACK_POSE:
                    keys.press("SPACE")
            if relight and fg:
                relight = False
                if JETPACK_POSE:
                    keys.release("SPACE")
                    time.sleep(0.06)
                    keys.press("SPACE")
            if CROSS_ROWS_HOLD and player and BASE is not None:
                try:
                    if xhold is None and space:
                        sr_ = [(charstate.read(a_), charstate.alive(a_)) for a_ in list(states)]
                        if any(s_ == charstate.SPACE and al_ for s_, al_ in sr_):
                            xrows = pm.read_bytes(player + PLAYER_ORIENT, 32)
                        elif xrows is not None and any(s_ in (charstate.ATMO, charstate.AIR) and al_ for s_, al_ in sr_):
                            U_ = unit(rd(player + PLAYER_ORIENT))
                            if float(np.dot(U_, unit(np.array(struct.unpack("<3f", xrows[:12]))))) < math.cos(math.radians(2.0)):
                                f_, r_, u_ = cam_axes()
                                if f_ is not None:
                                    mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                                    h_ = flat(f_ + u_ * abs(float(np.dot(f_, U_))), U_)
                                    p0_ = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(f_, U_))))))
                                    xhold = [now, {o_: pm.read_bytes(mgr_ + o_, 8) for o_ in CAM_ANGLES}, U_, (f_, u_, h_, p0_),
                                             0.0, 0, None, None, None]
                                    XG[0], XG[1] = U_, now + CROSS_ROWS_MAX + CROSS_UP_KEEP
                                    print(f"coming down: keeping your view through the hand-over (pitch {p0_:+.0f})", flush=True)
                    elif xhold is not None:
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        back_ = space and any(charstate.read(a_) == charstate.SPACE and charstate.alive(a_)
                                              for a_ in list(states))
                        G_, (f0_, u0_, h0_, p0_) = xhold[2], xhold[3]
                        bU_ = unit(rd(player + 0x320))
                        bA_ = unit(rd(player + 0x330))
                        lev_ = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(bU_, G_))))))
                        if back_:
                            for o_, b_ in xhold[1].items():
                                pm.write_bytes(mgr_ + o_, b_, 8)
                            print("coming down: only a blip, still in space", flush=True)
                            xhold, XG[0] = None, None
                        else:
                            lo_ = -(CAM_PLANET_LIMIT - 2.0)
                            pt_ = max(p0_, min(lo_, p0_ + CROSS_PITCH_EASE * (now - xhold[0])))
                            L_ = (unit(h0_ * math.cos(math.radians(pt_)) + G_ * math.sin(math.radians(pt_)))
                                  if h0_ is not None else f0_)
                            bR_ = unit(np.cross(bU_, bA_))
                            yp_of = lambda v: (math.degrees(math.atan2(-float(np.dot(v, bR_)), -float(np.dot(v, bA_)))),
                                               math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(v, bU_)))))))
                            y_, p_ = yp_of(L_)
                            if xhold[7] is not None and now - xhold[7][0] > 1e-3:
                                k_ = CROSS_LEAD / (now - xhold[7][0])
                                dy_ = (y_ - xhold[7][1] + 180.0) % 360.0 - 180.0
                                y_c, p_c = y_ + dy_ * min(k_, 8.0), p_ + (p_ - xhold[7][2]) * min(k_, 8.0)
                            else:
                                y_c, p_c = y_, p_
                            xhold[7] = (now, y_, p_)
                            rF_ = flat(-rd(player + PLAYER_ORIENT + 0x10), bU_)
                            Lh_ = flat(L_, bU_)
                            yP_ = (math.degrees(math.atan2(float(np.dot(np.cross(rF_, Lh_), bU_)), float(np.dot(rF_, Lh_))))
                                   if rF_ is not None and Lh_ is not None else None)
                            pP_ = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(L_, bU_))))))
                            if yP_ is not None:
                                if xhold[8] is not None and now - xhold[8][0] > 1e-3:
                                    k2_ = min(CROSS_LEAD / (now - xhold[8][0]), 8.0)
                                    yPc_ = yP_ + ((yP_ - xhold[8][1] + 180.0) % 360.0 - 180.0) * k2_
                                    pPc_ = pP_ + (pP_ - xhold[8][2]) * k2_
                                else:
                                    yPc_, pPc_ = yP_, pP_
                                xhold[8] = (now, yP_, pP_)
                                yP_, pP_ = (yPc_ + 180.0) % 360.0 - 180.0, max(-85.0, min(85.0, pPc_))
                            live_ = struct.unpack("<f", pm.read_bytes(mgr_ + CAM_ANGLES[0], 4))[0]
                            if (lev_ < CROSS_LEVEL_DONE and now - xhold[0] > CROSS_MIN_HOLD)                                     or (not CROSS_IN_GAME and xhold[6] is not None
                                        and abs((live_ - xhold[6] + 180.0) % 360.0 - 180.0) > 8.0)                                     or now - xhold[0] > CROSS_ROWS_MAX:
                                print(f"hand-over: the planet camera took over after {now - xhold[0]:.2f} s ({xhold[5]} "
                                      f"writes, body {lev_:.1f} deg off the planet's up, its yaw {live_:+.0f})", flush=True)
                                XG[1] = now + CROSS_UP_KEEP
                                xhold = None
                            elif not CROSS_IN_GAME:
                                yp_ = struct.pack("<2f", y_c, max(-85.0, min(85.0, p_c)))
                                for off_ in HANDOFF_PAIRS:
                                    pm.write_bytes(mgr_ + off_, yp_, 8)
                                if yP_ is not None:
                                    pm.write_bytes(mgr_ + CAM_ANGLES[0], struct.pack("<2f", yP_, pP_), 8)
                                    pm.write_bytes(mgr_ + CAM_ANGLES[1], struct.pack("<2f", yP_, pP_), 8)
                                    xhold[6] = yP_
                                xhold[5] += 1
                except Exception as e_:
                    if now >= zone_dbg_t:
                        zone_dbg_t = now + 0.5
                        print(f"crossing hold failed: {e_!r}", flush=True)
            if now >= next_zone and player:
                next_zone = now + 0.05
                if my_state is None or my_state not in states:
                    my_state = charstate.pick_airborne(list(states))
                if not any(charstate.alive(a) for a in list(states)):
                    s_ = own_slot()
                    if s_:
                        states[:] = [s_]
                        my_state = s_
                blind_ = not any(charstate.alive(a) for a in list(states))
                if space:
                    rs_ = [(charstate.read(a), charstate.alive(a)) for a in list(states)]
                    if not any(r_[0] == charstate.SPACE and r_[1] for r_ in rs_) and now >= zone_dbg_t:
                        zone_dbg_t = now + 0.2
                        print(f"ZONE blip in space: slots={rs_} blind={blind_}", flush=True)
                atmo_ = charstate.any_reads(states, charstate.ATMO)
                raw_w_ = charstate.in_water(states)
                if raw_w_:
                    water_seen = now
                    try:
                        water_pos = rd(player + 0x360)
                    except Exception:
                        pass
                try:
                    pos_w_ = rd(player + 0x360)
                except Exception:
                    pos_w_ = None
                if raw_w_prev is not None and raw_w_ != raw_w_prev and pos_w_ is not None:
                    surf_pt, surf_t = surf_update(surf_pt, surf_t, pos_w_, now, up)
                    skim_ok = True
                raw_w_prev = raw_w_
                water_ = water_flag(raw_w_, water, now, water_seen, pos_w_, water_pos, up)
                if water_ != water:
                    water = water_
                    jet_relight = None if water else now + WATER_RELIGHT[0]
                    print("into the water: underwater flight" if water else "out of the water", flush=True)
                    if not water and on and not space:
                        verify, verify_t = [], now
                spc_ = not atmo_ and charstate.any_reads(states, charstate.SPACE)
                planet_ = atmo_ or (not spc_ and any(charstate.read(a) in (charstate.AIR, *charstate.GROUND)
                                                     and charstate.alive(a) for a in list(states)))
                if blind_ and BASE is not None:
                    try:
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        lim_ = struct.unpack("<f", pm.read_bytes(mgr_ + CAM_PITCH_LIMIT, 4))[0]
                        spc_, planet_ = abs(lim_ - 85.0) < 1.0, abs(lim_ - 60.0) < 1.0
                    except Exception:
                        pass
                if not space:
                    handoff_orig = None
                elif SET_HANDOFF_IN_SPACE and BASE is not None:
                    try:
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        if planet_ and handoff_orig is None:
                            handoff_orig = (now, [pm.read_bytes(mgr_ + o_, 8) for o_ in HANDOFF_PAIRS])
                            f5, r5, u5 = cam_axes()
                            if f5 is not None and not CROSS_ROWS_HOLD:
                                freeze = (now, f5, u5)
                                print("coming down: holding the view", flush=True)
                                freeze_cmd = freeze_fh = freeze_look = freeze_face = level_rows = None
                        elif not planet_ and handoff_orig is not None and now - handoff_orig[0] > PLANET_HOLD + 0.3:
                            for o_, b_ in zip(HANDOFF_PAIRS, handoff_orig[1]):
                                pm.write_bytes(mgr_ + o_, b_, 8)
                            handoff_orig, freeze = None, None
                    except Exception:
                        pass
                zone_t = (zone_t[0] if zone_t[1] == (planet_, spc_) else now, (planet_, spc_))
                held_ = now - zone_t[0] >= (PLANET_HOLD if planet_ and space else 0.25)
                if planet_:
                    if atmo_:
                        try:
                            pm.write_bytes(player + PLAYER_SKYDIVE, b"\x00", 1)
                        except Exception:
                            pass
                    if space and held_:
                        settle_up = now + 1.5
                        space, roll_v = False, 0.0
                        fix_cam = (now, now + 2.5) if ENTRY_CAM_FIX else (0.0, 0.0)
                        cam_angles_until, cam_pitch_in = now + 2.0, None
                        gu_ = game_up()
                        f_, r_, u_ = cam_axes()
                        if gu_ is not None and f_ is not None:
                            steer = Steer(gu_, pitch_steers=CAMERA_PITCH_STEERS)
                            h_ = flat(f_ + u_ * abs(float(np.dot(f_, gu_))), gu_)
                            if h_ is not None:
                                steer.head, steer.head_known = h_, True
                                try:
                                    if freeze is None and xhold is None:
                                        pm.write_bytes(player + PLAYER_ORIENT, struct.pack("<3f", *gu_), 12)
                                        pm.write_bytes(player + PLAYER_ORIENT + 0x10, struct.pack("<3f", *(-h_)), 12)
                                    if freeze is not None:
                                        freeze_face = -h_
                                    elif xhold is None:
                                        pm.write_bytes(player + 0x3480, struct.pack("<3f", *(-h_)), 12)
                                except Exception:
                                    pass
                            up = last_up = gu_
                        relight = True
                        print("entered the atmosphere: planet flight", flush=True)
                elif not space and spc_ and held_:
                    space, sp_axes, space_since = True, cam_axes(), now
                    space_cam = (now + SPACE_CAM_HOLD, planet_pitch)
                    relight = True
                    print("left the atmosphere: SPACE 6-axis flight", flush=True)
            if not space and BASE is not None and viewdir is not None:
                gu4 = game_up()
                ax4 = viewdir.cam_axes(pm, BASE)
                if gu4 is not None:
                    last_up = gu4
                if gu4 is not None and ax4 is not None:
                    planet_pitch = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(np.array(ax4[2]), gu4))))))
            if not space and now < settle_up:
                gu = game_up()
                if gu is not None:
                    up = last_up = gu
                    steer.set_up(up)
            if not space and fix_cam[0] <= now < fix_cam[1] and entry_aim is not None and now >= next_fix:
                next_fix = now + 0.03
                try:
                    mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                    planet_cam = abs(struct.unpack("<f", pm.read_bytes(mgr_ + CAM_PITCH_LIMIT, 4))[0] - 60.0) < 1.0
                except Exception:
                    planet_cam = True
                if not planet_cam and now - fix_cam[0] < 1.5:
                    ax_ = None
                else:
                    next_fix = now + 0.45
                    ax_ = viewdir.cam_axes(pm, BASE) if viewdir is not None and BASE is not None else None
                gu2 = game_up()
                hh2 = flat(entry_aim[0], gu2) if gu2 is not None else None
                if ax_ is not None and hh2 is not None:
                    r2, u2, l2 = (np.array(x, dtype=np.float64) for x in ax_)
                    pc = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(l2, gu2))))))
                    hc = flat(l2 - u2 * float(np.dot(l2, gu2)), gu2)
                    if hc is not None:
                        yl = math.degrees(math.atan2(float(np.dot(np.cross(hc, hh2), gu2)), float(np.dot(hc, hh2))))
                        dp = pc - entry_aim[1]
                        if abs(yl) < 4.0 and abs(dp) < 4.0:
                            fix_cam = (0.0, 0.0)
                        else:
                            pxd = cfg.get("mouse_px_per_deg", [2.0, 6.9])
                            keys.mouse_move(int(round(-yl * pxd[0])), int(round(dp * pxd[1])))
            if freeze is not None and now - freeze[0] > CROSS_FREEZE:
                freeze = None
                if freeze_face is not None and player:
                    try:
                        pm.write_bytes(player + 0x3480, struct.pack("<3f", *freeze_face), 12)
                    except Exception:
                        pass
                    freeze_face = None
            if freeze is not None and now >= freeze_next and player and BASE is not None:
                freeze_next = now + 0.004
                try:
                    U5, B5 = unit(rd(player + PLAYER_ORIENT)), rd(player + PLAYER_ORIENT + 0x10)
                    if LEVEL_SLOW and level_rows is not None:
                        t5, Up5, Bp5 = level_rows
                        a5 = math.acos(max(-1.0, min(1.0, float(np.dot(Up5, U5)))))
                        lim5 = LEVEL_RATE * max(0.0, now - t5)
                        if a5 > lim5 + 1e-4:
                            ax5 = np.cross(Up5, U5)
                            n5 = float(np.linalg.norm(ax5))
                            if n5 > 1e-6:
                                ax5 /= n5
                                c5, s5 = math.cos(lim5), math.sin(lim5)
                                rt5 = lambda r: r * c5 + np.cross(ax5, r) * s5 + ax5 * np.dot(ax5, r) * (1 - c5)
                                U5, B5 = rt5(Up5), rt5(Bp5)
                                pm.write_bytes(player + PLAYER_ORIENT, struct.pack("<3f", *U5), 12)
                                pm.write_bytes(player + PLAYER_ORIENT + 0x10, struct.pack("<3f", *B5), 12)
                    level_rows = (now, U5, B5)
                    gu4 = game_up()
                    f4, r4, u4 = cam_axes()
                    if gu4 is not None and f4 is not None:
                        L0, U0 = freeze[1], freeze[2]
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        lim4 = struct.unpack("<f", pm.read_bytes(mgr_ + CAM_PITCH_LIMIT, 4))[0] - 1.0
                        th4 = flat(L0 + U0 * abs(float(np.dot(L0, gu4))), gu4)
                        ch4 = flat(f4 + u4 * abs(float(np.dot(f4, gu4))), gu4)
                        if CROSS_HOLD_PLANET_ONLY and lim4 >= CROSS_PLANET_LIM:
                            freeze_cmd = freeze_look = freeze_fh = None
                        elif th4 is not None and ch4 is not None and 30.0 < lim4 < 89.0:
                            asn = lambda x: math.degrees(math.asin(max(-1.0, min(1.0, x))))
                            cl4 = min(lim4, max(CAM_PLANET_LIMIT - 1.0, 84.0 - 50.0 * (now - freeze[0])))
                            tp4 = max(-cl4, min(cl4, asn(float(np.dot(L0, gu4)))))
                            sg4 = lambda a, b: math.degrees(math.atan2(float(np.dot(np.cross(a, b), gu4)), float(np.dot(a, b))))
                            if freeze_cmd is None:
                                freeze_cmd = list(struct.unpack("<2f", pm.read_bytes(mgr_ + CAM_ANGLES[0], 8)))
                            if freeze_face is not None:
                                cf4, tf4 = flat(rd(player + 0x3480), gu4), flat(freeze_face, gu4)
                                if cf4 is not None and tf4 is not None:
                                    a4 = sg4(cf4, tf4)
                                    if abs(a4) <= 1.2:
                                        nf4, freeze_face = tf4, None
                                    else:
                                        st4 = math.radians(math.copysign(1.2, a4))
                                        nf4 = cf4 * math.cos(st4) + np.cross(gu4, cf4) * math.sin(st4)
                                    pm.write_bytes(player + 0x3480, struct.pack("<3f", *nf4), 12)
                            fh4 = flat(-rd(player + 0x3480), gu4)
                            if fh4 is not None and freeze_fh is not None:
                                fp4 = flat(freeze_fh, gu4)
                                if fp4 is not None:
                                    freeze_cmd[0] -= sg4(fp4, fh4)
                            freeze_fh = fh4
                            if freeze_look is None or not np.array_equal(f4, freeze_look):
                                freeze_look = f4
                                freeze_cmd[0] += 0.5 * sg4(ch4, th4)
                                freeze_cmd[1] += 0.5 * (tp4 - asn(float(np.dot(f4, gu4))))
                            freeze_cmd[0] = (freeze_cmd[0] + 180.0) % 360.0 - 180.0
                            freeze_cmd[1] = max(-lim4, min(lim4, freeze_cmd[1]))
                            yp_ = struct.pack("<2f", *freeze_cmd)
                            for off_ in CAM_ANGLES:
                                pm.write_bytes(mgr_ + off_, yp_, 8)
                except Exception as e_:
                    if now >= zone_dbg_t:
                        zone_dbg_t = now + 0.5
                        print(f"crossing view hold failed: {e_!r}", flush=True)
            if ENTRY_CAM_HOLD and not space and now < cam_angles_until and player and BASE is not None:
                try:
                    gu3 = game_up()
                    if cam_pitch_in is None and gu3 is not None:
                        lk3 = viewdir.cam_axes(pm, BASE)
                        if lk3 is not None:
                            pin_ = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(np.array(lk3[2]), gu3))))))
                            cam_pitch_in = entry_pitch
                    if cam_pitch_in is not None:
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        yp_ = struct.pack("<2f", CAM_YAW_BEHIND, cam_pitch_in)
                        for off_ in CAM_ANGLES:
                            pm.write_bytes(mgr_ + off_, yp_, 8)
                except Exception:
                    pass
            if space and now < space_cam[0] and player and BASE is not None:
                try:
                    mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                    yp_ = struct.pack("<2f", 0.0, space_cam[1])
                    for off_ in CAM_ANGLES[:2]:
                        pm.write_bytes(mgr_ + off_, yp_, 8)
                except Exception:
                    pass
            if space:
                f_, r_, u_ = cam_axes()
                if f_ is not None:
                    sp_axes = (f_, r_, u_)
                fwd, right, cam_up = sp_axes
                if cam_up is not None:
                    up = cam_up
                if player and BASE is not None:
                    try:
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        if abs(struct.unpack("<f", pm.read_bytes(mgr_ + CAM_PITCH_LIMIT, 4))[0] - 85.0) < 1.0:
                            space_cam_t = space_cam_t or now
                        else:
                            space_cam_t = 0.0
                        diving_ = fwd is not None and last_up is not None and                             float(np.dot(fwd, last_up)) < -math.sin(math.radians(30))
                        if diving_ and SET_HANDOFF_IN_SPACE:
                            vp_ = view_pitch(last_up)
                            entry_pitch = max(-CAM_PLANET_LIMIT, min(CAM_PLANET_LIMIT, vp_ if vp_ is not None else -ENTRY_PITCH))
                    except Exception:
                        pass
                if fwd is not None and cam_up is not None and player:
                    try:
                        pu_ = unit(rd(player + PLAYER_ORIENT))
                        h_ = flat(fwd - cam_up * float(np.dot(fwd, pu_)), pu_)
                        if h_ is not None:
                            entry_aim = (h_, max(-ENTRY_PITCH_MAX, min(ENTRY_PITCH_MAX, math.degrees(
                                math.asin(max(-1.0, min(1.0, float(np.dot(fwd, pu_)))))))))
                            cl_ = h_ * math.cos(math.radians(30)) - pu_ * math.sin(math.radians(30))
                            pass
                    except Exception:
                        pass
            else:
                look, true_view = view_dir()
                fwd, right, cam_up = steer.update(dt, look, now, true_view)
            if right is not None and FLIP_STRAFE:
                right = -right
            fw, st, cl = down("W") - down("S"), down("D") - down("A"), down(CLIMB) - down(DESCEND)
            kb_ = lambda a, b: (kbdown(a) - kbdown(b)) if kbdown(a) or kbdown(b) else None
            fw, st, cl = PAD.axes(fw, st, cl, kb_("W", "S"), kb_("D", "A"),
                                  kb_(CLIMB, DESCEND))
            fin_ = fw
            if THROTTLE_MODE:
                throttle, thr_lock, reversing = throttle_step(throttle, fin_, dt, now, thr_lock)
                if suspended:
                    throttle, reversing = 0.0, False
                    thr_lock = now + THROTTLE_DETENT
                if reversing:
                    SPEED, fw = throttle_speed(-1.0), -1.0
                elif fin_ < 0:
                    ahead_ = float(np.dot(v, fwd)) if fwd is not None else 0.0
                    SPEED, fw = throttle_speed(-1.0), (-1.0 if ahead_ > 2.0 else 0.0)
                else:
                    SPEED = throttle_speed(throttle)
                    fw = 1.0 if throttle > 0.0 else 0.0
            if space:
                rk, st = st, 0
                roll_v += max(-SPACE_ROLL_ACC * dt, min(SPACE_ROLL_ACC * dt, rk * SPACE_ROLL_RATE - roll_v))
                roll_ax_ = None
                if abs(roll_v) > 1e-4 and player and fwd is not None and right is not None and cam_up is not None:
                    roll_ax_ = np.cross(cam_up, right)
                    if float(np.linalg.norm(roll_ax_)) < 0.5:
                        roll_ax_ = None
                roll_game_ = roll_share(roll_v if roll_ax_ is not None else 0.0, roll_ax_)
                if abs(roll_v) > 1e-4 and player and roll_ax_ is not None and not roll_game_:
                    ax = np.cross(cam_up, right)
                    n_ = np.linalg.norm(ax)
                    if n_ > 0.5:
                        ax, a_ = ax / n_, roll_v * dt
                        c_, s_ = math.cos(a_), math.sin(a_)
                        try:
                            for off in (PLAYER_ORIENT, PLAYER_ORIENT + 0x10):
                                r_ = rd(player + off)
                                r_ = r_ * c_ + np.cross(ax, r_) * s_ + ax * np.dot(ax, r_) * (1 - c_)
                                if np.isfinite(r_).all():
                                    pm.write_bytes(player + off, struct.pack("<3f", *r_), 12)
                        except Exception:
                            pass
                if (SPACE_ALIGN and player and fwd is not None and last_up is not None and BASE is not None
                        and float(np.dot(fwd, last_up)) < -math.sin(math.radians(SPACE_ALIGN_LOOK))):
                    try:
                        U0, B0, F0 = (rd(player + o_) for o_ in (PLAYER_ORIENT, PLAYER_ORIENT + 0x10, 0x3480))
                        U0 = unit(U0)
                        ang_ = math.acos(max(-1.0, min(1.0, float(np.dot(U0, last_up)))))
                        mgr_ = struct.unpack("<Q", pm.read_bytes(BASE + viewdir.DATA_PTR, 8))[0] + viewdir.MGR_OFF
                        def yp_of(U, B):
                            fh, lh = flat(B, U), flat(fwd, U)
                            p_ = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(fwd, U))))))
                            y_ = (math.degrees(math.atan2(float(np.dot(np.cross(fh, lh), U)), float(np.dot(fh, lh))))
                                  if fh is not None and lh is not None else None)
                            return y_, p_
                        U1, B1, F1 = U0, B0, F0
                        if ang_ > math.radians(0.05):
                            ax_ = np.cross(U0, last_up)
                            n_ = float(np.linalg.norm(ax_))
                            ax_ = ax_ / n_ if n_ > 1e-6 else right
                            a_ = min(ang_, SPACE_ALIGN_RATE * dt)
                            c_, s_ = math.cos(a_), math.sin(a_)
                            rot_ = lambda r: r * c_ + np.cross(ax_, r) * s_ + ax_ * np.dot(ax_, r) * (1 - c_)
                            U1, B1, F1 = rot_(U0), rot_(B0), rot_(F0)
                        y0_, p0_ = yp_of(U0, B0)
                        y1_, p1_ = yp_of(U1, B1)
                        dy_ = ((y1_ - y0_ + 180.0) % 360.0 - 180.0) if y0_ is not None and y1_ is not None else 0.0
                        dp_ = p1_ - p0_
                        lo_ = -(CAM_PLANET_LIMIT - 2.0)
                        if p1_ < lo_:
                            dp_ += min(lo_ - p1_, SPACE_ALIGN_PITCH * dt)
                        if (dy_ or dp_) and np.isfinite([*U1, *B1, *F1]).all():
                            pm.write_bytes(player + PLAYER_ORIENT, struct.pack("<3f", *U1), 12)
                            pm.write_bytes(player + PLAYER_ORIENT + 0x10, struct.pack("<3f", *B1), 12)
                            pm.write_bytes(player + 0x3480, struct.pack("<3f", *F1), 12)
                            yc_, pc_ = struct.unpack("<2f", pm.read_bytes(mgr_ + CAM_ANGLES[0], 8))
                            yp_ = struct.pack("<2f", (yc_ + dy_ + 180.0) % 360.0 - 180.0, max(-84.0, min(84.0, pc_ + dp_)))
                            for off_ in CAM_ANGLES[:2]:
                                pm.write_bytes(mgr_ + off_, yp_, 8)
                    except Exception:
                        pass
            else:
                if roll_v:
                    roll_share(0.0, None)
                roll_v = 0.0
            pad_brake_ = pressed("BRAKE")
            if pressed("S") or pad_brake_:
                if (pad_brake_ or now - brake_tap < BRAKE_TAP) and now - brake_t > BRAKE_COOLDOWN:
                    brake_t, brake_tap, throttle = now, -9.0, 0.0
                    thr_lock = now + THROTTLE_DETENT + BRAKE_TIME
                    if JETPACK_POSE:
                        jet_relight = now + BRAKE_TIME + BRAKE_RELIGHT
                    if space:
                        sfx_any("power_down", "brake_boom")
                    else:
                        sfx_any("brake_wub", "power_down", "brake_boom")
                    print("HARD BRAKE", flush=True)
                else:
                    brake_tap = now
            hold_mode = SET.flight["afterburner_mode"] == "hold"
            if hold_mode:
                burner = down("SHIFT") and not ab_locked
            elif pressed("SHIFT"):
                if ab_locked:
                    print("afterburner cooling down", flush=True)
                else:
                    burner = not burner
                    burner_on_t = now
                    print("afterburner " + ("ON" if burner else "off"), flush=True)
            if (burner and not hold_mode and idle_since is not None
                    and now - max(idle_since, burner_on_t) >= BURNER_IDLE_DELAY
                    and float(np.linalg.norm(v)) < BURNER_IDLE_SPEED):
                burner = False
                status("afterburner off (you came to a stop)", "burner_off")
            burning = (burner or (cl > 0 and not space and SET.flight["climb_fires_afterburner"])) and not ab_locked
            if burning:
                ab_last = now
                ab_fuel -= dt / AB_FUEL_TIME
                if ab_fuel <= 0.0:
                    ab_fuel, ab_locked, burner, burning = 0.0, True, False, False
                    print("afterburner overheated: cooling down", flush=True)
            if burning and not burn_was:
                sfx("afterburner_on")
                speedfx.punch(4.0, 0.5, 0.5)
            burn_was = burning
            raw_caps_ = caps_key_down(now)
            boom.rearm = SONIC_REARM_HOOK if caps_phys.ok(now) else SONIC_REARM
            caps_press_ = boom.key(now, raw_caps_)
            if cruise_prev and not cruise:
                cruise_lvl, ip_auto = 0.0, None
                if ip_charge:
                    audio.track_stop("ip_charge", IP_CHARGE_CUT)
                    ip_charge = False
            if space or cruise:
                n_tiers_ = len(CRUISE_TIERS)
                if not raw_caps_ and boom.armed:
                    ip_raise_ok = False
                if caps_press_ and fwd is not None and fin_ >= 0:
                    if cruise_mark(cruise_lvl) < 1 and ip_auto is None:
                        ip_auto, ip_raise_ok = ip_auto_origin(now, cruise_lvl), False
                        if IP_MODE == "mine":
                            audio.track_play("ip_charge", cruise_lvl * n_tiers_ * IP_CHARGE_TIME, volume=1.0, fade=0.03)
                            ip_charge = True
                        print(f"interplanetary charge-up: stage 1 in {(1.0 - cruise_lvl * n_tiers_) * IP_CHARGE_TIME:.2f} s",
                              flush=True)
                    else:
                        ip_raise_ok = True
                lvl0_ = cruise_lvl
                mark0_ = cruise_mark(cruise_lvl)
                if ip_auto is not None:
                    if fin_ < 0 or fwd is None:
                        ip_auto = None
                        if ip_charge:
                            audio.track_stop("ip_charge", IP_CHARGE_CUT)
                            ip_charge = False
                    else:
                        a_ = ip_auto_level(now, ip_auto)
                        cruise_lvl = max(cruise_lvl, a_)
                        if a_ >= 1.0 / n_tiers_ - 1e-9:
                            cruise_lvl, ip_auto = max(cruise_lvl, 1.0 / n_tiers_), None
                            lvl_lock = (now + CRUISE_DETENT, 1)
                hold_up_ = (raw_caps_ and ip_raise_ok and ip_auto is None and fwd is not None
                            and cruise_mark(cruise_lvl) >= 1)
                rate_ = (cruise_fill_rate(cruise_lvl) if hold_up_ else 0.0) + (fin_ / CRUISE_DRAIN if fin_ < 0 else 0.0)
                cruise_lvl, lvl_lock = cruise_level_step(cruise_lvl, rate_, dt, now, lvl_lock)
                mark1_ = cruise_mark(cruise_lvl)
                if mark1_ > mark0_:
                    j_ = min(mark1_, len(IP_BOOM_SHOCK)) - 1
                    shock_seq, shock_k = shock_seq + 1, IP_BOOM_SHOCK[j_]
                    speedfx.punch(*IP_BOOM_PUNCH[j_])
                    warpfx_boom(IP_BOOM_SHOCK[j_])
                    PAD.buzz(*IP_BOOM_RUMBLE[j_])
                    if mark1_ == 1:
                        sfx("ip_stage1")
                        sfx("ip_boom1")
                    else:
                        sfx_any(*IP_BOOM_SOUNDS[j_])
                        if ip_hum and (mark1_ < n_tiers_ or not IP_GROWL):
                            audio.track_fade("ip_hum", ip_hum_volume(ip_hum_rate_now) * IP_HUM_DUCK[0], IP_HUM_DUCK[1])
                            ip_duck_t = now
                        elif ip_hum:
                            audio.track_fade("ip_hum", ip_hum_volume(ip_hum_rate_now) * IP_HUM_DUCK[0], 0.0)
                    print(f"interplanetary threshold {mark1_}: {cruise_cap(cruise_lvl) / 1000:.0f} km/s "
                          f"(boom {IP_BOOM_SHOCK[j_]:.1f})", flush=True)
                elif mark1_ < mark0_:
                    brake_fx_t = now
                    if mark1_ == 0 and IP_MODE == "mine":
                        sfx_any("ip_stage1_rev", "brake_boom")
                    else:
                        sfx("brake_boom")
                    print(f"interplanetary threshold {mark0_} -> {mark1_}", flush=True)
                if ip_charge and ip_auto is None and mark1_ == 0 and cruise_lvl < lvl0_:
                    audio.track_stop("ip_charge", IP_CHARGE_CUT)
                    ip_charge = False
                elif ip_charge and ip_auto is None and mark1_ >= 1:
                    ip_charge = False
                if cruise and cruise_lvl <= 0.0:
                    cruise, cruise_end, cruise_out = False, now, CRUISE_OUT
                    print("interplanetary cruise off (its level down to none)", flush=True)
                elif not cruise and cruise_lvl > 0.0 and fwd is not None and now - cruise_end >= CRUISE_COOLDOWN:
                    cruise, cruise_out, cruise_t0 = True, None, now
                    cruise_spd = max(float(np.linalg.norm(v)), min(CRUISE_START, cruise_cap(cruise_lvl)))
                    print(f"INTERPLANETARY CRUISE (level {cruise_lvl * 100:.0f} %)", flush=True)
            else:
                cruise_lvl, ip_auto = 0.0, None
            mk_ = cruise_mark(cruise_lvl)
            want_hum_ = cruise and IP_MODE == "mine" and mk_ >= 1 and (mk_ < len(CRUISE_TIERS) or not IP_GROWL)
            want_growl_ = IP_GROWL and cruise and IP_MODE == "mine" and mk_ >= len(CRUISE_TIERS)
            if want_hum_ and not ip_hum:
                audio.track_play("ip_hum", 0.0, loop=True, volume=IP_HUM_VOLUME,
                                 fade=IP_HUM_FADE_IN if not ip_growl else IP_HUM_HANDOFF)
                ip_hum, ip_hum_rate_now = True, 1.0
            elif ip_hum and not want_hum_:
                audio.track_stop("ip_hum", IP_HUM_HANDOFF if want_growl_ else IP_HUM_FADE_OUT)
                ip_hum, ip_duck_t = False, None
            if want_growl_ and not ip_growl:
                audio.track_play("ip_growl", 0.0, loop=True, volume=IP_GROWL_VOLUME, fade=IP_GROWL_FADE_IN)
                ip_growl = True
            elif ip_growl and not want_growl_:
                audio.track_stop("ip_growl", IP_GROWL_FADE_OUT)
                ip_growl = False
            if ip_hum:
                r_ = ip_hum_rate(cruise_lvl)
                if abs(r_ - ip_hum_rate_now) > 0.006 and now - ip_pitch_t >= 0.04:
                    audio.track_speed("ip_hum", r_)
                    if ip_duck_t is None:
                        audio.track_fade("ip_hum", ip_hum_volume(r_), 0.1)
                    ip_hum_rate_now, ip_pitch_t = r_, now
            if ip_duck_t is not None and (not ip_hum or now - ip_duck_t >= IP_HUM_DUCK[2]):
                if ip_hum:
                    audio.track_fade("ip_hum", ip_hum_volume(ip_hum_rate_now), IP_HUM_DUCK[3])
                ip_duck_t = None
            if ip_charge and not (space or cruise):
                audio.track_stop("ip_charge", IP_CHARGE_CUT)
                ip_charge = False
            cruise_prev = cruise
            if caps_press_ and not (space or cruise):
                gate_ = THROTTLE_MODE and (reversing or fin_ < 0 or throttle <= SONIC_GATE)
                if fwd is None:
                    pass
                elif gate_ or boom.sections() < 1:
                    boom.refuse(now)
                    sfx_any("boom_denied")
                    why_ = ("not while reversing" if reversing else "not while braking (S held)" if fin_ < 0 else
                            f"needs more than a quarter throttle (throttle {max(0.0, throttle) * 100:.0f} %)")
                    print("sonic boom: " + (why_ if gate_ else f"recharging ({boom.meter * 100:.0f} %)"), flush=True)
                else:
                    i_ = boom.fire(now)
                    aim_ = fwd * (fin_ if fin_ else fw)
                    if right is not None:
                        aim_ = aim_ + right * st
                    if cam_up is not None:
                        aim_ = aim_ + cam_up * cl
                    n_ = float(np.linalg.norm(aim_))
                    aim_ = aim_ / n_ if n_ > 0.3 else fwd
                    kick_ = SONIC_BLAST_KICK[i_ - 1] * SONIC_KICK_SCALE * ((KICK_SPEED or SPEED) / 18.0)
                    v = v + aim_ * kick_
                    sonic_t, sonic_k = now, SONIC_BLAST_K[i_ - 1]
                    sonic_carry = float(np.dot(aim_, fwd)) > 0.7
                    sonic = sonic_k
                    shock_seq, shock_k = shock_seq + 1, SONIC_BLAST_SHOCK[i_ - 1]
                    speedfx.punch(*SONIC_BLAST_PUNCH[i_ - 1])
                    warpfx_blast(i_)
                    if i_ >= SONIC_SECTIONS:
                        warpfx_boom(SONIC_BLAST_SHOCK[i_ - 1])
                    PAD.buzz(*SONIC_BLAST_RUMBLE[i_ - 1])
                    sfx_any(*SONIC_BLAST_SOUNDS[i_ - 1])
                    print(f"SONIC BOOM {i_}/{SONIC_SECTIONS} (+{kick_:.0f} m/s"
                          + ("" if sonic_carry else f", keys fw {fw:+.1f} st {st:+.1f} cl {cl:+.1f}")
                          + f"; meter {boom.meter * 100:.0f} %)", flush=True)
            if sonic > 0.0 and sonic_carry and fw <= 0:
                fw = 1
            if fw < 0 and now - brake_t < BRAKE_TIME:
                fw = 0
            was_dive = dive
            dive = not space and fw > 0 and steer.pitch <= (DIVE_EXIT if dive else DIVE_ENTER)
            if dive != was_dive:
                print("dive mode " + ("ON" if dive else "off"), flush=True)
                if dive:
                    cue("dive_on")
            boost = (AFTERBURNER if burning else 1.0) * (DIVE_SPEED if dive else 1.0) * (1.0 + (SONIC_BOOST - 1.0) * sonic)
            v, want = fly_step(v, dt, fwd, right, cam_up, up, fw, st, cl, boost, 1.0 - (1.0 - SONIC_DRAG) * sonic,
                               (SPACE_DRAG_THRUST, SPACE_DRAG_COAST) if space else None,
                               None if space or not THROTTLE_MODE else HOVER_MOVE_SPEED)
            if water and not space and not water_speed.lifted:
                vn_w = float(np.linalg.norm(v))
                if vn_w > WATER_MAX_SPEED:
                    v = v * (WATER_MAX_SPEED / vn_w)
            if cruise and (not space or (fw <= 0 and not THROTTLE_MODE) or now - brake_t < BRAKE_TIME or suspended
                           or fwd is None):
                cruise, cruise_end = False, now
                cruise_out = CRUISE_OUT if space else CRUISE_OUT_ATMO
                print("interplanetary cruise off" + ("" if space else ": into the atmosphere"), flush=True)
            cruise_h = None
            if cruise:
                cap = cruise_cap(cruise_lvl) if THROTTLE_MODE else CRUISE_MAX
                ob_ = obstacles()
                sp_ = float(np.linalg.norm(v))
                u_ = v / sp_ if sp_ > 1.0 else (fwd if fwd is not None else np.array([0.0, 0.0, 1.0]))
                if ob_ is not None:
                    shift_ = v * min(1.0, max(0.0, now - ob_[0]))
                    for rel0_, r_ in ob_[1]:
                        rel_ = rel0_ - shift_
                        dist_ = float(np.linalg.norm(rel_))
                        s_ = float(rel_ @ u_)
                        if s_ <= 0.0 or math.sqrt(max(0.0, dist_ * dist_ - s_ * s_)) > \
                                r_ + max(CRUISE_MARGIN[0] * r_, CRUISE_MARGIN[1]):
                            continue
                        h_ = dist_ - r_
                        cruise_h = h_ if cruise_h is None else min(cruise_h, h_)
                else:
                    nv_ = nav()
                    try:
                        if nv_ is not None and float((nv_[2] - rd(player + 0x360)) @ v) > 0.0:
                            cruise_h = nv_[1]
                    except Exception:
                        pass
                if cruise_h is not None:
                    top_ = max(CRUISE_MAX, min(CRUISE_FAR[0], cruise_h / CRUISE_FAR[1])) * cap / CRUISE_MAX
                    cap = min(top_, max(CRUISE_MIN, CRUISE_K * cruise_h))
                    if cruise_h < CRUISE_FLOOR:
                        cruise, cruise_end, cruise_out = False, now, CRUISE_OUT_ATMO
                        print(f"interplanetary cruise off: {cruise_h:.0f} m above the ground", flush=True)
            if cruise:
                if cruise_spd < cap:
                    cruise_spd = min(cap, cruise_spd + max(CRUISE_ACC, cruise_spd / CRUISE_RAMP) * dt)
                else:
                    cruise_spd = max(cap, cruise_spd * math.exp(-dt / CRUISE_DOWN))
                if cruise_h is not None:
                    cruise_spd = min(cruise_spd, max(CRUISE_MIN, (cruise_h - 0.5 * CRUISE_FLOOR) / CRUISE_AHEAD))
                sp_ = float(np.linalg.norm(v))
                d_ = v / sp_ if sp_ > 1.0 else fwd
                d_ = d_ + (fwd - d_) * ease(dt, CRUISE_TURN)
                n_ = float(np.linalg.norm(d_))
                v = (d_ / n_ if n_ > 1e-6 else fwd) * cruise_spd
            elif cruise_out is not None:
                sp_ = float(np.linalg.norm(v))
                if sp_ > CRUISE_OUT_SPEED:
                    v = v * max(CRUISE_OUT_SPEED / sp_, math.exp(-dt / cruise_out))
                else:
                    cruise_out = None
            cruise_fx += ((1.0 if cruise else 0.0) - cruise_fx) * ease(dt, 0.2 if cruise else 0.8)
            if not cruise and cruise_fx < 0.01:
                cruise_fx = 0.0
            if PULL_ON and space and pull is None and player and now >= dock_check:
                dock_check = now + 0.1
                dt_ = dock_tunnel()
                if dt_ is not None:
                    try:
                        rel_ = rd(player + 0x360) - dt_[0]
                    except Exception:
                        rel_ = None
                    if rel_ is not None and not in_anomaly(rel_ + dt_[0], dt_[0]):
                        s_ = -float(rel_ @ dt_[1])
                        r_ = float(np.linalg.norm(rel_ + dt_[1] * s_))
                        if PULL_MOUTH[0] < s_ < PULL_MOUTH[1] and r_ < PULL_RADIUS and float(v @ dt_[1]) > PULL_IN_SPEED:
                            cruise = False
                            pull = {"phase": "out", "t": now, "te": dt_[0], "ax": dt_[1],
                                    "spd": max(float(v @ dt_[1]), 20.0)}
                            status("the Space Anomaly's pull has you", "ready")
            if PULL_ON and pull is None and player and now >= pull_out_check:
                pull_out_check = now + 0.1
                try:
                    me_ = rd(player + 0x360)
                except Exception:
                    me_ = None
                z_ = PULL_EXIT_ZONE
                if (me_ is not None and float(v[2]) > 5.0
                        and z_[0][0] < me_[0] < z_[0][1] and z_[1][0] < me_[1] < z_[1][1] and z_[2][0] < me_[2] < z_[2][1]):
                    dt_ = dock_tunnel()
                    if dt_ is not None and in_anomaly(me_, dt_[0]):
                        pull = {"phase": "exit", "t": now, "te": dt_[0], "ax": dt_[1], "spd": max(float(v[2]), 20.0)}
                        status("the Space Anomaly takes you out", "ready")
            if PULL_ON and pull is None and player and now >= st_check:
                st_check = now + 0.1
                sf_ = station()
                if sf_ is not None:
                    O_, R_, plug_, rel_ = sf_
                    try:
                        l_ = R_ @ (rd(player + 0x360) - O_)
                    except Exception:
                        l_ = None
                    if l_ is not None:
                        rad_ = float(np.hypot(l_[0] - plug_[0], l_[1] - plug_[1]))
                        vz_ = float(R_[2] @ v)
                        if (space and ST_CATCH[0] < l_[2] - plug_[2] < ST_CATCH[1] and rad_ < ST_RADIUS
                                and vz_ < -PULL_IN_SPEED):
                            cruise = False
                            pull = {"phase": "st_in", "t": now, "st": sf_, "spd": max(-vz_, 20.0)}
                            status("the space station's pull has you", "ready")
                        elif (-ST_TUBE_FROM < l_[2] - plug_[2] < -ST_HOP * 0.5 and rad_ < ST_TUBE and vz_ > 5.0):
                            pull = {"phase": "st_out", "t": now, "st": sf_, "spd": max(vz_, 20.0)}
                            status("the space station takes you out", "ready")
            if PULL_ON and pull is None and player and now >= fr_hop_until:
                fr_ = freighter()
                if fr_ is not None:
                    O_, R_, dz_, dy_, xs_ = fr_
                    try:
                        l_ = R_ @ (rd(player + 0x360) - O_)
                    except Exception:
                        l_ = None
                    z2_ = freighter_hop(l_, R_ @ v, dz_, dy_, xs_) if l_ is not None else None
                    if z2_ is not None:
                        w_ = O_ + R_.T @ np.array([l_[0], l_[1], z2_])
                        vn_ = float(np.linalg.norm(v))
                        warp_to(tuple(w_), tuple(float(round(x / 1024.0) * 1024.0) for x in w_), tuple(v),
                                tuple(v / vn_) if vn_ > 1e-3 else (0.0, 0.0, -1.0))
                        fr_hop_until = now + 0.6
                        cruise = False
                        print(f"freighter: hopped {'in through' if z2_ > dz_ + FR_WALL else 'out through'} the hangar's "
                              f"wall (at {l_[0]:.0f} {l_[1]:.0f} {l_[2]:.0f}, {vn_:.0f} m/s)", flush=True)
            if DOCK_ON and space and dock is None and player and now >= dock_check:
                dock_check = now + 0.1
                dt_ = dock_tunnel()
                if dt_ is not None:
                    try:
                        rel_ = rd(player + 0x360) - dt_[0]
                    except Exception:
                        rel_ = None
                    if rel_ is not None:
                        s_ = -float(rel_ @ dt_[1])
                        r_ = float(np.linalg.norm(rel_ + dt_[1] * s_))
                        if DOCK_MOUTH[0] < s_ < DOCK_MOUTH[1] and r_ < DOCK_RADIUS and float(v @ dt_[1]) > DOCK_IN_SPEED:
                            cruise = False
                            dock, force_toggle = {"state": "call", "t": now}, True
                            status("into the Space Anomaly: your starship docks you", "ready")
            if suspended and space:
                v = v * math.exp(-DRAG_COAST * dt)
            elif suspended and now - unfocused_since > 60.0:
                v = v + up * ((-4.0 - float(np.dot(v, up))) * ease(dt, 0.5))
            if now - brake_t < BRAKE_TIME:
                v = v * math.exp(-(SPACE_BRAKE_RATE if space else BRAKE_RATE)
                                 * math.sin(math.pi * (now - brake_t) / BRAKE_TIME) * dt)
            if water and not space and player and fw == 0 and cl == 0 and not stalled:
                try:
                    p_ = rd(player + 0x360)
                    if hold_pos is None:
                        hold_pos = p_
                        depth_hold.reset()
                    vt_, stale_ = depth_hold.step(float(np.dot(p_ - hold_pos, up)), now, dt)
                    if stale_ and now >= water_stale_quiet:
                        stale_now = True
                    elif stale_:
                        hold_pos = None
                    v = v + up * (vt_ - float(np.dot(v, up)))
                except Exception:
                    hold_pos = None
            else:
                hold_pos = None
            skimming = False
            if water and cl < 0 and surf_pt is not None:
                try:
                    if float(np.dot(rd(player + 0x360) - surf_pt, up)) < -SKIM_DIVE:
                        skim_ok = False
                except Exception:
                    pass
            if (SKIM and water and not space and player and fw != 0 and cl == 0 and skim_ok and surf_pt is not None
                    and now - surf_t < SKIM_FRESH and not stalled and pull is None and fwd is not None):
                try:
                    h_ = float(np.dot(rd(player + 0x360) - surf_pt, up))
                    el_ = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(fwd, up))))))
                    vz_ = skim_vz(h_, el_)
                    if vz_ is not None:
                        v = v + up * (vz_ - float(np.dot(v, up)))
                        skimming = True
                except Exception:
                    pass
            if pull is not None:
                pd_ = None
                try:
                    me_ = rd(player + 0x360)
                except Exception:
                    me_ = None
                if me_ is not None and pull["phase"] in ("out", "in", "exit", "away", "st_in", "st_out"):
                    if pull.get("sp") is None or pull.get("sph") != pull["phase"]:
                        pull.update(sp=me_, spt=now, sph=pull["phase"])
                    elif float(np.linalg.norm(me_ - pull["sp"])) > 3.0:
                        pull.update(sp=me_, spt=now)
                    elif now - pull["spt"] > PULL_STALL:
                        status("something's in the way: the pull lets you go", "error")
                        pull, me_ = None, None
                        v = np.zeros(3)
                if pull is None:
                    pass
                elif me_ is None or now - pull["t"] > PULL_TIMEOUT:
                    status("the pull lost you: flying on", "error")
                    pull = None
                elif pull["phase"] == "out":
                    dt2_ = dock_tunnel()
                    if dt2_ is not None:
                        pull["te"], pull["ax"] = dt2_
                    te_, ax_ = pull["te"], pull["ax"]
                    rel_ = me_ - te_
                    s_ = -float(rel_ @ ax_)
                    pull["spd"] = min(PULL_MAX, pull["spd"] + PULL_ACC * dt)
                    v = ax_ * pull["spd"] + _centre(rel_ + ax_ * s_)
                    pd_ = ax_
                    if s_ < PULL_WARP:
                        pull.update(phase="warp", req=warp_to(PULL_INSIDE, PULL_INSIDE_OFF, (0.0, 0.0, -pull["spd"] * 0.6),
                                                              (0.0, 0.0, -1.0)), wt=now)
                elif pull["phase"] == "warp":
                    v = np.array([0.0, 0.0, -pull["spd"] * 0.6])
                    pd_ = np.array([0.0, 0.0, -1.0])
                    if warp_done(pull["req"]) and in_anomaly(me_, pull["te"]):
                        pull.update(phase="in", k=0, spd=pull["spd"] * 0.6)
                    elif now - pull["wt"] > 3.0:
                        status("the pull couldn't take you through: flying on", "error")
                        pull = None
                elif pull["phase"] in ("st_in", "st_out", "st_hop"):
                    O_, R_, plug_, rel_ = pull["st"]
                    l_ = R_ @ (me_ - O_)
                    dz_ = l_[2] - plug_[2]
                    if pull["phase"] == "st_hop":
                        pd_ = pull["dir"]
                        v = pd_ * pull["spd"]
                        if warp_done(pull["req"]) and (dz_ * pull["side"]) > 1.0:
                            pull.update(phase=pull["back"])
                            pull.pop("sp", None)
                        elif now - pull["wt"] > 2.0:
                            status("the pull couldn't get you past the station's wall: flying on", "error")
                            pull = None
                    else:
                        inward_ = pull["phase"] == "st_in"
                        if inward_ and dz_ < -ST_HOP * 0.5:
                            tgt_ = rel_ if l_[2] < rel_[2] + 80.0 else np.array([plug_[0], plug_[1], rel_[2] + 60.0])
                            if l_[2] > rel_[2] + 80.0:
                                tgt_ = np.array([plug_[0], plug_[1], l_[2] - 60.0])
                            left_ = float(np.linalg.norm(rel_ - l_))
                            want_ = min(ST_IN_MAX, PULL_IN_SLOW * left_ + 1.0)
                        else:
                            tgt_ = np.array([plug_[0], plug_[1], l_[2] + (-60.0 if inward_ else 60.0)])
                            want_ = ST_IN_MAX if inward_ else (PULL_MAX if dz_ < ST_OUT_END - 80.0 else PULL_OUT_SPEED)
                        pull["spd"] += max(-PULL_ACC * dt, min(PULL_ACC * dt, want_ - pull["spd"]))
                        d_ = tgt_ - l_
                        dn_ = float(np.linalg.norm(d_))
                        dl_ = d_ / dn_ if dn_ > 1e-3 else np.array([0.0, 0.0, -1.0 if inward_ else 1.0])
                        side_ = np.array([d_[0], d_[1], 0.0])
                        v_l = dl_ * pull["spd"]
                        if not (inward_ and dz_ < -ST_HOP * 0.5):
                            v_l = np.array([0.0, 0.0, (-1.0 if inward_ else 1.0) * pull["spd"]]) + _centre(-side_)
                        v = R_.T @ v_l
                        pd_ = v / max(1e-3, float(np.linalg.norm(v)))
                        hop_ = (inward_ and 0.0 < dz_ < ST_HOP * 0.7) or (not inward_ and -ST_HOP * 0.7 < dz_ < 0.0)
                        if hop_:
                            l2_ = np.array([plug_[0], plug_[1], plug_[2] + (-ST_HOP if inward_ else ST_HOP)])
                            w_ = O_ + R_.T @ l2_
                            pull.update(phase="st_hop", back=pull["phase"], side=(-1.0 if inward_ else 1.0), wt=now,
                                        dir=pd_, req=warp_to(tuple(w_), tuple(float(round(x / 1024.0) * 1024.0) for x in w_),
                                                             tuple(v), tuple(pd_)))
                        elif inward_ and dz_ < 0.0 and float(np.linalg.norm(rel_ - l_)) < 2.5:
                            v = np.zeros(3)
                            pull = None
                            su_ = unit(R_[1])
                            if su_ is not None:
                                up = last_up = su_
                                if steer is not None:
                                    steer.set_up(up)
                            status("inside the space station: the pull lets you go", "ready")
                        elif not inward_ and dz_ > ST_OUT_END:
                            v = R_[2] * PULL_OUT_SPEED
                            pull = None
                            status("out of the space station: the pull lets you go", "ready")
                elif pull["phase"] == "hop":
                    pd_ = pull["dir"]
                    v = pd_ * pull["spd"]
                    if warp_done(pull["req"]) and (me_[2] - PULL_WALL_Z) * pull["side"] > 1.0:
                        pull.update(phase=pull["back"])
                        pull.pop("sp", None)
                    elif now - pull["wt"] > 2.0:
                        status("the pull couldn't get you past its wall: flying on", "error")
                        pull = None
                elif pull["phase"] == "exit":
                    (cx_, cy_), _ = PULL_EXIT_AXIS
                    pull["spd"] = min(PULL_MAX if me_[2] > PULL_WALL_Z else 40.0, pull["spd"] + PULL_ACC * dt)
                    pd_ = np.array([0.0, 0.0, 1.0])
                    v = pd_ * pull["spd"] + _centre(np.array([me_[0] - cx_, me_[1] - cy_, 0.0]))
                    if PULL_WALL_Z - PULL_HOP < me_[2] < PULL_WALL_Z:
                        w_ = (float(me_[0]), float(me_[1]), PULL_WALL_Z + PULL_HOP)
                        pull.update(phase="hop", back="exit", side=1.0, wt=now, dir=pd_,
                                    req=warp_to(w_, PULL_INSIDE_OFF, tuple(v), (0.0, 0.0, 1.0)))
                    if me_[2] > PULL_EXIT_WARP:
                        dt2_ = dock_tunnel()
                        if dt2_ is not None:
                            pull["te"], pull["ax"] = dt2_
                        te_, ax_ = pull["te"], pull["ax"]
                        w_ = te_ - ax_ * PULL_OUT_AT
                        pull.update(phase="exitwarp", wt=now, req=warp_to(
                            tuple(w_), tuple(float(round(x / 1024.0) * 1024.0) for x in w_),
                            tuple(-ax_ * pull["spd"] * 0.7), tuple(-ax_)))
                elif pull["phase"] == "exitwarp":
                    pd_ = np.array([0.0, 0.0, 1.0])
                    v = pd_ * pull["spd"] * 0.7
                    if warp_done(pull["req"]) and not in_anomaly(me_, pull["te"]):
                        pull.update(phase="away", spd=pull["spd"] * 0.7)
                    elif now - pull["wt"] > 3.0:
                        status("the Space Anomaly couldn't put you out: flying on", "error")
                        pull = None
                elif pull["phase"] == "away":
                    dt2_ = dock_tunnel()
                    if dt2_ is not None:
                        pull["te"], pull["ax"] = dt2_
                    te_, ax_ = pull["te"], pull["ax"]
                    rel_ = me_ - te_
                    s_ = -float(rel_ @ ax_)
                    want_ = PULL_OUT_SPEED + max(0.0, PULL_OUT_END - s_) * 0.5
                    pull["spd"] += max(-PULL_ACC * dt, min(PULL_ACC * dt, min(PULL_MAX, want_) - pull["spd"]))
                    pd_ = -ax_
                    v = pd_ * pull["spd"] + _centre(rel_ + ax_ * s_)
                    if s_ > PULL_OUT_END:
                        v = pd_ * PULL_OUT_SPEED
                        pull = None
                        status("out of the Space Anomaly: the pull lets you go", "ready")
                if pull is not None and pull["phase"] == "in" and PULL_WALL_Z < me_[2] < PULL_WALL_Z + PULL_HOP:
                    w_ = (float(me_[0]), float(me_[1]), PULL_WALL_Z - PULL_HOP)
                    d_ = np.array(w_) - me_
                    pull.update(phase="hop", back="in", side=-1.0, wt=now, dir=d_ / max(1e-3, float(np.linalg.norm(d_))),
                                req=warp_to(w_, PULL_INSIDE_OFF, tuple(v), (0.0, 0.0, -1.0)))
                    while pull["k"] < len(PULL_PATH) - 1 and PULL_PATH[pull["k"]][2] > PULL_WALL_Z - PULL_HOP:
                        pull["k"] += 1
                if pull is not None and pull["phase"] == "in":
                    end_ = np.array(PULL_PATH[-1])
                    while pull["k"] < len(PULL_PATH) - 1 and float(np.linalg.norm(np.array(PULL_PATH[pull["k"]]) - me_)) < 30.0:
                        pull["k"] += 1
                    tgt_ = np.array(PULL_PATH[pull["k"]])
                    left_ = float(np.linalg.norm(tgt_ - me_)) + sum(
                        float(np.linalg.norm(np.array(PULL_PATH[i + 1]) - np.array(PULL_PATH[i])))
                        for i in range(pull["k"], len(PULL_PATH) - 1))
                    want_ = min(PULL_IN_MAX, PULL_IN_SLOW * left_ + 1.0)
                    pull["spd"] += max(-PULL_ACC * dt, min(PULL_ACC * dt, want_ - pull["spd"]))
                    d_ = tgt_ - me_
                    dn_ = float(np.linalg.norm(d_))
                    pd_ = d_ / dn_ if dn_ > 1e-3 else np.array([0.0, 0.0, -1.0])
                    v = pd_ * pull["spd"]
                    if float(np.linalg.norm(end_ - me_)) < 2.5:
                        v = np.zeros(3)
                        pull = None
                        up = last_up = np.array(ANOMALY_UP)
                        if steer is not None:
                            steer.set_up(up)
                        status("inside the Space Anomaly: the pull lets you go", "ready")
                if pull is not None and pd_ is not None:
                    pull["dir"] = pd_
            if not (water and not space and water_speed.lifted):
                wr(v)
            if verify is not None and water:
                verify = None
            if verify is not None and stalled:
                verify, verify_t = [], now
            if verify is not None and player and now - verify_t >= TAKEOFF_CHECK[0]:
                try:
                    if not verify:
                        verify = [now, rd(player + 0x360), np.zeros(3), 0]
                    else:
                        verify[2] = verify[2] + v
                        verify[3] += 1
                        if now - verify[0] >= TAKEOFF_CHECK[1] - TAKEOFF_CHECK[0]:
                            moved = (rd(player + 0x360) - verify[1]) / (now - verify[0])
                            want_ = verify[2] / max(1, verify[3])
                            sp_ = float(np.linalg.norm(want_))
                            miss_ = float(np.linalg.norm(moved - want_))
                            verify = None
                            if sp_ > 2.0 and miss_ > TAKEOFF_CHECK[2] * sp_ and float(np.linalg.norm(moved)) > 1.0:
                                verify_miss += 1
                                if verify_miss < 2:
                                    verify = []
                                    if SET.debug["verbose"]:
                                        print(f"take-off check: off by {miss_:.1f} of {sp_:.1f} m/s -- looking again",
                                              flush=True)
                                else:
                                    print(f"the body steered isn't moving you (off by {miss_:.1f} of {sp_:.1f} m/s)",
                                          flush=True)
                                    stale_now, verify_miss = True, 0
                            else:
                                verify_miss = 0
                except Exception:
                    verify = None
            if stale_now and fg and not stalled:
                stale_now, verify = False, None
                BODY_STALE[0] = True
                print("re-finding your body mid-flight...", flush=True)
                if relocate():
                    v, hold_pos = np.zeros(3), None
                    water_stale_quiet = now + WATER_STALE_QUIET
                    limb_flag(True)
                    if JETPACK_POSE:
                        keys.press("SPACE")
                    print("found you: flying on", flush=True)
                else:
                    on, burner = False, False
                    limb_flag(False)
                    if JETPACK_POSE:
                        keys.release("SPACE")
                    sfx("flight_off")
                    import locate as locate_
                    print("flight OFF (" + (DECK_MSG if locate_.ON_DECK else "couldn't find your character: "
                                            "land and double-tap Space again") + ")", flush=True)
                continue
            warp_amt_ = cruise_fx * min(1.0, (float(np.linalg.norm(v)) / CRUISE_MAX) ** 0.35) if cruise_fx > 0 else 0.0
            speedfx.update(dt, 1.0 if dive else 0.0, 1.0 if burning else 0.0, sonic, max(cruise_fx * 0.5, warp_amt_))
            vp_ = (0.5, 0.5)
            if warp_amt_ > 0.0:
                try:
                    f_, r_, u2_ = cam_axes()
                    d_ = v / max(1e-3, float(np.linalg.norm(v)))
                    z_ = float(d_ @ f_)
                    if z_ > 0.3:
                        tv_ = math.tan(math.radians(0.5 * (70.0 + speedfx.extra_fov())))
                        vp_ = (min(0.85, max(0.15, 0.5 + 0.5 * float(d_ @ r_) / z_ / (tv_ * 16.0 / 9.0))),
                               min(0.85, max(0.15, 0.5 - 0.5 * float(d_ @ u2_) / z_ / tv_)))
                except Exception:
                    pass
            pack_screen(now)
            try:
                _WARPFX[88:96] = struct.pack("<d", cruise_lvl if cruise else 0.0)
            except Exception:
                pass
            warpfx_share(warp_amt_, float(np.linalg.norm(v)) if cruise_fx > 0 else 0.0, vp_,
                         cruise_h if (cruise and cruise_h is not None) else -1.0)
            water_cam.update(True)
            share(True, pull["dir"] if pull is not None and pull.get("dir") is not None else fwd, want, up,
                  burning or sonic > 0 or cruise, v, dive, space, cruise,
                  water and not space and water_speed.lifted)
            sinking = float(np.dot(v, up)) < -1.0
            if sinking and not stalled and float(np.dot(actual, up)) > 0.3 * float(np.dot(v, up)):
                last_blocked = now
            if water:
                water_last = now
            fall_hist.append((now, -float(np.dot(v, up))))
            vn = float(np.linalg.norm(v))
            steep = DIVE_LANDS and cl <= 0 and vn > 1.0 and float(np.dot(v, up)) < -0.87 * vn
            if stalled:
                grounded_since = None
            elif (pull is None and not space and not water and now - water_last > 1.5 and now - on_since > 3.0
                  and (not (fw or st or cl > 0) or steep)):
                on_ground_ = my_state is not None and my_state in states and charstate.read(my_state) in charstate.GROUND
                grounded = now - last_blocked < 0.1 or on_ground_
                if grounded:
                    grounded_since = grounded_since or now
                    if now - grounded_since > (0.25 if on_ground_ else LAND_BLOCK_HOLD):
                        on, burner = False, False
                        limb_flag(False)
                        if JETPACK_POSE:
                            keys.release("SPACE")
                        peak = max((d for t, d in fall_hist if t >= grounded_since - 0.3), default=0.0)
                        hard = peak > HARD_LAND_SPEED
                        sfx("land_hard" if hard else "land_soft")
                        if hard:
                            speedfx.punch(0.0, -0.3, 0.4)
                        status(f"landed{' hard' if hard else ''}: flight OFF")
                else:
                    grounded_since = None
            else:
                grounded_since = None
            if on and now >= next_block:
                next_block = now + 0.5
                kind = charstate.blocked(states, my_state)
                if kind == "vehicle":
                    on, burner = False, False
                    wr(v * min(1.0, 2.0 / max(vn, 1e-6)))
                    limb_flag(False)
                    if JETPACK_POSE:
                        keys.release("SPACE")
                    sfx("flight_off")
                    status("flight OFF (you got into a vehicle)")
            if on and now >= next_title:
                next_title = now + 0.25
                audio.title(f"FLYING {vn:.0f} m/s" + (" AB" if burning else "") + (" DIVE" if dive else ""))
            if log is not None and now >= next_log:
                next_log = now + 0.1
                log.write(f"{time.time():.2f},1,{SPEED:.1f},{np.linalg.norm(v):.2f},"
                          f"{np.linalg.norm(want):.2f},{cl},{int(burner)}\n")
                log.flush()
        if on and THROTTLE_MODE:
            if fin_ < 0 or reversing:
                force_, supp_ = 4, 1
            elif throttle > 0.0:
                force_, supp_ = 1 | 0x200, 4
            else:
                force_, supp_ = 0, 5
        else:
            force_, supp_ = 0, 0
        if suspended:
            force_, supp_ = 0, 0x3F
        PAD_SHARE.write(PAD, 0, force=force_, suppress=supp_, act=ROUTE.bits(now))
        thr_fl_ = ((8 if space else 0) | (16 if cruise else 0) | (64 if suspended else 0)
                   | (256 if on and skimming else 0))
        if on and THROTTLE_MODE:
            if reversing:
                thr_fl_ |= 2
            elif fin_ < 0:
                thr_fl_ |= 4
            elif throttle > 0.0:
                thr_fl_ |= 1
        throttle_share(on, -1.0 if reversing else throttle, float(np.linalg.norm(v)) if on else 0.0, thr_fl_)
        time.sleep(0.001)
    if JETPACK_POSE:
        keys.release("SPACE")
    if log is not None:
        log.close()
    limb_flag(False)
    print("quit", flush=True)
_QUIT = [False]
EXIT_CODE = [0]
def _cleanup():
    if not _QUIT[0]:
        _QUIT[0] = True
        time.sleep(0.05)
    try:
        audio.stop()
    except Exception:
        pass
    try:
        PAD.stop()
        PAD_SHARE.write()
    except Exception:
        pass
    try:
        water_cam.restore()
    except Exception:
        pass
    try:
        swim_anims.restore()
    except Exception:
        pass
    try:
        water_speed.restore()
    except Exception:
        pass
    try:
        lookcam.restore(pm)
    except Exception:
        pass
    try:
        if BASE is not None:
            pm.write_float(BASE + SPACE_CAM_CENTER, SPACE_CAM_CENTER_SHIPPED)
    except Exception:
        pass
    try:
        arsenal.set_ship(False)
    except Exception:
        pass
    try:
        if WHEEL_RESTORE[0]:
            w_, o_ = WHEEL_RESTORE[0]
            pm.write_bytes(w_ + WHEEL_LIST, struct.pack(f"<{len(o_)}i", *o_), 4 * len(o_))
            pm.write_bytes(w_ + WHEEL_N, struct.pack("<i", len(o_)), 4)
            WHEEL_RESTORE[0] = None
    except Exception:
        pass
    try:
        animswap.restore()
    except Exception:
        pass
    try:
        speedfx.restore()
    except Exception:
        pass
    try:
        hud(False)
        if _hud_proc[0] is not None:
            _hud_proc[0].terminate()
    except Exception:
        pass
    try:
        keys.release("SPACE")
    except Exception:
        pass
    try:
        (HERE / "limbjets.flag").write_text("0")
    except Exception:
        pass
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
def _on_console_close(event):
    _cleanup()
    return False
if __name__ == "__main__":
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_on_console_close, True)
    try:
        main()
    except pymem.exception.MemoryReadError:
        print("lost the game's data (game restarted or loaded elsewhere): start the launcher again", flush=True)
    except SystemExit:
        raise
    except BaseException as e:
        import traceback
        traceback.print_exc()
        EXIT_CODE[0] = 1
        try:
            CTRL.line(f"crashed: {e.__class__.__name__}: {e}")
        except Exception:
            pass
    finally:
        _cleanup()
        try:
            CTRL.exited(EXIT_CODE[0])
        except Exception:
            pass
    sys.exit(EXIT_CODE[0])
