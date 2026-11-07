import ctypes
import ctypes.wintypes as wt
import math
import threading
import time
import wave
import numpy as np
BUF_FRAMES = 1024
NBUF = 6
RATE_TC = 0.06
RATE_RANGE = (0.25, 4.0)
WHDR_DONE, WAVE_MAPPER, CALLBACK_NULL = 0x1, 0xFFFFFFFF, 0x0
class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD),
                ("nAvgBytesPerSec", wt.DWORD), ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD),
                ("cbSize", wt.WORD)]
class WAVEHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD), ("dwBytesRecorded", wt.DWORD),
                ("dwUser", ctypes.c_size_t), ("dwFlags", wt.DWORD), ("dwLoops", wt.DWORD),
                ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]
def load(path):
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if sw != 2 or ch not in (1, 2):
            raise ValueError(f"{path}: {sw * 8}-bit / {ch} channels (16-bit mono or stereo only)")
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
    a = a.reshape(-1, ch)
    return (np.repeat(a, 2, axis=1) if ch == 1 else a), sr
class Renderer:
    def __init__(self, data, sr):
        self.x, self.n, self.sr = np.ascontiguousarray(data, dtype=np.float32), len(data), sr
        self.pos, self.rate, self.rate_tgt = 0.0, 1.0, 1.0
        self.vol, self.vol_tgt, self.vol_rate = 0.0, 0.0, 0.0
        self.stop_at_zero, self.playing = False, False
    def play(self, start, volume, fade):
        self.pos = (max(0.0, start) * self.sr) % self.n
        self.rate = self.rate_tgt = 1.0
        self.vol = 0.0 if fade > 0 else volume
        self.vol_tgt, self.vol_rate = volume, (volume / fade if fade > 0 else 0.0)
        self.stop_at_zero, self.playing = False, True
    def fade(self, volume, secs, stop=False):
        self.vol_tgt = max(0.0, volume)
        self.vol_rate = abs(self.vol_tgt - self.vol) / secs if secs > 0 else 0.0
        self.stop_at_zero = bool(stop)
        if stop and self.vol_tgt <= 0.0 and secs <= 0:
            self.playing, self.vol = False, 0.0
    def stop(self):
        self.playing, self.vol, self.vol_tgt = False, 0.0, 0.0
    def speed(self, rate):
        self.rate_tgt = min(RATE_RANGE[1], max(RATE_RANGE[0], float(rate)))
    def render(self, frames, master=1.0):
        dt = frames / self.sr
        r0 = self.rate
        r1 = r0 + (self.rate_tgt - r0) * (1.0 - math.exp(-dt / RATE_TC))
        if abs(r1 - self.rate_tgt) < 1e-5:
            r1 = self.rate_tgt
        rates = r0 + (r1 - r0) * (np.arange(frames, dtype=np.float64) / frames)
        p = self.pos + np.concatenate(([0.0], np.cumsum(rates[:-1])))
        self.pos = float((self.pos + rates.sum()) % self.n)
        self.rate = r1
        fl = np.floor(p)
        f = (p - fl).astype(np.float32)[:, None]
        i0 = fl.astype(np.int64) % self.n
        i1 = (i0 + 1) % self.n
        out = self.x[i0] * (1.0 - f) + self.x[i1] * f
        v0 = self.vol
        if self.vol_rate <= 0.0:
            v1 = self.vol_tgt
        elif self.vol_tgt > v0:
            v1 = min(self.vol_tgt, v0 + self.vol_rate * dt)
        else:
            v1 = max(self.vol_tgt, v0 - self.vol_rate * dt)
        self.vol = v1
        g = (v0 + (v1 - v0) * (np.arange(frames, dtype=np.float32) / frames)) * np.float32(master)
        out *= g[:, None]
        if self.stop_at_zero and v1 <= 0.0:
            self.playing = False
        return out
class StreamTrack:
    def __init__(self, path, master=lambda: 1.0):
        data, sr = load(path)
        self.r = Renderer(data, sr)
        self.master = master
        self.lock = threading.Lock()
        self.winmm = ctypes.windll.winmm
        wfx = WAVEFORMATEX(1, 2, sr, sr * 4, 4, 16, 0)
        self.hwo = ctypes.c_void_p()
        err = self.winmm.waveOutOpen(ctypes.byref(self.hwo), WAVE_MAPPER, ctypes.byref(wfx), 0, 0, CALLBACK_NULL)
        if err:
            raise OSError(f"waveOutOpen failed ({err})")
        self.bufs = [ctypes.create_string_buffer(BUF_FRAMES * 4) for _ in range(NBUF)]
        self.hdrs = []
        for b in self.bufs:
            h = WAVEHDR(ctypes.cast(b, ctypes.c_void_p), BUF_FRAMES * 4, 0, 0, 0, 0, None, 0)
            self.winmm.waveOutPrepareHeader(self.hwo, ctypes.byref(h), ctypes.sizeof(h))
            self.hdrs.append(h)
        self.queued = [False] * NBUF
        self.written = self.underruns = 0
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="streamtrack")
        self.thread.start()
    def play(self, start=0.0, volume=1.0, fade=0.0):
        with self.lock:
            self.r.play(start, volume, fade)
    def fade(self, volume, secs, stop=False):
        with self.lock:
            self.r.fade(volume, secs, stop)
    def stop(self):
        with self.lock:
            self.r.stop()
        try:
            self.winmm.waveOutReset(self.hwo)
        except Exception:
            pass
    def speed(self, rate):
        with self.lock:
            self.r.speed(rate)
    @property
    def playing(self):
        return self.r.playing
    def close(self):
        self.closed = True
        self.thread.join(1.0)
        try:
            self.winmm.waveOutReset(self.hwo)
            for h in self.hdrs:
                self.winmm.waveOutUnprepareHeader(self.hwo, ctypes.byref(h), ctypes.sizeof(h))
            self.winmm.waveOutClose(self.hwo)
        except Exception:
            pass
    def _run(self):
        try:
            k32 = ctypes.windll.kernel32
            k32.SetThreadPriority(k32.GetCurrentThread(), 2)
        except Exception:
            pass
        while not self.closed:
            if not self.r.playing:
                time.sleep(0.01)
                continue
            free = [i for i in range(NBUF) if not self.queued[i] or self.hdrs[i].dwFlags & WHDR_DONE]
            if len(free) == NBUF and self.written:
                self.underruns += 1
            for i in free:
                with self.lock:
                    if not self.r.playing:
                        break
                    try:
                        m = float(self.master())
                    except Exception:
                        m = 1.0
                    out = self.r.render(BUF_FRAMES, m)
                pcm = (np.clip(out, -1.0, 1.0) * 32767.0).astype(np.int16)
                ctypes.memmove(self.bufs[i], pcm.ctypes.data, BUF_FRAMES * 4)
                self.winmm.waveOutWrite(self.hwo, ctypes.byref(self.hdrs[i]), ctypes.sizeof(self.hdrs[i]))
                self.queued[i] = True
                self.written += 1
            time.sleep(0.004)
