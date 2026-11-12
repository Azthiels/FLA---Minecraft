"""App principal: las 3 partes como pestanas. Al terminar una, el archivo pasa solo a la siguiente."""
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, TabbedContent, TabPane

from sa import util
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

        self.auto_en_curso = False

        def tras_escaneo(e):
            ruta = e.rutas["datos"]
            lim.cargar(ruta)
            ana.cargar(ruta)
            radio, lado = (e.radio_grupo, e.lado) if e.modo == "grupos" else (None, None)
            lim.prefijar(radio, lado)
            ana.prefijar(radio, lado)
            if not (esc.auto and e.estado == "completado"):
                return
            self.auto_en_curso = True                 # modo auto: 1 -> 2 -> 3 sin tocar nada
            if e.modo == "todas":
                self.action_pestana("t2")
                lim.ejecutar()
            else:                                     # en modo grupos el escaneo ya sale limpio: el paso 2 no cambia nada
                self.notify("Modo grupos: el resultado ya viene limpio, paso directo al analizador.", title="Modo auto")
                self.action_pestana("t3")
                ana.ejecutar()

        def tras_limpieza(salida):
            ana.cargar(salida)
            if self.auto_en_curso:
                self.action_pestana("t3")
                ana.ejecutar()

        def tras_analisis(r):
            if not self.auto_en_curso:
                return
            self.auto_en_curso = False
            if r is None:
                util.notificar("FLA: error en el analisis", "Revisa la pestana 3")
                return
            from sa import analizador
            t = r["mejor_tam"]
            if t:
                g = r["mejores"][str(t)][0]
                msg = f"Mejor: {analizador.nombre_tam(t)} en X {g['afk'][0]}, Z {g['afk'][1]} (margen {g['margen']})"
            else:
                msg = "No hay grupos en esta seed"
            self.bell()
            util.notificar("FLA: analisis terminado", msg)

        esc.al_terminar = tras_escaneo
        lim.al_terminar = tras_limpieza
        ana.al_terminar = tras_analisis

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
