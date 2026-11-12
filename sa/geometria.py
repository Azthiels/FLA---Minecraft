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


def punto_afk(miembros, radio, off, lado):
    """Mejor bloque para el jugador: el que minimiza la distancia a la esquina mas lejana de todas las cajas.
    Devuelve (bx, bz, distancia_maxima, margen) o None si ningun bloque cercano al centro sirve."""
    pts = esquinas(miembros, off, lado)
    cx, cz, _ = circulo_minimo(pts)
    mejor = None
    for bx in range(math.floor(cx - 0.5) - 1, math.floor(cx - 0.5) + 3):
        for bz in range(math.floor(cz - 0.5) - 1, math.floor(cz - 0.5) + 3):
            px, pz = bx + 0.5, bz + 0.5
            d = max(math.hypot(x - px, z - pz) for x, z in pts)
            if mejor is None or d < mejor[2]:
                mejor = (bx, bz, d)
    if mejor is None or mejor[2] > radio + EPS:
        return None
    return mejor[0], mejor[1], mejor[2], radio - mejor[2]
