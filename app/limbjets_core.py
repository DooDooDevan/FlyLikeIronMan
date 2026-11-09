import ctypes
import logging
import math
import os
import time
from ctypes import CFUNCTYPE, POINTER, c_bool, c_float, c_uint32, c_uint64, c_void_p
import logging.handlers
import threading
log = logging.getLogger("limbjets")
log.propagate = False
for _lg in [logging.getLogger()] + [l for l in logging.Logger.manager.loggerDict.values()
                                    if isinstance(l, logging.Logger)]:
    for _h in list(_lg.handlers):
        if isinstance(_h, logging.handlers.SocketHandler):
            _lg.removeHandler(_h)
_nms = None
_flag = {"want": False}
FLAG_STALE = 4.0
def _flag_reader(stop):
    last_txt, changed, warned = None, time.perf_counter(), False
    while not stop.is_set():
        try:
            try:
                with open(FLAG) as f:
                    txt = f.read(96)
            except OSError:
                txt = None
            now = time.perf_counter()
            want, stale = None, False
            if txt is not None:
                if txt != last_txt:
                    last_txt, changed = txt, now
                c = txt[:1]
                if c == "0":
                    want = False
                    if len(txt) > 2:
                        _flag["alive_t"] = changed
                elif c == "1":
                    parts = txt[2:].split()
                    try:
                        if len(parts) >= 3:
                            _flag["cam"], _flag["cam_sign"] = int(parts[1], 16), float(parts[2])
                    except ValueError:
                        pass
                    want = now - changed < FLAG_STALE if len(parts) >= 4 else True
                    stale = not want
                    _flag["alive_t"] = changed
            elif _flag["want"] and now - changed > FLAG_STALE:
                want, stale = False, True
            if stale and _flag["want"]:
                _release_space()
            _flag["read"] = True
            if want is not None:
                if want != _flag["want"]:
                    log.info(f"limb jets {'shown while the jetpack fires' if want else 'hidden'}")
                _flag["want"] = want
            if not _flag["want"]:
                _flag.pop("cam", None)
        except Exception:
            if not warned:
                warned = True
                log.exception("flag reader")
        time.sleep(0.015)
def _release_space():
    try:
        if ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000:
            ctypes.windll.user32.keybd_event(0x20, 0x39, 0x0002 | 0x0008, 0)
            log.info("the flight script stopped mid-flight: released the Space key it was holding")
    except Exception:
        pass
import sys as _sys
for _ev in getattr(_sys, "_limbjets_stops", []):
    _ev.set()
_stop = threading.Event()
_sys._limbjets_stops = [_stop]
_reader = None
def _ensure_reader():
    global _reader
    if _reader is None or not _reader.is_alive():
        _reader = threading.Thread(target=_flag_reader, args=(_stop,), name="limbjets-flag", daemon=True)
        _reader.start()
def nms():
    global _nms
    if _nms is None:
        import nmspy.data.types as m
        _nms = m
    return _nms
ROOT = os.path.dirname(os.path.abspath(__file__))
FLAG = os.path.join(ROOT, "limbjets.flag")
LOG_FILE, LOG_LIMIT = os.path.join(ROOT, "limbjets_log.txt"), 5 << 20
def _rotate_log():
    try:
        if os.path.getsize(LOG_FILE) <= LOG_LIMIT:
            return
    except OSError:
        return
    hs = [h for h in logging.getLogger("limbjets").handlers
          if isinstance(h, logging.FileHandler) and os.path.normcase(h.baseFilename) == os.path.normcase(LOG_FILE)]
    for h in hs:
        h.acquire()
    try:
        for h in hs:
            if h.stream:
                h.stream.close()
                h.stream = None
        os.replace(LOG_FILE, os.path.join(ROOT, "limbjets_log.old.txt"))
    except OSError:
        pass
    finally:
        for h in hs:
            h.release()
_rotate_log()
RVA_REFRESH = 0x1156F10
RVA_LAMBDA = 0x1157260
RVA_FIND_BY_HASH = 0x2C4FE50
RVA_FIND_BY_NAME = 0x2C4FF20
RVA_GET_NAME = 0x1889700
TYPE_JOINT, TYPE_LOCATOR = 4, 9
LIMBS = [("HandFX_L", "player01_l_arm_WristSHJnt"), ("HandFX_R", "player01_r_arm_WristSHJnt"),
         ("FootFX_L", "player01_l_leg_KneeSHJnt"), ("FootFX_R", "player01_r_leg_KneeSHJnt")]
k32 = ctypes.windll.kernel32
k32.GetModuleHandleW.restype = c_void_p
k32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
BASE = k32.GetModuleHandleW(None)
_find_hash = CFUNCTYPE(c_void_p, POINTER(c_uint32), c_uint32, c_uint32, c_uint32)(BASE + RVA_FIND_BY_HASH)
_find_name = CFUNCTYPE(c_void_p, POINTER(c_uint32), c_uint32, ctypes.c_char_p, c_uint32)(BASE + RVA_FIND_BY_NAME)
_get_name = CFUNCTYPE(ctypes.c_char_p, c_uint32)(BASE + RVA_GET_NAME)
_lambda = CFUNCTYPE(c_bool, c_void_p, c_uint32)(BASE + RVA_LAMBDA)
_refresh = CFUNCTYPE(None, c_void_p)(BASE + RVA_REFRESH)
RVA_TRANSLATE = 0x2C45F70
RVA_LANGUAGE = 0x6EF2CF0
NAME_IDS = (b"BOLT_NAME_L", b"BOLTSHOTGUN_NAME_L", b"BOLTSMG_NAME_L", b"RAILGUN1_NAME_L", b"CANNON_NAME_L",
            b"LASER_NAME_L", b"FLAMETHROW_NAME_L")
_translate = CFUNCTYPE(c_uint64, c_uint64, ctypes.c_char_p, c_void_p)(BASE + RVA_TRANSLATE)
try:
    import mmap as _mmap_names
    _NAMES = _mmap_names.mmap(-1, 72, tagname="IronManFlightNames")
except Exception:
    _NAMES = None
def _names_export(st):
    if _NAMES is None or getattr(st, "names_done", False):
        return
    now = time.perf_counter()
    if now < getattr(st, "names_t", 0.0):
        return
    st.names_t = now + 5.0
    out = [_translate(BASE + RVA_LANGUAGE, i, None) or 0 for i in NAME_IDS]
    if all(out):
        import struct as _struct_names
        _struct_names.pack_into("<d7Q", _NAMES, 0, now, *out)
        st.names_done = True
        log.info("weapon names (for the arsenal): " + ", ".join(ctypes.string_at(a).decode(errors="replace")
                                                          for a in out))
INVALID = 0x7FFFF
class State:
    def __init__(self):
        self.errors = set()
        self.component = None
        self.effect = None
        self.in_refresh = False
        self.building = False
        self.want = False
        self.applied = None
        self.next_poll = 0.0
        self.keep = []
        self.diag_done = False
        self.shown = False
def addr(p):
    if isinstance(p, int):
        return p
    return ctypes.cast(p, c_void_p).value or 0
def u32(a):
    return c_uint32.from_address(a).value
def u64(a):
    return c_uint64.from_address(a).value
def valid(h):
    return h is not None and (h & INVALID) != INVALID
def node_name(h):
    try:
        n = _get_name(h)
        return n.decode(errors="replace") if n else None
    except Exception as e:
        return f"<{e}>"
def _tk(v):
    from nmspy.data.basic_types import TkHandle
    h = TkHandle()
    h.lookupInt = v
    return h
def children(node):
    import nmspy.data.types as nms
    from nmspy.data.basic_types import TkHandle
    out = TkHandle()
    nms.Engine.GetNodeFirstChild(ctypes.byref(out), _tk(node))
    seen = 0
    while out.lookupInt and out.lookup != 0x3FFFF and seen < 10000:
        yield out.lookupInt
        nxt = TkHandle()
        nms.Engine.GetNodeNextSibling(ctypes.byref(nxt), _tk(out.lookupInt))
        out = nxt
        seen += 1
def find_by_walk(root, names):
    import nmspy.data.types as nms
    want = {n.upper(): n for n in names}
    found, stack, visited = {}, [root], 0
    while stack and len(found) < len(want) and visited < 20000:
        n = stack.pop()
        visited += 1
        nm = nms.Engine.GetNodeName(_tk(n))
        if nm:
            s = (nm.decode(errors="replace") if isinstance(nm, bytes) else str(nm)).upper()
            if s in want:
                found[want[s]] = n
        stack.extend(children(n))
    return found, visited
def find_node(parent, name, kinds):
    f, _ = find_by_walk(parent, [name])
    return f.get(name)
def on_reload(st):
    st.diag_done = True
    st.shown = False
    if hasattr(st, "limb_nodes"):
        st.rebuild = True
def refresh_before(st, this):
    st.in_refresh = True
    st.effect = None
REC_COUNT, REC_DATA, REC_SIZE = 0x624, 0x628, 0xF0
REC_NODES = (0x0, 0x4, 0xC)
def refresh_after(st, this):
    this = addr(this)
    st.in_refresh = False
    if st.component and this != st.component and time.perf_counter() - getattr(st, "comp_seen", 0.0) < 1.0:
        return
    st.component = this
    if st.effect:
        log.info(f"refresh on 0x{this:X}: effect 0x{st.effect:X}, {u32(st.effect + 0x38)} jets")
    before = u32(this + REC_COUNT)
    st.limb_mid = st.roll_end = None
    st.sh_joints = []
    add_limb_jets(st, this)
    st.body_diag_at = time.perf_counter() + 3.0
    try:
        st.model_root = player_root(this) or getattr(st, "model_root", None)
    except Exception:
        pass
    after = u32(this + REC_COUNT)
    data = u64(this + REC_DATA)
    st.limb_nodes, st.limb_tk = [], []
    st.pack_nodes, st.pack_tk = [], []
    mid = min(st.limb_mid or after, after)
    rec = lambda i: [h for h in (u32(data + i * REC_SIZE + off) for off in REC_NODES)
                     if h and (h & 0x3FFFF) != 0x3FFFF]
    st.limb_rec = [rec(i) for i in range(before, mid)]
    rend = min(st.roll_end or after, after)
    st.roll_rec = [rec(i) for i in range(mid, rend)]
    st.sh_rec = [rec(i) for i in range(rend, after)]
    st.rec_tk = st.roll_tk = st.sh_tk = None
    for i in range(before):
        for off in REC_NODES:
            h = u32(data + i * REC_SIZE + off)
            if h and (h & 0x3FFFF) != 0x3FFFF:
                st.pack_nodes.append(h)
    for i in range(before, mid):
        for off in REC_NODES:
            h = u32(data + i * REC_SIZE + off)
            if h and (h & 0x3FFFF) != 0x3FFFF:
                st.limb_nodes.append(h)
    log.info(f"limb jet records {before}->{after}: {len(st.limb_nodes)} limb nodes, "
             f"{len(st.pack_nodes)} backpack nodes")
def builder_before(st, cap, node):
    cap = addr(cap)
    if st.in_refresh and not st.building and cap:
        st.effect = u64(cap)
ADOPT_QUIET = 0.6
ADOPT_CACHES = ("arm_h", "chest_h", "spine_h", "finger_h", "rt_j", "tool_h", "sim_nodes", "body_joints",
                "torso_joints", "body_joints_root", "torso_joints_root", "sh_at", "model_root")
def _is_local_player(root):
    import nmspy.data.types as nms_
    from nmspy.data.basic_types import TkHandle as TkH_
    n_, prev = root, ""
    for _ in range(8):
        o_ = TkH_()
        nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(n_))
        if not o_.lookupInt or o_.lookup == 0x3FFFF:
            return False
        n_ = o_.lookupInt
        x = nms_.Engine.GetNodeName(_tk(n_))
        nm = x.decode(errors="replace") if isinstance(x, bytes) else str(x or "")
        if nm == "Simulation-Root":
            return prev == "Player"
        prev = nm
    return False
def _adopt(st, this):
    now = time.perf_counter()
    if getattr(st, "root_seen", None) is None:
        st.root_seen = now
    quiet = now - getattr(st, "comp_seen", 0.0) > ADOPT_QUIET
    lost = now - st.root_seen > 1.0
    seen = st.__dict__.setdefault("comps_seen", {})
    if this not in seen and len(seen) < 40:
        try:
            r_ = player_root(this)
            seen[this] = True
            log.info(f"player component 0x{this:X}: model {('0x%X' % r_) if r_ else None}, local "
                     f"{_is_local_player(r_) if r_ else '-'}, ours 0x{st.component or 0:X} "
                     f"(quiet {quiet}, model lost {lost}, node +0x50C 0x{u32(this + 0x50C):X} "
                     f"{node_name(u32(this + 0x50C))})")
        except Exception as e:
            seen[this] = True
            log.info(f"player component 0x{this:X}: {e!r}")
    nxt = st.__dict__.setdefault("adopt_next", {})
    if not isinstance(nxt, dict):
        nxt = st.adopt_next = {}
    if not (quiet or lost) or now < nxt.get(this, 0.0):
        return False
    nxt[this] = now + 0.25
    try:
        r = player_root(this)
        if not r or not _is_local_player(r):
            return False
    except Exception:
        return False
    log.info(f"player component changed 0x{st.component or 0:X} -> 0x{this:X} (appearance change?): "
             f"taking over, rebuilding the limb jets")
    st.component = this
    for a in ADOPT_CACHES:
        setattr(st, a, None)
    st.arm_base, st.arm_last = {}, {}
    st.root_seen = now
    st.rebuild = True
    st.body_diag_at = now + 3.0
    return True
def update(st, this):
    this = addr(this)
    if not this:
        return
    if this != st.component and not (st.component and _adopt(st, this)):
        return
    st.comp_seen = time.perf_counter()
    try:
        if getattr(st, "player", None):
            _cruise_advance(st, st.player)
    except Exception:
        if "cruise_advance" not in st.errors:
            st.errors.add("cruise_advance")
            log.exception("the cruise's advance failed (repeats not logged)")
    try:
        _space_roll(st, getattr(st, "player", None))
    except Exception:
        if "space_roll" not in st.errors:
            st.errors.add("space_roll")
            log.exception("the space roll failed (repeats not logged)")
    try:
        _water_vel_hold(st)
    except Exception:
        if "water_vel" not in st.errors:
            st.errors.add("water_vel")
            log.exception("the water velocity hold failed (repeats not logged)")
    try:
        _cross_hold(st, "update")
    except Exception:
        if "cross_hold" not in st.errors:
            st.errors.add("cross_hold")
            log.exception("crossing hold failed (repeats not logged)")
    try:
        _warp_request(st)
        _dock_request(st)
    except Exception as e:
        if "quick_action" not in st.errors:
            st.errors.add("quick_action")
            log.info(f"quick action failed {e!r}")
    try:
        _nav_export(st)
    except Exception as e:
        if "nav_export" not in st.errors:
            st.errors.add("nav_export")
            log.info(f"nav export failed {e!r}")
    try:
        _map_export(st)
    except Exception as e:
        if "map_export" not in st.errors:
            st.errors.add("map_export")
            log.info(f"map export failed {e!r}")
    try:
        _names_export(st)
    except Exception as e:
        if "names_export" not in st.errors:
            st.errors.add("names_export")
            log.info(f"weapon names export failed {e!r}")
    if st.comp_seen >= getattr(st, "root_check", 0.0):
        st.root_check = st.comp_seen + 0.5
        model_watch(st, this)
        try:
            _fit_feet(st)
        except Exception as e:
            if "fit_feet" not in st.errors:
                st.errors.add("fit_feet")
                log.info(f"feet fit failed {e!r}")
    if getattr(st, "body_diag_at", None) and st.comp_seen >= st.body_diag_at:
        st.body_diag_at = None
        body_diag(st)
    if _GAME is not None:
        try:
            _struct.pack_into("<dQ", _GAME, 0, st.comp_seen, this)
        except Exception:
            pass
    now = time.perf_counter()
    if now >= getattr(st, "reader_check", 0.0):
        st.reader_check = now + 1.0
        _ensure_reader()
    if not hasattr(st, "limb_nodes") or (getattr(st, "rebuild", False) and _flag.get("read")
                                         and not _flag["want"] and _steer() is None):
        st.rebuild = False
        st.limb_nodes, st.limb_tk = [], []
        _refresh(st.component)
    want = _flag["want"]
    st.want = want
    if want != st.applied:
        st.applied = want
    if not st.limb_tk and st.limb_nodes:
        st.limb_tk = [_tk(h) for h in st.limb_nodes]
    if not getattr(st, "pack_tk", None) and getattr(st, "pack_nodes", None):
        st.pack_tk = [_tk(h) for h in st.pack_nodes]
    act = nms().Engine.SetNodeActivation
    now = time.perf_counter()
    sp = bool(_key(0x20) & 0x8000)
    if sp and not getattr(st, "sp_down", False):
        if now - getattr(st, "sp_release", -9.0) < 0.35 and now - _flag.get("alive_t", -99.0) < 3.0:
            st.prov_until = now + 0.5
    elif not sp and getattr(st, "sp_down", False):
        st.sp_release = now
    st.sp_down = sp
    if not want and now < getattr(st, "prov_until", 0.0):
        for h in getattr(st, "pack_tk", ()):
            act(h, False)
        st.prov_hidden = True
    elif getattr(st, "prov_hidden", False) and not want:
        st.prov_hidden = False
        for h in getattr(st, "pack_tk", ()):
            act(h, True)
    burner = want and getattr(st, "burner", False)
    if want != st.shown:
        st.want_t = now
    if want:
        for h in getattr(st, "pack_tk", ()):
            act(h, burner)
        if not st.shown:
            for h in st.limb_tk:
                act(h, True)
    else:
        fading = (now - getattr(st, "want_t", -9.0) < 1.5 and getattr(st, "player", None)
                  and getattr(st, "side_gone", None) is not None
                  and not all(_flame_out(st, i_, now) for i_ in range(4)))
        for h in st.limb_tk:
            act(h, bool(fading))
        if st.shown:
            for h in getattr(st, "pack_tk", ()):
                act(h, True)
    st.shown = want
    _water_jets(st, want)
    _pack_share(st, want)
    _si_update(now)
    kd = lambda vk: 1 if _key(vk) & 0x8000 else 0
    kf_, ks_, kv_ = kd(0x57) - kd(0x53), kd(0x44) - kd(0x41), kd(0x52) - kd(0x46)
    r = getattr(st, "roll", 0.0)
    cut = getattr(st, "jet_cut", None)
    if not want:
        new = None
    elif r <= -JET_CUT_ROLL or (cut == "L" and r < -JET_BACK_ROLL):
        new = "L"
    elif r >= JET_CUT_ROLL or (cut == "R" and r > JET_BACK_ROLL):
        new = "R"
    elif ks_ and not kf_:
        new = "R" if ks_ > 0 else "L"
    elif kv_ < 0 and not kf_ and not ks_:
        new = "H"
    elif kf_ < 0 and not ks_:
        new = "F"
    else:
        new = None
    now_ = time.perf_counter()
    if new != getattr(st, "jet_pending", None):
        st.jet_pending, st.jet_pending_t = new, now_
    side = cut
    roll_driven = new in ("L", "R") and abs(r) >= JET_CUT_ROLL
    if new != cut and (roll_driven or (cut in ("L", "R") and new is None and abs(r) < JET_BACK_ROLL)):
        side = new
    elif new != cut and now_ - st.jet_pending_t >= JET_DEBOUNCE:
        side = new
    recs = getattr(st, "limb_rec", None)
    if recs and len(recs) == 4:
        if getattr(st, "rec_tk", None) is None:
            st.rec_tk = [[_tk(h) for h in hs_] for hs_ in recs]
        off = JET_OFF.get(side, ())
        if want and side != cut:
            for i_, tks in enumerate(st.rec_tk):
                for h in tks:
                    act(h, i_ not in off or not _flame_out(st, i_, now_))
        elif want and off:
            for i_ in off:
                for h in st.rec_tk[i_]:
                    act(h, not _flame_out(st, i_, now_))
    if not want:
        side = None
    st.jet_cut = side
    _fuel(st, want)
    _side_jets(st, want)
    try:
        _merge_feet(st, want)
    except Exception:
        if "merge_feet" not in st.errors:
            st.errors.add("merge_feet")
            log.exception("merging the foot flames failed (repeats not logged)")
    _shoulder_jets(st, want)
    _roll_bursts(st, want)
    pose(st, this, want)
    try:
        _water_splash(st, want)
    except Exception:
        st.splash_dead = True
        if "water_splash" not in st.errors:
            st.errors.add("water_splash")
            log.exception("the water splash failed -- off until a reload (repeats not logged)")
SPLASH = False
SPLASH_FX = (("NOMADWATER", 1.0, 0.0), ("NOMADWATER", 1.6, 20.0))
SPLASH_MIN_SPEED = 4.0
SPLASH_UP = 1.3
SPLASH_LINGER = 0.3
_PM_OFF = 0x4DED20
_pm_add = CFUNCTYPE(c_uint64, c_void_p, c_void_p, c_void_p, c_void_p)(BASE + 0x221770)
_pm_retire = CFUNCTYPE(c_bool, c_void_p, c_void_p)(BASE + 0x141BE20)
_node_world = CFUNCTYPE(None, c_uint32, c_void_p)(BASE + 0x2C533C0)
def _splash_mat(st, pos, up, scale=1.0):
    buf = getattr(st, "splash_buf", None)
    if buf is None:
        buf = st.splash_buf = (ctypes.c_ubyte * 96)()
    a = (ctypes.addressof(buf) + 15) & ~15
    r, n = _norm(_cross(up, [0.0, 0.0, 1.0]))
    if n < 0.1:
        r, _ = _norm(_cross(up, [1.0, 0.0, 0.0]))
    at = _cross(r, up)
    k = scale
    f = (ctypes.c_float * 16).from_address(a)
    for i, v in enumerate((r[0] * k, r[1] * k, r[2] * k, 0.0, up[0] * k, up[1] * k, up[2] * k, 0.0,
                           at[0] * k, at[1] * k, at[2] * k, 0.0, pos[0], pos[1], pos[2], 1.0)):
        f[i] = v
    return a
def _splash_retire(st):
    inst = getattr(st, "splash_inst", None)
    st.splash_inst, st.splash_cur = None, None
    if inst is None:
        return
    mgr = c_uint64.from_address(BASE + CAM_DATA).value
    if mgr:
        _pm_retire(mgr + _PM_OFF, ctypes.addressof(inst))
def _splash_pick(speed, test):
    if test:
        w = test.split()
        if w:
            try:
                return w[0].upper()[:15], float(w[1]) if len(w) > 1 else 1.0
            except ValueError:
                return w[0].upper()[:15], 1.0
    pick = SPLASH_FX[0]
    for fx in SPLASH_FX:
        if speed >= fx[2]:
            pick = fx
    return pick[0], pick[1]
def _water_splash(st, want):
    if not SPLASH or getattr(st, "splash_dead", False):
        return
    now = time.perf_counter()
    thr = _throttle()
    pl = getattr(st, "player", None)
    speed = thr[1] if thr is not None else 0.0
    skim = bool(thr is not None and thr[4] & THR_SKIM and speed >= SPLASH_MIN_SPEED)
    if skim:
        st.splash_seen = now
    on = bool(pl and want and (skim or now - getattr(st, "splash_seen", -99.0) < SPLASH_LINGER))
    inst = getattr(st, "splash_inst", None)
    h = ctypes.c_uint32.from_address(ctypes.addressof(inst)).value if inst is not None else 0
    if inst is not None and not _node_matrix(h):
        st.splash_inst, inst, h = None, None, 0
    if not on:
        if inst is not None:
            _splash_retire(st)
        return
    fx, scale = _splash_pick(speed, None)
    if inst is not None and getattr(st, "splash_cur", None) != (fx, scale):
        _splash_retire(st)
        inst, h = None, 0
    pos, up = _v(pl + 0x360), _norm(_v(pl + 0x320))[0]
    if not _finite(pos) or not _finite(up):
        return
    mat = _splash_mat(st, [pos[i] + up[i] * SPLASH_UP for i in range(3)], up, scale)
    if inst is None:
        mgr = c_uint64.from_address(BASE + CAM_DATA).value
        if not mgr:
            return
        res = (ctypes.c_ubyte * 32)()
        st.splash_id = (ctypes.c_char * 16).from_buffer_copy(fx.encode("ascii").ljust(16, bytes(1)))
        _pm_add(mgr + _PM_OFF, ctypes.addressof(res), ctypes.addressof(st.splash_id), mat)
        h = ctypes.c_uint32.from_address(ctypes.addressof(res)).value
        if not _node_matrix(h):
            log.info(f"water splash: {fx} gave no node -- splash off")
            st.splash_dead = True
            return
        if getattr(st, "splash_logged", None) != fx:
            st.splash_logged = fx
            log.info(f"water splash: {fx} x{scale:g} spawned, node {h:#x}")
        st.splash_inst, inst, st.splash_cur = res, res, (fx, scale)
    _node_world(h, mat)
FUEL = 0x3524
FUEL_LEARN = 2
try:
    import mmap as _mmap_jet
    _JET = _mmap_jet.mmap(-1, 32, tagname="IronManFlightJet")
except Exception:
    _JET = None
ROLL_ROWS = (0x1E0, 0x1F0)
try:
    _ROLL = _mmap_jet.mmap(-1, 64, tagname="IronManFlightRoll")
except Exception:
    _ROLL = None
try:
    _PACK = _mmap_jet.mmap(-1, 32, tagname="IronManFlightPack")
except Exception:
    _PACK = None
PACK_UP = 0.3
def _pack_share(st, want):
    if _PACK is None or not want:
        return
    tks = getattr(st, "pack_tk", None)
    if not tks:
        return
    try:
        import nmspy.data.basic_types as bt_
        m_ = getattr(st, "pack_m", None)
        if m_ is None:
            m_ = st.pack_m = bt_.cTkMatrix34()
        mr_ = getattr(st, "pack_mr", None)
        if mr_ is None:
            mr_ = st.pack_mr = bt_.cTkMatrix34()
        root_ = u32(st.player + 0xE0) if getattr(st, "player", None) else 0
        lr_ = _node_matrix(root_) if root_ else None
        if not lr_:
            return
        nms().Engine.GetNodeAbsoluteTransMatrix(tks[0], ctypes.byref(m_))
        nms().Engine.GetNodeAbsoluteTransMatrix(_tk(root_), ctypes.byref(mr_))
        r_ = F16.from_address(lr_)
        up_ = _norm(list(r_[4:7]))[0]
        k_ = PACK_UP
        p_ = (r_[12] + m_.pos.x - mr_.pos.x + up_[0] * k_, r_[13] + m_.pos.y - mr_.pos.y + up_[1] * k_,
              r_[14] + m_.pos.z - mr_.pos.z + up_[2] * k_)
        if _finite(p_):
            _struct.pack_into("<4d", _PACK, 0, time.perf_counter(), *p_)
    except Exception:
        pass
WATER_JETS = True
SURFACE_FLAG = 0x576D
def _water_jets(st, want):
    if not WATER_JETS or not want or not getattr(st, "in_water", False):
        return
    pl, comp = getattr(st, "player", None), getattr(st, "component", None)
    if not pl or not comp:
        return
    try:
        if ctypes.c_uint32.from_address(comp + 0x214).value in WATER_STATES:
            f_ = ctypes.c_ubyte.from_address(pl + SURFACE_FLAG)
            if f_.value == 1:
                f_.value = 0
    except Exception:
        pass
WATER_VEL_HOLD = True
def _water_vel_hold(st):
    if not WATER_VEL_HOLD or _JET is None or not getattr(st, "in_water", False):
        return
    s_ = _steer()
    if s_ is None or s_[3] is None or _cruise_on():
        return
    va = _struct.unpack_from("<Q", _JET, 16)[0]
    if not va:
        return
    if getattr(st, "wvh_va", None) != va:
        if not _writable(va, 12):
            return
        st.wvh_va = va
    v = s_[3]
    sp = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if not math.isfinite(sp):
        return
    k = PHYS_LIMIT / sp if sp > PHYS_LIMIT else 1.0
    f = (ctypes.c_float * 3).from_address(va)
    f[0], f[1], f[2] = v[0] * k, v[1] * k, v[2] * k
def _space_roll(st, player):
    if _ROLL is None or not player:
        return
    now = time.perf_counter()
    last = getattr(st, "roll_last", None)
    st.roll_last = now
    t_, rate, ax, ay, az = _struct.unpack_from("<5d", _ROLL, 0)
    if now - t_ > 0.15:
        return
    _ROLL[40:48] = _struct.pack("<d", now)
    if last is None or abs(rate) < 1e-5:
        return
    n_ = math.sqrt(ax * ax + ay * ay + az * az)
    if not 0.5 < n_ < 2.0:
        return
    k = (ax / n_, ay / n_, az / n_)
    a_ = rate * min(0.05, now - last)
    c_, s_ = math.cos(a_), math.sin(a_)
    for off in ROLL_ROWS:
        f = (ctypes.c_float * 3).from_address(player + off)
        r = (f[0], f[1], f[2])
        kr = k[0] * r[0] + k[1] * r[1] + k[2] * r[2]
        cx = (k[1] * r[2] - k[2] * r[1], k[2] * r[0] - k[0] * r[2], k[0] * r[1] - k[1] * r[0])
        o = [r[i] * c_ + cx[i] * s_ + k[i] * kr * (1.0 - c_) for i in range(3)]
        if all(math.isfinite(x) for x in o):
            f[0], f[1], f[2] = o
def _fuel(st, want):
    pl = getattr(st, "player", None)
    if not want or not pl:
        st.fuel_w = None
        return
    try:
        f = c_float.from_address(pl + FUEL)
        v = f.value
        if not (math.isfinite(v) and 0.0 <= v <= 1000.0):
            return
        if getattr(st, "fuel_learn", 0) != FUEL_LEARN:
            st.fuel_learn, st.fuel_full = FUEL_LEARN, max(0.5, v - 0.05)
        w = getattr(st, "fuel_w", None)
        if w is not None and w - v > 1e-4 and _JET is not None:
            _JET[0:8] = _struct.pack("<d", time.perf_counter())
        st.fuel_full = max(st.fuel_full, v)
        if v < st.fuel_full:
            f.value = st.fuel_full
        st.fuel_w = max(v, st.fuel_full)
    except Exception:
        pass
