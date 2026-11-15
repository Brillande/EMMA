"""Buscar en la documentación (`app/kb.py`) y exportar a PDF (`app/export.py`). Solo lectura."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool

from app import export, kb, timeline
from app.api import routes
from app.api.pain import list_pain_reports
from app.api.routes import SettingsDep, StoreDep, crew_status
from app.api.timeline import chronicle_view
from app.core import i18n
from app.evidence import dossier

knowledge_router = APIRouter()


@knowledge_router.get("/kb")
async def search_docs(
    q: Annotated[str, Query(min_length=2, max_length=200)],
    k: Annotated[int, Query(ge=1, le=20)] = 6,
) -> dict[str, Any]:
    """Pasajes de la documentación de EMMA con su fichero y sección, sin red."""
    # 503 si otro proceso tiene el índice más de lo que se le espera (`kb.RefreshBusyError`):
    # antes la petición esperaba sin tope (§5.38.10).
    try:
        return await run_in_threadpool(kb.search, q, k)
    except kb.RefreshBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@knowledge_router.get("/export/{kind}.pdf")
def export_pdf(
    kind: Literal["estado", "dosier", "cronica", "dolor"],
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    # Tierra exporta lo que Tierra tiene: estado y crónica hasta el corte del retardo (`/status`).
    until: dt.datetime | None = None,
) -> Response:
    """El estado, el dosier, la crónica o el dolor en PDF, fechado. Solo texto del backend."""
    now = dt.datetime.now(dt.UTC)
    if kind == "estado":
        status = crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None, until=until
        )
        markdown = export.status_markdown(status, now)
        title = i18n.tr(f"EMMA — estado de {subject}", f"EMMA — status of {subject}")
    elif kind == "dosier":
        markdown = export.dossier_markdown(dossier.status(), now)
        title = i18n.tr("EMMA — dosier", "EMMA — dossier")
    elif kind == "dolor":
        # Sin lecturas del tripulante, lo mismo que el estado: 404, no un PDF vacío. Los informes
        # son los de `/api/pain/reports`: mismo corte de Tierra y misma marca informativa.
        status = crew_status(
            settings, store, subject=subject, epoch=None, cumulative_dose_msv=None, until=until
        )
        markdown = export.pain_markdown(
            list_pain_reports(store, subject, until),
            subject,
            now,
            timeline.as_of(status, until, routes._now()).to_dict(),
            settings.mission_start,
            until,
        )
        title = i18n.tr(
            f"EMMA — anotaciones de dolor de {subject}", f"EMMA — pain notes of {subject}"
        )
    else:
        chronicle = chronicle_view(settings, store, subject, until)
        markdown = export.chronicle_markdown(chronicle, subject, now)
        title = i18n.tr(f"EMMA — crónica de {subject}", f"EMMA — chronicle of {subject}")
    try:
        pdf = export.to_pdf(markdown, title)
    except Exception as exc:  # noqa: BLE001 — sin PDF se dice, no se cae la consola
        raise HTTPException(status_code=503, detail=f"no se pudo generar el PDF: {exc}") from exc
    name = f"emma-{kind}-{subject}-{now:%Y%m%dT%H%M}Z.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
