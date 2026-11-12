"""Partes 2 y 3 + modo grupos: escaner(grupos) == escaner(todas) + limpiador, geometria exacta, analizador, formato."""
import csv, itertools, json, math, random

import numpy as np

from tests.comun import TMP, check, escanear, leer
from sa import analizador, datos, estructuras, geometria, limpiador, nativo

CASOS_GRUPOS = [  # (sid, version, radio border, kw extra)
    (3, "26.3", 300000, {}), (3, "1.12", 200000, {}), (3, "26.3", 200000, {"radio_grupo": 64}),
    (8, "26.3", 120000, {}), (11, "26.3", 40000, {}), (14, "26.3", 2500, {}), (18, "26.3", 30000, {}),
    (5, "1.18", 60000, {}), (1, "26.3", 120000, {}), (10, "26.3", 80000, {"radio_grupo": 200}),
    (3, "26.3", 300000, {"cajas": [(-200000, -200000, 30000, 30000), (0, 0, 250000, 250000), (-5000, -300000, 5000, 300000)]}),
    (5, "26.3", 60000, {"biomas": None}),   # se reemplaza por un subconjunto de biomas validos
]


def t_grupos_equivalencia():
    """El modo grupos (en C) da EXACTAMENTE lo mismo que escanear todo y pasar el limpiador."""
    for sid, ver, R, kw in CASOS_GRUPOS:
        kw = dict(kw)
        if "biomas" in kw:
            kw["biomas"] = [i for i, _ in nativo.biomas_validos(sid, ver)][:2]
        e1, r1, todas = escanear("g_todas", ver, sid, R, modo="todas", hilos=4, **kw)
        e2, r2, grp = escanear("g_grp", ver, sid, R, modo="grupos", hilos=4, **kw)
        res = limpiador.limpiar(e1.rutas["datos"], TMP / "g_limpio", radio=e2.radio_grupo, lado=e2.lado)
        lim = leer(TMP / "g_limpio.sab")
        a = sorted((d["x"], d["z"], d["biome"]) for d in grp)
        b = sorted((d["x"], d["z"], d["biome"]) for d in lim)
        st = r2["stats"]
        nombre = f"{nativo.nombre_estructura(sid)} {ver} R={R} radio={e2.radio_grupo} lado={e2.lado}" + \
            (" cajas" if "cajas" in kw else "") + (" biomas" if "biomas" in kw else "")
        check(f"grupos == todas + limpiador: {nombre}", a == b and len(a) == len(set(a)),
              f"todas={len(todas):,} grupos={len(a):,} limpio={len(b):,} | bioma consultado "
              f"{st['viable_calls']:,} vs {r1['stats']['viable_calls']:,}")


def t_geometria():
    random.seed(3)
    malos = 0
    for _ in range(20000):                 # el criterio de pares es exacto para cuadrados iguales
        lado = random.choice([1, 9, 16, 21, 58])
        R = random.choice([24, 64, 128, 200])
        x2, z2 = random.randint(-2 * R, 2 * R), random.randint(-2 * R, 2 * R)
        r = geometria.circulo_minimo(geometria.esquinas([(0, 0), (x2, z2)], 0, lado))[2]
        if geometria.par_ok(0, 0, x2, z2, R, lado) != (r <= R + 1e-9):
            malos += 1
    check("par_ok == circulo minimo de las 8 esquinas (20 000 pares al azar)", malos == 0, f"{malos} distintos")
    malos = 0
    for _ in range(3000):                  # circulo minimo contra fuerza bruta
        pts = [(random.uniform(-100, 100), random.uniform(-100, 100)) for _ in range(random.randint(2, 12))]
        cx, cz, r = geometria.circulo_minimo(pts)
        ok = all(math.hypot(x - cx, z - cz) <= r + 1e-6 for x, z in pts)
        mejor = min(c[2] for c in [geometria._circ2(a, b) for a, b in itertools.combinations(pts, 2)] +
                    [geometria._circ3(a, b, c) for a, b, c in itertools.combinations(pts, 3)]
                    if all(math.hypot(x - c[0], z - c[1]) <= c[2] + 1e-6 for x, z in pts))
        if not ok or abs(mejor - r) > 1e-6:
            malos += 1
    check("circulo minimo: contiene todo y es el minimo (fuerza bruta)", malos == 0, f"{malos} fallos")
    afk = geometria.punto_afk([(0, 0), (160, 0), (0, 160), (160, 160)], 128, 0, 9)
    pts = geometria.esquinas([(0, 0), (160, 0), (0, 160), (160, 160)], 0, 9)
    check("punto AFK: todas las esquinas a <= radio desde el centro del bloque",
          afk is not None and all(math.hypot(x - afk[0] - 0.5, z - afk[1] - 0.5) <= 128 for x, z in pts), str(afk))
    check("Witch Hut 26.3 radio 128: maximo teorico 4 (una por region de 512)",
          estructuras.maximo_teorico(3, "26.3", 128, 9) == 4)


