"""Un episodio que ya cesó no es una deriva en curso (§5.38.6, medido y sin adoptar).

La recta de 21 dias (`trend.py`) no sabe que paso dentro de su ventana: si el sueño cayo cuatro
dias y volvio, la recta sigue teniendo pendiente mientras contenga esos dias, y el estado lo
contaba en presente («bajando… a lo largo de 21 dias»). Medido con `transient-sleep-loss`
(§5.37.3): el episodio termina y el dominio conductual se queda en vigilancia hasta que sale de
la ventana.

Este modulo no inventa un criterio: junta los dos que el motor ya tiene. La via de desviacion
decide con su «ahora» (`CURRENT_WINDOW`) y su regla de persistencia
(`risk.representative_deviation`); la de tendencia, con su umbral de relevancia clinica. Una
tendencia que preocupa se da por **episodio cerrado** solo si las tres se cumplen (1 y 2 con las
desviaciones del indicador, como decide el estado; 3 con las lecturas del estrato de la recta):

1. un tramo anterior de la ventana tuvo hallazgo de desviacion en el sentido de la deriva (hubo
   episodio, no solo una deriva lenta dentro del rango personal: esa no se toca);
2. el tramo actual tiene lecturas y ningun hallazgo en ese sentido (sin lecturas no hay vuelta);
3. la mediana actual esta, en el sentido malo, a menos de lo que una deriva al ritmo de
   relevancia (`relevance_threshold` en `RELEVANCE_HORIZON_WEEKS`) habria movido el nivel en el
   tiempo transcurrido desde la mediana de antes del episodio. La base personal es movil: sin
   esta condicion, una deriva que salio de rango y siguio mientras la base la alcanzaba pareceria
   «de vuelta». Y escalada al tiempo, no el umbral entero: el umbral es lo que importa en cuatro
   semanas, y entre antes y ahora suelen pasar dos; sin escalar, una deriva viva por debajo del
   doble del umbral pasaba por «de vuelta» (lo cazo la revision de codigo, antes de medir).

No es un veto por el tramo final de la ventana: ese se probo en quince variantes y se descarto
(hallazgo 27 de `external-validation.md`). Ninguna fuente respalda la regla: es diseño.

MEDIDA, NO ADOPTADA. El usuario decidio (2026-10-26) medirla sin que cambie lo que decide el
motor. Por eso `trends_by_indicator` solo la aplica si alguien le pasa `settle`, y nadie que
decida se lo pasa: la usan la sombra de `/api/status` (`closed_episode_shadow`, que dice que
cerraria y que niveles cambiarian) y la validacion externa con `closed_episodes=True`. Adoptarla
es decision del usuario, con las dos metricas de §5.38.6 delante.
"""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import replace

from app.analysis.baseline import Deviation
from app.analysis.risk import representative_deviation
from app.analysis.trend import RELEVANCE_HORIZON_WEEKS, Direction, Settle, Trend
from app.core import i18n
from app.ingest.fhir import VitalObservation

# Como se lee la regla en la sombra de `/api/status`. Sin cifras: las da el codigo de abajo.
CLOSED_EPISODE_RULE = (
    "Medida, sin adoptar (§5.38.6): una tendencia preocupante se daría por episodio cerrado si "
    "un tramo anterior de su ventana tuvo hallazgo de desviación en su sentido, el tramo actual "
    "tiene lecturas sin ese hallazgo y el nivel ha vuelto al de antes del episodio."
)
# Quien la sirve (`api/routes.py`, la sombra de `/api/status`) la resuelve con `i18n.loc`.
i18n.en(
    CLOSED_EPISODE_RULE,
    "Measured, not adopted (§5.38.6): a concerning trend would be treated as a closed episode if "
    "an earlier stretch of its window had a deviation finding in its direction, the current "
    "stretch has readings without that finding, and the level has returned to the one before "
    "the episode.",
)


def closing(
    deviations: Iterable[Deviation],
    current_window: dt.timedelta,
) -> Settle:
    """El `settle` de `trends_by_indicator` con las desviaciones de esta evaluacion.

    Su «ahora» es el de `trends_by_indicator` (la ultima lectura). Solo para medir: ningun camino
    que decide lo usa (ver arriba).
    """
    by_key: dict[str, list[Deviation]] = {}
    for item in deviations:
        by_key.setdefault(item.key, []).append(item)
    for series in by_key.values():
        series.sort(key=lambda item: item.effective)

    def settle(trend: Trend, series: Sequence[VitalObservation], reference: dt.datetime) -> Trend:
        return close_if_finished(
            trend, series, by_key.get(trend.key, []), reference, current_window
        )

    return settle


