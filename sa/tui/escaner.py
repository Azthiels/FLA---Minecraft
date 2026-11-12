"""Pantalla 1: escaner."""
import os, time

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, ProgressBar, Select, Static

from sa import RAIZ, clima, config, estructuras, nativo, util
from sa.escaner import Escaneo, ReanudarError, SalidaExisteError
from sa.tui.comunes import BiomasScreen, CajasScreen, entero, valor


class PanelEscaner(Horizontal):
    def __init__(self, prefill=None, **kw):
        super().__init__(**kw)
        self.prefill = prefill or {}
        self.escaneo = None
        self.corriendo = False
        self.biomas_sel = None   # None = todos los biomas validos; si no, set de ids
        self.cajas = []          # [] = mundo completo
        self._mostradas = -1
        self.al_terminar = None  # callback(escaneo) que pone la App

    def compose(self) -> ComposeResult:
        with Vertical(classes="form"):
            yield Label("Seed (numero o texto)")
            yield Input(placeholder="ej: -4172144997902289642", id="seed")
            yield Label("Version del juego")
            yield Select([(nativo.VERSIONES_LABEL.get(v, v), v) for v in nativo.VERSIONES],
                         value=nativo.VERSIONES[-1], allow_blank=False, id="version")
            yield Label("Dimension")
            yield Select([("Overworld", 0), ("Nether", -1), ("End", 1)], value=0, allow_blank=False, id="dimension")
            yield Label("Estructura (solo UNA a la vez)")
            yield Select([], id="estructura", prompt="Elegi una estructura")
            yield Button("Biomas: todos los validos", id="btn_biomas")
            yield Label("Radio del world border (bloques desde 0,0)")
            yield Input(value=str(nativo.BORDE_MAX), id="borde")
            yield Button("Bounding boxes: mundo completo", id="btn_cajas")
            yield Label("Que guardar")
            yield Select([("Solo agrupables (para granjas, rapido)", "grupos"), ("Todas las estructuras", "todas")],
                         value=config.MODO, allow_blank=False, id="modo")
            with Horizontal(id="fila_grupo", classes="fila"):
                with Vertical():
                    yield Label("Radio activacion")
                    yield Input(value=str(config.RADIO_ACTIVACION), id="radio_g")
                with Vertical():
                    yield Label("Lado caja")
                    yield Input(value="16", id="lado")
            yield Checkbox("Prefiltro de clima 1.18+ (exacto, mas rapido)", value=config.CLIMA, id="clima")
            yield Label("Lote de escritura (registros)")
            yield Input(value=str(config.BATCH_SIZE), id="lote")
            yield Label(f"Hilos de calculo (este equipo: {os.cpu_count() or 1})")
            yield Input(value=str(os.cpu_count() or 1), id="hilos")
            yield Label("Salida (nombre base: .sab + .meta.json + .checkpoint.json)")
            yield Input(value=str(RAIZ / "escaneo"), id="salida")
            yield Checkbox("Sobrescribir salida previa (empezar de cero)", id="sobrescribir")
            yield Button("Iniciar / reanudar escaneo", variant="success", id="go")
            yield Static("", id="info", classes="info")
        with Vertical(classes="derecha"):
            yield Static("Listo. Completa los datos y presiona Iniciar.\n"
                         "Si ya existe un checkpoint con los mismos parametros, el escaneo se reanuda solo.\n\n"
                         "[b]Solo agrupables[/b]: guarda solo las estructuras que tienen otra con la que se pueden activar "
                         "a la vez (mismo resultado que guardar todas y pasar el limpiador, pero se saltea el calculo "
                         "de bioma de las aisladas: ~10-15x mas rapido).", id="stats", classes="estado")
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield DataTable(id="tabla")

    def on_mount(self):
        t = self.query_one("#tabla", DataTable)
        t.add_columns("#", "X", "Z", "Bioma")
        t.cursor_type = "row"
        t.border_title = f"Ultimos {config.RECENT_ROWS} registros"
        self._refrescar_estructuras()
        self.set_interval(0.5, self._tick)
        if self.prefill:
            self.run_worker(self._aplicar_prefill(), group="prefill")

    async def _aplicar_prefill(self):
        """Completa el formulario desde la linea de comandos (python main.py --seed ... --iniciar)."""
        import asyncio
        p = self.prefill
        sid, ver = p.get("estructura"), p.get("version") or self._version()
        self.query_one("#version", Select).value = ver
        if sid is not None:
            self.query_one("#dimension", Select).value = nativo.dimension(sid, ver)
        await asyncio.sleep(0.3)                 # que se procesen los Select.Changed (refrescan la lista)
        if sid is not None:
            self.query_one("#estructura", Select).value = sid
        await asyncio.sleep(0.3)
        campos = {"seed": "#seed", "borde": "#borde", "radio_grupo": "#radio_g", "lado": "#lado", "lote": "#lote",
                  "hilos": "#hilos", "salida": "#salida"}
        for k, sel in campos.items():
            if p.get(k) is not None:
                self.query_one(sel, Input).value = str(p[k])
        if p.get("modo"):
            self.query_one("#modo", Select).value = p["modo"]
        if p.get("clima") is not None:
            self.query_one("#clima", Checkbox).value = bool(p["clima"])
        if p.get("sobrescribir"):
            self.query_one("#sobrescribir", Checkbox).value = True
        await asyncio.sleep(0.2)
        if p.get("iniciar"):
            self._go()

    def _refrescar_clima(self):
        sid, ver = self._sid(), self._version()
        cb = self.query_one("#clima", Checkbox)
        cb.display = nativo.es_118_o_mas(ver)
        if sid is not None and cb.display:
            ok = clima.disponible(sid, ver)
            cb.disabled = not ok
            cb.tooltip = (None if ok else "No aplica a esta estructura/version (solo estructuras con un unico chequeo "
                          "de bioma, y versiones donde se verifica la cobertura del arbol de clima)")

    # ---------- helpers ----------
    def _sid(self):
        return valor(self.query_one("#estructura", Select))

    def _dim(self):
        return self.query_one("#dimension", Select).value

    def _version(self):
        return self.query_one("#version", Select).value

    def _radio_dim(self):
        try:
            r = int(self.query_one("#borde", Input).value)
        except ValueError:
            r = nativo.BORDE_MAX
        return nativo.limite_dimension(self._dim(), r)

    def _resumen_biomas(self):
        if self.biomas_sel is None:
            return "todos los biomas validos para la estructura"
        nombres = sorted(nativo.nombre_bioma(self._version(), b) for b in self.biomas_sel)
        return f"{len(nombres)} elegidos: " + ", ".join(nombres)

    def _etiquetas(self):
        self.query_one("#btn_biomas", Button).label = (
            "Biomas: todos los validos" if self.biomas_sel is None else f"Biomas: {len(self.biomas_sel)} elegidos")
        self.query_one("#btn_cajas", Button).label = (
            "Bounding boxes: mundo completo" if not self.cajas else f"Bounding boxes: {len(self.cajas)} caja(s)")

    # ---------- formulario ----------
    def _refrescar_estructuras(self):
        sel = self.query_one("#estructura", Select)
        opts = [(n, sid) for sid, n in nativo.estructuras_soportadas(self._version(), self._dim())]
        sel.set_options(opts)
        self.biomas_sel = None
        self._etiquetas()
        self._refrescar_clima()
        self.query_one("#info", Static).update("" if opts else "No hay estructuras para esta dimension en esta version.")

    @on(Select.Changed, "#version")
    @on(Select.Changed, "#dimension")
    def _ver_cambio(self, _):
        self.cajas = []          # las coordenadas dependen de la dimension
        self._refrescar_estructuras()

    @on(Select.Changed, "#modo")
    def _modo_cambio(self, ev):
        self.query_one("#fila_grupo").display = ev.value == "grupos"

    @on(Select.Changed, "#estructura")
    def _est_cambio(self, ev):
        sid = valor(ev.select)
        if sid is None:
            return
        self.biomas_sel = None
        self._refrescar_clima()
        caja = estructuras.caja(sid)
        self.query_one("#lado", Input).value = str(caja.lado)
        b = [n for _, n in nativo.biomas_validos(sid, self._version())]
        self._etiquetas()
        teo = estructuras.maximo_teorico(sid, self._version(), config.RADIO_ACTIVACION, caja.lado)
        self.query_one("#info", Static).update(
            f"Biomas posibles: {', '.join(b) if b else '(segun terreno/dimension)'}.\n"
            f"Caja para grupos: {caja.nota}{'' if caja.exacta else ' [aprox.]'}\n"
            f"Region: {nativo.region_bloques(sid, self._version())} bloques -> como mucho {teo} juntas con radio "
            f"{config.RADIO_ACTIVACION}.")

    @on(Button.Pressed, "#btn_biomas")
    def _abrir_biomas(self):
        sid = self._sid()
        if sid is None:
            self.notify("Primero elegi una estructura", severity="warning")
            return
        biomas = nativo.biomas_validos(sid, self._version())
        if not biomas:
            self.notify("Esta estructura no depende de biomas elegibles", severity="information")
            return

        def listo(res):
            if res is not False:
                self.biomas_sel = res
                self._etiquetas()
        self.app.push_screen(BiomasScreen(biomas, self.biomas_sel), listo)

    @on(Button.Pressed, "#btn_cajas")
    def _abrir_cajas(self):
        def listo(res):
            if res is not False:
                self.cajas = res
                self._etiquetas()
        self.app.push_screen(CajasScreen(self.cajas, nativo.DIM_NOMBRE[self._dim()], self._radio_dim()), listo)

    # ---------- escaneo ----------
    def _mensaje(self, txt):
        self.query_one("#stats", Static).update(txt)

    def detener(self):
        if self.corriendo and self.escaneo:
            self.escaneo.stop.set()

    @on(Button.Pressed, "#go")
    def _go(self):
        if self.corriendo:
            self.escaneo.stop.set()
            self.query_one("#go", Button).label = "Deteniendo (guardando)..."
            return
        try:
            seed = nativo.parse_seed(self.query_one("#seed", Input).value)
            sid = self._sid()
            if sid is None:
                raise ValueError("Elegi una estructura")
            radio = entero(self.query_one("#borde", Input), "Radio del border")
            lote = entero(self.query_one("#lote", Input), "Lote")
            hilos = entero(self.query_one("#hilos", Input), "Hilos")
            modo = self.query_one("#modo", Select).value
            rg = entero(self.query_one("#radio_g", Input), "Radio de activacion")
            lado = entero(self.query_one("#lado", Input), "Lado de la caja")
            salida = self.query_one("#salida", Input).value.strip()
            if not salida:
                raise ValueError("Falta la ruta de salida")
            cb = self.query_one("#clima", Checkbox)
            self.escaneo = Escaneo(self._version(), seed, sid, radio, salida, cajas=self.cajas or None,
                                   biomas=self.biomas_sel, hilos=hilos, lote=lote, modo=modo, radio_grupo=rg, lado=lado,
                                   clima=cb.value and cb.display and not cb.disabled,
                                   sobrescribir=self.query_one("#sobrescribir", Checkbox).value)
        except ValueError as e:
            self._mensaje(f"[red]Error:[/red] {e}")
            return
        self.query_one("#tabla", DataTable).clear()
        self._mostradas = -1
        self.corriendo = True
        self.query_one("#go", Button).label = "Detener (guarda y deja checkpoint)"
        self.run_worker(self._correr, thread=True, exclusive=True, group="escaneo")

    def _correr(self):
        err = None
        try:
            self.escaneo.run()
        except (ReanudarError, SalidaExisteError, OSError) as ex:
            err = str(ex)
        finally:
            self.app.call_from_thread(self._fin, err)

    def _fin(self, err=None):
        self.corriendo = False
        self.query_one("#go", Button).label = "Iniciar / reanudar escaneo"
        e = self.escaneo
        if err:
            self._mensaje(f"[red]No se pudo iniciar:[/red] {err}")
            self.notify(err, title="Escaneo no iniciado", severity="error", timeout=20)
        else:
            self._tick(forzar=True)
            r = e.resumen()
            total_t = util.fmt_t(e.tiempo())
            archivos = "\n".join(f"  {k}: {v}" for k, v in r["archivos"].items())
            if e.estado == "completado":
                color, titulo, sev = "green", "ESCANEO COMPLETADO", "information"
            elif e.estado == "interrumpido":
                color, titulo, sev = "yellow", "ESCANEO INTERRUMPIDO (se puede reanudar)", "warning"
            else:
                color, titulo, sev = "red", f"ESCANEO CON ERRORES: {e.error}", "error"
            msg = f"{e.escritas:,} estructuras en {total_t}"
            sig = ("\nSiguiente paso: pestana [b]3 Analizador[/b] (el archivo ya esta cargado)." if e.modo == "grupos"
                   else "\nSiguiente paso: pestana [b]2 Limpiador[/b] (el archivo ya esta cargado).")
            self._mensaje(f"[b {color}]{titulo}[/b {color}]\nEstructuras guardadas: {e.escritas:,}  (modo {e.modo})\n"
                          f"Tiempo total: {total_t}   Regiones: {r['regiones']:,}/{r['regiones_total']:,}\n"
                          f"Archivos:\n{archivos}{sig}")
            self.app.bell()
            self.notify(f"{msg}\n{e.rutas['datos']}", title=titulo.split(" (")[0].title(), timeout=60, severity=sev)
            util.notificar(titulo.split(" (")[0].title(), msg)
            if self.al_terminar and e.estado in ("completado", "interrumpido"):
                self.al_terminar(e)
        if getattr(self.app, "saliendo", False):
            self.app.exit()

    def _tick(self, forzar=False):
        e = self.escaneo
        if not e or (not self.corriendo and not forzar):
            return
        hechas, total = e.regiones_hechas, e.regiones_total
        self.query_one("#bar", ProgressBar).update(total=total, progress=hechas)
        if self.corriendo:
            el = time.time() - e.t0
            vel = e.regiones_sesion / el if el > 0.5 else 0
            falta = total - hechas
            eta = falta / vel if vel else float("inf")
            st = dict(zip(nativo.STAT_NAMES, e._stats_total()))
            area = ("mundo completo" if not e.cajas_usuario else f"{len(e.cajas_usuario)} caja(s)") + f" (limite +-{e.limite:,})"
            hil = "".join("[green]#[/green]" if t is not None else "[dim].[/dim]" for t in list(e.estado_hilos))
            biomas = "todos los validos" if e.biomas is None else f"{len(e.biomas)} elegidos"
            pos = max(1, st["in_box"])
            ahorro = f"   bioma completo en {100 * st['viable_calls'] / pos:.2f}% de las posiciones"
            if e.clima:
                ahorro += f" (clima descarto {st['climate_rejected']:,})"
            self._mensaje(
                f"[b]{nativo.nombre_estructura(e.sid)}[/b] | {nativo.DIM_NOMBRE[e.dim]} | {e.version} | "
                f"seed {nativo.seed_firmada(e.seed)} | modo {e.modo}{' + clima' if e.clima else ''}\n"
                f"Area: {area}   Biomas: {biomas}\n"
                f"Regiones: {hechas:,}/{total:,}  (restan {falta:,})  {100*hechas/max(1,total):.2f}%\n"
                f"Guardadas: {e.encontradas:,} (escritas {e.escritas:,})   {vel:,.0f} reg/s{ahorro}\n"
                f"Transcurrido {util.fmt_t(e.tiempo())}   ETA {util.fmt_t(eta)}\n"
                f"Hilos {len(e.estado_hilos)}: {hil}   {'(reanudado)' if e.reanudado else ''}")
        if e.encontradas != self._mostradas:
            self._mostradas = e.encontradas
            t = self.query_one("#tabla", DataTable)
            t.clear()
            for i, (x, z, b) in enumerate(list(e.ultimos)[::-1]):
                t.add_row(str(e.encontradas - i), str(x), str(z), b)
