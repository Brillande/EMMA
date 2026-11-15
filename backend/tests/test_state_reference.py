"""Un solo «ahora» para lo que decide (decimoctava ronda, §5.38.7).

La fusión de la ronda 17 dejó dos reglas para el «ahora» del estado: `_assess` apartaba antes los
indicadores descriptivos y lo inferido o predicho, y la radiación del hábitat no apartaba nada
(una lectura predicha fechada en el futuro movía su «ahora», y la «última tasa de dosis» podía ser
inferida o predicha). Las rutinas y las sesiones PVT apartaban lo no medido pero no lo descriptivo.
Ahora todas piden el «ahora» a `routes.state_reference`, y aquí se comprueba, sin red:

- que nadie en `app/` llama a `_analysable` fuera de `state_reference` (en el código, por AST);
- que una lectura predicha o descriptiva fechada en el futuro no mueve la radiación del hábitat,
  la del gemelo, las rutinas ni las sesiones PVT, y que la misma lectura MEDIDA sí lo haría (el
  testigo: la prueba no es ciega);
- que la última tasa de dosis del hábitat es la que lee el estado (medida), no una inferida;
- que `/crew/compare` cuenta lo que aparta, como el estado, y no compara un descriptivo;
- que `GET /api/crew` con un `until` sin zona es un 422, como las demás rutas con corte.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_support
from app.api import routes
from app.ingest.codes import get
from app.ingest.fhir import ObservationType, VitalObservation

APP = Path(__file__).resolve().parents[1] / "app"
T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
# Lejos de los datos y en grupo de tres: si contaran, `_analysable` los tomaría por un flujo y
# llevaría el «ahora» hasta ellos (con uno suelto no basta: se aparta solo).
FUTURE = [T0 + dt.timedelta(days=30, hours=hour) for hour in range(3)]


def _post(
    client: TestClient, key: str, value: float, when: dt.datetime, kind: str = "measured",
    subject: str = "crew-01", source: str | None = None,
) -> None:
    body: dict[str, Any] = {
        "key": key, "value": value, "subject": subject, "effective": when.isoformat(),
        "observation_type": kind,
    }
    if kind != "measured":
        body["model_version"] = "modelo-de-prueba@1"
    if source is not None:
        body["source"] = source
    response = client.post("/api/observations", json=body)
    assert response.status_code == 201, response.text


def _flow(client: TestClient, subject: str = "crew-01") -> None:
    """Un día de pulso y tasa de dosis medidos, cada hora: un flujo con su «ahora» en T0+23 h."""
    for hour in range(24):
        when = T0 + dt.timedelta(hours=hour)
        _post(client, "heart-rate", 60.0, when, subject=subject)
        _post(client, "absorbed-dose-rate", 12.0, when, subject=subject, source="dosimeter")


def _future(client: TestClient, kind: str) -> None:
    """Tres lecturas en el futuro: predichas de pulso, o de un descriptivo (fuerza de prensión)."""
    for when in FUTURE:
        if kind == "descriptive":
            _post(client, "grip-strength-right", 40.0, when)
        else:
            _post(client, "heart-rate", 60.0, when, kind=kind)


def _dose_rates(client: TestClient, **params: Any) -> list[tuple[str, float, str, str]]:
    response = client.get("/api/habitat", params=params)
    assert response.status_code == 200, response.text
    return [
        (item["subject"], item["value"], item["effective"], item["observation_type"])
        for item in response.json()["radiation"]["dose_rate"]["readings"]
    ]


def _habitat_note(client: TestClient) -> list[str]:
    body = client.get("/api/twins", params={"subject": "crew-01"}).json()
    layer = next(item for item in body["questions"] if item["key"] == "habitat")
    notes: list[str] = layer["notes"]
    return notes


# --------------------------------------------------------------------------- #
# La guarda: nadie más llama a `_analysable`
# --------------------------------------------------------------------------- #


def _calls_to_analysable(tree: ast.AST) -> list[ast.expr]:
    """Toda mención de `_analysable` que no es su definición: llamada, alias o atributo.

    No solo las llamadas: `f = routes._analysable` y luego `f(...)` es la misma regla propia.
    Un `getattr` con el nombre en una cadena también cuenta.
    """
    return [
        node for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == "_analysable")
        or (isinstance(node, ast.Attribute) and node.attr == "_analysable")
        or (isinstance(node, ast.Constant) and node.value == "_analysable")
    ]


def test_only_state_reference_calls_analysable() -> None:
    """Un filtro propio antes de `_analysable` es otra regla del «ahora»: ya pasó una vez."""
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        name = path.relative_to(APP).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "_analysable" for alias in node.names
            ):
                offenders.append(f"{name}:{node.lineno} importa _analysable")
        allowed: set[int] = set()
        if name == "api/routes.py":
            [helper] = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "state_reference"
            ]
            allowed = {id(call) for call in _calls_to_analysable(helper)}
            assert len(allowed) == 1, "state_reference llama a _analysable una vez"
        offenders.extend(
            f"{name}:{call.lineno} menciona _analysable"
            for call in _calls_to_analysable(tree) if id(call) not in allowed
        )
    assert offenders == [], offenders


def test_the_guard_sees_a_call_written_either_way() -> None:
    """El testigo de la guarda: las dos formas de llamarla, un alias y un `getattr`."""
    tree = ast.parse(
        "a = _analysable(x)\nb = routes._analysable(y)\nf = routes._analysable\n"
        "g = getattr(routes, '_analysable')\n"
    )
    assert len(_calls_to_analysable(tree)) == 4


def test_state_reference_is_the_rule_of_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lee `decides` del módulo, no una copia: si la regla cambia, cambia el «ahora» de todos."""
    seen: list[str] = []

    def spy(observation: Any) -> bool:
        seen.append(observation.key)
        return False

    monkeypatch.setattr(routes, "decides", spy)
    reading = VitalObservation(
        code=get("heart-rate"), value=60.0, effective=T0, subject="crew-01", source="sensor",
    )
    kept, _, _ = routes.state_reference([reading])
    assert seen == ["heart-rate"] and kept == []


