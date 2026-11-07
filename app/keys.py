import ctypes
import os
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path
from PIL import ImageChops, ImageGrab, ImageStat
SCAN = dict(W=0x11, A=0x1E, S=0x1F, D=0x20, SHIFT=0x2A, SPACE=0x39, CTRL=0x1D, F8=0x42, R=0x13, F=0x21,
            E=0x12, Q=0x10, X=0x2D, C=0x2E, G=0x22, Z=0x2C, V=0x2F, B=0x30, H=0x23, T=0x14, Y=0x15,
            ESC=0x01, TAB=0x0F, ENTER=0x1C, ALT=0x38, I=0x17, M=0x32, N=0x31, CAPS=0x3A,
            K1=0x02, K2=0x03, K3=0x04, K4=0x05, K5=0x06, PGUP=0x49, PGDN=0x51, END=0x4F, HOME=0x47,
            F9=0x43, F10=0x44)
EXTENDED = {"PGUP", "PGDN", "END", "HOME"}
KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP = 0x0008, 0x0002
user32 = ctypes.windll.user32
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]
class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]
ROUTE = [None]
def mouse_move(dx, dy=0):
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(dx, dy, 0, 0x0001, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))
MOUSE_BTN = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}
def mouse_button(button, up):
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(0, 0, 0, MOUSE_BTN[button][1 if up else 0], 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))
def click(button="left", secs=0.05):
    mouse_button(button, False)
    time.sleep(secs)
    mouse_button(button, True)
def release_all():
    release(*SCAN)
    for b in MOUSE_BTN:
        mouse_button(b, True)
def _pid(hwnd):
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value
def focused():
    fg = user32.GetForegroundWindow()
    if not fg:
        return True
    try:
        gw = game_window()
    except SystemExit:
        return False
    if fg == gw:
        return True
    p = _pid(fg)
    return p == _pid(gw) or p in _OURS or p == os.getpid()
_OURS = set()
def _send(name, up):
    r_ = ROUTE[0]
    if r_ is not None and r_(name, up):
        return
    raw_send(name, up)
def raw_send(name, up):
    i = INPUT(type=1)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0) | (0x0001 if name in EXTENDED else 0)
    i.ki = KEYBDINPUT(0, SCAN[name], flags, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))
def press(*names):
    for n in names:
        _send(n, False)
def release(*names):
    for n in names:
        _send(n, True)
def hold(secs, *names):
    press(*names)
    time.sleep(secs)
    release(*names)
_GW = [0]
def game_window():
    h = _GW[0]
    if h and user32.IsWindow(h):
        return h
    hwnd = user32.FindWindowW(None, "No Man's Sky")
    if not hwnd:
        raise SystemExit("No Man's Sky window not found")
    _GW[0] = hwnd
    return hwnd
def focus():
    hwnd = game_window()
    for _ in range(5):
        if user32.GetForegroundWindow() == hwnd:
            return True
        user32.ShowWindow(hwnd, 9)
        _send("ALT", False)
        _send("ALT", True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(0.5)
    return user32.GetForegroundWindow() == hwnd
_mss = None
def shot():
    global _mss
    import mss
    from PIL import Image
    if _mss is None:
        _mss = mss.mss()
    r = wt.RECT()
    user32.GetWindowRect(game_window(), ctypes.byref(r))
    g = _mss.grab({"left": r.left, "top": r.top, "width": r.right - r.left, "height": r.bottom - r.top})
    return Image.frombytes("RGB", g.size, g.rgb)
def diff(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b).convert("L")).mean)
if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    print("focused game:", focus(), flush=True)
    a = shot(); time.sleep(2); b = shot()
    hold(2, "W")
    c = shot()
    for img, name in ((a, "keys_0_start"), (b, "keys_1_idle"), (c, "keys_2_after_W")):
        img.convert("RGB").resize((img.width // 2, img.height // 2)).save(out / f"{name}.png")
    print(f"screen change with no input: {diff(a, b):.1f}")
    print(f"screen change after holding W: {diff(b, c):.1f}")
