# Estado del arte: dónde encaja EMMA

**Revisión:** 2026-09-20; fila de HERMES, 2026-10-26

EMMA se construyó razonando desde primeros principios. Este documento lo contrasta
con lo que ya existe en monitorización fisiológica autónoma —aeroespacial, civil y
militar— para situarlo en el conjunto: qué decisiones quedan validadas por
literatura ajena, y qué límites documentados hay que respetar.

---

## 1. El mapa

### Aeroespacial

| Sistema | Qué hace | Su límite |
|---|---|---|
| **CHeCS** (ISS) | Sistema de salud de la ISS: mantenimiento, salud ambiental, contramedidas | Diseñado para órbita baja **con cirujano de vuelo a minutos de distancia**. No es autónomo |
| **Bio-Monitor / Astroskin** (CSA) | Camiseta con ECG de 3 derivaciones, SpO₂, respiración, presión, temperatura y actividad — 48 h continuas. En la ISS desde 2019 | Es **adquisición**, no interpretación. Resuelve el sensor, no la decisión |
| **EveryWear** (CNES) | Tableta que integra funciones de salud con los wearables | Registro e integración; el juicio clínico sigue en Tierra |
| **ExMC** (NASA HRP) | Capacidad médica de exploración: define la **AMCL** (lista de condiciones médicas aceptadas), soporte a la decisión, guía procedimental y formación *just-in-time* | Marco y requisitos, no producto desplegado |
| **CMO-DA** (NASA + Google) | Asistente digital de oficial médico: diagnóstico por texto, imagen y voz cuando no hay médico a bordo | **Episódico y reactivo**: responde cuando ya hay un síntoma. Corre sobre **Vertex AI, en la nube** |
| **HERMES** (TRISH, acuerdo de cooperación del HRP) | Plataforma de datos de salud, rendimiento, investigación y entorno: agrega lo que dan dispositivos médicos, sensores ambientales y la misión, lleva el historial de cada persona de un vehículo a otro y lo reparte a la propia persona, a su equipo médico, a investigadores y a «algorithmic users». Pensada para conectividad limitada («edge-first»). Según NASA, para que la tripulación tenga la información de salud con que decidir lejos de la Tierra | Lo leído es la descripción que publican NASA y Baylor, no una evaluación: **dice que permite «detect early changes», pero no se ha encontrado cómo, si compara con una línea base personal, con qué se ha validado ni si ha volado**. Ver debajo |

**HERMES frente a EMMA (leído el 2026-10-26).** La conversación de ideación del equipo pone a TRISH
en el mapa y abre la categoría «Existing Software / Open Source / Prior Art»; de HERMES no se había
leído nada más que una frase. De lo leído, es lo más parecido a EMMA que tiene el programa de NASA:

- **La página de NASA** (sección del HRP, actualizada el 18 de mayo de 2026) lo llama «a health and
  research data management platform, known as the Human and Environmental Research Matrix for
  Exploration of Space (HERMES)», que «aims to provide astronauts with the health information they
  need to make informed medical decisions on distant missions from Earth». Sus frases están en
  `/api/framework` (bloque `hermes`, ficha `nasa-trish`).
- **La página de Baylor College of Medicine**, a la que enlaza (sin fecha a la vista): «a real-time,
  customizable and configurable medical, health, performance and environmental data platform that
  enables teams to monitor, detect early changes, and guide response»; «a layered, edge-first
  architecture»; cuatro funciones —agregación de datos de salud y rendimiento, software
  independiente del vehículo, interoperabilidad de fuentes y usuarios, y atención remota—; y que las
  herramientas de IA «strengthen our ability to diagnose and treat autonomously […] without
  replacing clinicians».
- **La nota de Baylor del 1 de noviembre de 2023**: TRISH seleccionó dos proyectos de su convocatoria
  de HERMES. Ejenta: un agente de IA y dispositivos por participante, un panel clínico para el
  oficial médico, el control de misión y los investigadores, y alertas de cambios en la salud o en
  el entorno del vehículo, sobre «HERMES Edge Computers» que funcionan sin nube. TrialX: un
  repositorio portátil sin conexión que se sincroniza al volver.

