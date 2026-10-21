"""User interface texts: fr (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Point de reprise {name} illisible ({error}), recalculé",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Le point de reprise ne peut pas être enregistré ({error})\u202f; on continue sans",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Format non pris en charge «\u202f{fmt}\u202f»\u202f; formats possibles\u202f: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Type de géométrie non pris en charge «\u202f{geometry}\u202f»\u202f; types possibles\u202f: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Noyau géométrique inconnu «\u202f{kernel}\u202f»\u202f; noyaux possibles\u202f: {kernels}",
    "IFC file not found: {path}": "Fichier IFC introuvable\u202f: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell ne peut pas lire les fichiers ifcXML ({name}). Veuillez exporter le modèle depuis le "
        "logiciel de conception en .ifc (format texte STEP) ou .ifczip.",
    "Reading IFC file ({size}) …": "Lecture du fichier IFC ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "Version IFC non prise en charge ({error}). Prises en charge\u202f: {supported}\u202f; {bridges} sont aussi lus "
        "comme le schéma apparenté le plus proche.",
    "{note} Dimensions and positions stay unchanged.": "{note} Les dimensions et les positions restent inchangées.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Détermination de l'enveloppe du bâtiment (géométrie précalculée grossièrement) …",
    "Computing geometry ({threads} threads) …": "Calcul de la géométrie ({threads} threads) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Aucune géométrie produite\u202f: aucun des {count} éléments avec géométrie n'a pu être converti (types de "
        "géométrie probablement non pris en charge).",
    "The file contains no elements with geometry.": "Le fichier ne contient aucun élément avec géométrie.",
    "Copying to the target folder ({size}) …": "Copie vers le dossier cible ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Copie échouée ({error}) – nouvel essai {attempt} dans {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Copie vers le dossier cible … {copied} sur {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Le fichier terminé n'a pas pu être copié vers {folder} ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Le fichier terminé n'a pas pu être copié vers {folder} ({error}). Il se trouve ici\u202f: {path} – veuillez "
        "le copier à la main.",
    "{count} extrusions with negative depth turned around": "{count} extrusions de profondeur négative retournées",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} éléments repris de l'essai précédent, {count} sont calculés",
    "Geometry contains itself (faulty file), not converted: {label}":
        "La géométrie se contient elle-même (fichier défectueux), non convertie\u202f: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Élément profondément imbriqué ({depth} niveaux) {number} sur {total} calculé séparément\u202f: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Élément {number} sur {total} calculé séparément\u202f: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} éléments calculés seulement au second essai (tolérance plus fine ou autre noyau)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Seconds essais arrêtés après {seconds} s\u202f; les autres éléments sans géométrie n'ont plus été essayés "
        "séparément",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} calculs de géométrie tournent encore après {seconds} s et sont arrêtés en arrière-plan",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} aura probablement besoin d'environ {needed} Go de mémoire, seuls {available} Go sont libres. "
        "Fermez d'autres programmes, sinon cela devient très lent ou la conversion s'interrompt.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grossier {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Enveloppe du bâtiment seule\u202f: le modèle n'a pas d'enveloppe fermée (toit, planchers ou murs manquants, "
        "p. ex. un modèle partiel sans gros œuvre)\u202f: l'air extérieur atteint presque tous les éléments "
        "(grille {voxel} m). À la place, ont été omis\u202f: {marked} éléments marqués comme intérieurs "
        "(IsExternal = Non) et {fittings} meubles, équipements, tuyaux et gaines, revêtements de plafond et de "
        "sol\u202f; {kept} éléments sur {total} sont convertis.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Enveloppe du bâtiment seule\u202f: {kept} éléments sur {total} sont à l'extérieur et sont convertis, "
        "{inside} éléments intérieurs omis (grille {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "\u202f; {count} sans géométrie précalculée repris par sécurité",
    "; {count} marked as exterior (IsExternal) taken over":
        "\u202f; {count} marqués comme extérieurs (IsExternal) repris",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "\u202f; {count} volumes de masse (enveloppes autour du modèle) non comptés comme opaques",
    "{count} more": "{count} de plus",
    " Left out: {classes}.": " Omis\u202f: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Détermination de l'enveloppe du bâtiment (recherche de l'air extérieur) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Enveloppe du bâtiment\u202f: {kept} éléments sur {total} à l'extérieur ({unknown} sans géométrie "
        "précalculée, {flagged} par IsExternal), grille {voxel} m (grossière {coarse} m, {cells} cellules, "
        "bande fine {band} cellules), géométrie précalculée {coarse_seconds} s, enveloppe {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Enveloppe du bâtiment\u202f: grille élargie à {voxel} m ({cells} cellules enregistrées)",
    # preview.py
    "Saving preview ({count} triangles) …": "Enregistrement de l'aperçu ({count} triangles) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Trop de triangles pour l'aperçu (plus de {limit} par élément).",
    "furniture": "mobilier",
    "MEP": "équipements techniques",
    "fasteners": "fixations",
    "reinforcement": "armatures",
    "deeply nested": "imbriqués profondément",
    # process.py
    "stack overflow": "débordement de pile",
    "The memory was not enough (the process was ended by the system)":
        "La mémoire n'a pas suffi (le processus a été arrêté par le système)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Plantage du noyau géométrique rapide – nouvel essai avec OpenCASCADE seul …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Plantage du noyau géométrique ({fatal}), après quoi la conversion est restée bloquée",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "La conversion n'a plus rien calculé depuis {duration} (elle était bloquée)",
    "{count} minutes": "{count} minutes",
    "{count} seconds": "{count} secondes",
    "stack overflow in the geometry kernel": "débordement de pile dans le noyau géométrique",
    "memory access violation": "violation d'accès mémoire",
    "internal program abort": "arrêt interne du programme",
    "Conversion ended without a result": "Conversion terminée sans résultat",
    "Conversion crashed: {name} (code {code})": "Conversion plantée\u202f: {name} (code {code})",
    "Conversion crashed (code {code})": "Conversion plantée (code {code})",
    "Crash in the geometry kernel ({fatal})": "Plantage du noyau géométrique ({fatal})",
    "Hang in the geometry kernel": "Blocage du noyau géométrique",
    "Crash in the geometry kernel": "Plantage du noyau géométrique",
    "New attempt ({attempt}. of at most {max})": "Nouvel essai (n° {attempt} sur {max} au plus)",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} sur les axes (IfcAlignment, IfcGrid). {again} sans les axes …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} sur {label}. {again}, cet élément est ignoré …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} sur un élément. {again}, il est calculé d'abord et séparément …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} sur l'un de {count} éléments. {again}, ils sont calculés d'abord et séparément pour trouver "
        "celui qui est touché …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Conversion\u202f: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}",
    "(next to the IFC file)": "(à côté du fichier IFC)",
    ", normal priority": ", priorité normale",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Connus de conversions précédentes de ce fichier, ignorés (le noyau géométrique y a planté ou s'y est "
        "bloqué) ({count})\u202f:\n  {elements}",
    ", already computed elements are taken over …": ", les éléments déjà calculés sont repris …",
    " (exit code {code})": " (code de sortie {code})",
    "Cancelled after {seconds} s: {path}": "Annulé après {seconds} s\u202f: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Erreur après {seconds} s sur {path}\u202f: {type}\u202f: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Plantage après {seconds} s sur {path}\u202f: {error} (code de sortie {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Bloqué, annulé après {seconds} s\u202f: {path}",
    "Conversion of {path} failed": "La conversion de {path} a échoué",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Terminé après {seconds} s\u202f: {input} -> {output}, {elements} éléments, {missing} sans géométrie, "
        "{skipped} ignorés",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Ignorés parce que le noyau géométrique y a planté ou s'y est bloqué ({count})\u202f:\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Sans géométrie ({count})\u202f:\n  {elements}{more}",
    "\n  … and {count} more": "\n  … et {count} de plus",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Trop peu de place dans le dossier temporaire pour un point de reprise\u202f; après un plantage, tout est "
        "recalculé",
    "size unknown": "taille inconnue",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Limite de mémoire du processus de conversion ({limit} Go) atteinte",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Limite de mémoire du processus de conversion ({limit} Go) atteinte, la conversion est tout de même "
        "allée jusqu'au bout (p. ex. sans processus auxiliaires)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "La mémoire n'a pas suffi\u202f: la conversion peut utiliser au plus {limit} Go ({share}\u202f% de la mémoire), "
        "pour que les autres programmes continuent de fonctionner. Pour ce fichier, le PC a besoin de plus de "
        "mémoire.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Objet de tâche (job) pour la conversion indisponible ({error}), on continue sans limite de mémoire",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Processus de conversion absent de l'objet de tâche ({error}), on continue sans limite de mémoire",
    "Skipped elements could not be saved ({path}): {error}":
        "Les éléments ignorés n'ont pas pu être enregistrés ({path})\u202f: {error}",
    "{message} (after {seconds} s)": "{message} (après {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "En cours depuis {seconds} s, {percent}\u202f%\u202f: {message}",
    "{message}: {size} written …": "{message}\u202f: {size} écrits …",
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Aucune activité de calcul depuis {seconds} s (CPU {cpu} s){fatal}, {percent}\u202f%\u202f: {message}",
    " after {fatal}": " après {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "Le processus de conversion signale une erreur fatale\u202f: {marker}",
    " (last {shown} KB of {size} KB)": " ({shown} derniers Ko sur {size} Ko)",
    "Output of the conversion process{cut}:\n{message}": "Sortie du processus de conversion{cut}\u202f:\n{message}",
    "The conversion process {pid} could not be ended": "Le processus de conversion {pid} n'a pas pu être arrêté",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "La géométrie Rhino a fait planter un processus auxiliaire, reprise comme maillage à la place\u202f: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "La géométrie Rhino a fait planter un processus auxiliaire, élément omis\u202f: {label}",
    "Writing Rhino file ({count} objects) …": "Écriture du fichier Rhino ({count} objets) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) est lu comme IFC2x3, qui a repris ses entités et ses attributs.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 est un brouillon non publié (tunnels) et est lu comme IFC4.3\u202f: IfcTunnel comme IfcFacility, "
        "IfcTunnelPart comme IfcFacilityPart, IfcUndergroundExcavation et IfcArchElement comme "
        "IfcBuildingElementProxy\u202f; les références de jeux de données (IfcDataSetInformation) sont abandonnées.",
    "IFC4x4 (draft)": "IFC4x4 (brouillon)",
    "{count} entities renamed": "{count} entités renommées",
    "{count} left out": "{count} omises",
    # serializers.py
    "Writing GLB file …": "Écriture du fichier GLB …",
    "Writing OBJ file …": "Écriture du fichier OBJ …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "Écriture du fichier STEP (surfaces exactes, prend des minutes pour les grands modèles) …",
    "Writing DAE file …": "Écriture du fichier DAE …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Le fichier {fmt} n'a pas pu être écrit\u202f: le sérialiseur n'a repris aucun des {count} éléments.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Ces éléments ont une géométrie qui n'a pas pu être convertie – p. ex. des types de géométrie non pris "
        "en charge, ou leurs ouvertures les découpent entièrement.",
    "Help → Open log file": "Aide → Ouvrir le fichier journal",
    "1 element without geometry": "1 élément sans géométrie",
    "{count} elements without geometry": "{count} éléments sans géométrie",
    " … and {count} more (all of them in the log file)": " … et {count} de plus (tous dans le fichier journal)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 élément ignoré parce que le noyau géométrique y a planté ou s'y est bloqué\u202f: {names}{more}. "
        "Dans le logiciel CAO, il se retrouve par son GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} éléments ignorés parce que le noyau géométrique y a planté ou s'y est bloqué\u202f: {names}{more}. "
        "Dans le logiciel CAO, ils se retrouvent par leur GlobalId.",
    "There was not enough memory": "La mémoire n'a pas suffi",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Le fichier n'a pas pu être lu comme IFC (endommagé ou pas un fichier IFC)\u202f: {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Le fichier n'a pas pu être lu comme IFC (endommagé ou pas un fichier IFC)",
    "File or network error: {message}": "Erreur de fichier ou de réseau\u202f: {message}",
    "Internal error ({name}): {message}": "Erreur interne ({name})\u202f: {message}",
    "Internal error ({name})": "Erreur interne ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Veuillez joindre le fichier journal ({log}) en signalant l'erreur.",
    "Details are in the log file ({log}).": "Les détails sont dans le fichier journal ({log}).",
    "up to 1 thread (of {cores} logical cores)": "jusqu'à 1 thread (sur {cores} cœurs logiques)",
    "up to {threads} threads (of {cores} logical cores)": "jusqu'à {threads} threads (sur {cores} cœurs logiques)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, plus jusqu'à {workers} processus auxiliaires pour la géométrie Rhino avec les grands "
        "modèles 3DM",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, priorité basse – les autres programmes passent avant",
    "{threads_text}, normal priority": "{threads_text}, priorité normale",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands}\u202f{hundreds}",  # the thousands separator: 117,137 -> 117 137
    "1 interior element left out": "1 élément intérieur omis",
    "{count} interior elements left out": "{count} éléments intérieurs omis",
    # app.py
    "not available": "non disponible",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<utilisateur>",
    "<computer>": "<ordinateur>",
    "<server>": "<serveur>",
    "<share>": "<partage>",
    "<folder>": "<dossier>",
    "File": "Fichier",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Précis (recommandé)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Chaque élément complet et identique à chaque exécution\u202f; seuls les grands maillages triangulaires "
        "(terrain) vont au noyau rapide, qui les reprend tels quels.",
    "Fast": "Rapide",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3 à 13 fois plus rapide, mais peut omettre ou dupliquer des faces de certains éléments.",
    "OpenCASCADE only": "OpenCASCADE seul",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Tout avec OpenCASCADE, modèles de terrain compris\u202f: très lent dans ce cas (plus de 20 minutes pour un "
        "grand terrain).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Remplace les noms d'utilisateur et d'ordinateur, les serveurs et partages des lecteurs réseau, les noms "
        "de dossiers (<dossier>) et de fichiers (Fichier-1.ifc, Fichier-1.3dm …) et omet les noms d'éléments. "
        "La classe IFC et le GlobalId, les durées, tailles, versions et messages d'erreur sont conservés.",
    "There is no log file yet in {folder}.": "Il n'y a pas encore de fichier journal dans {folder}.",
    "Save anonymised log file": "Enregistrer le fichier journal anonymisé",
    "Text files (*.txt);;All files (*)": "Fichiers texte (*.txt);;Tous les fichiers (*)",
    "The anonymised log file could not be saved:\n{error}":
        "Le fichier journal anonymisé n'a pas pu être enregistré\u202f:\n{error}",
    "The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
    "Please look through it briefly before sending. Open the folder now?":
        "Le fichier journal anonymisé a été enregistré\u202f:\n{path}\n\n{hint}\n\n"
        "Veuillez le parcourir brièvement avant de l'envoyer. Ouvrir le dossier maintenant\u202f?",
    # dialogs.py: settings
    "Settings": "Paramètres",
    "Performance": "Performances",
    "Geometry kernel": "Noyau géométrique",
    "Output": "Sortie",
    "Log file": "Fichier journal",
    "OK": "OK",
    "Apply and save the settings": "Appliquer et enregistrer les paramètres",
    "Cancel": "Annuler",
    "Discard changes": "Abandonner les modifications",
    "Defaults": "Par défaut",
    "Reset all settings to their defaults": "Rétablir toutes les valeurs par défaut",
    "At most this many threads:": "Au plus ce nombre de threads\u202f:",
    "Automatic ({threads})": "Automatique ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 ou «\u202fAutomatique\u202f» laisse quelques cœurs libres et en prend moins quand peu de RAM est libre.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Autant de cœurs de processeur calculent la géométrie en même temps. Moins de threads ralentissent "
        "moins les autres programmes, mais la conversion dure plus longtemps. "
        "«\u202fAutomatique\u202f» utilise jusqu'à {threads} des {cores} cœurs logiques de ce PC (environ la moitié, en "
        "comptant les processus auxiliaires de la sortie Rhino) et moins quand peu de RAM est libre\u202f; chaque "
        "thread peut avoir besoin d'environ 1 Go au plus avec de grands éléments.",
    "Convert at low priority (recommended)": "Convertir en priorité basse (recommandé)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "La conversion tourne avec la priorité Windows «\u202fInférieure à la normale\u202f»\u202f: Rhino, Revit et autres "
        "passent avant et restent réactifs\u202f; la conversion n'utilise que le temps de calcul qu'ils laissent. "
        "Sans ce réglage, elle est en concurrence avec eux à égalité.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Ce avec quoi la géométrie des éléments est calculée. S'applique à tous les formats de sortie.",
    "Open the output folder after the conversion": "Ouvrir le dossier de sortie après la conversion",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Ouvre le dossier dans l'Explorateur dès que tous les fichiers sont convertis.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Les fichiers existants ne sont jamais écrasés – si le nom existe déjà, (2), (3) … est ajouté. "
        "Les fichiers IFC eux-mêmes ne sont jamais modifiés.",
    "Identical elements as blocks (smaller file)": "Éléments identiques en blocs (fichier plus petit)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Les éléments ayant la même géométrie de type (fenêtres, portes, meubles …) deviennent des instances "
        "d'un bloc Rhino.\n"
        "Le fichier est plus petit, mais les instances de bloc se comportent autrement que les objets normaux\u202f:\n"
        "Pour modifier la géométrie, il faut d'abord décomposer l'instance (_Explode).\n"
        "Les textes utilisateur, le calque et la couleur sont sur l'instance.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "La géométrie de type partagée par plusieurs éléments (fenêtres, portes, meubles …) est enregistrée une "
        "fois comme bloc et insérée comme instance pour chaque élément\u202f: fichier 20–45\u202f% plus petit. Pour la "
        "modifier dans Rhino, il faut d'abord décomposer l'instance de bloc (_Explode).",
    "Log file:": "Fichier journal\u202f:",
    "Settings:": "Paramètres\u202f:",
    "Open log file": "Ouvrir le fichier journal",
    "Opens the current log file in the default program for text files.":
        "Ouvre le fichier journal actuel dans le programme par défaut pour les fichiers texte.",
    "Save anonymised…": "Enregistrer anonymisé…",
    "Anonymise log file": "Anonymiser le fichier journal",
    "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
    "no user, computer, server, folder, file or element names.":
        "Le fichier journal reste sur ce PC\u202f; rien n'est envoyé automatiquement. Une fois activé, il ne "
        "contient désormais plus aucun nom d'utilisateur, d'ordinateur, de serveur, de dossier, de fichier ni "
        "d'élément.",
    "With this, a conversion uses {resources}.": "Avec cela, une conversion utilise {resources}.",
    # dialogs.py: about
    "About {app}": "À propos de {app}",
    "Version {version}": "Version {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Convertit des modèles de bâtiment IFC en fichiers Rhino (3DM), GLB et OBJ. Fonctionne entièrement en "
        "local\u202f: pas de connexion Internet, pas de télémétrie, pas de mises à jour automatiques.",
    "Components": "Composants",
    "Component": "Composant",
    "Version": "Version",
    "Licence": "Licence",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Les bibliothèques sont incluses sans modification. Les textes complets des licences se trouvent dans "
        "le dossier du programme, dans THIRD-PARTY-NOTICES.txt et dans le dossier «\u202flicenses\u202f».",
    "Source code:": "Code source\u202f:",
    "Copy version info": "Copier les infos de version",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Copie les versions du programme et des composants sous forme de texte, p. ex. pour un rapport d'erreur.",
    "Close": "Fermer",
    "Copied ✓": "Copié ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Erreur inattendue",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Une erreur inattendue s'est produite.</b><br>"
        "Le programme continue de fonctionner. Si quelque chose ne marche plus, veuillez le redémarrer.<br>"
        "Pour signaler le problème, copiez les détails et joignez-les.",
    "Copy details": "Copier les détails",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Ignorés (noyau géométrique planté)",
    "Without geometry": "Sans géométrie",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Pour retrouver un élément dans le logiciel CAO\u202f: copiez le GlobalId et recherchez-le – dans ArchiCAD "
        "avec «\u202fRechercher et sélectionner\u202f» (Ctrl+F) par la propriété IFC GlobalId ou «\u202fArchicad IFC ID\u202f», dans "
        "Revit par le paramètre «\u202fIfcGUID\u202f» (p. ex. dans une nomenclature ou avec un filtre), sinon dans "
        "n'importe quelle visionneuse IFC.",
    "Reason": "Motif",
    "Class": "Classe",
    "GlobalId": "GlobalId",
    "Name": "Nom",
    "Skipped elements – {file}": "Éléments ignorés – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} ignorés parce que le noyau géométrique y a planté ou s'y est bloqué",
    "{count} without geometry (not convertible)": "{count} sans géométrie (non convertibles)",
    "{inside} (building hull only)": "{inside} (enveloppe du bâtiment seule)",
    "Copy": "Copier",
    "{count} more elements without geometry could not be named individually.":
        "{count} autres éléments sans géométrie n'ont pas pu être nommés individuellement.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Les éléments intérieurs omis à cause de «\u202fEnveloppe du bâtiment seule\u202f» ne sont pas listés "
        "individuellement\u202f; sans l'option, ils sont convertis aussi.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Sélectionner puis Ctrl+C copie les lignes choisies (Ctrl+A\u202f: toutes), sous forme de tableau à coller "
        "dans Excel ou un e-mail.",
    "Copy all": "Tout copier",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Copie tout le tableau, à coller dans Excel ou un e-mail.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Fichier Rhino (.3dm) – à ouvrir et retravailler directement dans Rhino.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binaire (.glb) – compact, pour les visionneuses web, Blender, Three.js et les moteurs de jeu.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – s'ouvre dans presque tous les logiciels 3D.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – maillages triangulaires avec couleurs, pour SketchUp, Blender, Unity et ArchiCAD. Fichier texte, environ deux fois la taille du .glb.",
    "Polysurfaces (recommended)": "Polysurfaces (recommandé)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Murs, dalles, fenêtres … en polysurfaces fermées avec de vraies ouvertures. Les objets très détaillés (meubles, sanitaires, luminaires) restent des maillages. Le fichier est 1,2–4,5× plus gros selon le modèle – pour les très grands modèles, choisissez plutôt «\u202fMaillages\u202f».",
    "Meshes": "Maillages",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "Fichiers les plus petits, conversion la plus rapide. Surfaces courbes lissées, arêtes nettes.",
    "Only the building hull": "Enveloppe du bâtiment seule",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Ne convertit que l'enveloppe du bâtiment, c'est-à-dire ce qui se voit de l'extérieur\u202f: murs extérieurs, toits, fenêtres, portes, balcons, terrain … Les murs intérieurs, meubles, équipements, tuyaux et gaines sont omis\u202f; le fichier devient bien plus petit (p. ex. pour des modèles de contexte ou des PC moins puissants).\n\nPour cela, une courte passe supplémentaire calcule d'abord une géométrie grossière de tous les éléments (les premiers 25\u202f% de la progression). Les éléments marqués comme extérieurs dans l'IFC (IsExternal) sont toujours conservés\u202f; dans le doute, un élément est plutôt gardé qu'omis. Les dimensions et positions des éléments convertis ne changent pas. S'applique à chaque format de sortie.",
    "Reading IFC …": "Lecture de l'IFC …",
    "Converting … {percent}% – {detail}": "Conversion … {percent}\u202f% – {detail}",
    "Converting … {percent}%": "Conversion … {percent}\u202f%",
    "{count} without geometry": "{count} sans géométrie",
    "Done – {elements}": "Terminé – {elements}",
    "Error: {error}": "Erreur\u202f: {error}",
    "Cancelled": "Annulé",
    "Queued – starts afterwards": "En file d'attente – démarre ensuite",
    "Waiting": "En attente",
    "1 file": "1 fichier",
    "{count} files": "{count} fichiers",
    "1 element": "1 élément",
    "{count} elements": "{count} éléments",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Cliquer ouvre la boîte de dialogue de fichiers (Ctrl+O). Les dossiers sont parcourus à la recherche de fichiers .ifc.",
    "Drop IFC files or folders here": "Déposez ici des fichiers ou dossiers IFC",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Les dossiers sont parcourus à la recherche de fichiers .ifc et .ifczip – plusieurs à la fois aussi",
    "Add files…": "Ajouter des fichiers…",
    "Size": "Taille",
    "Status": "État",
    "Convert IFC building models to 3D formats": "Convertir des modèles de bâtiment IFC en formats 3D",
    "Double-click a finished file to open its output folder; right-click for more.": "Double-cliquez sur un fichier terminé pour ouvrir son dossier de sortie\u202f; clic droit pour plus d'options.",
    "Remove": "Retirer",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Retire les fichiers sélectionnés de la liste (Suppr). Les fichiers eux-mêmes restent intacts.",
    "Clear list": "Vider la liste",
    "Take all files off the list.": "Retire tous les fichiers de la liste.",
    "Skipped elements…": "Éléments ignorés…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Liste les éléments du fichier sélectionné qui n'ont pas été convertis, avec classe, GlobalId et nom (aussi par clic droit sur la ligne).",
    "Drag to divide the room between list and preview": "Glisser\u202f: répartir la place entre liste et aperçu",
    "Output format": "Format de sortie",
    "Output folder": "Dossier de sortie",
    "Change…": "Modifier…",
    "Save next to the IFC file": "Enregistrer à côté du fichier IFC",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Les fichiers existants ne sont jamais écrasés\u202f: si le nom est pris, (2), (3) … est ajouté.",
    "Choose the output folder.": "Choisir le dossier de sortie.",
    "Each file goes into the folder of its IFC file.": "Chaque fichier va dans le dossier de son fichier IFC.",
    "Ready": "Prêt",
    "Progress over all files in the list": "Progression sur tous les fichiers de la liste",
    "Log – here you can see what happened to each file.": "Journal – ce qui est arrivé à chaque fichier.",
    "Log of this session. Everything is also in the log file (Help → Open log file).": "Journal de cette session. Tout est aussi dans le fichier journal (Aide → Ouvrir le fichier journal).",
    "Drag to enlarge or shrink the log": "Glisser\u202f: agrandir ou réduire le journal",
    "Log": "Journal",
    "Show or hide the log (F4)": "Afficher ou masquer le journal (F4)",
    "Open output folder": "Ouvrir le dossier de sortie",
    "Opens the folder of the file written last.": "Ouvre le dossier du dernier fichier écrit.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Annule la conversion en cours. Les fichiers terminés sont conservés, celui en cours est supprimé.",
    "Convert": "Convertir",
    "Convert all files in the list (Ctrl+Enter)": "Convertir tous les fichiers de la liste (Ctrl+Entrée)",
    "Add folder…": "Ajouter un dossier…",
    "Quit": "Quitter",
    "Settings…": "Paramètres…",
    "Save anonymised log file…": "Enregistrer le journal anonymisé…",
    "Preview": "Aperçu",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "Choisir des fichiers IFC (Ctrl+O). Dossiers\u202f: Fichier → Ajouter un dossier…",
    "&File": "&Fichier",
    "&Edit": "&Édition",
    "&View": "&Affichage",
    "&Tools": "&Outils",
    "&Help": "Ai&de",
    "Language": "Langue",
    "The user interface switches to {language} when the program is restarted. Restart now?": "L'interface passe à {language} au redémarrage du programme. Redémarrer maintenant\u202f?",
    "Restart now": "Redémarrer maintenant",
    "Later": "Plus tard",
    "Geometry": "Géométrie",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Dossier de sortie\u202f: {path}\n\nLes fichiers existants ne sont jamais écrasés\u202f: (2), (3) … est ajouté.",
    "Choose output folder": "Choisir le dossier de sortie",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ Aucun fichier IFC trouvé\u202f: {path} – seulement des fichiers .ifc et .ifczip et les dossiers qui en contiennent (ifcXML ne peut pas être lu)",
    "• Already in the list: {names}": "• Déjà dans la liste\u202f: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} en file d'attente\u202f: conversion juste après le lot en cours, avec les mêmes paramètres.",
    "+ {files} added": "+ Ajouté\u202f: {files}",
    "Add IFC files": "Ajouter des fichiers IFC",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "Fichiers IFC (*.ifc *.IFC *.ifczip *.ifcZIP);;Tous les fichiers (*)",
    "Add a folder with IFC files": "Ajouter un dossier de fichiers IFC",
    "Written: {path}": "Écrit\u202f: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} ignorés (noyau géométrique planté ou bloqué)",
    "Only the building hull: {inside} (interior elements)": "Enveloppe du bâtiment seule\u202f: {inside} (éléments intérieurs)",
    "List to copy: right-click → “Skipped elements…”": "Liste à copier\u202f: clic droit → «\u202fÉléments ignorés…\u202f»",
    "The output folder cannot be created:\n{error}": "Le dossier de sortie ne peut pas être créé\u202f:\n{error}",
    "next to the IFC files": "à côté des fichiers IFC",
    "identical elements as blocks": "éléments identiques en blocs",
    "only the building hull": "enveloppe du bâtiment seule",
    "output: {target}": "sortie\u202f: {target}",
    "geometry kernel {kernel}": "noyau géométrique {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Puissance de calcul\u202f: {resources}",
    "Conversion running …": "Conversion en cours …",
    "Cancelling …": "Annulation …",
    "■ Cancel requested": "■ Annulation demandée",
    "Reading IFC ({size}) – may take a few minutes …": "Lecture de l'IFC ({size}) – peut prendre quelques minutes …",
    "{file}: new attempt – reading IFC …": "{file}\u202f: nouvel essai – lecture de l'IFC …",
    "Converting {file} …": "Conversion de {file} …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Liste à copier\u202f: clic droit sur le fichier → «\u202fÉléments ignorés…\u202f»",
    "✗ Error in {file}: {error}": "✗ Erreur dans {file}\u202f: {error}",
    "{done} of {files} done": "{done} sur {files} terminés",
    "{count} with errors": "{count} en erreur",
    "cancelled": "annulé",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 fichier en attente non converti – «\u202fConvertir\u202f» le lance.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} fichiers en attente non convertis – «\u202fConvertir\u202f» les lance.",
    "▶ Continuing with {files}, added during the conversion": "▶ Suite avec ce qui a été ajouté pendant la conversion\u202f: {files}",
    "Cancelled after {duration}": "Annulé après {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ terminés\u202f: {done}, en erreur\u202f: {failed} – après {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} en erreur – après {duration}",
    "Error": "Erreur",
    "✓ Done after {duration}": "✓ Terminé après {duration}",
    "✓ Done": "✓ Terminé",
    "{done} of {files} done – %p%": "{done} sur {files} terminés –\u202f%p\u202f%",
    "✗ The output folder does not exist (yet): {path}": "✗ Le dossier de sortie n'existe pas (encore)\u202f: {path}",
    "Add files and click “Convert”.": "Ajoutez des fichiers, puis «\u202fConvertir\u202f».",
    "The conversion is still running.": "La conversion est encore en cours.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "«\u202f{file}\u202f» est en cours de conversion\u202f; la conversion tourne depuis {since} ({percent}\u202f%).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Quitter annule la conversion et sa progression est perdue. Quitter quand même\u202f?",
    "Select a file in the list – its preview appears here.": "Sélectionnez un fichier dans la liste – son aperçu apparaît ici.",
    "The 3D view is not available on this PC.": "La vue 3D n'est pas disponible sur ce PC.",
    "Compute preview": "Calculer l'aperçu",
    "Computes the preview of this file now (low priority, at most 8 threads, 4 while a conversion runs); it is kept for next time.":
        "Calcule l'aperçu de ce fichier maintenant (priorité basse, au plus 8 threads, 4 pendant une conversion) ; il est conservé pour la prochaine fois.",
    "Stop computing the preview": "Arrêter le calcul de l'aperçu",
    "Reset view": "Réinitialiser la vue",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Vue initiale\u202f: tout le modèle depuis le sud-ouest en hauteur (Début\u202f; double-clic\u202f: tout le modèle)",
    "Preview – {file}": "Aperçu – {file}",
    "Computing preview …": "Calcul de l'aperçu …",
    "No preview possible: {error}": "Aperçu impossible\u202f: {error}",
    "The file is not (or no longer) accessible.": "Le fichier n'est pas (ou plus) accessible.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Aucun aperçu n'est calculé pendant une conversion, pour ne pas la ralentir.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Gros fichier ({size})\u202f: l'aperçu prend quelques minutes. Il tourne en priorité basse et est conservé pour la prochaine fois.",
    "Waiting for the running preview to finish …": "Attente de la fin de l'aperçu en cours …",
    "Computing preview: reading the IFC file …": "Calcul de l'aperçu\u202f: lecture du fichier IFC …",
    "Loading preview …": "Chargement de l'aperçu …",
    "Preview cancelled.": "Aperçu annulé.",
    "No preview possible: the geometry kernel crashed repeatedly.":
        "Aucun aperçu possible : le noyau géométrique a planté à plusieurs reprises.",
    "Preview cancelled – incomplete":
        "Aperçu annulé – incomplet",
    "Preview incomplete (the geometry kernel crashed repeatedly)":
        "Aperçu incomplet (le noyau géométrique a planté à plusieurs reprises)",
    "Preview incomplete: {error}":
        "Aperçu incomplet : {error}",
    "Preview incomplete so far (the geometry kernel crashed), computing the rest …":
        "Aperçu incomplet pour l'instant (le noyau géométrique a planté), le reste est en cours de calcul …",
    "{count} of {total} elements so far":
        "{count} éléments sur {total} pour l'instant",
    "{count} details left out ({kinds})":
        "{count} détails omis ({kinds})",
    "The preview could not be loaded.": "L'aperçu n'a pas pu être chargé.",
    "The file contains no geometry that can be shown.": "Le fichier ne contient aucune géométrie affichable.",
    "Computing preview … {percent}%": "Calcul de l'aperçu … {percent}\u202f%",
    "Preview: {status}": "Aperçu\u202f: {status}",
    "Try again": "Réessayer",
    "{count} small elements left out": "{count} petits éléments omis",
    "Renderer: {renderer}": "Rendu\u202f: {renderer}",
    "Click an element to see its class, GlobalId and name": "Cliquez sur un élément pour voir sa classe, son GlobalId et son nom",
    "Iso": "Iso",
    "Isometric view from the south-west (1)": "Vue isométrique depuis le sud-ouest (1)",
    "Top": "Dessus",
    "Plan view, north up (2)": "Vue en plan, nord en haut (2)",
    "Front": "Face",
    "View from the south (3)": "Vue depuis le sud (3)",
    "Side": "Côté",
    "View from the east (4)": "Vue depuis l'est (4)",
    "Show the whole model (F, double-click)": "Afficher tout le modèle (F, double-clic)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "Le fichier contient {count} projets avec des unités différentes ; tous sont lus avec les unités du premier ({name}). Veuillez vérifier les dimensions.",
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} est lu comme {target} (le même schéma sous un autre nom).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Pas assez d’espace libre dans le dossier temporaire pour une copie de travail du fichier ({needed} nécessaires, {free} libres).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'Le fichier IFC semble tronqué (pas de END-ISO-10303-21 à la fin) : la sortie peut être incomplète.',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "Impossible d'écrire dans le dossier de sortie {folder} ({error})",
    "Show edges (E)": "Afficher les arêtes (E)",
    "Parallel projection instead of perspective (P)": "Projection parallèle au lieu de la perspective (P)",
}
