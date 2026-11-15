# Hallazgos de los spikes de APIs externas

Ejecutados el 2026-09-20. Todos contra las APIs reales, sin autenticación salvo donde se indica.
Estos hallazgos son los que deben guiar la implementación de `app/environment/`.

---

## 1. OSDR Biodata API — `spike_osdr.py`

**Base:** `https://visualization.osdr.nasa.gov/biodata/api/v2` · sin autenticación

- `GET /dataset/OSD-288/` → `{"OSD-288": {REST_URL, assays, files, metadata}}`.
  El accession es **la clave del objeto raíz**, no un campo. Hay que indexar por él.
- OSD-288 confirmado: ensayo `OSD-288_transcription-profiling_rna-sequencing-(rna-seq)_Illumina`.
- `GET /query/datasets/?study.factor value.spaceflight=in-flight` → CSV, 7 filas.

**⚠ Los valores de factor NO están normalizados.** La misma consulta devuelve `"in-flight"` y
`"In-flight"`. La capa de evidencia debe comparar sin distinguir mayúsculas, o perderá estudios.

---

## 2. OSDR RadLab — `spike_radlab.py`

**Base:** `https://visualization.osdr.nasa.gov/radlab/api` · sin autenticación

**⚠ CRÍTICO: una consulta sin filtro temporal devolvió 434 987 322 bytes (≈435 MB).**
El cliente de producción debe acotar *siempre* por rango de `timestamp`. El spike lleva un
corta-circuitos de 8 MB para no repetirlo.

Reglas de sintaxis confirmadas por error del servidor:

- `fields+=...` **exige** la forma booleana `query=(a=b)AND(c>=d)`. Mezclarlo con el estilo
  clave-valor da `500: If specifying 'fields+=...', must pass 'query=...'`.
- **Sin `fields+=` no llega ninguna columna de dosis** — solo `timestamp`, `instrument_id`,
  `instrument`, `spacecraft`. Es decir: `fields+=` es obligatorio para obtener datos útiles.

Formato de respuesta JSON: `{"columns": [...], "index": [...], "data": [[...]]}`
(estilo pandas *split*), **no** una lista de objetos.

Consulta que funciona:

```
/api/?query=(spacecraft=ISS)AND(instrument=DosTel)AND(timestamp>=2022-04-01)AND(timestamp<=2022-04-02)
     &fields+=absorbed_dose_rate&format=json
```

→ 2391 filas / 156 KB para un día. Cadencia de 10 s. Dos instrumentos: `DosTel1`, `DosTel2`.
Valores de `absorbed_dose_rate` ≈ 2,0 (µGy/h).

**Pendiente:** `dose_equivalent_rate` se solicitó y **no** apareció en las columnas devueltas.
Hay que averiguar si DosTel no lo expone o si el nombre del campo difiere.

---

## 3. NASA DONKI — `spike_donki.py`

**Base:** `https://api.nasa.gov/DONKI` · requiere `api_key` (`DEMO_KEY` sirve para desarrollo)

Los tres endpoints responden bien y con datos abundantes:

| Endpoint | Ventana probada | Eventos |
|---|---|---|
| `SEP` | 365 días | 59 |
| `FLR` | 60 días | 39 |
| `CME` | 30 días | 137 |

Campos útiles confirmados:

- **SEP**: `sepID`, `eventTime`, `instruments`, `linkedEvents`, `sentNotifications`.
  `linkedEvents` encadena el SEP con la CME que lo originó → permite reconstruir la cascada completa.
  `sentNotifications` trae **los mensajes de alerta reales de NASA**, con `messageIssueTime`.
- **FLR**: `classType` (p. ej. `M3.6`) → clase de fulguración, directamente utilizable para severidad.
  `beginTime` / `peakTime` / `endTime`, `sourceLocation`, `activeRegionNum`.
- **CME**: `cmeAnalyses`, `startTime`, `sourceLocation`.

**Nota:** los SEP son escasos. Una ventana de 30 días puede devolver cero. Para la demo hay que
cachear un periodo con eventos reales, no confiar en "los últimos 30 días".

---

## 4. JPL Horizons vía astroquery — `spike_horizons.py`

