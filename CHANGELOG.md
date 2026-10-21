# Änderungen

Der Abschnitt der jeweils neuesten Version wird als Text des GitHub-Releases verwendet.

## 0.8.0 – 2026-10-21

- **3D-Vorschau überarbeitet:** weiche Himmel-/Bodenbeleuchtung mit Hauptlicht, Kanten als feine Linien (umschaltbar), Verlaufshintergrund in hellem und dunklem Schema, Bodenraster und Achsenkreuz, 4× Kantenglättung, animierte Ansichtswechsel, Hervorhebung des angeklickten Bauteils, Perspektive/Parallelprojektion umschaltbar, kompakte Werkzeugleiste. Der Software-Zeichner ohne OpenGL hat dasselbe Aussehen.
- **Unabhängige Prüfung der Maßhaltigkeit** (neues Werkzeug `tools/night_accuracy.py`): Jedes Bauteil wurde je Format gegen eine unabhängige OpenCASCADE-Referenz verglichen (Duplex, Revit-Beispielhaus, Klinik, Tekla-Brücke in Fuß, KIT- und bSI-Brücken, Energy Tower über die IFC2x2-Brücke; georeferenzierte Lage 512 km / 5.423 km): Lage und Maße in 3DM (Polyflächen, Netze, Blöcke), GLB, OBJ und DAE exakt (≤ 0,002 mm), Öffnungen abgezogen, Einheiten mm/Fuß/Zoll korrekt. Gefunden und behoben: **gespiegelte Typgeometrie** (Revit-Türen, -Fenster, -Möbel) war in GLB, OBJ und DAE innen nach außen gekehrt (Normalen nach innen, negatives Volumen); sie wird jetzt wie im Rhino-Export nach außen gedreht.
- **Behoben nach Code-Review:** Eine Datei mit einem zweiten IfcProject ohne Einheiten (verknüpftes Modell) wurde komplett in Metern gelesen – 1000-fach zu groß; jetzt wird in das erste Projekt mit Einheiten zusammengeführt, bei abweichenden Einheiten mit Hinweis. Der Watchdog brach lange Rhino-Schreibphasen als „hängt“ ab, nachdem die Hilfsprozesse beendet waren. Schema-Namen wie `IFC4_ADD2`, `IFC2X3_TC1`, `IFC4X3_RC4` werden als das jeweils gleiche Schema gelesen. Abgeschnittene IFC-Dateien (kein `END-ISO-10303-21`) bekommen einen Hinweis. Die Arbeitskopie der Schema-Brücke prüft den freien Platz und bleibt bei Abbruch nicht liegen.
- **Nur Gebäudehülle:** Ob die Hülle offen ist, wird jetzt an der eingeschlossenen Luft erkannt, nicht an der Zahl weggelassener Bauteile (ein Hüllmodell ohne Innenausbau galt sonst als offen, und Bänke vor dem Haus fielen weg). Mehrere Baumassen (zwei Gebäudeflügel) und fein unterteilte Massen werden erkannt; weit abseits liegende Bauteile (Vermessungspunkte kilometerweit entfernt) sprengen das Raster nicht mehr; Ursprung ist die Gebäudeplatzierung. Die Massenprüfung bleibt auch bei 100.000 Bauteilen schnell.
- **Oberfläche:** Nicht beschreibbarer Ausgabeordner wird vor dem Start klar gemeldet (Fenster und Terminal); Zähler einer erneut gestarteten Zeile werden zurückgesetzt; Dialog „Übersprungene Bauteile“ ohne Zeilen zeigt die Spaltenköpfe vollständig; Tab-Reihenfolge ohne Zwischenstopp; Größen, Zählungen und Rastermaße mit den Zahlenzeichen der jeweiligen Sprache; Terminal-Ausgaben folgen `--lang`.

## 0.7.1 – 2026-10-20

- **Mehrsprachige Oberfläche:** Fenster, Dialoge, Dateiliste, Meldungen im Protokoll und die Statustexte der Konvertierung gibt es jetzt in Englisch (Standard), Deutsch, Französisch, Spanisch, Italienisch, Portugiesisch, Niederländisch, Polnisch und Türkisch. Umschalten unter Extras → Sprache (Tools → Language); die Wahl wird gemerkt und nach einem Neustart übernommen, den das Programm anbietet. Im Terminal `--lang de` bzw. die Umgebungsvariable `IFC_CONVERTER_LANG`. Die deutschen Texte sind unverändert; Logdatei und Konvertierungsmeldungen erscheinen in der gewählten Sprache, Rhino-Layer und Benutzertexte bleiben wie bisher.

## 0.6.3 – 2026-10-20

- **Nur Gebäudehülle: Spalte bleiben offen.** Bei großen Modellen wurde das Raster bisher auf 20 cm oder mehr vergröbert; ein Spalt unter einem Sturz oder zwischen Fensterrahmen und Decke, der schmaler als eine Zelle ist, galt dann als dicht, und das Bauteil dahinter fiel als „innen“ weg – zu sehen als Loch in der Hülle (Rückmeldung aus einem 316-MB-Modell). Jetzt wird das ganze Modell auf dem groben Raster gefüllt und rund um die Außenluft, zwölf Zellen tief, mit der viermal feineren Abtastung nachgefüllt: Spalte von der Breite einer feinen Zelle an bleiben offen, was sie auskleidet, zählt als außen. Die Speicherbudgets richten sich nach dem freien RAM des Rechners, auf dem Arbeitsplatz-PC bleibt das feine Raster damit auch bei großen Modellen bei 5 cm. Das Protokoll nennt beide Rastermaße („Raster 0,05 m, grob 0,2 m“).

