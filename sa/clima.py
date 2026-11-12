"""Verificacion del supuesto del prefiltro de clima (ver shim.c: clima_posible).

El prefiltro es exacto si las hojas de SUPERFICIE de profundidad 0 del arbol de clima cubren por completo una caja
de clima (temperatura, humedad, continentalidad, erosion, rareza). La capa de profundidad 1 no hace falta que este
completa: las hojas de profundidad 0 sin gemela (p. ej. 14 en 26.2) se tratan en C como zonas donde se calcula el
bioma completo. Se comprueba
con compresion de coordenadas: en cada eje solo importan los cortes de los intervalos, asi que alcanza con revisar
un representante por celda elemental (~340 mil celdas, recorridas en profundidad con bitsets: ~0,5 s por version).
"""
from functools import lru_cache

from sa import nativo

_CL = [0, 1, 2, 3, 5]     # T, H, C, E, W (el 4 es profundidad)


def _cubre(hojas, prof):
    sup = [r for _, r in hojas if r[4] == (prof, prof)]
    if not sup:
        return False, None
    lo = [min(r[p][0] for r in sup) for p in _CL]
    hi = [max(r[p][1] for r in sup) for p in _CL]
    masks = []
    for k, p in enumerate(_CL):
        cortes = sorted({lo[k]} | {r[p][0] for r in sup if lo[k] <= r[p][0] <= hi[k]} |
                        {r[p][1] + 1 for r in sup if r[p][1] + 1 <= hi[k]})
        masks.append([sum(1 << i for i, r in enumerate(sup) if r[p][0] <= c <= r[p][1]) for c in cortes])

    def rec(k, acc):
        if k == 5:
            return True
        for m in masks[k]:
            a = acc & m
            if not a or not rec(k + 1, a):
                return False
        return True
    return rec(0, (1 << len(sup)) - 1), (lo, hi)


@lru_cache(maxsize=None)
def cobertura_completa(version: str) -> bool:
    """True si el prefiltro de clima es exacto para esa version."""
    if not nativo.es_118_o_mas(version):
        return False
    ok0, _ = _cubre(nativo.hojas_clima(version), 0)
    return ok0


@lru_cache(maxsize=None)
def huerfanas(version: str) -> int:
    """Hojas de profundidad 0 sin gemela en profundidad 1 (informativo: ahi el prefiltro calcula el bioma completo)."""
    from collections import Counter
    h = nativo.hojas_clima(version)
    caja = lambda r: tuple(r[i] for i in _CL)
    d0 = Counter(caja(r) for _, r in h if r[4] == (0, 0))
    d1 = Counter(caja(r) for _, r in h if r[4] == (10000, 10000))
    return sum((d0 - d1).values())


def disponible(sid: int, version: str) -> bool:
    return nativo.clima_aplicable(sid, version) and cobertura_completa(version)
