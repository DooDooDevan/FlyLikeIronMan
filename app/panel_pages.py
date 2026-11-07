import math
import sys
import tempfile
import threading
import time
import tkinter as tk
import wave
from collections import namedtuple
from pathlib import Path
import panel_widgets as pw
import settings
try:
    import control
except Exception:
    control = None
HERE = Path(__file__).resolve().parent
SOUND_DIR = HERE / "sounds"
MPS = 10.0 / 18.0 / 0.20
BOOM_KICKS = (30.0, 50.0, 80.0)
TIERS_KMS = (6.0, 50.0, 200.0)
FAR_KMS = 450.0
Row = namedtuple("Row", "page card sec key label help kind spec fmt")
Card = namedtuple("Card", "page id title accent sections info")
def mps(level):
    return float(level) * MPS
def kmh(level):
    return float(level) * MPS * 3.6
def speed_text(level):
    return f"{mps(level):,.0f} m/s // {kmh(level):,.0f} km/h"
def _secs(d=1):
    return lambda v: f"{float(v):.{d}f} S"
def _times(d=1):
    return lambda v: f"×{float(v):.{d}f}"
def _pct(k=100.0):
    return lambda v: f"{float(v) * k:.0f} %"
def _speed(v):
    return f"{mps(v):,.0f} M/S"
def K(V, action):
    return pw.key_label(V("keys", action)) or "—"
def _kick_k(V):
    try:
        return float(V("flight", "start_speed")) / 18.0
    except (TypeError, ValueError):
        return 1.0
def _help_max(V):
    top, ab = float(V("flight", "max_speed")), float(V("flight", "afterburner_power"))
    return (f"Full throttle: {kmh(top):,.0f} km/h. Afterburner ×{ab:.1f} ≈ {mps(top * ab):,.0f} m/s "
            f"({kmh(top * ab):,.0f} km/h); diving ×{float(V('flight', 'dive_boost')):g}.")
def _help_min(V):
    return (f"The slowest you fly with the throttle just open: {kmh(V('flight', 'min_speed')):,.0f} km/h. "
            "An empty throttle is a hover.")
def _help_reverse(V):
    return f"How fast you back up holding {K(V, 'back')} at a hover ({kmh(V('flight', 'reverse_speed')):,.0f} km/h)."
def _help_burner(V):
    top, ab = float(V("flight", "max_speed")), float(V("flight", "afterburner_power"))
    return f"Top speed with it lit: {mps(top * ab):,.0f} m/s // {kmh(top * ab):,.0f} km/h."
def _help_kick(V):
    k = float(V("boom", "kick_scale")) * _kick_k(V)
    a, b, c = (x * k for x in BOOM_KICKS)
    return f"Speed each blast adds: the first +{a:.0f} m/s, the second +{b:.0f}, the third +{c:.0f} m/s."
def _tiers(V):
    k = float(V("cruise", "top_speed_kms")) / 200.0
    return max(3.0, TIERS_KMS[0] * k), TIERS_KMS[1] * k, TIERS_KMS[2] * k, FAR_KMS * k
def _help_cruise(V):
    t1, t2, t3, far = _tiers(V)
    return f"Tier 1 ≈ {t1:.0f} km/s // tier 2 ≈ {t2:.0f} // tier 3 = {t3:.0f}. Long trips go up to {far:.0f} km/s."
def _info_boom(V):
    return "PRESS CAPS LOCK = 1 BLAST  //  3 PER METER, EACH BIGGER  //  NEEDS OVER A QUARTER THROTTLE"
def _info_cruise(V):
    return f"IN SPACE: PRESS CAPS LOCK FOR STAGE 1  //  HOLD IT FOR 2 AND 3  //  {K(V, 'back')} LOWERS IT"
