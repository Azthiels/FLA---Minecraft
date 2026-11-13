"""Motor de escaneo.

  planificacion  : cajas -> rectangulos disjuntos -> tiles de regiones, orden centro->afuera (sa.escaner.plan)
  calculo        : N hilos, cada uno con su propio generador nativo (cubiomes) que reutiliza entre tiles
  modo grupos    : en C, solo se consulta el bioma de las posiciones con alguna vecina posible y solo se guardan
                   las que tienen una vecina valida (= escanear todo + limpiador, pero ~10-15x mas rapido)
  almacenamiento : UN hilo escritor dueno del .sab (registros binarios tal cual salen de C); buffer de lote
  recuperacion   : checkpoint (tiles confirmados + tamano del .sab) para reanudar sin duplicados

Garantia (exactly-once): un tile solo se "confirma" cuando sus registros ya estan escritos y volcados (o cuando
no tiene registros). El checkpoint guarda los tiles confirmados y el tamano en bytes del archivo en ese instante,
tras un fsync. Al reanudar se trunca el archivo a ese tamano y los tiles no confirmados se re-escanean (la
generacion es determinista): sin duplicados ni huecos aunque el proceso muera a mitad de una escritura.
"""
import collections, ctypes, itertools, json, os, queue, threading, time

import numpy as np

from sa import clima as clima_mod
from sa import config, datos, estructuras, nativo, util
from sa.i18n import t
from sa.nativo import L
from sa.escaner.plan import Plan, descomponer, normalizar_cajas

FORMAT_VERSION = 2
ESTADOS = ("en_ejecucion", "interrumpido", "completado", "error")
MODOS = ("grupos", "todas")
_SENT = object()


class ReanudarError(Exception):
    """El checkpoint existente no corresponde a los parametros pedidos."""


class SalidaExisteError(Exception):
    """Ya hay resultados en esa ruta y no se pidio reanudar ni sobrescribir."""