ROLL_JET_TIME = 0.6
ROLL_JETS = {-1: {0: -1, 3: 1},
             1: {1: -1, 2: 1}}
ROLL_GROW = (1.3, 1.9, 1.3)
ROLL_POP, ROLL_FADE = 0.06, 0.2
SIDE_JET_TIME = 0.12
BRAKE_JET_TIME = 0.15
SIDE_FADE_TIME = 0.12
SIDE_SMOKE_LINGER = 0.6
DROP_JET_SIZE = 0.25
FLAME_IGNITE_TIME = 0.07
FLAME_OUT_TIME = 0.1
ROLL_FLAME_OUT = 0.05
HAND_IDLE_DELAY = 0.2
HAND_ALIGN_IN, HAND_ALIGN_OUT = 0.6, 0.25
def _cd(x, v, tgt, tc, dt):
    w = 2.15 / max(1e-3, tc)
    e, q = x - tgt, w * dt
    ex = 1.0 / (1.0 + q + 0.48 * q * q + 0.235 * q * q * q)
    tmp = (v + w * e) * dt
    return tgt + (e + tmp) * ex, (v - w * tmp) * ex
def _flame_out(st, i, now):
    g = (getattr(st, "side_gone", None) or [None] * 4)[i]
    return g is not None and now - g >= SIDE_SMOKE_LINGER
def _side_jets(st, want):
    recs = getattr(st, "limb_rec", None)
    if not recs or len(recs) != 4 or not all(recs):
        return
    now = time.perf_counter()
    dt, st.side_t = min(0.1, now - getattr(st, "side_t", now)), now
    kd = lambda vk: 1 if _key(vk) & 0x8000 else 0
    ks = kd(0x44) - kd(0x41)
    tilt = getattr(st, "tilt", None)
    qs_ = bool(want and ks) and _quarter_side(st)
    k = ks if (want and ks and tilt and getattr(st, "player", None)
               and not ((kd(0x57) and not qs_) or kd(0x52) or kd(0x46))) else 0
    dsc = (want and kd(0x46)
           and not (kd(0x57) or kd(0x53) or kd(0x52) or kd(0x41) or kd(0x44)))
    brk = (want and kd(0x53) and tilt and getattr(st, "player", None)
           and not (kd(0x57) or kd(0x46)))
    bv = getattr(st, "brake_s", 0.0)
    bv += ((1.0 if brk else 0.0) - bv) * (1.0 - math.exp(-dt / BRAKE_JET_TIME))
    if not brk and bv < 0.01:
        bv = 0.0
    st.brake_s = bv
    if k:
        st.side_k = k
    sv, st.side_sv = _cd(getattr(st, "side_s", 0.0), getattr(st, "side_sv", 0.0), 1.0 if k else 0.0,
                         SIDE_JET_TIME, dt)
    sv = min(1.0, max(0.0, sv))
    if not k and sv < 0.01:
        sv, st.side_sv = 0.0, 0.0
    st.side_s = sv
    moving = any(kd(vk) for vk in (0x57, 0x41, 0x53, 0x44, 0x52, 0x46))
    if not want or moving:
        st.idle_t0 = None
    elif getattr(st, "idle_t0", None) is None:
        st.idle_t0 = now
    idle = st.idle_t0 is not None and now - st.idle_t0 >= HAND_IDLE_DELAY
    turn_ = JET_TURN.get(st.jet_cut, ()) if want and not k and not dsc else ()
    tv = getattr(st, "turn_v", None) or [0.0] * 4
    tvv = getattr(st, "turn_vv", None) or [0.0] * 4
    for i in range(4):
        tv[i], tvv[i] = _cd(tv[i], tvv[i], 1.0 if i in turn_ else 0.0, TURN_JET_TIME, dt)
        tv[i] = min(1.0, max(0.0, tv[i]))
        if i not in turn_ and tv[i] < 0.01:
            tv[i], tvv[i] = 0.0, 0.0
    st.turn_v, st.turn_vv = tv, tvv
    hv, st.hand_av = _cd(getattr(st, "hand_align", 0.0), getattr(st, "hand_av", 0.0), 1.0 if idle else 0.0,
                         HAND_ALIGN_IN if idle else HAND_ALIGN_OUT, dt)
    hv = min(1.0, max(0.0, hv))
    if not idle and hv < 0.01:
        hv, st.hand_av = 0.0, 0.0
    st.hand_align = hv
    thr_ = _throttle()
    if thr_ is not None and not (want and _quarter_live(st, now)):
        thr_ = None
    space_ = bool(getattr(st, "space_on", False) or getattr(st, "tilt_space", False))
    gsz = _flame_size(thr_, moving, bool(kd(0x53) or kd(0x52)) or now - getattr(st, "want_t", -9.0) < FLAME_FULL_IGNITE
                      or bool(getattr(st, "in_water", False)), space_)
    st.flame_size = gsz
    drawn_ = getattr(st, "tilt", None) is not None and 0.0 <= now - getattr(st, "drawn_t", -99.0) < QUARTER_DRAWN
    qa = getattr(st, "qh_w", 0.0) if want and drawn_ and not space_ else 0.0
    palm_aim = [0.0, 0.0]
    if qa > 0.0:
        fe_ = getattr(st, "fp_e", 0.0)
        fa_ = getattr(st, "fp_arms", ()) or ()
        palm_aim = [qa * ((1.0 - fe_) if sd_ in fa_ else 1.0) for sd_ in "lr"]
    orig = getattr(st, "side_orig", None)
    if orig is None or getattr(st, "side_recs", None) is not recs:
        orig, st.side_recs = {}, recs
    turned = getattr(st, "side_turned", set())
    fade = getattr(st, "side_fade", None) or [1.0] * 4
    gone = getattr(st, "side_gone", None) or [None] * 4
    keep, push, ws, foot_y = [], (), None, None
    palm_n = [None, None]
    if any(palm_aim):
        for i_, sd_ in enumerate("lr"):
            if palm_aim[i_] > 0.0:
                try:
                    palm_n[i_] = _palm_world(st, sd_)
                except Exception:
                    palm_n[i_] = None
        if not any(palm_n):
            palm_aim = [0.0, 0.0]
    if hv > 0.0 or sv > 0.0 or bv > 0.0 or any(tv) or any(palm_aim):
        import nmspy.data.basic_types as bt_
        ws = []
        for i in range(4):
            m_ = bt_.cTkMatrix34()
            nms().Engine.GetNodeAbsoluteTransMatrix(_tk(recs[i][0]), ctypes.byref(m_))
            ws.append(m_)
        if hv > 0.0:
            foot_y, n_ = _norm([ws[2].up.x + ws[3].up.x, ws[2].up.y + ws[3].up.y, ws[2].up.z + ws[3].up.z])
            if n_ < 1e-3:
                foot_y = None
    if sv > 0.0 and tilt and getattr(st, "player", None):
        up = _body_up(st.player)
        cr, _ = _norm(_cross(tilt[1], up))
        ex = _scale(cr, -getattr(st, "side_k", 1))
        push = getattr(st, "side_push", None)
        if not push or getattr(st, "side_push_k", 0) != st.side_k:
            sd = lambda a_, b_: _dot([ws[a_].pos.x - ws[b_].pos.x, ws[a_].pos.y - ws[b_].pos.y,
                                      ws[a_].pos.z - ws[b_].pos.z], ex)
            push = (0 if sd(0, 1) > 0 else 1, 2 if sd(2, 3) > 0 else 3)
            st.side_push, st.side_push_k = push, st.side_k
    else:
        st.side_push = None
    fv = getattr(st, "side_fv", None) or [0.0] * 4
    off_ = JET_OFF.get(st.jet_cut, ()) if want else ()
    for i in range(4):
        if not want:
            tgt, tc_ = 0.0, FLAME_OUT_TIME
        elif k and push and i not in push and not brk:
            tgt, tc_ = 0.0, SIDE_FADE_TIME
        else:
            tgt = DROP_JET_SIZE if dsc else 0.0 if i in off_ else gsz
            tc_ = FLAME_IGNITE_TIME if now - getattr(st, "want_t", -9.0) < 0.5 else SIDE_FADE_TIME
        fade[i], fv[i] = _cd(fade[i], fv[i], tgt, tc_, dt)
        fade[i] = min(1.1, max(0.0, fade[i]))
        if tgt and abs(fade[i] - tgt) < 0.005 and abs(fv[i]) < 0.05:
            fade[i], fv[i] = tgt, 0.0
        if fade[i] < 0.03:
            gone[i] = gone[i] or now
        else:
            gone[i] = None
    for i in range(4):
        h = recs[i][0]
        m = _node_matrix(h)
        if not m:
            continue
        if h not in orig:
            if h in turned:
                continue
            orig[h] = list(F16.from_address(m))
        aim = []
        if i < 2 and hv > 0.0 and foot_y:
            aim.append((foot_y, hv))
        if i < 2 and palm_aim[i] > 0.0 and palm_n[i]:
            aim.append((_scale(palm_n[i], -1.0), palm_aim[i]))
        if tv[i] > 0.0 and ws:
            o_ = ws[i ^ 1]
            out_, n_ = _norm([ws[i].pos.x - o_.pos.x, ws[i].pos.y - o_.pos.y, ws[i].pos.z - o_.pos.z])
            br_, bn_ = _norm(list((getattr(st, "last_out", None) or [0.0] * 3)[0:3]))
            sgs = getattr(st, "turn_sg", None)
            if sgs is None:
                sgs = st.turn_sg = {}
            if bn_ > 0.5 and n_ > 1e-3:
                if i not in sgs:
                    sgs[i] = 1.0 if _dot(out_, br_) >= 0.0 else -1.0
                out_ = _scale(br_, sgs[i])
            if n_ > 1e-3:
                aim.append((_scale(out_, -1.0), tv[i]))
        elif tv[i] <= 0.0:
            (getattr(st, "turn_sg", None) or {}).pop(i, None)
        if i in push:
            aim.append((_scale(ex, -1.0), sv))
        if i < 2 and bv > 0.0 and tilt and not (k and i in push):
            aim.append((_scale(_norm(tilt[1])[0], -1.0), bv))
        f_ = 1.0 if i in push else max(0.001, fade[i])
        if aim and ws:
            w_ = ws[i]
            Wc = [[w_.right.x, w_.right.y, w_.right.z], [w_.up.x, w_.up.y, w_.up.z], [w_.at.x, w_.at.y, w_.at.z]]
            Lc, L0 = _m3(list(F16.from_address(m))), _m3(orig[h])
            Wci, Lci = _m3inv(Wc), _m3inv(Lc)
            if Wci is None or Lci is None:
                continue
            W0 = _m3mul(_m3mul(L0, Lci), Wc)
            a, _ = _norm(W0[1])
            d = a
            for t, frac in aim:
                d = _slerp_dir(d, t, frac)
            ax, sn = _norm(_cross(a, d))
            th = math.acos(max(-1.0, min(1.0, _dot(a, d))))
            if sn < 1e-6:
                ax, _ = _norm(_cross(a, W0[0]))
            W2 = [_rot(r, ax, math.cos(th), math.sin(th)) for r in W0]
            L2 = _m3mul(_m3mul(W2, Wci), Lc)
            out = list(orig[h])
            for r in range(3):
                out[r * 4:r * 4 + 3] = [x * f_ for x in L2[r]]
            if _finite(out):
                f = F16(*out)
                keep.append(f)
                _set_local(h, ctypes.addressof(f))
                turned.add(h)
        elif f_ < 1.0:
            out = list(orig[h])
            for r in range(3):
                out[r * 4:r * 4 + 3] = [x * f_ for x in out[r * 4:r * 4 + 3]]
            f = F16(*out)
            keep.append(f)
            _set_local(h, ctypes.addressof(f))
            turned.add(h)
        elif h in turned:
            back = F16(*orig[h])
            keep.append(back)
            _set_local(h, ctypes.addressof(back))
            turned.discard(h)
    if getattr(st, "rec_tk", None) is None:
        st.rec_tk = [[_tk(h) for h in hs_] for hs_ in recs]
    act = nms().Engine.SetNodeActivation
    was = getattr(st, "side_active", False)
    if (k and push) or dsc:
        for i, tks in enumerate(st.rec_tk):
            on = i in push or gone[i] is None or now - gone[i] < SIDE_SMOKE_LINGER
            for h in tks:
                act(h, on)
    elif was and want:
        cut_ = JET_OFF.get(st.jet_cut, ())
        for i, tks in enumerate(st.rec_tk):
            for h in tks:
                act(h, i not in cut_ or not _flame_out(st, i, now))
    st.side_active = bool((k and push) or dsc)
    st.dropping = bool(dsc)
    st.side_orig, st.side_turned = orig, turned
    st.side_fade, st.side_gone, st.side_fv = fade, gone, fv
MERGE_TIME = 0.25
MERGE_SIZE = (1.7, 2.4)
def _merge_feet(st, want):
    recs = getattr(st, "limb_rec", None)
    if not recs or len(recs) != 4 or not all(recs):
        return
    now = time.perf_counter()
    dt, st.merge_t = min(0.1, now - getattr(st, "merge_t", now)), now
    on = bool(want and _cruise_on())
    mv, st.merge_vv = _cd(getattr(st, "merge_v", 0.0), getattr(st, "merge_vv", 0.0), 1.0 if on else 0.0,
                          MERGE_TIME, dt)
    mv = min(1.0, max(0.0, mv))
    last = getattr(st, "merge_last", None) or {}
    hs = (recs[2][0], recs[3][0])
    orig = getattr(st, "side_orig", None) or {}
    if mv < 0.005 and not on:
        st.merge_v, st.merge_vv = 0.0, 0.0
        for h in hs:
            m = _node_matrix(h)
            if m and h in last and list(F16.from_address(m)) == last[h] and h in orig:
                back = F16(*orig[h])
                _set_local(h, ctypes.addressof(back))
        st.merge_last = {}
        return
    st.merge_v = mv
    import nmspy.data.basic_types as bt_
    ws = []
    for h in hs:
        m_ = bt_.cTkMatrix34()
        nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
        ws.append(m_)
    mid = [(ws[0].pos.x + ws[1].pos.x) / 2, (ws[0].pos.y + ws[1].pos.y) / 2, (ws[0].pos.z + ws[1].pos.z) / 2]
    for j, h in enumerate(hs):
        m = _node_matrix(h)
        if not m:
            continue
        cur = list(F16.from_address(m))
        base = orig.get(h, cur) if (h in last and cur == last[h]) else cur
        out = list(base)
        if j == 0:
            w_ = ws[0]
            Wc = [[w_.right.x, w_.right.y, w_.right.z], [w_.up.x, w_.up.y, w_.up.z], [w_.at.x, w_.at.y, w_.at.z]]
            Wci = _m3inv(Wc)
            if Wci is None:
                continue
            Pi = _m3mul(Wci, _m3(cur))
            here = [w_.pos.x, w_.pos.y, w_.pos.z]
            dw = [(mid[i] - here[i]) * mv for i in range(3)]
            dl = [sum(dw[k] * Pi[k][i] for k in range(3)) for i in range(3)]
            ga, gl = 1.0 + (MERGE_SIZE[0] - 1.0) * mv, 1.0 + (MERGE_SIZE[1] - 1.0) * mv
            for r in range(3):
                g_ = gl if r == 1 else ga
                out[r * 4:r * 4 + 3] = [x * g_ for x in base[r * 4:r * 4 + 3]]
            for i in range(3):
                out[12 + i] = base[12 + i] + dl[i]
        else:
            g_ = max(0.001, 1.0 - mv)
            for r in range(3):
                out[r * 4:r * 4 + 3] = [x * g_ for x in base[r * 4:r * 4 + 3]]
        if _finite(out):
            f = F16(*out)
            _set_local(h, ctypes.addressof(f))
            last[h] = list(F16.from_address(m))
    st.merge_last = last
SHOULDER_SIZE = 0.8
SHOULDER_UP = 0.13
SHOULDER_IN, SHOULDER_OUT = 0.12, 0.45
def _shoulder_jets(st, want):
    recs, joints = getattr(st, "sh_rec", None), getattr(st, "sh_joints", None)
    if not recs or not joints or len(recs) != len(joints) or not all(recs):
        return
    now = time.perf_counter()
    dt, st.sh_t = min(0.1, now - getattr(st, "sh_t", now)), now
    on_ = want and getattr(st, "dropping", False) and getattr(st, "player", None) and getattr(st, "tilt", None)
    v = getattr(st, "sh_v", 0.0)
    v, st.sh_vv = _cd(v, getattr(st, "sh_vv", 0.0), 1.0 if on_ else 0.0,
                      SHOULDER_IN if on_ else SHOULDER_OUT, dt)
    v = min(1.0, max(0.0, v))
    if v > 0.995 and on_:
        v, st.sh_vv = 1.0, 0.0
    st.sh_v = v
    if v < 0.03 and not on_:
        st.sh_gone = getattr(st, "sh_gone", None) or now
    else:
        st.sh_gone = None
    if getattr(st, "sh_tk", None) is None:
        st.sh_tk = [[_tk(h) for h in hs_] for hs_ in recs]
    show = want and (st.sh_gone is None or now - st.sh_gone < SIDE_SMOKE_LINGER)
    act = nms().Engine.SetNodeActivation
    for tks in st.sh_tk:
        for h in tks:
            act(h, bool(show))
    if not show or not getattr(st, "player", None) or not getattr(st, "tilt", None):
        return
    import nmspy.data.basic_types as bt_
    up = _body_up(st.player)
    cr, _ = _norm(_cross(st.tilt[1], up))
    rows = [cr, _scale(up, -1.0), None]
    rows[2] = _cross(rows[0], rows[1])
    size = 0.5 * SHOULDER_SIZE * max(0.001, v)
    keep = []
    for i, hs_ in enumerate(recs):
        h, m = hs_[0], _node_matrix(hs_[0])
        if not m:
            continue
        pm_ = bt_.cTkMatrix34()
        nms().Engine.GetNodeAbsoluteTransMatrix(_tk(joints[i]), ctypes.byref(pm_))
        P = [[pm_.right.x, pm_.right.y, pm_.right.z], [pm_.up.x, pm_.up.y, pm_.up.z], [pm_.at.x, pm_.at.y, pm_.at.z]]
        Pi = _m3inv(P)
        if Pi is None:
            continue
        js = min(3.0, max(0.3, sum(math.sqrt(_dot(r, r)) for r in P) / 3.0))
        Wd = [_scale(r, size * js) for r in rows]
        L = _m3mul(Wd, Pi)
        at_ = (getattr(st, "sh_at", None) or [None, None])[i]
        if at_ is None:
            continue
        sm_ = bt_.cTkMatrix34()
        nms().Engine.GetNodeAbsoluteTransMatrix(_tk(at_), ctypes.byref(sm_))
        su_ = SHOULDER_UP * js * _body_fit(st)[1]
        off = [sm_.pos.x - pm_.pos.x + up[0] * su_, sm_.pos.y - pm_.pos.y + up[1] * su_,
               sm_.pos.z - pm_.pos.z + up[2] * su_]
        lp = [sum(off[k] * Pi[k][c] for k in range(3)) for c in range(3)]
        out = list(F16.from_address(m))
        for r in range(3):
            out[r * 4:r * 4 + 3] = L[r]
        out[12:15] = lp
        if _finite(out):
            f = F16(*out)
            keep.append(f)
            _set_local(h, ctypes.addressof(f))
def _slerp_dir(a, b, t):
    c = max(-1.0, min(1.0, _dot(a, b)))
    th = math.acos(c)
    if th < 1e-5:
        return list(b)
    ax, sn = _norm(_cross(a, b))
    if sn < 1e-6:
        ax, _ = _norm(_cross(a, [1.0, 0.0, 0.0] if abs(a[0]) < 0.9 else [0.0, 1.0, 0.0]))
    return _rot(a, ax, math.cos(th * t), math.sin(th * t))
def _m3(f):
    return [f[0:3], f[4:7], f[8:11]]
def _m3mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
def _m3inv(a):
    (p, q, r), (s_, t, u), (v, w, x) = a
    det = p * (t * x - u * w) - q * (s_ * x - u * v) + r * (s_ * w - t * v)
    if abs(det) < 1e-12:
        return None
    return [[(t * x - u * w) / det, (r * w - q * x) / det, (q * u - r * t) / det],
            [(u * v - s_ * x) / det, (p * x - r * v) / det, (r * s_ - p * u) / det],
            [(s_ * w - t * v) / det, (q * v - p * w) / det, (p * t - q * s_) / det]]
def _aim_jet(h, local, up, sign):
    import nmspy.data.basic_types as bt_
    m_ = bt_.cTkMatrix34()
    nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
    W = [[m_.right.x, m_.right.y, m_.right.z], [m_.up.x, m_.up.y, m_.up.z], [m_.at.x, m_.at.y, m_.at.z]]
    Wi = _m3inv(W)
    if Wi is None or not all(_finite(r) for r in W):
        return None
    a, _ = _norm(W[1])
    t = _scale(up, -sign)
    ax, sn = _norm(_cross(a, t))
    cs = max(-1.0, min(1.0, _dot(a, t)))
    if sn < 1e-6:
        if cs > 0:
            return None
        ax, _ = _norm(_cross(a, W[0]))
        sn = 0.0
    else:
        sn = math.sqrt(max(0.0, 1.0 - cs * cs))
    W2 = [_rot(r, ax, cs, sn) for r in W]
    L = _m3(local)
    L2 = _m3mul(_m3mul(W2, Wi), L)
    out = list(local)
    for r in range(3):
        out[r * 4:r * 4 + 3] = L2[r]
    return out if _finite(out) else None
def _roll_bursts(st, want):
    recs, rolls = getattr(st, "limb_rec", None), getattr(st, "roll_rec", None)
    if not recs or len(recs) != 4 or not rolls or len(rolls) != 4:
        return
    t = time.perf_counter() - getattr(st, "barrel_t0", -1e9)
    active = want and bool(getattr(st, "player", None)) and 0.0 <= t < ROLL_JET_TIME
    d = 1 if getattr(st, "barrel_dir", 1) > 0 else -1
    turn = ROLL_JETS[d] if active else {}
    env = min(1.0, t / ROLL_POP, max(0.0, (ROLL_JET_TIME - t) / ROLL_FADE)) if active else 0.0
    up = _body_up(st.player) if active else None
    orig = getattr(st, "burst_orig", None)
    if orig is None or getattr(st, "burst_recs", None) is not rolls:
        orig, st.burst_recs = {}, rolls
    turned = getattr(st, "burst_scaled", set())
    keep = []
    for i in range(4):
        if not rolls[i]:
            continue
        h = rolls[i][0]
        m = _node_matrix(h)
        if not m:
            continue
        if h not in orig:
            if h in turned:
                continue
            orig[h] = list(F16.from_address(m))
        if i in turn:
            cur = list(F16.from_address(m))
            aim = _aim_jet(h, cur, up, turn[i]) or cur
            for r in range(3):
                n0 = math.sqrt(sum(x * x for x in orig[h][r * 4:r * 4 + 3]))
                n1 = math.sqrt(sum(x * x for x in aim[r * 4:r * 4 + 3])) or 1.0
                k = n0 * (1.0 + (ROLL_GROW[r] - 1.0) * env) / n1
                aim[r * 4:r * 4 + 3] = [x * k for x in aim[r * 4:r * 4 + 3]]
            if _finite(aim):
                out = F16(*aim)
                keep.append(out)
                _set_local(h, ctypes.addressof(out))
                turned.add(h)
        elif h in turned:
            back = F16(*orig[h])
            keep.append(back)
            _set_local(h, ctypes.addressof(back))
            turned.discard(h)
    if getattr(st, "rec_tk", None) is None:
        st.rec_tk = [[_tk(h) for h in hs_] for hs_ in recs]
    if getattr(st, "roll_tk", None) is None:
        st.roll_tk = [[_tk(h) for h in hs_] for hs_ in rolls]
    act = nms().Engine.SetNodeActivation
    for i in range(4):
        for h in st.roll_tk[i]:
            act(h, i in turn)
    was = getattr(st, "roll_active", False)
    if active:
        now_ = time.perf_counter()
        for i, tks in enumerate(st.rec_tk):
            for h in tks:
                act(h, not _flame_out(st, i, now_))
    elif was and want:
        cut_ = JET_OFF.get(st.jet_cut, ())
        for i, tks in enumerate(st.rec_tk):
            if i not in cut_:
                for h in tks:
                    act(h, True)
    st.roll_active = active
    st.burst_orig, st.burst_scaled = orig, turned
def model_root(start):
    import nmspy.data.types as nms
    from nmspy.data.basic_types import TkHandle
    n = start
    for _ in range(16):
        x = nms.Engine.GetNodeName(_tk(n))
        s = (x.decode(errors="replace") if isinstance(x, bytes) else str(x or "")).upper()
        if s.endswith("PLAYERCHARACTER.SCENE.MBIN"):
            return n
        out = TkHandle()
        nms.Engine.GetNodeParent(ctypes.byref(out), _tk(n))
        if not out.lookupInt or out.lookup == 0x3FFFF:
            break
        n = out.lookupInt
    return None
def player_root(component=None):
    if component:
        r = model_root(u32(component + 0x50C))
        if r:
            return r
    return None
def model_watch(st, this):
    try:
        r = player_root(this)
    except Exception:
        return
    if not r:
        return
    st.root_seen = time.perf_counter()
    old = getattr(st, "model_root", None)
    st.model_root = r
    if old is None or r == old or st.in_refresh:
        return
    log.info(f"model rebuilt (race / appearance change?): root 0x{old:X} -> 0x{r:X}; rebuilding the limb jets")
    st.body_joints = st.torso_joints = None
    st.body_joints_root = st.torso_joints_root = None
    st.sh_at = None
    st.rebuild = True
BODY_DIAG_JOINTS = ("player01_TrajectorySHJnt", "player01_ROOTSHJnt", "player01_head_TopSHJnt",
                    "player01_l_arm_WristSHJnt", "player01_l_leg_KneeSHJnt", "HandFX_L", "FootFX_L")
def body_diag(st):
    try:
        import nmspy.data.basic_types as bt_
        root = player_root(st.component)
        if not root:
            log.info("body: no model root")
            return
        found, _ = find_by_walk(root, list(BODY_DIAG_JOINTS))
        mats = {}
        for nm_, h in found.items():
            m_ = bt_.cTkMatrix34()
            nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
            rows = [[m_.right.x, m_.right.y, m_.right.z], [m_.up.x, m_.up.y, m_.up.z], [m_.at.x, m_.at.y, m_.at.z]]
            mats[nm_] = ([m_.pos.x, m_.pos.y, m_.pos.z], sum(math.sqrt(_dot(r, r)) for r in rows) / 3.0)
        feet = mats.get("player01_TrajectorySHJnt")
        head = mats.get("player01_head_TopSHJnt")
        hips = mats.get("player01_ROOTSHJnt")
        up, _ = _norm(_body_up(st.player)) if getattr(st, "player", None) else (None, 0)
        hgt = lambda a: _dot([a[0][i] - feet[0][i] for i in range(3)], up) if (feet and up) else float("nan")
        log.info(f"body: scale {feet[1] if feet else float('nan'):.3f} (Traveller 1.000), hips {hgt(hips) if hips else float('nan'):.2f} m, "
                 f"head {hgt(head) if head else float('nan'):.2f} m above the feet (Traveller ~1.11 / ~1.75); "
                 f"missing: {[n for n in BODY_DIAG_JOINTS if n not in found] or 'none'}")
        for loc, jn in (("HandFX_L", "player01_l_arm_WristSHJnt"), ("FootFX_L", "player01_l_leg_KneeSHJnt")):
            if loc in mats and jn in mats:
                d = math.sqrt(sum((mats[loc][0][i] - mats[jn][0][i]) ** 2 for i in range(3)))
                log.info(f"body: {loc} {d:.2f} m from its joint, world scale {mats[loc][1]:.3f}")
        recs = getattr(st, "limb_rec", None) or []
        for i, hs_ in enumerate(recs):
            if not hs_:
                continue
            m_ = bt_.cTkMatrix34()
            nms().Engine.GetNodeAbsoluteTransMatrix(_tk(hs_[0]), ctypes.byref(m_))
            sc = math.sqrt(m_.up.x ** 2 + m_.up.y ** 2 + m_.up.z ** 2)
            d = (math.sqrt(sum((p_ - q_) ** 2 for p_, q_ in zip((m_.pos.x, m_.pos.y, m_.pos.z), feet[0])))
                 if feet else float("nan"))
            try:
                act = bool(nms().Engine.GetNodeActivation(_tk(hs_[0])))
            except Exception:
                act = "?"
            log.info(f"body: limb jet {'LRHF'[i] if i < 4 else i} group scale {sc:.3f}, {d:.2f} m from the feet, active {act}")
    except Exception as e:
        log.info(f"body: diagnostic failed {e!r}")
