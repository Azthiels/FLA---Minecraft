"""Corre todos los tests:  python -m tests            (o algunos:  python -m tests grupos analizador cajas)
Termina con codigo != 0 si algo falla."""
import shutil, sys, time

from tests import comun, test_escaner, test_grupos

if __name__ == "__main__":
    pruebas = test_grupos.PRUEBAS + test_escaner.PRUEBAS
    sel = sys.argv[1:]
    t0 = time.time()
    for t in pruebas:
        if sel and not any(s in t.__name__ for s in sel):
            continue
        print(f"\n== {t.__name__} ==", flush=True)
        t()
    shutil.rmtree(comun.TMP, ignore_errors=True)
    print(f"\n{'TODO OK' if not comun.FALLOS else 'FALLARON: ' + ', '.join(comun.FALLOS)}  ({time.time()-t0:.0f}s)")
    sys.exit(1 if comun.FALLOS else 0)
