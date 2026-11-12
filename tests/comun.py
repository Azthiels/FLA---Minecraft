"""Utilidades compartidas por los tests (sin dependencias de test externas)."""
import sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "bench"))

from sa import datos, nativo  # noqa: E402
from sa.escaner import Escaneo  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sa_tests_"))
FALLOS = []


def check(nombre, cond, detalle=""):
    print(("PASS " if cond else "FAIL ") + nombre + (f"  [{detalle}]" if detalle else ""), flush=True)
    if not cond:
        FALLOS.append(nombre)


def leer(p):
    """Registros como dicts {"x","z","biome"} (igual que el formato viejo, para comparar facil)."""
    arr, meta = datos.leer(p)
    nb = meta["_biomas"]
    return [{"x": x, "z": z, "biome": nb.get(b, f"id_{b}")}
            for x, z, b in zip(arr["x"].tolist(), arr["z"].tolist(), arr["b"].tolist())]


def escanear(nombre, version, sid, R, seed=12345, **kw):
    kw.setdefault("hilos", 1)
    kw.setdefault("modo", "todas")
    e = Escaneo(version, nativo.parse_seed(str(seed)), sid, R, TMP / nombre, sobrescribir=True, **kw)
    r = e.run()
    return e, r, leer(e.rutas["datos"])