**Módulo:** `astroquery.jplhorizons` (astroquery 0.4.11, astropy 8.0.1)

- **⚠ Horizons no devuelve tabla si `start == stop`.** Falla con un error opaco
  (`Query failed without known error message`) mientras imprime la ficha física del objeto.
  Hay que pedir una ventana real y quedarse con la primera fila.
- La tabla `ephemerides()` trae **`lighttime` ya calculado en minutos** — no hace falta derivarlo
  de `delta`. El cálculo manual (`delta × 499,004783836 s/UA`) coincide exacto, así que sirve como
  verificación cruzada independiente.
- También existe la columna `earth_lighttime`, a revisar para escenarios con la nave fuera del
  sistema Tierra-Marte.

Valores medidos (Marte desde geocentro `500@399`, objetivo `499`):

| Fecha | Distancia | Ida | Ida y vuelta |
|---|---|---|---|
| 2027-02-19 (oposición afélica) | 0,678 UA | 5,64 min | 11,28 min |
| 2028-02-10 (cerca de conjunción) | 2,348 UA | 19,53 min | 39,06 min |
| **2026-11-14 (día del hackathon)** | **1,324 UA** | **11,01 min** | **22,03 min** |

Nota: la oposición de febrero 2027 es afélica (0,678 UA), no de las cercanas (≈0,37 UA), por eso da
5,64 min y no los ~3 min del mejor caso. El rango completo Tierra-Marte va de ~3 a ~22 min de ida.

---

## 5. Datos ecográficos públicos — `spike_ultrasound_data.py`

Ejecutado el 2026-09-24. Objetivo: saber si hay ecografías con las que validar la ecografía a
bordo, idealmente de la NASA, y bajo qué licencia.

**⚠ La NASA no publica imágenes ecográficas, ni de tripulación ni de animales.**

- OSDR/ALSDA, búsqueda de texto libre (un índice por petición: con varios separados por comas la
  API no devuelve `total`): "ultrasound" y "sonography" solo dan **OSD-435**, ecocardiografía de
  ratones irradiados en tierra. Sus ficheros son **tablas de medidas derivadas (CSV)**, sin
  imágenes. `OSD-401` aparece por texto, pero es RNA-Seq de músculo.
- "optic nerve sheath" da OSD-363/364 (expresión génica, hipertensión intracraneal) y OSD-815 a
  818 (tejido humano *ex vivo* para SANS). Ninguno contiene ecografía.
- Los datos de astronautas en OSDR son procesados o de acceso controlado. La ecografía orbital y
  yugular hecha en la ISS no está publicada como imagen.

**Datasets abiertos candidatos (Zenodo), licencia leída en el registro de origen:**

| Registro | Contenido | Licencia | Utilidad |
|---|---|---|---|
| 10.5281/zenodo.1327317 (HC18) | Modo B fetal, **mm/píxel por imagen** y perímetro de referencia en mm | CC BY 4.0 | Valida el **motor de medida calibrada**, no fisiología espacial |
| 10.5281/zenodo.1009146 | Hígado en modo B, grado de esteatosis | CC BY 4.0 | Protocolo hepático; sin calibración declarada |

**Descartados:** el dataset multicéntrico de nervio óptico (Marzola et al., 2023) no tiene
repositorio ni licencia de datos publicados. Las etiquetas del dataset POCUS de pulmón son
CC BY-NC 4.0 y muchos de sus vídeos no se pueden redistribuir. No hay dataset abierto de vejiga ni
de yugular.

Consecuencia de diseño: como con MMASH, un dataset terrestre valida el motor, no la deriva en
vuelo. Detalle y reglas en `compliance/imaging-data-provenance.md`.

---

## 6. CCMC iSWA por HAPI — `spike_iswa.py`

Ejecutado el 2026-11-11. **Base:** `https://iswa.gsfc.nasa.gov/IswaSystemWebApp/hapi` (NASA
Goddard, Community Coordinated Modeling Center). **Sin clave**, HAPI 2.0, salida `csv` (por
defecto) o `json`. El catálogo tiene 327 conjuntos; los útiles para EMMA:

| Conjunto | Qué | Cadencia | Unidades de la ficha | Relleno |
|---|---|---|---|---|
| `goesp_part_flux_P5M` | GOES primario: canales de protones P1…P500 y electrones | 5 min | `Protons/cm^2 - s^-1 - sr` (= pfu) | `-100000` |
| `swpc_rtsw_plasma_P1M` | Viento solar en tiempo real de NOAA SWPC: densidad, velocidad, temperatura, `source` | 1 min | `p/cc`, `km/s`, `K` | `-9999` |

- **El dato es de NOAA (GOES y RTSW), redistribuido por la NASA (iSWA).** El canal `P10` coincide
  **valor a valor** con la serie integral ≥10 MeV de NOAA SWPC
  (`services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json`, consultada una vez en
  este spike solo para cotejar; EMMA no se conecta a NOAA). La ficha HAPI no escribe «integral
  ≥10 MeV»: se sabe por ese cotejo y porque P1, P5, P10, P30, P50, P100, P60 y P500 son los canales
  integrales de GOES.
- Retraso: el `stopDate` va unos 10 min por detrás del reloj. La consulta puede ser de ahora y la
  última muestra, no: hay que declarar las dos edades.
- SPE del 2024-05-11: máximo de P10 ese día, 116 pfu (por encima de S1, 10 pfu, y de S2, 100 pfu,
  de la escala de NOAA). En calma (2026-11-11), unos 0,2 pfu.
- La respuesta JSON trae la cabecera `parameters` **en el orden de la ficha, no en el pedido**
  (la densidad va antes que la velocidad): se lee por nombre.
- **⚠ Un parámetro desconocido se ignora en silencio**: 200 con solo la columna de hora. Si el
  cliente no comprueba la cabecera, una serie sin valores parecería una serie de huecos.
- Errores: id desconocido → 404 con `status.code` 1406; ventana sin datos (p. ej. futura) → 404
  con 1406 «No data available»; fecha mal formada → 400 con 1400; `time.max < time.min` → 400 con
  1408, que además dice el **máximo de 31 días** por consulta.
- Solo salen el id público, la ventana de fechas, los parámetros y el formato, con User-Agent
  genérico.

Conectado en `app/environment/iswa.py` y `GET /api/space-weather/series` (propósito de egress
`space-weather-series`).

---

## 7. SSCweb (Satellite Situation Center, NASA Goddard) — `spike_sscweb.py`

Ejecutado el 2026-11-11. **Base:** `https://sscweb.gsfc.nasa.gov/WS/sscr/2` · sin clave ni registro.

- `GET /locations/iss/<inicio>,<fin>/geo/` (instantes `YYYYMMDDTHHMMSSZ`) da latitud, longitud,
  hora local, X/Y/Z y `RadialLength` (km al centro de la Tierra) de la ISS.
- **El formato lo decide `Accept`.** Sin `Accept: application/json` responde XML. `egress.get` no
  deja poner cabeceras; el cliente usa `egress.client`.
- **El JSON es el de Jackson con tipos:** cada objeto llega como `["gov.nasa...Clase", {...}]` y cada
  lista como `["java.util.ArrayList", [...]]`. Hay que desenvolverlo.
- **Un satélite inexistente da HTTP 200** con `StatusCode: ERROR`, `StatusSubCode:
  INVALID_SATELLITE`. El código HTTP no basta: se mira `StatusCode`.
- **Fuera de las efemérides da 200, `SUCCESS` y sin `Data`.** No es un error ni «cero posiciones»:
  es que SSCweb no tiene ese tramo.
- Un instante mal formado da **404 con una página HTML** de Tomcat.
- `/observatories`: la ISS a **60 s** de resolución, de 1998-11-21 a 2026-11-29. Las efemérides
  llegan unas semanas por delante: lo que se da para «ahora» es una efeméride (definitiva o
  predicha), **no telemetría** de la nave.
- La longitud viene en **0-360°**. `Cache-Control: max-age=86400`.
- Tres horas de la ISS son ~35 KB en JSON (181 muestras).

