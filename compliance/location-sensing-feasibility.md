# Ubicación por anclas de módulo: viabilidad en vuelo

**Estado:** documento de diseño. Acompaña a `backend/scripts/anchor_gateway.py` (pasarela de
escucha) y al contrato `POST /api/location/sightings`. Fecha: 2026-11-10.

**Por qué existe.** El usuario pidió el 2026-11-10 que la ubicación del tripulante por módulo fuera
«real, no simulada», con balizas Bluetooth, pero «viable en el espacio». Este documento separa lo
que está documentado de lo que no, y explica qué decisiones de diseño se siguen de ahí. No es una
validación: **en un módulo metálico en vuelo, la precisión de zona por BLE no tiene respaldo**
(§3).

Clases de respaldo, las mismas que usa el simulador (`/api/status` → `simulation.evidence`):
**magnitud documentada**, **sentido documentado**, **contestado** y **sin respaldo**.

---

## 1. Precedentes

### 1.1 NASA JSC, Multi-Sensor Crew Device (MSCD): balizas BLE fijas, solo en Tierra

Leitgab M., Bautista J. *Multi-sensor Crew Device (MSCD) Project Status*, NASA JSC, 2019-01-24.
NTRS 20190001027. <https://ntrs.nasa.gov/citations/20190001027> (PDF leído el 2026-11-10).

- Motivación, diapositiva 2: «Correlated data with position on ISS».
- Diapositiva 8: «Using low power Bluetooth beacons (battery life 5 years) at fixed location»;
  ensayo con un iPad «in 3 m x 3 m x 2 m cubed area»; «Algorithm validated to measure location of
  iPad to 50-100 cm accuracy».
- Diapositiva 9, radiación en NSRL (abril de 2018), protones de 200 MeV hasta 70 Gy: «Numerous
  autonomous reboots during exposure» y «One latchup observed that was not resolved by watchdog
  after about 7 Gy of exposure; button press provided recovery».
- Diapositiva 11: el trabajo pendiente es «Work to prepare for operational use».

Lo que **no** dice: que volara. La presentación es un estado de proyecto con el uso operativo aún
pendiente; «nunca voló» es una inferencia de ese estado y de no haber encontrado constancia de
vuelo, no una frase del documento. La precisión de 50-100 cm se midió en un laboratorio de 3 × 3 ×
2 m en Tierra, no en un módulo.

Clase: **magnitud documentada** para el ensayo en Tierra y para los efectos de radiación sobre ese
equipo; **sin respaldo** para su extrapolación a un módulo en vuelo.

### 1.2 REALM-1: lectores RFID fijos en la ISS, en operación

McKinley M. K. *Logistics Reduction: RFID Enabled Autonomous Logistics Management Project
Introduction*, NASA JSC, 2021. NTRS 20210023626.
<https://ntrs.nasa.gov/citations/20210023626> (PDF leído el 2026-11-10).

- «REALM-1 infrastructure was developed and evaluated on ISS, with RFID open-air readers and
  antennas deployed in ISS Node 1, U.S. Laboratory, and Node 2.»
- «The REALM-1 core system was considered sufficiently matured in FY19 and was transitioned to an
  operational ISS system».

Es el precedente del patrón que adopta EMMA: **la infraestructura fija es de la nave**, y lo que se
localiza (allí, la carga etiquetada) no lleva la infraestructura encima.

Clase: **sentido documentado** (anclas fijas instaladas y operadas en la ISS). No da una precisión
por módulo aplicable a personas.

### 1.3 Multitrayecto en la ISS: REALM descarta el RSSI

Bhattacharya S. S., Rodriguez L., Fink P. *Short Window Intra-Spacecraft RFID Localization*, IEEE
RFID 2024. NTRS 20240000652. <https://ntrs.nasa.gov/citations/20240000652> (PDF leído el
2026-11-10).

- «The small interiors of space stations (such as the ISS) coupled with their metallic
  construction offer a highly noisy environment for RFID systems.»
- «We do not consider the RSSI value, or phase of readings gathered […] This is because our target
  environments (ISS, Wireless Testbed) are constructed from metal, and introduce noise into RSSI
  via multipath.»

Es RFID UHF, no BLE a 2,4 GHz, pero el mecanismo (reflexión en paredes metálicas) es el mismo
fenómeno físico. Clase: **sentido documentado** (el RSSI se degrada en un módulo metálico); la
magnitud a 2,4 GHz con BLE: **sin respaldo**.

### 1.4 DLR Wireless Compose: UWB con anclas fijas en Columbus (2018-2019)

