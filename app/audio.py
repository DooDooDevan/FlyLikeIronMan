import ctypes
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
VOICES = 2
CUES = ("ready", "error", "speed_up", "speed_down", "speed_limit", "burner_off", "dive_on")
ERROR_GAP = 1.0
_q = queue.Queue()
_state = dict(dir=None, volume=1000, cues=True, mci=False, started=False, last_error=-9.0)
_aliases = {}
muted = set()
_tracks = {}
STREAMED = ("ip_hum", "unibeam_hum", "wristlaser_hold")
_streams = {}
_stream_bad = set()
TRACK_TICK = 0.03
_next = {}
_thread = [None]
def _mci(cmd):
    buf = ctypes.create_unicode_buffer(128)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 128, None)
    return err, buf.value
def _scaled(path, volume):
    if volume >= 1000:
        return path
    out = Path(tempfile.gettempdir()) / "ironman_flight_sounds" / f"{path.stem}_v{volume}.wav"
    try:
        if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
            return out
        import numpy as np
        with wave.open(str(path), "rb") as f:
            params, frames = f.getparams(), f.readframes(f.getnframes())
        if params.sampwidth != 2:
            return path
        x = (np.frombuffer(frames, dtype=np.int16).astype(np.float32) * (volume / 1000.0)).astype(np.int16)
        out.parent.mkdir(exist_ok=True)
        with wave.open(str(out), "wb") as f:
            f.setparams(params)
            f.writeframes(x.tobytes())
        return out
    except Exception:
        return path
def _open_all():
    d = _state["dir"]
    ok = False
    for i, p in enumerate(sorted(Path(d).glob("*.wav"))):
        src = _scaled(p, _state["volume"])
        names = []
        for k in range(VOICES):
            alias = f"imf{i}v{k}"
            err, _ = _mci(f'open "{src}" type waveaudio alias {alias}')
            if err == 0:
                names.append(alias)
        if names:
            _aliases[p.stem], _next[p.stem] = names, 0
            ok = True
    return ok
def _close_sounds():
    for names in _aliases.values():
        for a in names:
            _mci(f"close {a}")
    _aliases.clear()
def _close_all():
    _close_sounds()
    for tr in _tracks.values():
        _mci(f"close {tr['alias']}")
    _tracks.clear()
def _swap_volume(volume):
    if volume == _state["volume"]:
        return
    _close_sounds()
    _state["volume"] = volume
    _state["mci"] = _open_all()
    for tr in _tracks.values():
        _track_vol(tr, tr["vol"])
def _track_vol(tr, v):
    tr["vol"] = max(0.0, min(1.0, v))
    _mci(f"setaudio {tr['alias']} volume to {int(round(1000 * tr['vol'] * _state['volume'] / 1000.0))}")
def _track_cmd(cmd):
    kind, name = cmd[0], cmd[1]
    tr = _tracks.get(name)
    if kind in ("play", "open"):
        if tr is None:
            path = Path(_state["dir"]) / "tracks" / f"{name}.wav"
            if not path.exists():
                return
            alias = f"imftrk{len(_tracks)}"
            if _mci(f'open "{path}" type mpegvideo alias {alias}')[0] != 0:
                return
            tr = _tracks[name] = dict(alias=alias, vol=0.0, target=0.0, rate=0.0, stop=False, speed=1000)
            _track_vol(tr, 0.0)
        if kind == "open":
            return
        _, _, start, loop, vol, fade = cmd
        if tr.get("speed", 1000) != 1000:
            _mci(f"set {tr['alias']} speed 1000")
            tr["speed"] = 1000
        _track_vol(tr, 0.0 if fade > 0 else vol)
        tr.update(target=vol, rate=(vol / fade) if fade > 0 else 0.0, stop=False)
        _mci(f"play {tr['alias']} from {int(max(0.0, start) * 1000)}" + (" repeat" if loop else ""))
    elif tr is None:
        return
    elif kind == "fade":
        _, _, vol, secs, stop = cmd
        if secs <= 0 or abs(vol - tr["vol"]) < 1e-6:
            _track_vol(tr, vol)
            tr.update(target=vol, rate=0.0)
            if stop and vol <= 0.0:
                _mci(f"stop {tr['alias']}")
        else:
            tr.update(target=vol, rate=abs(vol - tr["vol"]) / secs, stop=stop)
    elif kind == "speed":
        sp = int(round(max(0.25, min(4.0, cmd[2])) * 1000))
        if sp != tr.get("speed", 1000):
            _mci(f"set {tr['alias']} speed {sp}")
            tr["speed"] = sp
    elif kind == "stop":
        _mci(f"stop {tr['alias']}")
        tr.update(target=0.0, rate=0.0, stop=False)
def _track_tick(dt):
    for tr in _tracks.values():
        if tr["rate"] <= 0.0 or tr["vol"] == tr["target"]:
            continue
        v, t = tr["vol"], tr["target"]
        v = min(t, v + tr["rate"] * dt) if t > v else max(t, v - tr["rate"] * dt)
        _track_vol(tr, v)
        if v == t:
            tr["rate"] = 0.0
            if tr["stop"] and t <= 0.0:
                _mci(f"stop {tr['alias']}")
                tr["stop"] = False
