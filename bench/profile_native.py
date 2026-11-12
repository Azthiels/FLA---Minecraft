"""Perfil del coste por etapa (1 hilo): posiciones potenciales vs validacion de viabilidad vs modo grupos."""
import ctypes, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sa import estructuras, nativo
from sa.nativo import L

CASOS = [("Witch Hut", 3, "26.3", 20000), ("Witch Hut", 3, "1.16", 20000), ("Village", 5, "26.3", 20000),
         ("Monument", 8, "26.3", 20000), ("Desert Pyramid", 1, "26.3", 20000), ("Buried Treasure", 14, "26.3", 1500),
         ("Fortress", 18, "26.3", 2500), ("End City", 21, "26.3", 20000), ("Ruined Portal", 11, "26.3", 20000)]


def correr(sid, ver, R, flags, seed=12345):
    mc = nativo.mc_id(ver)
    rb = L.sh_region_blocks(sid, mc)
    dim = nativo.dimension(sid, ver)
    Rd = nativo.limite_dimension(dim, R * 8 if dim == -1 else R)
    r = Rd // rb + 1
    h = L.sh_new(mc, seed, sid)
    boxes = (ctypes.c_int * 4)(-Rd, -Rd, Rd, Rd)
    L.sh_set_groups(h, 128, estructuras.caja(sid).lado, boxes, 1)
    n_reg = (2 * r + 1) ** 2
    buf = (ctypes.c_int * (3 * n_reg))()
    t = time.perf_counter()
    n = L.sh_scan_tile(h, -r, -r, r, r, -Rd, -Rd, Rd, Rd, None, flags, buf, n_reg)
    dt = time.perf_counter() - t
    st = (ctypes.c_uint64 * nativo.NSTAT)(); L.sh_stats(h, st); L.sh_free(h)
    return n_reg, dt, dict(zip(nativo.STAT_NAMES, st)), n


if __name__ == "__main__":
    print(f"{'caso':24}{'regiones':>10}{'pos/s':>12}{'todas(s)':>10}{'grupos(s)':>10}{'x':>7}{'%bioma':>8}{'found':>8}{'grp':>6}")
    for nombre, sid, ver, R in CASOS:
        n_reg, dt0, st0, _ = correr(sid, ver, R, nativo.F_NO_VIABLE)
        _, dt1, st1, n1 = correr(sid, ver, R, 0)
        _, dt2, st2, n2 = correr(sid, ver, R, nativo.F_GROUPS)
        pct = 100 * st2["viable_calls"] / max(1, st1["viable_calls"])
        print(f"{nombre + ' ' + ver:24}{n_reg:>10,}{st0['positions'] / dt0:>12,.0f}{dt1:>10.3f}{dt2:>10.3f}"
              f"{dt1 / max(dt2, 1e-9):>7.1f}{pct:>8.1f}{n1:>8}{n2:>6}")
