"""Pantalla 1: escaner."""
import os, time

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, ProgressBar, Select, Static

from sa import RAIZ, clima, config, estructuras, nativo, util
from sa.escaner import Escaneo, ReanudarError, SalidaExisteError
from sa.tui.comunes import BiomasScreen, CajasScreen, entero, valor


def _campo(etiqueta, widget, clases="", id=None):
    """Celda de la grilla de opciones: etiqueta arriba + control compacto abajo."""
    c = Vertical(Label(etiqueta), widget, classes=("campo " + clases).strip(), id=id)
    return c


class PanelEscaner(Horizontal):
    DEFAULT_CSS = """
    PanelEscaner #izq { width: 1fr; padding: 0 1; }
    PanelEscaner #opciones { grid-size: 3; grid-columns: 1fr 1fr 1fr; grid-gutter: 1 2; height: auto;
                             border: round $primary; padding: 0 1; }
    PanelEscaner .campo { height: auto; }
    PanelEscaner .campo Label { color: $text-muted; }
    PanelEscaner .campo Input, PanelEscaner .campo Select, PanelEscaner .campo Button { width: 100%; }
    PanelEscaner .span2 { column-span: 2; }
    PanelEscaner .span3 { column-span: 3; }
    PanelEscaner #go { width: 100%; }
    PanelEscaner #info { color: $text-muted; height: auto; }
    PanelEscaner #stats { height: auto; margin-top: 1; }
    PanelEscaner #der { width: 52; }
    PanelEscaner #tabla { height: 1fr; border: round $secondary; }
    """

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
        nucleos = os.cpu_count() or 1
        with Vertical(id="izq"):
            with Grid(id="opciones"):
                yield _campo("Seed (numero o texto)", Input(placeholder="ej: -4172144997902289642", id="seed", compact=True), "span2")
                yield _campo("Version", Select([(nativo.VERSIONES_LABEL.get(v, v), v) for v in nativo.VERSIONES],
                                               value=nativo.VERSIONES[-1], allow_blank=False, id="version", compact=True))
                yield _campo("Dimension", Select([("Overworld", 0), ("Nether", -1), ("End", 1)], value=0,
                                                 allow_blank=False, id="dimension", compact=True))
                yield _campo("Estructura (una a la vez)", Select([], id="estructura", prompt="Elegi una estructura",
                                                                 compact=True), "span2")
                yield _campo("Radio del world border", Input(value=str(nativo.BORDE_MAX), id="borde", compact=True))
                yield _campo("Biomas", Button("todos los validos", id="btn_biomas", compact=True))
                yield _campo("Area (bounding boxes)", Button("mundo completo", id="btn_cajas", compact=True))
                yield _campo("Que guardar", Select([("Solo agrupables (rapido)", "grupos"), ("Todas", "todas")],
                                                   value=config.MODO, allow_blank=False, id="modo", compact=True))
                yield _campo("Radio de activacion", Input(value=str(config.RADIO_ACTIVACION), id="radio_g", compact=True))
                yield _campo("Lado de la caja", Input(value="16", id="lado", compact=True))
                yield _campo(f"Hilos (este equipo: {nucleos})", Input(value=str(nucleos), id="hilos", compact=True))
                yield _campo("Lote de escritura", Input(value=str(config.BATCH_SIZE), id="lote", compact=True))
                yield _campo("Salida (nombre base: .sab + .meta.json + .checkpoint.json)",
                             Input(value=str(RAIZ / "escaneo"), id="salida", compact=True), "span3")
                yield Checkbox("Modo auto (1 -> 2 -> 3)", id="auto", compact=True,
                               tooltip="Al terminar el escaneo, limpia (si hace falta) y analiza solo")
                yield Checkbox("Sobrescribir salida previa", id="sobrescribir", compact=True)
                yield Checkbox("Prefiltro de clima 1.18+", value=config.CLIMA, id="clima", compact=True)
                yield Static("", id="info", classes="span3")
                yield Button("Iniciar / reanudar escaneo", variant="success", id="go", classes="span3")
            yield Static("Listo. Completa los datos y presiona Iniciar. Si ya existe un checkpoint con los mismos "
                         "parametros, el escaneo se reanuda solo.\n[b]Solo agrupables[/b]: guarda solo las estructuras "
                         "que tienen otra con la que se pueden activar a la vez (mismo resultado que guardar todas y "
                         "limpiar, mucho mas rapido). [b]Modo auto[/b]: encadena escaner -> limpiador -> analizador.",
                         id="stats")
            yield ProgressBar(total=100, show_eta=False, id="bar")
        with Vertical(id="der"):
            yield DataTable(id="tabla")

    def on_mount(self):
        self.query_one("#opciones").border_title = "Opciones del escaneo"
        t = self.query_one("#tabla", DataTable)
        t.add_columns("#", "X", "Z", "Bioma")
        t.cursor_type = "row"
        t.border_title = "Encontradas (ultimas)"
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
        if p.get("auto"):
            self.query_one("#auto", Checkbox).value = True
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
            "todos los validos" if self.biomas_sel is None else f"{len(self.biomas_sel)} elegidos")
        self.query_one("#btn_cajas", Button).label = (
            "mundo completo" if not self.cajas else f"{len(self.cajas)} caja(s)")

    @property
    def auto(self):
        return self.query_one("#auto", Checkbox).value

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
        for i in ("#radio_g", "#lado"):          # deshabilitar (no ocultar) para no desarmar la grilla
            self.query_one(i, Input).disabled = ev.value != "grupos"

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
            if e.estado == "completado":
                color, titulo, sev = "green", "ESCANEO COMPLETADO", "information"
            elif e.estado == "interrumpido":
                color, titulo, sev = "yellow", "ESCANEO INTERRUMPIDO (se puede reanudar)", "warning"
            else:
                color, titulo, sev = "red", f"ESCANEO CON ERRORES: {e.error}", "error"
            msg = f"{e.escritas:,} estructuras en {total_t}"
            auto = self.auto and e.estado == "completado"
            if auto:
                sig = "\n[b]Modo auto:[/b] sigue el analisis solo."
            elif e.modo == "grupos":
                sig = "\nSiguiente paso: pestana [b]3 Analizador[/b] (el archivo ya esta cargado)."
            else:
                sig = "\nSiguiente paso: pestana [b]2 Limpiador[/b] (el archivo ya esta cargado)."
            self._mensaje(f"[b {color}]{titulo}[/b {color}]   {e.escritas:,} estructuras guardadas (modo {e.modo})\n"
                          f"Tiempo total: {total_t}   Regiones: {r['regiones']:,}/{r['regiones_total']:,}\n"
                          f"Archivo: {r['archivos']['datos']}{sig}")
            if not auto:                          # en modo auto el aviso llega al final de la cadena
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
