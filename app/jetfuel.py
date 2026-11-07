from classes import vtables_for
from objects import find
from rtti import pm
OFFSET = 0x3524
CLASS = "cGcPlayer"
def locate():
    try:
        import lookup
        p = lookup.player(pm)
        if p:
            return p + OFFSET
    except Exception:
        pass
    for vt in vtables_for(CLASS):
        for obj in find(vt):
            a = obj + OFFSET
            try:
                v = pm.read_float(a)
            except Exception:
                continue
            if 0.0 <= v <= 1000.0:
                return a
    return None
def read(addr):
    return pm.read_float(addr)
def fill(addr, value):
    pm.write_float(addr, value)
if __name__ == "__main__":
    a = locate()
    print(f"tank at 0x{a:X}: {read(a):.2f} s" if a else "tank not found")
