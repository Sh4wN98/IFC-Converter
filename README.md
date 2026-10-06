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
  - Wände, Decken, Fenster, Türen usw. werden geschlossene, ebene Polyflächen in Metern.
  - Koplanare Flächen sind zusammengeführt, und Fenster- und Türöffnungen sind echte Löcher in den Flächen.
  - Sehr detaillierte Objekte mit mehr als 1000 Dreiecken (Sanitär, Leuchten, Pflanzen) bleiben Netze, ebenso alles, was keine gültige Polyfläche ergibt.
  - Die Datei wird etwa 3× so groß wie mit Netzen.
- **Geometrie „Netze“:** Jedes Bauteil wird ein Mesh-Objekt. Das ergibt die kleinste Datei und die schnellste Umwandlung.
- **Gekrümmte Flächen:** Rundes bleibt facettiert, weil Revit es schon in der IFC als Dreiecke speichert. Echte NURBS-Flächen erzeugt der Converter nicht.
- Layer: `Geschoss::IfcKlasse`, z. B. `EG::IfcWall`. Bauteile ohne Geschoss landen unter `Ohne Geschoss`.
- Objektname = IFC-Name, Farbe aus dem IFC-Material/-Stil.
- GlobalId, IFC-Klasse und Property-Sets stehen als Benutzertexte (Attribute User Text) am Objekt.
- Die Datei wird im Rhino-7-Format geschrieben und lässt sich damit in Rhino 7 und 8 öffnen.

### Große Modelle (mehrere GB)

- **Arbeitsspeicher:** Die IFC-Datei wird komplett in den Arbeitsspeicher geladen (ca. 3× ihre Größe). Für ein 2-GB-Modell sollten also etwa 10–12 GB RAM frei sein. Ist absehbar zu wenig frei, warnt der Converter vor dem Start, wandelt aber trotzdem um.
- **Geometrie in Paketen:** Die Geometrie wird in Paketen zu 200 Bauteilen berechnet, und der Speicher wird nach jedem Paket wieder freigegeben. Der Bedarf wächst also nicht mit der Modellgröße.
- **Threads:** Die Zahl der Rechen-Threads passt sich dem freien RAM an. Bei wenig Speicher geht es langsamer, statt abzustürzen.
- **Fortschritt:** Das Einlesen großer Dateien dauert einige Minuten. Das Fenster zeigt solange „IFC wird gelesen …“.
- **Richtwert** (gemessen an einem 140-MB-Revit-Modell auf einem Laptop mit 8 Kernen / 8 GB RAM):
  - `.3dm` mit Polyflächen: ca. 8 min, 425 MB Datei, höchstens 3,7 GB RAM;
  - `.3dm` mit Netzen: ca. 7 min, 131 MB Datei;
  - `.glb`: ca. 2,5 min.
- **GLB:** Das Format ist auf 4 GB Ausgabe begrenzt. Für riesige Modelle `.3dm` oder `.obj` nehmen.

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