**La SAA no la da SSCweb.** Primera versión (2026-11-11, mañana): una caja publicada, NASA GSFC
«Ask an Astrophysicist» (1996-10-04): a 500 km, longitud −90° a +40° y latitud −50° a 0°,
declarada `unverified` porque la URL antigua redirigía y el archivo de Internet Archive dio 429.

**Revisión en fuente (2026-11-11, «se busca la verdad»):**

- **La caja de 1996 sí está en su fuente primaria**, que sigue publicada en otra URL:
  <https://imagine.gsfc.nasa.gov/ask_astro/earth.html>, pregunta 961004 («What are the boundaries
  of the South Atlantic Anomaly?», enviada el 4 de octubre de 1996). Dice literalmente: «The
  boundaries of the SAA vary with altitude above the Earth. At an altitude of 500 km, the SAA
  ranges between -90 and +40 in geographic longitude and -50 to 0 in geographic latitude. In this
  region, the extent of the SAA increases with increasing altitude.» Verificada, pues, como lo que
  es: una caja a 500 km de 1996. A la altura de la ISS la exagera.
- **Contorno a la altura de la ISS, publicado numéricamente: el de NICER.** NICER es un telescopio
  de rayos X instalado en la ISS, y NASA GSFC publica en su CALDB el contorno de SAA que usa para
  descartar datos: <https://heasarc.gsfc.nasa.gov/FTP/caldb/data/nicer/xti/bcf/saa/nixtisaareg20170601v003.fits>
  (tabla `REGION`, `REGTYPE(SAACONT)`, «NICER SAA Region», creado 2018-02-26, válido desde
  2017-06-01). Es un polígono de 13 vértices en longitud −180..180 y latitud geográficas; se leyó
  el fichero (cabecera y tabla) el 2026-11-11. La ayuda de `niprefilter2` en HEASARC dice: «The
  NICER_SAA is a custom definition of SAA for the NICER payload on the ISS. It is produced from
  NICER data.»; la de `nimaketime`: «The NICER_SAA contour is smaller than the standard SAA
  contour, but has been customized for NICER's environment.» Hay una versión ampliada
  (`SAACONTLARGE1`, `nixtisaalgreg20170601v001.fits`), que EMMA no usa.
- **Lo que EMMA usa ahora**: el contorno `SAACONT` (`SAA_REGION` en `app/environment/orbit.py`),
  `status: "verified"`, con la caja de 1996 guardada como `superseded`. Límites declarados: es
  donde los detectores de NICER ven fondo de partículas, **no un contorno de dosis** (el fichero no
  declara el umbral con que se trazó); es propio de NICER y más pequeño que el genérico; se trazó
  con datos hasta 2017-2018 y no sigue la deriva de la SAA; vale solo para la órbita de la ISS.
- **No encontrado**: un contorno de **dosis** a la altura de la ISS publicado en cifras (DOSTEL,
  DOSIS-3D, Liulin-5 e ISS-RAD publican mapas y tasas de dosis en figuras, no los vértices de una
  frontera). Tampoco se derivó uno de AP-8/AP-9: sería un cálculo propio, no una fuente.

---

## 8. NASA Technical Reports Server (NTRS) — `spike_ntrs.py`

Ejecutado el 2026-11-11. Objetivo: comprobar contra NTRS los informes técnicos de la NASA que cita
el registro de evidencia (resúmenes del HRP IWS, memorandos técnicos, informes de evidencia, normas
de JSC), como se comprueba un DOI contra Crossref.

- **`GET https://ntrs.nasa.gov/api/citations/<n>`**: pública, sin clave, JSON, ~0,7 s por ficha.
  Un número que no existe da **404** (`{"statusCode":404,"message":"Not Found"}`); uno que no es
  numérico, **400**. Cabeceras `X-RateLimit-Limit: 500` (con `Remaining` y `Reset`); una ráfaga
  de 10 no dio ningún 429. User-Agent genérico; no hace falta nada más.
