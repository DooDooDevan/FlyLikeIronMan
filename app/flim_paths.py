import configparser
import ctypes
import os
import re
from ctypes import wintypes
from pathlib import Path
APP = Path(__file__).resolve().parent
PKG = APP.parent if APP.name.lower() == "app" else APP
INI = PKG / "settings.ini"
STEAM_APPID = 275850
GOG_ID = "1446213994"
SUPPORTED_BUILD = "185034"
SUPPORTED_STEAM_BUILDS = {"26540391"}
MOD_FOLDER = "FlyLikeIronMan"
DEV_MOD_FOLDERS = ()
_ANIM_REL = Path("MODELS", "COMMON", "PLAYER", "PLAYERCHARACTER", "ANIMS", "JETPACK")
def settings():
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"), strict=False)
    try:
        cp.read(INI, encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            cp.read(INI, encoding="mbcs")
        except Exception:
            pass
    except Exception:
        pass
    return cp
def _is_game_dir(d):
    try:
        return d is not None and (Path(d) / "Binaries" / "NMS.exe").is_file()
    except OSError:
        return False
def _running_game_dir():
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi")
        arr = (wintypes.DWORD * 4096)()
        got = wintypes.DWORD()
        if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(got)):
            return None
        for pid in arr[: got.value // ctypes.sizeof(wintypes.DWORD)]:
            h = k32.OpenProcess(0x1000, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(1024)
                n = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                    p = Path(buf.value)
                    if p.name.lower() == "nms.exe":
                        return p.parent.parent
            finally:
                k32.CloseHandle(h)
    except Exception:
        pass
    return None
def _reg(root, key, value):
    try:
        import winreg
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as k:
                    return winreg.QueryValueEx(k, value)[0]
            except OSError:
                continue
    except Exception:
        pass
    return None
def steam_dir():
    import winreg
    for root, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                           (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
        v = _reg(root, key, val)
        if v and Path(v).is_dir():
            return Path(v)
    return None
def steam_libraries():
    libs = []
    s = steam_dir()
    if s:
        libs.append(s)
        vdf = s / "steamapps" / "libraryfolders.vdf"
        try:
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
        except OSError:
            pass
    out = []
    for p in libs:
        if p not in out:
            out.append(p)
    return out
def _steam_game_dir():
    libs = steam_libraries()
    libs = ([l for l in libs if (l / "steamapps" / f"appmanifest_{STEAM_APPID}.acf").is_file()]
            + [l for l in libs if not (l / "steamapps" / f"appmanifest_{STEAM_APPID}.acf").is_file()])
    for lib in libs:
        acf = lib / "steamapps" / f"appmanifest_{STEAM_APPID}.acf"
        name = "No Man's Sky"
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(encoding="utf-8", errors="replace"))
            if m:
                name = m.group(1)
        except OSError:
            pass
        d = lib / "steamapps" / "common" / name
        if _is_game_dir(d):
            return d
    return None
def _gog_game_dir():
    import winreg
    for key in (rf"SOFTWARE\GOG.com\Games\{GOG_ID}", rf"SOFTWARE\WOW6432Node\GOG.com\Games\{GOG_ID}"):
        v = _reg(winreg.HKEY_LOCAL_MACHINE, key, "path")
        if _is_game_dir(v):
            return Path(v)
    return None
def _common_dirs():
    for drive in "CDEFGH":
        for sub in (r"Program Files (x86)\Steam\steamapps\common\No Man's Sky",
                    r"Program Files\Steam\steamapps\common\No Man's Sky",
                    r"SteamLibrary\steamapps\common\No Man's Sky",
                    r"Steam\steamapps\common\No Man's Sky",
                    r"GOG Games\No Man's Sky",
                    r"Program Files (x86)\GOG Galaxy\Games\No Man's Sky"):
            d = Path(f"{drive}:\\") / sub
            if _is_game_dir(d):
                return d
    return None
_game = []
def game_dir(refresh=False):
    if _game and not refresh:
        return _game[0]
    cp = settings()
    found = None
    manual = cp.get("game", "path", fallback="").strip().strip('"')
    if manual and _is_game_dir(manual):
        found = Path(manual)
    if found is None:
        for f in (_running_game_dir, _steam_game_dir, _gog_game_dir, _common_dirs):
            try:
                d = f()
            except Exception:
                d = None
            if _is_game_dir(d):
                found = Path(d)
                break
    _game[:] = [found]
    return found
def game_store(d=None):
    d = d or game_dir()
    if d is None:
        return None
    s = str(d).lower()
    if "steamapps" in s:
        return "steam"
    if any(Path(d).glob("goggame-*.info")):
        return "gog"
    if "xboxgames" in s or "windowsapps" in s:
        return "xbox"
    return "other"
def game_exe(d=None):
    d = d or game_dir()
    return Path(d) / "Binaries" / "NMS.exe" if d else None
def mod_dir(d=None):
    d = d or game_dir()
    if d is None:
        return None
    mods = Path(d) / "GAMEDATA" / "MODS"
    for name in (MOD_FOLDER,) + DEV_MOD_FOLDERS:
        if (mods / name).is_dir():
            return mods / name
    return mods / MOD_FOLDER
def _first(cands):
    for c in cands:
        try:
            if c is not None and Path(c).is_file():
                return Path(c)
        except OSError:
            pass
    return None
def anim_up_file():
    return _first([
        APP / "data" / "0H_JPACK_UP.ANIM.MBIN",
    ])
def anim_down_file():
    md = mod_dir()
    return _first([
        PKG / "GAMEDATA" / "MODS" / MOD_FOLDER / _ANIM_REL / "0H_JPACK_DOWN.ANIM.MBIN",
        md / _ANIM_REL / "0H_JPACK_DOWN.ANIM.MBIN" if md else None,
        APP / "data" / "0H_JPACK_DOWN.ANIM.MBIN",
    ])
def steam_build_id(d=None):
    d = Path(d or game_dir() or ".")
    acf = d.parent.parent / f"appmanifest_{STEAM_APPID}.acf"
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', acf.read_text(encoding="utf-8", errors="replace"))
        return m.group(1) if m else None
    except OSError:
        return None
def start_game_normally(d=None):
    d = d or game_dir()
    if d is None or game_store(d) == "steam":
        os.startfile(f"steam://rungameid/{STEAM_APPID}")
    else:
        import subprocess
        subprocess.Popen([str(game_exe(d))], cwd=str(Path(d) / "Binaries"))
def graphics_settings_file():
    d = game_dir()
    return Path(d) / "Binaries" / "SETTINGS" / "TKGRAPHICSSETTINGS.MXML" if d else None
if __name__ == "__main__":
    d = game_dir(refresh=True)
    print("app folder     :", APP)
    print("release folder :", PKG)
    print("settings file  :", INI, "(exists)" if INI.exists() else "(not there)")
    print("game folder    :", d, f"[{game_store(d)}]" if d else "-- NOT FOUND: set [game] path = ... in settings.ini")
    print("mod folder     :", mod_dir(d) if d else None)
    print("hover anim     :", anim_up_file())
    print("flat-palm anim :", anim_down_file())
    print("gfx settings   :", graphics_settings_file())
    print("steam build id :", steam_build_id(d))
