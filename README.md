# EMMA — Environment and Medical Monitoring Assistant

Monitorización autónoma de salud para tripulaciones en misiones de larga duración.
NASA Space Apps Challenge 2026 · *The Next Frontier*.

La restricción que define el diseño no es el sensor: es la **autonomía**. El
14 de noviembre de 2026, Marte está a 1,324 UA de la Tierra — 11 minutos de ida,
**22 de ida y vuelta**, calculado con efemérides reales de JPL Horizons. No hay
consulta en vivo con el cirujano de vuelo. El software tiene que decidir solo.

> **CMO-DA diagnostica; EMMA vigila.** NASA y Google tienen un asistente médico
> digital para cuando no hay médico a bordo. Responde cuando ya hay un síntoma.
> EMMA detecta el cambio antes de que lo haya — y su salida es precisamente el
> contexto longitudinal que un asistente diagnóstico necesita y hoy no tiene.

---

## Descargar e instalar (Windows)

**[Instalador de EMMA para Windows](https://github.com/Brillande/EMMA/releases/latest)** —
descarga `EMMA.Setup.x.y.z.exe` de la última versión y ejecútalo. No necesita Python, Node ni nada
más: lleva el backend, la interfaz y el planificador.

- **Modelos de IA.** El instalador pregunta «Also download the AI models (about 33 GB)», marcado
  por defecto. Si se deja marcado, la primera vez que se abre EMMA descarga sola los modelos
  (modelos de lenguaje con Ollama, transcripción de voz con Whisper, segmentación de TAC con
  TotalSegmentator y lectura de informes con Tesseract) desde la versión
  [`modelos-1`](https://github.com/Brillande/EMMA/releases/tag/modelos-1), comprueba cada fichero
  con su SHA-256 y los instala en `%LOCALAPPDATA%\EMMA-modelos`. El progreso se ve en
  «AI models», al pie de la pantalla; se usan al volver a abrir EMMA. También se pueden bajar
  más tarde desde ese mismo panel, pieza a pieza, o instalar sin red desde un USB con
  `instalar.cmd` (ver las notas de `modelos-1`).
- **Sin modelos EMMA funciona igual:** constantes, análisis, alertas y recomendaciones no
  dependen de ellos; lo que sí, se muestra como «no disponible».
- **Actualizaciones desde la app (desde la 0.1.5).** En «About EMMA» → «Update EMMA», «Check
  for a new version» mira si hay una versión más nueva aquí, «Download» baja su instalador y lo
  comprueba con su SHA-256, e «Install and restart» la instala conservando los datos. Nunca lo
  hace solo, y sin red no busca nada. La 0.1.4 y anteriores no traen el actualizador: para pasar
  a la 0.1.5 se instala a mano una vez.
- **Sin firma de código.** Windows SmartScreen avisará: «Más información» → «Ejecutar de todas
  formas».

## Estado

| | |
|---|---|
| Backend | Funcional de extremo a extremo |
| Pruebas | **5522** en la suite normal del backend · 10 `live`, de contrato contra APIs reales y modelos locales · **42 de validación externa** |
| Calidad | `ruff` limpio · `mypy --strict` limpio |
| Interfaz | Consola de tripulación y consola de Tierra · **1768 pruebas**, entre ellas las reglas de pantalla de NASA-STD-3001 Vol 2 |
| Escritorio | [Instalador de Windows](https://github.com/Brillande/EMMA/releases/latest) (Electron), funciona sin red · modelos de IA descargables desde el instalador · se actualiza desde las Releases de GitHub, solo con botón · **sin firma de código** |
| API | 95 rutas de lectura · 51 de escritura: ingesta, firmas y decisiones de la tripulación, gestión de alertas, enmienda y supresión. La lista viva está en `/docs` |

Cifras medidas el 3 de noviembre de 2026 sobre el commit `f8276ea` (la última suite completa del
backend, sobre `5b1e14a`, dio 5510 en verde y 2 fallos que se corrigieron en ese commit); se
reproducen con los comandos de «Arranque». Las `live` y `external` son las que recoge pytest, no las que pasaron:
necesitan red, modelos locales o datasets descargados.

---

## Arranque

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Documentación interactiva en `http://127.0.0.1:8000/docs`.

```bash
.venv/Scripts/python.exe -m pytest tests/ -q      # suite (sin red)
.venv/Scripts/python.exe -m pytest -m live        # contratos contra APIs reales y modelos locales
.venv/Scripts/python.exe scripts/fetch_mmash.py   # descarga los datasets externos:
.venv/Scripts/python.exe scripts/fetch_hc18.py    #   MMASH (fisiología) y HC18 (ecografía)
.venv/Scripts/python.exe -m pytest -m external    # validación con humanos reales
.venv/Scripts/python.exe -m ruff check .          # calidad: lint
.venv/Scripts/python.exe -m mypy app              # calidad: tipos, en modo estricto
```

Interfaz, con el backend arrancado en `:8000`:

```bash
cd frontend
npm install && npm run dev                      # http://localhost:5173
npm test                                        # reglas del Apéndice F
```

Aplicación de escritorio (Windows):

```bash
cd desktop
npm install && npm run dist                     # desktop/release/EMMA Setup x.y.z.exe
```

### Actualizar el EMMA instalado desde GitHub

El EMMA instalado se pone al día con las versiones que se publican como Releases de
[`github.com/Brillande/EMMA`](https://github.com/Brillande/EMMA/releases): cada una lleva su
`EMMA.Setup.X.Y.Z.exe` y un manifiesto `emma-update.json` con la versión, el tamaño y el SHA-256
del instalador. Desde la **0.1.5**, la primera que lo trae; la 0.1.4 y anteriores se pasan a la
0.1.5 instalándola a mano una vez. En «Acerca de EMMA» → «Actualizar EMMA» (con la interfaz en
inglés, «About EMMA» → «Update EMMA»: «Check for a new version», «Download», «Install and
restart»):

1. **Comprobar si hay una versión nueva** lee el manifiesto de la última Release y dice si hay una versión más nueva.
2. **Descargar** baja el instalador (reanudable) y comprueba tamaño y SHA-256.
3. **Instalar y reiniciar** cierra EMMA, instala la versión nueva conservando los datos y la abre
   de nuevo. La aplicación de escritorio vuelve a comprobar la huella antes de lanzarlo.

Nada de esto ocurre solo: no hay comprobación al arrancar ni descarga en segundo plano. Solo se sale
a internet al pulsar «Comprobar…» o «Descargar», y siempre por `backend/app/core/egress.py`
(propósito `app-update`). En modo sin red (`EMMA_OFFLINE=true`, el nominal de misión) no se busca
nada: una versión nueva se instala con su instalador desde un USB. Con el **modo seguro** activo no
se busca, no se descarga y **tampoco se instala** lo ya descargado. El actualizador nunca baja de
versión; volver a una anterior es ejecutar a mano su instalador.

Publicar una versión para que el exe la vea (lo hace el responsable, nunca la aplicación):

```bash
# misma versión en backend/pyproject.toml, frontend/package.json, desktop/package.json y app/main.py
cd desktop && npm run dist
cd ../backend && .venv/Scripts/python.exe packaging/publish_app.py --notes "Qué cambia" --dry-run  # revisar el plan
.venv/Scripts/python.exe packaging/publish_app.py --notes "Qué cambia"            # sube con gh
```

Guía completa en [`docs/actualizaciones.md`](docs/actualizaciones.md); especificación, modelo de
amenazas y su encaje en IEC 62304 en
[`compliance/software-update.md`](compliance/software-update.md).

Las pruebas normales **no tocan la red**. Las `live` confirman que las APIs de
NASA siguen respondiendo como se documentó, que cada cita de EMMA existe en su
registro y que los modelos locales instalados (verificadores, Whisper, NER) siguen
funcionando. Las `external` pasan el motor por fisiología humana real (MMASH,
PhysioNet), por ecografías reales (HC18) y, si hay segmentaciones hechas en la
máquina, por los TAC de prueba del dataset de TotalSegmentator.

---

## Qué hace

Ingiere indicadores de salud —de un wearable BLE real, de exportaciones de Apple
Health o Google Fit, de un test PVT, o del simulador—, los normaliza a
**FHIR R4 `Observation`**, los persiste en un almacén *append-only* con auditoría
encadenada, los evalúa contra la línea base personal del tripulante y su
tendencia, los cruza con el entorno (radiación, meteorología espacial, retardo de
comunicaciones) y emite recomendaciones accionables, **cada una con su evidencia
científica enlazada**.

Dominios clínicos: cardiovascular, conductual, radiación, óseo, inmune, neuro-ocular,
genitourinario (retención e hidratación), musculoesquelético y nutrición, cada uno con su peligro
RIDGE de NASA. El catálogo vigente de indicadores, con qué códigos son LOINC y cuáles propios, lo
da `/api/indicators`.

### Lo que lo distingue

1. **Conciencia de tiempo de luz.** Efemérides reales del JPL: el sistema sabe
   cuán solo está el astronauta y **escala los hallazgos antes** cuando no hay
   ayuda cerca. No es un adorno del panel; está en el motor de riesgo.
2. **Evidencia trazable.** Cada alerta cita el riesgo del NASA HRP o el estudio
   OSDR en que se apoya — y declara el alcance real de esa evidencia.
3. **Offline-first de verdad.** La suite de API corre con el modo offline
   forzado: si algo tocara la red, fallaría.
4. **Antigüedad siempre visible.** Ningún dato externo se muestra sin su edad. Un
   dato de meteorología espacial de hace seis horas y uno de hace seis días
   exigen decisiones distintas.
5. **Diseñado contra la fatiga de alarma.** Cuatro controles independientes,
   documentados en [`compliance/clinical-decision-rationale.md`](compliance/clinical-decision-rationale.md).
6. **Auditoría impuesta por el código, no prometida.** No existe endpoint que
   guarde una observación sin pasar por el ledger encadenado y firmado. Editar la
   base SQLite por fuera entre sesiones queda detectado. Y corregir un dato **no
   borra el anterior**: la versión buena se anexa y queda enlazada por hash con la
   que corrige, que sigue registrada y visible — es lo que pide 45 CFR 164.526 y lo
   que exige 21 CFR 11.10(e), *"record changes shall not obscure previously recorded
   information"*.
7. **Validado contra humanos reales, en los dos ejes.** 1 740 412 latidos de 22
   sujetos sanos: **21 de 22 no reciben ninguna alerta**, mientras se marca el
   **82 %** de las taquicardias sostenidas y el **77 %** de los episodios agudos
   inyectados sobre esa misma fisiología real. Las dos métricas tienen prueba de regresión, porque
   una sin la otra se satisface apagando el sistema — y eso llegó a ocurrir
   durante el desarrollo. Ver
   [`compliance/external-validation.md`](compliance/external-validation.md).
8. **Tierra ve el pasado, y la pantalla lo dice.** Dos consolas sobre los mismos
   datos. La de tripulación es mínima. La de Tierra aplica el retardo real de las
   efemérides: solo muestra lo que ya ha llegado, calcula el veredicto con esas
   lecturas y marca en cian lo que sigue en tránsito. Cada alerta a bordo dice
   cuándo la conocerá Tierra y cuándo podría llegar su respuesta, como pronto.
   Las reglas de pantalla de NASA-STD-3001 Vol 2 (Apéndice F) son pruebas, no
   intenciones; ver [`compliance/hmi-state-of-the-art.md`](compliance/hmi-state-of-the-art.md).
9. **Ecografía a bordo, sin radiólogo al otro lado.** En la ISS una ecografía se guía en directo
   desde Tierra; hacia Marte, con más de diez minutos de retardo, no. La tripulación sube el DICOM
   (se des-identifica antes de guardarse y queda firmado en el ledger por su hash), lo ve fotograma
   a fotograma y mide con calibres guiados: vaina del nervio óptico (SANS), área de la yugular y
   volumen vesical (LOINC 15309-8). En pulmón, FAST e hígado se anotan signos de una lista cerrada
   —nunca un diagnóstico— con su lista de calidad. El motor de medida se valida contra 999
   ecografías reales de HC18. Un modelo de lenguaje **local** puede redactar un borrador para el médico de a bordo, que
   nace sin validar y pasa por cinco barreras automáticas —entre ellas, que no afirme la ausencia
   de un signo que no se anotó— antes de que una persona lo firme. Lo que todavía no
   hace: alertar sobre estas medidas; se dice en pantalla. Para practicar la lectura sin red, trae
   ecografías reales de pulmón e hígado de datasets abiertos, rotuladas como ejemplo y con su cita.
10. **Visor 3D de volúmenes (de Polaris).** TAC o RM en tres planos y en 3D, con segmentación
    automática local de TotalSegmentator (hígado con vasos y lesiones candidatas; órbitas y
    nervios ópticos para SANS; esqueleto de un TAC de cuerpo entero), mallas y tabla de lesiones.
    Hoy no vuela ningún TAC (en la ISS la única imagen es la ecografía; TAC sin partes giratorias
    y rayos X portátiles siguen en estudio para exploración): sirve para imagen de referencia
    previa al vuelo y para Tierra. La segmentación es un programa externo con sus pesos
    preinstalados; sin él se declara no disponible. Todo lo que marca el modelo va rotulado sin
    validar y no entra en el análisis. Trae TAC reales de ejemplo (dataset de TotalSegmentator,
    CC BY 4.0) ya segmentados.
11. **Astronauta + hábitat + misión, según la especificación del equipo** (`docs/contexto/`).
    Cada dato va rotulado MEDIDO, INFERIDO o PREDICHO, con su entorno (ISS, vuelo, análogo,
    Tierra, simulado). Las contramedidas son datos con fuente, recursos, tiempo de tripulación y
    seguimiento que una persona adopta y cierra. La atmósfera de cabina se vigila con los límites
    de NASA-STD-3001, y si varios tripulantes cambian a la vez con el CO2 fuera de límite, la
    primera hipótesis es el hábitat compartido, rotulada como correlación y no como causa. Cada
    alerta responde qué cambió, desde cuándo y frente a qué base. También hay fase de misión,
    pérdida ósea inferida, hidratación, nutrición (como hipótesis), recuperación posvuelo con el
    hemograma real de Inspiration4, modo anatómico y coste de medir cada indicador.
12. **Dónde duele, y cómo evoluciona.** Un cuerpo en 3D —hecho en código, sin modelos de
    terceros— donde el tripulante toca la zona que le duele, dice cuánto (0-10, LOINC 72514-3) y
    cómo, de listas cerradas. El informe queda firmado en el ledger; la intensidad máxima entra en
    la línea base y el riesgo, bajo su propio dominio, y el borrador del modelo local lee el
    historial. La evolución se sigue por zona en las dos consolas, con el retardo aplicado en
    Tierra.
13. **Lo que pide el enunciado del reto, y lo que pidió el equipo.** Para qué sirve cada órgano de
    la figura, con su fuente; guías paso a paso para medirse (tensión, temperatura, saturación,
    peso, pulso y variabilidad, sueño, ánimo, la PVT y la batería Cognition de NASA) y un
    glosario; rachas de las medidas periódicas como cifra, sin premio de color; monitorización
    intensificada mientras hay un evento solar; tres niveles de misión firmados (nominal,
    reducido, mínimo) que dejan de esperar lo que más cuesta medir sin apagar nunca el análisis
    ni las alertas; y una consola tipo tableta con pestañas por peligro y por entorno (órbita
    baja, cislunar, Luna, Marte), baja visión, modo esencial, privacidad, giro a mano o siguiendo
    el giroscopio, anuncios para lectores de pantalla y voz propia con voces locales.

---

## Del espacio a la Tierra

En 1970, Ernst Stuhlinger respondió a una monja que preguntaba por qué gastar en ir a Marte con
niños pasando hambre: los retos extremos del espacio obligan a soluciones que después vuelven a la
Tierra. EMMA nace de una restricción extrema —cuidar a alguien a millones de kilómetros del
hospital más cercano, sin conexión en tiempo real— y lo que resuelve es **arquitectura**, no
medicina espacial: funciona sin red, en local, conoce la línea base de cada persona, dice en qué
se apoya cada aviso y deja la decisión a quien está delante. Esas mismas restricciones existen
en una comunidad aislada con mala conectividad. No se afirma que los dos contextos clínicos sean
equivalentes; se afirma que la arquitectura es transferible.

## Honestidad sobre las fuentes

Dos premisas iniciales del proyecto resultaron falsas al comprobarlas, y merece
la pena dejarlo escrito:

**`astroquery` no es un backend de salud.** Es un cliente de catálogos
astronómicos sin un solo dato biomédico. Su único uso legítimo aquí es
`astroquery.jplhorizons` para el tiempo de luz — que resulta ser justo el
parámetro que sostiene toda la autonomía del sistema.

**OSD-288 no son datos de astronautas.** Es *"Transcriptome analysis of murine
spleen in space"*: RNA-Seq de bazo de 12 ratones tras 35 días en la ISS. Sirve
como respaldo inmunológico y la API lo declara con esas palabras. No mide signos
vitales humanos.

**No existe API pública de constantes vitales de astronautas** — son datos
médicos protegidos. Los datos vienen de un simulador fisiológico determinista y
de wearables reales vía BLE / Apple Health / Google Fit.

**No se inventan códigos LOINC.** Cada código LOINC del catálogo está
verificado en su ficha oficial. De los 128 indicadores del catálogo, 76 usan LOINC
real; los 52 restantes usan un sistema propio y **cada uno declara por qué** no
puede usar un código estándar — una invariante que la suite comprueba, así que
añadir un indicador nuevo obliga a justificarlo. `/api/indicators` distingue unos
de otros y da el recuento vigente.

Un matiz que costó atrapar: LOINC separa deliberadamente *Mass/volume* de
*Moles/volume* con códigos distintos, y la unidad tiene que seguir a la
propiedad. El código 2142-8 (cortisol salival) es Mass/volume → µg/dL, no nmol/L.
Adoptarlo con unidades molares habría sido un error semántico silencioso.

**El simulador declara qué respaldo tiene cada parámetro de su modelo**, en tres
clases: magnitud documentada, sentido documentado, o **contestado** — donde los
estudios discrepan. `/api/status` los lista en `simulation.evidence`.

La revisión bibliográfica corrigió tres cosas que estaban mal: la caída de SDNN
en vuelo **no está respaldada** (hay estudios que no ven diferencias y otros que
ven subida); la deriva de frecuencia cardíaca en reposo era el doble de lo
observado; y la dosis de radiación se integraba con un factor de calidad Q = 1
que **subestimaba la dosis equivalente unas dos veces y media**.

Esa última se validó contra datos reales: la serie de DosTel del 2022-04-01
(2391 muestras, 24 h) daba 0,272 mSv/día con Q = 1 —por debajo del rango
documentado de 0,3-0,8 para la ISS— y 0,647 con el factor de calidad medio
medido en vuelo, en el centro del rango. El sistema informaba de menos radiación
de la que realmente recibe la tripulación.

---

## Fuentes de datos

| Fuente | Uso | Autenticación |
|---|---|---|
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | Distancia y tiempo de luz | No |
| [OSDR RadLab](https://visualization.osdr.nasa.gov/radlab/) | Dosimetría real de la ISS | No |
| [NASA DONKI](https://api.nasa.gov/) | Eventos de partículas solares | `api_key` gratuita |
| [OSDR Biodata](https://visualization.osdr.nasa.gov/biodata/api) | Evidencia biológica | No |
| Crossref, DataCite, PubMed y ClinicalTrials.gov | Comprobar que la fuente citada en una firma (DOI, PMID o NCT) existe en su registro; sin red se declara no resoluble | No |
| [MMASH](https://physionet.org/content/mmash/1.0.0/) (PhysioNet, ODbL v1.0) | Validación del motor de medida y de la tasa de falsa alarma con 22 personas sanas en Tierra; no valida fisiología de vuelo | No |
| [HC18](https://doi.org/10.5281/zenodo.1327317) (CC BY 4.0) | Validación del motor de medida ecográfica | No |
| [OSDR OSD-569](https://osdr.nasa.gov/bio/repo/data/studies/OSD-569) | Hemograma real de la tripulación de Inspiration4, reproducido en la demo | No |
| [TotalSegmentator dataset](https://doi.org/10.5281/zenodo.10047292) (CC BY 4.0) | TAC reales de ejemplo del visor 3D y validación de la segmentación | No |
| [BodyParts3D](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/) 4.0 (CC BY 4.0) | Esqueleto de referencia del modo anatómico: vista anterior y centroide de cada hueso, derivados del atlas, que no se empaqueta | No |
| [Ecografía pulmonar](https://doi.org/10.17632/hb3p34ytvx.2) (Katumba 2025) y [hígado en modo B](https://doi.org/10.5281/zenodo.1009146) (Byra 2018), CC BY 4.0 | Ecografías reales de ejemplo que viajan en el paquete, sin calibrar y firmadas como simuladas | No |

La NASA no publica ecografías, ni de tripulación ni de animales: la búsqueda y las licencias de
cada dataset están en [`compliance/imaging-data-provenance.md`](compliance/imaging-data-provenance.md).

Los hallazgos reales de integración —incluido que una consulta mal acotada a
RadLab devuelve **435 MB**— están en
[`backend/spikes/HALLAZGOS.md`](backend/spikes/HALLAZGOS.md).

---

## Estructura

```
backend/
  app/
    core/        ledger de integridad, almacén, caché, configuración, salida a la red
    ingest/      catálogo de códigos, FHIR, simulador, wearable, PVT
    environment/ efemérides, DONKI, RadLab, dosimetría, hábitat
    analysis/    línea base, tendencia, riesgo
    advisor/     recomendaciones y contramedidas
    evidence/    enlaces a HRP y OSDR, gradación de evidencia, comprobación de citas
    imaging/     ecografía: DICOM, protocolos, medida, fotogramas, fantomas
    volumes/     TAC y RM: segmentación, mallas y visor 3D (de Polaris)
    reports/     informes escaneados: OCR local, des-identificación, analíticas
    pain/        mapa corporal de dolor: zonas, tipos, validación del informe
    interpret/   borrador de interpretación con un modelo local
    polaris/     único punto de entrada al código copiado de Polaris
    validation/  MMASH, HC18 e inyección de deterioros
    api/         rutas FastAPI
    data/        datos que viajan con la aplicación
  packaging/     congelado del backend para la aplicación de escritorio
  scripts/       descarga de datasets, campañas de mutantes, sincronización de Polaris
  spikes/        validación de APIs externas + hallazgos
  tests/
frontend/        consolas de tripulación y de Tierra (React, TypeScript)
desktop/         aplicación de escritorio (Electron)
polaris/         copia literal de Polaris (AGPL-3.0-or-later)
compliance/      documentación normativa
docs/            especificación del equipo y decisiones pendientes sobre Polaris
```

---

## Cumplimiento

| Documento | Cubre |
|---|---|
| [`record-integrity.md`](compliance/record-integrity.md) | 21 CFR 11.10, 45 CFR 164.312, ISO 27789 — ledger encadenado por hash, firma Ed25519, anclaje Merkle |
| [`clinical-decision-rationale.md`](compliance/clinical-decision-rationale.md) | Controles de riesgo ISO 14971 del motor clínico |
| [`risk-management-file.md`](compliance/risk-management-file.md) | ISO 14971 — veinticuatro peligros del sistema, sus controles y el riesgo residual que queda |
| [`software-safety-classification.md`](compliance/software-safety-classification.md) | IEC 62304 — por qué Clase B, clase por elemento, lista de SOUP y qué procesos no se cumplen |
| [`nasa-std-3001-traceability.md`](compliance/nasa-std-3001-traceability.md) | 15 requisitos de NASA-STD-3001 Vol 1 Rev C, con IDs y texto extraídos del PDF oficial |
| [`external-validation.md`](compliance/external-validation.md) | Validación contra MMASH: qué encontró y qué sigue roto. También el motor de medida ecográfica contra HC18 y la segmentación del visor 3D contra su referencia |
| [`imaging-data-provenance.md`](compliance/imaging-data-provenance.md) | Procedencia y licencia de cada dataset de imagen: los que se usan, los que viajan en el paquete y los que se buscaron y se descartaron |
| [`state-of-the-art.md`](compliance/state-of-the-art.md) | Dónde encaja EMMA frente a CHeCS, Astroskin, ExMC, CMO-DA, NEWS2, Epic y RT-PSM |
| [`hmi-state-of-the-art.md`](compliance/hmi-state-of-the-art.md) | La interfaz frente a Orion, Crew Dragon, Starliner, New Shepard, Open MCT y la consola BME; NASA-STD-3001 Vol 2 Apéndice F regla por regla, y dónde choca con IEC 60601-1-8 |

El requisito central del producto es **[V1 3004] h** — *"Assessing, recording,
monitoring, and trending vital signs and additional physiological and behavioral
health signs"* — y el mismo requisito nombra *"expected return time to Earth"*
entre los parámetros de diseño del sistema médico, que es justo lo que implementa
el factor de aislamiento. El límite de dosis de carrera de 600 mSv que usa el
sistema es el de **[V1 4030]**, verbatim.

**Alcance declarado con precisión:** el sistema se desarrolla **conforme a
IEC 62304 Clase B**, salvo el borrador de interpretación con modelo de lenguaje, que se clasifica
**Clase C** por elemento y está segregado del motor
([`software-safety-classification.md`](compliance/software-safety-classification.md) §2.1). La *certificación* la emite un organismo notificado sobre
una organización con sistema de gestión de calidad auditado — es una puerta
institucional, y este proyecto no la reclama.

El sistema es **apoyo a la decisión, no prescripción**: informa y recomienda, no
administra terapia ni sustituye el juicio clínico.

---

## Licencia

EMMA es software libre bajo la **GNU Affero General Public License v3.0 o posterior**
([`LICENSE`](LICENSE)). Titular y código de terceros incorporado: [`NOTICE`](NOTICE). Los datos de
terceros que viajan con la aplicación conservan su propia licencia (CC BY 4.0 las ecografías de
ejemplo; ver [`compliance/imaging-data-provenance.md`](compliance/imaging-data-provenance.md)).
La licencia de cada dependencia, modelo y dato que usa el repositorio, en una sola página:
[`LICENCIAS.md`](LICENCIAS.md).

---

## Reconocimientos

EMMA incorpora código de [Polaris](https://github.com/BeyondTheProtocol/polaris) (AGPL-3.0-or-later,
© 2026 la autora de Polaris, «Beyond the Protocol»), de dos maneras:

- **Copia literal.** `polaris/` guarda sus herramientas, pruebas, evaluaciones y documentos byte a
  byte, del commit que fija `polaris/ADOPTADO.txt` y con la huella de cada fichero en
  `polaris/MANIFEST.sha256`. EMMA la llama por un único punto de entrada (`backend/app/polaris/`).
  Los cambios a la copia se deciden uno a uno y están en `polaris/CAMBIOS.json`; lo pendiente de
  decidir, en [`docs/polaris-divergencias.md`](docs/polaris-divergencias.md).
- **Adaptación a mano**, de antes de esa regla: algunos ficheros de EMMA siguen llevando código de
  Polaris modificado, y cada uno dice en su cabecera de dónde sale y qué se cambió (AGPL §5a).

De Polaris vienen, entre otras cosas:

- **La verificación del borrador:** el linter de afirmaciones fuertes y los léxicos de acción
  clínica (`text_guard.py`), el cotejo de presencia y ausencia (`interpret/cotejo.py`), la guarda
  contra inyección de los prompts, la firma atada a la huella del texto leído, el comité de
  verificadores de casas distintas (aquí Qwen y Gemma, locales) con su dosier y su banco de
  pruebas (`committee_dossier.py`, `committee_bench.py`) y la segunda firma de otra persona para
  una decisión de alto riesgo (`decision_risk.py`).
- **La evidencia:** la gradación desde el registro de PubMed (`evidence/tier.py`), la comprobación
  de que cada cita existe en su registro (`evidence/citations.py`) y de que cada cifra que EMMA
  atribuye a un artículo está en su resumen (`evidence/support.py`).
- **La imagen, los informes y el dolor:** el visor 3D de volúmenes con su segmentación, medidas
  y mallas (`volumes/`, `frontend/src/volumes/`), el OCR local de informes escaneados
  (`reports/ocr.py`) con su des-identificación verificada (`reports/deid.py`) y la lista
  conservadora de síntomas que conviene comentar pronto (`pain/alarm.py`).
- **El día a día:** la crónica y lo que depende de cada dato (`timeline.py`), las medidas
  periódicas que dejan de llegar (`routines.py`), lo que espera por una persona (`waiting.py`), la
  exportación a PDF (`export.py`), la búsqueda local en la documentación (`kb.py`) y el dictado
  de notas (`voice.py`).
- **Las defensas de la casa:** el control de lo que sale a la red (`core/egress.py`), el techo de
  memoria de los procesos pesados (`memguard.py`) y las campañas de mutantes que comprueban que
  cada defensa tiene una prueba que la vigila (`scripts/mutants.py`).

El inventario, con el fichero de origen de cada pieza, está en [`NOTICE`](NOTICE). Lo que no
encaja en EMMA queda fuera o inalcanzable: los cerebros de nube de Polaris van en la copia, pero
EMMA solo le da un modelo local; no se copian los perfiles y contactos de personas reales ni la
fontanería de macOS de su autora; y del visor web se quitaron, como cambio declarado, los textos
del caso original (informe, marcas del radiólogo, PET).
