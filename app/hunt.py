import ctypes
import json
import threading
import time
from datetime import datetime
from pathlib import Path
import numpy as np
import pymem
import keys
from jscan import current
from vscan import CHUNK, read, regions
HERE = Path(__file__).parent
LOG, CONFIG = HERE / "hunt_log.txt", HERE / "config.json"
TURN_DX = 6
SPRINT = (3.0, 15.0)
ATTEMPTS = 4
pm = pymem.Pymem("NMS.exe")
class Aborted(Exception):
    pass
def log(msg):
    line = f"{datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
class Mover(threading.Thread):
    HOLD = {"still": (), "circle": ("W", "SHIFT"), "straight": ("W", "SHIFT"), "back": ("S", "SHIFT"),
            "walk": ("W",), "walkcircle": ("W",), "jetpack": ("SPACE",)}
    def __init__(self):
        super().__init__(daemon=True)
        self.mode, self.aborted, self.done = "still", False, False
        self.turn = TURN_DX
    def run(self):
        held = ()
        while not self.done:
            if not keys.focused():
                if not self.aborted:
                    keys.release_all()
                    self.aborted = True
                time.sleep(0.2)
                continue
            want = self.HOLD[self.mode]
            if want != held:
                keys.release(*[k for k in held if k not in want])
                keys.press(*[k for k in want if k not in held])
                held = want
            if self.mode in ("circle", "walkcircle"):
                keys.mouse_move(self.turn)
            time.sleep(0.01)
        keys.release_all()
mover = Mover()
def wait(secs):
    end = time.time() + secs
    while time.time() < end:
        if mover.aborted:
            raise Aborted("the game lost focus")
        time.sleep(0.05)
def do(mode, settle=0.0):
    mover.mode = mode
    wait(settle)
def vec(a):
    return np.frombuffer(pm.read_bytes(int(a), 12), dtype=np.float32).astype(np.float64)
def vecs(addrs):
    out = np.full((len(addrs), 3), np.nan)
    for i, a in enumerate(addrs):
        try:
            out[i] = vec(a)
        except Exception:
            pass
    return out
def norms(v):
    with np.errstate(all="ignore"):
        n = np.sqrt((v ** 2).sum(axis=1))
    return np.where(np.isfinite(n), n, -1)
def diagonal(v, n):
    with np.errstate(all="ignore"):
        return (np.abs(v) > 0.15 * n[:, None]).sum(axis=1) >= 2
def full_scan(keep):
    found, vals = [], []
    for base, size in regions(pm.process_handle):
        for off in range(0, size, CHUNK):
            if mover.aborted:
                raise Aborted("the game lost focus")
            buf = read(pm, base + off, min(CHUNK, size - off))
            if buf is None:
                continue
            v = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 16 * 4).reshape(-1, 4)[:, :3].astype(np.float64)
            idx = np.nonzero(keep(v, norms(v)))[0]
            found.append(base + off + idx.astype(np.uint64) * 16)
            vals.append(v[idx].astype(np.float32))
    return np.concatenate(found).astype(np.uint64), np.concatenate(vals)
def sprinting(v, n):
    return (n > SPRINT[0]) & (n < SPRINT[1]) & diagonal(v, n)
def scan_rounds():
    do("circle", 2.0)
    addrs, _ = full_scan(sprinting)
    log(f"  sprint scan: {len(addrs):,} candidates")
    for r in range(1, 13):
        do("still", 1.5)
        v, n = current(addrs)
        addrs = addrs[(n >= 0) & (n < 0.02)]
        do("circle", 2.0)
        if len(addrs) > 200_000:
            v, n = current(addrs)
            addrs = addrs[sprinting(v, n)]
        else:
            a, _ = current(addrs)
            wait(0.3)
            b, _ = current(addrs)
            na, nb = norms(a), norms(b)
            with np.errstate(all="ignore"):
                ang = np.degrees(np.arccos(np.clip((a * b).sum(axis=1) / (na * nb), -1, 1)))
            ok = sprinting(a, na) & sprinting(b, nb) & (np.abs(na - nb) < 0.5 * na) & (ang > 3)
            addrs = addrs[ok]
        log(f"  round {r}: {len(addrs):,} left")
        if len(addrs) <= 40:
            break
    do("still", 1.0)
    return addrs
