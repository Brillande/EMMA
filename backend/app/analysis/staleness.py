"""Cuando un dato externo deja de estar al dia: la regla vive aqui, no en la interfaz.

NASA-STD-3001 Vol 2, F.4.3.1 c: *"There must be an indication when data are stale."* El backend
ya declaraba la antiguedad de cada dato externo, pero **a partir de cuanto esta caducado** lo
decidia la interfaz (`frontend/src/lib/staleness.ts`), con tres limites escritos alli. Es una
regla que cambia lo que la tripulacion ve —un retardo con Tierra pintado como vigente o como
caducado— y estaba fuera del backend y de `rules_version`: alguien podia cambiar "6 horas" por
"6 dias" en un fichero de la interfaz sin que ningun estado lo declarase.

Los limites son los MISMOS que tenia la interfaz, traidos sin tocar:

- Efemerides: la distancia a Marte cambia despacio. De un dia a otro el retardo varia unos
  segundos; con una semana ya no es el de hoy.
- Meteorologia espacial: un evento de particulas solares se desarrolla en horas. Un dato de hace
  seis horas y uno de hace seis dias exigen decisiones distintas.
- Dosimetria: acumulada, cambia lentamente; se consulta por ventanas de dias.

DISENO DE EMMA, SIN FUENTE
--------------------------
La norma exige la indicacion, no dice cuando caduca cada dato. Los tres plazos son diseno de
EMMA: el razonamiento de arriba los motiva, ninguna fuente escrita en el repositorio los fija.
Se declara asi en cada respuesta (`basis`).

CONTRA QUE RELOJ
----------------
La antiguedad es la de la descarga (`CachedPayload.fetched_at`) frente al reloj del backend al
responder. No es el tiempo de los datos del tripulante: la pregunta es "¿cuando hablamos por
ultima vez con la fuente?", y eso lo sabe el ordenador que descargo, no las lecturas. La
interfaz no usaba su propio reloj (recibia los segundos ya contados), asi que traer la regla
aqui no cambia lo que se ve.

NO ENTRA EN EL VEREDICTO
------------------------
Que un dato externo este caducado no mueve niveles ni alertas (invariante 5): el motor usa el
dato que hay. Solo dice como de viejo es lo que se usa.
"""

from __future__ import annotations

import datetime as dt
import math
from enum import StrEnum
from typing import Any

from app.core import display, i18n


class ExternalSource(StrEnum):
    EPHEMERIS = "ephemeris"
    SPACE_WEATHER = "space-weather"
    DOSIMETRY = "dosimetry"


# Diseno de EMMA, sin fuente (ver cabecera). Entra en `rules_version`.
STALE_AFTER: dict[ExternalSource, dt.timedelta] = {
    ExternalSource.EPHEMERIS: dt.timedelta(days=7),
    ExternalSource.SPACE_WEATHER: dt.timedelta(hours=6),
    ExternalSource.DOSIMETRY: dt.timedelta(days=7),
}

BASIS = (
    "diseño de EMMA, sin fuente: NASA-STD-3001 Vol 2 F.4.3.1 c exige indicar el dato caducado "
    "y no fija el plazo. La antigüedad es la de la descarga frente al reloj del backend al "
    "responder; no cambia ningún nivel ni alerta"
)
i18n.en(
    BASIS,
    "EMMA design, with no source: NASA-STD-3001 Vol 2 F.4.3.1 c requires stale data to be "
    "indicated and does not set the time limit. The age is that of the download against the "
    "backend clock when answering; it changes no level or alert",
)


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    # Tabla F.5-1, "Missing or stale data": un dato ausente nunca se presenta como al dia.
    MISSING = "missing"

    @property
    def display(self) -> str:
        return i18n.tr(_FRESHNESS_DISPLAY[self], _FRESHNESS_DISPLAY_EN[self])


_FRESHNESS_DISPLAY: dict[Freshness, str] = {
    Freshness.FRESH: "al día",
    Freshness.STALE: "caducado",
    Freshness.MISSING: "sin dato",
}
# En inglés (`core/i18n.py`). Tabla aparte y no el registro de `i18n.en`: son palabras cortas que
# otro módulo puede usar con otro sentido.
_FRESHNESS_DISPLAY_EN: dict[Freshness, str] = {
    Freshness.FRESH: "up to date",
    Freshness.STALE: "stale",
    Freshness.MISSING: "no data",
}


def freshness(source: ExternalSource, age_seconds: float | None) -> Freshness:
    """`missing` sin antiguedad; `stale` solo pasado el plazo (justo en el plazo, al dia)."""
    if age_seconds is None or not math.isfinite(age_seconds):
        return Freshness.MISSING
    return (
        Freshness.STALE
        if age_seconds > STALE_AFTER[source].total_seconds()
        else Freshness.FRESH
    )


def _span(delta: dt.timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours >= 24 and hours % 24 == 0:
        return f"{display.number(hours / 24, 0)} d"
    return f"{display.number(hours, 0)} h"


def describe(source: ExternalSource, age_seconds: float | None) -> dict[str, Any]:
    """El veredicto de caducidad de un dato externo, listo para pintar."""
    state = freshness(source, age_seconds)
    limit = STALE_AFTER[source]
    return {
        "source": str(source),
        "state": str(state),
        "display": state.display,
        "is_current": state is Freshness.FRESH,
        "age_seconds": None if state is Freshness.MISSING else age_seconds,
        "stale_after_seconds": int(limit.total_seconds()),
        "stale_after_display": _span(limit),
    }