def _sab(nombre, puntos, sid=3, ver="26.3"):
    a = np.zeros(len(puntos), datos.DTYPE)
    a["x"] = [p[0] for p in puntos]; a["z"] = [p[1] for p in puntos]; a["b"] = 6
    datos.escribir(TMP / nombre, a, {"structure": {"id": sid, "name": "swamp_hut"}, "minecraft_version": ver,
                                     "seed": 1, "status": "completado", "biome_names": {"6": "swamp"}})
    return TMP / (nombre + ".sab")


def t_analizador():
    quad = [(0, 0), (160, 0), (0, 160), (160, 160)]
    triple = [(10000, 0), (10150, 0), (10075, 140)]
    doble = [(-20000, 5000), (-19800, 5000)]
    sueltas = [(50000, 50000), (-50000, 3000), (3000, -70000)]
    casi = [(30000, 30000), (30000 + 248, 30000)]          # (248+9) = 257 > 256: no entran
    p = _sab("ana", quad + triple + doble + sueltas + casi)
    r = analizador.analizar(p, radio=128)
    check("analizador: cuenta 1 cuadruple, 1 triple, 1 doble (maximales, sin contar subgrupos)",
          r["conteo"] == {"4": 1, "3": 1, "2": 1}, str(r["conteo"]))
    check("analizador: recomienda la cuadruple con AFK cerca del centro",
          r["mejor_tam"] == 4 and abs(r["recomendados"][0]["afk"][0] - 84) <= 1 and abs(r["recomendados"][0]["afk"][1] - 84) <= 1,
          str(r["recomendados"][0]["afk"]))
    check("analizador: guarda .grupos.json y .grupos.csv",
          datos.rutas(p)["grupos"].exists() and datos.rutas(p)["csv"].exists() and
          len(json.loads(datos.rutas(p)["grupos"].read_text(encoding="utf-8"))["grupos"]) == 3)
    r2 = analizador.analizar(_sab("ana2", triple + doble + sueltas), radio=128)
    check("analizador: sin cuadruples recomienda la triple", r2["mejor_tam"] == 3 and r2["conteo"] == {"3": 1, "2": 1})
    r3 = analizador.analizar(_sab("ana3", sueltas + casi), radio=128)
    check("analizador: sin grupos lo dice (0 grupos)", r3["mejor_tam"] == 0 and not r3["grupos"])
    # cadena A-B-C donde A y C no entran juntas: dos dobles, no una triple
    r4 = analizador.analizar(_sab("ana4", [(0, 0), (200, 0), (400, 0)]), radio=128)
    check("analizador: cadena A-B-C (A y C lejos) -> 2 dobles", r4["conteo"] == {"2": 2}, str(r4["conteo"]))
    lim = limpiador.limpiar(_sab("lim", quad + triple + doble + sueltas + casi), TMP / "lim_out", radio=128)
    check("limpiador: descarta solo las aisladas (3 sueltas + 2 casi)", lim["quedan"] == 9 and lim["descartadas"] == 5,
          f"quedan {lim['quedan']}")


def t_formato():
    e, r, rec = escanear("fmt", "26.3", 5, 30000, modo="todas")
    arr, meta = datos.leer(e.rutas["datos"])
    jl = TMP / "fmt_export.jsonl"
    datos.exportar_jsonl(arr, meta, jl)
    (TMP / "fmt_export.meta.json").write_text(json.dumps({"minecraft_version": "26.3"}), encoding="utf-8")
    arr2, meta2 = datos.leer(jl)
    check("formato: .sab -> .jsonl -> lectura da los mismos registros (bioma incluido)",
          np.array_equal(np.asarray(arr), arr2) and len(arr) == len(rec), f"{len(arr)} registros")
    check("formato: meta guarda los nombres de bioma y el modo", meta["biome_names"] and meta["mode"] == "todas")
    lim_jl = limpiador.limpiar(jl, TMP / "fmt_lim_jl", radio=128, lado=16)
    lim_sab = limpiador.limpiar(e.rutas["datos"], TMP / "fmt_lim_sab", radio=128, lado=16)
    check("limpiador: mismo resultado leyendo .jsonl viejo o .sab", lim_jl["quedan"] == lim_sab["quedan"])


