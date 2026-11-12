"""Pantalla 2: limpiador."""
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, ProgressBar, Static

from sa import RAIZ, config, datos, limpiador
from sa.tui.comunes import entero


class PanelLimpiador(Horizontal):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.corriendo = False
        self.al_terminar = None   # callback(ruta_salida)

    def compose(self) -> ComposeResult:
        with Vertical(classes="form"):
            yield Label("Archivo de entrada (.sab o .jsonl viejo)")
            yield Input(value=str(RAIZ / "resultados.jsonl"), id="entrada")
            yield Label("Radio de activacion (bloques)")
            yield Input(value=str(config.RADIO_ACTIVACION), id="radio")
            yield Label("Lado de la caja (vacio = el del escaneo/estructura)")
            yield Input(value="", id="lado", placeholder="auto")
            yield Label("Salida (nombre base, vacio = <entrada>_limpio)")
            yield Input(value="", id="salida", placeholder="auto")
            yield Button("Limpiar", variant="success", id="go")
            yield Static("Descarta las estructuras que no tienen ninguna otra con la que se puedan activar a la vez. "
                         "Antes de descartar una se revisan todas sus vecinas.\n\n"
                         "Si el escaneo se hizo en modo [b]Solo agrupables[/b] ya viene limpio: pasa directo al Analizador.",
                         classes="info")
        with Vertical(classes="derecha"):
            yield Static("Elegi un archivo y presiona Limpiar.", id="estado", classes="estado")
            yield ProgressBar(total=100, show_eta=False, id="bar")

    def cargar(self, ruta):
        self.query_one("#entrada", Input).value = str(ruta)

    def detener(self):
        pass   # la limpieza es corta y no deja archivos a medias (escritura atomica)

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
            sal = self.query_one("#salida", Input).value.strip() or None
        except ValueError as e:
            self.query_one("#estado", Static).update(f"[red]Error:[/red] {e}")
            return
        self.corriendo = True
        self.query_one("#go", Button).label = "Limpiando..."
        n = datos.contar(ent)
        self.query_one("#estado", Static).update(f"Leyendo {n:,} registros...")
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
        self.query_one("#go", Button).label = "Limpiar"
        st = self.query_one("#estado", Static)
        if err:
            st.update(f"[red]Error:[/red] {err}")
            return
        st.update(f"[b green]LIMPIEZA TERMINADA[/b green] en {r['segundos']:.1f}s\n"
                  f"Entrada: {r['entrada']:,} estructuras\n"
                  f"Quedan: [b]{r['quedan']:,}[/b]   descartadas: {r['descartadas']:,}   pares compatibles: {r['pares']:,}\n"
                  f"Criterio: radio {r['radio']}, caja {r['lado']}x{r['lado']}\n"
                  f"Salida: {r['salida']}\n\nSiguiente paso: pestana [b]3 Analizador[/b] (ya esta cargado).")
        self.notify(f"Quedan {r['quedan']:,} de {r['entrada']:,}", title="Limpieza terminada")
        if self.al_terminar:
            self.al_terminar(r["salida"])