def jump_test(addrs):
    do("still", 1.5)
    samples, times = [], []
    t0 = time.time()
    jumped = False
    while time.time() - t0 < 2.2:
        if not jumped and time.time() - t0 > 0.3:
            keys.hold(0.15, "SPACE")
            jumped = True
        samples.append(vecs(addrs))
        times.append(time.time() - t0)
        time.sleep(0.01)
    S = np.stack(samples, axis=1)
    T = np.array(times)
    passed = {}
    for i, a in enumerate(addrs):
        s = S[i]
        n = norms(s)
        before = n[T < 0.3]
        if len(before) == 0 or np.any((before < 0) | (before > 0.05)):
            continue
        moving = np.nonzero(n > 0.5)[0]
        if len(moving) < 5:
            continue
        up = s[moving[0]] / n[moving[0]]
        p = s @ up
        seg = np.arange(moving[0], int(np.argmin(p)) + 1)
        if len(seg) < 5 or p.max() < 3 or p.min() > -1.0:
            continue
        air = seg[n[seg] > 0.5]
        with np.errstate(all="ignore"):
            on_line = np.abs(p[air]) / n[air] > 0.97
        if not on_line.all():
            continue
        after = p[seg][int(np.argmax(p[seg])):]
        if len(after) < 3 or np.mean(np.diff(after) <= 0.05) < 0.8:
            continue
        passed[int(a)] = up
    return passed
def screen_motion(secs):
    a = keys.shot()
    wait(secs)
    return keys.diff(a, keys.shot())
def freeze_test(addr):
    do("straight", 0.5)
    free = screen_motion(0.8)
    do("still", 1.0)
    stop = threading.Event()
    def hold_zero():
        while not stop.is_set():
            pm.write_bytes(addr, bytes(12), 12)
            time.sleep(0.0005)
    th = threading.Thread(target=hold_zero, daemon=True)
    th.start()
    try:
        do("straight", 0.5)
        frozen = screen_motion(0.8)
    finally:
        stop.set()
        th.join()
    do("back", 1.6)
    do("still", 1.0)
    log(f"  freeze test 0x{addr:X}: screen change free {free:.1f}, frozen {frozen:.1f}")
    return frozen < 0.35 * free
def hunt_velocity():
    old = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if "body" in old and "vel" in old:
        from locate import still_valid
        if still_valid(int(old["body"], 16), int(old["vel"], 16)):
            log(f"velocity 0x{old['vel']} still linked to the player's physics object; using it")
            return int(old["vel"], 16), np.array(old["up"])
    known = [int(old["vel"], 16)] if "vel" in old else []
    known += [a for a in (0x2697E720090,) if a not in known]
    log(f"checking known addresses: {', '.join(f'0x{a:X}' for a in known)}")
    passed = jump_test(np.array(known, dtype=np.uint64))
    for a, up in passed.items():
        if freeze_test(a):
            return a, up
    for attempt in range(1, ATTEMPTS + 1):
        log(f"velocity hunt, attempt {attempt}")
        addrs = scan_rounds()
        if len(addrs) == 0:
            log("  nothing survived, starting over")
            continue
        first = jump_test(addrs)
        second = jump_test(np.array(list(first), dtype=np.uint64)) if first else {}
        log(f"  jump test: {len(first)} passed once, {len(second)} passed twice")
        for a, up in second.items():
            if freeze_test(a):
                return a, up
        log("  no candidate passed the freeze test")
    return None, None
def flat(v, up):
    v = v - np.dot(v, up) * up
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else v
def camera_tracks(cam, sign, vel, up, secs=4.0):
    do("circle", 1.5)
    angles, changes, last = [], 0, None
    end = time.time() + secs
    while time.time() < end:
        try:
            c, v = vec(cam) * sign, vec(vel)
        except Exception:
            return False
        if abs(np.linalg.norm(c) - 1) > 0.02:
            return False
        if last is not None and not np.allclose(c, last, atol=1e-4):
            changes += 1
        last = c
        if np.linalg.norm(v) > SPRINT[0]:
            angles.append(np.degrees(np.arccos(np.clip(np.dot(flat(c, up), flat(v, up)), -1, 1))))
        wait(0.1)
    do("still", 0.5)
    ok = changes > secs * 5 and len(angles) > 5 and np.median(angles) < 40
    log(f"  camera 0x{cam:X}: {changes} changes, median angle to heading "
        f"{np.median(angles) if angles else float('nan'):.0f} deg -> {'ok' if ok else 'no'}")
    return ok
