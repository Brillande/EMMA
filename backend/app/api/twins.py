# SPDX-License-Identifier: AGPL-3.0-or-later
"""Las cinco preguntas de los gemelos (base de conocimiento §10) para un tripulante.

Por qué existe aparte de `/api/status`: la respuesta junta tres vistas que ya existen —el estado,
la tripulación frente al hábitat y lo que espera a una persona— y compone con ellas
(`app/twins.py`). Meterla dentro del estado haría que cada estado calculara también la vista de
toda la tripulación.

UN SOLO ESTADO POR PETICIÓN. `crew_status` sin `until` firma en el registro las instantáneas de
predicción (como mucho una por indicador y día). Aquí se llama una vez y lo que espera a una
persona se calcula sobre ESE estado con el mismo cableado que `/api/timeline/waiting`
(`waiting_for`), sin volver a pedirlo. La vista de tripulación usa `_assess`, que no firma nada.

LA CONSOLA DE TIERRA (`until`). Lo que Tierra puede saber en su corte, como `/api/status` y la
crónica con el retardo: el estado, la vista de tripulación y lo que espera a una persona se cortan
los tres con el mismo instante, y con él no se firma nada. Sin lecturas llegadas a Tierra no hay
estado (404), como en `/api/status`.

Lo que falte se dice en su pregunta, no tumba las otras: sin vista de tripulación, el hábitat sale
«no disponible»; sin la herramienta de Polaris que cuenta lo que espera, la capa de decisión.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException

from app import twins
from app.api.habitat import crew_overview, habitat_radiation
from app.api.routes import SettingsDep, StoreDep, crew_status
from app.api.timeline import waiting_for
from app.environment.donki import SolarEvent
from app.polaris import PolarisUnavailable

twins_router = APIRouter()


@twins_router.get("/twins")
def read_twins(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Las cinco preguntas de §10, literales, cada una con su respuesta y de dónde sale. Con
    `until`, con lo que Tierra tiene en su corte."""
    status = crew_status(
        settings, store, subject=subject, epoch=None, cumulative_dose_msv=None, until=until
    )
    try:
        crew: dict[str, Any] | None = crew_overview(store, settings, until=until)
    except HTTPException:
        crew = None
    try:
        pending: dict[str, Any] | None = waiting_for(status, store, subject, until)
    except PolarisUnavailable:
        pending = None
    # La radiacion del habitat, con el mismo corte, y con el evento solar de ESTE estado: sin
    # volver a pedirlo a DONKI, la nota no puede nombrar otro evento que el estado de al lado.
    event = status.get("active_solar_event")
    age = status.get("solar_data_age")
    solar = (
        SolarEvent.from_dict(event) if event else None,
        (age, status["solar_data_age_seconds"]) if age is not None else None,
    )
    radiation = habitat_radiation(store, settings, until, solar)
    return twins.compose(status, crew, pending, until, radiation)
