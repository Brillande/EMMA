# Justificación de las decisiones del motor clínico

**Estado:** implementado y verificado — 265 pruebas en verde
**Última revisión:** 2026-09-20

Este documento registra las decisiones de diseño del motor de análisis y por qué
se tomaron. Todas surgieron de pruebas que **fallaron** contra una implementación
inicial razonable pero defectuosa; ninguna se diseñó por anticipado. Se dejan
escritas porque son controles de riesgo en el sentido de ISO 14971, no detalles
de implementación, y porque revertir cualquiera de ellas reintroduce el fallo.

---

## Peligro principal: fatiga de alarma

**Descripción.** Un sistema de monitorización que alerta con demasiada frecuencia
enseña a la tripulación a ignorarlo. El daño no se produce cuando el sistema da
una falsa alarma; se produce después, cuando da la verdadera y ya nadie la mira.

**Severidad.** Alta. Anula la función completa del producto.
**Probabilidad sin control.** Alta — cuatro mecanismos distintos la producían.

Cuatro controles, cada uno contra un mecanismo independiente.

---

### Control 1 — La línea base debe moverse con el tripulante

**Mecanismo del fallo.** La primera implementación ajustaba la línea base en la
semana 1 y la congelaba. Al día 40, con la tripulación ya adaptada, todo
indicador con deriva fisiológica normal daba z-scores enormes: pulso 7,74;
desfase circadiano 7,28; cortisol 5,36. El sistema alarmaba continuamente sobre
una adaptación esperada.

**Control.** `evaluate_rolling()` usa una ventana móvil de 14 días previos a cada
lectura, con 12 h de separación para que un episodio no entre en su propia
referencia y se camufle. La base fija (`fit()` + `evaluate()`) se conserva para la
pregunta distinta de la vigilancia longitudinal: cuánto se ha alejado el
tripulante de su normalidad terrestre.

**Separación de responsabilidades resultante:**

| Módulo | Pregunta que responde | Horizonte |
|---|---|---|
| `baseline.py` | ¿Ha pasado algo **hoy**? | Agudo |
| `trend.py` | ¿Algo cambia despacio desde hace semanas? | Crónico |

Pedirle a la línea base que detecte deriva lenta fue el error de origen.

**Causa conocida y aún no controlada: la fase del ciclo menstrual** (2026-11-14). La ventana de
14 días no sigue un cambio que va y vuelve cada mes. En una tripulante sin supresión menstrual, la
fase lútea sube la temperatura (0,23-0,7 °C frente a la folicular) y la frecuencia cardiaca
(3,42-3,91 lpm en un solo estudio con wearable) y baja la RMSSD y la SDNN (sentido documentado,
sin cifra en milisegundos); una ventana que mezcla días foliculares y lúteos puede leer ese
escalón como desviación o como tendencia. Lo leído, con su clase de respaldo, está en
`backend/app/data/cycle_physiology_read.json` (`evidence/cycle_physiology.py`); la supresión
menstrual con anticoncepción continua, frecuente en misiones largas (Jain y Wotring 2016), hace
que no se aplique a toda tripulante. Ni la falsa alarma que produce ni un ajuste por fase están
medidos todavía (`external-validation.md`, «Lo que queda abierto», punto 13): hoy este control
no la cubre.

**Controlada en parte desde el 2026-11-15: el ajuste por fase, con su puerta** (lote «ciclo», B3;
`backend/app/analysis/cycle_phase.py`, puerta en `backend/app/api/cycle_phase.py`). No es una base
por fase —estratificar de más fragmenta la muestra, el error del Control 2— sino un desplazamiento:
en la fase lútea, la base personal y la tendencia se llevan a la fase de la lectura con la subida de
temperatura y pulso de la propia tripulante, medida en sus ciclos ya cerrados y acotada al rango
leído (0,23-0,7 °C, 3,42-3,91 lpm); sin ciclo cerrado propio, el extremo menor. La lectura no se toca:
los límites de peligro absolutos y el rango poblacional siguen viendo el valor medido. La RMSSD y la
SDNN no se ajustan (lo leído no da cifra). La fase lútea son 12,4 días contados hacia atrás desde la
regla (Bull 2019), solo en los días que serían lúteos con cualquiera de los ciclos recientes; un
ciclo retrasado o irregular no se ajusta. La puerta exige las tres cosas: sexo declarado femenino,
último estado reproductivo exactamente «ciclo regular» y tres inicios de regla registrados; si falta
una, no hay ajuste y la respuesta dice cuál (`cycle_phase` en `/api/status` y en
`/api/baseline-profile`). El sexo solo lo lee `api/`: el motor recibe un desplazamiento por clave e
instante. Medido con las dos métricas (`external-validation.md`, hallazgo 32 bis): WATCH de una
tripulante sana simulada 63/71/75 → 26/43/52 de 84 (subida lútea de 0,3/0,5/0,7 °C), sin bajar la
detección en la lectura (15 de 15) y devolviendo el escalado del estado (0 → 6-7 de 15) y la
febrícula lútea (0 → 2-3 de 3). Pruebas: `tests/test_cycle_nuisance.py`; mutantes:
`tests/mutants/cycle_phase_baseline.json`.

**Y junto a la fase, la menopausia** (2026-11-15). Muchas astronautas vuelan pasados los 40, y en
la perimenopausia los ciclos se vuelven irregulares y, al final, casi todos anovulatorios: sin
ovulación no hay escalón lúteo, y un ajuste por fase aplicado sin ciclo regular movería la base
personal hacia una subida que no existe y podría tapar una real. La base solo se ajusta por
fase con ciclo regular declarado; en la perimenopausia, la menopausia o la supresión menstrual,
no (desde el 2026-11-15 lo impone la puerta, con prueba). Los sofocos son lo contrario de lo que este control sigue: picos de minutos (frecuencia
cardiaca unos 9-10 lpm más alta de media, con picos de 10 a 20 lpm, la piel más caliente y la temperatura central más baja), no un
cambio de nivel, y tener sofocos no cambia la variabilidad de base medida. Lo leído, con su clase
y lo buscado sin encontrar —incluido que en vuelo no se ha medido nada de la menopausia—, está en
`backend/app/data/menopause_physiology_read.json` (`evidence/menopause_physiology.py`); la falsa
alarma de los sofocos no está medida (`external-validation.md`, punto 14).

**Verificación:** `test_baseline_uses_robust_statistics`, `test_nominal_scenario_stays_calm`.

---

### Control 2 — Significancia estadística ≠ significancia clínica

