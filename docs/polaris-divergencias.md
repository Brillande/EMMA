# Polaris en EMMA: decisiones pendientes

Regla del proyecto (2026-09-29): adoptar Polaris es **copiarlo tal cual** (`polaris/`, vigilado
por `backend/tests/test_polaris_copy.py`) y decidir los cambios después, **uno a uno, con el
usuario**. Esta es la lista de lo que hay que decidir. Nada de aquí está cambiado todavía: cada
punto dice qué hace Polaris, qué pide EMMA y qué opciones hay.

Desde entonces cada punto lleva su decisión y su fecha, y los apartados nuevos cuentan cada
ronda. Lo que queda por decidir a día de hoy está al final del §17.

Cuando se decida un punto, el cambio se hace fuera de `polaris/` si se puede (pegamento en
`backend/app/polaris/`) o, si hay que tocar un fichero copiado, se anota en `polaris/ORIGEN.md`
como cambio (AGPL §5a).

---

## 1. Cerebros de nube del registro de Polaris

- **Polaris:** `tools/peripheries.json` registra cerebros de nube (Claude, Gemini, GLM, NVIDIA,
  OpenRouter, Consensus, scite…) además de `local-ollama`.
- **EMMA hoy:** el adaptador le da a `ia.py` un registro con **solo** `local-ollama`, con la URL y
  el modelo de EMMA (`Settings.llm_url`, `Settings.assistant_model` desde el 2026-11-03, §19). Los ficheros de nube están
  copiados pero no se pueden alcanzar. Decisión del usuario: "para lo de nube usamos Ollama".
- **Decidido (2026-09-29): fuera para siempre.** Ningún cerebro de nube ni salida de datos de salud.

## 2. Umbral clínico del modelo local

- **Polaris:** `ia.ask(..., clinico=True)` exige capacidad ≥ 7 (`BTP_CAP_MINIMA_CRITICA`) y su
  registro declara `local-ollama` con capacidad 4, "a propósito". Resultado: **lo clínico se niega
  con el modelo local** (probado en `tests/test_polaris_bridge.py`).
- **EMMA:** su modelo local es otro (`Settings.assistant_model` desde el 2026-11-03, §19; antes `Settings.llm_model`, más grande que el `qwen3:8b` de
  Polaris) y ya tiene su propio comité de verificadores locales.
- **Opciones:** (a) dejarlo así (lo clínico por `ia.py` no se usa); (b) declarar en el registro
  de EMMA la capacidad medida de su modelo; (c) bajar el umbral por variable de entorno. La nota
  del propio registro de Polaris dice que subir la capacidad "es decisión de la titular".
- **Decidido (2026-09-29): se queda negado**, "lo que diga nuestro contexto". La especificación dice
  que las salidas del modelo "no pueden generar directamente acciones clínicas" (§63), que el
  núcleo tiene que funcionar sin él (§65, §82) y EMMA segrega el borrador en Clase C con firma
  humana (invariante 6). Lo clínico no pasa por `ia.py`; lo prueba `tests/test_polaris_bridge.py`.

## 3. Windows: `fcntl`

- **Polaris:** `borde.py` (y `correo`, `pendientes`) importan `fcntl`, que solo existe en Unix. Sin
  él no cargaban 9 herramientas, entre ellas `ia` y `deid`.
- **EMMA hoy:** `backend/app/polaris/compat/fcntl.py` ofrece `flock` con `msvcrt` solo en Windows,
  fuera de la copia; con él cargaban 72 de 73 (recuento de entonces; el vigente lo da
  `polaris/ESTADO.md`). Probado en
  `tests/test_polaris_bridge.py`.
- **Decidido (2026-09-29): aceptado.**
- **Añadido el 2026-10-07 (§17):** `compat/resource.py`, con lo único que pide la copia
  (`getrusage(RUSAGE_SELF).ru_maxrss`), para que `test_visor3d_malla_recorte` —el freno de
  memoria de `_malla` y `_caja_de`, que EMMA usa— corra en Windows. Solo se deja importar desde
  `polaris/tests/test_*.py`: para EMMA no existe (una biblioteca que pruebe `import resource` no
  debe creerse en Unix) y no está entre los ficheros del instalador (`tests/test_packaging.py`).

## 4. Datos no copiados

- `tools/config/` y `tools/personas/`: perfiles y contactos de personas reales, que solo leen las
  herramientas de correo y `radar_personas` (dormidas en EMMA).
- `tools/launchd/` y `tools/hooks/`: fontanería de macOS y de git de la máquina de su autora.
- **Decidido (2026-09-29): fuera.** Son datos de personas reales.

## 5. Visor web de Polaris (`tools/visor3d_web/`)

- Es el visor del preset hígado, tal cual. **No cumple las reglas de interfaz de EMMA:** lesiones
  en coral y selección en amarillo (en EMMA: candidata amarilla, seleccionada verde; F.5-1), y
  textos del caso original ("TC portal", "informe del radiólogo", PET, marcas del radiólogo).
- Solo pinta hígado, porta y vasos: los ojos siguen en el visor propio de EMMA.
- **Pendiente:** qué cambiar (colores, textos) o dejarlo como excepción declarada
  (`compliance/hmi-state-of-the-art.md` §5.13).
- **Decidido (2026-09-29): adaptar colores y textos.** Primer cambio a la copia, en
  `polaris/CAMBIOS.json` y `polaris/ORIGEN.md`: candidata amarilla, seleccionada y cursor verdes,
  textos de EMMA y fuera las columnas de radiólogo, PET, procedencia y comparación. La forma, el
  render y la lógica siguen siendo los de Polaris.

## 6. `visor3d_superpone_focos.py`

- Es un experimento de su autora con los focos óseos de su propio caso (lista `FOCOS` con
  vértebras concretas) y una ruta a su carpeta de marca. Se copió porque estaba en la lista del
  plan; en EMMA no tiene uso.
- **Decidido (2026-10-01): darle uso** (§14): su `alinea()` coloca el mapa de dolor sobre el
  esqueleto real.

## 7. Módulos que EMMA había adaptado (F2)

Criterio: el módulo de EMMA pasa a llamar al original copiado; si las pruebas y mutantes de EMMA
siguen en verde, lo adaptado se borra. Si no, **se queda lo adaptado** hasta que se decida, y aquí
se explica por qué.

**Sustituidos por el original** (ya llaman a `polaris/tools/` por `app.polaris.load`):
`app/interpret/draft.py` (`local._ANTI`), `app/reports/ocr.py` (`ocr_informes._tsv_a_texto` y
constantes), `app/pain/alarm.py` (`sintomas.es_alarma` con la lista `ALARMA` completa),
`app/evidence/tier.py` (`teje`, `senales_desde_registro`), `app/text_guard.py` (listas completas
de `honestidad_lint` y `decision_alto_riesgo`), `app/decision_risk.py` (`disparar`),
`app/volumes/geometry.py` (`ply_binario`, `_caja_de`, `_taubin`, `_malla`, `_icosfera`,
`_elipsoide`, `_diametro_axial_mayor`, `empareja`), `app/volumes/assets.py` (`nifti_limpio` y las
constantes, comprobadas por prueba) y `scripts/mutants.py` (la clase `Campana` de `mutantes.py`).

Los mutantes cuya defensa pasó a ser código de Polaris apuntan ahora a la copia
(`tests/mutants/polaris_*.json`): se mutan solo en la copia temporal de la campaña, nunca en
`polaris/`.

**Cambios visibles que trae usar el original** (no rompen pruebas, pero conviene decidirlos):

- **`text_guard` es más estricto.** Las listas completas de Polaris incluyen disparadores del caso
  oncológico y frases como "no tiene", "telemetría", "y si", "qué lesión". Un borrador real de
  EMMA puede quedar bloqueado por ellas. Opción: recortar las listas desde el adaptador.
- **Etiquetas de nivel de evidencia** con el texto de Polaris ("modelo animal (PRECLÍNICO)",
  "DESCONOCIDO — no clasificable, mírala a mano").
- **Motivo de alto riesgo en la segunda firma**: puede quedar con el texto de Polaris
  ("…panel de élite obligatorio"), que se guarda en el ledger.

**Decidido (2026-09-29) sobre `text_guard`: "evitar que se bloquee manteniéndolo todo".** Todas las
entradas de las listas completas de Polaris se comprueban; bloquean solo la parte clínica que EMMA
ya usaba (absolutos, acciones terapéuticas, deliberación afirmada) y sus reglas propias, y el resto
se enseña a quien firma como aviso (`text_guard.advisories`, `language_notes` del borrador, panel
del borrador). Pruebas en `tests/test_text_guard.py` y mutantes en `tests/mutants/text_guard.json`.

**Decidido (2026-09-29) sobre 7.1 a 7.7: se mantiene lo de EMMA** donde el original hace algo peor
(nombre del paciente legible, ausencias inventadas, telemetría, espaciado, DOI, fracciones). Cada
módulo lo declara en su cabecera como cambio §5a, con la prueba que lo justifica.

### 7.1 `app/interpret/cotejo.py` ← `cotejo_invariante.afirma_estado_alteracion`

