"""Lo que se ensena a la tripulacion es la base real de cada hallazgo.

`describe()` justificaba todo con el z-score despues de que el z-score dejara de
decidir la gravedad. En el escenario de arritmia, un hallazgo GRAVE se explicaba
como "35 /min, 1,7 desviaciones por debajo de su base personal", cuando lo que lo
hizo grave fue cruzar el limite de peligro de 40 /min. El texto contradecia la
etiqueta que acompanaba, y una base mostrada que no es la usada no se puede
revisar.
"""

import datetime as dt

from app.analysis.baseline import (
    BaselineEngine,
    Deviation,
    Severity,
    SeverityBasis,
)
from app.ingest.fhir import Context, VitalObservation, observation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def _series(key: str, values: list[float]) -> list[VitalObservation]:
    return [
        observation(key, value, NOW - dt.timedelta(hours=len(values) - i), "crew-01", "t")
        for i, value in enumerate(values)
    ]


def _engine_with_heart_rate_baseline() -> BaselineEngine:
    engine = BaselineEngine()
    engine.fit(_series("heart-rate", [60.0 + (i % 4) for i in range(150)]))
    return engine


def _reading(
    value: float,
    key: str = "heart-rate",
    context: Context = Context.UNKNOWN,
    confidence: float = 1.0,
) -> VitalObservation:
    return observation(key, value, NOW, "crew-01", "t", context, confidence)


# --------------------------------------------------------------------------- #
# Limite de peligro
# --------------------------------------------------------------------------- #


def test_danger_limit_without_baseline_names_the_limit() -> None:
    """Sin base personal solo cuenta el limite, y el texto tiene que decir cual."""
    deviation = BaselineEngine().evaluate(_reading(190.0))

    assert deviation.severity is Severity.SEVERE
    assert deviation.basis is SeverityBasis.DANGER_LIMIT
    assert deviation.danger_limit == 150.0
    text = deviation.describe()
    assert "límite de peligro" in text
    assert "150" in text
    assert "desviaciones" not in text


def test_danger_limit_depends_on_context_and_says_so() -> None:
    """120 lpm en reposo cruza el limite de reposo (110), no el general (150)."""
    deviation = BaselineEngine().evaluate(_reading(120.0, context=Context.REST))

    assert deviation.basis is SeverityBasis.DANGER_LIMIT
    assert deviation.danger_limit == 110.0
    assert "110" in deviation.describe()


def test_single_reading_evaluation_applies_the_danger_net() -> None:
    """`evaluate()` se saltaba la red de peligro cuando habia base personal.

    Con base personal, 160 lpm solo llegaba a leve por cuantiles —150 muestras no
    sostienen mas— y el limite de 150 no se miraba. `evaluate_rolling()` si lo
    aplicaba. Dos caminos, dos respuestas para la misma lectura.
    """
    deviation = _engine_with_heart_rate_baseline().evaluate(_reading(160.0))

    assert deviation.severity is Severity.SEVERE
    assert deviation.basis is SeverityBasis.DANGER_LIMIT
    assert not deviation.used_population_range


# --------------------------------------------------------------------------- #
# Percentil personal
# --------------------------------------------------------------------------- #


def test_personal_finding_describes_where_it_falls_in_its_own_history() -> None:
    deviation = _engine_with_heart_rate_baseline().evaluate(_reading(95.0))

    assert deviation.is_concerning
    assert deviation.basis is SeverityBasis.PERSONAL_PERCENTILE
    text = deviation.describe()
    assert "por encima" in text
    assert "de sus propias lecturas de referencia (150 lecturas)" in text
    assert "desviaciones" not in text


def test_low_side_percentile_counts_readings_strictly_above() -> None:
    """Por debajo: la fraccion de lecturas de referencia **mayores** que el valor."""
    engine = BaselineEngine()
    engine.fit(_series("oxygen-saturation", [95.0 + (i % 5) * 0.5 for i in range(150)]))
    deviation = engine.evaluate(_reading(94.0, key="oxygen-saturation"))

    assert deviation.basis is SeverityBasis.PERSONAL_PERCENTILE
    assert "por debajo del 100,0 % de sus propias lecturas" in deviation.describe()


# --------------------------------------------------------------------------- #
# Baja confianza: el tope va el ultimo, tambien sobre limites de peligro
# --------------------------------------------------------------------------- #


def test_poor_contact_cannot_make_a_danger_crossing_severe() -> None:
    """Una trama sin contacto que marca 30 lpm no es un hallazgo grave.

    Antes la red de peligro se aplicaba despues del tope de confianza y lo
    anulaba, y la via poblacional ni miraba la confianza. Con el sensor suelto la
    cifra no es fisiologia, y los artefactos de contacto llegan en rachas: la
    regla de rafaga no protege de ellos.
    """
    for engine in (BaselineEngine(), _engine_with_heart_rate_baseline()):
        deviation = engine.evaluate(_reading(30.0, context=Context.REST, confidence=0.3))

        assert deviation.severity is Severity.MILD
        assert deviation.basis is SeverityBasis.LOW_CONFIDENCE
        assert deviation.danger_limit == 40.0
        text = deviation.describe()
        assert "límite de peligro (40 /min)" in text
        assert "baja confianza" in text


def test_good_contact_danger_crossing_stays_severe() -> None:
    """El contrapeso: con buena medida, el cruce sigue siendo grave."""
    for engine in (BaselineEngine(), _engine_with_heart_rate_baseline()):
        deviation = engine.evaluate(_reading(30.0, context=Context.REST, confidence=1.0))
        assert deviation.severity is Severity.SEVERE
        assert deviation.basis is SeverityBasis.DANGER_LIMIT


def test_rolling_path_caps_poor_contact_crossings_too() -> None:
    """El camino de produccion aplica la misma regla que la lectura suelta."""
    history = [
        observation(
            "heart-rate", 60.0 + (i % 4), NOW - dt.timedelta(hours=200 - i),
            "crew-01", "t", Context.REST,
        )
        for i in range(200)
    ]
    loose = observation("heart-rate", 30.0, NOW, "crew-01", "t", Context.REST, 0.3)
    last = BaselineEngine().evaluate_rolling([*history, loose])[-1]

    assert last.value == 30.0
    assert last.severity is Severity.MILD
    assert last.basis is SeverityBasis.LOW_CONFIDENCE


# --------------------------------------------------------------------------- #
# Compatibilidad
# --------------------------------------------------------------------------- #


def test_deviation_without_basis_still_describes_itself() -> None:
    """Una desviacion construida a mano, sin motivo, conserva el texto antiguo."""
    deviation = Deviation(
        subject="crew-01", key="heart-rate", value=90.0, effective=NOW,
        z_score=3.2, severity=Severity.MODERATE, direction="high",
        baseline=None, used_population_range=False,
    )
    assert deviation.describe() == (
        "Frecuencia cardiaca: 90 /min, 3,2 desviaciones por encima de su base personal"
    )
