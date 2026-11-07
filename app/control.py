import ctypes
import ctypes.wintypes as wt
import mmap
import os
import struct
import sys
import threading
import time
PROTO = 1
CTL_NAME, CTL_SIZE, CTL_MAGIC = "IronManFlightControl", 4096, b"IMFC"
STS_NAME, STS_SIZE, STS_MAGIC = "IronManFlightStatus", 8192, b"IMFS"
NSLOTS, SLOT_SIZE, SLOTS_OFF = 16, 128, 64
CTL_HDR_FMT = "<4sHHHHIIId"
CTL_SEQ_OFF = 12
CTL_BEAT_OFF, CTL_BEAT_FMT = 16, "<IId"
CTL_HWND_OFF = 32
CTL_SHOW_OFF = 40
CMD_FMT = "<IHHdfI4d64s"
STS_HDR_FMT = "<4sHHIIdd16si"
STS_BEAT_OFF = 16
STS_TEL_OFF, STS_TEL_FMT = 64, "<IIBBBB12fIdIIdf"
STS_ACK_OFF, ACK_FMT, ACK_SIZE = 1024, "<IBbHd48s", 64
STS_LINE_OFF, LINE_FMT = 2048, "<Id244s"
STS_LOG_OFF, LOG_FMT, LOG_SIZE, LOG_N = 2304, "<Id148s", 160, 36
SCRIPT_MUTEX = "Local\\IronManFlightScript"
SCRIPT_NAME = "flight_planet"
PANEL_MUTEX = "Local\\IronManFlightPanel"
WRITE_MUTEX = "Local\\IronManFlightControlWrite"
GAME_NAME, GAME_SIZE, GAME_FMT = "IronManFlightGame", 16, "<dQ"
PHASE = {0: "starting", 1: "running", 2: "quitting", 3: "exited"}
CMDS = {1: ("ping", False), 2: ("reload", False), 3: ("fly", True), 4: ("quit", False), 5: ("refind", True),
        6: ("reset_fx", False), 7: ("play_sound", False),
        13: ("relight", True), 14: ("restart_hud", False),
        15: ("restart_effects", False), 17: ("refill", False)}
CMD = {name: code for code, (name, _) in CMDS.items()}
F_WAIT_FOCUS, F_QUIET, F_FROM_HOTKEY = 1, 2, 4
ACK = {1: "received", 2: "waiting for the game", 3: "running", 4: "done", 5: "failed", 6: "expired",
       7: "refused", 8: "dropped"}
DONE, FAILED, EXPIRED, REFUSED, DROPPED = 4, 5, 6, 7, 8
FINAL = ("done", "failed", "expired", "refused", "dropped")
EXIT = {0: "powered down", 3: "another copy was already running", 75: "restarting"}
FL = dict(flying=1 << 0, suspended=1 << 1, stalled=1 << 2, space=1 << 3, water=1 << 4, cruise=1 << 5, dive=1 << 6,
          burning=1 << 7, ab_cooling=1 << 8, reversing=1 << 9, armed=1 << 10, ship_arms=1 << 11, focused=1 << 12,
          quitting=1 << 13, mod_live=1 << 14, pad=1 << 15, speedfx=1 << 16, restart_pending=1 << 17,
          character_ok=1 << 18, pull=1 << 19, on_deck=1 << 21, busy=1 << 23, menu_up=1 << 24,
          right_shoulder=1 << 25, hud_alive=1 << 26, warpfx_alive=1 << 27, panel_seen=1 << 29)
FL2 = dict(mods_disabled=1 << 0, camera_unreadable=1 << 1, tank_not_found=1 << 2, no_shoulder=1 << 3,
           speedfx_refused=1 << 4)
APPLY = {("keys", k): "live" for k in ("forward", "back", "left", "right", "fly_toggle", "climb", "descend",
                                       "afterburner", "faster", "slower", "quit", "double_tap_space",
                                       "arm_toggle", "arsenal_toggle")}
