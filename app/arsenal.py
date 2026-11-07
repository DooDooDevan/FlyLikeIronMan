import json
import re
import struct
import threading
from pathlib import Path
import speedfx
HERE = Path(__file__).resolve().parent
BACKUP = HERE / "arsenal_backup.json"
PSTRIDE, IDLEN = 0x1B0, 0x10
BSTRIDE, BID = 0x130, 0x80
MINING_PTR = 0x1120
CLIP = 0x24B0
PROJ = (("BOLTGUN", "SHIPGUN"), ("SHOTGUN", "SHIPSHOTGUN"),
        ("CANNON", "SHIPPLASMAGUN"), ("FLAMETHROW", "SHIPROCKET"))
BEAM = ("PLAYER", "PLAYER_SHIP")
DAMAGE_X, DAMAGE_CAP = 10, 1000000
P_DAMAGE = 0x8C
B_KIND = 0xD0
BOOST_BEAMS = ("PLAYER_SHIP", "PLAYER_RAIL")
B_AUDIO = 0xC4
MUTE_BEAMS = ("PLAYER_SHIP", "PLAYER_RAIL")
NAMES = {"BOLTGUN": "Boltcaster: Photon Cannon", "SHOTGUN": "Scatter Blaster: Positron Ejector",
         "SMG": "Pulse Spitter: Infraknife", "CANNON": "Neutron Cannon: Cyclotron Ballista",
         "FLAMETHROW": "Incinerator: Rocket Launcher", "PLAYER": "Mining Beam: Phase Beam"}
_IDRE = re.compile(rb"[A-Z][A-Z0-9_]{2,15}")
NAME_ORDER = ("Boltcaster", "Scatter Blaster", "Pulse Spitter", "Blaze Javelin", "Neutron Cannon", "Mining Beam",
              "Incinerator")
RENAME = {"Boltcaster": "Repulsors", "Scatter Blaster": "Twin Repulsors", "Pulse Spitter": "Wrist Cannon",
          "Blaze Javelin": "Wrist Laser", "Neutron Cannon": "Charged Blast", "Mining Beam": "Unibeam",
          "Incinerator": "Rocket Pods"}
