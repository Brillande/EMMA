# Clasificación de seguridad del software — IEC 62304

**Estado:** decidido y justificado. Clase B.
**Última revisión:** 2026-09-22, entera; el 2026-10-07, solo la clasificación de Polaris (§4 y §4.2); el 2026-11-16, solo la actualización de la aplicación (§3, §4.1 y §5)

Este documento existe porque el resto del proyecto lo cita. `record-integrity.md` §1.5 remite aquí,
el README afirma que EMMA se desarrolla *conforme a* IEC 62304 Clase B, y `CLAUDE.md` lo convierte
en invariante. Hasta hoy esa afirmación no tenía dónde apoyarse.

> **Nota de alcance de las citas.** IEC 62304 es una norma de pago. Aquí **se parafrasea**, no se
> cita literalmente, y se dice cuándo. La regla del proyecto se mantiene: no se cita un texto que no
> se haya leído en su fuente.

---

## 1. Qué decide esta clasificación

*Paráfrasis de la cláusula 4.3 de IEC 62304:2006/A1:2015.* El software de un dispositivo médico se
clasifica en tres clases según el daño que su fallo pueda causar o contribuir a causar:

| Clase | Daño posible si el software falla |
|---|---|
| **A** | Ninguna lesión ni daño a la salud |
| **B** | Lesión **no grave** |
| **C** | Muerte o lesión **grave** |

La clase determina cuánto proceso exige la norma: una Clase A pide poco más que planificación y
gestión de configuración; una Clase C añade diseño detallado por unidad, verificación de cada
unidad y trazabilidad completa. La clasificación se hace **antes** de decidir los controles de
riesgo del software, pero la norma permite tener en cuenta medidas de control externas al software
—hardware, otros sistemas, procedimientos— al estimar el daño posible.

---

## 2. La decisión: Clase B

EMMA **informa y recomienda; no diagnostica, no prescribe y no administra nada**. Esa frontera es
la que sostiene toda la clasificación, y está escrita en el código: la descripción de la API, el
tono de las recomendaciones del `advisor` y el límite declarado en
[`clinical-decision-rationale.md`](clinical-decision-rationale.md) §"apoyo a la decisión, no
prescripción".

**Por qué no Clase A.** Un fallo del software sí puede contribuir a un daño. Si el motor no señala
un deterioro que estaba en los datos, la tripulación puede tardar más en aplicar una contramedida;
si señala uno que no existe, puede aplicar una contramedida innecesaria —o, peor, aprender a
ignorar las alertas—. Ninguna de las dos cosas es "ninguna lesión posible", así que la Clase A
queda descartada.

**Por qué no Clase C.** Para que el fallo pueda causar muerte o lesión grave, el software tendría
que estar en el camino de una decisión terapéutica sin nadie ni nada entre medias. No lo está:

- No administra terapia ni controla ningún actuador. Su salida es JSON por la API y la interfaz
  de `frontend/`, que la muestra sin reescribirla.
- No diagnostica. Las recomendaciones son contramedidas de bajo riesgo intrínseco —higiene del
  sueño, ejercicio, refugio ante un evento solar, consultar con el cirujano de vuelo cuando haya
  ventana— y cada una cita la evidencia en que se apoya, de modo que quien la recibe puede
  revisarla, que es justo lo que exige la exención de *clinical decision support* de la FDA
  (§520(o)(1)(E), ver [`state-of-the-art.md`](state-of-the-art.md) §4).
- No es el sistema de monitorización primario de la misión. Es un complemento a los medios médicos
  de a bordo y al seguimiento desde Tierra cuando hay enlace.

**Supuestos de los que depende esta clase, y que hay que declarar.** Si alguno deja de cumplirse,
la clasificación hay que rehacerla:

1. **El sistema sigue sin diagnosticar.** Añadir un diagnóstico automático —por ejemplo, apoyándose
   en un modelo de lenguaje— sube la clasificación a Clase C. **Revisado el 2026-09-24** al añadir el
   borrador de interpretación con un modelo local (§2.1).
2. **Sigue habiendo otros medios médicos a bordo.** Si EMMA fuera la única vigilancia de salud de
   la tripulación, un falso negativo suyo ya no tendría nada detrás, y el daño posible dejaría de
   acotarse en "no grave".
3. **Ninguna recomendación se convierte en una orden ejecutada por otro sistema.**

### 2.1 El borrador de interpretación con modelo de lenguaje (2026-09-24)

El supuesto 1 anticipaba exactamente este caso, así que no se mantiene la clase por inercia.

**Qué hace el elemento.** `app/interpret/` pide a un modelo de lenguaje **local** un borrador que
describe las medidas ecográficas de un estudio y su evolución, para el médico de a bordo. Está
construido para no diagnosticar: recibe solo hechos firmados del registro; un verificador adversarial
revisa lo escrito; toda cifra tiene que salir de los hechos; un linter bloquea dosis, diagnósticos
(también insinuados: "compatible con") y certezas (`app/text_guard.py`); y nace **sin validar** hasta
que una persona lo acepta o lo rechaza con firma en el ledger.

**Por qué, aun así, no basta para quedarse en B.** Las barreras automáticas reducen la probabilidad
de un texto dañino, no su gravedad. El linter es un filtro de patrones y una formulación suave se le
escapa; el verificador es otro modelo, con los mismos modos de fallo; y la firma humana la pone la
misma tripulación que tiene prisa, que es donde aparece el sesgo de automatización. Si un borrador
engañoso llega a firmarse y orienta una decisión clínica, el daño posible no se puede acotar en "no
grave". Un texto que parece una interpretación clínica es, a efectos de gravedad, casi una.

**Decisión: el elemento `app/interpret/` se clasifica C; el resto de EMMA sigue B.** La norma
permite clases distintas por elemento si están segregados, y aquí lo están de forma comprobable: un
borrador no es una lectura, no entra en el análisis ni en la línea base, y no puede disparar ni
silenciar una alerta (`test_drafts_are_not_readings`). Un fallo del borrador no llega al motor.

**Qué implica.** La Clase C pide más rigor de proceso (diseño detallado y verificación por unidad
del elemento). Lo que hay hoy son pruebas que ejecutan cada barrera contra lo que debe parar
(`tests/test_interpret.py`); el diseño detallado es este documento y la docstring del paquete.
**Ningún modelo concreto está validado**: el modelo es configurable y no se ha probado contra un
servidor real en este entorno, solo contra respuestas simuladas.

**El dolor referido como hecho de entrada (2026-09-25).** `facts_for` añade a los hechos de un
estudio los últimos informes de dolor del tripulante (zona, intensidad y tipo, con los nombres que
se leen en la consola). Es solo **entrada**: el camino del borrador no cambia, y lo que redacte sigue
sin volver al motor. La instrucción del redactor le pide no relacionar el dolor con la imagen ni
atribuirle causa, y las barreras (cifras que salen de los hechos, linter, verificador) se aplican
igual (`tests/test_pain.py::test_the_draft_reads_pain_as_legible_input_facts`).

**Supuesto nuevo del que depende esta segregación:**

4. **Ningún borrador entra en un camino automático.** Si un borrador —firmado o no— alimentara el
   motor, una alerta o una recomendación, la segregación desaparece y **todo EMMA** pasaría a C.

### 2.2 El asistente de voz con modelo de lenguaje (2026-11-03)

**Qué hace el elemento.** `app/assistant/` (rutas en `api/assistant.py`) recibe lo que la persona
dice o escribe a la consola y devuelve una intención de un catálogo cerrado
(`data/assistant_intents.json`), una frase para decir en voz alta y, si la intención escribe, una
**propuesta** con el cuerpo exacto de la ruta del formulario de siempre. El modelo es local
(`Settings.assistant_model`, por loopback, temperatura 0 y salida JSON) y ve solo el texto que el
backend ya da a esa consola; en Tierra, con su corte de retardo.

**Por qué C, como el borrador.** Es un modelo de lenguaje que redacta texto sobre la salud de una
persona, y ese texto se **oye** sin que nadie lo revise antes: el sesgo de automatización es aún
mayor que con un borrador escrito. Las barreras reducen la probabilidad de una frase dañina, no su
gravedad. Así que el elemento es C, y lo que lo segrega del resto de EMMA (B) es comprobable:

- **No escribe en ningún sitio.** Un turno no anexa nada al ledger, ni al almacén, ni firma
  instantáneas de proyección (usa `routes._assess` y `routes.chronicle_status`, no `crew_status`).
  Prueba: `tests/test_assistant.py::test_a_turn_writes_nothing_in_the_ledger`.
- **No lo lee nada del análisis.** Ni `analysis/`, ni `advisor/`, ni `core/`, ni `ingest/`, ni
  `environment/` importan `app.assistant`. Prueba:
  `test_nothing_in_the_analysis_reads_the_assistant`.
- **Las escrituras son de una persona.** El asistente solo propone; la propuesta va sin quien
  firma y la interfaz la firma, tras «confirmo» o el botón, por la misma ruta y con la misma
  validación que el formulario. Fuera del catálogo: segundas firmas de alto riesgo y redactar
  asientos. Los valores, la zona, el alimento o el motivo tienen que estar en lo que dijo la
  persona; el nivel y el instante de una alerta salen del estado (`app/assistant/proposals.py`).
  El entorno de la misión se propone solo si es del catálogo y no es el vigente, con las reglas del
  almacén (`core/mission_profile_changes.check_change`).
- **Cuatro barreras deterministas** sobre cada frase del modelo (`app/assistant/guards.py`):
  linter de lenguaje (`text_guard.py`), cifras que salen del contexto o de lo dicho (también
  escritas con letras), no recetar y esquema contra el catálogo. Si una falla, se dice el texto
  del backend tal cual. Mutantes: `tests/mutants/assistant.json`.
- **Sin modelo, sigue.** Palabras clave del catálogo y texto del backend; nunca un 500.
- **La navegación por la interfaz no escribe** (2026-11-03). Abrir, leer, desplazarse, cambiar
  de consola y los modos de pantalla (`open_panel`, `read_panel`, `toggle_mode`, `switch_console`,
  `scroll`, `next_panel`, `previous_panel`) son de lectura; el catálogo no carga si una intención
  de lectura declara una ruta o si escribe una que no sea de las seis del contrato (`WRITE_IDS`:
  diario, dolor, reconocer una alerta, nivel de misión, entorno de la misión —desde el 2026-11-04,
  `mission_profile` → `POST /api/mission/profile`, descriptivo— y modo seguro).
  Sus valores son ids del inventario de la interfaz (`data/assistant_ui.json`), que solo nombra
  paneles, pliegues y modos de presentación; `read_panel` lee lo que ya está en pantalla, sin el
  modelo. Pruebas: `test_the_navigation_intents_are_reads_and_no_new_intent_writes`,
  `test_the_inventory_names_only_panels_and_display_modes` y, en la interfaz,
  `assistant/uiInventory.test.ts`; mutantes en `tests/mutants/assistant.json`.
- **El contexto se reutiliza mientras el registro no cambie** (`context.py`): por almacén,
  tripulante, consola y número de asientos, y como mucho un minuto. Cualquier anexo lo invalida
  (prueba: `test_the_context_is_reused_until_the_ledger_grows`). No cambia lo que ve el modelo:
  es la misma evaluación, hecha una vez.
- **Conocimiento del modelo, sin fuente** (`reply_source="general"`, decisión del usuario del
  2026-11-03). Lo no clínico y que no es del tripulante se puede contestar con lo que sabe el
  modelo, rotulado aparte; la segregación lo cubre igual: nada `general` entra en el ledger, el
  análisis ni una alerta (el asistente no escribe en ningún sitio). Una pregunta de salud o de la
  tripulación nunca es `general`, y una respuesta que nombre algo clínico, a un tripulante o una
  cifra con unidad clínica no se dice (`guards.general_ok`, `about_crew_or_health`; mutantes en
  `tests/mutants/assistant.json`).
- **De quién son los datos** (2026-11-04). El contexto del modelo es el de UN tripulante, y con
  `qwen3.5:9b` «¿qué tal está mi compañero?» se contestaba con los datos de crew-01 como si fueran
  del compañero. Ahora una pregunta por otro tripulante no llega al modelo: la contesta el backend
  con el resumen y las alertas de esa persona, nombrándola (`context.member_line`), o pregunta de
  quién si hay varias; y para otra persona no se prepara ninguna escritura. Una frase del modelo
  que hable de otro tripulante («tu compañero…», «crew-02…») en un turno que no es sobre él no
  pasa la barrera de cifras, que es también la de a quién se atribuyen (`guards.companion_ok`).
  Pruebas: `test_a_question_about_another_member_is_answered_with_that_person`,
  `test_a_model_reply_about_another_member_is_not_said`; mutantes en `tests/mutants/assistant.json`.
- **La dosis de radiación no es un fármaco** (2026-11-04). La negativa fija de no recetar ya no
  salta por «dosis» cuando la frase habla de radiación, de acumular o de un panel («léeme lo que
  pone en este panel de la dosis»), ni por un «tomes» que no es tomar nada («no hace falta que
  tomes la iniciativa»); un fármaco nombrado la sigue disparando. La barrera sobre la frase del
  modelo no cambia: «dosis» en una respuesta la sigue parando el linter, y entonces se dice la
  línea de la dosis de carrera del backend. Prueba: `test_a_radiation_dose_is_not_a_medication_question`.
- **El mapa de la aplicación no da poderes nuevos** (2026-11-04). Las pestañas y los paneles
  llevan un `about` (qué enseñan y qué dejan hacer) y el modelo ve, en cada turno, los que más se
  parecen a la frase (`retrieval.py`), con ejemplos de frases de la calle
  (`data/assistant_examples.json`). Es texto para elegir mejor entre las MISMAS intenciones del
  catálogo cerrado: lo que el modelo devuelve se valida igual, y un ejemplo que nombre algo que el
  catálogo no tiene no carga.

**Supuesto nuevo del que depende esta segregación:**

5. **Ninguna salida del asistente entra en un camino automático.** Si una frase o una propuesta
   del asistente se firmara sin confirmación humana, o alimentara el motor, una alerta o una
   recomendación, la segregación desaparece y **todo EMMA** pasaría a C.

**El origen de lo firmado.** Solo el informe de dolor tiene campo de origen: un informe preparado
por el asistente se firma con `note_origin` = `asistente-confirmada` y, como nota, las palabras de
la persona. El diario, el reconocimiento de alertas, el nivel de misión y el modo seguro no tienen
campo de origen y no se les inventa: lo firmado por voz no se distingue de lo tecleado (quien
firma es la misma persona, por la misma ruta).

**Lo que no está validado.** Ningún modelo: `qwen3.5:9b` se eligió con un banco de 17 casos y 24 órdenes reales (`backend/app/core/config.py`)
en un solo equipo (`core/config.py`), que orienta y no valida. Las barreras se han probado contra
respuestas simuladas; con el modelo real, solo la receta de extremo a extremo de la unidad.

**Lo que esta clasificación no es.** Una clasificación de un programa real la hace la organización
responsable, con el análisis de peligros del sistema completo —no solo del software— y la firma de
quien responde por ella. Esto es la justificación técnica de un equipo de hackathon, revisable y
declarada como tal.

---

## 3. Elementos de software y su clase

*Paráfrasis de la cláusula 5.2/4.3:* el sistema se descompone en elementos, y un elemento puede
tener una clase menor que el conjunto si su fallo no puede contribuir a una situación peligrosa.

