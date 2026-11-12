"""Parche minimo e idempotente sobre cubiomes_src (reaplicar tras actualizar Cubiomes, p.ej. para 26.4).

Objetivo: que isViableStructurePos() deje registrado en Generator.cb_last_biome el ultimo bioma que
muestreo para validar la estructura. Asi el bioma que se REPORTA y el que se FILTRA es el mismo que
uso la regla de generacion (no un punto arbitrario). No cambia ningun resultado de viabilidad.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "cubiomes_src"
MARK = "SCANNER-PATCH"


def patch():
    gh = SRC / "generator.h"
    t = gh.read_text(encoding="utf-8")
    if MARK not in t:
        old = "    EndNoise en; // MC 1.9\n};"
        assert old in t, "generator.h: no se encontro el final de STRUCT(Generator)"
        t = t.replace(old, "    EndNoise en; // MC 1.9\n    int cb_last_biome; // " + MARK + ": ultimo bioma muestreado por isViableStructurePos\n};", 1)
        gh.write_text(t, encoding="utf-8")

    fc = SRC / "finders.c"
    t = fc.read_text(encoding="utf-8")
    if MARK not in t:
        head = "int isViableStructurePos(int structureType, Generator *g, int x, int z, uint32_t flags)\n{"
        assert head in t, "finders.c: firma de isViableStructurePos no encontrada"
        wrapper = (
            f"/* {MARK}: registra el bioma que isViableStructurePos usa para validar */\n"
            "static inline int cb_getBiomeAt(Generator *g, int scale, int x, int y, int z)\n"
            "{ int id = getBiomeAt(g, scale, x, y, z); g->cb_last_biome = id; return id; }\n"
            "#define getBiomeAt cb_getBiomeAt\n")
        i = t.index(head)
        # final de la funcion: primer "\n}\n" despues de la etiqueta L_not_viable
        j = t.index("L_not_viable:", i)
        k = t.index("\n}\n", j) + 3
        t = t[:i] + wrapper + t[i:k] + f"#undef getBiomeAt /* {MARK} */\n" + t[k:]
        fc.write_text(t, encoding="utf-8")


if __name__ == "__main__":
    patch()
    print("parche aplicado/verificado")
