"""FLA - Farm Locator Azthiels: TUI with the 3 parts (scanner, cleaner, analyzer).

    python main.py                                   # empty TUI (English)
    python main.py --lang es                         # Spanish interface
    python main.py --seed 123 --structure 3 --output huts --auto --start
                                                     # form filled in, scan started, then cleaned + analyzed
    python main.py --help                            # all options
"""
import argparse


def _args():
    p = argparse.ArgumentParser(description="FLA - Farm Locator Azthiels (TUI). These options fill in the scanner form.")
    p.add_argument("--lang", choices=["en", "es"], help="interface language (default: en, or IDIOMA in config.json)")
    p.add_argument("--seed")
    p.add_argument("--version", help="e.g. 26.3, 1.21.11, 1.18")
    p.add_argument("--structure", "--estructura", type=int, dest="estructura", metavar="ID",
                   help="cubiomes structure id (3 = Witch Hut, 8 = Ocean Monument, ...)")
    p.add_argument("--border", "--borde", type=int, dest="borde", metavar="BLOCKS", help="world border radius")
    p.add_argument("--mode", "--modo", choices=["grupos", "todas", "groups", "all"], dest="modo",
                   help="groups = groupable only (fast), all = all structures")
    p.add_argument("--radius", "--radio-grupo", type=int, dest="radio_grupo", metavar="BLOCKS", help="activation radius (128)")
    p.add_argument("--side", "--lado", type=int, dest="lado", metavar="BLOCKS", help="structure box side")
    p.add_argument("--threads", "--hilos", type=int, dest="hilos", metavar="N")
    p.add_argument("--batch", "--lote", type=int, dest="lote", metavar="N")
    p.add_argument("--output", "--salida", dest="salida", metavar="NAME", help="base name of the output files")
    p.add_argument("--no-climate", "--sin-clima", dest="clima", action="store_false", default=None,
                   help="disable the climate prefilter")
    p.add_argument("--overwrite", "--sobrescribir", dest="sobrescribir", action="store_true")
    p.add_argument("--start", "--iniciar", dest="iniciar", action="store_true", help="start the scan right away")
    p.add_argument("--auto", action="store_true", help="auto mode: clean and analyze when the scan finishes")
    return {k: v for k, v in vars(p.parse_args()).items() if v is not None}


if __name__ == "__main__":
    a = _args()
    from sa import i18n
    if a.get("modo") in ("groups", "all"):
        a["modo"] = {"groups": "grupos", "all": "todas"}[a["modo"]]
    if a.get("lang"):
        i18n.set_idioma(a.pop("lang"))
    if "version" in a:
        from sa import nativo
        if a["version"] not in nativo.VERSIONES:
            raise SystemExit(f"Unknown version: {a['version']}. Available: {', '.join(nativo.VERSIONES)}")
    from sa.tui.app import run          # despues de elegir el idioma
    run(a)
