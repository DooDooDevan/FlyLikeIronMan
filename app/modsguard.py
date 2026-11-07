import os
import sys
import time
from pathlib import Path
HERE = Path(__file__).resolve().parent
DEFAULT_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\No Man's Sky\Binaries\NMS.exe")
ON = b'<Property name="DisableAllMods" value="true" />'
OFF = b'<Property name="DisableAllMods" value="false" />'
def default_exe():
    try:
        import flim_paths
        gd = flim_paths.game_dir()
        if gd is not None:
            return Path(flim_paths.game_exe(gd))
    except Exception:
        pass
    return DEFAULT_EXE
def settings_file(exe=None):
    return Path(exe or default_exe()).resolve().parent / "SETTINGS" / "GCMODSETTINGS.MXML"
def guard(exe=None):
    f = settings_file(exe)
    try:
        b = f.read_bytes()
    except OSError:
        return False
    if ON not in b:
        return False
    tmp = f.with_name(f.name + ".flim-tmp")
    try:
        tmp.write_bytes(b.replace(ON, OFF))
        os.replace(tmp, f)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        print(f"The game has all mods switched off and this couldn't switch them back on ({e.__class__.__name__}): "
              f"set DisableAllMods to false in {f}, or answer No when the game asks to disable mods.")
        return False
    try:
        with open(HERE / "autostart_log.txt", "a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%H:%M:%S')} the game had switched all mods off (after a crash?): "
                      f"switched back on before it started\n")
    except OSError:
        pass
    return True
def disabled(exe=None):
    try:
        return ON in settings_file(exe).read_bytes()
    except OSError:
        return False
if __name__ == "__main__":
    exe = next((a for a in sys.argv[1:] if a.lower().endswith("nms.exe")), None)
    guard(exe)
