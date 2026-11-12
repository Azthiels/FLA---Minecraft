"""Piezas compartidas de la TUI: modales de biomas y cajas, helpers de formularios."""
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, SelectionList
from textual.widgets.selection_list import Selection

FORM_CSS = """
.form { width: 52; padding: 0 2; border: round $primary; height: 100%; overflow-y: auto; }
.form Label { margin-top: 1; }
.form Button { margin-top: 1; width: 100%; }
.derecha { padding: 0 1; }
.info { height: auto; color: $text-muted; margin-top: 1; }
.estado { height: auto; margin-top: 1; }
.derecha DataTable { height: 1fr; margin-top: 1; }
"""


def valor(select: Select):
    v = select.value
    return None if v is Select.NULL or v is Select.BLANK else v


def entero(inp: Input, nombre: str, minimo=1):
    try:
        v = int(inp.value.strip().replace("_", "").replace(".", ""))
    except ValueError:
        raise ValueError(f"{nombre}: tiene que ser un numero entero")
    if v < minimo:
        raise ValueError(f"{nombre}: tiene que ser >= {minimo}")
    return v


class BiomasScreen(ModalScreen):
    """Ventana para elegir en que biomas buscar. Solo lista los biomas donde la estructura puede aparecer."""
    CSS = """
    BiomasScreen { align: center middle; }
    #cuadro { width: 60; height: 80%; border: round $primary; background: $surface; padding: 1 2; }
    #lista { height: 1fr; margin: 1 0; }
    #botones { height: auto; }
    #botones Button { margin-right: 1; width: auto; min-width: 12; }
    """

    def __init__(self, biomas, seleccion):
        super().__init__()
        self.biomas = biomas            # [(id, nombre)]
        self.seleccion = seleccion      # set de ids o None = todos

    def compose(self) -> ComposeResult:
        with Vertical(id="cuadro"):
            yield Label("Buscar solo en estos biomas (espacio para marcar/desmarcar)")
            yield SelectionList(*[Selection(n, i, self.seleccion is None or i in self.seleccion)
                                  for i, n in self.biomas], id="lista")
            with Horizontal(id="botones"):
                yield Button("Todos", id="todos")
                yield Button("Ninguno", id="ninguno")
                yield Button("Aplicar", variant="success", id="ok")
                yield Button("Cancelar", id="cancel")

    @on(Button.Pressed, "#todos")
    def _todos(self):
        self.query_one("#lista", SelectionList).select_all()

    @on(Button.Pressed, "#ninguno")
    def _ninguno(self):
        self.query_one("#lista", SelectionList).deselect_all()

    @on(Button.Pressed, "#cancel")
    def _cancel(self):
        self.dismiss(False)

    @on(Button.Pressed, "#ok")
    def _ok(self):
        sel = set(self.query_one("#lista", SelectionList).selected)
        if not sel:
            self.notify("Elegi al menos un bioma", severity="warning")
            return
        self.dismiss(None if len(sel) == len(self.biomas) else sel)


class CajasScreen(ModalScreen):
    """Ventana para definir bounding boxes (rectangulos X/Z) a escanear."""
    CSS = """
    CajasScreen { align: center middle; }
    #cuadro { width: 70; height: 80%; border: round $primary; background: $surface; padding: 1 2; }
    #coords { height: auto; }
    #coords Input { width: 1fr; margin-right: 1; }
    #tcajas { height: 1fr; margin: 1 0; }
    #add { width: 100%; }
    #botones { height: auto; }
    #botones Button { margin-right: 1; width: auto; min-width: 12; }
    """

    def __init__(self, cajas, dim_nombre, radio_dim):
        super().__init__()
        self.cajas = list(cajas)
        self.dim_nombre, self.radio_dim = dim_nombre, radio_dim

    def compose(self) -> ComposeResult:
        with Vertical(id="cuadro"):
            yield Label(f"Bounding boxes en coordenadas de {self.dim_nombre} (borde: +-{self.radio_dim:,}).\n"
                        "Sin cajas = se escanea el mundo completo.")
            with Horizontal(id="coords"):
                yield Input(placeholder="X1", id="x1")
                yield Input(placeholder="Z1", id="z1")
                yield Input(placeholder="X2", id="x2")
                yield Input(placeholder="Z2", id="z2")
            yield Button("Agregar caja", id="add")
            yield DataTable(id="tcajas")
            with Horizontal(id="botones"):
                yield Button("Quitar seleccionada", id="del")
                yield Button("Vaciar", id="clear")
                yield Button("Aplicar", variant="success", id="ok")
                yield Button("Cancelar", id="cancel")

    def on_mount(self):
        t = self.query_one("#tcajas", DataTable)
        t.add_columns("#", "X1", "Z1", "X2", "Z2", "Tamano")
        t.cursor_type = "row"
        self._pintar()

    def _pintar(self):
        t = self.query_one("#tcajas", DataTable)
        t.clear()
        for i, (a, b, c, d) in enumerate(self.cajas, 1):
            t.add_row(str(i), str(a), str(b), str(c), str(d), f"{abs(c-a)+1:,} x {abs(d-b)+1:,}")

    @on(Button.Pressed, "#add")
    def _add(self):
        try:
            v = [int(self.query_one(i, Input).value) for i in ("#x1", "#z1", "#x2", "#z2")]
        except ValueError:
            self.notify("Las coordenadas deben ser numeros enteros", severity="error")
            return
        self.cajas.append(tuple(v))
        for i in ("#x1", "#z1", "#x2", "#z2"):
            self.query_one(i, Input).value = ""
        self._pintar()

    @on(Button.Pressed, "#del")
    def _del(self):
        t = self.query_one("#tcajas", DataTable)
        if self.cajas and t.cursor_row is not None and 0 <= t.cursor_row < len(self.cajas):
            self.cajas.pop(t.cursor_row)
            self._pintar()

    @on(Button.Pressed, "#clear")
    def _clear(self):
        self.cajas.clear()
        self._pintar()

    @on(Button.Pressed, "#cancel")
    def _cancel(self):
        self.dismiss(False)

    @on(Button.Pressed, "#ok")
    def _ok(self):
        self.dismiss(self.cajas)