**Mecanismo del fallo.** Con 160 muestras por indicador, el contraste de la
pendiente declara real cualquier deriva minúscula. Una caída de eficiencia del
sueño de 0,37 % por semana es perfectamente detectable y clínicamente
irrelevante — y bastaba para generar una alerta.

**Control.** Una tendencia solo preocupa si además proyecta un cambio apreciable
en un horizonte operativo: **15 % del rango de referencia a cuatro semanas
vista** (`RELEVANCE_HORIZON_WEEKS`, `RELEVANCE_FRACTION_OF_RANGE`). Se exigen las
tres condiciones: real, apreciable y en la dirección clínicamente mala.

**Verificación:** `test_statistical_significance_is_not_clinical_significance`.

---

### Control 3 — El máximo de muchas muestras ruidosas no es evidencia

**Mecanismo del fallo.** El motor tomaba el z-score más extremo de cada
indicador. El máximo de 160 muestras gaussianas ronda |z| = 3 por puro azar, así
que **todos** los indicadores acababan mostrando una desviación moderada sin que
ocurriera nada.

Agravante: se vigilan 24 indicadores simultáneos. Con ~8 lecturas recientes de
cada uno son ~190 contrastes por evaluación; a 2 σ se esperan unas 9
desviaciones espurias por ciclo. Es el problema clásico de comparaciones
múltiples.

**Control, en dos partes:**

1. **Persistencia** (`_PERSISTENCE_FRACTION = 0.30`): un hallazgo exige que se
   desvíe al menos el 30 % de las lecturas recientes. El ruido no persiste.
2. **Percentil 90 en lugar del máximo** (`_FINDING_PERCENTILE`): se toma la
   lectura que el 10 % más extremo supera. Con pocas muestras equivale al máximo
   y conserva sensibilidad; con muchas resiste artefactos e inflación por valor
   extremo.

**Contrapeso deliberado.** La persistencia podría volver ciego al sistema ante un
evento agudo real y breve: sus lecturas son una fracción pequeña de una ventana
larga y nunca alcanzan el porcentaje. Por eso una **ráfaga** de lecturas graves
se reporta sin exigir persistencia (`_ALWAYS_REPORT_SEVERITY`).

Cuántas hacen una ráfaga no es una constante: se calcula para que aparecer por
azar sea tan improbable como lo era en la ventana validada, usando la tasa de
lecturas graves **medida** en los 22 sanos de MMASH. Una sola nunca basta. El
detalle y sus cifras, en [`external-validation.md`](external-validation.md),
hallazgo 26.

> Este párrafo describía hasta el 2026-09-22 un umbral `_ALWAYS_REPORT_Z` de
> |z| ≥ 6 que **ya no existe**: la gravedad dejó de decidirse por z-scores al
> pasar a cuantiles empíricos, y la red de seguridad se reescribió sobre la
> gravedad. Citaba además una prueba, `test_extreme_single_reading_always_reports`,
> que no existe. Lo encontró una auditoría de los documentos contra el código.

**Verificación:** `test_isolated_outlier_is_noise_not_a_finding`,
`test_persistent_deviation_is_a_finding`,
`test_a_single_extreme_reading_is_not_evidence`,
`test_a_burst_of_severe_readings_reports_without_persistence`,
`test_burst_threshold_keeps_the_validated_operating_point`.

---

### Control 4 — La evidencia se combina con rendimientos decrecientes

**Mecanismo del fallo.** Las puntuaciones se sumaban linealmente. Cuatro
hallazgos leves (15 puntos cada uno) alcanzaban el nivel crítico. Cuatro
hallazgos leves no son una emergencia.

**Control.** `combine_findings()` ordena las puntuaciones y aplica peso
decreciente: el hallazgo más grave marca el suelo y cada adicional aporta la
mitad del anterior. Consecuencia: muchos hallazgos leves elevan la vigilancia
sin llegar nunca a crítico, y el nivel crítico exige gravedad real.

**Verificación:** `test_critical_requires_real_severity_not_accumulation`,
`test_one_severe_finding_outweighs_several_mild`.

---

### Control 5 — Cada hallazgo se explica con la base que lo decidió

**Peligro.** Mostrar a la tripulación una justificación distinta de la que
decidió la gravedad. `describe()` explicaba todo con el z-score después de que el
z-score dejara de decidir la gravedad: un hallazgo **grave** del escenario de
arritmia se presentaba como *"35 /min, 1,7 desviaciones por debajo de su base
personal"*, cuando lo que lo hizo grave fue cruzar el límite de peligro de
40 /min. 1,7 desviaciones no es grave para nadie; el texto contradecía la
etiqueta que acompañaba.

No es cosmético. La exención de soporte a la decisión clínica del 21st Century
Cures Act descansa en que el usuario pueda **revisar independientemente la base**
de la recomendación. Una base mostrada que no es la usada no es revisable.

**Control.** Cada `Deviation` registra qué decidió su gravedad
(`SeverityBasis`: percentil personal, límite de peligro o baja confianza) y el
límite cruzado si lo hubo, y `describe()` lo dice con esas palabras: *"35 /min,
por debajo del límite de peligro (40 /min)"*, o *"por encima del N % de sus
propias lecturas de referencia (150 lecturas)"*.

De paso se unificó la graduación: `evaluate()` y `evaluate_rolling()` graduaban
por separado y solo el segundo aplicaba la red de peligro y el tope de
confianza. Producción usa el segundo, así que no fallaba nada todavía.

**Verificación:** `tests/test_severity_basis.py`.

### Control 6 — Una lectura dudosa no sostiene un hallazgo grave, tampoco en un límite de peligro

**Peligro.** Un sensor suelto que dispara alarmas graves. La red de peligro
absoluto se aplicaba **después** del tope por baja confianza y lo anulaba, y la
vía sin base personal ni miraba la confianza: una trama BLE sin contacto de
sensor que marcase 30 lpm salía como hallazgo grave. Es justo el caso en que la
cifra es menos fiable. Y como los artefactos de contacto llegan en rachas, la
regla de ráfaga no protege de ellos.

**Control.** El tope se aplica el último, sobre cualquier gravedad. "Un valor
peligroso lo es sea cual sea tu normalidad" habla de la normalidad del sujeto, no
de la calidad de la medida. La lectura no se descarta: queda como hallazgo leve,
conserva el límite cruzado, y el texto dice que no se afirma más hasta que lo
confirmen lecturas con buen contacto.

**Límite declarado.** Ninguna fuente de validación —MMASH, simulador, inyección—
produce lecturas de baja confianza. Este control no mueve ninguna cifra publicada
y **no está validado más allá de las pruebas unitarias**.

