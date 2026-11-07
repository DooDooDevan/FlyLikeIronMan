import configparser
import math
import os
import re
import shutil
import threading
import time
from pathlib import Path
APP = Path(__file__).resolve().parent
try:
    from flim_paths import PKG
except Exception:
    PKG = APP
INI = PKG / "settings.ini"
DEFAULT_INI = APP / "settings.default.ini"
SESSION_INI = INI.with_name("settings.panel-session.ini")
VK = {f"F{i}": 0x6F + i for i in range(1, 13)}
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({f"NUMPAD{d}": 0x60 + d for d in range(10)})
VK.update(SHIFT=0x10, CTRL=0x11, ALT=0x12, SPACE=0x20, HOME=0x24, END=0x23, PGUP=0x21, PGDN=0x22,
          INSERT=0x2D, DELETE=0x2E, SCROLLLOCK=0x91, PAUSE=0x13, TAB=0x09, CAPSLOCK=0x14,
          BACKSPACE=0x08, ENTER=0x0D, UP=0x26, DOWN=0x28, LEFT=0x25, RIGHT=0x27,
          LSHIFT=0xA0, RSHIFT=0xA1, LCTRL=0xA2, RCTRL=0xA3, LALT=0xA4, RALT=0xA5,
          MOUSE3=0x04, MOUSE4=0x05, MOUSE5=0x06)
ALIASES = {"CONTROL": "CTRL", "PAGEUP": "PGUP", "PAGEDOWN": "PGDN", "PGDOWN": "PGDN", "DEL": "DELETE",
           "INS": "INSERT", "SCROLL": "SCROLLLOCK", "SCROLL_LOCK": "SCROLLLOCK", "XBUTTON1": "MOUSE4",
           "XBUTTON2": "MOUSE5", "MIDDLEMOUSE": "MOUSE3", "RETURN": "ENTER", "ESC": None}
DEFAULTS = {
    "keys": dict(forward="W", back="S", left="A", right="D", fly_toggle="F8", climb="R", descend="F",
                 afterburner="SHIFT", faster="PGUP", slower="PGDN", quit="END",
                 double_tap_space="yes", arm_toggle="none", arsenal_toggle="MOUSE3",
                 panel="F7"),
    "flight": dict(start_speed=18.0, remember_speed="yes", min_speed=5.0, max_speed=80.0,
                   afterburner_mode="toggle", climb_fires_afterburner="yes",
                   double_tap_window=0.30, flip_strafe="no", dive_lands="yes",
                   throttle_up_time=2.5, throttle_down_time=1.5, throttle_curve=1.6, hover_detent=0.5,
                   reverse_speed=20.0, afterburner_power=2.4, afterburner_time=10.0, afterburner_recharge=15.0,
                   dive_boost=1.15, hard_brake_window=0.30,
                   pilot_flame=0.2,
                   hover_move_speed=10.0),
    "boom": dict(charge_time=1.2, kick_scale=1.0, boost=6.0, refill_time=16.0),
    "cruise": dict(top_speed_kms=200.0, tier_fill_time=2.0, drain_time=2.0),
    "camera": dict(recenter_delay=5.0, speed_effects="yes", motion_blur="yes", effects_strength=1.0,
                   camera_kicks="yes"),
    "sound": dict(cues="yes", sound_volume=1000, suit_sounds="yes", boom_sounds="yes",
                  interplanetary="yes", hum_volume=0.55),
    "hud": dict(hud="yes", space_map="yes", shock_waves="yes"),
    "effects": dict(warp_effects="yes", warp_blur="yes"),
    "panel": dict(always_on_top="no", open_with_flight="no", confirm_quit="yes", warm_start="yes"),
    "debug": dict(flight_log="no", verbose="no"),
}
KEY_SETTINGS = ("forward", "back", "left", "right", "fly_toggle", "climb", "descend", "afterburner",
                "faster", "slower", "quit", "arm_toggle", "arsenal_toggle", "panel")
