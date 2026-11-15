"""Avisos, no lecturas: la metrica que de verdad mide la fatiga de alarma.

La suite publica una tasa por lectura. Este fichero cubre la otra forma de contar
—cuantos avisos distintos llegarian al tripulante— y la sujeta con una regresion
sobre los 22 sujetos sanos de MMASH.
"""

import datetime as dt
from pathlib import Path

import pytest

from app.analysis.baseline import BaselineEngine, Deviation, Severity
from app.validation.episodes import EPISODE_GAP, group_episodes, summarize
from app.validation.mmash import MmashLoader
from app.validation.report import MISSION_LAG, MISSION_WINDOW

T0 = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)


def _deviation(
    minute: int,
    *,
    subject: str = "crew-01",
    key: str = "heart-rate",
    value: float = 120.0,
    severity: Severity = Severity.MODERATE,
    z_score: float = 3.0,
) -> Deviation:
    return Deviation(
        subject=subject,
        key=key,
        value=value,
        effective=T0 + dt.timedelta(minutes=minute),
        z_score=z_score,
        severity=severity,
        direction="high",
        baseline=None,
        used_population_range=True,
    )


# --------------------------------------------------------------------------- #
# Agrupacion
# --------------------------------------------------------------------------- #


def test_a_run_of_readings_is_one_alert() -> None:
    """Veinte lecturas marcadas en dos horas son un aviso, no veinte. Contarlas por
    separado multiplica por 2,5 la cifra de fatiga de alarma sobre MMASH."""
    episodes = group_episodes(_deviation(minute) for minute in range(0, 120, 6))

    assert len(episodes) == 1
    assert episodes[0].readings == 20
    assert episodes[0].duration == dt.timedelta(minutes=114)


def test_a_long_gap_splits_the_alert() -> None:
    """Dos rachas separadas por mas de la ventana son dos situaciones distintas."""
    minutes = [0, 5, 10, 200, 205]
    episodes = group_episodes(_deviation(minute) for minute in minutes)

    assert [episode.readings for episode in episodes] == [3, 2]


