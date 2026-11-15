"""Catalogo de codigos de los indicadores de salud.

Regla del proyecto: **no se inventan codigos LOINC**. Cada codigo marcado como
`CodeSystem.LOINC` esta verificado en su fuente:

  - Signos vitales clasicos: perfil oficial FHIR R4 Vital Signs
    (https://hl7.org/fhir/R4/observation-vitalsigns.html)
  - 80404-7  R-R interval.standard deviation (Heart rate variability)
  - 2142-8   Cortisol [Mass/volume] in Saliva (oral fluid)

Las medidas especificas de mision (HRV, PVT, dosimetria, carga osea, marcadores
inmunes) usan el sistema propio `CodeSystem.EMMA`. FHIR permite sistemas de
codigos propios; lo que no permite la honestidad tecnica es disfrazarlos de LOINC.
Para cada indicador con codigo propio hay que declarar **por que** no usa uno
estandar: o esta en `NO_LOINC_AVAILABLE` (se busco y no existe) o en
`MISSION_SPECIFIC` (mide algo que la practica clinica terrestre no mide).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core import i18n

# Indicadores para los que se busco codigo LOINC y **no existe** uno adecuado.
# No es una tarea pendiente: es un resultado de busqueda. Revisar si LOINC
# publica uno en el futuro.
#
#   hrv-rmssd   LOINC codifica la desviacion tipica del intervalo R-R (80404-7,
#               76643-6 por EKG) y su coeficiente de variacion (76644-4), pero
#               no la raiz cuadratica media de diferencias sucesivas.
#   onsd-*      Buscado el 2026-09-24 ("optic nerve sheath", "ONSD", "optic nerve"):
#               LOINC tiene funcion (VEP, ERG) y cociente copa-disco del nervio
#               optico, pero ningun diametro de su vaina.
#   ijv-csa-*   Buscado el 2026-09-24 ("jugular vein", "cross-sectional area", "vein
#               area"): solo distension yugular, onda V y procedimientos; ningun area
#               de seccion de la yugular interna.
#   energy-intake-daily  Revisado el 2026-09-26 en loinc.org: 9052-2 "Calorie intake total"
#               es `EngRat:Pt` (tasa puntual, unidad de ejemplo kcal), no un total diario.
#               Adoptarlo para una suma de 24 h seria el error de la invariante 2.
#   neutrophil-lymphocyte-ratio  Buscado el 2026-10-01 en tx.fhir.org (LOINC 2.82: "Neutrophils",
#               251 códigos, ninguno con linfocitos; "Neutrophils/Lymphocytes"; "neutrophil
#               lymphocyte ratio"): no hay código para el cociente.
#   nasa-tlx-workload  Buscado el 2026-10-16 en tx.fhir.org (LOINC 2.82: "NASA task load",
#               "TLX", "task load": nada; "workload", "mental workload": solo los paneles de
#               carga de trabajo de enfermería del NMMDS, 77221-0 y 77226-9, que describen una
#               unidad de hospital, no la carga que una persona percibe en una tarea).
#   urine-caox-supersaturation-24h  Buscado el 2026-10-26 en tx.fhir.org (LOINC 2.83):
#               «supersaturation» solo da dos paneles sin valor (81232-1 de 24 h, 101929-8);
#               «saturation» en orina da la fracción de saturación (SatFr) de la brushita
#               (42673-4), el urato (42678-3), el urato sódico (43423-3) y el fosfato triple
#               (53811-6), ninguna del oxalato cálcico; del oxalato cálcico en orina de 24 h solo
#               hay una diferencia de energía (81623-1, EngDiff, kJ/mol) y un «Calcium oxalate
#               index» (34736-9, Ratio), otras propiedades: adoptarlas para el cociente sería el
#               error de la invariante 2.
#   tandem-walk-correct-steps  Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «tandem» da
#               «Tandem gait for 10 steps [PhenX]» (66045-6: propiedad Find, escala Nom, estado
#               TRIAL, con su lista de respuestas «Normal…», «Slight difficulties…», «Clearly
#               abnormal…»), «Gait and turn and tandem gait assessment» (93015-6) y el balanceo en
#               postura tándem del NIH Toolbox (83179-2): ninguno es el porcentaje de pasos
#               correctos que puntúa NASA. «posturography», «sensory organization» y «stand test»:
#               nada;
#               «balance»: la duración en una postura del NIH Toolbox (91553-8) y la prueba de
#               equilibrio de PhenX (66248-6, 66249-4), otros protocolos.
#   recovery-from-fall-time  Buscado el mismo día: «stand test», «sensory organization»,
#               «posturography»: nada; «fall» y «balance» solo dan ítems de cuestionario sobre
#               caídas y mareo (PhenX, FACIT, PROMIS) y el conjunto mínimo de datos, ninguno el
#               tiempo hasta la postura estable tras levantarse.
#   dxa-lean-mass  Buscado el mismo día: «lean» da «Lean body weight» (91557-9: Mass, ^Patient, Qn,
#               sin método, kg), «Lean body weight Calculated» (88334-8), por inmersión (8342-8) y
#               por pliegues (8343-6). Ninguno es de DXA, y «lean body weight» no dice si incluye el
#               mineral óseo, que la DXA separa («bone, fat, lean» en la tabla leída): codificar el
#               tejido magro de la DXA como peso magro cambiaría lo que dice la cifra en unos kilos.
#               «fat free» y «soft tissue mass»: nada; «body composition»: solo el protocolo de
#               PhenX por DXA (63520-1, DISCOURAGED); «DXA»: 67 códigos, todos de densidad ósea;
#               «body fat»: la masa grasa calculada (73708-0) y porcentajes, sin DXA.
#   imtp-peak-force  Buscado el mismo día: «thigh pull», «peak force» y «force plate»: nada;
#               «isometric»: una respuesta de ejercicio terapéutico (LA29117-1); «muscle strength»:
#               el protocolo de PhenX (62821-4, inactivo) e ítems de debilidad muscular, ninguno la
#               fuerza máxima de una tracción isométrica medida en una plataforma de fuerza.
#   cognition-*  Las nueve pruebas de la batería Cognition con código propio (la décima, la PVT,
#               ya tiene los suyos). Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83) por el
#               nombre de cada prueba: «digit symbol», «emotion recognition», «matrix reasoning»,
#               «line orientation», «object learning», «risk taking» y «reaction time» no dan
#               ningún código; «working memory» da el List Sorting del NIH Toolbox (84434-0 y sus
#               puntuaciones) y un protocolo de PhenX (62776-0), otras pruebas, no el 2-Back de
#               fractales. Ninguna prueba de la batería tiene código.
#   stress-rating-vas  Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83: «perceived stress»): hay
#               códigos para la Perceived Stress Scale de Cohen (PSS-10, 106875-8 y su total
#               106860-0; PSS-14, 106904-6 y 106903-8) y para la encuesta del NIH Toolbox
#               (91528-0, 91527-2); ninguno para la escala visual analógica de estrés del Reaction
#               Self Test, que es otro instrumento. Adoptar el de la PSS para una EVA de 0 a 100
#               sería el error de la invariante 1.
#   team-cohesion-*  Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «cohesion» solo da la
#               eficacia colectiva de un vecindario de PhenX (63026-9); «team», equipos
#               asistenciales y notas de equipo clínico. Ningún código para las afirmaciones de
#               cohesión del cuestionario de fin de día de Standard Measures.
#   sodium-intake-daily  Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83, «sodium intake»): el
#               único código de 24 horas sin método, 9092-8 «Sodium intake 24 hour», es sustancia
#               por tiempo (SRat, mol/(24.h)); los dos de masa por tiempo (81011-9 «Estimated» y
#               81012-7 «Measured», g/(24.h)) declaran un método que lo leído no fija. EMMA registra
#               el sodio ingerido en masa por día y no sabe si se pesó o se estimó: adoptar 9092-8
#               cambiaría la unidad a moles; adoptar uno con método sería inventarlo.
#   vitamin-d-intake-daily  Buscado el mismo día («vitamin D intake»): solo existen con método,
#               81929-2 «Estimated» y 81930-0 «Measured» (MRat, ug/(24.h)); no hay uno sin método
#               que adoptar sin inventar cómo se obtuvo la cifra.
#   menstrual-flow, menstruation-start, intermenstrual-bleeding, ovulation-test,
#   contraceptive-in-use, basal-body-temperature  Buscado el 2026-11-14 en tx.fhir.org (LOINC
#               2.83): «menstrual», «menses», «menstruation», «menstrual flow», «vaginal
#               bleeding», «spotting», «intermenstrual», «ovulation», «lutropin», «luteinizing»,
#               «birth control», «contracept», «basal» y «body temperature». Lo encontrado son
#               hallazgos nominales (32400-4, 3146-8, 8678-5), una fecha (8665-2), una pregunta de
#               siete días del FACIT (70381-9), cantidades de lutropina en orina, el método
#               anticonceptivo nominal con su propia lista (8659-5) y la temperatura corporal sin
#               condición basal (8310-5, ya de `body-temperature`). El detalle, junto a los
#               indicadores (bloque del ciclo menstrual).
#   reproductive-status, menopausal-hormone-therapy, hot-flashes, night-sweats  Buscado el
#               2026-11-15 en tx.fhir.org (LOINC 2.83): «menopaus», «perimenopaus»,
#               «postmenopaus», «menstrual status», «hormone therapy», «hormone replacement»,
#               «estrogen use», «female hormone», «hot flash», «hot flush», «night sweat» y
#               «vasomotor». Lo encontrado: el estado menstrual nominal sin lista (3146-8, 8678-5),
#               el uso de estrógeno con su lista sí/no (98134-0), preguntas de PhenX y de
#               cuestionarios (FACIT 70376-9 y 70379-3, de siete días; PHQ 69710-2). El detalle,
#               en el bloque de esos indicadores.
NO_LOINC_AVAILABLE = (
    "hrv-rmssd", "onsd-right", "onsd-left", "ijv-csa-right", "ijv-csa-left",
    "energy-intake-daily", "neutrophil-lymphocyte-ratio", "nasa-tlx-workload",
    "urine-caox-supersaturation-24h",
    "tandem-walk-correct-steps", "recovery-from-fall-time", "dxa-lean-mass", "imtp-peak-force",
    # Equipo, estrés y cognición, descriptivos (2026-10-31): ver el bloque de la batería Cognition.
    "cognition-mpt-speed",
    "cognition-volt-speed", "cognition-volt-accuracy",
    "cognition-f2b-speed", "cognition-f2b-accuracy",
    "cognition-am-speed", "cognition-am-accuracy",
    "cognition-lot-speed", "cognition-lot-accuracy",
    "cognition-ert-speed", "cognition-ert-accuracy",
    "cognition-mrt-speed", "cognition-mrt-accuracy",
    "cognition-dsst-speed", "cognition-dsst-accuracy",
    "cognition-bart-speed", "cognition-bart-risk",
    "stress-rating-vas",
    "team-cohesion-cared", "team-cohesion-task-focus", "team-cohesion-shared-purpose",
    "sodium-intake-daily", "vitamin-d-intake-daily",
    # El ciclo menstrual y la anticoncepción, descriptivos (2026-11-14).
    "menstrual-flow", "menstruation-start", "intermenstrual-bleeding", "ovulation-test",
    "contraceptive-in-use", "basal-body-temperature",
    # El estado reproductivo, la terapia hormonal de la menopausia y los síntomas vasomotores,
    # descriptivos (2026-11-15); lo buscado, en el bloque de esos indicadores.
    "reproductive-status", "menopausal-hormone-therapy", "hot-flashes", "night-sweats",
)

# Indicadores propios de la mision, para los que no procede un codigo clinico
# estandar: miden cosas que la practica clinica terrestre no mide. Cada uno debe
# figurar aqui con su razon, y la prueba
# `test_every_custom_code_declares_why_it_is_not_loinc` impide anadir un
# indicador con codigo propio sin justificarlo.
MISSION_SPECIFIC: dict[str, str] = {
    "orthostatic-drop": "protocolo de tolerancia ortostática propio de vuelo",
    "pvt-mean-rt": "tarea de vigilancia psicomotora, no es una prueba clínica de rutina",
    "pvt-lapses": "ídem: lapsos de la misma tarea",
    "sleep-efficiency": "derivada de actigrafía de a bordo, no de polisomnografía",
    "circadian-shift": "desfase respecto al horario de misión, no a un ciclo terrestre",
    "mood-valence": "escala breve de autoinforme propia de la misión",
    "absorbed-dose-rate": "dosimetría de nave, no una medida de laboratorio clínico",
    "cumulative-dose": "dosis de carrera acumulada frente al límite de NASA-STD-3001",
    "exercise-minutes": "adherencia al protocolo de ejercicio resistivo de a bordo",
    "loading-impacts": "carga mecánica por acelerometría, proxy óseo específico de vuelo",
    "symptom-burden": "diario de síntomas de a bordo",
    "latent-virus-shedding": "vigilancia de reactivación de herpesvirus en vuelo",
    "food-acceptability": (
        "escala hedónica de 9 puntos del laboratorio de alimentos de la NASA sobre la comida "
        "de a bordo; no es una observación clínica"
    ),
    # Buscado en tx.fhir.org el 2026-09-28: LOINC tiene el apetito solo como item de
    # cuestionarios concretos (DI-PAD 65961-5, QIDS 65507-6, M3 71571-4, ESAS), cada uno con
    # su lista de respuestas; usarlos para otra escala seria el error de la invariante 1.
    "appetite-rating": "escala 0-10 de apetito propia de la misión, no la de ningún cuestionario",
    # Buscado el mismo dia: "Food intake panel" (80453-4) y los items del MNA no miden la
    # fraccion de la racion que se deja.
    "food-rejected-fraction": "fracción de la ración servida que se deja, registro de a bordo",
    # Buscado en tx.fhir.org el 2026-10-16 (LOINC 2.82: "vision change", "change in vision",
    # "blurred vision", "vision questionnaire": nada salvo una lista de respuestas, LL5656-5;
    # "visual disturbance": la descripción libre de un protocolo de PhenX, 65727-0).
    "vision-change": (
        "cuestionario de visión en vuelo de las operaciones médicas de NASA sobre el SANS: si se "
        "notó un cambio de visión desde el lanzamiento o el último examen en vuelo, y cuánto "
        "afecta; no es una prueba clínica terrestre"
    ),
}
# El inglés de cada razón, por la clave del indicador (2026-11-15, `core/i18n.py`). La razón
# castellana de arriba no se toca; quien la enseña la resuelve con `i18n.loc`. Una razón sin
# inglés hace fallar `tests/test_codes_en.py`.
MISSION_SPECIFIC_EN: dict[str, str] = {
    "orthostatic-drop": "orthostatic tolerance protocol specific to flight",
    "pvt-mean-rt": "psychomotor vigilance task, not a routine clinical test",
    "pvt-lapses": "likewise: lapses of the same task",
    "sleep-efficiency": "derived from on-board actigraphy, not from polysomnography",
    "circadian-shift": "shift relative to the mission schedule, not to an Earth cycle",
    "mood-valence": "brief self-report scale specific to the mission",
    "absorbed-dose-rate": "ship dosimetry, not a clinical laboratory measurement",
    "cumulative-dose": "accumulated career dose against the NASA-STD-3001 limit",
    "exercise-minutes": "adherence to the on-board resistive exercise protocol",
    "loading-impacts": "mechanical loading by accelerometry, a flight-specific bone proxy",
    "symptom-burden": "on-board symptom diary",
    "latent-virus-shedding": "surveillance of herpesvirus reactivation in flight",
    "food-acceptability": (
        "9-point hedonic scale of NASA's food laboratory about the on-board food; it is not a "
        "clinical observation"
    ),
    "appetite-rating": "0-10 appetite scale specific to the mission, not that of any questionnaire",
    "food-rejected-fraction": (
        "fraction of the served ration that is left uneaten, on-board record"
    ),
    "vision-change": (
        "in-flight vision questionnaire of NASA medical operations about SANS: whether a change "
        "in vision was noticed since launch or the last in-flight exam, and how much it affects; "
        "it is not a terrestrial clinical test"
    ),
}
i18n.en_many({
    MISSION_SPECIFIC[key]: english
    for key, english in MISSION_SPECIFIC_EN.items()
    if key in MISSION_SPECIFIC
})

# Las anclas de las tres escalas de autoinforme propias de la misión (decisión del usuario,
# 2026-10-15).
#
# Ninguna de las tres es la versión de un instrumento publicado: no hay fuente que leer sobre
# sus puntos. La escala hedónica sí la tiene, y por eso sus rótulos viven en otro sitio
# (`data/instruments_read.json`), cada uno con la frase de su fuente. Aquí no se leyó nada: lo que
# significa cada extremo lo decide EMMA, y se publica como lo que es, una decisión de diseño
# sin validar. Las anclas ponen por escrito lo que el catálogo ya suponía al vigilar un
# extremo (`concerning`); no cambian el rango, la unidad ni nada que puntúe.
#
# Tampoco se les cita una ficha de evidencia: la que respalda la deriva de un indicador en el
# simulador no es el instrumento que define su escala, y presentarla así le atribuiría una
# fuente que no tiene.
OWN_SCALES_DECIDED_ON = "2026-10-15"


@dataclass(frozen=True)
class OwnScaleAnchors:
    """Lo que EMMA decidió que significa cada extremo de una escala propia, y por qué decide él."""

    low: str  # el extremo bajo del rango físico del catálogo
    high: str  # el extremo alto
    why: str  # por qué no hay instrumento publicado que leer


OWN_SCALE_ANCHORS: dict[str, OwnScaleAnchors] = {
    "mood-valence": OwnScaleAnchors(
        low="el ánimo más negativo",
        high="el ánimo más positivo",
        why=(
            "No hay instrumento publicado detrás: EMMA definió esta escala para la misión y no "
            "es la versión de ningún cuestionario de ánimo, así que ninguna fuente dice qué "
            "significa cada punto."
        ),
    ),
    "symptom-burden": OwnScaleAnchors(
        low="ningún síntoma",
        high="la mayor carga de síntomas",
        why=(
            "No hay instrumento publicado detrás: EMMA definió esta escala para el diario de "
            "síntomas de a bordo y no es la versión de ningún cuestionario de síntomas, así que "
            "ninguna fuente dice qué significa cada punto."
        ),
    ),
    "appetite-rating": OwnScaleAnchors(
        low="ningún apetito",
        high="el mayor apetito",
        why=(
            "No hay instrumento publicado detrás: los cuestionarios con pregunta de apetito que "
            "codifica LOINC traen cada uno su propia lista de respuestas, y esta escala de 0 a 10 "
            "no es la de ninguno, así que ninguna fuente dice qué significa cada punto."
        ),
    ),
}
# El inglés de las anclas: decididas por EMMA y sin validar, también en inglés. Por clave del
# indicador, en el orden (bajo, alto, por qué) de `OwnScaleAnchors`.
OWN_SCALE_ANCHORS_EN: dict[str, OwnScaleAnchors] = {
    key: OwnScaleAnchors(low=low, high=high, why=why)
    for key, (low, high, why) in {
        "mood-valence": (
            "the most negative mood",
            "the most positive mood",
            "There is no published instrument behind it: EMMA defined this scale for the mission "
            "and it is not the version of any mood questionnaire, so no source says what each "
            "point means.",
        ),
        "symptom-burden": (
            "no symptoms",
            "the greatest symptom burden",
            "There is no published instrument behind it: EMMA defined this scale for the on-board "
            "symptom diary and it is not the version of any symptom questionnaire, so no source "
            "says what each point means.",
        ),
        "appetite-rating": (
            "no appetite",
            "the greatest appetite",
            "There is no published instrument behind it: the questionnaires with an appetite "
            "question that LOINC codes each bring their own list of answers, and this 0 to 10 "
            "scale is not that of any of them, so no source says what each point means.",
        ),
    }.items()
}
for _key, _english in OWN_SCALE_ANCHORS_EN.items():
    if _key in OWN_SCALE_ANCHORS:
        i18n.en_many({
            OWN_SCALE_ANCHORS[_key].low: _english.low,
            OWN_SCALE_ANCHORS[_key].high: _english.high,
            OWN_SCALE_ANCHORS[_key].why: _english.why,
        })

# Migrados tras verificar cada uno en su ficha oficial de LOINC:
#   hrv-sdnn         -> 80404-7  R-R interval.standard deviation (HRV)
#   cortisol-salivary-> 2142-8   Cortisol [Mass/volume] in Saliva (oral fluid)
#   sleep-duration   -> 93832-4  Sleep duration
#   ntx-telopeptide  -> 27939-8  Collagen crosslinked N-telopeptide [Moles/volume] in Urine
#   leukocytes       -> 6690-2   Leukocytes [#/volume] in Blood by Automated count
#   lymphocytes      -> 731-0    Lymphocytes [#/volume] in Blood by Automated count
#   neutrophils      -> 751-8    Neutrophils [#/volume] in Blood by Automated count
#                                Las tres, fichas oficiales leidas el 2026-09-24: NCnc, sangre,
#                                recuento automatico; unidad de ejemplo 10*3/uL. Llegan de las
#                                analiticas reales de Inspiration4 (app/ingest/inspiration4.py).
#   bladder-volume   -> 15309-8  Urinary bladder Volume by derived from height, width and
#                                length (US). Ficha oficial leida el 2026-09-24.
#   pain-intensity   -> 72514-3  Pain severity - 0-10 verbal numeric rating [Score] - Reported.
#                                Consultado el 2026-09-25 en tx.fhir.org (LOINC 2.82): ACTIVE,
#                                escala de puntuacion, unidad UCUM de ejemplo {score}.
#
# CUIDADO CON EL METODO, NO SOLO CON LA PROPIEDAD. 15309-8 es Vol (cm3) y su metodo
# `US.derived.HWL` define la formula: alto x ancho x largo x **0,57**. Calcular con el
# 0,52 del elipsoide y etiquetarlo con este codigo daria un volumen un 9 % menor del
# que el codigo declara: el mismo error silencioso que la unidad equivocada.
#
# CUIDADO CON LA PROPIEDAD DE LA MEDIDA. LOINC distingue deliberadamente
# Mass/volume de Moles/volume con codigos distintos, y la unidad tiene que
# seguir a la propiedad:
#   2142-8  es Mass/volume  -> ug/dL   (no nmol/L)
#   27939-8 es Moles/volume -> nmol/L  (no ug/L)
# Adoptar un codigo con la unidad de la otra propiedad seria un error semantico
# silencioso, del tipo exacto que la regla de no inventar codigos existe para
# evitar.


class ReferenceBasis(StrEnum):
    """De donde sale un rango de referencia. Hay que declararlo.

    La validacion externa destapo que bajo un mismo campo convivian cosas
    incompatibles: rangos observados en poblacion sana, **recomendaciones
    clinicas**, escalas inventadas por el proyecto y limites normativos. Tratar
    una recomendacion como umbral de alerta marcaba al 95 % de los sujetos sanos
    en `sleep-duration` y al 52 % en `sleep-efficiency`.

    Una guia dice "convendria estar aqui". Un rango observado dice "aqui esta la
    gente sana". Solo el segundo sirve para decidir si alguien se sale de lo
    normal.

    Un indicador sin rango no tiene base: `VitalCode.reference_basis` es `None`.
    """

    OBSERVED = "observed"    # medido en poblacion sana
    GUIDELINE = "guideline"  # recomendacion; NO es un umbral de alerta
    DESIGN = "design"        # escala definida por el proyecto
    LIMIT = "limit"          # limite normativo o de exposicion


class CodeSystem(StrEnum):
    LOINC = "http://loinc.org"
    EMMA = "https://emma.mission/codes"


# EL SISTEMA DE ANTES (2026-11-02). Hasta que HALO paso a llamarse EMMA, el sistema propio era
# `https://halo.mission/codes`, y asi va en cada observacion firmada antes: el recurso FHIR esta
# dentro de lo firmado y no se reescribe. Se lee como el sistema de hoy; se escribe siempre el
# de hoy. Es el mismo catalogo con otro nombre, no un sistema distinto.
FORMER_CODE_SYSTEMS: dict[str, CodeSystem] = {"https://halo.mission/codes": CodeSystem.EMMA}


def current_system(system: str) -> str:
    """El sistema de hoy para uno leido de un registro, que puede llevar el nombre de antes."""
    return str(FORMER_CODE_SYSTEMS.get(system, system))


# El sistema de un código como se lee, en un solo sitio: lo usan el panel de descriptivos
# (`api/descriptive.py`) y la cobertura de los riesgos del HRP (`evidence/hrp_coverage.py`).
CODE_SYSTEM_DISPLAY: dict[CodeSystem, str] = {
    CodeSystem.LOINC: "LOINC",
    CodeSystem.EMMA: "código propio de EMMA",
}
i18n.en(CODE_SYSTEM_DISPLAY[CodeSystem.EMMA], "EMMA's own code")


class Domain(StrEnum):
    """Dominios clinicos, alineados con los riesgos del NASA Human Research Program."""

    CARDIOVASCULAR = "cardiovascular"
    BEHAVIORAL = "behavioral"
    RADIATION = "radiation"
    BONE = "bone"
    IMMUNE = "immune"
    # Sindrome neuro-ocular asociado al vuelo (SANS): riesgo propio del HRP.
    NEURO_OCULAR = "neuro-ocular"
    # Retencion urinaria: condicion medica de adaptacion al vuelo (OCHMO-MTB-003).
    GENITOURINARY = "genitourinary"
    # Dolor musculoesqueletico autoinformado: el dolor de espalda de adaptacion al vuelo
    # es frecuente, y el riesgo de lesion discal al volver a la gravedad es del HRP. Aqui se
    # agrupa tambien la fuerza de prension, que es descriptiva (DESCRIPTIVE_ONLY), y desde la
    # decimonovena ronda las medidas descriptivas de músculo (masa magra por DXA, tracción
    # isométrica) y las dos pruebas funcionales sensoriomotoras de Standard Measures (marcha en
    # tándem, levantarse tras estar tumbado): EMMA no tiene dominio sensoriomotor, y agruparlas
    # aquí dice dónde se enseñan, no que el dominio las evalúe (`evaluated_by_domain`).
    MUSCULOSKELETAL = "musculoskeletal"
    # Ingesta real y aceptabilidad de la comida (base de conocimiento §5; riesgo del HRP por
    # sistema alimentario inadecuado).
    NUTRITION = "nutrition"

    @property
    def display(self) -> str:
        """Como se nombra ante la tripulacion.

        El valor del enum es la clave de la API y se queda en ingles; lo que se
        lee en pantalla, no. El panel decia "Atencion en behavioral (watch)":
        media frase en castellano y los nombres internos del codigo en la otra
        media.

        Sale en el idioma de la peticion (`core/i18n.py`); dentro de
        `i18n.record_language()`, en castellano, como todo lo que se firma.
        """
        return i18n.loc(_DOMAIN_DISPLAY[self])

    @property
    def ridge(self) -> Ridge:
        """Peligro RIDGE de NASA del que procede el riesgo del dominio."""
        return _DOMAIN_RIDGE[self]


class Ridge(StrEnum):
    """Los cinco peligros del vuelo humano con que NASA ordena sus riesgos (RIDGE).

    Fuente: NASA, "The Human Body in Space" (humans-in-space/the-human-body-in-space).
    La especificacion del equipo (§3) pide que cada riesgo lleve su categoria RIDGE.
    """

    RADIATION = "radiation"
    ISOLATION = "isolation"
    DISTANCE = "distance"
    GRAVITY = "gravity"
    ENVIRONMENT = "environment"

    @property
    def display(self) -> str:
        return i18n.loc(_RIDGE_DISPLAY[self])


_RIDGE_DISPLAY: dict[Ridge, str] = {
    Ridge.RADIATION: "radiación",
    Ridge.ISOLATION: "aislamiento y confinamiento",
    Ridge.DISTANCE: "distancia de la Tierra",
    Ridge.GRAVITY: "campos gravitatorios",
    Ridge.ENVIRONMENT: "entorno hostil y cerrado",
}
i18n.en_many({
    _RIDGE_DISPLAY[Ridge.RADIATION]: "radiation",
    _RIDGE_DISPLAY[Ridge.ISOLATION]: "isolation and confinement",
    _RIDGE_DISPLAY[Ridge.DISTANCE]: "distance from Earth",
    _RIDGE_DISPLAY[Ridge.GRAVITY]: "gravity fields",
    _RIDGE_DISPLAY[Ridge.ENVIRONMENT]: "hostile and closed environment",
})

# Segun la misma pagina de NASA: la gravedad alterada afecta a hueso, musculo, sistema
# cardiovascular, desplazamiento de fluidos y vision (SANS), y la adaptacion urinaria; el
# aislamiento, al sueno, la cognicion y el comportamiento; el entorno cerrado se asocia a
# alteraciones inmunitarias. "Distancia" no tiene dominio clinico propio en EMMA: es la
# autonomia que el sistema entero suple (factor de aislamiento por retardo).
_DOMAIN_RIDGE: dict[Domain, Ridge] = {
    Domain.CARDIOVASCULAR: Ridge.GRAVITY,
    Domain.BEHAVIORAL: Ridge.ISOLATION,
    Domain.RADIATION: Ridge.RADIATION,
    Domain.BONE: Ridge.GRAVITY,
    Domain.IMMUNE: Ridge.ENVIRONMENT,
    Domain.NEURO_OCULAR: Ridge.GRAVITY,
    Domain.GENITOURINARY: Ridge.GRAVITY,
    Domain.MUSCULOSKELETAL: Ridge.GRAVITY,
    # La distancia obliga a llevar la comida para toda la mision, sin reabastecimiento
    # (NASA, "The Human Body in Space"): el riesgo alimentario es de la D de RIDGE.
    Domain.NUTRITION: Ridge.DISTANCE,
}


_DOMAIN_DISPLAY: dict[Domain, str] = {
    Domain.CARDIOVASCULAR: "cardiovascular",
    Domain.BEHAVIORAL: "conductual",
    Domain.RADIATION: "radiación",
    Domain.BONE: "óseo",
    Domain.IMMUNE: "inmune",
    Domain.NEURO_OCULAR: "neuro-ocular",
    Domain.GENITOURINARY: "genitourinario",
    Domain.MUSCULOSKELETAL: "musculoesquelético",
    Domain.NUTRITION: "nutrición",
}
# «cardiovascular» y «neuro-ocular» se escriben igual en los dos idiomas.
i18n.en_many({
    _DOMAIN_DISPLAY[Domain.BEHAVIORAL]: "behavioral",
    _DOMAIN_DISPLAY[Domain.RADIATION]: "radiation",
    _DOMAIN_DISPLAY[Domain.BONE]: "bone",
    _DOMAIN_DISPLAY[Domain.IMMUNE]: "immune",
    _DOMAIN_DISPLAY[Domain.GENITOURINARY]: "genitourinary",
    _DOMAIN_DISPLAY[Domain.MUSCULOSKELETAL]: "musculoskeletal",
    _DOMAIN_DISPLAY[Domain.NUTRITION]: "nutrition",
})


def domain_name(key: str) -> str:
    """El nombre de pantalla de un dominio dado por su clave, en el idioma de la petición; una
    clave que el catálogo no conoce va tal cual.

    Para quien tiene la clave como texto (un asiento del ledger, una alerta ya servida) y no el
    `Domain`: vivía en `app/waiting.py` y `app/twins.py` la importaba de allí (§5.37.13).
    """
    try:
        return Domain(key).display
    except ValueError:
        return key


class ObservationCategory(StrEnum):
    """Los nueve códigos de categoría de `Observation` en FHIR R4, y solo esos.

    Leídos el 2026-10-26 en el sistema de códigos oficial
    (http://terminology.hl7.org/CodeSystem/observation-category, versión 4.0.1, página
    hl7.org/fhir/R4/codesystem-observation-category.html). Lo que distingue a los que usa EMMA:
    «vital-signs» nombra «blood pressure, heart rate, respiratory rate, height, weight, body mass
    index»; «laboratory» es lo «based on analysis of specimens obtained from the patient and
    submitted to the laboratory»; «survey», «Assessment tool/survey instrument observations»;
    «exam», «Observations generated by physical exam findings»; y «activity» pone como ejemplo
    «(e.g., laps swum, steps, sleep data)».
    """

    SOCIAL_HISTORY = "social-history"
    VITAL_SIGNS = "vital-signs"
    IMAGING = "imaging"
    LABORATORY = "laboratory"
    PROCEDURE = "procedure"
    SURVEY = "survey"
    EXAM = "exam"
    THERAPY = "therapy"
    ACTIVITY = "activity"


class NoCategory(StrEnum):
    """Un indicador que ningún código de `ObservationCategory` describe: el recurso va sin ella.

    `Observation.category` es opcional en FHIR R4 (0..*). Ponerle una que no es la suya —el
    registro de lo que se bebe como «survey» o como «imaging»— es peor que no ponerla: quien
    filtra por categoría lo encontraría donde no está.
    """

    NONE_FITS = "none-fits"


# Los lados que puede declarar `VitalCode.concerning`; lo comprueba su `__post_init__`.
CONCERNING_SIDES = frozenset({"high", "low", "both"})


@dataclass(frozen=True)
class VitalCode:
    """Un indicador monitorizable, con su codificacion y rango de referencia."""

    key: str
    code: str
    display: str
    unit: str  # UCUM
    system: CodeSystem
    domain: Domain
    # Rango de referencia terrestre para un adulto sano. Sirve de arranque hasta
    # que exista linea base personal; NO es el umbral de alerta (ver analysis/).
    reference_low: float | None = None
    reference_high: float | None = None
    # Direccion en que un valor es preocupante: "high", "low" o "both".
    concerning: str = "both"
    # Procedencia del rango (ver ReferenceBasis): hay rango <=> hay base, y lo exige
    # `__post_init__` al cargar el catalogo.
    #
    # Antes valia `OBSERVED` por defecto, y los indicadores sin rango (las analiticas, la
    # ecografia, las escalas propias sin rango, los descriptivos) declaraban "medido en
    # poblacion sana" sobre un rango que no existe: `/api/indicators` decia `observed` de
    # `appetite-rating`, una escala decidida por EMMA. Sin rango no hay de donde salga: `None`
    # (decision del usuario, 2026-10-20). Y un indicador con rango tiene que nombrar su base
    # en vez de heredarla.
    reference_basis: ReferenceBasis | None = None
    # LIMITES DE PELIGRO ABSOLUTO, no de normalidad.
    #
    # Mientras no hay linea base personal, estos son los **unicos** valores que
    # generan alerta. Antes se marcaba a 2 sigmas del punto medio del rango de
    # referencia, y eso producia el 58 % de las falsas alarmas de la validacion
    # externa. Un rango de referencia dice "asi es la gente sana"; un limite
    # critico dice "esto es peligroso". Solo el segundo justifica despertar a
    # alguien que aun no tiene historial.
    #
    # `None` significa que el indicador no tiene un umbral de peligro absoluto
    # defendible, y entonces **no alerta sin base personal**. Es lo correcto:
    # inventar uno para rellenar seria volver al problema.
    critical_low: float | None = None
    critical_high: float | None = None
    # Limites mas estrictos que aplican **solo en reposo o sueno**.
    #
    # 145 lpm corriendo es fisiologia normal; 145 lpm en reposo es un hallazgo.
    # Sin esta distincion hay que elegir entre perder el evento agudo o alarmar
    # en cada sesion de ejercicio, y ninguna de las dos es aceptable.
    resting_critical_low: float | None = None
    resting_critical_high: float | None = None
    # Y mas laxos durante esfuerzo fisico.
    #
    # Faltaba este tramo y era un hueco real: tres sujetos **sanos** quedaban
    # marcados por pulsos de 128, 191 y 192 lpm. En un adulto de 29 anos la
    # frecuencia maxima teorica ronda los 190, asi que eso es esfuerzo maximo,
    # no una urgencia. Con un unico limite de 150 para todo lo que no sea reposo,
    # cualquier sesion de ejercicio dispara la alarma.
    exertion_critical_low: float | None = None
    exertion_critical_high: float | None = None
    # LIMITES DE POSIBILIDAD FISICA, no de peligro.
    #
    # Un pulso de -50 no es bradicardia: es un sensor roto. Antes, un valor asi
    # cruzaba el limite de peligro y se reportaba como **urgencia clinica**,
    # mandando a la tripulacion a investigar un problema fisiologico inexistente.
    #
    # Fuera de este rango el dato no es extremo: es invalido, y se rechaza en la
    # frontera en vez de convertirse en hallazgo.
    physical_min: float | None = None
    physical_max: float | None = None
    # LA CATEGORÍA FHIR DE LO QUE ES LA MEDIDA, si no es la de su regla.
    #
    # Sin declarar (`None`), la da `ingest.fhir.category_of`: imagen para una medida
    # ecográfica, laboratorio para un analito de analítica y, si no, la de su dominio. El
    # dominio agrupa por riesgo, no por cómo se mide, y la regla falla con lo que no es lo
    # típico del dominio: el peso salía «activity» (óseo), la orina de 24 h «imaging»
    # (genitourinario) y la carga de síntomas «laboratory» (inmune). Esos la declaran aquí, con
    # el motivo junto al indicador. No entra en el asiento ni en la huella de las reglas: solo
    # vive en el recurso que sirve `to_fhir()`.
    category: ObservationCategory | NoCategory | None = None

    def __post_init__(self) -> None:
        """Un rango sin procedencia, o una procedencia sin rango, no carga.

        Un indicador con medio rango (`fluid-intake-24h` solo tiene minimo) cuenta como con
        rango: ese extremo sale de algun sitio y hay que decir de cual.
        """
        has_range = self.reference_low is not None or self.reference_high is not None
        if has_range and self.reference_basis is None:
            raise ValueError(f"{self.key}: tiene rango de referencia y no declara su base")
        if not has_range and self.reference_basis is not None:
            raise ValueError(
                f"{self.key}: declara base {self.reference_basis} sin rango de referencia"
            )
        # El tipo es `str`, y un valor fuera de estos tres no avisa por ningún lado: ni el motor
        # (`baseline.watches`) ni el perfil, que pintaría «Leve: .» sin cifra.
        if self.concerning not in CONCERNING_SIDES:
            raise ValueError(
                f"{self.key}: `concerning` {self.concerning!r} no es ninguno de "
                f"{sorted(CONCERNING_SIDES)}"
            )

    def clamp_to_physical(self, value: float) -> float:
        """Acota un valor al rango fisicamente posible.

        Solo para **datos sinteticos** (simulador, inyeccion de deterioro), donde
        acotar mantiene el escenario dentro de lo que un cuerpo puede hacer. Una
        lectura real fuera de rango NO se acota: se rechaza, porque significa que
        el sensor esta roto y acotarla la disfrazaria de dato bueno.
        """
        if self.physical_min is not None:
            value = max(value, self.physical_min)
        if self.physical_max is not None:
            value = min(value, self.physical_max)
        return value

    def is_physically_possible(self, value: float) -> bool:
        if self.physical_min is not None and value < self.physical_min:
            return False
        return not (self.physical_max is not None and value > self.physical_max)

    def critical_bounds(
        self, at_rest: bool, exerting: bool = False
    ) -> tuple[float | None, float | None]:
        """Limites de peligro segun el estado fisiologico.

        Tres tramos: reposo (mas estricto), general, y esfuerzo (mas laxo). Un
        pulso de 150 lpm es un hallazgo sentado, normal corriendo, y 195
        preocupante en cualquier caso.
        """
        if at_rest:
            low, high = self.resting_critical_low, self.resting_critical_high
        elif exerting:
            low, high = self.exertion_critical_low, self.exertion_critical_high
        else:
            return self.critical_low, self.critical_high

        return (
            low if low is not None else self.critical_low,
            high if high is not None else self.critical_high,
        )

    @property
    def is_standard(self) -> bool:
        return self.system is CodeSystem.LOINC

    @property
    def display_es(self) -> str:
        """El nombre con que lo lee la tripulación: en español, con su origen en `names_es`.

        `display` es el nombre de LOINC y se queda en inglés (FHIR y los clientes lo leen); lo
        que va dentro de una frase en castellano es este.
        """
        from app.ingest.names_es import name_es

        return name_es(self.key)


def _c(**kwargs: object) -> VitalCode:
    return VitalCode(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Cardiovascular
# --------------------------------------------------------------------------- #

HEART_RATE = _c(
    key="heart-rate", code="8867-4", display="Heart rate", unit="/min",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=50, reference_high=100,
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto en cualquier estado.
    critical_low=40, critical_high=150,
    # En reposo, una taquicardia mucho menor ya es un hallazgo.
    resting_critical_high=110,
    # En esfuerzo, por encima de la frecuencia maxima teorica de un adulto joven.
    exertion_critical_high=200,
    physical_min=20, physical_max=300
)
RESPIRATORY_RATE = _c(
    key="respiratory-rate", code="9279-1", display="Respiratory rate", unit="/min",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=12, reference_high=20,
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: bradipnea / taquipnea.
    critical_low=8, critical_high=30,
    resting_critical_high=24,
    exertion_critical_high=50,
    physical_min=0, physical_max=80
)
BODY_TEMPERATURE = _c(
    key="body-temperature", code="8310-5", display="Body temperature", unit="Cel",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=36.1, reference_high=37.8,
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: hipotermia / fiebre alta.
    critical_low=35, critical_high=39.5,
    physical_min=20, physical_max=45
)
OXYGEN_SATURATION = _c(
    key="oxygen-saturation", code="2708-6", display="Oxygen saturation in Arterial blood",
    unit="%", system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=95, reference_high=100, concerning="low",
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: hipoxemia.
    critical_low=88,
    physical_min=0, physical_max=100
)
SYSTOLIC_BP = _c(
    key="systolic-bp", code="8480-6", display="Systolic blood pressure", unit="mm[Hg]",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=90, reference_high=130,
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: hipotension / crisis hipertensiva.
    critical_low=80, critical_high=180,
    physical_min=30, physical_max=300
)
DIASTOLIC_BP = _c(
    key="diastolic-bp", code="8462-4", display="Diastolic blood pressure", unit="mm[Hg]",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=60, reference_high=85,
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: crisis hipertensiva.
    critical_high=120,
    physical_min=10, physical_max=200
)
BODY_WEIGHT = _c(
    key="body-weight", code="29463-7", display="Body weight", unit="kg",
    system=CodeSystem.LOINC, domain=Domain.BONE,
    physical_min=20, physical_max=300,
    # Un signo vital («weight», en la definición de la categoría), no la «actividad» del
    # dominio óseo en que se agrupa. 29463-7 está en el conjunto de códigos del perfil de
    # signos vitales de FHIR R4 (valueset-observation-vitalsignresult, leído el 2026-10-26).
    category=ObservationCategory.VITAL_SIGNS,
)
HRV_SDNN = _c(
    key="hrv-sdnn", code="80404-7",
    display="R-R interval.standard deviation (Heart rate variability)", unit="ms",
    system=CodeSystem.LOINC, domain=Domain.CARDIOVASCULAR,
    reference_low=50, reference_high=200, concerning="low",
    reference_basis=ReferenceBasis.OBSERVED,
    physical_min=0, physical_max=1000
)
HRV_RMSSD = _c(
    key="hrv-rmssd", code="hrv-rmssd", display="Heart rate variability (RMSSD)", unit="ms",
    system=CodeSystem.EMMA, domain=Domain.CARDIOVASCULAR,
    reference_low=20, reference_high=100, concerning="low",
    reference_basis=ReferenceBasis.OBSERVED,
    physical_min=0, physical_max=1000
)
ORTHOSTATIC_DROP = _c(
    key="orthostatic-drop", code="orthostatic-drop",
    display="Orthostatic systolic drop on standing", unit="mm[Hg]",
    system=CodeSystem.EMMA, domain=Domain.CARDIOVASCULAR,
    reference_low=0, reference_high=20, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=-100, physical_max=200
)

# --------------------------------------------------------------------------- #
# Conductual
# --------------------------------------------------------------------------- #

PVT_MEAN_RT = _c(
    key="pvt-mean-rt", code="pvt-mean-rt",
    display="Psychomotor vigilance task, mean reaction time", unit="ms",
    system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
    reference_low=200, reference_high=350, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=50, physical_max=10000
)
PVT_LAPSES = _c(
    key="pvt-lapses", code="pvt-lapses",
    display="Psychomotor vigilance task, lapses (RT > 500 ms)", unit="{count}",
    system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
    reference_low=0, reference_high=3, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0
)
SLEEP_DURATION = _c(
    key="sleep-duration", code="93832-4", display="Sleep duration", unit="h",
    system=CodeSystem.LOINC, domain=Domain.BEHAVIORAL,
    # Lo da el actígrafo, sin un clínico delante: «activity», cuya definición pone de ejemplo
    # «sleep data». No es un cuestionario («survey», la del dominio conductual).
    category=ObservationCategory.ACTIVITY,
    # UNA RECOMENDACION NO ES UN UMBRAL DE ALERTA.
    #
    # Aqui hubo 7-9 h, que es lo que se *recomienda* dormir. La validacion
    # externa contra MMASH marco al 95 % de los sujetos sanos por ese rango:
    # adultos sanos reales dormian 4-6 h. Peor, era incoherente con el propio
    # proyecto — el simulador usa 6,0 h como valor nominal documentado para
    # tripulacion de la ISS, o sea que la linea base de EMMA caia fuera del rango
    # de referencia de EMMA.
    #
    # El limite inferior pasa a ser el umbral de **preocupacion clinica**, no el
    # de recomendacion. Ver `compliance/external-validation.md`.
    reference_low=5, reference_high=10, concerning="low",
    reference_basis=ReferenceBasis.OBSERVED,
    # Peligro absoluto: privacion severa de sueno.
    critical_low=3,
    physical_min=0, physical_max=24
)
SLEEP_EFFICIENCY = _c(
    key="sleep-efficiency", code="sleep-efficiency", display="Sleep efficiency", unit="%",
    system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
    # Del actígrafo, como la duración: «activity» («sleep data»), no «survey».
    category=ObservationCategory.ACTIVITY,
    # MISMO ERROR QUE TENIA `sleep-duration`: aqui habia 85-100, que es el
    # **objetivo clinico** de eficiencia del sueno, no el rango de la gente sana.
    # En MMASH, 22 adultos sanos dieron mediana 84,9 % y minimo 73,5 %: el 52 %
    # caia por debajo de 85. Usar el objetivo como umbral marca a la mitad de la
    # poblacion sana.
    #
    # El limite inferior pasa a 75 %, que es donde se empieza a sospechar
    # alteracion del sueno. Con ese valor, 1 de 21 sujetos de MMASH queda por
    # debajo (~5 %), que es lo que cabe esperar de un hallazgo en gente sana.
    reference_low=75, reference_high=100, concerning="low",
    reference_basis=ReferenceBasis.OBSERVED,
    physical_min=0, physical_max=100
)
CIRCADIAN_SHIFT = _c(
    key="circadian-shift", code="circadian-shift",
    display="Circadian phase shift from mission schedule", unit="h",
    system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
    reference_low=-1, reference_high=1,
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=-24, physical_max=24
)
MOOD_VALENCE = _c(
    key="mood-valence", code="mood-valence", display="Self-reported mood valence",
    unit="{score}", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
    reference_low=4, reference_high=10, concerning="low",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0, physical_max=10
)

# --------------------------------------------------------------------------- #
# Radiacion
# --------------------------------------------------------------------------- #

ABSORBED_DOSE_RATE = _c(
    key="absorbed-dose-rate", code="absorbed-dose-rate",
    display="Absorbed radiation dose rate", unit="uGy/h",
    system=CodeSystem.EMMA, domain=Domain.RADIATION,
    reference_low=0, reference_high=20, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    # Una tasa de dosis asi no es variacion normal: es un evento. El fondo en
    # orbita baja ronda 2-20 uGy/h, y un evento de particulas solares lo eleva
    # dos ordenes de magnitud.
    #
    # Sin este limite la radiacion quedaba **sin ninguna proteccion** mientras no
    # hubiera linea base personal, que es justo el principio de mision. Lo
    # destapo una prueba del escenario SPE al subir MIN_SAMPLES.
    critical_high=100,
    physical_min=0
)
CUMULATIVE_DOSE = _c(
    key="cumulative-dose", code="cumulative-dose",
    display="Cumulative effective radiation dose", unit="mSv",
    system=CodeSystem.EMMA, domain=Domain.RADIATION,
    reference_low=0, reference_high=600, concerning="high",
    reference_basis=ReferenceBasis.LIMIT,
    physical_min=0
)

# --------------------------------------------------------------------------- #
# Osea
# --------------------------------------------------------------------------- #

EXERCISE_MINUTES = _c(
    key="exercise-minutes", code="exercise-minutes",
    display="Resistive exercise duration", unit="min",
    system=CodeSystem.EMMA, domain=Domain.BONE,
    reference_low=60, reference_high=150, concerning="low",
    reference_basis=ReferenceBasis.GUIDELINE,
    physical_min=0, physical_max=1440
)
LOADING_IMPACTS = _c(
    key="loading-impacts", code="loading-impacts",
    display="Mechanical loading impacts (accelerometry)", unit="{count}",
    system=CodeSystem.EMMA, domain=Domain.BONE,
    reference_low=1000, reference_high=20000, concerning="low",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0
)
NTX_TELOPEPTIDE = _c(
    key="ntx-telopeptide", code="27939-8",
    display="Collagen crosslinked N-telopeptide [Moles/volume] in Urine",
    # Moles/volume, de ahi nmol/L.
    unit="nmol/L", system=CodeSystem.LOINC, domain=Domain.BONE,
    reference_low=5, reference_high=65, concerning="high",
    reference_basis=ReferenceBasis.OBSERVED,
    physical_min=0,
    # Se mide en orina en un laboratorio: no es la «actividad» del dominio óseo.
    category=ObservationCategory.LABORATORY,
)

# --------------------------------------------------------------------------- #
# Inmune
# --------------------------------------------------------------------------- #

SYMPTOM_BURDEN = _c(
    key="symptom-burden", code="symptom-burden",
    display="Self-reported symptom burden", unit="{score}",
    system=CodeSystem.EMMA, domain=Domain.IMMUNE,
    reference_low=0, reference_high=2, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0, physical_max=10,
    # Un diario de síntomas con escala de autoinforme: «survey», no el «laboratory» del dominio
    # inmune, que es el de los análisis de sangre y saliva.
    category=ObservationCategory.SURVEY,
)
CORTISOL_SALIVARY = _c(
    key="cortisol-salivary", code="2142-8",
    display="Cortisol [Mass/volume] in Saliva (oral fluid)",
    # Mass/volume, no Moles/volume: la unidad tiene que ser masica.
    unit="ug/dL", system=CodeSystem.LOINC, domain=Domain.IMMUNE,
    reference_low=0.07, reference_high=0.65, concerning="high",
    reference_basis=ReferenceBasis.OBSERVED,
    physical_min=0
)
LATENT_VIRUS_SHEDDING = _c(
    key="latent-virus-shedding", code="latent-virus-shedding",
    display="Latent herpesvirus reactivation (EBV/VZV shedding)", unit="{count}",
    system=CodeSystem.EMMA, domain=Domain.IMMUNE,
    reference_low=0, reference_high=0, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0
)


# Hemograma: las analiticas reales de Inspiration4 (OSDR, OSD-569). Rango de referencia: el
# del laboratorio, publicado con el propio dataset (poblacion adulta sana). Sin limite critico:
# no hay uno defendible para una tripulacion sana, y sin el no se alerta sin base personal.
def _count(key: str, code: str, display: str, low: float, high: float) -> VitalCode:
    return _c(
        key=key, code=code, display=display, unit="10*3/uL",
        system=CodeSystem.LOINC, domain=Domain.IMMUNE,
        reference_low=low, reference_high=high, concerning="both",
        reference_basis=ReferenceBasis.OBSERVED,
        physical_min=0, physical_max=500,
    )


LEUKOCYTES = _count(
    "leukocytes", "6690-2", "Leukocytes [#/volume] in Blood by Automated count", 3.8, 10.8
)
LYMPHOCYTES = _count(
    "lymphocytes", "731-0", "Lymphocytes [#/volume] in Blood by Automated count", 0.85, 3.9
)
NEUTROPHILS = _count(
    "neutrophils", "751-8", "Neutrophils [#/volume] in Blood by Automated count", 1.5, 7.8
)

# --------------------------------------------------------------------------- #
# Medidas ecograficas (app/imaging/measure.py)
#
# Sin rango de referencia ni limite critico, a proposito. Los umbrales publicados del
# diametro de la vaina del nervio optico cambian de un estudio a otro, el punto de
# referencia de la medida esta discutido (Crit Care Med 2025, PMID 40459386) y en vuelo
# el area de la yugular se multiplica en gente sana (Marshall-Goebel 2019). Un umbral
# poblacional aqui alarmaria a toda la tripulacion. Estas medidas se leen contra la
# linea base personal, que es para lo que sirven.
# --------------------------------------------------------------------------- #

def _onsd(side: str) -> VitalCode:
    return _c(
        key=f"onsd-{side}", code=f"onsd-{side}",
        display=f"Optic nerve sheath diameter, {side} eye (US)", unit="mm",
        system=CodeSystem.EMMA, domain=Domain.NEURO_OCULAR, concerning="high",
        # Fuera de esto no es una vaina ensanchada: es un calibre mal puesto. El tope no
        # es estrecho a proposito: el informe de evidencia de SANS del HRP (2017) recoge
        # en vuelo una vaina de unos 12 mm. Con 15 se habria rechazado un caso real.
        physical_min=1, physical_max=20,
    )


def _ijv(side: str) -> VitalCode:
    return _c(
        key=f"ijv-csa-{side}", code=f"ijv-csa-{side}",
        display=f"Internal jugular vein cross-sectional area, {side} (US)", unit="mm2",
        system=CodeSystem.EMMA, domain=Domain.CARDIOVASCULAR, concerning="high",
        # En vuelo la media fue 70,3 mm2 (Marshall-Goebel 2019): el tope deja margen.
        physical_min=0, physical_max=1000,
    )


ONSD_RIGHT, ONSD_LEFT = _onsd("right"), _onsd("left")
IJV_CSA_RIGHT, IJV_CSA_LEFT = _ijv("right"), _ijv("left")
BLADDER_VOLUME = _c(
    key="bladder-volume", code="15309-8",
    display="Urinary bladder Volume by derived from height, width and length (US)",
    # Vol, y cm3 es la unidad de ejemplo de la ficha.
    unit="cm3", system=CodeSystem.LOINC, domain=Domain.GENITOURINARY, concerning="high",
    physical_min=0, physical_max=5000,
)

# --------------------------------------------------------------------------- #
# Dolor (app/pain/)
#
# Un solo indicador: la intensidad MAXIMA de cada informe, en la escala numerica verbal de
# 0 a 10. Donde duele y como duele no son una serie numerica: van en el asiento
# `pain-report` que cita esta lectura, y el analisis no los lee. Si cada zona fuera su
# propia serie, la linea base mezclaria una rodilla con una lumbar.
#
# Rango de referencia 0-3, de diseno: es el tramo "leve" de la escala numerica, no un
# rango observado en poblacion. Sin limite critico: la intensidad de un autoinforme no
# es un umbral de peligro defendible, asi que sin linea base personal no alerta.
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Hidratacion y riñon (especificacion del equipo §9, escenario "hidratacion/renal")
#
# NASA mide la produccion de orina para vigilar el riesgo de calculos renales y ajustar
# dieta, ejercicio e hidratacion ("The Human Body in Space"). Tres codigos LOINC leidos en su
# ficha el 2026-09-26, cada uno con la unidad de su propiedad (invariante 2):
#   fluid-intake-24h       -> 9108-2  Fluid intake total 24 hour. VRat:24H → mL/(24.h).
#   urine-volume-24h       -> 3167-4  Volume of 24 hour Urine. Vol:24H → mL.
#   urine-specific-gravity -> 2965-2  Specific gravity of Urine. SpGrav:Pt → adimensional.
# Sin limites de peligro: no hay uno defendible para una persona sana, asi que sin linea
# base personal no alertan. La ingesta lleva como guia la provision minima de agua de
# NASA-STD-3001 Vol 2 [V2 6109], 2,5 L/dia por tripulante: una guia no alerta.
# --------------------------------------------------------------------------- #

FLUID_INTAKE = _c(
    key="fluid-intake-24h", code="9108-2", display="Fluid intake total 24 hour",
    unit="mL/(24.h)", system=CodeSystem.LOINC, domain=Domain.GENITOURINARY,
    reference_low=2500, concerning="low", reference_basis=ReferenceBasis.GUIDELINE,
    physical_min=0, physical_max=20000,
    # Un registro de lo que se bebe: ni una imagen (la del dominio genitourinario) ni un análisis
    # de una muestra, ni un cuestionario. Ninguna de las nueve categorías lo describe.
    category=NoCategory.NONE_FITS,
)
URINE_VOLUME = _c(
    key="urine-volume-24h", code="3167-4", display="Volume of 24 hour Urine",
    unit="mL", system=CodeSystem.LOINC, domain=Domain.GENITOURINARY, concerning="low",
    physical_min=0, physical_max=15000,
    # Sale del análisis de la muestra: en vuelo, del litio de cada bolsa analizado en Tierra
    # (`data/measurement_cost.json`, «orina-24h-en-tierra»). «laboratory», no «imaging».
    category=ObservationCategory.LABORATORY,
)
URINE_SPECIFIC_GRAVITY = _c(
    key="urine-specific-gravity", code="2965-2", display="Specific gravity of Urine",
    unit="1", system=CodeSystem.LOINC, domain=Domain.GENITOURINARY, concerning="high",
    physical_min=0.990, physical_max=1.060,
    # Se mide sobre una muestra de orina (tira o refractómetro): «laboratory», no «imaging».
    category=ObservationCategory.LABORATORY,
)

# --------------------------------------------------------------------------- #
# Nutricion (base de conocimiento §5, hipotesis H7)
#
# La comida como contramedida diaria: ingesta real y aceptabilidad. La aceptabilidad usa la
# escala hedonica de 9 puntos con que el Space Food Systems Laboratory de la NASA puntua la
# comida de a bordo, y 6,0 es su criterio de aceptable: una guia sobre la comida, no un umbral
# sobre la persona, asi que no alerta. La "fatiga de menu" es hipotesis y se dice asi.
# La ingesta energetica no lleva referencia: la necesidad es individual.
# --------------------------------------------------------------------------- #

ENERGY_INTAKE = _c(
    key="energy-intake-daily", code="energy-intake-daily", display="Energy intake per day",
    unit="kcal/d", system=CodeSystem.EMMA, domain=Domain.NUTRITION, concerning="low",
    physical_min=0, physical_max=10000,
    # Un registro de ingesta, como la de líquidos: no es un cuestionario («survey», la del
    # dominio de nutrición), y ninguna de las nueve categorías lo describe.
    category=NoCategory.NONE_FITS,
)
APPETITE = _c(
    key="appetite-rating", code="appetite-rating", display="Appetite self-rating (0-10)",
    unit="{score}", system=CodeSystem.EMMA, domain=Domain.NUTRITION, concerning="low",
    physical_min=0, physical_max=10,
)
FOOD_REJECTED = _c(
    key="food-rejected-fraction", code="food-rejected-fraction",
    display="Fraction of served food left uneaten", unit="%", system=CodeSystem.EMMA,
    domain=Domain.NUTRITION, concerning="high", physical_min=0, physical_max=100,
    # Del mismo registro de ingesta: sin categoría, como la energía y los líquidos.
    category=NoCategory.NONE_FITS,
)
FOOD_ACCEPTABILITY = _c(
    key="food-acceptability", code="food-acceptability",
    display="Food acceptability, 9-point hedonic scale", unit="{score}",
    system=CodeSystem.EMMA, domain=Domain.NUTRITION, reference_low=6, reference_high=9,
    concerning="low", reference_basis=ReferenceBasis.GUIDELINE,
    physical_min=1, physical_max=9,
)

PAIN_INTENSITY = _c(
    key="pain-intensity", code="72514-3",
    display="Pain severity - 0-10 verbal numeric rating [Score] - Reported",
    unit="{score}", system=CodeSystem.LOINC, domain=Domain.MUSCULOSKELETAL,
    reference_low=0, reference_high=3, concerning="high",
    reference_basis=ReferenceBasis.DESIGN,
    physical_min=0, physical_max=10,
)

# --------------------------------------------------------------------------- #
# Indicadores descriptivos (decisión del usuario, 2026-10-15; la vitamina D, 2026-10-22)
#
# Salud conductual más allá del ánimo, síntomas visuales y fuerza y forma física entran como
# observaciones: se firman en el ledger como cualquier lectura (invariante 4), `/api/indicators`
# los lista con su sistema de códigos y un panel los enseña con lo leído de su medida
# (`GET /api/indicators/descriptive`). Pero son DESCRIPTIVOS, y eso es una propiedad del
# código, no una promesa:
#
#   - el estado no los lee: `routes._assess` los aparta antes de la línea base, así que no
#     mueven niveles, alertas ni puntuaciones (invariante 5);
#   - no se simulan (el simulador no tiene modelo de ninguno);
#   - no cuentan en la huella de las reglas (`core/versioning.py`): no deciden nada;
#   - no figuran entre lo que evalúa un dominio (`evaluated_by_domain`: riesgos, mapa
#     anatómico, contexto de una alerta) ni en lo que depende de un dato (`timeline.emma_map`).
#
# Solo entra lo que tiene una medida o un instrumento con fuente leída, y lo leído vive en
# `data/instruments_read.json` (bloque `measures`) con su frase exacta. Sin rango de referencia
# ni límite crítico, a propósito: los requisitos de NASA-STD-3001 Vol. 1 que se citan junto a
# ellos (el 80 % del valor previo al vuelo) se enseñan como frase, no se evalúan.
#
# Se buscó y se dejó fuera el par isocinético de la rodilla, que es la prueba de fuerza del
# requisito médico (HRP-47072: «isokinetic muscle strength and endurance testing of the legs
# and trunk muscles», a 60°/s): lo leído no dice de qué pierna ni el protocolo entero (lo remite
# a NASA AMMERD 6.1, que no es público), y un indicador sin definición completa no se inventa.
#
# La vitamina D 25-OH entró después, por otra decisión del usuario (2026-10-22): la conversación
# de ideación pedía pasar de «Vitamin D risk» a volver a medir el biomarcador, y NASA la vigila
# (OCHMO-MTB-013 Rev D, p. 16). Entra con las mismas reglas: descriptiva, sin rango ni límite,
# fuera del riesgo, de la huella y del simulador. Su fecha va en `DESCRIPTIVE_DECISIONS`.
#
# La glucosa capilar con glucómetro entró el 2026-11-04 (punto del calendario «Guía de glucosa
# capilar»): hasta entonces el catálogo solo tenía la glucosa de laboratorio (2345-7, suero o
# plasma), y una guía de glucómetro apuntada a ella mentía sobre la muestra (invariante 2). Entra
# descriptiva, con las mismas reglas: ninguna fuente leída da un umbral para una tripulación
# sana (las cifras de la página de los CDC son objetivos para personas con diabetes), MedlinePlus
# dice que la del pinchazo en el dedo es menos exacta que la de vena, y no se simula: no se puede
# dar la tasa de falsa alarma ni la sensibilidad de algo que no tiene datos (invariante 5).
# --------------------------------------------------------------------------- #

DESCRIPTIVE_DECIDED_ON = "2026-10-15"
VITAMIN_D_DECIDED_ON = "2026-10-22"
GLUCOSE_CAPILLARY_DECIDED_ON = "2026-11-04"


@dataclass(frozen=True)
class LoincRead:
    """Lo leído de la ficha de un código LOINC. La PROPIEDAD manda la unidad (invariante 2).

    loinc.org devolvía el 2026-10-16 una comprobación de Cloudflare a cualquier cliente sin
    navegador (403 con WebFetch, «Just a moment...» con curl). La ficha se leyó, como las de
    las analíticas (`data/lab_loinc.json`), en el servidor público tx.fhir.org con LOINC 2.82:
    `url` es la consulta exacta, y cada parte se resolvió a su nombre con otra consulta a la
    misma dirección con el código de la parte.
    """

    component: str
    property: str
    system: str
    scale: str
    method: str | None
    example_ucum: str
    status: str
    version: str
    read_on: str
    url: str


def _lookup_url(code: str) -> str:
    return (
        "https://tx.fhir.org/r4/CodeSystem/$lookup?system=http%3A%2F%2Floinc.org"
        f"&code={code}&_format=json&property=COMPONENT&property=PROPERTY&property=TIME_ASPCT"
        "&property=SYSTEM&property=SCALE_TYP&property=METHOD_TYP&property=EXAMPLE_UCUM_UNITS"
        "&property=STATUS&property=CLASS&property=DefinitionDescription"
    )


# Fuerza de prensión. HRP-47072 (Tabla 3) la cuenta entre las pruebas de forma física de antes y
# después de una misión larga en la ISS («Handgrip»), sin decir con qué instrumento ni con qué
# mano. LOINC la codifica por mano y con dinamómetro, con la propiedad FUERZA (`Force`): la unidad
# de ejemplo es la libra-fuerza ([lbf_av]) y EMMA la registra en kilogramos-fuerza (kgf), que es
# lo que marca un dinamómetro de mano en kilos. NO en kg: un kilogramo es masa, y adoptar el
# código con una unidad de masa sería el error silencioso de la invariante 2.
_GRIP_FORCE_UNIT = "kgf"
FORCE_UNITS = frozenset({"N", "kgf", "[lbf_av]"})

DESCRIPTIVE_LOINC: dict[str, LoincRead] = {
    # Consumo de oxígeno pico por kilo de peso. VRatCnt (tasa de volumen por contenido), escala
    # cuantitativa; la unidad de ejemplo de la ficha, tal cual: mL/min/kg{body_wt}.
    "vo2-peak": LoincRead(
        component="Oxygen consumption/Body weight^peak during exercise",
        property="VRatCnt", system="^Patient", scale="Qn", method=None,
        example_ucum="mL/min/kg{body_wt}", status="ACTIVE", version="2.82",
        read_on="2026-10-16", url=_lookup_url("94122-9"),
    ),
    "grip-strength-right": LoincRead(
        component="Grip strength", property="Force", system="Hand.right", scale="Qn",
        method="Dynamometer", example_ucum="[lbf_av]", status="ACTIVE", version="2.82",
        read_on="2026-10-16", url=_lookup_url("83174-3"),
    ),
    "grip-strength-left": LoincRead(
        component="Grip strength", property="Force", system="Hand.left", scale="Qn",
        method="Dynamometer", example_ucum="[lbf_av]", status="ACTIVE", version="2.82",
        read_on="2026-10-16", url=_lookup_url("83173-5"),
    ),
    # 25-hidroxivitamina D total (D2 + D3) en suero o plasma, propiedad MASA POR VOLUMEN (MCnc):
    # ng/mL, la unidad de ejemplo de la ficha y la que escribe la norma médica de NASA
    # (OCHMO-MTB-013 Rev D, [6037]: «35-90 ng/ml»). La misma medida en nmol/L es otra
    # propiedad (SCnc) con OTRO código, 68438-1, leído el mismo día: adoptar 62292-8 con nmol/L
    # sería el error silencioso de la invariante 2. Total y no solo D3 (1989-3, MCnc): las
    # fuentes dicen «25-OH Vitamin D» y «serum 25-hydroxyvitamin D», sin separar D2 de D3.
    "vitamin-d-25oh": LoincRead(
        component="Calcidiol+ercalcidiol", property="MCnc", system="Ser/Plas", scale="Qn",
        method=None, example_ucum="ng/mL", status="ACTIVE", version="2.82",
        read_on="2026-10-22", url=_lookup_url("62292-8"),
    ),
    # Glucosa en sangre CAPILAR por glucómetro: propiedad MASA POR VOLUMEN (MCnc), mg/dL, la
    # unidad de ejemplo de la ficha. Leída el 2026-11-04 en tx.fhir.org con LOINC 2.83 (loinc.org
    # seguía devolviendo 403 a WebFetch), con cada parte resuelta a su nombre: LP14635-4 Glucose,
    # LP6827-2 MCnc, LP6960-1 Pt, LP7068-2 BldC, LP7753-9 Qn, LP6298-6 Glucometer. No es la
    # 2345-7 del catálogo (suero o plasma, sin método): otra muestra, otro código. En mmol/L
    # sería otra propiedad (SCnc) y otro código: no se adopta con esa unidad (invariante 2).
    "glucose-capillary": LoincRead(
        component="Glucose", property="MCnc", system="BldC", scale="Qn",
        method="Glucometer", example_ucum="mg/dL", status="ACTIVE", version="2.83",
        read_on="2026-11-04", url=_lookup_url("41653-7"),
    ),
}

# Síntomas visuales: el cuestionario de visión en vuelo que describe el informe de evidencia del
# SANS (HRP, 2017, p. 27). La fuente da tres categorías con palabras (mild, moderate, severe) y
# la pregunta previa de si se notó algún cambio; los números 0 a 3 son de EMMA, y se dice
# (`instruments_read.json`, `numbering`).
VISION_CHANGE = _c(
    key="vision-change", code="vision-change",
    display="Change in vision since launch or the last in-flight exam (in-flight vision "
    "questionnaire)",
    unit="{score}", system=CodeSystem.EMMA, domain=Domain.NEURO_OCULAR, concerning="high",
    physical_min=0, physical_max=3,
    # Un cuestionario: «survey», no la «imaging» del dominio neuro-ocular.
    category=ObservationCategory.SURVEY,
)
# Salud conductual más allá del ánimo: la carga de trabajo percibida. NASA-STD-3001 Vol. 1 §4.3
# nombra el NASA-TLX entre las herramientas con que se valora; EMMA registra la puntuación
# global que da su procedimiento (de 0 a 100), no pasa el procedimiento. Una carga alta y una
# baja preocupan las dos (la misma §4.3), de ahí `both`.
NASA_TLX = _c(
    key="nasa-tlx-workload", code="nasa-tlx-workload",
    display="NASA Task Load Index (NASA-TLX), overall weighted workload score",
    unit="{score}", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL, concerning="both",
    physical_min=0, physical_max=100,
    category=ObservationCategory.SURVEY,
)
# Forma física: la capacidad aeróbica, que NASA mide en vuelo y frente a la de antes del vuelo
# ([V1 4003]; OCHMO-TB-031). Un VO2 pico de cero no es un dato: es un aparato mal leído.
VO2_PEAK = _c(
    key="vo2-peak", code="94122-9",
    display="Oxygen consumption (VO2)/Body weight [Volume Rate Content] --peak during exercise",
    unit=DESCRIPTIVE_LOINC["vo2-peak"].example_ucum, system=CodeSystem.LOINC,
    domain=Domain.CARDIOVASCULAR, concerning="low",
    physical_min=1, physical_max=100,
    # Una prueba con un instrumento sencillo, no un signo vital: el perfil de signos vitales no
    # admite su código.
    category=ObservationCategory.EXAM,
)
GRIP_RIGHT = _c(
    key="grip-strength-right", code="83174-3", display="Grip strength Hand - right Dynamometer",
    unit=_GRIP_FORCE_UNIT, system=CodeSystem.LOINC, domain=Domain.MUSCULOSKELETAL,
    concerning="low", physical_min=0, physical_max=200,
    # Con un dinamómetro, en una prueba: «exam», no la «survey» del dominio.
    category=ObservationCategory.EXAM,
)
GRIP_LEFT = _c(
    key="grip-strength-left", code="83173-5", display="Grip strength Hand - left Dynamometer",
    unit=_GRIP_FORCE_UNIT, system=CodeSystem.LOINC, domain=Domain.MUSCULOSKELETAL,
    concerning="low", physical_min=0, physical_max=200,
    category=ObservationCategory.EXAM,
)
# Vitamina D: NASA vigila su estado en la tripulación (OCHMO-MTB-013 Rev D, p. 16) y la mide en
# el suero de la sangre que toma antes, durante y después del vuelo (Hardy et al., 2025). Dominio
# óseo, como el calcio: la norma la trata en la pérdida ósea. Preocupan los dos extremos (la
# misma norma, p. 15: «risk of hypercalcemia» con la suplementación). El intervalo de 0 a 300
# ng/mL es un límite de plausibilidad de EMMA, sin fuente: no es un rango clínico y no evalúa.
VITAMIN_D_25OH = _c(
    key="vitamin-d-25oh", code="62292-8",
    display="25-Hydroxyvitamin D3+25-Hydroxyvitamin D2 [Mass/volume] in Serum or Plasma",
    unit=DESCRIPTIVE_LOINC["vitamin-d-25oh"].example_ucum, system=CodeSystem.LOINC,
    domain=Domain.BONE, concerning="both", physical_min=0, physical_max=300,
    # Un analito de suero: laboratorio, no la «actividad» del dominio óseo en que se agrupa.
    category=ObservationCategory.LABORATORY,
)
# Glucosa capilar con glucómetro. Dominio de nutrición, como la glucosa de laboratorio (estado
# metabólico). Preocupan los dos extremos, como en todos los analitos. El intervalo de 0 a 1000
# mg/dL es un límite de plausibilidad de EMMA, sin fuente: no es un rango clínico y no evalúa.
GLUCOSE_CAPILLARY = _c(
    key="glucose-capillary", code="41653-7",
    display="Glucose [Mass/volume] in Capillary blood by Glucometer",
    unit=DESCRIPTIVE_LOINC["glucose-capillary"].example_ucum, system=CodeSystem.LOINC,
    domain=Domain.NUTRITION, concerning="both", physical_min=0, physical_max=1000,
    # Un analito de sangre (clase CHEM de su ficha), aunque se lea a pie de cama: laboratorio.
    category=ObservationCategory.LABORATORY,
)

# --------------------------------------------------------------------------- #
# La química de la orina de 24 horas del riesgo de cálculos renales (decisión del usuario,
# 2026-10-26)
#
# El informe de evidencia del riesgo (HRP, 2024) valora el riesgo con la química de la orina de 24
# horas: calcio, oxalato, ácido úrico, citrato, pH, sodio, osmolalidad y la sobresaturación
# calculada. Hasta esta ronda solo se nombraban en la cobertura de los riesgos del HRP, como
# pendientes sin código (`data/hrp_risks_coverage.json`). Entran como DESCRIPTIVOS, con las mismas
# reglas que los demás: se firman y se enseñan, el estado no los lee, no se simulan y no cuentan
# en la huella. Sin rango ni límite crítico: el perfil de riesgo de cálculos que describe el
# informe no predice un cálculo, «it illustrates to the flight surgeon and crewmember the current
# urine chemistry environment» (p. 23), y los umbrales que cita (hipercalciuria, oxalato) se
# citan, no se evalúan. El rango físico de cada uno es un límite de plausibilidad de EMMA, sin
# fuente: no es un rango clínico.
#
# Siete códigos LOINC leídos en su ficha el 2026-10-26 en tx.fhir.org, ya con LOINC 2.83 (las
# fichas anteriores se leyeron con la 2.82), cada uno con la unidad de su PROPIEDAD (invariante 2):
#   * Calcio, oxalato, urato y citrato: MRat (masa por tiempo), en mg/(24.h). El informe los
#     escribe en mg al día («>300mg/day», «45mg/day», «470 to 700 mg a day»). La misma medida en
#     moles por tiempo (SRat) es OTRO código, leído el mismo día y descartado: 14637-3 (calcio),
#     14862-7 (oxalato), 14935-1 (urato) y 14650-6 (citrato). El urato trae como unidad de ejemplo
#     g/(24.h): misma propiedad, y EMMA lo registra en mg/(24.h) como los otros tres.
#   * Sodio: SRat (sustancia por tiempo), mmol/(24.h), la unidad de ejemplo. El informe no da
#     cifra; el sodio en sangre del catálogo también va en sustancia (2951-2, mmol/L). En masa
#     por tiempo es 21527-7, descartado.
#   * pH: LsCnc (logaritmo de la concentración de sustancia), escala SemiQn, [pH].
#   * Osmolalidad: Osmol, mosm/kg.
# Los siete son de la orina de 24 horas (TIME_ASPCT 24H). La misma medida en una micción suelta es
# otro código (2756-5 el pH, 2695-5 la osmolalidad): el informe nombra el pH y la osmolalidad sin
# decir de qué recogida, y EMMA toma la de 24 h porque es la del perfil de riesgo; lo dice la
# medida leída (`data/instruments_read.json`).
#
# La sobresaturación calculada no tiene código LOINC adecuado (`NO_LOINC_AVAILABLE`, con lo
# buscado en `api/descriptive.py`): EMMA registra la sobresaturación relativa del oxalato cálcico,
# un cociente adimensional, con código propio.
# --------------------------------------------------------------------------- #

RENAL_URINE_DECIDED_ON = "2026-10-26"
RENAL_URINE_READ_ON = "2026-10-26"
# Masa por tiempo (MRat): las dos unidades de la propiedad que aparecen en las fichas leídas.
MASS_PER_DAY_UNITS = frozenset({"mg/(24.h)", "g/(24.h)"})


def _urine_read(
    component: str, prop: str, scale: str, example_ucum: str, code: str
) -> LoincRead:
    return LoincRead(
        component=component, property=prop, system="Urine", scale=scale, method=None,
        example_ucum=example_ucum, status="ACTIVE", version="2.83",
        read_on=RENAL_URINE_READ_ON, url=_lookup_url(code),
    )


RENAL_URINE_LOINC: dict[str, LoincRead] = {
    "urine-calcium-24h": _urine_read("Calcium", "MRat", "Qn", "mg/(24.h)", "6874-2"),
    "urine-oxalate-24h": _urine_read("Oxalate", "MRat", "Qn", "mg/(24.h)", "2701-1"),
    "urine-urate-24h": _urine_read("Urate", "MRat", "Qn", "g/(24.h)", "3087-4"),
    "urine-citrate-24h": _urine_read("Citrate", "MRat", "Qn", "mg/(24.h)", "6687-8"),
    "urine-ph-24h": _urine_read("pH", "LsCnc", "SemiQn", "[pH]", "27378-9"),
    "urine-sodium-24h": _urine_read("Sodium", "SRat", "Qn", "mmol/(24.h)", "2956-1"),
    # El componente de la osmolalidad es «Observation» en la ficha: así lo publica LOINC.
    "urine-osmolality-24h": _urine_read("Observation", "Osmol", "Qn", "mosm/kg", "2694-8"),
}


def _urine(key: str, code: str, display: str, unit: str, concerning: str, high: float) -> VitalCode:
    return _c(
        key=key, code=code, display=display, unit=unit, system=CodeSystem.LOINC,
        domain=Domain.GENITOURINARY, concerning=concerning, physical_min=0, physical_max=high,
        # La química de la orina de 24 horas del riesgo renal se analiza en un laboratorio:
        # «laboratory», no la «imagen» que el dominio genitourinario toma de la ecografía.
        category=ObservationCategory.LABORATORY,
    )


# Lo que preocupa de cada uno es lo que nombra el informe (pp. 6, 9, 12 y 23): hipercalciuria,
# hiperoxaluria, hiperuricosuria, hipocitraturia, el pH bajo y, para la estruvita, el alto, más
# sodio urinario y más osmolalidad.
URINE_CALCIUM_24H = _urine(
    "urine-calcium-24h", "6874-2", "Calcium [Mass/time] in 24 hour Urine", "mg/(24.h)",
    "high", 2000,
)
URINE_OXALATE_24H = _urine(
    "urine-oxalate-24h", "2701-1", "Oxalate [Mass/time] in 24 hour Urine", "mg/(24.h)",
    "high", 500,
)
URINE_URATE_24H = _urine(
    "urine-urate-24h", "3087-4", "Urate [Mass/time] in 24 hour Urine", "mg/(24.h)",
    "high", 3000,
)
URINE_CITRATE_24H = _urine(
    "urine-citrate-24h", "6687-8", "Citrate [Mass/time] in 24 hour Urine", "mg/(24.h)",
    "low", 3000,
)
# La escala de pH entera: un límite de definición, no de plausibilidad clínica.
URINE_PH_24H = _urine("urine-ph-24h", "27378-9", "pH of 24 hour Urine", "[pH]", "both", 14)
URINE_SODIUM_24H = _urine(
    "urine-sodium-24h", "2956-1", "Sodium [Moles/time] in 24 hour Urine", "mmol/(24.h)",
    "high", 1000,
)
URINE_OSMOLALITY_24H = _urine(
    "urine-osmolality-24h", "2694-8", "Osmolality of 24 hour Urine", "mosm/kg", "high", 2000,
)
# La sobresaturación relativa del oxalato cálcico, calculada de la orina de 24 horas: un cociente
# adimensional («1»). Se elige el oxalato cálcico porque es la sal que más nombran lo leído: el
# cálculo más común lleva calcio (p. 6), el modelo de Glenn simula cristales de oxalato cálcico
# (p. 13) y el anexo de operaciones del informe vigila en vuelo el oxalato cálcico de la orina. La
# brushita, cuya sobresaturación el informe también da (p. 12), queda pendiente en la cobertura.
URINE_CAOX_SUPERSATURATION = _c(
    key="urine-caox-supersaturation-24h", code="urine-caox-supersaturation-24h",
    display="Calcium oxalate relative supersaturation, calculated from 24 hour urine",
    unit="1", system=CodeSystem.EMMA, domain=Domain.GENITOURINARY, concerning="high",
    physical_min=0, physical_max=100,
    # Un cálculo sobre la química de la orina analizada: «laboratory», como los analitos.
    category=ObservationCategory.LABORATORY,
)
RENAL_URINE_CHEMISTRY: tuple[VitalCode, ...] = (
    URINE_CALCIUM_24H, URINE_OXALATE_24H, URINE_URATE_24H, URINE_CITRATE_24H, URINE_PH_24H,
    URINE_SODIUM_24H, URINE_OSMOLALITY_24H, URINE_CAOX_SUPERSATURATION,
)
# Las fichas leídas de los analitos de orina, junto a las de los demás descriptivos: quien explica
# el código de un descriptivo (`api/descriptive.py`) las busca en un solo sitio.
DESCRIPTIVE_LOINC.update(RENAL_URINE_LOINC)


# Densitometría ósea (DXA), descriptiva (decisión del usuario, 2026-10-26)
#
# La banda ósea de `analysis/inferred.py` es INFERIDA: la densidad mineral ósea no se mide en
# vuelo («no system to date measures bone density in-flight», OCHMO-MTB-013 Rev D, p. 19). Se
# mide en Tierra, por densitometría (DXA), antes y después del vuelo. La conversación de ideación
# pedía contrastar lo estimado en vuelo con esas medidas posvuelo; para eso la medida tiene que
# poder entrar, firmada como cualquier lectura (invariante 4). Entra como las demás descriptivas:
# sin rango ni límite, fuera del riesgo, de la huella y del simulador. La comparación con la
# banda vive en `analysis/densitometry.py` y no puntúa ni alerta.
#
# Dos regiones, las que nombra el requisito de NASA ([V1 4026], la misma página: «total hip and
# lumbar spine (L1-L4), as measured by mass dual energy X-ray absorptiometry (DXA)»), y las dos
# en que la banda da su tasa (`simulator.LITERATURE["bmd_loss_pct_per_month"]`: cadera y columna
# lumbar). La propiedad de las dos fichas es MASA POR ÁREA (ArMass): g/cm², la densidad areal
# que da la DXA, no una densidad de volumen (Mass/volume es la de la tomografía, otro código:
# 104939-4 para la cadera). El T-score es otra propiedad y otro código (38267-1 y 38264-8), y no
# se registra: compara con una población, no con el valor previo de esta persona.
#
# Buscado y no adoptado: el cuello femoral, que la norma también vigila ([V1 4027]), no tiene en
# LOINC un código de DXA propio (lo más cercano es «DXA Femur», 24701-5, que no dice qué parte
# del fémur); la cadera de un lado (46278-8 izquierda, 46279-6 derecha), porque lo leído no dice
# de qué lado mide NASA; y «DXA Bone», 46383-6, que no nombra región.
#
# Las fichas se leyeron en tx.fhir.org, como las demás (`LoincRead`), el 2026-10-26: el servidor
# ya da LOINC 2.83. El componente que devuelve la consulta es la parte LP266468-0, que el mismo
# servidor nombra «Views for bone density» (el nombre de las partes de radiología); el nombre
# largo del código dice «Bone density». Se copia lo que da la consulta. Que es una medida y no
# el nombre de un estudio se comprobó el mismo día en la misma ficha, con todas sus
# propiedades: ORDER_OBS «Observation», escala Qn, propiedad ArMass, unidad g/cm2.
# --------------------------------------------------------------------------- #

DENSITOMETRY_DECIDED_ON = "2026-10-26"
# g/cm²: la unidad de ejemplo de las dos fichas, y la de su propiedad (ArMass).
_AREAL_DENSITY_UNIT = "g/cm2"

DENSITOMETRY_LOINC: dict[str, LoincRead] = {
    "bmd-dxa-lumbar-spine": LoincRead(
        component="Views for bone density", property="ArMass", system="Abdomen>Spine.lumbar",
        scale="Qn", method="DXA", example_ucum=_AREAL_DENSITY_UNIT, status="ACTIVE",
        version="2.83", read_on="2026-10-26", url=_lookup_url("24966-4"),
    ),
    "bmd-dxa-hip": LoincRead(
        component="Views for bone density", property="ArMass", system="Lower extremity>Hip",
        scale="Qn", method="DXA", example_ucum=_AREAL_DENSITY_UNIT, status="ACTIVE",
        version="2.83", read_on="2026-10-26", url=_lookup_url("38261-4"),
    ),
}
# Las fichas leídas de los descriptivos están en una sola tabla: quien la lee (el panel, la
# prueba de la unidad) no tiene que saber que estas entraron en otro bloque.
DESCRIPTIVE_LOINC.update(DENSITOMETRY_LOINC)

# Dominio óseo: es la medida de lo que la banda estima. Preocupa la baja (la pérdida). El
# intervalo de 0,1 a 3 g/cm² es un límite de plausibilidad de EMMA, sin fuente: no es un rango
# clínico y no evalúa; una densidad de cero no es un dato, y la comparación divide por la previa.
BMD_DXA_LUMBAR_SPINE = _c(
    key="bmd-dxa-lumbar-spine", code="24966-4",
    display="DXA Lumbar spine [Mass/Area] Bone density",
    unit=DENSITOMETRY_LOINC["bmd-dxa-lumbar-spine"].example_ucum, system=CodeSystem.LOINC,
    domain=Domain.BONE, concerning="low", physical_min=0.1, physical_max=3,
    # Una prueba de imagen con rayos X: «imaging», no la «actividad» del dominio óseo.
    category=ObservationCategory.IMAGING,
)
BMD_DXA_HIP = _c(
    key="bmd-dxa-hip", code="38261-4",
    display="DXA Hip [Mass/Area] Bone density",
    unit=DENSITOMETRY_LOINC["bmd-dxa-hip"].example_ucum, system=CodeSystem.LOINC,
    domain=Domain.BONE, concerning="low", physical_min=0.1, physical_max=3,
    # Una prueba de imagen con rayos X: «imaging», no la «actividad» del dominio óseo.
    category=ObservationCategory.IMAGING,
)
DENSITOMETRY_KEYS = frozenset({BMD_DXA_LUMBAR_SPINE.key, BMD_DXA_HIP.key})

# --------------------------------------------------------------------------- #
# Sensoriomotor y músculo, descriptivos (decimonovena ronda, 2026-10-31)
#
# La base de conocimiento del equipo pone «sensorimotor» y «músculo» entre lo que la gravedad
# altera (§2.1) y pide del musculoesquelético «fuerza, masa, densidad» (§4); la cobertura de los
# riesgos del HRP decía que ningún indicador medía el equilibrio ni la coordinación, ni la masa
# muscular ni la fuerza de las piernas. Entran cuatro medidas, cada una con su instrumento leído
# (`data/instruments_read.json`): las que NASA toma en el protocolo Spaceflight Standard Measures
# (Hardy et al., 2025) y describe el informe de evidencia del riesgo sensoriomotor (HRP, 2022) y el
# del riesgo de músculo y capacidad aeróbica (HRP, 2023). Como los demás descriptivos: se firman y
# se enseñan, el estado no las lee, no se simulan, sin rango ni límite crítico, fuera de la huella.
#
#   * Marcha en tándem: el porcentaje de pasos correctos de diez pasos talón-punta (Hardy et al.:
#     «the median value is used to determine the percent of correct steps for that trial»). Vigila
#     el bajo: «A higher percent of correct steps directly relates to better performance».
#   * Levantarse tras estar tumbado («recovery-from-fall»): los segundos desde la orden de
#     levantarse hasta la postura estable («The time elapsed between the command to stand and the
#     achievement of a stable posture is used as the measure of performance»). Vigila el alto.
#   * Masa magra del cuerpo entero por DXA: la «lean» de la composición corporal que operaciones
#     médicas comparte con Standard Measures («Body composition (bone, fat, lean, body mass,
#     percent fat)», antes y después del vuelo). En kg, la unidad de una masa. El informe de 2023
#     advierte que la masa magra del cuerpo entero no detecta bien lo que pierden los músculos
#     posturales; se cita en la medida leída, y EMMA no la compara con nada.
#   * Tracción isométrica a medio muslo (IMTP): la fuerza máxima en una plataforma de fuerza («a
#     full-body strength test that measures peak force production using a force plate»), la única
#     medida de fuerza que Standard Measures toma también en vuelo (en el ARED). En newtons (N),
#     unidad de la propiedad fuerza (`FORCE_UNITS`): lo leído no escribe la unidad, y EMMA toma la
#     del SI; no en kgf ni en kg (la prensión va en kgf porque así marca el dinamómetro).
#
# Las cuatro con código propio: LOINC no tiene ninguna (`NO_LOINC_AVAILABLE`, con lo buscado). Se
# agrupan en el dominio musculoesquelético para saber dónde enseñarlas; EMMA no tiene dominio
# sensoriomotor y el estado no las lee. Los rangos físicos son límites de plausibilidad de EMMA,
# sin fuente: no son rangos clínicos y no evalúan. El par isocinético de rodilla sigue fuera: su
# protocolo (AMMERD 6.1) no es público (duodécima ronda).
# --------------------------------------------------------------------------- #

SENSORIMOTOR_MUSCLE_DECIDED_ON = "2026-10-31"

TANDEM_WALK_CORRECT_STEPS = _c(
    key="tandem-walk-correct-steps", code="tandem-walk-correct-steps",
    display="Tandem walk test, percent of correct heel-to-toe steps (Spaceflight Standard "
    "Measures)",
    unit="%", system=CodeSystem.EMMA, domain=Domain.MUSCULOSKELETAL, concerning="low",
    physical_min=0, physical_max=100,
    # Una prueba funcional observada: «exam», no la «survey» del dominio.
    category=ObservationCategory.EXAM,
)
RECOVERY_FROM_FALL_TIME = _c(
    key="recovery-from-fall-time", code="recovery-from-fall-time",
    display="Recovery-from-fall test, time from the command to stand to a stable posture "
    "(Spaceflight Standard Measures)",
    unit="s", system=CodeSystem.EMMA, domain=Domain.MUSCULOSKELETAL, concerning="high",
    # Un tiempo de cero no es un dato. Media hora es plausibilidad de EMMA, sin fuente: debe dejar
    # entrar al tripulante que más tarda, porque lo que se vigila es el extremo alto (los tres
    # minutos y medio de la fuente son lo que sigue de pie después, no un tope de esta cifra).
    physical_min=0.1, physical_max=1800,
    category=ObservationCategory.EXAM,
)
DXA_LEAN_MASS = _c(
    key="dxa-lean-mass", code="dxa-lean-mass",
    display="Lean (soft tissue) mass, whole body, by DXA body composition",
    unit="kg", system=CodeSystem.EMMA, domain=Domain.MUSCULOSKELETAL, concerning="low",
    physical_min=10, physical_max=150,
    # La DXA es una prueba de imagen con rayos X, como la densidad ósea.
    category=ObservationCategory.IMAGING,
)
IMTP_PEAK_FORCE = _c(
    key="imtp-peak-force", code="imtp-peak-force",
    display="Isometric mid-thigh pull (IMTP), peak force on a force plate",
    unit="N", system=CodeSystem.EMMA, domain=Domain.MUSCULOSKELETAL, concerning="low",
    physical_min=1, physical_max=10000,
    category=ObservationCategory.EXAM,
)
# Las dos pruebas sensoriomotoras y las dos de músculo, en el orden del catálogo.
SENSORIMOTOR_TESTS: tuple[VitalCode, ...] = (TANDEM_WALK_CORRECT_STEPS, RECOVERY_FROM_FALL_TIME)
MUSCLE_MEASURES: tuple[VitalCode, ...] = (DXA_LEAN_MASS, IMTP_PEAK_FORCE)
SENSORIMOTOR_MUSCLE: tuple[VitalCode, ...] = (*SENSORIMOTOR_TESTS, *MUSCLE_MEASURES)


# --------------------------------------------------------------------------- #
# Equipo, estrés y cognición, descriptivos (decimonovena ronda, U14, 2026-10-31)
#
# La base de conocimiento del equipo pide fatiga, estrés, cohesión y una batería cognitiva más allá
# de la PVT (§4: «Sueño/cognición … PVT, fatiga»; «Conductual/equipo | estado, carga, cohesión,
# estrés»), y la conversación de ideación, las pruebas del Twins Study («alerta mental, velocidad,
# precisión, orientación espacial, reconocimiento emocional») y la «dinámica de equipo». La regla
# del plan (2026-10-31): un descriptivo nuevo entra solo si se lee un instrumento publicado que NASA
# use en vuelo; si no se lee, no entra y se anota qué se buscó (`data/hrp_risks_coverage.json`).
# Entran, con las mismas reglas que los demás descriptivos (sin rango ni límite; fuera del riesgo,
# de la huella y del simulador):
#
#   * La batería Cognition (Basner et al. 2015), la del proyecto Spaceflight Standard Measures y la
#     del Twins Study: diez pruebas, de las que la PVT ya tiene sus indicadores (`pvt-mean-rt`,
#     `pvt-lapses`) y NO se duplica. De las otras nueve, lo que Dev et al. 2024 publican de 25
#     astronautas en la ISS: la velocidad, «the average response time (in milliseconds)», y la
#     precisión, «the proportion correct to total stimuli» (en el F2B y el LOT, una proporción
#     calculada de otra forma, que la fuente describe); la BART da en vez de precisión una
#     puntuación de riesgo, «Scores range from 0 to 1»; la MPT no tiene precisión («No accuracy
#     score was calculated for the MPT»). Los rangos físicos de la velocidad (de 1 a 60 000 ms) son
#     un límite de plausibilidad de EMMA, sin fuente; los de las proporciones, de 0 a 1, son los de
#     una proporción.
#   * El estrés autoinformado del Reaction Self Test (Jones et al. 2022, 24 astronautas en la ISS):
#     una escala visual analógica cuyas anclas escribe la fuente, «100 = very stressed; 0 = not
#     stressed». De las demás escalas del mismo instrumento (fatiga mental, somnolencia, cansancio,
#     agotamiento físico) lo leído no da ni el rango ni las anclas (van en una tabla suplementaria
#     que no se leyó): NO entran, y se dice en `data/instruments_read.json`.
#   * La cohesión del equipo del cuestionario de fin de día de Standard Measures (Hardy et al.
#     2025): tres afirmaciones, cada una valorada de 1 a 7 («a scale from 1 to 7»). Una por
#     indicador, con la afirmación tal como la escribe la fuente: lo leído no dice cómo se combinan
#     las tres en un valor, y EMMA no inventa el agregado. Las anclas del 1 y del 7 no se leyeron.
#
# Buscado y no adoptado: la escala de somnolencia de Karolinska y la de fatiga de Samn-Perelli,
# que el informe de evidencia del riesgo de sueño (HRP, 2016) nombra como «single item ratings of
# self-assessed sleepiness» sin sus puntos ni sus anclas; y la Perceived Stress Scale, que sí tiene
# código LOINC (106860-0) pero ninguna fuente leída dice que NASA la pase en vuelo.
#
# Todos con código propio: lo buscado en LOINC va arriba, junto a `NO_LOINC_AVAILABLE`. Categoría
# FHIR «survey» («Assessment tool/survey instrument observations»): una batería de pruebas en un
# ordenador y dos cuestionarios, no un examen físico ni un laboratorio.
# --------------------------------------------------------------------------- #

BEHAVIORAL_INSTRUMENTS_DECIDED_ON = "2026-10-31"
# Medias de tiempos de respuesta: un límite de plausibilidad de EMMA, sin fuente (un minuto).
_RESPONSE_TIME_MAX_MS = 60_000


@dataclass(frozen=True)
class CognitionTest:
    """Una prueba de la batería Cognition, con lo que la fuente publica de ella.

    `accuracy` dice qué mide la segunda puntuación de la prueba, con las palabras de Dev et al.
    2024: `proportion-correct` (las cinco con «proportion correct to total stimuli»), `proportion`
    (el F2B y el LOT, una proporción calculada de otra forma), `risk` (la BART) o `None` (la MPT,
    sin puntuación de precisión).
    """

    abbrev: str  # la sigla de la fuente, en minúsculas para la clave
    sigla: str  # la sigla tal como la escribe la fuente
    name: str  # el nombre de la prueba tal como lo escribe Dev et al. 2024
    accuracy: str | None


COGNITION_TESTS: tuple[CognitionTest, ...] = (
    CognitionTest("mpt", "MPT", "Motor Praxis Task", None),
    CognitionTest("volt", "VOLT", "Visual Object Learning Task", "proportion-correct"),
    CognitionTest("f2b", "F2B", "Fractal 2-Back", "proportion"),
    CognitionTest("am", "AM", "Abstract Matching", "proportion-correct"),
    CognitionTest("lot", "LOT", "Line Orientation Task", "proportion"),
    CognitionTest("ert", "ERT", "Emotion Recognition Task", "proportion-correct"),
    CognitionTest("mrt", "MRT", "Matrix Reasoning Task", "proportion-correct"),
    CognitionTest("dsst", "DSST", "Digit Symbol Substitution Task", "proportion-correct"),
    CognitionTest("bart", "BART", "Balloon Analog Risk Test", "risk"),
)

_ACCURACY_DISPLAY = {
    "proportion-correct": "accuracy, proportion correct to total stimuli",
    "proportion": "accuracy score, proportion",
    "risk": "risk score, proportion of maximum pumps (0 to 1)",
}


def _cognition_speed(test: CognitionTest) -> VitalCode:
    """La velocidad de una prueba: la media de los tiempos de respuesta, en ms. Preocupa la alta
    (más lento). Un tiempo medio de cero no es un dato: es un aparato mal leído."""
    key = f"cognition-{test.abbrev}-speed"
    return _c(
        key=key, code=key,
        display=f"Cognition test battery, {test.name} ({test.sigla}), speed: average response time",
        unit="ms", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL, concerning="high",
        physical_min=1, physical_max=_RESPONSE_TIME_MAX_MS,
        category=ObservationCategory.SURVEY,
    )


def _cognition_accuracy(test: CognitionTest) -> VitalCode:
    """La precisión (o, en la BART, el riesgo) de una prueba: una proporción de 0 a 1, adimensional
    («1»). Preocupa la baja; en la BART ninguna dirección es «buena»."""
    assert test.accuracy is not None
    measure = "risk" if test.accuracy == "risk" else "accuracy"
    key = f"cognition-{test.abbrev}-{measure}"
    return _c(
        key=key, code=key,
        display=(
            f"Cognition test battery, {test.name} ({test.sigla}), "
            f"{_ACCURACY_DISPLAY[test.accuracy]}"
        ),
        unit="1", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL,
        concerning="both" if measure == "risk" else "low",
        physical_min=0, physical_max=1,
        category=ObservationCategory.SURVEY,
    )


COGNITION_CODES: tuple[VitalCode, ...] = tuple(
    code
    for test in COGNITION_TESTS
    for code in (
        (_cognition_speed(test), _cognition_accuracy(test))
        if test.accuracy is not None
        else (_cognition_speed(test),)
    )
)
COGNITION_KEYS = frozenset(code.key for code in COGNITION_CODES)

# El estrés del Reaction Self Test: la escala visual analógica con las anclas que escribe la fuente
# (Jones et al. 2022, pie de la figura 1). El rango de 0 a 100 es el de esas anclas.
STRESS_RATING_VAS = _c(
    key="stress-rating-vas", code="stress-rating-vas",
    display=(
        "Self-reported stress, visual analog scale of the Reaction Self Test "
        "(0 = not stressed, 100 = very stressed)"
    ),
    unit="{score}", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL, concerning="high",
    physical_min=0, physical_max=100,
    category=ObservationCategory.SURVEY,
)

# Las tres afirmaciones de cohesión del cuestionario de fin de día de Standard Measures (Hardy et
# al. 2025, Tabla 3), tal como las escribe la fuente, cada una valorada de 1 a 7. Preocupa la baja
# (menos acuerdo con una afirmación de cohesión).
_TEAM_COHESION_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("team-cohesion-cared", "Our team members cared about each other"),
    ("team-cohesion-task-focus", "Our team was unified in its task focus"),
    ("team-cohesion-shared-purpose", "Shared sense of purpose and commitment"),
)


def _team_cohesion(key: str, statement: str) -> VitalCode:
    return _c(
        key=key, code=key,
        display=(
            "End of day survey (Spaceflight Standard Measures), team cohesion, agreement 1 to 7: "
            f"“{statement}”"
        ),
        unit="{score}", system=CodeSystem.EMMA, domain=Domain.BEHAVIORAL, concerning="low",
        physical_min=1, physical_max=7,
        category=ObservationCategory.SURVEY,
    )


TEAM_COHESION_ITEMS: tuple[VitalCode, ...] = tuple(
    _team_cohesion(key, statement) for key, statement in _TEAM_COHESION_STATEMENTS
)
TEAM_COHESION_KEYS = frozenset(code.key for code in TEAM_COHESION_ITEMS)
# La afirmación de cada indicador de cohesión, para quien la enseña o la comprueba.
TEAM_COHESION_STATEMENT: dict[str, str] = dict(_TEAM_COHESION_STATEMENTS)

BEHAVIORAL_INSTRUMENT_CODES: tuple[VitalCode, ...] = (
    *COGNITION_CODES, STRESS_RATING_VAS, *TEAM_COHESION_ITEMS,
)

# Nutrientes ingeridos al día, descriptivos (decisión del plan de la decimonovena ronda,
# 2026-10-31)
#
# La base de conocimiento §5 pide registrar la «composición nutricional» y la «ingesta real», y
# los dominios renal y óseo citan el sodio, el calcio y la vitamina D de la dieta
# (`data/countermeasures.json`). EMMA tenía la energía diaria y nada de lo que la compone. Entran
# cuatro nutrientes como DESCRIPTIVOS, con las reglas de los demás: se firman y se enseñan, el
# estado no los lee, no se simulan y no cuentan en la huella. Sin rango ni límite, a propósito:
# [V1 4020] fija las necesidades «based on an individual's age, sex, body mass (kg), height (m),
# and appropriate activity factor», que EMMA no calcula, y la Tabla 7.1-2 de la Rev F del
# Volumen 2 solo escribe la vitamina D («25 µg (micrograms)» al día): se cita, no se evalúa. Los
# demás nutrientes van por los valores de referencia dietética del NIH ([V2 7100]), que no se han
# leído. El rango físico de los cuatro es un límite de plausibilidad de EMMA, sin fuente.
#
# LOINC leído en tx.fhir.org el 2026-10-31 (LOINC 2.83). La familia de la ingesta («intake») tiene
# códigos de 24 horas (TIME_ASPCT 24H), que es lo que EMMA registra; los de tasa puntual (Pt), como
# el 9052-2 de la energía, no sirven. Y cada nutriente tiene hasta tres variantes: sin método,
# «Estimated» y «Measured». EMMA no sabe si lo que le llega se pesó o se estimó —lo leído dice que
# NASA determina la ingesta con un cuestionario (Hardy et al., 2025) y que la valoración en órbita
# es dietética ([6038]), sin decir con qué instrumento nutriente a nutriente—, así que solo adopta
# el código SIN método, como con la LDH de las analíticas; declarar uno sería inventarlo.
#   * Calcio: 35264-1 «Calcium intake 24 hour», MRat (masa por tiempo), mg/(24.h). Sin método. La
#     misma medida en moles por tiempo es 9051-4 (SRat, mol/(24.h)), leída y descartada.
#   * Proteína: 9085-2 «Protein intake 24 hour», MRat, g/(24.h). Sin método.
#   * Sodio: el único de 24 horas sin método, 9092-8, es SUSTANCIA por tiempo (SRat, mol/(24.h));
#     los de masa (81011-9 estimada y 81012-7 medida, g/(24.h)) llevan método. EMMA lo registra
#     en masa por día como a los otros tres nutrientes (y como la única cifra de ingesta que la
#     norma escribe, en µg), así que va con código propio y lo buscado queda escrito
#     (`NO_LOINC_AVAILABLE`). Adoptar 9092-8 obligaría a quien envía a convertir a moles, y EMMA
#     no convierte.
#   * Vitamina D: solo existe con método (81929-2 estimada y 81930-0 medida, MRat, ug/(24.h)):
#     código propio, en µg al día, la unidad en que lo escribe la Tabla 7.1-2 («This field is only
#     expressed in metric units of measure»). No en unidades internacionales: convertir sería de
#     EMMA.
# Los dos propios llevan la unidad en la forma de la energía (`kcal/d`): mg/d y ug/d. Los dos
# LOINC, la de su ficha: mg/(24.h) y g/(24.h). Un registro de ingesta, como la energía: sin
# categoría FHIR (`NoCategory.NONE_FITS`), y con el coste de medir del registro de ingesta, que lo
# ofrece el diario.
# --------------------------------------------------------------------------- #

NUTRIENT_INTAKE_DECIDED_ON = "2026-10-31"
NUTRIENT_INTAKE_READ_ON = "2026-10-31"

NUTRIENT_INTAKE_LOINC: dict[str, LoincRead] = {
    "calcium-intake-daily": LoincRead(
        component="Calcium intake", property="MRat", system="^Patient", scale="Qn", method=None,
        example_ucum="mg/(24.h)", status="ACTIVE", version="2.83",
        read_on=NUTRIENT_INTAKE_READ_ON, url=_lookup_url("35264-1"),
    ),
    "protein-intake-daily": LoincRead(
        component="Protein intake", property="MRat", system="^Patient", scale="Qn", method=None,
        example_ucum="g/(24.h)", status="ACTIVE", version="2.83",
        read_on=NUTRIENT_INTAKE_READ_ON, url=_lookup_url("9085-2"),
    ),
}
DESCRIPTIVE_LOINC.update(NUTRIENT_INTAKE_LOINC)


def _intake(
    key: str, code: str, display: str, unit: str, system: CodeSystem, high: float
) -> VitalCode:
    return _c(
        key=key, code=code, display=display, unit=unit, system=system, domain=Domain.NUTRITION,
        concerning="low", physical_min=0, physical_max=high,
        # Un registro de lo que se come, como la energía y los líquidos: ninguna de las nueve
        # categorías FHIR lo describe.
        category=NoCategory.NONE_FITS,
    )


# Preocupa el extremo bajo en los cuatro: lo que la base de conocimiento teme es el déficit (la
# ingesta que cae con la fatiga de menú). Que al sodio y al calcio también les sobre (OCHMO-MTB-013,
# «Excess may cause kidney stones») se cita en las contramedidas, no se evalúa aquí: el estado no
# los lee.
SODIUM_INTAKE = _intake(
    "sodium-intake-daily", "sodium-intake-daily", "Sodium intake per day", "mg/d",
    CodeSystem.EMMA, 20000,
)
CALCIUM_INTAKE = _intake(
    "calcium-intake-daily", "35264-1", "Calcium intake 24 hour",
    NUTRIENT_INTAKE_LOINC["calcium-intake-daily"].example_ucum, CodeSystem.LOINC, 10000,
)
PROTEIN_INTAKE = _intake(
    "protein-intake-daily", "9085-2", "Protein intake 24 hour",
    NUTRIENT_INTAKE_LOINC["protein-intake-daily"].example_ucum, CodeSystem.LOINC, 1000,
)
VITAMIN_D_INTAKE = _intake(
    "vitamin-d-intake-daily", "vitamin-d-intake-daily", "Vitamin D intake per day", "ug/d",
    CodeSystem.EMMA, 1000,
)
NUTRIENT_INTAKES: tuple[VitalCode, ...] = (
    SODIUM_INTAKE, CALCIUM_INTAKE, PROTEIN_INTAKE, VITAMIN_D_INTAKE,
)

# --------------------------------------------------------------------------- #
# El ciclo menstrual y la anticoncepción, descriptivos (decisión del usuario, 2026-11-14, lote
# «ciclo», unidad A3)
#
# EMMA tenía estradiol, FSH y LH en el catálogo y nada del ciclo. El usuario pidió que contemplara
# las afecciones hormonales y menstruales: primero hay que poder REGISTRAR el ciclo y la
# anticoncepción, con lo que dan las fuentes de las que llegarán (Apple Health y Health Connect).
# Entran seis indicadores como DESCRIPTIVOS, con las reglas de los demás: se firman y se enseñan,
# el estado no los lee, no se simulan y no cuentan en la huella. Ninguna fuente leída da un umbral
# para una tripulación sana, y la línea base consciente de la fase es otra unidad (la B3), que
# leerá el inicio de la regla como dato, no como alerta.
#
# Las categorías son las de la documentación de HealthKit, leída el 2026-11-14 en
# developer.apple.com (`data/instruments_read.json`, bloque `measures`, cada una con su frase).
# Todo valor en EMMA es un número (`valueQuantity`): una categoría se guarda con un número que
# elige EMMA, y `numbering` lo dice, como en el cambio de visión. Lo que la fuente no ordena no
# entra en la escala: la cantidad de flujo «unspecified» y el test de ovulación «indeterminate» no
# son un punto entre otros dos: no tienen número, y una lectura con ellos no cabe en la escala.
#
# CÓDIGOS (invariantes 1 y 2). Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83), cada candidato
# leído en su ficha con sus partes resueltas a su nombre:
#   * «Menses finding» (32400-4: Find, ^Patient, escala Nom, Reported, sin lista de respuestas) y
#     «Menstrual status» (3146-8 Type/Nom/Stated; 8678-5 Find/Nom/Reported): hallazgos NOMINALES.
#     Guardar en ellos un ordinal propio de cantidad de flujo cambiaría la escala del código.
#   * «Last menstrual period start date» (8665-2): una FECHA ({date}), no una marca en el momento
#     del inicio; EMMA guarda números y no fechas como valor.
#   * Sangrado intermenstrual: solo «I have vaginal bleeding or spotting in the past 7 days
#     [FACIT]» (70381-9: Ord, 7D, lista «Not at all…Very much»), una pregunta de otro cuestionario
#     sobre siete días, no un registro puntual.
#   * Test de ovulación: los códigos de lutropina en orina son cantidades (15079-7 Units/volume,
#     2580-9 Moles/volume) o una orden de laboratorio en prueba (111244-0, TRIAL); ninguno es el
#     resultado de un test casero por categorías. «ovulation» solo da fechas (11976-8) y PhenX.
#   * Anticoncepción: «Birth control method - Reported» (8659-5: Type, Nom, lista LL353-4
#     «Condom, Oral contraceptive pill, Injectable/implantable hormone, Diaphragm/cervical cap,
#     Intrauterine device, Vasectomy/tubal ligation/hysterectomy»). Es nominal y con SU lista, que
#     no es la de HealthKit (junta el implante con el inyectable, no tiene anillo ni parche).
#     Adoptarlo obligaría a usar exactamente esa lista como código de respuesta, no un número de
#     EMMA.
#   * Temperatura basal: no hay código «basal». El único que casa en propiedad es «Body
#     temperature» (8310-5: Temp, Pt, ^Patient, Qn, Cel), que ya es el de `body-temperature`, que el
#     estado SÍ evalúa. Codificar con él la basal juntaría dos series tomadas en condiciones
#     distintas (al despertar, en reposo) en la línea base de la temperatura. Código propio, en
#     °C (Cel): la unidad de la propiedad Temp, la misma que tendría 8310-5 (invariante 2).
#
# DOMINIO. EMMA no tiene dominio reproductivo, y añadirlo cambiaría la lista de dominios que
# puntúa el estado (un dominio sin ningún indicador evaluado), su dibujo, su RIDGE y la consola,
# por seis indicadores que el estado no lee. Van al genitourinario, el único que nombra el aparato
# genital: agruparlos ahí dice dónde se enseñan, no que el dominio los evalúe
# (`evaluated_by_domain`).
# El estradiol, la FSH y la LH siguen en el óseo, por su relación con la masa ósea.
#
# CATEGORÍA FHIR. Ninguna de las nueve describe un diario del ciclo ni el resultado de un test
# casero leído por quien lo usa (no es «laboratory»: no se envía muestra a un laboratorio), y la
# temperatura basal con código propio no puede ir como «vital-signs», que en FHIR R4 obliga al
# perfil de signos vitales y a su código LOINC: las seis van sin categoría (`NoCategory`).
#
# Un anticonceptivo como existencias de a bordo no necesita nada de esto: cabe en el inventario
# firmado (`core/inventory.py`, categoría `medications`). Este indicador registra el uso declarado.
# --------------------------------------------------------------------------- #

CYCLE_DECIDED_ON = "2026-11-14"


def _cycle_record(
    key: str, display: str, high: float, concerning: str = "both", low: float = 0
) -> VitalCode:
    return _c(
        key=key, code=key, display=display, unit="{score}", system=CodeSystem.EMMA,
        domain=Domain.GENITOURINARY, concerning=concerning, physical_min=low, physical_max=high,
        category=NoCategory.NONE_FITS,
    )


# Cantidad de flujo: 0 ninguno, 1 escaso, 2 moderado, 3 abundante (las palabras de HealthKit).
MENSTRUAL_FLOW = _cycle_record(
    "menstrual-flow",
    "Menstrual flow amount, HealthKit categories (none, light, medium, heavy)", 3,
)
# El inicio de un ciclo: 1 la muestra marca el inicio, 0 no (HKMetadataKeyMenstrualCycleStart).
MENSTRUATION_START = _cycle_record(
    "menstruation-start", "Start of a menstrual cycle (HealthKit menstrual cycle start flag)", 1,
)
# Sangrado fuera de la regla («spotting»): 1 registrado; 0, declarado sin él.
INTERMENSTRUAL_BLEEDING = _cycle_record(
    "intermenstrual-bleeding",
    "Intermenstrual bleeding (spotting outside the menstruation period), recorded or not", 1,
    concerning="high",
)
# Test casero de ovulación: 0 negativo, 1 ascenso de estrógenos, 2 ascenso de LH.
OVULATION_TEST = _cycle_record(
    "ovulation-test",
    "Ovulation home test result, HealthKit categories (negative, estrogen surge, luteinizing "
    "hormone surge)", 2,
)
# Anticonceptivo en uso: siete tipos de HealthKit, del 1 al 7. Es NOMINAL: el número es un rótulo,
# no un orden ni una cantidad, y se dice (`numbering`).
CONTRACEPTIVE_IN_USE = _cycle_record(
    "contraceptive-in-use",
    "Contraceptive in use, HealthKit contraceptive types (nominal, numbered by EMMA)", 7, low=1,
)
# Temperatura basal: la del cuerpo en reposo, al despertar. El intervalo de 20 a 45 °C es el
# límite de plausibilidad de `body-temperature`, sin fuente: no es un rango clínico y no evalúa.
BASAL_BODY_TEMPERATURE = _c(
    key="basal-body-temperature", code="basal-body-temperature",
    display="Basal body temperature (at rest, immediately after waking)",
    unit="Cel", system=CodeSystem.EMMA, domain=Domain.GENITOURINARY, concerning="both",
    physical_min=20, physical_max=45,
    category=NoCategory.NONE_FITS,
)
CYCLE_RECORDS: tuple[VitalCode, ...] = (
    MENSTRUAL_FLOW, MENSTRUATION_START, INTERMENSTRUAL_BLEEDING, OVULATION_TEST,
    CONTRACEPTIVE_IN_USE, BASAL_BODY_TEMPERATURE,
)
CYCLE_KEYS = frozenset(code.key for code in CYCLE_RECORDS)

# --------------------------------------------------------------------------- #
# Estado reproductivo, terapia hormonal de la menopausia y síntomas vasomotores, descriptivos
# (decisión del usuario, 2026-11-15, lote «ciclo», unidad C2)
#
# Ellande amplió el lote a la menopausia. Hay un motivo técnico además del clínico: la línea base
# consciente de la fase (unidad B3) solo tiene sentido si hay un ciclo regular que seguir, y NO
# debe aplicarse a quien no lo tiene —supresión menstrual o anticoncepción continua (lo habitual
# en misiones largas, Jain y Wotring 2016), perimenopausia, posmenopausia—. Para saberlo hace falta
# un dato declarado: `reproductive-status`. Es lo que B3 leerá para decidir si hay ciclo que
# ajustar, y solo el 1 («ciclo menstrual regular») lo dice. No es el sexo declarado (`crew-sex`,
# que vive en `api/`): es un autoinforme del estado del ciclo, con su fecha, que cambia con la vida
# reproductiva y que el propio tripulante puede no tener. Nada de `ingest/` lee el sexo
# (`test_no_rule_of_emma_reads_sex_or_age`).
#
# Entran cuatro indicadores DESCRIPTIVOS, con las reglas de los demás: se firman y se enseñan, el
# estado no los lee, no se simulan y no cuentan en la huella. Ninguno avisa ni sugiere nada: la
# terapia hormonal se registra como uso declarado, no se propone (invariante 7).
#
# ESCALAS. Las palabras salen de lo leído el 2026-11-15 (`data/instruments_read.json`):
#   * `reproductive-status` es NOMINAL y su lista es de EMMA, porque ninguna fuente leída junta
#     los seis casos que B3 necesita distinguir. Las fases de la vida reproductiva son las de
#     STRAW+10 (Harlow et al. 2012: reproductiva, transición menopáusica, posmenopausia), la
#     referencia clínica de esos estadios; pero STRAW+10 se define con el patrón de sangrado y no
#     da categoría para quien no sangra por la anticoncepción continua (esa sale de Jain y Wotring
#     2016) ni para quien no puede estadificarse por el sangrado (la histerectomía, que STRAW+10
#     nombra). HealthKit tiene desde iOS 27 un estado menopáusico con tres valores (menopause,
#     perimenopause, none): los dos primeros caen en el 5 y el 4; «none» no dice cuál de los otros
#     cuatro es, y no tiene número.
#   * `menopausal-hormone-therapy`: 1 en uso, 0 declarado sin ella. MedlinePlus define la terapia
#     («Types of hormone therapy»); qué hormonas, por qué vía y con qué pauta no se guardan aquí.
#     No es `contraceptive-in-use` (A3): una anticoncepción hormonal no es terapia de la menopausia.
#   * `hot-flashes` y `night-sweats`: la gravedad de HealthKit (HKCategoryValueSeverity): 0 no
#     presente, 1 leve, 2 moderado, 3 grave; «unspecified» no es un punto de la escala y no tiene
#     número, como la cantidad de flujo sin especificar de A3.
# Health Connect no tiene registro de ninguno de los cuatro (lista de clases leída el 2026-11-15).
#
# CÓDIGOS (invariantes 1 y 2). Buscado el 2026-11-15 en tx.fhir.org (LOINC 2.83), cada candidato
# leído en su ficha con sus partes resueltas a su nombre:
#   * Estado: no hay «menopausal status». «Menstrual status» (3146-8 Type/Nom; 8678-5
#     Find/Pt/Nom/Reported) es nominal y sin lista de respuestas: pide un valor codificado, y los
#     significados serían igualmente de EMMA. «Age at menopause» (42802-9) es una edad (Qn) y
#     «Cause of menopause [PhenX]» (63891-6) otra pregunta; «premenopausal» y «postmenopausal»
#     (LP140231-4, LP140232-2) son partes de LOINC, no códigos de observación.
#   * Terapia hormonal: «Estrogen use» (98134-0: Find, Pt, Ord, lista LL5981-7 Yes/No/Don't
#     know) dice estrógeno, no terapia de la menopausia: lo cumple también un anticonceptivo
#     combinado y no un progestágeno solo. Las preguntas de PhenX y del California Teachers Study
#     (63873-4 «Have you ever taken estrogen…», lista LL1469-7; 64649-7, preparados sin receta, en
#     prueba) son otros instrumentos y otro periodo.
#   * Sofocos y sudores nocturnos: solo preguntas de cuestionarios. FACIT, «in the past 7 days»
#     (70376-9 y 70379-3: Find, 7D, Ord, lista LL5215-0 «Not at all…Very much»); PHQ «hot flashes
#     or chills» (69710-2, sí/no, y junta los escalofríos); «Night sweats [HIV-SSC]» (28392-9).
#     Otro instrumento, otro periodo u otra escala: no la gravedad de HealthKit de una muestra.
#
# DOMINIO Y CATEGORÍA FHIR: los del ciclo (A3), genitourinario y sin categoría, por el mismo
# motivo. Los síntomas no son «survey»: no salen de un cuestionario con sus preguntas.
#
# Un estrógeno o un progestágeno como existencias de a bordo no va aquí: cabe en el inventario
# firmado (`core/inventory.py`, categoría `medications`). Este indicador registra el uso declarado.
# --------------------------------------------------------------------------- #

REPRODUCTIVE_STATUS_DECIDED_ON = "2026-11-15"

# Los cuatro se construyen con `_cycle_record` (A3) a propósito: comparten con los registros del
# ciclo unidad, sistema, dominio y categoría FHIR, y por el mismo motivo. Si un día esa ayuda cambia
# algo solo del ciclo, estos cuatro necesitan la suya.

# Estado reproductivo declarado, NOMINAL (el número es un rótulo): 1 ciclo menstrual regular, 2
# ciclo irregular, 3 sin regla por supresión menstrual o anticoncepción continua, 4
# perimenopausia, 5 posmenopausia, 6 no aplica (no hay sangrado que seguir por otro motivo).
REPRODUCTIVE_STATUS = _cycle_record(
    "reproductive-status",
    "Declared reproductive status (nominal, categories by EMMA from STRAW+10, HealthKit and "
    "menstrual suppression in astronauts)", 6, low=1,
)
# Terapia hormonal de la menopausia en uso: 1 sí, 0 declarado sin ella.
MENOPAUSAL_HORMONE_THERAPY = _cycle_record(
    "menopausal-hormone-therapy", "Menopausal hormone therapy in use, declared (no or yes)", 1,
)
# Sofocos y sudores nocturnos: la gravedad de HealthKit, de 0 (no presente) a 3 (grave).
HOT_FLASHES = _cycle_record(
    "hot-flashes",
    "Hot flashes severity, HealthKit symptom categories (not present, mild, moderate, severe)", 3,
    concerning="high",
)
NIGHT_SWEATS = _cycle_record(
    "night-sweats",
    "Night sweats severity, HealthKit symptom categories (not present, mild, moderate, severe)", 3,
    concerning="high",
)
REPRODUCTIVE_RECORDS: tuple[VitalCode, ...] = (
    REPRODUCTIVE_STATUS, MENOPAUSAL_HORMONE_THERAPY, HOT_FLASHES, NIGHT_SWEATS,
)
REPRODUCTIVE_KEYS = frozenset(code.key for code in REPRODUCTIVE_RECORDS)
# El único valor de `reproductive-status` que dice que hay un ciclo regular que seguir. Lo leerá
# la puerta de la línea base consciente de la fase (B3); aquí no decide nada.
REGULAR_CYCLE_STATUS = 1


DESCRIPTIVE_ONLY = (
    frozenset(
        code.key
        for code in (VISION_CHANGE, NASA_TLX, VO2_PEAK, GRIP_RIGHT, GRIP_LEFT, VITAMIN_D_25OH)
    )
    | frozenset({GLUCOSE_CAPILLARY.key})
    | frozenset(code.key for code in RENAL_URINE_CHEMISTRY)
    | DENSITOMETRY_KEYS
    | frozenset(code.key for code in SENSORIMOTOR_MUSCLE)
    | frozenset(code.key for code in BEHAVIORAL_INSTRUMENT_CODES)
    | frozenset(code.key for code in NUTRIENT_INTAKES)
    | CYCLE_KEYS
    | REPRODUCTIVE_KEYS
)
# Qué día decidió el usuario que cada uno entrara como descriptivo. Una tabla y no una regla: un
# descriptivo nuevo declara su fecha o falla la prueba (`test_descriptive_indicators.py`).
DESCRIPTIVE_DECISIONS: dict[str, str] = {
    VISION_CHANGE.key: DESCRIPTIVE_DECIDED_ON,
    NASA_TLX.key: DESCRIPTIVE_DECIDED_ON,
    VO2_PEAK.key: DESCRIPTIVE_DECIDED_ON,
    GRIP_RIGHT.key: DESCRIPTIVE_DECIDED_ON,
    GRIP_LEFT.key: DESCRIPTIVE_DECIDED_ON,
    VITAMIN_D_25OH.key: VITAMIN_D_DECIDED_ON,
    GLUCOSE_CAPILLARY.key: GLUCOSE_CAPILLARY_DECIDED_ON,
    **{code.key: RENAL_URINE_DECIDED_ON for code in RENAL_URINE_CHEMISTRY},
    BMD_DXA_LUMBAR_SPINE.key: DENSITOMETRY_DECIDED_ON,
    BMD_DXA_HIP.key: DENSITOMETRY_DECIDED_ON,
    **{code.key: SENSORIMOTOR_MUSCLE_DECIDED_ON for code in SENSORIMOTOR_MUSCLE},
    **{code.key: BEHAVIORAL_INSTRUMENTS_DECIDED_ON for code in BEHAVIORAL_INSTRUMENT_CODES},
    **{code.key: NUTRIENT_INTAKE_DECIDED_ON for code in NUTRIENT_INTAKES},
    **{code.key: CYCLE_DECIDED_ON for code in CYCLE_RECORDS},
    **{code.key: REPRODUCTIVE_STATUS_DECIDED_ON for code in REPRODUCTIVE_RECORDS},
}

# --------------------------------------------------------------------------- #
# Analíticas escaneadas (app/reports/labs.py, con `biomarcadores.py` de Polaris)
#
# Los analitos que lee Polaris de un informe de laboratorio, con el código verificado en su
# ficha oficial (tx.fhir.org, LOINC 2.82, 2026-10-01: `app/data/lab_loinc.json`, con la URL de
# cada consulta) y la unidad de su PROPIEDAD (invariante 2). Notas de esa verificación:
#   * LDH 2532-0 está DISCOURAGED en LOINC 2.82 (prefiere los de método, 14804-9/14805-6). Los
#     informes no dicen el método: se queda el genérico en vez de inventar uno.
#   * Calcio y magnesio en mg/dL (Mass/volume, MCnc). Si el informe trae mmol/L la lectura no
#     se confirma sin corregir: la unidad cambiaría de propiedad (SCnc, otros códigos).
#   * Sodio, potasio y cloro en mmol/L (SCnc): para iones monovalentes mEq/L = mmol/L.
#   * La urea es urea (3091-6), no nitrógeno ureico (BUN, 3094-0): es lo que informan.
#   * Los marcadores tumorales en "UI/mL" son unidades arbitrarias ([arb'U]/mL, ACnc).
#   * bun-creatinine-ratio (3097-3) es un cociente derivado, no una medida del laboratorio.
#
# SIN rango de referencia ni límite crítico, a propósito: el rango que vale es el que imprime
# el propio informe (viaja con la lectura). Sin rango ni crítico, un indicador no alerta sin
# base personal (ver `critical_low`): no se inventa un umbral para rellenar.
#
# Dominio: los de EMMA no tienen "hematología" ni "bioquímica", y se asigna el riesgo del HRP
# más cercano, sin que eso diga nada clínico más allá de dónde se agrupa:
#   * Serie blanca, sus porcentajes, el NLR y la PCR -> inmune (como los recuentos que ya hay).
#   * Serie roja y plaquetas -> cardiovascular: la anemia del vuelo va ligada al
#     desplazamiento de fluidos y a la hemólisis en microgravedad (riesgo de gravedad).
#   * Función renal y electrolitos -> genitourinario (riesgo renal y de cálculos del HRP).
#   * Calcio, fósforo y magnesio -> óseo (la pérdida ósea en vuelo los mueve); estradiol, FSH
#     y LH también, por su relación con la masa ósea.
#   * Glucosa, proteínas, perfil hepático, LDH y tiroides -> nutrición (estado metabólico).
#   * Marcadores tumorales -> radiación: el riesgo de cáncer del HRP es el de la radiación. Son
#     de seguimiento, no de cribado; EMMA no los interpreta.
# --------------------------------------------------------------------------- #


def _lab(
    key: str, code: str, display: str, unit: str, system: CodeSystem, domain: Domain
) -> VitalCode:
    return _c(
        key=key, code=code, display=display, unit=unit, system=system, domain=domain,
        concerning="both", physical_min=0,
    )


NEUTROPHILS_PCT = _lab(
    "neutrophils-percent", "770-8",
    "Neutrophils/Leukocytes in Blood by Automated count",
    "%", CodeSystem.LOINC, Domain.IMMUNE,
)
LYMPHOCYTES_PCT = _lab(
    "lymphocytes-percent", "736-9",
    "Lymphocytes/Leukocytes in Blood by Automated count",
    "%", CodeSystem.LOINC, Domain.IMMUNE,
)
NLR = _lab(
    "neutrophil-lymphocyte-ratio", "neutrophil-lymphocyte-ratio",
    "Neutrophil/lymphocyte ratio in Blood",
    "1", CodeSystem.EMMA, Domain.IMMUNE,
)
CRP = _lab(
    "c-reactive-protein", "1988-5",
    "C reactive protein [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.IMMUNE,
)
ERYTHROCYTES = _lab(
    "erythrocytes", "789-8",
    "Erythrocytes [#/volume] in Blood by Automated count",
    "10*6/uL", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
HEMOGLOBIN = _lab(
    "hemoglobin", "718-7",
    "Hemoglobin [Mass/volume] in Blood",
    "g/dL", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
HEMATOCRIT = _lab(
    "hematocrit", "4544-3",
    "Hematocrit [Volume Fraction] of Blood by Automated count",
    "%", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
MCV = _lab(
    "mcv", "787-2",
    "MCV [Entitic mean volume] in Red Blood Cells by Automated count",
    "fL", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
MCH = _lab(
    "mch", "785-6",
    "MCH [Entitic mass] by Automated count",
    "pg", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
MCHC = _lab(
    "mchc", "786-4",
    "MCHC [Entitic Mass/volume] in Red Blood Cells by Automated count",
    "g/dL", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
PLATELETS = _lab(
    "platelets", "777-3",
    "Platelets [#/volume] in Blood by Automated count",
    "10*3/uL", CodeSystem.LOINC, Domain.CARDIOVASCULAR,
)
UREA = _lab(
    "urea", "3091-6",
    "Urea [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.GENITOURINARY,
)
CREATININE = _lab(
    "creatinine", "2160-0",
    "Creatinine [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.GENITOURINARY,
)
BUN_CREATININE = _lab(
    "bun-creatinine-ratio", "3097-3",
    "Urea nitrogen/Creatinine [Mass Ratio] in Serum or Plasma",
    "1", CodeSystem.LOINC, Domain.GENITOURINARY,
)
SODIUM = _lab(
    "sodium", "2951-2",
    "Sodium [Moles/volume] in Serum or Plasma",
    "mmol/L", CodeSystem.LOINC, Domain.GENITOURINARY,
)
POTASSIUM = _lab(
    "potassium", "2823-3",
    "Potassium [Moles/volume] in Serum or Plasma",
    "mmol/L", CodeSystem.LOINC, Domain.GENITOURINARY,
)
CHLORIDE = _lab(
    "chloride", "2075-0",
    "Chloride [Moles/volume] in Serum or Plasma",
    "mmol/L", CodeSystem.LOINC, Domain.GENITOURINARY,
)
CALCIUM = _lab(
    "calcium", "17861-6",
    "Calcium [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.BONE,
)
PHOSPHATE = _lab(
    "phosphate", "2777-1",
    "Phosphate [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.BONE,
)
MAGNESIUM = _lab(
    "magnesium", "19123-9",
    "Magnesium [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.BONE,
)
ESTRADIOL = _lab(
    "estradiol", "2243-4",
    "Estradiol (E2) [Mass/volume] in Serum or Plasma",
    "pg/mL", CodeSystem.LOINC, Domain.BONE,
)
FSH = _lab(
    "fsh", "15067-2",
    "Follitropin [Units/volume] in Serum or Plasma",
    "m[IU]/mL", CodeSystem.LOINC, Domain.BONE,
)
LH = _lab(
    "lh", "10501-5",
    "Lutropin [Units/volume] in Serum or Plasma",
    "m[IU]/mL", CodeSystem.LOINC, Domain.BONE,
)
GLUCOSE = _lab(
    "glucose", "2345-7",
    "Glucose [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
TOTAL_PROTEIN = _lab(
    "total-protein", "2885-2",
    "Protein [Mass/volume] in Serum or Plasma",
    "g/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
ALBUMIN = _lab(
    "albumin", "1751-7",
    "Albumin [Mass/volume] in Serum or Plasma",
    "g/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
AST = _lab(
    "ast", "1920-8",
    "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
    "U/L", CodeSystem.LOINC, Domain.NUTRITION,
)
ALT = _lab(
    "alt", "1742-6",
    "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
    "U/L", CodeSystem.LOINC, Domain.NUTRITION,
)
GGT = _lab(
    "ggt", "2324-2",
    "Gamma glutamyl transferase [Enzymatic activity/volume] in Serum or Plasma",
    "U/L", CodeSystem.LOINC, Domain.NUTRITION,
)
ALKALINE_PHOSPHATASE = _lab(
    "alkaline-phosphatase", "6768-6",
    "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma",
    "U/L", CodeSystem.LOINC, Domain.NUTRITION,
)
BILIRUBIN_TOTAL = _lab(
    "bilirubin-total", "1975-2",
    "Bilirubin.total [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
BILIRUBIN_DIRECT = _lab(
    "bilirubin-direct", "1968-7",
    "Bilirubin.direct [Mass/volume] in Serum or Plasma",
    "mg/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
LDH = _lab(
    "ldh", "2532-0",
    "Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma",
    "U/L", CodeSystem.LOINC, Domain.NUTRITION,
)
TSH = _lab(
    "tsh", "3016-3",
    "Thyrotropin [Units/volume] in Serum or Plasma",
    "u[IU]/mL", CodeSystem.LOINC, Domain.NUTRITION,
)
FREE_T4 = _lab(
    "free-t4", "3024-7",
    "Thyroxine (T4) free [Mass/volume] in Serum or Plasma",
    "ng/dL", CodeSystem.LOINC, Domain.NUTRITION,
)
CA_15_3 = _lab(
    "ca-15-3", "6875-9",
    "Cancer Ag 15-3 [Units/volume] in Serum or Plasma",
    "[arb'U]/mL", CodeSystem.LOINC, Domain.RADIATION,
)
CEA = _lab(
    "cea", "2039-6",
    "Carcinoembryonic Ag [Mass/volume] in Serum or Plasma",
    "ng/mL", CodeSystem.LOINC, Domain.RADIATION,
)
CA_125 = _lab(
    "ca-125", "10334-1",
    "Cancer Ag 125 [Units/volume] in Serum or Plasma",
    "[arb'U]/mL", CodeSystem.LOINC, Domain.RADIATION,
)
CA_19_9 = _lab(
    "ca-19-9", "24108-3",
    "Cancer Ag 19-9 [Units/volume] in Serum or Plasma",
    "[arb'U]/mL", CodeSystem.LOINC, Domain.RADIATION,
)
CA_27_29 = _lab(
    "ca-27-29", "17842-6",
    "Cancer Ag 27-29 [Units/volume] in Serum or Plasma",
    "[arb'U]/mL", CodeSystem.LOINC, Domain.RADIATION,
)
BETA2_MICROGLOBULIN = _lab(
    "beta2-microglobulin", "1952-1",
    "Beta-2-Microglobulin [Mass/volume] in Serum or Plasma",
    "mg/L", CodeSystem.LOINC, Domain.RADIATION,
)
CHROMOGRANIN_A = _lab(
    "chromogranin-a", "9811-1",
    "Chromogranin A [Mass/volume] in Serum or Plasma",
    "ug/L", CodeSystem.LOINC, Domain.RADIATION,
)
NSE = _lab(
    "neuron-specific-enolase", "15060-7",
    "Enolase.neuron specific [Mass/volume] in Serum or Plasma",
    "ng/mL", CodeSystem.LOINC, Domain.RADIATION,
)

# Indicadores que solo llegan de una analítica escaneada y confirmada por una persona
# (`app/reports/labs.py`): ni se simulan ni se aceptan por la ingesta genérica.
LAB_REPORT_ONLY = frozenset(code.key for code in (
    NEUTROPHILS_PCT,
    LYMPHOCYTES_PCT,
    NLR,
    CRP,
    ERYTHROCYTES,
    HEMOGLOBIN,
    HEMATOCRIT,
    MCV,
    MCH,
    MCHC,
    PLATELETS,
    UREA,
    CREATININE,
    BUN_CREATININE,
    SODIUM,
    POTASSIUM,
    CHLORIDE,
    CALCIUM,
    PHOSPHATE,
    MAGNESIUM,
    ESTRADIOL,
    FSH,
    LH,
    GLUCOSE,
    TOTAL_PROTEIN,
    ALBUMIN,
    AST,
    ALT,
    GGT,
    ALKALINE_PHOSPHATASE,
    BILIRUBIN_TOTAL,
    BILIRUBIN_DIRECT,
    LDH,
    TSH,
    FREE_T4,
    CA_15_3,
    CEA,
    CA_125,
    CA_19_9,
    CA_27_29,
    BETA2_MICROGLOBULIN,
    CHROMOGRANIN_A,
    NSE,
))

# Indicadores que solo llegan por autoinforme de la tripulacion: ni se simulan (seria
# inventar lo que alguien siente) ni se aceptan por la ingesta generica, porque cada
# lectura tiene que ir con el informe que la explica.
SELF_REPORTED_ONLY = frozenset({"pain-intensity"})

# Indicadores que solo se obtienen midiendo sobre una ecografia.
ULTRASOUND_MEASURES = frozenset(
    {"onsd-right", "onsd-left", "ijv-csa-right", "ijv-csa-left", "bladder-volume"}
)


CATALOG: dict[str, VitalCode] = {
    code.key: code
    for code in (
        HEART_RATE, RESPIRATORY_RATE, BODY_TEMPERATURE, OXYGEN_SATURATION,
        SYSTOLIC_BP, DIASTOLIC_BP, BODY_WEIGHT, HRV_SDNN, HRV_RMSSD, ORTHOSTATIC_DROP,
        PVT_MEAN_RT, PVT_LAPSES, SLEEP_DURATION, SLEEP_EFFICIENCY, CIRCADIAN_SHIFT,
        MOOD_VALENCE,
        ABSORBED_DOSE_RATE, CUMULATIVE_DOSE,
        EXERCISE_MINUTES, LOADING_IMPACTS, NTX_TELOPEPTIDE,
        SYMPTOM_BURDEN, CORTISOL_SALIVARY, LATENT_VIRUS_SHEDDING,
        ONSD_RIGHT, ONSD_LEFT, IJV_CSA_RIGHT, IJV_CSA_LEFT, BLADDER_VOLUME,
        LEUKOCYTES, LYMPHOCYTES, NEUTROPHILS,
        NEUTROPHILS_PCT,
        LYMPHOCYTES_PCT,
        NLR,
        CRP,
        ERYTHROCYTES,
        HEMOGLOBIN,
        HEMATOCRIT,
        MCV,
        MCH,
        MCHC,
        PLATELETS,
        UREA,
        CREATININE,
        BUN_CREATININE,
        SODIUM,
        POTASSIUM,
        CHLORIDE,
        CALCIUM,
        PHOSPHATE,
        MAGNESIUM,
        ESTRADIOL,
        FSH,
        LH,
        GLUCOSE,
        TOTAL_PROTEIN,
        ALBUMIN,
        AST,
        ALT,
        GGT,
        ALKALINE_PHOSPHATASE,
        BILIRUBIN_TOTAL,
        BILIRUBIN_DIRECT,
        LDH,
        TSH,
        FREE_T4,
        CA_15_3,
        CEA,
        CA_125,
        CA_19_9,
        CA_27_29,
        BETA2_MICROGLOBULIN,
        CHROMOGRANIN_A,
        NSE,
        PAIN_INTENSITY,
        FLUID_INTAKE, URINE_VOLUME, URINE_SPECIFIC_GRAVITY,
        ENERGY_INTAKE, FOOD_ACCEPTABILITY, APPETITE, FOOD_REJECTED,
        VISION_CHANGE, NASA_TLX, VO2_PEAK, GRIP_RIGHT, GRIP_LEFT, VITAMIN_D_25OH,
        GLUCOSE_CAPILLARY,
        *RENAL_URINE_CHEMISTRY,
        BMD_DXA_LUMBAR_SPINE, BMD_DXA_HIP,
        *SENSORIMOTOR_MUSCLE,
        *BEHAVIORAL_INSTRUMENT_CODES,
        *NUTRIENT_INTAKES,
        *CYCLE_RECORDS,
        *REPRODUCTIVE_RECORDS,
    )
}


def by_domain(domain: Domain) -> tuple[VitalCode, ...]:
    return tuple(code for code in CATALOG.values() if code.domain is domain)


def evaluated_by_domain(domain: Domain) -> tuple[VitalCode, ...]:
    """Los indicadores con que el estado evalúa un dominio: los del catálogo menos los descriptivos.

    Un indicador descriptivo se agrupa en un dominio para saber dónde enseñarlo, pero el estado
    no lo lee: listarlo entre lo que evalúa un riesgo, o como «sin lecturas» en el contexto de
    una alerta, diría que cuenta.
    """
    return tuple(code for code in by_domain(domain) if code.key not in DESCRIPTIVE_ONLY)


def get(key: str) -> VitalCode:
    try:
        return CATALOG[key]
    except KeyError:
        raise KeyError(f"indicador desconocido: {key!r}") from None
