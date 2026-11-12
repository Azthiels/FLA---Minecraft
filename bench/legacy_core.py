"""MOTOR ANTERIOR (referencia para benchmark/equivalencia). No se usa en la app."""
import ctypes, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
LIBDIR = BASE / "lib"

# Versiones: se arma sola a partir de la libreria, asi que al actualizar cubiomes_src
# (ej. cuando salga la 26.4) aparece automaticamente en el selector.
_FIJAS = ["1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16.1", "1.16",
          "1.17", "1.18", "1.19.2", "1.19", "1.20", "1.21.1", "1.21.3", "1.21.4", "1.21.5",
          "1.21.6", "1.21.9", "1.21.11"]
_ETIQ = {"1.16": "1.16.5", "1.17": "1.17.1", "1.18": "1.18.2", "1.19": "1.19.4", "1.20": "1.20.6",
         "1.15": "1.15.2", "1.14": "1.14.4", "1.13": "1.13.2", "1.12": "1.12.2", "1.11": "1.11.2",
         "1.10": "1.10.2", "1.9": "1.9.4", "1.8": "1.8.9", "1.7": "1.7.10"}

# (id de cubiomes, nombre para mostrar). Solo estructuras "por region" (las que se listan por semilla).
ESTRUCTURAS = [
    (1, "Desert Pyramid"), (2, "Jungle Temple"), (3, "Witch Hut (Swamp Hut)"), (4, "Igloo"),
    (5, "Village"), (6, "Ocean Ruin"), (7, "Shipwreck"), (8, "Ocean Monument"),
    (9, "Woodland Mansion"), (10, "Pillager Outpost"), (11, "Ruined Portal (Overworld)"),
    (12, "Ruined Portal (Nether)"), (13, "Ancient City"), (14, "Buried Treasure"),
    (18, "Nether Fortress"), (19, "Bastion Remnant"), (20, "Nether Fossil"), (21, "End City"),
    (24, "Trail Ruins"), (25, "Trial Chambers"), (26, "Abandoned Camp"),
]
DIM_NOMBRE = {-1: "nether", 0: "overworld", 1: "end"}
BORDE_MAX = 29_999_984  # radio del world border por defecto de vanilla (diametro 59 999 968)


def _cargar():
    nombres = ["scanner.dll"] if os.name == "nt" else (["scanner.dylib", "scanner.so"] if sys.platform == "darwin" else ["scanner.so"])
    for n in nombres:
        p = LIBDIR / n
        if p.exists():
            try:
                return ctypes.CDLL(str(p))
            except OSError:
                pass
    # intentar compilar
    import build_lib
    p = build_lib.compilar()
    return ctypes.CDLL(str(p))


L = _cargar()
L.sh_str2mc.argtypes = [ctypes.c_char_p]
L.sh_struct_name.restype = ctypes.c_char_p
L.sh_biome_name.restype = ctypes.c_char_p
L.sh_biome_name.argtypes = [ctypes.c_int, ctypes.c_int]
L.sh_supported.argtypes = [ctypes.c_int, ctypes.c_int]
L.sh_region_blocks.argtypes = [ctypes.c_int, ctypes.c_int]
L.sh_biome_ok.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
L.sh_new.restype = ctypes.c_void_p
L.sh_new.argtypes = [ctypes.c_int, ctypes.c_uint64, ctypes.c_int]
L.sh_free.argtypes = [ctypes.c_void_p]
L.sh_scan.argtypes = ([ctypes.c_void_p] + [ctypes.c_int] * 8 +
                      [ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.c_int), ctypes.c_int])


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


def estructuras_soportadas(version: str, dim=None):
    """Estructuras que existen en esa version y (si se indica) en esa dimension (-1, 0, 1)."""
    mc = mc_id(version)
    return [(sid, nombre) for sid, nombre in ESTRUCTURAS
            if L.sh_supported(sid, mc) and (dim is None or L.sh_supported(sid, mc) - 2 == dim)]


def dimension(sid: int, version: str) -> int:
    return L.sh_supported(sid, mc_id(version)) - 2


def biomas_validos(sid: int, version: str):
    """Biomas donde la estructura PUEDE aparecer: lista de (id, nombre)."""
    mc = mc_id(version)
    out = []
    for b in range(0, 256):
        nm = L.sh_biome_name(mc, b)
        if nm and L.sh_biome_ok(mc, sid, b):
            out.append((b, nm.decode()))
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