APPLY[("keys", "panel")] = "panel"
APPLY.update({("flight", k): "live" for k in (
    "start_speed", "min_speed", "max_speed", "afterburner_mode", "climb_fires_afterburner",
    "double_tap_window", "flip_strafe", "dive_lands", "throttle_up_time", "throttle_down_time", "throttle_curve",
    "hover_detent", "reverse_speed", "afterburner_power", "afterburner_time", "afterburner_recharge", "dive_boost",
    "hard_brake_window")})
APPLY[("flight", "remember_speed")] = "restart"
APPLY.update({("boom", k): "live" for k in ("charge_time", "kick_scale", "boost", "refill_time")})
APPLY.update({("flight", "pilot_flame"): "live", ("flight", "hover_move_speed"): "live"})
APPLY.update({("cruise", "top_speed_kms"): "hud+effects", ("cruise", "tier_fill_time"): "live",
              ("cruise", "drain_time"): "live"})
APPLY.update({("camera", "recenter_delay"): "live", ("camera", "speed_effects"): "live",
              ("camera", "motion_blur"): "live", ("camera", "effects_strength"): "live",
              ("camera", "camera_kicks"): "live"})
APPLY.update({("sound", k): "live" for k in ("cues", "sound_volume", "suit_sounds", "boom_sounds", "interplanetary",
                                             "hum_volume")})
APPLY.update({("hud", k): "hud" for k in ("hud", "space_map", "shock_waves")})
APPLY.update({("effects", k): "effects" for k in ("warp_effects", "warp_blur")})
APPLY.update({("panel", k): "panel" for k in ("always_on_top", "open_with_flight", "confirm_quit")})
APPLY[("panel", "warm_start")] = "launcher"
APPLY.update({("debug", "flight_log"): "restart", ("debug", "verbose"): "live", ("game", "path"): "launcher"})
APPLY.update({("pad", k): "live" for k in (
    "enabled", "fly_toggle", "climb", "descend", "afterburner", "faster", "slower",
    "roll_left", "roll_right", "sonic_boom", "hard_brake", "quit", "stick_deadzone", "trigger_deadzone", "move_threshold",
    "stick_curve", "double_tap_window", "quit_hold", "rumble", "rumble_strength")})
RESTART_KEYS = frozenset(k for k, v in APPLY.items() if v == "restart")
HUD_KEYS = frozenset(k for k, v in APPLY.items() if "hud" in v.split("+"))
EFFECTS_KEYS = frozenset(k for k, v in APPLY.items() if "effects" in v.split("+"))
def apply_class(sec, key):
    return APPLY.get((str(sec).lower(), str(key).lower()), "live")
k32 = ctypes.windll.kernel32
_kx = ctypes.WinDLL("kernel32", use_last_error=True)
_kx.CreateMutexW.restype = wt.HANDLE
_kx.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
_kx.OpenMutexW.restype = wt.HANDLE
_kx.OpenMutexW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
_kx.WaitForSingleObject.restype = wt.DWORD
_kx.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
_kx.ReleaseMutex.argtypes = [wt.HANDLE]
_kx.CloseHandle.argtypes = [wt.HANDLE]
_kx.OpenProcess.restype = wt.HANDLE
_kx.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_kx.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(ctypes.c_uint64)] * 4
def _open(name, size):
    return mmap.mmap(-1, size, tagname=name)
def pid_alive(pid):
    if not pid:
        return False
    h = k32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    try:
        code = wt.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(h)
def created_h(h):
    c, x, k, u = (ctypes.c_uint64() for _ in range(4))
    if not h or not _kx.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(k), ctypes.byref(u)):
        return None
    return c.value / 1e7 - 11644473600.0
def process_created(pid):
    if not pid:
        return None
    h = _kx.OpenProcess(0x1000, False, int(pid))
    if not h:
        return None
    try:
        return created_h(h)
    finally:
        _kx.CloseHandle(h)