**En qué se parecen:** los dos parten de que la tripulación tendrá que decidir sin Tierra en tiempo
real, juntan salud, rendimiento y entorno, y funcionan sin nube. **En qué no:** HERMES es la capa de
datos —recoger, guardar, mover el historial de una nave a otra y repartirlo— y el análisis lo ponen
las herramientas que se le conectan; EMMA es una sola aplicación cuyo peso está en comparar cada
lectura con la línea base del propio tripulante, explicar la desviación y citar la evidencia de cada
recomendación, con un registro encadenado y firmado. EMMA no lleva el historial entre vehículos ni
se conecta a HERMES. Nada de esto es una comparación medida: es lo que dicen las páginas.

### Civil

| Sistema | Su límite — documentado |
|---|---|
| **NEWS2** (estándar NHS) | *"Dependencia de parámetros fisiológicos 'normales' **sin tener en cuenta la variación individual**"*. Genera muchas falsas alarmas **y aun así no detecta a todos los pacientes que se deterioran** |
| **Epic Sepsis Model** | AUC 0,846 interno → **0,761 externo**. Se le escapó el **67 %** de las sepsis mientras alertaba sobre el **18 %** de todos los ingresados; 1,4 falsas alertas por cada verdadera. En urgencias: sensibilidad 14,7 %, VPP 7,6 %. **Las enfermeras taparon la cámara** para frenar las interrupciones |
| **Wearables PPG** | Error absoluto **~30 % mayor durante actividad**. Entre dispositivos, de 4,6 lpm (Apple Watch 4) a 13,8 lpm (Mi Band 3). Evidencia mixta sobre tono de piel; algunos estudios reportan hasta un 15 % más de lecturas inexactas en piel oscura |

### Militar

**RT-PSM / WPSM** (USARIEM, US Army). Su propia conclusión tras décadas de
programa:

> *"El limitante de la monitorización fisiológica en tiempo real **no ha sido la
> tecnología de ingeniería**, sino convertir datos fisiológicos en **información
> accionable**... los datos crudos son interesantes pero difíciles de
> interpretar, incluso para un sanitario."*

El segundo obstáculo que identifican: transmitir los datos hasta donde se
interpretan — que en una misión de larga duración es, directamente, imposible.

### Análogos de aislamiento

Medicina submarina y estaciones antárticas (Concordia, McMurdo) son los diseños de
referencia de los planificadores de Artemis. La lección operativa, textual: **la
autonomía médica es una restricción de diseño, no una contingencia**.

---

## 2. Lo que esto valida de EMMA

**El control de fatiga de alarma no es paranoia: es el modo de fallo dominante.**
Los cuatro controles de [`clinical-decision-rationale.md`](clinical-decision-rationale.md)
atacan exactamente lo que hundió al Epic Sepsis Model. Que un profesional tape la
cámara para dejar de recibir alertas es el final de cualquier sistema de
vigilancia — y EMMA mide su propia tasa en
[`external-validation.md`](external-validation.md) en vez de suponerla.

**La línea base personal frente a la norma poblacional.** La limitación
documentada de NEWS2 es literalmente la variación individual.

**La interpretación es el cuello de botella, no el sensor.** El Army lo concluyó
tras décadas; Astroskin ya resuelve la adquisición en órbita. Lo que falta es
`advisor/` + `evidence/`, que es donde EMMA pone su peso.

**La evidencia enlazada no es buena UX: es el criterio regulatorio.** La exención
de soporte a la decisión clínica del 21st Century Cures Act (§520(o)(1)(E) FDCA)
excluye un software de la definición de dispositivo médico si permite *"revisar
independientemente la base de la recomendación"*. Es lo que hace `evidence_for()`.

---

## 3. Posicionamiento frente a CMO-DA

> **CMO-DA diagnostica; EMMA vigila.** Uno responde cuando ya hay un síntoma; el
> otro detecta el cambio antes de que lo haya. Son complementarios: la salida de
> EMMA es precisamente el contexto longitudinal que un asistente diagnóstico
> necesita y hoy no tiene.

Un matiz técnico: CMO-DA corre en la nube. Es válido para la ISS en órbita baja e
incompatible con el escenario de Marte, donde el enlace es el recurso escaso.

---

## 4. Apoyarse en una IA médica para diagnosticar: la decisión

La pregunta obvia al ver CMO-DA. **La versión ingenua rompe tres cosas a la vez:**

1. **Sube la clasificación a IEC 62304 Clase C.** EMMA es Clase B porque informa
   y recomienda, no diagnostica. Un diagnóstico erróneo que retrase el tratamiento
   correcto puede causar daño grave. Toda la clasificación descansa en esa frontera.
