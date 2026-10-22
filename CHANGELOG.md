# Änderungen

Der Abschnitt der jeweils neuesten Version wird als Text des GitHub-Releases verwendet.

## 0.9.5 – 2026-10-22

- **Feste Download-Links für die neueste Version:** Jedes Release enthält den Installer, die Anleitung, die portable ZIP und das Linux-Archiv zusätzlich unter festen Namen ohne Versionsnummer. Damit zeigen `https://github.com/Sh4wN98/IFC-Converter/releases/latest/download/IFC-Converter-Setup.exe` und `…/IFC-Converter-Guide.pdf` (ebenso `IFC-Converter-portable.zip`, `IFC-Converter-linux-x86_64.tar.gz`, `SHA256SUMS.txt`) immer auf das neueste Release – zum einmaligen Eintragen auf einem Server oder einer Intranet-Seite. Heruntergeladen wird weiterhin nur von Hand; das Programm verbindet sich nie mit dem Internet.

## 0.9.4 – 2026-10-22

- **Gebäudehülle: nach einem Hänger rechnet OpenCASCADE die Vorberechnung:** Beim 1,5-GB-Modell hängt der schnelle (hybride) Kern sowohl in der Vorschau als auch in der Hüllen-Vorberechnung; 0.9.3 hat beides nach 8 bzw. 10 Minuten beendet, die Vorschau lief danach mit OpenCASCADE durch, die Hülle aber nicht: der neue Versuch rechnete die verdächtigen Bauteile einzeln, wieder zuerst mit dem hybriden Kern, und hing dort erneut. Jetzt wird die Hüllen-Vorberechnung nach einem Hänger oder Absturz in einem Rechenpaket mit OpenCASCADE wiederholt („… mit OpenCASCADE für die Vorberechnung …“); die Umwandlung selbst behält ihre Kern-Strategie.
- **Warum der Rechenprozess Hänger nicht selbst erkennt:** IfcOpenShell hält während des Rechnens die Sperre des Python-Interpreters. Hängt ein Kern-Thread, läuft im Rechenprozess kein Python-Code mehr, also weder die Hänger-Erkennung aus 0.9.0 noch ein Thread-Dump aus einem Python-Thread (deshalb fehlte er in den Logs von 0.9.3). Das Hauptprogramm ist der einzige Wächter; die Zeitlimits aus 0.9.3 (Hülle 10, Umwandlung 25, Vorschau 8 Minuten) gelten unverändert. Der Thread-Dump kommt jetzt vom Wächter-Thread von `faulthandler`, der ohne die Sperre auskommt („Timeout (…)!“ im Protokoll, eine Minute vor dem Abbruch).
- **Logdatei speichern:** Die gespeicherte Logdatei enthält jetzt auch `crash.log` aus dem Log-Ordner, in die das Fenster bei einem Absturz in nativem Code (Qt, OpenGL) seinen Python-Stapel schreibt – anonymisiert wie alles andere.

## 0.9.3 – 2026-10-22