_nt = ctypes.WinDLL("ntdll")
_nt.NtQueryInformationProcess.restype = ctypes.c_long
_nt.NtQueryInformationProcess.argtypes = [wt.HANDLE, wt.ULONG, ctypes.c_void_p, wt.ULONG, ctypes.POINTER(wt.ULONG)]
class _UStr(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]
def command_line_h(h):
    try:
        need = wt.ULONG(0)
        buf = ctypes.create_string_buffer(2048)
        r = _nt.NtQueryInformationProcess(h, 60, buf, len(buf), ctypes.byref(need))
        if r == -1073741820 and 0 < need.value < 1 << 20:
            buf = ctypes.create_string_buffer(need.value)
            r = _nt.NtQueryInformationProcess(h, 60, buf, len(buf), ctypes.byref(need))
        if r != 0:
            return None
        us = _UStr.from_buffer(buf)
        return ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else ""
    except Exception:
        return None
def runs_script(pid, name="flight_planet", h=None):
    own = h is None
    if own:
        h = _kx.OpenProcess(0x1000, False, int(pid)) if pid else None
        if not h:
            return None
    try:
        cl = command_line_h(h)
        return None if cl is None else name.lower() in cl.lower()
    finally:
        if own:
            _kx.CloseHandle(h)
REUSE_SLACK = 30.0
def same_process(pid, started, created=None):
    if not pid or not started or started <= 0.0:
        return None
    created = process_created(pid) if created is None else created
    if created is None:
        return None
    began = time.time() - (time.perf_counter() - started)
    return created <= began + REUSE_SLACK
def _text(b):
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")
def _bytes(s, n):
    b = (s or "").encode("utf-8", "replace")[:n - 1]
    return b.decode("utf-8", "ignore").encode("utf-8")
def mutex_exists(name):
    h = _kx.OpenMutexW(0x00100000, False, name)
    if h:
        _kx.CloseHandle(h)
        return True
    return ctypes.get_last_error() == 5
class Mutex:
    def __init__(self, name):
        kx = ctypes.WinDLL("kernel32", use_last_error=True)
        kx.CreateMutexW.restype = wt.HANDLE
        self.h = kx.CreateMutexW(None, False, name)
        self.taken = ctypes.get_last_error() == 183
        self._k = kx
    def close(self):
        if self.h:
            self._k.CloseHandle(self.h)
            self.h = None
class _WriteLock:
    def __init__(self, name):
        self.h = _kx.CreateMutexW(None, False, name)
        self.got = False
    def __enter__(self):
        self.got = bool(self.h) and _kx.WaitForSingleObject(self.h, 50) in (0, 0x80)
        return self
    def __exit__(self, *exc):
        if self.got:
            _kx.ReleaseMutex(self.h)
            self.got = False
def _init_ctl(ctl):
    if struct.unpack_from("<4s", ctl, 0)[0] != CTL_MAGIC:
        struct.pack_into(CTL_HDR_FMT, ctl, 0, CTL_MAGIC, PROTO, NSLOTS, SLOT_SIZE, SLOTS_OFF, 0, 0, 0, 0.0)
