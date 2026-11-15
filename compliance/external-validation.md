# Validación externa contra fisiología humana real

**Dataset:** MMASH — *Multilevel Monitoring of Activity and Sleep in Healthy people*
(PhysioNet, Open Access, ODbL v1.0). 22 sujetos sanos, 24 h continuas,
1 740 412 latidos procesados.
**Fecha:** 2026-09-21
**Resultado:** **21 de 22 personas sanas no reciben ninguna alerta**, mientras
se marca el **82 %** de las taquicardias sostenidas y el **77 %** de los episodios
agudos inyectados. Falsa alarma por lectura: 17,07 % → **0,18 %**.
*(Hallazgo 29, medido y sin adoptar: con la corrección del respaldo de familia y su cobertura de la
hora la falsa alarma bajaría a **0,16 %**, con los mismos 21 de 22 sanos sin alerta, pero el colapso
de HRV detectado bajaría de 13,6 % a 9,1 %, bajo su suelo de prueba. La literatura leída el
2026-10-23 respalda comparar a la misma hora, y en MMASH toda detección del colapso de HRV sale de lo
contrario. Por decisión del usuario (2026-10-23) el motor no cambia: estas cifras son las suyas.)*

---

## Por qué se hizo

EMMA tenía 284 pruebas en verde y estaba validado únicamente contra su propio
simulador. Eso es el patrón exacto del **Epic Sepsis Model**: AUC 0,846 en
validación interna, 0,761 en externa, y en producción se le escapaba el 67 % de
las sepsis mientras alertaba sobre el 18 % de todos los ingresados — hasta que
las enfermeras taparon la cámara para dejar de recibir avisos.

Un sistema probado solo contra los datos que él mismo genera no ha demostrado
nada.

## Las dos métricas

**Especificidad.** Los 22 participantes de MMASH no se deterioraron: por
construcción, cualquier hallazgo sobre ellos es una alarma que no corresponde a
un deterioro clínico.

**Sensibilidad.** MMASH no tiene deterioros, así que por sí solo no dice nada
sobre si el sistema detectaría uno. Se mide inyectando perturbaciones de magnitud
conocida sobre la fisiología real de los mismos sujetos: la base sigue siendo
humana —con su variabilidad circadiana, sus artefactos y sus colas pesadas— y lo
único sintético es el deterioro.

> **Sin el segundo eje, el primero no significa nada.** Se puede llegar al 0 % de
> falsas alarmas apagando las alertas.

---

## El resultado

| Etapa | Falsa alarma | Sujetos marcados |
|---|---|---|
| **Primera medición** | **17,07 %** | 22 / 22 |
| Tras corregir dos bugs del cargador | 16,90 % | 19 / 22 |
| Tras estratificar por contexto fisiológico | 13,92 % | 18 / 22 |
| Cuantiles empíricos + peligro absoluto | 5,27 % | 14 / 22 |
| Gravedad limitada por resolución de muestra | 4,98 % | 12 / 22 |
| Contexto con granularidad de agenda | 5,06 % | 11 / 22 |
| Sueño etiquetado desde registros de cama | 1,72 % | 9 / 22 |
| Base exigida con resolución suficiente | 0,32 % | 10 / 22 |
| Eje temporal del dataset corregido | 0,2329 % | 2 / 22 |
| **Aparato quitado ≠ reposo (hallazgo 28)** | **0,1842 %** | **1 / 22** |
| Respaldo de familia con el reposo (hallazgo 29, medido, sin adoptar) | 0,2329 % | 1 / 22 |
| Y solo si cubre la hora de la lectura (hallazgo 29, medido, sin adoptar) | 0,1625 % | 1 / 22 |

**Reducción del 98,9 %.** Epic alertaba sobre el 18 % de los pacientes; EMMA
marca a 1 de 22 personas sanas. En reposo la tasa baja a **0,1472 %**.

> Las dos últimas filas son la corrección del respaldo de familia (hallazgo 29): sin cobertura sube
> la falsa alarma; con cobertura de la hora baja a 0,1625 % (0,1472 % en reposo, igual), pero el
> colapso de HRV detectado cae bajo su suelo de prueba. No se adoptó (decisión del usuario,
> 2026-10-23): el motor es el de la fila del hallazgo 28, y la reducción del 98,9 % es la suya.

Los dos que siguen marcándose son `user_15` y `user_17`, ambos por dominio
cardiovascular. `user_15` es el sujeto con el pulso máximo más alto del dataset
(192,25 lpm).

### El contrapeso

Medido sobre los 22 sujetos, con la inyección acotada a lo fisiológicamente
posible (hallazgo 18) y el eje temporal corregido (hallazgo 17):

| Deterioro inyectado | Detectado | Dominio marcado | Escalado |
|---|---|---|---|
| Taquicardia sostenida (+25 lpm) | **95,5 %** | 81,8 % | 77,3 % |
| Episodio agudo (+40 lpm, 2 h) | **90,9 %** | 77,3 % | 72,7 % |
| Taquicardia progresiva (+15 lpm/día) | 31,8 % | 13,6 % | 9,1 % |
| Colapso de HRV (−30 ms SDNN) | 13,6 % | 4,5 % | 0,0 % |

*(Cifras del 2026-09-22, tras el hallazgo 28. Antes: escalado 72,7 % y 68,2 % en
los dos primeros; marcado 18,2 % y 9,1 % en los dos últimos.)*

Hubo **pérdida real de sensibilidad** frente al motor original, que detectaba el
100 % en los cuatro. Se acepta a cambio de dividir las falsas alarmas por setenta,
y se declara en vez de ocultarse.

**Los dos escenarios bajos miden el experimento, no el motor.** La taquicardia
progresiva acumula solo ~8 lpm en las 13,5 h que siguen a su inicio: está dentro
de la variación normal de un día. El colapso de HRV pide ver −30 ms de SDNN en un
indicador cuya razón sueño/reposo varía entre 0,58 y 2,85 según la persona.
MMASH dura 36 horas y no puede validar una deriva lenta.

> El suelo de la taquicardia progresiva **bajó de 0,35 a 0,30 y no porque el
> motor empeorara**: el 0,35 se fijó cuando dos sujetos tenían el eje temporal
> roto y eran triviales de detectar. Esa cifra estaba inflada por un defecto del
> dataset. Ver hallazgo 17.

**Sobre qué indicadores.** Los cuatro deterioros se inyectan solo en la
frecuencia cardiaca (tres) y en la SDNN (uno); la sensibilidad de los demás
indicadores, también los que salen de MMASH, no está medida. La matriz de riesgos
(`GET /api/risks`, `sensitivity` de cada fila y `sensitivity_measured` de cada
indicador) lo publica leyendo las claves y formas que construye el inyector
(`validation/injection.py`, `REFERENCE_TARGETS`), sin copiar las cifras de esta
tabla: remite aquí (`hmi-state-of-the-art.md` §5.36.2).

---

## Lo que la validación encontró

### 1. Dos bugs en el cargador — errores míos, no del motor

**Sueño fragmentado leído como noches completas.** MMASH registra el sueño por
segmentos: user_1 tiene dos episodios la misma noche (144 y 196 min). Emitir cada
segmento como una noche entera daba duraciones de 2-3 h y marcaba al **95,5 %**
de los sujetos.

**Falsa equivalencia PANAS → valencia de ánimo.** Se mapeó el afecto positivo de
PANAS (10-50) a `mood-valence` (0-10) con un reescalado inventado. La mediana
real (25) caía en 3,75, justo bajo el umbral de 4: la mitad de los sujetos sanos
marcados por una conversión que no existe en la literatura. Se eliminó el mapeo.
Es el mismo error que usar un código LOINC con la unidad de otra propiedad.

### 2. Recomendaciones clínicas usadas como umbrales de alerta

**`sleep-duration`** tenía 7-9 h, que es lo que se *recomienda* dormir. Los
adultos sanos de MMASH dormían 4-6 h. Peor: el simulador de EMMA usa 6,0 h como
valor nominal documentado para tripulación de la ISS, **o sea que la línea base
de EMMA caía fuera del rango de referencia de EMMA**. Una incoherencia interna
que solo un dato externo podía revelar, porque el simulador nunca ejercitaba esa
vía.

**`sleep-efficiency`** tenía 85-100 %, el *objetivo clínico*. Mediana real
**84,9 %**, mínimo 73,5 %: el 52 % por debajo del umbral. Corregido a 75 %, donde
se sospecha alteración del sueño — queda por debajo 1 de 21 sujetos (~5 %).

> **Principio:** una guía de salud pública no es un umbral de alarma.
> Confundirlos hace saltar la alerta sobre la mayoría de la población sana.

**El arreglo estructural.** Bajo un mismo campo convivían cuatro cosas
incompatibles. Ahora cada rango declara su procedencia (`ReferenceBasis`):

| Procedencia | Qué significa | Indicadores |
|---|---|---|
| `observed` | Medido en población sana. **El único válido como umbral** | 13 |
| `design` | Escala definida por el proyecto (autoinformes, recuentos) | 9 |
| `limit` | Límite normativo — `cumulative-dose`, NASA-STD-3001 [V1 4030] | 1 |
| `guideline` | Recomendación. **No es un umbral** | 1 — `exercise-minutes` |

Las cifras de la tabla son el reparto de cuando se hizo el arreglo; el vigente lo da
`/api/indicators`. Desde el 2026-10-20 (decisión del usuario) un indicador **sin rango no declara
procedencia**: su `reference_basis` es `null`, en `/api/indicators` y en la huella de reglas. Antes
heredaba `observed` por defecto, y así una escala decidida por EMMA sin rango (`appetite-rating`)
o una analítica cuyo rango trae el laboratorio en su informe se presentaban como "medido en
población sana". El catálogo no carga si hay rango sin base o base sin rango
(`VitalCode.__post_init__`; mutantes `reference_basis`, `reference_basis_api` y
`reference_basis_rules`, uno por sitio), y cada indicador con rango nombra la suya. La huella de
reglas cambia, y con ella `rules_version`: lo evaluado antes y después lleva versiones distintas aunque decida igual. Ningún lector cambia de
veredicto: el motor solo mira si la base es `guideline`, y `null` no lo es; los 9 escenarios del
simulador con 4 tripulantes dan el mismo estado completo antes y después, salvo la versión.

Queda una guía activa. **No se le ha inventado un umbral de preocupación**: no
hay dato para fijarlo, e inventarlo repetiría el error que se acaba de corregir.
Está declarada, expuesta en `/api/indicators`, y una prueba impide que de una
guía se derive un límite de peligro.

### 3. La línea base era ciega al estado

En 24 h de un sujeto sano el pulso recorrió **59-128 lpm — 68 lpm de amplitud
circadiana**, mientras la dispersión de su propia línea base era de **11,32 lpm**.
Seis veces más estrecha que la variación normal del día.

Una lectura tomada despierto y comparada contra una ventana construida mientras
el sujeto dormía queda a varias sigmas **por fisiología normal, no por
patología**. La base móvil resolvía el problema del tiempo (adaptación) pero no
el del estado.

**Corrección:** `VitalObservation` gana `context` (`sleep`/`rest`/`active`/
`unknown`) y `evaluate_rolling` estratifica por él.

**Por qué no bajó más:** el diario de MMASH es escaso — 31 ventanas en 24 h, y el
**33 % de las observaciones quedan sin contexto**. En una misión el equivalente
es el horario de a bordo, que cubre el día entero.

### 4. Los z-scores asumían una distribución que no existe

El hallazgo que permitió el salto del 13,9 % al 5,3 %.

Bajo normalidad, |z| ≥ 2 debería excederse en el **4,55 %** de las lecturas.
Observado: **22,02 %**. Los percentiles empíricos lo rematan — p90 = 5,66,
**p99 = 12,63**, p99,9 = 27,35. El umbral de "grave" (|z| = 4) caía alrededor del
percentil 80. Y subir el umbral no era salida: con |z| ≥ 4 seguía habiendo un
7,04 %.

**Corrección:** la gravedad la deciden **cuantiles empíricos** de la propia base
del sujeto. La tasa de falsa alarma deja de ser una consecuencia emergente de un
supuesto falso y pasa a ser un parámetro de diseño. Además es interpretable sin
estadística: *"por encima del 99 % de tus últimas dos semanas en reposo"*.

**Matiz que salió de una prueba rota:** con 40 muestras, p99 y p99,9 colapsan en
el máximo observado, así que todo exceso salía "grave". No se puede afirmar un
percentil más fino que la resolución de la muestra. Cada nivel exige ahora un
mínimo de muestras; por debajo, lo más que se afirma es "fuera de lo visto".

### 5. El sueño no estaba etiquetado, y era la mitad del problema

El cambio que más rindió de todos: **5,06 % → 1,72 %**.

Al investigar el residuo, las cinco rachas más largas de lecturas marcadas en
sujetos sanos —de hasta **90 lecturas consecutivas**— resultaron ser todas
lecturas **por debajo** de la línea base: −22, −26, −17, −29 y −22 lpm. Valores
de 47-74 lpm contra bases de 74-95.

Eso es dormir. El pulso cae 20-30 lpm durante el sueño, y el sistema lo marcaba
como "pulso demasiado bajo" porque lo comparaba contra una referencia de vigilia.

**La causa:** solo **228 de 18 460 observaciones** llevaban contexto de sueño. El
contexto se tomaba del diario de actividad, y nadie apunta "estoy dormido" en un
diario. Pero MMASH registra las horas reales de cama en `sleep.csv`.

**Corrección:** las ventanas de sueño se construyen desde los registros de cama y
tienen prioridad sobre el diario. La cobertura pasó de 228 a **4185**
observaciones, y la falsa alarma cayó a un tercio sin perder nada de
sensibilidad.

**La lección general:** el contexto declarado por la persona es poco fiable justo
cuando más importa. Los datos objetivos —registros de cama, acelerometría, la
agenda de a bordo— cubren lo que un diario deja fuera.

### 6. Un intento que NO rindió, y se deja escrito

Dentro de `rest`, la mediana de pulso va de **58 a 80 lpm** según la subactividad
(pantalla 71, laboral 76, comer 80): 22 lpm de dispersión entre subestados frente
a 11 lpm de la propia línea base. El diagnóstico era correcto, así que se dividió
`rest` en `rest`/`work`/`meal`.

**No mejoró la tasa** (4,98 % → 5,06 %). Mejoró levemente la detección progresiva
(86 % → 91 %). Se mantiene porque modela mejor la realidad medida y es lo que da
una agenda de misión real, pero **no se presenta como una mejora**.

Dos cosas más salieron de ese intento:

- **La persistencia temporal se descartó antes de implementarla.** Medidas las
  rachas, las excursiones de una sola lectura eran solo el **8 %** de las marcas
  en sanos. No habría servido.
- **Un bug de granularidad.** Al añadir `work` y `meal` se quedaron fuera del
  conjunto "reposo", así que esas lecturas se juzgaban con el límite de esfuerzo
  (150 lpm) en vez del de reposo (110): la detección del episodio agudo cayó del
  90 % al 20 %. Lo cazó el suelo de sensibilidad, no la tasa de falsa alarma.

### 7. Una base demasiado fina no es evidencia

El residuo que quedaba era casi todo `heart-rate`, y el diagnóstico fue nítido:
**213 de 220 lecturas marcadas usaban una línea base de menos de 100 muestras**,
con mediana de **30**.

Con 30 observaciones no se puede estimar un percentil 99. Lo que quedaba era un
respaldo que reportaba "fuera del rango que he visto" como hallazgo leve — y con
30 muestras eso ocurre en torno al **6 % de las veces por puro azar**, que era
exactamente la tasa observada.

**Corrección:** `MIN_SAMPLES` pasa de 20 a 100, acoplado a la resolución del
cuantil más débil que el sistema afirma. Una base está establecida **exactamente
cuando puede sostener alguna afirmación**. El respaldo de "fuera de lo visto" se
eliminó. Una invariante en las pruebas impide desacoplar las dos constantes.

Falsa alarma: 1,72 % → **0,32 %**.

**Lo que esto destapó en producto:** al subir el umbral, el escenario de evento
solar dejó de alertar. Causa: `absorbed-dose-rate` **no tenía límite de peligro
absoluto**, así que la radiación quedaba sin ninguna protección mientras no
hubiera base personal — justo al principio de una misión. Corregido con un
límite de 100 µGy/h, dos órdenes de magnitud sobre el fondo en órbita baja.

### 8. La sensibilidad se medía con un instrumento ciego

`measure_sensitivity` contaba solo **desviaciones**, no el estado de riesgo. Pero
una taquicardia progresiva de +15 lpm/día es precisamente lo que `trend.py`
existe para captar, y no genera necesariamente desviaciones puntuales. La métrica
estaba ciega a media arquitectura.

Ahora se mide en dos niveles: `detección` (hubo desviación marcada) y
**`escalado`** (subió el nivel de riesgo del dominio respecto al que ese mismo
sujeto ya tenía). El segundo es lo que la tripulación llega a ver.

