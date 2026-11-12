"""Capa nativa: carga lib/scanner.(dll|so), declara los tipos de ctypes y expone versiones/estructuras/biomas."""
import ctypes, os, sys

from sa import RAIZ

LIBDIR = RAIZ / "lib"

# Versiones: se arma sola a partir de la libreria, asi que al actualizar cubiomes_src
# (ej. cuando salga la 26.4) aparece automaticamente en el selector.
_FIJAS = ["1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16.1", "1.16",
          "1.17", "1.18", "1.19.2", "1.19", "1.20", "1.21.1", "1.21.3", "1.21.4", "1.21.5",
          "1.21.6", "1.21.9", "1.21.11"]
_ETIQ = {"1.16": "1.16.5", "1.17": "1.17.1", "1.18": "1.18.2", "1.19": "1.19.4", "1.20": "1.20.6",
         "1.15": "1.15.2", "1.14": "1.14.4", "1.13": "1.13.2", "1.12": "1.12.2", "1.11": "1.11.2",
         "1.10": "1.10.2", "1.9": "1.9.4", "1.8": "1.8.9", "1.7": "1.7.10"}

# (id de cubiomes, nombre para mostrar). Solo estructuras "por region" (las que se listan por semilla).
# Nether Fossil NO esta: cubiomes solo da celdas candidatas (sin comprobar terreno), listarlas seria impreciso.
ESTRUCTURAS = [
    (1, "Desert Pyramid"), (2, "Jungle Temple"), (3, "Witch Hut (Swamp Hut)"), (4, "Igloo"),
    (5, "Village"), (6, "Ocean Ruin"), (7, "Shipwreck"), (8, "Ocean Monument"),
    (9, "Woodland Mansion"), (10, "Pillager Outpost"), (11, "Ruined Portal (Overworld)"),
    (12, "Ruined Portal (Nether)"), (13, "Ancient City"), (14, "Buried Treasure"),
    (18, "Nether Fortress"), (19, "Bastion Remnant"), (21, "End City"),
    (24, "Trail Ruins"), (25, "Trial Chambers"), (26, "Abandoned Camp"),
]
DIM_NOMBRE = {-1: "nether", 0: "overworld", 1: "end"}
BORDE_MAX = 29_999_984  # radio del world border por defecto de vanilla (diametro 59 999 968)


def _cargar():
    alt = os.environ.get("SA_LIB")                  # otra libreria (p. ej. probar una compilacion nueva)
    if alt:
        return ctypes.CDLL(alt)
    nombres =["scanner.dll"] if os.name == "nt" else (["scanner.dylib", "scanner.so"] if sys.platform == "darwin" else ["scanner.so"])
    for n in nombres:
        p = LIBDIR / n
        if p.exists():
            try:
                return ctypes.CDLL(str(p))
            except OSError:
                pass
    sys.path.insert(0, str(RAIZ))
    import build_lib                       # no hay binario para este sistema: compilar
    return ctypes.CDLL(str(build_lib.compilar()))


L = _cargar()
_I, _P = ctypes.c_int, ctypes.POINTER
L.sh_str2mc.argtypes = [ctypes.c_char_p]
L.sh_struct_name.restype = ctypes.c_char_p
L.sh_biome_name.restype = ctypes.c_char_p
L.sh_biome_name.argtypes = [_I, _I]
L.sh_supported.argtypes = [_I, _I]
L.sh_region_blocks.argtypes = [_I, _I]
L.sh_biome_ok.argtypes = [_I, _I, _I]
L.sh_new.restype = ctypes.c_void_p
L.sh_new.argtypes = [_I, ctypes.c_uint64, _I]
L.sh_free.argtypes = [ctypes.c_void_p]
L.sh_scan.argtypes = [ctypes.c_void_p] + [_I] * 8 + [_P(ctypes.c_ubyte), _P(_I), _I]   # version anterior (referencia)
L.sh_scan_tile.argtypes = [ctypes.c_void_p] + [_I] * 8 + [_P(ctypes.c_ubyte), ctypes.c_uint, _P(_I), _I]
L.sh_scan_tile.restype = _I
L.sh_stats.argtypes = [ctypes.c_void_p, _P(ctypes.c_uint64)]
L.sh_stats_reset.argtypes = [ctypes.c_void_p]
L.sh_struct_config.argtypes = [_I, _I, _P(_I)]
L.sh_struct_pos.argtypes = [_I, _I, ctypes.c_uint64, _I, _I, _P(_I), _P(_I)]
L.sh_set_groups.argtypes = [ctypes.c_void_p, _I, _I, _P(_I), _I]
L.sh_set_groups.restype = _I
L.sh_nstat.restype = _I
L.sh_set_climate.argtypes = [ctypes.c_void_p, _I, _P(ctypes.c_ubyte)]
L.sh_set_climate.restype = _I
L.sh_climate_leaves.argtypes = [_I, _P(ctypes.c_int32), _I]
L.sh_climate_leaves.restype = _I

MASKN = 512          # ids de bioma 0..511 (igual que en shim.c)
F_NO_VIABLE, F_NO_TERRAIN, F_GROUPS = 1, 2, 4
STAT_NAMES = ["regions", "positions", "in_box", "viable_calls", "viable_ok", "mask_rejected",
              "terrain_calls", "found", "group_skipped", "halo_calls", "climate_rejected"]
