import sys
import time
from pathlib import Path
import numpy as np
import pymem
from vscan import CHUNK, read, regions
ROUNDS = 14
STATE = Path(__file__).with_name("vscan_state.npz")
pm = pymem.Pymem("NMS.exe")
def vecs(buf):
    v = np.frombuffer(buf, dtype=np.float32, count=len(buf) // 16 * 4).reshape(-1, 4)[:, :3].astype(np.float64)
    with np.errstate(all="ignore"):
        n = np.sqrt((v ** 2).sum(axis=1))
    n[~np.isfinite(n)] = -1
    return v, n
def current(addrs):
    out_v, out_n = np.zeros((len(addrs), 3)), np.full(len(addrs), -1.0)
    i = 0
    while i < len(addrs):
        start = int(addrs[i])
        j = np.searchsorted(addrs, start + CHUNK, side="left")
        buf = read(pm, start, int(addrs[j - 1]) + 16 - start)
        if buf is not None:
            v, n = vecs(buf)
            k = ((addrs[i:j] - start) // 16).astype(np.int64)
            out_v[i:j], out_n[i:j] = v[k], n[k]
        i = j
    return out_v, out_n
def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else ROUNDS
    t = time.time()
    addrs, axis, mag = [], [], []
    for base, size in regions(pm.process_handle):
        for off in range(0, size, CHUNK):
            buf = read(pm, base + off, min(CHUNK, size - off))
            if buf is None:
                continue
            v, n = vecs(buf)
            idx = np.nonzero((n > 0.5) & (n < 25))[0]
            addrs.append(base + off + idx.astype(np.uint64) * 16)
            axis.append(v[idx] / n[idx, None])
            mag.append(n[idx])
    addrs, axis, first = np.concatenate(addrs).astype(np.uint64), np.concatenate(axis), np.concatenate(mag)
    seen_sizes = np.ones(len(addrs), dtype=np.int32)
    last_size = first.copy()
    print(f"scan: {len(addrs):,} moving vectors ({time.time() - t:.0f}s)", flush=True)
    for r in range(1, rounds + 1):
        time.sleep(0.3)
        v, n = current(addrs)
        ground = (n >= 0) & (n < 0.05)
        moving = (n > 0.5) & (n < 25)
        with np.errstate(all="ignore"):
            on_line = np.abs((v * axis).sum(axis=1)) / np.maximum(n, 1e-9) > 0.98
        apex = (n >= 0.05) & (n <= 0.5)
        keep = ground | apex | (moving & on_line)
        changed = moving & on_line & (np.abs(n - last_size) > 0.1 * np.maximum(last_size, 0.5))
        seen_sizes = seen_sizes + changed
        last_size = np.where(moving & on_line, n, last_size)
        addrs, axis, seen_sizes, last_size = addrs[keep], axis[keep], seen_sizes[keep], last_size[keep]
        print(f"round {r}: {len(addrs):,} left", flush=True)
    good = seen_sizes >= 3
    addrs = addrs[good]
    print(f"{len(addrs):,} changed size at least 3 times along one line", flush=True)
    v, n = current(addrs)
    for a, x, s, ax in zip(addrs[:30], v[:30], n[:30], axis[good][:30]):
        print(f"0x{int(a):X}  now {x[0]:7.2f} {x[1]:7.2f} {x[2]:7.2f} |v|={s:5.2f}   line {ax[0]:.2f} {ax[1]:.2f} {ax[2]:.2f}")
    np.savez(STATE, addrs=addrs, mags=n)
if __name__ == "__main__":
    main()
