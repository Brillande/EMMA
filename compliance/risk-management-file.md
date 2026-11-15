# Archivo de gestión de riesgos — ISO 14971

**Estado:** peligros identificados, controles implementados, riesgo residual declarado.
**Última revisión:** 2026-09-22

Este archivo reúne en un sitio los peligros del sistema y lo que se hace con cada uno. **No
duplica** los análisis que ya existen: los controles clínicos están razonados uno a uno en
[`clinical-decision-rationale.md`](clinical-decision-rationale.md) y los de integridad en
[`record-integrity.md`](record-integrity.md). Aquí se enumeran, se dice qué queda sin cubrir y se
nombra la prueba que lo sujeta.

> **Nota de alcance de las citas.** ISO 14971 es una norma de pago. Aquí **se parafrasea** su
> proceso, no se cita su texto.

---

## 1. Uso previsto y mal uso previsible

**Uso previsto.** Vigilar de forma continua las constantes vitales y los indicadores de salud de
una tripulación en una misión de larga duración, avisar de desviaciones respecto de la línea base
personal de cada tripulante, y **recomendar** contramedidas no terapéuticas con la evidencia que
las respalda. Pensado para operar cuando el retardo de comunicación hace inviable consultar a
Tierra en tiempo real.

**Quién lo usa.** La tripulación, incluido el oficial médico de a bordo; el cirujano de vuelo desde
Tierra cuando hay ventana de enlace.

**Mal uso previsible, y por qué importa:**

| Mal uso | Por qué es previsible | Qué lo limita |
|---|---|---|
| Tomarlo como diagnóstico | Es lo que pasa con cualquier sistema que dice "riesgo alto" | Cada hallazgo declara la base que decidió su gravedad (Control 5) y el texto nunca suena a orden médica |
| Confiar en él como única vigilancia | Es cómodo, y en una misión larga la comodidad gana | Supuesto declarado en [`software-safety-classification.md`](software-safety-classification.md) §2: si deja de cumplirse, la clase de seguridad cambia |
| Ignorar las alertas por fatiga | Documentado en sistemas clínicos reales | Es el peligro principal del proyecto: H2 |
| Meter datos de un tripulante bajo el identificador de otro | Error de operación trivial | H3 |
| Firmar un borrador del modelo sin leerlo | Sesgo de automatización: un texto bien redactado parece correcto | H14 |

---

## 2. Cómo se estima el riesgo aquí

*Paráfrasis del proceso de ISO 14971:2019:* identificar peligros, estimar el riesgo de cada
situación peligrosa, controlarlo, evaluar el riesgo residual —incluido el que introduce el propio
control— y realimentar con lo que se aprenda en producción.

**La probabilidad no se estima con números, y decir lo contrario sería inventar.** No hay datos de
frecuencia de estos fallos en una misión de larga duración; no existe ninguna. Lo que sí hay es
**frecuencia medida sobre fisiología humana real** para los dos peligros clínicos principales (H1 y
H2), y para el resto una clasificación cualitativa honesta. Las columnas dicen cuál es cuál.

| Gravedad | Significado en este contexto |
|---|---|
| **Alta** | Contribuye a que un deterioro de salud avance sin que nadie lo vea |
| **Media** | Lleva a una contramedida innecesaria, a una decisión sobre un dato falso, o deja el sistema sin servicio |
| **Baja** | Degrada la calidad de la información sin cambiar la decisión |

---

## 3. Peligros, controles y riesgo residual

### H1 — Un deterioro real no se señala (falso negativo)

*Gravedad alta.* La tripulación tarda más en aplicar una contramedida porque el sistema no avisó.

**Causas:** umbrales demasiado altos; la línea base personal absorbe la deriva; la ventana móvil
diluye un cambio lento; la lectura llega con confianza baja; el indicador no está instrumentado.

**Controles:** el segundo eje de validación —sensibilidad sobre deterioros inyectados en fisiología
real— es un control de riesgo, no una métrica de vanidad, y tiene prueba de regresión
(`test_sensitivity_does_not_regress`, `test_acute_episode_is_detected_without_personal_baseline`,
`test_short_window_sensitivity_does_not_regress`). El escalado sin persistencia para episodios
agudos (`test_acute_episode_escalates_without_persistence`) existe justo para que un evento rápido
no espere a confirmarse. Cuando la causa es la confianza de la medida, deja de estar oculta:
`/api/status` → `data.quality` dice por indicador cuántas lecturas recientes son de baja confianza,
de qué fuente salen y cuántos hallazgos quedaron limitados a leve, y la consola lo marca junto al
dominio para que se revise el sensor (`tests/test_data_quality.py`). Es información, no detección:
no recupera el hallazgo limitado.

**Riesgo residual, medido y declarado.** Con la configuración actual queda marcado el dominio en
el 82 % de las taquicardias sostenidas y el 77 % de los episodios agudos inyectados —**y en mucho
menos de lo demás**: la taquicardia progresiva y el colapso de HRV caen muy por debajo, y la
proporción que además *escala* la urgencia es menor todavía. Las tres métricas de cada deterioro
—detectado, dominio marcado y escalado— están en la tabla de
[`external-validation.md`](external-validation.md); esa tabla y los tests `-m external` son la
fuente de verdad, no este párrafo ni el encabezado de aquel documento. **Es una pérdida aceptada a cambio de H2**, y la decisión está
argumentada allí. Quien lea esto tiene que saberlo: un deterioro lento y sin síntomas puede
pasársele al sistema.

**Riesgo de un ajuste por fase del ciclo que tape una subida real** (2026-11-14; sin control
hasta el 2026-11-15, control implantado abajo). Para quitar la falsa alarma de la fase lútea (causa nueva de H2) está previsto
llevar la línea base y la lectura a la misma fase, quitando a cada valor la variación de su fase
leída en `backend/app/data/cycle_physiology_read.json` (con su signo: en la lútea la temperatura y
la frecuencia suben, así que la base que se compara con una lectura lútea tiene que subir, no
bajar).
Ese desplazamiento, mal aplicado —con el signo invertido, sobre el lado equivocado, con una fase
mal estimada o alcanzando los límites absolutos de peligro—, convertiría una fiebre o una
taquicardia que llegue en la fase lútea en «lo esperado de la fase». El control está pendiente
(unidad B3 del lote «ciclo»): el ajuste no toca los límites absolutos, se aplica solo con sexo
declarado y un inicio de regla registrado, y se acepta solo si la sensibilidad no baja, incluida
una fiebre en la fase lútea, medida junto con la falsa alarma (invariante 5).

**Control implantado (2026-11-15, B3).** El ajuste existe (`backend/app/analysis/cycle_phase.py`) y
se controla así, cada punto con su prueba en `tests/test_cycle_nuisance.py` y su mutante en
`tests/mutants/cycle_phase_baseline.json`:
- **El signo**: en la lútea la base sube hasta la fase de la lectura (o, lo mismo, a la ventana se le
  resta la subida de su fase); invertirlo, en la base o en la tendencia, lo detecta una prueba.
- **El lado**: solo en la fase lútea; aplicarlo en la folicular lo detecta una prueba.
- **Los límites absolutos**: el desplazamiento mueve la base, nunca la lectura; una temperatura por
  encima del límite de peligro en plena lútea sigue siendo grave por el límite, con su valor medido.
- **Cuánto**: la subida de la propia tripulante, medida solo en ciclos ya cerrados (una fiebre del
  ciclo en curso no se descuenta a sí misma) y acotada al rango leído; sin ciclo cerrado, el extremo
  menor. Lo más que puede taparse es el extremo mayor de lo leído (0,7 °C, 3,91 lpm), y solo si
  ciclos anteriores lo midieron.
- **La fase**: tres inicios de regla, causal, solo en los días lúteos con cualquiera de los ciclos
  recientes; una regla retrasada o un ciclo irregular no se ajusta.
- **La puerta** (`backend/app/api/cycle_phase.py`): sexo declarado femenino, estado reproductivo
  exactamente 1 (1,5 no vale) e inicios suficientes; si no, el estado es idéntico al de sin ajuste.
- **La sensibilidad, medida con la falsa alarma** (`external-validation.md`, hallazgo 32 bis): con
  ajuste, la detección en la lectura sigue en 15 de 15, el escalado del estado sube de 0 a 6-7 de 15
  y la febrícula lútea vuelve a subir el estado (2 de 3 a 0,3 °C, como sin ciclo; 3 de 3 a 0,5 y
  0,7 °C).

**Riesgo residual:** simulado, no fisiología real; una mujer real puede tener una subida que varíe
de un ciclo a otro más que el simulador, y una fiebre menor que la subida descontada, en plena
lútea, se juzga contra una base más alta.

**Y sin ciclo regular, ningún ajuste por fase** (2026-11-15). En la perimenopausia —el caso
probable de una astronauta pasados los 40 en una misión larga— los ciclos se alargan y se vuelven
irregulares, y en la perimenopausia tardía la mayoría son anovulatorios: sin ovulación no hay
escalón lúteo (leído en `backend/app/data/menopause_physiology_read.json`, con su clase). Un
desplazamiento por fase calculado desde el último inicio de regla y una longitud de ciclo que ya no
se cumple restaría a la base personal una subida lútea que no existe, y una fiebre o una
taquicardia real quedaría tapada por «lo esperado de la fase». El ajuste solo se aplica con ciclo
regular declarado; sin él (perimenopausia, menopausia, supresión menstrual) la base no se ajusta,
y se dice. Es un requisito para la unidad B3, sin control todavía: cómo varían la temperatura, la
frecuencia y la variabilidad en ciclos irregulares se buscó y no se encontró. **Implantado el
2026-11-15**: la puerta de `backend/app/api/cycle_phase.py` exige el último estado reproductivo
exactamente 1, y con supresión, perimenopausia o 1,5 el estado es idéntico al de sin ajuste
(`test_the_gate_opens_only_with_all_three_and_says_what_is_missing`).

### H2 — Alarma sobre alguien sano (falso positivo) y fatiga de alarma

*Gravedad media, y la puerta de entrada a H1:* un sistema que cría lobos deja de mirarse.

**Causas:** las siete de `clinical-decision-rationale.md` — línea base poblacional en vez de
personal, significancia estadística confundida con clínica, el máximo de muchas muestras ruidosas,
evidencia sumada sin rendimientos decrecientes, gravedad sin su base, una lectura dudosa que
sostiene un hallazgo grave, y un "ahora" decidido por una sola lectura. **Y una octava, conocida
y sin controlar (2026-11-14): la variación cíclica de la fase lútea** en una tripulante sin
supresión menstrual —temperatura y frecuencia cardiaca más altas y variabilidad vagal más baja,
leídas con su clase de respaldo en `backend/app/data/cycle_physiology_read.json`—, que la ventana
de 14 días no sigue. MMASH no tiene mujeres: la cifra de abajo no la incluye, y la falsa alarma que
produce está sin medir (`external-validation.md`, «Lo que queda abierto», punto 13). *Desde el
2026-11-15, medida en el simulador y controlada en parte*: el ajuste por fase (Control 1 de
`clinical-decision-rationale.md`) baja las evaluaciones en WATCH de una tripulante sana de
63/71/75 a 26/43/52 de 84 con subidas lúteas de 0,3/0,5/0,7 °C (12 sin ciclo), sin bajar la
sensibilidad (hallazgo 32 bis). Lo que queda es la RMSSD (sin cifra leída, sin ajuste) y el primer
ciclo sin ciclo cerrado propio. **Y una
novena, también sin controlar (2026-11-15): los sofocos** de la perimenopausia y la menopausia,
picos de minutos en que la frecuencia cardiaca sube (unos 9-10 lpm de media en un estudio, picos
de 10 a 20 lpm en otro) y la piel se calienta unos
3,9 °C mientras la temperatura central baja de 0,2 a 0,6 °C (leídos en
`backend/app/data/menopause_physiology_read.json`). Un sofoco nocturno cabe en una sola lectura y
el motor puede tomarlo por un episodio agudo; la conductancia esternal, que es como se mide un
sofoco, no la tiene EMMA, y fuera del laboratorio coincide con lo que la mujer refiere en un 29 %
de los casos. El simulador no tiene sofocos y su falsa alarma está sin medir (`external-validation.md`, punto
14).

**Controles:** los siete de ese documento, cada uno con su prueba, comprobadas una a una. El
Control 3 citaba hasta el 2026-09-22 una prueba inexistente y describía un umbral por z-score que
el motor ya no usa; el propio documento deja escrito qué decía antes y por qué era falso.

**Riesgo residual:** 0,23 % de las lecturas de 22 personas sanas de MMASH producen alarma (2 de 22
sujetos). Regresión: `test_external_alarm_rate_does_not_regress`,
`test_healthy_subjects_mostly_get_no_alert`, `test_burst_rule_rate_is_what_healthy_people_produce`.

**La cifra que de verdad mide este peligro no es esa, y desde el 2026-09-22 también está sujeta.**
La fatiga de alarma no la produce una tasa por lectura: la produce el número de **avisos**. Las 43
lecturas marcadas de MMASH son **17 episodios** en 30,8 días-sujeto —2,5 lecturas cada uno—, y de
esos 17 solo dos llegan a ser un estado no nominal que un tripulante vería. En avisos visibles:
**menos de uno por tripulante y semana**. La diferencia entre las dos formas de contar crece con la
cadencia del sensor: un wearable que muestree el doble de rápido duplica la tasa por lectura sin
producir un solo aviso más. Módulo `app/validation/episodes.py`, regresión en
`test_alerts_per_crew_week_does_not_regress` (marcada `external`).

**Y los 17 episodios tienen causa conocida, que es mejor noticia que un número bajo.** Once los
decide el límite de peligro absoluto y no la base personal, varios rozándolo —110,0 · 110,03 ·
112,3 · 112,6 · 116,3 lpm—; cuatro ocurren con el contexto **sin etiquetar**, y ahí están los dos
que alertan; cuatro son caídas de HRV durante actividad o comida, que es fisiología normal. Solo
intervienen dos indicadores: pulso y HRV. Ninguno de los dos mecanismos se corrige moviendo
umbrales, así que corregirlos no cuesta sensibilidad.

