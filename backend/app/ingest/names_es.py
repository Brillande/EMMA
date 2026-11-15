"""El nombre en español de cada indicador del catálogo, con su origen declarado.

Por qué existe: el `display` del catálogo es el nombre de LOINC, en inglés, y tiene que seguir
así —es el `code.display` y el `code.text` de la `Observation` FHIR, y lo que un sistema de Tierra
lee—. Pero las frases que ve la tripulación lo metían tal cual: «Heart rate: 112 /min, por encima
de lo esperado», media frase en castellano y la otra media en el idioma de la ficha. Las
analíticas escaneadas ya se enseñaban con el nombre en español de Polaris, y el resto del catálogo
no tenía ninguno, así que una misma pantalla nombraba unos indicadores en un idioma y otros en
otro (decisión del usuario, 2026-10-20: una tabla de EMMA para el catálogo entero, rotulada).

Dos orígenes, y cada nombre dice el suyo:

  * `polaris` — los analitos de una analítica: el `nombre` del diccionario `ANALITOS` de Polaris
    (`polaris/tools/biomarcadores.py`), el mismo con que se enseña la lectura extraída. Se lee
    del `nombre` que `data/lab_loinc.json` ya guarda de cada analito, no cargando Polaris: así
    una frase del análisis (una desviación, una alerta) no depende de que la copia de Polaris
    importe, como no dependía antes. Que esa copia no se separe del original lo vigila una
    prueba (`test_the_polaris_names_are_the_ones_polaris_gives`), contra `reports.labs.names`.
  * `emma` — los demás (constantes vitales, PVT, sueño, ánimo, dosis, ejercicio, líquidos, escalas
    de nutrición, dolor, ecografía, los descriptivos): un nombre que redacta EMMA.

**Ninguno es un nombre de LOINC.** No se ha leído ninguna traducción de LOINC al español (si la
hay para alguno de estos códigos, queda sin verificar), y presentar una traducción propia como la
de la ficha sería el mismo disfraz que la invariante 1 prohíbe con los códigos. Por eso el rótulo
de cada origen lo dice con esas palabras, y la prueba (`tests/test_names_es.py`) lo exige.

Cada nombre de EMMA traduce la ficha del código sin cambiar lo que mide: «Frecuencia cardiaca» y
no «Pulso» para 8867-4, «Saturación de oxígeno en sangre arterial» para 2708-6 (es lo que dice
el código, aunque la lectura venga de un pulsioxímetro), «Densidad relativa de la orina» para
una propiedad adimensional (SpGrav). La unidad sigue a la propiedad (invariante 2) y no la cambia
el nombre: el nombre no la repite salvo donde la escala forma parte de lo que se mide (0-10, 9
puntos). Lo que un nombre de EMMA no hace es inventar contenido: si la ficha dice «autoinformado»,
el nombre también; si no lo dice, no se añade.

Convención de nombres de campo (escrita aquí el 2026-10-21; no se renombra ningún campo):

  * `display` en un objeto que nombra un indicador del catálogo (lleva su `key` o su código) es
    el `display` del catálogo, en inglés: el nombre de la ficha LOINC para un código LOINC y el
    que da EMMA, también en inglés, para uno de `https://emma.mission/codes`. Es lo que viaja
    en la `Observation` FHIR y lo que lee un sistema de Tierra; no es texto de pantalla.
  * `display_es` es el nombre en español de este módulo, el que ve la tripulación; su origen va
    en `display_es_origin` y `display_es_origin_display`.
  * Todo campo `*_display` (`trigger_display` en `analysis/alert_context.py`,
    `followup_checks_display` en `advisor/countermeasures.py`, `status_display`,
    `source_display`…) es texto de pantalla en español, compuesto en el backend para que la
    interfaz lo pinte tal cual. Si nombra indicadores, lo hace con `display_es`.

Fuera de un indicador del catálogo, un `display` suelto sigue la misma regla que `*_display`
(el rótulo de un estado, de una fuente, de una dimensión de coste): texto de pantalla en
español. La excepción es el `display` de un `Coding` o una `Reference` FHIR, que es el campo
de la especificación FHIR y lleva lo que esta pide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path

from app.core import i18n
from app.ingest.codes import CATALOG

# Solo la tabla de claves de Polaris a claves de EMMA, que es un diccionario: importar `labs` no
# carga la copia de Polaris (eso lo hace `labs._biomarkers`, al extraer).
from app.reports.labs import LAB_KEYS

# Fecha de la decisión del usuario y de la redacción de la tabla de EMMA.
DECIDED_ON = "2026-10-20"

# El código de cada analito de Polaris, con su `nombre` tal como está en su `ANALITOS`.
LAB_TABLE = Path(__file__).resolve().parents[1] / "data" / "lab_loinc.json"


class NameOrigin(StrEnum):
    """De dónde sale el nombre en español de un indicador."""

    POLARIS = "polaris"  # diccionario de analitos de Polaris (`biomarcadores.py`)
    EMMA = "emma"  # redactado por EMMA


# El rótulo que acompaña a cada nombre donde se publica su origen (`/api/indicators`). Los dos
# dicen que no es de LOINC: es lo que un consumidor no puede suponer al ver un nombre junto a
# un código LOINC.
ORIGIN_DISPLAY: dict[NameOrigin, str] = {
    NameOrigin.POLARIS: "nombre de Polaris (diccionario de analitos), no de LOINC",
    NameOrigin.EMMA: "nombre de EMMA, no de LOINC",
}

# Los indicadores que no son analitos de una analítica. Clave del catálogo → nombre de EMMA.
# Entre paréntesis, a la derecha, la ficha que traduce (el `display` del catálogo).
EMMA_NAMES: dict[str, str] = {
    # Cardiovascular
    "heart-rate": "Frecuencia cardiaca",  # Heart rate
    "respiratory-rate": "Frecuencia respiratoria",  # Respiratory rate
    "body-temperature": "Temperatura corporal",  # Body temperature
    # Oxygen saturation in Arterial blood
    "oxygen-saturation": "Saturación de oxígeno en sangre arterial",
    "systolic-bp": "Presión arterial sistólica",  # Systolic blood pressure
    "diastolic-bp": "Presión arterial diastólica",  # Diastolic blood pressure
    # R-R interval.standard deviation (Heart rate variability)
    "hrv-sdnn": "Variabilidad de la frecuencia cardiaca (desviación típica del intervalo R-R)",
    "hrv-rmssd": "Variabilidad de la frecuencia cardiaca (RMSSD)",  # Heart rate variability (RMSSD)
    # Orthostatic systolic drop on standing
    "orthostatic-drop": "Caída de la presión sistólica al ponerse en pie",
    # Internal jugular vein cross-sectional area, {side} (US)
    "ijv-csa-right": "Área de sección transversal de la vena yugular interna derecha (ecografía)",
    "ijv-csa-left": "Área de sección transversal de la vena yugular interna izquierda (ecografía)",
    # Oxygen consumption (VO2)/Body weight [Volume Rate Content] --peak during exercise
    "vo2-peak": "Consumo de oxígeno pico por kilo de peso durante el ejercicio (VO2 pico)",
    # Óseo
    "body-weight": "Peso corporal",  # Body weight
    "exercise-minutes": "Duración del ejercicio resistivo",  # Resistive exercise duration
    # Mechanical loading impacts (accelerometry)
    "loading-impacts": "Impactos de carga mecánica (acelerometría)",
    # Collagen crosslinked N-telopeptide [Moles/volume] in Urine
    "ntx-telopeptide": "Telopéptido N entrecruzado del colágeno (NTx) en orina",
    # 25-Hydroxyvitamin D3+25-Hydroxyvitamin D2 [Mass/volume] in Serum or Plasma
    "vitamin-d-25oh": "25-hidroxivitamina D3 más 25-hidroxivitamina D2 en suero o plasma",
    # Nutrición
    # Glucose [Mass/volume] in Capillary blood by Glucometer
    "glucose-capillary": "Glucosa en sangre capilar con glucómetro",
    # DXA Lumbar spine [Mass/Area] Bone density
    "bmd-dxa-lumbar-spine": "Densidad ósea de la columna lumbar por densitometría (DXA)",
    # DXA Hip [Mass/Area] Bone density
    "bmd-dxa-hip": "Densidad ósea de la cadera por densitometría (DXA)",
    # Conductual
    # Psychomotor vigilance task, mean reaction time
    "pvt-mean-rt": "Tiempo de reacción medio en la tarea de vigilancia psicomotora (PVT)",
    # Psychomotor vigilance task, lapses (RT > 500 ms)
    "pvt-lapses": "Lapsos en la tarea de vigilancia psicomotora (PVT; reacción de más de 500 ms)",
    "sleep-duration": "Duración del sueño",  # Sleep duration
    "sleep-efficiency": "Eficiencia del sueño",  # Sleep efficiency
    # Circadian phase shift from mission schedule
    "circadian-shift": "Desfase circadiano respecto al horario de misión",
    "mood-valence": "Valencia del ánimo autoinformada",  # Self-reported mood valence
    # NASA Task Load Index (NASA-TLX), overall weighted workload score
    "nasa-tlx-workload": (
        "Índice de carga de tarea de la NASA (NASA-TLX), puntuación global ponderada"
    ),
    # La batería Cognition (descriptivos, 2026-10-31): el nombre de cada prueba se traduce y su
    # sigla se deja como la escribe la fuente. La velocidad es la media de los tiempos de
    # respuesta; la precisión, una proporción de 0 a 1.
    # Cognition test battery, Motor Praxis Task (MPT), speed: average response time
    "cognition-mpt-speed": "Batería Cognition, praxis motora (MPT): tiempo de respuesta medio",
    # Cognition test battery, Visual Object Learning Task (VOLT), speed / accuracy
    "cognition-volt-speed": (
        "Batería Cognition, aprendizaje de objetos visuales (VOLT): tiempo de respuesta medio"
    ),
    "cognition-volt-accuracy": (
        "Batería Cognition, aprendizaje de objetos visuales (VOLT): proporción de aciertos"
    ),
    # Cognition test battery, Fractal 2-Back (F2B), speed / accuracy score, proportion
    "cognition-f2b-speed": (
        "Batería Cognition, memoria de trabajo 2-back con fractales (F2B): tiempo de respuesta "
        "medio"
    ),
    "cognition-f2b-accuracy": (
        "Batería Cognition, memoria de trabajo 2-back con fractales (F2B): puntuación de "
        "precisión (proporción)"
    ),
    # Cognition test battery, Abstract Matching (AM), speed / accuracy
    "cognition-am-speed": (
        "Batería Cognition, emparejamiento abstracto (AM): tiempo de respuesta medio"
    ),
    "cognition-am-accuracy": (
        "Batería Cognition, emparejamiento abstracto (AM): proporción de aciertos"
    ),
    # Cognition test battery, Line Orientation Task (LOT), speed / accuracy score, proportion
    "cognition-lot-speed": (
        "Batería Cognition, orientación de líneas (LOT): tiempo de respuesta medio"
    ),
    "cognition-lot-accuracy": (
        "Batería Cognition, orientación de líneas (LOT): puntuación de precisión (proporción)"
    ),
    # Cognition test battery, Emotion Recognition Task (ERT), speed / accuracy
    "cognition-ert-speed": (
        "Batería Cognition, reconocimiento de emociones (ERT): tiempo de respuesta medio"
    ),
    "cognition-ert-accuracy": (
        "Batería Cognition, reconocimiento de emociones (ERT): proporción de aciertos"
    ),
    # Cognition test battery, Matrix Reasoning Task (MRT), speed / accuracy
    "cognition-mrt-speed": (
        "Batería Cognition, razonamiento matricial (MRT): tiempo de respuesta medio"
    ),
    "cognition-mrt-accuracy": (
        "Batería Cognition, razonamiento matricial (MRT): proporción de aciertos"
    ),
    # Cognition test battery, Digit Symbol Substitution Task (DSST), speed / accuracy
    "cognition-dsst-speed": (
        "Batería Cognition, sustitución de dígitos por símbolos (DSST): tiempo de respuesta "
        "medio"
    ),
    "cognition-dsst-accuracy": (
        "Batería Cognition, sustitución de dígitos por símbolos (DSST): proporción de aciertos"
    ),
    # Cognition test battery, Balloon Analog Risk Test (BART), speed / risk score
    "cognition-bart-speed": (
        "Batería Cognition, prueba de riesgo del globo (BART): tiempo de respuesta medio"
    ),
    "cognition-bart-risk": (
        "Batería Cognition, prueba de riesgo del globo (BART): puntuación de riesgo (proporción "
        "de 0 a 1)"
    ),
    # Self-reported stress, visual analog scale of the Reaction Self Test (0 = not stressed,
    # 100 = very stressed)
    "stress-rating-vas": (
        "Estrés autoinformado en la escala visual analógica del Reaction Self Test (de 0 a 100)"
    ),
    # End of day survey (Spaceflight Standard Measures), team cohesion, agreement 1 to 7:
    # “<afirmación>”. La afirmación se deja como la escribe la fuente.
    "team-cohesion-cared": (
        "Cohesión del equipo, cuestionario de fin de día: acuerdo de 1 a 7 con «Our team members "
        "cared about each other»"
    ),
    "team-cohesion-task-focus": (
        "Cohesión del equipo, cuestionario de fin de día: acuerdo de 1 a 7 con «Our team was "
        "unified in its task focus»"
    ),
    "team-cohesion-shared-purpose": (
        "Cohesión del equipo, cuestionario de fin de día: acuerdo de 1 a 7 con «Shared sense of "
        "purpose and commitment»"
    ),
    # Radiación
    "absorbed-dose-rate": "Tasa de dosis de radiación absorbida",  # Absorbed radiation dose rate
    # Cumulative effective radiation dose
    "cumulative-dose": "Dosis efectiva de radiación acumulada",
    # Inmune
    "symptom-burden": "Carga de síntomas autoinformada",  # Self-reported symptom burden
    "cortisol-salivary": "Cortisol en saliva",  # Cortisol [Mass/volume] in Saliva (oral fluid)
    # Latent herpesvirus reactivation (EBV/VZV shedding)
    "latent-virus-shedding": "Reactivación de herpesvirus latentes (excreción de VEB/VVZ)",
    # Neuro-ocular
    # Optic nerve sheath diameter, {side} eye (US)
    "onsd-right": "Diámetro de la vaina del nervio óptico, ojo derecho (ecografía)",
    "onsd-left": "Diámetro de la vaina del nervio óptico, ojo izquierdo (ecografía)",
    # Change in vision since launch or the last in-flight exam (in-flight vision questionnaire)
    "vision-change": (
        "Cambio de visión desde el lanzamiento o el último examen en vuelo (cuestionario de "
        "visión en vuelo)"
    ),
    # Genitourinario
    # Urinary bladder Volume by derived from height, width and length (US)
    "bladder-volume": "Volumen vesical calculado del alto, el ancho y el largo (ecografía)",
    "fluid-intake-24h": "Ingesta total de líquidos en 24 horas",  # Fluid intake total 24 hour
    "urine-volume-24h": "Volumen de orina de 24 horas",  # Volume of 24 hour Urine
    "urine-specific-gravity": "Densidad relativa de la orina",  # Specific gravity of Urine
    # La química de la orina de 24 horas del riesgo de cálculos renales (descriptivos,
    # decisión del usuario del 2026-10-26). El urato de LOINC es lo que el informe llama ácido
    # úrico: el nombre dice el de la ficha.
    # Calcium [Mass/time] in 24 hour Urine
    "urine-calcium-24h": "Calcio en orina de 24 horas (masa por día)",
    # Oxalate [Mass/time] in 24 hour Urine
    "urine-oxalate-24h": "Oxalato en orina de 24 horas (masa por día)",
    # Urate [Mass/time] in 24 hour Urine
    "urine-urate-24h": "Urato en orina de 24 horas (masa por día)",
    # Citrate [Mass/time] in 24 hour Urine
    "urine-citrate-24h": "Citrato en orina de 24 horas (masa por día)",
    "urine-ph-24h": "pH de la orina de 24 horas",  # pH of 24 hour Urine
    # Sodium [Moles/time] in 24 hour Urine
    "urine-sodium-24h": "Sodio en orina de 24 horas (sustancia por día)",
    "urine-osmolality-24h": "Osmolalidad de la orina de 24 horas",  # Osmolality of 24 hour Urine
    # Calcium oxalate relative supersaturation, calculated from 24 hour urine
    "urine-caox-supersaturation-24h": (
        "Sobresaturación relativa del oxalato cálcico, calculada de la orina de 24 horas"
    ),
    # Musculoesquelético
    # Pain severity - 0-10 verbal numeric rating [Score] - Reported
    "pain-intensity": (
        "Intensidad del dolor en la escala numérica verbal de 0 a 10 (autoinformada)"
    ),
    # Grip strength Hand - {side} Dynamometer
    "grip-strength-right": "Fuerza de prensión de la mano derecha (dinamómetro)",
    "grip-strength-left": "Fuerza de prensión de la mano izquierda (dinamómetro)",
    # Sensoriomotor y músculo, descriptivos (decimonovena ronda, 2026-10-31).
    # Tandem walk test, percent of correct heel-to-toe steps (Spaceflight Standard Measures)
    "tandem-walk-correct-steps": (
        "Marcha en tándem, porcentaje de pasos talón-punta correctos (Standard Measures)"
    ),
    # Recovery-from-fall test, time from the command to stand to a stable posture (Spaceflight
    # Standard Measures)
    "recovery-from-fall-time": (
        "Levantarse tras estar tumbado, tiempo desde la orden hasta la postura estable "
        "(Standard Measures)"
    ),
    # Lean (soft tissue) mass, whole body, by DXA body composition
    "dxa-lean-mass": "Masa magra del cuerpo entero por densitometría (DXA)",
    # Isometric mid-thigh pull (IMTP), peak force on a force plate
    "imtp-peak-force": (
        "Tracción isométrica a medio muslo (IMTP), fuerza máxima en plataforma de fuerza"
    ),
    # Nutrición
    "energy-intake-daily": "Ingesta energética diaria",  # Energy intake per day
    "appetite-rating": "Apetito autoinformado (0-10)",  # Appetite self-rating (0-10)
    # Fraction of served food left uneaten
    "food-rejected-fraction": "Fracción de la ración servida que se deja sin comer",
    # Food acceptability, 9-point hedonic scale
    "food-acceptability": "Aceptabilidad de la comida en la escala hedónica de 9 puntos",
    # Nutrientes ingeridos al día (descriptivos, 2026-10-31). Los dos de LOINC traducen su ficha
    # («… intake 24 hour»); los dos propios, el nombre que les da EMMA.
    "sodium-intake-daily": "Sodio ingerido al día",  # Sodium intake per day
    "calcium-intake-daily": "Calcio ingerido en 24 horas",  # Calcium intake 24 hour
    "protein-intake-daily": "Proteína ingerida en 24 horas",  # Protein intake 24 hour
    "vitamin-d-intake-daily": "Vitamina D ingerida al día",  # Vitamin D intake per day
    # El ciclo menstrual y la anticoncepción (descriptivos, 2026-11-14): códigos propios de EMMA
    # con las categorías de HealthKit.
    # Menstrual flow amount, HealthKit categories (none, light, medium, heavy)
    "menstrual-flow": "Cantidad de flujo menstrual (categorías de HealthKit)",
    # Start of a menstrual cycle (HealthKit menstrual cycle start flag)
    "menstruation-start": "Inicio de un ciclo menstrual",
    # Intermenstrual bleeding (spotting outside the menstruation period), recorded or not
    "intermenstrual-bleeding": "Sangrado intermenstrual (manchado fuera de la regla)",
    # Ovulation home test result, HealthKit categories (negative, estrogen surge, LH surge)
    "ovulation-test": "Resultado del test casero de ovulación (categorías de HealthKit)",
    # Contraceptive in use, HealthKit contraceptive types (nominal, numbered by EMMA)
    "contraceptive-in-use": "Anticonceptivo en uso (tipos de HealthKit)",
    # Basal body temperature (at rest, immediately after waking)
    "basal-body-temperature": "Temperatura basal (en reposo, al despertar)",
    # El estado reproductivo, la terapia hormonal de la menopausia y los síntomas vasomotores
    # (descriptivos, 2026-11-15): códigos propios de EMMA.
    # Declared reproductive status (nominal, categories by EMMA from STRAW+10, HealthKit and
    # menstrual suppression in astronauts)
    "reproductive-status": "Estado reproductivo declarado (categorías de EMMA)",
    # Menopausal hormone therapy in use, declared (no or yes)
    "menopausal-hormone-therapy": "Terapia hormonal de la menopausia en uso (declarada)",
    # Hot flashes severity, HealthKit symptom categories (not present, mild, moderate, severe)
    "hot-flashes": "Sofocos: gravedad (categorías de HealthKit)",
    # Night sweats severity, HealthKit symptom categories (not present, mild, moderate, severe)
    "night-sweats": "Sudores nocturnos: gravedad (categorías de HealthKit)",
}


@dataclass(frozen=True)
class SpanishName:
    """El nombre en español de un indicador y de dónde sale."""

    text: str
    origin: NameOrigin

    @property
    def origin_display(self) -> str:
        return ORIGIN_DISPLAY[self.origin]


@cache
def polaris_names() -> dict[str, str]:
    """Indicador de EMMA → el `nombre` de Polaris que guarda `data/lab_loinc.json` de su analito."""
    analytes = json.loads(LAB_TABLE.read_text(encoding="utf-8"))["analytes"]
    return {
        LAB_KEYS[str(item["key"])]: str(item["nombre"])
        for item in analytes
        if str(item["key"]) in LAB_KEYS
    }


@cache
def _table() -> dict[str, SpanishName]:
    """El nombre de cada indicador del catálogo, calculado una vez.

    Un analito de analítica se nombra como lo nombra Polaris aunque EMMA tuviera un nombre suyo:
    así su lectura extraída y las frases que la citan dicen lo mismo.
    """
    table: dict[str, SpanishName] = {}
    for key in CATALOG:
        from_polaris = polaris_names().get(key)
        if from_polaris is not None:
            table[key] = SpanishName(from_polaris, NameOrigin.POLARIS)
        else:
            table[key] = SpanishName(EMMA_NAMES[key], NameOrigin.EMMA)
    return table


def spanish_name(key: str) -> SpanishName:
    """El nombre en español de un indicador del catálogo, o `KeyError` si no es del catálogo."""
    if key not in CATALOG:
        raise KeyError(f"indicador desconocido: {key!r}")
    return _table()[key]


# El nombre en inglés es el del catálogo (`display`, la ficha de LOINC o la del código propio): no
# se redacta otro. `name_es` y el campo `display_es` conservan el nombre por historia; desde que
# hay dos idiomas (2026-11-15, `core/i18n.py`) dan el nombre de pantalla en el idioma pedido.
CATALOG_ORIGIN = "catalog"
CATALOG_ORIGIN_DISPLAY = "catalogue name (the LOINC record, or EMMA's own code)"


def name_es(key: str) -> str:
    if i18n.current() == "en":
        if key not in CATALOG:
            raise KeyError(f"indicador desconocido: {key!r}")
        return CATALOG[key].display
    return spanish_name(key).text


def fields(key: str) -> dict[str, str]:
    """El nombre en español con su origen y su rótulo, como lo publica `/api/indicators`."""
    if i18n.current() == "en":
        return {
            "display_es": name_es(key),
            "display_es_origin": CATALOG_ORIGIN,
            "display_es_origin_display": CATALOG_ORIGIN_DISPLAY,
        }
    name = spanish_name(key)
    return {
        "display_es": name.text,
        "display_es_origin": str(name.origin),
        "display_es_origin_display": name.origin_display,
    }
