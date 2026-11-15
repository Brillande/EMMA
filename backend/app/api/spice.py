"""Ruta del cálculo local de efemérides con SPICE (`environment/spice.py`): si está y qué da.

Módulo aparte para no tocar `api/routes.py` más que lo imprescindible. Solo GET y sin red: dice si
`spiceypy` está instalado, si los núcleos fijados están y pasan su comprobación, qué días cubre
para el objetivo del perfil vigente, con qué precedencia entra frente a JPL Horizons y, con
`epoch`, la ventana que calcularía ese día, contrastada con la efeméride de Horizons de ese día si
está en caché (sin pedir nada en vivo). Lo que decide (el retardo del estado) no sale de aquí: sale
de `EphemerisClient.comms_window`, con su precedencia (SPICE primero desde el 2026-11-11).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from typing import Any

from fastapi import APIRouter

from app.api.routes import SettingsDep, StoreDep
from app.core import i18n
from app.environment import spice
from app.environment.ephemeris import EphemerisClient
from app.evidence import mission_profiles

spice_router = APIRouter(prefix="/spice")


@spice_router.get("")
def read_spice(
    settings: SettingsDep, store: StoreDep, epoch: dt.date | None = None
) -> dict[str, Any]:
    """El estado de SPICE para el perfil vigente; con `epoch`, lo que calcularía ese día."""
    profile = store.mission_profile(None, settings.mission_profile)
    target = mission_profiles.ephemeris_target(str(profile["id"]), settings).target
    state = spice.availability(settings)
    span = None if target is None else spice.coverage_span(settings, target)
    body: dict[str, Any] = {
        **state.to_dict(),
        "source": i18n.loc(spice.source_label()) if state.available else None,
        "target": target,
        "observer": settings.observer_body,
        "supported_targets": {
            code: i18n.loc(why) for code, (_, why) in spice.TARGETS.items()
        },
        "span": None if span is None else {"start": span[0].isoformat(),
                                           "end": span[1].isoformat()},
        "precedence": i18n.loc(spice.PRECEDENCE),
        "contrast_policy": i18n.loc(spice.CONTRAST_POLICY),
        "declared_max_error": dict(spice.DECLARED_MAX_ERROR),
        "license": {"url": spice.RULES_URL, "read_on": spice.RULES_READ_ON,
                    "quotes": list(spice.RULES_QUOTES)},
        "window": None,
        "window_unavailable": None,
    }
    if epoch is not None:
        if target is None:
            body["window_unavailable"] = i18n.tr(
                f"el perfil vigente ({profile['id']!r}) no tiene objetivo de efemérides",
                f"the profile in force ({profile['id']!r}) has no ephemeris target",
            )
        else:
            try:
                local = spice.window(settings, epoch, target)
            except spice.SpiceUnavailable as exc:
                body["window_unavailable"] = str(exc)
            else:
                # El contraste con lo que haya de Horizons en caché ese día (sin red).
                found = EphemerisClient(settings=settings).cached(epoch, target)
                if found is not None:
                    cached, reference = found
                    local = replace(
                        local, contrast=spice.contrast(local, reference, cached.fetched_at)
                    )
                body["window"] = local.to_dict()
    return body
