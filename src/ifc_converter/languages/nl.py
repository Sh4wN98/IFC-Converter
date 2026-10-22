"""User interface texts: nl (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Tussenstand {name} niet leesbaar ({error}), wordt opnieuw berekend",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Tussenstand kan niet worden opgeslagen ({error}); gaat verder zonder",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Niet-ondersteund formaat “{fmt}”; mogelijk zijn: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Niet-ondersteund geometrietype “{geometry}”; mogelijk zijn: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Onbekende geometriekern “{kernel}”; mogelijk zijn: {kernels}",
    "IFC file not found: {path}": "IFC-bestand niet gevonden: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell kan geen ifcXML-bestanden lezen ({name}). Exporteer het model vanuit het modelleerprogramma "
        "als .ifc (STEP-tekstformaat) of .ifczip.",
    "Reading IFC file ({size}) …": "IFC-bestand wordt gelezen ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "IFC-versie wordt niet ondersteund ({error}). Ondersteund: {supported}; {bridges} worden ook gelezen, als "
        "het dichtstbijzijnde verwante schema.",
    "{note} Dimensions and positions stay unchanged.": "{note} Afmetingen en posities blijven ongewijzigd.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Gebouwschil wordt bepaald (geometrie grof voorberekend) …",
    'The geometry kernel hung on {label} for more than {minutes} min: the element is skipped':
        'De geometriekern loopt al meer dan {minutes} min vast op {label}: het element wordt overgeslagen',
    'The geometry kernel hung on {label} for more than {minutes} min in the rough pre-computation: the element is kept as part of the hull':
        'De geometriekern loopt al meer dan {minutes} min vast op {label} (grove voorberekening): het element blijft als deel van de schil behouden',
    'The geometry kernel hung on one of {count} elements for more than {minutes} min: they are computed one by one …':
        'De geometriekern loopt al meer dan {minutes} min vast op een van {count} elementen: ze worden een voor een berekend …',
    '{count} elements not computed because the geometry kernel hung on their chunk: they are skipped':
        '{count} elementen niet berekend omdat de geometriekern op hun pakket vastliep: ze worden overgeslagen',
    '{count} elements not computed because the geometry kernel hung on their chunk in the rough pre-computation: they are kept as part of the hull':
        '{count} elementen in de grove voorberekening niet berekend omdat de geometriekern op hun pakket vastliep: ze blijven als deel van de schil behouden',
    "Computing geometry ({threads} threads) …": "Geometrie wordt berekend ({threads} threads) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Geen geometrie gemaakt: geen van de {count} elementen met geometrie kon worden geconverteerd "
        "(waarschijnlijk niet-ondersteunde geometrietypen).",
    "The file contains no elements with geometry.": "Het bestand bevat geen elementen met geometrie.",
    "Copying to the target folder ({size}) …": "Wordt naar de doelmap gekopieerd ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Kopiëren mislukt ({error}) – poging {attempt} over {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Wordt naar de doelmap gekopieerd … {copied} van {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Het voltooide bestand kon niet naar {folder} worden gekopieerd ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Het voltooide bestand kon niet naar {folder} worden gekopieerd ({error}). Het staat hier: {path} – "
        "kopieer het handmatig.",
    "{count} extrusions with negative depth turned around": "{count} extrusies met negatieve diepte omgedraaid",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} elementen overgenomen uit de vorige poging, {count} worden berekend",
    "Geometry contains itself (faulty file), not converted: {label}":
        "Geometrie bevat zichzelf (fout bestand), niet geconverteerd: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Diep genest element ({depth} niveaus) {number} van {total} wordt apart berekend: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Element {number} van {total} wordt apart berekend: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} elementen pas in de tweede poging berekend (fijnere tolerantie of andere kern)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Tweede pogingen na {seconds} s beëindigd; verdere elementen zonder geometrie zijn niet meer apart "
        "geprobeerd",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} geometrieberekeningen lopen na {seconds} s nog en worden op de achtergrond beëindigd",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} heeft waarschijnlijk ca. {needed} GB geheugen nodig, er is maar {available} GB vrij. Sluit andere "
        "programma's, anders wordt het erg traag of breekt de conversie af.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grof {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Alleen gebouwschil: Het model heeft geen gesloten schil (dak, vloeren of wanden ontbreken, bijv. een "
        "deelmodel zonder ruwbouw): de buitenlucht bereikt bijna alle elementen (raster {voxel} m). In plaats "
        "daarvan weggelaten: {marked} als binnen gemarkeerde elementen (IsExternal = Nee) en {fittings} meubels, "
        "inrichting, leidingen en kanalen, plafond- en vloerafwerkingen; {kept} van {total} elementen worden "
        "geconverteerd.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Alleen gebouwschil: {kept} van {total} elementen liggen buiten en worden geconverteerd, {inside} "
        "binnenliggende weggelaten (raster {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} zonder voorberekende geometrie voor de zekerheid overgenomen",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} als buiten gemarkeerd (IsExternal) overgenomen",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} massavolumes (omhullende lichamen rond het model) niet als ondoorzichtig geteld",
    "{count} more": "{count} meer",
    " Left out: {classes}.": " Weggelaten: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Gebouwschil wordt bepaald (buitenlucht wordt gezocht) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Gebouwschil: {kept} van {total} elementen buiten ({unknown} zonder voorberekende geometrie, {flagged} via "
        "IsExternal), raster {voxel} m (grof {coarse} m, {cells} cellen, fijne rand {band} cellen), voorberekende "
        "geometrie {coarse_seconds} s, schil {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Gebouwschil: raster vergrofd tot {voxel} m ({cells} rastercellen opgeslagen)",
    # preview.py
    "Saving preview ({count} triangles) …": "Voorbeeld wordt opgeslagen ({count} driehoeken) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Te veel driehoeken voor het voorbeeld (meer dan {limit} per element).",
    "furniture": "meubilair",
    "MEP": "installaties",
    "fasteners": "bevestigingen",
    "reinforcement": "wapening",
    "deeply nested": "diep genest",
    # process.py
    "stack overflow": "stackoverflow",
    "The memory was not enough (the process was ended by the system)":
        "Het geheugen was niet toereikend (het proces is door het systeem beëindigd)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Crash in de snelle geometriekern – nieuwe poging met alleen OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Crash in de geometriekern ({fatal}), waarna de conversie vastliep",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "De conversie heeft {duration} lang niets meer berekend (ze liep vast)",
    "{count} minutes": "{count} minuten",
    "{count} seconds": "{count} seconden",
    "stack overflow in the geometry kernel": "stackoverflow in de geometriekern",
    "memory access violation": "geheugentoegangsfout",
    "internal program abort": "interne programma-afbreking",
    "Conversion ended without a result": "Conversie beëindigd zonder resultaat",
    "Conversion crashed: {name} (code {code})": "Conversie gecrasht: {name} (code {code})",
    "Conversion crashed (code {code})": "Conversie gecrasht (code {code})",
    "Crash in the geometry kernel ({fatal})": "Crash in de geometriekern ({fatal})",
    "Hang in the geometry kernel": "Vastloper in de geometriekern",
    "Crash in the geometry kernel": "Crash in de geometriekern",
    "New attempt ({attempt}. of at most {max})": "Nieuwe poging ({attempt} van maximaal {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} bij de assen (IfcAlignment, IfcGrid). {again} zonder de assen …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} bij {label}. {again}, dit element wordt overgeslagen …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} bij één element. {again}, het wordt eerst en apart berekend …",
    "{what} in the hull's rough pre-computation. {again} with OpenCASCADE for the pre-computation …":
        '{what} in de voorberekening van de schil. {again} met OpenCASCADE voor de voorberekening …',
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} bij een van {count} elementen. {again}, deze worden eerst en apart berekend om het betreffende "
        "element te vinden …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Conversie: {input} ({size}) -> {output}, formaat {fmt}, {threads} threads{options}{priority}",
    "(next to the IFC file)": "(naast het IFC-bestand)",
    ", normal priority": ", normale prioriteit",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Bekend uit eerdere conversies van dit bestand, wordt overgeslagen (de geometriekern crashte erop of liep "
        "vast) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", al berekende elementen worden overgenomen …",
    " (exit code {code})": " (exitcode {code})",
    "Cancelled after {seconds} s: {path}": "Geannuleerd na {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Fout na {seconds} s bij {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Crash na {seconds} s bij {path}: {error} (exitcode {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Vastgelopen, geannuleerd na {seconds} s: {path}",
    "Conversion of {path} failed": "Conversie van {path} mislukt",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Klaar na {seconds} s: {input} -> {output}, {elements} elementen, {missing} zonder geometrie, {skipped} "
        "overgeslagen",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Overgeslagen omdat de geometriekern erop crashte of vastliep ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Zonder geometrie ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … en {count} meer",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Te weinig ruimte in de tijdelijke map voor een tussenstand; na een crash wordt alles opnieuw berekend",
    "size unknown": "grootte onbekend",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Geheugenlimiet van het conversieproces ({limit} GB) bereikt",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Geheugenlimiet van het conversieproces ({limit} GB) bereikt, de conversie is toch tot het einde gelopen "
        "(bijv. zonder hulpprocessen)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "Het geheugen was niet toereikend: De conversie mag maximaal {limit} GB gebruiken ({share} % van het "
        "geheugen), zodat andere programma's blijven draaien. Voor dit bestand heeft de pc meer geheugen nodig.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Jobobject voor de conversie niet beschikbaar ({error}), gaat verder zonder geheugenlimiet",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Conversieproces niet in het jobobject ({error}), gaat verder zonder geheugenlimiet",
    "Skipped elements could not be saved ({path}): {error}":
        "Overgeslagen elementen konden niet worden opgeslagen ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (na {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "Loopt al {seconds} s, {percent} %: {message}",
    "{message}: {size} written …": "{message}: {size} geschreven …",
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message}':
        'Al {minutes} min geen voortgang hoewel de omzetting rekent (CPU {cpu} s), {percent} %: {message}',
    'The conversion has made no progress for {duration} although it is computing (the geometry kernel hangs)':
        'De omzetting heeft al {duration} geen voortgang gemaakt hoewel ze rekent (de geometriekern hangt)',
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message} – the geometry kernel hangs, the conversion is restarted':
        'Al {minutes} min geen voortgang hoewel de omzetting rekent (CPU {cpu} s), {percent} %: {message} – de geometriekern hangt, de omzetting wordt opnieuw gestart',
    '{count} elements of the chunk are computed again together, without the ones the geometry kernel hung on …':
        '{count} elementen van het pakket worden opnieuw samen berekend, zonder de elementen waarop de geometriekern bleef hangen …',
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Geen rekenactiviteit sinds {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
    " after {fatal}": " na {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "Het conversieproces meldt een fatale fout: {marker}",
    " (last {shown} KB of {size} KB)": " (laatste {shown} KB van {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Uitvoer van het conversieproces{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Het conversieproces {pid} kon niet worden beëindigd",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "Rhino-geometrie liet een hulpproces crashen, in plaats daarvan als mesh overgenomen: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "Rhino-geometrie liet een hulpproces crashen, element weggelaten: {label}",
    "Writing Rhino file ({count} objects) …": "Rhino-bestand wordt geschreven ({count} objecten) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) wordt gelezen als IFC2x3, dat zijn entiteiten en attributen heeft overgenomen.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 is een niet-gepubliceerd ontwerp (tunnels) en wordt gelezen als IFC4.3: IfcTunnel als "
        "IfcFacility, IfcTunnelPart als IfcFacilityPart, IfcUndergroundExcavation en IfcArchElement als "
        "IfcBuildingElementProxy; datasetverwijzingen (IfcDataSetInformation) vervallen.",
    "IFC4x4 (draft)": "IFC4x4 (ontwerp)",
    "{count} entities renamed": "{count} entiteiten hernoemd",
    "{count} left out": "{count} weggelaten",
    # serializers.py
    "Writing GLB file …": "GLB-bestand wordt geschreven …",
    "Writing OBJ file …": "OBJ-bestand wordt geschreven …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "STEP-bestand wordt geschreven (exacte vlakken, duurt bij grote modellen minuten) …",
    "Writing DAE file …": "DAE-bestand wordt geschreven …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Het {fmt}-bestand kon niet worden geschreven: de serializer heeft geen van de {count} elementen "
        "overgenomen.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Deze elementen hebben geometrie die niet kon worden geconverteerd – bijv. niet-ondersteunde "
        "geometrietypen, of hun openingen snijden ze volledig weg.",
    "1 element without geometry": "1 element zonder geometrie",
    "{count} elements without geometry": "{count} elementen zonder geometrie",
    " … and {count} more (all of them in the log file)": " … en {count} meer (alle in het logbestand)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 element overgeslagen omdat de geometriekern erop crashte of vastliep: {names}{more}. "
        "In het CAD-programma is het te vinden via de GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} elementen overgeslagen omdat de geometriekern erop crashte of vastliep: {names}{more}. "
        "In het CAD-programma zijn ze te vinden via hun GlobalId.",
    "There was not enough memory": "Er was niet genoeg geheugen",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Het bestand kon niet als IFC worden gelezen (beschadigd of geen IFC-bestand): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Het bestand kon niet als IFC worden gelezen (beschadigd of geen IFC-bestand)",
    "File or network error: {message}": "Bestands- of netwerkfout: {message}",
    "Internal error ({name}): {message}": "Interne fout ({name}): {message}",
    "Internal error ({name})": "Interne fout ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Voeg het logbestand ({log}) bij wanneer u de fout meldt.",
    "Details are in the log file ({log}).": "Details staan in het logbestand ({log}).",
    "up to 1 thread (of {cores} logical cores)": "maximaal 1 thread (van {cores} logische kernen)",
    "up to {threads} threads (of {cores} logical cores)": "maximaal {threads} threads (van {cores} logische kernen)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, plus maximaal {workers} hulpprocessen voor de Rhino-geometrie bij grote 3DM-modellen",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, lage prioriteit – andere programma's gaan voor",
    "{threads_text}, normal priority": "{threads_text}, normale prioriteit",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} u {minutes} min",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 binnenliggend element weggelaten",
    "{count} interior elements left out": "{count} binnenliggende elementen weggelaten",
    # app.py
    "not available": "niet beschikbaar",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<gebruiker>",
    "<computer>": "<computer>",
    "<server>": "<server>",
    "<share>": "<share>",
    "<folder>": "<map>",
    "File": "Bestand",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Nauwkeurig (aanbevolen)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Elk element volledig en bij elke run hetzelfde; alleen grote driehoeksmeshes (terrein) gaan naar de "
        "snelle kern, die ze ongewijzigd overneemt.",
    "Fast": "Snel",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3 tot 13 keer sneller, maar kan bij sommige elementen vlakken weglaten of dubbel maken.",
    "OpenCASCADE only": "Alleen OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Alles met OpenCASCADE, ook terreinmodellen: daar erg traag (meer dan 20 minuten voor een groot terrein).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Vervangt gebruikers- en computernamen, servers en shares van netwerkschijven, mapnamen (<map>) en "
        "bestandsnamen (Bestand-1.ifc, Bestand-1.3dm …) en laat elementnamen weg. IFC-klasse en GlobalId, "
        "tijden, groottes, versies en foutmeldingen blijven behouden.",
    "There is no log file yet in {folder}.": "Er is nog geen logbestand in {folder}.",
    "Text files (*.txt);;All files (*)": "Tekstbestanden (*.txt);;Alle bestanden (*)",
    # dialogs.py: settings
    "Settings": "Instellingen",
    "Performance": "Prestaties",
    "Geometry kernel": "Geometriekern",
    "Output": "Uitvoer",
    "Log file": "Logbestand",
    "OK": "OK",
    "Apply and save the settings": "Instellingen toepassen en opslaan",
    "Cancel": "Annuleren",
    "Discard changes": "Wijzigingen verwerpen",
    "Defaults": "Standaard",
    "Reset all settings to their defaults": "Alle instellingen terugzetten naar de standaardwaarden",
    "At most this many threads:": "Maximaal zoveel threads:",
    "Automatic ({threads})": "Automatisch ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 of “Automatisch” laat enkele kernen vrij en neemt er minder bij weinig vrij RAM.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Zoveel processorkernen berekenen de geometrie tegelijk. Minder threads remmen andere programma's "
        "minder af, maar de conversie duurt langer. “Automatisch” gebruikt maximaal {threads} van de {cores} "
        "logische kernen van deze pc (ongeveer de helft, inclusief de hulpprocessen van de Rhino-uitvoer) en "
        "minder bij weinig vrij RAM; elke thread kan bij grote elementen tot ca. 1 GB nodig hebben.",
    "Convert at low priority (recommended)": "Converteren met lage prioriteit (aanbevolen)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "De conversie draait met de Windows-prioriteit “Lager dan normaal”: Rhino, Revit en dergelijke gaan "
        "voor en blijven vlot reageren; de conversie gebruikt alleen de rekentijd die zij overlaten. Zonder "
        "deze instelling concurreert ze op gelijke voet met hen.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Waarmee de geometrie van de elementen wordt berekend. Geldt voor alle uitvoerformaten.",
    "Open the output folder after the conversion": "Uitvoermap openen na de conversie",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Opent de map in de Verkenner zodra alle bestanden zijn geconverteerd.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Bestaande bestanden worden nooit overschreven – bestaat de naam al, dan wordt (2), (3) … "
        "toegevoegd. De IFC-bestanden zelf worden nooit gewijzigd.",
    "Identical elements as blocks (smaller file)": "Identieke elementen als blokken (kleiner bestand)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Elementen met dezelfde typegeometrie (ramen, deuren, meubels …) worden instanties van een Rhino-blok.\n"
        "Het bestand wordt kleiner, maar blokinstanties gedragen zich anders dan normale objecten:\n"
        "Om de geometrie te bewerken moet een instantie eerst worden geëxplodeerd (_Explode).\n"
        "Gebruikersteksten, laag en kleur staan op de instantie.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "Typegeometrie die meerdere elementen delen (ramen, deuren, meubels …) wordt één keer als blok "
        "opgeslagen en per element als instantie ingevoegd: bestand 20–45 % kleiner. Om die in Rhino te "
        "bewerken moet een blokinstantie eerst worden geëxplodeerd (_Explode).",
    "Log file:": "Logbestand:",
    "Settings:": "Instellingen:",
    "With this, a conversion uses {resources}.": "Een conversie gebruikt hiermee {resources}.",
    # dialogs.py: about
    "About {app}": "Over {app}",
    "Version {version}": "Versie {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Converteert IFC-gebouwmodellen naar Rhino-bestanden (3DM), GLB en OBJ. Draait volledig lokaal: "
        "geen internetverbinding, geen telemetrie, geen automatische updates.",
    "Components": "Componenten",
    "Component": "Component",
    "Version": "Versie",
    "Licence": "Licentie",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "De bibliotheken zijn ongewijzigd opgenomen. De volledige licentieteksten staan in de programmamap "
        "in THIRD-PARTY-NOTICES.txt en in de map “licenses”.",
    "Source code:": "Broncode:",
    "Copy version info": "Versie-info kopiëren",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Kopieert de programma- en componentversies als tekst, bijv. voor een foutmelding.",
    "Close": "Sluiten",
    "Copied ✓": "Gekopieerd ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Onverwachte fout",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Er is een onverwachte fout opgetreden.</b><br>"
        "Het programma blijft draaien. Als iets niet meer werkt, start het dan opnieuw.<br>"
        "Om het probleem te melden, kopieer de details en stuur ze mee.",
    "Copy details": "Details kopiëren",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Overgeslagen (kerncrash)",
    "Without geometry": "Zonder geometrie",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Zo vindt u een element in het CAD-programma: kopieer de GlobalId en zoek ernaar – in ArchiCAD met "
        "“Zoeken & selecteren” (Ctrl+F) op de IFC-eigenschap GlobalId of “Archicad IFC ID”, in Revit op de "
        "parameter “IfcGUID” (bijv. in een lijst of met een filter), anders in elke IFC-viewer.",
    "Reason": "Reden",
    "Class": "Klasse",
    "GlobalId": "GlobalId",
    "Name": "Naam",
    "Skipped elements – {file}": "Overgeslagen elementen – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} overgeslagen omdat de geometriekern erop crashte of vastliep",
    "{count} without geometry (not convertible)": "{count} zonder geometrie (niet converteerbaar)",
    "{inside} (building hull only)": "{inside} (alleen gebouwschil)",
    "Copy": "Kopiëren",
    "{count} more elements without geometry could not be named individually.":
        "{count} andere elementen zonder geometrie konden niet afzonderlijk worden benoemd.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "De binnenliggende elementen die vanwege “Alleen gebouwschil” zijn weggelaten, worden niet "
        "afzonderlijk vermeld; zonder de optie worden ze ook geconverteerd.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Selecteren en Ctrl+C kopieert de gekozen rijen (Ctrl+A: alle), als tabel om in Excel of een e-mail "
        "te plakken.",
    "Copy all": "Alles kopiëren",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Kopieert de hele tabel, om in Excel of een e-mail te plakken.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Rhino-bestand (.3dm) – direct in Rhino openen en verder bewerken.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binair (.glb) – compact, voor webviewers, Blender, Three.js en game-engines.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – is in vrijwel elk 3D-programma te openen.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – driehoeksmeshes met kleuren, voor SketchUp, Blender, Unity en ArchiCAD. Tekstbestand, ongeveer twee keer zo groot als .glb.",
    "Polysurfaces (recommended)": "Polyoppervlakken (aanbevolen)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Wanden, vloeren, ramen … als gesloten polyoppervlakken met echte openingen. Zeer gedetailleerde objecten (meubels, sanitair, verlichting) blijven meshes. Het bestand is afhankelijk van het model 1,2–4,5× groter – kies bij zeer grote modellen liever “Meshes”.",
    "Meshes": "Meshes",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "Kleinste bestanden, snelste conversie. Gebogen vlakken glad geschaduwd, randen scherp.",
    "Only the building hull": "Alleen de gebouwschil",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Converteert alleen de gebouwschil, dus wat van buiten te zien is: buitenwanden, daken, ramen, deuren, balkons, terrein … Binnenwanden, meubels, inrichting, leidingen en kanalen worden weggelaten; het bestand wordt veel kleiner (bijv. voor omgevingsmodellen of zwakkere pc's).\n\nHiervoor berekent een korte extra stap eerst een grove geometrie van alle elementen (de eerste 25 % van de voortgang). Elementen die in de IFC als buiten gemarkeerd zijn (IsExternal) blijven altijd behouden; bij twijfel wordt een element eerder behouden dan weggelaten. Afmetingen en posities van de geconverteerde elementen veranderen niet. Geldt voor elk uitvoerformaat.",
    "Reading IFC …": "IFC wordt gelezen …",
    "Converting … {percent}% – {detail}": "Converteren … {percent} % – {detail}",
    "Converting … {percent}%": "Converteren … {percent} %",
    "{count} without geometry": "{count} zonder geometrie",
    "Done – {elements}": "Klaar – {elements}",
    "Error: {error}": "Fout: {error}",
    "Cancelled": "Geannuleerd",
    "Queued – starts afterwards": "In wachtrij – start daarna",
    "Waiting": "Wacht",
    "1 file": "1 bestand",
    "{count} files": "{count} bestanden",
    "1 element": "1 element",
    "{count} elements": "{count} elementen",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Klik om het bestandsvenster te openen (Ctrl+O). Mappen worden doorzocht op .ifc-bestanden.",
    "Drop IFC files or folders here": "Sleep IFC-bestanden of mappen hierheen",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Mappen worden doorzocht op .ifc- en .ifczip-bestanden – ook meerdere tegelijk",
    "Add files…": "Bestanden toevoegen…",
    "Size": "Grootte",
    "Status": "Status",
    "Convert IFC building models to 3D formats": "IFC-gebouwmodellen naar 3D-formaten converteren",
    "Double-click a finished file to open its output folder; right-click for more.": "Dubbelklik op een voltooid bestand om de uitvoermap te openen; rechtsklik voor meer.",
    "Remove": "Verwijderen",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Geselecteerde bestanden uit de lijst halen (Del). De bestanden zelf blijven onaangeroerd.",
    "Clear list": "Lijst wissen",
    "Take all files off the list.": "Alle bestanden uit de lijst halen.",
    "Skipped elements…": "Overgeslagen elementen…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Toont de elementen van het geselecteerde bestand die niet zijn geconverteerd, met klasse, GlobalId en naam (ook via rechtsklik op de rij).",
    "Drag to divide the room between list and preview": "Slepen: ruimte verdelen tussen lijst en voorbeeld",
    "Output format": "Uitvoerformaat",
    "Output folder": "Uitvoermap",
    "Change…": "Wijzigen…",
    "Save next to the IFC file": "Naast het IFC-bestand opslaan",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Bestaande bestanden worden nooit overschreven: bestaat de naam al, dan wordt (2), (3) … toegevoegd.",
    "Choose the output folder.": "Uitvoermap kiezen.",
    "Each file goes into the folder of its IFC file.": "Elk bestand komt in de map van zijn IFC-bestand.",
    "Ready": "Gereed",
    "Progress over all files in the list": "Voortgang over alle bestanden in de lijst",
    "Log – here you can see what happened to each file.": "Logboek – hier ziet u wat er met elk bestand is gebeurd.",
    "Drag to enlarge or shrink the log": "Slepen: logboek vergroten of verkleinen",
    "Log": "Logboek",
    "Show or hide the log (F4)": "Logboek tonen of verbergen (F4)",
    "Open output folder": "Uitvoermap openen",
    "Opens the folder of the file written last.": "Opent de map van het laatst geschreven bestand.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Lopende conversie annuleren. Voltooide bestanden blijven, het bestand in bewerking wordt verwijderd.",
    "Convert": "Converteren",
    "Convert all files in the list (Ctrl+Enter)": "Alle bestanden in de lijst converteren (Ctrl+Enter)",
    "Add folder…": "Map toevoegen…",
    "Quit": "Afsluiten",
    "Settings…": "Instellingen…",
    "Preview": "Voorbeeld",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "IFC-bestanden kiezen (Ctrl+O). Mappen: Bestand → Map toevoegen…",
    "&File": "&Bestand",
    "&Edit": "Be&werken",
    "&View": "Beel&d",
    "&Tools": "E&xtra",
    "&Help": "&Help",
    "Language": "Taal",
    "The user interface switches to {language} when the program is restarted. Restart now?": "De gebruikersinterface schakelt over naar {language} wanneer het programma opnieuw wordt gestart. Nu opnieuw starten?",
    "Restart now": "Nu opnieuw starten",
    "Later": "Later",
    "Geometry": "Geometrie",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Uitvoermap: {path}\n\nBestaande bestanden worden nooit overschreven: (2), (3) … wordt toegevoegd.",
    "Choose output folder": "Uitvoermap kiezen",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ Geen IFC-bestand gevonden: {path} – alleen .ifc- en .ifczip-bestanden en mappen daarmee (ifcXML kan niet worden gelezen)",
    "• Already in the list: {names}": "• Al in de lijst: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} in wachtrij: wordt direct na de lopende batch geconverteerd, met dezelfde instellingen.",
    "+ {files} added": "+ {files} toegevoegd",
    "Add IFC files": "IFC-bestanden toevoegen",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "IFC-bestanden (*.ifc *.IFC *.ifczip *.ifcZIP);;Alle bestanden (*)",
    "Add a folder with IFC files": "Map met IFC-bestanden toevoegen",
    "Written: {path}": "Geschreven: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} overgeslagen (geometriekern gecrasht of vastgelopen)",
    "Only the building hull: {inside} (interior elements)": "Alleen gebouwschil: {inside} (binnenliggende elementen)",
    "List to copy: right-click → “Skipped elements…”": "Lijst om te kopiëren: rechtsklik → “Overgeslagen elementen…”",
    "The output folder cannot be created:\n{error}": "De uitvoermap kan niet worden aangemaakt:\n{error}",
    "next to the IFC files": "naast de IFC-bestanden",
    "identical elements as blocks": "identieke elementen als blokken",
    "only the building hull": "alleen gebouwschil",
    "output: {target}": "uitvoer: {target}",
    "geometry kernel {kernel}": "geometriekern {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Rekenkracht: {resources}",
    "Conversion running …": "Conversie loopt …",
    "Cancelling …": "Wordt geannuleerd …",
    "■ Cancel requested": "■ Annulering aangevraagd",
    "Reading IFC ({size}) – may take a few minutes …": "IFC wordt gelezen ({size}) – kan enkele minuten duren …",
    "{file}: new attempt – reading IFC …": "{file}: nieuwe poging – IFC wordt gelezen …",
    "Converting {file} …": "{file} wordt geconverteerd …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Lijst om te kopiëren: rechtsklik op het bestand → “Overgeslagen elementen…”",
    "✗ Error in {file}: {error}": "✗ Fout in {file}: {error}",
    "{done} of {files} done": "{done} van {files} klaar",
    "{count} with errors": "{count} met fouten",
    "cancelled": "geannuleerd",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 bestand in wachtrij niet geconverteerd – “Converteren” start het.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} bestanden in wachtrij niet geconverteerd – “Converteren” start ze.",
    "▶ Continuing with {files}, added during the conversion": "▶ Verder met {files}, toegevoegd tijdens de conversie",
    "Cancelled after {duration}": "Geannuleerd na {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ {done} klaar, {failed} met fouten – na {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} met fouten – na {duration}",
    "Error": "Fout",
    "✓ Done after {duration}": "✓ Klaar na {duration}",
    "✓ Done": "✓ Klaar",
    "{done} of {files} done – %p%": "{done} van {files} klaar – %p %",
    "✗ The output folder does not exist (yet): {path}": "✗ De uitvoermap bestaat (nog) niet: {path}",
    "Add files and click “Convert”.": "Voeg bestanden toe, klik “Converteren”.",
    "The conversion is still running.": "De conversie loopt nog.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "“{file}” wordt geconverteerd; de conversie loopt al {since} ({percent} %).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Afsluiten annuleert de conversie en de voortgang gaat verloren. Toch afsluiten?",
    "Select a file in the list – its preview appears here.": "Selecteer een bestand in de lijst – het voorbeeld verschijnt hier.",
    "The 3D view is not available on this PC.": "De 3D-weergave is op deze pc niet beschikbaar.",
    "Compute preview": "Voorbeeld berekenen",
    "Computes the preview of this file now (low priority, at most 8 threads, 4 while a conversion runs); it is kept for next time.":
        "Berekent het voorbeeld van dit bestand nu (lage prioriteit, hoogstens 8 threads, 4 tijdens een conversie); het wordt bewaard voor de volgende keer.",
    "Stop computing the preview": "Berekening van het voorbeeld stoppen",
    "Reset view": "Weergave herstellen",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Beginweergave: het hele model schuin vanuit het zuidwesten (Home; dubbelklik: hele model)",
    "Preview – {file}": "Voorbeeld – {file}",
    "Computing preview …": "Voorbeeld wordt berekend …",
    "No preview possible: {error}": "Geen voorbeeld mogelijk: {error}",
    "The file is not (or no longer) accessible.": "Het bestand is niet (meer) toegankelijk.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Tijdens een conversie wordt geen voorbeeld berekend, om die niet te vertragen.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Groot bestand ({size}): het voorbeeld duurt enkele minuten. Het draait met lage prioriteit en wordt bewaard voor de volgende keer.",
    "Waiting for the running preview to finish …": "Wacht tot het lopende voorbeeld klaar is …",
    "Computing preview: reading the IFC file …": "Voorbeeld wordt berekend: IFC-bestand wordt gelezen …",
    "Loading preview …": "Voorbeeld wordt geladen …",
    "Preview cancelled.": "Voorbeeld geannuleerd.",
    "No preview possible: the geometry kernel crashed repeatedly.":
        "Geen voorbeeld mogelijk: de geometriekernel is herhaaldelijk vastgelopen.",
    "Preview cancelled – incomplete":
        "Voorbeeld geannuleerd – onvolledig",
    "Preview incomplete (the geometry kernel crashed repeatedly)":
        "Voorbeeld onvolledig (de geometriekernel is herhaaldelijk vastgelopen)",
    "Preview incomplete: {error}":
        "Voorbeeld onvolledig: {error}",
    "Preview incomplete so far (the geometry kernel crashed), computing the rest …":
        "Voorbeeld tot nu toe onvolledig (de geometriekernel is vastgelopen), de rest wordt berekend …",
    "{count} of {total} elements so far":
        "tot nu toe {count} van {total} elementen",
    "{count} details left out ({kinds})":
        "{count} details weggelaten ({kinds})",
    "The preview could not be loaded.": "Het voorbeeld kon niet worden geladen.",
    "The file contains no geometry that can be shown.": "Het bestand bevat geen geometrie die kan worden getoond.",
    "Computing preview … {percent}%": "Voorbeeld wordt berekend … {percent} %",
    "Preview: {status}": "Voorbeeld: {status}",
    "Try again": "Opnieuw proberen",
    "{count} small elements left out": "{count} kleine elementen weggelaten",
    "Renderer: {renderer}": "Renderer: {renderer}",
    "Click an element to see its class, GlobalId and name": "Klik op een element om klasse, GlobalId en naam te zien",
    "Iso": "Iso",
    "Isometric view from the south-west (1)": "Isometrie vanuit het zuidwesten (1)",
    "Top": "Boven",
    "Plan view, north up (2)": "Bovenaanzicht, noorden boven (2)",
    "Front": "Voor",
    "View from the south (3)": "Aanzicht vanuit het zuiden (3)",
    "Side": "Zij",
    "View from the east (4)": "Aanzicht vanuit het oosten (4)",
    "Show the whole model (F, double-click)": "Hele model tonen (F, dubbelklik)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "Het bestand bevat {count} projecten met verschillende eenheden; alle worden gelezen met de eenheden van het eerste ({name}). Controleer de afmetingen.",
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} wordt gelezen als {target} (hetzelfde schema onder een andere naam).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Te weinig vrije ruimte in de tijdelijke map voor een werkkopie van het bestand ({needed} nodig, {free} vrij).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'Het IFC-bestand lijkt afgekapt (geen END-ISO-10303-21 aan het einde): de uitvoer kan onvolledig zijn.',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "Kan niet schrijven naar de uitvoermap {folder} ({error})",
    "Show edges (E)": "Randen tonen (E)",
    "Parallel projection instead of perspective (P)": "Parallelprojectie in plaats van perspectief (P)",
    # log file (always anonymised, one option: save)
    "Help → Save log file…": "Help → Logbestand opslaan…",
    "Save log file": "Logbestand opslaan",
    "The log file could not be saved:\n{error}": "Het logbestand kon niet worden opgeslagen:\n{error}",
    "The log file has been saved:\n{path}\n\n{hint}\n\nPlease look through it briefly before sending. Open the folder now?": "Het logbestand is opgeslagen:\n{path}\n\n{hint}\n\nKijk het even door voor het verzenden. Map nu openen?",
    "Save log…": "Log opslaan…",
    "The log file stays on this PC; nothing is sent automatically. It contains no user, computer, server, folder, file or element names.": "Het logbestand blijft op deze pc; er wordt niets automatisch verzonden. Het bevat geen gebruikers-, computer-, server-, map-, bestands- of elementnamen.",
    "Log of this session. Everything is also in the log file (Help → Save log file…).": "Log van deze sessie. Alles staat ook in het logbestand (Help → Logbestand opslaan…).",
    "Save log file…": "Logbestand opslaan…",
}
