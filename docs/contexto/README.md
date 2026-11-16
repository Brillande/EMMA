# Contexto de producto — referencia para toda mejora

Estos documentos los preparó el equipo antes y durante el desarrollo (23-24 sep 2026). Son la
referencia contra la que se contrasta cada mejora de EMMA a partir del 2026-09-26.

| Fichero | Qué es | Cómo se usa |
|---|---|---|
| `especificacion-tecnica-v1.1.md` | Especificación técnica para el agente de código (v1.1, en castellano) | **Norma.** Principios, modelo de dominio, escenarios y criterios de aceptación del MVP |
| `knowledge-base-v1.md` | Investigación: RIDGE, MDA/CDSS/IMM, análogos, variables, radiación, nutrición, hipótesis H1-H7 | Por qué se hace cada cosa y qué es hipótesis, no hecho |
| `conversacion-ideacion-v1.md` | Conversación de ideación de la que salen los dos anteriores | Contexto de fondo; si contradice a la especificación, manda la especificación |

La v1 en inglés de la especificación no se copia: la v1.1 la sustituye con el mismo contenido.
Los originales `.docx` están en la carpeta de descargas del autor.

**Precedencia.** Las invariantes de `CLAUDE.md` mandan sobre estos documentos: fueron escritas
tras errores reales y son más estrictas (p. ej. la especificación admite "etiquetas sintéticas
para la demo" y EMMA exige además declararlas en el ledger como `simulator`). Donde la
especificación pide algo que EMMA no tiene, es un hueco a cerrar, no una opción.

## Comparación con EMMA (2026-09-26)

### Criterios de aceptación del MVP (§14)

| Criterio | Estado | Dónde |
|---|---|---|
| Se ejecuta localmente con un comando documentado | Cumple | instalador de escritorio; `uvicorn app.main:app` |
| Reproduce al menos un escenario de misión | Cumple | `ingest/simulator.py` (`Scenario`: SPE, insomnio, arritmia, desacondicionamiento, reactivación inmune) |
| Baseline individual y desviación persistente | Cumple | `analysis/baseline.py`, `analysis/trend.py` |
| Al menos una variable de hábitat/misión en la interpretación | Cumple | radiación, retardo de comunicaciones y, desde el 2026-09-26, atmósfera de cabina con límites de NASA-STD-3001 y correlación entre tripulantes |
| Explica la alerta con variables contribuyentes y fuente | Cumple | `Deviation.describe`, `evidence/links.py` |
| Contramedida/comprobación **estructurada** con **estado de seguimiento** y confirmación humana | Cumple (2026-09-26) | biblioteca `app/data/countermeasures.json` validada al cargar; adopción y cierre firmados (`countermeasure-followup`); estado y evaluación derivados (`advisor/followup.py`) |
| Distingue medido / inferido / predicho | Cumple (2026-09-26; en el motor desde el 2026-10-26) | `observation_type` y `evidence_context` en cada observación y en el ledger; dosis rotulada inferida; proyecciones de tendencia como predichas; insignias en la interfaz (`lib/provenance.ts`). Desde la decimoséptima ronda (§5.37.1 de `compliance/hmi-state-of-the-art.md`) la separación también decide: la línea base, la tendencia y el riesgo solo leen lecturas `measured` (`ANALYSED_TYPES`, `decides` en `api/routes.py`), lo inferido y lo predicho se firma igual y se enseña rotulado y contado como «sin decidir»; `rules_version` pasó de `reglas@faf6e60fc2fd3f12` a `reglas@c89d7ebf4d5f4aa9` con las dos métricas de MMASH idénticas. Una excepción declarada, confirmada por el usuario en la decimoctava ronda: la dosis acumulada medida **o inferida** cuenta para el límite de carrera (`DOSE_TYPES`), la predicha nunca |
| Funciona con la red desactivada | Cumple | tests offline forzados (invariante 3) |
| Pruebas de esquemas, baseline, alerta, evidencia y fail-safe | Cumple | `backend/tests`, mutantes |

### Principios (§2) y seguridad (§12)

| Principio | Estado |
|---|---|
| Local-first / offline-first | Cumple |
| Human-in-the-loop, ninguna acción clínica automática | Cumple (invariante 7; borrador del LLM segregado) |
| Procedencia de la evidencia en toda regla | Cumple: cada contramedida lleva su protocolo o se declara `demo` (solo la respalda el riesgo del dominio) |
| Incertidumbre primero (medido/inferido/predicho + calidad) | Cumple: `confidence` y la triple etiqueta. Desde el 2026-10-07 la confianza de cada lectura se ve en pantalla (`data.quality`); hasta entonces el backend la usaba y la interfaz no la enseñaba |
| Fail-closed y degradación elegante | Cumple (servicios ausentes en gris, "no disponible") |
| No mezclar contextos sin `evidence_context` | Cumple: campo firmado en cada observación; las lecturas reales toman el del despliegue (`EMMA_DEPLOYMENT_CONTEXT`). Desde el 2026-10-07 cada fuente citada lleva además su entorno y su población en el registro único de evidencia, o dice que están sin verificar |
| Datos no son instrucciones (anti-inyección) | Cumple (DATA_GUARD de Polaris en `interpret/draft.py`) |
| Versionado y audit trail de modelos/reglas | Cumple: ledger, y `model_version` obligatorio en lo inferido o predicho (el simulador declara escenario y semilla). Hasta el 2026-10-10 varias reglas que cambian alertas (la persistencia, entre ellas) quedaban fuera de `rules_version`; ahora la huella recorre una lista declarada y una prueba falla si aparece una constante que decide y no está en ella |
| Reglas deterministas sin LLM | Cumple: el núcleo no usa el LLM |

### Modelo de dominio (§3) y escenarios (§9)

| Pieza | Estado |
|---|---|
| Observation | Cumple (2026-09-26). Desde el 2026-10-23 la unidad de §5 también en el alta manual: `POST /api/observations` admite `unit` (UCUM) opcional; distinta de la del catálogo es un 422 sin asiento y sin conversión, y ausente se asume la del catálogo y la respuesta lo dice. La tabla «campo de §5 → elemento FHIR R4 → dónde lo pone EMMA» está en `compliance/record-integrity.md` §3.14 quater, comparada con el código por una prueba |
| Astronauta: sexo y edad («sex/age sólo si el dataset lo permite») | Cumple: el sexo declarado desde el 2026-11-14 (decisión del usuario, revierte la omisión del 2026-10-23, §5.36.19); la edad, sin campo. El sexo no es un campo del perfil: lo declara el propio tripulante en su propio asiento firmado (`crew-sex`), que se borra solo él. `GET /api/baseline-profile` lo dice en `personal_data`: ningún rango ni umbral del catálogo depende del sexo ni de la edad; el sexo solo decide si se ofrece el seguimiento del ciclo menstrual, que es dato descriptivo, y si la línea base puede ajustarse por fase; lo que la ajusta (desde el 2026-11-15) es la fase del ciclo registrada, no el sexo; el límite de carrera de NASA-STD-3001 [V1 4030] es «universal for all ages and sexes» (Vol 1 Rev C, leída); los requisitos de la norma que sí ajustan por sexo y edad ([V1 4020] nutrición, [V1 4026] densidad ósea prevuelo) EMMA no los evalúa; y la privacidad (§12): se guarda lo mínimo —femenino o masculino y quién lo declaró—, porque hace falta para el ciclo, y la edad no se guarda. Nada de `analysis/`, `advisor/` ni `ingest/` lee el sexo (prueba `test_no_rule_of_emma_reads_sex_or_age`). La única fecha de nacimiento guardada es la de la identidad declarada, para comprobar de quién es un informe o un volumen |
| HabitatState (CO2, O2, presión, temperatura, humedad, ruido/luz, estado de sistemas) | Cumple con dos límites declarados: la luz se muestra y nunca se evalúa (2026-10-10), y desde el 2026-10-13 dice por qué con la norma leída: NASA-STD-3001 Vol 2 Rev F fija niveles por tarea y por periodo, no un límite general; el estado de los sistemas lo declara una persona, firmado, sobre un vocabulario de diseño de EMMA: no es telemetría (2026-10-10). El ruido tiene [V2 6077] desde la tercera ronda (`environment/habitat.py`). Desde el 2026-10-07 cada lectura declara su módulo. La radiación («radiation» de §3), que faltaba, está desde la decimoséptima ronda (§5.37.4): `GET /api/habitat` → `radiation` con la última tasa de dosis de cada dosímetro (la que lee el estado de su tripulante), el evento solar vigente del estado (o «sin datos de DONKI», nunca «ninguno» sin dato) y el módulo sin declarar dicho; sin factores de blindaje; en el panel del hábitat, `HabitatRadiation.tsx`. Descriptivo: no entra en ningún nivel |
| MissionContext | Cumple: día, fase (límites de diseño, solo se muestra), régimen de gravedad, retardo, eventos de misión firmados (EVA, bloques de trabajo y, desde el 2026-10-07, ubicación por módulo) y, desde el 2026-10-10, `available_resources`: lo que una persona declara disponible o no, recurso a recurso, sin inventario ni cantidades. Desde el 2026-10-13, un perfil de misión declarado (órbita baja, superficie lunar, tránsito a Marte) con lo que una fuente leída dice de cada uno: es descriptivo y no cambia el escalado del riesgo, que sigue saliendo del tiempo de luz. Desde el 2026-11-04 el entorno se declara en marcha desde la consola de a bordo, como asiento firmado (`mission-profile`); la configuración da el de partida. Desde el 2026-11-11 (decisión del usuario) el perfil vigente decide hacia qué cuerpo se calcula ese tiempo de luz (`mission_profiles.ephemeris_target`): con órbita baja ya no se escala el riesgo con el retardo de Marte, y un perfil sin objetivo lo declara (`no_target`) en vez de «no casan» |
| Astronauta: `mission_history` | Cumple desde el 2026-10-22 (§5.35.19 del estado del arte): nombre, fechas y dosis de cada misión previa, declarados y firmados (`crew-mission-history`), al lado de la dosis previa del perfil sin sustituirla; la escala de carrera sigue leyendo solo el perfil. Desde el 2026-10-23 (§5.36.4), también de solo lectura en la consola de Tierra con el corte del retardo, y en la crónica como etapa «carrera» antes del prevuelo («Career baseline → Mission 1 → …» de la conversación): una misión previa por hecho, en su fecha declarada y con su asiento, sin veredicto |
| Risk con categoría RIDGE | Cumple: `Domain.ridge` con fuente NASA "The Human Body in Space". Desde el 2026-10-10 la entidad se sirve junta (`GET /api/risks`): RIDGE, regiones, fichas, indicadores, el esquema de niveles leído de la regla del motor y la incertidumbre **declarada, no cuantificada** (el grado y lo sin verificar de sus fuentes). Desde el 2026-10-23 (§5.36.19) la matriz nombra también la región sin nivel propio en el riesgo del dominio de su nivel —el hígado en nutrición—, leída de `anatomy.py`. También desde el 2026-10-23 (§5.36.9): los 22 riesgos que publica el Human Research Roadmap, cada uno con su elemento del HRP, su eje RIDGE (nombrado por una fuente o deducido por EMMA) y si EMMA lo cita en un dominio (7), lo vigila en parte (7) o lo deja fuera de su alcance (8), con el motivo (`GET /api/risks/hrp-coverage`); el de cálculos renales tiene ficha y lo cita además el dominio genitourinario |
| Countermeasure estructurada | Cumple (2026-09-26); la mayoría de entradas son `demo` hasta que las revise un médico de vuelo. Desde el 2026-10-10: `resources` obligatorio y sobre un vocabulario cerrado, la contraindicación se entrega como «pendiente de revisión médica» en vez de callarse (ninguna está escrita), se puede dejar firmado que se decide **no adoptar**, con motivo, y junto a cada recomendación sale la respuesta previa |
| Alert con onset, correlaciones de contexto, estado | Cumple (2026-10-10): las siete preguntas de §10 las compone el backend. Hasta esa fecha esta página daba el detalle por cerrado y dos de ellas («¿qué comprobar?», «¿qué evidencia?») las componía la interfaz; ahora llevan además la persistencia (lecturas fuera de lo esperado sobre el total de la ventana) y la confianza, descriptiva y sin cifra única. `context` incluye el ejercicio registrado y los sistemas declarados. La historia de episodios ya cerrados se recalcula con las reglas de hoy, sin asiento, y lo dice. Desde la decimoséptima ronda (§5.37.6) el «Accept / Dismiss / Investigate» de la conversación está completo: una alerta concreta se puede **descartar**, con asiento firmado `alert-dismissal` y motivo de un vocabulario cerrado (`DISMISSAL_REASONS`: artefacto del sensor, explicada por el contexto, otro motivo con nota); nada se recalcula ni se borra, y solo cuenta lo firmado por la consola |
| Escenario radiación | Cumple, y es el más completo (evento, dosis con Q, refugio, límite de carrera) |
| Escenario CO2/fatiga con correlación entre tripulantes (Human FDIR, §7) | Cumple (2026-09-26): `co2-fatigue`, `analysis/context.py`, `/crew` |
| Escenario hidratación/renal | Cumple (2026-09-26): ingesta, orina de 24 h y densidad (LOINC 9108-2, 3167-4 y 2965-2, leídos en su ficha), escenario `dehydration` y contramedida de hidratación |
| Escenario musculoesquelético inferido | Cumple: banda de pérdida ósea `inferred` (`analysis/inferred.py`) y, desde el 2026-10-10, lo medido del ejercicio a su lado, rotulado como medido y sin modificarla. Sin «% de adherencia»: exige una pauta prescrita que EMMA no tiene |
| Modo anatómico CUERPO → ÓRGANO → estado (§10) | Cumple (2026-10-07): la cadena entera por región —estado, variables, evidencia, tendencia y contramedida— la compone el backend (`GET /api/anatomy/state`) y el panel la muestra. Antes el nivel de cada región lo calculaba la interfaz y una región sin lecturas salía «nominal». El render 3D anatómico queda opcional, como dice la especificación |
| Pantalla principal: estado de misión y tripulación, tendencias y excepciones primero (§10) | Cumple (2026-11-07): la sección «Inicio» de la consola de tripulación (`frontend/src/dashboard/HomeBoard.tsx`, la maqueta del equipo hecha paneles con `data-ui`): nivel y resumen del estado, los peligros RIDGE con el nivel de cada dominio, las cuatro constantes con su curva de 24 h, los seguimientos y recomendaciones abiertos, el perfil de misión con distancia y retardo de las efemérides y las proyecciones predichas. Lo que el backend no da (la foto del tripulante) se dice, no se inventa. El módulo del hábitat sí lo da desde el 2026-11-09 (`mission.location` del estado: desde el 2026-11-10, el que declaró la consola o el que estiman las anclas de módulo de la nave, con `source` y `location_state`; ya no lo pone el simulador; `compliance/record-integrity.md` §3.17 bis). La concha de la maqueta es la consola desde esa fecha (la de pestañas queda en `#clasica`); su adorno es una desviación declarada de NASA-STD-3001 F.5.10 (`compliance/hmi-state-of-the-art.md` §2.5) |

### Lo que EMMA ya tiene y la especificación no pide

Ledger firmado y encadenado, validación externa con dos ejes (MMASH), catálogo LOINC verificado,
clasificación IEC 62304, ecografía y visor 3D con segmentación, informes escaneados con OCR y
desidentificación, comité local de modelos y verificador de citas. Nada de eso contradice la
especificación; la AGPL de Polaris fue una adopción deliberada, que la especificación (§11)
contempla.

## Orden propuesto para cerrar huecos

1. ~~Medido / inferido / predicho~~ — hecho el 2026-09-26.
2. ~~Contramedidas como datos con seguimiento~~ — hecho el 2026-09-26.
3. ~~Hábitat y correlación entre tripulantes~~ — hecho el 2026-09-26.
4. ~~Fase de misión, `onset` y detalle de alerta, línea temporal~~ — hecho el 2026-09-26.
5. ~~Modo anatómico, recuperación posvuelo, coste de medir, hidratación y nutrición~~ — hecho el
   2026-09-26.

### Añadidos fuera del MVP de la especificación

- **Nutrición y palatabilidad** (hipótesis H7 de la base de conocimiento): dominio `nutrition`
  con ingesta energética (código propio: 9052-2 de LOINC es una tasa puntual, no un total
  diario) y aceptabilidad en la escala hedónica de 9 puntos de la NASA (guía ≥ 6, no alerta).
  El escenario `menu-fatigue` se proyecta y no alerta: es una hipótesis. Desde la duodécima
  ronda (2026-10-16) el 6,0 se evalúa: cada valoración por debajo se marca «por debajo del
  criterio de aceptable de la comida» con la frase de NASA-STD-3001 Vol 2 Rev F [V2 7002],
  página 119, leída en su PDF («6.0 or better»), en `GET /api/nutrition/food-acceptability` y en
  la consola. Es una marca sobre la comida, no sobre la persona: no entra en niveles, alertas,
  puntuaciones ni recomendaciones. La norma lo dice de la valoración global de un alimento; EMMA
  lo aplica a cada valoración y lo dice. En `menu-fatigue` quedan por debajo 19 de 40
  valoraciones; `nominal` no genera ninguna. Desde la decimoctava ronda (§5.38.2) cada valoración
  lleva el **alimento valorado** («Food selected / Food rejected» de la conversación): texto libre,
  porque ninguna fuente leída da un vocabulario cerrado de alimentos, con una regla que es decisión
  de diseño de EMMA y así se dice; el panel de nutrición cuenta por plato, sin umbral ni veredicto.
  La deriva `menu_fatigue_acceptability_drop_per_week` del simulador pasó a «sin respaldo en lo
  leído» con el mismo valor (decisión del usuario, §5.38.10): Douglas 2025 no ve bajar la
  aceptabilidad en la ISS.
- **Recuperación posvuelo** con el hemograma real de Inspiration4 (`/replay/recovery`).
- **Coste de medir** por indicador (base de conocimiento §9).

### Segunda ronda (2026-09-28)

Revisión de lo que quedaba en los tres documentos, todo hecho:

- **Radiación en tres escalas y tiempo hasta la acción** (KB §7), que quedó sin hacer en la
  primera ronda.
- **Confirmación humana de la hipótesis** de causa compartida, con seguimiento de la recuperación
  (§7).
- **Contramedidas de hábitat** como datos (§8), con alcance `habitat` y seguimiento del CO2.
- **MissionContext**: EVA y bloques de trabajo declarados (§3).
- **Perfil del tripulante**: misiones previas y dosis de carrera previa (§3).
- **Versión de reglas** en cada estado y alerta (§12).
- **Evidencia OSD-343 y Twins Study** (KB §8), leídas en su ficha. OSD-343 no es "datos de 59
  astronautas" como decía la conversación de ideación: el estudio los analiza, pero sus ficheros
  abiertos en OSDR son de ratón. Se cita con ese alcance.
- **Huecos Med 07 y Med 10 del MDA y relación con el IMM** (§16), citados de NTRS y de la página
  del IMM, en `/framework` y en `clinical-decision-rationale.md`.
- **Relato Espacio → Tierra** (KB §12) en el README.

### Tercera ronda (2026-09-28)

- **«Recuperándose»** (conversación: CAUTION → RECOVERING → NOMINAL): trayectoria descriptiva por
  dominio frente a una ventana antes.
- **Comprobar las proyecciones** (conversación: predicción → resultado → validación):
  retrospectiva inmediata e instantáneas firmadas que se comprueban al llegar su horizonte.
- **Tiempo hasta la acción** en cada alerta, en tiempo de los datos.
- **Nutrición completa**: apetito y fracción de ración que se deja (códigos propios: LOINC solo
  tiene el apetito dentro de cuestionarios concretos). El horario de comidas ya lo recoge el
  contexto «comida» de cada lectura.
- **Aire de cabina**: ruido ([V2 6077], 85 dBA) y CO, amoníaco y formaldehído con los SMAC de JSC
  20584 Rev C por tiempo de exposición, leídos en sus tablas. El límite NC-50 no se implementa
  (curva por bandas de octava).
- **Mapas de investigación**: `bancos-de-prueba.md`, `repositorios-humanos.md` y
  `personas-y-organizaciones.md`, cada fila con su fuente; lo no verificado (personas de Orion,
  TRISH) queda marcado; MMEA quedó verificado en la decimotercera ronda. Desde la decimosexta
  (E14), la pestaña «People & Organizations» de la ideación (y KB §15, P2) está servida:
  `GET /api/people` y el panel «Personas y organizaciones» de la consola de Tierra la derivan del
  registro de evidencia en cada consulta (organizaciones con sus fichas y su año; firmantes con la
  grafía de la cita; Kerry Lee, Jessica Vos y David Dinges con el cargo que les da su ficha), y el
  registro no admite una persona que la ficha no escriba ni un dato de contacto. Las personas de
  Orion pasan de marcadas a comprobadas contra la nota de su ficha; ~~TRISH sigue sin ficha~~ la
  página de NASA sobre TRISH tiene ficha desde la decimoséptima ronda (`nasa-trish`, §5.37.9, con
  HERMES frente a EMMA en `compliance/state-of-the-art.md`); TRISH como organización sigue sin ficha
  propia (la ficha es del HRP).

### Cuarta ronda (2026-10-01), desde Polaris

- **Una sola salida a internet y modo seguro** (§12 seguridad, offline-first): `core/egress.py` y el
  asiento `safe-mode`; la IA local sigue.
- **Estados de una alerta** (§3 Alert, "estado"): detectado → en arreglo → resuelto, firmados.
- **Línea temporal** (§10): crónica del ledger, "próximos días" y "qué depende de este dato".
- **Medidas periódicas** al día o rotas (§2 incertidumbre: un dato que falta se dice).
- **Analíticas escaneadas** (§3 Observation): cada cifra entra solo al confirmarla una persona.
- **Exportar a PDF, buscar en la documentación, dolor sobre el esqueleto y nota dictada.**

### Quinta ronda (2026-10-04), desde Polaris

- **Trazabilidad de la evidencia** (§2): la cita de una firma se coteja contra el informe que
  cita.
- **Incertidumbre primero** (§2): dos analíticas que no coinciden se avisan, sin decidir cuál es
  la buena.
- **Human-in-the-loop** (§2, §12): lo que lleva días esperando a una persona se junta.
- **IA local medida** (§2 versionado y audit trail): el comité de verificadores, con banco, línea
  base y dosier de sus objeciones.
- **Fail-safe** (§12): señuelo de exfiltración en el borde; techo de memoria en los procesos
  pesados.

### Sexta ronda (2026-10-07)

Una revisión contra la especificación encontró que los nueve criterios de §14 se cumplían, pero
que tres piezas que esta página daba por cerradas estaban a medias en el código (el detalle de
alerta, la confianza del dato en pantalla y el modo anatómico) y que faltaban otras de §3 y §10.
Hecho:

- **Contexto correlacionado en cada alerta** (§3 `context_correlations`; §10 «¿qué contexto ha
  cambiado?»): `analysis/alert_context.py`. Excursiones del hábitat, EVA y bloques de trabajo,
  cambios de fase, evento solar y contramedidas adoptadas que solapan con una ventana alrededor
  del inicio. Cada elemento va rotulado «correlación temporal, no causa» y cada fuente dice si
  tenía dato. La ventana es un parámetro de diseño declarado, sin fuente. Antes esa pregunta la
  componía la interfaz.
- **Concordancia entre señales** (§6): cuántos indicadores del dominio acompañan al que inició la
  alerta, cuáles van en contra y cuáles no tienen dato. Descriptivo: no entra en la puntuación.
- **Selector de tripulante y comparación entre tripulantes** (§10): la consola veía solo a
  `crew-01`. `GET /api/crew/compare` da el mismo indicador en cada uno contra su línea base
  propia y sobre el mismo eje. Toda firma lleva el sujeto del estado en pantalla.
- **Confianza del dato visible** (§2, §10): `data.quality` en `/status` y una marca en la consola
  y en las gráficas. Lo que una fuente no declara se dice «no declarada», sin número.
- **Modo anatómico con la cadena entera** (§10, §4): `GET /api/anatomy/state`.
- **Registro único de evidencia** (§3 EvidenceRef, §2): `evidence/registry.py`, una ficha por
  fuente con identificador, tipo, fecha, entorno y población. Lo que no está escrito en el
  repositorio queda en `null` y se lista como sin verificar (`GET /api/dossier/references`).
- **Ubicación por módulo** (§3 HabitatState y MissionContext): la declara una persona, va al
  ledger como evento de misión, ordena hipótesis y se muestra en el estado (`mission.location`);
  no mueve ningún nivel. Desde el 2026-11-10 también la **estiman las anclas de módulo** de la
  nave (BLE hoy; el receptor solo escucha, `analysis/location.py`), rotulada como estimada, con
  estados «indeterminada» y «caducada», y la consola manda sobre ella. El simulador ya no pone a
  nadie en ningún módulo. Hueco abierto: la estimación no está validada dentro de un módulo
  metálico (`compliance/location-sensing-feasibility.md`).
- **No mezclar humanos y animales** (§2): una fuente sin PMID cuyo título dice que es un modelo
  animal (OSD-288) se rotula preclínica, «desde el texto de la cita, no del registro».
- **Línea temporal en el tiempo de los datos** (§10): la crónica, «próximos días» y las medidas
  periódicas cuentan desde el instante de referencia de `/api/status`, no desde el reloj del
  ordenador, y lo declaran (`as_of` con su origen). La crónica cuenta lo que pasó además de lo
  que se decidió —desde cuándo está cada alerta, cambios de nivel y de fase, excursiones de
  cabina, eventos del plan, fin de la ventana de seguimiento, silencios— por las etapas de §10.

Ninguna de estas piezas mueve niveles, umbrales ni alertas (invariante 5): cada una tiene su
prueba de que el veredicto del motor es idéntico con y sin ella.

**Cruces entre piezas hechas a la vez**, resueltos al juntarlas: el contexto de una alerta y la
comparación entre tripulantes declaraban que EMMA no registra en qué módulo está cada
tripulante. Con la ubicación declarada, el contexto dice de cada excursión si el tripulante
estaba en ese módulo, y la comparación dice que no usa la ubicación. Y la línea temporal
trataba una ubicación declarada como un evento del plan más: ahora la cuenta como lo que es,
un hecho firmado, sin inicio ni fin de plan y sin sitio entre los asuntos de la semana.

### Séptima ronda (2026-10-07), sobre Polaris

La copia de Polaris se puso al día y se cerró lo que la sexta ronda dejó suelto. El detalle,
unidad a unidad, está en `docs/polaris-divergencias.md` §17. Lo que toca a la especificación:

- **Trazabilidad de la evidencia y human-in-the-loop** (§2, §12): quien pone la segunda firma de
  una decisión de alto riesgo ve la frase literal del informe que cita (des-identificada) antes de
  firmar, y esa frase queda firmada con su puntero y la huella del texto.
- **Incertidumbre primero** (§2): la densidad (HU) de cada lesión candidata se da con su
  dispersión, «no valorable» por debajo de un mínimo de vóxeles y sin veredicto; el PDF de
  anotaciones de dolor (`/api/export/dolor.pdf`) dice «sin anotaciones de dolor en el ledger», no
  «sin dolor», y declara qué nota es dictada; el esqueleto del modo anatómico dice si es el TAC
  del tripulante o la figura de referencia, qué huesos faltan o están cortados y qué zona de dolor
  queda fuera del estudio.
- **El visor es cliente del modelo** (§10): el esqueleto del propio TAC, el dolor referido sobre él
  y todos sus rótulos los da el backend.
- **Privacidad** (§12): un familiar nombrado en un informe se enmascara conservando el parentesco;
  un NIfTI rechazado por texto en la cabecera se puede limpiar dentro de EMMA, solo a petición de
  quien lo sube, y el asiento firmado dice que se limpió y qué campos.
- **Transparencia sobre el código de terceros** (AGPL §5a): el inventario de la copia de Polaris
  —qué carga, qué usa EMMA, qué se cambió— se ve en la consola de Tierra, y la copia literal queda
  clasificada como SOUP con su ficha (`compliance/software-safety-classification.md`).
- **Fail-safe** (§12): un fichero de freno de Polaris en la carpeta personal ya no puede cortar la
  salida de EMMA, tampoco desde una herramienta importada tarde.

Ninguna de estas piezas toca el análisis, los umbrales ni las alertas (invariante 5): en toda la
ronda no cambia nada de `app/analysis`, `app/advisor`, `app/validation`, `app/ingest` ni
`app/environment`.

### Octava ronda (2026-10-08), sobre Polaris

La copia de Polaris se puso otra vez al día, se copiaron sin uso las herramientas locales que
faltaban y se cerraron errores de concurrencia. No añade ninguna función a la consola ni cierra
ningún hueco de las tablas de arriba. El detalle está en `docs/polaris-divergencias.md` §18. Lo
que toca a la especificación:

- **Trazabilidad y audit trail** (§2): dos resultados que quedan en un asiento firmado podían
  salir mal por dos peticiones a la vez, sin que el dato hubiera cambiado.
  - El control de la cadena vertebral se lee de lo que Polaris escribe por consola. Si coincidía
    con una exportación a PDF o una reindexación, ese texto caía en otra captura y el control
    salía «no revisada» en el resumen firmado de la segmentación. Ahora hay una sola captura para
    todo el proceso (`app/polaris/console.py`).
  - El cotejo de una cita contra su informe podía dar `no_localizada` si dos cotejos del mismo
    informe coincidían (firma y contrafirma, o dos consolas). Ahora el cotejo entero y la lectura
    de la frase van bajo un mismo cerrojo (`evidence/vault.py`). Dos procesos de EMMA sobre el
    mismo estado siguen sin cubrir.
- **Offline-first y fail-safe** (§2, §12): el primer uso del borde de salida —sembrar el señuelo de
  exfiltración y configurar la copia— ocurre una sola vez aunque lleguen varias peticiones a la
  vez (`core/egress.py`, `app/polaris/__init__.py`). Si el sembrado falla, la puerta no se da por
  lista y se reintenta.
- **Transparencia sobre el código de terceros** (AGPL §5a): cada herramienta de Polaris que no se
  copia va por su nombre y con su motivo en `polaris/ADOPTADO.txt`, en vez de bajo una frase
  genérica que no se podía contrastar; el motivo es lectura de su docstring, no una auditoría de
  su código. Y la copia no recibe nada generado: el visor web se compila fuera de ella.

Ninguna de estas piezas toca el análisis, los umbrales ni las alertas (invariante 5): en toda la
ronda no cambia nada de `app/analysis`, `app/advisor`, `app/validation`, `app/ingest` ni
`app/environment` (`git diff 7315b18 2ac2d49 --stat` sobre esas carpetas sale vacío).

### Novena ronda (2026-10-09 y 10): lo que faltaba del contexto

Dos revisiones contra los tres documentos, hechas sobre el código y no sobre esta página,
encontraron que los nueve criterios de §14 se cumplían pero que quedaban piezas a medias, campos
de §3 sin existir y funciones que la base de conocimiento y la ideación piden y no estaban ni
hechas ni descartadas. Hecho, en dieciséis piezas:

- **Detalle de alerta entero en el backend** (§10, §6, §3): las siete preguntas, la persistencia
  y la confianza descriptiva (`analysis/alert_support.py`).
- **Toda regla que decide, versionada** (§12): `core/versioning.py`. El simulador declara cada
  deriva, y las que no tienen respaldo van como «diseño».
- **La interfaz no redacta** (§4): el nombre de cada nivel, fase y trayectoria lo da el backend
  (CONCERN es «precaución» en todas partes), y la caducidad de un dato externo es una regla del
  backend.
- **Human FDIR para cualquier parámetro de cabina** (§7): los siete pasos a la vista con su
  estado, y un contraste de sensor (`demo`) para los parámetros que no son CO2. De esos EMMA solo
  cita el límite: no hay nada leído sobre su efecto en las personas, y la hipótesis lo dice.
- **Luz de cabina** (§3): se muestra y nunca genera una excursión (en la décima ronda se leyó
  la norma: no hay un límite general que evaluar).
- **El ejercicio, medido** (§9): junto a la banda ósea y como fuente del contexto de una alerta.
- **Logs sin contenido personal** (§12): la traza se reduce a tipo y lugar, la línea de acceso
  pierde su consulta y el fichero de la aplicación de escritorio tiene tope.
- **Registro diario del tripulante y PVT en pantalla**: lo que antes solo llegaba del simulador
  se puede anotar o hacer en la consola, y entra firmado como cualquier observación.
- **Marco NASA e hipótesis H1-H7 a la vista** (§16, KB §13): cada hipótesis con lo que EMMA
  tiene, su estado y lo que **no** demuestra. Ninguna figura como probada.
- **Entidad Riesgo y coste de medir** (§3, KB §9): `GET /api/risks`; el coste gana tres
  dimensiones descriptivas, y lo que el repositorio no permite clasificar queda «sin clasificar».
- **Contramedidas** (§8, H5): «no adoptar» con motivo, respuesta previa y recursos declarados.
- **Estado de sistemas, vínculo sensor-tripulante y recursos** (§3): los tres los declara una
  persona, firmados, como la ubicación. Ninguno es telemetría ni inventario, y lo dicen.
- **Historia de alertas ya cerradas** (§3, §10): recalculada con las reglas de hoy, sin asiento.

Ninguna de estas piezas mueve niveles, umbrales ni alertas (invariante 5). Esta ronda sí toca
`app/analysis` y `app/advisor`, así que se comprobó de punta a punta: el veredicto de los nueve
escenarios del simulador —niveles, puntuaciones, alertas, recomendaciones, banda inferida y
excursiones de cabina, para los cuatro tripulantes— es idéntico entre el commit de partida
(`2c15d6a`) y el final. `rules_version` sí cambia de valor, porque ahora recoge reglas que antes
no recogía y la biblioteca de contramedidas creció.

**Cruce entre piezas hechas a la vez:** las recomendaciones del estado ganaron tres campos (la
decisión firmada, la respuesta previa y los recursos) y el modo anatómico seguía sirviéndolas sin
ellos; lo cazó la prueba que compara las dos respuestas.

**Límites que quedan a la vista:**

- ~~Las escalas de autoinforme (ánimo, síntomas, apetito) no tienen rótulos: se ofrecen como rango
  numérico, «escala sin rótulos verificados».~~ Siguen sin rótulos leídos, y desde la duodécima
  ronda (2026-10-15) llevan sus anclas como decisión de diseño de EMMA, sin validar (abajo).
- La PVT en pantalla usa parámetros de diseño de EMMA y un navegador no es un instrumento
  calibrado; el panel lo dice.
- ~~El aviso de un sensor vinculado a otro tripulante solo existe en la respuesta de la ingesta~~
  y ~~la evaluación de una adopción ya cerrada compara con el nivel de hoy~~: cerrados en la
  décima ronda.
- Una anotación a mano se fecha con la hora real; con datos simulados cae antes de la serie.

### Décima ronda (2026-10-13 y 14): fuentes leídas, decisiones tomadas y remates

La novena dejó la lista de «Pendiente» en dos bloques. El usuario decidió (2026-10-13) leer las
fuentes **ahora, en Tierra y durante el desarrollo** —el producto no gana ninguna conexión: a
bordo sigue sin red—, cuatro decisiones y cuatro remates. Hecho, en once piezas:

**Fuentes leídas** (cada dato con su ficha, la frase o la fila exacta y la fecha de lectura; lo
que no se encontró sigue «sin verificar»):

- **Cabina** (§3): NASA-STD-3001 Vol 2 Rev F y JSC 20584 Rev C. La luz no tiene un límite general
  (la norma da niveles por tarea, tabla 8.7-1, y por periodo): sigue sin evaluarse y ahora dice
  por qué, con los requisitos de referencia al lado. El contexto de una excursión lleva «lo que
  se sabe» de cada parámetro con frases literales.
- **Marco NASA** (§16): las tres referencias de ExMC, las limitaciones declaradas del IMM, el
  estado de los huecos Food y Level of Care, leídos (`data/nasa_framework_read.json`); ningún
  anclaje queda «sin leer».
- **PVT y escalas**: `GET /api/pvt/protocol` enseña, parámetro a parámetro, lo publicado para la
  PVT-B (Basner et al. 2011) junto a lo que usa EMMA. **Ningún valor que puntúa cambió**
  (invariante 5); las diferencias se dicen. De la escala hedónica se leyeron los dos extremos (y,
  en la decimotercera ronda, los puntos 2 a 8).
- **Registro de evidencia**: fecha, DOI, título y página reales de cada ficha, leídos en su
  fuente; de 67 campos sin verificar quedan 17, y tras la undécima ronda (2026-10-14) uno: la
  fecha del listado de huecos del Human Research Roadmap, que el listado no declara. Cinco
  entornos se leyeron y quedan **fuera del enumerado** (`outside_enum`): juntan entornos que
  ningún valor cubre. El estudio de GeroScience que el código invocaba
  tiene ficha (preclínico, hígado de ratón) y el docstring dice lo que el resumen dice.

**Decisiones:**

- **El aviso de sensor, en la consola**: cada lectura firmada puede llevar el identificador del
  dispositivo (opcional), y el estado dice qué lecturas vienen de uno vinculado a otro tripulante.
  No bloquea ni entra en el análisis.
- **El nivel, al cerrar una adopción**: el cierre lo guarda y la respuesta previa compara con ese
  día; los cierres antiguos comparan con hoy y lo dicen.
- **Quién anota**: el registro diario y la PVT de consola firman con fuente propia (`crew-diary`,
  `console-pvt`), por rutas propias que exigen el nombre de quien teclea
  (`Observation.performer`). Lo firmado antes se sigue leyendo; donde no hay anotador, «no consta».
- **Segunda firma más estricta**: si cita un informe guardado, se rechaza con la cita no
  localizada o sin declarar haber leído la frase, y no se escribe asiento. La primera firma puede
  llevar la frase.
- **Perfil de misión, descriptivo**: se muestra con lo que una fuente leída dice de cada perfil;
  una prueba fija que el escalado del riesgo no depende de él.

**Remates:**

- **Tarjetas de recomendación más cortas**: a la vista, lo que hay que leer primero; coste,
  recursos y respuesta previa, plegados con su resumen. Ninguna advertencia desaparece, y un
  recurso que falta se ve sin abrir nada (`compliance/hmi-state-of-the-art.md` §5.27).
- **Fase de contraste de un TAC, declarada** por una persona sobre un vocabulario cerrado, firmada
  en un asiento propio; se enseña junto a la densidad y en la comparación. EMMA no la propone ni
  la comprueba, y no decide nada.

Ninguna pieza mueve niveles, umbrales ni alertas (invariante 5): el veredicto de los nueve
escenarios del simulador —niveles, puntuaciones, alertas, recomendaciones, banda inferida y
excursiones de cabina, para los cuatro tripulantes— es idéntico entre el commit de partida
(`7c44dc3`) y el final. `rules_version` cambia de valor porque `countermeasures.json` ganó la
frase literal de la fuente en tres tiempos de tripulación. Todo campo nuevo de un asiento es
opcional, y cada uno tiene su prueba con un registro escrito antes del cambio.

**Lo que las lecturas encontraron y no se ha tocado** (cada una es una decisión):

- ~~**Límites de cabina que no casan del todo con la norma**~~ — **cerrado el 2026-10-14**
  (undécima ronda, `environment/habitat.py`): 145-155 mmHg de O2 pasa a rango objetivo (aviso) y
  los límites de salud del O2 son los de exposición de la tabla 6.2-1 (127 en media de 1 h, 122
  absoluto, 356); [V2 6012] se juzga como la figura conjunta que es, con sus cuatro vértices
  rotulados y la humedad simultánea, y sin ella la temperatura solo fuera de 18-27 °C; los 85 dBA
  de [V2 6077] siguen siendo límite de salud («hazardous noise limit») con un rótulo que dice para
  qué lo escribe la norma; el amoníaco evalúa sus SMAC de 30, 180 y 1000 días. Las excursiones de
  cabina de los nueve escenarios del simulador no cambian (ninguno se acerca a esos límites).
- ~~**Med07 figura «Closed»** en el Human Research Roadmap y Med10 se fusionó en Medical-701; los
  textos que presentan a EMMA sobre esos dos huecos siguen como estaban.~~ Cerrado en la undécima
  ronda (2026-10-14): cada hueco nombrado lleva su estado leído (`nasa_framework_read.json`,
  `gap`), los textos dicen a qué pregunta del enunciado de 2020 responde EMMA y que NASA da Med07
  por cerrado con su propia capacidad, y una prueba (`test_gap_status_texts.py`) impide presentar
  como abierto un hueco cerrado, fusionado o archivado. El hueco de fatiga de menú (FN-205) figura
  archivado y KB-H7 lo dice; NASA-STD-3001 Vol 1 ya no define Level of Care desde su Rev B.
- **PVT** (declarado, no corregido: cambiarlo movería la puntuación validada): la fuente cuenta un lapso con «≥ 500 ms» y EMMA con «> 500 ms»; ese umbral es el de la
  PVT de 10 minutos (la PVT-B usa ≥ 355 ms); un estímulo sin respuesta se da por lapso a los 30 s
  en lo publicado y EMMA abandona a los 10 s. `MIN_TRIALS` no tiene valor publicado. Desde la
  undécima ronda las cuatro se declaran juntas en `GET /api/pvt/protocol` (`divergences`), con
  la frase de la fuente y lo que hace EMMA deducido del código que puntúa; ningún valor cambió.
  Desde la duodécima (2026-10-15) el panel de la PVT las enseña plegadas bajo el protocolo, con
  la frase, su ubicación y lo no encontrado, sin color de alerta (`pvt/divergences.ts`).
- **Escalas**: los rótulos intermedios de la escala hedónica no tienen fuente accesible, y las
  tres escalas propias no tienen fuente que leer: sus anclas son una decisión, no un dato. Desde
  la duodécima ronda (2026-10-15) esa decisión está tomada y publicada: `GET /api/diary`
  (`design_anchors`) y el panel del diario dan, para ánimo, síntomas y apetito, qué significan
  el 0 y el 10, que entre medias ningún punto lleva ancla, el rango de referencia que ya tenían
  y por qué no hay instrumento publicado detrás, con la marca «decisión de diseño de EMMA, sin
  validar». Viven en el catálogo (`codes.OWN_SCALE_ANCHORS`), no con lo leído
  (`instruments_read.json`), y no cambian rango, unidad ni nada que puntúe. Una prueba
  (`test_own_scale_anchors.py`) impide presentarlas como validadas, citarles una ficha de
  evidencia como si fuera su instrumento y que un texto de EMMA llame validada a una escala.
- ~~**OSD-288**: OSDR lista 9 muestras; el «n = 12» no se pudo confirmar en su página.~~ Cerrado en
  la undécima ronda (2026-10-14): 12 ratones volaron, el conjunto publica 9 muestras de bazo (3 de
  control en Tierra, 3 a 1 g por centrifugación y 3 en microgravedad). La ficha lo dice con la
  frase de OSDR y la de Horie et al.; el «n = 12» contaba ratones lanzados, no datos.
  Desde el 2026-11-11 la API de datos de OSDR lo comprueba: `GET /api/osdr/studies` lee la
  ficha de cada estudio de OSDR citado (título, organismo, misión, ensayo, muestras, fecha) y la
  compara con el registro; OSD-288 da `Mus musculus` y 9 muestras.
- ~~**Segunda firma**: una que cita algo que no es un informe guardado, o nada, no se coteja.
  Desde la undécima ronda se dice a la vista —«no cotejada» y por qué, en la respuesta y en el
  panel del borrador—, pero se sigue admitiendo: exigir cita es decisión pendiente.~~ Decidido
  (2026-10-15) y hecho en la duodécima ronda: toda segunda firma de alto riesgo cita un informe
  guardado, con la frase localizada y declarada leída; si no, 422 y ningún asiento, y el panel
  dice antes de firmar qué falta. Las admitidas antes sin informe siguen verificando y se
  rotulan al leer (`record-integrity.md` §3.24).
- ~~**Fase de contraste**: la declaración no sale en la crónica, y redactar un estudio no redacta
  el nombre de quien declaró su fase.~~ Cerrado en la undécima ronda (2026-10-14): sale en la
  crónica del tripulante del estudio, con su rótulo y sin la nota, y redactar el TAC redacta sus
  declaraciones en el mismo `commit`, una lápida cada una (`record-integrity.md` §3.13 bis).
  Lo que entonces quedó dicho que no hacía —redactar el estudio no redactaba sus segmentaciones—
  se cerró en la duodécima ronda (2026-10-15): ver abajo.

### Undécima ronda (2026-10-14 y 15): lo que las lecturas encontraron, corregido o leído

El usuario decidió (2026-10-14) corregir lo que la décima encontró, meter el posvuelo en la
crónica y seguir leyendo fuentes en Tierra (el producto no gana ninguna conexión). Nueve piezas:

**Correcciones:**

- **Cabina conforme a la norma** (`environment/habitat.py`): ver la lista de arriba.
- **Marco NASA al día**: Med07 cerrado, Med10 fusionado en Medical-701, fatiga de menú archivada,
  cada uno con su frase y fecha; los textos de EMMA ya no los presentan como huecos abiertos.
- **Fase de contraste en la crónica y en la redacción** (`timeline.py`, `core/storage.py`).
- **Divergencias que se dicen**: una contrafirma que no cita un informe guardado se rotula «no
  cotejada» y por qué (sigue admitida); `GET /api/pvt/protocol` declara las cuatro divergencias de
  la PVT con su fuente, deducidas del código que puntúa, y una prueba fija que ningún valor cambia.

**Decisión:** la recuperación posvuelo entra en la crónica del tripulante (`_recovery_events`):
cada toma posvuelo, frente al rango prevuelo propio, sin veredicto. Con Inspiration4, las mismas
12 tomas que el panel de recuperación.

**Fuentes leídas** (cada dato con su frase, página y fecha; lo no encontrado sigue sin verificar):

- **Registro de evidencia**: de 17 campos sin verificar queda 1 (la fecha del listado de huecos
  del Roadmap, que no la publica). Un campo leído que ningún valor del enumerado cubre se declara
  `outside_enum`, con motivo. OSD-288: 12 ratones volaron y el conjunto publica 9 muestras.
- **Coste de medir**: de 170 pares indicador-dimensión «sin clasificar» quedan 82. Sangre, orina
  de laboratorio y saliva: en Tierra y con espera, con frase de NTRS y PubMed; al lado, lo que lo
  matiza (demostraciones de analizadores de sangre a bordo). MMEA leído en su página de NASA.
- **Luz personal**: NASA no publica un límite personal; la recomendación con cifras para la
  persona es de Tierra (Brown et al. 2022) y excluye el trabajo de noche. Se enseña, no se evalúa.
- **Tiempo de tripulación**: dos contramedidas ganan tiempo con frase de OCHMO (TB-031, MTB-009) y
  dos más pasan a citar un protocolo oficial; ninguna fuente da contraindicaciones.

**Cierre medido** (2026-10-15): suite entera en verde, en tres tandas (2948 pruebas); el veredicto
del motor —niveles, puntuaciones, alertas, recomendaciones y banda inferida de los nueve
escenarios para los cuatro tripulantes— idéntico entre `5d8dbac` y `570b027`, y las excursiones del
simulador de cabina, también; validación externa con MMASH en verde (falsa alarma y sensibilidad
juntas, `compliance/external-validation.md`); 15 campañas de mutantes tocadas, 191 de 191 cazados;
pasada visual por CDP de las dos consolas; instalador reconstruido desde el venv limpio, con los
datos nuevos dentro, y su backend congelado sirve las rutas nuevas.
La suite entera cazó un cruce que ninguna pieza veía: el fichero de referencia de las hipótesis de
cabina lleva dentro las fichas de evidencia que la lectura completó (regenerado y revisado).

**Lo que se vio y queda dicho** (las dos cosas, cerradas en la decimotercera ronda): el «Alcance»
de una ficha de evidencia junto a una hipótesis de
cabina repite la nota de lectura entera (organización releída en PubMed incluida): es largo para
la consola de tripulación. Y con datos posvuelo, la cabecera dice «posvuelo y recuperación» junto
a la gravedad declarada por configuración («microgravedad»), que no sigue a la fase.

### Duodécima ronda (2026-10-15 y 16): decisiones tomadas y remates

El usuario decidió (2026-10-15) cuatro de las decisiones abiertas y tres remates. Siete piezas:

**Decisiones:**

- **Redactar un TAC arrastra sus segmentaciones** (`core/storage.py`): en el mismo `commit`, con su
  lápida y su binario borrado; si una falla, nada. Un registro escrito antes sigue verificando.
- **Toda contrafirma de alto riesgo cita un informe guardado**, con la frase localizada y
  declarada vista, o se rechaza sin asiento (`countersign_rule.py`); lo firmado antes se lee
  rotulado con la regla de entonces.
- **Anclas de las escalas propias**: ánimo, síntomas y apetito publican sus extremos como
  «decisión de diseño de EMMA, sin validar», aparte de los rótulos leídos; una prueba impide
  presentarlas como validadas.
- **Indicadores descriptivos** (lista de pendientes): visión, carga de trabajo, VO2 pico y
  prensión, con su medida leída; el estado no los lee.

**Remates:** el posvuelo de la crónica, legible y agrupado por día; las divergencias de la PVT,
en su panel; y el criterio 6,0 de la comida, evaluado: cada valoración por debajo se marca con la
frase de [V2 7002], como marca sobre la comida (el estado no la lee).

**Cierre medido** (2026-10-16): suite entera en verde en tres tandas (3050 pruebas); veredicto del
motor —niveles, puntuaciones, alertas, recomendaciones y banda inferida de los nueve escenarios
para los cuatro tripulantes— idéntico entre `1923077` y el final; MMASH en verde (falsa alarma y
sensibilidad juntas); 22 campañas de mutantes de la ronda, 199 de 199 cazados. Se encontró y se
arregló una campaña antigua mal escrita desde el primer commit (`round2_versioning`: su ancla ya
no existía); las 204 campañas tienen ahora sus 1466 anclas exactamente una vez. La pasada visual
encontró que ocho direcciones web en monoespaciada no se partían y, con un plegable abierto,
ensanchaban la página de 1400 px a 2920; arreglado, con una prueba (`lib/urlWrap.test.ts`).
El instalador, reconstruido desde el venv limpio: su backend congelado sirve las rutas nuevas.

**Lo que se vio y queda dicho** (cerrado en la decimotercera ronda): en «Lo publicado y lo que hace
EMMA» de la PVT, la fila del
lapso marca «= es el valor de EMMA» junto a «≥ 500 ms», cuando EMMA cuenta «> 500 ms»: la cifra
coincide y el operador no (el párrafo de debajo y las divergencias lo dicen bien).

### Decimotercera ronda (2026-10-20): decisiones tomadas, Polaris y fuentes leídas

El usuario decidió (2026-10-20) cuatro de las decisiones abiertas: base sin rango, nombres en
español, gravedad en posvuelo y cuatro pendientes de Polaris. Entraron además tres remates de lo
visto en rondas anteriores y tres tandas de lectura de fuentes en Tierra. Doce piezas, hechas en
paralelo y fusionadas una a una:

**Decisiones:**

- **Sin rango no hay base** (`ingest/codes.py`): un indicador sin rango de referencia ya no hereda
  la base «observada». Su `reference_basis` es `null` en `/api/indicators` y en la huella de
  reglas, y el catálogo no carga si hay rango sin base o base sin rango
  (`VitalCode.__post_init__`; medio rango cuenta como rango). Afecta a 59 de los 88: las
  analíticas, cuyo rango trae el laboratorio en su informe; la ecografía; el apetito; y los
  descriptivos. Cambia `rules_version`; el veredicto no, porque el motor solo distingue
  `guideline`.
- **Nombre en español para el catálogo entero** (`ingest/names_es.py`): cada uno de los 88
  indicadores tiene nombre en español con su origen declarado. Los 46 analitos de una analítica
  llevan el de Polaris (`ANALITOS`, leído de su copia en `data/lab_loinc.json` sin cargar Polaris
  y cotejado por prueba con `labs.names`); los otros 42, uno redactado por EMMA y rotulado «nombre
  de EMMA, no de LOINC», fiel a la propiedad del código. Todas las frases que ve la tripulación
  cambian a la vez: desviaciones, tendencias, persistencia, confianza, contexto de alerta,
  ejercicio, comparación entre tripulantes, rutinas, seguimiento, crónica posvuelo, mapa de
  dependencias y hechos del borrador. El nombre de LOINC se queda en inglés en FHIR y en la API, y
  cada campo que nombra un indicador lleva `display_es` al lado, que la interfaz enseña tal cual.
  No se ha leído ninguna traducción de LOINC al español: queda sin verificar que exista.
- **La gravedad sigue a la fase en posvuelo** (`core/mission.py`): la cabecera y el contexto de una
  alerta decían «posvuelo y recuperación» junto a «microgravedad». En posvuelo el backend da la
  gravedad del momento y conserva la configurada como la de la misión (`gravity_display`);
  `gravity_regime` se queda por compatibilidad. La decisión decía «en Tierra (1 g)», pero el filtro
  de lenguaje (`text_guard.py`) lee «1 g» como una dosis de un gramo: se cambió la frase («en
  Tierra (gravedad terrestre)»), no la defensa. Una prueba fija que el análisis no lee la gravedad.
- **Polaris** (`docs/polaris-divergencias.md` §18), cuatro pendientes:
  - **El freno HALT avisa solo** (`api/safe_mode.py`, `components/SafeMode.tsx`): el backend
    redacta el aviso (`halt.notice`): qué es (no el modo seguro: sin firma ni asiento, y levantar
    el modo seguro no lo quita), desde cuándo (la fecha del fichero, rotulada «sin firma»), qué
    corta (la salida a internet, leída de `egress.ALLOWLIST`), qué sigue (constantes, análisis,
    alertas y modelo local) y cómo se quita (borrando el fichero). En modo sin red no se presenta
    como la causa del corte. La franja común de las dos consolas lo pinta en la celda «Red», en
    amarillo con triángulo, y relee cada 30 s; si una lectura falla, lo último visto se conserva
    marcado en cian.
  - **Modo DIRECTO del esqueleto** (`pain_on_skeleton.py`): la zona de dolor anclada a un hueso que
    la figura trae entero se pinta en el centroide de ese hueso, en la figura de referencia y en
    la del TAC propio, como en el `main()` de `visor3d_superpone_focos` (una línea, reproducida en
    EMMA porque ese `main()` no se llama). Cada zona dice cómo se colocó (`placed_on`: `bone` o
    `fit`). Dos divergencias declaradas: aquí se decide zona a zona y no de todo o nada (cabeza,
    abdomen o rodilla no tienen hueso en el mapa), y el ajuste se sigue calculando, porque coloca
    las zonas sin hueso y decide si se pinta algo, con el mismo umbral. En `esqueleto-4` el ajuste
    sigue en 44,4 mm de media y 75,1 de peor (umbral 80,0), pero ese error ya no es la posición de
    las zonas ancladas, que caen sobre su hueso (la lumbar se desplaza 75 mm, hasta L3); una
    prueba vigila ahora también el peor error (margen 4,9 mm). En la figura de referencia las 11
    zonas ancladas se mueven hasta su hueso (hasta unos 79 mm); allí el peor error del ajuste ya
    pasaba del umbral (101 px frente a 89,5) aunque la media no. Silueta y ancla visceral siguen
    abiertas.
  - **Las pruebas de la copia, con su temporal** (`scripts/polaris_tests.py`): reciben `TMP`,
    `TEMP` y `TMPDIR` dentro de la carpeta de la pasada, fuera de `polaris/`; se borra entera al
    terminar y lo que se resista se nombra.
  - **`cotejado` de `estado_actual` sin importar una prueba**, que no viaja con la aplicación
    instalada y la hacía fallar allí: cambio §5a en `CAMBIOS.json`, reaplicado por
    `polaris_sync.py`; `fecha_cotejo` pasa literal a la herramienta, con su SPDX, `ORIGEN.md` y
    `NOTICE`. En una copia sin `tests/` la original cae con `ModuleNotFoundError` y la parcheada
    escribe el mismo registro. `test_packaging.py` vigila que ninguna herramienta importe una
    prueba y que la función traída siga siendo la de la prueba.

**Remates:**

- **PVT, «misma cifra, distinto operador»** (`api/pvt_console.py`): la marca de cada valor leído
  compara la cifra y, donde la fuente escribe uno, el operador; el de EMMA se deduce del código que
  puntúa, no se escribe a mano. La fila del lapso dice «≠ misma cifra, distinto operador (EMMA:
  > 500 ms)» junto a «≥ 500 ms»; la salida en falso («< 100 ms») sigue siendo «=». La marca la da
  el backend (`marker_display`) y el panel la pinta tal cual. Ningún valor que puntúa cambia.
- **El alcance de una ficha, plegado** (`evidence/registry.py`, `evidence/EvidenceEntry.tsx`): la
  nota de cada ficha junta lo que mide la fuente y la bitácora de su lectura. El registro deriva
  de ella, sin tocar los datos, lo que va a la vista (`scope_in_view`: las frases antes de la
  primera lectura fechada, prefijo literal); la nota entera queda plegada debajo, sin perder
  texto, en las dos consolas. Una fuente con animales cuya nota empieza por la lectura se enseña
  entera. Junto a la hipótesis de cabina por CO2, de 2397 a 1019 caracteres a la vista; las fichas
  cortadas quedan fijadas en una prueba (`compliance/hmi-state-of-the-art.md` §5.29).
- **El nombre delante del parentesco** (`reports/deid.py`): «con Rosa Beltrán, su cuñada» → «con
  [REDACTADO], su cuñada»; también «Rosa Beltrán (su madre)», «Pedro, mi hermano» y «cuñada del
  paciente». Exige parentesco con posesivo o «del paciente» y descarta lo clínico, los estados, los
  centros y las vías. De paso, la marca de Polaris se une con el resto de un apellido compuesto
  («Pérez-Gómez»). Con un informe inventado nuevo (`informe12`), 44 de 45 identificadores tapados
  enteros y 1 fuga de 34; sin la pasada, 40 de 45 y 5 de 34. Lo que deja pasar está declarado y con
  prueba (un nombre de pila suelto al principio de la frase, la aposición sin posesivo, las
  mayúsculas sostenidas, una profesión sin tratamiento, un nombre junto a una palabra de la lista
  clínica). Lo que decide son listas finitas, y el corpus lo escribió quien escribió la regla. La
  capa NER sigue abierta y sin activar.

**Fuentes leídas** (cada dato con su frase, dónde y la fecha; lo no encontrado sigue sin verificar):

- **Qué consume cada medida y dónde se mide la orina de 24 h** (`measurement_cost.json`): el
  volumen de la orina de 24 h tomada en vuelo no se mide a bordo: cada micción va a una bolsa con
  1 mL de LiCl y tras el aterrizaje se analiza el litio para calcular el volumen (Mehta et al.
  2017; Broyan y Cibuzar 2009). Regla `orina-24h-en-tierra`, en Tierra y diferido, con al lado el
  UMS diseñado para medirlo a bordo y lanzado en 2011 (no se leyó si llegó a usarse) y el protocolo
  de medidas estándar descrito en 2025, que no recoge orina en vuelo. Consumibles, con su frase:
  bolsas con trazador (volumen de 24 h y NTX), tubos de suero (32 analitos), papel de filtro
  (cortisol salival) y algodón Salivette (virus en saliva). El hemograma queda fuera: se mide en
  sangre entera y lo leído no dice en qué tubo. De 85 pares indicador-dimensión sin clasificar
  quedan 47 (esta página decía 82; la duodécima ronda había añadido tres indicadores).
- **Tiempo de tripulación**: de las 32 contramedidas «sin fuente» y las dos con fuente sin
  duración, una gana cifra: la muestra de saliva para el ensayo de virus latentes, 3 minutos, tope
  de «2–3 min» con el rollo de algodón en la boca (Mehta et al. 2017). Sigue en `demo`: el artículo
  es un estudio, no el protocolo operativo. Las otras 33 siguen sin fuente; lo más cercano que se
  encontró era de otra acción (las conferencias psicológicas de 15 minutos, el cuestionario semanal
  de 5 a 15 minutos, los 30 minutos de preparar una comida) y no se aplicó. Ninguna fuente da
  contraindicaciones.
- **Escala hedónica, rótulos 2 a 8**: NTRS 19820015234, el informe de Ahmed de 1981 en JSC sobre
  alimentos de alta densidad, escribe los nueve rótulos tal como la usaba el panel del laboratorio
  de alimentos de JSC («8-Like Very Much»; el 5, «Neither Like or Dislike», con «or»). Los extremos
  siguen siendo los de NASA en 2025 (Douglas et al.); los intermedios son los de 1981, no los de la
  papeleta de hoy, que sigue sin leerse. No cambia rango, criterio ni puntuación.
- **MMEA**, fechado: la noticia de NASA es del 1 de julio de 2026 (`bancos-de-prueba.md`). **La
  fecha del listado de huecos del Roadmap** sigue sin escribirse en la fuente; el IRP Rev T anota
  la última revisión del contenido del Roadmap el 5/7/2025, y queda en la ficha sin adoptarse.

**Cruces entre piezas hechas a la vez**, resueltos al juntarlas: dos unidades leyeron a la vez
Mehta et al. 2017 y abrieron una ficha cada una; quedó una, con las dos lecturas en su nota, que
citan la regla de la orina y la contramedida de la saliva. Tres unidades abrieron un §5.29 en
`compliance/hmi-state-of-the-art.md`; quedan §5.29 (alcance), §5.30 (freno) y §5.31 (nombres).

**Cierre medido** (2026-10-20): suite entera del backend en verde (3148 pruebas: 3147 en la pasada completa
más la que prohíbe llamar validada a una escala en los textos, que fallaba desde `b300fd8` por
una frase de esta misma página, se corrigió aquí y se pasó aparte); `ruff`, `mypy --strict`, `npm test` (662) y `tsc` limpios; veredicto del
motor —nivel global, puntuación, nivel y trayectoria por dominio, alertas, recomendaciones y banda
inferida de los nueve escenarios para los cuatro tripulantes— idéntico entre `b300fd8` y `ef33b0b`
(mismo hash de los 36 casos); MMASH en verde (33 pruebas `external`: falsa alarma y sensibilidad
juntas); las 35 campañas de mutantes de la ronda, 331 de 331 cazados; las pruebas de la copia de
Polaris dan lo mismo que antes del cambio del temporal (115 verdes, 57 rojas por enlaces simbólicos
de Windows y ganchos no copiados, 19 saltadas, de 191; `polaris/PRUEBAS.md` regenerado con su
leyenda nueva). Pasada visual con Chromium sin cabeza sobre la interfaz compilada que sirve el
backend: nombres en español en todas las frases, gravedad en la cabecera, freno HALT en la franja,
PVT y alcance plegado; las capturas quedan fuera del repositorio. El instalador no se reconstruyó
en esta ronda.

**Lo que se vio y queda dicho:**

- El prevuelo también es en Tierra y sigue mostrando la gravedad de la misión: la decisión cubre
  solo el posvuelo. Con la reproducción de Inspiration4 (vuelo de 3 días) la fase sale del
  calendario configurado de 180 días: entre el día 3 y el 180 diría «fase estable ·
  microgravedad» con la tripulación ya en Tierra (leído en el código, no visto en pantalla).
- `trigger_display` y `followup_checks_display` ya eran texto para la pantalla y pasan a español
  sin campo `_es` aparte, a diferencia de los `display` que conservan el inglés.
- Un hueso cortado por un lado no se detecta (el corte solo se mide de arriba abajo): su zona cae
  sobre el centro del trozo visible.
- `diary._reference_text` trata medio rango como «sin rango», y el catálogo, desde esta ronda,
  como rango (afecta a `fluid-intake-24h`).
- **Al volver de la consola de Tierra a la de tripulación por la pestaña, cinco paneles quedan
  vacíos** (diario, comida, descriptivos, PVT y dolor): el navegador lanza sus peticiones al
  remontar la consola, pero no llegan al servidor (reproducido dos veces con Chromium sin cabeza
  sobre la interfaz compilada; en la primera carga están llenos). Anterior a esta ronda; sin
  corregir. La pasada visual recarga la página para cada consola en vez de cambiar de pestaña.

### Rediseño pictográfico (2026-10-20 y 21): la forma junto a la palabra

El usuario pidió (2026-10-20) «un rediseño del frontend lo más pictográfico posible» y decidió, de
las cuatro opciones recomendadas: pictograma junto a cada palabra y nunca en su lugar (la única base
que el repositorio tiene es F.5.10 e, tal como la lee el estado del arte: el color siempre con
palabra y forma; **ningún texto de la norma habla de iconos y no se cita ninguno**); SVG propio de
EMMA, geométrico, de trazo, 24×24 y `currentColor`, sin biblioteca npm (sin SOUP ni `NOTICE`
nuevos, CSP intacta); los glifos de texto de la interfaz (○ ◇ △ ■ niveles, ● ◐ ▷ procedencia, ◌
ausente, ⊘ ✕ no disponible y fallo…) pasan a SVG con la misma forma y el mismo significado —IBM
Plex, la fuente que viaja en el paquete, no los cubre y cada sistema los dibujaba con otra fuente—;
y una silueta corporal 2D en el resumen de la consola de tripulación. Lo contrasta la
especificación §10 (modo anatómico CUERPO → ÓRGANO → estado, «render 3D opcional»): la silueta es
cliente del mismo `/api/anatomy/state`, no una fuente de verdad aparte. Un núcleo y once unidades en
paralelo, fusionadas una a una, más una limpieza:

**Núcleo** (`frontend/src/icons/`): registro por áreas con tipo (`PictogramName`), `<Pictogram>`
(`<svg class="pictogram" … aria-hidden data-pictogram="…">`, sin `<title>`), `<Mark>` como única
pieza para pintar un estado (pictograma + palabra en su clase de color), `lib/marks.ts` para las
tablas «clave de la API → dibujo + color», y los sets transversales: 24 formas, procedencia y
entornos de evidencia, 9 dominios y 5 peligros RIDGE, 22 familias que cubren los 88 indicadores del
catálogo (`lib/indicatorFamily.ts`, con paridad vigilada por `backend/tests/test_indicator_families.py`).
Las insignias comunes (`LevelBadge`, `QualityBadge`, `ObservationTypeBadge`) migraron ahí. Lo que
comprueba `icons/pictograms.test.ts`: nombres por el dibujo y nunca por el significado (ni nivel, ni
fase, ni color), primitivas acotadas, sin color propio, un dibujo por nombre entre todos los sets,
ningún `<svg` fuera de `icons/` salvo el calibre de la ecografía y la silueta, y que todo nombre
usado exista. Reglas y tabla de formas en `compliance/hmi-state-of-the-art.md` §5.32.

**Unidades** (cada una con su apartado §5.32.n, sus pruebas con `data-pictogram` junto a la palabra
y, donde el vocabulario viene del backend, una prueba de paridad):

- **Alertas y crónica (P1).** Cada alerta lleva el pictograma de su dominio junto a la insignia
  de nivel, y cada estado declarado por una persona (detectada / en arreglo / resuelta, suprimida /
  inhibida, reconocida) lleva el suyo junto a la palabra de siempre. En «qué cambió», la flecha
  arriba/abajo de F.4.3.1 d sale de un campo estructurado que ahora expone el backend (`direction`:
  dos líneas en `analysis/explain.py` que no cambian ninguna frase ni veredicto), nunca de la frase,
  y lleva el color del nivel solo en la flecha. La crónica tiene un pictograma por tipo de hecho y
  por etapa de §10, leídos de `app/timeline.py` por la prueba de paridad. Esta unidad se cortó a
  medianoche por el límite de sesión de la API y se reanudó por la mañana desde su worktree.

- **Misión, calidad y vigilancia (P2).** Franja de fases con un pictograma por fase y el disco
  lleno en la actual; eventos declarados, perfil de misión y sus seis aspectos, capacidades de
  vigilancia con su dibujo y la señal de su causa, fuentes de lectura con un dibujo por canal
  (paridad con `data_quality.py`), proyecciones y calidad del dato con la familia junto a cada
  indicador, y el entorno de la evidencia con su dibujo. La gravedad solo lleva dibujo cuando el
  backend la fija (posvuelo, en Tierra): en vuelo es texto libre de configuración y va sola, para
  que la forma no contradiga a la palabra.
- **Silueta y anatomía (P3).** La consola de tripulación enseña en «Dominios», junto a la rejilla,
  una silueta 2D de frente (`icons/Silhouette.tsx`) con una zona por región de `anatomy.py` y, sobre
  cada una, el pictograma de su dominio y el nivel con palabra, forma y color; inmune y radiación,
  sin órgano, van al pie. Pulsar una región la abre en «Cuerpo». No es imagen del tripulante ni
  diagnóstico; Tierra no la monta (densidad y retardo). Las tarjetas de dominio de ambas consolas,
  la lista de regiones, la cadena y la figura del esqueleto pasan sus glifos a pictogramas.
- **Hábitat (P4).** Cada parámetro de cabina, módulo, sistema, clase de hipótesis y ubicación de
  tripulante lleva su pictograma junto a la palabra del backend; los glifos del panel (✓ ☐ ↻ – △ ◇ ◌
  ⊘ ✗ ▌) pasan a pictograma con el mismo dibujo y color (`limitMark`, `ABSENT_MARK`). Paridad con
  `environment/habitat.py` y los JSON de módulos y sistemas (`tests/test_habitat_pictograms.py`). Lo
  pasado —historial, excursiones cerradas— lleva la forma de la clase sin su color.
- **Asesor y evidencia (P5).** Tarjeta de recomendación, recursos, seguimiento y fichas de fuente:
  urgencia, dominio, decisión, respaldo, eje RIDGE, estado de recursos y de la respuesta previa; las
  27 claves del vocabulario de recursos en 19 dibujos de familia; los 14 niveles de evidencia en 7
  dibujos por diseño del estudio y las 12 clases de documento en 8, con paridad contra `tier.py` y
  `registry.py`; entorno y población. Un valor que la interfaz no conoce sale con su clave y el
  dibujo de «desconocido».
- **Consola de Tierra (P6).** Las tablas de estado de `ground/` (marco de NASA, huecos del Roadmap,
  alcance de lectura, riesgos, coste de medir, copia de Polaris) con una sola pieza de pintado
  (`StateWord`); las clases de medida y los valores de dimensión de `cost.py` y los treinta tipos de
  asiento del ledger ganan un dibujo cada uno, con paridad probada; dominios, RIDGE e indicadores
  llevan su dibujo en riesgos, marco, proyecciones, recuperación, coste y gráficas. Dos desvíos
  documentados: los estados de Polaris (enchufe) y la marca única de desconocido.
- **Diario, comida y descriptivos (P7).** La familia junto al nombre de cada indicador y el dominio
  junto a su palabra; un cursor en cada extremo de pista para las anclas de las escalas propias
  (posición en el rango, sin caras: siguen marcadas como decisión de diseño sin validar) y una
  escalera para la escala hedónica junto a sus rótulos leídos y a la regla del criterio; la
  valoración por debajo del criterio lleva el triángulo común sin color de aviso. Visto en captura
  que una escalera de nueve peldaños no se lee a 1 em: silueta de tres, y el número lo dice el texto.
- **PVT y radiación (P8).** La PVT gana forma para el respaldo de cada parámetro (hoja escrita,
  lápiz, libro leído), para cómo queda su valor frente a lo publicado (=, ≠, ≈, –, ⊘) y para la fase
  de la sesión (□ espera, ■ marca, ○ abandonada, ✓ resultado); la marca «= / ≠» de cada valor
  publicado sigue siendo la del backend, tal cual. La radiación lleva tres dibujos distintos para
  aguda (rayos), misión (trébol) y carrera (barra con tope), y una casa junto a «refugio». Ninguna
  cifra que puntúa cambia.
- **Dolor y volúmenes (P9).** Un dibujo propio por carácter del dolor junto a su palabra, la
  intensidad con el rayo de su familia, el cambio por zona triángulo/igual/punto, la nota con pluma
  o micrófono según su origen; nada del dolor va en rojo ni amarillo. En volúmenes, gantry e imán
  junto a CT/RM, una forma por fase de contraste, y los significados de F.5-1 con su forma en
  densidad, cadena vertebral y comparación. Paridad con `CHARACTERS` y `PHASES`
  (`tests/test_pain_volume_pictograms.py`).
- **Ecografía e informes (P10).** Protocolo, medida, signo anotado, clase de informe, veredicto de
  identidad y estado de cifra leída con su pictograma; el borrador del modelo local se distingue con
  una hoja a trazos antes y después de firmarse, y un hallazgo o una medida nunca la llevan
  (invariante 6). Paridad de protocolos en `tests/test_imaging_protocol_pictograms.py`. Sin
  pictograma a propósito lo que hoy no se enseña con palabra (evidencia del método, desidentificación
  `verified`).
- **Armazón y franja (P11).** Pestañas (casco / globo), selector de tripulante, cambio de escenario
  (el dibujo del dominio o familia que perturba cada escenario), almacén vacío y datos reales, y la
  franja común entera: reloj, modo (onda / onda y punto / cohete), vigilancia, campana con las
  formas de nivel en W/C/A, globo del retardo, candado del registro, mástil de la red con puerta
  abierta o con el triángulo amarillo del modo seguro y del freno HALT.

- **Limpieza (P12).** Lo que usan dos o más áreas vive en `icons/sets/common.ts` (25 dibujos) y
  una prueba lo exige; una sola pieza de pintado (`MarkOf`) sustituye a las tres que habían nacido
  en paralelo; `MISSING_MARK` para el dato ausente; el CO de cabina gana dibujo propio (compartía
  la llama del dolor quemante); `ring-dot` queda como única marca de «elegido/actual» y `dot-filled`
  solo para MEDIDO; las ventanas ecográficas pasan a abanico (a 12 px no se distinguían del anillo
  con punto); un barrido (`lib/glyphs.test.ts`) prohíbe cualquier carácter de símbolo en el fuente
  fuera de `icons/`, con dos excepciones declaradas (© de la licencia y «≤ ≥» de un límite con una
  sola cota). La regla c) de §5.32 se reescribe para que case con la decisión (la forma acompaña a
  la palabra en todo estado con significado propio; nunca sustituye; nada decorativo). Resultado:
  239 pictogramas en 20 sets; los que a 12 px se leen como mancha (legibles a 14-16 px, donde se
  usan) están listados en §5.32.12.