**Y la tendencia no lo aplica.** El tope y la exclusión de la referencia viven en
la línea base. El ajuste de tendencia (`analysis/trend.py`) no mira la confianza:
usa también las lecturas dudosas. No se ha cambiado —sería tocar el análisis sin
medir los dos ejes—, pero desde el 2026-10-07 se dice en pantalla.

**Lo que el control aparta, a la vista (2026-10-07).** `/api/status` →
`data.quality` cuenta por indicador las lecturas recientes de baja confianza, de
qué fuente salen, cuántas quedan fuera de la referencia y cuántos hallazgos se
limitaron a leve; la consola lo marca junto al dominio (`hmi-state-of-the-art.md`
§5.17). Solo lee lo que el motor ya calculó: con el bloque o sin él, el estado es
el mismo.

**Verificación:** `test_poor_contact_cannot_make_a_danger_crossing_severe`,
`test_rolling_path_caps_poor_contact_crossings_too`; de lo que se enseña,
`tests/test_data_quality.py` (con mutantes).

### Control 7 — El "ahora" del estado no lo decide una sola lectura

**Peligro.** El estado actual se evalúa sobre las desviaciones de los últimos
dos días, contados desde la lectura más reciente. Con eso, **una sola lectura
mal fechada esconde un hallazgo real**: reproducido, una arritmia en CONCERN
pasa a WATCH al ingerir un peso fechado en 2099, porque la ventana actual se va
al futuro y deja fuera las desviaciones de hoy. La integridad seguía en verde,
porque el registro no estaba manipulado: estaba mal fechado. Un reloj de
wearable mal puesto basta, sin ninguna malicia. Una lectura del año 1 dejaba el
endpoint en 500.

**Control.** La referencia temporal es la lectura más reciente que **no llega
sola tras un hueco anómalo**. Lo que cae después, o antes del 2000, no entra en
el análisis. Validar la ingesta no basta —y ya se valida—: el ledger es de solo
añadir, así que una lectura así, una vez dentro, se queda para siempre y el
análisis tiene que sobrevivirla.

«Anómalo» se mide contra los huecos típicos de esos mismos datos, no contra un
reloj fijo. **La primera versión no lo hacía y reproducía el fallo que arreglaba**:
exigía tres lecturas dentro de la ventana de dos días, y con un peso cada cinco
días ninguna lectura corrobora a ninguna, así que la referencia volvía a recaer
en la última sin comprobar. Funcionaba solo porque los datos de prueba eran
densos. Lo encontró una revisión adversaria, que además descartó el arreglo
evidente —tomar la lectura más antigua— porque ancla el «ahora» al primer día de
la misión para siempre.

**No se aparta nada en silencio.** `/api/status` publica `reference_time`, el
recuento `readings_ignored` por motivo, y una nota que pide revisar el reloj del
dispositivo. Si ninguna lectura tiene fecha analizable, responde 422 en vez de
inventar un estado.

**Límites declarados.** Dos. Un lote entero mal fechado —un dispositivo
emitiendo durante días con el reloj roto— sí movería la referencia: sin un reloj
de misión independiente es indistinguible de datos buenos. Y con menos de tres
lecturas en total no hay con qué juzgar: se toma la última y no se comprueba
nada. Ninguno de los dos está resuelto.

**Verificación:** `test_a_future_dated_reading_does_not_move_now`,
`test_sparse_data_also_refuses_an_isolated_future_reading`,
`test_a_gap_does_not_discard_the_data_that_comes_after`,
`test_a_reading_from_year_one_already_stored_does_not_break_status`,
`test_the_api_refuses_a_reading_from_year_one`.

## Decisión de diseño: el aislamiento modula el umbral

No es un control de riesgo sino la traducción de la premisa del reto a lógica.

En tierra, ante un hallazgo ambiguo se espera y se repite la medida, porque la
ayuda está a minutos. A 22 min de ida y vuelta —valor medido con JPL Horizons
para el 14 de noviembre de 2026— esa espera tiene otro coste: si la situación se
deteriora, la ventana de actuación ya se cerró.

`isolation_factor()` amplifica el riesgo **clínico** hasta un 35 % según el
retardo, saturando a los 40 min: pasado ese punto, más distancia no cambia la
conducta porque ya se está completamente solo.

**El factor no se aplica al riesgo de radiación.** La distancia no cambia la dosis
recibida; cambia lo que cuesta equivocarse al interpretar un hallazgo clínico.
Aplicarlo ahí habría sido confundir la métrica con la consecuencia.

**Verificación:** `test_isolation_raises_the_same_finding`,
`test_isolation_does_not_inflate_radiation_dose`, `test_isolation_factor_saturates`.

---

## Decisión de diseño: el escenario nominal es un control de verdad

El modelo nominal del simulador llevaba deriva simultánea en seis indicadores
conductuales — sueño, vigilancia, ánimo, ritmo circadiano. Es lo que se observa
en muchas misiones largas, pero convertía el control en un tripulante ya
deteriorado: sin un control limpio no hay con qué comparar los escenarios
patológicos, y la demo que debería estar tranquila alarma.

El modelo nominal contiene ahora solo las adaptaciones inevitables **que se
estabilizan**. El deterioro vive en los escenarios, donde se puede encender y
apagar a voluntad.

**Verificación:** `test_nominal_scenario_stays_calm`, `test_nominal_scenario_is_quiet`.

---

## Límite del sistema: apoyo a la decisión, no prescripción

El motor de recomendaciones no indica fármacos ni dosis, no diagnostica, y toda
acción que propone es ejecutable por la tripulación y reversible. Es la frontera
que sostiene la clasificación **IEC 62304 Clase B**: si el software falla, el
daño posible no es grave porque no ejecuta terapia.

Una consecuencia práctica: ante una situación crítica el sistema ofrece **una**
acción, no una lista. Ante una emergencia, una lista larga de opciones es ruido.

**Verificación:** `test_critical_urgency_offers_one_action_not_a_list`.

---

## Decisión de diseño: medidas ecográficas (2026-09-24)

La ecografía entra en el motor como **medidas**, no como imágenes: el diámetro de la vaina
del nervio óptico, el área de la yugular interna y el volumen vesical son lecturas del
catálogo que pasan por la misma línea base que el resto (`app/imaging/measure.py`). Cuatro
decisiones:

- **Una medida mal planteada se rechaza con su motivo; no se degrada.** Si la vaina se mide
  lejos de los 3 mm tras el globo, si dos ejes que deben ser perpendiculares no lo son, o si
  los puntos caen en regiones con escalas distintas, la API responde 422 y dice por qué. Bajar
  la confianza dejaría entrar un número mal medido con apariencia de dato.