- **Polaris:** solo reconoce afirmaciones sobre alteraciones genéticas (un símbolo de gen). Ante
  una frase de ecografía ("No se observa líquido libre", "Deslizamiento pleural presente, sin
  líneas B") devuelve `(False, None)`: no ve nada que cotejar.
- **EMMA:** un borrador del modelo nunca puede decir que un signo está ausente o presente si no
  está anotado así ("no valorable" no cuenta como ausencia).
- **Lo demuestra:** `tests/test_cotejo.py` (`test_an_absence_needs_an_annotated_absence`,
  `test_generate_blocks_an_invented_absence`) y `tests/mutants/cotejo.json`.
- **En juego:** invariantes 6 y 7. Con el original se apagaría la barrera contra ausencias
  inventadas en el borrador.

### 7.2 `app/reports/deid.py` ← `deid.de_identificar_verificado` — **resuelta el 2026-10-01**

Con el commit `e3b588d` el original ya enmascara el nombre del paciente con su etiqueta, y el
usuario decidió pasar al original ("actualízalo"). Lo que sigue abajo es la historia; lo vigente
está en el §12.

- **Polaris:** con un informe como los de EMMA deja legible "Paciente: Ana Lopez Garcia" y aun así
  lo da por verificado; además quita todas las tildes y enmascara la fecha de la analítica.
- **EMMA:** enmascara el nombre con su etiqueta u honorífico ("Firmado por: Dra. …"), conserva la
  etiqueta y las tildes, y no enmascara fechas que no son de nacimiento.
- **Lo demuestra:** `tests/test_reports.py` (`deid.deidentify(REPORT)`, casos "Firmado por").
- **En juego:** peligro H17 de `compliance/risk-management-file.md` (texto de informe enviado a
  Tierra). El original filtraría el nombre del paciente.

### 7.3 `app/evidence/support.py` ← `soporte_cita.numeros` / `cotejar` (mixto)

- Ya del original: `clean_source`, `entities`, `_plain`, `_canonical`.
- **Polaris:** descarta el número pegado a una barra (para que "CDK4/6" no cuente) y con eso pierde
  las fracciones y rangos de un resumen: dice que "728" no está en el de Kerstman 2012, que sí lo
  dice ("382/728").
- **EMMA:** en un resumen en inglés, una fracción y un rango aportan sus dos cifras.
- **Lo demuestra:** `test_a_fraction_in_the_abstract_backs_both_figures`,
  `test_a_range_in_the_abstract_backs_both_ends` y dos mutantes.
- **En juego:** honestidad de las citas (no dar por no respaldada una cifra que sí está).

### 7.4 `app/evidence/citations.py` ← `verifica_citas.clasifica` (mixto)

- Ya del original: `clean_doi`.
- **Polaris:** recorta paréntesis de los extremos antes de buscar el DOI, y
  `doi:10.1234/abcd(12)` sale como `10.1234/abcd(12`.
- **EMMA:** busca el DOI sin recortar.
- **Lo demuestra:** `test_classify_as_polaris_does[doi:10.1234/abcd(12)-…]`.
- **Además, no es divergencia sino pegamento:** el original consulta los registros con `curl`;
  EMMA usa un cliente httpx inyectable para que las pruebas no toquen la red (invariante 3).

### 7.5 `app/volumes/geometry.py` ← `visor3d` (mixto)

- **`spacing`.** Polaris toma el espaciado de `abs(diag(afín))`, que da un espaciado falso con un
  afín oblicuo; EMMA usa la norma de cada columna. Mutante "espaciado desde la diagonal del afín"
  en `tests/test_volumes.py`. En juego: medidas de lesión correctas.
- **`lesions`.** El `lesiones(raices, serie)` de Polaris no se puede llamar: segmenta con
  TotalSegmentator, lee DICOM y escribe en disco él mismo. EMMA recibe máscaras ya cargadas y llama
  `region` a lo que Polaris llama `segmento`.
- **`with_density` (2026-10-07, decisión del usuario; §17).** Densidad en HU dentro de la máscara
  de cada lesión candidata y del parénquima de referencia. Código de EMMA entero: `visor3d` no la
  mide por lesión (su `fase()` da medianas de aorta, porta e hígado y no se puede llamar: segmenta
  y lee por sí misma). Descriptiva: no clasifica ni entra en el análisis. Vigilan
  `tests/mutants/volumes_density.json` y `volumes_density_serving.json`.
- **La fase de contraste la declara una persona (2026-10-13, decisión del usuario).** `fase()`
  sigue sin llamarse y sin reimplementarse: EMMA no propone la fase ni la mira en la imagen. Una
  persona la declara en la consola, de un vocabulario cerrado, y queda en un asiento firmado
  aparte (`app/volumes/contrast_phase.py`, código de EMMA entero;
  `compliance/record-integrity.md` §3.13 bis). Se enseña junto a la densidad y en la comparación
  de dos estudios; no clasifica, no cambia el estado de `evolucion` y no entra en el análisis.
  Vigilan `tests/mutants/contrast_phase*.json`.

### 7.6 `app/volumes/assets.py` ← `visor3d.assets` (mixto)

- El `assets()` de Polaris segmenta, lee DICOM y escribe en el área clínica de su autora: no se
  puede llamar. Lo de EMMA: presets dirigidos por datos (`ojos`, para SANS, no existe en Polaris),
  vesícula con etiqueta 5, vóxel por preset medido del volumen real, y nivel de ventana del
  órgano sin lesiones (40 HU por defecto; Polaris 60).
- En juego: invariante 4 (los ficheros vuelven en memoria y van al ledger).
- **Desde el 2026-10-07** `build` firma la densidad en el resumen de la segmentación, y para lo ya
  guardado se calcula al servir desde su zip firmado, sin reescribir el ledger (como la cadena
  vertebral, §16).

### 7.7 `app/volumes/segment.py` ← `visor3d.segmenta` y `exige_telemetria_apagada`

- **Telemetría.** El original solo mira `~/.totalsegmentator` e ignora `TOTALSEG_HOME_DIR`, que
  TotalSegmentator sí respeta: con la telemetría encendida en esa carpeta, Polaris diría "apagada"
  y segmentaría con ella encendida. Lo demuestra
  `test_segmentation_refuses_to_run_with_telemetry_on`. En juego: ningún dato de salud sale fuera.
- **Ejecución.** Polaris usa la API de Python de TotalSegmentator (torch, `mps`, salida
  multietiqueta); EMMA llama a su línea de órdenes en otro proceso (una máscara por clase,
  `cuda`/`cpu`), porque el instalador no lleva torch. Desde el 2026-11-11 una tarea que falla en
  GPU se repite en CPU (`test_a_task_that_fails_on_the_gpu_is_repeated_on_the_cpu`): en el portátil
  de desarrollo la GPU fallaba por un overclock de MSI Center; de serie va bien con cuDNN.


### 7.8 `app/evidence/tier.py` ← `tier_evidencia.senales_desde_texto` (2026-10-07)

- **Polaris:** su `--texto` hace `teje(senales_desde_texto(texto))`. El léxico solo emite banco,
  personas y caso, nunca «rct» ni «guía», y da por bueno «caso clínico» sacado de una frase.
- **EMMA:** una fuente sin PMID pasa su cita y su título por esas dos funciones, tal cual. El
  resultado lleva `basis: "text"` y la etiqueta «… · desde el texto de la cita, no del registro».
  Alrededor, sin tocar el original: el texto nunca se mezcla con un registro; no se lee la
  relevancia ni el alcance, que son palabras de EMMA y suelen ser negaciones; y del texto solo se
  acepta la marca de preclínico.
- **Diferencia declarada:** «caso clínico» desde el texto no se acepta. Partiendo de
  «desconocido» sería subir, y una negación lo dispara.
- **Lo demuestra:** `tests/test_evidence_tier.py`, `tests/mutants/evidence_tier_text.json` y la
  tercera mutación de `polaris_tier_evidencia.json`.
- **Efecto:** OSD-288 pasa de «desconocido» a preclínico. Ninguna otra fuente cambia.
- **Pendiente de decidir:** admitir «caso clínico» desde el texto; leer también el alcance.
  (Sigue abierto tras la séptima ronda: lista vigente al final del §17.)


## 8. Enchufar en EMMA las herramientas nuevas (F3): qué necesita decisión

**Estado a 2026-10-01:** decididas y en uso `decision_alto_riesgo` (fuente y comprobador en la
segunda firma), `identidad_paciente`, `biomarcadores` (F4), `codigo_rojo` (su regla, F2), `_net` y
`borde` (F1), `salud` (F5), el dosier (F6), el preset `esqueleto` (§14), `md_to_pdf_pro`, `kb`,
`estado_rutina` y `transcribe_audios` (§14). Siguen sin uso `fuente_clinica`, `replay_guard`,
`evals`, `score_local` y `guarda_memoria`. La tabla de abajo es la de partida.

**Estado a 2026-10-07:** `fuente_clinica`, `score_local` y `guarda_memoria` están en uso desde la
quinta ronda (§15), y `replay_guard` y `evals` quedaron fuera (§15). Qué herramientas pide EMMA
por su nombre ya no se copia aquí: lo da `GET /api/polaris/estado` (la lista `EMMA_USES` de
`backend/app/api/polaris.py`, atada por prueba a las llamadas reales) y se ve en la consola de
Tierra (§17).

Copiadas y cargando (`polaris/ESTADO.md`), pero **todavía sin uso en EMMA**. Al revisar su
entrada, casi todas están construidas sobre el caso de su autora; usarlas obliga a decidir qué
significan aquí:

| Herramienta | Qué espera Polaris | Qué hay en EMMA | Decisión |
|---|---|---|---|
| `decision_alto_riesgo.evaluar` | Un panel de "lentes", cada una con postura, **fuente citada** y la comprobación de un **tercero** | Dos firmas humanas sobre un borrador, sin fuente ni tercero | Con lo que hay hoy, toda acta saldría "no entregable". ¿Se añade fuente y comprobador a la segunda firma? |
| `fuente_clinica` | Punteros a ficheros de una "bóveda" (`_PRIVADO_CLINICO/…`) | Informes guardados en el ledger | ¿La bóveda son los informes del ledger? |
| `identidad_paciente` | Nombre y fecha de nacimiento de la titular | El perfil de tripulante no guarda datos personales | ¿Se guardan nombre y fecha de nacimiento del tripulante? |
| `biomarcadores` | Analíticas en `.md` y un diccionario de analitos propio, **sin LOINC** | Catálogo con LOINC verificado (invariantes 1 y 2) | ¿Mapa de sus analitos a LOINC, o solo los que ya están en el catálogo? |
| `codigo_rojo` | Parar todo si algo pone en riesgo "el objetivo NED/vacuna"; ficheros `.HALT` en casa | — | ¿Qué es "modo seguro" en EMMA y qué congela? |
| `_net`, `canarios`, `borde`, `salida` | Su puerta de salida (curl, llavero de macOS, reglas del muro) | Llamadas con httpx y modo offline | ¿Se sustituye la salida de EMMA por la de Polaris? |
| `salud` | Acuse de las alertas de sus demonios | Alertas clínicas del tripulante | ¿Acuse de alertas de EMMA con este formato? |
| `dosier_invariantes`, `guardian_evals`, `frescura_dosier` | Un dosier JSONL con su esquema cerrado | `countermeasures.json`, `evidence_tiers.json` | ¿Se convierten esos JSON a su esquema o se escribe el esquema de EMMA? |
| `visor3d` (DICOM, `esqueleto`) | Lee DICOM y escribe en su área clínica, segmenta con la API de Python | Ruta de volúmenes por ledger, CLI de TotalSegmentator | Llevar el preset `esqueleto` a la ruta de EMMA |
| `replay_guard`, `evals`, `score_local` | Transcripciones de Claude Code y su centralita | — | ¿Uso en EMMA? |
| `guarda_memoria` | Grupos de procesos de Unix | Windows | Probar en Windows antes de usarlo |
| `transcribe_audios` | Whisper instalado | No instalado | ¿Se instala? |

**Sin decisión pendiente** (solo pegamento): `md_to_pdf_pro` (exportar a PDF lo que EMMA ya
muestra), `kb` (buscador local sobre documentos de EMMA) y `estado_rutina` (frescura de
medidas programadas).

## 9. Seis herramientas más, copiadas sin uso

`cronica`, `cascada_clinica`, `cascada_mapa`, `anticipa`, `paso_consolidacion` y `caja` (y lo que
arrastran: `capacidades`, `lentes`, `enruta_comite`, `decide_peticion`, `audit_constelacion`).
Encajan con la especificación (trazabilidad §64, línea temporal §54, comité de voces), pero leen
el caso de su autora (`00_FUENTE-DE-VERDAD`, `_PRIVADO_CLINICO`) y su catálogo de agentes
(`.claude/agents`). **Pendiente:** qué alimentarles en EMMA (ledger, eventos de misión,
contramedidas) antes de usarlas.

Después se añadieron `esquema_estado` (valida el estado de `seguimiento.json`) y
`prueba_entregable` (comprueba en disco que un trabajo dejó lo que prometió), compañeras de
`seguimiento` y `cola`; también sin uso en EMMA todavía.

**Al 2026-10-07:** `cronica`, `cascada_mapa`, `anticipa` (§13, F7) y `paso_consolidacion` (§15)
están en uso. Siguen copiadas sin uso `cascada_clinica`, `capacidades`, `lentes`, `enruta_comite`,
`decide_peticion` y `audit_constelacion`; `caja`, `esquema_estado` y `prueba_entregable` quedaron
fuera (§15). El pendiente de arriba sigue en pie para las seis primeras.

## 10. Lo que dicen las pruebas del propio Polaris aquí

**Al día (2026-10-07, séptima ronda; §17).** El recuento y la causa de cada prueba roja ya no se
copian aquí: los lleva `polaris/PRUEBAS.md`, generado por `backend/scripts/polaris_tests.py` con
una columna «Causa» por prueba y el recuento por clase (la tabla `CAUSES` del guion; una roja sin
causa sale como «sin explicar» y una causa cuya prueba ya no está roja, como «caducada»). A esa
fecha: ninguna roja es un fallo del pegamento de EMMA y ninguna queda sin clasificar; la mayoría
caen por ficheros del entorno de su autora que no se copian (`.claude/hooks`, `.claude/agents`,
`tools/config/`, sus guiones de shell, la marca `.espejo-publico`), el resto por Windows, una por
registrar solo Ollama (`test_avisos_origen`) y una por correr fuera del lazo de Polaris
(`test_casa_estilo`). Leídas las aserciones una a una, cambian cuatro cosas de la lista de abajo,
que es la de entonces:

- `test_llavero_mudo` no cae por el llavero de macOS sino porque falta `tools/hoy_compose.sh`.
- `test_deid_eval`, `test_identidad_paciente`, `test_visor3d` y `test_visor3d_cateter` caen por
  `.claude/hooks/zonas_clinicas.py`; `test_healthcheck_syspath`, por `correo_smtp.py` y
  `postdicom.py`.
- `test_decision_alto_riesgo` no es solo de «Windows». Sus cinco fallos, separados uno a uno
  (corriéndola en copias temporales con y sin cada causa): tres salen de que el catálogo de
  agentes de su autora (`.claude/agents/`) no se copia, y sin él `evaluar` da «panel
  INCOMPLETO»; uno, de los permisos `0600` del acta; y uno, de que la propia prueba escribe su
  informe en modo texto y en Windows su huella no es la del texto. EMMA usa `disparar`,
  `_canon_txt`, `_ACCION`, `_DELIBERA_FUERTE` y `_existencia_citas`; lo que esa prueba dice de
  ellas pasa, y EMMA no llama a `evaluar` ni a `render` ni escribe esa acta.
- Las tres «sin clasificar del todo» tienen causa: `test_casa_estilo` (fuera de launchd, `salida`
  antepone su sello de origen), `test_healthcheck_halt_inactividad` (`launchctl`) y
  `test_replay_gate` (`.claude/hooks/gate_salida.py`).

Las pruebas corren ahora sobre una copia temporal de `polaris/` (nada puede escribir en la
versionada: `biomarcadores` creó dos veces `00_FUENTE-DE-VERDAD/` dentro) y con `python`/`python3`
apuntando al intérprete de EMMA (antes `python3` era un Python 3.14 del sistema). De las cinco
campañas de mutantes de Polaris, tres cazan todo; `lector_clinico.json` y `caso_publico.json` no
corren porque su prueba ya está roja sin mutar (enlaces simbólicos; la marca `.espejo-publico`).

**No adoptar un escritor de `seguimiento` ni `_lock.lock` sin pegamento.** En Windows el candado
entre procesos de `_lock.py` no aguanta: sondea al dueño con `os.kill(pid, 0)`, que aquí no es una
sonda inocua ni distingue un proceso muerto; quien espera agota el plazo, `seguimiento` escribe
sin candado y los escritores se pisan hasta corromper el JSON (`test_seguimiento_carrera`). EMMA
solo lee por ahí, y `tests/test_polaris_windows_reds.py` falla si empieza a tomar ese candado.
**Desde el 2026-10-08 (§18)** el candado aguanta con `compat/winlock.py` y esas dos pruebas pasan;
el veto sigue por otra causa: `os.replace` falla en Windows si un lector tiene abierto el fichero.

`polaris/PRUEBAS.md` (`backend/scripts/polaris_tests.py`): de las pruebas suyas sobre lo copiado,
**82 verdes, 36 rojas y 14 saltadas** de 132 (se saltan solas cuando falta su entorno). Corren sin red,
con `HOME` y el estado en un directorio temporal, y fuera de la suite de EMMA. Ninguna escribió en
la carpeta personal: comprobado tras la primera pasada, en la que `test_muro_fase0` intentó usar
`~/claudecode` (sin dejar nada) y por eso `HOME` también se aísla.

Por qué salen en rojo, con la prueba que lo muestra:

- **Windows.** Enlaces simbólicos sin privilegio (`test_fuente_clinica`,
  `test_lector_clinico_binario`, `test_muro_fase0`, `test_cerebro_enlace`), `os.getuid`
  (`test_kickstart_bootstrap`), el módulo `resource` (`test_visor3d_malla_recorte`), una ruta de
  Windows con `\U` en una cadena (`test_visor3d_colab`), permisos `0600`
  (parte de `test_decision_alto_riesgo`: 83 de 88 bien), guiones de shell
  (`test_bucles_colgados`) y el llavero de macOS (`test_llavero_mudo`).
- **Ficheros del entorno de su autora que no se copian.** Sus ganchos y agentes de Claude Code
  (`.claude/hooks`, `.claude/agents`): `test_clinico_guard`, `test_regla_en_accion`,
  `test_f1_opus_supervision`, `test_muro_secreto_stdout`, `test_presencia_cc`,
  `test_dominios_con_dueno`, `test_seguimiento_objetivo_ned`, `test_visor3d`,
  `test_visor3d_cateter`, `test_lentes`, `test_capacidades`, `test_identidad_paciente` (21 de 22
  bien); sus guiones y ganchos de git (`test_git_mutex_*`, `test_rc_turnos_agotados`,
  `test_cola_turnos`, `test_deuda_*`, `test_autopoda_residuo`, `test_prueba_entregable`) y
  herramientas no copiadas (`correo_smtp` en
  `test_tools_no_sombrea_stdlib` y `test_healthcheck_syspath`).
- **La decisión de EMMA de registrar solo Ollama.** `test_avisos_origen` (7 de 13) espera el
  registro completo de cerebros de Polaris; con el de EMMA cambia qué se clasifica como fallo
  "ambiental". Es consecuencia del punto 1, no un error.
- **Sin clasificar del todo:** `test_casa_estilo` (79 de 80), `test_healthcheck_halt_inactividad`
  (9 de 12, depende de sus demonios) y `test_replay_gate`.

Campañas de mutantes de Polaris: 3 de 4 cazan todo; `lector_clinico.json` no corre porque su
prueba ya está en rojo sin mutar (enlaces simbólicos en Windows).

**Pendiente:** nada de esto se arregla tocando la copia. Si alguna herramienta se va a usar en
EMMA, sus rojos de Windows se resuelven con pegamento (como `fcntl`) o se deciden aquí.

## 12. Copia al día con Polaris `e3b588d` (2026-10-01)

Polaris se republicó sin historia común con `7bf4725`. Entre los dos árboles: 906 → 1329 ficheros,
424 añadidos, 152 cambiados. De lo que EMMA ya había copiado cambiaron 48: entre otros `deid.py`
(+316 líneas: campos de filiación etiquetados, capa NER opcional, diccionario de la titular),
`visor3d.py` (+804: lesiones con máscara, comparación entre series, cruces de malla),
`cost_guard.py`, `guarda_memoria.py`, `biomarcadores.py`, `salida.py`, `identidad_paciente.py` y
19 de sus pruebas. `visor3d_web/` no cambió: el cambio de colores y textos sigue aplicando.

**Resultado en EMMA:** nada se rompió (1184 pruebas y las 43 campañas de mutantes en verde, antes
de cambiar `deid`). Cargaban 90 de 91 herramientas (recuento de entonces). Las pruebas de Polaris aquí: 84 verdes, 47 rojas
y 14 saltadas de 145 (`polaris/PRUEBAS.md`), por las mismas causas del §10.

**`deid` pasa al original** (decisión del usuario). `app/reports/deid.py` es ahora un adaptador
sobre `de_identificar_verificado()` de la copia, más una regla de EMMA encima: un nombre con
tratamiento en mitad de una frase ("revisado por la Dra. Ana López"), que el original deja a la
vista y da por verificado. Cambia lo visible, como lo hace Polaris: el texto sale sin tildes, la
fecha de la analítica se enmascara y dos líneas enmascaradas seguidas se funden. Las pruebas de
seguridad se mantienen (ningún identificador a la vista, lo clínico se queda, falla cerrado); las
de forma se actualizaron. Mutantes: `tests/mutants/deid.json` (regla de EMMA, falla cerrado) y
`tests/mutants/polaris_deid.json` (revalidación del original).

**Decidido sobre `deid` (2026-10-01): las dos cosas.**
- **Reglas de EMMA antes del original:** IBAN con dígito de control (mod-97), tarjeta con Luhn,
  pasaporte con etiqueta y fecha ISO con hora. Una cifra larga que no pasa su dígito de control no
  se tapa. Pruebas en `tests/test_reports.py`; mutantes en `tests/mutants/deid.json` (10 de 10).
- **Capa NER:**
  - Instalador: `backend/scripts/install_deid_ner.py`. Crea `backend/.venv-deid` con
    `torch==2.14.1+cpu` y `transformers==5.18.0` (instalado), baja el modelo en la revisión de
    Polaris y comprueba el SHA-256 de los pesos, que Polaris declara pero no comprueba.
  - Cambio decidido a la copia (`polaris/CAMBIOS.json`): `deid._python_ner()` busca también
    `Scripts/python.exe` (Windows).
  - El adaptador pide la capa solo con la marca de pesos comprobados. Sin ella, cada informe se
    retendría entero.
  - **Bloqueado:** el modelo `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon` no es público (Hugging
    Face responde 401). Hace falta que el usuario cree una cuenta, acepte sus condiciones y dé
    un token (`HF_TOKEN`). El único modelo público del mismo grupo es
    `bsc-bio-ehr-es-carmen-anon`, otro corpus: usarlo cambiaría lo que fija Polaris, y eso es
    decisión aparte.
- **Medida** con `deid_eval` sobre un corpus propio inventado (`backend/tests/data/deid_corpus/`,
  10 informes, 39 identificadores):
  - patrones de Polaris solos: 26 de 39;
  - EMMA: 35 de 39;
  - NER: sin medir.
  - Escapan aún "Titular: <nombre>", "Tarjeta sanitaria: <código>", un familiar nombrado sin
    etiqueta y restos de un correo.
  - Detalle en `compliance/risk-management-file.md` (H17).
  - **Corrección del 2026-10-07:** el corpus tiene 34 identificadores anotados, no 39, y «26 de
    39» y «35 de 39» no se pueden reproducir. La medida vigente es por tipo de entidad y la
    escribe `backend/scripts/deid_report.py` en ese mismo apartado (§16).
- **Decidido (2026-10-01): etiquetas de EMMA y sin NER.** Regla de EMMA antes del original:
  "Titular", "Tarjeta sanitaria (individual)", "TSI" y "CIP" con dos puntos; se tapa el valor y
  la etiqueta se queda. La capa NER no se usa: ni cuenta en Hugging Face ni el modelo público de
  otro corpus. Con la regla solo se escapa entero el familiar nombrado sin etiqueta (1 de 23 fugas
  medidas con `deid_eval.fugas`, fijado en `tests/test_deid_corpus.py`; mutante en
  `tests/mutants/deid.json`).
- **Familiar nombrado (2026-10-07, séptima ronda; §17).** Otra regla de EMMA encima del original
  (`reports/deid.py::_mask_relatives`): parentesco + nombre propio; se tapa el nombre y se queda
  el parentesco, que es dato clínico. Con determinante («su hermana Lucía») basta un nombre de
  pila; sin él («Hermano: …»), nombre y apellido, porque así se escriben los antecedentes
  («Madre: Asma»). Una lista de enfermedades, epónimos y fármacos corta el nombre; estados y
  sufijos médicos no cuentan como nombre de pila; un parentesco en el nombre de un centro o una
  calle no cuenta; «mujer», «mamá» y «papá», solo con posesivo. Falla cerrado. Medido con
  `deid_eval`: sobre los 10 informes de antes, familiares tapados enteros de 0 de 2 a 2 de 2 y
  fugas de 1 a 0 de 23; con `informe11` (antecedentes familiares inventados; 11 informes, 39
  identificadores), 38 de 39 tapados enteros y 1 fuga de 28 (sin la regla: 32 de 39 y 6 de 28).
  Se escapan ~~el nombre **delante** del parentesco («con Rosa Beltrán, su cuñada»)~~ (cerrado el
  2026-10-20, abajo), un nombre de pila suelto sin determinante y los nombres en mayúsculas
  sostenidas. El corpus no es una muestra independiente: `informe11` lo escribió quien escribió la
  regla. `masked_spans` tiene una cuarta capa, `emma:parentesco`. Mutantes en
  `tests/mutants/deid.json`. No es un cambio a la copia.
- **Nombre delante del parentesco (2026-10-20, decimotercera ronda).** Segunda pasada de la misma
  regla (`_NAME_KIN`, `_name_before_kin`): «con Rosa Beltrán, su cuñada» → «con [REDACTADO], su
  cuñada»; también «Rosa Beltrán (su madre)», «Pedro, mi hermano» y «Rosa Beltrán, cuñada del
  paciente». El parentesco tiene que estar anclado a la persona (posesivo, o «del paciente»
  detrás); ninguna palabra del nombre en la lista clínica y la primera, ni estado, ni sufijo
  médico, ni un centro o una vía; lo que abre la frase («Hoy», «Además») se quita por la
  izquierda. Nombre y apellido bastan; un nombre de pila suelto, solo tras «con», «a», «por», «y
  (de)» o «acompañado de». De paso, el guion une la marca de Polaris con el resto de un apellido
  compuesto («[REDACTADO]-Gomez» salía a medias también detrás del parentesco). Medido: sobre los
  11 informes, familiares de 6 de 7 a 7 de 7, fugas de 1 a 0 de 28 y precisión por carácter de
  0,916 a 0,918; con `informe12` (cuatro familiares delante de su parentesco y, en esa misma
  posición, lo clínico y un centro), 44 de 45 tapados enteros y 1 fuga de 34 (sin la pasada: 40
  de 45 y 5 de 34). Límites declarados, con prueba: un nombre de pila suelto al principio de la
  frase («Marta, su sobrina, llamó»: la fuga que queda), la aposición sin posesivo ni «del
  paciente», las mayúsculas sostenidas, una profesión sin tratamiento («Ana López, su médica») y
  un nombre junto a una palabra de la lista clínica («Ana Graves, su madre»). Lo que decide son
  listas finitas. `informe12` también lo escribió quien escribió la regla. Doce mutantes nuevos en
  `tests/mutants/deid.json`. No es un cambio a la copia; la capa NER sigue sin usarse.

**Herramientas nuevas copiadas, sin uso todavía:**
- `deid_ner`: capa NER con el modelo del BSC entrenado con historias clínicas reales, sin red y con
  pesos comprobados por SHA-256. Para usarla hay que instalar `transformers` y el modelo
  (`BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`) aparte, como TotalSegmentator.
- `deid_eval`: banco de medida (recall por entidad). Para medir la de-identificación de EMMA
  hace falta un corpus de prueba propio.
- `esqueleto_referencia`: esqueleto de la cabeza a los pies desde BodyParts3D (CC BY 4.0, DBCLS).
  **En uso desde el 2026-10-01** (F8): licencia verificada en la fuente
  (https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html: "The license for this database is
  specified in the Creative Commons Attribution 4.0 International"); el aviso de
  `frontend/src/pain/bodyModel.ts` que lo daba por CC BY-SA se corrigió el mismo día. Zip
  de 65 MB en `data/bodyparts3d/` (fuera del instalador); la herramienta original genera la vista
  anterior y 60 centroides (217 piezas), que viajan en `backend/app/data/anatomy/` con su
  atribución y se ven en la región "Huesos" del modo anatómico. En Windows escribe
  `esqueleto.json` en cp1252 (abre el fichero sin `encoding=`): la copia de la app se pasó a
  UTF-8 sin cambiar datos; la copia de Polaris no se tocó.
- `fichas.py` y la ficha de cada herramienta copiada (87): para qué sirve y cuál es su prueba.

## 13. El resto del plan de decisiones (2026-10-01)

- **F1, una sola salida a internet** (`backend/app/core/egress.py`): se usan tal cual
  `borde.egress_check` (con `escalar=False` y `consulta=True`) y `_net.with_retries`; el
  adaptador traduce los errores de httpx a los de urllib que espera Polaris y de vuelta. La traza
  es de EMMA, con la forma de `salida._audit` (solo metadatos).
- **F2, modo seguro:** corta la red, no la IA, que es local (decisión del usuario). De
  `codigo_rojo.py` se toma la regla y no el mecanismo: escribe en la carpeta personal de su autora,
  avisa por Telegram y apaga demonios de macOS. Tipo de asiento `safe-mode`.
- **F5, estados de alerta:** los de `salud.py` (detectado → en arreglo → resuelto). No se usa su
  `acuses.json`, que es de sus demonios. Tipo de asiento `alert-resolution`.
- **F6, dosier** (`backend/app/evidence/dossier.py`, `GET /api/dossier`): se usan
  `dosier_invariantes._schema_pieza` e `_invariantes`, `frescura_dosier.evaluar_frescura` y el
  canario de `guardian_evals`. **No** se usa `dosier_invariantes.evaluar()` entero: arrastra el
  cotejo y la elegibilidad de ensayos del caso oncológico de su autora. Vigencia de una revisión:
  365 días (parámetro de diseño).
- **F7, crónica, «esta semana» y «qué depende»** (`backend/app/timeline.py`,
  `/api/timeline/*`):
  - `cronica._linea_bitacora` sobre eventos sacados del ledger. Sus cosechadores leen el git y
    las carpetas de su autora, así que no se usan.
  - `anticipa.esta_semana()` con `seguimiento.recopilar` sustituido por lo datado de EMMA y
    `cumbre.foco` por nada (la cadena "hacia NED" es de su caso).
  - `cascada_mapa.afectados()` y `validar_mapa()` con `MAPA`/`DEPENDIENTES` sustituidos por el
    mapa de EMMA (indicador → dominio, línea base, proyección, región, contramedidas).
  - Las sustituciones son temporales y bajo cerrojo: la copia no se toca, y una prueba comprueba
    que vuelve a su estado (mutantes `timeline.json`).
  - **Desde el 2026-10-07 (unidad 14 de la sexta ronda):** los eventos de la crónica salen del
    ledger y, además, del estado ya calculado, de las fases y de la cabina (desde cuándo está
    cada alerta, cambios de nivel y de fase, excursiones). A `anticipa.esta_semana` se le
    sustituye también su `date` por el día de los datos, bajo cerrojo y restaurado, y
    `estado_rutina` (§14) recibe el ahora de `/api/status` y declara de dónde sale
    (`now_source`). Una ubicación declarada se cuenta como hecho firmado, no como evento del
    plan.

## 14. Cuarta ronda (2026-10-01): exportar, buscar, rutinas, esqueleto, focos y voz

- **`md_to_pdf_pro`** (`backend/app/export.py`, `GET /api/export/{estado|dosier|cronica}.pdf`): su
  `main()` lee `sys.argv` y pone a todo PDF el título de su caso; los dos se sustituyen durante la
  llamada, bajo cerrojo. Su salida a consola se captura (emojis que cp1252 no codifica).
  Desde el 2026-10-07 hay un cuarto tipo, `dolor` (`GET /api/export/dolor.pdf`; §17), con el mismo
  cerrojo y la misma sustitución. Límite: `md_to_pdf_pro` quita emojis y algunos símbolos (su
  `clean`) e interpreta `**`, `*` y las comillas invertidas, así que una nota dictada sale con
  sus palabras pero no carácter a carácter.
- **`kb`** (`backend/app/kb.py`, `GET /api/kb`): indexa `BTP_REPO/00_FUENTE-DE-VERDAD`; el adaptador
  copia ahí `compliance/`, `docs/` y el README, que ahora viajan en el instalador
  (`packaging/freeze.py`). Sin capa vectorial (no hay modelo): BM25 puro, sin red.
- **`estado_rutina`** (`backend/app/routines.py`, `GET /api/timeline/routines`): `clasificar()`
  con fechas del ledger y periodos de diseño (`app/data/routines.json`).
- **`visor3d.PRESETS["esqueleto"]`** (`backend/app/volumes/assets.py`): los 60 huesos del esqueleto
  de referencia, tarea `total` limitada a ellos y sin margen. Su segmentación se cortaba por memoria
  en la máquina de su autora (20 GB en 16, cuerpo entero). En EMMA la memoria se estima por el tamaño
  de cada TAC: 6,0 GB fijos más 0,16 GB por millón de vóxeles a 1,5 mm, +25 %. Picos de la tarea
  entera, con GPU (2026-10-06): muestras de la app, 6,3 a 7,4 GB; s0013 (45 cm, reparto `test`),
  7,3 GB; s1152 (politrauma de 82 cm, reparto `test`), 15,5 GB con los 60 huesos en 469 s
  (estimado: 19,7). **Desde el 2026-10-06 la tarea corre entera, como en Polaris**, y ya no
  limitada a los 60 huesos con `--roi_subset`: con él TotalSegmentator recorta con su modelo de
  6 mm y en el ejemplo `esqueleto-4` perdía 20 de 60 huesos (Dice medio contra la segmentación
  del TAC original: 0,50 con subconjunto, 0,74 con `--roi_subset_robust`, 0,85 con la tarea
  entera). No ahorraba memoria, solo tiempo (60 s frente a 250 s). Sin esa memoria libre no se lanza, y es el techo de la
  guarda. **Corregido el 2026-10-04:** el primer modelo (0,6 GB por millón, solo con s0013) era
  proporcional, daba 1,3 GB de techo a un TAC pequeño y la guarda mataba la segmentación a los
  2,3 GB. Pruebas: `test_the_memory_estimate_covers_every_measured_peak` y, `external`,
  `test_the_skeleton_segments_within_the_memory_it_announces`.
- **`visor3d_superpone_focos.alinea`** (`backend/app/pain_on_skeleton.py`): con 11 zonas del mapa
  de dolor ancladas a su hueso, error medio 62,9 px sobre 2212 (umbral, de la geometría: 89,5;
  102,3 desde el cuerpo del mapa de dolor de 2026-11-09, cuya zona anclada más baja es el cuello,
  de 0,16 m, y no ya pelvis y cadera, de 0,14).
  `FOCOS`, `ANCLAS` y `VB` se sustituyen bajo cerrojo; su `fn` lee `VB` al llamarla, así que se
  coloca antes de devolvérselo. No se usa su `main()` (pinta en ámbar en su carpeta de marca).
  Desde el 2026-10-07 `alinea` se llama también sobre el esqueleto del propio TAC del tripulante
  (§17), con reglas de EMMA: solo anclan huesos que el estudio trae enteros; sin tres posiciones
  distintas de las anclas por eje no se alinea; un ajuste con escala negativa no coloca nada; la
  zona sin hueso o fuera de la imagen se declara «fuera del estudio»; el umbral se mide en
  milímetros físicos. Su `SystemExit` se captura y se dice. Desde el 2026-10-20 la zona anclada a
  un hueso entero va al centroide de ese hueso, como en el modo `DIRECTO` de su `main()` (§18,
  «Pendiente de decidir»).
- **`transcribe_audios`** (`backend/app/voice.py`): **cambio decidido a la copia**: `SRC` y `OUT`
  por variable de entorno (`polaris/CAMBIOS.json`), porque escribía dentro de `polaris/`. En Windows
  su `chatdir.rstrip("/")` deja la barra invertida y el fichero de salida se llama `.md`: EMMA lo
  busca por extensión, sin tocar la copia. Entorno `backend/.venv-voice` (`scripts/install_voice.py`,
  1 GB, fuera del instalador).

## 15. Copia al día con Polaris `0e629e4` y quinta ronda (2026-10-04)

**Copia.** 28 commits nuevos (1-3 oct).
- Cambian `borde.py` (+402 líneas), `codigo_rojo`, `salida` y `visor3d`.
- Se añaden `incongruencias_caso` y `atascos`, y lo que arrastran por imports (entre ellos
  `aprobaciones`, `promesas_caso`, `historial` y tres `laminillas_*`), dormido.
- `CAMBIOS.json` se reaplicó sin conflictos.
- 103 módulos, 155 pruebas suyas: 53 en rojo, 6 nuevas, todas explicadas:
  - `tools/config/` no se copia (`test_aprobaciones_atascos`, `test_codigo_rojo_excepciones`);
  - `pwd` de Unix (`laminillas_*`);
  - la "ventanilla clínica" de `deid_eval` depende de sus ganchos `.claude/`.
  - Lo que EMMA usa de `deid_eval` (`cargar_brat`, `fugas`, detección) pasa.

**Lo que se usa ahora y cómo:**
- **`canarios.sembrar_estado`:** el señuelo, sembrado donde lo lee el `borde` cargado. Es una
  vez, no se rota.
- **`fuente_clinica.cotejar`:**
  - sus ganchos `_IDENTIDAD` (el veredicto firmado en el informe) y `_LOG` (`vault/accesos.jsonl`);
  - `bovedas()` sustituida bajo cerrojo por la bóveda de EMMA (texto des-identificado de cada
    informe vigente). No se usa su variable `BTP_BOVEDA_CLINICA`, que reserva a pruebas.
- **`incongruencias_caso.analizar`:**
  - con `muestra_de` = la sangre de un día;
  - `extraer` = las lecturas ya estructuradas;
  - `_distintos` = 5 % relativo. La suya compara como texto todo lo que no es porcentaje, y un
    redondeo entre laboratorios saldría como incongruencia.
- **`guarda_memoria.corre`:** su lógica tal cual. Sus lecturas de macOS (`ps`,
  `proc_pid_rusage`, `vmmap`, `sysctl`, `killpg`, `sample`) se sustituyen por las de Windows en
  `compat/memguard.py`.
  - La primera versión medía memoria comprometida y la guarda mató una segmentación sana: ahora
    es memoria física y paginación real.
- **`score_local`:** `puntuar`, `_ece` y `comprobar_memoria`, con su URL y su lectura de memoria
  sustituidas bajo cerrojo. Su arnés `evals` no se usa: sus categorías son las de su motor.
- **`paso_consolidacion.consolidar`:** sí. Su `render` no: escribe en la voz de su autora
  ("acciones para ti").
- **`atascos.esperan_por_titular`:** sí (y su `ESPERA_DIAS`). Sus `propuestas_de_proceso` y
  `bloque` no: proponen pasar trabajo a su asistente.
- **`kb_embed`:** el plan preveía un cambio a la copia (`MODEL_DIR` por variable de entorno). No
  hizo falta: lee `MODEL_FILE` y `TOKENIZER_FILE` al cargar, y se le apuntan desde `app/kb.py`.
  La copia no se toca. Modelo `intfloat/multilingual-e5-small` (MIT), fijado por commit y
  SHA-256, en el instalador.

**Fuera, y por qué:**
- `vega_*`, `perfil_vega`, `acciones_datadas`, `promesas_caso` y `aprobaciones`: su asistente, sus
  reservas, su WhatsApp, su política.
- `laminillas_*`, `vision_n1`, `nube_n1`, `exporta_n1` y `puerta_n1`: sus láminas de patología y
  la subida a la nube.
- `panel_vision/medgemma_local`: el modelo exige cuenta en Hugging Face.
- `replay_guard`, `replay_gate`, `esquema_estado`, `prueba_entregable` y `caja`: sus ganchos y su
  cola de Claude Code.

## 16. Sexta ronda (2026-10-07): revisión de la copia y lo que faltaba por aprovechar

Se auditó la copia y el trabajo se repartió en dieciséis unidades en paralelo, cada una en su rama local,
revisadas y fusionadas una a una. La regla es la de siempre: se llama al original; lo propio de
su autora se sustituye desde el adaptador; nada de EMMA se escribe en `polaris/`.

**La copia está íntegra.** Los 397 ficheros coinciden con su huella, no hay ninguno en CRLF y
ningún módulo importa otro que falte. Los fallos estaban alrededor:

- **Documentos de la copia al día.** Tras pasar a `0e629e4`, `polaris/ORIGEN.md` seguía citando
  `e3b588d` y `polaris/ESTADO.md` contaba 91 herramientas donde hay 103. Corregidos: `ESTADO.md`
  se regeneró (100 de 103 cargan en Windows; no cargan `laminillas_jaulas` y
  `laminillas_ventanilla` por `pwd`, y `transcribe_audios` por `soundfile`). Se borró estado
  ajeno a la copia (`tools/state/enruta_salud.json`, `00_FUENTE-DE-VERDAD/00 · Bandeja de
  entrada/`). `test_polaris_copy.py` falla ahora si `ORIGEN.md` no cita el commit de
  `ADOPTADO.txt`, si `ESTADO.md` no cuenta y nombra los módulos de `tools/`, o si aparece un
  fichero o carpeta que Polaris no trae; lo generado se exime por ruta exacta
  (`tools/visor3d_web/node_modules`, `tools/visor3d_web/dist`, `__pycache__`), no por nombre de
  carpeta. (Desde el 2026-10-08 solo se tolera `__pycache__`: el visor web se compila fuera; §18.)
- **Avisos legales en el instalador.** El congelado solo llevaba `polaris/tools/`; ahora lleva
  también `polaris/LICENSE`, `NOTICE`, `CITATION.cff`, `ORIGEN.md` y `CAMBIOS.json`
  (`POLARIS_NOTICES` en `packaging/freeze.py`, y `extraResources` en `desktop/package.json`). Los
  imports de las herramientas copiadas se leen con `ast` en `freeze.py` y `polaris_sync.py`: el
  cierre no cambia (103 módulos) y los imports declarados al congelar ganan `logging` y `sqlite3`.
  **Sin comprobar:** que los ficheros acaben en `resources/polaris/` y en
  `resources/backend/_internal/polaris/` de un instalador construido.
  **Comprobado el 2026-10-07 en un instalador construido (§17).**
- **Cabeceras de licencia, con un solo criterio.** Quien llama a la copia lleva la línea SPDX y
  remite a `polaris/ADOPTADO.txt`, sin fijar un commit que caduque. Quien lleva código adaptado a
  mano fija el commit del que se adaptó (`7bf47257`) y está en `NOTICE`. Lo vigila
  `tests/test_polaris_headers.py`.
- **El freno HALT de Polaris, confinado al estado de EMMA.** `borde.HALT_FILES` apuntaba a
  `~/.btp.HALT` y al `.HALT` de la copia (lo saca de `__file__`, no de `BTP_REPO`): con
  cualquiera de los dos ficheros, `egress_check` negaba toda salida de EMMA sin dejar rastro, y
  `cost_guard._panic` habría escrito uno en la carpeta personal. `app/polaris/__init__.py`
  (`halt_file`, `_confine_halt`) lo deja en `<estado de EMMA>/.HALT` para toda herramienta
  cargada. No es el modo seguro: no se firma ni deja asiento, EMMA no lo crea nunca y se levanta
  borrándolo; por eso `core/egress.py` lo nombra en su error y en su traza, y
  `GET /api/safe-mode` lo enseña. No sirve `BTP_HALT_FILES`: se parte por `:` y una ruta de
  Windows queda en dos trozos. Pruebas en `tests/test_egress.py`; mutantes `polaris_halt.json`.
- **La guarda de memoria, al interrumpirse.** `guarda_memoria.corre` llama a `os.getpgid` y
  `os.killpg`, que no existen en Windows; su `try/except` se tragaba el `AttributeError` y el
  árbol hijo quedaba vivo. `compat/memguard.py` le da un `os` con esos dos nombres (el «grupo»
  es el pid raíz y matarlo es `taskkill /T /F`).
- `evidence/dossier.py` decía usar el canario de `guardian_evals`: no lo carga; lo usa su prueba.
  Corregida la cabecera.

**Funciones de Polaris que ahora se usan**, todas llamadas tal cual:

- **`visor3d.evolucion`** (`app/volumes/geometry.py::evolution`, `GET /api/volumes/compare`): el
  estado de cada lesión entre dos estudios, con sus textos («crece», «se reduce», «estable», «no
  vista en el TC previo») y sus umbrales (+20 % / −30 % del diámetro axial mayor). EMMA añade:
  rechaza comparar dos tripulantes, avisa cuando los dos estudios son pacientes distintos del
  dataset de ejemplo y mantiene el rótulo «segmentación automática sin validar». La interfaz no
  llamaba a `/compare`; ahora ofrece «Comparar con el estudio anterior».
- **`visor3d._revisa_cadena`, `_orden_columna`, `CADENA` y `VERTEBRA_MIN_MM3`**
  (`app/volumes/spine.py`): control de la cadena vertebral del preset esqueleto. Habría avisado
  de los 20 huesos perdidos con `--roi_subset` (§14). `_revisa_cadena` no devuelve nada (escribe
  por consola y aborta con `SystemExit`): el adaptador captura ambas cosas y lee los huecos y el
  orden de su texto; si ese texto cambia en la copia, el control se declara no hecho. Lo que
  pone EMMA: el sacro hace de extremo caudal (Polaris acaba en `vertebrae_S1`, que no está entre
  los 60 huesos); se le pasa el mapa recortado a la caja de la columna (5 s → 0,5 s); se mide si
  el volumen continúa más allá del último nivel presente, porque para Polaris solo es hueco lo
  que falta entre dos niveles y el caso real perdía los dos extremos; una cadena del revés se
  dice; y se listan los huesos sin vóxeles. No se usan `niveles_por_conteo` (a 2 mm cuenta 18
  cuerpos de 24 y no devuelve nada) ni `niveles_por_reparto` (exige `skull`). Es descriptivo: no
  bloquea ni borra. Las segmentaciones nuevas lo llevan firmado en su resumen; para las ya
  guardadas se calcula al servir, desde su mapa de etiquetas firmado, sin reescribir el ledger.
- **`tier_evidencia.senales_desde_texto`**: §7.8.
- **`visor3d.verifica_sin_pii` y `_trozos_pii`** (`app/volumes/privacy.py`, `POST /api/volumes`):
  un NIfTI con texto en la cabecera, extensiones o la identidad declarada del tripulante no se
  guarda (422 con el campo, nunca el dato; 503 si la comprobación no puede ejecutarse). Polaris
  la corre sobre el fichero que ella misma acaba de limpiar; EMMA, sobre lo que sube el operador,
  y ahí el original se queda corto en tres sitios, con tres reglas de EMMA encima: el hueco entre
  la cabecera y los vóxeles (el original solo lee los 352 primeros bytes), las tildes, eñes,
  mayúsculas y Latin-1, y el envoltorio gzip (nombre, comentario o campo extra). Los TAC del
  dataset bajados en local pasan la puerta (`-m external`).
- **`deid_eval.puntuar` y `offsets_cuadran`** (`backend/scripts/deid_report.py`;
  `reports/deid.py::masked_spans`): recall de la des-identificación por tipo de entidad. Los
  tramos tapados se deducen comparando el texto antes y después de cada capa, sin cambiar la
  salida. La tabla la escribe el guion en `compliance/risk-management-file.md` (H17). De paso se
  corrigieron dos cifras del §12 (ver la nota allí).

**Pendiente de decidir** (al cerrar la sexta ronda; el usuario decidió el mismo 2026-10-07 y cada
punto dice en qué quedó; la lista vigente está al final del §17):

- **La puerta del NIfTI es estricta.** Rechaza también texto técnico inocuo (un `descrip` con
  parámetros de adquisición, que es lo que escribe un conversor de DICOM corriente). Alternativa:
  ofrecer la limpieza dentro de EMMA en vez de pedirla fuera.
  → **Decidido: ofrecer la limpieza.** Hecho (§17).
- «Caso clínico» leído del texto, y leer también el alcance (§7.8).
  → Sigue abierto.
- Los avisos legales viajan en dos sitios del instalador; `README.md`, `CHANGELOG.md`,
  `MANIFEST.sha256` y `ADOPTADO.txt` de la copia siguen sin viajar.
  → Hecho: viajan los nueve, y las fichas (§17).
- `compliance/software-safety-classification.md` justifica que Polaris no es SOUP porque «no se
  usa tal cual». Desde que la copia es literal eso ya no describe el código: hay que decidir cómo
  se clasifica.
  → **Decidido: SOUP con ficha.** Hecho (§17).
- Lo que no se hizo porque exige decisión: densidad (HU) por lesión, vista anterior del esqueleto
  del propio TAC y reconstrucción de su silueta, resumen de dolor en PDF y frase literal de la
  fuente en la segunda firma.
  → **Decidido: entran las cuatro.** Hechas (§17); de la silueta se hizo la vista anterior, sin
  reconstruir lo que el modelo no segmentó.

## 17. Séptima ronda (2026-10-07): copia al día con Polaris `849989f`, errores y funciones nuevas

**Copia.** Dos commits nuevos en Polaris (5 y 7 de octubre). En lo copiado solo cambia
`tools/normas.json` (una norma más de su autora) y entra una prueba suya,
`test_visor3d_cuelgue.py`, que aquí se salta sola (`ps -o time=` y `sample` son de macOS). Ninguna
herramienta que EMMA use cambia; `CAMBIOS.json` se reaplicó sin conflictos y `ESTADO.md` no se
mueve.

**Lo que quedó suelto de la sexta ronda.** La unidad 14 (la línea temporal en el tiempo de los
datos; §13, F7) no se había fusionado; las cuatro campañas de mutantes de la ubicación por módulo
estaban sin confirmar en su copia de trabajo (27 de 27 cazados); y la línea temporal trataba una
ubicación declarada como un evento más del plan.

Después, doce unidades, cada una en su rama local, de tres en tres, revisadas y fusionadas una a
una. La regla es la de siempre: se llama al original; lo propio de su autora se sustituye desde el
adaptador; nada de EMMA se escribe en `polaris/`. **La copia no se tocó:** no hay ningún cambio
nuevo en `CAMBIOS.json`.

### Errores

- **El freno HALT, también en lo que se importa tarde.** Confinar solo en `load` (§16) dejaba un
  hueco: lo que una herramienta importa dentro de una función (`borde.egress_check` con
  `escalar=True` trae `codigo_rojo`; `seguimiento` y `cronica`, `salida`; `atascos`, `cost_guard`)
  llegaba con las rutas de fábrica hasta la siguiente `load`. `app/polaris/__init__.py` instala
  desde `configure` un gancho de importación (`_BrakeHook`) que envuelve el cargador de todo módulo
  resuelto en `polaris/tools` y confina su freno al ejecutarlo. Es idempotente y no toca módulos
  de otra carpeta (las copias temporales de `scripts/mutants.py` y `scripts/polaris_tests.py`); el
  barrido de `load` queda para lo importado antes del gancho. Límite que queda: un módulo cargado
  por ruta con `spec_from_file_location` no pasa por el gancho (en la copia, ninguno de esos define
  freno). La `_nota` del registro generado decía que los cerebros de nube estaban «pendientes de
  decisión»: corregida (§1). Pruebas en `tests/test_egress.py`; mutantes `polaris_halt.json`.
- **La huella de la fuente no depende del sistema.** De las seis pruebas rojas de Polaris que tocan
  herramientas en uso, dos alcanzaban a EMMA. `app/evidence/vault.py` escribía la copia del informe
  en la bóveda en modo texto: en Windows entraba con CRLF y el `sha256` de la fuente que queda en
  la firma difería del de Linux para el mismo informe. Ahora se escribe con LF. Las firmas hechas
  en Windows antes del cambio conservan su huella; no se reescriben
  (`compliance/record-integrity.md` §3.23). La otra: el freno de memoria de la malla no se
  comprobaba aquí por faltar `resource` (§3). Las cuatro restantes no alcanzan a EMMA (§10).
- **Las pruebas de la copia ya no la ensucian**, corren con el intérprete de EMMA y cada roja lleva
  su causa en el informe generado (§10).
- **Un familiar nombrado ya no escapa a la des-identificación** (§12).
- **Los avisos legales, comprobados en un instalador construido.** `README.md`, `CHANGELOG.md`,
  `MANIFEST.sha256` y `ADOPTADO.txt` se suman a los cinco que ya viajaban, y viajan también las
  fichas de las herramientas (`tools/fichas/`), que la consola enseña. En
  `desktop/release/win-unpacked/resources/` los nueve están en `polaris/` y en
  `backend/_internal/polaris/` con la misma huella que los de la copia; van las 103 herramientas y
  no van `polaris/tests/`, pytest ni TotalSegmentator; y el backend congelado carga las mismas
  herramientas que en desarrollo. **Sin comprobar:** ejecutar el instalador y abrir la ventana, y
  que `GET /api/polaris/estado` lea las fichas y `ADOPTADO.txt` dentro del congelado (el instalador
  se construyó antes de fusionar esa unidad).
- **Textos que habían dejado de ser ciertos:** la cabecera de `volumes/geometry.py` daba por
  pendientes `spacing()` y `lesions()` (§7); `ADOPTADO.txt`, lo que el §4 decidió; `NOTICE` decía
  que los cambios «se anotarán»; y los §8 a §10 de este documento.

### Funciones nuevas

- **La copia, a la vista** (`GET /api/polaris/estado`; `ground/PolarisPanel.tsx`, al final de la
  consola de Tierra): el commit adoptado y, por herramienta, si carga (con su motivo), su ficha
  literal y si EMMA la pide por su nombre; además, los cambios de `CAMBIOS.json`. «En uso» es la
  lista `EMMA_USES` de `backend/app/api/polaris.py`, atada por prueba a los `load("…")` de
  `backend/app`: una «copiada sin uso» puede cargarse igualmente porque otra la importa. La
  interfaz no redacta ni presenta Polaris como algo que decide; lo clínico por `ia.py` sigue negado
  (§2).
- **Densidad (HU) de cada lesión** (§7.5): mediana, media, desviación, percentiles 10 y 90 y
  vóxeles, con el parénquima sin lesiones del mismo estudio como referencia. Por debajo de 50
  vóxeles no hay cifra sino «no valorable» (mínimo de EMMA, sin validar contra lecturas humanas).
  Se ve bajo el visor de cada estudio y en la comparación entre dos, que enseña las dos densidades
  sin columna de cambio: la fase de contraste cambia la HU y un NIfTI no la declara. No clasifica
  ni alerta.
- **El esqueleto del propio TAC** (`app/volumes/skeleton_view.py`;
  `GET /api/anatomy/skeleton/own`). Con una segmentación `esqueleto` vigente, la vista anterior, los
  centroides por hueso y el dolor referido salen del TAC del tripulante; sin ella se enseña la de
  referencia, y la respuesta dice cuál es y por qué. Se llama tal cual a
  `visor3d.proyecta_anterior` y `_uv`. **Divergencia:** la función dibuja por índices y su
  comentario dice «canónica RAS», pero con la rejilla RAS en la que EMMA guarda los volúmenes la
  figura sale cabeza abajo (medido con `esqueleto-4`): EMMA le entrega el mapa en
  derecha-anterior-inferior y comprueba el sentido en la `ext` que devuelve; si no cuadra, enseña
  la de referencia y dice por qué. No se llama a `_reconstruye`, `_simetriza_costillas`,
  `_puentea_columna` ni `_une_fragmentos`: rellenan lo que el modelo no segmentó. El ancla
  hígado/bazo con la que Polaris comprueba el espejo no existe en el mapa publicado: EMMA contrasta
  los nombres izquierdo/derecho y el orden de la columna con el afín, que no es una comprobación
  independiente (no caza un NIfTI que declare mal su orientación). Se calcula al servir desde el
  zip firmado; nada se escribe en el ledger. El dolor sobre esa figura, en §14; en `esqueleto-4` el
  ajuste vale, pero cerca del umbral (error medio 44 mm, peor 75 mm, umbral 80 mm).
- **Resumen de dolor en PDF** (§14).
- **La frase literal de la fuente en la segunda firma.** `fuente_clinica.cotejar` devuelve por
  diseño solo sí/no y huellas («el fragmento y el contenido no salen de aquí»), y quien pone la
  segunda firma tiene que leer la frase del informe. No se cambia la copia:
  `app/evidence/vault.py::locate` lee aparte la copia de la bóveda de EMMA (texto des-identificado),
  solo si `cotejar` confirmó y con la misma huella; localiza el tramo con el `normaliza` de la copia
  como árbitro y deja su propia línea de acceso (`FRASE-…`, sin el texto). La frase, su puntero y
  la huella del texto quedan en el asiento `draft-countersign` (`source_quote`;
  `record-integrity.md` §3.24); si la firma declara lo que vio y la bóveda ya no da eso, 409 y sin
  asiento. Las contrafirmas anteriores se siguen verificando. Consecuencia: redactar el informe ya
  no retira la frase; hay que redactar además esa contrafirma.
- **La puerta del NIfTI ofrece limpiar** (`app/volumes/privacy.py::clean`; `POST /api/volumes` con
  `clean=true`). La puerta no se ablanda: no hay lista de textos permitidos. Al rechazo dice si
  limpiar aquí lo dejaría entrar; solo con la petición explícita del operador se vacía la cabecera
  con `nifti_limpio` de Polaris, y lo limpio **vuelve a pasar la misma puerta**. Reglas de EMMA
  alrededor, porque `nifti_limpio` se escribió para volúmenes que ella misma calcula y aquí hay que
  devolver el mismo estudio: la geometría y la escala del original se reponen (dejaría `sform` y
  `qform` en el mismo afín con código 1, y `pixdim`, las unidades y `scl_slope`/`scl_inter` de
  fábrica: un TAC guardado en crudo perdería sus HU); el fichero se escribe aquí, sin hueco tras la
  cabecera, sin nada detrás de los vóxeles y con el gzip sin nombre ni fecha; y antes de devolverlo
  se comprueba que los vóxeles son, bit a bit, los recibidos. Se guarda y se firma el limpio; el
  asiento declara los nombres de los campos vaciados, nunca su contenido, y la huella del recibido
  y la del guardado. Lo escrito dentro de la propia imagen ni se mira ni se limpia, y se dice.
- **La copia literal, clasificada como SOUP** (`compliance/software-safety-classification.md` §4 y
  §4.2; lo pendiente del §16). La frontera es quién mantiene el código: la copia literal es SOUP;
  lo adaptado a mano (la lista `ADAPTED` de `tests/test_polaris_headers.py`) y el pegamento son de
  EMMA. La ficha tiene una fila por herramienta que EMMA pide por su nombre y otra tabla para lo
  que llega por otro camino (guiones de desarrollo, `transcribe_audios` como programa aparte,
  datos generados una vez, el visor web): qué se usa de ella, desde qué módulo, en qué clase, qué
  pasa si falla y a qué peligro del expediente lleva, qué lo vigila en EMMA y qué dice su prueba
  en Polaris. Añade qué impide que las herramientas dormidas hagan algo, los requisitos de
  entorno, las anomalías conocidas (las pruebas de Polaris que aquí no pasan sobre una herramienta
  en uso) y qué revisar al sincronizar. `tests/test_soup_polaris.py` la lee como dato y falla si
  deja de decir la verdad. Al escribirla salieron cuatro dependencias que viajaban o se instalaban
  sin ficha: `reportlab`, `pypdf`, Whisper y la capa NER. **Lo que deja abierto, y lo dice:** los
  módulos que llaman a la copia y no tienen fila propia en la tabla de elementos (§3) heredan la
  clase del conjunto (desde el 2026-10-21 tienen fila todos menos `evidence/vault.py` y
  `evidence/source_check.py`, cuya clase queda por decidir con la de `evidence/citations.py`); las anomalías que publica la propia Polaris (`polaris/docs/lo-que-falta.md`,
  su `CHANGELOG.md`) no se han revisado una a una contra la ficha; y el número de cláusula que
  cita para las anomalías no se ha cotejado con el texto de la norma.

### Cruces entre unidades, cazados al fusionar

- Una prueba del registro de gasto fallaba según el orden de ejecución: `cost_guard.COST` se fija
  al importar y otra prueba lo había cargado con otro estado.
- `scripts/mutants.py` copiaba `scripts/` dos veces tras juntar las dos unidades que lo ampliaron,
  y ninguna campaña arrancaba; la suite no lo ve porque no ejecuta el arnés.
- La unidad Hounsfield (`[hnsf'U]`) se declaró solo en la tabla de la interfaz, y las dos tablas
  tienen que coincidir (`tests/test_display.py`).
- La causa de `test_visor3d_malla_recorte` caducó en cuanto entró `compat/resource.py`; el propio
  informe de pruebas lo avisó.
- La ficha de SOUP salió antes de fusionar el esqueleto del propio TAC: su prueba falló al
  juntarlas porque `visor3d` tenía un módulo más que la llamaba, que es para lo que está. Y daba
  por «sin explicar» cuatro aserciones de `test_decision_alto_riesgo` que otra unidad había mirado:
  separadas una a una, son tres causas y ninguna alcanza a EMMA (§10).

### Verificación

- **Suite de EMMA.** Entera tras cada tanda de fusiones: 1713 pruebas en verde al empezar, 1738
  con las unidades 1 a 3, 1773 con las seis primeras y, con las unidades 1 a 7, 9 y 10, 1803 en
  verde y una en rojo: la unidad Hounsfield de arriba, arreglada. **Sobre el árbol final, con las
  unidades 8, 11 y 12, no se ha pasado entera todavía:** la pasada que corría la detuvo el equipo
  por falta de memoria. Tras cada una de esas tres fusiones se pasaron las pruebas de sus áreas,
  `ruff` y `mypy`.
- **Mutantes**, sobre `main` y tras fusionar: las de la línea temporal y la ubicación al empezar,
  doce campañas con las unidades 1 a 6 y 9 (116 de 116) y trece con las unidades 7, 8, 10 y 11
  (122 de 122). **Quedan por correr sobre el árbol final** las campañas que la ronda toca y que no
  se han pasado desde su último cambio, entre ellas las tres de la ficha de SOUP.
- **Pruebas de la copia:** 89 verdes, 52 rojas y 15 saltadas de 156, todas las rojas con su causa
  (`polaris/PRUEBAS.md`). Una roja menos que al empezar: `test_visor3d_malla_recorte`.
- **Interfaz:** `tsc` limpio y 241 pruebas de lógica en verde. Pasada visual con la interfaz
  compilada, en un Chrome sin ventana: el panel de la copia, los enlaces de exportación, la
  densidad en un estudio y en la comparación, el esqueleto del propio TAC con el dolor encima, y
  el rechazo y la limpieza de un NIfTI; y el PDF de dolor, leído. De esa pasada salieron tres
  arreglos: el panel escribía «Anticipa» y «Md_to_pdf_pro» por una regla de estilo heredada, la
  figura decía «1 informes» y los huesos se llamaban «Clavícula izquierdo» y «Escápula derecho»
  (este, anterior a la ronda).
- **Humo real:** cada unidad contra un servidor propio. La limpieza del NIfTI, con tres ficheros
  hechos de un TAC de ejemplo: rechazo con oferta, vóxeles, afín y HU idénticos tras limpiar, y ni
  el nombre inventado ni el texto técnico en ninguna respuesta, en la auditoría ni en el fichero
  guardado.
- **Lo que no se ha visto:** la frase de la segunda firma en pantalla (hacen falta el modelo local
  y Tesseract; su recorrido entero se probó en proceso) y el instalador en marcha.

### Pendiente de decidir (lista vigente)

**La lista vigente es la del final del §18.** Esta es la de la séptima ronda, tal como quedó.

- **Segunda firma:** ~~hoy se puede contrafirmar con la cita «no localizada», y la API acepta una
  contrafirma de informe que no declara haber visto la frase (queda `vista: false`, rotulada en
  amarillo). ¿Debe bloquear alguna de las dos? ¿Se enseña la frase también en la primera firma?~~
  Decidido el 2026-10-13: las dos se rechazan (422, sin asiento) y la primera firma puede llevar
  la frase (`app/countersign_rule.py`, `compliance/record-integrity.md` §3.24).
- **Clasificación:** dar fila en la tabla de elementos a los módulos que llaman a la copia, y
  decidir la clase de `evidence/vault.py`, `evidence/source_check.py` y `evidence/citations.py`:
  lo que enseñan lo lee quien pone la segunda firma de un borrador de Clase C. Y revisar contra la
  ficha las anomalías que publica Polaris.
- **Esqueleto del propio TAC:** silueta suavizada o reconstruida; colocar cada zona anclada en el
  centroide de su hueso (el modo `DIRECTO` de Polaris: quitaría el desfase lumbar, pero cambia
  también la figura de referencia); guardar un ancla visceral para comprobar el espejo.
- **Densidad:** cómo se declara la fase de contraste de un estudio; el mínimo de 50 vóxeles.
- **Instalador:** ejecutarlo y abrir la ventana. `npm run dist` recompila el visor web con
  `npm ci` dentro de `polaris/tools/visor3d_web/` (exento por ruta en la prueba de la copia) y
  reescribe `backend/app/data/polaris_web/`: ¿se compila fuera de la copia?
- **Des-identificación:** ~~el nombre delante del parentesco («con Rosa Beltrán, su cuñada»)~~
  (cerrado el 2026-10-20 con reglas deterministas, §12; queda el nombre de pila suelto al principio
  de la frase como límite declarado); la capa NER sigue sin usarse, y con ella `deid_ner` y el cambio `_python_ner` de `CAMBIOS.json` (§12).
- **`_lock.py` en Windows** (§10): hace falta pegamento antes de adoptar cualquier escritor.
- **Muestra `esqueleto-4`:** su índice firmado conserva «Clavícula izquierdo» y «Escápula derecho»;
  se corrige al regenerarla (`scripts/build_volume_samples.py`), que cambia su huella.
- «Caso clínico» leído del texto, y leer también el alcance (§7.8).
- Etiquetas de nivel de evidencia y motivo de alto riesgo con el texto de Polaris (§7).
- Las seis herramientas copiadas sin uso (§9).

## 18. Octava ronda (2026-10-08)

Encargo: «sigue arreglando Polaris y copiando lo que falta por copiar». Una fase previa en serie
(la copia toca ficheros compartidos) y diez unidades, cada una en su rama local, de tres en tres,
revisadas y fusionadas una a una. Nada se subió a ningún sitio. **Ningún cambio nuevo en
`CAMBIOS.json`:** la copia no se tocó.

### Copia al día con Polaris `2052793` y 35 herramientas más

- **Tres commits nuevos en Polaris (8 de octubre).** En lo copiado cambian `tools/salida.py` (una
  respuesta a su titular no gasta el cupo de avisos) y `tools/visor3d.py` (un modelo ilustrativo
  del reservorio: `modelo_ilustrativo`, `ajusta_modelo_rigido` y auxiliares). Ninguna función que
  EMMA llame. `CAMBIOS.json` se reaplicó sin conflictos.
- **35 herramientas locales y deterministas, copiadas sin uso** (decisión del usuario): la copia
  pasa de 103 a 138. La lista está en `polaris/ADOPTADO.txt`, bloque «2026-10-08». Ninguna
  arrastra por imports un módulo que no estuviera ya. Quedaron fuera tres de las candidatas:
  `onco` y `audit_herramientas` abren ellas mismas una URL, y `contexto_lazo` arrastra módulos de
  red y `playwright`. Ninguna entra en `EMMA_USES`.
- **Pruebas que `tests auto` no reconocía.** `polaris_sync.py` admite `test <fichero>` en
  `ADOPTADO.txt` para las que prueban algo copiado sin nombrar una herramienta `x.py`:
  `test_visor3d_carga.py`, `test_sys_path_limpio.py` y `test_atribucion.py`, las tres verdes aquí.
  Entra también `tools/orquestadores.json`, que `cost_guard` y `enruta_comite` citan (ninguna
  herramienta copiada lo abre hoy).
- **El clon** vive ahora en `C:\Users\tidus\polaris-clon`, con el envío desactivado; el anterior
  estaba en la carpeta temporal de otra sesión.

### Errores

- **Un solo cerrojo de consola** (`app/polaris/console.py`). `kb`, `export` y `volumes/spine`
  redirigían la consola del proceso cada uno bajo su cerrojo; cruzados, el texto de Polaris caía
  en el búfer de otro y el control de la cadena vertebral —que EMMA lee de ese texto— salía «no
  revisada» en un resumen firmado, o `sys.stdout` no volvía. Ahora hay una sola captura,
  `console.captured()`, y una prueba impide un `redirect_stdout` propio en `app/`. El orden de
  toma: primero el cerrojo del adaptador, después el de consola. Lo que cuesta: mientras `kb`
  reindexa, exportar un PDF y revisar una cadena esperan. El fallo no se reprodujo con el código
  antiguo en el servidor; lo demuestran los mutantes que devuelven a cada adaptador su cerrojo.
- **La bóveda, dentro del cerrojo** (`app/evidence/vault.py`). La copia del informe se escribía
  antes de tomar `_LOCK`: dos cotejos del mismo informe a la vez se pisaban. Reproducido con el
  código anterior (`no_localizada` espurio en 5 de 5 ejecuciones de 16 peticiones en 8 hilos).
  Ahora el cotejo entero y la lectura de la frase van bajo el cerrojo y la copia se sustituye de
  golpe (`os.replace`). La huella de la fuente no cambia. Dos procesos de EMMA sobre el mismo
  estado siguen sin cubrir.
- **El primer uso del borde, una sola vez** (`core/egress.py`, `app/polaris/__init__.py`).
  `@cache` no impedía que dos hilos sembraran el señuelo a la vez, y en Windows el segundo
  `os.replace` daba `PermissionError`; `configure()` ejecutaba `registry()` ocho veces con ocho
  hilos. Los dos, bajo cerrojo. Si el sembrado falla, la puerta no se da por lista y se reintenta.
- **El candado de Polaris en Windows** (`compat/winlock.py`; decisión del usuario). `_lock`
  sondeaba al dueño con `os.kill(pid, 0)`, que aquí no distingue un proceso muerto, y soltar el
  candado fallaba si otro proceso estaba leyendo de quién era (WinError 32). El pegamento da una
  sonda con `OpenProcess` y `WaitForSingleObject` y un `remove` que insiste un segundo.
  `test_lock_dueno` pasa de 8 de 9 a 9 de 9 y `test_seguimiento_carrera` de 3 de 6 a 6 de 6. Lo
  instala el cargador de `app.polaris`, y `compat/sitecustomize.py` en los procesos de las
  pruebas de la copia. **El veto a adoptar un escritor de `seguimiento` sigue** (§10): su
  `os.replace` falla si un lector tiene abierto el fichero, y los lectores no toman el candado.
- **Textos que habían dejado de ser ciertos.** «Los cerebros de nube ni se registran ni se
  copian» (están en la copia; no se registran y por eso no se pueden alcanzar); `ADOPTADO.txt`
  daba por sin uso cuatro herramientas en uso; `ORIGEN.md` y `ESTADO.md` solo nombraban
  `compat/fcntl.py` (la lista sale ahora de la carpeta); la tabla «llaman a la copia» del `NOTICE`
  callaba diez nombres y la ficha de SOUP, los de catorce filas. `tests/test_polaris_texts.py` ata
  esas tablas a lo que el código pide, leído con `ast`.

### Lo decidido en esta ronda y hecho

- **El visor web se compila fuera de la copia** (`frontend/scripts/build-polaris.mjs`): en una
  carpeta temporal del sistema, con `npm ci` cada vez (necesita la caché de npm o red). Los cuatro
  ficheros de `backend/app/data/polaris_web/` salen idénticos byte a byte. `test_polaris_copy.py`
  ya solo tolera `__pycache__` dentro de `polaris/`.
- **La muestra `esqueleto-4`, regenerada** desde las máscaras guardadas, sin volver a segmentar
  (`build_volume_samples.py --only esqueleto-4`). Los 62 binarios son idénticos; en el índice
  cambian los cuatro nombres («Clavícula izquierda»…) y entra el control de la cadena vertebral,
  que `assets.build` firma en toda segmentación nueva. Huella de `visor.zip`: de `ec61e35f…` a
  `f6983be6…`. Un almacén que ya tuviera registrada la muestra antigua conserva su asiento.
  `--only` existe porque rehacer las otras tres les cambiaba la huella sin que nadie lo pidiera
  (cuatro campos de cabecera del NIfTI).
- **Lo que publica Polaris, contra la ficha de SOUP** (`software-safety-classification.md` §4.2):
  leídos enteros `polaris/docs/lo-que-falta.md` y `polaris/CHANGELOG.md`; ocho herramientas con
  fila tienen entrada y evaluación, y la prueba guarda la huella de los dos documentos para que
  una sincronización obligue a releerlos. Dos cosas que alcanzan a EMMA y ya constan: `deid`
  enmascara y verifica con los mismos patrones (lo cuenta `test_deid_procedencia.py`; EMMA lo
  trataba ya como límite, H17), y del freno `HALT` EMMA dice si está puesto y dónde, pero no desde
  cuándo, y nada avisa solo.
- **El instalador.** `orquestadores.json` viaja; `winlock` y `memguard` se declaran al congelador;
  `resource.py` y `sitecustomize.py` no viajan. Con 138 herramientas no entra ninguna biblioteca
  de terceros nueva (el único import nuevo es `scipy.spatial.transform`, de `visor3d`).
- **Las causas de las rojas nuevas** (§10): seis explicadas leyendo la aserción que cae y dos
  caducadas fuera. Dos son de Windows en herramientas nuevas: `inventario` y `rodaje_muro` montan
  con `\` una ruta que git solo entiende con `/`.

### Cruces entre unidades, cazados al fusionar

- **El pegamento del candado recordaba los módulos por su `id`**, que Python reutiliza: un `_lock`
  nuevo con el `id` de uno recogido se quedaba sin pegamento y una prueba fallaba según el orden.
  La marca va ahora en el propio módulo.
- La ficha de SOUP daba por roja `test_seguimiento_carrera`, que pasa con el pegamento.
- `test_polaris_copy.py` fallaba en el repositorio principal por el `node_modules` que el guion
  antiguo había dejado dentro de la copia; retirado.
- La campaña `packaging.json` mutaba un texto que la unidad del instalador cambió; puesta al día.

### Lo que no se copia, por su nombre

**Decisión del usuario (2026-10-08):** las herramientas locales y deterministas se copian (fase 0
de esta ronda, sin uso) y **el resto queda declarado fuera una a una**. Hasta ahora a casi todas
las cubría una frase de `polaris/ADOPTADO.txt` —«las demás herramientas: red, nube, macOS, datos
personales o el flujo de trabajo de su autora»—, que no se puede contrastar: una herramienta
nueva de Polaris quedaba «fuera» sin que nadie la hubiera mirado.

**Las cuentas, medidas contra el clon en `2052793`:** `tools/` tiene 274 módulos; 138 están en
`polaris/tools/` y 136 no. Los 136 llevan ahora su línea (`#   nombre   qué es`) en el bloque
final «NO copiado» de `ADOPTADO.txt`, cada uno una sola vez y agrupados por motivo. De ellos, 47
ya tenían nombre o comodín en §15 o en ese mismo comentario (`vega_*`, `laminillas_*`,
`juez_normas`…); a los otros 89 solo los cubría la frase genérica, que desaparece.

**El motivo de cada una es lectura de su docstring, no una auditoría de su código.** Para las
tres locales de abajo sí se abrió el código. La línea de cada herramienta está en `ADOPTADO.txt`;
aquí va solo el reparto:

| Motivo | Cuántas | Cuáles |
|---|---|---|
| Nube: cerebros y servicios de IA (§1, fuera para siempre) | 17 | `chatgpt`, `gemini`, `glm`, `grok`, `openrouter`, `perplexity`, `consensus_mcp`, `scite_mcp`, `_oauth_refresh`, `elicit`, `evidencia`, `radar_literatura`, `aeo`, `bench_jev`, `elevenlabs_voz`, `vision_n1`, `nube_n1` |
| Red: registros de ensayos y literatura | 7 | `actualizar_nct_cache`, `cde_fetch`, `cn`, `cn_fetch`, `radar_cn_vps`, `radar_navegador`, `radar_ned_diario` |
| Red: Google (Calendar, Drive, YouTube) | 7 | `calendar_sync`, `calendar_write`, `drive`, `subir_historial_drive`, `historial_sync`, `youtube`, `yt_inbox` |
| Red: X e Instagram | 10 | `_xurl`, `x_centinela`, `x_dms`, `x_guardados`, `x_mcp_puente`, `x_mentions`, `x_radar`, `ig_inbox`, `instagram_dm`, `reel_digest` |
| Red y datos personales: Telegram, WhatsApp y contactos | 10 | `bot_telegram`, `buzon_ideas`, `enviar_hoy`, `espejo_nudge`, `digest`, `wa_tracker`, `leer_contacto`, `memoria_contactos`, `voz_intima`, `presorteo` |
| Red y datos personales: correo (IMAP y SMTP) | 6 | `correo_outbox`, `correo_smtp`, `correo_responder`, `correo_triage`, `email_archive`, `adjuntos_clinicos` |
| Red: otros servicios de terceros | 4 | `postdicom`, `umami`, `ritmo`, `viajes_precios` |
| Su asistente Vega, sus reservas y su oncología (§15) | 10 | `vega_gate`, `vega_metrics`, `vega_sesion`, `vega_vision`, `perfil_vega`, `acciones_datadas`, `centinela_ned`, `estado_caso`, `reservas`, `pipeline_vacuna` |
| Sus láminas de patología y las copias «N1» (§15) | 19 | las diecisiete `laminillas_*` que no se copian, `exporta_n1` y `puerta_n1` |
| El juez de sus mensajes salientes (depende de sus ganchos) | 6 | `juez_normas`, `prefiltro_juez`, `cotejo_frases`, `nivel_salida`, `gate_escalera`, `gate_etiqueta` |
| macOS: launchd, Llavero, Apple MLX, Tailscale, Unix | 11 | `activar_daemon`, `vigia`, `backup`, `migrar_secretos`, `colgados_stdin`, `modelo_mlx`, `bench_modelos`, `archivar`, `preview_remoto`, `staging`, `sync_playbook` |
| git: el repositorio de Polaris, su espejo público y su web | 13 | `release`, `publicar`, `publicar_sync`, `espejo_reiniciar_historial`, `pr_portar`, `ci_barrido`, `cerrar_sesion`, `dependencias`, `tests_afectados`, `seguridad_sweep`, `seguridad_sweep_daemon`, `web_novedad`, `web_revertir` |
| Su sistema por dentro y sus sesiones de Claude Code | 13 | `anatomia`, `anatomia_mapa`, `anatomia_push`, `observatorio`, `mcp_server`, `archivar_nota`, `claude_lazo`, `continuidad_auto`, `tiempo_sesiones`, `memoria_contradicciones`, `repeticiones_semana`, `radar_taller`, `radar_contacto` |
| Locales que se miraron para copiar y no entraron | 3 | `onco`, `audit_herramientas`, `contexto_lazo` |

**Las tres locales que no entraron, y por qué** (aquí sí se leyó el código):
- **`onco`:** consulta en local el grafo de oncología OnCo, pero lo baja ella misma con
  `urllib.request.urlopen`, y sus datos son CC BY-NC 4.0 (lo declara su cabecera): ni la salida
  pasa por `core/egress.py` ni la licencia de los datos es compatible con el paquete.
- **`audit_herramientas`:** auditoría de uso y salud de las herramientas de su autora; abre ella
  misma una URL con `urllib.request.urlopen`.
- **`contexto_lazo`:** el contexto que su lazo antepone a cada trabajo. No abre red, pero arrastra
  por imports `radar_navegador` y `radar_ned_diario`, y con ellos `radar_cn_vps` (que importa
  `playwright`), `bench_jev` y `onco`: copiarla metería en la copia cinco módulos de red.

**No son las únicas sin red a la vista.** Por su docstring tampoco salen a internet
`laminillas_color` (matemática de tinciones), `radar_taller`, `reservas`, `pipeline_vacuna`,
`estado_caso`, `acciones_datadas`, `perfil_vega`, `vega_metrics`, `tiempo_sesiones`,
`memoria_contradicciones`, `repeticiones_semana` ni `radar_contacto`. Quedan fuera por lo que
son —el caso, el asistente y las sesiones de su autora—, no por la red. **Sin comprobar** en su
código; si alguna interesa, copiarla es decisión del usuario.

**Lo que en `tools/` no es un módulo** (carpetas, guiones de shell, datos, notas: 54 entradas sin
copiar) va en la primera parte del bloque, **clasificado por su nombre y sin abrir**. Lo único
comprobado es que ningún módulo copiado nombra los cuatro JSON que quedan fuera
(`anatomia_huella.json`, `juez_rubricas.json`, `puertos_excepciones.json`,
`.centinela_secrets.example.json`).

**Aclaración al «Fuera, y por qué» del §15, que mezcla dos cosas.** `replay_guard`, `replay_gate`,
`esquema_estado`, `prueba_entregable`, `caja`, `promesas_caso` y `aprobaciones` **están copiados
y sin uso**: no están fuera de la copia, sino fuera de `EMMA_USES`. Lo mismo `laminillas_jaulas`,
`laminillas_sello` y `laminillas_ventanilla`, que entraron por imports. Fuera de la copia, de esa
lista, están `vega_*`, `perfil_vega`, `acciones_datadas`, el resto de `laminillas_*`, `vision_n1`,
`nube_n1`, `exporta_n1`, `puerta_n1` y la carpeta `panel_vision/`.

**Un comentario de `ADOPTADO.txt` que ya no era verdad.** La sección «Trazabilidad y línea
temporal» decía «solo copiadas, sin uso todavía» de seis herramientas. Cuatro están en
`EMMA_USES` (`backend/app/api/polaris.py`): `cronica`, `cascada_mapa`, `anticipa` y
`paso_consolidacion`. Sin uso siguen `cascada_clinica` y `caja`, y así lo dice ahora.

**Cómo se vigila, y qué no cabe en la suite.**
- `backend/tests/test_polaris_left_out.py` (suite normal, sin red): ninguna herramienta copiada
  figura a la vez en el bloque «NO copiado», ninguna se nombra dos veces, y el bloque sigue siendo
  solo comentarios y sin la frase genérica. Campaña `tests/mutants/polaris_left_out.json`.
- `backend/scripts/polaris_left_out.py <clon de Polaris>`: que **toda** herramienta de Polaris
  esté o copiada o nombrada, que ningún nombre sobre y que toda carpeta o fichero de `tools/` sin
  copiar esté nombrado. Necesita el árbol de Polaris en el commit de `ADOPTADO.txt`, y el clon no
  viaja con EMMA: **por eso es un guion y no una prueba**. Se pasa a mano al poner la copia al
  día, junto a `polaris_sync.py`; una herramienta nueva de Polaris lo pone en rojo hasta que se
  copia o se nombra.
- Todo lo añadido a `ADOPTADO.txt` son comentarios: `polaris_sync.py` contra el clon no cambia
  nada más en `polaris/`, y `tests/test_polaris_copy.py` sigue en verde.

### Verificación

- **Suite de EMMA**, entera: 1863 en verde tras la fase previa y **1912 en verde sobre el árbol
  final**, sin ninguna roja.
- **Mutantes**, en serie sobre el árbol final: 35 campañas, **305 de 305 cazados**. Son las de
  esta ronda, las que mutan la copia (cambió `visor3d.py`) y las que el §17 dejó sin pasar (las de
  la ficha de SOUP, el esqueleto, la privacidad del NIfTI, el freno y la línea temporal). Las
  demás campañas no se han pasado en esta ronda.
- **Pruebas de la copia:** 112 verdes, 56 rojas y 20 saltadas de 188, todas las rojas con su causa
  y ninguna del pegamento de EMMA (`polaris/PRUEBAS.md`).
- **Instalador construido** (`desktop/release`, 2026-10-08): los nueve avisos están en
  `resources/polaris/` y en `resources/backend/_internal/polaris/` con la huella de la copia; van
  las 138 herramientas, sus fichas y los cuatro JSON; de `compat/` solo `fcntl.py` como fichero
  suelto; no van `polaris/tests` ni pytest; y `polaris/` queda limpio tras compilar. El backend
  congelado, arrancado a mano con el estado en una carpeta temporal: `GET /api/polaris/estado` da
  el commit, 138 herramientas, 135 cargan (las mismas tres que en desarrollo no) y ningún fichero
  en falta. Arranca, así que `winlock` va dentro (lo importa el arranque).
- **Sin comprobar:** ejecutar el instalador y abrir la ventana; que el candado se tome de verdad
  dentro del congelado (nadie lo toma); `npm ci` sin caché y sin red; la interfaz no se ha mirado
  en pantalla en esta ronda (ninguna unidad la cambió); y las pruebas `live` y `external`.

### Pendiente de decidir (lista vigente)

**Al día tras el remate del 2026-10-09** (apartado siguiente): lo que el remate cerró ya no está
en esta lista.

Nuevo en esta ronda:

- **Doce herramientas más sin red en su docstring**, fuera por ser el caso, el asistente o las
  sesiones de su autora (lista en «Lo que no se copia», abajo). Y `tools/templates/`, decidida
  fuera: es lo único que le falta a `test_rebuild_agents`.
- ~~**`estado_actual`** importa una prueba de Polaris en su orden `cotejado`; las pruebas no viajan
  y esa orden fallaría en la aplicación instalada. EMMA no la llama.~~ Hecho el 2026-10-20
  (decisión del usuario), como cambio §5a en `polaris/CAMBIOS.json`, reaplicado por
  `polaris_sync.py`: `fecha_cotejo` (tres líneas) pasa tal cual de
  `tests/test_perfil_clinico_al_dia.py` a la herramienta y `cotejado` deja de tocar `sys.path` y
  de importar la prueba, que no se toca. El fichero lleva su línea SPDX y el aviso con el commit
  de origen; constan en `ORIGEN.md` y `NOTICE`. Comprobado en una carpeta fuera del repositorio:
  sin `tests/` al lado, la orden original cae con `ModuleNotFoundError` y la parcheada escribe el
  mismo registro que la original con las pruebas presentes. `tests/test_packaging.py` vigila que
  ninguna herramienta copiada importe una prueba y que la función traída siga siendo la de la
  prueba (si Polaris cambia la suya, rojo).
- ~~**El freno `HALT`:** que avise solo, y que la consola lo pinte (hoy la fecha solo está en la
  API: `halt.since` de `GET /api/safe-mode`).~~ Hecho el 2026-10-20 (decimotercera ronda), por
  decisión del usuario. El backend compone el aviso (`halt.notice` en `GET /api/safe-mode`,
  `api/safe_mode.halt_notice`): qué es (el freno por fichero de Polaris, no el modo seguro: sin
  firma ni asiento, EMMA no lo pone y levantar el modo seguro no lo quita), desde cuándo (la
  fecha del fichero, rotulada «sin firma»), qué corta (la salida a internet: DONKI, OSDR RadLab,
  JPL Horizons y los registros de citas, que se sirven de lo guardado con su edad o se declaran
  ausentes), qué no (constantes, análisis, alertas y modelo local) y cómo se quita (borrando ese
  fichero; la consola no tiene mando). En modo sin red lo dice: ahí no sale nada con freno o sin
  él, y el aviso no se presenta como la causa del corte. La consola lo pinta tal cual en la celda
  «Red» de la franja común, en las dos consolas, en amarillo con triángulo (F.5-1, *off-nominal,
  attention required*), con la fecha por `formatUtc` y solo la explicación larga plegada; con el
  freno puesto la red ya no se rotula «abierta». «Avisa solo» es que el estado de la red se relee
  cada 30 s, al ritmo del estado del tripulante: un fichero puesto con la consola abierta aparece
  sin recargar; si una relectura falla, lo último visto se conserva marcado «sin actualizar» en
  cian. Lo que corta se compone desde `egress.ALLOWLIST`, no de una lista aparte. Límite: en la
  consola de Tierra es el estado del momento, sin retardo (como ya lo era el modo seguro).
  Pruebas en `tests/test_halt_notice.py` (con freno y sin él, en carpeta temporal) y
  `frontend/src/components/SafeMode.test.ts`; mutantes `halt_notice.json`. Visto en pantalla el
  2026-10-21, en las dos consolas y con un fichero puesto en una carpeta temporal
  (`compliance/hmi-state-of-the-art.md` §5.30 y §5.34.15): abierto, el aviso alarga la franja fija
  hasta tapar casi toda la ventana mientras no se pliega.
- ~~**Las pruebas de la copia dejan carpetas en el temporal del sistema** (sus `mkdtemp`): ¿se
  apunta `TMP` a la carpeta de la pasada?~~ Hecho el 2026-10-20 (decisión del usuario):
  `polaris_tests.py` da a las pruebas `TMP`, `TEMP` y `TMPDIR` en `tmp/`, dentro de la carpeta de
  la pasada (en el temporal del sistema, fuera de `polaris/`), y la borra entera al terminar; lo
  que se resista al borrado se dice por su ruta, no se calla. En el informe, `<tmp>` es ahora ese
  temporal. Probado con un Polaris de juguete (`tests/test_polaris_tests_runner.py`: el
  `mkdtemp` de una prueba cae en `<tmp>` y no en el del sistema; la pasada se borra con ficheros
  de solo lectura; lo que se resiste se nombra). Medido sobre las 191 pruebas reales de la copia
  en el cierre de la decimotercera ronda (`polaris/PRUEBAS.md`, regenerado ese día con la leyenda
  nueva): 115 verdes, 57 rojas y 19 saltadas, lo mismo que antes del cambio; los temporales de las
  pruebas salen como `<tmp>` y ninguna línea del informe nombra `<tmp del sistema>`.

Cerrado de la lista del §17: el pegamento de `_lock.py` (el veto sigue, por `os.replace`), el
visor compilado fuera, la muestra `esqueleto-4`, las anomalías que publica Polaris y la
construcción del instalador.

Sigue abierto, como en el §17:

- ~~**Segunda firma:** lo anterior quedó decidido el 2026-10-13 (bloquea con la cita «no
  localizada» o con la frase no vista; la frase, opcional, en la primera firma). Queda abierto
  su límite declarado: una segunda firma que cita algo que no es un informe guardado, o nada, no
  tiene frase que cotejar y se admite. ¿Debe toda segunda firma de alto riesgo citar un informe?~~
  Decidido el 2026-10-15 que sí (duodécima ronda): sin informe citado, 422 y ningún asiento; lo
  ya firmado sigue verificando y se rotula al leer (`compliance/record-integrity.md` §3.24).
- **Clasificación:** filas propias para los módulos que llaman a la copia; la clase de
  `evidence/vault.py`, `evidence/source_check.py` y `evidence/citations.py`; el número de cláusula
  de las anomalías, sin cotejar con la norma.
- **Esqueleto del propio TAC:** silueta y ancla visceral, abiertas. ~~Modo `DIRECTO`~~: decidido
  el 2026-10-20 adoptarlo, y hecho (`app/pain_on_skeleton.py`). Leído su código: está en el
  `main()` de `visor3d_superpone_focos`, que no se llama, y es una línea (`px, py = c["u"] * W,
  c["v"] * H`), así que EMMA la reproduce; la constante `DIRECTO = True` del módulo no la lee
  nadie, tampoco su `main()`. La zona anclada a un hueso que la figura trae entero va al centroide de ese hueso,
  en la de referencia y en la del TAC, y cada zona dice cómo se colocó (`placed_on`: `bone` o
  `fit`). **Dos divergencias, declaradas:** Polaris decide de todo o nada (si un foco no tiene
  hueso en el mapa, alinea todos), que con el mapa de EMMA no se daría nunca porque cabeza,
  abdomen o rodilla no tienen hueso, y aquí es zona a zona; y Polaris en modo directo no calcula
  el ajuste, y aquí se sigue calculando porque coloca las zonas sin hueso y sigue decidiendo si se
  pinta algo, con el mismo umbral (no cambia ningún nivel, umbral ni alerta). La zona sin hueso,
  con su hueso ausente o con él cortado por el borde no va a ningún centroide: sigue con el
  ajuste o se declara «fuera del estudio», como antes. En `esqueleto-4` (6 anclas): el ajuste
  sigue en error medio 44,4 mm y peor 75,1 mm, umbral 80,0 mm, y ese error ya no es la posición
  de las zonas ancladas, que caen sobre su hueso (0 mm; la lumbar se mueve 75 mm, a L3). Las
  zonas de la pelvis y las caderas, con el sacro y los ilíacos cortados, siguen con el ajuste. Una
  prueba vigila ahora el peor error en esa muestra, no solo la media: margen de 4,9 mm
  (`test_on_the_real_sample_ct_the_worst_anchor_stays_under_the_threshold`); campaña
  `tests/mutants/pain_on_skeleton_direct.json`. **Lo que cambia en la figura de referencia:** las
  11 zonas ancladas se mueven a su hueso (hasta 101 px, unos 79 mm: las caderas y los muslos), y
  allí el peor error del ajuste ya pasaba del umbral (101 px frente a 89,5) aunque la media no.
  **Hueso cortado por un lado** (decimocuarta ronda, 2026-10-21). «Cortado por el borde» era solo
  el de arriba o el de abajo: un húmero que el campo del TAC corta por el lado anclaba con el
  centroide de su trozo y su zona se pintaba sobre él. Ahora `volumes/spine.py` mide el campo del
  estudio en x, y y z (`field_mm`; `field_z_mm` sigue para la cadena vertebral) y
  `volumes/skeleton_view.py` compara los seis bordes, cada eje con su tolerancia (`EDGE_VOXELS`, la
  misma que ya usaba la z). Es código de EMMA alrededor de la copia: `proyecta_anterior` y `alinea`
  no cambian, ni ningún umbral. En `esqueleto-4` no cambia nada: el hueso más cercano a un lado,
  delante o detrás queda a 6 mm (su estudio es el TAC recortado a la caja del hueso con 3 vóxeles de
  holgura) y la tolerancia es de 4 mm; siguen las 6 anclas y el margen del peor error, 4,9 mm. Ese
  margen de 2 mm es estrecho: con un vóxel más de tolerancia los dos húmeros saldrían cortados y el
  dolor no se alinearía sobre la muestra (4 anclas, todas en la línea media). Los extremos del hueso
  se leen con el afín entero (una rejilla torcida por debajo de `OBLIQUE_TOLERANCE` desplazaba hasta
  12 mm leyendo solo la diagonal). Límite: el campo es la caja de las esquinas de la rejilla; lo que
  corta un campo de reconstrucción circular dentro de ella, o un estudio inclinado, no se ve.
  Campaña `pain_on_skeleton_direct.json` ampliada con tres mutantes sobre `skeleton_view.py`
  (`scripts/mutants.py` acepta un `target` por mutación).
- **Densidad:** el mínimo de 50 vóxeles. (La fase de contraste quedó decidida el 2026-10-13: la declara
  una persona y `fase()` sigue sin usarse; §7.5.)
- **Instalador:** ejecutarlo y abrir la ventana.
- **Des-identificación:** ~~el nombre delante del parentesco~~ (cerrado el 2026-10-20, §12: reglas
  deterministas; un nombre de pila suelto al principio de la frase queda como límite declarado,
  con prueba); la capa NER sigue abierta.
- «Caso clínico» leído del texto y el alcance (§7.8); las etiquetas con texto de Polaris (§7); las
  seis herramientas copiadas sin uso del §9, a las que se suman las 31 que quedan de esta ronda.

### Remate (2026-10-09)

Una auditoría de solo lectura contrastó este apartado con el código. Cuadraba; lo que faltaba era
poco, y se hizo en una fase previa en serie y cuatro unidades. Ningún cambio en `CAMBIOS.json`.

- **«Locales y deterministas» no era cierto para todas.** La clasificación se había hecho por
  docstring. Leído el código, cuatro salen de la copia (decisión del usuario): `borde_gateway`
  (un servidor HTTP que llama al modelo), `portguard` (abre un socket de escucha y mata procesos),
  `permiso_envio` (el Llavero de macOS) y `ok_envio`, que la importa. Quedan 31 de las 35, y la
  copia en **134 herramientas**. De las que quedan, varias llaman al modelo local (`ia.ask`) o
  lanzan `git` u `ollama` cuando se las llama: están dormidas, no son inertes. `ADOPTADO.txt`
  decía además que ninguna arrastraba «un módulo de red»; lo cierto es que ninguna arrastra un
  módulo que no estuviera ya copiado.
- **Cuatro pruebas de Polaris más, pedidas por su nombre:** `test_kpi_ned` (su herramienta no
  tenía ninguna), `test_rodaje_casa_base` y `test_healthcheck_state_aislado`, verdes, y
  `test_inventario_uso`, roja en 2 de 13 casos por ficheros que no se copian.
- **El inventario no importa lo que hace algo al importarse** (`app/polaris`: `NOT_IMPORTED`,
  con su motivo). `rodaje_muro` (lanza `git`) y `transcribe_audios` (un guion entero a nivel de
  módulo; hoy lo frenaba un import que falla) salen en `GET /api/polaris/estado`, en `ESTADO.md` y
  en la consola de Tierra como «no se importa», distinto de «no carga». `load("…")` por su nombre
  las sigue cargando. Una prueba mide que pedir el inventario no lanza procesos, ni escribe, ni
  abre conexiones, y que `rodaje_muro` importada a propósito sí lanza el suyo.
- **El freno `HALT` dice desde cuándo** (`halt.since` en `GET /api/safe-mode`): la fecha del
  fichero, no un asiento firmado. Ningún componente de la interfaz pintaba el freno, y sigue así.
  (Desde el 2026-10-20 la franja común lo avisa sola: lista vigente, arriba.)
- **Pruebas para los guiones de la copia**, que no tenían: `polaris_sync.py` sobre un Polaris de
  pega, `build_volume_samples.py --only`, y que las páginas del visor servido son las de la copia.
  Dos defectos salieron al escribirlas: `--only` con los argumentos mal ordenados abortaba con la
  muestra ya reescrita y el manifiesto con la huella antigua (ahora comprueba antes de rehacer
  nada); y `polaris_sync.py` se saltaba en silencio una línea mal formada de `ADOPTADO.txt`, con
  lo que esa herramienta se habría borrado de la copia (ahora aborta).
- **Documentos que la ronda no había tocado:** el apartado de la octava ronda en
  `docs/contexto/README.md`, los controles nuevos en `compliance/risk-management-file.md` (H17,
  H18) y el cerrojo de la bóveda en `compliance/record-integrity.md` (§3.23, §3.24).
- **Limpieza:** retirados `.git/lost-found/` (su commit colgante era idéntico a lo que entró en
  `7315b18`) y una carpeta de trabajo huérfana de la séptima ronda.

**Verificación del remate.**
- Copia: 130 herramientas cargan en Windows, 2 no cargan (`pwd`) y 2 no se importan, de 134.
  Pruebas de la copia: 115 verdes, 57 rojas y 19 saltadas de 191, todas con causa.
  `polaris_left_out.py` contra el clon: 134 copiadas y 140 declaradas fuera, «todo cuadra».
- Suite de EMMA, entera: tras fusionar las cuatro unidades, 1969 en verde y dos rojas, las dos de
  la prueba de la búsqueda por significado (abajo); ajustada esa prueba, **1971 en verde sobre el
  árbol final** (`c83f918`), sin ninguna roja.
- Mutantes, en serie: 26 campañas tocadas por el remate, 234 de 234 cazados. Una, la de
  `polaris_sync.py`, no corría tras hacer estricto el lector de la lista (su ancla aparecía dos
  veces); reparada, con una mutación más.
- Interfaz: `tsc` limpio y 243 pruebas en verde.
- **La prueba de la búsqueda por significado se relajó** (`tests/test_knowledge.py`): pedía que
  la sección «Segunda firma» saliera la primera y, al crecer la documentación indexada, bajó a
  la segunda. Ahora pide que salga entre las tres primeras; lo que demuestra (que las palabras
  solas no la encuentran entre las seis) no cambia.
- **Sin comprobar:** el instalador de `desktop/release` es anterior al remate y no se ha
  reconstruido; la consola de Tierra con el tercer estado no se ha abierto en un navegador; las
  pruebas `live` y `external`.

## 19. Cambio de cerebro de Polaris: el modelo del asistente (2026-11-03)

- **Antes:** el registro que EMMA da a `ia.py` (`app/polaris/__init__.py::registry`) llevaba el
  modelo del borrador de interpretación, `Settings.llm_model` (`qwen3.6:35b-a3b`).
- **Decidido por el usuario (2026-11-03):** «que sirva también en Polaris en vez del que hay». El
  cerebro local de Polaris pasa a `Settings.assistant_model` = `qwen3.5:9b` (primero `gemma4:12b-it-qat`; cambiado el mismo día tras medir 24 órdenes reales, `backend/app/core/config.py`), el del
  asistente de voz (`app/assistant/`), elegido midiendo en este portátil (RTX 4070 de 8 GB): banco
  de 17 casos, 11/12 órdenes, 3/3 respuestas solo con lo dado y 2/2 sin recetar, 0,70 s de
  mediana; el único de los tres candidatos que no cambió una cifra. Banco pequeño: orienta, no
  valida (`core/config.py`).
- **Lo que no cambia:** sigue siendo `local-ollama`, solo loopback (§1); lo clínico por `ia.py`
  sigue negado por el umbral de capacidad (§2); y el borrador de interpretación y su comité
  (`llm_model`, `llm_verifiers`) siguen con los modelos medidos para esa tarea. Cambiarlos es otra
  decisión.
- **Ningún fichero de la copia cambia:** el modelo lo pone el registro que genera EMMA en su estado
  (`polaris.state_dir()`), no `polaris/tools/peripheries.json`.
