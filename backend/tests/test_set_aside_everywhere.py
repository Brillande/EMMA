"""Lo que decide, dicho en todas partes (decimonovena ronda, §5.39.11).

Desde §5.37.1 solo lo medido decide y desde §5.38.7 el «ahora» es uno. Quedaban dos sitios que
apartaban sin decirlo: la radiación del hábitat, donde un tripulante cuya tasa de dosis solo llega
inferida desaparecía de la lista sin una nota (y con él la nota del gemelo, que hereda el
resumen); y el diario y las sesiones PVT, que situaban una entrada inferida o predicha por su
fecha frente al «ahora» («anterior a la ventana»), como si el estado la hubiera leído, y sin nada
que decidiera, frente a la cota. Aquí se comprueba, sin red:

- que el hábitat cuenta lo que aparta como lo cuenta `/crew/compare` (quién, cuántas, de qué
  tipo), con una frase distinta para quien no tiene ninguna medida que enseñar, y que el resumen
  —y con él la nota del gemelo— lo lleva; que Tierra cuenta solo lo que le ha llegado;
- que una entrada del diario o una sesión PVT inferida o predicha tiene su posición propia
  (`not-analysed-by-type`), con su tipo en la frase, y que sin nada que decida ninguna entrada se
  sitúa frente a la cota;
- que nada de esto decide, firma ni suena a orden.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_support
from app.api import diary, habitat, routes
from app.api.routes import get_store
from app.environment import habitat as cabin
from app.ingest.fhir import ObservationType
from app.text_guard import check
from tests.test_habitat_sources import _verdict

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
# Ocho lecturas por hora bastan para un «ahora» corroborado (`routes._REFERENCE_SUPPORT`); un
# día entero por tripulante hacía de este fichero el más lento de la campaña de mutantes.
FLOW_HOURS = 8
LAST = T0 + dt.timedelta(hours=FLOW_HOURS - 1)


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


def _flow(client: TestClient, subject: str = "crew-01", dose: bool = True) -> None:
    """Pulso medido cada hora (y, si se pide, tasa de dosis): su «ahora» es `LAST`."""
    for hour in range(FLOW_HOURS):
        when = T0 + dt.timedelta(hours=hour)
        _post(client, "heart-rate", 60.0, when, subject=subject)
        if dose:
            _post(client, "absorbed-dose-rate", 12.0, when, subject=subject, source="dosimeter")


def _modelled_doses(client: TestClient, subject: str, count: int) -> None:
    """Tasas de dosis que solo llegan inferidas (modeladas, como las que saldrían de RadLab)."""
    for hour in range(count):
        _post(
            client, "absorbed-dose-rate", 11.0, T0 + dt.timedelta(hours=hour), kind="inferred",
            subject=subject, source="radlab-model",
        )


def _radiation(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/habitat", params=params)
    assert response.status_code == 200, response.text
    radiation: dict[str, Any] = response.json()["radiation"]
    return radiation


def _habitat_notes(client: TestClient, subject: str) -> list[str]:
    body = client.get("/api/twins", params={"subject": subject}).json()
    layer = next(item for item in body["questions"] if item["key"] == "habitat")
    notes: list[str] = layer["notes"]
    return notes


# --------------------------------------------------------------------------- #
# La radiación del hábitat cuenta lo que aparta, y el gemelo lo hereda
# --------------------------------------------------------------------------- #


def test_a_crew_member_whose_dose_rate_only_arrives_inferred_is_named_with_why(
    client: TestClient,
) -> None:
    _flow(client, "crew-01")
    _flow(client, "crew-02", dose=False)
    _modelled_doses(client, "crew-02", 5)

    radiation = _radiation(client)
    # Sigue fuera de la lista (es la regla del estado), pero ya no desaparece sin más.
    assert [item["subject"] for item in radiation["dose_rate"]["readings"]] == ["crew-01"]
    [aside] = radiation["dose_rate"]["set_aside"]
    assert (aside["subject"], aside["counts"]) == ("crew-02", {"inferred": 5})
    assert aside["shown"] is False
    assert aside["text"].startswith(alert_support.typed_readings({"inferred": 5}))
    assert "sin ninguna lectura de las que deciden" in aside["text"]
    # Los tipos que deciden, con las palabras derivadas de `ANALYSED_TYPES`, no escritas a mano.
    assert f"solo lee lecturas {routes.analysed_type_words()}" in aside["text"]
    assert routes.analysed_type_words() == "medidas"
    assert radiation["dose_rate"]["set_aside_rule"] == alert_support.ANALYSED_RULE
    assert radiation["dose_rate"]["set_aside_display"] == cabin.DOSE_RATE_SET_ASIDE_DISPLAY
    # En el resumen, con quién: es lo que la capa del hábitat del gemelo repite como nota.
    assert f"crew-02: {aside['text']}." in radiation["summary"]
    assert any(f"crew-02: {aside['text']}." in note for note in _habitat_notes(client, "crew-02"))


def test_a_crew_member_shown_with_a_measured_reading_counts_the_rest_like_the_comparison(
    client: TestClient,
) -> None:
    _flow(client)
    # Dentro del flujo y después de la última medida: sin §5.38.7 serían «la última».
    _post(client, "absorbed-dose-rate", 80.0, LAST + dt.timedelta(minutes=30), kind="inferred")
    _post(client, "absorbed-dose-rate", 90.0, LAST + dt.timedelta(minutes=40), kind="predicted")

    radiation = _radiation(client)
    [reading] = radiation["dose_rate"]["readings"]
    assert (reading["value"], reading["observation_type"]) == (12.0, "measured")
    [aside] = radiation["dose_rate"]["set_aside"]
    assert (aside["subject"], aside["shown"]) == ("crew-01", True)
    assert aside["counts"] == {"inferred": 1, "predicted": 1}
    assert aside["text"].startswith(alert_support.typed_readings({"inferred": 1, "predicted": 1}))
    assert f"última de las {routes.analysed_type_words()}" in aside["text"]
    assert "sin ninguna lectura" not in aside["text"]
    # La misma cuenta que la comparación entre tripulantes para este indicador (§5.38.7).
    compare = client.get("/api/crew/compare", params={"key": "absorbed-dose-rate"}).json()
    series = {item["subject"]: item for item in compare["series"]}
    assert series["crew-01"]["set_aside"] == aside["counts"]


def test_with_only_measured_dose_rates_nothing_is_set_aside_and_nothing_is_said(
    client: TestClient,
) -> None:
    _flow(client)
    radiation = _radiation(client)
    assert radiation["dose_rate"]["set_aside"] == []
    assert radiation["dose_rate"]["set_aside_rule"] is None
    assert "crew-01:" not in radiation["summary"]


def test_two_crew_members_set_aside_come_sorted_by_name(client: TestClient) -> None:
    for subject in ("crew-03", "crew-02"):
        _flow(client, subject, dose=False)
        _modelled_doses(client, subject, 2)
    aside = _radiation(client)["dose_rate"]["set_aside"]
    assert [item["subject"] for item in aside] == ["crew-02", "crew-03"]
    assert _radiation(client)["dose_rate"]["readings"] == []


def test_the_ground_counts_only_what_reached_it(client: TestClient) -> None:
    _flow(client)
    _post(client, "absorbed-dose-rate", 80.0, T0 + dt.timedelta(hours=30), kind="inferred")
    cut = (T0 + dt.timedelta(hours=25)).isoformat()
    assert _radiation(client, until=cut)["dose_rate"]["set_aside"] == []
    [aside] = _radiation(client)["dose_rate"]["set_aside"]
    assert aside["counts"] == {"inferred": 1}


# --------------------------------------------------------------------------- #
# El diario y las sesiones PVT: una posición más, la del tipo
# --------------------------------------------------------------------------- #


def _diary_positions(client: TestClient) -> list[tuple[str, str, str]]:
    body = client.get("/api/diary/entries").json()
    return [
        (item["observation_type"], item["position"], item["position_note"])
        for item in body["entries"]
    ]


def test_an_old_inferred_diary_entry_says_the_state_does_not_read_it_by_type(
    client: TestClient,
) -> None:
    _flow(client)
    # Las tres son del diario (alta manual de un indicador suyo); la de en medio, inferida.
    _post(client, "mood-valence", 6.0, LAST - dt.timedelta(hours=1))
    _post(client, "mood-valence", 4.0, T0 - dt.timedelta(days=5), kind="inferred")
    _post(client, "mood-valence", 5.0, T0 - dt.timedelta(days=10))

    body = client.get("/api/diary/entries").json()
    assert body["reference_time"] == LAST.isoformat()
    kinds, positions, notes = zip(*_diary_positions(client), strict=True)
    assert kinds == ("measured", "inferred", "measured")
    assert positions == ("current", diary.NOT_ANALYSED_BY_TYPE, "earlier")
    assert positions[1] == "not-analysed-by-type"
    # La frase dice el tipo y que no se sitúa frente a la ventana; no «anterior a la ventana».
    assert "inferida" in notes[1] and "no la lee por su tipo" in notes[1]
    assert "Anterior" not in notes[1]


def test_a_predicted_entry_names_its_type(client: TestClient) -> None:
    _flow(client)
    _post(client, "appetite-rating", 7.0, LAST - dt.timedelta(hours=2), kind="predicted")
    [(kind, position, note)] = _diary_positions(client)
    assert (kind, position) == ("predicted", "not-analysed-by-type")
    assert "predicha" in note and "inferida" not in note


def test_with_nothing_that_decides_no_entry_is_placed_against_the_bound(
    client: TestClient,
) -> None:
    """Solo entradas inferidas: la referencia es nula y ninguna se sitúa frente a la cota con que
    `_analysable` responde a una lista vacía (antes salían «fechadas después de la referencia»)."""
    _post(client, "mood-valence", 4.0, T0 - dt.timedelta(days=10), kind="inferred")
    _post(client, "mood-valence", 5.0, T0 + dt.timedelta(days=400), kind="inferred")
    body = client.get("/api/diary/entries").json()
    assert body["reference_time"] is None and body["count"] == 2
    assert {item["position"] for item in body["entries"]} == {"not-analysed-by-type"}


def test_an_inferred_pvt_session_says_the_state_does_not_read_it_by_type(
    client: TestClient,
) -> None:
    _flow(client)
    when = T0 + dt.timedelta(hours=20)
    for key, value in (("pvt-mean-rt", 300.0), ("pvt-lapses", 2.0)):
        _post(client, key, value, when, kind="inferred", source="pvt-test")
    [session] = client.get("/api/pvt/sessions").json()["sessions"]
    assert (session["observation_type"], session["position"]) == (
        "inferred", "not-analysed-by-type",
    )
    assert "inferida" in session["position_note"]
    # El testigo: la misma prueba medida, una hora después, sí está en la ventana del estado.
    for key, value in (("pvt-mean-rt", 300.0), ("pvt-lapses", 2.0)):
        _post(client, key, value, when + dt.timedelta(hours=1), source="pvt-test")
    sessions = client.get("/api/pvt/sessions").json()["sessions"]
    assert [item["position"] for item in sessions] == ["current", "not-analysed-by-type"]


def test_two_readings_of_the_same_instant_and_source_with_distinct_types_are_two_sessions(
    client: TestClient,
) -> None:
    """Agrupadas solo por instante y fuente, la fila tomaba el tipo y la posición de la primera
    lectura y callaba los de la segunda (revisión de código, §5.39.11)."""
    _flow(client)
    when = T0 + dt.timedelta(hours=20)
    _post(client, "pvt-mean-rt", 300.0, when, source="pvt-test")
    _post(client, "pvt-lapses", 2.0, when, kind="inferred", source="pvt-test")
    body = client.get("/api/pvt/sessions").json()
    assert body["count"] == 2
    rows = {item["observation_type"]: item for item in body["sessions"]}
    assert rows["measured"]["position"] == "current"
    assert rows["inferred"]["position"] == "not-analysed-by-type"
    assert [value["key"] for value in rows["measured"]["values"]] == ["pvt-mean-rt"]
    assert [value["key"] for value in rows["inferred"]["values"]] == ["pvt-lapses"]


def test_every_observation_type_has_its_words() -> None:
    """`_position` indexa `TYPE_WORDS` con el tipo de la entrada: un tipo nuevo sin palabra
    convertiría el listado entero del diario en un 500."""
    assert set(alert_support.TYPE_WORDS) == {str(kind) for kind in ObservationType}
    assert routes.analysed_type_words() == " o ".join(
        alert_support.TYPE_WORDS[str(kind)][1] for kind in routes.ANALYSED_TYPES
    )


# --------------------------------------------------------------------------- #
# Nada de esto decide, firma ni suena a orden
# --------------------------------------------------------------------------- #


def test_saying_what_is_set_aside_decides_nothing_and_signs_nothing(client: TestClient) -> None:
    # Dos tripulantes con estado (`/api/crew` evalúa a los dos); el segundo, con la tasa de dosis
    # solo inferida. El escenario simulado entero se mira en vivo (§5.39.11), no aquí: con él,
    # esta prueba era la más lenta de la campaña de mutantes.
    _flow(client, "crew-01")
    _flow(client, "crew-09", dose=False)
    _modelled_doses(client, "crew-09", 3)
    _post(client, "mood-valence", 4.0, T0 - dt.timedelta(days=5), kind="inferred")
    before = _verdict(client)
    size = len(get_store().ledger)

    radiation = _radiation(client)
    assert [item["subject"] for item in radiation["dose_rate"]["set_aside"]] == ["crew-09"]
    assert any(
        item["position"] == "not-analysed-by-type"
        for item in client.get("/api/diary/entries").json()["entries"]
    )
    client.get("/api/pvt/sessions")
    client.get("/api/twins", params={"subject": "crew-09"})
    assert len(get_store().ledger) == size, "decir lo apartado no firma nada"
    assert _verdict(client) == before


@pytest.mark.parametrize(
    "text",
    [
        habitat.DOSE_RATE_SET_ASIDE_SHOWN.format(
            typed=alert_support.typed_readings({"inferred": 2, "predicted": 1}),
            analysed=routes.analysed_type_words(),
        ),
        habitat.DOSE_RATE_SET_ASIDE_ONLY.format(
            typed=alert_support.typed_readings({"inferred": 1}),
            analysed=routes.analysed_type_words(),
        ),
        cabin.DOSE_RATE_SET_ASIDE_DISPLAY,
        *(
            diary.NOT_ANALYSED_BY_TYPE_NOTE.format(
                kind=words[0], analysed=routes.analysed_type_words()
            )
            for words in alert_support.TYPE_WORDS.values()
        ),
    ],
)
def test_nothing_written_here_sounds_like_an_order(text: str) -> None:
    # «dosis» es aquí de radiación, no de un fármaco (como en test_habitat_radiation.py).
    found = [
        finding for finding in check(text)
        if (finding.category, finding.match.lower()) != ("dosing", "dosis")
    ]
    assert found == [], text
