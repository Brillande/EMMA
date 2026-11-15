"""Solo lo medido decide (decimoseptima ronda, §5.37.1; decision del usuario del 2026-10-26).

La especificacion del equipo (§2 «Uncertainty first», §10 y §14) pide separar lo medido de lo
inferido y lo predicho. `POST /api/observations` acepta las tres clases, y hasta ahora el estado
las metia todas en la linea base, la tendencia y el riesgo. Aqui se comprueba, sin red:

- una lectura inferida o predicha, por extrema que sea, no mueve niveles, alertas, puntuaciones
  ni el «ahora» de los datos; la misma lectura MEDIDA si los mueve (la prueba no es ciega);
- se firma igual en el ledger y el estado la cuenta como «sin decidir», con su nota;
- una dosis acumulada inferida no llega al limite de carrera, y se dice;
- la regla entra en `rules_version`;
- el detalle de alerta dice el tipo de las lecturas que la causaron y el corte personal que
  cruzaron, el mismo con que el motor las graduo;
- la cronica, el diario y la comparacion entre tripulantes apartan lo mismo que el estado.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_support
from app.analysis.baseline import (
    Baseline,
    Deviation,
    Severity,
    SeverityBasis,
    _severity_from_quantiles,
    crossed_personal_cut,
)
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.ingest.codes import get
from app.ingest.fhir import ObservationType
from app.main import app

# Fuera de todo rango y por el lado que preocupa: si entrara en el motor, se notaria.
EXTREME = {"heart-rate": 185.0, "oxygen-saturation": 80.0, "systolic-bp": 190.0}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _status(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/status")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _verdict(status: dict[str, Any]) -> tuple[Any, ...]:
    return (
        status["overall_level"],
        {key: (item["level"], item["score"]) for key, item in status["domains"].items()},
        [(item["id"], item["level"]) for item in status["alerts"]],
        status["data"]["reference_time"],
        status["data"]["observations"],
    )


def _post(
    client: TestClient, key: str, value: float, when: dt.datetime, kind: str = "measured",
    subject: str = "crew-01",
) -> None:
    body: dict[str, Any] = {
        "key": key, "value": value, "subject": subject, "effective": when.isoformat(),
        "observation_type": kind,
    }
    if kind != "measured":
        body["model_version"] = "modelo-de-prueba@1"
    response = client.post("/api/observations", json=body)
    assert response.status_code == 201, response.text


def _seed(client: TestClient) -> dt.datetime:
    assert client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 14}
    ).status_code == 201
    return dt.datetime.fromisoformat(_status(client)["data"]["reference_time"])


def _flood(client: TestClient, reference: dt.datetime, kind: str) -> None:
    # Dentro de la ventana actual y, tres, un mes despues de la referencia: tres bastan para que
    # `_analysable` las tome como un flujo y mueva el «ahora» si entraran.
    for offset in (dt.timedelta(hours=-3), dt.timedelta(hours=-2), dt.timedelta(hours=-1)):
        for key, value in EXTREME.items():
            _post(client, key, value, reference + offset, kind)
    for hours in (0, 1, 2):
        _post(client, "heart-rate", 185.0, reference + dt.timedelta(days=30, hours=hours), kind)


# --------------------------------------------------------------------------- #
# El estado
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["inferred", "predicted"])
def test_an_inferred_or_predicted_reading_does_not_move_the_verdict(
    client: TestClient, kind: str
) -> None:
    reference = _seed(client)
    before = _status(client)
    _flood(client, reference, kind)
    after = _status(client)
    assert _verdict(after) == _verdict(before)
    # Firmadas y legibles: se guardan, no se tiran.
    stored = client.get(
        "/api/observations",
        params={"subject": "crew-01", "key": "oxygen-saturation", "limit": 5000},
    ).json()["observations"]
    assert sum(
        1 for item in stored
        for ext in item.get("extension", [])
        if ext.get("valueCode") == kind
    ) == 3
    # El estado las cuenta como «sin decidir» y lo dice.
    assert after["provenance"]["set_aside"] == {kind: 12}
    assert after["provenance"]["observation_type"] == before["provenance"]["observation_type"]
    assert after["provenance"]["rule"] == alert_support.ANALYSED_RULE
    word = alert_support.TYPE_WORDS[kind][1]
    assert any(note.startswith(f"12 lecturas {word} se guardan") for note in after["notes"])
    assert not any("se guardan en el registro" in note for note in before["notes"])


def test_the_same_readings_measured_do_move_it(client: TestClient) -> None:
    """El testigo: sin el filtro, lo de arriba se notaria."""
    reference = _seed(client)
    before = _status(client)
    _flood(client, reference, "measured")
    after = _status(client)
    assert after["domains"]["cardiovascular"] != before["domains"]["cardiovascular"]
    assert after["provenance"]["set_aside"] == {}


def test_a_subject_with_only_inferred_readings_has_no_state_and_is_told_why(
    client: TestClient,
) -> None:
    _post(client, "heart-rate", 70.0, dt.datetime(2026, 10, 1, 9, tzinfo=dt.UTC), "inferred")
    response = client.get("/api/status")
    assert response.status_code == 404
    assert "inferidas o predichas" in response.json()["detail"]


def test_an_inferred_cumulative_dose_reaches_the_career_limit(client: TestClient) -> None:
    """La excepcion declarada (`DOSE_TYPES`): la dosis efectiva es inferida por definicion."""
    reference = _seed(client)
    _post(client, "cumulative-dose", 700.0, reference - dt.timedelta(hours=1), "inferred")
    status = _status(client)
    assert status["dose"]["cumulative_msv"] == 700.0
    assert status["dose"]["source"] == "observation"
    assert status["dose"]["set_aside"] is None
    assert status["domains"]["radiation"]["level"] != "nominal"
    # No entra en la linea base ni en la tendencia: sigue apartada y contada.
    assert status["provenance"]["set_aside"] == {"inferred": 1}
    # La historia recalculada lee la misma dosis que el estado.
    history = client.get("/api/alerts/history")
    assert history.status_code == 200, history.text
    # Y el modo anatomico la ensena, rotulada.
    anatomy = client.get("/api/anatomy/state").json()
    shown = [
        variable for region in anatomy["regions"] for variable in region["variables"]
        if variable["key"] == "cumulative-dose"
    ]
    assert shown and all(item["observation_type"] == "inferred" for item in shown)
    assert all(item["value"] == 700.0 and item["contributes"] for item in shown)


def test_a_predicted_cumulative_dose_does_not_reach_the_limit_and_is_said(
    client: TestClient,
) -> None:
    reference = _seed(client)
    _post(client, "cumulative-dose", 700.0, reference - dt.timedelta(hours=1), "predicted")
    status = _status(client)
    assert status["dose"]["cumulative_msv"] != 700.0
    assert status["dose"]["set_aside"] == {
        "value_msv": 700.0,
        "effective": (reference - dt.timedelta(hours=1)).isoformat(),
        "recorded_type": "predicted",
    }
    said = "La dosis acumulada registrada como predicha (700"
    assert any(note.startswith(said) for note in status["notes"])
    # Medida, si cuenta.
    _post(client, "cumulative-dose", 700.0, reference - dt.timedelta(minutes=30))
    assert _status(client)["dose"]["cumulative_msv"] == 700.0


def test_the_wording_of_the_rule_follows_the_rule() -> None:
    """`ANALYSED_RULE` y las notas dicen «solo lo medido»: si la regla cambia, el texto tambien."""
    assert routes.ANALYSED_TYPES == (ObservationType.MEASURED,), (
        "cambio la regla: reescriba `alert_support.ANALYSED_RULE`, la nota de `_set_aside_notes` "
        "y el mensaje de 404 de `_assess`"
    )
    assert routes.DOSE_TYPES == (ObservationType.MEASURED, ObservationType.INFERRED), (
        "cambio la excepcion de la dosis: reescriba la nota de `_set_aside_notes`"
    )


def test_the_rule_is_in_the_rules_version(monkeypatch: pytest.MonkeyPatch) -> None:
    assert {"ANALYSED_TYPES", "DOSE_TYPES"} <= set(versioning.FINGERPRINTED["app.api.routes"])
    parameters = versioning.rules()["parameters"]["app.api.routes"]
    assert parameters["ANALYSED_TYPES"] == ["measured"]
    assert parameters["DOSE_TYPES"] == ["measured", "inferred"]
    before = versioning.fingerprint(versioning.rules())
    monkeypatch.setattr(
        routes, "ANALYSED_TYPES", (ObservationType.MEASURED, ObservationType.INFERRED)
    )
    assert versioning.fingerprint(versioning.rules()) != before
    monkeypatch.undo()
    monkeypatch.setattr(routes, "DOSE_TYPES", (ObservationType.MEASURED,))
    assert versioning.fingerprint(versioning.rules()) != before


def test_the_filter_reads_the_rule_and_not_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quien cambie `ANALYSED_TYPES` cambia lo que decide: no hay otra lista en otro sitio."""
    from app.ingest.fhir import observation

    when = dt.datetime(2026, 10, 1, 9, tzinfo=dt.UTC)
    inferred = observation(
        "heart-rate", 70.0, when, "crew-01", "m", observation_type=ObservationType.INFERRED,
        model_version="m@1",
    )
    assert not routes.decides(inferred)
    monkeypatch.setattr(
        routes, "ANALYSED_TYPES", (ObservationType.MEASURED, ObservationType.INFERRED)
    )
    assert routes.decides(inferred)