ACC_FLIGHT, ACC_BURN, ACC_SONIC, ACC_CRUISE, ACC_AMBER, ACC_WHITE = "throttle", "burner", "sonic", "cruise", "amber", "white"
CARDS = [
    Card("FLIGHT", "speed", "speed", ACC_FLIGHT, 0, None),
    Card("FLIGHT", "throttle", "throttle", ACC_FLIGHT, 0, None),
    Card("FLIGHT", "tricks", "take-off, tricks and landing", ACC_FLIGHT, 0, None),
    Card("POWERS", "burner", "afterburner", ACC_BURN, 0, None),
    Card("POWERS", "sonic", "sonic boom", ACC_SONIC, 3, _info_boom),
    Card("POWERS", "cruise", "interplanetary", ACC_CRUISE, 3, _info_cruise),
    Card("SOUND", "master", "master", ACC_WHITE, 0, None),
    Card("SOUND", "suit", "suit sounds", ACC_WHITE, 0, None),
    Card("SOUND", "ip", "interplanetary cruise", ACC_CRUISE, 3, None),
    Card("VISUALS", "preview", "hud preview", ACC_AMBER, 0, None),
    Card("VISUALS", "hud", "hud", ACC_AMBER, 0, None),
    Card("VISUALS", "camera", "speed effects", ACC_WHITE, 0, None),
    Card("VISUALS", "warp", "warp (interplanetary cruise)", ACC_CRUISE, 0, None),
    Card("VISUALS", "aim", "camera", ACC_WHITE, 0, None),
    Card("CONTROLS", "move", "movement keys", ACC_WHITE, 0, None),
    Card("CONTROLS", "suit", "suit keys", ACC_WHITE, 0,
         "FIXED: DOUBLE-TAP SPACE FLIES  //  CAPS LOCK = SONIC BOOM  //  THE MOUSE STEERS  //  G, X AND E STAY THE GAME'S"),
    Card("CONTROLS", "pad", "controller", ACC_WHITE, 0, None),
    Card("CONTROLS", "card", "controls card", ACC_WHITE, 0, None),
]
CURVES = ((1.0, "linear"), (1.6, "balanced"), (2.4, "fine"))
ROWS = [
    Row("FLIGHT", "speed", "flight", "max_speed", "Top speed", _help_max, "slider", (20, 160, 1), _speed),
    Row("FLIGHT", "speed", "flight", "min_speed", "Lowest speed", _help_min, "slider", (1, 40, 1), _speed),
    Row("FLIGHT", "speed", "flight", "reverse_speed", "Reverse speed", _help_reverse, "slider", (5, 60, 1), _speed),
    Row("FLIGHT", "throttle", "flight", "throttle_up_time", "Time to full throttle",
        lambda V: f"How long you hold {K(V, 'forward')} to go from a hover to full throttle.",
        "slider", (0.5, 6.0, 0.1), _secs()),
    Row("FLIGHT", "throttle", "flight", "throttle_down_time", "Time back to hover",
        lambda V: f"Hold {K(V, 'back')} this long to bring full throttle back to a hover. Keep holding it there to "
                  "back up.", "slider", (0.5, 5.0, 0.1), _secs()),
    Row("FLIGHT", "throttle", "flight", "throttle_curve", "Low-speed control",
        "FINE: more precision at low speed. LINEAR: speed spread evenly along the throttle.", "choice", CURVES, None),
    Row("FLIGHT", "throttle", "flight", "hover_move_speed", "Hover moves",
        lambda V: f"How fast {K(V, 'left')} / {K(V, 'right')} sidestep and {K(V, 'climb')} / {K(V, 'descend')} climb and "
                  "drop at a hover (and at low throttle). 5 = as slow as the slowest speed.",
        "slider", (5, 30, 1), _speed),
    Row("FLIGHT", "throttle", "flight", "pilot_flame", "Hover flame size",
        "Your flames at a hover. Across the throttle's first quarter they grow to full size (your lean following the "
        "throttle up to 45 degrees, the hover's hands tilting back).", "slider", (0.1, 1.0, 0.05), _pct()),
    Row("FLIGHT", "tricks", "keys", "double_tap_space", "Double-tap Space to fly",
        lambda V: f"Off: only the fly key ({K(V, 'fly_toggle')}) starts and stops flying.", "toggle", None, None),
    Row("FLIGHT", "tricks", "flight", "double_tap_window", "Double-tap speed",
        lambda V: f"Time allowed between the two taps (Space to fly, {K(V, 'left')} / {K(V, 'right')} to roll). "
                  "Raise it if double-taps get missed.", "slider", (0.15, 0.6, 0.01), _secs(2)),
    Row("FLIGHT", "tricks", "flight", "hard_brake_window", "Hard-brake double-tap speed",
        lambda V: f"Double-tap {K(V, 'back')} within this for a hard brake: two mini booms from your palms.",
        "slider", (0.15, 0.6, 0.01), _secs(2)),
    Row("FLIGHT", "tricks", "flight", "dive_lands", "Super-hero landing",
        "A steep dive straight into the ground lands you in the super-hero pose.", "toggle", None, None),
    Row("FLIGHT", "tricks", "flight", "flip_strafe", "Flip strafe",
        lambda V: f"Swap {K(V, 'left')} and {K(V, 'right')} if sidestepping goes the wrong way.", "toggle", None, None),
    Row("POWERS", "burner", "flight", "afterburner_mode", "Afterburner key",
        lambda V: f"TOGGLE: {K(V, 'afterburner')} switches it on and off. HOLD: it burns only while "
                  f"{K(V, 'afterburner')} is held.", "choice", (("toggle", "toggle"), ("hold", "hold")), None),
    Row("POWERS", "burner", "flight", "climb_fires_afterburner", "Climb key fires it",
        lambda V: f"Holding climb ({K(V, 'climb')}) lights the afterburner for a faster climb.", "toggle", None, None),
    Row("POWERS", "burner", "flight", "afterburner_power", "Thrust", _help_burner, "slider", (1.5, 4.0, 0.1), _times()),
    Row("POWERS", "burner", "flight", "afterburner_time", "Burn time",
        "Seconds of burn on a full charge. Run it dry and it cools down until it is full again.",
        "slider", (3, 60, 1), _secs(0)),
    Row("POWERS", "burner", "flight", "afterburner_recharge", "Recharge time",
        "Seconds to refill from empty. It starts refilling 1 s after it stops burning.", "slider", (3, 60, 1), _secs(0)),
    Row("POWERS", "sonic", "boom", "kick_scale", "Kick strength", _help_kick, "slider", (0.5, 2.0, 0.1), _times()),
    Row("POWERS", "sonic", "boom", "refill_time", "Meter refill",
        "Seconds for the boom meter to refill from empty.", "slider", (4, 60, 1), _secs(0)),
    Row("POWERS", "sonic", "boom", "boost", "Boom thrust",
        "How hard a blast pushes while it carries you: thrust times this at the third blast's peak.",
        "slider", (2.0, 10.0, 0.5), _times()),
    Row("POWERS", "cruise", "cruise", "top_speed_kms", "Top cruise speed", _help_cruise, "slider", (100, 450, 10),
        lambda v: f"{float(v):.0f} KM/S"),
    Row("POWERS", "cruise", "cruise", "tier_fill_time", "Tier fill time",
        "Seconds of holding Caps Lock to fill tiers 2 and 3 (one press fills the first, in step with the charge-up).",
        "slider", (0.5, 3.0, 0.1), _secs()),
    Row("SOUND", "master", "sound", "sound_volume", "Master volume",
        "Every mod sound. It changes when you let go of the slider.", "slider", (0, 1000, 50), _pct(0.1)),
    Row("SOUND", "master", "sound", "cues", "Status beeps",
        "Short beeps: ready, speed limit, a refused take-off. Off: only the suit sounds.", "toggle", None, None),
    Row("SOUND", "suit", "sound", "suit_sounds", "Suit sounds",
        "Power up and down, the afterburner's boom, landings and the hard brake.",
        "toggle", None, None),
    Row("SOUND", "suit", "sound", "boom_sounds", "Sonic booms",
        "The three sonic boom sizes, and the interplanetary cruise's tier booms.", "toggle", None, None),
    Row("SOUND", "ip", "sound", "interplanetary", "Sounds",
        "The charge-up, \"stage 1 confirmed\" and the cruise hum. Off: none of them.", "toggle", None, None),
    Row("SOUND", "ip", "sound", "hum_volume", "Hum volume",
        "How loud the cruise hum sits under everything else.", "slider", (0.0, 1.0, 0.05), _pct()),
    Row("VISUALS", "hud", "hud", "hud", "HUD",
        "The bands under the game's compass, the speed and the space map. Off: none of it (the start-up card "
        "still shows).", "toggle", None, None),
    Row("VISUALS", "hud", "hud", "space_map", "Space map",
        "The sphere map of planets, stations and ships inside the gauge's circle.", "toggle", None, None),
    Row("VISUALS", "hud", "hud", "shock_waves", "Shock waves",
        "The bright ring that races out when you boom, and the hard brake's two small waves.", "toggle", None, None),
    Row("VISUALS", "camera", "camera", "speed_effects", "Speed effects",
        "The camera eases back and the view widens when you go fast. Feeling queasy? Turn it off.",
        "toggle", None, None),
    Row("VISUALS", "camera", "camera", "motion_blur", "Motion blur",
        "A subtle blur at speed. It joins about 30 s after the suit starts.", "toggle", None, None),
    Row("VISUALS", "camera", "camera", "effects_strength", "Effect strength",
        "How far the camera pulls back and how much the view widens.", "slider", (0.0, 1.5, 0.05), _pct()),
    Row("VISUALS", "camera", "camera", "camera_kicks", "Camera kicks",
        "A short camera jolt as the afterburner lights and as booms fire.", "toggle", None, None),
    Row("VISUALS", "warp", "effects", "warp_effects", "Warp effects",
        "The cruise's streaks and tunnel glow.", "toggle", None, None),
    Row("VISUALS", "warp", "effects", "warp_blur", "Warp blur",
        "The heaviest effect: turn it off on slower PCs.", "toggle", None, None),
    Row("VISUALS", "aim", "camera", "recenter_delay", "Camera re-centre delay",
        "Seconds the camera keeps where you aimed it before easing back behind you. The game's own: 0.4 s.",
        "slider", (0.0, 30.0, 0.5), _secs()),
    Row("CONTROLS", "move", "keys", "forward", "Forward", "Opens the throttle; it stays where you leave it.",
        "key", None, None),
    Row("CONTROLS", "move", "keys", "back", "Back and brake",
        "Closes the throttle; at a hover, brakes then backs up. Double-tap: hard brake.", "key", None, None),
    Row("CONTROLS", "move", "keys", "left", "Left", "Sidestep.", "key", None, None),
    Row("CONTROLS", "move", "keys", "right", "Right", "Sidestep.", "key", None, None),
    Row("CONTROLS", "move", "keys", "climb", "Climb", "Hold to rise.", "key", None, None),
    Row("CONTROLS", "move", "keys", "descend", "Descend", "Hold to sink.", "key", None, None),
    Row("CONTROLS", "suit", "keys", "afterburner", "Afterburner", "Toggle or hold: see POWERS.", "key", None, None),
    Row("CONTROLS", "suit", "keys", "fly_toggle", "Fly on / off", "The same as double-tapping Space.",
        "key", None, None),
    Row("CONTROLS", "suit", "keys", "quit", "Power down (hold 1 s)", "Held 1 s, so a stray tap never powers down.",
        "key", None, None),
    Row("CONTROLS", "suit", "keys", "arsenal_toggle", "Weapons",
        "Switches between your starship's weapons and the multi-tool's own while flying.", "key", None, None),
    Row("CONTROLS", "suit", "keys", "arm_toggle", "Take-off safety",
        "Optional: a key that arms or disarms take-off. With SCROLLLOCK the keyboard light shows it.",
        "key", None, None),
    Row("CONTROLS", "suit", "keys", "panel", "Suit Control", "Opens and closes this window in the game.",
        "key", None, None),
    Row("CONTROLS", "pad", "pad", "enabled", "Use a controller",
        "Any Xbox (XInput) pad, plugged in any time. The left stick flies.", "toggle", None, None),
    Row("CONTROLS", "pad", "pad", "stick_deadzone", "Stick dead zone",
        "Raise it if he creeps with the stick let go.", "slider", (0.0, 0.6, 0.01), lambda v: f"{float(v):.2f}"),
    Row("CONTROLS", "pad", "pad", "rumble", "Rumble",
        "Short rumbles: take-off, landing, afterburner.", "toggle", None, None),
    Row("CONTROLS", "pad", "pad", "rumble_strength", "Rumble strength", "How strong the rumbles are.",
        "slider", (0.0, 0.95, 0.05), _pct()),
]
PAGE_ORDER = ("FLIGHT", "POWERS", "SOUND", "VISUALS", "CONTROLS")
RAIL_ACCENT = {"FLIGHT": "throttle", "POWERS": ["burner", "sonic", "cruise"], "SOUND": None, "VISUALS": "amber",
               "CONTROLS": None}
