# Fuentes y procedencia: qué usa EMMA y de dónde sale

Inventario rama por rama del árbol de código: qué bibliotecas, datos, APIs, normas y artículos usa
cada parte, de dónde salen (URL, DOI, versión o commit, tal como aparecen en el repo), con qué
licencia y en qué fichero se usan.

**Regla de este documento:** solo se anota lo que el repo declara. Si una cosa se usa y el repo no
dice de dónde sale, se escribe «sin fuente en el repo» en vez de buscarle una cita. Las cifras que
cambian con el código (cuentas de indicadores, métricas) no van aquí: se apunta a su fuente de
verdad, como pide `CLAUDE.md`.

Fuentes transversales que no se repiten en cada rama:

- Dependencias de Python con su versión mínima y licencia comentada: `backend/pyproject.toml`.
- Código de terceros incorporado (Polaris, AGPL-3.0-or-later) y su commit: `NOTICE` y
  `polaris/ADOPTADO.txt`.
- Ficha de SOUP (software de terceros en el sentido de IEC 62304):
  `compliance/software-safety-classification.md`.

## Progreso

| # | Rama | Estado |
|---|------|--------|
| 1 | `backend/app/core/` | hecha (2026-11-14) |
| 2 | `backend/app/ingest/` | hecha (2026-11-14) |
| 3 | `backend/app/environment/` | hecha (2026-11-14) |
| 4 | `backend/app/analysis/` | hecha (2026-11-14) |
| 5 | `backend/app/advisor/` | hecha (2026-11-14) |
| 6 | `backend/app/evidence/` | hecha (2026-11-14) |
| 7 | `backend/app/pain/` (+ `anatomy.py`, `pain_on_skeleton.py`) | hecha (2026-11-14) |
| 8 | `backend/app/imaging/` | hecha (2026-11-14) |
| 9 | `backend/app/volumes/` | hecha (2026-11-14) |
| 10 | `backend/app/reports/` | hecha (2026-11-14) |
| 11 | `backend/app/interpret/` | hecha (2026-11-14) |
| 12 | `backend/app/assistant/` (+ `voice.py`) | hecha (2026-11-14) |
| 13 | `backend/app/polaris/` y `polaris/` | hecha (2026-11-14) |
| 14 | `backend/app/validation/` | hecha (2026-11-14) |
| 15 | `backend/app/api/` (+ `main.py`) | hecha (2026-11-14) |
| 16 | `backend/app/data/` | hecha (2026-11-14) |
| 17 | `backend/app/*.py` (módulos sueltos) | hecha (2026-11-14) |
| 18 | `backend/scripts/` y `backend/spikes/` | hecha (2026-11-14) |
| 19 | `frontend/` | hecha (2026-11-14) |
| 20 | `desktop/` (+ `backend/packaging/`) | hecha (2026-11-14) |
| 21 | `compliance/` (normas citadas) | hecha (2026-11-14) |
| 22 | `marplanner/` y `planner-bridge/` (copia de Marplanner, MIT) | hecha (2026-11-14; añadida al encontrarla en `api/planner.py`) |

---

## 1. `backend/app/core/` — ledger, caché, configuración, salida a internet

### Bibliotecas

| Qué | Para qué | Dónde | Origen / licencia según el repo |
|-----|----------|-------|---------------------------------|
| `pydantic-settings` | Configuración con prefijo `EMMA_` y `backend/.env` | `core/config.py` | `pyproject.toml` (`>=2.6`); **MIT** (2.15.0, metadatos del paquete instalado, leídos el 2026-11-14) |
| `cryptography` | Firma de las entradas del ledger | `core/ledger.py` | `pyproject.toml` (`>=43.0`, «integridad de registros»); **Apache-2.0 OR BSD-3-Clause** (50.0.1, metadatos del paquete instalado, leídos el 2026-11-14) |
| `sqlalchemy` | Almacén *append-only* | `core/storage.py` | `pyproject.toml` (`>=2.0`); **MIT** (2.0.54, metadatos del paquete instalado, leídos el 2026-11-14) |
| `httpx` | Único cliente HTTP, envuelto por la puerta de salida | `core/egress.py` | `pyproject.toml` (`>=0.27`); **BSD-3-Clause** (0.28.1, metadatos del paquete instalado, leídos el 2026-11-14) |
| `astroquery` (vía `requests`) | Excepción declarada de la puerta: la autoriza `egress.authorize` antes de llamar | `core/egress.py` | `pyproject.toml` (`>=0.4.7`, «solo jplhorizons»); se detalla en la rama `environment/` |

### Código de terceros

| Qué | Dónde | Origen |
|-----|-------|--------|
| `polaris/tools/borde.py` (`egress_check`) y `polaris/tools/_net.py` (`with_retries`), sin modificar | `core/egress.py` | Polaris, AGPL-3.0-or-later, © 2026 «Beyond the Protocol»; commit en `polaris/ADOPTADO.txt`; cargados con `app.polaris.load` |
| `tools/salida.py` (aprobación con nonce), adaptado | `core/storage.py` (`sign_draft`) | Polaris, commit `7bf47257f563fa0942a0b73d820191a125be92a2` (`NOTICE`) |
| `tools/decision_alto_riesgo.py` (acta a dos voces), adaptado | `core/storage.py` (`countersign_draft`) | Polaris, mismo commit (`NOTICE`) |

### Normas y referencias técnicas

| Referencia | Qué se toma de ella | Dónde |
|------------|---------------------|-------|
| 21 CFR 11.10(a) y 11.10(e) | Discernir registros alterados (cadena de hashes); audit trail con marca de tiempo (entradas firmadas) | `core/ledger.py`; especificación en `compliance/record-integrity.md` |
| 45 CFR 164.312(c)(1) y (c)(2) | Corroborar la no-alteración (verificación + Merkle) | `core/ledger.py` |
| 45 CFR 164.526 | Derecho de rectificación: redactar sin romper la cadena | `core/ledger.py`, `core/storage.py` |
| RFC 6962 (§2.1) | Árbol de Merkle `rfc6962-sha256`: hoja SHA-256(0x00‖hash), raíz MTH, MTH({}) | `core/ledger.py:812-845` |
| CVE-2012-2459 | El fallo de duplicar el nodo impar, que una revisión adversaria (2026-09-21) encontró en la versión anterior | `core/ledger.py` (cabecera) |
| RFC 8785 (JCS) | **No se usa**: se nombra como lo que haría falta para interoperar con otro lenguaje | `core/ledger.py:178` |
| ISO 8601 | Hora de modificación en UTC | `core/egress.py:147` |
| ISO 27789 | Qué debe decir una lápida (qué se quitó, por qué y a petición de quién) | `core/storage.py:702` |
| NASA-STD-3001 Vol 2, Apéndice F.5.6 | Decimales por indicador; coma decimal y espacio fino como desviaciones declaradas | `core/display.py`; desviaciones en `compliance/hmi-state-of-the-art.md` §2.3 |

### Documentos internos que sostienen decisiones de esta rama

| Documento | Qué sostiene |
|-----------|--------------|
| `compliance/record-integrity.md` | Es la especificación de `core/ledger.py` (incluye §3.29, asiento `simulated-link`) |
| `docs/contexto/especificacion-tecnica-v1.1.md` §3, §6, §10, §12 | `MissionContext` y fases (`core/mission.py`); logs sin contenido personal (`core/log_privacy.py`) |
| `docs/contexto/conversacion-ideacion-v1.md` (L182, L190, L510) | Notas de Tierra a bordo (`core/ground_notes.py`) |
| `docs/contexto/prioridades-evento.md` (idea 10) | Enlace simulado con Tierra (`core/link_sync.py`) |

### Sin fuente en el repo

- Los límites de fase de misión (adaptación / estable) son parámetros de diseño de EMMA, no cifras
  citadas; el propio `core/mission.py` lo declara.
- `http://127.0.0.1:11434` en la configuración es el Ollama local (el «cerebro» de Polaris); se
  detalla en la rama `interpret/`.

---

## 2. `backend/app/ingest/` — catálogo de códigos, FHIR, simulador, wearables, PVT

### Terminologías y estándares de datos

