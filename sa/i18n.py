"""Textos visibles en ingles y espanol.

    from sa.i18n import t
    t("esc.titulo")                     -> "Scan options" / "Opciones del escaneo"
    t("lim.quedan", n=10)               -> con formato

El idioma se elige con (en orden): --lang en|es, la variable SA_LANG, o "IDIOMA" en config.json. Por defecto: en.
Para agregar un idioma: sumar una columna a cada entrada de TEXTOS y su codigo a IDIOMAS.
"""
import os

from sa import config

IDIOMAS = ("en", "es")
_idioma = (os.environ.get("SA_LANG") or getattr(config, "IDIOMA", "en") or "en").lower()
if _idioma not in IDIOMAS:
    _idioma = "en"


def idioma() -> str:
    return _idioma


def set_idioma(cod: str):
    global _idioma
    cod = (cod or "en").lower()
    if cod not in IDIOMAS:
        raise ValueError(f"Unknown language '{cod}'. Available: {', '.join(IDIOMAS)}")
    _idioma = cod


def t(clave: str, **kw) -> str:
    par = TEXTOS.get(clave)
    if par is None:
        return clave
    s = par[IDIOMAS.index(_idioma)] if _idioma != "en" else par[0]
    return s.format(**kw) if kw else s


# clave: (ingles, espanol)
TEXTOS = {
    # ---------------------------------------------------------------- app
    "app.tab1": ("1 Scanner", "1 Escaner"),
    "app.tab2": ("2 Cleaner", "2 Limpiador"),
    "app.tab3": ("3 Analyzer", "3 Analizador"),
    "app.salir": ("Quit", "Salir"),
    "app.escaner": ("Scanner", "Escaner"),
    "app.limpiador": ("Cleaner", "Limpiador"),
    "app.analizador": ("Analyzer", "Analizador"),
    "app.guardando": ("Saving before quitting...", "Guardando antes de salir..."),
    "app.auto_titulo": ("Auto mode", "Modo auto"),
    "app.auto_grupos": ("Groupable mode: the result is already clean, going straight to the analyzer.",
                        "Modo grupos: el resultado ya viene limpio, paso directo al analizador."),
    "app.auto_error": ("FLA: analysis error", "FLA: error en el analisis"),
    "app.auto_error_msg": ("Check tab 3", "Revisa la pestana 3"),
    "app.auto_fin": ("FLA: analysis finished", "FLA: analisis terminado"),
    "app.auto_mejor": ("Best: {tipo} at X {x}, Z {z} (margin {m})", "Mejor: {tipo} en X {x}, Z {z} (margen {m})"),
    "app.auto_nada": ("No groups in this seed", "No hay grupos en esta seed"),

    # ---------------------------------------------------------------- comunes
    "com.entero": ("{campo}: must be a whole number", "{campo}: tiene que ser un numero entero"),
    "com.minimo": ("{campo}: must be >= {min}", "{campo}: tiene que ser >= {min}"),
    "com.error": ("Error:", "Error:"),
    "com.no_existe": ("File not found: {ruta}", "No existe el archivo: {ruta}"),
    "bio.titulo": ("Search only in these biomes (space to toggle)", "Buscar solo en estos biomas (espacio para marcar/desmarcar)"),
    "bio.todos": ("All", "Todos"),
    "bio.ninguno": ("None", "Ninguno"),
    "bio.uno": ("Pick at least one biome", "Elegi al menos un bioma"),
    "btn.aplicar": ("Apply", "Aplicar"),
    "btn.cancelar": ("Cancel", "Cancelar"),
    "caj.titulo": ("Bounding boxes in {dim} coordinates (border: +-{r:,}).\nNo boxes = the whole world is scanned.",
                   "Bounding boxes en coordenadas de {dim} (borde: +-{r:,}).\nSin cajas = se escanea el mundo completo."),
    "caj.agregar": ("Add box", "Agregar caja"),
    "caj.quitar": ("Remove selected", "Quitar seleccionada"),
    "caj.vaciar": ("Clear", "Vaciar"),
    "caj.tamano": ("Size", "Tamano"),
    "caj.enteros": ("Coordinates must be whole numbers", "Las coordenadas deben ser numeros enteros"),

    # ---------------------------------------------------------------- escaner
    "esc.opciones": ("Scan options", "Opciones del escaneo"),
    "esc.seed": ("Seed (number or text)", "Seed (numero o texto)"),
    "esc.seed_ej": ("e.g. -4172144997902289642", "ej: -4172144997902289642"),
    "esc.version": ("Version", "Version"),
    "esc.dimension": ("Dimension", "Dimension"),
    "esc.estructura": ("Structure (one at a time)", "Estructura (una a la vez)"),
    "esc.elegi": ("Pick a structure", "Elegi una estructura"),
    "esc.borde": ("World border radius", "Radio del world border"),
    "esc.biomas": ("Biomes", "Biomas"),
    "esc.area": ("Area (bounding boxes)", "Area (bounding boxes)"),
    "esc.que": ("What to save", "Que guardar"),
    "esc.modo_grupos": ("Groupable only (fast)", "Solo agrupables (rapido)"),
    "esc.modo_todas": ("All structures", "Todas"),
    "esc.radio_g": ("Activation radius", "Radio de activacion"),
    "esc.lado": ("Box side", "Lado de la caja"),
    "esc.hilos": ("Threads (this PC: {n})", "Hilos (este equipo: {n})"),
    "esc.lote": ("Write batch", "Lote de escritura"),
    "esc.salida": ("Output (base name: .sab + .meta.json + .checkpoint.json)",
                   "Salida (nombre base: .sab + .meta.json + .checkpoint.json)"),
    "esc.auto": ("Auto mode (1 -> 2 -> 3)", "Modo auto (1 -> 2 -> 3)"),
    "esc.auto_tip": ("When the scan finishes, clean (if needed) and analyze automatically",
                     "Al terminar el escaneo, limpia (si hace falta) y analiza solo"),
    "esc.sobrescribir": ("Overwrite previous output", "Sobrescribir salida previa"),
    "esc.clima": ("1.18+ climate prefilter", "Prefiltro de clima 1.18+"),
    "esc.clima_no": ("Not available for this structure/version (only structures with a single biome check)",
                     "No aplica a esta estructura/version (solo estructuras con un unico chequeo de bioma)"),
    "esc.iniciar": ("Start / resume scan", "Iniciar / reanudar escaneo"),
    "esc.detener": ("Stop (saves a checkpoint)", "Detener (guarda y deja checkpoint)"),
    "esc.deteniendo": ("Stopping (saving)...", "Deteniendo (guardando)..."),
    "esc.ayuda": ("Ready. Fill in the options and press Start. If a checkpoint with the same parameters exists, the scan "
                  "resumes by itself.\n[b]Groupable only[/b]: saves only structures that have another one they can be "
                  "activated with at the same time (same result as saving all and cleaning, much faster). "
                  "[b]Auto mode[/b]: runs scanner -> cleaner -> analyzer.",
                  "Listo. Completa los datos y presiona Iniciar. Si ya existe un checkpoint con los mismos "
                  "parametros, el escaneo se reanuda solo.\n[b]Solo agrupables[/b]: guarda solo las estructuras "
                  "que tienen otra con la que se pueden activar a la vez (mismo resultado que guardar todas y "
                  "limpiar, mucho mas rapido). [b]Modo auto[/b]: encadena escaner -> limpiador -> analizador."),
    "esc.encontradas": ("Found (latest)", "Encontradas (ultimas)"),
    "esc.col_bioma": ("Biome", "Bioma"),
    "esc.todos_validos": ("all valid ones", "todos los validos"),
    "esc.n_elegidos": ("{n} selected", "{n} elegidos"),
    "esc.mundo": ("whole world", "mundo completo"),
    "esc.n_cajas": ("{n} box(es)", "{n} caja(s)"),
    "esc.sin_estructuras": ("No structures for this dimension in this version.",
                            "No hay estructuras para esta dimension en esta version."),
    "esc.info": ("Possible biomes: {biomas}.\nBox for groups: {nota}{aprox}\n"
                 "Region: {rb} blocks -> at most {teo} together with radius {r}.",
                 "Biomas posibles: {biomas}.\nCaja para grupos: {nota}{aprox}\n"
                 "Region: {rb} bloques -> como mucho {teo} juntas con radio {r}."),
    "esc.segun_terreno": ("(depends on terrain/dimension)", "(segun terreno/dimension)"),
    "esc.aprox": (" [approx.]", " [aprox.]"),
    "esc.primero_estructura": ("Pick a structure first", "Primero elegi una estructura"),
    "esc.sin_biomas": ("This structure does not depend on selectable biomes", "Esta estructura no depende de biomas elegibles"),
    "esc.falta_estructura": ("Pick a structure", "Elegi una estructura"),
    "esc.f_borde": ("Border radius", "Radio del border"),
    "esc.f_lote": ("Batch", "Lote"),
    "esc.f_hilos": ("Threads", "Hilos"),
    "esc.f_radio_g": ("Activation radius", "Radio de activacion"),
    "esc.f_lado": ("Box side", "Lado de la caja"),
    "esc.falta_salida": ("The output path is missing", "Falta la ruta de salida"),
    "esc.no_inicio": ("Could not start:", "No se pudo iniciar:"),
    "esc.no_inicio_t": ("Scan not started", "Escaneo no iniciado"),
    "esc.completado": ("SCAN COMPLETED", "ESCANEO COMPLETADO"),
    "esc.interrumpido": ("SCAN INTERRUPTED (can be resumed)", "ESCANEO INTERRUMPIDO (se puede reanudar)"),
    "esc.con_errores": ("SCAN FAILED: {e}", "ESCANEO CON ERRORES: {e}"),
    "esc.msg_fin": ("{n:,} structures in {t}", "{n:,} estructuras en {t}"),
    "esc.sig_auto": ("\n[b]Auto mode:[/b] the analysis continues by itself.", "\n[b]Modo auto:[/b] sigue el analisis solo."),
    "esc.sig_3": ("\nNext step: tab [b]3 Analyzer[/b] (the file is already loaded).",
                  "\nSiguiente paso: pestana [b]3 Analizador[/b] (el archivo ya esta cargado)."),
    "esc.sig_2": ("\nNext step: tab [b]2 Cleaner[/b] (the file is already loaded).",
                  "\nSiguiente paso: pestana [b]2 Limpiador[/b] (el archivo ya esta cargado)."),
    "esc.resumen_fin": ("[b {c}]{tit}[/b {c}]   {n:,} structures saved ({modo} mode)\n"
                        "Total time: {t}   Regions: {r:,}/{rt:,}\nFile: {f}{sig}",
                        "[b {c}]{tit}[/b {c}]   {n:,} estructuras guardadas (modo {modo})\n"
                        "Tiempo total: {t}   Regiones: {r:,}/{rt:,}\nArchivo: {f}{sig}"),
    "esc.limite": (" (limit +-{l:,})", " (limite +-{l:,})"),
    "esc.ahorro": ("   full biome check on {p:.2f}% of positions", "   bioma completo en {p:.2f}% de las posiciones"),
    "esc.clima_desc": (" (climate skipped {n:,})", " (clima descarto {n:,})"),
    "esc.progreso": ("[b]{est}[/b] | {dim} | {ver} | seed {seed} | {modo} mode{clima}\n"
                     "Area: {area}   Biomes: {biomas}\n"
                     "Regions: {h:,}/{tot:,}  ({falta:,} left)  {pct:.2f}%\n"
                     "Saved: {enc:,} (written {esc:,})   {vel:,.0f} reg/s{ahorro}\n"
                     "Elapsed {t}   ETA {eta}\n"
                     "Threads {nh}: {hil}   {rean}",
                     "[b]{est}[/b] | {dim} | {ver} | seed {seed} | modo {modo}{clima}\n"
                     "Area: {area}   Biomas: {biomas}\n"
                     "Regiones: {h:,}/{tot:,}  (restan {falta:,})  {pct:.2f}%\n"
                     "Guardadas: {enc:,} (escritas {esc:,})   {vel:,.0f} reg/s{ahorro}\n"
                     "Transcurrido {t}   ETA {eta}\n"
                     "Hilos {nh}: {hil}   {rean}"),
    "esc.mas_clima": (" + climate", " + clima"),
    "esc.reanudado": ("(resumed)", "(reanudado)"),
    "modo.grupos": ("groupable", "grupos"),
    "modo.todas": ("all", "todas"),

    # ---------------------------------------------------------------- limpiador
    "lim.entrada": ("Input file (.sab or old .jsonl)", "Archivo de entrada (.sab o .jsonl viejo)"),
    "lim.radio": ("Activation radius (blocks)", "Radio de activacion (bloques)"),
    "lim.lado": ("Box side (empty = from the scan/structure)", "Lado de la caja (vacio = el del escaneo/estructura)"),
    "lim.salida": ("Output (base name, empty = <input>_limpio)", "Salida (nombre base, vacio = <entrada>_limpio)"),
    "lim.limpiar": ("Clean", "Limpiar"),
    "lim.limpiando": ("Cleaning...", "Limpiando..."),
    "lim.ayuda": ("Discards structures that have no other structure they can be activated with at the same time. "
                  "Before discarding one, all its neighbours are checked.\n\n"
                  "If the scan used [b]Groupable only[/b] it is already clean: go straight to the Analyzer.",
                  "Descarta las estructuras que no tienen ninguna otra con la que se puedan activar a la vez. "
                  "Antes de descartar una se revisan todas sus vecinas.\n\n"
                  "Si el escaneo se hizo en modo [b]Solo agrupables[/b] ya viene limpio: pasa directo al Analizador."),
    "lim.listo": ("Pick a file and press Clean.", "Elegi un archivo y presiona Limpiar."),
    "lim.leyendo": ("Reading {n:,} records...", "Leyendo {n:,} registros..."),
    "lim.fin": ("[b green]CLEANING FINISHED[/b green] in {s:.1f}s\nInput: {e:,} structures\n"
                "Kept: [b]{q:,}[/b]   discarded: {d:,}   compatible pairs: {p:,}\n"
                "Criterion: radius {r}, box {l}x{l}\nOutput: {f}\n\nNext step: tab [b]3 Analyzer[/b] (already loaded).",
                "[b green]LIMPIEZA TERMINADA[/b green] en {s:.1f}s\nEntrada: {e:,} estructuras\n"
                "Quedan: [b]{q:,}[/b]   descartadas: {d:,}   pares compatibles: {p:,}\n"
                "Criterio: radio {r}, caja {l}x{l}\nSalida: {f}\n\nSiguiente paso: pestana [b]3 Analizador[/b] (ya esta cargado)."),
    "lim.notif": ("{q:,} of {e:,} kept", "Quedan {q:,} de {e:,}"),
    "lim.notif_t": ("Cleaning finished", "Limpieza terminada"),
    "lim.f_radio": ("Radius", "Radio"),

    # ---------------------------------------------------------------- analizador
    "ana.archivo": ("File (.sab from the scanner/cleaner, or .jsonl)", "Archivo (.sab del escaneo/limpiador o .jsonl)"),
    "ana.archivo_ph": ("path to the file", "ruta al archivo"),
    "ana.radio": ("Activation radius (blocks)", "Radio de activacion (bloques)"),
    "ana.lado": ("Box side (empty = auto)", "Lado de la caja (vacio = auto)"),
    "ana.minimo": ("Minimum group size", "Tamano minimo de grupo"),
    "ana.min2": ("2 (doubles and up)", "2 (dobles en adelante)"),
    "ana.orden": ("Sort by", "Ordenar por"),
    "ana.o_dist": ("Closest to 0,0", "Cercania al 0,0"),
    "ana.o_margen": ("Margin (most room)", "Margen (mas holgado)"),
    "ana.analizar": ("Analyze", "Analizar"),
    "ana.analizando": ("Analyzing...", "Analizando..."),
    "ana.cargar": ("Load saved analysis", "Cargar analisis guardado"),
    "ana.ayuda": ("Finds every group whose boxes fit together inside the activation radius around an AFK point. "
                  "Bottom: the best options for each type found (quads, triples, doubles).\n\n"
                  "Full results in <file>.grupos.json and .grupos.csv.",
                  "Busca todos los grupos cuyas cajas entran juntas en el radio de activacion alrededor de un "
                  "punto AFK. Abajo: las mejores opciones de cada tipo encontrado (cuadruples, triples, dobles).\n\n"
                  "Resultados completos en <archivo>.grupos.json y .grupos.csv."),
    "ana.listo": ("Pick a file and press Analyze.", "Elegi un archivo y presiona Analizar."),
    "ana.seleccionado": ("Selected", "Seleccionado"),
    "ana.cols": (("Type", "AFK X", "AFK Z", "Margin", "Dist. 0,0", "Structures"),
                 ("Tipo", "AFK X", "AFK Z", "Margen", "Dist. 0,0", "Estructuras")),
    "ana.guardado": ("Saved analysis available{limpio}: {fecha}, {kb:,.0f} KB.",
                     "Hay un analisis guardado{limpio}: {fecha}, {kb:,.0f} KB."),
    "ana.de_limpio": (" (of the cleaned version)", " (de la version limpia)"),
    "ana.viejo": ("\n[yellow]The data file changed after that analysis: re-analyzing is recommended.[/yellow]",
                  "\n[yellow]El archivo de datos cambio despues de ese analisis: conviene re-analizar.[/yellow]"),
    "ana.no_cargar": ("Could not load:", "No se pudo cargar:"),
    "ana.cargado_n": ("Analysis loaded from disk (not recalculated)", "Analisis cargado del archivo (sin recalcular)"),
    "ana.cargado_t": ("Loaded", "Cargado"),
    "ana.f_radio": ("Radius", "Radio"),
    "ana.grupos_n": ("Groups: {c}", "Grupos: {c}"),
    "ana.fin_t": ("Analysis finished", "Analisis terminado"),
    "ana.ninguno": ("none", "ninguno"),
    "ana.incompleto": ("\n[yellow]Note: the source scan is '{e}': parts of the map are missing.[/yellow]",
                       "\n[yellow]Ojo: el escaneo de origen esta '{e}': faltan zonas del mapa.[/yellow]"),
    "ana.caja_aprox": ("\n[yellow]Approximate box: {n}[/yellow]", "\n[yellow]Caja aproximada: {n}[/yellow]"),
    "ana.de_disco": ("\n[cyan]Loaded from disk (analysis from {f}).[/cyan]", "\n[cyan]Cargado de disco (analisis del {f}).[/cyan]"),
    "ana.de_disco_viejo": (" [yellow]The data changed afterwards: re-analyzing is recommended.[/yellow]",
                           " [yellow]Los datos cambiaron despues: conviene re-analizar.[/yellow]"),
    "ana.faltan": (" (no {tipo} in what was scanned)", " (no hay {tipo} en lo escaneado)"),
    "ana.mejor_mundo": ("Best in this world: [b green]{tipo}[/b green]{faltan}", "Lo mejor de este mundo: [b green]{tipo}[/b green]{faltan}"),
    "ana.sin_grupos": ("[red]No groups at all:[/red] no structure can be activated together with another one with that radius.",
                       "[red]No hay ningun grupo:[/red] ninguna estructura se puede activar junto con otra con ese radio."),
    "ana.resumen": ("[b]{est}[/b] | seed {seed} | {ver} | radius {r} | box {l}x{l}\n"
                    "Structures: {n:,}   groups: {conteo}   (theoretical max: {teo})   {s:.1f}s\n{rec}{aviso}\n[dim]{f}[/dim]",
                    "[b]{est}[/b] | seed {seed} | {ver} | radio {r} | caja {l}x{l}\n"
                    "Estructuras: {n:,}   grupos: {conteo}   (maximo teorico: {teo})   {s:.1f}s\n{rec}{aviso}\n[dim]{f}[/dim]"),
    "ana.tabla_t": ("{n:,} of {tot:,} groups (all in the .csv)", "{n:,} de {tot:,} grupos (todos en el .csv)"),
    "ana.opcion": ("[b]{n}. AFK {x}, {z}[/b]\n   margin {m:.2f} - {d:,.0f} from 0,0\n   [dim]/tp @s {x} ~ {z}[/dim]",
                   "[b]{n}. AFK {x}, {z}[/b]\n   margen {m:.2f} - a {d:,.0f} del 0,0\n   [dim]/tp @s {x} ~ {z}[/dim]"),
    "ana.mejores_t": ("Best {tipo} ({n:,})", "Mejores {tipo} ({n:,})"),
    "ana.orden_dist": ("closest to 0,0", "mas cercanas al 0,0"),
    "ana.orden_margen": ("most margin", "con mas margen"),
    "ana.detalle": ("[b]{tipo}[/b] -> AFK X {x}, Z {z}\nFarthest corner at {d} (margin {m})\n{est}\n[dim]/tp @s {x} ~ {z}[/dim]",
                    "[b]{tipo}[/b] -> AFK X {x}, Z {z}\nEsquina mas lejana a {d} (margen {m})\n{est}\n[dim]/tp @s {x} ~ {z}[/dim]"),

    # tamanos de grupo: (singular, plural)
    "tam.2": (("double", "doubles"), ("doble", "dobles")),
    "tam.3": (("triple", "triples"), ("triple", "triples")),
    "tam.4": (("quad", "quads"), ("cuadruple", "cuadruples")),
    "tam.5": (("quintuple", "quintuples"), ("quintuple", "quintuples")),
    "tam.6": (("sextuple", "sextuples"), ("sextuple", "sextuples")),

    # ---------------------------------------------------------------- resumen por consola
    "txt.cab": ("{est} | seed {seed} | {ver} | radius {r} | box {l}x{l}{aprox}", "{est} | seed {seed} | {ver} | radio {r} | caja {l}x{l}{aprox}"),
    "txt.leidas": ("Structures read: {n:,}   compatible pairs: {p:,}   ({s:.1f}s)", "Estructuras leidas: {n:,}   pares compatibles: {p:,}   ({s:.1f}s)"),
    "txt.grupos": ("Groups: {c}", "Grupos: {c}"),
    "txt.ninguno": ("No groups at all: no structure can be activated together with another one.",
                    "No hay ningun grupo: ninguna estructura se puede activar junto con otra."),
    "txt.teorico": ("Theoretical max for this structure: {n}", "Maximo teorico para esta estructura: {n}"),
    "txt.recomendacion": ("Recommendation: {tipo} (the best this world has)", "Recomendacion: {tipo} (lo mejor que tiene este mundo)"),
    "txt.linea": ("  AFK X {x}, Z {z}  margin {m} blocks  {d:,.0f} from 0,0  -> {est}",
                  "  AFK X {x}, Z {z}  margen {m} bloques  a {d:,.0f} del 0,0  -> {est}"),

    # ---------------------------------------------------------------- errores del motor / datos
    "err.estructura_version": ("That structure does not exist in that version", "Esa estructura no existe en esa version"),
    "err.radio_borde": ("The world border radius must be positive", "El radio del world border debe ser positivo"),
    "err.un_bioma": ("Pick at least one biome", "Elegi al menos un bioma"),
    "err.modo": ("Unknown mode: {m}", "Modo desconocido: {m}"),
    "err.grupo_pos": ("Activation radius and box side must be positive", "Radio de activacion y lado de la caja deben ser positivos"),
    "err.ckpt_distinto": ("The existing checkpoint does not match in: {campos}. Change the output path or tick 'overwrite'.",
                          "El checkpoint existente no coincide en: {campos}. Cambia la ruta de salida o marca 'sobrescribir'."),
    "err.ckpt_corto": ("The data file is shorter than the checkpoint offset (file was modified).",
                       "El archivo de datos es mas corto que el offset del checkpoint (archivo alterado)."),
    "err.existe": ("Results already exist in {f}. Tick 'overwrite' or change the path.",
                   "Ya existen resultados en {f}. Activa 'sobrescribir' o cambia la ruta."),
    "err.generador": ("Could not create the native generator", "No se pudo crear el generador nativo"),
    "err.caja_4": ("Each box needs X1, Z1, X2, Z2", "Cada caja necesita X1, Z1, X2, Z2"),
    "err.caja_fuera": ("No box falls inside the world border (+-{l:,})", "Ninguna caja cae dentro del world border (+-{l:,})"),
    "err.seed_vacia": ("Empty seed", "Seed vacia"),
    "err.no_sab": ("{f} is not a valid .sab file", "{f} no es un archivo .sab valido"),
    "err.sab_version": ("{f}: version {v} / record size {r} not supported", "{f}: version {v} / registro {r} no soportados"),
    "err.no_existe": ("{f} does not exist", "No existe {f}"),

    # ---------------------------------------------------------------- notas de cajas (sa/estructuras.py)
    "caja.3": ("Witch Hut: 7x9 from the chunk corner, random rotation -> 9x9",
               "Witch Hut: 7x9 desde la esquina del chunk, rotacion aleatoria -> 9x9"),
    "caja.1": ("Desert Pyramid: 21x21 from the chunk corner", "Desert Pyramid: 21x21 desde la esquina del chunk"),
    "caja.2": ("Jungle Temple: 12x15 from the chunk corner, random rotation -> 15x15",
               "Jungle Temple: 12x15 desde la esquina del chunk, rotacion aleatoria -> 15x15"),
    "caja.4": ("Igloo (surface): 7x8 from the chunk corner -> 8x8", "Igloo (superficie): 7x8 desde la esquina del chunk -> 8x8"),
    "caja.8": ("Ocean Monument: 58x58 centred on the chunk (approx.)", "Ocean Monument: 58x58 centrado en el chunk (aprox.)"),
    "caja.def": ("No box data: 1 chunk (16x16) is assumed. Adjust the side for your farm.",
                 "Sin datos de la caja: se asume 1 chunk (16x16). Ajusta el lado segun la granja."),
}
