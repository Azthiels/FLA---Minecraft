"""Benchmark del escaner: modo "todas" vs modo "grupos", y escalado con hilos. Cada corrida en un subproceso
limpio (RAM pico real). Uso:  python bench/bench.py [rapido]    -> resultados en bench/resultados_bench.txt"""
import json, os, platform, statistics, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CODIGO = r'''
import sys, json, time; sys.path.insert(0, %(root)r)
from sa import nativo, util
from sa.escaner import Escaneo
modo, ver, sid, R, hilos, tmp = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
e = Escaneo(ver, nativo.parse_seed("6283985518325545008"), sid, R, tmp + "/r", hilos=hilos, modo=modo)
t = time.perf_counter(); r = e.run(); dt = time.perf_counter() - t
print(json.dumps(dict(dt=dt, found=e.escritas, regiones=e.regiones_total, stats=r["stats"], rss_mb=util.ram_pico_mb())))
'''


def correr(modo, ver, sid, R, hilos):
    with tempfile.TemporaryDirectory() as tmp:
        o = subprocess.run([sys.executable, "-c", CODIGO % {"root": ROOT}, modo, ver, str(sid), str(R), str(hilos), tmp],
                           capture_output=True, text=True, timeout=7200)
        if o.returncode:
            raise RuntimeError(o.stderr[-800:])
        return json.loads(o.stdout.strip().splitlines()[-1])


def comparar(out, titulo, ver, sid, R, hilos, reps):
    out(f"\n### {titulo}  (version {ver}, estructura {sid}, radio {R:,}, {hilos} hilos, {reps} reps, mediana)")
    out(f"{'':8}{'tiempo(s)':>10}{'reg/s':>14}{'guardadas':>11}{'bioma consultado':>18}{'RAM pico MB':>13}")
    fil = {}
    for modo in ("todas", "grupos"):
        rs = [correr(modo, ver, sid, R, hilos) for _ in range(reps)]
        dt = statistics.median(r["dt"] for r in rs)
        r0 = rs[0]
        fil[modo] = dt
        out(f"{modo:8}{dt:>10.2f}{r0['regiones'] / dt:>14,.0f}{r0['found']:>11,}{r0['stats']['viable_calls']:>18,}"
            f"{max(r['rss_mb'] or 0 for r in rs):>13.0f}")
    out(f"  velocidad grupos/todas: {fil['todas'] / fil['grupos']:.2f}x")
    return fil


if __name__ == "__main__":
    rapido = "rapido" in sys.argv
    lineas = []

    def out(s=""):
        print(s, flush=True)
        lineas.append(s)
    nucleos = os.cpu_count() or 1
    out(f"Maquina: {platform.platform()} | {platform.processor()} | nucleos logicos: {nucleos} | python {platform.python_version()}")
    R = 300_000 if rapido else 1_500_000
    comparar(out, "Witch Hut", "26.3", 3, R, nucleos, 1 if rapido else 3)
    comparar(out, "Witch Hut 1.12", "1.12", 3, R // 2, nucleos, 1 if rapido else 2)
    comparar(out, "Ocean Monument", "26.3", 8, R // 2, nucleos, 1)
    out("\n### Escalado con hilos (Witch Hut 26.3, modo todas)")
    base = None
    for h in sorted({1, 2, 4, nucleos}):
        r = correr("todas", "26.3", 3, R // 2, h)
        base = base or r["dt"]
        out(f"  {h} hilos: {r['dt']:.2f}s  ({r['regiones'] / r['dt']:,.0f} reg/s)  speedup {base / r['dt']:.2f}x")
    with open(os.path.join(ROOT, "bench", "resultados_bench.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