def add_limb_jets(st, this):
    eff = st.effect
    if not eff:
        log.warning("no equipped jetpack effect seen during refresh")
        return
    jets, count = u64(eff + 0x30), u32(eff + 0x38)
    if not jets or count == 0:
        log.warning("equipped effect has no jets")
        return
    root = player_root(this) or u32(this + 0x50C)
    st.keep = []
    built = _build_set(st, this, root, eff, jets)
    st.limb_mid = u32(this + REC_COUNT)
    log.info(f"limb jets: built on {built} limbs")
    fx_ = ROLL_FX
    src = [_thruster(n_) if n_ else None for n_ in fx_]
    entry = next((e_ for e_ in src if e_), None)
    if entry and built == 4:
        jet = (ctypes.c_ubyte * 0x60)()
        for k, (a_, b_) in enumerate(((0x00, 0x20), (0x20, 0x40), (0x40, 0x50))):
            if src[k]:
                ctypes.memmove(ctypes.addressof(jet) + a_, u64(src[k] + 0x30) + a_, b_ - a_)
        st.keep.append(jet)
        n = _build_set(st, this, root, entry, ctypes.addressof(jet))
        log.info(f"roll jets {fx_}: built on {n} limbs")
    st.roll_end = u32(this + REC_COUNT)
    if built == 4:
        st.sh_joints = []
        fx_ = SHOULDER_FX
        se = _thruster(fx_)
        sjet = (ctypes.c_ubyte * 0x60)()
        if se:
            ctypes.memmove(ctypes.addressof(sjet) + 0x40, u64(se + 0x30) + 0x40, 0x10)
        st.keep.append(sjet)
        n = _build_set(st, this, root, se or eff, ctypes.addressof(sjet), SHOULDERS, st.sh_joints)
        st.sh_at = [find_node(root, n_, (TYPE_JOINT, 0)) for n_ in SHOULDER_JOINTS]
        log.info(f"shoulder jets: built on {n} shoulders")
SHOULDERS = [("HandFX_L", "player01_l_arm_WristSHJnt"),
             ("HandFX_R", "player01_r_arm_WristSHJnt")]
SHOULDER_JOINTS = ("player01_l_arm_ShoulderSHJnt", "player01_r_arm_ShoulderSHJnt")
SHOULDER_FX = b"FUSION"
THRUSTERS = 0x6F6C288
ROLL_FX = (None, None, b"PLASMA")
def _thruster(name):
    try:
        tbl = u64(u64(BASE + THRUSTERS) + 0xD5EC8)
        arr, n = u64(tbl + 0x20), u32(tbl + 0x28)
        if not arr or not 0 < n < 200:
            return None
        for k in range(n):
            e = arr + k * 0x70
            if ctypes.string_at(e + 0x20, 16).split(b"\0")[0] == name and u64(e + 0x30) and u32(e + 0x38):
                return e
    except Exception as e_:
        log.warning(f"thruster table: {e_}")
    return None
def _build_set(st, this, root, eff, jets, limbs=LIMBS, joints=None):
    old_parent = u32(this + 0x510)
    built = 0
    st.building = True
    try:
        for lb in limbs:
            loc_name, joint_name = lb[0], lb[1]
            joint = find_node(root, joint_name, (TYPE_JOINT, 0))
            loc = find_node(root, loc_name, (TYPE_LOCATOR, 0))
            if joint is None or loc is None:
                log.warning(f"{loc_name}: joint {joint} locator {loc} not found under root 0x{root:X}")
                continue
            fake_jets = (ctypes.c_ubyte * 0x60)()
            ctypes.memmove(fake_jets, jets, 0x60)
            prefix = (lb[2] if len(lb) > 2 else loc_name.upper()).encode().ljust(16, b"\0")
            ctypes.memmove(ctypes.addressof(fake_jets) + 0x50, prefix, 16)
            fake_eff = (ctypes.c_ubyte * 0x70)()
            ctypes.memmove(fake_eff, eff, 0x70)
            c_uint64.from_address(ctypes.addressof(fake_eff) + 0x30).value = ctypes.addressof(fake_jets)
            c_uint32.from_address(ctypes.addressof(fake_eff) + 0x38).value = 1
            ref = c_uint32(joint)
            offset = (c_float * 4)(0, 0, 0, 0)
            cap = (c_uint64 * 4)(ctypes.addressof(fake_eff), ctypes.addressof(ref), ctypes.addressof(offset), this)
            st.keep += [fake_jets, fake_eff, ref, offset, cap]
            c_uint32.from_address(this + 0x510).value = joint
            _lambda(ctypes.addressof(cap), loc)
            built += 1
            if joints is not None:
                joints.append(joint)
    finally:
        c_uint32.from_address(this + 0x510).value = old_parent
        st.building = False
    return built
POSE_PIN = True
POSE_TILT = True
FWD_MAX, FWD_SPEED = 82.0, 11.0
BACK_MAX, BACK_SPEED = 25.0, 8.0
SIDE_MAX, SIDE_SPEED = 32.0, 9.0
VERT_MAX, VERT_SPEED = 32.0, 9.0
BANK_MAX, BANK_RATE = 45.0, 1.4
TILT_LIMIT = 86.0
TURN_ROLL_MAX = 78.0
ROLL_RELEASE_HZ = 1.1
ROLL_SPRING_HZ = 2.0
MAX_ROLL_RATE = 330.0
MAX_SPIN_RATE = 600.0
TURN_SMOOTH = 0.2
TILT_BLEND = True
TILT_FOLLOW_HZ = 3.5
TURN_DEADBAND = 0.5
TURN_ROLL_RATE = 0.55
FWD_KEY_ROLL = 0.0
FREE_ROLL_RATE = 220.0
FREE_ROLL_ACC = 900.0
FREE_ROLL_HOLD = 2.0
FREE_ROLL_RETURN_HZ = 0.9
ROLL_LIMIT = 82.0
JET_CUT_ROLL = 25.0
JET_BACK_ROLL = 8.0
JET_DEBOUNCE = 0.18
JET_OFF = {"L": (), "R": (), "H": (), "F": ()}
JET_TURN = {"L": (0, 2), "R": (1, 3)}
TURN_JET_TIME = 0.35
LAND_FLARE_DIST = 3.0
LAND_FLARE_TIME = 1.1
CLIMB_PITCH = -3.0
DESCEND_PITCH = -9.0
INPUT_FWD = 45.0
INPUT_VERT = 24.0
INPUT_SIDE = 28.0
STRAFE_YAW = 30.0
STRAFE_PITCH = 10.0
SPACE_FWD_PITCH = 40.0
SPACE_TURN_ROLL = 0.55
SPACE_STRAFE_BANK = 12.0
STRAFE_BANK = 22.0
BANK_SPEED = 8.0
MAX_YAW_RATE = 540.0
TAKEOFF_HEADING_TIME = 0.3
PITCH_MAX = 155.0
MAX_LEAN_RATE = 150.0
RELEASE_SPRING_HZ = 2.2
SPRING_HZ = 1.1
LEAN_PREFILTER = 0.07
VEL_SMOOTH = 0.08
ACC_SMOOTH = 0.12
ACC_LEAD = 0.55
TRAVEL_HEADING = 0.6
TRAVEL_SPEED = 14.0
PIN_TIME = 0.25
PIN_OUT_TIME = 0.4
LEGS_GAIN = 1.5
LEGS_IN, LEGS_LAND_FADE = 0.12, 0.35
MOVE_KEYS = (0x57, 0x41, 0x53, 0x44, 0x52, 0x46)
GLIDE_SPEED = (1.5, 4.0)
ARMS_IN_TIME = 0.15
ARMS_OUT_TIME = 0.42
QUARTER_ARMS_IN = 0.45
QUARTER_ARMS_HOLD = 2.0
COUNTER_MAX = 22.0
FLY_BLEND_Y = 2.2
BACK_BLEND_Y = -1.0
IDLE_Y = -2.15
IDLE_PITCH = -6.0
IDLE_SWAY = (1.6, 0.21, 1.2, 0.13)
WATER_SWAY_FADE = 0.6
NEAR_READY = (8.0, 4.0)
NEAR_RELAX = (3.5, 1.5)
NEAR_MAX_SPEED = 6.0
NEAR_PITCH = -4.0
NEAR_TIME = 0.35
NEAR_REF_RADIUS = 30.0
NEAR_GAME_MAX = 4.0
SIDE_R = 2.2 * math.sqrt(2)
BACK_R = 1.0
DIR_TIME = 0.32
BLEND_R = (2.2, 4.4)
BLEND_R_SPEED = 15.0
ANIM_PITCH = 15.0
HEADING_TIME = 0.12
HEADING_RELEASE_TIME = 0.35
PIVOT = 1.0
NOSE_FLIP_P = 87.0
NOSE_UNFLIP_P = 84.0
NOSE_FLIP_MAX = 175.0
NOSE_SAFE_P = 100.0
NOSE_EASE = (0.3, 0.25)
ROLL_BODY_P = (85.0, 110.0)
NOSE_CAM_UP = 62.0
PITCH_UP = 25.0
NOSE_LOOK_CURVE = 1.0
NOSE_CAM_DOWN = (57.0, 62.0)
VANILLA_BACK_Y = -1.2
BARREL_BODY_AXIS = True
DIVE_TIME = 0.3
VIEW_TRUE = True
VIEW_POLE = (0.10, 0.40)
VIEW_JUMP = 45.0
VIEW_MAX_RATE = 1500.0
VIEW_CONFIRM = 3
VIEW_CONFIRM_DEG = 20.0
VIEW_HOLD = 0.3
CAM_YR_MAX = 10.0
YAW_COMMIT = 150.0
YAW_SPIN = 1.5
YAW_COMMIT_MAX = 359.0
MAX_YAW_ACC = 4500.0
ROLL_TARGET_RATE = 360.0
PATH_ELEV_MAX = 85.0
PATH_ELEV_RATE = 240.0
LEAN_HARD_MAX = 88.0
NODE_MGR = 0x6EFE830
k32.ReadProcessMemory.argtypes = [c_void_p, c_void_p, c_void_p, ctypes.c_size_t, POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = c_bool
k32.GetCurrentProcess.restype = c_void_p
_SELF = k32.GetCurrentProcess()
_raw_key = ctypes.windll.user32.GetAsyncKeyState
_raw_key.restype = ctypes.c_short
import mmap as _mmap_pad
import struct as _struct_pad
try:
    _PAD = _mmap_pad.mmap(-1, 64, tagname="IronManFlightPad")
except Exception:
    _PAD = None
_PAD_FMT = "<dIIiffffIII"
_PAD_IDX = {vk: i for i, vk in enumerate((0x57, 0x41, 0x53, 0x44, 0x52, 0x46))}
THROTTLE_AHEAD_BIT = 0x200
_pad_cache = [-1.0, 0, None, 0, 0.0, 0]
def _pad_read():
    now = time.perf_counter()
    if now - _pad_cache[0] < 0.004 or _PAD is None:
        return _pad_cache
    _pad_cache[0] = now
    try:
        v = _struct_pad.unpack_from(_PAD_FMT, _PAD, 0)
        fresh_ = 0.0 <= now - v[0] < 0.25
        _pad_cache[1] = v[1] if fresh_ else 0
        _pad_cache[2] = (v[2], v[3]) if v[0] > 0.0 else None
        _pad_cache[3] = v[8] if fresh_ else 0
        _pad_cache[4] = v[7] if fresh_ else 0.0
        _pad_cache[5] = v[10] if fresh_ else 0
    except Exception:
        _pad_cache[1], _pad_cache[2], _pad_cache[3], _pad_cache[4], _pad_cache[5] = 0, None, 0, 0.0, 0
    return _pad_cache
PAD_NATIVE_BLOCK = True
PAD_NATIVE = {
    0x1000: ("jump", "interactsecondary"),
    0x2000: ("swap_secondary", "back"),
    0x4000: ("interact", "placemarker", "tagmarker", "reload"),
    0x8000: ("swap_weapon",),
    0x0100: ("alt_fire", "alt_down"),
    0x0200: ("melee", "alt_up"),
    0x0040: ("scan",),
    0x0080: ("zoom", "deconstruct", "Run"),
    0x0001: ("build_menu",),
    0x0002: ("quick_menu",),
    0x0008: ("bin_nextmode", "solarsys_togglemap"),
    0x0004: ("showhud", "bin_prevmode"),
    0x0010: ("inventory", "skipmessage"),
    0x0020: ("pause_menu",),
    0x10000: ("analysis",),
    0x20000: ("fire", "terrain_edit", "binoc_scan"),
}
SI_DIGITAL_DATA = 17
SI_FN = dict(get_ctrls=6, set_handle=9, cur_set=11, layers=15, digital=16)
PAD_ACT = (("jump", 1), ("reload", 2), ("swap_weapon", 4))
_SI = dict(next_t=0.0, blocked=frozenset(), used=None, held=set(), ctx=(0.0, None, False), n_block=0, logged=0.0,
           act_h={})
def _si_fn(vt, i, restype, *args):
    return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *args)(c_uint64.from_address(vt + 8 * i).value)
def _si_ctx_ok(d, ctrl):
    t_, c_, ok_ = _SI["ctx"]
    now = time.perf_counter()
    if c_ == ctrl and now - t_ < 0.05:
        return ok_
    try:
        lay = d["laybuf"]
        ok_ = d["cur_set"](d["it"], ctrl) == d["onfoot"] and d["layers"](d["it"], ctrl, ctypes.addressof(lay)) == 0
    except Exception:
        ok_ = False
    _SI["ctx"] = (now, ctrl, ok_)
    return ok_
def _si_logic(d, ctrl, act, ret):
    b_ = _SI["act_h"].get(act)
    if b_ and _flag.get("want") and (_pad_read()[5] & b_) and _si_ctx_ok(d, ctrl):
        ctypes.c_ubyte.from_address(ret).value = 1
        ctypes.c_ubyte.from_address(ret + 1).value = 1
        return
    if act not in _SI["blocked"] and act not in _SI["held"]:
        return
    _si_block(d, ctrl, act, ctypes.c_ubyte.from_address(ret))
def _si_block(d, ctrl, act, st_):
    if act in _SI["blocked"] and _flag.get("want") and _si_ctx_ok(d, ctrl):
        if st_.value:
            if act not in _SI["held"]:
                _SI["n_block"] += 1
            _SI["held"].add(act)
            st_.value = 0
    elif act in _SI["held"]:
        if st_.value:
            st_.value = 0
        else:
            _SI["held"].discard(act)
def _si_install():
    d = getattr(_sys, "_ironman_si", None)
    if d is not None:
        return d
    sa = ctypes.WinDLL("steam_api64.dll")
    sa.SteamAPI_GetHSteamUser.restype = ctypes.c_int32
    sa.SteamInternal_FindOrCreateUserInterface.restype = ctypes.c_void_p
    sa.SteamInternal_FindOrCreateUserInterface.argtypes = [ctypes.c_int32, ctypes.c_char_p]
    it = sa.SteamInternal_FindOrCreateUserInterface(sa.SteamAPI_GetHSteamUser(), b"SteamInput006")
    if not it:
        return None
    vt = c_uint64.from_address(it).value
    slot = vt + 8 * SI_DIGITAL_DATA
    orig = c_uint64.from_address(slot).value
    sc_ = k32.GetModuleHandleW("steamclient64.dll")
    hmod = ctypes.c_void_p()
    k32.GetModuleHandleExW.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    k32.GetModuleHandleExW.restype = ctypes.c_bool
    if not sc_ or not k32.GetModuleHandleExW(6, ctypes.c_void_p(orig), ctypes.byref(hmod)) or hmod.value != sc_:
        log.info("controller: Steam Input's table isn't where it should be -- the pad's game actions aren't hidden")
        return None
    dd = dict(it=it, vt=vt, slot=slot, orig=orig, laybuf=(ctypes.c_uint64 * 16)(), calls=0, logic=None)
    dd["get_ctrls"] = _si_fn(vt, SI_FN["get_ctrls"], ctypes.c_int, ctypes.c_void_p)
    dd["set_handle"] = _si_fn(vt, SI_FN["set_handle"], ctypes.c_uint64, ctypes.c_char_p)
    dd["cur_set"] = _si_fn(vt, SI_FN["cur_set"], ctypes.c_uint64, ctypes.c_uint64)
    dd["layers"] = _si_fn(vt, SI_FN["layers"], ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p)
    dd["digital"] = _si_fn(vt, SI_FN["digital"], ctypes.c_uint64, ctypes.c_char_p)
    dd["orig_fn"] = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64,
                                     ctypes.c_uint64)(orig)
    dd["onfoot"] = dd["set_handle"](it, b"OnFootControls")
    if not dd["onfoot"] or not dd["digital"](it, b"melee"):
        log.info("controller: Steam Input doesn't know the game's on-foot actions -- the pad's game actions "
                 "aren't hidden")
        return None
    ctrls = (ctypes.c_uint64 * 16)()
    n = dd["get_ctrls"](it, ctypes.addressof(ctrls))
    if n <= 0:
        return False
    buf = (ctypes.c_ubyte * 8)(0xAA, 0xAA, 0xAA, 0xAA)
    r = dd["orig_fn"](it, ctypes.addressof(buf), ctrls[0], dd["digital"](it, b"melee"))
    if r != ctypes.addressof(buf) or buf[0] > 1 or buf[1] > 1:
        log.info(f"controller: Steam Input's GetDigitalActionData isn't as expected ({buf[0]}, {buf[1]}) -- the "
                 "pad's game actions aren't hidden")
        return None
    def thunk(this, ret, ctrl, act, _d=dd):
        r_ = _d["orig_fn"](this, ret, ctrl, act)
        _d["calls"] += 1
        lg_ = _d["logic"]
        if lg_ is not None and ret:
            try:
                lg_(_d, ctrl, act, ret)
            except Exception:
                pass
        return r_
    dd["cb"] = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64,
                                ctypes.c_uint64)(thunk)
    dd["cb_addr"] = ctypes.cast(dd["cb"], ctypes.c_void_p).value
    if not _si_hook(dd, True):
        return None
    _sys._ironman_si = dd
    _si_atexit(dd)
    log.info("controller: the pad's own game actions are hidden while flying (Steam Input)")
    return dd
def _si_atexit(dd):
    if dd.get("atexit"):
        return
    dd["atexit"] = True
    slot, orig = dd["slot"], dd["orig"]
    def _unhook_at_exit(_slot=slot, _orig=orig, _vp=k32.VirtualProtect):
        try:
            o_ = ctypes.c_uint32()
            if _vp(ctypes.c_void_p(_slot), 8, 0x04, ctypes.byref(o_)):
                ctypes.c_uint64.from_address(_slot).value = _orig
                _vp(ctypes.c_void_p(_slot), 8, o_.value, ctypes.byref(ctypes.c_uint32()))
        except Exception:
            pass
    import atexit as _atexit_si
    _atexit_si.register(_unhook_at_exit)
def _si_hook(d, on):
    want_ = d["cb_addr"] if on else d["orig"]
    if c_uint64.from_address(d["slot"]).value == want_:
        return True
    old = ctypes.c_uint32()
    k32.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    k32.VirtualProtect.restype = ctypes.c_bool
    if not k32.VirtualProtect(ctypes.c_void_p(d["slot"]), 8, 0x04, ctypes.byref(old)):
        return False
    c_uint64.from_address(d["slot"]).value = want_
    k32.VirtualProtect(ctypes.c_void_p(d["slot"]), 8, old.value, ctypes.byref(ctypes.c_uint32()))
    return True
def _si_update(now):
    if now < _SI["next_t"]:
        return
    _SI["next_t"] = now + 0.25
    try:
        d = getattr(_sys, "_ironman_si", None)
        if d is not None and "cb_addr" not in d:
            d["cb_addr"] = ctypes.cast(d["cb"], ctypes.c_void_p).value
        if d:
            _si_atexit(d)
        if not PAD_NATIVE_BLOCK:
            if d is not None:
                d["logic"] = None
                _si_hook(d, False)
            return
        if d is not None:
            _si_hook(d, True)
        if d is None:
            if _SI.get("gave_up"):
                return
            d = _si_install()
            if d is None:
                _SI["gave_up"] = True
            if not d:
                return
        d["logic"] = _si_logic
        if not _SI["act_h"]:
            _SI["act_h"] = {h_: bit for h_, bit in ((d["digital"](d["it"], nm.encode()), bit) for nm, bit in PAD_ACT)
                            if h_}
        if not _SI.get("jump"):
            _SI["jump"] = d["digital"](d["it"], b"jump") or None
            _SI["used"] = None
        used = 0
        if _PAD is not None:
            v = _struct_pad.unpack_from("<dIIiffffII", _PAD, 0)
            used = v[9] if abs(time.perf_counter() - v[0]) < 4.0 else 0
        if used != _SI["used"]:
            names = [nm for bit, acts in PAD_NATIVE.items() if used & bit for nm in acts]
            hs = set()
            for nm in names:
                h = d["digital"](d["it"], nm.encode())
                if h:
                    hs.add(h)
            if _SI.get("jump"):
                hs.add(_SI["jump"])
                names = names + ["jump"]
            _SI["blocked"], _SI["used"] = frozenset(hs), used
            log.info(f"controller: while flying the game ignores these pad actions: {', '.join(names) or 'none'}")
        if now - _SI["logged"] > 600.0 and d["calls"]:
            _SI["logged"] = now
            log.info(f"controller: Steam Input digital reads so far {d['calls']}, game presses hidden "
                     f"{_SI['n_block']}")
    except Exception:
        if not _SI.get("err"):
            _SI["err"] = True
            log.exception("controller: hiding the pad's game actions failed (repeats not logged)")
SHM_KEYS, SHM_KFLAGS, SHM_KWINDOW = 120, 126, 127
def _bound(vk):
    i = _PAD_IDX.get(vk)
    if i is not None and _SHM is not None:
        try:
            b = _SHM[SHM_KEYS + i]
        except Exception:
            b = 0
        if b:
            return b
    return vk
_fg_cache = [-1.0, True]
_k32_pid = ctypes.windll.kernel32.GetCurrentProcessId()
def _fg():
    now = time.perf_counter()
    if now - _fg_cache[0] > 0.05:
        _fg_cache[0] = now
        try:
            pid_ = ctypes.c_ulong(0)
            hw_ = ctypes.windll.user32.GetForegroundWindow()
            ctypes.windll.user32.GetWindowThreadProcessId(hw_, ctypes.byref(pid_))
            _fg_cache[1] = bool(hw_) and pid_.value == _k32_pid
        except Exception:
            _fg_cache[1] = True
    return _fg_cache[1]
def _key(vk):
    if not _fg():
        return 0
    k = _raw_key(_bound(vk))
    i = _PAD_IDX.get(vk)
    if i is not None:
        pr_ = _pad_read()
        if pr_[3] & (1 << i):
            return k & ~0x8000
        if not k & 0x8000 and pr_[1] & (1 << i):
            k |= 0x8000
    return k
_rbuf = (ctypes.c_float * 3)()
import mmap as _mmap
import struct as _struct
_SHM_FMT = "<Id3d3d3d3d"
SHM_FLYING, SHM_BURNER, SHM_VEL, SHM_DIVE = 0x80000000, 0x40000000, 0x20000000, 0x10000000
SHM_SPACE = 0x08000000
SHM_WATER = 0x02000000
SHM_CRUISE = 0x04000000
SHM_LEGS = 112
try:
    _SHM = _mmap.mmap(-1, 128, tagname="IronManFlightShared")
except Exception:
    _SHM = None
try:
    _GAME = _mmap.mmap(-1, 16, tagname="IronManFlightGame")
except Exception:
    _GAME = None
try:
    _NAV = _mmap.mmap(-1, 128, tagname="IronManFlightNav2")
except Exception:
    _NAV = None
def _steer():
    if _SHM is None:
        return None
    try:
        v = _struct.unpack_from(_SHM_FMT, _SHM, 0)
    except Exception:
        return None
    if not (v[0] & SHM_FLYING) or time.perf_counter() - v[1] > 0.25:
        return None
    vel = list(v[11:14]) if v[0] & SHM_VEL and _finite(v[11:14]) else None
    return list(v[2:5]), list(v[5:8]), list(v[8:11]), vel, bool(v[0] & SHM_BURNER), bool(v[0] & SHM_DIVE)
def _water_on():
    if _SHM is None:
        return False
    try:
        v = _struct.unpack_from(_SHM_FMT, _SHM, 0)
    except Exception:
        return False
    return bool(v[0] & SHM_FLYING and v[0] & SHM_WATER) and time.perf_counter() - v[1] <= 0.25
def _cruise_on():
    if _SHM is None:
        return False
    try:
        v = _struct.unpack_from(_SHM_FMT, _SHM, 0)
    except Exception:
        return False
    return bool(v[0] & SHM_FLYING and v[0] & SHM_CRUISE) and time.perf_counter() - v[1] <= 0.25
try:
    _THR = _mmap.mmap(-1, 64, tagname="IronManFlightThrottle")
except Exception:
    _THR = None
THR_FMT = "<dffffI"
THR_AHEAD, THR_REVERSING, THR_BRAKING, THR_SPACE = 1, 2, 4, 8
THR_CRUISE, THR_SUSPENDED, THR_FLYING = 16, 64, 128
THR_SKIM = 256
THR_STALE = 0.5
QUARTER_PITCH = 45.0
QUARTER_PITCH_LOW = 8.0
QUARTER_TIME = 0.3
QUARTER_PALM_BACK = 80.0
QUARTER_TILT_MAX = 110.0
QUARTER_X_TIME = 0.1
QUARTER_UNTILT = 0.35
PILOT_MIN = 0.05
FLAME_FULL_IGNITE = 0.5
QUARTER_SETTLE = 0.5
QUARTER_DRAWN = 0.5
_thr_cache = [-1.0, None, 0.0]
def _thr_parse(v, now):
    if not v or len(v) < 6 or not -0.05 <= now - v[0] < THR_STALE:
        return None
    t, spd, fq, pil, fl = v[1], v[2], v[3], v[4], int(v[5])
    if not all(math.isfinite(x) for x in (t, spd, fq, pil)) or not 0.0 < fq < 1.0:
        return None
    t = -1.0 if t < 0.0 else min(1.0, t)
    return t, spd, fq, max(PILOT_MIN, min(1.0, pil)), fl
def _throttle():
    now = time.perf_counter()
    if now - _thr_cache[0] < 0.004:
        return _thr_cache[1]
    _thr_cache[0] = now
    r = None
    if _THR is not None:
        try:
            v_ = _struct.unpack_from(THR_FMT, _THR, 0)
            r = _thr_parse(v_, time.perf_counter())
        except Exception:
            r = None
    if (r is None) != (_thr_cache[1] is None) and now >= _thr_cache[2]:
        _thr_cache[2] = now + 5.0
        log.info(f"throttle block: {'stale or missing -- the poses and flames as before' if r is None else 'live'}"
                 + (f" (first quarter to {r[2]:.2f}, pilot flame {r[3]:.2f})" if r else ""))
    _thr_cache[1] = r
    return r
def _quarter_live(st, now):
    return (bool(getattr(st, "want", False)) and bool(getattr(st, "shown", False))
            and getattr(st, "tilt", None) is not None
            and 0.0 <= now - getattr(st, "drawn_t", -99.0) < QUARTER_DRAWN
            and now - getattr(st, "fly_since", now) >= QUARTER_SETTLE)
QUARTER_IN_WATER = False
def _quarter_on(thr, kf, space, water):
    if thr is None or space or (water and not QUARTER_IN_WATER) or kf <= 0:
        return 0.0
    t, _, fq, _, fl = thr
    if fl & (THR_SPACE | THR_REVERSING | THR_BRAKING) or not fl & THR_AHEAD:
        return 0.0
    return 1.0 if 0.0 < t <= fq else 0.0
def _quarter_side(st):
    thr = _throttle()
    if thr is None:
        return False
    return _quarter_on(thr, 1, bool(thr[4] & THR_SPACE), bool(getattr(st, "in_water", False))) > 0.0
def _quarter_hold(thr, space, water):
    if thr is None or space or (water and not QUARTER_IN_WATER):
        return 0.0
    t, _, fq, _, fl = thr
    if fl & (THR_SPACE | THR_REVERSING) or t < 0.0:
        return 0.0
    return 1.0 if t <= fq else 0.0
def _quarter_x(thr):
    if thr is None:
        return 0.0
    return min(1.0, max(0.0, thr[0] / thr[2]))
def _quarter_pitch(x):
    x = min(1.0, max(0.0, x))
    return QUARTER_PITCH_LOW + (QUARTER_PITCH - QUARTER_PITCH_LOW) * x
def _quarter_palm_dir(B, D):
    b = math.radians(QUARTER_PALM_BACK)
    return _norm(_add(_scale(D, math.sin(b)), _scale(B, -math.cos(b))))[0]
def _quarter_tilt(n, t, a):
    ax, sn = _norm(_cross(n, t))
    if a <= 0.0 or sn < 1e-6:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    ang = min(math.atan2(sn, _dot(n, t)), math.radians(QUARTER_TILT_MAX)) * min(1.0, a)
    return _q_axis(ax, ang)
def _quarter_ease(w, v, tgt, dt):
    w, v = _cd(w, v, tgt, QUARTER_TIME, dt)
    w = min(1.0, max(0.0, w))
    if abs(w - tgt) < 1e-3 and abs(v) < 1e-2:
        w, v = tgt, 0.0
    return w, v
def _quarter_lean(P, w, x):
    return P + (_quarter_pitch(x) - P) * w if w > 0.0 else P
def _flame_size(thr, moving, full, space):
    if thr is None or space or full:
        return 1.0
    t, _, fq, pil, fl = thr
    if t < 0.0 or fl & (THR_SPACE | THR_REVERSING | THR_BRAKING):
        return 1.0
    if t <= 0.0:
        return 1.0 if moving else pil
    if t >= fq:
        return 1.0
    return pil + (1.0 - pil) * _smoothstep(t, 0.0, fq)
def _palm_normal(W, tm, ti, tp, sg):
    f, fn = _norm(_vrow(tm, W))
    s, sn = _norm(_vrow(_add(ti, _scale(tp, -1.0)), W))
    n, nn = _norm(_cross(f, s))
    if fn < 1e-6 or sn < 1e-6 or nn < 1e-3:
        return None
    return _scale(n, sg)
def _palm_world(st, sd):
    hs = getattr(st, "arm_h", None)
    if not hs or sd not in hs or len(hs[sd]) < 7 or not all(hs[sd][3:7]):
        return None
    ms = [_node_matrix(h_) for h_ in hs[sd][4:7]]
    if not _node_matrix(hs[sd][3]) or not all(ms):
        return None
    W = _abs_full(hs[sd][3])
    if W is None:
        return None
    tm, ti, tp = (list(F16.from_address(x))[12:15] for x in ms)
    return _palm_normal(W, tm, ti, tp, PALM_SIGN[sd])
