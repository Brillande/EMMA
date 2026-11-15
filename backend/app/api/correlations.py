"""`GET /api/correlations`: la correlación de los pares declarados de un tripulante.

Por qué existe: la tarjeta «Correlación de variables» de la pestaña «Distancia y nodos» necesita
r, n y la ventana de unas series reales, y `analysis/correlations.py` los calcula con su método
declarado. Ruta de solo lectura: no firma nada y nada del estado la lee (invariante 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analysis import correlations as method
from app.api.console_header import console_post
from app.api.routes import SettingsDep, StoreDep
from app.core.storage import ObservationStore
from app.ingest.codes import CATALOG
from app.interpret import correlation_reading
from app.interpret.llm import LocalLlm

correlations_router = APIRouter()


@correlations_router.get("/correlations")
def read_correlations(
    store: StoreDep,
    subject: str = "crew-01",
    # La referencia del estado (o el corte de Tierra): la ventana acaba ahí. Sin ella, ahora.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    reference = until if until is not None else dt.datetime.now(dt.UTC)
    since = reference - dt.timedelta(days=method.WINDOW_DAYS)
    series = {
        key: store.query(subject, key=key, since=since, until=reference)
        for key in method.pair_keys()
    }
    return {"subject": subject, **method.correlations(series, reference)}


def _reference(until: dt.datetime | None) -> dt.datetime:
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    return until if until is not None else dt.datetime.now(dt.UTC)


def _search(
    store: ObservationStore, subject: str, reference: dt.datetime, domain: str | None
) -> dict[str, Any]:
    if domain is not None and domain not in {code.domain.value for code in CATALOG.values()}:
        raise HTTPException(status_code=422, detail=f"dominio desconocido: {domain!r}")
    since = reference - dt.timedelta(days=method.WINDOW_DAYS)
    series = {key: store.query(subject, key=key, since=since, until=reference) for key in CATALOG}
    return {"subject": subject, **method.search(series, reference, domain=domain)}


@correlations_router.get("/correlations/search")
def search_correlations(
    store: StoreDep,
    subject: str = "crew-01",
    until: dt.datetime | None = None,
    # Con dominio, solo los pares que tocan al menos un indicador suyo (la pestaña «Aislamiento»
    # pide `behavioral`).
    domain: str | None = None,
) -> dict[str, Any]:
    """La búsqueda automática de pares (estadística): los de mayor |r|, con cuántos se miraron."""
    return _search(store, subject, _reference(until), domain)


class ReadingRequest(BaseModel):
    subject: str = "crew-01"
    until: dt.datetime | None = None
    domain: str | None = None


# Con la cabecera de la consola: otra página del navegador no puede poner el modelo a trabajar.
@correlations_router.post("/correlations/reading", **console_post())
def correlation_reading_draft(
    store: StoreDep, settings: SettingsDep, body: ReadingRequest
) -> dict[str, Any]:
    """La lectura del modelo local sobre la búsqueda (borrador de Clase C, no se guarda).

    Las cifras se recalculan aquí, no se reciben: el modelo solo puede leer lo que EMMA calculó.
    """
    result = _search(store, body.subject, _reference(body.until), body.domain)
    try:
        llm = LocalLlm(settings.llm_url, settings.llm_model)
    except ValueError as exc:  # una URL que no es de loopback
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"subject": body.subject, **correlation_reading.read(llm, result)}