**Y el techo que impone la regresión por lectura, que importa tanto como la cifra:** hasta el
2026-09-22 era
**1,32 %** —una constante desfasada de 0,32 % más una tolerancia de un punto entero—, así que una
regresión de 0,23 % a 1,2 % habría pasado en verde. Lo encontró la auditoría de este documento y
está corregido: la constante es ahora la medición vigente (0,23 %) y la tolerancia 0,05 puntos, con
lo que el techo queda en **0,28 %**. Una prueba de regresión que tolera cinco veces lo que vigila
no es una prueba de regresión.
**Lo que esta cifra no dice:** MMASH son 22 personas sanas, 24 horas, en Tierra. Valida el motor de
medida y la tasa de falsa alarma, no la deriva fisiológica del vuelo.

### H3 — Una lectura queda atribuida al tripulante equivocado

*Gravedad alta:* contamina la línea base de dos personas a la vez, y la línea base es lo que decide
todo lo demás.

**Controles:** el tripulante es obligatorio y no puede ser vacío en ningún camino de entrada
(`test_an_empty_subject_is_rejected_everywhere`); la lectura se reasigna al tripulante correcto por
**enmienda anexada**, que corrige sin borrar y deja las dos versiones en el registro
(`record-integrity.md` §3.7, `test_a_misattributed_reading_moves_to_the_right_crew_member`); y si el
dato nunca debió registrarse, se suprime con lápida firmada (§3.6).

**En pantalla (2026-10-07, con el selector de tripulante).** Mientras la consola solo mostraba a
`crew-01` este peligro no existía en la interfaz. Al poder elegir a quién se mira, aparece: ver los
datos de una persona bajo el nombre de otra, o firmar un reconocimiento en el registro de otra
—en un escenario compartido los cuatro tienen la misma alerta en el mismo instante, y la firma
equivocada entraría sin error—. Controles: al cambiar de tripulante el estado anterior se retira
antes de pedir el nuevo y la respuesta de quien ya no es el elegido se descarta; la franja fija
dice de quién es lo que se ve; y toda firma lleva el sujeto del estado en pantalla, exigido por el
tipo de la llamada (`frontend/src/App.tsx`, `lib/crew.ts`, `compliance/hmi-state-of-the-art.md`
§5.18). Las reglas puras tienen prueba (`crew.test.ts`); la retirada del estado y el descarte de la
respuesta tardía viven en el componente y **no tienen prueba automática**.

**Riesgo residual:** **no hay autenticación de operadores ni de fuentes en la API.** Quien puede
llamar al endpoint puede escribir en nombre de cualquier tripulante. Declarado en
`record-integrity.md`. Es el hueco más grande de esta tabla.

### H4 — Un valor se interpreta en la unidad equivocada

*Gravedad media.* 170 lb guardadas como 170 kg no son un error de redondeo: son un sujeto
distinto.

**Controles:** el catálogo fija unidad por indicador y la invariante "la unidad sigue a la
propiedad LOINC" (`CLAUDE.md`); las importaciones convierten las unidades que conocen y **rechazan
las que no**, informando de cada rechazo (`test_units_are_converted_and_unknown_ones_reported`,
`test_rejected_readings_are_reported_not_dropped`).

**Riesgo residual:** el conjunto de unidades reconocidas es pequeño y cerrado. Una unidad nueva de
Apple Health se rechaza —no se malinterpreta—, pero el dato no entra; quien importe tiene que leer
el informe de rechazos.

### H5 — Un registro se altera, se borra o se inserta

*Gravedad alta:* una decisión clínica sobre datos falsos, sin que nadie pueda notarlo.

**Controles:** el módulo entero de `record-integrity.md` — cadena de hashes, firma Ed25519 por
asiento, registro de claves, lápidas firmadas, árbol de Merkle, cotejo con el disco. Seis
revisiones adversarias (§7 de ese documento). Dos ficheros dedicados a atacarlo —`test_ledger.py`
y `test_integrity_attacks.py`— con una prueba por hallazgo de cada ronda.

**Riesgo residual:** el truncado puro de la cola solo lo detecta un ancla, y hoy ningún camino de
la aplicación verifica contra una; en modo aprendido, quien da de alta una identidad en la base
puede añadir asientos que verifican. Ambos declarados en §3.2 y §3.3.

**Señuelo de exfiltración (2026-10-04).** Un fichero señuelo de Polaris (`canarios.sembrar_estado`)
vive en el estado del borde de EMMA. Ningún flujo lo lee, así que su token no tiene explicación
inocente en algo que sale: `borde.egress_check` lo bloquea en `core/egress.py`. Sin señuelo, ese
control del borde no tenía nada que buscar. Se siembra una vez y no se rota en cada arranque
(`test_the_decoy_token_never_leaves`, mutantes `decoys.json`).

### H6 — Una lectura entra y desaparece en silencio

*Gravedad media.* Peor que rechazarla: nadie se entera.

**Controles:** las importaciones no descartan en silencio —cada lectura rechazada se cuenta y se
informa—; el almacén es append-only y escribe en transacción; y `query()` se niega a entregar una
lectura cuyo contenido no case con su hash firmado: eso es un 409 y no un dato a medias. Un cuerpo
mal formado en la frontera es otra cosa, y es un 422.

**Riesgo residual:** el informe de rechazos de una importación **no se persiste**: viaja en la
respuesta HTTP y se pierde si el cliente no lo guarda. Y se recortan a 20 los rechazos detallados
para que la respuesta no crezca sin límite, aunque el total sí se informa.

**Una medida deja de llegar sin avisar (2026-10-01).** Un pulsómetro sin batería o una PVT que
nadie hace no mueven la línea base: se parecen a "todo normal". Control: `app/routines.py`
(Polaris `estado_rutina`) clasifica cada medida periódica en al día, atrasada, rota o nunca
corrió, con periodos declarados como parámetros de diseño (`app/data/routines.json`), y la consola
de tripulación muestra las atrasadas y rotas. Una lectura de confianza baja cuenta como ejecución,
no como éxito. **Residual:** los periodos no tienen fuente de NASA; son los de EMMA.

**La PVT cuenta lapsos de otra manera que la fuente (declarado el 2026-10-14).** Leído Basner et
al. 2011 (`app/data/instruments_read.json`), EMMA difiere en cuatro cosas: cuenta un lapso con
«> 500 ms» y la fuente con «≥ 500 ms»; su umbral es el de la PVT de 10 minutos, y la versión breve
usa ≥ 355 ms; un estímulo sin respuesta es lapso a los 30 s en lo publicado y en EMMA la prueba de
consola se abandona a los 10 s sin enviar nada; y `MIN_TRIALS` no tiene valor publicado. Las tres
primeras van en el mismo sentido: con ellas EMMA cuenta **menos** lapsos que lo publicado, no más. Control: se declaran, con la frase de
la fuente, en `GET /api/pvt/protocol` (`divergences`), y lo que dice de EMMA se deduce del código
que puntúa (`ingest/pvt.is_lapse`), no se copia a mano. Desde el 2026-10-15 el panel de la PVT
las enseña plegadas bajo el protocolo (`frontend/src/pvt/divergences.ts`). **Residual:** no se han corregido; moverlas
cambia el indicador de lapsos que el análisis vigila (invariante 5) y es decisión del usuario.
`tests/test_pvt_divergences.py` fija los valores que puntúan; campañas `pvt_divergences.json` y
`pvt_scoring_fixed.json`.

### H7 — Se decide sobre un dato ambiental viejo

*Gravedad media.* Una alerta de evento solar de hace tres días no es una alerta.

**Controles:** la caché declara la antigüedad de todo dato externo (`test_cache_reports_age`); el
modo offline responde con el dato cacheado **y su edad**, nunca como si fuera fresco; el "ahora"
del estado no lo decide una sola lectura (Control 7). **Vigencia de una consulta** (2026-10-01,
parámetro de diseño): con red, DONKI no se vuelve a pedir durante 15 min ni RadLab durante 6 h;
el dato se sirve de la caché con su edad (`test_a_recent_cache_is_used_without_going_out`, mutantes
`environment_freshness.json`). 15 min no esconde un SPE: DONKI lo publica con decenas de minutos de
retraso y Tierra lo ve además con el tiempo de luz. Antes cada estado de salud llamaba a DONKI y,
con la cuota de `DEMO_KEY` agotada, agotaba también la de las demás consultas. Para producción se
usa una clave propia de api.nasa.gov en `EMMA_NASA_API_KEY`.

**Instantánea fechada de DONKI para la demo sin red** (2026-11-04). La aplicación de escritorio
arranca con la caché vacía; con `EMMA_DONKI_SNAPSHOT=true` (lo pone `desktop/main.cjs`), sin red y
sin caché, `DonkiClient` sirve `app/data/donki_snapshot.json`: una respuesta real de DONKI escrita
tal cual por `scripts/fetch_donki_snapshot.py`, con la URL de la consulta (sin la clave), la fecha
de descarga y la licencia. Controles: nunca tapa una caché ni un dato en vivo y no se escribe en la
caché; su edad es la de la descarga, así que sale **caducada** (cian) y su edad se dice
«instantánea de DONKI del <fecha>, no en vivo»; sus eventos llevan su fecha real y no se mueven en
el tiempo para parecer vigentes; con datos de DONKI caducados (instantánea o caché vieja), el
hábitat dice que no cubren los últimos días y que no se sabe si hay evento (no «ningún evento»), y
la capacidad «Meteorología espacial» no se da por disponible (`tests/test_spe_demo_offline.py`,
mutantes `donki_snapshot.json`). Sin red, lo que acorta la monitorización es la dosis de a bordo,
no la instantánea (`app/routines.py`).

**Cerrado el 2026-11-11 (Lógica 1):** la ventana de DONKI corre con el día y la clave de la caché
llevaba sus fechas, así que sin red la consulta de ayer no casaba con la de hoy y se servía «sin
datos» (o la instantánea, más vieja) con una caché de un día en el disco. Ahora se usa la última
consulta de la misma anchura de ventana, con la edad de esa consulta, y solo si empieza en el
principio pedido o antes (`test_offline_the_next_day_uses_yesterdays_query_with_its_age`,
`test_an_earlier_query_does_not_vouch_for_days_it_never_asked`); entre ella y la instantánea del
paquete gana la más reciente (`test_an_older_saved_query_does_not_hide_a_newer_snapshot`). Un 200
sin JSON de DONKI, o sin la tabla *split* de RadLab, es una consulta fallida (caché vieja o «no
disponible»), no un 500 ni una «ventana mal pedida». El «hoy» del retardo, de su cobertura y de
DONKI es el día UT, no el del reloj local (`tests/test_environment_logic.py`). El día del
retardo que escala el riesgo no cambia de criterio (el pedido o hoy), y la validación externa
(`app/validation`) no pasa por el retardo: sus dos métricas no cambian.

**Series continuas de CCMC iSWA (2026-11-11).** `GET /api/space-weather/series` sirve el flujo
integral de protones ≥10 MeV de GOES (pfu) y el viento solar, de iSWA por HAPI
(`environment/iswa.py`; datos de NOAA SWPC redistribuidos por la NASA). Mismos controles que
DONKI: cada serie lleva la edad de su consulta **y la de su última muestra** (la serie llega unos
10 min tarde); sin red, la última serie guardada con su edad o «no disponible»; un relleno es un
hueco, no un cero; un parámetro que no vuelve en la cabecera o una unidad distinta de la exigida
es un cuerpo roto (iSWA ignora en silencio un parámetro desconocido), no una serie
(`tests/test_iswa.py`, mutantes `iswa.json`). Es el entorno en órbita geoestacionaria y en L1, no
la dosis de la nave: no entra en ningún nivel, alerta ni riesgo; la referencia S1 de NOAA (10 pfu)
viaja citada y con `evaluated: false`. Vigencia de una consulta: 5 min (la cadencia de la serie).

**Posición de la ISS y contorno de la SAA (2026-11-11, SSCweb).** `GET /api/orbit/iss`
(`environment/orbit.py`), solo con el perfil `leo`; con otro, «no aplica» y no sale a la red.
Descriptivo: no cambia riesgo, niveles, umbrales ni alertas, y no entra en el ledger. Controles:
la posición sale con la edad de la consulta y se dice que es una efeméride, no telemetría; sin red
se usa la consulta guardada solo si su ventana cubre el instante (a menos de 90 s de una
muestra), nunca se extrapola; un `StatusCode: ERROR`, un cuerpo roto o un tramo sin efemérides es
«no disponible», no «fuera de la SAA»; la frontera es el contorno `SAACONT` de la CALDB de
NICER (instrumento instalado en la ISS, NASA GSFC, válido desde 2017-06-01), verificado en el
propio fichero el 2026-11-11, con sus límites declarados (contorno de fondo de partículas de
NICER, no de dosis; umbral no declarado; sin la deriva posterior; solo para la órbita de la ISS),
y la ruta dice «dentro del contorno publicado», no «dentro de la SAA». Sustituye a la caja de
1996 a 500 km, que se leyó también en su fuente (NASA, «Ask an Astrophysicist» 961004) y queda
como `superseded` porque a la altura de la ISS exagera la SAA (`tests/test_orbit.py`, mutantes
`sscweb.json`; detalle en `backend/spikes/HALLAZGOS.md` §7).

