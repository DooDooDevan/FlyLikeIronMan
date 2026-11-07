import json
import math
import struct
import threading
import time
import lookup
from pathlib import Path
import flim_paths
UP_FILE = flim_paths.anim_up_file()
DOWN_FILE = flim_paths.anim_down_file()
COUNTS = struct.pack("<ii", 65, 247)
WRITE_EVERY = 1 / 90.0
EASE_TIME = 0.25
LEG_EASE = 0.15
LEGS_FILE = Path(__file__).resolve().parent / "landlegs.json"
FRAME_SIZE, FRAME_ROTS = 0x30, 117
PALMS_FILE = Path(__file__).resolve().parent / "palms.json"
PALM_POSES = ("brake", "left", "right", "brake_left", "brake_right")
PALM_IN, PALM_OUT = 0.1, 0.14
S = 1.0 / math.sqrt(2.0)
TAG = b"FLIMHND\x00"
COUNTS_1H = struct.pack("<ii", 65, 372)
ONEH_FILE = Path(DOWN_FILE).with_name("1H_SPACEWALK_IDLE.ANIM.MBIN") if DOWN_FILE else None
ONEH_RETRY = 60.0
def decode(w):
    drop = 3 - ((w[0] >> 15) << 1 | (w[1] >> 15))
    c = [((x & 0x7FFF) - 16383) / 16383.0 * S for x in w]
    q = c[:drop] + [math.sqrt(max(0.0, 1.0 - sum(x * x for x in c)))] + c[drop:]
    return q
def encode(q):
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    q = [x / n for x in q]
    drop = max(range(4), key=lambda i: abs(q[i]))
    if q[drop] < 0:
        q = [-x for x in q]
    w = [max(0, min(32766, int(round(x / S * 16383 + 16383)))) for i, x in enumerate(q) if i != drop]
    code = 3 - drop
    w[0] |= (code >> 1) << 15
    w[1] |= (code & 1) << 15
    return w
def _cd(x, v, tgt, tc, dt):
    w = 2.15 / max(1e-3, tc)
    e, q = x - tgt, w * dt
    ex = 1.0 / (1.0 + q + 0.48 * q * q + 0.235 * q * q * q)
    tmp = (v + w * e) * dt
    return tgt + (e + tmp) * ex, (v - w * tmp) * ex
def slerp(a, b, t):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = [-x for x in b], -d
    if d > 0.9995:
        return [x + (y - x) * t for x, y in zip(a, b)]
    th = math.acos(d)
    sa, sb = math.sin((1 - t) * th) / math.sin(th), math.sin(t * th) / math.sin(th)
    return [x * sa + y * sb for x, y in zip(a, b)]
def node_rots(b):
    off, cnt = struct.unpack_from("<qI", b, 0x60)
    base, out = 0x60 + off, {}
    for k in range(cnt):
        e = base + k * 0x20
        no, nl = struct.unpack_from("<qI", b, e)
        out[b[e + no:e + no + nl].split(b"\0")[0].decode("ascii", "replace")] = struct.unpack_from("<i", b, e + 0x10)[0]
    return out
def map_channels(n0, a0, n1, a1):
    out = {}
    for nm, r0 in n0.items():
        r1 = n1.get(nm)
        if r1 is not None:
            out[r0] = ("s", 3 * (r1 - a1)) if r1 >= a1 else ("a", 3 * r1)
    return out
