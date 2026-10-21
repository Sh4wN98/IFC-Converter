"""User interface texts: es (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Punto de control {name} ilegible ({error}), se calcula de nuevo",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "No se puede guardar el punto de control ({error}); se continúa sin él",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Formato no compatible “{fmt}”; formatos posibles: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Tipo de geometría no compatible “{geometry}”; tipos posibles: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Núcleo geométrico desconocido “{kernel}”; núcleos posibles: {kernels}",
    "IFC file not found: {path}": "Archivo IFC no encontrado: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell no puede leer archivos ifcXML ({name}). Exporte el modelo desde el programa de diseño como "
        ".ifc (formato de texto STEP) o .ifczip.",
    "Reading IFC file ({size}) …": "Leyendo el archivo IFC ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "Versión IFC no compatible ({error}). Compatibles: {supported}; {bridges} también se leen como el esquema "
        "relacionado más cercano.",
    "{note} Dimensions and positions stay unchanged.": "{note} Las dimensiones y posiciones no cambian.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Determinando la envolvente del edificio (geometría precalculada de forma aproximada) …",
    'The geometry kernel hung on {label} for more than {minutes} min: the element is skipped':
        'El núcleo geométrico lleva más de {minutes} min bloqueado en {label}: el elemento se omite',
    'The geometry kernel hung on {label} for more than {minutes} min in the rough pre-computation: the element is kept as part of the hull':
        'El núcleo geométrico lleva más de {minutes} min bloqueado en {label} (precálculo aproximado): el elemento se conserva como parte de la envolvente',
    'The geometry kernel hung on one of {count} elements for more than {minutes} min: they are computed one by one …':
        'El núcleo geométrico lleva más de {minutes} min bloqueado en uno de {count} elementos: se calculan uno por uno …',
    '{count} elements not computed because the geometry kernel hung on their chunk: they are skipped':
        '{count} elementos no calculados porque el núcleo geométrico se bloqueó en su paquete: se omiten',
    '{count} elements not computed because the geometry kernel hung on their chunk in the rough pre-computation: they are kept as part of the hull':
        '{count} elementos no calculados en el precálculo aproximado porque el núcleo geométrico se bloqueó en su paquete: se conservan como parte de la envolvente',
    "Computing geometry ({threads} threads) …": "Calculando la geometría ({threads} hilos) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "No se generó geometría: ninguno de los {count} elementos con geometría pudo convertirse (probablemente "
        "tipos de geometría no compatibles).",
    "The file contains no elements with geometry.": "El archivo no contiene elementos con geometría.",
    "Copying to the target folder ({size}) …": "Copiando a la carpeta de destino ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Error al copiar ({error}) – nuevo intento {attempt} en {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Copiando a la carpeta de destino … {copied} de {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "El archivo terminado no se pudo copiar a {folder} ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "El archivo terminado no se pudo copiar a {folder} ({error}). Está aquí: {path} – cópielo a mano.",
    "{count} extrusions with negative depth turned around": "{count} extrusiones con profundidad negativa invertidas",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} elementos recuperados del intento anterior, se calculan {count}",
    "Geometry contains itself (faulty file), not converted: {label}":
        "La geometría se contiene a sí misma (archivo defectuoso), no convertida: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Elemento muy anidado ({depth} niveles) {number} de {total} se calcula por separado: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Elemento {number} de {total} se calcula por separado: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} elementos calculados solo en el segundo intento (tolerancia más fina u otro núcleo)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Segundos intentos finalizados tras {seconds} s; los demás elementos sin geometría ya no se probaron por "
        "separado",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} cálculos de geometría siguen en marcha tras {seconds} s y se finalizan en segundo plano",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} necesitará probablemente unos {needed} GB de memoria; solo hay {available} GB libres. Cierre "
        "otros programas; si no, irá muy lento o la conversión se interrumpirá.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grueso {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Solo envolvente del edificio: el modelo no tiene una envolvente cerrada (falta la cubierta, faltan "
        "forjados o muros, p. ej. un modelo parcial sin la estructura): el aire exterior llega a casi todos los "
        "elementos (malla {voxel} m). En su lugar se omiten: {marked} elementos marcados como interiores "
        "(IsExternal = No) y {fittings} muebles, equipamiento, tuberías y conductos, acabados de techo y suelo; "
        "se convierten {kept} de {total} elementos.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Solo envolvente del edificio: {kept} de {total} elementos están en el exterior y se convierten, "
        "{inside} interiores omitidos (malla {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} sin geometría precalculada incluidos por seguridad",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} marcados como exteriores (IsExternal) incluidos",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} volúmenes de masa (envolventes alrededor del modelo) no contados como opacos",
    "{count} more": "{count} más",
    " Left out: {classes}.": " Omitidos: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Determinando la envolvente del edificio (buscando el aire exterior) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Envolvente del edificio: {kept} de {total} elementos en el exterior ({unknown} sin geometría "
        "precalculada, {flagged} por IsExternal), malla {voxel} m (gruesa {coarse} m, {cells} celdas, banda fina "
        "{band} celdas), geometría precalculada {coarse_seconds} s, envolvente {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Envolvente del edificio: malla engrosada a {voxel} m ({cells} celdas guardadas)",
    # preview.py
    "Saving preview ({count} triangles) …": "Guardando la vista previa ({count} triángulos) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Demasiados triángulos para la vista previa (más de {limit} por elemento).",
    "furniture": "mobiliario",
    "MEP": "instalaciones",
    "fasteners": "fijaciones",
    "reinforcement": "armaduras",
    "deeply nested": "anidados profundamente",
    # process.py
    "stack overflow": "desbordamiento de pila",
    "The memory was not enough (the process was ended by the system)":
        "No hubo memoria suficiente (el sistema finalizó el proceso)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Fallo en el núcleo geométrico rápido – reintentando solo con OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Fallo en el núcleo geométrico ({fatal}), tras el cual la conversión quedó bloqueada",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "La conversión no ha calculado nada durante {duration} (estaba bloqueada)",
    "{count} minutes": "{count} minutos",
    "{count} seconds": "{count} segundos",
    "stack overflow in the geometry kernel": "desbordamiento de pila en el núcleo geométrico",
    "memory access violation": "violación de acceso a memoria",
    "internal program abort": "aborto interno del programa",
    "Conversion ended without a result": "La conversión terminó sin resultado",
    "Conversion crashed: {name} (code {code})": "La conversión falló: {name} (código {code})",
    "Conversion crashed (code {code})": "La conversión falló (código {code})",
    "Crash in the geometry kernel ({fatal})": "Fallo en el núcleo geométrico ({fatal})",
    "Hang in the geometry kernel": "Bloqueo en el núcleo geométrico",
    "Crash in the geometry kernel": "Fallo en el núcleo geométrico",
    "New attempt ({attempt}. of at most {max})": "Nuevo intento ({attempt}.º de como máximo {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} en los ejes (IfcAlignment, IfcGrid). {again} sin los ejes …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} en {label}. {again}, este elemento se omite …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} en un elemento. {again}, se calcula primero y por separado …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} en uno de {count} elementos. {again}, estos se calculan primero y por separado para encontrar el "
        "afectado …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Conversión: {input} ({size}) -> {output}, formato {fmt}, {threads} hilos{options}{priority}",
    "(next to the IFC file)": "(junto al archivo IFC)",
    ", normal priority": ", prioridad normal",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Conocidos de conversiones anteriores de este archivo, omitidos (el núcleo geométrico falló o se bloqueó "
        "en ellos) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", los elementos ya calculados se recuperan …",
    " (exit code {code})": " (código de salida {code})",
    "Cancelled after {seconds} s: {path}": "Cancelado tras {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Error tras {seconds} s en {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Fallo tras {seconds} s en {path}: {error} (código de salida {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Bloqueado, cancelado tras {seconds} s: {path}",
    "Conversion of {path} failed": "La conversión de {path} ha fallado",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Terminado tras {seconds} s: {input} -> {output}, {elements} elementos, {missing} sin geometría, "
        "{skipped} omitidos",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Omitidos porque el núcleo geométrico falló o se bloqueó en ellos ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Sin geometría ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … y {count} más",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Poco espacio en la carpeta temporal para un punto de control; tras un fallo se calcula todo de nuevo",
    "size unknown": "tamaño desconocido",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Límite de memoria del proceso de conversión ({limit} GB) alcanzado",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Límite de memoria del proceso de conversión ({limit} GB) alcanzado; aun así la conversión llegó al final "
        "(p. ej. sin procesos auxiliares)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "No hubo memoria suficiente: la conversión puede usar como máximo {limit} GB ({share}\u202f% de la memoria) "
        "para que los demás programas sigan funcionando. Para este archivo el PC necesita más memoria.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Objeto de trabajo (job) para la conversión no disponible ({error}); se continúa sin límite de memoria",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "El proceso de conversión no está en el objeto de trabajo ({error}); se continúa sin límite de memoria",
    "Skipped elements could not be saved ({path}): {error}":
        "No se pudieron guardar los elementos omitidos ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (tras {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "En marcha desde hace {seconds} s, {percent}\u202f%: {message}",
    "{message}: {size} written …": "{message}: {size} escritos …",
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message}':
        'Sin avance desde hace {minutes} min aunque la conversión está calculando (CPU {cpu} s), {percent}\u202f%: {message}',
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Sin actividad de cálculo desde hace {seconds} s (CPU {cpu} s){fatal}, {percent}\u202f%: {message}",
    " after {fatal}": " tras {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "El proceso de conversión informa de un error fatal: {marker}",
    " (last {shown} KB of {size} KB)": " (últimos {shown} KB de {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Salida del proceso de conversión{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "No se pudo finalizar el proceso de conversión {pid}",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "La geometría Rhino hizo fallar un proceso auxiliar; se incluye como malla en su lugar: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "La geometría Rhino hizo fallar un proceso auxiliar; elemento omitido: {label}",
    "Writing Rhino file ({count} objects) …": "Escribiendo el archivo Rhino ({count} objetos) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) se lee como IFC2x3, que heredó sus entidades y atributos.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 es un borrador no publicado (túneles) y se lee como IFC4.3: IfcTunnel como IfcFacility, "
        "IfcTunnelPart como IfcFacilityPart, IfcUndergroundExcavation e IfcArchElement como "
        "IfcBuildingElementProxy; las referencias a conjuntos de datos (IfcDataSetInformation) se descartan.",
    "IFC4x4 (draft)": "IFC4x4 (borrador)",
    "{count} entities renamed": "{count} entidades renombradas",
    "{count} left out": "{count} omitidas",
    # serializers.py
    "Writing GLB file …": "Escribiendo el archivo GLB …",
    "Writing OBJ file …": "Escribiendo el archivo OBJ …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "Escribiendo el archivo STEP (superficies exactas, tarda minutos en modelos grandes) …",
    "Writing DAE file …": "Escribiendo el archivo DAE …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "No se pudo escribir el archivo {fmt}: el serializador no aceptó ninguno de los {count} elementos.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Estos elementos tienen geometría que no se pudo convertir – p. ej. tipos de geometría no compatibles, "
        "o sus huecos los recortan por completo.",
    "1 element without geometry": "1 elemento sin geometría",
    "{count} elements without geometry": "{count} elementos sin geometría",
    " … and {count} more (all of them in the log file)": " … y {count} más (todos en el archivo de registro)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 elemento omitido porque el núcleo geométrico falló o se bloqueó en él: {names}{more}. "
        "En el programa CAD se puede localizar por su GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} elementos omitidos porque el núcleo geométrico falló o se bloqueó en ellos: {names}{more}. "
        "En el programa CAD se pueden localizar por su GlobalId.",
    "There was not enough memory": "No hubo memoria suficiente",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "El archivo no se pudo leer como IFC (dañado o no es un archivo IFC): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "El archivo no se pudo leer como IFC (dañado o no es un archivo IFC)",
    "File or network error: {message}": "Error de archivo o de red: {message}",
    "Internal error ({name}): {message}": "Error interno ({name}): {message}",
    "Internal error ({name})": "Error interno ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Adjunte el archivo de registro ({log}) al informar del error.",
    "Details are in the log file ({log}).": "Los detalles están en el archivo de registro ({log}).",
    "up to 1 thread (of {cores} logical cores)": "hasta 1 hilo (de {cores} núcleos lógicos)",
    "up to {threads} threads (of {cores} logical cores)": "hasta {threads} hilos (de {cores} núcleos lógicos)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, más hasta {workers} procesos auxiliares para la geometría Rhino con modelos 3DM grandes",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, prioridad baja – los demás programas tienen preferencia",
    "{threads_text}, normal priority": "{threads_text}, prioridad normal",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 elemento interior omitido",
    "{count} interior elements left out": "{count} elementos interiores omitidos",
    # app.py
    "not available": "no disponible",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<usuario>",
    "<computer>": "<equipo>",
    "<server>": "<servidor>",
    "<share>": "<recurso compartido>",
    "<folder>": "<carpeta>",
    "File": "Archivo",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Preciso (recomendado)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Cada elemento completo e igual en cada ejecución; solo las mallas triangulares grandes (terreno) van al "
        "núcleo rápido, que las incluye sin cambios.",
    "Fast": "Rápido",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "De 3 a 13 veces más rápido, pero puede omitir o duplicar caras de algunos elementos.",
    "OpenCASCADE only": "Solo OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Todo con OpenCASCADE, también los modelos de terreno: ahí muy lento (más de 20 minutos para un terreno "
        "grande).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Sustituye los nombres de usuario y de equipo, los servidores y recursos compartidos de las unidades de "
        "red, los nombres de carpetas (<carpeta>) y de archivos (Archivo-1.ifc, Archivo-1.3dm …) y omite los "
        "nombres de elementos. Se conservan la clase IFC y el GlobalId, tiempos, tamaños, versiones y mensajes "
        "de error.",
    "There is no log file yet in {folder}.": "Todavía no hay ningún archivo de registro en {folder}.",
    "Text files (*.txt);;All files (*)": "Archivos de texto (*.txt);;Todos los archivos (*)",
    # dialogs.py: settings
    "Settings": "Configuración",
    "Performance": "Rendimiento",
    "Geometry kernel": "Núcleo geométrico",
    "Output": "Salida",
    "Log file": "Archivo de registro",
    "OK": "Aceptar",
    "Apply and save the settings": "Aplicar y guardar la configuración",
    "Cancel": "Cancelar",
    "Discard changes": "Descartar los cambios",
    "Defaults": "Predeterminados",
    "Reset all settings to their defaults": "Restablecer toda la configuración a los valores predeterminados",
    "At most this many threads:": "Como máximo este número de hilos:",
    "Automatic ({threads})": "Automático ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 o “Automático” deja algunos núcleos libres y usa menos cuando hay poca RAM libre.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Tantos núcleos del procesador calculan la geometría a la vez. Menos hilos frenan menos a los demás "
        "programas, pero la conversión tarda más. "
        "“Automático” usa hasta {threads} de los {cores} núcleos lógicos de este PC (aproximadamente la mitad, "
        "contando los procesos auxiliares de la salida Rhino) y menos cuando hay poca RAM libre; cada hilo "
        "puede necesitar hasta aproximadamente 1 GB con elementos grandes.",
    "Convert at low priority (recommended)": "Convertir con prioridad baja (recomendado)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "La conversión se ejecuta con la prioridad de Windows “Por debajo de lo normal”: Rhino, Revit y "
        "similares tienen preferencia y siguen respondiendo; la conversión solo usa el tiempo de cálculo que "
        "dejan libre. Sin esta opción compite con ellos en igualdad de condiciones.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Con qué se calcula la geometría de los elementos. Se aplica a todos los formatos de salida.",
    "Open the output folder after the conversion": "Abrir la carpeta de salida tras la conversión",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Abre la carpeta en el Explorador en cuanto se han convertido todos los archivos.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Los archivos existentes nunca se sobrescriben – si el nombre ya existe, se añade (2), (3) … "
        "Los propios archivos IFC nunca se modifican.",
    "Identical elements as blocks (smaller file)": "Elementos idénticos como bloques (archivo más pequeño)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Los elementos con la misma geometría de tipo (ventanas, puertas, muebles …) se convierten en instancias "
        "de un bloque de Rhino.\n"
        "El archivo es más pequeño, pero las instancias de bloque se comportan de forma distinta a los objetos "
        "normales:\n"
        "Para editar la geometría, primero hay que descomponer la instancia (_Explode).\n"
        "Los textos de usuario, la capa y el color están en la instancia.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "La geometría de tipo compartida por varios elementos (ventanas, puertas, muebles …) se guarda una vez "
        "como bloque y se inserta como instancia por elemento: archivo un 20–45\u202f% más pequeño. Para editarla en "
        "Rhino, primero hay que descomponer la instancia de bloque (_Explode).",
    "Log file:": "Archivo de registro:",
    "Settings:": "Configuración:",
    "With this, a conversion uses {resources}.": "Con esto, una conversión usa {resources}.",
    # dialogs.py: about
    "About {app}": "Acerca de {app}",
    "Version {version}": "Versión {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Convierte modelos de edificios IFC en archivos Rhino (3DM), GLB y OBJ. Funciona completamente en "
        "local: sin conexión a Internet, sin telemetría, sin actualizaciones automáticas.",
    "Components": "Componentes",
    "Component": "Componente",
    "Version": "Versión",
    "Licence": "Licencia",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Las bibliotecas se incluyen sin cambios. Los textos completos de las licencias están en la carpeta del "
        "programa, en THIRD-PARTY-NOTICES.txt y en la carpeta “licenses”.",
    "Source code:": "Código fuente:",
    "Copy version info": "Copiar info de versión",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Copia las versiones del programa y de los componentes como texto, p. ej. para informar de un error.",
    "Close": "Cerrar",
    "Copied ✓": "Copiado ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Error inesperado",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Se ha producido un error inesperado.</b><br>"
        "El programa sigue funcionando. Si algo deja de funcionar, reinícielo.<br>"
        "Para informar del problema, copie los detalles y adjúntelos.",
    "Copy details": "Copiar detalles",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Omitidos (fallo del núcleo geométrico)",
    "Without geometry": "Sin geometría",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Cómo localizar un elemento en el programa CAD: copie el GlobalId y búsquelo – en ArchiCAD con "
        "“Buscar y seleccionar” (Ctrl+F) por la propiedad IFC GlobalId o “Archicad IFC ID”, en Revit por el "
        "parámetro “IfcGUID” (p. ej. en una tabla de planificación o con un filtro), o bien en cualquier visor "
        "IFC.",
    "Reason": "Motivo",
    "Class": "Clase",
    "GlobalId": "GlobalId",
    "Name": "Nombre",
    "Skipped elements – {file}": "Elementos omitidos – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} omitidos porque el núcleo geométrico falló o se bloqueó en ellos",
    "{count} without geometry (not convertible)": "{count} sin geometría (no convertibles)",
    "{inside} (building hull only)": "{inside} (solo envolvente del edificio)",
    "Copy": "Copiar",
    "{count} more elements without geometry could not be named individually.":
        "{count} elementos más sin geometría no se pudieron nombrar individualmente.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Los elementos interiores omitidos por “Solo envolvente del edificio” no se enumeran individualmente; "
        "sin la opción también se convierten.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Seleccionar y Ctrl+C copia las filas elegidas (Ctrl+A: todas), como tabla para pegar en Excel o en un "
        "correo.",
    "Copy all": "Copiar todo",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Copia toda la tabla, para pegar en Excel o en un correo.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Archivo Rhino (.3dm) – para abrir y seguir trabajando directamente en Rhino.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binario (.glb) – compacto, para visores web, Blender, Three.js y motores de juegos.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – se abre en casi cualquier programa 3D.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – mallas triangulares con colores, para SketchUp, Blender, Unity y ArchiCAD. Archivo de texto, aproximadamente el doble de tamaño que .glb.",
    "Polysurfaces (recommended)": "Polisuperficies (recomendado)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Muros, forjados, ventanas … como polisuperficies cerradas con huecos reales. Los objetos muy detallados (muebles, sanitarios, luminarias) se quedan como mallas. El archivo es 1,2–4,5× más grande según el modelo – para modelos muy grandes, mejor elegir “Mallas”.",
    "Meshes": "Mallas",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "Archivos más pequeños, conversión más rápida. Superficies curvas con sombreado suave, aristas nítidas.",
    "Only the building hull": "Solo la envolvente del edificio",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Convierte solo la envolvente del edificio, es decir, lo que se ve desde fuera: muros exteriores, cubiertas, ventanas, puertas, balcones, terreno … Se omiten los muros interiores, muebles, equipamiento, tuberías y conductos; el archivo se hace mucho más pequeño (p. ej. para modelos de entorno o PC menos potentes).\n\nPara ello, una breve pasada adicional calcula primero una geometría aproximada de todos los elementos (el primer 25\u202f% del progreso). Los elementos marcados como exteriores en el IFC (IsExternal) se conservan siempre; en caso de duda, un elemento se conserva antes que omitirse. Las dimensiones y posiciones de los elementos convertidos no cambian. Se aplica a todos los formatos de salida.",
    "Reading IFC …": "Leyendo IFC …",
    "Converting … {percent}% – {detail}": "Convirtiendo … {percent}\u202f% – {detail}",
    "Converting … {percent}%": "Convirtiendo … {percent}\u202f%",
    "{count} without geometry": "{count} sin geometría",
    "Done – {elements}": "Terminado – {elements}",
    "Error: {error}": "Error: {error}",
    "Cancelled": "Cancelado",
    "Queued – starts afterwards": "En cola – empieza después",
    "Waiting": "En espera",
    "1 file": "1 archivo",
    "{count} files": "{count} archivos",
    "1 element": "1 elemento",
    "{count} elements": "{count} elementos",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Clic para abrir el diálogo de archivos (Ctrl+O). En las carpetas se buscan archivos .ifc.",
    "Drop IFC files or folders here": "Arrastre aquí archivos o carpetas IFC",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "En las carpetas se buscan archivos .ifc e .ifczip – también varias a la vez",
    "Add files…": "Añadir archivos…",
    "Size": "Tamaño",
    "Status": "Estado",
    "Convert IFC building models to 3D formats": "Convertir modelos de edificios IFC a formatos 3D",
    "Double-click a finished file to open its output folder; right-click for more.": "Doble clic en un archivo terminado abre su carpeta de salida; clic derecho para más opciones.",
    "Remove": "Quitar",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Quita los archivos seleccionados de la lista (Supr). Los propios archivos no se tocan.",
    "Clear list": "Vaciar lista",
    "Take all files off the list.": "Quita todos los archivos de la lista.",
    "Skipped elements…": "Elementos omitidos…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Enumera los elementos del archivo seleccionado que no se convirtieron, con clase, GlobalId y nombre (también con clic derecho en la fila).",
    "Drag to divide the room between list and preview": "Arrastrar: repartir el espacio entre lista y vista previa",
    "Output format": "Formato de salida",
    "Output folder": "Carpeta de salida",
    "Change…": "Cambiar…",
    "Save next to the IFC file": "Guardar junto al archivo IFC",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Los archivos existentes nunca se sobrescriben: si el nombre ya existe, se añade (2), (3) …",
    "Choose the output folder.": "Elegir la carpeta de salida.",
    "Each file goes into the folder of its IFC file.": "Cada archivo va a la carpeta de su archivo IFC.",
    "Ready": "Listo",
    "Progress over all files in the list": "Progreso de todos los archivos de la lista",
    "Log – here you can see what happened to each file.": "Registro – aquí se ve qué ha pasado con cada archivo.",
    "Drag to enlarge or shrink the log": "Arrastrar: ampliar o reducir el registro",
    "Log": "Registro",
    "Show or hide the log (F4)": "Mostrar u ocultar el registro (F4)",
    "Open output folder": "Abrir la carpeta de salida",
    "Opens the folder of the file written last.": "Abre la carpeta del último archivo escrito.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Cancela la conversión en curso. Los archivos terminados se conservan; el que está en curso se elimina.",
    "Convert": "Convertir",
    "Convert all files in the list (Ctrl+Enter)": "Convertir todos los archivos de la lista (Ctrl+Intro)",
    "Add folder…": "Añadir carpeta…",
    "Quit": "Salir",
    "Settings…": "Configuración…",
    "Preview": "Vista previa",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "Elegir archivos IFC (Ctrl+O). Carpetas: Archivo → Añadir carpeta…",
    "&File": "&Archivo",
    "&Edit": "&Edición",
    "&View": "&Ver",
    "&Tools": "&Herramientas",
    "&Help": "Ay&uda",
    "Language": "Idioma",
    "The user interface switches to {language} when the program is restarted. Restart now?": "La interfaz cambiará a {language} al reiniciar el programa. ¿Reiniciar ahora?",
    "Restart now": "Reiniciar ahora",
    "Later": "Más tarde",
    "Geometry": "Geometría",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Carpeta de salida: {path}\n\nLos archivos existentes nunca se sobrescriben: se añade (2), (3) …",
    "Choose output folder": "Elegir la carpeta de salida",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ No se encontró ningún archivo IFC: {path} – solo archivos .ifc e .ifczip y carpetas que los contengan (ifcXML no se puede leer)",
    "• Already in the list: {names}": "• Ya en la lista: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} en cola: conversión justo después del lote en curso, con la misma configuración.",
    "+ {files} added": "+ Añadido: {files}",
    "Add IFC files": "Añadir archivos IFC",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "Archivos IFC (*.ifc *.IFC *.ifczip *.ifcZIP);;Todos los archivos (*)",
    "Add a folder with IFC files": "Añadir una carpeta con archivos IFC",
    "Written: {path}": "Escrito: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} omitidos (el núcleo geométrico falló o se bloqueó)",
    "Only the building hull: {inside} (interior elements)": "Solo envolvente del edificio: {inside} (elementos interiores)",
    "List to copy: right-click → “Skipped elements…”": "Lista para copiar: clic derecho → “Elementos omitidos…”",
    "The output folder cannot be created:\n{error}": "No se puede crear la carpeta de salida:\n{error}",
    "next to the IFC files": "junto a los archivos IFC",
    "identical elements as blocks": "elementos idénticos como bloques",
    "only the building hull": "solo la envolvente del edificio",
    "output: {target}": "salida: {target}",
    "geometry kernel {kernel}": "núcleo geométrico {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Capacidad de cálculo: {resources}",
    "Conversion running …": "Conversión en curso …",
    "Cancelling …": "Cancelando …",
    "■ Cancel requested": "■ Cancelación solicitada",
    "Reading IFC ({size}) – may take a few minutes …": "Leyendo IFC ({size}) – puede tardar unos minutos …",
    "{file}: new attempt – reading IFC …": "{file}: nuevo intento – leyendo IFC …",
    "Converting {file} …": "Convirtiendo {file} …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Lista para copiar: clic derecho en el archivo → “Elementos omitidos…”",
    "✗ Error in {file}: {error}": "✗ Error en {file}: {error}",
    "{done} of {files} done": "{done} de {files} terminados",
    "{count} with errors": "{count} con errores",
    "cancelled": "cancelado",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 archivo en cola sin convertir – “Convertir” lo inicia.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} archivos en cola sin convertir – “Convertir” los inicia.",
    "▶ Continuing with {files}, added during the conversion": "▶ Continuando con lo añadido durante la conversión: {files}",
    "Cancelled after {duration}": "Cancelado tras {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ terminados: {done}, con errores: {failed} – tras {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} con errores – tras {duration}",
    "Error": "Error",
    "✓ Done after {duration}": "✓ Terminado tras {duration}",
    "✓ Done": "✓ Terminado",
    "{done} of {files} done – %p%": "{done} de {files} terminados –\u202f%p\u202f%",
    "✗ The output folder does not exist (yet): {path}": "✗ La carpeta de salida no existe (todavía): {path}",
    "Add files and click “Convert”.": "Añada archivos y pulse “Convertir”.",
    "The conversion is still running.": "La conversión sigue en curso.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "“{file}” se está convirtiendo; la conversión lleva {since} en marcha ({percent}\u202f%).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Al salir se cancela la conversión y se pierde su progreso. ¿Salir de todos modos?",
    "Select a file in the list – its preview appears here.": "Seleccione un archivo de la lista – su vista previa aparece aquí.",
    "The 3D view is not available on this PC.": "La vista 3D no está disponible en este PC.",
    "Compute preview": "Calcular vista previa",
    "Computes the preview of this file now (low priority, at most 8 threads, 4 while a conversion runs); it is kept for next time.":
        "Calcula la vista previa de este archivo ahora (prioridad baja, como máximo 8 hilos, 4 durante una conversión); se conserva para la próxima vez.",
    "Stop computing the preview": "Detener el cálculo de la vista previa",
    "Reset view": "Restablecer vista",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Vista inicial: todo el modelo desde el suroeste en altura (Inicio; doble clic: todo el modelo)",
    "Preview – {file}": "Vista previa – {file}",
    "Computing preview …": "Calculando la vista previa …",
    "No preview possible: {error}": "Vista previa no posible: {error}",
    "The file is not (or no longer) accessible.": "El archivo no está (o ya no está) accesible.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Mientras hay una conversión en curso no se calcula ninguna vista previa, para no frenarla.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Archivo grande ({size}): la vista previa tarda unos minutos. Se ejecuta con prioridad baja y se guarda para la próxima vez.",
    "Waiting for the running preview to finish …": "Esperando a que termine la vista previa en curso …",
    "Computing preview: reading the IFC file …": "Calculando la vista previa: leyendo el archivo IFC …",
    "Loading preview …": "Cargando la vista previa …",
    "Preview cancelled.": "Vista previa cancelada.",
    "No preview possible: the geometry kernel crashed repeatedly.":
        "No es posible la vista previa: el núcleo geométrico se bloqueó repetidamente.",
    "Preview cancelled – incomplete":
        "Vista previa cancelada – incompleta",
    "Preview incomplete (the geometry kernel crashed repeatedly)":
        "Vista previa incompleta (el núcleo geométrico se bloqueó repetidamente)",
    "Preview incomplete: {error}":
        "Vista previa incompleta: {error}",
    "Preview incomplete so far (the geometry kernel crashed), computing the rest …":
        "Vista previa incompleta por ahora (el núcleo geométrico se bloqueó), calculando el resto …",
    "{count} of {total} elements so far":
        "{count} de {total} elementos por ahora",
    "{count} details left out ({kinds})":
        "{count} detalles omitidos ({kinds})",
    "The preview could not be loaded.": "No se pudo cargar la vista previa.",
    "The file contains no geometry that can be shown.": "El archivo no contiene geometría que se pueda mostrar.",
    "Computing preview … {percent}%": "Calculando la vista previa … {percent}\u202f%",
    "Preview: {status}": "Vista previa: {status}",
    "Try again": "Reintentar",
    "{count} small elements left out": "{count} elementos pequeños omitidos",
    "Renderer: {renderer}": "Renderizador: {renderer}",
    "Click an element to see its class, GlobalId and name": "Haga clic en un elemento para ver su clase, GlobalId y nombre",
    "Iso": "Iso",
    "Isometric view from the south-west (1)": "Vista isométrica desde el suroeste (1)",
    "Top": "Planta",
    "Plan view, north up (2)": "Vista en planta, norte arriba (2)",
    "Front": "Frente",
    "View from the south (3)": "Vista desde el sur (3)",
    "Side": "Lateral",
    "View from the east (4)": "Vista desde el este (4)",
    "Show the whole model (F, double-click)": "Mostrar todo el modelo (F, doble clic)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "El archivo contiene {count} proyectos con unidades distintas; todos se leen con las unidades del primero ({name}). Compruebe las dimensiones.",
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} se lee como {target} (el mismo esquema con otro nombre).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'No hay suficiente espacio libre en la carpeta temporal para una copia de trabajo del archivo ({needed} necesarios, {free} libres).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'El archivo IFC parece estar truncado (sin END-ISO-10303-21 al final): la salida puede estar incompleta.',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "No se puede escribir en la carpeta de salida {folder} ({error})",
    "Show edges (E)": "Mostrar aristas (E)",
    "Parallel projection instead of perspective (P)": "Proyección paralela en lugar de perspectiva (P)",
    # log file (always anonymised, one option: save)
    "Help → Save log file…": "Ayuda → Guardar el archivo de registro…",
    "Save log file": "Guardar el archivo de registro",
    "The log file could not be saved:\n{error}": "No se pudo guardar el archivo de registro:\n{error}",
    "The log file has been saved:\n{path}\n\n{hint}\n\nPlease look through it briefly before sending. Open the folder now?": "El archivo de registro se ha guardado:\n{path}\n\n{hint}\n\nRevíselo brevemente antes de enviarlo. ¿Abrir la carpeta ahora?",
    "Save log…": "Guardar registro…",
    "The log file stays on this PC; nothing is sent automatically. It contains no user, computer, server, folder, file or element names.": "El archivo de registro permanece en este PC; nada se envía automáticamente. No contiene nombres de usuario, equipo, servidor, carpeta, archivo ni elemento.",
    "Log of this session. Everything is also in the log file (Help → Save log file…).": "Registro de esta sesión. Todo está también en el archivo de registro (Ayuda → Guardar el archivo de registro…).",
    "Save log file…": "Guardar el archivo de registro…",
}
