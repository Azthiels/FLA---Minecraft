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
import csv, json, sys, time
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
            "dist_origen": round(float(np.hypot(bx + 0.5, bz + 0.5)), 1),
            "estructuras": [{"x": mx, "z": mz, "bioma": nb.get(int(b[i]), f"id_{int(b[i])}")}
                            for (mx, mz), i in zip(miembros, ids)],
            "_ids": tuple(ids)}


def analizar(entrada, radio=None, lado=None, minimo=2, orden="distancia", progreso=None, guardar=True):
    t0 = time.time()
    prog = progreso or (lambda f, txt="": None)
    prog(0.0, "leyendo")
    arr, meta = datos.leer(entrada, progreso=lambda f: prog(0.3 * f, "leyendo"))
    r, l, off, caja = parametros(meta, radio, lado)
    x = np.asarray(arr["x"]); z = np.asarray(arr["z"]); b = np.asarray(arr["b"])
    nb = meta.get("_biomas", {})
    prog(0.3, "buscando pares")
    i, j = pares(x, z, r, l)
    prog(0.5, "armando grupos")
    adj = defaultdict(set)
    for a, c in zip(i.tolist(), j.tolist()):
        adj[a].add(c); adj[c].add(a)
    candidatos = _cliques(adj)
    grupos = {}
    for k, cl in enumerate(candidatos):
        if k % 20000 == 0:
            prog(0.5 + 0.4 * k / max(1, len(candidatos)), "validando grupos")
        g = _grupo(cl, x, z, b, r, off, l, nb)
        if g:
            grupos[g["_ids"]] = g
            continue
        hechos = []                                  # el clique entero no entra: subconjuntos mas grandes
        for t in range(len(cl) - 1, 1, -1):
            for sub in combinations(cl, t):
                if any(set(sub) <= h for h in hechos):
                    continue
                g = _grupo(sub, x, z, b, r, off, l, nb)
                if g:
                    grupos[g["_ids"]] = g
                    hechos.append(set(sub))
    # maximalidad global: descartar grupos contenidos en otro mas grande
    por_miembro = defaultdict(list)
    for ids in grupos:
        for m in ids:
            por_miembro[m].append(ids)
    maximales = []
    for ids, g in grupos.items():
        s = set(ids)
        if any(len(o) > len(ids) and s <= set(o) for o in por_miembro[ids[0]]):
            continue
        if g["tam"] >= minimo:
            maximales.append(g)
    clave = (lambda g: (-g["tam"], g["dist_origen"])) if orden == "distancia" else (lambda g: (-g["tam"], -g["margen"]))
    maximales.sort(key=clave)
    for g in maximales:
        g.pop("_ids", None)
    conteo = defaultdict(int)
    for g in maximales:
        conteo[g["tam"]] += 1
    sid = (meta.get("structure") or {}).get("id")
    ver = meta.get("minecraft_version")
    teorico = estructuras.maximo_teorico(sid, ver, r, l) if sid is not None and ver else None
    mejor_tam = max(conteo) if conteo else 0
    res = {
        "seed": meta.get("seed"), "version": ver, "estructura": (meta.get("structure") or {}).get("name"),
        "dimension": meta.get("dimension"), "fuente": meta.get("_archivo"), "fuente_estado": meta.get("status"),
        "estructuras_leidas": int(len(arr)), "pares": int(len(i)),
        "radio": r, "caja": {"lado": l, "offset": off, "exacta": caja.exacta, "nota": caja.nota},
        "maximo_teorico": teorico, "conteo": {str(k): conteo[k] for k in sorted(conteo, reverse=True)},
        "mejor_tam": mejor_tam, "orden": orden,
        "recomendados": [g for g in maximales if g["tam"] == mejor_tam][:10],
        "grupos": maximales, "segundos": round(time.time() - t0, 3), "fecha": util.ahora(),
    }
    if guardar:
        prog(0.95, "guardando")
        guardar_resultado(res, entrada)
    prog(1.0, "listo")
    return res


def guardar_resultado(res, entrada):
    rt = datos.rutas(entrada)
    util.escritura_atomica(rt["grupos"], json.dumps(res, separators=(",", ":"), ensure_ascii=False))
    with open(rt["csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tam", "afk_x", "afk_z", "margen", "dist_origen", "estructuras"])
        for g in res["grupos"]:
            w.writerow([g["tam"], g["afk"][0], g["afk"][1], g["margen"], g["dist_origen"],
                        " ".join(f"{e['x']},{e['z']}" for e in g["estructuras"])])
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