# --------------------------------------------------------------------------- #
# El detalle de alerta
# --------------------------------------------------------------------------- #


def test_the_alert_detail_says_the_type_and_the_personal_cut(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 14}
    ).status_code == 201
    status = _status(client)
    changed = [item for alert in status["alerts"] for item in alert["detail"]["changed"]]
    assert changed, "el escenario no da ninguna alerta con lecturas: la prueba no comprueba nada"
    personal = [item for item in changed if item["basis"] == "personal-percentile"]
    assert personal
    for item in changed:
        assert item["observation_type"] == "measured", item["key"]
    for item in personal:
        cut = item["personal_cut"]
        assert cut["applies"] is True, item["key"]
        assert cut["unit"] == get(item["key"]).unit
        assert cut["percentile"] in {99.0, 99.5, 99.9, 1.0, 0.5, 0.1}
        side = "Por encima" if item["direction"] == "high" else "Por debajo"
        assert cut["statement"].startswith(f"{side} del percentil ")
    for alert in status["alerts"]:
        readings = alert["detail"]["readings"]
        assert readings["set_aside"] == {}
        assert readings["rule"] == alert_support.ANALYSED_RULE
        if alert["detail"]["changed"]:
            assert set(readings["causes"]) == {"measured"}
            assert readings["statement"].endswith("lecturas medidas.") or readings[
                "statement"
            ].endswith("lectura medida.")


