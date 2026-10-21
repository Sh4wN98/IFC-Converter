"""User interface texts: tr (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Ara kayıt {name} okunamıyor ({error}), yeniden hesaplanıyor",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Ara kayıt kaydedilemiyor ({error}); ara kayıt olmadan devam ediliyor",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Desteklenmeyen biçim “{fmt}”; olası biçimler: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Desteklenmeyen geometri türü “{geometry}”; olası türler: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Bilinmeyen geometri çekirdeği “{kernel}”; olası çekirdekler: {kernels}",
    "IFC file not found: {path}": "IFC dosyası bulunamadı: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "IfcOpenShell ifcXML dosyalarını okuyamaz ({name}). Lütfen modeli yazarlık programından .ifc "
        "(STEP metin biçimi) veya .ifczip olarak dışa aktarın.",
    "Reading IFC file ({size}) …": "IFC dosyası okunuyor ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "IFC sürümü desteklenmiyor ({error}). Desteklenenler: {supported}; ayrıca {bridges} en yakın ilişkili "
        "şema olarak okunur.",
    "{note} Dimensions and positions stay unchanged.": "{note} Ölçüler ve konumlar değişmez.",
    "Determining the building hull (geometry roughly precomputed) …":
        "Bina kabuğu belirleniyor (geometri kabaca ön hesaplanıyor) …",
    'The geometry kernel hung on {label} for more than {minutes} min: the element is skipped':
        'Geometri çekirdeği {minutes} dakikadan uzun süredir {label} öğesinde takılı: öğe atlanıyor',
    'The geometry kernel hung on {label} for more than {minutes} min in the rough pre-computation: the element is kept as part of the hull':
        'Geometri çekirdeği {minutes} dakikadan uzun süredir {label} öğesinde takılı (kaba ön hesaplama): öğe kabuğun parçası olarak korunuyor',
    'The geometry kernel hung on one of {count} elements for more than {minutes} min: they are computed one by one …':
        'Geometri çekirdeği {minutes} dakikadan uzun süredir {count} öğeden birinde takılı: tek tek hesaplanıyorlar …',
    '{count} elements not computed because the geometry kernel hung on their chunk: they are skipped':
        'Geometri çekirdeği paketlerinde takıldığı için {count} öğe hesaplanmadı: atlanıyorlar',
    '{count} elements not computed because the geometry kernel hung on their chunk in the rough pre-computation: they are kept as part of the hull':
        'Kaba ön hesaplamada geometri çekirdeği paketlerinde takıldığı için {count} öğe hesaplanmadı: kabuğun parçası olarak korunuyorlar',
    "Computing geometry ({threads} threads) …": "Geometri hesaplanıyor ({threads} iş parçacığı) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Geometri üretilemedi: geometrisi olan {count} elemanın hiçbiri dönüştürülemedi (muhtemelen desteklenmeyen "
        "geometri türleri).",
    "The file contains no elements with geometry.": "Dosyada geometrisi olan eleman yok.",
    "Copying to the target folder ({size}) …": "Hedef klasöre kopyalanıyor ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "Kopyalama başarısız ({error}) – {attempt}. deneme {seconds} sn içinde …",
    "Copying to the target folder … {copied} of {total}": "Hedef klasöre kopyalanıyor … {copied} / {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Tamamlanan dosya {folder} klasörüne kopyalanamadı ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Tamamlanan dosya {folder} klasörüne kopyalanamadı ({error}). Dosya burada: {path} – lütfen elle "
        "kopyalayın.",
    "{count} extrusions with negative depth turned around": "{count} negatif derinlikli ekstrüzyon ters çevrildi",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} eleman önceki denemeden alındı, {count} eleman hesaplanıyor",
    "Geometry contains itself (faulty file), not converted: {label}":
        "Geometri kendini içeriyor (hatalı dosya), dönüştürülmedi: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Derin iç içe eleman ({depth} düzey) {number} / {total} tek başına hesaplanıyor: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Eleman {number} / {total} tek başına hesaplanıyor: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} eleman ancak ikinci denemede hesaplandı (daha ince tolerans veya başka çekirdek)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "İkinci denemeler {seconds} sn sonra sonlandırıldı; geometrisiz diğer elemanlar artık tek başına "
        "denenmedi",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} geometri hesaplaması {seconds} sn sonra hâlâ sürüyor ve arka planda sonlandırılıyor",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} muhtemelen yaklaşık {needed} GB bellek gerektirecek, yalnızca {available} GB boş. Diğer "
        "programları kapatın, yoksa işlem çok yavaşlar veya dönüştürme kesilir.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, kaba {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Yalnızca bina kabuğu: Modelin kapalı bir kabuğu yok (çatı, döşeme veya duvarlar eksik, örn. kaba yapısı "
        "olmayan kısmi bir model): dış hava hemen hemen tüm elemanlara ulaşıyor (ızgara {voxel} m). Bunun yerine "
        "dışarıda bırakılanlar: iç olarak işaretlenmiş {marked} eleman (IsExternal = Hayır) ile {fittings} "
        "mobilya, donanım, boru ve kanal, tavan ve zemin kaplaması; {total} elemandan {kept} tanesi dönüştürülüyor.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Yalnızca bina kabuğu: {total} elemandan {kept} tanesi dışta ve dönüştürülüyor, {inside} iç eleman "
        "dışarıda bırakıldı (ızgara {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; ön hesaplanmış geometrisi olmayan {count} eleman güvenli tarafta kalmak için alındı",
    "; {count} marked as exterior (IsExternal) taken over":
        "; dış olarak işaretlenmiş (IsExternal) {count} eleman alındı",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} kütle hacmi (modeli saran zarflar) opak sayılmadı",
    "{count} more": "{count} tane daha",
    " Left out: {classes}.": " Dışarıda bırakılanlar: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "Bina kabuğu belirleniyor (dış hava aranıyor) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Bina kabuğu: {total} elemandan {kept} tanesi dışta ({unknown} ön hesaplanmış geometrisiz, {flagged} "
        "IsExternal ile), ızgara {voxel} m (kaba {coarse} m, {cells} hücre, ince bant {band} hücre), ön hesaplanmış "
        "geometri {coarse_seconds} sn, kabuk {hull_seconds} sn",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Bina kabuğu: ızgara {voxel} m değerine kabalaştırıldı ({cells} ızgara hücresi saklandı)",
    # preview.py
    "Saving preview ({count} triangles) …": "Önizleme kaydediliyor ({count} üçgen) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Önizleme için çok fazla üçgen (eleman başına {limit} üzeri).",
    # process.py
    "stack overflow": "yığın taşması",
    "The memory was not enough (the process was ended by the system)":
        "Bellek yetmedi (süreç sistem tarafından sonlandırıldı)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Hızlı geometri çekirdeğinde çökme – yalnızca OpenCASCADE ile yeniden deneniyor …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Geometri çekirdeğinde çökme ({fatal}), ardından dönüştürme takılı kaldı",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "Dönüştürme {duration} boyunca hiçbir şey hesaplamadı (takılı kaldı)",
    "{count} minutes": "{count} dakika",
    "{count} seconds": "{count} saniye",
    "stack overflow in the geometry kernel": "geometri çekirdeğinde yığın taşması",
    "memory access violation": "bellek erişim ihlali",
    "internal program abort": "iç program sonlandırması",
    "Conversion ended without a result": "Dönüştürme sonuç vermeden sona erdi",
    "Conversion crashed: {name} (code {code})": "Dönüştürme çöktü: {name} (kod {code})",
    "Conversion crashed (code {code})": "Dönüştürme çöktü (kod {code})",
    "Crash in the geometry kernel ({fatal})": "Geometri çekirdeğinde çökme ({fatal})",
    "Hang in the geometry kernel": "Geometri çekirdeğinde takılma",
    "Crash in the geometry kernel": "Geometri çekirdeğinde çökme",
    "New attempt ({attempt}. of at most {max})": "Yeni deneme ({attempt}. / en fazla {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} akslarda (IfcAlignment, IfcGrid). {again} akslar olmadan …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} {label} elemanında. {again}, bu eleman atlanıyor …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} bir elemanda. {again}, bu eleman önce ve tek başına hesaplanıyor …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} {count} elemandan birinde. {again}, sorunlu olanı bulmak için bunlar önce ve tek tek "
        "hesaplanıyor …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Dönüştürme: {input} ({size}) -> {output}, biçim {fmt}, {threads} iş parçacığı{options}{priority}",
    "(next to the IFC file)": "(IFC dosyasının yanına)",
    ", normal priority": ", normal öncelik",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Bu dosyanın önceki dönüştürmelerinden biliniyor, atlanıyor (geometri çekirdeği bunlarda çöktü veya "
        "takıldı) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", önceden hesaplanmış elemanlar alınıyor …",
    " (exit code {code})": " (çıkış kodu {code})",
    "Cancelled after {seconds} s: {path}": "{seconds} sn sonra iptal edildi: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "{seconds} sn sonra hata, {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "{seconds} sn sonra çökme, {path}: {error} (çıkış kodu {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Takıldı, {seconds} sn sonra iptal edildi: {path}",
    "Conversion of {path} failed": "{path} dönüştürülemedi",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "{seconds} sn sonra tamamlandı: {input} -> {output}, {elements} eleman, {missing} geometrisiz, {skipped} "
        "atlandı",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Geometri çekirdeği bunlarda çöktüğü veya takıldığı için atlandı ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Geometrisiz ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … ve {count} tane daha",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Geçici klasörde ara kayıt için yer çok az; bir çökmeden sonra her şey yeniden hesaplanır",
    "size unknown": "boyut bilinmiyor",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Dönüştürme sürecinin bellek sınırına ({limit} GB) ulaşıldı",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Dönüştürme sürecinin bellek sınırına ({limit} GB) ulaşıldı, dönüştürme yine de sonuna kadar sürdü "
        "(örn. yardımcı süreçler olmadan)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "Bellek yetmedi: Diğer programların çalışmaya devam edebilmesi için dönüştürme en fazla {limit} GB "
        "(belleğin %{share} kadarını) kullanabilir. Bu dosya için bilgisayarın daha fazla belleğe ihtiyacı var.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Dönüştürme için iş nesnesi (job object) kullanılamıyor ({error}), bellek sınırı olmadan devam ediliyor",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Dönüştürme süreci iş nesnesinde değil ({error}), bellek sınırı olmadan devam ediliyor",
    "Skipped elements could not be saved ({path}): {error}":
        "Atlanan elemanlar kaydedilemedi ({path}): {error}",
    "{message} (after {seconds} s)": "{message} ({seconds} sn sonra)",
    "Running for {seconds} s, {percent} %: {message}": "{seconds} sn'dir sürüyor, %{percent}: {message}",
    "{message}: {size} written …": "{message}: {size} yazıldı …",
    'No progress for {minutes} min although the conversion is computing (CPU {cpu} s), {percent} %: {message}':
        'Dönüştürme hesaplamaya devam etse de {minutes} dakikadır ilerleme yok (CPU {cpu} sn), %{percent}: {message}',
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "{seconds} sn'dir hesaplama etkinliği yok (CPU {cpu} sn){fatal}, %{percent}: {message}",
    " after {fatal}": " {fatal} sonrasında",
    "The conversion process reports a fatal error: {marker}":
        "Dönüştürme süreci ölümcül bir hata bildiriyor: {marker}",
    " (last {shown} KB of {size} KB)": " ({size} KB'ın son {shown} KB'ı)",
    "Output of the conversion process{cut}:\n{message}": "Dönüştürme sürecinin çıktısı{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Dönüştürme süreci {pid} sonlandırılamadı",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "Rhino geometrisi bir yardımcı süreci çökertti, bunun yerine ağ (mesh) olarak alındı: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "Rhino geometrisi bir yardımcı süreci çökertti, eleman dışarıda bırakıldı: {label}",
    "Writing Rhino file ({count} objects) …": "Rhino dosyası yazılıyor ({count} nesne) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003), varlıklarını ve özniteliklerini devralan IFC2x3 olarak okunur.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 yayımlanmamış bir taslaktır (tüneller) ve IFC4.3 olarak okunur: IfcTunnel IfcFacility olarak, "
        "IfcTunnelPart IfcFacilityPart olarak, IfcUndergroundExcavation ve IfcArchElement IfcBuildingElementProxy "
        "olarak; veri kümesi başvuruları (IfcDataSetInformation) atılır.",
    "IFC4x4 (draft)": "IFC4x4 (taslak)",
    "{count} entities renamed": "{count} varlık yeniden adlandırıldı",
    "{count} left out": "{count} dışarıda bırakıldı",
    # serializers.py
    "Writing GLB file …": "GLB dosyası yazılıyor …",
    "Writing OBJ file …": "OBJ dosyası yazılıyor …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "STEP dosyası yazılıyor (tam yüzeyler, büyük modellerde dakikalar sürer) …",
    "Writing DAE file …": "DAE dosyası yazılıyor …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "{fmt} dosyası yazılamadı: serileştirici {count} elemanın hiçbirini almadı.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Bu elemanların geometrisi dönüştürülemedi – örn. desteklenmeyen geometri türleri ya da açıklıkları "
        "onları tamamen kesip çıkarıyor.",
    "Help → Open log file": "Yardım → Günlük dosyasını aç",
    "1 element without geometry": "1 geometrisiz eleman",
    "{count} elements without geometry": "{count} geometrisiz eleman",
    " … and {count} more (all of them in the log file)": " … ve {count} tane daha (tümü günlük dosyasında)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "Geometri çekirdeği çöktüğü veya takıldığı için 1 eleman atlandı: {names}{more}. "
        "CAD programında GlobalId ile bulunabilir.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "Geometri çekirdeği çöktüğü veya takıldığı için {count} eleman atlandı: {names}{more}. "
        "CAD programında GlobalId ile bulunabilirler.",
    "There was not enough memory": "Bellek yetmedi",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Dosya IFC olarak okunamadı (bozuk ya da IFC dosyası değil): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Dosya IFC olarak okunamadı (bozuk ya da IFC dosyası değil)",
    "File or network error: {message}": "Dosya veya ağ hatası: {message}",
    "Internal error ({name}): {message}": "İç hata ({name}): {message}",
    "Internal error ({name})": "İç hata ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Hatayı bildirirken lütfen günlük dosyasını ({log}) ekleyin.",
    "Details are in the log file ({log}).": "Ayrıntılar günlük dosyasında ({log}).",
    "up to 1 thread (of {cores} logical cores)": "en fazla 1 iş parçacığı ({cores} mantıksal çekirdekten)",
    "up to {threads} threads (of {cores} logical cores)":
        "en fazla {threads} iş parçacığı ({cores} mantıksal çekirdekten)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, büyük 3DM modellerinde Rhino geometrisi için ayrıca en fazla {workers} yardımcı süreç",
    "{threads_text}, low priority – other programs take precedence":
        "{threads_text}, düşük öncelik – diğer programlar önceliklidir",
    "{threads_text}, normal priority": "{threads_text}, normal öncelik",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} sn",
    "{minutes} min {seconds} s": "{minutes} dk {seconds} sn",
    "{hours} h {minutes} min": "{hours} sa {minutes} dk",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 iç eleman dışarıda bırakıldı",
    "{count} interior elements left out": "{count} iç eleman dışarıda bırakıldı",
    # app.py
    "not available": "kullanılamıyor",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<kullanıcı>",
    "<computer>": "<bilgisayar>",
    "<server>": "<sunucu>",
    "<share>": "<paylaşım>",
    "<folder>": "<klasör>",
    "File": "Dosya",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Hassas (önerilir)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Her eleman eksiksiz ve her çalıştırmada aynı; yalnızca büyük üçgen ağlar (arazi) hızlı çekirdeğe "
        "gider, o da bunları değiştirmeden alır.",
    "Fast": "Hızlı",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3 ila 13 kat daha hızlı, ancak bazı elemanların yüzeylerini atlayabilir veya çiftleyebilir.",
    "OpenCASCADE only": "Yalnızca OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Her şey OpenCASCADE ile, arazi modelleri de: orada çok yavaş (büyük bir arazi için 20 dakikadan fazla).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Kullanıcı ve bilgisayar adlarını, ağ sürücülerinin sunucu ve paylaşımlarını, klasör adlarını "
        "(<klasör>) ve dosya adlarını (Dosya-1.ifc, Dosya-1.3dm …) değiştirir, eleman adlarını çıkarır. IFC "
        "sınıfı ve GlobalId, süreler, boyutlar, sürümler ve hata iletileri korunur.",
    "There is no log file yet in {folder}.": "{folder} içinde henüz günlük dosyası yok.",
    "Save anonymised log file": "Anonimleştirilmiş günlük dosyasını kaydet",
    "Text files (*.txt);;All files (*)": "Metin dosyaları (*.txt);;Tüm dosyalar (*)",
    "The anonymised log file could not be saved:\n{error}":
        "Anonimleştirilmiş günlük dosyası kaydedilemedi:\n{error}",
    "The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
    "Please look through it briefly before sending. Open the folder now?":
        "Anonimleştirilmiş günlük dosyası kaydedildi:\n{path}\n\n{hint}\n\n"
        "Göndermeden önce lütfen kısaca gözden geçirin. Klasör şimdi açılsın mı?",
    # dialogs.py: settings
    "Settings": "Ayarlar",
    "Performance": "Performans",
    "Geometry kernel": "Geometri çekirdeği",
    "Output": "Çıktı",
    "Log file": "Günlük dosyası",
    "OK": "Tamam",
    "Apply and save the settings": "Ayarları uygula ve kaydet",
    "Cancel": "İptal",
    "Discard changes": "Değişiklikleri at",
    "Defaults": "Varsayılanlar",
    "Reset all settings to their defaults": "Tüm ayarları varsayılanlara sıfırla",
    "At most this many threads:": "En fazla bu kadar iş parçacığı:",
    "Automatic ({threads})": "Otomatik ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 veya “Otomatik” bazı çekirdekleri boş bırakır ve boş RAM azsa daha azını kullanır.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Bu kadar işlemci çekirdeği geometriyi aynı anda hesaplar. Daha az iş parçacığı diğer programları "
        "daha az yavaşlatır, ancak dönüştürme daha uzun sürer. “Otomatik”, bu bilgisayarın {cores} mantıksal "
        "çekirdeğinden en fazla {threads} tanesini kullanır (Rhino çıktısının yardımcı süreçleriyle birlikte "
        "yaklaşık yarısı) ve boş RAM azsa daha azını; büyük elemanlarda her iş parçacığı yaklaşık 1 GB'a kadar "
        "bellek gerektirebilir.",
    "Convert at low priority (recommended)": "Düşük öncelikle dönüştür (önerilir)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "Dönüştürme, Windows'un “Normalin altında” önceliğiyle çalışır: Rhino, Revit ve benzerleri öncelikli "
        "olur ve akıcı kalır; dönüştürme yalnızca onların bıraktığı işlem süresini kullanır. Bu ayar olmadan "
        "onlarla eşit koşullarda yarışır.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Elemanların geometrisinin neyle hesaplanacağı. Tüm çıktı biçimleri için geçerlidir.",
    "Open the output folder after the conversion": "Dönüştürmeden sonra çıktı klasörünü aç",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Tüm dosyalar dönüştürülür dönüştürülmez klasörü Gezgin'de açar.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Var olan dosyaların üzerine asla yazılmaz – ad zaten varsa sonuna (2), (3) … eklenir. "
        "IFC dosyalarının kendisi asla değiştirilmez.",
    "Identical elements as blocks (smaller file)": "Özdeş elemanlar blok olarak (daha küçük dosya)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Aynı tip geometrisine sahip elemanlar (pencereler, kapılar, mobilya …) bir Rhino bloğunun örnekleri "
        "olur.\nDosya küçülür, ancak blok örnekleri normal nesnelerden farklı davranır:\n"
        "Geometriyi düzenlemek için önce örneğin patlatılması gerekir (_Explode).\n"
        "Kullanıcı metinleri, katman ve renk örneğin üzerindedir.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "Birden çok elemanın paylaştığı tip geometrisi (pencereler, kapılar, mobilya …) bir kez blok olarak "
        "saklanır ve her eleman için bir örnek olarak eklenir: dosya %20–45 daha küçük. Rhino'da düzenlemek "
        "için blok örneğinin önce patlatılması gerekir (_Explode).",
    "Log file:": "Günlük dosyası:",
    "Settings:": "Ayarlar:",
    "Open log file": "Günlük dosyasını aç",
    "Opens the current log file in the default program for text files.":
        "Geçerli günlük dosyasını metin dosyaları için varsayılan programda açar.",
    "Save anonymised…": "Anonim kaydet…",
    "Anonymise log file": "Günlük dosyasını anonimleştir",
    "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
    "no user, computer, server, folder, file or element names.":
        "Günlük dosyası bu bilgisayarda kalır; hiçbir şey otomatik olarak gönderilmez. Açıkken bundan sonra "
        "kullanıcı, bilgisayar, sunucu, klasör, dosya veya eleman adı içermez.",
    "With this, a conversion uses {resources}.": "Böylece bir dönüştürme şunları kullanır: {resources}.",
    # dialogs.py: about
    "About {app}": "{app} hakkında",
    "Version {version}": "Sürüm {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "IFC bina modellerini Rhino dosyalarına (3DM), GLB ve OBJ'ye dönüştürür. Tamamen yerel çalışır: "
        "internet bağlantısı yok, telemetri yok, otomatik güncelleme yok.",
    "Components": "Bileşenler",
    "Component": "Bileşen",
    "Version": "Sürüm",
    "Licence": "Lisans",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "Kütüphaneler değiştirilmeden dahil edilmiştir. Tam lisans metinleri program klasöründeki "
        "THIRD-PARTY-NOTICES.txt dosyasında ve “licenses” klasöründedir.",
    "Source code:": "Kaynak kodu:",
    "Copy version info": "Sürüm bilgisini kopyala",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Program ve bileşen sürümlerini metin olarak kopyalar, örn. bir hata bildirimi için.",
    "Close": "Kapat",
    "Copied ✓": "Kopyalandı ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Beklenmeyen hata",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Beklenmeyen bir hata oluştu.</b><br>"
        "Program çalışmaya devam ediyor. Bir şey artık çalışmıyorsa lütfen programı yeniden başlatın.<br>"
        "Sorunu bildirmek için ayrıntıları kopyalayıp birlikte gönderin.",
    "Copy details": "Ayrıntıları kopyala",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Atlandı (geometri çekirdeği çöktü)",
    "Without geometry": "Geometrisiz",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "CAD programında bir elemanı bulmak için: GlobalId'yi kopyalayıp arayın – ArchiCAD'de “Bul ve Seç” "
        "(Ctrl+F) ile IFC özelliği GlobalId veya “Archicad IFC ID” üzerinden, Revit'te “IfcGUID” parametresiyle "
        "(örn. bir çizelgede veya filtreyle), diğer durumlarda herhangi bir IFC görüntüleyicide.",
    "Reason": "Neden",
    "Class": "Sınıf",
    "GlobalId": "GlobalId",
    "Name": "Ad",
    "Skipped elements – {file}": "Atlanan elemanlar – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "geometri çekirdeği çöktüğü veya takıldığı için {count} atlandı",
    "{count} without geometry (not convertible)": "{count} geometrisiz (dönüştürülemez)",
    "{inside} (building hull only)": "{inside} (yalnızca bina kabuğu)",
    "Copy": "Kopyala",
    "{count} more elements without geometry could not be named individually.":
        "Geometrisiz {count} eleman daha tek tek adlandırılamadı.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "“Yalnızca bina kabuğu” nedeniyle dışarıda bırakılan iç elemanlar tek tek listelenmez; "
        "seçenek olmadan onlar da dönüştürülür.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Seçip Ctrl+C ile seçilen satırlar (Ctrl+A: tümü) Excel'e veya bir e-postaya yapıştırılacak tablo "
        "olarak kopyalanır.",
    "Copy all": "Tümünü kopyala",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Tüm tabloyu Excel'e veya bir e-postaya yapıştırmak üzere kopyalar.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Rhino dosyası (.3dm) – doğrudan Rhino'da açıp üzerinde çalışmaya devam edin.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF ikili (.glb) – kompakt; web görüntüleyiciler, Blender, Three.js ve oyun motorları için.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – hemen hemen her 3D programda açılır.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – renkli üçgen ağlar; SketchUp, Blender, Unity ve ArchiCAD için. Metin dosyası, .glb'nin yaklaşık iki katı boyutunda.",
    "Polysurfaces (recommended)": "Poliyüzeyler (önerilir)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Duvarlar, döşemeler, pencereler … gerçek açıklıklı kapalı poliyüzeyler olarak. Çok ayrıntılı nesneler (mobilya, sıhhi tesisat, aydınlatma) ağ olarak kalır. Dosya modele göre 1,2–4,5× daha büyük – çok büyük modeller için “Ağlar” seçeneği daha uygundur.",
    "Meshes": "Ağlar (Mesh)",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "En küçük dosyalar, en hızlı dönüştürme. Eğri yüzeyler yumuşak gölgeli, kenarlar keskin.",
    "Only the building hull": "Yalnızca bina kabuğu",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Yalnızca bina kabuğunu, yani dışarıdan görülebilenleri dönüştürür: dış duvarlar, çatılar, pencereler, kapılar, balkonlar, arazi … İç duvarlar, mobilya, donanım, boru ve kanallar dışarıda bırakılır; dosya çok daha küçük olur (örn. çevre modelleri veya zayıf bilgisayarlar için).\n\nBunun için kısa bir ek geçiş önce tüm elemanların kaba geometrisini hesaplar (ilerlemenin ilk %25'i). IFC'de dış olarak işaretlenmiş elemanlar (IsExternal) her zaman korunur; kararsız durumlarda eleman dışarıda bırakılmak yerine korunur. Dönüştürülen elemanların ölçüleri ve konumları değişmez. Her çıktı biçimi için geçerlidir.",
    "Reading IFC …": "IFC okunuyor …",
    "Converting … {percent}% – {detail}": "Dönüştürülüyor … %{percent} – {detail}",
    "Converting … {percent}%": "Dönüştürülüyor … %{percent}",
    "{count} without geometry": "{count} geometrisiz",
    "Done – {elements}": "Tamamlandı – {elements}",
    "Error: {error}": "Hata: {error}",
    "Cancelled": "İptal edildi",
    "Queued – starts afterwards": "Sırada – ardından başlar",
    "Waiting": "Bekliyor",
    "1 file": "1 dosya",
    "{count} files": "{count} dosya",
    "1 element": "1 eleman",
    "{count} elements": "{count} eleman",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Tıklayınca dosya iletişim kutusu açılır (Ctrl+O). Klasörlerde .ifc dosyaları aranır.",
    "Drop IFC files or folders here": "IFC dosyalarını veya klasörleri buraya bırakın",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Klasörlerde .ifc ve .ifczip dosyaları aranır – aynı anda birden çok da olabilir",
    "Add files…": "Dosya ekle…",
    "Size": "Boyut",
    "Status": "Durum",
    "Convert IFC building models to 3D formats": "IFC bina modellerini 3D biçimlere dönüştürün",
    "Double-click a finished file to open its output folder; right-click for more.": "Tamamlanan bir dosyaya çift tıklayınca çıktı klasörü açılır; daha fazlası için sağ tıklayın.",
    "Remove": "Kaldır",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Seçilen dosyaları listeden çıkarır (Del). Dosyaların kendisine dokunulmaz.",
    "Clear list": "Listeyi temizle",
    "Take all files off the list.": "Tüm dosyaları listeden çıkarır.",
    "Skipped elements…": "Atlanan elemanlar…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Seçilen dosyanın dönüştürülmeyen elemanlarını sınıf, GlobalId ve adıyla listeler (satıra sağ tıklayarak da).",
    "Drag to divide the room between list and preview": "Sürükleyin: liste ile önizleme arasındaki alanı paylaştırın",
    "Output format": "Çıktı biçimi",
    "Output folder": "Çıktı klasörü",
    "Change…": "Değiştir…",
    "Save next to the IFC file": "IFC dosyasının yanına kaydet",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Var olan dosyaların üzerine asla yazılmaz: ad kullanılıyorsa sonuna (2), (3) … eklenir.",
    "Choose the output folder.": "Çıktı klasörünü seçin.",
    "Each file goes into the folder of its IFC file.": "Her dosya kendi IFC dosyasının klasörüne gider.",
    "Ready": "Hazır",
    "Progress over all files in the list": "Listedeki tüm dosyaların toplam ilerlemesi",
    "Log – here you can see what happened to each file.": "Günlük – her dosyaya ne olduğu burada görülür.",
    "Log of this session. Everything is also in the log file (Help → Open log file).": "Bu oturumun günlüğü. Her şey günlük dosyasında da var (Yardım → Günlük dosyasını aç).",
    "Drag to enlarge or shrink the log": "Sürükleyin: günlüğü büyütün veya küçültün",
    "Log": "Günlük",
    "Show or hide the log (F4)": "Günlüğü göster veya gizle (F4)",
    "Open output folder": "Çıktı klasörünü aç",
    "Opens the folder of the file written last.": "Son yazılan dosyanın klasörünü açar.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Süren dönüştürmeyi iptal eder. Tamamlanan dosyalar kalır, yarım kalan silinir.",
    "Convert": "Dönüştür",
    "Convert all files in the list (Ctrl+Enter)": "Listedeki tüm dosyaları dönüştür (Ctrl+Enter)",
    "Add folder…": "Klasör ekle…",
    "Quit": "Çıkış",
    "Settings…": "Ayarlar…",
    "Save anonymised log file…": "Anonimleştirilmiş günlük dosyasını kaydet…",
    "Preview": "Önizleme",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "IFC dosyalarını seçin (Ctrl+O). Klasörler: Dosya → Klasör ekle…",
    "&File": "&Dosya",
    "&Edit": "Dü&zen",
    "&View": "&Görünüm",
    "&Tools": "&Araçlar",
    "&Help": "&Yardım",
    "Language": "Dil",
    "The user interface switches to {language} when the program is restarted. Restart now?": "Kullanıcı arayüzü program yeniden başlatıldığında {language} diline geçer. Şimdi yeniden başlatılsın mı?",
    "Restart now": "Şimdi yeniden başlat",
    "Later": "Daha sonra",
    "Geometry": "Geometri",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Çıktı klasörü: {path}\n\nVar olan dosyaların üzerine asla yazılmaz: sonuna (2), (3) … eklenir.",
    "Choose output folder": "Çıktı klasörünü seç",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ IFC dosyası bulunamadı: {path} – yalnızca .ifc ve .ifczip dosyaları ve bunları içeren klasörler (ifcXML okunamaz)",
    "• Already in the list: {names}": "• Zaten listede: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} sıraya alındı: süren toplu işin hemen ardından aynı ayarlarla dönüştürülür.",
    "+ {files} added": "+ {files} eklendi",
    "Add IFC files": "IFC dosyası ekle",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "IFC dosyaları (*.ifc *.IFC *.ifczip *.ifcZIP);;Tüm dosyalar (*)",
    "Add a folder with IFC files": "IFC dosyaları içeren bir klasör ekle",
    "Written: {path}": "Yazıldı: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} atlandı (geometri çekirdeği çöktü veya takıldı)",
    "Only the building hull: {inside} (interior elements)": "Yalnızca bina kabuğu: {inside} (iç elemanlar)",
    "List to copy: right-click → “Skipped elements…”": "Kopyalanacak liste: sağ tık → “Atlanan elemanlar…”",
    "The output folder cannot be created:\n{error}": "Çıktı klasörü oluşturulamıyor:\n{error}",
    "next to the IFC files": "IFC dosyalarının yanına",
    "identical elements as blocks": "özdeş elemanlar blok olarak",
    "only the building hull": "yalnızca bina kabuğu",
    "output: {target}": "çıktı: {target}",
    "geometry kernel {kernel}": "geometri çekirdeği {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• İşlem gücü: {resources}",
    "Conversion running …": "Dönüştürme sürüyor …",
    "Cancelling …": "İptal ediliyor …",
    "■ Cancel requested": "■ İptal istendi",
    "Reading IFC ({size}) – may take a few minutes …": "IFC okunuyor ({size}) – birkaç dakika sürebilir …",
    "{file}: new attempt – reading IFC …": "{file}: yeni deneme – IFC okunuyor …",
    "Converting {file} …": "{file} dönüştürülüyor …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Kopyalanacak liste: dosyaya sağ tık → “Atlanan elemanlar…”",
    "✗ Error in {file}: {error}": "✗ {file} dosyasında hata: {error}",
    "{done} of {files} done": "{files} dosyadan {done} tanesi tamamlandı",
    "{count} with errors": "{count} hatalı",
    "cancelled": "iptal edildi",
    "• 1 queued file not converted – “Convert” starts it.": "• Sıradaki 1 dosya dönüştürülmedi – “Dönüştür” başlatır.",
    "• {count} queued files not converted – “Convert” starts them.": "• Sıradaki {count} dosya dönüştürülmedi – “Dönüştür” başlatır.",
    "▶ Continuing with {files}, added during the conversion": "▶ Dönüştürme sırasında eklenen {files} ile devam ediliyor",
    "Cancelled after {duration}": "{duration} sonra iptal edildi",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ {done} tamamlandı, {failed} hatalı – {duration} sonra",
    "✗ {failed} with errors – after {duration}": "✗ {failed} hatalı – {duration} sonra",
    "Error": "Hata",
    "✓ Done after {duration}": "✓ {duration} sonra tamamlandı",
    "✓ Done": "✓ Tamamlandı",
    "{done} of {files} done – %p%": "{files} dosyadan {done} tamamlandı – %%p",
    "✗ The output folder does not exist (yet): {path}": "✗ Çıktı klasörü (henüz) yok: {path}",
    "Add files and click “Convert”.": "Dosya ekleyip “Dönüştür”e tıklayın.",
    "The conversion is still running.": "Dönüştürme hâlâ sürüyor.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "“{file}” dönüştürülüyor; dönüştürme {since} süredir sürüyor (%{percent}).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Çıkmak dönüştürmeyi iptal eder ve ilerlemesi kaybolur. Yine de çıkılsın mı?",
    "Select a file in the list – its preview appears here.": "Listeden bir dosya seçin – önizlemesi burada görünür.",
    "The 3D view is not available on this PC.": "3D görünüm bu bilgisayarda kullanılamıyor.",
    "Compute preview": "Önizlemeyi hesapla",
    "Computes the preview of this file now (low priority, at most 4 threads); it is kept for next time.": "Bu dosyanın önizlemesini şimdi hesaplar (düşük öncelik, en fazla 4 iş parçacığı); bir sonraki sefer için saklanır.",
    "Stop computing the preview": "Önizleme hesaplamasını durdur",
    "Reset view": "Görünümü sıfırla",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Başlangıç görünümü: tüm model güneybatıdan, yukarıdan (Home; çift tık: tüm model)",
    "Preview – {file}": "Önizleme – {file}",
    "Computing preview …": "Önizleme hesaplanıyor …",
    "No preview possible: {error}": "Önizleme yapılamıyor: {error}",
    "The file is not (or no longer) accessible.": "Dosyaya (artık) erişilemiyor.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Dönüştürmeyi yavaşlatmamak için dönüştürme sürerken önizleme hesaplanmaz.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Büyük dosya ({size}): önizleme birkaç dakika sürer. Düşük öncelikle çalışır ve bir sonraki sefer için saklanır.",
    "Waiting for the running preview to finish …": "Süren önizlemenin bitmesi bekleniyor …",
    "Computing preview: reading the IFC file …": "Önizleme hesaplanıyor: IFC dosyası okunuyor …",
    "Loading preview …": "Önizleme yükleniyor …",
    "Preview cancelled.": "Önizleme iptal edildi.",
    "The preview could not be loaded.": "Önizleme yüklenemedi.",
    "The file contains no geometry that can be shown.": "Dosyada gösterilebilecek geometri yok.",
    "Computing preview … {percent}%": "Önizleme hesaplanıyor … %{percent}",
    "Preview: {status}": "Önizleme: {status}",
    "Try again": "Yeniden dene",
    "{count} small elements left out": "{count} küçük eleman dışarıda bırakıldı",
    "Renderer: {renderer}": "İşleyici: {renderer}",
    "Click an element to see its class, GlobalId and name": "Sınıfını, GlobalId'sini ve adını görmek için bir elemana tıklayın",
    "Iso": "İzo",
    "Isometric view from the south-west (1)": "Güneybatıdan izometrik görünüm (1)",
    "Top": "Üst",
    "Plan view, north up (2)": "Plan görünümü, kuzey yukarıda (2)",
    "Front": "Ön",
    "View from the south (3)": "Güneyden görünüm (3)",
    "Side": "Yan",
    "View from the east (4)": "Doğudan görünüm (4)",
    "Show the whole model (F, double-click)": "Tüm modeli göster (F, çift tık)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "Dosya farklı birimlere sahip {count} proje içeriyor; tümü ilk projenin ({name}) birimleriyle okunur. Lütfen ölçüleri kontrol edin.",
    '{declared} is read as {target} (the same schema under another name).':
        '{declared}, {target} olarak okunur (aynı şemanın başka adı).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Dosyanın çalışma kopyası için geçici klasörde yeterli boş alan yok ({needed} gerekli, {free} boş).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'IFC dosyası kesilmiş görünüyor (sonunda END-ISO-10303-21 yok): çıktı eksik olabilir.',
    # interactive.py (night-app)
    "Cannot write to the output folder {folder} ({error})": "Çıktı klasörüne {folder} yazılamıyor ({error})",
    "Show edges (E)": "Kenarları göster (E)",
    "Parallel projection instead of perspective (P)": "Perspektif yerine paralel izdüşüm (P)",
}