def test_the_boundary_belongs_to_the_same_episode() -> None:
    """Justo en el corte, sigue siendo el mismo aviso; un minuto mas, no."""
    exact = group_episodes([_deviation(0), _deviation(int(EPISODE_GAP.total_seconds() // 60))])
    beyond = group_episodes([_deviation(0), _deviation(int(EPISODE_GAP.total_seconds() // 60) + 1)])

    assert len(exact) == 1
    assert len(beyond) == 2


def test_two_indicators_at_the_same_time_are_two_alerts() -> None:
    """Una caida de HRV y una subida de pulso son dos hallazgos, no uno."""
    episodes = group_episodes([_deviation(0), _deviation(0, key="hrv-sdnn")])

    assert len(episodes) == 2
    assert {episode.key for episode in episodes} == {"heart-rate", "hrv-sdnn"}


def test_two_crew_members_never_share_an_episode() -> None:
    """Mezclar sujetos convertiria dos avisos en uno y dejaria a alguien sin el suyo."""
    episodes = group_episodes([_deviation(0), _deviation(1, subject="crew-02")])

    assert len(episodes) == 2
    assert {episode.subject for episode in episodes} == {"crew-01", "crew-02"}


def test_what_is_not_concerning_is_not_an_alert() -> None:
    within_range = _deviation(5, severity=Severity.NONE)

    episodes = group_episodes([_deviation(0), within_range, _deviation(10)])

    assert len(episodes) == 1
    assert episodes[0].readings == 2, "la lectura normal no entra en el aviso"


def test_nothing_concerning_means_no_alerts() -> None:
    assert group_episodes([_deviation(0, severity=Severity.NONE)]) == []
    assert group_episodes([]) == []


def test_episodes_come_out_in_order() -> None:
    episodes = group_episodes(
        [_deviation(300), _deviation(0, key="hrv-sdnn"), _deviation(150, subject="crew-02")]
    )

    assert [episode.start for episode in episodes] == sorted(e.start for e in episodes)


def test_the_peak_is_the_reading_that_explains_the_alert() -> None:
    """Un aviso se cuenta a quien lo recibe por su lectura mas extrema, no la primera."""
    episodes = group_episodes(
        [_deviation(0, z_score=2.1, value=112.0), _deviation(5, z_score=9.4, value=192.0)]
    )

    assert episodes[0].peak.value == 192.0


# --------------------------------------------------------------------------- #
# Resumen
# --------------------------------------------------------------------------- #


def test_the_rate_counts_the_quiet_subjects_too() -> None:
    """El que no dispara nada es justo el que baja la tasa: si no contara su tiempo
    de registro, la cifra saldria inflada."""
    deviations = [_deviation(0), _deviation(5)]

    alone = summarize(deviations, subject_days=1.0)
    with_company = summarize(deviations, subject_days=22.0)

    assert alone.per_crew_week == pytest.approx(7.0)
    assert with_company.per_crew_week == pytest.approx(7 / 22)


def test_a_record_of_nothing_does_not_divide_by_zero() -> None:
    empty = summarize([], subject_days=0.0)

    assert empty.count == 0
    assert empty.per_crew_week == 0.0
    assert empty.readings_per_episode == 0.0


def test_the_summary_separates_readings_from_alerts() -> None:
    summary = summarize([_deviation(minute) for minute in (0, 5, 10, 200)], subject_days=7.0)

    assert summary.flagged_readings == 4
    assert summary.count == 2
    assert summary.readings_per_episode == pytest.approx(2.0)
    assert summary.per_crew_week == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Regresion sobre fisiologia humana real
# --------------------------------------------------------------------------- #

DATASET = Path(__file__).resolve().parents[2] / "data" / "mmash" / "MMASH.zip"

# Medido el 2026-09-23 sobre los 22 sujetos de MMASH con parametros de mision:
# 34 lecturas marcadas que son 16 episodios en 30,8 dias-sujeto.
#
# BAJO DESDE 3,86 (43 lecturas, 17 episodios) y no por tocar este umbral: el
# hallazgo 28 dejo de leer "cero pasos con el acelerometro quitado" como reposo, y
# con ello se fueron nueve lecturas marcadas de `user_15` —comparadas contra el
# limite de peligro en reposo cuando el aparato ni siquiera estaba puesto—. El
# desglose esta en `compliance/external-validation.md`.
#
# Es un techo, como el de la tasa por lectura: detecta empeoramientos. Bajarlo cuando
# el motor mejore es correcto; subirlo para que pase una suite que empeoro, no.
MEASURED_EPISODES_PER_CREW_WEEK = 3.63
TOLERANCE = 0.4


@pytest.mark.external
def test_alerts_per_crew_week_does_not_regress() -> None:
    """Lo que un tripulante veria en una semana, sobre 22 personas sanas reales.

    Sujeta la cifra que importa para la fatiga de alarma, que no es la tasa por
    lectura: un sensor que muestree el doble de rapido duplica las lecturas marcadas
    sin producir un solo aviso mas.
    """
    if not DATASET.exists():
        pytest.skip(f"MMASH no descargado en {DATASET}")

    loader = MmashLoader(DATASET)
    engine = BaselineEngine()
    deviations: list[Deviation] = []
    recorded = dt.timedelta()

    for name in loader.subjects():
        data = loader.load(name)
        if not data.observations:
            continue
        deviations.extend(
            engine.evaluate_rolling(data.observations, window=MISSION_WINDOW, lag=MISSION_LAG)
        )
        moments = [item.effective for item in data.observations]
        recorded += max(moments) - min(moments)

    summary = summarize(deviations, subject_days=recorded.total_seconds() / 86400)

    assert summary.per_crew_week <= MEASURED_EPISODES_PER_CREW_WEEK + TOLERANCE, (
        f"los avisos por tripulante-semana empeoraron: {summary.per_crew_week:.2f} "
        f"(medido: {MEASURED_EPISODES_PER_CREW_WEEK}). {summary.describe()}"
    )
    assert summary.readings_per_episode > 1.0, (
        "cada lectura marcada esta saliendo como un aviso propio: o el motor cambio, "
        "o la agrupacion dejo de agrupar"
    )
