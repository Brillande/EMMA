SPACE HEALTH AUTONOMY
Project Knowledge Base · investigación, hipótesis y mapa de decisión
Space Apps Challenge 2026 · Versión 1 · 23 septiembre 2026
| Documento vivo. Separa hechos respaldados por fuentes, hipótesis de diseño y cuestiones abiertas. No debe interpretarse como consejo médico ni como especificación clínica validada. |
# 1. Propósito y tesis de trabajo
El reto se interpreta como un problema de autonomía sanitaria en exploración humana: recoger indicadores de salud, comprenderlos en contexto y ayudar a la tripulación a decidir y actuar cuando la asistencia terrestre sea limitada. La propuesta no se cierra todavía en un producto: esta versión documenta el espacio del problema y las hipótesis que deben validarse.
- Principio rector: no construir otro dashboard genérico; buscar una capa de inteligencia longitudinal, contextual y explicable.
- Unidad de análisis: astronauta + hábitat + misión + contramedidas, no el cuerpo aislado.
- Arquitectura operativa deseable: local-first, offline-first, resiliente, auditable y human-in-the-loop.
- Diferenciar siempre medición directa, inferencia y predicción; mostrar incertidumbre y procedencia de la evidencia.
- El MVP debe ser estrecho y demostrable con datos NASA reales o simulación trazable, aunque la visión sea amplia.
# 2. Marco NASA: de los riesgos a la autonomía
## 2.1 RIDGE como ontología superior
NASA agrupa los grandes peligros del vuelo espacial humano en radiación, aislamiento y confinamiento, distancia de la Tierra, campos gravitatorios y entornos hostiles/cerrados. Esta taxonomía sirve como índice superior para organizar variables, datasets, experimentos, sensores, contramedidas y escenarios.
| Riesgo | Variables / efectos | Implicación software |
| Radiation | dosis, tipo de partícula, tasa, blindaje, posición, exposición acumulada | fusionar hazard + dosimetría + historial personal; distinguir riesgo agudo, de misión y de carrera |
| Isolation | sueño, luz, fatiga, cognición, estado conductual, dinámica de equipo | detectar tendencias y degradación de rendimiento sin medicalizar señales aisladas |
| Distance | latencia, pérdida de comunicaciones, evacuación, soporte clínico | CDSS local y procedimientos utilizables sin Mission Control |
| Gravity | hueso, músculo, fluid shift, cardiovascular, sensorimotor, visión | baseline personal + tendencia + contramedidas + recuperación |
| Environment | CO2/O2, temperatura, humedad, contaminantes, microbiología, ruido/luz | correlacionar estado del hábitat con cambios humanos y eventos compartidos |
Fuente: NASA – The Human Body in Space — https://www.nasa.gov/humans-in-space/the-human-body-in-space/
## 2.2 Medical Data Architecture y Clinical Decision Support
La línea MDA/ExMC es central porque documenta que el problema no es sólo capturar datos. En 2020 NASA describía los gaps Med 07 (procesamiento integral de información médicamente relevante) y Med 10 (soporte computacional a la decisión médica). La evolución prevista era pasar de una arquitectura de datos a clinical decision support y guía en tiempo real para una atención cada vez más autónoma.
Un antecedente de 2016 ya describía datos de salud en vuelo heterogéneos, potencialmente aislados y no examinados como un conjunto, y proponía una arquitectura capaz de reunirlos y generar consejo específico para el caso. En 2022, NASA publicó una recomendación de arquitectura CDSS sobre la MDA, insistiendo en que la tripulación de exploración tendrá que detectar, diagnosticar, tratar y prevenir eventos con restricciones de masa, volumen, potencia, tiempo de tripulación y evacuación.
Fuente: NASA NTRS – MDA 2020 — https://ntrs.nasa.gov/citations/20200000567
Fuente: NASA NTRS – ECDS/MDA 2016 — https://ntrs.nasa.gov/citations/20160012678
Fuente: NASA NTRS – ExMC CDSS Architecture Recommendation — https://ntrs.nasa.gov/citations/20220017869
## 2.3 Integrated Medical Model: qué hace y qué no debemos duplicar
A septiembre de 2026 NASA describe el Integrated Medical Model (IMM) como una herramienta pre-misión de apoyo a decisión que usa evidencia médica e iMED, ejecuta simulaciones Monte Carlo y estima eventos médicos, capacidad funcional, tiempo perdido, evacuación/pérdida de vida y utilización de recursos. Evalúa más de 100 condiciones y ayuda a dimensionar MedCap. Esto obliga a diferenciar nuestro posible producto: IMM es principalmente planificación probabilística de riesgo y recursos; nuestra hipótesis se centra en monitorización longitudinal dinámica, contexto multimodal, desviación del baseline individual y apoyo operacional en vuelo.
La propia documentación NASA advierte limitaciones/hipótesis: baseline ISS, diagnóstico correcto y tratamiento efectivo en el modelo, y sensibilidad de resultados a las especificaciones de misión. Las validaciones históricas mostraron diferencias entre predicción y eventos observados, por lo que cualquier capa predictiva nueva debe explicitar credibilidad e incertidumbre.
Fuente: NASA – Integrated Medical Model (16 Sep 2026) — https://www.nasa.gov/general/nasas-integrated-medical-model-imm/
Fuente: NASA-STD-3001 Appendix E — https://www.nasa.gov/reference/appendix-e-health-and-medical-care-technical-requirements/
# 3. Escalera de evidencia y validación: Tierra → ISS → Luna → Marte
NASA utiliza una estrategia escalonada: análogos terrestres para controlar variables y ensayar condiciones; ISS para exposición humana real de larga duración en LEO; Artemis/Luna para operaciones fuera de LEO y mayor autonomía; Marte como combinación extrema de duración, distancia, radiación, microgravedad de tránsito, gravedad parcial y logística limitada.
| Entorno | Fortaleza | Limitación | Uso en el proyecto |
| Análogos terrestres | control experimental, más sujetos, instrumentación, menor coste | no reproducen todo el entorno espacial | descubrir relaciones, contramedidas, modelos e inferencias |
| ISS | microgravedad real, humanos, operaciones prolongadas | LEO, soporte Tierra, resupply/evacuación relativa | validar señales y comportamiento operacional real |
| Artemis/Luna | fuera de LEO, radiación/operaciones profundas, gravedad parcial | misiones más cortas y Tierra relativamente próxima | validar autonomía y transición a exploración |
| Marte | caso objetivo integrado | no existe banco de prueba completo | requisitos finales: autonomía, resiliencia, recursos y latencia |
## 3.1 Misiones análogas: considerar variables, no sólo escenarios
Comentario de proyecto asociado: “Misiones análogas, considerar variables”. Se adopta como regla metodológica. Cada dato debe conservar el contexto experimental y las variables manipuladas o ausentes; no se deben mezclar observaciones de bed rest, HERA, Antártida, NSRL e ISS como si fueran equivalentes.
| Análogo | Variables principales | Qué aporta |
| :envihab / bed rest | -6° head-down tilt, duración, fluid shift, descarga musculoesquelética, CO2, centrifugación | fisiología controlada y prueba de contramedidas |
| HERA | aislamiento, confinamiento, comunicación, autonomía, uso de equipos, capacidades médicas | validación operacional del CDSS y factores humanos |
| Antártida | aislamiento prolongado, ambiente extremo, cognición, relaciones y equipos | comportamiento, sueño, equipo y resiliencia |
| NSRL | partícula, energía, LET, dosis, tasa, secuencia, material/blindaje | mecanismos y modelos de radiación profunda |
| CHAPEA/MMEA y otros | misión integrada, recursos, operaciones, hábitat | interacciones multivariables y misión simulada |
Fuente: NASA – Step 1 Earth Analogs — https://www.nasa.gov/humans-in-space/step-1-earth-analogs-help-advance-missions-to-moon-mars/
## 3.2 Bed rest como dataset longitudinal
NASA explica que el head-down tilt a -6° descarga músculos y huesos y desplaza fluidos hacia la parte superior del cuerpo. AGBRESA comparó 60 días de bed rest con grupos de centrifugación continua, intermitente y control. La importancia para el proyecto es el patrón PRE → EXPOSURE → COUNTERMEASURE → POST → RECOVERY y la posibilidad de relacionar señales fáciles de medir con pruebas clínicas complejas.
Hipótesis de “variables inferibles”: entrenar/validar relaciones entre wearables, actividad, sueño, nutrición o ecografía y estados que normalmente exigen MRI, DEXA u otros recursos de alto coste operacional. Debe tratarse como hipótesis de investigación, no como capacidad demostrada.
Fuente: NASA – One Small Step Without Ever Leaving Bed — https://www.nasa.gov/humans-in-space/one-small-step-without-ever-leaving-bed/
# 4. Variables humanas: del sensor al estado de salud
La variable útil no es sólo el valor medido, sino su relación con baseline, tendencia, contexto, calidad del dato, fase de misión y posibilidad de actuar. El sistema debe distinguir tres clases: variables operacionales medibles en vuelo; variables de conocimiento usadas para entrenar/validar; variables inferibles estimadas a partir de señales disponibles.
| Sistema | Variables candidatas | Medición / evidencia | Contramedidas relacionadas |
| Cardiovascular | HR, HRV, presión, ortostatismo, fitness | wearables, pruebas funcionales, estudios de gravedad | ejercicio, hidratación, adaptación |
| Musculoesquelético | fuerza, masa, densidad, carga, ejercicio | actividad, ejercicio, imagen pre/post, análogos | resistivo/aeróbico, nutrición, gravedad artificial |
| Sueño/cognición | duración, eficiencia, luz, PVT, fatiga | actigrafía, tests cognitivos | luz, descanso, horario, workload |
| Renal/hidratación | ingesta, orina, solutos, riesgo de cálculos | orina, hidratación, dieta | agua, dieta, ejercicio; intervención clínica según protocolo |
| Inmune/biología | citocinas, células, omics, microbioma | sangre/saliva/OSDR/Biolab | conocimiento mecanístico y seguimiento |
| Visión/fluidos | síntomas, cambios oculares, fluid shift | imagen, ecografía, evaluaciones específicas | contramedidas de fluid shift en investigación |
| Conductual/equipo | estado, carga, cohesión, estrés | autoinformes, tareas, análogos | organización, sueño, comunicación, soporte |
# 5. Nutrición y alimentación como sensor, riesgo y contramedida
El Evidence Report AFT organiza el sistema alimentario alrededor de seguridad, nutrición, aceptabilidad y utilización de recursos. Para exploración, la comida no es sólo aporte calórico: su estabilidad, selección real, almacenamiento, seguridad y aceptación condicionan salud y rendimiento. El documento también trata la alimentación como factor modificable y, por tanto, potencial contramedida cotidiana.
- Registrar inventario, vida útil, composición nutricional, ingesta real, preferencias, rechazo, apetito y timing.
- Conectar dieta con ejercicio, hidratación, metabolismo, microbioma y estado inmune cuando exista evidencia suficiente.
- Modelar recursos: masa, volumen, residuos, preparación, tiempo de tripulación y energía.
- Explorar interacción radiación → estabilidad del alimento → nutrición → astronauta.
- Usar Food-01..Food-04 como mapa histórico de gaps, verificando estado actual antes de afirmar que siguen abiertos.
Fuente: NASA HRR – AFT Evidence Report — https://humanresearchroadmap.nasa.gov/Evidence/reports/AFT.pdf
# 6. Habitat Twin: la nave como parte del sistema sanitario
El ATCS de ISS muestra una arquitectura de sensado, redundancia, aislamiento de fallos y recuperación. El sistema interno usa circuitos de agua para recoger calor; el externo usa amoníaco y radiadores para rechazarlo al espacio. El EATCS permanente dispone de dos circuitos y una capacidad de rechazo de hasta 70 kW. La lección no es copiar el control térmico, sino reconocer que el estado del vehículo modifica el estado humano.
Concepto de Human FDIR inspirado en ingeniería: Health anomaly Detection → probable-cause Isolation → Countermeasure → Recovery monitoring. Debe ser una metáfora de arquitectura, no una equivalencia clínica automática.
| Telemetría de hábitat | Relevancia sanitaria contextual |
| CO2 / O2 / presión | ventilación, respiración, cognición, seguridad |
| Temperatura / humedad | termorregulación, sueño, rendimiento, confort |
| Radiación / posición / shielding | exposición aguda y acumulada |
| Contaminantes / microbiología | irritación, infección, respuesta inmune |
| Ruido / iluminación | sueño, fatiga, ritmo circadiano |
| Estado de life support / thermal control | causa común potencial de cambios en varios tripulantes |
Fuente: NASA – ISS ATCS Overview — https://www.nasa.gov/wp-content/uploads/2021/02/473486main_iss_atcs_overview.pdf
# 7. Radiación: hazard → exposición → biología → acción
El proyecto debe distinguir radiación atrapada, partículas energéticas solares (SEP/SPE), rayos cósmicos galácticos (GCR) y radiación secundaria producida por interacciones con blindaje/vehículo/tejido. Para interpretación biológica importan partícula, energía, LET, dosis, tasa, secuencia temporal, tejido y shielding; una única cifra de dosis no captura todo el riesgo.
- HERA/Orion y dosimetría: detección de hazard y alertas operacionales.
- NSRL: evidencia controlada sobre partículas/energías, biología, materiales y electrónica.
- Modelo longitudinal: exposición aguda + acumulada de misión + historial de carrera.
- Contramedidas: blindaje, uso de masa existente (agua/alimentos/suministros), refugio temporal, procedimiento operacional y seguimiento médico/biológico.
- No reinventar física de radiación si pueden integrarse modelos/telemetría NASA; concentrarse en traducción a estado personal y decisión.
Fuente: NASA – Orion Radiation Protection — https://www.nasa.gov/missions/artemis/orion/scientists-and-engineers-evaluate-orion-radiation-protection-plan/
Fuente: BNL – NSRL — https://www.bnl.gov/nsrl/about.php
# 8. Datos y repositorios: construir un mapa, no un único dataset
La estrategia de datos debe separar INPUT (señales de misión), KNOWLEDGE (evidencia histórica/mecanística) y CONTEXT (entorno/misión), además de protocolos/contramedidas. OSDR es especialmente útil para biología/omics; NLSP y publicaciones HRP son más relevantes para investigación humana operacional; LSAH representa vigilancia longitudinal, con restricciones de privacidad y acceso que deben respetarse.
| Fuente | Tipo | Uso previsto |
| OSDR / OSD-288 | murino, RNA-seq, ambiente/radiación | mecanismos inmunes; no usar como equivalente clínico humano |
| OSD-343 | integración multi-ómica/humana según estudio | relaciones longitudinales y comparación de modalidades |
| Twins Study | humano longitudinal N=1 + gemelo control | parámetros pre/in/post y recuperación; evitar generalización |
| Inspiration4 / OSDR | muestras humanas pre/durante/post | complemento humano multimodal |
| ISS Research Explorer | experimentos, equipos, PI, instalaciones | reconstruir qué se mide, cómo y con qué coste operacional |
| data.nasa.gov | catálogo de metadatos | descubrimiento sistemático |
| Astroquery/JPL context | posición/efemérides | sólo si el contexto astronómico mejora una decisión sanitaria |
# 9. Instalaciones y equipamiento: coste de medir
Cada variable debe acompañarse de su “coste de medición”: crew time, invasividad, hardware, masa, volumen, potencia, consumibles, calibración, entrenamiento, procesamiento, dependencia de Tierra y latencia hasta resultado. Esto permite priorizar sensores pasivos/continuos y usar pruebas invasivas o complejas como confirmación.
Columbus/EPM y Biolab deben analizarse como cadenas facility → experiment → equipment → parameter → investigator → provider → dataset → publication → application. Biolab es principalmente mecanístico (células, tejidos, pequeños organismos) y su automatización/teleoperación aporta una lección de reducción de crew time; EPM es más cercano a fisiología humana.
Fuente: ESA – Biolab — https://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Columbus/Biolab
# 10. Arquitectura conceptual consolidada
| Twin / capa | Contenido | Pregunta |
| Human Twin | fisiología, biología, cognición, nutrición, historial, baseline | ¿qué está cambiando en esta persona? |
| Habitat Twin | atmósfera, térmico, radiación, microbiología, life support | ¿hay una causa ambiental o sistémica? |
| Mission Twin | fase, posición, duración, gravedad, EVA, workload, comunicaciones, recursos | ¿qué contexto operacional explica/modifica el riesgo? |
| Countermeasure Twin | ejercicio, dieta, descanso, protección, procedimientos, recursos y respuesta previa | ¿qué puede hacerse ahora y qué efecto esperamos? |
| Decision layer | fusión, anomalía, explicación, evidencia, recomendación y seguimiento | ¿qué necesita saber/hacer la tripulación, con qué confianza? |
Flujo objetivo: SENSE → CONTEXTUALIZE → DETECT → EXPLAIN → RELATE TO RISK → RECOMMEND CHECK/COUNTERMEASURE → HUMAN DECISION → FOLLOW-UP. La capa de IA no debe presentarse como “doctor autónomo”; debe mantener trazabilidad de evidencia, límites y control humano.
# 11. Visualización y referencias técnicas (subapartado del proyecto)
Este subapartado agrupa referencias de implementación, UX, renderizado y hardware. No sustituye a la investigación biomédica; sirve para traducirla a un prototipo comprensible y robusto.
## 11.1 Polaris: referencia de sistema agéntico y render clínico
El repositorio BeyondTheProtocol/polaris no es un monitor espacial. Es un sistema agéntico orientado a un caso clínico complejo. Su README articula Goal → “Caja” de expertos → salida con gate humano, declara que no da consejo médico ni diseña tratamientos y utiliza evidencia médica antes que LLMs. Para nuestro proyecto son valiosos el goal explícito, la verificación adversarial, fail-closed, egress con aprobación humana y separación entre dato e instrucción.
Comentario asociado del proyecto: “Esto es como renderizar el hígado que te pasé”. Polaris incluye como ejemplo una petición de render 3D de lesiones a partir de PET para mejorar la comprensión por el equipo médico. La lección aplicable es convertir el Digital Twin en una interfaz anatómica navegable: BODY → ORGAN → HEALTH STATE → DATA → EVIDENCE → TREND → RISK → COUNTERMEASURE. Debe distinguir medición directa de estimación y mostrar incertidumbre.
Polaris usa AGPL-3.0; reutilizar código en un producto cerrado tendría implicaciones de licencia. Las ideas/arquitectura pueden inspirar una implementación propia; cualquier reutilización literal debe revisarse jurídicamente.
Fuente: GitHub – BeyondTheProtocol/polaris — https://github.com/BeyondTheProtocol/polaris
## 11.2 ZeroKeyUSB: referencia de hardware y filosofía local-first
Se conserva como referencia de diseño: minimizar dependencias, funcionamiento local/offline, control del usuario, simplicidad, “good friction” y reducción de puntos de fallo. Si se construye hardware para la demo, debe ser host/interfaz del software, no desviar el MVP hacia ingeniería electrónica.
## 11.3 Referencias X / enlaces no recuperables
Los dos posts de X aportados quedan registrados como referencias pendientes de contenido verificable. En la investigación previa el acceso público automatizado no permitió recuperar su contenido; no se infiere ni atribuye ninguna idea concreta hasta disponer de captura, texto o vídeo.
# 12. Storytelling y transferencia a Tierra
La carta de Ernst Stuhlinger se usa como marco narrativo: la exploración extrema puede producir soluciones transferibles. El proyecto puede contar una segunda misión —arquitecturas de salud autónoma/offline aplicables a lugares remotos o con recursos limitados en Tierra— sin afirmar equivalencia clínica entre medicina espacial y terrestre.
Narrativa de trabajo: “Cuanto más lejos viaja el ser humano de la Tierra, más debe viajar la atención sanitaria con él.” El valor terrestre debe presentarse como transferencia de arquitectura técnica: autonomía, resiliencia, integración de datos, soporte a decisión y operación con conectividad limitada.
# 13. Hipótesis prioritarias que deben probarse
- H1. Existe todavía un hueco entre datos médicos/ambientales heterogéneos y una capa personalizada, longitudinal y explicable de decisión a bordo.
- H2. El baseline individual y la tendencia son más útiles para determinadas señales que comparar únicamente con rangos poblacionales.
- H3. Algunas variables clínicas costosas pueden inferirse parcialmente mediante señales operacionales de bajo coste; debe demostrarse por dominio.
- H4. Correlacionar cambios simultáneos de varios tripulantes con telemetría de hábitat puede mejorar el aislamiento de causa.
- H5. Un Countermeasure Twin que conozca recursos, protocolos y respuesta previa añade más valor que una alerta aislada.
- H6. La radiación ofrece un buen caso end-to-end para demo porque conecta hazard, dosimetría, exposición acumulada, contexto, acción y seguimiento.
- H7. La alimentación puede ser un segundo caso porque es una contramedida cotidiana con interacción con recursos, microbioma, metabolismo y aceptabilidad.
# 14. MVP candidato, todavía provisional
Un MVP razonable para hackathon podría integrar 2–3 streams (p. ej. fisiología wearable simulada/realista + ambiente/hábitat + contexto de misión), mantener baseline individual, detectar una tendencia, explicar qué variables contribuyen, enlazarla con un riesgo/contramedida documentados y mostrar seguimiento. La visualización anatómica 3D puede ser una capa de UX si no compromete el núcleo funcional.
Caso demostrativo posible: evento de radiación/entorno + exposición personal + estado fisiológico + procedimiento/refugio + monitorización posterior. Alternativa: degradación sueño/fatiga/CO2 o riesgo renal/hidratación/nutrición. La selección debe depender de disponibilidad de datos y capacidad de validar la lógica.
# 15. Backlog de investigación
| Prioridad | Tarea | Resultado esperado |
| P0 | Mapear estado 2026 de MDA/CDSS/IMM/MEDPRAT | evitar duplicación y definir gap real |
| P0 | Twins Study + OSD-343 + datasets humanos | tabla de variables, timepoints, acceso y utilidad |
| P0 | ISS Research Explorer / EPM / equipos de salud | inventario de mediciones, hardware y ground dependence |
| P1 | NLSP y LSAH | qué datos humanos longitudinales son públicos/restringidos |
| P1 | ISS vs Artemis vs Mars | matriz formal de requisitos y autonomía |
| P1 | Contramedidas por RIDGE | biblioteca evidence-linked de acciones y recursos |
| P1 | Ground analogs | datasets y diseños experimentales reutilizables |
| P2 | Proveedores/investigadores | ecosistema NASA/ESA/TRISH/BNL/universidades/vendors |
| P2 | Visualización 3D | pipeline anatómico, formatos, rendimiento y licencias |
# 16. Fuentes y enlaces del proyecto
- NASA Space Apps Challenge 2026 – Create Health Monitoring Software for Astronauts on Space Missionshttps://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/
- NASA – Step 1, Earth: Analogs Help Advance Missions to Moon, Marshttps://www.nasa.gov/humans-in-space/step-1-earth-analogs-help-advance-missions-to-moon-mars/
- NASA NTRS – Medical Data Architecture Prototype Development (2020)https://ntrs.nasa.gov/citations/20200000567
- NASA Human Research Roadmap – Evidence Report: Inadequate Food System (2016)https://humanresearchroadmap.nasa.gov/Evidence/reports/AFT.pdf
- NASA – One Small Step… Without Ever Leaving Bedhttps://www.nasa.gov/humans-in-space/one-small-step-without-ever-leaving-bed/
- NASA – ISS Active Thermal Control System Overviewhttps://www.nasa.gov/wp-content/uploads/2021/02/473486main_iss_atcs_overview.pdf
- NASA – Body in Space / Human Body in Space infographic reporthttps://www.nasa.gov/wp-content/uploads/2021/02/bodyinspace_revised_forweb-2022-updated.pdf
- NASA – The Human Body in Spacehttps://www.nasa.gov/humans-in-space/the-human-body-in-space/
- NASA – Living in Spacehttps://www.nasa.gov/humans-in-space/living-in-space/
- NASA HRP – Research Operations & Integrationhttps://www.nasa.gov/hrp/research-operations-integration/
- NASA – Artemis Moon Missions as an Astronaut Testbed for Marshttps://www.nasa.gov/humans-in-space/step-3-artemis-moon-missions-as-an-astronaut-testbed-for-mars/
- NASA – ISS Astronaut Record Holdershttps://www.nasa.gov/international-space-station/space-station-astronaut-record-holders/
- NASA – Twins Studyhttps://www.nasa.gov/humans-in-space/twins-study/
- NASA OSDR – Open Science Data Repositoryhttps://science.nasa.gov/biological-physical/data/osdr/
- NASA OSDR – OSD-288https://osdr.nasa.gov/bio/repo/data/studies/OSD-288
- NASA OSDR – OSD-343https://osdr.nasa.gov/bio/repo/data/studies/OSD-343
- NASA – ISS Research Explorerhttps://www.nasa.gov/mission/station/research-explorer/
- ESA – Biolabhttps://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Columbus/Biolab
- ESA – Columbus laboratory (educational overview)https://www.esa.int/kids/es/Aprende/Vida_en_el_Espacio/Estaciones_espaciales/%21El_laboratorio_Columbus_cumple_10_anos
- EstacionEspacial.com – Columbus Orbital Facility historical pagehttps://www.estacionespacial.com/cof.php
- NASA – Orion Radiation Protection Planhttps://www.nasa.gov/missions/artemis/orion/scientists-and-engineers-evaluate-orion-radiation-protection-plan/
- Brookhaven National Laboratory – NASA Space Radiation Laboratoryhttps://www.bnl.gov/nsrl/about.php
- Astroquery documentationhttps://astroquery.readthedocs.io/en/latest/
- NASA Open Data Portalhttps://data.nasa.gov/
- NASA – Integrated Medical Model (current overview)https://www.nasa.gov/general/nasas-integrated-medical-model-imm/
- NASA – Integrated Medical Model overview/resourceshttps://www.nasa.gov/nasa-integrated-medical-model-imm-overview/
- NASA NTRS – Exploration Medical Capability CDSS Architecture Recommendationhttps://ntrs.nasa.gov/citations/20220017869
- NASA NTRS – Exploration Clinical Decision Support System: Medical Data Architecturehttps://ntrs.nasa.gov/citations/20160012678
- NASA NTRS – Clinical Decision Support – Concepts of Operationhttps://ntrs.nasa.gov/citations/20205008731
- NASA-STD-3001 Appendix E – Health and Medical Care Technical Requirementshttps://www.nasa.gov/reference/appendix-e-health-and-medical-care-technical-requirements/
- GitHub – BeyondTheProtocol/polarishttps://github.com/BeyondTheProtocol/polaris
- Naukas – traducción de la carta de Ernst Stuhlingerhttps://naukas.com/2012/08/08/por-que-explorar-el-espacio-carta-traducida-de-la-original-de-ernst-stuhlinger/
- ISS overview video supplied by projecthttps://youtu.be/5GeAORj0Nw0?is=-TF-NzF3yjSXfl_j
- ZeroKeyUSB Supermo share supplied by projecthttps://app.supermo.no/share/0c9f73b53405e57f/e564eed220
- X post supplied by project – Miriamhttps://x.com/miriamgonp/status/2101729927590453255
- X post supplied by project – Israelhttps://x.com/israeldfirzt/status/2100980215782473955