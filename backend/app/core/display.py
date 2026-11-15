"""Cifras y unidades dentro del texto que lee la tripulacion.

POR QUE EXISTE
--------------
El backend escribe frases con cifras dentro ("Sleep duration: 1.978 h, por debajo
del limite de peligro (3 h)"), y la interfaz las muestra tal cual: no reescribe
texto clinico (invariante 7 de CLAUDE.md). Asi que la forma de esas cifras es
responsabilidad de quien escribe la frase. Salian con punto decimal en un texto en
espanol, con tres decimales en una duracion de sueno y con unidades UCUM en crudo
("0.39 {score}/semana").

Las reglas son las de la interfaz (`frontend/src/lib/format.ts`), que a su vez
siguen NASA-STD-3001 Vol 2, Apendice F.5.6, con las dos desviaciones declaradas en
`compliance/hmi-state-of-the-art.md` §2.3: coma decimal y espacio fino para los
millares.

LOS DECIMALES SON UNA DECISION POR INDICADOR
--------------------------------------------
F.5.6 c: *"The number of decimal places shown must be the number required by
operators to perform the associated task."* Un pulso no necesita decimales; un
cortisol en ug/dL necesita dos. No hay un valor por defecto: todo indicador del
catalogo tiene que figurar en `DECIMALS`, y la suite lo comprueba. Es la misma
regla que la de justificar los codigos propios: un indicador nuevo obliga a decidir
como se lee.
"""

from __future__ import annotations

import math

from app.core import i18n

DECIMAL = ","
# Espacio fino que no parte linea: U+202F, invisible en el editor.
GROUP = " "
# F.5.6 j: separador de millares a partir de cinco digitos.
GROUP_FROM_DIGITS = 5

