"""Parte 3: analizador de grupos.

Con las estructuras que quedan (salida del escaner en modo grupos o del limpiador) busca TODAS las agrupaciones
que se pueden activar a la vez desde un punto AFK: las cajas de todas tienen que entrar en el radio de activacion
(128 por defecto) alrededor del jugador.

  1. pares compatibles (mismo criterio exacto que el limpiador)
  2. cliques maximales del grafo de pares (Bron-Kerbosch): candidatos a grupo
  3. cada candidato se valida con el circulo minimo de las esquinas de todas las cajas y se busca el mejor bloque
     para el jugador; si el clique entero no entra, se prueban sus subconjuntos mas grandes
  4. solo se informan grupos maximales (una cuadruple no se cuenta tambien como 4 triples)

Resultado: cuantos grupos hay de cada tamano, el maximo teorico para esa estructura, y una recomendacion: el
tamano mas grande que exista (cuadruple, quintuple...) o, si no hay, la mejor triple o doble.
"""
import csv, json, math, sys, time
from collections import defaultdict
from itertools import combinations

import numpy as np

from sa import config, datos, estructuras, geometria, util
from sa.limpiador import pares, parametros

NOMBRES = {2: "doble", 3: "triple", 4: "cuadruple", 5: "quintuple", 6: "sextuple"}


def nombre_tam(n):
    return NOMBRES.get(n, f"{n}-uple")


def _cliques(adj):
    """Cliques maximales (Bron-Kerbosch con pivote, iterativo). Los componentes son chicos."""
    out = []
    for v in sorted(adj):
        # solo cliques cuyo vertice minimo es v: P = vecinos > v, X = vecinos < v
        pila = [({v}, {u for u in adj[v] if u > v}, {u for u in adj[v] if u < v})]
        while pila:
            R, P, X = pila.pop()
            if not P and not X:
                if len(R) >= 2:
                    out.append(tuple(sorted(R)))
                continue
            piv = max(P | X, key=lambda u: len(adj[u] & P))
            for u in list(P - adj[piv]):
                pila.append((R | {u}, P & adj[u], X & adj[u]))
                P = P - {u}
                X = X | {u}
    return out


def _grupo(ids, x, z, b, radio, off, lado, nb):
    miembros = [(int(x[i]), int(z[i])) for i in ids]
    afk = geometria.punto_afk(miembros, radio, off, lado)
    if afk is None:
        return None
    bx, bz, dmax, margen = afk
    return {"tam": len(ids), "afk": [bx, bz], "margen": round(margen, 2), "dist_max": round(dmax, 2),
            "dist_origen": round(math.sqrt((bx + 0.5) ** 2 + (bz + 0.5) ** 2), 1),
            "estructuras": [{"x": mx, "z": mz, "bioma": nb.get(int(b[i]), f"id_{int(b[i])}")}
                            for (mx, mz), i in zip(miembros, ids)],
            "_ids": tuple(ids)}


def _soporte(ids, x, z, off, lado):
    """Estructuras con alguna esquina sobre el borde del circulo minimo (las que lo fijan: 2 o 3, mas si hay
    puntos cocirculares). Devuelve (radio_minimo, soporte)."""
    pts, dueno = [], []
    for m in ids:
        for p in geometria.esquinas([(int(x[m]), int(z[m]))], off, lado):
            pts.append(p); dueno.append(m)
    cx, cz, rad = geometria.circulo_minimo(pts)
    sop = {d for (px, pz), d in zip(pts, dueno) if math.hypot(px - cx, pz - cz) >= rad - 1e-6}
    return rad, sop