MOVE_KEYS = ("forward", "back", "left", "right", "climb", "descend")
CHOICES = {("flight", "afterburner_mode"): ("toggle", "hold")}
LEGACY = {("hud", "hud"): {"gauge": "yes", "classic": "yes"},
          ("sound", "interplanetary"): {"mine": "yes", "classic": "yes"}}
RANGES = {("flight", "start_speed"): (1, 500), ("flight", "min_speed"): (1, 500),
          ("flight", "max_speed"): (1, 500), ("flight", "double_tap_window"): (0.1, 1.0),
          ("camera", "recenter_delay"): (0.0, 60.0), ("sound", "sound_volume"): (0, 1000),
          ("flight", "throttle_up_time"): (0.3, 10.0), ("flight", "throttle_down_time"): (0.3, 10.0),
          ("flight", "throttle_curve"): (1.0, 3.0), ("flight", "hover_detent"): (0.0, 2.0),
          ("flight", "reverse_speed"): (2.0, 80.0), ("flight", "afterburner_power"): (1.0, 5.0),
          ("flight", "afterburner_time"): (2.0, 60.0), ("flight", "afterburner_recharge"): (2.0, 120.0),
          ("flight", "dive_boost"): (1.0, 2.0),
          ("flight", "hard_brake_window"): (0.15, 1.0), ("flight", "pilot_flame"): (0.05, 1.0),
          ("flight", "hover_move_speed"): (1.0, 60.0),
          ("boom", "charge_time"): (0.3, 5.0), ("boom", "kick_scale"): (0.0, 3.0), ("boom", "boost"): (1.0, 12.0),
          ("boom", "refill_time"): (2.0, 120.0),
          ("cruise", "top_speed_kms"): (100.0, 450.0), ("cruise", "tier_fill_time"): (0.3, 5.0),
          ("cruise", "drain_time"): (0.3, 10.0),
          ("camera", "effects_strength"): (0.0, 2.0), ("sound", "hum_volume"): (0.0, 1.0)}
TRUE, FALSE = ("yes", "true", "on", "1"), ("no", "false", "off", "0")
PAD_LIMITS = {"stick_curve": (0.5, 4.0), "double_tap_window": (0.15, 1.0), "quit_hold": (0.0, 5.0),
              "stick_deadzone": (0.0, 0.95), "trigger_deadzone": (0.0, 0.95), "move_threshold": (0.0, 0.95),
              "rumble_strength": (0.0, 0.95)}
PAD_BOOLS = ("enabled", "rumble")
def key_code(name):
    n = str(name).strip().upper().replace(" ", "")
    if n in ("", "NONE", "OFF", "NO", "-"):
        return 0
    n = ALIASES.get(n, n)
    return VK.get(n) if n else None
def key_name(vk):
    for n, c in VK.items():
        if c == vk and len(n) > 0:
            return n
    return "none" if not vk else f"0x{vk:02X}"
class Settings:
    def __init__(self, values, raw, warnings, path, unreadable=False):
        self._v, self._raw, self.warnings, self.path = values, raw, warnings, path
        self.unreadable = unreadable
        for sec in values:
            setattr(self, sec, values[sec])
    def vk(self, action):
        return self._v["keys"][action]
    def raw(self, section):
        return dict(self._raw.get(section, {}))
