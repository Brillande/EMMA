# MVP, RIDGE mínimo, fuentes y guion de datos

Qué enseña EMMA como producto mínimo en el NASA Space Apps 2026, qué parte de RIDGE cubre, de qué
fuentes depende y qué datos pasan por la demo, en qué orden. Se escribió el 2026-11-14 a partir de
la especificación del equipo (`docs/contexto/especificacion-tecnica-v1.1.md`, §9 y §14), su
comparación con EMMA (`docs/contexto/README.md`), el guion del vídeo (`docs/entrega/guion-video.md`)
y el código.

**Regla:** este documento no copia cifras que cambian con el código (métricas, cuentas de
indicadores). Apunta a su fuente de verdad. Lo que dice que EMMA hace se ha comprobado en el código.

## Progreso

| # | Sección | Estado |
|---|---------|--------|
| 1 | MVP: qué entra y qué no | hecha (2026-11-14) |
| 2 | RIDGE mínimo | hecha (2026-11-14) |
| 3 | Fuentes del MVP | hecha (2026-11-14) |
| 4 | Guion de datos de la demo | hecha (2026-11-14) |
| 5 | Comprobación en la aplicación | hecha (2026-11-14) |

---

## 1. MVP: qué entra y qué no

### La frase

> Una tripulación sin consulta en tiempo real con Tierra ve, sin red, que su salud se aparta de su
> propia normalidad, por qué, con qué fuente, qué puede hacer y si ha servido; y Tierra ve lo
> mismo con el retardo de verdad.

Es el caso que la especificación propone (§9, «evento de radiación»: detectar, dar contexto,
referir el procedimiento y seguir) y el que la base de conocimiento da como demostrativo (§14:
«evento de radiación/entorno + exposición personal + estado fisiológico + procedimiento/refugio +
monitorización posterior»).

### El caso que se enseña: evento solar sin red y vuelta a la normalidad

Es el escenario `spe-event-recovery` (`backend/app/ingest/simulator.py`, `Scenario.SPE_EVENT_RECOVERY`),
el mismo que la escena 5 del vídeo (`guion-video.md`). En una línea:

1. Sube la tasa de dosis y cruza su límite.
2. EMMA lo detecta contra la línea base personal.
3. Lo explica con las variables que lo mueven y su fuente.
4. Recomienda trasladarse al módulo con más blindaje (contramedida `rad-shielded-module`). El refugio de Orion (`rad-storm-shelter`) solo se propone con un evento solar **activo** de DONKI, y sin red no lo hay (ver §5).
5. Intensifica la monitorización (`app/routines.py`).
6. Enseña la vuelta a la normalidad.

Todo esto con la red cortada.

**Caso de reserva**, si el jurado pregunta por varias señales a la vez: `co2-fatigue`. El CO₂ de
cabina sale de límite y afecta a toda la tripulación (especificación §9, «CO2/fatiga»). Demuestra la
correlación con el hábitat.

### Criterios de aceptación de la especificación (§14)

EMMA los cumple todos. La tabla con el dónde de cada uno está en `docs/contexto/README.md`,
«Criterios de aceptación del MVP (§14)», que es la fuente de verdad. Resumen, con lo que el caso
enseña de cada uno:

| Criterio §14 | Cómo lo enseña el caso |
|---|---|
| Un único comando documentado | El instalador de escritorio (`docs/entrega/demo-en-directo.md`), o `uvicorn app.main:app` |
| Un escenario reproducible | `spe-event-recovery`, determinista (escenario y semilla en `model_version`) |
| Línea base individual y desviación persistente | La tasa de dosis contra la base de esa persona (`analysis/baseline.py`, `analysis/trend.py`) |
| Una variable de hábitat o misión | El retardo con Tierra calculado en local (SPICE) y la radiación del entorno (DONKI) |
| Alerta explicada con variables y fuente | El detalle de la alerta, con su ficha del registro de evidencia |
| Contramedida estructurada, seguimiento y confirmación humana | `rad-shielded-module`: adoptar y cerrar se firman en el registro |
| Medido, inferido o predicho | La dosis equivalente sale rotulada como INFERIDA (factor Q) |
| Funciona sin red | Modo avión. Instantánea fechada de DONKI y núcleos SPICE en el paquete |
| Pruebas de esquemas, base, alerta, evidencia y fail-safe | `backend/tests`, campañas de mutantes |