class Escaneo:
    def __init__(self, version, seed, sid, radio, salida, cajas=None, biomas=None, hilos=None,
                 lote=None, tile=None, flush_s=None, ckpt_s=None, reanudar=True, sobrescribir=False,
                 terreno=True, flags_extra=0, modo=None, radio_grupo=None, lado=None, clima=None):
        self.version, self.seed, self.sid = version, seed, sid
        self.mc = nativo.mc_id(version)
        if not L.sh_supported(sid, self.mc):
            raise ValueError(t("err.estructura_version"))
        self.dim = nativo.dimension(sid, version)
        self.radio = int(radio)
        if self.radio <= 0:
            raise ValueError(t("err.radio_borde"))
        self.limite = nativo.limite_dimension(self.dim, self.radio)
        self.cajas_usuario = [tuple(c) for c in cajas] if cajas else []
        self.cajas = normalizar_cajas(cajas, self.limite)
        self.rects = descomponer(self.cajas)
        self.biomas = None if biomas is None else sorted(set(int(b) for b in biomas))
        if self.biomas is not None and not self.biomas:
            raise ValueError(t("err.un_bioma"))
        self.mask = nativo.mascara_biomas(self.biomas)
        self.modo = modo or config.MODO
        if self.modo not in MODOS:
            raise ValueError(t("err.modo", m=self.modo))
        caja = estructuras.caja(sid)
        self.radio_grupo = int(radio_grupo if radio_grupo is not None else config.RADIO_ACTIVACION)
        self.lado = int(lado if lado is not None else caja.lado)
        self.offset = caja.offset
        if self.modo == "grupos" and (self.radio_grupo <= 0 or self.lado <= 0):
            raise ValueError(t("err.grupo_pos"))
        # prefiltro de clima: no cambia resultados, asi que no forma parte de la identidad (se puede alternar al reanudar)
        self.clima_pedido = config.CLIMA if clima is None else bool(clima)
        self.clima = self.clima_pedido and clima_mod.disponible(sid, version)
        self.rutas = datos.rutas(datos.resolver(salida))
        self.hilos = max(1, int(hilos or os.cpu_count() or 1))
        self.lote = max(1, int(lote or config.BATCH_SIZE))
        self.T = max(1, int(tile or config.TILE_REGIONS))
        self.flush_s = float(flush_s if flush_s is not None else config.FLUSH_INTERVAL_S)
        self.ckpt_s = float(ckpt_s if ckpt_s is not None else config.CHECKPOINT_INTERVAL_S)
        self.reanudar, self.sobrescribir = reanudar, sobrescribir
        self.terreno = terreno
        self.flags = (0 if terreno else nativo.F_NO_TERRAIN) | flags_extra | \
            (nativo.F_GROUPS if self.modo == "grupos" else 0)
        self.rb = L.sh_region_blocks(sid, self.mc)
        self.plan = Plan(self.rects, self.rb, self.T)
        self.rects = self.plan.rects      # mismo orden que usa el plan (indices de rect)
        self.regiones_total = self.plan.total_regions
        self.tiles_total = self.plan.total_tiles
        self._boxes = (ctypes.c_int * (4 * len(self.cajas)))(*[v for c in self.cajas for v in c])
        # ---- estado observable (la TUI lo lee) ----
        self.estado = "en_ejecucion"
        self.error = None
        self.stop = threading.Event()
        self._base_hechas = 0             # regiones confirmadas en ejecuciones previas (reanudacion)
        self._reg_w = [0] * self.hilos    # regiones escaneadas por cada hilo (un solo escritor por casilla)
        self.encontradas = 0              # incluye lo que aun esta en el buffer
        self.escritas = 0                 # ya volcadas al archivo
        self.n_escrituras = 0
        self.n_checkpoints = 0
        self._w_ult = None
        self.escritura_min_previa = None  # minimo tamano de escritura entre todas menos la ultima (verifica el lote)
        self.tiles_confirmados = 0
        self.ultimos = collections.deque(maxlen=config.RECENT_ROWS)
        self.estado_hilos = [None] * self.hilos
        self.t0 = 0.0
        self.t_fin = 0.0
        self.previo_s = 0.0
        self.reanudado = False
        self.inicio_iso = None
        self.fin_iso = None
        self.stats_prev = [0] * nativo.NSTAT
        self.stats_final = None
        self._handles = []
        self._q = queue.Queue(maxsize=config.QUEUE_PER_WORKER * self.hilos)
        self._lk_plan = threading.Lock()
        self._it = None
        self._skip = set()
        self._biomas = nativo.tabla_biomas(version)

    # ---------- identidad del escaneo (para validar la reanudacion) ----------
    def identidad(self) -> dict:
        ident = {"format": FORMAT_VERSION, "seed": nativo.seed_firmada(self.seed), "version": self.version,
                 "structure": self.sid, "dimension": self.dim, "limit": self.limite,
                 "rects": [list(r) for r in self.rects], "biomes": self.biomas, "tile": self.T,
                 "terrain_heuristic": bool(self.terreno), "mode": self.modo}
        if self.modo == "grupos":
            ident["group"] = {"radius": self.radio_grupo, "side": self.lado}
        return ident

    def _nombre(self, b):
        return self._biomas.get(b, f"id_{b}")

    # ---------- metadatos / checkpoint ----------
    def _stats_total(self):
        tot = list(self.stats_prev)
        buf = (ctypes.c_uint64 * nativo.NSTAT)()
        for h in list(self._handles):
            L.sh_stats(h, buf)
            for i in range(nativo.NSTAT):
                tot[i] += buf[i]
        return tot

    @property
    def regiones_sesion(self):
        return sum(self._reg_w)

    @property
    def regiones_hechas(self):
        return self._base_hechas + sum(self._reg_w)

    def tiempo(self):
        fin = self.t_fin or time.time()
        return self.previo_s + (fin - self.t0 if self.t0 else 0.0)

    def _meta(self):
        validos = [n for _, n in nativo.biomas_validos(self.sid, self.version)]
        st = dict(zip(nativo.STAT_NAMES, self._stats_total()))
        caja = estructuras.caja(self.sid)
        return {
            "format_version": FORMAT_VERSION,
            "kind": "escaneo",
            "status": self.estado,
            "error": self.error,
            "seed": nativo.seed_firmada(self.seed),
            "minecraft_version": self.version,
            "structure": {"id": self.sid, "name": nativo.nombre_estructura(self.sid),
                          "generation_config": nativo.config_estructura(self.sid, self.version),
                          "region_blocks": self.rb},
            "dimension": nativo.DIM_NOMBRE[self.dim],
            "world_border_radius": self.radio,
            "dimension_limit": self.limite,
            "mode": self.modo,
            "group": ({"radius": self.radio_grupo, "side": self.lado, "offset": self.offset,
                       "box_exact": caja.exacta, "note": caja.nota} if self.modo == "grupos" else None),
            "bounding_boxes_requested": [list(c) for c in self.cajas_usuario] or "full_world",
            "bounding_boxes_clamped": [list(c) for c in self.cajas],
            "scan_rectangles_disjoint": [list(r) for r in self.rects],
            "biome_filter": {"mode": "all_valid" if self.biomas is None else "subset",
                             "selected": None if self.biomas is None else [self._nombre(b) for b in self.biomas],
                             "rule_valid_biomes": validos},
            "counts": {"structures_found": self.escritas, "regions_processed": self.regiones_confirmadas,
                       "regions_total": self.regiones_total, "tiles_confirmed": self.tiles_confirmados,
                       "tiles_total": self.tiles_total},
            "started_at": self.inicio_iso, "finished_at": self.fin_iso,
            "elapsed_seconds": round(self.tiempo(), 3), "resumed": self.reanudado,
            "parameters": {"workers": self.hilos, "batch_size": self.lote, "tile_regions": self.T,
                           "flush_interval_s": self.flush_s, "checkpoint_interval_s": self.ckpt_s,
                           "terrain_heuristic": bool(self.terreno), "climate_prefilter": self.clima},
            "native_stats": st,
            "files": {k: self.rutas[k].name for k in ("datos", "meta", "ckpt")},
            "record_format": {"file": "SAB1: 16-byte header + records of 3 little-endian int32 (x, z, biome id)",
                              "x_z": "position returned by getStructurePos (structure start, blocks, coordinates of the dimension)",
                              "biome": "biome id the generation rule validated; names in biome_names",
                              "order": "scan order (tile rings from the origin), not sorted"},
            "biome_names": {str(k): v for k, v in self._biomas.items()},
            "notes": ["Positions come from cubiomes getStructurePos; validity from isViableStructurePos (+ cubiomes terrain heuristic "
                      "for Desert Pyramid / Jungle Temple / Mansion on 1.18+ when terrain_heuristic is true).",
                      "The biome filter is applied in addition to the generation rules, never instead of them.",
                      "mode=grupos keeps only structures with at least one valid neighbour whose square box (side) fits "
                      "together with it inside a circle of the group radius."],
        }

    def _guardar_meta(self):
        util.escritura_atomica(self.rutas["meta"], json.dumps(self._meta(), indent=2))

    def _guardar_ckpt(self, f):
        f.flush()
        os.fsync(f.fileno())
        data = {"format_version": FORMAT_VERSION, "identity": self.identidad(), "status": self.estado,
                "watermark": self._wm, "extra_done": sorted(self._done_extra), "file_bytes": self._bytes,
                "found": self.escritas, "regions_done": self.regiones_confirmadas,
                "tiles_confirmed": self.tiles_confirmados, "elapsed_seconds": round(self.tiempo(), 3),
                "stats": self._stats_total(), "started_at": self.inicio_iso, "saved_at": util.ahora()}
        util.escritura_atomica(self.rutas["ckpt"], json.dumps(data))
        self.n_checkpoints += 1

    # ---------- preparacion (nuevo / reanudar) ----------
    def _preparar(self):
        dt, ck = self.rutas["datos"], self.rutas["ckpt"]
        self._wm, self._done_extra, self._bytes = 0, set(), datos.CABECERA
        self.regiones_confirmadas = 0
        existe = dt.exists() or ck.exists() or self.rutas["meta"].exists()
        if existe and self.reanudar and not self.sobrescribir and ck.exists():
            c = json.loads(ck.read_text(encoding="utf-8"))
            ident, old = self.identidad(), c.get("identity", {})
            difs = [k for k in sorted(set(ident) | set(old)) if ident.get(k) != old.get(k)]
            if difs:
                raise ReanudarError(t("err.ckpt_distinto", campos=", ".join(difs)))
            if not dt.exists() or dt.stat().st_size < c["file_bytes"]:
                raise ReanudarError(t("err.ckpt_corto"))
            with open(dt, "r+b") as f:        # descarta lo escrito despues del ultimo checkpoint (se re-escanea)
                f.truncate(c["file_bytes"])
            self._wm, self._done_extra, self._bytes = c["watermark"], set(c["extra_done"]), c["file_bytes"]
            self.escritas = self.encontradas = c["found"]
            self.regiones_confirmadas = self._base_hechas = c["regions_done"]
            self.tiles_confirmados = c["tiles_confirmed"]
            self.previo_s = c["elapsed_seconds"]
            self.stats_prev = (list(c["stats"]) + [0] * nativo.NSTAT)[:nativo.NSTAT]
            self.inicio_iso, self.reanudado = c.get("started_at") or util.ahora(), True
            self._skip = set(self._done_extra)
        elif existe and not self.sobrescribir:
            raise SalidaExisteError(t("err.existe", f=dt.name))
        else:
            for k in ("datos", "meta", "ckpt"):
                if self.rutas[k].exists():
                    self.rutas[k].unlink()
            dt.parent.mkdir(parents=True, exist_ok=True)
            with open(dt, "wb") as f:
                f.write(datos.cabecera())
            self.inicio_iso = util.ahora()

    # ---------- hilos de calculo ----------
    def _siguiente(self):
        with self._lk_plan:
            if self.stop.is_set():
                return None
            for idx, spec in self._it:
                if idx in self._skip:
                    continue
                return idx, spec
            return None

    def _trabajador(self, wid):
        h = L.sh_new(self.mc, self.seed, self.sid)     # un generador por hilo, reutilizado en todos sus tiles
        if not h:
            self.error = t("err.generador")
            self.stop.set()
            self._q.put(_SENT)
            return
        self._handles.append(h)
        if self.modo == "grupos":
            L.sh_set_groups(h, self.radio_grupo, self.lado, self._boxes, len(self.cajas))
        if self.clima and L.sh_set_climate(h, 1, self.mask) < 0:
            self.clima = False                           # no aplica (no deberia pasar: se chequea antes)
        maxn = self.T * self.T                          # a lo sumo una posicion por region
        buf = (ctypes.c_int * (3 * maxn))()
        rec = datos.DTYPE.itemsize
        try:
            while True:
                nxt = self._siguiente()
                if nxt is None:
                    break
                idx, (ri, rx0, rz0, rx1, rz1) = nxt
                self.estado_hilos[wid] = idx
                x0, z0, x1, z1 = self.rects[ri]
                n = L.sh_scan_tile(h, rx0, rz0, rx1, rz1, x0, z0, x1, z1, self.mask, self.flags, buf, maxn)
                if n < 0:
                    raise RuntimeError("fallo nativo en sh_scan_tile (buffer o memoria)")
                vals = ctypes.string_at(buf, rec * n) if n else b""
                nreg = (rx1 - rx0 + 1) * (rz1 - rz0 + 1)
                self._reg_w[wid] += nreg
                self._q.put((idx, vals, n, nreg))        # bloquea si el escritor va atrasado (contrapresion)
                self.estado_hilos[wid] = None
        except Exception as e:                           # error controlado: parar todo y guardar lo pendiente
            self.error = f"{type(e).__name__}: {e}"
            self.stop.set()
        finally:
            self.estado_hilos[wid] = None
            self._q.put(_SENT)

    # ---------- hilo escritor (unico dueno del archivo) ----------
    def _confirmar(self, idx, nreg):
        self._done_extra.add(idx)
        self.tiles_confirmados += 1
        self.regiones_confirmadas += nreg
        while self._wm in self._done_extra:             # el watermark avanza mientras no haya huecos
            self._done_extra.discard(self._wm)
            self._wm += 1

    def _escritor(self):
        buf, pend = [], []
        nbuf = 0
        f = open(self.rutas["datos"], "ab")
        t_flush = t_ck = time.monotonic()
        fin = 0
        self._guardar_ckpt(f)                       # checkpoint inicial: existe desde el primer momento

        def volcar():
            nonlocal t_flush, nbuf
            if buf:
                data = b"".join(buf)
                f.write(data)
                f.flush()
                self._bytes += len(data)
                self.escritas += nbuf
                self.n_escrituras += 1
                if self._w_ult is not None:
                    m = self.escritura_min_previa
                    self.escritura_min_previa = self._w_ult if m is None else min(m, self._w_ult)
                self._w_ult = nbuf
            for idx, nreg in pend:
                self._confirmar(idx, nreg)
            buf.clear(); pend.clear(); nbuf = 0
            t_flush = time.monotonic()

        try:
            while fin < self.hilos:
                try:
                    item = self._q.get(timeout=0.25)
                except queue.Empty:
                    item = None
                if item is _SENT:
                    fin += 1
                elif item is not None:
                    idx, vals, n, nreg = item
                    if n:
                        buf.append(vals)
                        nbuf += n
                        cola = np.frombuffer(vals, dtype=datos.DTYPE)[-config.RECENT_ROWS:]
                        for x, z, b in cola.tolist():
                            self.ultimos.append((x, z, self._nombre(b)))
                        self.encontradas += n
                        pend.append((idx, nreg))
                        if nbuf >= self.lote:
                            volcar()
                    else:
                        self._confirmar(idx, nreg)       # tile sin registros: no depende de nada pendiente
                now = time.monotonic()
                if buf and now - t_flush >= self.flush_s:
                    volcar()
                if now - t_ck >= self.ckpt_s:
                    self._guardar_ckpt(f)
                    self._guardar_meta()
                    t_ck = time.monotonic()
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.stop.set()
        finally:
            try:
                while fin < self.hilos:                   # si fallo el bucle: drenar para no bloquear a los hilos
                    if self._q.get() is _SENT:
                        fin += 1
                volcar()                                  # guarda lo pendiente (fin normal, parada o error)
                self.t_fin = time.time()
                if self.error:
                    self.estado = "error"
                elif self._wm >= self.tiles_total:
                    self.estado = "completado"
                else:
                    self.estado = "interrumpido"
                self.fin_iso = util.ahora()
                self._guardar_ckpt(f)
                self._guardar_meta()
            except Exception as e:
                self.error = self.error or f"{type(e).__name__}: {e}"
                self.estado = "error"
            finally:
                f.close()

    # ---------- ejecucion ----------
    def run(self):
        self._preparar()
        it = enumerate(iter(self.plan))
        if self._wm:                                      # saltar lo ya confirmado (reanudacion)
            collections.deque(itertools.islice(it, self._wm), maxlen=0)
        self._it = it
        self.t0 = time.time()
        self.estado = "en_ejecucion"
        self._guardar_meta()
        escritor = threading.Thread(target=self._escritor, name="escritor", daemon=True)
        hilos = [threading.Thread(target=self._trabajador, args=(i,), name=f"w{i}", daemon=True)
                 for i in range(self.hilos)]
        escritor.start()
        for t in hilos:
            t.start()
        try:
            for t in hilos:
                while t.is_alive():
                    t.join(0.2)
            escritor.join()
        except KeyboardInterrupt:
            self.stop.set()
            escritor.join()
        st = self._stats_total()
        self.stats_final = dict(zip(nativo.STAT_NAMES, st))
        for h in self._handles:
            L.sh_free(h)
        self._handles.clear()
        self.stats_prev = st
        return self.resumen()

    def resumen(self):
        return {"estado": self.estado, "error": self.error, "encontradas": self.escritas,
                "regiones": self.regiones_confirmadas, "regiones_total": self.regiones_total,
                "segundos": self.tiempo(), "archivos": {k: str(self.rutas[k]) for k in ("datos", "meta", "ckpt")},
                "stats": self.stats_final, "escrituras": self.n_escrituras, "checkpoints": self.n_checkpoints,
                "modo": self.modo, "clima": self.clima}