def oneh_targets(pairs, palm_still, palm_anim, chan, a0, frames):
    def put(loc, q, f, s_out, a_out, acc):
        if loc is None:
            return
        kind, w = loc
        if kind == "s":
            if f is None:
                s_out.append((w, q))
            else:
                acc.setdefault(w, []).append(q)
        else:
            for ff in (range(frames) if f is None else (f,)):
                a_out.append((ff, w, q))
    def mean(qs):
        r = [0.0, 0.0, 0.0, 0.0]
        for q in qs:
            sg = 1.0 if sum(x * y for x, y in zip(q, qs[0])) >= 0 else -1.0
            r = [x + sg * y for x, y in zip(r, q)]
        n = math.sqrt(sum(x * x for x in r)) or 1.0
        return [x / n for x in r]
    hs, ha = [], []
    for w0, _, qb in pairs:
        put(chan.get(w0 // 3 + a0), qb, None, hs, ha, None)
    ps, pa = {}, {}
    for k in set(palm_still) | set(palm_anim):
        s_out, a_out, acc = [], [], {}
        for w0, _, qb in palm_still.get(k, ()):
            put(chan.get(w0 // 3 + a0), qb, None, s_out, a_out, acc)
        for f, w0, _, qb in palm_anim.get(k, ()):
            put(chan.get(w0 // 3), qb, f, s_out, a_out, acc)
        s_out += [(w, mean(qs)) for w, qs in acc.items()]
        ps[k], pa[k] = s_out, a_out
    return hs, ha, ps, pa
class HoverHands:
    def __init__(self):
        self.pm = None
        self.up = None
        self.up_ptr = self.buf = None
        self.bufs = ()
        self.fblks = ()
        self.extra = []
        self.n = 0
        self.pairs = []
        self.h, self.written, self.t = 0.0, None, None
        self.searching = False
        self.leg_pairs = []
        self.frames = None
        self.hip_pairs = []
        self.block = None
        self.l, self.lwritten = 0.0, None
        try:
            self.legs = json.loads(LEGS_FILE.read_text())
        except Exception:
            self.legs = None
        try:
            self.palms = json.loads(PALMS_FILE.read_text())
        except Exception:
            self.palms = None
        self.palm_still = {}
        self.palm_anim = {}
        self.p = {k: [0.0, 0.0] for k in PALM_POSES}
        self.pwritten = None
        self.upb = None
        self.l1 = None
        self.l1_next = 0.0
    def start(self, pm):
        self.pm = pm
        self._search_async()
    def _search_async(self):
        if not self.searching:
            self.searching = True
            threading.Thread(target=self._search, daemon=True).start()
    def _search(self):
        try:
            upb, dnb = open(UP_FILE, "rb").read(), open(DOWN_FILE, "rb").read()
            up = down = None
            ups = []
            for hit in lookup.clip_hits(self.pm, COUNTS):
                m = hit - 0x50
                if m % 8:
                    continue
                try:
                    p, n = struct.unpack("<Qi", self.pm.read_bytes(m, 12))
                    if not 0 < n < 5000:
                        continue
                    tail = self.pm.read_bytes(p + n * 2, 16)
                    if tail[:8] == TAG:
                        own = struct.unpack("<Q", tail[8:16])[0]
                        if self.pm.read_bytes(m + 0x50, 8) == COUNTS:
                            self.pm.write_bytes(m, struct.pack("<Q", own), 8)
                        p = own
                    rot = self.pm.read_bytes(p, n * 2)
                except Exception:
                    continue
                in_up, in_dn = upb.find(rot) >= 0, dnb.find(rot) >= 0
                if in_up and not in_dn:
                    up = (m, p, n, rot)
                    ups.append(up)
                elif in_dn and not in_up:
                    down = (m, p, n, rot)
            if up and down and up[2] == down[2]:
                m, p, n, rot = up
                wu, wd = struct.unpack(f"<{n}H", rot), struct.unpack(f"<{n}H", down[3])
                pairs = [(3 * k, decode(wu[3 * k:3 * k + 3]), decode(wd[3 * k:3 * k + 3]))
                         for k in range(n // 3) if wu[3 * k:3 * k + 3] != wd[3 * k:3 * k + 3]]
                bufs = tuple(self.pm.allocate(n * 2 + 16) for _ in range(3))
                for buf in bufs:
                    self.pm.write_bytes(buf, rot + TAG + struct.pack("<Q", p), n * 2 + 16)
                buf, self.bufs = bufs[0], bufs
                self.still = bytearray(rot[:n * 2])
                self.spointed = False
                self.up_ptr, self.buf, self.n, self.pairs = p, buf, n, pairs
                self.h, self.written, self.fpointed = 0.0, None, False
                self._find_legs(m, wu)
                self._find_palms(wu)
                self.extra = []
                for m2, p2, n2, _ in ups:
                    if m2 == m or n2 != n:
                        continue
                    fr2 = None
                    try:
                        if self.frames:
                            fp2, fn2 = struct.unpack("<Qi", self.pm.read_bytes(m2 + 0x30, 12))
                            if fn2 == len(self.frames[1]):
                                tbl = self.pm.read_bytes(fp2, fn2 * FRAME_SIZE)
                                if all(struct.unpack_from("<i", tbl, f * FRAME_SIZE + 8)[0] == FRAME_ROTS
                                       for f in range(fn2)):
                                    fr2 = (fp2, [struct.unpack_from("<Q", tbl, f * FRAME_SIZE)[0]
                                                 for f in range(fn2)])
                    except Exception:
                        fr2 = None
                    self.extra.append((m2, p2, fr2))
                self.up = m
                self.upb = upb
                self.l1_next = time.perf_counter() + ONEH_RETRY
                self._find_1h()
        finally:
            self.searching = False
    def _find_1h(self):
        try:
            if ONEH_FILE is None or self.upb is None:
                return
            ob = ONEH_FILE.read_bytes()
            n0, n1 = node_rots(self.upb), node_rots(ob)
            clips = []
            for hit in lookup.clip_hits(self.pm, COUNTS_1H):
                m = hit - 0x50
                if m % 8:
                    continue
                try:
                    p, n = struct.unpack("<Qi", self.pm.read_bytes(m, 12))
                    if not 0 < n < 5000 or n % 3 or not 0 < len(n1) - n // 3 < len(n1):
                        continue
                    tail = self.pm.read_bytes(p + n * 2, 16)
                    if tail[:8] == TAG:
                        own = struct.unpack("<Q", tail[8:16])[0]
                        if self.pm.read_bytes(m + 0x50, 8) == COUNTS_1H:
                            self.pm.write_bytes(m, struct.pack("<Q", own), 8)
                        p = own
                    rot = self.pm.read_bytes(p, n * 2)
                    if ob.find(rot) < 0:
                        continue
                    fp, fn = struct.unpack("<Qi", self.pm.read_bytes(m + 0x30, 12))
                    if fn != 65:
                        continue
                    tbl = self.pm.read_bytes(fp, fn * FRAME_SIZE)
                    rs = [struct.unpack_from("<Qi", tbl, f * FRAME_SIZE) for f in range(fn)]
                    if len({k for _, k in rs}) != 1:
                        continue
                    clips.append((m, p, n, rot, fp, [rp for rp, _ in rs], rs[0][1]))
                except Exception:
                    continue
            if not clips:
                return
            m, p, n, rot, fp, ptrs, rn = clips[0]
            a1 = len(n1) - n // 3
            if rn != 3 * a1 or not self.n:
                return
            data = bytearray()
            for rp in ptrs:
                data += self.pm.read_bytes(rp, rn * 2)
            tg = oneh_targets(self.pairs, self.palm_still, self.palm_anim,
                              map_channels(n0, len(n0) - self.n // 3, n1, a1), len(n0) - self.n // 3, len(ptrs))
            bufs = tuple(self.pm.allocate(n * 2 + 16) for _ in range(3))
            for b in bufs:
                self.pm.write_bytes(b, rot + TAG + struct.pack("<Q", p), n * 2 + 16)
            blks = tuple(self.pm.allocate(len(data) + 16) for _ in range(3))
            for b in blks:
                self.pm.write_bytes(b, bytes(data), len(data))
            self.l1 = {"clips": [(c[0], c[1], c[4], c[5]) for c in clips if c[2] == n and c[3] == rot and c[6] == rn],
                       "still": bytes(rot), "bufs": bufs, "buf": bufs[0], "rn": rn, "block": bytes(data),
                       "blks": blks, "blk": blks[0], "targets": tg, "spointed": False, "fpointed": False}
            self.written = self.pwritten = None
        except Exception:
            self.l1 = None
    def _point_1h_still(self, L, to):
        for m, p, fp, ptrs in L["clips"]:
            try:
                if (self.pm.read_bytes(m + 0x50, 8) == COUNTS_1H
                        and struct.unpack("<Q", self.pm.read_bytes(m, 8))[0] in (p, *L["bufs"])):
                    self.pm.write_bytes(m, struct.pack("<Q", to if to is not None else p), 8)
            except Exception:
                pass
    def _point_1h_frames(self, L, blk):
        rn = L["rn"]
        for m, p, fp, ptrs in L["clips"]:
            try:
                if self.pm.read_bytes(m + 0x50, 8) != COUNTS_1H:
                    continue
                tbl = bytearray(self.pm.read_bytes(fp, len(ptrs) * FRAME_SIZE))
                ok = True
                for f, rp in enumerate(ptrs):
                    o = f * rn * 2
                    if struct.unpack_from("<Q", tbl, f * FRAME_SIZE)[0] not in {rp} | {b + o for b in L["blks"]}:
                        ok = False
                        break
                    struct.pack_into("<Q", tbl, f * FRAME_SIZE, rp if blk is None else blk + o)
                if ok:
                    self.pm.write_bytes(fp, bytes(tbl), len(tbl))
            except Exception:
                pass
    def _write_1h(self, sh, poses):
        L = self.l1
        if not L:
            return
        hs, ha, ps, pa = L["targets"]
        sch, fch = {}, {}
        if sh > 0.0:
            for w, q in hs:
                sch.setdefault(w, []).append((q, sh))
            for f, w, q in ha:
                fch.setdefault((f, w), []).append((q, sh))
        for k, t in poses:
            for w, q in ps.get(k, ()):
                sch.setdefault(w, []).append((q, t))
            for f, w, q in pa.get(k, ()):
                fch.setdefault((f, w), []).append((q, t))
        for chans, key, base, nm, pt in ((sch, "buf", L["still"], "bufs", self._point_1h_still),
                                        (fch, "blk", L["block"], "blks", self._point_1h_frames)):
            flag = "spointed" if key == "buf" else "fpointed"
            if chans:
                d = bytearray(base)
                for w, steps in chans.items():
                    o = 2 * w if key == "buf" else w[0] * L["rn"] * 2 + w[1] * 2
                    q = decode(struct.unpack_from("<3H", base, o))
                    for qb, t in steps:
                        if t > 0.0:
                            q = slerp(q, qb, t)
                    struct.pack_into("<3H", d, o, *encode(q))
                L[key] = self._other(L[key], L[nm])
                self.pm.write_bytes(L[key], bytes(d), len(d))
                pt(L, L[key])
                L[flag] = True
            elif L[flag]:
                pt(L, None)
                L[flag] = False
    def _find_legs(self, m, wu):
        self.leg_pairs, self.hip_pairs, self.frames, self.block = [], [], None, None
        self.l, self.lwritten = 0.0, None
        if not self.legs:
            return
        try:
            self.leg_pairs = [(w, decode(wu[w:w + 3]), q) for w, q in self.legs["still"]]
            fp, fn = struct.unpack("<Qi", self.pm.read_bytes(m + 0x30, 12))
            ptrs, data = [], bytearray()
            for f in range(fn):
                rp, rn = struct.unpack("<Qi", self.pm.read_bytes(fp + f * FRAME_SIZE, 12))
                if rn != FRAME_ROTS:
                    raise ValueError(f"frame {f}: {rn} rotation words")
                ptrs.append(rp)
                data += self.pm.read_bytes(rp, rn * 2)
            for w, qs in self.legs["hips"]:
                if len(qs) != fn:
                    raise ValueError("frame count")
                for f in range(fn):
                    o = f * FRAME_ROTS * 2 + w * 2
                    self.hip_pairs.append((f, w, decode(struct.unpack_from("<3H", data, o)), qs[f]))
            blks = tuple(self.pm.allocate(len(data) + 16) for _ in range(3))
            for blk in blks:
                self.pm.write_bytes(blk, bytes(data), len(data))
            self.frames, self.block, self.fblks = (fp, ptrs, blks[0]), data, blks
        except Exception:
            self.leg_pairs, self.hip_pairs, self.frames, self.block = [], [], None, None
    def _find_palms(self, wu):
        self.palm_still, self.palm_anim, self.pwritten = {}, {}, None
        if not self.palms:
            return
        try:
            for pose in PALM_POSES:
                d = self.palms.get(pose) or {}
                self.palm_still[pose] = [(w, decode(wu[w:w + 3]), q) for w, q in d.get("still", [])]
                an = []
                if self.block is not None:
                    for w, qs in d.get("anim", []):
                        for f, q in enumerate(qs):
                            o = f * FRAME_ROTS * 2 + w * 2
                            an.append((f, w, decode(struct.unpack_from("<3H", self.block, o)), q))
                self.palm_anim[pose] = an
        except Exception:
            self.palm_still, self.palm_anim = {}, {}
    def _other(self, b, pair):
        if len(pair) < 2:
            return b
        return pair[(pair.index(b) + 1) % len(pair)] if b in pair else pair[0]
    def _repoint(self, m, fp, ptrs, to):
        if self.pm.read_bytes(m + 0x50, 8) != COUNTS:
            return False
        tbl = bytearray(self.pm.read_bytes(fp, len(ptrs) * FRAME_SIZE))
        blks = {self.frames[2], *self.fblks}
        for f, rp in enumerate(ptrs):
            o = f * FRAME_ROTS * 2
            if struct.unpack_from("<Q", tbl, f * FRAME_SIZE)[0] not in {rp} | {b + o for b in blks}:
                return False
            struct.pack_into("<Q", tbl, f * FRAME_SIZE, rp if to is None else to + o)
        self.pm.write_bytes(fp, bytes(tbl), len(tbl))
        return True
    def _point_frames(self, ours):
        fp, ptrs, blk = self.frames
        if not self._repoint(self.up, fp, ptrs, blk if ours else None):
            return
        for m2, p2, fr2 in getattr(self, "extra", ()):
            if fr2:
                try:
                    self._repoint(m2, fr2[0], fr2[1], blk if ours else None)
                except Exception:
                    pass
    def _point_extra(self, ours):
        for m2, p2, fr2 in getattr(self, "extra", ()):
            try:
                if (self.pm.read_bytes(m2 + 0x50, 8) == COUNTS
                        and struct.unpack("<Q", self.pm.read_bytes(m2, 8))[0] in (p2, self.buf, *self.bufs)):
                    self.pm.write_bytes(m2, struct.pack("<Q", self.buf if ours else p2), 8)
            except Exception:
                pass
    def _valid(self):
        try:
            return (self.pm.read_bytes(self.up + 0x50, 8) == COUNTS
                    and struct.unpack("<Q", self.pm.read_bytes(self.up, 8))[0] in (self.up_ptr, self.buf, *self.bufs))
        except Exception:
            return False
    def update(self, idle, legs=0.0, palms=None):
        now = time.perf_counter()
        dt, self.t = (min(0.1, now - self.t) if self.t else 0.0), now
        if self.up is None:
            return
        if getattr(self, "l1", None) is None and now >= getattr(self, "l1_next", 0.0) and not self.searching:
            self.l1_next = now + ONEH_RETRY
            self.searching = True
            threading.Thread(target=self._retry_1h, daemon=True).start()
        self.h, self.hv = _cd(self.h, getattr(self, "hv", 0.0), 1.0 if idle else 0.0, EASE_TIME, dt)
        self.h = min(1.0, max(0.0, self.h))
        if self.h > 0.998 and idle:
            self.h, self.hv = 1.0, 0.0
        if self.h < 0.002 and not idle:
            self.h = 0.0
        lt = max(0.0, min(1.0, legs)) if self.frames else 0.0
        self.l, self.lv = _cd(self.l, getattr(self, "lv", 0.0), lt, LEG_EASE, dt)
        self.l = min(1.0, max(0.0, self.l))
        if self.l < 0.002 and lt == 0.0:
            self.l = 0.0
        if self.l > 0.998 and lt == 1.0:
            self.l = 1.0
        pt = {}
        for k in PALM_POSES:
            tg = max(0.0, min(1.0, (palms or {}).get(k, 0.0))) if (self.palm_still.get(k) or self.palm_anim.get(k)) else 0.0
            e = self.p[k]
            kk = 1.0 - math.exp(-dt / (PALM_IN if tg > e[1] else PALM_OUT))
            e[0] += (tg - e[0]) * kk
            e[1] += (e[0] - e[1]) * kk
            if tg == 0.0 and e[1] < 0.002:
                e[0] = e[1] = 0.0
            if tg == 1.0 and e[1] > 0.998:
                e[0] = e[1] = 1.0
            pt[k] = e[1]
        pv = tuple(round(pt[k], 3) for k in PALM_POSES)
        near = lambda a_, b_: a_ is not None and (a_ == b_ or (abs(a_ - b_) < 0.004 and b_ not in (0.0, 1.0)))
        ch = not near(self.written, self.h)
        cl = not near(self.lwritten, self.l)
        cp = self.pwritten is None or (pv != self.pwritten and (max(abs(x - y) for x, y in zip(pv, self.pwritten)) >= 0.004
                                                               or any(x in (0.0, 1.0) for x in pv)))
        if not ch and not cl and not cp:
            return
        ends = self.h in (0.0, 1.0) and self.l in (0.0, 1.0) and all(x in (0.0, 1.0) for x in pv)
        if now < getattr(self, "next_write", 0.0) and not ends:
            return
        self.next_write = now + WRITE_EVERY
        if not self._valid():
            self.up = None
            self._search_async()
            return
        sm = lambda x: x * x * (3 - 2 * x)
        poses = [(k, sm(pt[k])) for k in PALM_POSES if pt[k] > 0.0]
        if self.h == 0.0 and self.l == 0.0 and not poses:
            if getattr(self, "spointed", True):
                self.pm.write_bytes(self.up, struct.pack("<Q", self.up_ptr), 8)
                self._point_extra(False)
                self.spointed = False
        else:
            chans = {}
            for pairs, t in ((self.pairs, sm(self.h)), (self.leg_pairs, sm(self.l))):
                for i, qa, qb in pairs:
                    chans.setdefault(i, [qa, []])[1].append((qb, t))
            for k in PALM_POSES:
                for i, qa, qb in self.palm_still.get(k, ()):
                    chans.setdefault(i, [qa, []])[1].append((qb, sm(pt[k])))
            still = getattr(self, "still", None)
            cur = struct.unpack("<Q", self.pm.read_bytes(self.up, 8))[0]
            if still is not None and cur == self.buf:
                self.buf = self._other(self.buf, self.bufs)
            for i, (qa, steps) in chans.items():
                q = qa
                for qb, t in steps:
                    if t > 0.0:
                        q = slerp(q, qb, t)
                if still is not None:
                    struct.pack_into("<3H", still, 2 * i, *encode(q))
                else:
                    self.pm.write_bytes(self.buf + 2 * i, struct.pack("<3H", *encode(q)), 6)
            if still is not None:
                self.pm.write_bytes(self.buf, bytes(still), len(still))
            if not getattr(self, "spointed", False) or cur != self.buf:
                self.pm.write_bytes(self.up, struct.pack("<Q", self.buf), 8)
                self._point_extra(True)
                self.spointed = True
        if (ch or cp) and getattr(self, "l1", None):
            self._write_1h(sm(self.h), poses)
        if (cl or cp) and self.frames:
            if self.l == 0.0 and not poses:
                self._point_frames(False)
                self.fpointed = False
            else:
                chans = {}
                for f, w, qa, qb in self.hip_pairs:
                    chans.setdefault((f, w), [qa, []])[1].append((qb, sm(self.l)))
                for k in PALM_POSES:
                    for f, w, qa, qb in self.palm_anim.get(k, ()):
                        chans.setdefault((f, w), [qa, []])[1].append((qb, sm(pt[k])))
                for (f, w), (qa, steps) in chans.items():
                    q = qa
                    for qb, t in steps:
                        if t > 0.0:
                            q = slerp(q, qb, t)
                    struct.pack_into("<3H", self.block, f * FRAME_ROTS * 2 + w * 2, *encode(q))
                fp, ptrs, blk = self.frames
                if getattr(self, "fpointed", False):
                    blk = self._other(blk, self.fblks)
                self.pm.write_bytes(blk, bytes(self.block), len(self.block))
                if blk != self.frames[2] or not getattr(self, "fpointed", False):
                    self.frames = (fp, ptrs, blk)
                    self._point_frames(True)
                    self.fpointed = True
        self.lwritten, self.written, self.pwritten = self.l, self.h, pv
    def _retry_1h(self):
        try:
            self._find_1h()
        finally:
            self.searching = False
    def restore(self):
        L = getattr(self, "l1", None)
        if L:
            self._point_1h_still(L, None)
            self._point_1h_frames(L, None)
            L["spointed"] = L["fpointed"] = False
        if self.up is not None and self._valid():
            self.pm.write_bytes(self.up, struct.pack("<Q", self.up_ptr), 8)
            self._point_extra(False)
            self.spointed = False
            if self.frames:
                self._point_frames(False)
                self.fpointed = False
        self.h, self.written = 0.0, None
        self.l, self.lwritten = 0.0, None
        self.p = {k: [0.0, 0.0] for k in PALM_POSES}
        self.pwritten, self.fpointed = None, False
_hh = HoverHands()
start, update, restore = _hh.start, _hh.update, _hh.restore