def hunt_camera(vel, up):
    old = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    known = [(int(old["cam"], 16), old.get("cam_sign", 1))] if "cam" in old else []
    known.append((0x26D0D200170, 1))
    for cam, sign in known:
        if camera_tracks(cam, sign, vel, up):
            return cam, sign
    for attempt in range(1, ATTEMPTS + 1):
        log(f"camera hunt, attempt {attempt}")
        do("circle", 2.0)
        found, signs = [], []
        for base, size in regions(pm.process_handle):
            for off in range(0, size, CHUNK):
                if mover.aborted:
                    raise Aborted("the game lost focus")
                h = flat(vec(vel), up)
                buf = read(pm, base + off, min(CHUNK, size - off))
                if buf is None:
                    continue
                v = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 16 * 4).reshape(-1, 4)[:, :3].astype(np.float64)
                n = norms(v)
                with np.errstate(all="ignore"):
                    d = (v - (v @ up)[:, None] * up) @ h
                unit = np.abs(n - 1) < 0.02
                s = np.where(unit & (d > 0.8), 1, np.where(unit & (d < -0.8), -1, 0))
                idx = np.nonzero(s)[0]
                found.append(base + off + idx.astype(np.uint64) * 16)
                signs.append(s[idx])
        addrs, signs = np.concatenate(found).astype(np.uint64), np.concatenate(signs)
        log(f"  camera scan: {len(addrs):,} candidates")
        for r in range(1, 9):
            wait(0.7)
            h = flat(vec(vel), up)
            c, n = current(addrs)
            with np.errstate(all="ignore"):
                d = (c - (c @ up)[:, None] * up) @ h * signs
            keep = (np.abs(n - 1) < 0.02) & (d > 0.8)
            addrs, signs = addrs[keep], signs[keep]
            log(f"  camera round {r}: {len(addrs):,} left")
            if len(addrs) <= 300:
                break
        do("still", 1.0)
        start = vecs(addrs)
        swing = np.zeros(len(addrs))
        for dx, dy in [(40, 0)] * 25 + [(0, -30)] * 15 + [(0, 30)] * 15 + [(-40, 0)] * 25:
            keys.mouse_move(dx, dy)
            wait(0.02)
            v = vecs(addrs)
            with np.errstate(all="ignore"):
                swing = np.maximum(swing, np.degrees(np.arccos(np.clip((v * start).sum(axis=1), -1, 1))))
        addrs, signs = addrs[swing > 30], signs[swing > 30]
        log(f"  look test: {len(addrs)} swung with the mouse")
        for a, s in zip(addrs[:20], signs[:20]):
            if camera_tracks(int(a), int(s), vel, up):
                return int(a), int(s)
    return None, None
def main():
    log("=== hunt started ===")
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
    if not keys.focus():
        log("couldn't bring the game to the front; stopping")
        return
    mover.start()
    try:
        vel, up = hunt_velocity()
        if vel is None:
            log("FAILED: no velocity address found")
            return
        log(f"FOUND velocity 0x{vel:X}, up {up.round(3).tolist()}")
        cam, sign = hunt_camera(vel, up)
        if cam is None:
            log("FAILED: velocity found but no camera address")
        else:
            log(f"FOUND camera 0x{cam:X} (sign {sign})")
        cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        if cfg.get("vel") != f"{vel:X}":
            cfg.pop("body", None)
        cfg.update(vel=f"{vel:X}", up=up.round(4).tolist(), found=datetime.now().isoformat(timespec="seconds"))
        if cam is not None:
            cfg.update(cam=f"{cam:X}", cam_sign=sign)
        CONFIG.write_text(json.dumps(cfg, indent=2))
        log(f"wrote {CONFIG.name}")
    except Aborted as e:
        log(f"STOPPED: {e}")
    finally:
        mover.done = True
        mover.mode = "still"
        keys.release_all()
        log("=== hunt finished ===")
if __name__ == "__main__":
    main()
