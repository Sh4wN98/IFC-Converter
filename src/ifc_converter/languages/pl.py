"""User interface texts: pl (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Punkt kontrolny {name} nieczytelny ({error}), obliczanie od nowa",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Nie można zapisać punktu kontrolnego ({error}); kontynuacja bez niego",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Nieobsługiwany format „{fmt}”; dostępne formaty: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Nieobsługiwany rodzaj geometrii „{geometry}”; dostępne rodzaje: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Nieznane jądro geometrii „{kernel}”; dostępne jądra: {kernels}",
    "IFC file not found: {path}": "Nie znaleziono pliku IFC: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell nie odczytuje plików ifcXML ({name}). Proszę wyeksportować model z programu autorskiego "
        "jako .ifc (format tekstowy STEP) lub .ifczip.",
    "Reading IFC file ({size}) …": "Odczyt pliku IFC ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "Wersja IFC nie jest obsługiwana ({error}). Obsługiwane: {supported}; {bridges} są też odczytywane jako "
        "najbliższy pokrewny schemat.",
    "{note} Dimensions and positions stay unchanged.": "{note} Wymiary i położenie pozostają bez zmian.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Wyznaczanie powłoki budynku (zgrubne obliczenie geometrii) …",
    'The geometry kernel hung on {label} for more than {minutes} min: the element is skipped':
        'Jądro geometrii od ponad {minutes} min wisi na {label}: element zostaje pominięty',
    'The geometry kernel hung on {label} for more than {minutes} min in the rough pre-computation: the element is kept as part of the hull':
        'Jądro geometrii od ponad {minutes} min wisi na {label} (zgrubne obliczenie wstępne): element zostaje zachowany jako część powłoki',
    'The geometry kernel hung on one of {count} elements for more than {minutes} min: they are computed one by one …':
        'Jądro geometrii od ponad {minutes} min wisi na jednym z {count} elementów: są obliczane pojedynczo …',
    '{count} elements not computed because the geometry kernel hung on their chunk: they are skipped':
        '{count} elementów nie obliczono, bo jądro geometrii zawiesiło się na ich pakiecie: zostają pominięte',
    '{count} elements not computed because the geometry kernel hung on their chunk in the rough pre-computation: they are kept as part of the hull':
        '{count} elementów nie obliczono w zgrubnym obliczeniu wstępnym, bo jądro geometrii zawiesiło się na ich pakiecie: zostają zachowane jako część powłoki',
    "Computing geometry ({threads} threads) …": "Obliczanie geometrii (wątki: {threads}) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Nie utworzono geometrii: żadnego z {count} elementów z geometrią nie udało się skonwertować "
        "(prawdopodobnie nieobsługiwane typy geometrii).",
    "The file contains no elements with geometry.": "Plik nie zawiera elementów z geometrią.",
    "Copying to the target folder ({size}) …": "Kopiowanie do folderu docelowego ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Kopiowanie nie powiodło się ({error}) – próba {attempt} za {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "Kopiowanie do folderu docelowego … {copied} z {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Nie udało się skopiować gotowego pliku do {folder} ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Nie udało się skopiować gotowego pliku do {folder} ({error}). Znajduje się tutaj: {path} – proszę "
        "skopiować go ręcznie.",
    "{count} extrusions with negative depth turned around": "Odwrócono {count} wyciągnięć o ujemnej głębokości",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "Przejęto {finished} elementów z poprzedniej próby, obliczanych jest {count}",
    "Geometry contains itself (faulty file), not converted: {label}":
        "Geometria zawiera samą siebie (wadliwy plik), nie skonwertowano: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Głęboko zagnieżdżony element (poziomów: {depth}) {number} z {total} jest obliczany osobno: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Element {number} z {total} jest obliczany osobno: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} elementów obliczono dopiero w drugiej próbie (dokładniejsza tolerancja lub inne jądro)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Drugie próby zakończono po {seconds} s; kolejnych elementów bez geometrii nie próbowano już obliczać "
        "osobno",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} obliczeń geometrii nadal trwa po {seconds} s; zostaną zakończone w tle",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} będzie potrzebować ok. {needed} GB pamięci, wolne jest tylko {available} GB. Proszę zamknąć inne "
        "programy, inaczej konwersja będzie bardzo wolna lub zostanie przerwana.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, zgrubnie {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Tylko powłoka budynku: Model nie ma zamkniętej powłoki (brak dachu, stropów lub ścian, np. model "
        "częściowy bez stanu surowego): powietrze zewnętrzne dociera do niemal wszystkich elementów (siatka "
        "{voxel} m). Zamiast tego pominięto: {marked} elementów oznaczonych jako wewnętrzne (IsExternal = Nie) "
        "oraz {fittings} mebli, wyposażenia, rur i kanałów, okładzin sufitów i podłóg; konwertowanych jest {kept} "
        "z {total} elementów.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Tylko powłoka budynku: {kept} z {total} elementów leży na zewnątrz i jest konwertowanych, pominięto "
        "{inside} wewnętrznych (siatka {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} bez wstępnie obliczonej geometrii przejęto dla bezpieczeństwa",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} oznaczonych jako zewnętrzne (IsExternal) przejęto",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} brył masowych (obrysów wokół modelu) nie uznano za nieprzezroczyste",
    "{count} more": "jeszcze {count}",
    " Left out: {classes}.": " Pominięto: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Wyznaczanie powłoki budynku (szukanie powietrza zewnętrznego) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Powłoka budynku: {kept} z {total} elementów na zewnątrz ({unknown} bez wstępnej geometrii, {flagged} wg "
        "IsExternal), siatka {voxel} m (zgrubna {coarse} m, komórek: {cells}, drobny pas: {band} komórek), "
        "wstępna geometria {coarse_seconds} s, powłoka {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Powłoka budynku: siatkę zgrubiono do {voxel} m (zapisanych komórek: {cells})",
    # preview.py
    "Saving preview ({count} triangles) …": "Zapisywanie podglądu (trójkątów: {count}) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Za dużo trójkątów do podglądu (ponad {limit} na element).",
    "furniture": "meble",
    "MEP": "instalacje",
    "fasteners": "łączniki",
    "reinforcement": "zbrojenie",
    "deeply nested": "głęboko zagnieżdżone",
    # process.py
    "stack overflow": "przepełnienie stosu",
    "The memory was not enough (the process was ended by the system)":
        "Zabrakło pamięci (proces został zakończony przez system)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Awaria szybkiego jądra geometrii – ponowna próba tylko z OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Awaria jądra geometrii ({fatal}), po której konwersja się zawiesiła",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "Konwersja nic nie obliczyła przez {duration} (zawiesiła się)",
    "{count} minutes": "{count} min",
    "{count} seconds": "{count} s",
    "stack overflow in the geometry kernel": "przepełnienie stosu w jądrze geometrii",
    "memory access violation": "naruszenie ochrony pamięci",
    "internal program abort": "wewnętrzne przerwanie programu",
    "Conversion ended without a result": "Konwersja zakończyła się bez wyniku",
    "Conversion crashed: {name} (code {code})": "Awaria konwersji: {name} (kod {code})",
    "Conversion crashed (code {code})": "Awaria konwersji (kod {code})",
    "Crash in the geometry kernel ({fatal})": "Awaria jądra geometrii ({fatal})",
    "Hang in the geometry kernel": "Zawieszenie jądra geometrii",
    "Crash in the geometry kernel": "Awaria jądra geometrii",
    "New attempt ({attempt}. of at most {max})": "Nowa próba ({attempt}. z maksymalnie {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} przy osiach (IfcAlignment, IfcGrid). {again} bez osi …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} przy {label}. {again}, ten element zostanie pominięty …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} przy jednym elemencie. {again}, zostanie obliczony najpierw i osobno …",
    "{what} in the hull's rough pre-computation. {again} with OpenCASCADE for the pre-computation …":
        '{what} we wstępnym obliczeniu powłoki. {again} z OpenCASCADE dla wstępnego obliczenia …',
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} przy jednym z {count} elementów. {again}, zostaną obliczone najpierw i osobno, aby znaleźć ten "
        "wadliwy …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Konwersja: {input} ({size}) -> {output}, format {fmt}, wątki: {threads}{options}{priority}",
    "(next to the IFC file)": "(obok pliku IFC)",
    ", normal priority": ", normalny priorytet",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Znane z wcześniejszych konwersji tego pliku, pomijane (jądro geometrii uległo na nich awarii lub się "
        "zawiesiło) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", już obliczone elementy są przejmowane …",
    " (exit code {code})": " (kod wyjścia {code})",
    "Cancelled after {seconds} s: {path}": "Anulowano po {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Błąd po {seconds} s przy {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Awaria po {seconds} s przy {path}: {error} (kod wyjścia {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Zawieszenie, anulowano po {seconds} s: {path}",
    "Conversion of {path} failed": "Konwersja {path} nie powiodła się",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Gotowe po {seconds} s: {input} -> {output}, elementów: {elements}, bez geometrii: {missing}, "
        "pominiętych: {skipped}",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Pominięte, bo jądro geometrii uległo na nich awarii lub się zawiesiło ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Bez geometrii ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … i jeszcze {count}",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Za mało miejsca w folderze tymczasowym na punkt kontrolny; po awarii wszystko zostanie obliczone od nowa",
    "size unknown": "rozmiar nieznany",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Osiągnięto limit pamięci procesu konwersji ({limit} GB)",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Osiągnięto limit pamięci procesu konwersji ({limit} GB), konwersja mimo to dobiegła końca (np. bez "
        "procesów pomocniczych)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "Zabrakło pamięci: Konwersja może zająć najwyżej {limit} GB ({share} % pamięci), aby inne programy mogły "
        "dalej działać. Do tego pliku komputer potrzebuje więcej pamięci.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Obiekt zadania (job) dla konwersji niedostępny ({error}), kontynuacja bez limitu pamięci",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Proces konwersji nie należy do obiektu zadania (job) ({error}), kontynuacja bez limitu pamięci",
    "Skipped elements could not be saved ({path}): {error}":
        "Nie udało się zapisać pominiętych elementów ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (po {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "Trwa od {seconds} s, {percent} %: {message}",
    "{message}: {size} written …": "{message}: zapisano {size} …",
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message}':
        'Brak postępu od {minutes} min, choć konwersja liczy (CPU {cpu} s), {percent} %: {message}',
    'The conversion has made no progress for {duration} although it is computing (the geometry kernel hangs)':
        'Konwersja nie poczyniła postępu od {duration}, choć liczy (jądro geometryczne zawiesiło się)',
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message} – the geometry kernel hangs, the conversion is restarted':
        'Brak postępu od {minutes} min, choć konwersja liczy (CPU {cpu} s), {percent} %: {message} – jądro geometryczne zawiesiło się, konwersja zostaje uruchomiona ponownie',
    '{count} elements of the chunk are computed again together, without the ones the geometry kernel hung on …':
        '{count} elementów pakietu jest liczonych ponownie razem, bez tych, na których zawiesiło się jądro geometryczne …',
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Brak aktywności obliczeniowej od {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
    " after {fatal}": " po {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "Proces konwersji zgłasza błąd krytyczny: {marker}",
    " (last {shown} KB of {size} KB)": " (ostatnie {shown} KB z {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Wyjście procesu konwersji{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Nie udało się zakończyć procesu konwersji {pid}",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "Geometria Rhino spowodowała awarię procesu pomocniczego, zamiast tego przejęto ją jako siatkę: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "Geometria Rhino spowodowała awarię procesu pomocniczego, element pominięto: {label}",
    "Writing Rhino file ({count} objects) …": "Zapisywanie pliku Rhino (obiektów: {count}) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) jest odczytywany jako IFC2x3, który przejął jego encje i atrybuty.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 to nieopublikowany projekt (tunele) i jest odczytywany jako IFC4.3: IfcTunnel jako IfcFacility, "
        "IfcTunnelPart jako IfcFacilityPart, IfcUndergroundExcavation i IfcArchElement jako "
        "IfcBuildingElementProxy; odwołania do zbiorów danych (IfcDataSetInformation) są pomijane.",
    "IFC4x4 (draft)": "IFC4x4 (projekt)",
    "{count} entities renamed": "zmieniono nazwy {count} encji",
    "{count} left out": "pominięto {count}",
    # serializers.py
    "Writing GLB file …": "Zapisywanie pliku GLB …",
    "Writing OBJ file …": "Zapisywanie pliku OBJ …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "Zapisywanie pliku STEP (dokładne powierzchnie, przy dużych modelach trwa minuty) …",
    "Writing DAE file …": "Zapisywanie pliku DAE …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Nie udało się zapisać pliku {fmt}: serializator nie przyjął żadnego z {count} elementów.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Te elementy mają geometrię, której nie udało się skonwertować – np. nieobsługiwane typy geometrii, "
        "albo ich otwory wycinają je w całości.",
    "1 element without geometry": "1 element bez geometrii",
    "{count} elements without geometry": "{count} elementów bez geometrii",
    " … and {count} more (all of them in the log file)": " … i jeszcze {count} (wszystkie w pliku dziennika)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 element pominięto, bo jądro geometrii uległo na nim awarii lub się zawiesiło: {names}{more}. "
        "W programie CAD można go znaleźć po GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} elementów pominięto, bo jądro geometrii uległo na nich awarii lub się zawiesiło: {names}{more}. "
        "W programie CAD można je znaleźć po GlobalId.",
    "There was not enough memory": "Zabrakło pamięci",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Nie udało się odczytać pliku jako IFC (uszkodzony lub nie jest plikiem IFC): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Nie udało się odczytać pliku jako IFC (uszkodzony lub nie jest plikiem IFC)",
    "File or network error: {message}": "Błąd pliku lub sieci: {message}",
    "Internal error ({name}): {message}": "Błąd wewnętrzny ({name}): {message}",
    "Internal error ({name})": "Błąd wewnętrzny ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Zgłaszając błąd, proszę dołączyć plik dziennika ({log}).",
    "Details are in the log file ({log}).": "Szczegóły w pliku dziennika ({log}).",
    "up to 1 thread (of {cores} logical cores)": "do 1 wątku (z {cores} rdzeni logicznych)",
    "up to {threads} threads (of {cores} logical cores)": "do {threads} wątków (z {cores} rdzeni logicznych)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, plus do {workers} procesów pomocniczych dla geometrii Rhino przy dużych modelach 3DM",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, niski priorytet – inne programy mają pierwszeństwo",
    "{threads_text}, normal priority": "{threads_text}, normalny priorytet",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands} {hundreds}",  # the thousands separator: 117,137 -> 117 137
    "1 interior element left out": "pominięto 1 element wewnętrzny",
    "{count} interior elements left out": "pominięto {count} elementów wewnętrznych",
    # app.py
    "not available": "niedostępne",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<użytkownik>",
    "<computer>": "<komputer>",
    "<server>": "<serwer>",
    "<share>": "<udział>",
    "<folder>": "<folder>",
    "File": "Plik",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Dokładne (zalecane)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Każdy element kompletny i taki sam przy każdym uruchomieniu; tylko duże siatki trójkątów (teren) "
        "trafiają do szybkiego jądra, które przejmuje je bez zmian.",
    "Fast": "Szybkie",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3 do 13 razy szybsze, ale w niektórych elementach może pominąć lub zdublować ściany.",
    "OpenCASCADE only": "Tylko OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Wszystko przez OpenCASCADE, także modele terenu: tam bardzo wolno (ponad 20 minut dla dużego terenu).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Zastępuje nazwy użytkowników i komputerów, serwery i udziały dysków sieciowych, nazwy folderów "
        "(<folder>) i plików (Plik-1.ifc, Plik-1.3dm …) oraz pomija nazwy elementów. Zachowane zostają klasa "
        "IFC i GlobalId, czasy, rozmiary, wersje i komunikaty o błędach.",
    "There is no log file yet in {folder}.": "W {folder} nie ma jeszcze pliku dziennika.",
    "Text files (*.txt);;All files (*)": "Pliki tekstowe (*.txt);;Wszystkie pliki (*)",
    # dialogs.py: settings
    "Settings": "Ustawienia",
    "Performance": "Wydajność",
    "Geometry kernel": "Jądro geometrii",
    "Output": "Wyjście",
    "Log file": "Plik dziennika",
    "OK": "OK",
    "Apply and save the settings": "Zastosuj i zapisz ustawienia",
    "Cancel": "Anuluj",
    "Discard changes": "Odrzuć zmiany",
    "Defaults": "Domyślne",
    "Reset all settings to their defaults": "Przywróć wszystkie ustawienia domyślne",
    "At most this many threads:": "Najwyżej tyle wątków:",
    "Automatic ({threads})": "Automatycznie ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 lub „Automatycznie” zostawia kilka rdzeni wolnych i bierze mniej, gdy wolnego RAM-u jest mało.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Tyle rdzeni procesora oblicza geometrię jednocześnie. Mniej wątków mniej spowalnia inne programy, ale "
        "konwersja trwa dłużej. „Automatycznie” używa do {threads} z {cores} rdzeni logicznych tego komputera "
        "(około połowy, licząc procesy pomocnicze wyjścia Rhino) i mniej, gdy wolnego RAM-u jest mało; każdy "
        "wątek może przy dużych elementach potrzebować do ok. 1 GB.",
    "Convert at low priority (recommended)": "Konwertuj z niskim priorytetem (zalecane)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "Konwersja działa z priorytetem Windows „Poniżej normalnego”: Rhino, Revit i podobne mają pierwszeństwo "
        "i pozostają responsywne; konwersja wykorzystuje tylko czas procesora, który jej zostawią. Bez tego "
        "ustawienia konkuruje z nimi na równych prawach.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Czym obliczana jest geometria elementów. Dotyczy wszystkich formatów wyjściowych.",
    "Open the output folder after the conversion": "Otwórz folder wyjściowy po konwersji",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Otwiera folder w Eksploratorze, gdy tylko wszystkie pliki zostaną skonwertowane.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Istniejące pliki nigdy nie są nadpisywane – jeśli nazwa już istnieje, dopisywane jest (2), (3) … "
        "Same pliki IFC nigdy nie są zmieniane.",
    "Identical elements as blocks (smaller file)": "Identyczne elementy jako bloki (mniejszy plik)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Elementy o tej samej geometrii typu (okna, drzwi, meble …) stają się wystąpieniami bloku Rhino.\n"
        "Plik jest mniejszy, ale wystąpienia bloków zachowują się inaczej niż zwykłe obiekty:\n"
        "Aby edytować geometrię, wystąpienie trzeba najpierw rozbić (_Explode).\n"
        "Teksty użytkownika, warstwa i kolor są przypisane do wystąpienia.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "Geometria typu wspólna dla kilku elementów (okna, drzwi, meble …) jest zapisywana raz jako blok i "
        "wstawiana jako wystąpienie dla każdego elementu: plik mniejszy o 20–45 %. Aby edytować ją w Rhino, "
        "wystąpienie bloku trzeba najpierw rozbić (_Explode).",
    "Log file:": "Plik dziennika:",
    "Settings:": "Ustawienia:",
    "With this, a conversion uses {resources}.": "Konwersja używa wtedy: {resources}.",
    # dialogs.py: about
    "About {app}": "O programie {app}",
    "Version {version}": "Wersja {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Konwertuje modele budynków IFC do plików Rhino (3DM), GLB i OBJ. Działa całkowicie lokalnie: "
        "bez połączenia z internetem, bez telemetrii, bez automatycznych aktualizacji.",
    "Components": "Składniki",
    "Component": "Składnik",
    "Version": "Wersja",
    "Licence": "Licencja",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Biblioteki dołączono bez zmian. Pełne teksty licencji znajdują się w folderze programu w pliku "
        "THIRD-PARTY-NOTICES.txt oraz w folderze „licenses”.",
    "Source code:": "Kod źródłowy:",
    "Copy version info": "Kopiuj informacje o wersji",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Kopiuje wersje programu i składników jako tekst, np. do zgłoszenia błędu.",
    "Close": "Zamknij",
    "Copied ✓": "Skopiowano ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Nieoczekiwany błąd",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Wystąpił nieoczekiwany błąd.</b><br>"
        "Program działa dalej. Jeśli coś przestało działać, proszę uruchomić go ponownie.<br>"
        "Aby zgłosić problem, skopiuj szczegóły i dołącz je do zgłoszenia.",
    "Copy details": "Kopiuj szczegóły",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Pominięte (awaria jądra)",
    "Without geometry": "Bez geometrii",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Jak znaleźć element w programie CAD: skopiuj GlobalId i wyszukaj go – w ArchiCAD-zie przez "
        "„Znajdź i zaznacz” (Ctrl+F) po właściwości IFC GlobalId lub „Archicad IFC ID”, w Revicie po "
        "parametrze „IfcGUID” (np. w zestawieniu lub filtrem), w innym wypadku w dowolnej przeglądarce IFC.",
    "Reason": "Powód",
    "Class": "Klasa",
    "GlobalId": "GlobalId",
    "Name": "Nazwa",
    "Skipped elements – {file}": "Pominięte elementy – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} pominięto, bo jądro geometrii uległo na nich awarii lub się zawiesiło",
    "{count} without geometry (not convertible)": "{count} bez geometrii (nie do skonwertowania)",
    "{inside} (building hull only)": "{inside} (tylko powłoka budynku)",
    "Copy": "Kopiuj",
    "{count} more elements without geometry could not be named individually.":
        "Jeszcze {count} elementów bez geometrii nie dało się wymienić z osobna.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Elementy wewnętrzne pominięte z powodu opcji „Tylko powłoka budynku” nie są wymieniane z osobna; "
        "bez tej opcji one także są konwertowane.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Zaznaczenie i Ctrl+C kopiuje wybrane wiersze (Ctrl+A: wszystkie) jako tabelę do wklejenia w Excelu "
        "lub e-mailu.",
    "Copy all": "Kopiuj wszystko",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Kopiuje całą tabelę do wklejenia w Excelu lub e-mailu.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Plik Rhino (.3dm) – otwórz i pracuj dalej bezpośrednio w Rhino.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binarny (.glb) – kompaktowy, do przeglądarek internetowych, Blendera, Three.js i silników gier.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – otwiera się w niemal każdym programie 3D.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – siatki trójkątów z kolorami, do SketchUpa, Blendera, Unity i ArchiCAD-a. Plik tekstowy, około dwa razy większy niż .glb.",
    "Polysurfaces (recommended)": "Polipowierzchnie (zalecane)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Ściany, stropy, okna … jako zamknięte polipowierzchnie z prawdziwymi otworami. Bardzo szczegółowe obiekty (meble, armatura sanitarna, oprawy) pozostają siatkami. Plik 1,2–4,5× większy zależnie od modelu – przy bardzo dużych modelach lepiej wybrać „Siatki”.",
    "Meshes": "Siatki",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "Najmniejsze pliki, najszybsza konwersja. Powierzchnie krzywe cieniowane gładko, krawędzie ostre.",
    "Only the building hull": "Tylko powłoka budynku",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Konwertuje tylko powłokę budynku, czyli to, co widać z zewnątrz: ściany zewnętrzne, dachy, okna, drzwi, balkony, teren … Ściany wewnętrzne, meble, wyposażenie, rury i kanały są pomijane; plik jest znacznie mniejszy (np. do modeli otoczenia lub na słabsze komputery).\n\nW tym celu krótki dodatkowy przebieg oblicza najpierw zgrubną geometrię wszystkich elementów (pierwsze 25 % postępu). Elementy oznaczone w IFC jako zewnętrzne (IsExternal) są zawsze zachowywane; w razie wątpliwości element jest raczej zachowywany niż pomijany. Wymiary i położenie skonwertowanych elementów nie zmieniają się. Dotyczy każdego formatu wyjściowego.",
    "Reading IFC …": "Odczyt IFC …",
    "Converting … {percent}% – {detail}": "Konwersja … {percent} % – {detail}",
    "Converting … {percent}%": "Konwersja … {percent} %",
    "{count} without geometry": "{count} bez geometrii",
    "Done – {elements}": "Gotowe – {elements}",
    "Error: {error}": "Błąd: {error}",
    "Cancelled": "Anulowano",
    "Queued – starts afterwards": "W kolejce – zacznie się potem",
    "Waiting": "Oczekuje",
    "1 file": "1 plik",
    "{count} files": "{count} plików",
    "1 element": "1 element",
    "{count} elements": "{count} elementów",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Kliknij, aby otworzyć okno wyboru plików (Ctrl+O). Foldery są przeszukiwane pod kątem plików .ifc.",
    "Drop IFC files or folders here": "Upuść tutaj pliki lub foldery IFC",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Foldery są przeszukiwane pod kątem plików .ifc i .ifczip – także kilka naraz",
    "Add files…": "Dodaj pliki…",
    "Size": "Rozmiar",
    "Status": "Stan",
    "Convert IFC building models to 3D formats": "Konwertuj modele budynków IFC do formatów 3D",
    "Double-click a finished file to open its output folder; right-click for more.": "Dwuklik na gotowym pliku otwiera jego folder wyjściowy; prawy przycisk – więcej.",
    "Remove": "Usuń",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Usuwa zaznaczone pliki z listy (Del). Same pliki pozostają nietknięte.",
    "Clear list": "Wyczyść listę",
    "Take all files off the list.": "Usuwa wszystkie pliki z listy.",
    "Skipped elements…": "Pominięte elementy…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Wyświetla elementy wybranego pliku, które nie zostały skonwertowane, z klasą, GlobalId i nazwą (także prawym przyciskiem na wierszu).",
    "Drag to divide the room between list and preview": "Przeciągnij, aby podzielić miejsce między listą a podglądem",
    "Output format": "Format wyjściowy",
    "Output folder": "Folder wyjściowy",
    "Change…": "Zmień…",
    "Save next to the IFC file": "Zapisz obok pliku IFC",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Istniejące pliki nigdy nie są nadpisywane: jeśli nazwa jest zajęta, dopisywane jest (2), (3) …",
    "Choose the output folder.": "Wybierz folder wyjściowy.",
    "Each file goes into the folder of its IFC file.": "Każdy plik trafia do folderu swojego pliku IFC.",
    "Ready": "Gotowy",
    "Progress over all files in the list": "Postęp dla wszystkich plików na liście",
    "Log – here you can see what happened to each file.": "Dziennik – tu widać, co się stało z każdym plikiem.",
    "Drag to enlarge or shrink the log": "Przeciągnij, aby powiększyć lub zmniejszyć dziennik",
    "Log": "Dziennik",
    "Show or hide the log (F4)": "Pokaż lub ukryj dziennik (F4)",
    "Open output folder": "Otwórz folder wyjściowy",
    "Opens the folder of the file written last.": "Otwiera folder ostatnio zapisanego pliku.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Anuluje trwającą konwersję. Gotowe pliki zostają, rozpoczęty jest usuwany.",
    "Convert": "Konwertuj",
    "Convert all files in the list (Ctrl+Enter)": "Konwertuj wszystkie pliki z listy (Ctrl+Enter)",
    "Add folder…": "Dodaj folder…",
    "Quit": "Zakończ",
    "Settings…": "Ustawienia…",
    "Preview": "Podgląd",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "Wybierz pliki IFC (Ctrl+O). Foldery: Plik → Dodaj folder…",
    "&File": "&Plik",
    "&Edit": "&Edycja",
    "&View": "&Widok",
    "&Tools": "&Narzędzia",
    "&Help": "Pomo&c",
    "Language": "Język",
    "The user interface switches to {language} when the program is restarted. Restart now?": "Interfejs przełączy się na język {language} po ponownym uruchomieniu programu. Uruchomić ponownie teraz?",
    "Restart now": "Uruchom ponownie",
    "Later": "Później",
    "Geometry": "Geometria",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Folder wyjściowy: {path}\n\nIstniejące pliki nigdy nie są nadpisywane: dopisywane jest (2), (3) …",
    "Choose output folder": "Wybierz folder wyjściowy",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ Nie znaleziono pliku IFC: {path} – tylko pliki .ifc i .ifczip oraz foldery, które je zawierają (ifcXML nie można odczytać)",
    "• Already in the list: {names}": "• Już na liście: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} w kolejce: konwersja zaraz po bieżącej partii, z tymi samymi ustawieniami.",
    "+ {files} added": "+ dodano: {files}",
    "Add IFC files": "Dodaj pliki IFC",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "Pliki IFC (*.ifc *.IFC *.ifczip *.ifcZIP);;Wszystkie pliki (*)",
    "Add a folder with IFC files": "Dodaj folder z plikami IFC",
    "Written: {path}": "Zapisano: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} pominięto (awaria lub zawieszenie jądra geometrii)",
    "Only the building hull: {inside} (interior elements)": "Tylko powłoka budynku: {inside} (elementy wewnętrzne)",
    "List to copy: right-click → “Skipped elements…”": "Lista do skopiowania: prawy przycisk → „Pominięte elementy…”",
    "The output folder cannot be created:\n{error}": "Nie można utworzyć folderu wyjściowego:\n{error}",
    "next to the IFC files": "obok plików IFC",
    "identical elements as blocks": "identyczne elementy jako bloki",
    "only the building hull": "tylko powłoka budynku",
    "output: {target}": "wyjście: {target}",
    "geometry kernel {kernel}": "jądro geometrii {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Moc obliczeniowa: {resources}",
    "Conversion running …": "Konwersja trwa …",
    "Cancelling …": "Anulowanie …",
    "■ Cancel requested": "■ Zażądano anulowania",
    "Reading IFC ({size}) – may take a few minutes …": "Odczyt IFC ({size}) – może potrwać kilka minut …",
    "{file}: new attempt – reading IFC …": "{file}: nowa próba – odczyt IFC …",
    "Converting {file} …": "Konwersja {file} …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Lista do skopiowania: prawy przycisk na pliku → „Pominięte elementy…”",
    "✗ Error in {file}: {error}": "✗ Błąd w {file}: {error}",
    "{done} of {files} done": "gotowe {done} z {files}",
    "{count} with errors": "{count} z błędami",
    "cancelled": "anulowano",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 plik w kolejce nie został skonwertowany – „Konwertuj” go uruchomi.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} plików w kolejce nie zostało skonwertowanych – „Konwertuj” je uruchomi.",
    "▶ Continuing with {files}, added during the conversion": "▶ Kontynuacja: {files}, dodane podczas konwersji",
    "Cancelled after {duration}": "Anulowano po {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ gotowe {done}, z błędami {failed} – po {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} z błędami – po {duration}",
    "Error": "Błąd",
    "✓ Done after {duration}": "✓ Gotowe po {duration}",
    "✓ Done": "✓ Gotowe",
    "{done} of {files} done – %p%": "gotowe {done} z {files} – %p %",
    "✗ The output folder does not exist (yet): {path}": "✗ Folder wyjściowy (jeszcze) nie istnieje: {path}",
    "Add files and click “Convert”.": "Dodaj pliki i kliknij „Konwertuj”.",
    "The conversion is still running.": "Konwersja wciąż trwa.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "Trwa konwersja „{file}”; konwersja działa od {since} ({percent} %).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Zakończenie anuluje konwersję, a jej postęp przepadnie. Zakończyć mimo to?",
    "Select a file in the list – its preview appears here.": "Wybierz plik z listy – tu pojawi się jego podgląd.",
    "The 3D view is not available on this PC.": "Widok 3D jest niedostępny na tym komputerze.",
    "Compute preview": "Oblicz podgląd",
    "Computes the preview of this file now (low priority, at most 8 threads, 4 while a conversion runs); it is kept for next time.":
        "Oblicza podgląd tego pliku teraz (niski priorytet, najwyżej 8 wątków, 4 podczas konwersji); zostaje zapamiętany na następny raz.",
    "Stop computing the preview": "Przerwij obliczanie podglądu",
    "Reset view": "Resetuj widok",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Widok początkowy: cały model z południowego zachodu z góry (Home; dwuklik: cały model)",
    "Preview – {file}": "Podgląd – {file}",
    "Computing preview …": "Obliczanie podglądu …",
    "No preview possible: {error}": "Podgląd niemożliwy: {error}",
    "The file is not (or no longer) accessible.": "Plik jest niedostępny (lub już niedostępny).",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Podczas konwersji podgląd nie jest obliczany, aby jej nie spowalniać.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Duży plik ({size}): podgląd zajmie kilka minut. Działa z niskim priorytetem i zostanie zachowany na następny raz.",
    "Waiting for the running preview to finish …": "Oczekiwanie na zakończenie trwającego podglądu …",
    "Computing preview: reading the IFC file …": "Obliczanie podglądu: odczyt pliku IFC …",
    "Loading preview …": "Wczytywanie podglądu …",
    "Preview cancelled.": "Podgląd anulowano.",
    "No preview possible: the geometry kernel crashed repeatedly.":
        "Podgląd niemożliwy: jądro geometryczne wielokrotnie uległo awarii.",
    "Preview cancelled – incomplete":
        "Podgląd anulowano – niekompletny",
    "Preview incomplete (the geometry kernel crashed repeatedly)":
        "Podgląd niekompletny (jądro geometryczne wielokrotnie uległo awarii)",
    "Preview incomplete: {error}":
        "Podgląd niekompletny: {error}",
    "Preview incomplete so far (the geometry kernel crashed), computing the rest …":
        "Podgląd na razie niekompletny (jądro geometryczne uległo awarii), obliczanie reszty …",
    "{count} of {total} elements so far":
        "na razie {count} z {total} elementów",
    "{count} details left out ({kinds})":
        "pominięto {count} detali ({kinds})",
    "The preview could not be loaded.": "Nie udało się wczytać podglądu.",
    "The file contains no geometry that can be shown.": "Plik nie zawiera geometrii, którą można wyświetlić.",
    "Computing preview … {percent}%": "Obliczanie podglądu … {percent} %",
    "Preview: {status}": "Podgląd: {status}",
    "Try again": "Spróbuj ponownie",
    "{count} small elements left out": "pominięto {count} małych elementów",
    "Renderer: {renderer}": "Renderer: {renderer}",
    "Click an element to see its class, GlobalId and name": "Kliknij element, aby zobaczyć jego klasę, GlobalId i nazwę",
    "Iso": "Izo",
    "Isometric view from the south-west (1)": "Widok izometryczny z południowego zachodu (1)",
    "Top": "Góra",
    "Plan view, north up (2)": "Rzut z góry, północ u góry (2)",
    "Front": "Przód",
    "View from the south (3)": "Widok z południa (3)",
    "Side": "Bok",
    "View from the east (4)": "Widok ze wschodu (4)",
    "Show the whole model (F, double-click)": "Pokaż cały model (F, dwuklik)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "Plik zawiera {count} projektów o różnych jednostkach; wszystkie są wczytywane w jednostkach pierwszego ({name}). Proszę sprawdzić wymiary.",
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} jest wczytywany jako {target} (ten sam schemat pod inną nazwą).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Za mało wolnego miejsca w folderze tymczasowym na kopię roboczą pliku (potrzeba {needed}, wolne {free}).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'Plik IFC wydaje się ucięty (brak END-ISO-10303-21 na końcu): wynik może być niekompletny.',
    # interactive.py (drag-and-drop terminal mode)
    'Drop IFC file(s) or folders into this window, then press Enter.': 'Przeciągnij plik(i) IFC lub foldery do tego okna, potem Enter.',
    'Finished files go to: {folder}': 'Gotowe pliki trafiają do: {folder}',
    '{first} or {last}': '{first} lub {last}',
    "Change the format: enter {formats}.  Quit: 'q'": "Zmiana formatu: wpisz {formats}.  Wyjście: 'q'",
    'Cancel a running conversion: Ctrl+C': 'Przerwanie trwającej konwersji: Ctrl+C',
    'Computing power: {resources}': 'Moc obliczeniowa: {resources}',
    'Building hull only: elements inside the building (interior walls, furniture, fittings, pipes and ducts) are left out.': 'Tylko powłoka budynku: elementy wewnątrz budynku (ściany wewnętrzne, meble, wyposażenie, rury i kanały) są pomijane.',
    '[{fmt}] Drop a file here > ': '[{fmt}] Przeciągnij plik tutaj > ',
    'The format is {fmt} now.': 'Format to teraz {fmt}.',
    '✗ No IFC file found: {path}': '✗ Nie znaleziono pliku IFC: {path}',
    '✗ The output folder cannot be created: {error}': '✗ Nie można utworzyć folderu wyjściowego: {error}',
    '… converting {name}': '… konwersja {name}',
    '■ Cancelled: {name}': '■ Przerwano: {name}',
    ' ({count} more not converted)': ' ({count} kolejnych nie przekonwertowano)',
    ', {count} without geometry': ', {count} bez geometrii',
    '✓ Finished: {output}  ({count} elements{skipped}{inside})': '✓ Gotowe: {output}  ({count} elementów{skipped}{inside})',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "Nie można zapisać do folderu wyjściowego {folder} ({error})",
    "Show edges (E)": "Pokaż krawędzie (E)",
    "Parallel projection instead of perspective (P)": "Rzut równoległy zamiast perspektywy (P)",
    # log file (always anonymised, one option: save)
    "Help → Save log file…": "Pomoc → Zapisz plik dziennika…",
    "Save log file": "Zapisz plik dziennika",
    "The log file could not be saved:\n{error}": "Nie udało się zapisać pliku dziennika:\n{error}",
    "The log file has been saved:\n{path}\n\n{hint}\n\nPlease look through it briefly before sending. Open the folder now?": "Plik dziennika został zapisany:\n{path}\n\n{hint}\n\nPrzejrzyj go krótko przed wysłaniem. Otworzyć folder teraz?",
    "Save log…": "Zapisz dziennik…",
    "The log file stays on this PC; nothing is sent automatically. It contains no user, computer, server, folder, file or element names.": "Plik dziennika pozostaje na tym komputerze; nic nie jest wysyłane automatycznie. Nie zawiera nazw użytkowników, komputerów, serwerów, folderów, plików ani elementów.",
    "Log of this session. Everything is also in the log file (Help → Save log file…).": "Dziennik tej sesji. Wszystko jest też w pliku dziennika (Pomoc → Zapisz plik dziennika…).",
    "Save log file…": "Zapisz plik dziennika…",
}
