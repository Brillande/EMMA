"""Recuperacion posvuelo: linea base prevuelo → desviacion → trayectoria → vuelta.

La especificacion del equipo (§10) termina su linea temporal en "postflight/recovery", y la
base de conocimiento insiste en que el seguimiento no acaba al aterrizar: un parametro que
cambia mucho en vuelo pero se recupera en dias no significa lo mismo que otro que sigue
alterado meses despues. Con las analiticas reales de Inspiration4 (OSD-569: L-92, L-44, L-3,
R+1, R+45, R+82) EMMA puede ensenar esa trayectoria sin inventar nada.

Descriptivo y declarado: la referencia es la media y el rango de las tomas prevuelo del propio
tripulante; cada toma posvuelo dice cuanto se separa y si cae dentro de ese rango. No hay
umbral clinico ni veredicto de "recuperado": con tres o cuatro tomas prevuelo, el rango es
estrecho y la conclusion la saca una persona.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable
from typing import Any

from app.core import display, i18n
from app.ingest import inspiration4
from app.ingest.codes import get
from app.ingest.fhir import VitalObservation


def flight(
    observations: Iterable[VitalObservation], mission_start: dt.date, mission_days: int
) -> tuple[dt.datetime, dt.datetime, bool]:
    """Lanzamiento, regreso y si son los de un vuelo real reproducido.

    El lanzamiento es el inicio de misión configurado. Con el hemograma de Inspiration4 el
    regreso es tres días después, el de su vuelo; con otros datos, al final de la misión
    configurada. Una sola regla para el panel (`/replay/recovery`) y para la crónica: con dos,
    el mismo R+1 podía ser posvuelo en un sitio y día de misión en el otro.
    """
    launch = dt.datetime.combine(mission_start, dt.time(0, 0), tzinfo=dt.UTC)
    real = any(item.source == inspiration4.SOURCE for item in observations)
    days = inspiration4.MISSION_DAYS if real else mission_days
    return launch, launch + dt.timedelta(days=days), real


def days_after_landing(moment: dt.datetime, landing: dt.datetime) -> int:
    """El R+ de un instante posvuelo: días desde el regreso, redondeados. Uno para el panel, la
    crónica y los momentos del modo anatómico: con dos reglas, la misma toma tendría dos R+."""
    return round((moment - landing).total_seconds() / 86_400)


# Tomas prevuelo que hacen un rango: con una sola, "dentro del rango" sería "igual a esa toma".
MIN_PREFLIGHT_SAMPLES = 2


def split(
    observations: Iterable[VitalObservation], launch: dt.datetime, landing: dt.datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Los indicadores con tomas posvuelo, en orden de clave: los que tienen rango prevuelo propio
    (los de `recovery`) y los que no (`_unranged`). Una sola pasada para las dos listas: con dos,
    una toma podía caer en una y no en la otra, y la ruta agrupaba y ordenaba la historia dos
    veces.
    """
    by_key: dict[str, list[VitalObservation]] = {}
    for item in observations:
        by_key.setdefault(item.key, []).append(item)
    ranged: list[dict[str, Any]] = []
    unranged: list[dict[str, Any]] = []
    for key, series in sorted(by_key.items()):
        before = [item.value for item in series if item.effective < launch]
        after = sorted(
            (item for item in series if item.effective >= landing), key=lambda item: item.effective
        )
        # Sin posvuelo no hay recuperacion; sin al menos dos tomas prevuelo no hay rango, y se dice.
        if not after:
            continue
        if len(before) < MIN_PREFLIGHT_SAMPLES:
            unranged.append(_unranged(key, len(before), after, landing))
            continue
        mean = statistics.fmean(before)
        low, high = min(before), max(before)
        code = get(key)
        postflight = [
            {
                # El instante de la toma: la crónica la sitúa con él (`timeline.py`).
                "at": item.effective.isoformat(),
                "days_after_landing": days_after_landing(item.effective, landing),
                "value": item.value,
                "delta_pct": round(100 * (item.value - mean) / mean, 1) if mean else None,
                "within_preflight_range": low <= item.value <= high,
            }
            for item in after
        ]
        ranged.append({
            "key": key,
            "display": code.display,
            "display_es": code.display_es,
            "unit": code.unit,
            "observation_type": "measured",
            "preflight": {
                "samples": len(before), "mean": round(mean, 4),
                "low": round(low, 4), "high": round(high, 4),
            },
            "postflight": postflight,
            "return_to_range": return_to_range(postflight),
        })
    return ranged, unranged


def recovery(
    observations: Iterable[VitalObservation], launch: dt.datetime, landing: dt.datetime
) -> list[dict[str, Any]]:
    return split(observations, launch, landing)[0]