def _coerce(sec, name, text, default, warn):
    t = str(text).split(";")[0].split("#")[0].strip() if not isinstance(text, (int, float)) else text
    t = LEGACY.get((sec, name), {}).get(str(t).lower(), t)
    if sec == "keys" and name in KEY_SETTINGS:
        code = key_code(t)
        if code is None:
            warn(f"settings.ini: '{name} = {t}' isn't a key name I know, using {default}")
            return key_code(default)
        return code
    if isinstance(default, str) and default.lower() in TRUE + FALSE:
        s = str(t).lower()
        if s in TRUE:
            return True
        if s in FALSE:
            return False
        warn(f"settings.ini: '{name} = {t}' should be yes or no, using {default}")
        return default.lower() in TRUE
    if (sec, name) in CHOICES:
        s = str(t).lower()
        if s in CHOICES[(sec, name)]:
            return s
        warn(f"settings.ini: '{name} = {t}' should be one of {' / '.join(CHOICES[(sec, name)])}, using {default}")
        return default
    if isinstance(default, (int, float)):
        try:
            x = type(default)(float(t))
            if not math.isfinite(x):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            warn(f"settings.ini: '{name} = {t}' isn't a number, using {default:g}")
            return default
        lo, hi = RANGES.get((sec, name), (None, None))
        if lo is not None and not lo <= x <= hi:
            warn(f"settings.ini: '{name} = {t}' should be between {lo:g} and {hi:g}, using {default:g}")
            return default
        return x
    return t
_READ_TRIES, _READ_GAP = 10, 0.03
_LAST_GOOD = {}
def _read_bytes(path):
    for i in range(_READ_TRIES):
        try:
            return Path(path).read_bytes()
        except FileNotFoundError:
            return None
        except PermissionError:
            if i == _READ_TRIES - 1:
                raise
            time.sleep(_READ_GAP)
