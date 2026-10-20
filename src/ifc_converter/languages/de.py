"""User interface texts: de (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Zwischenstand {name} nicht lesbar ({error}), wird neu berechnet",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Zwischenstand kann nicht gespeichert werden ({error}); ohne weiter",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Nicht unterstütztes Format „{fmt}“, möglich sind: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Nicht unterstützte Geometrieart „{geometry}“, möglich sind: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Unbekannter Geometriekern „{kernel}“, möglich sind: {kernels}",
    "IFC file not found: {path}": "IFC-Datei nicht gefunden: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "ifcXML-Dateien kann IfcOpenShell nicht lesen ({name}). Bitte das Modell im Autorenprogramm als .ifc "
        "(STEP-Textformat) oder .ifczip exportieren.",
    "Reading IFC file ({size}) …": "IFC-Datei wird gelesen ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "IFC-Version wird nicht unterstützt ({error}). Unterstützt werden: {supported}; außerdem werden {bridges} "
        "als nächstverwandtes Schema gelesen.",
    "{note} Dimensions and positions stay unchanged.": "{note} Maße und Lage bleiben unverändert.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Gebäudehülle wird bestimmt (Geometrie grob vorberechnet) …",
    "Computing geometry ({threads} threads) …": "Geometrie wird berechnet ({threads} Threads) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Keine Geometrie erzeugt: keines der {count} Bauteile mit Geometrie ließ sich umwandeln (vermutlich nicht "
        "unterstützte Geometrietypen).",
    "The file contains no elements with geometry.": "Die Datei enthält keine Bauteile mit Geometrie.",
    "Copying to the target folder ({size}) …": "Wird ins Zielverzeichnis kopiert ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Kopieren fehlgeschlagen ({error}) – neuer Versuch {attempt} in {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Wird ins Zielverzeichnis kopiert … {copied} von {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Die fertige Datei konnte nicht nach {folder} kopiert werden ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Die fertige Datei konnte nicht nach {folder} kopiert werden ({error}). Sie liegt hier: {path} – bitte von "
        "Hand kopieren.",
    "{count} extrusions with negative depth turned around": "{count} Extrusionen mit negativer Tiefe umgedreht",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} Bauteile aus dem vorigen Versuch übernommen, {count} werden berechnet",
    "Geometry contains itself (faulty file), not converted: {label}":
        "Geometrie enthält sich selbst (fehlerhafte Datei), nicht umgewandelt: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Tief verschachteltes Bauteil ({depth} Ebenen) {number} von {total} wird einzeln berechnet: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Bauteil {number} von {total} wird einzeln berechnet: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} Bauteile erst im zweiten Versuch berechnet (feinere Toleranz bzw. anderer Kern)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Zweite Versuche nach {seconds} s beendet; weitere Bauteile ohne Geometrie wurden nicht mehr einzeln "
        "versucht",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} Geometrie-Berechnungen laufen nach {seconds} s noch und werden im Hintergrund beendet",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} braucht voraussichtlich ca. {needed} GB Arbeitsspeicher, frei sind nur {available} GB. Andere "
        "Programme schließen, sonst wird es sehr langsam oder die Umwandlung bricht ab.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grob {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Nur Gebäudehülle: Das Modell hat keine geschlossene Hülle (fehlendes Dach, fehlende Decken oder Wände, "
        "z. B. ein Teilmodell ohne Rohbau): die Außenluft erreicht fast alle Bauteile (Raster {voxel} m). "
        "Stattdessen weggelassen: {marked} als innen gekennzeichnete Bauteile (IsExternal = Nein) sowie {fittings} "
        "Möbel, Einrichtungen, Leitungen, Decken- und Bodenbeläge; {kept} von {total} Bauteilen werden umgewandelt.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Nur Gebäudehülle: {kept} von {total} Bauteilen liegen außen und werden umgewandelt, {inside} innen "
        "liegende weggelassen (Raster {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} ohne Vorab-Geometrie sicherheitshalber übernommen",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} als außen gekennzeichnete (IsExternal) übernommen",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} Baumassen (Hüllkörper um das Modell) nicht als undurchsichtig gewertet",
    "{count} more": "{count} weitere",
    " Left out: {classes}.": " Weggelassen: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Gebäudehülle wird bestimmt (Außenluft wird gesucht) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Gebäudehülle: {kept} von {total} Bauteilen außen ({unknown} ohne Vorab-Geometrie, {flagged} per "
        "IsExternal), Raster {voxel} m (grob {coarse} m, {cells} Zellen, feiner Saum {band} Zellen), "
        "Vorab-Geometrie {coarse_seconds} s, Hülle {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Gebäudehülle: Raster auf {voxel} m vergröbert ({cells} Rasterzellen gespeichert)",
    # preview.py
    "Saving preview ({count} triangles) …": "Vorschau wird gespeichert ({count} Dreiecke) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Zu viele Dreiecke für die Vorschau (mehr als {limit} je Bauteil).",
    # process.py
    "stack overflow": "Stapelüberlauf",
    "The memory was not enough (the process was ended by the system)":
        "Der Arbeitsspeicher hat nicht gereicht (Prozess wurde vom System beendet)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Absturz im schnellen Geometriekern – neuer Versuch nur mit OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Absturz im Geometriekern ({fatal}), danach hing die Umwandlung fest",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "Die Umwandlung hat {duration} lang nicht mehr gerechnet (sie hing fest)",
    "{count} minutes": "{count} Minuten",
    "{count} seconds": "{count} Sekunden",
    "stack overflow in the geometry kernel": "Stapelüberlauf im Geometriekern",
    "memory access violation": "Speicherzugriffsfehler",
    "internal program abort": "interner Programmabbruch",
    "Conversion ended without a result": "Umwandlung wurde ohne Ergebnis beendet",
    "Conversion crashed: {name} (code {code})": "Umwandlung abgestürzt: {name} (Code {code})",
    "Conversion crashed (code {code})": "Umwandlung abgestürzt (Code {code})",
    "Crash in the geometry kernel ({fatal})": "Absturz im Geometriekern ({fatal})",
    "Hang in the geometry kernel": "Hänger im Geometriekern",
    "Crash in the geometry kernel": "Absturz im Geometriekern",
    "New attempt ({attempt}. of at most {max})": "Neuer Versuch ({attempt}. von höchstens {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} bei den Achsen (IfcAlignment, IfcGrid). {again} ohne die Achsen …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} bei {label}. {again}, dieses Bauteil wird übersprungen …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} bei einem Bauteil. {again}, es wird zuerst und einzeln berechnet …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} bei einem von {count} Bauteilen. {again}, diese werden zuerst und einzeln berechnet, um das "
        "betroffene zu finden …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Umwandlung: {input} ({size}) -> {output}, Format {fmt}, {threads} Threads{options}{priority}",
    "(next to the IFC file)": "(neben der IFC-Datei)",
    ", normal priority": ", normale Priorität",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Bekannt aus früheren Umwandlungen dieser Datei, wird übersprungen (der Geometriekern stürzte daran ab oder "
        "blieb hängen) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", bereits berechnete Bauteile werden übernommen …",
    " (exit code {code})": " (Exit-Code {code})",
    "Cancelled after {seconds} s: {path}": "Abgebrochen nach {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Fehler nach {seconds} s bei {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Absturz nach {seconds} s bei {path}: {error} (Exit-Code {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Hing fest, abgebrochen nach {seconds} s: {path}",
    "Conversion of {path} failed": "Umwandlung von {path} fehlgeschlagen",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Fertig nach {seconds} s: {input} -> {output}, {elements} Bauteile, {missing} ohne Geometrie, {skipped} "
        "übersprungen",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Ohne Geometrie ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … und {count} weitere",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Zu wenig Platz im Temp-Ordner für einen Zwischenstand; nach einem Absturz wird neu gerechnet",
    "size unknown": "Größe unbekannt",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Speichergrenze des Umwandlungsprozesses ({limit} GB) erreicht",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Speichergrenze des Umwandlungsprozesses ({limit} GB) erreicht, die Umwandlung lief trotzdem zu Ende "
        "(z. B. ohne Hilfsprozesse)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "Der Arbeitsspeicher hat nicht gereicht: Die Umwandlung darf höchstens {limit} GB belegen ({share} % des "
        "Arbeitsspeichers), damit andere Programme weiterlaufen. Für diese Datei braucht der PC mehr "
        "Arbeitsspeicher.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Job-Objekt für die Umwandlung nicht verfügbar ({error}), weiter ohne Speichergrenze",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Umwandlungsprozess nicht im Job-Objekt ({error}), weiter ohne Speichergrenze",
    "Skipped elements could not be saved ({path}): {error}":
        "Übersprungene Bauteile konnten nicht gespeichert werden ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (nach {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "Läuft seit {seconds} s, {percent} %: {message}",
    "{message}: {size} written …": "{message}: {size} geschrieben …",
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Keine Rechenaktivität seit {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
    " after {fatal}": " nach {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "Der Umwandlungsprozess meldet einen schweren Fehler: {marker}",
    " (last {shown} KB of {size} KB)": " (letzte {shown} KB von {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Ausgabe des Umwandlungsprozesses{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Der Umwandlungsprozess {pid} ließ sich nicht beenden",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "Rhino-Geometrie ließ einen Hilfsprozess abstürzen, stattdessen als Netz übernommen: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "Rhino-Geometrie ließ einen Hilfsprozess abstürzen, Bauteil weggelassen: {label}",
    "Writing Rhino file ({count} objects) …": "Rhino-Datei wird geschrieben ({count} Objekte) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) wird als IFC2x3 gelesen, das seine Bauteile und Attribute übernommen hat.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 ist ein unveröffentlichter Entwurf (Tunnel) und wird als IFC4.3 gelesen: IfcTunnel als "
        "IfcFacility, IfcTunnelPart als IfcFacilityPart, IfcUndergroundExcavation und IfcArchElement als "
        "IfcBuildingElementProxy; Datensatz-Verweise (IfcDataSetInformation) entfallen.",
    "IFC4x4 (draft)": "IFC4x4 (Entwurf)",
    "{count} entities renamed": "{count} Entitäten umbenannt",
    "{count} left out": "{count} ausgelassen",
    # serializers.py
    "Writing GLB file …": "GLB-Datei wird geschrieben …",
    "Writing OBJ file …": "OBJ-Datei wird geschrieben …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "STEP-Datei wird geschrieben (exakte Flächen, dauert bei großen Modellen Minuten) …",
    "Writing DAE file …": "DAE-Datei wird geschrieben …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Die {fmt}-Datei konnte nicht geschrieben werden: der Serializer hat keines der {count} Bauteile "
        "übernommen.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Diese Bauteile haben Geometrie, die nicht umgewandelt werden konnte – z. B. nicht unterstützte "
        "Geometrietypen, oder sie werden von ihren Öffnungen vollständig weggeschnitten.",
    "Help → Open log file": "Hilfe → Logdatei öffnen",
    "1 element without geometry": "1 Bauteil ohne Geometrie",
    "{count} elements without geometry": "{count} Bauteile ohne Geometrie",
    " … and {count} more (all of them in the log file)": " … und {count} weitere (alle in der Logdatei)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 Bauteil übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb: {names}{more}. "
        "Im CAD-Programm lassen sie sich über die GlobalId finden.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} Bauteile übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb: {names}{more}. "
        "Im CAD-Programm lassen sie sich über die GlobalId finden.",
    "There was not enough memory": "Der Arbeitsspeicher hat nicht gereicht",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Die Datei ließ sich nicht als IFC lesen (beschädigt oder keine IFC-Datei): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Die Datei ließ sich nicht als IFC lesen (beschädigt oder keine IFC-Datei)",
    "File or network error: {message}": "Datei- oder Netzwerkfehler: {message}",
    "Internal error ({name}): {message}": "Interner Fehler ({name}): {message}",
    "Internal error ({name})": "Interner Fehler ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Bitte die Logdatei ({log}) mitschicken, wenn Sie den Fehler melden.",
    "Details are in the log file ({log}).": "Details in der Logdatei ({log}).",
    "up to 1 thread (of {cores} logical cores)": "bis zu 1 Thread (von {cores} logischen Kernen)",
    "up to {threads} threads (of {cores} logical cores)": "bis zu {threads} Threads (von {cores} logischen Kernen)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, bei großen 3DM-Modellen dazu bis zu {workers} Hilfsprozesse für die Rhino-Geometrie",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, niedrige Priorität – andere Programme haben Vorrang",
    "{threads_text}, normal priority": "{threads_text}, normale Priorität",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 innen liegendes weggelassen",
    "{count} interior elements left out": "{count} innen liegende weggelassen",
    # app.py
    "not available": "nicht verfügbar",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<Benutzer>",
    "<computer>": "<Rechner>",
    "<server>": "<Server>",
    "<share>": "<Freigabe>",
    "<folder>": "<Ordner>",
    "File": "Datei",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Genau (empfohlen)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Jedes Bauteil vollständig und bei jedem Lauf gleich; nur große Dreiecksnetze (Gelände) nimmt der "
        "schnelle Kern, der sie unverändert übernimmt.",
    "Fast": "Schnell",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3- bis 13-mal schneller, kann aber bei einzelnen Bauteilen Flächen weglassen oder doppelt erzeugen.",
    "OpenCASCADE only": "Nur OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Alles mit OpenCASCADE, auch Geländemodelle: dort sehr langsam (über 20 Minuten für ein großes Gelände).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Ersetzt Benutzer- und Rechnernamen, Server und Freigaben von Netzlaufwerken, Ordnernamen "
        "(<Ordner>) und Dateinamen (Datei-1.ifc, Datei-1.3dm …) und lässt Bauteilnamen weg. Erhalten bleiben "
        "IFC-Klasse und GlobalId, Zeiten, Größen, Versionen und Fehlermeldungen.",
    "There is no log file yet in {folder}.": "Es gibt noch keine Logdatei in {folder}.",
    "Save anonymised log file": "Anonymisierte Logdatei speichern",
    "Text files (*.txt);;All files (*)": "Textdateien (*.txt);;Alle Dateien (*)",
    "The anonymised log file could not be saved:\n{error}":
        "Die anonymisierte Logdatei konnte nicht gespeichert werden:\n{error}",
    "The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
    "Please look through it briefly before sending. Open the folder now?":
        "Die anonymisierte Logdatei wurde gespeichert:\n{path}\n\n{hint}\n\n"
        "Bitte vor dem Versenden kurz durchsehen. Ordner jetzt öffnen?",
    # dialogs.py: settings
    "Settings": "Einstellungen",
    "Performance": "Leistung",
    "Geometry kernel": "Geometriekern",
    "Output": "Ausgabe",
    "Log file": "Logdatei",
    "OK": "OK",
    "Apply and save the settings": "Einstellungen übernehmen und speichern",
    "Cancel": "Abbrechen",
    "Discard changes": "Änderungen verwerfen",
    "Defaults": "Standardwerte",
    "Reset all settings to their defaults": "Alle Einstellungen auf die Vorgaben zurücksetzen",
    "At most this many threads:": "Höchstens so viele Threads:",
    "Automatic ({threads})": "Automatisch ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 bzw. „Automatisch“ lässt einige Kerne frei und nimmt bei wenig freiem RAM weniger.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "So viele Prozessorkerne berechnen die Geometrie gleichzeitig. Weniger Threads bremsen andere "
        "Programme weniger, die Konvertierung dauert dafür länger. "
        "„Automatisch“ nutzt bis zu {threads} der {cores} logischen Kerne dieses PCs (mit den "
        "Hilfsprozessen der Rhino-Ausgabe etwa die Hälfte) und bei wenig freiem RAM weniger; jeder Thread "
        "kann bei großen Bauteilen bis ca. 1 GB brauchen.",
    "Convert at low priority (recommended)": "Mit niedriger Priorität konvertieren (empfohlen)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "Die Konvertierung läuft mit der Windows-Priorität „Niedriger als normal“: Rhino, Revit & Co. haben "
        "Vorrang und bleiben flüssig bedienbar; die Konvertierung nutzt nur die Rechenzeit, die sie übrig "
        "lassen. Ohne diese Einstellung konkurriert sie gleichberechtigt mit ihnen.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Womit die Geometrie der Bauteile berechnet wird. Gilt für alle Zielformate.",
    "Open the output folder after the conversion": "Ausgabeordner nach der Konvertierung öffnen",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Öffnet den Ordner im Explorer, sobald alle Dateien konvertiert sind.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Vorhandene Dateien werden nie überschrieben – gibt es den Namen schon, wird (2), (3) … "
        "angehängt. Die IFC-Dateien selbst werden nie verändert.",
    "Identical elements as blocks (smaller file)": "Gleiche Bauteile als Blöcke (kleinere Datei)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Bauteile mit derselben Typ-Geometrie (Fenster, Türen, Möbel …) werden Instanzen eines Rhino-Blocks.\n"
        "Die Datei wird kleiner, aber Blockinstanzen verhalten sich anders als normale Objekte:\n"
        "Zum Bearbeiten der Geometrie muss eine Instanz erst aufgelöst werden (_Explode).\n"
        "Benutzertexte, Layer und Farbe stehen an der Instanz.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "Typ-Geometrie, die mehrere Bauteile teilen (Fenster, Türen, Möbel …), wird einmal als Block gespeichert "
        "und je Bauteil als Instanz eingefügt: Datei 20–45 % kleiner. Zum Bearbeiten in Rhino muss eine "
        "Blockinstanz erst aufgelöst werden (_Explode).",
    "Log file:": "Logdatei:",
    "Settings:": "Einstellungen:",
    "Open log file": "Logdatei öffnen",
    "Opens the current log file in the default program for text files.":
        "Öffnet die aktuelle Logdatei im Standardprogramm für Textdateien.",
    "Save anonymised…": "Anonymisiert speichern…",
    "Anonymise log file": "Logdatei anonymisieren",
    "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
    "no user, computer, server, folder, file or element names.":
        "Die Logdatei bleibt auf diesem PC; nichts wird automatisch versendet. Eingeschaltet, enthält sie "
        "ab jetzt keine Benutzer-, Rechner-, Server-, Ordner-, Datei- und Bauteilnamen mehr.",
    "With this, a conversion uses {resources}.": "Eine Konvertierung nutzt damit {resources}.",
    # dialogs.py: about
    "About {app}": "Über {app}",
    "Version {version}": "Version {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Konvertiert IFC-Gebäudemodelle in Rhino-Dateien (3DM), GLB und OBJ. Läuft vollständig lokal: "
        "keine Internetverbindung, keine Telemetrie, keine automatischen Updates.",
    "Components": "Komponenten",
    "Component": "Komponente",
    "Version": "Version",
    "Licence": "Lizenz",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Die Bibliotheken sind unverändert enthalten. Die vollständigen Lizenztexte stehen im "
        "Programmordner in THIRD-PARTY-NOTICES.txt und im Ordner „licenses“.",
    "Source code:": "Quellcode:",
    "Copy version info": "Versionsinfo kopieren",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Kopiert Programm- und Komponentenversionen als Text, z. B. für eine Fehlermeldung.",
    "Close": "Schließen",
    "Copied ✓": "Kopiert ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Unerwarteter Fehler",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Es ist ein unerwarteter Fehler aufgetreten.</b><br>"
        "Das Programm läuft weiter. Falls etwas nicht mehr funktioniert, bitte neu starten.<br>"
        "Zum Melden des Problems die Details kopieren und mitschicken.",
    "Copy details": "Details kopieren",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Übersprungen (Geometriekern abgestürzt)",
    "Without geometry": "Ohne Geometrie",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "So finden Sie ein Bauteil im CAD-Programm: GlobalId kopieren und danach suchen – in ArchiCAD mit "
        "„Suchen & Auswählen“ (Strg+F) über die IFC-Eigenschaft GlobalId bzw. „Archicad IFC ID“, in Revit über "
        "den Parameter „IfcGUID“ (z. B. in einer Bauteilliste oder mit einem Filter), sonst in jedem IFC-Viewer.",
    "Reason": "Grund",
    "Class": "Klasse",
    "GlobalId": "GlobalId",
    "Name": "Name",
    "Skipped elements – {file}": "Übersprungene Bauteile – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb",
    "{count} without geometry (not convertible)": "{count} ohne Geometrie (nicht konvertierbar)",
    "{inside} (building hull only)": "{inside} (nur Gebäudehülle)",
    "Copy": "Kopieren",
    "{count} more elements without geometry could not be named individually.":
        "{count} weitere Bauteile ohne Geometrie ließen sich nicht einzeln benennen.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Die innen liegenden Bauteile, die wegen „Nur Gebäudehülle“ weggelassen wurden, werden nicht "
        "einzeln aufgeführt; ohne die Option werden sie mit umgewandelt.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Markieren und Strg+C kopiert die gewählten Zeilen (Strg+A: alle), als Tabelle zum Einfügen in Excel "
        "oder eine E-Mail.",
    "Copy all": "Alles kopieren",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Kopiert die ganze Tabelle, zum Einfügen in Excel oder eine E-Mail.",
}
