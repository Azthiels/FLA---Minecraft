"""Planificacion: cajas (bounding boxes) -> rectangulos disjuntos -> tiles de regiones en anillos desde el origen."""
from sa.i18n import t


def normalizar_cajas(cajas, limite):
    """Valida y recorta cajas (x0,z0,x1,z1) al world border. Sin cajas = mundo completo."""
    if not cajas:
        return [(-limite, -limite, limite, limite)]
    out = []
    for c in cajas:
        if len(c) != 4:
            raise ValueError(t("err.caja_4"))
        x0, z0, x1, z1 = (int(v) for v in c)
        x0, x1 = sorted((x0, x1)); z0, z1 = sorted((z0, z1))
        x0, z0, x1, z1 = max(x0, -limite), max(z0, -limite), min(x1, limite), min(z1, limite)
        if x0 <= x1 and z0 <= z1:
            out.append((x0, z0, x1, z1))
    if not out:
        raise ValueError(t("err.caja_fuera", l=limite))
    return out


def _restar(p, r):
    """Partes del rectangulo p (inclusivo) que NO estan en r."""
    px0, pz0, px1, pz1 = p
    rx0, rz0, rx1, rz1 = r
    ix0, ix1, iz0, iz1 = max(px0, rx0), min(px1, rx1), max(pz0, rz0), min(pz1, rz1)
    if ix0 > ix1 or iz0 > iz1:
        return [p]
    out = []
    if pz0 < iz0: out.append((px0, pz0, px1, iz0 - 1))
    if iz1 < pz1: out.append((px0, iz1 + 1, px1, pz1))
    if px0 < ix0: out.append((px0, iz0, ix0 - 1, iz1))
    if ix1 < px1: out.append((ix1 + 1, iz0, px1, iz1))
    return out


def descomponer(cajas):
    """Union de cajas (posiblemente solapadas) -> rectangulos DISJUNTOS. Asi cada posicion pertenece a una sola
    caja y no hace falta deduplicar resultados (ni guardar un set gigante en RAM)."""
    res = []
    for b in sorted(cajas):
        piezas = [b]
        for r in res:
            piezas = [q for p in piezas for q in _restar(p, r)]
        res.extend(piezas)
    return sorted(res)


def _dist_origen(r):
    x0, z0, x1, z1 = r
    dx = 0 if x0 <= 0 <= x1 else min(abs(x0), abs(x1))
    dz = 0 if z0 <= 0 <= z1 else min(abs(z0), abs(z1))
    return dx * dx + dz * dz


class Plan:
    """Secuencia determinista de tiles. Un tile = rectangulo de hasta T x T regiones alineado a multiplos de T
    (en el espacio de regiones), recortado a las regiones que tocan su rectangulo. Las regiones que no
    intersectan ninguna caja jamas se procesan; las que la cortan parcialmente se escanean enteras y la posicion
    se filtra exactamente contra la caja (dentro de C)."""

    def __init__(self, rects, region_blocks, T):
        self.rb, self.T = region_blocks, T
        self.rects = sorted(rects, key=lambda r: (_dist_origen(r), r))
        self.info = []
        self.total_tiles = self.total_regions = 0
        for r in self.rects:
            x0, z0, x1, z1 = r
            rx0, rx1, rz0, rz1 = x0 // self.rb, x1 // self.rb, z0 // self.rb, z1 // self.rb
            tx0, tx1, tz0, tz1 = rx0 // T, rx1 // T, rz0 // T, rz1 // T
            px, pz = min(max(0, x0), x1), min(max(0, z0), z1)       # punto de la caja mas cercano al origen
            cx, cz = (px // self.rb) // T, (pz // self.rb) // T
            self.info.append((r, rx0, rx1, rz0, rz1, tx0, tx1, tz0, tz1, cx, cz))
            self.total_tiles += (tx1 - tx0 + 1) * (tz1 - tz0 + 1)
            self.total_regions += (rx1 - rx0 + 1) * (rz1 - rz0 + 1)

    def __iter__(self):
        """Genera (rect_idx, rx0, rz0, rx1, rz1). Anillos concentricos (distancia de Chebyshev) alrededor del tile
        mas cercano al origen: los resultados utiles aparecen primero y el orden es reproducible."""
        T = self.T
        for ri, (r, RX0, RX1, RZ0, RZ1, tx0, tx1, tz0, tz1, cx, cz) in enumerate(self.info):
            dmax = max(abs(tx0 - cx), abs(tx1 - cx), abs(tz0 - cz), abs(tz1 - cz))
            for d in range(dmax + 1):
                for tz in range(max(cz - d, tz0), min(cz + d, tz1) + 1):
                    if abs(tz - cz) == d:
                        xs = range(max(cx - d, tx0), min(cx + d, tx1) + 1)
                    else:
                        xs = [x for x in (cx - d, cx + d) if tx0 <= x <= tx1]
                    for tx in xs:
                        yield (ri, max(tx * T, RX0), max(tz * T, RZ0),
                               min(tx * T + T - 1, RX1), min(tz * T + T - 1, RZ1))