- **Hänger, die der Rechenprozess selbst nicht bemerkt, werden jetzt vom Hauptprogramm beendet:** Beim 1,5-GB-Modell blieb die Hüllen-Vorberechnung auch mit 0.9.2 bei 23 % stehen (40 Minuten, CPU beschäftigt), ohne dass die Hänger-Erkennung aus 0.9.0 ansprang: sie sieht nur ein Rechenpaket, das nichts mehr liefert, nicht aber einen Kern-Thread, der schon beim Start eines Pakets hängt (der Iterator wartet dort auf sein erstes Bauteil) oder an einer anderen Stelle, die sie nicht beobachtet. Jetzt gilt zusätzlich im Hauptprogramm: Rechnet der Prozess in einer Kern-Phase (Hüllen-Vorberechnung, Geometrie, einzelne Bauteile) länger als das Hänger-Limit des Durchgangs plus 5 Minuten, ohne Fortschritt, Phase oder Position zu melden (Hülle 10, Umwandlung 25, Vorschau 8 Minuten), wird er als hängend beendet und die Umwandlung neu gestartet – wie nach einem Absturz: die noch nicht gelieferten Bauteile werden zuerst und einzeln berechnet, ein Bauteil, an dem der Kern weiter hängt, wird übersprungen (in der Hüllen-Vorberechnung sicherheitshalber behalten). Das Limit gilt nur, solange der Prozess ein Rechenpaket oder ein einzelnes Bauteil gemeldet hat, an dem der Kern arbeitet; beim Lesen, bei den Vorarbeiten in Python, beim Suchen der Außenluft und beim Schreiben gibt es kein solches Limit, dort warnt das Protokoll wie bisher nach 30 Minuten. Ein Standby des Rechners zählt nicht als Stillstand. Ein einzeln berechnetes Bauteil hat das Hänger-Limit jetzt für alle seine Versuche zusammen (bisher je Kern und Koordinatensystem einzeln), damit der Hauptprozess es nicht vorher als hängend beendet.
- **Start eines Rechenpakets mit Zeitlimit:** Liefert ein Paket schon beim Start nichts (alle ersten Bauteile hängen), wird es nach dem Hänger-Limit aufgegeben und seine Bauteile werden einzeln berechnet, statt dass die Umwandlung dort stehen bleibt.
- **Weniger Bauteile verloren nach einem Hänger:** Blieb der Kern bei den einzeln nachgerechneten Bauteilen eines aufgegebenen Pakets zweimal hängen, wurden bisher alle übrigen Bauteile des Pakets ungerechnet übersprungen (bis zu einige hundert). Jetzt bekommen sie ein neues Paket ohne die hängenden Bauteile; erst wenn auch das hängt, wird der Rest übersprungen und gemeldet.
- **Protokoll:** Eine Minute bevor das Hauptprogramm einen hängenden Prozess beendet, schreibt dieser die Stapel aller seiner Python-Threads in sein Protokoll („No progress reported for … threads of the conversion process“), damit die Stelle des Hängers in der Logdatei steht. Die Suche der Außenluft ist im Protokoll und im Fenster eine eigene Phase.

## 0.9.2 – 2026-10-22

- **Logdatei immer anonym:** Das Protokoll wird von Anfang an ohne Benutzer-, Rechner-, Server-, Ordner-, Datei- und Bauteilnamen geschrieben; den Schalter „Logdatei anonymisieren“ und „Logdatei öffnen“ gibt es nicht mehr. Die einzige Option ist **„Logdatei speichern…“** (Hilfe-Menü, Fehlerdialog, Einstellungen → Logdatei, Rechtsklick auf eine fehlgeschlagene Datei): sie speichert eine Kopie des ganzen Protokolls, standardmäßig als `ifc-converter-log.txt` auf dem Desktop. Einträge älterer Versionen werden beim Speichern ebenfalls anonymisiert.
- **Lizenz:** Der IFC Converter steht unter der GNU General Public License 3.0 oder neuer (`LICENSE`); die Lizenzhinweise im Programm nennen das.

## 0.9.1 – 2026-10-21

- **Anleitung auf Englisch, neu gestaltet:** Die Kurzanleitung im Release heißt jetzt `IFC-Converter-<Version>-Guide.pdf`, ist vollständig englisch (vier Seiten: Was das Programm macht, Installation, erste Schritte, 3D-Vorschau, große Modelle, Sprache, Rückmeldung, Kommandozeile) und hat ein ruhigeres Layout mit Titelblock, Inhaltsübersicht und Tabellen; die großen Leerräume zwischen Abbildungen und Text sind weg. Die Startseite des Repositories (README) ist dieselbe Anleitung auf Englisch mit allen Details für Anwender und Entwickler; die ausführliche deutsche Dokumentation liegt unter `docs/README-de.md`.

## 0.9.0 – 2026-10-21