class Client:
    def __init__(self, suffix=""):
        self.suffix = suffix
        self.ctl = _open(CTL_NAME + suffix, CTL_SIZE)
        self.sts = _open(STS_NAME + suffix, STS_SIZE)
        self.lock = threading.Lock()
        self._wl = _WriteLock(WRITE_MUTEX + suffix)
        _init_ctl(self.ctl)
    def beat(self, visible=True, foreground=False, hotkey=False, hwnd=0):
        flags = (1 if visible else 0) | (2 if foreground else 0) | (4 if hotkey else 0)
        struct.pack_into(CTL_BEAT_FMT, self.ctl, CTL_BEAT_OFF, os.getpid(), flags, time.perf_counter())
        struct.pack_into("<Q", self.ctl, CTL_HWND_OFF, int(hwnd or 0) & 0xFFFFFFFFFFFFFFFF)
    def panel_info(self):
        pid, flags, t = struct.unpack_from(CTL_BEAT_FMT, self.ctl, CTL_BEAT_OFF)
        hwnd = struct.unpack_from("<Q", self.ctl, CTL_HWND_OFF)[0]
        age = time.perf_counter() - t if t else 1e9
        return dict(pid=pid, flags=flags, hwnd=hwnd, age=age, alive=age < 2.0 and pid_alive(pid))
    def show_request(self):
        with self.lock, self._wl:
            n = (struct.unpack_from("<I", self.ctl, CTL_SHOW_OFF)[0] + 1) & 0xFFFFFFFF
            struct.pack_into("<I", self.ctl, CTL_SHOW_OFF, n)
        return n
    def show_count(self):
        return struct.unpack_from("<I", self.ctl, CTL_SHOW_OFF)[0]
    def send(self, cmd, a=(0.0, 0.0, 0.0, 0.0), text="", flags=0, ttl=None):
        code = CMD[cmd] if isinstance(cmd, str) else int(cmd)
        if CMDS.get(code, ("", False))[1]:
            flags |= F_WAIT_FOCUS
        ttl = ttl if ttl is not None else (20.0 if flags & F_WAIT_FOCUS else 5.0)
        a = tuple(float(x) for x in (list(a) + [0.0, 0.0, 0.0, 0.0])[:4])
        with self.lock, self._wl:
            seq = (struct.unpack_from("<I", self.ctl, CTL_SEQ_OFF)[0] + 1) & 0xFFFFFFFF or 1
            off = SLOTS_OFF + SLOT_SIZE * (seq % NSLOTS)
            struct.pack_into("<I", self.ctl, off, 0)
            struct.pack_into(CMD_FMT, self.ctl, off, 0, code, flags, time.perf_counter(), ttl, os.getpid(), *a,
                             _bytes(text, 64))
            struct.pack_into("<I", self.ctl, off, seq)
            struct.pack_into("<I", self.ctl, CTL_SEQ_OFF, seq)
        return seq
    def ack(self, seq):
        a = struct.unpack_from(ACK_FMT, self.sts, STS_ACK_OFF + ACK_SIZE * (seq % NSLOTS))
        if a[0] != seq:
            return None
        return ACK.get(a[1], str(a[1])), a[2], _text(a[5])
    def wait(self, seq, timeout=3.0):
        end = time.perf_counter() + timeout
        last = None
        while time.perf_counter() < end:
            last = self.ack(seq)
            if last and last[0] in FINAL:
                return last
            time.sleep(0.03)
        return last
    def status(self):
        for _ in range(20):
            h = struct.unpack_from(STS_HDR_FMT, self.sts, 0)
            if h[4] % 2:
                time.sleep(0.001)
                continue
            raw = bytes(self.sts[0:STS_SIZE])
            if struct.unpack_from(STS_HDR_FMT, raw, 0)[4] != h[4]:
                continue
            break
        else:
            raw = bytes(self.sts[0:STS_SIZE])
        if self.suffix:
            return parse_status(raw)
        return parse_status(raw, script_mutex=mutex_exists(SCRIPT_MUTEX), script_name=SCRIPT_NAME)
    def log_lines(self, since=0):
        cnt = struct.unpack_from("<I", self.sts, STS_LOG_OFF)[0]
        out = []
        for n in range(max(since + 1, cnt - LOG_N + 1), cnt + 1):
            off = STS_LOG_OFF + 8 + LOG_SIZE * (n % LOG_N)
            m, t, txt = struct.unpack_from(LOG_FMT, self.sts, off)
            if m == n:
                out.append((n, t, _text(txt)))
        return out
