"""Structure Analyzer - TUI con las 3 partes (escaner, limpiador, analizador).

    python main.py                                   # TUI vacia
    python main.py --seed 123 --estructura 3 --salida huts --iniciar
                                                     # formulario completado y escaneo arrancado
    python main.py --help                            # todas las opciones
"""
import argparse


def _args():
    p = argparse.ArgumentParser(description="Structure Analyzer (TUI). Las opciones completan el formulario del escaner.")
    p.add_argument("--seed")
    p.add_argument("--version", help="ej. 26.3, 1.21.11, 1.18")
    p.add_argument("--estructura", type=int, help="id de cubiomes (3 = Witch Hut, 8 = Ocean Monument, ...)")
    p.add_argument("--borde", type=int, help="radio del world border")
    p.add_argument("--modo", choices=["grupos", "todas"])
    p.add_argument("--radio-grupo", type=int, dest="radio_grupo", help="radio de activacion (128)")
    p.add_argument("--lado", type=int, help="lado de la caja de la estructura")
    p.add_argument("--hilos", type=int)
    p.add_argument("--lote", type=int)
    p.add_argument("--salida", help="nombre base de los archivos de salida")
    p.add_argument("--sin-clima", dest="clima", action="store_false", default=None, help="desactivar el prefiltro de clima")
    p.add_argument("--sobrescribir", action="store_true")
    p.add_argument("--iniciar", action="store_true", help="arrancar el escaneo apenas abre")
    return {k: v for k, v in vars(p.parse_args()).items() if v is not None}


if __name__ == "__main__":
    a = _args()
    if "version" in a:
        from sa import nativo
        if a["version"] not in nativo.VERSIONES:
            raise SystemExit(f"Version desconocida: {a['version']}. Disponibles: {', '.join(nativo.VERSIONES)}")
    from sa.tui.app import run
    run(a)