### Lo que entra en el MVP

- **Las dos consolas:** tripulación, y Tierra con el retardo aplicado.
- **El motor:** línea base personal, tendencia, riesgo escalado por el retardo y alertas explicadas.
- **Las contramedidas:** la biblioteca y el seguimiento firmado.
- **La integridad:** el registro encadenado y firmado (ledger).
- **El entorno:** DONKI, SPICE y Horizons, la dosimetría con su factor de calidad y la cabina.
- **Las garantías:** el modo sin red y la validación externa (MMASH y deterioros inyectados).

### Lo que existe pero no es el núcleo del MVP

Son añadidos fuera del MVP de la especificación (`docs/contexto/README.md`, «Añadidos fuera del MVP
de la especificación»). Se enseñan si hay tiempo y no sostienen la demo:

- Ecografía guiada.
- Visor 3D de TAC (imagen de referencia previa al vuelo o de Tierra: hoy no vuela ningún TAC).
- Mapa de dolor.
- Informes escaneados con OCR.
- Borrador del modelo de lenguaje (Clase C, segregado).
- Asistente de voz.
- Planificador (Marplanner).
- Modos de misión.

### Lo que no se afirma

- **No está certificado.** Está desarrollado conforme a IEC 62304 Clase B (invariante 6).
- **No prescribe:** apoyo a la decisión (invariante 7).
- **No valida fisiología espacial.** MMASH valida el motor y la falsa alarma, en Tierra.
- **No hay datos de constantes de astronautas:** no son públicos. Los datos vienen del simulador
  declarado, de Inspiration4 (OSDR) y de wearables reales.

---

## 2. RIDGE mínimo

RIDGE son los cinco peligros con que NASA ordena los riesgos del vuelo humano (fuente: NASA, *The
Human Body in Space*). Cada dominio clínico de EMMA lleva su letra en el código (`Domain.ridge` y
`_DOMAIN_RIDGE` en `backend/app/ingest/codes.py`), y `GET /api/risks` sirve el riesgo entero con su
categoría RIDGE.

### Cada letra, con qué dominio la cubre EMMA y con qué escenario se ve

| Letra | Peligro | Dominios de EMMA | Escenario que lo enseña | ¿En el MVP? |
|---|---|---|---|---|
| **R** | Radiación | radiación | `spe-event-recovery` (y `spe-event`): sube la tasa de dosis | **Sí, es el caso central** |
| **I** | Aislamiento y confinamiento | conductual (sueño, PVT, ánimo, cognición) | `progressive-insomnia`, `transient-sleep-loss`; `co2-fatigue` también lo mueve | Opcional |
| **D** | Distancia de la Tierra | nutrición (la comida va entera desde el lanzamiento) **y**, sobre todo, la autonomía: el retardo con Tierra escala el riesgo (`risk.isolation_factor`) y la consola de Tierra lo aplica | `menu-fatigue` para nutrición; el retardo está en **todos** los escenarios | **Sí, dentro del caso central** |
| **G** | Campos gravitatorios | cardiovascular, óseo, neuro-ocular, genitourinario, musculoesquelético | `cardiovascular-deconditioning`, `arrhythmia`, `dehydration`; la banda ósea inferida (especificación §9, musculoesquelético) | Opcional |
| **E** | Entorno hostil y cerrado | inmune y la cabina (CO₂, O₂, presión, temperatura, humedad, ruido, contaminantes, con límites de NASA-STD-3001 Vol 2) | `co2-fatigue` (cabina), `immune-reactivation` | **Sí, como caso de reserva** |

### El mínimo y por qué