NAV_EVERY = 0.25
try:
    _PLANETS = _mmap.mmap(-1, 512, tagname="IronManFlightPlanets")
except Exception:
    _PLANETS = None
PLANETS_MAX = 12
NAV_OBJ_R = 1500.0
SIM_SOLAR = 0x4CD580 + 0x25E090
SOLAR_PLANETS, PLANET_SIZE = 0x2E30, 0xD9170
PLANET_POS, PLANET_RADIUS = 0xD74D0, 0x3C70 + 0x30
def _planets_sized():
    try:
        data_ = c_uint64.from_address(BASE + CAM_DATA).value
        ss_ = c_uint64.from_address(data_ + SIM_SOLAR).value if data_ else 0
        if not ss_:
            return None
        out = []
        for i in range(6):
            p_ = ss_ + SOLAR_PLANETS + i * PLANET_SIZE
            c_ = list((ctypes.c_float * 3).from_address(p_ + PLANET_POS))
            r_ = ctypes.c_float.from_address(p_ + PLANET_RADIUS).value
            if _finite(c_) and _finite([r_]) and 1000.0 < r_ < 1e6 and max(abs(x) for x in c_) < 1e8:
                out.append((c_, r_))
        return out or None
    except Exception:
        return None
TUNNEL_Y, TUNNEL_Z = 135.0, 350.3
TE_LOCAL = (0.0, 119.6, 350.3)
TUNNEL_FIT = 40.0
NEXUS_BOX = ((-450.0, 450.0), (-1300.0, -500.0), (-700.0, 2300.0))
NEXUS_OFF_AFTER = False
def _in_nexus_box(p):
    b = NEXUS_BOX
    return all(b[i][0] < p[i] < b[i][1] for i in range(3))
def _nexus_inside_node(st):
    for h, nm, act, pos in _nexus_nodes(st):
        if nm.startswith("NEXUS.SCENE"):
            return h
    return None
def _nexus_on(st):
    import nmspy.data.types as nms_
    h = _nexus_inside_node(st)
    if not h:
        log.info("nexus: no inside scene to switch on")
        return
    was = bool(nms_.Engine.GetNodeActivation(_tk(h)))
    if not was:
        nms_.Engine.SetNodeActivation(_tk(h), True)
    if getattr(st, "nexus_keep", None) != h:
        st.nexus_keep, st.nexus_we_on = h, not was
    log.info(f"nexus: inside {'was on' if was else 'switched on'} ({h:08X})")
def _nexus_keep(st):
    import nmspy.data.types as nms_
    h = getattr(st, "nexus_keep", None)
    if not h:
        return
    root = player_root(getattr(st, "component", None))
    if not root:
        return
    if not _node_matrix(h):
        st.nexus_keep = None
        return
    if _in_nexus_box(_abs_pos(root)):
        if not nms_.Engine.GetNodeActivation(_tk(h)):
            nms_.Engine.SetNodeActivation(_tk(h), True)
            log.info("nexus: the game switched its inside off under you: on again")
        return
    if NEXUS_OFF_AFTER and getattr(st, "nexus_we_on", False):
        nms_.Engine.SetNodeActivation(_tk(h), False)
    log.info(f"nexus: out of its inside{' (left on, as after a ship visit)' if not NEXUS_OFF_AFTER else ''}")
    st.nexus_keep, st.nexus_we_on = None, False
def _dock_tunnel(st):
    import nmspy.data.types as nms_
    sn = _sim_nodes(st)
    objs = sn.get("Objects") if sn else None
    inside_ = bool(getattr(st, "nexus_keep", None))
    ext = getattr(st, "dock_ext", None)
    if not (ext and _node_matrix(ext) and (inside_ or nms_.Engine.GetNodeActivation(_tk(ext)))):
        ext = off_ = None
        for c in children(objs) if objs else ():
            if "NEXUSEXTERIOR" in (node_name(c) or "").upper():
                if nms_.Engine.GetNodeActivation(_tk(c)):
                    ext = c
                    break
                if inside_ and off_ is None and max(abs(x) for x in _abs_pos(c)) > 1.0:
                    off_ = c
        ext = ext or off_
        st.dock_ext = ext
        st.dock_nodes = None
    if not ext:
        return None
    dn = getattr(st, "dock_nodes", None)
    if not dn:
        te_ = find_by_walk(ext, ["TeleportEntrance"])[0].get("TeleportEntrance")
        tun = find_by_walk(ext, ["Tunnel"])[0].get("Tunnel")
        inner = None
        for c in children(tun) if tun else ():
            if node_name(c) == "Tunnel":
                inner = c
        dn = st.dock_nodes = (te_, inner or tun) if te_ and (inner or tun) else None
    if not dn:
        return None
    import nmspy.data.basic_types as bt_
    m_ = bt_.cTkMatrix34()
    nms_.Engine.GetNodeAbsoluteTransMatrix(_tk(ext), ctypes.byref(m_))
    R_ = [[m_.right.x, m_.right.y, m_.right.z], [m_.up.x, m_.up.y, m_.up.z], [m_.at.x, m_.at.y, m_.at.z]]
    P_ = [m_.pos.x, m_.pos.y, m_.pos.z]
    te_ = _abs_pos(dn[0])
    pred = [P_[i] + sum(TE_LOCAL[k] * R_[k][i] for k in range(3)) for i in range(3)]
    if math.dist(pred, te_) < TUNNEL_FIT:
        c_ = [P_[i] + TUNNEL_Y * R_[1][i] + TUNNEL_Z * R_[2][i] for i in range(3)]
        ax, n_ = _norm([-R_[2][i] for i in range(3)])
        return (c_, ax) if n_ > 0.5 else None
    if "tunnel_fit" not in st.errors:
        st.errors.add("tunnel_fit")
        log.info(f"tunnel: the exterior's matrix doesn't fit its TeleportEntrance ({math.dist(pred, te_):.1f} m): nodes")
    tt_ = _abs_pos(dn[1])
    ax, n_ = _norm([tt_[i] - te_[i] for i in range(3)])
    return (te_, ax) if n_ > 1.0 else None
try:
    _STATION = _mmap.mmap(-1, 192, tagname="IronManFlightStation")
except Exception:
    _STATION = None
STATION_GEO_VER = 2
STATION_RELEASE_IN = 25.0
STATION_RELEASE_UP = 5.0
def _station_find(st):
    import nmspy.data.types as nms_
    sn = _sim_nodes(st)
    objs = sn.get("Objects") if sn else None
    root = getattr(st, "st_root", None)
    if (root and _node_matrix(root) and nms_.Engine.GetNodeActivation(_tk(root)) and getattr(st, "st_geo", None)
            and getattr(st, "st_ver", None) == STATION_GEO_VER):
        return root, st.st_geo
    if getattr(st, "st_ver", None) != STATION_GEO_VER:
        st.st_ver, st.st_next = STATION_GEO_VER, 0.0
    st.st_root = st.st_geo = None
    now_ = time.perf_counter()
    if now_ < getattr(st, "st_next", 0.0):
        return None
    st.st_next = now_ + 5.0
    for c in children(objs) if objs else ():
        nm = (node_name(c) or "").upper()
        if "/SPACESTATION/SPACESTATION" in nm and nm.endswith(".SCENE.MBIN") and nms_.Engine.GetNodeActivation(_tk(c)):
            O_, R_ = _node_frame(c)
            plug, pads, stack, seen = None, [], [c], 0
            while stack and seen < 60000:
                m_ = stack.pop()
                seen += 1
                n_ = node_name(m_) or ""
                if n_ == "StationPhysicsPlug" and plug is None:
                    pk_ = next((k for k in children(m_) if "COLLISION" in (node_name(k) or "").upper()), m_)
                    plug = _to_local(O_, R_, _abs_pos(pk_))
                elif n_.startswith("LandingPadFloorLOD") and not n_.startswith("SUB"):
                    pads.append(_to_local(O_, R_, _abs_pos(m_)))
                stack.extend(children(m_))
            if plug is None or not pads:
                log.info(f"station {nm.rsplit('/', 1)[-1]}: plug {plug is not None}, {len(pads)} pads: no pull")
                continue
            front = max(p_[2] for p_ in pads)
            rel = [sum(p_[0] for p_ in pads) / len(pads), max(p_[1] for p_ in pads) + STATION_RELEASE_UP,
                   front + STATION_RELEASE_IN]
            st.st_root, st.st_geo = c, (plug, rel)
            log.info(f"station {nm.rsplit('/', 1)[-1]}: plug at {[round(x, 1) for x in plug]}, {len(pads)} pads, "
                     f"let go at {[round(x, 1) for x in rel]} ({seen} nodes)")
            return c, st.st_geo
    return None
def _node_frame(h):
    import nmspy.data.basic_types as bt_
    m_ = bt_.cTkMatrix34()
    nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
    R_ = [_norm([m_.right.x, m_.right.y, m_.right.z])[0], _norm([m_.up.x, m_.up.y, m_.up.z])[0],
          _norm([m_.at.x, m_.at.y, m_.at.z])[0]]
    return [m_.pos.x, m_.pos.y, m_.pos.z], R_
def _to_local(O_, R_, w):
    d = [w[i] - O_[i] for i in range(3)]
    return [_dot(R_[k], d) for k in range(3)]
def _station_export(st, now):
    if _STATION is None:
        return
    f_ = _station_find(st)
    if f_ is None:
        return
    O_, R_ = _node_frame(f_[0])
    plug, rel = f_[1]
    _STATION[0:152] = _struct.pack("<19d", now, *O_, *R_[0], *R_[1], *R_[2], *plug, *rel)
FREIGHTER_EVERY = 3.0
try:
    _FREIGHTER = _mmap.mmap(-1, 192, tagname="IronManFlightFreighter")
except Exception:
    _FREIGHTER = None
def _game_state_node(st):
    gs = getattr(st, "gs_node", None)
    if gs and _node_matrix(gs):
        return gs
    import nmspy.data.types as nms_
    from nmspy.data.basic_types import TkHandle as TkH_
    n_ = player_root(getattr(st, "component", None))
    top = None
    for _ in range(10):
        o_ = TkH_()
        nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(n_))
        if not o_.lookupInt or o_.lookup == 0x3FFFF:
            break
        n_ = top = o_.lookupInt
    if top is None:
        sn = getattr(st, "sim_nodes", None)
        if sn and sn.get("Objects"):
            o_ = TkH_()
            nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(sn["Objects"]))
            top = o_.lookupInt if o_.lookupInt and o_.lookup != 0x3FFFF else None
            for _ in range(4):
                if top is None:
                    break
                o_ = TkH_()
                nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(top))
                if not o_.lookupInt or o_.lookup == 0x3FFFF:
                    break
                top = o_.lookupInt
    for c in children(top) if top else ():
        if node_name(c) == "GameState":
            st.gs_node = c
            return c
    return None
def _freighter_find(st):
    import nmspy.data.types as nms_
    h = getattr(st, "fr_hangar", None)
    if h and _node_matrix(h) and nms_.Engine.GetNodeActivation(_tk(h)) and getattr(st, "fr_geo", None):
        return h, st.fr_geo
    st.fr_hangar = st.fr_geo = None
    now_ = time.perf_counter()
    if now_ < getattr(st, "fr_next", 0.0):
        return None
    st.fr_next = now_ + FREIGHTER_EVERY
    gs = _game_state_node(st)
    if gs is None:
        return None
    me = _abs_pos(player_root(getattr(st, "component", None)))
    best = None
    for f in children(gs):
        if "FREIGHTER" not in (node_name(f) or "").upper() or not nms_.Engine.GetNodeActivation(_tk(f)):
            continue
        for c in children(f):
            if (node_name(c) or "").upper().endswith("/HANGAR.SCENE.MBIN") and nms_.Engine.GetNodeActivation(_tk(c)):
                d = math.dist(_abs_pos(c), me)
                if best is None or d < best[0]:
                    best = (d, c)
    if best is None:
        return None
    h = best[1]
    O_, R_ = _node_frame(h)
    doors = []
    for c in children(h):
        if node_name(c) == "HANGARINTERIOR":
            for k in children(c):
                if "HANGARDOOR" in (node_name(k) or "").upper():
                    doors.append(_to_local(O_, R_, _abs_pos(k)))
    if not doors:
        log.info(f"freighter hangar {h:08X}: no entrance doors found")
        return None
    dz = sum(d_[2] for d_ in doors) / len(doors)
    dy = sum(d_[1] for d_ in doors) / len(doors)
    xs = sorted(d_[0] for d_ in doors)[:3]
    st.fr_hangar, st.fr_geo = h, (dz, dy, xs)
    log.info(f"freighter hangar {h:08X} {best[0]:.0f} m away: {len(doors)} doors at z {dz:.1f} y {dy:.1f} "
             f"x {[round(x, 1) for x in xs]}")
    return h, st.fr_geo
def _freighter_export(st, now):
    if _FREIGHTER is None:
        return
    f_ = _freighter_find(st)
    if f_ is None:
        return
    O_, R_ = _node_frame(f_[0])
    dz, dy, xs = f_[1]
    xs3 = (list(xs) + [0.0, 0.0, 0.0])[:3]
    _FREIGHTER[0:152] = _struct.pack("<19d", now, *O_, *R_[0], *R_[1], *R_[2], dz, dy, float(len(xs)), *xs3)
def _dock_request(st):
    if _NAV is None:
        return
    req = _struct.unpack_from("<I", _NAV, 112)[0]
    if req == getattr(st, "dock_req", None):
        return
    first = getattr(st, "dock_req", None) is None
    st.dock_req = req
    if first:
        return
    r_ = quick_action_live(QA_RECOVERY_SHIP, False)
    log.info(f"dock: recovery starship called ({r_})")
    _NAV[116:124] = _struct.pack("<Ii", req, 1 if r_ else 0)
def _nav_export(st):
    now = time.perf_counter()
    if _NAV is None or now < getattr(st, "nav_t", 0.0):
        return
    st.nav_t = now + NAV_EVERY
    _nexus_keep(st)
    tun = _dock_tunnel(st)
    if tun is not None:
        _NAV[48:104] = _struct.pack("<7d", now, *tun[0], *tun[1])
    _station_export(st, now)
    try:
        _freighter_export(st, now)
    except Exception as e:
        if "freighter_export" not in st.errors:
            st.errors.add("freighter_export")
            log.info(f"freighter export failed {e!r} (repeats not logged)")
    if _space_up() is None:
        return
    root = player_root(getattr(st, "component", None))
    if not root:
        return
    me = _abs_pos(root)
    pls = _planets_sized()
    if pls is None:
        sn = _sim_nodes(st)
        terrain = sn.get("Terrain") if sn else None
        pls = [(_abs_pos(pl), 130048.0) for t in (children(terrain) if terrain else ()) if node_name(t) == "PlanetRoot"
               for pl in children(t)]
    if now >= getattr(st, "nav_obj_t", 0.0):
        st.nav_obj_t = now + 1.0
        st.nav_objs = [(p_, NAV_OBJ_R) for k_, p_ in _live_markers(st) if k_ in (4, 5)]
    best = None
    allp = list(pls) + list(getattr(st, "nav_objs", None) or [])
    for c_, r_ in allp:
        h_ = math.dist(me, c_) - r_
        if best is None or h_ < best[0]:
            best = (h_, c_, r_)
    if _PLANETS is not None and allp:
        allp = allp[:PLANETS_MAX]
        try:
            _PLANETS[0:16 + 32 * len(allp)] = _struct.pack(
                "<dI4x" + "4d" * len(allp), now, len(allp),
                *[x for c_, r_ in allp for x in (c_[0] - me[0], c_[1] - me[1], c_[2] - me[2], r_)])
        except Exception:
            pass
    if best is not None:
        _NAV[0:48] = _struct.pack("<6d", now, best[0], *best[1], best[2])
SPACE_UP_STALE = 1.5
def _space_up():
    if _SHM is None:
        return None
    try:
        v = _struct.unpack_from(_SHM_FMT, _SHM, 0)
    except Exception:
        return None
    if not (v[0] & SHM_FLYING and v[0] & SHM_SPACE) or time.perf_counter() - v[1] > SPACE_UP_STALE:
        return None
    u, n = _norm(list(v[8:11]))
    return u if n > 0.5 and _finite(u) else None
def _body_up(player):
    return _space_up() or _norm(_v(player + 0x320))[0]
def _finite(v):
    return all(math.isfinite(x) for x in v)
_set_local = CFUNCTYPE(None, c_uint32, c_void_p)(BASE + 0x18804C0)
WATER_STATES = (12, 13)
WATER_RECENT = 3.0
WATER_NEAR = 3000.0
WATER_LEVEL_TOL = 3.0
WATER_GROUND = 100.0
WATER_OUT_HOLD = 2.5
WATER_OUT_HEIGHT = 2.0
SPACE_GROUND = None
SPACE_LOOK_PIN = None
SPACE_TSJE_HOVER = 3.0
SPACE_FLY_IN, SPACE_FLY_OUT = 0.2, 0.35
PARAMS = 0x8C0
F16 = ctypes.c_float * 16
def _v(a, n=3):
    return list((ctypes.c_float * n).from_address(a))
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _scale(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]
def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (_scale(a, 1.0 / n), n) if n > 1e-9 else ([0.0, 0.0, 0.0], 0.0)
def _rot(v, k, c, s_):
    kv = _cross(k, v)
    d = _dot(k, v) * (1 - c)
    return [v[i] * c + kv[i] * s_ + k[i] * d for i in range(3)]
def _node_matrix(h):
    slot, gen = h & 0x7FFFF, h >> 19
    if not gen or slot == 0x7FFFF:
        return 0
    mgr = u64(BASE + NODE_MGR)
    if not mgr:
        return 0
    if ctypes.c_uint16.from_address(u64(mgr + 0xF0) + 2 * slot).value != (gen & 0xFFFF):
        return 0
    idx = ctypes.c_int32.from_address(u64(mgr + 0xE8) + 4 * slot).value
    if idx < 0:
        return 0
    return u64(mgr + 0x48) + idx * 0x40
def _smoothstep(x, lo, hi):
    u = min(1.0, max(0.0, (x - lo) / (hi - lo)))
    return u * u * (3 - 2 * u)
def _horiz(v, up):
    return _norm(_add(v, _scale(up, -_dot(v, up))))
def _signed_yaw(a, b, up):
    return math.atan2(_dot(_cross(a, b), up), _dot(a, b))
CAM_DATA = 0x6F6C288
CAM_MGR = 0x92CD50
CAM_MGR_VTABLE = 0x4B19AD0
CAM_MAT = 0x130
_mbuf = (ctypes.c_float * 16)()
_pbuf = c_uint64()
def _view():
    if not k32.ReadProcessMemory(_SELF, BASE + CAM_DATA, ctypes.byref(_pbuf), 8, None) or not _pbuf.value:
        return None
    mgr = _pbuf.value + CAM_MGR
    if not k32.ReadProcessMemory(_SELF, mgr, ctypes.byref(_pbuf), 8, None) or _pbuf.value != BASE + CAM_MGR_VTABLE:
        return None
    if not k32.ReadProcessMemory(_SELF, mgr + CAM_MAT, _mbuf, 64, None):
        return None
    f = list(_mbuf)
    r, b = f[0:3], f[8:11]
    if not (_finite(r) and _finite(b)) or abs(_dot(b, b) - 1) > 0.01 or abs(_dot(r, r) - 1) > 0.01 or abs(_dot(r, b)) > 0.01:
        return None
    return [-b[0], -b[1], -b[2]]
def _cam_frame():
    look = _view()
    if look is None:
        return None
    u = list(_mbuf)[4:7]
    u, n = _norm(_add(u, _scale(look, -_dot(u, look))))
    return (look, u) if n > 0.5 and _finite(u) else None
EXIT_EASE = 0.6
SPACE_GAME_POSE = False
SPACE_BLEND_IN = 2.5
SPACE_BLEND_OUT = 0.6
SPACE_FRAME_TIME = 0.10
def _view_filtered(st, now, dt):
    v = _view()
    if v is not None:
        v, n = _norm(v) if _finite(v) else (None, 0.0)
        if not 0.5 < n < 2.0:
            v = None
    prev = getattr(st, "look", None)
    if v is not None and prev is not None:
        ang = math.degrees(math.acos(max(-1.0, min(1.0, _dot(v, prev)))))
        if ang > max(VIEW_JUMP, VIEW_MAX_RATE * dt):
            pend = getattr(st, "look_pend", None)
            if pend is not None and _dot(v, pend[0]) > math.cos(math.radians(VIEW_CONFIRM_DEG)):
                pend = (v, pend[1] + 1)
            else:
                pend = (v, 1)
            st.look_pend = pend
            if pend[1] < VIEW_CONFIRM:
                v = None
            else:
                st.look_pend = None
                st.look, st.look_t = v, now
                return v, "snap"
        else:
            st.look_pend = None
    if v is None:
        if prev is not None and now - getattr(st, "look_t", now) > VIEW_HOLD:
            st.look = prev = None
        return prev, ("held" if prev is not None else "none")
    st.look, st.look_t = v, now
    return v, ("new" if prev is not None else "snap")
def _view_heading(st, look, up, head, now, dt, status):
    hd, n = _horiz(look, up)
    w = _smoothstep(n, VIEW_POLE[0], VIEW_POLE[1])
    ref = getattr(st, "look_h", None)
    if ref is not None:
        ref, rn = _horiz(ref, up)
        if rn < 0.5:
            ref = None
    if ref is None:
        ref = hd if w > 0.0 else head
    elif n < VIEW_POLE[1] and _dot(hd, ref) < 0.0:
        w = 0.0
    if w > 0.0:
        k = 1.0 - (1.0 - w) ** min(6.0, 60.0 * dt)
        a = _signed_yaw(ref, hd, up) * k
        ref = _rot(ref, up, math.cos(a), math.sin(a))
    st.look_h = ref
    if status == "snap" or n <= VIEW_POLE[0]:
        st.cam_yr_hist = []
        st.cam_yr = 0.0
        st.cv_prev, st.cv_t, st.cv_w = (hd, now, w) if n > VIEW_POLE[0] else (None, None, 0.0)
        return
    if status != "new":
        return
    pcv, pt = getattr(st, "cv_prev", None), getattr(st, "cv_t", None)
    if pcv is not None and pt is not None and now - pt > 1e-4:
        d = _signed_yaw(pcv, hd, up)
        if abs(d) > math.pi / 2:
            d = 0.0
        smp = max(-CAM_YR_MAX, min(CAM_YR_MAX, d / (now - pt))) * min(w, getattr(st, "cv_w", w))
        hist = (getattr(st, "cam_yr_hist", None) or [])[-2:] + [smp]
        st.cam_yr_hist = hist
        st.cam_yr = sorted(hist)[1] if len(hist) == 3 else min(hist, key=abs)
    st.cv_prev, st.cv_t, st.cv_w = hd, now, w
def _free_roll(st, now, dt, flying):
    fwd_ = flying and _key(0x57) & 0x8000 and not _key(0x53) & 0x8000 and not _quarter_side(st)
    k = ((1 if _key(0x44) & 0x8000 else 0) - (1 if _key(0x41) & 0x8000 else 0)) if fwd_ else 0
    ang, rate = getattr(st, "free_roll", 0.0), getattr(st, "free_roll_v", 0.0)
    racc = getattr(st, "free_roll_a", 0.0)
    if k:
        st.free_roll_t = now
        st.free_roll_ret = None
        rate, racc = _cd(rate, racc, k * FREE_ROLL_RATE, FREE_ROLL_RATE / FREE_ROLL_ACC, dt)
    elif now - getattr(st, "free_roll_t", -1e9) < FREE_ROLL_HOLD and flying:
        rate, racc = _cd(rate, racc, 0.0, FREE_ROLL_RATE / FREE_ROLL_ACC, dt)
    else:
        ang = math.remainder(ang, 360.0)
        if getattr(st, "free_roll_ret", None) is None:
            st.free_roll_ret = now
        w = 2 * math.pi * FREE_ROLL_RETURN_HZ * (0.25 + 0.75 * _smoothstep(now - st.free_roll_ret, 0.0, 0.35))
        rate += (-w * w * ang - 2 * w * rate) * dt
        racc = 0.0
        if abs(ang) < 0.3 and abs(rate) < 3.0:
            ang, rate = 0.0, 0.0
    ang += rate * dt
    if not (math.isfinite(ang) and math.isfinite(rate)):
        ang, rate = 0.0, 0.0
    st.free_roll, st.free_roll_v, st.free_roll_a = ang, rate, racc
    return ang
def _pose_reset(st):
    st.lean = None
    st.lean_v = None
    st.tilt = None
    st.head = None
    st.yaw_off = 0.0
    st.pose_pos = None
    st.pose_vel = None
    st.pose_acc = None
    st.roll = 0.0
    st.roll_v = 0.0
    st.lean_loc = None
    st.cv_prev = None
    st.cam_yr = 0.0
    st.pose_fwd = None
    _view_reset(st)
    st.yaw_rate = 0.0
    st.yaw_dir = 0
    st.head_step = 0.0
    st.roll_t = 0.0
    st.free_roll = st.free_roll_v = 0.0
def _view_reset(st):
    st.look = None
    st.look_pend = None
    st.look_h = None
    st.cv_prev, st.cv_t, st.cv_w = None, None, 0.0
    st.cam_yr_hist = []
    st.cam_yr = 0.0