| Qué | Para qué | Dónde | Origen según el repo |
|-----|----------|-------|----------------------|
| LOINC (`http://loinc.org`) | Código de cada indicador que tiene uno verificado (invariante 1) | `ingest/codes.py` | Cada código se buscó en `tx.fhir.org` (`https://tx.fhir.org/r4/CodeSystem/$lookup`), LOINC 2.82 y 2.83, con fecha de búsqueda anotada junto al código (`codes.py:40-47`, `:1094`). El reparto vigente lo da `/api/indicators` |
| Sistema propio `https://emma.mission/codes` | Indicadores sin código estándar; cada uno declara por qué | `ingest/codes.py:276` | Propio de EMMA |
| `https://halo.mission/codes` y `https://halo.mission/fhir/` | Sistema de códigos y extensiones heredados | `codes.py:280`, `fhir.py:193` | **Resuelto el 2026-11-14:** es el nombre anterior del proyecto, HALO. Se renombró a EMMA el 2026-11-02 (commit `29aa2a1c`, «Renombra a EMMA los identificadores firmados y sigue leyendo los de HALO»). Lo firmado antes conserva `halo.mission` y se sigue leyendo (`FORMER_CODE_SYSTEMS`, `codes.py:279-283`) |
| HL7 FHIR R4 `Observation` y perfil de constantes vitales (`https://hl7.org/fhir/R4/observation-vitalsigns.html`) | Modelo canónico de toda observación | `ingest/fhir.py`, `codes.py:7` | Biblioteca `fhir.resources>=7.1` (`pyproject.toml`) |
| Categorías `http://terminology.hl7.org/CodeSystem/observation-category` | `Observation.category`; seis aproximaciones declaradas | `fhir.py:42`, `ingest/category_fit.py` | Corrección en §5.38.9 y §5.39.19 (rondas de revisión del repo) |
| UCUM (`http://unitsofmeasure.org`) | Unidades | `fhir.py:38` | — |
| Extensiones `https://emma.mission/fhir/{context,confidence,observation-type,evidence-context,model-version}` | Contexto, confianza, tipo y versión del modelo en la observación | `fhir.py:187-196` | Propias de EMMA |
| Bluetooth SIG, característica Heart Rate Measurement (UUID 0x2A37, perfil GATT) | Trama BLE: pulso e intervalos R-R en 1/1024 s | `ingest/wearable.py` | **Resuelto el 2026-11-14:** Bluetooth SIG, *Heart Rate Service 1.0* (V10r00, 2011-07-12, MED WG), `https://www.bluetooth.com/specifications/specs/heart-rate-service-1-0/`, con la errata obligatoria 23224. Su §3.1.1.1 da el bit 0 (UINT8/UINT16) y su §3.1.1.4 el bit 4 (intervalos R-R). La resolución de los R-R, **resuelta el 2026-11-14**: *GATT Specification Supplement* (versión del 2026-09-09), §3.126.2: «Each RR-Interval value is represented by a uint16 with 1/1024 second as the unit». §3.126.1 (tabla 3.216) da los bits 0-4 tal como los describe `wearable.py`. PDF: `https://btprodspecificationrefs.blob.core.windows.net/gatt-specification-supplement/GATT_Specification_Supplement.pdf` |
| Exportaciones de Apple Health (XML) y Google Fit (JSON) | Ingesta de wearables | `ingest/wearable.py` | **Google Fit, resuelto el 2026-11-14:** `com.google.heart_rate.bpm` («the user's heart rate in beats per minute», `https://developers.google.com/fit/datatypes/health`). **Hallazgo:** «The Google Fit APIs, including the Google Fit REST API, will be deprecated in 2026» (`https://developers.google.com/fit`). EMMA lee un fichero exportado, no la API, pero la fuente de esos ficheros está en retirada; Google recomienda Health Connect. **Apple Health, resuelto en parte el 2026-11-14:**
  - La exportación existe y es XML («export all of your health and fitness data from Health in XML format», `https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios`).
  - El tipo de pulso está documentado: «A quantity sample type that measures the user's heart rate», en unidades count/time (`https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/heartrate`).
  - **Apple no publica un esquema del fichero exportado**: no se encontró en developer.apple.com ni en support.apple.com. El parser de EMMA se apoya en la forma del fichero, no en una especificación |
| Health Connect (Android), el sucesor de Google Fit | **No disponible: EMMA no lo lee.** No hay ruta `/api/import/health-connect` ni fuente `health-connect` en `ingest/bindings.py` | — | **Investigado el 2026-11-15 (lote «ciclo», unidad B2); no se implementa porque no hay formato documentado que leer.** Se leyó lo siguiente:<br>• **Health Connect es una API dentro del teléfono para apps Android.** Guía (`https://developer.android.com/health-and-fitness/guides/health-connect`): «The platform provides standard insert, update, and delete functions for recorded data. Health Connect also includes functionality that allows client apps to synchronize data out of Health Connect». Esa sincronización (`https://developer.android.com/health-and-fitness/health-connect/sync-data`) son llamadas Kotlin (`getChangesToken`, `getChanges`) de una app instalada, que además solo lee en primer plano salvo permiso de fondo («Apps can only read data from Health Connect while they are in the foreground»). Ninguna de las dos páginas habla de exportar un fichero.<br>• **El usuario puede exportar sus datos, pero el formato no está documentado.** Ayuda de Android (`https://support.google.com/android/answer/15323271`): «Your Health Connect data is bundled in a zip file and saved to a cloud storage provider of your choice», «By default, the file is named "Health Connect.zip."», «To use this feature, you need an Android device with version 14 and up» y «Export and import of health records isn't supported at this time». La página no da el formato ni el esquema de lo que hay dentro del zip, y no enlaza ninguna documentación sobre ello. Tampoco se encontró en developer.android.com. Ese zip está pensado para volver a importarlo en Health Connect, no para que lo lea otro programa. Leerlo sería adivinar su forma y, si Google la cambia, el parser mentiría sin avisar. No se inventa (mismo criterio que la invariante 1).<br>• **Los tipos de registro sí están documentados**, pero solo como clases de la API. En la tabla de tipos (`https://developer.android.com/health-and-fitness/health-connect/data-types`), la categoría «Cycle Tracking» incluye `MenstruationFlowRecord`, `MenstruationPeriodRecord`, `IntermenstrualBleedingRecord`, `OvulationTestRecord`, `BasalBodyTemperatureRecord`, `CervicalMucusRecord` y `SexualActivityRecord`. **No hay ningún tipo de registro de anticoncepción.** La referencia de `MenstruationFlowRecord` (`https://developer.android.com/reference/kotlin/androidx/health/connect/client/records/MenstruationFlowRecord`) da `FLOW_UNKNOWN = 0`, `FLOW_LIGHT = 1`, `FLOW_MEDIUM = 2` y `FLOW_HEAVY = 3`. Ojo: el 0 de Health Connect es «desconocido», no el 0 «sin flujo» de EMMA; quien traduzca debe rechazarlo, no copiarlo.<br>**Qué haría falta:** una app Android compañera, fuera de este repo, que pida los permisos de lectura (`READ_MENSTRUATION`, `READ_OVULATION_TEST`, `READ_BASAL_BODY_TEMPERATURE`…), lea los registros con la API y los escriba como FHIR R4 `Observation` o como un JSON con esquema propio y declarado, preferiblemente firmado. EMMA lo leería por una ruta de importación que acabe en el ledger (invariante 4), sin salir a internet. Hasta entonces, desde Android solo entra por un formato que EMMA ya lea |

### Datos reales

| Datos | Uso | Dónde | Origen / cita |
|-------|-----|-------|---------------|
| Inspiration4: hemograma de los 4 tripulantes civiles (NASA OSDR, estudio **OSD-569**, fichero `LSDS-7 CBC TRANSFORMED`) | Se reproducen en la línea de tiempo, firmados como simulados. Una fila incoherente (C003, L-92) se excluye y se declara | `ingest/inspiration4.py`; fichero en `app/data/osdr/OSD-569_LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv` | `https://osdr.nasa.gov/bio/repo/data/studies/OSD-569`. Cita que pide OSDR: «Data are courtesy of the NASA Open Science Data Repository (https://osdr.nasa.gov/bio/repo)» |
| Nombres en español de los analitos | Frases de la tripulación | `ingest/names_es.py`, leídos de `app/data/lab_loinc.json` | Diccionario `ANALITOS` de Polaris (`polaris/tools/biomarcadores.py`). El resto de nombres los redacta EMMA. Ninguno es traducción de LOINC |

### Instrumentos y protocolos

| Qué | Dónde | Fuente según el repo |
|-----|-------|----------------------|
| PVT (Reaction Self-Test de la ISS): lapso > 500 ms y salida falsa < 100 ms | `ingest/pvt.py` | `app/data/instruments_read.json` (leído el 2026-10-13). Discrepancia declarada: la fuente dice ≥ 500 ms y EMMA usa > 500; no se cambió (invariante 5). La comparación la sirve `GET /api/pvt/protocol` |
| Batería NASA Cognition (sus 9 pruebas sin la PVT, como 17 indicadores descriptivos) | `ingest/cognition.py`, `codes.COGNITION_CODES` | Basner et al. 2015 («15 unique forms of 10 neuropsychological tests»). Dev et al. 2024, Tabla 1 (25 astronautas): **no** se adopta como rango. EMMA no pasa ni puntúa las pruebas |
| Valoración de alimentos por plato | `ingest/food_item.py` | `instruments_read.json` (`hedonic-anchors-crew`); NASA-STD-3001 `v2-7002-acceptable-6`; ficha `hrp-food-system-evidence-report`. Texto libre porque ninguna fuente leída da un vocabulario cerrado |
| Coste de medir cada indicador | `ingest/cost.py` | Base de conocimiento §9; reglas con su `basis` en `app/data/measurement_cost.json`. El tiempo solo lleva cifra si tiene fuente |
| Vaina del nervio óptico y yugular, sin umbral poblacional | `codes.py:903-909` | Crit Care Med 2025, PMID 40459386; Marshall-Goebel 2019 (sin DOI en el repo) |

### Simulador fisiológico (`ingest/simulator.py`)

Cada parámetro de deriva declara una clase de evidencia (`established`, `direction_only`,
`contested`, `unsupported` o `design`), una fuente y las fichas que cita. Las fichas se resuelven en
`app/data/evidence_refs.json`, que se documenta en la rama `data/`. Una prueba comprueba que cada
ficha citada existe y que un `contested` nombra los dos lados. Esto se expone en `/api/status` →
`simulation.evidence`.

| Parámetro | Clase | Fuente declarada (resumen) | Fichas |
|-----------|-------|----------------------------|--------|
| `bmd_loss_pct_per_month` | established | NASA-STD-3001 [V1 4027] | — |
| `iss_sleep_hours_actual` | established | Barger LK et al., Lancet Neurol 2014 (PMID 25127232): 6,09 h en vuelo en la ISS. **Enlazado el 2026-11-14**; antes decía «literatura de sueño» sin cita | `barger-2014-sleep-spaceflight` |
| `pvt_lapse_threshold_ms` | established | Basner y Dinges, Sleep 2011 (PMID 21532951), Tabla 3: «Response times ≥ 500 ms». **Enlazado el 2026-11-14**; EMMA cuenta > 500, discrepancia ya declarada | `basner-2011-pvt-metrics` |
| `iss_daily_dose_msv` | established | Dosimetría DosTel vía OSDR RadLab (0,27 mSv/24 h del 2022-04-01 con Q = 1; ver la mina de Q en `CLAUDE.md`) | — |
| `career_dose_limit_msv` | established | NASA-STD-3001 Vol 1 Rev C [V1 4030], Appendix D | — |
| `orthostatic_drop_growth_per_week` | direction_only | Intolerancia ortostática postvuelo (sin cita concreta) | — |
| `circadian_drift_h_per_week` | direction_only | Cortisol que no se sincroniza con días de 23,6 h (sin cita concreta) | — |
| `ntx_rise_per_week` | direction_only | Smith 2005 (Mir), Smith 2012 (ISS), Zwart 2018 | `smith-2005-bone-markers-mir`, `smith-2012-bone-resistance-iss`, `zwart-2018-dietary-acid-load` |
| `co2_symptom_burden_rise` | direction_only | Law J. et al. J Occup Environ Med 2014;56(5):477-83, PMID 24806559 | — |
| `dehydration_urine_drop_ml_per_week` | direction_only | NASA, *The Human Body in Space* | — |
| `menu_fatigue_acceptability_drop_per_week` | unsupported | Sin respaldo en lo leído | `meiselman-2000-variety-monotony`, `douglas-2025-iss-food-acceptability`, `ntrs-20220014371` |
| `resting_hr_drift_bpm_per_week` | contested (valor 0) | Hughson 2012, Xu 2013, Fraser 2012, Baevsky 2007 (sin cambio) frente a Baevsky 1997 (sube); Otsuka 2022 | `hughson-2012-…`, `xu-2013-…`, `fraser-2012-…`, `baevsky-2007-…`, `baevsky-1997-…`, `otsuka-2022-…` |
| `co2_pvt_rt_rise_ms` | contested | Scully 2019 frente a Satish 2012 y Manzey 1998 | `scully-2019`, `satish-2012-…`, `manzey-1998-…` |
| `co2_sleep_efficiency_drop_pct` | contested | Van Hoy 2026 frente a Gundel 1998 y Christian 2024; Law 2014 | `van-hoy-2026-…`, `gundel-1998-…`, `christian-2024-…`, `law-2014` |
| `hrv_sdnn_decline_ms_per_week` | contested | Xu 2013 frente a Otsuka 2016; Otsuka 2022 | `xu-2013-…`, `otsuka-2016-…`, `otsuka-2022-…` |
| `hrv_rmssd_decline_ms_per_week` | contested | Xu 2013 y Hughson 2012 frente a Baevsky 2007 | ídem |
| `systolic_bp_decline_mmhg_per_week` / `diastolic_…` | contested | Norsk 2015 y Baevsky 2007 frente a Hughson 2012 | `norsk-2015-…`, `baevsky-2007-…`, `hughson-2012-…` |
| `cortisol_rise_per_week` | contested (valor 0) | Vorobiev 1995 frente a Buchheim 2019; Mehta 2017 y Agha 2020 no dan el sentido | `vorobiev-1995-…`, `buchheim-2019-…`, `mehta-2017-…`, `agha-2020-…` |

Además hay **36 parámetros `design`**: valores de diseño de EMMA que llevan la fuente literal
«Diseño de EMMA: sin fuente escrita en el repositorio» (`simulator.py:171`).

### Simulador de cabina (`ingest/habitat_simulator.py`)

Los valores nominales son de diseño y quedan dentro de los límites de NASA-STD-3001 Vol 2:
- ppCO₂ 2,0 mmHg [V2 6004].
- ppO₂ 150 mmHg [V2 6003]; los límites de exposición están en la tabla 6.2-1.
- Presión 101,3 kPa [V2 6006].
- Temperatura y humedad [V2 6013].
- Ruido [V2 6077].
- CO, amoniaco y formaldehído: SMAC de **JSC 20584 Rev C**.

**Luz 300 lx: diseño sin fuente**, solo se muestra. No hay telemetría pública de cabina de la ISS.

### Bibliotecas

`numpy` (simuladores), `fhir.resources` (modelo FHIR) y la biblioteca estándar (`csv`, `statistics`,
`unicodedata`). Versiones en `pyproject.toml`.

### Sin fuente en el repo

- Los 36 parámetros `design` del simulador fisiológico y la luz de cabina.
- ~~El origen del sistema `halo.mission`~~ **Resuelto el 2026-11-14**: es el nombre anterior del proyecto (HALO, renombrado el 2026-11-02).
- ~~Bluetooth SIG y Google Fit~~ **Resueltos el 2026-11-14** (ver la tabla). Después se resolvieron también la resolución de 1/1024 s (GSS §3.126.2) y lo que Apple documenta de su exportación. Sigue sin fuente el esquema del XML de Apple, porque Apple no lo publica.
- `bindings.py` y `location_anchors.py` no citan fuentes externas. Se apoyan en la especificación
  del equipo §3 y en decisiones del usuario (2026-10-09).

---

## 3. `backend/app/environment/` — efemérides, meteorología espacial, dosimetría, hábitat

Todas las salidas a la red pasan por `core/egress.py` (invariante 3 bis). Los hallazgos de cada
API (formatos, trampas) están en `backend/spikes/HALLAZGOS.md`.

### APIs y servicios externos

| Servicio | Qué da | Dónde | URL / notas según el repo |
|----------|--------|-------|---------------------------|
| **JPL Horizons** (vía `astroquery.jplhorizons`, único uso de astroquery) | Tiempo de luz, distancia, elongación solar (cantidad 23, «S-O-T») | `environment/ephemeris.py`, `conjunction.py`, precarga en `scripts/preload_ephemeris.py` | `https://ssd.jpl.nasa.gov/api/horizons.api`. Horizons no devuelve tabla si `start == stop` (spike) |
| **NAIF SPICE** (`spiceypy`, extra `[spice]`; MIT, incluye CSPICE) | Mismo cálculo en local y sin red; Horizons queda de contraste y respaldo (decisión del usuario, 2026-11-11) | `environment/spice.py`, `comms_status.py`, `ephemeris_coverage.py` | Núcleos `naif0012.tls` (LSK) y `de432s.bsp` (SPK) en `https://naif.jpl.nasa.gov/pub/naif/generic_kernels/…`, descargados por `scripts/fetch_spice_kernels.py`. Peor diferencia con Horizons: 0,003 ms en 181 días (`HALLAZGOS.md` §10). **Licencia de los núcleos:** `https://naif.jpl.nasa.gov/naif/rules.html` (leída 2026-11-11), redistribución permitida si no se modifican; la página no dice «dominio público». Declarado en `NOTICE` |
| **NASA DONKI** (api.nasa.gov) | Eventos SEP, CME y fulguraciones, con `linkedEvents` y `sentNotifications` | `environment/donki.py` | `https://api.nasa.gov/DONKI`, `DEMO_KEY` (30 peticiones/h). Instantánea fechada `app/data/donki_snapshot.json` de `scripts/fetch_donki_snapshot.py`. Licencia declarada en el código: obra del Gobierno de EE. UU., 17 U.S.C. §105, directrices de `https://www.nasa.gov/nasa-brand-center/images-and-media/` |
| **CCMC iSWA por HAPI** (NASA Goddard) | Flujo de protones GOES ≥10 MeV (canal P10 de `goesp_part_flux_P5M`) y viento solar (`swpc_rtsw_plasma_P1M`) | `environment/iswa.py` | `https://iswa.gsfc.nasa.gov/IswaSystemWebApp/hapi`. **El dato es de NOAA (GOES y RTSW)**, servido por NASA. Escalas NOAA: `https://www.swpc.noaa.gov/noaa-scales-explanation`. Spike del 2026-11-11, `HALLAZGOS.md` §6. Solo se muestra |
| **SSCweb** (Satellite Situation Center, NASA Goddard) | Posición de la ISS | `environment/orbit.py` | `https://sscweb.gsfc.nasa.gov/WS/sscr/2`, REST sin clave (`HALLAZGOS.md` §6). Solo con el perfil `leo`. Descriptivo |
| **OSDR RadLab** | Tasa de dosis absorbida medida en vuelo (DosTel, etc.) | `environment/radlab.py` | `https://visualization.osdr.nasa.gov/radlab/api/`. Hallazgos: el rango temporal es obligatorio (435 MB sin él) y el parámetro `fields ` lleva espacio final. `dose_equivalent_rate` está vacío en 98 688 filas (2011-2022, diez instrumentos) |

### Referencias científicas y técnicas

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| Contorno SAA de NICER: HEASARC CALDB `nixtisaareg20170601v003.fits` (`https://heasarc.gsfc.nasa.gov/FTP/caldb/data/nicer/xti/bcf/saa/…`); ayuda `niprefilter2` | Saber si la ISS pasa por la Anomalía del Atlántico Sur. Leído el 2026-11-11, con sus límites declarados: es un contorno de fondo de detector, no de dosis | `orbit.py` (`SAA_REGION`) |
| NASA «Ask an Astrophysicist» 961004 (1996), `https://imagine.gsfc.nasa.gov/ask_astro/earth.html` | La caja SAA anterior. **Sustituida**; solo consta | `orbit.py` (`superseded`) |
| ICRP 60 | Factor de calidad Q en función de la LET | `environment/dosimetry.py` |
| Badhwar 1992, TEPC en Spacelab SLS-1 (STS-40), ficha `badhwar-1992-sls1-tepc` (leída en PubMed el 2026-10-21) | Q global de misión = 2,38 cuando no hay dosis equivalente medida (ver la mina de Q en `CLAUDE.md`) | `dosimetry.py:106-113` |
| NASA-STD-3001 [V1 4030] | Dosis efectiva con el modelo NASA Q. **No implementable**: RadLab no da el espectro de LET, y está medido | `dosimetry.py` |
| Nota de JPL de 2015 sobre la conjunción solar de Marte («within two degrees of Mars») | Umbral de 2° para decir que hay conjunción. Solo vale para Marte y no entra en el riesgo | `conjunction.py` (dos fichas del registro de evidencia) |
| Manual de Horizons, cantidad 23 | Elongación solar | `ephemeris.py`, `spice.py` |

### Límites del hábitat (`environment/habitat.py`)

| Documento | Qué se toma | Ficha / leído |
|-----------|-------------|---------------|
| NASA-STD-3001 Vol 2 Rev F: [V2 6003], [V2 6004], [V2 6006], [V2 6012], [V2 6013], [V2 6077], [V2 6078], [V2 6080], [V2 8051], [V2 8055], [V2 8057] | Límites de atmósfera, presión, temperatura, humedad, ruido e iluminación | — |
| NASA-STD-3001 Vol 2 Rev F: [V2 6026], [V2 6059], [V2 7081] | Agua, aire y superficies «microbiologically safe». **Sin cifra**: se muestran sin límite | — |
| [V2 6046] | Aviso de calidad del agua. EMMA no es ese sistema y no avisa | — |
| Technical Brief **OCHMO-TB-002 Rev B**, ECLSS (2023-11-14) | Catálogo de límites de cabina y partición de sistemas (`systems.py`) | `ochmo-tb-002`, leído el 2026-10-21 |
| Technical Brief **OCHMO-TB-035 Rev C**, Acoustics (2023-10-06) | Límite de ruido [V2 6077] | `ochmo-tb-035`, leído el 2026-10-31 |
| **JSC 20584 Rev C** (2024-06-13), SMAC | Límites de exposición a contaminantes del aire | `habitat.py:23` |
| **JSC 63414 Rev A** (SWEG, nov. 2023) | Carbono orgánico total (p. 14) y plata (p. 13), en sus cuatro tiempos de consumo; solo se muestran | `jsc-63414-rev-a`, leído el 2026-10-22 |
| Control térmico de la ISS (ATCS) | Base del vocabulario de sistemas | Ficha en `basis_refs` de `app/data/habitat_systems.json` |

### Datos que viajan con el paquete

- `app/data/donki_snapshot.json`: respuesta real de DONKI con su URL, fecha y licencia.
- `app/data/habitat_systems.json`: vocabulario de sistemas. Es diseño de EMMA, rotulado como tal,
  con `basis_refs`.
- `app/data/habitat_modules.json`: módulos del hábitat (se detalla en la rama `data/`).
- Núcleos SPICE, empaquetados por `packaging/freeze.py` tras comprobar su huella.

### Bibliotecas

`astroquery` (vía `requests`), `spiceypy` (opcional), `httpx` (por `egress`). Versiones en
`pyproject.toml`.

### Sin fuente en el repo

- `FRESH_FOR` de DONKI (15 min) y de RadLab (6 h), y `MAX_WINDOW_DAYS = 30`: parámetros de diseño.
- La luz de cabina sigue sin límite verificado (`DISPLAY_ONLY`).
- El estado de los sistemas no es telemetría: lo declara una persona (`systems.py`).

---

## 4. `backend/app/analysis/` — línea base, tendencia, riesgo y capas descriptivas

Esta rama no sale a la red y casi no usa bibliotecas externas: la biblioteca estándar
(`statistics`, `bisect`, `itertools`). Sus «fuentes» son sobre todo **métodos estadísticos**,
**normas** y **la validación propia**. La justificación clínica de conjunto está en
`compliance/clinical-decision-rationale.md`, y las cifras de validación vigentes en
`compliance/external-validation.md` y en los tests `-m external` (invariante 5).

### Métodos estadísticos

| Método | Dónde | Respaldo según el repo |
|--------|-------|------------------------|
| Línea base personal robusta: mediana y MAD, con `MAD_TO_SD = 1.4826` | `analysis/baseline.py:76-78` | Constante de consistencia bajo normalidad. **Resuelto el 2026-11-14:** es 1/Φ⁻¹(3/4) = 1,4826, comprobado con `statistics.NormalDist`; es una definición, no un parámetro de diseño. Referencia: Rousseeuw PJ, Croux C, *Alternatives to the Median Absolute Deviation*, J Am Stat Assoc 1993;88(424):1273-1283, doi:10.1080/01621459.1993.10476408 (comprobado en Crossref) |
| Cuantiles empíricos de \|z\| en lugar de sigmas | `baseline.py` (desde la línea ~110) | **Validación propia** con MMASH: \|z\| ≥ 2 se excedía en el 22,02 % de las lecturas, frente al 4,55 % teórico. Ver `compliance/external-validation.md` |
| `MIN_SAMPLES = 100`, acoplado al cuantil 99 | `baseline.py` | Medido: 213 de 220 falsas alarmas usaban bases de menos de 100 muestras. Lo vigila la prueba `test_established_matches_the_weakest_claim` |
| Ventana móvil de 14 días con 12 h de hueco; suelo de dispersión del 1 % | `baseline.py` | Diseño de EMMA, motivado en el comentario; sin fuente bibliográfica |
| Tendencia: recta por mínimos cuadrados contrastada con su error típico; proyección a 4 semanas rotulada PREDICHA | `analysis/trend.py`, `forecast_check.py` | Método estándar; sin cita en el repo |
| Episodio cerrado frente a deriva en curso | `analysis/episode.py` | §5.38.6 (medido, sin adoptar), escenario `transient-sleep-loss` |

### Riesgo

| Parámetro | Dónde | Respaldo |
|-----------|-------|----------|
| Factor de aislamiento: hasta ×1,35, saturado a 40 min de ida y vuelta | `analysis/risk.py:67`, `:321-331` | **Diseño de EMMA, sin fuente en el repo.** El retardo sale de `environment/` |
| `_TREND_POINTS = 20` | `risk.py` | Medido sobre los escenarios: consta en el comentario |

### Normas

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| NASA-STD-3001 Vol 1 Rev C [V1 4030] | Límite de carrera de 600 mSv | `analysis/radiation.py`, `baseline_profile.py` |
| [V1 4020], [V1 4026], [V1 4027] | Perfil del tripulante y densidad ósea (95 % de la DMO previa) | `baseline_profile.py`, `densitometry.py` |
| NASA-STD-3001 Vol 2 Rev F [V2 6003], [V2 6006], [V2 6012], [V2 6077] | Contexto de cabina junto a una alerta | `analysis/context.py` |
| [V2 7002] («6.0 or better»), leída en el PDF oficial | Criterio de aceptabilidad de la comida. Se marca sobre el alimento, no sobre la persona | `analysis/food_acceptability.py`; frase en `app/data/instruments_read.json` (`v2-7002-acceptable-6`) |
| Vol 2, Apéndice F.4.3.1 c («There must be an indication when data are stale») | Exige indicar que un dato está caducado | `analysis/staleness.py`. **Los tres plazos (efemérides, meteorología espacial, dosimetría) son diseño de EMMA, sin fuente**, y cada respuesta lo declara |
| OCHMO-MTB-013 Rev D, p. 19 («no system to date measures bone density in-flight») | Por qué la densidad ósea en vuelo es inferida | `analysis/densitometry.py` |

### Artículos y documentos de NASA

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| NASA, *The Human Body in Space* | Pérdida ósea de 1-1,5 %/mes sin contramedidas (banda inferida) | `analysis/inferred.py`; ficha en `evidence/registry.py` |
| Law et al. 2014 | CO₂ y cefalea | `analysis/context.py:138` |
| Scully et al. 2019 | El efecto del CO₂ sobre la cognición es contestado | `analysis/context.py:140` |
| Badhwar 1992 (TEPC SLS-1), ficha `badhwar-1992-sls1-tepc` | Q por tipo de radiación | `analysis/radiation.py` |
| Fichas `nasa-orion-radiation-protection`, `nasa-artemis1-radiation-research`, `nasa-artemis2-eyes-on-sun` | HERA (instrumento de Orion) y el refugio: hasta 1 h para montarlo y hasta 24 h dentro | `analysis/radiation.py` |
| Inspiration4, OSD-569 (L-92, L-44, L-3, R+1, R+45, R+82) | Trayectoria de recuperación posvuelo | `analysis/recovery.py` |
| `compliance/location-sensing-feasibility.md`, `app/data/location_sensing.json` (REALM-1, DLR Wireless Compose) | Ubicación por anclas de la nave | `analysis/location.py` |

En `compliance/clinical-decision-rationale.md` hay citas con PMID que justifican decisiones del
motor:
- Marshall-Goebel et al., JAMA Netw Open 2019, PMID 31722025.
- Crit Care Med 2025, PMID 40459386.
- Kerstman et al., Aviat Space Environ Med 2012, PMID 22272509.
- Serlin et al., Pain 1995 (el corte de 7-10 para «intenso»).
- Hamilton et al. 2004, PMID 15018297.
- Krihak et al., *Medical Data Architecture Prototype*.

Su lectura detallada va en las ramas `evidence/` y `pain/`.

### Documentos del equipo

Especificación v1.1 §2, §3, §9 y §10, y la conversación de ideación. Piden la confianza visible, el
perfil de base, los estados inferidos, el ciclo predicción → validación y el tiempo hasta la acción.

### Sin fuente en el repo

- El factor de aislamiento (×1,35, saturado a 40 min).
- ~~La constante 1,4826~~ **Resuelto el 2026-11-14** (Rousseeuw y Croux 1993; ver la tabla).
- La ventana de 14 días y el hueco de 12 h.
- Los plazos de caducidad de `staleness.py`.
- La semana de `exercise_summary.py`, declarada parámetro de diseño.

---

## 5. `backend/app/advisor/` — recomendaciones y contramedidas

Sin bibliotecas externas ni red. Las recomendaciones son **datos con fuente**, no frases.
- `app/data/countermeasures.json`: la biblioteca de 40 contramedidas.
- `app/data/countermeasure_effects.json`: dónde cae cada efecto. Va fuera de la huella de reglas.
- `app/data/resources.json`: el vocabulario cerrado de recursos.

Cada `protocol_ref` es una ficha del registro de evidencia (rama `evidence/`). Por qué el sistema
no prescribe (invariante 7, IEC 62304 Clase B): `compliance/software-safety-classification.md`.

### Contramedidas con respaldo (`evidence-backed`: 12 de 40)

| Contramedida | Ficha (`protocol_ref`) | Tiempo de tripulación: base declarada |
|--------------|------------------------|---------------------------------------|
| `cv-exercise-session` | `csa-physical-activity` (Agencia Espacial Canadiense) | Frase de la CSA sobre el ejercicio diario |
| `bh-protect-sleep` | `ochmo-mtb-009` (ritmo circadiano) | OCHMO-MTB-009 p. 4: «1-2 hrs before bedtime: avoid…» |
| `bh-circadian-lighting` | `ochmo-mtb-009` | OCHMO-MTB-009 p. 4: dice cuándo, no cuánto |
| `bh-repeat-pvt` | `hrr-task-1651-pvt` (Human Research Roadmap) | La duración sale del artículo que validó la prueba breve, no de la tarea del Roadmap |
| `rad-storm-shelter` | `nasa-orion-radiation-protection` | NASA sobre Orion: refugio en una hora |
| `rad-shielded-module` | `nasa-orion-radiation-protection` | Sin fuente: buscada el 2026-11-14, no encontrada (ver abajo) |
| `bone-resistive-load` | `ochmo-tb-031` (ejercicio) | OCHMO-TB-031 p. 10, «Inflight Training Time Prescriptions», adaptado de Loehr et al. 2015 |
| `bone-calcium-vitd` | `ochmo-mtb-013` (hueso) | Sin fuente (OCHMO-MTB-013 Rev D no da el tiempo): buscada el 2026-11-14, no encontrada (ver abajo) |
| `gu-hydration-target` | `nasa-human-body-in-space` | Sin fuente: buscada el 2026-11-14, no encontrada (ver abajo) |
| `nut-menu-variety` | `hrp-food-system-evidence-report` | Sin fuente: buscada el 2026-11-14, no encontrada (ver abajo) |
| `hab-co2-sensor-crosscheck` | `ochmo-tb-002` ([V2 6022], [V2 6004]) | Sin fuente: buscada el 2026-11-14, no encontrada (ver abajo) |
| `hab-co2-removal-check` | `ochmo-tb-002` ([V2 6004]: 3 mmHg en media de 1 h) | Sin fuente: buscada el 2026-11-14, no encontrada (ver abajo) |

Las **28 restantes son `demo`**: se apoyan solo en el riesgo del dominio, sin protocolo concreto.
Son las contramedidas de inmunidad, neuro-ocular (SANS), genitourinario, musculoesquelético y la
mayoría de las de cabina.

**Tiempo de tripulación:** 33 de 40 entradas lo dejan en `null` («sin fuente», buscada el 2026-11-14 y no encontrada). La regla de la
carga es que una cifra sin fuente no se escribe.

**Búsqueda del tiempo de tripulación de las 33 contramedidas sin cifra (2026-11-14).** Se buscó en
nasa.gov, ntrs.nasa.gov, esa.int y PubMed (E-utilities), en cuatro grupos. **Ninguna fuente da un
tiempo que corresponda a la acción tal como EMMA la describe, así que las 33 siguen en `null`.** No se
toca `countermeasures.json` ni cambia `rules_version`. Lo encontrado, y por qué no se aplica:

| Contramedida | Lo más cercano encontrado | Por qué no se aplica |
|---|---|---|
| `sans-repeat-both-eyes` | NTRS 20150003006 (presentación de NASA sobre VIIP), diapositiva 20: «Ocular Ultrasound, Vascular Compliance, & Transcranial Doppler – 250 min/session» | Es una sesión de protocolo completa (ecografía ocular, cardiaca, ECG, Doppler), no la repetición de la vaina del nervio óptico. No se comprobó si es en vuelo |
| `gu-void-repeat` | Estudio en Tierra en J Nurs Res 2005;13(3):216-24, PMID 16237633, doi:10.1097/01.jnr.0000387543.68383.a0: «The BladderScan averaged 45 seconds (range=17-119 seconds)» | Es un escáner vesical automático; EMMA mide con ecografía y tres diámetros a mano. Además solo cubre la exploración, no el intento de micción |
| `bh-social-contact` | NASA, *Living in Space: Family Video Conference* (`https://www.nasa.gov/video-detail/living-in-space-family-holiday-video-conference/`, grabado el 26-feb-2023, leído el 2026-11-14): «Family video conferences are conducted on a weekly basis and on Holidays and special events» | Da la frecuencia, no la duración: la única duración de la página (1:05) es la del vídeo |
| `hab-noise-sensor-crosscheck` | Limardo et al., Inter-Noise 2021, NTRS 20210016305: dosímetro llevado «for a continuous 24-hour period»; despliegue de área «approximately 16-18 hours»; la medida con sonómetro, solo «brief» | Son tiempos de exposición o despliegue, no de tripulación. El propio texto dice que el procedimiento se optimizó para ahorrar tiempo de tripulación, sin dar la cifra |
| `bh-circadian-lighting` | Lockley y Brainard, *Lighting Effects*, NASA 2016, NTRS 20160006727: los tres modos de luz (pre-sueño 2700 K, ≤50 lux) | No da cuánto tiempo. Una cifra de «2 horas» que dio un resumen de búsqueda **no está en el PDF** (comprobado). La contramedida sigue con OCHMO-MTB-009 («1-2 hrs before bedtime»), que dice cuándo, no cuánto |
| Registros (`nut-log-intake`, diarios, ingesta, orina, dosímetro) | ESA, *Diet tracker in space* (2017): la app de ingesta de la ISS ayudó «without taking up more time» | Sin minutos. En PubMed no hay ningún estudio publicado del rastreador de ingesta de la ISS (FIT) con tiempos |
| Radiación (`rad-shielded-module`, `rad-hold-eva`), `imm-hygiene`, revisiones con el médico, el resto de sensores del hábitat y `hab-co2-removal-check` | — | No se encontró ninguna cifra. Los procedimientos de a bordo con tiempos por paso no son públicos |


### Otras referencias

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| `hayslip-2026` (GeroScience, 23-jun-2026; resumen leído en PubMed el 2026-10-13). Preclínico, hígado de ratón | Por qué existe el campo de efectos adversos: «una intervención puede mejorar una variable y empeorar otra» | `advisor/countermeasures.py`, `advisor/effects.py` |
| OCHMO-TB-031, OCHMO-MTB-009 y OCHMO-MTB-013 (leídas el 2026-10-14 buscando contraindicaciones) | No dan ninguna contraindicación de estas acciones; queda «pendiente de revisión médica» | `countermeasures.py` |
| Especificación del equipo §3, §7, §8 y §14; base de conocimiento §9 e hipótesis H5 | Contramedidas como datos, recursos, seguimiento, coste de la comprobación y respuesta previa | `countermeasures.py`, `followup.py`, `check_cost.py`, `prior_response.py` |

### Sin fuente en el repo

- Las 28 contramedidas `demo` no tienen protocolo concreto.
- Ninguna contramedida tiene contraindicaciones escritas («pendiente de revisión médica»).
- Las ventanas de seguimiento marcadas «diseño EMMA».
- La «trayectoria esperada con y sin contramedida» se rechazó (2026-10-31) por no tener fuente.

---

## 6. `backend/app/evidence/` — el registro de fuentes y su comprobación

Es la rama que **resuelve las fichas** que citan todas las demás. Cuando otra rama dice «ficha
`x`», la referencia completa está aquí.

### El registro único: `app/data/evidence_refs.json`

`evidence/registry.py` carga una ficha por fuente, con los campos que pide la especificación
del equipo (§3, EvidenceRef):
- `id`, `title`, `url`, `doi`, `pmid`, `organization`, `date`.
- `evidence_type`, `evidence_context` y `population` (humano, animal o ambos: principio §2, no
  mezclarlos).
- `notes`, `authors`, `named_people` y `named_organizations`.

**La lista completa de fichas** (id, título, organización, fecha, tipo, población, DOI, PMID y URL)
está en [`docs/fuentes-registro-evidencia.md`](fuentes-registro-evidencia.md), generada desde el
JSON. Es una foto: si no coincide con el JSON, manda el JSON. Las cuentas por tipo, población y
organización se sacan del JSON y no se copian aquí (regla de `CLAUDE.md`).

### Ficheros de «lo leído»

Cada uno guarda la frase literal de la fuente, la ficha del registro que la respalda, cuánto se
leyó (`extent`) y la fecha. Los valida `evidence/read_contract.py`: una frase sin ficha, o de un
sitio que no es la fuente, no carga.

| Fichero de datos | Cargador | Qué contiene |
|------------------|----------|--------------|
| `instruments_read.json` | `instruments_read.py` | PVT (10 y 3 min), escalas de autoinforme, Cognition, glucómetro (agencia de salud pública, desde el 2026-11-04) |
| `nasa_framework_read.json` | `nasa_framework.py` | Arquitectura CDSS de ExMC, IMM, MEDPRAT, IMPACT, huecos Food-01…04, nivel de asistencia IV→V (leído el 2026-10-13, 10-21 y 10-22) |
| `credibility_read.json` | `credibility.py` | **NASA-STD-7009B** (2024, standards.nasa.gov, leída el 2026-10-23): once factores de credibilidad, [M&S 48] y [M&S 31], capa por capa |
| `flight_direction_read.json` | `flight_direction.py` | Sentido del cambio en vuelo de cada indicador, frase a frase |
| `light_exposure_read.json` | `light_exposure.py` | NASA-STD-3001 Vol 2 tabla 8.7-2 y [V2 6117] (fórmulas ACGIH); Brown et al. 2022 (EDI melanópica, recomendación de Tierra, **no** de vuelo) |
| `radiation_read.json` | `radiation_read.py` | HERA (instrumento de Orion, no el análogo homónimo), fase del ciclo solar, fin del refugio |
| `human_datasets_read.json` | `human_datasets.py` | Mapa de conjuntos humanos: Twins Study, OSD-343, OSD-569, OSD-288 (ratón), MMASH, CIPHER |
| `hrp_risks_coverage.json` | `hrp_coverage.py` | Los riesgos del Human Research Roadmap (`https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=…`) y qué hace EMMA con cada uno |
| `mission_profiles.json` | `mission_profiles.py` | Estación, Luna y Marte: cada aspecto con su frase, URL, apartado y fecha, o «sin verificar» con dónde se buscó |
| `facilities_read.json` | `facilities.py` | EPM y Biolab de Columbus (ESA): la cadena instalación → aplicación con sus huecos |
| `testbeds.json` | `testbeds.py` | Bancos de prueba y análogos (`docs/contexto/bancos-de-prueba.md`) |
| `countermeasures_research.json` | `research_countermeasures.py` | Contramedidas en investigación (AGBRESA, LBNP, gravedad artificial, realidad virtual), que nunca se ofrecen |
| `context_sources_read.json` | `context_sources.py` | Las fuentes de §17 de la especificación, incluido el enunciado del reto |
| `design_hypotheses.json` | `design_hypotheses.py` | Hipótesis H1-H7 de la base de conocimiento §13. El vocabulario de estados no tiene «probada» |
| `evidence_tiers.json` | `tier.py` | Nivel de evidencia de cada fuente citada |

### Servicios externos de comprobación (por `core/egress.py`, solo en pruebas `live`)

| Servicio | URL | Para qué | Dónde |
|----------|-----|----------|-------|
| Crossref, DataCite, doi.org | `https://api.crossref.org/works/`, `https://api.datacite.org/dois/`, `https://doi.org/api/handles/` | Que un DOI existe, en ese orden: un 404 de Crossref no prueba nada | `evidence/citations.py` |
| PubMed eutils | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi` | Que un PMID existe; tipo de estudio por MeSH | `citations.py`, `tier.py`, `support.py` |
| ClinicalTrials.gov | `https://clinicaltrials.gov/api/v2/studies/` | Que un NCT existe | `citations.py` |
| NTRS | `https://ntrs.nasa.gov/api/citations/<n>` | Cotejar cerca de 50 informes técnicos de NASA sin DOI (spike `spikes/spike_ntrs.py`) | `evidence/ntrs.py` |
| OSDR Biological Data API v2 | `https://visualization.osdr.nasa.gov/biodata/api/v2` | Comparar campo a campo la ficha de cada estudio OSD con la API. Si discrepan, se declara y no se corrige sola (caso real: el «n = 12» de OSD-288) | `evidence/osdr_data.py` |

### Código de terceros (Polaris, AGPL-3.0-or-later; commit en `polaris/ADOPTADO.txt` y `NOTICE`)

| Original en Polaris | Adaptador en EMMA | Qué hace |
|---------------------|-------------------|----------|
| `tools/verifica_citas.py` | `citations.py` | Existencia de DOI, PMID y NCT, con los cuatro estados |
| `tools/tier_evidencia.py` | `tier.py` | Nivel de evidencia sin modelo de lenguaje |
| `tools/soporte_cita.py` | `support.py` (+ `claims.py`) | ¿Respalda el artículo la cifra que se le atribuye? |
| `tools/decision_alto_riesgo.py` (`_existencia_citas`) | `source_check.py` | Cita «FABRICADA» en una firma de alto riesgo |
| `tools/fuente_clinica.py` (`cotejar`) | `vault.py` | Abre el informe citado y busca el fragmento |
| `tools/dosier_invariantes.py`, `tools/frescura_dosier.py` | `dossier.py` | Esquema, contradicciones y frescura del dosier |

### Normas citadas en esta rama

- **NASA-STD-7009B** (2024): credibilidad de modelos y simulaciones.
- NASA-STD-3001 Vol 2: tabla 8.7-2 y [V2 6117].
- Fórmulas de la ACGIH, a través de [V2 6117].

### Regenerar el anexo

Desde la raíz del repo, con un script que lea `backend/app/data/evidence_refs.json` y escriba una
fila por ficha en `docs/fuentes-registro-evidencia.md`. El de esta pasada vivía en una carpeta
temporal de la sesión, así que no queda en el repo. Si se quiere fijo, va a `backend/scripts/`.

### Sin fuente en el repo

- Ningún caso nuevo. Esta rama es justamente la que obliga a que todo lo demás la tenga. Las
  fichas con huecos declarados («sin verificar», «no_resoluble» en NTRS) lo dicen en su campo.

---

## 7. `backend/app/pain/` — mapa corporal de dolor (con `app/anatomy.py`, `app/pain_on_skeleton.py` y `app/data/anatomy/`)

### Artículos

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| Kerstman et al., Aviat Space Environ Med 2012, **PMID 22272509** («52 % de 728 astronautas») | Por qué existe el mapa de dolor: el dolor de espalda al adaptarse a la microgravedad | `pain/__init__.py`; `compliance/clinical-decision-rationale.md` (cerca de la línea 335) |
| Serlin et al., Pain 1995, **PMID 7659438** | El corte de «intenso» = 7-10 en la escala 0-10. Se estableció en pacientes oncológicos, no en tripulantes: es una convención clínica, no un umbral validado en vuelo | `pain/alarm.py`; `clinical-decision-rationale.md` (cerca de la línea 353) |
| Hardy et al. 2025, Spaceflight Standard Measures de la NASA | Hitos posvuelo R+ del modo anatómico | `app/anatomy.py:1026` |

### Datos anatómicos y su licencia

| Datos | Origen | Licencia | Dónde |
|-------|--------|----------|-------|
| `esqueleto-anterior.png`, `esqueleto.json` (render anterior y centroides por hueso, con nombres de TotalSegmentator) | **BodyParts3D 4.0** (`partof_BP3D_4.0_obj_99.zip`, `https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/…`), generados el 2026-10-01 con `polaris/tools/esqueleto_referencia.py` | **CC BY 4.0**, «© The Database Center for Life Science». Verificada el 2026-10-01 en `https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html`. Obra derivada redistribuida con atribución | `app/data/anatomy/ATRIBUCION.txt` |
| `pain_points.json` | Centro de cada zona, copiado de `frontend/src/pain/bodyModel.ts` y vigilado por una prueba | Propio de EMMA | `app/data/anatomy/` |
| Proporciones del cuerpo dibujado (cabeza, tórax, cráneo, brazo y pierna en el percentil 50) | **ANSUR II** p50 (1,75 m, escalado a 1,73) | **ANSUR II** (US Army, encuesta de 2012). Informe NATICK/TR-15/007 en DTIC: «Approved for public release; distribution is unlimited»; CSV públicos `ANSUR II MALE/FEMALE Public.csv`. EMMA solo toma proporciones p50 y no redistribuye los datos. La licencia exacta de los CSV no consta (búsqueda del 2026-11-14) | `frontend/src/pain/bodyModel.ts` (comentarios de las líneas 351-816); se detalla en la rama `frontend/` |

### Código de terceros (Polaris, AGPL-3.0-or-later; commit en `polaris/ADOPTADO.txt`)

| Original | Uso en EMMA |
|----------|-------------|
| `tools/sintomas.py` (`es_alarma()`, lista `ALARMA`), sin modificar | `pain/alarm.py`: marca «comentar con el médico de a bordo». Es informativa, no una alerta (invariante 5) |
| `tools/visor3d_superpone_focos.py` (`alinea`) | `app/pain_on_skeleton.py`: ajuste por mínimos cuadrados de las zonas sobre el esqueleto real. Umbral geométrico: la mitad de la zona anclada más pequeña (cuello, 0,16 m) |
| `tools/esqueleto_referencia.py` | Generó los ficheros de `app/data/anatomy/` |

### Terminología

- Zonas y tipos de dolor: listas cerradas con el sistema propio `https://emma.mission/codes/pain-zone`
  (`pain/catalog.py`). **No se usa SNOMED CT** a propósito: las zonas son regiones para señalar,
  no estructuras anatómicas.
- La intensidad entra como observación `pain-intensity` del catálogo (rama `ingest/`).
- Lateralidad: la del paciente, no la de quien mira.

### Sin fuente en el repo

- La lista de zonas y tipos de dolor es diseño de EMMA.
- ANSUR II se cita sin URL, versión exacta ni licencia.
- La frase fija con que cada zona pasa por `es_alarma()` la compone EMMA.

---

## 8. `backend/app/imaging/` — ecografía: DICOM, protocolos, medida guiada, fantomas

La procedencia completa, con las reglas de licencia y lo descartado, está en
**`compliance/imaging-data-provenance.md`**, que es la fuente de verdad.

### Bibliotecas

| Qué | Para qué | Dónde | Licencia (según `pyproject.toml`) |
|-----|----------|-------|-----------------------------------|
| `pydicom>=3.0` | Lectura, calibración física y des-identificación de DICOM | `imaging/dicom.py`, `render.py` | MIT |
| `pillow>=11` | Fotograma a PNG, sin realce | `imaging/render.py`, `phantom.py` | MIT-CMU |

### Normas

| Norma | Qué se toma | Dónde |
|-------|-------------|-------|
| DICOM PS3.15, anexo E | Perfil básico de confidencialidad, con la opción de conservar las fechas completas (DCM 113106) | `imaging/dicom.py` |
| DICOM PS3.3 y PS3.4 | Atributos y calibración del equipo (regiones calibradas) | `imaging/dicom.py` |
| LOINC 15309-8 | Volumen vesical = alto × ancho × largo × 0,57. Lo fija la definición del código | `imaging/measure.py` (`bladder_coefficient`) |

### Artículos (protocolos y método)

| Referencia | Para qué | Dónde |
|------------|----------|-------|
| Helmke K, Hansen HC. Pediatr Radiol 1996, **PMID 8805599** | Vaina del nervio óptico medida 3 mm detrás del globo (`contested`) | `imaging/measure.py:54` |
| Crit Care Med 2025, **PMID 40459386** | El punto de referencia de esos 3 mm está en discusión | `measure.py:55` |
| Marshall-Goebel et al., JAMA Netw Open 2019, **PMID 31722025** | Protocolo de la yugular | `imaging/protocols.py:98` |
| Lichtenstein DA, Mezière GA. Chest 2008, **PMID 18403664** | Protocolo BLUE de pulmón | `protocols.py:125` |
| Hamilton DR et al. Aviat Space Environ Med 2004, **PMID 15018297** | Ecografía pulmonar en vuelo | `protocols.py:126` |
| Sargsyan AE et al. J Trauma 2005, **PMID 15674147** | FAST de cuatro ventanas | `protocols.py:149` |
| Daum N et al. Z Gastroenterol 2026, **PMID 42161258** | Índice hepatorrenal | `protocols.py:174` |

### Datos de imagen

| Dataset | Origen | Licencia | Uso | Cita obligatoria |
|---------|--------|----------|-----|------------------|
| **HC18** (perímetro cefálico fetal) | Zenodo, doi:10.5281/zenodo.1327317. Lo descarga `scripts/fetch_hc18.py`, que comprueba el MD5 | CC BY 4.0 | Validación `-m external`: calibres en píxeles a mm sin error de escala. No viaja en el paquete | van den Heuvel et al., PLoS ONE 13(8):e0200412, 2018 |
| **Hígado graso en modo B** | Zenodo, doi:10.5281/zenodo.1009146 | CC BY 4.0 | Ejemplos `liver-*.png` en el paquete; sin calibración, no se mide | Byra M. et al., Int J CARS 2018, doi:10.1007/s11548-018-1843-2 |
| **Ecografía pulmonar** | Mendeley Data, doi:10.17632/hb3p34ytvx.2 (licencia leída en el registro de datos) | CC BY 4.0 | Ejemplos `lung-*.png` en el paquete | Katumba A. et al., Data in Brief 62:112034, 2025 |
| Fantomas sintéticos | Generados por `imaging/phantom.py` | Propios | Nervio óptico, yugular y vejiga, firmados `simulator:phantom` | — |

Los ejemplos que viajan en el paquete están en `app/data/ultrasound_samples/` con
`manifest.json`, que da el origen, la licencia y el SHA-256 de cada imagen. La cita viaja en el
asiento del ledger.

**Buscados y descartados** (§3 del documento de procedencia):
- OSD-435.
- Ecografía de tripulación de la ISS.
- Marzola et al. 2023: la licencia es del artículo, no de los datos.
- `covid19_ultrasound`: CC BY-NC.
- COVID-BLUES: CC BY-NC-ND.
- Ecografías de Inspiration4 en TRISH EXPAND: acceso controlado.
- Vejiga, yugular y FAST: no se encontró ningún dataset abierto.

### Sin fuente en el repo

- `onsd_depth_tolerance_mm = 0,5` y `right_angle_tolerance_deg = 15`: el propio código los
  declara «lo fija el proyecto».

---

## 9. `backend/app/volumes/` — TAC/RM, segmentación y visor 3D

Recordatorio de `CLAUDE.md`: **hoy no vuela ningún TAC**. Estos volúmenes son imagen de referencia
previa al vuelo o de Tierra, no diagnóstico a bordo. La procedencia completa está en
`compliance/imaging-data-provenance.md` §2.0.

### Bibliotecas y programas

| Qué | Para qué | Dónde | Origen / licencia según el repo |
|-----|----------|-------|---------------------------------|
| `nibabel>=5` | Lectura de NIfTI | `volumes/` | MIT (`pyproject.toml`) |
| `scikit-image>=0.24` | Marching cubes (mallas) | `volumes/geometry.py` vía Polaris | BSD-3 (`pyproject.toml`) |
| **TotalSegmentator** (programa externo, `backend/.venv-seg`, pesos en `~/.totalsegmentator`, telemetría apagada) | Segmentación local de TAC. **No se empaqueta**: si falta, se declara no disponible | `volumes/segment.py` | Wasserthal et al., Radiol AI 2023. Código y pesos de las tareas usadas bajo **Apache-2.0** (`totalsegmentator` 2.18.0 en `.venv-seg`: «Apache 2.0», metadatos leídos el 2026-11-14). Necesita PyTorch |

### Datos

| Dataset | Origen | Licencia | Uso | Cita obligatoria |
|---------|--------|----------|-----|------------------|
| **TotalSegmentator dataset v2.0.1** (1228 TAC, 117 estructuras) | Zenodo, **doi:10.5281/zenodo.10047292**. Sujetos sueltos por rangos HTTP con `scripts/fetch_ct_samples.py` (sin el zip de 23,6 GB) | **CC BY 4.0**, leída en el registro | Cuatro ejemplos en `app/data/volume_samples/`: `higado-1` (s0816), `higado-2` (s0048), `ojos-3` (s0289) y `esqueleto-4` (s1152, reparto `test`). Cada uno recortado a 2 mm, con su segmentación precalculada y SHA-256 en `manifest.json`, firmado `simulator:dataset`. Generados con `scripts/build_volume_samples.py`. Validación `-m external` **solo con sujetos `test`** (mina de `CLAUDE.md`) | Wasserthal J. et al., *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images*. Radiol Artif Intell 2023;5(5):e230024 |

### Código de terceros (Polaris, AGPL-3.0-or-later, © 2026 «Beyond the Protocol»)

| Original | Cómo lo usa EMMA | Dónde |
|----------|------------------|-------|
| `polaris/tools/visor3d.py`, llamado tal cual desde la copia: `nifti_bytes` (`nifti_limpio`), `ply_binario`, `_taubin`, `_malla`, `_icosfera`, `_elipsoide`, `_diametro_axial_mayor`, `empareja`, `evolucion`, `verifica_sin_pii`, `_trozos_pii` | Mallas, medidas de lesiones, evolución entre estudios, puerta de privacidad del NIfTI | `assets.py`, `geometry.py`, `privacy.py`, `spine.py`, `skeleton_view.py` |
| `tools/visor3d.py` @ `7bf47257`, **adaptado a mano**: `segmenta()` y `exige_telemetria_apagada()` | Divergencias pendientes de decisión (`docs/polaris-divergencias.md`) | `segment.py`, parte de `assets.py` |
| `polaris/tools/visor3d_web/` (visor web, con colores y textos cambiados) | Compilado fuera de la copia por `frontend/scripts/build-polaris.mjs` en `app/data/polaris_web/` | `volumes/polaris_web.py` |

Repositorio de origen de Polaris: `https://github.com/BeyondTheProtocol/polaris` (`NOTICE`).

### Documentos internos

- `compliance/risk-management-file.md`: «Esqueleto incompleto» (control de `spine.py`) y H18
  (lo que no cubre la puerta de privacidad).
- `docs/polaris-divergencias.md`: lo adaptado y pendiente de decidir.

### Sin fuente en el repo

- `contrast_phase.py`: la fase de contraste es una etiqueta que declara una persona, sin código
  LOINC (invariante 1).
- Las constantes `AIR_HU` y `WINDOW_WIDTH` son las de Polaris y una prueba lo comprueba. No hay
  fuente bibliográfica para ellas en el repo.

---

## 10. `backend/app/reports/` — informes escaneados: OCR local, des-identificación, analíticas

Todo corre a bordo y sin red: un informe médico no sale a un servicio en la nube. Esta rama es casi
entera **código de Polaris usado tal cual** con un adaptador de EMMA.

### Programas y bibliotecas

| Qué | Para qué | Dónde | Origen / licencia según el repo |
|-----|----------|-------|---------------------------------|
| **tesseract** (programa externo; ruta típica `C:\Program Files\Tesseract-OCR\tesseract.exe`) | OCR de páginas escaneadas | `reports/ocr.py` | Sin URL, versión ni licencia en el código. Si falta, `OcrUnavailable` |
| `pypdfium2>=4.30` | Rasterizar PDF en Windows, en lugar de `pdftoppm` | `reports/ocr.py` | BSD-3 o Apache-2.0 (`pyproject.toml`) |
| `pillow` | Abrir imágenes, en lugar de `sips` de macOS | `reports/ocr.py` | MIT-CMU |
| Capa NER opcional: modelo **`BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`** (Hugging Face), con `torch` (CPU) y `transformers` en `backend/.venv-deid` | Segunda capa de des-identificación, entrenada con historias clínicas en castellano | `reports/deid.py`; la instala `scripts/install_deid_ner.py` (decisión del usuario, 2026-10-01) | Revisión fijada por Polaris. EMMA comprueba el SHA-256 de los pesos contra `SHA256_PESOS` de `deid_ner.py`. **El modelo no es público**: Hugging Face responde 401 sin una cuenta que acepte sus condiciones (`HF_TOKEN`). Su licencia no consta en el repo. No va en el instalador |

### Código de terceros (Polaris, AGPL-3.0-or-later, © 2026 «Beyond the Protocol»; commit en `polaris/ADOPTADO.txt`)

| Original | Qué hace | Adaptador en EMMA | Qué pone EMMA (AGPL §5a) |
|----------|----------|-------------------|--------------------------|
| `tools/ocr_informes.py` (`_tsv_a_texto`, `LANGS`, `DPI`, `TEXT_LAYER_MIN_CHARS`, `CONF_MINIMA` = 60/100) | Maquetación desde el TSV de tesseract | `ocr.py` | Rasterizado en Windows y sin escribir ficheros junto al original |
| `tools/deid.py` (`de_identificar_verificado`). Único cambio declarado en `polaris/CAMBIOS.json`. Original desde el commit `e3b588d` (antes, versión adaptada hasta `7bf4725`) | Patrones (correo, teléfono, DNI/NIE, historia, fechas, filiación), normalizador contra homoglifos, **revalidación que falla cerrada** | `deid.py` | Regla de nombres con tratamiento y parentesco |
| `tools/deid_ner.py` | Capa NER | `deid.py` (`ner=True`) | Comprobación del SHA-256 |
| `tools/identidad_paciente.py` (`verificar`) | ¿El informe es de este tripulante? | `identity.py` | La identidad sale del ledger (`crew-identity`), no de un fichero local |
| `tools/biomarcadores.py` (diccionario `ANALITOS`, familias de unidades) | Extraer analitos de una analítica | `labs.py` | **Confirmación humana** de cada cifra antes de entrar al análisis. Equivalencias LOINC en `app/data/lab_loinc.json` |
| `tools/incongruencias_caso.py` (`analizar`) | Mismo dato con valores distintos | `incongruences.py` | Muestra = sangre de un día; diferencia relativa > 5 % (parámetro de diseño) en vez de 5 puntos |

### Normas y documentos

- DICOM PS3.15: el perfil que ya usaba la ecografía (rama `imaging/`), citado como comparación.
- `compliance/risk-management-file.md`, **H17**: el texto de los informes no estaba
  des-identificado. Este módulo lo corrige.
- Límite declarado por Polaris: una des-identificación por patrones siempre es porosa.

### Sin fuente en el repo

- ~~La URL, versión y licencia de tesseract~~ **Resuelto el 2026-11-14**: tesseract v5.4.0.20240606 (leptonica 1.84.1), **Apache-2.0** (`C:\Program Files\Tesseract-OCR\doc\LICENSE`).
- ~~Hallazgo: faltaba `spa.traineddata`~~ **Arreglado el 2026-11-14**: se instaló `spa.traineddata` de `https://github.com/tesseract-ocr/tessdata_fast` (la misma variante que el `eng` instalado, que coincide byte a byte con el de ese repositorio). Hash git `72e901f1…` comprobado contra la API de GitHub; SHA-256 `6f2e04d0…`; licencia Apache-2.0. `tesseract --list-langs` da eng, osd y spa. Una imagen de prueba se leyó bien con `-l spa+eng`, tildes incluidas, y pasan las 202 pruebas de informes.
- La licencia del modelo NER de BSC, **comprobada sin éxito el 2026-11-14**:
  - La API de Hugging Face (`/api/models/BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`) responde 401.
  - El modelo **no aparece** entre los 157 modelos públicos de la organización `BSC-NLP4BIA`: es
    privado o se retiró.
  - La revisión que fija Polaris es `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`
    (`polaris/tools/deid_ner.py:35`).
  - Su licencia no es verificable sin un acceso que la organización conceda.
  - El hermano público de la misma organización, `bsc-bio-ehr-es-carmen-anon`, es **CC BY 4.0**.
    Sustituirlo sería una decisión aparte: cambia el detector de Polaris.
- El margen del 5 % de `incongruences.py` (diseño).

---

## 11. `backend/app/interpret/` — borrador con modelo de lenguaje local (Clase C, segregado)

Alcance (invariante 6): el borrador es **Clase C por elemento** de IEC 62304 y nunca entra en el
análisis ni en una alerta (`compliance/software-safety-classification.md` §2.1). Solo corre en
local: una URL que no sea de loopback se rechaza.

### Programas y modelos

| Qué | Para qué | Dónde | Origen / licencia según el repo |
|-----|----------|-------|---------------------------------|
| **Ollama**, API de chat (`POST /api/chat`, `stream: false`, `format` como esquema JSON, `options.temperature`) en `http://127.0.0.1:11434` | Servidor local del modelo | `interpret/llm.py`, `core/config.py:94` | Licencia **MIT** (`llm.py`). Formato verificado en `docs/api.md` de Ollama, «Generate a chat completion». Es también el «cerebro» de Polaris |
| Redactor `qwen3.6:35b-a3b` | Redacta el borrador | `config.py:95` (`llm_model`) | Elegido por prueba propia (8,5 s en una GPU de 8 GB), anotada en el comentario. **No está instalado en esta máquina** (`ollama list`, 2026-11-14): el valor por defecto de `llm_model` no se puede cargar aquí. Licencia: sin comprobar |
| Verificadores `qwen3.6:35b-a3b` y `gemma4:latest` (Google) | Comité adversarial de casas distintas | `config.py:101` (`llm_verifiers`) | Prueba del 2026-09-25: gemma4 cazó la afirmación inventada; `llama3.1:8b` (Meta) quedó fuera por objetarlo todo. **Ninguno de los dos está instalado** con esas etiquetas (`ollama list`, 2026-11-14); sí lo están `gemma4:e2b`, `gemma4:e4b` y `gemma4:12b-it-qat`. Licencia: sin comprobar |
| Asistente `qwen3.5:9b`; probados también `gemma4:12b-it-qat`, `ministral-3:8b`, `granite4.2:8b`; voz con `gemma4:e4b` | Asistente de la consola (rama `assistant/`) | `config.py:108-127`, `llm.py:162` | Comparativas propias con fecha en los comentarios. **Apache-2.0** según `ollama show --license` (2026-11-14) en los instalados: `qwen3.5:9b`, `qwen3.5:4b`, `gemma4:e2b`, `gemma4:e4b`, `gemma4:12b-it-qat`, `ministral-3:8b`, `qwen3-vl:*` y `emma-qwen3.5-9b-v2`. `granite4.2:8b` no está instalado |

### Código de terceros (Polaris, AGPL-3.0-or-later; `https://github.com/BeyondTheProtocol/polaris`)

| Original | Uso | Dónde |
|----------|-----|-------|
| `tools/local.py` (`_ANTI`), sin modificar | Guarda contra inyección (`DATA_GUARD`) | `interpret/draft.py` |
| `tools/cotejo_invariante.py` @ `7bf47257` (`_AUSENCIA`, `_PRESENCIA`, `_NEG_RE`, `afirma_estado_alteracion`), **adaptado** | Cotejo de presencia y ausencia de signos ecográficos. Se quitan los términos genómicos y se añaden los de EMMA. Divergencia pendiente en `docs/polaris-divergencias.md` | `interpret/cotejo.py` |
| `tools/salida.py` (patrón) | Firma humana sobre la huella del texto leído | `draft.py`, `core/storage.py` |
| Patrón de comité de verificadores de casas distintas | Solo el patrón, sin código copiado | `draft.py` |

Lo que es de EMMA: los hechos del registro, los prompts, `fenced()`, el encadenado de las seis
barreras y `app/text_guard.py` (filtro de lenguaje, con léxicos de `honestidad_lint.py` y
`decision_alto_riesgo.py` de Polaris; se detalla en la rama de módulos sueltos).

### Sin fuente en el repo

- ~~Licencias de los modelos~~ **Resuelto en parte el 2026-11-14**: los modelos instalados declaran Apache-2.0 en Ollama (`ollama show --license`). Queda:
  - Hay que comprobar `qwen3.6:35b-a3b`, `gemma4:latest` y `granite4.2:8b`, que **no están instalados**.
  - **Hallazgo:** el redactor y los verificadores configurados por defecto (`llm_model`, `llm_verifiers`) no están en esta máquina.
  - `emma-qwen3.5-9b-v2` es un modelo derivado y local; su origen no consta en el repo.
- La elección de modelos sale de pruebas propias fechadas, no de una evaluación publicada.

---

## 12. `backend/app/assistant/` — asistente de voz «EMMA» (con `app/voice.py`)

Pedido por el usuario el 2026-11-03. El asistente entiende, contesta y propone; **nunca firma**
(invariantes 4 y 7). Sin modelo, el turno sale igual, con lo determinista.

### Programas y modelos

| Qué | Para qué | Dónde | Origen / licencia según el repo |
|-----|----------|-------|---------------------------------|
| Ollama con `qwen3.5:9b` (`assistant_model`) | Elegir la intención y redactar la frase | `assistant/turn.py`, `core/config.py:119` | Comparativa propia del 2026-11-04 con cuatro modelos (rama `interpret/`). **Apache-2.0** (`ollama show --license`, 2026-11-14) |
| **Whisper**, modelo `base` (`openai-whisper`, `torch` CPU, `soundfile`, en `backend/.venv-voice`) | Voz a texto, local y sin red | `app/voice.py`; lo instala `scripts/install_voice.py` (decisión del usuario, 2026-10-01) | Whisper comprueba el SHA-256 de su URL de descarga y EMMA lo recalcula y guarda en `voice-ok.json`. `openai-whisper` 20250625: **MIT** (metadatos instalados). No va en el instalador |
| `soundfile` 0.14.0 / libsndfile 1.2.2 | WAV a Ogg/Opus | `assistant/audio.py` (en el entorno de voz) | Versiones comprobadas el 2026-11-03. **BSD-3-Clause** (metadatos instalados) |

### Código de terceros (Polaris, AGPL-3.0-or-later)

| Original | Uso | Cambio declarado |
|----------|-----|------------------|
| `polaris/tools/transcribe_audios.py`, ejecutado como programa aparte | Transcripción | `SRC` y `OUT` por variable de entorno (`polaris/CAMBIOS.json`) |

### Datos propios que lee el asistente

| Fichero | Qué es |
|---------|--------|
| `app/data/assistant_intents.json` | Catálogo cerrado de intenciones, con su esquema y grupos de sinónimos |
| `app/data/assistant_ui.json` | Inventario de la interfaz (unas 175 entradas con su `about`), cotejado con los `.tsx` por `frontend/src/assistant/uiInventory.test.ts` |
| `app/data/assistant_examples.json` | Ejemplos del asistente |
| Glosario, guías de medida, perfiles de misión, catálogo de dolor e indicadores | Se leen de su propia fuente para que ninguna lista se quede atrás |

### Barreras (todas deterministas)

- `text_guard`: el filtro de lenguaje de EMMA (`app/text_guard.py`).
- `numbers`: toda cifra tiene que estar en el contexto, incluidas las cifras escritas con letras.
- `no_prescription`: no recetar.
- `schema`: la intención tiene que estar en el catálogo.

`retrieval.py` puntúa por palabras, sin modelo ni red, a partir de una medición propia del
2026-11-04 (la mitad de las frases naturales fallaban).

### Sin fuente en el repo

- ~~Licencias~~ **Resuelto el 2026-11-14**, de los metadatos instalados en `.venv-voice`:
  - `openai-whisper` 20250625: **MIT**.
  - `soundfile` 0.14.0: **BSD-3-Clause**.
  - `torch` 2.14.1+cpu: **Apache-2.0** (con excepción LLVM y otras en su expresión SPDX).
  - `qwen3.5:9b`: **Apache-2.0** (`ollama show --license`).
  - Pesos de Whisper, **resuelto el 2026-11-14**: «Whisper's code and model weights are released under the MIT License» (README de `https://github.com/openai/whisper`).
- Por diseño, las respuestas `general` son «conocimiento del modelo, sin fuente» y se rotulan así ante la
  persona (decisión del usuario, 2026-11-03).

---

## 13. `polaris/` y `backend/app/polaris/` — el código de terceros que incorpora EMMA

### Qué es y de dónde sale

| Campo | Valor según el repo |
|-------|---------------------|
| Proyecto | **Polaris**, «Un sistema personal para sostener investigación clínica dirigida por objetivo» (`polaris/CITATION.cff`) |
| Autoría | «Beyond the Protocol» (© 2026, la autora de Polaris, que opera bajo ese nombre) |
| Repositorio | `https://github.com/BeyondTheProtocol/polaris` |
| Licencia | **AGPL-3.0-or-later** (`polaris/LICENSE`). Por ella **EMMA entera es AGPL-3.0-or-later** (`LICENSE`, `NOTICE`) |
| Commit vigente de la copia | `20527939e00b9ebc063a0024210e6f9df663d989` (desde el 2026-10-08), fijado en `polaris/ADOPTADO.txt` |
| Historia de la copia | `7bf4725` → `e3b588d` (2026-10-01; Polaris se republicó sin historia común) → `0e629e4` (2026-10-04) → `849989f` (2026-10-07) → `2052793` (2026-10-08). Detalle en `polaris/ORIGEN.md` y `docs/polaris-divergencias.md` §12, §15, §17 y §18 |
| Cita | `polaris/CITATION.cff`. No tiene `date-released`: el propio fichero dice que no se verificó una fecha de publicación |

### Cómo se copia y se vigila

- **Copia literal, byte a byte**, desde los objetos de git del commit, no desde una copia de trabajo
  (en Windows saldría en CRLF). La hace `backend/scripts/polaris_sync.py` según
  `polaris/ADOPTADO.txt`: herramientas pedidas (`root`), su cierre de imports, datos, pruebas y
  fichas. Huellas en `polaris/MANIFEST.sha256`, y `backend/tests/test_polaris_copy.py` falla si la
  copia cambia.
- **Lo que no se copia, por su nombre y motivo:** `backend/scripts/polaris_left_out.py` y
  `docs/polaris-divergencias.md` §18.
- **Cambios a ficheros copiados** (AGPL §5a): solo los de `polaris/CAMBIOS.json`, con fecha y
  motivo. A 2026-11-14 son seis:
  - `tools/visor3d_web/index.html`, `main.js` y `render.js`: colores y textos de EMMA (2026-09-29).
  - `tools/deid.py` (2026-10-01).
  - `tools/transcribe_audios.py` (2026-10-01): `SRC` y `OUT` por variable de entorno.
  - `tools/estado_actual.py` (2026-10-20).
- **Pruebas de Polaris**: se corren aparte (`backend/scripts/polaris_tests.py`, sin red), con el
  informe en `polaris/PRUEBAS.md`. Estado de cada herramienta: `polaris/ESTADO.md`.

### Las herramientas que EMMA usa (`EMMA_USES`, `backend/app/api/polaris.py:45`)

`_net`, `anticipa`, `atascos`, `biomarcadores`, `borde`, `canarios`, `cascada_mapa`, `cronica`,
`cumbre`, `decision_alto_riesgo`, `deid`, `dosier_invariantes`, `estado_rutina`, `frescura_dosier`,
`fuente_clinica`, `guarda_memoria`, `honestidad_lint`, `identidad_paciente`, `incongruencias_caso`,
`kb`, `local`, `md_to_pdf_pro`, `ocr_informes`, `paso_consolidacion`, `score_local`, `seguimiento`,
`sintomas`, `soporte_cita`, `tier_evidencia`, `verifica_citas`, `visor3d`,
`visor3d_superpone_focos`.

Dónde lo usa cada una se dice en su rama (1, 6, 7, 9, 10 y 11, y más abajo en los módulos sueltos).
El resto de `polaris/tools/` está copiado sin uso. Cada herramienta en uso tiene fila en la ficha de
SOUP (`compliance/software-safety-classification.md` §4.2).

### Código de Polaris adaptado a mano (`NOTICE`, commit de origen `7bf47257…`)

| Origen | Destino en EMMA |
|--------|-----------------|
| `tools/honestidad_lint.py` (`_TRIGGERS`) | `app/text_guard.py` (`_OVERCLAIM`) |
| `tools/decision_alto_riesgo.py` (`_TTO`, `_ACCION`, `_DELIBERA_FUERTE`) | `app/text_guard.py` (`_ACTION`, `_DELIBERATE`) |
| `tools/cotejo_invariante.py` | `app/interpret/cotejo.py` |
| `tools/salida.py` (aprobación con nonce) | `app/core/storage.py` (`sign_draft`) |
| `tools/decision_alto_riesgo.py` (acta a dos voces) | `app/core/storage.py` (`countersign_draft`) |
| `tools/tier_evidencia.py` (`_fetch_pubmed`) | `backend/scripts/grade_sources.py` |
| `tools/verifica_citas.py` | `app/evidence/citations.py`, `tests/test_citations_live.py` |
| `tools/soporte_cita.py` | `app/evidence/support.py`, `tests/test_citation_support_live.py` |
| `tools/visor3d.py` (lesiones, `segmenta`, `exige_telemetria_apagada`) | `app/volumes/geometry.py`, `segment.py`, `assets.py` |

La lista completa y vigente está en `NOTICE`.

### El adaptador `backend/app/polaris/`

Único punto de entrada (`load`, `inventory`, `console.captured`). Hace estas cosas:
- Apunta `BTP_REPO` y `BTP_STATE_DIR` al estado de EMMA.
- Da a `ia.py` un registro con **solo** `local-ollama`: sin nube, decidido para siempre el
  2026-09-29 (`polaris-divergencias.md` §1).
- Confina el freno por fichero (`HALT_FILES`).
- Siembra el señuelo de `canarios`.

`compat/` (`fcntl.py`, `resource.py`, `winlock.py`, `memguard.py`, `sitecustomize.py`) pone lo que a
la copia le falta en Windows, sin tocarla. `NOT_IMPORTED` lista las herramientas que hacen algo solo
con importarse.

### Pendiente

Lo que queda por decidir sobre Polaris está en la «lista vigente» de `docs/polaris-divergencias.md`
(§17 y §18).

---

## 14. `backend/app/validation/` — validación externa con fisiología humana real

Invariante 5: falsa alarma sobre sujetos sanos **y** sensibilidad sobre deterioros inyectados en
esa misma fisiología, siempre juntas. **Las cifras vigentes no se copian aquí.** Su fuente de
verdad es `compliance/external-validation.md` y los tests `-m external`.

### Datasets

| Dataset | Origen | Licencia | Qué valida y qué no | Dónde |
|---------|--------|----------|---------------------|-------|
| **MMASH** (*Multilevel Monitoring of Activity and Sleep in Healthy people*): 22 sujetos sanos, 24 h, RR latido a latido con banda Polar H7, actigrafía, sueño y cuestionarios | PhysioNet, `https://physionet.org/files/mmash/1.0.0/MMASH.zip` (unos 25 MB, fuera de git). Lo descarga `scripts/fetch_mmash.py`. Ficha `mmash` en el registro | **ODbL v1.0** (Open Data Commons Open Database License) | **Valida** el motor (HRV, artefactos, línea base, falsa alarma en sanos). **No valida** la deriva de vuelo (mina de `CLAUDE.md`) | `validation/mmash.py`, `report.py`, `episodes.py` |
| **LifeSnaps**: 71 personas, Fitbit Sense, unas 8 semanas | Zenodo, **doi:10.5281/zenodo.7229547**, `https://zenodo.org/api/records/7229547`, fichero `rais_anonymized.zip` con MD5 `726afe26…` (leído en la API el 2026-11-01). Ficha `lifesnaps-2022` | **CC BY 4.0** | Varias semanas por persona, para medir el respaldo de familia y la cobertura de la hora (decisión del usuario, 2026-10-23). No son sujetos «sanos» con cribado clínico | `validation/lifesnaps.py`, `family_variants.py` |
| **HC18** | Zenodo, doi:10.5281/zenodo.1327317 (rama `imaging/`) | CC BY 4.0 | Calibres a mm del motor de ecografía | `validation/hc18.py` |

**Citas:**
- LifeSnaps: Yfantidou S et al. *LifeSnaps, a 4-month multi-modal dataset capturing unobtrusive
  snapshots of our lives in the wild.* Sci Data 2022;9:663 (`lifesnaps.py:72`).
- MMASH, **resuelto el 2026-11-14** (cita que pide `https://physionet.org/content/mmash/1.0.0/`, leída ese día):
  - Rossi A, Da Pozzo E, Menicagli D, Tremolanti C, Priami C, Sirbu A, Clifton D, Martini C, Morelli D (2020). *Multilevel Monitoring of Activity and Sleep in Healthy People* (version 1.0.0). PhysioNet. doi:10.13026/cerq-fc86.
  - Artículo original: Rossi A et al. *A Public Dataset of 24-h Multi-Levels Psycho-Physiological Responses in Young Healthy Adults.* Data 2020;5(4):91. doi:10.3390/data5040091.
  - Cita estándar de PhysioNet: Pollard T et al. *PhysioNet as a global platform for biomedical research.* Nature Health (2026). doi:10.1038/s44360-026-00096-z.
  - Licencia confirmada: «Open Data Commons Open Database License v1.0».

### Método

| Pieza | Respaldo |
|-------|----------|
| Deterioros inyectados de magnitud conocida sobre series reales (`validation/injection.py`) | Diseño de EMMA. Los multiplicadores están **medidos en MMASH, no citados** (`external-validation.md`, cerca de la línea 577) |
| Episodios: marcas del mismo indicador a menos de media hora = un aviso | Parámetro de diseño, sin fisiología detrás; el propio módulo lo dice |
| Variantes de familia (A, B, C) y su cobertura (media hora, 5 lecturas) | Diseño de EMMA, fijado antes de medir. Nada se adopta sin decisión del usuario |

### Referencia de motivación

- **Epic Sepsis Model**: AUC 0,846 interno frente a 0,761 externo; se le escapó el 67 % de las
  sepsis mientras alertaba sobre el 18 % de los ingresados. Es por qué la validación tiene que ser
  externa. Citado en `validation/mmash.py` y `report.py`, con fuente en
  `compliance/state-of-the-art.md:176` (validación externa en JAMA Intern Med,
  `https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2781307`).

### Bibliotecas

`httpx` (por `egress`, en las descargas) y la biblioteca estándar (`csv`, `zipfile`). Para leer
LifeSnaps hace falta lector de BSON (`fitbit.bson`, `sema.bson`); el código no indica con qué
biblioteca.

### Sin fuente en el repo

- ~~El artículo de MMASH~~ **Resuelto el 2026-11-14** (ver arriba). Conviene añadir estas citas a la ficha `mmash` del registro, que es decisión de código.
- RELAX se nombra como alternativa a LifeSnaps, sin ficha.
- El corte de media hora de los episodios y los umbrales de cobertura son diseño.

---

## 15. `backend/app/api/` (+ `app/main.py`) — rutas FastAPI

Rama sobre todo **de pegamento**: sirve lo que calculan las demás y apenas tiene fuentes propias.
Cada ruta se apoya en el módulo que ya se documentó en su rama.

### Bibliotecas

| Qué | Para qué | Origen / licencia |
|-----|----------|-------------------|
| `fastapi>=0.115` (`APIRouter`, `CORSMiddleware`, `StaticFiles`, `run_in_threadpool`) | Rutas, CORS y ficheros estáticos (visor de Polaris compilado) | `pyproject.toml`. **MIT** (0.141.1, metadatos instalados) |
| `uvicorn[standard]>=0.32` | Servidor | `pyproject.toml` |
| `pydantic>=2.9` | Validación de cuerpos (`BaseModel`, `StringConstraints`, validadores) | `pyproject.toml` |
| Biblioteca estándar: `xml.etree.ElementTree`, `zipfile`, `uuid` | Importaciones (Apple Health, ficheros) | — |

### Lo que tiene fuente propia en esta rama

| Ruta | Fuente | Dónde |
|------|--------|-------|
| Contrato JSON de §5 de la especificación del equipo (`timestamp`, `subject_id`, `variable_id`, …) | `docs/contexto/especificacion-tecnica-v1.1.md` §5 y §13. La correspondencia está en `compliance/record-integrity.md` §3.14 quater | `api/spec5.py` |
| Reproducción de Inspiration4, con la cita literal de OSDR | OSD-569 (rama `ingest/`) | `api/replay.py:25` |
| Vitamina D: la cifra diaria de la tabla 7.1-2 de NASA-STD-3001 Vol 2 Rev F | Norma | `api/descriptive.py:157` |
| Aceptabilidad de la comida, [V2 7002] | Norma (rama `analysis/`) | `api/nutrition.py` |
| [V1 4030], Vol 1 Rev C | Límite de dosis de carrera | `api/routes.py` |
| Inventario de Polaris en uso (`EMMA_USES`) | Rama `polaris/` | `api/polaris.py` |
| Base de datos de **Marplanner** guardada en el ledger, como changesets de SQLite (decisión del usuario, 2026-11-12) | Código de terceros: ver la rama 22, `marplanner/` | `api/planner.py` |

### Sin fuente en el repo

- ~~Licencias~~ **Resuelto el 2026-11-14** (metadatos instalados):
  - `fastapi` 0.141.1: **MIT**.
  - `starlette` 1.6.0: **BSD-3-Clause**.
  - `uvicorn` 0.53.0: **BSD-3-Clause**.
  - `pydantic` 2.13.5: **MIT**.

---

## 16. `backend/app/data/` — datos que viajan en el paquete

Índice de cada fichero con la procedencia que declara su propia nota (`_nota`, `basis` o `source`).
Los que ya se documentaron a fondo en otra rama solo se remiten allí.

### Datos de terceros (con licencia propia)

| Fichero o carpeta | Origen | Licencia | Rama |
|-------------------|--------|----------|------|
| `osdr/OSD-569_…CBC_TRANSFORMED.csv` | NASA OSDR, OSD-569 (Inspiration4) | Cita que pide OSDR | 2 |
| `donki_snapshot.json` | Respuesta real de NASA DONKI, con `source_url`, `retrieved_at` y `licence` | Obra del Gobierno de EE. UU. (17 U.S.C. §105) | 3 |
| `anatomy/esqueleto-*` | BodyParts3D 4.0 | CC BY 4.0, `ATRIBUCION.txt` | 7 |
| `ultrasound_samples/` | Hígado (Zenodo 1009146) y pulmón (Mendeley hb3p34ytvx.2), con `manifest.json` y SHA-256 | CC BY 4.0 | 8 |
| `volume_samples/` | TotalSegmentator dataset v2.0.1 (Zenodo 10047292), con `manifest.json` | CC BY 4.0 | 9 |
| `kb-model/` (`model_qint8_avx512_vnni.onnx`, `tokenizer.json`) | **`intfloat/multilingual-e5-small`**, revisión `614241f622f53c4eeff9890bdc4f31cfecc418b3`, SHA-256 de cada fichero en `MODELO.json` | **MIT** (`MODELO.json`) | Búsqueda semántica de `app/kb.py` (rama 17) |
| `polaris_web/` | Visor de Polaris compilado por `frontend/scripts/build-polaris.mjs` | AGPL-3.0-or-later | 9, 13 |

### Datos «leídos»: frase literal de la fuente, con ficha y fecha (rama 6)

`evidence_refs.json` (el registro), `instruments_read.json`, `nasa_framework_read.json`,
`credibility_read.json` (NASA-STD-7009B), `flight_direction_read.json`, `light_exposure_read.json`,
`radiation_read.json`, `human_datasets_read.json`, `hrp_risks_coverage.json`,
`facilities_read.json`, `testbeds.json`, `context_sources_read.json`,
`countermeasures_research.json`, `design_hypotheses.json` (copia literal de H1-H7) y
`mission_profiles.json` (leído el 2026-10-13 en nasa.gov, science.nasa.gov y ntrs.nasa.gov).

Además:
- `evidence_tiers.json`: nivel de cada fuente, sacado de PubMed
  (`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`).
- `lab_loinc.json`: código LOINC de cada analito de `biomarcadores.ANALITOS` de Polaris,
  verificado el 2026-10-01 contra LOINC 2.82 en tx.fhir.org. La unidad sigue a la propiedad de
  LOINC (invariante 2).
- `location_sensing.json`: viabilidad de la ubicación, con fuentes como NASA JSC (balizas BLE,
  NTRS 20190001027, `https://ntrs.nasa.gov/citations/20190001027`). Su desarrollo está en
  `compliance/location-sensing-feasibility.md`.

### Datos con reglas y su base declarada

| Fichero | Qué es | Base declarada |
|---------|--------|----------------|
| `countermeasures.json` | 40 contramedidas | Cada cifra con fuente o «diseño EMMA» (rama 5) |
| `countermeasure_effects.json` | Dónde cae cada efecto | Conversación de ideación; fuera de la huella (rama 5) |
| `measurement_cost.json` | Coste de medir | Base de conocimiento §9; el tiempo solo con fuente (rama 2) |
| `resources.json` | Vocabulario de recursos | Sale solo de los textos de `countermeasures.json` |
| `measurement_guides.json` | Cómo tomarse cada medida | Enunciado del reto («Do not assume that astronauts know everything…»); cada guía con su fuente |
| `glossary.json` | Términos de la interfaz | Cada término dice su `origin` y su documento |
| `mission_modes.json` | Niveles de misión | Lo comprueba `core/mission_modes.py` |
| `data_sharing.json` | Qué se comparte y qué no | `app/sharing.py`; contrastado con pruebas |
| `habitat_systems.json` | Sistemas del hábitat | Vocabulario de diseño con `basis_refs` (OCHMO-TB-002, ATCS) |
| `assistant_*.json` | Asistente | Propios (rama 12) |
| `samples/spec5_observations.json` | Ejemplo del contrato §5 | Propio |

### Declarados como diseño de EMMA, sin fuente

- `habitat_modules.json`: «Parámetro de diseño de EMMA, sin respaldo bibliográfico: EMMA no modela
  una nave concreta».
- `routines.json`: «TODOS son parámetros de diseño de EMMA: no se ha leído una fuente de NASA que
  fije la cadencia a bordo».
- `planner_leisure.json`: lista de palabras de ocio (decisión del usuario, 2026-11-12).
- Los umbrales de `location_sensing.json` (`window_s`, `margin_db`, `min_dwell_s`,
  `stale_after_s`, `min_rssi_dbm`): su base está en el documento de viabilidad. No se comprobó en
  esta pasada cuáles llevan fuente.

---

## 17. `backend/app/*.py` — módulos sueltos

Casi todos dan datos de EMMA a una herramienta de Polaris copiada tal cual (AGPL-3.0-or-later,
commit en `polaris/ADOPTADO.txt`). `anatomy.py`, `pain_on_skeleton.py` y `voice.py` ya se
documentaron en las ramas 7 y 12, y `main.py` en la 15.

| Módulo | Herramienta de Polaris | Qué hace en EMMA | Otras fuentes |
|--------|------------------------|------------------|---------------|
| `committee_bench.py` | `tools/score_local.py` (`puntuar`, por logprobs) | Mide si los verificadores locales distinguen un borrador correcto de uno que inventa | — |
| `committee_dossier.py` | `tools/paso_consolidacion.py` (`consolidar`) | Junta las objeciones del comité en un solo dosier | — |
| `decision_risk.py` | `tools/decision_alto_riesgo.py` (`disparar`) | Cuándo una decisión humana exige segunda firma | — |
| `countersign_rule.py` | (regla de EMMA sobre el cotejo de `fuente_clinica`) | Rechaza una contrafirma sobre una cita que no se localiza o que no se ha visto | Decisión del usuario, 2026-10-13 |
| `export.py` | `tools/md_to_pdf_pro.py` (con **reportlab**, BSD) | PDF con texto del backend | — |
| `kb.py` | `tools/kb.py` (SQLite FTS5, BM25) y `tools/kb_embed.py` (modelo **e5-small** en ONNX, MIT; ver la rama 16) | Busca en la documentación de EMMA sin red | `onnxruntime` (MIT) y `tokenizers` (Apache-2.0), según `pyproject.toml` |
| `memguard.py` | `tools/guarda_memoria.py` (`corre`) | Techo de memoria para procesos pesados; en Windows con `polaris/compat/memguard.py` | — |
| `routines.py` | `tools/estado_rutina.py` (`clasificar`) | Si cada medida periódica está al día | Las cadencias de `data/routines.json` son diseño, sin fuente |
| `text_guard.py` | Léxicos **adaptados** de `tools/honestidad_lint.py` y `tools/decision_alto_riesgo.py` (`NOTICE`) | Filtro de lenguaje de la invariante 7 en dos niveles (decisión del usuario, 2026-09-29) | — |
| `timeline.py` | `tools/cronica.py`, `cumbre.py`, `anticipa.py`, `cascada_mapa.py`, `seguimiento.py` | Crónica, «esta semana» y «qué depende de este dato» | Especificación del equipo (línea temporal) |
| `waiting.py` | `tools/atascos.py` (`esperan_por_titular`, `ESPERA_DIAS` = 3) y `seguimiento._manos` | Lo que espera por una persona | — |

Módulos sin código de terceros:

| Módulo | Fuente declarada |
|--------|------------------|
| `guides.py` | Enunciado del reto: «Do not assume that astronauts know everything about how to assess their health…» (`compliance/challenge-coverage.md`); los datos están en `measurement_guides.json` y `glossary.json` |
| `risk_entity.py` | Especificación §3 (entidad Riesgo: RIDGE, HRP, severidad, incertidumbre). No calcula nada nuevo |
| `sharing.py` | `data/data_sharing.json`; invariante 6 |
| `twins.py` | Base de conocimiento §10 (Human, Habitat, Mission y Countermeasure Twin, y la capa de decisión) |
| `planner_link.py`, `planner_ground.py` | Marplanner en loopback (`http://127.0.0.1:8790`) y `planner-bridge/ground-summary.mjs` (rama 22). Ocio según `planner_leisure.json` (decisión del usuario, 2026-11-12) |

### Sin fuente en el repo

- `ESPERA_DIAS = 3` es el de Polaris, sin cita.
- reportlab 5.0.1, **resuelto el 2026-11-14**: su `dist-info/licenses/LICENSE` es **BSD de 3 cláusulas** («Copyright (c) 2000-2024, ReportLab Inc.»). Trae además las fuentes Bitstream Vera, con su licencia (`reportlab/fonts/bitstream-vera-license.txt`), que se pueden redistribuir incluidas en software.

---

## 18. `backend/scripts/` y `backend/spikes/` — descargas, instalaciones y exploración de APIs

### Scripts que traen algo de fuera (todos por `core/egress.py` o con su comprobación de huella)

| Script | Qué trae | De dónde (según el script) | Comprobación |
|--------|----------|----------------------------|--------------|
| `fetch_mmash.py` | MMASH | `https://physionet.org/files/mmash/1.0.0/MMASH.zip` (ODbL v1.0) | — |
| `fetch_lifesnaps.py` | LifeSnaps, reducido a lo que se usa | Zenodo 7229547 (CC BY 4.0) | MD5 publicado por Zenodo |
| `fetch_hc18.py` | HC18 | Zenodo, doi:10.5281/zenodo.1327317 (CC BY 4.0) | MD5 publicado |
| `fetch_ct_samples.py` | Sujetos sueltos de TotalSegmentator por rangos HTTP | `https://zenodo.org/api/records/10047292/files/Totalsegmentator_dataset_v201.zip/content` | — |
| `build_volume_samples.py` | Los TAC de ejemplo del paquete | doi:10.5281/zenodo.10047292 | SHA-256 en el manifiesto |
| `extract_ultrasound_samples.py` | Ecografías de ejemplo | `https://doi.org/10.5281/zenodo.1009146` y `https://data.mendeley.com/datasets/hb3p34ytvx/2` | SHA-256 en el manifiesto |
| `fetch_donki_snapshot.py` | Instantánea de DONKI | api.nasa.gov | URL, fecha y licencia dentro del JSON |
| `fetch_spice_kernels.py` | Núcleos SPICE | NAIF (`https://naif.jpl.nasa.gov/naif/rules.html` para la licencia) | Tamaño y huella fijados en `spice.py` |
| `preload_ephemeris.py` | Efemérides de toda la misión | JPL Horizons | — |
| `grade_sources.py` | Registro de PubMed de cada fuente citada | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi` (adaptado de `tier_evidencia._fetch_pubmed` de Polaris, `NOTICE`) | — |
| `install_kb_embed.py` | Modelo e5-small en ONNX (decisión del usuario, 2026-10-04) | `https://huggingface.co/` (`intfloat/multilingual-e5-small`, MIT) | SHA-256 en `MODELO.json` |
| `install_voice.py` | Whisper `base`, `torch` CPU | `https://download.pytorch.org/whl/cpu` y la URL de Whisper | SHA-256 |
| `install_deid_ner.py` | Modelo NER de BSC | `https://download.pytorch.org/whl/cpu` y Hugging Face (acceso restringido, `HF_TOKEN`) | SHA-256 contra `SHA256_PESOS` |

### Scripts de copia y vigilancia de terceros

- `polaris_sync.py`, `polaris_left_out.py`, `polaris_tests.py` y `polaris_estado.py`: copia literal
  de Polaris, lo que se deja fuera, sus pruebas y su estado (rama 13).
- `marplanner_sync.py`: copia literal de Marplanner (rama 22).
- `deid_report.py`: recall de la des-identificación con el banco de pruebas de Polaris.
- `mutants.py`: cada defensa tiene una prueba que se pone roja al quitarla (`tests/mutants/`).

### Otros

- `anchor_gateway.py`: pasarela de balizas BLE con **`bleak`**, opcional (extra `[anchors]` de
  `pyproject.toml`). Su licencia no consta en el repo.
- `assistant_bench.py`: mide el asistente contra un backend vivo en loopback.

### `backend/spikes/` y `HALLAZGOS.md`

Exploración de cada API antes de escribir su cliente; los hallazgos (formatos y trampas) están en
`spikes/HALLAZGOS.md`:

| § | Spike | API |
|---|-------|-----|
| 1 | `spike_osdr.py` | OSDR Biodata |
| 2 | `spike_radlab.py` | OSDR RadLab |
| 3 | `spike_donki.py` | NASA DONKI |
| 4 | `spike_horizons.py` | JPL Horizons (astroquery) |
| 5 | `spike_ultrasound_data.py` | Datos ecográficos públicos |
| 6 | `spike_iswa.py` | CCMC iSWA (HAPI) |
| 7 | `spike_sscweb.py` | SSCweb |
| 8 | `spike_ntrs.py` | NASA NTRS |
| 9 | `spike_osdr_data.py` | Fichas de estudio de OSDR (2026-11-11) |
| 10 | `spike_spice.py` | NAIF SPICE frente a Horizons (2026-11-11) |

### Sin fuente en el repo

- ~~Licencias~~ **Resuelto el 2026-11-14**:
  - `torch`: Apache-2.0 (en `.venv-voice`). En `.venv-seg` está la build 2.11.0+cu128, que declara BSD-3-Clause.
  - `openai-whisper`: MIT.
  - `bleak`: **MIT**. No está instalado en `.venv`; lo dicen PyPI y libraries.io, que es fuente externa y no metadato local.
- **Corregido el 2026-11-14:** `fetch_ct_samples.py` sí calcula y guarda el SHA-256 de cada fichero extraído en su `manifest.json`, y `zipfile` comprueba el CRC32 de cada miembro. Lo que no hay es una huella **publicada** por sujeto con que compararla: Zenodo solo da el MD5 del zip entero. `preload_ephemeris.py` guarda respuestas de Horizons, que no tienen huella publicada; su contraste es SPICE (`comms_status`), que avisa si discrepan.

---

## 19. `frontend/` — consola de tripulación y consola de Tierra (React/TS)

Licencia del paquete: `AGPL-3.0-or-later` (`frontend/package.json`). Las reglas de la interfaz y sus
referentes están en `compliance/hmi-state-of-the-art.md`.

### Dependencias (`frontend/package.json`)

| Paquete | Versión | Para qué | Licencia según el repo |
|---------|---------|----------|------------------------|
| `react`, `react-dom` | ^19.3.0 | Interfaz | **MIT** (`node_modules/*/package.json`, 19.3.0) |
| `three` | 0.186.1 | Cuerpo 3D del mapa de dolor | **MIT** |
| `@niivue/niivue` | 0.69.0 | Visor de volúmenes | **BSD-2-Clause** |
| `uplot` | ^1.6.32 | Curvas | **MIT** |
| `@mediapipe/tasks-vision` | 1.2.2 | Vista que sigue la cara (demostración) | Apache-2.0 (`public/mediapipe/ORIGEN.txt`) |
| `vosk-browser` | 0.0.8 | Palabra de activación «EMMA» | **Apache-2.0** (`node_modules/vosk-browser/package.json`, leído el 2026-11-14) |
| `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` | ^5.3.0 | Tipografía | **SIL OFL 1.1** (`public/fonts/LICENSE-IBM-Plex-*-OFL-1.1.txt`) |
| De desarrollo: `vite` ^8.3, `vitest` ^5.0, `typescript` ^7.0, `@vitejs/plugin-react`, tipos | — | Compilar y probar | vite, vitest y plugin-react **MIT**; typescript **Apache-2.0** |
| esbuild 0.25.10 (el de Polaris, por `npm ci` en una carpeta temporal) | — | Compilar el visor de Polaris (`scripts/build-polaris.mjs`) | Del `package-lock.json` de Polaris |

### Modelos que viajan en `public/` (cada uno con `ORIGEN.txt` y su licencia al lado)

| Modelo | Origen | Huella | Licencia | Límite declarado |
|--------|--------|--------|----------|------------------|
| **MediaPipe Face Landmarker** float16 v1 (BlazeFace corto alcance, Face Mesh V2 de 478 puntos, Blendshape V2), `face_landmarker.task` | `https://storage.googleapis.com/mediapipe-models/face_landmarker/…/float16/1/face_landmarker.task`, descargado el 2026-11-03 | SHA-256 `64184e22…`, comprobado por `src/lib/faceModel.test.ts` | **Apache-2.0**, leída en las tres fichas de modelo de Google (Face Mesh V2: Geng Yan e Ivan Grishchenko, 15-sep-2022). Texto copiado de apache.org el 2026-11-03; anotado en `NOTICE` | No validado: es una demostración. Las fichas no hablan de microgravedad ni de cascos |
| **Vosk `vosk-model-small-es-0.42`** (Kaldi TDNN), de Alpha Cephei (AC Technologies LLC) | `https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip` (2026-11-03), reempaquetado en `.tar.gz` sin cambiar ficheros | zip `09b23988…`; tar.gz `bcbcc2dd…`, comprobado por `src/assistant/wake/voskModel.test.ts` | **Apache-2.0** según la tabla de modelos de Vosk (`https://alphacephei.com/vosk/models`, leída el 2026-11-03); «Copyright 2022-2050 AC Technologies LLC». Anotado en `NOTICE` | WER 16-17 % en Common Voice y MTEDx; 42,63 % en llamadas. Sin probar con personas |

### Normas y guías de interfaz

| Referencia | Qué se toma | Dónde |
|------------|-------------|-------|
| **NASA-STD-3001 Vol 2, Apéndice F** | Tabla de color F.5-1 (cian = dato caducado o ausente; gris = no disponible), F.5-2, cifras F.5.6, F.5.10 a, F.6.2, F.4.3.1 c | `src/lib/palette.ts`, `src/lib/format.ts` y unas 170 menciones a F.5-1 en `src/`. Pruebas en `npm test`. Desviaciones en `hmi-state-of-the-art.md` §2 (cian, parpadeo, coma decimal, silenciar una alarma) |
| **WCAG 2.x**: 1.4.6 (AAA, contraste ≥ 6:1 en EMMA), 1.4.11 (contraste no textual), 2.3.1 (destellos) | Contraste de la paleta y animaciones | `src/lib/palette.ts`, `orientation.ts`, `upAngle.ts`, `components/DisplayControls.tsx` |
| NASA-STD-3001 [V1 4030], Vol 1 | Unidades y límite de dosis en la interfaz | `src/radiation/` |
| ISO 8601 | Fechas | `src/lib/` |
| **ANSUR II** p50 (1,75 m, escalado a 1,73) | Proporciones del cuerpo 3D del dolor | `src/pain/bodyModel.ts` (comentarios). **ANSUR II** (US Army, encuesta de 2012). Informe NATICK/TR-15/007 en DTIC: «Approved for public release; distribution is unlimited»; CSV públicos `ANSUR II MALE/FEMALE Public.csv`. EMMA solo toma proporciones p50 y no redistribuye los datos. La licencia exacta de los CSV no consta (búsqueda del 2026-11-14) |
| BodyParts3D (CC BY 4.0, `https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html`) | Esqueleto de referencia | `src/pain/bodyModel.ts` (rama 7) |

**Referentes de diseño** (`hmi-state-of-the-art.md` §3): NASA Orion (Artemis II), SpaceX Crew
Dragon, Boeing Starliner, Blue Origin New Shepard, NASA Open MCT (Ames y JPL), consola BME del
Centro de Control de Houston y Astroskin / Bio-Monitor (CSA). Son comparación de diseño; no se
copia código de ninguno.

### La maqueta y su adorno (excepción declarada, `hmi-state-of-the-art.md` §2.5)

- **Maqueta «Panel EMMA: Rutas Espaciales y Salud»**: la dibujó el equipo como referencia (decisión
  del usuario, 2026-11-07). Fondo, planetas, astronauta, acentos RIDGE y el cuerpo de «Inicio» son
  adorno y no siguen la tabla F.5-1.
- `src/dashboard/referenceBody.generated.ts`: calco de los píxeles del cuerpo de la maqueta,
  generado por `referenceBodyMosaic.py`, ampliado ×4 con **Real-ESRGAN** (RRDBNet, pesos
  `RealESRGAN_x4plus.pth`, `referenceBodyUpscale.py`). Pesos y salida en `data/upscale/`, fuera de
  git. **Resuelto el 2026-11-14:** código de `https://github.com/xinntao/Real-ESRGAN`, **BSD 3-Clause** («Copyright (c) 2021, Xintao Wang», leído en su `LICENSE`). Los pesos salen de `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth`, y el SHA-256 del fichero local `4fa0d389…d682f1` coincide con el que publica una conversión en Hugging Face. El repositorio no declara una licencia aparte para los pesos. Ni los pesos ni el programa viajan en EMMA: solo la imagen ampliada, ya calcada.
- Colores térmicos del cuerpo 3D (`pain/thermalSkin.ts`) y espalda dibujada a mano
  (`pain/backSkin.ts`, `pain/backAnatomy/`): adorno derivado de la maqueta.
- Iconos (`src/icons/sets/`): no se encontró una nota de origen de terceros; parecen propios. No se
  comprobó en detalle.

### Sin fuente en el repo

- ~~Licencias npm~~ **Resuelto el 2026-11-14**, leídas en `node_modules/*/package.json`. `vosk-browser` 0.0.8 es **Apache-2.0**.
- ANSUR II: datos de publicación aprobada (DTIC); la licencia exacta de los CSV no consta. La página oficial (ph.health.mil) **no se pudo leer el 2026-11-14**: el nombre no resuelve desde aquí.
- Real-ESRGAN: el código es BSD-3; para los pesos el repositorio no dice nada aparte.
- La autoría y licencia de la maqueta: la dibujó el equipo, pero el repo no lo formaliza.

---

## 20. `desktop/` (+ `backend/packaging/`) — aplicación de escritorio para Windows

Licencia del paquete: `AGPL-3.0-or-later` (`desktop/package.json`).

### Herramientas

| Qué | Versión | Para qué | Dónde | Notas del repo |
|-----|---------|----------|-------|----------------|
| **Electron** | 44.4.5 (fijada) | Ventana; arranca el backend congelado en loopback | `desktop/main.cjs` | Se eligió frente a Tauri porque **Chromium va fijado** en cada versión e IEC 62304 pide identificar la versión de cada componente; WebView2 se actualiza solo (`hmi-state-of-the-art.md`). Sandbox, sin preload ni IPC, *fuses* endurecidos (`runAsNode: false`, integridad de asar). **MIT** (`node_modules/electron/package.json`) |
| **electron-builder** | 26.15.3 | Instalador NSIS (`npm run dist`, sale en `desktop/release/`) | `desktop/package.json` | **MIT** (`node_modules/electron-builder/package.json`) |
| **PyInstaller** | 6.22.3 | Congela el backend en `emma-backend`, desde un venv limpio (`build/venv-desktop`) y nunca desde `.venv` | `backend/packaging/freeze.py`, `hooks/` (p. ej. `hook-astropy.py`), `desktop/scripts/build-backend.mjs` | Excluye `pandas` y `matplotlib`; incluye `scipy` desde el 2026-10-04 (`tests/test_packaging.py`). **GPLv2 o posterior con excepción** para los ejecutables que genera (metadatos instalados, 2026-11-14) |
| Node + Marplanner | — | Planificador empaquetado (`build:planner` → `planner-bridge/build-marplanner.mjs`) | `desktop/build/marplanner` | Rama 22 |

### Qué viaja en el instalador (`extraResources`)

- Las licencias y avisos: `LICENSE`, `NOTICE` y, de Polaris, `LICENSE`, `NOTICE`, `CITATION.cff`,
  `ORIGEN.md`, `CAMBIOS.json`, `README.md`, `CHANGELOG.md`, `MANIFEST.sha256` y `ADOPTADO.txt`.
  Cumple la AGPL §4-5 al redistribuir.
- La interfaz compilada, el backend congelado, Marplanner con sus `node_modules`, los ficheros
  necesarios de `planner-bridge/` y `marplanner/ORIGEN.md`.
- Dentro del backend congelado: los núcleos SPICE comprobados, los datos de la rama 16 y los datos
  de Polaris que leen sus herramientas (`peripheries.json`, `normas.json`,
  `polaris_estado.checklist.json`, `orquestadores.json`).
- **No viajan:** TotalSegmentator, Whisper, la capa NER ni las herramientas de prueba. Ollama,
  Whisper, TotalSegmentator y Tesseract van en el **paquete de modelos**, aparte (ver «Modelos de IA»).

### Marca

`desktop/build/brand/`: logotipos y marcas `emma-logo-*` y `emma-mark-*` (SVG y PNG) e `icon.ico`.
Su `README.md` cuenta que se propusieron como borrador el 2026-11-04 (antes el instalador llevaba el
icono por defecto de Electron). Son propios de EMMA.

### Sin fuente en el repo

- ~~Licencias~~ **Resuelto el 2026-11-14**:
  - Electron 44.4.5: **MIT**.
  - electron-builder 26.15.3: **MIT**.
  - PyInstaller **6.22.3** (instalado en `.venv`): **GPLv2 o posterior con una excepción especial** que permite distribuir los ejecutables que genera bajo la licencia que se quiera. Al empaquetar EMMA con él, la licencia GPL no se extiende al ejecutable.
- ~~Avisos de terceros en el instalador~~ **Resuelto en código el 2026-11-14**: ver «Resumen de huecos», punto 2. Falta recompilar el instalador.

---

## 21. `compliance/` — las normas que cita EMMA, una por una

Cada fila dice **cómo se leyó** la norma. Varias son de pago y se citan solo en paráfrasis o desde
fuentes secundarias, y eso consta en el documento que las usa.

### Normas de NASA

| Norma | Documento oficial (URL del repo) | Cómo se leyó | Dónde se aplica |
|-------|----------------------------------|--------------|-----------------|
| **NASA-STD-3001 Vol 1 Rev C**, *Crew Health*, y Appendix D (matriz de cumplimiento) | `https://www.nasa.gov/wp-content/uploads/2023/11/nasa-std-3001-vol-1-rev-c-with-signature.pdf` y `https://www.nasa.gov/wp-content/uploads/2025/07/nasa-std-3001-vol-1-app-d-requirements-compliance-matrix.pdf` | Extraída del PDF oficial el 2026-09-20; «no se cita un ID de requisito que no se haya leído» | `nasa-std-3001-traceability.md`. Los requisitos aplicables y su número están en ese documento |
| **NASA-STD-3001 Vol 2 (Rev F)** y su **Apéndice F** (interfaz) | `https://www.nasa.gov/wp-content/uploads/2025/05/nasa-std-3001-vol-2.pdf`, `https://www.nasa.gov/reference/appendix-f-vol-2/` | PDF y página oficiales | Hábitat (rama 3), comida, interfaz (`hmi-state-of-the-art.md`) |
| Technical Briefs OCHMO (TB-002, TB-031, TB-035, MTB-009, MTB-013) | Fichas del registro (rama 6) | PDF oficiales, con fecha | Ramas 3, 4 y 5 |
| **NASA-STD-7009B** (2024) y NASA-HDBK-7009A (2019) | standards.nasa.gov | 7009B leída el 2026-10-23; el manual, solo portada y prólogo | Credibilidad de modelos (rama 6) |
| JSC 20584 Rev C (SMAC) y JSC 63414 Rev A (SWEG) | Fichas del registro | PDF oficiales | Hábitat (rama 3) |

### Software médico y riesgo

| Norma | Cómo la usa EMMA | Dónde | Cómo se leyó |
|-------|------------------|-------|--------------|
| **IEC 62304:2006/A1:2015** | Clasificación B, y C por elemento para el borrador y el visor 3D; ficha de SOUP (§4) | `software-safety-classification.md` | **Paráfrasis** de las cláusulas 4.3, 5.3.3 y 8.1.2. No se cita texto de la norma (de pago) |
| **ISO 14971:2019** | Archivo de gestión de riesgos (H1…H20) | `risk-management-file.md` | Paráfrasis del proceso |
| ISO 13485 | Solo para decir que **no** hay un sistema de calidad auditado: «conforme a», nunca «certificado» (invariante 6) | `software-safety-classification.md:832` | — |
| **IEC 60601-1-8** (alarmas de equipos electromédicos) | El cian y el parpadeo, y dónde chocan con NASA | `hmi-state-of-the-art.md` §2 | **De pago, no leída en original**: lo afirmado sale de fuentes secundarias, y así lo dice |

### Registro e integridad

| Norma | Qué se toma | URL del repo |
|-------|-------------|--------------|
| **21 CFR 11.10** (a), (e) | Registros alterados detectables; audit trail con hora | `https://www.law.cornell.edu/cfr/text/21/11.10` |
| **45 CFR 164.312** (c)(1), (c)(2) (HIPAA) | Integridad | `https://www.ecfr.gov/current/title-45/…/section-164.312` |
| 45 CFR 164.526 | Rectificación | `https://www.law.cornell.edu/cfr/text/45/164.526` |
| 45 CFR 164.514 | Des-identificación | — |
| **ISO 27789:2021**, *Audit trails for electronic health records* | Qué identifica cada asiento y qué dice una lápida | `https://www.iso.org/standard/75313.html`; muestra en `cdn.standards.iteh.ai` (solo la parte pública) |
| RFC 6962 | Árbol de Merkle | — (rama 1) |
| RFC 8785 (JCS) | No se usa; se nombra | — |
| HL7 FHIR R4 `AuditEvent`; IHE ATNA (formato heredado de RFC 3881) | Comparación del formato de auditoría | `https://hl7.org/fhir/R4/auditevent.html`, `https://profiles.ihe.net/ITI/TF/Volume1/ch-9.html` |
| CVE-2012-2459 | Fallo de Merkle que se corrigió | — |
| DICOM PS3.15, anexo E | Des-identificación de imagen (rama 8) | — |

### Accesibilidad

WCAG 2.2: 1.4.6, 1.4.11, 2.3.1 (`https://www.w3.org/TR/WCAG22/#three-flashes-or-below-threshold`) y
2.5.5 (objetivos de 44 px). Guía del Narrador de Windows (support.microsoft.com) para la prueba con
lector de pantalla.

### El reto y el estado del arte

- **Enunciado del reto**: `https://www.spaceappschallenge.org/2026/challenges/health-monitoring-software/`
  (`challenge-coverage.md`).
- `state-of-the-art.md`: Epic Sepsis Model (JAMA Intern Med) y otros sistemas comparables.
- Referentes de interfaz (§3 de `hmi-state-of-the-art.md`), con su fuente:
  - Orion: nasa.gov y ENSCO.
  - Crew Dragon: TechCrunch, InfoQ y Hackaday.
  - Starliner: NASASpaceflight.
  - New Shepard: Blue Origin.
  - Open MCT: `https://github.com/nasa/openmct`.
  - Consola BME: nasa.gov.
  - Astroskin / Bio-Monitor: CSA y Hexoskin.
- `location-sensing-feasibility.md`: fuentes de las balizas y anclas (NTRS y otras; rama 16).

### Sin fuente en el repo, o leído solo en parte

- IEC 62304, ISO 14971 e IEC 60601-1-8 no se han leído en su texto completo (son de pago). Se citan
  en paráfrasis o desde fuentes secundarias, y cada documento lo declara.
- NASA-HDBK-7009A: solo portada y prólogo.
- ISO 27789:2021: la muestra pública.

---

## 22. `marplanner/` y `planner-bridge/` — el planificador de a bordo

### Qué es y de dónde sale

| Campo | Valor según el repo |
|-------|---------------------|
| Proyecto | **Marplanner**: planificador doméstico autoalojado (calendario e ICS, rutinas y tareas, comidas, recordatorios, mensajes diarios, hoja diaria impresa, avisos hablados, copias de seguridad) |
| Autoría y licencia | © 2026 Diego Mariño, **MIT** (`marplanner/LICENSE`), compatible con la AGPL de EMMA (`NOTICE`) |
| Repositorio | `https://github.com/diegomarino/marplanner` |
| Commit copiado | `6c061d43e3dc39476ad9238c1823b09257a831f3` (desde el 2026-11-12), en `marplanner/ADOPTADO.txt` |
| Copia | Literal, la hace `backend/scripts/marplanner_sync.py` y la vigila `backend/tests/test_marplanner_copy.py` (`MANIFEST.sha256`). **Fuera**: `.github`, `.do`, `render.yaml`, `railway.json` e `infra/fly` (CI y despliegue en la nube) |
| Entorno | Servicio Node aparte, solo en loopback (`:8790`). Node 26 (el commit pide `>=24.21 <25`; se usa 26 por decisión del usuario) |

### Terceros que trae Marplanner (`marplanner/THIRD_PARTY_NOTICES.md`)

| Recurso | Licencia | Notas |
|---------|----------|-------|
| JetBrains Mono (fuente del renderizador de la hoja diaria) | SIL OFL 1.1 | `github.com/JetBrains/JetBrainsMono` |
| Weather Icons (Erik Flowers) | SIL OFL 1.1 | El tiempo está apagado en EMMA |
| «Win Jingle» (Fupi, opengameart.org) | CC0 1.0 | — |
| `trivia-questions.json` (Open Trivia Database) | **CC BY-SA 4.0** | Se distribuye con la misma licencia |
| `vocabulary-entries.json` (Free Dictionary API → Wiktionary) | **CC BY-SA 3.0** | — |
| `number-facts.json` y su traducción `.es` | **Sin licencia publicada** por la fuente (repite la Numbers API retirada) | Revisar antes de redistribuir |
| `word-search-corpus.json` (Datamuse API) | Reconocimiento a la fuente | — |
| Avatar de freesvg.org | Según freesvg.org | — |
| Dependencias npm (`fastify` 5.12.8, `better-sqlite3` 13.0.3, `drizzle-orm`, `argon2` 0.45.2, `@resvg/resvg-js` 2.6.2, `node-ical` 0.27.3, Radix UI, Schedule-X, dnd-kit, `lucide-react`, `pressedslip`…) | Las de su `package-lock.json` | Cada compilación de Marplanner escribe `THIRD_PARTY_LICENSES.txt` junto a cada paquete (`scripts/bundled-licenses.mjs`) |

### Lo que pone EMMA (`planner-bridge/`, código de EMMA y fuera de la copia)

- **Base de datos en el ledger** (decisión del usuario, 2026-11-12): sustituye `better-sqlite3`
  por SQLite en memoria (`node:sqlite`) y anota cada transacción en `POST /api/planner/changesets`
  antes del COMMIT (`compliance/record-integrity.md` §3.31). Al arrancar reproduce el ledger.
  Ficheros: `register.mjs`, `better-sqlite3.mjs`, `ledger-client.mjs` y `ledger-worker.mjs`.
- **Salidas a internet por la puerta de EMMA** (`egress.mjs`, `undici.mjs`):
  - Open-Meteo, UniFi Cloud y los feeds ICS: **no salen**.
  - ZenQuotes (`planner-quotes`) y Wikipedia «tal día» (`planner-onthisday`): solo con red y por la
    lista blanca.
- **Windows** (`compat-windows.mjs`): `fsync` sin EPERM.
- **Resumen para Tierra** (`ground-summary.mjs`, `summary-*.mjs`): lo que llega con el retardo
  (`app/planner_ground.py`).
- Suite de Marplanner con el puente (2026-11-12): las que fallan son de plataforma o de lo excluido.
  El detalle está en `marplanner/ORIGEN.md`.

### Sin fuente en el repo, o por revisar

- `number-facts.json`: la fuente no publicó licencia de datos. **Comprobado otra vez el 2026-11-14, en las fuentes primarias:**
  - `number-trivia.com` rechaza la conexión.
  - `numbersapi.com` sirve el certificado de otro dominio (`amanahtrader.uk`).
  - No hay repositorio `numbersapi` en la cuenta de su autor (`github.com/divad12/numbersapi`, 404).
  - Solo directorios de terceros (apis.io y similares) le atribuyen «MIT» o «free for any use», sin citar un fichero de licencia del proyecto, y no coinciden entre sí.
  - Sigue sin licencia verificable.
- Los corpus CC BY-SA obligan a compartir con la misma licencia si se modifican.
- ~~El texto de licencias de las dependencias de Marplanner~~ **Resuelto el 2026-11-14**: la compilación deja `desktop/build/marplanner/server/THIRD_PARTY_LICENSES.txt`, y `build/marplanner` viaja entero en `extraResources`. (Texto anterior:) depende de su compilación
  (`THIRD_PARTY_LICENSES.txt`). No se comprobó que el instalador de EMMA lo lleve.

---

## Modelos de IA: de dónde se descargó cada uno (vista transversal, 2026-11-15)

Reúne en un sitio lo que las ramas 9-12, 16, 18 y 19 dicen por separado. Sale de los scripts de
instalación, de los `ORIGEN.txt`/`MODELO.json` y de lo que había instalado en el portátil de
desarrollo el 2026-11-15 (`ollama list`, `~/.totalsegmentator`, los `.venv-*`).

**Dónde vive cada uno no es casual.** Solo van en git los modelos pequeños que la aplicación
necesita siempre y que tienen una licencia que permite redistribuirlos. Los pesados u opcionales
quedan fuera a propósito (`CLAUDE.md`: «lo que depende de ellos tiene que declararse no disponible
cuando faltan, no romper el arranque»), y se reinstalan con su script o con `ollama pull`.

### En git, y viajan en el instalador

| Modelo | Para qué | Descargado de | Dónde | Huella | Licencia |
|--------|----------|---------------|-------|--------|----------|
| `intfloat/multilingual-e5-small`, ONNX int8 + tokenizer, revisión `614241f6…` | Búsqueda semántica (`kb_embed` de Polaris) | `https://huggingface.co/intfloat/multilingual-e5-small/resolve/<rev>/onnx/…` con `scripts/install_kb_embed.py` | `backend/app/data/kb-model/` | SHA-256 en `MODELO.json` | MIT |
| MediaPipe Face Landmarker float16 v1 | Vista que sigue la cara (demostración) | `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task` (2026-11-03) | `frontend/public/mediapipe/` | `ORIGEN.txt`, comprobado por `faceModel.test.ts` | Apache-2.0 |
| Vosk `vosk-model-small-es-0.42` | Palabra de activación del asistente | `https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip` (2026-11-03), reempaquetado en `.tar.gz` | `frontend/public/vosk/` | comprobado por `voskModel.test.ts` | Apache-2.0 |

### Fuera de git: programas externos opcionales (no viajan; sin ellos, «no disponible»)

| Modelo | Para qué | Descargado de | Dónde | Licencia |
|--------|----------|---------------|-------|----------|
| Whisper `base` (`openai-whisper==20250625`) | Transcripción de voz | `https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b…/base.pt` (URL fijada en el paquete `whisper`, que comprueba el SHA-256) con `scripts/install_voice.py`. PyTorch CPU de `https://download.pytorch.org/whl/cpu` | `backend/.venv-voice/cache/whisper/base.pt` | **Sin anotar** (pesos) |
| `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`, revisión `83db1112…` | Des-identificación NER de informes | Hugging Face (`snapshot_download`) con `scripts/install_deid_ner.py`; revisión y SHA-256 de los pesos fijados en `polaris/tools/deid_ner.py` | Caché de `backend/.venv-deid` | **Sin anotar**: el repo no es público (401) |
| TotalSegmentator 2.18.0: tareas Dataset291-295, 297, 298 (`total`, 3 mm, 6 mm), 570 `liver_segments`, 591 `liver_lesions` y 008 `HepaticVessel` | Segmentación de TAC/RM | Los descarga el propio TotalSegmentator (paquete de PyPI instalado en `.venv-seg`) | `~/.totalsegmentator/nnunet/results/` | Apache-2.0 (rama 9) |
| Tesseract `eng`, `osd`, `spa` (`tessdata_fast`) | OCR de informes escaneados | `https://github.com/tesseract-ocr/tessdata_fast` (`spa` añadido el 2026-11-14) | `C:\Program Files\Tesseract-OCR\tessdata\` | Apache-2.0 |

### Fuera de git: Ollama (registro `ollama.com`, `ollama pull`; servidor local en loopback)

Configurados en `app/core/config.py`: `gemma4:e4b` (redactor y voz, `llm_model`),
`gemma4:12b-it-qat` (verificador, `llm_verifiers`) y `qwen3.5:9b` (asistente, `assistant_model`).
Instalados para comparativas, sin uso fijo: `qwen3.5:4b`, `gemma4:e2b`, `ministral-3:8b`,
`qwen3-vl:4b-instruct`, `qwen3-vl:8b-instruct`. Todos Apache-2.0 según `ollama show --license`
(rama 11). **`emma-qwen3.5-9b-v2`**: derivado local; su origen no consta en el repo.

### Fuera de git: solo en desarrollo (no lo usa la aplicación)

| Modelo | Para qué | Descargado de | Dónde | Licencia |
|--------|----------|---------------|-------|----------|
| Real-ESRGAN `RealESRGAN_x4plus.pth` | Ampliar ×4 la maqueta del cuerpo de «Inicio» (solo viaja la imagen ya calcada) | `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth` | `data/upscale/` | Código BSD-3; pesos sin licencia aparte (rama 19) |

### El paquete de modelos (decisión del usuario, 2026-11-15)

Los modelos de fuera de git se instalan con EMMA como un **paquete aparte**, desde disco o USB y
sin red. Lo construye `backend/packaging/models_pack.py` con lo que está probado en la máquina que
lo crea (no descarga nada): `ollama/` (programa sin la aplicación de bandeja, y solo los modelos
configurados más los pedidos con `--ollama-model`), `voice/`, `segmentation/` y `tesseract/`.
Whisper y TotalSegmentator van sobre una **copia de Python** aislada con `python312._pth`, porque
un venv lleva escrita la ruta del Python de la máquina que lo creó. El script arranca cada pieza
ya copiada antes de dar el paquete por bueno, y escribe `MANIFIESTO.json` (tamaño y SHA-256 de
cada fichero, versión, origen y licencia por pieza).

`instalar.cmd` copia el paquete a `%LOCALAPPDATA%\EMMA-modelos` (o `-Destino`), comprueba cada
huella ya en el destino y solo entonces escribe `instalado.json`. La aplicación de escritorio
(`desktop/main.cjs`, `modelsEnv`) solo usa un paquete con esa marca: arranca su Ollama en un puerto
propio de loopback y pasa al backend las rutas de cada pieza. Sin paquete, todo sigue «no
disponible» como antes.

**No va en el paquete** la capa NER del BSC: sin licencia que permita redistribuirla.

### Pendiente

- El origen de `emma-qwen3.5-9b-v2`, y anotarlo.
- La licencia de los pesos de Whisper `base` y la del modelo NER del BSC.

---

## Resumen de huecos (primera vuelta y su resolución, 2026-11-14)

| # | Hueco | Estado |
|---|-------|--------|
| 1 | Licencias sin anotar | **Resuelto en su mayoría**. Python leído de los metadatos instalados en los cuatro entornos y JS de `node_modules`; tesseract de su `LICENSE`; modelos de Ollama con `ollama show --license`; Real-ESRGAN, bleak y ANSUR II por búsqueda. **Queda:** el modelo NER de BSC (su página responde 401), los pesos de Whisper `base` y los tres modelos no instalados |
| 2 | Avisos de terceros en el instalador | **Resuelto el 2026-11-14** (código, sin compilar el instalador). `backend/packaging/third_party.py` escribe `THIRD_PARTY_LICENSES.txt` junto al backend congelado, al final de `freeze.py`. `frontend/scripts/third-party.mjs` lo escribe en `frontend/dist/` al final de `npm run build`. Los dos copian el texto de licencia que trae cada paquete, y los dos viajan ya en `extraResources`. Pruebas: `tests/test_third_party_notices.py` y `src/lib/thirdPartyNotices.test.ts`. Electron y Chromium ya traían los suyos (`LICENSE.electron.txt`, `LICENSES.chromium.html`, comprobado en `desktop/release/win-unpacked/`). **Falta** recompilar el instalador para que los lleve |
| 3 | Normas de pago no leídas (IEC 62304, ISO 14971, IEC 60601-1-8) | **No se resuelve buscando**: hay que comprarlas. Sigue declarado así en cada documento |
| 4 | Parámetros de diseño sin fuente | **No es un hueco de fuente, es diseño declarado.** Buscarles una cita a posteriori sería justo lo que `CLAUDE.md` prohíbe. Se quedan como «diseño de EMMA» |
| 5 | Dos parámetros `established` con fuente genérica | **Resuelto**: enlazados a Barger 2014 y Basner 2011 en `ingest/simulator.py`, con sus fichas |
| 6 | Datos sin licencia clara (`number-facts.json`, maqueta) | `number-facts.json`: **decisión del usuario** (2026-11-14): se deja como está; su licencia se buscó en las fuentes originales, que ya no existen. Maqueta: **pendiente del usuario** (autor y licencia) |
| 7 | Descargas sin huella | **Corregido el diagnóstico**: `fetch_ct_samples.py` sí guarda SHA-256 y CRC; Horizons se contrasta con SPICE |

**Hallazgos nuevos al resolver:**
- ~~Faltaba `spa.traineddata` en tesseract~~ **Arreglado el 2026-11-14** (rama 10).
- Los modelos por defecto del borrador (`qwen3.6:35b-a3b`, `gemma4:latest`) no están instalados en
  esta máquina.

---

## Identificadores de las citas por autor (2026-11-14)

Muchas secciones nombran un estudio por «autor y año». Su DOI y su PMID, comprobados al crear cada ficha, están en el registro de evidencia; aquí se cruzan para que ninguna cita quede sin referencia. La fuente de verdad sigue siendo `backend/app/data/evidence_refs.json`.

| Ficha | Primer autor (año) | Título | DOI | PMID |
|---|---|---|---|---|
| `agha-2020-salivary-iss` | — (2020) | Salivary antimicrobial proteins and stress biomarkers are elevated during a 6-month mission to the International Space Station | 10.1152/japplphysiol.00560.2019 | 31751178 |
| `badhwar-1992-sls1-tepc` | Badhwar GD (1992) | Dose rate, dose-equivalent rate, and quality factor in SLS-1 | 10.1016/1359-0189(92)90030-y | 11537535 |
| `baevsky-1997-holter-mir` | — (1997) | Adaptive responses of the cardiovascular system to prolonged spaceflight conditions: assessment with Holter monitoring | — | 11539935 |
| `baevsky-2007-autonomic-iss` | — (2007) | Autonomic cardiovascular and respiratory control during prolonged spaceflights aboard the International Space Station | 10.1152/japplphysiol.00137.2007 | 17446414 |
| `barger-2014-sleep-spaceflight` | Barger LK (2014) | Prevalence of sleep deficiency and use of hypnotic drugs in astronauts before, during, and after spaceflight: an observational study | 10.1016/S1474-4422(14)70122-X | 25127232 |
| `basner-2011-pvt-metrics` | Basner M (2011) | Maximizing Sensitivity of the Psychomotor Vigilance Test (PVT) to Sleep Loss | 10.1093/sleep/34.5.581 | 21532951 |
| `basner-2011-pvt-b` | Basner M (2011) | Validity and Sensitivity of a Brief Psychomotor Vigilance Test (PVT-B) to Total and Partial Sleep Deprivation | 10.1016/j.actaastro.2011.07.015 | 22025811 |
| `basner-2015-cognition-battery` | Basner M (2015) | Development and Validation of the Cognition Test Battery for Spaceflight | 10.3357/AMHP.4343.2015 | 26564759 |
| `brown-2022-melanopic-light` | Brown TM (2022) | Recommendations for daytime, evening, and nighttime indoor light exposure to best support physiology, sleep, and wakefulness in healthy adults | 10.1371/journal.pbio.3001571 | 35298459 |
| `buchheim-2019-inflammaging-cosmonauts` | — (2019) | Stress Related Shift Toward Inflammaging in Cosmonauts After Long-Duration Space Flight | 10.3389/fphys.2019.00085 | 30873038 |
| `christian-2024-hdtbr-co2-sleep` | Christian KH (2024) | Development of optic disc edema during 30 days of hypercapnic head-down tilt bed rest is associated with short sleep duration and blunted temperature amplitude | 10.1152/japplphysiol.00211.2023 | 38357726 |
| `dev-2024-cognition-iss` | — (2024) | Cognitive performance in ISS astronauts on 6-month low earth orbit missions | 10.3389/fphys.2024.1451269 | 39633651 |
| `fraser-2012-heart-rate-iss` | Fraser KS (2012) | Heart rate and daily physical activity with long-duration habitation of the International Space Station | 10.3357/asem.3206.2012 | 22764612 |
| `gundel-1998-co2-sleep` | Gundel A (1998) | Joint NASA-ESA-DARA Study. Part three: characterization of sleep under ambient CO2-levels of 0.7% and 1.2% | — | 9591620 |
| `hardy-2025-spaceflight-standard-measures` | Hardy JG (2025) | Spaceflight Standard Measures is a multidisciplinary study that systematically monitors risks to astronaut health and performance | 10.1038/s41526-025-00532-6 | 41224762 |
| `hughson-2012-cardiovascular-iss` | Hughson RL (2012) | Cardiovascular regulation during long-duration spaceflights to the International Space Station | 10.1152/japplphysiol.01196.2011 | 22134699 |
| `law-2014` | Law J. (2014) | Relationship between carbon dioxide levels and reported headaches on the International Space Station | 10.1097/JOM.0000000000000158 | 24806559 |
| `manzey-1998-co2-performance` | Manzey D (1998) | Joint NASA-ESA-DARA Study. Part three: effects of chronically elevated CO2 on mental performance during 26 days of confinement | — | 9591623 |
| `marshall-goebel-2019-ijv` | Marshall-Goebel K (2019) | Assessment of Jugular Venous Blood Flow Stasis and Thrombosis During Spaceflight | 10.1001/jamanetworkopen.2019.15011 | 31722025 |
| `mehta-2017-latent-virus-iss` | Mehta SK (2017) | Latent virus reactivation in astronauts on the international space station | 10.1038/s41526-017-0015-y | 28649633 |
| `norsk-2015-ambulatory-bp-iss` | Norsk P (2015) | Fluid shifts, vasodilatation and ambulatory blood pressure reduction during long duration spaceflight | 10.1113/jphysiol.2014.284869 | 25774397 |
| `otsuka-2016-hrv-time-structure` | Otsuka K (2016) | Long-term exposure to space's microgravity alters the time structure of heart rate variability of astronauts | 10.1016/j.heliyon.2016.e00211 | 28050606 |
| `otsuka-2022-one-year-hrv` | — (2022) | Unconscious mind activates central cardiovascular network and promotes adaptation to microgravity possibly anti-aging during 1-year-long spaceflight | 10.1038/s41598-022-14858-8 | 35831420 |
| `satish-2012-co2-decision-making` | Satish U (2012) | Is CO2 an indoor pollutant? Direct effects of low-to-moderate CO2 concentrations on human decision-making performance | 10.1289/ehp.1104789 | 23008272 |
| `scully-2019` | Scully R.R. (2019) | Effects of acute exposures to carbon dioxide on decision making and cognition in astronaut-like subjects | 10.1038/s41526-019-0071-6 | 31240239 |
| `smith-2005-bone-markers-mir` | Smith SM (2005) | Bone markers, calcium metabolism, and calcium kinetics during extended-duration space flight on the mir space station | 10.1359/JBMR.041105 | 15647814 |
| `smith-2012-bone-resistance-iss` | — (2012) | Benefits for bone from resistance exercise and nutrition in long-duration spaceflight: Evidence from biochemistry and densitometry | 10.1002/jbmr.1647 | 22549960 |
| `van-hoy-2026-co2-sleep-analog` | Van Hoy SE (2026) | Environmental Carbon Dioxide and Temperature Effects on Sleep Quality During Space Analogs | 10.3357/AMHP.6410.2026 | 41461188 |
| `vorobiev-1995-altair-mir` | — (1995) | Blood volume regulating hormones, fluid and electrolyte modifications during 21 and 198-day space flights (Altair-MIR 1993) | 10.1016/0094-5765(95)00164-6 | 11541010 |
| `zwart-2018-dietary-acid-load` | — (2018) | Dietary acid load and bone turnover during long-duration spaceflight and bed rest | 10.1093/ajcn/nqy029 | 29722847 |

Fuera del registro, con su identificador leído en el código o comprobado el 2026-11-14 en PubMed (E-utilities). Comprobado también el mismo día: las 7 fichas del registro que tienen PMID y declaran el DOI como «no aplica» (Baevsky 1997, Manzey 1998, Gundel 1998, Grigoriev 1994, Strollo 1997 y 1998, Morey-Holton 1988) no tienen DOI en PubMed. Son revistas de 1988 a 1998, así que la declaración es correcta:

| Cita | Dónde | Identificador |
|---|---|---|
| Helmke K, Hansen HC. Pediatr Radiol 1996 | `imaging/measure.py` | PMID 8805599 |
| Crit Care Med 2025 | `ingest/codes.py`, `imaging/measure.py` | PMID 40459386 |
| Lichtenstein DA, Mezière GA. Chest 2008 | `imaging/protocols.py` | PMID 18403664 |
| Hamilton DR et al. Aviat Space Environ Med 2004 | `imaging/protocols.py` | PMID 15018297 |
| Sargsyan AE et al. J Trauma 2005 | `imaging/protocols.py` | PMID 15674147 |
| Daum N et al. Z Gastroenterol 2026 | `imaging/protocols.py` | PMID 42161258 |
| Kerstman et al. Aviat Space Environ Med 2012 | `pain/__init__.py` | PMID 22272509 |
| Serlin et al. Pain 1995 | `pain/alarm.py` | PMID 7659438 |
| Rousseeuw PJ, Croux C. J Am Stat Assoc 1993 | `analysis/baseline.py` (constante 1,4826) | doi:10.1080/01621459.1993.10476408 (Crossref) |
| Marzola F et al. *Development of a Deep Learning-Based System for Optic Nerve Characterization in Transorbital Ultrasound Images on a Multicenter Data Set*. Ultrasound Med Biol 2023;49:2060-2071 | `compliance/imaging-data-provenance.md` (descartado) | PMID 37357081, doi:10.1016/j.ultrasmedbio.2023.05.011 |
| Loehr et al. 2015, citado por OCHMO-TB-031 p. 10 | `data/countermeasures.json` (`bone-resistive-load`) | **Resuelto el 2026-11-14:** Loehr JA, Guilliams ME, Petersen N, Hirsch N, Kawashima S, Ohshima H. *Physical Training for Long-Duration Spaceflight*. Aerosp Med Hum Perform 2015;86(12 Suppl):A14-A23, PMID 26630191, doi:10.3357/AMHP.EC03.2015. Confirmado en el propio OCHMO-TB-031 (PDF oficial, leído ese día): la p. 10 dice «Adapted from: Physical Training for Long-Duration Spaceflight (Loehr et al., 2015)» y su referencia 6 es ese artículo |
| Wasserthal J et al. Radiol Artif Intell 2023;5(5):e230024 | `volumes/` | Datos: doi:10.5281/zenodo.10047292 |
| van den Heuvel et al. PLoS ONE 2018;13(8):e0200412; Byra M et al. Int J CARS 2018; Katumba A et al. Data in Brief 2025 | `imaging/` | DOI en la rama 8 |
