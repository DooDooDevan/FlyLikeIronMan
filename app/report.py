import configparser
import os
import re
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE / "report.txt"
KEY = re.compile(r"WARNING|ERROR|Traceback|body:|model rebuilt|built on|refresh on|mod loaded|reloaded|failed", re.I)
FLIGHT_KEY = re.compile(r"flight ON|flight OFF|landed|stale|isn't moving|re-finding|found you|locate:|couldn't|WARNING|"
                        r"Error|Traceback|deck|game closed|mods switched|into the water|out of the water|ZONE|SPACE", re.I)
def _short_path(p):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 1024):
            return buf.value
    except Exception:
        pass
    return None
def scrub(text):
    home = os.path.expanduser("~")
    homes = {home, os.environ.get("USERPROFILE", ""), _short_path(home) or ""}
    forms = set()
    for h in homes:
        if h:
            forms |= {h, h.replace("\\", "/"), h.replace("\\", "\\\\")}
    for f in sorted(forms, key=len, reverse=True):
        text = re.sub(re.escape(f), "<home>", text, flags=re.I)
    names = {os.environ.get("USERNAME", ""), os.path.basename(home.rstrip("\\/"))}
    short = _short_path(home)
    if short:
        names.add(os.path.basename(short.rstrip("\\/")))
    for old, new in [(n, "<user>") for n in names] + [(os.environ.get("COMPUTERNAME", ""), "<pc>")]:
        if len(old) >= 2:
            text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])", new, text, flags=re.I)
    return text
def tail(path, n):
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return None
def last_session(path, keep=80):
    lines = tail(path, 20000)
    if lines is None:
        return ["(no limbjets_log.txt yet: the in-game part hasn't run on this PC)"]
    start = max((i for i, l in enumerate(lines) if "mod loaded" in l), default=0)
    key = [l for l in lines[start:] if KEY.search(l)]
    return key[:20] + (["   ..."] if len(key) > keep else []) + key[-(keep - 20):] if len(key) > keep else key
def section(title, body):
    return [f"== {title} " + "=" * max(3, 60 - len(title)), *body, ""]
def main():
    out = []
    try:
        ver = (HERE / "VERSION.txt").read_text().strip()
    except OSError:
        ver = "?"
    info = [f"mod version: {ver}"]
    try:
        import flim_paths
        gd = flim_paths.game_dir()
        info.append(f"game folder found: {'yes' if gd else 'NO'} ({flim_paths.game_store(gd) if gd else '-'})")
        if gd:
            info.append(f"Steam build id: {flim_paths.steam_build_id(gd)}")
        import version_check
        st, msg = version_check.check()
        info.append(f"version check: {st}: {msg.splitlines()[0]}")
        ok, msg2 = version_check.launcher_verdict()
        info.append(f"launcher verdict: {'OK' if ok else 'BLOCKED'}: {msg2.splitlines()[0]}")
    except Exception as e:
        info.append(f"(version / game folder check failed: {e!r})")
    try:
        import modsguard
        info.append("game mods switched OFF (DisableAllMods): " + ("YES -- start the game from the launcher, it "
                                                                 "switches them back on" if modsguard.disabled() else "no"))
    except Exception as e:
        info.append(f"(mods check failed: {e!r})")
    out += section("Versions", info)
    changed = []
    try:
        dflt, cur = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#")), \
            configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        dflt.read(HERE / "settings.default.ini", encoding="utf-8-sig")
        cur.read(HERE.parent / "settings.ini", encoding="utf-8-sig")
        for sec in cur.sections():
            for k, v in cur.items(sec):
                if sec == "game" and k == "path":
                    v = "<set>" if v.strip() else ""
                if not dflt.has_option(sec, k) or dflt.get(sec, k).strip() != v.strip():
                    changed.append(f"[{sec}] {k} = {v}")
    except Exception as e:
        changed.append(f"(couldn't compare settings: {e!r})")
    out += section("Settings changed from the defaults", changed or ["(none)"])
    out += section("In-game part (limbjets_log.txt, last session, key lines)", last_session(HERE / "limbjets_log.txt"))
    fl = tail(HERE / "flight_out.txt", 3000)
    out += section("Flight script (flight_out.txt, last run, key lines)",
                   ([l for l in fl if FLIGHT_KEY.search(l)][-60:] or fl[-30:]) if fl else ["(no flight_out.txt yet)"])
    out += section("Setup (setup_log.txt, last lines)", tail(HERE / "setup_log.txt", 30) or ["(no setup_log.txt yet)"])
    out += section("NMS.py window (nmspy_out.txt, last lines)",
                   tail(HERE / "nmspy_out.txt", 25) or ["(no nmspy_out.txt yet)"])
    plog = None
    try:
        import flim_paths
        gd_ = flim_paths.game_dir()
        if gd_:
            logs = sorted((Path(gd_) / "Binaries" / "logs").glob("pymhf-*.log"), key=lambda p: p.stat().st_mtime)
            plog = logs[-1] if logs else None
    except Exception:
        pass
    out += section(f"In-game Python ({plog.name if plog else 'pymhf log'}, newest, last lines)",
                   (tail(plog, 25) if plog else None) or ["(no pymhf log in the game's Binaries\\logs: the in-game "
                                                          "Python never started)"])
    pkg_crash = HERE.parent / "runtime" / "python" / "Lib" / "site-packages" / "pymhf" / "CRITICAL_ERROR.txt"
    for crash_f in (HERE / "CRITICAL_ERROR.txt", pkg_crash, Path.home() / "CRITICAL_ERROR.txt"):
        crash = tail(crash_f, 25)
        if crash:
            out += section(f"NMS.py crash note ({crash_f.name}, {crash_f.parent.name})", crash)
    text = scrub("\n".join(out))
    print(text)
    try:
        OUT.write_text(text, encoding="utf-8")
        print(f"Saved as {scrub(str(OUT))} -- attach that file (or paste this window's text) to your bug report.")
    except OSError as e:
        print(f"(Couldn't save report.txt here: {e.__class__.__name__}. Copy this window's text into the bug report.)")
if __name__ == "__main__":
    main()