DECIMALS: dict[str, int] = {
    "heart-rate": 0,
    "respiratory-rate": 0,
    "body-temperature": 1,
    "oxygen-saturation": 0,
    "systolic-bp": 0,
    "diastolic-bp": 0,
    "body-weight": 1,
    "hrv-sdnn": 0,
    "hrv-rmssd": 0,
    "orthostatic-drop": 0,
    "pvt-mean-rt": 0,
    "pvt-lapses": 0,
    "sleep-duration": 1,
    "sleep-efficiency": 0,
    "circadian-shift": 1,
    "mood-valence": 1,
    "absorbed-dose-rate": 1,
    "cumulative-dose": 1,
    "exercise-minutes": 0,
    "loading-impacts": 0,
    "ntx-telopeptide": 0,
    "symptom-burden": 1,
    "cortisol-salivary": 2,
    "latent-virus-shedding": 0,
    # La vaina del nervio optico cambia en decimas de milimetro: sin decimal, una
    # distension de 0,4 mm no se veria.
    "onsd-right": 1,
    "onsd-left": 1,
    "ijv-csa-right": 0,
    "ijv-csa-left": 0,
    "bladder-volume": 0,
    # Recuentos en miles por microlitro: 1,64 y 1,6 no son la misma cifra para un linfocito.
    "leukocytes": 1,
    "lymphocytes": 2,
    "neutrophils": 2,
    # La escala numerica verbal es de enteros: nadie informa un dolor de 6,4.
    "pain-intensity": 0,
    "fluid-intake-24h": 0,
    "urine-volume-24h": 0,
    # La densidad de la orina se lee con tres decimales (1,020): con menos, no se ve.
    "urine-specific-gravity": 3,
    "energy-intake-daily": 0,
    "food-acceptability": 1,
    "appetite-rating": 0,
    "food-rejected-fraction": 0,
    # Analíticas escaneadas: los decimales con que los informa un laboratorio.
    "neutrophils-percent": 1,
    "lymphocytes-percent": 1,
    "neutrophil-lymphocyte-ratio": 2,
    "c-reactive-protein": 2,
    "erythrocytes": 2,
    "hemoglobin": 1,
    "hematocrit": 1,
    "mcv": 1,
    "mch": 1,
    "mchc": 1,
    "platelets": 0,
    "urea": 0,
    "creatinine": 2,
    "bun-creatinine-ratio": 1,
    "sodium": 0,
    "potassium": 1,
    "chloride": 0,
    "calcium": 1,
    "phosphate": 1,
    "magnesium": 1,
    "estradiol": 0,
    "fsh": 1,
    "lh": 1,
    "glucose": 0,
    "total-protein": 1,
    "albumin": 1,
    "ast": 0,
    "alt": 0,
    "ggt": 0,
    "alkaline-phosphatase": 0,
    "bilirubin-total": 1,
    "bilirubin-direct": 1,
    "ldh": 0,
    "tsh": 2,
    "free-t4": 2,
    "ca-15-3": 1,
    "cea": 1,
    "ca-125": 1,
    "ca-19-9": 1,
    "ca-27-29": 1,
    "beta2-microglobulin": 2,
    "chromogranin-a": 0,
    "neuron-specific-enolase": 1,
    # Indicadores descriptivos (`codes.DESCRIPTIVE_ONLY`). El cuestionario de visión es de
    # categorías: enteros. La puntuación global del NASA-TLX es una media ponderada dividida por
    # 15, que no cae en enteros. El VO2 pico y la prensión se leen con un decimal, como la
    # vitamina D 25-OH en ng/mL.
    "vision-change": 0,
    "nasa-tlx-workload": 1,
    "vo2-peak": 1,
    "grip-strength-right": 1,
    "grip-strength-left": 1,
    "vitamin-d-25oh": 1,
    # La glucosa capilar, en enteros como la de laboratorio: mg/dL sin decimales.
    "glucose-capillary": 0,
    # La química de la orina de 24 horas (descriptivos del riesgo de cálculos renales). Las masas
    # y el sodio por día, en enteros, como los escribe el informe («300mg/day», «470 to 700 mg a
    # day»); el pH con dos decimales, como lo escribe («5.90 to 6.46»); la osmolalidad en enteros;
    # la sobresaturación relativa, un cociente, con dos.
    "urine-calcium-24h": 0,
    "urine-oxalate-24h": 0,
    "urine-urate-24h": 0,
    "urine-citrate-24h": 0,
    "urine-ph-24h": 2,
    "urine-sodium-24h": 0,
    "urine-osmolality-24h": 0,
    "urine-caox-supersaturation-24h": 2,
    # La densidad ósea por DXA se da en g/cm² con tres decimales (0,987): con menos, un cambio
    # del 1 % no se vería.
    "bmd-dxa-lumbar-spine": 3,
    "bmd-dxa-hip": 3,
    # Sensoriomotor y músculo (descriptivos, 2026-10-31). El porcentaje de pasos correctos de
    # diez pasos cae en enteros; el tiempo hasta la postura estable se lee en décimas de segundo;
    # la masa magra con un decimal, como el peso; la fuerza máxima de la tracción, en newtons
    # enteros (una plataforma de fuerza da miles).
    "tandem-walk-correct-steps": 0,
    "recovery-from-fall-time": 1,
    "dxa-lean-mass": 1,
    "imtp-peak-force": 0,
    # La batería Cognition (descriptivos, 2026-10-31): la velocidad es una media de tiempos de
    # respuesta en milisegundos, en enteros como la de la PVT; la precisión y el riesgo son
    # proporciones de 0 a 1, con dos decimales (0,85).
    "cognition-mpt-speed": 0,
    "cognition-volt-speed": 0,
    "cognition-volt-accuracy": 2,
    "cognition-f2b-speed": 0,
    "cognition-f2b-accuracy": 2,
    "cognition-am-speed": 0,
    "cognition-am-accuracy": 2,
    "cognition-lot-speed": 0,
    "cognition-lot-accuracy": 2,
    "cognition-ert-speed": 0,
    "cognition-ert-accuracy": 2,
    "cognition-mrt-speed": 0,
    "cognition-mrt-accuracy": 2,
    "cognition-dsst-speed": 0,
    "cognition-dsst-accuracy": 2,
    "cognition-bart-speed": 0,
    "cognition-bart-risk": 2,
    # El estrés de la escala visual analógica (de 0 a 100) y el acuerdo de 1 a 7 con cada
    # afirmación de cohesión: enteros.
    "stress-rating-vas": 0,
    "team-cohesion-cared": 0,
    "team-cohesion-task-focus": 0,
    "team-cohesion-shared-purpose": 0,
    # Nutrientes ingeridos al día (descriptivos, 2026-10-31): el sodio y el calcio en miligramos
    # enteros y la proteína en gramos enteros, como los escribe una tabla de composición; la
    # vitamina D en microgramos con un decimal (la norma escribe «25 µg»; media ración de muchos
    # alimentos no llega al microgramo).
    "sodium-intake-daily": 0,
    "calcium-intake-daily": 0,
    "protein-intake-daily": 0,
    "vitamin-d-intake-daily": 1,
    # El ciclo menstrual y la anticoncepción (descriptivos, 2026-11-14): las cinco categorías son
    # números enteros de EMMA; la temperatura basal, con dos decimales, para no redondear al
    # enseñarla lo que llega del termómetro (la temperatura corporal evaluada sigue con uno).
    "menstrual-flow": 0,
    "menstruation-start": 0,
    "intermenstrual-bleeding": 0,
    "ovulation-test": 0,
    "contraceptive-in-use": 0,
    "basal-body-temperature": 2,
    # El estado reproductivo, la terapia hormonal y los síntomas vasomotores (descriptivos,
    # 2026-11-15): categorías con número entero de EMMA.
    "reproductive-status": 0,
    "menopausal-hormone-therapy": 0,
    "hot-flashes": 0,
    "night-sweats": 0,
}