DLR, Instituto de Sistemas Espaciales, página del proyecto
<https://www.dlr.de/en/irs/research-transfer/projects-missions/past-projects/wireless-compose>
(leída el 2026-11-10).

- Tecnología «Impulse Radio - Ultrawideband (IR-UWB)»; 5 anclas fijas en el módulo Columbus y 2
  etiquetas que lleva el astronauta; operación en la ISS «06. Jun 2018 – Jan 2019».
- La página plantea la viabilidad y la precisión del posicionamiento en el módulo como objetivo de
  investigación, **pero no publica ninguna precisión medida**.
- Nota de prensa del DLR (13-07-2018), seguimiento de Alexander Gerst durante 30 minutos:
  <https://www.dlr.de/en/latest/news/2018/3/20180713_alexander-gerst-the-horizons-mission-radiation-exposure-protection-and-indoor-tracking-on-the-iss_28896>
  (hallada por búsqueda; su texto no se ha releído en esta sesión).

Clase: **sentido documentado** (UWB con anclas fijas ha volado y ha seguido a una persona dentro de
un módulo). Precisión: **sin respaldo** público.

### 1.5 Astroskin (Agencia Espacial Canadiense)

Prenda de monitorización de constantes usada en la ISS. Es precedente de *wearable* en vuelo, no de
localización. **No reverificado en esta sesión**: la página de la CSA no respondió (conexión
reiniciada). No se cita ningún dato suyo aquí.

### 1.6 ICAres-1 / Lunares (EWSN 2020)

Referencia aportada en la investigación previa (localización de tripulantes en un hábitat
análogo). **No encontrada en esta sesión**: una búsqueda no devolvió el artículo. Queda como no
verificada y no sostiene ninguna afirmación de este documento.

---

## 2. Restricciones de vuelo

| Restricción | Fuente | Qué se sabe | Clase |
| --- | --- | --- | --- |
| EMC | McCollum M., Kim L., Lowe C. *Electromagnetic Compatibility Considerations for International Space Station Payload Developers*, IEEE Aerospace 2020. NTRS 20200002330, <https://ntrs.nasa.gov/citations/20200002330> (PDF leído) | «The ISS electromagnetic interference (EMI) requirements and test methods are based on MIL-STD-461»; SSP 30237 se describe como derivado de MIL-STD-461B; «The selection and use of commercial-off-the-shelf (COTS) equipment for ISS applications requires special considerations to meet both EMC and crew safety requirements.» | sentido documentado |
| Límites de emisión radiada a 2,4 GHz (RE02 de SSP 30237) | — | El artículo no da los límites ni habla de 2,4 GHz. | **sin verificar** |
| Baterías | JSC 20793 (requisitos de seguridad de baterías de la tripulación) | Toda batería a bordo pasa por esa norma; el documento **no se ha leído** en esta sesión. | **sin verificar** en sus detalles |
| Radiación | MSCD (§1.1) | Reinicios y un latch-up hacia 7 Gy en un equipo comercial con BLE. Una baliza con pila no tiene botón ni vigilancia: un latch-up la deja muda hasta que alguien la toque. | magnitud documentada (ese equipo) |
| Multitrayecto en metal | REALM 2024 (§1.3) | El RSSI se vuelve ruidoso en un módulo metálico. | sentido documentado |
| Sombra del cuerpo | Hadian 2023, Kiarashi 2023 (§3) | En Tierra, los errores de zona se concentran donde las señales de dos balizas compiten; la atenuación por el cuerpo no se cuantifica en esas fuentes. | sentido documentado (fronteras); magnitud **sin respaldo** |

---

## 3. Precisión documentada de la ubicación por zona con BLE

Las dos fuentes son **en Tierra**, en edificios no metálicos. Ninguna mide un módulo de nave.

- Hadian K., Fernie G., Roshan Fekr A. *Development and Evaluation of BLE-Based Room-Level
  Localization to Improve Hand Hygiene Performance Estimation*. J Healthc Eng 2023,
  doi:10.1155/2023/4258362. <https://pmc.ncbi.nlm.nih.gov/articles/PMC9904895/>.
  Nueve voluntarios en una habitación simulada de 5 × 5 m: «achieved the best accuracies of 81% and
  71% in the binary and multiclass classifications, respectively». Son zonas dentro de una
  habitación, no habitaciones distintas.