**Cruces entre unidades, resueltos al fusionar:** la prueba de unicidad del registro cazó, en nueve
fusiones, veintidós nombres dibujados por dos unidades a la vez (`equals`, `pin`, `flame`, `flask`,
`house`, `star-four`, `pen`, `hourglass`, `bell`, `bulb`, `magnifier`, `notebook`, `probe-arcs`,
`sheet-lines`, `calendar`, `pencil`, `helmet`…): en cada caso queda el dibujo de la unidad fusionada
antes y el otro set lo cita por su nombre. Dos de ellos nombran cosas distintas con el mismo dibujo
(`flame`: dolor quemante y monóxido de carbono) y los decide la limpieza.

**Lo que se vio y queda dicho:** los `<option>` de los selectores no admiten SVG y siguen solo con
palabra (el pictograma va junto a la opción elegida). Con el freno HALT puesto, la celda «Red» de la
franja ensancha y empuja dos celdas a una segunda fila. Con datos sembrados en un proceso que ya
tenía otros, `/api/status` tarda decenas de segundos y las medidas de una ecografía otros tantos
(verificación del ledger): no es del frontend.

**Cierre medido** (2026-10-21, `main` 31c82ef): `npm test` 991 pruebas en verde (662 antes del rediseño), `tsc`
limpio y `npm run build` entero (con el visor de Polaris) en verde; suite entera del backend en verde con las once
unidades (3157 pruebas, nueve de ellas de paridad nuevas) y, tras la limpieza, las 233 que leen el frontend o
vigilan la paridad, `ruff` y `mypy --strict` limpios; veredicto del motor idéntico al de `b300fd8` en los 36 casos
(las dos líneas de `analysis/explain.py` solo exponen un campo); pasada visual con Chromium sin cabeza sobre la
interfaz compilada que sirve el backend, las dos consolas cerradas y abiertas en `cardiovascular-deconditioning`
y `co2-fatigue`, sin ningún error de página; una hoja de contactos de los 239 pictogramas a 12, 16 y 24 px. El
guion de capturas vive fuera del repositorio (usa el Playwright del Python del sistema, que no es ninguno de los
cuatro entornos del proyecto): adoptarlo es una decisión pendiente. El instalador, reconstruido desde el venv limpio (`desktop/npm run dist`, 2026-10-21 13:36, 321 MB):
su backend congelado sirve la interfaz nueva y las rutas de la decimotercera ronda (`/api/indicators` con
`display_es` y base `null` sin rango, `halt.notice` en `/api/safe-mode`, el `marker_display` de la PVT).

