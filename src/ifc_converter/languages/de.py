"""User interface texts: de (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {
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