#### Y con la métrica corregida apareció un bug propio

Con el escalado medido, el episodio agudo daba **0 %**: detectaba el 90 % de las
desviaciones y no elevaba el riesgo ni una vez.

La causa: la red de seguridad que permite que un hallazgo aislado pase sin
cumplir persistencia seguía condicionada a **|z| ≥ 6**, pero la gravedad había
pasado a decidirse por cuantiles empíricos. Un hallazgo grave con z moderado ya
no la disparaba, y las ~25 lecturas del episodio en una ventana de 280 no
llegaban al 30 % de persistencia.

Corregido para que mire la gravedad. Escalado del episodio agudo: **0 % → 50 %**.

### 9. La tendencia ajustaba ritmo circadiano y lo llamaba deriva clínica

El peor bug de todos los encontrados, porque producía hallazgos **falsos con
apariencia de verdaderos**.

Medido sobre un sujeto **sano y sin deterioro inyectado**, el ajuste lineal de
24 h daba una pendiente de **−92,9 lpm por semana**, marcada como significativa y
clínicamente relevante. Nadie pierde 93 lpm de pulso a la semana: la serie
empezaba a las 10:00 y terminaba a las 09:45 del día siguiente, recogiendo la
rama descendente del ciclo diario. Ajustar una recta a menos de un ciclo no mide
deriva — mide en qué fase empezó y acabó la ventana.

Y había un segundo efecto, peor: esa pendiente espuria **enmascaraba** la deriva
ascendente de un deterioro inyectado, porque iba en sentido contrario.

**Corrección doble:**
- `MIN_SPAN_DAYS = 3`: no se afirma una tendencia sin varios ciclos completos.
- Las tendencias se estratifican por contexto, igual que la línea base. La
  tendencia del pulso **en reposo** es una magnitud clínica; la del pulso "en
  general" depende de cuánto ejercicio cayó en cada extremo de la ventana.

**Consecuencia honesta:** con 24 h, MMASH ya no puede validar la vía de
tendencia, y el escalado de deriva lenta cae a 5 % y 0 %. No es una pérdida: **parte
de aquel 9 % y 27 % venía de tendencias circadianas espurias**, es decir, el
sistema acertaba por el motivo equivocado.

Esa vía se valida donde sí se puede, con datos de duración de misión: en
escenario nominal calcula 22 tendencias y marca **cero**; en desacondicionamiento
marca exactamente pulso, HRV, ortostática y ejercicio
(`test_trend_path_works_on_mission_length_data`).

### 10. Una sola lectura extrema tampoco es evidencia

Al medir lo que ve la tripulación apareció el último defecto grande, y era **mi
propia corrección anterior**.

De 22 sujetos sanos, **9 acababan en nivel CONCERN**. Diagnóstico: los nueve por
**un único hallazgo grave** con 0,4 % de persistencia — una lectura de unas 250.
La red de seguridad que había añadido para rescatar el episodio agudo eximía de
persistencia a cualquier hallazgo grave, aunque fuera uno suelto.

El argumento que lo zanja es aritmético: el corte de "grave" es el percentil
99,9, así que en 250 lecturas se esperan **0,25 por puro azar**. Ver una no
sorprende; ver tres sí — la probabilidad cae al orden del 0,2 %.

**Corrección:** la red exime del *porcentaje* de persistencia, no de la
evidencia. Exige una **ráfaga de tres** lecturas graves. Un episodio agudo real
produce ráfaga; el ruido produce lecturas sueltas. *(Ese «tres» era la respuesta
solo para la ventana de MMASH; hoy se calcula según la ventana — ver hallazgo 26.)*

| | Antes | Después |
|---|---|---|
| Sanos sin ninguna alerta | 12 / 22 | **19 / 22** |
| Escalado, taquicardia sostenida | 55 % | **68 %** |
| Escalado, episodio agudo | 50 % | **65 %** |
| Falsa alarma por lectura | 0,32 % | 0,32 % |

Mejoró en los dos ejes: al dejar de marcar a sanos, además hay margen para que un
deterioro real escale.

### 11. La métrica de sensibilidad infravaloraba el sistema

`escalated` exige que la perturbación **suba** el nivel respecto al que el sujeto
ya tenía, así que penaliza a quien ya alertaba. Desglosado en la taquicardia
sostenida: 12 sujetos pasaban de nominal a concern, **9 ya estaban en concern** y
solo 1 se escapaba. El escalado decía 55 %; los marcados eran 21 de 22.

Se añadió `flagged` —con el deterioro presente, ¿el dominio queda marcado?— que
es la pregunta clínica. Y su contrapeso, `MAX_HEALTHY_FLAGGED`: sin un techo de
sujetos sanos marcados, cualquier suelo de detección se satisface alarmando con
todo.

### 12. MMASH apenas ejercita el motor que se creía estar validando

El hallazgo más importante sobre la propia validación, y descubierto midiéndolo:

**El 99,4 % de las desviaciones pasan por el respaldo poblacional y los límites
críticos. Solo el 0,6 % usa línea base personal.**

La causa es estructural: con 24 h de datos, ventana de 14 días, desfase de 12 h y
estratificación por contexto, **ninguna ventana móvil llega a reunir las 100
muestras** que exige una base establecida. La maquinaria de cuantiles empíricos,
la estratificación de la base y la ponderación por confianza quedan dormidas.

Consecuencia honesta: **las cifras de MMASH miden sobre todo la lógica de
límites de peligro absoluto**, no el motor de base personal. No invalida nada de
lo anterior, pero acota lo que se puede afirmar.

Esa vía se valida donde sí se ejercita —con datos de duración de misión, donde el
88 % de las desviaciones usan base personal— en
`test_every_scenario_flags_its_own_domain_only`: cada patología marca exactamente
su dominio y el escenario nominal no marca nada.

### 13. Los límites de peligro se desactivaban al conocer al sujeto

El bug más grave de esta tanda, y lo destapó la validación anterior.

En el escenario de evento solar: **35 lecturas de dosis por encima del límite
—pico de 1668 µGy/h contra un límite de 100— y ningún hallazgo.** El dominio de
radiación se quedaba en NOMINAL.

La causa: los umbrales de peligro absoluto solo se comprobaban en el respaldo
poblacional. En cuanto el sistema tenía línea base personal, **dejaba de
vigilarlos**. La vía de cuantiles graduaba aquellas lecturas por debajo de grave
y la persistencia las descartaba.

**Corrección:** `exceeds_danger_limit()` se comprueba siempre. La línea base
personal sirve para detectar lo que es anormal **para ti**; no para rebajar lo
que es peligroso para cualquiera.

Con ello los seis escenarios se comportan como deben: nominal limpio, y cada
patología marcando su propio dominio.

### 14. Faltaba el tramo de esfuerzo en los límites de peligro

Tres sujetos **sanos** quedaban marcados por pulsos de 128, 191 y 192 lpm. En un
adulto de 29 años la frecuencia máxima teórica ronda los 190: eso es esfuerzo
máximo, no una urgencia.

Había dos tramos —reposo (110) y general (150)— y faltaba el tercero. Con un
único límite de 150 para todo lo que no fuera reposo, cualquier sesión de
ejercicio disparaba la alarma. Añadido `exertion_critical_high = 200`.

Sanos marcados: 3/22 → **2/22**. Falsa alarma por lectura: 0,32 % → **0,23 %**.

### 15. Un dato inválido no es un dato extremo

Encontrado cambiando de ángulo: en vez de seguir puliendo contra MMASH —con
riesgo de adaptar el motor a 22 sujetos— se probó el motor con **entradas
degeneradas**. Nueve casos se comportaron bien (serie constante, lista vacía,
hueco de 200 días, marcas de tiempo duplicadas, orden invertido, todo de baja
confianza, rampa monótona, pulso sostenido de 195). Dos no.

**NaN atravesaba el sistema en silencio.** Cero hallazgos, nivel nominal. Toda
comparación con NaN es falsa, así que ni los cuantiles ni los límites de peligro
lo veían: la lectura desaparecía sin dejar rastro **ni alerta**. En
monitorización clínica, un dato que se esfuma sin avisar es peor que uno que da
error.

**Y un valor físicamente imposible se reportaba como urgencia clínica.** Un pulso
de −50 lpm cruzaba el límite de peligro y salía como hallazgo grave. Pero −50 lpm
no es bradicardia: es un sensor roto. Mandar a la tripulación a investigar un
problema fisiológico inexistente es justo el tipo de alarma que destruye la
confianza en el sistema.

**Corrección:** tres tramos distintos, y la diferencia entre ellos importa.

| Tramo | Qué significa | Qué hace el sistema |
|---|---|---|
| Rango de referencia | Así es la gente sana | Contexto, no alarma |
| Límite de peligro | Esto es peligroso | Alarma grave |
| **Límite físico** | **Esto no puede pasar** | **Rechaza el dato** |

`VitalObservation` rechaza en la frontera los valores no finitos y los
físicamente imposibles, con el mensaje diciendo cuál de las dos cosas es. Una
prueba comprueba además que los límites de peligro caen **dentro** del rango
físico — si no, serían inalcanzables.

Dos indicadores admiten valores negativos y están declarados con su razón:
`circadian-shift` (un desfase va en cualquier sentido) y `orthostatic-drop` (hay
quien sube la tensión al levantarse). Cualquier otro que los admita hace fallar
la suite.

### 16. Sin base personal, solo peligro absoluto

**1497 de 1831 hallazgos leves** venían del rango poblacional — el 58 % de todas
las alarmas. Comparar a alguien que no conoces contra el punto medio de una tabla
es estadística, no medicina.

Regla nueva: mientras no haya base personal, solo se avisa si el valor cruza un
**límite de peligro fisiológico**. Siete indicadores tienen uno defendible; los
otros diecisiete **no alertan sin base personal** — inventar un umbral para
rellenar sería volver al problema.

#### El fallo que esto provocó, y que solo la sensibilidad detectó

Al aplicar la regla, **el episodio agudo pasó de 20/20 a 0/20 sujetos
detectados** mientras la falsa alarma "mejoraba" a 5,27 %. Diagnóstico: el 100 %
de sus lecturas caían sin base personal, con valores de 111-145 lpm contra un
límite crítico de 150.

**La tasa de falsa alarma sola habría presentado esto como un éxito rotundo.**

**Corrección:** los límites de peligro dependen del estado. 145 lpm corriendo es
fisiología normal; en reposo es un hallazgo. Un estado desconocido se trata como
*no reposo*, que es lo conservador frente a la falsa alarma.


### 17. El dataset traía dos sujetos con el eje temporal roto

`user_8` y `user_9` abarcaban **31,5 días con un hueco de 710 horas**, frente a
los 1,36-1,45 días de los otros veinte. Causa: MMASH etiqueta el día como `1` o
`2`, y en esos dos sujetos vale **`-29`**. Tomado al pie de la letra, coloca la
segunda mitad del registro treinta días en el pasado.

Que `-29` es el día 2 está **medido**, no supuesto. Las franjas horarias
coinciden exactamente con las de un sujeto sano:

| sujeto | `day=1` | segundo día |
|---|---|---|
| user_15 (sano) | 09:30 → 23:59 | `day=2`: 00:00 → 10:59 |
| user_8 (roto) | 09:53 → 23:59 | `day=-29`: 00:00 → 09:08 |
| user_9 (roto) | 10:06 → 23:59 | `day=-29`: 00:00 → 09:24 |

**Lo que esto contaminaba.** La ventana móvil de 14 días descartaba medio
registro de esos sujetos; el ajuste de tendencia cruzaba un vacío de un mes; y la
inyección de deriva de 15 lpm/día acumulaba sobre treinta días falsos hasta
**370 lpm**. Los dos sujetos llevaban alimentando la tasa de falsa alarma
publicada desde la primera medición.

**Cómo salió a la luz:** no lo detectó nadie leyendo la salida. Lo detectó el
límite de posibilidad física al rechazar los 370 lpm. Sin esa comprobación en la
frontera, el defecto seguiría dentro y en silencio.

**Lo que de verdad generaliza** no es arreglar `-29`. Es que un dato absurdo
recorrió el sistema entero sin que nada protestara. Ahora el cargador rechaza
cualquier sujeto cuyo registro supere los 3 días, porque el protocolo de MMASH
dura 36 horas: si el dataset trae otro defecto que no he encontrado, para ahí en
vez de entrar en una cifra que luego se presenta como evidencia.

---

### 18. Un deterioro inyectado seguía siendo fisiología imposible

La inyección sumaba un desplazamiento fijo sin mirar dónde caía el resultado:
`-30 ms` de SDNN sobre un sujeto cuya SDNN real ya era 29,46 ms daba **-0,54 ms**.

No es cosmético. **Si la inyección fabrica valores imposibles, parte de la
sensibilidad medida se ganó detectando disparates**, no deterioro clínico: el
número publicado quedaba inflado por lecturas que ningún sensor produce.

El valor inyectado se acota ahora al rango físicamente posible, y **cuántas
lecturas chocaron con el techo queda contado**, porque un deterioro que topa en
masa ya no es el que dice su etiqueta. Medido sobre MMASH: los tres escenarios de
pulso acotan **0 lecturas**; el colapso de HRV acota **90 de 3322 (2,71 %)**,
sujetos cuya SDNN real ya estaba por debajo de 30 ms.

La medida se vuelve más dura, no más benévola.

---

### 19. Los controles de falsa alarma estaban apagados por el camino real

El más grave de esta tanda. `ObservationRow` no tenía columnas para **contexto**
ni **confianza**, y `query()` reconstruía sin ellas. Toda lectura que pasaba por
la base volvía como `unknown / 1.0`.

Consecuencia directa: los dos controles que más bajaron la falsa alarma —la
estratificación por contexto y el tope de severidad por baja confianza— **no
funcionaban en el sistema desplegado**. Funcionaban en las listas en memoria del
simulador y del banco de validación, que es donde se medían.

> Las cifras se medían sobre un motor que el sistema desplegado no ejecutaba.

El asiento de auditoría tenía el mismo agujero: `_to_payload` omitía ambos. La
confianza cambia cómo se interpreta la lectura, así que es registro clínico, no
metadato de transporte; sin ella no se puede reproducir la decisión que se tomó,
que es justo lo que 21 CFR 11.10(e) exige poder hacer.

---

### 20. El simulador no tenía ritmo diario, y eso lo hacía más fácil que la realidad

3520 observaciones generadas, **todas con contexto `unknown`**, y valores que no
dependían de la hora. Dos consecuencias:

1. La estratificación por contexto **nunca se ejercitaba** con datos de duración
   de misión. Solo MMASH la probaba, y MMASH dura 36 horas.
2. Un generador sin ciclo diario es más benigno que un cuerpo real: le falta
   justo la fuente de variación que produjo la tendencia espuria de −92,9 lpm por
   semana (hallazgo 9).

**Los multiplicadores están medidos, no citados.** Salen de MMASH, 22 sujetos
humanos reales, tomando la mediana por sujeto de la razón entre contextos y luego
la mediana entre sujetos:

| razón | medido en MMASH | rango por sujeto | reproducido por el simulador |
|---|---|---|---|
| pulso sueño/reposo | **0,765** | 0,676 – 0,884 (n = 21) | 0,773 |
| pulso actividad/reposo | **1,117** | — | 1,111 |

Para la HRV la razón sueño/reposo va de **0,58 a 2,85** según el sujeto: no hay
efecto consistente que modelar, y fabricar uno sería inventar fisiología. Por eso
solo se modula el pulso. **Lo que no está medido, no se simula.**

---

### 21. La API aceptaba o reventaba con entrada degradada

Nueve formas de entrada mal formada, tres modos de fallo distintos:

- un valor físicamente imposible salía como **HTTP 500**: quien teclea 5000 de
  pulso recibía "error del servidor" en vez de "eso no es posible";
- `context` y `confidence` **no existían** en el modelo de entrada, así que
  Pydantic los descartaba en silencio: toda lectura entraba como contexto
  desconocido y confianza plena, y la estratificación era inalcanzable desde ahí;
- **`subject` vacío se aceptaba** y la lectura se archivaba bajo un tripulante
  inexistente: no aparecía en el estado de nadie y no daba ningún error.

Una constante vital que desaparece sin protestar es el peor fallo posible en un
sistema de vigilancia. Los nueve casos devuelven ahora **422**, y el modelo
prohíbe campos extra para que un nombre mal escrito sea un error y no una pérdida
muda.

---

### 22. Nada impedía mezclar a dos tripulantes en un mismo informe

`Deviation` no llevaba el sujeto. Pasar por error lecturas de dos personas al
motor de riesgo producía un informe **bien formado, plausible y clínicamente
falso**, que atribuía a una los hallazgos de la otra. No hay forma de detectarlo
leyendo la salida.

