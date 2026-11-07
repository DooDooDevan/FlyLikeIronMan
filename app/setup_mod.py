import filecmp
import shutil
import stat
import os
import sys
from pathlib import Path
import flim_paths
SRC = flim_paths.PKG / "GAMEDATA" / "MODS" / flim_paths.MOD_FOLDER
KEY_FILE = Path("MODELS", "COMMON", "PLAYER", "PLAYERCHARACTER", "PLAYERCHARACTER.SCENE.MBIN")
def _files(root):
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
def _same_tree(a, b):
    try:
        return all((b / rel).is_file() and filecmp.cmp(a / rel, b / rel, shallow=False) for rel in _files(a))
    except OSError:
        return False
def status():
    d = flim_paths.game_dir()
    out = {"game": d, "source": SRC if SRC.is_dir() else None, "installed": None, "same": None}
    if d is None:
        return out
    mods = Path(d) / "GAMEDATA" / "MODS"
    for name in (flim_paths.MOD_FOLDER,) + flim_paths.DEV_MOD_FOLDERS:
        if (mods / name / KEY_FILE).is_file():
            out["installed"] = mods / name
            if out["source"]:
                out["same"] = _same_tree(SRC, mods / name)
                if out["same"] and name == flim_paths.MOD_FOLDER:
                    out["same"] = set(_files(mods / name)) == set(_files(SRC))
            break
    return out
def _enable_mods(d):
    f = Path(d) / "GAMEDATA" / "PCBANKS" / "DISABLEMODS.TXT"
    if f.exists():
        try:
            f.rename(f.with_name("DISABLEMODS.TXT.disabled_by_FlyLikeIronMan"))
            print("  Mods were switched off in this game install (DISABLEMODS.TXT): switched them on.")
        except OSError as e:
            print(f"  Mods are switched off in this game install: delete {f} ({e}).")
            return False
    return True
def install(quiet=False):
    st = status()
    d = st["game"]
    if d is None:
        print("No Man's Sky was not found. Open settings.ini and set  path = <your No Man's Sky folder>"
              "  under [game].")
        return False
    _enable_mods(d)
    if st["source"] is None:
        if st["installed"] is None:
            print("The game-side files (GAMEDATA\\MODS\\FlyLikeIronMan) are missing from this download"
                  " and from the game: download the mod again.")
            return False
        return True
    if st["installed"] is not None and st["same"]:
        if not quiet:
            print(f"Game-side files OK ({st['installed']}).")
        return True
    dst = Path(d) / "GAMEDATA" / "MODS" / flim_paths.MOD_FOLDER
    try:
        dst.mkdir(parents=True, exist_ok=True)
        want = set(_files(SRC))
        for rel in _files(dst):
            if rel not in want:
                _writable(dst / rel)
                (dst / rel).unlink()
        for rel in want:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            if (dst / rel).exists():
                _writable(dst / rel)
            shutil.copyfile(SRC / rel, dst / rel)
    except OSError as e:
        print(f"Couldn't copy the game-side files into the game folder ({e}).\n"
              f"Copy the folder  {SRC}\n  into  {Path(d) / 'GAMEDATA' / 'MODS'}  yourself, then start again.")
        return False
    print(f"Installed the game-side files into {dst}.")
    return True
def _writable(p):
    try:
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
def uninstall():
    d = flim_paths.game_dir()
    if d is None:
        print("No Man's Sky was not found; nothing to remove.")
        return True
    dst = Path(d) / "GAMEDATA" / "MODS" / flim_paths.MOD_FOLDER
    if dst.is_dir():
        try:
            shutil.rmtree(dst, onexc=lambda fn, p, e: (_writable(p), fn(p)))
            print(f"Removed {dst}.")
        except OSError as e:
            print(f"Couldn't remove {dst} ({e}): close the game and try again, or delete it yourself.")
            return False
    else:
        print("The game-side files are not installed (nothing to remove).")
    return True
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "uninstall":
        sys.exit(0 if uninstall() else 1)
    if cmd == "status":
        for k, v in status().items():
            print(f"{k:10}: {v}")
        sys.exit(0)
    sys.exit(0 if install() else 1)