**El MVP cubre R, D y E.** Es lo mínimo que hace creíble la premisa del reto, una tripulación lejos
de la Tierra y sin consulta en tiempo real:

- **R:** el caso central es un evento de radiación, el peligro agudo de una misión.
- **D:** la distancia es lo que obliga a la autonomía. El retardo calculado en local (SPICE) entra en
  el riesgo y en la consola de Tierra. Sin D, el resto sería una pulsera de actividad.
- **E:** el CO₂ de cabina demuestra que una alteración compartida por la tripulación apunta al
  hábitat y no a una persona (especificación §9, «CO2/fatiga»).

**I y G están hechos y se pueden enseñar,** pero no hacen falta para demostrar la premisa. Quedan
para preguntas del jurado.

### Lo que hay que decir para no exagerar (invariante 6)

- **D no tiene dominio clínico propio** salvo nutrición. En EMMA es la autonomía que el sistema
  entero suple, y así lo dice el código (`codes.py`, comentario de `_DOMAIN_RIDGE`).
- **El escenario `co2-fatigue` cruza letras.** La causa es E (la cabina), pero lo que mueve son
  indicadores conductuales (sueño y PVT), que EMMA pone bajo I, y la carga de síntomas, que pone
  bajo inmune (E). Se enseña como lo que es: una causa ambiental con efecto en varios dominios.
- **Cubrir una letra no es cubrir todos sus riesgos del HRP.** Qué riesgos del Human Research
  Roadmap vigila EMMA y cuáles deja fuera, con su motivo, lo da `GET /api/risks/hrp-coverage`
  (`backend/app/data/hrp_risks_coverage.json`). Esa es la fuente de verdad; aquí no se copian
  cuentas.
- **La asignación de dominio a letra es de EMMA,** leída en la página de NASA citada. No es una
  tabla oficial de NASA dominio por dominio.

---

## 3. Fuentes del MVP

Este es el subconjunto del que depende el caso central y su reserva. La procedencia completa de
todo EMMA, con licencias y fecha de lectura, está en `docs/fuentes-y-procedencia.md` (se cita su
sección con §). Las fichas son las del registro de evidencia (`backend/app/data/evidence_refs.json`),
y `docs/fuentes-registro-evidencia.md` las lista todas.

### R: el evento de radiación

| Qué sostiene | Fuente | Dónde se documenta |
|---|---|---|
| El evento solar real, también sin red | NASA DONKI (api.nasa.gov) e instantánea fechada `backend/app/data/donki_snapshot.json`, obra del Gobierno de EE. UU. | §3 |
| La dosis medida en vuelo | OSDR RadLab (DosTel) | §3 |
| Dosis equivalente con Q = 2,38, rotulada INFERIDA | Badhwar 1992, TEPC en SLS-1 (ficha `badhwar-1992-sls1-tepc`, PMID 11537535) | §3 y §4 |
| El límite de carrera de 600 mSv | NASA-STD-3001 Vol 1 Rev C [V1 4030], PDF oficial | §4 y §21 |
| El blindaje como principio («interponer masa de baja densidad») y el refugio de Orion («within an hour… as long as 24 hours»), que solo se propone con un evento solar activo | NASA, plan de protección de Orion (ficha `nasa-orion-radiation-protection`) | §5 (`rad-shielded-module`, `rad-storm-shelter`) |
| Que la dosis cuente para el refugio, y HERA | Fichas `nasa-artemis1-radiation-research` y `nasa-artemis2-eyes-on-sun` | §4 |

### D: la distancia y la autonomía

| Qué sostiene | Fuente | Dónde se documenta |
|---|---|---|
| El retardo con Tierra sin red | NAIF SPICE (`naif0012.tls`, `de432s.bsp`), redistribuible sin modificar (`naif.jpl.nasa.gov/naif/rules.html`) | §3 |
| El contraste y el respaldo del retardo | JPL Horizons, vía `astroquery` | §3 |
| El escalado del riesgo por el retardo | **Diseño de EMMA, sin fuente** (factor de aislamiento): se dice así | §4 |