Hoy la API filtra por sujeto y no ocurría, pero EMMA vigila a una **tripulación**.
`Deviation` lleva ahora el sujeto y `assess()` rechaza cualquier lectura que no
sea de la persona del informe.


### 23. "Actual" se decidía por valor, no por tiempo

El estado de tripulación seleccionaba las lecturas recientes así:

```python
recent = {(obs.key, obs.value) for obs in observations if obs.effective >= cutoff}
current = [dev for dev in deviations if (dev.key, dev.value) in recent]
```

Emparejar por `(clave, valor)` es ambiguo, y las cifras se repiten mucho: **960
lecturas de pulso toman solo 36 valores distintos**, y el más frecuente sale 99
veces. Una desviación de hace semanas contaba como actual en cuanto su valor
reaparecía.

Medido sobre 40 días de escenario nominal: **2582 desviaciones dadas por
actuales frente a 1078 lecturas realmente en ventana** — un inflado de 2,4×. Con
pulsos enteros de un wearable real sería peor.

Eso contamina numerador y denominador de la persistencia **a la vez**, y la
persistencia es el control central contra la fatiga de alarma. `Deviation` lleva
ahora su momento y la selección es temporal: 1078 de 1078, inflado ×1,00.

**El mismo emparejamiento seguía en la sensibilidad** (2026-11-11, lote «lógica»).
`measure_sensitivity` decidía qué desviaciones eran de lecturas perturbadas por
`(clave, valor)`: una lectura sana, anterior al deterioro, marcada y con la misma
cifra que una perturbada contaba como acierto del deterioro. Ahora empareja por
`(clave, momento)`, como la tasa en reposo. Remedido sobre MMASH con los
parámetros de misión, las cifras **no cambian** (sostenida 21/22 sujetos y
223/3322 lecturas; progresiva 7/22 y 29/3322; agudo 20/22 y 211/518; HRV 3/22 y
10/3322; falsa alarma 0,18 %, en reposo 0,15 %): el fallo estaba latente, no
inflaba la cifra publicada. Lo prueba `tests/test_sensitivity_matching.py`.

---

### 24. Estratificar cuesta muestras, y eso se declara

Con el simulador emitiendo contexto, el uso de línea base personal **cae del
88 % al 55,3 %** en 40 días. No es una regresión: es el precio de estratificar.
El contexto de esfuerzo son el 8,3 % de las lecturas —unas 28 en la ventana de
14 días— y nunca llega a las 100 muestras mínimas, así que cae al camino
poblacional.

Y ese camino, desde el hallazgo 16, **solo alerta por límite de peligro
absoluto**. Es la degradación correcta: el sistema sabe menos del esfuerzo, así
que ahí solo avisa de lo inequívoco. Comprobado sobre 40 días de escenario sano:
**cero hallazgos por el camino poblacional**; los 15 con severidad (1,56 % de
960) vienen todos del camino de cuantiles personales, que es la tasa que esos
umbrales predicen.

Se consideró y se descartó respaldar en la base personal **sin estratificar**
cuando un contexto va escaso. Sería volver al hallazgo 5: comparar una lectura de
esfuerzo contra la media de todo el día la marca alta por definición.


### 25. La demo enseñaba la rama más débil del motor

`POST /api/simulate` traía `samples_per_day = 4` por defecto. Con eso, la ventana
móvil de 14 días reúne **56 lecturas frente a las 100** que exige `MIN_SAMPLES`,
y estratificadas por contexto muchas menos. Medido sobre 40 días:

| muestras/día | uso de base personal | escenario de arritmia |
|---|---|---|
| **4 (el que había)** | **0,0 %** | **no detectada** |
| 8 | 0,0 % | detectada |
| 12 | 45,0 % | no detectada |
| **24 (el nuevo)** | **55,3 %** | detectada |
| 48 | 80,0 % | detectada |

Con el valor anterior, **`/api/status` devolvía "nominal" sobre un tripulante con
arritmia**, y lo hacía apoyándose solo en límites de peligro absoluto. Quien
evaluara el sistema por su demo veía la rama más débil del motor. 24 muestras al
día es además lo realista: un wearable no mide cuatro veces al día.

#### Decir "nominal" sin decir sobre qué base

El defecto de fondo no era el número, era el silencio. Sin línea base personal
solo se comprueban límites de peligro absoluto, así que "nominal" significa **"no
ha cruzado nada grave"**, no **"está como siempre"**. Son dos afirmaciones muy
distintas, y el panel daba la segunda cuando solo podía sostener la primera.

`/api/status` publica ahora `personal_baseline_fraction` y un campo `basis` que
dice literalmente en qué se apoya el veredicto. Un panel clínico que afirma más
de lo que sabe es el mismo problema que las falsas alarmas, por el otro extremo.

### 26. La ráfaga de tres era una respuesta congelada, y corregirla costó tres intentos

La tabla del hallazgo 25 dejaba anotada una rareza: la arritmia se detectaba a 8
y a 24 muestras/día **y se perdía a 12**. Un motor que pierde un evento al
recibir más datos tiene algo frágil. A 12/día, la ventana actual reunía 25
lecturas de pulso con **2 graves**; a 24/día, 49 con 3. La red de seguridad del
hallazgo 10 exigía **tres, siempre**.

Ese «tres» era la respuesta para la ventana de MMASH, congelada. Con 25 lecturas
pedía demasiado; con las cientos o miles de lecturas de un wearable continuo, el
azar lo alcanza casi seguro. La corrección evidente —exigir el menor número de
lecturas graves que, dadas n, sea tan sorprendente como 3 en la ventana
validada— es correcta. Fijar sus parámetros no lo fue a la primera, ni a la
segunda.

#### Intento 1: α = 0,005 sobre un modelo de percentil, y la sensibilidad lo cazó

Se modeló cada lectura grave como un suceso del percentil 99,9 (p = 0,001 por
cola) y se tomó α = 0,005 razonando con una sola cola. Para el pulso, que
preocupa por las dos, la exigencia en la ventana de MMASH subía a **cuatro**:

| | k = 3 fijo | α = 0,005 | α = 0,02 | **final** |
|---|---|---|---|---|
| Falsa alarma por lectura | 0,2329 % | 0,2329 % | 0,2329 % | 0,2329 % |
| Sanos marcados | 2 / 22 | 2 / 22 | 2 / 22 | 2 / 22 |
| Taquicardia sostenida: marcado / escalado | 82 % / 73 % | **68 % / 59 %** | 77 % / 68 % | 82 % / 73 % |
| Episodio agudo: marcado / escalado | 77 % / 68 % | 73 % / 64 % | 77 % / 68 % | 77 % / 68 % |
| Taquicardia progresiva: marcado / escalado | 18 % / 9 % | 14 % / 5 % | 18 % / 9 % | 18 % / 9 % |

Ninguna ganancia en especificidad y una pérdida de sensibilidad que bajó la
taquicardia sostenida de su suelo del 75 %: `test_sensitivity_does_not_regress`
falló. Es exactamente lo que esa prueba existe para impedir.

#### Intento 2: α = 0,02, con una cifra que nadie había medido

α se ancló al punto validado —k = 3 en «n = 250-280», la cifra que traía el
comentario de la regla antigua—. Instrumentando la función sobre MMASH, las
ventanas reales van de **249 a 303** lecturas. Las de 285-303 seguían exigiendo
4, y la taquicardia sostenida perdía un sujeto (82 % → 77 %). Pasaba el suelo;
seguía siendo una pérdida sin contrapartida.

#### Intento 3: el suceso que se cuenta no era el que se modelaba

Una revisión estadística independiente encontró el fallo de fondo: **en ningún
dato disponible ocurre una sola lectura grave por percentil**. Declarar «grave»
por cuantil exige 1000 muestras de base; la mayor base de MMASH tiene 116, y la
del simulador a 24/día, 336. Todas las lecturas graves medidas son **cruces de
límite de peligro** —en MMASH, 30 de 6132 lecturas, todas de pulso—, y su tasa
en gente sana (0,49 % por lectura) es cinco veces la que suponía el modelo.
*(Esa tasa bajó a 0,3425 % con el hallazgo 28, y el ancla se recalculó para
conservar el mismo comportamiento: ver allí.)*

La regla final escala con esa **tasa medida** (`_HEALTHY_SEVERE_RATE`), y el
ancla (`_BURST_SURPRISE`) se elige dentro del intervalo que reproduce k = 3 en
**todas** las ventanas medidas de MMASH. Una prueba externa vuelve a medir la
tasa y falla si se desvía, o si aparece un solo suceso de percentil en la
validación. Resultado: **las métricas de MMASH son idénticas a las de la constante 3 en los dos ejes** (última columna de la tabla).

Con ello la detección deja de depender del muestreo: arritmia detectada y sano
limpio a 4, 8, 12 y 24 muestras/día (`test_detection_does_not_depend_on_sampling_rate`).

Una observación que da confianza en la forma de la regla: como el ancla fija lo
validado, la tabla de umbrales **apenas depende de la tasa supuesta**. Con
p = 0,002 y con p = 0,0049 sale el mismo k para toda ventana de 8 a 576
lecturas. Lo validado es «tres en 249-303»; lo demás es la forma de extrapolar,
y esa forma es robusta.

#### Las ventanas cortas, contrastadas contra fisiología real

Bajar a 2 en ventanas cortas es lo que recupera la arritmia a 4 y 12
muestras/día, y lo único que podría costar falsas alarmas. Se contrastó
submuestreando el pulso real de MMASH a cadencia de wearable modesto:

| lecturas de pulso/día | sanos marcados, k = 3 fijo | sanos marcados, regla final |
|---|---|---|
| 12 | 0 / 22 | 0 / 22 |
| 24 | 0 / 22 | 0 / 22 |
| 48 | 1 / 22 | 1 / 22 |
| 96 | 1 / 22 | 1 / 22 |

Ninguna falsa alarma añadida. Y el otro eje, con los mismos deterioros
inyectados sobre ese pulso submuestreado (dominio marcado):

| lecturas de pulso/día | taquicardia sostenida | episodio agudo |
|---|---|---|
| 12 | 0 % → 0 % | 0 % → 0 % |
| 24 | 9 % → **18 %** | 0 % → **27 %** |
| 48 | 27 % → **41 %** | 36 % → **59 %** |

*(k = 3 fijo → regla final.)* En ventana corta la regla nueva es ganancia sin
coste: la sensibilidad sube y los sanos marcados no se mueven. Los dos ejes
quedan fijados en `test_short_windows_do_not_alarm_more_than_the_validated_one`
y `test_short_window_sensitivity_does_not_regress`.

**La cifra incómoda:** con 12 lecturas de pulso al día **no se marca ningún
deterioro**, con ninguna de las dos reglas; con 24, menos de uno de cada tres.
Un wearable que mide poco deja a EMMA casi sin vista, y eso no lo arregla
ninguna regla de ráfaga: es la razón por la que la demo usa 24/día como mínimo
y por la que el panel declara sobre qué base emite su veredicto (hallazgo 25).

#### Un fallo que ningún dataset habría mostrado

La revisión de código encontró que el cálculo desbordaba el float a partir de
~22 000 lecturas (`math.comb`). Un wearable BLE a 1 Hz llega ahí en unas 6 h de
ventana: `/api/status` habría respondido 500 justo con el dispositivo que más
datos da. Ahora la distribución se acumula en escala logarítmica —mismos
umbrales de 1 a 3000 lecturas, un millón en 0,6 ms— y lo cubre
`test_burst_threshold_survives_a_wearable_window`.

**Límites declarados:**

- Los cruces se concentran: un sujeto aporta 18 de los 30 y 14 de 22 no tienen
  ninguno. La binomial con la tasa agregada da la forma de la escala, no una
  probabilidad calibrada; por eso el ancla vale 0,25 y **no es una tasa de
  falsa alarma**. La real se mide —2 de 22 sanos— y la vigila la validación.
- La tasa es del pulso, el único indicador de MMASH con cruces. Aplicarla a los
  demás es un supuesto.
- En ventanas cortas, donde la regla baja a 2, los dos ejes están contrastados
  sobre pulso real **submuestreado**, que no es lo mismo que un wearable real de
  baja cadencia: la agregación cada 5 min de MMASH ya suaviza los picos.
- **La vía de percentil sigue sin validar.** Solo se activa con wearables de
  alta cadencia. La revisión estimó que con bases finitas la tasa real por cola
  en el corte p99,9 es ≈ 0,001 + 1/(muestras + 1) —el doble con 1000 muestras—
  y que la autocorrelación de lecturas consecutivas multiplica las ráfagas
  falsas. Validarla requiere datos de wearable de varios días.

### 27. La tendencia preguntaba si la pendiente era distinta de cero, no si importaba

*Medido sobre el simulador, no sobre MMASH: con 36 h de datos la vía de
tendencia está desactivada (`MIN_SPAN_DAYS`). Es la única fuente de misiones
largas disponible, y sus límites se declaran abajo.*

Una tasa de falsa alarma por lectura no dice cuánto molesta el sistema.
`/api/status` se reevalúa sin parar sobre una ventana de dos días y 24
indicadores a la vez, así que la cifra que sufre una tripulación es **cuántas
alertas recibe un tripulante sano al mes**. Se midió recorriendo el camino
desplegado día a día, desde el día 14 hasta el 70, en el escenario nominal:

| muestras/día | tripulantes | días en CONCERN | días en WATCH | episodios de WATCH por tripulante-mes |
|---|---|---|---|---|
| 24 | 50 | **0** | 7,4 % | 0,74 |
| 96 | 20 | **0** | 2,3 % | 0,19 |

Ninguna alerta seria. Pero **todo** el WATCH salía de la vía de tendencia.

#### Un intento que NO rindió: acortar la ventana

La hipótesis era que la recta sobre toda la misión seguía viendo derivas ya
estabilizadas. Se probaron ventanas más cortas (10 tripulantes por escenario,
evaluación diaria):

| ventana de tendencia | días del nominal con un dominio marcado | detección de los 5 deterioros |
|---|---|---|
| toda la historia | 12,0 % | 10/10, día 14 |
| 28 días | 12,9 % | igual |
| 21 días | 13,8 % | igual |
| 14 días | **28,9 %** | igual |

Peor en especificidad y sin ganancia en detección. Sola, no se aplicó: la ventana
de 21 días entró después, junto con el cambio de contraste que sigue.

#### Por qué, según una revisión estadística independiente

- **Las pendientes de ruido crecen al acortar la ventana** (como W^-3/2), y el
  umbral de relevancia es fijo: con 14 días, el ruido lo supera con facilidad.
- **Comparaciones múltiples:** 66 estratos (indicador × contexto) por
  evaluación, y de cada indicador se queda el contexto más preocupante.
- **Derivas reales por debajo del umbral:** el nominal tiene cortisol y caída
  ortostática al 67 % del umbral. El contraste pedía que la pendiente fuera
  *distinta de cero* y que su estimación *puntual* superase el umbral; al ruido
  solo le faltaba completar el resto.
- **Y un fallo que ningún escenario podía mostrar**, porque todos arrancan el
  día 0: una deriva que empieza a mitad de misión se diluye en la recta de toda
  la historia. Verificado con el código del repo —deriva de pulso desde el día
  35, escalada por el ritmo circadiano como la produce el simulador, 20
  tripulantes—:

| deriva | toda la historia, contraste contra 0 | 21 días, contraste contra el umbral | marcas antes del inicio |
|---|---|---|---|
| 1× umbral | **0/20** | **20/20**, 16 días | 0 / 0 |
| 1,5× | 19/20, 31 días | 20/20, 12 días | 0 / 0 |
| 2× | 20/20, 22 días | 20/20, **10 días** | 0 / 0 |

*Horizonte: 34 días tras el inicio (día 69). La primera versión de esta tabla
daba 7/20 y 25 días para la regla antigua: se emuló mezclando piezas nuevas —el
desempate entre contextos ya cambiado— con las viejas. Una revisión de código lo
cazó; con la regla antigua reproducida entera, 19/20 a 1,5× y 22 días a 2×. A
1× el umbral, la regla antigua sí era ciega; por encima, lenta.*

#### Corrección: preguntar si la deriva supera, con confianza, lo relevante

`trend.py` contrasta ahora |pendiente| − umbral contra su error típico (mismo
|t| ≥ 2), en una ventana de 21 días (`TREND_WINDOW`). La pregunta pasa de
«¿la recta de la misión tiene pendiente?» a «¿está derivando **ahora**, con
confianza, **más de lo clínicamente relevante**?».

| | antes | ahora |
|---|---|---|
| Días en WATCH, nominal (50 tripulantes), **sin factor de aislamiento** | 7,43 % | **0,39 %** |
| Episodios de WATCH por tripulante-mes | 0,74 | **0,06** |
| Días en CONCERN | 0 | 0 |
| Deriva tardía al umbral | nunca | 16 días |
| Escenarios de deterioro detectados | 10/10 el día 14 | 10/10; el desacondicionamiento, 7 el día 14 y 3 los días 15, 17 y 19 |
| Días con el desacondicionamiento marcado | 100 % | **93 %** |

