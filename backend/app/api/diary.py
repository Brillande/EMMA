"""Registro diario del tripulante: qué puede anotar a mano y con qué escala.

POR QUÉ EXISTE
--------------
El reto pide «recoger indicadores de salud» y la base de conocimiento cuenta con autoinformes
(ánimo, síntomas, apetito, aceptabilidad de la comida, ingesta). El catálogo los tenía y la
ingesta los aceptaba, pero ninguna pantalla los pedía: solo llegaban del simulador.

QUIÉN ANOTA (decisión del usuario, 2026-10-13)
----------------------------------------------
Hasta esa fecha el panel enviaba cada valor a `POST /api/observations` con la fuente `manual`,
la de cualquier alta a mano, y la lectura decía de qué tripulante era el dato pero no quién lo
había tecleado. Ahora el diario tiene su ruta de escritura (`POST /api/diary/entries`), que:

- **fija la fuente** (`crew-diary`): la pone el backend, no el cliente. La ingesta genérica la
  rechaza como reservada (`routes._is_reserved_source`), así que una lectura con esta fuente
  ha pasado siempre por aquí;
- **exige quién anota** (`recorded_by`, el operador de la consola): 422 si falta. Es un nombre
  declarado, como el de quien reconoce una alerta: la API no autentica a nadie;
- **solo admite indicadores del diario** y pone la hora de recepción;
- **exige el alimento valorado** en la aceptabilidad de la comida (`food`, decisión del usuario
  del 2026-10-26): la valoración es de un alimento. Texto libre con la regla de
  `ingest/food_item.py`, decisión de diseño de EMMA; en otro indicador, el campo es un 422.
  Desde el 2026-10-31 la fracción rechazada también lo admite, opcional (`food_item.REQUIRED`).

Sigue siendo una observación normal: se construye con `ingest.fhir.observation` y entra por
`store.record`, firmada y en el ledger (invariante 4). Lo anotado antes, firmado como `manual`,
se sigue leyendo y enseñando con su fuente y sin anotador («no consta»): no se rellena.

Además de esa ruta, aquí se decide, en el backend, lo que la interfaz no debe decidir:

- **qué indicadores entran**: los del catálogo cuyo coste de medir (`measurement_cost.json`)
  es un autoinforme, un diario o un registro de ingesta. No hay lista escrita a mano;
- **con qué escala**: el rango físico del catálogo. Un punto solo lleva rótulo si se leyó
  en una fuente (`evidence/instruments_read.py`: hoy, los nueve de la escala hedónica, en
  inglés: los extremos, de NASA en 2025; del 2 al 8, de un informe de JSC de 1981). Las
  escalas propias de la misión no tienen fuente: siguen «sin rótulos verificados» y, desde el
  2026-10-15, publican aparte sus anclas (`design_anchors`), las que decidió EMMA, marcadas
  como decisión de diseño sin validar y con por qué no hay instrumento publicado detrás
  (`codes.OWN_SCALE_ANCHORS`). Un rótulo leído y un ancla decidida no van nunca en el mismo
  campo: el primero lleva su frase; la segunda no tiene ninguna que llevar;
- **con qué procedencia** se firma una entrada de la consola.

No interpreta lo anotado ni toca el análisis (invariante 5): una lectura anotada a mano
entra en la línea base como cualquier otra del mismo indicador, que es lo que el motor ya
hacía con un alta manual.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.analysis.alert_support import TYPE_WORDS
from app.analysis.data_quality import source_label
from app.api.routes import (
    CURRENT_WINDOW,
    SettingsDep,
    StoreDep,
    _recorded_or_422,
    _when,
    analysed_type_words,
    identity_for,
    is_analysed_type,
    state_reference,
)
from app.core import display
from app.evidence import instruments_read
from app.ingest import food_item
from app.ingest.codes import (
    CATALOG,
    DESCRIPTIVE_ONLY,
    LAB_REPORT_ONLY,
    MISSION_SPECIFIC,
    OWN_SCALE_ANCHORS,
    OWN_SCALES_DECIDED_ON,
    SELF_REPORTED_ONLY,
    ULTRASOUND_MEASURES,
    ReferenceBasis,
    VitalCode,
)
from app.ingest.cost import cost, costs
from app.ingest.fhir import ObservationType, VitalObservation, observation

diary_router = APIRouter(prefix="/diary")

# Con qué se obtiene un indicador que el tripulante anota por sí mismo, con las palabras de
# `measurement_cost.json`. El dolor («mapa corporal de dolor») queda fuera a propósito: su
# lectura va siempre con el informe que la explica (`api/pain.py`).
DIARY_EQUIPMENT = frozenset({"autoinforme", "diario de síntomas", "registro de ingesta"})

# La fuente propia del registro diario. NO es `crew-console`: esa identidad firma decisiones
# del operador (reconocer, silenciar) y una lectura no puede llevarla. Es una fuente de datos
# más, con su clave de firma, que solo pone esta ruta.
DIARY_SOURCE = "crew-diary"
# Con qué se firmaba una anotación antes del 2026-10-13: la fuente de cualquier alta a mano.
# Esas lecturas siguen en el registro y se siguen enseñando, con su fuente y sin anotador.
LEGACY_SOURCE = "manual"
DIARY_SOURCES = frozenset({DIARY_SOURCE, LEGACY_SOURCE})

# Lo que se dice de una lectura que no lleva quién la anotó. No se rellena con nadie.
NOT_RECORDED = "no consta"
RECORDED_BY_LABEL = "Quién anota"
RECORDED_BY_NOTE = (
    "Con cada valor se firma el nombre que declara quien lo teclea en la consola, que puede "
    "no ser el tripulante del dato. Es un nombre declarado: la consola no autentica a nadie."
)
LEGACY_NOTE = (
    f"Las anotaciones firmadas como «{source_label(LEGACY_SOURCE)}» no llevan quién las "
    f"anotó: de ellas se dice «{NOT_RECORDED}»."
)


def _named(value: str) -> str:
    if not any(character.isalnum() for character in value):
        raise ValueError("debe contener al menos una letra o una cifra")
    return value


# «Lo anota una persona con nombre»: la misma regla que `acknowledged_by` o `declared_by`.
OperatorName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    AfterValidator(_named),
]


class DiaryEntryIn(BaseModel):
    """Un valor del registro diario, como lo envía la consola.

    No lleva fuente, tipo, entorno ni hora: los pone el backend. Un campo de más es un 422
    (`extra="forbid"`), para que nadie crea haber elegido una fuente que no se ha usado.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: float
    subject: str = Field(min_length=1, max_length=64)
    recorded_by: OperatorName
    # El alimento valorado: en la aceptabilidad de la comida, obligatorio; en la fracción
    # rechazada, opcional; en los demás, un 422. La regla (`food_item.accept`) la aplica la ruta,
    # con su motivo en español; el tope de aquí solo evita leer un texto enorme antes de
    # rechazarlo.
    food: str | None = Field(default=None, max_length=food_item.FIELD_MAX_LENGTH)


