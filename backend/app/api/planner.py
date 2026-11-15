"""La base de datos de Marplanner, guardada en el ledger firmado de EMMA.

Por qué existe: Marplanner (`marplanner/`, copia literal) guarda todo en un fichero SQLite. El
usuario decidió (2026-11-12) que en EMMA ese almacén sea el mismo registro encadenado y firmado
que el resto: así sus datos tienen la misma auditoría y no hay un segundo almacén que se pueda
reescribir sin dejar rastro. Marplanner sigue usando SQLite, pero en memoria; cada transacción
sale como un changeset de sesión de SQLite y se anota aquí antes de responder al cliente. Al
arrancar, Marplanner reproduce los changesets en orden y su base vuelve a ser la del ledger.

Dos rutas: una anexa un changeset (409 si quien escribe no está al día; 422 si no es válido) y
otra los entrega en orden desde un número. Ninguna toca observaciones ni análisis.

Y una tercera, `POST /planner/fetch`: lo que Marplanner pide a internet (la cita del día, las
efemérides) no sale desde Node, sino por aquí y por `core/egress.py` (invariante 3 bis): la misma
lista blanca, el mismo modo sin red, el mismo modo seguro y la misma traza que el resto de EMMA.
Solo GET a un propósito `planner-*`; el puente de Node (`planner-bridge/register.mjs`) desvía su
`fetch` a esta ruta.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app import planner_ground, planner_link
from app.api.console_header import console_post
from app.api.routes import (
    SettingsDep,
    StoreDep,
    _read_capped,
    _recorded_or_422,
    identity_for,
)
from app.core import egress, identities
from app.core.storage import PlannerConflict

planner_router = APIRouter()

Writer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ChangesetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changeset: str = Field(min_length=1, description="Changeset de sesión de SQLite, en base64")
    # Cuántos changesets había reproducido quien escribe: si no son todos, su base está atrasada.
    expected: int = Field(ge=0)
    written_by: Writer = "marplanner"


@planner_router.post("/planner/changesets", status_code=201)
def append_changeset(store: StoreDep, payload: ChangesetIn) -> dict[str, Any]:
    """Anota una transacción de Marplanner. 409 si quien escribe no ha visto las anteriores."""
    try:
        entry = _recorded_or_422(
            lambda: store.record_planner_changeset(
                payload.changeset, payload.expected, payload.written_by,
                identity_for(identities.PLANNER_IDENTITY),
            )
        )[0]
    except HTTPException as exc:
        if isinstance(exc.__cause__, PlannerConflict):
            raise HTTPException(status_code=409, detail=exc.detail) from exc.__cause__
        raise
    return {"seq": payload.expected + 1, "ledger_index": entry.index}


@planner_router.get("/planner/changesets")
def read_changesets(
    store: StoreDep, after: Annotated[int, Query(ge=0)] = 0
) -> dict[str, Any]:
    """Los changesets posteriores a `after`, en orden, comprobados contra su huella firmada."""
    items = store.planner_changesets(after)
    return {"after": after, "count": len(items), "changesets": items}


# Lo que se devuelve de una respuesta de fuera: la hoja diaria no necesita más.
MAX_FETCH_BYTES = 2 * 1024 * 1024
PlannerPurpose = Literal["planner-quotes", "planner-onthisday"]


class FetchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: PlannerPurpose
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]


@planner_router.post("/planner/fetch")
def fetch_for_planner(payload: FetchIn, settings: SettingsDep) -> dict[str, Any]:
    """Un GET de Marplanner, por la puerta de EMMA. 403 fuera de lista; 503 sin red o en modo
    seguro; 502 si el sitio de fuera falla."""
    try:
        response = egress.get(settings, payload.purpose, payload.url)
    except egress.EgressNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except egress.EgressBlocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        return {"status": exc.response.status_code, "content_type": "", "body": ""}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"no se pudo leer: {exc}") from exc
    body = response.content[:MAX_FETCH_BYTES + 1]
    if len(body) > MAX_FETCH_BYTES:
        raise HTTPException(status_code=502, detail="respuesta demasiado grande")
    return {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "body": body.decode(response.encoding or "utf-8", errors="replace"),
    }


async def _forward(path: str, request: Request, body: bytes = b"") -> Response:
    """Reenvía a Marplanner. 403 fuera de su API de uso diario; 503 si no está arrancado. Lo
    demás, tal cual lo responde Marplanner. Sus escrituras van a su base, que es el ledger."""
    try:
        # En un hilo, no en el bucle: para responder, Marplanner escribe en el ledger de ESTE
        # proceso (`/planner/changesets`); con el bucle bloqueado esperando a Marplanner, ninguno
        # de los dos avanzaba hasta agotar el tiempo (visto el 2026-11-12 al probarlo de verdad).
        reply = await run_in_threadpool(
            planner_link.get_link().request,
            request.method, path, list(request.query_params.multi_items()), body or None,
            request.headers.get("content-type"),
        )
    except planner_link.PlannerPathRefused as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except planner_link.PlannerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(reply.body, status_code=reply.status, media_type=reply.content_type or None)


@planner_router.get("/planner/app/{path:path}")
async def planner_read(path: str, request: Request, store: StoreDep) -> Response:
    """Lee de la API de uso diario de Marplanner, para las pantallas de EMMA.

    Antes de leer, cada tripulante del registro tiene su miembro en el planificador
    (`planner_link.ensure_crew`): crew-01 es crew-01 también aquí.
    """
    # Si falla, la lectura de abajo dirá lo que pase.
    with contextlib.suppress(planner_link.PlannerUnavailable, ValueError):
        await run_in_threadpool(planner_link.get_link().ensure_crew, store.subjects())
    return await _forward(path, request)


# El cuerpo pasa tal cual, sin validar como JSON. Un POST así lo podría mandar otra página del
# navegador como petición simple: exige la cabecera de la consola (`api/console_header.py`) y
# declara su cuerpo en OpenAPI, como las importaciones. PUT, PATCH y DELETE nunca son peticiones
# simples: el navegador pregunta antes (`OPTIONS`) y el CORS de `main.py` las deniega.
# El cuerpo se lee con tope (`_read_capped`): el de Marplanner nunca pasa de unos KB.
MAX_PLANNER_BODY = 256 * 1024
_RAW_JSON_BODY = {
    "requestBody": {
        "required": False,
        "content": {"application/json": {"schema": {"description": "Para Marplanner, tal cual"}}},
    }
}


@planner_router.post("/planner/app/{path:path}", **console_post(**_RAW_JSON_BODY))
async def planner_post(path: str, request: Request) -> Response:
    """Crea en Marplanner (completar una tarea, un evento, una comida…)."""
    return await _forward(path, request, await _read_capped(request, MAX_PLANNER_BODY))


@planner_router.api_route("/planner/app/{path:path}", methods=["PUT", "PATCH", "DELETE"])
async def planner_change(path: str, request: Request) -> Response:
    """Cambia o borra en Marplanner."""
    return await _forward(path, request, await _read_capped(request, MAX_PLANNER_BODY))


@planner_router.get("/planner/ground-summary")
def ground_summary(
    store: StoreDep,
    until: dt.datetime | None = None,
    days: Annotated[int, Query(ge=1, le=planner_ground.MAX_DAYS)] = 7,
) -> dict[str, Any]:
    """Lo que Tierra ve del planificador: un resumen por miembro y día hasta el corte del retardo.

    Sin `until`, hasta ahora (a bordo). 503 si no se puede calcular (sin Node o sin Marplanner).
    """
    cut = until if until is not None else dt.datetime.now(dt.UTC)
    if cut.tzinfo is None:
        raise HTTPException(status_code=422, detail="until tiene que llevar zona horaria")
    try:
        return planner_ground.summarize(store.planner_changesets(), cut, days)
    except planner_ground.SummaryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
