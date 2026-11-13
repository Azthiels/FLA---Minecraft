"""Structure Analyzer: escaner (parte 1), limpiador (parte 2) y analizador de grupos (parte 3).

    sa.nativo        bindings ctypes de la libreria (cubiomes + shim.c), versiones, estructuras, biomas
    sa.estructuras   geometria de cada estructura (caja de spawn) y limites teoricos de agrupacion
    sa.geometria     circulo minimo, prueba de "entra en el radio", punto AFK
    sa.datos         formato de resultados (.sab binario + .meta.json), lectura/exportacion, JSONL viejo
    sa.escaner       plan (cajas -> tiles) y motor multihilo con checkpoint
    sa.limpiador     descarta estructuras sin ninguna vecina con la que activarse a la vez
    sa.analizador    dobles, triples, cuadruples...: cuantas hay, cuales conviene y donde poner el AFK
    sa.tui           interfaz (Textual) con las 3 partes
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "results"      # aca van los escaneos y analisis cuando la salida es un nombre o ruta relativa
__version__ = "2.0"