def _received() -> dt.datetime:
    """La hora de una anotación: la de recepción. La consola no envía ninguna."""
    return _when(None)


def recorded_by_display(reading: VitalObservation) -> str:
    return reading.recorded_by if reading.recorded_by is not None else NOT_RECORDED

# Unidad UCUM de una puntuación: el indicador es una escala, no una magnitud física.
_SCORE_UNIT = "{score}"

SCALE_UNLABELLED = "escala sin rótulos verificados"
# Cómo se marcan las anclas de una escala propia. No hay un estado «validada»: nadie las ha
# validado, y la marca lo dice en cada respuesta que las lleva.
DESIGN_STATUS = "design"
DESIGN_STATUS_DISPLAY = "decisión de diseño de EMMA, sin validar"
# La verdad completa de una escala propia: no es que falte leer su fuente, es que no la tiene.
SCALE_OWN = (
    "Es una escala propia de la misión: ninguna fuente la define. Sus anclas son una "
    f"{DESIGN_STATUS_DISPLAY}, no un dato leído"
)
# La de un instrumento publicado cuya fuente sí se leyó (los indicadores descriptivos, desde el
# 2026-10-16): la fuente no escribe un rótulo junto a cada número, y no se le pone ninguno. Lo
# leído va aparte, en `instrument`, con cada frase y, si da categorías con palabras, cada una.
SCALE_INSTRUMENT = (
    "Es un instrumento publicado con su fuente leída, que no escribe un rótulo junto a cada "
    "número de la escala: lo leído va con su frase"
)
# Un instrumento cuya fuente escribe sus anclas con su número (el estrés del Reaction Self Test):
# decir que no tiene rótulos contradiría las anclas que el diario enseña al lado. No vale para los
# síntomas visuales, cuyas categorías son de la fuente pero sus números, de EMMA.
SOURCE_NUMBERED_ANCHORS = frozenset({"stress-rating-vas"})
SCALE_INSTRUMENT_ANCHORED = (
    "Es un instrumento publicado con su fuente leída: lleva solo las anclas que ella escribe, y "
    "ningún rótulo en los demás puntos de la escala"
)
# Un indicador descriptivo se firma como cualquier otro, pero el estado no lo lee.
DESCRIPTIVE_NOTE = (
    "Indicador descriptivo: se firma y se enseña, pero el estado no lo lee ni entra en la "
    "línea base."
)