# --------------------------------------------------------------------------- #
# La radiación del hábitat y la del gemelo
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["predicted", "descriptive"])
def test_a_future_predicted_or_descriptive_reading_does_not_move_the_habitat_radiation(
    client: TestClient, kind: str
) -> None:
    _flow(client)
    # Una tasa de dosis medida con el reloj roto, sola, un mes después: el estado la aparta.
    _post(client, "absorbed-dose-rate", 999.0, FUTURE[1], source="dosimeter")
    before, note_before = _dose_rates(client), _habitat_note(client)
    assert [value for _, value, _, _ in before] == [12.0]
    status = client.get("/api/status").json()

    _future(client, kind)
    assert _dose_rates(client) == before
    assert _habitat_note(client) == note_before
    # Y el estado tampoco se movió: el hábitat dice lo mismo que él.
    assert client.get("/api/status").json()["data"]["reference_time"] == (
        status["data"]["reference_time"]
    )


def test_the_same_future_readings_measured_do_move_it(client: TestClient) -> None:
    """El testigo: tres lecturas medidas en el futuro sí llevan el «ahora» hasta ellas."""
    _flow(client)
    _post(client, "absorbed-dose-rate", 999.0, FUTURE[1], source="dosimeter")
    _future(client, "measured")
    assert [value for _, value, _, _ in _dose_rates(client)] == [999.0]


def test_the_last_dose_rate_is_the_measured_one_the_state_reads(client: TestClient) -> None:
    """La tasa de dosis la lee el estado solo medida: la excepción `DOSE_TYPES` es de la dosis
    acumulada frente al límite de carrera, no de la tasa."""
    _flow(client)
    last = T0 + dt.timedelta(hours=23)
    # Dentro del flujo y después de la última medida: con todas las lecturas, sería «la última».
    _post(client, "absorbed-dose-rate", 80.0, last + dt.timedelta(minutes=30), kind="inferred")
    _post(client, "absorbed-dose-rate", 90.0, last + dt.timedelta(minutes=40), kind="predicted")
    assert _dose_rates(client) == [("crew-01", 12.0, last.isoformat(), "measured")]
    assert ObservationType.INFERRED in routes.DOSE_TYPES  # la excepción sigue, intacta


def test_crew_overview_and_the_habitat_read_the_same_doses(client: TestClient) -> None:
    """`/api/crew` correlaciona con la dosimetría que leyó cada estado; el hábitat enseña la
    última de esas mismas."""
    _flow(client, "crew-01")
    _flow(client, "crew-02")
    _future(client, "predicted")
    response = client.get("/api/crew")
    assert response.status_code == 200, response.text
    references = {item["subject"]: item["reference_time"] for item in response.json()["crew"]}
    for subject, _, effective, _ in _dose_rates(client):
        assert effective == references[subject]


