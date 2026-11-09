import os
import sys
import time
class _Tee:
    def __init__(self, stream, path):
        self._s = stream
        try:
            self._f = open(path, "w", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            self._f = None
    def write(self, t):
        try:
            self._s.write(t)
        except Exception:
            pass
        if self._f is not None:
            try:
                self._f.write(t)
            except OSError:
                self._f = None
        return len(t)
    def flush(self):
        for s in (self._s, self._f):
            try:
                s and s.flush()
            except Exception:
                pass
    def __getattr__(self, name):
        return getattr(self._s, name)
sys.stdout = sys.stderr = _Tee(sys.__stdout__,
                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "nmspy_out.txt"))
print(time.strftime("NMS.py start %Y-%m-%d %H:%M:%S"))
import questionary
for name in ("confirm", "text", "path", "select", "checkbox"):
    setattr(questionary, name, lambda *a, **k: None)
import nmspy
from pymhf import run_module
from pymhf.utils.parse_toml import read_pymhf_settings
HERE = os.path.dirname(os.path.abspath(__file__))
pkg = os.path.dirname(nmspy.__file__)
cfg = read_pymhf_settings(os.path.join(pkg, "pymhf.toml"))
cfg.update({
    "mod_dir": os.path.join(HERE, "mods"),
    "start_exe": os.environ.get("NMSPY_ATTACH") != "1",
    "start_paused": True,
    "interactive_console": False,
})
cfg["gui"] = dict(cfg.get("gui") or {}, shown=False)
try:
    import flim_paths
    _gd = flim_paths.game_dir()
    if _gd is not None and flim_paths.game_store(_gd) != "steam":
        cfg["exe"] = str(flim_paths.game_exe(_gd))
        cfg.pop("steam_gameid", None)
    if (flim_paths.PKG / "runtime").is_dir():
        cfg.setdefault("logging", {})["shown"] = False
except Exception as e:
    print(f"(couldn't check the game folder: {e}; starting through Steam)")
try:
    import pyrun_injected.dllinject as _dllinject
    _ST = _dllinject.StringType
    def _as_text(value, is_file=False):
        if is_file:
            try:
                with open(value, encoding="utf-8") as f_:
                    return _ST(f_.read(), False)
            except OSError:
                pass
        return _ST(value, is_file)
    _dllinject.StringType = _as_text
except Exception as e:
    print(f"(couldn't adjust the injector: {e})")
try:
    import pymem as _pymem
    _read_bool = _pymem.Pymem.read_bool
    def _read_bool_nap(self, addr):
        time.sleep(0.05)
        return _read_bool(self, addr)
    _pymem.Pymem.read_bool = _read_bool_nap
except Exception as e:
    print(f"(couldn't slow the start-up wait: {e})")
state_dir = os.path.join(HERE, "nmspy_state")
os.makedirs(state_dir, exist_ok=True)
run_module(pkg, cfg, "nmspy", state_dir)
