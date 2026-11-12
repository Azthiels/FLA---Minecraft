# FLA - Minecraft (Farm Locator Azthiels): escaner + limpiador + analizador de grupos
Repo: https://github.com/Azthiels/FLA---Minecraft (rama main). El paquete Python se sigue llamando `sa/`.

Proyecto personal de Azthiels (Cordoba, Argentina, UTC-3). Comunicacion en espanol.
El `README.md` tiene la documentacion tecnica (arquitectura, formato, modo grupos). Leelo antes de tocar el motor.

## Que es
Un programa (`python main.py`, TUI Textual) con 3 partes en pestanas, en el paquete `sa/`:
1. **Escaner** (`sa/escaner/`): todas las estructuras de un tipo hasta el world border usando **Cubiomes** (C,
   `lib/scanner.dll`/`.so`, via ctypes). Modo `grupos` (por defecto): solo guarda las que tienen una vecina valida que
   entra en el radio de activacion; el filtro geometrico corre en C antes del chequeo de bioma (~15x en Witch Hut).
   Modo `todas`: el listado completo.
2. **Limpiador** (`sa/limpiador.py`): saca las estructuras sin ninguna vecina compatible (numpy, busqueda espacial).
3. **Analizador** (`sa/analizador.py`): grupos maximales (dobles, triples, cuadruples...), maximo teorico, punto AFK
   (circulo minimo de las esquinas de las cajas) y recomendacion (lo mas grande que haya; si no hay quads, triple/doble).

Al terminar una parte, la TUI carga el archivo en la siguiente. Los 3 usan el mismo criterio de par
(`(|dx|+L)^2+(|dz|+L)^2 <= (2R)^2`, exacto para cajas cuadradas iguales), definido en C (`shim.c: pair_ok`) y en
`sa/geometria.py:par_ok` / `sa/limpiador.py:pares`. Si se cambia en uno, cambiarlo en todos (el test `grupos` lo verifica).

## Comandos
```
pip install -r requirements.txt   # textual, numpy
python main.py                    # TUI
python -m tests [filtro...]       # tests (todos tardan varios minutos; t_equivalencia es lo mas lento)
python bench/bench.py [rapido]    # benchmark todas vs grupos + hilos
python bench/profile_native.py    # perfil por etapa/estructura
python build_lib.py               # recompilar lib/ si cambia cubiomes_src (en esta PC no hay gcc: usa ziglang, ~2 min)
```

## Que cuidar (importante)
- **Archivos enormes: no abrirlos enteros.** `resultados.jsonl` pesa ~380 MB (8,9 M de Witch Huts, formato viejo,
  scan interrumpido a ~8 %), `structure.json` ~54 MB (formato mas viejo todavia). Muestras o streaming, nunca `json.load`.
- `resultados.*` es el scan real **interrumpido** del motor anterior (seed `6283985518325545008`, 26.3, swamp_hut, mundo
  completo, modo "todas", formato JSONL v1). El motor nuevo **no** lo reanuda (formato distinto); se puede limpiar/analizar
  directamente (`resultados_limpio.*` es esa salida). **No borrarlo ni truncarlo a mano.**
- `cubiomes_src/` es externo salvo `shim.c` (nuestro) y el parche de `tools/apply_patches.py`. Al actualizar Cubiomes
  (26.4): reemplazar la carpeta conservando `shim.c`, `python tools/apply_patches.py`, borrar `lib/`, `python build_lib.py`.
- Si cambia `NSTAT` en `shim.c`, actualizar `STAT_NAMES` en `sa/nativo.py` (al importar se verifica y avisa).
- No compilar con `-ffast-math` ni `-march=native`: cambian el redondeo del ruido y los resultados.
- Nether Fossil no esta soportado a proposito. Desert Pyramid, Jungle Temple y Mansion en 1.18+ usan una heuristica de terreno.
- Cajas de spawn (`sa/estructuras.py`): exactas para Witch Hut (9x9 conservador por la rotacion), Desert Pyramid, Jungle
  Temple, Igloo; Monument y el resto son aproximadas. El radio es 2D (no se modela la altura del AFK).
- `_viejo/` tiene los modulos anteriores (core/engine/config/main/tests/Analyzer, shim.c y dll viejos) como respaldo
  hasta que se suba a git; se puede borrar despues. `bench/legacy_core.py` SI se usa (test de equivalencia).

## Estado / proximos pasos
- Hecho: reestructuracion modular, modo grupos en C, formato `.sab`, limpiador, analizador, TUI de 3 pestanas, tests.
- Pendiente de decidir/medir: rotacion real de la Witch Hut (cajas 7x9 exactas en vez de 9x9), radio 3D segun altura
  del AFK, cajas reales de estructuras jigsaw (outposts, etc.), regla de 24 bloques de distancia minima de spawn.
- Hecho: prefiltro de clima 1.18+ (`shim.c: clima_posible`, `sa/clima.py`), exacto por cota de vecino mas cercano;
  depende de que las hojas de superficie cubran toda la caja de clima (se verifica por version; en 26.2 no, se apaga).
  Si se toca, correr `python -m tests clima`. Witch Hut mundo completo: ~6 min con 8 hilos.
- Hecho: analizador a gran escala (dobles de grado 1 en numpy, grafo solo para grado >= 2, subgrupos por soporte
  del circulo minimo). Tests: nunca escanear el mundo completo (areas chicas); el runner corta tests de > 300 s.
- Resultado real (seed 6283985518325545008, 26.3, mundo completo): 4,34 M huts agrupables, 243 triples, 0 cuadruples.
- Ideas siguientes: extender el prefiltro a Village/Outpost/Monument (chequeos de bioma multiples), rotacion real.
- Git: rama main, remoto origin = GitHub (arriba). Identidad noreply de GitHub (el push con email real esta
  bloqueado por la cuenta). `.gitignore` excluye datos (.sab/.jsonl/meta), lib/ y _viejo/.
