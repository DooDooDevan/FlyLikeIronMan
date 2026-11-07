import importlib
import logging
import os
import sys
import threading
import time
from ctypes import c_bool, c_uint32, c_uint64
import nmspy.data.types as nms
from pymhf import FUNCDEF, Mod
from pymhf.core.hooking import manual_hook
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "limbjets_core.py")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
log = logging.getLogger("limbjets")
log.setLevel(logging.INFO)
if not log.handlers:
    _fh = logging.FileHandler(os.path.join(ROOT, "limbjets_log.txt"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    log.addHandler(_fh)
import limbjets_core as core
log.info("limbjets mod loaded")
class LimbJets(Mod):
    __author__ = "DooDooDevan"
    __description__ = "Equipped jetpack trail copied onto hands and feet while flying"
    def __init__(self):
        super().__init__()
        self.st = core.State()
        self.core_mtime = os.path.getmtime(CORE)
        self.next_check = 0.0
        self.threads = {}
        log.info("LimbJets mod instance created")
    def _note_thread(self, hook):
        if hook in self.threads or len(self.threads) >= 2:
            return
        self.threads[hook] = threading.get_ident()
        if len(self.threads) == 2:
            a, b = self.threads.get("update"), self.threads.get("graphics")
            log.info(f"threads: update={a} graphics={b} ({'same' if a == b else 'DIFFERENT'})")
    def _call(self, name, *args):
        try:
            return getattr(core, name)(self.st, *args)
        except Exception:
            if name not in self.st.errors:
                self.st.errors.add(name)
                log.exception(f"{name} failed (repeats not logged)")
    def _maybe_reload(self):
        global core
        now = time.perf_counter()
        if now < self.next_check:
            return
        self.next_check = now + 1.0
        try:
            m = os.path.getmtime(CORE)
        except OSError:
            return
        if m != self.core_mtime:
            self.core_mtime = m
            try:
                core = importlib.reload(core)
                self.st.errors.clear()
                log.info("limbjets_core reloaded")
                core.on_reload(self.st)
            except Exception:
                log.exception("reloading limbjets_core failed")
    @manual_hook("RefreshJetpackEffect", offset=0x1157BC0, func_def=FUNCDEF(restype=None, argtypes=[c_uint64]),
                 detour_time="before")
    def refresh_before(self, this):
        self._call("refresh_before", this)
    @manual_hook("RefreshJetpackEffect", offset=0x1157BC0, func_def=FUNCDEF(restype=None, argtypes=[c_uint64]),
                 detour_time="after")
    def refresh_after(self, this):
        self._call("refresh_after", this)
    @manual_hook("QuickMenuAddAction", offset=0x156EEC0,
                 func_def=FUNCDEF(restype=c_uint64, argtypes=[c_uint64, c_uint64]), detour_time="after")
    def qmenu_add_after(self, actions, action):
        self._call("qmenu_add_after", actions, action)
    @manual_hook("JetLocatorBuilder", offset=0x1157F10,
                 func_def=FUNCDEF(restype=c_bool, argtypes=[c_uint64, c_uint32]), detour_time="before")
    def builder_before(self, cap, node):
        self._call("builder_before", cap, node)
    @nms.cGcPlayerCharacterComponent.Update.after
    def update_after(self, this, lfTimeStep):
        self._maybe_reload()
        self._note_thread("update")
        self._call("update", this)
    @nms.cGcPlayer.UpdateGraphics.after
    def graphics_after(self, this, lbSetNode):
        self._note_thread("graphics")
        self._call("graphics_after", this, lbSetNode)