class Escaneo:
    """Escanea por filas de regiones, dentro de una o mas cajas (bounding boxes) y solo en los
    biomas elegidos. Cada 'lote' de N estructuras encontradas se publica y se guarda en el JSON."""

    def __init__(self, version, seed, sid, radio, lote, salida, cajas=None, biomas=None,
                 hilos=None, on_lote=None, on_progreso=None):
        self.version, self.seed, self.sid = version, seed, sid
        self.mc = mc_id(version)
        self.dim = dimension(sid, version)
        # En el Nether el world border vanilla se escala 1:8
        self.radio_dim = radio // 8 if self.dim == -1 else radio
        self.radio = radio
        self.lote = max(1, lote)
        self.salida = Path(salida)
        self.hilos = hilos or max(1, os.cpu_count() or 2)
        self.on_lote, self.on_progreso = on_lote, on_progreso
        self.biomas = set(biomas) if biomas else None
        self.cajas = self._normalizar_cajas(cajas)
        self.stop = threading.Event()
        self.resultados = []
        self._vistos = set()
        self.regiones_hechas = 0
        self.regiones_total = 0
        self.t0 = 0.0
        self.t_fin = 0.0
        self._lock = threading.Lock()
        self._pend = 0

    def _normalizar_cajas(self, cajas):
        R = self.radio_dim
        if not cajas:
            return [(-R, -R, R, R)]
        out = []
        for x0, z0, x1, z1 in cajas:
            x0, x1 = sorted((int(x0), int(x1)))
            z0, z1 = sorted((int(z0), int(z1)))
            x0, z0, x1, z1 = max(x0, -R), max(z0, -R), min(x1, R), min(z1, R)
            if x0 <= x1 and z0 <= z1:
                out.append((x0, z0, x1, z1))
        if not out:
            raise ValueError("Ninguna caja cae dentro del world border")
        return out

    def _mascara(self):
        if self.biomas is None:
            return None
        m = (ctypes.c_ubyte * 256)()
        for b in self.biomas:
            if 0 <= b < 256:
                m[b] = 1
        return m

    def _fila(self, caja, rb, rz, rx0, rx1, mask):
        if self.stop.is_set():
            return
        x0, z0, x1, z1 = caja
        h = L.sh_new(self.mc, self.seed, self.sid)
        buf = (ctypes.c_int * (3 * 4096))()
        try:
            n = L.sh_scan(h, rx0, rz, rx1, rz, x0, z0, x1, z1, mask, buf, 4096)
            items = [(buf[i*3], buf[i*3+1], buf[i*3+2]) for i in range(n)]
        finally:
            L.sh_free(h)
        publicar = False
        with self._lock:
            self.regiones_hechas += (rx1 - rx0 + 1)
            for x, z, b in items:
                if (x, z) in self._vistos:   # cajas solapadas
                    continue
                self._vistos.add((x, z))
                nm = L.sh_biome_name(self.mc, b)
                self.resultados.append({"x": x, "z": z, "biome": nm.decode() if nm else str(b)})
                self._pend += 1
            if self._pend >= self.lote:
                self._pend = 0
                publicar = True
        if publicar:
            self._guardar(parcial=True)
            if self.on_lote:
                self.on_lote(len(self.resultados))
        if self.on_progreso:
            self.on_progreso(self.regiones_hechas, self.regiones_total)

    def run(self):
        rb = L.sh_region_blocks(self.sid, self.mc)
        mask = self._mascara()
        trabajos = []
        for caja in self.cajas:
            x0, z0, x1, z1 = caja
            rx0, rx1, rz0, rz1 = x0 // rb, x1 // rb, z0 // rb, z1 // rb
            self.regiones_total += (rx1 - rx0 + 1) * (rz1 - rz0 + 1)
            for rz in range(rz0, rz1 + 1):
                trabajos.append((caja, rb, rz, rx0, rx1, mask))
        # filas cercanas al centro primero: resultados utiles enseguida
        trabajos.sort(key=lambda t: abs(t[2]))
        self.t0 = time.time()
        with ThreadPoolExecutor(max_workers=self.hilos) as ex:
            for f in [ex.submit(self._fila, *t) for t in trabajos]:
                f.result()
        self.t_fin = time.time()
        self._guardar(parcial=self.stop.is_set())
        if self.on_lote:
            self.on_lote(len(self.resultados))
        return self.resultados

    def _guardar(self, parcial=False):
        with self._lock:
            res = sorted(self.resultados, key=lambda d: d["x"] ** 2 + d["z"] ** 2)
            data = {
                "seed": seed_firmada(self.seed),
                "version": self.version,
                "structure": L.sh_struct_name(self.sid).decode(),
                "dimension": DIM_NOMBRE[self.dim],
                "world_border_radius": self.radio,
                "bounding_boxes": [{"x1": a, "z1": b, "x2": c2, "z2": d} for a, b, c2, d in self.cajas],
                "biomes_filter": (sorted(L.sh_biome_name(self.mc, b).decode() for b in self.biomas
                                         if L.sh_biome_name(self.mc, b)) if self.biomas else "all_valid"),
                "scan_complete": not parcial,
                "count": len(res),
                "structures": res,
            }
        tmp = self.salida.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.salida)


def notificar(titulo: str, mensaje: str):
    """Aviso del sistema (sonido + notificacion de escritorio si el SO lo permite). Nunca lanza errores."""
    import shutil, subprocess
    try:
        if os.name == "nt":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  f"$n.ShowBalloonTip(10000,'{titulo}','{mensaje}',[System.Windows.Forms.ToolTipIcon]::Info);"
                  "Start-Sleep -Seconds 11;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             creationflags=0x08000000)
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'display notification "{mensaje}" with title "{titulo}"'])
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", titulo, mensaje])
    except Exception:
        pass
