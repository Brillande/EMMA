"""Distancias de la Tierra a la Luna y a Marte, y el retardo con Tierra de un perfil, sin red.

Por qué existe (petición del usuario, 2026-11-14, lote «reservas»): la fila «Distancia y
comunicaciones» de «Inicio» se adapta a la ubicación elegida (órbita baja, cislunar, Luna,
tránsito a Marte, Marte). `/api/status` solo trae el retardo del perfil DECLARADO (`comms_status`),
y la consola deja mirar cualquier otro perfil. Las cifras no pueden salir de la maqueta («Luna
384.400 km», «Marte 55 M - 401 M km») ni de una tabla escrita a mano: aquí salen del mismo cálculo
local con SPICE que da el retardo (`environment/spice.py`), con sus núcleos verificados.

Qué da, para un día y un perfil:

- **El retardo con Tierra del perfil** (`earth_link`), por el ÚNICO punto que da su objetivo
  (`mission_profiles.ephemeris_target`): sin objetivo, «no aplica», como `comms_status`; con él,
  SPICE y, si SPICE no calcula ese día, la efeméride de JPL Horizons de ese día en caché. No se
  pide nada a Horizons en vivo: esta vista no sale a la red, ni para un perfil que no está
  declarado.
- **La distancia geocéntrica de la Luna y de Marte** (`bodies`), centro a centro desde el
  geocentro, con su tiempo de luz de ida. La Luna es el cuerpo 301 del SPK planetario (`de432s`
  la trae); Marte, su baricentro (4), como en `spice.TARGETS` y por el mismo motivo. Es geometría,
  no el retardo de nadie: la Luna NO pasa a ser objetivo de efemérides por estar aquí (con la
  superficie lunar el retardo del perfil sigue «no aplica», y el riesgo sigue sin escalarse).
- **Dónde pone el perfil a la tripulación** (`crew_place`): solo cuando el nombre del perfil lo
  dice (órbita baja terrestre, superficie lunar, superficie de Marte). En cislunar y en tránsito a
  Marte la nave va entre dos cuerpos y EMMA no tiene su posición: se dice, no se estima.

Lo que NO hace: no escala el riesgo, no cambia niveles, umbrales ni alertas, no firma nada y no
escribe en el ledger (no es una observación de nadie). Ningún módulo de `analysis/` ni de
`advisor/` lo importa (lo fija `tests/test_distances.py`).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Any

from app.core import i18n
from app.core.config import Settings
from app.environment import spice
from app.environment.ephemeris import LIGHT_SECONDS_PER_AU, EphemerisClient
from app.evidence import mission_profiles

SCOPE = (
    "Descriptivo: no cambia el riesgo, los niveles, los umbrales ni las alertas, no firma nada y "
    "no sale a la red."
)
OBSERVER_TEXT = "desde el geocentro (centro de la Tierra), centro a centro"

AVAILABLE = "available"
NOT_APPLICABLE = "not_applicable"
MISSING = "missing"


@dataclass(frozen=True, slots=True)
class Body:
    """Un cuerpo cuya distancia geocéntrica se calcula con el SPK planetario."""

    id: str
    label: str
    spice_code: str
    note: str


BODIES: tuple[Body, ...] = (
    Body(
        "moon", "Luna", "301",
        "la Luna (cuerpo 301 del núcleo planetario)",
    ),
    Body(
        "mars", "Marte", "4",
        "Marte por su baricentro (el núcleo planetario pequeño no trae el centro del planeta, "
        "499): la diferencia es de decenas de centímetros",
    ),
)

# Dónde pone cada perfil a la tripulación, solo cuando su nombre lo dice (`display` del catálogo):
# «órbita baja terrestre», «superficie lunar», «superficie de Marte». Los otros dos van en ruta.
CREW_PLACE: dict[str, str | None] = {
    "leo": "earth",
    "cislunar": None,
    "lunar-surface": "moon",
    "mars-transit": None,
    "mars-surface": "mars",
}
CREW_PLACE_TEXT: dict[str, str] = {
    "earth": "En órbita baja de la Tierra.",
    "moon": "En la superficie de la Luna.",
    "mars": "En la superficie de Marte.",
}
EN_ROUTE_TEXT = (
    "En ruta: la nave va entre dos cuerpos y EMMA no tiene su posición; no se estima."
)
i18n.en_many({
    SCOPE: (
        "Descriptive: it does not change the risk, the levels, the thresholds or the alerts, "
        "signs nothing and does not go out to the network."
    ),
    OBSERVER_TEXT: "from the geocentre (centre of the Earth), centre to centre",
    "Luna": "Moon",
    "Marte": "Mars",
    BODIES[0].note: "the Moon (body 301 of the planetary kernel)",
    BODIES[1].note: (
        "Mars by its barycentre (the small planetary kernel does not carry the centre of the "
        "planet, 499): the difference is tens of centimetres"
    ),
    CREW_PLACE_TEXT["earth"]: "In low Earth orbit.",
    CREW_PLACE_TEXT["moon"]: "On the surface of the Moon.",
    CREW_PLACE_TEXT["mars"]: "On the surface of Mars.",
    EN_ROUTE_TEXT: (
        "En route: the spacecraft is between two bodies and EMMA does not have its position; "
        "it is not estimated."
    ),
})


def _measure(settings: Settings, epoch: dt.date, code: str) -> tuple[float, float]:
    """Distancia geocéntrica aparente (km) y tiempo de luz de ida (s) a las 00:00 UTC.

    Con el mismo cerrojo y los mismos núcleos verificados que el retardo (`spice.window`): CSPICE
    tiene un solo almacén por proceso. `SpiceUnavailable` si no se puede calcular.
    """
    state = spice.availability(settings)
    if not state.available or state.folder is None:
        raise spice.SpiceUnavailable(state.reason or "SPICE no disponible")
    sp = spice._spiceypy()
    assert sp is not None  # `availability` ya lo comprobó
    try:
        with spice._LOCK:
            spice._ensure_loaded(sp, state.folder)
            et = sp.str2et(f"{epoch.isoformat()} 00:00:00 UTC")
            position, light_seconds = sp.spkpos(code, et, spice.FRAME, "LT", "399")
    except Exception as exc:  # noqa: BLE001 - SPICE lanza sus propios errores
        raise spice.SpiceUnavailable(
            f"SPICE no pudo calcular el {epoch}: {spice._spice_error(exc)}"
        ) from exc
    distance = math.sqrt(sum(float(value) ** 2 for value in position))
    return distance, float(light_seconds)


def _checked(distance_km: float, seconds: float, epoch: dt.date) -> None:
    """La misma verificación cruzada que `spice.window`: el tiempo de luz frente a la distancia."""
    if not (math.isfinite(distance_km) and math.isfinite(seconds)) or distance_km <= 0:
        raise spice.SpiceUnavailable(f"SPICE dio para {epoch} una distancia no finita")
    expected = distance_km / spice.AU_KM * LIGHT_SECONDS_PER_AU
    if abs(expected - seconds) > spice.DECLARED_MAX_ERROR["one_way_seconds"]:
        raise spice.SpiceUnavailable(
            f"discrepancia en el tiempo de luz de SPICE para {epoch}: {seconds:.3f} s frente a "
            f"{expected:.3f} s desde la distancia"
        )


def body_row(settings: Settings, epoch: dt.date, body: Body) -> dict[str, Any]:
    """La distancia geocéntrica de un cuerpo ese día, o «sin dato» con el motivo."""
    base: dict[str, Any] = {
        "id": body.id, "label": i18n.loc(body.label), "note": i18n.loc(body.note),
    }
    try:
        distance, seconds = _measure(settings, epoch, body.spice_code)
        _checked(distance, seconds, epoch)
    except spice.SpiceUnavailable as exc:
        return {**base, "state": MISSING, "distance_km": None, "one_way_seconds": None,
                "source": None, "text": str(exc)}
    return {**base, "state": AVAILABLE, "distance_km": distance, "one_way_seconds": seconds,
            "source": i18n.loc(spice.source_label()), "text": None}


def earth_link(settings: Settings, epoch: dt.date, profile_id: str) -> dict[str, Any]:
    """El retardo con Tierra de un perfil ese día: SPICE, la caché de Horizons o «sin dato».

    Sin red: a diferencia de `/api/status`, no consulta Horizons en vivo, porque el perfil que se
    mira puede no ser el declarado. Sin objetivo de efemérides, «no aplica», con la frase de
    `mission_profiles`.
    """
    target = mission_profiles.ephemeris_target(profile_id, settings).target
    if target is None:
        return {"state": NOT_APPLICABLE, "target": None, "distance_km": None,
                "one_way_seconds": None, "source": None,
                "text": i18n.loc(mission_profiles.NO_TARGET_TEXT)}
    toward = i18n.loc(mission_profiles.KNOWN_TARGETS.get(target, target))
    try:
        window = spice.window(settings, epoch, target)
    except spice.SpiceUnavailable as exc:
        found = EphemerisClient(settings=settings).cached(epoch, target)
        if found is None:
            return {"state": MISSING, "target": target, "distance_km": None,
                    "one_way_seconds": None, "source": None,
                    "text": i18n.tr(
                        f"Sin efemérides de {toward} del {epoch.isoformat()}: {exc}. JPL "
                        "Horizons no lo tiene en caché y esta vista no sale a la red.",
                        f"No ephemeris of {toward} for {epoch.isoformat()}: {exc}. JPL "
                        "Horizons does not have it cached and this view does not go out to "
                        "the network.",
                    )}
        window = found[1]
    return {
        "state": AVAILABLE,
        "target": target,
        "distance_km": window.distance_au * spice.AU_KM,
        "one_way_seconds": window.one_way_minutes * 60.0,
        "source": i18n.loc(window.source),
        "text": i18n.tr(
            f"Hacia {toward}, el objetivo de efemérides de este perfil: el retardo es el de "
            f"la distancia Tierra-{toward}.",
            f"Towards {toward}, the ephemeris target of this profile: the delay is that of "
            f"the Earth-{toward} distance.",
        ),
    }


def describe(settings: Settings, epoch: dt.date, profile_id: str) -> dict[str, Any]:
    """Todo lo de la fila para un perfil y un día. Un perfil fuera del catálogo no se adivina."""
    profile = next(
        (item for item in mission_profiles.catalog()["profiles"] if item["id"] == profile_id),
        None,
    )
    state = spice.availability(settings)
    base: dict[str, Any] = {
        "profile": profile_id,
        "epoch": epoch.isoformat(),
        "scope": i18n.loc(SCOPE),
        "observer": i18n.loc(OBSERVER_TEXT),
        "spice": {"available": state.available, "reason": state.reason,
                  "source": i18n.loc(spice.source_label()) if state.available else None},
    }
    if profile is None:
        return {
            **base, "known": False, "display": None,
            "unknown_text": i18n.tr(
                f"El perfil {profile_id!r} no está en el catálogo de EMMA: no se "
                "calcula nada para él.",
                f"The profile {profile_id!r} is not in EMMA's catalogue: nothing is "
                "computed for it.",
            ),
            "crew_place": None, "earth_link": None, "bodies": [],
        }
    place = CREW_PLACE.get(profile_id)
    return {
        **base,
        "known": True,
        "display": profile["display"],
        "unknown_text": None,
        "crew_place": {"body": place,
                       "text": i18n.loc(
                           EN_ROUTE_TEXT if place is None else CREW_PLACE_TEXT[place]
                       )},
        "earth_link": earth_link(settings, epoch, profile_id),
        "bodies": [body_row(settings, epoch, body) for body in BODIES],
    }