def _tomas(amount: int, one: str, many: str) -> str:
    """«la toma siguiente» o «las 3 tomas siguientes»: `many` lleva `{n}` donde va la cifra."""
    return one if amount == 1 else many.format(n=display.number(amount, 0))


def return_to_range(postflight: list[dict[str, Any]]) -> dict[str, Any]:
    """Cuándo vuelve y si vuelve: lo que la conversación de ideación preguntaba de la recuperación
    («¿cuánto tarda en volver al baseline? ¿Vuelve completamente?»), dicho con las tomas que hay.

    Tres hechos, en la escala de días R+ de cada toma (`days_after_landing`): el primer R+ con la
    toma dentro del rango prevuelo propio; si las tomas siguientes se mantienen dentro; y si la
    última sigue fuera («sin volver»). No es una tasa de recuperación (con tres o cuatro tomas
    posvuelo no hay curva que ajustar, y la conversación la pedía sin dar cómo medirla) ni un
    veredicto: entre dos tomas no se sabe qué pasó, y la frase solo cuenta lo tomado.

    Se cuenta por tomas y se sitúa en días: con varias tomas en un mismo R+, la frase dice cuántas
    y no «hasta R+1; vuelve en R+1», que se contradiría.

    `postflight` es la lista de `recovery`: en orden de instante y no vacía.
    """
    days = [sample["days_after_landing"] for sample in postflight]
    inside = [bool(sample["within_preflight_range"]) for sample in postflight]
    last = days[-1]
    first = next((index for index, within in enumerate(inside) if within), None)
    if first is None:
        span = (
            f"su única toma posvuelo, R+{days[0]}, cae fuera"
            if len(days) == 1
            else f"ninguna de sus {display.number(len(days), 0)} tomas posvuelo "
            f"(R+{days[0]} a R+{last}) cae dentro"
        )
        return {
            "state": "not-back", "first_within_day": None, "held": None, "later_samples": 0,
            "within_since_day": None, "last_day": last,
            "text": (
                _never_back_en(days) if i18n.current() == "en"
                else f"Sin volver: {span} de su rango prevuelo."
            ),
        }
    later = len(inside) - first - 1
    out_after = [days[index] for index in range(first + 1, len(inside)) if not inside[index]]
    # El tramo final dentro: desde la toma siguiente a la última que cayó fuera.
    start: int | None = None
    if inside[-1]:
        start = len(inside) - 1
        while start > 0 and inside[start - 1]:
            start -= 1
    since = None if start is None else days[start]
    head = (
        f"Dentro de su rango prevuelo en la primera toma posvuelo, R+{days[first]}"
        if first == 0
        else "Fuera de su rango prevuelo en "
        f"{_tomas(first, 'la primera toma posvuelo', 'las {n} primeras tomas posvuelo')}; "
        f"vuelve dentro en R+{days[first]}"
    )
    if later == 0:
        tail = "; no hay tomas posteriores."
    elif not out_after:
        tail = (
            f"; se mantiene dentro en "
            f"{_tomas(later, 'la toma siguiente', 'las {n} tomas siguientes')}, hasta R+{last}."
        )
    else:
        where = _tomas(len(out_after), "una toma fuera después", "{n} tomas fuera después")
        where += (
            f", en R+{out_after[0]}" if out_after[0] == out_after[-1]
            else f", entre R+{out_after[0]} y R+{out_after[-1]}"
        )
        if start is None:
            end = f"; la última toma, R+{last}, sigue fuera: sin volver."
        else:
            final = len(inside) - start
            end = (
                f"; dentro de nuevo en la última toma, R+{since}." if final == 1
                else f"; dentro de nuevo en las {display.number(final, 0)} últimas tomas, "
                f"desde R+{since}."
            )
        tail = f"; no se mantiene: {where}{end}"
    return {
        "state": "not-back" if since is None else ("within" if not out_after else "back-again"),
        "first_within_day": days[first],
        "held": None if later == 0 else not out_after,
        "later_samples": later,
        "within_since_day": since,
        "last_day": last,
        "text": (
            _back_en(days, first, out_after, start) if i18n.current() == "en" else head + tail
        ),
    }


def _samples_en(amount: int, one: str, many: str) -> str:
    """`_tomas` en inglés: «the next sample» o «the next 3 samples»."""
    return one if amount == 1 else many.format(n=display.number(amount, 0))


def _never_back_en(days: list[int]) -> str:
    """La frase de `return_to_range` cuando ninguna toma posvuelo cae dentro, en inglés."""
    if len(days) == 1:
        return (
            f"Not back: their only postflight sample, R+{days[0]}, falls outside their "
            f"preflight range."
        )
    return (
        f"Not back: none of their {display.number(len(days), 0)} postflight samples "
        f"(R+{days[0]} to R+{days[-1]}) falls within their preflight range."
    )


