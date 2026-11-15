"""La sensibilidad por inyección cuenta solo las lecturas que tocó el deterioro.

`measure_sensitivity` emparejaba las desviaciones con las lecturas perturbadas por
`(clave, valor)`. Una lectura sana, anterior al deterioro, marcada y con la misma cifra que una
perturbada contaba como acierto: la sensibilidad (eje 2 de la invariante 5) subía con alarmas
que no eran del deterioro. Es el fallo que ya se había corregido en la tasa en reposo de
`evaluate_subject`; aquí se empareja por el momento de la lectura (`Deviation.effective`).

Sin red ni MMASH: un sujeto sintético y un motor de línea base de mentira que marca solo la
lectura sana. Lo que se prueba es el emparejamiento, no el motor.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import pytest

from app.analysis.baseline import Deviation, Severity
from app.ingest.codes import get
from app.ingest.fhir import VitalObservation
from app.validation import report as R
from app.validation.injection import Injection, Perturbation
from app.validation.mmash import SubjectData

T0 = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.UTC)
# Diez lecturas horarias de 70 lpm; la de las 10:00 (sana, antes del deterioro) es de 95.
HEALTHY_SPIKE = T0 + dt.timedelta(hours=2)


def _reading(when: dt.datetime, value: float) -> VitalObservation:
    return VitalObservation(
        code=get("heart-rate"), value=value, effective=when, subject="user_x", source="mmash",
    )


class _Loader:
    def subjects(self) -> list[str]:
        return ["user_x"]

    def load(self, name: str) -> SubjectData:
        readings = [
            _reading(T0 + dt.timedelta(hours=h), 95.0 if h == 2 else 70.0) for h in range(10)
        ]
        return SubjectData(subject=name, observations=readings)


class _OnlyTheHealthySpike:
    """Marca solo la lectura sana de 95 lpm: ninguna perturbada."""

    def evaluate_rolling(
        self, observations: Sequence[VitalObservation], **_: object
    ) -> list[Deviation]:
        return [
            Deviation(
                subject=o.subject, key=o.key, value=o.value, effective=o.effective, z_score=0.0,
                severity=Severity.MODERATE if o.effective == HEALTHY_SPIKE else Severity.NONE,
                direction="high", baseline=None, used_population_range=True,
            )
            for o in observations
        ]


def _step(onset: dt.datetime) -> Injection:
    # +25 sobre 70: cada lectura perturbada vale 95, la misma cifra que la sana marcada.
    return Injection("heart-rate", Perturbation.STEP, 25.0, onset)


def test_a_healthy_flag_with_the_same_value_is_not_a_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(R, "BaselineEngine", _OnlyTheHealthySpike)
    result = R.measure_sensitivity(_Loader(), _step, "escalón")  # type: ignore[arg-type]

    assert result.subjects == 1
    assert result.perturbed_readings > 0
    # Ninguna lectura perturbada quedó marcada: ni acierto por lectura ni sujeto detectado.
    assert result.flagged_perturbed == 0
    assert result.detected == 0
