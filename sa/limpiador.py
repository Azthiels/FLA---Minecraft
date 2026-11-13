"""Parte 2: limpiador.

Descarta las estructuras que no tienen NINGUNA otra con la que puedan activarse a la vez (sus cajas no entran
juntas en un circulo de radio R alrededor de algun punto). Antes de descartar una se revisan todas sus vecinas,
no solo la siguiente de la lista: la busqueda es espacial (celdas de lado 2R - lado), asi que el orden del archivo
no importa.

Sirve para escaneos hechos en modo "todas" o para los .jsonl del formato viejo. Si el escaneo ya se hizo en modo
"grupos", el resultado ya esta limpio (mismo criterio, aplicado en C) y esto no saca nada.
RAM: ~60 bytes por registro de entrada (8,9 M de registros -> ~550 MB).
"""
import time

import numpy as np

from sa import config, datos, estructuras, util


def pares(x, z, radio, lado):
    """Todos los pares (i, j), i < j, cuyas cajas cuadradas entran juntas en un circulo de radio 'radio'.
    Vectorizado: se ordena por celda y se compara cada punto con las celdas vecinas hacia adelante."""
    x = np.asarray(x, np.int64); z = np.asarray(z, np.int64)
    n = len(x)
    vacio = (np.zeros(0, np.int64), np.zeros(0, np.int64))
    span = 2 * radio - lado
    if n < 2 or span < 0:
        return vacio
    cel = max(1, span)
    cx = x // cel; cz = z // cel
    cx -= cx.min(); cz -= cz.min()
    W = int(cz.max()) + 3
    key = cx * W + (cz + 1)
    orden = np.argsort(key, kind="stable")
    ks = key[orden]
    xs, zs = x[orden], z[orden]
    d2 = 4 * radio * radio
    pos = np.arange(n)
    ii, jj = [], []
    for ox, oz in ((0, 0), (0, 1), (1, -1), (1, 0), (1, 1)):
        objetivo = ks + (ox * W + oz)
        lo = np.searchsorted(ks, objetivo, "left")
        hi = np.searchsorted(ks, objetivo, "right")
        if ox == 0 and oz == 0:
            lo = np.maximum(lo, pos + 1)             # misma celda: solo los siguientes (sin repetir ni a si mismo)
        cnt = hi - lo
        m = int(cnt.max()) if n else 0
        for t in range(max(0, m)):
            sel = np.nonzero(cnt > t)[0]
            b = lo[sel] + t
            dx = np.abs(xs[sel] - xs[b]) + lado
            dz = np.abs(zs[sel] - zs[b]) + lado
            ok = dx * dx + dz * dz <= d2
            ii.append(sel[ok]); jj.append(b[ok])
        del objetivo, lo, hi, cnt
    if not ii:
        return vacio
    a = orden[np.concatenate(ii)]; b = orden[np.concatenate(jj)]
    i, j = np.minimum(a, b), np.maximum(a, b)
    return i, j


def mascara_util(x, z, radio, lado):
    """True para las estructuras que tienen al menos una vecina compatible."""
    i, j = pares(x, z, radio, lado)
    m = np.zeros(len(x), bool)
    m[i] = True; m[j] = True
    return m, len(i)


def parametros(meta, radio=None, lado=None):
    """Radio y caja: lo pedido, si no lo del meta del escaneo, si no lo de la tabla de estructuras."""
    sid = (meta.get("structure") or {}).get("id")
    caja = estructuras.caja(sid) if sid is not None else estructuras.caja(-1)
    g = meta.get("group") or {}
    r = int(radio if radio is not None else g.get("radius", config.RADIO_ACTIVACION))
    l = int(lado if lado is not None else g.get("side", caja.lado))
    off = int(g.get("offset", caja.offset))
    return r, l, off, caja


def limpiar(entrada, salida=None, radio=None, lado=None, progreso=None):
    """Lee 'entrada' (.sab / .jsonl / base), guarda las estructuras utiles en '<salida>.sab' + meta.
    Devuelve un resumen."""
    t0 = time.time()
    prog = progreso or (lambda f, txt="": None)
    prog(0.0, "leyendo")
    entrada = datos.encontrar(entrada)
    if salida is not None:
        salida = datos.resolver(salida)
    arr, meta = datos.leer(entrada, progreso=lambda f: prog(0.6 * f, "leyendo"))
    r, l, off, caja = parametros(meta, radio, lado)
    prog(0.6, "buscando vecinas")
    x = np.asarray(arr["x"]); z = np.asarray(arr["z"])
    m, npares = mascara_util(x, z, r, l)
    util_arr = np.asarray(arr)[m]
    prog(0.9, "guardando")
    if salida is None:
        b = datos.rutas(entrada)["datos"]
        salida = b.with_name(b.stem + "_limpio")
    nuevo = {k: v for k, v in meta.items() if not k.startswith("_")}
    nuevo.update({
        "format_version": 2, "kind": "limpio",
        "source": {"file": meta.get("_archivo"), "kind": meta.get("kind", "escaneo"), "status": meta.get("status"),
                   "mode": meta.get("mode", "todas"), "records": int(len(arr))},
        "group": {"radius": r, "side": l, "offset": off, "box_exact": caja.exacta, "note": caja.nota},
        "cleaning": {"kept": int(m.sum()), "removed": int(len(arr) - m.sum()), "pairs": int(npares),
                     "elapsed_seconds": round(time.time() - t0, 3), "at": util.ahora()},
        "biome_names": {str(k): v for k, v in meta.get("_biomas", {}).items()},
    })
    nuevo.pop("counts", None); nuevo.pop("native_stats", None)
    rt = datos.escribir(salida, util_arr, nuevo)
    prog(1.0, "listo")
    return {"entrada": len(arr), "quedan": int(m.sum()), "descartadas": int(len(arr) - m.sum()), "pares": int(npares),
            "radio": r, "lado": l, "segundos": time.time() - t0, "salida": str(rt["datos"]), "meta": nuevo}
