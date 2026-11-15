"""La batería Cognition de NASA en la consola: qué mide cada prueba y lo que quedó firmado.

POR QUÉ EXISTE
--------------
El usuario pidió (2026-11-03) que las pruebas psicomotrices sean las del protocolo de NASA. Esa
batería es Cognition (Basner et al. 2015), la de Spaceflight Standard Measures y del Twins Study:
diez pruebas, de las que la PVT ya se pasa en su consola (`api/pvt_console.py`). Las otras nueve
estaban en el catálogo (`codes.COGNITION_CODES`) sin una vía para anotar una sesión.

Las pruebas las pasa y las puntúa el programa de NASA, que es software de terceros: EMMA no las
reimplementa (`ingest/cognition.py` dice por qué). Lo que hace esta ruta:

- `GET /api/cognition/protocol`: las diez pruebas en su orden de administración, cada una con
  qué mide según la frase leída en su fuente y su ficha; de la que no hay frase leída, lo dice.
  Con cada puntuación, su rango físico y la frase que dice qué es esa cifra.
- `POST /api/cognition/console`: registra las puntuaciones de una sesión con la fuente propia
  `console-cognition`, que fija el backend, con quién teclea (`recorded_by`, 422 si falta) y con
  la hora de recepción. Todo por `store.record_many` con la identidad de la fuente (invariante
  4); la ingesta genérica rechaza esta fuente como reservada (`routes._is_reserved_source`).
- `GET /api/cognition/sessions`: las sesiones leídas del registro firmado, la última primero.

Descriptivo: estas cifras no entran en el riesgo, ni en las alertas, ni en la huella de reglas
(`codes.DESCRIPTIVE_ONLY`). No se comparan con ninguna norma ni con la línea base.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.analysis.data_quality import source_label
from app.api.descriptive import _range_text
from app.api.diary import (
    NOT_RECORDED,
    RECORDED_BY_NOTE,
    OperatorName,
    _position,
    recorded_by_display,
)
from app.api.routes import (
    SettingsDep,
    StoreDep,
    _recorded_or_422,
    _when,
    identity_for,
    state_reference,
)
from app.core import display
from app.evidence import instruments_read
from app.ingest.codes import CATALOG, COGNITION_KEYS, COGNITION_TESTS, CognitionTest
from app.ingest.cognition import FIELDS, field, keys_of, to_observations
from app.ingest.fhir import ObservationType, annotated_by, deployed

cognition_router = APIRouter(prefix="/cognition")

# La fuente propia de lo anotado en esta consola. Solo la pone `POST /api/cognition/console`; la
# ingesta genérica la rechaza como reservada. No es `crew-console`, que firma decisiones del
# operador y no puede firmar una lectura.
CONSOLE_SOURCE = "console-cognition"
SUBMIT_TO = "/api/cognition/console"
PVT_PROTOCOL = "/api/pvt/protocol"

RECORDED_BY_LABEL = "Quién está en la consola"

IDENTITY = (
    "EMMA no pasa las pruebas de la batería ni las puntúa: las pasa el programa de la batería "
    "Cognition, que es software de terceros. Aquí se copian las puntuaciones que ese programa da "
    "al acabar una sesión, y se firman tal cual, con quién las teclea."
)
SCOPE = (
    "Indicadores descriptivos: se firman en el registro y se enseñan, pero el estado no los lee. "
    "No entran en el riesgo ni en las alertas, y no se comparan con ninguna norma, con la línea "
    "base ni con otras sesiones."
)
LIMITS = (
    "Las cifras se copian a mano del programa de la batería: EMMA no puede comprobar que sean "
    "las de esa sesión.",
    "Se registran sin las correcciones por la práctica y por la versión de la prueba que "
    "publican Basner et al. 2020a: no se leyeron.",
    "Una prueba se registra con todas sus puntuaciones; una sesión puede traer menos de nueve "
    "pruebas, y EMMA no rellena las que faltan. Es diseño de EMMA, sin fuente leída.",
)
EFFECTIVE_NOTE = (
    "Las lecturas se firman con la hora en que el backend recibe la sesión, no con la hora en "
    "que el programa de la batería la pasó."
)
NO_STATEMENT = (
    "Entre las frases copiadas de Dev et al. 2024 y de Basner et al. 2015 no hay ninguna que "
    "diga qué mide esta prueba dentro de la batería: las de qué mide cada prueba son de las "
    "otras nueve, y Basner et al. 2015 solo la nombra en el orden en que se pasan las pruebas."
)
PVT_NOTE = (
    "La PVT se pasa en su propia consola, con sus parámetros y lo leído de ella, y se registra "
    "con sus indicadores (tiempo de reacción medio y lapsos). Aquí no se anota."
)
# Lo que la sigla de la PVT es en el pie de la figura 1 de Basner et al. 2015
# (`basner-standard-order`): «10) Psychomotor Vigilance (PVT)».
PVT_NAME = "Psychomotor Vigilance"
# Las frases que describen la batería entera, en el orden en que se enseñan.
BATTERY_STATEMENTS = (
    "basner-standard-order",
    "bmed-cognition-subtests",
    "bmed-cognition-iss",
    "ssm-ctb-ten-tests",
    "ssm-ctb-speed-accuracy",
    "cog-speed-accuracy-metrics",
)
_MEASURE_WORDS = {"speed": "velocidad", "accuracy": "precisión", "risk": "riesgo"}


def _score(value: Any) -> Any:
    """Un booleano no es una puntuación: sin esto, `true` entraba como 1."""
    if isinstance(value, bool):
        raise ValueError("no es una cifra")
    return value


Score = Annotated[float, BeforeValidator(_score), Field(allow_inf_nan=False)]


class ConsoleCognitionIn(BaseModel):
    """Las puntuaciones de una sesión, por clave del catálogo, de quién son y quién teclea.

    No lleva hora ni fuente: las pone el backend.
    """

    model_config = ConfigDict(extra="forbid")

    scores: dict[str, Score] = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=64)
    recorded_by: OperatorName


def _received() -> dt.datetime:
    """La hora de una sesión anotada en pantalla: la de recepción."""
    return _when(None)


def _field_view(key: str) -> dict[str, Any]:
    item = field(key)
    code = CATALOG[key]
    return {
        "key": key,
        "measure": item.measure,
        "measure_display": _MEASURE_WORDS[item.measure],
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "unit_display": display.unit(code.unit),
        "decimals": display.decimals_for(key),
        "physical_min": code.physical_min,
        "physical_max": code.physical_max,
        "range_text": _range_text(code),
        "statement": instruments_read.statement(item.statement),
    }


def _test_view(order: int, test: CognitionTest) -> dict[str, Any]:
    no_accuracy = (
        instruments_read.statement("cog-mpt-no-accuracy") if test.accuracy is None else None
    )
    return {
        "order": order,
        "abbrev": test.abbrev,
        "sigla": test.sigla,
        "name": test.name,
        "measures": instruments_read.statement(f"cog-test-{test.abbrev}"),
        "measures_note": None,
        "recorded_here": True,
        "fields": [_field_view(key) for key in keys_of(test)],
        "no_accuracy": no_accuracy,
        "console": None,
        "console_note": None,
    }


def tests() -> list[dict[str, Any]]:
    """Las diez pruebas en el orden de administración: las nueve de aquí y la PVT, que remite."""
    listed = [_test_view(order, test) for order, test in enumerate(COGNITION_TESTS, start=1)]
    listed.append({
        "order": len(listed) + 1,
        "abbrev": "pvt",
        "sigla": "PVT",
        "name": PVT_NAME,
        "measures": None,
        "measures_note": NO_STATEMENT,
        "recorded_here": False,
        "fields": [],
        "no_accuracy": None,
        "console": PVT_PROTOCOL,
        "console_note": PVT_NOTE,
    })
    return listed


@cognition_router.get("/protocol")
def protocol(settings: SettingsDep) -> dict[str, Any]:
    """Qué mide cada prueba de la batería, qué puntuaciones se anotan y cómo se firman."""
    first = instruments_read.measure(FIELDS[0].key)
    return {
        "title": "Batería Cognition (NASA)",
        "identity": IDENTITY,
        "scope": SCOPE,
        "limits": list(LIMITS),
        "battery": [instruments_read.statement(ref) for ref in BATTERY_STATEMENTS],
        "tests": tests(),
        # Lo buscado y no leído es el mismo para las diecisiete puntuaciones.
        "not_found": list(first["not_found"]) if first is not None else [],
        "provenance": {
            "source": CONSOLE_SOURCE,
            "source_display": source_label(CONSOLE_SOURCE),
            "observation_type": str(ObservationType.MEASURED),
            "evidence_context": str(settings.deployment_context),
            "effective_note": EFFECTIVE_NOTE,
        },
        "recorded_by": {
            "required": True,
            "label": RECORDED_BY_LABEL,
            "note": RECORDED_BY_NOTE,
            "missing_display": NOT_RECORDED,
        },
        "submit_to": SUBMIT_TO,
    }


@cognition_router.post("/console", status_code=201)
def submit_console(
    store: StoreDep, settings: SettingsDep, payload: ConsoleCognitionIn
) -> dict[str, Any]:
    """Registra las puntuaciones de una sesión, firmadas con su fuente y con quién tecleó.

    O entra la sesión entera o no entra nada: cada motivo de rechazo va en el 422.
    """
    try:
        observations = annotated_by(
            deployed(
                to_observations(payload.scores, payload.subject, _received(), CONSOLE_SOURCE),
                settings.deployment_context,
            ),
            payload.recorded_by,
        )
    except ValueError as exc:
        # `InvalidSession` lleva todos los motivos, unidos; el modelo canónico, el suyo.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    entries = _recorded_or_422(
        lambda: store.record_many(observations, identity_for(CONSOLE_SOURCE))
    )
    return {
        "recorded": [entry.index for entry in entries],
        "keys": [item.key for item in observations],
        "source": CONSOLE_SOURCE,
        "source_display": source_label(CONSOLE_SOURCE),
        "recorded_by": payload.recorded_by,
    }


@cognition_router.get("/sessions")
def sessions(
    store: StoreDep,
    subject: str = "crew-01",
    limit: int = Query(default=5, ge=1, le=100),
) -> dict[str, Any]:
    """Las sesiones de la batería de un tripulante, leídas del registro firmado, la última primero.

    Cuenta lo anotado en esta consola y lo que llegó por la ingesta de observaciones: cada
    sesión dice con qué fuente entró y quién tecleó, si consta.
    """
    readings = store.query(subject)
    kept, reference, _ = state_reference(readings)
    # Las lecturas de una sesión comparten instante, fuente y tipo: es lo que las agrupa.
    grouped: dict[tuple[dt.datetime, str, str], list[Any]] = {}
    for item in readings:
        if item.key in COGNITION_KEYS:
            key = (item.effective, item.source, str(item.observation_type))
            grouped.setdefault(key, []).append(item)

    order = [item.key for item in FIELDS]
    found = []
    for effective, source, kind in sorted(grouped, reverse=True)[:limit]:
        items = sorted(grouped[effective, source, kind], key=lambda item: order.index(item.key))
        position, note = _position(items[0], reference)
        found.append({
            "effective": effective.isoformat(),
            "source": source,
            "source_display": source_label(source),
            "recorded_by": items[0].recorded_by,
            "recorded_by_display": recorded_by_display(items[0]),
            "observation_type": kind,
            "evidence_context": str(items[0].evidence),
            "position": position,
            "position_note": note,
            "values": [
                {
                    "key": item.key,
                    "sigla": field(item.key).test.sigla,
                    "measure_display": _MEASURE_WORDS[field(item.key).measure],
                    "display": item.code.display,
                    "display_es": item.code.display_es,
                    "value": item.value,
                    "value_text": display.quantity(item.key, item.value, item.code.unit),
                }
                for item in items
            ],
        })
    return {
        "subject": subject,
        "count": len(grouped),
        "reference_time": reference.isoformat() if kept else None,
        "sessions": found,
    }
