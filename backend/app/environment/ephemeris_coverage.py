"""Qué días de la misión tienen efemérides en caché, y cuáles no.

Por qué existe: sin red, el modo nominal de misión (`EMMA_OFFLINE=true`), el retardo con Tierra y
la conjunción solar de un día salen de la efeméride de ese día en caché, o salen «sin dato». Hasta
la decimosexta ronda nadie decía de antemano qué días quedarían sin ella: se descubría el día en
que faltaba. La especificación pide «funcionar sin red una vez cargados los assets/datos» (§2) y
que el sistema «continúa funcionando con la red desactivada» (§14); el «Queda» de la conjunción
solar (§5.35.6 de `compliance/hmi-state-of-the-art.md`) lo dejó escrito: haría falta precargar la
caché de los días de la misión.

La precarga la hacen `scripts/preload_ephemeris.py` y `POST /api/comms/preload`, con
`EphemerisClient.preload` (una consulta por tramo que falte, por la puerta de salida). Aquí solo
se mira la caché, con una lectura de su carpeta (`EphemerisClient.cached_days`): no sale nada a
la red, y la cobertura se sirve en `/api/status` (`mission.ephemeris_coverage`).

Los días de la misión son los del lanzamiento (`mission_start`) al fin configurado
(`mission_start + mission_days`), ambos incluidos: el día del regreso también tiene retardo.
Es descriptivo: el retardo, el riesgo y las alertas no leen la cobertura, leen la efeméride del día.

Desde el 2026-11-11 la cobertura dice también qué días puede calcular SPICE en local
(`environment/spice.py`, bloque `spice`) y cuántos quedan sin ninguna de las dos (`offline_*`).
`state`, `covered` y `missing` siguen siendo los de la caché de Horizons.

SPICE PRIMERO (decisión del usuario, 2026-11-11): un día que SPICE calcula sale de SPICE, esté o
no en la caché de Horizons; la caché de ese día sirve de contraste. Un día que SPICE no calcula
sale de la caché de Horizons, si la tiene. `served_by` cuenta los días de cada fuente con la red
cortada, `spice.contrast_days` los que SPICE calcula y además tienen contraste, y la frase lo dice
en ese orden. Con SPICE cubriendo toda la misión, precargar Horizons ya no hace falta para el
retardo sin red: sirve de contraste y de respaldo, y `how_to_preload` lo dice
(`HOW_TO_PRELOAD_AS_CONTRAST`).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.core import display, i18n
from app.core.config import Settings
from app.environment import spice
from app.environment.ephemeris import EphemerisClient, day_runs, days_between, utc_today
from app.evidence import registry

COMPLETE = "complete"
PARTIAL = "partial"
NONE = "none"
STATES = (COMPLETE, PARTIAL, NONE)

# De dónde sale sin red el retardo del día del estado (`day.served_by`), y cómo se dice.
SPICE_SERVED = "spice"
HORIZONS_SERVED = "horizons_cache"
SERVED_TEXT: dict[str | None, str] = {
    SPICE_SERVED: "calculado en local (SPICE)",
    HORIZONS_SERVED: "en la caché de JPL Horizons",
    None: "sin efemérides: ni el cálculo local (SPICE) ni la caché de JPL Horizons",
}

# Cómo se precarga, dicho igual en el estado, en el guion y en la ruta. Texto plano: la consola
# lo enseña tal cual (`MissionProfileView`), y las comillas invertidas de Markdown que llevaba
# salían a la vista (decimoctava ronda, §5.38.9).
HOW_TO_PRELOAD = (
    "Se precargan con red, con una consulta a JPL Horizons por cada tramo de días que falte: "
    "con el guion backend/scripts/preload_ephemeris.py o con la orden POST /api/comms/preload "
    "del servidor, con la cabecera X-EMMA-Console: 1."
)

# Con SPICE cubriendo toda la misión (2026-11-11): la precarga no se quita, pero cambia de papel.
# Decisión: se mantiene porque es lo único que da contraste al cálculo local (la consulta diaria no
# pide nada en vivo para contrastar) y el respaldo si SPICE faltara (núcleos borrados, otro
# objetivo de perfil). La frase va en `preload_role` de la cobertura, en la ruta y en el guion.
PRELOAD_ROLE_WITH_SPICE = (
    "No hace falta para el retardo sin red: el cálculo local (SPICE) cubre todos los días de la "
    "misión. Precargar JPL Horizons sirve de contraste del cálculo local y de respaldo si SPICE "
    "faltara."
)
HOW_TO_PRELOAD_AS_CONTRAST = PRELOAD_ROLE_WITH_SPICE + " " + HOW_TO_PRELOAD
_HOW_TO_PRELOAD_EN = (
    "They are preloaded with network access, with one query to JPL Horizons for each stretch of "
    "missing days: with the script backend/scripts/preload_ephemeris.py or with the server "
    "command POST /api/comms/preload, with the header X-EMMA-Console: 1."
)
_PRELOAD_ROLE_WITH_SPICE_EN = (
    "Not needed for the offline delay: the local computation (SPICE) covers every day of the "
    "mission. Preloading JPL Horizons serves as a cross-check of the local computation and as a "
    "fallback if SPICE were missing."
)
i18n.en_many({
    SERVED_TEXT[SPICE_SERVED]: "computed locally (SPICE)",
    SERVED_TEXT[HORIZONS_SERVED]: "in the JPL Horizons cache",
    SERVED_TEXT[None]: (
        "no ephemeris: neither the local computation (SPICE) nor the JPL Horizons cache"
    ),
    HOW_TO_PRELOAD: _HOW_TO_PRELOAD_EN,
    PRELOAD_ROLE_WITH_SPICE: _PRELOAD_ROLE_WITH_SPICE_EN,
    HOW_TO_PRELOAD_AS_CONTRAST: _PRELOAD_ROLE_WITH_SPICE_EN + " " + _HOW_TO_PRELOAD_EN,
})

READ_ON = "2026-10-23"
CITATIONS = (
    {
        "ref": "jpl-horizons-api",
        "section": "Ephemeris-Specific Parameters: START_TIME, STOP_TIME, STEP_SIZE",
        "quote": "specifies ephemeris start time",
        "read_on": READ_ON,
    },
    {
        "ref": "jpl-horizons-api",
        "section": "Ephemeris-Specific Parameters: START_TIME, STOP_TIME, STEP_SIZE",
        "quote": "specifies ephemeris stop time",
        "read_on": READ_ON,
    },
)


def _validate() -> None:
    for cite in CITATIONS:
        registry.get(cite["ref"])


_validate()


def cited_refs() -> set[str]:
    """Las fichas del registro que cita la cobertura."""
    return {cite["ref"] for cite in CITATIONS}


def mission_span(settings: Settings) -> tuple[dt.date, dt.date]:
    """Del lanzamiento al fin configurado de la misión, ambos incluidos."""
    start = settings.mission_start
    return start, start + dt.timedelta(days=settings.mission_days)


def _runs(days: list[dt.date], covered: list[bool], value: bool) -> list[dict[str, Any]]:
    """Los tramos seguidos de días con `covered == value`.

    La misma definición de «tramo» que la precarga (`day_runs`): lo que aquí falta en un tramo
    es lo que la precarga pide junto.
    """
    selected = [day for day, flag in zip(days, covered, strict=True) if flag == value]
    return [
        {"start": first.isoformat(), "end": last.isoformat(), "days": (last - first).days + 1}
        for first, last in day_runs(selected)
    ]


def _days(count: int) -> str:
    if i18n.current() == "en":
        return f"{display.number(count, 0)} {'day' if count == 1 else 'days'}"
    return f"{display.number(count, 0)} {'día' if count == 1 else 'días'}"


def _spice_first_en(
    total: int, span: str, served: dict[str, int], contrasted: int, cached: int, label: str
) -> str:
    """`_spice_first` en inglés: las mismas ramas y las mismas cifras."""
    spice_days = served["spice"]
    if spice_days == total:
        head = f"Offline, the delay and the solar conjunction of the {_days(total)} of the mission"
    else:
        head = (
            f"Offline, the delay and the solar conjunction of {_days(spice_days)} of the "
            f"{_days(total)} of the mission"
        )
    text = f"{head} ({span}) are computed locally ({i18n.loc(label)})"
    rest = []
    if served["horizons_cache"]:
        rest.append(f"those of {_days(served['horizons_cache'])} come from the JPL Horizons cache")
    if served["none"]:
        rest.append(f"those of {_days(served['none'])} come out with no data")
    if rest:
        text += "; " + " and ".join(rest)
    if cached == 0:
        return (
            text + ". JPL Horizons has no day cached: the local computation has no cross-check."
        )
    verb = "serves" if contrasted == 1 else "serve"
    return (
        text + f". JPL Horizons has {_days(cached)} cached; {_days(contrasted)} {verb} as a "
        "cross-check of the local computation."
    )


def _text_en(
    state: str, total: int, covered: int, gaps: int, start: dt.date, end: dt.date,
    label: str, served: dict[str, int] | None, contrasted: int,
) -> str:
    """`_text` en inglés: las mismas ramas y las mismas cifras."""
    span = f"from {start.isoformat()} to {end.isoformat()}, launch and return included"
    if total == 0:
        return (
            f"The configured mission has no days (it starts on {start.isoformat()} and would "
            "end before): there is no ephemeris to preload. Check EMMA_MISSION_DAYS."
        )
    if served is not None and served["spice"] > 0:
        return _spice_first_en(total, span, served, contrasted, covered, label)
    if state == COMPLETE:
        return (
            f"The {_days(total)} of the mission ({span}) have ephemeris cached: offline, the "
            "delay and the solar conjunction of each day come from it."
        )
    local = "the delay and the solar conjunction come out with no data"
    if state == NONE:
        return (
            f"No day of the mission ({span}, {_days(total)}) has ephemeris cached: offline, "
            f"{local}."
        )
    stretches = "stretch" if gaps == 1 else "stretches"
    return (
        f"{display.number(covered, 0)} of the {_days(total)} of the mission ({span}) have "
        f"ephemeris cached; {_days(total - covered)} are missing in {display.number(gaps, 0)} "
        f"{stretches}, and offline on those days {local}."
    )


def _spice_first(
    total: int, span: str, served: dict[str, int], contrasted: int, cached: int, label: str
) -> str:
    """La frase con SPICE primero: de qué fuente sale cada día sin red y cuántos se contrastan."""
    spice_days = served["spice"]
    if spice_days == total:
        head = f"Sin red, el retardo y la conjunción solar de los {_days(total)} de la misión"
    else:
        head = (
            f"Sin red, el retardo y la conjunción solar de {_days(spice_days)} de los "
            f"{_days(total)} de la misión"
        )
    text = f"{head} ({span}) se calculan en local ({label})"
    rest = []
    if served["horizons_cache"]:
        rest.append(f"los de {_days(served['horizons_cache'])} salen de la caché de JPL Horizons")
    if served["none"]:
        rest.append(f"los de {_days(served['none'])} salen sin dato")
    if rest:
        text += "; " + " y ".join(rest)
    if cached == 0:
        return (
            text + ". JPL Horizons no tiene ningún día en caché: el cálculo local va sin contraste."
        )
    verb = "sirve" if contrasted == 1 else "sirven"
    return (
        text + f". JPL Horizons tiene {_days(cached)} en caché; {_days(contrasted)} {verb} de "
        "contraste del cálculo local."
    )


def _text(
    state: str, total: int, covered: int, gaps: int, start: dt.date, end: dt.date,
    label: str = "", served: dict[str, int] | None = None, contrasted: int = 0,
) -> str:
    if i18n.current() == "en":
        return _text_en(state, total, covered, gaps, start, end, label, served, contrasted)
    # El día del regreso cuenta (también tiene retardo) aunque `phase_at` ya lo llame posvuelo:
    # por eso son `mission_days + 1` días, y se dice cuáles para que no choque con la duración.
    span =f"del {start.isoformat()} al {end.isoformat()}, lanzamiento y regreso incluidos"
    if total == 0:
        return (
            f"La misión configurada no tiene ningún día (empieza el {start.isoformat()} y "
            "acabaría antes): no hay efemérides que precargar. Revisa EMMA_MISSION_DAYS."
        )
    if served is not None and served["spice"]:
        return _spice_first(total, span, served, contrasted, covered, label)
    if state == COMPLETE:
        return (
            f"Los {_days(total)} de la misión ({span}) tienen efemérides en caché: sin red, el "
            "retardo y la conjunción solar de cada día salen de ellas."
        )
    # Sin SPICE, la frase de siempre: los días sin caché salen sin dato.
    local = "el retardo y la conjunción solar salen sin dato"
    if state == NONE:
        return (
            f"Ningún día de la misión ({span}, {_days(total)}) tiene efemérides en caché: sin "
            f"red, {local}."
        )
    tramos = "tramo" if gaps == 1 else "tramos"
    return (
        f"{display.number(covered, 0)} de los {_days(total)} de la misión ({span}) tienen "
        f"efemérides en caché; faltan {_days(total - covered)} en {display.number(gaps, 0)} "
        f"{tramos}, y sin red esos días {local}."
    )


def _citation(cite: dict[str, str]) -> dict[str, Any]:
    ref = registry.get(cite["ref"])
    return {**cite, "title": ref.title, "url": ref.url}


def coverage(
    settings: Settings,
    client: EphemerisClient | None = None,
    day: dt.date | None = None,
    *,
    target: str,
) -> dict[str, Any]:
    """Qué días de la misión tiene la caché de efemérides. Sin red: solo mira el disco.

    `day` es el día cuya efeméride enseña quien pregunta (el `epoch` de `/api/status`, o hoy).
    `target` es el objetivo del perfil vigente (`mission_profiles.ephemeris_target`): un perfil
    sin objetivo no tiene cobertura que mirar, y quien pregunta no llama aquí.
    """
    client = client or EphemerisClient(settings=settings)
    start, end = mission_span(settings)
    days = days_between(start, end)
    # Una lectura de la carpeta para todos los días, no un `stat` por día (§5.37.12).
    covered = client.cached_days(days, target)
    count = sum(covered)
    missing = _runs(days, covered, False)
    # Una misión sin días (EMMA_MISSION_DAYS negativo) no está «completa»: no tiene nada.
    state = COMPLETE if days and count == len(days) else NONE if count == 0 else PARTIAL
    # Hoy en UT, como `_fetch_comms`: el día de las efemérides, no el del reloj local.
    day = day or utc_today()
    in_mission = start <= day <= end
    # Qué días puede calcular SPICE en local (`environment/spice.py`): sin `spiceypy` o sin sus
    # núcleos, ninguno, y el texto es el de siempre. Solo cuentan los que no están en caché.
    by_spice, spice_state, spice_span = spice.covered_days(settings, days, target)
    local_only = [s and not c for s, c in zip(by_spice, covered, strict=True)]
    offline = [s or c for s, c in zip(by_spice, covered, strict=True)]
    # SPICE primero: los días que calcula salen de él; los que no, de la caché de Horizons si la
    # tienen; y los demás, sin dato. Los que SPICE calcula y la caché tiene se contrastan.
    contrasted = sum(s and c for s, c in zip(by_spice, covered, strict=True))
    served = {
        "spice": sum(by_spice),
        "horizons_cache": sum(c and not s for s, c in zip(by_spice, covered, strict=True)),
        "none": len(days) - sum(offline),
    }
    spice_covers_all = bool(days) and served["spice"] == len(days)
    label = spice.source_label()
    # Lo mismo con la red cortada, sumando las dos fuentes (2026-11-11): la interfaz pintaba en cian
    # «sin efemérides en caché» días que SPICE calcula. `offline_state` y `day.served_by` dicen la
    # verdad del retardo sin red; `state` y `day.covered` siguen siendo los de la caché de Horizons.
    offline_count = sum(offline)
    offline_state = (
        COMPLETE if days and offline_count == len(days) else NONE if offline_count == 0
        else PARTIAL
    )
    day_cached = covered[(day - start).days] if in_mission else client.is_cached(day, target)
    day_by_spice = (
        by_spice[(day - start).days] if in_mission
        else spice_span is not None and spice_span[0] <= day <= spice_span[1]
    )
    day_served = SPICE_SERVED if day_by_spice else HORIZONS_SERVED if day_cached else None
    described: dict[str, Any] = {
        "state": state,
        "target": target,
        "observer": settings.observer_body,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": len(days),
        "covered_days": count,
        "missing_days": len(days) - count,
        "covered": _runs(days, covered, True),
        "missing": missing,
        # El día cuya efeméride enseña el estado (su `epoch`, o hoy: la misma regla que
        # `_fetch_comms`): si cae dentro de la misión y si está en caché. Antes del lanzamiento o
        # después del regreso, la cobertura de la misión no dice nada de él.
        "day": {
            "date": day.isoformat(),
            "in_mission": in_mission,
            "covered": day_cached,
            # Sin red, de dónde sale el retardo de ese día (SPICE primero), y cómo se dice.
            "offline_covered": day_served is not None,
            "served_by": day_served,
            "served_text": i18n.loc(SERVED_TEXT[day_served]),
        },
        "text": _text(
            state, len(days), count, len(missing), start, end, label, served, contrasted,
        ),
        # De qué fuente sale cada día con la red cortada, con SPICE primero (2026-11-11).
        "served_by": served,
        # El cálculo local con SPICE para los días sin caché (2026-11-11). `covered` son los días
        # de la misión que puede calcular, estén o no en caché; `local_only`, los que solo él
        # cubre. `offline_*`: lo que queda con la red cortada sumando las dos fuentes.
        "spice": {
            **spice_state.to_dict(),
            "source": i18n.loc(label) if spice_state.available else None,
            "span": (
                None if spice_span is None
                else {"start": spice_span[0].isoformat(), "end": spice_span[1].isoformat()}
            ),
            "covered_days": sum(by_spice),
            "covered": _runs(days, by_spice, True),
            "local_only_days": sum(local_only),
            # Días que SPICE calcula y que además tienen efeméride de Horizons en caché: los que
            # se contrastan (`spice.contrast`).
            "contrast_days": contrasted,
            "day_covered": day_by_spice,
            "declared_max_error": dict(spice.DECLARED_MAX_ERROR),
            "precedence": i18n.loc(spice.PRECEDENCE),
            "contrast_policy": i18n.loc(spice.CONTRAST_POLICY),
        },
        "offline_covered_days": offline_count,
        "offline_state": offline_state,
        "offline_missing": _runs(days, offline, False),
        "how_to_preload": (
            None if state == COMPLETE
            else HOW_TO_PRELOAD_AS_CONTRAST if spice_covers_all
            else HOW_TO_PRELOAD
        ),
        # Para qué sirve precargar Horizons con SPICE cubriendo toda la misión; `None` si no la
        # cubre (entonces la precarga sigue haciendo falta para los días que SPICE no calcula).
        "preload_role": PRELOAD_ROLE_WITH_SPICE if spice_covers_all else None,
        "note": i18n.tr(
            "Solo se dice: el retardo, el riesgo y las alertas leen la efeméride del día, no "
            "esta cobertura. Meter la caché precargada en el instalador no está hecho.",
            "Stated only: the delay, the risk and the alerts read the ephemeris of the day, not "
            "this coverage. Shipping the preloaded cache in the installer is not done.",
        ),
        "citations": [_citation(cite) for cite in CITATIONS],
    }
    # Las dos frases de la precarga se deciden arriba, cada una en su línea, y aquí se dicen en el
    # idioma de quien pide.
    for key in ("how_to_preload", "preload_role"):
        if described[key] is not None:
            described[key] = i18n.loc(described[key])
    return described
