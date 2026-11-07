import os
import sys
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
state_dir = os.path.join(HERE, "nmspy_state")
os.makedirs(state_dir, exist_ok=True)
run_module(pkg, cfg, "nmspy", state_dir)