def _decode(b):
    if b.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return b.decode("utf-16")
        except UnicodeDecodeError:
            pass
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    out = []
    for part in b.split(b"\n"):
        try:
            out.append(part.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(part.decode("mbcs", errors="replace"))
    return "\n".join(out)
def _lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
def _new_cp():
    return configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"), strict=False)
def _parse(lines, path, warn):
    cp = _new_cp()
    try:
        cp.read_string("\n".join(lines) + "\n", source=str(path))
        return cp
    except configparser.MissingSectionHeaderError:
        pass
    except configparser.ParsingError as e:
        for n, ln in e.errors[:3]:
            warn(f"settings.ini: line {n} isn't a setting (ignored): {str(ln).strip()[:60]}")
        return cp
    roles = _scan(lines)
    top = next((i for i, r in enumerate(roles) if r[0] == "header"), len(lines))
    above = [i for i in range(top) if roles[i][0] != "blank"]
    for i in above[:3]:
        warn(f"settings.ini: line {i + 1} is above every [section] (ignored): {lines[i].strip()[:60]}")
    lines = ["" if i < top else ln for i, ln in enumerate(lines)]
    cp = _new_cp()
    try:
        cp.read_string("\n".join(lines) + "\n", source=str(path))
    except configparser.ParsingError as e:
        for n, ln in e.errors[:3]:
            warn(f"settings.ini: line {n} isn't a setting (ignored): {str(ln).strip()[:60]}")
    return cp
RETIRED = {("flight", "barrel_roll_double_tap"), ("flight", "barrel_roll_kick"), ("pad", "barrel_left"),
           ("pad", "barrel_right"), ("keys", "drone"), ("sound", "interplanetary_sounds"),
           ("keys", "shoulder_swap"), ("pad", "shoulder_swap")}
def load(path=None, quiet=False):
    path = Path(path) if path else INI
    warnings = []
    warn = warnings.append
    if not path.exists() and DEFAULT_INI.exists():
        try:
            shutil.copyfile(DEFAULT_INI, path)
        except OSError:
            pass
    cp, unreadable, ok = _new_cp(), False, False
    try:
        b = _read_bytes(path)
        if b is not None:
            cp = _parse(_lines(_decode(b)), path, warn)
            ok = True
    except OSError:
        unreadable = True
    except Exception as e:
        warn(f"settings.ini couldn't be read ({e.__class__.__name__}): using the defaults for everything")
        cp = _new_cp()
    where = os.path.abspath(str(path))
    if unreadable:
        last = _LAST_GOOD.get(where)
        warn("settings.ini couldn't be read (in use by another program): "
             + ("kept the settings as they were" if last else "using the defaults for now"))
        if last:
            if not quiet:
                for w in warnings:
                    print(w, flush=True)
            return Settings({s: dict(v) for s, v in last[0].items()}, {s: dict(v) for s, v in last[1].items()},
                            warnings, path, unreadable=True)
    raw = {s: dict(cp.items(s)) for s in cp.sections()}
    values = {}
    for sec, defs in DEFAULTS.items():
        got = raw.get(sec, {})
        values[sec] = {}
        for name, default in defs.items():
            values[sec][name] = _coerce(sec, name, got[name], default, warn) if name in got \
                else _coerce(sec, name, default, default, lambda m: None)
        for name in got:
            if name not in defs and (sec, name) not in RETIRED:
                warn(f"settings.ini: [{sec}] has no setting called '{name}' (ignored)")
    snd, got = values["sound"], raw.get("sound", {})
    if "interplanetary" not in got and "interplanetary_sounds" in got:
        snd["interplanetary"] = _coerce("sound", "interplanetary", got["interplanetary_sounds"], "yes", warn)
    f = values["flight"]
    if f["min_speed"] >= f["max_speed"]:
        warn(f"settings.ini: min_speed ({f['min_speed']:g}) must be below max_speed ({f['max_speed']:g}), "
             "using 5 and 80")
        f["min_speed"], f["max_speed"] = DEFAULTS["flight"]["min_speed"], DEFAULTS["flight"]["max_speed"]
    f["start_speed"] = min(max(f["start_speed"], f["min_speed"]), f["max_speed"])
    k = values["keys"]
    for a in MOVE_KEYS:
        if not k[a]:
            warn(f"settings.ini: '{a}' can't be none, using {DEFAULTS['keys'][a]}")
            k[a] = key_code(DEFAULTS["keys"][a])
    if ok:
        if len(_LAST_GOOD) > 32:
            _LAST_GOOD.clear()
        _LAST_GOOD[where] = ({s: dict(v) for s, v in values.items()}, {s: dict(v) for s, v in raw.items()})
    if not quiet:
        for w in warnings:
            print(w, flush=True)
    return Settings(values, raw, warnings, path, unreadable=unreadable)
class SettingsError(ValueError):
    def __init__(self, msg, key=None):
        super().__init__(msg)
        self.key = key
_SAVE_LOCK = threading.Lock()
_HEADER = re.compile(r"\[(.+)\]")
_INLINE = re.compile(r"(^|\s)[;#]")
_DELIM = re.compile(r"[=:]")
def _pad_defaults():
    try:
        import xpad
        return dict(xpad.PAD_DEFAULTS)
    except Exception:
        return {}
def _clean(line):
    s = line.strip()
    if not s or s[0] in ";#":
        return ""
    m = _INLINE.search(line)
    return line[:m.start() if m else None].strip()
def _num_text(x, integer=False):
    if integer:
        return str(int(round(x)))
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.6f}".rstrip("0").rstrip(".")
def _value_text(sec, key, value, pad_defs):
    where = f"[{sec}] {key}"
    if isinstance(value, bool):
        text = "yes" if value else "no"
    elif isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise SettingsError(f"{where}: {value} isn't a number", (sec, key))
        text = _num_text(float(value))
    else:
        text = str(value).strip()
    if "\n" in text or "\r" in text:
        raise SettingsError(f"{where}: a value can't have a line break in it", (sec, key))
    if sec == "game":
        if _INLINE.search(text):
            raise SettingsError(f"{where}: a space followed by ; or # would cut the path short", (sec, key))
        return text
    if ";" in text or "#" in text:
        raise SettingsError(f"{where}: a value can't contain ; or #", (sec, key))
    if sec == "pad":
        if "%" in text:
            raise SettingsError(f"{where}: a controller setting can't contain %", (sec, key))
        if key in PAD_BOOLS:
            if text.lower() not in TRUE + FALSE:
                raise SettingsError(f"{where} should be yes or no", (sec, key))
            return "yes" if text.lower() in TRUE else "no"
        if key in PAD_LIMITS:
            lo, hi = PAD_LIMITS[key]
            try:
                x = float(text)
            except ValueError:
                raise SettingsError(f"{where}: '{text}' isn't a number", (sec, key)) from None
            if not (math.isfinite(x) and lo <= x <= hi):
                raise SettingsError(f"{where} should be between {lo:g} and {hi:g}", (sec, key))
            return _num_text(x)
        import xpad
        combo = xpad._parse_combo(text)
        if combo is None:
            raise SettingsError(f"{where}: '{text}' isn't a pad button I know", (sec, key))
        if len(combo) > 1 and key != "quit":
            raise SettingsError(f"{where}: only quit can be a combination (with +)", (sec, key))
        return "+".join(combo) if combo else "none"
    default = DEFAULTS[sec][key]
    if sec == "keys" and key in KEY_SETTINGS:
        code = key_code(text)
        if code is None:
            raise SettingsError(f"{where}: '{text}' isn't a key name I know", (sec, key))
        if not code and key in MOVE_KEYS:
            raise SettingsError(f"{where} can't be none", (sec, key))
        return key_name(code)
    if isinstance(default, str) and default.lower() in TRUE + FALSE:
        if text.lower() not in TRUE + FALSE:
            raise SettingsError(f"{where} should be yes or no", (sec, key))
        return "yes" if text.lower() in TRUE else "no"
    if (sec, key) in CHOICES:
        if text.lower() not in CHOICES[(sec, key)]:
            raise SettingsError(f"{where} should be one of {' / '.join(CHOICES[(sec, key)])}", (sec, key))
        return text.lower()
    if isinstance(default, (int, float)):
        try:
            x = float(text)
        except ValueError:
            raise SettingsError(f"{where}: '{text}' isn't a number", (sec, key)) from None
        lo, hi = RANGES.get((sec, key), (-math.inf, math.inf))
        if not (math.isfinite(x) and lo <= x <= hi):
            raise SettingsError(f"{where} should be between {lo:g} and {hi:g}", (sec, key))
        return _num_text(x, integer=isinstance(default, int) and not isinstance(default, bool))
    return text