## 0.6.2 – 2026-10-20

- **Nur Gebäudehülle bleibt geschlossen:** Bisher fiel ein Bauteil weg, wenn weniger als 5 % seiner Rasterzellen an Außenluft grenzten – ein Sturz oder ein Wandstück, das nur durch einen Spalt zu sehen ist, hinterließ dann ein Loch in der Hülle. Jetzt bleibt jedes Bauteil, das irgendwo an Außenluft grenzt; weggelassen wird nur, was von außen an keiner Stelle zu sehen ist. Das Raster ist feiner (5 cm statt 10 cm, bei großen Modellen weiterhin automatisch gröber), damit auch schmale Spalte und dünne Bauteile aufgelöst werden. Das Protokoll nennt die weggelassenen Bauteile nach Klassen („Weggelassen: 34 IfcWallStandardCase, 16 IfcSlab, …“).

## 0.6.1 – 2026-10-20

- **Nur Gebäudehülle, Nachbesserungen aus der Prüfung am Testbestand:** Baumassen (z. B. ein Revit-Massenkörper, der das ganze Gebäude umschließt, oder ein als Block modelliertes Gelände) verdecken die Hülle nicht mehr – ohne `IsExternal`-Kennzeichnung wäre im Revit-Bürogebäude sonst das Dach weggefallen; solche Körper bleiben selbst erhalten, das Protokoll nennt sie. Bei Teilmodellen ohne geschlossene Hülle entfallen zusätzlich Decken- und Bodenbeläge (IfcCovering CEILING/FLOORING). Neues Prüfwerkzeug `tools/hull_check.py` (Vergleich mit `IsExternal`, Dateigrößen, Ansichten der behaltenen und weggelassenen Bauteile).

## 0.6.0 – 2026-10-20

- **Neue Option „Nur Gebäudehülle“** (Häkchen unter dem Zielformat; im Terminal `--envelope`, kurz `--hull`; für jedes Zielformat): Nur was von außen zu sehen ist – Außenwände, Dächer, Fenster, Türen, Balkone, Gelände – wird umgewandelt, Innenwände, Möbel, Einrichtung, Rohre und Kanäle bleiben weg, die Ausgabe wird deutlich kleiner (für Umgebungsmodelle, schwächere PCs und Modelle mit GB-großer Ausgabe). Bauteile werden nur weggelassen, nie verändert. Als außen gekennzeichnete Bauteile (`IsExternal`) bleiben immer erhalten, im Zweifel wird ein Bauteil behalten. Ein kurzer Durchgang vorab bestimmt die Hülle („Gebäudehülle wird bestimmt …“, die ersten 25 % des Fortschritts); Protokoll, Dateiliste und Terminal nennen danach, wie viele innen liegende Bauteile weggelassen wurden. Die Einstellung wird gemerkt.
- **So wird die Hülle bestimmt:** Ein grober Durchgang (schneller Kern, 5 cm Toleranz) trägt die Oberflächen aller Bauteile in ein 10-cm-Raster ein; vom Rand des Rasters aus wird die Außenluft gesucht, und ein Bauteil gehört zur Hülle, wenn mindestens 5 % seiner Rasterzellen an Außenluft grenzen. Verglasung gilt als undurchsichtig. Hat das Modell keine geschlossene Hülle (Teilmodell ohne Decken und Dach), entscheiden stattdessen die Kennzeichnung `IsExternal` und die Bauteilklasse (Möbel, Einrichtung, Leitungen entfallen). Geprüft am öffentlichen Testbestand (Duplex, Revit-Beispiele, Schependomlaan, Klinik, KIT-Brücke): kein von außen sichtbares Bauteil fehlte. Duplex: 63 von 215 Bauteilen bleiben, OBJ 1,2 → 0,2 MB; Revit-Bürogebäude mit Vorhangfassade: 4.872 von 5.552, OBJ 32 → 18 MB; Klinik-Architekturmodell ohne Decken (Fallback über IsExternal): 1.121 von 2.586, OBJ 8,3 → 1,9 MB.

## 0.5.3 – 2026-10-19

- **IFC2x2 und IFC4x4 werden gelesen:** IFC2x2 (2003) als IFC2x3; der unveröffentlichte Tunnel-Entwurf IFC4x4 als IFC4.3 mit Ersatzklassen für seine sechs Entwurfs-Entitäten (IfcTunnel → IfcFacility, IfcTunnelPart → IfcFacilityPart, IfcUndergroundExcavation und IfcArchElement → IfcBuildingElementProxy; Datensatz-Verweise entfallen). Geprüft am „Energy Tower“ (IFC2x2, 234.000 Entitäten) und am Trimble-Tunnel (IFC4x4, 695.000 Entitäten, 16 Bauteile mit Geometrie). Das Protokoll nennt die Umdeutung; Maße und Lage bleiben unverändert.

## 0.5.2 – 2026-10-19

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