def parse_status(raw, now=None, script_mutex=None, script_name=None):
    h = struct.unpack_from(STS_HDR_FMT, raw, 0)
    now = time.perf_counter() if now is None else now
    d = dict(magic=h[0] == STS_MAGIC, phase=PHASE.get(h[2], "?"), pid=h[3], age=now - h[5] if h[5] else 1e9,
             started=h[6], version=_text(h[7]), exit_code=h[8])
    d["session"] = (h[3], h[6])
    d["pid_alive"] = d["magic"] and pid_alive(h[3])
    d["pid_reused"] = False
    if d["pid_alive"] and (script_mutex is False or same_process(h[3], h[6]) is False
                           or (script_name and runs_script(h[3], script_name) is False)):
        d["pid_alive"], d["pid_reused"] = False, True
    d["alive"] = d["magic"] and d["phase"] in ("starting", "running", "quitting") and d["pid_alive"]
    d["responding"] = d["alive"] and d["age"] < 1.5
    t = struct.unpack_from(STS_TEL_FMT, raw, STS_TEL_OFF)
    d["flags"], d["flags2"], d["startup_stage"] = t[0], t[1], t[2]
    d["player_mode"], d["settings_warnings"] = t[3], t[4]
    for i, k in enumerate(("startup_progress", "speed", "throttle", "cruise_level", "ab_fuel", "sonic_meter",
                           "speed_level", "min_speed", "max_speed", "height", "loop_hz", "mod_age")):
        d[k] = t[6 + i]
    d["settings_gen"], d["settings_mtime"], d["last_seq_seen"], d["raise_req"] = t[18], t[19], t[20], t[21]
    d["loop_t"], d["away_s"] = t[22], t[23]
    d["loop_age"] = now - t[22] if t[22] > 0.0 else 1e9
    for k, b in FL.items():
        d[k] = bool(t[0] & b)
    for k, b in FL2.items():
        d[k] = bool(t[1] & b)
    ln = struct.unpack_from(LINE_FMT, raw, STS_LINE_OFF)
    d["line"] = (ln[0], ln[1], _text(ln[2]))
    return d
def exit_text(code):
    if code in EXIT:
        return EXIT[code]
    return "it crashed" if code == 1 else f"exit code {code}"
STUCK_EXITED, STUCK_QUITTING, STUCK_STARTING = 20.0, 20.0, 120.0
def suit_state(st, now=None):
    if not st.get("magic"):
        return "offline", "not started"
    now = time.perf_counter() if now is None else now
    phase = st.get("phase")
    line = st.get("line", (0, 0.0, ""))[2]
    if not st.get("pid_alive"):
        if phase == "exited":
            why = exit_text(st.get("exit_code", 0))
            if why == "it crashed" and line.startswith("crashed: "):
                line = line[len("crashed: "):]
            return "offline", why + (f": {line}" if line else "")
        return "offline", "stopped without saying why (killed or crashed)" + (f": {line}" if line else "")
    age, busy = st.get("age", 1e9), st.get("busy", False)
    if phase == "exited":
        if age > STUCK_EXITED:
            return "not_responding", f"it powered down {age:.0f} s ago but its process is still running"
        return "busy", "powering down"
    if age >= 15.0:
        return "not_responding", f"no heartbeat for {age:.0f} s"
    if age >= 1.5:
        return "busy", line or "busy"
    la, has_loop = st.get("loop_age", 1e9), st.get("loop_t", 0.0) > 0.0
    if phase == "running" and has_loop and la > 10.0 and not (busy and la < 60.0):
        return "not_responding", f"its main loop has been stuck for {la:.0f} s"
    if phase == "quitting" and has_loop and la > STUCK_QUITTING:
        return "not_responding", f"it has been powering down for {la:.0f} s"
    started = st.get("started", 0.0) or 0.0
    quiet = now - max(started, st.get("loop_t", 0.0) or 0.0)
    if phase == "starting" and started > 0.0 and quiet > STUCK_STARTING:
        return "not_responding", f"it has been starting for {now - started:.0f} s"
    if busy:
        return "busy", line or "busy"
    return "online", {"starting": "starting", "quitting": "powering down"}.get(phase, "running")
def mod_state(stamp_t, nms_running, now=None):
    if not nms_running:
        return "off"
    if not stamp_t or stamp_t <= 0.0:
        return "not_attached"
    now = time.perf_counter() if now is None else now
    return "live" if now - stamp_t < 0.5 else "paused"
