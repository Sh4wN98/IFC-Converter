"""User interface texts: it (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Stato intermedio {name} non leggibile ({error}), viene ricalcolato",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Impossibile salvare lo stato intermedio ({error}); si prosegue senza",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Formato “{fmt}” non supportato; formati possibili: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Tipo di geometria “{geometry}” non supportato; tipi possibili: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Kernel geometrico “{kernel}” sconosciuto; kernel possibili: {kernels}",
    "IFC file not found: {path}": "File IFC non trovato: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell non può leggere i file ifcXML ({name}). Esportare il modello dal programma di authoring "
        "come .ifc (formato testo STEP) o .ifczip.",
    "Reading IFC file ({size}) …": "Lettura del file IFC ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "Versione IFC non supportata ({error}). Supportate: {supported}; inoltre {bridges} vengono letti come lo "
        "schema più affine.",
    "{note} Dimensions and positions stay unchanged.": "{note} Dimensioni e posizioni restano invariate.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Determinazione dell’involucro (geometria precalcolata in modo grossolano) …",
    "Computing geometry ({threads} threads) …": "Calcolo della geometria ({threads} thread) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Nessuna geometria prodotta: nessuno dei {count} elementi con geometria è stato convertito (probabilmente "
        "tipi di geometria non supportati).",
    "The file contains no elements with geometry.": "Il file non contiene elementi con geometria.",
    "Copying to the target folder ({size}) …": "Copia nella cartella di destinazione ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Copia non riuscita ({error}) – tentativo {attempt} fra {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Copia nella cartella di destinazione … {copied} di {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Il file finito non è stato copiato in {folder} ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Il file finito non è stato copiato in {folder} ({error}). Si trova qui: {path} – copiarlo a mano.",
    "{count} extrusions with negative depth turned around": "{count} estrusioni con profondità negativa invertite",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} elementi ripresi dal tentativo precedente, {count} vengono calcolati",
    "Geometry contains itself (faulty file), not converted: {label}":
        "La geometria contiene se stessa (file difettoso), non convertita: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Elemento molto annidato ({depth} livelli) {number} di {total} calcolato singolarmente: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Elemento {number} di {total} calcolato singolarmente: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} elementi calcolati solo al secondo tentativo (tolleranza più fine o altro kernel)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Secondi tentativi terminati dopo {seconds} s; gli altri elementi senza geometria non sono più stati "
        "provati singolarmente",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} calcoli di geometria sono ancora in corso dopo {seconds} s e vengono terminati in background",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} richiederà probabilmente circa {needed} GB di memoria, ne sono liberi solo {available} GB. Chiudere "
        "altri programmi, altrimenti tutto diventa molto lento o la conversione si interrompe.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grossolano {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Solo involucro: il modello non ha un involucro chiuso (manca il tetto, mancano solai o pareti, ad es. un "
        "modello parziale senza struttura grezza): l’aria esterna raggiunge quasi tutti gli elementi (griglia "
        "{voxel} m). Tralasciati invece: {marked} elementi contrassegnati come interni (IsExternal = No) e "
        "{fittings} arredi, attrezzature, tubazioni e canali, rivestimenti di soffitti e pavimenti; {kept} di "
        "{total} elementi vengono convertiti.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Solo involucro: {kept} di {total} elementi sono all’esterno e vengono convertiti, {inside} interni "
        "tralasciati (griglia {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} senza geometria precalcolata ripresi per sicurezza",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} contrassegnati come esterni (IsExternal) ripresi",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} volumi di massa (involucri attorno al modello) non considerati opachi",
    "{count} more": "altri {count}",
    " Left out: {classes}.": " Tralasciati: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Determinazione dell’involucro (ricerca dell’aria esterna) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Involucro: {kept} di {total} elementi all’esterno ({unknown} senza geometria precalcolata, {flagged} per "
        "IsExternal), griglia {voxel} m (grossolana {coarse} m, {cells} celle, fascia fine {band} celle), geometria "
        "precalcolata {coarse_seconds} s, involucro {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Involucro: griglia ingrossata a {voxel} m ({cells} celle memorizzate)",
    # preview.py
    "Saving preview ({count} triangles) …": "Salvataggio dell’anteprima ({count} triangoli) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Troppi triangoli per l’anteprima (più di {limit} per elemento).",
    # process.py
    "stack overflow": "overflow dello stack",
    "The memory was not enough (the process was ended by the system)":
        "La memoria non è bastata (il processo è stato terminato dal sistema)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Crash nel kernel geometrico veloce – nuovo tentativo solo con OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Crash nel kernel geometrico ({fatal}), dopo il quale la conversione è rimasta bloccata",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "La conversione non ha calcolato nulla per {duration} (era bloccata)",
    "{count} minutes": "{count} minuti",
    "{count} seconds": "{count} secondi",
    "stack overflow in the geometry kernel": "overflow dello stack nel kernel geometrico",
    "memory access violation": "violazione di accesso alla memoria",
    "internal program abort": "interruzione interna del programma",
    "Conversion ended without a result": "Conversione terminata senza risultato",
    "Conversion crashed: {name} (code {code})": "Conversione in crash: {name} (codice {code})",
    "Conversion crashed (code {code})": "Conversione in crash (codice {code})",
    "Crash in the geometry kernel ({fatal})": "Crash nel kernel geometrico ({fatal})",
    "Hang in the geometry kernel": "Blocco nel kernel geometrico",
    "Crash in the geometry kernel": "Crash nel kernel geometrico",
    "New attempt ({attempt}. of at most {max})": "Nuovo tentativo ({attempt}° di al massimo {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} sugli assi (IfcAlignment, IfcGrid). {again} senza gli assi …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} su {label}. {again}, questo elemento viene saltato …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} su un elemento. {again}, viene calcolato per primo e singolarmente …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} su uno di {count} elementi. {again}, questi vengono calcolati per primi e singolarmente per trovare "
        "quello interessato …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Conversione: {input} ({size}) -> {output}, formato {fmt}, {threads} thread{options}{priority}",
    "(next to the IFC file)": "(accanto al file IFC)",
    ", normal priority": ", priorità normale",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Noti da conversioni precedenti di questo file, saltati (il kernel geometrico vi è andato in crash o si è "
        "bloccato) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", gli elementi già calcolati vengono ripresi …",
    " (exit code {code})": " (codice di uscita {code})",
    "Cancelled after {seconds} s: {path}": "Annullata dopo {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Errore dopo {seconds} s su {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Crash dopo {seconds} s su {path}: {error} (codice di uscita {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Bloccata, annullata dopo {seconds} s: {path}",
    "Conversion of {path} failed": "Conversione di {path} non riuscita",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Terminata dopo {seconds} s: {input} -> {output}, {elements} elementi, {missing} senza geometria, {skipped} "
        "saltati",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Saltati perché il kernel geometrico vi è andato in crash o si è bloccato ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Senza geometria ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … e altri {count}",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Troppo poco spazio nella cartella temporanea per uno stato intermedio; dopo un crash si ricalcola tutto",
    "size unknown": "dimensione sconosciuta",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Limite di memoria del processo di conversione ({limit} GB) raggiunto",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Limite di memoria del processo di conversione ({limit} GB) raggiunto, la conversione è comunque arrivata "
        "alla fine (ad es. senza processi ausiliari)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "La memoria non è bastata: la conversione può usare al massimo {limit} GB ({share} % della memoria), perché "
        "gli altri programmi continuino a funzionare. Per questo file il PC ha bisogno di più memoria.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Oggetto job per la conversione non disponibile ({error}), si prosegue senza limite di memoria",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Processo di conversione non nell’oggetto job ({error}), si prosegue senza limite di memoria",
    "Skipped elements could not be saved ({path}): {error}":
        "Impossibile salvare gli elementi saltati ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (dopo {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "In corso da {seconds} s, {percent} %: {message}",
    "{message}: {size} written …": "{message}: {size} scritti …",
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Nessuna attività di calcolo da {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
    " after {fatal}": " dopo {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "Il processo di conversione segnala un errore fatale: {marker}",
    " (last {shown} KB of {size} KB)": " (ultimi {shown} KB di {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Output del processo di conversione{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Impossibile terminare il processo di conversione {pid}",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "La geometria Rhino ha fatto andare in crash un processo ausiliario, ripresa invece come mesh: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "La geometria Rhino ha fatto andare in crash un processo ausiliario, elemento tralasciato: {label}",
    "Writing Rhino file ({count} objects) …": "Scrittura del file Rhino ({count} oggetti) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) viene letto come IFC2x3, che ne ha ereditato entità e attributi.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 è una bozza non pubblicata (gallerie) e viene letto come IFC4.3: IfcTunnel come IfcFacility, "
        "IfcTunnelPart come IfcFacilityPart, IfcUndergroundExcavation e IfcArchElement come "
        "IfcBuildingElementProxy; i riferimenti a set di dati (IfcDataSetInformation) vengono eliminati.",
    "IFC4x4 (draft)": "IFC4x4 (bozza)",
    "{count} entities renamed": "{count} entità rinominate",
    "{count} left out": "{count} tralasciati",
    # serializers.py
    "Writing GLB file …": "Scrittura del file GLB …",
    "Writing OBJ file …": "Scrittura del file OBJ …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "Scrittura del file STEP (superfici esatte, richiede minuti per modelli grandi) …",
    "Writing DAE file …": "Scrittura del file DAE …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Impossibile scrivere il file {fmt}: il serializzatore non ha accettato nessuno dei {count} elementi.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Questi elementi hanno una geometria che non è stato possibile convertire – ad es. tipi di geometria non "
        "supportati, oppure le loro aperture li ritagliano completamente.",
    "Help → Open log file": "Aiuto → Apri file di log",
    "1 element without geometry": "1 elemento senza geometria",
    "{count} elements without geometry": "{count} elementi senza geometria",
    " … and {count} more (all of them in the log file)": " … e altri {count} (tutti nel file di log)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 elemento saltato perché il kernel geometrico vi è andato in crash o si è bloccato: {names}{more}. "
        "Nel programma CAD si trova tramite il GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} elementi saltati perché il kernel geometrico vi è andato in crash o si è bloccato: {names}{more}. "
        "Nel programma CAD si trovano tramite il GlobalId.",
    "There was not enough memory": "La memoria non è bastata",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Impossibile leggere il file come IFC (danneggiato o non è un file IFC): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Impossibile leggere il file come IFC (danneggiato o non è un file IFC)",
    "File or network error: {message}": "Errore di file o di rete: {message}",
    "Internal error ({name}): {message}": "Errore interno ({name}): {message}",
    "Internal error ({name})": "Errore interno ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Allegare il file di log ({log}) quando si segnala l’errore.",
    "Details are in the log file ({log}).": "I dettagli sono nel file di log ({log}).",
    "up to 1 thread (of {cores} logical cores)": "fino a 1 thread (su {cores} core logici)",
    "up to {threads} threads (of {cores} logical cores)": "fino a {threads} thread (su {cores} core logici)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, più fino a {workers} processi ausiliari per la geometria Rhino con modelli 3DM grandi",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, priorità bassa – gli altri programmi hanno la precedenza",
    "{threads_text}, normal priority": "{threads_text}, priorità normale",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 elemento interno tralasciato",
    "{count} interior elements left out": "{count} elementi interni tralasciati",
    # app.py
    "not available": "non disponibile",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<utente>",
    "<computer>": "<computer>",
    "<server>": "<server>",
    "<share>": "<condivisione>",
    "<folder>": "<cartella>",
    "File": "File",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Preciso (consigliato)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Ogni elemento completo e identico a ogni esecuzione; solo le grandi mesh triangolari (terreno) vanno al "
        "kernel veloce, che le riprende invariate.",
    "Fast": "Veloce",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "Da 3 a 13 volte più veloce, ma può omettere o duplicare facce di alcuni elementi.",
    "OpenCASCADE only": "Solo OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Tutto con OpenCASCADE, anche i modelli del terreno: lì molto lento (oltre 20 minuti per un terreno grande).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Sostituisce nomi di utenti e computer, server e condivisioni delle unità di rete, nomi di cartelle "
        "(<cartella>) e di file (File-1.ifc, File-1.3dm …) e omette i nomi degli elementi. Restano classe IFC e "
        "GlobalId, tempi, dimensioni, versioni e messaggi di errore.",
    "There is no log file yet in {folder}.": "Non c’è ancora nessun file di log in {folder}.",
    "Save anonymised log file": "Salva file di log anonimizzato",
    "Text files (*.txt);;All files (*)": "File di testo (*.txt);;Tutti i file (*)",
    "The anonymised log file could not be saved:\n{error}":
        "Impossibile salvare il file di log anonimizzato:\n{error}",
    "The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
    "Please look through it briefly before sending. Open the folder now?":
        "Il file di log anonimizzato è stato salvato:\n{path}\n\n{hint}\n\n"
        "Dargli un’occhiata prima di inviarlo. Aprire la cartella adesso?",
    # dialogs.py: settings
    "Settings": "Impostazioni",
    "Performance": "Prestazioni",
    "Geometry kernel": "Kernel geometrico",
    "Output": "Output",
    "Log file": "File di log",
    "OK": "OK",
    "Apply and save the settings": "Applica e salva le impostazioni",
    "Cancel": "Annulla",
    "Discard changes": "Scarta le modifiche",
    "Defaults": "Predefiniti",
    "Reset all settings to their defaults": "Riporta tutte le impostazioni ai valori predefiniti",
    "At most this many threads:": "Numero massimo di thread:",
    "Automatic ({threads})": "Automatico ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 o “Automatico” lascia liberi alcuni core e ne usa meno quando c’è poca RAM libera.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Tanti core del processore calcolano la geometria contemporaneamente. Meno thread rallentano meno gli "
        "altri programmi, ma la conversione dura di più. “Automatico” usa fino a {threads} dei {cores} core "
        "logici di questo PC (circa la metà, contando i processi ausiliari dell’output Rhino) e meno quando c’è "
        "poca RAM libera; ogni thread può richiedere fino a circa 1 GB con elementi grandi.",
    "Convert at low priority (recommended)": "Converti a bassa priorità (consigliato)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "La conversione gira con la priorità Windows “Inferiore al normale”: Rhino, Revit e simili hanno la "
        "precedenza e restano reattivi; la conversione usa solo il tempo di calcolo che lasciano libero. Senza "
        "questa impostazione compete con loro alla pari.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Con cosa viene calcolata la geometria degli elementi. Vale per tutti i formati di output.",
    "Open the output folder after the conversion": "Apri la cartella di destinazione dopo la conversione",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Apre la cartella in Esplora file appena tutti i file sono convertiti.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "I file esistenti non vengono mai sovrascritti – se il nome esiste già, viene aggiunto (2), (3) … "
        "I file IFC stessi non vengono mai modificati.",
    "Identical elements as blocks (smaller file)": "Elementi identici come blocchi (file più piccolo)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Gli elementi con la stessa geometria di tipo (finestre, porte, arredi …) diventano istanze di un blocco "
        "Rhino.\n"
        "Il file diventa più piccolo, ma le istanze di blocco si comportano diversamente dagli oggetti normali:\n"
        "per modificare la geometria, un’istanza va prima esplosa (_Explode).\n"
        "Testi utente, livello e colore sono sull’istanza.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "La geometria di tipo condivisa da più elementi (finestre, porte, arredi …) viene salvata una volta come "
        "blocco e inserita come istanza per ogni elemento: file più piccolo del 20–45 %. Per modificarla in "
        "Rhino, un’istanza di blocco va prima esplosa (_Explode).",
    "Log file:": "File di log:",
    "Settings:": "Impostazioni:",
    "Open log file": "Apri file di log",
    "Opens the current log file in the default program for text files.":
        "Apre il file di log corrente nel programma predefinito per i file di testo.",
    "Save anonymised…": "Salva anonimizzato…",
    "Anonymise log file": "Anonimizza il file di log",
    "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
    "no user, computer, server, folder, file or element names.":
        "Il file di log resta su questo PC; nulla viene inviato automaticamente. Se attivo, da ora in poi non "
        "contiene più nomi di utenti, computer, server, cartelle, file ed elementi.",
    "With this, a conversion uses {resources}.": "Con questo, una conversione usa {resources}.",
    # dialogs.py: about
    "About {app}": "Informazioni su {app}",
    "Version {version}": "Versione {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Converte modelli edilizi IFC in file Rhino (3DM), GLB e OBJ. Funziona interamente in locale: nessuna "
        "connessione Internet, nessuna telemetria, nessun aggiornamento automatico.",
    "Components": "Componenti",
    "Component": "Componente",
    "Version": "Versione",
    "Licence": "Licenza",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Le librerie sono incluse senza modifiche. I testi completi delle licenze si trovano nella cartella del "
        "programma in THIRD-PARTY-NOTICES.txt e nella cartella “licenses”.",
    "Source code:": "Codice sorgente:",
    "Copy version info": "Copia info versione",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Copia le versioni del programma e dei componenti come testo, ad es. per una segnalazione di errore.",
    "Close": "Chiudi",
    "Copied ✓": "Copiato ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Errore imprevisto",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Si è verificato un errore imprevisto.</b><br>"
        "Il programma continua a funzionare. Se qualcosa non funziona più, riavviarlo.<br>"
        "Per segnalare il problema, copiare i dettagli e allegarli.",
    "Copy details": "Copia dettagli",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Saltati (kernel geometrico in crash)",
    "Without geometry": "Senza geometria",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Per trovare un elemento nel programma CAD: copiare il GlobalId e cercarlo – in ArchiCAD con "
        "“Trova e seleziona” (Ctrl+F) tramite la proprietà IFC GlobalId o “Archicad IFC ID”, in Revit tramite il "
        "parametro “IfcGUID” (ad es. in un abaco o con un filtro), altrimenti in qualsiasi visualizzatore IFC.",
    "Reason": "Motivo",
    "Class": "Classe",
    "GlobalId": "GlobalId",
    "Name": "Nome",
    "Skipped elements – {file}": "Elementi saltati – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} saltati perché il kernel geometrico vi è andato in crash o si è bloccato",
    "{count} without geometry (not convertible)": "{count} senza geometria (non convertibili)",
    "{inside} (building hull only)": "{inside} (solo involucro)",
    "Copy": "Copia",
    "{count} more elements without geometry could not be named individually.":
        "Altri {count} elementi senza geometria non hanno potuto essere elencati singolarmente.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Gli elementi interni tralasciati per “Solo involucro” non vengono elencati singolarmente; senza "
        "l’opzione vengono convertiti anch’essi.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Selezionare e Ctrl+C copia le righe scelte (Ctrl+A: tutte), come tabella da incollare in Excel o in "
        "un’e-mail.",
    "Copy all": "Copia tutto",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Copia l’intera tabella, da incollare in Excel o in un’e-mail.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "File Rhino (.3dm) – da aprire e continuare a modificare direttamente in Rhino.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binario (.glb) – compatto, per visualizzatori web, Blender, Three.js e motori di gioco.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – si apre in quasi tutti i programmi 3D.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – mesh triangolari con colori, per SketchUp, Blender, Unity e ArchiCAD. File di testo, circa il doppio di .glb.",
    "Polysurfaces (recommended)": "Polisuperfici (consigliato)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Pareti, solai, finestre … come polisuperfici chiuse con aperture reali. Gli oggetti molto dettagliati (arredi, sanitari, lampade) restano mesh. Il file è 1,2–4,5× più grande a seconda del modello – per modelli molto grandi meglio scegliere “Mesh”.",
    "Meshes": "Mesh",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "File più piccoli, conversione più rapida. Superfici curve ombreggiate in modo uniforme, spigoli netti.",
    "Only the building hull": "Solo involucro",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Converte solo l’involucro dell’edificio, cioè ciò che si vede dall’esterno: pareti esterne, tetti, finestre, porte, balconi, terreno … Pareti interne, arredi, attrezzature, tubazioni e canali vengono tralasciati; il file diventa molto più piccolo (ad es. per modelli di contesto o PC meno potenti).\n\nPer questo un breve passaggio aggiuntivo calcola prima una geometria grossolana di tutti gli elementi (il primo 25 % dell’avanzamento). Gli elementi contrassegnati come esterni nell’IFC (IsExternal) vengono sempre mantenuti; nel dubbio un elemento viene piuttosto mantenuto che tralasciato. Dimensioni e posizioni degli elementi convertiti non cambiano. Vale per ogni formato di output.",
    "Reading IFC …": "Lettura IFC …",
    "Converting … {percent}% – {detail}": "Conversione … {percent} % – {detail}",
    "Converting … {percent}%": "Conversione … {percent} %",
    "{count} without geometry": "{count} senza geometria",
    "Done – {elements}": "Fatto – {elements}",
    "Error: {error}": "Errore: {error}",
    "Cancelled": "Annullata",
    "Queued – starts afterwards": "In coda – parte dopo",
    "Waiting": "In attesa",
    "1 file": "1 file",
    "{count} files": "{count} file",
    "1 element": "1 elemento",
    "{count} elements": "{count} elementi",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Clic per aprire la finestra di scelta file (Ctrl+O). Nelle cartelle vengono cercati i file .ifc.",
    "Drop IFC files or folders here": "Trascinare qui file IFC o cartelle",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Nelle cartelle vengono cercati i file .ifc e .ifczip – anche più di una alla volta",
    "Add files…": "Aggiungi file…",
    "Size": "Dimensione",
    "Status": "Stato",
    "Convert IFC building models to 3D formats": "Converti modelli edilizi IFC in formati 3D",
    "Double-click a finished file to open its output folder; right-click for more.": "Doppio clic su un file finito apre la sua cartella di destinazione; clic destro per altro.",
    "Remove": "Rimuovi",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Toglie i file selezionati dall’elenco (Canc). I file stessi restano intatti.",
    "Clear list": "Svuota elenco",
    "Take all files off the list.": "Toglie tutti i file dall’elenco.",
    "Skipped elements…": "Elementi saltati…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Elenca gli elementi del file selezionato che non sono stati convertiti, con classe, GlobalId e nome (anche con clic destro sulla riga).",
    "Drag to divide the room between list and preview": "Trascinare per ripartire lo spazio tra elenco e anteprima",
    "Output format": "Formato di output",
    "Output folder": "Destinazione",
    "Change…": "Cambia…",
    "Save next to the IFC file": "Salva accanto al file IFC",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "I file esistenti non vengono mai sovrascritti: se il nome è già usato, viene aggiunto (2), (3) …",
    "Choose the output folder.": "Scegliere la cartella di destinazione.",
    "Each file goes into the folder of its IFC file.": "Ogni file va nella cartella del suo file IFC.",
    "Ready": "Pronto",
    "Progress over all files in the list": "Avanzamento su tutti i file dell’elenco",
    "Log – here you can see what happened to each file.": "Registro – qui si vede cosa è successo a ogni file.",
    "Log of this session. Everything is also in the log file (Help → Open log file).": "Registro di questa sessione. Tutto è anche nel file di log (Aiuto → Apri file di log).",
    "Drag to enlarge or shrink the log": "Trascinare per ingrandire o ridurre il registro",
    "Log": "Registro",
    "Show or hide the log (F4)": "Mostra o nascondi il registro (F4)",
    "Open output folder": "Apri cartella di destinazione",
    "Opens the folder of the file written last.": "Apre la cartella dell’ultimo file scritto.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Annulla la conversione in corso. I file finiti restano, quello in corso viene eliminato.",
    "Convert": "Converti",
    "Convert all files in the list (Ctrl+Enter)": "Converti tutti i file dell’elenco (Ctrl+Invio)",
    "Add folder…": "Aggiungi cartella…",
    "Quit": "Esci",
    "Settings…": "Impostazioni…",
    "Save anonymised log file…": "Salva file di log anonimizzato…",
    "Preview": "Anteprima",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "Scegliere i file IFC (Ctrl+O). Cartelle: File → Aggiungi cartella…",
    "&File": "&File",
    "&Edit": "&Modifica",
    "&View": "&Visualizza",
    "&Tools": "&Strumenti",
    "&Help": "&Aiuto",
    "Language": "Lingua",
    "The user interface switches to {language} when the program is restarted. Restart now?": "L’interfaccia passa a {language} al prossimo avvio del programma. Riavviare adesso?",
    "Restart now": "Riavvia adesso",
    "Later": "Più tardi",
    "Geometry": "Geometria",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Cartella di destinazione: {path}\n\nI file esistenti non vengono mai sovrascritti: viene aggiunto (2), (3) …",
    "Choose output folder": "Scegli cartella di destinazione",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ Nessun file IFC trovato: {path} – solo file .ifc e .ifczip e cartelle che li contengono (ifcXML non può essere letto)",
    "• Already in the list: {names}": "• Già nell’elenco: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} in coda: conversione subito dopo quella in corso, con le stesse impostazioni.",
    "+ {files} added": "+ {files} aggiunti",
    "Add IFC files": "Aggiungi file IFC",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "File IFC (*.ifc *.IFC *.ifczip *.ifcZIP);;Tutti i file (*)",
    "Add a folder with IFC files": "Aggiungi una cartella con file IFC",
    "Written: {path}": "Scritto: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} saltati (kernel geometrico in crash o bloccato)",
    "Only the building hull: {inside} (interior elements)": "Solo involucro: {inside} (elementi interni)",
    "List to copy: right-click → “Skipped elements…”": "Elenco da copiare: clic destro → “Elementi saltati…”",
    "The output folder cannot be created:\n{error}": "Impossibile creare la cartella di destinazione:\n{error}",
    "next to the IFC files": "accanto ai file IFC",
    "identical elements as blocks": "elementi identici come blocchi",
    "only the building hull": "solo involucro",
    "output: {target}": "destinazione: {target}",
    "geometry kernel {kernel}": "kernel geometrico {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Potenza di calcolo: {resources}",
    "Conversion running …": "Conversione in corso …",
    "Cancelling …": "Annullamento …",
    "■ Cancel requested": "■ Annullamento richiesto",
    "Reading IFC ({size}) – may take a few minutes …": "Lettura IFC ({size}) – può richiedere alcuni minuti …",
    "{file}: new attempt – reading IFC …": "{file}: nuovo tentativo – lettura IFC …",
    "Converting {file} …": "Conversione di {file} …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Elenco da copiare: clic destro sul file → “Elementi saltati…”",
    "✗ Error in {file}: {error}": "✗ Errore in {file}: {error}",
    "{done} of {files} done": "{done} di {files} fatti",
    "{count} with errors": "{count} con errori",
    "cancelled": "annullata",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 file in coda non convertito – “Converti” lo avvia.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} file in coda non convertiti – “Converti” li avvia.",
    "▶ Continuing with {files}, added during the conversion": "▶ Si prosegue con {files}, aggiunti durante la conversione",
    "Cancelled after {duration}": "Annullata dopo {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ {done} fatti, {failed} con errori – dopo {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} con errori – dopo {duration}",
    "Error": "Errore",
    "✓ Done after {duration}": "✓ Fatto dopo {duration}",
    "✓ Done": "✓ Fatto",
    "{done} of {files} done – %p%": "{done} di {files} fatti – %p %",
    "✗ The output folder does not exist (yet): {path}": "✗ La cartella di destinazione non esiste (ancora): {path}",
    "Add files and click “Convert”.": "Aggiungere file e premere “Converti”.",
    "The conversion is still running.": "La conversione è ancora in corso.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "“{file}” è in conversione; la conversione è in corso da {since} ({percent} %).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Uscendo la conversione viene annullata e il suo avanzamento va perso. Uscire comunque?",
    "Select a file in the list – its preview appears here.": "Selezionare un file nell’elenco – la sua anteprima appare qui.",
    "The 3D view is not available on this PC.": "La vista 3D non è disponibile su questo PC.",
    "Compute preview": "Calcola anteprima",
    "Computes the preview of this file now (low priority, at most 4 threads); it is kept for next time.": "Calcola adesso l’anteprima di questo file (bassa priorità, al massimo 4 thread); viene conservata per la prossima volta.",
    "Stop computing the preview": "Interrompi il calcolo dell’anteprima",
    "Reset view": "Ripristina vista",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Vista iniziale: l’intero modello da sud-ovest dall’alto (Home; doppio clic: intero modello)",
    "Preview – {file}": "Anteprima – {file}",
    "Computing preview …": "Calcolo dell’anteprima …",
    "No preview possible: {error}": "Anteprima non possibile: {error}",
    "The file is not (or no longer) accessible.": "Il file non è (più) accessibile.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Durante una conversione non viene calcolata nessuna anteprima, per non rallentarla.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "File grande ({size}): l’anteprima richiede alcuni minuti. Gira a bassa priorità e viene conservata per la prossima volta.",
    "Waiting for the running preview to finish …": "In attesa che l’anteprima in corso finisca …",
    "Computing preview: reading the IFC file …": "Calcolo dell’anteprima: lettura del file IFC …",
    "Loading preview …": "Caricamento dell’anteprima …",
    "Preview cancelled.": "Anteprima annullata.",
    "The preview could not be loaded.": "Impossibile caricare l’anteprima.",
    "The file contains no geometry that can be shown.": "Il file non contiene geometria visualizzabile.",
    "Computing preview … {percent}%": "Calcolo dell’anteprima … {percent} %",
    "Preview: {status}": "Anteprima: {status}",
    "Try again": "Riprova",
    "{count} small elements left out": "{count} elementi piccoli tralasciati",
    "Renderer: {renderer}": "Rendering: {renderer}",
    "Click an element to see its class, GlobalId and name": "Clic su un elemento mostra classe, GlobalId e nome",
    "Iso": "Iso",
    "Isometric view from the south-west (1)": "Vista isometrica da sud-ovest (1)",
    "Top": "Alto",
    "Plan view, north up (2)": "Pianta, nord in alto (2)",
    "Front": "Fronte",
    "View from the south (3)": "Vista da sud (3)",
    "Side": "Lato",
    "View from the east (4)": "Vista da est (4)",
    "All": "Tutto",
    "Show the whole model (F, double-click)": "Mostra l’intero modello (F, doppio clic)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "Il file contiene {count} progetti con unità diverse; tutti vengono letti con le unità del primo ({name}). Verificare le dimensioni.",
    'cancelled':
        'annullato',
    'Reading IFC …':
        'Lettura IFC …',
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} viene letto come {target} (lo stesso schema con un altro nome).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Spazio libero insufficiente nella cartella temporanea per una copia di lavoro del file ({needed} necessari, {free} liberi).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'Il file IFC sembra troncato (nessun END-ISO-10303-21 alla fine): l’output potrebbe essere incompleto.',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "Impossibile scrivere nella cartella di output {folder} ({error})",
}
