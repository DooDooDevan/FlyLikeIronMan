import math
import struct
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from pathlib import Path
import numpy as np
import animswap
import fastwrite
import lookup
HERE = Path(__file__).resolve().parent
if (HERE / "anim_lib.py").exists():
    sys.path.insert(0, str(HERE))
SRC = HERE / "swimfx" / "src" if (HERE / "swimfx" / "src").is_dir() else HERE / "data" / "swimfx"
TARGET = "0h_swim_fwd_jpack"
IDLE_TARGET = "0h_swim_idle"
MORE_TARGETS = (IDLE_TARGET, "0h_swim_fwd", "0h_swim_back", "0h_swim_left", "0h_swim_right",
                "1h_swim_idle", "1h_swim_idle_aim", "1h_swim_fwd", "1h_swim_back", "1h_swim_left", "1h_swim_right")
def encode_np(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    n = len(q)
    drop = np.argmax(np.abs(q), axis=1)
    q = q * np.where(q[np.arange(n), drop] < 0, -1.0, 1.0)[:, None]
    keep = np.ones((n, 4), bool)
    keep[np.arange(n), drop] = False
    w = np.clip(np.round(q[keep].reshape(n, 3) / animswap.S * 16383 + 16383), 0, 32766).astype(np.uint16)
    code = (3 - drop).astype(np.uint16)
    w[:, 0] |= (code >> 1) << 15
    w[:, 1] |= (code & 1) << 15
    return w.astype("<u2").tobytes()
POSES = {"idle": ("0H_JPACK_DOWN", 0, None), "fwd": ("0H_JPACK_FWD", None, None),
         "back": ("0H_JPACK_UP", 0, "brake"),
         "left": ("0H_JPACK_LEFT", None, None), "right": ("0H_JPACK_RIGHT", None, None)}
NAMES = list(POSES)
PALMS = HERE / "palms.json"
POSES_FILE = HERE / "data" / "swimposes.json"
EASE = 0.15
WRITE_EVERY = 1 / 120.0
VERIFY_EVERY = 0.25
SNAP = 0.005
MAX_SPAN = 0x40000
RETRY_EVERY = 15.0
FRAME_SIZE = 0x30
def _put(pm, addr, data):
    if not fastwrite.write(pm.process_handle, addr, data):
        raise OSError("write failed")
def _q(e):
    return [float(p.get("value")) for p in e if p.get("name") in ("X", "Y", "Z", "W")]
def _unit(q):
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]
def build_poses(target=TARGET):
    import json
    from anim_lib import Anim
    base = Anim(SRC / f"{target}.anim.MXML")
    still_e = list(base.still.find('Property[@name="Rotations"]'))
    n_still, n_anim = len(still_e), base.n_anim_rot
    mid = base.frame_count // 2
    default_still = [_q(e) for e in still_e]
    default_anim = [_q(e) for e in base.frames[mid].find('Property[@name="Rotations"]')]
    poses = {}
    palms = json.loads(PALMS.read_text()) if PALMS.exists() else {}
    for name, (fn, fr, palm) in POSES.items():
        src = Anim(SRC / f"{fn}.ANIM.MXML")
        f_ = src.frame_count // 2 if fr is None else fr
        over = {}
        if palm and palm in palms:
            by_ri = {ri: nd for nd, ri, _, _ in src.nodes}
            for w, q in palms[palm].get("still", []):
                nd = by_ri.get(src.n_anim_rot + w // 3)
                if nd:
                    over[nd] = list(q)
            for w, qs in palms[palm].get("anim", []):
                nd = by_ri.get(w // 3)
                if nd and qs:
                    over[nd] = list(qs[min(f_, len(qs) - 1)])
        st_, an_ = list(default_still), list(default_anim)
        for node, ri, _, _ in base.nodes:
            if (node not in src.index and node not in over) or ri < 0:
                continue
            q = over[node] if node in over else list(src.rot(node, f_))
            if ri < n_anim:
                an_[ri] = q
            elif ri - n_anim < n_still:
                st_[ri - n_anim] = q
        poses[name] = (st_, an_)
    return base.frame_count, base.node_count, n_still, n_anim, default_still, poses
_POSES_CACHE = {}
def load_poses(target=TARGET):
    if target not in _POSES_CACHE:
        _POSES_CACHE[target] = _load_poses(target)
    return _POSES_CACHE[target]
def _load_poses(target):
    import json
    if (SRC / f"{target}.anim.MXML").exists():
        return build_poses(target)
    d = json.loads(POSES_FILE.read_text())
    if d.get("target") != target:
        d = d.get("more", {})[target]
    return (d["frame_count"], d["node_count"], d["n_still"], d["n_anim"], d["default_still"],
            {k: (v[0], v[1]) for k, v in d["poses"].items()})
def export_poses():
    import json
    r = lambda qs: [[round(x, 6) for x in q] for q in qs]
    def one(target):
        fc, nc, ns, na, ds, poses = build_poses(target)
        return {"target": target, "frame_count": fc, "node_count": nc, "n_still": ns, "n_anim": na,
                "default_still": r(ds), "poses": {k: [r(a), r(b)] for k, (a, b) in poses.items()}}
    d = one(TARGET)
    d["more"] = {t_: one(t_) for t_ in MORE_TARGETS}
    POSES_FILE.parent.mkdir(exist_ok=True)
    POSES_FILE.write_text(json.dumps(d))
    return POSES_FILE
class SwimSwap:
    def __init__(self, target=TARGET, managed=False, pool=None):
        self.target = target
        self.managed = managed
        self.pm = None
        self.recs = []
        self.verified = {}
        self.poses = {}
        self.last = self.last_key = None
        self.P = None
        self.n_still = self.n_anim = 0
        self.applied = None
        self.searching = False
        self.next_check = self.next_write = self.next_retry = 0.0
        self.w = {k: (1.0 if k == "idle" else 0.0) for k in POSES}
        self.t = None
        self.late_retry = 0.0
        self.active = False
        self.pool = pool or ThreadPoolExecutor(12)
        self.lock = threading.Lock()
    def start(self, pm):
        self.pm = pm
        if self.managed:
            return
        self.late_retry = time.perf_counter() + 60.0
        self._search_async()
        threading.Thread(target=self._writer, daemon=True).start()
    def _search_async(self):
        if not self.searching:
            self.searching = True
            threading.Thread(target=self._search, daemon=True).start()
    def _search(self, hits=None):
        try:
            frame_count, node_count, n_still, n_anim, default_still, poses = load_poses(self.target)
            want = [_unit(q) for q in default_still]
            counts = struct.pack("<ii", frame_count, node_count)
            rivals, order = [], (TARGET,) + MORE_TARGETS
            for t_ in order:
                if t_ != self.target:
                    r_ = load_poses(t_)
                    if (r_[0], r_[1], r_[2]) == (frame_count, node_count, n_still):
                        rivals.append((order.index(t_) < order.index(self.target), [_unit(q) for q in r_[4]]))
            def n_off(w, ref, cap):
                o_ = 0
                for k in range(n_still):
                    d = animswap.decode(w[3 * k:3 * k + 3])
                    if min(max(abs(a - b) for a, b in zip(d, ref[k])), max(abs(a + b) for a, b in zip(d, ref[k]))) > 2e-3:
                        o_ += 1
                        if o_ > cap:
                            break
                return o_
            recs = []
            for hit in (lookup.clip_hits(self.pm, counts) if hits is None else hits):
                m = hit - 0x50
                if m % 8:
                    continue
                try:
                    p, n = struct.unpack("<Qi", self.pm.read_bytes(m, 12))
                    if n != 3 * n_still:
                        continue
                    w = struct.unpack(f"<{n}H", self.pm.read_bytes(p, n * 2))
                    fp, fn_ = struct.unpack("<Qi", self.pm.read_bytes(m + 0x30, 12))
                except Exception:
                    continue
                off = n_off(w, want, n_still // 10)
                if off > n_still // 10 or fn_ != frame_count or any(n_off(w, rv, off) < off + (1 if first_ else 0) for first_, rv in rivals):
                    continue
                own_frames = [struct.unpack("<Q", self.pm.read_bytes(fp + f * FRAME_SIZE, 8))[0] for f in range(fn_)]
                rn = struct.unpack("<i", self.pm.read_bytes(fp + 8, 4))[0]
                if rn != 3 * n_anim:
                    continue
                lo = min([p] + own_frames)
                hi = max([p + n_still * 6] + [r + n_anim * 6 for r in own_frames])
                if hi - lo > MAX_SPAN:
                    continue
                slices = [(p - lo, n_still * 6)] + [(r - lo, n_anim * 6) for r in own_frames]
                recs.append((m, counts, p, fp, own_frames, (lo, self.pm.read_bytes(lo, hi - lo), slices)))
            if recs:
                self.poses, self.n_still, self.n_anim = poses, n_still, n_anim
                self.P = None
                self.recs = recs
                self.last = self.last_key = None
            self.applied = None
        finally:
            self.searching = False
    def _blend(self):
        wv = np.array([self.w[k] for k in NAMES], dtype=np.float64)
        wv = wv / (wv.sum() or 1.0)
        i0 = int(np.argmax(wv > 1e-3))
        if self.P is None or getattr(self, "P_src", None) is not self.poses:
            self.P = [np.array([self.poses[nm][part] for nm in NAMES], dtype=np.float64) for part in (0, 1)]
            self.P_src = self.poses
        out = []
        for P in self.P:
            sg = np.where(np.einsum("mnk,nk->mn", P, P[i0]) >= 0, 1.0, -1.0)
            acc = np.einsum("m,mn,mnk->nk", wv, sg, P)
            out.append(list(acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)))
        return out
    def _valid(self, m, counts, p, fp, own_frames):
        hd = self.pm.read_bytes(m, 0x58)
        if hd[0x50:0x58] != counts or struct.unpack_from("<Q", hd, 0)[0] != p:
            return False
        fr = self.pm.read_bytes(fp, (len(own_frames) - 1) * FRAME_SIZE + 8)
        return struct.unpack_from("<Q", fr, 0)[0] == own_frames[0] and \
            struct.unpack_from("<Q", fr, (len(own_frames) - 1) * FRAME_SIZE)[0] == own_frames[-1]
    def _write(self, ours=True):
        if not self.recs:
            return True
        if ours:
            key = tuple(round(self.w[k], 4) for k in NAMES)
            if key == self.last_key and self.last is not None:
                return True
            st_, an_ = self._blend()
            sb, fb = encode_np(np.asarray(st_)), encode_np(np.asarray(an_))
            self.last_key = key
            if (sb, fb) == self.last:
                return True
            self.last = (sb, fb)
        else:
            self.last = self.last_key = None
        def one(rec):
            m, counts, p, fp, own_frames, (lo, blk, slices) = rec
            try:
                if not self._valid(m, counts, p, fp, own_frames):
                    return False
                now_ = time.perf_counter()
                if not ours or now_ - self.verified.get(m, -99.0) >= VERIFY_EVERY:
                    cur = bytearray(self.pm.read_bytes(lo, len(blk)))
                    for o, n_ in slices:
                        cur[o:o + n_] = blk[o:o + n_]
                    if cur != blk:
                        self.verified.pop(m, None)
                        return False
                    self.verified[m] = now_
                if ours:
                    buf = bytearray(blk)
                    buf[p - lo:p - lo + len(sb)] = sb
                    for rp in own_frames:
                        buf[rp - lo:rp - lo + len(fb)] = fb
                    _put(self.pm, lo, bytes(buf))
                else:
                    _put(self.pm, lo, blk)
                return True
            except Exception:
                return False
        with self.lock:
            res = [one(r_) for r_ in self.recs]
        if not all(res):
            self.recs = [r for r, ok_ in zip(self.recs, res) if ok_]
        return bool(self.recs)
    def _writer(self):
        while True:
            time.sleep(WRITE_EVERY)
            self.step()
    def step(self):
        try:
            if not self.recs or self.searching:
                return
            if self.active:
                self._ease()
                if not self._write(True):
                    self.recs = []
                    if not self.managed:
                        self._search_async()
                self.applied = True
            elif self.applied:
                self._write(False)
                self.applied = False
        except Exception:
            pass
    def update(self, active, fwd=0, back=0, left=0, right=0):
        now = time.perf_counter()
        if not self.recs and self.managed:
            self.active = False
            return
        if not self.recs:
            if self.late_retry and now >= self.late_retry and not self.searching:
                self.late_retry = 0.0
                self._search_async()
            elif active and not self.searching and now >= self.next_retry:
                self.next_retry = now + RETRY_EVERY
                self._search_async()
            return
        tgt = {"fwd": fwd, "back": back, "left": left, "right": right}
        tgt["idle"] = 0.0 if any(tgt.values()) else 1.0
        self.tgt = tgt
        self.active = bool(active)
    def _ease(self):
        tgt = getattr(self, "tgt", None)
        now = time.perf_counter()
        dt = 0.0 if self.t is None else min(0.1, now - self.t)
        self.t = now
        if tgt is None:
            return
        k = 1.0 - math.exp(-dt / EASE) if dt else 1.0
        for nm in self.w:
            self.w[nm] += (tgt[nm] - self.w[nm]) * k
            if abs(tgt[nm] - self.w[nm]) < SNAP:
                self.w[nm] = float(tgt[nm])
    def restore(self):
        self.active = False
        if self.recs and self.applied:
            self._write(False)
        self.applied = False
    def found(self):
        return len(self.recs)
class SwimSwaps:
    SEARCH_LATE = 60.0
    RETRY_LOST = 30.0
    RETRY_NEVER = 300.0
    def __init__(self):
        self.pool = ThreadPoolExecutor(12)
        self.parts = [SwimSwap(t_, managed=True, pool=self.pool) for t_ in (TARGET,) + MORE_TARGETS]
        self.pm = None
        self.active = False
        self.ever = set()
    def start(self, pm):
        self.pm = pm
        for s_ in self.parts:
            s_.start(pm)
        threading.Thread(target=self._searcher, daemon=True).start()
        threading.Thread(target=self._writer, daemon=True).start()
    CACHE = HERE / "swim_orig.pkl"
    def _cache_load(self):
        import pickle
        try:
            d = pickle.loads(self.CACHE.read_bytes())
            return d["recs"] if d.get("game_pid") == self.pm.process_id else {}
        except Exception:
            return {}
    def _cache_save(self):
        import pickle
        try:
            d = self._cache_load()
            for s_ in self.parts:
                if s_.recs:
                    d[s_.target] = list(s_.recs)
            self.CACHE.write_bytes(pickle.dumps({"game_pid": self.pm.process_id, "recs": d}))
        except Exception:
            pass
    def _adopt(self, s_, cached):
        ok = []
        for rec in cached:
            m, counts, p, fp, own_frames, (lo, blk, slices) = rec
            try:
                if not s_._valid(m, counts, p, fp, own_frames):
                    continue
                cur = bytearray(self.pm.read_bytes(lo, len(blk)))
                for o, n_ in slices:
                    cur[o:o + n_] = blk[o:o + n_]
                if cur == blk:
                    ok.append(rec)
            except Exception:
                pass
        if ok:
            fc, nc, ns, na, ds, poses = load_poses(s_.target)
            s_.poses, s_.n_still, s_.n_anim = poses, ns, na
            s_.P = None
            s_.recs, s_.last, s_.last_key, s_.applied = ok, None, None, True
            self.ever.add(s_.target)
    def _search(self, parts):
        try:
            for s_ in parts:
                s_.searching = True
            pats = {}
            for s_ in parts:
                fc, nc = load_poses(s_.target)[:2]
                pats.setdefault(struct.pack("<ii", fc, nc), []).append(s_)
            hits = {p_: list(lookup.clip_hits(self.pm, p_)) for p_ in pats}
            cache = None
            for pat, ss in pats.items():
                for s_ in ss:
                    s_._search(hits[pat])
                    if not s_.recs:
                        cache = self._cache_load() if cache is None else cache
                        if cache.get(s_.target):
                            self._adopt(s_, cache[s_.target])
                    if s_.recs:
                        self.ever.add(s_.target)
            self._cache_save()
        except Exception:
            pass
        finally:
            for s_ in parts:
                s_.searching = False
    def _searcher(self):
        t0 = time.perf_counter()
        self._search(self.parts)
        late, nxt = t0 + self.SEARCH_LATE, {}
        while True:
            time.sleep(1.0)
            now = time.perf_counter()
            if late and now >= late:
                late = 0.0
                self._search([s_ for s_ in self.parts if not s_.recs])
                continue
            if not self.active:
                continue
            due = [s_ for s_ in self.parts if not s_.recs and now >= nxt.get(s_.target, 0.0)]
            if due:
                for s_ in due:
                    nxt[s_.target] = now + (self.RETRY_LOST if s_.target in self.ever or s_.target == TARGET
                                            else self.RETRY_NEVER)
                self._search(due)
    def _writer(self):
        t_next = time.perf_counter()
        while True:
            t_next = max(t_next + WRITE_EVERY, time.perf_counter() - WRITE_EVERY)
            time.sleep(max(0.0, t_next - time.perf_counter()))
            for s_ in self.parts:
                s_.step()
    def update(self, active, fwd=0, back=0, left=0, right=0):
        self.active = bool(active)
        for s_ in self.parts:
            s_.update(active, fwd, back, left, right)
    def restore(self):
        for s_ in self.parts:
            s_.restore()
    def found(self):
        return sum(s_.found() for s_ in self.parts)
if __name__ == "__main__":
    if "--export" in sys.argv:
        print("wrote", export_poses())