### Segunda pasada pictográfica (2026-10-21): la interfaz vistosa

El usuario pidió (2026-10-21) más pictogramas «para hacer vistoso el frontend» y que se buscaran
referencias de código abierto. Decidió que entran todos los huecos que la primera pasada dejó sin
forma —títulos de panel y plegables, botones y mandos, cabeceras de tabla y etiquetas, estados de
carga, vacío y error— y toda la jerarquía visual (tamaños por contexto, fichas con cifra, medidores
neutros, silueta recalcada); que la regla c) de §5.32, regla propia de EMMA y no de la Space Apps,
se reescribe: el pictograma acompaña a cada título, plegable, mando y cabecera como signo de qué es
cada cosa, **un dibujo por concepto en todo el sistema**, y siguen prohibidos el color decorativo,
el dibujo sin palabra, dos dibujos para un concepto y el parpadeo fuera de crítico; y que las
fuentes abiertas leídas (Health Icons CC0, Lucide ISC, Tabler MIT, Open MCT de la NASA Apache-2.0,
la silueta CC0 de Wikimedia Commons) sirven solo como vocabulario y referencia de proporción: todo
se redibuja en primitivas propias, sin `NOTICE` ni SOUP nuevos. Nada de la pasada toca niveles,
umbrales ni alertas, y la palabra sigue siendo la del backend o un rótulo que ya existía. Un núcleo,
once unidades en paralelo fusionadas una a una y una limpieza; detalle en
`compliance/hmi-state-of-the-art.md` §5.33.

**Núcleo.** `lib/uiMarks.ts` es la tabla cerrada concepto → dibujo (títulos, plegables, mandos y
cabeceras ponen el concepto, no el dibujo), con los sinónimos declarados; 20 dibujos nuevos en
`icons/sets/ui.ts`, 25 subidos a `common` y 5 retirados por casi iguales (tres hojas escritas →
`sheet-lines`, `equals-slash` → `not-equal`, `power` → `gear`). Piezas que exigen la palabra:
`PanelTitle`, `Fold`, `Command`, `Th`, `FieldLabel`, `StatTile` (ficha con cifra; sin cifra exige
estado, nunca cero) y `Meter` (medidor neutro; fuera de escala se señala y no se dibuja, patrón de
Open MCT). Cinco marcas de estado en `lib/marks.ts`: ausente, no disponible, fallo, cargando y
hecho. El dato caducado lleva además cursiva —tercera señal tras color y forma, patrón de Open MCT—
con la itálica de IBM Plex, que ahora viaja en el paquete. La franja pasa a 0,875 rem, la insignia
del resumen y los dominios crecen, y sale la última mayúscula forzada (F.5.1 h).

**Unidades:**

- **Alertas y crónica (V1).** Títulos, plegables, mandos y las doce claves del detalle con su
  dibujo; el estado que deja cada mando comparte dibujo con el mando (Suprimir / Suprimida);
  nombre con familia en base, concordancia y dependencias; sin efemérides, anillo cian.
