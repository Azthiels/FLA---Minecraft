"""Parte 1: escaner (equivalencia con el motor anterior, cajas, biomas, lotes, hilos, reanudacion, kill, errores)."""
import json, os, random, subprocess, sys, threading, time

from tests.comun import ROOT, TMP, check, escanear, leer
from sa import datos, nativo
from sa.escaner import Escaneo, ReanudarError, SalidaExisteError, motor, normalizar_cajas


def t_region_span():
    """Supuesto del planificador y del modo grupos: la posicion de una region cae DENTRO de esa region."""
    malos, total = 0, 0
    for v in nativo.VERSIONES:
        mc = nativo.mc_id(v)
        for sid, _ in nativo.ESTRUCTURAS:
            if not nativo.L.sh_supported(sid, mc):
                continue
            rb = nativo.L.sh_region_blocks(sid, mc)
            for seed in (1, 987654321, 0xFFFFFFFFFFFFF000):
                for rx in range(-12, 13):
                    for rz in range(-12, 13):
                        p = nativo.posicion(sid, v, seed, rx, rz)
                        if p:
                            total += 1
                            if p[0] // rb != rx or p[1] // rb != rz:
                                malos += 1
    check("posicion de cada region cae dentro de la region (todas las estructuras/versiones)", malos == 0,
          f"{total:,} posiciones, {malos} fuera")


CASOS = [("3", "26.3", 20000), ("3", "1.12", 20000), ("3", "1.16", 20000), ("1", "1.14", 20000), ("1", "26.3", 20000),
         ("2", "1.18", 20000), ("4", "26.3", 20000), ("5", "1.14", 20000), ("5", "1.16", 20000), ("5", "1.18", 20000),
         ("5", "26.3", 20000), ("6", "26.3", 20000), ("7", "1.16", 20000), ("7", "26.3", 20000), ("8", "1.12", 8000),
         ("8", "1.18", 8000), ("8", "26.3", 8000), ("9", "1.14", 60000), ("9", "1.18", 60000), ("9", "26.3", 60000),
         ("10", "1.14", 20000), ("10", "1.18", 20000), ("10", "26.3", 20000), ("11", "1.16", 20000), ("11", "26.3", 20000),
         ("12", "26.3", 20000), ("13", "26.3", 20000), ("14", "26.3", 1500), ("18", "1.14", 20000), ("18", "1.18", 20000),
         ("18", "26.3", 20000), ("19", "1.16", 20000), ("19", "26.3", 20000), ("21", "1.12", 6000), ("21", "26.3", 6000),
         ("24", "26.3", 20000), ("25", "26.3", 20000), ("26", "26.3", 20000)]


def t_equivalencia():
    """Mismo conjunto de posiciones que el motor anterior (bench/legacy_core.py) sin filtros."""
    import legacy_core as legacy
    for sid, ver, R in CASOS:
        sid = int(sid)
        if not nativo.L.sh_supported(sid, nativo.mc_id(ver)):
            continue
        dim = nativo.dimension(sid, ver)
        Rr = R * 8 if dim == -1 else R               # el motor viejo recibe el radio de border en overworld
        _, _, nuevo = escanear("eq", ver, sid, Rr)
        e = legacy.Escaneo(ver, nativo.parse_seed("12345"), sid, Rr, 10 ** 9, TMP / "old.json", hilos=1)
        e.run()
        a = {(d["x"], d["z"]) for d in nuevo}
        b = {(d["x"], d["z"]) for d in e.resultados}
        check(f"equivalencia posiciones {nativo.nombre_estructura(sid)} {ver} R={R}", a == b and len(nuevo) == len(a),
              f"nuevo={len(a)} viejo={len(b)}")


