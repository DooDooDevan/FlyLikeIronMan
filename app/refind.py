import math
import struct
import threading
import time
import numpy as np
import locate
from objects import find
from rtti import pm
POS_OFF = 0x360
RELIST = 8.0
class Refinder:
    def __init__(self, player, valid):
        self.player, self.valid = player, valid
        self.cands = None
        self.busy = False
        self.next_check = 0.0
        self.list_t = 0.0
    def poll(self, now):
        if self.busy or now < self.next_check or self.player is None:
            return
        self.next_check = now + 2.0
        if (self.cands is None or now - self.list_t > RELIST) and not self.valid():
            self.busy = True
            threading.Thread(target=self._list, daemon=True).start()
    def _list(self):
        try:
            import lookup
            b, v = lookup.body(pm)
            if b:
                self.cands, self.list_t = [(b, v)], time.perf_counter()
                return
            out = []
            for o in find(locate.vtable()):
                try:
                    out.append((o, locate.chain(o)))
                except Exception:
                    pass
            self.cands = out or None
            self.list_t = time.perf_counter()
        except Exception:
            self.cands = None
        finally:
            self.busy = False
    def forget(self):
        self.cands = None
    def _pos(self):
        return np.frombuffer(pm.read_bytes(self.player + POS_OFF, 12), dtype=np.float32).astype(np.float64)
    def match(self, secs=0.25, cands=None):
        cands = cands if cands is not None else self.cands
        if not cands or self.player is None:
            return None
        ts, ps, vs = [], [], []
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < secs:
            t = time.perf_counter()
            try:
                p = self._pos()
            except Exception:
                return None
            row = []
            for _, va in cands:
                try:
                    row.append(np.frombuffer(pm.read_bytes(va, 12), dtype=np.float32).astype(np.float64))
                except Exception:
                    row.append(np.full(3, np.nan))
            ts.append(t)
            ps.append(p)
            vs.append(row)
            time.sleep(0.004)
        if len(ts) < 8:
            return None
        T = np.array(ts) - ts[0]
        P = np.array(ps)
        if not np.isfinite(P).all():
            return None
        mine = np.polyfit(T, P, 1)[0]
        sp = float(np.linalg.norm(mine))
        if not 1.5 < sp < 300.0:
            return None
        V = np.array(vs)
        with np.errstate(all="ignore"):
            err = np.linalg.norm(np.nanmean(V, axis=0) - mine, axis=1)
        err = np.where(np.isfinite(err), err, np.inf)
        order = np.argsort(err)
        best = int(order[0])
        second = float(err[order[1]]) if len(order) > 1 else np.inf
        if err[best] < max(1.5, 0.25 * sp) and second > 2.0 * err[best] + 1.0:
            return cands[best]
        return None
    def seed(self, cands):
        good = []
        for o, va in cands:
            try:
                if locate.still_valid(o, va):
                    good.append((o, va))
            except Exception:
                pass
        if good:
            self.cands, self.list_t = good, time.perf_counter()
        return bool(good)
    def list_now(self, progress=None):
        self.busy = True
        try:
            import lookup
            b, v = lookup.body(pm)
            bodies = [(b, v)] if b else locate.scan_bodies(progress)[1]
            self.cands = bodies or None
            self.list_t = time.perf_counter()
        except Exception:
            self.cands = None
        finally:
            self.busy = False
        return bool(self.cands)
SCAN, SYNC, READY = 1, 2, 3
MIN_BOOT = 3.0
SCAN_TO = 0.8
class Startup:
    def __init__(self, refinder, known=False, seeded=False):
        self.r, self.known, self.seeded = refinder, known, seeded
        self.state, self.progress, self.result = SCAN, 0.0, None
        self.t0, self.ready_t = time.perf_counter(), None
        self.adopted = self.chimed = False
        self._done = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
    def finish(self):
        self._done.set()
    def _ramp(self, a, b, secs):
        t0 = time.perf_counter()
        while (k := (time.perf_counter() - t0) / secs) < 1.0:
            self.progress = a + (b - a) * k * k * (3 - 2 * k)
            time.sleep(0.02)
        self.progress = b
    def _run(self):
        try:
            if self.known:
                self._ramp(0.0, 1.0, MIN_BOOT)
            else:
                if self.seeded and self.r.cands:
                    self._ramp(0.0, SCAN_TO, 0.9)
                else:
                    self.r.list_now(lambda f: setattr(self, "progress", max(self.progress, SCAN_TO * f)))
                    self.progress = max(self.progress, SCAN_TO)
                self.state = SYNC
                mine = list(self.r.cands or [])
                while not self._done.is_set():
                    if not mine:
                        self.r.list_now()
                        mine = list(self.r.cands or [])
                        continue
                    m = self.r.match(0.3, mine)
                    if m:
                        self.result = m
                        break
                    self.r.list_t = time.perf_counter()
                    self.progress = SCAN_TO + (0.95 - SCAN_TO) * (1 - math.exp(-(time.perf_counter() - self.t0) / 20))
                    time.sleep(0.05)
                left = MIN_BOOT - (time.perf_counter() - self.t0)
                self._ramp(self.progress, 1.0, max(0.35, left))
        except Exception:
            pass
        self.progress, self.state, self.ready_t = 1.0, READY, time.perf_counter()
