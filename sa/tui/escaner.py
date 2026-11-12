"""Pantalla 1: escaner."""
import os, time

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, ProgressBar, Select, Static

from sa import RAIZ, clima, config, estructuras, nativo, util
from sa.escaner import Escaneo, ReanudarError, SalidaExisteError
from sa.i18n import t
from sa.tui.comunes import BiomasScreen, CajasScreen, entero, valor


def _campo(etiqueta, widget, clases="", id=None):
    """Celda de la grilla de opciones: etiqueta arriba + control compacto abajo."""
    return Vertical(Label(etiqueta), widget, classes=("campo " + clases).strip(), id=id)


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
                yield _campo(t("esc.seed"), Input(placeholder=t("esc.seed_ej"), id="seed", compact=True), "span2")
                yield _campo(t("esc.version"), Select([(nativo.VERSIONES_LABEL.get(v, v), v) for v in nativo.VERSIONES],
                                                      value=nativo.VERSIONES[-1], allow_blank=False, id="version",
                                                      compact=True))
                yield _campo(t("esc.dimension"), Select([("Overworld", 0), ("Nether", -1), ("End", 1)], value=0,
                                                        allow_blank=False, id="dimension", compact=True))
                yield _campo(t("esc.estructura"), Select([], id="estructura", prompt=t("esc.elegi"), compact=True), "span2")
                yield _campo(t("esc.borde"), Input(value=str(nativo.BORDE_MAX), id="borde", compact=True))
                yield _campo(t("esc.biomas"), Button(t("esc.todos_validos"), id="btn_biomas", compact=True))
                yield _campo(t("esc.area"), Button(t("esc.mundo"), id="btn_cajas", compact=True))
                yield _campo(t("esc.que"), Select([(t("esc.modo_grupos"), "grupos"), (t("esc.modo_todas"), "todas")],
                                                  value=config.MODO, allow_blank=False, id="modo", compact=True))
                yield _campo(t("esc.radio_g"), Input(value=str(config.RADIO_ACTIVACION), id="radio_g", compact=True))
                yield _campo(t("esc.lado"), Input(value="16", id="lado", compact=True))
                yield _campo(t("esc.hilos", n=nucleos), Input(value=str(nucleos), id="hilos", compact=True))
                yield _campo(t("esc.lote"), Input(value=str(config.BATCH_SIZE), id="lote", compact=True))
                yield _campo(t("esc.salida"), Input(value=str(RAIZ / "escaneo"), id="salida", compact=True), "span3")
                yield Checkbox(t("esc.auto"), id="auto", compact=True, tooltip=t("esc.auto_tip"))
                yield Checkbox(t("esc.sobrescribir"), id="sobrescribir", compact=True)
                yield Checkbox(t("esc.clima"), value=config.CLIMA, id="clima", compact=True)
                yield Static("", id="info", classes="span3")
                yield Button(t("esc.iniciar"), variant="success", id="go", classes="span3")
            yield Static(t("esc.ayuda"), id="stats")
            yield ProgressBar(total=100, show_eta=False, id="bar")
        with Vertical(id="der"):
            yield DataTable(id="tabla")

    def on_mount(self):
        self.query_one("#opciones").border_title = t("esc.opciones")
        tb = self.query_one("#tabla", DataTable)
        tb.add_columns("#", "X", "Z", t("esc.col_bioma"))
        tb.cursor_type = "row"
        tb.border_title = t("esc.encontradas")
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
            cb.tooltip = None if ok else t("esc.clima_no")

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

    def _etiquetas(self):
        self.query_one("#btn_biomas", Button).label = (
            t("esc.todos_validos") if self.biomas_sel is None else t("esc.n_elegidos", n=len(self.biomas_sel)))
        self.query_one("#btn_cajas", Button).label = (
            t("esc.mundo") if not self.cajas else t("esc.n_cajas", n=len(self.cajas)))

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
        self.query_one("#info", Static).update("" if opts else t("esc.sin_estructuras"))

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
        self.query_one("#info", Static).update(t(
            "esc.info", biomas=", ".join(b) if b else t("esc.segun_terreno"), nota=caja.nota,
            aprox="" if caja.exacta else t("esc.aprox"), rb=nativo.region_bloques(sid, self._version()), teo=teo,
            r=config.RADIO_ACTIVACION))

    @on(Button.Pressed, "#btn_biomas")
    def _abrir_biomas(self):
        sid = self._sid()
        if sid is None:
            self.notify(t("esc.primero_estructura"), severity="warning")
            return
        biomas = nativo.biomas_validos(sid, self._version())
        if not biomas:
            self.notify(t("esc.sin_biomas"), severity="information")
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
            self.query_one("#go", Button).label = t("esc.deteniendo")
            return
        try:
            seed = nativo.parse_seed(self.query_one("#seed", Input).value)
            sid = self._sid()
            if sid is None:
                raise ValueError(t("esc.falta_estructura"))
            radio = entero(self.query_one("#borde", Input), t("esc.f_borde"))
            lote = entero(self.query_one("#lote", Input), t("esc.f_lote"))
            hilos = entero(self.query_one("#hilos", Input), t("esc.f_hilos"))
            modo = self.query_one("#modo", Select).value
            rg = entero(self.query_one("#radio_g", Input), t("esc.f_radio_g"))
            lado = entero(self.query_one("#lado", Input), t("esc.f_lado"))
            salida = self.query_one("#salida", Input).value.strip()
            if not salida:
                raise ValueError(t("esc.falta_salida"))
            cb = self.query_one("#clima", Checkbox)
            self.escaneo = Escaneo(self._version(), seed, sid, radio, salida, cajas=self.cajas or None,
                                   biomas=self.biomas_sel, hilos=hilos, lote=lote, modo=modo, radio_grupo=rg, lado=lado,
                                   clima=cb.value and cb.display and not cb.disabled,
                                   sobrescribir=self.query_one("#sobrescribir", Checkbox).value)
        except ValueError as e:
            self._mensaje(f"[red]{t('com.error')}[/red] {e}")
            return
        self.query_one("#tabla", DataTable).clear()
        self._mostradas = -1
        self.corriendo = True
        self.query_one("#go", Button).label = t("esc.detener")
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
        self.query_one("#go", Button).label = t("esc.iniciar")
        e = self.escaneo
        if err:
            self._mensaje(f"[red]{t('esc.no_inicio')}[/red] {err}")
            self.notify(err, title=t("esc.no_inicio_t"), severity="error", timeout=20)
        else:
            self._tick(forzar=True)
            r = e.resumen()
            total_t = util.fmt_t(e.tiempo())
            if e.estado == "completado":
                color, titulo, sev = "green", t("esc.completado"), "information"
            elif e.estado == "interrumpido":
                color, titulo, sev = "yellow", t("esc.interrumpido"), "warning"
            else:
                color, titulo, sev = "red", t("esc.con_errores", e=e.error), "error"
            msg = t("esc.msg_fin", n=e.escritas, t=total_t)
            auto = self.auto and e.estado == "completado"
            sig = t("esc.sig_auto") if auto else (t("esc.sig_3") if e.modo == "grupos" else t("esc.sig_2"))
            self._mensaje(t("esc.resumen_fin", c=color, tit=titulo, n=e.escritas, modo=t(f"modo.{e.modo}"), t=total_t,
                            r=r["regiones"], rt=r["regiones_total"], f=r["archivos"]["datos"], sig=sig))
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
            area = (t("esc.mundo") if not e.cajas_usuario else t("esc.n_cajas", n=len(e.cajas_usuario))) + \
                t("esc.limite", l=e.limite)
            hil = "".join("[green]#[/green]" if h is not None else "[dim].[/dim]" for h in list(e.estado_hilos))
            biomas = t("esc.todos_validos") if e.biomas is None else t("esc.n_elegidos", n=len(e.biomas))
            ahorro = t("esc.ahorro", p=100 * st["viable_calls"] / max(1, st["in_box"]))
            if e.clima:
                ahorro += t("esc.clima_desc", n=st["climate_rejected"])
            self._mensaje(t(
                "esc.progreso", est=nativo.nombre_estructura(e.sid), dim=nativo.DIM_NOMBRE[e.dim], ver=e.version,
                seed=nativo.seed_firmada(e.seed), modo=t(f"modo.{e.modo}"), clima=t("esc.mas_clima") if e.clima else "",
                area=area, biomas=biomas, h=hechas, tot=total, falta=falta, pct=100 * hechas / max(1, total),
                enc=e.encontradas, esc=e.escritas, vel=vel, ahorro=ahorro, t=util.fmt_t(e.tiempo()),
                eta=util.fmt_t(eta), nh=len(e.estado_hilos), hil=hil, rean=t("esc.reanudado") if e.reanudado else ""))
        if e.encontradas != self._mostradas:
            self._mostradas = e.encontradas
            tb = self.query_one("#tabla", DataTable)
            tb.clear()
            for i, (x, z, b) in enumerate(list(e.ultimos)[::-1]):
                tb.add_row(str(e.encontradas - i), str(x), str(z), b)
