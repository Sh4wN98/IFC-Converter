# Änderungen

Der Abschnitt der jeweils neuesten Version wird als Text des GitHub-Releases verwendet.

## 0.5.0 – 2026-10-19

(wird vor dem Release ergänzt)

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
