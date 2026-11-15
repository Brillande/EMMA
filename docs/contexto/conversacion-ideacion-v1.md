https://www.spaceappschallenge.org/2026/challenges/
Perfecto. Tomo esta página de NASA Space Apps Challenge 2026 – Challenges como punto de partida para el proyecto.
Puedo ayudarte a trabajar los retos con un enfoque bastante práctico: analizar cada challenge, detectar qué problema intenta resolver realmente, valorar qué datos de NASA ofrece, proponer ideas de solución y convertir la mejor en un proyecto presentable al Space Apps Challenge.
Ahora mismo la web oficial me está devolviendo un error al intentar acceder a esa página directamente. Si quieres, en el siguiente paso puedo buscar los challenges 2026 publicados, recopilarlos y preparar una primera matriz con: reto, temática, dificultad, datos disponibles, posibilidades de IA, componente social/ambiental/científico, originalidad potencial y posibles ideas de proyecto.
https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/
Sí. Este reto me parece especialmente interesante para trabajar dentro del proyecto Space Apps Challenge 2026.
He conseguido recuperar el contenido aunque la página oficial está dando problemas de acceso directo. El reto se titula “Create Health Monitoring Software for Astronauts on Space Missions”, está clasificado como Intermediate y pertenece a Human Exploration / Software / Space Exploration. 
El problema que plantea NASA es bastante concreto: en misiones de larga duración, los astronautas están sometidos a radiación espacial, aislamiento y confinamiento, gravedad alterada y un entorno cerrado hostil. Entre las consecuencias que señala el reto aparecen cambios inmunológicos, pérdida ósea, problemas cardiovasculares y problemas de salud conductual. Además, cuanto más lejos se encuentre la tripulación, mayor será su responsabilidad para detectar por sí misma esos cambios. 
Por tanto, NASA no está pidiendo simplemente un dashboard médico. La formulación importante es:
construir software que recopile indicadores de salud y permita a los astronautas evaluar y actuar sobre su estado de salud. 
Y ahí creo que está la parte interesante.
Una dirección que estudiaría
En vez de hacer únicamente un “monitor de constantes vitales para astronautas”, plantearía algo parecido a un sistema autónomo de apoyo a decisiones médicas para misiones de espacio profundo.
Conceptualmente:
sensores/datos → evolución individual → detección de anomalías → interpretación → riesgo → recomendación → actuación → seguimiento.
Es decir, crear una especie de “copiloto sanitario de la tripulación”.
El sistema podría construir para cada astronauta una línea basal personalizada y detectar desviaciones respecto de su propio estado normal, en lugar de limitarse a comparar constantes con valores poblacionales.
Por ejemplo, podría integrar frecuencia cardiaca y HRV, sueño, actividad física, SpO₂, temperatura, presión arterial, peso/composición corporal, rendimiento cognitivo, estado psicológico/autoevaluaciones, exposición acumulada a radiación, ejercicio, medicación y determinados parámetros ambientales de la nave.
Y presentar algo mucho más comprensible que veinte gráficas:
Crew Health Index → 87/100
con dimensiones como cardiovascular, musculoesquelética, sueño/recuperación, comportamiento/cognición, exposición a radiación, etc.
Pero la verdadera diferenciación podría aparecer cuando el sistema diga:
“Tu recuperación cardiovascular lleva 6 días deteriorándose respecto a tu baseline. Coincide con reducción del sueño y aumento de carga de ejercicio. Riesgo creciente → recomendamos reducir intensidad, realizar test X y reevaluar en 12 h.”
Eso responde mucho mejor al “evaluate and act” que pide NASA.
Y añadiría una condición de diseño muy espacial
Que funcione offline y de manera autónoma.
En una misión hacia Marte no tiene demasiado sentido diseñar un sistema sanitario que dependa constantemente de un médico o de un servidor en Tierra. El concepto podría ser:
Earth-independent astronaut health monitoring.
Además, la IA no debería aparecer como una caja negra que “diagnostica”. Para un sistema de apoyo sanitario sería mucho más defendible que cada alerta mostrase qué indicadores cambiaron, respecto de qué baseline, desde cuándo y por qué el sistema considera relevante esa combinación.
Eso nos permitiría incorporar una capa muy potente de IA explicable + human-in-the-loop.
Hay otra oportunidad importante
Podemos convertir al astronauta en su propio control longitudinal.
En microgravedad algunas variables van a cambiar necesariamente. Por eso un sistema basado exclusivamente en rangos médicos terrestres puede tener limitaciones. Una arquitectura interesante sería:
Population reference + Mission reference + Personal baseline + Current trend
y sobre eso calcular anomalías y riesgo.
Esto tiene bastante más profundidad científica que poner simplemente semáforos verde/amarillo/rojo.
Y todavía podemos darle otra vuelta
Podríamos introducir un Crew Health Digital Twin muy sencillo.
No un gemelo digital fisiológico completo —sería inabarcable para un hackathon— sino un modelo dinámico de cada astronauta que vaya aprendiendo su baseline durante la misión y permita visualizar:
Past → Current → Predicted
Por ejemplo:
Bone health: stable → declining → intervention recommended
Cardiovascular recovery: 92 → 84 → projected 76
Sleep debt: +1.8 h → +4.1 h → cognitive-risk threshold in ~3 days
Ahí pasamos de monitorización a predicción y prevención.
Además, hay una razón estratégica para no quedarnos en el dashboard: ya existen proyectos anteriores de Space Apps que han abordado monitorización de temperatura, ECG, EEG y visualización centralizada de parámetros de astronautas. Incluso participantes de 2026 están describiendo prototipos basados en dashboards de constantes y datos ambientales. 
Por eso intentaría diferenciarnos precisamente en personalización + tendencias + predicción + explicación + decisión autónoma.
Y hay algo más que me interesa bastante para este proyecto: no empezaría todavía a programar.
Primero investigaría a fondo qué datos reales ofrece NASA para este challenge, qué métricas son científicamente relevantes, qué soluciones utiliza actualmente NASA para vigilar la salud de astronautas y cuáles son las limitaciones específicas de una misión lunar/marciana. De ahí podemos encontrar el hueco real del proyecto.
Si te parece, el siguiente paso puede ser precisamente ese: desmontar el reto de NASA punto por punto, localizar todos los datasets/resources que proporciona y empezar a diseñar nuestra propuesta para Space Apps 2026 sobre evidencia real.
https://osdr.nasa.gov/bio/repo/data/studies/OSD-288
Sí. Este dataset encaja con el reto, pero con un matiz importante: OSD-288 no contiene datos clínicos de astronautas humanos. Es un experimento biológico con ratones que nos puede servir para construir la capa científica del proyecto.
Qué es OSD-288
El estudio se titula “Transcriptome analysis of murine spleen in space”. Trabaja con ratones macho C57BL/6J enviados a la ISS y analiza tejido del bazo mediante RNA-Seq. El experimento compara condiciones de vuelo espacial y gravedad alterada; los animales permanecieron aproximadamente 35 días en la ISS y el experimento registra una exposición total de unos 39 días. 
Esto es particularmente interesante porque el bazo está directamente relacionado con la función inmunitaria, uno de los riesgos que NASA estudia en vuelos espaciales. NASA identifica expresamente la alteración de la respuesta inmunitaria entre los riesgos del vuelo espacial. 
Y OSD-288 tiene algo que me parece muy valioso para nuestra idea: no contiene solamente RNA.
También incorpora metadatos de radiación y del entorno de los animales. Por ejemplo, para las muestras aparecen aproximadamente:
8,97 mGy de dosis absorbida → 0,23 mGy/día → 39 días de exposición. 
Además, el hábitat monitorizaba temperatura, humedad, CO₂ y amoníaco. 
Esto empieza a parecerse precisamente al modelo que comentábamos:
Entorno + exposición + biología → cambio fisiológico → riesgo.
Pero no utilizaría OSD-288 de forma aislada
Aquí aparece una oportunidad mucho mejor.
OSDR contiene datos ómicos, fisiológicos, fenotípicos, conductuales, biomédicos y ambientales, procedentes tanto de humanos como de animales y otros organismos. NASA señala además que estos datasets están normalizados precisamente para facilitar análisis cruzados y aplicaciones de IA/ML. 
Por tanto, podemos plantear nuestra solución como una arquitectura de varias capas:
SPACE HEALTH DIGITAL TWIN
SPACE ENVIRONMENTRadiación · CO₂ · temperatura · humedad · duración misión
↓
BIOMEDICAL DATAFrecuencia cardíaca · HRV · sueño · actividad · SpO₂ · etc.
↓
BIOLOGICAL DATARNA · inmunidad · biomarcadores · metabolismo
↓
PERSONAL BASELINEEstado normal del astronauta
↓
AI RISK ENGINEAnomalías · tendencias · correlaciones
↓
HEALTH FORECAST¿Qué está cambiando?
↓
DECISION SUPPORT¿Qué debería comprobar/hacer el astronauta?
Y aquí OSD-288 podría alimentar específicamente la dimensión:
Spaceflight → radiation/microgravity → immune response.
Hay un dataset todavía más importante para nosotros
NASA ya dispone en OSDR de datos humanos de astronautas comerciales.
La misión Inspiration4 produjo el primer conjunto amplio de datos biológicos humanos de vuelo espacial disponible públicamente en OSDR. Incluye muestras de sangre, plasma, PBMC, orina, biopsias de piel, muestras microbianas de los astronautas y de la cápsula, tomadas en distintos momentos antes, durante y después del vuelo. 
Eso nos abre una posibilidad mucho más potente:
Human data + animal data + environmental data.
Los ratones pueden proporcionar profundidad experimental que no podemos obtener éticamente de astronautas, mientras que Inspiration4 nos proporciona evidencia humana.
Además, NASA explica que OSDR permite análisis comparativos entre estudios biológicos y datos ambientales. 
Esto puede cambiar el enfoque del proyecto
En lugar de presentar al jurado:
“Hemos creado un dashboard para controlar la salud del astronauta.”
podemos aspirar a:
“Hemos creado un sistema que aprende de datos biológicos reales de vuelos espaciales de NASA para detectar cómo está respondiendo cada astronauta al entorno espacial y anticipar riesgos de salud.”
Y eso tiene bastante más profundidad.
Incluso podríamos demostrarlo durante el hackathon con un astronauta ficticio:
ASTRONAUT A — Mission Day 143
Radiation exposure↑ 18%
Sleep quality↓ 12%
HRV↓ 9%
Immune-risk signature↑
Health Digital Twin:
Immune Stress: ELEVATED
Y al pulsarlo:
Why?
Radiation exposure ↑HRV trend ↓Sleep deficit ↑Biological model → immune alteration pattern
Es decir, no solamente mostrar qué está pasando, sino por qué el sistema cree que está pasando.
Y veo una línea de trabajo bastante clara ahora. No analizaría solamente OSD-288. Haría un mapa completo de datasets OSDR aprovechables para este challenge: humanos (Inspiration4 y otros), cardiovascular, músculo, hueso, inmunidad, sueño/comportamiento, radiación, microgravedad y datos ambientales.
De cada dataset podemos identificar qué variable aporta, si puede conectarse con otra y para qué módulo de nuestro Health Digital Twin serviría.
Ese mapa probablemente nos permita descubrir cuál puede ser la verdadera ventaja diferencial de nuestra propuesta para NASA Space Apps Challenge 2026. 
https://astroquery.readthedocs.io/en/latest/
Sí, Astroquery puede ser útil para el proyecto, aunque juega un papel distinto de OSDR.
Es una colección de herramientas de Python —integrada en el ecosistema de Astropy— para consultar programáticamente numerosos archivos y servicios astronómicos. En lugar de descargar datos manualmente, permite que nuestro software haga consultas a servicios como SIMBAD, VizieR, Gaia, JPL Horizons, MAST, IRSA, HEASARC, etc.
Para este challenge yo lo situaría en la capa de contexto espacial, no en la capa médica. OSDR nos aporta evidencia biológica y biomédica; Astroquery puede ayudarnos a obtener información astronómica o de misión que contextualice el riesgo. Por ejemplo, JPL Horizons permite consultar efemérides y posiciones de cuerpos del Sistema Solar mediante astroquery.jplhorizons.
La arquitectura empieza entonces a ponerse interesante:
OSDR → qué le ocurre biológicamente al organismoWearables/biomarcadores → qué le está ocurriendo ahora al astronautaDatos ambientales → qué está ocurriendo dentro/fuera de la naveAstroquery/JPL → dónde se encuentra la misión y cuál es su contexto espacialMotor de riesgo → relaciona exposición + individuo + evolución temporalDecision Support → explica el riesgo y propone qué comprobar
Hay una idea que merece especialmente la pena explorar: que nuestro sistema no sea únicamente astronaut health monitoring, sino context-aware astronaut health monitoring.
Por ejemplo, imaginemos una misión Tierra–Marte. El sistema conoce la trayectoria/posición de la nave y el día de misión. Si incorporamos además fuentes adecuadas de space weather y radiación —aquí necesitaremos otras APIs/datasets, porque Astroquery por sí solo no resuelve esa parte— podemos construir algo conceptualmente así:
Mission position → Space environment → Estimated exposure → Personal physiology → Biological response → Individual risk
Eso permitiría que una alerta no dijera simplemente:
HRV ↓ 14 %
sino algo del estilo:
Elevated physiological stress
HRV: −14 % respecto al baseline personal 
Sleep debt: +3,2 h 
Radiation exposure: elevada durante las últimas 72 h 
Mission day: 184 
Immune-response model: desviación creciente 
Confidence: 78 %
y, sobre todo:
Why am I seeing this alert?
Esto conecta muy bien con la idea que estamos construyendo de IA explicable.
Pero evitaría meter Astroquery simplemente porque NASA lo proporciona como recurso. En un hackathon, añadir tecnologías sin una función clara puede acabar debilitando la propuesta. La pregunta debería ser:
¿Qué información obtenida mediante Astroquery mejora realmente una decisión sobre la salud del astronauta?
Si encontramos una respuesta fuerte, lo integramos. Si no, OSDR y las fuentes biomédicas/ambientales deberían tener prioridad.
Creo que ya tenemos tres piezas distintas sobre la mesa: el challenge define el problema, OSD-288/OSDR aporta evidencia biológica y Astroquery puede aportar contexto astronómico/de misión. El siguiente paso útil sería revisar todos los Resources que NASA ha enlazado específicamente dentro del challenge y clasificarlos en Health / Biology / Environment / Mission / Space Weather / Software, porque probablemente NASA nos está dando bastantes pistas sobre qué tipo de solución espera.
https://app.supermo.no/share/0c9f73b53405e57f/e564eed220
Este enlace es muy interesante para el proyecto, aunque no por el gestor de contraseñas en sí, sino por la filosofía de diseño que explica Bruno Escobar con ZeroKeyUSB.
La idea central es construir un dispositivo físico que almacena localmente credenciales cifradas y se comporta como un teclado USB: sin nube, sin instalar software, sin cuenta externa y sin batería. Su evolución además siguió una lógica de eliminar dependencias y componentes que pudieran convertirse en puntos de fallo. 
Eso conecta sorprendentemente bien con el reto de salud espacial.
La idea que trasladaría: «descolonizar» también el software médico espacial
En una misión lejana, depender de Tierra es precisamente lo que deberíamos evitar.
Podríamos convertir este principio en uno de los requisitos fundamentales de nuestro sistema:
Local-first · Offline-first · Autonomous · Explainable · Resilient
El sistema de salud debería poder seguir funcionando aunque desaparezcan temporalmente las comunicaciones con Tierra, no exista acceso a servicios cloud o un servicio externo deje de funcionar.
Esto encaja especialmente con misiones de espacio profundo: la Tierra debería ser un apoyo del sistema, no una dependencia del sistema.
Y me parece muy buena la reflexión del artículo sobre la “fricción buena”: ZeroKeyUSB deliberadamente no decide por el usuario; este desbloquea el dispositivo y decide cuándo utilizar la credencial. Podemos trasladarlo al ámbito médico:
la IA no sustituye la decisión humana; aumenta la capacidad del astronauta para tomarla.
Por ejemplo:
DETECTED
HRV ↓ 14%Sleep quality ↓ 18%Radiation exposure ↑Resting HR ↑ 7%
↓
INTERPRETED
Pattern consistent with elevated physiological stress
↓
EXPLAINED
Why am I seeing this?
↓
RECOMMENDED
Perform cardiovascular assessmentReview sleep/recovery protocolRepeat measurement in 6 h
↓
HUMAN DECISION
Accept / Dismiss / Investigate
Y esa última capa es importante. El astronauta mantiene el control.
Incluso el hardware merece consideración
El artículo cuenta que eliminar la batería mejoró simplicidad, peso y durabilidad porque la batería acababa convirtiéndose en otro punto débil. Es una excelente regla para nuestro proyecto:
Cada componente añadido tiene que justificar la dependencia que introduce.
Eso nos debería llevar a evitar un proyecto que necesite veinte APIs, siete sensores específicos, conexión permanente y un LLM gigantesco ejecutándose en la nube.
Podríamos diseñar deliberadamente un Minimum Viable Space Health System capaz de funcionar con recursos limitados.
De hecho, esto puede convertirse en una característica diferencial bastante atractiva:
Autonomous Space Health Node
Imagino un pequeño dispositivo/ordenador de a bordo que contenga localmente:
Personal Health Digital Twin
historial del astronauta 
baseline fisiológico 
modelos predictivos 
protocolos médicos 
modelos derivados de OSDR 
motor de anomalías 
IA explicable 
Los wearables y sensores alimentarían ese nodo.
No cloud required.
Cuando existe comunicación con Tierra, sincroniza datos, recibe nuevos modelos/protocolos y permite supervisión médica. Cuando no existe:
sigue funcionando.
Eso además nos proporciona una arquitectura muy limpia:
ASTRONAUT / WEARABLES
↓ Bluetooth / local sensors
SPACE HEALTH NODE
Personal baselineRisk engineDigital TwinExplainable AIMedical protocols
↕ optional synchronization
EARTH / MISSION CONTROL
Y hay una frase del artículo que me parece especialmente aplicable a lo que estamos haciendo. El autor dice que fabricar hardware le enseñó que mejorar un producto a veces consiste en eliminar funcionalidades que aportan menos de lo que requieren. 
La conservaría como principio interno de diseño del proyecto.
Porque con OSDR + IA + Astroquery + wearables + Digital Twin + radiación + space weather podemos caer fácilmente en intentar construir demasiado.
Yo empezaría a separar ya dos cosas:
VISION: un sistema autónomo integral de salud para misiones espaciales de larga duración.
SPACE APPS MVP: demostrar de manera extraordinariamente clara una parte pequeña de esa visión que realmente funcione con datos NASA.
Y creo que encontrar cuál debe ser exactamente esa pequeña parte es ahora una de las decisiones más importantes del proyecto.
https://naukas.com/2012/08/08/por-que-explorar-el-espacio-carta-traducida-de-la-original-de-ernst-stuhlinger/
Este texto sí puede aportar algo importante al proyecto, pero en una capa diferente a OSDR o Astroquery: nos da el relato de por qué merece la pena resolver este problema.
La carta de Ernst Stuhlinger, escrita en 1970 como respuesta a la hermana Mary Jucunda —que cuestionaba gastar miles de millones en llegar a Marte mientras había niños muriendo de hambre— defiende que los grandes desafíos espaciales funcionan como catalizadores tecnológicos y científicos cuyos resultados terminan regresando a la Tierra. 
Y hay una parte de la carta casi profética para el challenge que hemos elegido. Stuhlinger plantea precisamente por qué desarrollar primero sistemas de soporte vital para viajeros espaciales en vez de sensores remotos para pacientes cardíacos, y argumenta que los objetivos extremadamente difíciles obligan a encontrar soluciones que después pueden aplicarse a problemas terrestres. 
Eso conecta directamente con Create Health Monitoring Software for Astronauts on Space Missions.
El proyecto podría tener dos misiones
Hasta ahora estábamos pensando fundamentalmente:
MISSION 1 — SPACE
¿Cómo podemos mantener sano a un ser humano cuando está a millones de kilómetros de un hospital?
Pero la carta introduce naturalmente:
MISSION 2 — EARTH
¿Y si las tecnologías que necesitamos para cuidar a un astronauta lejos de la Tierra pudieran servir también para cuidar a personas lejos de un hospital en la Tierra?
Aquí creo que aparece una dimensión muy potente.
Una misión a Marte obliga a diseñar medicina para unas condiciones extremas:
Distancia → no hay hospital cercanoLatencia → el especialista no puede intervenir inmediatamenteRecursos limitados → pocos instrumentosAislamiento → autonomíaConectividad limitada → offline-firstPocos profesionales → apoyo automatizadoDatos longitudinales → prevención antes que reacción
Pero muchas de esas restricciones existen también en la Tierra:
Marte → zona rural/remota
Astronauta → paciente aislado
Mission Control → hospital de referencia
Space Health Node → Local Health Node
Telemetría → telemedicina
Autonomía médica → atención sanitaria descentralizada
Eso no significa afirmar que ambos contextos médicos sean equivalentes. No lo son. Pero determinadas soluciones técnicas desarrolladas para uno pueden tener aplicaciones en el otro.
Y conecta inesperadamente con otro concepto que has traído al proyecto
La filosofía de ZeroKeyUSB que acabamos de analizar era:
local-first + offline-first + autonomía + mínima dependencia externa.
Ahora tenemos una razón adicional para que esos principios no sean solamente requisitos técnicos espaciales.
Imagina una versión terrestre del sistema funcionando en una comunidad aislada con conectividad deficiente.
Un pequeño dispositivo recibe información de wearables y sensores médicos, mantiene localmente el historial y baseline del paciente, detecta desviaciones y ofrece protocolos básicos de decisión. Cuando recupera conexión:
sincroniza con el centro médico.
Conceptualmente sería la misma arquitectura.
SPACE → EARTH
Y esto nos permite contar una historia muy buena en la presentación.
Podríamos comenzar mirando hacia Marte:
How do you care for someone when the nearest hospital is 225 million kilometers away?
Construimos nuestra solución.
Y después, al final de la presentación, volvemos a la Tierra:
What if the technology designed for someone 225 million kilometers from a hospital could also help someone 225 kilometers from one?
Eso cierra el círculo de Stuhlinger.
No sería simplemente un recurso emocional. Tiene coherencia con el argumento histórico que él planteaba: los requisitos extremos de precisión y fiabilidad de la exploración espacial generan tecnologías y conocimientos susceptibles de aplicación terrestre. 
Incluso podríamos introducirlo discretamente en el nombre
Hasta ahora estamos hablando de Space Health Digital Twin / Autonomous Space Health Node.
Pero el concepto de fondo podría ser algo como:
ONE HEALTH NODEBorn for space. Built for anywhere.
o
LIFELINEHealthcare beyond Earth. Healthcare beyond reach.
o incluso:
225
porque esa distancia variable Tierra-Marte puede convertirse en una metáfora del problema: la distancia no debería determinar la posibilidad de recibir atención sanitaria.
No decidiría todavía el nombre. Hay tiempo para eso.
Lo que sí incorporaría desde ahora al proyecto es un principio:
No desarrollar una tecnología exclusivamente para sobrevivir lejos de la Tierra, sino investigar qué podemos aprender cuidando de un ser humano allí para cuidar mejor de seres humanos aquí.
Y eso nos da una estructura conceptual bastante bonita para Space Apps:
NASA DATA → SPACE HEALTH → EXTREME CONSTRAINTS → INNOVATION → EARTH APPLICATION
Además, encaja extraordinariamente bien con algo que Stuhlinger escribió hace 56 años: la exploración espacial no sólo consiste en estudiar otros mundos; también puede proporcionarnos conocimiento, tecnología y nuevas formas de resolver problemas en el nuestro. 
Yo conservaría esta carta como una de las referencias conceptuales centrales del proyecto, no como fuente técnica. Puede resultar muy útil cuando llegue el momento de construir el storytelling y el pitch.
https://www.linkedin.com/posts/brunoescobar_zerokeyusb-hardware-ciberseguridad-activity-7495181338208018432-19B9?utm_source=share&utm_medium=member_android&rcm=ACoAACVj1I4BNwUMiX2KIoNRFNhHjjtXprFrh1M
Sí, este enlace aclara bastante mejor qué querías aportar al proyecto con ZeroKeyUSB. En mi respuesta anterior me fui sobre todo a la filosofía offline/local-first, pero esta publicación aporta otra dimensión: hardware real, pequeño, autónomo y fabricable.
Bruno muestra que las PCB de ZeroKeyUSB ya están fabricadas y montadas, pendientes de incorporar la pantalla OLED para pasar al montaje final y pruebas. Incluso cuenta un problema muy concreto de fabricación: recibieron pantallas de 15 pines en lugar de las de 14 previstas. 
Eso me hace pensar que deberíamos explorar una variante física del proyecto.
De software a un pequeño «Health Node»
El challenge pide software, así que el núcleo debe seguir siendo software. Pero podríamos presentarlo ejecutándose sobre un dispositivo físico muy sencillo, aproximadamente:
ASTRONAUT HEALTH NODE
OLED / pequeña pantalla
Microcontroller / SBC
Local storage
USB-C
Bluetooth / sensor input
Health AI / anomaly model
Sin pretender construir un dispositivo médico certificado ni diseñar hardware espacial real.
El prototipo podría recibir datos simulados o reales de un wearable y mostrar algo extremadamente simple:
CREW 02♥ 78 bpmHRV ↓ 12%Sleep ↓Radiation ↑
HEALTH STATUS: CAUTION
y desde una interfaz más completa explicar el motivo.
Esto introduce algo que para una presentación presencial de Space Apps puede tener muchísimo valor: el proyecto deja de ser solamente una pantalla de ordenador.
Y la publicación nos da otra lección
Bruno termina indicando las siguientes fases:
pantallas → montaje final → pruebas. 
Es decir, hay una diferencia entre tener una idea de arquitectura y tener algo que puedas poner encima de una mesa y demostrar.
Para nuestro hackathon yo establecería esa misma regla:
El jurado tiene que poder verlo funcionar.
Por ejemplo, colocamos el pequeño Health Node encima de la mesa.
Le introducimos una secuencia temporal:
Mission Day 126
HRV normal → normal → ↓ → ↓Sleep 7.4h → 6.8h → 5.9hRadiation nominal → elevatedResting HR 64 → 69 → 74
El dispositivo cambia:
NOMINAL → WATCH → CAUTION
En el ordenador aparece:
WHY?
y el sistema explica qué variables han provocado la alerta, su evolución respecto del baseline y qué protocolo recomienda consultar.
Entonces modificamos los datos.
El astronauta descansa, mejora el sueño y se normalizan determinados indicadores:
CAUTION → RECOVERING → NOMINAL
Eso es una demo, no simplemente una presentación.
Y aquí empiezan a encajar las piezas que has ido enviando
Yo ya no las veo como enlaces independientes:
NASA Challenge→ define el problema.
OSDR / OSD-288→ aporta ciencia y datos biológicos espaciales.
Astroquery / fuentes NASA→ pueden aportar contexto de misión cuando resulte relevante.
ZeroKeyUSB→ inspira autonomía, simplicidad y potencial materialización física.
Stuhlinger→ proporciona el por qué: resolver problemas extremos en el espacio puede producir soluciones útiles en la Tierra.
Y podríamos terminar teniendo:
SPACE
Astronaut → sensors → Health Node → local intelligence → decision support
↓ transferencia tecnológica
EARTH
Persona en ubicación remota → sensors → Health Node → local intelligence → medical support
Eso empieza a ser bastante más interesante que «una aplicación que monitoriza la salud de los astronautas».
Pero mantendría una disciplina importante: no decidir todavía que todo esto debe entrar en el MVP. Algunas piezas pueden quedarse como visión futura. Primero tenemos que encontrar el núcleo mínimo que podamos demostrar de forma convincente durante Space Apps.
Además, hay un detalle de esta publicación que me gusta especialmente para nuestro enfoque: muestra que incluso un error tan pequeño como 14 frente a 15 pines puede detener una fase de producción. En un sistema pensado para funcionar lejos de la Tierra, reducir dependencias y puntos de fallo no es estética de diseño; forma parte del problema que estamos intentando resolver.
https://x.com/miriamgonp/status/2101729927590453255
Este enlace no he podido leerlo: X está bloqueando el acceso externo al post (403) y la publicación todavía no aparece indexada en los buscadores que puedo consultar.
Como los enlaces que me estás pasando están construyendo el contexto del proyecto, prefiero no inferir el contenido. Si me pasas una captura del post —o copias aquí el texto— lo analizo y lo conecto con lo que ya tenemos: NASA Challenge + OSDR + Astroquery + autonomía/ZeroKeyUSB + Stuhlinger + aplicación terrestre.
https://data.nasa.gov/
Sí. Este recurso es central para el proyecto.
NASA define Data.nasa.gov como su repositorio público central de metadatos de datasets sobre ciencia, exploración espacial, aeronáutica y otros ámbitos. Un matiz importante: normalmente no aloja los datos, sino que funciona como catálogo que conduce al archivo NASA donde reside cada dataset. 
Para nuestro challenge, esto significa que tenemos ya un pequeño ecosistema de fuentes:
OSDR → biología y efectos del vuelo espacialData.nasa.gov → descubrimiento transversal de datasets NASAAPI.nasa.gov → APIs que puedan alimentar dinámicamente el sistemaCode.nasa.gov → software NASA reutilizable/estudiableNTRS → papers, informes técnicos y documentación científica NASAAstroquery → acceso programático a archivos y servicios astronómicos
NASA enlaza precisamente varios de estos recursos desde su portal de Open Data. 
Para nuestro proyecto, yo haría algo bastante específico ahora: no buscar “health” genéricamente. Buscaría datasets alrededor de las variables que necesitará nuestro modelo:
astronaut / human health / spaceflight / physiological / cardiovascular / sleep / exercise / radiation / immune / bone / muscle / cognition / behavioral health / CO₂ / environment / space weather
Y los clasificaría después en tres niveles:
INPUT — información que podríamos recibir durante una misión: HR, HRV, sueño, actividad, radiación, CO₂, etc.
KNOWLEDGE — datasets históricos que utilizamos para construir/calibrar nuestros modelos: OSDR, estudios humanos, animales, omics, etc.
CONTEXT — posición, misión, ambiente espacial, radiación/space weather y demás variables que modifican el riesgo.
Hay además una cuarta pieza que NASA enlaza y que puede ser incluso más valiosa que Data.nasa.gov para justificar científicamente nuestro sistema: el NASA Technical Reports Server (NTRS), que contiene informes técnicos, publicaciones y presentaciones NASA. 
Eso nos permitiría hacer algo metodológicamente mucho mejor que entrenar una IA con datos y esperar que encuentre correlaciones:
NASA research → seleccionamos factores de riesgo conocidos → NASA datasets → construimos modelo → datos del astronauta → detectamos desviaciones → explicamos alerta.
Así evitamos buena parte del problema de la IA médica como caja negra.
Y veo una decisión de diseño cada vez más clara: el Digital Twin no tiene por qué intentar reproducir todo el cuerpo humano. Podemos construir inicialmente 4–6 módulos de riesgo científicamente defendibles —por ejemplo cardiovascular, sueño/recuperación, inmunológico, musculoesquelético, radiación y behavioral/cognitive— y hacer que cada uno tenga sus propios inputs y evidencias NASA.
Eso es muchísimo más viable para un hackathon.
Creo que ya hemos recopilado suficientes recursos generales. El siguiente trabajo útil es dejar de añadir fuentes y empezar a explotarlas: puedo investigar Data.nasa.gov + OSDR + NTRS y construir un NASA Health Data Map específico para este challenge, indicando para cada fuente/dataset: datos disponibles, variables, humanos/animales, formato, utilidad para nuestro MVP y módulo del Digital Twin al que alimentaría.
https://www.nasa.gov/humans-in-space/living-in-space/
Sí. Esta página encaja como fuente de contexto operativo del proyecto: cómo es realmente vivir y trabajar en el espacio, no solo qué datos biomédicos existen.
NASA reúne aquí información sobre vida cotidiana a bordo, alimentación, ejercicio, higiene, sueño, trabajo y adaptación a la microgravedad. Para nuestro sistema esto importa porque la salud del astronauta no debería interpretarse únicamente a partir de constantes fisiológicas: actividad, descanso, ejercicio, alimentación y condiciones de vida forman parte del contexto que explica esas constantes.
La incorporaría al mapa de fuentes como:
NASA Living in Space → contexto humano y operacional
mientras que:
OSDR → evidencia biológica, Data.nasa.gov → datasets, Astroquery → contexto astronómico/de misión.
Esto refuerza una idea importante para el diseño: el baseline del astronauta debería ser contextual, no simplemente biométrico. Un cambio en HRV, frecuencia cardiaca o sueño tiene diferente significado dependiendo de ejercicio, carga de trabajo, descanso, exposición ambiental y momento de la misión.
Así que añadiría al futuro Astronaut Health Digital Twin una capa que hasta ahora no habíamos explicitado:
BIOLOGY + PHYSIOLOGY + ENVIRONMENT + BEHAVIOR + MISSION CONTEXT
→ Personal Baseline
→ Deviation / Trend
→ Risk Interpretation
→ Explainable Recommendation
Y esto también nos ayuda a no caer en un error frecuente: diseñar al astronauta como si fuese simplemente “un paciente conectado a sensores”. Es una persona que vive durante meses dentro de un ecosistema extremadamente particular.
Estoy guardando mentalmente estos enlaces como piezas del mismo mapa. Cuando terminemos de aportarlos, podemos hacer una síntesis completa de todo el material que has ido reuniendo y convertirlo en la primera definición formal del proyecto para Space Apps 2026.
https://www.nasa.gov/humans-in-space/the-human-body-in-space/
Esta página es mucho más importante para nuestro proyecto que la anterior de Living in Space. De hecho, NASA nos proporciona aquí una estructura que podemos utilizar casi directamente para diseñar el sistema.
NASA agrupa los principales peligros del vuelo espacial humano bajo el acrónimo RIDGE: Radiation, Isolation and Confinement, Distance from Earth, Gravity Fields y Hostile/Closed Environments. 
Y hay algo especialmente relevante: NASA dice expresamente que está desarrollando una arquitectura de datos médicos para las naves que permita herramientas de apoyo a la decisión clínica, potencialmente mediante IA y machine learning, para ayudar al diagnóstico y tratamiento en misiones distantes. También investiga asistentes virtuales para ayudar a las tripulaciones a responder autónomamente a problemas. 
Eso valida bastante bien la dirección que estamos construyendo.
RIDGE puede convertirse en la columna vertebral
Yo reorganizaría nuestra idea alrededor de esos cinco riesgos oficiales de NASA:
| RIDGE | Qué vigilaría nuestro sistema |
| R — Radiation | dosis acumulada, tasa de exposición, eventos solares, evolución del riesgo |
| I — Isolation & Confinement | sueño, ritmo circadiano, fatiga, rendimiento cognitivo, comportamiento |
| D — Distance from Earth | autonomía médica, capacidad offline, decisión sin Mission Control |
| G — Gravity Fields | hueso, músculo, cardiovascular, equilibrio, coordinación, fluid shift |
| E — Hostile/Closed Environment | CO₂, temperatura, calidad del aire, contaminantes, microbiología, interacción ambiente-salud |
No es una taxonomía que inventemos nosotros. Es la estructura que utiliza NASA para explicar los riesgos humanos de misiones a Marte. 
Y cada módulo tiene variables observables
Por ejemplo, en Isolation, NASA habla explícitamente de sueño, ritmos circadianos, fatiga, carga de trabajo, motivación, comportamiento y cognición. Utiliza actigrafía y hasta tests de vigilancia y atención de diez minutos. 
En Gravity, encontramos datos muchísimo más concretos. NASA señala una pérdida media aproximada del 1–1,5 % mensual de densidad mineral en huesos que soportan peso durante el vuelo espacial si no se aplican las contramedidas adecuadas. También aparecen pérdida muscular, cambios cardiovasculares, desplazamiento de fluidos hacia la cabeza, problemas visuales y mayor riesgo de cálculos renales. 
En Environment, NASA relaciona el entorno cerrado con alteraciones inmunológicas y estrés y monitoriza la calidad del aire frente a contaminantes como formaldehído, amoníaco y monóxido de carbono. 
Y en Radiation, distingue tres grandes fuentes: partículas atrapadas por el campo magnético terrestre, partículas energéticas solares y rayos cósmicos galácticos. La estrategia actual incluye monitorización de radiación, blindaje y procedimientos operacionales. 
Pero «Distance from Earth» me parece nuestro hueco
Aquí aparece probablemente la justificación más fuerte de nuestra propuesta.
NASA recuerda que Marte puede implicar hasta unos 20 minutos de retraso de comunicación en un solo sentido. Eso significa que la tripulación tiene que ser capaz de identificar problemas y encontrar soluciones sin depender inmediatamente de Mission Control. 
Por tanto, nuestra filosofía:
Local-first · Offline-first · Autonomous · Explainable · Human-in-the-loop
ya no es simplemente algo inspirado en ZeroKeyUSB.
Responde directamente al D de RIDGE.
Y podemos formular el problema de manera bastante potente:
The farther humans travel from Earth, the more healthcare must travel with them.
Ahí veo un posible núcleo narrativo del proyecto.
Cambiaría ligeramente nuestra idea del Digital Twin
Hasta ahora hablábamos de cinco o seis módulos médicos independientes. Después de leer esta fuente, creo que sería más elegante utilizar dos capas.
Capa 1 — NASA RIDGE
RadiationIsolationDistanceGravityEnvironment
↓
Capa 2 — HUMAN
CardiovascularMusculoskeletalImmuneSleep / CircadianCognitive / BehavioralVision / Sensorimotor
↓
PERSONAL HEALTH DIGITAL TWIN
De esta forma podemos relacionar causa → efecto.
Por ejemplo:
Microgravity
↓
Muscle loading ↓
↓
Muscle mass trend ↓
↓
Exercise adherence ↓
↓
Musculoskeletal risk ↑
O:
Isolation + workload
↓
Sleep ↓
↓
HRV ↓ + vigilance ↓
↓
Fatigue / cognitive risk ↑
Esto sería mucho más explicativo que un simple Health Score = 72.
Y aquí OSDR cobra todavía más sentido
Ahora podemos buscar los datasets no aleatoriamente, sino preguntando:
¿Qué datasets NASA tenemos para cada relación RIDGE → Human System?
Por ejemplo:
Radiation → Immune → OSD-288 y otros estudios.
Microgravity → Muscle/Bone → datasets OSDR.
Isolation → Sleep/Cognition → estudios humanos/análogos.
Environment → Immune → microbioma + datos ambientales.
Eso nos permitiría construir una matriz científica:
NASA Hazard → Biological effect → Observable variable → NASA dataset → Detection model → Countermeasure
Esa matriz podría terminar siendo el verdadero cerebro científico del proyecto.
Y hay un último detalle importante. NASA lleva más de 50 años utilizando su Human Research Program para estudiar estos efectos y convertir el conocimiento obtenido en procedimientos, dispositivos, estándares médicos, programas de ejercicio, entrenamiento fisiológico/psicológico y protocolos nutricionales. 
Por tanto, nuestro sistema no tendría que inventar tratamientos. Podría hacer algo más defendible:
detectar → explicar → relacionar con riesgo NASA → recuperar la contramedida/protocolo correspondiente → ayudar al astronauta a decidir.
Eso reduce mucho el riesgo de presentar una «IA que hace de médico» y nos acerca más a un autonomous clinical decision-support system.
Creo que con esta fuente hemos encontrado una estructura científica mucho más sólida para todo lo que veníamos construyendo.
https://www.nasa.gov/hrp/
Sí. Esta probablemente sea la fuente institucional más importante que has pasado hasta ahora para construir el proyecto.
El Human Research Program (HRP) tiene precisamente como misión investigar y desarrollar métodos para proteger la salud y el rendimiento de los astronautas, pensando en misiones hacia Marte y más allá. Para ello combina investigación terrestre, ISS y entornos análogos. 
Y al revisar la página actual —actualizada el 9 de septiembre de 2026— aparecen varias piezas que nos ayudan mucho.
HRP nos da la arquitectura científica
NASA divide el programa en grandes áreas que prácticamente podemos trasladar a nuestro sistema:
Human Factors & Behavioral Performance → comportamiento, cognición, sueño, rendimiento.
Human Health Countermeasures → efectos fisiológicos del vuelo espacial y contramedidas.
Space Radiation → exposición y riesgo radiológico.
Research Operations & Integration → integración de la investigación realizada en Tierra, simulaciones, ISS y otras plataformas. 
Esto encaja perfectamente con la estructura RIDGE → Human Systems → Detection → Countermeasure que acabábamos de plantear.
Pero he encontrado algo todavía más importante.
Hay tres repositorios distintos que debemos investigar
HRP distingue expresamente:
NASA Life Sciences Portal (NLSP)Datos de investigación humana procedentes de vuelos espaciales y estudios análogos, remontándose hasta 1961. 
Open Science Data Repository (OSDR)Datos celulares humanos y datos de ciencias de la vida no humanas. Es donde estamos encontrando, por ejemplo, OSD-288. 
Lifetime Surveillance of Astronaut Health (LSAH)Utiliza datos de seguimiento médico para la vigilancia longitudinal de la salud de astronautas. 
Esto es importante porque estábamos concentrándonos bastante en OSDR. Para construir un Digital Twin humano, NLSP puede resultar incluso más relevante.
Nuestra búsqueda de datos debería pasar a:
NLSP — Human Research
OSDR — Biological / Omics
LSAH — Longitudinal medical surveillance
Environmental / Mission data
Y aparece algo que quiero investigar específicamente: IMM
En la página actual de HRP aparece destacada una publicación de hace apenas 7 días:
NASA's Integrated Medical Model (IMM). 
Esto merece que nos detengamos.
Porque Integrated Medical Model suena extraordinariamente próximo a lo que estamos intentando diseñar. Antes de definir nuestro MVP tenemos que estudiar qué hace exactamente IMM, qué inputs utiliza, cómo modela el riesgo médico y —sobre todo— qué problema deja sin resolver.
No queremos presentar a NASA algo que NASA ya tiene.
Pero si descubrimos:
IMM → modela riesgo médico de misión
mientras nuestro sistema:
Health Node → monitoriza dinámicamente al individuo + aprende su baseline + detecta desviaciones + explica + recomienda
entonces podríamos encontrar una complementariedad muy potente.
Hay además otra organización que debemos incorporar al mapa
NASA destaca TRISH — Translational Research Institute for Space Health, que financia investigación científica y tecnologías destinadas a mantener saludables a los astronautas en misiones de espacio profundo hacia Luna, Marte y más allá. 
Y TRISH puede ser especialmente interesante para nosotros porque está justamente en la intersección:
Space Health + Technology + Translation.
Es decir, muy cerca de la filosofía que hemos obtenido de Stuhlinger:
SPACE → innovación → EARTH.
Con todo lo que has ido aportando, ya empieza a aparecer una estructura bastante sólida:
PROBLEMA
NASA Space Apps ChallengeCreate Health Monitoring Software for Astronauts
↓
MARCO DE RIESGOS
NASA HRPRIDGE / Five Hazards
↓
INVESTIGACIÓN HUMANA
NLSP
↓
BIOLOGÍA / OMICS
OSDR
↓
SEGUIMIENTO LONGITUDINAL
LSAH
↓
CONTEXTO
Living in Space + Environment + Mission + Radiation
↓
MODELOS NASA EXISTENTES
IMM + HRP Countermeasures
↓
NUESTRA CAPA
Personal Health Digital Twin
↓
AUTONOMÍA
Local-first / Offline-first / Explainable / Human-in-the-loop
↓
DISPOSITIVO
Autonomous Health Node
↓
IMPACTO
Space → Earth
↓
STORYTELLING
Stuhlinger
Creo que ahora sí hemos llegado a un punto importante: antes de seguir diseñando nuestra solución, investigaría a fondo el Integrated Medical Model (IMM).
Puede ser la pieza que nos diga exactamente dónde está el hueco de innovación que debemos atacar en Space Apps 2026.
https://www.nasa.gov/international-space-station/
La incorporo. La página de la International Space Station (ISS) es especialmente útil como fuente del entorno real de experimentación y operación sobre el que se ha construido buena parte del conocimiento que estamos utilizando.
Para nuestro proyecto la clasificaría principalmente como Mission / Operational Context + Research Platform: nos permite conectar los estudios de HRP y OSDR con las condiciones reales de vida y trabajo en microgravedad, las investigaciones realizadas a bordo y las tecnologías probadas en vuelo.
Además, nos ayuda a mantener una distinción importante en el proyecto: ISS no es Marte. En órbita baja existe una infraestructura, capacidad de comunicación y proximidad relativa a la Tierra que no tendremos en una misión de espacio profundo. Precisamente ese salto de ISS → Moon → Mars es donde cobra fuerza nuestra propuesta de mayor autonomía sanitaria.
La guardaría, por tanto, para tres usos posteriores: fuente de investigaciones y experimentos, contexto operacional para nuestros escenarios de prueba y punto de comparación para explicar por qué la medicina de espacio profundo necesita evolucionar hacia sistemas más autónomos.
Sigue pasándome los recursos que tengas. De momento prefiero ir clasificándolos sin cerrar prematuramente la solución; cuando acabes, hacemos la síntesis conjunta y vemos qué idea emerge realmente de las fuentes.
Ver sinergias y conocer proveedores e investigadores y los retos actuales
Conocer instalaciones, equipos y vida diaria para conocer necesidades
Sí. Ese enfoque me parece incluso más importante: antes de diseñar “la solución”, conviene entender cómo se vive realmente en la ISS, qué equipos existen, qué tareas consumen tiempo, qué datos se recogen y dónde están las fricciones. Ahí pueden aparecer necesidades que no vemos leyendo solo el challenge.
He empezado a mapearlo y ya salen varias pistas claras.
La ISS dispone de una infraestructura médica y de investigación bastante rica. El Human Research Facility (HRF) incluye dos racks en el módulo Columbus y equipos almacenados que se sacan cuando hacen falta. NASA menciona, entre otros, ecografía clínica, medición de masa corporal en microgravedad, equipos para presión arterial y función cardiaca, centrífuga refrigerada, actígrafos y otros instrumentos fisiológicos. 
También existe una capa de monitorización de actividad y sueño mediante actigrafía, con wearables que registran movimiento y exposición a luz para estudiar ritmos circadianos y patrones sueño-vigilia. NASA sigue usando sensores durante la jornada para monitorizar signos vitales y adaptación a la microgravedad. 
Hay además un Crew Health Care System (CHeCS) apoyado desde Tierra por Biomedical Flight Controllers y Flight Surgeons. Ese equipo recibe y supervis
Fuentes
https://www.nasa.gov/humans-in-space/step-3-artemis-moon-missions-as-an-astronaut-testbed-for-mars/
Este enlace encaja exactamente con el enfoque que acabas de marcar: usar Artemis y Gateway como “laboratorio real” para descubrir necesidades de salud antes de Marte.
NASA plantea una progresión muy clara: análogos en Tierra → ISS → Artemis/Luna → Marte. La idea es usar las misiones lunares para probar en un entorno de espacio profundo qué capacidades médicas, procedimientos y tecnologías funcionan cuando la tripulación tiene que depender menos de la Tierra. 
Para nuestro proyecto, de esta página extraería cinco necesidades muy concretas:
Autonomía médica creciente: NASA quiere comprobar que la tripulación pueda realizar exámenes y procedimientos con menos apoyo desde Mission Control. 
Equipos pequeños y ligeros: se menciona explícitamente la necesidad de dispositivos compactos, algo muy relevante para nuestro posible Health Node. 
Uso independiente de instrumentos, por ejemplo ecografía miniaturizada sin guía constante desde Tierra. 
Adaptación fisiológica a distintos campos gravitatorios: microgravedad durante el viaje, 1/6 g en la Luna y aproximadamente 1/3 g en Marte. Eso afecta a cardiovascular, equilibrio, movilidad y capacidad de realizar tareas nada 
Fuentes
Analizar el banco de pruebas y diferencias y requerimientos en la ISS y en Luna o Marte
https://www.nasa.gov/international-space-station/space-station-astronaut-record-holders/
Ver posibilidades análisis post vuelo y valorar su evolución posterior y datos clínicos
Sí. Aquí veo una línea muy potente para el proyecto: no limitar el sistema a “qué pasa durante el vuelo”, sino estudiar el ciclo completo pre-vuelo → vuelo → aterrizaje → recuperación → seguimiento a largo plazo.
NASA ya trabaja exactamente así. El programa CIPHER integra 14 estudios sobre distintos sistemas del cuerpo y recopila datos antes, durante y después de la misión: visión, cognición, razonamiento espacial, imagen cardiovascular, ejercicio, función sensoriomotora, resonancias, muestras biológicas y otros biomarcadores. Su objetivo es observar cómo cambia el organismo con distintas duraciones de vuelo y cómo se recupera después. 
El post-vuelo puede ser un “banco de pruebas” extraordinario
Al volver a la Tierra, NASA monitoriza la readaptación a la gravedad, el grado de desacondicionamiento y los cambios asociados a la misión. Los estándares NASA exigen exploraciones médicas inmediatamente después del aterrizaje y posteriormente hasta estabilización, pruebas de laboratorio e imagen, recuperación física individualizada, control del sueño/circadiano, nutrición y apoyo conductual. 
Esto permite algo que me interesa mucho para nuestra idea:
hacer predicciones durante el vuelo y comprobar después si eran correctas.
Por ejemplo:
Pre-flight baseline→ HRV, capacidad cardiovascular, músculo, hueso, cognición…
In-flight→ nuestro modelo estima tendencia y riesgo.
`R+0 / R+1 / R+4 / R
Fuentes
https://www.nasa.gov/humans-in-space/twins-study/
Sí: el Twins Study es una referencia fundamental para la línea que propones de analizar evolución clínica antes, durante y después del vuelo.
NASA comparó durante 340 días a Scott Kelly en la ISS con su hermano gemelo idéntico Mark Kelly en Tierra. Diez equipos estudiaron simultáneamente **metabolómica, proteómica, cognición, microbioma, telómeros, epigenómica, bioquímica, expresión génica, inmunidad e integración multi-ómica
Ver parámetros comparados a efectos del estudio
Sí. El Twins Study nos da una referencia excelente para decidir qué parámetros tiene sentido comparar longitudinalmente en nuestro proyecto, porque NASA no analizó una sola variable, sino una combinación de capas biológicas, fisiológicas y cognitivas antes, durante y después del vuelo. 
Los diez bloques comparados fueron:
| Área | Qué se comparó | Utilidad para nuestro sistema |
| Metabolómica | Metabolitos, inflamación, estrés oxidativo, función vascular, riesgo aterosclerótico | Detectar cambios metabólicos y cardiovasculares |
| Proteómica | Proteínas, desplazamiento de fluidos, hidratación y mecanismos asociados a cambios oculares | Relacionar fluid shift con visión e hidratación |
| Cognición | Alerta mental, velocidad, precisión, orientación espacial, reconocimiento emocional | Fatiga, rendimiento y recuperación post-vuelo |
| Microbioma | Composición de la flora intestinal | Nutrición, inmunidad y adaptación |
| Telómeros | Longitud y dinámica telomérica | Estrés celular y posible seguimiento a largo plazo |
| Epigenómica | Metilación del ADN y regulación genética | Cambios inducidos por ambiente espacial |
| Bioquímica | Sangre, orina, peso corporal, folato, metabolismo óseo, nutrición | Excelente fuente de |
Fuentes
Debe haber un recopilatorio de datos
Sí, y de hecho he encontrado el punto clave: NASA sí tiene un repositorio recopilatorio, pero no todo está abierto al mismo nivel.
El lugar principal es OSDR — Open Science Data Repository. NASA lo define como un repositorio multimodal de datos de ciencias de la vida en el espacio, incluyendo ómicas, datos fisiológicos, fenotípicos, conductuales, biomédicos, bioimagen, telemetría ambiental, hardware y metadatos. 
Para estudios derivados de astronautas, NASA publica de forma abierta buena parte de los datos procesados, mientras que ciertos datos humanos sensibles o secuencias están sometidos a acceso controlado y requieren una solicitud específica. 
Y hay un dataset especialmente interesante para lo que buscas: OSD-343, que integra datos de cientos de muestras espaciales, métricas humanas de 59 astronautas y datos confirmatorios del Twins Study para estudiar conjuntamente respuestas transcriptómicas, proteómicas, metabolómicas y epigenéticas al vuelo espacial. 
Además, NASA ofrece API para acceder programáticamente a OSDR y explorar estudios, experimentos, sujetos, muestras, misiones, vehículos, hardware y archivos asociados. 
Eso abre una línea de trabajo mucho más ambiciosa para nuestro proyecto:
crear nuestro propio “Astronaut Longitudinal Health Dataset Map”, no necesariamente copiando todos los datos, sino identificando:
qué parámetros existen, 
en qué estudio aparecen, 
qué periodos cubren, 
si son pre-vuelo, in-flight o post-vuelo, 
si son humanos o animales, 
si están abiertos o restringidos, 
y si sirven para entrenar, validar o simplemente contextualizar nuestro modelo. 
Yo empezaría por tres conjuntos:
Twins Study → longitudinal extremo N=1, muy rico en capas biológicas. OSD-343 → integración de métricas de 59 astronautas + multi-omics. CIPHER / estudios HRP humanos → para evolución fisiológica y recuperación post-vuelo.
Con eso podríamos empezar a construir una auténtica matriz:
Astronauta / Cohorte → Variable → Baseline → In-flight → R+0 → R+7 → R+30 → R+180 → tendencia → recuperación
Y creo que ahí puede estar una de las aportaciones más interesantes del proyecto: no sólo detectar riesgo durante el vuelo, sino aprender del patrón de recuperación posterior para mejorar futuras predicciones en vuelo.
Eso nos permitiría cerrar un bucle:
predicción durante misión → resultado post-vuelo → validación → modelo mejorado
Ese ciclo de aprendizaje me parece mucho más sólido que un simple monitor de constantes.
https://share.google/ZdtkBDXcRm98JwTOa
Este enlace abre mediante un redirect de Google Share y desde aquí no puedo resolver el contenido final: el acceso se detiene antes de mostrarme qué recurso has compartido.
Pásame el enlace original de destino (NASA, artículo, documento, etc.) o una captura y lo incorporo al análisis que estamos construyendo.
Tengo ya clara la línea que quieres que sigamos: no sólo diseñar una aplicación, sino entender el ecosistema completo de salud humana espacial —ISS como banco de pruebas, Artemis/Luna como siguiente nivel, Marte como escenario de autonomía; instalaciones y equipos; vida diaria; proveedores e investigadores; parámetros médicos; datos pre/in/post-vuelo; recuperación posterior; Twins Study y repositorios longitudinales— para que las necesidades reales sean las que nos lleven a la solución, y no al revés.
https://www.estacionespacial.com/cof.php
Este enlace sí nos aporta una pieza concreta para la línea que acabas de definir: conocer las instalaciones y equipos reales en los que se investiga la fisiología humana.
La página describe Columbus, el laboratorio europeo presurizado de la ISS, y entre sus instalaciones originales incluye el European Physiology Laboratory (EPM), junto con Biolab, Fluid Science Laboratory y Material Science Laboratory. 
Para nuestro proyecto, el EPM es mucho más importante que Columbus en abstracto. Yo lo incorporaría como un nodo específico de investigación:
ISS → Columbus → European Physiology Laboratory → investigación humana → parámetros medidos → instrumentos → investigadores → experimentos → datasets resultantes.
Además, Columbus está organizado alrededor de racks estandarizados ISPR, con instalaciones experimentales integradas en un entorno presurizado. Esto nos interesa porque quiero que investiguemos no sólo qué se mide, sino cómo se mide actualmente a un astronauta: qué aparato utiliza, cuánto ocupa, cuánto tiempo de tripulación requiere, si necesita muestras, si el resultado es inmediato o posterior, etc.
Una nueva variable importante: «coste de medir»
Hasta ahora hemos hablado mucho de parámetros médicos. Pero para diseñar algo realmente útil necesitamos añadir otra dimensión:
¿Cuánto cuesta obtener cada parámetro en el espacio?
No sólo dinero. También:
tiempo del astronauta + hardware + masa + volumen + energía + consumibles + calibración + procesamiento + intervención desde Tierra + formación
Esto puede descubrir necesidades que un simple análisis médico no revela.
Por ejemplo, puede haber un biomarcador científicamente extraordinario pero que requiera extracción de sangre, preparación, congelación y análisis posterior. Para monitorización autónoma diaria en Marte, quizá sea mucho menos útil que una señal fisiológica algo menos precisa pero medible continuamente mediante un wearable.
Ahí podemos empezar a clasificar:
Continuo y pasivo → ideal para nuestro sistema.
Periódico y no invasivo → muy interesante.
Periódico e invasivo → útil para confirmación.
Laboratorio complejo → conocimiento para entrenar/validar modelos, pero posiblemente no input operativo.
Esto encaja perfectamente con lo que querías hacer con Twins Study + datos post-vuelo.
También quiero tener cuidado con esta web
estacionespacial.com nos sirve muy bien como mapa inicial en castellano, pero parte del contenido técnico es histórico. Por ejemplo, describe Columbus desde su fase de planificación/desarrollo. Para cualquier decisión del proyecto verificaría después cada instalación contra NASA/ESA actuales.
Y eso nos da una tarea de investigación bastante clara: seguir la pista del European Physiology Laboratory hasta la actualidad y averiguar qué equipos contiene o ha contenido, qué parámetros humanos se han medido, qué experimentos se han realizado, quiénes son los investigadores/centros/proveedores y dónde han terminado sus datos.
Ahí podemos empezar a conectar físicamente instalación → instrumento → medición → astronauta → dataset → nuestro Health Node.
Y creo que esa trazabilidad va a ser bastante valiosa para encontrar una necesidad real, en lugar de inventarla desde fuera.
https://www.esa.int/kids/es/Aprende/Vida_en_el_Espacio/Estaciones_espaciales/%21El_laboratorio_Columbus_cumple_10_anos
Sí. Esta página de ESA refuerza la línea de Columbus como banco de pruebas de salud humana, pero nos aporta además una perspectiva europea muy útil para localizar experimentos, investigadores y tecnología.
Columbus es el laboratorio europeo de la ISS y ESA destaca que allí se realizan experimentos sobre cómo responde el cuerpo humano a la ingravidez, además de biología, física de fluidos, materiales y tecnología.
Para nuestro análisis, lo importante ahora no es tanto Columbus como módulo, sino reconstruir la cadena:
Columbus → instalación → experimento → equipo → parámetro fisiológico → investigador → proveedor → datos → aplicación médica
Y quiero añadir una comparación que puede resultar decisiva:
ISS/Columbus: laboratorio con apoyo terrestre relativamente cercano, comunicaciones frecuentes, infraestructura considerable y posibilidad de retorno de muestras.
Luna/Artemis: menor infraestructura, operaciones más autónomas, entorno radiológico diferente y logística mucho más limitada.
Marte: autonomía médica mucho mayor, retrasos de comunicaciones, imposibilidad práctica de evacuación rápida y necesidad de diagnóstico/seguimiento local.
Por tanto, no debemos preguntarnos solamente “¿qué puede medir Columbus?”, sino:
¿Qué capacidades médicas que actualmente dependen de la infraestructura de la ISS tendremos que miniaturizar, automatizar o sustituir para Luna y Marte?
Ahí puede aparecer nuestro verdadero problema de Space Apps.
Voy guardando Columbus/EPM como una de las ramas que tendremos que investigar con profundidad cuando hagamos el mapa ISS → Luna → Marte.
https://www.esa.int/Science_Exploration/Human_and_Robotic_Exploration/Columbus/Biolab
Sí. Biolab nos interesa mucho, pero por una razón distinta del European Physiology Module: no monitoriza directamente al astronauta; permite estudiar los mecanismos biológicos que explican lo que después observamos en humanos.
ESA lo diseñó para experimentos con microorganismos, células, cultivos de tejidos, plantas pequeñas e invertebrados, estudiando cómo cambia la biología en microgravedad. 
Y contiene varias ideas que deberíamos trasladar a nuestro análisis.
Biolab como «laboratorio causal»
Una característica especialmente potente es que puede realizar simultáneamente experimentos en microgravedad y experimentos con gravedad simulada mediante centrifugación, además de mantener controles equivalentes en Tierra. 
Eso permite una comparación muy valiosa:
Tierra 1g ↔ ISS microgravedad ↔ ISS 1g artificial
Por tanto, no estamos viendo simplemente que algo cambia en el espacio. Podemos intentar separar cuánto del cambio está relacionado específicamente con la gravedad.
Para nuestro futuro mapa de datos añadiría siempre:
Flight sampleIn-flight controlGround controlPre-flightPost-flight
cuando estén disponibles.
Pero hay otra cosa que me interesa todavía más: cómo funciona
Biolab incorpora incubación, centrifugadoras, almacenamiento con control de temperatura, instrumentación de análisis, manipulación automática de muestras y BioGlovebox para operaciones manuales en ambiente controlado. Las muestras pueden conservarse congeladas y después descongelarse y prepararse para el experimento. 
Una vez cargadas por el astronauta, buena parte del procesamiento puede hacerse automáticamente. Científicos en Tierra pueden además participar mediante teleoperación y recibir datos preliminares; los experimentos pueden durar desde un día hasta unos tres meses. 
Esto nos descubre otra variable fundamental para nuestra comparación ISS → Luna → Marte:
dependencia de Tierra.
Actualmente:
Astronauta prepara/carga muestra
↓
Biolab automatiza
↓
Tierra monitoriza/controla
↓
científico interpreta
↓
muestras/datos vuelven a Tierra
Para Marte esa arquitectura empieza a romperse.
Y aquí puede aparecer una necesidad real
En la ISS resulta razonable enviar determinados análisis a Tierra o que un científico participe mediante teleoperación. En Marte, la latencia de comunicaciones, logística y ausencia de retorno rápido obligan a desplazar capacidad hacia la misión.
Por eso incluiría en nuestro estudio una pregunta para cada equipo actual:
¿Qué parte de este proceso depende actualmente de Tierra y quién tendrá que realizarla cuando Tierra deje de estar disponible en tiempo real?
Puede ser software, astronauta, IA, automatización o nuevo hardware.
Esto es exactamente el tipo de necesidad que estamos buscando.
Un precedente especialmente interesante: inmunidad
ESA utilizó Biolab para investigaciones como TripleLux, cuyo objetivo incluía estudiar mecanismos celulares relacionados con la respuesta a radiación y el deterioro de la función inmunitaria durante el vuelo espacial. 
Esto conecta directamente con OSD-288, que habíamos identificado por sus datos de bazo/respuesta inmunitaria.
Podemos empezar a construir cadenas completas:
HAZARD
Radiación + microgravedad
↓
BIOLOGICAL MECHANISM
cambios celulares/inmunológicos
↓
EXPERIMENTAL EVIDENCE
Biolab / OSDR / otros estudios
↓
HUMAN MANIFESTATION
biomarcadores + fisiología + síntomas
↓
MONITORING
wearables + tests + muestras
↓
OUR SYSTEM
detección de desviación → interpretación → decisión.
Y Biolab nos da además una lección de diseño
ESA explica que la automatización fue diseñada precisamente para reducir mucho el tiempo requerido de la tripulación. 
Añadiría por tanto Crew Time como requisito explícito de nuestro proyecto.
No basta con que un sistema de salud sea científicamente bueno. Cada medición debería evaluarse por:
valor clínico / tiempo de astronauta / invasividad / hardware / consumibles / energía / masa / almacenamiento / dependencia de Tierra / frecuencia posible / capacidad de automatización.
Eso puede acabar siendo importantísimo.
Porque quizá nuestro proyecto no necesite encontrar más datos del astronauta. Puede que la innovación sea conseguir mucho más conocimiento médico a partir de menos mediciones y menor intervención humana.
Y eso sí sería especialmente relevante para Marte.
Voy viendo además que el mapa de instalaciones empieza a dividirse naturalmente:
EPM → qué ocurre fisiológicamente al astronauta.
Biolab → por qué ocurre biológicamente.
OSDR/NLSP → datos históricos para aprender esos patrones.
Nuestro sistema → qué está ocurriendo ahora, qué puede ocurrir después y qué decisión tomar.
Esta distinción me parece importante mantenerla mientras seguimos recorriendo las instalaciones de Columbus.
https://youtu.be/5GeAORj0Nw0?is=-TF-NzF3yjSXfl_j
Sí. Este vídeo es “International Space Station: Humanity’s Lab in Space”, producido por NASA y narrado por Adam Savage. NASA lo plantea precisamente como una visión de la ISS como laboratorio para descubrimientos imposibles o difíciles en Tierra y como banco de pruebas de tecnologías necesarias para volver a la Luna, además de aplicaciones terrestres. 
Para nuestra investigación lo marcaría como visión general / storytelling, pero confirma una línea mucho más importante que quiero incorporar al análisis que estamos construyendo.
NASA contempla expresamente la ISS como plataforma para desarrollar atención médica miniaturizada, autónoma y autosuficiente para vuelos espaciales, señalando además su posible transferencia a atención domiciliaria, ubicaciones remotas y países en desarrollo. Esto coincide casi exactamente con varias ideas que hemos ido deduciendo: Health Node, autonomía frente a Tierra, miniaturización y posterior aplicación terrestre.
Por tanto, en el mapa ISS → Luna → Marte quiero investigar algo más específico que “qué experimentos hay”: para cada capacidad sanitaria de la ISS, identificaré qué instalación/equipo la proporciona, cuánto depende de Tierra, qué intervención exige al astronauta, qué datos produce y qué tendría que cambiar para funcionar en Luna y Marte.
Además, el ecosistema de proveedores empieza a aparecer. NASA identifica, por ejemplo, a Boeing en ingeniería de sostenimiento de la ISS, Teledyne Brown Engineering en operaciones e integración, COLSA en soporte de operaciones de Huntsville y CASIS en la gestión del ISS National Laboratory. Más adelante debemos bajar de ese nivel general a los proveedores específicamente relacionados con human health, wearables, diagnóstico, análisis de muestras, ejercicio, life support y software médico.
Y mantendría muy presente una pregunta mientras vemos estos vídeos e instalaciones:
¿Qué puede hacer hoy un astronauta en la ISS porque tiene detrás toda la infraestructura de la ISS y de la Tierra que dejará de poder hacer de la misma manera en Marte?
Ahí es donde probablemente encontraremos los mejores requisitos para nuestro challenge.
Continúa pasándome material. Estoy viendo que tu enfoque de primero comprender profundamente cómo viven, trabajan, se miden y reciben apoyo los astronautas antes de diseñar la solución puede llevarnos a una propuesta bastante más fundamentada que empezar directamente construyendo una app.
https://www.nasa.gov/mission/station/research-explorer/investigation/?#id=975
Sí. Este enlace cambia bastante el nivel de detalle al que podemos llevar la investigación. Es el Space Station Research Explorer de NASA, es decir, podemos bajar desde “qué instalaciones existen en la ISS” hasta experimentos concretos.
El enlace con #id=975 intenta seleccionar una investigación concreta, pero NASA carga esa ficha dinámicamente y el identificador no aparece resuelto en la versión accesible desde aquí. No quiero atribuirle un experimento equivocado. Lo interesante es que el propio Research Explorer permite obtener información estructurada y ofrece incluso exportaciones en Excel y texto, además de separar descripción, aplicaciones, operaciones, publicaciones y experimentos/instalaciones relacionados. 
Esto encaja exactamente con el recopilatorio que estábamos buscando.
Lo explotaría como una base de datos de necesidades
No me limitaría a buscar “health”. Para cada experimento humano relevante extraería:
| Campo | Qué queremos averiguar |
| Experimento | Qué se investiga |
| Riesgo RIDGE | Radiation / Isolation / Distance / Gravity / Environment |
| Sistema humano | cardiovascular, músculo, hueso, inmunidad, visión, sueño, cognición… |
| Parámetro | qué se mide exactamente |
| Instrumento | con qué dispositivo/equipo |
| Frecuencia | continuo, diario, semanal, pre/post… |
| Astronauta | qué tiene que hacer |
| Crew time | cuánto trabajo requiere |
| Invasividad | wearable, saliva, sangre, ecografía… |
| Consumibles | qué necesita |
| Ground support | cuánto depende de especialistas en Tierra |
| Procesamiento | ISS / Tierra / post-vuelo |
| Resultado inmediato | sí/no |
| Investigadores | PI + instituciones |
| Proveedores | fabricante/integrador cuando sea identificable |
| Dataset | dónde acaba el dato |
| Publicaciones | qué han descubierto |
| Aplicación | utilidad espacial y terrestre |
| Luna | qué cambia |
| Marte | qué deja de funcionar |
| Opportunity | qué podríamos automatizar/miniaturizar/predecir |
Esta última columna es probablemente la más importante.
Podemos reconstruir el «hospital invisible» de la ISS
La ISS dispone de mucha más capacidad sanitaria de la que percibimos cuando vemos simplemente a un astronauta flotando con un wearable.
Detrás puede haber:
instrumento a bordo → astronauta entrenado → procedimiento → comunicaciones → especialista en Tierra → procesamiento → laboratorio → muestras almacenadas → retorno de muestras → análisis post-vuelo.
Nuestro reto debería preguntarse qué sucede cuando vamos eliminando elementos de esa cadena.
ISS
Astronaut → Instrument → Ground specialist → Earth laboratory
Luna
Astronaut → Instrument → mayor autonomía → Earth support
Marte
Astronaut → Instrument → onboard analysis → onboard decision support
Ahí aparece un concepto muy importante:
No tenemos que sustituir un dispositivo de la ISS. Podemos intentar trasladar a bordo parte de la inteligencia que actualmente está distribuida entre la ISS y cientos de personas e instalaciones en Tierra.
Eso encaja mucho mejor con un challenge de software.
Y podemos cruzarlo con el seguimiento post-vuelo
También conecta con tu observación anterior sobre estudiar qué ocurre después de regresar.
Para cada experimento deberíamos buscar:
L-180 → L-30 → Flight → R+0 → R+7 → R+30 → R+90 → R+180 → R+365
cuando existan esos puntos temporales.
Así podremos distinguir tres cosas:
AdaptationEl organismo cambia porque está en el espacio.
RiskEl cambio puede comprometer salud/rendimiento durante la misión.
RecoveryAl regresar, ¿cuánto tarda en volver al baseline? ¿Vuelve completamente?
Esto es importantísimo para entrenar un modelo. Un parámetro que cambia mucho durante el vuelo pero se recupera rápidamente puede tener un significado distinto de otro cuya alteración persiste meses.
Y aparece una posibilidad especialmente interesante
NASA ofrece desde el propio Research Explorer salida en Excel. 
Por tanto, en vez de ir analizando experimentos manualmente uno por uno, podemos intentar construir nuestro propio:
SPACE HUMAN HEALTH RESEARCH MAP
y cruzar:
ISS Research Explorer + HRP + OSDR + Twins Study + publicaciones + equipos + investigadores.
Después filtramos exclusivamente investigaciones relacionadas con salud humana.
El resultado puede acabar revelándonos algo muy valioso para Space Apps:
qué mide NASA mucho, qué mide poco, qué requiere demasiado trabajo, qué depende demasiado de Tierra, qué sólo se conoce después del vuelo y qué sería extremadamente valioso conocer durante el vuelo.
Ese último grupo —“hoy lo sabemos después; en Marte necesitaríamos saberlo ahora”— me parece uno de los lugares más prometedores para buscar nuestra propuesta.
Además, acabo de detectar en la propia NASA una publicación de hace 7 días sobre el Integrated Medical Model (IMM) y otra de hoy sobre riesgos de descompresión y tromboembolismo. Esto confirma que merece la pena incluir riesgo médico operacional actual, no sólo investigación histórica.
Creo que ya tenemos material suficiente para dejar de estudiar las fuentes aisladamente y empezar a construir ese mapa sistemático de experimentos, parámetros, equipos, investigadores, datos y gaps ISS → Luna → Marte.
https://www.nasa.gov/missions/artemis/orion/scientists-and-engineers-evaluate-orion-radiation-protection-plan/
Este artículo aporta una pieza muy concreta que nos faltaba: cómo se transforma un dato ambiental en una decisión operativa de salud en tiempo real.
En Orion, NASA prevé un instrumento integrado, HERA (Hybrid Electronic Radiation Assessor), para detectar un evento radiológico —por ejemplo, asociado a actividad solar— y alertar a la tripulación de que debe protegerse. Al abandonar la protección de la magnetosfera terrestre, la radiación adquiere mucha más relevancia que en la ISS. 
Lo interesante para nosotros es la cadena:
Sensor → Hazard detection → Alert → Procedure → Crew action → Protection
Eso es prácticamente un caso real de la arquitectura que estamos planteando.
Una solución muy ingeniosa: utilizar lo que ya está a bordo
NASA no quería resolver el problema simplemente añadiendo más blindaje porque eso implica más masa. El procedimiento estudiado para Orion aprovecha la propia carga de la nave: bolsas con suministros, alimentos y agua se redistribuyen alrededor de los astronautas para crear una zona más densamente protegida dentro del módulo. 
Esto conecta directamente con el principio que habíamos extraído de ZeroKeyUSB:
Resolver más añadiendo menos.
No es sólo interesante como filosofía. Masa, volumen, energía y consumibles deben formar parte de nuestra matriz de requisitos.
Hay un factor crítico: tiempo de reacción
NASA estudió que, ante una alerta, los astronautas pudieran construir el refugio en menos de una hora, y contempla situaciones en las que podrían permanecer allí hasta 24 horas. También evaluó cómo sujetar las bolsas, cómo introducir ventilación y cómo entrar y salir del refugio. 
Esto introduce una dimensión que todavía no habíamos explicitado suficientemente:
TIME TO ACTION.
Para cada riesgo deberíamos medir:
Detection time → Interpretation time → Decision time → Intervention time → Recovery/monitoring
Un sistema que prediga algo con mucha precisión pero demasiado tarde puede tener poco valor operacional.
Y aparece una oportunidad muy buena para nuestro software
HERA fundamentalmente responde a:
¿Qué está ocurriendo en el entorno radiológico?
Nuestro sistema podría añadir:
¿Qué significa para ESTE astronauta?
Porque no todos parten necesariamente del mismo contexto:
Current radiation
Accumulated mission dose
Lifetime exposure
Personal biological response
Current health state
Mission duration remaining
↓
PERSONAL RADIATION RISK
↓
Recommended action
NASA señala precisamente que el objetivo es limitar el riesgo derivado de la exposición acumulada durante la vida del astronauta, y que determinados efectos preocupan especialmente a largo plazo, no necesariamente durante la misión o inmediatamente después del regreso. 
Esto conecta extraordinariamente bien con tu idea anterior de seguimiento post-vuelo.
Por tanto, necesitamos tres escalas temporales
Creo que esto es importante para el Digital Twin:
ACUTE
Minutos → horas.
Evento solar → HERA → shelter.
MISSION
Días → meses/años.
Dosis acumulada + fisiología + cambios biológicos.
LIFETIME
Años → décadas.
Historial de misiones + exposición acumulada + vigilancia médica posterior.
Nuestro modelo longitudinal ya no debería ser simplemente:
Pre-flight → Flight → Post-flight
sino:
Career baseline → Mission 1 → Recovery → Mission 2 → Recovery → ... → Long-term surveillance
Ahí LSAH (Lifetime Surveillance of Astronaut Health) que encontramos anteriormente adquiere todavía más sentido.
ISS → Luna → Marte vuelve a cambiar radicalmente
En la ISS, la magnetosfera terrestre proporciona una protección considerable frente al entorno de espacio profundo.
En Orion/Luna, abandonamos buena parte de esa protección y necesitamos detección, procedimientos y refugio.
En Marte, añadimos además una misión mucho más larga y exposición acumulada mucho mayor.
Por eso Radiation puede ser uno de nuestros mejores casos de demostración:
ISS
Monitorización radiológica + protección magnetosférica + apoyo inmediato de Tierra.
↓
MOON / ORION
HERA + alerta + procedimiento de refugio.
↓
MARS
Detección + predicción + exposición acumulada + contexto de misión + respuesta biológica individual + autonomía decisional.
Y eso nos permite formular una evolución muy clara:
HERA tells the crew when radiation is dangerous. Our system could help determine what that exposure means for each crew member over time.
No como sustitución de HERA, sino como capa de inteligencia sobre los sistemas existentes.
Y anotaría dos personas en nuestro mapa
El artículo identifica a Kerry Lee, entonces radiation system manager for Orion, y a Jessica Vos, entonces deputy health and medical technical authority for Orion. 
Esto responde también a lo que pedías de localizar investigadores, ingenieros y responsables de los problemas reales. Deberíamos empezar a registrar esos nombres junto con institución, especialidad, publicaciones/proyectos relacionados y tecnología.
De hecho, veo cada vez más claro que nuestro recopilatorio debería tener también una pestaña de People & Organizations.
Y Radiation puede ser el primer caso completo que reconstruyamos de extremo a extremo:
RIDGE Hazard → NASA research → sensor → hardware → astronaut → procedimiento → dato → efecto biológico → seguimiento post-vuelo → gap Luna/Marte → oportunidad software.
Si conseguimos hacer esto para los cinco elementos de RIDGE, probablemente el propio análisis nos dirá qué merece la pena construir para Space Apps, en vez de tener que inventarlo.
Interesante porque explica algunos métodos de protección contra la radiación
Exacto. Y yo lo conservaría no sólo como fuente sobre riesgo radiológico, sino específicamente como referencia sobre contramedidas y protección.
Lo interesante es que muestra que la respuesta a la radiación no es una única tecnología, sino un sistema: medir la radiación → detectar el evento → alertar → reducir exposición → utilizar blindaje/refugio → controlar dosis acumulada → seguimiento sanitario posterior.
Para nuestro análisis deberíamos empezar a separar las medidas de protección en varias familias: blindaje estructural, uso de masa ya disponible —agua, alimentos, suministros— como protección adicional, refugios temporales dentro de la nave, dosimetría y sensores como HERA, procedimientos operacionales para reducir exposición y, finalmente, contramedidas médicas/biológicas y vigilancia longitudinal.
Esto además introduce una idea que me parece importante para el software: no limitarse a decir “radiation risk: high”, sino conocer las contramedidas disponibles en ese vehículo o hábitat.
Por ejemplo:
Solar Particle Event detected
→ ¿Dónde está la tripulación?→ ¿Qué zonas ofrecen mayor protección?→ ¿Qué materiales/recursos hay disponibles?→ ¿Cuánto tarda en alcanzarse/configurarse el refugio?→ ¿Cuál es la dosis actual de cada astronauta?→ ¿Cuál sería la dosis prevista permaneciendo donde está?→ ¿Cuánto se reduciría cambiando de ubicación?→ ¿Durante cuánto tiempo debería permanecer protegido?
Así, el sistema evoluciona de Health Monitoring a algo más interesante:
Health Monitoring + Exposure Management + Countermeasure Decision Support.
Y esto deberíamos generalizar a los demás riesgos. Para cada problema que encontremos, registrar no sólo qué daño produce, sino también cómo se previene, cómo se detecta, qué contramedidas existen y cuáles son sus limitaciones en ISS → Luna → Marte.
Voy a incorporar por tanto una columna específica de “Countermeasures / Protection Methods” al mapa que estamos construyendo. Eso puede ser fundamental para pasar de detectar problemas a ayudar al astronauta a actuar, que es precisamente una parte central del challenge.
Evaluador Electrónico Híbrido de Radiación (HERA, por sus siglas en inglés),
Sí: Hybrid Electronic Radiation Assessor (HERA), que podemos traducir como Evaluador Electrónico Híbrido de Radiación.
Lo marcaría expresamente en nuestro inventario de equipos/sensores existentes, porque es justo el tipo de hardware con el que nuestro software debería integrarse, no competir.
La función de HERA en Orion es especialmente relevante: proporciona mediciones de radiación y puede alertar a la tripulación ante niveles elevados, permitiendo activar los procedimientos de protección. NASA lo utiliza dentro de la estrategia para gestionar el riesgo radiológico de las misiones Artemis.
Para nuestro mapa:
HERA→ Tipo: dosímetro / monitor de radiación→ Vehículo: Orion→ Riesgo RIDGE: Radiation→ Input: entorno radiológico→ Output: medición/detección de exposición→ Función operacional: alerta→ Contramedida asociada: desplazamiento/configuración del área de mayor protección→ Evolución que nos interesa: convertir el dato ambiental en riesgo sanitario individual y acumulativo
La distinción puede acabar siendo fundamental:
HERA mide el peligro.Nuestro sistema intenta interpretar qué significa ese peligro para la persona.
Por eso quiero que cuando construyamos el inventario registremos equipos como HERA, dosímetros personales, wearables, ultrasonidos, dispositivos de ejercicio, analizadores de sangre, equipos de visión, sensores ambientales, etc.
Después podremos dibujar literalmente el ecosistema de datos del astronauta y ver qué información ya existe pero permanece fragmentada entre distintos sistemas.
Ese posible problema de fragmentación de datos empieza a parecerme una línea que merece mucha atención.
Diferentes tipos de radiación Fuera protección magnetosfera terrestre
Sí. Esto merece convertirse en un submódulo propio del proyecto, porque al salir de la magnetosfera cambia de forma importante el problema sanitario.
NASA distingue tres grandes fuentes de radiación espacial ionizante: partículas atrapadas por campos magnéticos planetarios —en la Tierra, principalmente los cinturones de Van Allen—, partículas energéticas solares (SEP/SPE) y rayos cósmicos galácticos (GCR). 
La comparación ISS → Luna → Marte es especialmente interesante:
| Radiación | ISS / LEO | Fuera de magnetosfera | Problema |
| Trapped radiation | Relevante; cinturones/partículas atrapadas | Deja de ser la fuente terrestre dominante tras alejarse | Especialmente importante al atravesar regiones como Van Allen |
| SEP/SPE solar | La magnetosfera aporta protección importante | Mayor exposición | Episódica, puede aumentar rápidamente y requiere respuesta operacional |
| GCR | Exposición existente pero parcialmente modulada por protección geomagnética | Exposición continua | Muy energéticos y especialmente difíciles de blindar |
| Radiación secundaria | Existe | Muy relevante para diseño de blindaje | La interacción de partículas primarias con nave/blindaje puede generar neutrones, protones y otras partículas secundarias |
NASA señala que la ISS permanece dentro de la protección relativa del campo magnético terrestre, aunque sus astronautas reciben dosis muy superiores a las terrestres. Orion, al atravesar los cinturones de Van Allen y abandonar esa protección, entra en un entorno radiológico más severo. 
Dos problemas radiológicos muy diferentes
Esto es importante para nuestro software.
Los Solar Particle Events son relativamente repentinos. Están asociados a actividad solar y pueden producir flujos intensos, principalmente de protones. Para ellos tiene sentido:
detectar → predecir exposición → alertar → buscar refugio → monitorizar dosis → decidir cuándo salir.
Aquí encaja muy bien HERA y el sistema de refugio de Orion que acabamos de estudiar.
Los GCR, en cambio, son una especie de problema crónico de fondo. Proceden de fuera del sistema solar —muchos asociados a fenómenos como supernovas— e incluyen protones y núcleos pesados de altísima energía. Son extremadamente penetrantes. 
Y aquí aparece una complicación fascinante: más blindaje no significa necesariamente proporcionalmente más protección.
Cuando una partícula GCR de enorme energía atraviesa determinados materiales puede producir interacciones nucleares y generar radiación secundaria. NASA explica precisamente que materiales pesados pueden aumentar este problema; por ello se estudian materiales de bajo número atómico, incluyendo agua y polietileno. 
Esto explica mejor por qué tiene sentido utilizar agua, alimentos y otros suministros alrededor de zonas protegidas de la nave.
Y hay otra variable que debemos incorporar: ciclo solar
Los GCR y la actividad solar no se comportan igual.
NASA señala que el flujo de GCR observado cerca de la Tierra varía con el ciclo solar: aproximadamente aumenta durante el mínimo solar y disminuye durante el máximo solar. 
Esto significa que el riesgo del astronauta depende también de:
cuándo viaja + dónde está + cuánto tiempo permanece + qué blindaje tiene + qué actividad solar existe + qué dosis lleva acumulada.
Esto empieza a parecer un problema perfecto para nuestro sistema.
Radiation Digital Twin
Podríamos imaginar dentro del Health Digital Twin un módulo específico:
SPACE ENVIRONMENT
GCR + SEP + posición + actividad solar
↓
SPACECRAFT
trayectoria + orientación + materiales + distribución de masa + refugio
↓
PERSON
ubicación dentro de la nave + dosímetro/HERA + historial de exposición
↓
BIOLOGY
dosis acumulada + parámetros biológicos/fisiológicos + susceptibilidad/modelos NASA
↓
RISK
Acute / Mission / Career
↓
COUNTERMEASURE
dónde refugiarse · cuánto tiempo · qué monitorizar · cuándo reevaluar.
Y ya existe incluso una herramienta NASA que debemos investigar: NAIRAS 3.0, actualizada en septiembre de 2026. El modelo predice exposición radiológica biológicamente peligrosa procedente de GCR, protones atrapados y SEP, transportando la radiación a través de heliosfera, magnetosfera, atmósfera y blindaje de vehículos. 
NAIRAS + HERA + dosimetría personal + modelo de la nave + Health Digital Twin podría ser una sinergia muchísimo más interesante que intentar crear nosotros un predictor radiológico desde cero.
Y anotaría una conclusión provisional importante para el análisis ISS → Luna → Marte:
La ISS permite estudiar los efectos de la radiación espacial, pero no reproduce completamente el entorno radiológico de una misión interplanetaria porque permanece bajo la protección relativa de la magnetosfera terrestre.
NASA dice precisamente que su Space Radiation Element busca mitigar los efectos sobre astronautas fuera de esa protección relativa. 
Esto convierte la radiación en un ejemplo perfecto de por qué ISS es banco de pruebas, pero no réplica completa de Marte.
Y además nos da tres variables nuevas para nuestro recopilatorio: tipo de radiación, protección geomagnética y radiación secundaria. Las añadiría a la matriz junto con dosis, tiempo de exposición, blindaje y contramedidas.
https://www.bnl.gov/nsrl/about.php
Este enlace es muy valioso porque NSRL — NASA Space Radiation Laboratory, en Brookhaven National Laboratory— es el banco de pruebas terrestre del problema radiológico que acabamos de identificar.
NASA y el Department of Energy crearon NSRL precisamente porque la ISS no reproduce plenamente el entorno radiológico de una misión de espacio profundo. Allí utilizan aceleradores para producir haces de protones e iones pesados con características semejantes a componentes de los rayos cósmicos y estudiar sus efectos en células, tejidos, ADN, materiales, detectores y electrónica. 
Lo incorporaría a nuestro mapa de «bancos de pruebas»
Estamos empezando a encontrar distintos lugares donde NASA puede estudiar partes del problema:
ISS→ ser humano real + microgravedad + entorno espacial→ pero dentro de la protección relativa de la magnetosfera.
NSRL→ radiación de espacio profundo simulada y controlable→ pero en Tierra, sin el conjunto de condiciones del vuelo.
Artemis / Orion / Luna→ personas + radiación fuera de LEO + condiciones operacionales reales→ misiones todavía relativamente próximas a Tierra.
Marte→ combinación extrema: duración + radiación + microgravedad/gravedad parcial + aislamiento + autonomía.
Esto es importante porque ningún banco de pruebas reproduce Marte completamente. Nuestra evidencia tendrá que integrar información procedente de varios.
NSRL puede simular diferentes componentes
La instalación puede producir haces desde protones hasta iones muy pesados, con energías aproximadamente entre 50 y 1.500 MeV dependiendo de la especie. Dispone de una línea de transporte de unos 100 metros que lleva el haz hasta una sala experimental blindada y laboratorios de apoyo para experimentos biológicos y de materiales. 
Además, su sistema permite cambiar rápidamente las especies de iones para aproximarse mejor a la mezcla compleja de partículas de los Galactic Cosmic Rays (GCR). 
Esto corrige además una posible simplificación de nuestro modelo: no podemos representar «radiación» únicamente como:
Dosis = X mGy
Porque importa también:
tipo de partícula + energía + LET + dosis + tasa de dosis + secuencia temporal + tejido expuesto + blindaje.
Dos exposiciones con una dosis absorbida similar pueden tener consecuencias biológicas distintas.
Y NSRL estudia precisamente lo que queremos conocer
Entre los objetivos están determinar efectos sobre los sistemas biológicos, establecer relaciones dosis-respuesta y reducir las incertidumbres sobre riesgos como cáncer, efectos sobre el sistema nervioso central y enfermedades degenerativas, además de estudiar contramedidas. 
NASA utiliza además resultados de experimentos como estos para desarrollar y validar modelos computacionales de riesgo radiológico. En Johnson Space Center combinan experimentos celulares y animales, transcriptómica de tripulantes de la ISS y modelos para proyectar riesgos como cáncer y síndrome agudo por radiación. 
Esto tiene una relación directa con nuestro proyecto:
NSRL experimental data
↓
NASA radiation risk models
↓
Mission environment
↓
HERA / personal dosimetry
↓
Individual astronaut history
↓
Health Decision Support
No deberíamos intentar reinventar las tres primeras capas.
Y encontramos también contramedidas
Brookhaven señala que la investigación está evolucionando desde risk assessment hacia countermeasure development.
Una vía es el blindaje.
Pero también están investigando contramedidas farmacológicas destinadas a favorecer la reparación del ADN o potenciar mecanismos naturales de protección frente al daño radiológico. 
Esto amplía nuestro inventario:
Contramedidas físicas→ materiales, agua, polietileno, distribución de masa, refugios.
Contramedidas operacionales→ alerta, desplazamiento, reducción del tiempo de exposición.
Contramedidas biológicas/farmacológicas→ protección/reparación celular.
Vigilancia médica→ detectar consecuencias tempranas y longitudinales.
Nuestro software podría conocer las cuatro categorías sin tener que inventar ninguna.
Proveedores, investigadores y centros
Aquí también empezamos a construir el ecosistema que querías identificar.
NASA Human Research Program / Space Radiation Element
↕
DOE Office of Science
↕
Brookhaven National Laboratory
↕
universidades + laboratorios nacionales + investigadores internacionales.
Brookhaven indica que NSRL ha recibido investigadores de más de 50 institutos y universidades de EE. UU., Europa y Japón. 
Y NASA identifica además otro centro terrestre utilizado por su Space Radiation Element: Loma Linda University Proton Treatment Center. 
Aquí merece la pena seguir tirando del hilo de quién investiga qué, porque probablemente encontraremos grupos especializados en cáncer, SNC, cardiovascular, inmunidad, blindajes, farmacología, dosimetría y modelos predictivos.
Hay incluso una conexión directa con OSDR
NASA está desarrollando alrededor de NSRL una colección de biospecímenes y tejidos para mejorar su recopilación, trazabilidad, acceso, distribución y reutilización científica. 
Esto refuerza nuestra idea de conectar:
experimento → muestra → medición → dataset → modelo → aplicación operacional.
Y de este enlace sacaría una conclusión importante para nuestro Space Apps:
el problema no es obtener un número de radiación.
NASA ya tiene HERA, dosímetros, modelos, NSRL, especialistas y décadas de investigación.
El problema potencialmente interesante para nosotros es integrar esas capas para responder en tiempo real:
¿Qué significa el entorno radiológico actual para este astronauta concreto, teniendo en cuenta dónde está, cuánto lleva expuesto, qué exposición acumulada tiene, cuál es su estado biológico y qué contramedidas tiene disponibles?
Ahí el Digital Twin empieza a tener una justificación mucho más concreta.
Y NSRL nos añade una categoría nueva que conservaría en nuestro recopilatorio: Ground Analogs / Testbeds. Deberíamos localizar todos los demás —radiación, aislamiento, gravedad, medicina, hábitats, Luna/Marte— porque compararlos con ISS y Artemis puede mostrarnos exactamente qué aspectos de una misión marciana todavía no podemos ensayar conjuntamente.
https://www.nasa.gov/humans-in-space/step-1-earth-analogs-help-advance-missions-to-moon-mars/
Este enlace es fundamental para ordenar el método de investigación. NASA confirma que no existe un único lugar capaz de reproducir todas las condiciones de Marte: utiliza diferentes análogos terrestres para aislar y estudiar problemas concretos, después ISS y finalmente Artemis. 
Para nuestro proyecto, esto significa que debemos construir un mapa de bancos de pruebas, no estudiar solamente la ISS.
Los análogos que más nos interesan
HERA — Human Exploration Research Analog es especialmente relevante para nuestro challenge. NASA lo utiliza en Johnson Space Center para estudiar aislamiento, distancia de la Tierra, comportamiento, comunicación, capacidades médicas, utilización de equipos y autonomía de la tripulación. Puede introducir retrasos de comunicación para obligar a la tripulación a resolver situaciones sin ayuda inmediata de Mission Control. 
Esto lo convierte en un entorno excelente para nuestra pregunta:
¿Qué información y qué apoyo necesita una tripulación para gestionar autónomamente un problema médico?
:envihab, del DLR en Colonia, estudia otros aspectos. Mediante head-down bed rest durante uno o dos meses reproduce determinados efectos fisiológicos de la microgravedad. También permite investigar CO₂ elevado y gravedad artificial mediante centrifugación. 
Aquí podemos estudiar:
CardiovascularMuscleBoneFluid shiftsCO₂Artificial gravity
y, sobre todo, obtener mediciones antes/durante/después en condiciones mucho más controladas que un vuelo espacial.
Antártida proporciona otro laboratorio completamente diferente: aislamiento prolongado, confinamiento, ambiente extremo, relaciones sociales, trabajo en equipo y cognición. 
Y NSRL, que acabamos de analizar, cubre la pieza que ISS no puede reproducir adecuadamente: componentes del entorno radiológico de espacio profundo mediante haces de iones sobre muestras biológicas y equipos. 
NASA mantiene además un catálogo mucho más amplio: cámaras de altitud, ARGOS, CHAPEA, HERA, :envihab, Kraken, Neutral Buoyancy Laboratory, NSRL, vuelos parabólicos, ISRU y otros. 
Y hay una novedad de 2026 muy interesante
NASA está desarrollando el Moon and Mars Exploration Analog (MMEA).
A diferencia de estudiar factores por separado, este nuevo análogo pretende combinar múltiples partes de una misión lunar o marciana en una campaña integrada de un año. NASA anunció en julio de 2026 que la primera misión está prevista no antes de agosto de 2027 en Johnson Space Center. 
Esto lo marcaría con una estrella en nuestro mapa.
Porque uno de nuestros problemas es precisamente:
Tenemos mucha evidencia de factores aislados. ¿Qué ocurre cuando empiezan a interactuar?
Radiación + sueño + confinamiento + carga de trabajo + nutrición + ejercicio + estrés + ambiente + fisiología.
Ese carácter multifactorial puede ser precisamente uno de los argumentos del Digital Twin.
El mapa de bancos de pruebas empieza a quedar muy claro
| Banco de pruebas | Qué podemos estudiar especialmente |
| Laboratorios terrestres | biología, medicina, tecnología |
| NSRL | radiación |
| :envihab | microgravedad simulada, CO₂, gravedad artificial |
| HERA | autonomía, aislamiento, comunicación, medicina |
| Antártida | aislamiento prolongado, comportamiento, equipos |
| CHAPEA/MMEA | misión integrada Luna/Marte |
| ISS | humano real + microgravedad real + larga duración |
| Artemis/Orion | espacio profundo + radiación + operaciones lunares |
| Luna | gravedad parcial + superficie + autonomía creciente |
| Marte | combinación final de riesgos |
Y esto permite entender algo importante: cada entorno elimina variables que otro sí contiene.
También nos ayuda a definir qué significa «validado»
Imaginemos que nuestro sistema detecta riesgo cardiovascular.
Podemos encontrar evidencia procedente de:
:envihab → fisiología controlada.
ISS → respuesta real en microgravedad.
Twins Study / OSDR → cambios biológicos.
Post-flight → recuperación.
Y después probar el software en:
HERA / CHAPEA / MMEA → ¿puede una tripulación utilizarlo autónomamente?
Es decir:
Scientific validation ≠ Operational validation.
Necesitamos ambas.
Esto es muy relevante para nuestro proyecto.
Y añadiría ahora una pestaña específica al recopilatorio que estamos construyendo:
TESTBEDS & ANALOGS
con columnas:
Instalación | País | Organismo | Riesgo RIDGE | Condición simulada | Duración | Nº participantes | Parámetros medidos | Equipos | Investigadores | Datos disponibles | Proveedores | Experimentos | Limitaciones | Aplicación ISS | Aplicación Luna | Aplicación Marte | Oportunidad para nuestro sistema
Porque empieza a aparecer algo que puede ser bastante potente en el pitch:
EARTH → ISS → MOON → MARS
No son cuatro destinos independientes.
Son una escalera progresiva de validación que NASA utiliza precisamente para reducir riesgos antes de mandar seres humanos más lejos. NASA describe oficialmente esa estrategia como Three Steps to Mars. 
Y nuestro software podría diseñarse siguiendo exactamente la misma filosofía.
Primero aprende de datos históricos y análogos terrestres.
Después se valida con ISS.
Después se adapta al contexto de Artemis/Luna.
Y su objetivo final es proporcionar autonomía sanitaria para Marte.
Además, NASA acaba de hacer explícito algo muy cercano a lo que estamos buscando: los análogos se utilizan, entre otras cosas, para aprender a diagnosticar y tratar problemas médicos y trabajar autónomamente cuando la ayuda de Tierra deja de ser inmediata. 
Ese punto merece que lo sigamos muy de cerca.
Misiones análogas, considerar variables
Sí. Lo incorporaría como una regla metodológica del proyecto: las misiones análogas no son sólo antecedentes o ejemplos; son una fuente de variables, datos longitudinales y escenarios de validación.
En nuestro futuro modelo, cada dato debería llevar asociado su contexto experimental. No podemos mezclar sin más un dato obtenido en ISS, bed rest, HERA, Antártida o una misión real. Cada entorno reproduce unas condiciones y deja fuera otras.
Para las misiones análogas registraría, como mínimo, estas familias de variables:
Misión: duración, fase, objetivo, tamaño y composición de tripulación, carga de trabajo, turnos y eventos críticos. 
Aislamiento: días de confinamiento, espacio disponible, privacidad, interacción social y monotonía. 
Comunicación: latencia con Tierra, ventanas de comunicación, pérdida de comunicaciones y autonomía exigida. 
Ambiente: CO₂, O₂, presión, temperatura, humedad, ruido, iluminación, ciclo día/noche y calidad del aire. 
Gravedad/movilidad: 1g, bed rest, microgravedad, gravedad parcial simulada, actividad y restricciones de movimiento. 
Radiación: real, simulada o inexistente; tipo de partículas, dosis, tasa y exposición acumulada. 
Fisiología: HR/HRV, presión arterial, sueño, actividad, ejercicio, masa/composición corporal, músculo, hueso, equilibrio, etc. 
Biología: sangre, saliva, orina, inmunidad, inflamación, microbioma, metabolómica, transcriptómica y otros biomarcadores. 
Cognición/comportamiento: atención, tiempo de reacción, memoria, rendimiento, fatiga, estrés, estado de ánimo y dinámica de equipo. 
Nutrición: ingesta, hidratación, composición de dieta, horarios y cambios metabólicos. 
Medicina: síntomas, eventos médicos, medicación, pruebas realizadas, tiempo hasta diagnóstico, intervención y resultado. 
Operación sanitaria: equipo disponible, consumibles, tiempo de tripulación, formación necesaria, asistencia desde Tierra y decisiones autónomas. 
Contramedidas: ejercicio, sueño, nutrición, gravedad artificial, protección radiológica, tratamientos y otras intervenciones. 
Temporalidad: baseline pre-misión → evolución durante la misión → incidente/intervención → recuperación → seguimiento post-misión. 
Y añadiría algo especialmente importante para nuestro Digital Twin: variables de interacción.
No queremos estudiar solamente:
CO₂ → salud
o
sueño → salud.
Queremos acabar entendiendo combinaciones como:
CO₂ ↑ + sueño ↓ + carga de trabajo ↑ + aislamiento prolongado
→ HRV ↓ + rendimiento cognitivo ↓
→ riesgo operacional creciente.
Ese carácter multivariable y longitudinal puede ser uno de los puntos fuertes del proyecto.
También conservaría una variable que hemos ido descubriendo y que suele olvidarse:
“¿Esta variable puede medirse realmente durante una misión a Marte?”
Porque podemos disponer de un biomarcador excelente en un estudio terrestre que requiera un laboratorio de 500 kg. Científicamente será valioso para construir el modelo, pero no necesariamente como input operacional.
Así tendremos dos categorías:
Variables de conocimiento → sirven para comprender/entrenar/validar.
Variables operacionales → pueden medirse realmente durante la misión y alimentar el sistema.
Y una tercera que me parece aún más interesante:
Variables inferibles → no podemos medirlas continuamente, pero quizá podamos estimarlas a partir de variables más fáciles de obtener.
Ahí puede existir una oportunidad importante para IA: inferir estados fisiológicos complejos utilizando un conjunto pequeño de señales no invasivas y de bajo coste operacional.
Lo dejaría anotado como una de las hipótesis principales que deberíamos comprobar cuando empecemos a cruzar datasets de análogos + ISS + OSDR + estudios post-vuelo.
https://ntrs.nasa.gov/citations/20200000567
Este documento es especialmente importante. Aquí NASA formula de manera explícita, ya en 2020, varios de los problemas que nosotros hemos ido deduciendo a partir de las otras fuentes. Es el proyecto Medical Data Architecture (MDA) dentro de Exploration Medical Capability (ExMC). 
Y aparecen dos gaps oficiales que debemos guardar literalmente como referencia conceptual:
ExMC Gap Med 07: NASA no disponía de capacidad para procesar de manera integral toda la información médicamente relevante necesaria para apoyar operaciones médicas durante misiones de exploración.
ExMC Gap Med 10: NASA no disponía de capacidad para proporcionar apoyo computacional a la decisión médica durante esas misiones. 
Eso es prácticamente el problema que estamos intentando abordar.
Lo más importante: NASA no habla sólo de monitorización
MDA plantea una evolución:
Medical Data Management
→ Processing
→ Information Discovery
→ Clinical Decision Support
→ Real-time Guidance
→ Autonomous Medical Care
NASA señala expresamente que las misiones de larga duración necesitan un sistema médico capaz de funcionar tanto con asistencia terrestre como sin ella. 
Por tanto, nuestra intuición de:
Monitor → Understand → Predict → Explain → Recommend → Act
tiene bastante respaldo.
Y NASA enumera exactamente varios de los problemas técnicos
Para desarrollar el siguiente nivel de Clinical Decision Support, el documento identifica cuestiones como:
interoperabilidad, monitorización de salud y rendimiento, adquisición y procesamiento de información procedente de biosensores, gestión de datos y conocimiento, integración y fusión de datos, algoritmos avanzados, predicción de eventos médicos y tratamiento basado en información médicamente relevante y evidencia clínica. 
Esto es tremendamente útil porque podemos empezar a distinguir entre problemas que imaginamos nosotros y gaps documentados por NASA.
Y uno me llama especialmente la atención:
Data integration and fusion.
Llevamos varios enlaces sospechando precisamente que los datos del astronauta están repartidos entre equipos, experimentos, sensores, sistemas ambientales y análisis posteriores.
Ahora tenemos una referencia NASA que identifica integración y fusión como problema técnico del CDSS para exploración. 
Level of Care IV → Level of Care V
El documento además habla de niveles de capacidad médica.
La arquitectura MDA había trabajado en requisitos de Level of Care IV, mediante prototipos y demostraciones en bancos de pruebas y análogos.
La siguiente evolución propuesta era desarrollar una hoja de ruta para Level of Care V, orientada hacia mayor capacidad autónoma de decisión clínica. 
Esto merece investigación específica: quiero averiguar qué significa exactamente cada Level of Care, qué capacidades exige el V y cuál es el estado en 2026.
Porque nuestro proyecto podría alinearse explícitamente con esa progresión.
Y aparecen personas y organizaciones
Añadiría a nuestra futura base People & Organizations:
M. Krihak — Universities Space Research Association (USRA)B. Burian — NASA Ames Research CenterB. Schmitt — Wyle LaboratoriesS. Shetye — NASA AmesT. Shaw — NASA Ames. 
El trabajo se presentó en el Human Research Program Investigators' Workshop 2020 y procede de Ames Research Center. 
Eso también nos señala otro repositorio que merece explotar sistemáticamente: los HRP Investigators' Workshops. Ahí probablemente encontremos la evolución año por año de muchos de estos proyectos.
Esto modifica ligeramente nuestra pregunta de investigación
Hasta ahora estábamos preguntándonos:
¿Qué datos necesita nuestro Health Digital Twin?
Ahora añadiría una pregunta anterior:
¿Qué arquitectura está construyendo NASA ya para resolver este problema y qué sigue sin estar resuelto en 2026?
Porque sería un error construir desde cero una versión simplificada de MDA.
Nuestra oportunidad puede estar encima de esa arquitectura.
Por ejemplo:
MDA
Medical data infrastructure + interoperability + knowledge
↓
OUR LAYER
Longitudinal personal model
↓
Multimodal fusion
↓
Deviation from personal baseline
↓
Prediction
↓
Explainable risk
↓
Countermeasure selection
↓
Autonomous decision support
Pero primero tenemos que comprobar cuánto de esto NASA ya ha desarrollado desde 2020 hasta 2026.
Y veo una línea de investigación especialmente prometedora
Podemos seguir la genealogía:
ExMC Gap Med 07 / Med 10
→ Medical Data Architecture (MDA)
→ Level of Care V CDSS
→ proyectos posteriores 2021–2026
→ Integrated Medical Model (IMM)
→ estado actual
→ gaps todavía abiertos
→ Space Apps Challenge 2026
Si hacemos esa investigación histórica, podemos llegar al hackathon diciendo algo bastante más sólido que “hemos pensado que los astronautas necesitan IA”.
Podríamos decir:
NASA has spent years building the medical data architecture needed for exploration. We're addressing one of the remaining challenges: turning fragmented longitudinal, environmental and physiological data into actionable, explainable, crew-autonomous health intelligence.
Siempre que la investigación confirme que ése sigue siendo realmente el hueco.
Este documento, por tanto, lo marcaría como FUENTE PRIORITARIA en nuestro recopilatorio. Probablemente sea una de las referencias técnicas más directamente relacionadas con el propio challenge que hemos encontrado hasta ahora.
https://humanresearchroadmap.nasa.gov/Evidence/reports/AFT.pdf
Este informe abre una dimensión que todavía no habíamos incorporado con suficiente profundidad: la alimentación como variable de salud, contramedida y sistema operacional.
Es el Evidence Report: Risk of Performance Decrement and Crew Illness Due to an Inadequate Food System, del Human Research Program. Aunque es de 2016, lo utilizaría como mapa de hipótesis y variables, verificando después qué ha cambiado hasta 2026. 
1. Alimentación no es simplemente «nutrición»
NASA estructura el problema alrededor de cuatro dimensiones:
Safety + Nutrition + Acceptability + Resource Utilization.
Y esto último es crucial: el sistema alimentario compite con los demás sistemas de la nave por masa, volumen, residuos y tiempo de tripulación. 
Para nuestro modelo, por tanto, no basta con registrar:
calorías / proteínas / vitaminas.
Necesitamos pensar en:
qué come + cuánto come + cuándo + preferencias + estabilidad nutricional + almacenamiento + seguridad microbiológica + recursos necesarios + estado fisiológico resultante.
2. La comida puede ser una contramedida
Esta es probablemente la idea más importante para nuestro challenge.
NASA señala que la alimentación es un factor modificable diariamente con potencial para influir en salud y rendimiento, y plantea que el sistema alimentario pueda actuar como contramedida natural, no sólo como suministro calórico. También relaciona dieta, microbioma, metabolismo, fisiología y psicología. 
Esto encaja extraordinariamente bien con nuestro esquema:
MONITOR
detectamos una alteración
↓
INTERPRET
¿qué sistema fisiológico está cambiando?
↓
COUNTERMEASURE
ejercicio / descanso / nutrición / protección / intervención médica
↓
MONITOR
¿está funcionando?
Es decir, nuestro sistema no tendría necesariamente que limitarse a decir:
“Vitamin D risk”
sino eventualmente:
“Nutritional intervention recommended → reevaluate biomarker/physiology in X days.”
Siempre basado en protocolos/evidencia, no haciendo que una IA improvise tratamientos.
3. Marte cambia radicalmente el problema
La ISS dispone de reabastecimiento. Para Marte, NASA contempla alimentos que podrían enviarse por adelantado y tener 3–5 años cuando finalmente sean consumidos. El informe señalaba que buena parte del sistema alimentario existente estaba diseñado para vidas útiles mucho menores y que nutrientes y características de calidad pueden degradarse durante almacenamiento prolongado. 
Además:
ISS: resupply + proximidad Tierra.
Luna: logística más difícil pero todavía relativamente accesible.
Marte: prácticamente sin resupply de emergencia.
Otra diferencia que añadir a nuestra matriz ISS → Luna → Marte.
4. Radiación × alimentación
Hay una interacción especialmente interesante con lo que acabamos de investigar.
NASA señala que los alimentos almacenados más allá de LEO estarán sometidos a un entorno radiológico más severo y que debía investigarse su efecto sobre contenido nutricional y aceptabilidad. 
Por tanto, Radiation no afecta solamente:
Radiation → Astronaut.
También:
Radiation → Food → Nutrition → Astronaut.
Éste es exactamente el tipo de interacción entre sistemas que puede justificar nuestro enfoque multivariable.
5. Microbioma
El documento relaciona alimentación con microbioma y señala cambios observados durante vuelos espaciales en diversidad microbiana, función inmunitaria y producción de citocinas, entre otros fenómenos. 
Podemos añadir entonces una cadena:
Diet
↓
Microbiome
↓
Metabolites
↓
Immune / metabolic / psychological state
↓
Health & performance
Esto conecta directamente con OSDR y con los datos ómicos que habíamos localizado.
6. Acceptability es una variable médica
Esto también me parece importante.
Si una comida es nutricionalmente perfecta pero el astronauta no se la come, el sistema fracasa.
NASA incluye expresamente variedad, elección, entorno de consumo y aceptabilidad sensorial, y señala la importancia psicológica de la alimentación durante aislamiento y confinamiento. 
Así que deberíamos añadir variables que normalmente no aparecerían en un monitor médico:
Food selected
Food rejected
Actual intake
Appetite
Preference
Meal timing
Menu fatigue
Crew satisfaction
Incluso podemos imaginar que el Digital Twin detecte que una deficiencia nutricional prevista no procede de que falte alimento a bordo, sino de un patrón longitudinal de selección del astronauta.
7. Cuatro gaps NASA muy interesantes
El informe identifica cuatro gaps:
Food-01 — cómo procesamiento y almacenamiento afectan al contenido nutricional.
Food-02 — cómo cambia la aceptabilidad por microgravedad, procesamiento, almacenamiento, elección y entorno.
Food-03 — qué tecnologías/métodos permiten proporcionar seguridad + nutrición + aceptabilidad durante exploración de larga duración.
Food-04 — herramientas para equilibrar las necesidades alimentarias de la tripulación con los recursos del vehículo. 
Food-04 me parece particularmente interesante para nosotros, porque introduce optimización multivariable y decisión.
8. Y hay un precedente histórico precioso para nuestro storytelling
El informe recuerda que NASA, el laboratorio del Ejército estadounidense y Pillsbury desarrollaron el enfoque HACCP para conseguir alimentos extremadamente seguros para las misiones espaciales, y posteriormente el sistema se extendió ampliamente a la industria alimentaria. 
Esto conecta casi perfectamente con la carta de Stuhlinger que trajiste al principio:
problema extremo espacial → innovación → aplicación masiva en Tierra.
Es un ejemplo concreto de esa transferencia.
Con este documento añadiría al Digital Twin un módulo que hasta ahora teníamos demasiado simplificado:
NUTRITION & FOOD
Inventory / shelf life
Nutritional composition
Actual intake
Personal preferences
Physiological needs
Exercise
Microbiome / biomarkers
Mission phase
↓
Nutritional status
↓
Personalized countermeasure
↓
Follow-up
Y hay algo todavía más interesante: la alimentación es una de las pocas contramedidas que podemos modificar todos los días sin añadir nuevo hardware.
Eso la convierte potencialmente en una variable muy potente para un sistema que no sólo monitoriza al astronauta, sino que intenta mantenerlo sano.
Yo marcaría este PDF como otra FUENTE PRIORITARIA, junto con MDA. Uno nos explica cómo construir la inteligencia médica; éste empieza a enseñarnos sobre qué variables puede actuar esa inteligencia.
https://www.nasa.gov/humans-in-space/one-small-step-without-ever-leaving-bed/
Sí. Lo incorporo especialmente a misiones análogas / variables fisiológicas / validación longitudinal.
El artículo describe los estudios de head-down tilt bed rest, en los que los participantes permanecen durante periodos prolongados tumbados con una inclinación aproximada de 6° con la cabeza hacia abajo. NASA utiliza este modelo porque reproduce parcialmente varios efectos de la microgravedad, especialmente el desplazamiento de fluidos hacia la parte superior del cuerpo y el desuso musculoesquelético.
Para nuestro proyecto, lo más valioso no es solamente el análogo, sino el diseño experimental:
PRE → EXPOSURE → COUNTERMEASURE → POST → RECOVERY
Es exactamente la estructura longitudinal que queremos encontrar en los datos de astronautas.
Qué variables podemos extraer
Los estudios de bed rest permiten estudiar de forma controlada cambios en:
Cardiovascular → volumen sanguíneo, regulación cardiovascular, ortostatismo.
Muscular → pérdida de masa/fuerza por desuso.
Óseo → pérdida mineral y metabolismo óseo.
Fluid shift → redistribución de líquidos hacia cabeza y tórax.
Ocular/neurológico → relación entre fluid shift y cambios asociados al vuelo espacial.
Metabolismo/nutrición → balance energético y respuesta metabólica.
Ejercicio → eficacia de diferentes contramedidas.
Y podemos medir después cuánto tarda cada sistema en recuperarse al finalizar el análogo.
Esto es especialmente valioso porque, a diferencia de la ISS, en Tierra podemos tener más participantes, instrumentación más completa y mediciones mucho más frecuentes.
Pero no debemos confundir análogo con vuelo espacial
Esto quiero que quede marcado en nuestro futuro dataset.
Un bed-rest study reproduce determinados efectos de descarga mecánica y redistribución de fluidos, pero el participante continúa:
en 1g, sin radiación espacial, respirando una atmósfera terrestre controlada, con acceso inmediato a médicos, sin microgravedad real y sin muchas de las restricciones operacionales de una misión.
Por tanto, cada dataset debería llevar algo como:
Evidence context
Ground controlBed rest analogIsolation analogRadiation analogISSLunarDeep space
Así evitamos que una IA trate todas las observaciones como si procedieran de la misma población y entorno.
Y aquí aparece una oportunidad excelente para IA
Podemos intentar aprender una relación:
variable fácil de medir → estado fisiológico difícil de medir.
Supongamos que durante estos estudios disponemos simultáneamente de:
wearable signals + actividad + sueño + alimentación + ejercicio
y también de pruebas sofisticadas:
DEXA/MRI + sangre + músculo + cardiovascular + laboratorio.
Podemos investigar si las primeras permiten inferir parcialmente las segundas.
Eso sería extremadamente útil para Marte.
En Tierra podemos medir:
A + B + C + D + E + F + G.
En Marte quizá sólo podamos medir:
A + B + C.
Si el modelo aprendido en Tierra y validado posteriormente con datos espaciales puede estimar D/E, habremos reducido:
hardware + masa + consumibles + crew time + dependencia de laboratorio.
Esto conecta directamente con la hipótesis que habíamos apuntado de las variables inferibles.
Y también podemos estudiar contramedidas
El gran valor experimental de estos estudios es poder comparar:
Control
vs.
Bed rest + countermeasure
Por ejemplo, ejercicio u otras intervenciones.
Eso permite que nuestro sistema aprenda no sólo:
«este parámetro empeora».
sino algo mucho más útil:
«ante este patrón fisiológico, esta contramedida produjo esta trayectoria de recuperación en estudios comparables».
Conceptualmente:
Current state
→ Expected trajectory without intervention
vs.
→ Expected trajectory with countermeasure
Eso empieza a acercarnos a un Countermeasure Decision Support System.
Por tanto, añadiría los estudios bed rest a nuestro mapa con una importancia alta:
GROUND ANALOG — PHYSIOLOGICAL DECONDITIONING
y buscaría después los datasets concretos, participantes, duración, parámetros, contramedidas y seguimiento post-estudio.
Porque aquí podemos encontrar algo que necesitamos desesperadamente para IA: muchos más puntos temporales y sujetos que en las misiones espaciales reales.
La estrategia de datos podría terminar siendo:
Ground analogs → volumen y experimentación
ISS → validación en microgravedad real
Artemis → validación fuera de LEO
post-flight → recuperación
=
modelo longitudinal de salud para exploración profunda.
Ese esquema me parece cada vez más prometedor.
https://www.nasa.gov/wp-content/uploads/2021/02/473486main_iss_atcs_overview.pdf?emrc=046ace
Este documento es muy útil porque introduce algo que no deberíamos separar de la salud: la nave es parte del sistema sanitario. Es el Active Thermal Control System (ATCS) de la ISS, encargado de recoger, transportar y expulsar al espacio el calor residual generado por equipos, experimentos y sistemas de la estación. 
Lo que nos interesa para el proyecto
La arquitectura tiene dos mundos claramente diferenciados.
Dentro de los módulos habitables, el IATCS utiliza agua como refrigerante porque es eficiente y segura para el entorno de la tripulación. En Destiny existen circuitos independientes de baja y moderada temperatura, lo que permite separar cargas y aporta redundancia. 
Fuera, el EATCS utiliza amoníaco anhidro. Recibe el calor mediante intercambiadores y lo transporta hasta grandes radiadores, donde finalmente se disipa al espacio. Los dos circuitos externos son independientes: el fallo de uno permite continuar funcionando con capacidad reducida. El sistema permanente fue diseñado para disipar hasta 70 kW, 35 kW por circuito. 
Es una arquitectura interesante:
Crew / Equipment
↓ genera calor
Internal water loops
↓
Heat exchanger
↓
External ammonia loops
↓
Radiators
↓
Space
Pero para nuestro proyecto aparecen varias ideas más profundas.
1. Salud humana + salud de la nave
Hasta ahora nuestro Digital Twin era principalmente:
Astronaut Digital Twin
Creo que necesitamos contemplar también:
Habitat / Vehicle State.
Porque el estado del astronauta depende de ambos.
Por ejemplo:
Cabin temperature ↑
Humidity ↑
CO₂ ↑
Cooling capacity ↓
Workload ↑
↓
Heart rate ↑
Sleep quality ↓
Cognitive performance ↓
Un algoritmo médico que sólo viera la frecuencia cardiaca podría interpretar mal esa situación.
Por eso la arquitectura empieza a ser:
HUMAN DIGITAL TWIN
↕
HABITAT DIGITAL TWIN
↕
MISSION DIGITAL TWIN
Y la IA interpreta conjuntamente los tres.
2. El ATCS nos da un excelente ejemplo de cómo debería diseñarse nuestro software
Hay redundancia, sensores, límites, detección de fallos y respuestas automáticas.
Por ejemplo, el sistema monitoriza presión mediante múltiples sensores y emplea lógica de votación; existen protecciones frente a sobrepresión, baja presión, sobretemperatura y temperaturas demasiado bajas, con diferentes niveles de actuación automática. 
Es prácticamente:
SENSE
→ COMPARE
→ DETECT ANOMALY
→ ISOLATE
→ RESPOND
→ RECOVER
Exactamente la lógica que estamos planteando para salud humana.
Hay incluso un concepto explícito:
FDIR — Failure Detection, Isolation and Recovery. 
Me parece una inspiración muy buena para nuestro software:
Human FDIR
Health anomaly Detection
→ probable cause Isolation
→ Countermeasure
→ Recovery monitoring
No utilizaría necesariamente ese nombre como producto, pero conceptualmente es muy potente.
3. Los datos técnicos de la nave también pueden convertirse en biomarcadores contextuales
El ATCS dispone de sensores de:
temperatura + presión + flujo + cantidad de fluido + estado de bombas + válvulas + funcionamiento del sistema. 
No necesitamos todos esos datos en el Health Digital Twin.
Pero sí debemos preguntarnos:
¿Qué telemetría del vehículo tiene relevancia médica?
Por ejemplo:
TemperatureHumidityCO₂O₂PressureRadiationNoiseLightAir contaminants
y posiblemente determinados estados del ECLSS y otros sistemas.
Así aparece otra categoría para nuestro recopilatorio:
Vehicle telemetry relevant to human health.
4. Luna y Marte cambian el problema de mantenimiento
La ISS dispone de una arquitectura enorme. Sólo determinados componentes descritos aquí pesan cientos de kilos: un Pump Module ronda 354 kg y un Ammonia Tank Assembly alrededor de 508 kg. 
Además, muchos componentes están diseñados como ORU — Orbital Replacement Units, es decir, unidades sustituibles en órbita. 
En Marte la pregunta cambia:
¿Qué ocurre si falla un componente crítico y no llega un repuesto?
Esto introduce otra conexión salud–ingeniería:
Predictive maintenance → crew health.
Una avería del life support o control térmico puede convertirse rápidamente en un problema médico.
Nuestro sistema quizá debería conocer:
Vehicle anomaly → environmental consequence → human-health consequence.
5. Y aparece una interacción muy interesante con nuestro Health Node
Supongamos:
ATCS/ECLSS telemetry
detecta deterioro ambiental.
↓
El sistema sabe qué astronautas están en ese módulo.
↓
Observa simultáneamente:
HR ↑HRV ↓cognitive performance ↓
↓
En lugar de concluir:
“Astronaut physiological anomaly.”
podría decir:
“Crew-wide physiological deviation correlates with habitat environmental change.”
Eso es bastante más inteligente.
Incluso permite diferenciar:
un astronauta cambia → posiblemente individual.
toda la tripulación cambia simultáneamente → buscar primero una causa ambiental/operacional compartida.
Esto es una propiedad muy interesante de tener varios Digital Twins conectados.
Por tanto, añadiría una nueva dimensión al mapa que estamos construyendo:
HUMAN–HABITAT INTERFACE
Life Support
Thermal Control
Atmosphere
Radiation
Lighting
Noise
Food/Water
Exercise systems
Vehicle telemetry
↓
Human physiology / cognition / behavior
Y aquí empieza a aparecer algo que me parece potencialmente diferencial para el challenge:
No construir simplemente un Astronaut Health Monitor.
Construir un sistema capaz de entender:
Astronaut + Habitat + Mission
como un único sistema dinámico.
Porque en una misión de espacio profundo, la salud del astronauta y la salud de su hábitat dejan de ser problemas independientes.
https://www.nasa.gov/wp-content/uploads/2021/02/bodyinspace_revised_forweb-2022-updated.pdf?emrc=6b269c
Este PDF merece convertirse en uno de nuestros documentos marco. Resume RIDGE, pero lo valioso para nuestro trabajo es que baja de cada riesgo a efectos → mediciones → equipos → contramedidas → necesidades futuras. 
Hay varias piezas que debemos incorporar al recopilatorio.
1. Distancia de la Tierra = autonomía médica. NASA señala que una misión a Marte puede tener hasta unos 20 minutos de retardo en cada sentido y, a diferencia de la ISS, debe llevar consigo alimentos, equipos y suministros médicos necesarios. Por eso ya investiga una Medical Data Architecture, herramientas de clinical decision support con IA/ML y asistentes virtuales para ayudar a la tripulación a identificar y responder a problemas sin asistencia inmediata de Tierra. 
Esto confirma que nuestro challenge no debería reducirse a monitorización: medir → interpretar → diagnosticar/apoyar diagnóstico → seleccionar procedimiento → actuar → comprobar evolución.
2. Nos da un inventario inicial de mediciones y equipos reales. Aparecen actigrafía para sueño/luz, test de vigilancia y atención de 10 minutos, ecografía de órganos, ecografía espinal, análisis de laboratorio a bordo, MRI e imagen de alta resolución pre/post-vuelo, autoevaluaciones de fitness, análisis de orina, sangre y saliva, muestreo microbiológico del cuerpo y de la nave y monitorización de contaminantes atmosféricos. 
Esto es exactamente lo que queríamos reconstruir como:
Variable → Sensor/equipo → frecuencia → invasividad → crew time → procesamiento → Tierra/a bordo → dato producido → utilidad clínica.
3. Aparece un gap particularmente interesante entre “lo que sabemos” y “lo que podemos medir durante el vuelo”. Por ejemplo, NASA evalúa deterioro muscular y óseo mediante MRI y técnicas avanzadas de imagen antes y después del vuelo. 
Ésta es una pregunta excelente para nuestro proyecto:
¿Podemos estimar durante el vuelo algo que actualmente conocemos principalmente mediante una prueba compleja pre/post-vuelo?
Ahí entran nuestras variables inferibles.
Podríamos investigar, por ejemplo:
exercise + activity + nutrition + HR/HRV + ultrasound + urine biomarkers + mission duration
→ modelo
→ estimated musculoskeletal deterioration
y contrastarlo después con las mediciones clínicas post-vuelo.
No significa que podamos hacerlo; significa que hemos encontrado una hipótesis investigable.
4. La orina es especialmente interesante. NASA explica que mide producción urinaria y determinadas sustancias para evaluar, entre otras cosas, riesgo de cálculos renales, y que eso permite modificar dieta, ejercicio e hidratación como prevención. 
Aquí tenemos un circuito completo real:
Measurement → Risk → Countermeasure → Follow-up
que es exactamente la lógica que buscamos para el software.
5. El documento confirma nuestro Human–Habitat Twin. En Hostile/Closed Environments, NASA conecta directamente salud con microbiología del hábitat, calidad del aire, formaldehído, amoníaco, CO, temperatura, iluminación, superficies, agua y filtros. También relaciona el entorno con estrés y alteraciones inmunológicas. 
Por tanto, telemetría de la nave es también información médica contextual.
Una matriz que empieza a emerger
| RIDGE | Inputs que encontramos | Estado humano | Contramedida |
| Radiation | detectores, dosis, tipo | exposición/riesgo longitudinal | shielding + procedimientos |
| Isolation | actigrafía, luz, sueño, test cognitivo | fatiga/cognición/estado conductual | iluminación, descanso, actividades, VR |
| Distance | síntomas, laboratorio, ecografía, historial | evento médico | diagnóstico autónomo + CDSS |
| Gravity | fitness, fluidos, ecografía, orina, imagen | cardiovascular, hueso, músculo, visión | ejercicio, LBNP, cuffs, dieta/fármacos |
| Environment | aire, temperatura, microbios, sangre/saliva | inmunidad + bienestar | filtrado, limpieza, tratamiento agua, ambiente |
Y hay una cuestión temporal fundamental: NASA señala que la pérdida de densidad mineral en huesos de carga puede rondar 1–1,5 % al mes en vuelo y que la recuperación posterior puede no restaurarla completamente. Esto refuerza tu interés por post-vuelo y evolución posterior: el Digital Twin no debería terminar cuando aterriza el astronauta.
Empiezo a ver cuatro Digital Twins, no uno
Todo lo que has ido recopilando sugiere una arquitectura algo más sofisticada:
HUMAN TWINfisiología + biología + cognición + nutrición
↕
HABITAT TWINatmósfera + temperatura + radiación + microbiología + life support
↕
MISSION TWINposición + duración + gravedad + workload + comunicaciones + recursos
↕
COUNTERMEASURE TWINejercicio + alimentación + protección + descanso + procedimientos + intervención médica
Y sobre los cuatro:
Autonomous Health Decision Support
La cuarta capa es nueva y me parece importante: no basta con modelizar qué está ocurriendo. Necesitamos conocer qué podemos hacer, con qué recursos, cuándo y cuál ha sido la respuesta del astronauta.
Finalmente, este PDF contiene una frase conceptual importante para nuestra investigación: NASA dice que los riesgos de seis meses en la ISS no son los mismos que los de una misión marciana de varios años. 
Eso justifica todo el análisis comparativo que estamos haciendo de análogos terrestres → ISS → Artemis/Luna → Marte.
Yo marcaría este documento como FUENTE MARCO – PRIORIDAD MÁXIMA, junto al documento de Medical Data Architecture. El MDA nos dice cómo debería circular y convertirse en decisión la información médica; The Human Body in Space nos proporciona un primer mapa bastante completo de qué información necesitamos y para qué.
BeyondTheProtocol/polaris
Este repositorio puede ser relevante como referencia técnica/prototipo de software, pero antes de integrarlo en nuestra arquitectura conviene distinguir qué hace realmente Polaris de lo que nosotros estamos planteando.
Por el contexto del proyecto, lo analizaría con estas preguntas: qué datos ingiere, si trabaja con datos fisiológicos/ambientales reales o simulados, cómo modela al astronauta, qué capacidad de monitorización/predicción tiene, si funciona localmente, qué dependencias externas utiliza, cómo presenta alertas, qué nivel de explicabilidad ofrece y si incorpora contramedidas o sólo visualización.
También lo compararía expresamente con nuestra línea actual:
Polaris / soluciones existentes ↔ Human Twin + Habitat Twin + Mission Twin + Countermeasure Twin + Autonomous Decision Support.
Y, sobre todo, buscaría qué podemos reutilizar legítimamente: arquitectura, componentes, modelos, datasets, interfaz, licencia y código. Si es software abierto relacionado con el mismo challenge, puede ahorrarnos muchísimo tiempo durante Space Apps y permitir que dediquemos el hackathon a la parte verdaderamente diferencial en vez de reconstruir infraestructura básica.
Lo incorporo, por tanto, a una nueva categoría del mapa: Existing Software / Open Source / Prior Art, junto a MDA, IMM y las herramientas NASA que vayamos encontrando.
Esto es como renderizar el hígado que te pase
Sí, entiendo ahora por qué me pasaste Polaris. No tanto como solución médica comparable a la nuestra, sino como referencia para la representación visual del organismo.
La idea sería que el Digital Twin no se limite a dashboards y gráficas, sino que tenga una representación anatómica 3D sobre la que visualizar el estado del astronauta. Por ejemplo, renderizar el hígado —como el ejemplo que mencionas— y superponer sobre él información derivada de datos reales o estimados.
Podríamos llevarlo bastante más lejos:
Astronauta 3D → sistema → órgano → tejido → variable → evolución temporal.
Por ejemplo, seleccionas:
LIVER
y el sistema muestra:
Current stateBaseline deviationRelevant biomarkersRadiation exposureMetabolic/nutritional factorsPredicted trend
y permite desplazarse temporalmente:
Pre-flight → Day 30 → Day 180 → Day 360 → Post-flight → Recovery
Así el Digital Twin deja de ser una metáfora y empieza a tener una manifestación visual.
Además, no todos los órganos tendrían que representar lo mismo. Podríamos visualizar:
Corazón → cardiovascular, HR/HRV, adaptación y recuperación. 
Cerebro → cognición, sueño, aislamiento, radiación/CNS. 
Ojos → fluid shift/SANS. 
Huesos → densidad mineral y riesgo estimado. 
Músculos → pérdida/adaptación y efecto del ejercicio. 
Riñones → hidratación, orina, riesgo de cálculos. 
Sistema inmune/bazo → biomarcadores e información OSDR. 
Hígado → metabolismo, nutrición y biomarcadores asociados. 
Y podríamos representar visualmente incertidumbre. Si el hígado dispone de datos directos, el modelo lo muestra como medición; si estamos estimando su estado mediante otras variables, la interfaz debería decir claramente “estimated”, con nivel de confianza y evidencia utilizada. Eso sería muy importante científicamente.
La idea visual que me parece especialmente potente sería un Astronaut Body Map donde el jurado pueda tocar un órgano y viajar desde la representación anatómica hasta la evidencia:
BODY → ORGAN → HEALTH STATE → DATA → NASA EVIDENCE → TREND → RISK → COUNTERMEASURE.
Y al otro lado podríamos tener el equivalente para la nave:
ASTRONAUT TWIN ↔ HABITAT TWIN
De modo que seleccionar una alteración del astronauta permita ver también qué factores externos pueden estar relacionados: radiación, CO₂, temperatura, ejercicio, alimentación, sueño, etc.
Así que sí: renderizar el hígado es exactamente una de las posibilidades que conservaría de Polaris. No como adorno gráfico, sino como interfaz del Digital Twin para convertir una enorme cantidad de datos biomédicos en algo que un astronauta pueda comprender rápidamente.
https://x.com/israeldfirzt/status/2100980215782473955
Sí, lo añado a las referencias que estamos recopilando, pero X no me permite acceder al contenido de ese post (devuelve acceso bloqueado) y tampoco aparece indexado por el identificador, así que no quiero deducir de qué trata. 
Pásame una captura del post —y, si contiene vídeo, alguna captura del vídeo o una breve descripción— y lo analizo igual que hemos hecho con Polaris: qué idea aporta, qué tecnología utiliza, qué podemos reutilizar y dónde encaja en nuestro mapa del Digital Twin / monitorización de salud / visualización.
Todo esto para contexto del proyecto. Pon como un subapartado. Luego documenta todo para poder alimentar a Claude, para mejorar contexto en codificación y programación. Gracias
Perfecto. Lo considero desde ahora un subapartado específico del proyecto, no como una línea que desplace la investigación principal.
Lo organizaría como «Referencias técnicas y de visualización para el desarrollo», donde entrarán Polaris, el ejemplo de renderizado del hígado, el post de X que acabas de pasar —pendiente de poder ver su contenido—, ZeroKeyUSB y futuras referencias de interfaces, hardware, visualización 3D, Digital Twins, arquitectura local-first, etc.
Y sí: cuando preparemos la documentación consolidada, haré además una versión específicamente pensada para alimentar a Claude como contexto de programación. No será simplemente una transcripción de nuestras conversaciones. La convertiré en una especificación técnica estructurada: objetivo del challenge, investigación NASA, hipótesis, arquitectura Human/Habitat/Mission/Countermeasure Twin, fuentes y datasets, variables, módulos, requisitos funcionales y no funcionales, referencias visuales, tecnologías reutilizables, decisiones ya tomadas, decisiones abiertas, restricciones, MVP y backlog. Así Claude podrá entrar directamente a programar sin tener que reconstruir todo nuestro razonamiento.
Cuando lleguemos a ese punto, también podemos mantener dos documentos separados: Project Knowledge Base para conservar toda la investigación y Coding Context / Technical Specification como contexto compacto para Claude.
Profundiza en todos los enlaces, con los comentarios asociados que van justo en después en algunos casos y cuando tengas hecho eso, prepara un primer documentos de las dos versiones separadas.
He preparado una primera versión separada en dos documentos, profundizando y reorganizando los enlaces que hemos ido aportando y, sobre todo, incorporando los comentarios que hiciste inmediatamente después de algunos de ellos como parte del razonamiento del proyecto.
En esta revisión ya he hecho una corrección importante respecto a nuestras primeras conclusiones: he contrastado el estado actual del Integrated Medical Model (IMM) en 2026 y lo he separado conceptualmente de lo que estamos buscando. NASA lo describe actualmente como una herramienta probabilística pre-misión basada en Monte Carlo e iMED para estimar eventos médicos, impacto operacional y recursos; mientras que MDA/CDSS aborda la arquitectura de datos y la autonomía médica en vuelo. Esto nos ayuda bastante a delimitar un posible hueco sin afirmar prematuramente que NASA no lo cubre.
También he incorporado expresamente tus ideas de “misiones análogas: considerar variables” y “esto es como renderizar el hígado”. La primera se convierte en una regla metodológica para los datasets; la segunda en un subapartado de visualización anatómica/Digital Twin. Además, he revisado Polaris directamente: el repositorio contiene precisamente un ejemplo de generación de un render 3D a partir de PET y una arquitectura con goal, expertos, verificación, human gate y fail-closed que ofrece patrones interesantes para nuestro desarrollo. 
Los dos primeros documentos son:
1. Project Knowledge Base v1 — 13 páginas. Es la versión extensa para nosotros: investigación NASA, RIDGE, MDA/CDSS/IMM, análogos, variables, nutrición, Habitat Twin, radiación, repositorios, instalaciones, arquitectura de cuatro twins, Polaris/renderizado, ZeroKeyUSB, storytelling, hipótesis, MVP y backlog de investigación.
Descargar Project Knowledge Base v1
2. Coding Context / Technical Specification for Claude v1 — 8 páginas. Está deliberadamente escrito de otra manera: convierte nuestra investigación en contexto directamente utilizable por un agente de programación. Incluye product goal, principios no negociables, modelo de dominio, arquitectura, contratos de datos, baseline engine, Human FDIR, biblioteca de contramedidas, escenarios MVP, UX, seguridad, estructura de repositorio y criterios de aceptación.
Descargar Coding Context para Claude v1
He verificado visualmente ambos documentos completos después de generarlos.
Hay además una decisión metodológica importante en esta V1: no he rellenado artificialmente lo que no hemos podido comprobar. Los posts de X quedan registrados pero pendientes de captura/contenido verificable. Y las ideas que todavía son nuestras hipótesis aparecen como hipótesis, separadas de lo que NASA documenta. Eso será especialmente importante cuando Claude empiece a convertir este contexto en código.
Esta es una V1 de consolidación, no considero terminada todavía la fase de profundización. El siguiente salto de calidad será bajar a nivel de datasets concretos —Twins Study, OSD-343, NLSP/LSAH, Research Explorer—, inventariar equipos/variables y seguir la evolución MDA → CDS/CDSS → IMM/MEDPRAT hasta 2026. Ahí podremos convertir la Knowledge Base en una auténtica especificación científica y de producto.
SpaceApps2026_Project_Knowledge_Base_v1.docxDocumentoAbrir archivo
SpaceApps2026_Coding_Context_Claude_v1.docxDocumentoAbrir archivo
hoy 9:13
La palatabilidad es el grado de placer y atractivo que un alimento produce en el sentido del gusto, el olfato y el tacto al comerlo. [1]
¿Qué factores forman la palatabilidad?
Sabor y aroma: El olor y el gusto en la lengua guían las ganas de comer.
Textura y sonido: Lo crujiente o suave de la comida cambia la experiencia en la boca.
Apariencia visual: El color y la forma llaman la atención desde el primer momento. [1]
Alimentos Hiperpalatables
Tienen mezclas altas de grasas, azúcares o sal que estimulan mucho el cerebro.
Ejemplos comunes son la pizza, los pasteles, las patatas fritas y la bollería.
Su consumo frecuente puede llevar a comer de más o descuidar la salud. [1, 2]
Si te interesa, dime:
¿Quieres saber cómo mejorar la palatabilidad de comidas saludables?
¿Buscas información sobre alimentos para mascotas?
Sí. Palatabilidad debe incorporarse como variable del proyecto, y además encaja directamente con el informe NASA sobre el sistema alimentario que acabamos de analizar.
No la trataría sólo como una propiedad del alimento. Para nuestro modelo interesa sobre todo como variable dinámica de comportamiento nutricional:
Palatabilidad percibida → elección del alimento → ingesta real → aporte nutricional real → estado fisiológico → salud/rendimiento.
Esto introduce una distinción importante entre dieta disponible y dieta realmente consumida. Podemos tener a bordo una dieta nutricionalmente perfecta y, sin embargo, que el astronauta reduzca progresivamente su consumo por monotonía, cambios sensoriales, textura, preferencias, estado psicológico o duración de la misión.
Además, para el Digital Twin consideraría variables como aceptabilidad/palatabilidad individual, preferencias, repetición del menú, apetito, porcentaje consumido, alimento rechazado, momento de la ingesta, cambios de preferencia durante la misión y evolución temporal. También deberíamos investigar cómo microgravedad, congestión/fluid shift, aislamiento, almacenamiento prolongado y otros factores del vuelo pueden modificar la percepción y aceptación de los alimentos.
Y aparece una correlación potencialmente interesante:
Mission duration ↑ → menu fatigue / palatability ↓ → actual intake ↓ → nutritional adequacy ↓ → physiological/performance effects
No debemos asumir que esa relación exista o sea lineal: la anotamos como hipótesis para contrastar con datos.
También la añadiría a nuestra futura matriz de correlaciones, porque puede cruzarse con sueño, estado de ánimo, estrés, microbioma, ejercicio, masa corporal, ingesta energética, hidratación, aislamiento y rendimiento cognitivo.
En definitiva, no guardaría simplemente “palatabilidad de los alimentos”. Guardaría el concepto más útil para el algoritmo:
Food acceptability / palatability → actual eating behavior → health outcome.
Lo incorporamos a la Knowledge Base y, cuando proceda, al modelo de datos del Coding Context, porque puede acabar siendo una variable relevante del Human Twin + Countermeasure Twin.
https://www.tiempo.com/noticias/astronomia/el-tiempo-no-se-detiene-en-el-espacio-un-estudio-revela-por-que-estar-en-orbita-acelera-nuestro-reloj-biologico.html?dc_data=49417928_realme-lockscreen-spain&utm_source=taboola&utm_medium=taboola_news
Este enlace es muy relevante y conecta de forma casi perfecta varias líneas que llevamos separadas: radiación + microgravedad + hígado + envejecimiento biológico + Twins Study + Inspiration4 + análogos + correlaciones + contramedidas. He ido al artículo científico original de GeroScience, publicado el 23 de junio de 2026, porque la noticia simplifica algunos aspectos. 
Lo incorporaría a la Knowledge Base como «Spaceflight as accelerated-aging model / Organ-level Digital Twin».
Lo más interesante para nosotros
El experimento utilizó ratones sometidos durante 14 días a hindlimb unloading para simular aspectos de la microgravedad y añadió exposiciones diferenciadas a GCR y SPE. Después analizaron el hígado 24 horas tras la irradiación. Es decir, tenemos justamente el esquema que estamos buscando:
factor ambiental → exposición → órgano → biomarcador molecular → cambio biológico → riesgo → posible contramedida. 
Y confirma algo importante: “radiación” no puede ser una sola variable. GCR y SPE produjeron patrones moleculares distintos; incluso las correlaciones miRNA–mRNA cambiaron dependiendo del tipo de exposición. 
Esto refuerza nuestra futura matriz:
tipo de radiación × dosis × microgravedad × duración × órgano × biomarcador × individuo.
Aquí aparece exactamente el hígado que querías renderizar
Ya no sería simplemente una visualización bonita.
Podríamos tener:
ASTRONAUT → LIVER
y dentro:
Metabolic stateInflammationSenescenceFibrotic signalingTGF-β pathwayRelevant miRNAsRadiation exposureMicrogravity exposureNutrition
con una línea temporal.
Pero deberíamos distinguir visualmente tres niveles:
MEASURED — dato realmente medido en ese astronauta.
INFERRED — estado estimado por el modelo.
RESEARCH EVIDENCE — mecanismo observado en estudios animales/celulares, pero que no podemos afirmar que esté ocurriendo directamente en ese astronauta.
Esta separación puede darle bastante rigor al Digital Twin.
Y el estudio hace algo muy parecido a nuestra estrategia de validación
Después del experimento animal, los investigadores fueron a datos humanos.
Utilizaron el NASA Twins Study —340 días en ISS, con muestras antes, durante y hasta 200 días después— y Inspiration4, con cuatro astronautas y muestras pre-vuelo y a R+1, R+45 y R+82 días. 
Es prácticamente:
GROUND ANALOG
↓
mechanistic hypothesis
↓
REAL SPACEFLIGHT DATA
↓
human translational validation
↓
POST-FLIGHT RECOVERY
Esto respalda muchísimo la metodología que estamos construyendo.
Y atención a la recuperación
Hay un resultado especialmente interesante para nuestro interés por el seguimiento post-vuelo.
En Twins Study, varios genes de la vía TGF-β estaban reducidos hacia la parte final de la misión, pero en gran medida se habían restaurado en la primera medición post-vuelo analizada por los autores. En Inspiration4 también aparecen alteraciones inmediatamente después del vuelo y recuperación posterior de determinadas señales hacia R+82. 
Por tanto, no basta con representar:
NORMAL / ABNORMAL.
Necesitamos:
baseline → deviation → trajectory → recovery rate → new baseline.
Eso puede ser mucho más interesante para un Digital Twin.
Y hay algo todavía más importante: correlaciones
Este artículo hace explícitamente análisis de correlación de Spearman entre miRNAs y mRNAs. Encontraron numerosas correlaciones positivas dentro de cada grupo y relaciones inversas entre determinados miRNA y mRNA, con patrones diferentes bajo GCR+microgravedad frente a SPE+microgravedad. 
Esto conecta directamente con lo que dijiste al comenzar el brainstorming: guardar variables para después buscar correlaciones y posibles algoritmos.
Aquí tenemos un ejemplo real de cómo hacerlo:
Exposure variables
GCR / SPE / microgravity
↓
Molecular variables
miRNA
↔ correlación ↔
mRNA
↓
Pathways
TGF-β / inflammation / senescence / fibrosis
↓
Organ state
Liver
↓
Whole-person health
Y después podemos buscar qué parte de esa cadena puede observarse mediante variables operacionales mucho más fáciles de medir.
Pero cuidado con el titular de la noticia
No lo almacenaría como «el espacio acelera nuestro reloj biológico» en sentido literal.
El artículo científico habla de respuestas moleculares semejantes a procesos asociados al envejecimiento: senescencia, inflamación, fibrosis y determinadas vías regulatorias. No demuestra que un astronauta envejezca globalmente X años por permanecer Y días en el espacio. 
Esa distinción debería quedar en nuestra Knowledge Base.
También aparece una posible contramedida, pero con una advertencia excelente para nuestro software
Probaron antagomirs dirigidos contra determinados miRNA. El tratamiento modificó favorablemente algunas señales relacionadas con senescencia e inflamación, pero también aumentó la expresión de marcadores asociados a fibrosis. 
Esto es magnífico conceptualmente para nuestro Countermeasure Twin:
Una intervención puede mejorar una variable y empeorar otra.
Por tanto, nunca deberíamos modelizar:
Risk → Countermeasure
de manera aislada.
Mejor:
Current multidimensional state
↓
Countermeasure
↓
expected benefits
possible adverse effects
interactions
↓
new predicted multidimensional state
Eso empieza a parecerse bastante más a un verdadero sistema de decisión.
Este estudio, además, une dos ideas tuyas que inicialmente parecían independientes:
«Misiones análogas: considerar variables»
y
«renderizar el hígado».
Ahora podemos visualizar literalmente una arquitectura:
MISSION / ENVIRONMENT
GCR + SPE + microgravity + duration
↓
HUMAN DIGITAL TWIN
↓
ORGAN DIGITAL TWINS
🫀 Heart🧠 Brain🫁 LungLiver🦴 Bone💪 Muscle👁 Eye🫘 Kidney
↓
PATHWAYS / BIOMARKERS
↓
FUNCTIONAL STATE
↓
COUNTERMEASURES
↓
LONGITUDINAL RECOVERY
Y cada capa podría permitir bajar hasta la evidencia NASA/OSDR/publicación que sustenta la relación.
Este artículo lo marcaría como FUENTE PRIORITARIA, porque no sólo aporta conocimiento sobre el hígado: proporciona un ejemplo concreto de cómo podríamos conectar análogos → datos espaciales humanos → correlaciones → órgano → evolución temporal → contramedidas → Digital Twin. 
hoy 10:46
Descargar Coding Context para Claude v1
Por qué desde el apartado 4 lo pones en inglés?
Porque tomé una decisión que no debía haber tomado sin consultarte: a partir del apartado 4 del Coding Context para Claude pasé al inglés pensando que sería más útil como especificación técnica para un modelo de programación, especialmente para nombres de componentes, contratos de datos, arquitectura y criterios de aceptación.
Pero no hay ninguna necesidad de que esté en inglés para que Claude lo entienda o programe correctamente. De hecho, tiene más sentido mantener todo el documento en castellano, conservando en inglés únicamente los términos técnicos cuando sea conveniente (baseline, API, Human-in-the-loop, fail-closed, nombres de clases/campos, etc.).
Además, mezclar idiomas dentro del mismo documento empeora su coherencia. La versión correcta debería ser:
Documento completo en castellano → terminología técnica original en inglés cuando aporte precisión → código, nombres de variables y estructuras en inglés si decidimos que ésa será la convención del repositorio.
Así que sí: lo corregiría en la siguiente versión del Coding Context para Claude y dejaría todo el contenido explicativo en castellano.
Hazlo por favor, coincido con tu respuesta. Tampoco te fustigues. 
Hecho. He preparado la versión 1.1 íntegramente en castellano, manteniendo en inglés únicamente aquello que tiene sentido conservar como terminología técnica, nombres de componentes, campos de datos, código o convenciones del repositorio.
También he traducido las tablas, criterios de aceptación, arquitectura, escenarios MVP, seguridad, decisiones pendientes y comentarios de la estructura del repositorio. He mantenido términos como baseline, Human FDIR, fail-closed, LLM, MEASURED / INFERRED / PREDICTED, etc., cuando aportan precisión, normalmente acompañados de explicación en castellano.
He revisado además el documento renderizado para comprobar maquetación y tablas.
Descargar Coding Context / Especificación Técnica para Claude v1.1 — Castellano
A partir de ahora mantendría esta convención para el proyecto: documentación y razonamiento en castellano; código, schemas, nombres de clases/variables y terminología técnica internacional en inglés cuando sea conveniente.