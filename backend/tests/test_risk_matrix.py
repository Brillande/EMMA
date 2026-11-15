"""La matriz de riesgos (`app/risk_entity.py`, `GET /api/risks`): peligro, efecto, variable,
dato, detección y contramedida de cada dominio.

Lo que vigilan estas pruebas es que nada de la fila se escriba a mano: la regla de detección es
la del motor —cambiar una constante de `analysis/` cambia lo publicado, y lo publicado clasifica
como clasifica el motor—, la evidencia se parte por la clase de documento del registro y las
contramedidas son las de la biblioteca, una a una. Y que describirlo no toca el almacén.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import risk_entity
from app.advisor.countermeasures import SHELTER_ID, for_domain, library
from app.analysis import baseline, risk, trend
from app.analysis.alert_support import BASIS_DISPLAY
from app.analysis.baseline import Deviation, Severity, crossed_danger_limit
from app.analysis.risk import RiskEngine, representative_deviation
from app.api import routes
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.environment.donki import Severity as SolarSeverity
from app.evidence import registry
from app.evidence.links import HRP_RISKS, evidence_for
from app.ingest.codes import Domain, evaluated_by_domain
from app.ingest.codes import get as get_code
from app.ingest.cost import costs
from app.ingest.fhir import Context, observation
from app.main import app
from app.validation import mmash
from app.validation.mmash import DATASET as VALIDATION_DATASET

MOMENT = dt.datetime(2030, 1, 1, tzinfo=dt.UTC)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _risks(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/risks")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _step(body: dict[str, Any], key: str) -> dict[str, Any]:
    step: dict[str, Any] = next(
        item for item in body["detection_rule"]["steps"] if item["key"] == key
    )
    return step


def _risk(body: dict[str, Any], domain: Domain) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in body["risks"] if item["risk_id"] == str(domain))
    return found


def _deviation(key: str, severity: Severity, minute: int) -> Deviation:
    return Deviation(
        subject="crew-01", key=key, value=0.0, effective=MOMENT + dt.timedelta(minutes=minute),
        z_score=3.0 if severity is not Severity.NONE else 0.0, severity=severity,
        direction="high", baseline=None, used_population_range=True,
    )


# --------------------------------------------------------------------------- #
# La cadena
# --------------------------------------------------------------------------- #

def test_the_matrix_has_the_six_links_of_the_conversation_in_order(client: TestClient) -> None:
    chain = _risks(client)["chain"]
    assert [item["key"] for item in chain["links"]] == [
        "hazard", "effect", "variables", "data", "detection", "countermeasures",
    ]
    assert all(item["display"] for item in chain["links"])
    assert "no decide nada" in chain["basis"]


def test_every_risk_carries_its_row(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        for field in ("ridge", "effect", "indicators", "data_sources", "detection",
                      "countermeasures"):
            assert field in item, (item["risk_id"], field)


def test_the_effect_is_what_the_hrp_citation_says(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        cited = HRP_RISKS[Domain(item["risk_id"])]
        assert item["effect"]["statement"] == cited.relevance
        assert item["effect"]["source"]["id"] == cited.id


def test_a_domain_without_hrp_risk_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_entity, "HRP_RISKS", {})
    block = risk_entity.effect(Domain.BONE)
    assert block["source"] is None and block["statement"] == risk_entity.NO_EFFECT


# --------------------------------------------------------------------------- #
# El dato: conjuntos de datos y documentos, por la clase del registro
# --------------------------------------------------------------------------- #

def test_the_evidence_is_split_by_the_registry_document_class(client: TestClient) -> None:
    assert risk_entity.DATASET_TYPE in registry.EVIDENCE_TYPES
    for item in _risks(client)["risks"]:
        cited = evidence_for(Domain(item["risk_id"]))
        block = item["data_sources"]
        assert [row["id"] for row in block["datasets"]] == [
            ref.id for ref in cited if ref.ref.evidence_type == "dataset"
        ]
        assert [row["id"] for row in block["documents"]] == [
            ref.id for ref in cited if ref.ref.evidence_type != "dataset"
        ]
        assert all(row["evidence_type"] == "dataset" for row in block["datasets"])
        assert (block["datasets_empty"] is None) == bool(block["datasets"])
        assert (block["documents_empty"] is None) == bool(block["documents"])


def test_the_immune_risk_names_its_datasets_and_says_who_they_measured(
    client: TestClient,
) -> None:
    block = _risk(_risks(client), Domain.IMMUNE)["data_sources"]
    datasets = {row["id"]: row for row in block["datasets"]}
    # OSD-288 es de ratón; Inspiration4 (OSD-569), de personas: la fila lo dice, no lo calla.
    assert {"osd-288", "osd-569"} <= datasets.keys()
    assert datasets["osd-288"]["population"] == "animal"
    assert datasets["osd-569"]["population"] == "human"
    assert "hrp-risk-immune" in {row["id"] for row in block["documents"]}


def test_a_reference_without_class_is_not_taken_for_a_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cited = evidence_for(Domain.IMMUNE)
    unclassified = [
        type(item)(ref=type(item.ref)(**{
            **{name: getattr(item.ref, name) for name in item.ref.__slots__},
            "evidence_type": None,
        }), relevance=item.relevance)
        for item in cited
    ]
    block = risk_entity.data_sources(unclassified)
    assert block["datasets"] == [] and len(block["documents"]) == len(cited)
    assert block["datasets_empty"] == risk_entity.NO_DATASETS


# --------------------------------------------------------------------------- #
# La contramedida: la biblioteca, una a una
# --------------------------------------------------------------------------- #

def test_the_countermeasures_are_the_library_one_by_one(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        domain = Domain(item["risk_id"])
        expected = [entry for entry in library().values() if entry.domain is domain]
        rows = item["countermeasures"]["items"]
        assert [row["id"] for row in rows] == [entry.id for entry in expected]
        for row, entry in zip(rows, expected, strict=True):
            assert row["action"] == entry.action
            assert row["basis"] == entry.basis
            assert row["basis_display"] == BASIS_DISPLAY[entry.basis]
            # La familia es la que declare la biblioteca, o ninguna: aquí no se deduce.
            assert row["family"] == entry.to_dict().get("family")
        # Lo que cuenta la incertidumbre son las que ofrece el nivel; la de refugio va aparte.
        offered = [row for row in rows if not row["on_event"]]
        assert len(offered) == len(for_domain(domain))
        assert item["uncertainty"]["countermeasures"]["count"] == len(offered)


def test_only_the_shelter_goes_by_event(client: TestClient) -> None:
    rows = [row for item in _risks(client)["risks"] for row in item["countermeasures"]["items"]]
    by_event = [row for row in rows if row["on_event"]]
    assert [row["id"] for row in by_event] == [SHELTER_ID]
    assert by_event[0]["trigger_display"] == risk_entity.ON_EVENT
    assert all(row["trigger_display"] is None for row in rows if not row["on_event"])


# --------------------------------------------------------------------------- #
# La detección: leída del motor
# --------------------------------------------------------------------------- #

def test_the_rule_publishes_the_engine_constants(client: TestClient) -> None:
    body = _risks(client)
    base = _step(body, "baseline")["values"]
    assert base["window_hours"] == baseline.DEFAULT_ROLLING_WINDOW.total_seconds() / 3600
    assert base["lag_hours"] == baseline.DEFAULT_ROLLING_LAG.total_seconds() / 3600
    assert base["min_samples"] == baseline.MIN_SAMPLES
    quantiles = _step(body, "deviation")["values"]["quantiles"]
    assert [(row["quantile"], row["severity"]) for row in quantiles] == [
        (fraction, str(severity)) for fraction, severity in sorted(baseline._QUANTILE_THRESHOLDS)
    ]
    for row in quantiles:
        assert row["min_samples"] == baseline._SAMPLES_FOR_SEVERITY[Severity(row["severity"])]
    persistence = _step(body, "persistence")["values"]
    assert persistence["fraction"] == risk._PERSISTENCE_FRACTION
    assert persistence["current_window_hours"] == routes.CURRENT_WINDOW.total_seconds() / 3600
    assert persistence["representative_percentile"] == risk._FINDING_PERCENTILE
    drift = _step(body, "trend")["values"]
    assert drift["window_hours"] == trend.TREND_WINDOW.total_seconds() / 3600
    assert (drift["min_points"], drift["min_span_days"], drift["t_significance"]) == (
        trend.MIN_POINTS, trend.MIN_SPAN_DAYS, trend.T_SIGNIFICANCE,
    )
    points = _step(body, "points")["values"]
    assert {row["severity"]: row["points"] for row in points["severity_points"]} == {
        str(severity): value for severity, value in risk._SEVERITY_POINTS.items()
        if severity is not Severity.NONE
    }
    assert points["trend_points"] == risk._TREND_POINTS
    assert points["additional_finding_decay"] == risk._ADDITIONAL_FINDING_DECAY
    levels = _step(body, "levels")["values"]["levels"]
    assert sorted(row["min_score"] for row in levels) == sorted(
        minimum for minimum, _ in risk._LEVEL_THRESHOLDS
    )


def test_the_windows_are_the_ones_the_engine_calls_with() -> None:
    import inspect

    rolling = inspect.signature(baseline.BaselineEngine.evaluate_rolling).parameters
    assert rolling["window"].default == baseline.DEFAULT_ROLLING_WINDOW
    assert rolling["lag"].default == baseline.DEFAULT_ROLLING_LAG
    drift = inspect.signature(trend.trends_by_indicator).parameters
    assert drift["window"].default == trend.TREND_WINDOW


@pytest.mark.parametrize(
    ("module", "name", "value", "step", "words"),
    [
        (risk, "_PERSISTENCE_FRACTION", 0.25, "persistence", "el 25 %"),
        (trend, "TREND_WINDOW", dt.timedelta(days=28), "trend", "últimos 28 días"),
        (baseline, "DEFAULT_ROLLING_WINDOW", dt.timedelta(days=10), "baseline", "los 10 días"),
        (baseline, "MIN_SAMPLES", 150, "baseline", "desde 150 lecturas"),
        (risk, "_TREND_POINTS", 15.0, "points", "una deriva, 15"),
        (trend, "T_SIGNIFICANCE", 2.5, "trend", "|t| de 2,5"),
    ],
)
def test_changing_an_engine_constant_changes_the_published_rule(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
    module: Any, name: str, value: Any, step: str, words: str,
) -> None:
    before = _step(_risks(client), step)
    assert words not in before["statement"]
    monkeypatch.setattr(module, name, value)
    after = _step(_risks(client), step)
    assert words in after["statement"]
    # Y las cifras que acompañan a la frase también: ninguna se quedó escrita a mano.
    assert after["values"] != before["values"]


def test_the_current_window_is_the_one_of_the_status_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "CURRENT_WINDOW", dt.timedelta(hours=36))
    persistence = _step(_risks(client), "persistence")
    assert persistence["values"]["current_window_hours"] == 36
    assert "últimos 36 h" in persistence["statement"]


def test_the_published_persistence_classifies_like_the_engine(client: TestClient) -> None:
    fraction = _step(_risks(client), "persistence")["values"]["fraction"]
    readings = 20
    enough = round(readings * fraction)
    assert enough / readings >= fraction > (enough - 1) / readings

    def series(concerning: int) -> list[Deviation]:
        return [
            _deviation("heart-rate", Severity.MILD if index < concerning else Severity.NONE, index)
            for index in range(readings)
        ]

    assert representative_deviation(series(enough)) is not None
    assert representative_deviation(series(enough - 1)) is None


def test_the_burst_ladder_is_the_engine_function(client: TestClient) -> None:
    steps = _step(_risks(client), "persistence")["values"]["burst"]
    assert steps[0]["severe"] == risk._MIN_BURST
    # Un tramo con menos lecturas que las graves que pide sería una ráfaga imposible.
    assert all(step["from_readings"] >= step["severe"] for step in steps)
    for step in steps:
        needed = step["severe"]
        assert risk.min_severe_readings(step["from_readings"]) == needed
        # Una lectura menos: o el motor pide otro número, o no hay ráfaga posible.
        before = step["from_readings"] - 1
        assert risk.min_severe_readings(before) != needed or needed > before
        # Con esa ráfaga el motor da el hallazgo; con una lectura grave menos, no.
        readings = step["from_readings"]

        def series(severe: int, readings: int = readings) -> list[Deviation]:
            return [
                _deviation("heart-rate", Severity.SEVERE if index < severe else Severity.NONE,
                           index)
                for index in range(readings)
            ]

        burst, short = series(needed), series(needed - 1)
        if (needed - 1) / readings < risk._PERSISTENCE_FRACTION:
            assert representative_deviation(burst) is not None
            assert representative_deviation(short) is None


def test_the_isolation_factor_is_read_from_the_engine(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = _risks(client)["detection_rule"]["isolation"]
    assert curve["max_factor"] == risk._MAX_ISOLATION_FACTOR
    assert curve["saturates_at_minutes"] == 40.0
    # Al pasar el umbral de autonomía el factor no arranca en 1: salta, y se dice cuánto.
    threshold = curve["autonomy_above_minutes"]
    assert risk.isolation_factor(risk_entity._probe_comms(threshold)) == 1.0
    assert curve["factor_above_threshold"] == pytest.approx(
        risk.isolation_factor(risk_entity._probe_comms(threshold + 1e-6))
    )
    assert 1.0 < curve["factor_above_threshold"] < curve["max_factor"]
    # Un poco antes del retardo publicado aún no se llega al tope; en él, sí.
    saturation = curve["saturates_at_minutes"]
    assert risk.isolation_factor(risk_entity._probe_comms(saturation - 0.1)) < curve["max_factor"]
    assert risk.isolation_factor(risk_entity._probe_comms(saturation)) == curve["max_factor"]
    monkeypatch.setattr(risk, "_MAX_ISOLATION_FACTOR", 1.5)
    assert _risks(client)["detection_rule"]["isolation"]["max_factor"] == 1.5


def test_the_published_quantile_tails_grade_like_the_engine(client: TestClient) -> None:
    rows = _step(_risks(client), "deviation")["values"]["quantiles"]
    reference = baseline.compute_baseline("x", [float(value) for value in range(2000)])
    for key in ("absorbed-dose-rate", "oxygen-saturation"):
        code = get_code(key)
        rising = code.concerning == "high"
        for row in rows:
            tail = 1.0 - row["quantile"]
            cut = reference.quantile(1.0 - tail if rising else tail)
            assert cut is not None
            value = cut + 0.5 if rising else cut - 0.5
            severity, _ = baseline._severity_from_quantiles(value, reference, code)
            assert str(severity) == row["severity"], (key, row)
    statement = _step(_risks(client), "deviation")["statement"]
    # Se dice como la cola extrema por el lado que preocupa: vale para subir y para bajar.
    assert "percentil" not in statement and "por ese lado" in statement
    for words in (
        "leve si cae en el 1 %", "moderada si cae en el 0,5 %", "grave si cae en el 0,1 %",
    ):
        assert words in statement


def test_a_burst_finding_takes_the_reading_farthest_from_its_base(client: TestClient) -> None:
    statement = _step(_risks(client), "persistence")["statement"]
    assert "por ráfaga, la de la lectura grave más alejada de su base" in statement
    series = [_deviation("heart-rate", Severity.NONE, index) for index in range(280)]
    for index, z_score in ((3, 5.0), (90, 9.0), (200, 7.0)):
        series[index] = Deviation(
            subject="crew-01", key="heart-rate", value=0.0, effective=series[index].effective,
            z_score=z_score, severity=Severity.SEVERE, direction="high", baseline=None,
            used_population_range=True,
        )
    found = representative_deviation(series)
    assert found is not None and found.z_score == 9.0


def test_isolation_applies_to_every_domain_but_radiation(client: TestClient) -> None:
    for item in _risks(client)["risks"]:
        applies = item["detection"]["isolation_applies"]
        assert applies is (item["risk_id"] != str(Domain.RADIATION)), item["risk_id"]
        if applies:
            assert "factor de hasta" in item["detection"]["summary"]
        else:
            assert item["detection"]["isolation_statement"] == risk_entity.NO_ISOLATION


def test_the_isolation_probe_is_what_assess_does() -> None:
    # La sonda no se fía de sí misma: se compara con el motor de la ruta de estado.
    comms = risk_entity._probe_comms(60.0)
    engine = RiskEngine()
    for domain in Domain:
        key = evaluated_by_domain(domain)[-1].key
        burst = [_deviation(key, Severity.MODERATE, index) for index in range(10)]
        near = engine.assess("crew-01", burst).domains[domain].score
        far = engine.assess("crew-01", burst, comms=comms).domains[domain].score
        assert near > 0, domain
        assert (far > near) is risk_entity.isolation_applies(domain), domain


def test_a_domain_without_indicators_cannot_be_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_entity, "evaluated_by_domain", lambda domain: ())
    assert risk_entity.isolation_applies(Domain.BONE) is None
    block = risk_entity.detection(Domain.BONE, {})
    assert block["isolation_statement"] == risk_entity.NO_ISOLATION_PROBE
    assert block["summary"].startswith(risk_entity.NO_INDICATORS_DETECTION)


def test_only_radiation_adds_the_environment_and_with_the_engine_points(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _risks(client)
    for item in body["risks"]:
        keys = [entry["key"] for entry in item["detection"]["environment"]]
        assert keys == (
            ["solar_event", "cumulative_dose"] if item["risk_id"] == "radiation" else []
        ), item["risk_id"]
    found = {e["key"]: e for e in _risk(body, Domain.RADIATION)["detection"]["environment"]}
    # Solo cuentan las severidades que el motor atiende, con lo que suma cada una.
    engine = RiskEngine()
    for row in found["solar_event"]["values"]:
        status = engine.assess("x", [], solar_events=[
            risk_entity._probe_event(SolarSeverity(row["severity"]))
        ])
        assert status.domains[Domain.RADIATION].score == row["points"]
    assert {row["severity"] for row in found["solar_event"]["values"]} == {"high", "severe"}
    assert found["cumulative_dose"]["values"]["points_at_limit"] == risk._DOSE_LIMIT_POINTS
    monkeypatch.setattr(risk, "_DOSE_LIMIT_POINTS", 60.0)
    moved = {
        e["key"]: e for e in _risk(_risks(client), Domain.RADIATION)["detection"]["environment"]
    }
    assert moved["cumulative_dose"]["values"]["points_at_limit"] == 60.0
    assert "60 puntos" in moved["cumulative_dose"]["statement"]


def _label_for(context: Context) -> str:
    if context.family in {Context.REST, Context.SLEEP}:
        return "resting"
    return "exertion" if context is Context.ACTIVE else "general"


def test_the_published_danger_limits_cross_like_the_engine(client: TestClient) -> None:
    rows = [row for item in _risks(client)["risks"] for row in item["detection"]["danger_limits"]]
    assert rows, "ningún límite de peligro publicado"
    for row in rows:
        code = get_code(row["key"])
        for context in Context:
            low, high = row[_label_for(context)]

            def crossed(
                value: float, key: str = code.key, context: Context = context
            ) -> float | None:
                return crossed_danger_limit(
                    observation(key, value, MOMENT, "crew-01", "prueba", context=context)
                )

            for bound, outside in ((low, -1.0), (high, 1.0)):
                if bound is not None:
                    step = max(abs(bound) * 0.01, 0.01)
                    assert crossed(bound + outside * step) == bound, (row["key"], context)
                    assert crossed(bound) is None, (row["key"], context)
            if low is not None and high is not None:
                assert crossed((low + high) / 2) is None, (row["key"], context)


def test_the_state_words_name_the_states_of_each_bound(client: TestClient) -> None:
    rate = next(
        row for row in _risk(_risks(client), Domain.CARDIOVASCULAR)["detection"]["danger_limits"]
        if row["key"] == "heart-rate"
    )
    # El pulso tiene los tres tramos: la frase los nombra a los tres.
    for words in (risk_entity.RESTING_STATES, risk_entity.EXERTION_STATE,
                  risk_entity.OTHER_STATE):
        assert words in rate["statement"]
    for context in (Context.REST, Context.SLEEP, Context.WORK, Context.MEAL):
        assert _label_for(context) == "resting"
    assert _label_for(Context.ACTIVE) == "exertion"
    assert _label_for(Context.UNKNOWN) == "general"


def test_the_rule_says_against_what_it_was_measured(client: TestClient) -> None:
    block = _risks(client)["detection_rule"]["validated_with"]
    assert block["dataset"]["id"] == VALIDATION_DATASET.id == "mmash"
    assert block["dataset"]["evidence_type"] == "dataset"
    # El alcance es el de la ficha: personas sanas en Tierra, no fisiología de vuelo.
    assert block["scope"] == VALIDATION_DATASET.scope_in_view
    assert "no es fisiología de vuelo" in block["scope"]
    assert "compliance/external-validation.md" in block["statement"]


def test_describing_the_matrix_writes_nothing(client: TestClient) -> None:
    store = get_store()
    before = store.count()
    _risks(client)
    assert store.count() == before == 0
    assert "sonda-de-la-matriz" not in store.subjects()


# --------------------------------------------------------------------------- #
# Qué sale de MMASH en cada dominio, y el equipo de cada variable
# --------------------------------------------------------------------------- #

def test_each_risk_names_the_keys_the_mmash_loader_emits(client: TestClient) -> None:
    """Las claves de cada dominio son las de la tabla del cargador, no una lista copiada; entre
    todos los dominios salen todas, una vez."""
    seen: list[str] = []
    for item in _risks(client)["risks"]:
        block = item["validation"]
        expected = [
            code.key for code in evaluated_by_domain(Domain(item["risk_id"]))
            if code.key in mmash.LOADED
        ]
        assert [entry["key"] for entry in block["keys"]] == expected
        for entry in block["keys"]:
            assert entry["source"] == mmash.LOADED[entry["key"]]
            assert entry["source_display"] == mmash.SOURCE_DISPLAY[entry["source"]]
            assert entry["domain"] == item["risk_id"]
        assert block["dataset_id"] == VALIDATION_DATASET.id
        assert block["indicators"] == len(item["indicators"])
        seen.extend(expected)
        flags = {entry["key"] for entry in item["indicators"] if entry["from_mmash"]}
        assert flags == set(expected)
    assert sorted(seen) == sorted(mmash.LOADED_KEYS)


def test_a_domain_with_mmash_keys_says_what_they_validate(client: TestClient) -> None:
    body = _risks(client)
    row = _risk(body, Domain.CARDIOVASCULAR)
    block = row["validation"]
    assert block["keys"] and block["empty"] is None
    assert block["validates"] == mmash.VALIDATES
    # Y hasta dónde llega: sobre todo rango de población y límites, no la base personal.
    assert block["note"] == mmash.VALIDATES_NOTE
    assert block["statement"].endswith(f": {mmash.VALIDATES}.")
    assert "no fisiología espacial" in block["statement"]
    for entry in block["keys"]:
        assert entry["display_es"] in block["statement"]
    # El recuento es el de la fila: tantos de cuantos indicadores tiene el dominio.
    assert block["statement"].startswith(f"{len(block['keys'])} de {len(row['indicators'])} ")


def test_a_domain_without_mmash_keys_says_so(client: TestClient) -> None:
    block = _risk(_risks(client), Domain.RADIATION)["validation"]
    assert block["keys"] == []
    assert block["statement"] == block["empty"] == risk_entity.NO_MMASH
    assert block["validates"] is None and block["note"] is None


def test_the_mmash_keys_are_read_from_the_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cambiar la tabla del cargador cambia lo publicado: no hay segunda copia."""
    monkeypatch.setattr(mmash, "LOADED", {"oxygen-saturation": mmash.POLAR_SOURCE})
    monkeypatch.setattr(mmash, "LOADED_KEYS", ("oxygen-saturation",))
    block = risk_entity.validation(Domain.CARDIOVASCULAR)
    assert [entry["key"] for entry in block["keys"]] == ["oxygen-saturation"]
    assert risk_entity.validation(Domain.BEHAVIORAL)["keys"] == []
    assert [entry["key"] for entry in risk_entity.mmash_keys()] == ["oxygen-saturation"]
    row = _risk(risk_entity.payload(routes.CURRENT_WINDOW), Domain.CARDIOVASCULAR)
    assert [entry["key"] for entry in row["indicators"] if entry["from_mmash"]] == [
        "oxygen-saturation"
    ]