Lo que queda de WATCH **no** es una adaptación en curso, como se escribió al
principio: la rampa circadiana del simulador termina el día 14 y la evaluación
empieza ese mismo día. Es la cola de una rampa ya terminada, más ruido: el
defecto que se describe abajo.

**El retraso del desacondicionamiento es un coste del contraste nuevo**, no de
la ventana: con la regla antigua, 10 de 10 el día 14; con el contraste contra el
umbral y cualquier ventana, 3 de 10 se retrasan 1, 3 y 5 días. Se declara.

**Por qué 21 días y no 28.** Con 28, el desacondicionamiento quedaría marcado el
98 % de los días, pero la deriva tardía tardaría 3-4 días más en verse (20, 15
y 13 días a 1×, 1,5× y 2× el umbral). En el nominal no hay diferencia. Se elige
ver antes lo nuevo: con 22 minutos de retardo, es el problema que la tripulación
no puede delegar. El 93 % se declara como el precio.

**El coste, por construcción:** una deriva por debajo del umbral ya no se
marca. La SDNN del escenario de desacondicionamiento deriva 5,45 ms/semana
frente a un umbral de 5,62 —el 97 %— y deja de marcarse. La prueba que la
exigía pasaba solo cuando el ruido empujaba la estimación por encima: con 36 de
60 semillas.

#### Con el retardo de Marte, y un segundo intento que NO rindió

Todo lo anterior se midió **sin factor de aislamiento**. Una revisión de código
lo señaló: con el retardo de Marte (22 min de ida), `isolation_factor` sube una
sola tendencia por encima del umbral de WATCH. Medido en el nominal:

| régimen | días 14-69 en WATCH | días 14-25 | días 26-69 |
|---|---|---|---|
| sin retardo | 0,4 % | 1,8 % | **0,00 %** |
| retardo de Marte | **13,9 %** | 59 % | **1,55 %** |

No es un goteo crónico: es **un episodio al principio de la misión**. La
adaptación circadiana de las dos primeras semanas es real —deriva al doble del
umbral— y se reporta con hasta 11 días de retraso, mientras la ventana contiene
la rampa. Pasado el día 25, el régimen estable con retardo de Marte es del
1,55 % de los días.

Se intentó quitar esa cola con un veto: descartar la tendencia si el tercio más
reciente de la ventana ya no deriva. Se probaron 15 variantes (mitad, tercio,
bisagra fija o estimada, varios umbrales). La mejor bajaba el nominal de Marte
del 13,9 % al 1,6 %, pero **vetaba derivas reales cuando hay pocos datos**: a 4
muestras/día descartaba el pulso del desacondicionamiento, que seguía subiendo.
Exigiendo al tercio potencia para ver al menos una deriva del umbral, dejaba de
vetar derivas reales, pero también dejaba de vetar la cola: nominal de Marte en
14,2 %, sin cambio. En `circadian-shift`, con 7 días de datos, ni una deriva del
tamaño del umbral daría |t| ≥ 2: con estos datos, **la cola de una rampa y una
deriva real al umbral no se pueden distinguir**. No se aplicó. Entre una
alerta leve con retraso sobre algo que sí pasó y perder una deriva real, se
prefiere lo primero.

#### Decisión: una deriva confirmada llega sola a la tripulación

La misma revisión destapó algo mayor. Una tendencia pesaba 15 puntos
(`risk._TREND_POINTS`), con un comentario que decía «como una desviación
moderada» —que son 25—, y WATCH empieza en 20. Así que **sin retardo de
comunicaciones una tendencia sola no llegaba nunca a la tripulación**: la
deriva tardía que la vía de tendencia detectaba en 20 de 20 casos marcaba el
dominio en 1 de 10. Solo el factor de aislamiento de Marte la hacía visible.

Medido sin retardo, antes de decidir:

| `_TREND_POINTS` | nominal en WATCH, días 14-25 / 26-69 | deriva tardía visible | desacondicionamiento marcado |
|---|---|---|---|
| 15 | 0,8 % / 0,00 % | 1 de 10 | 93 % |
| **20** | 62,5 % / 1,36 % | **10/10** a 16, 12 y 9 días | **100 %** |
| 25 | igual que 20 | igual que 20 | 100 % |

Se decidió **20**: el mínimo con el que una deriva confirmada se ve, en
cualquier régimen. El coste se acepta y se declara: la adaptación circadiana
real de las semanas 2-3 sale como WATCH también en órbita baja, igual que ya
salía con el retardo de Marte, y en régimen estable queda un 1,4 % de días en
WATCH en tripulantes sanos. **CONCERN sigue en 0.** Las cifras de «0,39 %» de
la tabla anterior eran el estado intermedio, con 15.

Al subirlo aparecieron dos marcas nuevas en los escenarios. Se analizaron una
por una:

- **SPE marca también el dominio inmune.** El escenario modela a propósito una
  subida de la carga de síntomas (0,3 por semana, cuatro veces el umbral), que
  el catálogo asigna a ese dominio. Antes existía y no se veía. Es detección.
- **El desacondicionamiento marcaba el dominio óseo** por la caída del
  ejercicio resistivo. `exercise-minutes` es la única guía del catálogo, y su
  umbral de relevancia salía de una recomendación: exactamente lo que el
  hallazgo 2 prohibió como umbral de alarma. La regla se aplicaba a las
  desviaciones y no a las tendencias; con 15 puntos no se notaba. Ahora la
  tendencia de una guía se describe y no alerta.

**Lo que no se arregló del todo:** una deriva ya estabilizada se sigue marcando
mientras la ventana contenga su rampa. El desfase circadiano nominal se asienta
el día 14; antes se marcaba hasta el día 28 (mediana de 30 tripulantes), ahora
hasta el 22. Y un tripulante de 30 vuelve a marcarlo el día 59: ruido que superó
el umbral.

**Límites declarados:**

- El ruido del simulador es independiente por construcción. El de un wearable
  real no: en el pulso de MMASH a 5 minutos la revisión estimó que la
  autocorrelación infla el t unas 2,2 veces. El contraste contra el umbral lo
  amortigua —un error típico subestimado rebaja la exigencia a «umbral + 0,9
  errores», no a «0,9 errores»—, pero **no está validado con un wearable real de
  varios días**.
- Todo lo anterior es simulador. Un registro real de semanas con derivas
  documentadas sigue siendo el punto abierto 6.


### 28. Cero pasos con el aparato quitado no es reposo, es silencio

De las 43 lecturas que quedaban marcadas sobre sujetos sanos, **20 eran de un
solo sujeto**, `user_15`: dos horas seguidas con el pulso entre 112 y 192 lpm,
comparadas contra el límite de peligro **en reposo**, 110 lpm. La etiqueta de
reposo no venía del diario —que callaba—, sino de la inferencia por
acelerometría: menos de 10 pasos por minuto se leía como quietud.

Lo que dice el resto del registro en esa franja:

| señal | valor |
|---|---|
| Pasos por minuto | 0 |
| Magnitud vectorial de aceleración | 0 (mediana en actividad declarada: 1799) |
| Inclinómetro | **`Off` en todos los minutos** |
| Intervalos R-R | mediana 0,312 s, **máximo 21,8 s** |
| Latidos plausibles por ventana | 0,58-0,85 (mediana del sujeto: 1,00) |

El inclinómetro marca `Off` cuando no detecta orientación: **el acelerómetro no
está puesto**. La lectura más plausible es un actígrafo fuera del cuerpo
mientras la banda de pecho sigue midiendo, con los artefactos de movimiento que
eso trae. Sus cero pasos no eran quietud: eran ausencia de medida.

Y ese es el error: **leer una ausencia de evidencia como evidencia**, el mismo
patrón que el hallazgo 2 corrigió con las guías clínicas. El motor ya lo hacía
bien —un estado desconocido se compara contra 150 lpm, no contra 110—; era el
cargador el que convertía el silencio en reposo antes de que el motor lo viera.

**Corrección:** si el acelerómetro declara que no lo llevan puesto, el contexto
inferido es **desconocido**. Afecta a 170 lecturas de pulso de los 22 sujetos
(2,8 %), de las cuales 21 son de `user_15`.

| | antes | después |
|---|---|---|
| Falsa alarma por lectura | 0,2329 % | **0,1842 %** |
| En reposo | 0,2103 % | **0,1472 %** |
| Sanos marcados | 2 / 22 | **1 / 22** |
| Taquicardia sostenida: detectado / marcado / escalado | 95 % / 82 % / 73 % | 95 % / 82 % / **77 %** |
| Episodio agudo | 91 % / 77 % / 68 % | 91 % / 77 % / **73 %** |
| Taquicardia progresiva | 32 % / 18 % / 9 % | 32 % / **14 %** / 9 % |
| Colapso de HRV | 14 % / 9 % / 0 % | 14 % / **5 %** / 0 % |

**Los dos ejes mejoran donde el motor es fuerte**: menos falsas alarmas y más
escalado en los dos deterioros que MMASH puede validar. El marcado baja en los
dos débiles, y la explicación es incómoda pero honesta: **parte de su marcado
venía prestado del ruido que se acaba de quitar**. Un sujeto que ya alertaba en
falso cuenta como «marcado» en cuanto se le inyecta cualquier cosa.

**Lo que queda.** `user_15` sigue siendo el único sujeto marcado: incluso con el
límite de desconocido, cinco de sus lecturas superan los 150 lpm. Con el
acelerómetro fuera del cuerpo no hay forma de saber si eso fue ejercicio o no, y
el sistema hace lo correcto al no darlo por normal.

#### El segundo mecanismo: HRV sin mirar la actividad — medido y NO aplicado

De las 34 lecturas que quedan marcadas, **8 son caídas de HRV en contexto
`active` o `meal`**: RMSSD de 4 a 8,8 ms y SDNN de 17 a 33 ms en `user_17` y
`user_21`. Que la HRV se hunda haciendo esfuerzo o digiriendo es fisiología
normal, y el motor las compara contra una base de reposo porque `meal` y `work`
se agrupan con `rest` (`Context.family`, que existe para no fragmentar la
muestra: al pasar de tres estados a cinco, la detección del episodio agudo cayó
del 90 % al 20 %).

Lo evidente es interpretar la HRV solo en reposo y sueño, que es como se mide en
clínica. Medido antes de aplicarlo:

| | actual | HRV solo en reposo/sueño |
|---|---|---|
| Falsa alarma por lectura | 0,1842 % | **0,2122 %** |
| En reposo | 0,1472 % | 0,1940 % |
| Sanos marcados | 1 / 22 | 1 / 22 |
| Colapso de HRV: detectado | 13,6 % | **0,0 %** |

**No se aplicó.** Quita 8 lecturas leves que nunca escalan —los sanos marcados
no se mueven—, **empeora** la tasa publicada porque elimina más denominador que
numerador, y **apaga del todo** la detección del colapso de HRV: la mitad de las
lecturas del indicador dejan de mirarse, y con ellas las del deterioro
inyectado. Cambiar un residuo cosmético por una capacidad de detección real es
justo lo que la invariante 5 existe para impedir.

*(El primer prototipo de esta medición no cambió ni una cifra: parcheaba
`BaselineEngine.evaluate`, que la vía de ventana móvil no usa. Que un prototipo
dé exactamente los mismos números es motivo de sospecha, no de alivio.)*

#### En avisos, que es como se sufren

Una tasa por lectura no dice cuánto molesta el sistema: un sensor que muestree el
doble de rápido duplica las lecturas marcadas sin producir un solo aviso más.
Agrupadas por sujeto e indicador con corte de 30 minutos:

| | antes | después |
|---|---|---|
| Lecturas marcadas | 43 | **34** |
| Episodios | 17 | **16** |
| Episodios por tripulante-semana | 3,86 | **3,63** |

Queda fijado en `test_alerts_per_crew_week_does_not_regress`.

#### Lo cazó la prueba que vigila la tasa, no una revisión

La regla de ráfaga (hallazgo 26) escala con la tasa de lecturas graves **medida
en sanos**, y esa tasa acababa de cambiar: sin las lecturas mal etiquetadas pasa
del **0,49 % al 0,3425 %**. `test_burst_rule_rate_is_what_healthy_people_produce`
falló en la misma corrida que validaba el arreglo. Es exactamente para lo que se
escribió: la constante sigue a los datos.

El ancla se recalculó para conservar el **comportamiento** validado —tres
lecturas graves en la ventana de MMASH, dos en las cortas— y no el número: el
intervalo admisible pasa de [18,6 %, 34,4 %) a [8,6 %, 20,8 %), y
`_BURST_SURPRISE` de 0,25 a 0,15.

### 29. El respaldo de familia deja fuera el reposo — medido con cobertura de la hora, sin adoptar

**Decisión del usuario (2026-10-23): no se adopta.** El motor sigue como en el hallazgo 28
(`reglas@faf6e60fc2fd3f12` en la regla de la línea base): ni la variante A ni la B entran, y los
techos y suelos de prueba siguen como estaban. Lo que entra es la lectura: este hallazgo, las fichas
de la literatura y de los conjuntos de varias semanas (`validation.mmash.FAMILY_BASELINE_LITERATURE`
y `MULTI_WEEK_CANDIDATES`, que no deciden nada). El código de las variantes, con sus pruebas y sus
campañas de mutantes, queda en la rama `worktree-agent-a13145213e51ba902`, para decidirlo cuando se
mida con un conjunto de varias semanas. Lo que sigue cuenta lo medido en esa rama.

*(2026-10-22, decimoquinta ronda, unidad D16. Decisión del usuario: corregir solo esto, con las dos
métricas medidas antes y después; después, exigir cobertura de la hora antes de juntar. Ningún techo
ni suelo de prueba se ha tocado. **Con la cobertura, la prueba de sensibilidad falla en el colapso de
HRV (9,1 % contra un suelo de 10 %): pendiente de decisión del usuario.**)*

`Context.family` dice que un estado sin lecturas suficientes se compara «contra el grupo al que
pertenece». `evaluate_rolling` no lo hacía: la familia juntaba solo las lecturas cuyo estado
**difiere** de su familia, así que el grupo de reposo eran trabajo y comida, sin reposo. Una lectura
de trabajo con 250 de reposo y 10 de trabajo en la ventana caía al rango poblacional con 10; una de
reposo con pocas propias se juzgaba contra trabajo y comida, sin las suyas. Lo encontró la
decimocuarta ronda (`compliance/hmi-state-of-the-art.md` §5.34.2) al enseñar de dónde sale cada base.

**Corrección.** `baseline.FAMILY_FALLBACK` dice de qué otros estados toma lecturas una base que no
llega a establecerse (reposo, trabajo y comida, cada uno de los otros dos; sueño, actividad y
desconocido, de nadie), derivado de `Context.family`. La base de respaldo es la del estado exacto
**más** la de esos estados, con la misma ventana, el mismo desfase y sin las de baja confianza. La
regla entra en la huella: `rules_version` pasa de `reglas@faf6e60fc2fd3f12` a
`reglas@52650e59430814fe` (sin los cambios de otras unidades de la ronda). `MIN_SAMPLES` no se toca.

| MMASH, 22 sujetos, parámetros de misión | antes | después |
|---|---|---|
| Falsa alarma por lectura | 0,1842 % (34 de 18 460) | **0,2329 %** (43) |
| En reposo | 0,1472 % | **0,2103 %** |
| Episodios por tripulante-semana | 3,63 (16) | **4,31** (19) |
| Sanos marcados | 1 / 22 | 1 / 22 |
| Lecturas graves de pulso | 0,3425 %, todas por límite | igual |
| Taquicardia sostenida: detectado / marcado / escalado | 95,5 / 81,8 / 77,3 % | igual |
| Episodio agudo | 90,9 / 77,3 / 72,7 % | igual |
| Taquicardia progresiva | 31,8 / 13,6 / 9,1 % | igual |
| Colapso de HRV | 13,6 / 4,5 / 0,0 % | **18,2** / 4,5 / 0,0 % |

Con la ventana corta (4 h / 30 min) y con el pulso submuestreado a 12, 24 y 48 lecturas/día no cambia
nada salvo el colapso de HRV detectado a 48/día (3 → 4 de 22): con esas ventanas ninguna lectura
llega a base personal. En el simulador, nada: emite sueño, reposo y actividad, y el reposo no tiene
con quién compartir familia. Los 36 casos del veredicto (9 escenarios × 4 tripulantes) son idénticos.

**De dónde salen las 9 lecturas nuevas.** El arreglo lleva 54 lecturas (18 instantes × pulso, RMSSD
y SDNN) del rango poblacional a una base personal de 102-110 lecturas, justo por encima del mínimo
de 100. Nueve quedan leves por percentil, en dos franjas:

- `user_14`, 08:35-08:50 del segundo día, **reposo justo después de actividad** (123 lpm a las
  08:10): pulso 103-106 lpm contra una mediana de 73,6 y un p99 de 91,5; RMSSD de 3 a 16 ms. Base:
  77 de reposo, 22 de trabajo y 3 de comida.
- `user_21`, 07:20-07:25, **reposo al despertar** (el sueño anterior, 62-68 lpm): pulso 58-63 lpm
  contra una mediana de 80,4. Base: 89 de trabajo, 12 de reposo y 9 de comida.

Las dos bases son solo lecturas diurnas del primer día (09:15-20:35): con 24 h de registro y 12 h de
desfase, la base de una lectura de primera hora es siempre de la otra mitad del día. Es el mismo
efecto que el hallazgo 7 (una base fina no es evidencia) en el único tramo de MMASH donde la familia
llega al mínimo. Ninguna de las nueve escala: no cambia ningún nivel ni ningún sujeto marcado.

**Lo que queda por decidir.** `test_external_alarm_rate_does_not_regress` (0,2329 % contra un techo de
0,23 %) y `test_alerts_per_crew_week_does_not_regress` (4,31 contra 4,03) fallan. Sus comentarios
dicen que subir el techo para que pase una suite que empeoró es el fallo que existen para evitar,
así que no se ha subido. Con las cifras delante caben dos lecturas: aceptar el arreglo y re-anclar
los dos techos a lo medido (lo que el motor hace ahora es lo que dice su documentación, y el coste es
de lecturas leves sin escalado en un efecto de duración del dataset), o no adoptarlo hasta tener un
registro de varios días donde la base de reposo cubra todas las horas.

**Lo que se decidió con estas cifras** (usuario, 2026-10-22): exigir cobertura antes de juntar. Los
techos no se tocan.

#### Con cobertura de la hora: la falsa alarma baja, y la sensibilidad del colapso de HRV también

**La regla** (de diseño de EMMA en sus números; el principio de comparar a la misma hora tiene
fuentes, leídas después: «Qué dice la literatura», abajo): la familia solo se junta si las lecturas
que **presta** —las de los otros estados, no las del propio— incluyen al menos
`FAMILY_COVERAGE_MIN` = 5 a menos de `FAMILY_COVERAGE_HALF_WIDTH` = 30 min de la hora del reloj de
la lectura juzgada, en cualquier día de la ventana (`baseline.family_covers`). La franja es la hora
centrada en la lectura, sin bordes de hora fija; el 5 es lo que esa hora tendría en una base del
tamaño mínimo repartida por igual en el día (`MIN_SAMPLES` / 24, hacia arriba). La hora es la de la
marca de tiempo (UTC). Si no cubre, la base es la del estado exacto y la lectura cae al respaldo
poblacional, como antes del arreglo. La regla se fijó antes de medir, y no se ha ajustado después.
`rules_version`: `reglas@dfce3ccf979318b1` (sin los cambios de otras unidades). *(2026-10-23, E1:
la hora se lee en el reloj `FAMILY_COVERAGE_CLOCK` = UTC, pasando antes a UTC una marca con otra
zona; una sin zona es un error, como ya lo es en `VitalObservation`. El reloj entra en la huella: `reglas@ef06e009be80877f`. MMASH
y el simulador ya dan sus marcas en UTC, y ninguna cifra de este hallazgo cambia.)*

| MMASH, parámetros de misión | antes del arreglo | sin cobertura | **con cobertura** |
|---|---|---|---|
| Falsa alarma por lectura | 0,1842 % (34) | 0,2329 % (43) | **0,1625 %** (30) |
| En reposo | 0,1472 % | 0,2103 % | **0,1472 %** |
| Episodios por tripulante-semana | 3,63 | 4,31 | **3,18** |
| Sanos marcados | 1 / 22 | 1 / 22 | 1 / 22 |
| Taquicardia sostenida, episodio agudo, taquicardia progresiva | — | igual | igual |
| Colapso de HRV: detectado / marcado / escalado | 13,6 / 4,5 / 0 % | 18,2 / 4,5 / 0 % | **9,1** / 4,5 / 0 % |

Con la cobertura desaparecen las nueve lecturas nuevas del arreglo, y además cuatro que el motor
anterior ya marcaba: SDNN y RMSSD de `user_21` en `meal` a las 08:35-08:40, juzgadas contra una
familia de trabajo y comida de 112 lecturas diurnas. Es el residuo de «HRV durante la digestión» del
hallazgo 28 (de 8 lecturas quedan 4). Nueve lecturas que el motor anterior juzgaba contra una base
personal vuelven al respaldo poblacional.

**Y por el mismo mecanismo se pierde una detección.** El colapso de HRV inyectado se detectaba en
`user_21` solo por esas mismas lecturas de comida de las 08:35-08:40 (SDNN de 0 y 3,78 ms contra la
misma base diurna). Con la cobertura dejan de juzgarse con base personal, y la detección baja de 3 a
2 de 22 sujetos: **9,1 %, por debajo del suelo de 10 %** de `test_sensitivity_does_not_regress`, que
falla. Las dos pruebas de falsa alarma pasan con sus techos de siempre (0,1625 % ≤ 0,23 %; 3,18 ≤
4,03). Con el pulso submuestreado a 48/día el colapso de HRV detectado baja también de 3 a 2; lo
demás no cambia. Los 36 casos del veredicto del simulador son idénticos: el simulador no emite
trabajo ni comida.

**No se ha bajado el suelo.** Es exactamente lo que la invariante 5 prohíbe sin decisión: la falsa
alarma mejora y un deterioro inyectado se detecta menos. Lo que se pierde es una detección que salía
de comparar una lectura de primera hora con una base diurna, el mismo cruce que la cobertura existe
para impedir, en un indicador cuya baja detección ya está declarada como límite del experimento.
Queda pendiente de decisión del usuario.

#### Qué dice la literatura

*(2026-10-23, decimosexta ronda, unidad E1. Pedido del usuario: «buscar información sobre qué es lo
correcto». Cada fuente se leyó ese día y tiene ficha en `backend/app/data/evidence_refs.json`, citada
desde `validation.mmash.FAMILY_BASELINE_LITERATURE` (las fuentes; en la rama, desde
`baseline.FAMILY_COVERAGE_SOURCES`) y `validation.mmash.MULTI_WEEK_CANDIDATES` (los conjuntos). Ningún techo ni suelo de prueba se ha tocado, y la regla es la de la cobertura salvo
el reloj en que se lee la hora (arriba), que no cambia ninguna cifra de MMASH: **la rama sigue
pendiente de decisión del usuario**.)*

**1. El pulso y la VFC cambian con la hora del día, también despierto.**

- La norma de VFC (`task-force-hrv-1996`, leída en la copia de Internet Archive porque el editor
  devolvió 403) dice que en sujetos normales LF y HF «exhibit a circadian pattern», y que en
  registros largos «individual subjects should be recorded under fairly similar conditions and in a
  fairly similar environment». Dice también que «it is inappropriate to compare SDNN measures
  obtained from recordings of different durations»: eso es de duración, no de hora, y aquí solo
  respalda el principio general de comparar lo comparable.
- En 166 sanos con Holter de 24 h (`bonnemeier-2003-circadian-hrv`, solo el resumen), la RMSSD y el
  pNN50 tienen «a peak at nighttime and a plateau at daytime», y la SDNN es baja de noche y
  «increased in the morning hours». Los autores piden rangos normales que dependan de la hora del día
  («nycthemeral-dependent»).
- En un protocolo de 72 h en aislamiento temporal (`boudreau-2013-circadian-hrv-sleep`, solo el
  resumen, 13 jóvenes sanos) hay «a circadian rhythm of heart rate (HR) and high-frequency power
  during wakefulness». Estratificar por estado (despierto o dormido) no quita la hora.

**2. La comida y la actividad previa también la mueven.**

- Tras una comida de 500 kcal (`lu-1999-postprandial-hrv`, solo el resumen, 9 sanos) la HF baja y el
  cociente simpático-vagal sube «lasting 1 hr, mainly attributed to diminished vagal activity».
- Tras el ejercicio (`michael-2017-post-exercise-hrv`, revisión) pulso y VFC se recuperan con el
  tiempo, y «complete recovery may take up to 48 h following some bouts of exercise».

**3. Las recomendaciones de método piden comparar a la misma hora y en la misma condición.**

- `laborde-2017-hrv-recommendations` (revisión de método): con medidas en días distintos, «the time
  when the experiment is realized should be maintained constant», y entre lo que hay que controlar,
  «No intense physical training the day before» y «No meal the last 2 h before».
- `buchheit-2014-hr-monitoring` (seguimiento longitudinal de deportistas): «precautions be taken to
  standardize recording conditions»; la noche es la condición más estandarizada y la práctica
  habitual, medir «upon awakening in the morning», con «same bed and same time most days».

**4. Los sistemas publicados con reloj comparan cada hora con la misma hora, o solo la noche.**

- `mishra-2020-presymptomatic-smartwatch` (Stanford, relojes de consumo): RHR-Diff estandariza el
  reposo «in 1-h resolution based on the average of daily curves from a 28-d sliding window», y
  CuSum construye «a null distribution for each hour» con 28 días de base. El reposo es el pulso con
  cero pasos en los 12 minutos previos.
- `alavi-2022-realtime-alerting-wearables` (estudio prospectivo, 3318 inscritos): su detector
  NightSignal toma como base la mediana del reposo nocturno (24:00 a 7:00, cero pasos) y lo justifica:
  «substantial performance improvement when overnight RHR approach is used compared to daily RHR,
  because overnight RHR avoids short-range non-infection events such as stress or intense exercise
  during the day».

**Lo que se buscó y no se encontró.** Ninguna fuente fija la anchura de la franja (la media hora de
`FAMILY_COVERAGE_HALF_WIDTH`) ni un mínimo de lecturas por franja (las 5 de `FAMILY_COVERAGE_MIN`):
siguen siendo de diseño de EMMA. No se encontró un estudio que mida el despertar como estado propio
con cifras aplicables a una base personal: lo que salió en Europe PMC buscando el despertar o el
«morning surge» con la VFC era de presión arterial, de cortisol o de pacientes. De Bonnemeier 2003,
Boudreau 2013 y Lu 1999 se leyó solo el resumen.

**Lo que esto dice de cada variante.** Las nueve lecturas que añade la variante A (reposo al
despertar de `user_21`; reposo justo después de una actividad en `user_14`) son exactamente las
comparaciones que estas fuentes desaconsejan: una lectura de primera hora o de recuperación contra
una base diurna de otro estado. Re-anclar los techos a ellas sería aceptar como coste del motor unas
alarmas que salen de un cruce de fase. La variante B aplica el principio de las fuentes al camino de
la familia.

**Y obliga a mirar también la base propia.** Medido el 2026-10-23 con la variante B (un guion fuera
del repositorio que reconstruye, para cada lectura juzgada con base personal, las lecturas de su base
propia a menos de 30 min de su hora del reloj):

- Solo **102 de las 18 460** lecturas de MMASH se juzgan con base personal. De ellas, solo **6**
  tienen en su base propia 5 o más lecturas a menos de media hora de su hora.
- Las 8 lecturas que detectan el colapso de HRV con la variante B (`user_15` y `user_17`, actividad,
  08:15-08:45 del segundo día) tienen **0** lecturas de su base a menos de media hora. Las de
  `user_21` que lo detectaban antes (comida, 08:35-08:40) eran el mismo cruce por la familia.

Es decir: **toda la detección del colapso de HRV en MMASH, con cualquiera de las tres variantes,
sale de juzgar una lectura de primera hora contra una base de la otra mitad del día.** Ese 13,6 % no
mide si el motor ve una caída de SDNN en condiciones comparables; mide cuántas de esas
comparaciones cruzadas pasan del percentil 99.

**Variante C, medida para saberlo y no implementada en el motor.** Es la regla que las fuentes
respaldan llevada hasta el final. Se fijó antes de medir: toda base personal, propia o con familia,
solo juzga una lectura si sus lecturas incluyen al menos `FAMILY_COVERAGE_MIN` a menos de
`FAMILY_COVERAGE_HALF_WIDTH` de su hora del reloj; si no, respaldo poblacional. Se midió aplicándola
en el disco y devolviendo el fichero después; no está en la rama.

| MMASH, 22 sujetos, parámetros de misión | antes | A | B (la rama) | C |
|---|---|---|---|---|
| Falsa alarma por lectura | 0,1842 % (34) | 0,2329 % (43) | 0,1625 % (30) | **0,1192 %** (22) |
| En reposo | 0,1472 % | 0,2103 % | 0,1472 % | **0,1192 %** (17 de 14 266) |
| Episodios por tripulante-semana | 3,63 | 4,31 | 3,18 | **2,27** (10 episodios) |
| Sanos marcados | 1 / 22 | 1 / 22 | 1 / 22 | 1 / 22 (`user_15`) |
| Lecturas juzgadas con base personal | no medido | no medido | 102 | **6** |
| Taquicardia sostenida: detectado / marcado / escalado | 95,5 / 81,8 / 77,3 % | igual | igual | igual |
| Episodio agudo | 90,9 / 77,3 / 72,7 % | igual | igual | igual |
| Taquicardia progresiva | 31,8 / 13,6 / 9,1 % | igual | igual | igual |
| Colapso de HRV: detectado / marcado / escalado | 13,6 / 4,5 / 0 % | 18,2 / 4,5 / 0 % | 9,1 / 4,5 / 0 % | **0** / 4,5 / 0 % |

Con C fallaría la prueba de sensibilidad con más margen (0 de 22 contra 3) y pasarían las de falsa
alarma. Que las taquicardias no cambien con ninguna variante dice lo mismo que el hallazgo 12: su
detección sale de los límites de peligro, no de la base personal, y MMASH apenas ejercita la base
personal. **C no se puede evaluar con MMASH**: deja 6 juicios con base personal en 22 personas.

**Estadística.** Intervalos de Wilson al 95 % de la detección del colapso de HRV por sujeto: 2/22 =
9,1 % (2,5-27,8 %); 3/22 = 13,6 % (4,7-33,3 %); 4/22 = 18,2 % (7,3-38,5 %); 0/22 = 0 % (0-14,9 %). Los
cuatro se solapan de lado a lado. Entre «antes» y B cambia un solo sujeto (`user_21`): la prueba
exacta de McNemar con un par discordante da p = 1. Con n = 22 el suelo del 10 % significa «3 sujetos
o más», y la distancia entre pasar y fallar es una persona (4,5 puntos). Si la detección real fuera
13,6 %, otra muestra de 22 personas pasaría ese suelo solo el 59 % de las veces (binomial). Las
falsas alarmas: 22, 30, 34 y 43 de 18 460 dan 0,079-0,180 %, 0,114-0,232 %, 0,132-0,257 % y
0,173-0,314 %, y son más anchos de verdad porque las lecturas de un sujeto no son independientes
(vienen seguidas en el tiempo). Las pruebas son de regresión sobre un conjunto fijo y
determinista: dicen que algo cambió, no que cambiara la sensibilidad del motor en otra población.
Para saber si B dejó sordo al motor no sirve el número: sirve qué detección se perdió y por qué, y
la que se perdió era un cruce de fase.

**Conjuntos públicos con varias semanas por persona (KB §13, hipótesis H2).** Licencia leída en la
página de cada conjunto el 2026-10-23. No se ha descargado nada. Los tres primeros los releyó esta
unidad y tienen ficha; el resto los leyó una búsqueda delegada de la unidad y quedan descartados o
pendientes, sin ficha porque EMMA no los usa.