- **3D-Vorschau in Sekunden statt Minuten:** Die Vorschau baut sich jetzt auf, während sie berechnet wird. Der Rechenprozess schreibt alle paar Sekunden einen Zwischenstand, die Vorschau holt ihn ab und zeigt das wachsende Modell, ohne Blickwinkel und Zoom zu verlieren (nachgepasst wird nur, solange noch nicht gedreht oder gezoomt wurde). Tragende Struktur zuerst: Gelände, Decken, Dächer, Wände, Stützen, Träger, Treppen, Rampen, Fassaden, Fenster, Türen, Geländer, dann der Rest. Möbel, Haustechnik (Rohre, Kanäle, Leitungen, Armaturen), Befestigungen, Bewehrung und sehr tief verschachtelte Bauteile bleiben ganz weg – in großen Modellen sind das die meisten Bauteile, und die tief verschachtelten waren es, die den Kern abstürzen ließen; die Infozeile nennt sie („3.210 Details weggelassen (Möbel, Haustechnik)“). Bis zu 8 Threads, wenn keine Umwandlung läuft, 4 daneben. Die Vorschau startet jetzt bei jeder Dateigröße von selbst, wenn der freie Arbeitsspeicher reicht – auch neben einer laufenden Umwandlung; sonst wie bisher auf Knopfdruck. Bei Abbruch, Absturz oder Fehler bleibt das bisher Gezeigte stehen; nach dem zweiten Absturz des Geometriekerns wird nicht weiter versucht (jeder Versuch liest die ganze Datei neu), „Erneut versuchen“ startet neu. Bereits berechnete Vorschauen werden einmal neu berechnet. Das Einlesen der IFC-Datei selbst bleibt die Untergrenze für das erste Bild (etwa 35 s je 600 MB, 100 s je 1,5 GB).
- **Hänger des Geometriekerns an einzelnen Bauteilen werden in der Umwandlung selbst abgefangen:** Ein Rechenpaket, das trotz laufendem Kern 20 Minuten lang nichts liefert (Gebäudehülle-Vorberechnung 5, Vorschau 3 Minuten), wird aufgegeben; seine noch fehlenden Bauteile werden einzeln nachgerechnet, ein Bauteil, an dem der Kern weiter hängt, wird wie nach einem Absturz übersprungen, gemerkt und im Protokoll, im Fenster und unter „Übersprungene Bauteile“ genannt – ohne Neustart und ohne die IFC noch einmal zu lesen (bisher stand die Hüllen-Vorberechnung eines 1,5-GB-Modells über zwei Stunden bei 23 %, weil nur fehlende Rechenaktivität erkannt wurde, der hängende Kern aber weiter rechnete). In der Hüllen-Vorberechnung bleibt ein solches Bauteil sicherheitshalber erhalten. Auch einzeln berechnete, tief verschachtelte Bauteile und zweite Versuche haben jetzt dieses Zeitlimit. Der Umwandlungsprozess beendet sich danach hart, weil der hängende Kern-Thread nicht beendet werden kann (`IFC_CONVERTER_HANG_SECONDS` überschreibt die Limits).
- **3D-Vorschau auf Windows-PCs mit NVIDIA-Grafik:** Achsenkreuz und Bauteil-Beschriftung werden jetzt im Bild selbst gezeichnet (bisher ein durchsichtiges Fenster über der OpenGL-Ansicht, das dort nicht erschien). Die Ansichtsleiste (Iso, Oben, Vorne, Seite, ganzes Modell, Kanten, Projektion) sitzt jetzt dauerhaft in der Kopfzeile der Vorschau neben „Ansicht zurücksetzen“ statt nur bei Mauszeiger über der Ansicht; ohne Modell ist sie ausgegraut. Kantenlinien werden erst berechnet, wenn ein paar Sekunden kein neueres Modell kam, und nie doppelt. Kurzanleitung mit neuer Abbildung (`tools/guide_screens.py`).
- **Behoben:** Nach tief verschachtelten Bauteilen blieb in der Hüllen-Vorberechnung deren Text („Element 11 von 11 wird einzeln berechnet …“) bis zum Ende des Durchgangs stehen; jetzt kehrt „Gebäudehülle wird bestimmt …“ zurück. Das Protokoll warnt, wenn die Umwandlung 30 Minuten lang rechnet, ohne dass sich Fortschritt, Phase oder Position ändern.

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