# --------------------------------------------------------------------------- #
# Rutinas y sesiones PVT: el «ahora» del estado, también sin los descriptivos
# --------------------------------------------------------------------------- #


def test_a_future_descriptive_reading_does_not_move_the_routines(client: TestClient) -> None:
    _flow(client)
    before = client.get("/api/timeline/routines").json()
    assert before["now_source"] == "data"
    _future(client, "descriptive")
    assert client.get("/api/timeline/routines").json() == before


def test_the_same_readings_measured_do_move_the_routines(client: TestClient) -> None:
    _flow(client)
    before = client.get("/api/timeline/routines").json()
    _future(client, "measured")
    assert client.get("/api/timeline/routines").json() != before


def test_a_future_descriptive_reading_does_not_move_the_pvt_sessions(client: TestClient) -> None:
    _flow(client)
    protocol = client.get("/api/pvt/protocol").json()
    trials = protocol["session"]["trials"]
    session = {
        "reaction_times_ms": [250.0] * trials, "subject": "crew-01",
        "effective": (T0 + dt.timedelta(hours=12)).isoformat(),
    }
    assert client.post("/api/pvt", json=session).status_code == 201
    before = client.get("/api/pvt/sessions").json()
    _future(client, "descriptive")
    assert client.get("/api/pvt/sessions").json() == before
    # El testigo: medidas, lo mueven (la sesión deja de estar en la ventana actual).
    _future(client, "measured")
    assert client.get("/api/pvt/sessions").json() != before


# --------------------------------------------------------------------------- #
# La comparación entre tripulantes y `GET /api/crew`
# --------------------------------------------------------------------------- #


def test_crew_compare_counts_what_it_sets_aside_like_the_state(client: TestClient) -> None:
    _flow(client, "crew-01")
    _flow(client, "crew-02")
    for hour, kind in ((3, "inferred"), (4, "inferred"), (5, "predicted")):
        _post(client, "heart-rate", 185.0, T0 + dt.timedelta(hours=hour), kind=kind)
    body = client.get("/api/crew/compare", params={"key": "heart-rate"}).json()
    series = {item["subject"]: item for item in body["series"]}
    assert series["crew-01"]["set_aside"] == {"inferred": 2, "predicted": 1}
    expected = alert_support.typed_readings({"inferred": 2, "predicted": 1})
    assert series["crew-01"]["set_aside_text"].startswith(f"{expected} de este indicador")
    assert series["crew-02"]["set_aside"] == {} and series["crew-02"]["set_aside_text"] is None
    # Lo mismo que cuenta el estado de crew-01.
    status = client.get("/api/status", params={"subject": "crew-01"}).json()
    assert status["provenance"]["set_aside"] == series["crew-01"]["set_aside"]


def test_crew_compare_does_not_judge_a_descriptive_indicator(client: TestClient) -> None:
    _flow(client, "crew-01")
    _flow(client, "crew-02")
    for subject in ("crew-01", "crew-02"):
        for hour in range(3):
            _post(client, "grip-strength-right", 40.0, T0 + dt.timedelta(hours=hour),
                  subject=subject)
    response = client.get("/api/crew/compare", params={"key": "grip-strength-right"})
    assert response.status_code == 422
    assert "descriptivo" in response.json()["detail"]


def test_crew_overview_rejects_a_cut_without_time_zone(client: TestClient) -> None:
    _flow(client)
    response = client.get("/api/crew", params={"until": "2026-12-01T12:00:00"})
    assert response.status_code == 422, response.text
    assert "zona horaria" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Sin nada que decida no hay «ahora»: ni el diario ni las sesiones PVT dan la cota
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("path", "field"), [("/api/diary/entries", "entries"), ("/api/pvt/sessions", "sessions")]
)
def test_without_anything_that_decides_the_reference_is_null(
    client: TestClient, path: str, field: str
) -> None:
    """Solo descriptivos y predichos: `_analysable` responde con su cota, que no es un «ahora»."""
    _future(client, "descriptive")
    _future(client, "predicted")
    body = client.get(path).json()
    assert body["reference_time"] is None, body
    # El testigo: con un flujo medido, sí hay «ahora».
    _flow(client)
    assert client.get(path).json()["reference_time"] == (T0 + dt.timedelta(hours=23)).isoformat()
    assert field in body