- Kiarashi Y. et al. *Graph Trilateration for Indoor Localization in Sparsely Distributed Edge
  Computing Devices in Complex Environments Using Bluetooth Technology*. Sensors 2023;23(23):9517.
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10708633/>. 39 dispositivos BLE en un centro de 1700 m²:
  «over 85% accuracy in region-level localization»; por región, de 66,67 % (salón) a 96,29 %. Los
  errores aparecen cuando los dispositivos más cercanos están «in the boundary of signal ranges», y
  la ventana deslizante puede ocultar transiciones reales.

| Afirmación | Clase |
| --- | --- |
| BLE por zona acierta del orden de 71-85 % en Tierra | magnitud documentada (Tierra) |
| Los errores se concentran donde compiten dos balizas | sentido documentado |
| Esa precisión se mantiene en un módulo metálico | **sin respaldo** |
| Precisión de UWB en Columbus | **sin respaldo** público (§1.4) |

---

## 4. Lo que queda sin verificar

Se lista para que nadie lo dé por hecho. Ninguno de estos puntos sostiene una decisión de EMMA.

1. Los límites RE02 de SSP 30237 en la banda de 2,4 GHz y si una baliza BLE comercial los cumple.
2. Qué exige JSC 20793 a una pila de botón (litio) en concreto: ensayos, contención, excepciones.
3. Coordinación del espectro de 2,4 GHz a bordo (Wi-Fi de la estación y otros emisores).
4. Desgasificación (*offgassing*) de las carcasas y adhesivos de las balizas.
5. Efecto de la microgravedad en la orientación del cuerpo y del wearable respecto a las balizas
   (en Tierra el wearable está casi siempre a la misma altura y con la misma orientación).
6. Efecto de las escotillas abiertas o cerradas entre módulos sobre la señal.
7. La cifra «20 dB por mamparo», que circuló en la ideación: **no tiene fuente** y no se usa.
8. Que el MSCD no volara: inferencia del estado del proyecto (§1.1), no afirmación del documento.
9. Astroskin e ICAres-1/Lunares: no reverificados (§1.5, §1.6).

---

## 5. Qué exige esto al diseño de EMMA

1. **Las anclas son equipo de la nave**, certificado y alimentado por ella, como los lectores de
   REALM y las anclas de Wireless Compose. EMMA no añade emisores ni pilas: ni balizas con pila de
   botón (§2, baterías y radiación), ni emisión desde el wearable. La pasarela
   (`scripts/anchor_gateway.py`) **solo escucha**: escaneo pasivo, sin conectarse a nada; si el
   sistema no permite el pasivo, se para en vez de caer al escaneo activo, que emitiría peticiones
   de escaneo. Solo habla con el backend propio en loopback o en la red local de la nave, nunca con
   internet (por eso no pasa por `app/core/egress.py`, y rechaza cualquier destino que no sea una
   IP local).
2. **La granularidad es el módulo, nunca metros.** Ninguna fuente respalda metros dentro de un
   módulo metálico. Se compara el RSSI de las anclas en una ventana, con histéresis; la pasarela
   resume cada ancla por ventana con la mediana. Ventana, margen, permanencia y caducidad son
   **sin respaldo: calibrar en cada nave** (`backend/app/data/location_sensing.json`).
3. **Estado «indeterminado (entre módulos)».** Cuando dos módulos compiten —justo donde la
   literatura pone los errores (§3)— no se fuerza una respuesta.
4. **Manda lo que declara una persona** en la consola, aunque haya lecturas posteriores. Lo
   estimado se muestra como estimado y con su antigüedad.
5. **Sin anclas declaradas, la ubicación medida está «no disponible».** Sin `bleak` instalado, la
   escucha en vivo también lo está (código 3 de la pasarela): no rompe nada.
6. **La ubicación no entra en el riesgo ni en las alertas**: solo ordena hipótesis (invariante 5).
   Una estimación errónea no puede subir ni bajar un nivel.
7. **Alternativa con vuelo documentado: UWB** (Wireless Compose, §1.4). La pasarela nombra la
   tecnología de forma neutra («ancla de módulo»); UWB o el RFID de la nave podrían entrar por el
   mismo contrato (`anchor_id`, `rssi_dbm`, `at`), aunque UWB mediría distancia y no RSSI, y eso
   pediría ampliar el contrato.

---

## 6. Alcance

Esto no valida la ubicación en vuelo ni la certifica. Dice qué está documentado, qué no, y por qué
el diseño se limita a módulos, a anclas de la nave y a apoyo a la decisión. La pasarela se ha
probado sin radio (análisis de tramas con bytes fijos y envío simulado,
`backend/tests/test_anchor_gateway.py`); **no se ha probado con balizas reales**.