- **Resumen, misión y calidad (V2).** Fichas con cifra bajo el resumen (día de misión, retardo,
  alertas, dosis de carrera, lecturas analizadas): lo ausente o caducado se marca, nunca sale como
  cero; títulos, plegables, mandos, rótulos y cabeceras de misión, vigilancia y calidad.
- **Silueta y anatomía (V3).** Silueta recalcada sobre la plantilla CC0 de Wikimedia Commons
  (citada; el SVG fuente no entra en el repositorio): un solo trazo cerrado de 38 nodos con la mitad
  derecha en espejo, órganos con el rasgo que los hace reconocibles (cisura del cerebro, iris,
  vértebras, asa intestinal, cóndilos del fémur) y etiquetas colocadas a la medida del contorno en
  su altura, para que ninguna tape una mano. Cada título, plegable y nombre del área lleva su signo.
- **Hábitat (V4).** Medidor neutro donde el propio límite fija la escala sin inventarla (CO2,
  presión, formaldehído, humedad: [0, 2× límite], banda = rango permitido); fuera de escala, la
  marca y la palabra de la fila; Confirmada / Descartada con el dibujo del mando que la firmó.
- **Asesor y evidencia (V5).** Títulos, plegables, mandos y claves; cada campo vacío de una ficha
  de fuente dice por qué lo está (sin verificar, no aplica, fuera del enumerado): antes un campo que
  el registro sí había leído podía salir «sin verificar».
- **Consola de Tierra (V6).** Fichas «Tierra tiene datos hasta / A bordo ya van por» (cursiva y
  cian si caduca); diecinueve títulos, rótulos, cabeceras y riesgos con el dibujo de su dominio;
  los fallos, con cruz roja en vez de anillo gris.
- **Diario, comida y descriptivos (V7).** Sin dibujos nuevos: todo del vocabulario común; carga,
  vacío y caducado con sus marcas. Al cambiar de tripulante ya no quedan en pantalla los datos del
  anterior (con la cursiva nueva se habrían leído como datos caducados del nuevo).
- **PVT y radiación (V8).** Cronómetro en la PVT y signo en cada cabecera (el respaldo con los
  pilares de «base» y no con el libro: no toda fila tiene fuente leída); el registro solo dice
  «vacío» cuando se ha leído. Medidor de la dosis de carrera contra el límite que da el backend, sin
  banda inventada; el dosímetro usa la misma pieza y su tanto por ciento ya no se recorta a 100.
- **Dolor y volúmenes (V9).** Títulos, mandos (Frente / Espalda), cabeceras de las cuatro tablas de
  volúmenes; la vista 3D no disponible, en gris con forma; el error del visor, con cruz roja.
- **Ecografía e informes (V10).** Las tres listas decían «Sin estudios» mientras la petición seguía
  en curso (en Tierra, varios segundos con fantomas ya registrados): ahora dicen «Cargando…». Un no
  del backend lleva triángulo y su motivo; una petición caída, cruz. «Rechazado» lleva el dibujo
  del mando «rechazar»; las hojas de cada clase de informe salen de la misma hoja base; un dibujo
  nuevo para cerrar el contorno. El borrador del modelo local conserva su hoja a trazos en el título
  y en el mando que lo pide (invariante 6).
- **Armazón y franja (V11).** Cada rótulo de la franja con su signo; el retardo con Tierra pasa del
  globo (que es Tierra y su consola) a las ondas de señal; «inhibidas» llevaba la campana tachada de
  «suprimidas» y ahora la suya; modo seguro, aviso HALT y «Acerca de» como plegables; los errores
  del armazón, con cruz.
- **Limpieza (V12).** Un dibujo por concepto donde había dos: «reducida» con la marca de su causa
  en la franja y en el panel, la línea base y la integridad del registro con el dibujo de su
  concepto, los registros vacíos de a bordo con una sola marca y quien no consta con la suya. Nuevos
  conceptos `chosen` (pieza `Chosen`, que reserva el hueco del anillo: la fila ya no se mueve al
  elegir) y `measured`. Subieron al núcleo la marca de rechazo, la de vacío, la de fuera de escala y
  la pieza `Loading` (doce copias del párrafo «Cargando…»); `Fold` admite una marca de estado como
  signo, `<Th>` no deja el dibujo solo encima de su palabra, `Meter` elige su flecha y la banda
  enseña sus extremos. Una prueba nueva caza dibujos casi iguales y cazó uno (la tableta de la PVT
  frente al aislamiento del RIDGE, redibujada).

**El fallo de la pestaña, diagnosticado:** al volver de Tierra a tripulación cinco paneles se veían
vacíos. No se perdía nada: la consola se remonta y lanza unas treinta peticiones a la vez, el
navegador abre seis conexiones por servidor y cada respuesta tarda segundos, así que esos paneles
recibían sus datos entre 5 y 20 s después, y mientras tanto no decían «Cargando…». Ahora lo dicen, y
el guion de capturas espera las peticiones en vuelo en lugar de dar la página por cargada.

**Lo que queda dicho:** con el texto del navegador muy agrandado, una etiqueta de la silueta puede
tocar el brazo (por debajo de 720 px no aplica); el paso de confirmar el cambio de escenario ocupa
tres renglones de la barra; la hoja a trazos del borrador se lee a 14 px como una columna punteada,
y redibujarla cambia la marca de la invariante 6 (decisión abajo).

**Cierre medido:** (2026-10-21, `main` 10fb68d): `npm test` 1150 pruebas en verde (991 tras la primera pasada), `tsc`
limpio y `npm run build` entero (con el visor de Polaris) en verde; suite entera del backend en verde con las once
unidades (3157 pruebas: la pasada no toca Python) y, tras la limpieza, las 187 que leen el frontend o vigilan la
paridad; veredicto del motor idéntico al de la base en los 36 casos (9 escenarios × 4 tripulantes: nivel global,
dominios, alertas, recomendaciones y banda inferida); pasada visual con Chromium sin cabeza sobre la interfaz
compilada que sirve el backend, las dos consolas cerradas y abiertas y la vuelta de Tierra a tripulación por la
pestaña, en `cardiovascular-deconditioning` y `co2-fatigue`, sin ningún error de página; una hoja de contactos de
los 270 pictogramas en 21 conjuntos a 12, 16, 24 y 64 px. El instalador, reconstruido desde el venv limpio
(`desktop/npm run dist`, 2026-10-21 17:34, 321 MB): su backend congelado arranca y sirve la interfaz nueva.

### Decimocuarta ronda (2026-10-21): más del contexto de producto

El usuario pidió (2026-10-21) «sigue añadiendo cosas del contexto». Tres lecturas enteras de la
especificación, la base de conocimiento, la conversación de ideación y sus anexos, contrastadas con
este README y con el código, dieron lo que quedaba: los nueve criterios de §14 ya se cumplían, y lo
pendiente eran piezas que la KB y la conversación proponen y EMMA no enseñaba aunque ya tenía los
datos, lecturas que desbloquean pendientes y remates. Decisiones del usuario del mismo día: un
rechazo del backend (4xx) va en amarillo con triángulo y una petición caída (5xx, sin red) en rojo
con cruz, en toda la interfaz; las comunicaciones declaradas caídas solo se dicen (franja, `/comms`,
Tierra), sin tocar recomendaciones ni `notify_ground`; la banda ósea inferida se corta en el
regreso; cada contramedida lleva su familia, de un vocabulario cerrado. Diecisiete unidades en
paralelo, fusionadas una a una; detalle de cada una en `compliance/hmi-state-of-the-art.md` §5.34.
Al fusionar, cuatro paneles nuevos (biblioteca, bancos de prueba, línea base, momento pasado de la
cadena) traían su propia regla de rechazo o fallo y pasaron a la común (`requestOutcome`).

**Lo que se ve nuevo:**

- **Biblioteca de contramedidas por RIDGE, con familia (C1; KB §15 P1 y §10, especificación §8).**
  La biblioteca entera (40 entradas) se lee en las dos consolas, agrupada por peligro RIDGE
  (radiación 4, aislamiento 4, distancia 2, gravedad 17, entorno 13), con respaldo, tiempo de
  tripulación (con su fuente al lado), ventana de seguimiento, recursos y familia. Cada entrada
  lleva `family` de un vocabulario cerrado tomado de la conversación y de KB §7: física o de masa
  (3), operacional (8) y comprobación o vigilancia (29), con el criterio escrito; dos criterios son
  de EMMA y se dicen (el ejercicio es «física» por carga mecánica; trasladarse al módulo blindado es
  operacional y el refugio con masa, física). La farmacológica queda fuera del alcance de EMMA: una
  entrada así no carga, y hoy no hay ninguna. Cambia `rules_version` por el fichero de datos; el
  veredicto es idéntico y una prueba fija que la familia no cambia lo recomendado.
- **Perfil de línea base (C2; especificación §3 `baseline_profile`, §10 «¿respecto a qué
  baseline?»).** `GET /api/baseline-profile` y el panel «Línea base personal» (tripulación; Tierra
  con el corte del retardo) enseñan, por indicador y estado fisiológico, la base contra la que el
  motor juzgó la última lectura: mediana y dispersión (desviación absoluta mediana × 1,4826),
  lecturas de las 100 que la establecen, ventana de 14 días que acaba 12 h antes, si las lecturas
  son del estado o de su familia, el límite de peligro de ese estado y, mientras aprende, contra qué
  se juzga. Es base móvil: la de prevuelo existe en el motor pero el estado no la usa, y se dice. El
  perfil lee las desviaciones del motor sin recalcular nada y no escribe en el ledger. Al hacerlo
  salieron dos hallazgos del motor, que quedan para decidir (abajo).
- **Cadena anatómica con riesgo, hábitat y tiempo (C3; KB §11.1, conversación «ASTRONAUT TWIN ↔
  HABITAT TWIN» y «Pre-flight → … → Recovery»).** `GET /api/anatomy/state` da en cada dominio de
  cada región el paso RIESGO (RIDGE, ficha del riesgo con su clase de documento, incertidumbre no
  cuantificada), el contexto externo de cada región (el mismo constructor que el de las alertas:
  anclado en el inicio de su alerta o, sin alerta, en el instante del estado, «correlación temporal,
  no causa») y los momentos de la misión (cambios de fase, regreso y cada día R+). Pedida con
  `until`, la cadena es un recálculo «con las reglas de hoy, sin asiento», con los eventos solares y
  el tiempo de luz de hoy, y se dice. La consola lo pinta en los eslabones «Riesgo» y «Contexto
  externo» y con un selector «Momento»; en un momento pasado los niveles van sin insignia vigente y
  no se ofrece adoptar nada.
- **Sistemas declarados degradados como causa común (C4; KB §6).** Con dos o más tripulantes fuera
  de nominal, un sistema de soporte vital declarado degradado o fuera de servicio en la ventana entra
  en las hipótesis de tripulación como «coincidencia temporal, no causa», detrás de las excursiones
  medidas. Qué sistemas son de soporte vital sale de OCHMO-TB-002 Rev B (aire, presión, térmico y
  humedad, contaminantes y agua; no iluminación, energía ni comunicaciones). Ninguna fuente leída
  dice qué sistema explica qué dominio, y la hipótesis lo dice. Sin declaraciones, la salida es la de
  antes.
- **Enlace con Tierra declarado caído (C5; KB §2.1).** La declaración de «Comunicaciones:
  degradado / fuera de servicio», que ya se podía firmar y nadie leía, la lee `systems.earth_link`
  y se dice en `/api/comms`, `/api/status` (Tierra, hasta su corte), la franja y la ficha «Tierra
  tiene datos hasta», con la marca del estado del panel de sistemas. Solo texto: el retardo sigue
  saliendo de las efemérides y nada que decida la lee. En la demo, Tierra sigue «recibiendo» aunque
  el enlace esté declarado caído: no hay enlace real que cortar.
- **Detalle de alerta: qué cuesta comprobar, en qué paso va y cuánto cambió (C6; KB §9 y §10).**
  Cada comprobación lleva su coste de medir (tiempo de la acción y, por indicador, clase, tiempo,
  dónde se procesa, cuándo llega el resultado y consumibles, de `ingest/cost.py`; lo «sin
  clasificar» se dice; no se reordenan, porque ordenar por coste sería una decisión clínica). La
  alerta enseña por qué paso del flujo SENSE → … → FOLLOW-UP va, con la convención de las hipótesis
  (pieza común `FlowSteps`) y los estados leídos del reconocimiento, la adopción y el seguimiento
  firmados. Y cada cambio da su cambio relativo frente a la mediana personal («HRV −14 %», de la
  conversación), solo en escala de razón; en ordinales, °C, diferencias con signo, densidad, dosis
  acumulada, mediana 0 o rango poblacional dice por qué no.
- **Radiación: proyección, tipos y límites a corto plazo (C7; KB §7).** La dosis de misión se
  proyecta al fin configurado (PREDICHA, «supone tasa constante: no prevé eventos solares») y, con
  dosis previa declarada, la carrera proyectada frente a los 600 mSv de [V1 4030], cuya
  justificación incluye «the projected exposure for an upcoming mission»; no alimenta la dosis
  acumulada, niveles ni alertas (prueba explícita). La horquilla por tipo de radiación usa los Q de
  atrapada (1,83) y GCR (2,74) medidos con TEPC en el SLS-1, ahora con ficha leída en PubMed
  (`badhwar-1992-sls1-tepc`); es INFERIDA y no un intervalo de confianza. Los límites de 30 días y
  1 año de la Tabla 4.8-1 de NASA-STD-3001 Vol 1 se muestran en su unidad (mGy-Eq, mGy en SNC), sin
  convertir ni comparar: EMMA no tiene dosis por órgano.
- **Perfiles de misión sin huecos y con su entorno de radiación (C8).** Los seis aspectos sin
  verificar (evacuación desde la estación, la Luna y Marte; retardo, reabastecimiento y duración
  lunares) llevan frase literal de documentos de la NASA, con sus discrepancias: el tiempo de luz
  Tierra-Luna (1,3 s) se separa de la latencia de comunicaciones (3-14 s), y el retardo con Marte
  suma la cifra de 22 minutos de un memorando técnico. Cada perfil gana un séptimo aspecto, el
  entorno de radiación (dentro o fuera de la magnetosfera, ciclo solar), con la nota de EMMA de que
  la tasa medida mezcla componentes. Sigue siendo descriptivo; el perfil lunar sigue sin cuerpo de
  efemérides.
- **Bancos de prueba y las dos validaciones (C9; `bancos-de-prueba.md`, KB §3 y §3.1).** `GET
  /api/testbeds` y un panel de Tierra: siete bancos (HERA, :envihab, Antártida, NSRL, CHAPEA, MMEA,
  ISS) con lo que reproduce cada uno (frase literal de su página, releída), lo que deja fuera (dicho
  por la fuente o deducido por EMMA, y se dice cuál) y el `evidence_context` que llevaría un dato
  suyo, sin ampliar el enumerado; la escalera Tierra → ISS → Luna → Marte. La validación científica
  de EMMA es «en parte» (MMASH en Tierra, no fisiología espacial; Inspiration4 sin muestras en vuelo;
  las cifras, en `compliance/external-validation.md`); la operacional, «ninguna», compuesta por el
  cargador desde la lista vacía. La lectura corrigió que «Step 1, Earth» no dice que ningún sitio
  reproduzca Marte entero (lo dice la KB).
- **Marco NASA: MEDPRAT y ATCS (C10; KB §15 P0, especificación §16-§17).** Leídos el póster de
  MEDPRAT, tres resúmenes de NTRS de 2023, el resumen del ATCS (Boeing, 2006) y OCHMO-TB-002 Rev B;
  `/api/framework` gana los bloques `medprat` y `habitat-systems`, con fecha de lectura por fuente.
  MEDPRAT/IMPACT es la línea que sucede al IMM («will soon replace»), no un complemento; que la
  sustitución ya haya ocurrido no se encontró. EMMA no estima frecuencias ni consecuencias de
  eventos médicos. El vocabulario de sistemas deja de decir «sin respaldo bibliográfico» y dice en
  qué difiere su partición. La lectura corrigió una atribución: la cadena SENSE → … → RECOVER es de
  la conversación de ideación, no de la KB §6.
- **Matriz de riesgos (C11; conversación «Hazard → efecto → variable → dataset → detección →
  contramedida»).** `GET /api/risks` da a cada riesgo su fila: el efecto (relevancia del riesgo del
  HRP citado), los datos separados en conjuntos de datos (OSD-288, OSD-569, OSD-343) y documentos,
  la regla de detección leída del motor en cada consulta (constantes de `analysis/` y preguntas a
  `RiskEngine` para el aislamiento, el evento solar y la dosis), con pruebas que fallan si lo
  publicado diverge, y las contramedidas una a una (el refugio, por evento). Tierra la enseña como
  tabla, con la regla plegada.
- **Coste de medir: «hoy se sabe después» (C12; conversación).** Las 50 medidas que hoy requieren
  retorno o análisis en Tierra, al lado de lo que la fuente de cada perfil dice del reabastecimiento
  y del regreso (lo que C8 dejó leído); donde no dice nada, «EMMA no tiene fuente». Los tres
  calculados enlazan sus entradas: NLR y BUN/creatinina heredan de sus analitos; la dosis
  acumulada no (llega registrada). Leído: el recuento de leucocitos tomado en vuelo iba en tubo EDTA
  (Crucian et al. 2015); en el protocolo de 2025 el hemograma se toma solo antes y después del vuelo
  porque no se mide en muestra congelada (Hardy et al. 2025). Sin clasificar: de 47 a 38 pares.
- **Banda ósea inferida cortada en el regreso (C13).** En posvuelo la banda se detiene en el día de
  regreso, no proyecta y lo dice. La frase sobre la recuperación sale de OCHMO-MTB-013 (el hueso
  cortical se recupera bien y el trabecular puede no recuperarse; DXA a los 6 meses y a 1, 2 y 3
  años); EMMA no estima la recuperación porque la ficha no da tasa.
- **Remates de interfaz (C14).** La decisión 1 en toda la interfaz desde una sola función
  (`requestOutcome`): antes el mismo 422 salía amarillo en el asesor y rojo en el modo seguro, y
  «Sin datos» iba en cian como un dato ausente. El recuento vacío de descriptivos y comida pasa a la
  marca de registro vacío; el aviso del freno HALT ocupa una línea; los rótulos de la silueta se
  apartan del brazo en `em`; la confirmación del cambio de escenario deja de ocupar tres renglones.
- **Remates de backend y documentación (C15).** Un rango con un solo extremo dice «desde X» /
  «hasta Y» en el diario; la convención `display` / `display_es` / `*_display` queda escrita; los
  apartados de interfaz que decían «sin ver» dicen lo visto; las 191 pruebas de Polaris constan
  medidas (115/57/19); los catorce módulos que llamaban a Polaris sin fila de clasificación la tienen
  (B; C los cuatro del visor 3D).
- **Papeleta hedónica y personas (C16).** La papeleta que NASA usa hoy no está publicada (ISS
  Research Explorer, Douglas et al. 2025 sin material suplementario, NTRS). Entran junto a los
  rótulos, sin cambiarlos, la leyenda de la figura 1 de Douglas et al. 2025 y un panel de catadores
  de JSC de 2015, que dicen «nor» en el punto 5. `personas-y-organizaciones.md` cierra el hueco de
  Orion (Kerry Lee y Jessica Vos, cargo de 2016) y TRISH, y añade los autores y organizaciones de
  las fichas registradas, cada uno con su ficha.
- **Hueso cortado por un lado (C17).** Un hueso se da por cortado si llega a cualquiera de los seis
  bordes del estudio, no solo arriba o abajo, con los extremos leídos con el afín entero (la
  revisión cazó que leyendo solo la diagonal un húmero cortado por el lado se escondía en una
  rejilla girada). En `esqueleto-4` no cambia nada: 6 anclas y margen del peor error 4,9 mm, que
  depende de una holgura de 2 mm vigilada por prueba.

**Lo que se vio y queda dicho:** la franja común es fija arriba y, con el aviso del freno HALT
abierto, ocupa unos 640 de 900 px; con el texto del navegador muy agrandado, los rótulos de la
silueta ya no tocan el brazo pero se montan entre sí; en un momento pasado de la cadena anatómica las
tarjetas de recomendación conservan su urgencia y su color; la ficha de Tierra con el enlace
declarado caído y su nota llega a nueve renglones.

**Cierre medido:** (2026-10-22, `main` e23ecf9): suite entera del backend con 3431 pruebas en verde y una roja,
la de completitud del registro (dos fichas sin fecha de C9 sin declarar), corregida y vuelta a pasar
su fichero; `ruff` y `mypy --strict` limpios; `npm test` 1222 pruebas en verde, `tsc` limpio y
`npm run build` entero (con el visor de Polaris) en verde; veredicto del motor idéntico al de la base
en los 36 casos (`rules_version` cambia solo por la familia de C1); las 241 campañas de mutantes
cazan 1712 de 1712 (tres de `cost_ground_dependence` sobrevivían porque C8 dejó sin huecos los
perfiles: una prueba con un aspecto fabricado vuelve a vigilar esa rama); pasada visual con Chromium
sin cabeza sobre la interfaz compilada, las dos consolas cerradas y abiertas y la vuelta de Tierra a
tripulación por la pestaña, en `cardiovascular-deconditioning` y `co2-fatigue`, sin ningún error de
página. El instalador, reconstruido desde el venv limpio (`desktop/npm run dist`, 2026-10-22 04:20,
322 MB): su backend congelado arranca, sirve la interfaz nueva y las rutas de la ronda
(`/api/countermeasures` con su agrupación por RIDGE, `/api/testbeds`, `/api/framework` con `medprat`
y `habitat-systems`, `/api/risks` con la matriz, `/api/measurement-cost` con «hoy se sabe después»
y `/api/baseline-profile`).

### Decimoquinta ronda (2026-10-22 y 23): más del contexto de producto

Diecinueve unidades en paralelo, cada una con su apartado en
`compliance/hmi-state-of-the-art.md` §5.35. Decisiones del usuario del 2026-10-22: corregir el
respaldo de «familia» de la línea base con las dos métricas juntas; la vitamina D descriptiva y el
hígado como región sin nivel propio; agua y microbiología mostradas sin evaluar; historial misión a
misión; el 409 de integridad en rojo; los días R+ agrupados en hitos; el aviso HALT abierto dentro
de la página.

- **Las cinco preguntas de los gemelos (D1).** `GET /api/twins` copia literal la tabla de cinco
  capas de KB §10 (Human, Habitat, Mission y Countermeasure Twin y la capa de decisión) y responde
  cada pregunta con lo que ya daba el panel que la contestaba, con su estado, sus partes, sus
  reservas y de dónde sale. Solo en la consola de tripulación; Tierra, en la decimosexta (E3)
  (§5.35.1).
- **Mapa de conjuntos de datos humanos y CIPHER (D2).** La tarea P0 de KB §15 y su §8 pasan a dato
  servido (`GET /api/human-datasets`): una fila por conjunto (OSD-569, Inspiration4/SOMA, Twins
  Study, OSD-343, OSD-288 y MMASH) con su población, a quién mide, sus tomas en la escalera de hitos
  y su acceso, cada cosa con su frase; CIPHER, con sus catorce estudios y sus tres duraciones, sin un
  solo día de toma (§5.35.2).
- **EPM y Biolab (D3).** Las dos instalaciones de Columbus como cadena de nueve eslabones, de la
  instalación a la aplicación (`GET /api/facilities`), cada una seguida por un experimento
  (Neurospat y TripleLux-A); cada eslabón con su frase leída o con lo que falta y dónde se buscó
  (§5.35.3).
- **Coste de medir: el material de las medidas sin muestra (D4).** Una regla que no estaba escrita:
  que una ficha de equipo no nombre consumibles no dice que no los gaste; lo que no se lee queda
  sin clasificar con lo buscado al lado (§5.35.4).
- **Bancos de prueba (D5).** NEEMO, ARGOS y los vuelos parabólicos, con frases de su página; los
  dos últimos, fuera del enumerado de contexto de evidencia, que no se amplía (§5.35.5).
- **Conjunción solar (D6).** La efeméride guarda la elongación solar de Horizons y
  `conjunction.py` dice si Marte está dentro de los 2° con que JPL describió la pausa de órdenes de
  2015; cinco estados, y se dice que no decide nada (§5.35.6).
- **Biblioteca (D7).** Filtro por familia en el cliente y contraindicaciones y efectos en la tabla;
  el backend, el veredicto y `rules_version` no cambian (§5.35.7).
- **Momento (D8).** Los días R+ agrupados en hitos con fuente (R+0, R+1, R+7 y R+30 de Spaceflight
  Standard Measures), la crónica enlazada con el selector y las tarjetas de un momento pasado sin
  el color de lo vigente (§5.35.8).
- **Tierra (D9).** El enlace declarado se ve aunque aún no haya llegado ninguna lectura, y la ficha
  «Tierra tiene datos hasta» lleva la frase corta (§5.35.9).
- **Matriz de riesgos (D10).** Cada fila dice qué indicadores salen de MMASH (seis) y con qué equipo
  se mide cada variable; el cargador de MMASH emite desde una sola tabla (§5.35.10).
- **Silueta (D11).** El hígado como región sin nivel propio (el nivel es el de nutrición) y los
  rótulos de la silueta colocados por su alto real con el texto agrandado (§5.35.11).
- **Remates de interfaz (D12).** El aviso HALT abierto dentro de la página y el 409 de un registro
  manipulado en rojo, no en el amarillo de un rechazo que se corrige (§5.35.12).
- **Rendimiento de /status y de la crónica (D13).** Medido con `cProfile` sobre 94 080 asientos: la
  crónica pasa de unos 6 s a 1,5 s y ya no firma instantáneas de proyección al leerse; `/api/status`
  deja de repetir lecturas (§5.35.13).
- **Sentido documentado en vuelo (D14).** `GET /api/baseline-profile` lleva, por indicador, si se ha
  visto subir, bajar, sin cambio o discutido en otros vuelos, cada sentido con su frase; solo en el
  panel de línea base, no en la alerta (§5.35.14).
- **MEDPRAT frente al IMM (D15).** Leído NASA/TM-20240012058: la sustitución del IMM no está
  fechada en nada leído, y el memorando no nombra a IMPACT (§5.35.15).
- **El respaldo de familia (D16).** Medido con y sin cobertura de la hora; con ella el colapso de
  HRV cae bajo su suelo de prueba. No se fusionó en esta ronda: pasó a la decimosexta (E1) para leer
  la literatura, y el usuario decidió no adoptarlo (§5.35.16, §5.36.1).
- **Vitamina D 25-OH (D17).** Sexto indicador descriptivo, LOINC 62292-8 leído en su ficha (MCnc,
  ng/mL); el estado no la lee (§5.35.17).
- **Agua y microbiología del hábitat (D18).** Cinco parámetros nuevos, mostrados con el límite leído
  y sin evaluar, como la luz (§5.35.18).
