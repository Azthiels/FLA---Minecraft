"""Valores por defecto. Se pueden sobreescribir con 'config.json' en la raiz del proyecto,
p. ej. {"BATCH_SIZE": 100, "TILE_REGIONS": 64, "RADIO_ACTIVACION": 128}. La TUI tambien permite cambiarlos."""
import json

from sa import RAIZ

# ---- escaner
BATCH_SIZE = 50              # registros por escritura al archivo de datos
FLUSH_INTERVAL_S = 5.0       # si hay registros pendientes, se escriben igualmente pasado este tiempo
CHECKPOINT_INTERVAL_S = 10.0 # checkpoint + metadatos (fsync incluido)
TILE_REGIONS = 128           # lado (en regiones) de la unidad de trabajo/checkpoint
QUEUE_PER_WORKER = 4         # cola acotada entre hilos de calculo y el escritor (contrapresion)
RECENT_ROWS = 200            # ultimos registros que guarda en RAM la TUI
MODO = "grupos"              # "grupos" = solo las que tienen vecina (recomendado) | "todas"
CLIMA = True                 # prefiltro de clima 1.18+ (exacto; se ignora donde no aplica)

# ---- grupos (escaner en modo grupos, limpiador, analizador)
RADIO_ACTIVACION = 128       # bloques: radio desde el jugador en el que tiene que entrar cada caja
TOP_GRUPOS = 500             # grupos que muestra la tabla del analizador (el archivo exportado tiene todos)

_f = RAIZ / "config.json"
if _f.exists():
    try:
        for _k, _v in json.loads(_f.read_text(encoding="utf-8")).items():
            if _k in globals() and not _k.startswith("_"):
                globals()[_k] = type(globals()[_k])(_v)
    except Exception:
        pass