def test_one_mmash_key_reads_in_singular() -> None:
    block = risk_entity.validation(Domain.BONE)
    assert [entry["key"] for entry in block["keys"]] == ["body-weight"]
    assert " indicadores sale de MMASH (" in block["statement"]


def test_the_rule_lists_every_mmash_key_in_loader_order(client: TestClient) -> None:
    block = _risks(client)["detection_rule"]["validated_with"]
    assert [entry["key"] for entry in block["keys"]] == list(mmash.LOADED_KEYS)
    assert block["validates"] == mmash.VALIDATES
    assert block["note"] == mmash.VALIDATES_NOTE
    assert block["keys_basis"] == risk_entity.MMASH_BASIS


def test_each_variable_carries_its_equipment_from_the_cost(client: TestClient) -> None:
    declared = costs()
    for item in _risks(client)["risks"]:
        for entry in item["indicators"]:
            assert entry["equipment"] == declared[entry["key"]]["equipment"]
        # Los grupos reparten los indicadores de la fila, en su orden, sin repetir ninguno.
        groups = item["equipment"]["groups"]
        flat = [indicator["key"] for group in groups for indicator in group["indicators"]]
        assert sorted(flat) == sorted(entry["key"] for entry in item["indicators"])
        assert len({group["equipment"] for group in groups}) == len(groups)
        for group in groups:
            for indicator in group["indicators"]:
                assert declared[indicator["key"]]["equipment"] == group["equipment"]
        firsts = [group["indicators"][0]["key"] for group in groups]
        order = [entry["key"] for entry in item["indicators"]]
        assert firsts == sorted(firsts, key=order.index)


