"""La vista de tripulación de Tierra (`GET /api/crew?until=`) solo lee la cabina de su corte.

Existe porque el cierre de la ronda 16 (§5.36) dejó escrito que `crew_overview` lee las lecturas
de cabina con el corte de Tierra y que ninguna prueba lo vigilaba: si esa lectura ignorase
`until`, Tierra correlacionaría a la tripulación con un tramo de excursión que en su corte aún
no ha llegado —un dato del futuro de la nave— y nada se pondría rojo. La campaña
`tests/mutants/habitat_crew_api.json` comprueba que estas pruebas cazan ese descuido.
"""

import datetime as dt
from typing import Any

from fastapi.testclient import TestClient

SCENARIO = {"scenario": "co2-fatigue", "days": 10, "crew_size": 4, "replace": "true"}
# A mitad de la excursión de CO2 del escenario: ya ha empezado, todavía no ha acabado.
CUT = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.UTC)


def _when(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def _with_excursion(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in view["correlation"]["hypotheses"] if item["excursion"]]


def test_ground_sees_the_cabin_excursion_only_up_to_its_cut(client: TestClient) -> None:
    assert client.post("/api/simulate", params=SCENARIO).status_code == 201
    aboard = client.get("/api/crew").json()
    [shared] = [item for item in _with_excursion(aboard) if item["kind"] == "shared_environment"]
    start, end = _when(shared["excursion"]["start"]), _when(shared["excursion"]["end"])
    # Premisa: el corte cae dentro de la excursión vista a bordo.
    assert start < CUT < end

    ground = client.get("/api/crew", params={"until": CUT.isoformat()}).json()
    assert _when(ground["reference_time"]) <= CUT
    found = _with_excursion(ground)
    # Tierra ve la excursión que ya había empezado en su corte, con el mismo comienzo...
    assert [item["excursion"]["start"] for item in found
            if item["kind"] == "shared_environment"] == [shared["excursion"]["start"]]
    # ...pero nada de lo que la cabina midió después del corte.
    assert all(_when(item["excursion"]["end"]) <= CUT for item in found), found
    # Y lo mismo que dice el hábitat de Tierra con ese corte: una sola fuente para la cabina.
    habitat = client.get("/api/habitat", params={"until": CUT.isoformat()}).json()
    ends = {
        (item["parameter"], item["start"]): item["end"]
        for item in [*habitat["active"], *habitat.get("excursions", [])]
    }
    for item in found:
        key = (item["excursion"]["parameter"], item["excursion"]["start"])
        if key in ends:
            assert item["excursion"]["end"] == ends[key]


def test_a_cabin_excursion_after_the_cut_does_not_reach_ground(client: TestClient) -> None:
    assert client.post("/api/simulate", params=SCENARIO).status_code == 201
    aboard = client.get("/api/crew").json()
    reference = _when(aboard["reference_time"])
    # Un tramo de CO2 muy por encima del límite, entero después del corte, firmado por un
    # sensor real: a bordo cuenta; Tierra, con su corte, todavía no lo conoce.
    later = CUT + dt.timedelta(hours=6)
    assert later < reference
    for minutes in range(0, 180, 15):
        response = client.post("/api/habitat", json={
            "parameter": "cabin-ppco2", "value": 9.0,
            "effective": (later + dt.timedelta(minutes=minutes)).isoformat(),
        })
        assert response.status_code == 201, response.text
    # Premisa: a bordo ese tramo sí está en la correlación.
    assert any(
        _when(item["excursion"]["end"]) >= later
        for item in _with_excursion(client.get("/api/crew").json())
    )
    ground = client.get("/api/crew", params={"until": CUT.isoformat()}).json()
    assert _with_excursion(ground)
    for item in _with_excursion(ground):
        assert _when(item["excursion"]["start"]) <= CUT
        assert _when(item["excursion"]["end"]) <= CUT, item["excursion"]