INTRO = {
    "FLIGHT": "How he flies. Changes apply at once while the suit runs, even in mid-air.",
    "POWERS": "The afterburner, the sonic boom and the interplanetary cruise.",
    "SOUND": "PLAY tries a sound here, at your volume, with or without the game.",
    "VISUALS": "The HUD and the camera's speed effects.",
    "CONTROLS": "Click a key, then press the new one: Esc cancels, Del clears. Mouse buttons 3, 4 and 5 work too.",
}
_FX_ON = (("camera", "speed_effects"), True, "Speed effects are off")
_PAD_ON = (("pad", "enabled"), True, "The controller is off")
NEEDS = {
    ("camera", "motion_blur"): [_FX_ON], ("camera", "effects_strength"): [_FX_ON], ("camera", "camera_kicks"): [_FX_ON],
    ("effects", "warp_blur"): [(("effects", "warp_effects"), True, "Warp effects are off")],
    ("hud", "space_map"): [(("hud", "hud"), True, "The HUD is off")],
    ("sound", "hum_volume"): [(("sound", "interplanetary"), True, "The interplanetary sounds are off")],
    ("pad", "stick_deadzone"): [_PAD_ON], ("pad", "rumble"): [_PAD_ON],
    ("pad", "rumble_strength"): [_PAD_ON, (("pad", "rumble"), True, "Rumble is off")],
}
PAIR = {("flight", "max_speed"): ("flight", "min_speed"), ("flight", "min_speed"): ("flight", "max_speed")}
PREVIEWS = {
    ("sound", "sound_volume"): lambda V: ["flight_on"],
    ("sound", "cues"): lambda V: ["ready", "speed_up", "speed_limit"],
    ("sound", "suit_sounds"): lambda V: ["flight_on", "afterburner_on"],
    ("sound", "boom_sounds"): lambda V: ["sonic_blast_3" if (SOUND_DIR / "sonic_blast_3.wav").exists()
                                         else "sonic_boom_mid"],
    ("sound", "interplanetary"): lambda V: ["tracks/ip_charge", "ip_stage1"] if V("sound", "interplanetary") else [],
    ("sound", "hum_volume"): lambda V: ["tracks/ip_hum"],
}
HUM_PREVIEW_S = 6.0
DEMO_MAP = [(2, 2.6, 0.9, -1.8), (4, -2.4, 0.4, -1.2), (3, 1.5, -0.2, 2.2), (1, 0.9, 0.1, -0.7), (1, -1.3, 0.0, 1.1),
            (2, -3.2, -0.6, -3.0)]
LABEL_W, SLIDER_W, KEY_W, TICK_W, HELP_W = 206, 400, 132, 96, 700
def row_keys(page):
    return [(r.sec, r.key) for r in ROWS if r.page == page]
def pill_for(sec, key):
    cls = control.apply_class(sec, key) if control is not None else "live"
    return {"restart": "↻ after restart", "launcher": "next game start"}.get(cls)
LABELS = {r.key: r.label for r in ROWS if r.kind == "key"}
KEY_ROWS = tuple(r.key for r in ROWS if r.kind == "key")
HIDDEN_KEYS = ("faster", "slower")
LABELS.update(faster="Speed step up (settings.ini)", slower="Speed step down (settings.ini)")
KEYMAP_ACTIONS = ("forward", "back", "left", "right", "climb", "descend", "afterburner", "fly_toggle",
                  "faster", "slower", "quit")
NAV_KEYS = {0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc", 0x25: "Left", 0x26: "Up", 0x27: "Right",
            0x28: "Down", 0x2E: "Delete"}
RESERVED = {"SPACE": "Space is the suit's take-off key (double-tap) and holds its jetpack pose",
            "CAPSLOCK": "Caps Lock is the sonic boom"}
GAME_KEYS = {"R": "reload / recharge", "F": "the Analysis Visor", "G": "your weapon", "X": "the quick menu",
             "E": "interact"}
_GENERIC = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11, 0xA4: 0x12, 0xA5: 0x12}
_NO_HOTKEY = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12, 0x14, 0x20, 0x5B, 0x5C}
def _vk(name):
    code = settings.key_code(name)
    return _GENERIC.get(code, code) if code else code
def _hotkey_ok(code):
    try:
        import panel_proc
        return panel_proc.hotkey_ok(code)
    except Exception:
        return bool(code) and code not in _NO_HOTKEY
def key_check(action, name, binds):
    lab = LABELS.get(action, action)
    code = _vk(name)
    if code is None:
        return "block", f"{name} isn't a key the suit knows", None
    if code == 0:
        if action in settings.MOVE_KEYS:
            return "block", f"{lab} needs a key", None
        return None, None, None
    kl = pw.key_label(settings.key_name(code))
    for n, why in RESERVED.items():
        if code == _vk(n):
            return "block", why, None
    if action != "panel" and code == _vk(binds.get("panel", "none")):
        return "block", f"{kl} opens Suit Control", "panel"
    for other, oname in binds.items():
        if other != action and (other in KEY_ROWS or other in HIDDEN_KEYS) and _vk(oname) == code:
            return "block", f"{kl} is already {LABELS.get(other, other)}", other
    for other in KEYMAP_ACTIONS:
        d = settings.DEFAULTS["keys"][other]
        if other != action and _vk(d) == code and _vk(binds.get(other, d)) != code:
            now = pw.key_label(binds.get(other, d))
            return "block", f"{kl} stays reserved for {LABELS.get(other, other)} (now on {now})", other
    if action == "panel" and code in NAV_KEYS:
        return "block", (f"Suit Control's key can't be {NAV_KEYS[code]}: this window needs Tab, Enter, Esc, "
                         "Backspace, Delete and the arrows for its own controls"), None
    if action == "panel" and not _hotkey_ok(code):
        return "block", "Suit Control's key can't be a mouse button, Shift, Ctrl, Alt, Caps Lock or Space", None
    kn = settings.key_name(code)
    if kn in GAME_KEYS and _vk(settings.DEFAULTS["keys"].get(action, "none")) != code:
        return "warn", f"The game also uses {kn} ({GAME_KEYS[kn]})", None
    return None, None, None
