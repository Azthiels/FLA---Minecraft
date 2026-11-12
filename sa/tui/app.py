"""App principal: las 3 partes como pestanas. Al terminar una, el archivo pasa solo a la siguiente.
El idioma (sa.i18n) tiene que estar elegido ANTES de importar este modulo (los atajos se arman al importar)."""
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, TabbedContent, TabPane

from sa import util
from sa.i18n import t
from sa.tui.analizador import PanelAnalizador
from sa.tui.comunes import FORM_CSS
from sa.tui.escaner import PanelEscaner
from sa.tui.limpiador import PanelLimpiador


class StructureAnalyzer(App):
    TITLE = "FLA - Farm Locator Azthiels"
    CSS = FORM_CSS
    BINDINGS = [("q", "quit", t("app.salir")), ("1", "pestana('t1')", t("app.escaner")),
                ("2", "pestana('t2')", t("app.limpiador")), ("3", "pestana('t3')", t("app.analizador"))]

    def __init__(self, prefill=None):
        super().__init__()
        self.saliendo = False
        self.auto_en_curso = False
        self.prefill = prefill or {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="t1"):
            with TabPane(t("app.tab1"), id="t1"):
                yield PanelEscaner(prefill=self.prefill, id="p_escaner")
            with TabPane(t("app.tab2"), id="t2"):
                yield PanelLimpiador(id="p_limpiador")
            with TabPane(t("app.tab3"), id="t3"):
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
                self.notify(t("app.auto_grupos"), title=t("app.auto_titulo"))
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
                util.notificar(t("app.auto_error"), t("app.auto_error_msg"))
                return
            from sa.analizador import nombre_tam
            tam = r["mejor_tam"]
            if tam:
                g = r["mejores"][str(tam)][0]
                msg = t("app.auto_mejor", tipo=nombre_tam(tam), x=g["afk"][0], z=g["afk"][1], m=g["margen"])
            else:
                msg = t("app.auto_nada")
            self.bell()
            util.notificar(t("app.auto_fin"), msg)

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
            self.notify(t("app.guardando"), severity="warning")
        else:
            self.exit()


def run(prefill=None):
    StructureAnalyzer(prefill).run()
