import json
import os
import subprocess
import sys
import time
from pathlib import Path
HERE = Path(__file__).parent
PY = sys.executable
FORCE = "--force" in sys.argv
DRY = "--dry-run" in sys.argv
def nmspy_python():
    dev = HERE / ".venv-nmspy" / "Scripts" / "python.exe"
    if dev.exists():
        return dev
    try:
        import importlib.util
        if importlib.util.find_spec("nmspy") is not None:
            return Path(PY)
    except Exception:
        pass
    return None
NMSPY = nmspy_python()
def cue(name):
    try:
        import winsound
        f = HERE / "sounds" / f"{name}.wav"
        if f.exists():
            winsound.PlaySound(str(f), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass
def nms_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq NMS.exe", "/NH"], capture_output=True)
    return b"NMS.exe" in (r.stdout or b"")
def fullscreen(gd):
    try:
        t = (Path(gd) / "Binaries" / "SETTINGS" / "TKGRAPHICSSETTINGS.MXML").read_text(encoding="utf-8", errors="replace")
        return '<Property name="FullScreen" value="true"' in t
    except OSError:
        return False
def steam_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"], capture_output=True)
    return b"steam.exe" in (r.stdout or b"").lower()
def ensure_steam(gd):
    import flim_paths
    if flim_paths.game_store(gd) != "steam" or steam_running():
        return True
    print("Steam isn't running: starting it (sign in if it asks) ...", flush=True)
    try:
        os.startfile("steam://open/main")
    except OSError:
        pass
    t0 = time.time()
    while not steam_running() and time.time() - t0 < 120:
        time.sleep(2)
    if not steam_running():
        return False
    time.sleep(12)
    return True
def verbose():
    try:
        import settings
        return bool(settings.load(quiet=True).debug["verbose"]) or os.environ.get("FLIM_VERBOSE") == "1"
    except Exception:
        return os.environ.get("FLIM_VERBOSE") == "1"
SETUP_LOG = HERE / "setup_log.txt"
def run(script):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if verbose():
        print(f"--- {script}", flush=True)
        return subprocess.run([PY, "-u", str(HERE / script)], cwd=HERE, env=env).returncode
    try:
        f = open(SETUP_LOG, "a", encoding="utf-8")
    except OSError:
        return subprocess.run([PY, "-u", str(HERE / script)], cwd=HERE, env=env).returncode
    with f:
        f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {script}\n")
        f.flush()
        return subprocess.run([PY, "-u", str(HERE / script)], cwd=HERE, stdout=f, stderr=subprocess.STDOUT,
                              env=env).returncode
def addresses_ok():
    try:
        import numpy as np
        import pymem
        from locate import still_valid
        cfg = json.loads((HERE / "config.json").read_text())
        if not still_valid(int(cfg["body"], 16), int(cfg["vel"], 16)):
            return False
        if "cam" not in cfg:
            return True
        pm = pymem.Pymem("NMS.exe")
        c = np.frombuffer(pm.read_bytes(int(cfg["cam"], 16), 12), dtype=np.float32)
        return abs(float(np.linalg.norm(c)) - 1.0) < 0.02
    except Exception:
        return False
def floating_in_space():
    try:
        import charstate
        return charstate.in_space(charstate.candidates())
    except Exception:
        return False
_IW = {"err": None, "n": None, "last": None}
def _body():
    import pymem
    import lookup
    if _IW.get("pm") is None:
        _IW["pm"] = pymem.Pymem("NMS.exe")
    return lookup.body(_IW["pm"])[0]
def in_world():
    try:
        b = _body()
        _IW["err"], _IW["n"] = None, 1 if b else 0
        ok = b is not None and b == _IW["last"]
        _IW["last"] = b
        return ok
    except Exception as e:
        _IW["err"], _IW["pm"] = f"{type(e).__name__}: {e}", None
        return False
PAUSE_LIMIT = 75
_PZ = {"since": None, "done": False}
def nms_suspended():
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == "nms.exe":
                return p if p.status() == psutil.STATUS_STOPPED else False
    except Exception:
        pass
    return False
def unstick_paused_game():
    if _PZ["done"]:
        return
    p = nms_suspended()
    if not p:
        _PZ["since"] = None
        return
    if _PZ["since"] is None:
        _PZ["since"] = time.time()
        _setup_note("game is paused: NMS.py is loading the in-game part")
        return
    secs = time.time() - _PZ["since"]
    if secs < PAUSE_LIMIT:
        return
    _PZ["done"] = True
    try:
        p.resume()
        _setup_note(f"game still paused after {secs:.0f} s: the in-game part didn't finish loading; resumed the game")
        print("\nThe in-game part (NMS.py) didn't finish loading, and the game was waiting for it.\n"
              "  Resumed the game: it opens now. Flight works; the hand and foot jets may be missing.\n"
              "  For a bug report: run Troubleshoot.bat after you quit (it includes app\\nmspy_out.txt).", flush=True)
    except Exception as e:
        _setup_note(f"game still paused after {secs:.0f} s; couldn't resume it ({type(e).__name__}: {e})")
        print("\nThe game is stuck paused (NMS.py didn't finish loading) and this launcher couldn't resume it.\n"
              "  Stop the game in Steam, then run Troubleshoot.bat and attach app\\report.txt.", flush=True)
def _setup_note(msg):
    try:
        with open(SETUP_LOG, "a", encoding="utf-8") as f_:
            f_.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except OSError:
        pass
def control_card():
    try:
        import settings
        S = settings.load(quiet=True)
        n = lambda a: settings.key_name(S.vk(a))
        dt = S.keys.get("double_tap_space", True)
    except Exception:
        d = dict(forward="W", back="S", left="A", right="D", fly_toggle="F8", climb="R", descend="F",
                 afterburner="SHIFT", faster="PGUP", slower="PGDN", quit="END",
                 arsenal_toggle="MOUSE3")
        n = d.get
        dt = True
    try:
        hold_quit = "hold end" in (HERE / "flight_planet.py").read_text(encoding="utf-8").lower()
    except OSError:
        hold_quit = False
    tog = n("fly_toggle")
    fly = ("double-tap SPACE" + (f" or {tog}" if tog not in ("none", None) else "")) if dt else tog
    move = f"{n('forward')}/{n('left')}/{n('back')}/{n('right')}"
    lines = [
        "CONTROLS",
        f"  {fly:<26} fly / stop",
        f"  {n('forward') + ' / ' + n('back'):<26} throttle up / down (it stays where you leave it)",
        f"  {n('left') + '/' + n('right') + ' + mouse':<26} steer (you fly where you look)",
        f"  {n('climb') + ' / ' + n('descend'):<26} climb / descend",
        f"  {n('afterburner'):<26} afterburner on / off",
        f"  {'CAPS LOCK':<26} sonic boom: each press = one blast (3 per meter, past a quarter throttle)",
        f"  {'CAPS LOCK in space':<26} cruise: press = stage 1, hold = stages 2 / 3 ({n('back')}: down)",
        f"  {'double-tap ' + n('back'):<26} hard brake",
        f"  {'G / hold G':<26} weapons: flying, the multi-tool fires your STARSHIP's",
        f"  {n('arsenal_toggle'):<26} starship weapons / your multi-tool as it is",
        f"  {('hold ' if hold_quit else '') + n('quit'):<26} quit the flight script",
    ]
    return "\n".join(lines)
def start_without_mod(msg):
    import flim_paths
    print(msg)
    cue("error")
    if DRY:
        print("[dry run] would start the game normally (no NMS.py, no flight script).")
        return
    try:
        import setup_mod
        setup_mod.uninstall()
    except Exception:
        pass
    if not nms_running():
        flim_paths.start_game_normally()
    input("\nPress Enter to close this window.")
def main():
    print("Fly Like Iron Man launcher (by DooDooDevan)\n")
    try:
        import flim_paths
        import setup_mod
        import version_check
    except Exception as e:
        print(f"This folder is incomplete ({e}). Download and unzip the mod again.")
        input("Press Enter to close.")
        sys.exit(1)
    gd = flim_paths.game_dir()
    if gd is None:
        print("No Man's Sky wasn't found on this PC.\n"
              "Open settings.ini (in this folder) and under [game] set\n"
              "  path = <your No Man's Sky folder, the one with Binaries and GAMEDATA in it>")
        cue("error")
        input("Press Enter to close.")
        sys.exit(1)
    if FORCE:
        print("Game-version check skipped (--force).")
    else:
        ok, msg = version_check.launcher_verdict()
        if not ok:
            start_without_mod(msg)
            sys.exit(1)
        if msg.startswith("Warning"):
            print(msg)
    if DRY:
        print("[dry run] would install / repair the game-side files and switch the game's mods back on if a "
              "crash turned them off (nothing is changed in a dry run)")
    elif not setup_mod.install(quiet=True):
        print("\nThe flight script still works without the game-side files, but the pose and limb jets won't.")
    if not DRY and not nms_running():
        try:
            import modsguard
            if modsguard.guard(flim_paths.game_exe(gd)):
                print("The game had switched all mods off (it does that after a crash): switched back on.")
        except Exception:
            pass
    if fullscreen(gd):
        print("Note: No Man's Sky is set to Fullscreen, where the mod's HUD can't show. In the game: Options > Display >"
              " Window Mode: Borderless.\n")
    if DRY:
        print(f"[dry run] game folder: {gd} ({flim_paths.game_store(gd)}); "
              f"NMS.py: {'yes' if NMSPY else 'NOT available'}; game running: {nms_running()}")
        print("[dry run] would start the game through NMS.py, then the flight script.\n")
        print(control_card())
        return
    if not nms_running():
        if not ensure_steam(gd):
            cue("error")
            print("\nSteam didn't start. Start Steam and sign in, then run this launcher again.")
            input("Press Enter to close.")
            sys.exit(1)
        nmspy_p = None
        if NMSPY is not None:
            print("Starting No Man's Sky through NMS.py (for the hand and foot jets).")
            print("Two NMS.py windows open; leave them open while you play (closing them closes the game).\n")
            env = dict(os.environ)
            env["PATH"] = str(Path(PY).parent) + os.pathsep + env.get("PATH", "")
            nmspy_p = subprocess.Popen([str(NMSPY), "-u", str(HERE / "run_nmspy.py")], cwd=HERE, env=env,
                                       creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            print("Starting No Man's Sky (NMS.py isn't installed here, so no hand and foot jets).")
            flim_paths.start_game_normally(gd)
        t0 = time.time()
        while not nms_running():
            if nmspy_p is not None and nmspy_p.poll() is not None and not nms_running():
                cue("error")
                print("\nNMS.py stopped before the game started. Is Steam running and signed in? Did an antivirus "
                      "block it? Troubleshoot.bat shows what the mod finds; then start the launcher again.")
                input("Press Enter to close.")
                sys.exit(1)
            if time.time() - t0 > 180:
                cue("error")
                print("\nNo Man's Sky didn't start within 3 minutes. Is Steam running and logged in? Did an "
                      "antivirus block NMS.py? Start the launcher again (Troubleshoot.bat shows what it finds).")
                input("Press Enter to close.")
                sys.exit(1)
            time.sleep(2)
    else:
        print("No Man's Sky is already running: flight works, but the hand/foot jets need the game")
        print("to be started from this launcher (close the game first next time).\n")
    print("Load your save. Waiting until you're in the world...", flush=True)
    t_wait, told, last_note = time.time(), 0.0, None
    while not in_world():
        if not nms_running():
            print("\nNo Man's Sky closed before a save was loaded: nothing to do. Start the launcher again to play.")
            input("Press Enter to close.")
            sys.exit(0)
        unstick_paused_game()
        note = (f"waiting for the world: can't read the game ({_IW['err']})" if _IW["err"] else
                f"waiting for the world: your character {'is there, checking again' if _IW['n'] else 'is not there yet'}")
        if note != last_note:
            _setup_note(note)
            last_note = note
        if time.time() - t_wait > 90 and time.time() - told > 60:
            told = time.time()
            if _IW["err"]:
                print("\nStill can't see your character: this launcher can't read No Man's Sky's memory.\n"
                      f"  ({_IW['err']})\n"
                      "  Usually Windows is blocking it: close the game, then right-click 'Start Fly Like Iron Man.bat'\n"
                      "  and choose 'Run as administrator' (if Steam runs as administrator, the launcher must too).\n"
                      "  An antivirus can block it as well: allow this folder's runtime\\python\\python.exe.", flush=True)
            else:
                print("\nStill waiting for your character. Are you in the world, not a\n"
                      "  menu or the loading screen? Walk a few steps or use your jetpack once.", flush=True)
        time.sleep(3)
    _setup_note("in the world")
    time.sleep(5)
    found_ = None
    try:
        found_ = _body()
    except Exception:
        pass
    if found_:
        print("Found your character: no setup needed.")
    elif addresses_ok():
        print("Found your character from last time: no setup needed.")
    elif floating_in_space():
        print("You're out in space: no setup jump there. The suit syncs to you as soon as you move")
        print("(W / your jetpack).")
    else:
        print("\nFinding your character. Click into the game and stand still on open ground.")
        print("Starting in 10 seconds (the character jumps once, then the camera turns by itself)...")
        for i in range(10, 0, -1):
            print(f"  {i} ", end="\r", flush=True)
            cue("tick")
            time.sleep(1)
        print("      ")
        if run("locate.py") != 0 or run("camfind.py") != 0 or not addresses_ok():
            print("\nThe setup jump didn't find you (inside, in a menu, in your ship, or moving?): starting anyway.\n"
                  "Walk a few steps (or use your jetpack in space) and the suit syncs to you.\n"
                  f"(Setup details for a bug report: {SETUP_LOG})")
    print("\nReady.\n")
    print(control_card())
    print()
    cue("ready")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        log_ = open(HERE / "flight_out.txt", "w", encoding="utf-8", errors="replace")
    except OSError:
        log_ = None
    p = subprocess.Popen([PY, "-u", str(HERE / "flight_planet.py"), "--pose"], cwd=HERE, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", bufsize=1)
    while True:
        try:
            for line in p.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if log_ is not None:
                    try:
                        log_.write(line)
                        log_.flush()
                    except OSError:
                        log_ = None
            break
        except KeyboardInterrupt:
            continue
    p.wait()
    if log_ is not None:
        log_.close()
if __name__ == "__main__":
    main()