def _back_en(days: list[int], first: int, out_after: list[int], start: int | None) -> str:
    """La frase de `return_to_range` cuando alguna toma cae dentro, en inglés.

    Recibe lo que `return_to_range` ya contó (la primera toma dentro, las que caen fuera después
    y dónde empieza el tramo final dentro): aquí solo se redacta, no se vuelve a contar.
    """
    last = days[-1]
    later = len(days) - first - 1
    opening = (
        f"Within their preflight range at the first postflight sample, R+{days[first]}"
        if first == 0
        else "Outside their preflight range at "
        + _samples_en(first, "the first postflight sample", "the first {n} postflight samples")
        + f"; back within it at R+{days[first]}"
    )
    if later == 0:
        return opening + "; there are no later samples."
    if not out_after:
        held = _samples_en(later, "the next sample", "the next {n} samples")
        return opening + f"; it stays within it at {held}, up to R+{last}."
    where = _samples_en(
        len(out_after), "one sample outside afterwards", "{n} samples outside afterwards"
    )
    where += (
        f", at R+{out_after[0]}" if out_after[0] == out_after[-1]
        else f", between R+{out_after[0]} and R+{out_after[-1]}"
    )
    if start is None:
        closing = f"; the last sample, R+{last}, is still outside: not back."
    else:
        final = len(days) - start
        closing = (
            f"; within it again at the last sample, R+{days[start]}." if final == 1
            else f"; within it again at the last {display.number(final, 0)} samples, "
            f"since R+{days[start]}."
        )
    return opening + f"; it does not stay within it: {where}{closing}"


def _unranged(
    key: str, preflight: int, after: list[VitalObservation], landing: dt.datetime
) -> dict[str, Any]:
    """Un indicador con tomas posvuelo y sin rango prevuelo propio: se dice, no se supone.

    Antes desaparecía del panel sin más, y un indicador ausente se lee como «nada que contar».
    Sin rango no hay dentro ni fuera, así que no lleva tomas comparadas: solo cuántas hay, entre
    qué R+, y por qué no se comparan.
    """
    days = [days_after_landing(item.effective, landing) for item in after]
    code = get(key)
    reason = (
        "ninguna toma antes del lanzamiento" if not preflight
        else "una sola toma antes del lanzamiento, y EMMA pide "
        f"{display.number(MIN_PREFLIGHT_SAMPLES, 0)} para un rango"
    )
    taken = (
        f"su única toma posvuelo, R+{days[0]}, no se compara"
        if len(days) == 1
        else f"sus {display.number(len(days), 0)} tomas posvuelo (R+{days[0]} a "
        f"R+{days[-1]}) no se comparan"
    )
    return {
        "key": key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "observation_type": "measured",
        "preflight_samples": preflight,
        "postflight_samples": len(after),
        "first_day": days[0],
        "last_day": days[-1],
        "return_to_range": {
            "state": "no-preflight-range",
            "text": (
                _unranged_en(preflight, days) if i18n.current() == "en"
                else f"Sin rango prevuelo: {reason}; {taken}."
            ),
        },
    }


def _unranged_en(preflight: int, days: list[int]) -> str:
    """La frase de `_unranged` en inglés: por qué no hay rango y qué tomas no se comparan."""
    reason = (
        "no sample before launch" if not preflight
        else "only one sample before launch, and EMMA asks for "
        f"{display.number(MIN_PREFLIGHT_SAMPLES, 0)} for a range"
    )
    taken = (
        f"their only postflight sample, R+{days[0]}, is not compared"
        if len(days) == 1
        else f"their {display.number(len(days), 0)} postflight samples (R+{days[0]} to "
        f"R+{days[-1]}) are not compared"
    )
    return f"No preflight range: {reason}; {taken}."


BASIS = (
    "Referencia: media y rango de las tomas prevuelo del propio tripulante. Cada toma posvuelo "
    "dice cuánto se separa y si cae dentro de ese rango, y cada indicador, en qué R+ vuelve "
    "dentro, si se mantiene y si la última toma sigue fuera; no es un veredicto de recuperación "
    "ni una tasa."
)
# Quien la sirve (`api/replay.py`) la resuelve con `i18n.loc`.
i18n.en(
    BASIS,
    "Reference: mean and range of the crew member's own preflight samples. Each postflight "
    "sample says how far it is from them and whether it falls within that range, and each "
    "indicator, at which R+ it comes back within it, whether it stays and whether the last "
    "sample is still outside; it is not a recovery verdict or a rate.",
)