class Server:
    def __init__(self, suffix="", version="dev", beat=True):
        self.ctl = _open(CTL_NAME + suffix, CTL_SIZE)
        self.sts = _open(STS_NAME + suffix, STS_SIZE)
        _init_ctl(self.ctl)
        h = struct.unpack_from(CTL_HDR_FMT, self.ctl, 0)
        self.seen = h[5]
        self.started = time.perf_counter()
        self.version = version
        self.pub_seq = 0
        self.tel = dict(flags=0, flags2=0, startup_stage=0)
        self.log_n = struct.unpack_from("<I", self.sts, STS_LOG_OFF)[0]
        self.log_lock = threading.Lock()
        self.line_n = 0
        self._header(0)
        self._beat_stop = threading.Event()
        self._beat_thread = None
        if beat:
            self.start_beat()
    def start_beat(self, interval=0.25):
        if self._beat_thread is None or not self._beat_thread.is_alive():
            self._beat_stop.clear()
            self._beat_thread = threading.Thread(target=self._beat_loop, args=(interval,), daemon=True,
                                                 name="control-beat")
            self._beat_thread.start()
    def stop_beat(self):
        self._beat_stop.set()
    def _beat_loop(self, interval):
        while not self._beat_stop.wait(interval):
            try:
                struct.pack_into("<d", self.sts, STS_BEAT_OFF, time.perf_counter())
            except Exception:
                return
    def _header(self, phase, exit_code=0):
        self.pub_seq = (self.pub_seq + 1) | 1
        struct.pack_into("<I", self.sts, 12, self.pub_seq)
        struct.pack_into(STS_HDR_FMT, self.sts, 0, STS_MAGIC, PROTO, phase, os.getpid(), self.pub_seq,
                         time.perf_counter(), self.started, _bytes(self.version, 16), exit_code)
        self.pub_seq += 1
        struct.pack_into("<I", self.sts, 12, self.pub_seq)
    def poll(self, now=None):
        now = time.perf_counter() if now is None else now
        ws = struct.unpack_from("<I", self.ctl, CTL_SEQ_OFF)[0]
        if ws == self.seen:
            return []
        if (ws - self.seen) & 0xFFFFFFFF > 0x7FFFFFFF:
            self.seen = ws
            return []
        out = []
        first = (self.seen + 1) & 0xFFFFFFFF
        if (ws - first) & 0xFFFFFFFF >= NSLOTS:
            for s in range(first, (ws - NSLOTS + 1) & 0xFFFFFFFF):
                self.ack(s, DROPPED, 0, "dropped (too many at once)")
            first = (ws - NSLOTS + 1) & 0xFFFFFFFF
        s = first
        while True:
            off = SLOTS_OFF + SLOT_SIZE * (s % NSLOTS)
            v = struct.unpack_from(CMD_FMT, self.ctl, off)
            if v[0] == s and struct.unpack_from("<I", self.ctl, off)[0] == s:
                c = dict(seq=s, cmd=v[1], name=CMDS.get(v[1], ("?", False))[0], flags=v[2], issued=v[3], ttl=v[4],
                         pid=v[5], a=v[6:10], text=_text(v[10]))
                if now - c["issued"] > c["ttl"]:
                    self.ack(s, EXPIRED, 0, "too old")
                else:
                    out.append(c)
                    self.ack(s, 1, 0, "")
            else:
                self.ack(s, DROPPED, 0, "dropped (too many at once)")
            if s == ws:
                break
            s = (s + 1) & 0xFFFFFFFF
        self.seen = ws
        return out
    def ack(self, seq, state, code=0, msg=""):
        struct.pack_into(ACK_FMT, self.sts, STS_ACK_OFF + ACK_SIZE * (seq % NSLOTS), seq, state, max(-128, min(127, code)),
                         0, time.perf_counter(), _bytes(msg, 48))
    def panel(self):
        pid, _, t = struct.unpack_from(CTL_BEAT_FMT, self.ctl, CTL_BEAT_OFF)
        return pid, (time.perf_counter() - t < 2.0) and pid_alive(pid), time.perf_counter() - t
    def publish(self, phase=1, **tel):
        now = time.perf_counter()
        loop_t = float(tel.pop("loop_t", 0.0) or now)
        self.tel.update(tel)
        t = self.tel
        f = [t.get(k, 0.0) for k in ("startup_progress", "speed", "throttle", "cruise_level", "ab_fuel", "sonic_meter",
                                     "speed_level", "min_speed", "max_speed", "height", "loop_hz", "mod_age")]
        self.pub_seq += 1
        struct.pack_into("<I", self.sts, 12, self.pub_seq)
        struct.pack_into(STS_HDR_FMT, self.sts, 0, STS_MAGIC, PROTO, phase, os.getpid(), self.pub_seq,
                         now, self.started, _bytes(self.version, 16), 0)
        struct.pack_into(STS_TEL_FMT, self.sts, STS_TEL_OFF, int(t.get("flags", 0)) & 0xFFFFFFFF,
                         int(t.get("flags2", 0)) & 0xFFFFFFFF, int(t.get("startup_stage", 0)) & 0xFF,
                         int(t.get("player_mode", 255)) & 0xFF, min(255, max(0, int(t.get("settings_warnings", 0)))),
                         0, *[float(x) for x in f], int(t.get("settings_gen", 0)) & 0xFFFFFFFF,
                         float(t.get("settings_mtime", 0.0)), self.seen, int(t.get("raise_req", 0)) & 0xFFFFFFFF,
                         loop_t, float(t.get("away_s", -1.0)))
        self.pub_seq += 1
        struct.pack_into("<I", self.sts, 12, self.pub_seq)
    def line(self, text):
        self.line_n += 1
        struct.pack_into(LINE_FMT, self.sts, STS_LINE_OFF, self.line_n, time.perf_counter(), _bytes(text, 244))
    def log(self, text):
        with self.log_lock:
            self.log_n += 1
            off = STS_LOG_OFF + 8 + LOG_SIZE * (self.log_n % LOG_N)
            struct.pack_into(LOG_FMT, self.sts, off, self.log_n, time.perf_counter(), _bytes(text.rstrip(), 148))
            struct.pack_into("<I", self.sts, STS_LOG_OFF, self.log_n)
    def exited(self, code=0, text=""):
        self.stop_beat()
        if text:
            self.line(text)
        self._header(3, code)