# Una pendiente semanal es mas fina que la lectura: una deriva de 0,4 lpm/semana
# con los decimales del pulso se leeria "0 /min/semana", y pareceria que no hay
# deriva. Un decimal mas que el valor.
SLOPE_EXTRA_DECIMALS = 1

# Como se lee cada unidad UCUM. Solo cambia la escritura, nunca la magnitud: la
# unidad sigue a la propiedad LOINC (invariante 2). Misma tabla que la interfaz.
UNITS: dict[str, str] = {
    "/min": "/min",
    "Cel": "°C",
    "%": "%",
    "mm[Hg]": "mmHg",
    "kPa": "kPa",
    "dB(A)": "dBA",
    "[ppm]": "ppm",
    "mL/(24.h)": "mL/día",
    "mL": "mL",
    "1": "",
    "kcal/d": "kcal/día",
    "kg": "kg",
    "ms": "ms",
    "h": "h",
    "min": "min",
    "mSv": "mSv",
    "uGy/h": "µGy/h",
    "ug/dL": "µg/dL",
    "nmol/L": "nmol/L",
    "{count}": "recuento",
    "{score}": "puntos",
    "mm": "mm",
    "mm2": "mm²",
    "cm3": "cm³",
    "10*3/uL": "×10³/µL",
    "10*6/uL": "×10⁶/µL",
    "g/dL": "g/dL",
    "pg": "pg",
    "fL": "fL",
    "mg/dL": "mg/dL",
    "U/L": "U/L",
    "mmol/L": "mmol/L",
    "[arb'U]/mL": "U/mL",
    "ng/mL": "ng/mL",
    "mg/L": "mg/L",
    "ug/L": "µg/L",
    "u[IU]/mL": "µUI/mL",
    "ng/dL": "ng/dL",
    "pg/mL": "pg/mL",
    "m[IU]/mL": "mUI/mL",
    "[hnsf'U]": "HU",
    "lx": "lx",
    # Recuentos microbianos del habitat (`environment/habitat.py`), en unidades formadoras de
    # colonias: se muestran y no se evaluan.
    "{CFU}/mL": "UFC/mL",
    "{CFU}/m3": "UFC/m³",
    "{CFU}/(100.cm2)": "UFC/100 cm²",
    "mL/min/kg{body_wt}": "mL/(kg·min)",
    "kgf": "kgf",
    # La química de la orina de 24 horas: masa y sustancia por día, pH y osmolalidad.
    "mg/(24.h)": "mg/día",
    "mmol/(24.h)": "mmol/día",
    "[pH]": "pH",
    "mosm/kg": "mOsm/kg",
    "g/cm2": "g/cm²",
    # Sensoriomotor y músculo (descriptivos): segundos hasta la postura estable y newtons de la
    # tracción isométrica.
    "s": "s",
    "N": "N",
    # Nutrientes ingeridos al día: los de LOINC con la unidad de su ficha (24 h), los propios con
    # la forma de la energía (`kcal/d`). Se leen igual: por día.
    "g/(24.h)": "g/día",
    "mg/d": "mg/día",
    "ug/d": "µg/día",
}


