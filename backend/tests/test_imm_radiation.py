"""Lo que el IMM de NASA publica sobre radiación (`evidence/imm_radiation.py`).

Lo que vigilan estas pruebas: que cada probabilidad servida esté, tal cual, en la fila citada de su
tabla; que los meses y las EVA de cada misión de referencia estén en la fila citada de la Tabla 1;
que todo perfil de EMMA tenga su misión de referencia con motivo y que ninguno apunte a una que no
existe; que EMMA no escriba una cifra suya; que la ficha esté en el registro y diga cuándo se leyó;
y que la ruta señale el perfil declarado sin tocar nada que decida. Ninguna toca la red.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import imm_radiation, mission_profiles
from app.main import app

RAW: dict[str, Any] = json.loads(imm_radiation.DATA_PATH.read_text(encoding="utf-8"))


def _mutated(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    change(raw)
    return raw


def test_the_file_loads_and_every_profile_has_its_reference_mission() -> None:
    served = imm_radiation.describe(None)
    assert {item["id"] for item in served["profiles"]} == set(mission_profiles.EXPECTED_IDS)
    keys = {item["key"] for item in served["drms"]}
    assert all(item["drm"] in keys and item["reason"] for item in served["profiles"])
    assert served["condition"] == "Acute Radiation Syndrome"


def test_each_probability_is_the_cited_row_of_its_table() -> None:
    for item in imm_radiation.describe(None)["drms"]:
        assert item["probability_text"] in item["row_quote"].split()
        assert float(item["probability_text"]) == item["probability"]
        assert "Acute Radiation Syndrome" in item["row_quote"]


def test_the_figures_are_the_ones_read_in_the_report() -> None:
    drms = imm_radiation.describe(None)["drms"]
    by_key = {item["key"]: item["probability_text"] for item in drms}
    assert by_key == {
        "leo-6": "1.41E-03",
        "leo-12": "2.83E-03",
        "deep-space-sortie": "2.36E-04",
        "lunar-12": "2.83E-03",
        "deep-space-journey-12": "2.83E-03",
        "planetary-36": "8.45E-03",
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw["drms"][0].__setitem__("probability", "9.99E-03"), "fila citada"),
        (lambda raw: raw["drms"][0].__setitem__("probability", "0.00141"), "como en el informe"),
        (lambda raw: raw["drms"][0].__setitem__("months", 7), "Tabla 1"),
        (lambda raw: raw["drms"][0].__setitem__("evas", 3), "Tabla 1"),
        (lambda raw: raw["drms"][0].__setitem__("row_quote", "Acute Arthritis 1.41E-03"), "fila"),
        (lambda raw: raw["profiles"]["leo"].__setitem__("drm", "iss-forever"), "no es una misión"),
        (lambda raw: raw["profiles"].pop("mars-surface"), "los de EMMA"),
        (lambda raw: raw["profiles"].__setitem__("venus", {"drm": "leo-6", "reason": "x"}), "EMMA"),
        (lambda raw: raw["profiles"]["leo"].__setitem__("reason", "seis meses, 180 días"), "cifra"),
        (lambda raw: raw.__setitem__("caveat_display", "en el 50 % de los casos"), "cifra"),
        (lambda raw: raw.__setitem__("caveat_quote", "baselined to the ISS"), "condición"),
        (lambda raw: raw.__setitem__("ref", "imm-que-no-existe"), "registro"),
        (lambda raw: raw.__setitem__("read_on", "2026-11-13"), "Leída el"),
        (lambda raw: raw["drms"].append(copy.deepcopy(raw["drms"][0])), "repetida"),
        (lambda raw: raw.__setitem__("kp_forecast", 4), "sobran"),
    ],
)
def test_each_defence_rejects_its_mutant(
    change: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(imm_radiation.ImmError, match=message):
        imm_radiation.validate(_mutated(change))


@pytest.fixture
def api(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_profile="mars-transit"
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_route_marks_the_declared_profile_and_says_it_decides_nothing(api: TestClient) -> None:
    body = api.get("/api/radiation/imm").json()
    declared = [item for item in body["profiles"] if item["declared"]]
    assert [item["id"] for item in declared] == ["mars-transit"]
    assert declared[0]["drm"] == "deep-space-journey-12"
    assert declared[0]["probability_text"] == "2.83E-03"
    assert "no entra en ningún nivel" in body["scope"]
    assert body["source"]["id"] == "imm-ranking-2015"
    assert body["source"]["url"].startswith("https://www.nasa.gov/")


def test_the_route_wants_a_zoned_cut(api: TestClient) -> None:
    assert api.get("/api/radiation/imm", params={"until": "2026-11-14T00:00:00"}).status_code == 422
