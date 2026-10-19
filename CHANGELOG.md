# Änderungen

Der Abschnitt der jeweils neuesten Version wird als Text des GitHub-Releases verwendet.

## 0.5.1 – 2026-10-19

- **Linux-Version:** `IFC-Converter-<Version>-linux-x86_64.tar.gz` mit `install.sh` (Installation ohne Root unter `~/.local`, Startmenü-Eintrag, `ifc-convert` im Pfad) und `uninstall.sh`; läuft unter Wayland und X11. Die Prüfsummen aller Pakete stehen in `SHA256SUMS.txt`.
- **Neues Ausgabeformat DAE (Collada):** Dreiecksnetze mit Farben, in Metern, Z nach oben, ein Knoten je Bauteil (für SketchUp, Blender, Unity, ArchiCAD). **Gepackte `.ifczip`-Dateien** werden direkt gelesen; ifcXML wird mit einer klaren Meldung abgelehnt.
- **Überarbeitetes Programmfenster:** neues Programmsymbol, Statussymbole und Fortschritt je Datei in der Liste, ein-/ausklappbares Protokoll (Ansicht → Protokoll, F4), kompakte Ablagezone sobald Dateien in der Liste sind, Einstellungen mit Reitern (passt auch bei 150 % Skalierung), Über-Dialog mit Komponenten und Lizenzen, einheitliche Texte („Konvertierung“), Hervorhebung von „Ausgabeordner öffnen“ nach dem Erfolg. Geprüft in hellem und dunklem Farbschema.
- **Maßhaltigkeit:** Extrusionen mit negativer Tiefe (Zenodo-„AutoGen“-Brücken, IFC4.3) werden beim Einlesen repariert – bisher fehlten diese Bauteile; Trassierungs-Hilfslinien (`IfcAlignmentHorizontal/Vertical/Cant/Segment`) werden in GLB/OBJ nicht mehr als Geometrie geschrieben (sie lagen weit außerhalb des Modells). Für fünf Modelle quer durch den Testbestand wurde belegt, dass jede Bauteilklasse mit 3D-Körper in der Ausgabe ankommt.
- Release-Text kommt aus dieser Datei (`packaging/release_notes.py`).

## 0.4.1 – 2026-10-19

- **3D-Vorschau** der ausgewählten IFC-Datei unter der Dateiliste (Ansicht → Vorschau, F3): Drehen, Verschieben, Zoomen, Klick auf ein Bauteil zeigt Klasse, GlobalId und Name. Dateien bis 150 MB werden sofort berechnet, größere auf Knopfdruck; berechnete Vorschauen werden gemerkt. Zeichnen mit der Grafikkarte (OpenGL), sonst automatisch in Software.
- IFC4.3-Dateien, deren SI-Einheit ohne Namen geschrieben ist (z. B. `IfcSIUnit(*,.LENGTHUNIT.,.MILLI.,$)`), wurden 1000-fach zu groß gelesen; die Einheit wird jetzt repariert.
- Bauteile ohne Geometrie bekommen einzeln einen zweiten Versuch mit feinerer Toleranz (höchstens 2 Minuten je Umwandlung).

## 0.3.4 – 2026-10-08

- Problem-Bauteile werden je Datei und IfcOpenShell-Version gemerkt, nicht je Converter-Version.
- Baugruppen (z. B. Vorhangfassaden), deren Teile umgewandelt wurden, gelten nicht mehr als „ohne Geometrie“.

## 0.3.3 – 2026-10-08

- Nach einem Absturz oder Hänger werden fertig berechnete Pakete übernommen statt neu berechnet (Rhino-Ausgabe).

## 0.3.2 – 2026-10-08

- Rhino: Bauteile mit mehreren Materialien werden je Material aufgeteilt und gruppiert (Glas bleibt durchsichtig); Baugruppen als Gruppen; Typ, Geschoss, Tag und Georeferenzierung als Text; Platzhalter-Werte entfallen; Option „Gleiche Bauteile als Blöcke“.
- Rechenbudget etwa die halbe Maschine, Speicherdeckel 85 % des RAM, niedrige Priorität auch für den Speicher; ein langsames Bauteil hält die übrigen Threads nicht mehr auf.
- Übersprungene Bauteile als kopierbare Liste; anonymisierte Logdatei (Hilfe-Menü und Einstellung); Dateien lassen sich während einer Konvertierung hinzufügen; Installer verweigert, solange das Programm läuft; „Öffnen mit“-Eintrag funktioniert.

## 0.2.5 – 2026-10-08

- Stapelüberlauf im Geometriekern wird nach einer Minute erkannt; nur noch nicht fertige Bauteile gelten als verdächtig und werden zuerst berechnet; Problem-Bauteile werden mit GlobalId genannt.
- Netzwerk-Kopie mit Wiederholungen über eine `.part`-Datei; fertige Dateien bleiben lokal erhalten, wenn das Kopieren scheitert; kein Standby während einer Konvertierung.
- Längen, Flächen und Volumen im Rhino-Text in m, m² und m³; Raum-Layer zunächst ausgeblendet.

## 0.2.4 – 2026-10-08

- Absturz oder Hänger bei einzelnen Bauteilen: automatischer Neustart, das betroffene Bauteil wird eingegrenzt und übersprungen; tief verschachtelte Bauteile werden einzeln mit großem Stack berechnet.

## 0.2.2 – 2026-10-08

- 256 MB Stack für die Windows-Programme (Stapelüberlauf bei tief verschachtelten Modellen); Ausgabe für Netzlaufwerke wird lokal geschrieben und dann kopiert; Phasen und Lebenszeichen im Log.

## 0.2.1 – 2026-10-07

- Große Rhino-Exporte (Hilfsprozesse) funktionierten im installierten Programm nicht („daemonic processes“).

## 0.2.0 – 2026-10-07

- Windows-Programm mit Installer und portabler ZIP; Rhino-Export als Polyflächen oder Netze in Metern, Lage wie in der IFC; Kern „Genau“ als Standard.