def check_all(binds):
    return {a: key_check(a, binds.get(a, "none"), binds) for a in KEY_ROWS}
def controls_lines(V, pad=None):
    k = lambda a: K(V, a)
    fly = f"double-tap SPACE or {k('fly_toggle')}" if V("keys", "double_tap_space") else k("fly_toggle")
    out = [("Fly on / off", fly),
           ("Throttle", f"{k('forward')} opens it, {k('back')} closes it; it stays where you leave it"),
           ("Brake, reverse", f"{k('back')} at a hover: palms out, then back up"),
           ("Hard brake", f"double-tap {k('back')}"),
           ("Sidestep", f"{k('left')} / {k('right')}")]
    out += [("Climb / descend", f"{k('climb')} / {k('descend')}"),
            ("Afterburner", f"{k('afterburner')} ({'tap on / off' if V('flight', 'afterburner_mode') == 'toggle' else 'hold'})"),
            ("Sonic boom", "CAPS LOCK: each press = 1 blast (3, each bigger; over a quarter throttle)"),
            ("Interplanetary", f"in space, press CAPS LOCK for stage 1, hold it for 2 and 3; {k('back')} lowers it"),
            ("Steer", "the mouse"),
            ("Dive", f"aim straight down + {k('forward')}" + (" (lands you)" if V("flight", "dive_lands") else "")),
            ("Weapons", k("arsenal_toggle"))]
    if _vk(V("keys", "arm_toggle")):
        out.append(("Take-off safety", k("arm_toggle")))
    out += [("Power down", f"hold {k('quit')} 1 s"), ("Suit Control", k("panel"))]
    if pad and pad.get("enabled"):
        n = lambda a: "+".join(pad.get(a) or ()) or "-"
        brake = (f"{n('hard_brake')} or the stick back twice" if pad.get("hard_brake")
                 else "the stick back twice")
        ab_ = (f"{n('afterburner')} or the stick up twice" if pad.get("afterburner") else "the stick up twice")
        out.append(("Controller", f"double-tap {n('fly_toggle')} fly // {n('climb')} / {n('descend')} up / down // "
                                  f"{n('roll_left')} / {n('roll_right')} roll (a sidestep at a hover) // "
                                  f"{ab_} afterburner // {n('sonic_boom')} boom, in space the cruise // "
                                  f"{brake} hard brake // hold {n('quit')} power "
                                  "down // flying, the game ignores those buttons; on foot they're the game's"))
    return out
def controls_text(V, pad=None):
    lines = controls_lines(V, pad)
    w = max(len(a) for a, _ in lines) + 3
    body = "\n".join(f"{a} {'.' * (w - len(a))} {b}" for a, b in lines)
    return f"FLY LIKE IRON MAN // CONTROLS\n{body}\n\nFly Like Iron Man by DooDooDevan\n"
def _wav_secs(path):
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / float(f.getframerate())
    except Exception:
        return 1.0
def _trimmed(path, secs, gain):
    g = max(0, min(1000, int(round(gain * 1000))))
    out = Path(tempfile.gettempdir()) / "ironman_flight_sounds" / f"{path.stem}_preview{int(secs)}_v{g}.wav"
    try:
        if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
            return out
        import numpy as np
        with wave.open(str(path), "rb") as f:
            p = f.getparams()
            data = f.readframes(int(secs * p.framerate))
        if p.sampwidth != 2:
            return path
        x = np.frombuffer(data, dtype=np.int16).astype(np.float32).reshape(-1, p.nchannels) * (g / 1000.0)
        n = min(len(x), int(0.4 * p.framerate))
        if n:
            x[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)[:, None]
        out.parent.mkdir(exist_ok=True)
        with wave.open(str(out), "wb") as f:
            f.setparams(p)
            f.writeframes(x.astype(np.int16).tobytes())
        return out
    except Exception:
        return path
def prepare_preview(names, volume, hum=None):
    import audio
    vol = max(0, min(1000, int(round(float(volume) / 50.0)) * 50))
    out = []
    for n in names:
        p = SOUND_DIR / f"{n}.wav"
        if not p.exists():
            continue
        if hum is not None and p.stem == "ip_hum":
            q = _trimmed(p, HUM_PREVIEW_S, vol / 1000.0 * float(hum))
        else:
            q = audio._scaled(p, vol)
        out.append((q, min(_wav_secs(q), HUM_PREVIEW_S + 1.0)))
    return out
class _Player:
    def __init__(self):
        self.owner = None
        self.gen = 0
        self._after = None
        self._playing = False
    def play(self, owner, names, volume, hum=None):
        self.stop()
        self.gen += 1
        gen, got = self.gen, []
        self.owner = owner
        owner.set_playing(True)
        def work():
            try:
                got.append(prepare_preview(names, volume, hum))
            except Exception:
                got.append([])
        threading.Thread(target=work, daemon=True, name="sound-preview").start()
        def wait():
            if gen != self.gen:
                return
            if not got:
                self._later(owner, 30, wait)
                return
            self._next(owner, got[0], 0, gen)
        self._later(owner, 30, wait)
    def _later(self, owner, ms, fn):
        try:
            self._after = (owner, owner.after(ms, fn))
        except tk.TclError:
            self._after = None
    def _next(self, owner, files, i, gen):
        if gen != self.gen:
            return
        if i >= len(files):
            self.stop()
            return
        path, secs = files[i]
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self._playing = True
        except Exception:
            pass
        self._later(owner, int(secs * 1000) + 60, lambda: self._next(owner, files, i + 1, gen))
    def stop(self):
        self.gen += 1
        if self._after:
            w, aid = self._after
            try:
                w.after_cancel(aid)
            except tk.TclError:
                pass
            self._after = None
        if self._playing:
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass
            self._playing = False
        if self.owner is not None:
            try:
                self.owner.set_playing(False)
            except tk.TclError:
                pass
            self.owner = None