# Lo que conviene saber antes de anotar. Descriptivo: lo que el sistema ya hace.
NOTES = (
    "Cada valor se guarda como una lectura medida, firmada en el registro con la fuente "
    f"«{source_label(DIARY_SOURCE)}», con el nombre de quien lo anota y con la hora en que "
    "se recibe.",
    "Una lectura anotada aquí entra en la línea base personal junto a las demás lecturas del "
    "mismo indicador, vengan de donde vengan: el análisis no las separa por fuente. Los "
    "indicadores descriptivos son la excepción: se firman igual, pero el estado no los lee.",
    "Es un registro real: mientras exista, el almacén no se puede sustituir por otro "
    "escenario simulado.",
)

_CONCERNING = {
    "low": "El catálogo vigila el extremo bajo.",
    "high": "El catálogo vigila el extremo alto.",
}


def diary_keys() -> list[str]:
    """Indicadores que admite el registro diario, en el orden del catálogo.

    Solo los que la ingesta genérica acepta: uno que exige su informe o su imagen daría un
    422 al enviarlo, y ofrecerlo sería ofrecer un formulario que no se puede guardar.
    """
    excluded = SELF_REPORTED_ONLY | ULTRASOUND_MEASURES | LAB_REPORT_ONLY
    keys = []
    for key in CATALOG:
        # La ficha sin traducir: `cost()` sirve el equipo en el idioma de la petición, y aquí se
        # compara con las palabras castellanas del fichero (en inglés el diario salía vacío).
        item = costs().get(key)
        if item is not None and item["equipment"] in DIARY_EQUIPMENT and key not in excluded:
            keys.append(key)
    return keys


def _range_text(code: VitalCode) -> str:
    decimals = display.decimals_for(code.key)
    low, high = code.physical_min, code.physical_max
    if low is not None and high is not None:
        return f"de {display.number(low, decimals)} a {display.number(high, decimals)}"
    if low is not None:
        return f"desde {display.number(low, decimals)}"
    if high is not None:
        return f"hasta {display.number(high, decimals)}"
    return "sin rango físico declarado"


def _reference_text(code: VitalCode) -> str:
    """El rango de referencia que el catálogo ya daba a la escala, y de dónde sale.

    El catálogo admite medio rango (`fluid-intake-24h` lleva solo `reference_low`): un extremo
    solo se dice «desde X» o «hasta Y», como `_range_text`, y no «sin rango», que sería callar
    el extremo que sí hay. Hoy ninguna escala propia tiene medio rango; la prueba lo fija con un
    caso sintético para que el día que lo tenga no se pierda.
    """
    low, high = code.reference_low, code.reference_high
    decimals = display.decimals_for(code.key)
    if low is not None and high is not None:
        span = f"de {display.number(low, decimals)} a {display.number(high, decimals)}"
    elif low is not None:
        span = f"desde {display.number(low, decimals)}"
    elif high is not None:
        span = f"hasta {display.number(high, decimals)}"
    else:
        return "El catálogo no le da rango de referencia."
    if code.reference_basis is ReferenceBasis.DESIGN:
        return (
            f"El catálogo le da {span} como rango de referencia, también decidido por EMMA: "
            "no se observó en población."
        )
    return f"El catálogo le da {span} como rango de referencia ({code.reference_basis})."