# Lo que cambia en ingles (decision del usuario, 2026-11-15; `core/i18n.py`): el punto decimal,
# que es el de F.5.6, y las pocas unidades que llevan una palabra castellana. El espacio fino de
# los millares se queda en los dos idiomas. Las tablas de arriba no se tocan: son las castellanas.
DECIMAL_EN = "."
UNITS_EN: dict[str, str] = {
    "mL/(24.h)": "mL/day",
    "kcal/d": "kcal/day",
    "{count}": "count",
    "{score}": "points",
    "u[IU]/mL": "µIU/mL",
    "m[IU]/mL": "mIU/mL",
    "{CFU}/mL": "CFU/mL",
    "{CFU}/m3": "CFU/m³",
    "{CFU}/(100.cm2)": "CFU/100 cm²",
    "mg/(24.h)": "mg/day",
    "mmol/(24.h)": "mmol/day",
    "g/(24.h)": "g/day",
    "mg/d": "mg/day",
    "ug/d": "µg/day",
}


def decimal_mark() -> str:
    """El separador decimal del idioma de la peticion: coma en castellano, punto en ingles."""
    return DECIMAL_EN if i18n.current() == "en" else DECIMAL


def number(value: float, decimals: int) -> str:
    """Una cifra en el idioma de la peticion, segun F.5.6.

    Cero inicial si |x| < 1, sin ceros a la izquierda, sin "+", el menos siempre, y
    un valor que redondea a cero no lleva signo: "-0" no es un dato.
    """
    if not math.isfinite(value):
        raise ValueError(f"no es una cifra representable: {value}")
    fixed = f"{abs(value):.{decimals}f}"
    whole, _, fraction = fixed.partition(".")
    if len(whole) >= GROUP_FROM_DIGITS:
        head = len(whole) % 3 or 3
        groups = [whole[:head]] + [whole[i : i + 3] for i in range(head, len(whole), 3)]
        whole = GROUP.join(groups)
    sign = "-" if value < 0 and float(fixed) != 0 else ""
    return sign + whole + (decimal_mark() + fraction if fraction else "")


def unit(ucum: str) -> str:
    """La unidad como se lee. Una que no este en la tabla falla: no se improvisa."""
    try:
        written = UNITS[ucum]
    except KeyError:
        raise ValueError(f"unidad sin forma de lectura declarada: {ucum}") from None
    return UNITS_EN.get(ucum, written) if i18n.current() == "en" else written


def decimals_for(key: str) -> int:
    try:
        return DECIMALS[key]
    except KeyError:
        raise ValueError(f"indicador sin decimales declarados: {key}") from None


def quantity(key: str, value: float, ucum: str) -> str:
    """Un valor de un indicador con su unidad: "35 /min", "36,6 °C".

    Una magnitud adimensional (UCUM «1»: una proporción, una densidad relativa) se lee sin
    unidad, y entonces sin el espacio que la separaría: "0,85", no "0,85 ". Se vio en el panel
    de descriptivos con la precisión de la batería Cognition (2026-11-01).
    """
    text = number(value, decimals_for(key))
    written = unit(ucum)
    return f"{text} {written}" if written else text


def rate_per_week(key: str, slope: float, ucum: str) -> str:
    """Una pendiente semanal: "0,4 /min/semana", "1,5 recuento/semana"."""
    week = i18n.tr("semana", "week")
    return f"{number(slope, decimals_for(key) + SLOPE_EXTRA_DECIMALS)} {unit(ucum)}/{week}"


def percent(fraction: float, decimals: int = 1) -> str:
    """Una fraccion como porcentaje, con espacio antes del signo: "12,5 %"."""
    return f"{number(fraction * 100, decimals)} %"