- **Sin umbral poblacional.** Los umbrales publicados del diámetro de la vaina cambian de un
  estudio a otro, el punto de referencia de la medida está en discusión (Crit Care Med 2025,
  PMID 40459386), y en vuelo el área de la yugular pasó de 9,8 a 70,3 mm² de media en
  tripulantes sanos (Marshall-Goebel et al., JAMA Netw Open 2019). Un umbral de Tierra
  alarmaría a toda la tripulación. Prueba: `test_ultrasound_measures_have_no_population_alarm`.
- **El coeficiente sigue al código.** LOINC 15309-8 define el volumen vesical como alto ×
  ancho × largo × 0,57. Calcularlo con el 0,52 del elipsoide y etiquetarlo con ese código
  sería el error de la invariante 2 aplicado al método. Prueba:
  `test_the_coefficient_is_the_one_the_code_declares`.
- **Una medida no se enmienda: se vuelve a medir.** Su valor sale de unos puntos firmados
  sobre una imagen firmada; corregir el número lo separaría de su procedencia.

Cada parámetro del método declara su respaldo (`established`, `contested` o `design`) y se
expone en `/api/imaging/protocols`.

**Protocolos sin medida: se anotan signos, no diagnósticos.** En pulmón, FAST e hígado el operador
anota lo que ve en cada ventana —"deslizamiento pleural: ausente", "líquido libre: presente"— de
una lista cerrada, nunca el nombre de una enfermedad. Las ventanas y los signos salen de la
literatura citada en el propio protocolo (protocolo BLUE; FAST de cuatro ventanas hecho en la ISS;
deslizamiento pleural en microgravedad). Un signo sin contestar no se guarda como "ausente": el
formulario exige todos, con "no valorable" como opción. Los signos no entran en el análisis ni
generan alertas; sí llegan al borrador de interpretación, donde el linter bloquea que se
traduzcan en un diagnóstico ("compatible con neumotórax").

---

## Decisión de diseño: dolor referido (2026-09-25)

El tripulante marca en un mapa corporal dónde le duele, cuánto (escala numérica verbal 0-10,
LOINC 72514-3) y cómo. Cuatro decisiones:

- **Una sola serie: la intensidad máxima de cada informe.** Si cada zona fuera su propia serie,
  la línea base mezclaría una rodilla con una lumbar, o habría que abrir decenas de indicadores con
  una lectura cada uno. Dónde y cómo duele quedan en el informe firmado (`record-integrity.md`
  §3.11), que leen una persona y el borrador del modelo local, no el motor.
- **Dominio propio, musculoesquelético.** El dolor de espalda de adaptación al vuelo lo refirió el
  52 % de 728 astronautas (Kerstman et al., Aviat Space Environ Med 2012, PMID 22272509), en su
  mayoría leve. Meterlo en "inmune", junto a la carga de síntomas, habría mezclado dos cosas.
- **Rango de referencia 0-3, de diseño; sin límite crítico.** Es el tramo "leve" de la escala, no
  un rango observado en población, y se declara `design`. No hay un umbral de peligro absoluto
  defendible para un autoinforme, así que **sin línea base personal la intensidad no alerta**: un 6
  el primer día sale nominal. Con base personal, una subida sostenida sí cuenta, como cualquier
  otro indicador. Es la misma regla que el resto del catálogo (Control 1 y hallazgo 16 de
  `external-validation.md`).
- **Sin informe no hay cero.** "Sin dolor" es un informe explícito que registra 0; que no se
  pregunte no se rellena. Una zona que deja de marcarse en un informe nuevo baja a 0, porque cada
  informe describe el cuerpo entero.

La contramedida es de registro y confirmación: repetir el registro, anotar la actividad previa y
revisar la evolución con el médico de a bordo. Nada farmacológico: el sistema no decide analgesia.

**Marca "comentar con el médico de a bordo" (2026-09-25).** Algunos dolores no deberían esperar a la
revisión rutinaria. La lista es la conservadora de Polaris (`tools/sintomas.py`), reducida a lo que
un mapa de dolor puede expresar: opresión o dolor en el pecho, dolor intenso de cabeza o de
espalda, y hormigueo en un solo lado. "Intenso" es 7-10, el corte de Serlin et al. (Pain 1995, PMID
7659438), establecido en pacientes oncológicos y no en tripulantes: es la convención clínica más
citada, no un umbral validado en vuelo. **No es una alerta** y no pasa por el motor: sin datos para
medir falsa alarma y sensibilidad, una vía de alerta nueva rompería la invariante 5. Es una marca
informativa que se calcula al leer, desde lo firmado, y no cambia el informe (`app/pain/alarm.py`).

---

## Decisión de diseño: nivel de evidencia de cada fuente (2026-09-25)

Citar no es respaldar. Cada fuente con PMID que citan los protocolos y la evidencia se gradúa
desde su registro de PubMed (tipo de publicación y MeSH), con la jerarquía de Polaris
(`tools/tier_evidencia.py`, portada a `app/evidence/tier.py`): lo preclínico manda sobre todo lo
demás, y sin señales de diseño el nivel es "desconocido", no uno inventado. El registro se guarda
una vez (`scripts/grade_sources.py`); la aplicación no sale a la red.

Lo que destapó al aplicarse: **Hamilton et al. 2004 (PMID 15018297), citado en el protocolo
pulmonar, es un estudio en cerdos**. Sigue siendo la fuente de que el neumotórax se ve por
ecografía en microgravedad, pero ahora la interfaz dice que es preclínico. Y un límite heredado:
Marshall-Goebel et al. 2019 (PMID 31722025) lleva a la vez los MeSH de estudio prospectivo y
retrospectivo, y la regla de Polaris lo baja a "cohorte retrospectiva". Se deja así: ante señales
contradictorias, el nivel más bajo.