PLAYER = _Player()
class PlayButton(pw.Button):
    def __init__(self, parent, command, tip=None, bg=None):
        self.playing = False
        super().__init__(parent, "play", command=command, width=pw.px(84), height=pw.px(30), tip=tip, bg=bg)
    def set_playing(self, flag):
        self.playing = bool(flag)
        self.label = "stop" if flag else "play"
        self.redraw()
    def _draw(self, w, h):
        lab, self.label = self.label, ""
        try:
            super()._draw(w, h)
        finally:
            self.label = lab
        x0, y0, x1, y1 = self._body(w, h)
        col = pw.TEXT_OFF if self._disabled else (pw.ACCENTS["throttle"][1] if self.playing else pw.TEXT)
        f = pw.font("value")
        t = pw.spaced(lab)
        s = pw.px(10)
        gap = pw.px(8)
        gx = (x0 + x1 - (s + gap + f.measure(t))) // 2
        cy = (y0 + y1) // 2 + (pw.px(1) if self._pressed else 0)
        if self.playing:
            self.rect(gx, cy - s // 2, gx + s, cy + s // 2, col)
        else:
            self.create_polygon(gx, cy - s // 2 - 1, gx + s, cy, gx, cy + s // 2 + 1, fill=col, outline="")
        self.text(gx + s + gap, cy, t, f, col)
class _RowUI:
    __slots__ = ("row", "frame", "label", "help", "widget", "extra", "pill", "tick", "play", "dis")
    def __init__(self, row):
        self.row = row
        self.frame = self.label = self.help = self.widget = self.extra = None
        self.pill = self.tick = self.play = None
        self.dis = None
class Page:
    def __init__(self, name, page, ctx):
        self.name, self.sp, self.ctx = name, page, ctx
        self.body = page.body
        self.rows = {}
        self.cards = {}
        self.strips = {}
        self.live = {}
        self.sent = {}
        self.keys = set(row_keys(name))
        self._suit = None
        self._dyn = []
        self._timers = []
        self._preview_img = None
        self._pad_t = 0.0
        self._pad_job = None
        self._pad_seen = None
        self.keycaps = {}
        self.card_lines = None
        self._build()
        self.reload(animate=False)
    def get(self, sec, key):
        v = None
        try:
            v = self.ctx.get(sec, key)
        except Exception:
            v = None
        if sec == "pad":
            return _pad_value(key, v)
        if v is None:
            v = _default(sec, key)
        if sec == "keys" and key in settings.KEY_SETTINGS:
            return settings.key_name(v) if isinstance(v, int) and not isinstance(v, bool) else str(v).upper()
        return v
    def V(self, sec, key):
        if (sec, key) in self.live:
            return self.live[(sec, key)]
        return self.get(sec, key)
    def binds(self):
        return {a: self.V("keys", a) for a in settings.KEY_SETTINGS}
    def _build(self):
        bg = pw.BG
        intro = pw.label(self.body, INTRO.get(self.name, ""), "help", bg=bg, wrap=pw.px(760))
        intro.pack(anchor="w", pady=(0, pw.px(8)))
        for c in CARDS:
            if c.page != self.name:
                continue
            card = pw.Card(self.body, c.title, accent=c.accent if c.accent != ACC_WHITE else None,
                           sections=c.sections)
            card.pack(fill="x", pady=(0, pw.px(12)))
            self.cards[c.id] = card
            strip = pw.InlineStrip(card.body, "error", width=pw.px(560))
            strip.pack(fill="x")
            self.strips[c.id] = strip
            if (self.name, c.id) == ("VISUALS", "preview"):
                self._card_preview(card)
                continue
            if (self.name, c.id) == ("CONTROLS", "card"):
                self._card_card(card)
                continue
            for r in ROWS:
                if r.page == self.name and r.card == c.id:
                    self._make_row(card.body, r, c.accent)
            if c.info:
                lab = pw.label(card.body, "", "badge", colour=pw.TEXT_DIM, bg=pw.CARD)
                lab.pack(anchor="w", pady=(pw.px(6), 0))
                self._dyn.append((lab, c.info if callable(c.info) else (lambda V, t=c.info: t)))
            extra = getattr(self, f"_extra_{c.id}", None) if self.name == "CONTROLS" else None
            if extra:
                extra(card)
        for card in self.cards.values():
            card.body.bind("<Configure>", lambda e, b=card.body: self._wrap(b, e.width), add="+")
    def _wrap(self, body, width):
        for ui in self.rows.values():
            if ui.help is not None and ui.frame is not None and ui.frame.master is body:
                room = width - pw.px(TICK_W + 24) - (pw.px(LABEL_W + KEY_W + 40) if ui.row.kind == "key" else 0)
                ui.help.configure(wraplength=max(pw.px(160), room))
    def _make_row(self, parent, r, accent):
        ui = _RowUI(r)
        sec, key = r.sec, r.key
        f = tk.Frame(parent, bg=pw.CARD, highlightthickness=0, bd=0)
        f.pack(fill="x", pady=(pw.px(3), pw.px(5)))
        f.columnconfigure(0, minsize=pw.px(LABEL_W))
        f.columnconfigure(2, weight=1)
        ui.frame = f
        ui.label = pw.label(f, r.label, "label", bg=pw.CARD)
        ui.label.grid(row=0, column=0, sticky="w")
        acc = accent if accent not in (None, ACC_WHITE) else "white"
        dflt = _default(sec, key)
        tip = lambda ui=ui: self._tip(ui)
        if r.kind == "slider":
            lo, hi, step = r.spec
            big = 10 if isinstance(step, int) else round(step * 10, 6)
            w = pw.Slider(f, lo, hi, dflt, step, default=dflt, fmt=r.fmt, accent=acc, width=pw.px(SLIDER_W),
                          readout=pw.px(112), big_step=big, tip=tip, bg=pw.CARD)
            w.on_live(lambda v, ui=ui: self._on_live(ui, v))
        elif r.kind == "toggle":
            w = pw.Toggle(f, bool(dflt), default=bool(dflt), accent=acc if acc != "white" else "throttle", tip=tip,
                          bg=pw.CARD)
        elif r.kind == "choice":
            w = pw.Segmented(f, list(r.spec), dflt, default=dflt, accent=acc, tip=tip, bg=pw.CARD)
        elif r.kind == "key":
            w = pw.KeyCap(f, dflt, default=dflt, width=pw.px(KEY_W), tip=tip, bg=pw.CARD)
            self.keycaps[key] = w
        else:
            raise ValueError(f"row kind {r.kind!r}")
        w.grid(row=0, column=1, sticky="w", padx=(pw.px(8), 0))
        w.on_change(lambda v, ui=ui: self._on_commit(ui, v))
        ui.widget = w
        side = tk.Frame(f, bg=pw.CARD, highlightthickness=0, bd=0)
        side.grid(row=0, column=3, sticky="e", padx=(pw.px(8), 0))
        ui.extra = side
        if (sec, key) in PREVIEWS:
            ui.play = PlayButton(side, lambda ui=ui: self._play(ui), bg=pw.CARD,
                                 tip="Plays it here, at your volume")
            ui.play.pack(side="right")
        p = pill_for(sec, key)
        if p:
            ui.pill = pw.Chip(side, p, small=True, colour=pw.AMBER, bg=pw.CARD,
                              tip="This one counts after the suit restarts (HOME: RESTART SUIT)")
            ui.pill.pack(side="right", padx=(0, pw.px(8)))
        ui.tick = pw.Chip(f if r.kind != "key" else side, "applied ✓", small=True, colour=pw.GREEN,
                          width=pw.px(TICK_W), bg=pw.CARD)
        ui.tick._fade = 0.0
        if r.kind == "key":
            ui.tick.pack(side="right", padx=(0, pw.px(6)))
            ui.help = pw.label(f, "", "help", bg=pw.CARD, wrap=pw.px(HELP_W - LABEL_W - KEY_W - TICK_W))
            ui.help.grid(row=0, column=2, sticky="w", padx=(pw.px(14), 0))
        else:
            ui.tick.grid(row=1, column=3, sticky="e", padx=(pw.px(8), 0))
            ui.help = pw.label(f, "", "help", bg=pw.CARD, wrap=pw.px(HELP_W))
            ui.help.grid(row=1, column=0, columnspan=3, sticky="w", pady=(pw.px(1), 0))
        self._dyn.append((ui.help, r.help if callable(r.help) else (lambda V, t=r.help: t)))
        self.rows[(sec, key)] = ui
        return ui
    def _tip(self, ui):
        r = ui.row
        lines = []
        w = ui.widget
        if getattr(w, "custom", False):
            v = self.get(r.sec, r.key)
            if r.kind == "slider":
                lines.append(f"Your settings.ini says {_num(v)}: outside this slider's {_num(r.spec[0])} to "
                             f"{_num(r.spec[1])}. It stays as it is until you move the slider.")
            else:
                lines.append(f"Your settings.ini says {_num(v)}: not one of these. It stays until you pick one.")
        if r.key in ("max_speed", "min_speed", "reverse_speed") and r.sec == "flight":
            lines.append(f"Speed level {_num(self.V(r.sec, r.key))}: the suit cruises at 2.78 × the level in m/s.")
        d = _default(r.sec, r.key)
        dt = ("yes" if d else "no") if isinstance(d, bool) else (pw.key_label(d) if r.kind == "key" else _num(d))
        lines.append(f"settings.ini [{r.sec}] {r.key} // default {dt} // double-click resets")
        return "\n".join(lines)
    def _card_preview(self, card):
        b = card.body
        self._pv = tk.Canvas(b, bg=pw.CARD, highlightthickness=0, bd=0, height=pw.px(236), width=pw.px(720))
        self._pv.pack(anchor="w", fill="x")
        self._pv_key = None
    def _draw_preview(self):
        if getattr(self, "_pv", None) is None:
            return
        style, smap = ("gauge" if self.V("hud", "hud") else "off"), bool(self.V("hud", "space_map"))
        key = (style, smap)
        if key == self._pv_key:
            return
        self._pv_key = key
        cv = self._pv
        cv.delete("all")
        H = pw.px(236)
        legend_x = pw.px(560)
        try:
            from PIL import Image, ImageTk
            import hud
            st = dict(hud.idle_state(), fuel=0.72, charge=0.75, throttle=0.62, cruise=0.34)
            now = time.perf_counter()
            img = None
            if style == "gauge":
                g = hud.Gauge(0.62 * pw.SCALE)
                for i in range(24):
                    img = g.draw(1.0, st, now + i * 0.1, DEMO_MAP if smap else None)
            if img is not None:
                back = Image.new("RGBA", img.size, _rgb(pw.CARD) + (255,))
                img = Image.alpha_composite(back, img).convert("RGB")
                self._preview_img = ImageTk.PhotoImage(img, master=cv)
                cv.create_image(0, H // 2, image=self._preview_img, anchor="w")
                legend_x = img.size[0] + pw.px(28)
        except Exception as e:
            self._preview_img = None
            cv.create_text(0, H // 2, anchor="w", text=pw.spaced("preview unavailable"), font=pw.font("badge"),
                           fill=pw.TEXT_DIM)
            print(f"panel_pages: HUD preview: {e}", file=sys.stderr)
        if style == "off":
            cv.create_text(0, H // 2 - pw.px(12), anchor="w", text=pw.spaced("hud off"), font=pw.font("head"),
                           fill=pw.TEXT_DIM)
            cv.create_text(0, H // 2 + pw.px(16), anchor="w", font=pw.font("help"), fill=pw.TEXT_DIM,
                           text="The start-up card still shows.")
            return
        bands = [("throttle", "throttle"), ("afterburner", "burner"), ("sonic boom", "sonic"),
                 ("interplanetary", "cruise")]
        y = H // 2 - len(bands) * pw.px(15)
        for name, acc in bands:
            e, m = pw.ACCENTS[acc]
            cv.create_rectangle(legend_x, y - pw.px(4), legend_x + pw.px(26), y + pw.px(4), fill=m, outline=pw.LINE,
                                width=pw.px(2))
            cv.create_text(legend_x + pw.px(38), y, anchor="w", text=pw.spaced(name), font=pw.font("badge"),
                           fill=pw.TEXT)
            y += pw.px(30)
        cv.create_text(legend_x, y + pw.px(2), anchor="w", font=pw.font("help"), fill=pw.TEXT_DIM,
                       text="In the circle: the space map." if smap else "The space map is off.")
    def _extra_move(self, card):
        row = tk.Frame(card.body, bg=pw.CARD)
        row.pack(anchor="w", pady=(pw.px(8), 0))
        pw.Button(row, "azerty", command=self._azerty,
                  tip="Forward Z, left Q (back S and right D stay)").pack(side="left", padx=(0, pw.px(8)))
        pw.Button(row, "mouse 5 / 4: climb / descend", command=self._mouse_sides,
                  tip="Climb on mouse button 5, descend on mouse button 4: R and F stay free for the game"
                  ).pack(side="left", padx=(0, pw.px(8)))
        pw.Button(row, "reset keyboard", kind="ghost", command=self._reset_keys,
                  tip="Every key back to the default").pack(side="left")
    def _extra_pad(self, card):
        self._pad_light = pw.Light(card.body, "controller", "off", "Looking for a controller…", width=pw.px(520),
                                   bg=pw.CARD)
        first = self.rows.get(("pad", "enabled"))
        self._pad_light.pack(anchor="w", pady=(0, pw.px(6)), before=first.frame if first else None)
    def _card_card(self, card):
        card.header(pw.Button(card, "copy", command=self._copy_card, bg=pw.CARD,
                              tip="Copies this card as text (to paste in a chat or a note)"))
        self.card_grid = tk.Frame(card.body, bg=pw.CARD)
        self.card_grid.pack(anchor="w", fill="x")
        self.card_lines = None
    def _fill_card(self):
        if getattr(self, "card_grid", None) is None:
            return
        lines = controls_lines(self.V, _pad_cfg(self.V))
        if lines == self.card_lines:
            return
        self.card_lines = lines
        for w in self.card_grid.winfo_children():
            w.destroy()
        half = (len(lines) + 1) // 2
        for i, (a, b) in enumerate(lines):
            col, r = (0, i) if i < half else (2, i - half)
            if a == "Controller":
                col, r = 0, half + 1
            pw.label(self.card_grid, pw.spaced(a), "badge", colour=pw.TEXT_DIM, bg=pw.CARD).grid(
                row=r, column=col, sticky="nw", pady=pw.px(3), padx=(0, pw.px(10)))
            wrap = pw.px(640) if a == "Controller" else pw.px(250)
            pw.label(self.card_grid, b, "label", bg=pw.CARD, wrap=wrap).grid(
                row=r, column=col + 1, columnspan=3 if a == "Controller" else 1, sticky="nw", pady=pw.px(3),
                padx=(0, pw.px(24)))
    def _copy_card(self):
        text = controls_text(self.V, _pad_cfg(self.V))
        try:
            root = self.body.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(text)
            self._toast("Controls card copied", "ok")
        except tk.TclError as e:
            self._toast(f"Couldn't copy: {e}", "error")
    def _on_live(self, ui, v):
        r = ui.row
        self.live[(r.sec, r.key)] = v
        if (r.sec, r.key) in PAIR:
            p, pv = self._pair(r.key, v)
            if p is not None:
                self.live[p] = pv
                self.rows[p].widget.set(pv, animate=False)
        self._update_dyn()
    def _base(self, k):
        return self.sent[k] if k in self.sent else self.get(*k)
    def _pair(self, which, v):
        p = PAIR[("flight", which)]
        ui = self.rows.get(p)
        if ui is None:
            return None, None
        v, base = float(v), self._base(p)
        lo, hi = ui.row.spec[0], ui.row.spec[1]
        if which == "max_speed":
            return p, (base if float(base) < v else max(lo, int(math.ceil(v)) - 1))
        return p, (base if float(base) > v else min(hi, int(math.floor(v)) + 1))
    def _on_commit(self, ui, v):
        r = ui.row
        sec, key = r.sec, r.key
        if r.kind == "key":
            self._commit_key(ui, v)
            return
        self.live[(sec, key)] = v
        changes = {(sec, key): v}
        if (sec, key) in PAIR:
            p, pv = self._pair(key, v)
            if p is not None and not _same(pv, self._base(p)):
                changes[p] = pv
        self._send(changes)
        self._after_change()
    def _commit_key(self, ui, name):
        action = ui.row.key
        old = self.V("keys", action)
        name = str(name or "none").upper()
        if name in ("", "NONE"):
            name = "none"
        binds = self.binds()
        state, note, other = key_check(action, name, binds)
        if state == "block":
            ui.widget.set(old)
            ui.widget.set_state("block", note)
            self._later(2600, self._update_keys)
            actions = []
            swap = self._swap_for(action, name, other, old, binds)
            if swap:
                actions.append((f"swap with {LABELS.get(other, other)}", lambda s=swap: self._send_keys(s)))
            self._strip(ui.row.card, f"{note}: pick another key." if not actions else f"{note}.", actions)
            return
        self._send({("keys", action): name})
        self._after_change()
    def _swap_for(self, action, name, other, old, binds):
        if not other or other not in KEY_ROWS or other == "panel" or _vk(name) != _vk(binds.get(other)):
            return None
        trial = dict(binds)
        trial[action], trial[other] = name, old
        if any(s[0] == "block" for s in check_all(trial).values()):
            return None
        return {action: name, other: old}
    def _send_keys(self, binds_changes):
        self._send({("keys", a): v for a, v in binds_changes.items()})
        self._after_change()
        self._hide_strips()
    def _quick(self, changes, what):
        trial = self.binds()
        trial.update(changes)
        bad = [(a, s) for a, s in check_all(trial).items() if s[0] == "block"]
        if bad:
            a, s = bad[0]
            self._strip("move", f"{what}: {s[1]}. Change {LABELS.get(a, a)} first.")
            return
        self._send_keys(changes)
        self._toast(f"{what} keys set", "ok")
    def _azerty(self):
        self._quick({"forward": "Z", "left": "Q", "back": "S", "right": "D"}, "AZERTY")
    def _mouse_sides(self):
        self._quick({"climb": "MOUSE5", "descend": "MOUSE4"}, "Mouse side button")
    def _reset_keys(self):
        self._send_keys({a: settings.DEFAULTS["keys"][a] for a in settings.KEY_SETTINGS})
        self._toast("Keyboard back to the defaults", "ok")
    def _send(self, changes):
        for (sec, key), v in changes.items():
            self.live[(sec, key)] = self.sent[(sec, key)] = v
            ui = self.rows.get((sec, key))
            if ui is not None and not _same(ui.widget.get(), v):
                ui.widget.set(v)
        try:
            if len(changes) > 1 and hasattr(self.ctx, "set_many"):
                self.ctx.set_many(dict(changes))
            else:
                for (sec, key), v in changes.items():
                    self.ctx.set(sec, key, v)
        except Exception as e:
            self._toast(f"Couldn't save: {e}", "error")
    def _after_change(self):
        self._update_dyn()
        self._update_needs()
        self._update_keys()
        self._draw_preview()
        self._fill_card()
    def reload(self, animate=True):
        self.live.clear()
        self.sent.clear()
        for (sec, key), ui in self.rows.items():
            v = self.get(sec, key)
            if ui.row.kind == "toggle":
                v = bool(v)
            if not _same(ui.widget.get(), v) or getattr(ui.widget, "custom", False):
                ui.widget.set(v, animate=animate)
        self._after_change()
    def saved(self, keys, ok, text=""):
        mine = [k for k in (keys or ()) if k in self.rows]
        if not mine:
            return
        if ok:
            word = str(text or "applied").lower()
            colour = pw.AMBER if "restart" in word else (pw.GREEN if word.startswith("applied") else pw.TEXT_DIM)
            label = {"applied": "applied ✓", "saved": "saved"}.get(word, word)
            for k in mine:
                ui = self.rows[k]
                ui.tick.colour = colour
                ui.tick.flash(label, hold=1.4, fade=0.6)
            return
        ui = self.rows[mine[0]]
        self._strip(ui.row.card, str(text or "Couldn't save that"), kind="error")
        self.reload()
    def refresh(self, status):
        suit = None
        try:
            suit = self.ctx.suit()
        except Exception:
            suit = "online" if status else "offline"
        if suit != self._suit:
            self._suit = suit
            for (sec, key), ui in self.rows.items():
                if ui.pill is not None:
                    want = suit not in ("offline", None)
                    if want and not ui.pill.winfo_manager():
                        ui.pill.pack(side="right", padx=(0, pw.px(8)), before=ui.tick)
                    elif not want and ui.pill.winfo_manager():
                        ui.pill.pack_forget()
        if self.name == "CONTROLS":
            self._poll_pad()
    def on_show(self):
        self._after_change()
    def on_hide(self):
        if PLAYER.owner is not None and any(ui.play is PLAYER.owner for ui in self.rows.values()):
            PLAYER.stop()
        for kc in self.keycaps.values():
            kc.cancel()
    def _update_dyn(self):
        for lab, fn in self._dyn:
            try:
                t = fn(self.V)
            except Exception:
                t = ""
            if lab.cget("text") != t:
                lab.configure(text=t)
    def _update_needs(self):
        for (sec, key), conds in NEEDS.items():
            ui = self.rows.get((sec, key))
            if ui is None:
                continue
            why = None
            for need, want, because in conds:
                have = self.V(*need)
                if not (want(have) if callable(want) else _same(have, want)):
                    why = because
                    break
            if ui.dis == why:
                continue
            ui.dis = why
            ui.widget.set_disabled(why is not None, why)
            ui.label.configure(fg=pw.TEXT_OFF if why else pw.TEXT)
            if ui.play is not None:
                ui.play.set_disabled(why is not None, why)
        ui = self.rows.get(("sound", "interplanetary"))
        if ui is not None and ui.play is not None:
            off = not self.V("sound", "interplanetary")
            if ui.play.disabled != off:
                ui.play.set_disabled(off, "Off: no interplanetary sounds")
    def _update_keys(self):
        if not self.keycaps:
            return
        states = check_all(self.binds())
        for a, kc in self.keycaps.items():
            st, note, _ = states.get(a, (None, None, None))
            if (kc._state, kc._note) != (st, note):
                kc.set_state(st, note)
        ui_help = {a: self.rows[("keys", a)].help for a in self.keycaps}
        for a, lab in ui_help.items():
            st, note, _ = states.get(a, (None, None, None))
            r = self.rows[("keys", a)].row
            t = note if st else r.help
            col = pw.RED if st == "block" else (pw.AMBER if st == "warn" else pw.TEXT_DIM)
            if lab.cget("text") != t or lab.cget("fg") != col:
                lab.configure(text=t, fg=col)
    def _poll_pad(self):
        light = getattr(self, "_pad_light", None)
        if light is None:
            return
        if self._pad_job is not None and self._pad_job[0]:
            slots = self._pad_job[0][0]
            self._pad_job = None
            seen = tuple(sorted(slots)) if slots is not None else None
            if seen != self._pad_seen:
                self._pad_seen = seen
                if seen is None:
                    light.set("off", "controller", "Controller support isn't available here")
                elif seen:
                    light.set("ok", "controller connected", "Slot " + ", ".join(str(i + 1) for i in seen))
                else:
                    light.set("off", "no controller", "Plug one in any time: it's picked up by itself")
        now = time.perf_counter()
        if self._pad_job is None and now - self._pad_t > 2.0:
            self._pad_t = now
            box = []
            def work():
                try:
                    import xpad
                    box.append(xpad.slots())
                except Exception:
                    box.append(None)
            self._pad_job = (box,)
            threading.Thread(target=work, daemon=True, name="pad-slots").start()
    def _play(self, ui):
        if PLAYER.owner is ui.play:
            PLAYER.stop()
            return
        names = PREVIEWS[(ui.row.sec, ui.row.key)](self.V)
        if not names:
            return
        vol = self.V("sound", "sound_volume")
        hum = self.V("sound", "hum_volume") if ui.row.key == "hum_volume" else None
        PLAYER.play(ui.play, names, vol, hum)
    def _strip(self, card_id, text, actions=(), kind="error"):
        s = self.strips.get(card_id)
        if s is None:
            self._toast(text, kind)
            return
        s.show(text, kind=kind, actions=list(actions), timeout=8.0)
        try:
            self.sp.see(s)
        except Exception:
            pass
    def _hide_strips(self):
        for s in self.strips.values():
            if s.shown:
                s.hide()
    def _toast(self, text, kind="ok"):
        try:
            self.ctx.toast(text, kind)
        except Exception:
            pass
    def _later(self, ms, fn):
        try:
            self._timers.append(self.body.after(ms, fn))
        except tk.TclError:
            pass
        if len(self._timers) > 32:
            del self._timers[:16]
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def _num(v):
    try:
        f = float(v)
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(v)
def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b) and type(a) is type(b)
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return str(a).upper() == str(b).upper()
def _default(sec, key):
    if sec == "pad":
        return _pad_value(key, None)
    d = settings.DEFAULTS[sec][key]
    if isinstance(d, str) and d.lower() in settings.TRUE + settings.FALSE and not (
            sec == "keys" and key in settings.KEY_SETTINGS):
        return d.lower() in settings.TRUE
    if sec == "keys" and key in settings.KEY_SETTINGS:
        return d.upper()
    return d
def _pad_value(key, text):
    try:
        import xpad
        dflt = xpad.PAD_DEFAULTS.get(key, "")
    except Exception:
        dflt = ""
    t = dflt if text is None else text
    if isinstance(t, bool) or isinstance(t, (int, float)):
        return t
    t = str(t).strip()
    if key in settings.PAD_BOOLS:
        return t.lower() in settings.TRUE
    if key in settings.PAD_LIMITS:
        try:
            return float(t)
        except ValueError:
            return float(dflt or 0.0)
    return t
def _pad_cfg(V):
    try:
        import xpad
        out = {}
        for k in xpad.PAD_DEFAULTS:
            v = V("pad", k)
            if k in settings.PAD_BOOLS or k in settings.PAD_LIMITS:
                out[k] = v
            else:
                out[k] = xpad._parse_combo(str(v))
                if out[k] is None:
                    out[k] = xpad._parse_combo(xpad.PAD_DEFAULTS[k]) or ()
        return out
    except Exception:
        return None
def _builder(name):
    def build(page, ctx):
        return Page(name, page, ctx)
    build.__name__ = f"build_{name.lower()}"
    build.__doc__ = f"The {name} page into a pw.ScrollPage."
    return build
PAGES = {n: _builder(n) for n in PAGE_ORDER}
def tk_activation_lock():
    return pw.tk_activation_lock()
def tk_activation_unlock():
    pw.tk_activation_unlock()
class PreviewCtx:
    demo = True
    def __init__(self, root=None, path=None, overrides=None, suit="online"):
        S = settings.load(path, quiet=True)
        self.root = root
        self.v = {sec: dict(vals) for sec, vals in S._v.items()}
        self.v["pad"] = dict(S.raw("pad"))
        for (sec, key), val in (overrides or {}).items():
            self.v.setdefault(sec, {})[key] = val
        self._suit = suit
        self.sets, self.toasts = [], []
    def get(self, sec, key):
        if sec == "pad":
            return self.v["pad"].get(key)
        v = self.v[sec][key]
        if sec == "keys" and key in settings.KEY_SETTINGS and isinstance(v, int):
            return settings.key_name(v)
        return v
    def default(self, sec, key):
        return _default(sec, key)
    def set(self, sec, key, value):
        self.sets.append({(sec, key): value})
        self.v.setdefault(sec, {})[key] = value
    def set_many(self, changes):
        self.sets.append(dict(changes))
        for (sec, key), value in changes.items():
            self.v.setdefault(sec, {})[key] = value
    def suit(self):
        return self._suit
    def status(self):
        return {} if self._suit != "offline" else None
    def running(self):
        return self._suit != "offline"
    def toast(self, text, kind="ok", action=None):
        self.toasts.append((text, kind))
    def speed_text(self, level):
        return speed_text(level)
def _preview(names, out_dir, scale=None, ini=None):
    pw.dpi_aware()
    guard = pw.no_activate_guard(True)
    tk_activation_lock()
    pw.REDUCE_MOTION = True
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=pw.BG)
    mon = pw.rightmost_monitor()
    pw.init(root, scale=scale or pw.scale_for(mon[3] - mon[1]))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    try:
        for name in names:
            for w in root.winfo_children():
                w.destroy()
            ctx = PreviewCtx(root, path=ini)
            maxh = mon[3] - mon[1] - pw.px(60)
            frame = tk.Frame(root, bg=pw.BG, width=pw.px(872), height=maxh)
            frame.pack_propagate(False)
            frame.pack(fill="both", expand=True)
            sp = pw.ScrollPage(frame)
            sp.pack(fill="both", expand=True)
            page = PAGES[name](sp, ctx)
            page.refresh({})
            shot = 0
            while True:
                shot += 1
                out = out_dir / f"page_{name.lower()}_{shot}.png"
                more = []
                def ready(shot=shot, more=more):
                    t_end = time.perf_counter() + 0.3
                    while time.perf_counter() < t_end:
                        page.refresh({})
                        root.update()
                        time.sleep(0.02)
                    page.on_show()
                    total = sp.total()
                    h = min(total, maxh)
                    frame.configure(height=h)
                    root.geometry(f"{frame.winfo_reqwidth()}x{h}")
                    root.update()
                    y = (shot - 1) * (h - pw.px(80))
                    sp.scroll_to(y, animate=False)
                    more.append(y + h < total)
                fg0 = pw.u32.GetForegroundWindow()
                w, h = pw.capture(root, str(out), ready=ready)
                fg1 = pw.u32.GetForegroundWindow()
                made.append((out, w, h, fg0 == fg1 and fg1 != 0))
                if not more or not more[0] or shot >= 3:
                    break
    finally:
        root.destroy()
        guard.remove()
    return made
def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Suit Control settings pages")
    ap.add_argument("--preview", default=None, help="FLIGHT POWERS SOUND VISUALS CONTROLS or all")
    ap.add_argument("--out", default=str(HERE / "previews"))
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--ini", default=None, help="a settings file to show (default: settings.ini, only read)")
    a = ap.parse_args(argv)
    if not a.preview:
        ap.print_help()
        return 0
    names = PAGE_ORDER if a.preview.lower() == "all" else [a.preview.upper()]
    for out, w, h, fg_kept in _preview(names, a.out, a.scale, a.ini):
        print(f"{out}: {w}x{h}{'' if fg_kept else '  (FOREGROUND CHANGED)'}")
    return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