| Conjunto | Licencia (en su página) | Acceso | Personas / duración / aparato | Corazón | ¿Sirve para medir B o C? |
|---|---|---|---|---|---|
| LifeSnaps (`lifesnaps-2022`, Zenodo) | Creative Commons Attribution 4.0 International | abierto | 71 / 8 semanas por persona / Fitbit Sense | pulso < 1 min (69), reposo diario (71), VFC cada 5 min (44), fases de sueño | **Sí**, para pulso y VFC; valores del reloj, sin RR |
| RELAX (`relax-2026-six-week-stress`, Zenodo) | Creative Commons Attribution 4.0 International | abierto | 31 adultos trabajadores / 6 semanas / aparato no nombrado | intervalos latido a latido y acelerómetro a 52 Hz | **Sí**, para RMSSD por franja; salud de los participantes no dicha |
| PMData (`pmdata-2020`, Simula) | CC BY 4.0 | abierto | 16 / 5 meses / Fitbit Versa 2 | pulso con hora, reposo diario, sueño | **En parte**: pulso sí, VFC no |
| Baigutanova et al. 2025 (figshare 28509740) | CC BY | abierto | 49 sanos / 4 semanas / Galaxy Watch Active 2 | IBI y VFC cada 5 min | En parte: el reloj se cargaba de noche |
| Fitbit Fitness Tracker Data (Zenodo 53894) | Creative Commons Attribution 4.0 International | abierto | 30 / unos 2 meses / varios Fitbit | pulso por minuto en parte de los usuarios | Poco: sin VFC |
| TILES-2018 / TILES-2019 | ninguna en la página; el artículo pide un acuerdo de uso firmado | cuenta y acuerdo | 212 / 10 semanas; 57 / 3 semanas | Fitbit; ECG solo en turnos (2018) | En parte, con acuerdo: no abierto |
| mcPHASES (PhysioNet) | PhysioNet Restricted Health Data License 1.5.0 | registro y acuerdo | 42 / 3 meses / Fitbit Sense | pulso | Restringido |
| GLOBEM (PhysioNet) | PhysioNet Credentialed Health Data License 1.5.0 | acreditación | 497 / unas 10 semanas al año | no se vio pulso | No |
| BIG IDEAs Glycemic (PhysioNet) | Open Data Commons Attribution License v1.0 | abierto | 16 / 8-10 días / Empatica E4 | pulso, IBI | No: menos de dos semanas |
| CGMacros (PhysioNet) | CC BY-NC-SA 4.0 | abierto | 45 / unos 10 días | Fitbit | No: corto, no comercial |
| Hannon et al. 2025 (GitHub) | ninguna en el repositorio | público sin licencia | 41 / 7-14 días | RMSSD matinal | No: sin licencia no hay derecho de uso |
| RR interval time series from healthy subjects (PhysioNet) | Creative Commons Attribution 4.0 International Public License | abierto | 147 / 24 h | RR | No: un día |

No se encontró en PhysioNet ningún conjunto de personas sanas con RR de varias semanas. No se
pudieron abrir las páginas de licencia de Kaggle (copia del conjunto de Fitbit), NetHealth,
Tesserae, ETRI Lifelog y Homekit2020: no se declara su licencia.

**Recomendación: la variante B con el suelo revisado, y C pendiente de un conjunto de varias
semanas.**

1. **No adoptar** deja el motor contradiciendo su propio contrato (`Context.family`): el reposo se
   juzga sin el reposo. No hay fuente que respalde quedarse así.
2. **A con los techos re-anclados** acepta como coste falsas alarmas que salen justo del cruce que
   las fuentes desaconsejan (despertar y recuperación contra una base diurna). Se descarta.
3. **B** aplica a la familia el principio que respaldan la norma, las recomendaciones de método y los
   dos detectores publicados. Baja la falsa alarma (0,1842 → 0,1625 %; episodios 3,63 → 3,18) y
   pierde una detección que era un cruce de fase. El suelo del colapso de HRV no puede distinguir 2
   de 3 sujetos (intervalos y McNemar arriba), y además ancla una detección que en MMASH sale entera
   de comparaciones cruzadas. **Propuesta para el usuario**: re-anclar ese suelo a lo medido con B
   (2 de 22, 0,09), con el comentario de por qué, como se hizo con la taquicardia progresiva cuando
   su cifra estaba inflada por un defecto del conjunto (hallazgo 17); o declararlo, igual que la
   deriva lenta en `MIN_ESCALATION`, como algo que MMASH no puede validar. Las dos son decisión del
   usuario, no de esta unidad.
4. **C** es lo que las fuentes respaldan llevado a toda base personal, pero en MMASH deja 6 juicios
   con base personal y no se puede evaluar. Antes de proponerla hay que medirla con un conjunto de
   varias semanas donde las bases cubran todas las horas: LifeSnaps (VFC cada 5 min, CC BY 4.0) o
   RELAX (latido a latido, CC BY 4.0). Descargarlos y añadir su cargador es trabajo aparte.

**Lo que B no hace, dicho antes de decidir.** La cobertura es una puerta, no una base de la misma
hora: si pasa, la base sigue mezclando todas las horas de la ventana, y Mishra 2020 lo que hace es
comparar cada hora con la misma hora. El mínimo de 5 cuenta lecturas, no días: con un aparato que
muestree cada minuto, un solo día con actividad a esa hora ya la cubre. Y el perfil de línea base
(`baseline_profile`) no distingue una familia rechazada por no cubrir la hora de un estado sin
familia: dice «Lecturas de trabajo.» aunque hubiera cientos de lecturas de reposo en la ventana. Las tres cosas se miden mejor con un conjunto de varias semanas y quedan abiertas.

### 30. La tendencia cuenta en presente un episodio ya cerrado — medido, sin adoptar

**Decisión del usuario (2026-10-26): medirlo sin adoptar.** El motor no cambia
(`reglas@c89d7ebf4d5f4aa9`, la versión de §5.37.1 de `compliance/hmi-state-of-the-art.md`): nada que
decide pasa la regla, y los techos y suelos de prueba siguen como estaban. El código está en `main`
desde la fusión de la unidad U6 de la decimoctava ronda (`05fe919`, sobre `812786e`), como medida y
no como regla: `analysis/episode.py`, un gancho opcional `settle` de `trends_by_indicator` que ni el
estado, ni la trayectoria, ni la historia recalculada, ni la retrospectiva de proyecciones, ni la
comparación de tripulación llaman. Una sesión anterior, interrumpida, lo había cableado en todos
ellos —adoptado—, y la unidad lo deshizo. Detalle en `hmi-state-of-the-art.md` §5.38.6.

*(2026-10-29, decimoctava ronda, unidad U6. Lo que motivó la medida: §5.37.3 dejó escrito que el
escenario `transient-sleep-loss` —una falta de sueño pasajera que cesa tres días antes del final—
acaba en vigilancia y no en nominal, porque la recta de 21 días de `analysis/trend.py` todavía
contiene el episodio y lo cuenta en presente, «subiendo… a lo largo de 21 días». El motor no
distingue un episodio que cesó de una deriva que sigue.)*

**La regla, fijada antes de medir.** Una tendencia que hoy preocupa deja de contar como deriva
vigente —se describe en pasado como «episodio cerrado», no suma puntos al riesgo ni se proyecta—
cuando se cumplen las tres a la vez:

1. *Hubo episodio y lo vio la vía de desviación.* Partiendo la ventana de la tendencia en tramos de
   `CURRENT_WINDOW` (dos días) hacia atrás desde el «ahora», al menos un tramo anterior al actual
   tiene hallazgo en el sentido de la deriva con la regla de persistencia del estado
   (`risk.representative_deviation`): el indicador salió de su rango personal, no lo rozó una lectura.
2. *La vía de desviación lo ve de vuelta.* El tramo actual tiene lecturas del indicador y ningún
   hallazgo en ese sentido. Sin lecturas no hay vuelta: un dato ausente no es una recuperación.
3. *Ha vuelto a su nivel, no a una base que lo ha seguido.* La mediana del tramo actual se ha movido,
   en el sentido malo y respecto a la mediana de antes del primer tramo con hallazgo, menos de lo que
   una deriva al ritmo de relevancia de la propia tendencia (`relevance_threshold` en
   `RELEVANCE_HORIZON_WEEKS`) habría movido el nivel en el tiempo transcurrido. Escalado al tiempo y
   no el umbral entero: sin escalar, una deriva viva por debajo del doble del umbral pasaba por «de
   vuelta» (lo cazó la revisión de código antes de medir). Si el episodio empieza con la ventana, no
   hay nivel previo y no se cierra.

No hay número nuevo: combina el «ahora» y la persistencia con que ya decide la vía de desviación con
el umbral clínico con que ya decide la de tendencia. La 1 la limita a lo agudo: una deriva lenta que
nunca sale de su rango personal —lo que la vía de tendencia existe para ver— no la toca. La 3 existe
porque la base personal es móvil (14 días). No se pondera lo reciente ni se veta por el tercio final
de la ventana: el hallazgo 27 probó quince variantes de ese veto y todas o vetaban derivas reales con
pocos datos o no vetaban nada. Ninguna fuente respalda la regla: es diseño, y se declara así. Se
aplica por estrato de contexto antes de quedarse con el más preocupante: si no, un episodio cerrado
en un contexto taparía una deriva viva en otro.

**Dónde se mide.** `GET /api/status` → `closed_episode_shadow` (`adopted: false`; qué tendencias
cerraría, con su texto en pasado, y el nivel global y los dominios que cambiarían si se adoptara,
calculados aparte con las mismas desviaciones, el mismo «ahora» y los mismos argumentos del motor de
riesgo) y la validación externa con `closed_episodes=True` (por defecto `False`). La interfaz no la
muestra: es una medida para decidir, no un dato de tripulación.

**Medido (2026-10-29; invariante 5, los dos ejes juntos).**

*Fisiología humana real (MMASH, `-m external`): idéntico con y sin la regla, por construcción, no por
mérito.* 24 h de registro no dan tendencia (`MIN_SPAN_DAYS = 3`) ni tramos anteriores de dos días, así
que la regla no se ejerce. Falsa alarma en reposo 0,1472 % (§5.38.6 la escribe redondeada, «0,147 %»;
la tasa por lectura no la anota, y es la de las demás medidas de esa ronda, 0,1842 %, §5.38.11,
porque en 24 h la regla no puede ejercerse), con 1 de 22 sanos con alguna alerta; sensibilidad
(marcado / escalado): taquicardia sostenida 18 de 22 (82 %) / 77 %, progresiva 3 de 22 (14 %) / 9 %,
episodio agudo 17 de 22 (77 %) / 73 %, colapso de HRV 1 de 22 (5 %) / 0 %. Las ocho cifras, iguales
en las dos corridas. **MMASH no puede validar esta regla y no se presenta como si lo hiciera.**

*Los diez escenarios del simulador, tres semillas (20261114, 7 y 1), 40 días, `/api/status` y su
sombra:*

| Escenario | Qué cerraría la regla | Nivel global, sin → con regla |
|---|---|---|
| `nominal` (eje de falsa alarma) | nada, en las tres semillas | nominal → nominal |
| los siete deterioros (eje de sensibilidad) | nada, en las 21 corridas | igual en todas |
| `menu-fatigue` | nada | igual (nominal; vigilancia en la semilla 7) |
| `transient-sleep-loss` (lo que motivó la regla) | 3, 2 y 3 de sus 4 indicadores | vigilancia → **vigilancia** |

Son los diez escenarios de `Scenario` (`ingest/simulator.py`) por tres semillas, treinta corridas:
§5.38.6 escribe en esta fila «los ocho deterioros» y «24 corridas», que con las otras tres filas
sumarían 33; con `nominal`, `menu-fatigue` y `transient-sleep-loss` aparte quedan siete deterioros
(`spe-event`, `progressive-insomnia`, `arrhythmia`, `cardiovascular-deconditioning`,
`immune-reactivation`, `co2-fatigue` y `dehydration`), y así se escribe aquí.

Las dos métricas no se mueven: ninguna deriva viva se da por cerrada en ningún deterioro
(sensibilidad intacta) y la falsa alarma del escenario sano ya era cero. Pero **la regla tampoco logra
aquello para lo que se pensó**: en el escenario que cesa cierra la mayoría de lo que volvió, nunca
todo, y basta un indicador abierto para que el dominio conductual siga en vigilancia. Cuál se queda
abierto cambia con la semilla (los lapsos del PVT en dos, la duración del sueño en otra); el motivo
medido en la semilla 20261114 es un estrato de contexto ralo: el de esfuerzo de los lapsos tiene
cuatro lecturas en el «ahora» y su mediana no ha vuelto (condición 3).

**Lo que no mide esto.** Treinta corridas de un simulador determinista, con un único escenario que
cesa: no hay base para una tasa. La validación con `closed_episodes=True` pasa todas las desviaciones
al motor de riesgo, como ya hacía, no solo las del «ahora»: con datos largos mezclaría dos «ahoras».
Y parte los tramos con una constante propia, `STATE_WINDOW` (`validation/report.py`, dos días), que
es una copia de `CURRENT_WINDOW` (`api/routes.py`) y nada ata a ella: si una cambia y la otra no, la
sombra del estado y la validación medirían reglas distintas sin que ninguna prueba lo vea. Hoy no
importa (MMASH no la ejerce); las dos cosas habría que arreglarlas antes de medirla con un conjunto
de varias semanas.

**Decisión pendiente del usuario.** Adoptarla tal cual no cambia hoy ningún veredicto del simulador
ni de MMASH: no hace daño medible, pero tampoco cumple su propósito. Las salidas que se ven: (a)
dejarla medida y sin adoptar, como está; (b) que la condición 3 exija un mínimo de lecturas recientes
por estrato y, si no lo hay, no cuente ese estrato ni como «sigue» ni como «volvió» —un número nuevo,
que habría que medir igual—; (c) descartarla. Pruebas: `tests/test_trend_closed_episode.py` (las
tres condiciones, el estrato antes de elegir, el «antes» de este episodio, que el estado no la usa y
lo que dice la sombra) y la campaña `tests/mutants/trend_closed_episode.json`;
`test_simulator_evidence.py` sigue fijando `transient-sleep-loss` en vigilancia.
### 31. Con varias semanas por persona la base personal trabaja de verdad, y ahí está la falsa alarma

*(2026-11-01, decimonovena ronda, U24. Decisión del usuario del 2026-10-31, que sigue a la del
2026-10-23: medir A, B y C con un conjunto de varias semanas. **Medido y sin adoptar**: el motor y
`rules_version` no cambian, y ningún techo ni suelo se ha tocado. Código: `validation/lifesnaps.py`,
`validation/family_variants.py`; cifras exactas en `tests/test_lifesnaps_external.py`.)*

**Conjunto.** LifeSnaps (Zenodo, doi:10.5281/zenodo.7229547, versión 4; ficha `lifesnaps-2022`),
licencia «Creative Commons Attribution 4.0 International». 71 personas con Fitbit Sense, 4768
días-persona con lecturas (mediana 64 por persona; hay registros de 1 a 243 días), 1 322 974
lecturas: pulso en ventanas de 5 min y RMSSD del reloj. Es vida diaria en Tierra: **no valida
fisiología espacial**, y como MMASH valida el motor de medida y la falsa alarma, no la deriva de
vuelo. Además, no es una cohorte cribada como sana: nadie declara un deterioro, pero un catarro de
tres días cuenta aquí como falsa alarma, así que la cifra de abajo es una cota por arriba.

**Lo que el conjunto no trae, y cambia lo que se puede medir.**

- **No hay SDNN ni RR, y la RMSSD es solo nocturna.** El colapso de HRV de referencia (-30 ms de
  SDNN), el que falla con B en MMASH, **no se puede medir aquí**. Se inyecta una caída de la RMSSD
  nocturna a la mitad (los -30 ms dejaban en 0 ms 248 de 327 lecturas de un sujeto), que es otro
  deterioro: **esto no decide el suelo del hallazgo 29**.
- **La familia apenas se ejercita.** No hay comida, y trabajo solo sale de las encuestas «dónde
  estás» (`WORK/SCHOOL`, `HOME_OFFICE`): 7575 lecturas quietas a menos de 30 min de una respuesta,
  el 0,57 %. Las variantes A y B solo pueden mover ese trozo.
- El estado sale de los registros de sueño y ejercicio y de los pasos, no de un diario. La RMSSD no
  se mide despierto, y las marcas son del reloj local de la persona.

**La medida.** Falsa alarma: toda lectura, como en `report.py`, y además día a día, porque en ocho
semanas «sujetos marcados» deja de significar nada. Sensibilidad: con una base real delante del
deterioro, desde `onset_after` y 72 h de tramo (sin corte, una deriva de 15 lpm/día sumaría más de
300 lpm), con un **brazo simulado**: la misma persona y el mismo tramo sin deterioro. Base de 14 días
y desfase de 12 h, los parámetros de misión. `family_variants.spread` da los intervalos, remuestreando personas. La implementación de las variantes reproduce exacta la
tabla de MMASH del hallazgo 29 (34 / 43 / 30 / 22 lecturas; colapso de HRV 3 / 4 / 2 / 0), y la
vigente coincide con `evaluate_rolling` en sus pruebas.

| LifeSnaps, parámetros de misión | vigente | A | B | C |
|---|---|---|---|---|
| Falsa alarma por lectura | **3,532 %** (46 721) | 3,540 % (46 835) | **3,539 %** (46 815) | **3,274 %** (43 316) |
| IC 95 % (remuestreo de personas) | 3,33-3,76 | 3,34-3,77 | 3,34-3,77 | 3,09-3,49 |
| Diferencia con la vigente, pareada (puntos) | — | +0,004 a +0,014 | +0,004 a +0,011 | **-0,30 a -0,22** |
| Sin actividad | 3,785 % | 3,797 % | 3,795 % | 3,489 % |
| Episodios por tripulante-semana | 20,64 | 20,67 | 20,67 | 19,83 |
| Días-persona con nivel sobre nominal | 70,4 % (3355) | 70,4 % | 70,4 % | 70,2 % (3347) |
| Personas con alguna lectura marcada | 70 / 71 | 70 / 71 | 70 / 71 | 70 / 71 |
| Lecturas juzgadas con base personal | 95,09 % | 95,53 % | 95,52 % | 92,88 % |
| Trabajo con base personal (de 7575) | 1764 | 7440 | 7387 | 7253 |