- **Campos útiles**: `title`; `authorAffiliations[].meta.author.name` (en orden por `sequence`),
  con **grafías mezcladas** («Krihak, M.», «David L Pletcher», «Pietrzyk,, Robert A.»): se coteja
  por apellido. `publications[].publicationDate` y `meetings[].startDate/endDate` dan el año;
  `created`, `submittedDate` y `distributionDate` son de NTRS, no de la obra (2019 en informes de
  2016). `otherReportNumbers` lleva cada número **dos veces**, una con el prefijo
  «Report Number: » (`NASA/TM-2017-219290`, `JSC-20584/REVC`, `HRP-48032 Rev. B`);
  `reportNumbers` no vino en ninguna. `stiType`: `ABSTRACT`, `TECHNICAL_MEMORANDUM`, `OTHER`.
- **Búsqueda** `GET /api/citations/search?q=...` funciona (`stats.total`, `results[]`); no se usa:
  EMMA cita por número.
- **Barrido de las 48 fichas del registro con número de NTRS**: 47 existen; **1 no**:
  `nasa-hrp-roi-iss-facilities-2023` cita «NTRS 20230009091» y NTRS da 404. En NTRS hay una
  versión anterior con el mismo título (20210013701, «HRP Research Operations and Integration
  (ROI) ISS Facilities Overview»). No se acusa de inventada: NTRS retira y restringe fichas.
- **Diferencias de campos** (para revisar con la fuente; no se corrigen aquí): JSC 20584 (EMMA sin
  «: Revision C» en el título); Ahmed 1981 (EMMA cita el capítulo y NTRS el volumen de 1981 con sus
  editores); 20130000839 («SMO 016E» frente a «SMO -16E» de NTRS); 20090007818 («Clarke MSF»
  frente a «Clark, Mark S.F.»); 20110008547 («Rodriguez BR» frente a «Rodriquez, Branelle R.» de
  NTRS); el informe de evidencia de sueño de 2016 (EMMA antepone «Evidence Report:»);
  20205011728 (EMMA añade «(diapositivas)»).
- **Revisadas en fuente el 2026-11-11** (PDF de cada ficha de NTRS; la portada manda):
  - `nasa-hrp-roi-iss-facilities-2023`: el documento que respalda la ficha es el PDF de junio de
    2023 de nasa.gov; su portada imprime «NF-1676 20230009091». NTRS no tiene ficha pública con
    ese número (404; búsqueda por el número, 0 resultados) y no consta si existió y se retiró. La
    revisión de agosto de 2022 sí está: 20210013701 (portada «REVISED August 2022», «NF-1676
    20210013701»), con las mismas frases citadas en las diapositivas 9 y 11 (en la de 2023, 10 y
    12). La ficha se queda con 2023 y lo declara; `KNOWN_NOT_IN_NTRS` lo explica.
  - JSC 20584: la portada da el título sin «: Revision C» (la revisión va aparte). EMMA bien.
  - Ahmed 1981: NTRS 19820015234 es el volumen; el capítulo tiene ficha propia, 19820015235 (sin
    PDF), titulada «Experimental study of high density foods for the Space Operations Center».
    La portada del capítulo (p. 2 del PDF del volumen, capa de texto del escaneo) dice
    «EXPERIMENTAL STUDY OF HIGH DENSITY FOODS» y «Selina M. Ahmed»: **título de EMMA corregido**
    a ese.
  - 20130000839: el resumen dice «(SMO 016E)». Errata de NTRS; EMMA bien.
  - 20090007818: el póster firma «Mark S.F. Clarke». Errata de NTRS; EMMA bien.
  - 20110008547: la ponencia firma «Branelle R. Rodriguez». Errata de NTRS; EMMA bien.
  - Informe de sueño 2016: la portada lleva «Evidence Report:» delante del título. EMMA bien.
  - 20205011728: la portada de las diapositivas dice «Clinical Decision Support – ConOps»;
    «(diapositivas)» era un añadido de EMMA. **Título de EMMA corregido** al de la portada.
  El cotejo (`app/evidence/ntrs.py`, `EXPLAINED_DIFFERENCES`) marca estas siete como
  `explicada` con su motivo, solo mientras los dos lados escriban lo mismo que al revisarlas.

Consecuencia de diseño: `app/evidence/ntrs.py` (caché con edad, sin red como modo nominal) y
`check_ntrs` en `app/evidence/citations.py`, donde un 404 es `no_encontrada_en_ntrs`, nunca
`no_existe`.

---

