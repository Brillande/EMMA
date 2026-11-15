"""El simulador debe ser reproducible y producir derivas que el analisis pueda ver.

La reproducibilidad no es comodidad: sin ella no se puede afirmar que una alerta
se disparo por la razon que se cree, y la verificacion documentada pierde valor.
"""

import datetime as dt
from statistics import mean, pstdev

import pytest
from fastapi.testclient import TestClient

from app.ingest.codes import (
    CATALOG,
    DESCRIPTIVE_ONLY,
    LAB_REPORT_ONLY,
    SELF_REPORTED_ONLY,
    ULTRASOUND_MEASURES,
    Domain,
)
from app.ingest.fhir import Context
from app.ingest.simulator import (
    ENVIRONMENTAL_SCENARIOS,
    EVIDENCE_CLASSES,
    LITERATURE,
    SCENARIO_ONLY_KEYS,
    CrewMember,
    PhysiologicalSimulator,
    Scenario,
    domain_keys,
    transient_level,
)


def series(sim: PhysiologicalSimulator, key: str, days: int = 28) -> list[float]:
    return [obs.value for obs in sim.generate(days=days, samples_per_day=4, keys=[key])]


def test_same_seed_gives_identical_series() -> None:
    first = series(PhysiologicalSimulator(seed=42), "heart-rate")
    second = series(PhysiologicalSimulator(seed=42), "heart-rate")
    assert first == second


def test_different_seed_gives_different_series() -> None:
    first = series(PhysiologicalSimulator(seed=42), "heart-rate")
    second = series(PhysiologicalSimulator(seed=43), "heart-rate")
    assert first != second


def test_generates_valid_observations() -> None:
    sim = PhysiologicalSimulator()
    observations = list(sim.generate(days=1, samples_per_day=2))
    assert observations
    assert all(obs.validates() for obs in observations[:10])


def test_observations_are_chronological() -> None:
    sim = PhysiologicalSimulator()
    times = [obs.effective for obs in sim.generate(days=3, samples_per_day=4, keys=["heart-rate"])]
    assert times == sorted(times)


def test_covers_every_domain_with_telemetry() -> None:
    """Todo dominio tiene fuente: telemetría simulada o, si solo se mide por ecografía,
    estudios de imagen, o si solo lo cuenta el tripulante, su autoinforme. Una ecografía
    no es telemetría, y lo que alguien siente no se simula: sería fisiología inventada,
    así que esos indicadores no se simulan aquí. Una analítica tampoco: llega en papel."""
    sim = PhysiologicalSimulator()
    produced = {obs.domain for obs in sim.generate(days=1, samples_per_day=1)}
    # Hidratacion y nutricion solo existen en sus escenarios: el nominal no los genera.
    # Los analitos de analítica solo entran confirmando un informe escaneado: no se simulan.
    # Los indicadores descriptivos tampoco: el estado no los lee y no hay modelo de ninguno.
    not_simulated = (
        ULTRASOUND_MEASURES | SELF_REPORTED_ONLY | SCENARIO_ONLY_KEYS | LAB_REPORT_ONLY
        | DESCRIPTIVE_ONLY
    )
    unsimulated_domains = {
        domain for domain in Domain
        if all(key in not_simulated for key in domain_keys(domain))
    }
    assert unsimulated_domains == {
        Domain.NEURO_OCULAR, Domain.GENITOURINARY, Domain.MUSCULOSKELETAL, Domain.NUTRITION,
    }
    assert produced == set(Domain) - unsimulated_domains
    assert not any(obs.key in not_simulated for obs in sim.generate(days=1))


def test_unknown_indicator_is_rejected() -> None:
    sim = PhysiologicalSimulator()
    with pytest.raises(KeyError, match="desconocidos"):
        list(sim.generate(days=1, keys=["no-existe"]))


def test_values_respect_physiological_bounds() -> None:
    """Un valor fuera de lo fisiologicamente posible seria ruido, no una alerta."""
    sim = PhysiologicalSimulator(scenario=Scenario.ARRHYTHMIA)
    for obs in sim.generate(days=14, samples_per_day=4, keys=["heart-rate", "oxygen-saturation"]):
        if obs.key == "heart-rate":
            assert 35 <= obs.value <= 190
        else:
            assert 70 <= obs.value <= 100


# --------------------------------------------------------------------------- #
# Escenarios: cada uno debe producir la senal que le da sentido
# --------------------------------------------------------------------------- #