El acierto bruto engaña con esta tasa de fondo: por eso cada fila va con su brazo simulado. En la
primera tabla, inyectado frente a simulado (sujetos de cada brazo); en la segunda, las lecturas.

| Deterioro, 72 h (sujetos) | Variante | Alguna lectura marcada: inyectado / simulado | Nivel sobre nominal: inyectado / simulado | Escalado sobre su simulado |
|---|---|---|---|---|
| Taquicardia sostenida, +25 lpm (59) | vigente, B | 59 / 57 | 59 / 47 | 54 |
| | C | 59 / 57 | 59 / 47 | 55 |
| Taquicardia progresiva, +15 lpm/día (59) | vigente, B | 57 / 57 | 59 / 47 | 49 |
| | C | 57 / 57 | 59 / 47 | 50 |
| Episodio agudo, +40 lpm, 2 h (49) | vigente, B | 47 / 13 | 49 / 38 | 30 |
| | C | 47 / 13 | 49 / 38 | 32 |
| Colapso de RMSSD nocturna, -50 % (35) | vigente, B | 32 / 21 | 34 / 27 | 23 |
| | C | 32 / 20 | 34 / 27 | 22 |

| Lecturas marcadas: inyectado / simulado → diferencia (puntos) | vigente | B | C |
|---|---|---|---|
| Taquicardia sostenida (38 365 lecturas) | 27,10 / 3,28 → **23,82** | 27,13 / 3,28 → **23,85** | 26,59 / 3,08 → **23,51** |
| Taquicardia progresiva (38 365) | 35,33 / 3,28 → **32,05** | 35,43 / 3,28 → **32,15** | 34,82 / 3,08 → **31,74** |
| Episodio agudo (1145) | 64,28 / 3,41 → **60,87** | 64,28 / 3,41 → **60,87** | 63,32 / 3,41 → **59,91** |
| Colapso de RMSSD nocturna (8029) | 22,87 / 2,59 → **20,28** | 22,87 / 2,59 → **20,28** | 22,39 / 2,58 → **19,81** |

A da lo mismo que B en los sujetos de estas tablas. Ninguna lectura perturbada se acotó al límite
físico; el colapso es proporcional porque restar milisegundos dejaba lecturas en 0 ms. La cuenta de
sujetos excluye a quien no tiene base personal delante del inicio o menos de una hora perturbada.

**Lo que se mide de cada variante.**

- **A y B no cambian nada visible, en ningún sentido.** Dan base personal a casi todo el trabajo
  (1764 → 7387 de 7575) y suben la falsa alarma 94 lecturas; la sensibilidad, menos de 0,1 puntos.
  Esta medida **no dice nada a favor ni en contra de B**, ni resuelve el suelo del colapso de HRV.
- **C baja la falsa alarma 0,26 puntos (un 7 %) y la señal neta 0,3-1,0 puntos.** Los dos ejes se
  mueven en el sentido esperado, y las diferencias de sujetos son de 1 o 2 y en los dos sentidos:
  escala 1 o 2 más en las tres taquicardias y 1 menos en el colapso de RMSSD. Deja un 7 % de las
  lecturas en respaldo poblacional. Episodios -4 %; días marcados -0,2 puntos. Es la primera medida de
  C con base personal de verdad (en MMASH quedaban 6 juicios).
- **Lo que distingue un deterioro de su simulado es el escalado y la fracción de lecturas**, no
  «alguna lectura marcada» (57 de 59 sin deterioro) ni «nivel sobre nominal» (47 de 59 sin deterioro).
  La deriva progresiva no se distingue nada en la primera columna: 57 frente a 57.

**Y lo que dice sobre el motor, que importa más que las variantes.** Con la base personal trabajando
(95 % de las lecturas, frente a menos del 1 % en MMASH), la regla vigente marca el **3,53 %** de las
lecturas, unas **19 veces** el 0,18 % de MMASH; 20,6 episodios por tripulante-semana, y el **70 %**
de los días-persona acaba sobre nominal. La mediana por persona es 3,4 % (p10-p90: 2,6-4,8 %), o sea,
no son unos pocos sujetos. **El 0,18 % de la portada no es la tasa esperable con semanas de datos**:
como ya decía el hallazgo 12, es la de un motor que en MMASH apenas usa la base personal. Por
construcción, un corte por percentil de la propia base marca una fracción fija aunque nada pase, y
se añade la falsa alarma real de una vida no estacionaria. El mismo efecto se ve en el brazo
simulado: 47 de 59 sujetos sin deterioro tienen el nivel sobre nominal en alguno de los tres días.
Esto no significa que el sistema fuera a alarmar igual en vuelo: es un reloj
de muñeca en ventanas de 5 min y en vida libre, sin cribado. Pero es una medida real de la rama que
la validación por MMASH no ejercitaba, y hay que tenerla delante.

**Lo que queda.** La decisión de adoptar es del usuario, y esta unidad no recomienda ninguna: B sigue
dependiendo del suelo del colapso de HRV, que este conjunto no puede medir (haría falta RELAX, con
latido a latido despierto). Lo que abre es otra cosa: decidir si la tasa de falsa alarma con base
personal activa se trata, y cómo. No se ha probado ningún cambio de esa regla.

### 32. El ciclo menstrual, medido como molestia: el motor de hoy lo confunde con una deriva

*(2026-11-14, lote «ciclo», unidad A5. Simulado, no fisiología real; motor sin tocar.)*

**El hueco.** Una tripulante sin supresión menstrual pasa cada ~4 semanas dos con la temperatura, el
pulso en reposo y la variabilidad del pulso desplazados. MMASH son 24 h de varones y el tripulante
simulado no tenía ciclo: esa falsa alarma no la había medido nadie, y la invariante 5 pide medirla
junto con la sensibilidad.

**Lo que se añadió.** Un ciclo opcional en el simulador (`CrewMember.cycle`, apagado por defecto: el
nominal y las series fijadas no cambian) con forma de escalón lúteo suavizado: 28 días, 14 de fase
lútea, rampas de medio coseno de 2 días. Amplitudes de diseño, sin cita (`LITERATURE`, clase
`design`; se sustituirán por las de la bibliografía que se está fichando): temperatura +0,4 °C, pulso
+3 lpm, RMSSD y SDNN -6 ms. Y una perturbación `CYCLE` en `validation/injection.py` con la misma forma,
**fuera** de los deterioros de referencia: es una molestia, no un deterioro. Prueba:
`tests/test_cycle_nuisance.py`, en la suite por defecto.

**Las dos métricas, juntas** (3 semillas; temperatura a 0,3 y a 0,5 °C, el resto de diseño):

| | Sin ciclo | Ciclo, 0,3 °C | Ciclo, 0,5 °C |
|---|---|---|---|
| Falsa alarma: evaluaciones en WATCH, tripulante sano, 70 días (de 84) | 12 | **63** | **71** |
| Falsa alarma: evaluaciones en CONCERN (de 84) | 0 | 0 | 0 |
| Sensibilidad: deterioros con alguna lectura marcada (de 15) | 15 | 15 | 15 |
| Sensibilidad: deterioros que suben el estado sobre la serie sin deterioro (de 15) | 8 | **0** | **0** |
| Serie sin deterioro ya fuera de NOMINAL en esos instantes (de 15) | 0 | 15 | 15 |
| Febrícula en fase lútea (+0,5 °C): sube el estado (de 3) | 2 | **0** | **0** |

Los 15 casos de sensibilidad son los cuatro deterioros de referencia más una febrícula sostenida de
+0,5 °C, inyectados el día 20 a las 10:00 (plena meseta lútea, en vigilia), sobre temperatura,
pulso, RMSSD y SDNN, y mirados a 24 y 48 h. Sin ciclo, el episodio de 2 h y el colapso de SDNN se
marcan en la lectura pero no mueven el estado en 48 h; eso no es del ciclo.

**Lo que dicen.** Con el ciclo, una tripulante sana pasaría tres cuartas partes de la misión en
WATCH. Por clave, con su amplitud de diseño: la temperatura sola da 68 de 84, la RMSSD sola 26, el
pulso solo y la SDNN sola 12 (lo mismo que sin ciclo). No lo dispara la lectura sino la
**tendencia**: el escalón lúteo, visto por la recta de 21 días, supera el umbral clínico de deriva
(hallazgo 27). Y la sensibilidad se degrada de una forma que «alguna lectura marcada» no ve: la
lectura deteriorada se sigue marcando, pero el estado ya estaba en WATCH por la molestia y ningún
deterioro lo sube en 48 h. Por el nivel, la febrícula no se distingue de la fase lútea.

**Lo que queda.** Es la línea de partida que fija la prueba como regresión documentada, no un fallo
escondido. La línea base consciente de la fase (unidad B3) tiene que bajar las dos cifras de WATCH
con ciclo hacia la de sin ciclo y devolver el escalado, sin bajar las lecturas marcadas. Las
amplitudes son de diseño: con las de la bibliografía las cifras cambiarán, y se vuelven a medir.

#### 32 bis. La línea base consciente de la fase: las dos métricas, juntas

*(2026-11-15, lote «ciclo», unidad B3. Simulado, no fisiología real.)*

**Lo que se añadió.** Un **desplazamiento** por fase, no una base por fase (estratificar de más ya
hundió el episodio agudo del 90 % al 20 %, hallazgo 24): en la fase lútea se descuenta de la base
personal **y de la tendencia** la subida de temperatura y pulso (`analysis/cycle_phase.py`). La base
se lleva a la fase de la lectura que se juzga; la lectura no se toca, así que el límite de peligro
absoluto y el rango poblacional siguen viendo el valor medido. Solo donde lo leído da cifra
(temperatura 0,23-0,7 °C, pulso 3,42-3,91 lpm); la RMSSD y la SDNN, con solo el sentido
documentado, no se ajustan. La fase lútea son 12,4 días contados hacia atrás desde la regla (Bull
2019, `bull-2019-menstrual-cycle-characteristics`), y solo se ajustan los días que serían lúteos con
cualquiera de los ciclos recientes de la propia tripulante (hasta 3); hacen falta 3 inicios de regla
registrados, un ciclo retrasado o demasiado irregular no se ajusta, y todo es causal (cada instante
con los inicios registrados hasta él). Con una **puerta en `api/`** (`api/cycle_phase.py`): sexo
declarado femenino, último estado reproductivo exactamente 1 («ciclo regular») e inicios
suficientes; si falta algo, el motor es el de siempre y la respuesta dice qué falta. El simulador
pasa la temperatura (0,4 °C) y el pulso (+3,7 lpm) a magnitud documentada, dentro del rango leído; la
RMSSD y la SDNN siguen de diseño (-6 ms).

**Cuánto descontar: medido, no elegido.** Primero se probó el extremo menor de lo leído, igual para
todas (0,23 °C, 3,42 lpm), que es lo que menos puede tapar. Con una subida real de 0,3 °C bajaba
WATCH de 63 a 26, pero con 0,5 y 0,7 °C casi nada (71 → 61, 75 → 72), y ahí la febrícula lútea seguía
sin subir el estado (0 de 3): lo no descontado sigue siendo un escalón que la recta de 21 días ve.
Se adoptó la **subida de la propia tripulante, medida en sus ciclos ya cerrados y acotada al rango
leído** (mediana de los últimos 7 días antes de cada regla menos la folicular interpolada a su
fecha entre la de lo anterior a los últimos 17 días —los extremos del intervalo de la fase lútea de
Bull— y la de los 7 primeros días del ciclo siguiente, por familia de contexto); sin ciclo cerrado
con lecturas, el extremo menor. Una fiebre del ciclo en curso no entra en lo que se descuenta en él.
La interpolación la pidió la revisión de código: comparando solo con la folicular de antes, una
deriva lenta y real (+0,03 °C al día) se leía como ~0,55 °C de subida lútea y se descontaba; con
ella se cancela (prueba `test_a_slow_real_drift_is_not_taken_for_her_luteal_rise`).
La variante del extremo menor se midió con el pulso del simulador aún en +3 lpm; el pulso solo no
movía la falsa alarma (A5).

**Las dos métricas, juntas** (3 semillas; 84 evaluaciones de una tripulante sana de 70 días; 15
casos de sensibilidad: los cuatro deterioros de referencia y la febrícula de +0,5 °C, inyectados
ahora el **día 48** a las 10:00, en la meseta lútea del segundo ciclo, después de un ciclo cerrado
con lecturas, y mirados a 24 y 48 h; la fila sin ciclo se volvió a medir ese día):

| | Sin ciclo | 0,3 °C sin ajuste | 0,3 °C con ajuste | 0,5 °C sin ajuste | 0,5 °C con ajuste | 0,7 °C sin ajuste | 0,7 °C con ajuste |
|---|---|---|---|---|---|---|---|
| WATCH, tripulante sana (de 84) | 12 | 63 | **26** | 71 | **43** | 75 | **52** |
| CONCERN, tripulante sana (de 84) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Deterioros con alguna lectura marcada (de 15) | 15 | 15 | 15 | 15 | 15 | 15 | 15 |
| Deterioros que suben el estado (de 15) | 10 | 0 | **6** | 0 | **7** | 0 | **7** |
| Serie sin deterioro ya fuera de NOMINAL (de 15) | 0 | 15 | 10 | 15 | 10 | 15 | 10 |
| Febrícula lútea: sube el estado (de 3) | 2 | 0 | **2** | 0 | **3** | 0 | **3** |

**Lo que dicen.** La falsa alarma baja en las tres amplitudes y la sensibilidad no baja en ninguna
métrica: la lectura se sigue marcando en 15 de 15, y el estado vuelve a subir por el deterioro (0 →
6-7) y por la febrícula lútea (0 → 2 de 3 a 0,3 °C, como sin ciclo, y 3 de 3 a 0,5 y 0,7 °C). De la temperatura, lo que queda
es casi todo del primer ciclo de la serie (sin ciclo cerrado propio, descuenta el extremo menor) y
su eco en la recta de 21 días: desde el día 44, la tendencia de la temperatura marca 0 de 39
evaluaciones a 0,5 °C y 1 de 39 a 0,7 °C. Y queda la **RMSSD**
(15 evaluaciones; 10 de 15 series sin deterioro en WATCH en la lútea), que no se ajusta porque lo
leído no da cifra. Por eso el escalado se queda en 6-7 y no en los 10 de sin ciclo: la serie sin
deterioro ya está en WATCH por la RMSSD. Con la puerta cerrada (sexo masculino o sin declarar,
supresión, perimenopausia, 1,5) el estado es idéntico al de sin ajuste, con su motivo.

**Lo que NO demuestra.** Es el simulador: un escalón lúteo de forma fija, de 14 días, sobre un
modelo con ruido independiente; ninguna serie real con ciclo se ha medido (MMASH no tiene mujeres).
La subida propia de una mujer real puede variar de ciclo en ciclo más que en el simulador, y la
amplitud de la RMSSD del simulador es de diseño. El mayor descuento posible es el extremo mayor de
lo leído (0,7 °C, 3,91 lpm): una fiebre menor que eso en plena lútea se juzga contra una base más
alta (peligro H1 de `risk-management-file.md`); el límite de peligro absoluto no se mueve.

**Pruebas.** `tests/test_cycle_nuisance.py` (las dos métricas por amplitud, con y sin ajuste; la
puerta por la API; el límite de peligro y la causalidad) y la campaña
`tests/mutants/cycle_phase_baseline.json`.

---

## Lo que esta validación NO demuestra

- **No valida el modelo de deriva de vuelo espacial.** Son 24 h de varones
  jóvenes sanos en Tierra.
- **Las perturbaciones son paramétricas, no clínicas.** Dicen que el motor
  reacciona ante un cambio de magnitud dada, no que ese cambio sea el que produce
  una patología concreta.
- **Cubre 6 de 24 indicadores.** El cortisol de MMASH está normalizado a proteína
  (no µg/dL; LOINC 2142-8 es Mass/volume) y no admite conversión directa;
  radiación, óseo e inmune no tienen correspondencia en el dataset.
- **No dice nada del ciclo menstrual.** MMASH no tiene mujeres ni, por tanto, ciclo, y ningún
  conjunto usado trae una serie de temperatura de semanas: la falsa alarma medida no incluye la
  variación de la fase lútea (temperatura y frecuencia cardiaca más altas, variabilidad vagal más
  baja). LifeSnaps, el único conjunto de varias semanas medido, no sirve tal como está: su cargador
  no lee el sexo ni ningún registro del ciclo, y no trae temperatura. Lo leído sobre cuánto cambia cada
  indicador por fase está en `data/cycle_physiology_read.json` (`evidence/cycle_physiology.py`,
  2026-11-14), con su clase de respaldo; no es una medida de EMMA.