def _design_anchors(code: VitalCode) -> dict[str, Any] | None:
    """Las anclas de una escala propia de la misión: las decidió EMMA y se dicen así.

    Van aparte de `labels` a propósito. `labels` son rótulos leídos en una fuente, cada uno con
    su frase; esto no se leyó en ningún sitio, y por eso no lleva frase, ficha ni enlace: no
    hay instrumento publicado que citar, y citar otro sería atribuirle una fuente. Los puntos
    son los extremos del rango físico del catálogo, para que no puedan separarse de él.
    """
    anchors = OWN_SCALE_ANCHORS.get(code.key)
    if anchors is None or code.physical_min is None or code.physical_max is None:
        return None
    low, high = code.physical_min, code.physical_max
    return {
        "status": DESIGN_STATUS,
        "status_display": DESIGN_STATUS_DISPLAY,
        "decided_on": OWN_SCALES_DECIDED_ON,
        "why": anchors.why,
        "anchors": [
            {"value": low, "label": anchors.low},
            {"value": high, "label": anchors.high},
        ],
        "between": (
            f"Entre {display.number(low, 0)} y {display.number(high, 0)} ningún punto lleva ancla."
        ),
        "reference": _reference_text(code),
    }


def _labels(code: VitalCode) -> dict[str, Any]:
    """Los rótulos de una escala: los leídos en su fuente, o por qué no tiene ninguno.

    Tres casos, y ninguno se disimula: rótulos leídos (solo los que la fuente escribe, en su
    idioma); escala propia de la misión, que no tiene fuente y cuyas anclas decidió EMMA
    (`design_anchors`, marcadas como decisión de diseño sin validar); y escala de la que
    simplemente no se ha leído nada.
    """
    read = instruments_read.scale_labels(code.key)
    if read is not None:
        return {
            "labels": read["labels"],
            "labels_status": "read",
            "labels_language": read["language"],
            "labels_note": read["labels_note"],
            "labels_sources": read["sources"],
            "labels_see_also": read["see_also"],
            "labels_not_found": read["not_found"],
            "design_anchors": None,
            "instrument": None,
        }
    instrument = instruments_read.measure(code.key)
    if instrument is not None:
        # Un instrumento publicado, leído: ni rótulos que la fuente no escribe ni anclas de EMMA.
        return {
            "labels_status": "instrument", "labels": None, "labels_language": None,
            "labels_note": (
                SCALE_INSTRUMENT_ANCHORED if code.key in SOURCE_NUMBERED_ANCHORS
                else f"{SCALE_UNLABELLED}. {SCALE_INSTRUMENT}"
            ),
            "labels_see_also": [], "labels_sources": [], "labels_not_found": [],
            "instrument": instrument, "design_anchors": None,
        }
    own = code.key in instruments_read.OWN_SCALES
    return {
        "labels": None,
        "labels_status": "own" if own else "unverified",
        "labels_language": None,
        "labels_note": f"{SCALE_UNLABELLED}. {SCALE_OWN}" if own else SCALE_UNLABELLED,
        "labels_sources": [],
        "labels_see_also": [],
        "labels_not_found": [],
        "design_anchors": _design_anchors(code) if own else None,
        "instrument": None,
    }


def _scale(code: VitalCode) -> dict[str, Any] | None:
    """La escala de un indicador de puntos, tal como está escrita en el catálogo."""
    if code.unit != _SCORE_UNIT:
        return None
    return {
        # Lo que el catálogo dice de la escala al justificar su código propio.
        "described_as": MISSION_SPECIFIC.get(code.key),
        **_labels(code),
        "concerning": code.concerning,
        # De un descriptivo no se dice que el catálogo «vigile» un extremo: el estado no lo lee.
        "concerning_note": (
            DESCRIPTIVE_NOTE if code.key in DESCRIPTIVE_ONLY else _CONCERNING.get(code.concerning)
        ),
    }