def _worker():
    _state["mci"] = _open_all()
    last = time.perf_counter()
    while True:
        try:
            name = _q.get(timeout=TRACK_TICK)
        except queue.Empty:
            name = ""
        now = time.perf_counter()
        _track_tick(min(0.2, now - last))
        last = now
        if name == "":
            continue
        if name is None:
            break
        if callable(name):
            name()
            continue
        if isinstance(name, tuple):
            _track_cmd(name)
            continue
        if _state["mci"] and name in _aliases:
            names = _aliases[name]
            a = names[_next[name]]
            _next[name] = (_next[name] + 1) % len(names)
            err = _mci(f"play {a} from 0")[0]
            if err == 0:
                continue
        _winsound(name)
    _close_all()
def _winsound(name):
    try:
        import winsound
        p = Path(_state["dir"]) / f"{name}.wav"
        if p.exists():
            winsound.PlaySound(str(_scaled(p, _state["volume"])),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass
def start(sound_dir, volume=1000, cues=True):
    if _state["started"]:
        return
    _state.update(dir=str(sound_dir), volume=max(0, min(1000, int(volume))), cues=bool(cues), started=True)
    t = threading.Thread(target=_worker, daemon=True, name="audio")
    _thread[0] = t
    t.start()
def play(name):
    if not _state["started"] or _state["volume"] <= 0 or name in muted:
        return
    _q.put(name)
def set_volume(volume):
    try:
        v = max(0, min(1000, int(round(float(volume) / 50.0)) * 50))
    except (TypeError, ValueError, OverflowError):
        return
    if not _state["started"]:
        _state["volume"] = v
        return
    _q.put(lambda: _swap_volume(v))
def get_volume():
    return _state["volume"]
def _stream(name):
    if name not in STREAMED or name in _stream_bad or not _state["started"]:
        return None
    st = _streams.get(name)
    if st is None:
        path = Path(_state["dir"]) / "tracks" / f"{name}.wav"
        if not path.exists():
            return None
        try:
            import streamtrack
            st = _streams[name] = streamtrack.StreamTrack(path, master=lambda: _state["volume"] / 1000.0)
        except Exception:
            _stream_bad.add(name)
            return None
    return st
def track_play(name, start=0.0, loop=False, volume=1.0, fade=0.0):
    if _state["started"] and _state["volume"] > 0 and name not in muted:
        st = _stream(name)
        if st is not None:
            st.play(float(start), float(volume), float(fade))
            return
        _q.put(("play", name, float(start), bool(loop), float(volume), float(fade)))
def track_speed(name, rate):
    if _state["started"]:
        st = _streams.get(name)
        if st is not None:
            st.speed(float(rate))
            return
        _q.put(("speed", name, float(rate)))
def track_open(name):
    if _state["started"] and _state["volume"] > 0:
        if name in STREAMED and _stream(name) is not None:
            return
        _q.put(("open", name))
def track_fade(name, volume, secs, stop=False):
    if _state["started"]:
        st = _streams.get(name)
        if st is not None:
            st.fade(float(volume), float(secs), bool(stop))
            return
        _q.put(("fade", name, float(volume), float(secs), bool(stop)))
def track_stop(name, fade=0.0):
    if _state["started"]:
        st = _streams.get(name)
        if st is not None:
            st.fade(0.0, float(fade), True) if fade > 0 else st.stop()
            return
        _q.put(("fade", name, 0.0, float(fade), True) if fade > 0 else ("stop", name))
def cue(name):
    if not _state["cues"]:
        return
    if name == "error":
        now = time.perf_counter()
        if now - _state["last_error"] < ERROR_GAP:
            return
        _state["last_error"] = now
    play(name)
def stop(timeout=0.5):
    for st in list(_streams.values()):
        try:
            st.close()
        except Exception:
            pass
    _streams.clear()
    t = _thread[0]
    if t is None:
        return
    _q.put(None)
    t.join(timeout)
    _thread[0] = None
    _state["started"] = False
def _set_title(text):
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except Exception:
        pass
_title = [None]
def title(text):
    t = f"Iron Man: {text}"
    if t != _title[0]:
        _title[0] = t
        _set_title(t)
if __name__ == "__main__":
    import sys
    here = Path(__file__).parent
    start(here / "sounds", volume=int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
    time.sleep(0.5)
    print("mci:", _state["mci"], "sounds:", sorted(_aliases))
    t0 = time.perf_counter()
    play("afterburner_on")
    print("play() took %.3f ms" % ((time.perf_counter() - t0) * 1000))
    time.sleep(0.25)
    play("speed_up")
    time.sleep(1.5)
    for c in CUES:
        print("cue", c, flush=True)
        cue(c)
        time.sleep(0.6)
    stop()
