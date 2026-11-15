"""Los indicadores descriptivos de un tripulante: qué son, de dónde sale su medida y qué consta.

POR QUÉ EXISTE
--------------
El usuario decidió (2026-10-15) que la salud conductual más allá del ánimo, los síntomas
visuales y la fuerza y la forma física entren como observaciones, sin entrar en el riesgo
(`codes.DESCRIPTIVE_ONLY`), el 2026-10-22 añadió la vitamina D 25-OH, el 2026-10-26 los ocho
analitos de la orina de 24 horas del riesgo de cálculos renales y las dos densitometrías, y el
2026-10-31 (decimonovena ronda) las dos pruebas sensoriomotoras y las dos medidas de músculo de
Standard Measures, las nueve pruebas de la batería Cognition, el estrés del Reaction Self Test y
las tres afirmaciones de cohesión del cuestionario de fin de día de Standard Measures, cada uno
con su instrumento leído, y el 2026-11-14 (lote «ciclo») los seis registros del ciclo menstrual y
la anticoncepción con las categorías de HealthKit, y el 2026-11-15 el estado reproductivo
declarado, la terapia hormonal de la menopausia, los sofocos y los sudores nocturnos. Firmarlas
en el ledger no basta:
el estado no las lee, así que ninguna pantalla las enseñaría, y las que no se anotan en el diario
(VO2 pico, prensión, vitamina D, la química de la orina) no tendrían dónde verse. Esta ruta las
sirve juntas, cada una con:

- su código y por qué es ese: la ficha LOINC leída, con su propiedad y su unidad de ejemplo, o
  lo que se buscó en LOINC antes de darle un código propio;
- lo leído de su medida (`instruments_read.measure`), con cada frase en su idioma;
- por dónde se registra (el diario o la ingesta de observaciones);
- lo que consta en el registro firmado, lo último primero.

Ruta de solo lectura: no escribe nada, no la lee el estado y no mueve ningún nivel, alerta,
puntuación ni recomendación (invariante 5). Tampoco evalúa: el 80 % de la norma se cita.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.analysis.data_quality import source_label
from app.api.diary import DIARY_SOURCE, NOT_RECORDED, diary_keys
from app.api.routes import StoreDep
from app.core import display
from app.evidence import instruments_read
from app.ingest.codes import (
    CATALOG,
    CODE_SYSTEM_DISPLAY,
    COGNITION_KEYS,
    DESCRIPTIVE_DECIDED_ON,
    DESCRIPTIVE_DECISIONS,
    DESCRIPTIVE_LOINC,
    DESCRIPTIVE_ONLY,
    MISSION_SPECIFIC,
    TEAM_COHESION_KEYS,
    VitalCode,
)
from app.ingest.cost import cost
from app.ingest.fhir import VitalObservation

descriptive_router = APIRouter(prefix="/indicators")

SCOPE = (
    "Indicadores descriptivos: se firman en el registro como cualquier lectura y se enseñan "
    "aquí, pero el estado no los lee. No mueven niveles, alertas ni puntuaciones, no se simulan "
    "y no se comparan con ningún umbral: lo que pide la norma se cita, no se evalúa."
)
SYSTEM_DISPLAY = CODE_SYSTEM_DISPLAY
# Lo que se buscó en LOINC para cada descriptivo con código propio, como se enseña.
LOINC_SEARCHED = {
    "vision-change": (
        "Buscado el 2026-10-16 en tx.fhir.org (LOINC 2.82): «vision change», «change in "
        "vision», «blurred vision», «vision questionnaire» y «visual disturbance». Solo "
        "aparecen una lista de respuestas y la descripción libre de un protocolo de PhenX: "
        "ningún código del cuestionario de visión en vuelo."
    ),
    "nasa-tlx-workload": (
        "Buscado el 2026-10-16 en tx.fhir.org (LOINC 2.82): «NASA task load», «TLX» y «task "
        "load», sin resultados; «workload» y «mental workload» solo dan los paneles de carga "
        "de trabajo de enfermería del NMMDS (77221-0 y 77226-9), que describen una unidad de "
        "hospital y no la carga que una persona percibe en una tarea."
    ),
    "urine-caox-supersaturation-24h": (
        "Buscado el 2026-10-26 en tx.fhir.org (LOINC 2.83): «supersaturation» solo da dos paneles "
        "sin valor (81232-1, de la orina de 24 horas, y 101929-8); «saturation» en orina da la "
        "fracción de saturación de la brushita (42673-4), del urato (42678-3), del urato sódico "
        "(43423-3) y del fosfato triple (53811-6), ninguna del oxalato cálcico. Del oxalato "
        "cálcico en orina de 24 horas solo hay una diferencia de energía (81623-1, en kJ/mol) y un "
        "índice (34736-9): son otras propiedades, y adoptarlas para el cociente cambiaría lo que "
        "dice la cifra."
    ),
    # Sensoriomotor y músculo (2026-10-31, LOINC 2.83 en tx.fhir.org).
    "tandem-walk-correct-steps": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «tandem» da «Tandem gait for 10 steps "
        "[PhenX]» (66045-6: una observación nominal en fase de prueba, con su lista de respuestas, "
        "no un porcentaje), «Gait and turn and tandem gait assessment» (93015-6) y el balanceo en "
        "postura tándem del NIH Toolbox (83179-2); «posturography», «sensory organization» y "
        "«stand test», nada; «balance», la duración en una postura del NIH Toolbox (91553-8) y "
        "la prueba de equilibrio de PhenX (66248-6, 66249-4), otros protocolos. Ninguno es el "
        "porcentaje de pasos correctos que puntúa NASA."
    ),
    "recovery-from-fall-time": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «stand test», «sensory organization» y "
        "«posturography», nada; «fall» y «balance» solo dan preguntas de cuestionario sobre caídas "
        "y mareo (PhenX, FACIT, PROMIS), el conjunto mínimo de datos y la duración en una postura "
        "del NIH Toolbox (91553-8), que es aguantar una postura, no llegar a ella. Ninguno es el "
        "tiempo desde la orden de levantarse hasta la postura estable."
    ),
    "dxa-lean-mass": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «lean» da «Lean body weight» (91557-9: "
        "masa, sin método, kg), su cálculo (88334-8), la estimación por inmersión (8342-8) y por "
        "pliegues (8343-6); ninguno es de DXA, y «lean body weight» no dice si incluye el mineral "
        "óseo, que la DXA separa de la masa magra: codificar así la cifra la cambiaría en unos "
        "kilos. «fat free» y «soft tissue mass», nada; «body composition», solo el protocolo de "
        "PhenX por DXA (63520-1, desaconsejado); «DXA», 67 códigos, todos de densidad ósea; «body "
        "fat», la masa grasa calculada (73708-0) y porcentajes."
    ),
    "imtp-peak-force": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «thigh pull», «peak force» y «force "
        "plate», nada; «isometric», una respuesta de ejercicio terapéutico (LA29117-1); «muscle "
        "strength», el protocolo de PhenX (62821-4, inactivo) y preguntas sobre debilidad "
        "muscular. Ninguno es la fuerza máxima de una tracción isométrica en una plataforma de "
        "fuerza."
    ),
    # Las nueve pruebas de la batería Cognition comparten lo buscado: se buscó cada una por su
    # nombre y ninguna tiene código.
    **dict.fromkeys(
        COGNITION_KEYS,
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83) por el nombre de cada prueba de la "
        "batería: «digit symbol», «emotion recognition», «matrix reasoning», «line orientation», "
        "«object learning», «risk taking» y «reaction time» no dan ningún código; «working "
        "memory» da la prueba de ordenación de listas del NIH Toolbox (84434-0 y sus "
        "puntuaciones) y un protocolo de PhenX (62776-0), que son otras pruebas, no el 2-Back de "
        "fractales. Ninguna prueba de la batería Cognition tiene código LOINC.",
    ),
    "stress-rating-vas": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «perceived stress» da la Perceived "
        "Stress Scale de Cohen (PSS-10: 106875-8 y su total 106860-0; PSS-14: 106904-6 y 106903-8) "
        "y la encuesta de estrés percibido del NIH Toolbox (91528-0 y su T-score 91527-2). Son "
        "otros instrumentos, cuestionarios de varias preguntas; ninguno es la escala visual "
        "analógica de estrés de 0 a 100 del Reaction Self Test, y adoptar su código para ella "
        "cambiaría lo que dice la cifra."
    ),
    **dict.fromkeys(
        TEAM_COHESION_KEYS,
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «cohesion» solo da la eficacia "
        "colectiva de un vecindario de PhenX (63026-9 y su medida); «team» da equipos "
        "asistenciales y notas de equipo clínico. Ningún código para las afirmaciones de cohesión "
        "del cuestionario de fin de día de Standard Measures.",
    ),
    "sodium-intake-daily": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «sodium intake». El único código de "
        "24 horas sin método, 9092-8 «Sodium intake 24 hour», es sustancia por tiempo (SRat, en "
        "moles al día); los dos de masa por tiempo, 81011-9 «Estimated» y 81012-7 «Measured» (en "
        "gramos al día), declaran un método que lo leído no fija: NASA determina la ingesta con "
        "un cuestionario y valora la dieta en órbita, sin decir si cada cifra se pesa o se "
        "estima. EMMA registra el sodio ingerido en masa por día, como los otros tres "
        "nutrientes, y no sabe cómo se obtuvo la cifra: adoptar 9092-8 cambiaría la unidad a "
        "moles y adoptar uno con método sería inventarlo."
    ),
    "vitamin-d-intake-daily": (
        "Buscado el 2026-10-31 en tx.fhir.org (LOINC 2.83): «vitamin D intake». Solo existen "
        "con método, 81929-2 «Estimated» y 81930-0 «Measured» (masa por tiempo, en microgramos al "
        "día); no hay uno sin método que adoptar sin inventar cómo se obtuvo la cifra. La unidad, "
        "microgramos al día, es la que escribe la Tabla 7.1-2 de NASA-STD-3001 Vol. 2 Rev F."
    ),
    # El ciclo menstrual y la anticoncepción (2026-11-14, LOINC 2.83 en tx.fhir.org).
    "menstrual-flow": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «menstrual», «menses», «menstrual "
        "flow», «menstruation» y «vaginal bleeding». Lo más cercano son hallazgos nominales: "
        "«Menses finding» (32400-4) y «Menstrual status» (3146-8 y 8678-5), sin lista de "
        "cantidades de flujo. Guardar en ellos una escala ordenada de 0 a 3 cambiaría la escala "
        "del código."
    ),
    "menstruation-start": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «menstrual» da la fecha de inicio de "
        "la última regla (8665-2), que es una fecha y no una marca en el momento del inicio, y el "
        "día del ciclo (107139-8), que es otro dato. Ningún código para la marca de inicio de un "
        "ciclo de una muestra."
    ),
    "intermenstrual-bleeding": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «intermenstrual», nada; «spotting» y "
        "«vaginal bleeding» solo dan preguntas del cuestionario FACIT sobre los últimos siete días "
        "(70381-9 y 70830-5), con su propia lista de respuestas: otro instrumento y otro periodo, "
        "no el registro de un manchado."
    ),
    "ovulation-test": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «ovulation» da la fecha de ovulación "
        "(11976-8) y protocolos de PhenX; «lutropin» en orina, cantidades medidas en laboratorio "
        "(15079-7, 2580-9, 25716-2) y una orden en fase de prueba (111244-0). Ninguno es el "
        "resultado por categorías de un test casero."
    ),
    "contraceptive-in-use": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «birth control» y «contracept». El más "
        "cercano, «Birth control method - Reported» (8659-5), es nominal y lleva su propia lista "
        "de respuestas (LL353-4: preservativo, píldora oral, hormona inyectable o implantable, "
        "diafragma, dispositivo intrauterino, vasectomía o ligadura), que no es la de HealthKit: "
        "junta el implante con el inyectable y no tiene anillo ni parche. Adoptarlo obligaría a "
        "codificar con esa lista, no con un número de EMMA."
    ),
    "basal-body-temperature": (
        "Buscado el 2026-11-14 en tx.fhir.org (LOINC 2.83): «basal» y «body temperature». No hay "
        "código de temperatura basal. «Body temperature» (8310-5: temperatura, Cel) casa en "
        "propiedad pero no dice la condición basal, y ya es el código de la temperatura corporal "
        "que el estado evalúa: codificar con él la basal juntaría dos series tomadas en "
        "condiciones distintas. Código propio, en °C, la unidad de esa misma propiedad."
    ),
    # El estado reproductivo, la terapia hormonal y los síntomas vasomotores (2026-11-15, LOINC
    # 2.83 en tx.fhir.org).
    "reproductive-status": (
        "Buscado el 2026-11-15 en tx.fhir.org (LOINC 2.83): «menopaus», «perimenopaus», "
        "«postmenopaus» y «menstrual status». No hay código de estado menopáusico ni de estadio "
        "reproductivo. «Menstrual status» (3146-8 y 8678-5) es nominal y sin lista de "
        "respuestas: pide un valor codificado, y lo que significara cada valor seguiría siendo "
        "de EMMA. «Age at menopause» (42802-9) es una edad y «Cause of menopause» (63891-6), "
        "otra pregunta de PhenX."
    ),
    "menopausal-hormone-therapy": (
        "Buscado el 2026-11-15 en tx.fhir.org (LOINC 2.83): «hormone therapy», «hormone "
        "replacement», «estrogen use» y «female hormone». El más cercano, «Estrogen use» "
        "(98134-0: ordinal, con su lista LL5981-7 sí, no, no sabe), dice estrógeno y no terapia "
        "de la menopausia: lo cumple también un anticonceptivo combinado, y no un progestágeno "
        "solo. Las preguntas de PhenX y del California Teachers Study (63873-4, 64649-7) son "
        "otros instrumentos y otro periodo («ever taken», preparados de venta libre)."
    ),
    "hot-flashes": (
        "Buscado el 2026-11-15 en tx.fhir.org (LOINC 2.83): «hot flash», «hot flush» y "
        "«vasomotor». Solo preguntas de cuestionarios: «I have hot flashes in the past 7 days» "
        "del FACIT (70376-9: siete días, lista LL5215-0 de «Not at all» a «Very much») y «Did "
        "you have hot flashes or chills» del PHQ (69710-2: sí o no, y junta los escalofríos). "
        "Otro instrumento y otro periodo, no la gravedad de una muestra de HealthKit."
    ),
    "night-sweats": (
        "Buscado el 2026-11-15 en tx.fhir.org (LOINC 2.83): «night sweat». Solo preguntas de "
        "cuestionarios: «I have night sweats in the past 7 days» del FACIT (70379-3: siete "
        "días, lista LL5215-0) y «Night sweats [HIV-SSC]» (28392-9), de una lista de síntomas "
        "del VIH con su propia escala. Otro instrumento y otro periodo, no la gravedad de una "
        "muestra de HealthKit."
    ),
}
NO_LOINC = "Se buscó un código LOINC y no existe uno adecuado."
DIARY_ROUTE = "/api/diary/entries"
INGEST_ROUTE = "/api/observations"
HOW_DIARY = (
    f"Se anota en el registro diario de la consola, que lo firma con la fuente "
    f"«{source_label(DIARY_SOURCE)}» y con quién lo anota."
)
HOW_INGEST = (
    "No se anota en el diario: entra por la ingesta de observaciones con la fuente del "
    "instrumento que lo mide, firmado en el registro como cualquier lectura."
)


def _code_basis(code: VitalCode) -> dict[str, Any]:
    """Por qué tiene ese código: la ficha LOINC leída, o lo que se buscó antes del propio."""
    read = DESCRIPTIVE_LOINC.get(code.key)
    if read is not None:
        method = f", método {read.method}" if read.method else ""
        return {
            "kind": "loinc",
            "text": (
                f"Código LOINC {code.code}, leído en su ficha el {read.read_on} (LOINC "
                f"{read.version}, {read.status}): propiedad {read.property}, sistema "
                f"{read.system}, escala {read.scale}{method}; unidad de ejemplo "
                f"{read.example_ucum}. EMMA lo registra en {code.unit}: la unidad sigue a la "
                f"propiedad."
            ),
            "loinc": {
                "component": read.component,
                "property": read.property,
                "system": read.system,
                "scale": read.scale,
                "method": read.method,
                "example_ucum": read.example_ucum,
                "status": read.status,
                "version": read.version,
                "read_on": read.read_on,
                "url": read.url,
            },
            "searched": None,
        }
    return {
        "kind": "own",
        "text": MISSION_SPECIFIC.get(code.key) or NO_LOINC,
        "loinc": None,
        "searched": LOINC_SEARCHED.get(code.key),
    }


def _how(key: str, diary: set[str]) -> dict[str, str]:
    if key in diary:
        return {"route": DIARY_ROUTE, "text": HOW_DIARY}
    return {"route": INGEST_ROUTE, "text": HOW_INGEST}


def _reading(item: VitalObservation) -> dict[str, Any]:
    return {
        "effective": item.effective.isoformat(),
        "value": item.value,
        "value_text": display.quantity(item.key, item.value, item.code.unit),
        "source": item.source,
        "source_display": source_label(item.source),
        "recorded_by": item.recorded_by,
        "recorded_by_display": item.recorded_by if item.recorded_by is not None else NOT_RECORDED,
        "observation_type": str(item.observation_type),
        "evidence_context": str(item.evidence),
    }


def _range_text(code: VitalCode) -> str:
    """El rango físico del catálogo con su unidad. Todo descriptivo declara los dos extremos."""
    decimals = display.decimals_for(code.key)
    low, high = code.physical_min, code.physical_max
    if low is None or high is None:
        return "sin rango físico declarado"
    return (
        f"de {display.number(low, decimals)} a {display.number(high, decimals)} "
        f"{display.unit(code.unit)}"
    ).strip()


def _summary(subject: str, total: int) -> str:
    if total == 0:
        return f"Sin lecturas de indicadores descriptivos en el registro de {subject}."
    return (
        f"{display.number(total, 0)} lecturas de indicadores descriptivos en el registro de "
        f"{subject}."
    )


def describe(
    subject: str, readings: list[VitalObservation], diary: set[str], limit: int
) -> dict[str, Any]:
    """Cada indicador descriptivo, en el orden del catálogo, con lo que consta de él."""
    by_key: dict[str, list[VitalObservation]] = {key: [] for key in DESCRIPTIVE_ONLY}
    for item in readings:
        if item.key in by_key:
            by_key[item.key].append(item)
    indicators: list[dict[str, Any]] = []
    total = 0
    for key, code in CATALOG.items():
        if key not in DESCRIPTIVE_ONLY:
            continue
        mine = sorted(by_key[key], key=lambda item: item.effective, reverse=True)
        measured_with = cost(key) or {}
        total += len(mine)
        indicators.append({
            "key": key,
            "display": code.display,
            "display_es": code.display_es,
            # El día en que el usuario decidió que entrara: no todos entraron a la vez.
            "decided_on": DESCRIPTIVE_DECISIONS[key],
            "domain": str(code.domain),
            "domain_display": code.domain.display,
            "unit": code.unit,
            "unit_display": display.unit(code.unit),
            "decimals": display.decimals_for(key),
            "range_text": _range_text(code),
            "system": str(code.system),
            "system_display": SYSTEM_DISPLAY[code.system],
            "code": code.code,
            "code_basis": _code_basis(code),
            "equipment": measured_with.get("equipment"),
            "how_recorded": _how(key, diary),
            "instrument": instruments_read.measure(key),
            "count": len(mine),
            "shown": min(limit, len(mine)),
            "readings": [_reading(reading) for reading in mine[:limit]],
        })
    return {
        "subject": subject,
        # La decisión que abrió el panel; cada indicador lleva la suya (`decided_on`).
        "decided_on": DESCRIPTIVE_DECIDED_ON,
        "scope": SCOPE,
        "statement": _summary(subject, total),
        "indicators": indicators,
    }


@descriptive_router.get("/descriptive")
def descriptive_indicators(
    store: StoreDep,
    subject: str = "crew-01",
    limit: int = Query(default=10, ge=1, le=200),
) -> dict[str, Any]:
    """Los indicadores descriptivos del tripulante, con su medida leída y sus lecturas firmadas.

    Sin lecturas, lo dice: no tener ninguna es un dato, no un error (no es un 404).
    """
    readings = [item for item in store.query(subject) if item.key in DESCRIPTIVE_ONLY]
    return describe(subject, readings, set(diary_keys()), limit)
