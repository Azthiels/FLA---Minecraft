"""App principal: las 3 partes como pestanas. Al terminar una, el archivo pasa solo a la siguiente."""
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, TabbedContent, TabPane

from sa.tui.analizador import PanelAnalizador
from sa.tui.comunes import FORM_CSS
from sa.tui.escaner import PanelEscaner
from sa.tui.limpiador import PanelLimpiador


class StructureAnalyzer(App):
    TITLE = "FLA - Farm Locator Azthiels"
    CSS = FORM_CSS + """
    .fila { height: auto; }
    .fila Vertical { height: auto; width: 1fr; }
    """
    BINDINGS = [("q", "quit", "Salir"), ("1", "pestana('t1')", "Escaner"), ("2", "pestana('t2')", "Limpiador"),
                ("3", "pestana('t3')", "Analizador")]

    def __init__(self, prefill=None):
        super().__init__()
        self.saliendo = False
        self.prefill = prefill or {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="t1"):
            with TabPane("1 Escaner", id="t1"):
                yield PanelEscaner(prefill=self.prefill, id="p_escaner")
            with TabPane("2 Limpiador", id="t2"):
                yield PanelLimpiador(id="p_limpiador")
            with TabPane("3 Analizador", id="t3"):
                yield PanelAnalizador(id="p_analizador")
        yield Footer()

    def on_mount(self):
        esc = self.query_one(PanelEscaner)
        lim = self.query_one(PanelLimpiador)
        ana = self.query_one(PanelAnalizador)

        def tras_escaneo(e):
            ruta = e.rutas["datos"]
            lim.cargar(ruta)
            ana.cargar(ruta)

        esc.al_terminar = tras_escaneo
        lim.al_terminar = ana.cargar

    def check_action(self, action, parameters):
        if action == "pestana" and isinstance(self.focused, Input):
            return False                     # en un Input, 1/2/3 se escriben
        return True

    def action_pestana(self, tab):
        self.query_one(TabbedContent).active = tab

    def action_quit(self):
        esc = self.query_one(PanelEscaner)
        if esc.corriendo:                    # primero guardar y dejar checkpoint, despues salir
            self.saliendo = True
            esc.detener()
            self.notify("Guardando antes de salir...", severity="warning")
        else:
            self.exit()


def run(prefill=None):
    StructureAnalyzer(prefill).run()
