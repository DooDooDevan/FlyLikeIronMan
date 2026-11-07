import json
import time
import numpy as np
import keys
from hunt import CONFIG, log
from jscan import current
from rtti import pm
from vscan import CHUNK, read, regions
cfg = json.loads(CONFIG.read_text())
UP = np.array(cfg["up"]) / np.linalg.norm(cfg["up"])
VEL = int(cfg["vel"], 16)
def yaw(v):
    h = v - (v @ UP)[:, None] * UP
    ref = np.cross(UP, [1.0, 0.0, 0.0])
    ref /= np.linalg.norm(ref)
    ref2 = np.cross(UP, ref)
    return np.degrees(np.arctan2(h @ ref2, h @ ref)), v @ UP
def turn(dx, dy=0, steps=25):
    for _ in range(steps):
        keys.mouse_move(dx, dy)
        time.sleep(0.01)
    time.sleep(0.6)
def wrap(a):
    return (a + 180) % 360 - 180
def main():
    keys.focus()
    time.sleep(1.0)
    found = []
    for base, size in regions(pm.process_handle):
        for off in range(0, size, CHUNK):
            buf = read(pm, base + off, min(CHUNK, size - off))
            if buf is None:
                continue
            v = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 16 * 4).reshape(-1, 4)[:, :3].astype(np.float64)
            with np.errstate(all="ignore"):
                n = np.sqrt((v ** 2).sum(axis=1))
            idx = np.nonzero(np.abs(n - 1) < 0.005)[0]
            found.append(base + off + idx.astype(np.uint64) * 16)
    addrs = np.concatenate(found).astype(np.uint64)
    log(f"camfind: {len(addrs):,} unit vectors")
    v0, _ = current(addrs)
    y0, h0 = yaw(v0)
    turn(12)
    v1, n1 = current(addrs)
    y1, h1 = yaw(v1)
    d1 = wrap(y1 - y0)
    keep = (np.abs(n1 - 1) < 0.01) & (np.abs(d1) > 10) & (np.abs(d1) < 170) & (np.abs(h1 - h0) < 0.05)
    addrs, y1, d1, h1, v0 = addrs[keep], y1[keep], d1[keep], h1[keep], v0[keep]
    log(f"camfind: turned with the mouse: {len(addrs):,}")
    turn(12)
    v2, n2 = current(addrs)
    y2, h2 = yaw(v2)
    d2 = wrap(y2 - y1)
    keep = (np.abs(n2 - 1) < 0.01) & (np.abs(d2 - d1) < 0.25 * np.abs(d1)) & (np.abs(h2 - h1) < 0.05)
    addrs, v0 = addrs[keep], v0[keep]
    log(f"camfind: turned the same again: {len(addrs):,}")
    turn(-12, 0, 50)
    v3, _ = current(addrs)
    keep = (v3 * v0).sum(axis=1) > 0.97
    addrs = addrs[keep]
    log(f"camfind: came back: {len(addrs):,}")
    _, ha = yaw(current(addrs)[0])
    turn(0, -10)
    _, hb = yaw(current(addrs)[0])
    turn(0, 10)
    addrs = addrs[np.abs(hb - ha) > 0.08]
    log(f"camfind: followed pitch: {len(addrs):,}")
    if len(addrs) == 0:
        log("camfind: FAILED")
        return
    keys.press("W")
    time.sleep(0.5)
    vel = np.frombuffer(pm.read_bytes(VEL, 12), dtype=np.float32).astype(np.float64)
    c, _ = current(addrs)
    keys.release("W")
    hv = vel - (vel @ UP) * UP
    hv /= max(np.linalg.norm(hv), 1e-6)
    hc = c - (c @ UP)[:, None] * UP
    hc /= np.maximum(np.linalg.norm(hc, axis=1), 1e-6)[:, None]
    dots = hc @ hv
    good = np.abs(dots) > 0.85
    addrs, signs = addrs[good], np.sign(dots[good]).astype(int)
    log(f"camfind: lined up with walking: {len(addrs):,}")
    if len(addrs) == 0:
        log("camfind: FAILED (nothing lined up with the walking direction)")
        return
    last, changes = current(addrs)[0], np.zeros(len(addrs))
    for _ in range(40):
        keys.mouse_move(6, 0)
        time.sleep(0.03)
        now = current(addrs)[0]
        changes += np.any(np.abs(now - last) > 1e-4, axis=1)
        last = now
    best = int(np.argmax(changes))
    cam, sign = int(addrs[best]), int(signs[best])
    log(f"camfind: camera 0x{cam:X} sign {sign} ({int(changes[best])}/40 updates)")
    cfg.update(cam=f"{cam:X}", cam_sign=sign)
    CONFIG.write_text(json.dumps(cfg, indent=2))
if __name__ == "__main__":
    try:
        main()
    finally:
        keys.release_all()
