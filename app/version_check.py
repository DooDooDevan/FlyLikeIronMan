import hashlib
import struct
import sys
from pathlib import Path
import flim_paths
BUILD = flim_paths.SUPPORTED_BUILD
SUPPORTED_STEAM_BUILDS = {"26540391"}
KNOWN_SHA1 = {
    "fcb981a89e58656936556f097948aade7d14983c": "Steam, build 185034",
}
FINGERPRINTS = {
    0x1156F10: bytes.fromhex("40554156488d6c24b14881ec880000004c8bf1488b492848"),
    0x1157260: bytes.fromhex("40555641544157488dac2438fdffff4881ecc80300004c8b"),
    0x2C4FE50: bytes.fromhex("4c8bdc49895b0849896b1049897318574881eca0000000c7"),
    0x2C4FF20: bytes.fromhex("48895c240848897424104c89442418574881eca000000041"),
    0x1889700: bytes.fromhex("448bc141c1e8134585c07469448bc94181e1ffff07004181"),
    0x18804C0: bytes.fromhex("448bc94c8bd241c1e9134585c9745a448bc14181e0ffff07"),
    0x156F300: bytes.fromhex("48895c2408574881ecb0000000488b7908488bd98b49044c"),
}
CHECK_RVAS = tuple(FINGERPRINTS)
FP_LEN = 24
def _sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    off = pe + 24 + opt
    out = []
    for i in range(nsec):
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, off + i * 40 + 8)
        out.append((va, max(vsize, rawsize), raw, rawsize))
    return out
def read_rva(data, secs, rva, n):
    for va, size, raw, rawsize in secs:
        if va <= rva < va + size:
            o = rva - va
            if o + n > rawsize:
                return None
            return data[raw + o: raw + o + n]
    return None
def check(exe=None):
    exe = Path(exe) if exe else flim_paths.game_exe()
    if exe is None or not exe.is_file():
        return "nogame", ("No Man's Sky was not found. Open settings.ini (in the mod folder) and set\n"
                          "  [game]\n  path = <your No Man's Sky folder, the one with Binaries and GAMEDATA>")
    try:
        data = exe.read_bytes()
    except OSError as e:
        return "nogame", f"Could not read {exe}: {e}"
    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 in KNOWN_SHA1:
        return "exact", f"Game version OK ({KNOWN_SHA1[sha1]})."
    try:
        secs = _sections(data)
    except Exception as e:
        return "unsupported", f"{exe} doesn't look like the game ({e})."
    bad = [rva for rva, fp in FINGERPRINTS.items() if read_rva(data, secs, rva, len(fp)) != fp]
    has_build = (b"\0" + BUILD.encode() + b"\0") in data
    if not bad and FINGERPRINTS:
        return "compatible", (f"Game exe differs from the tested one, but all {len(FINGERPRINTS)} code/data "
                              f"locations the mod uses match build {BUILD}: should work.")
    return "unsupported", (
        f"Your No Man's Sky version is NOT the one this mod supports (build {BUILD}"
        f"{'' if has_build else '; yours is a different build'}).\n"
        f"{len(bad)} of {len(FINGERPRINTS)} game code/data locations the mod relies on have changed, so the\n"
        "in-game part (hand/foot jets, pose) would hook the wrong places and could crash the game.\n"
        "Wait for an updated version of the mod on its Nexus page (a game update always needs one).")
def launcher_verdict():
    d = flim_paths.game_dir()
    if d is None:
        return False, check()[1]
    bid = flim_paths.steam_build_id(d)
    if bid is not None and bid in SUPPORTED_STEAM_BUILDS:
        return True, f"Game version OK (Steam build {bid})."
    st, msg = check(flim_paths.game_exe(d))
    if st in ("exact", "compatible"):
        return True, msg
    if st == "nogame":
        return True, f"Warning: couldn't check the game version ({msg.splitlines()[0]}). Continuing."
    return False, ("No Man's Sky was updated. Iron Man Flight needs an update for this version.\n"
                   "Starting the game normally, without the mod.\n"
                   "(Check the mod's Nexus page for an update. Details: " + msg.splitlines()[0] + ")")
def capture(exe=None):
    exe = Path(exe) if exe else flim_paths.game_exe()
    data = exe.read_bytes()
    secs = _sections(data)
    print(f'    "{hashlib.sha1(data).hexdigest()}": "...",')
    for rva in CHECK_RVAS:
        b = read_rva(data, secs, rva, FP_LEN)
        print(f"    0x{rva:X}: bytes.fromhex(\"{b.hex()}\"),")
if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture(*(a for a in sys.argv[1:] if a != "--capture"))
        sys.exit(0)
    st, msg = check(*(a for a in sys.argv[1:]))
    print(msg)
    sys.exit({"exact": 0, "compatible": 0, "unsupported": 1}.get(st, 2))
