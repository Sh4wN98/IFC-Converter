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
}