class NullServer:
    null = True
    def __init__(self, *a, **k):
        self.seen, self.pub_seq, self.line_n, self.log_n = 0, 0, 0, 0
        self.started = time.perf_counter()
        self.version = k.get("version", "dev")
        self.tel = dict(flags=0, flags2=0, startup_stage=0)
    def poll(self, now=None):
        return []
    def panel(self):
        return 0, False, 1e9
    def ack(self, *a, **k):
        pass
    def publish(self, *a, **k):
        pass
    def line(self, *a, **k):
        pass
    def log(self, *a, **k):
        pass
    def exited(self, *a, **k):
        pass
    def start_beat(self, *a, **k):
        pass
    def stop_beat(self, *a, **k):
        pass
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None
class Tee:
    def __init__(self, stream, server):
        self.stream, self.server, self.buf = stream, server, ""
        self._lock = threading.RLock()
    def write(self, s):
        with self._lock:
            try:
                self.stream.write(s)
            except Exception:
                pass
            try:
                self.buf += s
                while "\n" in self.buf:
                    ln, self.buf = self.buf.split("\n", 1)
                    if ln.strip():
                        try:
                            self.server.log(ln)
                        except Exception:
                            pass
                if len(self.buf) > 4096:
                    self.buf = self.buf[-1024:]
            except Exception:
                pass
        try:
            return len(s)
        except Exception:
            return 0
    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass
    def __getattr__(self, name):
        return getattr(self.stream, name)
if __name__ == "__main__":
    c = Client()
    if len(sys.argv) > 2 and sys.argv[1] == "send":
        args = [float(x) for x in sys.argv[3:7] if x.replace(".", "").replace("-", "").isdigit()]
        text = next((x for x in sys.argv[3:] if not x.replace(".", "").replace("-", "").isdigit()), "")
        seq = c.send(sys.argv[2], args, text)
        print("sent", sys.argv[2], "seq", seq, "->", c.wait(seq, 25.0))
    else:
        s = c.status()
        print(f"{'suit':12s} {suit_state(s)}")
        for k in ("alive", "responding", "phase", "pid", "age", "loop_age", "version", "flying", "speed", "throttle",
                  "line"):
            print(f"{k:12s} {s[k]}")
        print(f"{'panel':12s} {c.panel_info()}")
        for n, t, txt in c.log_lines()[-10:]:
            print("   ", txt)
