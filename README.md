# IFC File Converter

Kleines Programm (mit Fenster oder als Kommandozeilen-Tool), das IFC-Gebäudemodelle in 3D-Formate umwandelt:

| Format | Endung | Gut für |
|---|---|---|
| Rhino | `.3dm` | Rhino, Grasshopper (Layer pro Geschoss und Bauteiltyp, IFC-Daten als Attribute) |
| glTF (binär) | `.glb` | Web-Viewer, Three.js, Blender, Game-Engines |
| Wavefront OBJ | `.obj` + `.mtl` | Blender, fast jedes 3D-Programm |

Die Geometrie wird mit [IfcOpenShell](https://ifcopenshell.org) berechnet und in Metern ausgegeben.
Öffnungskörper (`IfcOpeningElement`) werden nie exportiert. Raumvolumen (`IfcSpace`) landen nur in `.3dm`, dort auf eigenen Layern zum Ausblenden.

## Installation unter Windows

Der Converter wird wie ein normales Windows-Programm installiert, Python ist dafür nicht nötig.

- **Installer:** `IFC-Converter-<Version>-Setup.exe` (aus den [Releases](https://github.com/Sh4wN98/IFC-Converter/releases)) doppelklicken.
  - Keine Administratorrechte nötig: installiert wird nur für den angemeldeten Benutzer nach `%LOCALAPPDATA%\Programs\IFC Converter`, dazu ein Eintrag im Startmenü.
  - Desktop-Symbol und ein „Öffnen mit“-Eintrag für `.ifc`-Dateien sind wählbar, aber standardmäßig aus. Das Standardprogramm für IFC-Dateien wird nie geändert.
  - Keine Dienste, kein Autostart, keine Hintergrund-Updates, keine Internetverbindung im Betrieb.
- **Portable Version:** `IFC-Converter-<Version>-portable.zip` entpacken (z. B. in „Dokumente“) und `IFC Converter.exe` im entpackten Ordner starten. Nichts wird installiert.
- **Windows SmartScreen:** Das Programm ist nicht digital signiert. Beim ersten Start des Installers (bzw. der portablen exe) erscheint deshalb „Der Computer wurde durch Windows geschützt“. Dann auf **„Weitere Informationen“ → „Trotzdem ausführen“** klicken. Blockiert der Virenscanner der Firma das Programm, die IT um eine Ausnahme für den Programmordner bitten.
- **Update:** Den Installer der neuen Version ausführen. Er ersetzt die alte Version; Einstellungen bleiben erhalten. Läuft der Converter noch (Fenster oder `ifc-convert`, z. B. mit einer langen Umwandlung), bittet der Installer, ihn erst zu schließen, und macht sonst nichts – eine laufende Umwandlung wird nie abgebrochen.
- **Deinstallation:** Windows-Einstellungen → Apps → „IFC Converter“ → Deinstallieren (ebenfalls erst, wenn der Converter beendet ist). Einstellungen und Logdateien (`%APPDATA%\IFC Converter`, `%LOCALAPPDATA%\IFC Converter`) bleiben liegen und können bei Bedarf von Hand gelöscht werden; entfernt werden der „Öffnen mit“-Eintrag und die alten Einstellungen in der Registry (`HKCU\Software\IFC File Converter\IFC File Converter`, aus der Zeit vor der Umbenennung). Die portable Version wird einfach gelöscht.
- **Kommandozeile:** Neben `IFC Converter.exe` liegt `ifc-convert.exe` mit denselben Optionen wie unten beschrieben, z. B. `"%LOCALAPPDATA%\Programs\IFC Converter\ifc-convert.exe" haus.ifc -f 3dm`. Ohne Argumente (Doppelklick) startet der Terminal-Modus.

## Schnellstart (Programmfenster)

1. **Installiert:** „IFC Converter“ im Startmenü öffnen. **Aus dem Quellcode:** unter Windows `start.bat` doppelklicken, unter Linux/macOS `./start.sh` ausführen.
2. Aus dem Quellcode richtet sich der Converter beim ersten Start selbst ein (Internet nötig für den Download von IfcOpenShell, rhino3dm und Qt; Python 3.10 oder neuer muss installiert sein). Nach einem Update passiert das automatisch noch einmal.
3. IFC-Dateien oder ganze Ordner ins Fenster ziehen (oder „Dateien hinzufügen…“).
4. Format wählen (Standard: 3DM), Ausgabeordner prüfen und auf „Konvertieren“ klicken.
5. Die fertigen Dateien landen standardmäßig auf dem Desktop. Gibt es den Namen schon, wird `(2)`, `(3)` … angehängt.

- **Während einer Umwandlung** hinzugefügte Dateien (ins Fenster gezogen, über „Dateien hinzufügen…“ oder per „Öffnen mit“/Ziehen aufs Programmsymbol) werden vorgemerkt und gleich danach mit denselben Einstellungen umgewandelt. Nach „Abbrechen“ bleiben sie in der Liste stehen.
- **Rechenleistung:** Zu Beginn steht im Protokoll, wie viele Threads die Umwandlung höchstens nutzt und dass sie mit niedriger Priorität läuft. Unter Extras → Einstellungen → Leistung lässt sich die Zahl der Threads verringern, damit andere rechenintensive Programme mehr Luft haben; „Automatisch“ lässt einige Kerne frei und nimmt bei wenig freiem RAM weniger.
- **Fehler:** Schlägt eine Datei fehl, steht im Protokoll darunter, wo die Details sind (Hilfe → Logdatei öffnen). „Interner Fehler (…)“ bedeutet einen Fehler im Programm selbst: dann bitte die Logdatei mitschicken (siehe „Logdatei und Datenschutz“).

### 3D-Vorschau

Unter der Dateiliste zeigt eine Vorschau die ausgewählte Datei – eine ins Fenster gezogene Datei wird gleich ausgewählt. Ein- und ausblenden: **Ansicht → Vorschau** (F3); die Trennlinie zur Liste lässt sich verschieben.

- Dateien bis 150 MB werden sofort berechnet (wenige Sekunden), größere erst nach Klick auf „Vorschau berechnen“ (das Einlesen allein dauert Minuten). Während einer Umwandlung wird keine Vorschau von selbst berechnet, damit sie nicht gebremst wird.
- Eine berechnete Vorschau wird gemerkt und erscheint beim nächsten Mal sofort, auch nach einem Neustart des Programms (solange die Datei unverändert ist).
- Wechselt man zu einer anderen Datei, wird eine von selbst gestartete Berechnung abgebrochen; eine per Klick gestartete läuft weiter und steht danach bereit.

Die Vorschau zeigt das Modell zum Drehen und Anschauen, zu Beginn schräg von Südwesten oben, ganz im Bild. Z ist oben.

| Aktion | Maus / Taste |
|---|---|
| Drehen | linke Maustaste ziehen (dreht um den angeklickten Punkt, neben dem Modell um die Bildmitte) |
| Verschieben | mittlere oder rechte Maustaste ziehen, oder Umschalt + linke Maustaste |
| Zoomen | Mausrad, zum Mauszeiger hin |
| Ganzes Modell | Doppelklick, Taste `F` oder „Alles“ |
| Ansichten | Knöpfe oben links oder Tasten `1` Iso, `2` Oben (Norden oben), `3` Vorne (von Süden), `4` Seite (von Osten); `Pos1` = Startansicht |
| Bauteil anklicken | Klick (ohne Ziehen) auf ein Bauteil zeigt Klasse, GlobalId und Name |

- Gezeichnet wird mit der Grafikkarte (OpenGL 3.3), auch Modelle mit mehreren Millionen Dreiecken bleiben flüssig. Gezeichnet wird nur, wenn sich etwas ändert: eine ruhende Vorschau kostet keine Rechenzeit.
- Ohne brauchbaren Grafiktreiber (Remotedesktop, virtuelle Maschine) nimmt Qt automatisch das mitgelieferte Software-OpenGL (`opengl32sw.dll`, rechnet auf dem Prozessor). Geht auch das nicht, zeichnet die Vorschau selbst: dann nur die größten Bauteile (je nach Rechnerleistung bis 200 000 Dreiecke), beim Drehen gröber. Meldet die Grafik einen Fehler, wechselt die Vorschau ebenfalls auf die eigene Darstellung, statt das Programm zu beenden; der Grund steht in der Logdatei.
- Macht ein Grafiktreiber Probleme, erzwingt die Umgebungsvariable `IFC_CONVERTER_PREVIEW_RENDERER=software` die eigene Darstellung.

### Vorschau: wie sie berechnet wird

- **Wie eine Umwandlung, nur leichter:** Die Vorschau entsteht im selben eigenen Prozess wie eine Umwandlung, mit niedriger Priorität, unter Windows im Job-Objekt mit Speichergrenze, und endet mit dem Programm. Stürzt der Geometriekern ab oder hängt er, wird wie bei der Umwandlung neu gestartet (siehe „Absturz oder Hänger bei einzelnen Bauteilen“); ein Absturz des schnellen Kerns führt dabei gleich zu einem Versuch nur mit OpenCASCADE, weil er meist viele gleichartige Bauteile trifft (alle Träger einer Brücke).
- **Schnell statt genau:** Kern „Schnell“ (Hybrid), Rundungen gröber facettiert (Sehnen bis 1 cm statt 0,5 mm; auf den Testmodellen nur 1–3 % weniger Dreiecke, weil Revit & Co. ohnehin Dreiecke speichern), höchstens 4 Threads (auf kleinen PCs weniger), damit eine Vorschau neben einer Umwandlung und anderen Programmen Platz hat. Öffnungen werden ausgeschnitten; Räume (`IfcSpace`), Öffnungskörper, Zonen, Annotationen, virtuelle Elemente sowie Achsen und Raster fehlen.
- **Farben** wie in Rhino aus Material/Oberflächenstil der IFC, Glas durchsichtig; Bauteile ohne Farbe grau. Jedes Dreieck kennt sein Bauteil („IfcWall 2O2Fr… „Name““).
- **Höchstens 3 Millionen Dreiecke:** Bei größeren Modellen fallen zuerst die kleinsten Bauteile weg (nach der Größe ihres umschließenden Quaders: Schrauben, Armaturen, Kleinteile); die Vorschau nennt, wie viele. Clinic Plumbing (56 MB, Revit-TGA) erreicht die Grenze.
- **Koordinaten:** In Metern, Lage wie in der IFC; gespeichert relativ zur Modellmitte, sodass auch georeferenzierte Modelle (Hunderte km vom Ursprung) auf unter 1 mm genau bleiben.
- **Zwischenspeicher:** Fertige Vorschauen liegen in `%LOCALAPPDATA%\IFC Converter\previews` (Linux: `~/.local/state/ifc-converter/previews`), nie neben der IFC-Datei. Wird dieselbe, unveränderte Datei wieder gewählt, erscheint die Vorschau sofort. Ändert sich die Datei (Größe oder Änderungszeit), kommt eine neue IfcOpenShell-Version oder ändern sich die Vorschau-Einstellungen, wird neu gerechnet. Der Ordner wird höchstens ca. 2 GB groß; darüber werden die am längsten nicht benutzten Vorschauen gelöscht. Er kann jederzeit von Hand geleert werden.
- **Dauer** (Laptop, 3 Threads, Vorschau gegenüber `.3dm` Netze mit dem Standardkern): duplex (2 MB) 1,2 statt 2,8 s, Clinic Architectural (13 MB) 4,5 statt 15 s, Schependomlaan (49 MB) 6,5 statt 33 s.

### Rhino-Export (.3dm)

- **Geometrie „Polyflächen“ (Standard):**
  - Wände, Decken, Fenster, Türen, Träger usw. werden geschlossene, ebene Polyflächen in Metern.
  - Koplanare Flächen sind zusammengeführt, Fenster- und Türöffnungen sind echte Löcher in den Flächen.
  - Facettiert-Rundes (Rohre, Kanäle, runde Stützen, Bewehrung, Sanitärobjekte), sehr detaillierte Objekte (über 1000 Dreiecke) und Revit-Platzhalter (RPC-Bäume/-Personen) bleiben Netze, ebenso alles, was keine gültige Polyfläche ergibt.
  - Die Datei wird je nach Modell etwa 1,2–4,5× so groß wie mit Netzen (siehe „Große Modelle“).
- **Geometrie „Netze“:** Jedes Bauteil wird ein Mesh-Objekt, die kleinste Datei und die schnellste Umwandlung. Runde Flächen werden glatt schattiert, Kanten bleiben scharf.
- **Gekrümmte Flächen:** Rundes bleibt facettiert, weil Revit & Co. es schon in der IFC als Dreiecke speichern. Echte NURBS-Flächen erzeugt der Converter nicht.
- **Layer** folgen der räumlichen Struktur:
  - Gebäude: `Geschoss::IfcKlasse`, z. B. `EG::IfcWall`. Bei mehreren Gebäuden in einer Datei steht das Gebäude davor.
  - Brücken, Straßen, Bahn (IFC4.3): `Bauwerk::Bauwerksteil::IfcKlasse`, z. B. `Talbrücke::Pfeiler::IfcColumn`.
  - Bauteile außerhalb davon landen unter `Ohne Geschoss`.
- **Achsen:** Trassierungsachsen (`IfcAlignment`) und Achsraster (`IfcGrid`) werden Rhino-Polylinien.
- Objektname = IFC-Name, Farbe aus dem IFC-Material/-Stil.
- **Mehrere Materialien:** Ein Bauteil mit mehreren Materialien (Fenster: Rahmen und Glas, Türen, Möbel) wird ein Objekt je Material, zusammengefasst als Gruppe mit dem Namen des Bauteils. Glas bleibt so durchsichtig. Gezählt wird weiterhin je IFC-Bauteil.
- **Baugruppen:** Die Teile von Baugruppen ohne eigene Geometrie (`IfcElementAssembly`, Vorhangfassaden, Treppen, Dächer aus Einzelteilen …) bilden eine Gruppe mit dem Namen der Baugruppe; ein Klick wählt alle Teile.
- **Benutzertexte (Attribute User Text)** am Objekt: GlobalId (`IfcGlobalId`), IFC-Klasse, Name, Typname (`IfcType`), `IfcPredefinedType` (bei USERDEFINED der vergebene Name), `IfcObjectType`, `IfcTag` (z. B. die Revit-Element-ID), Geschoss (`IfcStorey`), dazu die Property-Sets und die Standard-Mengen (`BaseQuantities` bzw. `Qto_…`: Flächen, Volumen, Längen in m, m², m³).
  - Platzhalterwerte ohne Inhalt („N/A“, „-“, „NOTDEFINED“, „UNSET“, „None“, „<default>“, leer …) und Werte, die nur den Namen ihrer Eigenschaft wiederholen (Revits COBie-Parameter: „SerialNumber“ = „SerialNumber“), werden weggelassen. Bei Revit-Modellen waren das bis zur Hälfte aller Benutzertexte (Clinic: Datei 41 % kleiner).
  - Herstellereigene Mengenlisten (z. B. `ArchiCADQuantities`) werden weggelassen; sie wiederholen meist die Standardwerte und machten bei ArchiCAD-Dateien fast die Hälfte der Datei aus.
- **Dokument-Benutzertext** (Rhino: `GetDocumentUserText`): Name der IFC-Datei, IFC-Schema, Projektname und, falls vorhanden, die Georeferenzierung aus `IfcMapConversion` (Rechts-/Hochwert und Höhe in m, Drehung in Grad, Maßstab, Koordinatensystem z. B. „EPSG:25832“).
- **Blöcke (Option, Standard aus):** Mit „Gleiche Bauteile als Blöcke (kleinere Datei)“ in den Einstellungen bzw. `--blocks` wird Typ-Geometrie, die mehrere Bauteile gemeinsam haben (Fenster, Türen, Möbel, Formteile), einmal als Blockdefinition gespeichert und jedes Bauteil als Blockinstanz an seiner Stelle, mit seinen Benutzertexten, seinem Layer und seiner Farbe. Die Lage ist dieselbe wie ohne Blöcke, auch bei gespiegelten Typen. Gemessen an drei Revit-Modellen: Datei 20–45 % kleiner, Schreiben 0,6–0,75× so lang; mit Polyflächen auch die ganze Umwandlung schneller (revit_arc 33 statt 50 s, Clinic 23 statt 37 s), weil jede Typ-Geometrie nur einmal zur Polyfläche wird. Aber: Blockinstanzen verhalten sich in Rhino anders als normale Objekte – zum Bearbeiten der Geometrie muss eine Instanz erst aufgelöst werden (`_Explode`). Die Objekte der Blockdefinitionen liegen auf dem Layer `Blockdefinitionen`, der sichtbar bleiben muss.
- **Georeferenzierte Modelle** (Koordinaten in UTM/Gauß-Krüger, z. B. bei Brücken) behalten volle Genauigkeit.
- Die Datei wird im Rhino-7-Format geschrieben und lässt sich damit in Rhino 7 und 8 öffnen.

### Maßhaltigkeit

- **Einheiten:** Die Ausgabe ist immer in Metern, ob die IFC in mm, m, Fuß oder Zoll vorliegt. Die Rhino-Datei hat die Einheit Meter, die absolute Toleranz 0,001 m (1 mm) und die Winkeltoleranz 1°.
- **Koordinaten:** Die Bauteile liegen in den Projektkoordinaten der IFC, wie im Autorenprogramm. Eine Georeferenzierung (`IfcMapConversion`: Rechts-/Hochwert, Drehung, Maßstab) wird nicht angewendet; in `.3dm` stehen ihre Werte im Dokument-Benutzertext. Auch Hunderte Kilometer vom Ursprung bleiben die Koordinaten genau: `.3dm` speichert sie in doppelter Genauigkeit, `.obj` mit 15 Stellen, `.glb` jedes Bauteil um seinen Einfügepunkt.
- **Ebene Geometrie** (Wände, Decken, Öffnungen, Profile) kommt eckpunktgenau heraus. Gemessen an 11 echten Modellen (mm, m, Fuß; IFC2X3, IFC4, IFC4X3) gegen IfcOpenShells eigene Geometrie und gegen die Maße in der IFC (Profile, Extrusionen, Mengen): Abweichung unter 0,001 mm in `.3dm` und `.obj`, unter 0,02 mm in `.glb`.
- **Runde Geometrie** (Stützen, Rohre, Bögen) wird facettiert: Die Eckpunkte liegen genau auf der Rundung, die Sehnen höchstens 0,5 mm innen (mit OpenCASCADE, also im Standard „Genau“, 0,25 mm). Ein dünnes Rohr (Ø 10 cm) hat dadurch etwa 0,6 % weniger Volumen.
- **Vollständig und reproduzierbar:** Der Standard-Geometriekern „Genau“ liefert jedes Bauteil vollständig und bei jedem Lauf gleich, unabhängig von der Zahl der Threads (siehe „Geometriekern“).
- **Selbst prüfen:** `tools/accuracy.py` wandelt eine IFC in allen Formaten um und vergleicht jedes Bauteil mit IfcOpenShells Geometrie und den Maßen aus der IFC:

```bash
python tools/accuracy.py modell.ifc --out-dir out --report genauigkeit.md
```

### Große Modelle (mehrere GB)

- **Arbeitsspeicher:** Die IFC-Datei wird komplett eingelesen. Das allein braucht etwa das 6-Fache ihrer Größe, die Umwandlung 1–2 GB mehr; bei `.3dm` bleibt zusätzlich die Ausgabe bis zum Speichern im Speicher. **Faustregel: eine 2-GB-IFC braucht ca. 14–16 GB RAM.** Ist absehbar zu wenig frei, warnt der Converter vor dem Start, wandelt aber trotzdem um.
- **Geometrie in Paketen:** Die Geometrie wird in Paketen zu 200 Bauteilen berechnet (50 je Thread, höchstens 2000), und der Speicher wird nach jedem Paket wieder freigegeben. Die Zahl der Rechen-Threads passt sich dem freien RAM an.
  - **Keine wartenden Threads:** Rechnen nur noch die letzten Bauteile eines Pakets (höchstens ein Viertel der Threads ist beschäftigt), beginnt schon das nächste Paket. Hält ein einzelnes langsames Bauteil sein Paket auf, rechnen die übrigen Threads bis zu 16 Pakete voraus, solange mindestens 4 GB RAM frei sind. Die Ergebnisse warten im Speicher, bis das Paket davor fertig ist; die Reihenfolge in der Ausgabe bleibt dieselbe.
- **Geometriekern** (Einstellungen bzw. `--kernel`):
  - **Genau** (Standard, `accurate`): Alle Bauteile werden mit OpenCASCADE berechnet, nur reine Dreiecksnetze ab 1000 Dreiecken (Geländemodelle, `IfcTriangulatedFaceSet` ohne Öffnungen) mit IfcOpenShells schnellem Hybrid-Kern, der sie unverändert übernimmt (auf allen Testmodellen identisch mit OpenCASCADE). Ein Gelände dauert so Sekunden statt über 20 Minuten.
  - **Schnell** (`hybrid`): alles mit dem Hybrid-Kern (CGAL + OpenCASCADE), auf echten Modellen 3–13× schneller. Er lässt aber bei einzelnen Bauteilen Flächen weg oder erzeugt sie doppelt, je nach Zahl der Threads (z. B. fehlte einer ArchiCAD-Wand ein Viertel ihrer Fläche).
  - **Nur OpenCASCADE** (`opencascade`): alles mit OpenCASCADE, auch Geländemodelle.
  - Stürzt der Hybrid-Kern bei der Bauteilberechnung ab („Genau“ und „Schnell“) und lässt sich das betroffene Bauteil nicht eingrenzen, wird die ganze Datei automatisch nur mit OpenCASCADE wiederholt. Ein Absturz beim Lesen der IFC-Datei oder beim Schreiben der Ausgabe wird nicht so wiederholt, er käme wieder.
- **Absturz oder Hänger bei einzelnen Bauteilen:** Stürzt die Umwandlung ab oder rechnet sie nicht mehr (alle Prozesse bei 0 % CPU), wird sie beendet und automatisch neu gestartet. Hängt sie nach einem gemeldeten Stapelüberlauf, wird das nach einer Minute erkannt, sonst nach 10 Minuten ohne Rechenaktivität. Verdächtig sind nur die Bauteile, die dabei noch nicht fertig waren; sie werden im neuen Versuch zuerst und einzeln berechnet, und ein Bauteil, an dem es erneut hängt oder abstürzt, wird übersprungen. Nach der Umwandlung nennt das Fenster die übersprungenen Bauteile mit Klasse, GlobalId und Name (z. B. „IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc“), damit sie sich im CAD-Programm finden lassen. Die vollständige Liste – übersprungene Bauteile und Bauteile ohne Geometrie – zeigt ein Rechtsklick auf die Datei → „Übersprungene Bauteile…“ (oder der gleichnamige Knopf unter der Liste); dort lässt sie sich markieren und kopieren (Strg+A, Strg+C, „Alles kopieren“), als Tabelle zum Einfügen in Excel. Geometrie, die sich selbst enthält (fehlerhafte Datei), wird gar nicht erst berechnet.
  - **Kein Neuberechnen nach einem Absturz** (Rhino-Ausgabe): Die fertig berechnete Geometrie wird nach jedem Paket im Temp-Ordner zwischengespeichert. Ein Neustart nach einem Absturz oder Hänger liest diese Pakete wieder ein und berechnet nur den Rest, das Ergebnis ist dasselbe wie ohne Absturz. Nur das Einlesen der IFC-Datei wiederholt sich. Der Zwischenstand braucht etwa das Dreifache der IFC-Größe an freiem Platz (sonst wird ohne ihn umgewandelt) und wird am Ende gelöscht. Wechselt der Neustart auf den OpenCASCADE-Kern, wird alles neu berechnet. Für GLB/OBJ gibt es das nicht.
  - **Gemerkt pro Datei:** Übersprungene Bauteile merkt sich der Converter in `%LOCALAPPDATA%\IFC Converter\quarantine.json` (Linux: `~/.local/state/ifc-converter/`), zur Datei mit Name, Größe und Änderungszeit, Geometriekern-Strategie und IfcOpenShell-Version. Wird dieselbe, unveränderte Datei wieder umgewandelt, werden sie gleich übersprungen und wieder gemeldet, ohne neue Versuche. Ändert sich die Datei (oder die Kern-Strategie, oder kommt eine neue IfcOpenShell-Version), wird alles neu versucht. Gemerkt werden höchstens 100 Bauteile für die 50 zuletzt umgewandelten Dateien; ist die Datei beschädigt, fängt der Converter einfach neu an.
  - **Achsen:** Stürzt die Umwandlung bei den Achsen der Rhino-Ausgabe ab (`IfcAlignment`, `IfcGrid`, die nach den Bauteilen berechnet werden) oder hängt sie dort, wird sie einmal ohne diese Achsen wiederholt; sie werden als übersprungen gemeldet.
- **Eigener Prozess:** Jede Umwandlung läuft in einem eigenen Prozess (im Fenster wie im Terminal). Reicht der Arbeitsspeicher nicht und das System beendet die Umwandlung (oder sie stürzt ab), wird nur diese Datei als Fehler markiert, und die nächste wird umgewandelt. „Abbrechen“ im Fenster wirkt sofort, auch während die IFC-Datei noch gelesen wird. Im Terminal zeigt eine Zeile den Fortschritt in Prozent.
- **Fortschritt:** Das Einlesen großer Dateien dauert einige Minuten. Das Fenster zeigt solange „IFC wird gelesen …“. Auch beim Schreiben der Ausgabe (bei großen Modellen ebenfalls Minuten) steht dort, was gerade passiert, mit der schon geschriebenen Größe; die Logdatei hält jede Phase mit ihrer Dauer fest und schreibt jede Minute ein Lebenszeichen.
- **Netzlaufwerke:** Liegt der Ausgabeordner auf einem Netzlaufwerk (`\\server\…` oder ein verbundenes Laufwerk), wird die Datei erst lokal im Temp-Ordner geschrieben und dann in einem Zug kopiert – openNURBS schreibt in vielen kleinen Stücken, was über das Netz sehr langsam ist. Bricht die Verbindung beim Kopieren ab, wird es bis zu viermal erneut versucht, über eine `.part`-Datei, also nie halb unter dem richtigen Namen. Klappt es gar nicht, bleibt die fertige Datei lokal in `%LOCALAPPDATA%\IFC Converter\Ausgabe`, und die Meldung sagt das.
- **Standby:** Während einer Umwandlung geht Windows nicht von selbst in den Standby; der Bildschirm darf sich trotzdem abschalten und sperren.
- **Rücksicht auf andere Programme** (der Converter läuft auf Arbeitsrechnern neben Rhino, Revit & Co.):
  - **Rechenleistung:** Standardmäßig hält eine Umwandlung etwa die Hälfte der logischen Kerne beschäftigt: zwei Drittel davon als Geometrie-Threads (höchstens 16), den Rest für die Hilfsprozesse, die bei `.3dm` ab 500 Bauteilen die Polyflächen bauen (einer je zwei Threads, höchstens 8). Auf 32 logischen Kernen sind das 11 Threads und 5 Hilfsprozesse, auf 8 Kernen 3 Threads und 1 Hilfsprozess. Mehr Threads lassen sich in den Einstellungen bzw. mit `-j` wählen.
  - **Priorität:** Umwandlungsprozess und Hilfsprozesse laufen mit niedriger Priorität („Niedriger als normal“), unter Windows auch mit niedrigerer Speicherpriorität: Wird der Arbeitsspeicher knapp, behält Windows die Seiten der anderen Programme zuerst im RAM. Die Ein-/Ausgabe-Priorität wird nicht geändert (das ginge nur über eine undokumentierte Windows-Funktion); die IFC-Datei wird ohnehin einmal am Stück gelesen und die Ausgabe am Stück geschrieben.
  - **Speichergrenze (Windows):** Umwandlungsprozess und Hilfsprozesse laufen in einem Windows-Job-Objekt und dürfen zusammen höchstens 85 % des Arbeitsspeichers belegen, damit eine außer Kontrolle geratene Umwandlung andere Programme nicht in die Auslagerungsdatei drängt. Wird die Grenze erreicht, endet die Umwandlung mit „Der Arbeitsspeicher hat nicht gereicht …“, ohne neuen Versuch. Das Job-Objekt sorgt außerdem dafür, dass alle Prozesse der Umwandlung mit dem Programm enden, auch wenn es abstürzt oder im Task-Manager beendet wird. Lässt sich das Job-Objekt nicht einrichten, läuft die Umwandlung ohne diese Grenze (steht in der Logdatei).
- **Tief verschachtelte Geometrie:** Bauteile mit mehr als 100 Ebenen verschachtelter Ausschnitte (`IfcBooleanResult`) oder Typ-Geometrien (`IfcMappedItem`) werden vor allen anderen einzeln in einem Thread mit 240 MB Stack berechnet; das Fenster zeigt dabei, welches gerade dran ist. Mit Windows' Standard von 1 MB liefen solche Modelle in einen Stapelüberlauf (Fehlercode `0xC00000FD`) oder blieben hängen. Zusätzlich reservieren die Windows-Programme 256 MB Stack für jeden Thread.
- **GLB:** Das Format ist auf 4 GB Ausgabe begrenzt. Für riesige Modelle `.3dm` oder `.obj` nehmen.

**Richtwerte** aus dem Stresstest mit 64 frei verfügbaren Modellen (Laptop, 8 Kerne / 8 GB RAM):

| Modell | IFC | Bauteile | `.3dm` Netze | `.3dm` Polyflächen | `.glb` | RAM-Spitze (Netze) |
|---|---|---|---|---|---|---|
| UpTown (35 Geschosse, FZKViewer) | 1,3 GB | 33.132 | 7,5 min | – | 5,5 min | 5,8 GB |
| UpTown (ARCHICAD) | 445 MB | 50.557 | 9,5 min | – | 5,5 min | 3,5 GB |
| Holter Tower (50 Geschosse, ArchiCAD) | 177 MB | 60.541 | 4 min | 7 min (818 MB) | 2,5 min | 1,7 GB |
| Landsarkivet (Revit, georeferenziert) | 178 MB | 10.056 | 5,5 min | 15,5 min (691 MB) | 4,5 min | 3,7 GB |
| 210 King Street (39 Geschosse, 3 Fachmodelle) | 155 MB | 12.934 | 2 min | 3 min | 1,5 min | 1,3 GB |
| ACCA Viadotto Acerno (Brücke, IFC4.3) | 33 MB | 6.546 | 1,5 min | 2,5 min | 1,5 min | 1,5 GB |

Die Zeiten wurden mit dem Kern „Schnell“ gemessen. Mit dem Standard „Genau“ dauert die Umwandlung auf dem Laptop (4 Threads) meist 1,2–2× so lang (210 King: `.3dm` Netze 2,2 statt 1,4 min, `.glb` 1,7 statt 0,8 min), bei kleinen Modellen mit vielen detaillierten Revit-Familien bis 8× (revit_arc, 14 MB: 22 statt 3 s); Geländemodelle sind gleich schnell. Auf Rechnern mit vielen Kernen schrumpft der Unterschied, weil dann das Schreiben der Datei den Takt vorgibt.

**Polyflächen bei sehr großen Modellen:** Die Ausgabe wird 1,2–4,5× so groß wie mit Netzen und liegt bis zum Speichern komplett im Arbeitsspeicher (Landsarkivet: 5,7 GB statt 3,7 GB). Für Modelle ab einigen hundert MB ist „Netze“ meist die bessere Wahl; Polyflächen lohnen sich vor allem, wenn in Rhino an Wänden, Decken und Öffnungen weitergearbeitet wird.

### Was der Converter bei fehlerhaften Dateien selbst repariert

- **Zusammengeführte Fachmodelle** mit mehreren `IfcProject` (Architektur + Tragwerk + TGA in einer Datei): IfcOpenShell würde sonst alle Einheiten ignorieren (Fuß als Meter, Grad als Bogenmaß, Öffnungen fehlen). Die Projekte werden im Speicher zusammengeführt, wenn ihre Einheiten übereinstimmen.
- **Falsch deklarierte Einheiten** (z. B. OpenRoads: Fuß ohne Typ, Fläche als Länge) werden korrigiert.
- **Leere Geometrie-Darstellungen** einzelner Bauteile blockieren nicht mehr die Nachbarn.
- **Statik-Analysemodelle** (z. B. RFEM): Knoten, Stabachsen und Lasten werden übersprungen, Flächenbauteile umgewandelt.
- Bauteile, deren Geometrie sich nicht berechnen lässt, werden gezählt und gemeldet („236 Bauteile (3 ohne Geometrie)“). Kommt gar keine Geometrie heraus, gibt es einen Fehler statt einer leeren Datei.
- **Nicht unterstützt:** IFC2X2 (vor 2006) und der Entwurf IFC4X4 (Tunnel) – dafür gibt es eine klare Meldung. Brücken im Zwischenformat IFC4X2 mit `IfcSectionedSolidHorizontal` kann IfcOpenShell nicht berechnen.

### Terminal-Modus (Drag & Drop ins Konsolenfenster)

Die alte Konsolen-Variante gibt es weiterhin: `IFC_CONVERTER_CLI=1 ./start.sh` (Linux/macOS) bzw. `python -m ifc_converter` in der Umgebung. Dort Dateien ins Fenster ziehen, Enter drücken, `3dm`, `glb` oder `obj` eingeben, um das Format zu wechseln, und `q`, um zu beenden. Strg+C bricht die laufende Umwandlung ab (ohne halbe Ausgabe und ohne Reste im Temp-Ordner).

Voraussetzung: Python 3.10 oder neuer ([python.org](https://www.python.org/downloads/), unter Windows den Haken bei „Add python.exe to PATH“ setzen).

## Logdatei und Datenschutz

- Der Converter schreibt ein Protokoll nach `%LOCALAPPDATA%\IFC Converter\logs\ifc-converter.log` (höchstens ca. 4 MB, ältere Teile werden überschrieben); Hilfe → Logdatei öffnen. Es bleibt auf diesem PC: Der Converter versendet nichts, er braucht keine Internetverbindung.
- Das Protokoll enthält Dateipfade (mit Benutzer- und Servernamen), Datei- und Bauteilnamen. **Zum Verschicken** Hilfe → „Anonymisierte Logdatei speichern…“ wählen (auch im Fehlerdialog und unter Einstellungen): Das speichert eine Kopie des ganzen Protokolls, standardmäßig als `ifc-converter-log-anonym.txt` auf dem Desktop. Darin sind Benutzer- und Rechnername durch `<Benutzer>`/`<Rechner>` ersetzt, Server und Freigaben von Netzlaufwerken durch `<Server>`/`<Freigabe>`, Ordner durch `<Ordner>` und Dateinamen durch `Datei-1.ifc`, `Datei-1.3dm` … (gleicher Name, gleiche Nummer); Bauteilnamen fallen weg. Erhalten bleiben IFC-Klasse und GlobalId, Zeiten, Größen, Versionen und Fehlermeldungen. Vor dem Versenden kurz durchsehen.
- Mit Extras → Einstellungen → „Logdatei anonymisieren“ wird das Protokoll schon beim Schreiben anonymisiert (ab dann; ältere Einträge bleiben, wie sie sind). Die Nummern der Dateien beginnen dabei mit jedem Programmstart neu.

## Manuelle Einrichtung

Das Projekt liegt auf einer exFAT-Platte, die keine Symlinks kann. Die virtuelle Umgebung liegt deshalb auf der internen SSD:

```bash
python3 -m venv ~/.local/share/venvs/ifc-file-converter
source ~/.local/share/venvs/ifc-file-converter/bin/activate
pip install -e ".[dev]"
```

## Benutzung als Kommandozeilen-Tool

```bash
source ~/.local/share/venvs/ifc-file-converter/bin/activate

ifc-converter-gui                         # Programmfenster starten

ifc-convert haus.ifc                      # → haus.glb
ifc-convert haus.ifc -f obj               # → haus.obj + haus.mtl
ifc-convert haus.ifc -f 3dm               # → haus.3dm (Rhino, Polyflächen)
ifc-convert haus.ifc -f 3dm -g mesh       # → haus.3dm nur mit Netzen
ifc-convert haus.ifc -o export/modell.glb # eigener Ausgabepfad
ifc-convert *.ifc -d output/              # mehrere Dateien in einen Ordner
```

Optionen:

- `-f, --format {glb,obj,3dm}`: Zielformat (Standard: `glb`)
- `-g, --geometry {brep,mesh}`: nur für 3dm, Polyflächen oder Netze (Standard: `brep`)
- `--blocks`: nur für 3dm, gleiche Bauteile als Blöcke (siehe „Rhino-Export“)
- `-o, --output PFAD`: Ausgabedatei (nur bei einer Eingabedatei)
- `-d, --out-dir ORDNER`: Ausgabeordner für mehrere Dateien
- `-j, --threads N`: Anzahl Threads für die Geometrie (Standard: automatisch wie im Programmfenster – zusammen mit den Hilfsprozessen der Rhino-Ausgabe etwa die Hälfte der Kerne, siehe „Rücksicht auf andere Programme“; `ifc-convert --help` zeigt die Zahl für diesen PC)
- `--normal-priority`: mit normaler statt niedriger Priorität umwandeln
- `--kernel {accurate,hybrid,opencascade}`: Geometriekern (Standard: `accurate`, siehe „Geometriekern“)

Strg+C (bzw. Strg+Untbr) bricht ab: Exit-Code 130, halbe Ausgabedateien und Zwischendateien werden entfernt.

Auch aus Python nutzbar:

```python
from ifc_converter import convert

result = convert("haus.ifc", fmt="3dm", progress=lambda pct: print(f"{pct} %"))
print(result.output, result.elements)
```

## Tests

```bash
pytest
```

## Windows-App bauen und veröffentlichen

Die Windows-App ist ein mit [PyInstaller](https://pyinstaller.org) gebauter Programmordner (`IFC Converter.exe` ohne Konsole, `ifc-convert.exe` für die Kommandozeile, Bibliotheken in `_internal`), daraus entstehen die portable ZIP und mit [Inno Setup](https://jrsoftware.org/isinfo.php) der Installer. Alles dazu liegt in `packaging/`.

**Automatisch (GitHub Actions, `.github/workflows/build.yml`)** bei jedem Push:

1. Tests unter Linux und Windows.
2. Build der App, der portablen ZIP und des Installers unter Windows.
3. Test der gebauten exe (`packaging/smoke_test.py`): eine 5 × 0,2 × 3 m große Wand wird in einem Ordner mit Umlauten und Leerzeichen in alle Formate umgewandelt (3DM Polyflächen mit dem Standardkern und dem Hybrid-Kern, 3DM Netze, GLB, OBJ). Jede Ausgabe muss genau diese Maße haben. Dazu: Ausgabe auf ein Netzlaufwerk (UNC), tief verschachtelte Geometrie, eine mit Strg+Untbr abgebrochene und eine hart beendete Umwandlung; im Temp-Ordner darf nichts liegen bleiben (Reste einer hart beendeten räumt ein späterer Start weg). Außerdem muss das Programmfenster starten, und die Bibliotheken der 3D-Vorschau (QtOpenGL, `opengl32sw.dll`) müssen im Build sein.
4. Test des Installers (`packaging/installer_test.py`): Update von der letzten veröffentlichten Version (Einstellungen bleiben, das Programm läuft), stille Neuinstallation mit Umwandlung durch das installierte Programm, Installer und Deinstallation verweigern sich bei laufendem Programm, Installation mit „Öffnen mit“-Eintrag; jede Deinstallation muss Programm, Verknüpfung und Registry-Einträge entfernen.
5. Installer und ZIP liegen 7 Tage als Artefakt „IFC-Converter-windows“ am Workflow-Lauf.

**Neue Version veröffentlichen:** `version` in `pyproject.toml` erhöhen, committen und pushen, dann ein Tag setzen:

```bash
git tag v0.2.0
git push origin v0.2.0
```

Der Workflow baut und testet wie oben und legt danach ein GitHub-Release mit Installer, ZIP und `SHA256SUMS.txt` an. Passt das Tag nicht zur Version in `pyproject.toml`, bricht der Build ab.

**Lokal unter Windows bauen** (Python 3.13 und [Inno Setup 6](https://jrsoftware.org/isdl.php) installiert):

```bat
py -3.13 -m venv .venv-build
.venv-build\Scripts\python -m pip install -c packaging\constraints.txt ".[build]"
.venv-build\Scripts\python packaging\build.py
.venv-build\Scripts\python packaging\smoke_test.py "dist\IFC Converter" --gui
```

Ergebnis in `dist\`. Ohne Inno Setup: `build.py --no-installer`.

**Feste Versionen:** `packaging/constraints.txt` legt die genauen Versionen von IfcOpenShell, rhino3dm, Qt, NumPy und PyInstaller für Tests und Build fest, damit ein Release genau das enthält, was getestet wurde. Beim Aktualisieren die Maßhaltigkeit mit echten Modellen erneut prüfen (`tools/benchmark.py`).

## Stresstest mit echten Modellen

`tools/benchmark.py` wandelt IFC-Dateien in allen Formaten um, jede Umwandlung in einem eigenen Prozess, und schreibt Zeit, RAM-Spitze, Ausgabegröße und Prüfungen der Ausgabe (gültige Polyflächen, Attribute, Koordinaten) in einen Bericht:

```bash
python tools/benchmark.py modelle/*.ifc --modes 3dm-brep,3dm-mesh,glb --out-dir out --report bericht.md
```