def _subgrupos(cl, x, z, b, radio, off, lado, nb):
    """Subconjuntos maximales que SI entran, de un clique que no entra entero.
    Propiedad: si S no entra y su circulo minimo (radio > R) lo fijan las cajas del soporte, todo subconjunto
    que contenga el soporte entero tiene un circulo minimo >= ese, asi que tampoco entra: hay que sacar al menos
    una caja del soporte. Se ramifica solo sobre esas (2-3) en vez de probar todos los subconjuntos.
    Si el circulo minimo entra pero ningun BLOQUE sirve (margen de fracciones de bloque), se ramifica sobre todas."""
    vistos, encontrados = set(), []
    pila = [tuple(cl)]
    while pila:
        S = pila.pop()
        if S in vistos or len(S) < 2:
            continue
        vistos.add(S)
        if any(set(S) <= f for f in encontrados):
            continue
        if S != tuple(cl):
            g = _grupo(S, x, z, b, radio, off, lado, nb)
            if g:
                encontrados.append(set(S))
                yield g
                continue
        rad, sop = _soporte(S, x, z, off, lado)
        quitar = sop if rad > radio + 1e-9 else S
        for m in quitar:
            pila.append(tuple(v for v in S if v != m))


class Dobles:
    """Grupos de 2 en arrays (pueden ser millones): indices de las dos estructuras + punto AFK."""

    def __init__(self, i, j, bx, bz, d2):
        self.i, self.j, self.bx, self.bz, self.d2 = i, j, bx, bz, d2

    def __len__(self):
        return len(self.i)

    @staticmethod
    def unir(partes):
        partes = [p for p in partes if len(p)]
        if not partes:
            e = np.zeros(0, np.int64)
            return Dobles(e, e, e, e, np.zeros(0))
        return Dobles(*(np.concatenate([getattr(p, k) for p in partes]) for k in ("i", "j", "bx", "bz", "d2")))

    def tomar(self, idx):
        return Dobles(self.i[idx], self.j[idx], self.bx[idx], self.bz[idx], self.d2[idx])

    def dist_origen(self):
        return np.sqrt((self.bx + 0.5) ** 2 + (self.bz + 0.5) ** 2)

    def ordenar(self, orden):
        dist = self.dist_origen()
        k = np.lexsort((self.d2, dist)) if orden == "distancia" else np.lexsort((dist, self.d2))
        return self.tomar(k)

    def dicts(self, x, z, b, nb, radio, desde=0, hasta=None):
        out = []
        for k in range(desde, min(len(self), hasta if hasta is not None else len(self))):
            i, j = int(self.i[k]), int(self.j[k])
            bx, bz = int(self.bx[k]), int(self.bz[k])
            d = math.sqrt(float(self.d2[k]))
            out.append({"tam": 2, "afk": [bx, bz], "margen": round(radio - d, 2), "dist_max": round(d, 2),
                        "dist_origen": round(math.sqrt((bx + 0.5) ** 2 + (bz + 0.5) ** 2), 1),
                        "estructuras": [{"x": int(x[m]), "z": int(z[m]), "bioma": nb.get(int(b[m]), f"id_{int(b[m])}")}
                                        for m in (i, j)]})
        return out


