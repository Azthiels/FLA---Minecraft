"""Corre todos los tests:  python -m tests            (o algunos:  python -m tests grupos analizador cajas)
Termina con codigo != 0 si algo falla.

Vigilancia contra cuelgues: cada 3 minutos imprime que test esta corriendo y hace cuanto; si un test pasa de
LIMITE_S (300 s, o la variable de entorno SA_TEST_LIMITE), vuelca el stack de todos los hilos (para ver donde se
colgo) y corta el proceso con error."""
import faulthandler, os, shutil, sys, threading, time

from tests import comun, test_escaner, test_grupos

LIMITE_S = float(os.environ.get("SA_TEST_LIMITE", 300))
LATIDO_S = 180
_actual = {"nombre": None, "t0": 0.0}


def _latido():
    while True:
        time.sleep(LATIDO_S)
        if _actual["nombre"]:
            print(f"   ... sigue corriendo {_actual['nombre']} ({time.time() - _actual['t0']:.0f}s)", flush=True)


if __name__ == "__main__":
    pruebas = test_grupos.PRUEBAS + test_escaner.PRUEBAS
    sel = sys.argv[1:]
    t0 = time.time()
    threading.Thread(target=_latido, daemon=True).start()
    for t in pruebas:
        if sel and not any(s in t.__name__ for s in sel):
            continue
        print(f"\n== {t.__name__} ==", flush=True)
        _actual.update(nombre=t.__name__, t0=time.time())
        faulthandler.dump_traceback_later(LIMITE_S, exit=True)   # si se cuelga: stack de todos los hilos y salida
        try:
            t()
        finally:
            faulthandler.cancel_dump_traceback_later()
        print(f"   ({time.time() - _actual['t0']:.1f}s)", flush=True)
    _actual["nombre"] = None
    shutil.rmtree(comun.TMP, ignore_errors=True)
    print(f"\n{'TODO OK' if not comun.FALLOS else 'FALLARON: ' + ', '.join(comun.FALLOS)}  ({time.time()-t0:.0f}s)")
    sys.exit(1 if comun.FALLOS else 0)
