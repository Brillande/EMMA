"""Adaptador del contrato JSON de §5 de la especificacion del equipo (`docs/contexto/`).

Por que existe: §5 define «un esquema canonico de observacion con unidades y procedencia
explicitas» con sus propios nombres (`timestamp`, `subject_id`, `variable_id`, `value`, `unit`,
`source`, `quality`, `evidence_context`, `observation_type`, `model_version`), y §13 pide
adaptadores de «archivos/demo». EMMA tenia el alta manual con nombres propios (`ObservationIn`:
`key`, `subject`, `effective`, `confidence`...) y la correspondencia entre ambos solo escrita, en
`compliance/record-integrity.md` §3.14 quater. Un fichero con la forma literal de §5 no tenia por
donde entrar sin reescribirlo a mano campo a campo.

Este modulo es la fuente unica de esa correspondencia (`FIELDS`; la columna «nombre en la
ingesta» de la tabla del documento se compara con el en `tests/test_observation_unit.py`) y la
ruta que la aplica: `POST /api/import/observations` recibe como cuerpo una lista JSON de lecturas
con los nombres de §5 —el fichero tal cual, como `/api/import/apple-health` recibe el `export.xml`
y `/api/import/google-fit` la respuesta de su API— y las traduce a `ObservationIn`.

Lo que NO es: otra via al ledger. Cada lectura traducida pasa por lo mismo que
`POST /api/observations` (`routes._catalog_or_422`, `routes._observation_or_422`: catalogo,
unidad, modelo canonico) y el lote se firma entero con `record_many`, con la identidad de su
fuente: entra entero o nada. Una unidad distinta de la del catalogo, un campo que §5 no tiene o un
`variable_id` fuera del catalogo son un 422 que dice la lectura, el campo y el motivo, y al ledger
no llega ninguna del lote.

`variable_id` es la clave del catalogo: el ejemplo de §5 escribe `hrv_rmssd` y el catalogo
`hrv-rmssd`, y no se normaliza (un nombre adivinado seria una lectura atribuida a otro indicador).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.api import routes
from app.api.console_header import console_post
from app.api.routes import (
    ObservationIn,
    SettingsDep,
    StoreDep,
    _binding_notice,
    _catalog_or_422,
    _import_slots,
    _json_or_422,
    _observation_or_422,
    _read_capped,
    _recorded_or_422,
    identity_for,
)
from app.core.config import Settings
from app.core.storage import ObservationStore
from app.ingest.codes import LAB_REPORT_ONLY, SELF_REPORTED_ONLY
from app.ingest.fhir import EvidenceContext, VitalObservation
from app.ingest.wearable import MAX_CLOCK_SKEW

spec5_router = APIRouter()

# NOMBRE EN §5 -> NOMBRE EN LA INGESTA (`ObservationIn`). Fuente unica de la correspondencia: la
# tabla de `record-integrity.md` §3.14 quater la copia en su ultima columna y una prueba las
# compara. Son exactamente los diez campos del JSON de §5, en su orden; `context` (estado
# fisiologico), `device`, `recorded_by` y `food` son de EMMA, §5 no los tiene y por aqui no entran.
FIELDS: Mapping[str, str] = MappingProxyType({
    "timestamp": "effective",
    "subject_id": "subject",
    "variable_id": "key",
    "value": "value",
    "unit": "unit",
    "source": "source",
    "quality": "confidence",
    "evidence_context": "evidence_context",
    "observation_type": "observation_type",
    "model_version": "model_version",
})

# Lo que una lectura de fichero no puede omitir sin que EMMA le invente algo. El alta manual
# supone «ahora», `crew-01` y `manual` cuando faltan, y tiene sentido para quien teclea una cifra
# delante de la consola; en un fichero importado despues, una lectura sin instante apareceria
# como de hoy, y sin sujeto o sin fuente quedaria atribuida a quien no la produjo. §5 pide
# «procedencia explicita». `unit` ausente se asume del catalogo y se dice; `quality` ausente es
# confianza plena, como en el alta; `evidence_context` ausente es el del despliegue;
# `observation_type` ausente es `measured`; `model_version` es nulo salvo que no sea una medida.
REQUIRED: frozenset[str] = frozenset({"timestamp", "subject_id", "variable_id", "value", "source"})

# §5 escribe `ISS` en mayusculas («ISS|analog_bedrest|simulated|ground»); el codigo de EMMA es
# `iss` (`EvidenceContext`). Es el UNICO alias: nada mas se normaliza ni se pasa a minusculas, y
# los otros codigos de EMMA (`spaceflight`, `analog_isolation`) se admiten con su nombre.
EVIDENCE_CONTEXT_ALIASES: Mapping[str, str] = MappingProxyType({"ISS": EvidenceContext.ISS.value})

_SPEC_NAME = {emma: spec for spec, emma in FIELDS.items()}

# La forma de un instante de §5. Pydantic admite tambien, en modo estricto, un texto numerico como
# segundos desde 1970 («1700000000»), ya con zona: un numero de cuenta firmado como fecha.
_ISO_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]")

# Tope de un motivo. Los rechazos repiten nombres que llegan del fichero; sin tope, una clave de
# 200 KB o miles de fuentes devuelven una respuesta del tamano de la peticion, lo mismo que
# `_RejectionLog` y `_unit_length_or_422` ya evitan en las otras vias.
MAX_DETAIL_CHARS = 500

# La fuente firma: acaba de clave en el registro de confianza, y un fichero no la elige sin tope.
MAX_SOURCE_CHARS = 128

# Como se nombra en un error lo que llega donde se esperaba un objeto.
_JSON_KIND: Mapping[type, str] = MappingProxyType({
    list: "una lista", str: "un texto", bool: "un booleano", int: "un número", float: "un número",
    type(None): "null",
})


class _Reading(dict[str, Any]):
    """Un objeto del JSON que recuerda sus claves repetidas.

    `json.loads` se queda con la ultima sin decir nada: `"value": 61, "value": 180` entraria
    como 180 y una unidad ajena declarada antes de otra quedaria oculta. Se detecta al parsear,
    que es cuando aun existen, y se rechaza al validar, que es cuando se sabe que lectura es.
    """

    repeated: tuple[str, ...] = ()


def _reading_of(pairs: list[tuple[str, Any]]) -> _Reading:
    reading = _Reading(pairs)
    counts = Counter(name for name, _ in pairs)
    reading.repeated = tuple(sorted(name for name, count in counts.items() if count > 1))
    return reading


def translate(item: Mapping[str, Any]) -> dict[str, Any]:
    """Una lectura con los nombres de §5, con los de `ObservationIn`.

    `ValueError` con el campo y el motivo, en español, si tiene un campo que §5 no define o le
    falta uno obligatorio. Un campo opcional nulo cuenta como ausente: §5 escribe
    `"model_version": null`, y una unidad nula es una unidad sin declarar. Uno obligatorio nulo
    falta.
    """
    unknown = sorted(set(item) - set(FIELDS))
    if unknown:
        raise ValueError(
            f"campo desconocido {_listed(unknown)}: los campos de §5 son {', '.join(FIELDS)}"
        )
    missing = sorted(name for name in REQUIRED if item.get(name) is None)
    if missing:
        raise ValueError(
            f"falta el campo {_listed(missing)}, obligatorio en esta vía: EMMA no supone el "
            "instante, el sujeto, el indicador, el valor ni la fuente de una lectura importada"
        )
    # Un texto de espacios no es un dato: `is None` lo dejaba pasar y firmaba una lectura a nombre
    # de nadie, que es lo que `REQUIRED` evita.
    blank = sorted(
        name for name in ("subject_id", "variable_id", "source", "model_version")
        if isinstance(item.get(name), str) and not item[name].strip()
    )
    if blank:
        raise ValueError(f"campo {_listed(blank)}: en blanco: no dice nada de la lectura")
    source = item["source"]
    if isinstance(source, str) and len(source) > MAX_SOURCE_CHARS:
        raise ValueError(f"campo 'source': más de {MAX_SOURCE_CHARS} caracteres")
    timestamp = item["timestamp"]
    if isinstance(timestamp, str) and not _ISO_INSTANT.match(timestamp):
        raise ValueError(
            "campo 'timestamp': no es un instante ISO-8601 (`AAAA-MM-DDThh:mm:ss` con su zona)"
        )
    translated: dict[str, Any] = {}
    for name, value in item.items():
        if value is None:
            continue
        if name == "evidence_context" and isinstance(value, str):
            value = EVIDENCE_CONTEXT_ALIASES.get(value, value)
        translated[FIELDS[name]] = value
    return translated


def _listed(names: list[str]) -> str:
    return ", ".join(repr(name) for name in names)


def _label(position: int, total: int) -> str:
    return f"lectura {position + 1} de {total}"


def _observation_in(item: object, label: str) -> ObservationIn:
    """La lectura traducida y validada por el esquema del alta manual, o 422 con la lectura."""
    if not isinstance(item, Mapping):
        kind = _JSON_KIND.get(type(item), type(item).__name__)
        raise HTTPException(
            status_code=422,
            detail=f"{label}: se esperaba un objeto JSON con los campos de §5, llega {kind}",
        )
    if isinstance(item, _Reading) and item.repeated:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label}: campo repetido {_listed(list(item.repeated))}: una lectura con dos "
                "valores para un campo no dice cuál vale"
            ),
        )
    try:
        translated = translate(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label}: {exc}") from exc
    # ESTRICTO, a diferencia del alta manual: Pydantic en modo laxo toma `true` por 1.0, "64" por
    # 64 y un entero por un instante. Delante de la consola hay una persona que ve lo que entro;
    # un fichero importado despues no lo lee nadie, y una cifra que no era una cifra quedaria
    # firmada. Se valida como JSON (lo que es) porque el modo estricto sobre un `dict` exigiria
    # un `datetime` ya construido para el instante.
    try:
        payload = ObservationIn.model_validate_json(json.dumps(translated), strict=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"{label}: {_in_spec_names(exc)}") from exc
    # SIN ZONA NO HAY INSTANTE. El alta manual toma por UTC un instante sin zona (`_when`), que es
    # un supuesto como los de `REQUIRED`: en un fichero son horas de error firmadas sin que nadie
    # las vea. §5 pide ISO-8601; aqui la zona, o `Z`, es obligatoria.
    if payload.effective is not None and payload.effective.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label}: campo 'timestamp': sin zona horaria: EMMA no supone la zona de una "
                "lectura importada; escríbela (`Z` para UTC)"
            ),
        )
    # El alta manual no acota el futuro (`routes._when`: las pruebas y el simulador usan la fecha de
    # la misión). Un fichero no tiene esa razón, y las otras importaciones ya lo rechazan.
    latest = dt.datetime.now(dt.UTC) + MAX_CLOCK_SKEW
    if payload.effective is not None and payload.effective > latest:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: campo 'timestamp': instante en el futuro",
        )
    return payload


def _in_spec_names(exc: ValidationError) -> str:
    """Los errores del esquema, con el nombre del campo tal y como lo escribe §5.

    El motivo de los validadores propios (`source` reservada) ya esta en español; el de un tipo
    equivocado («Input should be a valid number») es el de Pydantic, como en el alta manual. Un
    error sin campo (de todo el modelo) va solo con su motivo.
    """
    reasons = []
    for error in exc.errors():
        location = [str(part) for part in error["loc"]]
        message = error["msg"].removeprefix("Value error, ")
        if not location:
            reasons.append(message)
            continue
        location[0] = _SPEC_NAME.get(location[0], location[0])
        reasons.append(f"campo {'.'.join(location)!r}: {message}")
    return "; ".join(reasons)


@spec5_router.post(
    "/import/observations",
    status_code=201,
    # Lee el cuerpo tal cual y firma lecturas en el ledger: sin la cabecera de la consola, una
    # petición simple desde otra página las firmaría. Como las otras dos importaciones.
    **console_post(
        requestBody={
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {name: {} for name in FIELDS},
                            "required": sorted(REQUIRED),
                            "additionalProperties": False,
                        },
                    }
                }
            },
        }
    ),
)
async def import_spec5_observations(
    request: Request, store: StoreDep, settings: SettingsDep
) -> dict[str, Any]:
    """Importa un lote de lecturas con los nombres literales de §5 de la especificacion.

    El cuerpo es la lista JSON tal cual (un fichero `--data-binary @lecturas.json`), con los
    mismos topes que las demas importaciones: tamaño, numero de lecturas e importaciones a la vez.
    Entra entero o nada; la respuesta dice cuantas, de que indicadores, y de cuales se asumio la
    unidad del catalogo por no venir declarada. Muestra en
    `app/data/samples/spec5_observations.json`.
    """
    body = await _read_capped(request)
    async with _import_slots:
        return await run_in_threadpool(_import_spec5, store, body, settings)


def _import_spec5(store: ObservationStore, body: bytes, settings: Settings) -> dict[str, Any]:
    """La importacion, con todo motivo de rechazo acotado en un solo sitio."""
    try:
        return _import_batch(store, body, settings)
    except HTTPException as exc:
        if isinstance(exc.detail, str) and len(exc.detail) > MAX_DETAIL_CHARS:
            exc.detail = f"{exc.detail[:MAX_DETAIL_CHARS]}… (motivo recortado)"
        raise


def _only_elsewhere(key: str) -> str | None:
    """Por que un indicador no entra por esta via, o `None` si entra.

    `record_many` lo rechaza igualmente, y es quien lo garantiza; aqui se comprueba antes para
    poder decir que lectura de un fichero largo es la que no entra.
    """
    if key in SELF_REPORTED_ONLY:
        return f"'{key}' solo se registra con su informe de dolor"
    if key in LAB_REPORT_ONLY:
        return f"'{key}' solo se registra confirmando una analítica escaneada"
    return None


def _import_batch(store: ObservationStore, body: bytes, settings: Settings) -> dict[str, Any]:
    batch = _json_or_422(body, object_pairs_hook=_reading_of)
    if not isinstance(batch, list):
        raise HTTPException(
            status_code=422,
            detail="se esperaba una lista JSON de lecturas con los campos de §5",
        )
    if not batch:
        raise HTTPException(
            status_code=422, detail="la lista está vacía: no hay ninguna lectura que importar"
        )
    # El tope se lee al llamar, como en las otras importaciones, y antes de traducir nada.
    if len(batch) > routes.MAX_IMPORT_RECORDS:
        raise HTTPException(
            status_code=413,
            detail=f"más de {routes.MAX_IMPORT_RECORDS} lecturas en una importación",
        )

    total = len(batch)
    labels = [_label(position, total) for position in range(total)]
    payloads = [_observation_in(item, label) for label, item in zip(labels, batch, strict=True)]

    # El ledger firma cada lote con una identidad (`record_many`, §3.4): un lote es una fuente.
    sources = sorted({payload.source for payload in payloads})
    if len(sources) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "un lote lleva una sola fuente ('source'), porque el ledger firma cada lote con "
                f"una identidad; llegan {_listed(sources)}: envíalas en lotes separados"
            ),
        )

    # Todo el lote se comprueba antes de firmar nada: la primera lectura que no pasa lo para.
    observations: list[VitalObservation] = []
    units: dict[str, dict[str, Any]] = {}
    for label, payload in zip(labels, payloads, strict=True):
        try:
            code = _catalog_or_422(payload.key)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=f"{label}, campo 'variable_id': {exc.detail}"
            ) from exc
        elsewhere = _only_elsewhere(code.key)
        if elsewhere:
            raise HTTPException(
                status_code=422, detail=f"{label}, campo 'variable_id': {elsewhere}"
            )
        try:
            recorded, unit = _observation_or_422(code, payload, settings)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=f"{label}: {exc.detail}"
            ) from exc
        observations.append(recorded)
        tally = units.setdefault(code.key, {"unit": code.unit, "declared": 0, "assumed": 0})
        tally["assumed" if unit["unit_assumed"] else "declared"] += 1

    entries = _recorded_or_422(
        lambda: store.record_many(observations, identity_for(sources[0]))
    )
    # El aviso de vinculo sensor-tripulante, como en las otras importaciones: §5 no tiene `device`,
    # pero el vinculo tambien se declara por fuente. Uno por sujeto: un lote puede traer varios.
    notices = [
        _binding_notice(
            store, sources[0], None, subject,
            [item for item in observations if item.subject == subject],
        )
        for subject in sorted({item.subject for item in observations})
    ]
    return {
        "imported": len(entries),
        "by_indicator": dict(Counter(item.key for item in observations)),
        "binding_notices": [notice for notice in notices if notice],
        # Por indicador: la unidad del catalogo en que quedo la cifra, y cuantas lecturas la
        # declararon y cuantas no (se asumio, como en el alta manual).
        "units": units,
        "ledger_first": entries[0].index,
        "ledger_last": entries[-1].index,
    }
