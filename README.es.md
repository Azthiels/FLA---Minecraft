# FLA - Minecraft (Farm Locator Azthiels)

Encuentra en una seed de Minecraft los lugares donde varias estructuras del mismo tipo (Witch Huts, Monuments,
Outposts...) se pueden activar a la vez desde un punto AFK, para granjas multiples. TUI en Python + Cubiomes en C.

*[English version](README.md) · [Guia paso a paso (en ingles)](docs/GUIDE.md)*. Este archivo es la documentacion
tecnica. La interfaz esta en ingles por defecto; en espanol: `python main.py --lang es` o `{"IDIOMA": "es"}` en
`config.json`.

    pip install -r requirements.txt     # textual, numpy
    python main.py                      # TUI con las 3 partes (teclas 1/2/3 cambian de pestana)
    python -m tests                     # tests (o algunos: python -m tests grupos analizador cajas)
    python bench/bench.py [rapido]      # benchmark modo todas vs grupos + hilos
    python bench/profile_native.py      # coste por etapa y por estructura (1 hilo)
    python -m sa.analizador <archivo>   # analizador por consola
    python build_lib.py                 # recompilar lib/ (gcc/clang/cc o, si no hay, ziglang via pip)

## Las 3 partes
1. **Escaner**: seed, version (1.7 a 26.x), estructura, dimension, cajas y biomas -> todas las estructuras de ese tipo
   hasta el world border. Dos modos:
   * **Solo agrupables** (recomendado): guarda solo las que tienen otra con la que se pueden activar a la vez.
     Mismo resultado que guardar todas y pasar el limpiador, pero ~15x mas rapido en Witch Hut (ver abajo).
   * **Todas**: el listado completo, como antes.
2. **Limpiador**: descarta las estructuras sin ninguna vecina compatible. La busqueda es espacial (revisa todas las
   vecinas, no la siguiente de la lista). Para escaneos en modo "todas" o `.jsonl` viejos.
3. **Analizador**: busca todos los grupos (dobles, triples, cuadruples...) cuyas cajas entran juntas en el radio
   de activacion (128) alrededor de un punto AFK, cuenta cuantos hay de cada tamano, da el maximo teorico para
   esa estructura y recomienda el mejor grupo que tenga el mundo con su punto AFK. Si no hay cuadruples recomienda
   la mejor triple, y si no la mejor doble. Exporta `<archivo>.grupos.json` y `.grupos.csv`.

## Arquitectura
| modulo | rol |
|---|---|
| `cubiomes_src/` | Cubiomes (MIT, fork con 26.x) + `shim.c` (escaneo por tile, modo grupos) + parche de `tools/apply_patches.py` |
| `sa/nativo.py` | bindings ctypes, versiones, estructuras, biomas, seeds |
| `sa/estructuras.py` | caja de spawn de cada estructura (lado/offset, exacta o aprox.) y maximo teorico por grupo |
| `sa/geometria.py` | criterio de pares, circulo minimo (Welzl), punto AFK |
| `sa/datos.py` | formato `.sab` + `.meta.json`, lectura de `.jsonl` viejo, exportacion |
| `sa/escaner/` | `plan.py` (cajas -> rectangulos disjuntos -> tiles) y `motor.py` (hilos, escritor unico, checkpoint) |
| `sa/limpiador.py`, `sa/analizador.py` | partes 2 y 3 |
| `sa/tui/` | `app.py` + una pantalla por parte + `comunes.py` (modales de biomas y cajas) |
| `tests/` | escaner (equivalencia con el motor viejo, cajas, biomas, lotes, hilos, reanudacion, kill, errores) + grupos |
| `bench/` | benchmark, perfil nativo, `legacy_core.py` (motor original, solo para el test de equivalencia) |

