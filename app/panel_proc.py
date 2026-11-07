import ctypes
import ctypes.wintypes as wt
import mmap
import os
import queue
import struct
import subprocess
import threading
import time
from collections import namedtuple
from pathlib import Path
import control
APP = Path(__file__).resolve().parent
KIT = APP.name.lower() == "app"
PKG = APP.parent if KIT else APP
_RT = APP.parent / "runtime" / "python" / "python.exe"
PY = _RT if _RT.exists() else APP / ".venv" / "Scripts" / "python.exe"
PYW = PY.with_name("pythonw.exe") if PY.with_name("pythonw.exe").exists() else PY
FLIGHT = APP / "flight_planet.py"
FLIGHT_OUT, FLIGHT_PREV = APP / "flight_out.txt", APP / "flight_out.prev.txt"
LIMB_FLAG = APP / "limbjets.flag"
KIT_BAT = PKG / "Start Fly Like Iron Man.bat"
GAME_TITLE = "No Man's Sky"
STEAM_URL = "steam://rungameid/275850"
CREATE_NO_WINDOW, CREATE_NEW_PROCESS_GROUP = 0x08000000, 0x00000200
CREATE_BREAKAWAY_FROM_JOB, CREATE_NEW_CONSOLE, DETACHED_PROCESS = 0x01000000, 0x00000010, 0x00000008
SYNCHRONIZE, PROCESS_TERMINATE, QUERY_LIMITED = 0x00100000, 0x0001, 0x1000
Result = namedtuple("Result", "ok text pid")
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi")
_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
_k32.WaitForSingleObject.restype = wt.DWORD
_k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
_k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
_k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_k32.GetCurrentThreadId.restype = wt.DWORD
_psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
_u32.FindWindowW.restype = wt.HWND
_u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
_u32.GetForegroundWindow.restype = wt.HWND
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u32.IsWindow.argtypes = [wt.HWND]
_u32.IsIconic.argtypes = [wt.HWND]
_u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_u32.SetForegroundWindow.argtypes = [wt.HWND]
_u32.BringWindowToTop.argtypes = [wt.HWND]
_u32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
_u32.AllowSetForegroundWindow.argtypes = [wt.DWORD]
_u32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
_u32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
_u32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
_u32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.MsgWaitForMultipleObjects.restype = wt.DWORD
_u32.MsgWaitForMultipleObjects.argtypes = [wt.DWORD, ctypes.c_void_p, wt.BOOL, wt.DWORD, wt.DWORD]
def image_path(pid):
    h = _k32.OpenProcess(QUERY_LIMITED, False, int(pid))
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        _k32.CloseHandle(h)
def processes():
    out = {}
    try:
        arr = (wt.DWORD * 8192)()
        got = wt.DWORD()
        if not _psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(got)):
            return out
        for pid in arr[: got.value // ctypes.sizeof(wt.DWORD)]:
            if pid:
                p = image_path(pid)
                if p:
                    out[pid] = p
    except Exception:
        pass
    return out
_NMS = [0]
def nms_pid():
    try:
        p = _NMS[0]
        if p and Path(image_path(p)).name.lower() == "nms.exe":
            return p
        _NMS[0] = next((pid for pid, exe in processes().items() if Path(exe).name.lower() == "nms.exe"), 0)
        return _NMS[0]
    except Exception:
        return 0
def window_pid(hwnd):
    pid = wt.DWORD()
    if hwnd:
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value
def nms_window(nms=None):
    try:
        hwnd = _u32.FindWindowW(None, GAME_TITLE)
        if not hwnd:
            return 0
        nms = nms_pid() if nms is None else nms
        return hwnd if nms and window_pid(hwnd) == nms else 0
    except Exception:
        return 0
def foreground():
    try:
        h = _u32.GetForegroundWindow()
        return (h or 0), window_pid(h)
    except Exception:
        return 0, 0
def game_in_front(nms=None):
    nms = nms_pid() if nms is None else nms
    return bool(nms) and foreground()[1] == nms
def script_running():
    try:
        return control.mutex_exists(control.SCRIPT_MUTEX)
    except Exception:
        return False
def probe():
    nms = nms_pid()
    fg_hwnd, fg_pid = foreground()
    return dict(t=time.perf_counter(), nms_pid=nms, nms_hwnd=nms_window(nms) if nms else 0,
                game_fg=bool(nms) and fg_pid == nms, fg_hwnd=fg_hwnd, fg_pid=fg_pid, script=script_running())
def pid_alive(pid):
    return control.pid_alive(pid)
def wait_exit(pid, timeout):
    if not pid:
        return True
    h = _k32.OpenProcess(SYNCHRONIZE | QUERY_LIMITED, False, int(pid))
    if not h:
        end = time.perf_counter() + timeout
        while pid_alive(pid) and time.perf_counter() < end:
            time.sleep(0.1)
        return not pid_alive(pid)
    try:
        return _k32.WaitForSingleObject(h, int(max(0.0, timeout) * 1000)) == 0
    finally:
        _k32.CloseHandle(h)
class ModWatch:
    def __init__(self):
        self.mm, self.nms = None, False
    def update(self, nms_running):
        self.nms = bool(nms_running)
        if self.nms and self.mm is None:
            try:
                self.mm = mmap.mmap(-1, control.GAME_SIZE, tagname=control.GAME_NAME)
            except OSError:
                self.mm = None
        elif not self.nms and self.mm is not None:
            self.close()
    def stamp(self):
        try:
            return struct.unpack_from(control.GAME_FMT, self.mm, 0) if self.mm is not None else (0.0, 0)
        except Exception:
            return 0.0, 0
    def state(self, now=None):
        now = time.perf_counter() if now is None else now
        t = self.stamp()[0]
        return control.mod_state(t, self.nms, now), (now - t if t > 0.0 else -1.0)
    def close(self):
        if self.mm is not None:
            try:
                self.mm.close()
            except Exception:
                pass
            self.mm = None
def flight_command():
    return [str(PY), "-u", str(FLIGHT), "--pose"]
def _env():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if KIT:
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env["PATH"] = str(_RT.parent) + os.pathsep + env.get("PATH", "")
    return env
def spawn_flight():
    try:
        if FLIGHT_OUT.exists():
            os.replace(FLIGHT_OUT, FLIGHT_PREV)
    except OSError:
        pass
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    try:
        out = open(FLIGHT_OUT, "wb")
    except OSError:
        try:
            out = open(APP / "flight_out.panel.txt", "wb")
        except OSError:
            out = None
    try:
        kw = dict(cwd=str(APP), env=_env(), stdin=subprocess.DEVNULL, stdout=out or subprocess.DEVNULL,
                  stderr=subprocess.STDOUT)
        try:
            return subprocess.Popen(flight_command(), creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:
            return subprocess.Popen(flight_command(), creationflags=flags, **kw)
    finally:
        if out is not None:
            out.close()
def flight_out_tail(n=6):
    try:
        with open(FLIGHT_OUT, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            lines = [ln.strip() for ln in f.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        return lines[-n:]
    except OSError:
        return []
def in_world(timeout=40.0):
    try:
        r = subprocess.run([str(PY), "-c", "from locate import find, vtable\nprint(len(find(vtable())))"],
                           cwd=str(APP), env=_env(), capture_output=True, text=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
        n = int((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return None
    return n >= 3
WORLD_STAMP_S = 5.0
def _say(progress, text):
    if progress:
        try:
            progress(text)
        except Exception:
            pass
def _guard(fn):
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            return Result(False, f"{fn.__name__} failed ({e.__class__.__name__}: {e})", 0)
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run
@_guard
def start_suit(client, progress=None, check_world=True):
    st = client.status()
    if script_running() or (getattr(client, "suffix", "") and st["alive"]):
        return Result(True, "the suit is already running", st["pid"] if st["alive"] else 0)
    if not nms_pid():
        return Result(False, "Start No Man's Sky first", 0)
    if check_world:
        mw = ModWatch()
        mw.update(True)
        age = mw.state()[1]
        mw.close()
        if not 0.0 <= age < WORLD_STAMP_S:
            _say(progress, "checking that you're in the world ...")
            if in_world() is False:
                return Result(False, "Load your save first, then press it again", 0)
    _say(progress, "powering up the suit ...")
    old = st["session"]
    p = spawn_flight()
    end = time.perf_counter() + 20.0
    while time.perf_counter() < end:
        st = client.status()
        if st["magic"] and st["session"] != old and st["alive"]:
            return Result(True, "the suit is starting", st["pid"])
        code = p.poll()
        if code is not None:
            if code == 3:
                st = client.status()
                return Result(True, "the suit was already running", st["pid"] if st["alive"] else 0)
            tail = flight_out_tail(1)
            return Result(False, f"the flight script stopped at once ({control.exit_text(code)})"
                          + (f": {tail[-1]}" if tail else ""), 0)
        time.sleep(0.2)
    return Result(False, "the flight script didn't answer in 20 s (see flight_out.txt)", 0)
def _quit(client, restart, progress):
    st = client.status()
    pid = st["pid"]
    seq = client.send("quit", (1.0 if restart else 0.0,))
    ack = client.wait(seq, 3.0)
    _say(progress, "waiting for the suit to power down ...")
    return pid, ack, wait_exit(pid, 15.0 if restart else 10.0)
@_guard
def power_down(client, progress=None):
    st = client.status()
    if not st["alive"]:
        return Result(True, "the suit is already off", 0)
    pid, ack, gone = _quit(client, False, progress)
    if gone:
        return Result(True, "the suit is powered down", 0)
    if ack is None:
        return Result(False, "the suit didn't answer: FORCE STOP can end it", pid)
    return Result(False, "the suit didn't power down in 10 s: FORCE STOP can end it", pid)
@_guard
def restart_suit(client, progress=None):
    st = client.status()
    if not st["alive"]:
        return start_suit(client, progress)
    pid, ack, gone = _quit(client, True, progress)
    if not gone:
        return Result(False, "the suit didn't stop in 15 s: FORCE STOP can end it", pid)
    return start_suit(client, progress, check_world=False)
def _image_h(h):
    buf = ctypes.create_unicode_buffer(1024)
    n = wt.DWORD(1024)
    return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
def _key_up(scan):
    class KBD(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p)]
    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KBD), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]
    i = INPUT(type=1)
    i.ki = KBD(0, scan, 0x0008 | 0x0002, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))
def _write_flag(text):
    tmp = LIMB_FLAG.with_name(LIMB_FLAG.name + ".tmp")
    for _ in range(20):
        try:
            tmp.write_text(text)
            os.replace(tmp, LIMB_FLAG)
            return True
        except OSError:
            time.sleep(0.01)
    return False
_GONE = "the flight script had already stopped (nothing was touched): POWER UP starts it again"
@_guard
def force_stop(client, progress=None):
    st = client.status()
    pid = st["pid"]
    if not (st["magic"] and pid and pid_alive(pid)):
        return Result(True, "the suit isn't running", 0)
    if st.get("pid_reused"):
        return Result(True, _GONE, 0)
    if pid == os.getpid():
        return Result(False, "that process isn't the flight script: nothing was stopped", 0)
    if control.suit_state(st)[0] == "online":
        return Result(False, "the suit is answering: POWER DOWN ends it cleanly (nothing was stopped)", 0)
    h = _k32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE | QUERY_LIMITED, False, int(pid))
    if not h:
        if not script_running():
            return Result(True, _GONE, 0)
        return Result(False, "Windows won't let Suit Control stop it (started as administrator?)", pid)
    try:
        if not Path(_image_h(h)).name.lower().startswith("python") or not script_running() \
                or control.runs_script(pid, control.SCRIPT_NAME, h) is False \
                or control.same_process(pid, st["started"], control.created_h(h)) is False:
            return Result(True, _GONE, 0)
        _say(progress, "stopping the flight script ...")
        _k32.TerminateProcess(h, 1)
        gone = _k32.WaitForSingleObject(h, 5000) == 0
    finally:
        _k32.CloseHandle(h)
    if not gone:
        return Result(False, "it is still running after 5 s", pid)
    _key_up(0x39)
    _write_flag("0")
    return Result(True, "the flight script was stopped: POWER UP starts it again", 0)
def steam_autostart():
    try:
        import start_flight
        return bool(start_flight.steam_autostart())
    except Exception:
        import glob
        for f in glob.glob(r"C:\Program Files (x86)\Steam\userdata\*\config\localconfig.vdf"):
            try:
                if "steam_launch.bat" in open(f, encoding="utf-8", errors="replace").read():
                    return True
            except OSError:
                pass
        return False
GAME_WAIT = 120.0
_LAUNCH = dict(t=-1e9, proc=None, text="")
def _shell_open(target):
    os.startfile(target)
def _console(cmd):
    return subprocess.Popen(cmd, cwd=str(APP), env=_env(), creationflags=CREATE_NEW_CONSOLE)
@_guard
def start_game(progress=None, wait=None):
    wait = GAME_WAIT if wait is None else wait
    if nms_pid():
        return Result(False, "No Man's Sky is already running", 0)
    now = time.perf_counter()
    p = _LAUNCH["proc"]
    launcher_open = p is not None and p.poll() is None
    if now - _LAUNCH["t"] < GAME_WAIT:
        _say(progress, "No Man's Sky is starting already: waiting for it ...")
    elif launcher_open:
        return Result(False, "the game launcher's window is still open: finish there, or close it and press again", 0)
    else:
        if KIT:
            if not KIT_BAT.exists():
                return Result(False, f"{KIT_BAT.name} is missing", 0)
            _shell_open(str(KIT_BAT))
            p, text = None, "starting the game: a window opens and explains each step (leave it open)"
        elif steam_autostart():
            _shell_open(STEAM_URL)
            p, text = None, "starting No Man's Sky through Steam: the suit powers up by itself in the world"
        else:
            p = _console([str(PY), "-u", str(APP / "start_flight.py")])
            text = "starting the game: the launcher window explains each step"
        _LAUNCH.update(t=now, proc=p, text=text)
        _say(progress, "waiting for No Man's Sky to open ...")
    end = time.perf_counter() + max(0.0, wait)
    while True:
        if nms_pid():
            return Result(True, _LAUNCH["text"] or "No Man's Sky is starting", 0)
        left = end - time.perf_counter()
        if left <= 0.0:
            break
        time.sleep(min(1.0, left))
    return Result(False, "No Man's Sky hasn't opened yet: Steam (or the launcher window) may be showing a message", 0)
class Job:
    def __init__(self, fn, *args, **kw):
        self.events, self.done, self.result = queue.Queue(), False, None
        self._t = threading.Thread(target=self._run, args=(fn, args, kw), daemon=True, name="suit-job")
        self._t.start()
    def _run(self, fn, args, kw):
        try:
            self.result = fn(*args, progress=self.events.put, **kw)
        except Exception as e:
            self.result = Result(False, f"{e.__class__.__name__}: {e}", 0)
        finally:
            self.done = True
    def wait(self, timeout=None):
        self._t.join(timeout)
        return self.result
def allow_foreground(pid):
    try:
        return bool(_u32.AllowSetForegroundWindow(int(pid)))
    except Exception:
        return False
def focus_game(wait=0.2):
    try:
        nms = nms_pid()
        hwnd = nms_window(nms)
        if not hwnd:
            return False
        end = time.perf_counter() + max(0.0, wait)
        while True:
            if foreground()[1] == nms:
                return True
            if time.perf_counter() >= end:
                break
            time.sleep(0.02)
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, 9)
        _u32.SetForegroundWindow(hwnd)
        return foreground()[1] == nms
    except Exception:
        return False
def _alt_tap():
    class KBD(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p)]
    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KBD), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]
    for up in (0, 0x0002):
        i = INPUT(type=1)
        i.ki = KBD(0, 0x38, 0x0008 | up, 0, None)
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))
def raise_window(hwnd):
    try:
        hwnd = int(hwnd or 0)
        if not hwnd or not _u32.IsWindow(hwnd):
            return False
        _u32.ShowWindow(hwnd, 9 if _u32.IsIconic(hwnd) else 5)
        _u32.SetForegroundWindow(hwnd)
        _u32.BringWindowToTop(hwnd)
        if foreground()[0] == hwnd:
            return True
        _alt_tap()
        _u32.SetForegroundWindow(hwnd)
        _u32.BringWindowToTop(hwnd)
        return foreground()[0] == hwnd
    except Exception:
        return False
