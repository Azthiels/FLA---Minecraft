"""Formato de resultados.

<base>.sab        binario: cabecera de 16 bytes (b"SAB1", version, tamano de registro, reservado) + registros de
                  12 bytes little-endian: x int32, z int32, bioma int32 (id de cubiomes). Es exactamente lo que
                  escribe la libreria nativa, asi que el escritor no formatea nada y se lee al instante con numpy.
                  ~3,5x mas chico que el JSONL.
<base>.meta.json  seed, version, estructura, parametros, conteos, nombres de biomas {id: nombre}...
<base>.checkpoint.json  (solo escaneos) tiles confirmados + tamano en bytes del .sab, para reanudar.

Tambien se leen los .jsonl del formato viejo ({"x":..,"z":..,"biome":".."} por linea) en streaming.
"""
import json, os, struct
from pathlib import Path

import numpy as np

from sa import util

MAGIC = b"SAB1"
VERSION_SAB = 1
CABECERA = 16
DTYPE = np.dtype([("x", "<i4"), ("z", "<i4"), ("b", "<i4")])
EXT = ".sab"


def cabecera() -> bytes:
    return MAGIC + struct.pack("<III", VERSION_SAB, DTYPE.itemsize, 0)


def _base(p) -> Path:
    p = Path(p)
    for suf in (".checkpoint.json", ".meta.json", ".grupos.json", ".grupos.csv"):
        if p.name.endswith(suf):
            return p.with_name(p.name[: -len(suf)])
    if p.suffix.lower() in (EXT, ".jsonl", ".json"):
        return p.with_suffix("")
    return p


def rutas(base) -> dict:
    """'resultados' / 'resultados.sab' / 'resultados.meta.json' -> los archivos de ese conjunto de datos."""
    b = _base(base)
    return {"datos": b.with_name(b.name + EXT), "meta": b.with_name(b.name + ".meta.json"),
            "ckpt": b.with_name(b.name + ".checkpoint.json"), "jsonl": b.with_name(b.name + ".jsonl"),
            "grupos": b.with_name(b.name + ".grupos.json"), "csv": b.with_name(b.name + ".grupos.csv")}


def leer_meta(ruta) -> dict:
    m = rutas(ruta)["meta"]
    if m.exists():
        try:
            return json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def nombres_biomas(meta) -> dict:
    """{id: nombre} guardado en el meta; si no esta (archivos viejos), se arma desde la libreria."""
    n = meta.get("biome_names")
    if n:
        return {int(k): v for k, v in n.items()}
    v = meta.get("minecraft_version")
    if v:
        from sa import nativo
        if nativo.mc_id(v):
            return nativo.tabla_biomas(v)
    return {}


def contar(ruta) -> int:
    p = Path(ruta)
    if p.suffix.lower() == EXT:
        return max(0, (p.stat().st_size - CABECERA) // DTYPE.itemsize)
    n = 0
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 24), b""):
            n += blk.count(b"\n")
    return n


def leer_sab(ruta):
    p = Path(ruta)
    with open(p, "rb") as f:
        h = f.read(CABECERA)
    if len(h) < CABECERA or h[:4] != MAGIC:
        raise ValueError(f"{p.name} no es un archivo .sab valido")
    ver, rec, _ = struct.unpack("<III", h[4:])
    if ver != VERSION_SAB or rec != DTYPE.itemsize:
        raise ValueError(f"{p.name}: version {ver} / registro {rec} no soportados")
    n = (p.stat().st_size - CABECERA) // rec
    if n == 0:
        return np.zeros(0, DTYPE)
    return np.memmap(p, dtype=DTYPE, mode="r", offset=CABECERA, shape=(n,))


def leer_jsonl(ruta, meta=None, progreso=None):
    """JSONL viejo en streaming -> array (los nombres de bioma se traducen a ids con la tabla de la version)."""
    meta = meta if meta is not None else leer_meta(ruta)
    inv = {v: k for k, v in nombres_biomas(meta).items()}
    extra = {}
    total = os.path.getsize(ruta) or 1
    partes, leido = [], 0
    with open(ruta, "rb") as f:
        while True:
            lineas = f.readlines(1 << 25)
            if not lineas:
                break
            xs = np.empty(len(lineas), np.int32); zs = np.empty(len(lineas), np.int32); bs = np.empty(len(lineas), np.int32)
            n = 0
            for ln in lineas:
                leido += len(ln)
                t = ln.split(b'"')
                try:                                   # {"x":93872,"z":352,"biome":"swamp"}
                    x, z, nb = int(t[2][1:-1]), int(t[4][1:-1]), t[7].decode()
                except (IndexError, ValueError):
                    if not ln.strip():
                        continue
                    d = json.loads(ln)
                    x, z, nb = d["x"], d["z"], d.get("biome", "")
                b = inv.get(nb)
                if b is None:
                    b = extra.setdefault(nb, -1 - len(extra))
                xs[n], zs[n], bs[n] = x, z, b
                n += 1
            a = np.empty(n, DTYPE); a["x"], a["z"], a["b"] = xs[:n], zs[:n], bs[:n]
            partes.append(a)
            if progreso:
                progreso(leido / total)
    if extra:
        meta.setdefault("biome_names_extra", {str(v): k for k, v in extra.items()})
    return np.concatenate(partes) if partes else np.zeros(0, DTYPE)


def leer(ruta, progreso=None):
    """Devuelve (registros, meta). Acepta .sab, .jsonl o el nombre base."""
    p = Path(ruta)
    r = rutas(p)
    if p.suffix.lower() not in (EXT, ".jsonl"):
        p = r["datos"] if r["datos"].exists() else r["jsonl"]
    if not p.exists():
        raise FileNotFoundError(f"No existe {p}")
    meta = leer_meta(p)
    if p.suffix.lower() == EXT:
        arr = leer_sab(p)
    else:
        arr = leer_jsonl(p, meta, progreso)
    nb = nombres_biomas(meta)
    for k, v in meta.get("biome_names_extra", {}).items():
        nb[int(k)] = v
    meta["_biomas"] = nb
    meta["_archivo"] = str(p)
    return arr, meta


def escribir(base, arr, meta):
    """Escribe <base>.sab + <base>.meta.json (atomico: tmp + replace)."""
    r = rutas(base)
    r["datos"].parent.mkdir(parents=True, exist_ok=True)
    tmp = r["datos"].with_name(r["datos"].name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(cabecera())
        f.write(np.ascontiguousarray(arr, dtype=DTYPE).tobytes())
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, r["datos"])
    m = {k: v for k, v in meta.items() if not k.startswith("_")}
    util.escritura_atomica(r["meta"], json.dumps(m, indent=2))
    return r


def exportar_jsonl(arr, meta, destino):
    """Exporta registros al JSONL legible (mismo formato que la version anterior)."""
    nb = meta.get("_biomas") or nombres_biomas(meta)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        for i in range(0, len(arr), 1 << 20):
            blk = arr[i:i + (1 << 20)]
            f.write("".join(f'{{"x":{x},"z":{z},"biome":"{nb.get(b, f"id_{b}")}"}}\n'
                            for x, z, b in zip(blk["x"].tolist(), blk["z"].tolist(), blk["b"].tolist())))
    return destino