### E: la cabina (caso de reserva)

| Qué sostiene | Fuente | Dónde se documenta |
|---|---|---|
| Límites de CO₂ y del resto de la cabina | NASA-STD-3001 Vol 2 Rev F ([V2 6004] y siguientes); OCHMO-TB-002 Rev B (ficha `ochmo-tb-002`) | §3 |
| CO₂ y cefalea | Law et al. 2014 (ficha `law-2014`, PMID 24806559) | §4 |
| El efecto cognitivo del CO₂ es contestado | Scully et al. 2019 (ficha `scully-2019`, PMID 31240239) frente a Satish 2012 y Manzey 1998 | §2 (simulador) y §4 |

### Lo que sostiene a todo el MVP

| Qué sostiene | Fuente | Dónde se documenta |
|---|---|---|
| La taxonomía RIDGE | NASA, *The Human Body in Space* (ficha `nasa-human-body-in-space`) | §2 de este documento |
| Que la falsa alarma y la sensibilidad están medidas | MMASH (PhysioNet, ODbL v1.0; Rossi et al. 2020) y deterioros inyectados. Las cifras vigentes están en `compliance/external-validation.md` y en los tests `-m external` | §14 |
| Las observaciones normalizadas | LOINC (verificado en tx.fhir.org), HL7 FHIR R4 y UCUM | §2 |
| La integridad del registro | 21 CFR 11.10, 45 CFR 164.312 y RFC 6962 | §1 y §21 |
| La interfaz | NASA-STD-3001 Vol 2, Apéndice F (tabla de color F.5-1) y WCAG 2.2 | §19 y §21 |
| El código de terceros | Polaris (AGPL-3.0-or-later) y Marplanner (MIT) | §13 y §22 |

### Lo que el MVP usa sin fuente, y lo dice

- El factor de aislamiento.
- Las ventanas de la línea base.
- Los plazos de caducidad de los datos.

Son diseño de EMMA, declarado así en el código y en `docs/fuentes-y-procedencia.md` («Resumen de
huecos», punto 4).

---

## 4. Guion de datos de la demo

Qué datos entran, por dónde, en qué orden y qué deja cada paso en el registro. Va en paralelo al
guion del vídeo (`docs/entrega/guion-video.md`, escena 5) y a la presentación
(`docs/entrega/presentacion.md`, paso 3), y no los sustituye.

### Antes de empezar: qué viaja en el paquete

La demo se hace **sin red** (modo avión). Lo que la aplicación de escritorio lleva dentro para no
necesitarla:

| Dato | Para qué | Cómo llega |
|---|---|---|
| Instantánea fechada de DONKI (`backend/app/data/donki_snapshot.json`) | Eventos solares reales, caducados y con su fecha (cian, F.5-1) | La aplicación de escritorio pone `EMMA_DONKI_SNAPSHOT=true` (`desktop/main.cjs`) |
| Núcleos SPICE comprobados | El retardo con Tierra calculado en local | Los empaqueta `backend/packaging/freeze.py` |
| Hemograma de Inspiration4 (OSD-569) | Datos humanos reales de una misión, para la recuperación posvuelo | `backend/app/data/osdr/` |
| Ejemplos de ecografía y TAC | Solo si se enseñan los añadidos | `backend/app/data/ultrasound_samples/`, `volume_samples/` |

### Los pasos, con el dato que se mueve en cada uno

