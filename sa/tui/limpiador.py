"""Pantalla 2: limpiador."""
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, ProgressBar, Static

from sa import RAIZ, config, datos, limpiador
from sa.i18n import t
from sa.tui.comunes import entero


class PanelLimpiador(Horizontal):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.corriendo = False
        self.al_terminar = None   # callback(ruta_salida)

    def compose(self) -> ComposeResult:
        with Vertical(classes="form"):
            yield Label(t("lim.entrada"))
            yield Input(value=str(RAIZ / "escaneo.sab"), id="entrada")
            yield Label(t("lim.radio"))
            yield Input(value=str(config.RADIO_ACTIVACION), id="radio")
            yield Label(t("lim.lado"))
            yield Input(value="", id="lado", placeholder="auto")
            yield Label(t("lim.salida"))
            yield Input(value="", id="salida", placeholder="auto")
            yield Button(t("lim.limpiar"), variant="success", id="go")
            yield Static(t("lim.ayuda"), classes="info")
        with Vertical(classes="derecha"):
            yield Static(t("lim.listo"), id="estado", classes="estado")
            yield ProgressBar(total=100, show_eta=False, id="bar")

    def cargar(self, ruta):
        self.query_one("#entrada", Input).value = str(ruta)

    def prefijar(self, radio=None, lado=None):
        if radio is not None:
            self.query_one("#radio", Input).value = str(radio)
        if lado is not None:
            self.query_one("#lado", Input).value = str(lado)

    def detener(self):
        pass   # la limpieza es corta y no deja archivos a medias (escritura atomica)

    @on(Button.Pressed, "#go")
    def ejecutar(self):
        if self.corriendo:
            return
        try:
            ent = self.query_one("#entrada", Input).value.strip()
            if not ent or not Path(ent).exists():
                raise ValueError(t("com.no_existe", ruta=ent))
            radio = entero(self.query_one("#radio", Input), t("lim.f_radio"))
            l = self.query_one("#lado", Input).value.strip()
            lado = int(l) if l else None
            sal = self.query_one("#salida", Input).value.strip() or None
        except ValueError as e:
            self.query_one("#estado", Static).update(f"[red]{t('com.error')}[/red] {e}")
            return
        self.corriendo = True
        self.query_one("#go", Button).label = t("lim.limpiando")
        self.query_one("#estado", Static).update(t("lim.leyendo", n=datos.contar(ent)))
        self.run_worker(lambda: self._correr(ent, sal, radio, lado), thread=True, exclusive=True, group="limpiar")

    def _prog(self, f, txt=""):
        self.app.call_from_thread(self.query_one("#bar", ProgressBar).update, total=100, progress=100 * f)

    def _correr(self, ent, sal, radio, lado):
        try:
            r = limpiador.limpiar(ent, sal, radio=radio, lado=lado, progreso=self._prog)
            self.app.call_from_thread(self._fin, r, None)
        except Exception as e:
            self.app.call_from_thread(self._fin, None, f"{type(e).__name__}: {e}")

    def _fin(self, r, err):
        self.corriendo = False
        self.query_one("#go", Button).label = t("lim.limpiar")
        st = self.query_one("#estado", Static)
        if err:
            st.update(f"[red]{t('com.error')}[/red] {err}")
            return
        st.update(t("lim.fin", s=r["segundos"], e=r["entrada"], q=r["quedan"], d=r["descartadas"], p=r["pares"],
                    r=r["radio"], l=r["lado"], f=r["salida"]))
        self.notify(t("lim.notif", q=r["quedan"], e=r["entrada"]), title=t("lim.notif_t"))
        if self.al_terminar:
            self.al_terminar(r["salida"])
