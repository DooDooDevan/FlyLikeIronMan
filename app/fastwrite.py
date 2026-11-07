import ctypes
import ctypes.wintypes as _w
import pymem.memory
_nt = ctypes.WinDLL("ntdll")
_NtWrite = _nt.NtWriteVirtualMemory
_NtWrite.argtypes = [_w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_NtWrite.restype = ctypes.c_long
stats = {"fast": 0, "fallback": 0}
def _make(orig):
    def write_ctype(handle, address, ctype):
        size = ctypes.sizeof(ctype)
        done = ctypes.c_size_t(0)
        try:
            status = _NtWrite(handle, address, ctypes.addressof(ctype), size, ctypes.byref(done))
        except Exception:
            status = -1
        if status == 0 and done.value == size:
            stats["fast"] += 1
            return 1
        stats["fallback"] += 1
        return orig(handle, address, ctype)
    write_ctype._fastwrite = True
    write_ctype._orig = orig
    return write_ctype
_WPM = ctypes.windll.kernel32.WriteProcessMemory
_WPM.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p)
def write(handle, address, data):
    done = ctypes.c_size_t(0)
    buf = ctypes.create_string_buffer(data, len(data))
    try:
        status = _NtWrite(handle, address, ctypes.addressof(buf), len(data), ctypes.byref(done))
    except Exception:
        status = -1
    if status == 0 and done.value == len(data):
        stats["fast"] += 1
        return True
    stats["fallback"] += 1
    return bool(_WPM(handle, address, data, len(data), None))
def install():
    cur = pymem.memory.write_ctype
    if not getattr(cur, "_fastwrite", False):
        pymem.memory.write_ctype = _make(cur)
install()
