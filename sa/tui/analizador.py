"""Pantalla 3: analizador de grupos."""
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, ProgressBar, Select, Static

from sa import config, analizador
from sa.tui.comunes import entero


class PanelAnalizador(Horizontal):
    DEFAULT_CSS = """
    PanelAnalizador #detalle { height: auto; max-height: 12; border: round $secondary; padding: 0 1; margin-top: 1; }
    PanelAnalizador #resumen { height: auto; max-height: 16; }
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.corriendo = False
        self.res = None
        self._filas = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="form"):
            yield Label("Archivo (.sab del escaneo/limpiador o .jsonl)")
            yield Input(value="", id="entrada", placeholder="ruta al archivo")
            yield Label("Radio de activacion (bloques)")
            yield Input(value=str(config.RADIO_ACTIVACION), id="radio")
            yield Label("Lado de la caja (vacio = auto)")
            yield Input(value="", id="lado", placeholder="auto")
            yield Label("Tamano minimo de grupo")
            yield Select([("2 (dobles en adelante)", 2), ("3", 3), ("4", 4), ("5", 5)], value=2, allow_blank=False, id="minimo")
            yield Label("Ordenar por")
            yield Select([("Cercania al 0,0", "distancia"), ("Margen (mas holgado)", "margen")],
                         value="distancia", allow_blank=False, id="orden")
            yield Button("Analizar", variant="success", id="go")
            yield Static("Busca todos los grupos cuyas cajas entran juntas en el radio de activacion alrededor de un "
                         "punto AFK, y recomienda el mejor que tenga el mundo (si no hay cuadruples, la mejor triple o "
                         "doble).\n\nResultados completos en <archivo>.grupos.json y .grupos.csv.", classes="info")
        with Vertical(classes="derecha"):
            yield Static("Elegi un archivo y presiona Analizar.", id="resumen", classes="estado")
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield DataTable(id="tabla")
            yield VerticalScroll(Static("", id="txt_detalle"), id="detalle")

    def on_mount(self):
        t = self.query_one("#tabla", DataTable)
        t.add_columns("Tipo", "AFK X", "AFK Z", "Margen", "Dist. 0,0", "Estructuras")
        t.cursor_type = "row"

    def cargar(self, ruta):
        self.query_one("#entrada", Input).value = str(ruta)

    def detener(self):
        pass

    @on(Button.Pressed, "#go")
    def _go(self):
        if self.corriendo:
            return
        try:
            ent = self.query_one("#entrada", Input).value.strip()
            if not ent or not Path(ent).exists():
                raise ValueError(f"No existe el archivo: {ent}")
            radio = entero(self.query_one("#radio", Input), "Radio")
            l = self.query_one("#lado", Input).value.strip()
            lado = int(l) if l else None
            minimo = self.query_one("#minimo", Select).value
            orden = self.query_one("#orden", Select).value
        except ValueError as e:
            self.query_one("#resumen", Static).update(f"[red]Error:[/red] {e}")
            return
        self.corriendo = True
        self.query_one("#go", Button).label = "Analizando..."
        self.query_one("#resumen", Static).update("Analizando...")
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
        self.query_one("#go", Button).label = "Analizar"
        if err:
            self.query_one("#resumen", Static).update(f"[red]Error:[/red] {err}")
            return
        self.res = r
        conteo = ", ".join(f"[b]{v:,}[/b] {analizador.nombre_tam(int(k))}s" for k, v in r["conteo"].items()) or "ninguno"
        aviso = ""
        if r.get("fuente_estado") not in (None, "completado"):
            aviso = f"\n[yellow]Ojo: el escaneo de origen esta '{r['fuente_estado']}': faltan zonas del mapa.[/yellow]"
        if not r["caja"]["exacta"]:
            aviso += f"\n[yellow]Caja aproximada: {r['caja']['nota']}[/yellow]"
        if r["mejor_tam"]:
            t = r["mejor_tam"]
            g = r["recomendados"][0]
            faltan = ""
            if r["maximo_teorico"] and t < min(r["maximo_teorico"], 4):
                faltan = f" (no hay {analizador.nombre_tam(t + 1)}s en lo escaneado)"
            rec = (f"Recomendacion: [b green]{analizador.nombre_tam(t)}[/b green]{faltan}\n"
                   f"  AFK en X [b]{g['afk'][0]}[/b], Z [b]{g['afk'][1]}[/b]  (margen {g['margen']} bloques, "
                   f"a {g['dist_origen']:,.0f} del 0,0)")
        else:
            rec = "[red]No hay ningun grupo:[/red] ninguna estructura se puede activar junto con otra con ese radio."
        self.query_one("#resumen", Static).update(
            f"[b]{r['estructura']}[/b] | seed {r['seed']} | {r['version']} | radio {r['radio']} | "
            f"caja {r['caja']['lado']}x{r['caja']['lado']}\n"
            f"Estructuras: {r['estructuras_leidas']:,}   grupos: {conteo}   "
            f"(maximo teorico: {r['maximo_teorico'] or '?'})   {r['segundos']:.1f}s\n{rec}{aviso}\n"
            f"[dim]{r.get('archivos', {}).get('json', '')}[/dim]")
        t = self.query_one("#tabla", DataTable)
        t.clear()
        self._filas = r["grupos"][:config.TOP_GRUPOS]
        for g in self._filas:
            t.add_row(analizador.nombre_tam(g["tam"]), str(g["afk"][0]), str(g["afk"][1]), f"{g['margen']:.1f}",
                      f"{g['dist_origen']:,.0f}", "  ".join(f"{e['x']},{e['z']}" for e in g["estructuras"]))
        t.border_title = f"{len(self._filas):,} de {r.get('total_grupos', len(r['grupos'])):,} grupos (todos en el .csv)"
        if self._filas:
            self._detalle(0)
        self.notify(f"Grupos: {conteo}".replace("[b]", "").replace("[/b]", ""), title="Analisis terminado")

    @on(DataTable.RowHighlighted, "#tabla")
    def _fila(self, ev):
        if ev.cursor_row is not None:
            self._detalle(ev.cursor_row)

    def _detalle(self, i):
        if not (0 <= i < len(self._filas)):
            return
        g = self._filas[i]
        est = "\n".join(f"  {k + 1}. X {e['x']}, Z {e['z']}  ({e['bioma']})" for k, e in enumerate(g["estructuras"]))
        self.query_one("#txt_detalle", Static).update(
            f"[b]{analizador.nombre_tam(g['tam']).title()}[/b]  ->  AFK en el bloque X {g['afk'][0]}, Z {g['afk'][1]}\n"
            f"Esquina mas lejana a {g['dist_max']} bloques (margen {g['margen']})\n{est}\n"
            f"[dim]/tp @s {g['afk'][0]} ~ {g['afk'][1]}[/dim]")
