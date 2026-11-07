import ctypes
import ctypes.wintypes as wt
import threading
import time
WH_KEYBOARD_LL, WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP = 13, 0x100, 0x104, 0x101, 0x105
VK_SPACE, LLKHF_INJECTED = 0x20, 0x10
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
class DoubleTap:
    def __init__(self, window=0.35, vk=VK_SPACE):
        self.window, self.vk = window, vk
        self._held = False
        self._last = -1.0
        self._fired = False
        self.physically_down = False
        self.last_release = -1.0
        self.tap_gap = None
        self.hooked = False
        self.last_any = 0.0
        self.injected_down = set()
        self.last_key = -1e9
        threading.Thread(target=self._run, daemon=True).start()
    def _on_key(self, n_code, w_param, l_param):
        if n_code == 0:
            self.last_any = time.perf_counter()
            k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if k.flags & LLKHF_INJECTED:
                    self.injected_down.add(k.vkCode)
                else:
                    self.last_key = self.last_any
            else:
                self.injected_down.discard(k.vkCode)
            if k.vkCode == self.vk and not (k.flags & LLKHF_INJECTED):
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self._held:
                        now = time.perf_counter()
                        if now - self._last < self.window:
                            self._fired = True
                            self.tap_gap = (self.last_release, now)
                            self._last = -1.0
                        else:
                            self._last = now
                    self._held = self.physically_down = True
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    self._held = self.physically_down = False
                    self.last_release = time.perf_counter()
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
    def _run(self):
        self._proc = HOOKPROC(self._on_key)
        self.hooked = bool(user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0))
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    def reset(self):
        self._last = -1.0
        self._fired = False
    def fired(self):
        if self._fired:
            self._fired = False
            return True
        return False
if __name__ == "__main__":
    t = DoubleTap()
    print("double-tap Space (Ctrl+C to stop)")
    while True:
        if t.fired():
            print("double tap!", flush=True)
        time.sleep(0.01)