def test_the_alert_detail_counts_what_did_not_decide_in_its_window(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 14}
    ).status_code == 201
    before = _status(client)
    cardio = [item for item in before["alerts"] if item["domain"] == "cardiovascular"]
    assert cardio, "el escenario no da alerta cardiovascular: la prueba no comprueba nada"
    reference = dt.datetime.fromisoformat(before["data"]["reference_time"])
    _post(client, "heart-rate", 185.0, reference - dt.timedelta(hours=1), "inferred")
    _post(client, "heart-rate", 186.0, reference - dt.timedelta(hours=2), "predicted")
    # Fuera de la ventana actual: no cuenta en el detalle.
    _post(client, "heart-rate", 187.0, reference - dt.timedelta(days=5), "inferred")
    after = _status(client)
    [alert] = [item for item in after["alerts"] if item["domain"] == "cardiovascular"]
    readings = alert["detail"]["readings"]
    assert readings["set_aside"] == {"inferred": 1, "predicted": 1}
    assert "En la ventana hay además 1 lectura inferida y 1 predicha de este dominio" in (
        readings["statement"]
    )
    assert after["provenance"]["set_aside"] == {"inferred": 2, "predicted": 1}
    # Y el detalle no cambia en lo que decide.
    assert [item["key"] for item in alert["detail"]["changed"]] == [
        item["key"] for item in cardio[0]["detail"]["changed"]
    ]


# --------------------------------------------------------------------------- #
# El corte personal: la misma regla con que se gradua
# --------------------------------------------------------------------------- #


def _baseline(samples: int) -> Baseline:
    values = tuple(float(value) for value in range(samples))
    return Baseline(
        key="heart-rate", center=(samples - 1) / 2, spread=samples / 6, samples=samples,
        sorted_values=values,
    )


@pytest.mark.parametrize("value", [-5.0, 0.2, 0.6, 5.0, 500.0, 989.5, 994.8, 995.6, 999.5, 1200.0])
def test_the_cut_is_the_one_that_grades(value: float) -> None:
    baseline = _baseline(1000)
    for key in ("heart-rate", "oxygen-saturation", "hrv-sdnn", "circadian-shift"):
        code = get(key)
        severity, _ = _severity_from_quantiles(value, baseline, code)
        cut = crossed_personal_cut(value, baseline, code)
        assert (cut.severity if cut is not None else Severity.NONE) is severity, (key, value)