def close_if_finished(
    trend: Trend,
    series: Sequence[VitalObservation],
    deviations: Sequence[Deviation],
    now: dt.datetime,
    current_window: dt.timedelta,
) -> Trend:
    """La tendencia marcada como episodio cerrado si cumple las tres condiciones; si no, igual.

    `deviations`, ordenadas por instante (las de `closing` lo estan).
    """
    if not trend.is_concerning or not series or current_window <= dt.timedelta(0):
        return trend
    sense = "high" if trend.direction is Direction.RISING else "low"
    start = min(obs.effective for obs in series)
    since = now - current_window
    # Las desviaciones del INDICADOR, de todos sus contextos: la via de desviacion decide asi
    # (`RiskEngine.assess` agrupa por clave). Medido en `transient-sleep-loss`: de los tres
    # estratos del PVT y de la eficiencia del sueño, solo el de reposo tuvo lecturas marcadas
    # durante el episodio; con las del estrato solo, la recta de sueño o actividad —que lo
    # sufrieron igual— no se cerraba y el estado acababa en vigilancia. El
    # precio, declarado en §5.38.6: un episodio en un contexto habilita (1) y (2) para otro, y lo
    # que queda de guarda es (3).
    moments = [item.effective for item in deviations]

    def between(low: dt.datetime, high: dt.datetime, closed: bool = False) -> Sequence[Deviation]:
        """Las desviaciones en `[low, high)`, o `[low, high]` si `closed`."""
        stop = (bisect.bisect_right if closed else bisect.bisect_left)(moments, high)
        return deviations[bisect.bisect_left(moments, low):stop]

    # 2. El estado lo ve de vuelta: lecturas de la recta en su «ahora» (sin ellas no hay vuelta:
    # un dato ausente no es una recuperacion) y ningun hallazgo en ese sentido.
    recent = [obs for obs in series if since <= obs.effective <= now]
    if not recent:
        return trend
    if _out_of_range(between(since, now, closed=True), sense):
        return trend

    # 1. Hubo episodio: tramos anteriores con hallazgo, contados hacia atras. `first_out` es el
    # inicio del mas antiguo de la racha mas reciente: el comienzo de ESTE episodio. Ni el ultimo
    # tramo con hallazgo (el «antes» incluiria el propio episodio y lo cerraria con facilidad)
    # ni el mas antiguo de la ventana (el «antes» seria el de otra excursion anterior, y con mas
    # tiempo transcurrido la condicion 3 permitiria mas). Lo cazo la revision de codigo.
    first_out: dt.datetime | None = None
    end = since
    while end > start:
        if _out_of_range(between(max(end - current_window, start), end), sense):
            first_out = end - current_window
        elif first_out is not None:
            break
        end -= current_window
    if first_out is None:
        return trend

    # 3. Ha vuelto a su nivel de antes del episodio, no a una base que lo ha seguido: lo que se
    # ha movido es menos de lo que una deriva al ritmo de relevancia habria movido en ese tiempo.
    before = [obs for obs in series if obs.effective < first_out]
    if not before:
        return trend
    shift = statistics.median(obs.value for obs in recent) - statistics.median(
        obs.value for obs in before
    )
    if sense == "low":
        shift = -shift
    elapsed_days = (_middle(recent) - _middle(before)).total_seconds() / 86400.0
    allowed = trend.relevance_threshold * elapsed_days / (RELEVANCE_HORIZON_WEEKS * 7.0)
    if shift >= allowed:
        return trend
    return replace(trend, closed_episode=True)


def _middle(readings: Sequence[VitalObservation]) -> dt.datetime:
    """El instante mediano de unas lecturas: donde «esta» su mediana en el tiempo."""
    ordered = sorted(obs.effective for obs in readings)
    return ordered[len(ordered) // 2]


def _out_of_range(block: Sequence[Deviation], sense: str) -> bool:
    """Hallazgo de la via de desviacion en ese tramo y en ese sentido (regla de persistencia)."""
    found = representative_deviation(block)
    return found is not None and found.direction == sense
