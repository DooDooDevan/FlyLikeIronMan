import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path
import numpy as np
import pymem
PROCESS = "NMS.exe"
STATE = Path(__file__).with_name("vscan_state.npz")
CHUNK = 8 * 1024 * 1024
PACE = 0.001
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
PAGE_READWRITE = 0x04
class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]
def regions(handle):
    k32 = ctypes.windll.kernel32
    k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    addr, mbi = 0, MBI()
    while k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and mbi.Protect == PAGE_READWRITE:
            yield base, size
        addr = base + size
        if addr >= 0x7FFFFFFFFFFF:
            break
def read(pm, base, size):
    try:
        return pm.read_bytes(base, size)
    except Exception:
        return None
    finally:
        time.sleep(PACE)
def lengths(buf):
    v = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 16 * 4).reshape(-1, 4)[:, :3]
    with np.errstate(all="ignore"):
        m = np.sqrt((v.astype(np.float64) ** 2).sum(axis=1))
    m[~np.isfinite(m)] = -1
    return m
def keep(rule, m, prev=None):
    if rule == "moving":
        return (m > 0.5) & (m < 500)
    if rule == "stopped":
        return (m >= 0) & (m < 0.05)
    if rule == "same":
        return (m > 0.5) & (np.abs(m - prev) <= 0.15 * prev)
    raise SystemExit(f"unknown rule {rule}")
def full_scan(pm, rule):
    addrs, mags, total = [], [], 0
    for base, size in regions(pm.process_handle):
        for off in range(0, size, CHUNK):
            n = min(CHUNK, size - off)
            buf = read(pm, base + off, n)
            if buf is None:
                continue
            total += n
            m = lengths(buf)
            idx = np.nonzero(keep(rule, m))[0]
            addrs.append(base + off + idx.astype(np.uint64) * 16)
            mags.append(m[idx])
    print(f"scanned {total / 2**30:.2f} GB")
    return np.concatenate(addrs).astype(np.uint64), np.concatenate(mags)
def current_lengths(pm, addrs):
    out = np.full(len(addrs), -1.0)
    i = 0
    while i < len(addrs):
        start = int(addrs[i])
        j = np.searchsorted(addrs, start + CHUNK, side="left")
        end = int(addrs[j - 1]) + 16
        buf = read(pm, start, end - start)
        if buf is not None:
            m = lengths(buf)
            out[i:j] = m[((addrs[i:j] - start) // 16).astype(np.int64)]
        i = j
    return out
def vec(pm, addr):
    return np.frombuffer(pm.read_bytes(addr, 12), dtype=np.float32)
def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    pm = pymem.Pymem(PROCESS)
    t = time.time()
    if cmd == "scan":
        addrs, mags = full_scan(pm, sys.argv[2])
    elif cmd == "filter":
        st = np.load(STATE)
        addrs, prev = st["addrs"], st["mags"]
        m = current_lengths(pm, addrs)
        mask = keep(sys.argv[2], m, prev)
        addrs, mags = addrs[mask], m[mask]
    elif cmd == "show":
        st = np.load(STATE)
        for a in st["addrs"][: int(sys.argv[2]) if len(sys.argv) > 2 else 40]:
            x, y, z = vec(pm, int(a))
            print(f"0x{int(a):X}  {x:9.3f} {y:9.3f} {z:9.3f}  |v|={np.sqrt(x*x+y*y+z*z):8.3f}")
        return
    elif cmd == "watch":
        a = int(sys.argv[2], 16)
        end = time.time() + (float(sys.argv[3]) if len(sys.argv) > 3 else 5)
        while time.time() < end:
            x, y, z = vec(pm, a)
            print(f"{x:9.3f} {y:9.3f} {z:9.3f}  |v|={np.sqrt(x*x+y*y+z*z):8.3f}")
            time.sleep(0.25)
        return
    else:
        raise SystemExit(__doc__)
    np.savez(STATE, addrs=addrs, mags=mags)
    print(f"{len(addrs):,} candidates  ({time.time() - t:.1f}s)")
if __name__ == "__main__":
    main()