class Arsenal:
    def __init__(self):
        self.pm = None
        self.ready = False
        self.on = False
        self.proj = {}
        self.beam = {}
        self.weapon = None
        self.saved = {}
        self.note = ""
        self.texts = {}
    def start(self, pm, player_weapon_vtable=None):
        self.pm = pm
        threading.Thread(target=self._find, args=(player_weapon_vtable,), daemon=True).start()
    def _id(self, a, n=IDLEN):
        try:
            s = self.pm.read_bytes(a, n).split(b"\0")[0]
        except Exception:
            return None
        return s.decode() if _IDRE.fullmatch(s) else None
    def _find(self, wvt):
        try:
            self._undo_backup()
            import lookup
            w_ = lookup.weapon(self.pm)
            if w_:
                self.weapon = w_
            elif wvt:
                from objects import find
                ws = find(wvt)
                self.weapon = ws[0] if ws else None
            a0 = lookup.projectile_entry(self.pm, self.weapon) if self.weapon else None
            for a in ([a0] if a0 else speedfx._scan(self.pm.process_handle, b"BOLTGUN\x00")):
                if self._id(a) != "BOLTGUN":
                    continue
                ids = {}
                for k in range(-4, 90):
                    n = self._id(a + k * PSTRIDE)
                    if n:
                        ids[n] = a + k * PSTRIDE
                if all(t in ids and s in ids for t, s in PROJ):
                    self.proj = ids
                    break
            if self.weapon:
                p = struct.unpack("<Q", self.pm.read_bytes(self.weapon + MINING_PTR, 8))[0]
                if self._id(p + BID, 24) == BEAM[0]:
                    self.beam = {n: p + k * BSTRIDE for k in range(-2, 40)
                                 if (n := self._id(p + k * BSTRIDE + BID, 24))}
            self._find_names()
            self.ready = bool(self.proj) or BEAM[1] in self.beam
            self.note = (f"ship arsenal ready: {sum(1 for t, s in PROJ if t in self.proj)} projectile weapons"
                         + (", the Phase Beam" if BEAM[1] in self.beam else "") if self.ready
                         else "ship arsenal unavailable (its tables weren't found)")
        except Exception as e:
            self.note = f"ship arsenal unavailable ({e.__class__.__name__})"
    def _find_names(self, wait=15.0):
        import mmap
        import time
        try:
            blk = mmap.mmap(-1, 72, tagname="IronManFlightNames")
        except Exception:
            return
        found, t_end = {}, time.time() + wait
        while time.time() < t_end:
            vals = struct.unpack_from("<d7Q", blk, 0)
            if vals[0] > 0.0:
                for name, a in zip(NAME_ORDER, vals[1:]):
                    try:
                        have = self.pm.read_bytes(a, len(name)) if a else b""
                    except Exception:
                        continue
                    if have in (name.encode(), RENAME[name].encode().ljust(len(name), b"\x00")):
                        found[a] = name
                break
            time.sleep(0.5)
        self.texts = found
    def _rename(self, on):
        for a, orig in self.texts.items():
            new = RENAME[orig].encode().ljust(len(orig), b"\x00")
            have, want = (orig.encode(), new) if on else (new, orig.encode())
            try:
                if self.pm.read_bytes(a, len(orig)) == have:
                    self.pm.write_bytes(a, want, len(want))
            except Exception:
                pass
    def set(self, ship):
        if not self.ready or ship == self.on:
            return
        try:
            if ship:
                self._apply()
            else:
                self._restore()
        except Exception as e:
            self.note = f"arsenal swap failed ({e.__class__.__name__}): put back"
            self._restore()
    def _apply(self):
        for t, s in PROJ:
            ta, sa = self.proj.get(t), self.proj.get(s)
            if not ta or not sa or self._id(ta) != t or self._id(sa) != s:
                continue
            body = bytearray(self.pm.read_bytes(sa + IDLEN, PSTRIDE - IDLEN))
            d = P_DAMAGE - IDLEN
            struct.pack_into("<i", body, d, min(struct.unpack_from("<i", body, d)[0] * DAMAGE_X, DAMAGE_CAP))
            if ta + IDLEN not in self.saved:
                self.saved[ta + IDLEN] = self.pm.read_bytes(ta + IDLEN, PSTRIDE - IDLEN)
            self._save_backup()
            self.pm.write_bytes(ta + IDLEN, bytes(body), len(body))
        if self.weapon and BEAM[1] in self.beam:
            a = self.weapon + MINING_PTR
            cur = struct.unpack("<Q", self.pm.read_bytes(a, 8))[0]
            if cur == self.beam.get(BEAM[0]):
                self.saved.setdefault(a, struct.pack("<Q", cur))
                self._save_backup()
                self.pm.write_bytes(a, struct.pack("<Q", self.beam[BEAM[1]]), 8)
        for n in BOOST_BEAMS:
            e = self.beam.get(n)
            if not e or self._id(e + BID, 24) != n:
                continue
            kind, dmg = struct.unpack("<ii", self.pm.read_bytes(e + B_KIND, 8))
            if n == BEAM[1] and BEAM[0] in self.beam:
                kind = struct.unpack("<i", self.pm.read_bytes(self.beam[BEAM[0]] + B_KIND, 4))[0]
            if e + B_KIND not in self.saved:
                self.saved[e + B_KIND] = self.pm.read_bytes(e + B_KIND, 8)
                self._save_backup()
                self.pm.write_bytes(e + B_KIND, struct.pack("<ii", kind, min(dmg * DAMAGE_X, DAMAGE_CAP)), 8)
        for n in MUTE_BEAMS:
            e = self.beam.get(n)
            if e and self._id(e + BID, 24) == n and e + B_AUDIO not in self.saved:
                self.saved[e + B_AUDIO] = self.pm.read_bytes(e + B_AUDIO, 8)
                self._save_backup()
                self.pm.write_bytes(e + B_AUDIO, bytes(8), 8)
        self._rename(True)
        self.on = True
    def _restore(self):
        for a, orig in list(self.saved.items()):
            try:
                if a == (self.weapon or 0) + MINING_PTR:
                    cur = struct.unpack("<Q", self.pm.read_bytes(a, 8))[0]
                    if cur not in (self.beam.get(BEAM[0]), self.beam.get(BEAM[1])):
                        del self.saved[a]
                        continue
                elif any(a in (e + B_KIND, e + B_AUDIO) for e in self.beam.values()):
                    pass
                elif self._id(a - IDLEN) is None:
                    continue
                self.pm.write_bytes(a, orig, len(orig))
                del self.saved[a]
            except Exception:
                pass
        self._rename(False)
        self.on = False
        self._save_backup()
    def keep_loaded(self):
        if not self.on or not self.weapon:
            return
        try:
            sel = struct.unpack("<i", self.pm.read_bytes(self.weapon + 0xF74, 4))[0]
            if not 0 <= sel < 32:
                return False
            slot = self.weapon + CLIP + 4 * sel
            v = struct.unpack("<i", self.pm.read_bytes(slot, 4))[0]
            if not 0 <= v < 100000:
                return
            cap = self.clip_cap = getattr(self, "clip_cap", {})
            last = getattr(self, "clip_last", None)
            if sel != getattr(self, "clip_sel", None):
                self.clip_sel, self.clip_last = sel, v
                return
            if not getattr(self, "clip_wrote", False):
                cap[sel] = max(cap.get(sel, 0), v)
            self.clip_wrote = False
            if cap.get(sel, 0) > 0 and v < cap[sel] - 1:
                self.pm.write_bytes(slot, struct.pack("<i", cap[sel]), 4)
                self.clip_wrote, v = True, cap[sel]
            self.clip_last = v
            return v == 0 and not cap.get(sel)
        except Exception:
            pass
        return False
    def _save_backup(self):
        try:
            if self.saved:
                BACKUP.write_text(json.dumps({"pid": self.pm.process_id,
                                              "saved": {f"{a:X}": b.hex() for a, b in self.saved.items()},
                                              "texts": {f"{a:X}": n for a, n in self.texts.items()}}))
            elif BACKUP.exists():
                BACKUP.unlink()
        except Exception:
            pass
    def _undo_backup(self):
        try:
            d = json.loads(BACKUP.read_text())
        except Exception:
            return
        try:
            if d.get("pid") == self.pm.process_id:
                for a, h in d.get("saved", {}).items():
                    b = bytes.fromhex(h)
                    self.pm.write_bytes(int(a, 16), b, len(b))
                for a, n in d.get("texts", {}).items():
                    if n in RENAME:
                        new = RENAME[n].encode().ljust(len(n), b"\x00")
                        if self.pm.read_bytes(int(a, 16), len(n)) == new:
                            self.pm.write_bytes(int(a, 16), n.encode(), len(n))
                self.note = "put back the ship arsenal a stopped run had left in"
        finally:
            try:
                BACKUP.unlink()
            except OSError:
                pass
_a = Arsenal()
start, set_ship, state = _a.start, _a.set, _a