## 9. API de datos de OSDR: fichas de estudio — `spike_osdr_data.py` (2026-11-11)

**Base:** `https://visualization.osdr.nasa.gov/biodata/api/v2` · sin autenticación ni clave; el
spike sale con el User-Agent genérico de httpx y solo manda el identificador del estudio.

- `GET /dataset/<OSD>/?format=json` → `{<OSD>: {metadata: {...}}}` (≈5-17 kB, <1 s). En
  `metadata`: `study title`, `organism`, `mission` (`name`, `start date`, `end date`),
  `study assay measurement type`/`technology type` (texto **o lista**, según cuántos ensayos),
  `project type` («Spaceflight Study» / «Ground Study») y `study public release date` en
  **segundos desde 1970**.
- `GET /dataset/<OSD>/samples/?format=json` → `{<OSD>: {assays: {<ensayo>: {samples: {...}}}}}`.
  Se cuentan los nombres distintos: una muestra no es un sujeto (OSD-51: 340 muestras de 24
  mujeres). `/assays/<ensayo>/samples/` da 400: la ruta buena es `/assay/` en singular.
- Errores: un estudio que no existe da **422** (`UNPROCESSABLE_ENTITY`); una ruta mal formada,
  **400** con JSON (`ParserError`).
- Las fechas de misión mezclan formatos («7/18/16», «14-Aug-2017»): se enseñan como texto.
- Los diez estudios de OSDR del registro coinciden con su ficha en título, fecha y población.
  **OSD-288: `Mus musculus`, SpaceX-9, RNA-Seq, 9 muestras** en un solo ensayo (3 por grupo): la cifra de
  la ficha («publica 9 muestras de bazo») es la de la API. OSD-343 da `Mus musculus`: es lo que la
  ficha ya decía (estudio humano y animal, ficheros de ratón), y sale «compatible».
- **Para revisar, no corregido:** la misión de OSD-288 termina el «9/26/16» según la API, y la
  ficha cita del protocolo el amerizaje el 26 de agosto de 2016. Es un mes de diferencia en
  la fuente misma; la ficha no guarda la fecha de fin como campo y EMMA no la compara.
- **Revisado en fuente el 2026-11-11:** la fecha buena del regreso es el **26 de agosto de 2016**.
  Lo dicen el protocolo del estudio en la propia API («The capsule splashed down in the Pacific
  Ocean offshore from California on 26 August 2016 (GMT)») y NASA (nota de prensa RELEASE16-090,
  «SpaceX Dragon Splashes Down with Crucial NASA Research Samples», 26-ago-2016: amerizaje a las
  11:47 EDT del viernes 26 de agosto). «9/26/16» es el `endDate` («09/26/2016») del registro de
  misión «SpaceX-9» de OSDR (`osdr.nasa.gov/geode-py/ws/api/mission/SpaceX-9`), compartido por
  ocho estudios; OSDR no dice qué marca y ninguna fuente leída da un hito ese día. La ficha de
  EMMA estaba bien. `osdr_data.py` (`MISSION_NOTES`) enseña la nota junto a la misión mientras la
  API siga dando «9/26/16».

Cliente: `app/evidence/osdr_data.py`; ruta `GET /api/osdr/studies[/<ficha>]`.

---

## 10. NAIF SPICE: tiempo de luz y elongación en local — `spike_spice.py` (2026-11-11)

**Fuente:** núcleos genéricos de NAIF (JPL) en `https://naif.jpl.nasa.gov/pub/naif/generic_kernels/`,
sin clave ni registro; biblioteca `spiceypy` 8.3.0 (MIT, lleva CSPICE N0067). La descarga sale por
`egress` (propósito `spice-kernels`) con el User-Agent genérico de httpx y solo la URL del fichero.
(Si otro hallazgo del mismo lote tomó el número 10, renumerar al fusionar.)