**Cerrado el 2026-11-11 (perfil y efemérides, decisión del usuario):** el perfil de misión
declarado (`EMMA_MISSION_PROFILE` o el último asiento `mission-profile`) y el cuerpo hacia el que se
calculaba el tiempo de luz (`EMMA_TARGET_BODY`, Marte por defecto) eran independientes: con órbita
baja declarada, el factor de aislamiento escalaba el riesgo con el tiempo de luz de Marte (~1,2 en
vivo), y `/api/status` solo lo decía con el estado `mismatch`. Ahora el objetivo lo decide el perfil
vigente en un único punto (`mission_profiles.ephemeris_target`), y todo lo que consulta efemérides
(el estado, `/api/comms`, la precarga y su guion, la cobertura) pasa por él. Un perfil sin objetivo
(órbita baja, cislunar, superficie lunar, o uno no reconocido) no consulta Horizons ni su caché: el
factor de aislamiento es 1, la conjunción y la cobertura se sirven `null`, `/api/comms` es un 404
y la precarga un 409, y `mission.profile.ephemeris` lo declara con su estado propio (`no_target`),
sin cifra y sin el «sin efemérides» de un fallo (tampoco la vigilancia cuenta el retardo como
capacidad perdida). `EMMA_TARGET_BODY` ya no manda: si alguien lo puso y difiere del objetivo del
perfil, se dice que se ignora. El estado lee el perfil una sola vez y sirve el mismo con que pidió
el tiempo de luz. Efecto en el riesgo: con perfil de órbita baja, el
factor de aislamiento pasa de ~1,2 a 1,0 en vivo (los niveles se calculan igual que un día sin
efemérides); con un perfil de Marte no cambia nada. No se toca ningún umbral, línea base ni regla
del riesgo, y la validación externa (`app/validation/report.py`, `family_variants.py`) llama a
`RiskEngine().assess` sin tiempo de luz (`comms=None`, factor 1): **las dos métricas de la
invariante 5 (falsa alarma y sensibilidad) no cambian**. Pruebas: `tests/test_mission_profile.py`
(perfil `leo` sin consulta a Horizons y con factor 1, `mars-transit` hacia 499, el perfil firmado
manda sobre el configurado, y ningún módulo salvo el punto único lee `EMMA_TARGET_BODY`); campañas
`mission_profile.json`, `mission_profile_declaration.json` y `ephemeris_preload.json`.

**Tiempo de luz calculado en local con SPICE (2026-11-11, `environment/spice.py`).** Sin red y sin
efeméride de Horizons en caché, el retardo de un día salía «sin dato» y el factor de aislamiento
valía 1: con la misión configurada (del 2026-11-01 al 2027-04-30) y caché solo del 4 al 9 de
noviembre, casi toda la misión se evaluaba sin escalar el riesgo por el aislamiento. Ahora, si
`spiceypy` (extra `[spice]`) y los núcleos fijados de NAIF (`naif0012.tls`, `de432s.bsp`, en
`data/spice/`) están, esos días se calculan en el equipo. Precedencia (primera versión, invertida el
mismo día: ver «SPICE primero» abajo): la caché de Horizons, después Horizons en vivo, y SPICE solo
cuando Horizons no se puede consultar o responde algo inservible. Cada ventana declara su origen (`source`: «JPL Horizons» o
«SPICE local, núcleo de432s.bsp») y lo de SPICE no se escribe en la caché de Horizons. **Efecto en el
riesgo:** con un perfil de Marte, un día sin caché pasa en vivo de factor 1,0 a >1 (en esta misión,
de 11 a 24 min de ida y vuelta: siempre por encima de los 10 min de autonomía). Es el mismo factor
y la misma fórmula (`risk.isolation_factor`) que con la efeméride de Horizons de ese día: no se toca
ningún umbral, línea base ni regla. La validación externa no usa tiempo de luz (`comms=None`,
factor 1, ver arriba): **las dos métricas de la invariante 5 no cambian**. Controles: un núcleo con
otro tamaño, otra huella SHA-256 fijada u otro MD5 publicado por NAIF no se carga; solo Marte
(por su baricentro) y solo desde el geocentro; un día fuera de la cobertura del núcleo es «no
disponible», nunca extrapolado; el tiempo de luz de SPICE se contrasta con el que sale de la
distancia. Coincidencia con Horizons medida en los 181 días de la misión
(`spikes/HALLAZGOS.md`): ≤ 3 µs de tiempo de luz, ≤ 0,73 km de distancia, ≤ 0,00005° de elongación
y la misma marca `/T`-`/L`; error declarado 0,1 s y 0,01°. Sin `spiceypy` o sin núcleos, como antes
y dicho («SPICE no instalado», «Núcleos SPICE ausentes»). Pruebas: `tests/test_spice.py` (con
`spiceypy`, un núcleo diminuto hecho en la prueba con la geometría contada a mano); campaña
`spice.json`. **Residual:** un segundo intercalar nuevo dejaría `naif0012.tls` desfasado un segundo
(el error en tiempo de luz sería de microsegundos); un objetivo nuevo de perfil necesita su núcleo.

**SPICE primero (decisión del usuario, 2026-11-11).** La precedencia de arriba se invierte: si SPICE
puede calcular el día (instalado, núcleos verificados, día dentro del núcleo, objetivo y observador
soportados), el retardo sale de SPICE sin salir a la red, también con red. Motivo: sin red es el
modo nominal de misión, y SPICE calcula la misión entera en local con el mismo resultado que
Horizons (peor diferencia 0,003 ms de tiempo de luz en 181 días, `spikes/HALLAZGOS.md` §10).
Horizons queda de **contraste** —su efeméride de ese día en caché, si la hay; no se pide nada en
vivo solo para contrastar— y de **respaldo** —si SPICE no calcula el día: la caché de Horizons,
después Horizons en vivo, y si nada, «sin dato», como antes—. **Control nuevo:** si el contraste
discrepa por encima del error declarado (0,1 s de tiempo de luz o 0,01° de elongación), la ventana
lo dice (`contrast.agrees = false`, con las dos diferencias), queda en el registro como error y ese
día se usa Horizons, la referencia: la discrepancia no se esconde ni se promedia. Con contraste
coincidente, la ventana sale de SPICE y lleva el contraste (`contrast.agrees = true`). Una
respuesta inservible de Horizons ya no se tapa con SPICE: con SPICE disponible no se le pregunta, y
sin él es el error de siempre. **Efecto en el riesgo: ninguno numérico.** El tiempo de luz que
entra en `risk.isolation_factor` es el mismo dentro del error declarado (microsegundos frente a
los minutos que mueven el factor); no se toca ningún umbral, línea base ni regla. La validación
externa no usa tiempo de luz (`comms=None`, factor 1): **las dos métricas de la invariante 5 no
cambian**. Pruebas: `tests/test_spice.py` (con SPICE no se llama a Horizons, con `respx` sin rutas y
Horizons interceptado y contado; contraste coincidente y discrepante, también solo en la
elongación; sin SPICE, como antes; un día que SPICE no calcula va a la caché y después a Horizons);
campaña `spice.json`. **Residual:** un día sin efeméride de Horizons en caché va sin contraste
(`contrast = null`, dicho); la precarga lo llena, y la cobertura dice cuántos días tienen contraste
(`spice.contrast_days`).

**Riesgo residual:** el sistema depende de la cuota y la disponibilidad de NASA DONKI, OSDR, iSWA y SSCweb. Sin
enlace, la ventana de datos ambientales envejece indefinidamente; lo único que el software garantiza
es que se vea.

### H8 — Una marca de tiempo falsa desplaza el análisis

*Gravedad media.* Una lectura fechada en 2099 tapa las desviaciones de hoy.

**Controles:** la fecha de registro la pone el sistema, no quien llama; el reloj del ledger nunca
va hacia atrás y solo se iguala a un asiento que verifica por sí solo; las importaciones rechazan
instantes anteriores a 2000 y posteriores al presente más una tolerancia de 10 minutos
(`test_incredible_dates_are_reported_not_imported`).

**Riesgo residual:** todo esto confía en el reloj del sistema. Un reloj adelantado arrastra el
ledger por diseño hasta que el tiempo real lo alcanza (§3.1). Y el tope superior de fechas es de la
**importación**, no del alta directa: `POST /api/observations` con fecha 2099 responde 201 y la
lectura queda en el ledger. Es deliberado —una fecha futura puede ser un reloj mal puesto de un
wearable, y perder el dato sería peor—, y el Control 7 impide que mueva el "ahora" del estado: la
cuenta como ignorada por ser posterior a la referencia. Pero entra, y este documento tiene que
decirlo.

### H9 — La dosis de radiación se subestima

*Gravedad alta:* el límite de carrera de 600 mSv de [V1 4030] es un límite de salud, no un aviso.

**Controles:** el factor de calidad deja de ser 1; se prefiere la dosis equivalente medida cuando
existe y se estima con Q solo si no la hay (`test_measured_dose_equivalent_is_preferred_over_estimation`,
`test_unit_quality_factor_underestimates_by_the_mission_average`); verificado contra DosTel, el
resultado cae en el rango documentado de la ISS —`test_real_iss_dose_lands_in_the_documented_range`,
que está marcada `live` y por tanto **fuera de la suite por defecto**: consulta RadLab de verdad—;
el 100 % del límite de carrera entra solo en nivel crítico (`test_dose_at_career_limit_is_critical_on_its_own`).

**Riesgo residual:** **no se implementa el modelo NASA Q** que especifica [V1 4030], porque
requiere espectro LET que el sistema no recibe. La aproximación está declarada donde se usa y en
`nasa-std-3001-traceability.md`.

**Cerrado el 2026-09-24:** la dosis acumulada solo se leía de un parámetro de la consulta, así que un
dosímetro que registraba 600 mSv en el ledger no llegaba al límite. Ahora, si nadie la facilita, vale
la última dosis acumulada registrada, y `/api/status` → `dose.source` dice de dónde sale
(`test_a_recorded_career_dose_triggers_the_limit`).

**Cerrado el 2026-11-11 (Lógica 1):** `GET /api/radiation/dose` daba «0 mSv» con su factor de
calidad cuando la serie no tenía dos muestras que integrar, como si la tripulación no hubiera
recibido nada; ahora responde 404 sin cifra. Con dosis equivalente medida, el factor era NaN, que no
cabe en JSON, y la ruta caía con un 500 justo en el caso preferente; ahora es `null`, y la
advertencia ya no dice que se aplicó un factor medio cuando no se aplicó. Pedir `measured` como
modelo de factor de calidad (no lo es) da 422 en vez de un 500 (`tests/test_dosimetry.py`).

### H10 — El sistema se toma como prescripción

*Gravedad alta si ocurre.* Es el peligro que sostiene la clasificación Clase B: si se cruza esa
línea, la clase cambia.

**Controles:** límite declarado en `clinical-decision-rationale.md` y en la descripción de la API;
toda acción propuesta es ejecutable por la tripulación y reversible; ante una situación crítica se
ofrece **una** acción, no una lista (`test_critical_urgency_offers_one_action_not_a_list`); cada
recomendación cita su evidencia para que se pueda revisar.

**Riesgo residual:** ningún control técnico impide que alguien trate una recomendación como una
orden. Es un riesgo de uso, y se mitiga con formación y con el texto, no con código.

**Desde el 2026-09-24 el texto de las contramedidas también se comprueba con código**: el linter
`app/text_guard.py` pasa por todas las frases fijas que ve la tripulación
(`test_every_fixed_crew_text_passes_the_guard`), así que una frase nueva con dosis, diagnóstico o
certeza hace fallar la suite.

**Exportar a PDF (2026-10-01).** Un PDF del estado sale de la consola y se lee fuera de contexto.
Controles: lleva fecha y hora de generación, el aviso "Apoyo a la decisión, no prescripción" y
solo texto que ya da el backend (`app/export.py`); desde Tierra, el estado hasta el corte del
retardo, no el de a bordo (`until`).

**Anotaciones de dolor en PDF (2026-10-07).** El mismo riesgo, con dos añadidos: que la marca
«comentar con el médico de a bordo» se lea como una alerta o un diagnóstico, y que una nota
dictada se tome por texto comprobado. Controles (`app/export.py`, `pain_markdown`): el documento
se declara descriptivo («no prescripción ni diagnóstico»); la marca sale con la frase y la nota de
`app/pain/alarm.py` y rotulada «marca informativa, no una alerta»; cada nota lleva su origen
firmado, y la dictada dice que la transcribió un modelo local, que la revisó quien informa y que
EMMA no la ha corregido ni verificado; sin informes dice «sin anotaciones de dolor en el ledger»,
que no es «sin dolor»; cada informe cita su asiento del ledger. Mutantes:
`tests/mutants/export_pain.json`.

### H11 — El sistema deja de responder

*Gravedad media.* Sin vigilancia no hay aviso, y H1 se vuelve seguro en vez de probable.

**Controles:** tope de tamaño del cuerpo, **comprobado por trozos, sin llegar a tenerlo entero en
memoria** (413: `test_an_oversized_export_is_refused`); tope de número de registros, que actúa
después, ya con el cuerpo decodificado, y acota lo que llega al almacén; un tope de importaciones
**simultáneas**, porque el de tamaño no acotaba cuántas corren a la vez y el pool admite decenas;
defensa contra amplificación de entidades XML (`test_billion_laughs_is_refused_quickly`,
`test_entity_declarations_are_refused`); y un dato mal formado que termina en 422, nunca en 500.

**Riesgo residual:** no hay autenticación ni limitación de tasa. Verificar la cadena entera cuesta
segundos con decenas de miles de asientos, y ese coste crece con la misión. El "nunca en 500" es
una propiedad que se puede falsar y no demostrar: 21 sondas de una auditoría no lo falsaron, lo que
no es lo mismo.

### H12 — Datos de salud expuestos

*Gravedad media, y es información médica protegida.*

**Controles:** el almacén guarda solo lo necesario; la redacción borra de verdad del fichero
principal (`PRAGMA secure_delete`, sal por lectura) y deja lápida firmada.

**Riesgo residual:** **no hay cifrado en disco ni control de acceso.** El journal de SQLite conserva
lo redactado en bloques libres hasta que se reutilicen (§3.6), y no hay auditoría de lecturas: se
sabe quién escribió, no quién leyó.

### H13 — Una alerta real queda silenciada

*Gravedad alta.* Suprimir o inhibir una alerta (NASA-STD-3001 Vol 2, F.6.4) es la forma más directa
de volver H1 seguro: el sistema detecta, pero nadie se entera. Es también el camino por el que la
fatiga de alarma (H2) acaba apagando la vigilancia, que es lo que la invariante 5 de `CLAUDE.md`
prohíbe optimizar.

**Controles** (añadidos el 2026-09-23, `record-integrity.md` §3.8):

- **Nada desaparece.** La alerta silenciada sigue en la lista con su estado de anuncio, y la franja
  cuenta aparte las suprimidas y las inhibidas.
- **Límite de tiempo, siempre.** Suprimir, 12 h como mucho y **1 h si la alerta es crítica**.
  Inhibir, 7 días. Al vencer vuelve a anunciarse sin que nadie lo pida.
- **Un dominio en crítico no se puede inhibir**: la API lo rechaza (422) y la interfaz no lo ofrece.
- **Una escalada rompe el silencio.** Suprimir cubre un nivel; inhibir cubre hasta un nivel. Si el
  dominio sube, se anuncia.