| Elemento | Qué hace | Clase | Por qué |
|---|---|---|---|
| `analysis/risk.py`, `analysis/baseline.py`, `analysis/trend.py` | Línea base personal, desviación, tendencia y puntuación de riesgo | **B** | Su fallo produce el falso negativo o el falso positivo del §2 |
| `advisor/recommendations.py` | Recomendaciones y urgencia | **B** | Es la salida que la tripulación lee y sobre la que actúa |
| `advisor/countermeasures.py`, `app/data/countermeasures.json` | Biblioteca de contramedidas como datos: recursos, tiempo, protocolo, seguimiento | **B** | Mismo alcance que las recomendaciones: nada invasivo ni farmacológico. La carga rechaza entradas sin base |
| `environment/habitat.py`, `api/habitat.py`, `ingest/habitat_simulator.py` | Atmósfera de cabina con los límites de NASA-STD-3001 Vol 2 y excursiones | **B** | Compara con un límite normativo; no decide sobre la salud |
| `core/mission.py`, `analysis/explain.py` | Fase y día de misión; detalle estructurado de cada alerta | **B** | Solo exponen lo que el motor ya calculó; la fase no entra en el análisis |
| `analysis/inferred.py` | Banda de pérdida ósea inferida (1-1,5 %/mes, NASA); en posvuelo se detiene en el día de regreso | **B** | Rotulada INFERIDO, no se registra como medida ni genera alertas |
| `analysis/recovery_state.py` | «Recuperándose» o «empeorando» frente a una ventana antes | **B** | Descriptivo; no es un nivel ni cambia alertas |
| `analysis/data_quality.py` | Confianza de cada lectura por indicador: última, recientes de baja confianza, fuente y lo que la línea base apartó | **B** | Solo cuenta lo que el motor ya calculó, sin umbral propio ni efecto en niveles o alertas (`tests/test_data_quality.py`). No es A: una etiqueta equivocada orienta mal cuánto fiarse de una lectura |
| `analysis/forecast_check.py` | Comprobación de proyecciones: retrospectiva e instantáneas firmadas | **A** | Calibración del propio modelo; no decide nada |
| `analysis/time_to_action.py` | Tiempo desde el inicio de la alerta hasta reconocerla y actuar | **A** | Medida operativa; no decide nada |
| `analysis/radiation.py` | Radiación aguda (tiempo hasta la acción), de misión (inferida) y de carrera | **B** | Se muestra; no cambia la puntuación de riesgo |
| `api/mission.py` | Perfil del tripulante, eventos de misión y revisión humana de hipótesis | **B** | Registra decisiones humanas firmadas |
| `core/versioning.py` | Huella de las reglas con que se decide | **A** | Trazabilidad; no decide nada |
| `app/anatomy.py` | Mapa región del cuerpo → dominios y la cadena de cada región (estado, variables, evidencia, tendencia, contramedidas), para el modo anatómico | **B** | Solo presentación: compone lo que el análisis y el advisor ya dieron a `/api/status`; no puntúa ni toca umbrales. `tests/test_anatomy.py` comprueba que nivel, motivos y contramedidas coinciden con los de `/api/status` |
| `analysis/recovery.py` | Recuperación posvuelo frente al rango prevuelo propio | **B** | Descriptivo, sin umbral ni veredicto |
| `ingest/cost.py`, `app/data/measurement_cost.json` | Coste de medir cada indicador | **A** | Información de planificación; no interviene en el análisis |
| `analysis/context.py` | Correlación entre tripulantes y hábitat (hipótesis de causa compartida) | **B** | Solo ordena hipótesis rotuladas "correlación, no causa"; no toca puntuaciones ni alertas fisiológicas |
| `analysis/correlations.py`, `api/correlations.py` (2026-11-14) | r de Pearson entre pares cerrados de indicadores de un tripulante: medias diarias de lecturas medidas, 30 días, n mínimo de 10 días, intervalo del 95 % de Fisher, sin p-valor | **B** | Descriptivo, rotulado "correlación, no causa", con la salvedad de las comparaciones múltiples y de las series simuladas. Ningún módulo del análisis, del riesgo, de las alertas ni del advisor lo importa (`tests/test_correlations.py`). No es A: un r engañoso podría orientar mal a quien lo lea; no se ha argumentado una clase menor, así que queda la del conjunto (§2) |
| `analysis/alert_context.py` | Qué cambió alrededor del inicio de cada alerta (ingesta de líquidos, dieta, sueño, hábitat, EVA y bloques de trabajo, fase, evento solar, contramedidas adoptadas) y concordancia entre señales de su dominio | **B** | Solo describe: cada elemento va rotulado "correlación temporal, no causa" y cada fuente dice si tenía dato. Lee lo que el motor ya calculó y el motor no lo lee; `tests/test_alert_context.py` comprueba que niveles, puntuaciones y recomendaciones de un escenario son idénticos con y sin esta capa |
| `api/habitat.py` (`/crew/compare`, `/crew/members`), `analysis/context.py` (`coincidence`) | Un indicador en cada tripulante, contra su línea base propia y sobre el mismo eje | **B** | Solo lee: quién se desvía lo deciden la persistencia y la tendencia del motor, sin umbral propio; no firma nada ni cambia niveles. El resumen se rotula "coincidencia temporal, no causa" |
| `advisor/followup.py`, `api/countermeasures.py` | Adopción, seguimiento y cierre de contramedidas | **B** | Registra decisiones humanas y describe cambios de nivel; no introduce umbrales ni decide nada |
| `ingest/codes.py`, `ingest/fhir.py`, `ingest/wearable.py`, `ingest/pvt.py` | Catálogo, modelo canónico, wearable BLE, importaciones, PVT | **B** | Una unidad mal interpretada o una lectura perdida falsean todo lo que viene después |
| `ingest/simulator.py` | Series fisiológicas simuladas | **B** | Entra por la misma puerta auditada (`POST /api/simulate`) y alimenta el mismo motor. Sus lecturas se declaran simuladas y van firmadas por una identidad propia, pero una vez dentro pesan como cualquier otra |
| `environment/donki.py`, `radlab.py`, `ephemeris.py`, `dosimetry.py` | Meteorología espacial, dosimetría, tiempo de luz | **B** | Alimentan el riesgo de radiación y el factor de aislamiento |
| `core/ledger.py`, `core/storage.py` | Registro íntegro y persistencia auditada | **B** | Un registro alterado o una lectura que desaparece llevan a una decisión sobre datos falsos |
| `core/cache.py`, `core/config.py` | Caché con antigüedad declarada, configuración | **B** | La antigüedad de un dato externo cambia cómo se interpreta |
| `api/routes.py`, `main.py` | API HTTP | **B** | Es el único camino por el que entran y salen los datos |
| `imaging/dicom.py`, `imaging/protocols.py`, `imaging/measure.py`, `api/imaging.py` | Ecografía: lectura, calibración y des-identificación de DICOM; protocolos; medidas por calibres del operador | **B** | Una calibración mal leída o una fórmula equivocada dan milímetros falsos, y las medidas entran en el mismo análisis que las constantes. Mide lo que marca una persona y rechaza lo mal planteado: no diagnostica. La clase se revisa cuando entre la interpretación asistida (supuesto 1 del §2) |
| `pain/catalog.py`, `api/pain.py` | Mapa corporal de dolor: zonas y tipos de listas cerradas, informe firmado y la intensidad máxima como lectura | **B** | La intensidad entra en el mismo análisis que las constantes: una zona o un lado mal registrados, o un máximo mal calculado, falsean lo que se evalúa. Registra lo que refiere el tripulante: no diagnostica |
| `interpret/` (`llm.py`, `draft.py`, `cotejo.py`) | Borrador de interpretación con un modelo de lenguaje local, sin validar hasta firma humana; cotejo de presencia y ausencia de signos contra lo anotado | **C** | Un texto engañoso firmado podría orientar una decisión clínica; las barreras automáticas bajan la probabilidad, no la gravedad (§2.1). Segregado del motor: no es una lectura ni toca alertas |
| `interpret/correlation_reading.py` (2026-11-15) | Lectura en lenguaje llano, por el modelo local, de los pares de correlación que ya calculó `analysis/correlations.search` (pestaña «Aislamiento», «Correlaciones clave (IA)»). No calcula, no elige ni ordena pares; no se guarda ni se firma | **C** | Una lectura que hablara de causa o citara una cifra que no existe podría orientar una decisión; se bloquea entera si escribe una cifra ausente de los hechos, una palabra de causa o algo que `text_guard.check` rechaza, y se enseña marcada «IA · borrador». Segregada del motor: `tests/test_correlation_reading.py` comprueba que nada de `analysis/`, `advisor/`, `core/` ni `ingest/` la importa |
| `assistant/` (`catalog.py`, `context.py`, `guards.py`, `proposals.py`, `retrieval.py`, `turn.py`, `audio.py`), `api/assistant.py` | Asistente de voz con un modelo de lenguaje local: intención de un catálogo cerrado, frase hablada con cuatro barreras y propuestas de escritura sin firmar (§2.2) | **C** | Una frase engañosa se oye sin revisión previa; no escribe ni lo lee el análisis, y lo que se firma lo firma una persona por la ruta de siempre |
| `text_guard.py` | Linter de lenguaje prohibido (dosis, diagnóstico, certeza, órdenes, acciones terapéuticas, afirmaciones absolutas) | **C** | Es una barrera del elemento anterior: su fallo deja pasar un borrador peligroso |
| `pain/alarm.py` | Marca informativa "comentar con el médico de a bordo" sobre el informe de dolor | **B** | Su fallo calla una marca o la pone de más; no alerta ni entra en el riesgo (invariante 5), así que no puede silenciar ni disparar una alerta. Es la lectura del informe, como el resto del mapa de dolor |
| `decision_risk.py` | Disparador de decisión de alto riesgo sobre el comentario de una firma: exige segunda firma de otra persona | **C** | Es una barrera del borrador: su fallo deja pasar una decisión de alto riesgo con una sola voz |
| `reports/ocr.py`, `api/reports.py` | Informes escaneados: original firmado y texto por OCR local con su confianza | **B** | Una cifra mal leída puede engañar a quien no mira el original (H17); el texto no entra en análisis ni en alertas |
| `volumes/segment.py`, `volumes/assets.py`, `volumes/geometry.py`, `api/volumes.py` | Visor 3D de Polaris: volúmenes TAC/RM, segmentación automática local (TotalSegmentator), estructuras, mallas y **lesiones candidatas** | **C** | Detectar lesiones es ayuda diagnóstica automática: una lesión no marcada o una falsa pueden orientar mal una decisión. Segregado como el borrador del modelo de lenguaje: rotulado "sin validar", sin alertas, fuera del análisis (H18) |
| `volumes/privacy.py`, `volumes/skeleton_view.py`, `volumes/spine.py`, `volumes/polaris_web.py` | Visor 3D: la puerta de datos personales de un NIfTI antes de firmarlo, la vista anterior del esqueleto del propio TAC, el control de la cadena vertebral de la segmentación y el visor web de Polaris servido con los ficheros firmados | **C** | Son del paquete del visor 3D, cuyo elemento (fila anterior) es C: bajarlos de clase exigiría justificar su segregación, y no se ha hecho. Un volumen entra con un nombre en la cabecera, un esqueleto incompleto no se avisa, la figura sale cabeza abajo o en espejo, o el visor pinta mal una estructura (H18; ficha de `visor3d` y `visor3d_web/` en el §4.2) |
| `reports/deid.py` | Des-identificación del texto de los informes, con revalidación que retiene el texto si falla | **B** | Su fallo expone datos personales en la consola y en Tierra; no altera ninguna lectura ni alerta |
| `evidence/support.py`, `evidence/claims.py` | Cotejo de las cifras que EMMA atribuye a un artículo con su resumen | **A** | Herramienta de verificación de la documentación: corre como prueba `live`, fuera del producto |
| `evidence/citations.py` | Clasificación de identificadores de cita y su comprobación contra el registro | **A** | En la aplicación solo se clasifica; la comprobación con red es una prueba `live`, fuera del producto |
| `sharing.py`, `api/sharing.py`, `app/data/data_sharing.json` | Qué se comparte y qué no: tabla por tipo de dato con su destino y si lo impone el código, comprobada contra la lista blanca de `core/egress.py` y las rutas con corte | **A** | Inventario: no lee el almacén, no entra en análisis ni alertas y no sale a la red. Su fallo engañaría sobre la privacidad, no sobre la salud; por eso la carga y las pruebas la cotejan con el código (`tests/test_sharing.py`, `tests/test_sharing_console.py`) |
| `evidence/tier.py` | Nivel de evidencia de cada fuente citada, desde su registro de PubMed guardado | **B** | Un nivel mal calculado haría pasar por clínica una fuente preclínica; se calcula en código, sin modelo, y sin registro sale "desconocido" o, si el texto de la cita da señales, un nivel que solo puede degradar y va rotulado como leído del texto |
| `evidence/registry.py`, `app/data/evidence_refs.json` | Registro único de referencias: una ficha por fuente (tipo, fecha, entorno, población), citada por identificador desde la evidencia, las hipótesis y las contramedidas | **B** | Como `links.py`: se resuelve dentro de la construcción de cada recomendación y de cada hipótesis, así que un fallo suyo las deja sin emitir. Una población mal declarada presentaría como humano un estudio en animales: la carga rechaza una fuente con animales sin salvedad de alcance, y una prueba coteja la población con los MeSH guardados (`tests/test_evidence_registry.py`) |
| `evidence/osdr_data.py`, `api/osdr_data.py` | Lee en la API de datos de OSDR (Biological Data API v2) la ficha de cada estudio de OSDR que EMMA cita —título, organismo, misión, ensayo, muestras, fecha— y la compara con la del registro; una discrepancia se declara con los dos valores, no se corrige | **A** | Evidencia, no medida: no entra en el ledger, en el análisis, en el riesgo ni en una alerta; sin red sirve la última lectura con su edad o «no disponible» (`tests/test_osdr_data.py`, mutantes `osdr_data.json`) |
| `evidence/links.py` | Enlaces a riesgos del HRP y estudios OSDR | **B** | Se clasificó como A por un razonamiento equivocado —"perdería su cita, no su corrección clínica"—. `evidence_for()` se llama **dentro** de la construcción de cada recomendación, así que un fallo suyo no deja la recomendación sin cita: la deja sin emitir |
| `core/egress.py` | Única salida a internet: lista blanca por propósito, modo sin red y modo seguro, reintentos (`_net`) bajo un tope total y el control de borde de Polaris sobre lo que sale | **B** | Si deja pasar, un dato de salud o el señuelo salen en una consulta (H15, H12); si niega de más, cada cliente sirve su caché con la edad declarada (H7). Sin el tope, un `Retry-After` largo retenía cada estado de salud (H11) |
| `polaris/__init__.py` | Único punto de entrada a la copia de Polaris: dónde escribe, a qué modelo habla, el señuelo que siembra y el freno por fichero confinado al estado de EMMA | **B** | Sin señuelo sembrado, el control de borde no tiene qué buscar y no avisa de una exfiltración (H5, H15). Carga también lo que piden elementos de Clase C; lo que cada uno toma de la copia lleva la clase de su propia fila (§4.2) |
| `routines.py` | Si cada medida periódica está al día, atrasada, rota o nunca corrió | **B** | Una medida que dejó de llegar no se señala, y su silencio se parece a «todo normal» (H6) |
| `timeline.py`, `waiting.py` | Crónica, «esta semana», «qué depende de este dato» y lo que lleva tres días o más esperando por una persona | **B** | Presentación: no entra en el análisis ni en una alerta, el registro es el ledger y lo que espera sigue en su panel. Sin peligro propio en el expediente; no se ha argumentado una clase menor, así que queda la del conjunto (§2) |
| `kb.py`, `export.py` | Búsqueda sin red en la documentación de EMMA; PDF de lo que la consola ya enseña | **B** | La búsqueda devuelve otro pasaje (sin peligro propio en el expediente), o el PDF no sale o sale mal maquetado, con el texto siempre del backend (H10). No toca el registro ni el análisis; no se ha argumentado una clase menor, así que queda la del conjunto (§2) |
| `memguard.py` | Techo de memoria sobre el árbol de procesos entero de la segmentación y de la transcripción | **B** | Si no corta, el proceso ahoga la máquina y EMMA deja de responder (H11); si corta de más, una segmentación sana termina como fallida (H18) |
| `voice.py` | Dictado: un audio pasa a texto con Whisper local, en un entorno aparte | **B** | La transcripción cambia lo que se dijo; vuelve como borrador, que la persona lee y corrige antes de firmar (H16) |
| `pain_on_skeleton.py` | Las zonas del mapa de dolor, ajustadas sobre el esqueleto que se enseña | **B** | Un punto de dolor se dibuja sobre otro hueso; con un ajuste malo se dice «no se superpone». No cambia lo registrado (H16) |
| `reports/labs.py`, `reports/identity.py`, `reports/incongruences.py` | Analíticas escaneadas: cifras propuestas por confirmar, si el informe es de este tripulante y dos analíticas de la misma muestra que no coinciden | **B** | Una cifra, una unidad o un analito que no son los del papel (H17, H4), un informe ajeno dado por propio (H3) o dos cifras del mismo día confirmadas cada una por su lado (H17). Ninguna cifra entra en el análisis hasta que una persona la confirma |
| `evidence/dossier.py` | El dosier de evidencia comprobado con las reglas de Polaris: esquema cerrado, ninguna contradicción, «alta» solo con fuente y frescura | **B** | Una pieza mal formada, contradictoria o caducada respalda una contramedida (H20) |
| `validation/mmash.py`, `injection.py`, `report.py` | Validación externa contra fisiología real | **A** | Herramienta de banco de pruebas: no corre en vuelo |
| Actualizador (`/api/app-update` y su módulo del backend, el sondeo de `instalar.json` en `desktop/main.cjs`, `packaging/publish_app.py`) (2026-11-16) | Comprobar, descargar y verificar la versión nueva publicada, y lanzar su instalador cuando una persona lo pide | **B** | No toca el ledger, el análisis ni las alertas, pero cambia el software entero: un instalador corrupto o una instalación cortada dejan EMMA sin vigilar o con otro programa (H25-H28). No se ha argumentado una clase menor, así que queda la del conjunto (§2). Especificación en [`software-update.md`](software-update.md) |
| `spikes/`, `scripts/fetch_mmash.py` | Verificación de las APIs externas, descarga del dataset | — | No forman parte del producto |