- **Qué núcleo.** Los SPK planetarios genéricos, por tamaño (listado del servidor): `de432s.bsp`
  10 MB (1950-2050), `de440s.bsp` y `de442s.bsp` 31 MB (1849-2150), `de430`/`de435`/`de438`/
  `de440`/`de442` 114 MB, `de431`/`de441` 1,3-1,7 GB por parte. El más pequeño que cubre la misión
  es **`de432s.bsp`** (10 895 360 bytes); su cobertura real para Marte, Tierra y Sol, leída con
  `spkcov`, va del 1949-12-14 al 2050-01-01. Trae baricentros de Mercurio a Plutón, el Sol, la
  Luna, la Tierra, Mercurio y Venus: **no trae el centro de Marte (499)**, solo su baricentro (4).
  El LSK es `naif0012.tls` (5 257 bytes; último segundo intercalar, 2017-01-01).
- **Integridad.** NAIF publica MD5 de los SPK en `spk/planets/aa_checksums.txt` (`de432s.bsp`:
  `d66c2153188958472fec67016b4b4e7a`, coincide); de los LSK no publica nada. EMMA fija además el
  tamaño y el SHA-256 de los dos el día de la descarga (`environment/spice.py`, `KERNELS`).
- **Licencia.** `https://naif.jpl.nasa.gov/naif/rules.html`: «SPICE kernels placed on the NAIF
  server may be downloaded and used by anyone» y «Redistribution of SPICE kernels distributed by
  NAIF is permitted as long as they have not been modified». La página no dice «dominio público».
  CSPICE dentro de un paquete de terceros (lo que hace `spiceypy`) es «entirely appropriate» según
  la misma página.
- **Comparación con Horizons, los 181 días de la misión (2026-11-01 a 2027-04-30), 00:00 UT,
  objetivo 499 desde 500@399.** Peor diferencia: **tiempo de luz 0,003 ms, distancia 0,73 km,
  elongación 0,00005°**. La diferencia de distancia baja de 0,73 km (1,43 UA) a 0,01 km cerca de
  la oposición: es la de DE432 frente a DE441 de Horizons más baricentro frente a centro, muy por
  debajo del error declarado (0,1 s y 0,01°). Muestra: 2026-11-01 Horizons 11,91382 min y
  1,43251012 UA, SPICE lo mismo hasta el quinto decimal; 2027-02-15 (oposición) 5,66164 min.
- **Cómo se calcula** para casar con Horizons: distancia aparente con `spkpos(..., "LT", ...)` (el
  `delta` de Horizons, corregido por tiempo de luz); tiempo de luz el que devuelve `spkpos`;
  elongación entre las direcciones `LT+S` del Sol y del objetivo; fecha `str2et("AAAA-MM-DD
  00:00:00 UTC")` con el LSK.
- **HALLAZGO: la marca `/T`-`/L` va por ascensión recta, no por longitud eclíptica.** Con la
  longitud eclíptica, el 2027-02-20 (elongación 175,5°, junto a la oposición) salía `/T` y Horizons
  dice `/L`; Horizons cambia de marca entre el 20 y el 21, justo cuando la diferencia de ascensión
  recta J2000 cruza 180° (181,17° → 179,83°). Con ascensión recta coinciden los 181 días.
- **Fuera de cobertura** (2051-01-01), SPICE no extrapola: `SPICE(SPKINSUFFDATA)`; EMMA lo dice
  como «no disponible».

Cliente: `app/environment/spice.py`; precedencia en `EphemerisClient.comms_window`; ruta
`GET /api/spice`; descarga `scripts/fetch_spice_kernels.py`; cobertura en
`mission.ephemeris_coverage.spice`.

**Decisión del usuario (2026-11-11): SPICE primero; Horizons de contraste y respaldo.** La primera
versión ponía Horizons delante (caché → en vivo → SPICE). Con esta medida (0,003 ms de peor
diferencia en 181 días) y sin red como modo nominal, se invierte: si SPICE calcula el día, el
retardo sale de SPICE sin salir a la red; la efeméride de Horizons de ese día en caché, si la hay,
lo contrasta (no se pide en vivo solo para contrastar); si discrepan por encima del error declarado
(0,1 s, 0,01°) se dice y ese día se usa Horizons. Si SPICE no calcula el día (otro objetivo, fuera
del núcleo, sin núcleos), el orden de antes: caché de Horizons → Horizons en vivo → «sin dato».
Mismas cifras de riesgo; la validación externa no usa retardo.