**Fuente sin PMID (2026-10-07).** No hay registro que leer, así que la cita y su título pasan por
la red de léxico de Polaris (`senales_desde_texto` y `teje`, tal cual, como en su `--texto`), que
por diseño solo degrada: no detecta "aleatorizado" ni "guía". EMMA acepta de ahí solo la marca de
preclínico (modelo animal o in vitro). El original saca también "caso clínico" de una frase; aquí
no se acepta, porque partiendo de "desconocido" sería subir, y un nivel clínico solo lo da el
registro. El resultado lleva `basis: "text"` y la etiqueta lo dice ("desde el texto de la cita, no
del registro"): es una lectura de palabras, no un hecho catalogado por la NLM. El texto nunca se
mezcla con un registro, porque su señal de personas podría quitarle lo preclínico, y no se lee lo
que EMMA escribe sobre la fuente (relevancia, alcance): suelen ser negaciones, y el léxico es
literal. Lo que cambió al aplicarse: **OSD-288 (bazo de ratón) deja de salir "desconocido" y sale
preclínico**, por su título ("murine spleen"). Límites, heredados: el léxico es corto, no entiende
negaciones y no reconoce "de ratón" ni "murino"; OSD-343, cuyos ficheros abiertos son de ratón
pero cuya publicación analiza también datos humanos, sigue en "desconocido".
`tests/test_evidence_tier.py` fija qué fuentes de EMMA se gradúan desde el texto; añadir una que
el léxico marque obliga a decidirlo.

---

## Decisión de diseño: registro único de evidencia (2026-10-07)

La misma fuente estaba escrita en varios sitios, cada uno con su forma: los riesgos del HRP y los
estudios de OSDR en `evidence/links.py`, los artículos del CO2 en `analysis/context.py`, el
protocolo de cada contramedida en `countermeasures.json`. Ninguna copia decía de cuándo es la
fuente, qué clase de documento es ni sobre quién se midió, y corregir una salvedad en un sitio
dejaba a los demás diciendo lo de antes. Ahora hay una ficha por fuente
(`app/data/evidence_refs.json`, `evidence/registry.py`) con los campos de EvidenceRef de la
especificación del equipo (§3) —`id`, `title`, `url`/`doi`, `organization`, `date`,
`evidence_type`, `notes`— y todos la citan por identificador. Para qué se cita lo sigue diciendo
quien cita: la misma página respalda cosas distintas en dos contramedidas.

**Dos ejes, no uno.** La especificación (§2) pide no mezclar humanos, animales y análogos.
`evidence_context` es el enumerado que ya llevan las observaciones (ISS, vuelo, análogo, Tierra,
simulado): el entorno del estudio. No dice la especie —un ratón en la ISS es `iss`—, así que la
ficha lleva además `population`. OSD-288 sale `iss` y `animal`; MMASH, `ground` y `human`. Una
fuente con animales no se puede registrar sin su salvedad de alcance, y la interfaz enseña la
población en amarillo bajo la cita cuando no son solo personas, igual que el nivel preclínico
(`compliance/hmi-state-of-the-art.md` §5.3).

**Lo que no se leyó no se rellena.** El registro se compiló sin red, solo con lo que ya estaba
escrito en el repositorio. Un campo sin respaldo es `null` y la ficha lo lista en `unverified`; lo
que no procede (una norma no tiene entorno de estudio) va en `not_applicable` y deja de contar.
Lo que sí procede y se leyó, pero ningún valor del enumerado cubre (un estudio que junta historias
de siete programas de vuelo, o un informe que mezcla la ISS, el reposo en cama y animales), va en
`outside_enum`, con el motivo en `notes`: es un campo leído, no un hueco, y forzarlo al valor más
parecido sería afirmar algo que la fuente no dice.
`GET /api/dossier/references` da el registro entero con el recuento de lo pendiente, que es la
fuente de verdad de lo que falta. El diseño del estudio no se escribe en la ficha: sigue saliendo
del registro de PubMed (`evidence/tier.py`), y una prueba comprueba que la población declarada no
contradice los MeSH guardados.

**Lo que queda fuera.** Siguen siendo citas en texto libre, no fichas: la literatura de cada
parámetro del simulador (`ingest/simulator.py`), las fuentes de los protocolos de ecografía
(`imaging/protocols.py`) y la del catálogo de límites de cabina (`environment/habitat.py`, que
repite la URL del resumen técnico de la OCHMO; una prueba vigila que ese duplicado no crezca).
Los títulos de los riesgos del HRP son la descripción de EMMA en español, no el título oficial,
y los cinco comparten la URL del listado de riesgos: falta la de cada uno.

---

## Decisión de diseño: la densidad de una lesión candidata se describe, no se interpreta (2026-10-07)

El visor mide el diámetro y el volumen de cada lesión candidata de un TAC segmentado; desde esta
fecha da también su densidad en unidades Hounsfield (`app/volumes/geometry.py`, `with_density`).
Es código de EMMA: `visor3d` de Polaris no mide la densidad por lesión. Cinco decisiones:

- **Descriptiva.** Se dan la mediana, la media, la desviación, los percentiles 10 y 90 y el número
  de vóxeles de la máscara, y la densidad del órgano fuera de las lesiones candidatas como
  referencia del mismo estudio. Nada más: EMMA no deriva de esas cifras qué es la lesión. Una
  cifra de HU dentro de una máscara automática invita a ponerle nombre, y ese nombre sería un
  diagnóstico hecho sobre (a) una máscara que nadie ha validado, borde incluido, (b) una fase de
  contraste que el estudio no declara y (c) rangos de densidad que se solapan entre lesiones de
  naturaleza distinta. Por eso no hay umbral, ni categoría, ni color por valor. Prueba:
  `test_what_is_said_next_to_a_density_describes_and_does_not_classify`.
- **Fuera del análisis.** No entra en la línea base, en el riesgo ni en una alerta, y no cambia
  ningún umbral: las dos métricas de validación (falsa alarma y sensibilidad) no se mueven
  porque nada de esto toca el motor. La segmentación sigue rotulada «segmentación automática sin
  validar» y cada lesión, «lesión candidata».
- **Mínimo de vóxeles declarado.** Por debajo de `DENSITY_MIN_VOXELS` no se da cifra: se dice
  «no valorable» y por qué. Con pocos vóxeles casi todos son borde y promedian la lesión con lo
  que la rodea. El valor es una regla de diseño de EMMA, del orden del mínimo que Polaris pide
  a cada región en `visor3d.fase()`; **no está validado contra lecturas humanas** y no tiene
  respaldo bibliográfico propio. Su fuente de verdad es el código.
- **La fase de contraste se dice junto a la cifra.** La densidad de un tejido cambia con la fase
  en que se adquirió el estudio. Un NIfTI no la lleva y EMMA no la propone, así que cada bloque
  dice que no está declarada. En la comparación entre dos estudios van las dos densidades sin
  restarlas y sin veredicto: el estado de cada lesión lo sigue decidiendo `visor3d.evolucion`
  con el diámetro. Prueba: `test_the_comparison_gives_both_densities_and_no_verdict`.
- **HU reales, y las mismas al firmar que al recalcular.** Se mide sobre los enteros que se
  publican en `ct.nii.gz`, con `scl_slope` y `scl_inter` aplicados. Las segmentaciones nuevas la
  llevan en su resumen firmado; las guardadas antes y los ejemplos precalculados la reciben al
  servir, desde su zip firmado, sin escribir nada en el ledger. Fuera de un TAC no hay unidades
  Hounsfield y no se da ninguna cifra.

**Lo que queda fuera.** Ninguna validación externa de estas cifras: los ejemplos del repositorio
confirman que el cálculo coincide con uno independiente sobre los mismos vóxeles, no que la
máscara sea la lesión. La referencia incluye los vasos del interior del órgano, y con contraste
eso la sube; se dice en la nota que acompaña a la cifra.

---

## Revisión bibliográfica (2026-09-20)

Las tres tareas de rigor que quedaban abiertas se cerraron, y dos de ellas
cambiaron el modelo:

**Los parámetros del simulador se clasificaron en tres clases de evidencia**, no
dos. "Contestado" no es lo mismo que "sin comprobar", y tratarlos igual habría
ocultado el hallazgo más importante de la revisión: **la caída de SDNN en vuelo
no está respaldada**. Hay estudios que no encuentran diferencias entre diez
astronautas y otros que observan tendencia creciente, interpretándola como
plasticidad y no como declive. El parámetro pasó de −1,5 ms/semana a una deriva
mínima marcada `contested`. Inventar una tendencia clara donde la ciencia no la
tiene habría sido peor que no modelarla.

**La deriva de frecuencia cardíaca en reposo era el doble de lo observado.** La
literatura reporta ~54,9 → 60,0 lpm en misiones de 2 a 6 meses; el modelo daba
~9,6 lpm. Corregido a 0,4 lpm/semana con meseta a las 12 semanas. (Y esa cifra es
de **después** del vuelo, no de durante: ver «Revisión de lo leído (2026-10-23)».)

**Los códigos LOINC se verificaron uno a uno.** Cuatro indicadores migraron a
código estándar tras comprobarlos en su ficha oficial; uno (RMSSD) resultó no
tener LOINC adecuado, lo cual es un resultado de búsqueda y no una tarea
pendiente. Ver `nasa-std-3001-traceability.md` y el catálogo en
`app/ingest/codes.py`.

**Los IDs de NASA-STD-3001 se extrajeron del PDF oficial**, no de memoria. La
matriz está en `nasa-std-3001-traceability.md`, y confirmó que el límite de dosis
de carrera de 600 mSv que ya usaba el sistema es exactamente el de [V1 4030].

## Revisión de lo leído (2026-10-23): dos derivas que lo leído contradice

La decimoquinta ronda leyó en qué sentido cambia cada indicador **en vuelo**
(`data/flight_direction_read.json`, `hmi-state-of-the-art.md` §5.35.14) y encontró
dos derivas del modelo nominal del simulador que lo leído no sostiene. Se
reclasifican **sin cambiar su valor** (decisión del plan de la decimosexta ronda):
el valor lo decide el usuario, con la medida de abajo delante.

- **`resting_hr_drift_bpm_per_week` (0,4 lpm/semana): de «sentido documentado» a
  «contestado».** La cifra de la que salía, 54,9 → 60,0 lpm sentados (Hughson
  2012), es de **después** del vuelo. Durante el vuelo, cuatro estudios ven la
  frecuencia cardiaca sin cambio —Hughson 2012 (6 astronautas, ISS), Xu 2013 (7,
  durante el sueño), Fraser 2012 (7, actividad diaria) y Baevsky 2007 (8
  cosmonautas, ISS: «Mean HR and HRV in the low- and high-frequency bands did not
  change during spaceflight»)— y uno la ve subir: Baevsky 1997, dos tripulantes de
  la Mir con Holter («Both crew members had significant increase of heart rate»),
  sin decir frente a qué. Otsuka 2022 resume la literatura así: «sometimes showing
  decreases, increases, or no change compared to preflight values». El peso de lo
  leído está del lado de «sin cambio», y la clase lo dice. También dice que 0,4
  lpm/semana (~5 lpm a la meseta) no es la deriva pequeña que pide «contestado».
- **`cortisol_rise_per_week` (0,0145 µg/dL/semana): de «sentido documentado» a
  «sin respaldo en lo leído»**, una clase nueva (`unsupported`): se buscó y no se
  encontró, que no es lo mismo que «diseño» (no se buscó). Su fuente decía
  «Biomarcadores de estrés elevados en misiones de 6 meses a la ISS» sin nombrar
  estudio; es el título de Agha 2020 (8 tripulantes de la ISS, visto en E16), cuyo
  resumen da elevado el cociente cortisol/DHEA antes (L-180) y durante la misión, no
  el cortisol, y por eso también figura entre las fichas buscadas. Mehta 2017 (23 astronautas, ISS) dice que en vuelo cambió la
  trayectoria diurna del cortisol salival, no que suba, y que el de plasma no
  cambió; Buchheim 2019 (12 cosmonautas, más de 140 días), que el cortisol en
  saliva «where not significantly altered» (sin decir en qué muestras). Un
  resultado de búsqueda atribuía a una presentación de NTRS (20140010672) una
  frase de cortisol «más alto en vuelo»: se leyó entera y es un estudio en Tierra
  sin esa frase; no se cita.

Cada parámetro nombra ahora sus fichas del registro de evidencia (`refs`) y, si no
tiene respaldo, dónde se buscó (`searched`); `/api/status` →
`simulation.parameters` los da. `literature_problems` rechaza una clase sin
respaldo que no diga dónde se buscó o sin ficha, un «contestado» con menos de dos fichas
(desde el 2026-10-26 también el que no cita ninguna; antes solo se le pedían al que citara alguna),
un «diseño» que cite fichas y una cita a una ficha inexistente
(`tests/test_simulator_evidence.py`, campaña `tests/mutants/simulator_drift_classes.json`).

### Qué cambiaría si se corrigieran los valores (medido, no adoptado)

Veredicto de los 9 escenarios × 4 tripulantes (36 casos, día 40 de una misión de
180, la siembra de `POST /api/simulate?crew_size=4`), con la entrada de
`LITERATURE` sustituida en memoria antes de sembrar. Se comparan nivel global,
puntuación, nivel y trayectoria de cada dominio, alertas, recomendaciones, banda
inferida y el texto de los motivos de cada dominio.

| Variante | Casos con algo distinto | Nivel global | Alertas | Puntuaciones y recomendaciones | Lo único que cambia |
|---|---|---|---|---|---|
| Tal cual (FC 0,4; cortisol 0,0145) | — | 26 nominal, 7 `watch`, 3 `concern` | 10 casos con alerta | — | — |
| FC en reposo a 0 en vuelo | 5 de 36 | igual | iguales por dominio y nivel | puntuaciones iguales; recomendaciones iguales salvo la lectura que cita una | desaparece la subida **predicha** de la FC (+4,23 /min a 4 semanas, intervalo 0,12-8,34) de crew-01 en `nominal`, `spe-event`, `progressive-insomnia` y `co2-fatigue`; en `arrhythmia`/crew-01 la alerta empieza 12 h antes, con 5 lecturas bajo el límite de peligro de 40 en vez de 3, y el motivo y las dos recomendaciones citan «39 /min» en vez de «35 /min» |
| Cortisol a 0 | 26 de 36 | igual | iguales por dominio y nivel | iguales | desaparece la subida **predicha** del cortisol salival en 25 casos (`nominal`/crew-01: +0,090 µg/dL a 4 semanas); en `co2-fatigue`, la lectura de cortisol del detalle de la alerta baja en crew-02 (0,55 → 0,46 µg/dL) y crew-03 (0,50 → 0,41, de moderada a leve) |
| Las dos a 0 | 26 de 36 | igual | iguales por dominio y nivel | como la FC | la suma de las dos |

**Ningún escenario deja de alertar** (10 casos con alerta en las cuatro filas), y
ningún nivel ni puntuación se mueve. Lo que se mueve es lo **predicho**: las dos
derivas bastan para que el motor proyecte una subida significativa de la FC en un
tripulante y del cortisol en 25 casos, que el panel de predicciones enseña. Y en
la arritmia la deriva de la FC retrasa 12 h la alerta. El desacondicionamiento
cardiovascular no se entera porque sustituye la deriva de la FC por la suya (de
diseño, 2,4 lpm/semana).

Un primer intento de esta medida escribió aquí «1 de 36» y «0 de 36» sin que la
medida hubiera terminado (su registro solo tenía la línea de base); la tabla es la
de la medida completa, rehecha el 2026-10-23.

**Invariante 5.** MMASH no pasa por el simulador: `app/validation/` no lo importa,
y medir las dos métricas con el árbol de esta ronda deja `app.ingest.simulator`
sin cargar. Con la reclasificación, `pytest -m external`: 29 en verde y 5 omitidas
(HC18 y TAC, sin datos). Falsa alarma 0,1842 % (la publicada); sensibilidad:
taquicardia sostenida 95,45 % detectada y 81,82 % marcada, episodio agudo 90,91 %
y 77,27 %, taquicardia progresiva 31,82 % y 13,64 %, colapso de HRV 13,64 % y
4,55 %. Corregir los valores tampoco las movería: no las calcula el simulador.

`rules_version` no cambia (`reglas@faf6e60fc2fd3f12` antes y después): el
simulador no está en `FINGERPRINTED`, y la clase de un parámetro no decide nada.

**Otras derivas frente a lo leído en vuelo** (anotado, sin corregir; las dos primeras se
reclasificaron el 2026-10-31, en la revisión de ese día):

- Presión sistólica y diastólica: el simulador las baja como «diseño»; lo leído
  las da como discutidas (Hughson 2012 sin cambio frente a Norsk 2015, −8 y −9
  mmHg en 24 h). Tienen ya con qué ser «contestadas».
- RMSSD (baja) y telopéptido N (sube): «diseño» en el simulador, y lo leído va en
  el mismo sentido. Tienen con qué ser «sentido documentado». (La RMSSD no: la lectura del sentido en
  vuelo la dio por discutida; ver la revisión del 2026-10-31.)
- Temperatura corporal: el simulador la deja plana; Stahn 2017 ve subir la
  **central** en reposo en vuelo. No casa, con la salvedad de qué temperatura mide
  el indicador.
- Excreción de virus latentes: el nominal la deja en 0; Mehta 2017 la ve subir en
  vuelos largos. El nominal es un control a propósito (arriba), pero lo leído no
  dice que un tripulante sano no excrete.
- SDNN «contestada»: casa con lo leído. Duración del sueño (6 h, «magnitud
  documentada»): Barger 2014 da 6,09 h en vuelo en la ISS, casa con el nivel.

### La fatiga de menú, «sin respaldo en lo leído» (2026-10-26)

**`menu_fatigue_acceptability_drop_per_week` (0,4 puntos/semana): de «contestado» a
«sin respaldo en lo leído»**, con el mismo valor (decisión del usuario,
`hmi-state-of-the-art.md` §5.38.10, sobre lo leído en §5.37.10). El único estudio en
vuelo leído, Douglas 2025 (15 astronautas en la ISS), no ve bajar la aceptabilidad
(«acceptability scores did not decrease over the mission»); lo que la ve bajar,
Meiselman 2000, es de Tierra con la misma comida servida cinco días seguidos, que no
es una misión; y el resumen de Sirius-21 (NTRS 20220014371) no da resultados. Un
estudio de Tierra con monotonía estricta no basta como el otro lado de un
«contestado». El parámetro dice dónde se buscó (`searched`) y cita las tres fichas.

No cambia nada de lo que se calcula: el valor es el mismo y la clase de un parámetro
no decide nada (el escenario `menu-fatigue` siembra las mismas lecturas). El
simulador no está en `FINGERPRINTED` (`rules_version` no se mueve) y MMASH no pasa
por él (`app/validation/` no lo importa), así que las dos métricas de la invariante 5
tampoco se mueven.

## Revisión de lo leído (2026-10-31): las dos derivas, corregidas; cuatro, reclasificadas

Decisión del usuario sobre lo medido el 2026-10-23: **la FC en reposo y el cortisol salival dejan
de derivar en el modelo nominal** (`resting_hr_drift_bpm_per_week` 0,4 → 0;
`cortisol_rise_per_week` 0,0145 → 0) y cuatro derivas de diseño reciben su clase con el valor que
tenían. Detalle, caso a caso, en `hmi-state-of-the-art.md` §5.39.22.

- **La FC conserva su clase, «contestado»; el cortisol pasa de «sin respaldo en lo leído» a
  «contestado».** La clase dice qué se leyó; el valor, qué hace el modelo. El 0 de la FC es el lado
  del peso de lo leído («sin cambio»), no una magnitud documentada. El del cortisol, que una frase
  discutida no sostiene una deriva semanal: en la misma ronda, U6 leyó a Vorobiev 1995 (sube en dos
  cosmonautas, los primeros 18 días) frente a Buchheim 2019 (sin cambio significativo en los días
  90 y 150), y el cierre alineó la clase con el sentido leído para que `/api/status` y el perfil
  de línea base no se contradigan; el valor no cambió.
- **Sistólica y diastólica: de «diseño» a «contestado»,** con su valor (0,3 y 0,2 mmHg/semana):
  Norsk 2015 (−8 y −9 mmHg en 24 h) y Baevsky 2007 («BP decreased», sin separarlas) frente a Hughson
  2012 (sin cambio, medidas cortas sentados).
- **Telopéptido N: de «diseño» a «sentido documentado»,** con su valor (1,1/semana): Smith 2005 y
  Smith 2012 dan al alza en vuelo los marcadores de resorción en conjunto. La magnitud es de diseño.
- **RMSSD: de «diseño» a «contestado»,** con su valor (0,8 ms/semana). **No es lo que decía la
  decisión,** que pedía «sentido documentado» a partir de la nota del 2026-10-23; la lectura del
  sentido en vuelo da `hrv-rmssd` como discutida desde que entró Baevsky 2007, sin cambio en la banda
  de alta frecuencia (`data/flight_direction_read.json`), y el simulador no debe contradecirla en
  `/api/status`. Queda para que el usuario lo confirme; cambiarlo es una línea.

**Se comprobó contra lo medido el 2026-10-23, y coincide.** Sobre sus mismos 36 casos, desaparecen
las 4 subidas predichas de la FC y las 25 del cortisol, y la alerta de la arritmia empieza 12 h
antes (5 lecturas bajo el límite de peligro en vez de 3). Con `transient-sleep-loss`, llegado
después, son 40 casos: 5 y 28. **En los 40, ningún nivel, puntuación, alerta por dominio y nivel,
identificador de recomendación ni banda inferida cambia;** con alerta, 14 antes y después. Lo nuevo
frente a aquella medida: la lectura de cortisol del detalle de la alerta también baja en `spe-event`
(que ahora alerta a toda la tripulación), y el contraste de lo predicho con lo ocurrido gana 11
comprobaciones fuera de margen y cambia la cifra de 10, sin ganar ningún acierto.

**Invariante 5.** Falsa alarma 0,1842 % antes y después. Sensibilidad, igual a todos los decimales:
taquicardia sostenida 95,45 % detectada y 81,82 % marcada, episodio agudo 90,91 % y 77,27 %,
taquicardia progresiva 31,82 % y 13,64 %, colapso de HRV 13,64 % y 4,55 %. MMASH no pasa por el
simulador, y `pytest -m external` da 33 en verde y 1 omitida las dos veces. `rules_version`,
`reglas@c89d7ebf4d5f4aa9` antes y después.

## Lo que sigue abierto

- **El modelo NASA Q para la dosis efectiva**, que es el que especifica
  [V1 4030] con parámetros de mujer de 35 años. Necesita el espectro LET por
  partícula, y OSDR RadLab no lo da: `quality_factor`, `lineal_energy` y `let`
  no existen, y `dose_equivalent_rate` está nulo en las 98 688 filas revisadas.
  Es un límite del dato, no del código. Mientras tanto, `environment/dosimetry.py`
  usa la dosis equivalente medida cuando la hay; si no, estima con el factor de
  calidad medio medido en vuelo (Q = 2,38, TEPC en Spacelab SLS-1) y declara
  qué Q ha usado. La función Q(L) de ICRP 60 ya está implementada para cuando
  llegue el espectro. Ver H9 en `risk-management-file.md`.
- **Las medidas ecográficas todavía no alertan.** La línea base personal exige 100 lecturas
  en su ventana de 14 días (`analysis/baseline.py`), y una ecografía se hace pocas veces:
  nunca llega a ese número. Sin base personal cae al rango poblacional, que estas medidas no
  tienen a propósito, así que hoy **se registran, se ven y forman historial, pero no disparan
  alertas**. Resolverlo exige una línea base para medidas escasas —pocas medidas preflight y
  el error de medida del operador— validada con las dos métricas de la invariante 5 a la vez.
  Hasta entonces, la interfaz no debe presentar su ausencia de alertas como normalidad.
  **Revisado el 2026-09-24: se mantiene sin alertas a propósito.** No existe un dataset abierto
  de ecografías seriadas del mismo sujeto con el que medir falsa alarma y sensibilidad, y un
  umbral sin validar es exactamente lo que la invariante 5 prohíbe. Lo que sí se hace: la tabla
  de medidas muestra la anterior del mismo indicador, su fecha y el cambio en palabras ("sube
  0,4 mm"), en color neutro, y la nota de que no alertan va en pantalla y en Tierra.

## Encaje con los huecos de NASA y con el IMM (2026-09-28)

La especificación del equipo (§16) ancla el producto en dos huecos de Exploration Medical
Capability, citados literalmente de Krihak et al., *Medical Data Architecture Prototype
Development* (NTRS 20200000567, 2020). **Ninguno de los dos figura hoy abierto**: según el Human
Research Roadmap, leído el 2026-10-13 (`data/nasa_framework_read.json`, bloque
`exmc-gaps-today`), Med 07 está cerrado y Med 10 se fusionó en Medical-701. Lo que sigue dice a
qué pregunta de cada enunciado responde el prototipo, no que EMMA cierre un hueco:

- **Med 07** (cerrado; *Closure Rationale*: "NASA now has the capability to comprehensively
  process medically-relevant information to support medical operations during exploration
  missions"). Enunciado de 2020: *"We do not have the capability to comprehensively process
  medically-relevant information to support medical operations during exploration missions."*
  EMMA integra constantes, autoinformes, ecografía, hábitat, radiación y misión en un registro
  firmado y un estado por tripulante. NASA da el hueco por cerrado con su propia capacidad; EMMA
  no ha contribuido a ese cierre ni se ha evaluado frente a ella.
- **Med 10** (fusionado en Medical-701, que el Roadmap publica abierto; la página no da motivo).
  Enunciado de 2020: *"We do not have the capability to provide computed medical decision
  support during exploration missions."* EMMA da apoyo a la decisión a bordo y sin red, con
  evidencia y contramedidas estructuradas; no diagnostica ni prescribe (invariante 7). EMMA no
  forma parte del trabajo de ExMC sobre Medical-701.

Lo mismo vale para la alimentación: el escenario de fatiga de menú es una hipótesis simulada, y
el hueco del Roadmap sobre fatiga de menú (FN-205) figura archivado y retirado del plan de
investigación actual. Que ningún texto presente como abierto un hueco leído como cerrado,
fusionado, archivado o dividido lo vigila `tests/test_gap_status_texts.py`.

**No duplica el Integrated Medical Model.** El IMM usa simulaciones de Monte Carlo sobre la base
iMED para pronosticar riesgos **antes del lanzamiento**, y entre sus salidas hay un *Crew Health
Index* de misión. EMMA vigila durante el vuelo a cada persona frente a su línea base, y por eso
no adopta un índice único de salud (propuesto en la conversación de ideación): una cifra agregada
esconde qué cambió, que es lo que la especificación pide mostrar (§2, §10). Se expone en
`/api/framework` (`exmc_gaps`, `imm`).
