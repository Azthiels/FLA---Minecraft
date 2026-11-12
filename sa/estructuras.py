"""Geometria de cada estructura para las granjas multiples.

Modelo: la zona de spawn de una estructura es un CUADRADO [x+offset, x+offset+lado] x [z+offset, z+offset+lado]
(bloques, continuo), donde (x, z) es lo que devuelve getStructurePos. Se usa un cuadrado porque la rotacion de
la estructura es aleatoria y no la calculamos: el lado es el de la dimension MAYOR, asi que es conservador
(nunca da por buena una agrupacion que en el juego no funciona en planta).

Con cuadrados iguales, dos estructuras entran a la vez en un circulo de radio R si y solo si
(|dx|+lado)^2 + (|dz|+lado)^2 <= (2R)^2  -> lo usan el escaner (modo grupos, en C) y el limpiador.
"""
from dataclasses import dataclass

from sa import nativo


@dataclass(frozen=True)
class Caja:
    offset: int      # desde la posicion de getStructurePos hasta la esquina minima del cuadrado
    lado: int        # lado del cuadrado conservador
    exacta: bool     # True = dimensiones conocidas del juego; False = aproximacion, ajustala en la TUI
    nota: str


# getStructurePos devuelve la esquina del chunk de inicio en todas estas estructuras.
CAJAS = {
    3: Caja(0, 9, True, "Witch Hut: 7x9 desde la esquina del chunk, rotacion aleatoria -> 9x9"),
    1: Caja(0, 21, True, "Desert Pyramid: 21x21 desde la esquina del chunk"),
    2: Caja(0, 15, True, "Jungle Temple: 12x15 desde la esquina del chunk, rotacion aleatoria -> 15x15"),
    4: Caja(0, 8, True, "Igloo (superficie): 7x8 desde la esquina del chunk -> 8x8"),
    8: Caja(-21, 58, False, "Ocean Monument: 58x58 centrado en el chunk (aprox.)"),
}
_DEFECTO = Caja(0, 16, False, "Sin datos de la caja: se asume 1 chunk (16x16). Ajusta el lado segun la granja.")


def caja(sid: int) -> Caja:
    return CAJAS.get(int(sid), _DEFECTO)


def maximo_teorico(sid: int, version: str, radio: int, lado: int) -> int:
    """Cota superior de estructuras que pueden entrar juntas: hay como mucho una por region, y un circulo de
    diametro 2R solo toca unas pocas regiones por eje. Witch Hut (regiones de 512) con R=128 -> 4."""
    rb = nativo.region_bloques(sid, version)
    span = 2 * radio - lado
    if span < 0 or rb <= 0:
        return 1
    por_eje = span // rb + 2
    return por_eje * por_eje
