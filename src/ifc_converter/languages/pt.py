"""User interface texts: pt (see ifc_converter.i18n)."""

TEXTS: dict[str, str] = {

    # --- core ---
    # checkpoint.py
    "Checkpoint {name} not readable ({error}), computed again":
        "Estado intermédio {name} ilegível ({error}), é recalculado",
    "Checkpoint cannot be saved ({error}); continuing without one":
        "Não foi possível guardar o estado intermédio ({error}); continua-se sem ele",
    # converter.py
    'Unsupported format "{fmt}"; possible formats: {formats}':
        "Formato “{fmt}” não suportado; formatos possíveis: {formats}",
    'Unsupported geometry kind "{geometry}"; possible kinds: {kinds}':
        "Tipo de geometria “{geometry}” não suportado; tipos possíveis: {kinds}",
    'Unknown geometry kernel "{kernel}"; possible kernels: {kernels}':
        "Núcleo geométrico “{kernel}” desconhecido; núcleos possíveis: {kernels}",
    "IFC file not found: {path}": "Ficheiro IFC não encontrado: {path}",
    "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program as .ifc "
    "(STEP text format) or .ifczip.":
        "O IfcOpenShell não consegue ler ficheiros ifcXML ({name}). Exporte o modelo do programa de autoria como "
        ".ifc (formato de texto STEP) ou .ifczip.",
    "Reading IFC file ({size}) …": "A ler o ficheiro IFC ({size}) …",
    "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the closest related "
    "schema.":
        "Versão IFC não suportada ({error}). Suportadas: {supported}; além disso, {bridges} são lidas como o "
        "esquema mais próximo.",
    "{note} Dimensions and positions stay unchanged.": "{note} Dimensões e posições mantêm-se inalteradas.",
    "Determining the building hull (geometry roughly precomputed) …":
        "A determinar a envolvente (geometria pré-calculada de forma grosseira) …",
    "Computing geometry ({threads} threads) …": "A calcular a geometria ({threads} threads) …",
    "No geometry produced: none of the {count} elements with geometry could be converted (probably unsupported "
    "geometry types).":
        "Nenhuma geometria produzida: nenhum dos {count} elementos com geometria pôde ser convertido "
        "(provavelmente tipos de geometria não suportados).",
    "The file contains no elements with geometry.": "O ficheiro não contém elementos com geometria.",
    "Copying to the target folder ({size}) …": "A copiar para a pasta de destino ({size}) …",
    "Copying failed ({error}) – attempt {attempt} in {seconds} s …":
        "A cópia falhou ({error}) – tentativa {attempt} dentro de {seconds} s …",
    "Copying to the target folder … {copied} of {total}": "A copiar para a pasta de destino … {copied} de {total}",
    "The finished file could not be copied to {folder} ({error}).":
        "Não foi possível copiar o ficheiro final para {folder} ({error}).",
    "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.":
        "Não foi possível copiar o ficheiro final para {folder} ({error}). Está aqui: {path} – copie-o "
        "manualmente.",
    "{count} extrusions with negative depth turned around": "{count} extrusões com profundidade negativa invertidas",
    "{finished} elements taken over from the previous attempt, {count} are computed":
        "{finished} elementos aproveitados da tentativa anterior, {count} são calculados",
    "Geometry contains itself (faulty file), not converted: {label}":
        "A geometria contém-se a si própria (ficheiro defeituoso), não convertida: {label}",
    "Deeply nested element ({depth} levels) {number} of {total} is computed on its own: {label} …":
        "Elemento muito aninhado ({depth} níveis) {number} de {total} é calculado isoladamente: {label} …",
    "Element {number} of {total} is computed on its own: {label} …":
        "Elemento {number} de {total} é calculado isoladamente: {label} …",
    "{count} elements only computed in the second attempt (finer tolerance or other kernel)":
        "{count} elementos só calculados na segunda tentativa (tolerância mais fina ou outro núcleo)",
    "Second attempts ended after {seconds} s; further elements without geometry were not tried on their own any "
    "more":
        "Segundas tentativas terminadas após {seconds} s; os restantes elementos sem geometria já não foram "
        "tentados isoladamente",
    "{count} geometry computations are still running after {seconds} s and are ended in the background":
        "{count} cálculos de geometria ainda decorrem após {seconds} s e são terminados em segundo plano",
    "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other programs, "
    "otherwise it gets very slow or the conversion breaks off.":
        "{name} precisará provavelmente de cerca de {needed} GB de memória, só estão livres {available} GB. Feche "
        "outros programas, senão tudo fica muito lento ou a conversão é interrompida.",
    # envelope.py
    "{voxel} m, coarse {coarse}": "{voxel} m, grosseiro {coarse}",
    "Building hull only: The model has no closed hull (missing roof, missing floors or walls, e.g. a partial model "
    "without the shell): the outside air reaches almost all elements (grid {voxel} m). Left out instead: {marked} "
    "elements marked as interior (IsExternal = No) and {fittings} furniture, fittings, pipes and ducts, ceiling and "
    "floor finishes; {kept} of {total} elements are converted.":
        "Só envolvente: o modelo não tem envolvente fechada (falta a cobertura, faltam lajes ou paredes, p. ex. um "
        "modelo parcial sem a estrutura): o ar exterior chega a quase todos os elementos (grelha {voxel} m). "
        "Em vez disso, omitidos: {marked} elementos marcados como interiores (IsExternal = Não) e {fittings} "
        "mobiliário, equipamentos, tubagens e condutas, revestimentos de tetos e pavimentos; {kept} de {total} "
        "elementos são convertidos.",
    "Building hull only: {kept} of {total} elements are on the outside and are converted, {inside} interior ones "
    "left out (grid {voxel} m)":
        "Só envolvente: {kept} de {total} elementos estão no exterior e são convertidos, {inside} interiores "
        "omitidos (grelha {voxel} m)",
    "; {count} without pre-computed geometry taken over to be safe":
        "; {count} sem geometria pré-calculada mantidos por segurança",
    "; {count} marked as exterior (IsExternal) taken over":
        "; {count} marcados como exteriores (IsExternal) mantidos",
    "; {count} massing volumes (envelopes around the model) not counted as opaque":
        "; {count} volumes de massa (envolventes em torno do modelo) não contados como opacos",
    "{count} more": "mais {count}",
    " Left out: {classes}.": " Omitidos: {classes}.",
    "Determining the building hull (searching for the outside air) …":
        "A determinar a envolvente (à procura do ar exterior) …",
    "Building hull: {kept} of {total} elements outside ({unknown} without pre-computed geometry, {flagged} by "
    "IsExternal), grid {voxel} m (coarse {coarse} m, {cells} cells, fine band {band} cells), pre-computed geometry "
    "{coarse_seconds} s, hull {hull_seconds} s":
        "Envolvente: {kept} de {total} elementos no exterior ({unknown} sem geometria pré-calculada, {flagged} por "
        "IsExternal), grelha {voxel} m (grosseira {coarse} m, {cells} células, faixa fina {band} células), "
        "geometria pré-calculada {coarse_seconds} s, envolvente {hull_seconds} s",
    "Building hull: grid coarsened to {voxel} m ({cells} grid cells stored)":
        "Envolvente: grelha engrossada para {voxel} m ({cells} células guardadas)",
    # preview.py
    "Saving preview ({count} triangles) …": "A guardar a pré-visualização ({count} triângulos) …",
    "Too many triangles for the preview (more than {limit} per element).":
        "Demasiados triângulos para a pré-visualização (mais de {limit} por elemento).",
    # process.py
    "stack overflow": "excesso de pilha (stack overflow)",
    "The memory was not enough (the process was ended by the system)":
        "A memória não chegou (o processo foi terminado pelo sistema)",
    "Crash in the fast geometry kernel – retrying with OpenCASCADE only …":
        "Falha no núcleo geométrico rápido – nova tentativa só com OpenCASCADE …",
    "Crash in the geometry kernel ({fatal}), after which the conversion was stuck":
        "Falha no núcleo geométrico ({fatal}), após a qual a conversão ficou bloqueada",
    "The conversion has not computed anything for {duration} (it was stuck)":
        "A conversão não calculou nada durante {duration} (estava bloqueada)",
    "{count} minutes": "{count} minutos",
    "{count} seconds": "{count} segundos",
    "stack overflow in the geometry kernel": "excesso de pilha no núcleo geométrico",
    "memory access violation": "violação de acesso à memória",
    "internal program abort": "aborto interno do programa",
    "Conversion ended without a result": "Conversão terminou sem resultado",
    "Conversion crashed: {name} (code {code})": "A conversão falhou: {name} (código {code})",
    "Conversion crashed (code {code})": "A conversão falhou (código {code})",
    "Crash in the geometry kernel ({fatal})": "Falha no núcleo geométrico ({fatal})",
    "Hang in the geometry kernel": "Bloqueio no núcleo geométrico",
    "Crash in the geometry kernel": "Falha no núcleo geométrico",
    "New attempt ({attempt}. of at most {max})": "Nova tentativa ({attempt}.ª de no máximo {max})",
    "{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …":
        "{what} nos eixos (IfcAlignment, IfcGrid). {again} sem os eixos …",
    "{what} at {label}. {again}, this element is skipped …":
        "{what} em {label}. {again}, este elemento é ignorado …",
    "{what} at one element. {again}, it is computed first and on its own …":
        "{what} num elemento. {again}, é calculado primeiro e isoladamente …",
    "{what} at one of {count} elements. {again}, these are computed first and on their own to find the affected "
    "one …":
        "{what} num de {count} elementos. {again}, estes são calculados primeiro e isoladamente para encontrar o "
        "afetado …",
    "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}":
        "Conversão: {input} ({size}) -> {output}, formato {fmt}, {threads} threads{options}{priority}",
    "(next to the IFC file)": "(junto ao ficheiro IFC)",
    ", normal priority": ", prioridade normal",
    "Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or hung) ({count}):\n"
    "  {elements}":
        "Conhecidos de conversões anteriores deste ficheiro, ignorados (o núcleo geométrico falhou ou bloqueou "
        "neles) ({count}):\n  {elements}",
    ", already computed elements are taken over …": ", os elementos já calculados são aproveitados …",
    " (exit code {code})": " (código de saída {code})",
    "Cancelled after {seconds} s: {path}": "Cancelada após {seconds} s: {path}",
    "Error after {seconds} s at {path}: {type}: {error}\n{details}":
        "Erro após {seconds} s em {path}: {type}: {error}\n{details}",
    "Crash after {seconds} s at {path}: {error} (exit code {code})":
        "Falha após {seconds} s em {path}: {error} (código de saída {code})",
    "Stuck, cancelled after {seconds} s: {path}": "Bloqueada, cancelada após {seconds} s: {path}",
    "Conversion of {path} failed": "A conversão de {path} falhou",
    "Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, {skipped} "
    "skipped":
        "Concluída após {seconds} s: {input} -> {output}, {elements} elementos, {missing} sem geometria, {skipped} "
        "ignorados",
    "Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}":
        "Ignorados porque o núcleo geométrico falhou ou bloqueou neles ({count}):\n  {elements}",
    "Without geometry ({count}):\n  {elements}{more}": "Sem geometria ({count}):\n  {elements}{more}",
    "\n  … and {count} more": "\n  … e mais {count}",
    "Too little room in the temp folder for a checkpoint; after a crash everything is computed again":
        "Pouco espaço na pasta temporária para um estado intermédio; após uma falha tudo é recalculado",
    "size unknown": "tamanho desconhecido",
    "Memory limit of the conversion process ({limit} GB) reached":
        "Limite de memória do processo de conversão ({limit} GB) atingido",
    "Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the end (e.g. without "
    "worker processes)":
        "Limite de memória do processo de conversão ({limit} GB) atingido, a conversão chegou mesmo assim ao fim "
        "(p. ex. sem processos auxiliares)",
    "The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so that other "
    "programs keep running. For this file the PC needs more memory.":
        "A memória não chegou: a conversão pode usar no máximo {limit} GB ({share} % da memória), para que os "
        "outros programas continuem a funcionar. Para este ficheiro o PC precisa de mais memória.",
    "Job object for the conversion not available ({error}), continuing without a memory limit":
        "Objeto de trabalho (job) para a conversão indisponível ({error}), continua-se sem limite de memória",
    "Conversion process not in the job object ({error}), continuing without a memory limit":
        "Processo de conversão fora do objeto de trabalho (job) ({error}), continua-se sem limite de memória",
    "Skipped elements could not be saved ({path}): {error}":
        "Não foi possível guardar os elementos ignorados ({path}): {error}",
    "{message} (after {seconds} s)": "{message} (após {seconds} s)",
    "Running for {seconds} s, {percent} %: {message}": "A decorrer há {seconds} s, {percent} %: {message}",
    "{message}: {size} written …": "{message}: {size} escritos …",
    "No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}":
        "Sem atividade de cálculo há {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
    " after {fatal}": " após {fatal}",
    "The conversion process reports a fatal error: {marker}":
        "O processo de conversão comunica um erro fatal: {marker}",
    " (last {shown} KB of {size} KB)": " (últimos {shown} KB de {size} KB)",
    "Output of the conversion process{cut}:\n{message}": "Saída do processo de conversão{cut}:\n{message}",
    "The conversion process {pid} could not be ended": "Não foi possível terminar o processo de conversão {pid}",
    # rhino.py
    "Rhino geometry crashed a worker process, taken over as a mesh instead: {label}":
        "A geometria Rhino fez falhar um processo auxiliar, aproveitada em vez disso como malha: {label}",
    "Rhino geometry crashed a worker process, element left out: {label}":
        "A geometria Rhino fez falhar um processo auxiliar, elemento omitido: {label}",
    "Writing Rhino file ({count} objects) …": "A escrever o ficheiro Rhino ({count} objetos) …",
    # schema_bridge.py
    "IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.":
        "IFC2x2 (2003) é lido como IFC2x3, que herdou as suas entidades e atributos.",
    "IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, IfcTunnelPart as "
    "IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as IfcBuildingElementProxy; dataset references "
    "(IfcDataSetInformation) are dropped.":
        "IFC4x4 é um rascunho não publicado (túneis) e é lido como IFC4.3: IfcTunnel como IfcFacility, "
        "IfcTunnelPart como IfcFacilityPart, IfcUndergroundExcavation e IfcArchElement como "
        "IfcBuildingElementProxy; as referências a conjuntos de dados (IfcDataSetInformation) são descartadas.",
    "IFC4x4 (draft)": "IFC4x4 (rascunho)",
    "{count} entities renamed": "{count} entidades renomeadas",
    "{count} left out": "{count} omitidos",
    # serializers.py
    "Writing GLB file …": "A escrever o ficheiro GLB …",
    "Writing OBJ file …": "A escrever o ficheiro OBJ …",
    "Writing STEP file (exact surfaces, takes minutes for large models) …":
        "A escrever o ficheiro STEP (superfícies exatas, demora minutos em modelos grandes) …",
    "Writing DAE file …": "A escrever o ficheiro DAE …",
    "The {fmt} file could not be written: the serializer took none of the {count} elements.":
        "Não foi possível escrever o ficheiro {fmt}: o serializador não aceitou nenhum dos {count} elementos.",
    # --- dialogs ---
    # interactive.py helpers (window and command line)
    "These elements have geometry that could not be converted – e.g. unsupported geometry types, or their "
    "openings cut them away completely.":
        "Estes elementos têm geometria que não pôde ser convertida – p. ex. tipos de geometria não suportados, ou "
        "as suas aberturas recortam-nos por completo.",
    "Help → Open log file": "Ajuda → Abrir ficheiro de registo",
    "1 element without geometry": "1 elemento sem geometria",
    "{count} elements without geometry": "{count} elementos sem geometria",
    " … and {count} more (all of them in the log file)": " … e mais {count} (todos no ficheiro de registo)",
    "1 element skipped because the geometry kernel crashed or hung on it: {names}{more}. "
    "In the CAD program it can be found by its GlobalId.":
        "1 elemento ignorado porque o núcleo geométrico falhou ou bloqueou nele: {names}{more}. "
        "No programa CAD encontra-se pelo seu GlobalId.",
    "{count} elements skipped because the geometry kernel crashed or hung on them: {names}{more}. "
    "In the CAD program they can be found by their GlobalId.":
        "{count} elementos ignorados porque o núcleo geométrico falhou ou bloqueou neles: {names}{more}. "
        "No programa CAD encontram-se pelo seu GlobalId.",
    "There was not enough memory": "A memória não chegou",
    "The file could not be read as IFC (damaged or not an IFC file): {message}":
        "Não foi possível ler o ficheiro como IFC (danificado ou não é um ficheiro IFC): {message}",
    "The file could not be read as IFC (damaged or not an IFC file)":
        "Não foi possível ler o ficheiro como IFC (danificado ou não é um ficheiro IFC)",
    "File or network error: {message}": "Erro de ficheiro ou de rede: {message}",
    "Internal error ({name}): {message}": "Erro interno ({name}): {message}",
    "Internal error ({name})": "Erro interno ({name})",
    "Please attach the log file ({log}) when reporting the error.":
        "Anexe o ficheiro de registo ({log}) ao comunicar o erro.",
    "Details are in the log file ({log}).": "Os detalhes estão no ficheiro de registo ({log}).",
    "up to 1 thread (of {cores} logical cores)": "até 1 thread (de {cores} núcleos lógicos)",
    "up to {threads} threads (of {cores} logical cores)": "até {threads} threads (de {cores} núcleos lógicos)",
    "{threads_text}, plus up to {workers} helper processes for the Rhino geometry with large 3DM models":
        "{threads_text}, mais até {workers} processos auxiliares para a geometria Rhino com modelos 3DM grandes",
    "{threads_text}, low priority – other programs take precedence": "{threads_text}, prioridade baixa – os outros programas têm precedência",
    "{threads_text}, normal priority": "{threads_text}, prioridade normal",
    "{integer}.{fraction}": "{integer},{fraction}",  # the decimal mark
    "{seconds} s": "{seconds} s",
    "{minutes} min {seconds} s": "{minutes} min {seconds} s",
    "{hours} h {minutes} min": "{hours} h {minutes} min",
    "{thousands},{hundreds}": "{thousands}.{hundreds}",  # the thousands separator: 117,137 -> 117.137
    "1 interior element left out": "1 elemento interior omitido",
    "{count} interior elements left out": "{count} elementos interiores omitidos",
    # app.py
    "not available": "não disponível",
    # anonymize.py: the placeholders in the anonymised log
    "<user>": "<utilizador>",
    "<computer>": "<computador>",
    "<server>": "<servidor>",
    "<share>": "<partilha>",
    "<folder>": "<pasta>",
    "File": "Ficheiro",
    # dialogs.py: geometry kernels
    "Accurate (recommended)": "Preciso (recomendado)",
    "Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
    "fast kernel, which takes them over unchanged.":
        "Cada elemento completo e igual em cada execução; só as grandes malhas triangulares (terreno) vão para o "
        "núcleo rápido, que as aproveita sem alterações.",
    "Fast": "Rápido",
    "3 to 13 times faster, but may drop or duplicate faces of some elements.":
        "3 a 13 vezes mais rápido, mas pode omitir ou duplicar faces de alguns elementos.",
    "OpenCASCADE only": "Só OpenCASCADE",
    "Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large terrain).":
        "Tudo com OpenCASCADE, também os modelos de terreno: aí muito lento (mais de 20 minutos para um terreno "
        "grande).",
    # dialogs.py: anonymised log
    "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
    "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
    "sizes, versions and error messages are kept.":
        "Substitui nomes de utilizadores e computadores, servidores e partilhas de unidades de rede, nomes de "
        "pastas (<pasta>) e de ficheiros (Ficheiro-1.ifc, Ficheiro-1.3dm …) e omite os nomes dos elementos. "
        "Mantêm-se a classe IFC e o GlobalId, tempos, tamanhos, versões e mensagens de erro.",
    "There is no log file yet in {folder}.": "Ainda não há nenhum ficheiro de registo em {folder}.",
    "Save anonymised log file": "Guardar ficheiro de registo anonimizado",
    "Text files (*.txt);;All files (*)": "Ficheiros de texto (*.txt);;Todos os ficheiros (*)",
    "The anonymised log file could not be saved:\n{error}":
        "Não foi possível guardar o ficheiro de registo anonimizado:\n{error}",
    "The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
    "Please look through it briefly before sending. Open the folder now?":
        "O ficheiro de registo anonimizado foi guardado:\n{path}\n\n{hint}\n\n"
        "Reveja-o brevemente antes de o enviar. Abrir a pasta agora?",
    # dialogs.py: settings
    "Settings": "Definições",
    "Performance": "Desempenho",
    "Geometry kernel": "Núcleo geométrico",
    "Output": "Saída",
    "Log file": "Ficheiro de registo",
    "OK": "OK",
    "Apply and save the settings": "Aplicar e guardar as definições",
    "Cancel": "Cancelar",
    "Discard changes": "Rejeitar as alterações",
    "Defaults": "Predefinições",
    "Reset all settings to their defaults": "Repor todas as definições nos valores predefinidos",
    "At most this many threads:": "Número máximo de threads:",
    "Automatic ({threads})": "Automático ({threads})",
    "0 or “Automatic” leaves some cores free and takes fewer when little RAM is free.":
        "0 ou “Automático” deixa alguns núcleos livres e usa menos quando há pouca RAM livre.",
    "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
    "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
    "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
    "little RAM is free; each thread can need up to about 1 GB with large elements.":
        "Tantos núcleos do processador calculam a geometria em simultâneo. Menos threads atrasam menos os outros "
        "programas, mas a conversão demora mais. “Automático” usa até {threads} dos {cores} núcleos lógicos "
        "deste PC (cerca de metade, contando os processos auxiliares da saída Rhino) e menos quando há pouca RAM "
        "livre; cada thread pode precisar de até cerca de 1 GB com elementos grandes.",
    "Convert at low priority (recommended)": "Converter com prioridade baixa (recomendado)",
    "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
    "and stay responsive; the conversion only uses the processing time they leave over. Without this "
    "setting it competes with them on equal terms.":
        "A conversão corre com a prioridade do Windows “Abaixo do normal”: Rhino, Revit e afins têm precedência e "
        "continuam a responder; a conversão só usa o tempo de processamento que eles deixam. Sem esta definição "
        "concorre com eles em pé de igualdade.",
    "What the geometry of the elements is computed with. Applies to all output formats.":
        "Com que se calcula a geometria dos elementos. Aplica-se a todos os formatos de saída.",
    "Open the output folder after the conversion": "Abrir a pasta de destino após a conversão",
    "Opens the folder in Explorer as soon as all files are converted.":
        "Abre a pasta no Explorador assim que todos os ficheiros estiverem convertidos.",
    "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
    "The IFC files themselves are never changed.":
        "Os ficheiros existentes nunca são substituídos – se o nome já existir, acrescenta-se (2), (3) … "
        "Os próprios ficheiros IFC nunca são alterados.",
    "Identical elements as blocks (smaller file)": "Elementos idênticos como blocos (ficheiro mais pequeno)",
    "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
    "The file gets smaller, but block instances behave differently from normal objects:\n"
    "To edit the geometry, an instance has to be exploded first (_Explode).\n"
    "User texts, layer and colour are on the instance.":
        "Elementos com a mesma geometria de tipo (janelas, portas, mobiliário …) tornam-se instâncias de um bloco "
        "Rhino.\n"
        "O ficheiro fica mais pequeno, mas as instâncias de bloco comportam-se de forma diferente dos objetos "
        "normais:\n"
        "para editar a geometria, uma instância tem de ser primeiro explodida (_Explode).\n"
        "Textos de utilizador, camada e cor estão na instância.",
    "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
    "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
    "has to be exploded first (_Explode).":
        "A geometria de tipo partilhada por vários elementos (janelas, portas, mobiliário …) é guardada uma vez "
        "como bloco e inserida como instância por elemento: ficheiro 20–45 % mais pequeno. Para a editar no "
        "Rhino, uma instância de bloco tem de ser primeiro explodida (_Explode).",
    "Log file:": "Ficheiro de registo:",
    "Settings:": "Definições:",
    "Open log file": "Abrir ficheiro de registo",
    "Opens the current log file in the default program for text files.":
        "Abre o ficheiro de registo atual no programa predefinido para ficheiros de texto.",
    "Save anonymised…": "Guardar anonimizado…",
    "Anonymise log file": "Anonimizar o ficheiro de registo",
    "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
    "no user, computer, server, folder, file or element names.":
        "O ficheiro de registo fica neste PC; nada é enviado automaticamente. Ativado, a partir de agora não "
        "contém nomes de utilizadores, computadores, servidores, pastas, ficheiros nem elementos.",
    "With this, a conversion uses {resources}.": "Com isto, uma conversão usa {resources}.",
    # dialogs.py: about
    "About {app}": "Acerca de {app}",
    "Version {version}": "Versão {version}",
    "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
    "no internet connection, no telemetry, no automatic updates.":
        "Converte modelos de edifícios IFC em ficheiros Rhino (3DM), GLB e OBJ. Funciona totalmente em local: "
        "sem ligação à Internet, sem telemetria, sem atualizações automáticas.",
    "Components": "Componentes",
    "Component": "Componente",
    "Version": "Versão",
    "Licence": "Licença",
    "The libraries are included unchanged. The full licence texts are in the program folder in "
    "THIRD-PARTY-NOTICES.txt and in the folder “licenses”.":
        "As bibliotecas estão incluídas sem alterações. Os textos completos das licenças estão na pasta do "
        "programa em THIRD-PARTY-NOTICES.txt e na pasta “licenses”.",
    "Source code:": "Código-fonte:",
    "Copy version info": "Copiar info da versão",
    "Copies the program and component versions as text, e.g. for a bug report.":
        "Copia as versões do programa e dos componentes como texto, p. ex. para um relatório de erro.",
    "Close": "Fechar",
    "Copied ✓": "Copiado ✓",
    # dialogs.py: unexpected error
    "{app} – Unexpected error": "{app} – Erro inesperado",
    "<b>An unexpected error occurred.</b><br>"
    "The program keeps running. If something no longer works, please restart it.<br>"
    "To report the problem, copy the details and send them along.":
        "<b>Ocorreu um erro inesperado.</b><br>"
        "O programa continua a funcionar. Se algo deixar de funcionar, reinicie-o.<br>"
        "Para comunicar o problema, copie os detalhes e envie-os juntamente.",
    "Copy details": "Copiar detalhes",
    # dialogs.py: skipped elements
    "Skipped (geometry kernel crashed)": "Ignorados (núcleo geométrico falhou)",
    "Without geometry": "Sem geometria",
    "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
    "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
    "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer.":
        "Como encontrar um elemento no programa CAD: copie o GlobalId e procure-o – no ArchiCAD com "
        "“Localizar e Selecionar” (Ctrl+F) pela propriedade IFC GlobalId ou “Archicad IFC ID”, no Revit pelo "
        "parâmetro “IfcGUID” (p. ex. numa tabela ou com um filtro), caso contrário em qualquer visualizador IFC.",
    "Reason": "Motivo",
    "Class": "Classe",
    "GlobalId": "GlobalId",
    "Name": "Nome",
    "Skipped elements – {file}": "Elementos ignorados – {file}",
    "{count} skipped because the geometry kernel crashed or hung on them":
        "{count} ignorados porque o núcleo geométrico falhou ou bloqueou neles",
    "{count} without geometry (not convertible)": "{count} sem geometria (não convertíveis)",
    "{inside} (building hull only)": "{inside} (só envolvente)",
    "Copy": "Copiar",
    "{count} more elements without geometry could not be named individually.":
        "Mais {count} elementos sem geometria não puderam ser indicados individualmente.",
    "The interior elements left out because of “Building hull only” are not listed individually; "
    "without the option they are converted too.":
        "Os elementos interiores omitidos por “Só a envolvente” não são listados individualmente; sem a opção "
        "também são convertidos.",
    "Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an e-mail.":
        "Selecionar e Ctrl+C copia as linhas escolhidas (Ctrl+A: todas), como tabela para colar no Excel ou num "
        "e-mail.",
    "Copy all": "Copiar tudo",
    "Copies the whole table, to paste into Excel or an e-mail.":
        "Copia a tabela inteira, para colar no Excel ou num e-mail.",
    # --- gui --- (gui.py, preview_pane.py, viewer.py)
    "Rhino file (.3dm) – open and keep working on it directly in Rhino.": "Ficheiro Rhino (.3dm) – abrir e continuar a trabalhar diretamente no Rhino.",
    "glTF binary (.glb) – compact, for web viewers, Blender, Three.js and game engines.": "glTF binário (.glb) – compacto, para visualizadores web, Blender, Three.js e motores de jogo.",
    "Wavefront OBJ (.obj + .mtl) – opens in almost any 3D program.": "Wavefront OBJ (.obj + .mtl) – abre em quase todos os programas 3D.",
    "COLLADA 1.4 (.dae) – triangle meshes with colours, for SketchUp, Blender, Unity and ArchiCAD. Text file, about twice the size of .glb.": "COLLADA 1.4 (.dae) – malhas triangulares com cores, para SketchUp, Blender, Unity e ArchiCAD. Ficheiro de texto, cerca do dobro do tamanho de .glb.",
    "Polysurfaces (recommended)": "Polissuperfícies (recomendado)",
    "Walls, slabs, windows … as closed polysurfaces with real openings. Very detailed objects (furniture, sanitary fittings, lights) stay meshes. The file is 1.2–4.5× larger depending on the model – for very large models, better choose “Meshes”.": "Paredes, lajes, janelas … como polissuperfícies fechadas com aberturas reais. Objetos muito detalhados (mobiliário, sanitários, luminárias) ficam malhas. Ficheiro 1,2–4,5× maior conforme o modelo – em modelos grandes, prefira “Malhas”.",
    "Meshes": "Malhas",
    "Smallest files, fastest conversion. Curved surfaces smoothly shaded, edges sharp.": "Ficheiros mais pequenos, conversão mais rápida. Superfícies curvas com sombreado suave, arestas vivas.",
    "Only the building hull": "Só a envolvente",
    "Converts only the building hull, i.e. what can be seen from outside: exterior walls, roofs, windows, doors, balconies, terrain … Interior walls, furniture, fittings, pipes and ducts are left out; the file gets much smaller (e.g. for context models or weaker PCs).\n\nFor this, a short extra pass first computes a coarse geometry of all elements (the first 25 % of the progress). Elements marked as exterior in the IFC (IsExternal) are always kept; in doubt, an element is rather kept than left out. Dimensions and positions of the converted elements do not change. Applies to every output format.": "Converte só a envolvente do edifício, ou seja, o que se vê do exterior: paredes exteriores, coberturas, janelas, portas, varandas, terreno … Paredes interiores, mobiliário, equipamentos, tubagens e condutas são omitidos; o ficheiro fica muito mais pequeno (p. ex. para modelos de contexto ou PCs mais fracos).\n\nPara isso, uma curta passagem adicional calcula primeiro uma geometria grosseira de todos os elementos (os primeiros 25 % do progresso). Os elementos marcados como exteriores no IFC (IsExternal) são sempre mantidos; na dúvida, um elemento é antes mantido do que omitido. As dimensões e posições dos elementos convertidos não mudam. Aplica-se a todos os formatos de saída.",
    "Reading IFC …": "A ler o IFC …",
    "Converting … {percent}% – {detail}": "A converter … {percent} % – {detail}",
    "Converting … {percent}%": "A converter … {percent} %",
    "{count} without geometry": "{count} sem geometria",
    "Done – {elements}": "Concluído – {elements}",
    "Error: {error}": "Erro: {error}",
    "Cancelled": "Cancelada",
    "Queued – starts afterwards": "Em fila – começa a seguir",
    "Waiting": "À espera",
    "1 file": "1 ficheiro",
    "{count} files": "{count} ficheiros",
    "1 element": "1 elemento",
    "{count} elements": "{count} elementos",
    "Click to open the file dialog (Ctrl+O). Folders are searched for .ifc files.": "Clique para abrir o diálogo de ficheiros (Ctrl+O). Nas pastas procuram-se ficheiros .ifc.",
    "Drop IFC files or folders here": "Largue aqui ficheiros IFC ou pastas",
    "Folders are searched for .ifc and .ifczip files – several at once, too": "Nas pastas procuram-se ficheiros .ifc e .ifczip – também várias de uma vez",
    "Add files…": "Adicionar ficheiros…",
    "Size": "Tamanho",
    "Status": "Estado",
    "Convert IFC building models to 3D formats": "Converter modelos de edifícios IFC em formatos 3D",
    "Double-click a finished file to open its output folder; right-click for more.": "Duplo clique num ficheiro concluído abre a sua pasta de destino; clique direito para mais.",
    "Remove": "Remover",
    "Take the selected files off the list (Del). The files themselves are left untouched.": "Retira os ficheiros selecionados da lista (Del). Os próprios ficheiros ficam intactos.",
    "Clear list": "Limpar lista",
    "Take all files off the list.": "Retira todos os ficheiros da lista.",
    "Skipped elements…": "Elementos ignorados…",
    "Lists the elements of the selected file that were not converted, with class, GlobalId and name (also by right-clicking the row).": "Lista os elementos do ficheiro selecionado que não foram convertidos, com classe, GlobalId e nome (também com clique direito na linha).",
    "Drag to divide the room between list and preview": "Arraste para repartir o espaço entre lista e pré-visualização",
    "Output format": "Formato de saída",
    "Output folder": "Pasta de destino",
    "Change…": "Alterar…",
    "Save next to the IFC file": "Guardar junto ao ficheiro IFC",
    "Existing files are never overwritten: if the name is taken, (2), (3) … is appended.": "Os ficheiros existentes nunca são substituídos: se o nome já existir, acrescenta-se (2), (3) …",
    "Choose the output folder.": "Escolher a pasta de destino.",
    "Each file goes into the folder of its IFC file.": "Cada ficheiro vai para a pasta do seu ficheiro IFC.",
    "Ready": "Pronto",
    "Progress over all files in the list": "Progresso de todos os ficheiros da lista",
    "Log – here you can see what happened to each file.": "Registo – aqui vê-se o que aconteceu a cada ficheiro.",
    "Log of this session. Everything is also in the log file (Help → Open log file).": "Registo desta sessão. Tudo está também no ficheiro de registo (Ajuda → Abrir ficheiro de registo).",
    "Drag to enlarge or shrink the log": "Arraste para aumentar ou reduzir o registo",
    "Log": "Registo",
    "Show or hide the log (F4)": "Mostrar ou ocultar o registo (F4)",
    "Open output folder": "Abrir pasta de destino",
    "Opens the folder of the file written last.": "Abre a pasta do último ficheiro escrito.",
    "Cancel the running conversion. Finished files are kept, the one in progress is deleted.": "Cancela a conversão em curso. Os ficheiros concluídos ficam, o que está em curso é eliminado.",
    "Convert": "Converter",
    "Convert all files in the list (Ctrl+Enter)": "Converter todos os ficheiros da lista (Ctrl+Enter)",
    "Add folder…": "Adicionar pasta…",
    "Quit": "Sair",
    "Settings…": "Definições…",
    "Save anonymised log file…": "Guardar ficheiro de registo anonimizado…",
    "Preview": "Pré-visualização",
    "Choose IFC files (Ctrl+O). Folders: File → Add folder…": "Escolher ficheiros IFC (Ctrl+O). Pastas: Ficheiro → Adicionar pasta…",
    "&File": "&Ficheiro",
    "&Edit": "&Editar",
    "&View": "&Ver",
    "&Tools": "Ferramen&tas",
    "&Help": "A&juda",
    "Language": "Idioma",
    "The user interface switches to {language} when the program is restarted. Restart now?": "A interface muda para {language} quando o programa for reiniciado. Reiniciar agora?",
    "Restart now": "Reiniciar agora",
    "Later": "Mais tarde",
    "Geometry": "Geometria",
    "Output folder: {path}\n\nExisting files are never overwritten: (2), (3) … is appended.": "Pasta de destino: {path}\n\nOs ficheiros existentes nunca são substituídos: acrescenta-se (2), (3) …",
    "Choose output folder": "Escolher pasta de destino",
    "✗ No IFC file found: {path} – only .ifc and .ifczip files and folders holding them (ifcXML cannot be read)": "✗ Nenhum ficheiro IFC encontrado: {path} – só ficheiros .ifc e .ifczip e pastas que os contenham (ifcXML não pode ser lido)",
    "• Already in the list: {names}": "• Já na lista: {names}",
    "+ {files} queued: converted right after the running batch, with the same settings.": "+ {files} em fila: convertidos logo a seguir ao lote em curso, com as mesmas definições.",
    "+ {files} added": "+ {files} adicionados",
    "Add IFC files": "Adicionar ficheiros IFC",
    "IFC files (*.ifc *.IFC *.ifczip *.ifcZIP);;All files (*)": "Ficheiros IFC (*.ifc *.IFC *.ifczip *.ifcZIP);;Todos os ficheiros (*)",
    "Add a folder with IFC files": "Adicionar uma pasta com ficheiros IFC",
    "Written: {path}": "Escrito: {path}",
    "⚠ {count} skipped (geometry kernel crashed or hung)": "⚠ {count} ignorados (núcleo geométrico falhou ou bloqueou)",
    "Only the building hull: {inside} (interior elements)": "Só a envolvente: {inside} (elementos interiores)",
    "List to copy: right-click → “Skipped elements…”": "Lista para copiar: clique direito → “Elementos ignorados…”",
    "The output folder cannot be created:\n{error}": "Não é possível criar a pasta de destino:\n{error}",
    "next to the IFC files": "junto aos ficheiros IFC",
    "identical elements as blocks": "elementos idênticos como blocos",
    "only the building hull": "só a envolvente",
    "output: {target}": "destino: {target}",
    "geometry kernel {kernel}": "núcleo geométrico {kernel}",
    "▶ {files} → {what}, {details}": "▶ {files} → {what}, {details}",
    "• Computing power: {resources}": "• Capacidade de cálculo: {resources}",
    "Conversion running …": "Conversão em curso …",
    "Cancelling …": "A cancelar …",
    "■ Cancel requested": "■ Cancelamento pedido",
    "Reading IFC ({size}) – may take a few minutes …": "A ler o IFC ({size}) – pode demorar alguns minutos …",
    "{file}: new attempt – reading IFC …": "{file}: nova tentativa – a ler o IFC …",
    "Converting {file} …": "A converter {file} …",
    "   → List to copy: right-click the file → “Skipped elements…”": "   → Lista para copiar: clique direito no ficheiro → “Elementos ignorados…”",
    "✗ Error in {file}: {error}": "✗ Erro em {file}: {error}",
    "{done} of {files} done": "{done} de {files} concluídos",
    "{count} with errors": "{count} com erros",
    "cancelled": "cancelada",
    "• 1 queued file not converted – “Convert” starts it.": "• 1 ficheiro em fila não convertido – “Converter” inicia-o.",
    "• {count} queued files not converted – “Convert” starts them.": "• {count} ficheiros em fila não convertidos – “Converter” inicia-os.",
    "▶ Continuing with {files}, added during the conversion": "▶ A continuar com {files}, adicionados durante a conversão",
    "Cancelled after {duration}": "Cancelada após {duration}",
    "✗ {done} done, {failed} with errors – after {duration}": "✗ {done} concluídos, {failed} com erros – após {duration}",
    "✗ {failed} with errors – after {duration}": "✗ {failed} com erros – após {duration}",
    "Error": "Erro",
    "✓ Done after {duration}": "✓ Concluído após {duration}",
    "✓ Done": "✓ Concluído",
    "{done} of {files} done – %p%": "{done} de {files} concluídos – %p %",
    "✗ The output folder does not exist (yet): {path}": "✗ A pasta de destino (ainda) não existe: {path}",
    "Add files and click “Convert”.": "Adicione ficheiros e clique em “Converter”.",
    "The conversion is still running.": "A conversão ainda está em curso.",
    "“{file}” is being converted; the conversion has been running for {since} ({percent}%).": "“{file}” está a ser convertido; a conversão decorre há {since} ({percent} %).",
    "Quitting cancels the conversion and its progress is lost. Quit anyway?": "Sair cancela a conversão e o seu progresso perde-se. Sair mesmo assim?",
    "Select a file in the list – its preview appears here.": "Selecione um ficheiro na lista – a sua pré-visualização aparece aqui.",
    "The 3D view is not available on this PC.": "A vista 3D não está disponível neste PC.",
    "Compute preview": "Calcular pré-visualização",
    "Computes the preview of this file now (low priority, at most 4 threads); it is kept for next time.": "Calcula agora a pré-visualização deste ficheiro (prioridade baixa, no máximo 4 threads); fica guardada para a próxima vez.",
    "Stop computing the preview": "Parar o cálculo da pré-visualização",
    "Reset view": "Repor vista",
    "Start view: the whole model from the south-west above (Home; double-click: whole model)": "Vista inicial: o modelo inteiro de sudoeste, de cima (Home; duplo clique: modelo inteiro)",
    "Preview – {file}": "Pré-visualização – {file}",
    "Computing preview …": "A calcular a pré-visualização …",
    "No preview possible: {error}": "Pré-visualização impossível: {error}",
    "The file is not (or no longer) accessible.": "O ficheiro não está (ou já não está) acessível.",
    "No preview is computed while a conversion runs, so as not to slow it down.": "Durante uma conversão não se calcula nenhuma pré-visualização, para não a atrasar.",
    "Large file ({size}): the preview takes a few minutes. It runs at low priority and is kept for next time.": "Ficheiro grande ({size}): a pré-visualização demora alguns minutos. Corre com prioridade baixa e fica guardada para a próxima vez.",
    "Waiting for the running preview to finish …": "À espera que a pré-visualização em curso termine …",
    "Computing preview: reading the IFC file …": "A calcular a pré-visualização: a ler o ficheiro IFC …",
    "Loading preview …": "A carregar a pré-visualização …",
    "Preview cancelled.": "Pré-visualização cancelada.",
    "The preview could not be loaded.": "Não foi possível carregar a pré-visualização.",
    "The file contains no geometry that can be shown.": "O ficheiro não contém geometria que possa ser mostrada.",
    "Computing preview … {percent}%": "A calcular a pré-visualização … {percent} %",
    "Preview: {status}": "Pré-visualização: {status}",
    "Try again": "Tentar de novo",
    "{count} small elements left out": "{count} elementos pequenos omitidos",
    "Renderer: {renderer}": "Renderização: {renderer}",
    "Click an element to see its class, GlobalId and name": "Clique num elemento para ver classe, GlobalId e nome",
    "Iso": "Iso",
    "Isometric view from the south-west (1)": "Vista isométrica de sudoeste (1)",
    "Top": "Topo",
    "Plan view, north up (2)": "Planta, norte para cima (2)",
    "Front": "Frente",
    "View from the south (3)": "Vista de sul (3)",
    "Side": "Lado",
    "View from the east (4)": "Vista de este (4)",
    "All": "Tudo",
    "Show the whole model (F, double-click)": "Mostrar o modelo inteiro (F, duplo clique)",
    # --- lead, 2026-10-21 ---
    "The file holds {count} projects with different units; all of them are read with the units of the first one ({name}). Please check the dimensions.":
        "O ficheiro contém {count} projetos com unidades diferentes; todos são lidos com as unidades do primeiro ({name}). Verifique as dimensões.",
    'cancelled':
        'cancelado',
    'Reading IFC …':
        'A ler IFC …',
    '{declared} is read as {target} (the same schema under another name).':
        '{declared} é lido como {target} (o mesmo esquema com outro nome).',
    'Not enough free space in the temp folder for a working copy of the file ({needed} needed, {free} free).':
        'Espaço livre insuficiente na pasta temporária para uma cópia de trabalho do ficheiro ({needed} necessários, {free} livres).',
    'The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be incomplete.':
        'O ficheiro IFC parece estar truncado (sem END-ISO-10303-21 no fim): a saída pode estar incompleta.',
}