def analizar(entrada, radio=None, lado=None, minimo=2, orden="distancia", progreso=None, guardar=True,
             top=2000, rapido=True):
    """rapido=True: los pares cuyas dos estructuras no tienen ninguna otra vecina (grado 1) son dobles maximales
    seguras (no hay tercera con la que formar nada) y se resuelven en bloque con numpy; el grafo y la busqueda
    de cliques solo se arman con las estructuras de grado >= 2. rapido=False pasa todo por el grafo (referencia
    para los tests). Mismo resultado en los dos casos, para cualquier estructura."""
    t0 = time.time()
    prog = progreso or (lambda f, txt="": None)
    prog(0.0, "leyendo")
    arr, meta = datos.leer(entrada, progreso=lambda f: prog(0.3 * f, "leyendo"))
    r, l, off, caja = parametros(meta, radio, lado)
    x = np.asarray(arr["x"]); z = np.asarray(arr["z"]); b = np.asarray(arr["b"])
    nb = meta.get("_biomas", {})
    prog(0.3, "buscando pares")
    i, j = pares(x, z, r, l)
    npares = len(i)
    prog(0.45, "dobles aisladas")
    if rapido and len(i):
        grado = np.bincount(i, minlength=len(x)) + np.bincount(j, minlength=len(x))
        simple = (grado[i] == 1) & (grado[j] == 1)
    else:
        simple = np.zeros(len(i), bool)
    si, sj = i[simple], j[simple]
    bx, bz, d2, ok = geometria.afk_pares(x[si], z[si], x[sj], z[sj], r, off, l)
    dobles_simples = Dobles(si[ok], sj[ok], bx[ok], bz[ok], d2[ok])
    i, j = i[~simple], j[~simple]                    # el resto (grado >= 2): grafo + cliques
    del simple, bx, bz, d2, ok
    prog(0.55, "armando grupos")
    adj = defaultdict(set)
    for a, c in zip(i.tolist(), j.tolist()):
        adj[a].add(c); adj[c].add(a)
    candidatos = _cliques(adj)
    grupos = {}
    for k, cl in enumerate(candidatos):
        if k % 20000 == 0:
            prog(0.55 + 0.35 * k / max(1, len(candidatos)), "validando grupos")
        g = _grupo(cl, x, z, b, r, off, l, nb)
        if g:
            grupos[g["_ids"]] = g
            continue
        for g in _subgrupos(cl, x, z, b, r, off, l, nb):   # el clique entero no entra
            grupos[g["_ids"]] = g
    # maximalidad global: descartar grupos contenidos en otro mas grande
    por_miembro = defaultdict(list)
    for ids in grupos:
        for m in ids:
            por_miembro[m].append(ids)
    grandes, dobles_grafo = [], []                   # grandes = 3+ (dicts, pocos); dobles del grafo -> arrays
    for ids, g in grupos.items():
        s = set(ids)
        if any(len(o) > len(ids) and s <= set(o) for o in por_miembro[ids[0]]):
            continue
        if g["tam"] >= 3 and g["tam"] >= minimo:
            g.pop("_ids", None)
            grandes.append(g)
        elif g["tam"] == 2:
            dobles_grafo.append((ids[0], ids[1], g["afk"][0], g["afk"][1], g["dist_max"]))
    del grupos, por_miembro, adj
    if dobles_grafo:
        # recalculo exacto de d2 (el dict tiene dist_max redondeado) con la misma funcion vectorizada
        di = np.array([t[0] for t in dobles_grafo], np.int64); dj = np.array([t[1] for t in dobles_grafo], np.int64)
        bx, bz, d2, _ = geometria.afk_pares(x[di], z[di], x[dj], z[dj], r, off, l)
        dobles_grafo = Dobles(di, dj, bx, bz, d2)
    else:
        dobles_grafo = Dobles.unir([])
    dobles = Dobles.unir([dobles_simples, dobles_grafo]) if minimo <= 2 else Dobles.unir([])
    prog(0.92, "ordenando")
    clave = (lambda g: (-g["tam"], g["dist_origen"])) if orden == "distancia" else (lambda g: (-g["tam"], -g["margen"]))
    grandes.sort(key=clave)
    dobles = dobles.ordenar(orden)
    conteo = defaultdict(int)
    for g in grandes:
        conteo[g["tam"]] += 1
    if len(dobles):
        conteo[2] = len(dobles)
    sid = (meta.get("structure") or {}).get("id")
    ver = meta.get("minecraft_version")
    teorico = estructuras.maximo_teorico(sid, ver, r, l) if sid is not None and ver else None
    mejor_tam = max(conteo) if conteo else 0
    tope = grandes[:top] + dobles.dicts(x, z, b, nb, r, 0, max(0, top - len(grandes)))
    mejores = {}                                     # las mejores opciones de CADA tamano encontrado
    for t in sorted(conteo, reverse=True):
        mejores[str(t)] = ([g for g in grandes if g["tam"] == t][:5] if t >= 3 else dobles.dicts(x, z, b, nb, r, 0, 5))
    res = {
        "seed": meta.get("seed"), "version": ver, "estructura": (meta.get("structure") or {}).get("name"),
        "dimension": meta.get("dimension"), "fuente": meta.get("_archivo"), "fuente_estado": meta.get("status"),
        "estructuras_leidas": int(len(arr)), "pares": int(npares),
        "radio": r, "caja": {"lado": l, "offset": off, "exacta": caja.exacta, "nota": caja.nota},
        "maximo_teorico": teorico, "conteo": {str(k): conteo[k] for k in sorted(conteo, reverse=True)},
        "mejor_tam": mejor_tam, "orden": orden,
        "recomendados": [g for g in tope if g["tam"] == mejor_tam][:10], "mejores": mejores,
        "total_grupos": len(grandes) + len(dobles), "grupos": tope,
        "segundos": round(time.time() - t0, 3), "fecha": util.ahora(),
    }
    if guardar:
        prog(0.95, "guardando")
        guardar_resultado(res, entrada, grandes, dobles, (x, z, r))
    res["segundos"] = round(time.time() - t0, 3)
    prog(1.0, "listo")
    return res