def _norm_changes(changes, before):
    pad_defs = _pad_defaults()
    out = {}
    for (sec, key), value in dict(changes).items():
        sec, key = str(sec).strip().lower(), str(key).strip().lower()
        known = (sec in DEFAULTS and key in DEFAULTS[sec]) or (sec == "pad" and key in pad_defs) \
            or (sec, key) == ("game", "path")
        if not known:
            raise SettingsError(f"[{sec}] has no setting called '{key}'", (sec, key))
        out[(sec, key)] = _value_text(sec, key, value, pad_defs)
    if ("flight", "min_speed") in out or ("flight", "max_speed") in out:
        lo = float(out.get(("flight", "min_speed"), before.flight["min_speed"]))
        hi = float(out.get(("flight", "max_speed"), before.flight["max_speed"]))
        if lo >= hi:
            raise SettingsError(f"the lowest speed ({lo:g}) must be below the top speed ({hi:g})",
                                ("flight", "min_speed" if ("flight", "min_speed") in out else "max_speed"))
    return out
def _snapshot(path):
    try:
        return _read_bytes(path)
    except OSError:
        raise SettingsError("settings.ini is open in another program: close it (or wait a moment) and try "
                            "again") from None
def _read_text(path, b=False):
    b = _snapshot(path) if b is False else b
    if b is None:
        return "", "\r\n"
    text = _decode(b)
    crlf = text.count("\r\n")
    cr, lf = text.count("\r") - crlf, text.count("\n") - crlf
    nl = "\r\n" if crlf and crlf >= lf and crlf >= cr else ("\r" if cr > lf else "\n")
    return "\n".join(_lines(text)), nl
