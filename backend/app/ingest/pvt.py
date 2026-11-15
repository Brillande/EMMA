"""Puntuacion del test de vigilancia psicomotora (PVT).

El PVT es la medida objetiva de fatiga y deterioro de vigilancia que la NASA usa
en la ISS (Reaction Self-Test). Importa porque convierte "me encuentro cansado"
—que un astronauta motivado infravalora sistematicamente— en un numero.

Reglas de puntuacion estandar:

  lapso         tiempo de reaccion > 500 ms
  salida falsa  respuesta antes del estimulo, o por debajo del minimo
                fisiologico de reaccion humana (~100 ms): no es vigilancia,
                es anticipacion

Leido en las fuentes el 2026-10-13 (`data/instruments_read.json`, con sus frases):
la prueba de 10 minutos define el lapso como TR >= 500 ms (aqui es > 500: difieren
en el valor exacto), la version breve de 3 minutos usa otro umbral, mas bajo, y
un estimulo sin respuesta cuenta en ambas como lapso. La salida falsa (< 100 ms)
coincide. Los valores de este modulo NO se cambiaron al leerlo: mueven el
indicador de lapsos que el analisis vigila (invariante 5), y es una decision
pendiente. La comparacion la sirve `GET /api/pvt/protocol`.

Que metrica mira cada cosa
--------------------------
Se informan varias porque miden cosas distintas, y confundirlas lleva a
conclusiones falsas:

  `lapses`              la medida sensible al **fallo de vigilancia**. Es la que
                        se degrada con la deuda de sueno.
  `mean_rt_ms`          intuitiva, pero queda dominada por unas pocas respuestas
                        muy lentas.
  `response_speed`      media de 1/RT. Su valor no es "detectar antes": por la
                        desigualdad de Jensen siempre resulta mayor o igual que
                        1/(RT medio). Lo que aporta es **reducir la influencia de
                        las respuestas extremas** y dar una distribucion menos
                        sesgada, mas apta para estadistica parametrica. Por eso
                        la literatura de PVT la usa **junto a** los lapsos, no en
                        su lugar.
  `slowest_10pct_mean`  el decil mas lento, que es donde asoma la fatiga antes de
                        que la media se mueva.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Umbral estandar de lapso en el PVT.
LAPSE_THRESHOLD_MS = 500.0

# Por debajo de esto no hay reaccion posible a un estimulo: es anticipacion.
FALSE_START_THRESHOLD_MS = 100.0

# Un PVT util necesita suficientes estimulos. El test clasico dura 10 min; la
# version breve de la ISS ronda los 3-5 min. Por debajo de esto el resultado no
# es interpretable y el sistema lo dice en vez de puntuarlo.
MIN_TRIALS = 10


@dataclass(frozen=True, slots=True)
class PvtResult:
    """Resultado puntuado de una sesion de PVT."""

    trials: int
    valid_trials: int
    mean_rt_ms: float
    median_rt_ms: float
    slowest_10pct_mean_ms: float
    lapses: int
    false_starts: int
    response_speed: float  # media de 1/RT, en s^-1

    @property
    def lapse_rate(self) -> float:
        return self.lapses / self.valid_trials if self.valid_trials else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trials": self.trials,
            "valid_trials": self.valid_trials,
            "mean_rt_ms": self.mean_rt_ms,
            "median_rt_ms": self.median_rt_ms,
            "slowest_10pct_mean_ms": self.slowest_10pct_mean_ms,
            "lapses": self.lapses,
            "lapse_rate": round(self.lapse_rate, 4),
            "false_starts": self.false_starts,
            "response_speed": self.response_speed,
        }


class InsufficientTrials(ValueError):
    """La sesion no tiene estimulos suficientes para ser interpretable."""


def is_lapse(rt_ms: float) -> bool:
    """Si una respuesta valida cuenta como lapso: estrictamente por encima del umbral.

    Existe aparte para que la regla se pueda exponer tal como puntua, no copiada a mano:
    `GET /api/pvt/protocol` deduce de aqui si EMMA cuenta con «>» o con «>=». Lo
    publicado (Basner et al. 2011) cuenta con «>= 500 ms»; EMMA, con «> 500 ms». Es
    una divergencia declarada, no corregida: cambiarla mueve el indicador de lapsos
    (invariante 5) y es decision del usuario.
    """
    return rt_ms > LAPSE_THRESHOLD_MS


def score(reaction_times_ms: Sequence[float]) -> PvtResult:
    """Puntua una sesion de PVT a partir de sus tiempos de reaccion.

    Las salidas falsas se cuentan pero **no** entran en las estadisticas de
    tiempo: promediarlas mejoraria artificialmente el resultado de quien anticipa
    en vez de atender, que es justo lo contrario de lo que mide el test.
    """
    if len(reaction_times_ms) < MIN_TRIALS:
        raise InsufficientTrials(
            f"el PVT necesita al menos {MIN_TRIALS} estímulos para ser "
            f"interpretable; llegaron {len(reaction_times_ms)}"
        )

    false_starts = sum(1 for rt in reaction_times_ms if rt < FALSE_START_THRESHOLD_MS)
    valid = [rt for rt in reaction_times_ms if rt >= FALSE_START_THRESHOLD_MS]

    if not valid:
        raise InsufficientTrials(
            "todas las respuestas fueron salidas falsas: la sesión no mide vigilancia"
        )

    ordered = sorted(valid, reverse=True)
    slowest_count = max(1, len(ordered) // 10)
    slowest = ordered[:slowest_count]

    return PvtResult(
        trials=len(reaction_times_ms),
        valid_trials=len(valid),
        mean_rt_ms=round(statistics.fmean(valid), 2),
        median_rt_ms=round(statistics.median(valid), 2),
        slowest_10pct_mean_ms=round(statistics.fmean(slowest), 2),
        lapses=sum(1 for rt in valid if is_lapse(rt)),
        false_starts=false_starts,
        # 1/RT en segundos: la metrica mas sensible al deterioro por fatiga.
        response_speed=round(statistics.fmean([1000.0 / rt for rt in valid]), 4),
    )


def to_observations(
    result: PvtResult, subject: str, effective: Any, source: str = "pvt-test"
) -> list[Any]:
    """Convierte un resultado de PVT en observaciones del catalogo."""
    from app.ingest.fhir import observation

    return [
        observation("pvt-mean-rt", result.mean_rt_ms, effective, subject, source),
        observation("pvt-lapses", float(result.lapses), effective, subject, source),
    ]