def guardar_resultado(res, entrada, grandes=None, dobles=None, xzr=None):
    """<base>.grupos.json = resumen + los primeros 'top' grupos; <base>.grupos.csv = TODOS los grupos."""
    rt = datos.rutas(entrada)
    util.escritura_atomica(rt["grupos"], json.dumps(res, separators=(",", ":"), ensure_ascii=False))
    grandes = res["grupos"] if grandes is None else grandes
    with open(rt["csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tam", "afk_x", "afk_z", "margen", "dist_origen", "estructuras"])
        for g in grandes:
            w.writerow([g["tam"], g["afk"][0], g["afk"][1], g["margen"], g["dist_origen"],
                        " ".join(f"{e['x']},{e['z']}" for e in g["estructuras"])])
        if dobles is not None and len(dobles):
            x, z, r = xzr
            for s in range(0, len(dobles), 200_000):
                d = dobles.tomar(slice(s, s + 200_000))
                dist = d.dist_origen(); mg = r - np.sqrt(d.d2)
                xi, zi, xj, zj = x[d.i], z[d.i], x[d.j], z[d.j]
                f.write("".join(f'2,{a},{c},{round(m, 2)},{round(o, 1)},"{p},{q} {s_},{t}"\r\n' for a, c, m, o, p, q, s_, t in
                                zip(d.bx.tolist(), d.bz.tolist(), mg.tolist(), dist.tolist(),
                                    xi.tolist(), zi.tolist(), xj.tolist(), zj.tolist())))
    res["archivos"] = {"json": str(rt["grupos"]), "csv": str(rt["csv"])}
    return res["archivos"]


def resumen_texto(res, n=5):
    lin = [f"{res['estructura']} | seed {res['seed']} | {res['version']} | radio {res['radio']} | "
           f"caja {res['caja']['lado']}x{res['caja']['lado']}{'' if res['caja']['exacta'] else ' (aprox.)'}",
           f"Estructuras leidas: {res['estructuras_leidas']:,}   pares compatibles: {res['pares']:,}   ({res['segundos']:.1f}s)"]
    if res["conteo"]:
        lin.append("Grupos: " + ", ".join(f"{v:,} {nombre_tam(int(k))}s" for k, v in res["conteo"].items()))
    else:
        lin.append("No hay ningun grupo: ninguna estructura se puede activar junto con otra.")
    if res["maximo_teorico"]:
        lin.append(f"Maximo teorico para esta estructura: {res['maximo_teorico']}")
    if res["mejor_tam"]:
        t = res["mejor_tam"]
        lin.append(f"Recomendacion: {nombre_tam(t)} (lo mejor que tiene este mundo)")
        for g in res["recomendados"][:n]:
            lin.append(f"  AFK X {g['afk'][0]}, Z {g['afk'][1]}  margen {g['margen']} bloques  a {g['dist_origen']:,.0f} del 0,0  -> " +
                       "; ".join(f"{e['x']},{e['z']}" for e in g["estructuras"]))
    return "\n".join(lin)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python -m sa.analizador <archivo .sab/.jsonl> [radio]")
        sys.exit(2)
    r = analizar(sys.argv[1], radio=int(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(resumen_texto(r))