| # | Qué se hace | Qué dato entra o se lee | Vía | Qué queda firmado en el registro |
|---|---|---|---|---|
| 1 | Abrir la aplicación | Arranca con el escenario **`spe-event`** (decisión del usuario, 2026-11-12: el que más estados en vigilancia deja al abrir) | `desktop/main.cjs`, `STARTUP_SCENARIO` → `POST /api/simulate?scenario=spe-event` | Lecturas simuladas de los cuatro tripulantes, firmadas con una identidad que las declara simuladas |
| 2 | **Cambiar al caso central** | Escenario **`spe-event-recovery`**: el mismo pico de dosis, pero antes en la ventana, para que se vea la vuelta | Selector de escenario de la consola → `POST /api/simulate?scenario=spe-event-recovery&replace=true` (solo sustituye si todo lo que hay es simulado; si no, 409) | Almacén nuevo con el escenario pedido. Semilla y escenario en `model_version` |
| 3 | Ver el retardo y el entorno | Retardo con Tierra (SPICE en local, Horizons de contraste), evento de DONKI (instantánea) y tasa de dosis | `GET /api/status` (`comms_status`, entorno), `GET /api/comms` | Nada: es lectura. Una discrepancia SPICE-Horizons sí se firmaría (`record-integrity.md` §3.30) |
| 4 | La alerta | La tasa de dosis contra la línea base personal: desviación y tendencia, riesgo escalado por el retardo. **Ojo:** el estado «de ahora» es el final de la ventana, cuando la dosis ya volvió. La alerta se ve **avanzando la línea temporal hasta el pico** (estado con `until`; ver §5) | `GET /api/status` (las alertas vienen dentro; su historia en `GET /api/alerts/history`) | Nada al detectarla: las alertas se derivan, no se guardan |
| 5 | Por qué | Variables que la mueven, ficha de evidencia y dosis equivalente **inferida** (Q de Badhwar 1992) | Detalle de la alerta en la consola | Nada |
| 6 | Reconocer la alerta | Una persona dice «la he visto» | `POST /api/alerts/acknowledge` | **Sí:** reconocimiento firmado por la consola, con quien lo firma |
| 7 | Adoptar la contramedida recomendada | `rad-shielded-module`, «Trasladarse al módulo con mayor blindaje disponible». El refugio de Orion (`rad-storm-shelter`) solo sale con un evento solar activo de DONKI, que sin red no hay | `POST /api/countermeasures/adopt` con el `reference_time` del estado que se ve | **Sí:** adopción firmada; empieza el seguimiento |
| 8 | Monitorización intensificada | Las rutinas exigen la dosis más a menudo mientras está por encima de su límite | `app/routines.py`, panel de rutinas | Nada nuevo: se deriva de las lecturas |
| 9 | La vuelta a la normalidad | La dosis vuelve a su fondo. La línea temporal enseña comienzo, intensificación y vuelta | Línea temporal (`app/timeline.py`), avanzando en el tiempo | Nada al verla |
| 10 | Cerrar el seguimiento | ¿Ha servido? Nivel del dominio al adoptar frente a ahora, con la advertencia de que coincidir no prueba causa | `POST /api/countermeasures/close` | **Sí:** cierre firmado con el nivel del dominio |
| 11 | Tierra | La consola de Tierra ve lo mismo **un tiempo de luz después** | Pestaña de Tierra (`groundCut` en la interfaz) | Nada: lee el mismo registro con el corte |
| 12 | La integridad | El registro encadenado y firmado verifica entero | Panel de integridad | Nada |

### Reserva: CO₂ de cabina (E)

`POST /api/simulate?scenario=co2-fatigue&replace=true`. Por ser un escenario ambiental, afecta a los
cuatro tripulantes a la vez (`ENVIRONMENTAL_SCENARIOS` en `ingest/simulator.py`). Se ve:

- El CO₂ por encima de [V2 6004].
- Sueño y PVT peores en todos.
- La contramedida de contrastar el sensor (`hab-co2-sensor-crosscheck`).

### Opcional: datos humanos reales

`POST /api/replay/inspiration4` coloca en la línea de tiempo el hemograma real de los cuatro
tripulantes de Inspiration4 (OSD-569), firmado como simulado porque no son de esta tripulación.
`GET /api/replay/recovery` enseña su trayectoria posvuelo frente a su propio prevuelo (los linfocitos
bajan al volver).

### Lo que el guion no hace

- **No mezcla escenarios.** Cambiar de escenario sustituye el almacén con `replace=true`, nunca
  suma uno encima del otro.
- **No inventa datos «en vivo»:** todo lo que se ve es del simulador declarado, de la instantánea
  fechada o de datos públicos con su cita.