def test_a_variable_without_equipment_says_so() -> None:
    codes = evaluated_by_domain(Domain.CARDIOVASCULAR)
    block = risk_entity.equipment(Domain.CARDIOVASCULAR, {codes[0].key: "banda"})
    assert block["groups"][0] == {
        "equipment": "banda",
        "indicators": [{"key": codes[0].key, "display_es": codes[0].display_es}],
    }
    assert block["groups"][1]["equipment"] == risk_entity.NO_EQUIPMENT
    assert len(block["groups"][1]["indicators"]) == len(codes) - 1


def test_the_equipment_is_read_from_the_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """El equipo publicado es el del coste de medir en cada consulta."""
    altered = {key: {**item, "equipment": "otro"} for key, item in costs().items()}
    monkeypatch.setattr(risk_entity, "costs", lambda: altered)
    body = risk_entity.payload(routes.CURRENT_WINDOW)
    groups = _risk(body, Domain.CARDIOVASCULAR)["equipment"]["groups"]
    assert [group["equipment"] for group in groups] == ["otro"]


def test_an_empty_equipment_reads_the_same_in_the_variable_and_its_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    altered = {key: {**item, "equipment": ""} for key, item in costs().items()}
    monkeypatch.setattr(risk_entity, "costs", lambda: altered)
    row = _risk(risk_entity.payload(routes.CURRENT_WINDOW), Domain.CARDIOVASCULAR)
    assert {entry["equipment"] for entry in row["indicators"]} == {None}
    assert [group["equipment"] for group in row["equipment"]["groups"]] == [
        risk_entity.NO_EQUIPMENT
    ]
