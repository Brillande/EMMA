# Trazabilidad a NASA-STD-3001

**Fuente:** NASA-STD-3001 Volume 1, Revision C — *Crew Health*, y su
Appendix D *Requirements Compliance Matrix*.
**Extracción:** 2026-09-20, del PDF oficial publicado por NASA.
**Estado:** 15 requisitos identificados como aplicables.

Todos los identificadores y las citas entrecomilladas de este documento están
**extraídos del PDF oficial**, no reconstruidos de memoria. La regla del
proyecto se mantiene: no se cita un ID de requisito que no se haya leído en el
documento fuente.

Documentos:
- [Volume 1 Rev C](https://www.nasa.gov/wp-content/uploads/2023/11/nasa-std-3001-vol-1-rev-c-with-signature.pdf)
- [Appendix D Requirements Compliance Matrix](https://www.nasa.gov/wp-content/uploads/2025/07/nasa-std-3001-vol-1-app-d-requirements-compliance-matrix.pdf)

---

## El requisito central

**[V1 3004]**, apartado **h**, es la razón de ser de este software:

> "Assessing, recording, monitoring, and trending vital signs and additional
> physiological and behavioral health signs."

El cuerpo del mismo requisito confirma dos decisiones de diseño que se tomaron
antes de leerlo, y que resultan estar en el estándar:

> "In-mission capabilities (**including hardware and software**), resources
> (including consumables), and training to enable in-mission medical care, and
> behavioral care, are to include, but are not limited to: […]"

> "…with particular attention to parameters such as mission duration,
> **expected return time to Earth**, mission route and destination, expected
> radiation profile, concept of operations, and more."

El "expected return time to Earth" como parámetro de diseño del sistema médico
es exactamente lo que implementa `isolation_factor()`: el retardo de
comunicaciones no es contexto decorativo, es una entrada del diseño clínico.

---

## Matriz

Cobertura: **completa** = el sistema implementa el requisito en su alcance de
software · **parcial** = lo cubre en parte, con el límite declarado ·
**contexto** = el requisito informa el diseño pero su cumplimiento es del
programa, no del software.

| ID | Requisito (extracto textual) | Cobertura | Implementación |
|---|---|---|---|
| **[V1 3004] h** | "Assessing, recording, monitoring, and trending vital signs and additional physiological and behavioral health signs." | Completa | `ingest/fhir.py` (registro), `analysis/baseline.py` (monitorización), `analysis/trend.py` (tendencia), `core/storage.py` (persistencia auditada). Signos referidos: mapa corporal de dolor con zona, intensidad (LOINC 72514-3) y tipo, y su evolución (`app/pain/`) |
| **[V1 3003]** | "…in-mission capabilities, and resources to monitor physiological and psychosocial well-being and enable delivery of in-mission preventive health care…" | Completa | `analysis/risk.py` + `advisor/recommendations.py`: dominios fisiológicos y conductual con contramedidas preventivas |
| **[V1 4011]** | "Pre-mission, in-mission, and post-mission crew behavioral health and crewmember cognitive state shall be within clinically accepted values…" | Parcial | `ingest/pvt.py` da la medida objetiva de estado cognitivo; la evaluación conductual formal la hace un profesional, no el software |
| **[V1 4014]** | "The planned number of hours for in-mission completion of critical tasks and events, workday, physical activity/exercise, and planned sleep period shall have established limits…" | Parcial | Se monitoriza `sleep-duration` y `exercise-minutes` frente a sus límites; la planificación del horario es del programa |
| **[V1 4017]** | "Countermeasures and monitoring shall ensure immune and hematology values remain outside the critical values…" | Parcial | Dominio inmune: `symptom-burden`, `cortisol-salivary`, `latent-virus-shedding`. No hay hematología de a bordo |
| **[V1 4027]** | "Countermeasures shall maintain bone mineral density of the hip and spine at or above 95% of pre-mission values and at or above 90% for the femoral neck." | Parcial | **No se mide densidad ósea**: no hay DXA a bordo. Se monitoriza la adherencia a la contramedida (`exercise-minutes`, `loading-impacts`) y el marcador de resorción `ntx-telopeptide` (LOINC 27939-8) |
| **[V1 4024]** | "Countermeasures shall maintain in-mission skeletal muscle strength at or above 80% of baseline values." | Parcial | `exercise-minutes` cubre la adherencia; no se mide fuerza directamente |
| **[V1 4003]** | "The in-mission aerobic capacity shall be maintained… at or above 80% of the pre-mission capacity…" | Parcial | Proxy cardiovascular (FC en reposo, HRV); no hay prueba de esfuerzo a bordo |
| **[V1 4029]** | "All crewmember radiation exposures shall be minimized using the ALARA principle." | Completa | Alerta de evento solar con acción de refugio (`advisor`), alimentada por NASA DONKI |
| **[V1 4030]** | "An individual crewmember's total career effective radiation dose due to spaceflight radiation exposure shall be **less than 600 mSv**. This limit is universal for all ages and sexes." | Completa | `Settings.career_dose_limit_msv = 600.0`. El 100 % del límite entra por sí solo en nivel CRITICAL |
| **[V1 6001]** | "Crew schedule planning and operations shall be provided to include circadian entrainment, work/rest schedule assessment…" | Parcial | `circadian-shift` mide el desfase; la recomendación de reanclaje lumínico está en `advisor` |
| **[V1 3018]** | "Crewmembers returning from spaceflight shall be monitored longitudinally for health, behavioral health, and well-being parameters in a standardized manner." | Completa | Modelo canónico FHIR R4 + almacén append-only con integridad verificable: el "standardized manner" y la conservación a largo plazo |
| **[V1 3002]** | "Pre-mission preventive strategies shall be used to reduce in-mission and long-term health medical risks…" | Contexto | La línea base preflight (`BaselineEngine.fit`) sirve a la comparación longitudinal |
| **[V1 4012]** | "End-of-mission assessment and treatment for crewmember cognitive status shall include cognitive assessment, monitoring…" | Parcial | Serie histórica de PVT disponible para la evaluación de fin de misión |
| **[V1 4010]** | "Post-mission reconditioning shall be monitored and aimed at returning to baseline sensorimotor function." | Contexto | La base preflight conservada es la referencia de retorno |

---

## Validación que aportó la lectura del estándar

**El límite de dosis ya era correcto.** `career_dose_limit_msv = 600.0` se había
elegido antes de leer el Appendix D, y **[V1 4030]** lo fija exactamente en ese
valor, universal para todas las edades y sexos. Queda confirmado contra la
fuente en lugar de ser un número plausible.

**Una limitación que el estándar hace explícita, investigada hasta el fondo.**
[V1 4030] añade que la dosis efectiva de NASA se calcula con el modelo NASA Q y
parámetros de mujer de 35 años. Ese modelo necesita el espectro de partículas.
Se comprobó empíricamente que **OSDR RadLab no lo proporciona**:

- `quality_factor`, `lineal_energy` y `let` devuelven HTTP 500: no existen.
- `dose_equivalent_rate` existe en el esquema pero **nunca está poblado**:
  98 688 filas revisadas en cuatro ventanas entre 2011 y 2022, con diez
  instrumentos distintos, todas nulas.

Así que NASA Q no es implementable con esta fuente. No es una carencia de la
implementación: es un límite del dato, establecido midiéndolo.

Lo que sí se hizo, y corrigió un error de magnitud: la versión anterior integraba
con **Q = 1**, que subestima la dosis equivalente unas dos veces y media.
`app/environment/dosimetry.py` implementa ahora la función Q(L) de **ICRP 60**
—lista para cuando haya espectro— y aplica mientras tanto un factor de calidad
medio **medido en vuelo**, con la estimación viajando siempre acompañada de su
procedencia.

El contraste con datos reales de DosTel del 2022-04-01 (2391 muestras, 24,0 h de
cobertura) lo valida:

| Factor de calidad | Dosis | mSv/día |
|---|---|---|
| Q = 1 (anterior) | 0,272 mSv | 0,272 — **por debajo** del rango documentado |
| Atrapada, Q = 1,83 | 0,497 mSv | 0,497 |
| **Media de misión, Q = 2,38** | **0,647 mSv** | **0,647 — centro del rango** |
| Galácticos, Q = 2,74 | 0,745 mSv | 0,745 |

El rango documentado para la ISS es 0,3-0,8 mSv/día. Con Q = 1 el sistema
informaba por debajo de lo que realmente recibe la tripulación.

---

## Volumen 2, Apéndice F: la norma de pantallas

**Fuente:** NASA-STD-3001 Volume 2, **Revision F** (aprobada el 2026-07-14), Appendix F *Display
Standard*, extraído del [PDF oficial](https://www.nasa.gov/wp-content/uploads/2025/05/nasa-std-3001-vol-2.pdf)
el 2026-09-23. Rige la interfaz, no el motor clínico.

El apéndice se aplica a *"flight elements only (not ground)"*: la consola de tripulación está dentro
de su alcance y la de Tierra fuera. La matriz regla por regla, las cuatro desviaciones declaradas
(ASCII, separador de millares, frecuencia de parpadeo, supresión e inhibición de alertas) y los
choques con IEC 60601-1-8 están en [`hmi-state-of-the-art.md`](hmi-state-of-the-art.md) §1-2.

Una regla que conecta directamente con el motor:

> "Automated systems that provide decisions or recommendations must provide explanation with
> rationale for the decision or recommendation." (F.6.2)

Cada recomendación de `advisor/` ya lleva su `rationale` y su evidencia enlazada. La norma de
pantallas pide lo mismo que la exención CDS citada en `state-of-the-art.md`, con otras palabras.

**Estado:** implementado en `frontend/`, con un test por cada regla verificable. La relación entre
reglas y pruebas, y lo que queda pendiente (indicador del nivel de automatización de F.6.2 y
búsqueda de alertas de F.6.4), están en `hmi-state-of-the-art.md` §5.

---

## Alcance de lo que este documento afirma

Esta matriz declara **qué hace el software respecto a cada requisito**. No es
una declaración de cumplimiento del programa: la mayoría de estos requisitos
aplican a un programa de vuelo completo —entrenamiento, consumibles, personal
médico, hardware— del que el software es una parte.

Las filas marcadas *parcial* dicen explícitamente qué queda fuera. Ninguna
reclama una capacidad que el sistema no tenga.