def test_insomnia_scenario_degrades_sleep_and_vigilance() -> None:
    sim = PhysiologicalSimulator(scenario=Scenario.PROGRESSIVE_INSOMNIA)
    sleep = series(sim, "sleep-duration")
    reaction = series(PhysiologicalSimulator(scenario=Scenario.PROGRESSIVE_INSOMNIA), "pvt-mean-rt")

    assert mean(sleep[-8:]) < mean(sleep[:8]) - 1.0, "el sueño debe deteriorarse"
    # El vinculo sueno -> rendimiento es lo que el motor de analisis debe captar.
    assert mean(reaction[-8:]) > mean(reaction[:8]) + 20, "el PVT debe empeorar"


def test_nominal_scenario_keeps_sleep_stable() -> None:
    sleep = series(PhysiologicalSimulator(scenario=Scenario.NOMINAL), "sleep-duration")
    assert abs(mean(sleep[-8:]) - mean(sleep[:8])) < 1.0


def test_deconditioning_raises_heart_rate_and_lowers_hrv() -> None:
    decon = Scenario.CARDIOVASCULAR_DECONDITIONING
    hr = series(PhysiologicalSimulator(scenario=decon), "heart-rate")
    hrv = series(PhysiologicalSimulator(scenario=decon), "hrv-sdnn")

    assert mean(hr[-8:]) > mean(hr[:8]) + 3
    assert mean(hrv[-8:]) < mean(hrv[:8]) - 5


def test_arrhythmia_raises_variability_not_the_mean() -> None:
    """La clave del escenario: un umbral sobre la media sola no lo detectaria.

    Se compara **dentro del mismo contexto**, y no por gusto: con ritmo circadiano
    la dispersion de un dia entero mezcla la variabilidad patologica con la caida
    normal del pulso durante el sueno. Medida asi, la serie sana parece variable y
    la arritmia se diluye. Es exactamente el error que la estratificacion por
    contexto corrige en el motor, aplicado aqui a la medida.
    """
    def en_reposo(scenario: Scenario) -> list[float]:
        sim = PhysiologicalSimulator(scenario=scenario, seed=7)
        return [
            obs.value
            for obs in sim.generate(days=30, keys=["heart-rate"])
            if obs.context is Context.REST
        ]

    nominal = en_reposo(Scenario.NOMINAL)
    arrhythmic = en_reposo(Scenario.ARRHYTHMIA)

    assert pstdev(arrhythmic) > pstdev(nominal) * 3
    assert abs(mean(arrhythmic) - mean(nominal)) < 10


def test_spe_event_produces_an_acute_dose_spike() -> None:
    sim = PhysiologicalSimulator(scenario=Scenario.SPE_EVENT)
    dose = series(sim, "absorbed-dose-rate", days=14)

    baseline = mean(dose[:16])  # primeros dias, muy anteriores al evento
    assert max(dose) > baseline * 20, "un SPE debe ser un pico agudo, no una deriva"


def test_spe_event_is_recent_enough_to_be_visible() -> None:
    """Un evento que ya decayo cuando se mira la pantalla no demuestra nada."""
    sim = PhysiologicalSimulator(scenario=Scenario.SPE_EVENT)
    dose = series(sim, "absorbed-dose-rate", days=20)
    peak_index = dose.index(max(dose))
    # El pico debe caer en el ultimo 15 % de la ventana generada.
    assert peak_index > len(dose) * 0.85


def test_spe_onset_scales_with_the_window() -> None:
    sim = PhysiologicalSimulator(scenario=Scenario.SPE_EVENT)
    assert sim._spe_onset_day(40) == 38.5
    assert sim._spe_onset_day(20) == 18.5
    # Ventanas muy cortas no pueden poner el evento en negativo.
    assert sim._spe_onset_day(1) == 0.5


def test_nominal_scenario_has_no_dose_spike() -> None:
    dose = series(PhysiologicalSimulator(scenario=Scenario.NOMINAL), "absorbed-dose-rate", days=14)
    assert max(dose) < mean(dose) * 4


def test_immune_scenario_triggers_viral_reactivation() -> None:
    shedding = series(
        PhysiologicalSimulator(scenario=Scenario.IMMUNE_REACTIVATION), "latent-virus-shedding"
    )
    assert max(shedding) > 0
    assert mean(shedding[-8:]) > mean(shedding[:8])


def test_nominal_scenario_has_no_viral_reactivation() -> None:
    shedding = series(PhysiologicalSimulator(scenario=Scenario.NOMINAL), "latent-virus-shedding")
    assert max(shedding) == 0


@pytest.mark.parametrize("scenario", list(Scenario))
def test_every_scenario_runs_and_is_reproducible(scenario: Scenario) -> None:
    def run() -> list:
        sim = PhysiologicalSimulator(scenario=scenario, seed=1)
        return list(sim.generate(days=2, samples_per_day=2))

    first, second = run(), run()
    assert [obs.value for obs in first] == [obs.value for obs in second]
    assert first