def describe(code: VitalCode) -> dict[str, Any]:
    item = cost(code.key) or {}
    return {
        "key": code.key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "unit_display": display.unit(code.unit),
        "domain": str(code.domain),
        "decimals": display.decimals_for(code.key),
        "physical_min": code.physical_min,
        "physical_max": code.physical_max,
        "range_text": _range_text(code),
        "equipment": item.get("equipment"),
        "mode_display": item.get("mode_display"),
        "scale": _scale(code),
        # Se anota igual, pero el estado no lo lee (`codes.DESCRIPTIVE_ONLY`).
        "descriptive_only": code.key in DESCRIPTIVE_ONLY,
        # El alimento que se valora, con su regla (decisión de diseño de EMMA) y si es
        # obligatorio en este indicador; `None` en los indicadores que no lo llevan.
        "food_item": food_item.describe(code.key) if code.key in food_item.KEYS else None,
    }


@diary_router.get("")
def diary(settings: SettingsDep) -> dict[str, Any]:
    """Qué se puede anotar en el registro diario y cómo se firma. No guarda nada."""
    return {
        "indicators": [describe(CATALOG[key]) for key in diary_keys()],
        # Con qué procedencia firma `POST /api/diary/entries` cada valor. La consola no la
        # envía: la lee de aquí para enseñarla.
        "provenance": {
            "source": DIARY_SOURCE,
            "source_display": source_label(DIARY_SOURCE),
            "observation_type": str(ObservationType.MEASURED),
            "evidence_context": str(settings.deployment_context),
        },
        # Quién teclea: obligatorio en cada envío, y cómo se nombra cuando una lectura
        # antigua no lo lleva.
        "recorded_by": {
            "required": True,
            "label": RECORDED_BY_LABEL,
            "note": RECORDED_BY_NOTE,
            "missing_display": NOT_RECORDED,
            "legacy_note": LEGACY_NOTE,
        },
        "submit_to": "/api/diary/entries",
        "notes": list(NOTES),
    }