- **Historial misión a misión (D19).** Asiento firmado `crew-mission-history`, junto a la dosis
  previa declarada y sin sustituirla (§5.35.19; `record-integrity.md` §3.17 quinquies).

**Cierre medido:** el de la decimosexta ronda, abajo; las dos se cerraron juntas.

### Decimosexta ronda (2026-10-23): más del contexto de producto

Diecinueve unidades en paralelo, cada una con su apartado en
`compliance/hmi-state-of-the-art.md` §5.36. Los workers se cortaron dos veces y se reanudaron sobre
sus mismos worktrees; las ramas se fusionaron una a una en `main`.

- **Línea base de familia: qué dice la literatura (E1).** La literatura leída (la norma de VFC de
  1996, Bonnemeier 2003, Boudreau 2013, Lu 1999, Laborde 2017, Buchheit 2014, Michael 2017, Mishra
  2020 y Alavi 2022) respalda comparar a la misma hora y en la misma condición, y en MMASH toda la
  detección del colapso de HRV sale de lo contrario. Tres conjuntos de varias semanas con licencia
  CC BY 4.0 leída (LifeSnaps, RELAX y PMData), sin descargar. **Decisión del usuario
  (2026-10-23): solo la documentación**: entran el hallazgo 29 de `external-validation.md`, las doce
  fichas y dos tuplas que no deciden nada en `validation/mmash.py`; el motor, `rules_version` y las
  dos métricas no cambian. La rama `worktree-agent-a13145213e51ba902` queda sin fusionar
  (§5.36.1).
- **Sensibilidad medida, por indicador (E2).** `/api/risks` dice de cada indicador si su
  sensibilidad está medida y con qué deterioros, leído del propio inyector: solo la frecuencia
  cardiaca y la SDNN. Las dos métricas, idénticas (falsa alarma 0,1842 %) (§5.36.2).
- **Las cinco preguntas en Tierra (E3).** `waiting.py` se corta por `until` y Tierra monta el panel
  con su retardo; los títulos dicen el dominio en español (§5.36.3).
- **Historial misión a misión en Tierra y en la crónica (E4).** Tierra lo ve de solo lectura con su
  corte, y las misiones previas entran en la crónica como etapa «carrera» antes del prevuelo; la
  dosis de carrera sigue leyendo solo el perfil (§5.36.4).
- **La unidad en la ingesta manual (E5).** `POST /api/observations` admite una unidad UCUM
  opcional: distinta de la del catálogo, 422 sin conversión ni asiento; ausente, se asume la del
  catálogo y se dice. Tabla «campo de §5 → elemento FHIR» con su prueba (`record-integrity.md`
  §3.14 quater) (§5.36.5).
- **Efemérides de toda la misión, precargadas (E6).** Una consulta a Horizons por `egress` para los
  días que faltan, con guion y ruta; `/api/status` dice qué días están cubiertos. Una efeméride con
  NaN ya no se guarda. La caché sigue fuera del instalador (§5.36.6).
- **Efemérides sin red calculadas en local con SPICE (2026-11-11, lote «APIs abiertas»).** Cierra
  el hueco que dejaba la precarga: un día sin efeméride de Horizons en caché ya no sale «sin dato»
  si están `spiceypy` (extra `[spice]`) y los núcleos genéricos de NAIF (`naif0012.tls`,
  `de432s.bsp`, `scripts/fetch_spice_kernels.py`). Encaja con «funcionar sin red una vez cargados
  los assets/datos» (§2) y «continúa funcionando con la red desactivada» (§14). **SPICE primero**
  (decisión del usuario, 2026-11-11): si calcula el día, el retardo sale de SPICE sin red, y
  Horizons queda de contraste (su caché de ese día; si discrepa por encima del error declarado, se
  dice y se usa Horizons) y de respaldo (caché y después en vivo, para lo que SPICE no calcula);
  cada ventana dice de qué fuente sale; coincide con Horizons en ≤ 3 µs de tiempo de luz en los
  181 días de la misión (`spikes/HALLAZGOS.md` §10). Solo Marte y desde el geocentro. Con SPICE
  cubriendo la misión, la precarga de Horizons deja de hacer falta para el retardo sin red y
  queda como contraste y respaldo (lo dice `how_to_preload`). Queda: la biblioteca y los núcleos no van en el instalador (decisión del usuario),
  y la consola no enseña aún la cobertura de SPICE (`mission.ephemeris_coverage.spice`) más que en
  la frase de la cobertura.
- **Perfiles ISS, Luna y Marte lado a lado (E7).** `GET /api/mission/profiles` y la matriz en
  Tierra, con un octavo aspecto, la capacidad o autonomía médica, hecho solo de frases ya leídas;
  descriptiva (§5.36.7).
- **Radiación (E8).** El HERA de Orion separado del análogo HERA (avisa a bordo; EMMA no lo lee), la
  nota de NASA y NOAA de 2024 sobre el máximo del ciclo 25, fechada y descriptiva, y una frase de
  fuente sobre la salida del refugio, sin umbral propio. La proyección de dosis no cambia (§5.36.8).
- **Riesgos del HRP (E9).** Los 22 riesgos del Roadmap, cada uno con su elemento, su eje RIDGE y si
  EMMA lo cubre (7), en parte (7) o lo deja fuera (8), con el motivo (`GET /api/risks/hrp-coverage`);
  el riesgo de cálculos renales con ficha, enlazado al dominio genitourinario. Ningún analito nuevo
  (§5.36.9); la decimoctava ronda añadió los ocho de la orina de 24 horas, descriptivos (§5.38.5).
- **Credibilidad de cada capa que predice o infiere (E10).** NASA-STD-7009B leída en parte: una
  ficha por cifra INFERIDA o PREDICHA, con sus once factores en palabras y sin puntuación
  («validación: ninguna» donde lo es), en `/api/framework` (§5.36.10).
- **Mapa de datos humanos ampliado (E11).** Reposo en cama (AGBRESA y OSD-51) con su calendario de
  análogo, ISS Research Explorer y data.nasa.gov como catálogos, controles validados (OSD-288 sigue
  siendo ratón) y las diez áreas del Twins Study (§5.36.11).
- **Bancos de prueba (E12).** Matriz banco × RIDGE, declarada como deducción de EMMA, y la duración
  de cada banco con su frase; CHAPEA, de ICON (la página no nombra a BIG); Kraken, NBL y cámaras de
  altitud, fuera del enumerado (§5.36.12).
- **Anatomía: hitos con fuente y pulmones (E13; conversación «L-180 → L-30 → Flight → R+0 → … →
  R+365» y los órganos del gemelo, «Lung» incluido).** Cada hito del selector «Momento» dice de qué
  ficha sale y qué cubre: R+0, R+1, R+7 y R+30 son las tomas de Spaceflight Standard Measures (sus
  tablas suplementarias, leídas, no pasan de R+30); R+180 y R+365, la densitometría posvuelo de
  OCHMO-MTB-013, solo del hueso; R+90 sigue de diseño, sin fuente. El prevuelo gana L-180 y L-90
  (Standard Measures) y L-30 (la densitometría del calendario de ejemplo de OCHMO-MTB-013), con la
  misma regla de tramos que el posvuelo. «Pulmones» entra como el hígado: una región sin nivel
  propio con la frecuencia respiratoria y la saturación de oxígeno, que siguen contando en el
  dominio cardiovascular (cuáles, según el NHLBI). Veredicto idéntico en los 36 casos y
  `rules_version` sin cambio (compliance/hmi-state-of-the-art.md §5.36.13).
- **Personas y organizaciones, servidas (E14).** `GET /api/people` lo deriva del registro de
  evidencia en cada consulta (la afiliación, la del artículo), con un panel en Tierra;
  `personas-y-organizaciones.md`, al día (§5.36.14).
- **Contramedidas en investigación (E15).** Seis (realidad virtual, manguitos de muslo, LBNP,
  centrifugación de AGBRESA, Kaatsu modificado y el dispositivo de umbral de impedancia), cada una
  con su frase y su ficha, en un fichero aparte que no entra en la huella; nunca se ofrecen, con
  prueba (§5.36.15).
- **Sentido en vuelo de los indicadores que faltaban (E16).** Respiración (discutida), saturación,
  sueño, PVT y analíticas; la RMSSD pasa a «discutido». Xu 2013 sigue sin poder leerse: ninguna
  caída de SDNN entra (§5.36.16).
- **Coste de medir: KB §9 (E17).** Los doce términos tienen sitio; masa, volumen, potencia,
  calibración y formación entran como dimensiones, y una cifra solo se acepta copiada de una frase
  leída: ninguna de masa, volumen o potencia lo está (§5.36.17).
- **Simulador: derivas que lo leído contradice (E18).** La FC en reposo pasa a «contestada» y el
  cortisol salival a una clase nueva, «sin respaldo en lo leído», sin cambiar su valor. Medido qué
  cambiaría corregirlas: la FC a 0 cambia 5 de 36 casos y el cortisol 26, sin mover ningún nivel ni
  alerta por dominio; las dos métricas de MMASH no se mueven (§5.36.18).
- **Remates (E19).** Dibujos de contraindicaciones y efectos en la tarjeta, el hígado en el riesgo
  de nutrición de `/api/risks` y el perfil dice que el sexo y la edad no se guardan (§5.36.19;
  lo del sexo, revertido el 2026-11-14: véase «Sexo declarado y ciclo menstrual»).
- **Al juntar las unidades.** Choques que solo se ven al fusionar, resueltos y anotados en sus
  commits de fusión: la prueba de personas de E14 daba por hecho que ninguna ficha real carecía de
  organización, y E11 trae una (AGBRESA, filiación sin leer); los pulmones de E13 salen en el riesgo
  cardiovascular de `/api/risks` como el hígado en el de nutrición (E19), y la prueba fija ahora las
  dos regiones; E16 y E18 escribieron cada uno la ficha de Baevsky 2007 con el mismo `id`, y queda
  una; Agha 2020, que E16 leyó, es la fuente sin nombre que citaba la deriva del cortisol (su
  título es la frase), y la deriva la cita y sigue «sin respaldo» (desde el cierre de la decimonovena
  ronda, «contestado»); en la tabla de organizaciones,
  Brookhaven e ICON salen de E12 y la CSA y las filas nuevas de E14; las páginas sin fecha de E9 y
  E11 comparten una constante.
- **Decisiones que quedan para el usuario** (al día el 2026-10-31). Coste de medir (E17): si el gas
  de calibración cuenta como consumible, si la guía desde Tierra entra en «Hoy se sabe después» y
  cómo escribir un volumen que la fuente da como largo × ancho × alto: siguen abiertas. Perfiles
  (E7): la frase del reabastecimiento lunar de C8 que el filtro de lenguaje marca como `dosing`,
  reescribirla o ajustar el filtro: sigue abierta. Simulador (E18): ~~si se corrigen los dos valores
  de deriva; si la FC en reposo es «contestada» o «sin respaldo»~~ decidido en la decimonovena ronda
  (registrado en la entradilla de §5.39 de `hmi-state-of-the-art.md`, «Decisiones del usuario en el
  plan aprobado (2026-10-31)»; lo detalla su cierre); la fatiga de menú pasó a «sin respaldo en lo
  leído» con el mismo valor en
  la decimoctava (§5.38.10); y `CLAUDE.md` y el README raíz hablan de tres clases de respaldo, y
  ahora hay cuatro (sigue abierta). La excepción de la dosis de §5.37.1 (la inferida cuenta para el
  límite de carrera, la predicha nunca) la confirmó el usuario en la decimoctava (entradilla de
  §5.38). API (E6): ~~`POST` sin cuerpo en `/api/comms/preload` y `/api/simulate`~~ decidido en la
  decimonovena ronda (misma entradilla de §5.39). Línea base (E1): ~~medir las variantes B y C con
  LifeSnaps o RELAX~~ decidido en la decimonovena ronda (misma entradilla: se mide, sin adoptar).
  ~~Y la consola de Tierra desborda en horizontal
  (unos 1434-1439 px en una ventana de 1400, visto por E9 y E10), sin localizar el panel.~~ Localizado
  y arreglado en la decimoséptima (U17, §5.37.17): `main` era una rejilla de columna implícita que
  crecía con su panel más ancho («Conjuntos de datos humanos»); con `minmax(0, 1fr)`, 1400/1400 y
  390/390 medidos, cerrada y abierta.

**Cierre medido** (2026-10-23 y 24, `main` 6e26ff2, con las dieciocho unidades fusionadas y antes de
la documentación de E1): suite entera del backend, 4349 pruebas en verde y ninguna roja, en una
pasada sin otras suites a la vez (las de los workers, con diecisiete en paralelo, se cortaban o
fallaban por memoria y por el índice de búsqueda reconstruido a media pasada); `pytest -m external`,
34 en verde, entre ellas las dos pruebas de regresión de la invariante 5; `ruff` y `mypy --strict`
limpios tras cada fusión; `npm test` 1416 pruebas en verde, `tsc` limpio y `npm run build` entero.
`rules_version` sigue en `reglas@faf6e60fc2fd3f12`. Campañas de mutantes: las 276, en dos pasadas
(la primera se paró por falta de memoria del sistema tras 237; las 40 restantes, el 2026-10-25), sin
ningún mutante vivo. Tres campañas tenían mutantes **mal escritos** desde rondas anteriores, que no
mutaban nada porque el código o el texto que buscaban había cambiado: `system_status_api.json` (la
ruta guarda las declaraciones en una variable desde D9), `crew_compare_api.json` (la lectura de la
cabina de `/api/crew/compare` se llama `stored` desde D18) y cuatro de `soup_polaris.json` (la †
pasó de `waiting.py` y `routines.py` a `vault.py` y `source_check.py` en C15, y la frase de H20 sale
dos veces). Reapuntados a lo de hoy con la misma defensa, cazan 8/8, 9/9 y 50/50. Al reapuntar el de
la cabina se vio que `/api/habitat/crew` (`crew_overview`) también lee la cabina con el corte de
Tierra y ninguna prueba lo vigila: ~~queda pendiente su prueba~~ hecha en la decimoséptima ronda
(U11, §5.37.11: `backend/tests/test_habitat_crew_cut.py`, la ruta es `/api/crew`; no reveló ningún
fallo, y la campaña `habitat_crew_api.json` caza 3 de 3). Sin pasada visual de cierre con
`shots.py` ni veredicto de los 36 casos medido sobre `main`: los dio cada worker en su rama.

### Decimoséptima ronda (2026-10-26): lo que faltaba del contexto de producto

El usuario pidió «mira a ver si falta algo más por añadir del contexto». Tres lecturas en paralelo
(especificación y base de conocimiento; conversación de ideación y anexos; lo escrito como pendiente
en §5.35, §5.36 y `external-validation.md`), cada candidato comprobado en el código, y dieciocho
unidades en paralelo, cada una con su apartado en `compliance/hmi-state-of-the-art.md` §5.37, fusionadas
una a una en `main` (de `33d570e` a `909a9c0`). Decisiones del usuario en el plan: el motor deja fuera
las lecturas que no son medidas, con `rules_version` nueva y las dos métricas de la invariante 5
reportadas juntas; entran descartar una alerta, un escenario que se recupera, el evento solar a toda la
tripulación y la radiación en el estado del hábitat. Lo pendiente de decisión de rondas anteriores no
entró.

- **Medido frente a inferido y predicho, en el motor (U1; especificación §2, §10 y criterio de §14).**
  La separación se veía en la etiqueta y no en el motor: una deriva extrapolada podía mover la base
  contra la que se la juzgaba. Ahora la línea base, la tendencia y el riesgo solo leen lecturas
  `measured` (`ANALYSED_TYPES`, `is_analysed_type`, `decides`, en `api/routes.py`; siguen la regla el
  diario, la crónica, las rutinas, la PVT y `/crew/compare`); lo demás se firma igual, se enseña con su
  rótulo y el estado lo cuenta en `provenance.set_aside` con la regla en palabras. El detalle de
  alerta dice el tipo de cada cambio y el corte de la base personal que cruzó (`personal_cut`).
  Excepción declarada: la dosis acumulada medida o inferida cuenta para el límite de carrera
  (`DOSE_TYPES`), la predicha nunca —la dosis efectiva es inferida por definición y, sin la excepción,
  volvería el fallo que cerró «la dosis registrada cuenta»—; el usuario la confirmó en la decimoctava.
  `rules_version`: `reglas@faf6e60fc2fd3f12` → `reglas@c89d7ebf4d5f4aa9`. Las dos métricas,
  idénticas a las publicadas (falsa alarma por lectura 0,1842 %, 0,1472 % en reposo; detectado /
  marcado / escalado: taquicardia sostenida 95,45 / 81,82 / 77,27 %,
  progresiva 31,82 / 13,64 / 9,09 %, episodio agudo 90,91 / 77,27 / 72,73 %, colapso de HRV 13,64 /
  4,55 / 0 %); veredicto idéntico en los 36 casos (§5.37.1).
- **El perfil de línea base dice de qué está hecho y dónde corta (U2; §2, §3 «personal thresholds»,
  §10 «¿respecto a qué baseline?»).** Cada base lleva su composición por entorno y por tipo de
  lectura, contada solo si los valores reconstruidos son exactamente los de la base, y sus tres
  cortes (leve, moderado, grave) con el cuantil y el mínimo de lecturas del motor; «pide 1000
  lecturas y tiene 225» donde la base no sostiene la gravedad. Descriptivo: `rules_version` igual
  (§5.37.2; en la decimoctava, U11, los cortes pasaron a leerse de la función del motor).
- **Simulador: un escenario que cesa y el evento solar a toda la tripulación (U3; conversación,
  «CAUTION → RECOVERING → NOMINAL»).** `transient-sleep-loss` («Falta de sueño pasajera (cesa)»):
  sueño y PVT peores unos días anclados al final de la ventana, siete parámetros «diseño», y la
  mejora no se atribuye a nada. `spe-event` siembra cuatro tripulantes y los cuatro lo sufren. El
  veredicto pasa de 36 a 40 casos; de los 36 de antes cambian solo los tres esperados (crew-02 a -04
  de `spe-event`, a `concern` como crew-01). El escenario nuevo acaba en vigilancia «recuperándose»
  y no en nominal, porque la recta de 21 días todavía contiene el episodio: el motor no distingue un
  episodio cesado de una deriva, y eso se midió en la decimoctava (U6). MMASH no cambia (§5.37.3).
- **Radiación en el estado del hábitat (U4; §3 HabitatState «radiation», KB §10).** `GET /api/habitat`
  → `radiation`: la última tasa de dosis de cada dosímetro, el evento solar del estado con tres
  estados (vigente, ninguno en 3 días, «sin datos de DONKI»), el módulo sin declarar y sin factores
  de blindaje; la misma nota en el gemelo del hábitat; `HabitatRadiation.tsx` en el panel.
  Descriptivo, con prueba de veredicto idéntico (§5.37.4).
- **El evento solar como causa común candidata (U5; KB §6 y §2.1 «fusionar hazard + dosimetría»,
  §7).** `correlate` propone `solar_event`, «coincidencia temporal, no causa», con la tasa de dosis
  del catálogo por encima de su límite y lo que DONKI cubre o no de la ventana; con uno o varios
  afectados. Niveles y `rules_version` iguales (§5.37.5).
- **Descartar una alerta (U6; conversación, «HUMAN DECISION / Accept / Dismiss / Investigate»).**
  Asiento `alert-dismissal` firmado por la consola, motivo de un vocabulario cerrado (artefacto del
  sensor, explicada por el contexto, otro motivo con nota) y quién lo dice; nada se recalcula ni se
  borra, y la cobertura es la de un reconocimiento (§5.37.6; `record-integrity.md` §3.20 bis).
- **Recuperación posvuelo: cuándo vuelve y si vuelve (U7; conversación, «¿cuánto tarda en volver
  al baseline? ¿Vuelve completamente?»).** `return_to_range`: por indicador, el primer R+ dentro del
  rango prevuelo, si se mantiene y «sin volver» si la última toma sigue fuera; los indicadores sin
  rango prevuelo se dicen con su motivo en vez de desaparecer. No es una tasa de recuperación: con
  tres o cuatro tomas no hay curva, y no se inventa (§5.37.7).
- **Lecturas: el enunciado del reto y las fuentes que faltaban (U8; especificación §17, KB §1 y
  §11.3).** El enunciado no se pudo leer (salía el 28 de octubre): ficha como buscado y no leído;
  once fichas más (anuncio y preguntas frecuentes de Space Apps, «Living in Space», OSDR, Columbus,
  la carta de Stuhlinger, el vídeo de la estación y los dos posts de X) en `GET /api/context-sources`,
  y `compliance/challenge-coverage.md`, que separa lo leído de NASA de la interpretación del equipo
  (§5.37.8).
- **Lecturas: HERMES, el CDSS de ExMC y la estabilidad del alimento (U9; conversación, mapa de
  organizaciones y «prior art»; KB §5).** HERMES, la plataforma de datos de TRISH, con lo que dicen
  NASA y Baylor y sin lo que no dicen (cómo detecta, con qué se validó), en `state-of-the-art.md`
  (ficha `nasa-trish`); el CDSS punto por punto: los dieciséis supuestos de HRP-48032 y una tabla de
  cobertura de 34 filas (10 «cubre», 13 «en parte», 11 «no»), inventario y no puntuación; cinco frases
  del informe de alimentación de 2016 sobre radiación y comida, descriptivas (§5.37.9).
- **Lecturas: las derivas sin ficha del simulador y los reposos en cama de OSDR (U10).** Las cuatro
  derivas «contestadas» que no citaban ficha nombran ahora sus dos lados (siete fichas nuevas);
  ningún valor ni clase cambia; dos notas decían lo que la fuente no dice (Law 2014 y la SDNN) y se
  corrigieron. Los seis reposos humanos de OSDR que faltaban (OSD-195, 198, 353, 370, 942 y 946)
  entran en `GET /api/human-datasets` con su acceso leído (§5.37.10).
- **Remates de backend (U11).** La prueba de `/api/crew` con el corte de Tierra que pedía el cierre
  de la decimosexta (`test_habitat_crew_cut.py`, sin fallo); una misión previa no puede solaparse
  con la actual al darla de alta (422); y cuatro vías por las que la huella del índice de `kb.py`
  se escribía sobre un índice que no casaba con ella, arregladas con cerrojo entre procesos
  (§5.37.11).
- **Efemérides: caché y precarga robustas (U12).** Los siete fallos que dejó §5.36.6: la consulta
  diaria busca la fila de medianoche de su día, la caché se escribe atómica, un fallo de disco o la
  puerta de salida dan 503 y no 500, la precarga va por tramos; con la caché del repositorio nada
  cambia (§5.37.12).
- **Lo que espera a una persona y la crónica (U13).** `waiting` cuenta «en arreglo» y «resuelto»
  con la regla del estado (solo lo que firma la consola); la ruta solo absorbe «nada que analizar»;
  `domain_name` pasa al catálogo; los momentos de la crónica salen de la evaluación (§5.37.13).
- **Enmienda e ingesta manual (U14).** La enmienda exige el mismo indicador y no el mismo
  tripulante (el peligro H3 se controla reasignando por enmienda; exigirlo dejaría la redacción como
  única vía); unidad UCUM opcional también en la lectura de cabina manual; los analitos de analítica
  salen `laboratory` en FHIR (§5.37.14).
- **Cargadores de evidencia: un solo contrato (U15).** `read_contract.check_sources` para los seis
  ficheros de lectura, y `main.py` los valida al importarse: un fichero roto no deja arrancar, con su
  nombre y su motivo (§5.37.15).
- **Anatomía y riesgo (U16; conversación, «MEASURED / INFERRED / RESEARCH EVIDENCE»).** Las fichas
  que nombra la frase de cada región bajo «Sistema humano»; R+730 y R+1095 en «Momento» (OCHMO-MTB-013,
  solo del hueso); una capa aparte «Evidencia de investigación» en el hígado con Hayslip 2026
  (hígado de ratón), que no cuenta en el nivel, la evidencia ni las contramedidas (§5.37.16).
- **Consola de Tierra: desbordamiento y cortes (U17).** Localizado el desbordamiento que E9 y E10
  vieron: `main` con `minmax(0, 1fr)`, medido 1400/1400 y 390/390; un solo corte (`groundCut`), una
  sola clave de refresco y los paneles de lo que viaja al firmarse con una misma regla (§5.37.17).
- **Remates de interfaz (U18).** La carrera del modo seguro resuelta en `networkSync`; la cobertura
  de efemérides a la vista en la línea temporal (en cian lo que falta); la guarda de `urlWrap`
  ensanchada, que encontró seis direcciones sin partir (§5.37.18).

**Cierre:** las dieciocho unidades se fusionaron una a una; la suite completa y las campañas las
corrió el cierre de la decimoctava ronda, que incluyó lo pendiente de esta (abajo).

### Decimoctava ronda (2026-10-26): lo que aún faltaba del contexto de producto

El usuario pidió «céntrate en si hace falta añadir algo más del contexto». Una lectura comprobada en
el código de lo que dejaron las unidades de §5.37, de lo que seguía abierto y de las piezas de la
conversación de ideación aún sin hacer. Veinte unidades en paralelo, cada una con su apartado en
`compliance/hmi-state-of-the-art.md` §5.38, fusionadas una a una (de `2972d93` a `05fe919`). Decisiones
del usuario en el plan aprobado: entran las notas de Tierra a bordo, la comida plato a plato, la
densitometría frente a la banda ósea y los turnos como evento de misión; **la dosis inferida cuenta
para el límite de carrera y la predicha nunca** (confirmada la excepción de §5.37.1); **la crónica
cuenta solo las decisiones firmadas por la consola**, como el estado; **medido, inferido y predicho
deciden también en el motor** (lo de §5.37.1, con su `rules_version` nueva, se queda); **las notas de
Tierra solo informan o preguntan**, nunca mandan; **la comida va plato a plato como texto libre**;
**los analitos de orina del riesgo renal entran como descriptivos**; **la fatiga de menú pasa a «sin
respaldo en lo leído»** con el mismo valor; y **la tendencia que no distingue un episodio cerrado de
una deriva se mide sin adoptar**. Entró seguro un fallo de la fusión de §5.37.1 con §5.37.4 (U7).

- **Notas de Tierra a bordo (U1; conversación, la línea de ida y vuelta con Tierra, L182, L190,
  L510).** Asiento `ground-note` firmado con una clave propia, `ground-console`, que no puede
  reconocer, silenciar ni descartar nada; clase `information` o `question`, 600 caracteres, y una
  regla única para quien escribe y quien lee: el filtro general de lenguaje más las formas de mandato
  fuera de una pregunta («Repita la medida esta tarde, ¿vale?» se rechaza). La nota viaja con el
  retardo: a bordo no se entrega ni se cuenta lo firmado después del corte. No cambia ningún nivel ni
  `rules_version` (§5.38.1; `record-integrity.md` §3.25).
