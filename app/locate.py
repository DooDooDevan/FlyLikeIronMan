import json
import struct
import time
import numpy as np
from classes import vtables_for
from objects import find, find_many
from rtti import pm
CLASS = "cTkCharacterRigidBody"
ON_DECK = False
BODY_PTR, VEL_OFF = 0x90, 0x60
_vt = None
LAST_BODIES = []
def vtable():
    global _vt
    if _vt is None:
        try:
            import lookup
            _vt = lookup.vtable(pm, CLASS)
        except Exception:
            _vt = vtables_for(CLASS)[0]
    return _vt
def chain(obj):
    return struct.unpack("<Q", pm.read_bytes(obj + BODY_PTR, 8))[0] + VEL_OFF
def still_valid(obj, vel):
    try:
        return struct.unpack("<Q", pm.read_bytes(obj, 8))[0] == vtable() and chain(obj) == vel
    except Exception:
        return False
PLAYER_CLASS = "cGcPlayer"
PLAYER_BACK = 0x6B0
def scan_bodies(progress=None):
    global LAST_BODIES
    pvts = vtables_for(PLAYER_CLASS)
    hits = find_many(list(pvts) + [vtable()], progress)
    players = {p for vt in pvts for p in hits.get(vt, [])}
    bodies = []
    for b in hits.get(vtable(), []):
        try:
            bodies.append((b, chain(b)))
        except Exception:
            pass
    LAST_BODIES = bodies
    return players, bodies
def locate_direct(log=print, progress=None):
    try:
        import lookup
        b, v = lookup.body(pm)
        if b:
            log(f"locate: player body 0x{b:X}, velocity 0x{v:X} (from the player object)")
            return b, v
    except Exception:
        pass
    try:
        players, bodies = scan_bodies(progress)
        if players:
            for b, v in bodies:
                try:
                    if struct.unpack("<Q", pm.read_bytes(b + PLAYER_BACK, 8))[0] in players:
                        log(f"locate: player body 0x{b:X}, velocity 0x{v:X} (from the player object)")
                        return b, v
                except Exception:
                    continue
    except Exception as e:
        log(f"locate: direct lookup failed ({e})")
    return None, None
def motion_test(vels, secs=0.8, log=print):
    import keys
    import viewdir
    import pymem.process
    base = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
    player = struct.unpack("<Q", pm.read_bytes(base + viewdir.DATA_PTR, 8))[0] + viewdir.PLAYER_OFF
    rd = lambda a: np.array(struct.unpack("<3f", pm.read_bytes(a, 12)), dtype=np.float64)
    addrs = [v for _, v in vels]
    win = []
    keys.press("SPACE")
    try:
        t0 = last_t = time.perf_counter()
        last_p, acc, n = rd(player + 0x360), np.zeros((len(addrs), 3)), 0
        while time.perf_counter() - t0 < secs:
            for k, a in enumerate(addrs):
                try:
                    acc[k] += rd(a)
                except Exception:
                    acc[k] += np.nan
            n += 1
            now = time.perf_counter()
            if now - last_t >= 0.1:
                p_ = rd(player + 0x360)
                win.append(((p_ - last_p) / (now - last_t), acc / n))
                last_p, last_t, acc, n = p_, now, np.zeros((len(addrs), 3)), 0
            time.sleep(0.005)
    finally:
        keys.release("SPACE")
    win = [(pv, bv) for pv, bv in win if np.linalg.norm(pv) > 1.0]
    if len(win) < 3:
        log("locate: you didn't move enough to match a body")
        return None
    err = np.zeros(len(addrs))
    speed = float(np.mean([np.linalg.norm(pv) for pv, _ in win]))
    for pv, bv in win:
        e = np.linalg.norm(bv - pv, axis=1)
        err += np.where(np.isfinite(e), e, 1e9)
    err /= len(win)
    k = int(np.argmin(err))
    if err[k] > 0.35 * speed:
        pn = np.array([np.linalg.norm(pv) for pv, _ in win])
        for j in range(len(addrs)):
            bn = np.array([np.linalg.norm(bv[j]) for _, bv in win])
            if np.all(np.isfinite(bn)) and bn.std() > 0.2 and np.mean(np.abs(bn - pn)) < 0.35 * speed \
                    and np.corrcoef(pn, bn)[0, 1] > 0.6:
                log("locate: you're on a corvette deck (your body moves in the ship's frame)")
                return "deck"
        log(f"locate: no body moved with you (best off by {err[k]:.1f} of {speed:.1f} m/s)")
        return None
    log(f"locate: body velocity matches your motion (off by {err[k]:.2f} of {speed:.1f} m/s)")
    return addrs[k]
def locate(log=print):
    global ON_DECK, LAST_BODIES
    ON_DECK = False
    t = time.time()
    import lookup
    b_, _ = lookup.body(pm)
    objs = [b_] if b_ else find(vtable())
    vels = []
    for o in objs:
        try:
            vels.append((o, chain(o)))
        except Exception:
            pass
    LAST_BODIES = vels
    log(f"locate: {len(vels)} character bodies ({time.time() - t:.0f}s)")
    v = motion_test(vels, log=log)
    if v == "deck":
        ON_DECK = True
        return None, None, None
    if v is not None:
        for o, vv in vels:
            if vv == v:
                log(f"locate: player body 0x{o:X}, velocity 0x{v:X}")
                return o, v, None
    from hunt import jump_test
    addrs = np.array([v for _, v in vels], dtype=np.uint64)
    passed = jump_test(addrs)
    for o, v in vels:
        if v in passed:
            log(f"locate: player body 0x{o:X}, velocity 0x{v:X}")
            return o, v, passed[v]
    log("locate: no body reacted to the jump; trying a short walk")
    v = walk_test(addrs)
    if v is not None:
        for o, vv in vels:
            if vv == v:
                log(f"locate: player body 0x{o:X}, velocity 0x{v:X} (walk test)")
                return o, v, None
    log("locate: no body reacted to the jump or the walk")
    return None, None, None
def walk_test(addrs):
    import keys
    from hunt import norms, vecs
    samples, times = [], []
    t0 = time.time()
    walking = False
    while time.time() - t0 < 2.2:
        el = time.time() - t0
        if not walking and el > 0.4:
            keys.press("W")
            walking = True
        if walking and el > 1.2:
            keys.release("W")
        samples.append(vecs(addrs))
        times.append(el)
        time.sleep(0.01)
    keys.release("W")
    S = np.stack(samples, axis=1)
    T = np.array(times)
    best, best_speed = None, 0.0
    for i, a in enumerate(addrs):
        n = norms(S[i])
        before, during, after = n[T < 0.35], n[(T > 0.8) & (T < 1.2)], n[T > 1.9]
        if not len(before) or not len(during) or not len(after):
            continue
        if before.max() > 0.2 or after.max() > 1.0:
            continue
        sp = float(np.median(during))
        if 1.0 < sp < 15.0 and sp > best_speed:
            best, best_speed = int(a), sp
    return best
if __name__ == "__main__":
    import keys
    from hunt import CONFIG
    obj, vel = locate_direct()
    up = None
    if vel is None:
        keys.focus()
        obj, vel, up = locate()
    if vel is not None:
        cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        cfg.update(body=f"{obj:X}", vel=f"{vel:X}")
        if LAST_BODIES:
            cfg.update(cands=[[f"{o:X}", f"{v:X}"] for o, v in LAST_BODIES], cands_t=time.time())
        cfg["verified"] = up is not None
        if up is not None:
            cfg["up"] = up.round(4).tolist()
        CONFIG.write_text(json.dumps(cfg, indent=2))
        print("updated config.json")
