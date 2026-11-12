"""Parte 1: escaner de estructuras (plan de tiles + motor multihilo con checkpoint)."""
from sa.escaner.motor import Escaneo, ReanudarError, SalidaExisteError, MODOS  # noqa: F401
from sa.escaner.plan import Plan, descomponer, normalizar_cajas  # noqa: F401