def _scan(lines):
    out, sect, opt, indent = [], None, None, 0
    for ln in lines:
        c = _clean(ln)
        if not c:
            out.append(("blank", sect, None))
            continue
        cur = len(ln) - len(ln.lstrip())
        if sect is not None and opt and cur > indent:
            out.append(("cont", sect, opt))
            continue
        indent = cur
        m, d = _HEADER.match(c), _DELIM.search(c)
        if m:
            sect, opt = m.group(1), None
            out.append(("header", sect, None))
        elif sect is None or d is None or not c[:d.start()].strip():
            out.append(("junk", sect, None))
        else:
            opt = c[:d.start()].strip().lower()
            out.append(("key", sect, opt))
    return out
def _replace_value(line, text):
    d = _DELIM.search(line).start()
    m = _INLINE.search(line, d + 1)
    cstart = m.start() if m else len(line)
    vstart = d + 1
    while vstart < cstart and line[vstart] in " \t":
        vstart += 1
    while cstart > vstart and line[cstart - 1] in " \t":
        cstart -= 1
    head = line[:vstart]
    if vstart == d + 1 and d > 0 and line[d - 1] in " \t":
        head += " "
    return head + text + (line[cstart:] if m else "")
def _default_blocks():
    text, _ = _read_text(DEFAULT_INI)
    lines = text.replace("\r\n", "\n").split("\n")
    roles = _scan(lines)
    head, above, order, hdr_at = {}, {}, {}, {}
    for i, (kind, sec, key) in enumerate(roles):
        if kind == "header":
            j, block = i + 1, []
            while j < len(lines) and roles[j][0] == "blank" and lines[j].strip():
                block.append(lines[j])
                j += 1
            head.setdefault(sec, block)
            hdr_at.setdefault(sec, i)
            order.setdefault(sec, [])
        elif kind == "key":
            j, block = i - 1, []
            while j >= 0 and roles[j][0] == "blank" and lines[j].strip():
                block.insert(0, lines[j])
                j -= 1
            above.setdefault((sec, key), (block, bool(block) and j == hdr_at.get(sec)))
            order.setdefault(sec, []).append(key)
    return head, above, order
def _repair(lines):
    lines = list(lines)
    for i, (kind, sec, _) in enumerate(_scan(lines)):
        if kind == "junk":
            lines[i] = ("; (ignored: above every [section]) " if sec is None else "; (ignored: not a setting) ") \
                + lines[i].strip()
    roles = _scan(lines)
    heads = [i for i, r in enumerate(roles) if r[0] == "header"]
    blocks = [(roles[i][1], i, heads[n + 1] if n + 1 < len(heads) else len(lines)) for n, i in enumerate(heads)]
    if len({b[0] for b in blocks}) == len(blocks):
        return lines
    def body_end(i, end):
        last = i
        for j in range(i + 1, end):
            if roles[j][0] in ("key", "cont"):
                last = j
        return last + 1
    first, moved, gone = {}, {}, set()
    for sec, i, end in blocks:
        if sec not in first:
            first[sec] = (i, end)
            continue
        be = body_end(i, end)
        at = body_end(*first[sec]) - 1
        moved.setdefault(at, []).extend(ln.lstrip() if roles[j][0] == "key" else ln
                                        for j, ln in zip(range(i + 1, be), lines[i + 1:be]))
        gone.update(range(i, be))
    out = []
    for j, ln in enumerate(lines):
        if j not in gone:
            out.append(ln)
        out.extend(moved.get(j, []))
    return out