def t_clima_cobertura():
    """Supuesto del prefiltro: las hojas de superficie cubren toda la caja de clima (si falla, se apaga solo)."""
    from sa import clima
    for v in [x for x in nativo.VERSIONES if nativo.es_118_o_mas(x)]:
        ok = clima.cobertura_completa(v)
        check(f"clima {v}: cobertura completa de la capa 0 -> prefiltro activo", ok,
              f"{clima.huerfanas(v)} hojas sin gemela (zonas con calculo completo)")


CASOS_CLIMA = [(3, "26.3", 120000), (3, "1.18", 120000), (3, "1.21.4", 120000), (3, "1.20", 80000), (1, "26.3", 60000),
               (2, "1.19", 60000), (4, "26.3", 40000), (6, "26.3", 25000), (7, "1.21.11", 25000), (14, "26.3", 1200),
               (24, "26.3", 30000), (3, "26.2", 60000), (4, "26.2", 40000), (1, "26.2", 60000), (6, "26.2", 25000),
               (3, "1.19.2", 60000), (3, "1.21.5", 60000), (3, "26.1", 60000)]


def t_clima_equivalencia():
    """Prefiltro de clima on/off: mismos registros (con y sin modo grupos, con filtro de biomas)."""
    for sid, ver, R in CASOS_CLIMA:
        for modo in ("todas", "grupos"):
            e0, r0, a = escanear("c_off", ver, sid, R, modo=modo, hilos=4, clima=False)
            e1, r1, b = escanear("c_on", ver, sid, R, modo=modo, hilos=4, clima=True)
            a, b = sorted(map(json.dumps, a)), sorted(map(json.dumps, b))      # con hilos el orden varia
            st = r1["stats"]
            check(f"clima on == off: {nativo.nombre_estructura(sid)} {ver} {modo} (prefiltro {'si' if e1.clima else 'no'})",
                  a == b, f"{len(a):,} registros | bioma completo {st['viable_calls']:,} vs {r0['stats']['viable_calls']:,}, "
                          f"clima descarto {st['climate_rejected']:,}")
    validos = [i for i, _ in nativo.biomas_validos(1, "26.3")]
    for sub in (validos[:1], validos[1:3]):
        _, _, a = escanear("cb_off", "26.3", 1, 60000, biomas=sub, clima=False, hilos=4)
        _, _, b = escanear("cb_on", "26.3", 1, 60000, biomas=sub, clima=True, hilos=4)
        check(f"clima on == off con filtro de biomas {sub}", sorted(map(json.dumps, a)) == sorted(map(json.dumps, b)),
              f"{len(a)} registros")


def t_afk_vectorizado():
    """afk_pares (numpy) == punto_afk (escalar) bit a bit, con distintos lados, offsets y radios."""
    random.seed(11)
    malos, n = 0, 0
    for lado, off, R in ((9, 0, 128), (16, 0, 128), (58, -21, 128), (21, 0, 100), (1, 0, 24), (16, 0, 200)):
        x1 = [random.randint(-3 * 10 ** 7, 3 * 10 ** 7) for _ in range(4000)]
        z1 = [random.randint(-3 * 10 ** 7, 3 * 10 ** 7) for _ in range(4000)]
        x2 = [a + random.randint(-2 * R, 2 * R) for a in x1]; z2 = [a + random.randint(-2 * R, 2 * R) for a in z1]
        bx, bz, d2, ok = geometria.afk_pares(np.array(x1), np.array(z1), np.array(x2), np.array(z2), R, off, lado)
        for k in range(len(x1)):
            n += 1
            ref = geometria.punto_afk([(x1[k], z1[k]), (x2[k], z2[k])], R, off, lado)
            got = (int(bx[k]), int(bz[k]), math.sqrt(d2[k]), R - math.sqrt(d2[k])) if ok[k] else None
            if ref != got:
                malos += 1
    check("AFK de pares vectorizado == escalar (bit a bit)", malos == 0, f"{malos} distintos de {n:,}")