# --------------------------------------------------------------------------- #
# Deriva y adaptacion
# --------------------------------------------------------------------------- #


def test_drift_plateaus_instead_of_growing_without_end() -> None:
    """El cuerpo se adapta. Una deriva lineal infinita seria un modelo falso.

    Sobre la RMSSD (meseta a las 16 semanas): la FC en reposo, que era el ejemplo, no deriva
    desde el 2026-10-31 y con ella la prueba no comprobaba nada.
    """
    sim = PhysiologicalSimulator(scenario=Scenario.NOMINAL, seed=3)
    long_run = series(sim, "hrv-rmssd", days=180)
    mid = mean(long_run[len(long_run) // 2 - 8 : len(long_run) // 2 + 8])
    end = mean(long_run[-16:])
    assert abs(end - mid) < 5, "tras la meseta el indicador no debe seguir subiendo"


# --------------------------------------------------------------------------- #
# Honestidad de los parametros
# --------------------------------------------------------------------------- #


def test_literature_parameters_declare_a_valid_evidence_class() -> None:
    for name, param in LITERATURE.items():
        assert param.evidence in EVIDENCE_CLASSES, f'{name}: {param.evidence}'


def test_every_parameter_carries_a_note_and_a_source() -> None:
    """Un parametro sin procedencia declarada no deberia existir en el modelo."""
    for name, param in LITERATURE.items():
        assert param.note.strip(), f'{name} no explica que representa'
        assert param.source.strip(), f'{name} no declara de donde sale'


def test_simulator_reports_evidence_by_class() -> None:
    """La demo debe poder decir que respaldo tiene cada parte de su modelo."""
    evidence = PhysiologicalSimulator().describe()['evidence']

    assert set(evidence) == set(EVIDENCE_CLASSES)
    assert evidence['established'], 'algo tiene que estar bien documentado'
    for evidence_class, names in evidence.items():
        for name in names:
            assert LITERATURE[name].evidence == evidence_class


def test_contested_parameters_use_a_small_drift() -> None:
    """Donde la ciencia discrepa, el modelo no debe afirmar una tendencia clara.

    La SDNN es el caso: hay estudios que no ven diferencias y otros que ven
    subida. Inventar una caida marcada seria peor que no modelarla.
    """
    contested = {n: p for n, p in LITERATURE.items() if p.evidence == 'contested'}
    assert contested, 'si no queda ninguno contestado, revisar la bibliografia'
    assert 'hrv_sdnn_decline_ms_per_week' in contested
    assert contested['hrv_sdnn_decline_ms_per_week'].value <= 0.5
    # La FC en reposo: reclasificada con su valor de antes el 2026-10-23 (~5 lpm a la meseta, que
    # no era pequeno) y corregida a 0 el 2026-10-31 por decision del usuario: el lado del peso
    # de lo leido, que es «sin cambio».
    assert contested['resting_hr_drift_bpm_per_week'].value == 0.0
    # Las excepciones que quedan lo dicen en su nota: una deriva de diseno reclasificada el
    # 2026-10-31 conserva su valor hasta que el usuario decida (la RMSSD, 0,8 ms/semana). Solo
    # las derivas semanales del modelo nominal: los efectos agudos del CO2 van en otra unidad.
    for name, param in contested.items():
        if name.endswith('_per_week') and param.value > 0.5:
            assert 'no es la deriva pequeña de esta clase' in param.note, name


def test_career_dose_limit_matches_the_standard() -> None:
    """NASA-STD-3001 [V1 4030] fija el limite en 600 mSv, texto verbatim."""
    from app.core.config import Settings

    assert LITERATURE['career_dose_limit_msv'].value == 600.0
    assert Settings().career_dose_limit_msv == 600.0


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #


def test_domain_keys_are_catalog_keys() -> None:
    for domain in Domain:
        for key in domain_keys(domain):
            assert CATALOG[key].domain is domain


def test_custom_crew_member_is_respected() -> None:
    crew = CrewMember(subject_id="crew-99")
    sim = PhysiologicalSimulator(crew=crew)
    obs = next(sim.generate(days=1, samples_per_day=1, keys=["heart-rate"]))
    assert obs.subject == "crew-99"


def test_mission_start_is_respected() -> None:
    start = dt.date(2027, 3, 1)
    sim = PhysiologicalSimulator(mission_start=start)
    obs = next(sim.generate(days=1, samples_per_day=1, keys=["heart-rate"]))
    assert obs.effective.date() == start


# --------------------------------------------------------------------------- #
# Un escenario que cesa y el evento solar a toda la tripulacion (§5.37.3)
# --------------------------------------------------------------------------- #

TRANSIENT_KEYS = {"sleep-duration", "sleep-efficiency", "pvt-mean-rt", "pvt-lapses"}


def test_the_transient_perturbation_rises_holds_and_ceases() -> None:
    """Con 40 dias: entra el dia 34 en 12 h, se queda entera hasta el 37 y se va en otras 12 h."""
    assert transient_level(33.9, 40) == 0.0
    assert transient_level(34.0, 40) == 0.0
    assert transient_level(34.25, 40) == pytest.approx(0.5)
    assert transient_level(35.0, 40) == 1.0
    assert transient_level(37.0, 40) == 1.0
    assert transient_level(37.25, 40) == pytest.approx(0.5)
    assert transient_level(37.5, 40) == 0.0
    # Cesa del todo: los dos ultimos dias, que son la ventana actual del estado, no la ven.
    assert all(transient_level(38.0 + hour / 24, 40) == 0.0 for hour in range(48))
    # En una ventana mas corta que el arranque no aparece, en vez de encogerse para caber.
    assert all(transient_level(day / 4, 4) == 0.0 for day in range(16))


def test_outside_the_episode_the_transient_series_is_the_nominal_one() -> None:
    """Misma semilla: fuera del episodio, lectura a lectura, la serie nominal. El escenario
    solo añade el episodio; y dentro, los cuatro indicadores van en el sentido malo."""
    nominal = list(PhysiologicalSimulator(Scenario.NOMINAL, seed=5).generate(days=40))
    transient = list(
        PhysiologicalSimulator(Scenario.TRANSIENT_SLEEP_LOSS, seed=5).generate(days=40)
    )
    assert [(o.key, o.effective) for o in nominal] == [(o.key, o.effective) for o in transient]
    start = nominal[0].effective
    worse = {key: 0 for key in TRANSIENT_KEYS}
    for before, after in zip(nominal, transient, strict=True):
        day = (before.effective - start).total_seconds() / 86400
        if before.key not in TRANSIENT_KEYS or transient_level(day, 40) == 0.0:
            assert after.value == before.value, (before.key, before.effective)
            continue
        bad_way = (
            after.value > before.value
            if before.key.startswith("pvt-") else after.value < before.value
        )
        worse[before.key] += bad_way
    # 3 dias enteros y dos rampas de 12 h, a 24 lecturas por dia: cada indicador, en todas.
    assert all(count >= 3 * 24 for count in worse.values()), worse


def test_only_the_whole_ship_scenarios_reach_the_whole_crew() -> None:
    """Un evento solar es para toda la nave, como el CO2 de cabina; el resto, una persona."""
    assert {
        Scenario.CO2_FATIGUE, Scenario.SPE_EVENT, Scenario.SPE_EVENT_RECOVERY
    } == ENVIRONMENTAL_SCENARIOS
    assert Scenario.TRANSIENT_SLEEP_LOSS not in ENVIRONMENTAL_SCENARIOS


def test_the_solar_event_reaches_the_four_crew_members(client: TestClient) -> None:
    """Hasta la decimoseptima ronda solo crew-01 lo sufria: los otros tres, en la misma nave,
    seguian con la dosis de fondo. Ahora la siembra por defecto es de cuatro y los cuatro lo
    ven en su radiacion."""
    seeded = client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    assert seeded.status_code == 201
    crew = seeded.json()["simulation"]["crew"]
    assert crew == ["crew-01", "crew-02", "crew-03", "crew-04"]
    for subject in crew:
        status = client.get("/api/status", params={"subject": subject}).json()
        assert status["domains"]["radiation"]["level"] != "nominal", subject


def test_a_personal_scenario_still_seeds_one_crew_member(client: TestClient) -> None:
    seeded = client.post("/api/simulate", params={"scenario": "transient-sleep-loss", "days": 2})
    assert seeded.json()["simulation"]["crew"] == ["crew-01"]


def test_the_transient_scenario_ends_recovering(client: TestClient) -> None:
    """La demo de la conversacion de ideacion: CAUTION -> RECOVERING. A los 40 dias el dominio
    conductual esta por debajo de donde estaba una ventana antes, y el estado lo dice."""
    assert client.post(
        "/api/simulate", params={"scenario": "transient-sleep-loss", "days": 40}
    ).status_code == 201
    behavioral = client.get("/api/status").json()["domains"]["behavioral"]
    assert behavioral["trajectory"]["direction"] == "recovering"
    assert behavioral["trajectory"]["from_level"] == "concern"
    assert behavioral["level"] in {"nominal", "watch"}
