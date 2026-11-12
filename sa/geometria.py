"""Geometria de grupos: circulo minimo (Welzl), pares compatibles y punto AFK.

Coordenadas en bloques. Una estructura en (x, z) ocupa el cuadrado [x+off, x+off+lado] x [z+off, z+off+lado].
El jugador en el bloque (bx, bz) esta en (bx+0.5, bz+0.5).
"""
import math

EPS = 1e-9


def par_ok(x1, z1, x2, z2, radio, lado):
    """Dos cuadrados iguales entran juntos en un circulo de radio 'radio' (exacto, ver sa.estructuras)."""
    dx = abs(x1 - x2) + lado
    dz = abs(z1 - z2) + lado
    return dx * dx + dz * dz <= 4 * radio * radio


def esquinas(miembros, off, lado):
    pts = []
    for x, z in miembros:
        x0, z0 = x + off, z + off
        pts += [(x0, z0), (x0 + lado, z0), (x0, z0 + lado), (x0 + lado, z0 + lado)]
    return pts


def _circ2(a, b):
    cx, cz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return cx, cz, math.hypot(a[0] - cx, a[1] - cz)


def _circ3(a, b, c):
    ax, az = a; bx, bz = b; cx, cz = c
    d = 2 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz))
    if abs(d) < EPS:                       # colineales: el mayor de los circulos de 2 puntos
        return max((_circ2(a, b), _circ2(a, c), _circ2(b, c)), key=lambda t: t[2])
    ux = ((ax * ax + az * az) * (bz - cz) + (bx * bx + bz * bz) * (cz - az) + (cx * cx + cz * cz) * (az - bz)) / d
    uz = ((ax * ax + az * az) * (cx - bx) + (bx * bx + bz * bz) * (ax - cx) + (cx * cx + cz * cz) * (bx - ax)) / d
    return ux, uz, math.hypot(ax - ux, az - uz)


def _dentro(c, p):
    return math.hypot(p[0] - c[0], p[1] - c[1]) <= c[2] + 1e-7


def circulo_minimo(pts):
    """Circulo minimo que contiene todos los puntos (incremental de Welzl; pocos puntos -> instantaneo)."""
    pts = list(dict.fromkeys(pts))
    if not pts:
        return 0.0, 0.0, 0.0
    c = (pts[0][0], pts[0][1], 0.0)
    for i in range(1, len(pts)):
        if _dentro(c, pts[i]):
            continue
        c = (pts[i][0], pts[i][1], 0.0)
        for j in range(i):
            if _dentro(c, pts[j]):
                continue
            c = _circ2(pts[i], pts[j])
            for k in range(j):
                if not _dentro(c, pts[k]):
                    c = _circ3(pts[i], pts[j], pts[k])
    return c


def grupo_ok(miembros, radio, off, lado):
    return circulo_minimo(esquinas(miembros, off, lado))[2] <= radio + EPS


def _centro(miembros, off, lado):
    """Centro del circulo minimo. Para 2 cuadrados iguales es exactamente el centro de la caja que los envuelve
    (lo fijan las dos esquinas opuestas); se calcula asi para que coincida bit a bit con afk_pares()."""
    if len(miembros) == 2:
        (x1, z1), (x2, z2) = miembros
        return (min(x1, x2) + max(x1, x2) + 2 * off + lado) / 2, (min(z1, z2) + max(z1, z2) + 2 * off + lado) / 2
    cx, cz, _ = circulo_minimo(esquinas(miembros, off, lado))
    return cx, cz


def punto_afk(miembros, radio, off, lado):
    """Mejor bloque para el jugador: el que minimiza la distancia a la esquina mas lejana de todas las cajas.
    Se prueban los 4x4 bloques alrededor del centro del circulo minimo. Las distancias se comparan al cuadrado
    (exacto en coma flotante: las coordenadas son enteros o .5). Devuelve (bx, bz, distancia_maxima, margen)
    o None si ningun bloque sirve."""
    pts = esquinas(miembros, off, lado)
    cx, cz = _centro(miembros, off, lado)
    mejor = None
    for bx in range(math.floor(cx - 0.5) - 1, math.floor(cx - 0.5) + 3):
        for bz in range(math.floor(cz - 0.5) - 1, math.floor(cz - 0.5) + 3):
            px, pz = bx + 0.5, bz + 0.5
            d2 = max((x - px) * (x - px) + (z - pz) * (z - pz) for x, z in pts)
            if mejor is None or d2 < mejor[2]:
                mejor = (bx, bz, d2)
    if mejor is None or mejor[2] > radio * radio:
        return None
    d = math.sqrt(mejor[2])
    return mejor[0], mejor[1], d, radio - d


def afk_pares(x1, z1, x2, z2, radio, off, lado, bloque=250_000):
    """punto_afk() vectorizado para muchos pares a la vez (mismo resultado, bit a bit).
    Devuelve (bx, bz, d2, ok) como arrays; d2 = distancia maxima al cuadrado; ok = entra en el radio."""
    import numpy as np
    n = len(x1)
    BX = np.empty(n, np.int64); BZ = np.empty(n, np.int64); D2 = np.empty(n, np.float64)
    offs = [(i, j) for i in range(-1, 3) for j in range(-1, 3)]       # mismo orden que los for de punto_afk
    for s in range(0, n, bloque):
        a1 = np.asarray(x1[s:s + bloque], np.int64); b1 = np.asarray(z1[s:s + bloque], np.int64)
        a2 = np.asarray(x2[s:s + bloque], np.int64); b2 = np.asarray(z2[s:s + bloque], np.int64)
        cx = (np.minimum(a1, a2) + np.maximum(a1, a2) + 2 * off + lado) / 2
        cz = (np.minimum(b1, b2) + np.maximum(b1, b2) + 2 * off + lado) / 2
        fx = np.floor(cx - 0.5).astype(np.int64); fz = np.floor(cz - 0.5).astype(np.int64)
        # esquinas de los dos cuadrados: x in {x+off, x+off+lado}, z igual (los 4 x 2 se arman por eje)
        ex = np.stack([a1 + off, a1 + off + lado, a2 + off, a2 + off + lado], 1).astype(np.float64)
        ez = np.stack([b1 + off, b1 + off + lado, b2 + off, b2 + off + lado], 1).astype(np.float64)
        mejor = np.full(len(a1), np.inf); mbx = np.zeros(len(a1), np.int64); mbz = np.zeros(len(a1), np.int64)
        for dx, dz in offs:
            bx, bz = fx + dx, fz + dz
            px, pz = (bx + 0.5)[:, None], (bz + 0.5)[:, None]
            ddx = (ex - px) ** 2; ddz = (ez - pz) ** 2
            # esquina (x_k, z_k) del mismo cuadrado: k en {0,1} con {0,1} y {2,3} con {2,3}
            d2 = np.maximum(np.maximum(ddx[:, :2].max(1) + ddz[:, :2].max(1), 0),
                            ddx[:, 2:].max(1) + ddz[:, 2:].max(1))
            mej = d2 < mejor
            mejor[mej] = d2[mej]; mbx[mej] = bx[mej]; mbz[mej] = bz[mej]
        BX[s:s + bloque], BZ[s:s + bloque], D2[s:s + bloque] = mbx, mbz, mejor
    return BX, BZ, D2, D2 <= radio * radio
