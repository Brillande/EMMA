"""Correlación de Pearson entre pares declarados de indicadores de un mismo tripulante.

POR QUÉ EXISTE
--------------
La maqueta de la ISS del equipo (lote «reservas», 2026-11-14) trae una tarjeta «Correlación de
variables» con pares como radiación-inmunidad o nutrición-desempeño y su r. EMMA no calculaba
ninguna correlación entre series: `analysis/context.py` ordena hipótesis de causa compartida
entre tripulantes y hábitat, y `alert_context.py` cuenta qué cambió alrededor de una alerta, pero
ninguno da un r. La tarjeta no se podía llenar sin inventar cifras, así que aquí se calcula, con
el método declarado y sus límites a la vista, y nada más lo lee.

MÉTODO
------
- Pares cerrados (`PAIRS`): los temas de la maqueta llevados a indicadores del catálogo. Se miran
  porque el equipo los propuso; EMMA no afirma que exista relación entre ellos.
- Solo lecturas MEDIDAS del tripulante pedido (lo inferido o predicho es salida de un modelo).
- Ventana de `WINDOW_DAYS` días hasta la referencia. Cada serie se reduce a su media por día UTC,
  para que un indicador con 24 lecturas al día no pese 24 veces más que uno diario; se emparejan
  los días con las dos medias.
- r de Pearson con al menos `MIN_DAYS` días emparejados; intervalo del 95 % por la transformación
  de Fisher (`atanh`). Sin p-valor: con varios pares, alguno sale alto por azar, y se dice.
- Una serie sin variación en la ventana no tiene r: se dice «sin variación», no se da un cero.

LO QUE NO ES
------------
Correlación no es causa. No entra en el análisis, en el riesgo, en las alertas ni en las
recomendaciones: ningún módulo del motor importa este (lo vigila `tests/test_correlations.py`).
Con series simuladas, el r es el del modelo del simulador, no fisiología, y la respuesta lo dice.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core import display, i18n
from app.ingest.codes import CATALOG
from app.ingest.fhir import EvidenceContext, ObservationType, VitalObservation

WINDOW_DAYS = 30
MIN_DAYS = 10
# z de la normal para el 95 % bilateral.
Z_95 = 1.959964
# Versión del cálculo: cambia si cambia el método, para que una cifra se pueda reproducir.
METHOD_VERSION = "pearson-daily-means-1"

METHOD = (
    f"r de Pearson entre las medias diarias (UTC) de dos indicadores del mismo tripulante, "
    f"solo lecturas medidas, en los {WINDOW_DAYS} días hasta la referencia; hacen falta "
    f"{MIN_DAYS} días con las dos series. Intervalo del 95 % por la transformación de Fisher."
)
SCOPE = (
    "Correlación, no causa. Descriptivo: no entra en el análisis, en el riesgo, en las alertas "
    "ni en las recomendaciones."
)
MULTIPLE = (
    "Se miran varios pares a la vez: alguno puede salir alto por azar. Un r sin su n y su "
    "intervalo no dice nada."
)
SIMULATED_TEXT = (
    "Series simuladas: el r es el del modelo del simulador, no fisiología medida."
)
PAIRS_BASIS = (
    "Pares propuestos en la maqueta del equipo y llevados a indicadores del catálogo. EMMA no "
    "afirma que estén relacionados: se mira si covarían en este tripulante."
)
i18n.en_many({
    METHOD: (
        f"Pearson's r between the daily means (UTC) of two indicators of the same crew member, "
        f"measured readings only, over the {WINDOW_DAYS} days up to the reference; "
        f"{MIN_DAYS} days with both series are needed. 95 % interval by the Fisher "
        f"transformation."
    ),
    SCOPE: (
        "Correlation, not cause. Descriptive: it does not enter the analysis, the risk, the "
        "alerts or the recommendations."
    ),
    MULTIPLE: (
        "Several pairs are looked at together: one of them may come out high by chance. An r "
        "without its n and its interval says nothing."
    ),
    SIMULATED_TEXT: (
        "Simulated series: the r is that of the simulator's model, not measured physiology."
    ),
    PAIRS_BASIS: (
        "Pairs proposed in the team's mock-up and mapped to indicators of the catalogue. EMMA "
        "does not claim they are related: it looks at whether they covary in this crew member."
    ),
})


@dataclass(frozen=True)
class Pair:
    """Un par que se mira: dos claves del catálogo y el tema de la maqueta del que sale."""

    x: str
    y: str
    theme: str


PAIRS: tuple[Pair, ...] = (
    Pair("absorbed-dose-rate", "latent-virus-shedding", "radiación e inmunidad"),
    Pair("energy-intake-daily", "pvt-mean-rt", "nutrición y desempeño"),
    Pair("exercise-minutes", "dxa-lean-mass", "ejercicio y masa muscular"),
    Pair("sleep-duration", "pvt-mean-rt", "sueño y desempeño"),
    Pair("cortisol-salivary", "sleep-duration", "estrés y sueño"),
)
# El tema de cada par en inglés, en el orden de `PAIRS`.
i18n.en_many(dict(zip(
    (pair.theme for pair in PAIRS),
    (
        "radiation and immunity", "nutrition and performance", "exercise and muscle mass",
        "sleep and performance", "stress and sleep",
    ),
    strict=True,
)))


def pair_keys() -> list[str]:
    """Las claves que leen los pares, sin repetir, en su orden."""
    seen: list[str] = []
    for pair in PAIRS:
        for key in (pair.x, pair.y):
            if key not in seen:
                seen.append(key)
    return seen


def daily_means(
    readings: Iterable[VitalObservation], start: dt.datetime, end: dt.datetime
) -> dict[dt.date, float]:
    """Media por día UTC de las lecturas medidas en `[start, end]`."""
    sums: dict[dt.date, tuple[float, int]] = {}
    for item in readings:
        if item.observation_type != ObservationType.MEASURED:
            continue
        at = item.effective.astimezone(dt.UTC)
        if at < start or at > end or not math.isfinite(item.value):
            continue
        total, count = sums.get(at.date(), (0.0, 0))
        sums[at.date()] = (total + item.value, count + 1)
    return {day: total / count for day, (total, count) in sums.items()}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """r de Pearson; `None` si alguna serie no varía (no hay r, no es un cero)."""
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("dos series de la misma longitud, con dos puntos al menos")
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def fisher_interval(r: float, n: int) -> tuple[float, float]:
    """Intervalo del 95 % de r por Fisher; pide n > 3."""
    if n <= 3:
        raise ValueError("el intervalo de Fisher pide más de tres puntos")
    clipped = max(-0.999999, min(0.999999, r))
    z = math.atanh(clipped)
    half = Z_95 / math.sqrt(n - 3)
    # Con |r| = 1 el recorte deja el extremo un pelo por dentro: el intervalo siempre contiene r.
    return min(r, math.tanh(z - half)), max(r, math.tanh(z + half))


def _side(key: str) -> dict[str, Any]:
    code = CATALOG[key]
    return {
        "key": key,
        "display_es": code.display_es,
        "unit": code.unit,
        "decimals": display.decimals_for(key),
    }


def _simulated(readings: Iterable[VitalObservation]) -> bool:
    return any(item.evidence_context == EvidenceContext.SIMULATED for item in readings)


def pair_result(
    pair: Pair,
    xs: Sequence[VitalObservation],
    ys: Sequence[VitalObservation],
    reference: dt.datetime,
) -> dict[str, Any]:
    """Un par con su estado (`computed`, `insufficient`, `constant`), r, n, intervalo y puntos."""
    start = reference - dt.timedelta(days=WINDOW_DAYS)
    mx = daily_means(xs, start, reference)
    my = daily_means(ys, start, reference)
    days = sorted(set(mx) & set(my))
    points = [{"day": day.isoformat(), "x": mx[day], "y": my[day]} for day in days]
    n = len(days)
    used = [item for item in (*xs, *ys) if start <= item.effective.astimezone(dt.UTC) <= reference]
    base: dict[str, Any] = {
        "x": _side(pair.x),
        "y": _side(pair.y),
        "theme": i18n.loc(pair.theme),
        "n": n,
        "r": None,
        "ci_low": None,
        "ci_high": None,
        "points": points,
        "simulated": _simulated(used),
    }
    if n < MIN_DAYS:
        return {
            **base,
            "state": "insufficient",
            "text": i18n.tr(
                f"{display.number(n, 0)} {'día' if n == 1 else 'días'} con las dos series; "
                f"hacen falta {display.number(MIN_DAYS, 0)}.",
                f"{display.number(n, 0)} {'day' if n == 1 else 'days'} with both series; "
                f"{display.number(MIN_DAYS, 0)} are needed.",
            ),
        }
    r = pearson([mx[day] for day in days], [my[day] for day in days])
    if r is None:
        return {
            **base,
            "state": "constant",
            "text": i18n.tr(
                "Una de las dos series no varía en la ventana: no hay r.",
                "One of the two series does not vary in the window: there is no r.",
            ),
        }
    low, high = fisher_interval(r, n)
    return {
        **base,
        "state": "computed",
        "r": r,
        "ci_low": low,
        "ci_high": high,
        "text": i18n.tr(
            f"r = {display.number(r, 2)} (IC 95 %: {display.number(low, 2)} a "
            f"{display.number(high, 2)}; n = {display.number(n, 0)} días).",
            f"r = {display.number(r, 2)} (95 % CI: {display.number(low, 2)} to "
            f"{display.number(high, 2)}; n = {display.number(n, 0)} days).",
        ),
    }


def correlations(
    series: Mapping[str, Sequence[VitalObservation]], reference: dt.datetime
) -> dict[str, Any]:
    """Todos los pares, con el método, el alcance y la salvedad de las comparaciones múltiples."""
    if reference.tzinfo is None:
        raise ValueError("la referencia debe llevar zona horaria")
    reference = reference.astimezone(dt.UTC)
    pairs = [
        pair_result(pair, series.get(pair.x, ()), series.get(pair.y, ()), reference)
        for pair in PAIRS
    ]
    return {
        "reference_time": reference.isoformat(),
        "window_days": WINDOW_DAYS,
        "min_days": MIN_DAYS,
        "method": i18n.loc(METHOD),
        "method_version": METHOD_VERSION,
        "scope": i18n.loc(SCOPE),
        "multiple": i18n.loc(MULTIPLE),
        "pairs_basis": i18n.loc(PAIRS_BASIS),
        "simulated_text": i18n.loc(SIMULATED_TEXT),
        "pairs": pairs,
    }


# --------------------------------------------------------------------------- búsqueda automática
#
# POR QUÉ: la maqueta de aislamiento (2026-11-15) pone «Correlaciones Clave (IA)», y el usuario
# eligió que EMMA BUSQUE los pares sola en vez de mirar solo los cinco declarados («búsqueda
# automática + explicación IA»). Las cifras siguen saliendo de aquí, con el mismo método; el modelo
# de lenguaje solo las lee después (`interpret/correlation_reading.py`), nunca las calcula.
#
# Lo que la búsqueda añade al riesgo de las comparaciones múltiples se dice con su número: cuántos
# pares se miraron. Con decenas de pares, alguno sale alto por azar; por eso no hay p-valor ni
# «significativo», y cada par lleva su n y su intervalo.

SEARCH_LIMIT = 6
SEARCH_THEME = "búsqueda automática"
SEARCH_METHOD_VERSION = "pearson-daily-means-search-1"

# Dos medidas de la misma prueba covarían por construcción: no es un hallazgo.
SAME_SOURCE_PREFIXES: tuple[str, ...] = ("pvt-", "onsd-", "ijv-csa-", "hrv-")

# Un indicador derivado de otros (cociente, recuento y su porcentaje, la dosis y su integral)
# covaría con ellos por construcción.
CONSTRUCTED: frozenset[frozenset[str]] = frozenset(
    frozenset(pair)
    for pair in (
        ("systolic-bp", "diastolic-bp"),
        ("neutrophils", "neutrophils-percent"),
        ("lymphocytes", "lymphocytes-percent"),
        ("neutrophils-percent", "lymphocytes-percent"),
        ("neutrophil-lymphocyte-ratio", "neutrophils"),
        ("neutrophil-lymphocyte-ratio", "lymphocytes"),
        ("neutrophil-lymphocyte-ratio", "neutrophils-percent"),
        ("neutrophil-lymphocyte-ratio", "lymphocytes-percent"),
        ("bun-creatinine-ratio", "urea"),
        ("bun-creatinine-ratio", "creatinine"),
        ("hemoglobin", "hematocrit"),
        ("hemoglobin", "erythrocytes"),
        ("hematocrit", "erythrocytes"),
        ("mchc", "hemoglobin"),
        ("mchc", "hematocrit"),
        ("mch", "mcv"),
        ("absorbed-dose-rate", "cumulative-dose"),
        ("bilirubin-total", "bilirubin-direct"),
        ("sleep-duration", "sleep-efficiency"),
    )
)

SEARCH_BASIS = (
    "Búsqueda automática: se miran todos los pares de indicadores medidos del tripulante en la "
    "ventana y se enseñan los de mayor |r|. Se excluyen los que covarían por construcción (dos "
    "medidas de la misma prueba, o un indicador derivado de otro). EMMA no afirma que estén "
    "relacionados."
)
i18n.en_many({
    SEARCH_THEME: "automatic search",
    SEARCH_BASIS: (
        "Automatic search: all pairs of the crew member's measured indicators in the window are "
        "looked at and those with the highest |r| are shown. Those that covary by construction "
        "are excluded (two measures from the same test, or an indicator derived from another). "
        "EMMA does not claim they are related."
    ),
})


def constructed(a: str, b: str) -> bool:
    """Si el par covaría por construcción (misma prueba o uno derivado del otro)."""
    if frozenset((a, b)) in CONSTRUCTED:
        return True
    return any(a.startswith(prefix) and b.startswith(prefix) for prefix in SAME_SOURCE_PREFIXES)


def search(
    series: Mapping[str, Sequence[VitalObservation]],
    reference: dt.datetime,
    domain: str | None = None,
    limit: int = SEARCH_LIMIT,
) -> dict[str, Any]:
    """Los pares de mayor |r| entre todos los indicadores con lecturas; con `domain`, los que tocan
    al menos un indicador de ese dominio. Solo pares con r (los demás no se ordenan: no tienen
    cifra); el recuento de los mirados va en `tested`."""
    if reference.tzinfo is None:
        raise ValueError("la referencia debe llevar zona horaria")
    if limit < 1:
        raise ValueError("el límite es al menos 1")
    reference = reference.astimezone(dt.UTC)
    keys = sorted(key for key, readings in series.items() if key in CATALOG and readings)
    found: list[dict[str, Any]] = []
    tested = 0
    for index, a in enumerate(keys):
        for b in keys[index + 1:]:
            if constructed(a, b):
                continue
            domains = (CATALOG[a].domain.value, CATALOG[b].domain.value)
            if domain is not None and domain not in domains:
                continue
            result = pair_result(Pair(a, b, SEARCH_THEME), series[a], series[b], reference)
            if result["state"] != "computed":
                continue
            tested += 1
            found.append(result)
    found.sort(key=lambda item: (-abs(item["r"]), item["x"]["key"], item["y"]["key"]))
    return {
        "reference_time": reference.isoformat(),
        "window_days": WINDOW_DAYS,
        "min_days": MIN_DAYS,
        "method": i18n.loc(METHOD),
        "method_version": SEARCH_METHOD_VERSION,
        "scope": i18n.loc(SCOPE),
        "multiple": i18n.tr(
            f"Se miraron {display.number(tested, 0)} pares con r: entre tantos, alguno sale alto "
            "por azar. Un r sin su n y su intervalo no dice nada.",
            f"{display.number(tested, 0)} pairs with r were looked at: among so many, one or "
            "another comes out high by chance. An r without its n and its interval says nothing.",
        ),
        "pairs_basis": i18n.loc(SEARCH_BASIS),
        "simulated_text": i18n.loc(SIMULATED_TEXT),
        "domain": domain,
        "tested": tested,
        "pairs": found[:limit],
    }