- **Una inhibición reduce la vigilancia declarada** (F.6.2) aunque el dominio esté nominal, en
  amarillo, como decisión manual, con quién la pidió y por qué.
- **Motivo obligatorio y asiento firmado** en el ledger. Un silencio alterado en disco da 409: no
  puede ocultar una alerta.
- **Dos acciones independientes** en la interfaz y cinta de peligro en el botón que confirma
  (F.4.3.2).

Cada control tiene su prueba en `backend/tests/test_api.py` (bloque "F.6.4").

**Cerrados el 2026-09-24** (revisión adversaria de la tanda anterior; pruebas en el bloque "Revision
adversaria" de `test_api.py`):

- **Solo se reconoce o suprime una alerta que existe** en el estado sobre el que se decide (409):
  antes, un asiento sobre una alerta inexistente silenciaba de antemano la siguiente de ese nivel.
- **Solo cuentan las acciones firmadas por la consola.** Con la clave de un wearable no se reconoce
  ni se silencia nada, aunque el asiento esté bien firmado.
- **Los límites se aplican también al leer.** Un silencio que la API no habría aceptado —inhibir en
  crítico, suprimir una crítica más de una hora— no se respeta aunque esté firmado por la consola.
- **Un silencio caduca con el reloj**, no con la última lectura: si el sensor calla, una hora no dura
  para siempre.
- **Tierra no ve acciones posteriores a su corte**, aunque se decidieran sobre un estado anterior.
- **Una lectura fechada en el futuro no mueve el "ahora"**: queda apartada y declarada.
- **La ingesta pública no puede firmar como el sistema** (`simulator`, `crew-console`,
  `emma-audit`, `ultrasound`, `interpretation-local`): 422.

**Riesgo residual:** quien silencia es un nombre **declarado**, no una identidad autenticada (H3).
Nada impide suprimir otra vez al vencer, una y otra vez: el límite obliga a decidirlo de nuevo y lo
deja registrado, pero no lo impide. Y la supresión de una crítica durante una hora es una hora sin
aviso sobre la condición más grave.

---

### H14 — Un borrador del modelo de lenguaje engaña a quien lo firma

*Gravedad alta si ocurre.* Por eso su elemento es Clase C (`software-safety-classification.md` §2.1).

**Qué puede fallar:** el modelo inventa un valor, lo copia mal, insinúa un diagnóstico, propone un
tratamiento o afirma una certeza que los datos no sostienen; y quien revisa lo firma sin leerlo.

**Controles, en el orden en que actúan** (`app/interpret/`). Los marcados *(Polaris)* incorporan
código de Polaris desde el 2026-09-25 (`NOTICE`):
1. El modelo recibe solo hechos firmados del registro, nunca texto libre. Los hechos van entre
   delimitadores, con la instrucción de tratarlos como dato y no como orden, y un delimitador
   dentro de un dato se neutraliza *(Polaris, `local.py`)*: el nombre de quien mide o firma no
   puede dar instrucciones al modelo.
2. Salida estructurada con esquema; si no rellena las secciones, se bloquea.
3. **Toda cifra del borrador tiene que salir de los hechos**, comprobado sin ningún modelo.
4. **Todo signo que el borrador dé por presente o ausente tiene que estar anotado así**, con la
   negación resuelta ("no se detecta" es ausencia) y "no valorable" separado de "ausente"
   *(Polaris, `cotejo_invariante.py`)*. Es el fallo que la comprobación de cifras no ve: una
   ausencia inventada, sin una sola cifra, que tranquiliza a quien la lee.
5. Linter de dosis, diagnóstico (también insinuado), certeza, órdenes, acciones terapéuticas
   (tocar una dosis, parar o seguir un tratamiento, biopsiar, operar) y afirmaciones absolutas
   ("nunca", "siempre", "cero riesgo") *(Polaris, `honestidad_lint.py`, `decision_alto_riesgo.py`)*.
   La deliberación ("conviene", "es razonable") solo bloquea afirmada: como pregunta al médico
   es lo que el borrador debe contener. Casos fijos con gemelo que no debe bloquearse
   (`tests/data/text_guard_evals.json`).
6. **Comité de verificadores de casas distintas** *(Polaris)*: Qwen (Alibaba) y Gemma (Google),
   los dos locales; basta la objeción citada de uno para bloquear. Elegidos midiendo: con dos
   borradores correctos y uno con una afirmación inventada, Gemma no objetó nada correcto y cazó la
   inventada; Llama 3.1 8B objetó todas las frases y quedó fuera. Si falta un miembro, la función
   se declara no disponible.
7. Lo bloqueado no se muestra ni se guarda su texto: queda la constancia y los motivos.
8. Lo que pasa nace **sin validar**, rotulado así en amarillo, hasta que una persona lo acepta o lo
   rechaza. Una sola firma por borrador, en el ledger, **que cita la huella del texto leído**: si
   no coincide con el registrado, no hay firma *(Polaris, `salida.py`)*. Si el comentario de la
   firma registra una decisión clínica de alto riesgo, **hace falta una segunda firma de otra
   persona**, y el acta muestra si las dos discrepan *(Polaris, `decision_alto_riesgo.py`)*.
   Desde el 2026-10-13, si esa segunda firma cita un informe guardado, la cita tiene que
   localizarse en él y quien firma tiene que declarar haber leído la frase: si no, 422 y ningún
   asiento (`app/countersign_rule.py`, `record-integrity.md` §3.24). Desde el 2026-10-15 la
   segunda firma **tiene que** citar un informe guardado: una que cita otra fuente, o ninguna, no
   tiene frase que cotejar y se rechaza igual (422, sin asiento). Se cierra así el residual que
   se declaraba hasta entonces (bastaba no citar un informe para que la regla no se aplicara).
   **Residual declarado:** localizar la frase acredita que está en el informe, no que sostenga la
   decisión; y las contrafirmas admitidas antes sin informe siguen en la cadena, rotuladas al
   leer.
9. Un borrador no es una lectura: no entra en el análisis ni toca alertas.

Pruebas: `tests/test_interpret.py`, `test_cotejo.py` y `test_text_guard.py`, que ejecutan cada
caso que debe parar.

**Riesgo residual:** el linter es de patrones y una formulación suave se le escapa; el cotejo de
signos es por estudio y no por ventana (un "ausente" en una ventana deja pasar una ausencia dicha de
otra); un linter más estricto también rechaza más borradores correctos; el verificador falla como
falla el redactor; y ningún control impide firmar sin leer. La firma registra quién
asumió el borrador, no que lo entendiera. Ningún modelo concreto está validado.

**Comité medido y en un dosier (2026-10-04).** Medidos con `score_local` de Polaris sobre 25
casos escritos a mano (`app/committee_bench.py`, sin red, temperatura 0). Cada caso es un borrador
correcto o con uno de los cuatro fallos (cifra inventada, diagnóstico, tratamiento, certeza).

| Modelo | Acierto | ECE | Fallos detectados | Correctos respetados |
|---|---|---|---|---|
| gemma4 | 84 % | 0,10 | 100 % | 100 % |
| qwen3.5:9b | 88 % | 0,11 | 95 % (deja pasar una fecha inventada con 85 % de confianza) | 100 % |
| llama3.1:8b | 60 % | 0,20 | 100 % | 40 % (bloquea correctos) |

- **Por qué varios modelos:** el comité por defecto (`qwen3.6:35b-a3b` + `gemma4`) tiene uno que
  detecta todos los fallos del banco. `qwen3.5:9b` solo no basta.
- **Comité vigente (2026-11-14):** redactor `gemma4:e4b`, verificador único `gemma4:12b-it-qat`;
  los modelos anteriores ya no están instalados. `gemma4:e4b` dejó pasar un síntoma inventado y no
  verifica. Un solo verificador, de la misma casa que el redactor: riesgo residual de que comparta
  sus puntos ciegos; lo atenúan las barreras deterministas (cifras, lenguaje, hallazgos anotados).
- **El modelo grande no se midió:** `qwen3.6:35b-a3b` (23 GB) no lo carga el freno de memoria de
  Polaris con 17,5 GB libres.
- **Línea base** en `tests/data/evals/baseline.json`; la prueba `live` falla si un modelo baja.
- **Dosier:** las objeciones se juntan con `paso_consolidacion` de Polaris. Primero las que
  citan el borrador; las que no citan nada se marcan "sin fuente trazable".
- **Residual:** 25 casos son pocos y los ha escrito el equipo; mide la tarea, no la valida
  clínicamente.

### H15 — Los datos de salud salen de la nave a través del modelo

*Gravedad media; información médica protegida.*

**Controles:** el cliente solo admite una URL de loopback y rechaza cualquier otra al construirse
(`test_a_remote_model_is_refused`). El modelo recibe hechos del registro, no la imagen ni
identificadores del tripulante.

**Riesgo residual:** EMMA no controla qué hace el servidor local con lo que recibe; elegirlo y
configurarlo sin salida a red es responsabilidad de quien lo instala.

**Una sola salida a internet (2026-10-01).** Toda llamada HTTP de EMMA pasa por
`core/egress.py`:
- **lista blanca** de host por propósito: un host fuera de lista falla ruidosamente
  (`EgressNotAllowed`), no en silencio;
- **modo sin red y modo seguro** comprobados en un solo sitio;
- **`borde.egress_check` de Polaris** sobre la URL y la consulta (sin la clave de API), con
  destino externo: un dato de salud o un canario en lo que sale se bloquea;
- **traza de metadatos** (hora, host, propósito, veredicto; nunca la consulta ni el cuerpo) en
  `cache/egress/`;
- reintentos con la política de Polaris `_net.with_retries`, con tope total de 10 s (`deadline`).
  Sin el tope, un 429 de DONKI con `Retry-After` de horas hacía esperar 4 min a cada estado de
  salud (H11): se falla ya y el cliente usa su caché con la edad declarada
  (`test_a_long_retry_after_fails_at_once_instead_of_waiting`).

El propósito `osdr-data` (2026-11-11, `evidence/osdr_data.py`) solo lleva el identificador público de un estudio (OSD-288…) con el User-Agent genérico de httpx; `test_the_request_carries_only_the_public_study_identifier` comprueba que ni un identificador de tripulante, ni una ruta local, ni el nombre del proyecto viajan en la petición.

El propósito `spice-kernels` (2026-11-11, `scripts/fetch_spice_kernels.py`) solo lo usa el guion que descarga los núcleos SPICE públicos de NAIF: lleva la URL del fichero y nada más, con el User-Agent genérico de httpx; `test_the_download_carries_only_the_public_url` inspecciona la petición (sin consulta, sin cuerpo, sin cookies ni credenciales, y sin el nombre del usuario, de la tripulación ni del proyecto). La aplicación calcula con los núcleos sin red.

Los propósitos `planner-quotes` (`zenquotes.io`) y `planner-onthisday` (`en.wikipedia.org`, `es.wikipedia.org`) (2026-11-12) son los de Marplanner (`marplanner/`, decisión del usuario: «datos que entran, sí; nada que salga»). Marplanner es Node y no sale por su cuenta: `planner-bridge/egress.mjs` desvía su `fetch` a `POST /api/planner/fetch`, que llama a `egress.get`; su `undici` (calendarios ICS, UniFi) solo llega a loopback, y cualquier otro host es un error. Solo GET sin cuerpo; la cita no lleva parámetros y las efemérides solo el mes, el día y el idioma. Open-Meteo (coordenadas del hogar) y UniFi (clave y control de la red) no tienen propósito: no salen. Pruebas: `tests/test_planner_ledger.py` (sin red no sale, host ajeno al propósito 403) y `planner-bridge/bridge.test.mjs`.

El propósito `models-pack` (2026-11-15, `app/models_download.py`, «Descargar modelos») baja el paquete de modelos publicado en GitHub (`github.com` y sus almacenes `objects.githubusercontent.com` y `release-assets.githubusercontent.com`, adonde redirige cada fichero) solo cuando la persona lo pide desde «Modelos de IA», y nunca en modo sin red ni con el modo seguro. Solo sale la URL de cada fichero. Lo bajado se comprueba dos veces: cada trozo con el tamaño y el SHA-256 de `emma-modelos-partes.json`, y cada fichero con los de `MANIFIESTO.json`; solo se escriben los ficheros que el manifiesto nombra para esa pieza (una ruta ajena del `tar` invalida la pieza, sin escribir nada fuera de su carpeta), y la pieza solo sustituye a la instalada cuando todo casa. **Residual:** el índice se fía de HTTPS y de la cuenta de GitHub que lo publica: no va firmado. Pruebas: `tests/test_models_download.py` (sin red no sale, trozo alterado, ruta ajena, reanudación, carpeta ajena).

Las efemérides (`astroquery`, que usa `requests`) se autorizan antes de llamar. **Modo seguro**
(asiento `safe-mode`, `record-integrity.md` §3.20): corta toda salida y deja el modelo local.
Pruebas: `tests/test_egress.py`, `tests/test_safe_mode.py`; mutantes `egress.json`,
`safe_mode.json`, `storage_safe_mode.json`. **Residual:** la puerta vigila el código de EMMA; una
dependencia que abra su propio socket no pasa por ella. Por eso la suite corre con el modo sin red
forzado (invariante 3) y una prueba de la API falla si algo sale.

### H16 — Un informe de dolor registra una zona, un lado o una intensidad que no son los referidos

*Gravedad media: lleva a vigilar, o a dejar de vigilar, el sitio equivocado.* Añadido el
2026-09-25 con el mapa corporal (`app/pain/`, `frontend/src/pain/`).

**Qué puede fallar:** el mapa invierte izquierda y derecha (el lado del tripulante frente al de quien
mira la pantalla); un clic al girar el cuerpo marca una zona sin querer; una zona queda con una
intensidad que nadie dijo; o la cifra que analiza el motor no es la del informe.

**Controles:**
1. Lateralidad del tripulante en el catálogo y en el modelo 3D, con prueba de que cada zona
   izquierda cae en su lado y de que izquierda y derecha son espejo exacto (`bodyModel.test.ts`), y
   prueba de que las zonas del cuerpo son exactamente las del catálogo
   (`test_the_body_model_draws_exactly_the_declared_zones`).
2. Soltar el puntero tras arrastrar no marca nada (`isClick`); el nombre de cada zona marcada se
   lee en el formulario antes de enviar, y un segundo toque la quita.
3. **Sin intensidad por defecto:** el formulario no se envía hasta que cada zona tiene la suya, y
   el backend rechaza una zona marcada con 0. "Sin dolor" es un informe explícito; no informar no es
   un cero.
4. La intensidad que entra en el análisis es el máximo del informe, escrita en el mismo `commit`
   que el informe y comprobada por el almacén; no entra por la ingesta genérica ni se enmienda
   (`record-integrity.md` §3.11).

**Riesgo residual:** el autoinforme es subjetivo y la escala 0-10 no se compara entre personas; la
línea base personal lo acota, pero **la intensidad no está validada como señal de alerta** (MMASH no
tiene dolor: `external-validation.md`). Sin límite crítico, no alerta sin línea base. Quien informa
se declara y no se autentica (H3).

**Marca "comentar con el médico de a bordo"** (`app/pain/alarm.py`, desde el 2026-09-25; lista
conservadora de Polaris `sintomas.py`): opresión o dolor en el pecho, dolor intenso de cabeza o de
espalda (7-10, Serlin 1995) y hormigueo en un solo lado. **No es una alerta** ni entra en el riesgo:
no hay datos para medir su falsa alarma y su sensibilidad (invariante 5). Su propio riesgo residual:
callarse ante un dolor que merecía atención y que no está en la lista, o marcar de más. Ninguno
silencia ni dispara una alerta, porque no está conectada a ellas.

**Nota dictada (2026-10-01).** Una transcripción automática puede cambiar lo que el tripulante
dijo ("no me duele" → "me duele"). Controles: vuelve como borrador, se muestra en amarillo con
triángulo pidiendo que se lea y corrija, no se firma sin que la persona envíe el informe, y el
asiento marca `dictada-revisada`. La nota no entra en el análisis: la intensidad y las zonas son
las que la persona marca. **Residual:** sin una grabación de voz real, la calidad de la
transcripción en castellano no está medida aquí; la prueba `live` solo comprueba la cadena.

### H17 — El texto de un informe escaneado se lee mal y alguien lo toma por bueno

*Gravedad media: una cifra mal leída de una analítica en papel.* Añadido el 2026-09-25 con el OCR
local de informes (`app/reports/`, de Polaris `ocr_informes.py`).

**Qué puede fallar:** tesseract confunde un 1 con un 7 o se come una coma decimal, y quien lee el
texto no mira el original.

**Controles:**
1. Cada página lleva la confianza media del OCR; por debajo de 60/100 se marca en amarillo con el
   aviso de no leer cifras sin mirar el original.
2. El original, firmado y con su hash comprobado en cada entrega, se muestra siempre al lado del
   texto.
3. El texto no entra en el análisis, ni en alertas, ni en el borrador del modelo: nada automático
   actúa sobre él.
4. Un PDF que ya trae texto no se OCR-iza: se usa el texto que tiene.
5. **El texto que se firma, se muestra y viaja a Tierra está des-identificado** (`reports/deid.py`,
   de Polaris `deid.py`/`borde.py`): correo, teléfono, DNI/NIE, número de historia, tarjeta
   sanitaria, fecha de nacimiento, domicilio y nombres con etiqueta o tratamiento. Tras
   enmascarar, el detector vuelve a mirar el resultado, también normalizado (tildes falsas,
   caracteres invisibles); si aún ve algo, el texto se retiene y solo queda el original.
   Desde el 2026-10-01 lo hace el original de Polaris (`e3b588d`), que también enmascara las
   fechas de las analíticas y quita las tildes, con una regla de EMMA encima para nombres con
   tratamiento en mitad de una frase.
   **Familiar nombrado (2026-10-07):** otra regla de EMMA encima tapa el nombre que sigue a un
   parentesco ("su hermana Lucía Fernández" → "su hermana [REDACTADO]") y deja el parentesco, que
   es dato clínico. Con determinante delante basta un nombre de pila; sin él ("Hermano: …") hacen
   falta nombre y apellido, porque así se escriben los antecedentes ("Madre: Asma"). Una lista
   de enfermedades, epónimos y fármacos corta el nombre; un estado ("Fallecido") o una palabra
   con sufijo médico en primer lugar no es un nombre; un parentesco dentro del nombre de un centro
   o de una calle no cuenta; "mujer", "mamá" y "papá" solo cuentan con posesivo (son antes el
   sexo de la paciente o "la Mama Derecha"), y lo que acaba en dos puntos es la etiqueta del
   campo siguiente. Si tras tapar la regla aún ve un familiar nombrado, el texto se retiene.
   **Nombre delante del parentesco (2026-10-20):** una segunda pasada de la misma regla tapa el
   nombre en aposición ("con Rosa Beltrán, su cuñada" → "con [REDACTADO], su cuñada"; también
   "Rosa Beltrán (su madre)" y "Rosa Beltrán, cuñada del paciente"). Solo si el parentesco está
   anclado a la persona —posesivo o "del paciente" detrás—; ninguna palabra del nombre en la lista
   clínica, y la primera, ni estado ni sufijo médico ni un centro o una vía; lo que abre la frase
   ("Hoy", "Además") se quita por la izquierda. Nombre y apellido bastan; un nombre de pila suelto,
   solo en mitad de la frase tras "con", "a", "por", "y (de)" o "acompañado de". La revalidación
   que retiene el texto mira las dos pasadas; como usa la misma regla, caza restos y no lo que la
   regla no ve.
6. **Reglas de EMMA antes del original** (2026-10-01): IBAN con dígito de control (mod-97),
   número de tarjeta con Luhn, pasaporte con su etiqueta y fecha ISO con hora. Las cifras largas
   que no pasan su dígito de control no se tapan (`tests/test_reports.py`).
7. **Capa NER** (`deid_ner` de Polaris, modelo del BSC entrenado con historias clínicas): se usa
   solo con la marca de pesos comprobados de `scripts/install_deid_ner.py`; pedida y caída,
   retiene el texto. **Hoy no está activa**: el modelo no es público (Hugging Face responde 401,
   hace falta una cuenta que acepte sus condiciones y un token).

**Medida** (2026-10-01, `deid_eval` de Polaris sobre `backend/tests/data/deid_corpus/`: 10
informes inventados, 39 identificadores según el recuento de entonces —ver la corrección del
2026-10-07 más abajo—, anotados en formato brat; cuenta como escapado el valor
que aparece en la salida, sin distinguir tildes ni mayúsculas):

| Capa | Tapados | Escapan |
|---|---|---|
| Patrones de Polaris solos | 26 de 39 | IBAN, tarjetas y pasaporte (5 de 5), 2 de 3 nombres de personal sanitario, 1 fecha ISO, 1 familiar, 1 nombre de paciente, la tarjeta sanitaria |
| EMMA (Polaris + reglas de EMMA) | 35 de 39 | "Titular: <nombre>" (etiqueta que no reconoce), "Tarjeta sanitaria: <código>", un familiar nombrado sin etiqueta y restos parciales de un correo |
| EMMA + etiquetas "Titular" y "Tarjeta sanitaria" (2026-10-01, decisión del usuario) | ver abajo | un familiar nombrado sin etiqueta |
| EMMA + regla de parentesco (2026-10-07) | ver abajo | el familiar cuyo nombre va delante del parentesco ("con Rosa Beltrán, su cuñada") |
| EMMA + nombre delante del parentesco (2026-10-20) | ver abajo | un nombre de pila suelto delante del parentesco al principio de la frase ("Marta, su sobrina, llamó"; límite declarado) |
| Con capa NER | sin medir | modelo no disponible (no se usa, decisión del usuario) |

Tras la regla de etiquetas se mide con la métrica de fugas del propio banco (`deid_eval.fugas`:
el texto normalizado de cada identificador largo, buscado en la salida real): **1 de 23 se
escapa**, el familiar sin etiqueta. Sobre los 34 tramos que carga `cargar_brat`, 33 desaparecen
de la salida. La prueba `backend/tests/test_deid_corpus.py` fija esa cifra: si escapa algo más,
falla. Las dos filas anteriores se midieron con el recuento del 2026-10-01 (39 identificadores) y
no son comparables uno a uno con esta.

**Corrección del 2026-10-07: "26 de 39" y "35 de 39" no se pueden reproducir.** El corpus tiene 34
identificadores anotados, no 39, y no queda registro de cómo se contaron aquellos 39 (el corpus
entró en el repositorio ya con 34). Las dos primeras filas de la tabla de arriba se dejan como
historia de la decisión, no como medida vigente. "1 de 23" sí se reproduce. La medida vigente es
la de abajo.

**Recall por tipo de entidad** (`deid_eval.puntuar` de Polaris, llamado tal cual por
`backend/scripts/deid_report.py`; los suelos los fija `backend/tests/test_deid_corpus.py`, que
también falla si esta tabla deja de coincidir con lo medido). Una entidad cuenta como tapada solo
si no queda a la vista ninguno de sus caracteres; "tocada", si se tapa al menos uno.

<!-- deid-report:inicio (lo escribe backend/scripts/deid_report.py --write) -->
Medido el 2026-10-20.

| Tipo de entidad (etiqueta del corpus) | Anotadas | Tapadas enteras, EMMA | Tocadas, EMMA | Tapadas enteras, solo Polaris |
|---|---|---|---|---|
| `FAMILIARES_SUJETO_ASISTENCIA` | 11 | 10 de 11 (91 %) | 10 | 0 de 11 (0 %) |
| `NOMBRE_SUJETO_ASISTENCIA` | 7 | 7 de 7 (100 %) | 7 | 6 de 7 (86 %) |
| `ID_SUJETO_ASISTENCIA` | 6 | 6 de 6 (100 %) | 6 | 6 de 6 (100 %) |
| `FECHAS` | 6 | 6 de 6 (100 %) | 6 | 5 de 6 (83 %) |
| `OTRO_NUMERO_IDENTIF` | 5 | 5 de 5 (100 %) | 5 | 0 de 5 (0 %) |
| `NOMBRE_PERSONAL_SANITARIO` | 3 | 3 de 3 (100 %) | 3 | 1 de 3 (33 %) |
| `NUMERO_TELEFONO` | 2 | 2 de 2 (100 %) | 2 | 2 de 2 (100 %) |
| `CORREO_ELECTRONICO` | 2 | 2 de 2 (100 %) | 2 | 2 de 2 (100 %) |
| `CALLE` | 2 | 2 de 2 (100 %) | 2 | 2 de 2 (100 %) |
| `ID_ASEGURAMIENTO` | 1 | 1 de 1 (100 %) | 1 | 0 de 1 (0 %) |
| **Total** | 45 | **44 de 45 (98 %)** | 44 | 24 de 45 (53 %) |

Precisión por carácter (cuánto de lo tapado era un identificador anotado): 0.924 con EMMA, 0.890 solo Polaris.
Fugas literales en la salida real (`deid_eval.fugas`): 1 de 34.
Informes: 12; retenidos enteros por no verificar: 0.
<!-- deid-report:fin -->

**Antes y después de la regla de parentesco (2026-10-07).** Sobre los 10 informes y 34
identificadores que había: familiares tapados enteros, de 0 de 2 a 2 de 2; total, de 32 de 34 a
34 de 34; fugas literales, de 1 de 23 a 0 de 23. Como esos dos casos son los que motivaron la
regla, se añadió `informe11` (antecedentes familiares: cinco familiares nombrados y, a su lado,
"Madre con Diabetes Mellitus", "Padre fallecido de Infarto" y "enfermedad de Parkinson, en
tratamiento con Levodopa"). Sobre los 11 informes y 39 identificadores, sin la regla: familiares
0 de 7, total 32 de 39, fugas 6 de 28; con ella, la tabla de arriba. Lo clínico de `informe11`
sale intacto (`test_the_family_history_keeps_its_clinical_content`).

**Antes y después del nombre delante del parentesco (2026-10-20).** Sobre los 11 informes y 39
identificadores de entonces: familiares tapados enteros, de 6 de 7 a 7 de 7; total, de 38 de 39 a
39 de 39; fugas literales, de 1 de 28 a 0 de 28; precisión por carácter, de 0,916 a 0,918 (no
tapa nada de más en el corpus). Como el caso de `informe11` es el que motivó la regla, se añadió
`informe12` (nota de evolución: cuatro familiares nombrados delante de su parentesco y, en la
misma posición, lo que no es un nombre: "Además, su madre…", "Hipertensión Arterial, su padre
también", "Enfermedad de Crohn, su tío materno", "Ingresó en el Hospital Clínico, su madre
también"). Sobre los 12 informes y 45 identificadores, sin la segunda pasada: familiares 6 de
11, total 40 de 45, fugas 5 de 34, precisión 0,919; con ella, la tabla de arriba. El familiar que
queda es "Marta, su sobrina, llamó…": un nombre de pila suelto al principio de la frase, límite
declarado. Lo clínico de `informe12` sale intacto
(`test_names_before_the_kinship_go_and_clinical_appositions_stay`).

Qué añade esta medida a la de fugas: en "Persona de contacto: su padre, Tomás Pérez" Polaris tapa
solo el apellido (patrón `nombre_titular`) y el nombre de pila quedaba a la vista.
`deid_eval.fugas` no lo contaba, porque busca el texto entero; `puntuar` sí. Eran **dos**
familiares los que no quedaban tapados, no uno; la regla de parentesco tapa los dos.

Qué deja pasar la regla de parentesco, medido o sabido:
- ~~**El nombre delante del parentesco** ("con Rosa Beltrán, su cuñada")~~: lo tapa desde el
  2026-10-20 la segunda pasada. De él queda: un nombre de pila suelto al principio de la frase o
  tras dos puntos ("Marta, su sobrina, llamó": es el familiar que queda en la tabla, 10 de 11, y
  la fuga que queda, 1 de 34; una mayúscula sola ahí puede ser "Además, su madre…"); la aposición
  sin posesivo ni "del paciente" ("Rosa Beltrán, cuñada"); una profesión, que no es un
  parentesco ("Ana López, su médica": el personal sanitario se tapa con su tratamiento, "Dra.");
  y un nombre junto a una palabra de la lista clínica, que descarta el tramo entero ("Ana Graves,
  su madre"; "Parkinson y Rosa Beltrán, su cuñada"). Lo fija
  `test_a_name_before_its_kinship_that_needs_ner_is_a_declared_limit`.
- Un nombre de pila suelto sin determinante ("Hermano Juan operado"), los nombres en mayúsculas
  sostenidas ("MADRE: CARMEN RUIZ": ahí van también HTA, IAM, EPOC), "mujer", "mamá" y "papá"
  sin posesivo, un nombre de pila que acabe en sufijo médico (solo se exceptúan Paloma y Eufemia)
  y los parentescos que no están en la lista.
- **De más:** una palabra clínica que no esté en la lista ni acabe en un sufijo médico, escrita
  con mayúscula justo detrás de un parentesco con determinante ("su madre Vitíligo"), se taparía;
  y detrás de un nombre de pila solo corta la lista, no los sufijos (hay apellidos que acaban
  así: Coloma). Delante del parentesco, un lugar tras "a" ("trasladado a Bilbao, su hermano…"),
  dos palabras con mayúscula que no estén en ninguna lista ("Plan Terapéutico, su madre…") o una
  palabra que abre la frase y no está en la lista de inicios se taparían, esta última junto con
  el nombre. La lista es finita; las pruebas fijan los casos de `tests/test_reports.py`, no todos.

Qué **no** mide:
- El corpus son 12 informes inventados para esta prueba, con 45 identificadores; hay tipos con
  una o dos entidades, y ahí un 100 % no es una tasa. Las reglas de etiquetas y la de parentesco
  de EMMA se añadieron tras medir con este mismo corpus, e `informe11` e `informe12` los escribió
  quien escribió la regla: no son una muestra independiente de ella.
- No valida la des-identificación de historias clínicas reales ni de informes escaneados con
  errores de OCR (un DNI mal leído no casa con su patrón).
- Los tramos tapados se deducen comparando el texto antes y después de cada capa
  (`reports/deid.py`, `masked_spans`): con varias marcas seguidas la frontera entre dos tramos
  vecinos puede correrse. La prueba comprueba que, aplicados al original, dan la salida real.
- La precisión por carácter cuenta como "de más" lo tapado que no está anotado: el tratamiento
  ("Dra.") delante de un nombre, la palabra "contacto" (término vetado de Polaris), la etiqueta
  "Titular" (el patrón `nombre_titular` de Polaris la tapa después de la regla de EMMA) y la "y"
  entre dos familiares ("sus hijos Marcos y Julia" es un solo tramo).
- La capa NER sigue sin medirse (no se usa).

**Riesgo residual:** una página con buena confianza media puede tener una cifra mal leída; el
control último es leer el original. La des-identificación es por patrones y porosa: un nombre sin
etiqueta, tratamiento ni parentesco al lado se escapa (la medida lo confirma: un nombre de pila
suelto delante de su parentesco al principio de la frase), y revalidar con el mismo detector caza
restos, no demuestra anonimato. Lo que falta tapar (nombres sueltos sin etiqueta: la capa NER no se
usa) está en `docs/polaris-divergencias.md` §12. El original escaneado conserva todo:
se guarda en local y se puede redactar.

**Cita cotejada e incongruencias (2026-10-04).**
- **Cita cotejada:** una firma que se apoya en un informe escaneado (`informe:<n>`) se coteja de
  verdad. El fragmento citado tiene que estar en el texto de ese informe (Polaris
  `fuente_clinica`), y un informe de otro tripulante no vale. Acredita procedencia, no fidelidad.
- **Incongruencias:** dos analíticas de la misma extracción con más de un 5 % de diferencia en
  el mismo analito se avisan (Polaris `incongruencias_caso`). Su comparación original daba por
  distinto un redondeo entre laboratorios (92 frente a 92,4).
- **Residual:** su lector de fechas solo reconoce los formatos de los laboratorios de su autora.
  Un informe sin fecha legible no se cruza, y se cuenta aparte.

**Dos cotejos del mismo informe a la vez (2026-10-08).**
- **Qué fallaba:** la copia del informe en la bóveda se escribía antes de tomar el cerrojo. Dos
  cotejos del mismo informe a la vez (firma y contrafirma, o dos consolas) se pisaban: uno
  truncaba el fichero mientras el otro lo leía, y este salía con «vacía», «fragmento ausente» o
  una huella que no era la del informe; en la contrafirma, un 409 o un `no_localizada` sin causa
  en el asiento. Reproducido con el código anterior (`docs/polaris-divergencias.md` §18).
- **Control:** el cotejo entero y la lectura de la frase literal van bajo un mismo cerrojo
  (`app/evidence/vault.py`), y la copia se escribe a un lado y se sustituye de golpe
  (`os.replace`): si el proceso muere a media escritura queda la copia anterior entera. La huella
  de la fuente no cambia. Pruebas en `tests/test_vault.py` y `tests/test_source_quote.py`;
  campaña `tests/mutants/vault.json`.
- **Residual:** el cerrojo es de un proceso. Dos procesos de EMMA sobre el mismo estado no están
  cubiertos.

### H18 — La segmentación automática de un volumen marca mal una lesión o una estructura

*Gravedad alta si orienta una decisión.* Añadido el 2026-09-26 con el visor 3D de Polaris
(`app/volumes/`). Elemento Clase C.

**Qué puede fallar:** el modelo no marca una lesión (falso negativo), marca algo que no lo es
(falso positivo), mide mal un diámetro, confunde izquierda y derecha, o la escala sale mal de un
afín oblicuo.

**Controles:**
1. Todo lo que sale del modelo se rotula "segmentación automática sin validar" y "lesión
   candidata", en amarillo con triángulo; nunca es un hallazgo.
2. No entra en `observations`, ni en el análisis, ni en alertas: segregado como el borrador del
   modelo de lenguaje (`software-safety-classification.md` §2.1).
3. Las lesiones de menos de 10 mm se marcan como de fiabilidad baja (Polaris: la sensibilidad
   publicada cae mucho por debajo).
4. El espaciado sale de la norma de cada columna del afín, no de su diagonal: con un afín oblicuo
   la diagonal daba milímetros falsos (probado).
5. Convención radiológica y rótulos de orientación visibles en los cortes.
6. Dos modelos: se muestra qué fracción de cada lesión marca también el segundo (`liver_vessels`,
   clase tumor). Coincidir no valida; discrepar es una bandera.
7. La comparación entre dos estudios se niega si no salen del mismo preset y segmentador.
8. Los ficheros del visor van firmados por su hash y se comprueban en cada entrega.

**Riesgo residual:** ningún modelo está validado para esta población en EMMA; la medida de Dice
frente a la segmentación experta del dataset (`-m external`) dice cuánto coincide, no si detecta
lo que importa. Decide una persona con el volumen delante.

**Esqueleto y memoria (2026-10-02).** El preset `esqueleto` (Polaris) segmenta 60 huesos con la
tarea `total`, que pide memoria según el tamaño del TAC; a medias, una segmentación cortada no es
un resultado. EMMA estima lo que necesita (6,0 GB fijos más 0,16 GB por millón de vóxeles a 1,5 mm,
+25 %, medido con s0013 y con las muestras de la app) y no la lanza sin esa memoria libre: lo dice y
pide cerrar programas. El primer modelo (0,6 GB por millón, proporcional) se quedaba corto con los
TAC pequeños y la guarda los cortaba siempre; corregido el 2026-10-04, con prueba de que la
estimación cubre cada pico medido. **Esqueleto incompleto (2026-10-06):** limitada a los huesos
con `--roi_subset`, la segmentación local del ejemplo de cuerpo entero salía sin cuello, sin
columna lumbar y sin pelvis (40 de 60 huesos), sin ningún aviso, y tapaba en el visor a la
correcta. Ahora corre la tarea entera (60 de 60); tarda unos 4 minutos en vez de 1. Como el resto de
segmentaciones, sale como "segmentación automática sin validar".

**Control de la cadena vertebral (2026-10-07).** Lo que faltó aquel día fue el aviso: un esqueleto
sin media columna se dibuja igual de bien que uno entero. Cada segmentación del esqueleto lleva
ahora el control de Polaris (`visor3d._revisa_cadena` y `_orden_columna`, llamados tal cual desde
`app/volumes/spine.py`): niveles presentes, huecos en mitad de la cadena, orden craneocaudal,
niveles reconocidos a medias y huesos del preset sin vóxeles; se enseña junto al visor. Para
Polaris un nivel que falta por un extremo no es un hueco, y aquel caso era justo ese, así que EMMA
añade una regla geométrica propia: si más allá del último nivel presente el volumen sigue al menos
paso y medio entre vértebras, pide atención; si el volumen acaba ahí, es dato ausente (casi ningún
TAC cubre la columna entera, y avisar siempre no avisa de nada). Las nuevas lo llevan en su resumen
firmado, y también el ejemplo `esqueleto-4` desde que se regeneró el 2026-10-08; para las ya
guardadas se calcula al servir desde su zip firmado, sin tocar el ledger. Es descriptivo: no
bloquea ni borra, no entra en el análisis ni en una alerta, y si el propio control falla se dice y
la segmentación sigue. **Riesgo residual:** la regla de los
extremos está probada con el caso real y con recortes del ejemplo real, no con más estudios; un
nivel perdido justo en el borde del volumen sale como dato ausente y no como atención; y el
control no dice si un hueso presente está bien segmentado. Pruebas en `tests/test_volumes.py` y
campaña `tests/mutants/volumes_spine.json`.

**El control, leído de una consola compartida (2026-10-08).** `_revisa_cadena` no devuelve nada:
EMMA lee el control de lo que imprime. La consola es de todo el proceso, y la revisión de la
cadena, la exportación a PDF y la reindexación de la biblioteca la capturaban cada una bajo su
propio cerrojo. Cruzadas, el texto de Polaris caía en el búfer de otra captura y el control salía
«no revisada», o sin los niveles reconocidos a medias, en el resumen firmado de la segmentación;
o la consola del proceso no volvía. **Control:** una sola captura y un solo cerrojo
(`app/polaris/console.py`, `captured()`), y una prueba que impide a cualquier módulo de `app/`
redirigir la consola por su cuenta (`tests/test_polaris_console.py`; campañas
`tests/mutants/polaris_console.json`, `polaris_console_kb.json`, `polaris_console_export.json` y
`polaris_console_spine.json`). El fallo no se reprodujo con el código anterior en el servidor: lo
demuestran los mutantes que devuelven a cada adaptador su cerrojo. Lo que cuesta: mientras la
biblioteca reindexa, exportar un PDF y revisar una cadena esperan. **Riesgo residual:** un hilo
que escriba por consola sin pasar por `captured()` mientras otro captura (una herramienta de
Polaris llamada sin captura, o `logging.lastResort`) deja su texto en el búfer de quien captura.

**El esqueleto del propio TAC en el modo anatómico (2026-10-07).** Con una segmentación del
esqueleto vigente, la vista anterior, el centroide de cada hueso y el dolor referido salen de ella
(`app/volumes/skeleton_view.py`, con `visor3d.proyecta_anterior` de Polaris llamada tal cual); sin
ella se enseña el esqueleto de referencia. Peligros nuevos y su control:
- *Una figura en espejo o del revés, que no se nota mirándola* (un esqueleto es casi simétrico).
  La función de Polaris dibuja por índices de la rejilla: con la rejilla RAS en la que EMMA guarda
  los volúmenes sale cabeza abajo (medido con `esqueleto-4`). El mapa se reorienta según su afín
  antes de llamarla, se comprueba el sentido en la extensión que la propia función devuelve, y se
  contrastan los nombres de los pares izquierdo/derecho y el orden de la columna con el afín; si
  algo no cuadra, o la rejilla es oblicua, no se enseña y se dice por qué. Probado con el mismo
  cuerpo guardado en seis rejillas volteadas o permutadas: sale la misma imagen.
- *Tomar un cuerpo ajeno por el propio.* La respuesta dice cuál es (`source`), de qué asientos
  del ledger sale y con qué fecha, y la interfaz enseña ese texto tal cual; un TAC de ejemplo
  (paciente de un dataset, firmado como simulado) se rotula como tal y lleva su cita CC BY. Las
  marcas de dolor solo se pintan sobre la figura en la que se colocaron (misma fuente y asiento).
- *Un hueso inventado o un punto donde no hay hueso.* No se llama a la reconstrucción de Polaris
  (unir fragmentos, simetrizar costillas, puentear la columna, rellenar huecos). El hueso sin
  vóxeles no se dibuja y se lista; el que llega al borde craneocaudal del estudio se declara
  cortado (su punto es el del trozo) y no ancla el ajuste del dolor.
- *Dolor colocado donde el estudio no llega.* La zona cuyo hueso de anclaje no está, o que el
  ajuste deja fuera de la imagen, se declara «fuera del estudio»; sin tres posiciones distintas de
  las anclas por eje no se alinea; un ajuste que le da la vuelta al cuerpo no coloca nada.
- *La zona anclada lejos de su propio hueso* (2026-10-20). El ajuste estira el dibujo y en
  `esqueleto-4` dejaba la zona lumbar a 75 mm de L3. Con el modo DIRECTO de Polaris la zona
  anclada a un hueso que la figura trae entero se pinta en el centroide de ese hueso (en la de
  referencia y en la del TAC), y la respuesta dice de cada zona cómo se colocó (`placed_on`). La
  de un hueso cortado no va al centroide de su trozo: sigue con el ajuste o fuera del estudio. El
  ajuste sigue decidiendo si se pinta algo, con el mismo umbral.
- *Mostrar una figura de un binario que ya no es el firmado.* El zip se pide al ledger en cada
  entrega, que lo comprueba contra su huella; la figura en memoria no se sirve si eso falla. Nada
  se escribe en el ledger: se calcula al servir.
Es imagen de referencia previa al vuelo o de Tierra (hoy no vuela ningún TAC) de una segmentación
automática sin validar, y lo dice junto a la figura; no entra en el análisis ni en una alerta.
**Riesgo residual:** la comprobación del espejo no es independiente del afín (Polaris usa hígado y
bazo, que el mapa publicado no trae): si el NIfTI de origen declara mal su orientación, EMMA no lo
detecta. El corte de un hueso solo se mide en el eje craneocaudal (un brazo fuera del campo por
un lado no se declara). El umbral del ajuste del dolor es geométrico y está medido en un único
TAC real: en `esqueleto-4`, con 6 anclas, el error medio es de 44 mm y el peor de 75 mm, dentro de
la tolerancia (80 mm) pero cerca de ella (margen del peor, 4,9 mm, vigilado por
`test_on_the_real_sample_ct_the_worst_anchor_stays_under_the_threshold`). Desde el modo DIRECTO
ese error ya no es el de las zonas ancladas, que van sobre su hueso, sino el de las que coloca el
ajuste (sin hueso o con el suyo cortado). En la figura de referencia el peor (101 px, 79 mm) se
queda a menos de 1 px del umbral (102,3 px, 80 mm); con el cuerpo anterior del mapa de dolor,
cuya zona anclada más baja eran pelvis y cadera (0,14 m), el umbral era de 89,5 px (70 mm) y el
peor lo pasaba. El umbral mira la media (63 px): ni antes ni ahora decide el peor. Desde el
cuerpo de 2026-11-09 la más baja es el cuello (0,16 m), y las alturas de `pain_points.json` las
comprueba `frontend/src/pain/bodyModel.test.ts` contra las mallas. Un hueso cortado por un lado,
que no se declara, pone su zona en el centroide de su trozo. Pruebas en
`tests/test_skeleton_view.py` y `tests/test_pain_on_skeleton.py`; campañas
`tests/mutants/skeleton_view.json`, `anatomy_skeleton.json`, `pain_on_skeleton.json` y
`pain_on_skeleton_direct.json`.

**Techo de memoria (2026-10-04).** TotalSegmentator (preset esqueleto) y Whisper corren con
`guarda_memoria.corre` de Polaris, que vigila el árbol de procesos entero y lo corta a tiempo; en
Windows con lecturas propias (`app/polaris/compat/memguard.py`):
- **Techos:** la estimación por tamaño del TAC en la segmentación; 4 GB en Whisper (medido 1,5).
- **Colgado:** un árbol que no gasta CPU en 10 min (5 en Whisper) se corta.
- **Lo que enseñó la prueba `external`:** medir la "huella" como memoria comprometida mató una
  segmentación sana. torch y CUDA comprometen más de lo que tocan (9,3 GB comprometidos con
  7,4 GB de memoria física). Se mide la memoria física y la paginación real.
- **Residual:** el pico se mide cada 2 s; un pico más corto que eso puede no verse.
- **La malla (2026-10-07).** `visor3d._malla` de Polaris recorta a la caja de la máscara antes de
  suavizar; sin ese recorte una lesión pequeña en un estudio grande pide gigas. Es la malla de
  `app/volumes/geometry.py`. La prueba de Polaris que lo fija (`test_visor3d_malla_recorte`: malla
  idéntica a la del volumen entero y pico en megas) no corría en Windows por el módulo `resource`;
  con `app/polaris/compat/resource.py` corre y pasa en esta máquina (corrida suelta con el entorno
  de `scripts/polaris_tests.py`; `polaris/PRUEBAS.md` lo recoge cuando se regenere). Ese
  módulo solo existe para las pruebas de Polaris: en EMMA `import resource` sigue fallando
  (`tests/test_polaris_windows_reds.py`, campaña `polaris_compat_resource`).
  - **Residual:** la prueba mide el salto del pico histórico del proceso, como la original; un
    pico menor que el que ya dejaron sus casos anteriores no se vería.

**Datos personales en la cabecera del volumen (2026-10-07).** Un NIfTI lleva campos de texto libre
y admite extensiones; los conversores de DICOM guardan ahí desde el protocolo hasta la cabecera
DICOM entera, con nombre y fecha de nacimiento. EMMA firma el volumen tal como llega: lo que
entrara con un nombre quedaba firmado con él. *Gravedad media: un dato personal en un registro que
no se corrige, solo se redacta.* Controles (`app/volumes/privacy.py`; `tests/test_volumes.py`,
campañas `volumes_privacy` y `volumes_upload_privacy`):
1. **La comprobación de Polaris, tal cual** (`verifica_sin_pii`): antes de guardar, la subida se
   niega (422) si la cabecera lleva texto en `descrip`, `aux_file`, `intent_name` o `db_name`, o
   alguna extensión. Si el tripulante tiene identidad declarada (`crew-identity`), busca además
   su nombre, sus apellidos y su fecha de nacimiento en la cabecera.
2. **Tres reglas de EMMA encima.** El original se escribió para comprobar los ficheros que su
   autora acaba de limpiar, no los de otros, y como puerta de entrada se queda corto en tres
   sitios (medidos los tres):
   - *El hueco entre la cabecera y los vóxeles.* El original solo lee los 352 primeros bytes
     (toma `vox_offset` de una cabecera que nibabel ya ha puesto a cero): un nombre en el byte
     360 pasaba incluso con la identidad declarada. Con algo que no sean ceros ahí, no entra.
   - *Tildes, eñes y mayúsculas.* El original compara en minúsculas ASCII y en UTF-8: «MUÑOZ» en
     mayúsculas, o en Latin-1 (lo habitual en DICOM), se le escapaba. Cada trozo se busca también
     en mayúsculas, sin tildes y en Latin-1; la fecha, en los tres órdenes y con los separadores
     habituales (sin separador y con el año delante es la forma de DICOM).
   - *El envoltorio gzip.* `gzip fichero.nii` guarda dentro el nombre que tenía el fichero, y
     EMMA firma el `.gz` entero. Con nombre, comentario o campo extra en el envoltorio, no entra.
3. El motivo nombra el campo y nunca el dato, ni en la respuesta ni en el registro de sucesos.
4. Fallo cerrado: si la comprobación no puede ejecutarse (503), tampoco se guarda.
5. No se limpia en silencio: sin pedirlo, lo firmado es lo que el operador subió, y el mensaje
   dice cómo limpiarlo fuera y volver a subirlo.
6. **Limpiar aquí, solo si el operador lo pide (2026-10-07, decisión del usuario).** El rechazo
   dice además si vaciar la cabecera en EMMA lo dejaría entrar (`cleanable`, probado en seco), y
   la interfaz ofrece hacerlo reenviando el mismo fichero con `clean=true`. La puerta no se
   ablanda: no hay lista de textos permitidos. La limpieza usa `nifti_limpio` de Polaris, repone
   del fichero recibido la geometría y la escala, escribe cabecera y vóxeles seguidos (sin hueco,
   sin nada detrás, gzip sin nombre ni fecha), comprueba que los vóxeles son bit a bit los
   recibidos y **vuelve a pasar la misma puerta** con la misma identidad: si no pasa, 422 y no se
   guarda nada. Se guarda y se firma el limpio; el asiento declara que se limpió, los nombres de
   los campos vaciados (nunca su contenido: no sale en el asiento, ni en la respuesta, ni en el
   registro de sucesos) y el SHA-256 del recibido y del guardado. El fichero recibido no se
   conserva. Cada paso con su mutante (mismas dos campañas).

Tiene dos caras y se miden las dos, porque una puerta que lo rechaza todo tampoco deja pasar
ningún nombre. Lo que lleva un nombre no entra: pruebas de la suite, cada regla con su mutante.
Lo real y limpio sí entra: los 15 TAC del dataset de TotalSegmentator bajados en local, byte a
byte como los publica el dataset, pasan la puerta (medido el 2026-10-07; de 2 a 65 MB, el mayor
en unos 0,1 s en la máquina de desarrollo; `tests/test_volumes_external.py`, `-m external`). Los
cuatro ejemplos del paquete entran por su ruta, con huella fija, y su cabecera pasa esta misma
comprobación (suite normal).
- **Residual:** no se miran los vóxeles: un nombre quemado en la imagen pasa, y de un TAC de
  cabeza se puede reconstruir la cara. Sin identidad declarada solo se ve lo estructural (un
  nombre en `data_type` pasa; hay prueba que lo fija). La identidad se busca como se declaró: un
  trozo de menos de 4 letras no se busca (regla de Polaris), ni un apodo, ni una fecha con el año
  en dos cifras, ni otros identificadores (número de historia, DNI), que EMMA no conoce. Del
  envoltorio gzip solo se mira el primer miembro, y no se mira lo que haya detrás de los vóxeles.
  El texto técnico inocuo también se rechaza (`descrip` con los parámetros de adquisición, o el
  nombre «ct.nii» guardado por gzip): la comprobación no distingue y prefiere negar. No se ha
  medido con ficheros salidos de conversores de DICOM, que no hay aquí; si escriben `descrip`,
  se rechazarán, y se podrán limpiar aquí si el operador lo pide (control 6). De la limpieza: no
  mira ni limpia los vóxeles (lo mismo de arriba, y la oferta y el asiento lo dicen); un valor del
  tripulante que no sea su identidad declarada y esté en un campo numérico conservado (`pixdim`,
  el afín) sobrevive, igual que hoy pasa la puerta sin limpiar; del fichero recibido solo queda
  la huella, así que no se puede volver a él desde EMMA; los campos de la cabecera que no son
  geometría ni escala (`regular`, `extents`, `glmax`…) quedan de fábrica y se declaran por su
  nombre; un fichero big-endian se guarda en el orden de bytes de la máquina, con los mismos
  valores. Tampoco esto se ha medido con ficheros de conversores de DICOM reales.

### H19 — Un valor inferido o predicho se lee como medido, o un dato simulado como real

*Gravedad moderada.* Añadido el 2026-09-26 al contrastar EMMA con la especificación del equipo.

**Qué puede fallar:** la dosis efectiva (calculada con un factor de calidad medio) o la proyección
de una deriva se presentan con el mismo aspecto que la lectura de un sensor; un veredicto
construido sobre datos simulados o de voluntarios en Tierra se toma por uno de vuelo.

**Controles:**
1. Toda observación lleva `observation_type` y `evidence_context` firmados en el ledger (§3.14 de
   `record-integrity.md`); lo no medido exige el modelo que lo produjo.
2. La interfaz rotula MEDIDO / INFERIDO / PREDICHO con palabra y glifo, sin color propio, y el
   entorno (ISS, vuelo real, análogo, Tierra, simulado) en gráficas, dosis y proyecciones.
3. Las proyecciones solo existen para derivas estadísticamente reales, llevan su margen y el
   backend las declara "extrapolación lineal, no pronóstico clínico".
   Excepción declarada (decimocuarta ronda, C7, 2026-10-21): la dosis de misión proyectada al fin
   de misión configurado (`analysis/radiation.py`, `mission_projection`) no es la deriva de una
   tendencia sino la tasa media registrada prolongada a tasa constante. Va rotulada PREDICHA con
   su `model_version`, dice lo que supone («supone tasa constante: no prevé eventos solares») y
   cuántos días anteriores a la primera lectura no cuenta, y no lleva margen: su horquilla por
   tipo de radiación es INFERIDA y dice que no es un intervalo de confianza. No entra en la dosis
   acumulada, en ningún nivel ni en ninguna alerta (`tests/test_radiation_projection.py`,
   `test_the_projection_never_feeds_the_cumulative_dose_or_any_level`; campaña
   `tests/mutants/radiation_projection.json`).
4. `/status.provenance` cuenta de qué tipo y entorno son las lecturas que sostienen el veredicto.
5. Desde el 2026-10-26 (decimoséptima ronda, §5.37.1 de `hmi-state-of-the-art.md`; decisión del
   usuario) solo lo medido decide: la línea base, la tendencia y el riesgo leen las lecturas de
   tipo `measured` (`api/routes.py`, `ANALYSED_TYPES`, en `rules_version`). Una lectura inferida
   o predicha que llega por `POST /api/observations` se firma igual, se cuenta en
   `provenance.set_aside` y en las notas del estado, y no mueve ni la base, ni la tendencia, ni el
   «ahora» de los datos, ni ningún nivel o alerta; el detalle de cada alerta dice el tipo de las
   lecturas que la causaron y el corte personal que cruzaron. Excepción declarada, pendiente de
   que el usuario la confirme: la dosis acumulada medida **o inferida** llega al límite de carrera
   (`DOSE_TYPES`; la dosis efectiva es inferida por definición, H23); la predicha, no, y se dice
   (`tests/test_measured_only.py`; campaña `tests/mutants/measured_only.json`).

**Riesgo residual:** la etiqueta de entorno de las lecturas reales la declara quien despliega
(`EMMA_DEPLOYMENT_CONTEXT`); si se configura mal, la etiqueta miente.

### H20 — Una contramedida se presenta con más respaldo del que tiene, o su seguimiento se lee como prueba de eficacia

*Gravedad moderada.* Añadido el 2026-09-26 con la biblioteca de contramedidas.

**Qué puede fallar:** un tiempo de tripulación o una ventana de seguimiento inventados; una
contramedida sin protocolo presentada como respaldada; "el dominio mejoró" leído como "la
contramedida funcionó".

**Controles:**
1. La biblioteca (`app/data/countermeasures.json`) se valida al cargar: sin base declarada,
   `evidence-backed` sin protocolo, cifra de tiempo "sin fuente" o indicador fuera del catálogo,
   no se carga (`advisor/countermeasures.py`, con mutantes).
2. Cada entrada dice si la respalda un protocolo propio o solo el riesgo del dominio (`demo`), y
   la interfaz lo muestra; las cifras sin fuente se muestran como "sin fuente".
3. La evaluación compara niveles del dominio y comprueba que se repitió la medida; no añade
   umbrales (invariante 5) y siempre dice que coincidir en el tiempo no demuestra causa.
4. Dentro de la ventana no hay veredicto; cerrar es una decisión humana firmada con motivo.
5. La fuente de cada entrada es una ficha del registro único de evidencia, citada por
   identificador (`evidence/registry.py`, añadido el 2026-10-07): dice qué clase de documento es,
   en qué entorno y sobre quién se midió. Lo que nadie ha leído en la fuente sale `null` y
   declarado sin verificar; una fuente con animales no se registra sin su salvedad de alcance, y
   una ficha escrita en línea en la biblioteca no se carga.

**Riesgo residual:** la mayoría de entradas son `demo`; sin revisión de un médico de vuelo, la
biblioteca es un andamiaje con fuentes donde las hay, no un protocolo operativo.

### H21 — La hipótesis de causa ambiental compartida es errónea, o tapa un problema individual

*Gravedad moderada.* Añadido el 2026-09-26 con el hábitat y la correlación entre tripulantes.

**Qué puede fallar:** se atribuye al CO2 lo que en un tripulante es otra cosa; un sensor de cabina
averiado dispara la hipótesis; los tripulantes no estaban en el módulo cuya lectura se usa; o, al
revés, **una ubicación mal declarada o caducada** manda detrás la hipótesis ambiental que era la
buena (añadido el 2026-10-07, con la ubicación declarada por módulo); o **las anclas de módulo
estiman un módulo equivocado** —multitrayecto en un módulo metálico, el cuerpo que tapa la señal,
un ancla movida sin declararlo, la frontera entre dos módulos— y esa estimación ordena mal las
hipótesis (añadido el 2026-11-10, con las anclas).

**Controles:**
1. Es una capa de hipótesis por encima del motor: no cambia puntuaciones, umbrales ni alertas de
   nadie (invariante 5). El estado individual de cada tripulante sigue igual y visible.
2. Solo cuenta una excursión fuera de un **límite normativo** (NASA-STD-3001 Vol 2) en la misma
   ventana; la zona de confort no es causa, y no se inventa un umbral de "subida".
3. Toda salida dice "correlación, no causa", declara el supuesto de que la tripulación comparte
   el hábitat y propone primero contrastar el sensor.
4. Lecturas imposibles se rechazan como fallo de sensor; el CO2 se juzga en media de una hora,
   como pide el requisito, y un pico breve no dispara nada.
5. **Ubicación declarada (2026-10-07).** Una persona puede declarar en qué módulo estaba un
   tripulante (asiento firmado, `record-integrity.md` §3.17 bis); una excursión en un módulo
   donde no estaba deja de explicar su cambio. Contra una declaración equivocada:
   - la hipótesis **no se quita**: baja en el orden, rotulada "menos probable", con el motivo y
     el aviso de que la ubicación la declara una persona y no se mide. Sigue pudiéndose confirmar;
   - cuando todas bajan, la primera comprobación que se propone es revisar la ubicación declarada;
   - solo se da por ausente a quien tiene declarado **todo** el tramo de la excursión en otros
     módulos. Un tramo sin declarar, o una lectura de un módulo que no está en la lista, se tratan
     como hábitat compartido (`test_a_gap_in_the_declaration_never_clears_the_habitat`,
     `test_a_reading_from_a_module_outside_the_list_places_nobody_elsewhere`);
   - el módulo sale de una lista cerrada, en la declaración y en la lectura de cabina: un nombre
     libre escrito de dos maneras daría por ausente a quien estaba (422);
   - una declaración posterior corrige a la anterior, y solo cuentan las firmadas por la consola;
   - niveles, puntuaciones, motivos y alertas son idénticos con y sin ubicación
     (`test_the_location_only_orders_hypotheses_and_never_moves_a_level` y, por la API,
     `test_a_declared_location_is_a_signed_ledger_entry_and_reorders_the_hypothesis`); y sin
     ubicación la salida es la de antes, clave por clave
     (`test_without_a_declared_location_the_output_is_the_one_from_before_locations`).
6. **Ubicación estimada por las anclas de módulo (2026-11-10).** Sustituye a la que ponía el
   simulador, que se quitó (decisión del usuario: «las queremos reales»). Contra una estimación
   errónea (`analysis/location.py`, `record-integrity.md` §3.17 bis):
   - **la consola manda** sobre las anclas aunque su declaración sea anterior a las lecturas
     (`context.prevailing`, la única regla; `test_the_console_wins_even_when_the_anchors_are_heard_after_it`):
     quien ve que la estimación está mal la corrige declarando;
   - la granularidad es el **módulo, nunca metros**; si dos módulos se oyen con menos de
     `margin_db` de diferencia el tramo queda **indeterminado** y no se elige, y un tramo
     indeterminado cuenta como sin ubicación, que nunca exculpa al hábitat;
   - histéresis (`min_dwell_s`) contra un cuerpo que tapa un ancla un instante, y caducidad
     (`stale_after_s`): una estimación vieja se dice **caducada**, con su antigüedad, y deja de
     ordenar;
   - los textos de la correlación, del contexto de una alerta y del estado dicen «estimada por las
     anclas» y no «declarada por una persona»; la interfaz recibe `source` y `location_state`;
   - un ancla sin declarar se guarda pero no se usa; una lectura se juzga con el ancla que valía
     en su instante; solo cuentan los lotes firmados por `location-anchors`, identidad que ninguna
     lectura pública puede usar;
   - los cinco parámetros están clasificados **sin respaldo: calibrar en cada nave**
     (`data/location_sensing.json`): la precisión de zona con BLE medida en Tierra (71-85 %) no
     se traslada a un módulo metálico, y eso queda dicho;
   - niveles y alertas idénticos con y sin anclas
     (`test_the_estimated_location_never_moves_a_level_or_an_alert`). Campaña de mutantes:
     `tests/mutants/location_anchors.json`.

**Comparación de un indicador entre tripulantes (2026-10-07).** Poner la misma variable de todos
sobre el mismo eje (`GET /api/crew/compare`) tiene sus propias formas de engañar: leerse como
prueba de causa común, comparar valores absolutos de personas con bases distintas, o dar por
"normal" a quien no tiene lecturas. Controles, con mutantes
(`tests/mutants/crew_compare.json`, `crew_compare_api.json`):
1. Cada serie va contra la línea base propia de su tripulante; sin base personal no hay
   diferencia, y no se inventa.
2. Quién se desvía lo deciden la persistencia y la tendencia del motor, sin umbral propio
   (`test_who_deviates_is_what_each_crew_status_says`). Es de solo lectura: no firma nada ni mueve
   niveles (`test_comparing_is_read_only_and_moves_no_level`).
3. Quien no tiene lecturas se dice y no cuenta como "dentro de lo esperado".
4. El resumen se rotula "coincidencia temporal, no causa", solo cuenta, y pasa el guardián de
   texto. A una deriva, que no tiene inicio, no se le da un "desde".
5. Con `until`, Tierra no ve más de lo que ha llegado (`test_ground_only_sees_what_has_arrived`).
6. Cada serie declara tipo y entorno de sus lecturas: una simulada y una real no se comparan sin
   decirlo.

**Riesgo residual:** una ubicación declarada errónea o que nadie actualizó, o una estimada por las
anclas en el módulo equivocado, ordena mal las hipótesis (nunca las elimina ni toca una alerta).
La estimación por anclas BLE no está validada dentro de un módulo metálico ni ha volado (el
precedente de NASA JSC se probó solo en Tierra); la alternativa con vuelo documentado es UWB
(`compliance/location-sensing-feasibility.md`). Sin ninguna ubicación
declarada se sigue suponiendo un hábitat compartido, y la salida lo dice. La lista de módulos es
un parámetro de diseño, no la de una nave; y el simulador supone, sin respaldo bibliográfico, que
la excursión ocurre en un solo módulo: no hay modelo de mezcla de aire entre módulos.
En la comparación, el "ahora" es la última lectura de ese indicador en la tripulación, que en un
indicador que se mide poco puede no coincidir con el del estado de cada uno; la respuesta lo
declara (`window_basis`).

### H22 — Un dato de hidratación, nutrición o recuperación se sobreinterpreta

*Gravedad baja.* Añadido el 2026-09-26.

**Qué puede fallar:** una guía (2,5 L/día de agua, aceptabilidad ≥ 6) se toma por umbral clínico;
una hipótesis (fatiga de menú) se presenta como hallazgo; "fuera del rango prevuelo" se lee como
"no recuperado".

**Controles:** las guías son `ReferenceBasis.GUIDELINE` y el motor no alerta por ellas (con
mutante); ningún indicador nuevo tiene límite de peligro; la fatiga de menú está clasificada como
«sin respaldo en lo leído» (hasta el 2026-10-26, «contestada»; `hmi-state-of-the-art.md` §5.38.10)
y se proyecta sin alertar; la recuperación es descriptiva y lo dice. Los códigos LOINC
se leyeron en su ficha y la unidad sigue a su propiedad (mutante para la ingesta VRat). Desde el
2026-10-16 el criterio de aceptabilidad se evalúa valoración a valoración
(`analysis/food_acceptability.py`, `GET /api/nutrition/food-acceptability`) como marca sobre la
comida, con la frase de NASA-STD-3001 Vol 2 [V2 7002] (página 119) y lo que la norma juzga (la
valoración global de un alimento) dicho al lado: el motor no la importa, la ruta no escribe, una
prueba fija el veredicto de `menu-fatigue` y el cargador rechaza un criterio que su frase no
escriba (mutantes `food_criterion` y `food_acceptability`).

### H23 — Una dosis inferida se toma por medida, o una revisión humana se registra sobre una hipótesis que ya no existe

*Gravedad moderada.* Añadido el 2026-09-28.

**Controles:** la dosis de misión y la de carrera van rotuladas INFERIDA con su modelo y su factor
de calidad; sin dosis previa declarada no se suma cero (con mutante). La revisión de una hipótesis
devuelve 409 si no está en el estado actual (con mutante). Cada estado declara la versión de las
reglas con que se decidió, y cambiar un umbral la cambia (con mutante).

### H24 — Una proyección comprobada se lee como validación clínica, o un contaminante se juzga con la ventana equivocada

*Gravedad moderada.* Añadido el 2026-09-28.

**Controles:** la comprobación de proyecciones se declara calibración del propio modelo y separa
retrospectiva de instantánea firmada; la vista de Tierra no firma instantáneas (con mutante). Cada
SMAC se juzga con la media de su tiempo de exposición (1 h, 24 h, 7 d, 30 d; el amoníaco también
180 d y 1000 d desde el 2026-10-14) y el formaldehído como techo, leídos en JSC 20584 Rev C (con
mutantes); el ruido solo contra [V2 6077], porque el límite NC-50 por bandas de octava no se
puede comprobar con una lectura en dBA, y se dice; su rótulo dice además para qué lo escribe la
norma (operaciones fuera de lo nominal) y que EMMA no conoce la ponderación temporal de la
lectura.

*Ampliado el 2026-10-14: un límite se juzga con una clase que la norma no le da.* El rango
objetivo de normoxia (145-155 mmHg, tabla 6.2-1 de NASA-STD-3001 Vol 2 Rev F) se juzgaba como
límite de salud, y [V2 6012] como dos rangos sueltos cuando es una figura conjunta. **Controles:**
el rango objetivo es una clase propia (`target`, aviso, fuera de las hipótesis) y los límites de
salud del O2 son los de exposición de esa tabla (127 mmHg en media de 1 h, 122 absoluto, 356); la
temperatura se juzga con los lados inclinados de la figura 6.2-2 y la humedad simultánea, y sin
ella solo fuera de la envolvente 18-27 °C («no evaluable con una lectura»); una clase de límite
desconocida no carga (todo con mutantes, `tests/mutants/habitat.json`). **Residual:** los lados se
trazan rectos sobre la humedad relativa, y la figura los dibuja sobre la razón de humedad: a
101,325 kPa, hasta ~2 puntos más estricto arriba y 0,6 más laxo abajo (cabecera del módulo); y la
lectura de O2 es la presión parcial de cabina, no la inspirada que pide el requisito.

## 4. Riesgo residual global

Los veinticuatro peligros tienen control implementado y **ninguno está cerrado del todo**. Los tres que más
pesan, por orden:

1. **H3 y H12 comparten causa raíz: no hay identidad de operador.** Toda la integridad del registro
   se sostiene sobre firmas de fuentes, y la API no autentica a quien llama. Es lo primero que
   habría que resolver para cualquier uso que no sea una demostración.
2. **H1 en los deterioros lentos.** El sistema está afinado para no gritar, y eso tiene un precio
   medido. Está declarado, no compensado.
3. **H9 sin espectro LET.** La aproximación es conservadora respecto de Q = 1, pero no es el modelo
   que pide el estándar.

**Quién declara aceptable este riesgo residual.** Nadie, todavía, y este documento no lo hace. Esa
decisión la toma la organización responsable del programa, con el análisis del sistema completo y
la firma de quien responde. Lo que hay aquí es el material para que esa decisión se pueda tomar con
los ojos abiertos.

---

## 5. Realimentación desde producción

*Paráfrasis de la cláusula 10 de ISO 14971:* el archivo de riesgos no se cierra al entregar.

Lo que este sistema ya produce y serviría de entrada: el informe de rechazos de cada importación
(H4, H6), los fallos de verificación de integridad con su índice de asiento (H5), la edad de los
datos externos (H7) y las dos métricas de validación, que son regresión ejecutable (H1, H2). Lo que
**no** hay: registro de qué alertas resultaron ser ciertas. Sin eso, la tasa de falsa alarma real de
una misión no se puede medir, solo la del banco de pruebas.

---

## 6. Este documento también se audita

**2026-09-22.** Una revisión independiente comprobó contra el código, ejecutándolo, cada afirmación
de este archivo: los 21 nombres de prueba citados —los 21 existen y pasan—, las rutas de módulo,
los doce riesgos residuales y las cuatro cifras de validación, que volvió a medir sobre MMASH en
vez de leerlas (81,82 %, 77,27 %, 0,2329 %, 2 de 22: coinciden). Encontró cinco enunciados
imprecisos, corregidos aquí: el techo real de la regresión de falsa alarma (H2), la confusión entre
el 422 de un dato mal formado y el 409 de un contenido que no casa con su hash (H6), el tope de
fechas que solo rige en la importación (H8), una prueba marcada `live` citada como si corriera en
la suite (H9) y qué tope se comprueba antes de tener el cuerpo en memoria (H11).

Dos de sus hallazgos no eran de este archivo sino de lo que este archivo cita, y se corrigieron en
su origen el mismo día: la prueba inexistente del Control 3 y el techo de la regresión de falsa
alarma. Auditar un documento sirve para encontrar fallos en el código, no solo en la prosa.

Lo que no se puede auditar contra el código queda dicho: las paráfrasis de ISO 14971 —norma de
pago—, los juicios clínicos sobre reversibilidad de las contramedidas, y que "nunca en 500" es una
propiedad falsable, no demostrable.