def test_the_cut_says_percentile_and_value_in_its_unit() -> None:
    baseline = _baseline(1000)
    high = Deviation(
        subject="crew-01", key="heart-rate", value=1200.0,
        effective=dt.datetime(2026, 10, 1, tzinfo=dt.UTC), z_score=9.0, severity=Severity.SEVERE,
        direction="high", baseline=baseline, used_population_range=False,
        basis=SeverityBasis.PERSONAL_PERCENTILE,
    )
    cut = alert_support.personal_cut(high)
    assert cut["applies"] is True
    assert cut["percentile"] == 99.9
    assert cut["value"] == pytest.approx(baseline.quantile(0.999), abs=1e-4)
    assert cut["unit"] == "/min"
    assert cut["statement"] == (
        "Por encima del percentil 99,9 de su línea base personal (998 /min, sobre 1000 lecturas)."
    )
    low = Deviation(
        subject="crew-01", key="oxygen-saturation", value=-5.0,
        effective=dt.datetime(2026, 10, 1, tzinfo=dt.UTC), z_score=-9.0, severity=Severity.SEVERE,
        direction="low", baseline=baseline, used_population_range=False,
        basis=SeverityBasis.DANGER_LIMIT, danger_limit=88.0,
    )
    cut = alert_support.personal_cut(low)
    assert cut["percentile"] == 0.1
    assert cut["statement"].startswith("Por debajo del percentil 0,1 de su línea base personal")
    assert cut["statement"].endswith("La gravedad la decide el límite de peligro, no este corte.")
    population = Deviation(
        subject="crew-01", key="oxygen-saturation", value=80.0,
        effective=dt.datetime(2026, 10, 1, tzinfo=dt.UTC), z_score=-9.0, severity=Severity.SEVERE,
        direction="low", baseline=None, used_population_range=True,
        basis=SeverityBasis.DANGER_LIMIT, danger_limit=88.0,
    )
    assert alert_support.personal_cut(population)["applies"] is False


def test_typed_readings_names_the_noun_once() -> None:
    assert alert_support.typed_readings({"measured": 3, "inferred": 1}) == (
        "3 lecturas medidas y 1 inferida"
    )
    assert alert_support.typed_readings({"predicted": 1}) == "1 lectura predicha"
    assert alert_support.typed_readings(
        {"measured": 2, "inferred": 2, alert_support.NOT_LOCATED: 1}
    ) == "2 lecturas medidas, 2 inferidas y 1 sin localizar en el registro"


# --------------------------------------------------------------------------- #
# Lo que juzga o situa con las reglas del estado fuera de `_assess`
# --------------------------------------------------------------------------- #


def test_crew_compare_judges_only_what_is_measured(client: TestClient) -> None:
    reference = _seed(client)
    before = client.get("/api/crew/compare", params={"key": "heart-rate"})
    assert before.status_code == 200, before.text
    _flood(client, reference, "inferred")
    after = client.get("/api/crew/compare", params={"key": "heart-rate"})
    # Lo juzgado, igual; lo apartado, contado como lo cuenta el estado (§5.38.7).
    judged, counted = _without_set_aside(after.json())
    assert judged == _without_set_aside(before.json())[0]
    assert counted == [({"inferred": 6}, True)]
    assert after.json()["series"][0]["set_aside_text"].startswith(
        "6 lecturas inferidas de este indicador"
    )


def _without_set_aside(body: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    """La comparación sin lo apartado, y lo apartado de cada serie (recuento, si tiene frase)."""
    series = [
        {key: value for key, value in item.items() if not key.startswith("set_aside")}
        for item in body["series"]
    ]
    counted = [
        (item["set_aside"], item["set_aside_text"] is not None) for item in body["series"]
    ]
    return {**body, "series": series}, counted


def test_the_diary_reference_ignores_a_predicted_reading_in_the_future(client: TestClient) -> None:
    reference = _seed(client)
    before = client.get("/api/diary/entries", params={"subject": "crew-01"})
    assert before.status_code == 200, before.text
    for hours in (24 * 30, 24 * 31, 24 * 32):
        _post(client, "heart-rate", 70.0, reference + dt.timedelta(hours=hours), "predicted")
    after = client.get("/api/diary/entries", params={"subject": "crew-01"})
    assert after.json() == before.json()