## Modo grupos (en C, `sh_scan_tile` con `F_GROUPS`)
Lo caro es `isViableStructurePos` (ruido de bioma); `getStructurePos` es matematica pura (~30-40 M/s por hilo).
Por cada tile se calculan las posiciones de tile + halo, y solo se consulta el bioma de las que tienen alguna vecina
geometricamente posible; las vecinas se validan bajo demanda (memoizado). Se guarda una estructura si existe una
vecina **valida** (reglas + filtro de biomas + terreno + dentro de las cajas) con la que entra en el radio.

Criterio de par (exacto para cajas cuadradas iguales de lado `L`): `(|dx|+L)^2 + (|dz|+L)^2 <= (2R)^2`.
Es el mismo en C, en el limpiador y en el analizador; el test `grupos` comprueba que modo grupos == todas + limpiador.

Witch Hut 26.3, seed del scan real: el bioma se consulta en ~5 % de las posiciones -> ~15x mas rapido; en el 8 %
del mundo ya escaneado quedan 350 964 de 8 905 103 huts (17 triples, 176 676 dobles, ninguna cuadruple).

## Prefiltro de clima 1.18+ (checkbox en la TUI, `--sin-clima` para apagarlo)
En 1.18+ el bioma sale del **vecino mas cercano** en un espacio de 6 parametros de clima (arbol de hiperrectangulos).
El prefiltro (`shim.c: clima_posible`) calcula los parametros de a uno, los mas selectivos primero, y descarta en
cuanto es imposible que gane un bioma buscado: como las hojas de superficie cubren toda la caja de clima, siempre hay
una hoja a distancia `sum(ex_i^2)` (lo que el punto se sale de la caja), y si todas las hojas buscadas ya estan mas
lejos con los parametros conocidos, no pueden ganar. Es una **cota exacta**, no una heuristica.
* La cobertura de la capa de profundidad 0 se verifica por version al usarla (`sa/clima.py`, ~0,5 s, en cache);
  se cumple en todas las versiones 1.18+. Las hojas sin gemela en profundidad 1 (14 en **26.2**, biomas nevados y
  de playa) son zonas donde la cota no vale: si el punto puede caer ahi, se calcula el bioma completo. Asi el
  prefiltro es exacto en todas las versiones 1.18+.
  Aplica a Witch Hut, piramides, iglu, ruinas oceanicas, naufragios, tesoros y trail ruins.
* Witch Hut 26.3: el 99,2 % de las posiciones se descarta solo con clima; el bioma completo se calcula
  practicamente solo en las huts que existen. Escaneo del mundo completo en modo grupos + clima: ~40 M reg/s
  con 8 hilos (~6 minutos para las 13 700 M de regiones; antes ~4 horas).
* `tests`: `t_clima_cobertura` (prueba de cobertura) y `t_clima_equivalencia` (on == off en 11 casos x 2 modos).

## Modo auto y linea de comandos
Con el checkbox **Modo auto (1 -> 2 -> 3)** del escaner, al terminar un escaneo completo se limpia (solo en modo
"todas"; en modo grupos ya sale limpio) y se analiza solo, y avisa con una notificacion del sistema con el mejor
grupo. En la pestana 3, abajo, hay un recuadro por tipo encontrado (cuadruples, triples, dobles) con sus mejores
opciones y el `/tp` de cada una, mas el detalle del grupo seleccionado en la tabla.

    python main.py --seed 6283985518325545008 --version 26.3 --estructura 3 --salida mundo_witch_huts --auto --iniciar
Completa el formulario y arranca (`python main.py --help` para todas las opciones).

## Analizador a gran escala
* Los pares cuyas dos estructuras no tienen ninguna otra vecina (grado 1) son dobles maximales seguras: se
  resuelven en bloque con numpy, punto AFK incluido (`geometria.afk_pares`, identico bit a bit a `punto_afk`:
  las distancias se comparan al cuadrado, que es exacto con coordenadas enteras o .5).
* El grafo + Bron-Kerbosch solo se arma con las estructuras de grado >= 2 (donde puede haber triples o mas).
* Si un clique no entra entero, todo subconjunto que si entre tiene que dejar afuera alguna de las 2-3 cajas que
  fijan su circulo minimo: se ramifica solo sobre esas (antes se probaban todos los subconjuntos, exponencial).