def t_cajas():
    ver, sid, R = "26.3", 11, 80000          # Ruined Portal: una posicion valida por region (densidad maxima)
    _, _, base = escanear("box_base", ver, sid, R)
    pos = {(d["x"], d["z"]) for d in base}
    rb = nativo.region_bloques(sid, ver)
    assert rb == 640 and len(pos) > 50000

    def esperado(cajas):
        return {(x, z) for x, z in pos if any(a <= x <= c and b <= z <= d for a, b, c, d in cajas)}

    px, pz = sorted(pos)[len(pos) // 2]
    casos = {
        "alineada a limite de region": [(-rb, -rb, rb - 1, rb - 1)],
        "limite de region +-1": [(-rb - 1, -rb - 1, rb, rb)],
        "x1 == x de una estructura (incluye)": [(px - 3000, pz - 3000, px, pz)],
        "x1 == x-1 de una estructura (excluye)": [(px - 3000, pz - 3000, px - 1, pz - 1)],
        "esquina exacta sobre una estructura": [(px, pz, px + 2000, pz + 2000)],
        "1 bloque de ancho": [(px, -R, px, R)],
        "1 solo bloque sobre una estructura": [(px, pz, px, pz)],
        "1 solo bloque vacio": [(px + 1, pz, px + 1, pz)],
        "partida por frontera de region": [(-300, 100, 300, 5000)],
        "solapadas (union)": [(-20000, -20000, 5000, 5000), (0, 0, 30000, 30000), (-100, -50000, 100, 50000)],
        "contenidas una en otra": [(-5000, -5000, 5000, 5000), (-100, -100, 100, 100)],
        "disjuntas": [(-60000, -60000, -30000, -30000), (30000, 30000, 60000, 60000)],
        "mayor que el border (se recorta)": [(-10 ** 8, -10 ** 8, 10 ** 8, 10 ** 8)],
    }
    for nombre, cajas in casos.items():
        e, r, rec = escanear("box", ver, sid, R, cajas=cajas, tile=8)
        got = [(d["x"], d["z"]) for d in rec]
        cl = normalizar_cajas(cajas, R)
        check(f"bounding box: {nombre}", set(got) == esperado(cl) and len(got) == len(set(got)),
              f"{len(got)} registros, {e.regiones_total} regiones")
    e, _, _ = escanear("box_small", ver, sid, R, cajas=[(0, 0, 2 * rb - 1, 2 * rb - 1)])
    check("bounding box: solo se procesan las regiones que tocan la caja", e.regiones_total == 4, f"{e.regiones_total} regiones")
    e, _, _ = escanear("box_small2", ver, sid, R, cajas=[(rb - 1, 0, rb, 0)])
    check("bounding box: caja a caballo de dos regiones procesa las dos", e.regiones_total == 2, f"{e.regiones_total} regiones")
    try:
        Escaneo(ver, 1, sid, 1000, TMP / "x", cajas=[(5000, 5000, 6000, 6000)])
        check("caja totalmente fuera del border se rechaza", False)
    except ValueError:
        check("caja totalmente fuera del border se rechaza", True)
    e = Escaneo("26.3", 1, 18, 80000, TMP / "nether", sobrescribir=True)
    check("nether: limite 1:8", e.limite == 10000 and e.cajas == [(-10000, -10000, 10000, 10000)])


def t_biomas():
    ver, sid, R = "26.3", 5, 30000
    _, _, full = escanear("bio_full", ver, sid, R)
    validos = dict((n, i) for i, n in nativo.biomas_validos(sid, ver))
    bio_full = {d["biome"] for d in full}
    check("todo registro tiene un bioma valido segun las reglas", bio_full <= set(validos), str(sorted(bio_full)))
    elegido = sorted(bio_full)[:2]
    _, _, sub = escanear("bio_sub", ver, sid, R, biomas=[validos[n] for n in elegido])
    exp = [d for d in full if d["biome"] in elegido]
    check(f"filtro de varios biomas {elegido}", sorted(map(json.dumps, sub)) == sorted(map(json.dumps, exp)), f"{len(sub)} de {len(full)}")
    _, _, todos = escanear("bio_all", ver, sid, R, biomas=list(validos.values()))
    check("seleccionar todos los biomas validos == sin filtro", len(todos) == len(full))
    _, _, vacio = escanear("bio_bad", ver, sid, R, biomas=[0])          # ocean: invalido para Village
    check("un bioma no valido no genera estructuras (el filtro no sustituye las reglas)", len(vacio) == 0)


def t_lotes():
    e, r, rec = escanear("lotes", "26.3", 11, 40000, lote=50, tile=8, flush_s=1e9)
    n = len(rec)
    check("datos: la cantidad de registros coincide", n == e.escritas == r["encontradas"], f"{n} registros")
    check("datos: tamano del archivo = cabecera + 12 bytes por registro",
          os.path.getsize(e.rutas["datos"]) == datos.CABECERA + 12 * n)
    check("escritura por lotes de 50 (todas las escrituras salvo la ultima >= 50)",
          e.escritura_min_previa is None or e.escritura_min_previa >= 50, f"min={e.escritura_min_previa}, escrituras={e.n_escrituras}")
    check("muchas menos escrituras que registros", e.n_escrituras <= n // 50 + 2, f"{e.n_escrituras} escrituras / {n} registros")
    e2, _, rec2 = escanear("lotes2", "26.3", 11, 40000, lote=7, tile=8, flush_s=1e9)
    check("lote configurable (7)", (e2.escritura_min_previa is None or e2.escritura_min_previa >= 7) and len(rec2) == n)
    e3, _, rec3 = escanear("lotes3", "26.3", 11, 40000, lote=10 ** 6, tile=8, flush_s=0.0)
    check("flush periodico escribe aunque el buffer no llegue al lote", len(rec3) == n and e3.n_escrituras > 1)


def t_hilos():
    base = None
    for h in (1, 2, 4, 7):
        for modo in ("todas", "grupos"):
            e, r, rec = escanear("hilos", "26.3", 5, 40000, hilos=h, tile=8, modo=modo)
            s = sorted((d["x"], d["z"]) for d in rec)
            if base is None or modo not in base:
                base = base or {}
                base.setdefault(modo, s)
            check(f"{h} hilos ({modo}): mismos resultados, sin duplicados ni regiones repetidas",
                  s == base[modo] and len(s) == len(set(s)) and e.regiones_hechas == e.regiones_total and e.estado == "completado")


def t_reanudar():
    ver, sid, R = "26.3", 5, 60000
    for modo in ("todas", "grupos"):
        _, _, base = escanear("rb" + modo, ver, sid, R, tile=8, modo=modo)
        base_set = sorted((d["x"], d["z"]) for d in base)
        nombre = "rc" + modo
        kw = dict(tile=8, hilos=2, lote=10, ckpt_s=0.05, flush_s=0.05, modo=modo)
        e = Escaneo(ver, nativo.parse_seed("12345"), sid, R, TMP / nombre, sobrescribir=True, **kw)

        def parar():
            while e.tiles_confirmados < e.tiles_total // 3:
                time.sleep(0.005)
            e.stop.set()
        threading.Thread(target=parar, daemon=True).start()
        r1 = e.run()
        check(f"[{modo}] parada controlada: estado interrumpido y progreso parcial",
              r1["estado"] == "interrumpido" and 0 < r1["regiones"] < r1["regiones_total"], f"{r1['regiones']}/{r1['regiones_total']}")
        e2 = Escaneo(ver, nativo.parse_seed("12345"), sid, R, TMP / nombre, **kw)
        r2 = e2.run()
        fin = sorted((d["x"], d["z"]) for d in leer(e2.rutas["datos"]))
        check(f"[{modo}] reanudacion: completa y == escaneo sin interrupciones (sin duplicados)",
              r2["estado"] == "completado" and fin == base_set and len(fin) == len(set(fin)), f"{len(fin)} vs {len(base_set)}")
        check(f"[{modo}] reanudacion: no repite regiones ya confirmadas", e2.regiones_sesion < r2["regiones_total"])
        otros = [("seed", dict(seed=1)), ("biomas", dict(biomas=[1])), ("cajas", dict(cajas=[(0, 0, 9999, 9999)])),
                 ("modo", dict(modo="todas" if modo == "grupos" else "grupos"))]
        if modo == "grupos":
            otros.append(("radio de grupo", dict(radio_grupo=100)))
        for campo, kw2 in otros:
            seed_ = kw2.pop("seed", nativo.parse_seed("12345"))
            try:
                Escaneo(ver, seed_, sid, R, TMP / nombre, **{**kw, **kw2}).run()
                check(f"[{modo}] reanudar con {campo} distinto se rechaza", False)
            except ReanudarError:
                check(f"[{modo}] reanudar con {campo} distinto se rechaza", True)
        try:
            Escaneo(ver, nativo.parse_seed("12345"), sid, R, TMP / nombre, reanudar=False, **kw).run()
            check(f"[{modo}] salida existente sin reanudar/sobrescribir se rechaza", False)
        except SalidaExisteError:
            check(f"[{modo}] salida existente sin reanudar/sobrescribir se rechaza", True)
        e4 = Escaneo(ver, nativo.parse_seed("12345"), sid, R, TMP / nombre, **kw)
        r4 = e4.run()
        check(f"[{modo}] reanudar un escaneo completado no procesa nada",
              r4["estado"] == "completado" and e4.regiones_sesion == 0 and len(leer(e4.rutas["datos"])) == len(base_set))


WORKER = r'''
import sys; sys.path.insert(0, %r)
from sa import nativo
from sa.escaner import Escaneo
e = Escaneo("26.3", nativo.parse_seed("12345"), 5, 250000, sys.argv[1], tile=8, hilos=2, lote=5, ckpt_s=0.05, flush_s=0.02, modo="todas")
e.run()
'''


def t_kill():
    """Muerte real del proceso (TerminateProcess / SIGKILL) varias veces MIENTRAS escanea, reanudando cada vez."""
    ver, sid, R = "26.3", 5, 250000
    _, _, base = escanear("kb", ver, sid, R, tile=8, hilos=2)
    base_set = sorted((d["x"], d["z"]) for d in base)
    salida = str(TMP / "kill")
    codigo = WORKER % str(ROOT)
    random.seed(7)
    kills = 0
    for _ in range(7):
        p = subprocess.Popen([sys.executable, "-c", codigo, salida], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(random.uniform(0.6, 1.6))
        if p.poll() is None:
            p.kill(); kills += 1
        p.wait()
    meta_mid = json.load(open(salida + ".meta.json"))
    check("kill: se mato el proceso a mitad de escaneo al menos 5 veces", kills >= 5 and meta_mid["status"] != "completado",
          f"kills={kills}")
    with open(salida + ".sab", "ab") as f:              # muerte a mitad de escritura: registro parcial
        f.write(b"\x01\x02\x03\x04\x05")
    r = subprocess.run([sys.executable, "-c", codigo, salida], capture_output=True, text=True)
    fin = sorted((d["x"], d["z"]) for d in leer(salida + ".sab"))
    meta = json.load(open(salida + ".meta.json"))
    check(f"kill x{kills} + registro parcial + reanudaciones: resultado == escaneo limpio, sin duplicados",
          fin == base_set and len(fin) == len(set(fin)) and meta["status"] == "completado" and meta["resumed"],
          f"{len(fin)} vs {len(base_set)} {r.stderr[-200:]}")


def t_grande():
    """Muchos registros: el motor NO acumula resultados en RAM (RSS pico en un subproceso limpio)."""
    codigo = ("import sys, tempfile; sys.path.insert(0, %r)\nfrom sa import util\nfrom sa.escaner import Escaneo\n"
              "e = Escaneo('26.3', 5, 11, int(sys.argv[1]), tempfile.mkdtemp() + '/r', tile=64, hilos=2, modo='todas'); e.run()\n"
              "print(e.escritas, round(util.ram_pico_mb()), e.n_escrituras)\n") % str(ROOT)
    res = []
    for R in (50000, 400000):
        o = subprocess.run([sys.executable, "-c", codigo, str(R)], capture_output=True, text=True).stdout.split()
        res.append(tuple(int(x) for x in o))
    (n1, m1, _), (n2, m2, w2) = res
    check("archivo grande: 64x mas registros, RAM pico casi igual", n2 > 50 * n1 and m2 < m1 + 30,
          f"{n1:,} regs -> {m1} MB ; {n2:,} regs -> {m2} MB ; escrituras={w2}")


def t_error():
    """Error controlado en un hilo: se guardan los pendientes y el estado queda en 'error' (checkpoint valido)."""
    e = Escaneo("26.3", 5, 5, 60000, TMP / "err", tile=8, hilos=2, sobrescribir=True, lote=3, modo="todas")
    orig = nativo.L.sh_scan_tile
    cnt = {"n": 0}

    class Boom:
        def __call__(self, *a):
            cnt["n"] += 1
            if cnt["n"] == 20:
                raise RuntimeError("fallo simulado")
            return orig(*a)
    motor.L = type("LL", (), {"sh_scan_tile": Boom(), "__getattr__": lambda s, k: getattr(nativo.L, k)})()
    try:
        r = e.run()
    finally:
        motor.L = nativo.L
    n = len(leer(e.rutas["datos"]))
    meta = json.load(open(e.rutas["meta"]))
    check("error controlado: estado=error, pendientes guardados, metadatos coherentes",
          r["estado"] == "error" and meta["status"] == "error" and n == meta["counts"]["structures_found"], f"{n} registros; {r['error']}")


PRUEBAS = [t_region_span, t_cajas, t_biomas, t_lotes, t_hilos, t_reanudar, t_kill, t_error, t_grande, t_equivalencia]