- **Comida plato a plato (U2; conversación, «Food selected / Food rejected / Menu fatigue»).** La
  valoración de aceptabilidad lleva el alimento valorado, texto libre con regla de diseño de EMMA
  (`ingest/food_item.py`, `Observation.focus` en FHIR), porque ninguna fuente leída da un vocabulario
  cerrado; una enmienda conserva el alimento; el panel de nutrición cuenta por plato sin umbral ni
  veredicto. Mismos valores a las mismas horas dan el mismo estado con alimento y sin él (§5.38.2;
  `record-integrity.md` §3.14 quinquies).
- **Densitometría frente a la banda ósea (U3; conversación, «predicción durante misión → resultado
  post-vuelo → validación»).** Dos descriptivos nuevos con LOINC leído en su ficha, 24966-4 (columna
  lumbar) y 38261-4 (cadera), propiedad ArMass en g/cm2 (los T-score, la cadera de un lado y «DXA
  Femur» se descartaron y se dice por qué), y `analysis/densitometry.py`: la pérdida medida entre la
  última DXA previa (≤ 180 días antes) y la primera posvuelo (< 30 días) frente a la banda INFERIDA
  del día de regreso; dentro, por encima o por debajo, rotulado MEDIDO frente a INFERIDO y sin
  puntuar. Es una comprobación de la inferencia, no un veredicto clínico; la DXA no vuela (§5.38.3).
- **Turnos como evento de misión (U4; conversación, «carga de trabajo, turnos y eventos críticos»,
  «ciclo día/noche»).** `shift` como cuarto `kind` de `mission-event`, con los campos de una EVA;
  Flynn-Evans 2016 releída (los «slam-shifts» de la ISS acortan el sueño desalineado, 5,4 frente a
  6,4 h) no da horas ni ventana, así que no hay umbral; en la alerta, «correlación temporal, no
  causa» (§5.38.4; `record-integrity.md` §3.17 sexies).
- **Los analitos de orina del riesgo renal, al catálogo (U5; KB, riesgo de cálculos renales; E9 de la
  decimosexta).** Ocho descriptivos: siete LOINC leídos (6874-2, 2701-1, 3087-4, 6687-8 en mg/(24.h);
  27378-9 en pH; 2956-1 en mmol/(24.h); 2694-8 en mosm/kg) con la unidad de su propiedad y la
  sobresaturación del oxalato cálcico con código propio, porque LOINC no tiene ese cociente; sus
  umbrales se citan y no se evalúan; las 22 portadas de los informes de evidencia del HRP, leídas y
  enlazadas en la cobertura de riesgos. `rules_version` igual (§5.38.5).
- **Tendencia: un episodio cerrado frente a una deriva (U6; medido, sin adoptar).** Una regla de
  tres condiciones (hubo episodio y lo vio la vía de desviación; el tramo actual lo ve de vuelta; ha
  vuelto a su nivel y no a una base que lo siguió) en `analysis/episode.py`, que nada que decide
  pasa: se mide por `GET /api/status` → `closed_episode_shadow` y en la validación con
  `closed_episodes=True`. MMASH idéntico por construcción (24 h no dan tendencia); en los diez
  escenarios con tres semillas la regla no cierra nada en los deterioros ni en `nominal` y en
  `transient-sleep-loss` cierra 3, 2 y 3 de sus 4 indicadores: el dominio sigue en vigilancia. No
  cumple su propósito y no hace daño medible; decisión pendiente del usuario (§5.38.6; hallazgo 30 de
  `compliance/external-validation.md`).
- **Un solo «ahora» para lo que decide (U7; el fallo de la fusión).** Tras la decimoséptima había
  tres filtros distintos antes de fijar el «ahora»: la radiación del hábitat no apartaba nada (tres
  lecturas predichas un mes después movían su «ahora» y su «última tasa» podía ser una inferida que
  el estado no leyó). Ahora `routes.state_reference` es la regla dicha una vez, y una guarda por AST
  falla si algo en `app/` llama a `_analysable` fuera de ella; `/crew/compare` cuenta lo apartado y
  rechaza un descriptivo (422); `/api/crew` con `until` sin zona es 422 y no 404 (§5.38.7).
- **Ante un evento solar, la tripulación de un vistazo (U8; conversación, «¿Dónde está la
  tripulación? ¿Cuál es la dosis actual de cada astronauta?»).** `GET /api/crew/radiation` compone,
  sin calcular nada nuevo, la ubicación declarada, la dosis de esta misión y la de carrera de cada
  tripulante (INFERIDAS, iguales a las de su estado), el evento del estado y el refugio de Orion; sin
  factores de blindaje; `CrewRadiation.tsx` en las dos consolas con el corte de Tierra (§5.38.8).
- **Monitorización intensificada durante un evento solar (2026-11-02; idea del equipo, «un protocolo
  para cuando hay eventos críticos inminentes que aumente la monitorización y se centre en los
  parámetros más importantes»).** Con el evento que el estado da por activo
  (`analysis.risk.active_solar_event`, extraído del motor: el mismo criterio, no una copia), las
  rutinas del bloque `during_event` de `routines.json` se juzgan con un periodo más corto (dosis 1 h;
  carga de síntomas 12 h; pulso, SpO₂ y respiración 2 h; temperatura 4 h) y van primero por su
  prioridad. `GET /api/timeline/routines` declara por rutina `period_hours`, `period_source`
  (`design`/`event`), el de siempre, el evento y la frase que lo dice; Tierra solo lo ve si el
  evento ya había empezado en su corte. Parámetros de diseño de EMMA (no se ha leído un procedimiento
  de NASA que fije esa cadencia), en `rules_version`; solo orden y marca: no cambia el riesgo, las
  alertas ni la caducidad del evento, y «rota» sigue sin ser alerta (`app/routines.py`).
- **El evento solar en la demo sin red y la vuelta a la normalidad (2026-11-04; cronograma, y la
  especificación §9, «evento de radiación»: detectar, contexto, procedimiento y línea temporal de
  seguimiento).** Sin red no había DONKI y la monitorización no se intensificaba nunca: ahora, sin
  evento de DONKI, la acorta también la última tasa de dosis de a bordo por encima de su límite de
  peligro (`active_trigger` `dose`; no se llama «evento solar»). Escenario `spe-event-recovery`: el
  pico de `spe-event` 12 días antes del final, de modo que la línea temporal (con el corte `until`)
  ve el comienzo, el periodo intensificado y la vuelta a nominal sin alertas; parámetros del pico
  declarados de diseño. Instantánea fechada de DONKI para el instalador (`EMMA_DONKI_SNAPSHOT`,
  `scripts/fetch_donki_snapshot.py`), declarada «instantánea de DONKI del <fecha>, no en vivo», en
  cian, con su último SEP y su fecha real («no está vigente»). **Hueco abierto:** el fichero de la
  instantánea aún no está en el paquete (la `DEMO_KEY` estaba agotada al hacer el cambio); hay que
  ejecutar el guion con red antes de `demo-v1` (`compliance/hmi-state-of-the-art.md` §5.40.4).
- **Remates de efemérides e ingesta (U9).** Una precarga a la vez por carpeta de caché (espera con
  tope de 30 s, decisión de diseño, y 409 si no acaba); la categoría FHIR declarada en cada indicador
  contra la definición oficial (peso corporal → `vital-signs`, orina → `laboratory`, sueño →
  `activity`, los registros de ingesta sin categoría porque ninguna de las nueve los describe);
  el tope de unidad en español también al confirmar una analítica (§5.38.9).
- **Remates de backend (U10; dos decisiones del usuario).** La crónica cuenta lo que cuenta el estado
  (solo lo firmado por la consola, con la misma regla y sin tercera copia; lo de otra identidad se
  omite, no se marca; el modo seguro y la fase de contraste, excepciones dichas); la fatiga de menú a
  «sin respaldo en lo leído» con su valor; aviso `overlap` al leer una misión previa solapada; tope
  de 300 s (diseño) a la espera de los cerrojos de `kb.py` (§5.38.10; `record-integrity.md` §3.20).
- **Los cortes del perfil con la función del motor (U11).** `baseline.cut_rules`, `watches` y
  `personal_cuts`, la regla una sola vez; un oráculo congela la regla anterior y la compara en más de
  10 000 casos sin diferencia; 40 casos y 80 respuestas idénticas; las dos métricas de MMASH
  idénticas (§5.38.11).
- **Consola de Tierra: un reloj y menos peticiones (U12).** Un reloj de llegada compartido
  (`arrivalClock`), lo fijo pedido una vez por panel, `baselineRefreshKey` común y la guarda de
  `urlWrap` también sobre lo pintado; de 29 a 20 peticiones en 90 s; la lista de ficheros de la
  cobertura del CDSS (U9 de la 17, fusionada después de medir) llevaba Tierra a 1623 px y se parte
  (§5.38.12).
- **Versión en el estado del modo seguro (U13).** `version` (cuántos asientos `safe-mode`) y
  `store_epoch` en `GET /api/safe-mode`; la consola se queda con lo más nuevo que llegue y solo relee
  si un cambio falló; la prueba recorre todas las intercalaciones de ocho tandas (§5.38.13).
- **Lecturas: marco de NASA y radiación (U14).** El Apéndice D de NASA-STD-7009B, leído entero: la
  criticidad la fija la autoridad técnica de NASA, así que la matriz no se aplica y cada capa dice en
  palabras lo que hay en sus dos ejes, con una defensa que rechaza el nombre de una categoría aunque
  vaya negado; el resumen descargable de NTRS 20240013005 tampoco fecha la sustitución del IMM; de las
  series del ciclo solar de NOAA entra una sola cifra con su mes (94,4 manchas suavizadas, marzo de
  2026) y EMMA no deduce la fase (§5.38.14).
- **Lecturas: datos humanos (U15).** Clément 2022 → KBR; el resultado de AGBRESA que existe (Kramer
  2021, capacidad física; no hay uno del estudio entero); el Twins Study e Inspiration4 leídos hasta
  el final (Inspiration4 subió sus datos a cuatro repositorios); Hayslip 2026 entero (acceso abierto
  en su revista), que confirma la frase de la capa de investigación del hígado (§5.38.15).
- **Sentido en vuelo: bioquímica (U16) y hormonas y marcadores (U17).** Dieciocho analitos y trece
  hormonas y marcadores buscados en PubMed, PMC y NTRS: tres sentidos leídos (magnesio sube, Smith
  2015; proteínas totales sin cambio, Zwart 2022; LH sube, Strollo 1998) y veintiocho «buscado y no
  encontrado» con lo leído, dicho con cuidado (la PCR solo cambia después del vuelo; la T4 libre no
  se confunde con el índice; de los marcadores tumorales no hay nada en vuelo). La revisión cazó que
  el cargador aceptaba «space flight» suelto y con él «post space flight»: vuelve a como estaba
  (§5.38.16, §5.38.17).
- **Coste de medir: calibración y formación (U18; KB §9).** Leídas la calibración del DOSTEL y de los
  REM del SRAG, de los analizadores de Tierra de la serie roja y la recalibración del fabricante del
  actígrafo, y la formación (flebotomía instruida antes de la misión; la camiseta de la CSA en HERA),
  con dos palabras nuevas que dicen el sitio (`station-trained`, `analog-trained`); 456 → 436 pares
  sin clasificar (§5.38.18).
- **Fuentes del contexto que faltaban (U19; especificación §17).** Las seis direcciones sin ficha,
  leídas (ninguna con fecha de publicación); astroquery y ZeroKeyUSB entran para decir que no se
  adoptan; la frase de HACCP, en el informe de comida del HRP; la de la estación como «atención médica
  miniaturizada» no se encontró y se dice (§5.38.19).
- **PMID pendientes de graduar (U20).** `grade_sources.py` corrido sobre los 67 PMID citados, por la
  puerta de salida (antes usaba `httpx` a pelo); 61 nuevos con el grado que da su registro (50
  «desconocido», porque PubMed no fija su diseño); un fallo de la expresión de tipos de publicación,
  corregido (§5.38.20).

**Cierre medido** (2026-10-29 y 30, sobre `main` con las veinte unidades fusionadas; incluyó lo
pendiente de la decimoséptima). Lo que la suite completa encontró tras fusionar, corregido en
`8a13743`: dos líneas de registro de las efemérides (U9) llevaban la excepción entera y ahora su tipo,
y la fecha pedida entra en la lista cerrada de argumentos; las unidades de la orina de 24 h (U5) no
tenían escala declarada para el cambio relativo (masas, sustancia y osmolalidad de razón; el pH no,
que es un logaritmo); el fichero de referencia del hábitat sin ubicación, regenerado (solo cambia la
gradación de dos citas que U20 graduó); y la prueba del descarte con nota larga firma como la
consola, que es lo único que la crónica cuenta desde U10. Las campañas de mutantes, al día con el
código fusionado en `eb4084a`: el filtro por firma de Tierra de la crónica vive en `timeline.counted`
y los mutantes de recursos, vínculos y sistemas apuntan ahí (antes, con el corte en 2020, dos filtros
quitaban la misma declaración y uno sobraba sin que nada lo viera: 2 mutantes sobrevivían, y las
pruebas ganan el caso que los distingue); cinco mutantes mal escritos tras las fusiones (la
densitometría de U3, `kb.py` de U10, la proyección con el episodio cerrado de U6, la consola PVT),
reapuntados al texto actual. Los dos commits no anotan el total de pruebas ni de campañas; no se
inventa aquí. `rules_version` tras la ronda: `reglas@c89d7ebf4d5f4aa9` (la de §5.37.1; ninguna unidad
de la decimoctava la movió, y §5.38.5, §5.38.8 y §5.38.11 lo midieron).

### Decimonovena ronda (2026-10-31 y 11-01): lo que aún faltaba del contexto de producto

Veinticuatro unidades, una rama por unidad y fusión de una en una; el detalle de cada una, con lo
medido y lo que queda, en `compliance/hmi-state-of-the-art.md` §5.39.1 a §5.39.24.

- **Este documento y el reto (U1, U2).** Rondas 17 y 18 al día; el enunciado leído y el inventario
  de fuentes rematado.
- **Evidencia y personas (U3, U4, U5).** Registro sin verificar, bancos de prueba, proveedores y
  repositorios humanos con su uso.
- **Sentido en vuelo (U6, U7).** Hematología, bioquímica, función y cabina: lo leído, junto a la
  línea base, y sin mover una regla.
- **Radiación, perfiles y marco de NASA (U8).** Incluye el perfil `mars-surface`.
- **Reglas y motor (U9, U11, U21).** La versión de reglas va firmada con cada decisión; lo que
  decide se dice en todas partes; la coletilla «¿…?» ya no tapa una orden en el filtro general.
  El imperativo de pauta sigue permitido solo en las notas de Tierra.
- **Contrato de §5 (U10).** `POST /api/import/observations`, por el ledger y con la cabecera de
  consola, que se le puso al fusionar.
- **Contexto y descriptivos (U12 a U15).** Dieta, líquidos y sueño como contexto de alerta;
  indicadores descriptivos y composición del plato. La fatiga no entró (§5.39.14). Las nueve
  pruebas de la batería Cognition de NASA (U14) entraron como 17 indicadores descriptivos sin vía
  propia de registro; **desde el 2026-11-03 tienen ingesta y pantalla**: `POST
  /api/cognition/console` firma las puntuaciones de una sesión que da el programa de la batería
  (EMMA no pasa las pruebas ni las puntúa: es software de terceros) con la fuente
  `console-cognition` y con quién teclea, `GET /api/cognition/protocol` da las diez pruebas con la
  frase leída de qué mide cada una (de la PVT no hay frase leída y remite a su consola), y el panel
  «Batería Cognition (NASA)» va en «Diario y pruebas» de la consola de tripulación. Sigue fuera del
  riesgo, de las alertas y de la huella de reglas.
- **Investigación, contramedidas y coste (U16, U17, U18).** Capa de investigación en otros órganos,
  efectos de contramedidas y dimensiones del coste de medir.
- **Remates (U19, U20, U23).** Backend, interfaz y `POST` sin cuerpo con cabecera propia.
- **Simulador (U22 y cierre).** Dos derivas corregidas a 0 y cuatro reclasificadas.
  `cortisol_rise_per_week` pasó además a «contestado» al fusionar, para no contradecir el sentido
  leído por U6 (Vorobiev 1995 frente a Buchheim 2019); el valor sigue en 0.
- **Línea base de familia (U24).** B y C medidas con LifeSnaps: 71 personas y 1 322 974 lecturas.
  La falsa alarma vigente sale en 3,532 % frente a 0,184 % en MMASH, unas 19 veces más, y no hay que
  citar el 0,18 % sin esa salvedad. B da 3,539 % y C 3,274 %, con señal neta casi igual. **Nada se
  adoptó: adoptar es decisión del usuario** (`external-validation.md`).

**Queda abierto, para decidir:** RMSSD «contestado» o «sentido documentado»; cabecera en todo método
no seguro (siguen fuera `PENDING_SIMPLE` e `/api/imaging/studies`); signo de `circadian-shift`;
serie de una persona en yugular; manguitos y caída ortostática; OSD-288 duplicada; «por protocolo,
en vuelo» en coste; y la adopción de la línea base.

### Vigésima ronda (2026-11-02): lo de más impacto para el evento

- **Para qué sirve cada órgano (unidad 2).** El enunciado del reto pide que cada parte de la figura
  enseñe «its function and health status»; faltaba la función. Cada región de `anatomy.REGIONS`
  lleva ahora `function` (una o dos frases sobre para qué sirve el órgano o sistema, no sobre lo que
  EMMA mide) con `function_refs`, fichas nuevas leídas el 2026-11-02: nueve páginas del módulo SEER
  de anatomía y fisiología del NCI (sin fecha en la página) y la del NEI sobre cómo funcionan los
  ojos. La radiación («todo el cuerpo») no es un órgano y lo dice (`function_note`). Se sirve en
  `/api/anatomy` y `/api/anatomy/state` y sale en la sección «Función» de la cadena, antes del
  estado. No entra en el nivel, la evidencia del dominio ni las alertas
  (`compliance/challenge-coverage.md`, fila de la figura).

### Desconexión progresiva (2026-11-02): niveles de misión

Idea del equipo para el evento: «un protocolo de desconexión progresiva de funciones para ver lo
mínimo básico en ambientes con restricción de recursos, sobre todo energéticos y humanos». La
especificación pide degradación elegante (§2) y la base de conocimiento el coste de medir (§9);
faltaba poder declarar, firmado, que se espera menos. Hecho así (`compliance/record-integrity.md`
§3.27):

- **Tres niveles firmados** (`nominal`, `reduced`, `minimal`; asiento `mission-mode`,
  `GET/POST /api/mission-mode`, con versión y época como el modo seguro y el corte `until` de
  Tierra). Bajar lo firma cualquiera con nombre y motivo, saltando niveles si hace falta; subir,
  una persona con nombre, un nivel cada vez. Puede citar el estado declarado de la energía o de
  las comunicaciones (§3.16 bis), sin vatios: no hay potencia de los equipos con fuente.
- **El criterio sale del coste de medir**, no de una importancia clínica que EMMA no puede
  afirmar: cada nivel nombra las clases de medida y el gasto de consumibles que se siguen
  esperando (`data/mission_modes.json`, «vocabulario de diseño de EMMA»). En reducido se dejan de
  esperar muestras, laboratorio y lo que gasta consumibles; en mínimo, lo que no da un sensor sin
  que nadie lo tome, salvo síntomas y dolor, añadidos a mano con su motivo.
- **Nunca se apaga** la ingesta por el ledger, el análisis, el riesgo, las alertas ni el modo
  seguro: con el mismo dato, el estado y las alertas son idénticos en cualquier nivel (invariante
  5). El aviso lo redacta el backend y no manda nada (invariante 7).

- **En la crónica (2026-11-03).** Cada cambio de nivel es un hecho `mission-mode-change` de
  `app/timeline.py`, como el modo seguro: en su hora de firma, con el nivel anterior y el nuevo,
  quién lo firmó, el motivo y, si lo hay, el sistema citado con su estado declarado al firmar. La
  frase la redacta el backend (`mission_modes.chronicle_sentence`) y no manda nada. Cuenta lo que
  cuenta el estado (lo firmado por la consola y, para Tierra, lo que existía en su corte); un
  asiento redactado se va y el siguiente cuenta desde el que queda, como la versión.

**Queda abierto:** ~~cablear `expected_measurements(level)` a las rutinas~~ (hecho en 4906833);
~~montar `MissionModePanel` en las dos consolas~~ (hecho en 30d17d1); ~~que la crónica cuente los
cambios de nivel~~ (hecho, arriba); y un procedimiento de vuelo leído que dé niveles con fuente
sustituiría al vocabulario de diseño.

### Perfiles por entorno (2026-11-03, unidad 8 del trabajo en paralelo)

La interfaz del equipo tiene una vista por entorno —órbita baja, cislunar, Luna y Marte— y EMMA no
tenía el perfil cislunar. **Hecho:** perfil `cislunar` (Orion entre la Tierra y la Luna), entre
`leo` y `lunar-surface`, con lo que Artemis II observó (9 días, 1 hora y 32 minutos; 252.756 millas
en el punto más lejano; el corte previsto de unos 40 minutos tras la Luna, que no es retardo), la
guía de referencia de Orion (trajes para un regreso de varios días, sin envíos frecuentes de
repuestos) y el paso por los cinturones de Van Allen; cuatro fichas nuevas. Y dos aspectos más en
todos los perfiles, **polvo de superficie** (regolito y Apollo con el informe de evidencia del HRP;
el polvo de Marte con percloratos, medido por Perseverance) y **ciclo de día y noche** (16
amaneceres al día en la estación, 14,5 días de luz y de noche en los lugares de Apollo e
irregular en el polo, sol de 24,6 h); cuatro fichas nuevas más. Sigue descriptivo: nada que decida
lo lee, la huella de reglas no cambia y el perfil no tiene cuerpo de efemérides (la Luna no está
anotada en EMMA). **Sin fuente:** el polvo a bordo de la estación, de Orion y en el tránsito, y la
luz durante el tránsito y en Orion, quedan «sin verificar» con lo que se buscó. **No hecho:** Gateway
no se da por parte de las misiones de hoy (su página se está actualizando tras la reorganización de
Artemis de 2026; solo entra una frase de un plan de 2021); ningún perfil de róver presurizado ni de
base, por falta de fuente leída para los diez aspectos; ni EVA frecuentes ni el sol de Marte en
horas y minutos (la página leída da 24,6 horas).

### Pruebas psicomotrices: las de NASA, no las del DSM-5-TR (2026-11-03, unidad 5)

Petición del usuario: «que las pruebas psicomotrices sean las que vengan indicadas en el DSM-5-TR o
el protocolo de la NASA». **Hecho: las de NASA.** Guía de medida nueva `cognition-battery`
(`backend/app/data/measurement_guides.json`, `GET /api/guides`) para la batería Cognition del
protocolo Standard Measures, la que se pasa en la ISS: las diez pruebas en su orden de
administración (MPT, VOLT, F2B, AM, LOT, ERT, MRT, DSST, BART y PVT), qué mide y cómo se hace cada
una, y lo leído de cómo se pasa (rondas de práctica, panel táctil sin ratón, el cuestionario previo
y las condiciones del estudio normativo en Tierra) y de cuándo en vuelo (el portátil de la HRF en
Columbus, el calendario de Dev et al. 2024 y las sesiones de Standard Measures). Sus indicadores
son los diecisiete de la batería y los dos de la PVT del catálogo. Cada paso cita frases leídas de
fichas que ya existían (Basner et al. 2015, releído el 2026-11-03 para el procedimiento; Dev et al.
2024; Hardy et al. 2025; el informe de evidencia BMed del HRP). **Sin fuente, dicho en
`not_found`:** las instrucciones literales de la pantalla de cada prueba, si en vuelo rigen las
condiciones del estudio de Tierra, y qué intervalos usa hoy la PVT de la batería (2 a 5 s según el
artículo de 2015, 1 a 4 s en lo leído de la PVT-B). Sin rangos ni lectura del resultado
(invariante 7): la puntuación de 0 a 1000 que da el programa no se copia. **No el DSM-5-TR:** ver
«No se adopta, y por qué».

### Vista que sigue la cara (2026-11-03, demostración)

La consola tipo tableta (§5.40 de `compliance/hmi-state-of-the-art.md`) dejó fuera, «por ser
hardware», el **seguimiento ocular** de las notas de voz del equipo, y el giro por giroscopio lo
volvió a nombrar como el límite que no arregla ningún código: el giroscopio no sabe si la persona
gira con la tableta, su cara sí. El usuario pidió integrarlo como demo. **Hecho, rotulado
«demostración, sin validar»:** «Seguir la cara (demo)» en el grupo de girar, apagado por defecto;
la cámara frontal y MediaPipe Face Landmarker, todo dentro del paquete y sin red, sacan el giro de
la cara sobre la pantalla de la recta entre los ojos, y la vista va al cuadrante con la histéresis
del sensor. Con dos caras no gira; con el sensor también encendido, manda la cara mientras la ve.
Privacidad (principios §2 y §12): la cámara solo con el modo, apagada con la privacidad y con la
ventana oculta, «Cámara encendida» siempre a la vista, ningún fotograma guardado ni enviado, nada
en el registro firmado y nada inferido de la cara (invariante 7). **No es seguimiento de la
mirada** ni mide nada de la persona. **Queda abierto:** probarlo con una tableta y con casco, gafas
y poca luz; y decidir si el registro de uso de MediaPipe (parado por la CSP y por
`blockForeignFetch`) justifica otra biblioteca.

### Sensor de presencia con modo incógnito, sin hardware nuevo (2026-11-05, demostración)

La idea 16 de `prioridades-evento.md` («sensor de presencia con modo incógnito», ideograma P3)
estaba en «Después del evento o descartado» por necesitar hardware. La cámara de «Seguir la cara»
ya cuenta caras, así que **hecho como demostración, sin validar** (§5.40 de
`compliance/hmi-state-of-the-art.md`, `frontend/src/lib/faceCompany.ts`): con la cámara encendida,
si ve más de una cara durante 1,5 s seguidos (histéresis declarada como parámetro de diseño de
EMMA, sin fuente; se da por ida tras 3 s sin verla), EMMA **propone** «Hay otra persona delante:
¿activo la privacidad?» con un toque, o, con el modo «Privacidad automática con otra cara», **la
pone sola y lo dice** (franja y lector de pantalla). La privacidad apaga la cámara, como siempre:
la puesta sola se queda hasta que la persona la quita, y la cámara no vuelve sola. Principios §2 y
§12: solo se usa cuántas caras hay, ningún fotograma se guarda ni sale, nada en el registro, nada
inferido de nadie (invariante 7). **Queda abierto:** probarlo con personas (la cámara falsa no
tiene caras), y un sensor de presencia de verdad o un filtro físico, que siguen siendo hardware.

