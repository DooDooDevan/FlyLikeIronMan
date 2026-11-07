import re
import struct
import time
import viewdir
VT = {"cGcPlayer": 0x4B192D8, "cGcPlayerWeapon": 0x4B19388, "cGcPlayerCharacterComponent": 0x4B98C90,
      "cTkCharacterRigidBody": 0x35DDE20, "cTkHavokCharacterController": 0x35DCF80}
PLAYER_CTRL, CTRL_BODY = 0x160, 0x200
BODY_HAVOK, HAVOK_VEL = 0x90, 0x60
PLAYER_WEAPON = 0x3E0
PLAYER_COMP = 0x5610
RES_MGR = 0x6EFD7E0
RES_COUNT, RES_LIST = 0x5C, 0x60
RES_TYPE, RES_NAME = 0x8, 0xC
ANIM_TYPE, ANIM_CLIP = 3, 0x1D0
GFX_SETTINGS = 0x6EF1A40
MINING_SLOT = 0x1120
BSTRIDE, BID, PSTRIDE = 0x130, 0x80, 0x1B0
PROJ_AFTER = 0x4000
_IDRE = re.compile(rb"[A-Z][A-Z0-9_]{2,23}")
_bases = {}
_clips = {}
def base(pm):
    b = _bases.get(id(pm))
    if b is None:
        import pymem.process
        b = _bases[id(pm)] = pymem.process.module_from_name(pm.process_handle, "NMS.exe").lpBaseOfDll
    return b
def vtable(pm, name):
    return base(pm) + VT[name]
def _u64(pm, a):
    return struct.unpack("<Q", pm.read_bytes(a, 8))[0]
def is_a(pm, obj, name):
    try:
        return bool(obj) and _u64(pm, obj) == vtable(pm, name)
    except Exception:
        return False
def player(pm):
    try:
        p = _u64(pm, base(pm) + viewdir.DATA_PTR) + viewdir.PLAYER_OFF
    except Exception:
        return None
    return p if is_a(pm, p, "cGcPlayer") else None
def body(pm):
    p = player(pm)
    try:
        ctrl = _u64(pm, p + PLAYER_CTRL) if p else 0
        b = ctrl + CTRL_BODY
        if ctrl and is_a(pm, ctrl, "cTkHavokCharacterController") and is_a(pm, b, "cTkCharacterRigidBody"):
            hv = _u64(pm, b + BODY_HAVOK)
            if hv:
                return b, hv + HAVOK_VEL
    except Exception:
        pass
    return None, None
def component(pm):
    p = player(pm)
    try:
        c = _u64(pm, p + PLAYER_COMP) if p else 0
    except Exception:
        return None
    return c if is_a(pm, c, "cGcPlayerCharacterComponent") else None
def weapon(pm):
    p = player(pm)
    w = p + PLAYER_WEAPON if p else 0
    return w if is_a(pm, w, "cGcPlayerWeapon") else None
def _ident(pm, a, n=24):
    try:
        s = pm.read_bytes(a, n).split(b"\0")[0]
        return s.decode() if _IDRE.fullmatch(s) else None
    except Exception:
        return None
def anim_clips(pm, max_age=5.0):
    now = time.perf_counter()
    got = _clips.get(id(pm))
    if got and now - got[0] < max_age:
        return got[1]
    out = {}
    try:
        rm = _u64(pm, base(pm) + RES_MGR)
        n = struct.unpack("<i", pm.read_bytes(rm + RES_COUNT, 4))[0]
        if not 0 < n < 1000000:
            return out
        for r in struct.unpack(f"<{n}Q", pm.read_bytes(_u64(pm, rm + RES_LIST), n * 8)):
            try:
                hdr = pm.read_bytes(r + RES_TYPE, 0x58)
                if struct.unpack_from("<i", hdr, 0)[0] != ANIM_TYPE:
                    continue
                m = _u64(pm, r + ANIM_CLIP)
                if m:
                    out[m] = hdr[RES_NAME - RES_TYPE:].split(b"\0")[0].decode(errors="replace")
            except Exception:
                continue
    except Exception:
        return out
    _clips[id(pm)] = (now, out)
    return out
def clip_hits(pm, counts):
    for m in anim_clips(pm):
        try:
            if pm.read_bytes(m + 0x50, 8) == counts:
                yield m + 0x50
        except Exception:
            continue
def gfx_settings(pm):
    try:
        return _u64(pm, base(pm) + GFX_SETTINGS) or None
    except Exception:
        return None
def projectile_entry(pm, w, ident=b"BOLTGUN"):
    try:
        p = _u64(pm, w + MINING_SLOT)
        if not _ident(pm, p + BID):
            return None
        k = 0
        while k > -64 and _ident(pm, p + (k - 1) * BSTRIDE + BID):
            k -= 1
        n = 0
        while n < 128 and _ident(pm, p + (k + n) * BSTRIDE + BID):
            n += 1
        end = p + (k + n) * BSTRIDE
        blob = pm.read_bytes(end, PROJ_AFTER + 8 * PSTRIDE)
        i = blob.find(ident + b"\0")
        while i >= 0:
            if i % 8 == 0 and blob[i:i + 16].split(b"\0")[0] == ident:
                return end + i
            i = blob.find(ident + b"\0", i + 1)
    except Exception:
        pass
    return None
