"""Pantalla 3: analizador de grupos."""
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, ProgressBar, Select, Static

from sa import config, analizador
from sa.analizador import nombre_tam
from sa.i18n import t
from sa.tui.comunes import entero

MEJORES_POR_TIPO = 3     # opciones que muestra cada recuadro de abajo (el JSON guarda 5 por tipo)


def _conteo(r, markup=True):
    b0, b1 = ("[b]", "[/b]") if markup else ("", "")
    return ", ".join(f"{b0}{v:,}{b1} {nombre_tam(int(k), plural=True)}" for k, v in r["conteo"].items()) or t("ana.ninguno")


class PanelAnalizador(Horizontal):
    DEFAULT_CSS = """
    PanelAnalizador #resumen { height: auto; max-height: 12; }
    PanelAnalizador #abajo { height: 13; margin-top: 1; }
    PanelAnalizador .caja_mejor { width: 1fr; height: 100%; border: round $success; padding: 0 1; }
    PanelAnalizador #detalle { width: 1fr; height: 100%; border: round $secondary; padding: 0 1; }
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.corriendo = False
        self.res = None
        self._filas = []
        self.al_terminar = None   # callback(resultado) que pone la App (modo auto)

    def compose(self) -> ComposeResult:
        with Vertical(classes="form"):
            yield Label(t("ana.archivo"))
            yield Input(value="", id="entrada", placeholder=t("ana.archivo_ph"))
            yield Label(t("ana.radio"))
            yield Input(value=str(config.RADIO_ACTIVACION), id="radio")
            yield Label(t("ana.lado"))
            yield Input(value="", id="lado", placeholder="auto")
            yield Label(t("ana.minimo"))
            yield Select([(t("ana.min2"), 2), ("3", 3), ("4", 4), ("5", 5)], value=2, allow_blank=False, id="minimo")
            yield Label(t("ana.orden"))
            yield Select([(t("ana.o_dist"), "distancia"), (t("ana.o_margen"), "margen")],
                         value="distancia", allow_blank=False, id="orden")
            yield Button(t("ana.analizar"), variant="success", id="go")
            yield Button(t("ana.cargar"), id="cargar", disabled=True)
            yield Static("", id="guardado", classes="info")
            yield Static(t("ana.ayuda"), classes="info")
        with Vertical(classes="derecha"):
            yield Static(t("ana.listo"), id="resumen", classes="estado")
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield DataTable(id="tabla")
            with Horizontal(id="abajo"):
                yield VerticalScroll(Static("", id="txt_detalle"), id="detalle")

    def on_mount(self):
        tb = self.query_one("#tabla", DataTable)
        tb.add_columns(*t("ana.cols"))
        tb.cursor_type = "row"
        self.query_one("#detalle").border_title = t("ana.seleccionado")

    # ---------- API para la App (modo auto) ----------
    def cargar(self, ruta):
        self.query_one("#entrada", Input).value = str(ruta)

    def prefijar(self, radio=None, lado=None):
        if radio is not None:
            self.query_one("#radio", Input).value = str(radio)
        if lado is not None:
            self.query_one("#lado", Input).value = str(lado)

    def detener(self):
        pass

    @on(Input.Changed, "#entrada")
    def _entrada_cambio(self, ev):
        self._actualizar_guardado(ev.value)

    def _actualizar_guardado(self, valor):
        """Si ese archivo ya tiene un analisis guardado, habilitar 'Cargar' y decir de cuando es."""
        info = None
        ent = valor.strip()
        if ent:
            try:
                info = analizador.guardado(ent)
            except (OSError, ValueError):
                info = None
        self.query_one("#cargar", Button).disabled = info is None
        txt = ""
        if info:
            txt = t("ana.guardado", limpio=t("ana.de_limpio") if info["limpio"] else "",
                    fecha=(info["fecha"] or "?")[:16].replace("T", " "), kb=info["kb"])
            if info["desactualizado"]:
                txt += t("ana.viejo")
        self.query_one("#guardado", Static).update(txt)

    @on(Button.Pressed, "#cargar")
    def cargar_guardado(self):
        ent = self.query_one("#entrada", Input).value.strip()
        try:
            r = analizador.cargar_resultado(ent)
        except (OSError, ValueError, KeyError) as e:
            self.query_one("#resumen", Static).update(f"[red]{t('ana.no_cargar')}[/red] {e}")
            return
        self._mostrar(r)
        self.notify(t("ana.cargado_n"), title=t("ana.cargado_t"))

    @on(Button.Pressed, "#go")
    def ejecutar(self):
        if self.corriendo:
            return
        try:
            ent = self.query_one("#entrada", Input).value.strip()
            if not ent or not Path(ent).exists():
                raise ValueError(t("com.no_existe", ruta=ent))
            radio = entero(self.query_one("#radio", Input), t("ana.f_radio"))
            l = self.query_one("#lado", Input).value.strip()
            lado = int(l) if l else None
            minimo = self.query_one("#minimo", Select).value
            orden = self.query_one("#orden", Select).value
        except ValueError as e:
            self.query_one("#resumen", Static).update(f"[red]{t('com.error')}[/red] {e}")
            return
        self.corriendo = True
        self.query_one("#go", Button).label = t("ana.analizando")
        self.query_one("#resumen", Static).update(t("ana.analizando"))
        self.run_worker(lambda: self._correr(ent, radio, lado, minimo, orden), thread=True, exclusive=True, group="analizar")

    def _prog(self, f, txt=""):
        self.app.call_from_thread(self.query_one("#bar", ProgressBar).update, total=100, progress=100 * f)

    def _correr(self, ent, radio, lado, minimo, orden):
        try:
            r = analizador.analizar(ent, radio=radio, lado=lado, minimo=minimo, orden=orden, progreso=self._prog)
            self.app.call_from_thread(self._fin, r, None)
        except Exception as e:
            self.app.call_from_thread(self._fin, None, f"{type(e).__name__}: {e}")

    def _fin(self, r, err):
        self.corriendo = False
        self.query_one("#go", Button).label = t("ana.analizar")
        if err:
            self.query_one("#resumen", Static).update(f"[red]{t('com.error')}[/red] {err}")
            if self.al_terminar:
                self.al_terminar(None)
            return
        self._mostrar(r)
        self._actualizar_guardado(self.query_one("#entrada", Input).value)
        self.notify(t("ana.grupos_n", c=_conteo(r, markup=False)), title=t("ana.fin_t"))
        if self.al_terminar:
            self.al_terminar(r)

    def _mostrar(self, r):
        """Pinta un resultado (recien calculado o cargado de disco)."""
        self.res = r
        aviso = ""
        if r.get("fuente_estado") not in (None, "completado"):
            aviso = t("ana.incompleto", e=r["fuente_estado"])
        if not r["caja"]["exacta"]:
            aviso += t("ana.caja_aprox", n=r["caja"]["nota"])
        if r.get("cargado"):
            aviso += t("ana.de_disco", f=str(r.get("fecha", "?"))[:16].replace("T", " "))
            if r.get("desactualizado"):
                aviso += t("ana.de_disco_viejo")
        if r["mejor_tam"]:
            tam = r["mejor_tam"]
            faltan = ""
            if r["maximo_teorico"] and tam < min(r["maximo_teorico"], 4):
                faltan = t("ana.faltan", tipo=nombre_tam(tam + 1, plural=True))
            rec = t("ana.mejor_mundo", tipo=nombre_tam(tam), faltan=faltan)
        else:
            rec = t("ana.sin_grupos")
        self.query_one("#resumen", Static).update(t(
            "ana.resumen", est=r["estructura"], seed=r["seed"], ver=r["version"], r=r["radio"], l=r["caja"]["lado"],
            n=r["estructuras_leidas"], conteo=_conteo(r), teo=r["maximo_teorico"] or "?", s=r["segundos"], rec=rec,
            aviso=aviso, f=r.get("archivos", {}).get("json", "")))
        tb = self.query_one("#tabla", DataTable)
        tb.clear()
        self._filas = r["grupos"][:config.TOP_GRUPOS]
        for g in self._filas:
            tb.add_row(nombre_tam(g["tam"]), str(g["afk"][0]), str(g["afk"][1]), f"{g['margen']:.2f}",
                       f"{g['dist_origen']:,.0f}", "  ".join(f"{e['x']},{e['z']}" for e in g["estructuras"]))
        tb.border_title = t("ana.tabla_t", n=len(self._filas), tot=r.get("total_grupos", len(r["grupos"])))
        self._pintar_mejores(r)
        if self._filas:
            self._detalle(0)

    def _pintar_mejores(self, r):
        """Un recuadro por tipo encontrado (de mayor a menor) con sus mejores opciones y el /tp de cada una."""
        abajo = self.query_one("#abajo", Horizontal)
        for w in list(abajo.query(".caja_mejor")):
            w.remove()
        orden = t("ana.orden_dist") if r.get("orden") == "distancia" else t("ana.orden_margen")
        detalle = self.query_one("#detalle")
        for k, lista in r.get("mejores", {}).items():
            lineas = [t("ana.opcion", n=n, x=g["afk"][0], z=g["afk"][1], m=g["margen"], d=g["dist_origen"])
                      for n, g in enumerate(lista[:MEJORES_POR_TIPO], 1)]
            caja = VerticalScroll(Static("\n".join(lineas)), classes="caja_mejor")
            caja.border_title = t("ana.mejores_t", tipo=nombre_tam(int(k), plural=True), n=r["conteo"].get(k, 0))
            caja.border_subtitle = orden
            abajo.mount(caja, before=detalle)

    @on(DataTable.RowHighlighted, "#tabla")
    def _fila(self, ev):
        if ev.cursor_row is not None:
            self._detalle(ev.cursor_row)

    def _detalle(self, i):
        if not (0 <= i < len(self._filas)):
            return
        g = self._filas[i]
        est = "\n".join(f"  {k + 1}. X {e['x']}, Z {e['z']}  ({e['bioma']})" for k, e in enumerate(g["estructuras"]))
        self.query_one("#txt_detalle", Static).update(t(
            "ana.detalle", tipo=nombre_tam(g["tam"]).title(), x=g["afk"][0], z=g["afk"][1], d=g["dist_max"],
            m=g["margen"], est=est))