def _edit(text, todo):
    lines = _lines(text)
    if lines and lines[-1] == "":
        lines.pop()
    lines = _repair(lines)
    roles = _scan(lines)
    drop, written, added = set(), [], []
    where = {}
    for i, (kind, sec, key) in enumerate(roles):
        if kind == "key":
            where.setdefault((sec, key), []).append(i)
    def drop_conts(i):
        j = i + 1
        while j < len(lines) and roles[j][0] in ("cont", "blank"):
            if roles[j][0] == "cont":
                drop.add(j)
            j += 1
    for at in where.values():
        for i in at[:-1]:
            drop.add(i)
            drop_conts(i)
    for (sec, key), val in todo.items():
        at = where.get((sec, key))
        if not at:
            continue
        lines[at[-1]] = _replace_value(lines[at[-1]], val)
        drop_conts(at[-1])
        written.append((sec, key))
    missing = [k for k in todo if k not in where]
    inserts, tail = {}, []
    if missing:
        head, above, order = _default_blocks()
        secs = list(DEFAULTS) + ["pad", "game"]
        missing.sort(key=lambda k: (secs.index(k[0]) if k[0] in secs else 99,
                                    order.get(k[0], []).index(k[1]) if k[1] in order.get(k[0], []) else 999))
        last = {}
        for i, (kind, sec, key) in enumerate(roles):
            if kind == "header" or (kind in ("key", "cont") and sec in last):
                last[sec] = i
        new_secs = {}
        for sec, key in missing:
            block, is_head = above.get((sec, key), ([], False))
            entry = list(block) + [f"{key} = {todo[(sec, key)]}"]
            if sec in last:
                inserts.setdefault(last[sec], []).extend(entry)
            else:
                if sec not in new_secs:
                    new_secs[sec] = [f"[{sec}]"] + list(head.get(sec, []))
                    if is_head:
                        entry = entry[len(block):]
                new_secs[sec].extend(entry)
            added.append((sec, key))
        for block in new_secs.values():
            prev = tail[-1] if tail else (lines[-1] if lines else "")
            if prev.strip():
                tail.append("")
            tail.extend(block)
    out = []
    for i, ln in enumerate(lines):
        if i not in drop:
            out.append(ln)
        out.extend(inserts.get(i, []))
    return out + tail, written, added
def _check_tmp(tmp, todo, before):
    s = load(tmp, quiet=True)
    if s.unreadable:
        return "another program held the new file while it was being checked: try again"
    new = [w for w in s.warnings if w not in before.warnings]
    for (sec, key), text in todo.items():
        if sec == "pad":
            continue
        if sec == "game":
            got = s.raw("game").get("path", "")
            if got != text:
                return "[game] path didn't read back the way it was written"
            continue
        hit = [w for w in new if f"'{key} " in w or f" {key} (" in w or f"'{key}'" in w]
        if hit:
            return hit[0]
        want = _coerce(sec, key, text, DEFAULTS[sec][key], lambda m: None)
        got = getattr(s, sec)[key]
        if got != want and (sec, key) != ("flight", "start_speed"):
            return f"[{sec}] {key} didn't read back the way it was written"
    import xpad
    logs_b, logs_a = [], []
    xpad.load_pad_settings(str(before.path), log=logs_b.append)
    got = xpad.load_pad_settings(str(tmp), log=logs_a.append)
    broken = lambda logs: any("couldn't read it" in m for m in logs)
    if broken(logs_a):
        if not broken(logs_b):
            return "the controller settings ([pad]) wouldn't read any more"
        return None
    pads = {k: t for (sec, k), t in todo.items() if sec == "pad"}
    if pads:
        for key, text in pads.items():
            g = got.get(key)
            if key in PAD_BOOLS:
                ok = g == (text == "yes")
            elif key in PAD_LIMITS:
                ok = abs(float(g) - float(text)) < 1e-9
            else:
                ok = "+".join(g) == ("" if text == "none" else text)
            if not ok:
                return f"[pad] {key} didn't read back the way it was written"
    return None
def validate(changes, path=None):
    return _norm_changes(changes, load(Path(path) if path else INI, quiet=True))