# Estructuras cuya viabilidad 1.18+ es un unico chequeo de bioma: admiten el prefiltro de clima (shim.c)
_CLIMA_SIDS = {1, 2, 3, 4, 6, 7, 14, 24}
NSTAT = L.sh_nstat()
if NSTAT != len(STAT_NAMES):
    raise RuntimeError(f"lib/ desactualizada (NSTAT={NSTAT}): borra lib/ y ejecuta python build_lib.py")


def mc_id(version: str) -> int:
    return L.sh_str2mc(version.encode())


def _armar_versiones():
    vs = list(_FIJAS)
    for n in range(1, 30):  # 26.1, 26.2, 26.3, 26.4 ... segun lo que conozca la libreria
        v = f"26.{n}"
        if mc_id(v) != 0:
            vs.append(v)
    return [v for v in vs if mc_id(v) != 0]


VERSIONES = _armar_versiones()
VERSIONES_LABEL = {v: _ETIQ.get(v, v) for v in VERSIONES}


def es_118_o_mas(version: str) -> bool:
    return mc_id(version) >= mc_id("1.18")


def clima_aplicable(sid: int, version: str) -> bool:
    """El prefiltro de clima (exacto) existe para esta estructura/version."""
    if not es_118_o_mas(version) or sid not in _CLIMA_SIDS or dimension(sid, version) != 0:
        return False
    return not (sid == 24 and mc_id(version) <= mc_id("1.19"))


def hojas_clima(version: str):
    """Hojas del arbol de clima 1.18+: lista de (bioma, [(min,max) x 6 en orden T,H,C,E,D,W])."""
    mc = mc_id(version)
    n = L.sh_climate_leaves(mc, None, 0)
    buf = (ctypes.c_int32 * (13 * n))()
    L.sh_climate_leaves(mc, buf, n)
    return [(buf[13 * i], [(buf[13 * i + 1 + 2 * p], buf[13 * i + 2 + 2 * p]) for p in range(6)]) for i in range(n)]


def estructuras_soportadas(version: str, dim=None):
    """Estructuras que existen en esa version y (si se indica) en esa dimension (-1, 0, 1)."""
    mc = mc_id(version)
    return [(sid, nombre) for sid, nombre in ESTRUCTURAS
            if L.sh_supported(sid, mc) and (dim is None or L.sh_supported(sid, mc) - 2 == dim)]


def dimension(sid: int, version: str) -> int:
    return L.sh_supported(sid, mc_id(version)) - 2


def region_bloques(sid: int, version: str) -> int:
    return L.sh_region_blocks(sid, mc_id(version))


def biomas_validos(sid: int, version: str):
    """Biomas donde la estructura PUEDE aparecer: lista de (id, nombre)."""
    mc = mc_id(version)
    out = []
    for b in range(0, MASKN):
        nm = L.sh_biome_name(mc, b)
        if nm and L.sh_biome_ok(mc, sid, b):
            out.append((b, nm.decode()))
    return out


def tabla_biomas(version: str) -> dict:
    """{id: nombre} de todos los biomas que conoce la libreria para esa version."""
    mc = mc_id(version)
    out = {}
    for b in range(MASKN):
        nm = L.sh_biome_name(mc, b)
        if nm:
            out[b] = nm.decode()
    return out


def parse_seed(texto: str) -> int:
    """Acepta numeros (con signo) o texto, como el juego (hash de Java String.hashCode)."""
    t = texto.strip()
    if not t:
        raise ValueError("Seed vacia")
    try:
        return int(t) & 0xFFFFFFFFFFFFFFFF
    except ValueError:
        h = 0
        for ch in t:
            h = (31 * h + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
        return h & 0xFFFFFFFFFFFFFFFF


def seed_firmada(s: int) -> int:
    return s - (1 << 64) if s >= (1 << 63) else s


def limite_dimension(dim: int, radio: int = BORDE_MAX) -> int:
    """Radio maximo (en coordenadas de la dimension) dentro del world border. Nether: escala 1:8."""
    return radio // 8 if dim == -1 else radio


def config_estructura(sid: int, version: str):
    out = (ctypes.c_int * 4)()
    if not L.sh_struct_config(sid, mc_id(version), out):
        return None
    return {"salt": out[0], "region_size_chunks": out[1], "chunk_range": out[2], "dim": out[3]}


def nombre_estructura(sid: int) -> str:
    return L.sh_struct_name(sid).decode()


def nombre_bioma(version: str, bid: int) -> str:
    nm = L.sh_biome_name(mc_id(version), bid)
    return nm.decode() if nm else f"id_{bid}"


def mascara_biomas(ids):
    """Mascara ctypes (MASKN bytes) para sh_scan_tile; None = sin filtro adicional."""
    if ids is None:
        return None
    m = (ctypes.c_ubyte * MASKN)()
    for b in ids:
        if 0 <= b < MASKN:
            m[b] = 1
    return m


def posicion(sid: int, version: str, seed: int, rx: int, rz: int):
    """Posicion potencial (sin validar bioma) de la region (rx, rz), o None."""
    x, z = ctypes.c_int(), ctypes.c_int()
    if L.sh_struct_pos(sid, mc_id(version), seed, rx, rz, ctypes.byref(x), ctypes.byref(z)):
        return x.value, z.value
    return None