### EMMA «tipo Jarvis»: el cerebro del asistente (2026-11-03, unidad A)

Petición del usuario: un asistente «tipo Jarvis» para toda la interfaz, manos libres, con
iniciativa y con memoria de la conversación, con el mejor modelo local que quepa en el equipo y
también como cerebro de Polaris. **Hecho, el backend** (las unidades de interfaz, palabra de
activación e iniciativa van aparte): `GET /api/assistant`, `POST /api/assistant/turn` y
`POST /api/assistant/audio` (`app/assistant/`, `app/api/assistant.py`). El modelo
(`qwen3.5:9b`, medido en este portátil con 24 órdenes reales frente a gemma4:12b, ministral-3:8b y granite4.2:8b; `backend/app/core/config.py`) elige una intención de un
catálogo cerrado (`data/assistant_intents.json`: abrir pestañas y guías, leer estado, alertas y
rutinas, girar, modos de pantalla, voz, PVT y Cognition) y redacta una frase que solo se dice si
pasa cuatro barreras (lenguaje, cifras, no recetar y esquema); si no, se dice el texto del backend
tal cual, y sin modelo el turno sale igual por palabras clave. Ve solo lo que el backend ya da a
esa consola, y en Tierra hasta su corte de retardo. Las escrituras (diario, dolor, reconocer una
alerta, nivel de misión, modo seguro) **solo se proponen** con el cuerpo exacto de su ruta y lo que
dijo la persona; las firma ella desde la interfaz (principios §2: el modelo no genera acciones
clínicas). Clase C segregada (`compliance/software-safety-classification.md` §2.2). El historial
lo guarda la consola y el backend lo olvida al responder. Polaris pasa a ese mismo modelo
(`docs/polaris-divergencias.md` §19). **Queda abierto:** validar el modelo con personas, más allá
de la batería de frases del equipo; que el diario no tenga un indicador de sueño («apunta que he
dormido mal» no tiene dónde anotarse y el asistente lo dice); y que solo el dolor distinga en lo
firmado que llegó por el asistente.

**Que entienda la aplicación (2026-11-04).** Petición del usuario: «la IA no entiende la
aplicación». Cada pestaña y panel del inventario dice qué hay dentro (`about`), el modelo ve en
cada turno los paneles que más se parecen a la frase y ejemplos de frases de la calle, y una
pregunta por otro tripulante la contesta el backend con el estado de esa persona (antes se
contestaba con los datos del de la consola). Se mide con una batería de frases naturales que se
queda fuera de todo lo que ve el modelo (`backend/tests/data/assistant_nl_eval.json`,
`scripts/assistant_bench.py`); detalle y cifras en `compliance/hmi-state-of-the-art.md` §5.43.3.

### Qué se comparte y qué no (2026-11-04)

Principios §2 (local-first) y §12 («mantener localmente los inputs sensibles en bruto»): EMMA los
cumplía, pero la tripulación no tenía dónde verlo, y lo que EMMA **no** protege no estaba dicho en
ningún sitio. **Hecho:** `GET /api/sharing` (`app/sharing.py`, `data/data_sharing.json`) y su vista
«Qué se comparte y qué no» en las dos consolas (§5.45 de `compliance/hmi-state-of-the-art.md`): por
tipo de dato, si sale a internet, lo ve Tierra con el retardo, se queda a bordo, solo vive en la
consola o no se guarda, y si lo impone el código, en parte o no. Las pruebas cotejan la tabla con el
código (lista blanca de `egress`, rutas con corte, símbolos y pruebas citados, ficheros de la
consola, paneles que Tierra no monta) y dos campañas de mutantes. **Dicho sin adornos:** no hay
notas personales que Tierra no vea; el corte del retardo lo pide la consola, el backend no
autentica a nadie; y en el prototipo las dos consolas comparten máquina. **Queda abierto:** si se
quiere una nota reservada a la tripulación, es decisión del usuario.

### Guía de glucosa capilar (2026-11-04)

El enunciado pone de ejemplo la glucosa en mg/dL, y las guías de medida no tenían la del
glucómetro: el catálogo solo tenía la de laboratorio (2345-7, suero o plasma), y una guía de
glucómetro apuntada a ella mentía sobre la muestra (invariante 2). **Hecho:** indicador nuevo
`glucose-capillary`, LOINC 41653-7 («Glucose [Mass/volume] in Capillary blood by Glucometer»;
componente Glucose, propiedad MCnc, sistema BldC, escala Qn, método Glucometer, ACTIVE, unidad de
ejemplo mg/dL), con la ficha leída en tx.fhir.org con LOINC 2.83 (`codes.DESCRIPTIVE_LOINC`), y
guía `capillary-glucose` (`GET /api/guides`) con cada paso de la página de los CDC «Monitoring Your
Blood Sugar» o de MedlinePlus «Blood sugar test». Es **descriptiva** (`DESCRIPTIVE_ONLY`): ninguna
fuente leída da un umbral para una tripulación sana, y no se simula, así que no mueve la tasa de
falsa alarma ni la sensibilidad (invariante 5). La glucosa de laboratorio sigue como estaba.
**Sin fuente, dicho en la guía:** si hay glucómetro a bordo de la ISS y cómo se pincha el dedo en
microgravedad.

### Sincronizar con el enlace roto (2026-11-05, idea 10)

La conversación de ideación pone la «pérdida de comunicaciones» entre las variables de misión, y la
especificación (§12) pide sincronizar con Tierra cuando hay enlace. El ideograma del usuario (P3)
pide la idea 10 de `prioridades-evento.md`. Hasta ahora la consola de Tierra solo descontaba el
tiempo de luz. Con «Comunicaciones: fuera de servicio» declarado, seguía «recibiendo» (lo de arriba,
C5). **Hecho:** un asiento firmado propio, `simulated-link` (`record-integrity.md` §3.29,
`core/link_sync.py`, `GET/POST /api/link-sync`). Una persona declara a bordo el enlace con Tierra
simulado caído o restablecido desde un instante. El corte de Tierra se queda en la caída, y lo
firmado después espera a bordo: la tripulación ve «N asientos pendientes de enviar a Tierra
desde…». Tierra ve «Tierra tiene datos hasta…, faltan N por llegar». Al restablecerse, lo retenido
llega entero y en orden un tiempo de luz después. El registro es la fuente: no se copia, no se
pierde ni se reordena nada (§5.47 de `hmi-state-of-the-art.md`). Nada que decide lo lee
(invariante 5).

**Dicho sin adornos:** no hay enlace real ni se mide. Las dos consolas leen el mismo registro en
la misma máquina, y por eso Tierra puede saber cuánto le falta, cosa que en vuelo no sabría. La
declaración del sistema Comunicaciones sigue siendo **solo texto** (decisión del usuario del
2026-10-21) y no corta nada: hay dos declaraciones que pueden discrepar.

**Queda abierto:**
- **Unificar el enlace simulado con la declaración de Comunicaciones.** Lo decide el usuario.
- **Las ecografías, el dolor y el historial de Tierra.** Se cortan con el reloj (`arrivalCut`) y
  todavía no siguen al enlace caído.
- **La crónica.** No cuenta los cambios del enlace.

### No se adopta, y por qué

- **El DSM-5-TR como fuente de las pruebas psicomotrices** (petición del usuario, 2026-11-03): es
  un manual de criterios diagnósticos; la agitación o el enlentecimiento psicomotor los observa un
  clínico, y el manual no indica una batería de pruebas que pasar. Tomarlo como pauta convertiría
  EMMA en diagnóstico (invariante 7), y ya estaba descartado en `prioridades-evento.md` §5. Es una
  decisión de alcance: el DSM-5-TR no se ha leído ni se cita como fuente. Las pruebas son las del
  protocolo de NASA (guía `cognition-battery`, arriba).

- **Índice único de salud "87/100"** (conversación): una cifra agregada esconde qué cambió, que
  es lo que la especificación pide mostrar (§2, §10). El IMM de NASA ya tiene un *Crew Health
  Index*, y es de planificación previa a la misión.
- **Líneas base por fase de misión** (§6 "más adelante"): cambiaría el eje de validación
  (invariante 5) sin datos que lo validen.
- **Trayectoria esperada con y sin contramedida** (KB §3.2): no hay datos de respuesta con que
  calcularla; sería inventar.
- **NAIRAS** (conversación): sin API ni fuente verificada.
- **Nodo de salud en hardware** (ZeroKeyUSB): pospuesto por la propia especificación (§15).
- **Umbrales personales que cambien alertas** (§3 Astronauta): mueven el eje de validación
  (invariante 5) sin datos que lo validen. Solo con una decisión expresa y las dos métricas
  reportadas juntas.
- **«% de adherencia» al ejercicio** (§9): exige una pauta prescrita con la que comparar. Lo que
  sí hay desde el 2026-11-02 (decisión del usuario, gamificación del reto) es un recuento sin
  porcentaje: las rachas de las medidas periódicas (`routines.streaks`, «N periodos seguidos»
  rotulado «ritmo de diseño»), fuera del riesgo y de las alertas.
- **Refugio por módulo e inventario de alimentos** (KB §7 y §6): serían factores de blindaje y
  existencias inventados; EMMA no modela una nave concreta.
- **Matriz de correlaciones entre variables** (conversación): sobre datos del simulador sería
  circular.
- **Deuda de sueño** (KB): exige una «necesidad» de sueño sin fuente.
- **Firma inmune del tripulante desde OSD-288, astroquery como capa de contexto general y «59
  astronautas» en OSD-343** (conversación): tropiezan con premisas ya desmentidas (`CLAUDE.md`,
  «Minas conocidas»).
- **La triple clase operacional / de conocimiento / inferible** de cada variable (KB §9): separar
  las dos primeras exige juicio caso a caso, sin regla escrita.

### Pendiente

Exige leer una fuente (no se inventa un límite ni una cita):

- ~~Exposición personal a la luz~~: leída en la undécima ronda (F3). NASA no publica un límite
  personal (NASA-STD-3001 Vol 1 y Vol 2, OCHMO-TB-026, informe de evidencia del HRP, revisión
  de NASA Ames y el estudio Lighting Effects); la única recomendación con cifras para la persona
  es de Tierra (Brown et al. 2022, EDI melanópica en el ojo) y sus autores la excluyen del
  trabajo de noche. Se enseña junto a la luz de cabina, con sus frases, y no se evalúa: EMMA no
  mide la luz en el ojo de nadie (`evidence/light_exposure.py`).
- ~~Rótulos intermedios de la escala hedónica: sin fuente accesible.~~ Leídos en la decimotercera
  ronda en un informe de JSC de 1981 (NTRS 19820015234). La papeleta que usa NASA hoy se buscó en
  la decimocuarta (ISS Research Explorer, Douglas et al. 2025, NTRS) y no está publicada; entran a su
  lado la leyenda de Douglas et al. 2025 y un panel de JSC de 2015 (`instruments_read.json`).
- Tiempo de tripulación de las contramedidas: la undécima ronda dio con frase dos más (OCHMO-TB-031
  y OCHMO-MTB-009) y la decimotercera una más (Mehta et al. 2017, la muestra de saliva); quedan 33
  sin cifra, buscadas en OCHMO, NASA-STD-3001 Vol 2, los informes de evidencia del HRP, NTRS y PMC, y
  ninguna fuente leída da contraindicaciones (siguen «pendiente de revisión médica»). Buscado otra
  vez el 2026-11-05 (rama «Evidencia», §5.46 de `hmi-state-of-the-art.md`): siguen 33. Lo más cercano
  vuelve a ser de otra acción (la aplicación ISS FIT, con un objetivo de menos de 15 minutos de
  registro a la semana en un resumen de un concurso, no en una fuente de NASA leída; los 30 minutos
  de cada comida, que son de comer y no de anotar) y no se aplica.
- Lo que queda sin verificar del registro de evidencia (`GET /api/dossier/references`): ~~dos
  campos~~ **81 campos en 58 de las 258 fichas**, contados sobre `main` (6372fad) el 2026-10-31
  leyendo `ref.unverified` de cada ficha de `registry().values()` (`app/evidence/registry.py`; es lo
  que suma `unverified_fields` de `GET /api/dossier/references`): 33 fechas (páginas de agencia sin fecha de publicación: las de bancos de
  prueba, catálogos y portales de la decimoquinta y la decimosexta, y las once del contexto y las seis
  de §17 de la decimoséptima y la decimoctava, que solo dicen cuándo se actualizó la página, o nada),
  21 entornos y 21 poblaciones (las portadas de los informes de evidencia del HRP que §5.38.5 leyó
  solo en su portada: un informe no tiene un entorno de estudio hasta que se lee) y 6 organizaciones
  (Conkin 2017, PMData, RELAX, el reto de Space Apps, Van Hoy 2026 y Grigor'ev 1994, que ningún
  registro da). Entre las fechas siguen las dos de siempre: la del listado de huecos del Roadmap, que
  no la publica (buscada otra vez en la decimotercera ronda; el IRP Rev T fecha el 5/7/2025 la última
  revisión del contenido del Roadmap, sin adoptarse como fecha del listado: decidir si vale), y la
  del listado de riesgos, que tampoco (decimosexta ronda, E9: cada página de riesgo lleva la suya).
  La decimonovena ronda tiene una unidad para esto (§5.39.3 de `hmi-state-of-the-art.md`); esta
  cifra es la de su entrada, no la de su salida. **Al día el 2026-11-05** (rama «Evidencia», §5.46
  de `hmi-state-of-the-art.md`, contado igual sobre 337 fichas): **52 campos en 52 fichas → 51 en
  51**, 47 fechas y 4 organizaciones. Ya no queda ningún entorno ni población sin verificar. Se
  cierra la fecha del libro de nutrición del HRP (`hrp-nutrition-human-adaptation-2020`, «2021»: la
  página de NASA del libro da «Download Second Edition PDF – 2021»). Las 47 fechas son páginas que
  no publican la suya (solo «Page Last Updated», o nada), entre ellas las nueve del módulo SEER, y
  las dos de siempre del Roadmap; las 4 organizaciones son Conkin 2017, Van Hoy 2026 y David 2021,
  de la revista de la Aerospace Medical Association (página y PDF con 403, Crossref sin
  afiliaciones), y Grigor'ev 1994, en ruso y sin afiliación en PubMed ni Europe PMC.
- Cálculos renales (decimosexta ronda, E9; cerrado en parte en la decimoctava, U5, §5.38.5 de
  `hmi-state-of-the-art.md`): los ocho analitos de la orina de 24 horas con que el informe de
  evidencia del HRP (2024) valora el riesgo entraron al catálogo como descriptivos, siete con LOINC
  leído en su ficha y la unidad de su propiedad (6874-2, 2701-1, 3087-4 y 6687-8 en mg/día; 27378-9
  en pH; 2956-1 en mmol/día; 2694-8 en mOsm/kg) y la sobresaturación del oxalato cálcico con código
  propio, porque LOINC no tiene ese cociente. Se registran y se enseñan; el estado no los lee y
  ninguna cifra se compara con los umbrales del informe. Leídos ya las portadas de los demás
  informes de evidencia y el anexo B de operaciones del informe renal. Queda pendiente la
  sobresaturación de la brushita (decidir si entra) y las tablas del informe, que son imágenes.
- Coste de medir (`GET /api/measurement-cost`): la decimocuarta ronda leyó el tubo de los
  leucocitos en vuelo (EDTA, Crucian et al. 2015) y enlazó las entradas de los tres calculados; la
  decimoquinta, el gel de la ecografía y el tubo de la serie roja (24 pares sin clasificar en las
  tres dimensiones de entonces). La decimosexta (E17, §5.36.17 de `hmi-state-of-the-art.md`) cerró
  el hueco de la lista de la base de conocimiento §9: sus doce términos tienen sitio
  (`summary.kb_coverage`) y entran como dimensiones masa, volumen y potencia del equipo (cifras solo
  copiadas de una frase leída), calibración, y formación y guía del operador. Leído: la calibración
  del SLAMMD (informe diario de 2019), el gas de calibración del analizador de la prueba de esfuerzo
  (resumen de instalaciones de NASA HRP de 2023) y la guía desde Tierra de la ecografía de la
  yugular izquierda (Marshall-Goebel et al. 2019). Sin fuente: la masa, el volumen y la potencia de
  todos los equipos de EMMA (el único tope leído es el del rack, y no se escribe como consumo), la
  densidad de la orina, si el UMS se usó tras 2011, de cuál de los dos dosímetros llega la dosis
  acumulada, los consumibles de los sensores puestos y de los aparatos sin muestra. ~~456 pares sin
  clasificar: 24 en las tres dimensiones de antes y 432 en las cinco nuevas.~~ La decimoctava ronda
  (U18, §5.38.18) leyó la calibración (DOSTEL y los REM del SRAG, los analizadores de Tierra de la
  serie roja, la recalibración del fabricante del actígrafo) y la formación (la flebotomía instruida
  antes de la misión, la camiseta de la CSA en HERA, con dos palabras nuevas, `station-trained` y
  `analog-trained`): 456 → 436. Después entraron diez indicadores descriptivos con su regla de
  procesado leída (las dos densitometrías de §5.38.3 y los ocho analitos de orina de §5.38.5: 80
  pares nuevos, 18 clasificados). Hoy (`GET /api/measurement-cost`, `summary`, `main` 6372fad,
  2026-10-31): **498 pares sin clasificar** de 99 indicadores: procesado 2, resultado 4, consumibles
  30, masa, volumen y potencia 97 cada una, calibración 84 y formación 87; 2 indicadores con las ocho
  dimensiones decididas.
- Radiación y perfiles (decimocuarta ronda): ~~ninguna fuente leída da la fase actual del ciclo
  solar~~ (decimosexta ronda, E8, §5.36.8: la nota de NASA y NOAA del 15 de octubre de 2024, que
  anuncia el periodo de máximo del ciclo 25, se enseña fechada y solo descriptiva junto a la
  radiación; ninguna nota de 2025 o 2026 se encontró). Con ella, el panel dice que a bordo de
  Orion avisa HERA (ficha propia; EMMA no lo lee) y lo que una fuente dice del fin del refugio: de
  NASA, nada leído; un preprint de 2025 con datos de Marte, como fuente, sin umbral de EMMA. Siguen
  sin fuente un criterio de NASA para salir del refugio, la cifra de los umbrales de HERA y un plazo
  de evacuación propio del tránsito a Marte; la proyección de dosis sigue suponiendo tasa
  constante. Sin leer: el texto completo del artículo del SLS-1 ~~, NASA/TM-20240012058 (MEDPRAT
  frente al IMM; el PDF pasa de 10 MB)~~ (NASA/TM-20240012058 se leyó en la decimoquinta ronda, D15,
  §5.35.15, como dice arriba su línea: no fecha la sustitución del IMM ni nombra a IMPACT; y en la
  decimoctava, U14, §5.38.14, el resumen descargable de NTRS 20240013005, que tampoco la fecha; las
  diapositivas de esa presentación no están en NTRS). De la radiación, la decimoctava leyó además las
  series del ciclo solar de NOAA SWPC: entra una sola cifra con su mes (manchas suavizadas, marzo de
  2026, 94,4) y EMMA no deduce la fase. Los análogos ARGOS, NEEMO y vuelos parabólicos se leyeron en la
  decimoquinta ronda, y el Kraken, el NBL y las cámaras de altitud en la decimosexta (E12), con la
  duración y la matriz banco × peligro RIDGE (deducción de EMMA salvo donde una página de NASA nombra
  el peligro). De los bancos de prueba siguen sin fuente dónde quedan los datos de cualquiera de
  ellos; la duración del NSRL, ARGOS, el NBL y la ISS; los participantes de la Antártida, ARGOS, los
  vuelos parabólicos, el NBL y la ISS; y el proveedor u operador de HERA, la Antártida, MMEA, ARGOS
  y la ISS (el hábitat de CHAPEA lo imprimió ICON; ninguna página leída nombra a BIG).
- Los datos humanos de NLSP, LSDA y LSAH exigen solicitud.
- ~~Mapa de datos humanos: reposo en cama, ISS Research Explorer, data.nasa.gov, controles y las
  diez áreas del Twins Study~~: hecho en la decimosexta ronda (E11, `GET /api/human-datasets`;
  `compliance/hmi-state-of-the-art.md` §5.36.11). ~~Queda leer los otros seis reposos en cama humanos
  de OSDR~~ leídos en la decimoséptima ronda (U10, §5.37.10: OSD-195, 198, 353, 370, 942 y 946 en
  `GET /api/human-datasets`, con su acceso de la API de OSDR; OSD-353 fuera del enumerado de entorno
  porque junta cosmonautas de la ISS, reposo e inmersión seca, y OSD-370 con su ficha contradicha,
  dicha). Sigue sin saberse dónde quedan los datos de AGBRESA (el artículo de Clément solo dice «made
  available by the authors»; el de resultados de Kramer 2021, leído en la decimoctava, §5.38.15, no
  tiene declaración de disponibilidad de datos).
- Sentido en vuelo junto a la línea base (§5.35.14 y §5.36.16): la decimosexta ronda leyó la
  respiración (discutida), la saturación, el sueño frente a antes del vuelo, la PVT y la serie
  roja, los leucocitos y la orina; la RMSSD pasó a «discutido». Buscados y sin sentido leído: los
  lapsos de la PVT, el desfase circadiano, la caída ortostática, el VCM, la CHCM, el cociente
  neutrófilos/linfocitos y sus porcentajes, la vitamina D, la fosfatasa alcalina, el calcio y el
  cortisol salival (y, de D14, el área de la yugular interna derecha). ~~Del resto de la
  bioquímica, las hormonas y los marcadores tumorales no se buscó nada.~~ Buscado en la decimoctava
  ronda: la bioquímica (U16, §5.38.16: dieciocho analitos, ocho fichas nuevas; dos sentidos leídos,
  el magnesio sube —Smith 2015— y las proteínas totales sin cambio —Zwart 2022—, y dieciséis
  «buscado y no encontrado» con lo leído, entre ellos la PCR, que solo cambia después del vuelo) y
  las hormonas y los marcadores (U17, §5.38.17: trece indicadores, seis fichas nuevas; un sentido, la
  LH sube —Strollo 1998, cuatro varones—, y doce «buscado y no encontrado»: de los marcadores
  tumorales no hay nada en vuelo). Queda sin leer el material suplementario del Twins Study, que da
  su bioquímica, y el texto completo de Markin 1998, Lee 2020 y Zwart 2013. El texto completo de Xu
  2013 sigue cerrado (403, fuera de PMC): la SDNN y la RMSSD no se nombran en nada leído.
- ~~Matriz «ISS vs Artemis vs Mars» (KB §15 P1).~~ Hecha en la decimosexta ronda (E7,
  hmi-state-of-the-art §5.36.7): `GET /api/mission/profiles` y la matriz perfil × aspecto en la
  consola de Tierra, con un octavo aspecto, la capacidad o autonomía médica, construido solo con
  frases ya leídas (la carga rechaza una que no lo esté). Descriptiva: nada que decida la lee.
  Queda sin fuente: ninguna frase leída ata los niveles de asistencia IV y V a un destino
  (HRP-48034, HRP-48035 y la tabla de NASA-STD-3001 Vol 2 Rev A que rotula el memorando, sin leer),
  y EIMO no tiene frase leída con ficha: su descripción en `evidence/links.py` es de EMMA.
- El hito R+90 del selector «Momento» (decimosexta ronda, E13): ni Standard Measures (texto y
  tablas suplementarias) ni OCHMO-MTB-013 dan una toma a los 90 días del regreso; sigue de diseño.
- Credibilidad de las capas que predicen o infieren (KB §2.3): NASA-STD-7009B leída en la
  decimosexta ronda (E10, §5.36.10), con una ficha por cifra INFERIDA o PREDICHA y sus once factores
  en palabras (`/api/framework` → `credibility`). Ninguna capa evaluada con las tablas de nivel de la
  norma, y sin guía publicada para la revisión B. Su Apéndice D (criticidad del uso) se leyó en la
  decimoctava ronda (U14, §5.38.14): cada capa dice en palabras lo que hay en los dos ejes de la
  matriz (`credibility.criticality`), pero la matriz no se aplica —fijar la criticidad corresponde
  a la autoridad técnica de NASA (§4.1)— y ninguna capa tiene criticidad registrada.
- ~~Contramedidas en investigación (KB §4 «contramedidas de fluid shift en investigación», KB §3.2
  y la matriz RIDGE de la conversación: realidad virtual, LBNP, brazaletes, gravedad
  artificial)~~: enseñadas aparte en la decimosexta ronda (E15, `GET /api/countermeasures/research`
  y una sección plegada de la biblioteca), con la frase literal de NASA (2022), del informe de
  evidencia del SANS (2017) y de la página de AGBRESA; fuera de la huella de reglas, de las
  familias y de toda recomendación. ~~Queda sin leer el resultado publicado de AGBRESA~~ leído en
  parte en la decimoctava ronda (U15, §5.38.15): no hay un artículo con el resultado del estudio
  entero; el que se presenta como sus resultados, Kramer et al. 2021 (`kramer-2021-agbresa`,
  capacidad física), se leyó entero y la gravedad artificial suma sus tres frases («AG had no
  significant effect on aerobic exercise capacity», mitigó parte de las pérdidas de pantorrilla,
  rodilla y salto, y tendría que combinarse con ejercicio); los de las otras áreas (ortostatismo,
  SANS, hueso) no se buscaron uno por uno. De paso, la filiación de Clément 2022 pasó de `null` a
  KBR, la que dan PubMed y Europe PMC. Queda sin leer lo que se sepa después de 2017 del estado de
  cada contramedida.

Exige una decisión:

- Lo que queda de las lecturas de la décima ronda (lista en su apartado): la PVT, declarada y sin
  corregir (los valores que puntúan); de las escalas, solo la papeleta hedónica actual.
- ~~Redactar un TAC: hoy no redacta sus segmentaciones.~~ Decidido el 2026-10-15 que sí, y hecho
  en la duodécima ronda: redactar el TAC redacta en el mismo `commit` cada segmentación que lo
  cite, con su lápida y su binario borrado (llevaba un volumen recortado del estudio); si una
  falla, nada. Un ledger escrito antes sigue verificando (`record-integrity.md` §3.13 bis).
- ~~Las anclas de las tres escalas de autoinforme propias (ánimo, síntomas, apetito).~~ Decidido
  (2026-10-15) y hecho en la duodécima ronda: son decisión de diseño de EMMA, sin validar, y se
  publican como tal (apartado de lecturas, «Escalas»).