- **No sale a la red.**

---

## 5. Comprobación en la aplicación (2026-11-14)

El guion de la sección 4 se ejecutó contra el backend real, en proceso (FastAPI `TestClient`):

- **Sin red:** `EMMA_OFFLINE=true`.
- **Con la instantánea de DONKI:** `EMMA_DONKI_SNAPSHOT=true`, como la aplicación de escritorio.
- **Desde cero:** caché vacía en una carpeta temporal, con los núcleos SPICE a su lado (en el
  instalador viajan dentro del paquete).
- **Con la configuración por defecto:** misión desde el 2026-11-01, 40 días y 24 muestras al día.

Las fechas de abajo salen de esa configuración. Si cambian el inicio o la duración, cambian con ellas.

### Resultado paso a paso

| # | Paso | Resultado |
|---|---|---|
| 1 | `POST /api/simulate?scenario=spe-event` | 201 |
| 2 | `POST /api/simulate?scenario=spe-event-recovery&replace=true` | 201, `replaced: true` |
| 3 | Retardo y entorno (`GET /api/status`) | Retardo **disponible, calculado en local con SPICE** («calculado en local (SPICE)… núcleo de432s.bsp»). DONKI: «instantánea de DONKI del 2026-11-13, no en vivo», **sin evento activo**, porque los de la instantánea ya pasaron |
| 4 | La alerta | En el estado «de ahora» (fin de la ventana) **no hay ninguna alerta**: la dosis ya volvió. Recorriendo la línea temporal con `until`: radiación en **precaución** del 30-nov al 5-dic, **vigilancia** del 6 al 9-dic y **nominal** el 10-dic. Es la trayectoria completa que promete el caso |
| 5 | Por qué | La recomendación cita la tasa de dosis por encima de su límite de peligro y subiendo semana a semana, con su fuente |
| 6 | Reconocer la alerta (30-nov) | 201 |
| 7 | Adoptar | `rad-shielded-module`: **201**, asiento firmado. `rad-storm-shelter`: **409** «no estaba recomendada», porque el refugio solo lo dispara un evento solar activo (`advisor/countermeasures.py`, `SHELTER_ID`) |
| 8 | Monitorización intensificada (`GET /api/timeline/routines`) | Tasa de dosis: cada **6 h** el 20-nov, cada **1 h** el 30-nov (en el pico) y otra vez cada **6 h** el 10-dic. Las dos cadencias se declaran parámetro de diseño de EMMA |
| 9 | Al final | Nivel nominal y el seguimiento de la adopción a la vista |
| 10 | Cerrar el seguimiento | 201, asiento firmado |
| Reserva | `POST /api/simulate?scenario=co2-fatigue&replace=true` | 201 |
| Opcional | `POST /api/replay/inspiration4` y `GET /api/replay/recovery` | 201 y 200 |

### Lo que la comprobación cambió en este documento

- **El refugio de Orion no sale en la demo sin red.** Las secciones 1, 3 y 4 decían que se proponía
  el refugio (`rad-storm-shelter`). Lo que EMMA recomienda con la dosis alta y sin evento solar activo
  es `rad-shielded-module`, trasladarse al módulo más blindado. Ya está corregido. Para enseñar el
  refugio hace falta un evento solar activo de DONKI, es decir, con red y un evento en curso.
- **La alerta no está en el estado «de ahora».** En `spe-event-recovery` hay que avanzar la línea
  temporal hasta el pico (30-nov a 5-dic con la configuración por defecto) y luego enseñar la vuelta.
  Así lo hace el guion del vídeo («se avanza en el tiempo»), que no promete el refugio y sigue siendo
  correcto.

### Lo que no se comprobó aquí

- **La interfaz:** se comprobaron las rutas que usa, no las pantallas.
- **La consola de Tierra:** aplica el corte del retardo en la interfaz (`groundCut`).
- **El instalador:** recompilarlo es aparte (`docs/entrega/demo-en-directo.md`).