BODY_JOINTS = ("player01_TrajectorySHJnt", "player01_ROOTSHJnt", "player01_spine_01SHJnt", "player01_head_TopSHJnt")
def _joint_tilt(st):
    hs = getattr(st, "body_joints", None)
    if hs is None or getattr(st, "body_joints_root", None) != getattr(st, "component", None):
        try:
            f_, _ = find_by_walk(player_root(getattr(st, "component", None)), BODY_JOINTS)
            hs = st.body_joints = [f_.get(n) for n in BODY_JOINTS]
            st.body_joints_root = getattr(st, "component", None)
        except Exception:
            st.body_joints = [None] * 4
            return None
    try:
        rows = None
        for h in hs[:2]:
            m = _node_matrix(h) if h else 0
            if not m:
                return None
            f = list(F16.from_address(m))
            R = [_norm(f[0:3])[0], _norm(f[4:7])[0], _norm(f[8:11])[0]]
            rows = R if rows is None else [[sum(R[i][k] * rows[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        st.jt_rows = rows
        ref = getattr(st, "jt_ref", None)
        if ref is None or not getattr(st, "space_on", False):
            st.jt_ref = ref = rows
        Rr = [[sum(rows[k][i] * ref[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        st.jt_Rr = Rr
        tr = Rr[0][0] + Rr[1][1] + Rr[2][2]
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
        ax = [Rr[2][1] - Rr[1][2], Rr[0][2] - Rr[2][0], Rr[1][0] - Rr[0][1]]
        an_ = math.sqrt(_dot(ax, ax))
        st.game_tilt = (-ang if ax[0] > 0 else ang) * (abs(ax[0]) / an_ if an_ > 1e-6 else 0.0)
        return ang, ax
    except Exception:
        return None
def _in_root(h, root):
    import nmspy.data.types as nms_
    from nmspy.data.basic_types import TkHandle as TkH_
    pos, rows, n = [0.0, 0.0, 0.0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], h
    for _ in range(24):
        if n == root:
            return pos, rows
        m = _node_matrix(n)
        if not m:
            return None
        f = list(F16.from_address(m))
        R = [f[0:3], f[4:7], f[8:11]]
        pos = [sum(pos[k] * R[k][j] for k in range(3)) + f[12 + j] for j in range(3)]
        rows = [[sum(rows[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        o_ = TkH_()
        nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(n))
        if not o_.lookupInt or o_.lookup == 0x3FFFF:
            return None
        n = o_.lookupInt
    return None
def _spine_axis(st):
    hs = getattr(st, "body_joints", None)
    if not hs or not hs[2] or not hs[3]:
        return None
    root = player_root(getattr(st, "component", None))
    a, b = _in_root(hs[2], root), _in_root(hs[3], root)
    if not a or not b:
        return None
    v, n = _norm([b[0][i] - a[0][i] for i in range(3)])
    return v if n > 0.1 else None
WATER_EXIT_FADE = 1.0
WATER_PITCH_MAX = 88.0
WATER_TORSO_CANCEL = True
TORSO_CANCEL = False
TORSO_JOINTS = ("player01_spine_01SHJnt", "player01_spine_TopSHJnt",
                "player01_l_arm_ClavicleSHJnt", "player01_r_arm_ClavicleSHJnt")
TORSO_PLANET_PITCH = 4.0
SPACE_EXTRA_FADE = 0.35
SPACE_EXTRA_EASE = 0.2
SPACE_EXTRA_RANGE = (-15.0, 70.0)
SPINE_PLANET_PITCH = -12.0
SPACE_LINE_SERVO = True
SPACE_LINE_TARGET = (12.0, 56.0)
SPACE_LINE_GAIN = 1.5
SPACE_LINE_MAX = 85.0
def _drawn_body_line(st):
    bj = getattr(st, "body_joints", None)
    cf_ = _cam_frame()
    if not bj or not bj[1] or not bj[3] or not cf_:
        return None
    a_, b_ = _abs_pos(bj[1]), _abs_pos(bj[3])
    v_, n_ = _norm([b_[i] - a_[i] for i in range(3)])
    if n_ < 0.05 or not _finite(v_):
        return None
    return math.degrees(math.atan2(_dot(v_, cf_[0]), _dot(v_, cf_[1])))
def _space_line_servo(st, in_space, fwd_blend, dt):
    a_ = max(0.0, min(1.0, fwd_blend))
    t0, t1 = getattr(st, "sp_trim0", 0.0), getattr(st, "sp_trim1", 0.0)
    if in_space:
        m_ = _drawn_body_line(st)
        if m_ is not None:
            tgt = SPACE_LINE_TARGET[0] + (SPACE_LINE_TARGET[1] - SPACE_LINE_TARGET[0]) * a_
            e_ = SPACE_LINE_GAIN * (tgt - m_) * min(dt, 0.05)
            t0 = max(-SPACE_LINE_MAX, min(SPACE_LINE_MAX, t0 + e_ * (1.0 - a_)))
            t1 = max(-SPACE_LINE_MAX, min(SPACE_LINE_MAX, t1 + e_ * a_))
            st.sp_line = m_
    st.sp_trim0, st.sp_trim1 = t0, t1
    st.sp_trim = t0 * (1.0 - a_) + t1 * a_
    return st.sp_trim
def _space_torso_extra(st, dt):
    sa_ = _spine_axis(st)
    ext = getattr(st, "sp_extra", 0.0)
    if sa_:
        tgt = max(SPACE_EXTRA_RANGE[0], min(SPACE_EXTRA_RANGE[1],
                                            math.degrees(math.atan2(-sa_[2], sa_[1])) - SPINE_PLANET_PITCH))
        if math.isfinite(tgt):
            ext += (tgt - ext) * (1.0 - math.exp(-dt / SPACE_EXTRA_EASE))
    st.sp_extra = ext
    return ext
def _torso_frame(st):
    hs = getattr(st, "torso_joints", None)
    if hs is None or getattr(st, "torso_joints_root", None) != getattr(st, "component", None):
        try:
            f_, _ = find_by_walk(player_root(getattr(st, "component", None)), TORSO_JOINTS)
            hs = st.torso_joints = [f_.get(n) for n in TORSO_JOINTS]
            st.torso_joints_root = getattr(st, "component", None)
        except Exception:
            st.torso_joints = [None] * 4
            return None
    if not all(hs):
        return None
    root = player_root(getattr(st, "component", None))
    ps = [_in_root(h, root) for h in hs]
    if not all(ps):
        return None
    u, nu = _norm([ps[1][0][i] - ps[0][0][i] for i in range(3)])
    r = [ps[3][0][i] - ps[2][0][i] for i in range(3)]
    r, nr = _norm(_add(r, _scale(u, -_dot(r, u))))
    if nu < 0.05 or nr < 0.05:
        return None
    return [r, u, _cross(r, u)]
def _water_held(st, pos, up):
    if time.perf_counter() - getattr(st, "water_t", -99.0) >= WATER_OUT_HOLD:
        return False
    wp = getattr(st, "water_pt", None)
    if wp is None or not _finite(pos) or not _finite(up):
        return True
    return _dot(_add(pos, _scale(wp, -1.0)), up) <= WATER_OUT_HEIGHT
def _space_tsje(space, sp_fly):
    if not (space and SPACE_TSJE_HOVER):
        return 0.0
    return SPACE_TSJE_HOVER * (1.0 - max(0.0, min(1.0, sp_fly)))
def _sp_fly_step(x, v, fwd, dt):
    t = 1.0 if fwd else 0.0
    x, v = _cd(x, v, t, SPACE_FLY_IN if t > x else SPACE_FLY_OUT, dt)
    x = min(1.0, max(0.0, x))
    if t == 0.0 and x < 0.002:
        x, v = 0.0, 0.0
    return x, v
def _space_fwd_blend(a, sp_fly, space_w):
    if not SPACE_TSJE_HOVER:
        return a
    return a + (sp_fly - a) * _smoothstep(space_w, 0.0, 1.0)
def pose(st, comp, flying):
    jt_ = _joint_tilt(st) if flying else None
    tf_ = _torso_frame(st) if flying else None
    st.torso_cur = tf_
    if (flying and not getattr(st, "space_on", False) and getattr(st, "space_w", 0.0) <= 0.0
            and time.perf_counter() - getattr(st, "water_t", -99.0) > WATER_EXIT_FADE):
        st.planet_t = getattr(st, "planet_t", None) or time.perf_counter()
    else:
        st.planet_t = None
    if tf_ is not None and st.planet_t and time.perf_counter() - st.planet_t > 2.0:
        st.torso_ref = tf_
    if not jt_:
        st.game_tilt = 0.0
    now = time.perf_counter()
    dt = min(0.1, now - getattr(st, "pose_t", now)) or 1e-3
    st.pose_t = now
    player = getattr(st, "player", None)
    lean = getattr(st, "lean", None)
    if not flying and comp:
        prm_ = (ctypes.c_float * 24).from_address(comp + PARAMS)
        if prm_[5] < VANILLA_BACK_Y:
            prm_[4] *= VANILLA_BACK_Y / prm_[5]
            prm_[5] = VANILLA_BACK_Y
    if not flying and getattr(st, "pin", 0.0) < 0.02 and (
            lean is None or (_dot(lean, lean) < 0.04 and _dot(st.lean_v, st.lean_v) < 0.25
                             and abs(getattr(st, "yaw_off", 0.0)) < 0.0015 and abs(getattr(st, "roll", 0.0)) < 0.2)):
        _pose_reset(st)
        return
    if not player:
        return
    up, nu = _norm(_v(player + 0x320))
    if CROSS_POSE_CARRY and now < getattr(st, "x_upkeep", 0.0) and not (flying and _space_up() is not None):
        ru_, rn_ = _norm(_v(player + 0x1E0))
        if rn_ > 0.5 and _finite(ru_):
            up, nu = ru_, rn_
    game_fwd, nf = _norm(_scale(_v(player + 0x330), -1))
    pup = up
    space_on = flying and _space_up() is not None
    st.space_on = space_on
    if space_on and SPACE_GAME_POSE:
        st.tilt_space = True
        _pose_reset(st)
        return
    w_ = getattr(st, "space_w", 0.0)
    if space_on and not getattr(st, "space_fly_prev", False):
        w_ = 1.0
    st.space_fly_prev = flying
    w_ = min(1.0, w_ + dt / SPACE_BLEND_IN) if space_on else max(0.0, w_ - dt / SPACE_BLEND_OUT)
    if (CROSS_POSE_CARRY and flying and not space_on and getattr(st, "space_on_prev", False)
            and getattr(st, "body_axis", None) is not None):
        w_ = 0.0
        st.lean_conv = list(st.body_axis)
        st.nose_preset = True
    st.space_on_prev = space_on
    st.space_w = w_ if flying else 0.0
    sup = None
    if flying and st.space_w > 1e-3:
        cf_b = _cam_frame()
        if cf_b:
            ws_ = _smoothstep(st.space_w, 0.0, 1.0)
            ax_b = _cross(pup, cf_b[1])
            sn_b = math.sqrt(_dot(ax_b, ax_b))
            ang_b = math.atan2(sn_b, _dot(pup, cf_b[1])) * ws_
            if sn_b > 1e-6:
                sup = _norm(_rot(pup, _scale(ax_b, 1.0 / sn_b), math.cos(ang_b), math.sin(ang_b)))[0]
            else:
                sup = list(pup) if _dot(pup, cf_b[1]) > 0 or ws_ < 0.5 else _scale(pup, -1.0)
        else:
            sup = list(pup)
    st.tilt_space = sup is not None
    if sup is not None:
        up = sup
        game_fwd, nf = _horiz(game_fwd, up)
    if flying and nf < 0.5 and _finite(up):
        cf_f = _cam_frame()
        for alt_ in (getattr(st, "head", None), getattr(st, "drawn_head", None), cf_f[0] if cf_f else None,
                     _v(player + 0x310)):
            if alt_ is not None and _finite(alt_):
                g2_, n2_ = _horiz(alt_, up)
                if n2_ >= 0.5:
                    game_fwd, nf = g2_, n2_
                    break
    if not (_finite(up) and _finite(game_fwd)) or nu < 0.5 or nf < 0.5:
        _pose_reset(st)
        return
    want = game_fwd
    head = getattr(st, "head", None)
    if head is None or not _finite(head) or _dot(head, head) < 0.5:
        head = game_fwd
    head, hn = _horiz(head, up)
    if hn < 0.5:
        head = game_fwd
    kside = (1 if _key(0x44) & 0x8000 else 0) - (1 if _key(0x41) & 0x8000 else 0)
    kfwd = (1 if _key(0x57) & 0x8000 else 0) - (1 if _key(0x53) & 0x8000 else 0)
    look, vstat = _view_filtered(st, now, dt) if flying else (None, "none")
    if not flying or look is None:
        _view_reset(st)
    st.view_stat = vstat
    if flying:
        want = head
    if flying and look is not None:
        lk_h = look
        if sup is not None:
            cf_ = _cam_frame()
            if cf_:
                lk_h = _norm(_add(cf_[0], _scale(cf_[1], -_dot(cf_[0], up))))[0]
        _view_heading(st, lk_h, up, head, now, dt, vstat)
        if sup is not None:
            hh_s, hn_s = _horiz(lk_h, up)
            if hn_s > 0.1:
                st.look_h = hh_s
        want = st.look_h
        st.view_elev = max(-PATH_ELEV_MAX, min(PATH_ELEV_MAX,
                           math.degrees(math.asin(max(-1.0, min(1.0, _dot(look, up)))))))
        ywt = -math.radians(STRAFE_YAW) * kside * 0.5 if (kside and kfwd > 0) else 0.0
        st.str_yaw, st.str_yaw_v = _cd(getattr(st, "str_yaw", 0.0), getattr(st, "str_yaw_v", 0.0), ywt, 0.12, dt)
        yw = st.str_yaw
        if abs(yw) > 1e-4:
            want = _rot(want, up, math.cos(yw), math.sin(yw))
        pv = getattr(st, "pose_vel", None)
        if pv is not None:
            hv, hs = _horiz(pv, up)
            off = _signed_yaw(want, hv, up)
            taper = min(1.0, max(0.0, (math.radians(80) - abs(off)) / math.radians(35)))
            f = TRAVEL_HEADING * min(1.0, max(0.0, hs - 2.0) / TRAVEL_SPEED) * taper * off
            want = _rot(want, up, math.cos(f), math.sin(f))
    yaw = _signed_yaw(head, want, up)
    if flying and not getattr(st, "was_flying", False):
        st.fly_since = now
    st.was_flying = flying
    yd = getattr(st, "yaw_rate", 0.0)
    d = getattr(st, "yaw_dir", 0)
    yc = yaw + 2 * math.pi * d if d and (yaw > 0) != (d > 0) else yaw
    spinning = d and d * getattr(st, "cam_yr", 0.0) > YAW_SPIN and abs(yc) < math.radians(YAW_COMMIT_MAX)
    if abs(yaw) > math.radians(YAW_COMMIT) or (spinning and abs(yc) > math.radians(YAW_COMMIT)):
        if not d:
            d = math.copysign(1, yd) if abs(yd) > 1e-3 else math.copysign(1, yaw)
            yc = yaw + 2 * math.pi * d if (yaw > 0) != (d > 0) else yaw
        yaw = yc
        st.yaw_dir = d
    else:
        st.yaw_dir = 0
    tc = (TAKEOFF_HEADING_TIME + (HEADING_TIME - TAKEOFF_HEADING_TIME)
          * _smoothstep(now - getattr(st, "fly_since", 0.0), 0.4, 0.8)) if flying else HEADING_RELEASE_TIME
    amax = math.radians(MAX_YAW_ACC)
    lim = min(math.radians(MAX_YAW_RATE), math.sqrt(2 * amax * abs(yaw)))
    r_want = max(-lim, min(lim, yaw * (1 - math.exp(-dt / tc)) / dt))
    if flying:
        r_want *= _smoothstep(now - getattr(st, "fly_since", 0.0), 0.0, 0.3)
    yd +=max(-amax * dt, min(amax * dt, r_want - yd))
    step = yd * dt
    if (step > 0) == (yaw > 0) and abs(step) > abs(yaw):
        step = yaw
    if not math.isfinite(step):
        step = 0.0
    st.yaw_rate = step / dt
    st.head_step = step
    head = _rot(head, up, math.cos(step), math.sin(step))
    st.head = head
    if flying and time.perf_counter() >= getattr(st, "x_face_until", 0.0):
        fd = (ctypes.c_float * 3).from_address(player + 0x3480)
        fh, fn = _horiz(head, pup)
        if fn > 0.3:
            fd[0], fd[1], fd[2] = -fh[0], -fh[1], -fh[2]
    st.yaw_off = math.atan2(_dot(_cross(game_fwd, head), up), _dot(game_fwd, head))
    fwd = head
    right = _cross(up, fwd)
    pos = _v(player + 0x360)
    last = getattr(st, "pose_pos", None)
    st.pose_pos = pos
    vel = getattr(st, "pose_vel", None) or [0.0, 0.0, 0.0]
    sh = _steer() if flying else None
    if sh is not None and sh[3] is not None:
        k = 1 - math.exp(-dt / VEL_SMOOTH)
        vel = [vel[i] + (sh[3][i] - vel[i]) * k for i in range(3)]
    elif last is not None:
        raw = _scale(_add(pos, _scale(last, -1)), 1.0 / dt)
        if _dot(raw, raw) < 400.0 ** 2:
            k = 1 - math.exp(-dt / VEL_SMOOTH)
            vel = [vel[i] + (raw[i] - vel[i]) * k for i in range(3)]
    acc = getattr(st, "pose_acc", None) or [0.0, 0.0, 0.0]
    prev_v = getattr(st, "pose_vel", None)
    if prev_v is not None and last is not None:
        ka = 1 - math.exp(-dt / ACC_SMOOTH)
        acc = [acc[i] + ((vel[i] - prev_v[i]) / dt - acc[i]) * ka for i in range(3)]
        if not _finite(acc) or _dot(acc, acc) > 200.0 ** 2:
            acc = [0.0, 0.0, 0.0]
    st.pose_acc = acc
    st.pose_vel = vel
    st.burner = bool(sh and sh[4])
    st.dive = getattr(st, "dive", 0.0) + ((1.0 if sh and sh[5] else 0.0) - getattr(st, "dive", 0.0)) \
        * (1 - math.exp(-dt / DIVE_TIME))
    st.pin, st.pin_v = _cd(getattr(st, "pin", 0.0), getattr(st, "pin_v", 0.0), 1.0 if flying else 0.0,
                           PIN_TIME if flying else PIN_OUT_TIME, dt)
    st.pin = min(1.0, max(0.0, st.pin))
    thr_q = _throttle() if flying else None
    space_q, water_q = sup is not None or space_on, getattr(st, "in_water", False)
    qt_ = _quarter_hold(thr_q, space_q, water_q)
    if flying and getattr(st, "fly_since", None) == now:
        st.q_w, st.q_wv = qt_, 0.0
    elif qt_ > 0.0 or getattr(st, "q_w", 0.0) > 0.0 or getattr(st, "q_wv", 0.0) != 0.0:
        st.q_w, st.q_wv = _quarter_ease(getattr(st, "q_w", 0.0), getattr(st, "q_wv", 0.0), qt_, dt)
    if thr_q is not None:
        st.q_x = _quarter_x(thr_q)
    q_ahead = _quarter_on(thr_q, kfwd, space_q, water_q) > 0.0
    qh_t = 1.0 if q_ahead and _quarter_live(st, now) else 0.0
    if qh_t > 0.0 or getattr(st, "qh_w", 0.0) > 0.0 or getattr(st, "qh_wv", 0.0) != 0.0:
        st.qh_w, st.qh_wv = _quarter_ease(getattr(st, "qh_w", 0.0), getattr(st, "qh_wv", 0.0), qh_t, dt)
    if POSE_PIN and (flying or st.pin > 0.02):
        keys_held = any(_key(vk) & 0x8000 for vk in MOVE_KEYS)
        prm = (ctypes.c_float * 24).from_address(comp + PARAMS)
        ground = prm[10]
        if SPACE_GROUND is not None and flying and getattr(st, "space_on", False):
            ground = prm[10] = SPACE_GROUND
        wraw_ = flying and ctypes.c_uint32.from_address(comp + 0x214).value in WATER_STATES
        if wraw_:
            st.water_pt = _v(player + 0x360)
            st.water_t = time.perf_counter()
        st.in_water = flying and (wraw_ or _water_held(st, _v(player + 0x360), _norm(_v(player + 0x320))[0]))
        if st.in_water:
            ground = prm[10] = WATER_GROUND
            st.gref = None
        elif (flying and getattr(st, "water_pt", None) is not None and math.isfinite(ground)
              and (time.perf_counter() - getattr(st, "water_t", -99.0) < WATER_RECENT
                   or any(_key(vk) & 0x8000 for vk in (0x57, 0x41, 0x53, 0x44)))):
            gu_w = _norm(_v(player + 0x320))[0]
            d_ = _add(_v(player + 0x360), _scale(st.water_pt, -1))
            hv_ = _dot(d_, gu_w)
            hz_ = _add(d_, _scale(gu_w, -hv_))
            if _dot(hz_, hz_) < WATER_NEAR ** 2 and -WATER_LEVEL_TOL < ground - hv_ < 1.0:
                ground = prm[10] = WATER_GROUND
        st.gnd = ground
        vdown = -_dot(vel, up)
        flare = 0.0
        reach = LAND_FLARE_DIST + LAND_FLARE_TIME * max(0.0, vdown)
        steering = any(_key(vk) & 0x8000 for vk in (0x57, 0x41, 0x53, 0x44))
        if sup is None and not steering and math.isfinite(ground) and 0.0 <= ground < reach and 1.0 < vdown < 120.0:
            flare = 1.0 - ground / reach
            if vdown > 8.0:
                flare = 1.0
        st.flare = getattr(st, "flare", 0.0) + (flare - getattr(st, "flare", 0.0)) * (1 - math.exp(-dt / 0.1))
        hz = _add(vel, _scale(up, -_dot(vel, up)))
        hs = math.sqrt(_dot(hz, hz))
        sp_all = math.sqrt(_dot(vel, vel))
        g = min(1.0, max(0.0, (sp_all - GLIDE_SPEED[0]) / (GLIDE_SPEED[1] - GLIDE_SPEED[0])))
        k = (1.0 if keys_held else (0.0 if sup is not None else g * g * (3 - 2 * g))) if flying else 0.0
        k *= 1.0 - st.flare
        if q_ahead or getattr(st, "qa_w", 0.0) > 0.0:
            k = 0.0
        okg = math.isfinite(ground)
        if okg and 0.0 <= ground < 0.6:
            st.gref = pos
        hgt = None
        gref = getattr(st, "gref", None)
        if gref is not None:
            d_ = _add(pos, _scale(gref, -1))
            hv_ = _dot(d_, up)
            hd_ = _add(d_, _scale(up, -hv_))
            if _dot(hd_, hd_) < NEAR_REF_RADIUS ** 2:
                hgt = max(0.0, hv_)
        if okg and 0.0 <= ground < NEAR_GAME_MAX:
            hgt = ground if hgt is None else min(hgt, ground)
        st.hgt = hgt
        rdy = rlx = 0.0
        if flying and sup is None and not steering and hgt is not None and hgt < NEAR_READY[0] and hs < NEAR_MAX_SPEED:
            rdy = _smoothstep(NEAR_READY[0] - hgt, 0.0, NEAR_READY[0] - NEAR_READY[1])
            rlx = _smoothstep(NEAR_RELAX[0] - hgt, 0.0, NEAR_RELAX[0] - NEAR_RELAX[1])
        kn = 1 - math.exp(-dt / NEAR_TIME)
        st.near_rdy = getattr(st, "near_rdy", 0.0) + (rdy - getattr(st, "near_rdy", 0.0)) * kn
        st.near_rlx = getattr(st, "near_rlx", 0.0) + (rlx - getattr(st, "near_rlx", 0.0)) * kn
        k *= 1.0 - st.near_rdy
        st.legs_tgt = min(1.0, LEGS_GAIN * max(st.near_rdy, st.flare)) if flying else 0.0
        st.arms = getattr(st, "arms", 0.0)
        if getattr(st, "q_ahead_was", False) and not q_ahead and flying:
            st.q_exit_t = now
        st.q_ahead_was = q_ahead
        t_in_ = QUARTER_ARMS_IN if now - getattr(st, "q_exit_t", -99.0) < QUARTER_ARMS_HOLD else ARMS_IN_TIME
        st.arms, st.arms_v = _cd(st.arms, getattr(st, "arms_v", 0.0), k,
                                 t_in_ if k > st.arms else ARMS_OUT_TIME, dt)
        st.arms = min(1.0, max(0.0, st.arms))
        w = st.pin
        for i in (6, 7, 18, 22, 23):
            prm[i] = prm[i] * (1 - w)
        kd = lambda vk: 1 if _key(vk) & 0x8000 else 0
        kfi, ksi = kd(0x57) - kd(0x53), kd(0x44) - kd(0x41)
        if kfi > 0 and _pad_read()[1] & THROTTLE_AHEAD_BIT:
            ksi = 0
        st.sp_fly, st.sp_fly_v = _sp_fly_step(getattr(st, "sp_fly", 0.0), getattr(st, "sp_fly_v", 0.0), kfi > 0, dt)
        lx, ly = -_dot(vel, right), _dot(vel, fwd)
        if kfi or ksi:
            dx, dy = float(ksi), float(kfi)
        elif math.hypot(lx, ly) > 2.0 and sup is None:
            dx, dy = lx, ly
        else:
            dx, dy = 0.0, 0.0
        n = math.hypot(dx, dy)
        if n > 1e-6:
            dx, dy = dx / n, dy / n
        bx, by = getattr(st, "bdir", (0.0, 1.0))
        if not (kfi or ksi):
            s_ = getattr(st, "head_step", 0.0)
            cs_, sn_ = math.cos(s_), math.sin(s_)
            bx, by = bx * cs_ + by * sn_, by * cs_ - bx * sn_
        kk = 1 - math.exp(-dt / DIR_TIME)
        bx, by = bx + (dx - bx) * kk, by + (dy - by) * kk
        st.bdir = (bx, by)
        r = BLEND_R[0]
        m = min(1.0, math.hypot(bx, by))
        th = math.atan2(bx, by)
        ath = abs(th)
        if ath <= math.pi / 2:
            u = ath / (math.pi / 2)
            thb, rad = th / 2, r + (SIDE_R - r) * u
        else:
            u = (ath - math.pi / 2) / (math.pi / 2)
            thb = math.copysign(math.pi / 4 + u * 3 * math.pi / 4, th)
            rad = SIDE_R + (BACK_R - SIDE_R) * u
        a_ = st.arms
        px = math.sin(thb) * rad * m * a_
        py = math.cos(thb) * rad * m * a_
        prm[4] = prm[4] * (1 - w) + px * w
        prm[5] = prm[5] * (1 - w) + py * w
        st.anim_fwd = st.arms * min(1.0, max(0.0, math.cos(thb) * m / 0.7))
        prm[19] = prm[19] * (1 - w) + _space_tsje(space_q, st.sp_fly) * w
        if sup is not None and SPACE_LOOK_PIN is not None:
            for o_ in (PARAMS + 4, PARAMS + 0x20):
                ctypes.c_float.from_address(comp + o_).value = SPACE_LOOK_PIN
    if not flying and st.pin <= 0.02:
        st.arms = 0.0
        st.anim_fwd = 0.0
    lt_ = getattr(st, "legs_tgt", 0.0) if flying else 0.0
    lo_ = getattr(st, "legs_out", 0.0)
    lo_ += (lt_ - lo_) * (1 - math.exp(-dt / (LEGS_IN if lt_ > lo_ else LEGS_LAND_FADE if not flying else LEGS_IN)))
    st.legs_out = lo_ if lo_ > 0.003 or lt_ > 0.0 else 0.0
    if _SHM is not None:
        try:
            _struct.pack_into("<d", _SHM, SHM_LEGS, st.legs_out)
        except Exception:
            pass
    if not POSE_TILT:
        return
    last_fwd = getattr(st, "pose_fwd", None) or fwd
    st.pose_fwd = fwd
    target = [0.0, 0.0, 0.0]
    kf = ks = 0
    roll_t = 0.0
    if flying:
        kd = lambda vk: 1 if _key(vk) & 0x8000 else 0
        kf, ks, kv = kd(0x57) - kd(0x53), kd(0x44) - kd(0x41), kd(0x52) - kd(0x46)
        ve = _add(vel, _scale(st.pose_acc, ACC_LEAD))
        vf, vr, vu = _dot(ve, fwd), _dot(ve, right), _dot(ve, up)
        hs = math.hypot(vf, vr)
        st.anim_fwd_s = getattr(st, "anim_fwd_s", 0.0)
        st.anim_fwd_s += (getattr(st, "anim_fwd", 0.0) - st.anim_fwd_s) * (1 - math.exp(-dt / 0.15))
        a = st.anim_fwd_s
        if sup is not None:
            a = _space_fwd_blend(a, getattr(st, "sp_fly", 0.0), getattr(st, "space_w", 0.0))
        anim = ANIM_PITCH * a
        sv = _steer()
        sd, _n = _norm(sv[0]) if sv is not None and _finite(sv[0]) else (None, 0.0)
        if _n > 0.5:
            pe = math.degrees(math.asin(max(-1.0, min(1.0, _dot(sd, up)))))
            tc_e = 0.2
        elif VIEW_TRUE and look is not None:
            pe = getattr(st, "view_elev", 0.0)
            tc_e = 0.2
        else:
            pe = math.degrees(math.atan2(_dot(vel, up), max(hs, 1.0))) * min(1.0, math.sqrt(_dot(vel, vel)) / 8.0)
            tc_e = 0.2
        pe = max(-PATH_ELEV_MAX, min(PATH_ELEV_MAX, pe)) if math.isfinite(pe) else 0.0
        pe0 = getattr(st, "path_elev", 0.0)
        de = (pe - pe0) * (1 - math.exp(-dt / tc_e))
        de = max(-PATH_ELEV_RATE * dt, min(PATH_ELEV_RATE * dt, de))
        st.path_elev = pe0 + de
        if kf > 0:
            P = INPUT_FWD + (FWD_MAX - INPUT_FWD) * math.tanh(math.hypot(hs, min(vu, 0.0)) / FWD_SPEED)
            P = _quarter_lean(P, getattr(st, "q_w", 0.0), getattr(st, "q_x", 0.0))
            P -= INPUT_VERT * kv
            P -= st.path_elev
        elif kf < 0:
            P = -BACK_MAX * (0.6 + 0.4 * math.tanh(max(-vf, 0.0) / BACK_SPEED))
        elif ks:
            P = STRAFE_PITCH
        elif kv > 0:
            P = CLIMB_PITCH
        elif kv < 0:
            P = DESCEND_PITCH
        else:
            P = FWD_MAX * math.tanh(max(vf, 0.0) / FWD_SPEED) - BACK_MAX * math.tanh(max(-vf, 0.0) / BACK_SPEED)
            P -= VERT_MAX * 0.5 * math.tanh(vu / VERT_SPEED)
        if not kf and not ks:
            idl = 1.0 - getattr(st, "arms", 0.0)
            P += IDLE_PITCH * idl
            nr = getattr(st, "near_rdy", 0.0)
            P += (NEAR_PITCH - P) * nr
        if kf > 0:
            P += (PITCH_MAX - P) * getattr(st, "dive", 0.0)
        P *= 1.0 - getattr(st, "flare", 0.0)
        if kf > 0:
            ve = getattr(st, "view_elev", 0.0)
            if ve <= 0.0:
                nd = min(1.0, -ve / NOSE_CAM_DOWN[1]) ** NOSE_LOOK_CURVE
            else:
                nd = -min(1.0, ve / NOSE_CAM_UP) ** NOSE_LOOK_CURVE
            na, nb = getattr(st, "nose_a", 0.0), getattr(st, "nose_b", 0.0)
            if getattr(st, "nose_preset", False):
                na = nb = nd
            k = 1 - math.exp(-dt / (NOSE_EASE[0] if abs(nd) > abs(nb) else NOSE_EASE[1]))
            na += (nd - na) * k
            nb += (na - nb) * k
            st.nose_a, st.nose_b = na, nb
            st.nose_preset = False
            if nb >= 0.0:
                P = min(P, PITCH_MAX) + (PITCH_MAX - min(P, PITCH_MAX)) * nb
            else:
                P = max(P, PITCH_UP) + (PITCH_UP - max(P, PITCH_UP)) * -nb
        else:
            st.nose_a = st.nose_b = 0.0
        st.flip = kf > 0 and P >= (NOSE_UNFLIP_P if getattr(st, "flip", False) else NOSE_FLIP_P)
        if getattr(st, "in_water", False):
            P = min(P, WATER_PITCH_MAX)
            st.flip = False
        if sup is not None:
            if not (kf or ks or kv):
                P = IDLE_PITCH * (1.0 - getattr(st, "arms", 0.0))
            st.flip = False
        st.anim_lean = anim
        tf = P - anim
        if sup is not None:
            st.sp_x_t = time.perf_counter()
        wx_ = 1.0 if sup is not None else max(0.0, 1.0 - (time.perf_counter() - getattr(st, "sp_x_t", -99.0)) / SPACE_EXTRA_FADE)
        ext_ = _space_torso_extra(st, dt) if flying else 0.0
        tf = max(tf, -COUNTER_MAX * a + min(P, 0.0) * (1 - a))
        tf = min(tf, PITCH_MAX - anim)
        if SPACE_ROOT_CORR and wx_ > 0.0:
            tf -= ext_ * wx_
        if SPACE_LINE_SERVO:
            tf += _space_line_servo(st, sup is not None, a, dt) * wx_
        if ks and (not kf or (kf > 0 and _quarter_side(st))):
            tr = -(SPACE_STRAFE_BANK if sup is not None else STRAFE_BANK) * ks
        elif kf > 0:
            tr = SIDE_MAX * 0.15 * math.tanh(vr / SIDE_SPEED)
        else:
            tr = -INPUT_SIDE * ks * 0.5 + SIDE_MAX * 0.5 * math.tanh(vr / SIDE_SPEED)
        wet_ = bool(getattr(st, "in_water", False))
        if (sup is not None or wet_) and not (kf or ks or kv):
            tr = 0.0
        st.sway_w = getattr(st, "sway_w", 1.0)
        st.sway_w += ((0.0 if wet_ else 1.0) - st.sway_w) * (1.0 - math.exp(-dt / WATER_SWAY_FADE))
        if not (kf or ks or kv):
            idl = (1.0 - getattr(st, "arms", 0.0)) * (1.0 - 0.5 * getattr(st, "near_rlx", 0.0)) * st.sway_w
            a1, f1, a2, f2 = IDLE_SWAY
            tf += idl * a1 * math.sin(2 * math.pi * f1 * now)
            tr += idl * a2 * math.sin(2 * math.pi * f2 * now + 1.3)
        target = _add(_scale(fwd, tf), _scale(right, tr))
        turn = _scale(_add(fwd, _scale(last_fwd, -1)), 1.0 / dt)
        tdir, rate = _norm(_add(turn, _scale(up, -_dot(turn, up))))
        bank = BANK_MAX * math.tanh(rate / BANK_RATE) * min(1.0, hs / BANK_SPEED)
        yr = getattr(st, "cam_yr", 0.0)
        st.yr = getattr(st, "yr", 0.0) + (yr - getattr(st, "yr", 0.0)) * (1 - math.exp(-dt / TURN_SMOOTH))
        yr_eff = math.copysign(max(0.0, abs(st.yr) - TURN_DEADBAND), st.yr)
        if kf > 0 and getattr(st, "w_since", None) is None:
            st.w_since = now
        elif kf <= 0:
            st.w_since = None
        if kf > 0:
            bank = 0.0
            sf = min(1.0, hs / BANK_SPEED) * min(1.0, (now - st.w_since) / 0.5)
            roll_t = -TURN_ROLL_MAX * math.tanh(yr_eff / TURN_ROLL_RATE) * sf + FWD_KEY_ROLL * ks
            roll_t = max(-ROLL_LIMIT, min(ROLL_LIMIT, roll_t))
        if sup is not None and kf <= 0:
            bank = 0.0
            roll_t = -TURN_ROLL_MAX * SPACE_TURN_ROLL * math.tanh(yr_eff / TURN_ROLL_RATE)
        target = _add(target, _scale(tdir, bank))
        tdir, mag = _norm(target)
        lim_ = NOSE_FLIP_MAX if st.flip else TILT_LIMIT
        if mag > lim_:
            target = _scale(tdir, lim_)
    flip = flying and getattr(st, "flip", False)
    if not flip:
        st.flip = False
    if not flying:
        st.q_w, st.q_wv = 0.0, 0.0
        st.qh_w, st.qh_wv = 0.0, 0.0
    if not flying or (kf <= 0 and sup is None):
        roll_t = 0.0
    rt0 = getattr(st, "roll_t", 0.0)
    rs_ = ROLL_TARGET_RATE * dt
    roll_t = rt0 + max(-rs_, min(rs_, roll_t - rt0))
    st.roll_t = roll_t
    if lean is None or getattr(st, "lean_loc", None) is None:
        st.lean_loc, st.lean_loc_v = [0.0, 0.0], [0.0, 0.0]
    elif not any(_key(vk) & 0x8000 for vk in MOVE_KEYS) and _finite(lean) and _finite(st.lean_v):
        st.lean_loc = [_dot(lean, fwd), _dot(lean, right)]
        st.lean_loc_v = [_dot(st.lean_v, fwd), _dot(st.lean_v, right)]
    lc_ = getattr(st, "lean_conv", None)
    if lc_ is not None:
        st.lean_conv = None
        bt_ = math.degrees(math.acos(max(-1.0, min(1.0, _dot(lc_, up))))) - getattr(st, "body_al", 0.0)
        bd_, bn_ = _norm(_add(lc_, _scale(up, -_dot(lc_, up))))
        if bn_ > 0.02 and _finite(bd_):
            st.lean_loc = [bt_ * _dot(bd_, fwd), bt_ * _dot(bd_, right)]
            st.lean_loc_v = [0.0, 0.0]
            st.lean_hard = max(getattr(st, "lean_hard", LEAN_HARD_MAX), abs(bt_))
            st.lean_tgt_f = None
            lean = st.lean = _add(_scale(fwd, st.lean_loc[0]), _scale(right, st.lean_loc[1]))
            log.info(f"crossing: body tilt carried into the planet's lean ({bt_:.0f} deg)")
    tgt = (_dot(target, fwd), _dot(target, right))
    tg0 = getattr(st, "lean_tgt_f", None)
    if tg0 is None or lean is None:
        tg0 = tgt
    kpf = 1 - math.exp(-dt / LEAN_PREFILTER)
    tgt = (tg0[0] + (tgt[0] - tg0[0]) * kpf, tg0[1] + (tgt[1] - tg0[1]) * kpf)
    st.lean_tgt_f = tgt
    lh_ = SPRING_HZ if flying else RELEASE_SPRING_HZ
    st.lean_hz = getattr(st, "lean_hz", lh_) + (lh_ - getattr(st, "lean_hz", lh_)) * (1 - math.exp(-dt / 0.15))
    w = 2 * math.pi * st.lean_hz
    for i in range(2):
        st.lean_loc_v[i] += (w * w * (tgt[i] - st.lean_loc[i]) - 2 * w * st.lean_loc_v[i]) * dt
    sp = math.hypot(*st.lean_loc_v)
    if sp > MAX_LEAN_RATE:
        st.lean_loc_v = [x * MAX_LEAN_RATE / sp for x in st.lean_loc_v]
    for i in range(2):
        st.lean_loc[i] += st.lean_loc_v[i] * dt
    lm = math.hypot(*st.lean_loc)
    hard = NOSE_FLIP_MAX + 3.0 if flip else max(LEAN_HARD_MAX, min(getattr(st, "lean_hard", LEAN_HARD_MAX), lm))
    st.lean_hard = hard
    if lm > hard:
        ux_, uy_ = st.lean_loc[0] / lm, st.lean_loc[1] / lm
        st.lean_loc = [ux_ * hard, uy_ * hard]
        vo_ = st.lean_loc_v[0] * ux_ + st.lean_loc_v[1] * uy_
        if vo_ > 0:
            st.lean_loc_v = [st.lean_loc_v[0] - ux_ * vo_, st.lean_loc_v[1] - uy_ * vo_]
    st.lean =_add(_scale(fwd, st.lean_loc[0]), _scale(right, st.lean_loc[1]))
    st.lean_v = _add(_scale(fwd, st.lean_loc_v[0]), _scale(right, st.lean_loc_v[1]))
    st.roll = getattr(st, "roll", 0.0)
    st.roll_v = getattr(st, "roll_v", 0.0)
    hz_ = ROLL_SPRING_HZ if abs(roll_t) >= abs(st.roll) else ROLL_RELEASE_HZ
    hz_ = hz_ if flying else RELEASE_SPRING_HZ
    rh_ = getattr(st, "roll_hz", hz_)
    st.roll_hz = rh_ + (hz_ - rh_) * (1 - math.exp(-dt / 0.2))
    wr_ = 2 * math.pi * st.roll_hz
    st.roll_v += (wr_ * wr_ * (roll_t - st.roll) - 2 * wr_ * st.roll_v) * dt
    rcap = min(MAX_ROLL_RATE, math.sqrt(max(0.0, MAX_SPIN_RATE ** 2 - math.degrees(getattr(st, "yaw_rate", 0.0)) ** 2)))
    st.roll_v = max(-rcap, min(rcap, st.roll_v))
    st.roll += st.roll_v * dt
    if not (math.isfinite(st.roll) and math.isfinite(st.roll_v)):
        st.roll, st.roll_v = 0.0, 0.0
    if not (_finite(st.lean) and _finite(st.lean_v) and _finite(head)):
        _pose_reset(st)
        return
    L = _add(st.lean, _scale(up, -_dot(st.lean, up)))
    br = _free_roll(st, now, dt, flying and sup is None)
    ldir, ang = _norm(L)
    st.pose_angle = ang
    axis, _ = _norm(_cross(up, ldir)) if ang >= 0.05 else (fwd, 0.0)
    ca_, sa_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    al = math.radians(getattr(st, "anim_lean", 0.0) if flying else 0.0)
    nu, nf = _rot(up, axis, ca_, sa_), _rot(fwd, axis, ca_, sa_)
    body = _add(_scale(nu, math.cos(al)), _scale(nf, math.sin(al)))
    st.body_axis, st.body_al = body, math.degrees(al)
    tp_ = ang + math.degrees(al)
    rw = _smoothstep(tp_, ROLL_BODY_P[0], ROLL_BODY_P[1])
    if flying and getattr(st, "nose_b", 0.0) < 0.0:
        rw = max(rw, (1.0 - _smoothstep(tp_, 2 * ROLL_BODY_P[0] - ROLL_BODY_P[1], ROLL_BODY_P[0]))
                 * min(1.0, -st.nose_b * 4.0))
    st.sp_rw = rw
    rax, rn_ = _norm(_add(_scale(head, 1.0 - rw), _scale(body, rw)))
    if rn_ < 0.5 or not _finite(rax):
        rax = head
    bax = head
    if BARREL_BODY_AXIS:
        bax, bn_ = _norm(_rot(body, rax, math.cos(math.radians(st.roll)), math.sin(math.radians(st.roll))))
        if bn_ < 0.5 or not _finite(bax):
            bax = head
    st.tilt = (up, head, axis, ca_, sa_, math.radians(st.roll), bax, math.radians(br), rax)
    st.tilt_t = now
def _tilt_between(st, cur):
    if not TILT_BLEND:
        return cur
    now = time.perf_counter()
    lean = _scale(cur[2], math.atan2(cur[4], cur[3]))
    tgt = list(cur[1]) + list(lean) + [cur[5]] + list(cur[6]) + [cur[7]] + list(cur[8])
    x, v, t0 = getattr(st, "tf_x", None), getattr(st, "tf_v", None), getattr(st, "tf_t", 0.0)
    if x is None or not 0.0 < now - t0 < 0.25:
        st.tf_x, st.tf_v, st.tf_t = tgt[:], [0.0] * len(tgt), now
        return cur
    tb = x[10] + (tgt[10] - x[10] + math.pi) % (2 * math.pi) - math.pi
    tgt[10] = tb
    w = 2 * math.pi * TILT_FOLLOW_HZ
    dt = now - t0
    while dt > 1e-6:
        h = min(dt, 0.008)
        for i in range(len(x)):
            v[i] += (w * w * (tgt[i] - x[i]) - 2 * w * v[i]) * h
            x[i] += v[i] * h
        dt -= h
    st.tf_t = now
    if not _finite(x) or not _finite(v):
        st.tf_x = None
        return cur
    def unit(i, fb):
        r_, n_ = _norm(x[i:i + 3])
        return r_ if n_ > 0.3 else fb
    la, ang = _norm(x[3:6])
    if ang < 1e-6:
        la = cur[2]
    return (cur[0], unit(0, cur[1]), la, math.cos(ang), math.sin(ang), x[6], unit(7, cur[6]), x[10], unit(11, cur[8]))
try:
    _ARMS = _mmap.mmap(-1, 64, tagname="IronManFlightArms2")
except Exception:
    _ARMS = None
ARMS_FMT = "<dQI6f"
ARMS_ON = 1
WEAPON_SEL = 0xF74
FIRE_POSES = {0: "repulsor", 1: "twin", 2: "wristcannon", 3: "wristlaser", 4: "charged", 5: "unibeam",
              16: "rockets", 15: "repulsor", 11: "repulsor"}
POSE_IN, POSE_HOLD, POSE_OUT = 0.10, 0.45, 0.30
ARM_CHAIN = {s: (f"player01_{s}_arm_ClavicleSHJnt", f"player01_{s}_arm_ShoulderSHJnt",
                 f"player01_{s}_arm_ElbowSHJnt", f"player01_{s}_arm_WristSHJnt") for s in "lr"}
HAND_REF = {s: (f"player01_{s}_hand_03_01SHJnt", f"player01_{s}_hand_02_01SHJnt",
                f"player01_{s}_hand_05_01SHJnt") for s in "lr"}
WRIST_MAX = 75.0
GUN_ARM = "l"
PALM_SIGN = {"r": -1.0, "l": 1.0}
def _vrow(v, m):
    return [v[0] * m[0][j] + v[1] * m[1][j] + v[2] * m[2][j] for j in range(3)]
def _frame_rows(W, f, n, ft, nt):
    def basis(a, b):
        a, _ = _norm(a)
        b, nb = _norm(_add(b, _scale(a, -_dot(a, b))))
        return (a, b, _cross(a, b)) if nb > 1e-4 else None
    B0, B1 = basis(f, n), basis(ft, nt)
    if not B0 or not B1:
        return W
    out = []
    for r in W:
        c = [_dot(r, e) for e in B0]
        out.append([c[0] * B1[0][k] + c[1] * B1[1][k] + c[2] * B1[2][k] for k in range(3)])
    return out
def _arms_state():
    if _ARMS is None:
        return 0, 0
    try:
        t, w, fl = _struct.unpack_from(ARMS_FMT, _ARMS, 0)[:3]
    except Exception:
        return 0, 0
    if time.perf_counter() - t > 1.0:
        return 0, 0
    return w, fl
def _pose_targets(kind, look, up, out):
    n_ = lambda *vs: _norm([sum(v[i] for v in vs) for i in range(3)])[0]
    s_ = lambda v, k: _scale(v, k)
    o_r, o_l = out["r"], out["l"]
    T = {}
    if kind == "repulsor":
        T["r"] = (n_(look, s_(o_r, 0.05)), look, up, look)
    elif kind == "twin":
        for sd in "rl":
            T[sd] = (n_(look, s_(out[sd], 0.12)), n_(look, s_(out[sd], 0.05)), up, look)
    elif kind == "charged":
        for sd in "rl":
            T[sd] = (n_(look, s_(out[sd], 0.30), s_(up, -0.10)), n_(look, s_(out[sd], -0.22)), up, look)
    elif kind == "wristcannon":
        T["r"] = (n_(s_(look, 0.75), s_(up, -0.55), s_(o_r, 0.15)), look, look, s_(up, -1.0))
    elif kind == "wristlaser":
        T["r"] = (n_(look, s_(o_r, 0.25)), n_(look, s_(o_r, 0.10)), n_(look, s_(o_r, 0.10)), s_(up, -1.0))
    elif kind == "unibeam":
        T["r"] = ("ik", ("chest", _add(s_(look, 0.30), s_(up, -0.04))), n_(s_(up, -0.6), s_(o_r, 0.8)), up, look)
        T["l"] = (n_(s_(look, -0.45), s_(up, -0.85), s_(o_l, 0.35)),
                  n_(s_(look, -0.55), s_(up, -0.80), s_(o_l, 0.15)), s_(up, -1.0), s_(look, -1.0))
    elif kind == "rockets":
        T["r"] = ("ik", ("shoulder", _add(_add(s_(up, 0.16), s_(look, 0.22)), s_(o_r, 0.10))),
                  n_(s_(up, -0.4), s_(o_r, 0.9)), look, s_(o_r, -1.0))
        T["l"] = (n_(s_(up, -0.80), s_(o_l, 0.55), s_(look, 0.10)),
                  n_(s_(up, -0.55), s_(o_l, 0.30), s_(look, 0.55)), n_(s_(up, -0.55), s_(o_l, 0.30), s_(look, 0.55)),
                  s_(o_l, -1.0))
    return T
def _arm_out(st, hs, look, up):
    rt = _norm(_cross(look, up))[0]
    ch = _chest(st)
    out = {}
    for sd in "rl":
        k = 1.0 if sd == "l" else -1.0
        try:
            if ch:
                d = _dot(_add(_abs_pos(hs[sd][1]), _scale(_abs_pos(ch), -1.0)), rt)
                if abs(d) > 0.03:
                    k = 1.0 if d > 0 else -1.0
        except Exception:
            pass
        out[sd] = _scale(rt, k)
    return out
def _arm_handles(st):
    hs = getattr(st, "arm_h", None)
    if hs and all(_node_matrix(h_) for sd in hs for h_ in hs[sd] if h_):
        return hs
    names = [n for sd in "lr" for n in ARM_CHAIN[sd] + HAND_REF[sd]]
    f_, _ = find_by_walk(player_root(getattr(st, "component", None)), names)
    hs = {sd: [f_.get(n) for n in ARM_CHAIN[sd] + HAND_REF[sd]] for sd in "lr"}
    st.arm_h = hs if all(hs[sd][:4] for sd in "lr") else None
    return st.arm_h
_I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
def _abs_full(h):
    import nmspy.data.basic_types as bt_
    m_ = bt_.cTkMatrix34()
    nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
    W = [[m_.right.x, m_.right.y, m_.right.z], [m_.up.x, m_.up.y, m_.up.z], [m_.at.x, m_.at.y, m_.at.z]]
    return W if all(_finite(r) for r in W) and all(_dot(r, r) > 1e-6 for r in W) else None
def _q_axis(ax, ang):
    c, s_ = math.cos(ang), math.sin(ang)
    return [_rot(e, ax, c, s_) for e in _I3]
def _q_frame(f, n, ft, nt):
    return _frame_rows(_I3, f, n, ft, nt)
def _q_apply(W, Q):
    return [_vrow(r, Q) for r in W]
def _q_angle(Q):
    return math.degrees(math.acos(max(-1.0, min(1.0, (Q[0][0] + Q[1][1] + Q[2][2] - 1.0) / 2.0))))
def _local_from(cur, W2, Pfull):
    Pi = _m3inv(Pfull)
    if Pi is None:
        return None
    L = _m3mul(W2, Pi)
    out = F16(*cur)
    for r in range(3):
        out[r * 4:r * 4 + 3] = L[r]
    return out if _finite(list(out)) else None
def _solve_arm(st, hs, tgt, w):
    cla, sho, elb, wri, mid, idx, pnk = hs
    if tgt and tgt[0] == "ik":
        (anchor, offs), pole, fing, palm = tgt[1], tgt[2], tgt[3], tgt[4]
        S, E, Wr = _abs_pos(sho), _abs_pos(elb), _abs_pos(wri)
        a = math.sqrt(_dot(_add(E, _scale(S, -1)), _add(E, _scale(S, -1))))
        b = math.sqrt(_dot(_add(Wr, _scale(E, -1)), _add(Wr, _scale(E, -1))))
        if anchor == "chest":
            ch = _chest(st)
            if not ch:
                return
            base_p = _abs_pos(ch)
        else:
            base_p = S
        H = _add(base_p, _scale(offs, _arm_k(a + b)))
        st.__dict__.setdefault("ik_last", {})[wri] = (H, base_p, round(_arm_k(a + b), 3))
        u_d, f_d = _ik_dirs(S, H, a, b, pole)
        tgt = (u_d, f_d, fing, palm)
    base = st.arm_base = getattr(st, "arm_base", {})
    last = st.arm_last = getattr(st, "arm_last", {})
    up_d, fore_d, fing_d, palm_d = tgt
    def _local(j):
        m = _node_matrix(j)
        if not m:
            return None
        cur = list(F16.from_address(m))
        if last.get(j) == cur and j in base:
            cur = list(base[j])
        else:
            base[j] = list(cur)
        return cur
    def _write(j, cur, W2, Pfull):
        out = _local_from(cur, W2, Pfull)
        if out is None:
            return False
        _set_local(j, ctypes.addressof(out))
        last[j] = list(out)
        return True
    cs, ce, cw = _local(sho), _local(elb), _local(wri)
    Pc = _abs_full(cla)
    if cs is None or ce is None or cw is None or Pc is None:
        return
    Ws = _m3mul(_m3(cs), Pc)
    d_u = _norm(_vrow(ce[12:15], Ws))[0]
    h_now = _norm(_vrow(ce[4:7], Ws))[0]
    u_t = _slerp_dir(d_u, up_d, w)
    bend, bn = _norm(_cross(up_d, fore_d))
    if bn > 0.15:
        if _dot(bend, h_now) < 0:
            bend = _scale(bend, -1.0)
        h_t = _slerp_dir(h_now, bend, w)
    else:
        h_t = h_now
    Ws2 = _q_apply(Ws, _q_frame(d_u, h_now, u_t, h_t))
    if not _write(sho, cs, Ws2, Pc):
        return
    We = _m3mul(_m3(ce), Ws2)
    hinge = _norm(We[1])[0]
    f_now = _norm(_vrow(cw[12:15], We))[0]
    f_t = _slerp_dir(f_now, fore_d, w)
    a_ = _norm(_add(f_now, _scale(hinge, -_dot(f_now, hinge))))[0]
    b_ = _norm(_add(f_t, _scale(hinge, -_dot(f_t, hinge))))[0]
    ang = math.atan2(_dot(_cross(a_, b_), hinge), _dot(a_, b_))
    We2 = _q_apply(We, _q_axis(hinge, ang))
    if not _write(elb, ce, We2, Ws2):
        return
    ms = [_node_matrix(h_) for h_ in (mid, idx, pnk)]
    if not all(ms):
        return
    Ww = _m3mul(_m3(cw), We2)
    tm, ti, tp = (list(F16.from_address(x))[12:15] for x in ms)
    sg = PALM_SIGN["r" if hs is st.arm_h["r"] else "l"]
    f = _norm(_vrow(tm, Ww))[0]
    side = _norm(_vrow(_add(ti, _scale(tp, -1.0)), Ww))[0]
    nrm = _scale(_norm(_cross(f, side))[0], sg)
    Q = _q_frame(f, nrm, _slerp_dir(f, fing_d, w), _slerp_dir(nrm, palm_d, w))
    tot = _q_angle(Q)
    if tot > WRIST_MAX:
        k_ = WRIST_MAX / tot
        Q = _q_frame(f, nrm, _slerp_dir(f, _vrow(f, Q), k_), _slerp_dir(nrm, _vrow(nrm, Q), k_))
    Ww2 = _q_apply(Ww, Q)
    if _write(wri, cw, Ww2, We2):
        f_t2 = _norm(_vrow(tm, Ww2))[0]
        n_t2 = _scale(_norm(_cross(f_t2, _norm(_vrow(_add(ti, _scale(tp, -1.0)), Ww2))[0]))[0], sg)
        return Ww2, f_t2, n_t2
    return None
def _tool_model(st):
    h = getattr(st, "tool_h", None)
    if h and _node_matrix(h):
        return h
    st.tool_h = None
    try:
        import nmspy.data.types as nms_
        from nmspy.data.basic_types import TkHandle as TkH_
        o_ = TkH_()
        nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(player_root(getattr(st, "component", None))))
        top = o_.lookupInt
        for _ in range(3):
            nm = nms_.Engine.GetNodeName(_tk(top))
            nm = nm.decode(errors="replace") if isinstance(nm, bytes) else str(nm)
            if nm == "Player":
                break
            nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(top))
            top = o_.lookupInt
        for c in children(top):
            nm = nms_.Engine.GetNodeName(_tk(c))
            nm = nm.decode(errors="replace") if isinstance(nm, bytes) else str(nm)
            if nm.upper().endswith("MULTITOOL.SCENE.MBIN"):
                for c2 in children(c):
                    n2 = nms_.Engine.GetNodeName(_tk(c2))
                    n2 = n2.decode(errors="replace") if isinstance(n2, bytes) else str(n2)
                    if n2.startswith("_MultiTool"):
                        st.tool_h = c2
                        return c2
    except Exception:
        pass
    return None
CHEST_JOINT = "player01_spine_TopSHJnt"
SOCKET_JOINT = "player01_r_hand_socket_AuxSHJnt"
def _abs_pos(h):
    import nmspy.data.basic_types as bt_
    m_ = bt_.cTkMatrix34()
    nms().Engine.GetNodeAbsoluteTransMatrix(_tk(h), ctypes.byref(m_))
    return [m_.pos.x, m_.pos.y, m_.pos.z]
def _chest(st):
    h = getattr(st, "chest_h", None)
    if h and _node_matrix(h):
        return h
    f_, _ = find_by_walk(player_root(getattr(st, "component", None)), [CHEST_JOINT])
    st.chest_h = f_.get(CHEST_JOINT)
    return st.chest_h
def _ik_dirs(S, H, a, b, pole):
    v, d = _norm(_add(H, _scale(S, -1.0)))
    d = max(abs(a - b) + 1e-3, min(a + b - 1e-3, d))
    x = (a * a - b * b + d * d) / (2 * d)
    h = math.sqrt(max(0.0, a * a - x * x))
    pp, pn = _norm(_add(pole, _scale(v, -_dot(pole, v))))
    if pn < 1e-3:
        pp = _norm(_cross(v, [0.0, 1.0, 0.0]))[0]
    E = _add(S, _add(_scale(v, x), _scale(pp, h)))
    Hc = _add(S, _scale(v, d))
    return _norm(_add(E, _scale(S, -1.0)))[0], _norm(_add(Hc, _scale(E, -1.0)))[0]
RECOIL_KINDS = ("repulsor", "twin", "charged", "wristcannon")
RECOIL_DEG, RECOIL_TC = 11.0, 0.09
TORSO = {"unibeam": ("arch", 12.0), "repulsor": ("twist", 14.0), "wristcannon": ("twist", 18.0),
         "wristlaser": ("twist", 20.0), "rockets": ("twist", -10.0)}
FIST = {"wristcannon": 1.0, "rockets": 1.0}
OPEN = {"repulsor": 1.0, "twin": 1.0, "charged": 1.0, "unibeam": 1.0, "wristlaser": 0.6}
CURL = (55.0, 75.0, 50.0)
SPINE_JOINT, SPINE_PARENT = "player01_spine_TopSHJnt", "player01_spine_02SHJnt"
def _spine(st):
    sp = getattr(st, "spine_h", None)
    if sp and all(_node_matrix(h_) for h_ in sp):
        return sp
    f_, _ = find_by_walk(player_root(getattr(st, "component", None)), [SPINE_JOINT, SPINE_PARENT])
    sp = (f_.get(SPINE_JOINT), f_.get(SPINE_PARENT))
    st.spine_h = sp if all(sp) else None
    return st.spine_h
def _torso(st, kind, look, up, o_r, e):
    how = TORSO.get(kind)
    sp = _spine(st)
    if not how or not sp:
        return
    h, par = sp
    m = _node_matrix(h)
    if not m:
        return
    base = st.arm_base = getattr(st, "arm_base", {})
    last = st.arm_last = getattr(st, "arm_last", {})
    cur = list(F16.from_address(m))
    if last.get(h) == cur and h in base:
        cur = list(base[h])
    else:
        base[h] = list(cur)
    Wp = _abs_full(par)
    if Wp is None:
        return
    W = _m3mul(_m3(cur), Wp)
    kind_, deg = how
    rt = _norm(_cross(look, up))[0]
    if kind_ == "arch":
        ax, ang = rt, math.radians(deg) * e
    else:
        sgn = 1.0 if _dot(_cross(o_r, look), up) > 0 else -1.0
        ax, ang = up, math.radians(deg) * e * sgn
    out = _local_from(cur, _q_apply(W, _q_axis(ax, ang)), Wp)
    if out is not None:
        _set_local(h, ctypes.addressof(out))
        last[h] = list(out)
def _finger_handles(st, sd):
    fh = getattr(st, "finger_h", None) or {}
    if fh.get(sd) and all(_node_matrix(h_) for ch in fh[sd] for h_ in ch):
        return fh[sd]
    names = [f"player01_{sd}_hand_0{f}_0{j}SHJnt" for f in range(1, 6) for j in range(1, 4)]
    f_, _ = find_by_walk(player_root(getattr(st, "component", None)), names)
    chains = [[f_.get(f"player01_{sd}_hand_0{f}_0{j}SHJnt") for j in range(1, 4)] for f in range(1, 6)]
    fh[sd] = [c for c in chains if all(c)] or None
    st.finger_h = fh
    return fh[sd]
def _fingers(st, sd, wrist, kind, e):
    fist, opn = FIST.get(kind, 0.0), OPEN.get(kind, 0.0)
    if (fist <= 0 and opn <= 0) or wrist is None:
        return
    chains = _finger_handles(st, sd)
    if not chains:
        return
    Ww, f_dir, palm = wrist
    axis = _norm(_cross(f_dir, palm))[0]
    base = st.arm_base = getattr(st, "arm_base", {})
    last = st.arm_last = getattr(st, "arm_last", {})
    for fi, chain in enumerate(chains):
        thumb = fi == 0
        Wpar = Ww
        for ji, h in enumerate(chain):
            m = _node_matrix(h)
            if not m:
                break
            cur = list(F16.from_address(m))
            if last.get(h) == cur and h in base:
                cur = list(base[h])
            else:
                base[h] = list(cur)
            W = _m3mul(_m3(cur), Wpar)
            if fist > 0:
                ang = math.radians(CURL[ji] * (0.45 if thumb else 1.0)) * fist * e
            else:
                fd = _norm(W[0])[0]
                bend = math.asin(max(-1.0, min(1.0, _dot(fd, palm))))
                ang = -bend * opn * e * (0.0 if thumb else 1.0)
            W2 = _q_apply(W, _q_axis(axis, ang))
            out = _local_from(cur, W2, Wpar)
            if out is None:
                break
            _set_local(h, ctypes.addressof(out))
            last[h] = list(out)
            Wpar = W2
def _recoil_step(st, w_obj, sel, firing, dt):
    try:
        clip = ctypes.c_int32.from_address(w_obj + 0x24B0 + 4 * sel).value if 0 <= sel < 32 else 0
    except Exception:
        clip = 0
    prev = getattr(st, "clip_prev", None)
    if firing and prev is not None and clip < prev:
        st.recoil = 1.0
    st.clip_prev = clip
    st.recoil = getattr(st, "recoil", 0.0) * math.exp(-dt / RECOIL_TC)
    return st.recoil
def _apply_recoil(T, kind, look, up, k):
    g = GUN_ARM
    if kind not in RECOIL_KINDS or k < 0.01 or g not in T or T[g][0] == "ik":
        return T
    rt = _norm(_cross(look, up))[0]
    a = math.radians(RECOIL_DEG) * k
    rot_ = lambda v, f: _rot(v, rt, math.cos(a * f), math.sin(a * f))
    u, f, fg, pm_ = T[g]
    T = dict(T)
    T[g] = (rot_(u, -0.35), rot_(f, -1.0), rot_(fg, -1.6), rot_(pm_, -1.6))
    return T
ARM_REF = 0.5653
LEG_REF = 0.9136
ANKLE_REF = {"FootFX_L": (0.4410, 0.0000, 0.0000), "FootFX_R": (-0.4410, 0.0000, 0.0000)}
FOOT_FX = {"FootFX_L": "player01_l_leg_AnkleSHJnt", "FootFX_R": "player01_r_leg_AnkleSHJnt"}
FOOT_REF = 0.1658
FOOT_BALL = {"FootFX_L": "player01_l_leg_BallSHJnt", "FootFX_R": "player01_r_leg_BallSHJnt"}
FOOT_KNEE = {"FootFX_L": "player01_l_leg_KneeSHJnt", "FootFX_R": "player01_r_leg_KneeSHJnt"}
def _arm_k(arm_len):
    return max(0.6, min(1.5, arm_len / ARM_REF))
def _body_fit(st):
    root = player_root(getattr(st, "component", None))
    bf = getattr(st, "body_fit", None)
    if bf and bf[0] == root:
        return bf[1]
    k = (1.0, 1.0)
    try:
        names = [f"player01_l_leg_{j}SHJnt" for j in ("Hip", "Knee", "Ankle")]
        f_, _ = find_by_walk(root, names)
        hs = _arm_handles(st)
        if all(n in f_ for n in names) and hs:
            P = [_abs_pos(f_[n]) for n in names]
            leg = sum(math.sqrt(_dot(_add(P[i + 1], _scale(P[i], -1)), _add(P[i + 1], _scale(P[i], -1)))) for i in (0, 1))
            A = [_abs_pos(hs["l"][i]) for i in (1, 2, 3)]
            arm = sum(math.sqrt(_dot(_add(A[i + 1], _scale(A[i], -1)), _add(A[i + 1], _scale(A[i], -1)))) for i in (0, 1))
            k = (max(0.6, min(1.5, leg / LEG_REF)), _arm_k(arm))
            log.info(f"body fit: legs {leg:.3f} m (x{k[0]:.2f}), arms {arm:.3f} m (x{k[1]:.2f}) vs Anomaly body 1")
    except Exception as e:
        log.info(f"body fit failed {e!r}")
    st.body_fit = (root, k)
    return k
def _fit_feet(st):
    root = player_root(getattr(st, "component", None))
    ff = getattr(st, "feet_fit2", None)
    if ff and ff[0] == root:
        return
    f_, _ = find_by_walk(root, list(FOOT_FX) + list(FOOT_FX.values()) + list(FOOT_BALL.values()) + list(FOOT_KNEE.values()))
    done = []
    for fx, an in FOOT_FX.items():
        h, ha = f_.get(fx), f_.get(an)
        m, ma = (_node_matrix(h) if h else None), (_node_matrix(ha) if ha else None)
        if not m or not ma:
            continue
        cur = list(F16.from_address(m))
        ank = list(F16.from_address(ma))[12:15]
        base = getattr(st, "feet_base", {}).get(h) or cur[12:15]
        st.__dict__.setdefault("feet_base", {})[h] = base
        off = [base[i] - ANKLE_REF[fx][i] for i in range(3)]
        try:
            A, B, K = (_abs_pos(f_[n]) for n in (an, FOOT_BALL[fx], FOOT_KNEE[fx]))
            foot = math.sqrt(_dot(_add(B, _scale(A, -1)), _add(B, _scale(A, -1))))
            shin_w = math.sqrt(_dot(_add(A, _scale(K, -1)), _add(A, _scale(K, -1))))
            shin_l = math.sqrt(_dot(ank, ank))
            k = (foot / FOOT_REF) / (shin_w / shin_l) if shin_l > 1e-4 and shin_w > 1e-4 else 1.0
            k = max(0.5, min(2.5, k))
        except Exception:
            k = 1.0
        want = [ank[i] + off[i] * k for i in range(3)]
        out = F16(*cur)
        out[12:15] = want
        if _finite(list(out)):
            _set_local(h, ctypes.addressof(out))
            done.append(f"{fx} moved {math.sqrt(sum((want[i] - base[i]) ** 2 for i in range(3))):.3f} (x{k:.2f})")
    if done:
        log.info("feet fit: " + ", ".join(done))
    st.feet_fit2 = (root, done)
def _fire_poses(st):
    w_obj, fl = _arms_state()
    on = bool(fl & ARMS_ON) and w_obj
    act = nms().Engine.SetNodeActivation
    tool = _tool_model(st) if (on or getattr(st, "tool_hidden", False)) else None
    if tool:
        if on:
            act(_tk(tool), False)
            st.tool_hidden = True
        elif getattr(st, "tool_hidden", False):
            act(_tk(tool), True)
            st.tool_hidden = False
    now = time.perf_counter()
    dt = min(0.1, now - getattr(st, "fp_t", now))
    st.fp_t = now
    kind = None
    if on:
        try:
            kind = FIRE_POSES.get(ctypes.c_int32.from_address(w_obj + WEAPON_SEL).value)
        except Exception:
            kind = None
    firing = on and kind and (bool(_raw_key(0x01) & 0x8000) or _pad_read()[4] > 0.5) and _fg()
    if firing:
        st.fp_last, st.fp_kind = now, kind
    want = 1.0 if (on and now - getattr(st, "fp_last", -9.0) < POSE_HOLD) else 0.0
    wv = getattr(st, "fp_w", 0.0)
    wv += (dt / POSE_IN) if want > wv else -(dt / POSE_OUT)
    st.fp_w = wv = max(0.0, min(1.0, wv))
    if getattr(st, "sock_last", None) is not None and getattr(st, "sock_base", None):
        try:
            f_, _ = find_by_walk(player_root(getattr(st, "component", None)), [SOCKET_JOINT])
            if f_.get(SOCKET_JOINT):
                _set_local(f_[SOCKET_JOINT], ctypes.addressof(F16(*st.sock_base)))
        finally:
            st.sock_last = None
    eq = _quarter_arms(st, dt)
    if wv <= 0.0 or not getattr(st, "fp_kind", None):
        st.fp_e, st.fp_arms, st.fp_wr = 0.0, (), {}
        if eq > 0.0:
            _quarter_wrists(st, eq)
        return
    fr = _cam_frame()
    hs = _arm_handles(st)
    if fr is None or not hs:
        return
    e = wv * wv * (3 - 2 * wv)
    ROLE = {"r": GUN_ARM, "l": "r" if GUN_ARM == "l" else "l"}
    out_sk = _arm_out(st, hs, fr[0], fr[1])
    T0 = _pose_targets(st.fp_kind, fr[0], fr[1], {"r": out_sk[ROLE["r"]], "l": out_sk[ROLE["l"]]})
    T = {ROLE[k]: v for k, v in T0.items()}
    sel_ = ctypes.c_int32.from_address(w_obj + WEAPON_SEL).value if w_obj else -1
    T = _apply_recoil(T, st.fp_kind, fr[0], fr[1], _recoil_step(st, w_obj, sel_, firing, dt))
    _torso(st, st.fp_kind, fr[0], fr[1], out_sk[GUN_ARM], e)
    wrs = {}
    for sd, tgt in T.items():
        wr = _solve_arm(st, hs[sd], tgt, e)
        _fingers(st, sd, wr, st.fp_kind, e)
        wrs[sd] = wr
    st.fp_e, st.fp_arms, st.fp_wr = e, tuple(T), wrs
    if eq > 0.0:
        _quarter_wrists(st, eq)
def _quarter_arms(st, dt):
    thr = _throttle()
    tgt = 0.0
    if thr is not None and _quarter_live(st, time.perf_counter()):
        kd = lambda vk: 1 if _key(vk) & 0x8000 else 0
        tgt = _quarter_on(thr, kd(0x57) - kd(0x53),
                          bool(getattr(st, "space_on", False) or getattr(st, "tilt_space", False)),
                          getattr(st, "in_water", False))
    if tgt <= 0.0 and getattr(st, "qa_w", 0.0) <= 0.0 and getattr(st, "qa_wv", 0.0) == 0.0:
        st.qa_out = None
        return 0.0
    if tgt <= 0.0:
        now_ = time.perf_counter()
        qo = getattr(st, "qa_out", None)
        if qo is None:
            qo = st.qa_out = (now_, getattr(st, "qa_w", 0.0))
        u = min(1.0, (now_ - qo[0]) / QUARTER_UNTILT)
        st.qa_w, st.qa_wv = qo[1] * (1.0 - u * u * (3.0 - 2.0 * u)), 0.0
        if u >= 1.0:
            st.qa_w = 0.0
    else:
        st.qa_out = None
        st.qa_w, st.qa_wv = _quarter_ease(getattr(st, "qa_w", 0.0), getattr(st, "qa_wv", 0.0), tgt, dt)
    x_t = _quarter_x(thr) if thr is not None else getattr(st, "q_x", 0.0)
    x_, st.qx_v = _cd(getattr(st, "qx_w", x_t), getattr(st, "qx_v", 0.0), x_t, QUARTER_X_TIME, dt)
    st.qx_w = min(1.0, max(0.0, x_))
    return st.qa_w * st.qx_w
QUARTER_WRIST_FREE = True
NODE_TABLE = 0x6EFE830
_anim_vcall = CFUNCTYPE(c_uint64, c_uint64)
def _joint_anim_flag(h):
    try:
        g = u64(BASE + NODE_TABLE)
        if not g:
            return None
        idx = ctypes.c_int32.from_address(u64(g + 0xE8) + (h & 0x7FFFF) * 4).value
        if idx < 0 or ctypes.c_ubyte.from_address(u64(g + 0xA0) + idx).value != 4:
            return None
        node = u64(u64(g + 0x90) + idx * 8)
        if not node:
            return None
        obj = node + 0x38
        inst = _anim_vcall(u64(u64(obj) + 0x50))(obj)
        if not inst:
            return None
        arr = u64(inst + 0x178)
        ji = ctypes.c_int32.from_address(node + 0x40).value
        return arr + ji if arr and 0 <= ji < 512 else None
    except Exception:
        return None
def _quarter_wrists(st, amt):
    if amt <= 1e-4 or not _quarter_live(st, time.perf_counter()):
        return
    hs = _arm_handles(st)
    out = getattr(st, "drawn_prev", None)
    if not hs or not out or len(out) < 12:
        return
    B, nb = _norm(list(out[4:7]))
    D, nd = _norm(list(out[8:11]))
    if nb < 0.5 or nd < 0.5:
        return
    D, nd = _norm(_add(D, _scale(B, -_dot(D, B))))
    if nd < 0.5:
        return
    tdir = _quarter_palm_dir(B, D)
    fe, fa, fw = getattr(st, "fp_e", 0.0), getattr(st, "fp_arms", ()) or (), getattr(st, "fp_wr", None) or {}
    base = st.arm_base = getattr(st, "arm_base", {})
    last = st.arm_last = getattr(st, "arm_last", {})
    for sd in "lr":
        held = sd in fa and fe > 0.0
        a = amt * ((1.0 - fe) if held else 1.0)
        if a <= 1e-4 or len(hs[sd]) < 7 or not all(hs[sd][2:7]):
            continue
        elb, wri = hs[sd][2], hs[sd][3]
        m = _node_matrix(wri)
        ms = [_node_matrix(h_) for h_ in hs[sd][4:7]]
        if not m or not all(ms) or not _node_matrix(elb):
            continue
        cur = list(F16.from_address(m))
        if held:
            wr = fw.get(sd)
            Li = _m3inv(_m3(cur)) if wr else None
            if Li is None:
                continue
            Ww = wr[0]
            We = _m3mul(Li, Ww)
        else:
            if last.get(wri) == cur and wri in base:
                cur = list(base[wri])
            else:
                base[wri] = list(cur)
            We = _abs_full(elb)
            if We is None:
                continue
            Ww = _m3mul(_m3(cur), We)
        tm, ti, tp = (list(F16.from_address(x_))[12:15] for x_ in ms)
        n = _palm_normal(Ww, tm, ti, tp, PALM_SIGN[sd])
        if n is None:
            continue
        Ww2 = _q_apply(Ww, _quarter_tilt(n, tdir, a))
        o = _local_from(cur, Ww2, We)
        if o is None:
            continue
        _set_local(wri, ctypes.addressof(o))
        last[wri] = list(o)
        if QUARTER_WRIST_FREE:
            fl_ = st.wr_flag = getattr(st, "wr_flag", {})
            if wri not in fl_:
                fl_[wri] = _joint_anim_flag(wri)
            if fl_[wri]:
                ctypes.c_ubyte.from_address(fl_[wri]).value = 0
MAP_KINDS = {"cube": 1, "sphere": 2, "freighter": 3, "station": 4, "nexus": 5, "shipmarker_square": 6,
             "shipmarker_neutral": 7, "shipmarker_squadgreen": 8}
MAP_MAX, MAP_EVERY = 96, 0.1
try:
    _MAPSHM = _mmap.mmap(-1, 16 + 16 * MAP_MAX, tagname="IronManFlightMap")
except Exception:
    _MAPSHM = None
LIVE_FAR = 2.0e6
LIVE_NEAR = 100.0
LIVE_EVERY = 0.15
LIVE_FAMILIES = (
    ("SPACESTATION", 4), ("NEXUSEXTERIOR", 5), ("FREIGHTER_PROC", 3), ("FRIGATE", 7),
    ("SPACEPOISITE", 1), ("TERRAINFLATTENMARKER", 1), ("NPCGEK", 8),
)
def _sim_nodes(st):
    sn = getattr(st, "sim_nodes", None)
    if sn and all(_node_matrix(sn[k_]) for k_ in ("Objects", "Space") if k_ in sn):
        return sn
    import nmspy.data.types as nms_
    from nmspy.data.basic_types import TkHandle as TkH_
    nm_ = lambda h: (lambda n: n.decode(errors="replace") if isinstance(n, bytes) else str(n))(nms_.Engine.GetNodeName(_tk(h)))
    n_ = player_root(getattr(st, "component", None))
    for _ in range(6):
        o_ = TkH_()
        nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(n_))
        if not o_.lookupInt or o_.lookup == 0x3FFFF:
            return None
        n_ = o_.lookupInt
        if nm_(n_) == "Simulation-Root":
            st.sim_nodes = {nm_(c): c for c in children(n_)}
            return st.sim_nodes
    return None
def _live_markers(st):
    import nmspy.data.types as nms_
    sn = _sim_nodes(st)
    if not sn:
        return []
    nm_ = lambda h: (lambda n: n.decode(errors="replace") if isinstance(n, bytes) else str(n))(nms_.Engine.GetNodeName(_tk(h)))
    out = []
    for parent in ("Objects", "Space"):
        for c in children(sn.get(parent)) if sn.get(parent) else ():
            name = nm_(c).upper()
            for key, kind in LIVE_FAMILIES:
                if key in name and nms_.Engine.GetNodeActivation(_tk(c)):
                    out.append((kind, _abs_pos(c)))
                    break
    terrain = sn.get("Terrain")
    for t in children(terrain) if terrain else ():
        if nm_(t) == "PlanetRoot":
            for pl in children(t):
                out.append((2, _abs_pos(pl)))
    return out
def _live_rows(st):
    fr = _cam_frame()
    root = player_root(getattr(st, "component", None))
    if fr is None or not root:
        return []
    me = _abs_pos(root)
    up = _norm(_v(st.player + 0x320))[0] if getattr(st, "player", None) else fr[1]
    if not _finite(up) or _dot(up, up) < 0.5:
        up = fr[1]
    fwd, fn = _norm(_add(fr[0], _scale(up, -_dot(fr[0], up))))
    if fn < 0.2:
        return []
    rt = _cross(fwd, up)
    rows = []
    k_far = math.log10(1 + LIVE_FAR / LIVE_NEAR)
    for kind, p_ in _live_markers(st):
        d = _add(p_, _scale(me, -1.0))
        dist = math.sqrt(_dot(d, d))
        if dist < 5.0 or abs(dist - 101652) < 1.0:
            continue
        if kind == 2 and dist < 150000:
            continue
        r = 5.0 * min(1.0, math.log10(1 + dist / LIVE_NEAR) / k_far)
        f = r / dist
        rows.append((kind, _dot(d, rt) * f, _dot(d, up) * f, -_dot(d, fwd) * f))
    return rows
CROSS_ON = True
CROSS_POSE_CARRY = True
CROSS_DRAW_EASE = 0.45
CROSS_CLOSE_DIST = 6.5
CROSS_CLOSE_EASE = 1.5
CROSS_CLOSE_WAIT = 0.4
CROSS_SMOOTH = (0.15, 0.15)
CROSS_SMOOTH_FOR = 2.5
_CLOSE_RVA = 0x5043150 + 0x5060
CROSS_HOOK = "graphics"
CROSS_MAX = 2.5
CROSS_LEVEL = 0.5
CROSS_LEVEL_FRAMES = 3
CROSS_MIN = 0.4
CROSS_PITCH_LIM = 57.0
CROSS_PITCH_EASE = 40.0
CROSS_JUMP = 10.0
CROSS_FACE_AFTER = 0.35
CROSS_CAM_LAG = 0.07
CROSS_LEAD = 0.0
CROSS_RATE_SMOOTH = 0.03
CROSS_FB = 6.0
CROSS_FB_MAX = 25.0
CROSS_FB_OFF = 10.0
CROSS_FB_FADE = 0.06
_HANDOFF = (0x2A10, 0x2A20)
_LIVE = (0x21D0, 0x21E0)
def _f2(a):
    return list((ctypes.c_float * 2).from_address(a))
def _w2(a, y, p):
    m = (ctypes.c_float * 2).from_address(a)
    m[0], m[1] = y, p
def _frame3(up, at):
    a_ = _norm(_add(at, _scale(up, -_dot(at, up))))[0]
    return [_cross(up, a_), list(up), a_]
def _frame_follow(A, B, k):
    m = [[sum(B[k_][i] * A[k_][j] for k_ in range(3)) for j in range(3)] for i in range(3)]
    tr = m[0][0] + m[1][1] + m[2][2]
    w = math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0)))
    if w < 1e-6:
        return [list(r) for r in B]
    s_ = 2.0 * math.sin(w)
    if abs(s_) < 1e-6:
        return [list(r) for r in B]
    ax = [(m[2][1] - m[1][2]) / s_, (m[0][2] - m[2][0]) / s_, (m[1][0] - m[0][1]) / s_]
    c, sn = math.cos(w * k), math.sin(w * k)
    return [_rot(r, ax, c, sn) for r in A]
RVA_QA_TRIGGER = 0x1562220
RVA_MENU_ACTION = 0x1469150
QA_MENU = 0x86FCA0
QA_VTABLE = 0x4B1D1C0
QA_RECOVERY_SHIP, QA_SUMMON_NEXUS = 5, 3
_qa_trigger = CFUNCTYPE(c_bool, c_void_p, c_void_p, c_bool)(BASE + RVA_QA_TRIGGER)
_menu_action = CFUNCTYPE(None, c_void_p, ctypes.c_int32, c_uint32, c_bool, c_bool)(BASE + RVA_MENU_ACTION)
def quick_action(action, as_menu=False):
    data_ = c_uint64.from_address(BASE + CAM_DATA).value
    if not data_:
        return None
    inst = data_ + QA_MENU
    if c_uint64.from_address(inst).value != BASE + QA_VTABLE:
        return None
    buf = (c_uint64 * 0x40)()
    _menu_action(ctypes.addressof(buf), 0, action, False, True)
    return bool(_qa_trigger(inst, ctypes.addressof(buf), bool(as_menu)))
def quick_action_live(action, as_menu=True):
    data_ = c_uint64.from_address(BASE + CAM_DATA).value
    inst = data_ + QA_MENU if data_ else 0
    if not inst or c_uint64.from_address(inst).value != BASE + QA_VTABLE:
        return None
    n_ = ctypes.c_uint32.from_address(inst + 0xA050 + 8 + 4).value
    ptr = c_uint64.from_address(inst + 0xA050 + 16).value
    if not ptr or not 0 < n_ < 40:
        return None
    for k in range(n_):
        e_ = ptr + k * 0xE0
        if ctypes.c_int32.from_address(e_ + 4).value == action:
            return bool(_qa_trigger(inst, e_, bool(as_menu)))
    return None
RVA_SET_TO_POSITION = 0x1495CF0
_TP_REGION = CFUNCTYPE(c_uint64, c_void_p, c_uint64)(BASE + 0x2D5CA60)
_TP_REGION_DEF = CFUNCTYPE(c_uint64)(BASE + 0x2D5CA90)
_TP_TO_LOCAL = CFUNCTYPE(None, c_void_p, c_void_p, c_uint64)(BASE + 0x2D5C070)
_TP_PLAYER_POS = CFUNCTYPE(None, c_void_p, c_void_p)(BASE + 0x14B3860)
_TP_BODY_POS = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32)(BASE + 0x2D18EA0)
_TP_BODY_VEL = CFUNCTYPE(None, c_void_p, c_void_p)(BASE + 0x29A0C0)
_TP_BODY_RB = CFUNCTYPE(c_uint64, c_void_p)(BASE + 0x2D144D0)
_TP_RB_VEL = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32)(BASE + 0x2D3A2C0)
_TP_FACE = CFUNCTYPE(None, c_void_p, c_void_p)(BASE + 0x2B2450)
_TP_AFTER = CFUNCTYPE(None, c_void_p, c_float)(BASE + 0x154DD30)
_TP_CTRL_TM = CFUNCTYPE(None, c_void_p, c_void_p)(BASE + 0x575AD0)
TP_REGION_GLOBAL = 0x5371260
TP_DATA_REGION = 0x72D088
def _aligned(n, vals=None):
    buf = ctypes.create_string_buffer(n + 16)
    a = (ctypes.addressof(buf) + 15) & ~15
    if vals is not None:
        (ctypes.c_float * len(vals)).from_address(a)[:] = [float(x) for x in vals]
    return buf, a
def player_to(player, world, look, vel=(0.0, 0.0, 0.0), offset=None):
    off = list(offset) if offset is not None else _v(player + 0x350)
    loc = [world[i] - off[i] for i in range(3)]
    pk, pa = _aligned(32, loc + [0.0] + off + [1024.0])
    data_ = c_uint64.from_address(BASE + CAM_DATA).value
    key = c_uint64.from_address(data_ + TP_DATA_REGION).value
    rg = _TP_REGION(BASE + TP_REGION_GLOBAL, key)
    rg = _TP_REGION(BASE + TP_REGION_GLOBAL, key) if rg else _TP_REGION_DEF()
    lk, la = _aligned(32)
    _TP_TO_LOCAL(la, pa, rg)
    ctypes.memmove(player + 0x34B0, la, 32)
    ctypes.memmove(player + 0x33F0, la, 32)
    (ctypes.c_float * 4).from_address(player + 0x360)[:] = [loc[0] + off[0], loc[1] + off[1], loc[2] + off[2], 1024.0]
    ctypes.memmove(player + 0x3410, pa, 32)
    ctypes.c_uint8.from_address(player + 0x5781).value = 1
    _TP_PLAYER_POS(player, pa)
    body = c_uint64.from_address(player + 0x160).value
    _TP_BODY_POS(body, pa, 0)
    vk, va = _aligned(16, list(vel) + [0.0])
    _TP_BODY_VEL(body, va)
    _TP_RB_VEL(_TP_BODY_RB(body), va, 0)
    dk, da = _aligned(16, list(look) + [0.0])
    _TP_FACE(player, da)
    ctypes.c_uint8.from_address(player + 0x5958).value = 1
    _TP_AFTER(c_uint64.from_address(player + 0x148).value, 0.0)
    tk, ta = _aligned(48)
    _TP_CTRL_TM(c_uint64.from_address(c_uint64.from_address(player + 0x160).value + 0xC0).value, ta)
    ctypes.memmove(player + 0x2E0, ta, 48)
PHYS_LIMIT = 19968.0
class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", c_void_p), ("AllocationBase", c_void_p), ("AllocationProtect", ctypes.c_uint32),
                ("PartitionId", ctypes.c_uint16), ("RegionSize", ctypes.c_size_t), ("State", ctypes.c_uint32),
                ("Protect", ctypes.c_uint32), ("Type", ctypes.c_uint32)]
def _writable(a, n):
    m = _MBI()
    if not ctypes.windll.kernel32.VirtualQuery(c_void_p(a), ctypes.byref(m), ctypes.sizeof(m)):
        return False
    base = m.BaseAddress or 0
    return m.State == 0x1000 and m.Protect in (0x04, 0x40) and base <= a and a + n <= base + m.RegionSize
WATER_GROUND_GUARD = 5.0
WATER_BODY_LIMIT = 19.0
def _water_drive(st, player, now, lt):
    s_ = _steer()
    vel = s_[3] if s_ else None
    body = c_uint64.from_address(player + 0x160).value
    if not vel or not body or not _finite(vel):
        return
    sp = math.sqrt(_dot(vel, vel))
    if sp > 2000.0:
        return
    f_ = min(1.0, WATER_BODY_LIMIT / sp) if sp > 0 else 1.0
    comp_ = getattr(st, "component", None)
    try:
        if not comp_ or c_uint32.from_address(comp_ + 0x214).value not in (12, 13):
            f_ = 1.0
    except Exception:
        f_ = 1.0
    dt = min(0.05, now - lt)
    if f_ < 1.0 and dt > 0.0 and _JET is not None:
        va = _struct.unpack_from("<Q", _JET, 16)[0]
        if va and (va == getattr(st, "wd_va", None) or _writable(va - 0x20, 48)):
            st.wd_va = va
            r_ = (c_float * 12).from_address(va - 0x20)
            if r_[3] == 1.0 and r_[7] == 1024.0 and _finite(list(r_)):
                k = (1.0 - f_) * dt
                mv = list(vel)
                g_ = getattr(st, "gnd", None)
                if g_ is not None and math.isfinite(g_) and g_ < WATER_GROUND_GUARD:
                    up_ = _norm(_v(player + 0x320))[0]
                    dn_ = _dot(mv, up_)
                    if dn_ < 0.0:
                        mv = [mv[i] - up_[i] * dn_ for i in range(3)]
                pk, pa = _aligned(32, [r_[0] + mv[0] * k, r_[1] + mv[1] * k, r_[2] + mv[2] * k, 0.0,
                                       r_[4], r_[5], r_[6], 1024.0])
                _TP_BODY_POS(body, pa, 0)
            else:
                f_ = 1.0
        else:
            f_ = 1.0
    vk, vb = _aligned(16, [vel[0] * f_, vel[1] * f_, vel[2] * f_, 0.0])
    _TP_BODY_VEL(body, vb)
    _TP_RB_VEL(_TP_BODY_RB(body), vb, 0)
    st.wh_n = getattr(st, "wh_n", 0) + 1
    if st.wh_n % 300 == 1:
        log.info(f"water drive: {sp:.1f} m/s ({min(sp, WATER_BODY_LIMIT):.1f} by the physics, the rest moved on)")
def _cruise_advance(st, player):
    now = time.perf_counter()
    lt, st.adv_t = getattr(st, "adv_t", now), now
    if _water_on():
        _water_drive(st, player, now, lt)
        return
    if not _cruise_on() or _JET is None:
        return
    s_ = _steer()
    vel = s_[3] if s_ else None
    if not vel:
        return
    sp = math.sqrt(_dot(vel, vel))
    dt = min(0.05, now - lt)
    if sp <= PHYS_LIMIT * 1.001 or dt <= 0.0:
        return
    va = _struct.unpack_from("<Q", _JET, 16)[0]
    if not va:
        return
    if va != getattr(st, "adv_va", None):
        st.adv_va, st.adv_ok = va, False
        if _writable(va - 0x20, 48):
            r_ = (c_float * 12).from_address(va - 0x20)
            st.adv_ok = (r_[3] == 1.0 and r_[7] == 1024.0 and all(abs(r_[4 + i]) % 1024.0 == 0.0 for i in range(3))
                         and _finite(list(r_)))
        log.info(f"cruise advance: body record at 0x{va - 0x20:X} {'ok' if st.adv_ok else 'NOT recognised: off'}")
    if not st.adv_ok:
        return
    r_ = (c_float * 12).from_address(va - 0x20)
    if r_[3] != 1.0 or r_[7] != 1024.0:
        return
    k = (sp - PHYS_LIMIT) / sp * dt
    body = c_uint64.from_address(player + 0x160).value
    if not body:
        return
    pk, pa = _aligned(32, [r_[0] + vel[0] * k, r_[1] + vel[1] * k, r_[2] + vel[2] * k, 0.0, r_[4], r_[5], r_[6], 1024.0])
    _TP_BODY_POS(body, pa, 0)
    f_ = PHYS_LIMIT / sp
    vk, vb = _aligned(16, [vel[0] * f_, vel[1] * f_, vel[2] * f_, 0.0])
    _TP_BODY_VEL(body, vb)
    _TP_RB_VEL(_TP_BODY_RB(body), vb, 0)
try:
    _WARP = _mmap.mmap(-1, 128, tagname="IronManFlightWarp")
except Exception:
    _WARP = None
def _warp_request(st):
    if _WARP is None or not getattr(st, "player", None):
        return
    req = _struct.unpack_from("<I", _WARP, 0)[0]
    if req == getattr(st, "warp_req", None):
        return
    first = getattr(st, "warp_req", None) is None
    st.warp_req = req
    if first:
        return
    v_ = _struct.unpack_from("<12d", _WARP, 8)
    st.tp_pending = (v_[0:3], v_[9:12], v_[6:9], v_[3:6], req)
def _nexus_nodes(st):
    import nmspy.data.types as nms_
    sn = _sim_nodes(st)
    objs = sn.get("Objects") if sn else None
    out = []
    for c in children(objs) if objs else ():
        nm = (node_name(c) or "").upper()
        if "NEXUS" in nm:
            out.append((c, nm.rsplit("/", 1)[-1], bool(nms_.Engine.GetNodeActivation(_tk(c))), _abs_pos(c)))
    return out
def _tp_run(st, player):
    tp_ = getattr(st, "tp_pending", None)
    if not tp_:
        return
    st.tp_pending = None
    world, look, vel, off, req = tp_
    try:
        player_to(player, world, look, vel, off)
        log.info(f"put at {[round(x, 1) for x in world]} (pull {req})")
    except Exception as e:
        log.info(f"put at {[round(x, 1) for x in world]} FAILED {e!r}")
    if req is not None and _in_nexus_box(world) and not getattr(st, "nexus_keep", None):
        try:
            _nexus_on(st)
        except Exception as e:
            log.info(f"nexus: switching its inside on failed {e!r}")
    if req is not None and _WARP is not None:
        _WARP[4:8] = _struct.pack("<I", req)
QA_GALAXY_MAP = 0x14
QA_TABLE = 0xA050
MENU_ACTION_SIZE = 0xE0
def _qmenu_entries(inst, depth=0):
    cap = ctypes.c_uint32.from_address(inst + QA_TABLE + 8 + 16 * depth).value
    n_ = ctypes.c_uint32.from_address(inst + QA_TABLE + 12 + 16 * depth).value
    return cap, n_, c_uint64.from_address(inst + QA_TABLE + 16 + 16 * depth).value
QMENU_EXTRA = ((QA_SUMMON_NEXUS, 0xA098), (QA_GALAXY_MAP, 0xA0D8))
QA_PHOTO_MODE = 0x15
RVA_CAN_SUMMON_NEXUS = 0x167F020
_can_summon_nexus = CFUNCTYPE(c_bool, c_void_p, c_uint32)(BASE + RVA_CAN_SUMMON_NEXUS)
def qmenu_add_after(st, actions, action):
    data_ = c_uint64.from_address(BASE + CAM_DATA).value
    inst = data_ + QA_MENU if data_ else 0
    if not inst or actions != inst + QA_TABLE + 8 or not action:
        return
    if _JET is not None:
        try:
            _JET[8:16] = _struct.pack("<d", time.perf_counter())
        except Exception:
            pass
    if ctypes.c_int32.from_address(action + 4).value != QA_PHOTO_MODE or not getattr(st, "shown", False):
        return
    if c_uint64.from_address(inst).value != BASE + QA_VTABLE:
        return
    pl = getattr(st, "player", None)
    if pl and c_uint64.from_address(pl + 0x168).value:
        return
    cap, n_, ptr = _qmenu_entries(inst)
    if not ptr or n_ == 0 or n_ + len(QMENU_EXTRA) > cap:
        return
    have = {ctypes.c_int32.from_address(ptr + k * MENU_ACTION_SIZE + 4).value for k in range(n_)}
    last = ptr + (n_ - 1) * MENU_ACTION_SIZE
    for act, icon_at in QMENU_EXTRA:
        if act in have:
            continue
        dst = ptr + n_ * MENU_ACTION_SIZE
        ctypes.memmove(dst, last, MENU_ACTION_SIZE)
        ctypes.c_int32.from_address(dst).value = ctypes.c_int32.from_address(inst + icon_at).value
        ctypes.c_int32.from_address(dst + 4).value = act
        off = False
        if act == QA_SUMMON_NEXUS:
            try:
                off = not _can_summon_nexus(c_uint64.from_address(data_ + SIM_SOLAR).value, 0)
            except Exception:
                off = False
        ctypes.c_uint8.from_address(dst + 0x4C).value = 1 if off else 0
        n_ += 1
        ctypes.c_uint32.from_address(inst + QA_TABLE + 12).value = n_
def _node_obj(h):
    slot, gen = h & 0x7FFFF, h >> 19
    if not gen or slot == 0x7FFFF:
        return 0, -1
    mgr = u64(BASE + NODE_MGR)
    if not mgr or ctypes.c_uint16.from_address(u64(mgr + 0xF0) + 2 * slot).value != (gen & 0xFFFF):
        return 0, -1
    idx = ctypes.c_int32.from_address(u64(mgr + 0xE8) + 4 * slot).value
    if idx < 0:
        return 0, -1
    return u64(u64(mgr + 0x90) + 8 * idx), ctypes.c_uint8.from_address(u64(mgr + 0xA0) + idx).value
def _cross_close(st, now):
    xc0 = getattr(st, "x_close", None)
    if xc0 is None or getattr(st, "xc", None) is not None:
        return
    t_ = getattr(st, "x_close_t", None)
    if t_ is None:
        st.x_close_t = t_ = now + CROSS_CLOSE_WAIT
    u_ = max(0.0, min(1.0, (now - t_) / CROSS_CLOSE_EASE))
    ctypes.c_float.from_address(BASE + _CLOSE_RVA).value = CROSS_CLOSE_DIST + (xc0 - CROSS_CLOSE_DIST) * _smoothstep(u_, 0.0, 1.0)
    if u_ >= 1.0:
        st.x_close = st.x_close_t = None
def _space_cam_angles(L, R, U, A):
    return (math.degrees(math.atan2(-_dot(L, R), -_dot(L, A))),
            math.degrees(math.asin(max(-1.0, min(1.0, _dot(L, U))))))
def _char_cam_angles(L, U, rB):
    F, fn = _norm(_add(_scale(rB, -1.0), _scale(U, _dot(rB, U))))
    Lh, ln = _norm(_add(L, _scale(U, -_dot(L, U))))
    p = math.degrees(math.asin(max(-1.0, min(1.0, _dot(L, U)))))
    if fn < 0.05 or ln < 0.05:
        return None, p
    return math.degrees(math.atan2(_dot(_cross(F, Lh), U), _dot(F, Lh))), p
def _cross_hold(st, where):
    if where == CROSS_HOOK:
        try:
            _cross_close(st, time.perf_counter())
        except Exception:
            pass
    if not CROSS_ON or where != CROSS_HOOK:
        return
    comp, pl = getattr(st, "component", None), getattr(st, "player", None)
    xc = getattr(st, "xc", None)
    if not comp or not pl or not _flag["want"]:
        st.xc = st.x_last = None
        return
    data = c_uint64.from_address(BASE + CAM_DATA).value
    if not data:
        return
    mgr = data + CAM_MGR
    if c_uint64.from_address(mgr).value != BASE + CAM_MGR_VTABLE:
        return
    now = time.perf_counter()
    s_ = ctypes.c_uint32.from_address(comp + 0x214).value
    rU = _norm(_v(pl + 0x1E0))[0]
    if xc is None:
        if s_ == 16:
            fr = _cam_frame()
            st.x_last = (now, rU, fr) if fr else None
            return
        xl = getattr(st, "x_last", None)
        if s_ in (17, 8) and xl and now - xl[0] < 0.5 and _dot(rU, xl[1]) < math.cos(math.radians(2.0)):
            look, up = xl[2]
            G = rU
            h, hn = _norm(_add(look, _scale(G, -_dot(look, G))))
            if hn < 0.05:
                h = _norm(_add(up, _scale(G, -_dot(up, G))))[0]
            p0 = math.degrees(math.asin(max(-1.0, min(1.0, _dot(look, G)))))
            st.xc = dict(t0=now, G=G, h=h, p0=p0, look=look, n=0, lev_n=0, last_y=None,
                         orig={o: _f2(mgr + o) for o in _HANDOFF + _LIVE})
            st.x_last = None
            st.xlog_t0 = now
            st.x_face_until = now + CROSS_MAX + 1.0
            if CROSS_CLOSE_DIST:
                cd_ = ctypes.c_float.from_address(BASE + _CLOSE_RVA)
                if getattr(st, "x_close", None) is None and 0.1 < cd_.value < 20.0:
                    st.x_close = cd_.value
                cd_.value = CROSS_CLOSE_DIST
            st.x_upkeep = now + CROSS_MAX + 1.5
            log.info(f"crossing: keeping your view through the hand-over (pitch {p0:+.0f})")
        return
    if s_ == 16:
        for o, v in xc["orig"].items():
            _w2(mgr + o, *v)
        st.xc = None
        st.x_face_until = 0.0
        log.info("crossing: only a blip, still in space")
        return
    t = now - xc["t0"]
    G, h = xc["G"], xc["h"]
    pt = max(xc["p0"], min(-CROSS_PITCH_LIM, xc["p0"] + CROSS_PITCH_EASE * t)) if xc["p0"] < -CROSS_PITCH_LIM else         min(xc["p0"], max(CROSS_PITCH_LIM, xc["p0"] - CROSS_PITCH_EASE * t))
    cp, sp = math.cos(math.radians(pt)), math.sin(math.radians(pt))
    L = _norm(_add(_scale(h, cp), _scale(G, sp)))[0]
    bU = _norm(_v(pl + 0x320))[0]
    bA = _norm(_v(pl + 0x330))[0]
    lev = math.degrees(math.acos(max(-1.0, min(1.0, _dot(bU, rU)))))
    M = _frame3(bU, bA)
    if xc.get("cam") is None:
        xc["cam"], xc["ct"] = M, now
    else:
        xc["cam"] = _frame_follow(xc["cam"], M, 1.0 - math.exp(-max(0.0, now - xc["ct"]) / CROSS_CAM_LAG))
        xc["ct"] = now
    bR, sU, bA = xc["cam"]
    live = _f2(mgr + _LIVE[0])
    if xc["last_y"] is not None and abs((live[0] - xc["last_y"] + 180.0) % 360.0 - 180.0) > CROSS_JUMP:
        st.xc = None
        st.x_face_until = now + CROSS_FACE_AFTER
        log.info(f"crossing: the game committed early after {t:.2f} s ({xc['n']} frames, body {lev:.1f} deg off)")
        return
    if lev < CROSS_LEVEL and t > CROSS_MIN:
        xc["lev_n"] += 1
    else:
        xc["lev_n"] = 0
    if xc["lev_n"] >= CROSS_LEVEL_FRAMES or t > CROSS_MAX:
        st.xc = None
        st.x_face_until = now + CROSS_FACE_AFTER
        log.info(f"crossing: hand-over done after {t:.2f} s ({xc['n']} frames, body {lev:.1f} deg off the planet's up)")
        return
    ys, ps = _space_cam_angles(L, bR, sU, bA)
    rB = _v(pl + 0x1F0)
    F, fn = _norm(_add(_scale(rB, -1.0), _scale(bU, _dot(rB, bU))))
    ym, pc = _char_cam_angles(L, bU, rB)
    want = [ys, ps, ym if ym is not None else (xc.get("prev") or [0.0, 0.0, 0.0])[2], pc]
    prev, rate = xc.get("prev"), xc.get("rate") or [0.0, 0.0, 0.0, 0.0]
    if prev is not None and now - xc["pt"] > 1e-4:
        dt = now - xc["pt"]
        k = min(1.0, dt / CROSS_RATE_SMOOTH)
        for i in range(4):
            d = want[i] - prev[i]
            if i in (0, 2):
                d = (d + 180.0) % 360.0 - 180.0
            rate[i] += (d / dt - rate[i]) * k
    corr = xc.get("corr") or [0.0, 0.0, 0.0, 0.0]
    fr = _cam_frame()
    if fr is not None and prev is not None and CROSS_FB > 0:
        Lc = fr[0]
        e = [math.degrees(math.atan2(-_dot(Lc, bR), -_dot(Lc, bA))),
             math.degrees(math.asin(max(-1.0, min(1.0, _dot(Lc, sU))))), None,
             math.degrees(math.asin(max(-1.0, min(1.0, _dot(Lc, bU)))))]
        Lch, lcn = _norm(_add(Lc, _scale(bU, -_dot(Lc, bU))))
        if ym is not None and lcn > 0.05:
            e[2] = math.degrees(math.atan2(_dot(_cross(F, Lch), bU), _dot(F, Lch)))
        dt_ = min(0.05, now - xc["pt"]) if "pt" in xc else 0.0
        kf = CROSS_FB * dt_
        if lev < CROSS_FB_OFF:
            corr = [c_ * math.exp(-dt_ / CROSS_FB_FADE) for c_ in corr]
            kf = 0.0
        for i in range(4):
            if e[i] is None or kf <= 0.0:
                continue
            d = want[i] - e[i]
            if i in (0, 2):
                d = (d + 180.0) % 360.0 - 180.0
            corr[i] = max(-CROSS_FB_MAX, min(CROSS_FB_MAX, corr[i] + d * kf))
    xc["corr"] = corr
    xc["prev"], xc["rate"], xc["pt"] = want, rate, now
    ysl = (ys + corr[0] + rate[0] * CROSS_LEAD + 180.0) % 360.0 - 180.0
    psl = max(-85.0, min(85.0, ps + corr[1] + rate[1] * CROSS_LEAD))
    for o in _HANDOFF:
        _w2(mgr + o, ysl, psl)
    if ym is not None:
        yml = (ym + corr[2] + rate[2] * CROSS_LEAD + 180.0) % 360.0 - 180.0
        pcl = max(-85.0, min(85.0, pc + corr[3] + rate[3] * CROSS_LEAD))
        for o in _LIVE:
            _w2(mgr + o, yml, pcl)
        xc["last_y"] = yml
    xc["n"] += 1
def _map_export(st):
    now = time.perf_counter()
    if _MAPSHM is None or now < getattr(st, "map_t", 0.0):
        return
    st.map_t = now + MAP_EVERY
    rows = _live_rows(st)[:MAP_MAX]
    buf = bytearray(16 + 16 * MAP_MAX)
    _struct.pack_into("<dI", buf, 0, now, len(rows))
    for i, (k, x, y, z) in enumerate(rows):
        _struct.pack_into("<I3f", buf, 16 + 16 * i, k, x, y, z)
    _MAPSHM[:len(buf)] = bytes(buf)
SPACE_UNFOLD = False
SPACE_ROOT_CORR = False
UNFOLD_MAX = 80.0
def _node_parent(h):
    import nmspy.data.types as nms_
    from nmspy.data.basic_types import TkHandle as TkH_
    o_ = TkH_()
    nms_.Engine.GetNodeParent(ctypes.byref(o_), _tk(h))
    return o_.lookupInt if o_.lookupInt and o_.lookup != 0x3FFFF else None
def _pos_in(h, stop):
    pos, n = [0.0, 0.0, 0.0], h
    for _ in range(16):
        if n == stop:
            return pos
        m = _node_matrix(n)
        if not m:
            return None
        f = list(F16.from_address(m))
        pos = [sum(pos[k] * f[k * 4 + j] for k in range(3)) + f[12 + j] for j in range(3)]
        n = _node_parent(n)
        if not n:
            return None
    return None
def _space_unfold(st):
    if not SPACE_UNFOLD or not getattr(st, "space_on", False) and             time.perf_counter() - getattr(st, "sp_x_t", -99.0) > SPACE_EXTRA_FADE:
        st.unf_last = None
        return
    hs = getattr(st, "torso_joints", None)
    if not hs or not hs[0] or not hs[1]:
        return
    j, top = hs[0], hs[1]
    root = player_root(getattr(st, "component", None))
    par = _node_parent(j)
    if not root or not par:
        return
    w = 1.0 if getattr(st, "space_on", False) else max(0.0, 1.0 - (time.perf_counter() - getattr(st, "sp_x_t", -99.0)) / SPACE_EXTRA_FADE)
    m = _node_matrix(j)
    if not m:
        return
    cur = list(F16.from_address(m))
    if getattr(st, "unf_last", None) == cur and getattr(st, "unf_base", None):
        cur = list(st.unf_base)
    else:
        st.unf_base = list(cur)
    p_s = _pos_in(top, j)
    pr = _in_root(par, root)
    if p_s is None or not pr:
        return
    L = [cur[0:3], cur[4:7], cur[8:11]]
    P = [_norm(r)[0] for r in pr[1]]
    d = [sum(p_s[k] * L[k][i] for k in range(3)) for i in range(3)]
    d = [sum(d[k] * P[k][i] for k in range(3)) for i in range(3)]
    u, n_ = _norm(d)
    if n_ < 1e-3:
        return
    fold = math.degrees(math.atan2(-u[2], u[1])) - TORSO_PLANET_PITCH
    fold = max(-UNFOLD_MAX, min(UNFOLD_MAX, fold)) * w
    st.unf_fold = fold
    if abs(fold) < 0.5:
        st.unf_last = None
        return
    th = -math.radians(fold)
    c, s_ = math.cos(th), math.sin(th)
    Rx = [[1.0, 0.0, 0.0], [0.0, c, s_], [0.0, -s_, c]]
    mul = lambda A, B: [[sum(A[i][k] * B[k][j_] for k in range(3)) for j_ in range(3)] for i in range(3)]
    PT = [[P[k][i] for k in range(3)] for i in range(3)]
    Lr = mul(L, mul(mul(P, Rx), PT))
    out = F16(*cur)
    for r in range(3):
        out[r * 4:r * 4 + 3] = Lr[r]
    if not _finite(out):
        return
    _set_local(j, ctypes.addressof(out))
    st.unf_last = list(out)
def graphics_after(st, player, set_node):
    _graphics_after(st, player, set_node)
    try:
        _space_unfold(st)
    except Exception:
        if "space_unfold" not in st.errors:
            st.errors.add("space_unfold")
            log.exception("the space unfold failed (repeats not logged)")
    try:
        _fire_poses(st)
    except Exception:
        if "fire_poses" not in st.errors:
            st.errors.add("fire_poses")
            log.exception("fire poses failed (repeats not logged)")
SPEED_LEAD = 1.0
SPEED_LEAD_FROM = (0.3, 1.0)
FADE_GUARD = True
FADE_AT = 0x6C
FADE_NEAR = 1.0
def _fade_guard(st, player):
    if not getattr(st, "shown", False):
        return
    h = getattr(st, "fade_h", None)
    o_, ty_ = _node_obj(h) if h else (0, -1)
    if not o_ or ty_ != 2:
        h = player_root(getattr(st, "component", None))
        st.fade_h = h
        o_, ty_ = _node_obj(h) if h else (0, -1)
        if not o_ or ty_ != 2:
            return
    f_ = ctypes.c_float.from_address(o_ + FADE_AT)
    st.fade_seen = f_.value
    if f_.value >= 1.0 or not (0.0 <= f_.value < 1.0):
        return
    try:
        data_ = c_uint64.from_address(BASE + CAM_DATA).value
        c_ = (ctypes.c_float * 16).from_address(data_ + CAM_MGR + CAM_MAT)
        p_ = _v(player + 0x340)
        d_ = getattr(st, "lead_d", None) or [0.0, 0.0, 0.0]
        if math.dist([c_[12], c_[13], c_[14]], [p_[i] + d_[i] for i in range(3)]) < FADE_NEAR:
            return
    except Exception:
        pass
    f_.value = 1.0
def _speed_lead(st, player, out):
    p_ = _v(player + 0x340)
    lp = getattr(st, "lead_p", None)
    st.lead_p = p_
    if lp is None or not _finite(p_):
        return
    d = [p_[i] - lp[i] for i in range(3)]
    dn = math.sqrt(_dot(d, d))
    now = time.perf_counter()
    lt, st.lead_t = getattr(st, "lead_t", now), now
    if dn > 1200.0:
        s_ = _steer()
        vel = s_[3] if s_ else None
        if not vel:
            return
        exp_ = [vel[i] * (now - lt) for i in range(3)]
        if math.dist(d, exp_) > max(300.0, 0.35 * math.sqrt(_dot(exp_, exp_))):
            return
    k = _smoothstep(dn, SPEED_LEAD_FROM[0], SPEED_LEAD_FROM[1]) * SPEED_LEAD
    st.lead_d = [d[i] * k for i in range(3)]
    if k > 0.0:
        for i in range(3):
            out[12 + i] += d[i] * k
def _square_rows(rows):
    u = _norm(rows[1])[0]
    b = _norm(_add(rows[2], _scale(u, -_dot(rows[2], u))))[0]
    return [_cross(u, b), u, b]
def _cross_smooth(st, out, Fc):
    now = time.perf_counter()
    R = [_norm(list(out[r * 4:r * 4 + 3]))[0] for r in range(3)]
    T = _square_rows([[sum(Fc[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)])
    S1, S2, t0 = getattr(st, "xs_S", None), getattr(st, "xs_S2", None), getattr(st, "xs_t", 0.0)
    if S1 is None or not 0.0 < now - t0 < 0.25:
        st.xs_S, st.xs_S2, st.xs_t = T, [list(r) for r in T], now
        return
    dt = now - t0
    S1 = _frame_follow(S1, T, 1.0 - math.exp(-dt / CROSS_SMOOTH[0]))
    S2 = _frame_follow(S2, S1, 1.0 - math.exp(-dt / CROSS_SMOOTH[1]))
    st.xs_S, st.xs_S2, st.xs_t = S1, S2, now
    m = [[sum(S2[k][i] * T[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    tr = m[0][0] + m[1][1] + m[2][2]
    w = math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0)))
    if w < 1e-4 or math.sin(w) < 1e-5:
        return
    ax = [(m[2][1] - m[1][2]) / (2 * math.sin(w)), (m[0][2] - m[2][0]) / (2 * math.sin(w)), (m[1][0] - m[0][1]) / (2 * math.sin(w))]
    c, s_ = math.cos(w), math.sin(w)
    pv = _scale(list(out[4:7]), PIVOT * _body_fit(st)[0])
    for r in range(3):
        out[r * 4:r * 4 + 3] = _rot(list(out[r * 4:r * 4 + 3]), ax, c, s_)
    rp = _rot(pv, ax, c, s_)
    for i in range(3):
        out[12 + i] += pv[i] - rp[i]
def _graphics_after(st, player, set_node):
    player = addr(player)
    if not player:
        return
    st.player = player
    st.last_set_node = bool(set_node)
    _tp_run(st, player)
    if FADE_GUARD:
        try:
            _fade_guard(st, player)
        except Exception:
            if "fade_guard" not in st.errors:
                st.errors.add("fade_guard")
                log.exception("fade guard failed (repeats not logged)")
    try:
        _cross_hold(st, "graphics")
    except Exception:
        if "cross_hold" not in st.errors:
            st.errors.add("cross_hold")
            log.exception("crossing hold failed (repeats not logged)")
    tilt = getattr(st, "tilt", None)
    if not tilt or not set_node:
        return
    if time.perf_counter() - getattr(st, "tilt_t", 0.0) > 0.2:
        st.tilt = None
        return
    up, head, axis, c, s_, roll, bax, barrel, rax = _tilt_between(st, tilt)
    st.drawn_head, st.drawn_up = head, up
    cr, sr = math.cos(roll), math.sin(roll)
    cb, sb = math.cos(barrel), math.sin(barrel)
    h = u32(player + 0xE0)
    m = _node_matrix(h)
    if not m:
        return
    base = list(F16.from_address(m))
    if base == getattr(st, "last_out", None):
        return
    out = F16(*base)
    if getattr(st, "tilt_space", False):
        bu, bn = _norm(base[4:7])
        fh_, fhn = _horiz(head, up)
        if bn > 0.1 and fhn > 0.3:
            sc_ = [math.sqrt(_dot(base[r * 4:r * 4 + 3], base[r * 4:r * 4 + 3])) for r in range(3)]
            hand = 1.0 if _dot(_cross(base[0:3], base[4:7]), base[8:11]) >= 0 else -1.0
            r1 = up
            r2 = _scale(fh_, -1.0)
            r0 = _scale(_cross(r1, r2), hand)
            piv0 = _scale(base[4:7], PIVOT * _body_fit(st)[0])
            for r, row in enumerate((r0, r1, r2)):
                base[r * 4:r * 4 + 3] = _scale(row, sc_[r])
            piv1 = _scale(base[4:7], PIVOT * _body_fit(st)[0])
            for i in range(3):
                base[12 + i] += piv0[i] - piv1[i]
    gf, _ = _norm(_scale(base[8:11], -1))
    gf, gn = _norm(_add(gf, _scale(up, -_dot(gf, up))))
    if gn < 0.5:
        return
    yaw = math.atan2(_dot(_cross(gf, head), up), _dot(gf, head))
    cy, sy = math.cos(yaw), math.sin(yaw)
    for r in range(3):
        row = _rot(base[r * 4:r * 4 + 3], up, cy, sy)
        row = _rot(row, axis, c, s_)
        row = _rot(row, rax, cr, sr)
        out[r * 4:r * 4 + 3] = _rot(row, bax, cb, sb)
    piv = _scale(base[4:7], PIVOT * _body_fit(st)[0])
    rp = _rot(_rot(_rot(piv, axis, c, s_), rax, cr, sr), bax, cb, sb)
    for i in range(3):
        out[12 + i] = base[12 + i] + piv[i] - rp[i]
    Fc, Fr = getattr(st, "torso_cur", None), getattr(st, "torso_ref", None)
    wtc_ = WATER_TORSO_CANCEL
    if ((TORSO_CANCEL and getattr(st, "space_on", False)) or (wtc_ and time.perf_counter() - getattr(st, "water_t", -99.0) < WATER_EXIT_FADE)) and Fc and Fr:
        K = [[sum(Fc[k][i] * Fr[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        if K[0][0] + K[1][1] + K[2][2] < 2.999:
            pv2 = _scale(list(out[4:7]), PIVOT * _body_fit(st)[0])
            rows0 = [list(out[r * 4:r * 4 + 3]) for r in range(3)]
            for i in range(3):
                out[i * 4:i * 4 + 3] = [sum(K[i][j] * rows0[j][k] for j in range(3)) for k in range(3)]
            pv3 = _scale(list(out[4:7]), PIVOT * _body_fit(st)[0])
            for i in range(3):
                out[12 + i] += pv2[i] - pv3[i]
    ex_up, ex_t = getattr(st, "exit_up", None), getattr(st, "exit_t", 0.0)
    if ex_up is not None and not getattr(st, "tilt_space", False) and time.perf_counter() - ex_t < EXIT_EASE:
        u_ = _smoothstep(time.perf_counter() - ex_t, 0.0, EXIT_EASE)
        cur_, _ = _norm(_add(_scale(ex_up, 1.0 - u_), _scale(up, u_)))
        ax2 = _cross(up, cur_)
        s2 = math.sqrt(_dot(ax2, ax2))
        if s2 > 1e-4 and _finite(cur_):
            ax2, c2 = _scale(ax2, 1.0 / s2), _dot(up, cur_)
            pv_ = _scale(list(out[4:7]), PIVOT * _body_fit(st)[0])
            for r in range(3):
                out[r * 4:r * 4 + 3] = _rot(list(out[r * 4:r * 4 + 3]), ax2, c2, s2)
            rp2 = _rot(pv_, ax2, c2, s2)
            for i in range(3):
                out[12 + i] += pv_[i] - rp2[i]
    ts_ = getattr(st, "tilt_space", False)
    smoothing_ = bool(CROSS_SMOOTH) and time.perf_counter() - (getattr(st, "xlog_t0", None) or -99.0) < CROSS_SMOOTH_FOR
    if (CROSS_POSE_CARRY and not smoothing_ and getattr(st, "tilt_space_prev", False) and not ts_
            and getattr(st, "drawn_prev", None)):
        P_ = [_norm(st.drawn_prev[r * 4:r * 4 + 3])[0] for r in range(3)]
        N_ = [_norm(list(out[r * 4:r * 4 + 3]))[0] for r in range(3)]
        Q_ = [[sum(P_[k][i] * N_[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        tr_ = Q_[0][0] + Q_[1][1] + Q_[2][2]
        w_ = math.acos(max(-1.0, min(1.0, (tr_ - 1.0) / 2.0)))
        if w_ > math.radians(0.5) and math.sin(w_) > 1e-4:
            ax_ = [(Q_[2][1] - Q_[1][2]) / (2 * math.sin(w_)), (Q_[0][2] - Q_[2][0]) / (2 * math.sin(w_)),
                   (Q_[1][0] - Q_[0][1]) / (2 * math.sin(w_))]
            st.draw_ease = (time.perf_counter(), ax_, w_)
            nu_ = N_[1]
            yaw_ = math.degrees(w_) * _dot(ax_, nu_)
            fw_ = N_[2]
            pit_ = math.degrees(w_) * _dot(ax_, N_[0])
            rol_ = math.degrees(w_) * _dot(ax_, fw_)
            log.info(f"crossing: drawn body step of {math.degrees(w_):.1f} deg eased out (yaw {yaw_:+.0f}, tip {pit_:+.0f}, "
                     f"roll {rol_:+.0f}; space extra {getattr(st, 'sp_extra', 0.0):+.0f}, lean {getattr(st, 'pose_angle', 0.0):.0f})")
    st.tilt_space_prev = ts_
    de_ = getattr(st, "draw_ease", None)
    if de_ is not None:
        u_ = (time.perf_counter() - de_[0]) / CROSS_DRAW_EASE
        if u_ >= 1.0:
            st.draw_ease = None
        else:
            a_ = de_[2] * (1.0 - _smoothstep(u_, 0.0, 1.0))
            c3, s3 = math.cos(a_), math.sin(a_)
            pv_ = _scale(list(out[4:7]), PIVOT * _body_fit(st)[0])
            for r in range(3):
                out[r * 4:r * 4 + 3] = _rot(list(out[r * 4:r * 4 + 3]), de_[1], c3, s3)
            rp3 = _rot(pv_, de_[1], c3, s3)
            for i in range(3):
                out[12 + i] += pv_[i] - rp3[i]
    if SPEED_LEAD:
        _speed_lead(st, player, out)
    if CROSS_SMOOTH and Fc and time.perf_counter() - (getattr(st, "xlog_t0", None) or -99.0) < CROSS_SMOOTH_FOR:
        _cross_smooth(st, out, Fc)
    elif getattr(st, "xs_S", None) is not None:
        st.xs_S = st.xs_S2 = None
    if not _finite(out):
        return
    st.drawn_prev = list(out)
    _set_local(h, ctypes.addressof(out))
    st.last_out = list(F16.from_address(m))
    st.drawn_t = time.perf_counter()
_ensure_reader()
