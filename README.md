# IFC File Converter

Kleines Programm (mit Fenster oder als Kommandozeilen-Tool), das IFC-Gebäudemodelle in 3D-Formate umwandelt:

| Format | Endung | Gut für |
|---|---|---|
| Rhino | `.3dm` | Rhino, Grasshopper (Layer pro Geschoss und Bauteiltyp, IFC-Daten als Attribute) |
| glTF (binär) | `.glb` | Web-Viewer, Three.js, Blender, Game-Engines |
| Wavefront OBJ | `.obj` + `.mtl` | Blender, fast jedes 3D-Programm |

Die Geometrie wird mit [IfcOpenShell](https://ifcopenshell.org) berechnet und in Metern ausgegeben.
Öffnungskörper (`IfcOpeningElement`) werden nie exportiert. Raumvolumen (`IfcSpace`) landen nur in `.3dm`, dort auf eigenen Layern zum Ausblenden.

## Schnellstart (Programmfenster)

1. **Windows:** `start.bat` doppelklicken. **Linux/macOS:** `./start.sh` ausführen.
2. Beim ersten Start richtet sich der Converter selbst ein (Internet nötig für den Download von IfcOpenShell, rhino3dm und Qt). Nach einem Update passiert das automatisch noch einmal.
3. IFC-Dateien oder ganze Ordner ins Fenster ziehen (oder „Dateien hinzufügen…“).
4. Format wählen (Standard: 3DM), Ausgabeordner prüfen und auf „Konvertieren“ klicken.
5. Die fertigen Dateien landen standardmäßig auf dem Desktop. Gibt es den Namen schon, wird `(2)`, `(3)` … angehängt.

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
- GlobalId, IFC-Klasse, Property-Sets und die Standard-Mengen (`BaseQuantities` bzw. `Qto_…`: Flächen, Volumen, Längen) stehen als Benutzertexte (Attribute User Text) am Objekt. Herstellereigene Mengenlisten (z. B. `ArchiCADQuantities`) werden weggelassen; sie wiederholen meist die Standardwerte und machten bei ArchiCAD-Dateien fast die Hälfte der Datei aus.
- **Georeferenzierte Modelle** (Koordinaten in UTM/Gauß-Krüger, z. B. bei Brücken) behalten volle Genauigkeit.
- Die Datei wird im Rhino-7-Format geschrieben und lässt sich damit in Rhino 7 und 8 öffnen.

### Große Modelle (mehrere GB)

- **Arbeitsspeicher:** Die IFC-Datei wird komplett eingelesen. Das allein braucht etwa das 6-Fache ihrer Größe, die Umwandlung 1–2 GB mehr; bei `.3dm` bleibt zusätzlich die Ausgabe bis zum Speichern im Speicher. **Faustregel: eine 2-GB-IFC braucht ca. 14–16 GB RAM.** Ist absehbar zu wenig frei, warnt der Converter vor dem Start, wandelt aber trotzdem um.
- **Geometrie in Paketen:** Die Geometrie wird in Paketen zu 200 Bauteilen berechnet, und der Speicher wird nach jedem Paket wieder freigegeben. Die Zahl der Rechen-Threads passt sich dem freien RAM an.
- **Schneller Geometriekern:** Standard ist IfcOpenShells Hybrid-Kern (CGAL + OpenCASCADE), auf echten Modellen 3–13× schneller als OpenCASCADE allein; Geländemodelle aus Dreiecksnetzen dauern Sekunden statt über 20 Minuten. Bauteile, die er nicht schafft, werden automatisch mit OpenCASCADE nachberechnet. Stürzt er ab, wird die ganze Datei automatisch mit OpenCASCADE wiederholt. Mit `--kernel opencascade` lässt sich OpenCASCADE erzwingen.
- **Eigener Prozess:** Jede Umwandlung läuft in einem eigenen Prozess (im Fenster wie im Terminal). Reicht der Arbeitsspeicher nicht und das System beendet die Umwandlung (oder sie stürzt ab), wird nur diese Datei als Fehler markiert, und die nächste wird umgewandelt. „Abbrechen“ im Fenster wirkt sofort, auch während die IFC-Datei noch gelesen wird. Im Terminal zeigt eine Zeile den Fortschritt in Prozent.
- **Fortschritt:** Das Einlesen großer Dateien dauert einige Minuten. Das Fenster zeigt solange „IFC wird gelesen …“.
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

**Polyflächen bei sehr großen Modellen:** Die Ausgabe wird 1,2–4,5× so groß wie mit Netzen und liegt bis zum Speichern komplett im Arbeitsspeicher (Landsarkivet: 5,7 GB statt 3,7 GB). Für Modelle ab einigen hundert MB ist „Netze“ meist die bessere Wahl; Polyflächen lohnen sich vor allem, wenn in Rhino an Wänden, Decken und Öffnungen weitergearbeitet wird.

### Was der Converter bei fehlerhaften Dateien selbst repariert

- **Zusammengeführte Fachmodelle** mit mehreren `IfcProject` (Architektur + Tragwerk + TGA in einer Datei): IfcOpenShell würde sonst alle Einheiten ignorieren (Fuß als Meter, Grad als Bogenmaß, Öffnungen fehlen). Die Projekte werden im Speicher zusammengeführt, wenn ihre Einheiten übereinstimmen.
- **Falsch deklarierte Einheiten** (z. B. OpenRoads: Fuß ohne Typ, Fläche als Länge) werden korrigiert.
- **Leere Geometrie-Darstellungen** einzelner Bauteile blockieren nicht mehr die Nachbarn.
- **Statik-Analysemodelle** (z. B. RFEM): Knoten, Stabachsen und Lasten werden übersprungen, Flächenbauteile umgewandelt.
- Bauteile, deren Geometrie sich nicht berechnen lässt, werden gezählt und gemeldet („236 Bauteile (3 ohne Geometrie)“). Kommt gar keine Geometrie heraus, gibt es einen Fehler statt einer leeren Datei.
- **Nicht unterstützt:** IFC2X2 (vor 2006) und der Entwurf IFC4X4 (Tunnel) – dafür gibt es eine klare Meldung. Brücken im Zwischenformat IFC4X2 mit `IfcSectionedSolidHorizontal` kann IfcOpenShell nicht berechnen.

### Terminal-Modus (Drag & Drop ins Konsolenfenster)

Die alte Konsolen-Variante gibt es weiterhin: `IFC_CONVERTER_CLI=1 ./start.sh` (Linux/macOS) bzw. `python -m ifc_converter` in der Umgebung. Dort Dateien ins Fenster ziehen, Enter drücken, `3dm`, `glb` oder `obj` eingeben, um das Format zu wechseln, und `q`, um zu beenden.

Voraussetzung: Python 3.10 oder neuer ([python.org](https://www.python.org/downloads/), unter Windows den Haken bei „Add python.exe to PATH“ setzen).

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
- `-o, --output PFAD`: Ausgabedatei (nur bei einer Eingabedatei)
- `-d, --out-dir ORDNER`: Ausgabeordner für mehrere Dateien
- `-j, --threads N`: Anzahl Threads für die Geometrie (Standard: alle Kerne)
- `--kernel {hybrid,opencascade}`: Geometriekern (Standard: `hybrid`, deutlich schneller)

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

## Stresstest mit echten Modellen

`tools/benchmark.py` wandelt IFC-Dateien in allen Formaten um, jede Umwandlung in einem eigenen Prozess, und schreibt Zeit, RAM-Spitze, Ausgabegröße und Prüfungen der Ausgabe (gültige Polyflächen, Attribute, Koordinaten) in einen Bericht:

```bash
python tools/benchmark.py modelle/*.ifc --modes 3dm-brep,3dm-mesh,glb --out-dir out --report bericht.md
```
