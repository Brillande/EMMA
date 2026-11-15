# Repositorios de datos humanos de NASA

Backlog de la base de conocimiento (§15, P1 "NLSP y LSAH": qué datos humanos longitudinales son
públicos o restringidos). Leído en sus fuentes el 2026-09-28; la fila de OSDR, al día con el mapa
de conjuntos el 2026-10-31.

| Repositorio | Qué contiene (según NASA) | Acceso | Uso en EMMA |
|---|---|---|---|
| **NLSP** (NASA Life Sciences Portal) | "Human research data from spaceflight and ground-analog studies dating back to 1961" | Por solicitud ([preguntas frecuentes de solicitud](https://nlsp.nasa.gov/Request/DataRequestFAQ)) | Ninguno todavía: exige solicitud y aprobación |
| **LSDA** (Life Sciences Data Archive) | Datos de investigación de 1961 a hoy, humanos, animales y plantas | Datos atribuibles a una persona restringidos por la Privacy Act; se pueden pedir para investigación, y toda publicación se revisa antes por atribuibilidad | Ninguno. Es donde están los datos individuales del Twins Study y las medidas estándar de AGBRESA (abajo) |
| **LSAH** (Lifetime Surveillance of Astronaut Health) | "Medical monitoring data for astronaut health surveillance" | Restringido; los astronautas autorizan acceso total, parcial o ninguno | Ninguno. Por eso "no existe API de constantes de astronautas" es una mina de `CLAUDE.md` |
| **OSDR** (Open Science Data Repository) | "Human cellular and non-human life science data" | Abierto en su mayor parte; lo controlado se marca fichero a fichero (un botón «Request Access to Restricted Files» y un candado, según su tutorial; la API de ficheros lo da como `restricted`) | Sí: OSD-288 (ratón, bazo), OSD-569 (hemograma real de Inspiration4), OSD-343 (ficheros abiertos de ratón; el análisis humano, en su publicación). Leídos y sin uso: los siete reposos en cama humanos |

Fuentes: [NASA HRP](https://www.nasa.gov/hrp/),
[Life Sciences Data Archive](https://www.nasa.gov/directorates/esdmd/hhp/life-sciences-data-archive-lsda/),
[NTRS 20170009498, revisión de atribuibilidad](https://ntrs.nasa.gov/citations/20170009498),
[tutorial de OSDR sobre acceso controlado](https://www.nasa.gov/reference/osdr-tutorials-requesting-controlled-access-datasets/).

**Consecuencia para el proyecto**: los datos humanos longitudinales de astronautas existen pero
no son abiertos. EMMA usa lo abierto (OSDR, MMASH en Tierra) y el simulador, y lo declara.
Pedir datos a NLSP o LSDA sería un trabajo de meses con revisión de privacidad, fuera del alcance
de un hackathon.

## Mapa de conjuntos de datos humanos (decimoquinta ronda, D2; al día en la decimonovena, U5)

La tarea P0 de la base de conocimiento (§15: «tabla de variables, timepoints, acceso y utilidad»)
vive ya como dato servido: `backend/app/data/human_datasets_read.json`, validado por
`backend/app/evidence/human_datasets.py`, en `GET /api/human-datasets` y en el panel «Conjuntos de
datos humanos y CIPHER» de la consola de Tierra. Cada frase tiene ficha en
`backend/app/data/evidence_refs.json` y lleva el día en que se leyó (2026-10-22, -23, -26 y -31).
Resumen de los **catorce conjuntos** (el detalle y las frases, en el fichero):

| Conjunto | A quién | Tomas leídas (L- / vuelo / R+) | Acceso | Uso en EMMA |
|---|---|---|---|---|
| **OSD-569** | 4 civiles de Inspiration4, 3 días | L-92, L-44, L-3 / ninguna en este conjunto / R+1, R+45, R+82, R+194 | Abierto en parte: los 11 ficheros depositados llevan `restricted: false` y el protocolo dice que la tripulación consintió compartir datos y muestras; las lecturas en bruto de secuenciación no están depositadas y lo sensible (secuencia genética) es de acceso controlado | Linfocitos en la consola de Tierra (`ingest/inspiration4.py`) |
| **Inspiration4 / SOMA** | Los mismos 4 civiles (Overbey et al. y Jones et al., Nature 2024) | L-92, L-44, L-3 / FD1, FD2, FD3 / R+1, R+45, R+82, R+194 | Abierto en parte; lo sensible (secuencia genética, muestras), controlado | Ninguno |
| **NASA Twins Study** | Un astronauta 340 días en la ISS y su gemelo en Tierra (Garrett-Bakelman et al., Science 2019) | Los días que el artículo nombra en resultados concretos: L-162 / FD76, FD259, FD334, FD340 / R+0, R+4, R+12, R+36, R+104, R+190. El calendario entero (figura 1A, tabla S1) está en el suplementario, que no se pudo descargar | Por solicitud aprobada al LSDA | Respaldo del dominio inmune (`evidence/links.py`) |
| **OSD-343** | El estudio analiza métricas de 59 astronautas, pero **los ficheros abiertos son de ratón** (Rodent Research-9) | De los ratones, la recogida en L+35d (el día después del amerizaje), escrita desde el lanzamiento y sin traducir a R+; de los astronautas, nada | Abierto: 81 ficheros con `restricted: false` | Respaldo de mecanismo (`evidence/links.py`) |
| **OSD-288** | 12 ratones, 35 días en la ISS: **no son astronautas** | Disección «at the laboratory» tras el regreso, sin día | Abierto: 178 ficheros con `restricted: false` | Respaldo inmunológico en ratón (`evidence/links.py`) |
| **MMASH** | 22 hombres jóvenes sanos, 24 h en Tierra: **no es fisiología de vuelo** | No procede | Abierto (ODbL 1.0) | Falsa alarma y sensibilidad del motor (`validation/mmash.py`) |
| **AGBRESA** (reposo en cama) | 24 voluntarios, 60 días con la cabeza 6° abajo (Clément et al., Front Physiol 2022): **no es vuelo** | No proceden: su calendario es de análogo (BDC-14 … BDC-1, HDT1 … HDT60, R+0 … R+13 de recuperación tras el reposo) | Dos vías: las medidas estándar internacionales están en el LSDA y se piden allí (Clément et al., Acta Astronautica 2022); el resto, a petición a sus autores | Ninguno con sus datos; los bancos de prueba citan su página de NASA |
| **OSD-51** (WISE 2005, reposo en cama) | 24 mujeres, 60 días de reposo; ficheros de transcriptoma de músculo | No proceden: 20 días antes, 60 de reposo, 20 de recuperación | Abierto: 4 ficheros con `restricted: false` | Ninguno |
| **OSD-195** (PlanHab, 21 días) | 14 hombres, reposo en cama horizontal normóxico; expresión génica del vasto lateral | No proceden: biopsias seis días antes y el día 21 | Abierto: 49 ficheros con `restricted: false` | Ninguno |
| **OSD-198** (PlanHab, reposo e hipoxia) | Los mismos 14 hombres en tres campañas cruzadas (reposo normóxico, reposo hipóxico, confinamiento hipóxico); microARN del vasto lateral | No proceden: siete días basales, 21 de intervención, cuatro meses de descanso entre campañas | Abierto: 70 ficheros con `restricted: false` | Ninguno |
| **OSD-353** (proteoma del plasma) | 13 cosmonautas antes y después de 169-199 días en la ISS, 5 hombres en reposo en cama de 21 días y 5 en inmersión seca de 21 días; su entorno queda fuera del enumerado | Antes y después, sin día L-/R+ escrito: el artículo dice «six months before flight» y «+1 day», «+7 days» tras el aterrizaje / ninguna en vuelo | Abierto: 4 ficheros con `restricted: false` | Ninguno |
| **OSD-370** (9 días de reposo e insulina) | Hombres jóvenes (diez en el protocolo, veinte en la descripción: sin resolver), reposo medio recostado y cuatro semanas de reentrenamiento; expresión génica del vasto lateral | No proceden: antes y después del reposo y tras el reentrenamiento | Abierto: 71 ficheros con `restricted: false` (la API v2 daba 72 el 2026-10-26) | Ninguno |
| **OSD-942** (70 días de reposo de NASA) | 22 hombres, cabeza 6° abajo, con y sin ejercicio (SPRINT); expresión génica del vasto lateral | No proceden: un día antes y el día 64 del reposo | Abierto: 45 ficheros con `restricted: false` | Ninguno |
| **OSD-946** (70 días de reposo de NASA) | El mismo estudio; microARN del vasto lateral | No proceden: un día antes y el día 64 | Abierto: 45 ficheros con `restricted: false` | Ninguno |

**Acceso, leído y no deducido (2026-10-31).** Hasta la decimonovena ronda el acceso de los
conjuntos de OSDR se deducía de que sus ficheros tuvieran enlace de descarga, y el de OSD-569 de
que EMMA tuviera uno. La API de ficheros de OSDR (`osdr/data/osd/files/<n>`) marca cada fichero con
`restricted: true|false`, y el tutorial de OSDR dice qué significa: un estudio con datos de acceso
controlado lleva el botón «Request Access to Restricted Files» y un candado en cada fichero
restringido. Los diez conjuntos de OSDR del mapa tienen todos sus ficheros en `false`; lo que no
está depositado (las lecturas en bruto de secuenciación de Inspiration4) no se puede llamar abierto
por eso, y se dice.

**Papel y aptitud (decimonovena ronda, U5).** La base de conocimiento (§8) pide separar INPUT
(señales de misión), KNOWLEDGE (evidencia histórica o mecanística) y CONTEXT (entorno y misión), y
la conversación de ideación pide decir de cada conjunto «si sirven para entrenar, validar o
simplemente contextualizar nuestro modelo». Cada conjunto y CIPHER llevan ahora `role`: su nivel y
su aptitud, cada uno con su motivo, rotulados **«deducción de EMMA sobre lo leído»** (ninguna fuente
dice para qué le sirve a EMMA; es el mismo rótulo que la matriz banco × RIDGE de los bancos de
prueba). La respuesta del mapa: **los catorce conjuntos y CIPHER son KNOWLEDGE**, porque un estudio
con población es evidencia histórica —los INPUT de EMMA son los wearables y el simulador, y el
CONTEXT las efemérides y DONKI, que no están en este mapa—, y **solo MMASH sirve para validar**
(sobre él se miden juntas la falsa alarma y la sensibilidad del motor); los demás **solo
contextualizan**, incluido OSD-569, cuyo hemograma se reproduce para enseñar una respuesta real al
vuelo pero no mide el motor (sin línea base personal con siete muestras, EMMA no alerta sobre la
bajada de linfocitos). «Entrenar» no lo dice ninguno: EMMA no entrena ningún modelo; compara con
la línea base de la persona o con un rango de referencia, y los parámetros del simulador salen de
la bibliografía. El cargador rechaza INPUT,
CONTEXT y «entrenar» con su motivo, y «validar» en un conjunto que EMMA no usa o cuyos ficheros
abiertos no miden personas. Los catálogos no se clasifican: no son una fuente de datos sino el
índice de otras.

**Controles** (decimosexta ronda, E11; la conversación, a propósito de Biolab: «Flight sample /
In-flight control / Ground control / Pre-flight / Post-flight»): cada conjunto dice los suyos con
su frase. OSD-288: ratones en Tierra y ratones a 1 g en vuelo por centrifugación (siguen siendo
ratones); OSD-343: ratones en hábitat en Tierra; Twins Study: el gemelo en Tierra; Inspiration4:
cada tripulante es su propio control, sin controles en Tierra; AGBRESA, OSD-51, OSD-942 y OSD-946:
el grupo en reposo sin contramedida; OSD-569: los mismos cuatro tripulantes de Inspiration4, con el
control del artículo de la misión (su ficha de OSDR no nombra ninguno); MMASH: no procede.
**Buscado y no encontrado** en OSD-195, OSD-198, OSD-353 y OSD-370: sus fichas no nombran ningún
grupo de control; los artículos de OSD-198 (Rullman et al. 2016, tres campañas cruzadas) y OSD-353
(Brzhozovskiy et al. 2019) tampoco; los de OSD-195 y OSD-370 no están en PMC y no se leyeron.

**Catálogos** (§8): el **ISS Research Explorer** (experimentos, instalaciones y publicaciones; sus
informes se descargan sin cuenta) y **data.nasa.gov** («describes NASA datasets rather than hosting
the data itself») no miden a nadie: van aparte, sin población, tomas ni papel.

**Twins Study, las diez áreas** (página «The Research» de NASA): Metabolomics, Proteomics,
Cognition, Microbiome, Telomeres, Epigenomics, Biochemical, Gene Expression, Integrative Omics e
Immunome.

**CIPHER** (Complement of Integrated Protocols for Human Exploration Research): catorce estudios
antes, durante y después de la misión, hasta 30 astronautas en tres duraciones (corta, menos de
3,5 meses; estándar, de 3,5 a 8; extendida, más de 8). Dos pósteres de NTRS (2026-10-31) dan el
calendario de **su propio estudio**, no el de la suite: Space Physiology (VO2pk en L-180, L-60,
FD14, FD75, R-14, R+5, R+30; «30 astronauts (n=10 for each mission duration of 2 months, 6 months,
and 1 year)») y Vestibular Health (Launch-200, Launch-90, Flight Day 1, Flight Day 30, Return-30,
Return+0, Return+4, Return+9, Return+30). Por eso CIPHER sigue sin días propios, con las frases a la
vista. **Buscado y no encontrado:** cómo se accede a sus datos; lo más cercano es el plan de gestión
de datos del HRP (resumen del taller de 2024, NTRS), que dice que el HRP archiva en el NLSP los
datos de sujetos humanos en vuelo que considera únicos y de alto valor, sin nombrar CIPHER. EMMA
cita uno de sus estudios, Spaceflight Standard Measures, en el coste de medir.

La escalera de hitos de la conversación (L-180 → L-30 → Flight → R+0 → R+7 → R+30 → R+90 → R+180 →
R+365) se pinta con los días leídos en su tramo: ninguno de estos conjuntos da una toma con día
antes de L-180 ni después de R+365; los únicos con tomas en vuelo con día son Inspiration4 (tres
días de vuelo) y el Twins Study (los cuatro días de vuelo que su artículo nombra).

**Lo que sigue buscado y no encontrado** (la lista completa, en `not_found` del fichero): el
calendario entero del Twins Study (suplementario de 11 MB, que PMC no sirve sin navegador y Europe
PMC declara no abierto); los días de las tomas de las métricas de astronautas de OSD-343 y de la
disección de OSD-288; los días de CIPHER como suite y el acceso a sus datos; los controles de los
cuatro reposos de arriba; y una API pública de constantes vitales de astronautas, que no existe.
Nada de este mapa son constantes vitales de astronautas en vuelo: lo más cercano es el hemograma de
Inspiration4, siete tomas en Tierra.
