# Decisión: ¿entra la sobresaturación de la brushita?

*Preparado el 2026-11-05. Es el «Pendiente» de `docs/contexto/README.md` y de
`compliance/hmi-state-of-the-art.md` §5.38 («Qué queda»). No hay ningún cambio de código.*

## Qué es

La brushita es fosfato cálcico dihidratado (CaHPO₄·2H₂O). Es la sal de los cálculos de fosfato
cálcico, el segundo tipo después del oxalato cálcico. Su **sobresaturación relativa** la calcula
el laboratorio a partir de la química de la orina de 24 horas (calcio, fosfato, pH, volumen…). Es
un cociente sin unidad: cuánto se aleja la orina del equilibrio con esa sal. Por encima de 1, la
sal tiende a precipitar. Hoy EMMA registra la sobresaturación del oxalato cálcico
(`urine-caox-supersaturation-24h`, código propio). La de la brushita está en `pending` de la fila
del riesgo renal (`data/hrp_risks_coverage.json`).

## ¿La respalda una fuente leída? Sí

Es el mismo informe de evidencia del HRP que respalda la del oxalato cálcico
(`hrp-renal-stone-evidence-report`). Las frases ya están en `data/instruments_read.json`:

- p. 12, `renal-iss-supersaturation`: «brushite and calcium oxalate supersaturation risk
  increased by 150% and 115% during flight, respectively».
- p. 20, `renal-bedrest-relative-saturation`: «the relative saturation of calcium oxalate,
  brushite, and undissociated uric acid».
- p. 19, `renal-supersaturation-calculated-after-return`: la sobresaturación se calcula después
  del regreso, en Tierra.

En vuelo, la subida de la brushita (150 %) es **mayor** que la del oxalato cálcico (115 %), que sí
se registra.

## ¿Tiene LOINC? Sí, y esto cambia el planteamiento

Para el oxalato cálcico, la búsqueda del 2026-10-26 (`ingest/codes.py`, `api/descriptive.py`) no
encontró código. En esa misma búsqueda ya salió el de la brushita. Se ha comprobado de nuevo hoy
con `$lookup` en tx.fhir.org (LOINC 2.83):

- **LOINC 42673-4**: «Calcium hydrogen phosphate dihydrate [Saturation Fraction] in 24 hour Urine».
- Estado **ACTIVE**, clase CHEM, sistema orina, TIME_ASPCT 24H, escala cuantitativa, ORDER_OBS
  `Observation`.
- Propiedad LP36180-5 (**SatFr**, fracción de saturación). Entre sus nombres relacionados están
  «Brushite», «Relative Supersaturation» y «RS». El propio LOINC lo da como la sobresaturación
  relativa de la brushita.

Por tanto, la invariante 1 obliga a **usar 42673-4 y no un código propio**. Las dos sales quedarían
codificadas de forma distinta, y eso es lo correcto: la del oxalato cálcico usa código propio
porque LOINC no tiene su SatFr (solo 81623-1, que es una energía, y 34736-9, un índice).

**Invariante 2, a comprobar en la implementación.** La ficha no dio unidad de ejemplo en el
`$lookup`. Una fracción de saturación es adimensional, y lo natural es la unidad UCUM `1`, igual
que el cociente del oxalato cálcico. Antes de fijarla hay que leer la ficha completa en loinc.org
(EXAMPLE_UCUM_UNITS) y decidir cómo se escribe: como cociente (`1`) o en porcentaje. Mezclar las
dos formas sería el error silencioso de la invariante 2.

## Coste de añadirla

Es pequeño y conocido, porque reproduce el camino de la del oxalato cálcico (§5.38):

- `ingest/codes.py`: una entrada LOINC 42673-4 en `RENAL_URINE_CHEMISTRY`. Lleva unidad `1`, si la
  ficha lo confirma, y es descriptiva: el estado no la lee, no tiene umbral y no cuenta en la
  huella.
- `names_es.py`, `core/display.py` (dos decimales) y la medida leída en `instruments_read.json`
  (con las tres frases de arriba).
- `measurement_cost.json`, que reutiliza la regla `perfil-litiasico-en-tierra`.
- `hrp_risks_coverage.json`: el analito pasa de `pending` a `in_catalog`, y `pending` queda vacío.
- Pruebas: `test_descriptive_indicators.py`, `test_hrp_coverage.py`, la campaña de mutantes
  `hrp_coverage.json` y el fixture de `frontend/src/ground/hrpCoverageMarks.test.ts`.
- `docs/contexto/README.md` y §5.38: cerrar el pendiente.
- Riesgo para la validación: **ninguno**. Al ser descriptiva, no toca la falsa alarma ni la
  sensibilidad (invariante 5). `rules_version` no cambia.

Es una unidad de trabajo de unas horas, sin red en las pruebas.

## Recomendación

**Que entre, con LOINC 42673-4 y no con código propio**, como indicador descriptivo igual que el
del oxalato cálcico. Hay fuente leída, el aumento en vuelo es el mayor de los dos y el código
estándar existe y está activo. El coste es bajo y no afecta a la validación. Antes de implementarla
queda un solo paso abierto: confirmar en la ficha de loinc.org la unidad de ejemplo de 42673-4.
