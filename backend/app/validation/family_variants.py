"""Las variantes del respaldo de familia, medidas sin tocar el motor.

POR QUE EXISTE ESTE MODULO
--------------------------
`BaselineEngine.evaluate_rolling` deja al propio reposo fuera de su respaldo de familia, en contra
de lo que dice `Context.family` (hallazgo 29). La decimoquinta y decimosexta rondas midieron en
MMASH tres arreglos, y el usuario decidio el 2026-10-23 no adoptar ninguno hasta medirlos con
varias semanas por persona. Esto los mide. **Nada de aqui decide**: `evaluate_rolling` sigue siendo
la regla, `rules_version` no cambia, y la adopcion es decision del usuario.

Las variantes, como las dejo la rama `worktree-agent-a13145213e51ba902` (no fusionada):

- `CURRENT`: la regla vigente. Debe dar exactamente lo mismo que `evaluate_rolling`, y una prueba
  lo exige: es lo que hace creibles las demas filas.
- `FAMILY` (A): la familia es el estado exacto mas `FAMILY_FALLBACK`.
- `COVERED` (B): A, y solo si lo prestado cubre la hora de la lectura (`_covers`).
- `ALL_COVERED` (C): B, y ademas toda base personal, tambien la propia, tiene que cubrir la hora;
  si no, respaldo poblacional. Es lo que la literatura respalda llevado hasta el final (E1).

Los numeros de la cobertura (media hora, 5 lecturas) son de diseno de EMMA, fijados antes de medir
en MMASH y sin ajustar a LifeSnaps.

POR QUE ES UNA COPIA DEL BUCLE Y NO UN PARAMETRO DEL MOTOR
----------------------------------------------------------
Un parametro en `evaluate_rolling` seria tocar el motor para algo no adoptado. La copia usa la
graduacion real (`_grade_against_personal`, `_evaluate_against_population`): lo unico que difiere
es de que lecturas sale la base.

LA MEDIDA, Y EN QUE NO ES LA DE MMASH
-------------------------------------
- **Falsa alarma**: toda lectura de toda persona, con la misma definicion que `report.py`. Por
  dia ademas de por persona: en 24 h «sujetos marcados» es una foto; en ocho semanas, casi todo
  el mundo tendra algun dia marcado, y esa cifra sola no diria nada.
- **Sensibilidad**: el deterioro empieza en `onset_after` y la serie se corta `SEGMENT` despues.
  Solo cuenta quien tiene base delante (`MIN_BASE_READINGS`) y algo que perturbar (`MIN_PERTURBED`).
  En MMASH el fin del registro lo pone el conjunto; aqui, sin corte, una deriva de 15 lpm/dia
  sumaria 330 lpm en 22 dias.
- **El brazo simulado**: la misma persona y el mismo tramo sin deterioro. Con lecturas cada 5 min
  durante tres dias, «alguna lectura marcada» sale tambien sin deterioro en quien tenga una tasa
  de fondo; sin este brazo, una detección no se distinguiria del fondo. En MMASH no hacia falta
  tanto: el tramo era de horas.
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import statistics
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from app.analysis.baseline import (
    DEFAULT_ROLLING_LAG,
    DEFAULT_ROLLING_WINDOW,
    MIN_SAMPLES,
    BaselineEngine,
    Deviation,
    _grade_against_personal,
    compute_baseline,
)
from app.analysis.risk import RiskEngine, RiskLevel
from app.analysis.trend import Trend, trends_by_indicator
from app.ingest.codes import get
from app.ingest.fhir import Context, VitalObservation
from app.validation.episodes import group_episodes
from app.validation.injection import (
    InjectedSeries,
    Injection,
    Perturbation,
    acute_episode,
    inject,
    onset_after,
    progressive_tachycardia,
    tachycardia,
)
from app.validation.lifesnaps import HRV_RMSSD, LifeSnapsLoader, dataset_dir
from app.validation.report import STATE_WINDOW


class Variant(StrEnum):
    CURRENT = "vigente"
    FAMILY = "A"
    COVERED = "B"
    ALL_COVERED = "C"


# El estado y de quien toma prestado, derivado de `Context.family` como en la rama.
FAMILY_FALLBACK: dict[Context, tuple[Context, ...]] = {
    state: others
    for state in Context
    if (
        others := tuple(
            other for other in Context if other.family is state.family and other is not state
        )
    )
}
COVERAGE_HALF_WIDTH_US = 30 * 60 * 1_000_000
COVERAGE_MIN = -(-MIN_SAMPLES // 24)
_DAY_US = 86_400 * 1_000_000

Clocks = npt.NDArray[np.int64]


def _clock(moment: dt.datetime) -> int:
    """Microsegundos desde la medianoche UTC, el reloj de la regla de la rama."""
    clock = moment.astimezone(dt.UTC)
    return ((clock.hour * 60 + clock.minute) * 60 + clock.second) * 1_000_000 + clock.microsecond


def _covers(target: int, clocks: Clocks) -> bool:
    """Si al menos `COVERAGE_MIN` de esas horas estan a menos de media hora de `target`."""
    gap = np.abs(clocks - target)
    return int(np.count_nonzero(np.minimum(gap, _DAY_US - gap) <= COVERAGE_HALF_WIDTH_US)) >= (
        COVERAGE_MIN
    )


def evaluate(
    observations: Iterable[VitalObservation],
    variant: Variant,
    window: dt.timedelta = DEFAULT_ROLLING_WINDOW,
    lag: dt.timedelta = DEFAULT_ROLLING_LAG,
    judge_from: dt.datetime | None = None,
) -> list[Deviation]:
    """`evaluate_rolling` con la familia de `variant`, juzgando desde `judge_from`.

    Lo anterior a `judge_from` sigue en la base, pero no se juzga: la sensibilidad solo necesita
    el tramo del deterioro, y juzgar ocho semanas por cada inyeccion costaria horas.
    """
    engine = BaselineEngine()
    grouped: dict[tuple[str, str, Context], list[VitalObservation]] = {}
    families: dict[tuple[str, str, Context], list[VitalObservation]] = {}
    for obs in observations:
        grouped.setdefault((obs.subject, obs.key, obs.context), []).append(obs)
        if obs.context.family is not obs.context:
            families.setdefault((obs.subject, obs.key, obs.context.family), []).append(obs)
    for series in (*grouped.values(), *families.values()):
        series.sort(key=lambda item: item.effective)
    moments = {slot: [item.effective for item in series] for slot, series in grouped.items()}
    clocks: dict[tuple[str, str, Context], Clocks] = {}
    usable: dict[tuple[str, str, Context], npt.NDArray[np.bool_]] = {}
    if variant in (Variant.COVERED, Variant.ALL_COVERED):
        for slot, series in grouped.items():
            clocks[slot] = np.fromiter(
                (_clock(item.effective) for item in series), np.int64, len(series)
            )
            usable[slot] = np.fromiter(
                (not item.is_low_confidence for item in series), np.bool_, len(series)
            )

    results: list[Deviation] = []
    for slot, series in grouped.items():
        subject, key, state = slot
        times = moments[slot]
        code = get(key)
        start_index = 0
        end_index = 0
        for position, obs in enumerate(series):
            window_end = obs.effective - lag
            window_start = window_end - window
            while start_index < position and times[start_index] < window_start:
                start_index += 1
            while end_index < position and times[end_index] <= window_end:
                end_index += 1
            if judge_from is not None and obs.effective < judge_from:
                continue

            values = [
                item.value
                for item in series[start_index:end_index]
                if not item.is_low_confidence
            ]
            baseline = compute_baseline(key, values)
            from_family = False

            if not baseline.established:
                if variant is Variant.CURRENT:
                    relatives = families.get((subject, key, state.family))
                    if relatives:
                        wider = [
                            item.value
                            for item in relatives
                            if window_start <= item.effective <= window_end
                            and not item.is_low_confidence
                        ]
                        if len(wider) > len(values):
                            baseline = compute_baseline(key, wider)
                else:
                    borrowed: list[float] = []
                    near: list[Clocks] = []
                    for other in FAMILY_FALLBACK.get(state, ()):
                        other_slot = (subject, key, other)
                        relatives = grouped.get(other_slot)
                        if not relatives:
                            continue
                        lower = bisect.bisect_left(moments[other_slot], window_start)
                        upper = bisect.bisect_right(moments[other_slot], window_end)
                        borrowed += [
                            item.value
                            for item in relatives[lower:upper]
                            if not item.is_low_confidence
                        ]
                        if variant is not Variant.FAMILY:
                            near.append(
                                clocks[other_slot][lower:upper][usable[other_slot][lower:upper]]
                            )
                    if borrowed and (
                        variant is Variant.FAMILY
                        or _covers(_clock(obs.effective), np.concatenate(near))
                    ):
                        baseline = compute_baseline(key, values + borrowed)
                        from_family = True

            personal = baseline.established
            if personal and variant is Variant.ALL_COVERED and not from_family:
                own = clocks[slot][start_index:end_index][usable[slot][start_index:end_index]]
                personal = _covers(_clock(obs.effective), own)

            if personal:
                severity, direction, basis, limit = _grade_against_personal(obs, baseline, code)
                results.append(
                    Deviation(
                        subject=obs.subject, key=key, value=obs.value, effective=obs.effective,
                        z_score=baseline.z_score(obs.value), severity=severity,
                        direction=direction, baseline=baseline, used_population_range=False,
                        basis=basis, danger_limit=limit,
                    )
                )
            else:
                results.append(engine._evaluate_against_population(obs, code, baseline))
    return results


# --------------------------------------------------------------------------- #
# La medida
# --------------------------------------------------------------------------- #

# Tres dias de deterioro: 45 lpm de deriva a 15 lpm/dia, y un escalon que llega a entrar en su
# propia base tras las 12 h de desfase, como le pasaria de verdad.
SEGMENT = dt.timedelta(hours=72)
# Base real delante del deterioro: las lecturas de la propia base minima, dentro de la ventana que
# va a juzgarlo. Medir la distancia al primer dato no basta: un registro de 16 dias, un hueco de
# meses y otro tramo dejan el inicio despues del hueco, y el deterioro sin base.
MIN_BASE_READINGS = MIN_SAMPLES
# Una hora de lecturas de 5 min: con menos, el inicio cayo en un hueco y no hay deterioro que ver.
MIN_PERTURBED = 12
CHECKPOINTS = (dt.timedelta(hours=24), dt.timedelta(hours=48), SEGMENT)
_LEVELS = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]


def rmssd_collapse(
    observations: Sequence[VitalObservation], onset: dt.datetime,
) -> InjectedSeries:
    """Cada RMSSD desde `onset`, a la mitad: lo mas parecido a `hrv_collapse` que hay aqui.

    La misma forma, en otro indicador (LifeSnaps no trae SDNN) y solo de noche. Es proporcional
    y no los -30 ms de MMASH porque restar milisegundos dejaba en 0 ms 248 de 327 lecturas de la
    persona con mas dias, y se detectaba un disparate en vez del deterioro (`inject`). Tampoco
    restar media mediana: seguia acotando a 0 todo lo que ya estaba por debajo. No es el mismo
    deterioro, y su cifra no se compara con la de MMASH.
    """
    # La magnitud no se aplica: la `Injection` solo dice que lecturas toca y desde cuando.
    marker = Injection(HRV_RMSSD, Perturbation.STEP, -0.5, onset)
    halved = [
        replace(item, value=round(item.value / 2, 3)) if marker.applies_to(item) else item
        for item in observations
    ]
    return InjectedSeries(
        observations=halved, injection=marker,
        perturbed=sum(marker.applies_to(item) for item in observations),
    )


HEART_INJECTIONS: dict[str, Callable[[dt.datetime], Injection]] = {
    "taquicardia sostenida (+25 lpm)": tachycardia,
    "taquicardia progresiva (+15 lpm/día)": progressive_tachycardia,
    "episodio agudo (+40 lpm, 2 h)": acute_episode,
}
RMSSD_LABEL = "colapso de RMSSD nocturna (-50 %)"


def _trends_at(observations: Sequence[VitalObservation], moment: dt.datetime) -> dict[str, Trend]:
    """Las tendencias vistas en `moment`. `observations` va ordenada por tiempo."""
    upto = bisect.bisect_right(observations, moment, key=lambda item: item.effective)
    return trends_by_indicator(observations[:upto], now=moment)


def _level(
    subject: str, deviations: Sequence[Deviation], moment: dt.datetime, trends: dict[str, Trend],
) -> RiskLevel:
    """El nivel en `moment`: lo del «ahora» del estado y la tendencia. Ordenadas por tiempo."""
    lower = bisect.bisect_right(
        deviations, moment - STATE_WINDOW, key=lambda item: item.effective
    )
    upper = bisect.bisect_right(deviations, moment, key=lambda item: item.effective)
    return RiskEngine().assess(subject, deviations[lower:upper], trends=trends).overall_level


def _is_at_rest(context: Context) -> bool:
    return context is not Context.ACTIVE


def healthy_arm(
    subject: str, observations: Sequence[VitalObservation], variant: Variant,
    trends_by_day: dict[dt.date, dict[str, Trend]],
) -> dict[str, Any]:
    """Las dos formas de contar la falsa alarma, para una persona y una variante."""
    deviations = evaluate(observations, variant)
    context = {(o.key, o.effective): o.context for o in observations}
    by_context: Counter[str] = Counter()
    at_rest = flagged_at_rest = personal = 0
    for item in deviations:
        state = context[(item.key, item.effective)]
        by_context[f"{state}:lecturas"] += 1
        if item.is_concerning:
            by_context[f"{state}:marcadas"] += 1
        if not item.used_population_range:
            personal += 1
            by_context[f"{state}:base personal"] += 1
        if _is_at_rest(state):
            at_rest += 1
            flagged_at_rest += item.is_concerning

    in_order = sorted(deviations, key=lambda item: item.effective)
    days_flagged = 0
    for day, trends in trends_by_day.items():
        moment = dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=dt.UTC)
        days_flagged += _level(subject, in_order, moment, trends) is not RiskLevel.NOMINAL
    return {
        "readings": len(deviations),
        "flagged": sum(1 for item in deviations if item.is_concerning),
        "at_rest": at_rest,
        "flagged_at_rest": flagged_at_rest,
        "personal": personal,
        "episodes": len(group_episodes(deviations)),
        "days": len(trends_by_day),
        "days_flagged": days_flagged,
        "subjects_flagged": int(days_flagged > 0),
        "subjects_with_reading": int(any(item.is_concerning for item in deviations)),
        "by_context": dict(by_context),
    }


def _sensitivity_arm(
    subject: str, observations: Sequence[VitalObservation], variants: Sequence[Variant],
) -> dict[str, dict[str, dict[str, int]]]:
    onset = onset_after(observations)
    base_end = onset - DEFAULT_ROLLING_LAG
    base_start = base_end - DEFAULT_ROLLING_WINDOW
    if sum(base_start <= o.effective <= base_end for o in observations) < MIN_BASE_READINGS:
        return {}
    segment = [o for o in observations if o.effective <= onset + SEGMENT]
    judge_from = onset - STATE_WINDOW
    checkpoints = [onset + delay for delay in CHECKPOINTS]
    clean_trends = [_trends_at(segment, moment) for moment in checkpoints]
    clean = {
        variant: sorted(
            evaluate(segment, variant, judge_from=judge_from), key=lambda item: item.effective
        )
        for variant in variants
    }
    clean_marks = {
        variant: {(d.key, d.effective): d.is_concerning for d in items}
        for variant, items in clean.items()
    }
    sham = {
        variant: [
            _level(subject, clean[variant], moment, trend)
            for moment, trend in zip(checkpoints, clean_trends, strict=True)
        ]
        for variant in variants
    }

    planned = {label: inject(segment, build(onset)) for label, build in HEART_INJECTIONS.items()}
    planned[RMSSD_LABEL] = rmssd_collapse(segment, onset)

    out: dict[str, dict[str, dict[str, int]]] = {}
    for label, series in planned.items():
        if series.perturbed < MIN_PERTURBED:
            continue
        touched = [(o.key, o.effective) for o in series.affected]
        trends = [_trends_at(series.observations, moment) for moment in checkpoints]
        out[label] = {}
        for variant in variants:
            deviations = sorted(
                evaluate(series.observations, variant, judge_from=judge_from),
                key=lambda item: item.effective,
            )
            by_reading = {(d.key, d.effective): d for d in deviations}
            hits = sum(by_reading[slot].is_concerning for slot in touched)
            personal_hits = sum(
                by_reading[slot].is_concerning and not by_reading[slot].used_population_range
                for slot in touched
            )
            sham_hits = sum(clean_marks[variant][slot] for slot in touched)
            levels = [
                _level(subject, deviations, moment, trend)
                for moment, trend in zip(checkpoints, trends, strict=True)
            ]
            out[label][variant] = {
                "subjects": 1,
                "perturbed": series.perturbed,
                "clamped": series.clamped,
                "hits": hits,
                "personal_hits": personal_hits,
                "sham_hits": sham_hits,
                "detected": int(hits > 0),
                "sham_detected": int(sham_hits > 0),
                "flagged": int(any(level is not RiskLevel.NOMINAL for level in levels)),
                "sham_flagged": int(any(level is not RiskLevel.NOMINAL for level in sham[variant])),
                "escalated": int(
                    any(
                        _LEVELS.index(level) > _LEVELS.index(base)
                        for level, base in zip(levels, sham[variant], strict=True)
                    )
                ),
            }
    return out


def measure_subject(job: tuple[Path, str, tuple[Variant, ...]]) -> dict[str, Any] | None:
    """Una persona entera. Va por procesos: ocho semanas por persona no caben en uno solo."""
    folder, subject, variants = job
    data = LifeSnapsLoader(folder).load(subject)
    if not data.observations:
        return None
    observations = data.observations
    days = sorted({o.effective.date() for o in observations})
    trends_by_day = {
        day: _trends_at(
            observations, dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=dt.UTC)
        )
        for day in days
    }
    return {
        "subject": subject,
        "healthy": {
            variant.value: healthy_arm(subject, observations, variant, trends_by_day)
            for variant in variants
        },
        "sensitivity": _sensitivity_arm(subject, observations, variants),
    }


def _add(total: dict[str, Any], part: dict[str, Any]) -> None:
    for key, value in part.items():
        if isinstance(value, dict):
            _add(total.setdefault(key, {}), value)
        else:
            total[key] = total.get(key, 0) + value


def aggregate(results: Iterable[dict[str, Any] | None]) -> dict[str, Any]:
    """Suma por variante, y por variante y deterioro."""
    healthy: dict[str, Any] = {}
    sensitivity: dict[str, Any] = {}
    subjects = 0
    per_subject: list[dict[str, Any]] = []
    for result in results:
        if result is None:
            continue
        subjects += 1
        per_subject.append({
            variant: {name: arm[name] for name in ("readings", "flagged", "days", "days_flagged")}
            for variant, arm in result["healthy"].items()
        })
        _add(healthy, result["healthy"])
        _add(sensitivity, result["sensitivity"])
    return {
        "subjects": subjects, "healthy": healthy, "sensitivity": sensitivity,
        "per_subject": per_subject,
    }


def spread(measured: dict[str, Any], resamples: int = 10_000) -> dict[str, dict[str, Any]]:
    """Intervalos de la falsa alarma remuestreando personas, no lecturas.

    Las lecturas de una persona no son independientes: tratarlas como tales daria un intervalo
    mentirosamente estrecho con 1,3 millones. Mismas personas en cada variante, asi que la
    diferencia con la vigente es pareada. Semilla fija: la cifra publicada sale siempre igual.
    """
    people = measured["per_subject"]
    picks = np.random.default_rng(20261101).integers(0, len(people), (resamples, len(people)))
    readings = np.array([person[Variant.CURRENT]["readings"] for person in people], float)

    def rates(variant: str) -> npt.NDArray[np.float64]:
        flagged = np.array([person[variant]["flagged"] for person in people], float)
        share: npt.NDArray[np.float64] = flagged[picks].sum(axis=1) / readings[picks].sum(axis=1)
        return 100 * share

    current = rates(Variant.CURRENT)
    out: dict[str, dict[str, Any]] = {}
    for variant in people[0]:
        each = [100 * person[variant]["flagged"] / person[variant]["readings"] for person in people]
        ordered = sorted(each)
        out[variant] = {
            "interval": np.percentile(rates(variant), [2.5, 97.5]).round(2).tolist(),
            "difference": np.percentile(rates(variant) - current, [2.5, 97.5]).round(3).tolist(),
            "median_person": round(statistics.median(each), 2),
            "p10_p90_person": [
                round(ordered[len(ordered) // 10], 2), round(ordered[len(ordered) * 9 // 10], 2),
            ],
        }
    return out


def run(
    folder: Path | None = None, workers: int = 6, limit: int | None = None,
    variants: tuple[Variant, ...] = tuple(Variant),
) -> dict[str, Any]:
    """La medida completa: las dos metricas, juntas, para cada variante (invariante 5)."""
    source = folder or dataset_dir() / "normalized"
    names = LifeSnapsLoader(source).subjects()[:limit]
    jobs = [(source, name, variants) for name in names]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return aggregate(pool.map(measure_subject, jobs))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()
    measured = run(workers=arguments.workers, limit=arguments.limit)
    measured["spread"] = spread(measured)
    arguments.output.write_text(
        json.dumps(measured, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