* `<base>.grupos.json` guarda el resumen y los primeros 2000 grupos; `<base>.grupos.csv`, todos.
* Tests: rapido == todo-por-el-grafo en 7 estructuras reales (de Monument a Ruined Portal con radio 400) y un caso
  sintetico con grupos de hasta 10; subgrupos == fuerza bruta en 300 casos.

## Tests
`python -m tests [filtro...]`. Cada test tiene un limite de 300 s (`SA_TEST_LIMITE`): si se pasa, se vuelca el
stack de todos los hilos y el proceso termina con error; cada 3 minutos imprime que test sigue corriendo.
Los tests usan areas chicas (radios de miles a cientos de miles de bloques), nunca el mundo completo.

## Licencia
MIT (ver `LICENSE`). Incluye Cubiomes (MIT, Cubitect) y su libreria de loot (MIT, ScriptLine).

## Cajas de spawn (`sa/estructuras.py`)
Cuadrado `[x+offset, x+offset+lado]`, conservador porque la rotacion no se calcula (lado = dimension mayor).
Witch Hut 7x9 -> 9x9; Desert Pyramid 21; Jungle Temple 12x15 -> 15; Igloo 7x8 -> 8; Ocean Monument 58 centrado (aprox.).
El resto usa 16 (un chunk, aproximado): ajustalo en la TUI. El radio es en planta (2D): con el jugador mas alto o mas
bajo que la zona de spawn, el radio horizontal efectivo es menor (`sqrt(128^2 - dy^2)`), bajalo en la TUI.
Maximo teorico: hay como mucho una estructura por region; con regiones de 512 (Witch Hut) y radio 128 -> 4.

## Archivos (`<base>` = nombre elegido)
* `<base>.sab`: cabecera de 16 bytes (`SAB1`, version, tamano de registro) + registros de 12 bytes little-endian
  `x, z, bioma` (int32). Es lo que escribe C tal cual; ~3,5x mas chico que el JSONL. Orden de descubrimiento.
* `<base>.meta.json`: seed, version, estructura, modo, radio/caja del grupo, cajas, biomas, nombres de biomas,
  conteos, estado (`en_ejecucion` / `interrumpido` / `completado` / `error`), parametros, contadores nativos.
* `<base>.checkpoint.json`: tiles confirmados + tamano en bytes del `.sab` (para reanudar).
* `<base>.grupos.json` / `.grupos.csv`: salida del analizador.

## Escritura y recuperacion
Los hilos de calculo no escriben: mandan cada tile a **un unico hilo escritor**. Buffer de `BATCH_SIZE` (50) registros
-> una escritura; pasados `FLUSH_INTERVAL_S` (5 s) se escribe igual. Un tile se *confirma* solo cuando sus registros
ya estan en el archivo; el checkpoint (cada 10 s, con fsync) guarda los tiles confirmados y el tamano del archivo.
Al reanudar se **trunca el `.sab` a ese tamano** y se re-escanean los tiles no confirmados (determinista): sin
duplicados ni huecos aunque se mate el proceso. Se valida que seed, version, estructura, dimension, biomas, cajas,
tile, modo y radio/caja del grupo coincidan.

## Notas de precision
* Nether Fossil **no** esta soportado: Cubiomes solo da celdas candidatas sin comprobar terreno.
* Desert Pyramid / Jungle Temple / Mansion en 1.18+: heuristica de terreno de Cubiomes (`terrain_heuristic` en el meta).
* Nether: el world border se escala 1:8. Las cajas se expresan en coordenadas de la dimension elegida.
* Compilado con `-ffp-contract=off` y sin `-ffast-math`/`-march=native` para no alterar el redondeo del ruido.
* Version 26.4: cuando el fork de Cubiomes la incorpore, reemplaza `cubiomes_src/` **conservando `shim.c`**, ejecuta
  `python tools/apply_patches.py`, borra `lib/` y ejecuta `python build_lib.py`; el selector la mostrara sola.