class PanelLock:
    def __init__(self, name=control.PANEL_MUTEX):
        self._m = control.Mutex(name)
        self.taken = self._m.taken
        if self.taken:
            self._m.close()
    def close(self):
        self._m.close()
def handoff_to_resident(client):
    try:
        info = client.panel_info()
        running = info["alive"] or control.mutex_exists(control.PANEL_MUTEX)
        if not running:
            return False
        if info["pid"] and pid_alive(info["pid"]):
            allow_foreground(info["pid"])
        client.show_request()
        return True
    except Exception:
        return False
_NEVER_HOTKEY = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12, 0x14, 0x20, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4,
                 0xA5, 0x5B, 0x5C,
                 0x08, 0x09, 0x0D, 0x1B, 0x25, 0x26, 0x27, 0x28, 0x2E}
def hotkey_ok(vk, blocked=()):
    return bool(vk) and 0 < int(vk) < 0xFF and int(vk) not in _NEVER_HOTKEY and int(vk) not in set(blocked)
class HotkeyThread(threading.Thread):
    ID = 0x4946
    WM_HOTKEY, WM_QUIT, MOD_NOREPEAT = 0x0312, 0x0012, 0x4000
    def __init__(self, vk, blocked=(), interval=0.2):
        super().__init__(daemon=True, name="suit-hotkey")
        self.queue = queue.Queue()
        self.registered, self.vk, self.error = False, 0, ""
        self._want, self._blocked, self._interval = int(vk or 0), set(blocked), interval
        self._tid, self._stop_ev = 0, threading.Event()
        self._img = {}
    def set_vk(self, vk, blocked=None):
        self._want = int(vk or 0)
        if blocked is not None:
            self._blocked = set(blocked)
    def stop(self):
        self._stop_ev.set()
        if self._tid:
            _u32.PostThreadMessageW(self._tid, self.WM_QUIT, 0, 0)
    def _in_front(self):
        pid = foreground()[1]
        if not pid:
            return False
        if pid == os.getpid():
            return True
        if pid not in self._img:
            if len(self._img) > 64:
                self._img.clear()
            self._img[pid] = Path(image_path(pid)).name.lower() == "nms.exe"
        return self._img[pid]
    def _sync(self):
        want = self._want if hotkey_ok(self._want, self._blocked) and self._in_front() else 0
        if self.registered and want != self.vk:
            _u32.UnregisterHotKey(None, self.ID)
            self.registered, self.vk = False, 0
        if want and not self.registered:
            if _u32.RegisterHotKey(None, self.ID, self.MOD_NOREPEAT, want):
                self.registered, self.vk, self.error = True, want, ""
            else:
                self.error = "another program has this key as its hotkey"
    def run(self):
        self._tid = _k32.GetCurrentThreadId()
        msg = wt.MSG()
        _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        try:
            while not self._stop_ev.is_set():
                try:
                    self._sync()
                except Exception:
                    pass
                _u32.MsgWaitForMultipleObjects(0, None, False, int(self._interval * 1000), 0x04FF)
                while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.ID:
                        self.queue.put("toggle")
                    elif msg.message == self.WM_QUIT:
                        self._stop_ev.set()
        finally:
            if self.registered:
                _u32.UnregisterHotKey(None, self.ID)
                self.registered = False
if __name__ == "__main__":
    p = probe()
    print("game:", p["nms_pid"] or "not running", "| window:", p["nms_hwnd"], "| in front:", p["game_fg"],
          "| flight script:", "running" if p["script"] else "not running")
    print("python:", PY, "| kit:", KIT)