2. **Rompe la exención CDS.** §520(o)(1)(E) exige poder revisar independientemente
   la base de la recomendación. El razonamiento de un LLM se puede leer, no
   verificar. Un diagnóstico sin base revisable cae **dentro** de la definición de
   dispositivo médico.
3. **No hay quien corrija el error.** En Tierra una sugerencia equivocada la caza
   un clínico; a 22 min de tiempo de luz no hay nadie. La premisa del proyecto es
   justo lo que vuelve peligrosa una salida no verificable.

**La versión que sí encaja — explicación y recuperación, no diagnóstico:**

| Propiedad | Cómo se preserva |
|---|---|
| Base revisable | RAG estricto sobre corpus de a bordo (procedimientos ExMC, AMCL, briefs OCHMO). **Cada frase cita su documento.** Sin recuperación, sin respuesta |
| Offline-first | Modelo local pequeño, a bordo |
| Clase B | El modelo **nunca** altera una puntuación de riesgo ni dispara una alerta. El motor determinista sigue siendo la autoridad |

Lo que solo un modelo puede aportar: estructurar el relato del astronauta
—síntomas descritos, diario, voz— que el motor determinista no puede tocar.

**Lo implementado (2026-09-24), y en qué se aparta de esto.** El primer uso de un modelo en EMMA
es el borrador de interpretación de las ecografías (`app/interpret/`). No es RAG sobre un corpus:
redacta a partir de **hechos del propio registro** —medidas, historial y método— y la base revisable
son esas mismas medidas, que la interfaz muestra junto al borrador. El modelo es local y no altera
ninguna puntuación ni alerta. Aun así, su elemento se clasifica **Clase C** y el resto sigue B por
segregación: el razonamiento está en `software-safety-classification.md` §2.1 y el peligro, en H14
de `risk-management-file.md`.

**Fuera de alcance por ahora.** Añadir un componente no validable a un proyecto
cuyo compromiso metodológico es la honestidad sobre la validación sería
contradictorio. Primero cerrar la tasa de falsa alarma.

---

## 5. Tensión regulatoria sin resolver

La exención CDS asume que quien revisa la base es un *health care professional*.
En una misión a Marte el usuario puede no serlo: hay un Crew Medical Officer, pero
no siempre es médico. **No se resuelve aquí, se nombra.** Es una pregunta abierta
legítima del dominio, no un descuido del proyecto.

---

## Fuentes

- [NASA ExMC — Medical System Concept of Operations for Mars](https://ntrs.nasa.gov/citations/20170000500)
- [NASA HRP — TRISH y HERMES](https://www.nasa.gov/hrp/the-translational-research-institute-for-space-health-trish/) (ficha `nasa-trish`), leída el 2026-10-26
- [Baylor College of Medicine — Hermes](https://www.bcm.edu/academic-centers/space-medicine/translational-research-institute/research/hermes), leída el 2026-10-26; sin fecha a la vista
- [Baylor College of Medicine — TRISH selects healthcare and data management projects for spaceflights](https://www.bcm.edu/news/trish-selects-healthcare-and-data-management-projects-for-spaceflights) (1 de noviembre de 2023), leída el 2026-10-26
- [Valor de un CDSS para operaciones médicas independientes de la Tierra](https://www.nature.com/articles/s41526-023-00284-1)
- [Astroskin / Bio-Monitor](https://hexoskin.com/pages/astroskin-vital-signs-monitoring-platform-for-advanced-research)
- [Validación externa del Epic Sepsis Model (JAMA Intern Med)](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2781307)
- [NEWS2: validación a gran escala en planta](https://pmc.ncbi.nlm.nih.gov/articles/PMC12550795/)
- [Fuentes de inexactitud en sensores ópticos de pulso (npj Digital Medicine)](https://www.nature.com/articles/s41746-020-0226-6)
- [Real Time Physiological Status Monitoring (RT-PSM), DTIC](https://apps.dtic.mil/sti/pdfs/ADA630142.pdf)
- [Medicina submarina como análogo del vuelo espacial (npj Microgravity)](https://www.nature.com/articles/s41526-026-00566-4)
- [FDA — IA en Software as a Medical Device](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-software-medical-device)
- [MMASH (PhysioNet)](https://physionet.org/content/mmash/1.0.0/)