def save(changes, path=None):
    path = Path(path) if path else INI
    with _SAVE_LOCK:
        if not path.exists() and DEFAULT_INI.exists():
            try:
                shutil.copyfile(DEFAULT_INI, path)
            except PermissionError:
                raise SettingsError("the folder is read-only (move it out of Program Files)") from None
            except OSError:
                pass
        for _ in range(3):
            got = _save_once(path, changes)
            if got is not None:
                return got
        raise SettingsError("settings.ini kept changing while it was being saved (another program writes it): "
                            "try again")
def _save_once(path, changes):
    before = load(path, quiet=True)
    if before.unreadable:
        raise SettingsError("settings.ini is open in another program: close it (or wait a moment) and try again")
    todo = _norm_changes(changes, before)
    src = _snapshot(path)
    text, nl = _read_text(path, src)
    lines, written, added = _edit(text, todo)
    out = nl.join(lines) + nl
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(out)
            f.flush()
            os.fsync(f.fileno())
    except PermissionError:
        raise SettingsError("the folder is read-only (move it out of Program Files)") from None
    except OSError as e:
        raise SettingsError(f"settings.ini couldn't be written ({e.strerror or e.__class__.__name__})") from None
    try:
        bad = _check_tmp(tmp, todo, before)
    except Exception as e:
        bad = f"the check after writing failed ({e.__class__.__name__})"
    if bad:
        _unlink(tmp)
        raise SettingsError(f"not saved: {bad}")
    if _snapshot(path) != src:
        _unlink(tmp)
        return None
    for i in range(20):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if i == 19:
                _unlink(tmp)
                raise SettingsError("settings.ini is read-only or open in another program "
                                    "(move the folder out of Program Files, or close that program)") from None
            time.sleep(0.05)
        except OSError as e:
            _unlink(tmp)
            raise SettingsError(f"settings.ini couldn't be replaced ({e.strerror or e.__class__.__name__})") \
                from None
    got = _LAST_GOOD.pop(os.path.abspath(str(tmp)), None)
    if got:
        _LAST_GOOD[os.path.abspath(str(path))] = got
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        mtime = 0.0
    return path, written, added, mtime
def _unlink(p):
    try:
        os.unlink(p)
    except OSError:
        pass
def reset_all_changes():
    out = {(sec, k): v for sec, defs in DEFAULTS.items() for k, v in defs.items()}
    out.update({("pad", k): v for k, v in _pad_defaults().items()})
    return out
def begin_session(path=None, session=None):
    path, session = Path(path) if path else INI, Path(session) if session else SESSION_INI
    if not path.exists():
        load(path, quiet=True)
    try:
        shutil.copyfile(path, session)
        return session
    except OSError:
        return None
def _value_out(sec, key, v):
    if sec == "keys" and key in KEY_SETTINGS:
        return key_name(v)
    return v
def session_changes(path=None, session=None):
    path, session = Path(path) if path else INI, Path(session) if session else SESSION_INI
    if not session.exists():
        return {}
    now, then = load(path, quiet=True), load(session, quiet=True)
    out = {}
    for sec, defs in DEFAULTS.items():
        for k in defs:
            a, b = getattr(now, sec)[k], getattr(then, sec)[k]
            if a != b:
                out[(sec, k)] = _value_out(sec, k, b)
    try:
        import xpad
        pa, pb = xpad.load_pad_settings(path, log=lambda m: None), xpad.load_pad_settings(session, log=lambda m: None)
        for k in pb:
            if pa.get(k) != pb[k]:
                v = pb[k]
                out[("pad", k)] = ("+".join(v) or "none") if isinstance(v, tuple) else v
    except Exception:
        pass
    ga, gb = now.raw("game").get("path", ""), then.raw("game").get("path", "")
    if ga != gb:
        out[("game", "path")] = gb
    return out
if __name__ == "__main__":
    s = load()
    print("settings file:", s.path)
    for sec in DEFAULTS:
        for n, v in getattr(s, sec).items():
            print(f"  [{sec}] {n} = {key_name(v) if sec == 'keys' and n in KEY_SETTINGS else v}")