---

## 4. SOUP — software de origen desconocido

*Paráfrasis de las cláusulas 5.3.3 y 8.1.2:* de cada SOUP hay que registrar título, fabricante y
versión, y qué se espera de él. Versiones exactas del entorno del 2026-09-22, con Python 3.12.10:

| SOUP | Versión | Para qué se usa | Qué pasa si falla |
|---|---|---|---|
| `cryptography` | 50.0.1 | Firma Ed25519 del ledger | Se pierde la prueba de procedencia; la cadena de hashes sigue detectando alteraciones |
| `sqlalchemy` | 2.0.54 | Persistencia sobre SQLite | La verificación del disco contra la cadena lo detecta (`record-integrity.md` §3.5) |
| `fastapi` | 0.141.1 | API HTTP | Sin API no hay ingesta ni consulta; no afecta a los datos ya registrados |
| `uvicorn` | 0.53.0 | Servidor ASGI | Igual que el anterior |
| `pydantic` | 2.13.5 | Validación en la frontera | Un dato mal formado podría entrar; el modelo canónico vuelve a validarlo |
| `fhir.resources` | 8.3.0 | Modelo canónico FHIR R4 | Afecta a la exportación, no al análisis |
| `pydantic-settings` | 2.15.0 | Configuración desde el entorno (`core/config.py`) | Arranque con una configuración por defecto; el modo offline es lo que más pesa |
| `numpy` | 2.5.3 | El simulador fisiológico (`ingest/simulator.py`); desde el 2026-09-24 también los fotogramas ecográficos (`imaging/render.py`), los fantomas (`imaging/phantom.py`) y la validación HC18 (`validation/hc18.py`) | Se caen las series simuladas, la visualización de fotogramas y los fantomas. El análisis de constantes no lo usa (`statistics` de la biblioteca estándar), y la medida ecográfica tampoco: es geometría con `math` |
| `httpx` | 0.28.1 | Los clientes que salen a la red: NASA DONKI, RadLab (OSDR) y la API de datos de OSDR (fichas de estudio); desde el 2026-11-16 también el actualizador (`software-update.md`) | El modo offline responde con el dato cacheado y su antigüedad |
| `astroquery` | 0.4.11 | Solo `jplhorizons`: distancia y tiempo de luz | Sin efemérides no hay factor de aislamiento; el riesgo se calcula sin él y se declara |
| `spiceypy` (con CSPICE N0067 de NAIF dentro) y los núcleos `naif0012.tls` y `de432s.bsp` de NAIF | 8.3.0; núcleos fijados por tamaño y SHA-256 (y el MD5 que publica NAIF para el SPK) en `environment/spice.py` | Calcular en local, sin red, el tiempo de luz y la elongación solar de los días sin efeméride de Horizons en caché (`environment/spice.py`), solo hacia Marte y desde el geocentro. Extra opcional `[spice]` en desarrollo, donde los núcleos se bajan con `scripts/fetch_spice_kernels.py` a `data/spice/`. **La aplicación de escritorio lo lleva dentro** (decisión del usuario, 2026-11-11: el retardo con Tierra, sin red desde el primer arranque): el entorno limpio instala `[desktop,spice]`, `packaging/freeze.py` declara `spiceypy` (el hook de `pyinstaller-hooks-contrib` recoge `cspice.dll`) y su `dist-info` con la licencia, y mete los dos núcleos en `_internal/spice/` solo si pasan la comprobación de tamaño y huella (si faltan, los baja con el guion; si no verifican, no congela). En el congelado se buscan primero en la carpeta configurada y después en el paquete, comprobados igual, y `/api/spice` dice de dónde salen (`kernel_origin`). `spiceypy`: licencia MIT; CSPICE y núcleos: reglas de NAIF (https://naif.jpl.nasa.gov/naif/rules.html, leídas el 2026-11-11: incluir módulos del Toolkit en el paquete de una herramienta propia basada en SPICE «is entirely appropriate», uso comercial sin tasas ni licencia, entregado «AS-IS»; los núcleos «may be downloaded and used by anyone», y redistribuirlos sin modificar está permitido; la página no dice «dominio público»; SPICE está designado TSPA para exportación, y quien fuera de NAIF produce un producto derivado que lo incorpora «must obtain her/his own export designation»). Añadido el 2026-11-11 | Sin la biblioteca o sin núcleos válidos, «SPICE no instalado» o «Núcleos SPICE ausentes» y el retardo sale como antes (Horizons y su caché). Un cálculo equivocado escalaría mal el factor de aislamiento: se mitiga con la huella de los núcleos, la verificación cruzada del tiempo de luz con la distancia y la comparación con Horizons del spike (≤ 3 µs en los 181 días de la misión); desde que SPICE va primero (decisión del usuario, 2026-11-11), además, con el contraste de cada día con la efeméride de Horizons en caché: si discrepan por encima del error declarado, se dice y se usa Horizons |
| `pandas` | 3.0.6 | **Ninguno.** Declarada en `pyproject.toml` y sin una sola importación en el código | Nada. La validación externa lee MMASH con `csv` y `zipfile` |
| `scipy` | 1.18.1 | Solo el visor 3D: `ndimage` para las mallas y las máscaras (`volumes/geometry.py`, `volumes/assets.py`, el `visor3d` de Polaris) y el remuestreo de `nibabel.processing`; licencia BSD-3-Clause. El análisis no lo usa: la línea base usa `statistics` | Sin él, una segmentación termina en fallo declarado; el volumen se guarda y se ve igual. **Faltó en el ejecutable hasta el 2026-10-04** (ver abajo) |
| Servidor de modelos local (p. ej. Ollama, licencia MIT) y el modelo que sirva | — | Redactar y verificar el borrador de interpretación. **No va en el instalador**: lo trae el paquete de modelos (`backend/packaging/models_pack.py`) desde el 2026-11-15, y la aplicación de escritorio arranca su `ollama serve` en un puerto de loopback propio; sin paquete, se configura (`EMMA_LLM_URL`, `EMMA_LLM_MODEL`). Solo se admite en loopback. Por defecto, desde el 2026-11-14, redactor `gemma4:e4b` y verificador `gemma4:12b-it-qat` (antes `qwen3.6:35b-a3b` + `gemma4:latest`, que ya no están instalados en el equipo de desarrollo). Medido con dos borradores correctos y uno con un síntoma inventado: `gemma4:12b-it-qat` 3/3; `gemma4:e4b` dejó pasar el inventado y no se usa como verificador; `qwen3.5:9b` bloqueó los correctos. Comité de una sola casa: desviación del patrón de Polaris, ver `config.py`. Probado de punta a punta con Ollama 0.34.4, también desde el backend empaquetado La licencia de los pesos depende del modelo elegido y hay que verificarla antes de distribuirlo | Sin servidor, la función se declara no disponible (503 y aviso en gris) y todo lo demás sigue igual. Un modelo que responde mal queda bloqueado por las barreras del §2.1 |
| `pillow` | 12.3.0 | Descodificar fotogramas y servirlos como PNG (`imaging/render.py`); licencia MIT-CMU. Añadido el 2026-09-24 | Un fotograma que no descodifica es un 415 con el motivo; el estudio y sus medidas no se ven afectados. No altera la imagen: sin realce de contraste |
| `nibabel` | 5.4.2 | Leer y escribir volúmenes NIfTI, remuestrear a 2 mm (`volumes/`); licencia MIT. Añadido el 2026-09-26 | Un volumen que no lee se rechaza con 422 |
| `scikit-image` | 0.26.0 | Solo `marching_cubes` para las mallas del visor 3D; licencia BSD-3-Clause | Sin malla, la estructura se ve en los cortes pero no en 3D |
| NiiVue (interfaz) | 0.69.0 | Visor de volúmenes en el navegador (cortes, regla, render 3D de mallas); licencia BSD-2-Clause | Si no carga, el panel muestra el error; el registro no se ve afectado |
| `@mediapipe/tasks-vision` (interfaz) y su modelo `face_landmarker.task` | 1.2.2; modelo float16 v1 (SHA-256 en `frontend/public/mediapipe/ORIGEN.txt`) | Solo la vista que sigue la cara, **demostración sin validar** (`frontend/src/lib/faceCamera.ts`, §5.40 de `hmi-state-of-the-art.md`): el giro de la cara sobre la pantalla para girar la vista. Apache-2.0 los dos. Se carga solo al encender el modo. Lleva un registro de uso hacia Google que paran la CSP y `blockForeignFetch`. Añadido el 2026-11-03 | Sin cámara, permiso o modelo, «Cámara no disponible» en gris y el giro manual sigue. Un ángulo equivocado gira la vista de una consola, nada más: no toca el registro, el análisis ni las alertas |
| `vosk-browser` (interfaz) y su modelo `vosk-model-small-es-0.42` | 0.0.8 (SHA-256 de `dist/vosk.js` fijado en `frontend/src/assistant/wake/voskWorker.ts`); modelo con su SHA-256 en `frontend/public/vosk/ORIGEN.txt` | Solo el modo «Escuchar "EMMA"» (manos libres, `frontend/src/assistant/wake/`, §5.44 de `hmi-state-of-the-art.md`): oír la palabra «EMMA» con una gramática cerrada para saber cuándo empieza una frase para el asistente. Vosk y Kaldi compilados a WebAssembly, Apache-2.0 los dos y el modelo. Se carga solo al encender el modo; el trabajador se sirve del propio origen con una guarda contra la red. No transcribe la frase (eso es Whisper, en el backend). Añadido el 2026-11-03 | Sin micrófono, permiso o modelo, «Escucha no disponible» en gris y lo demás sigue. Un falso disparo graba una frase y se la manda al asistente, que no escribe en el registro sin confirmación; una palabra perdida es no oír una orden por voz: el botón y el teclado siguen. No toca el análisis ni las alertas |
| TotalSegmentator (programa externo) | 2.x | Segmentación automática de TAC/RM, con PyTorch y pesos preinstalados; código Apache-2.0 y tareas de licencia abierta. **No va en el instalador**; lo trae el paquete de modelos (`backend/packaging/models_pack.py`) (copia de Python + pesos, `EMMA_TOTALSEG_CMD` apunta a su `python.exe`); telemetría exigida apagada | Sin él, "no disponible" en gris; una segmentación errónea es el riesgo H18 |
| `pypdfium2` | 5.13.0 | Rasterizar y leer la capa de texto de los PDF de informes escaneados (`reports/ocr.py`); licencia BSD-3-Clause o Apache-2.0, con PDFium y sus bibliotecas (FreeType, libjpeg, zlib…) bajo licencias permisivas. Añadido el 2026-09-25 | Un PDF que no abre se rechaza con 422; el resto del producto no lo usa |
| Tesseract OCR (programa externo) | — | OCR local de los informes escaneados, `spa+eng`; licencia Apache-2.0. **No va en el instalador**; lo trae el paquete de modelos (`backend/packaging/models_pack.py`), o se busca en el PATH o en la instalación típica de Windows (`EMMA_TESSERACT_CMD`) | Sin él, la función se declara no disponible en gris; el informe se guarda y se ve sin texto |
| `onnxruntime` / `tokenizers` | 1.30.0 / 0.23.2 | Búsqueda semántica en la documentación (`app/kb.py`, Polaris `kb_embed`) con el modelo e5-small; MIT y Apache-2.0. Añadido el 2026-10-04 | Sin ellos o sin el modelo, la búsqueda cae a BM25 por palabras; no toca el registro ni el análisis |
| `pydicom` | 3.0.2 | Leer, des-identificar y reescribir los DICOM de ecografía (`imaging/dicom.py`); licencia MIT. Añadido el 2026-09-24 | Un DICOM que no lee se rechaza con 422. Una calibración mal leída es el riesgo real: la escala se toma de `SequenceOfUltrasoundRegions` y se descarta la que es imposible (cero, no finita, otra unidad) |
| `reportlab` | 5.0.1 | Maquetar los PDF que EMMA exporta (`app/export.py`, por `md_to_pdf_pro` de Polaris, que lo importa al cargar); licencia BSD. En uso desde el 2026-10-01 y **sin ficha hasta el 2026-10-07** | Sin él `md_to_pdf_pro` no carga y la exportación responde 503 con el motivo; lo que la consola muestra no depende de él |
| `pypdf` | 6.19.0 | **Ninguno en EMMA.** `kb` de Polaris lo usa para leer los PDF de su biblioteca, y EMMA solo le da Markdown (`app/kb.py`). Declarada en `pyproject.toml` por la copia; licencia BSD-3-Clause. Sin ficha hasta el 2026-10-07 | Nada: `kb` comprueba si está antes de usarlo |
| Whisper (programa externo, `backend/.venv-voice`) | `openai-whisper` 20250625, `torch` 2.14.1 (CPU) y `soundfile` 0.14.0, con el modelo `base`: las fija y las comprueba `scripts/install_voice.py` | Transcribir una nota dictada (`app/voice.py`, con `transcribe_audios.py` de Polaris, §4.2). **No va en el instalador** ni se descarga con un audio esperando; lo trae el paquete de modelos (`backend/packaging/models_pack.py`), sobre una copia de Python (`BTP_VENV_VOICE`). Sin ficha hasta el 2026-10-07; su licencia no está anotada en `NOTICE` ni se ha comprobado aquí | Sin él, o sin la marca de instalación, el dictado se declara no disponible. Una transcripción equivocada es el riesgo de la nota dictada (H16): vuelve como borrador que la persona corrige |
| Capa NER de la des-identificación (programa externo, `backend/.venv-deid`) | `transformers` 5.18.0 y `torch` 2.14.1 (CPU), fijadas en `scripts/install_deid_ner.py`; el modelo y su revisión los fija `deid_ner.py` de Polaris | Un segundo detector de nombres para los informes (`app/reports/deid.py`, §4.2). **No se empaqueta y hoy no está activa**: el modelo no es público y la marca de instalación no existe. Sin ficha hasta el 2026-10-07 | Sin la marca no se pide. Pedida y caída, el texto del informe se retiene (H17) |
| Polaris, la copia literal (`polaris/`) | El commit de `polaris/ADOPTADO.txt`; la huella de cada fichero, en `polaris/MANIFEST.sha256` | Las herramientas que EMMA llama por `app.polaris.load` y las que ejecuta aparte; licencia AGPL-3.0-or-later. Declarada SOUP el 2026-10-07: su ficha, con una fila por herramienta, es el §4.2 | Depende de la herramienta: columna «Qué pasa si falla» del §4.2 |
| Marplanner, la copia literal (`marplanner/`) | El commit de `marplanner/ADOPTADO.txt`; la huella de cada fichero, en `marplanner/MANIFEST.sha256`; en el instalador, compilado por `planner-bridge/build-marplanner.mjs` y ejecutado con el Node de Electron (24.21) | El planificador de la casa: tareas, menú, calendario, recordatorios, hoja diaria, avisos de hora (sección «Planificador» y resumen de Tierra); licencia MIT. Añadido el 2026-11-12 (decisión del usuario). **No es dato de salud ni entra en el análisis ni en las alertas** | La sección «Planificador» dice que no está disponible y EMMA sigue: el backend responde 503 en `/api/planner/app/*` y `/api/planner/ground-summary`. Su base es el ledger (§3.31 de `record-integrity.md`): un asiento que no cuadra al reproducirse detiene su arranque en vez de servir una base distinta |

**Polaris: la copia literal es SOUP; lo adaptado a mano es código de EMMA**
(github.com/BeyondTheProtocol/polaris, AGPL-3.0-or-later; decisión del usuario, 2026-10-07: «SOUP
con ficha»). Hasta esa fecha este documento dejaba a Polaris fuera de la lista porque «no se usa
tal cual ni como caja negra»: describía la adopción del 2026-09-25, cuando cada pieza se leía, se
adaptaba y se mantenía aquí. Desde el 2026-09-29 la regla del proyecto es la contraria —copiarlo
literal y llamar al original— y aquella frase dejó de describir el código. Hoy conviven dos cosas
distintas, y la frontera entre ellas es una sola pregunta: **¿quién mantiene ese código?**

- **La copia literal (`polaris/`) es SOUP.** No se escribió para ir dentro de EMMA ni con el
  proceso de EMMA, y EMMA no la mantiene: se copia byte a byte de un commit
  (`polaris/ADOPTADO.txt`), cada fichero se vigila contra su huella (`polaris/MANIFEST.sha256`,
  `tests/test_polaris_copy.py`) y los únicos cambios son los que el usuario decide uno a uno,
  declarados en `polaris/CAMBIOS.json`. EMMA entra por un solo sitio, `app.polaris.load`. Su ficha
  es el §4.2: una fila por herramienta que EMMA usa.
- **El código adaptado a mano es de EMMA, no SOUP.** Son los ficheros de la lista `ADAPTED` de
  `tests/test_polaris_headers.py`, los mismos de la sección «ADAPTADO a mano» de `NOTICE`. Se
  escribieron aquí a partir del commit `7bf47257`, el que se copió primero; no avanzan cuando la
  copia avanza, y se mantienen con el proceso de EMMA: sus pruebas, sus campañas de mutantes
  (`tests/mutants/`) y la clase del elemento en que viven (§3). Que procedan de otro proyecto
  obliga a la licencia —cada uno declara en su cabecera el fichero de origen y qué se cambió
  (AGPL §5a)—, no a darles ficha de SOUP.
- **Un mismo fichero puede estar en los dos lados.** `volumes/geometry.py` llama a `visor3d` para
  las mallas y lleva además `lesions()`, adaptada a mano. La frontera va por función, no por
  fichero: lo que se ejecuta desde `polaris/tools/` es SOUP y lo que está escrito en el fichero
  de EMMA es de EMMA. La cabecera de cada fichero mixto dice qué es cada cosa.
- **El pegamento tampoco es SOUP.** `backend/app/polaris/` (el adaptador y `compat/`) y lo que
  cada módulo pone alrededor de la herramienta que llama son código de EMMA, escrito para que la
  copia viva aquí sin tocarla.

Las dos mitades obligan a lo mismo en un punto: EMMA se distribuye bajo AGPL-3.0-or-later.

**Marplanner: la misma frontera** (github.com/diegomarino/marplanner, MIT; decisión del usuario, 2026-11-12: «queremos todo, no lo que filtre información para fuera»). La copia literal (`marplanner/`) es SOUP: se copia de un commit, se vigila contra su huella (`tests/test_marplanner_copy.py`) y no se edita. Lo que la hace vivir en EMMA es código de EMMA, con su proceso: `planner-bridge/` (su base en el ledger, su red solo por `core/egress.py`, lo que le falta en Windows), `app/planner_link.py`, `app/planner_ground.py`, `app/api/planner.py` y `frontend/src/planner/`. Sus pruebas son las de EMMA (`backend/tests/test_planner_ledger.py`, `planner-bridge/bridge.test.mjs`, `frontend/src/planner/*.test.ts`) y la suite de Marplanner corrida con el puente (2077 de 2095 en Windows; lo que falla es de la plataforma o de lo excluido).

Ninguno se usa para tomar una decisión clínica por sí solo. Las herramientas de desarrollo
—`pytest`, `respx`, `ruff`, `mypy`— no entran en esta lista porque no viajan en el producto.

**Las fichas que dicen "ninguno" son un hallazgo, no una curiosidad.** Una revisión del
2026-09-22 comprobó el uso real de cada SOUP y encontró que `pandas` y `scipy` se declaran como
dependencias de ejecución sin que nada las importe. La primera versión de esta tabla les atribuía
un papel —"series temporales", "estadística de la línea base"— que el código no respalda: el
error exacto que este proyecto dice no querer. Quedan listadas mientras estén en `pyproject.toml`,
porque un evaluador ve lo que se instala; lo que procede es quitarlas de ahí.

**2026-10-04: `scipy` dejó de ser "ninguno" y nadie lo vio.** El visor 3D (2026-09-26) empezó a
usarlo, la ficha siguió diciendo "ninguno" y el congelado lo siguió excluyendo. La suite estaba en
verde porque en desarrollo está instalado; en la app instalada, toda segmentación moría al
remuestrear y el trabajo se quedaba "en marcha" sin fin. Corregido: `scipy` viaja en el
ejecutable, un fallo inesperado cierra el trabajo como fallido (`api/volumes.py`), y
`tests/test_packaging.py` falla si `app/` importa algo que el congelado excluye.

El proyecto fija versiones mínimas en `backend/pyproject.toml`; **no hay fichero de versiones
exactas fijadas** (*lockfile*), y eso es una carencia real para la reproducibilidad.

### 4.1 Interfaz y aplicación de escritorio (2026-09-23)

La interfaz y la envoltura de escritorio sí tienen versiones exactas: `package-lock.json` en
`frontend/` y `desktop/`, y Electron y electron-builder fijados sin rango en `desktop/package.json`.

| SOUP | Versión | Para qué se usa | Qué pasa si falla |
|---|---|---|---|
| `react`, `react-dom` | 19.3.0 | Pintar la interfaz | No se ve el estado. El backend sigue registrando y evaluando |
| `uplot` | 1.6.32 | Gráficas de tendencia de la consola de Tierra | Se pierden las gráficas; el estado y las alertas no dependen de ellas |
| IBM Plex Sans y Plex Mono (`@fontsource`) | 5.3.0 | Tipografía, empaquetada en local (licencia OFL) | Se usa la fuente del sistema; F.5.1 c (distinguir 0/O y l/1) deja de estar garantizado |
| **Electron** | **44.4.5** (Chromium 152.0.7977.130, Node 24.21.0) | Ventana de escritorio y motor de renderizado | No arranca la interfaz de escritorio. El backend es otro proceso y no se ve afectado |
| `three` (three.js) | 0.186.1, fijada sin `^` | Dibujar el mapa corporal de dolor en WebGL y averiguar qué zona se toca (licencia MIT). Añadido el 2026-09-25 | Sin WebGL o si falla, el mapa se declara no disponible en gris y las zonas se eligen en la lista: el informe no depende del 3D. El riesgo real es tocar una zona y registrar otra; la lateralidad del modelo tiene prueba (`bodyModel.test.ts`) y el formulario muestra el nombre de cada zona marcada antes de enviar |

**Por qué Electron y no Tauri.** Tauri usa por defecto WebView2 *evergreen*, que Windows actualiza por
su cuenta. Así, el motor que pinta las alertas cambiaría sin que el proyecto lo decida ni lo pruebe,
y eso choca con identificar la versión de cada SOUP. Electron lleva su Chromium fijado en cada
versión. Razonamiento completo en [`hmi-state-of-the-art.md`](hmi-state-of-the-art.md).

**Herramientas que producen el entregable.** No viajan en él, pero determinan su contenido, así que
se registran: `vite` 8.3.0 y `typescript` 7.0.2 compilan la interfaz; `electron-builder` 26.15.3
genera el instalador; `pyinstaller` 6.22.3 congela el backend. El congelado se hace desde un entorno
limpio con solo las dependencias de ejecución (`backend/packaging/freeze.py`), y **excluye `pandas`
y `matplotlib`**, que el código de EMMA no importa (`tests/test_packaging.py` lo comprueba). Hasta
el 2026-10-04 excluía también `scipy`, que el visor 3D sí necesita.

**Los avisos de Polaris viajan con su código (2026-10-06).** El ejecutable lleva las herramientas
de Polaris (`polaris/tools/`), y hasta esa fecha las llevaba sin los ficheros a los que remite el
`NOTICE` de EMMA. Ahora el congelado incluye `polaris/LICENSE`, `polaris/NOTICE`,
`polaris/CITATION.cff`, `polaris/ORIGEN.md` y `polaris/CAMBIOS.json` junto a `polaris/tools/`
(`POLARIS_NOTICES` en `freeze.py`), y el instalador los pone además en `resources/polaris/`, al
lado del `NOTICE` y el `LICENSE` de EMMA (`desktop/package.json`). Desde el 2026-10-07 viajan
también, en los dos sitios, `polaris/README.md`, `polaris/CHANGELOG.md`, `polaris/MANIFEST.sha256`
y `polaris/ADOPTADO.txt` (lo que hace falta para seguir esos avisos sin el repositorio delante), y
junto a las herramientas la carpeta `polaris/tools/fichas/`. `tests/test_packaging.py` falla si
falta alguno, y `tests/mutants/packaging.json` comprueba que esa prueba caza cada omisión.

**Comprobado en un instalador construido (2026-10-07).** Se congeló el backend desde un entorno
limpio y se generó el instalador NSIS con `electron-builder`. En la carpeta desempaquetada
(`desktop/release/win-unpacked/resources/`) se vio: los nueve ficheros en `polaris/` y en
`backend/_internal/polaris/`, cada uno con el mismo SHA-256 que el de `polaris/` del repositorio;
los `.py` de `polaris/tools/`, todos y con la misma huella, y `tools/fichas/` idéntica; ningún
fichero de `polaris/tests/`, de pytest ni de TotalSegmentator; y de `app/polaris/compat/`, como
fichero suelto, solo `fcntl.py`. El backend congelado se arrancó en loopback sin red y respondió a
`/api/health` y a `/api/polaris/estado` con las mismas herramientas cargadas que en desarrollo (las
que no cargan piden módulos que en Windows no existen o que no se instalan, y lo dicen). **Lo que
no se comprobó**: el instalador no se ejecutó (se miró la carpeta de la que se empaqueta, no una
instalación hecha con él), la ventana de Electron no se abrió, y el visor web de Polaris no se
recompiló en esa construcción: se usó el paquete ya confirmado en `backend/app/data/polaris_web/`.

**Endurecimiento del ejecutable.** Con los *fuses* de Electron desactivados, `ELECTRON_RUN_AS_NODE`
convertía `EMMA.exe` en un intérprete de Node para cualquier proceso; se comprobó en el paquete y se
cerró. La página corre en *sandbox*, sin Node, sin preload ni IPC, y solo navega al backend local.

**Lo que no hay:** el instalador **no va firmado** con certificado de código (Windows SmartScreen
avisará).

**Actualización (2026-11-16): manual, con botón, nunca automática.** El panel «Actualizaciones» del
pie «Acerca de» comprueba, descarga e instala la versión nueva publicada en
`github.com/Brillande/EMMA` solo cuando una persona lo pide, y nunca instala sin que alguien pulse
«Instalar y reiniciar». La descarga la hace el backend por `core/egress.py` (propósito
`app-update`) y comprueba tamaño y SHA-256 contra el manifiesto `emma-update.json`; la aplicación
de escritorio vuelve a comprobar la huella antes de lanzar el instalador. Se descartó
`electron-updater`, que saldría a internet desde Node saltándose la puerta. **No se añade ningún
SOUP**: ni dependencia nueva en el backend, en la interfaz ni en `desktop/package.json`; el
actualizador usa `httpx` (ya en la tabla del §4), la biblioteca estándar de Python y los módulos
de Node que ya trae Electron. Como el instalador no va firmado, la
huella protege de la corrupción y de las descargas cortadas, no de una cuenta de publicación
comprometida: el manifiesto viaja por el mismo canal que el exe. Especificación, modelo de amenazas
y límites en [`software-update.md`](software-update.md); peligros H25-H28 en
[`risk-management-file.md`](risk-management-file.md).

### 4.2 Polaris, la copia literal: ficha de SOUP (2026-10-07)

Las demás fichas de este documento caben en una fila porque cada biblioteca hace una cosa. Polaris
no: son muchas herramientas de otro proyecto (cuántas, y cuáles cargan aquí, lo dice
`polaris/ESTADO.md`), de las que EMMA llama a una parte, cada una dentro de un elemento distinto
y con un fallo distinto. Por eso su ficha tiene una cabecera común y **una fila por herramienta
en uso**.

Una ficha así caduca en cuanto alguien añade una llamada y no vuelve por aquí; ya pasó con
`scipy`, más arriba. Por eso esta no se sostiene sola: `backend/tests/test_soup_polaris.py` lee
este apartado y falla si una herramienta que EMMA carga no tiene fila; si una fila nombra una
herramienta que no se carga o un módulo que no la llama, o calla uno que sí; si el código le pide
a una herramienta un nombre que su fila no escribe; si cita una prueba, una campaña o un peligro
que no existen; si el resultado que da de una prueba de Polaris no es el de `polaris/PRUEBAS.md`,
o una roja queda sin explicar entre las anomalías; si la copia importa una biblioteca que no tiene
ficha en el §4; si Polaris cambia lo que publica de sus propios fallos y aquí no se ha vuelto a
leer; si una herramienta de la copia hace al importarse algo que este apartado no declara; o si
el documento vuelve a citar como vigente un commit que no es el adoptado. Lo que la prueba **no**
puede comprobar es lo que hay que leer: que «qué usa EMMA de ella» y «qué pasa si falla»
describan bien el código, y que la clase sea la correcta.

| | |
|---|---|
| **Título** | Polaris: sus herramientas en Python (`polaris/tools/`) y su visor web (`polaris/tools/visor3d_web/`) |
| **Fabricante** | La autora de Polaris, que opera bajo el nombre «Beyond the Protocol» (github.com/BeyondTheProtocol/polaris). Es el proyecto de una persona, escrito para su propio uso. Trae sus pruebas y sus campañas de mutantes, pero su proceso de desarrollo no es el de EMMA ni EMMA lo audita: por eso es SOUP |
| **Versión** | La línea `commit` de `polaris/ADOPTADO.txt`. Ese fichero dice además qué herramientas se pidieron (con ellas se copia todo lo que importan) y qué se dejó fuera. La huella SHA-256 de cada fichero copiado está en `polaris/MANIFEST.sha256`, y `tests/test_polaris_copy.py` falla si un fichero cambia, falta o sobra. Aquí no se escribe el commit: caducaría con la siguiente sincronización. En la máquina donde corre lo da `GET /api/polaris/estado`. Polaris numera sus entregas por fecha en su `CHANGELOG.md`; la copia se fija por commit, que no admite dos lecturas |
| **Licencia** | AGPL-3.0-or-later, © 2026 su autora. Sus avisos (`polaris/LICENSE`, `polaris/NOTICE`, `polaris/CITATION.cff`) viajan con el código en el instalador (§4.1) |
| **Cambios sobre el original** | Solo los de `polaris/CAMBIOS.json`, cada uno decidido por el usuario y con su motivo: los colores y los textos del visor web, la ruta del intérprete de la capa NER en Windows en `deid.py`, y las carpetas de entrada y salida por variable de entorno en `transcribe_audios.py`. Todo lo demás se resuelve desde fuera, en `backend/app/polaris/` |
| **Qué viaja en el producto** | Todos los `.py` de `polaris/tools/`, se usen o no, con sus fichas y sus avisos, y el visor web ya compilado (`backend/app/data/polaris_web/`); no sus pruebas (§4.1) |

**Cómo leer la tabla.** «Qué usa EMMA de ella» es lo que se espera de la herramienta, función a
función: lo demás que traiga no se llama. Cada nombre que el código de EMMA le pide —para
llamarlo, para leerlo o para sustituirlo mientras dura una llamada— está escrito ahí tal cual. «Módulo» es el fichero de `backend/` que la pide. «Clase»
es la del elemento de EMMA en que corre, según el §3 o el §7 (con varios módulos, la más alta);
una † marca las filas en las que algún módulo todavía no tiene fila propia en el §3 (nota al pie
de la tabla), y una raya, lo que no viaja en el producto. «Qué
pasa si falla» remite al peligro de [`risk-management-file.md`](risk-management-file.md) al que
conduce, y dice cuándo ese expediente no tiene ninguno; donde el expediente no nombra el control
(las analíticas, la filiación, el dosier), el peligro se asigna aquí por lo que el fallo produce.
«Su prueba en Polaris» es el resultado de las pruebas del propio Polaris en esta máquina, tal
como lo recoge `polaris/PRUEBAS.md`, que explica cada roja en su columna «Causa»: una roja o una
saltada no dice que la función falle, dice que aquí esa prueba no la respalda. Las campañas de
mutantes están en `backend/tests/mutants/`.

<!-- soup-polaris:inicio (lo lee backend/tests/test_soup_polaris.py) -->

**Herramientas que `backend/app` carga por su nombre** (`polaris.load("…")`; son las de
`EMMA_USES` en `app/api/polaris.py`, ni una más ni una menos):

| Herramienta | Qué usa EMMA de ella | Módulo de EMMA que la llama | Clase | Qué pasa si falla | Qué lo vigila en EMMA | Su prueba en Polaris |
|---|---|---|---|---|---|---|
| `_net` | `with_retries` y `RETRY_STATUS`: los reintentos de cada petición que sale (429, 5xx y fallos de red, con espera exponencial y `Retry-After`), bajo el tope total que pone EMMA | `app/core/egress.py` | B | No reintenta, o espera de más: la petición falla y el cliente sirve su caché con la edad declarada (H7). Sin el tope de EMMA, un `Retry-After` largo retenía cada estado de salud (H11) | `tests/test_egress.py`; mutantes `egress.json` | Ninguna con su nombre, y tampoco tiene ficha; `test_nvidia_tope.py` verde prueba `with_retries` y su tope de tiempo |
| `anticipa` | `esta_semana()`: lo datado de hoy a N días, sobre los asuntos de EMMA (fin de la ventana de seguimiento de una contramedida, horizonte de una proyección, eventos de misión) y con el día de los datos como «hoy»: su `date` se sustituye mientras dura la llamada. Y `_fecha`, que da la fecha de cada asunto | `app/timeline.py` | B | «Esta semana» sale vacía, incompleta o con el día corrido. Es presentación: no entra en el análisis ni en una alerta. El expediente no tiene un peligro para la línea temporal | `tests/test_timeline.py`; mutantes `timeline.json` | `test_anticipa.py` verde |
| `atascos` | `esperan_por_titular()` y su `ESPERA_DIAS`: lo que lleva tres días o más esperando por una persona (una alerta sin reconocer, una cifra sin confirmar, un borrador sin firmar), del más viejo al más nuevo | `app/waiting.py` | B | Algo que espera no sale en el resumen, o sale con los días mal contados; cada cosa sigue en su propio panel. Sin peligro propio en el expediente | `tests/test_waiting.py`; mutantes `waiting.json` | `test_aprobaciones_atascos.py` roja |
| `biomarcadores` | El extractor de analitos del texto de una analítica (`parse_line`, con su diccionario `ANALITOS`): la familia de unidades y una confianza por lectura. La fecha de la extracción (`fecha_de`) y el cociente BUN/creatinina (`_añadir_bun_cr`). Y el `nombre` de cada entrada de `ANALITOS`: el nombre en español de origen `polaris` con que todas las frases y pantallas de EMMA nombran ese analito (`app/ingest/names_es.py` lo lee de su copia en `data/lab_loinc.json`, sin cargar Polaris, y una prueba la coteja con `ANALITOS` por `labs.names`) | `app/reports/labs.py` | B | Propone una cifra, una unidad o un analito que no son los del papel (H17, H4). Ninguna entra en el análisis hasta que una persona la confirma, y la que no se puede fiar no se confirma sin corregir. Un nombre equivocado cambiaría cómo se nombra el analito en toda frase y pantalla (desviación, alerta, crónica), no la cifra ni el análisis: el análisis va por la clave del indicador | `tests/test_lab_readings.py`, `tests/test_timeline.py`, `tests/test_names_es.py`; mutantes `lab_readings.json`, `timeline.json`, `names_es.json` | `test_biomarcadores_muestras.py` verde; `test_biomarcadores_hormonas.py` verde; `test_biomarcadores_ggt_alias.py` verde; `test_biomarcadores_fecha_extraccion.py` verde; `test_biomarcadores_vhio.py` verde |
| `borde` | `egress_check` sobre la URL y la consulta de todo lo que sale, hacia un destino no confiable y sin escalar a su código rojo; `halted` y `HALT_FILES`, su freno por fichero, confinado al estado de EMMA; y `CANARIO_FILE`, la ruta donde busca el señuelo | `app/core/egress.py`, `app/polaris/__init__.py` | B | Si deja pasar: un dato de salud o el señuelo salen en una consulta (H15, H12). Si niega de más: no sale nada y cada cliente sirve su caché con la edad declarada (H7) | `tests/test_egress.py`; mutantes `egress.json`, `polaris_halt.json` | `test_borde.py` saltada; `test_canarios.py` verde llama a `egress_check` con el señuelo dentro |
| `canarios` | `sembrar_estado()`: siembra una vez el señuelo —un fichero que ningún flujo de EMMA lee— donde lo busca el `borde` cargado: sus rutas `BORDE_DIR`, `CANARIOS`, `REGISTRO` y `SENUELO_ESTADO` se apuntan antes a las de ese `borde` | `app/polaris/__init__.py` | B | Sin señuelo sembrado, el control de `borde` contra la exfiltración no tiene nada que buscar y no avisa (H5, que es donde el expediente lo describe, y H15) | `tests/test_egress.py`; mutantes `decoys.json` | `test_canarios.py` verde |
| `cascada_mapa` | `afectados()`: el cierre transitivo de «qué depende de este dato», sobre el mapa de EMMA (indicador → dominio de riesgo, región anatómica, contramedidas, línea base y proyección). Ese mapa se pone en su `MAPA` y su `DEPENDIENTES` mientras dura la llamada, y pasa antes por su `validar_mapa()` | `app/timeline.py` | B | La lista de lo que depende de un dato sale corta o de más. Es informativa: no recalcula nada. Sin peligro propio en el expediente | `tests/test_timeline.py`; mutantes `timeline.json` | Ninguna con su nombre; `test_cascada_clinica.py` verde prueba el mapa de dependencias |
| `cronica` | La forma de sus eventos, su saneado y `_linea_bitacora`, para escribir la crónica con los asientos del ledger y el estado de EMMA | `app/timeline.py` | B | Un evento falta, se repite o sale mal escrito en la crónica. El registro es el ledger, que no cambia. Sin peligro propio en el expediente | `tests/test_timeline.py`; mutantes `timeline.json` | `test_cronica.py` verde |
| `cumbre` | Nada suyo: se carga para sustituir su `foco()` mientras dura la llamada a `anticipa`, que si no buscaría la cadena «hacia NED» del caso de su autora | `app/timeline.py` | B | Si la sustitución no se aplicara o no se deshiciera, `anticipa` leería el foco de Polaris, que en EMMA no existe. Una prueba comprueba que la copia queda como estaba | `tests/test_timeline.py`; mutantes `timeline.json` | `test_cumbre.py` verde; `test_cumbre_integridad.py` saltada |
| `decision_alto_riesgo` | `disparar()` con sus ejes y sus léxicos (¿el comentario de una firma es una decisión clínica de alto riesgo?); `_existencia_citas()` (¿existe la fuente que cita esa firma?); sus listas `_ACCION` y `_DELIBERA_FUERTE`, que avisan a quien firma; y `_canon_txt`, el normalizador con el que lee el comentario | `app/decision_risk.py`, `app/evidence/source_check.py`, `app/text_guard.py` | C† | Una decisión de alto riesgo pasa con una sola firma, una cita inventada se enseña como confirmada, o un aviso de lenguaje no llega a quien firma (H14) | `tests/test_decision_risk.py`, `tests/test_source_check.py`, `tests/test_text_guard.py`, `tests/test_polaris_windows_reds.py`; mutantes `decision_risk.json`, `source_check.json`, `text_guard.json` | `test_decision_alto_riesgo.py` roja |
| `deid` | `de_identificar_verificado()` y `_mapa_normalizado`: enmascara el texto de un informe y vuelve a mirarlo; si aún ve algo, el texto no se usa. Lleva un cambio declarado en `polaris/CAMBIOS.json` | `app/reports/deid.py` | B | Si deja pasar: un nombre o un identificador se ve en la consola y viaja a Tierra (H17, H12). Si retiene de más: el informe se queda sin texto y solo se ve el original | `tests/test_reports.py`, `tests/test_deid_corpus.py`; mutantes `deid.json`, `polaris_deid.json` | `test_deid_diccionario.py` verde; `test_deid_procedencia.py` verde; `test_deid.py` saltada |
| `dosier_invariantes` | `_schema_pieza` e `_invariantes`: esquema cerrado de cada pieza del dosier de evidencia, ninguna contradicción y «alta» solo con fuente | `app/evidence/dossier.py` | B | Una pieza mal formada o contradictoria pasa por buena y respalda una contramedida (H20) | `tests/test_evidence_dossier.py`; mutantes `evidence_dossier.json` | `test_dosier_invariantes.py` verde |
| `estado_rutina` | `clasificar()`: cada medida periódica, al día, atrasada, rota o nunca corrió, con las fechas y los periodos de EMMA | `app/routines.py` | B | Una medida que dejó de llegar no se señala, y su silencio se parece a «todo normal» (H6) | `tests/test_routines.py`; mutantes `routines.json` | `test_estado_rutina.py` verde |
| `frescura_dosier` | `evaluar_frescura()`: una pieza del dosier revisada hace más de su vigencia no respalda nada | `app/evidence/dossier.py` | B | Una pieza caducada sigue contando como respaldo (H20) | `tests/test_evidence_dossier.py`; mutantes `evidence_dossier.json` | `test_frescura_dosier.py` verde |
| `fuente_clinica` | `cotejar()`: abre el informe que cita una firma y busca dentro el fragmento, con sus ganchos `_IDENTIDAD` y `_LOG` rellenos por EMMA y su `bovedas()` sustituida mientras dura la llamada. Y `normaliza`, con la que `locate` devuelve la frase literal del informe a quien pone la segunda firma | `app/evidence/vault.py` | B† | Da por confirmada una cita que no está en el informe, o la frase que se enseña no es la del informe: quien firma se apoya en una fuente que no dice eso (H17, donde el expediente describe la cita cotejada, y H14) | `tests/test_vault.py`, `tests/test_source_quote.py`; mutantes `vault.json`, `source_quote.json` | `test_fuente_clinica.py` roja |
| `guarda_memoria` | `corre()`: lanza la segmentación (TotalSegmentator) y la transcripción (Whisper) con un techo de memoria sobre el árbol de procesos entero. Sus lecturas de macOS se sustituyen por las de Windows | `app/memguard.py` | B | Si no corta: el proceso ahoga la máquina y EMMA deja de responder (H11). Si corta de más: una segmentación sana termina como fallida (H18) | `tests/test_memguard.py`; mutantes `memguard.json` | `test_guarda_memoria.py` saltada |
| `honestidad_lint` | Su lista `_TRIGGERS` completa, que avisa a quien firma un borrador sin bloquearlo. Las reglas que bloquean son código de EMMA | `app/text_guard.py` | C | Un aviso de lenguaje no se enseña, o se enseña de más. Lo que bloquea no depende de la copia (H14) | `tests/test_text_guard.py`; mutantes `text_guard.json` | `test_honestidad_lint.py` verde; `test_honestidad_lint_repo.py` verde |
| `identidad_paciente` | `verificar()`: ¿el informe es de este tripulante?, por el nombre y la fecha de nacimiento de su cabecera, contra la identidad declarada en el ledger, que se le da sustituyendo su `titular()` mientras dura la llamada. Y su tabla `SIRVE`, que dice si con ese veredicto el informe se puede usar | `app/reports/identity.py` | B | Un informe de otra persona se da por propio y sus cifras, una vez confirmadas, quedan atribuidas a quien no son (H3); o uno propio se rechaza | `tests/test_report_identity.py`; mutantes `report_identity.json` | `test_identidad_paciente.py` roja; `test_identidad_tabla.py` verde |
| `incongruencias_caso` | `analizar()`, con tres costuras sustituidas mientras dura la llamada: qué es la misma muestra (`muestra_de`), de dónde salen las lecturas (`extraer`) y cuánto es «distinto» (`_distintos`) | `app/reports/incongruences.py` | B | Dos analíticas de la misma extracción con cifras distintas no se avisan, y cada una se confirma por su lado (H17) | `tests/test_incongruences.py`; mutantes `incongruences.json` | `test_incongruencias_caso.py` verde |
| `kb` | `build()` y `retrieve()`: buscar en la documentación de EMMA, sin red (SQLite FTS5). Sus rutas `ROOT`, `FV`, `DB`, `IDX` y `VEC` se apuntan al estado de EMMA, y por su atributo `kb_embed` se llega a la capa vectorial (tabla de abajo) | `app/kb.py` | B | La búsqueda no devuelve el pasaje, o devuelve otro. No toca el registro ni el análisis. Sin peligro propio en el expediente | `tests/test_knowledge.py`; mutantes `kb_semantic.json` | `test_kb_fts5.py` verde; `test_kb_hibrido.py` verde; `test_kb_lock.py` verde; `test_kb_pdf_avisos.py` verde |
| `local` | Solo su texto `_ANTI`: la instrucción de tratar los hechos como dato y no como orden (`DATA_GUARD` del borrador) | `app/interpret/draft.py` | C | Si ese texto cambiara o quedara vacío, un dato del registro podría dar instrucciones al modelo que redacta (H14) | `tests/test_interpret.py`; mutantes `draft.json` | Ninguna propia en la copia |
| `md_to_pdf_pro` | `main()`: de Markdown a PDF (estado, dosier, crónica y anotaciones de dolor), con su `sys.argv` y su título sustituidos mientras dura la llamada (el título, envolviendo su `SimpleDocTemplate`) | `app/export.py` | B | No sale el PDF, sale mal maquetado o, si la sustitución fallara, con el título del caso de su autora. El texto es siempre el del backend (H10) | `tests/test_knowledge.py`; mutantes `knowledge.json`, `export_pain.json` | Ninguna propia en la copia |
| `ocr_informes` | `_tsv_a_texto()`, la maquetación reconstruida desde el TSV de tesseract, y sus constantes `LANGS`, `DPI`, `TEXT_LAYER_MIN_CHARS` y `CONF_MINIMA` | `app/reports/ocr.py` | B | El texto de un informe sale con las celdas mezcladas, o una página de poca confianza no se marca (H17) | `tests/test_reports.py`; mutantes `ocr.json` | Ninguna con su nombre; `test_ocr_layout.py` verde prueba `_tsv_a_texto` |
| `paso_consolidacion` | `consolidar()`: las objeciones de los verificadores y de las barreras en un solo dosier, por impacto y con lo que no trae fuente marcado. No su `render()` | `app/committee_dossier.py` | C | Una objeción no llega a quien firma, o llega sin su marca de «sin fuente trazable» (H14) | `tests/test_committee_dossier.py`; mutantes `committee_dossier.json` | `test_paso_consolidacion.py` verde |
| `score_local` | `puntuar`, `_ece` y `comprobar_memoria`: medir si cada modelo local del comité acierta y está calibrado, sobre el banco de casos de EMMA. Su `URL` y su `_memoria_libre_gb` se sustituyen mientras dura la medida por el servidor de modelos y la lectura de memoria de EMMA | `app/committee_bench.py` | C | Un verificador se da por bueno sin serlo. Es una medida, no una barrera en ejecución (H14) | `tests/test_committee_bench.py`; mutantes `committee_bench.json` | Ninguna propia en la copia |
| `seguimiento` | Nada suyo: su `recopilar()` se sustituye mientras dura la llamada a `anticipa` por lo datado de EMMA. EMMA no escribe su fichero ni toma su candado | `app/timeline.py` | B | Como `cumbre`: si la sustitución fallara, `anticipa` leería los hilos de Polaris, que en EMMA están vacíos | `tests/test_timeline.py`, `tests/test_polaris_windows_reds.py`; mutantes `timeline.json` | `test_seguimiento.py` saltada; `test_seguimiento_carrera.py` verde; `test_seguimiento_objetivo_ned.py` roja |
| `sintomas` | `es_alarma()` con su lista `ALARMA`: qué informe de dolor lleva la marca «comentar con el médico de a bordo» | `app/pain/alarm.py` | B | La marca falta o sobra. No es una alerta ni entra en el riesgo (H16) | `tests/test_pain_alarm.py`; mutantes `pain_alarm.json` | Ninguna propia en la copia |
| `soporte_cita` | `_limpia_fuente`, `entidades`, `_num_canon` y `_plano`: ¿las cifras de una frase están en el resumen del artículo que cita? `numbers()` y `check()` son código de EMMA | `app/evidence/support.py` | A | Una cifra de la documentación se da por respaldada sin estarlo. Corre como prueba `live`, fuera del producto: no llega a la tripulación | `tests/test_citation_support.py`; mutantes `support.json` | `test_soporte_cita.py` verde; `test_soporte_cita_juez.py` verde |
| `tier_evidencia` | `senales_desde_registro()`, `senales_desde_texto()` y `teje()`: el nivel de evidencia de cada fuente, desde su registro de PubMed guardado y sin ningún modelo. Y `SENALES` y `_resultado()`, con los que se escribe el nivel «desconocido» de una fuente que no se puede graduar | `app/evidence/tier.py` | B | Una fuente preclínica se enseña como clínica, o al revés (H20) | `tests/test_evidence_tier.py`; mutantes `evidence_tier_text.json`, `polaris_tier_evidencia.json` | `test_tier_evidencia.py` verde |
| `verifica_citas` | `_limpia_doi()`: la limpieza de un DOI antes de comprobarlo. `classify()` y las comprobaciones contra el registro son código de EMMA | `app/evidence/citations.py` | A | Un DOI válido se recorta mal y la cita sale como no resoluble, o al revés. Alcanza a la segunda firma por `evidence/source_check.py` (H14) | `tests/test_citations.py`; mutantes `polaris_verifica_citas.json` | `test_verifica_citas.py` verde; `test_verifica_citas_datacite.py` verde; `test_verifica_citas_estados.py` verde |
| `visor3d` | Las mallas y sus medidas (`ply_binario`, `_malla`, `_caja_de`, `_taubin`, `_icosfera`, `_elipsoide`, `_diametro_axial_mayor`); el emparejado y la evolución de lesiones entre dos estudios (`empareja`, `evolucion`); `nifti_limpio`, la cabecera limpia de lo que EMMA genera y, a petición de quien lo sube, la de un volumen que la puerta rechazó; el control de la cadena vertebral (`_revisa_cadena`, `_orden_columna`, `CADENA`, `VERTEBRA_MIN_MM3`); y la puerta de datos personales de un NIfTI (`verifica_sin_pii`, `_trozos_pii`); y la vista anterior del esqueleto del propio TAC (`proyecta_anterior`, `_uv`). `build()`, `lesions()`, la densidad en HU, la reorientación del mapa antes de proyectarlo y lo que rodea a la limpieza son código de EMMA | `app/volumes/assets.py`, `app/volumes/geometry.py`, `app/volumes/privacy.py`, `app/volumes/skeleton_view.py`, `app/volumes/spine.py` | C | Un diámetro, una malla o el estado de una lesión candidata salen mal; un esqueleto incompleto no se avisa; un volumen entra con un nombre en la cabecera; una limpieza cambia la imagen (EMMA compara los vóxeles bit a bit y vuelve a pasar la puerta); o la figura del esqueleto del propio TAC sale cabeza abajo o en espejo (EMMA comprueba el sentido y, si no cuadra, enseña la de referencia y dice por qué) (H18) | `tests/test_volumes.py`, `tests/test_skeleton_view.py`; mutantes `volumes_geometry.json`, `volumes_assets.json`, `volumes_spine.json`, `volumes_privacy.json`, `skeleton_view.json`, `polaris_visor3d.json` | `test_visor3d_malla_recorte.py` verde; `test_visor3d_mascara_union.py` verde; `test_esqueleto_niveles.py` verde; `test_visor3d_ficha.py` verde; `test_visor3d.py` roja; `test_visor3d_cateter.py` roja; `test_visor3d_colab.py` roja; `test_visor3d_cuelgue.py` saltada. `proyecta_anterior` y `_uv` no las nombra ninguna prueba de la copia. Las demás, sobre funciones que EMMA no llama, en `polaris/PRUEBAS.md` |
| `visor3d_superpone_focos` | `alinea()`: ajusta por mínimos cuadrados las zonas del mapa de dolor al esqueleto que se enseña —el de referencia o, si lo tiene, el del TAC del tripulante—, con los focos, las anclas y la caja del cuerpo de EMMA en el sitio de sus `FOCOS`, `ANCLAS` y `VB` mientras dura la llamada. Desde el 2026-10-20, además, la regla de su modo DIRECTO (en su `main()`, que no se llama): la zona anclada a un hueso que la figura trae entero va al centroide de ese hueso; EMMA la reproduce zona a zona, no de todo o nada como en Polaris | `app/pain_on_skeleton.py` | B | Un punto de dolor se dibuja sobre otro hueso, o sobre el centroide de un hueso mal segmentado; con un ajuste malo se dice «no se superpone». No cambia lo registrado: H16 es el peligro más cercano, y el expediente no recoge este como propio | `tests/test_pain_on_skeleton.py`; mutantes `pain_on_skeleton.json`, `pain_on_skeleton_direct.json` | Ninguna propia en la copia |

<!-- soup-polaris:otro-camino -->

**Lo que llega por otro camino.** No son `load("…")` desde `backend/app`, y por eso no están en
`EMMA_USES`: guiones de desarrollo que sí cargan la copia por su nombre, un programa que se
ejecuta aparte, datos generados una vez, capas que trae otra herramienta y el visor web.

| Herramienta | Qué usa EMMA de ella | Módulo de EMMA que la llama | Clase | Qué pasa si falla | Qué lo vigila en EMMA | Su prueba en Polaris |
|---|---|---|---|---|---|---|
| `deid_eval` | `cargar_brat`, `offsets_cuadran`, `puntuar` y `fugas`: mide cuánto se le escapa a la des-identificación, por tipo de entidad, y escribe la tabla del expediente de riesgos. Guion de desarrollo: no viaja en el producto | `scripts/deid_report.py` | — | La cifra del expediente diría que se escapa menos de lo que se escapa (H17) | `tests/test_deid_corpus.py` | `test_deid_eval.py` roja |
| `mutantes` | Su clase `Campana`, con sus tres reglas: corre cada campaña de `tests/mutants/`. Guion de desarrollo: no viaja en el producto | `scripts/mutants.py` | — | Una defensa se daría por vigilada sin estarlo: un mutante que «muere» sin haberse cargado | **Ninguna prueba de EMMA corre el guion.** Lo ejercita cada campaña, que se niega a correr si la prueba ya está roja sin mutar o si `import app` no resuelve a su copia temporal | `test_mutantes.py` verde |
| `transcribe_audios` | El guion entero, como programa aparte en `backend/.venv-voice` y bajo `guarda_memoria`: un audio Ogg/Opus pasa a texto con Whisper local. Lleva un cambio declarado en `polaris/CAMBIOS.json`. No se importa: en el entorno de EMMA no carga (`polaris/ESTADO.md`) | `app/voice.py` | B | La transcripción cambia lo que se dijo («no me duele» por «me duele»). Vuelve como borrador, que la persona lee y corrige antes de firmar (H16) | `tests/test_voice.py`; mutantes `voice.json` | Ninguna propia en la copia |
| `esqueleto_referencia` | No se ejecuta en el producto: con él se generaron una vez la vista anterior y los centroides por hueso del esqueleto de referencia (`app/data/anatomy/`), desde BodyParts3D | `app/anatomy.py` | B | Un centroide mal calculado coloca mal un hueso en el modo anatómico y las anclas del dolor sobre el esqueleto. Sin peligro propio en el expediente | `tests/test_anatomy_skeleton.py` | `test_esqueleto_referencia.py` verde |
| `kb_embed` | La capa vectorial del buscador (modelo e5-small en ONNX). La trae `kb`; `app/kb.py` le apunta las rutas del modelo y le pregunta si está `disponible()` | `app/kb.py` | B | Sin el modelo o sin `onnxruntime`, la búsqueda cae sola a palabras (BM25); con vectores malos, empeora el orden de los pasajes. Sin peligro propio en el expediente | `tests/test_knowledge.py`; mutantes `kb_semantic.json` | Ninguna con su nombre; `test_kb_hibrido.py` verde, que aquí solo recorre la rama sin vectores (lo dice su última línea en `polaris/PRUEBAS.md`) |
| `deid_ner` | La capa NER de la des-identificación, en un entorno aparte (`backend/.venv-deid`). `deid` la pide solo si existe la marca de instalación. **Hoy no está activa**: el modelo no es público | `app/reports/deid.py` | B | Pedida y caída, el original devuelve «no verificado» y el texto se retiene (H17) | `tests/test_reports.py` | `test_deid_ner.py` verde |
| `visor3d_web/` | El visor web del preset hígado, en JavaScript. Lo compila `frontend/scripts/build-polaris.mjs` y lo sirve el backend con los ficheros firmados del ledger. Lleva cambios declarados en `polaris/CAMBIOS.json` (colores y textos) | `app/volumes/polaris_web.py` | C | El visor no carga, o pinta mal una estructura; los ficheros que enseña van firmados y se comprueban en cada entrega (H18) | `tests/test_volumes.py` | `test_visor3d_carga.py` verde, que con `node` prueba solo `carga.js` (el porcentaje de carga tumoral del resumen); del resto del visor web, ninguna |

<!-- soup-polaris:fin -->

† **Módulos sin fila propia en el §3.** `app/evidence/vault.py` y `app/evidence/source_check.py`
llaman a la copia y no figuran en la tabla de elementos, porque su clase está **sin decidir**: no
bloquean nada, pero lo que enseñan lo lee quien pone la segunda firma de un borrador de Clase C;
si eso orienta la decisión como la orienta el dosier del comité (§7), les corresponde C. Y
`app/evidence/citations.py` figura como A en el §3 porque entonces la aplicación solo clasificaba
identificadores: desde que `source_check.py` llama a su `verify` al firmar, esa justificación ya
no describe el código. Las tres son decisión del usuario; mientras tanto, para los dos primeros
vale la clase del conjunto, B (§2), y `citations.py` sigue con la fila que tiene. Los otros
catorce módulos que llamaban a la copia sin fila la tienen desde el 2026-10-21 con la clase que
este documento ya les daba: B, la del conjunto, y C los cuatro del paquete del visor 3D
(`volumes/privacy.py`, `volumes/skeleton_view.py`, `volumes/spine.py` y
`volumes/polaris_web.py`).

**Lo que esta tabla enseña de la vigilancia.** Ninguna herramienta que corre en el producto está
sin prueba de EMMA sobre su adaptador; la de `transcribe_audios` simula Whisper y la de
`score_local` simula el servidor de modelos, y la cadena real de cada una solo la corre una
prueba `live`. Pero estas no tienen detrás ninguna prueba propia de Polaris en la copia:
`local`, `md_to_pdf_pro`, `score_local`, `sintomas`, `visor3d_superpone_focos` y
`transcribe_audios`; del visor web solo se prueba `carga.js`; `_net` no tiene prueba con su
nombre, y la que ejercita `with_retries` es la del tope de `nvidia`, que EMMA no usa; la capa vectorial de
`kb_embed` solo se recorre aquí por su rama de reserva; y, de `visor3d`, las dos funciones de la vista anterior del esqueleto
(`proyecta_anterior`, `_uv`) no las nombra ninguna prueba de la copia. De ellas, lo único que respalda lo que EMMA usa son las pruebas de EMMA. Y el
guion que corre las campañas de mutantes (`scripts/mutants.py`) no tiene prueba propia en la
suite.

**Lo que la copia arrastra y EMMA no llama.** Con cada herramienta pedida se copia todo lo que
importa, y en el ejecutable viajan todos los `.py` de `polaris/tools/`: la mayoría no tiene fila
arriba. No se les da ficha una a una, porque de ellas no se espera nada; lo que hay que poder
decir es qué impide que hagan algo. Cuáles son lo dicen `polaris/ADOPTADO.txt` (qué se pidió y qué
se dejó fuera) y `GET /api/polaris/estado` (cuáles usa EMMA y cuáles solo viajan).

**Desde el 2026-10-08 no todas las dormidas llegaron arrastradas.** Ese día se pidieron por su
nombre treinta y cinco herramientas que nada de EMMA usa: las locales de Polaris que faltaban
por copiar (el bloque «octava ronda» de `polaris/ADOPTADO.txt`; el criterio, y lo que quedó fuera
una a una, en `docs/polaris-divergencias.md` §18). El 2026-10-09 se retiraron cuatro, al leer su
código y no solo su docstring (`borde_gateway`, `portguard`, `permiso_envio` y `ok_envio`: abren
un puerto, matan procesos o usan el Llavero de macOS), y quedan treinta y una. «Locales» no
quiere decir inertes: llamadas, varias piden algo al modelo local o lanzan `git` u `ollama`.
Ninguna está en `EMMA_USES`, y lo de abajo vale para ellas igual que para las que arrastró un
`import`.

- **Nadie las llama.** Lo que EMMA pide a la copia por su nombre es una lista cerrada
  (`EMMA_USES`), atada a las fuentes por `tests/test_polaris_bridge.py`: una llamada nueva sin
  declarar hace fallar la suite, y una declarada sin fila aquí, también. Y ninguna de las dormidas
  se ejecuta como programa: los únicos guiones de la copia que se lanzan en el producto son
  `transcribe_audios`, que lanza EMMA, y `deid_ner`, que lanza `deid` si existe su marca de
  instalación (los dos, en la tabla de arriba).
- **Importarlas no es llamarlas, y aun así se mide qué hace cada una al importarse.**
  `GET /api/polaris/estado` las importa para decir si cargan, menos las de una lista declarada
  (`NOT_IMPORTED`, en `app/polaris/__init__.py`), que salen como «no se importa» con su motivo.
  La primera medida (2026-10-08, importándolas todas) encontró una que lanza un proceso, y el
  2026-10-09 se decidió no importarla para hacer el inventario, sin tocar la copia.
  `tests/test_soup_polaris.py` pide ese inventario en un intérprete limpio, con el estado en un
  directorio temporal, y apunta con un gancho de auditoría de Python todo proceso que se lanza,
  todo fichero que se abre para escribir o se crea, mueve o borra, y toda conexión que se
  intenta: **pedir el inventario no lanza ningún proceso, ni escribe en disco, ni abre una
  conexión.** Después importa a propósito lo que la tabla de abajo declara, y tiene que hacer
  eso mismo: es lo que justifica la exclusión. La otra herramienta de la lista,
  `transcribe_audios`, no está en la tabla porque no se importa ni para medirla: es un guion sin
  función de entrada (crea su carpeta de salida y carga un modelo de Whisper a nivel de módulo),
  y EMMA lo lanza como programa aparte (`app/voice.py`). Una herramienta de la lista que ya no
  esté en la copia hace fallar `tests/test_polaris_bridge.py`.

<!-- soup-polaris:al-importar -->

| Herramienta | Qué hace al importarse | Qué alcanza a EMMA |
|---|---|---|
| `rodaje_muro` | **Proceso.** Para dar nombre a su fichero de estado pregunta a `git` por la rama de la carpeta que contiene a `tools/` (`git -C … rev-parse --abbrev-ref HEAD`, con diez segundos de tope y el fallo tragado). No escribe nada: solo calcula una ruta | Dormida, de las del 2026-10-08. `git` solo lee, y lo que lee es la rama del repositorio de EMMA, o nada si no lo hay. Pero es un proceso que EMMA no decide, y se lanzaba cada vez que un proceso de EMMA la importaba por primera vez, cosa que hacía `GET /api/polaris/estado`. **Decidido el 2026-10-09: el inventario no la importa** (`NOT_IMPORTED`), y la copia no se toca. Quien la cargue por su nombre (`load("rodaje_muro")`) sí lo lanzaría, y nadie en EMMA lo hace: no está en `EMMA_USES`. Sin repositorio o sin `git`, su código se queda con «sin-rama» y la importación sigue (leído en su código; sin comprobar en un instalador) |

<!-- soup-polaris:al-importar-fin -->

  **Lo que esa medida no ve:** lo que una herramienta haría si se la llamara (para eso está el
  primer punto), ni lo que llegara al sistema por una vía que Python no audita (una biblioteca
  nativa que abra un fichero por su cuenta). El código intermedio de Python (`__pycache__`) lo
  escribe el intérprete, no la herramienta, y no se cuenta.
- **Solo pueden hablar con el modelo local.** El enrutador de Polaris (`ia`) elige «cerebro» de
  un registro, y el adaptador le da uno con una sola entrada: el `local-ollama` del propio
  Polaris, con la URL y el modelo de EMMA. **Los cerebros de nube sí están en la copia**: el
  registro original (`polaris/tools/peripheries.json`) los trae todos, y viajan y cargan los
  módulos que los atienden (`carril_gratis`, `nvidia`, `fugu`). Lo que no están es registrados:
  `ia` lee el registro que le escribe EMMA, y por él no puede alcanzar un cerebro que no figura
  ahí. Fuera para siempre, por decisión del usuario (`docs/polaris-divergencias.md` §1). Y lo
  clínico, por ese camino, se niega con el modelo local (§2 de ese documento). Las dos cosas
  tienen prueba en `tests/test_polaris_bridge.py`. Llamar a uno de esos módulos sin pasar por
  `ia` no lo impide el registro: lo impide el primer punto.
- **Escriben en el estado de EMMA.** Su casa y su estado (`BTP_REPO`, `BTP_STATE_DIR`) apuntan a
  un directorio de EMMA, nunca a la carpeta personal. Lo que leían de su autora no se copió
  —perfiles y contactos de personas reales, sus ganchos, la fontanería de macOS—, así que las
  herramientas que dependen de ello se quedan sin con qué trabajar.
- **EMMA sale a internet por un solo sitio.** Toda petición de EMMA pasa por `core/egress.py`, y
  las funciones de la copia que EMMA llama no salen por su cuenta: donde el original preguntaba a
  un registro con `curl`, EMMA pone su propio cliente, que pasa por esa puerta; `score_local`
  solo habla con el servidor de modelos local. **Lo que esa puerta no vigila** es una herramienta
  dormida que abriera su propia conexión si alguien la llamara (correo, modelos de nube, redes
  sociales): a esa no la detiene `egress.py`, la detiene el primer punto. La suite corre con el
  modo sin red forzado, y las pruebas de Polaris, con el proxy apuntando a un puerto muerto.
- **Su freno por fichero está confinado.** Varias herramientas se paran, o lo paran todo, si
  existe un fichero `HALT` en la carpeta personal o dentro de la copia, y algunas lo escriben. Tal
  cual, un fichero ajeno a EMMA habría cortado su salida sin dejar rastro. El adaptador lo deja en
  un único fichero del estado de EMMA, también para lo que una herramienta importa tarde; no es
  el modo seguro, EMMA no lo crea nunca, y `GET /api/safe-mode` lo enseña (`tests/test_egress.py`,
  campaña `polaris_halt.json`) con un aviso que la franja común de las consolas pinta sola
  (`halt_notice`, campaña `halt_notice.json`). Y `borde` se llama siempre sin escalar a su «código rojo», que
  avisa por Telegram y apaga demonios de macOS.

**Residual, dicho claro:** no hay un candado que impida a código nuevo de EMMA importar una
herramienta dormida y llamarla. Lo que hay es una prueba que obliga a declararla y esta ficha, que
obliga a darle fila y a escribir qué pasa si falla.

**Requisitos de entorno.** Polaris se escribió para macOS y para el Python de su autora. Lo que
necesita para vivir en EMMA —Windows y el intérprete de EMMA— está fuera de la copia:

- `backend/app/polaris/compat/fcntl.py`: el `flock` que `borde` importa, hecho con `msvcrt`. Solo
  en Windows y al final de `sys.path`. Sin él no cargan `borde` ni nada de lo que lo importa.
- `backend/app/polaris/compat/memguard.py`: las lecturas de memoria, de procesos y de CPU de
  `guarda_memoria`, con la API de Windows. La decisión de cortar sigue siendo la del original.
- `backend/app/polaris/compat/winlock.py`: la sonda de Windows para el candado entre procesos de
  Polaris (`_lock`). El cargador de `app/polaris/__init__.py` la instala sobre `_lock` en cuanto
  se importa. EMMA no toma ese candado: es para que una herramienta cargada que lo tome por su
  cuenta no espere a un dueño muerto. No arregla los ficheros que el candado protege (fila de
  `seguimiento` entre las anomalías).
- `backend/app/polaris/compat/resource.py` y `backend/app/polaris/compat/sitecustomize.py` **no**
  son requisitos del producto: existen para las pruebas de Polaris en Windows (medir memoria, y
  activar esa sonda en sus procesos), y dentro de EMMA no hacen nada. La lista de la carpeta la
  escribe `scripts/polaris_estado.py` en `polaris/ESTADO.md`, y `tests/test_polaris_texts.py`
  falla si ese texto, `polaris/ORIGEN.md` o `NOTICE` callan un módulo.
- **Un proceso con varios hilos.** Las herramientas de Polaris son guiones de terminal: hablan
  por la consola y guardan su configuración en variables del módulo, y EMMA las llama desde un
  servidor. Lo que eso exige está en el pegamento, no en la copia: una sola captura de consola
  con un solo cerrojo (`app/polaris/console.py`, para `kb`, `md_to_pdf_pro` y `visor3d`); cada
  sustitución «mientras dura la llamada» de la tabla de arriba, bajo el cerrojo de su adaptador
  (en `evidence/vault.py` cubre el cotejo entero, y la copia del informe se cambia de golpe); y
  el primer uso de `borde`, con su señuelo, una sola vez (`core/egress.py`).
- **Bibliotecas.** Lo que las herramientas con fila importan y EMMA necesita tiene ficha en el §4:
  `numpy`, `scipy`, `nibabel`, `scikit-image` y `pillow` (el visor 3D y el esqueleto),
  `onnxruntime` y `tokenizers` (`kb_embed`), `reportlab` (`md_to_pdf_pro`) y `pypdf` (`kb`). Las
  dos últimas viajaban sin ficha hasta esta revisión. `visor3d` importa además `SimpleITK`,
  `matplotlib`, `nnunetv2`, `torch` y la API de Python de TotalSegmentator, pero dentro de
  funciones que EMMA no llama (leer una serie DICOM, pintar figuras, segmentar por sí mismo): no
  son requisitos de EMMA. `tests/test_soup_polaris.py` lee los `import` de cada herramienta con
  fila y falla si aparece una biblioteca que no está ni en la lista del §4 ni entre esas
  excepciones.
- **Entornos aparte**, que no viajan en el instalador: `backend/.venv-voice` (Whisper, para
  `transcribe_audios`) y `backend/.venv-deid` (la capa NER, para `deid_ner`), cada uno con su
  guion de instalación y su marca de pesos comprobados; sin la marca, EMMA no los pide. Y el
  visor web se compila con las dependencias que fija el `package-lock.json` de Polaris, no con
  las de la interfaz de EMMA.
- **Lo que aun así no carga** en esta máquina, y por qué, está en `polaris/ESTADO.md`. Ninguna de
  las que `backend/app` carga por su nombre está ahí; `transcribe_audios` sí, y por eso se ejecuta
  en su entorno en vez de importarse.

**Anomalías conocidas.** *Paráfrasis de la cláusula 7.1.3:* hay que evaluar las anomalías
publicadas del SOUP que puedan llevar a una situación peligrosa. Lo más parecido que publica
Polaris viaja en la copia: `polaris/docs/lo-que-falta.md` (sus problemas abiertos, dichos por su
autora) y `polaris/CHANGELOG.md` (cada entrega, por fecha). Hablan de su sistema entero. Aquí van
tres cosas: lo que publican esos dos documentos, cruzado con las filas de arriba; las pruebas de
Polaris que en esta máquina no pasan; y los sitios donde EMMA pone una regla encima del original.

*Lo que publica Polaris, leído entero y cruzado con la ficha* (decisión del usuario, 2026-10-08).
La pregunta para cada punto es la de la norma, estrechada a lo que EMMA usa: ¿toca una función
de la columna «qué usa EMMA de ella»? En la tabla entra lo que toca a una herramienta con fila,
aunque lo que EMMA le pide quede fuera, para que conste que se miró.

<!-- soup-polaris:publicadas -->

| Herramienta | Qué publica Polaris | ¿Alcanza a lo que EMMA usa? Qué lo vigila |
|---|---|---|
| `borde` | `CHANGELOG.md`, entrega del 17 de septiembre: su radar de literatura no corrió en su fecha porque el freno por fichero (`HALT`) estaba puesto, y pasó semanas sin barrer | **Sí**: es el freno que EMMA lee con `halted` y `HALT_FILES`, y mientras existe corta toda la salida a internet. En EMMA está confinado a un único fichero de su estado, que EMMA no crea nunca; `core/egress.py` lo nombra en su error y `GET /api/safe-mode` dice si está puesto y dónde (`tests/test_egress.py`, mutantes `polaris_halt.json`). Desde el 2026-10-09 dice también desde cuándo (`halt.since`, la fecha del fichero, sin firma), y desde el 2026-10-20 avisa por su cuenta: la franja común de las dos consolas lo pinta sin recargar (relee el estado cada 30 s), con el texto que compone `api/safe_mode.halt_notice` (`tests/test_halt_notice.py`, mutantes `halt_notice.json`; `components/SafeMode.test.ts`) (H7) |
| `deid` | Fuera de los dos documentos, en la cabecera de `test_deid_procedencia.py`, que viaja en la copia: `deid` enmascara y verifica con los mismos patrones, y un texto inventado con nombre, domicilio, diagnóstico y médico salió sin una sola redacción y dado por limpio. Polaris no lo corrige en `deid`: desde entonces trata como sensible todo lo que viene del caso, en su enrutador | **Sí, de lleno**: es `de_identificar_verificado()`, y el arreglo de Polaris está en un camino que EMMA no usa. Lo que EMMA pone: sus reglas encima (el nombre con tratamiento, el familiar nombrado), la medida de lo que se escapa por tipo de entidad (`tests/test_deid_corpus.py`, con la tabla del expediente en H17) y el original guardado aparte. Revalidar con el detector que enmascara caza restos, no demuestra anonimato: el residual es de H17 y sigue abierto |
| `estado_rutina` | `lo-que-falta.md`, punto 5: sigue abierto «distinguir “no hay nada que hacer” de “esto lleva roto un mes”» y que una rutina que deja de correr avise sola. `clasificar()` nació de ese punto, lo dice su cabecera | **La función, no**: es pura y sus umbrales tienen prueba (`test_estado_rutina.py` verde). Lo abierto es engancharla a sus rutinas y avisar, que en EMMA es código propio: `app/routines.py` le da las fechas y los periodos (`tests/test_routines.py`, mutantes `routines.json`). Un estado «rota» se enseña; no es una alerta ni entra en el riesgo (H6) |
| `honestidad_lint` | `CHANGELOG.md`, entrega del 25 de julio: su barrido no miraba ningún documento, y una frase con «según X» delante quedaba perdonada. Corregido en la copia | **No**: EMMA toma solo la lista `_TRIGGERS`. Ni el barrido ni los sellos que perdonan se llaman, y lo que bloquea un borrador son reglas de EMMA (`tests/test_text_guard.py`) |
| `kb` | `lo-que-falta.md`, punto 4: con un buscador local y todo, hay cosas que su autora tiene que volver a explicar; pide no fiarlo «a la suerte del recuperador» | **Sí, como límite**: `retrieve()` puede no devolver el pasaje que existe. Es el fallo que ya declara su fila; la búsqueda es consulta, y no toca el registro ni el análisis (`tests/test_knowledge.py`) |
| `local` | `lo-que-falta.md`, punto 1: el carril local de Polaris está «disponible pero sin uso real» | **No a una función**: EMMA toma solo el texto `_ANTI`, y habla con su modelo por su propio cliente (`interpret/llm.py`). Lo que sí dice el punto es que ese carril tiene poco rodaje en su casa: aquí el texto lo respaldan `tests/test_interpret.py` y los mutantes `draft.json`, no el uso de su autora |
| `seguimiento` | `CHANGELOG.md`, entrega del 25 de julio: su fichero perdía escrituras cuando varias coincidían. Corregido con un candado | **No**: EMMA no escribe ese fichero ni toma ese candado (`tests/test_polaris_windows_reds.py`). Lo que le pasa al candado en Windows está en la tabla de abajo |
| `verifica_citas` | `CHANGELOG.md`, entrega del 25 de julio: un DOI inventado dentro de una referencia bibliográfica pasaba limpio. Corregido en su `clasifica()` | **No**: EMMA llama solo a `_limpia_doi()`. Su `classify()` es código propio y busca el DOI dentro de la cita (`tests/test_citations.py`, mutantes `polaris_verifica_citas.json`) |

<!-- soup-polaris:publicadas-fin -->

**Lo que no alcanza, contado.** `lo-que-falta.md` tiene cinco problemas abiertos; tres rozan una
herramienta con fila y están arriba. Los otros dos —que su catálogo de herramientas crece sin
ciclo de vida y que todo corre sobre Claude Code— hablan de cómo se organiza su sistema, no de
una función. `CHANGELOG.md` tiene siete entregas y seis líneas de historial anteriores; de dos
entregas sale algo que toca a una herramienta con fila (arriba). El resto no alcanza por una de
tres razones: habla de herramientas que no se copian (su radar de literatura, sus demonios de
macOS, sus ganchos de Claude Code), de herramientas copiadas que EMMA no llama (el control de
errores, el tope de gasto, el «código rojo», al que EMMA no escala nunca), o anuncia
una capacidad nueva y no un fallo; entre estas, el origen de dos cosas que EMMA sí usa, la
comprobación de que una cita existe y la frescura del dosier. Una de esas entregas explica además
tres filas de la tabla de abajo: cerró una fuga con una fuente única de «zonas clínicas» que vive
en ganchos que no se copian, y sin ella las pruebas que pasan por su «ventanilla clínica» salen
aquí en rojo.

**Qué no cubre esta lectura.** Son los dos documentos, tal como viajan en la copia de hoy:
`tests/test_soup_polaris.py` guarda la huella de cada uno y falla si cambian, para que se vuelvan
a leer al sincronizar. No se han leído las cabeceras de las demás pruebas de la copia, donde
Polaris cuenta el fallo que originó cada una (la de `deid` salió al revisar las pruebas copiadas
en esta ronda), ni los *issues* de su repositorio público, que no viajan con EMMA.

*Las pruebas de Polaris que aquí no pasan sobre una herramienta en uso.* La causa de cada una
está en `polaris/PRUEBAS.md`; esta tabla dice qué alcanza a EMMA.

<!-- soup-polaris:anomalias -->

| Herramienta | Su prueba, y por qué no pasa aquí | Qué alcanza a EMMA |
|---|---|---|
| `atascos` | `test_aprobaciones_atascos.py` roja: no se copia `tools/config/`, donde está su política de aprobaciones | Sin respaldo de Polaris aquí. Lo que EMMA usa lo prueban `tests/test_waiting.py` y su campaña |
| `borde` | `test_borde.py` saltada: pide un fichero local de su autora con las marcas que su detector busca | Sin el respaldo de su prueba principal aquí, para una pieza de la que depende la única salida a internet; de Polaris solo queda `test_canarios.py` verde, que comprueba que `egress_check` niega un texto con el señuelo dentro. Lo que EMMA espera de ella —que un dato de salud, un canario o el señuelo no salgan— lo prueba `tests/test_egress.py` |
| `cumbre` | `test_cumbre_integridad.py` saltada: pide el estado vivo del lazo de su autora | Nada: EMMA no usa nada suyo, solo sustituye su `foco()` |
| `decision_alto_riesgo` | `test_decision_alto_riesgo.py` roja, por tres causas, separadas una a una el 2026-10-08 corriéndola en copias temporales con y sin cada una: tres aserciones caen porque no se copia el catálogo de agentes de su autora (`.claude/agents/`), y sin él `evaluar()` da «panel INCOMPLETO»; una, porque la propia prueba escribe su informe en modo texto y en Windows su huella no es la del texto; y una, porque los permisos `0600` de su acta no existen en Windows | Ninguna alcanza a lo que EMMA llama. Las aserciones de esa misma prueba sobre `disparar()` y sobre la existencia de las citas pasan aquí, y las dos tienen pruebas de EMMA; EMMA no llama a `evaluar()` ni a `render()` ni escribe esa acta (`tests/test_polaris_windows_reds.py` lo fija). La huella con saltos de Windows sí alcanzó a EMMA por otro lado: fila de `fuente_clinica` |
| `deid` | `test_deid.py` saltada: la prueba viaja en la copia desde el 2026-10-08 (entró con `contexto_caso`), pero pide `tools/nombres.local.json`, la lista local de nombres de terceros de su autora, que no se copia | Sin respaldo de Polaris aquí para su prueba principal; `test_deid_procedencia.py` verde sí llama a `de_identificar_verificado()`, y lo que cuenta su cabecera está en la tabla de arriba. Lo que EMMA espera de esa función lo prueban `tests/test_reports.py` y `tests/test_deid_corpus.py`, y lo revalidan los mutantes `polaris_deid.json` |
| `deid_eval` | `test_deid_eval.py` roja: no se copian los ganchos de su «ventanilla clínica» | Falla lo de la ventanilla, que EMMA no usa. `cargar_brat`, `fugas` y la detección pasan dentro de esa misma prueba; `puntuar` y `offsets_cuadran` los ejercita `tests/test_deid_corpus.py` |
| `fuente_clinica` | `test_fuente_clinica.py` roja: crear un enlace simbólico en Windows pide un privilegio que el usuario no tiene | Sí alcanzó a EMMA por otro lado: en Windows la bóveda se escribía con otros saltos de línea y la huella del informe salía distinta. Corregido y fijado en `tests/test_vault.py` |
| `guarda_memoria` | `test_guarda_memoria.py` saltada: mide con `top` de macOS | En Windows las lecturas son de EMMA (`compat/memguard.py`), probadas con procesos reales en `tests/test_memguard.py` |
| `identidad_paciente` | `test_identidad_paciente.py` roja: no se copia la «ventanilla clínica»; el resto de sus casos pasa | EMMA llama a `verificar()` con la identidad del ledger, sin la ventanilla (`tests/test_report_identity.py`) |
| `seguimiento` | `test_seguimiento_objetivo_ned.py` roja y `test_seguimiento.py` saltada: piden ficheros de su autora. `test_seguimiento_carrera.py` verde desde el 2026-10-08, con el pegamento de Windows para su candado (`compat/winlock.py`); sin él los escritores se pisaban | EMMA no escribe ese fichero ni toma ese candado; `tests/test_polaris_windows_reds.py` lo fija. El candado ya aguanta, pero quien adopte un escritor de `seguimiento` tiene que resolver antes otra cosa: su `os.replace` falla en Windows si un lector tiene abierto el fichero, y los lectores no toman el candado |
| `visor3d` | `test_visor3d.py` roja y `test_visor3d_cateter.py` roja: no se copia la «ventanilla clínica». `test_visor3d_colab.py` roja: una ruta de Windows dentro de código generado. `test_visor3d_cuelgue.py` saltada: es de macOS | Ninguna toca una función que EMMA llame: las que usa las prueban `tests/test_volumes.py` y sus campañas, y las pruebas verdes de Polaris de su fila |

<!-- soup-polaris:anomalias-fin -->

*Los sitios donde el original hace algo peor para el uso de EMMA, y EMMA mantiene lo suyo o pone
una regla encima.* No se copian aquí: están decididos uno a uno en
`docs/polaris-divergencias.md` (§7.1 a §7.8, lo que EMMA conserva adaptado; §10, lo que dicen las
pruebas de Polaris en esta máquina; §15, cómo se llama a cada herramienta adoptada después y qué
no se usa de ella), y cada módulo lo declara en su cabecera con la prueba que lo demuestra. Los
que tocan un peligro: el espaciado de un afín oblicuo, la puerta de datos personales de un
NIfTI, los extremos de la cadena vertebral (H18); el nombre con tratamiento y el familiar
nombrado en la des-identificación, y la comparación de dos analíticas (H17); las ausencias
inventadas en el borrador (H14).

**Gestión de cambios: qué revisar al pasar la copia a otro commit.** La copia no se actualiza
sola ni a trozos: se cambia la línea `commit` de `polaris/ADOPTADO.txt` y se vuelve a copiar
entera. Lo que hay que mirar, en este orden:

1. **Copiar.** `backend/scripts/polaris_sync.py` recalcula el cierre de imports, copia byte a
   byte, reaplica `polaris/CAMBIOS.json` y reescribe el manifiesto. Un cambio declarado que ya
   no encaje en el fichero nuevo no se fuerza: se decide otra vez con el usuario.
2. **Que la copia sea la que se dice.** `tests/test_polaris_copy.py` (huellas, y los documentos
   que la describen) y `tests/test_polaris_headers.py` (ningún fichero sigue citando el commit
   anterior, que se añade a su lista de commits viejos).
3. **Qué carga y qué pasa.** Regenerar `polaris/ESTADO.md` (`scripts/polaris_estado.py`) y
   `polaris/PRUEBAS.md` (`scripts/polaris_tests.py --mutantes`). Una herramienta nueva que no
   carga o una prueba nueva en rojo se explican, no se toleran.
4. **Esta ficha.** `tests/test_soup_polaris.py` falla donde cambió el resultado de una prueba
   citada, donde una herramienta arrastra una biblioteca nueva o donde el cierre trajo o quitó
   algo que EMMA usa. Falla también si Polaris cambió `docs/lo-que-falta.md` o su `CHANGELOG.md`
   (se leen otra vez, se cruzan con la tabla de lo que publica y se actualiza la huella en la
   prueba), y si una herramienta, nueva o no, hace al importarse algo que no está declarado.
   Lo que no ve hay que leerlo: para cada herramienta con fila, qué cambió en
   las funciones de la columna «qué usa EMMA de ella». Varias son nombres privados del original
   (`_malla`, `_tsv_a_texto`, `_ANTI`) o dependen del texto que escribe por consola
   (`_revisa_cadena`): no tienen contrato, y un cambio suyo no avisa.
5. **Los adaptadores.** Las pruebas de EMMA de cada fila y las campañas que mutan la copia
   (`tests/mutants/polaris_*.json`): si el trozo que mutan ya no aparece una vez, la campaña no
   corre y hay que reescribirla sobre el código nuevo.
6. **Lo que llega de nuevo.** Si el cierre trae herramientas con red, con nube o con datos de
   personas, se aplica el criterio de «NO copiado» de `polaris/ADOPTADO.txt`; el registro de
   cerebros sigue con una sola entrada.
7. **El riesgo.** Si cambió una función en uso, se vuelve a escribir su «qué pasa si falla» y se
   revisa su peligro en el expediente. Y la sincronización se anota, como las anteriores, en
   `docs/polaris-divergencias.md`, en `polaris/ORIGEN.md` y en `NOTICE`.

**La sincronización del 2026-10-08, pasada por el punto 4.** Se compararon los dos commits en un
clon de Polaris, fichero a fichero, para todo lo que tiene fila en las dos tablas de arriba. Del
commit anterior al de hoy solo cambió `visor3d`; y `salida`, que no tiene fila pero la importan
tarde `seguimiento` y `cronica`.

- **`visor3d`.** Todo lo que cambia es su escena del reservorio: funciones nuevas para superponer
  un modelo de catálogo (`modelo_ilustrativo`, `ajusta_modelo_rigido` y sus auxiliares), y
  `reservorio3d` con su orden de terminal y su página. Ninguna está en la columna «qué usa EMMA
  de ella». Las nuevas llaman a `ply_binario`, que EMMA sí usa, sin cambiarla. Importan
  `scipy.spatial` dentro de una función: `scipy` ya tiene ficha.
- **`salida`.** Cambian `report_to_titular` (una excepción más a su cupo diario de avisos) y su
  orden de terminal. EMMA no carga `salida` ni llama a ninguna de las dos.
- **Lo que llegó de nuevo** son las herramientas dormidas de ese día (treinta y una desde el
  2026-10-09): su sitio
  es «lo que la copia arrastra y EMMA no llama», con lo que se midió al importarlas.

**Lo que no hay:** un procedimiento escrito para seguir las correcciones de Polaris entre una
sincronización y otra, ni un plazo para sincronizar. Una corrección de seguridad en el original
llega cuando alguien decide pasar de commit.

Los números de cláusula de este apartado que no estaban ya en el documento (7.1.3) no se han
cotejado con el texto de la norma en esta revisión: es paráfrasis de su estructura, y hay que
comprobarlo antes de citarlo fuera.

---

## 5. Qué procesos de la norma se cumplen hoy, y cuáles no

*Paráfrasis de las cláusulas 5 a 9.* Sin adornos:

| Proceso | Estado |
|---|---|
| 5.1 Planificación del desarrollo | **Parcial.** Existe un plan de proyecto con hitos y alcance, no un plan de desarrollo de software formal |
| 5.2-5.4 Requisitos, arquitectura y diseño detallado | **Parcial.** La arquitectura está documentada y cada módulo explica por qué existe; no hay especificación de requisitos numerada ni trazabilidad requisito→código |
| 5.5 Implementación y verificación de unidades | **Sí.** Suite completa en verde con `ruff` y `mypy --strict` limpios, y un criterio de aceptación por prueba. El recuento vigente lo da el README, no este documento |
| 5.6-5.7 Integración y pruebas de sistema | **Sí**, por la API, incluida la validación externa contra fisiología humana real |
| 6 Mantenimiento | **Parcial.** Seis revisiones adversarias con sus hallazgos y correcciones documentados (`record-integrity.md` §7), más una auditoría de estos dos documentos contra el código. Desde el 2026-11-16, una versión nueva llega a una instalación existente por un camino especificado y verificado —comprobación con botón, huella SHA-256, sin perder los datos de usuario— ([`software-update.md`](software-update.md)). No hay plan de mantenimiento formal ni análisis de impacto escrito por versión |
| 7 Gestión de riesgos | **Sí**, en [`risk-management-file.md`](risk-management-file.md) y en `clinical-decision-rationale.md` |
| 8 Gestión de configuración | **Parcial.** El repositorio de trabajo usa git, **solo local** y sin remoto; cada versión que se entrega se publica como una foto sin historia en `github.com/Brillande/EMMA`, con etiqueta `vX.Y.Z`, su instalador y, desde el 2026-11-16, su manifiesto con la huella (`software-update.md` §2). La versión es la misma en `backend/pyproject.toml`, `frontend/package.json`, `desktop/package.json` y `backend/app/main.py`, con prueba. Las dependencias tienen versión exacta (§4). Falta: control de cambios con aprobación formal, y la trazabilidad cambio a cambio de lo publicado vive solo en el repositorio local. Hasta el 2026-11-16 esta fila decía «el repositorio no usa control de versiones»: estaba desfasada |
| 9 Resolución de problemas | **Parcial.** Cada hallazgo queda documentado con su corrección y su prueba, pero no hay un registro formal de problemas |

**Y lo que no se reclama, por si queda duda:** ninguna certificación, ningún sistema de gestión de
calidad auditado (ISO 13485), ningún organismo notificado, ninguna evaluación clínica. "Conforme a"
significa que el diseño sigue la norma donde el proyecto llega, y que dice dónde no llega.

---

## 6. Este documento también se audita

**2026-09-22, el mismo día que se escribió.** Una revisión independiente comprobó cada afirmación
contra el código. Las once versiones de SOUP eran exactas, pero **tres fichas describían un uso que
el código no hace**: `pandas` y `scipy` no se importan en ninguna parte, y `numpy` solo lo usa el
simulador, no el análisis. Es justo el error que este proyecto dice no querer —una afirmación que
compila, pasa los tests y miente—, y en el artefacto que un evaluador de 62304 mira primero.
Corregido, junto con la clase de `evidence/links.py` (era A por un razonamiento falso), la ausencia
del simulador en la tabla de elementos, la de `pydantic-settings` en la de SOUP, y la frase que
prometía gráficos que aún no existen.

Sirve de recordatorio para quien siga: una tabla de dependencias se escribe leyendo los `import`,
no el `pyproject.toml`.

## 7. El dosier y el banco del comité siguen en la Clase C (2026-10-04)

El dosier de objeciones del comité (`app/committee_dossier.py`) y su banco de medida
(`app/committee_bench.py`) pertenecen al borrador de interpretación, Clase C por elemento (§2.1).
- El dosier ordena y marca lo que ya objetaron los verificadores. No añade juicio ni texto clínico
  propio, y no usa el texto que Polaris redacta para su autora.
- No entran en el análisis ni en una alerta: los lee quien firma.