@diary_router.post("/entries", status_code=201)
def record_entry(
    store: StoreDep, settings: SettingsDep, payload: DiaryEntryIn
) -> dict[str, Any]:
    """Firma un valor del registro diario con su fuente propia y con quién lo tecleó.

    Es una observación como cualquier otra (invariante 4): se construye con el modelo
    canónico, que rechaza lo que no es una medida, y se anexa al ledger con `store.record`.
    """
    if payload.key not in diary_keys():
        raise HTTPException(
            status_code=422,
            detail=f"'{payload.key}' no es un indicador del registro diario",
        )
    food = _food_or_422(payload.key, payload.food)
    try:
        recorded = observation(
            payload.key, payload.value, _received(), payload.subject, DIARY_SOURCE,
            observation_type=ObservationType.MEASURED,
            evidence_context=settings.deployment_context,
            recorded_by=payload.recorded_by,
            food=food,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry = _recorded_or_422(lambda: store.record(recorded, identity_for(DIARY_SOURCE)))[0]
    return {
        "ledger_index": entry.index,
        "content_hash": entry.content_hash,
        "source": recorded.source,
        "source_display": source_label(recorded.source),
        "recorded_by": recorded.recorded_by,
        "food": recorded.food,
    }


def _food_or_422(key: str, food: str | None) -> str | None:
    """El alimento normalizado que se firmará, o el 422 con el motivo.

    El diario EXIGE el alimento donde es obligatorio (la valoración); la regla entera es la de
    `food_item.accept`, la misma que aplican la ingesta genérica y la enmienda.
    """
    try:
        return food_item.accept(key, food, require=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# La posición de una entrada que el estado no lee por su tipo (§5.39.11). Hasta entonces un alta
# antigua inferida se situaba por su fecha frente al «ahora» («anterior a la ventana»), como si
# el estado la hubiera leído; y sin nada que decidiera, frente a la cota con que `_analysable`
# responde a una lista vacía. Va antes de mirar la fecha: una lectura que el estado no lee no
# está dentro ni fuera de su ventana.
NOT_ANALYSED_BY_TYPE = "not-analysed-by-type"
# `{kind}` es el tipo de la entrada y `{analysed}` los que deciden (`routes.analysed_type_words`):
# ninguno se escribe a mano.
NOT_ANALYSED_BY_TYPE_NOTE = (
    "Registrada como {kind}: el estado no la lee por su tipo (solo lee lecturas {analysed}), y "
    "no se sitúa frente a su ventana actual."
)


def _position(reading: VitalObservation, reference: dt.datetime) -> tuple[str, str]:
    """Dónde cae una entrada respecto a los datos que analiza el estado.

    Una anotación de un indicador descriptivo no cae en ningún sitio: el estado no la lee, ni
    dentro de su ventana ni fuera (`codes.DESCRIPTIVE_ONLY`). Tampoco una inferida o predicha
    (`routes.ANALYSED_TYPES`): se dice su tipo y no se compara con `reference`. Las dos salen
    antes de mirar la fecha; por eso, cuando nada decide y `reference` es la cota de
    `_analysable`, ninguna entrada llega a compararse con ella: una entrada medida con fecha
    analizable ya habría decidido, y la ingesta no admite fechas anteriores a esa cota
    (`routes._when`, `wearable.EARLIEST_IMPORTED_READING`). Se dice eso, sin color.
    """
    if reading.key in DESCRIPTIVE_ONLY:
        return ("descriptive", DESCRIPTIVE_NOTE)
    if not is_analysed_type(reading):
        # `TYPE_WORDS` cubre todo `ObservationType` (lo fija `tests/test_set_aside_everywhere.py`).
        kind = TYPE_WORDS[str(reading.observation_type)][0]
        return (
            NOT_ANALYSED_BY_TYPE,
            NOT_ANALYSED_BY_TYPE_NOTE.format(kind=kind, analysed=analysed_type_words()),
        )
    if reading.effective > reference:
        return (
            "after-reference",
            "Fechada después de la referencia de los datos: el estado la aparta del análisis.",
        )
    if reading.effective >= reference - CURRENT_WINDOW:
        return ("current", "Dentro de la ventana actual del estado.")
    return ("earlier", "Anterior a la ventana actual del estado.")


@diary_router.get("/entries")
def diary_entries(
    store: StoreDep,
    subject: str = "crew-01",
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    """Lo anotado a mano por un tripulante, leído del registro firmado, lo último primero.

    Es lo que la consola enseña tras guardar: qué quedó registrado y a qué hora, no lo que
    el formulario cree que envió. Cuenta lo firmado con la fuente del diario y lo firmado
    antes como alta manual; cada entrada dice con cuál entró y quién la anotó, si consta.
    """
    readings = store.query(subject)
    # La referencia es la del estado, que no lee los indicadores descriptivos ni lo inferido o
    # predicho (`routes.state_reference`): una anotación así no puede mover el «ahora» con el
    # que se sitúan las demás.
    kept, reference, _ = state_reference(readings)
    keys = set(diary_keys())
    mine = sorted(
        (item for item in readings if item.source in DIARY_SOURCES and item.key in keys),
        key=lambda item: item.effective,
        reverse=True,
    )
    entries = []
    for item in mine[:limit]:
        position, note = _position(item, reference)
        entries.append(
            {
                "key": item.key,
                "display": item.code.display,
                "display_es": item.code.display_es,
                "value": item.value,
                "value_text": display.quantity(item.key, item.value, item.code.unit),
                "effective": item.effective.isoformat(),
                "source": item.source,
                "source_display": source_label(item.source),
                # Quién la tecleó, tal como quedó firmado; `None` si la lectura no lo lleva.
                "recorded_by": item.recorded_by,
                "recorded_by_display": recorded_by_display(item),
                # El alimento valorado, tal como quedó firmado; `None` si la lectura no lo lleva.
                "food": item.food,
                "observation_type": str(item.observation_type),
                "evidence_context": str(item.evidence),
                "position": position,
                "position_note": note,
            }
        )
    return {
        "subject": subject,
        "count": len(mine),
        # Sin ninguna lectura con fecha analizable no hay «ahora»: se dice nulo, no la cota.
        "reference_time": reference.isoformat() if kept else None,
        "entries": entries,
    }