- **Tampoco dice nada de la perimenopausia ni de los sofocos** (2026-11-15). Sin mujeres no hay
  ciclos irregulares ni anovulatorios, ni sofocos: picos de minutos (1,3 a 6,5 min por episodio en
  laboratorio) con la frecuencia cardiaca unos 9-10 lpm más alta de media (picos de 10 a 20 lpm en
  otro estudio), la piel del dedo unos 3,9 °C más
  caliente y la temperatura central de 0,2 a 0,6 °C más baja, que la falsa alarma medida no
  incluye. Lo leído, con su clase y lo buscado sin encontrar —cuántos sofocos al día con medida
  objetiva, cómo varían la temperatura, la frecuencia y la variabilidad en ciclos irregulares, y
  nada medido de la menopausia en vuelo—, está en `data/menopause_physiology_read.json`
  (`evidence/menopause_physiology.py`); no es una medida de EMMA.

## Lo que queda abierto

1. **Queda 1 de 22 sanos marcado** (`user_15`, cardiovascular: cinco lecturas
   por encima de 150 lpm con el acelerómetro fuera del cuerpo, ver hallazgo 28)
   **y 1 de 22 taquicardias sostenidas sin detectar.** El sistema discrimina
   bien, pero no es perfecto en ninguno de los dos lados.
2. **La deriva lenta no se puede validar con MMASH**, y así está declarado: los
   suelos de escalado solo cubren los deterioros que el dataset soporta. Hace
   falta un registro de semanas con deterioros documentados. Los dos escenarios
   de baja detección —progresiva 31,8 %, HRV 13,6 %— son consecuencia de esto,
   no del motor.
3. **Se perdió sensibilidad** frente al motor original (100 % → 13,6-95,5 %).
   Recuperarla sin devolver las falsas alarmas es el trabajo siguiente.
4. **`exercise-minutes` sigue siendo una guía.** No genera alertas, ni por
   desviación ni —desde el hallazgo 27— por tendencia: su tendencia se describe
   pero no cuenta como hallazgo. Fijar su umbral clínico necesita una cita que
   no se tiene.
5. **El contexto de esfuerzo nunca gana base personal** con el muestreo actual:
   8,3 % de las lecturas, unas 28 en la ventana de 14 días, frente a las 100
   mínimas. Degrada a límites de peligro absoluto, que es lo seguro, pero
   significa que EMMA sabe menos del esfuerzo que del reposo. Ver hallazgo 24.
6. **Falta un dataset con deterioros reales documentados.**
7. **La vía de gravedad por percentil no tiene validación.** En MMASH y en el
   simulador ninguna base alcanza las 1000 muestras que exige; solo la activa un
   wearable de alta cadencia. Hay dos efectos estimados sin medir: bases finitas
   (≈ el doble de lecturas graves con 1000 muestras) y autocorrelación. Ver
   hallazgo 26.
8. **Quedan 8 lecturas de HRV marcadas durante esfuerzo o digestión**, leves y
   sin escalar nunca. Restringir la HRV al reposo las quita pero apaga la
   detección del colapso de HRV (13,6 % → 0 %): medido y descartado, ver
   hallazgo 28. Separar `meal` de `rest` en su propia familia fragmentaría la
   muestra, que es lo que hundió el episodio agudo del 90 % al 20 %.
9. **La vía de tendencia no está validada con un wearable real de varios
   días.** Su ruido está autocorrelacionado —en el pulso de MMASH, el t de la
   pendiente sale inflado unas 2,2 veces— y el simulador no lo reproduce. El
   contraste contra el umbral clínico lo amortigua, pero no se ha medido. Ver
   hallazgo 27.
10. ~~Sin retardo de comunicaciones, una tendencia sola no llega a la
   tripulación.~~ **Resuelto** (hallazgo 27): se midió y se decidió que una
   deriva confirmada llegue sola a WATCH en cualquier régimen.
11. **El respaldo de familia sigue sin el reposo** (hallazgo 29). Con el reposo y la cobertura de
   la hora, medido en su rama: falsa alarma 0,1842 % → 0,1625 %, episodios por tripulante-semana
   3,63 → 3,18, pero el colapso de HRV detectado baja de 13,6 % a 9,1 %, bajo el suelo de 10 % de
   su prueba. No se adoptó ni se bajó el suelo (decisión del usuario, 2026-10-23): se mide antes con
   un conjunto de varias semanas. Leída la literatura (2026-10-23): respalda
   comparar a la misma hora y en la misma condición; 2 de 22 y 3 de 22 no se distinguen; y en
   MMASH toda la detección del colapso de HRV sale de comparar una lectura de primera hora con una
   base de la otra mitad del día. Recomendación: B con el suelo revisado; la regla llevada a toda
   base personal (variante C) se mide antes con LifeSnaps o RELAX (CC BY 4.0, varias semanas).
   Medido con LifeSnaps (hallazgo 31, sin adoptar): A y B no mueven nada visible y C baja un 7 % la
   falsa alarma y 0,3-1,0 puntos la señal neta, pero el conjunto no trae SDNN, así que el suelo sigue sin resolver.
12. **La vía de tendencia cuenta en presente un episodio ya cerrado** (hallazgo 30). Una regla de
   tres condiciones, medida y sin adoptar (decisión del usuario, 2026-10-26): en MMASH no se ejerce
   (24 h no dan tendencia) y las ocho cifras son idénticas; en el simulador no cierra nada en los
   deterioros ni en `nominal`, y en el escenario que cesa cierra 3, 2 y 3 de sus 4 indicadores según
   la semilla, así que el dominio sigue en vigilancia. No hace daño medible ni cumple su propósito;
   adoptarla, exigir un mínimo de lecturas por estrato o descartarla sigue pendiente.
13. **La variación por fase del ciclo menstrual no está medida ni controlada** (lote «ciclo»,
   2026-11-14). En una tripulante sin supresión menstrual, la fase lútea sube la temperatura
   (0,23-0,7 °C frente a la folicular, magnitud documentada) y la frecuencia cardiaca
   (3,42-3,91 lpm, de un solo estudio con wearable) y baja la RMSSD y la SDNN (sentido
   documentado, sin cifra en milisegundos que valga para el indicador): todo leído en
   `data/cycle_physiology_read.json`, con sus fuentes. Con el ruido de temperatura del simulador
   (0,18 °C), ese escalón puede salir como desviación de la base personal o como tendencia, y es
   una falsa alarma que no se ha medido. Queda abierto: medir las dos métricas juntas con una
   perturbación cíclica (tripulante sano con ciclo, y el ciclo más las inyecciones de referencia),
   y solo después decidir un ajuste por fase de la línea base que no tape una subida real. Lo
   hacen otras unidades del lote; aquí no se da ninguna cifra de falsa alarma del ciclo.
   **Medido y controlado en parte** (2026-11-15, hallazgos 32 y 32 bis): el ajuste por fase con su
   puerta baja WATCH de 63/71/75 a 26/43/52 de 84 sin bajar la sensibilidad. Sigue abierto: la RMSSD y
   la SDNN (sin cifra leída, sin ajuste), el primer ciclo sin ciclo cerrado propio, y cualquier
   medida con fisiología real de mujeres con ciclo.
14. **La perimenopausia y los sofocos no están medidos ni controlados** (lote «ciclo», unidad C1,
   2026-11-15). Muchas astronautas vuelan pasados los 40, y en una misión larga la perimenopausia
   es el caso probable. Dos huecos, leídos en `data/menopause_physiology_read.json`:
   (a) **los sofocos como falsa alarma**: la frecuencia cardiaca sube durante el sofoco
   (magnitud documentada por dos estudios de laboratorio pequeños: unos 9-10 lpm de media en uno,
   picos de 10 a 20 lpm en otro) y el control vagal cae
   (sentido documentado); un sofoco nocturno cabe entero en una sola lectura y puede salir como
   episodio agudo. El simulador no tiene sofocos y su falsa alarma no está medida; la frecuencia
   diaria con medida objetiva se buscó y no se encontró, y la conductancia esternal ambulatoria,
   la medida de referencia, coincide con lo que la mujer refiere en un 29 % de los casos: un pico
   sin declarar no se puede atribuir a un sofoco. (b) **Sin ciclo regular no hay fase**: en la
   perimenopausia tardía la mayoría de los ciclos son anovulatorios y no tienen el escalón lúteo,
   y cómo varían la temperatura, la frecuencia y la variabilidad en ciclos irregulares se buscó y
   no se encontró. Un ajuste por fase (punto 13) aplicado a quien no tiene ciclo regular restaría
   un escalón que no existe y podría tapar una subida real: no se aplica sin ciclo regular
   declarado (desde el 2026-11-15 la puerta de `api/cycle_phase.py` lo impone: con la
   perimenopausia declarada el estado es idéntico al de sin ajuste, hallazgo 32 bis). Del
   hueso: la NASA escribe que la pérdida lumbar en vuelo es «~10x» más rápida que al inicio de la
   menopausia, y nada de lo leído mide qué pasa cuando las dos coinciden; en vuelo no se ha medido
   nada de la menopausia (lo buscado, en `in_flight` del mismo fichero).

---

## Motor de medida ecográfica contra HC18 (2026-09-24)

MMASH valida el motor de constantes. La ecografía tiene otro motor —puntos en píxeles a
milímetros— y otra validación, contra **HC18** (Zenodo, doi:10.5281/zenodo.1327317, CC BY 4.0;
van den Heuvel et al., PLoS ONE 2018). Procedencia y licencia en `imaging-data-provenance.md`.

**Método.** Para cada una de las 999 imágenes del conjunto de entrenamiento se ajusta una elipse
al contorno anotado por el experto, se sacan sus dos diámetros como los marcaría un operador, se
miden con la función de distancia calibrada del motor (`imaging.measure.distance_mm`) usando el
tamaño de píxel que declara el dataset, y se reconstruye el perímetro (Ramanujan). Se compara con
el perímetro de referencia de los autores. Código: `app/validation/hc18.py`; pruebas:
`tests/test_imaging_hc18.py` (`-m external`).

| Métrica | Valor medido |
|---|---|
| Casos | 999 |
| Error absoluto mediano | 0,003 % |
| Percentil 95 | 0,01 % |
| Máximo | 0,024 % |
| Control negativo: escala desviada un 1 % | error mediano 1,0 % |

**Por qué el acuerdo es tan alto, y qué significa.** Los autores calcularon la referencia a partir
de la misma elipse que dibujaron, así que la prueba no mide error de nadie marcando calibres:
demuestra que **la conversión de escala y la distancia no introducen error**. Para que eso no sea
una validación incapaz de fallar, el control negativo desvía la calibración un 1 % y la prueba lo
detecta. Un fallo de escala —mm/píxel mal leído, ejes intercambiados— es justo el error silencioso
que produciría milímetros falsos con apariencia de medida.

**Lo que no demuestra:** la precisión de un operador, nada sobre nervio óptico, yugular o vejiga,
ni ningún umbral clínico. No hay ecografías abiertas de esas anatomías con licencia utilizable.

**Las dos métricas de la invariante 5** —falsa alarma y sensibilidad— **no aplican todavía** a la
ecografía: sus medidas no generan alertas (`clinical-decision-rationale.md`, "Lo que sigue
abierto"). Cuando las generen, tendrán que medirse las dos a la vez, como aquí.

**Fantomas.** Para demostración, `app/imaging/phantom.py` dibuja ecografías sintéticas de los tres
protocolos medibles con la medida real conocida. Entran firmadas como simuladas y la interfaz las
rotula así. Sus pruebas (`tests/test_imaging_phantom.py`) comprueban que la imagen dibujada casa
con la medida que declaran; no validan nada clínico.

---

## Datos reales de tripulación: hemograma de Inspiration4 (2026-09-24)

Lo más cercano a datos de astronauta que es público de verdad: el hemograma de los cuatro
tripulantes civiles de Inspiration4 (3 días en órbita, 2021), publicado procesado por NASA en OSDR
(OSD-569). Siete momentos por tripulante: L-92, L-44, L-3, R+1, R+45, R+82 y R+194. Sin muestras
en vuelo. Se reproducen en EMMA (`app/ingest/inspiration4.py`, `POST /api/replay/inspiration4`)
firmados como simulados, porque no son lecturas de esta tripulación; el fichero viaja con el
paquete y se verifica por su huella. Cita: "Data are courtesy of the NASA Open Science Data
Repository (https://osdr.nasa.gov/bio/repo)".

**Lo que enseñan.** Los linfocitos de **los cuatro** bajaron al volver (R+1 frente a L-3): de
2,667 a 1,640; de 2,873 a 1,540; de 3,156 a 2,086 y de 2,947 a 2,155 × 10³/µL, entre un 27 y un
46 %. Fijado como prueba (`test_the_real_signal_every_crew_member_lost_lymphocytes_on_return`).

**Lo que EMMA no hace con ellos, y se dice.** Esos valores de R+1 siguen dentro del rango de
referencia del laboratorio, y con siete muestras no hay línea base personal: **EMMA no alerta**
sobre esa bajada. Es coherente con su diseño —sin base personal solo vigila límites de peligro, y
los recuentos no tienen uno defendible— y es exactamente la limitación que declara `data.basis`.
Detectar una bajada así exigiría una línea base con pocas muestras, el mismo punto abierto que las
medidas ecográficas.

**Un fallo en origen, detectado y no corregido a mano.** La muestra de C003 en L-92 trae los
recuentos absolutos desplazados una columna —el "absoluto de linfocitos" es el valor de los
neutrófilos, y así con los demás— y también las plaquetas y los índices eritrocitarios. Como son
los mismos números permutados, la suma de absolutos cuadra con el total; lo que no cuadra es cada
absoluto con su porcentaje. La reproducción la aparta y lo declara en la respuesta
(`test_the_shifted_row_in_the_source_is_excluded_and_said`).

---

## Dolor referido: fuera de lo que esta validación cubre (2026-09-25)

`pain-intensity` (mapa corporal de dolor) **no está en MMASH**, que no registra dolor, y tampoco hay
un deterioro inyectado para él: `uncovered_indicators` lo lista entre lo que la validación no
alimenta. Las cifras de arriba no dicen nada de cómo se comporta. Lo que sí se comprobó al añadirlo:
las dos pruebas de regresión —`test_external_alarm_rate_does_not_regress` y
`test_sensitivity_does_not_regress`— siguen en verde, así que el cambio de dominios no movió ninguna
de las dos métricas. Por diseño no alerta sin línea base personal
(`clinical-decision-rationale.md`).

## Disciplina metodológica

**Las dos métricas van juntas o no sirve ninguna.**
`test_external_alarm_rate_does_not_regress` fija el techo de falsa alarma;
`test_sensitivity_does_not_regress` fija el suelo de detección. Sin la segunda,
apagar las alertas daría 0 % de falsas alarmas y pasaría la suite — y eso
**ocurrió de verdad** durante el desarrollo.

**Los umbrales se fijaron después de medir**, no antes, y anclan el valor
observado. Sirven para detectar empeoramientos, no para certificar que las cifras
sean buenas.

**Cada cambio se hizo tras diagnosticar su causa con datos**, nunca probando
parámetros a ver cuál sale mejor: dos bugs del cargador, dos guías usadas como
umbral, la ceguera al estado, el supuesto de normalidad y el respaldo
poblacional.

**Se publica el número tal cual.** El compromiso se adquirió antes de conocerlo.

## Segmentación local del visor 3D frente a la referencia (2026-09-26)

**Qué se mide:** cuánto coincide el hígado que segmenta TotalSegmentator en esta máquina (RTX 4070,
PyTorch 2.11 + CUDA 12.8, tarea `total`) con la máscara de referencia revisada por expertos del
dataset de TotalSegmentator (CC BY 4.0). Métrica: Dice. Prueba: `tests/test_volumes_external.py`.

**Solo con sujetos que el modelo no vio.** El dataset reparte sus TAC en `train`, `val` y `test`, y
TotalSegmentator se entrenó con los dos primeros. Medido primero con seis sujetos de `train` salió
0,986-0,992: un número que no valida nada, porque el modelo ya los había visto. La prueba solo
cuenta los de `test`.

| Sujeto (`test`) | Dice hígado |
|---|---|
| s0013 | 0,9945 |
| s0235 | 0,9939 |
| s0450 | 0,9936 |
| s0735 | 0,9912 |
| s0829 | 0,9904 |

Suelo de regresión: **0,98** (algo por debajo del mínimo medido). Si baja, ha cambiado el modelo,
sus pesos o la forma de llamarlo.

**Qué NO valida:** n = 5 y un solo órgano. Coincidir en el contorno del hígado no dice si se
detectan las lesiones que importan: las lesiones candidatas no tienen referencia en este dataset y
su sensibilidad no está medida. Nada de esto es fisiología de vuelo: son pacientes hospitalarios
(`risk-management-file.md`, H18).