- ~~Salud conductual más allá del ánimo, síntomas visuales como indicador, fuerza y forma física:
  qué escala o qué código propio.~~ Decidido (2026-10-15) y hecho en la duodécima ronda: cinco
  indicadores descriptivos con su medida leída (cambio de visión del cuestionario del SANS y carga
  de trabajo NASA-TLX, con código propio; VO2 pico y prensión de cada mano, con LOINC leído en su
  ficha), que no entran en el riesgo, la huella de reglas ni el simulador
  (`codes.DESCRIPTIVE_ONLY`, `GET /api/indicators/descriptive`). Queda fuera, y dicho, el par
  isocinético de rodilla: el protocolo (AMMERD 6.1) no es público.
- ~~Nombre en español para el catálogo entero (constantes, escalas).~~ Decidido (2026-10-20) y hecho
  en la decimotercera ronda: tabla de EMMA para los 88, rotulada por origen (`ingest/names_es.py`).
- ~~`appetite-rating` no tiene rango de referencia, pero `/api/indicators` y la huella de reglas
  le dan base «observada» por defecto; corregirlo cambia `rules_version`.~~ Hecho en la
  decimotercera ronda (2026-10-20): sin rango, base `null`, y el catálogo exige rango ⇔ base.
- ~~Recuperación posvuelo dentro de la crónica del tripulante, o aparte como hoy.~~ Decidido
  (2026-10-14): dentro. Cada toma posvuelo entra en la etapa posvuelo de la crónica frente al
  prevuelo del propio tripulante, sin veredicto; el panel de recuperación sigue como estaba.
- Revisión de la biblioteca de contramedidas por un médico de vuelo (la mayoría son `demo`).
- ~~Segunda firma: si toda segunda firma de alto riesgo debe citar un informe guardado.~~
  Decidido el 2026-10-15 que sí, y hecho en la duodécima ronda: sin informe citado, con la frase
  localizada y declarada leída, la contrafirma se rechaza sin asiento; lo ya firmado no cambia
  (`app/countersign_rule.py`, `record-integrity.md` §3.24).
- ~~Posvuelo en la crónica: con muchas tomas al día, cada una es un evento; sin tope inventado.~~
  Hecho en la duodécima ronda (2026-10-16): las tomas de un indicador en un mismo día tras el
  regreso (el R+ que les da el panel) van en un solo evento, con cuántas son, entre qué cifras y
  cuántas caen dentro del rango prevuelo, sin tope; un día con una sola toma se cuenta como
  antes. El indicador se nombra en español donde EMMA tiene el nombre (el de la lectura de una
  analítica: «Linfocitos (abs.)») y las cifras llevan sus decimales y su unidad legible. Queda
  dicho: el resto del catálogo (constantes, escalas) no tiene nombre en español en EMMA —todas
  sus frases dicen el del catálogo, en inglés—; darle uno sería una tabla nueva para todas a la
  vez, y no se ha inventado aquí. (Cerrado en la decimotercera ronda: ver arriba.)
- ~~PVT, «Lo publicado»: la marca «= es el valor de EMMA» compara la cifra y no el operador del
  lapso (≥ frente a >); conviene que diga «misma cifra, distinto operador».~~ Hecho en la
  decimotercera ronda.
- ~~Volúmenes: en el esqueleto del propio TAC el dolor se alinea cerca del umbral.~~ Con el modo
  DIRECTO (decimotercera ronda) la zona anclada va a su hueso; quedan la silueta y el ancla visceral.
  Lista completa de lo que queda por decidir sobre Polaris: `docs/polaris-divergencias.md` §18,
  «Pendiente de decidir (lista vigente)». Comprobado el 2026-10-31: §18 (octava ronda, 2026-10-08,
  con su remate del 2026-10-09) sigue siendo la última sección de ese documento; ninguna ronda
  posterior ha añadido allí nada, así que esa lista es la vigente. (La cabecera del propio documento
  remite todavía al «final del §17»: está desfasada, y no es de esta página.)
- Gravedad «en Tierra (1 g)»: la frase quedó «en Tierra (gravedad terrestre)» porque el filtro de
  lenguaje lee «1 g» como una dosis; si se prefiere «1 g», hace falta una excepción acotada en
  `text_guard.py` con su campaña de mutantes.
- La muestra de saliva (`imm-viral-sample`) sigue en `demo` aunque cite Mehta et al. 2017: el
  artículo es un estudio, no el protocolo operativo. Decidir si cambia de base.
- ~~Segunda pasada pictográfica: el color de un rechazo o de una petición fallida.~~ Decidido el
  2026-10-21 y hecho en la decimocuarta ronda (C14): un rechazo del backend (4xx) en amarillo con
  triángulo y una petición caída (5xx, sin red) en rojo con cruz, en toda la interfaz desde una sola
  función (`requestOutcome`). ~~Queda una pregunta: un 409 de la ecografía (registro manipulado,
  calibración ilegible) sale ahora en amarillo por esa regla; si lo de integridad debe ir en rojo,
  es una regla en `isRefusal`.~~ Decidido (2026-10-22) y hecho en la decimoquinta ronda (D12,
  §5.35.12): los dos 409 de integridad (`integrity_ok: false` de `TamperedRecordError` y la
  calibración ilegible) van en rojo con la cruz, desde `isIntegrityBreak` en `frontend/src/lib/marks.ts`,
  que `isRefusal` excluye; cualquier otro 409 sigue en amarillo.
- La hoja a trazos del borrador (`page-dashed`, la marca de la invariante 6) se lee a 14 px como una
  columna punteada: redibujarla o no.
- `slash-circle` dice a la vez «rechazado» y «no disponible», y `play`, `stairs`, `clipboard`,
  `chip`, `pencil`, `arrow-u-turn`, la cruz gris y `ring-dot` llevan dos significados sin declararse
  sinónimos (§5.33.12): para una pasada de dibujo. Sin dibujo por falta de uno que no sea de otro
  concepto: «pieza de código», «apartadas», «ventana de días» y «signo ecográfico»
  («Contraindicaciones» y «Efectos» llevan desde la decimosexta ronda los dos dibujos de la
  biblioteca, en la tabla y en la tarjeta, §5.36.19).
- Adoptar en el repositorio el guion de capturas (vive fuera, con el Playwright del Python del
  sistema).
- Dos hallazgos del motor al describir la línea base (decimocuarta ronda, C2); arreglarlos mueve
  bases y veredicto, así que van con las dos métricas juntas (invariante 5): en el simulador el
  sueño (84 lecturas en 14 días) y la actividad (28) nunca llegan a las 100 de una base personal, y
  esas lecturas solo se juzgan contra el límite de peligro; y el respaldo de «familia» de
  `evaluate_rolling` deja fuera al propio reposo (para reposo, trabajo y comida solo junta trabajo y
  comida), en contra de lo que dice el docstring de `Context.family`. Lo segundo se midió (D16,
  E1; hallazgo 29 de `external-validation.md`) y no se adoptó (decisión del usuario, 2026-10-23):
  se mide antes con LifeSnaps o RELAX.
- ~~Derivas del simulador que lo leído contradice (decimosexta ronda, E18): la FC en reposo quedó
  «contestada» y el cortisol salival «sin respaldo en lo leído», con sus valores de antes. Decidir
  si se corrigen~~; corregirlas a 0 no cambiaba ningún nivel ni alerta de los 36 casos ni las
  métricas de MMASH, pero quitaba la subida predicha de la FC (4 casos) y del cortisol (25) y
  adelantaba 12 h la alerta de la arritmia (`clinical-decision-rationale.md`, «Revisión de lo leído
  (2026-10-23)»; `hmi-state-of-the-art.md` §5.36.18). Decidido en la decimonovena ronda (registrado
  en la entradilla de §5.39, «Decisiones del usuario en el plan aprobado (2026-10-31)»; lo detalla su
  cierre). Entre medias, la decimoséptima (U10, §5.37.10) dio sus dos lados a las cuatro derivas
  «contestadas» que no citaban ficha, sin cambiar ningún valor.
- Banda ósea inferida (C13): en vuelo, la trayectoria «si nada cambia» aún puede enseñar
  horizontes posteriores al regreso; cortarla cambiaría la banda en los 36 casos del veredicto.
- Escala hedónica (C16): si el punto 5 pasa a «Neither Like Nor Dislike», como escriben Douglas et
  al. 2025 y JSC 2015; pide una defensa nueva en el cargador.
- ~~Cadena anatómica (C3): cada día R+ con lecturas es su propio momento, sin tope; ¿agruparlos? En
  un momento pasado las tarjetas de recomendación conservan urgencia y color.~~ Hecho en la
  decimoquinta ronda (D8, §5.35.8): los días R+ se agrupan en hitos con fuente y las tarjetas de
  un momento pasado van sin el color de lo vigente.
- Clasificación de software (C15): la clase de `evidence/vault.py`, `evidence/source_check.py` y
  `evidence/citations.py`, y si la fila B de `polaris/__init__.py` aguanta, que carga también lo que
  piden elementos de clase C.
- Ordenar las comprobaciones de una alerta por su coste de medir (C6): decisión clínica, abierta.
- Enlace con Tierra declarado caído (C5): cortar lo que Tierra recibe en el instante declarado
  cambiaría lo que ve Tierra; hoy solo se dice.
- ~~La franja común, fija arriba, ocupa unos 640 de 900 px con el aviso del freno HALT abierto.~~
  Decidido (2026-10-22) y hecho en la decimoquinta ronda (D12, §5.35.12): la franja guarda solo la
  línea del aviso y la explicación se despliega debajo, fuera de ella; medido, 146 px con el aviso
  cerrado y 146 con él abierto.

### Serie continua del entorno de partículas (2026-11-11, lote «APIs abiertas»)

La especificación (§9, «Evento de radiación») pide «flujo de radiación + contexto de misión». EMMA
tenía los eventos catalogados de DONKI y la dosis de a bordo, pero no el flujo entre evento y
evento. **Hecho:** `GET /api/space-weather/series` sirve, de CCMC iSWA (NASA) por HAPI, el flujo
integral de protones ≥10 MeV de GOES en pfu y el viento solar, con unidades, edad de la consulta
y de la última muestra, y fuente (datos de NOAA SWPC redistribuidos por la NASA). Sin red, la
última serie guardada con su edad o «no disponible» (principio §2, local-first). Descriptivo: no
entra en el riesgo ni cambia umbrales; la referencia S1 de NOAA va citada y sin evaluar. **Pintada
(2026-11-14)** en la sección «Radiación» de la consola de tripulación: última muestra y curvas de
24 h. **Queda abierto:** el panel de Tierra y decidir si el flujo debe intensificar la
monitorización como ya lo hace la tasa de dosis de a bordo.

### Sección «Radiación» y lo que publica el IMM (2026-11-14)

El usuario pidió integrar la maqueta «Panel EMMA: Radiación y Salud Espacial» con el estilo de
«Inicio» y simular sus cifras «con el IMM», «solo con los parámetros del IMM». El IMM (§16) no es
código público y la especificación pide no duplicarlo: EMMA no lo ejecuta. **Hecho:** sección
`radiation` de la consola de tripulación (`frontend/src/radiation/RadiationBoard.tsx`) con datos
del estado, de la entidad Riesgo, de los perfiles, de iSWA y del historial; y `GET
/api/radiation/imm` (`evidence/imm_radiation.py`, `data/imm_ars.json`), con la única cifra de
radiación que publica el IMM: la probabilidad de al menos un síndrome agudo de radiación por misión
de referencia (informe «Ranking of Medical Conditions by Probability», 2015, iMED v5.0, ficha
`imm-ranking-2015`), cada una con su fila citada, la misión a la que EMMA asimila cada perfil con su
motivo y la salvedad del informe (referido al entorno de la ISS). Descriptivo: no entra en ningún
nivel ni alerta. **Queda abierto (sin fuente del IMM):** dosis por ubicación, pronóstico de 72 h,
índice Kp, probabilidad de evento solar y dosis por fase; la ficha «Acute Radiation Syndrome
CliFF» de la página lunar del IMM no se ha leído.

### Sexo declarado y ciclo menstrual (2026-11-14, lote «ciclo»)

El usuario preguntó si EMMA contempla las afecciones hormonales y menstruales. El catálogo tenía
estradiol, FSH, LH, TSH, T4 libre y cortisol, pero nada del ciclo, y el perfil no guardaba el sexo
por decisión (§5.36.19, 2026-10-23). **Decisión del usuario (2026-11-14):** añadir el sexo
declarado, revirtiendo esa omisión, y llegar hasta una línea base que tenga en cuenta la fase del
ciclo; la edad sigue sin campo. **Hecho (frase pública):** el sexo va en un asiento firmado aparte
(`crew-sex`, `{sex, declared_by}`), no en el perfil, lo declara el propio tripulante y se borra
solo; `GET /api/baseline-profile` → `personal_data` lo dice, con una frase nueva (`cycle`): solo
decide si se ofrece el seguimiento del ciclo, que es descriptivo, y lo que podrá ajustar la base es
la fase, no el sexo (en presente desde B3, 2026-11-15: «lo que puede ajustar la línea base es la
fase…»). Sigue cierto, con prueba, que ningún rango ni umbral depende del sexo ni de la
edad y que nada de `analysis/`, `advisor/` ni `ingest/` lo lee: la puerta vive en `api/`. La
privacidad (§12) se reescribe: por qué se guarda ahora, lo mínimo, y borrable aparte. **Queda
abierto** (resto del lote): la ingesta descriptiva del ciclo y de la anticoncepción, la evidencia y
el hueco de validación (MMASH son 24 h de varones), y la línea base consciente de la fase con las
dos métricas medidas juntas (invariante 5).

### Registros del ciclo menstrual y de la anticoncepción (2026-11-14, lote «ciclo», unidad A3)

El usuario pidió que EMMA contemplara las afecciones hormonales y menstruales. Tenía estradiol, FSH
y LH en el catálogo y nada del ciclo. **Hecho:** seis indicadores **descriptivos**
(`DESCRIPTIVE_ONLY`, `CYCLE_RECORDS` en `backend/app/ingest/codes.py`), con código propio y lo
buscado en LOINC escrito (`NO_LOINC_AVAILABLE`, `api/descriptive.py`): `menstrual-flow` (0 sin
flujo, 1 escaso, 2 moderado, 3 abundante), `menstruation-start` (1 inicio de ciclo, 0 no),
`intermenstrual-bleeding` (1 registrado, 0 declarado sin él), `ovulation-test` (0 negativo, 1
ascenso de estrógenos, 2 ascenso de LH), `contraceptive-in-use` (siete tipos, del 1 al 7, nominal) y
`basal-body-temperature` (°C). Las categorías son las palabras de la documentación de HealthKit y
de Health Connect, leídas el 2026-11-14 (`data/instruments_read.json`, quince fichas nuevas en el
registro); el número de cada una es de EMMA y se dice, como las diferencias de numeración de Health
Connect (su 0 de flujo es «desconocido»). LOINC solo tiene hallazgos nominales, una fecha, una
pregunta del FACIT, cantidades de lutropina y el método anticonceptivo con su propia lista; la
temperatura basal no reutiliza 8310-5, que es de la temperatura corporal que el estado evalúa. Van
al dominio genitourinario, sin dominio reproductivo nuevo (motivo en `codes.py`). No mueven la tasa
de falsa alarma ni la sensibilidad: el estado no los lee (invariante 5). Un anticonceptivo como
existencias va en el inventario firmado (`core/inventory.py`, `medications`), no aquí. **Queda
abierto:** la ingesta desde Apple Health y Health Connect, la línea base consciente de la fase y el
panel de las consolas (otras unidades del lote); si el anticonceptivo es hormonal no lo dice
HealthKit (su dispositivo intrauterino no distingue el de cobre), y Health Connect no registra la
anticoncepción.

### Variación por fase del ciclo menstrual: leída y declarada (2026-11-14, lote «ciclo», A4)

La base de conocimiento pide considerar las variables de cada persona y no mezclar contextos, y la
especificación (§2) pone la incertidumbre primero; EMMA validó su falsa alarma con MMASH (24 h de
varones) y no decía nada del ciclo. **Hecho:** once fichas leídas en PubMed y PMC el 2026-11-14
(la supresión menstrual en astronautas, Jain y Wotring 2016; dos revisiones sistemáticas de la
variabilidad vagal; una revisión y un metaanálisis de la temperatura; estudios con wearables) y
`data/cycle_physiology_read.json` con su cargador `evidence/cycle_physiology.py`: por indicador
(temperatura, frecuencia cardiaca, RMSSD y SDNN) y fase, la diferencia frente a la folicular con
su frase, su fuente y su clase de respaldo (el vocabulario de las derivas del simulador).
Temperatura lútea: magnitud documentada (0,23-0,7 °C); frecuencia cardiaca lútea: magnitud de un
solo estudio (3,42-3,91 lpm); RMSSD y SDNN lúteas: solo el sentido (bajan); en la menstruación,
casi todo buscado y no encontrado. La estasis yugular en vuelo (Marshall-Goebel 2019) ya tenía
ficha. El hueco queda declarado en `compliance/external-validation.md` («NO demuestra» y punto 13
de «Lo que queda abierto»), en el Control 1 de `clinical-decision-rationale.md` y en H1 y H2 del
expediente de riesgos. No entra en la base, el riesgo ni las alertas. **Queda abierto:** medir la
falsa alarma y la sensibilidad con un ciclo simulado y, después, la línea base consciente de la
fase (otras unidades del lote).

### Menopausia y perimenopausia: leídas y declaradas (2026-11-15, lote «ciclo», C1)

Muchas astronautas vuelan pasados los 40: en una misión larga la perimenopausia es el caso
probable, y la especificación (§2) pide la incertidumbre primero. El lote contemplaba la regla,
no la menopausia. **Hecho:** quince fichas nuevas leídas en PubMed y PMC el 2026-11-15 (fisiología
del sofoco con medida objetiva, su duración y su detección, la variabilidad durante el sofoco, la
ovulación en la transición, la pérdida ósea alrededor de la última regla, una revisión de la mujer
en vuelo y 9 astronautas de la ISS), dos documentos de la NASA ya fichados releídos (el informe de
evidencia de fractura ósea del HRP y OCHMO-MTB-013) y `data/menopause_physiology_read.json` con su
cargador `evidence/menopause_physiology.py`, hermano del del ciclo porque sin ciclo regular no hay
fase con la que comparar. Sofoco: frecuencia cardiaca +9-10 lpm de media y picos de +10 a +20 lpm, piel del dedo +3,9 °C,
temperatura central −0,2 a −0,6 °C, de 1,3 a 6,5 minutos (magnitud documentada); control vagal
a la baja durante el sofoco (sentido); cuántos al día con medida objetiva, buscado y no
encontrado. Perimenopausia: los ciclos anovulatorios aumentan (sentido); temperatura, frecuencia
y variabilidad en ciclos irregulares, buscado y no encontrado. Hueso: 5,8-7,38 % en la
transmenopausia frente a 1-1,5 % al mes en vuelo, «~10x» según la NASA. **En vuelo no se ha
medido nada de la menopausia** (`in_flight`, con lo buscado en PubMed y NTRS). El hueco queda
declarado en `compliance/external-validation.md` («NO demuestra» y punto 14), en el Control 1 de
`clinical-decision-rationale.md` y en H1 (ningún ajuste por fase sin ciclo regular) y H2 (los
sofocos, novena causa de falso positivo) del expediente de riesgos. No entra en la base, el
riesgo ni las alertas. **Queda abierto:** simular sofocos y medir su falsa alarma junto con la
sensibilidad, y que la línea base por fase exija ciclo regular declarado (unidad B3 y la del
estado reproductivo declarado).

### Estado reproductivo, terapia hormonal de la menopausia y síntomas vasomotores (2026-11-15, lote «ciclo», unidad C2)

El usuario amplió el lote a la menopausia. La línea base consciente de la fase (B3) no debe
ajustar a quien no tiene un ciclo regular (supresión menstrual o anticoncepción continua,
perimenopausia, posmenopausia), y para saberlo hace falta un dato declarado. **Hecho:** cuatro
indicadores **descriptivos** más en el mismo bloque del catálogo (`REPRODUCTIVE_RECORDS` en
`backend/app/ingest/codes.py`), con código propio y lo buscado en LOINC escrito:
`reproductive-status` (nominal, lista de EMMA: 1 ciclo menstrual regular, 2 ciclo irregular, 3 sin
regla por supresión menstrual o anticoncepción continua, 4 perimenopausia, 5 posmenopausia, 6 no
aplica; solo el 1 dice que hay ciclo que seguir, `REGULAR_CYCLE_STATUS`), `menopausal-hormone-therapy`
(1 en uso, 0 declarado sin ella), `hot-flashes` y `night-sweats` (gravedad de HealthKit: 0 no
presente, 1 leve, 2 moderado, 3 grave). Las palabras de las fases son las de STRAW+10 (Harlow et
al. 2012, leído en PMC), la supresión la de Jain y Wotring 2016, y la gravedad y el estado
menopáusico (iOS 27: menopause, perimenopause, none) los de la documentación de HealthKit; la
terapia, la de MedlinePlus. LOINC solo tiene el estado menstrual nominal sin lista (3146-8,
8678-5), el uso de estrógeno (98134-0, que lo cumple también un anticonceptivo combinado) y
preguntas de cuestionarios de siete días (FACIT 70376-9 y 70379-3). El estado reproductivo no es
el sexo declarado y nada de `ingest/` lee el sexo. Health Connect no registra ninguno de los
cuatro. Un estrógeno o un progestágeno como existencias va en el inventario firmado
(`core/inventory.py`, `medications`). No mueven la falsa alarma ni la sensibilidad: el estado no
los lee. **Queda abierto:** la ingesta desde Apple Health del estado menopáusico, los sofocos y los
sudores nocturnos (`ingest/wearable.py`), la puerta de B3 y otros síntomas de HealthKit
(sequedad vaginal, cambios de ánimo y de sueño, sangrado tras la menopausia) que no se adoptaron.

### Línea base consciente de la fase del ciclo (2026-11-15, lote «ciclo», unidad B3)

El usuario pidió llegar hasta una línea base que tenga en cuenta la fase del ciclo para que una
tripulante con ciclo regular no reciba falsas alarmas por la variación lútea, sin perder
sensibilidad (invariante 5; especificación §2, considerar las variables de cada persona; §14,
criterios medibles). **Hecho:** `backend/app/analysis/cycle_phase.py` lleva la base personal y la
tendencia a la fase de la lectura con un **desplazamiento** (no una base por fase, que fragmentaría
la muestra): en la fase lútea, la subida de temperatura y pulso de la propia tripulante, medida en
sus ciclos ya cerrados y acotada al rango leído (0,23-0,7 °C; 3,42-3,91 lpm); sin ciclo cerrado,
el extremo menor. La RMSSD y la SDNN no se ajustan: lo leído no da cifra. La fase lútea son 12,4
días contados hacia atrás desde la regla (Bull 2019, ficha nueva leída en PMC), solo en los días
lúteos con cualquiera de los ciclos recientes; hacen falta tres inicios de regla; un ciclo retrasado
o irregular no se ajusta; todo causal. Los límites de peligro absolutos y el rango poblacional no se
tocan. La **puerta** vive en `backend/app/api/cycle_phase.py` (el motor no lee el sexo): sexo
declarado femenino, último `reproductive-status` exactamente 1 e inicios suficientes; la respuesta
lo dice en `cycle_phase: {applied, phase, reason}` de `/api/status` y `/api/baseline-profile` (con
`until`), con frase fija del backend para la consola. `POST /api/simulate?cycle=true` da a crew-01
el ciclo del simulador, cuyas subidas de temperatura (0,4 °C) y pulso (+3,7 lpm) pasan a magnitud
documentada. **Medido** (`compliance/external-validation.md`, hallazgo 32 bis, las dos métricas
juntas): WATCH de una tripulante sana 63/71/75 → 26/43/52 de 84 (sin ciclo, 12), con la detección
en la lectura en 15 de 15, el escalado del estado de 0 a 6-7 de 15 y la febrícula lútea de 0 a 2-3 de 3
(como sin ciclo, o mejor). Controles en el Control 1 de `clinical-decision-rationale.md` y en H1/H2 del
expediente de riesgos; mutantes en `tests/mutants/cycle_phase_baseline.json`. **Queda abierto:**
la RMSSD y la SDNN (sin cifra leída), el primer ciclo sin ciclo cerrado propio, la comparación
entre tripulantes de `api/habitat.py` (no aplica la fase todavía) y cualquier medida con
fisiología real de mujeres con ciclo.

### Actualizar el EMMA instalado desde GitHub Releases (2026-11-16, lote «actualizar»)

El usuario pidió que el exe instalado pueda pasar a las versiones nuevas publicadas en
`github.com/Brillande/EMMA/releases` y que se documente la tecnología. **La especificación v1.1 no
pide nada sobre actualizar, mantener o distribuir el programa**: buscado en
`especificacion-tecnica-v1.1.md`, `knowledge-base-v1.md` y `conversacion-ideacion-v1.md`, ninguna
habla de actualizaciones del software, parches ni versiones de la aplicación (el «mantenimiento» de
la conversación, §4, es el de los repuestos de la nave). Lo más cercano son dos puntos de la
especificación y uno de `prioridades-evento.md`, y el cambio se contrasta con ellos:

- **§12, «todo modelo/regla debe estar versionado y disponer de trazabilidad»**: se refiere a las
  reglas que deciden (`core/versioning.py`, `rules_version`) y sigue igual. Lo nuevo añade la
  versión de la propia aplicación a la vista (`settings.app_version`, la que pasa Electron) y una
  prueba que exige el mismo número en `backend/pyproject.toml`, `frontend/package.json`,
  `desktop/package.json` y `backend/app/main.py`. Actualizar no escribe en el ledger: no es una vía
  de datos de salud.
- **§2 y §12, local-first y offline-first**: la comprobación es solo con botón (decisión del usuario,
  2026-11-16: nunca automática), sale por `core/egress.py` (propósito `app-update`, invariante 3 bis)
  y, en modo sin red, el panel lo dice y no falla. Instalar exige que una persona pulse «Instalar y
  reiniciar» (§2, human-in-the-loop, aplicado aquí al programa y no a la clínica).
- **`prioridades-evento.md`, punto 11, «versión de demo congelada»**: como nada se actualiza solo,
  un EMMA instalado para enseñarlo se queda en su versión hasta que alguien decida cambiarla.

Guía de uso y de publicación, con el diagrama de secuencia y por qué no se usó `electron-updater`:
`docs/actualizaciones.md`. Especificación normativa: `compliance/software-update.md`. **Queda
abierto:** el instalador no lleva firma de código, así que la huella SHA-256 asegura que se instala
lo publicado pero no quién lo publicó; volver a una versión anterior es manual.