def t_subgrupos():
    """Subgrupos maximales de un clique que no entra: ramificar por el soporte == fuerza bruta (todos los subconjuntos)."""
    random.seed(9)
    malos = 0
    for caso in range(300):
        lado, R = random.choice([(9, 128), (16, 128), (21, 100), (1, 40)])
        k = random.randint(3, 9)
        pts = list({(random.randint(0, 2 * R), random.randint(0, 2 * R)) for _ in range(k)})
        x = np.array([p[0] for p in pts]); z = np.array([p[1] for p in pts]); b = np.zeros(len(pts), int)
        ids = tuple(range(len(pts)))
        if geometria.punto_afk(pts, R, 0, lado):
            continue                                     # el clique entero entra: no aplica
        bruto = []
        for t in range(len(ids) - 1, 1, -1):
            for sub in itertools.combinations(ids, t):
                if not any(set(sub) <= s for s in bruto) and geometria.punto_afk([pts[i] for i in sub], R, 0, lado):
                    bruto.append(set(sub))
        got = [set(g["_ids"]) for g in analizador._subgrupos(ids, x, z, b, R, 0, lado, {})]
        got = [s for s in got if not any(s < o for o in got)]
        if sorted(map(sorted, got)) != sorted(map(sorted, bruto)):
            malos += 1
    check("subgrupos maximales (ramificar por soporte) == fuerza bruta (300 casos)", malos == 0, f"{malos} distintos")


def _firma(res):
    return sorted((g["tam"], tuple(g["afk"]), g["margen"], tuple(sorted((e["x"], e["z"]) for e in g["estructuras"])))
                  for g in res["grupos"])


def t_analizador_rapido():
    """Analizador rapido (dobles aisladas en numpy) == todo por el grafo, en estructuras de densidad muy distinta."""
    casos = [("swamp_hut grupos", "26.3", 3, 300000, dict(modo="grupos"), {}),
             ("village todas", "26.3", 5, 40000, {}, {}),
             ("monument todas", "26.3", 8, 60000, {}, {}),
             ("buried_treasure todas (denso)", "26.3", 14, 4000, {}, {"radio": 128}),
             ("ruined_portal todas radio 400", "26.3", 11, 20000, {}, {"radio": 400}),
             ("pillager_outpost radio 300", "26.3", 10, 60000, {}, {"radio": 300}),
             ("fortress nether", "26.3", 18, 20000, {}, {})]
    for nombre, ver, sid, R, kw, ka in casos:
        e, _, _ = escanear("ar", ver, sid, R, hilos=4, **kw)
        a = analizador.analizar(e.rutas["datos"], top=10 ** 9, rapido=True, guardar=False, **ka)
        b = analizador.analizar(e.rutas["datos"], top=10 ** 9, rapido=False, guardar=False, **ka)
        check(f"analizador rapido == grafo: {nombre}", a["conteo"] == b["conteo"] and _firma(a) == _firma(b),
              f"{a['conteo']} | {a['segundos']:.2f}s vs {b['segundos']:.2f}s")
    random.seed(5)        # sintetico denso (~3 por circulo de activacion, mas que cualquier estructura real)
    pts = list({(random.randint(0, 5000), random.randint(0, 5000)) for _ in range(1000)})
    p = _sab("denso", pts)
    a = analizador.analizar(p, radio=128, top=10 ** 9, rapido=True, guardar=False)
    b = analizador.analizar(p, radio=128, top=10 ** 9, rapido=False, guardar=False)
    check("analizador rapido == grafo: sintetico denso", a["conteo"] == b["conteo"] and _firma(a) == _firma(b), str(a["conteo"]))
    r = analizador.analizar(p, radio=128, top=5)
    filas = open(datos.rutas(p)["csv"], encoding="utf-8").read().splitlines()
    check("CSV tiene TODOS los grupos y el JSON solo el top",
          len(filas) - 1 == r["total_grupos"] and len(r["grupos"]) == 5 and
          all(len(next(csv.reader([f]))) == 6 for f in filas), f"{len(filas) - 1} filas, total {r['total_grupos']}")


PRUEBAS = [t_geometria, t_afk_vectorizado, t_subgrupos, t_analizador, t_analizador_rapido, t_formato, t_clima_cobertura,
           t_clima_equivalencia, t_grupos_equivalencia]
