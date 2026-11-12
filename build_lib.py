"""Compila la libreria nativa si no hay binario para tu sistema. Usa gcc/clang/cc y, si no hay, instala 'ziglang' (no requiere instalar nada mas)."""
import os, shutil, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "cubiomes_src"
FILES = ["shim.c", "finders.c", "carver.c", "generator.c", "layers.c", "biomenoise.c", "biomes.c", "noise.c",
         "terrainnoise.c", "util.c", "quadbase.c", "xradv.c"] + sorted(
    str(p.relative_to(SRC)) for d in ("features", "loot") for p in (SRC / d).rglob("*.c"))


def compilar():
    (BASE / "lib").mkdir(exist_ok=True)
    nombre = "scanner.dll" if os.name == "nt" else ("scanner.dylib" if sys.platform == "darwin" else "scanner.so")
    out = BASE / "lib" / nombre
    flags = ["-O3", "-fwrapv", "-ffp-contract=off", "-shared"] + ([] if os.name == "nt" else ["-fPIC"])
    libs = [] if os.name == "nt" else ["-lm"]
    for cc in ("gcc", "clang", "cc"):
        if shutil.which(cc):
            if subprocess.run([cc, *flags, "-o", str(out), *FILES, *libs], cwd=SRC).returncode == 0:
                return out
    # ultimo recurso: zig como compilador de C
    subprocess.run([sys.executable, "-m", "pip", "install", "ziglang"], check=True)
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", *flags, "-o", str(out), *FILES], cwd=SRC)
    if r.returncode != 0:
        raise RuntimeError("No se pudo compilar la libreria nativa.")
    return out


if __name__ == "__main__":
    print(compilar())
